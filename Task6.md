# A CORAL-Coached Self-Evolving Agent for Pokémon TCG Pocket

**Kaggle Pokémon TCG AI Battle Challenge — Strategy Category**

*A proposed approach. The architecture, graders, and expected behaviors below are design — not yet implemented or empirically evaluated. §7 lays out what we'd expect the system to discover; §8 lays out what we'd measure to know it's working.*

---

## At a glance — for readers new to the game

Pokémon TCG Pocket is a fast, two-player card game. Before a match, each player builds a **20-card deck**. During a match, you play creatures, attach energy to power their attacks, and try to knock out your opponent's creatures. **First to three knockouts wins.** Games are short — typically five to fifteen turns.

Two things make it interesting as an AI problem. First, **you can't see your opponent's hand or deck order** — like poker, you're playing under uncertainty. Second, **a lot of outcomes hinge on coin flips and random draws**, so the same move can win or lose depending on luck. A good player isn't the one who always picks the move with the highest average outcome; it's the one who picks the move with the best *distribution* of outcomes given what's hidden.

That's the game. Now the system.

---

## 1. Why this is hard

The competition is really two problems stacked on top of each other, and most submissions will lose by treating them as one.

**Problem 1 — Deck building.** Before the match, choose 20 cards from a large pool. This is a discrete combinatorial search. The decision is fixed once the match starts.

**Problem 2 — Playing the game.** During the match, make the right move every turn, under hidden information, with a tight time budget. The simulator expects your move back in well under a second — like a chess engine, not a chess grandmaster taking five minutes to think.

These problems have different time scales, different success criteria, and different ways to fail. A great deck piloted badly loses to a mediocre deck piloted well. A brilliant pilot on a structurally weak deck has a ceiling no amount of clever play can break. They're coupled — the value of a deck depends on how you play it — but trying to solve them jointly is a trap. The search space is too big, and when something gets worse you can't tell whether it was the deck or the pilot's fault.

The latency constraint is the other thing that rules out a lot of "obvious" approaches up front. **You cannot call a large language model on every turn.** It's too slow and too expensive. Whatever plays the game has to be small, fast, and pre-trained — the same shape as the engine in a chess bot.

So the question becomes: where does CORAL fit? CORAL is a system for autonomous agents that read, write, and improve over a shared knowledge base. That's a powerful primitive — but the primitive is too slow for real-time play. The trick is to **put CORAL where time is cheap** (offline, between matches) and use it as a **coach**, not a player. The player is a small trained network. CORAL studies its games, finds patterns in its losses, and decides how to make the next version better.

The whole pitch in one sentence: **the network plays, CORAL coaches.**

---

## 2. The three layers

The system splits into three layers, each running on its own time scale.

```
┌──────────────────────────────────────────────────────────────────────────┐
│  HOT  —  The Player                       (sub-second, in-match)         │
│                                                                          │
│  A small policy + value network with shallow look-ahead search.          │
│                                                                          │
│  Inputs:   game state                                                    │
│          + deck profile      (compact strategic identity for the deck)   │
│          + opponent belief   (running guess at what the opponent has)    │
│  Outputs:  the next move.                                                │
└──────────────────────────────┬───────────────────────────────────────────┘
                               │  game logs
                               ▼
┌──────────────────────────────────────────────────────────────────────────┐
│  WARM  —  The Knowledge Base              (compiled once per match)      │
│                                                                          │
│  Win conditions, key combos, weaknesses, matchup priors —                │
│  compressed into a small vector, fed to the network at game load.        │
│  Not consulted move-by-move; that would be too slow.                     │
└──────────────────────────────▲───────────────────────────────────────────┘
                               │  curated and consolidated
                               │
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

* **The Player (hot).** Trained network in the AlphaZero family — outputs a move distribution and a value estimate, with a small bounded look-ahead. Fast enough for the timer. The only piece that actually plays.
* **The Knowledge Base (warm).** Everything CORAL has learned about the deck and the meta — what it's *for*, where it falls apart, who it beats. Compiled into a small vector when the match starts and fed to the network as conditioning. How strategy reaches the player without slowing it down.
* **The Coach (cold).** Three CORAL agents and a librarian. The **Loss Analyst** finds patterns in losses. The **Curriculum Author** turns them into training changes. The **Deck Agent** mutates the decklist when the problem is structural.

---

## 3. The Player

The player is a compact neural network — policy head (which move?) plus value head (am I winning?) — with a light look-ahead search on top. Same template as a modern game-playing engine. Architecture details are mostly orthogonal to this report; what matters are two design choices.

**The deck profile as context.** One set of network weights serves many decks. The deck profile is a small vector that summarizes the deck's identity: what its win condition is, how fast it sets up, where it's fragile, what it's good and bad against. Computed once at the start of the match, held constant throughout. This is the channel through which all of CORAL's strategic understanding reaches the player — at game time the network just consumes it, no reasoning required.

**The opponent belief as context.** From the very first move the opponent makes, we can start guessing what deck they're playing. A small inference module maintains a running probability over likely opponent archetypes and feeds that to the network too. The network doesn't have to explicitly *think* "this is probably a water deck" — it just learns to behave differently when that probability is high.

Training is offline, with self-play and gradient updates. The network gets snapshots, and the snapshots are what we ship.

---

## 4. The Coach — what CORAL actually does

None of this is on the critical path of a match. All of it happens between training cycles.

**The Loss Analyst** reads batches of recent games (typically thousands at a time) and clusters losses into named **failure modes**. A failure mode is a structured pattern: which matchup, which turn the game went sideways, which decision triggered the slide. Examples:

* *"Going second, no early search card, missed the evolution window"* — costs an estimated few percentage points of win-rate.
* *"Spread our creatures too wide against a sniper deck and lost to scattered damage"* — recurring against a specific opponent archetype.
* *"Bet the game on a coin-flip attack when a safer line was available"* — appears across multiple matchups.

Each failure mode lands in the knowledge base with a tag, an estimated cost, and the game logs that exemplify it.

**The Curriculum Author** turns failure modes into training changes via three levers:

1. **Targeted self-play.** Spin up new games from board states matching the failure signature. The next training run sees more of them — practice on exactly the situations the player is currently losing.
2. **Reward shaping.** Add a small penalty for the offending action (e.g. extra creatures on the bench when the opponent likely plays a sniper deck). Gradient pressure, not a hard rule.
3. **Expert demonstrations.** When a good response is known, script a small batch of correct sequences and seed them into training. Imitate first, refine through self-play.

**The Deck Agent** comes in when the failure is structural, not pilot-level. If the same pattern keeps surfacing after multiple curriculum attempts, the deck is wrong — and the deck agent proposes mutations the outer loop evaluates.

The crucial point: **no proposal becomes reality automatically.** Every curriculum change, every promoted skill, every deck mutation has to clear a grader. The grader is the contract. CORAL writes proposals; the graders decide what actually ships.

---

## 5. The library — making knowledge compound (and not rot)

The knowledge base has the same three-tier structure CORAL uses everywhere:

1. **Attempts** — the raw record of every scored training run. Cheap to keep, never read by anything but the librarian.
2. **Notes** — observations the agents write down. Short, tagged with archetype and matchup.
3. **Skills** — promoted notes. Each one is a `(failure pattern → coaching prescription)` mapping, validated by data.

Examples of actual library entries — translated out of game jargon:

* *"When we go second and don't draw a way to find more Pokémon, oversample expert mulligan decisions in the next training pass."*
* *"Against opponents likely to play sniper decks, add a small training penalty for putting too many creatures in play."*
* *"In the endgame when one knockout decides the match, reward-shape toward securing that knockout this turn — not toward looking good two turns from now."*
* *"Avoid betting the game on a single coin flip when a safer line gives 40%+ win probability without one."*

These used to be the kind of rule a hand-coded bot would have buried in if-statements. In our system they live as named, ablation-tested coaching prescriptions, and they shape the network through training rather than override it at runtime.

**Why curation matters.** Left alone, a library like this rots. Agents write duplicate notes, contradictory notes, notes that were true two cycles ago but aren't anymore. Retrieval quality drops, the coach gets worse, training drifts. We prevent this with:

* **Consolidation.** A scheduled librarian pass clusters near-duplicate notes and supersedes the weaker ones.
* **Promotion gates.** A note becomes a skill only after its proposed training change passes a controlled experiment (§6).
* **Demotion.** Skills that haven't fired in a while, or whose claimed effect no longer shows up in experiments, get demoted back to notes (or removed). **Promotion without demotion is worse than no library at all** — stale prescriptions keep firing and push training in the wrong direction.

That last point is the one that surprises people. A library is only useful if it forgets.

---

## 6. How we measure progress — the grader stack

The whole system runs on graders, and **the obvious grader — "what's our win rate?" — is wrong.** Here's why:

* **It depends on who you're playing.** Beat a weak gauntlet, win-rate looks great. Beat a strong one, looks terrible. The number is a function of your opponents, not you.
* **The gauntlet changes.** Add a new opponent and the win-rate moves. Was it the player getting better, or the gauntlet getting easier? You can't tell.
* **Pokémon games are noisy.** Coin flips, mulligans, lucky draws — a 100-game gauntlet has a confidence interval of about ±10 percentage points. Most "improvements" you'd see are noise.
* **Optimizing it overfits.** Tune everything against a fixed gauntlet and you'll beat that gauntlet beautifully, then lose to the hidden opponents on the Kaggle leaderboard.

So we don't use one grader. We use a stack of them, each cheap, each answering a specific question.

| Grader                            | What it answers                                           | How it works                                                                                                                                                                                                                                      |
| --------------------------------- | --------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| **Self-play league (Elo)**        | "Is the new player better than the old player?"           | New checkpoints play against past checkpoints; we track relative skill (Elo, the same idea used in chess ratings). Going up means real improvement, regardless of how strong the gauntlet is.                                                     |
| **Held-out gauntlet**             | "Is this player safe to ship?"                            | A separate set of opponents the coach never trains against. Reports mean win-rate **and** worst-case matchup, both with confidence intervals. Catches overfitting and protects against decks with one terrible matchup.                           |
| **Counterfactual ablation**       | "Did this specific coaching change help?"                 | Train two identical players in parallel — one with the proposed change, one without. Play them head-to-head. If the change-side player wins meaningfully, ship the change. Otherwise revert. **This is the most important grader in the system.** |
| **Skill calibration**             | "Is this library entry still pulling its weight?"         | When a skill was promoted, we recorded how much it was supposed to help. Periodically re-check. If the predicted lift no longer shows up, demote.                                                                                                 |
| **Variance-penalized deck score** | "Is this deck robust enough to ship?"                     | Not just average win-rate. We subtract a penalty for being inconsistent across matchups, and apply a hinge penalty for any matchup below a hard floor (say 30%). A 70/70/70/30/30 deck loses to a steady 55% deck on the leaderboard.             |
| **Leaderboard correlation**       | "Do our offline graders actually predict the real thing?" | Every few cycles, submit to Kaggle and compare the actual leaderboard movement to what our offline graders predicted. If they're drifting apart, the offline graders themselves become CORAL's next thing to fix.                                 |

The single most important idea here is **counterfactual ablation**. Whenever the coach proposes a change — a new curriculum scenario, a reward tweak, a new training exemplar — we don't ask "is the new player better than before?" Too many things changed. We ask "did *this specific change* help?" by training two identical players, one with the change and one without, and letting them battle each other. Same starting point, same compute, same opponents — only the change differs. If the change-side wins, it ships. If not, it doesn't.

This is the grader that disciplines CORAL. Without it, CORAL would generate plausible-sounding coaching ideas all day, most of which would be wrong, and we'd never know which. With it, the library can only grow when an idea has actually been proven to help in a controlled experiment.

The leaderboard correlation gate is the meta-version of the same idea. Our offline graders are surrogates for the real grader (the leaderboard), and surrogates drift. So we periodically check that our internal measurements still predict external reality, and treat any drift as a bug to fix.

---

## 7. What we expect the agent to discover

This system is a proposal — we haven't built and run it yet, so the strategic behaviors below are hypotheses, not results. But they aren't arbitrary either. Each is the kind of pattern the loss analyst's clustering would surface from real game logs, and each maps to a curriculum prescription the author can already articulate. They're the discoveries the architecture is *designed to be able to make*, and listing them is the most concrete way to explain what the coach is for.

If the system works, the library should accumulate entries along these lines:

* **Prioritize early board presence over conserving resources.** Early-game greed (hold for the perfect turn) loses to opponents who establish first. We'd expect the agent to commit basics and energy aggressively in the opening, even at the cost of running thin later.
* **Avoid high-variance coin-flip lines when ahead.** Once win probability is favorable, betting the match on a 50/50 attack is dominated by the slower guaranteed line. We'd expect a library entry that suppresses coin-flip-dependent winning lines when a safer alternative exists.
* **Aggressively trade tempo when behind.** The symmetric case: down on knockouts, the agent should *increase* variance — take the coin flip, accept unfavorable trades, anything that fattens the losing distribution's tail. Mean expected outcome gets worse; win probability goes up.
* **Modify attachment priorities by inferred archetype.** When the opponent's first move suggests a fast aggressive deck, energy should go to the bench attacker (the one that will survive). Against a slow setup deck, energy goes to the active for early pressure. Same hand, different play, driven by the opponent-belief vector.
* **Concentrate or spread damage based on opponent removal.** Against decks with healing or repositioning, concentrate on one target. Against decks without, spread damage to set up multiple cheap knockouts. The right answer is conditional, not absolute — exactly the kind of distinction a fixed policy gets wrong.
* **Size the bench to the matchup.** Smaller benches against sniper decks; larger against decks that only hit the active. The bench is a defensive asset whose size should depend on what the opponent can punish.
* **Recognize forced lines and pre-position for them.** When the opponent's energy commitments make a specific attack inevitable next turn, set up the response *this* turn — retreat the high-value target, promote a sacrificial creature, take the knockout on a low-value piece.
* **Mulligan toward setup, not toward power.** Opening hands with a strong attacker but no way to find more Pokémon are weaker than they look. Consistency beats peak ceiling, especially going second.

These are the kinds of intuitions strong human players develop over thousands of games. Crucially, **we are not encoding any of them as rules.** We're claiming the loss-analyst → curriculum-author → ablation-gate pipeline is the right shape to surface them on its own from game logs. If the system is built and only the first two emerge, the design is partially validated. If none emerge, the coach is broken and we'd need to debug why the clustering isn't finding what's there.

This is the section we'd want to fill with empirical evidence once the system is running. For now it's the most honest version of the claim: *here is what the architecture is supposed to be able to learn*.

---

## 8. What success would look like

Until the system is built, system-level claims are predictions, not findings. Here's what we'd treat as success — and what we'd treat as falsifying.

* **Curriculum-driven retraining beats untargeted self-play.** Measured by the counterfactual ablation grader from §6: a curriculum-shaped training cycle should beat an equal-compute untargeted one head-to-head. If it doesn't, the failure-mode clustering isn't finding signal worth training on.
* **The deck profile is load-bearing.** Zeroing the deck-profile vector at inference should drop win-rate meaningfully across multiple decks. If it doesn't, the network is ignoring the conditioning and we're not actually getting deck-specific play.
* **Demotion matters as much as promotion.** Disabling the librarian's demotion step should cause measurable training drift after a few cycles. If it doesn't, either the library isn't accumulating stale entries (unlikely) or those entries aren't influencing training (worse — means promotion isn't doing anything either).
* **Evolved decks beat hand-built baselines.** Mostly through copy-count tuning, not exotic cards. If the deck agent only finds exotic builds, it's overfitting to the gauntlet rather than improving consistency.
* **The latency budget holds.** All CORAL work happens offline; the hot-path player must stay under the simulator's per-move time cap. This is a hard constraint, not a soft one — if the deployed player can't return moves in time it doesn't matter how good its decisions are.
* **Offline graders correlate with the leaderboard.** Every K cycles, submit and compare. Positive offline movement should correspond to positive leaderboard movement. Drift here is the single most important signal that the rest of the system is solving the wrong problem.

The intended pattern: **the player carries the weights, the coach carries the library, the library compounds across cycles — and the graders are what would keep all three honest if and when the system is running.**

---

## 9. What's next

* **A learned opponent model.** The current "what deck is the opponent playing" inference is a hand-built module. Training it end-to-end with the player is the obvious next bottleneck.
* **A rolling gauntlet.** Every so often, promote our own best evolved decks into the gauntlet and retire dominated ones. This keeps us from optimizing against a stale picture of the meta.
* **A smaller, faster coach.** Once we have enough validated `failure → prescription` mappings, distill them into a small model that proposes new ones without a full LLM call. Makes CORAL cycles cheaper.
* **Surviving expansions.** When new cards drop, most strategic principles still apply but some card-specific skills don't. Tracking which library entries depend on which cards lets us prune precisely on expansion day instead of starting over.

The throughline: under a real latency budget, the durable artifact isn't the player and isn't the deck — it's the **library of coaching prescriptions** that takes both from one version to the next, plus the **graders** that decide what's allowed into it. The network plays, CORAL coaches, the graders keep both honest. That's the system.
