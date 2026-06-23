# Agent Briefing — Alpha Z Technical Assessment

You are running experiments for a technical assessment on **CORAL** (arXiv 2604.01658), a framework for autonomous multi-agent LLM evolution on open-ended optimization problems.

## What CORAL Does

CORAL replaces fixed evolutionary search heuristics with long-running autonomous agents that:
1. **Retrieve** — autonomously decide what prior attempts/notes/skills to inspect
2. **Propose** — plan, implement, and test solutions independently
3. **Evaluate** — call `coral eval -m "description"` to submit and get scored
4. **Update** — write notes and skills to shared persistent memory for other agents

Agents live in isolated git worktrees, share state via `.coral/public/` (symlinked as `.claude/`), and are kept on track by **heartbeat actions** (reflect every eval, consolidate every 10, pivot after 5 plateau evals).

## Repository Layout

```
examples/
  circle_packing/         # Task 1 — already set up
    task.yaml             # default (opencode + docker)
    task_claude.yaml      # modified for claude_code + local session
    seed/initial_program.py
    grader/
  tsp/                    # Task 2 — already set up
    task.yaml             # TSP Berlin52 (currently targets opencode — needs editing for local runs)
    seed/solution.py      # nearest-neighbour baseline
    grader/               # validates tour, scores as 7542/tour_length
results/                  # created at runtime, one subdir per run
```

## Assessment Tasks

### Task 1 — Replicate circle_packing result
- **Goal:** Run CORAL on `examples/circle_packing/task_claude.yaml` and compare against paper.
- **Config ready:** `task_claude.yaml` uses `runtime: claude_code`, `session: local`, `model: claude-haiku-4-5-20251001`, `max_turns: 30`, 2 agents.
- **Paper result:** CORAL (1 agent, Opus 4.6) scored 2.6360 sum_radii (≈1.0 normalized) in 11 evals. Best known = 2.635977.
- **Run:** `uv run coral start -c examples/circle_packing/task_claude.yaml`
- **Record:** final score (`sum_radii / 2.635977`) and number of evals.

### Task 2 — TSP Berlin52
- **Goal:** Run CORAL on `examples/tsp/task.yaml` (needs runtime/session adjustment for local use).
- **Problem:** Find shortest Hamiltonian tour through 52 cities. Optimal = 7542. Score = `7542 / tour_length`.
- **Baseline seed:** nearest-neighbour heuristic in `seed/solution.py` (scores ~0.84).
- **To run locally:** either edit `task.yaml` or pass overrides:
  ```
  uv run coral start -c examples/tsp/task.yaml agents.runtime=claude_code agents.model=claude-haiku-4-5-20251001 run.session=local agents.count=1
  ```
- **Record:** best tour length, score, number of evals.

### Task 3 — Ablation Study on TSP
Run 3 conditions on the TSP task, 3 runs each. Report mean ± std of final score.

| Condition | What to change | How |
|---|---|---|
| **Full CORAL** | All mechanisms enabled | Default config |
| **Condition A** | Disable notes/skills (no shared knowledge) | Pass `agents.heartbeat=[]` AND clear `.coral/public/notes` + `.coral/public/skills` between attempts, or instruct the agent not to write notes/skills |
| **Condition B** | Disable all heartbeat actions | Pass `agents.heartbeat=[]` in config or via dotlist override |

To disable heartbeats via config override:
```bash
uv run coral start -c examples/tsp/task.yaml ... agents.heartbeat=[]
```

To disable knowledge (notes + skills) — the cleanest way is to instruct the agent in CORAL.md not to write notes or read from them. Alternatively, set an empty notes/skills directory and restrict agent write access. A pragmatic hack: use a CORAL.md tip that says "Do NOT write to notes/ or skills/".

### Task 4 — Improve Knowledge Management
**Problem identified from paper:** CORAL accumulates notes/skills indefinitely with no deduplication, contradiction resolution, or relevance ranking. In long runs this causes noise and retrieval degradation.

**Proposed fix (to be designed after Tasks 2–3):** Likely candidates:
- A `consolidate` heartbeat that LLM-summarizes + deduplicates notes
- A scoring/tagging mechanism for skills (hit count, improvement correlation)
- A "librarian" agent that prunes stale/contradictory entries

Use evidence from your Task 2–3 runs (how notes actually accumulate, what's redundant) to pick the most motivated fix, then implement it in `coral/hub/` or as a new heartbeat action.

### Task 5 — Product Plan
Write a plan for an LLM-driven autonomous optimization product after completing Tasks 1–4. Incorporate lessons from the runs.

---

## Running on Windows (Important)

This is running on **Windows 10 with PowerShell**. Several commands are broken:

| Broken command | Reason | Workaround |
|---|---|---|
| `coral stop --all` | `os.kill(pid, 0)` raises WinError 87 | Kill PIDs directly: `Stop-Process -Id <pid> -Force` |
| `coral status` | Same `os.kill` issue | Read `.coral/public/attempts/` manually |
| `coral log` | Same issue + needs `--task` flag | Read attempt JSONs directly |

**Start a run and note the PIDs printed at startup** — you'll need them to stop agents:
```powershell
Stop-Process -Id <agent1_pid>, <agent2_pid>, <grader_pid> -Force -ErrorAction SilentlyContinue
```

**Check scores directly:**
```powershell
ls results\<task-slug>\<timestamp>\.coral\public\attempts\
cat results\<task-slug>\<timestamp>\.coral\public\attempts\<hash>.json
```

---

## Key Config Knobs

| What | Dotlist override |
|---|---|
| Number of agents | `agents.count=2` |
| Model | `agents.model=claude-haiku-4-5-20251001` |
| Session mode | `run.session=local` |
| Runtime | `agents.runtime=claude_code` |
| Disable heartbeats | `agents.heartbeat=[]` |
| Max turns per session | `agents.max_turns=30` |
| Verbose output | `run.verbose=true` |

---

## Paper Key Numbers (for comparison)

| Task | Method | Final Score | #Evals | Improvement Rate |
|---|---|---|---|---|
| Circle Packing | CORAL 1-agent (Opus 4.6) | 2.6360 (≈1.0) | 11 | 100% |
| Circle Packing | OpenEvolve (Opus 4.6) | 2.6293 | 100 | 7.0% |
| Kernel Eng. | CORAL 4-agent (no notes) | 1601 cycles | — | — |
| Kernel Eng. | CORAL 4-agent (w/ notes) | 1350 cycles | 56 | 43% |

For TSP Berlin52 there are no direct paper numbers — this is a task you're introducing. Baselines to beat:
- Nearest-neighbour: ~0.84
- Good 2-opt: ~0.95+
- Optimal: 1.0 (7542)

---

## What's Already Built

- `examples/circle_packing/task_claude.yaml` — ready to run
- `examples/tsp/` — complete: task.yaml, seed/solution.py (nearest-neighbour), grader (validates tour, scores correctly)
- TSP grader has Berlin52 city coordinates hardcoded; validates permutation; computes Euclidean tour length

## What Still Needs Doing

- [ ] Run Task 1 and fill in results table in `assignment/README.md`
- [ ] Create a local-friendly TSP config (or use dotlist overrides)
- [x] Run Task 2 and record results
- [ ] Run Task 3 ablation (3 conditions × 3 runs)
- [ ] Design and implement Task 4 knowledge management improvement
- [ ] Write Task 5 product plan

---

## Progress Update (2026-06-23)

### Environment
- Running in **WSL (Ubuntu)** on Windows, not PowerShell. Ignore the Windows notes above.
- Agent runtime: **OpenCode** (`/usr/bin/opencode` — Linux binary)
- Model: `openrouter/deepseek/deepseek-v4-flash` via OpenRouter
- No LiteLLM gateway — OpenCode uses its built-in OpenRouter provider directly
- `opencode.json` in seed dirs contains only permissions (no custom provider block)

### Task 2 — Berlin52 COMPLETE
- Best score: **0.9997** (tour 7544.37, optimal 7542)
- Approach: Best-NN from all starts + 2-opt + 500x ILS double-bridge perturbations
- Hit on **attempt #1** — problem is too easy, agents converge immediately

### Task 3 — Ablation on pr1002 (IN PROGRESS)
Berlin52 was retired for the ablation — too easy, all agents converge to 0.9997 with no variance. Using **pr1002** instead (1002 cities, optimal 259,045, baseline ~0.989).

New task created: `examples/tsp_pr1002/`
- Score = `259045 / tour_length` (nint distances)
- Data downloaded automatically from TSPLIB on first run
- Seed baseline: nearest-neighbour (~0.9897)

#### Ablation commands
```bash
# Full CORAL (baseline)
uv run coral start -c examples/tsp_pr1002/task.yaml agents.count=2

# Condition A — no notes/skills
uv run coral start -c examples/tsp_pr1002/task.yaml agents.count=2 sharing.notes=false sharing.skills=false

# Condition B — no heartbeats
uv run coral start -c examples/tsp_pr1002/task.yaml agents.count=2 agents.heartbeat=[]
```

#### Runs completed so far

| Condition | Timestamp | Evals | Best Score | Notes |
|-----------|-----------|-------|------------|-------|
| Full CORAL | 2026-06-23_012657 | 42 | 0.9879 | Valid |
| Condition A (no notes/skills) | 2026-06-23_095931 | 27 | 0.9915 | Valid |
| Condition B (no heartbeats) | 2026-06-23_100004 | 0 | FAILED | Agent never submitted eval |

Still needed: 2 more Full CORAL, 2 more Condition A, 3 Condition B.

#### Recommended setup for remaining runs
Use **3 terminals with 3 separate OpenRouter API keys**, each with a $5 credit limit:
```bash
# Terminal 1
export OPENROUTER_API_KEY=key_baseline
uv run coral start -c examples/tsp_pr1002/task.yaml agents.count=2

# Terminal 2
export OPENROUTER_API_KEY=key_condition_a
uv run coral start -c examples/tsp_pr1002/task.yaml agents.count=2 sharing.notes=false sharing.skills=false

# Terminal 3
export OPENROUTER_API_KEY=key_condition_b
uv run coral start -c examples/tsp_pr1002/task.yaml agents.count=2 agents.heartbeat=[]
```
Keys auto-stop at $5. Repeat 3 times total per condition.

#### Identifying which condition a run was
```bash
cat ~/CORAL/results/travelling-salesman-problem-pr1002/<timestamp>/.coral/config.yaml | grep -A5 "sharing\|heartbeat"
```

### Task 4 — Proposed Modification
- pr1002 is the right task (baseline ~0.989, enough headroom)
- Modification TBD — decide after Task 3 results are in
- Must report mean ± std across 3 runs vs full CORAL baseline

### Common Issues
- **0 evals in a run**: Agent was still exploring when budget ran out — give more budget
- **`coral stop` stops all runs**: Be careful with simultaneous experiments
- **OpenCode Windows binary**: Always verify `which opencode` = `/usr/bin/opencode`
- **`examples/` missing after fresh clone**: `cp -r /mnt/c/Users/Luqman/Desktop/projects/CORAL/examples ~/CORAL/`
