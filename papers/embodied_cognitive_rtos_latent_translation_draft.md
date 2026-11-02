# Beyond the Monolithic Multimodal Model:
## An Embodied Cognitive RTOS with a Latent Translation Fabric

**Draft — October 2026**  
**Status:** Working research paper. Architectural thesis with partial implementation evidence; several central claims remain experimental.

## Abstract

Modern multimodal AI increasingly concentrates perception, language, memory and action inside large end-to-end foundation models. This approach is powerful, but it is not the only route to coherent embodied intelligence. It is also poorly matched to small edge systems, where sensors, accelerators, language models and effectors are heterogeneous, independently constrained and often replaced on different timescales.

We develop an alternative systems view: an embodied agent can be organized as a **cognitive real-time operating system (RTOS)** coordinating specialized organs through a **latent translation fabric**. Each sensor, memory system, cognitive model and effector is allowed to retain a representation suited to its own modality. Learned or explicit translation edges connect only the representations that need to communicate. A language model becomes one cognitive organ rather than the definition of the agent. Memory acts as a temporal sensor, action as inverse transduction from intent into bounded consequence, and trust attaches to translation edges according to how reliably they preserve task-relevant meaning. An RTOS-like control plane schedules attention, wakeups, deadlines and compute, while an external governance boundary separates action proposals from authorized execution.

This architecture is motivated by work in SAGE, a persistent embodied-agent research system running across devices from small Jetson-class nodes to larger local GPU machines. Earlier SAGE designs used variational autoencoders and a universal "puzzle space" as concrete translation mechanisms. We argue that the durable principle is more general: not one universal latent, but a graph of modality-native and locally shared representations with measured translation between them.

The paper distinguishes architectural claims from current evidence and proposes falsifiable experiments: direct sensor-to-frozen-LLM projection on small text-native models, local cross-modal alignment versus universal bottlenecks, consequence-grounded sensor/effector learning, translation-edge trust calibration, and RTOS scheduling benchmarks. The central hypothesis is that some benefits of monolithic multimodality can be recovered—or made more inspectable and resource-efficient—by externalizing the mechanisms that large multimodal models hide inside their boundaries.

---

## 1. Introduction

A common mental model of advanced AI is increasingly simple: make the model large enough, multimodal enough and context-rich enough that perception, reasoning and action all become internal capabilities of one network.

That trajectory is producing remarkable systems. It also hides an architectural question.

When a multimodal model receives images, audio and text, some representation must still translate those modalities into forms that can interact. When an embodied model emits actions, some representation must still connect internal state to motor or tool space. When the system cannot process every event at once, something must still allocate time and compute. When it remembers, something must decide what persisted state enters the next decision. When an action carries real consequence, something outside pure next-token prediction must decide whether the proposed act is allowed.

A sufficiently large model can internalize many of these functions. Internalization is not the same as elimination.

For small embodied agents the functions become impossible to ignore. A Jetson-class system cannot simply host a frontier multimodal model that absorbs every camera, microphone, memory channel and actuator into one trained backbone. Its sensory processing may run in TensorRT, its language model in a different runtime, its motor policy in another model, and its safety boundary in ordinary code. Memory spans sessions and model replacements. Power and latency are first-class constraints.

This makes small embodied systems scientifically useful. They expose interfaces that large models conceal.

This paper asks whether those exposed interfaces can be made into a principled architecture rather than treated as integration debt.

We propose two complementary ideas:

1. **Latent translation fabric** — specialized components retain modality-native representations and communicate through learned or explicit projections into local shared spaces.
2. **Embodied cognitive RTOS** — a control plane schedules attention, sensor events, model invocation, memory, compute and effectors according to urgency, salience, trust and resource constraints.

The resulting system is not centered on one model. It is centered on a persistent embodied process.

---

## 2. From Model-Centric to System-Centric Intelligence

A model-centric architecture tends to identify capability with the model:

```text
input -> model -> output
```

An embodied system quickly becomes:

```text
sensors -> perception -> memory -> cognition -> policy -> effectors
                     \       |       /
                      resource/safety
```

The second diagram is not merely a larger version of the first. It contains qualitatively different problems:

- heterogeneous timescales;
- asynchronous events;
- different failure modes;
- different numerical representations;
- different hardware;
- different authority levels;
- persistence across model invocations;
- actions whose consequences return through sensors.

If the agent persists while individual models can be swapped, then identity and cognition are also no longer identical to one set of weights.

SAGE began from this observation operationally: the system surrounding a model—identity, memory, trust, attention, tools, developmental history and governance—can materially change behavior without modifying the model itself. Embodiment extends the same idea downward into perception and action.

The key architectural unit becomes the **organ**, not the foundation model.

An organ is any specialized component that transforms part of the being's state:

- visual perception;
- auditory perception;
- proprioception;
- language reasoning;
- memory retrieval;
- prediction;
- planning;
- speech generation;
- motor policy;
- external tool use.

Some organs may be neural.
Some may be symbolic.
Some may be compiled accelerator engines.
Some may be ordinary deterministic code.

The system problem is how they communicate and how they are scheduled.

---

## 3. Why a Single Universal Latent Is Too Strong

Earlier SAGE work proposed a concrete sensor→puzzle→effector architecture. Raw modalities would be encoded into a common puzzle representation, processed through hierarchical reasoning, then decoded into action.

That proposal captured a real problem: modalities need translation.

Its most literal assumption—that all modalities should share one universal representation—now appears unnecessary.

Different modalities preserve different invariants.

A visual representation may need spatial locality.
An audio representation may need temporal phase or spectral structure.
Proprioception may need precise continuous state.
Language benefits from discrete sequential structure.
A motor policy may care about reachable trajectories and contact geometry rather than object names.

Forcing all of them through one bottleneck risks discarding information merely to make the interfaces look uniform.

A more flexible model is a **graph of representations**.

```text
                   visual native
                    /        \
                   /          motion/self-state
                  /                 \
audio native -- event state ------ semantic state ---- language
                    \                 /
                     \-- affordance --/
                            |
                         action
```

Shared spaces exist where relationships require them.

They are local rather than universal.

This resembles ordinary systems engineering more than it resembles a single neural network. Two processes do not need identical private memory layouts in order to communicate. They need a contract at the boundary.

The translation fabric is that contract layer for representations.

---

## 4. The Latent Translation Fabric

A translation edge maps one representation into another:

```text
z_B = T_{A->B}(z_A, context)
```

where (z_A) and (z_B) need not share dimensionality, topology, precision or timescale.

The implementation of (T) is deliberately unconstrained. It may be:

- a linear projection;
- an MLP;
- a cross-attention adapter;
- a VAE/VQ-VAE encoder or decoder;
- a learned tokenizer;
- a small transformer;
- a contrastively trained mapping;
- an inverse-dynamics model;
- a symbolic transducer;
- a hybrid learned/symbolic codec.

The important property is not architectural fashion. It is that the translation is independently measurable.

For each edge the system should eventually be able to describe:

- source and target schema;
- version;
- temporal horizon;
- expected information loss;
- uncertainty;
- provenance;
- latency;
- compute/energy cost;
- calibration/trust history;
- fallback paths.

This turns representation translation from an invisible implementation detail into a schedulable, testable system resource.

### 4.1 Translation is task-relative

Perfect reconstruction is usually the wrong objective.

A visual→language translation may safely discard texture while preserving:
- object identity;
- relation;
- motion;
- uncertainty.

A visual→motor translation may discard names while preserving:
- geometry;
- contact state;
- affordance;
- predicted collision.

A memory summary may discard wording while preserve:
- causal relation;
- commitment;
- unresolved dependency.

Translation quality should therefore be evaluated relative to a **relying organ and relevancy horizon**.

This is a more general form of what earlier SAGE work called *compression trust*.

---

## 5. The Language Model as an Organ

Large language models are unusually capable semantic processors, but making one the conceptual center of an embodied system creates an avoidable bottleneck.

Consider a small text-native embodied model.

A common integration path is:

```text
camera -> detector -> English description -> tokenizer -> LLM
```

This is useful because it is simple and interpretable. It is also severely lossy. Everything the model can know about vision is limited to what the descriptor author decided to verbalize.

A richer path is:

```text
camera
  -> visual encoder
  -> visual latent
  -> small learned projector
  -> embedding/prefix consumed by frozen LLM
```

The LLM does not need to become a native vision model. It needs a translation edge from visual representation into a space it can use.

The same principle applies to audio, proprioception and memory.

At larger scale, a multimodal foundation model may move these projectors inside the model boundary. The conceptual architecture does not disappear; the implementation boundary moves.

This yields a useful prediction:

> As the central model becomes larger and more multimodal, some translation edges should migrate inside it, while scheduling, persistent memory, effectors, trust and governance remain system-level concerns.

If instead a sufficiently large model makes nearly all surrounding structure irrelevant, the proposed architecture is weakened.

---

## 6. Why Sensors Should Not All Become Tokens

There is another reason not to make language the universal bus: some embodied responses should never wait for linguistic interpretation.

Visual motion can trigger attention before object naming.
Proprioceptive instability can alter control before verbal explanation.
Audio onset can wake the system before transcription completes.

A useful architecture therefore branches:

```text
sensor latent
   |\
   | \----> semantic projection -> LLM / reflection / report
   |
   \------> fast policy/reflex -> immediate embodied response
```

The semantic route supports deliberation.
The fast route supports embodiment.

Both may later influence memory and trust.

This is not an argument for fixed reflexes over reasoning. It is an argument against forcing every timescale through one representational and computational path.

---

## 7. Effectors as Inverse Transduction

LLM-agent frameworks often treat action as a terminal API call:
the model emits structured text and a tool executes it.

Physical embodiment exposes a deeper symmetry.

Sensors translate world state inward.
Effectors translate desired state outward.

```text
world -> sensor -> latent -> cognition
cognition -> latent -> effector -> world
```

An effector decoder is therefore an **inverse transducer**.

Its quality can be judged by consequence, not only by command fidelity.

Suppose a system has:
- observed state (s_t);
- desired state (g);
- proposed action (a_t);
- observed next state (s_{t+1}).

Then action learning can use not only imitation loss on (a_t), but prediction or goal error on (s_{t+1}).

The closed loop matters because it grounds internal representations in causal consequence.

This also offers a route to trust.

An action decoder that repeatedly predicts the consequences of its actions accurately should be treated differently from one whose outputs are syntactically valid but behaviorally unreliable.

---

## 8. Memory as a Sensor Across Time

An embodied agent does not observe only the present.

It observes:
- the present through physical sensors;
- the past through memory;
- possible futures through prediction.

Treating memory as a temporal sensor makes this symmetry explicit.

```text
camera/mic/IMU ---- present evidence
memory ------------ past evidence
world model -------- possible future evidence
clock -------------- temporal coordinate
```

All four can feed the same attention and trust machinery.

The distinction between "live sensor" and "memory" remains operationally important—freshness and provenance differ—but both are observations presented to cognition.

This framing helps explain why persistent identity and memory can produce behavior that differs sharply from a stateless model even when the underlying language model is unchanged. The system is not asking the same model the same question. It is constructing a different temporally grounded reality around it.

---

## 9. The Embodied Cognitive RTOS

Representation is only half the problem.

Embodied cognition is also a scheduling problem.

A person speaks while the system is reflecting.
A camera notices motion while a model is generating.
A motor controller has a deadline shorter than a memory-consolidation cycle.
A low-power device cannot run every neural organ continuously.
A background thought should not block an urgent interaction.

These are recognizably real-time systems problems.

A cognitive RTOS need not be a literal operating-system kernel. The claim is functional: the control plane should provide concepts analogous to those that make real-time computing coherent.

| Real-time systems | Embodied cognition |
|---|---|
| interrupt | salient event |
| priority | urgency / relationship / salience |
| task | cognitive or sensory process |
| deadline | acceptable response/control latency |
| scheduler | awareness loop |
| device driver | sensor/effector organ |
| IPC | translation/message fabric |
| power budget | metabolic / ATP budget |
| device health | sensor trust/liveness |
| context switch | attention reallocation |
| persistent storage | memory |
| privilege boundary | action/governance harness |

SAGE's current awareness loop already implements a narrow version of this: events are assigned priority classes, a person addressing the being can preempt routine work, and the generation/tool loop includes explicit yield points.

That evidence does not prove the broader RTOS architecture. It does show that the metaphor has crossed into executable semantics.

### 9.1 Preemption is not attention

A cognitive scheduler must avoid a trap.

If every salient event becomes a hard interrupt, the system becomes reactive and incoherent.

Real-time systems distinguish:
- interrupt handling;
- deferred work;
- priority inheritance;
- fairness;
- deadlines;
- starvation.

Embodied cognition needs analogous mechanisms.

A person speaking may deserve immediate acknowledgement, while the interrupted reflective process may need resumable state rather than deletion.

Thus the research target is not maximal responsiveness. It is **coherent temporal arbitration**.

---

## 10. Trust at Translation Boundaries

Heterogeneous systems fail at interfaces.

A camera can be noisy.
A projector can be stale.
A model can misinterpret a latent.
A memory summary can omit a crucial exception.
An action decoder can be outside its training distribution.

A modular architecture makes these boundaries visible enough to measure.

For a translation (T_{A->B}), trust can be updated from evidence such as:

- agreement with another modality;
- downstream task success;
- reconstruction or cycle consistency;
- predicted versus actual action consequence;
- calibration under known degradation;
- temporal stability;
- known version/provenance.

Trust should be contextual, not global.

A visual→semantic translator may be trusted for object identity but not depth.
A memory compressor may be trusted for topic continuity but not exact quotation.
A motor model may be trusted in free space but not near contact.

The system can use this trust operationally:
- route through an alternate translator;
- request a higher-cost sensor;
- allocate more compute;
- preserve uncertainty;
- refuse to act.

This is a stronger role for uncertainty than attaching a confidence number to a final answer.

---

## 11. Governance Must Remain Outside the Learned Action Path

A system that can translate intent into action still needs a boundary between **proposal** and **authority**.

The architecture should preserve:

```text
cognition
   -> action proposal
   -> effector decoder
   -> bounded candidate action
   -> authorization / policy / hard safety
   -> execution
   -> witnessed outcome
```

The learned policy may be excellent.
The effector decoder may be compiled and highly optimized.
Neither should silently become the authorization layer.

This matters more as agents gain persistent identity and physical or digital authority.

A modular system can make the distinction explicit:
- cognition proposes;
- the harness authorizes;
- the effector executes;
- sensors observe consequence;
- evidence updates memory and trust.

The same separation supports debugging and accountability.

---

## 12. Hardware-Shaped Organs

Once cognition is decomposed into organs and translation edges, hardware optimization has a natural place.

An ASR engine, visual encoder, speech synthesizer or motor policy can be compiled, quantized and fused for a particular target without changing the surrounding architecture.

This is the role of what SAGE currently calls a **compiled transducer**.

A compiled transducer is not a new cognitive ontology. It is a target-specific implementation of a known transformation.

For example:

```text
audio -> semantic representation
```

may be implemented by:
- a reference PyTorch model on a workstation;
- TensorRT FP16 on one edge board;
- INT8 on another;
- a CPU fallback;
- a symbolic shortcut for a simple signal.

The scheduler chooses according to capability, trust, deadline and cost.

This separation is important because hardware changes faster than the conceptual role of hearing.

---

## 13. Scaling Across Small and Large Models

The architecture makes a specific claim about scale.

### Small text-native model

Most boundaries are explicit:

```text
sensor -> encoder -> projector -> LLM -> action projector -> effector
```

### Larger multimodal model

Some boundaries move inward:

```text
sensor -> [multimodal model: encoder + projector + language reasoning] -> effector
```

### End-to-end embodied foundation model

Even more moves inward:

```text
sensor -> [multimodal reasoning + policy] -> actuator proposal
```

But several things remain outside:
- physical device timing;
- persistent identity;
- durable memory policy;
- resource contention;
- authority;
- hard safety;
- evidence of consequence.

The architecture is therefore not anti-foundation-model.

It is a claim about **where system responsibilities live when they are not, or should not be, hidden inside weights**.

---

## 14. SAGE as an Implementation Case

SAGE provides a useful but incomplete implementation environment for this thesis because many pieces evolved independently before the current synthesis.

Historically, SAGE documents described:
- SAGE as the cognition kernel;
- IRP as the common plugin interface;
- VAE/compression as the translation layer;
- a universal puzzle-space bridge from sensors to reasoning to effectors;
- trust-weighted resource allocation.

Current embodiment work adds:
- continuous visual and audio sensing;
- symbolic and learned perception on constrained hardware;
- persistent beings across sessions;
- event-driven wakeups;
- priority classes;
- preemption/yield semantics;
- governed effectors;
- model-independent memory and identity;
- hardware-specific inference paths.

The important caution is that these pieces do not yet constitute empirical validation of the whole theory.

Some are implemented.
Some are partially implemented.
Some exist only as architectural proposals.

The value of the synthesis is that it produces experiments that can now distinguish them.

---

## 15. Experimental Program

### 15.1 Direct visual latent into a frozen small LLM

Train only a small projector from an existing visual encoder into prefix/pseudo-token embeddings for a frozen text-native LLM.

Compare against:
- handcrafted visual descriptor → text;
- optionally a larger native multimodal teacher.

Measure:
- visual question accuracy;
- relation/state understanding;
- context-token cost;
- latency/energy;
- hallucination;
- performance on information intentionally omitted from the symbolic descriptor.

This is the cleanest test of whether small language models can gain a new sensory channel without full multimodal retraining.

### 15.2 Local shared spaces versus universal bottleneck

Choose two cross-modal relationships such as:
- vision↔IMU self-motion;
- vision↔audio event identity.

Compare:
- pairwise learned alignment;
- universal bottleneck;
- symbolic bridge.

If local spaces consistently preserve more task-relevant information at lower cost, the translation-fabric hypothesis gains support.

### 15.3 Translation trust calibration

Degrade a sensor or adapter in controlled ways.

Ask whether translator confidence/history predicts downstream failure.

Then test whether routing by trust improves performance:
- use alternate representation;
- request another modality;
- spend more compute;
- abstain.

### 15.4 RTOS scheduling benchmark

Compare sequential cognition with priority/preemptive scheduling.

Measure:
- urgent response latency;
- sensor deadline misses;
- wasted compute;
- fairness/starvation;
- reflective task quality;
- memory continuity after interruption.

The hypothesis is not that preemption is always better. It is that explicit temporal arbitration outperforms accidental queue order.

### 15.5 Closed-loop action grounding

In simulation or a low-risk environment:
- encode state;
- generate action latent;
- execute;
- observe next state;
- train or score against predicted consequence.

Test whether consequence-grounded action representation improves recovery and generalization beyond command imitation.

### 15.6 Cross-scale boundary movement

Repeat one translation task with:
- small text-only model;
- larger local model;
- native multimodal model.

Observe which external organs disappear and which system-level functions remain.

---

## 16. Falsifiability

The architecture should be rejected or narrowed if the experiments show that:

- direct latent projection provides no meaningful advantage over concise text descriptors;
- small models cannot make stable use of projected non-text representations;
- pairwise translation graphs are more brittle and expensive than a shared universal representation;
- translation trust does not predict consequential failure;
- RTOS-style scheduling harms coherence more than it improves latency;
- closed-loop sensor/effector grounding provides no benefit over ordinary imitation;
- large multimodal models eliminate rather than merely internalize most of the surrounding system structure.

The goal is not to defend modularity.

The goal is to discover where modularity is actually useful.

---

## 17. Discussion

The broader implication is that **multimodality is partly a systems problem**.

A model can be multimodal because its training embeds multiple modalities into one end-to-end network.

A persistent agent can also become multimodal because it develops reliable translations among specialized organs.

These are not equivalent architectures, but they may implement overlapping functions.

The second path has several potential advantages:
- incremental addition of modalities;
- hardware specialization;
- inspectable failure boundaries;
- independent replacement of organs;
- explicit uncertainty and trust;
- operation on small edge hardware;
- separation of cognition from authority.

It also has obvious costs:
- more interfaces;
- versioned schemas;
- harder joint optimization;
- adapter training;
- scheduler complexity;
- possible loss of emergent cross-modal structure.

The empirical question is where the tradeoff lies.

Small embodied agents are a particularly good place to study it because they cannot hide integration inside scale.

---

## 18. Conclusion

A persistent embodied AI system is more than a model with tools.

It is a time-bound process that must continuously decide:
- what happened;
- what matters;
- what deserves compute;
- how representations cross modality boundaries;
- what to remember;
- what to do;
- whether an action is allowed;
- what the consequence taught it.

We propose treating that process as an **embodied cognitive RTOS** coordinating specialized organs over a **latent translation fabric**.

The architecture does not require one universal latent.
It does not require a VAE.
It does not require a particular language model.
It does not oppose large multimodal models.

Its core claim is simpler:

> **Representations should remain native where possible, be translated where necessary, scheduled according to time and resource constraints, and trusted according to observed consequences.**

If that claim survives experiment, then general embodied capability need not be concentrated entirely inside one model.

Some of it can live in the organization of the being.
