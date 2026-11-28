# Octopus-inspired distributed cognition: does local work belong below the beat?

date: 2026-11-27  
status: first measurement in (A0, B0, C0 below: recorded beats only, no model run). B parked on its own numbers. A's and C's first live candidates are named. Nothing live has run.  
scope: public research. The being's control loop, IRP plugins, salience, and ARC-AGI-3 action spaces.  
related: [exploration criteria](README.md), [SAGE evidence rules](../AGENTS.md)  
provenance: dp asked Gemini, on the web, for a proposal after an octopus story came up. Gemini's text is kept unedited in the [appendix](#appendix-the-source-proposal-gemini-2026-11-27). A Claude Code seat (cbp) checked it against this repo and the cited sources and wrote the sections above the appendix.

## Assessment

An octopus has about two neurons in its arms for every one in its central brain, and only a thin bundle of fibres runs between them. The arms solve most of their own problems, and the brain sees summaries. The proposal applies that shape to SAGE: keep the expensive central model for decisions that need it, and let cheaper local loops absorb local friction.

Taken as a *question*, it's worth testing: how much of a being's central beat budget goes on problems a local loop could have settled, and does moving that work down cost anything the being needed? Taken as a *description* of SAGE, it's framing, not a finding. Some of the mappings are already true, one rests on a misreading of the code, and one would need a new kind of trust semantics. The experiments below are written so that each one can come back negative.

## What was checked

| Claim in the source | Checked against | Result |
|---|---|---|
| `IRPPlugin` in `sage/irp/base.py` | repo, main 318dfc499 | exists |
| `GridCartridgeIRP` | `sage/irp/plugins/grid_cartridge_irp.py`, TODO.md | exists (a memory-search wrapper, done 2026-04-01) |
| "15+ IRP plugins" | `sage/irp/plugins/` | 43 files; "15+" is an understatement |
| `sage-core`, `sage-rs` | repo | both are Rust crates |
| #574 `settle` | dp-web4/SAGE | merged PR: the being keeps its conclusions where every beat shows them |
| #585 skill capture | dp-web4/SAGE | merged PR: the being is told when it has just worked something out |
| #582 "preflight stalls" | dp-web4/SAGE | open. The seed fitter and the step-1 preflight disagree; hub-being was silent for 11 h, with 22 beats refused. "Stall" is fair. |
| ARC-AGI-3 local play scores 0.04–0.14 | README.md:217 | matches: the same frozen code draws 0.04–0.14 |
| Hou et al. 2026, arXiv:2603.10198 | arXiv abstract page | real: SoftGM, two-stage graph attention, CTDE, PyElastica, accepted at IROS 2026 |
| Sivitilli 2022; Nakajima 2013; Müller & Hoffmann 2017; Brooks 1986 | — | well-known papers; their figures are not re-checked here. The neuron and fibre counts are as the source quotes them. |
| `daseinpbc/SPL-FRAMEWORK`, `011235813/hierarchical-marl`, `TimeBreaker/MARL-resources-collection` | GitHub API | all three exist and match their descriptions (last pushes 2026-01, 2022-06, 2026-07) |

## Where the source's mapping needs correcting

- **IRP plugins already loop locally.** The source wants to "upgrade IRP plugins from passive wrappers into stateful local micro-loops". `IRPPlugin` already is one: `init_state` → `step` → `energy` → `halt`, where `halt` fires on an energy slope below `halt_eps` over `halt_K` steps or at `max_iterations`. The real gap is one level up: **does the being's own multi-step work go through such a loop at all, or does every retry cost a central beat?** Experiment A is aimed at that question.
- **The Hestia gate is a reflex, but on the outgoing path.** The source maps Hestia to sucker chemoreceptors that "reject invalid intents before central reasoning spends tokens". The gate fires *after* the central model has chosen an act, before the act runs. It saves the act, not the tokens that chose it. A real touch-before-commit reflex would sit on the incoming side: telling the being what is reachable before it chooses. That is closer to Experiment C than to Hestia.
- **SNARC "state vectors" across the bottleneck.** A frozen LLM reads text, not vectors. What could cross the bottleneck is salience-filtered text: what changed, what surprised, what conflicts. The test is whether the filter drops something the being needed, not whether it compresses.
- **Peers passing T3/V3 tensors directly to each other.** This is a trust claim, not a routing one. A plugin that hands trust to another plugin without a central record is exactly the kind of unrecorded act Web4 exists to prevent. Experiment B tests routing alone and leaves trust out.

## Experiments

### A. Local loops below the beat: peripheral absorption with escalation

- **Hypothesis.** On multi-step tasks where most failures are local (a test that fails and needs a small fix, a grid probe within one level), a local loop with a small budget and an escalation threshold uses fewer central beats per completed task, and completes no fewer tasks, than routing every failure to the central model.
- **Probe procedure.** Use a fixed task set where failures are mostly local, with the same frozen model, seeds and scaffold in both arms:
  - Arm 1 (local): failures are retried inside a local loop with a budget of 3–5 cheap steps, deterministic or tiny-model. The loop escalates when its budget runs out or its surprise/conflict score crosses a threshold.
  - Arm 2 (ablated): every failure goes to the central model.

  Draw each arm several times; one draw proves nothing inside a 0.04–0.14 noise band.
- **Measurement.** Per task: central beats, tokens, wall time, and completion. Also count **missed escalations**: failures the local loop settled wrongly or hid, which the central model would have caught. Score these by replaying each locally settled failure through the central model.
- **Criterion.** It is a finding if central beats per completed task fall and completion stays inside the noise band across draws. The analogy misleads here, and the experiment closes negative, if completion drops beyond the band, or if missed escalations exceed some agreed level (proposed: more than 1 in 20 locally settled failures). Setting that level is the operator's call.
- **Status.** A0 measured on recorded beats (below). The first live candidate is chosen, in Picks. Not run live.

### B. A nerve ring for plugin handoff: learned routing, no shared trust

- **Hypothesis.** When the central model is confident about which plugin comes next, a small learned readout over plugin telemetry and salience picks the same plugin. That would let those handoffs skip a central round-trip.
- **Probe procedure.** Run it offline first, on logged plugin sequences:
  - train a small readout (logistic or a two-layer MLP) to predict the next plugin;
  - compare it against the central model's actual choice, and against a frequency baseline (the most common successor);
  - only if it beats the baseline, run it live in shadow mode: it predicts and records, the central model still decides.
- **Measurement.** On the slice where the readout is confident: agreement with the central choice, the outcome when they disagree, and the baseline's agreement on the same slice.
- **Criterion.** It closes negative if, on the confident slice, the readout does no better than the frequency baseline, or if its disagreements turn out better than the central choice too rarely to matter. Passing it carries no trust semantics: plugins pass routing hints, never trust.
- **Status.** Parked (2026-11-27). The logs exist: 170,000 acts across two beings. The frequency baseline is confident on only ~5% of transitions; see B0 below.

### C. Scaffolding as morphology: prune the action space before the model sees it

- **Hypothesis.** A 4B local model scores better on ARC-AGI-3 if the environment wrapper removes invalid and redundant actions before showing the choices. A second arm adds a fading-memory trace of recent observations, so the model sees how the state changed, not just a static snapshot.
- **Probe procedure.** Same frozen model and competition-legal setup, with three arms: baseline; pruning; pruning plus the trace. Pruning may use only what the environment itself reports (legal moves, no-ops seen this level), never game-specific knowledge. Otherwise it becomes hand-coding the solution, and the score measures us, not the being.
- **Measurement.** Score per arm across repeated draws, plus a leak audit: for each pruned action, record why it was pruned, and check that none of the reasons encode a solution.
- **Criterion.** It is a finding only if pruning moves the score above the 0.04–0.14 band across draws and passes the leak audit. It closes negative if the gain sits inside the band, or if the audit finds that pruning used knowledge the environment did not report.
- **Status.** Drafted, not run.

## First measurement: what the recorded beats say (2026-11-27)

The operator's answer to the open questions was to pick what is reasonable and learn by doing. The cheapest reasonable first step runs no model and touches no live being: it reads the beats the beings have already recorded. The question it answers is: before building any local loop, how much central work goes on local friction, and of which kind?

**Data.** The mirrored daily heartbeat logs of two beings:
- sprout-being: Jetson, 85 days, 7,850 beats, 34,431 acts, 47,481 model steps. It runs `qwen3.8-distill:4b` now and ran the 2b in September. When it switched isn't checked, and the weekly trend spans both models.
- cbp-being: WSL, 76 days, 12,417 beats, 135,629 acts, 142,722 model steps, on `qwen3.8-distill:4b` at both ends of the period.

One model step re-reads the whole prompt, about 17,000 tokens on sprout. By beat time over steps, a step costs roughly 40 s on sprout and 15 s on cbp. Probe: [`beat_friction.py`](2026-11-27-octopus-distributed-cognition/beat_friction.py) `<heartbeats dir>`. Every number below is its output. The logs themselves are private and are not in this repo.

### A0. Where the local friction is

| | sprout | cbp |
|---|---|---|
| acts going back to a target whose act just failed (upper bound: includes a read that leads to the fix) | 9.7% | 15.5% |
| …of which follow a failed `memory_edit` | 2,023 | 16,541 |
| `memory_edit` failure rate | 73% | 60% |
| commonest failure | "that text is not in *file*" | same |
| next act after a failed edit: `memory_read` of the same file | 726 of 1,168 (62%) | 4,746 of 8,417 (56%) |
| edit text-not-found per 100 acts, last 4 weeks | 1.2 → 3.9 | 5.5 → 6.0 |

The largest single block of local friction is **edit, text not found, re-read the file, edit again**. The refusal already does part of an arm's job: it says the file is unchanged and names the closest matching lines (seen in refusals from 2026-11-20; when that wording landed isn't checked here). The being still reads the file next after 56–62% of failed edits, and the rate of text-not-found failures hasn't fallen across November. Better wording has stopped moving this class. Contrast: peer_ask sent to a conversation partner fell on cbp from 3.8 to 0.4 per 100 acts once its refusal named the right door, so wording does work for some classes. This one looks structural.

### B0. Is there a nerve-ring signal to learn?

A frequency table, trained on days before 2026-11-12 and tested on the days after, predicts the next act from the previous act and its outcome:

| | sprout | cbp |
|---|---|---|
| top-1, commonest act | 33.8% | 23.7% |
| top-1, previous act + outcome | 38.8% | 41.7% |
| transitions where the table is confident (≥ 0.8) | 4.8% | 5.0% |
| right on that confident slice | 87.9% | 88.3% |

The confident slice is about one transition in twenty. A readout that matched the central choice perfectly there would skip at most ~5% of handoffs, and each handoff it skipped is one of the cheapest, most routine steps. **B is parked on this:** the nerve ring has little to carry in a single being's tool loop. It reopens if someone proposes a readout with a reason to expect a confident slice well above 5%, or a setting with many more parallel arms (several plugins or machines acting at once), where the octopus analogy is stronger.

### C0. Wrong doors in the being's own action space

Before any ARC run, there is a cheaper case of "prune before the model sees it": acts the environment already knows are the wrong door.

| | sprout | cbp |
|---|---|---|
| `search` refused | 94% | 72% |
| …mostly because | it reads code checkouts, not the being's home | same |
| `peer_ask` to someone already in conversation with it | 608 | 1,294 |

The fact behind the commonest search refusal, "there is no code checkout here", is one the environment reports itself. Pruning on it passes C's leak audit trivially, because nothing about any task's answer is used.

## Picks (2026-11-27), revisable as results come in

1. **A, first live candidate: the arm does the read.** When `memory_edit`'s old text isn't found and the closest region can be identified, the refusal also carries the current text of that region, with line numbers and a few lines of context. Then the being's next step can be the corrected edit instead of a read. Nothing is applied automatically; the central model still writes every edit. No change to the model, posture or offered tools.
   - **Being:** all of them, because it is one gateway change. It is measured per being by rerunning `beat_friction.py` on beats before and after.
   - **Prediction:** `memory_read` right after a failed edit falls well below today's 56–62%, and model steps per recovered edit fall by about one. The share of failed edits later recovered stays the same.
   - **Missed escalation:** this becomes "an edit recovered through the shown region lands on the wrong lines". It is checked by sampling recovered edits. The 1-in-20 threshold is kept: above it, the change is reverted and A closes negative for this class.
   - **Second candidate:** #829's progress signal, which compares where a run stops with the last run of the same file. Failed runs account for 1,509 steps back on cbp and 472 on sprout.
2. **C, first candidate: don't offer the wrong door.** Offer `search` only when the being has a code checkout to search. Measure the refusals that remain, and whether the being reaches the same lines through `memory_read`/`recall` instead of giving up. The ARC arm stays drafted.
3. **Missed-escalation level: 1 in 20,** as above, for A. C has no escalation path to miss.
4. **B: parked** on B0.

None of these is built yet. Each lands as its own SAGE PR, reviewed like any other gateway change.

---

## Appendix: the source proposal (Gemini, 2026-11-27)

Kept as received; its headings are demoted two levels to nest here, and the text is otherwise unchanged. The corrections above take precedence where the two disagree.

### Exploration Proposal: Octopus-Inspired Distributed Cognition in SAGE

**Target Repository:** `dp-web4/SAGE`  
**Status:** Exploration Proposal / Architecture Note  
**Date:** November 27, 2026  

---

#### Executive Summary

An octopus-inspired architecture maps directly onto `dp-web4/SAGE` by treating the frozen central LLM as the optic lobes/supraesophageal brain and elevating **IRP (Iterative Refinement Protocol) plugins**, **SNARC salience gates**, and **Hestia governance boundaries** into semi-autonomous peripheral arm ganglia.

Because SAGE explicitly tests whether capability comes from persistent structure rather than weights, solving the "infinite degrees of freedom" problem of open-ended tool use and multi-beat reasoning mirrors how an octopus avoids choking its narrow central axonal bottleneck (~140k afferent / ~32k efferent fibers connecting ~350M peripheral neurons to ~170M central neurons).

---

#### 1. Architectural Mapping: Octopus Nervous System → SAGE / Web4

| Octopus Biological Mechanism | SAGE / Web4 Structural Counterpart | Proposed Exploration Shift |
| :--- | :--- | :--- |
| **Central Brain & Optic Lobes** (~170M neurons): Sets high-level goals, visual integration, and long-term learning. | **Frozen LLM Core + Consciousness Loop** (`WAKE`, `FOCUS`, `DREAM`) | Stop invoking the central LLM for low-level tool retries or syntax loops. Reserve central beats for goal arbitration, cross-beat `settle` (#574), and hypothesis generation. |
| **Axonal Bottleneck** (~172k fibers): Compresses raw sensory streams into low-dimensional summaries before central delivery. | **SNARC Salience & MRH** (Markov Relevancy Horizon) | Replace raw verbatim log dumps into the LLM context with SNARC-compressed state vectors; only escalate high-surprise/high-conflict anomalies across the bottleneck. |
| **Brachial Ganglia / Axial Nerve Cord** (~350M neurons): Local sensorimotor loops executing multi-step actions independently. | **IRP (Iterative Refinement Protocol) Plugins** (`sage/irp/`) | Upgrade IRP plugins from passive wrappers into stateful local micro-loops with local memory and retry policies (building on #585 skill capture) that resolve sub-tasks before reporting back. |
| **Interbrachial Commissure (Nerve Ring)**: Direct arm-to-arm cross-talk bypassing the central brain. | **Peer IRP Message-Passing / Fleet Federation** | Allow IRP plugins (and fleet nodes) to pass lightweight state/trust tensors (`T3/V3`) directly to adjacent plugins without a central LLM round-trip. |
| **Sucker Chemoreceptors & Mechanoreceptors**: Local "taste-by-touch" validation before committing energy. | **Hestia Governance & PolicyGate** | Treat Hestia preflight checks as peripheral reflexes: local boundary/ATP-ADP checks reject or reshape invalid action intents at the edge before central reasoning spends tokens. |
| **Morphological Computation**: Passive compliance of soft tissue constraining degrees of freedom. | **Rust/Python Execution Boundary & Deterministic Schemas** | Offload combinatorial constraints (parsing, file diffs, graph indexing, schema validation) to rigid Rust/Python scaffolding (`sage-core`, `sage-rs`) so the LLM operates in a reduced-dimensionality manifold. |

---

#### 2. Concrete Research Proposals for `dp-web4/SAGE`

##### Proposal A: "Brachial IRP" — Local Convergence Loops with Central Escalation
* **Problem in SAGE:** Currently, multi-step tool failures or environment exploration often require full consciousness-loop turns through the central LLM, burning ATP/ADP budget and context window on local friction (e.g., issue #582 preflight stalls or ARC-AGI-3 grid probing).
* **Octopus Mechanism:** **Ascending Recruitment & Local Reflexes** (Sivitilli et al., 2022). Individual suckers sense local stimuli and recruit neighboring suckers along the axial nerve cord, only alerting the central brain when a threshold of novelty or resistance is crossed.
* **Implementation Experiment:**
  1. Extend `IRPPlugin` (`sage/irp/base.py`) with a **local micro-budget** (e.g., 3–5 fast, deterministic or tiny-model sub-beats) and a local **SNARC residual score**.
  2. When an IRP plugin executes (such as `GridCartridgeIRP` or a code-test runner), let it iterate locally using cached convergence patterns (`#585`) until either local coherence is reached or `Conflict` / `Surprise` exceeds a threshold.
  3. **Falsifiable Metric (SAGE Proof Standard):** Compare token/ATP consumption and task completion on multi-step tool tasks with *Brachial Local Loops ON* vs. *Ablated (all beats routed to central LLM)*.

##### Proposal B: Inter-Plugin Nerve Ring via Graph Attention & `T3/V3` Routing
* **Problem in SAGE:** Selecting and chaining among 15+ IRP plugins relies heavily on central LLM prompt routing.
* **Octopus Mechanism:** **Interbrachial Nerve Ring & Graph Attention Control** (Hou et al., 2026). Arms coordinate directly via a ring network without central arbitration.
* **Implementation Experiment:**
  1. Model active IRP plugins as nodes in a lightweight graph connected by recent co-occurrence and `T3/V3` trust edges.
  2. Implement a small, trainable **readout/gating layer** (inspired by physical reservoir computing) over plugin telemetry and SNARC states to propose the next plugin handoff automatically when local confidence is high, escalating to the central LLM only on low confidence.

##### Proposal C: Scaffolding-as-Morphology (Constraint-Driven Exploration)
* **Problem in SAGE:** Small local models (e.g., Qwen/Gemma 4B–27B) struggle in high-dimensional action spaces like ARC-AGI-3 (scoring 0.04–0.14 in competition-legal local play).
* **Octopus Mechanism:** **Morphological Computation** (Nakajima et al., 2013; Müller & Hoffmann, 2017). The physical elasticity of the arm naturally filters out impossible trajectories, turning infinite degrees of freedom into manageable synergies.
* **Implementation Experiment:**
  1. Treat `sage-rs` / `sage-core` environment wrappers as "soft tissue" that dynamically prunes invalid or redundant state transitions before presenting affordances to the LLM.
  2. Use **fading-memory state traces** (reservoir dynamics) across recent observations so the frozen LLM receives trajectory differentials rather than static snapshots.

---

#### 3. Key Research Papers & Literature

1. **Sivitilli, D. M., Smith, J. R., & Gire, D. H. (2022).** *Lessons for Robotics From the Control Architecture of the Octopus.* **Frontiers in Robotics and AI**, 9:862391.  
   * *Relevance to SAGE:* Quantifies the exact neural compression ratio (350M peripheral vs. 170M central across ~172k axons) and formalizes **top-down vs. bottom-up hybrid action selection** and **ascending sucker recruitment**—a direct blueprint for SNARC escalation.
2. **Hou, L., Wu, Q., Qin, Z., Guo, Y., & Laschi, C. (2026).** *Octopus-inspired Distributed Control for Soft Robotic Arms: A Graph Neural Network–Based Attention Policy with Environmental Interaction.* **arXiv:2603.10198** (IROS 2026).  
   * *Relevance to SAGE:* Introduces **SoftGM**, modeling each arm segment as a cooperative agent using **two-stage graph attention message passing** and **Centralized Training, Decentralized Execution (CTDE)**. Directly applicable to coordinating SAGE's 15+ IRP plugins and 8-machine fleet seats.
3. **Nakajima, K., Hauser, H., Kang, R., Guglielmino, E., Caldwell, D. G., & Pfeifer, R. (2013).** *A soft body as a reservoir: case studies in a dynamic model of octopus-inspired soft robotic arm.* **Frontiers in Computational Neuroscience**, 7:91.  
   * *Relevance to SAGE:* Demonstrates how a fixed, non-trainable dynamical substrate ("frozen weights" / physical body) can perform nonlinear temporal processing and short-term memory when paired with a lightweight trained readout layer.
4. **Müller, V. C., & Hoffmann, M. (2017).** *What Is Morphological Computation? On How the Body Contributes to Cognition and Control.* **Artificial Life**, 23(1), 1–24.  
   * *Relevance to SAGE:* Provides strict taxonomy separating *morphology facilitating perception*, *morphology facilitating control*, and *true morphological computation*—aligning cleanly with SAGE's research philosophy of not overclaiming what scaffolding does versus model weights.
5. **Brooks, R. A. (1986).** *A robust layered control system for a mobile robot.* **IEEE Journal of Robotics and Automation**, 2(1), 14–23. (Subsumption Architecture).  
   * *Relevance to SAGE:* The foundational robotics architecture for layered reactive loops where higher deliberative layers subsume—rather than micromanage—fast peripheral behaviors.

---

#### 4. Related Public Repositories

* **`dp-web4/web4`**: Companion protocol repository defining the substrate primitives (`LCT`, `T3/V3` trust tensors, `MRH`, `ATP/ADP`, and Hestia governance) that act as the "biochemical and axonal signaling" layer around SAGE.
* **`daseinpbc/SPL-FRAMEWORK`**: *Subsumption Pattern Learning (SPL) Multi-Agent Framework*—an open-source LLM agent framework explicitly adapting Rodney Brooks' subsumption architecture and Ronald Arkin's reactive schemas to suppress expensive foundation model calls by routing rote/reactive patterns to lower layers.
* **`011235813/hierarchical-marl`**: Reference implementation for Hierarchical Cooperative Multi-Agent Reinforcement Learning with Skill Discovery (AAMAS), useful for benchmarking decentralized sub-agent skill reuse against SAGE's `#585` skill-capture mechanism.
* **`TimeBreaker/MARL-resources-collection`**: Curated index of Multi-Agent Reinforcement Learning frameworks (including `JaxMARL` and LLM-based multi-agent systems) for decentralized policy and graph-communication baselines.
