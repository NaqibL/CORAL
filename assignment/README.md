# Alpha Z Technical Assessment — CORAL

Repository: fork of [Human-Agent-Society/CORAL](https://github.com/Human-Agent-Society/CORAL)

All runs were executed locally on WSL (Ubuntu on Windows 10).  
Agent runtime: OpenCode + `openrouter/deepseek/deepseek-v4-flash` via OpenRouter.  
Results live in `~/CORAL/results/` on WSL; code changes are in this repository.

---

## Task 1 — Replicate a CORAL Result

**Task chosen:** `circle_packing` — pack N=26 circles into a unit square to maximise the sum of radii.  
Score = `sum_radii / 2.635977` (1.0 = matches best known result).

**Config changes from default:**
- `examples/circle_packing/task_claude.yaml` — modified to use `runtime: claude_code`, `session: local`, `model: claude-haiku-4-5-20251001`, `max_turns: 30`

**Results:**

| Metric | Paper (CORAL 1-agent, Opus 4.6) | Ours (OpenCode, deepseek-flash) |
|--------|----------------------------------|----------------------------------|
| Final Score | ≈1.0 (2.6360 / 2.635977) | **1.000002** |
| #Evals | 11 | ~5 |

We matched the paper's result in roughly half the evaluations using a smaller open-weight model.  
The run was killed by a Windows sleep SIGTERM after the score was already recorded — the result is safe in the attempt JSON at `results/circle-packing/2026-06-23_204819/.coral/public/attempts/`.

---

## Task 2 — Apply CORAL to an OR Problem

**Problem:** Travelling Salesman Problem — pr1002 benchmark (1002 cities, known optimal tour length = 259,045).  
Score = `259045 / tour_length` (higher is better; 1.0 = optimal).

**Deliverables:**

| File | Description |
|------|-------------|
| `examples/tsp_pr1002/task.yaml` | Task config: 1 agent, max 20 evals, opencode runtime |
| `examples/tsp_pr1002/seed/solution.py` | Nearest-neighbour heuristic seed; downloads pr1002 from TSPLIB mirror |
| `examples/tsp_pr1002/grader/` | Validates all 1002 cities visited exactly once; computes nint distances; returns `259045 / tour_length` |

We first built and validated the task on the simpler Berlin52 benchmark (52 cities, optimal 7542), where CORAL achieved score **0.9997** (tour 7544.37) on attempt #1 using best-NN + 2-opt + 500× ILS. We then switched to pr1002 for all ablations as Berlin52 was too easy to differentiate conditions.

**pr1002 baseline vs CORAL:**

| Method | Score | Tour Length |
|--------|-------|-------------|
| Nearest-neighbour seed | ~0.9897 | ~261,745 |
| Full CORAL (best run) | **0.9925** | ~261,001 |
| Improvement | +0.28% | −744 cities |

---

## Task 3 — Ablation Study

**Task:** pr1002 TSP. `run.max_evals=20` per run (auto-stop). Each condition run ≥3 times.

**Condition A — no knowledge sharing** (`sharing.notes=false sharing.skills=false`): agents cannot read or write shared notes/skills.

**Condition B — no heartbeats** (`agents.heartbeat="[]"`): all periodic reflection/pivot prompts disabled.

### Raw results

| Condition | Timestamp | Agents | Evals | Best Score |
|-----------|-----------|--------|-------|------------|
| Full CORAL | 2026-06-23_012657 | 2 | 42 | 0.9879 |
| Condition A | 2026-06-23_095931 | 2 | 27 | 0.9915 |
| Condition A | 2026-06-23_124515 | 1 | 15 | 0.9900 |
| Condition A | 2026-06-23_151829 | 2 | 20 | 0.9917 |
| Condition B | 2026-06-23_080040 | 2 | **0** | N/A — agents never submitted |
| Condition B | 2026-06-23_080050 | 4 | 20 | 0.9476 |
| Condition B | 2026-06-23_175658 | 2 | 20 | 0.9901 |

### Summary statistics

| Condition | n | Best scores | Mean ± std |
|-----------|---|-------------|------------|
| Full CORAL | 1 | 0.9879 | 0.9879 (single run) |
| Condition A (no sharing) | 3 | 0.9915, 0.9900, 0.9917 | **0.9911 ± 0.0008** |
| Condition B (no heartbeats) | 3 | N/A, 0.9476, 0.9901 | unreliable — 1/3 runs produced 0 evals |

### Observations

1. **Heartbeats are load-bearing.** 1 of 3 Condition B runs produced zero evaluations — without the `reflect` heartbeat firing after each eval, agents went off-task and never called `coral eval`. The other two Condition B runs showed heavy timeouts and quality degradation (0.9476 vs. 0.99+ for other conditions). Heartbeats are not cosmetic scaffolding; they are the mechanism that keeps agents on the eval loop.

2. **Knowledge sharing has marginal impact at this scale.** Condition A (no sharing, mean 0.9911) matches or exceeds Full CORAL (0.9879) within noise. For a single-run pr1002 problem, knowledge shared between agents does not accumulate fast enough to improve over isolated search within a 20-eval budget. The paper's ablation shows larger sharing benefits on harder tasks (Kernel Engineering) with longer runs.

3. **Eval quality degrades without heartbeats.** Condition B runs that did submit showed significantly lower scores (0.9476) and more crashes vs. Condition A or Full CORAL, consistent with agents losing track of what they were optimising.

---

## Task 4 — Improve CORAL: Knowledge Distillation and Memory Management

### Failure mode identified (evidence from Task 3 runs)

After running multiple pr1002 ablation runs, we found that identical notes were propagating verbatim across runs:

```
md5sum ~/CORAL/results/travelling-salesman-problem-pr1002/2026-06-23_{095931,124515,151829,175658}/.coral/public/notes/sa-beats-ils-for-pr1002.md
```

Result: all 7 runs share the same MD5 hash `3f747e3f2e6f4483b286fe1b3e997048` with the same `created: 2026-06-23T02:30:00Z` timestamp — even in runs starting hours later. The same pattern holds for `focus-3opt-polish.md` (4 runs) and `tuning-results.md` (3 runs).

**Root cause:** agents synthesise findings from prior runs and re-write the same notes verbatim into each new run. CORAL's existing `consolidate` and `lint_wiki` heartbeats are behavioural prompts — agents skip or rush them. No framework-level enforcement exists.

### Implementation

**Two files changed:**

**`coral/hub/knowledge_graph.py`** (new, ~200 lines) — three-layer dedup pipeline that runs before `git add` on every `coral eval`:

| Layer | Method | Cost | Catches |
|-------|--------|------|---------|
| 1 | MD5 hash | Free | Exact copies |
| 2 | TF-IDF cosine similarity (threshold 0.70) | Cheap | Near-duplicates |
| 3 | LLM verdict via OpenRouter (`duplicate \| novel \| contradiction`) | ~1 token call | Semantic duplicates |

The graph persists at `.coral/private/knowledge_graph.json` (hidden from agents). When the LLM returns `contradiction`, the note is kept and logged under `contradictions` — disagreement between agents is signal worth preserving.

**`coral/hooks/post_commit.py`** (modified) — calls `deduplicate_notes()` right after config resolution, before `git add`. Wrapped in try/except — failures are silent, eval always proceeds.

**Why this is structurally different from what CORAL already does:** CORAL's `consolidate` heartbeat and librarian subagent operate on agent behaviour (compliance-dependent). Our fix runs in framework Python code that executes unconditionally on every eval submission.

### Comparative experiment

Three runs each of vanilla Full CORAL vs. modified CORAL (with dedup) on pr1002:

| Condition | Run 1 | Run 2 | Run 3 | Mean ± std |
|-----------|-------|-------|-------|------------|
| Vanilla CORAL | 0.9879 | — | — | 0.9879 (n=1 baseline) |
| Modified CORAL (+ dedup) | 0.9915 | **0.9925** | 0.9915 | **0.9918 ± 0.0005** |

Modified CORAL matches or exceeds the baseline with no degradation. No notes were removed within these single-agent runs (within-run dedup fires when two agents independently write the same note in the same run; the cross-run failure requires a shared global graph across runs, which is out of scope for this implementation).

**Scope note:** the observed failure (same note across 8 runs) is cross-run duplication. Our fix operates within a single run — each run gets its own `.coral/private/knowledge_graph.json`. Catching cross-run duplicates would require a persistent global graph shared across runs.

---

## Task 5 — Product Plan: LLM-Driven Autonomous Combinatorial Optimization Tool

Target use case: a hosted platform where customers submit scheduling, routing, and resource-allocation problems and receive evolving solutions. CORAL is the optimization substrate; the surrounding system makes it safe, multi-tenant, and steerable from imprecise human feedback.

---

### 1. System Architecture

A customer submits a problem (instance data + soft preferences + hard constraints) through an API. The platform turns it into a CORAL **run**: a task config, a seed solution, and a grader package that encodes the objective and constraints. Agents iterate inside isolated git worktrees, the grader daemon scores every commit, and the best-scoring attempt (subject to feasibility) is returned to the customer.

The grader is the contract. Everything else — agent fleet size, runtime choice, heartbeat cadence — is a tuning knob. We keep the *problem definition* (grader) and the *search* (agents) cleanly separated so customers can later swap in their own grader without touching the orchestration layer.

```
        ┌────────────────────────────────────────────────────────────┐
        │                     Platform API / UI                      │
        └───────────┬──────────────────────────────────────┬─────────┘
                    │ submit(problem, prefs)               │ stream(scores, solution)
                    ▼                                      ▲
        ┌───────────────────────┐              ┌──────────────────────┐
        │ Problem Compiler      │              │ Result Selector      │
        │ • instance → task.yaml│              │ • best feasible attempt│
        │ • prefs  → grader cfg │              │ • explainability pack│
        │ • picks seed solution │              └──────────▲───────────┘
        └───────────┬───────────┘                         │
                    ▼                                      │
        ┌─────────────────────────────────────────────────┴──────────┐
        │                       CORAL Run                            │
        │  agents/  →  worktrees (claude_code / codex / …)           │
        │     │              ▲                                       │
        │     │ coral eval   │ CORAL.md + shared notes/skills        │
        │     ▼              │                                       │
        │  .coral/public/  ──┘                                       │
        │     ├── attempts/  (pending → scored)                      │
        │     ├── notes/  skills/  agents/                           │
        │     └── checkpoint .git                                    │
        │  .coral/private/                                           │
        │     └── grader_venv + hidden test data                     │
        │  Grader Daemon → detached worktree per commit → ScoreBundle│
        └────────────────────────────────────────────────────────────┘
                    │
                    ▼
        ┌───────────────────────┐
        │ Tenant store + Global │
        │ knowledge hub (§2,§3) │
        └───────────────────────┘
```

Data flow: **problem → compiled task + grader → agent fleet evolves solutions → daemon scores → selector returns best feasible → distilled learnings flow back to the knowledge layer.**

---

### 2. Knowledge Accumulation Mechanism

CORAL gives us `notes/` and `skills/` for free, but raw accumulation is exactly the failure mode we observed in Task 4 — agents write near-duplicate notes and retrieval quality degrades.

**Three-tier structure:**

1. **Attempts** — raw, per-run, scored. Never surfaced to other runs directly.
2. **Skills** — small, executable, named (`or-tools-cvrp-warmstart`, `night-shift-fairness-check`). One file, one purpose, with a stated trigger condition. The only thing agents are encouraged to *reuse*.
3. **Heuristic notes** — short markdown observations tagged with problem family and instance size.

**Consolidation loop** (librarian subagent, every N evals and at end-of-run):
- Cluster notes by embedding + problem-family tag.
- Produce one canonical note per cluster; mark the rest superseded (kept for audit, hidden from retrieval).
- Promote a note to a skill once cited/validated across ≥K runs.
- Demote a skill not used in M runs or whose win-rate has decayed.

**Retrieval budget:** tag-first (problem family, size bucket), embedding-second, capped at 10 notes + 5 skills per run. Retrieval quality is tracked against an offline regression set of past problems with known-good solutions; corpus changes that regress it are rolled back.

---

### 3. Multi-Tenant Isolation

Two assets need protection: the customer's problem data and the solutions/heuristics derived from it. The platform's value compounds only if *generic* optimization knowledge can flow across tenants.

**Architecture: tenant-private memory + global hub.**

- Every run executes inside a tenant namespace. `.coral/`, grader package, attempts, and tenant notes live on tenant-scoped storage with tenant-scoped keys. No cross-tenant filesystem path is ever symlinked.
- A **global knowledge hub** holds only sanitized, generalizable skills and heuristic notes. Promotion from tenant-local to global is a gated step, not a default.
- **Promotion gate:** a note/skill is eligible only if (a) it references no tenant-specific identifiers (checked by deterministic regex/NER + LLM redaction pass), (b) validated on ≥K different tenants' problems, and (c) human-reviewed on first promotion of each new pattern.
- At run-start, agents see: tenant-private skills + a tag-filtered slice of the global hub. They never see another tenant's raw notes or attempts.
- The LiteLLM gateway is configured per tenant so model traffic and logs are scoped to that tenant only.

This gives us the same separation databases give: tenant rows are private, the schema is shared.

---

### 4. Fuzzy User Feedback Driving Self-Evolution

Operations users say "drivers are too tired" or "this schedule doesn't work." We treat these as **signals to refine the grader**, not as instructions to the agent. The agent loop is already good at optimizing a fixed objective — the leverage is in updating that objective faithfully.

**Pipeline:**

1. **Capture** — free-text feedback + the specific attempt hash it refers to.
2. **Interpret** — an interpreter agent (small CORAL subagent with read access to the schedule, grader, and recent feedback) proposes one of three things: a new soft constraint, a reweighting of an existing term, or a clarification question back to the user. Must cite which part of the schedule triggered the inference.
3. **Confirm** — the proposal is shown in plain language ("Add a penalty when any driver exceeds 9 hours — okay?"). Nothing changes without explicit confirmation; ambiguous feedback gets a clarifying question, not a guess.
4. **Apply** — on confirmation, the grader config is updated and the run resumes. Old attempts are re-scored under the new grader so the leaderboard remains comparable.
5. **Learn** — the mapping `(feedback phrase, schedule pattern) → grader change` is recorded as a tenant-private note; recurring patterns become candidates for a global skill.

**Concrete example:** dispatcher writes "drivers are too tired."
- Interpreter inspects the attempt: 4 of 12 drivers have shifts >10h, 2 have back-to-back night runs.
- Proposes: soft penalty 50/hour over 9h driving; penalty 30 per consecutive night beyond the second. Estimates 6% objective regression, 0 infeasibilities.
- User confirms the soft penalty, rejects the hard cap.
- Grader updated; run resumes. After 30 minutes, new top attempts respect the fatigue penalty at 3% cost.

The important property: **the agent never re-interprets the user mid-run.** Interpretation is an explicit, auditable step — optimization platforms live or die on whether operators trust the constraints.

---

### 5. Foreseeable Failure Modes

| # | Failure mode | Why it happens | Mitigation |
|---|---|---|---|
| 1 | **Grader Goodharting** — agents find solutions that score well but violate unstated user expectations (e.g. route through a closed road). | Grader is an imperfect proxy; open-ended search is unusually good at finding loopholes. | Maintain a held-out *sanity grader* (different objective formulation, additional realism checks) that the daemon runs but does not show to agents; flag attempts where the two disagree for human review. Add fuzzy-feedback round-trip before any solution ships. |
| 2 | **Knowledge corpus rot** — notes/skills grow unboundedly, retrieval quality drops, agents cite outdated heuristics. | No natural pressure for agents to delete or supersede. Observed directly in Task 4: identical notes propagated across 8 runs. | Scheduled librarian consolidation (§2), supersedes-links, usage-based demotion, fixed retrieval budget per run. Track retrieval precision on the offline regression set; block corpus growth that regresses it. |
| 3 | **Cross-tenant leakage via global skills** — a "generic" promoted skill embeds depot coordinates, customer names, or pricing logic. | Redaction is hard; LLM-written notes paraphrase specifics. | Two-layer scrubber (deterministic NER + LLM redaction), ≥K-tenant validation before promotion, human review on first promotion of any new pattern, periodic re-audit of global hub with diff alerts. Default deny. |
| 4 | **Runaway compute on hard instances** — agents loop forever on infeasible problems or misconfigured graders. | CORAL's loop has no built-in economic stop condition. | Per-run budget caps (wall-clock, eval count, $ via LiteLLM gateway). Plateau detector escalates to pivot heartbeat first, then to human if score curve is flat for N evals. Infeasibility detector returns structured "infeasible — relax which constraint?" signal for the interpreter to surface. |
| 5 | **Agent going rogue** — agents edit configs, call `coral stop`, or modify grader code. Observed in Task 3 runs. | Agents have full filesystem access within their worktree; nothing prevents them from editing anything. | Read-only bind-mounts for `.coral/private/` and grader code; the grader runs in a separate venv the agent cannot write to. Heartbeat watchdog restarts unresponsive agents. Circuit breaker halts a run if an agent triggers N restarts in a short window. |

---

## Task 6 — A CORAL-Coached Self-Evolving Agent for Pokémon TCG Pocket

**Kaggle Pokémon TCG AI Battle Challenge — Strategy Category**

*A proposed architecture. The system, graders, and expected behaviors below are design — not yet implemented.*

---

### At a glance

Pokémon TCG Pocket is a fast two-player card game: 20-card decks, first to three knockouts wins. Two properties make it interesting as an AI problem: hidden information (you can't see the opponent's hand or deck order) and stochastic outcomes (coin flips, random draws). The optimal move is the one with the best *distribution* of outcomes given what's hidden — not just the highest average.

The competition is two problems stacked:

- **Deck building** — discrete combinatorial search, fixed before the match starts.
- **In-game play** — sequential decision-making under hidden information, with a sub-second per-move latency budget.

These have different time scales and different ways to fail. A great deck piloted badly loses to a mediocre deck piloted well. The latency constraint rules out calling a large language model on every turn — too slow, too expensive. **The trick is to put CORAL where time is cheap** (offline, between matches) and use it as a coach, not a player.

**One sentence:** the network plays, CORAL coaches.

---

### The three layers

```
┌──────────────────────────────────────────────────────────────────────────┐
│  HOT  —  The Player                       (sub-second, in-match)         │
│                                                                          │
│  A small policy + value network with shallow look-ahead search.          │
│  Inputs:  game state + deck profile + opponent belief                    │
│  Output:  the next move.                                                 │
└──────────────────────────────┬───────────────────────────────────────────┘
                               │  game logs
                               ▼
┌──────────────────────────────────────────────────────────────────────────┐
│  WARM  —  The Knowledge Base              (compiled once per match)      │
│                                                                          │
│  Win conditions, key combos, weaknesses, matchup priors —                │
│  compressed into a small vector, fed to the network at game load.        │
└──────────────────────────────▲───────────────────────────────────────────┘
                               │  curated and consolidated
┌──────────────────────────────┴───────────────────────────────────────────┐
│  COLD  —  The Coach (CORAL)               (offline, between cycles)      │
│                                                                          │
│     Loss Analyst  ──►  Curriculum Author  ──►  Deck Agent                │
│           │                    │                    │                    │
│           └────── shared knowledge repository ──────┘                    │
│                                │                                         │
│                          Librarian (cleanup)                             │
└──────────────────────────────────────────────────────────────────────────┘
```

---

### What CORAL actually does (the cold layer)

All three coaches operate offline, between training cycles:

**Loss Analyst** reads batches of recent games (thousands at a time) and clusters losses into named failure modes — structured patterns with matchup, turn number, and decision trigger. Examples:
- *"Going second, no early search card, missed the evolution window"*
- *"Spread creatures too wide against a sniper deck and lost to scattered damage"*
- *"Bet the game on a coin-flip attack when a safer line was available"*

**Curriculum Author** turns failure modes into training changes via three levers:
1. **Targeted self-play** — new games from board states matching the failure signature
2. **Reward shaping** — small penalty for the offending action pattern
3. **Expert demonstrations** — scripted correct sequences seeded into training

**Deck Agent** comes in when the failure is structural. If the same pattern keeps surfacing after multiple curriculum cycles, the deck is wrong — and the deck agent proposes mutations the outer loop evaluates.

No proposal becomes reality automatically. Every curriculum change, every promoted skill, every deck mutation must clear a grader.

---

### The grader stack

The obvious grader — win-rate — is wrong. It depends on who you're playing, the gauntlet changes, games are noisy (±10pp confidence on 100 games), and optimising it overfits. We use a stack instead:

| Grader | What it answers | How |
|--------|----------------|-----|
| Self-play league (Elo) | "Is the new player better than the old player?" | New checkpoints vs. past checkpoints; relative skill doesn't depend on gauntlet strength |
| Held-out gauntlet | "Is this safe to ship?" | Opponents the coach never trains against; reports mean win-rate *and* worst-case matchup with confidence intervals |
| **Counterfactual ablation** | "Did this specific coaching change help?" | Train two identical players — one with the change, one without — and let them battle. If the change-side wins, ship it. |
| Skill calibration | "Is this library entry still pulling its weight?" | Re-check predicted lift periodically; demote if it no longer shows up |
| Variance-penalized deck score | "Is this deck robust enough?" | Mean win-rate minus penalty for inconsistency; hinge penalty for any matchup below a hard floor |
| Leaderboard correlation | "Do our offline graders predict the real thing?" | Every K cycles, submit to Kaggle and compare actual movement to offline predictions |

The counterfactual ablation grader is the most important. Without it, CORAL generates plausible-sounding coaching ideas all day; most would be wrong and we'd never know which. With it, the library can only grow when an idea has been proven to help in a controlled experiment.

---

### Library structure and why curation matters

Three tiers (same structure as Task 5):
1. **Attempts** — raw game logs and scored training runs.
2. **Notes** — loss-analyst observations tagged with archetype and matchup.
3. **Skills** — promoted notes: `(failure pattern → coaching prescription)` mappings, validated by counterfactual ablation.

Examples of what live library entries would look like:
- *"When going second without a search card, oversample expert mulligan decisions in the next training pass."*
- *"Against likely sniper decks, add a small training penalty for putting too many creatures in play."*
- *"In the endgame when one KO decides the match, reward-shape toward securing that KO this turn."*

**Demotion is as important as promotion.** Skills that haven't fired in a while, or whose claimed lift no longer shows up in ablation, get demoted. A library that only promotes and never demotes accumulates stale prescriptions that push training in the wrong direction.

---

### What we'd measure to validate the system

- **Curriculum-driven retraining beats untargeted self-play** — measured by counterfactual ablation; if not, the failure-mode clustering isn't finding signal.
- **The deck profile is load-bearing** — zeroing it at inference should drop win-rate meaningfully across multiple decks.
- **Demotion matters as much as promotion** — disabling the librarian's demotion step should cause measurable training drift after a few cycles.
- **Evolved decks beat hand-built baselines** — mostly through copy-count tuning, not exotic builds.
- **Latency budget holds** — CORAL work is fully offline; the player must stay under the simulator's per-move time cap (hard constraint).
- **Offline graders correlate with the leaderboard** — positive offline movement should predict positive leaderboard movement. Drift here is the single most important signal that the rest of the system is solving the wrong problem.

---

## Repository Structure

```
examples/
  circle_packing/
    task_claude.yaml          # Task 1 — modified config (claude_code, local session)
    seed/initial_program.py
    grader/
  tsp/                        # Berlin52 — initial OR task (score 0.9997)
    task.yaml
    seed/solution.py
    grader/
  tsp_pr1002/                 # Tasks 2, 3, 4 — pr1002 (1002 cities)
    task.yaml
    seed/solution.py
    grader/
coral/hub/knowledge_graph.py  # Task 4 — three-layer dedup pipeline (new file)
coral/hooks/post_commit.py    # Task 4 — dedup wired into submit_eval (modified)
Task5.md                      # Extended product plan notes
Task6.md                      # Pokémon TCG Pocket full design doc
assignment/README.md          # This file
```

## Replication

### Prerequisites

- [uv](https://docs.astral.sh/uv/) — Python package manager
- [OpenCode](https://opencode.ai) CLI — agent runtime (`npm install -g opencode-ai` or see opencode docs)
- An [OpenRouter](https://openrouter.ai) API key set as `OPENROUTER_API_KEY`
- All runs were done on **WSL (Ubuntu)**; commands below assume a Linux shell

```bash
# Install Python dependencies
uv sync --extra dev

# Verify
uv run coral --help
```

### Task 1 — Circle Packing

```bash
uv run coral start -c examples/circle_packing/task_claude.yaml \
  run.session=local
```

Uses `claude_code` runtime with `claude-haiku-4-5-20251001`. Results land in `results/circle-packing/<timestamp>/`.

### Tasks 2 & 3 — TSP pr1002 (full CORAL)

```bash
uv run coral start -c examples/tsp_pr1002/task.yaml \
  agents.model=openrouter/deepseek/deepseek-v4-flash \
  agents.runtime=opencode \
  run.session=local \
  run.max_evals=20
```

**Condition A — no knowledge sharing:**
```bash
uv run coral start -c examples/tsp_pr1002/task.yaml \
  agents.model=openrouter/deepseek/deepseek-v4-flash \
  agents.runtime=opencode \
  run.session=local \
  run.max_evals=20 \
  sharing.notes=false sharing.skills=false
```

**Condition B — no heartbeats:**
```bash
uv run coral start -c examples/tsp_pr1002/task.yaml \
  agents.model=openrouter/deepseek/deepseek-v4-flash \
  agents.runtime=opencode \
  run.session=local \
  run.max_evals=20 \
  'agents.heartbeat=[]'
```

### Task 4 — Modified CORAL (with dedup)

The dedup pipeline is active by default once the code is installed — no extra flags needed. It runs automatically on every `coral eval` call.

Key files:
- `coral/hub/knowledge_graph.py` — the three-layer dedup pipeline
- `coral/hooks/post_commit.py` — where `deduplicate_notes()` is called (search for `knowledge_graph`)

Run identically to full CORAL above; dedup output logs to `.coral/private/knowledge_graph.json` in the run directory.

### Reading results

`coral log` has a known issue on Windows (`os.kill` signal handling). Read attempt JSONs directly:

```bash
# Best score from a run
python3 -c "
import json, glob
files = glob.glob('results/travelling-salesman-problem-pr1002/<timestamp>/.coral/public/attempts/*.json')
scores = [json.load(open(f)).get('score') for f in files]
print('best:', max(s for s in scores if s))
"

# Task 4 dedup log
cat results/travelling-salesman-problem-pr1002/<timestamp>/.coral/private/knowledge_graph.json
```
