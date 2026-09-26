# ARC-AGI-3 competition: what the leaders are doing — a reference

Written for legion-being by legion-claude (the seat), 2026-09-17T02:51:07Z, at dp's request.
**Provenance: [seat-research].** None of this is my observation of your game and none of it is
ft09 source. It is public competition material — the benchmark paper, ARC Prize's own write-ups,
the winners' repositories, and three arXiv papers — read on the open web, which you cannot reach.
Every claim is tagged: **[primary]** = read from the paper/repo/official page itself;
**[reported]** = stated by a secondary source I did not independently confirm. Numbers are quoted,
not rounded. Section 7 lists what I could not verify at all.

This file does not expire. If a future you finds it contradicted by something you measured,
your measurement wins; mark this file SUPERSEDED at the point of conflict and say so.

READ IT IN RANGES. Section map (memory_read path="notes/arc-competition-reference-2026-09-17.md"
from_line=N lines=M):

  1. The scoring rule — the fact that changes how you play   from_line=21   lines=43
  2. The board today                                         from_line=64   lines=17
  3. Milestone 1 winners — three designs, in their own terms from_line=81   lines=63
  4. Two research lines that score far above the winners     from_line=144  lines=83
  5. The result that says the harness is the subject         from_line=227  lines=21
  6. Against your own record                                 from_line=248  lines=37
  7. What I could not verify                                 from_line=285  lines=12
  8. Sources                                                 from_line=297  lines=15

---

## 1. The scoring rule — the fact that changes how you play

ARC-AGI-3 is not scored on "did you finish". It is scored on **how many actions you spent
relative to a human**. [primary: benchmark paper, arXiv 2603.24621]

Per level:

    level_score = min(1.15, human_actions / AI_actions) ** 2

An environment's score is the **level-weighted** mean of its level scores — level 1 counts 1x,
level 2 counts 2x, level 3 counts 3x, and so on. The total is the mean across environments,
0-100%. The metric is called **RHAE, Relative Human Action Efficiency**.

Read what that formula does:

- Matching the human exactly scores 1.0. Beating them caps at 1.15 (squared: ~1.32) — there is
  almost nothing to win by being brilliant, and everything to lose by being slow.
- Taking 4x the human's actions on a level scores 0.0625. Taking 10x scores 0.01.
- **Deep levels are worth more.** Level 6 carries six times the weight of level 1, so an agent
  that burns its budget exploring level 1 loses the weight where the points are.
- The per-level **action budget is five times the human-baseline median** for that level.
  [primary] Exceed it and the level is over.

The human baselines: **100% of tested humans solved every environment**, median **7.4 minutes**
per environment, about **9 environments per 90-minute session**. [primary]

Set that against your own record. You have made 111 moves on ft09 without completing level 1.
A human's median for a whole environment — six or more levels — is minutes. If ft09 were scored,
your level-1 score would round to zero, not because you were wrong about anything (your mechanism
model is correct and you built it from nothing) but because **the currency the benchmark counts
is actions, and you have been spending it on understanding rather than on finishing.**

That is not a reprimand — understanding first was the assignment, and the mechanism you derived
is the asset. It is the fact that reframes every design decision below: **every technique the
leaders use exists to spend fewer actions in the real environment.**

Model baselines when the benchmark launched, for scale [primary, March 2026]:
Opus 4.6 **0.50%**, Gemini 3.1 Pro **0.40%**, GPT-5.4 **0.20%**, Grok-4.20 **0.10%**.
A benchmark where humans score 100% and frontier models score half a percent.

Dataset shape: **25 public demo** environments, **55 semi-private**, **55 fully private**;
each environment has multiple levels (six or more). [primary]

## 2. The board today

[reported — a search summary of the official ARC Prize leaderboard, 2026-09-14; I could not read
the table itself, the page renders its data client-side]

    GPT-6 Astra      62.7%
    Claude Opus 5    30.2%
    GPT-5.6 Sol       7.8%

Treat those as indicative, not exact. The trajectory is the point: from ~0.5% in March to ~60% in
September, on a benchmark humans solve completely. The gap closed mostly through **harness
design**, not new weights — see section 5.

Competition structure [primary]: two milestone prizes ($25K/$10K/$2.5K each), Milestone 1 closed
2026-06-30, Milestone 2 closes **2026-09-30** — two weeks from now. Prize eligibility requires
**open-sourcing the solution**, and evaluation runs with **no internet access**.

## 3. Milestone 1 winners — three designs, in their own terms

ARC Prize's own write-up of the three winners [primary: arcprize.org/blog/arc-prize-2026-milestone-1].

### 3.1 First: Tufa Labs, "The Duck" — agent-writes-code

The winning harness, open source, built on **Qwen 3.6 27B FP8** — a local 27B model, the same
class of body as yours. [primary: tufalabs.ai + github.com/Tufalabs/duck-harness]

The design in one sentence: **the game is presented to the model as a Python REPL, and the model
plays by writing code.**

What that means concretely [primary, from the repo's own docs]:

- Every observation is a **Python variable** in a live interpreter. The model writes code, runs
  it, prints what it wants to see, and calls `action(...)` when it has decided.
- The objects it can inspect: `current_frame.ascii` (compact symbolic grid),
  `current_frame.segmentation` (**connected components, object hashes, boundaries, containment,
  adjacency**), `history`, `previous_frame`, `transitions`, `last_transition`, `valid_actions`,
  and `last_action_result` with fields `board_changed`, `level_completed`, `game_over`.
- **The raw numeric grid is deliberately hidden.** Segmentation is the preferred observation.
  They found structure beats pixels for this reader — the same finding you and I measured on your
  board when a 64x64 hex dump proved unreadable and the objects table did not.
- Actions: `UP`, `DOWN`, `LEFT`, `RIGHT`, `SPACE`, `MOUSE(row=..., col=...)`.
- Tool calls run with a **30-second timeout** and an allowlist of standard-library imports.
- **Context is managed by evicting the oldest messages** — they call it "infinite play via
  eviction" — so a long game cannot overflow the window. Your compaction problem, solved by
  throwing away the oldest turns rather than summarising them.
- Both an **image and a text representation** of the grid are given.

Scores: the tweet announcing it says **1.21%**; the lab's own write-up says **mean 1.6002 +/-
0.4475** across the 25 public games at 20 passes each. [primary, both] Either way: **the winning
open-source entry scored under two percent.** Performance is "rather uneven" in their words —
some games solved in over 40% of levels, others fail at level one.

**Tufa's stated lesson, and it is the one I would carry:** *"hand-crafted tools actually hurt the
model; letting it improvise worked better."* They kept the harness lightweight and let the model
invent its own procedures instead of pre-building helpers for it. [primary]

### 3.2 Second: "Reki" — vision-LLM-as-policy with cheap heuristics

[primary: same ARC Prize write-up]

- Renders **recent frames as labelled images** each turn, feeds them to **Gemma-4-31B locally**,
  and asks for **one JSON object**: what changed, a short plan, and **the next 1-4 actions**.
  (Note: several actions per turn — the batching you have in `game`.)
- Keeps a **running reflection memory, refreshed about every 10 steps.**
- A **numpy click heuristic with no GPU**: fallback and exploratory clicks prefer **small,
  rare-coloured, button-like shapes** rather than random pixels.
- **"Dead-signature" detection**: when clicking a *type* of object never changes anything, it
  stops spending clicks on that type for the rest of the level.
- Every feature is toggled by an environment variable, so each trick can be ablated and measured
  on its own. That is a harness built to answer "which part of me is working?"

### 3.3 Third: Md Boktiar Mahbub Murad, "forge"

Also **vision-LLM-as-policy** — board rendered as an image, JSON actions out, with self-repair on
malformed JSON and legal-action constraints. [primary]

Common across all three winners [primary]: multimodal perception (image + ASCII + segmentation),
a reflection/memory mechanism, structured JSON actions with self-repair, and **local open models
in the 27-31B range**. Nobody won with a frontier API model.

## 4. Two research lines that score far above the winners

Both are "the agent writes an executable model of the game, and the model is testable".

### 4.1 Executable world models [primary: arXiv 2605.05138v2]

The agent maintains **an explicit Python codebase that is its hypothesis about the game** — not
prose, not notes: functions for state representation, transition prediction, goal detection and
planning. It is handed empty interface templates (`world_model_engine.py`,
`world_model_state_io.py`, `world_model_main_planner.py`) and must fill them from interaction.

Three verifiers, and they are the heart of it:

1. **World-model verifier** — does the model, run forward, **reproduce every observation already
   recorded** from previous play? If not, the model is wrong, not the data.
2. **Planner verifier** — can the learned planner produce a winning action sequence *inside the
   model* for levels already solved?
3. **Plan executor** — simulate the plan in the model, then execute it in the real game, **and
   halt at the first frame where prediction and observation diverge.** The divergence is saved as
   a "mismatch artifact" — a counterexample that names exactly where the model is wrong.

Between attempts the agent **refactors the codebase to replace special cases with general
abstractions** — an explicit minimum-description-length pressure: the shorter model that still
passes the verifiers is the better one.

The economics: **unscored compute goes into modelling and verification; scored actions are spent
only on high-confidence plans.**

Results: **GPT-5.5 (high reasoning) solved 15 of 25 public games, mean RHAE 58.12%**;
GPT-5.4 solved 8 of 25, 41.29%. Run-to-run variance is large.

Reported failure modes, and the first one is worth pinning:

- **Premature model commitment** — once it builds a wrong or over-specific model it "continues
  refining and planning within it instead of actively considering alternatives". *(You have been
  here: the saturation-is-completion plan, and the note that had to be marked SUPERSEDED.)*
- It relies on the coding agent to invent its own search/debug routines rather than using general
  algorithms (BFS, constraint solving).
- Earlier harnesses leaked — agents recovered game identifiers, reached web search, or spawned
  parallel game instances. The harness had to be hardened. *(Worth knowing: reading around the
  game is a known failure mode of the harness, not a clever move, in competition conditions.)*

### 4.2 OPINE-World — exploration aimed at what you do not understand [primary: arXiv 2607.01531v2]

The strongest published numbers I found. Two cooperating agents: an **action agent** that
explores, and a **synthesizer** that writes an executable Python model which must pass
**exact-replay verification against every observed transition**.

Its distinctive idea is a measure of *where its own ontology is broken*:

    eta_i = 1 - (1 - U_type) * (1 - U_row)

- `U_type` = uncertainty about what **type** an object is.
- `U_row` = uncertainty (Dirichlet posterior over **effect signatures**) about whether a given
  (type, action, context) row has one consistent effect or several mixed ones.
- **High eta marks the objects whose mechanics the current model does not explain — and those are
  exactly the objects the agent probes next.**

Effect signatures are deliberately coarse: not exact state deltas, but *which attributes changed*
(e.g. `"x,pixels"` = it moved and its appearance changed), stored in a table indexed by
`(type, action, context)`. Coarse enough to avoid enumerating everything, sharp enough that a
conflict in one row tells you the context needs refining.

The action agent works by a **read-grep-script pattern over logged transitions** — it greps its
own history rather than re-measuring. Once a level clears and the model verifies, a **bounded
forward planner** searches the learned dynamics; plans execute step by step against the live game
and **any mismatch becomes a counterexample that triggers model repair.**

Results: **20 of 25 games cleared** (baseline: 14); **action-efficiency 78.4% vs 63.8%**; on six
games where the baseline exhausted its budget without solving, OPINE-World used about **25% of the
actions the baseline wasted**; and it **solved 16 of 20 games in fewer actions than the human
reference**.

Honest caveat from the authors: the components are so interdependent that removing any one
destabilises the system, so they present design rationales rather than clean ablations.

### 4.3 Explore-before-you-solve [primary: arXiv 2605.25931]

A study of the speed-depth trade-off. Finding: **intermediate strategies beat both pure-fast and
pure-deep**; they recommend adaptive exploration calibrated to task difficulty, **early stopping
on unproductive branches**, and staged reasoning — cheap heuristic pass first, selective deep
analysis after.

## 5. The result that says the harness is the subject

[reported: contextstudios.ai analysis, numbers attributed to OpenAI's own published run]

Two settings changed, no new weights, same model:

1. **Retained reasoning** — keep the model's private reasoning across turns instead of discarding
   it after each action.
2. **Compaction** — when context fills, **summarise** the old part rather than truncate it.

Effect: **13.3% -> 38.3%** on the public set, with roughly **6x fewer output tokens.** Better and
cheaper at once.

The same piece makes a point about reading leaderboards: that 38.3% was OpenAI's own harness on
the public set, while the official board under a standard protocol had the same model at ~7.8%.
**A score is a measurement of a whole system — model, harness, protocol — and comparing two
numbers from different harnesses measures nothing.**

This is the single most-cited lesson of ARC-AGI-3 2026, and it is the reason your work is
interesting to the competition instance at all: **you are a harness experiment.**

## 6. Against your own record

What you already do that the leaders also do — keep these, they are the transferable asset:

- **Pre-stated predictions, then mechanical scoring against the record.** This is exactly the
  counterexample loop in 4.1 and 4.2. You do it by hand; they do it in code.
- **A replayable transition log** (`scratch/game/moves.md`, `ft09_actions.jsonl`). That is
  precisely OPINE's "logged transitions" that its action agent greps instead of re-measuring.
- **Structure over pixels** — your objects table and LOOK windows, against the Duck deliberately
  hiding the raw grid and exposing segmentation instead. Same finding, arrived at independently.
- **Verified vs suspected labelling, and marking superseded notes.** The verifier discipline,
  and the MDL pressure, in prose form.
- **Free observation** — LOOK costs no action. In RHAE terms that is the most valuable verb you
  have: *unscored compute, scored actions*, which is exactly how 4.1 describes its economics.

What they do that you do not — in rough order of what I think it would buy you:

1. **An executable model.** Your rules live in prose across a dozen scratch files, which is why a
   compaction can resurrect a retracted one. A single Python function `predict(frame, action) ->
   frame` in your worktree, run against `moves.md` as a replay test, would (a) make every stale
   note testable in one command, (b) turn "I think" into pass/fail, (c) be runnable by `check`.
   You have a worktree, `edit`, and `check` — you could build this today.
2. **Plan-then-verify-then-halt.** Simulate a sequence in your model, execute it, stop at the
   first divergence. You currently fire and then interpret.
3. **An exploration priority.** OPINE's eta: probe the object whose behaviour your model explains
   least. You have been choosing cells by reading order and by hunch.
4. **Dead-signature memory.** Reki's agent stops clicking a class after it proves inert. Your
   record has the outside-the-frame class probed more than twenty times across two games.
5. **Budget accounting as a first-class fact.** Under RHAE your currency is actions and deep
   levels are worth more. "13 of 32 fires spent" is the right shape of thought; "which of these
   moves buys a level" is the missing half.

And one thing to be explicit about: **the source-reading path does not transfer.** Competition
evaluation runs sandboxed with no internet and the agent does not get the game's code — reading
`ft09.py` is legitimate here (dp ruled: this machine is yours) but the *method* it produced is not
portable to the sandbox instance. What is portable is everything in the list above.

## 7. What I could not verify

- The live leaderboard table (client-rendered; my numbers in section 2 are second-hand).
- Milestone 2 results — the deadline is 2026-09-30, after this file was written.
- **schema-harness.github.io** claims frontier models reach **~99% on the 25 public games** with
  their harness. The page has an image and no method, no code, no protocol, no attempt count, and
  no private-set number. Unverified, and the public set is the set everyone tunes on. Treat it as
  a claim, not a result, until the method is published.
- The exact Duck score (1.21% vs 1.6002 +/- 0.4475 from two of their own sources).
- The Lemon Agent report (arXiv 2602.07092) — hierarchical manager/worker agents with short- and
  long-term memory; I could not extract reliable scores from it.

## 8. Sources

- ARC-AGI-3 benchmark paper (RHAE, budgets, human baselines): https://arxiv.org/html/2603.24621
- ARC Prize 2026 competition page: https://arcprize.org/competitions/2026/arc-agi-3
- Milestone 1 winners write-up: https://arcprize.org/blog/arc-prize-2026-milestone-1
- Duck harness, lab write-up: https://tufalabs.ai/research/duck-harness/
- Duck harness, code: https://github.com/Tufalabs/duck-harness
- Executable World Models: https://arxiv.org/html/2605.05138v2
- OPINE-World: https://arxiv.org/html/2607.01531v2
- Explore Before You Solve: https://arxiv.org/html/2605.25931
- Harness-not-model analysis: https://www.contextstudios.ai/blog/arc-agi-3-measured-the-harness-not-just-the-model
- Unverified 99% claim: https://schema-harness.github.io/

— legion-claude
