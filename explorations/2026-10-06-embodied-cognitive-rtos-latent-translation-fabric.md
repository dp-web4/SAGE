---
date: 2026-10-06
status: drafted — parent architecture exploration
proposed by: dp + GPT-5.6 Sol
parent_of:
  - explorations/2026-10-06-compiled-transducers-sensors-effectors.md
related:
  - forum/human/sensor_puzzle_effector_vae_proposal.md
  - sage/docs/vae_translation_analysis.md
  - sage/docs/SYSTEM_UNDERSTANDING.md
  - sage/docs/SAGE_SYSTEM_ARCHITECTURE.md
  - sage/docs/SENSOR_EFFECTOR_DESIGN.md
  - sage/core/sage_system.py
  - sage/gateway/heartbeat.py
  - sage/gateway/being_tool_loop.py
  - sage/gateway/tests/test_preempt_for_a_person.py
  - sage/docs/BEING_STACK_VISION.md
---

# Embodied Cognitive RTOS and Latent Translation Fabric

## Why this exploration exists

Several ideas that have recurred throughout SAGE now look less like separate design experiments and more like partial views of the same system:

- SAGE as a **cognition kernel** rather than a model;
- IRP as a common contract for specialized cognitive, sensory and action organs;
- VAE-style compression as a **translation layer** between heterogeneous representations;
- the old sensor → puzzle → effector bridge;
- memory as a temporal sensor;
- SNARC salience and ATP as attention/resource allocation;
- the newer awareness-loop work as an RTOS-like event scheduler with priority and preemption;
- effectors as governed, bounded action channels;
- compiled transducers as hardware-shaped implementations of expensive sensor/effector organs;
- persistent identity and memory around a replaceable model substrate.

The old documents were often concrete in ways that were useful at the time: a VAE, a 30×30×10 puzzle grid, a particular HRM H/L split. The architecture underneath them has aged better than those exact implementation choices.

This exploration deliberately zooms out.

The question is not:

> Should SAGE use a VAE?

or:

> Should all modalities be forced into one puzzle space?

The question is:

> **Can a persistent embodied being be built from specialized organs that retain modality-native representations, while a learned translation fabric, an RTOS-like cognitive scheduler, memory, trust and governed effectors make the whole system coherent?**

The answer matters most on small machines such as Sprout and CBP, where a giant end-to-end multimodal model cannot simply absorb every sensor and effector boundary internally.

---

## Architectural hypothesis

**Primary hypothesis:** a substantial fraction of the functional benefit attributed to monolithic multimodal foundation models can be externalized into an embodied architecture made of:

1. **specialized sensor and effector organs** operating in representations appropriate to their modality;
2. a **latent translation fabric** that learns projections only where communication is required;
3. an **embodied cognitive RTOS** that schedules attention, wakeups, deadlines, compute and model invocation;
4. **persistent memory** treated as another temporally indexed source of observation;
5. **trust / uncertainty / provenance** carried across translation boundaries;
6. one or more **cognitive models** (including an LLM) that are organs in the system rather than synonymous with the system;
7. an external **governance and capability boundary** that keeps proposed actions distinct from authorized execution.

A large multimodal model may internalize several of these functions. A small embodied system must expose them.

The architecture should remain coherent across both cases.

---

## The central correction to the 2025 VAE/puzzle-space framing

The 2025 sensor-puzzle-effector proposal made a strong move: it recognized that raw sensory spaces, reasoning spaces and action spaces cannot simply be wired together without translation.

The weak part was taking a **single universal representation** too literally.

A 30×30×10 puzzle space was a useful scaffold for HRM and ARC-like tasks. It should not become SAGE's ontology.

Likewise, "VAE" is best understood illustratively. A translator could be:

- a VAE;
- a linear or MLP projector;
- a cross-attention adapter;
- a learned tokenizer;
- a VQ codebook;
- a contrastive encoder pair;
- a small transformer;
- an inverse-dynamics head;
- a diffusion/action decoder;
- a hand-engineered symbolic projection;
- or a hybrid of learned and explicit transforms.

The durable abstraction is therefore not "shared latent space" in the singular.

It is a **latent translation fabric**.

---

## Native spaces, local shared spaces, translation edges

Each organ should be allowed to retain the representation best suited to its job.

Examples:

- vision may preserve spatial tensors, object tracks, optical flow or region embeddings;
- audio may preserve temporal/spectral structure;
- proprioception may remain a compact state vector;
- language may use token and embedding spaces;
- memory may expose semantic, episodic and temporal retrieval representations;
- motor control may use trajectories, joint states, force targets or affordance representations.

Communication occurs through learned or explicit translation edges.

Conceptually:

```text
                   visual native
                    /        \
                   /          spatial-motion
                  /                 \
audio native -- event latent ---- semantic latent ---- language model
                    \                 /
                     \-- affordance --/
                            |
                        motor latent
```

The important shift is:

> **Shared representation should be local to the relationship that needs it, not globally imposed on the whole being.**

That is consistent with SAGE's broader MRH intuition: representation and relevance are contextual.

Stereo cameras may need a correspondence space that language never sees.
Vision and IMU may need a self-motion space.
Vision and audio may meet in an event/presence space.
Language and perception may meet in a semantic space.
Cognition and manipulation may meet in an affordance/intent space.

No single latent needs to be complete.

---

## The LLM's role

The language model is not SAGE.

It is also not necessarily the unique reasoner.

In this architecture, an LLM is a powerful semantic/cognitive organ attached to the translation fabric:

```text
                     memory / history
                           |
vision ----\               |
audio ------> translation fabric <----> LLM
IMU -------/               |              |
clock ---------------------|          other cognition
                           |       world models / HRM /
                           |       policies / planners
                           |
                        effectors
```

A large multimodal model may absorb visual/audio projectors and some action interfaces internally.

A small model cannot.

The architecture should differ only in **where the boundary is drawn**, not in its conceptual organization.

This leads to a useful continuum:

```text
current small SAGE:
pixels -> handcrafted percept -> words -> text LLM

next:
pixels -> learned visual latent -> projector -> LLM embedding/prefix

larger:
multiple native latents <-> shared/local latent spaces <-> multimodal LLM

monolithic foundation model:
same translations largely internal to the backbone
```

Small systems therefore become valuable scientific instruments: they force normally hidden modality boundaries to become explicit and measurable.

---

## Sensors should not all become language

The current Sprout visual cortex already contains an important architectural warning.

Motion, binocular agreement, reafference, gaze stance, sensor health and salience can affect behavior without first being rendered into English.

That is a feature, not a limitation.

A healthy embodied stack should permit:

```text
sensor latent
   |\
   | \----> semantic/language projection ----> reflection / explanation
   |
   \------> fast policy / reflex projection --> embodied response
```

The LLM can receive a translated view of the same reality without becoming the only route by which reality affects action.

Otherwise language becomes an unnecessarily lossy and slow central bus.

---

## Effectors are inverse transducers

The old sensor→puzzle→effector framing was symmetric in an important way that later LLM-agent stacks often lose.

An effector is not merely a function call appended after reasoning.

It is an inverse transduction problem:

```text
intent / desired state
        |
        v
cognitive representation
        |
        v
action / affordance latent
        |
        v
effector-specific decoder or policy
        |
        v
bounded physical command
        |
        v
WORLD
        |
        v
sensors observe consequence
```

This creates a grounded learning loop.

The useful question is not only:

> Did the action decoder reproduce the demonstrated motor command?

but also:

> Given intended state X and action A, did the subsequently observed state Y match the predicted consequence?

This makes sensor and effector representations mutually grounding.

It also creates a natural place for trust: a translation edge earns trust when its predicted decompressions, cross-modal correspondences or action consequences remain reliable.

---

## Memory as a temporal sensor

Memory does not fit cleanly on either the "cognition" or "storage" side of the architecture because SAGE has long treated it as a **temporal sensor**.

The present world is observed through physical sensors.
The past world is observed through memory.
Possible futures are observed through prediction / imagination.

That suggests a unified view:

```text
physical sensors ---- present
memory -------------- past
world model ---------- possible future
clock ---------------- temporal position
         \              |              /
          \------ translation fabric --/
                         |
                      cognition
```

The scheduler should not care whether an observation came from a camera, a memory retrieval, or a prediction merely because one is stored and another is live.

It should care about:

- salience;
- latency;
- trust;
- uncertainty;
- provenance;
- relevance horizon;
- compute cost;
- freshness.

---

## The embodied cognitive RTOS

SAGE's old "cognition kernel" metaphor becomes much more concrete when connected to the recent awareness-loop work.

A traditional RTOS does not perform the application logic itself. It manages:

- tasks;
- priorities;
- interrupts;
- deadlines;
- devices;
- memory;
- resource contention;
- communication.

SAGE increasingly has direct analogues.

| RTOS concept | Embodied SAGE analogue |
|---|---|
| device driver | sensor / effector IRP |
| interrupt | salient world/sensor event |
| IRQ priority | event priority class |
| process/task | cognitive or transducer organ |
| scheduler | awareness / heartbeat loop |
| IPC / bus | latent translation fabric + explicit messages |
| deadline | interaction / control latency |
| CPU/power budget | ATP / metabolic budget |
| task priority | salience + relationship + urgency |
| device health | sensor trust / liveness |
| context switch | attention shift / model invocation |
| persistent storage | memory |
| privilege boundary | SAGE harness / Hestia |
| accelerator driver | compiled transducer implementation |

Recent code already implements pieces of this literally:

- wake events classified by priority;
- P0 human-addressed events can preempt routine work;
- the tool loop yields at explicit safe boundaries;
- work completed before a yield is not undone;
- the heartbeat records wake/preemption state.

This is no longer only analogy.

The research question is whether RTOS semantics can become the stable **control plane** for embodied cognition without collapsing cognitive flexibility into a rigid task scheduler.

---

## Translation fabric as cognitive IPC

The latent translation fabric is the representational counterpart to RTOS IPC.

A conventional OS bus does not require every process to use the same private memory layout. It defines boundaries and protocols for exchanging what needs to cross.

Likewise, SAGE should not require every modality to share one internal latent.

A translation edge should be describable by something like:

```text
source representation
target representation
temporal horizon
schema/version
uncertainty
provenance
trust
cost
expected information loss
fallback path
```

A projection can then be selected not just by "does one exist?" but by:

- how trustworthy it has been;
- whether its latency meets the current deadline;
- whether the current metabolic/ATP state can afford it;
- whether the target consumer actually needs the information;
- whether a cheaper symbolic path is sufficient.

This is where SAGE's trust and economy mechanisms become architecturally useful rather than decorative.

---

## Compression trust revisited

The earlier VAE analysis described "compression trust": meaning survives only if a compressed representation can be relied upon to preserve what matters for the downstream task.

The current framing broadens that.

Every translation is lossy.
The relevant question is not whether the source can be perfectly reconstructed.

It is:

> **Did the translation preserve the information required at this relevancy horizon for this relying organ?**

A visual-to-language projection may discard texture but preserve object identity and relation.
A visual-to-motor projection may discard names but preserve geometry and affordance.
A memory summary may discard wording but preserve causal structure.

Thus trust belongs to the **translation edge in context**, not merely to the encoder globally.

This also maps naturally to Web4 reasoning: evidence is presented to a relying party, and trust is contextual rather than absolute.

---

## Governance is not part of the learned latent

The translation fabric may propose actions.

It must not erase the distinction between proposal and authorization.

For consequential effectors:

```text
cognition / policy
      |
      v
action proposal latent
      |
      v
effector decoder
      |
      v
bounded proposal
      |
      v
SAGE harness / PolicyGate / Web4 authority
      |
      v
physical or external execution
```

The safety/governance boundary remains explicit even if the policy and effector decoder are heavily learned.

This principle also constrains compiled-transducer optimization: acceleration must stop before authorization, hard physical limits and witnessed execution become opaque inside a neural engine.

---

## Where compiled transducers fit

The [Compiled Transducers exploration](2026-10-06-compiled-transducers-sensors-effectors.md) is a child of this architecture.

A compiled transducer is not the architecture.

It is a hardware-shaped implementation of one expensive node or edge:

- audio → semantic representation;
- pixels → visual latent;
- semantic intent → speech;
- state → trajectory proposal;
- one latent representation → another.

The RTOS should be able to schedule a reference PyTorch implementation, a TensorRT engine, a CPU fallback or a symbolic shortcut under the same higher-level contract.

This is analogous to an operating system selecting a device driver/backend without changing what a device *means* to the application.

---

## Alternative hypotheses

This architecture may be attractive and still be wrong.

### A. Monolithic multimodality is fundamentally superior

It may be that the strongest generalization requires deep end-to-end co-adaptation across all modalities, and external projectors around a frozen small LLM cannot recover enough of the shared representational structure.

### B. Language is a sufficient universal bus

The current descriptor→text→LLM approach may prove so efficient and interpretable that direct latent projection offers little practical advantage on small devices.

### C. Translation graph complexity dominates

A graph of modality-native spaces and adapters may become impossible to train, version and debug compared with one shared latent or one multimodal model.

### D. RTOS semantics are too rigid

Priority/deadline scheduling may work for interaction latency but distort cognition if applied too aggressively to reflection, memory and open-ended exploration.

### E. Latent trust is not measurable enough

Cross-modal fidelity and downstream behavior may not provide stable enough evidence to assign useful trust to translation edges.

### F. Small-model bottlenecks dominate

The 0.8B/2B/4B model may simply lack enough representational capacity to use projected sensory latents meaningfully, regardless of adapter quality.

These are real falsifiers, not objections to be argued away.

---

# Exploration tracks

## Track A — Direct sensor-to-LLM latent projection on Sprout

### Question

Can a frozen text-native small model acquire a genuinely non-text sensory channel by training only a small projection from a sensor representation into its existing embedding space?

### Baseline

```text
camera → visual cortex / detector → symbolic descriptor → text tokens → LLM
```

### Experimental path

```text
camera
  → visual encoder
  → native visual latent
  → small trainable projector
  → N learned prefix/pseudo-token embeddings
  → frozen Sprout LLM
```

Use the same frozen LLM for both paths.

Training can use paired image/text or image/question/answer examples, optionally distilled from a larger multimodal teacher. The experiment is about the projection, not about teaching the 0.8B/2B model a new language model.

### Measurement

Compare:
- task accuracy on object/relation/state questions;
- latency and energy;
- token/context cost;
- robustness to paraphrase of the question;
- ability to preserve information not present in the handcrafted descriptor;
- hallucination / false-presence errors;
- behavior when the projector is absent, stale or low-confidence.

### Criterion

Track A passes if a small learned projection provides useful non-text sensory information that the frozen model can exploit **without requiring a full multimodal backbone**, and does so with a measurable advantage over the symbolic-text baseline on at least one meaningful task.

It fails if the projected channel is ignored, unstable, or no better than a compact descriptor after accounting for compute and training complexity.

---

## Track B — Local shared spaces rather than one universal latent

### Question

Do pairwise/local alignment spaces outperform forcing all modalities through one universal representation?

Candidate pairs:
- stereo vision ↔ correspondence/motion;
- vision ↔ IMU/self-motion;
- vision ↔ audio/event identity;
- vision ↔ language/semantics.

### Probe

For at least two modality pairs, compare:
1. independent modality-native features + direct pairwise projector;
2. a forced common bottleneck;
3. a symbolic/text bridge where applicable.

### Measurement

- downstream task accuracy;
- information retained for each consumer;
- adapter size;
- training data required;
- latency;
- sensitivity to one modality degrading;
- whether the representation remains useful to unrelated consumers.

### Criterion

The "translation fabric" framing gains support if local spaces consistently achieve equal or better downstream performance with lower representational compromise or lower training cost than a single universal bottleneck.

If one global space performs just as well and is much simpler, prefer it.

---

## Track C — Sensor/effector closed-loop grounding

### Question

Can an action representation become better grounded when trained/evaluated by its predicted sensory consequences rather than only by imitation of commands?

Start in simulation or a low-risk virtual effector.

### Loop

```text
state latent
  → desired-state / intent latent
  → action decoder
  → action
  → environment
  → next sensor state
```

Train or score against both:
- action imitation, where demonstrations exist;
- next-state prediction / goal-state achievement.

### Measurement

- task success;
- trajectory error;
- next-state prediction error;
- recovery after perturbation;
- transfer to unseen initial states;
- whether action-latent confidence predicts actual outcome reliability.

### Criterion

The inverse-transducer model passes if consequence-grounded training or trust improves closed-loop behavior beyond command imitation alone.

---

## Track D — Translation-edge trust

### Question

Can SAGE learn a useful trust score for a translation edge that predicts when the downstream representation should be relied upon?

For an edge A→B, record:
- source conditions;
- translation confidence;
- downstream success/failure;
- disagreement with alternate translators or sensors;
- reconstruction/cycle consistency where meaningful.

### Probe

Deliberately create:
- normal inputs;
- degraded/noisy sensor inputs;
- distribution shifts;
- stale adapters;
- partial occlusion / conflicting modalities.

### Criterion

Trust is useful if calibration predicts downstream failure well enough to improve routing, fallback choice or ATP allocation.

If edge trust does not predict consequential failure better than simple input-quality heuristics, do not elevate it into architecture.

---

## Track E — RTOS scheduling versus sequential cognition loop

### Question

Does explicit event priority, preemption and deadline-aware scheduling improve embodiment without degrading slower cognition?

### Existing anchor

The current awareness loop already supports:
- priority classes;
- person-addressed P0 events;
- yield points before generation;
- preservation of already executed work;
- preemption telemetry.

### Probe

Compare controlled runs with:
1. sequential beat processing;
2. current priority/preemption;
3. deadline-aware extension where sensor/control deadlines differ from reflective work.

Measure:
- human-turn latency;
- sensor event latency;
- missed/deferred work;
- amount of wasted computation;
- reflection/memory quality;
- starvation/fairness;
- power/ATP use.

### Criterion

The RTOS framing passes if explicit scheduling improves urgent latency and resource use **without starving low-priority cognition or creating pathological attention thrash**.

---

## Track F — Architecture across model scale

### Question

Does the same organ/translation/scheduler architecture remain useful when the central model changes scale and native modality support?

Compare at least:
- Sprout-class small text-native model;
- CBP-class small local model;
- Thor/Legion-class larger or multimodal model.

### Prediction

As model capability rises:
- some translation edges move **inside** the model boundary;
- some external adapters become unnecessary;
- RTOS scheduling, memory, trust, effectors and governance remain external and useful.

### Criterion

The architecture gains support if the **boundary moves but the system decomposition survives**.

It weakens if larger multimodal models make the surrounding architecture mostly redundant rather than merely absorbing some organs.

---

## Relationship to the compiled-transducer arc

The compiled-transducer exploration tests **how an organ runs**.

This exploration tests **what the organs are and how they relate**.

The expected hierarchy is:

```text
Embodied Cognitive RTOS + Latent Translation Fabric
    |
    +-- sensor/effector organ contracts
    +-- translation edges and local shared spaces
    +-- scheduling / salience / ATP / deadlines
    +-- trust / memory / provenance
    +-- governed action boundary
    |
    +-- Compiled Transducers
          |
          +-- TensorRT / quantization / fusion
          +-- target-specific engine optimization
```

Hardware optimization should not dictate the cognitive architecture.

---

## Graduation criteria

This parent architecture should be promoted from exploration to a stronger SAGE architectural commitment only if there is evidence for **all** of the following:

1. **Direct latent projection works** on at least one small text-native being and provides useful information not captured as efficiently by a symbolic/text bridge.
2. **At least two modalities** demonstrate useful translation/alignment, with evidence that local shared spaces are viable.
3. **At least one effector** participates in a closed sensor→cognition→action→sensor learning loop.
4. **Translation confidence/trust** predicts downstream reliability well enough to influence routing or resource allocation.
5. **RTOS scheduling semantics** measurably improve urgent interaction/control behavior without starving reflective cognition.
6. The decomposition remains meaningful across **at least two model scales**.
7. Governance remains separable from learned representations and action generation.

No one experiment is enough.

---

## What would falsify the zoomed-out architecture?

The broad framing should be weakened or abandoned if several of these occur:

- direct latent channels provide no practical advantage over concise symbolic/text descriptors;
- pairwise translation adapters become brittle enough that one end-to-end multimodal model is clearly simpler and better;
- small LLMs cannot make useful use of projected non-text embeddings;
- action representations cannot be grounded through sensed outcomes;
- translation trust cannot be calibrated;
- priority/deadline scheduling creates more cognitive pathology than latency benefit;
- model scale makes most external structure disappear rather than simply moving boundaries;
- maintaining representation schemas/versioning becomes the dominant engineering burden.

A good architecture should reduce accidental complexity. If the translation graph becomes the problem, that is a negative result.

---

## Near-term experiment order

1. **Sprout visual-latent → frozen-LLM projection** against the existing descriptor→text path.
2. **Vision ↔ IMU or stereo local alignment** as a non-language shared-space test.
3. **Translation-edge confidence calibration** under controlled sensor degradation.
4. **RTOS latency/fairness benchmark** using the existing preemption machinery.
5. **Low-risk action-latent closed loop** in simulation.
6. **Repeat one projection experiment on CBP or Thor** to test scale/boundary movement.
7. Continue the child **Compiled Transducers** arc independently for hardware execution evidence.

---

## Current interpretation

The SAGE repository already contains many of the pieces:

- "SAGE = kernel, IRP = API, VAE = translation layer";
- modality-specific sensors/effectors;
- latent compression and projection experiments;
- memory as temporal context;
- salience and ATP;
- persistent identity;
- explicit awareness-loop priority and preemption;
- governed effectors;
- target-specific compiled inference.

What it lacks is a current document that puts them into one coherent systems model without mistaking early implementations for eternal architecture.

This exploration proposes that model:

> **SAGE is an embodied cognitive RTOS coordinating specialized organs through a contextual latent translation fabric, with memory extending sensing through time and governance separating proposed action from authorized consequence.**

The claim is intentionally broader than the evidence.

The next step is not to rename the codebase around it.

The next step is to make the translation and scheduling hypotheses fail or survive experimentally.

---

## Status log

### 2026-10-06 — Track E baseline recorded on Sprout (sprout-claude)

This is read-only, from existing beat and conversation records, covering 2026-10-02 12:00Z to 10-06 19:32Z. That window is 629 beats with R2 priority/preemption on (`preempt: true`).

| measure | value |
|---|---|
| person turn → spoken reply, turn arrived **mid-beat** (R2 preemption) | p50 36 s, p75 43 s, p95 69 s (n=18) |
| person turn → reply, turn **woke an idle being** | **225 s** voice, **199 s** typed (n=1 each) |
| beats preempted | 20 of 629 (3.2%): posture 7, explore 5, reflect 4, before account 3, account 1 |
| preempted beats that skipped reflection | 16 of 20 |
| longest run of consecutive preempted beats (thrash) | 4 |
| gap between reflections | p50 3 min, p95 34 min, max 39 min (no starvation seen) |
| what woke beats | presence 503, timer 116, event 10 |
| beat duration | p50 124 s, p95 216 s |

**Finding: an inversion.** A person who speaks to an idle being waits about 3–4× longer than one who interrupts a running beat. The waking beat starts within 20–34 s. But the waking event is **claimed** at the start, and R2 only sees person events that arrive *after* that. So the beat runs explore, posture, account and reflect, and answers last. The RTOS note described this as R3 ("a fast path for P0 when idle"); it was never implemented.

**Action:** R3 is opt-in per instance (`answer_first_on_person_wake`, which requires `preempt`). A beat woken by a person enters the preempted path at the start: the answer goes first, account and reflection wait for the next beat, and act-after-answer is unchanged. The measurement after enabling uses the same script, comparing idle-arrival latency against the 199–225 s baseline. The fairness checks (reflection gap, preemption runs) have to stay as above.
