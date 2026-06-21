# Alpha Z Technical Assessment — CORAL

## Overview

This README tracks progress on the Alpha Z technical assessment, which requires:
1. Running CORAL and replicating an existing task result
2. Applying CORAL to an Operations Research (OR) problem
3. Running an ablation study on the OR task
4. Improving CORAL's knowledge management mechanism
5. Writing a product plan for an LLM-driven autonomous optimization tool
6. Any additional relevant work

All experiments are run from this repository: [Human-Agent-Society/CORAL](https://github.com/Human-Agent-Society/CORAL)

---

## Task 1 — Replicate a CORAL Result

**Task:** Run CORAL on an existing example and compare results against the paper (arXiv 2604.01658).

**Chosen task:** `circle_packing` — pack N=26 circles into a unit square to maximise the sum of radii. Best known result is 2.635977 (AlphaEvolve). Score = `sum_radii / 2.635977`, where 1.0 means matching the best known result.

**Approach:**
- Modify `examples/circle_packing/task.yaml` to use `claude_code` runtime and `session: local` (the default config targets `opencode` + `docker`)
- Run with 1–2 agents using `claude-sonnet-4-6`
- Record final score and number of evaluations
- Compare against paper numbers

**Results:** *(to be filled in after the run)*

| Metric | Paper | Ours |
|--------|-------|------|
| Final Score (sum_radii / 2.635977) | — | — |
| #Evals | — | — |

---

## Task 2 — Apply CORAL to an OR Problem

**Task:** Build a complete CORAL task for a classic combinatorial optimisation problem.

**Chosen problem:** Travelling Salesman Problem (TSP) — Berlin52 benchmark (52 cities, known optimal ≈ 7542).

**Deliverables:**
- `examples/tsp/task.yaml` — task configuration
- `examples/tsp/seed/solution.py` — nearest-neighbour heuristic as baseline
- `examples/tsp/grader/` — validates tour (all 52 cities exactly once), computes Euclidean distance, scores as `7542 / tour_length`

**Results:** *(to be filled in after the run)*

---

## Task 3 — Ablation Study

**Task:** Isolate which CORAL mechanisms matter for the TSP task.

**Conditions (3 runs each, report mean ± std of Final Score):**
- **Full CORAL** — baseline with all mechanisms enabled
- **Condition A** — disable notes/skills (no shared knowledge between agents)
- **Condition B** — disable all heartbeat actions (no periodic reflection/pivot prompts)

**Results:** *(to be filled in after the run)*

---

## Task 4 — Improve CORAL's Knowledge Management

**Problem:** CORAL accumulates notes and skills indefinitely with no mechanism to discard duplicates, resolve contradictions, or surface the most relevant knowledge. In long runs this leads to noise, redundancy, and retrieval degradation.

**Proposed fix:** *(to be defined after Tasks 2–3 — we will use evidence from those runs to identify the concrete failure mode before designing the fix)*

---

## Task 5 — Product Plan

*(to be written after Tasks 1–4)*

---

## Setup

```bash
# Install dependencies
uv sync --extra dev

# Verify CORAL is working
uv run coral --help

# Run a task
uv run coral start -c examples/circle_packing/task.yaml
```

---

## Windows Notes & Known Bugs

Running CORAL on **Windows 10** with PowerShell. Several CLI commands are broken due to Unix-only signal handling.

### Broken commands on Windows

| Command | Error | Workaround |
|---|---|---|
| `coral stop --all` | `OSError: [WinError 87] The parameter is incorrect` in `os.kill(manager_pid, 0)` | Kill agent PIDs directly (see below) |
| `coral status` | Same `os.kill` error in `_collect_runs` | Check `.coral/public/attempts/` manually |
| `coral log` | `No results directory found` unless run from the CORAL root with `--task` flag | Always `cd` to the CORAL root first; `--task` flag also doesn't work (same `os.kill` issue) |

**Root cause:** `coral/cli/query.py:380` calls `os.kill(manager_pid, 0)` to check if the manager process is alive. On Windows, signal 0 raises `[WinError 87]` instead of working as a liveness probe.

### Stopping agents on Windows

Note the PIDs printed at startup, then kill them directly in PowerShell:

```powershell
# PIDs printed at startup, e.g.:
#   agent-1: PID 14576
#   agent-2: PID 18332
#   Grader daemon: PID 9936
Stop-Process -Id 14576, 18332, 9936 -Force -ErrorAction SilentlyContinue
```

### Checking scores without `coral log`

Read attempt JSONs directly from the run directory:

```powershell
# Latest run attempts
ls results\circle-packing\<timestamp>\.coral\public\attempts\
# Read a specific attempt
cat results\circle-packing\<timestamp>\.coral\public\attempts\<hash>.json
```

### Resuming after a stop

```bash
uv run coral resume
```

### Config used for Task 1

`examples/circle_packing/task_claude.yaml` — modified from the default to use:
- `runtime: claude_code` (default targets `opencode`)
- `session: local` (default targets `docker`)
- `model: claude-haiku-4-5-20251001`
- `max_turns: 30`
