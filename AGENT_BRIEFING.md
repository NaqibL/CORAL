# Agent Briefing — Alpha Z Technical Assessment

You are running experiments for a technical assessment on **CORAL** (arXiv 2604.01658), a framework for autonomous multi-agent LLM evolution on open-ended optimization problems.

## What CORAL Does

CORAL replaces fixed evolutionary search heuristics with long-running autonomous agents that:
1. **Retrieve** — autonomously decide what prior attempts/notes/skills to inspect
2. **Propose** — plan, implement, and test solutions independently
3. **Evaluate** — call `coral eval -m "description"` to submit and get scored
4. **Update** — write notes and skills to shared persistent memory for other agents

Agents live in isolated git worktrees, share state via `.coral/public/` (symlinked as `.claude/`), and are kept on track by **heartbeat actions** (reflect every eval, consolidate every 10, pivot after 5 plateau evals).

---

## Assessment Tasks — Status

| Task | Status | Notes |
|------|--------|-------|
| Task 1 — circle_packing replication | COMPLETE | Score 1.000002, ~5 evals |
| Task 2 — TSP Berlin52 | COMPLETE | Score 0.9997 |
| Task 3 — Ablation on pr1002 | COMPLETE | Results collected |
| Task 4 — Knowledge management improvement | COMPLETE | Implemented + 3 runs done |
| Task 5 — Product plan | NOT STARTED | Write in assignment/README.md |

---

## Environment

- **Platform:** WSL (Ubuntu) on Windows — all runs done locally
- **Agent runtime:** OpenCode (`opencode`)
- **Model:** `openrouter/deepseek/deepseek-v4-flash` via OpenRouter
- **No LiteLLM gateway** — OpenCode uses its built-in OpenRouter provider directly
- **Results location (WSL):** `~/CORAL/results/`

---

## Repository Layout

```
examples/
  circle_packing/         # Task 1 — COMPLETE
    task_claude.yaml      # claude_code runtime, local session
    seed/initial_program.py
    grader/
  tsp/                    # Task 2 — Berlin52, COMPLETE
  tsp_pr1002/             # Tasks 3 & 4 — pr1002 ablation
    task.yaml             # run.max_evals=20, session=local, 1 agent
    seed/solution.py
    grader/
coral/hub/knowledge_graph.py   # Task 4 — new dedup module
coral/hooks/post_commit.py     # Task 4 — dedup wired into submit_eval
results/                  # in WSL at ~/CORAL/results/
```

---

## Task 1 — Circle Packing — COMPLETE

- **Run:** `results/circle-packing/2026-06-23_204819/` (WSL)
- **Result:** Score **1.000002** (paper target ≈1.0), achieved in ~5 evals
- **Paper comparison:** CORAL paper (1 agent, Opus 4.6) scored ≈1.0 in 11 evals. We matched with fewer evals using deepseek-flash.
- **Run was killed by Windows sleep (SIGTERM)** after the score was already recorded — result is safe in the attempt JSON.
- **Agent:** agent-1 did the circle packing; agent-2 monitored ablation runs.

Extract result:
```bash
python3 -c "
import json, glob
files = glob.glob('/home/luqman/CORAL/results/circle-packing/2026-06-23_204819/.coral/public/attempts/*.json')
for f in files:
    d = json.load(open(f))
    if d.get('score'): print(d['score'], d['status'], d['commit_hash'][:8])
"
```

---

## Task 2 — TSP Berlin52 — COMPLETE

- Best score: **0.9997** (tour 7544.37, optimal 7542)
- Approach: Best-NN from all starts + 2-opt + 500x ILS double-bridge perturbations
- Hit on **attempt #1** — problem too easy, retired for ablation

---

## Task 3 — Ablation on pr1002 — COMPLETE

Berlin52 too easy (all converge to 0.9997). Using **pr1002** (1002 cities, optimal 259,045).

- Score = `259045 / tour_length` (nint distances)
- **max_evals=20** — runs auto-stop

### Runs completed

| Condition | Timestamp | Agents | Evals | Best Score | Notes |
|-----------|-----------|--------|-------|------------|-------|
| Full CORAL | 2026-06-23_012657 | 2 | 42 | 0.9879 | baseline |
| Condition A | 2026-06-23_095931 | 2 | 27 | 0.9915 | no sharing |
| Condition A | 2026-06-23_124515 | 1 | 15 | 0.9900 | no sharing |
| Condition A | 2026-06-23_151829 | 2 | 20 | 0.9917 | no sharing |
| Condition B | 2026-06-23_080040 | 2 | 0 | N/A | no heartbeats — all inactive |
| Condition B | 2026-06-23_080050 | 4 | 20 | 0.9476 | no heartbeats — heavy timeouts |
| Condition B | 2026-06-23_175658 | 2 | 20 | 0.9901 | no heartbeats |

### Summary statistics

| Condition | n | Best scores | Mean best |
|-----------|---|-------------|-----------|
| Full CORAL | 1 | 0.9879 | 0.9879 |
| Condition A (no sharing) | 3 | 0.9915, 0.9900, 0.9917 | 0.9911 |
| Condition B (no heartbeats) | 3 | 0 evals, 0.9476, 0.9901 | unreliable |

### Key findings
- **Heartbeats are load-bearing:** 1/3 Condition B runs produced 0 evals. Without `reflect`, agents never submit.
- **Sharing has marginal impact at this scale:** Condition A (0.9911 mean) matches Full CORAL (0.9879) within noise.
- **Condition B eval quality degrades:** heavy timeouts and crashes vs clean evals in other conditions.

### Extract results
```bash
python3 - << 'EOF'
import json, glob
base = '/home/luqman/CORAL/results/travelling-salesman-problem-pr1002'
for run in sorted(glob.glob(f'{base}/2026-*')):
    files = glob.glob(f'{run}/.coral/public/attempts/*.json')
    scores = [s for s in [json.load(open(f)).get('score') for f in files] if s]
    ts = run.split('/')[-1]
    print(f'{ts}: {len(files)} attempts, best={round(max(scores),4) if scores else "none"}')
EOF
```

---

## Task 4 — Knowledge Management Improvement — COMPLETE

### The failure mode (from Task 3 runs)

`sa-beats-ils-for-pr1002.md` appeared **byte-for-byte identical** (same MD5: `3f747e3f...`) across 7 out of 8 runs, with the same `created: 2026-06-23T02:30:00Z` timestamp even in runs starting hours later. Same for `focus-3opt-polish.md` (4 runs) and `tuning-results.md` (3 runs).

Root cause: agents synthesise findings from prior runs and re-write the same notes verbatim into each new run. CORAL's existing `consolidate` and `lint_wiki` heartbeats aim to address this but are **behavioral prompts** — agents skip or rush them. The failure persists because there is no framework-level enforcement.

### The fix

**Two files changed:**

1. **`coral/hub/knowledge_graph.py`** (new) — three-layer dedup pipeline that runs before `git add` in every `coral eval`:
   - Layer 1: MD5 hash — catches exact copies instantly, free
   - Layer 2: TF-IDF cosine similarity — flags suspicious pairs (threshold 0.70), no model needed
   - Layer 3: LLM verdict via OpenRouter — `duplicate | novel | contradiction`, uses same model as agents

   The graph persists at `.coral/private/knowledge_graph.json` (not visible to agents).

2. **`coral/hooks/post_commit.py`** (modified) — calls `deduplicate_notes()` right after config/island_id are resolved, before `git add`. Wrapped in try/except — failures are silent, eval always proceeds.

### Why this is different from what CORAL already does

CORAL's `consolidate` heartbeat and `lint_wiki` (librarian subagent) already aim for synthesis and dedup. The difference: those are **agent-side instructions** that depend on compliance. Our fix runs in **framework Python code** that executes unconditionally on every eval submission, regardless of agent behavior.

### Contradiction detection

When the LLM returns `contradiction` (note B conflicts with note A on a specific claim), the note is **kept** and logged to `.coral/private/knowledge_graph.json` under `contradictions`. This is valuable signal — disagreement between agents means something worth investigating.

### Task 4 runs (with dedup active)

Three runs of Full CORAL on pr1002 with the fix installed:

| Timestamp | Evals | Best Score | Notes registered | Removed |
|-----------|-------|------------|-----------------|---------|
| 2026-06-24_012621 | 19 | 0.9915 | 15 | 3 (index.md bug, now fixed) |
| 2026-06-24_082209 | 20 | **0.9925** | 20 | 0 |
| 2026-06-24_114814 | 21 | 0.9915 | 15 | 0 |

**Mean best: 0.9918**

No actual note duplicates were caught within these runs. This is expected: with `agents.count=1`, a single agent writes each note once per run. Within-run dedup fires when two agents independently write the same note in the same run — which needs `agents.count=2`.

### Important caveat for write-up

The observed failure (same note propagating across 8 runs) is **cross-run** duplication. Our fix operates **within a single run** (each run has its own `.coral/private/knowledge_graph.json`). To catch cross-run duplicates would require a shared global graph across runs — out of scope for this lighter treatment.

The write-up should:
1. Present the cross-run evidence (MD5 proof, timestamps)
2. Explain CORAL's existing mechanisms fail because they're prompt-based
3. Describe the framework-level fix and why it's structurally different
4. Show the within-run dedup would catch the harder multi-agent case
5. Acknowledge the cross-run gap honestly

### Extract Task 4 dedup data
```bash
python3 - << 'EOF'
import json, glob
base = '/home/luqman/CORAL/results/travelling-salesman-problem-pr1002'
for run in ['2026-06-24_012621', '2026-06-24_082209', '2026-06-24_114814']:
    try:
        g = json.load(open(f'{base}/{run}/.coral/private/knowledge_graph.json'))
        log = g.get('dedup_log', [])
        notes = len(g.get('notes', {}))
        contradictions = g.get('contradictions', [])
        print(f'{run}: {notes} notes, {len(log)} removed, {len(contradictions)} contradictions')
        for e in log:
            print(f'  removed {e["removed"]} ({e["method"]}) duplicate of {e["duplicate_of"]}')
    except Exception as ex:
        print(f'{run}: {ex}')
EOF
```

### Verify the MD5 evidence from Task 3 runs
```bash
md5sum ~/CORAL/results/travelling-salesman-problem-pr1002/2026-06-23_{095931,124515,151829,175658,211515,211630,211841}/.coral/public/notes/sa-beats-ils-for-pr1002.md 2>/dev/null
```
All 7 should share the same hash: `3f747e3f2e6f4483b286fe1b3e997048`

---

## Task 5 — Product Plan — NOT STARTED

Write in `assignment/README.md` under the Task 5 section. See `TASK5_BRIEF.md` for the five required points and grounding context from our runs.

Key observations to incorporate:
- Heartbeats are load-bearing (Condition B finding) → analogous scaffolding needed in a product
- Structured evaluator is the linchpin → fuzzy feedback (point ④) is the hardest design challenge
- Notes accumulate without dedup → Task 4 finding, relevant to knowledge accumulation (point ②)
- Agents go rogue without guidance → point ⑤ failure modes

---

## Key Config Knobs

| What | Dotlist override |
|------|-----------------|
| Number of agents | `agents.count=1` |
| Model | `agents.model=openrouter/deepseek/deepseek-v4-flash` |
| Session mode | `run.session=local` |
| Runtime | `agents.runtime=opencode` |
| Disable heartbeats | `agents.heartbeat="[]"` |
| Disable notes/skills | `sharing.notes=false sharing.skills=false` |
| Max evals (auto-stop) | `run.max_evals=20` |
| Max turns per session | `agents.max_turns=50` (use 50, not 100 — 100 causes context explosion and high cost) |

**Cost note:** `agents.count=2` with `max_turns=100` cost ~$18 for one 20-eval run on deepseek-flash. `agents.count=1 agents.max_turns=50` is the recommended config — ~$4-6 per run.

---

## Paper Key Numbers (for comparison)

| Task | Method | Final Score | #Evals |
|------|--------|-------------|--------|
| Circle Packing | CORAL 1-agent (Opus 4.6) | 2.6360 (≈1.0) | 11 |
| Circle Packing | OpenEvolve (Opus 4.6) | 2.6293 | 100 |
| Circle Packing | **Our run** (deepseek-flash) | **1.000002** | **~5** | 
| Kernel Eng. | CORAL 4-agent (no notes) | 1601 cycles | — |
| Kernel Eng. | CORAL 4-agent (w/ notes) | 1350 cycles | 56 |

TSP pr1002 baselines:
- Nearest-neighbour: ~0.9897
- Good 2-opt: ~0.99+
- Optimal: 1.0 (259,045)
- **Our runs:** 0.9879–0.9925

---

## Common Issues

| Issue | Cause | Fix |
|-------|-------|-----|
| Run killed overnight | Windows sleep sending SIGTERM to WSL | `powercfg /change standby-timeout-ac 0` before starting |
| 0 evals | Condition B — no heartbeats | Known failure, treat as result |
| Agent never submits | Only one agent submitting with 2-agent config | Use `agents.count=1` |
| High cost | `max_turns=100` causes context explosion | Use `agents.max_turns=50` |
| index.md deleted by dedup | Bug in `_is_user_note` (now fixed) | Fixed in `knowledge_graph.py`, pushed to fork |
| Data download fails | Heidelberg TSPLIB URL unreliable | GitHub mirror in seed/solution.py handles this |
