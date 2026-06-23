"""Framework-side knowledge graph for structural note deduplication.

Pipeline per new or changed note (runs inside submit_eval before git add):
  1. Hash check   — exact copy → delete immediately, zero cost
  2. TF-IDF pre-filter — flags suspicious pairs for LLM comparison
  3. LLM verdict  — duplicate / novel / contradiction (OpenRouter only)

The graph lives at .coral/private/knowledge_graph.json — not visible to agents.
Failures at any stage are silent: the note is kept and the eval proceeds normally.
"""

from __future__ import annotations

import hashlib
import json
import logging
import math
import os
import re
from collections import Counter
from datetime import UTC, datetime
from pathlib import Path

logger = logging.getLogger(__name__)

_GRAPH_FILE = "knowledge_graph.json"
_TFIDF_THRESHOLD = 0.70


# ---------------------------------------------------------------------------
# Graph I/O
# ---------------------------------------------------------------------------


def _load_graph(private_dir: Path) -> dict:
    path = private_dir / _GRAPH_FILE
    if path.exists():
        try:
            return json.loads(path.read_text())
        except (json.JSONDecodeError, OSError):
            pass
    return {"notes": {}, "dedup_log": [], "contradictions": []}


def _save_graph(private_dir: Path, graph: dict) -> None:
    path = private_dir / _GRAPH_FILE
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(graph, indent=2))
    tmp.replace(path)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _now() -> str:
    return datetime.now(UTC).isoformat()


def _note_hash(path: Path) -> str:
    return hashlib.md5(path.read_bytes()).hexdigest()


def _word_counts(text: str) -> Counter:
    return Counter(re.findall(r"\b[a-z]{3,}\b", text.lower()))


def _is_user_note(p: Path) -> bool:
    return p.name != "notes.md" and not p.name.startswith("_")


# ---------------------------------------------------------------------------
# TF-IDF similarity
# ---------------------------------------------------------------------------


def _tfidf_similarity(
    counts_a: Counter,
    counts_b: Counter,
    corpus: list[Counter],
) -> float:
    """Cosine similarity of smoothed TF-IDF vectors over the given corpus."""
    n = max(len(corpus), 1)
    vocab = set(counts_a) | set(counts_b)

    idf: dict[str, float] = {}
    for term in vocab:
        df = sum(1 for c in corpus if term in c)
        idf[term] = math.log((n + 1) / (df + 1))

    def vec(counts: Counter) -> dict[str, float]:
        total = max(sum(counts.values()), 1)
        return {t: (counts[t] / total) * idf[t] for t in vocab if t in counts}

    va, vb = vec(counts_a), vec(counts_b)
    dot = sum(va.get(t, 0) * vb.get(t, 0) for t in vocab)
    na = math.sqrt(sum(x**2 for x in va.values())) or 1.0
    nb = math.sqrt(sum(x**2 for x in vb.values())) or 1.0
    return dot / (na * nb)


# ---------------------------------------------------------------------------
# LLM verdict (OpenRouter)
# ---------------------------------------------------------------------------

_VERDICT_PROMPT = """\
Compare these two research notes. Respond with JSON only — no other text.

Note A (existing):
{a}

Note B (new):
{b}

{{"verdict": "duplicate" | "novel" | "contradiction", "reason": "<one sentence>"}}

duplicate     = B makes the same claims as A, even if worded differently
contradiction = B conflicts with A on a specific claim
novel         = B contains meaningfully different information"""


def _llm_verdict(text_a: str, text_b: str, model: str) -> str:
    """Call the LLM and return 'duplicate', 'novel', or 'contradiction'.

    Returns 'novel' on any failure so the note is always kept when uncertain.
    Only supports OpenRouter models (openrouter/... prefix).
    """
    api_key = os.environ.get("OPENROUTER_API_KEY", "")
    if not api_key or not model.startswith("openrouter/"):
        return "novel"

    try:
        import httpx
    except ImportError:
        return "novel"

    api_model = model.removeprefix("openrouter/")
    prompt = _VERDICT_PROMPT.format(a=text_a[:1500], b=text_b[:1500])

    try:
        resp = httpx.post(
            "https://openrouter.ai/api/v1/chat/completions",
            headers={"Authorization": f"Bearer {api_key}"},
            json={
                "model": api_model,
                "messages": [{"role": "user", "content": prompt}],
                "response_format": {"type": "json_object"},
                "max_tokens": 80,
            },
            timeout=30,
        )
        resp.raise_for_status()
        data = json.loads(resp.json()["choices"][0]["message"]["content"])
        verdict = data.get("verdict", "novel")
        return verdict if verdict in ("duplicate", "novel", "contradiction") else "novel"
    except Exception as exc:
        logger.debug("LLM verdict failed, keeping note: %s", exc)
        return "novel"


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------


def deduplicate_notes(
    coral_dir: Path | str,
    notes_dir: Path | str,
    model: str,
    tfidf_threshold: float = _TFIDF_THRESHOLD,
) -> list[str]:
    """Remove duplicate notes before they are staged in submit_eval.

    Returns the list of filenames deleted.  Never raises — all errors are
    logged at DEBUG level and the function returns [] so the eval proceeds.
    """
    try:
        return _deduplicate_notes(Path(coral_dir), Path(notes_dir), model, tfidf_threshold)
    except Exception as exc:
        logger.debug("deduplicate_notes failed, skipping: %s", exc)
        return []


def _deduplicate_notes(
    coral_dir: Path,
    notes_dir: Path,
    model: str,
    tfidf_threshold: float,
) -> list[str]:
    if not notes_dir.exists():
        return []

    private_dir = coral_dir / "private"
    private_dir.mkdir(parents=True, exist_ok=True)
    graph = _load_graph(private_dir)

    known: dict = graph.setdefault("notes", {})
    dedup_log: list = graph.setdefault("dedup_log", [])
    contradictions: list = graph.setdefault("contradictions", [])

    # Build corpus of known note term counters for TF-IDF IDF calculation.
    corpus = [Counter(v["terms"]) for v in known.values()]

    md_files = sorted(f for f in notes_dir.rglob("*.md") if _is_user_note(f))
    removed: list[str] = []

    for path in md_files:
        fname = path.name
        h = _note_hash(path)

        # Already registered and unchanged — nothing to do.
        if fname in known and known[fname]["hash"] == h:
            continue

        # --- Layer 1: hash check ---
        # Check if this content already exists under a different (or same) name.
        duplicate_of = next(
            (n for n, v in known.items() if v["hash"] == h and n != fname),
            None,
        )
        if duplicate_of:
            path.unlink()
            removed.append(fname)
            dedup_log.append(
                {"removed": fname, "duplicate_of": duplicate_of, "method": "hash", "ts": _now()}
            )
            logger.debug("Removed exact duplicate %s (same content as %s)", fname, duplicate_of)
            continue

        # --- Layer 2: TF-IDF pre-filter ---
        text = path.read_text()
        counts = _word_counts(text)
        best_name, best_sim = None, 0.0

        for existing_name, existing_v in known.items():
            sim = _tfidf_similarity(counts, Counter(existing_v["terms"]), corpus)
            if sim > best_sim:
                best_sim, best_name = sim, existing_name

        if best_sim >= tfidf_threshold and best_name:
            # --- Layer 3: LLM verdict ---
            existing_path = notes_dir / best_name
            existing_text = existing_path.read_text() if existing_path.exists() else ""
            verdict = _llm_verdict(existing_text, text, model) if existing_text else "novel"

            if verdict == "duplicate":
                path.unlink()
                removed.append(fname)
                dedup_log.append(
                    {
                        "removed": fname,
                        "duplicate_of": best_name,
                        "method": "llm",
                        "similarity": round(best_sim, 3),
                        "ts": _now(),
                    }
                )
                logger.debug(
                    "Removed semantic duplicate %s (%.0f%% similar to %s)",
                    fname,
                    best_sim * 100,
                    best_name,
                )
                continue

            if verdict == "contradiction":
                contradictions.append(
                    {"note_a": best_name, "note_b": fname, "ts": _now()}
                )
                logger.debug("Contradiction flagged: %s vs %s", best_name, fname)

        # Novel (or contradiction kept): register in graph.
        known[fname] = {"hash": h, "terms": dict(counts), "added": _now()}
        corpus.append(counts)

    _save_graph(private_dir, graph)
    return removed
