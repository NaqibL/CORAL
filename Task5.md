# Task 5 — CORAL for an Enterprise Optimization Platform

Target use case: a hosted platform where customers submit scheduling, routing, and resource-allocation problems and receive evolving solutions. CORAL is the optimization substrate; the surrounding system makes it safe, multi-tenant, and steerable from imprecise human feedback.

---

## 1. System Architecture

A customer submits a problem (instance data + soft preferences + hard constraints) through an API. The platform turns it into a CORAL **run**: a task config, a seed solution, and a grader package that encodes the objective and constraints. Agents iterate inside isolated git worktrees, the grader daemon scores every commit, and the best-scoring attempt (subject to feasibility) is returned to the customer. The customer can leave the run open and stream improvements, or take a single snapshot.

The grader is the contract. Everything else — the agent fleet size, runtime choice, heartbeat cadence — is a tuning knob. We keep the *problem definition* (grader) and the *search* (agents) cleanly separated so that customers can later swap in their own grader without touching the orchestration layer.

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

## 2. Knowledge Accumulation Mechanism

CORAL gives us `notes/` and `skills/` for free, but raw accumulation is exactly the failure mode we want to avoid — agents will otherwise write twenty near-duplicate notes about the same heuristic, and retrieval quality degrades as the corpus grows.

**Structure.** We split persisted knowledge into three tiers:

1. **Attempts** — raw, per-run, scored. Cheap to keep; never surfaced to other runs directly.
2. **Skills** — small, executable, named (e.g. `or-tools-cvrp-warmstart`, `night-shift-fairness-check`). One file, one purpose, with a stated trigger condition. Skills are the only thing agents are encouraged to *reuse*.
3. **Heuristic notes** — short markdown observations ("for >500 stops, two-opt local search dominates Clarke-Wright by ~6%"). Tagged with problem family and instance size.

**Consolidation loop.** A scheduled `librarian` heartbeat action (we already ship a librarian subagent) runs every N evals and at end-of-run:

* Cluster notes by embedding + problem-family tag.
* For each cluster, ask the librarian to produce one canonical note and mark the rest superseded (kept on disk for audit, hidden from retrieval).
* Promote a note to a *skill* once it has been cited or validated across ≥K runs.
* Demote a skill that has not been used in M runs or whose win-rate against the baseline has decayed.

**Avoiding retrieval degradation.** Retrieval at run-start is tag-first (problem family, size bucket), embedding-second, and capped at a small budget (e.g. 10 notes, 5 skills) that fits comfortably in CORAL.md. We measure retrieval quality with an offline regression set — a fixed bundle of past problems whose known-good solutions we can replay — and gate corpus changes on it. Anything that lowers replay quality is rolled back.

---

## 3. Multi-Tenant Isolation

Two assets need protection: **the customer's problem data** (instance, history, preferences) and **the solutions and heuristics derived from it**, which often encode operational secrets. At the same time, the platform's value compounds only if *generic* optimization knowledge — "branch-and-cut beats LP rounding above density X" — can flow across tenants.

**Architecture: tenant-private memory + global hub.**

* Every run executes inside a tenant namespace. The `.coral/` directory, the grader package, attempts, and tenant notes live on tenant-scoped storage with tenant-scoped keys. No cross-tenant filesystem path is ever symlinked.
* A separate **global knowledge hub** holds only *sanitized, generalizable* skills and heuristic notes. Promotion from tenant-local to global is a gated step, not a default.
* Promotion gate: a note/skill is eligible only if (a) it references no tenant-specific identifiers (depots, SKUs, employee names — checked by a deterministic scrubber plus an LLM redaction pass), (b) it has been validated on ≥K *different* tenants' problems, and (c) a human reviewer approves the first time a given pattern is promoted.
* At run-start, agents see: tenant-private skills + a tag-filtered slice of the global hub. They never see another tenant's raw notes or attempts.
* The LiteLLM gateway is configured per tenant so model traffic, logs, and any third-party agent runtime (Codex, Cursor) sees only that tenant's data.

This gives us the same separation databases give us — tenant rows are private, the schema is shared.

---

## 4. Fuzzy User Feedback Driving Self-Evolution

Operations users do not file objective functions; they say "drivers are too tired" or "this schedule doesn't work." We treat these as **signals to refine the grader**, not as instructions to the agent. The agent loop is already good at optimizing a fixed objective — the leverage is in updating that objective faithfully.

**Pipeline.**

1. **Capture.** Free-text feedback + the specific attempt hash it refers to.
2. **Interpret.** An *interpreter agent* (a small CORAL subagent with read access to the schedule, the grader, and recent feedback) proposes one of three things: a new soft constraint, a reweighting of an existing term, or a clarification question back to the user. It must cite which part of the schedule triggered the inference.
3. **Confirm.** The proposal is shown back to the user in plain language ("Add a penalty when any driver exceeds 9 hours behind the wheel — okay?"). Nothing changes without an explicit yes; ambiguous feedback gets a clarifying question, not a guess.
4. **Apply.** On confirmation, the grader config is updated (a new term added or a weight changed) and the run resumes. Old attempts are re-scored under the new grader so the leaderboard remains comparable.
5. **Learn.** The mapping `(feedback phrase, schedule pattern) → grader change` is recorded as a tenant-private note; recurring patterns become candidates for a global skill (e.g. `fatigue-detector: when shift > 9h or consecutive nights ≥ 3, add penalty term`).

**Concrete example.** Dispatcher reviews Monday's routes and writes "drivers are too tired."

* Interpreter inspects the attempt: 4 of 12 drivers have shifts >10h, 2 have back-to-back night runs.
* Proposes: *soft constraint, penalty 50/hour over 9h driving; hard cap at 11h; penalty 30 per consecutive night shift beyond the second.* Estimates 6% objective regression, 0 infeasibilities on the current instance.
* User confirms the soft penalty, rejects the hard cap (says "11h is fine for special deliveries").
* Grader updated, run resumes. After 30 minutes the leaderboard shows new top attempts that respect the fatigue penalty at a 3% cost.
* The mapping is filed; next time any tenant says "tired" / "burned out" / "too many late shifts," the interpreter proposes the same template first.

The important property: **the agent never re-interprets the user mid-run.** Interpretation is an explicit, auditable step, because optimization platforms live or die on whether operators trust the constraints.

---

## 5. Foreseeable Failure Modes

| # | Failure mode                                                                                                                                                              | Why it happens                                                                                                            | Mitigation                                                                                                                                                                                                                                                                                                                                                                             |
| - | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------- | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| 1 | **Grader Goodharting** — agents find solutions that score well but violate unstated user expectations (e.g. minimize distance by routing through a closed road).          | Grader is an imperfect proxy. Open-ended search is unusually good at finding loopholes.                                   | Maintain a held-out *sanity grader* (different objective formulation, additional realism checks) that the daemon also runs but does not show to agents; flag attempts where the two disagree by more than a threshold for human review. Add fuzzy-feedback round-trip as a routine step before any solution ships.                                                                     |
| 2 | **Knowledge corpus rot** — notes/skills grow unboundedly, retrieval quality drops, agents start citing outdated heuristics.                                               | No natural pressure for agents to delete or supersede. Embedding retrieval degrades with corpus size and near-duplicates. | Scheduled librarian consolidation (§2), explicit supersedes-links, usage-based demotion, and a fixed retrieval budget per run. Track retrieval precision on the offline regression set; block corpus growth that regresses it.                                                                                                                                                         |
| 3 | **Cross-tenant leakage via global skills** — a "generic" promoted skill embeds depot coordinates, customer names, or pricing logic.                                       | Promotion looks safe in isolation but redaction is hard; LLM-written notes paraphrase specifics.                          | Two-layer scrubber (deterministic regex/NER + LLM redaction), require ≥K-tenant validation before promotion, human review on first promotion of any new pattern, and periodic re-audit of the global hub with diff alerts. Default deny — when in doubt, the skill stays tenant-private.                                                                                               |
| 4 | **Runaway compute on hard instances** — agents loop forever on a problem that is intrinsically infeasible or where the grader is misconfigured; the daemon backlog grows. | CORAL's loop has no built-in economic stop condition.                                                                     | Per-run budget caps (wall-clock, eval count, $ via the LiteLLM gateway). Plateau detector escalates to a pivot heartbeat first, then to a human if the score curve is flat for N evals. Infeasibility detector in the grader returns a structured "infeasible — relax which constraint?" signal that the interpreter agent can surface to the user instead of silently burning budget. |
