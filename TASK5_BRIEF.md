# Task 5 Brief — Product Plan: LLM-Driven Autonomous Optimization

## Your Job

Write a product plan for a commercial product built on the principles of CORAL. The plan should be grounded in what you know about CORAL's mechanisms, its empirical results, and lessons from running it. It does not need to be a replica of CORAL — it should be a product vision informed by it.

**Output:** Write the plan directly into `assignment/README.md` under the "Task 5 — Product Plan" section. Aim for 600–1000 words. Use headers, bullet points, and tables where appropriate.

---

## What the Assessment Asks For

From the Alpha Z technical assessment:
> Write a plan for an LLM-driven autonomous optimization tool. Incorporate lessons from the runs.

A product plan should cover:
- **Problem & opportunity** — what gap does this fill?
- **Product vision** — what does it look like as a product?
- **Target users** — who pays for this?
- **Core features** — what does it do?
- **Technical architecture** — how is it built?
- **Competitive differentiation** — why is this better than existing tools?
- **Risks & mitigations**
- **Roadmap** — what gets built first?

---

## CORAL Background

CORAL (arXiv:2604.01658) is a framework for autonomous multi-agent LLM evolution on open-ended optimization problems. It replaces fixed evolutionary search heuristics with long-running agents that decide for themselves what to explore, when to evaluate, and what knowledge to preserve.

### Three core mechanisms

**1. Shared Persistent Memory (file system)**
- `attempts/` — scored historical solutions agents can browse and build on
- `notes/` — markdown observations/learnings written and read by all agents
- `skills/` — reusable procedures and implementation patterns
- Agents interact indirectly through this shared memory — no direct messaging protocol

**2. Asynchronous Multi-Agent Organization**
- Each agent runs in an isolated git worktree
- Agents explore in parallel, sharing discoveries through the hub
- No predefined roles or communication structure — coordination is emergent

**3. Heartbeat-Based Interventions**
- `reflect` — fires after every eval, gives agent score feedback and prompts iteration
- `consolidate` — fires every 10 evals, prompts agents to synthesize and write notes
- `pivot` — fires after 5 plateau evals, pushes agents to try different approaches
- **Critical finding from our runs:** without heartbeats, agents lose focus entirely and stop submitting evaluations. The reflect action is what keeps agents on task.

### Paper results (key numbers)

| Task | Method | Score | Evals | Improvement Rate |
|------|--------|-------|-------|-----------------|
| Circle Packing | CORAL 1-agent (Opus 4.6) | 2.6360 (~1.0) | 11 | 100% |
| Circle Packing | OpenEvolve (Opus 4.6) | 2.6293 | 100 | 7.0% |
| Kernel Engineering | CORAL 4-agent | 1103 cycles | 596 | 9% |
| Kernel Engineering | CORAL 1-agent | 1350 cycles | 56 | 43% |
| Kernel Engineering | Best Known | 1363 cycles | — | — |

CORAL achieves **2.5× higher improvement rate** and **10× fewer evaluations** than fixed evolutionary search baselines across 11 tasks.

### Competitive landscape

| System | Paradigm | Key limitation |
|--------|----------|---------------|
| FunSearch (Google DeepMind) | Fixed evolutionary search | LLM has no agency — fixed parent selection + prompt construction |
| AlphaEvolve (Google DeepMind) | Fixed evolutionary search + MAP-Elites | No agent autonomy over retrieval/update; no persistent memory across steps |
| OpenEvolve | Fixed evolutionary search | Same fixed-pipeline limitations |
| CORAL | Autonomous multi-agent evolution | Agents control retrieve/propose/evaluate/update; shared persistent memory |

Key differentiator: in fixed evolutionary search, the LLM only acts in the PROPOSE step. CORAL agents control all four steps autonomously.

---

## Lessons from Our Experimental Runs

These are first-hand observations from running CORAL on TSP pr1002 (1002-city benchmark):

**1. Heartbeats are load-bearing**
Condition B (no heartbeats) produced 0 valid evaluations across multiple attempts. Agents without periodic reflection prompts either explore indefinitely without submitting, or go rogue — editing config files, stopping and restarting the run, trying to manage the framework itself. The reflect heartbeat is what anchors agents to the task loop.

**2. Shared knowledge (notes/skills) provides modest lift**
Condition A (no notes/skills) scored ~0.9915 vs Full CORAL ~0.9879 (only 1 run each so far — not statistically conclusive). On pr1002 the problem may be too structured for shared notes to matter much. The paper shows larger gains on less structured tasks (kernel engineering).

**3. Agents converge fast on well-defined problems**
Berlin52 (52 cities) converged to 0.9997 on attempt #1 — near-optimal in a single shot. pr1002 (1002 cities) shows more variance and room for iterative improvement. Problem difficulty/headroom determines whether CORAL's iterative loop adds value.

**4. Agent reliability is a real concern**
Without proper guardrails (heartbeats, clear instructions), agents go off-task quickly. One agent called `coral stop` on its own run. Another spent 30+ minutes diagnosing infrastructure issues instead of solving the TSP. A product built on this needs robust agent grounding.

**5. Multi-agent parallelism has overhead**
Running 2 agents doesn't give 2× speedup — they share a grader queue and can write conflicting notes. The benefit is exploration diversity, not raw throughput.

**6. Knowledge accumulation degrades over time**
Notes accumulate indefinitely with no deduplication or quality filtering. In long runs, redundant notes crowd out useful ones. This is the core knowledge management problem (Task 4).

---

## Product Ideas to Consider

You are free to define the product vision however you see fit. Some directions:

- **"CORAL as a Service"** — cloud platform where users upload a scoring function and get back optimized solutions, with no agent management overhead
- **"AutoOptimize"** — developer SDK that wraps any evaluator and runs autonomous multi-agent search, with built-in knowledge management and reliability guarantees
- **"OR Copilot"** — tool specifically for operations research teams to run competitive optimization across routing, scheduling, packing problems
- **Enterprise angle** — focus on cost/time savings vs hiring specialists or running manual evolutionary search

The plan should be opinionated. Pick one direction and make a clear case for it.

---

## Where to Write

Open `assignment/README.md` and fill in the **Task 5 — Product Plan** section (currently says "*(to be written after Tasks 1–4)*"). Replace it with your plan.
