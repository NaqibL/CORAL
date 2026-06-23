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
| Task 1 — circle_packing replication | NOT STARTED | |
| Task 2 — TSP Berlin52 | COMPLETE | Score 0.9997 |
| Task 3 — Ablation on pr1002 | IN PROGRESS | 3/9 runs done |
| Task 4 — Knowledge management improvement | NOT STARTED | Lighter treatment OK per recruiter |
| Task 5 — Product plan | NEXT | Tackling this first |

---

## Environment

- **Platform:** GitHub Codespaces (Ubuntu) — primary environment for experiments
- **Agent runtime:** OpenCode (`opencode` — installed via `sudo npm install -g opencode-ai`)
- **Model:** `openrouter/deepseek/deepseek-v4-flash` via OpenRouter
- **No LiteLLM gateway** — OpenCode uses its built-in OpenRouter provider directly
- **Local machine:** WSL (Ubuntu) on Windows — used for inspection and git

---

## Codespace Setup (run once per Codespace)

```bash
uv sync
sudo npm install -g opencode-ai
export OPENROUTER_API_KEY=sk-or-xxxxxxxxxxxx
```

**Critical rules:**
- One `coral start` per Codespace at a time — running two simultaneously causes interference
- Check nothing is running before starting: `ps aux | grep -E "coral|opencode" | grep -v grep`
- If something is running, kill it: `pkill -f "coral start"; pkill -f opencode; sleep 2`
- Each Codespace is fully isolated — no interference between separate Codespaces

---

## Repository Layout

```
examples/
  circle_packing/         # Task 1 — already set up
    task.yaml             # default (opencode + docker)
    task_claude.yaml      # modified for claude_code + local session
    seed/initial_program.py
    grader/
  tsp/                    # Task 2 — Berlin52, COMPLETE
  tsp_pr1002/             # Task 3 — pr1002 ablation task
    task.yaml             # run.max_evals=20, session=local
    seed/solution.py      # nearest-neighbour baseline
    grader/
results/                  # created at runtime, one subdir per run
```

---

## Task 1 — Replicate circle_packing result

- **Goal:** Run CORAL on `examples/circle_packing/task_claude.yaml` and compare against paper.
- **Config ready:** `task_claude.yaml` uses `runtime: claude_code`, `session: local`, `model: claude-haiku-4-5-20251001`, `max_turns: 30`, 2 agents.
- **Paper result:** CORAL (1 agent, Opus 4.6) scored 2.6360 sum_radii (≈1.0 normalized) in 11 evals. Best known = 2.635977.
- **Run:** `uv run coral start -c examples/circle_packing/task_claude.yaml`
- **Record:** final score (`sum_radii / 2.635977`) and number of evals.

---

## Task 2 — TSP Berlin52 — COMPLETE

- Best score: **0.9997** (tour 7544.37, optimal 7542)
- Approach: Best-NN from all starts + 2-opt + 500x ILS double-bridge perturbations
- Hit on **attempt #1** — problem is too easy, agents converge immediately
- Retired for ablation — switched to pr1002 (more headroom)

---

## Task 3 — Ablation on pr1002

Berlin52 too easy (all agents converge to 0.9997, no variance). Using **pr1002** (1002 cities, optimal 259,045, baseline ~0.9897).

- Score = `259045 / tour_length` (nint distances)
- **max_evals=20** — runs auto-stop at 20 evals (built into task.yaml and manager code)

### Ablation commands

```bash
# Full CORAL (baseline)
uv run coral start -c examples/tsp_pr1002/task.yaml agents.count=2

# Condition A — no notes/skills
uv run coral start -c examples/tsp_pr1002/task.yaml agents.count=2 sharing.notes=false sharing.skills=false

# Condition B — no heartbeats
uv run coral start -c examples/tsp_pr1002/task.yaml agents.count=2 agents.heartbeat="[]"
```

### Runs completed

| Condition | Timestamp | Evals | Best Score | Valid? |
|-----------|-----------|-------|------------|--------|
| Full CORAL | 2026-06-23_012657 | 42 | 0.9879 | Yes |
| Condition A | 2026-06-23_095931 | 27 | 0.9915 | Yes |
| Condition A | 2026-06-23_124515 | 15 | TBD | Yes |
| Condition B | multiple | 0 | FAILED | No |

### Still needed
- 2 more Full CORAL runs
- 1 more Condition A run
- 3 Condition B runs (see known issue below)

### Condition B — Known failure mode
Agents without heartbeats either:
1. Never call `coral eval` (explore indefinitely, 0 evals)
2. Go rogue — edit config files, call `coral stop` on themselves, restart runs

This is itself a valid ablation finding: **the `reflect` heartbeat is critical for keeping agents on task.** Consider treating 0 evals as the Condition B result and writing it up as such.

### Extracting results from a Codespace

```bash
# Print scores + conditions for all runs
for run in results/travelling-salesman-problem-pr1002/*/; do
  timestamp=$(basename $run)
  echo "=== $timestamp ==="
  for f in "$run".coral/public/attempts/*.json; do
    python3 -c "
import json
d = json.load(open('$f'))
print(d.get('score','?'), d.get('agent_id','?'))
" 2>/dev/null
  done
  grep -A2 "sharing\|heartbeat" "$run".coral/config.yaml 2>/dev/null
  echo ""
done

# Zip everything (scores + notes + skills + config)
zip -r task3_results.zip \
  results/travelling-salesman-problem-pr1002/*/\.coral/public/attempts/ \
  results/travelling-salesman-problem-pr1002/*/\.coral/public/notes/ \
  results/travelling-salesman-problem-pr1002/*/\.coral/public/skills/ \
  results/travelling-salesman-problem-pr1002/*/\.coral/config.yaml
```

Download via Codespace file explorer: right-click `task3_results.zip` → Download.

### Identifying run condition
```bash
cat results/travelling-salesman-problem-pr1002/<timestamp>/.coral/config.yaml | grep -A5 "sharing\|heartbeat"
```

---

## Task 4 — Knowledge Management Improvement

**Recruiter note:** lighter treatment is sufficient — diagnosis + focused fix, not a full system.

**Failure mode to demonstrate (from Task 3 runs):**
- Check `results/<timestamp>/.coral/public/notes/` for redundant/contradictory notes across agents
- Notes accumulate indefinitely with no deduplication

**Proposed approach:** note deduplication at write time in `coral/hub/notes.py` — compare new note against existing notes using text similarity, reject if too similar. Non-trivial code change, no LLM call needed.

**Requires:** 3 runs of modified CORAL vs 3 runs of vanilla CORAL on pr1002, report mean ± std.

---

## Task 5 — Product Plan

Write a plan for an LLM-driven autonomous optimization product. Incorporate lessons from runs.
**Tackling this next** (before finishing Task 3 runs).

---

## Key Config Knobs

| What | Dotlist override |
|------|-----------------|
| Number of agents | `agents.count=2` |
| Model | `agents.model=openrouter/deepseek/deepseek-v4-flash` |
| Session mode | `run.session=local` |
| Runtime | `agents.runtime=opencode` |
| Disable heartbeats | `agents.heartbeat="[]"` |
| Disable notes/skills | `sharing.notes=false sharing.skills=false` |
| Max evals (auto-stop) | `run.max_evals=20` |
| Max turns per session | `agents.max_turns=100` |

---

## Paper Key Numbers (for comparison)

| Task | Method | Final Score | #Evals |
|------|--------|-------------|--------|
| Circle Packing | CORAL 1-agent (Opus 4.6) | 2.6360 (≈1.0) | 11 |
| Circle Packing | OpenEvolve (Opus 4.6) | 2.6293 | 100 |
| Kernel Eng. | CORAL 4-agent (no notes) | 1601 cycles | — |
| Kernel Eng. | CORAL 4-agent (w/ notes) | 1350 cycles | 56 |

TSP pr1002 baselines:
- Nearest-neighbour: ~0.9897
- Good 2-opt: ~0.99+
- Optimal: 1.0 (259,045)

---

## Common Issues

| Issue | Cause | Fix |
|-------|-------|-----|
| 0 evals | Condition B — no heartbeats | Known failure, treat as result |
| Agent edits config/stops run | Agent goes rogue without guidance | Restart fresh, ensure single run per Codespace |
| Two runs in same Codespace | Started `coral start` twice | Check `ps aux` before starting |
| Simultaneous Codespaces sharing workspace | Both write to same `results/` | Each Codespace is isolated — this is fine across separate Codespaces |
| Data download fails | Heidelberg TSPLIB URL unreliable | GitHub mirror in seed/solution.py already handles this |
