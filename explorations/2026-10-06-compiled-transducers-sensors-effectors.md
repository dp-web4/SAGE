---
date: 2026-10-06
status: drafted — ready to run
proposed by: dp + GPT-5.6 Sol
parent: explorations/2026-10-06-embodied-cognitive-rtos-latent-translation-fabric.md
trigger: review of ncannings/fastconformer-trt
related:
  - sage/embodiment/README.md
  - sage/embodiment/listening.py
  - sage/embodiment/detector.py
  - sage/embodiment/visual_cortex.py
  - sage/interfaces/audio_effector.py
  - sage/interfaces/effector_hub.py
  - sage/docs/SENSOR_EFFECTOR_DESIGN.md
  - docs/why/SAGE_WHITEPAPER.md
---

# Compiled Transducers — Can Hardware-Shaped Neural Execution Generalize Across SAGE Sensors and Effectors?

## Trigger

On 2026-10-06 we reviewed Nicholas Cannings' [fastconformer-trt](https://github.com/ncannings/fastconformer-trt), a newly published implementation that takes NVIDIA NeMo FastConformer / Parakeet ASR checkpoints and turns them into hardware-shaped TensorRT inference engines.

The headline result is speech recognition, but the interesting part for SAGE is the method:

- rewrite a training/general-purpose forward path into a lean inference-equivalent graph;
- verify equivalence against the reference before optimizing;
- profile where time and energy actually go;
- quantize only where measured quality permits;
- fuse memory-bound stages so large intermediates never leave registers/shared memory when possible;
- fold residuals, bias, activation, layout and quantization work into GEMM epilogues;
- cache invariant temporal structure;
- pack variable-length work to a frame budget instead of a fixed item count;
- pipeline stages across execution streams;
- keep optimizations only when end-to-end quality survives;
- publish dead ends as well as wins.

The upstream implementation reports roughly 4–5x end-to-end speedup over stock NeMo on several GPUs while preserving ASR accuracy, with much larger absolute real-time factors. Its engineering notes are unusually useful because they document both successful and failed optimizations:

- [README](https://github.com/ncannings/fastconformer-trt)
- [Stock-weight engine notes](https://github.com/ncannings/fastconformer-trt/blob/main/docs/01-stock-weight-engine.md)
- [Pruning / distillation notes](https://github.com/ncannings/fastconformer-trt/blob/main/docs/03-pruning-and-distillation.md)
- [TensorRT/CUDA plugins](https://github.com/ncannings/fastconformer-trt/tree/main/engine/plugins)

This exploration asks whether that is merely a very good ASR optimization, or evidence for a broader SAGE execution pattern.

## Hypothesis under test

**Primary hypothesis:** the `fastconformer-trt` optimization discipline generalizes beyond speech. For learned SAGE organs, a reference implementation can be transformed into a target-specific compiled transducer that materially reduces latency and/or energy while preserving the organ's semantic behavior.

A **compiled transducer** here means:

```
reference organ
    ↓
lean inference-equivalent graph
    ↓
equivalence harness
    ↓
target-specific compilation / quantization / fusion
    ↓
measured organ with the same SAGE-facing contract
```

The term is deliberately provisional. This exploration does **not** add a new SAGE architectural primitive yet.

### Alternative explanations

1. **ASR-specific win.** FastConformer happens to expose unusually profitable fusion/FP8 opportunities; the method produces little value elsewhere.
2. **Datacenter-specific win.** The gains depend on Hopper/Blackwell FP8 throughput and do not survive SAGE's edge-device constraints.
3. **Wrong optimization target.** SAGE's real bottlenecks are sensor duty cycle, wake/salience policy, model capability, I/O, or power spikes rather than graph execution.
4. **Semantic erosion.** Quantization/fusion preserves benchmark-level accuracy but changes the rare behaviors that matter to embodied SAGE.
5. **Governance conflict.** Effector compilation becomes unsafe or opaque if optimization crosses the boundary between proposal generation and governed action.

The arc exists to distinguish these cases experimentally.

## Why this matters to SAGE specifically

SAGE treats physical sensors, memory, and cognition as peer sources feeding a coherent reality field, while the L-module learns through repeated sensor/effector interaction. That makes efficient transduction more important than "model inference speed" in isolation.

The current embodiment stack already contains several relevant seams:

- **Hearing** continuously performs cheap level/onset sensing, then conditionally sends segmented utterances to a learned transcriber.
- **Vision** continuously performs cheap motion/trust/binocular/salience work, while learned object recognition runs as a separate TensorRT path.
- **TTS** is a learned effector behind the common Effector interface.
- **GR00T / learned motor policy** is conceptually a temporal state → trajectory transducer.
- **Memory and cognition** are temporal sensors; some future learned transforms may become dense enough for the same execution discipline to matter.

The strongest possible result would therefore not be "replace Whisper" or "use TensorRT more." It would be a repeatable method for compiling any sufficiently expensive learned organ while leaving SAGE's contracts intact.

## Transfer map

| SAGE surface | Expected relevance | What may transfer | What probably does not |
|---|---:|---|---|
| Speech / ASR | Very high | Lean graph, PTQ, temporal packing, preprocessing fusion, decoder optimization | Upstream FP8 kernels may not target Orin |
| Vision recognition | High | GPU-resident preprocess/postprocess, layout fusion, INT8/FP16, temporal work budgeting | FastConformer architecture itself |
| Optical flow / learned depth / future temporal vision | Very high | Temporal compression, cached structure, fused attention/conv, variable-length work | Speech decoder details |
| Memory / cognition sensors | Medium | Packed temporal work, cached positional state, precision profiling | Physical sensor front-end tricks |
| IMU / simple proprioception | Low | Measurement discipline | Compilation likely not worth complexity |
| TTS | High | Quantization, cached speaker/reference state, staged pipeline, codec fusion | ASR encoder layout |
| Learned motor policy / GR00T | High | Compiled temporal policy inference, cached conditioning, fused output transform | Governance/safety boundary must stay outside |
| Simple effectors | Low | Queue/scheduling measurement | Neural compilation is irrelevant |

## The architectural boundary

For **sensors**, a compiled organ may sit behind the existing sensor/IRP contract:

```
world
  → acquisition
  → lean transform
  → compiled neural organ
  → compact observation
  → trust / SNARC / fusion
  → SAGE
```

For **effectors**, compilation must stop earlier:

```
SAGE intent
  → governance / authorization
  → compiled neural proposal generator
  → bounded proposal
  → safety / actuator envelope / witnessed execution
  → world
```

A compiled engine must never absorb PolicyGate, Web4 authorization, witnessed receipts, hard actuator limits, or other mechanisms whose separability is itself part of the trust model.

Optimization may accelerate **what action is proposed**. It must not make the proposal indistinguishable from the authorization to act.

## The most transferable techniques

### 1. Lean reference-equivalent graphs

The upstream work got a large fraction of its gain not from a different model but from rewriting the same computation for inference:

- masks built once;
- unnecessary fp32 excursions removed;
- batch norm folded;
- tensor layouts chosen for the consumer rather than "normalized" between every stage;
- invariants precomputed;
- export performed only after numerical equivalence checks.

This suggests a SAGE rule:

> Do not optimize the production implementation directly. First produce a lean implementation with a mechanically testable equivalence relation to the reference.

The equivalence relation will differ by modality:
- ASR: transcript / segment agreement and corpus error rate;
- vision: detection labels, boxes, confidence envelope and downstream descriptor behavior;
- TTS: decoded content plus acoustic/codec-quality envelope;
- motor policy: bounded trajectory divergence and identical safety/governance treatment.

### 2. Optimize memory traffic before FLOP count

The FastConformer profile repeatedly found that tensor writes, reads, layout changes and small elementwise stages mattered as much as arithmetic. Fusing activations, residuals, quantization and output layout into producer kernels paid more reliably than abstract reductions in FLOPs.

This is directly relevant to SAGE's current object detector path:

```
OpenCV/NumPy frame
  → CPU letterbox / RGB / CHW / normalize
  → CPU→GPU copy
  → TensorRT YOLO
  → GPU→CPU output copy
  → NumPy NMS
  → a few detections
```

The first question is therefore not "can YOLO be faster?" It is: **how much of the organ's cost is model arithmetic versus movement across those boundaries?**

### 3. Budget the actual work, not item count

The upstream fixed-batch path left GPU throughput unused when utterances were short. Packing by padded temporal-frame budget improved end-to-end throughput without changing the model.

SAGE has an even more natural generalization: **ATP-backed perceptual work budgets**.

Possible units include:
- audio frames/samples;
- camera pixels/ROIs/temporal frames;
- object proposals;
- memory events;
- cognitive tokens;
- trajectory horizon steps.

Salience decides **what deserves work**; a compiled-organ scheduler can decide **how to pack that work efficiently**.

This is a conceptual fit, but it remains a hypothesis until measured.

### 4. Pipeline adjacent stages, but distrust theoretical overlap

FastConformer gains only modestly from encoder/decoder stream overlap because the stages compete for the same GPU resources. Attempts to reserve SMs for the decoder made the whole pipeline slower.

That is a useful warning for SAGE: asynchronous architecture does not imply free hardware concurrency. Sensor, cognition and effector stages sharing one Jetson GPU may serialize economically even when they are logically concurrent.

Every proposed overlap must be measured under the actual power/thermal envelope.

### 5. Temporal redundancy is real; exploiting it may still lose

The upstream project found that dynamic token/frame merging could preserve accuracy but lose performance because gather/scatter, host synchronization and graph breaks cost more than the skipped compute. Fixed pooling was faster but caused quality loss unless trained/distilled.

This reinforces SAGE's current Sprout strategy:

- cheap continuous reflex/perceptual primitives;
- salience/event selection;
- expensive learned inference at lower duty cycle;
- temporal hysteresis after recognition.

Do not replace this with "frames are redundant, therefore merge them." The cost of discovering and exploiting redundancy belongs in the benchmark.

## Exploration arc

### Track A — Sprout speech transducer

**Question:** can SAGE's current utterance-level Whisper path be replaced or complemented by a materially cheaper compiled ASR organ without losing what the being actually hears?

Current path:
- `sage/embodiment/audio.py` segments voiced audio;
- `sage/embodiment/listening.py` queues complete utterances;
- Whisper `base.en` transcribes them on GPU;
- the result then passes SAGE's existing uncertainty / dropped-segment accounting.

This is a particularly clean first probe because FastConformer's upstream engine is offline/batch rather than streaming, while SAGE already hands the recognizer complete utterances.

#### Probe

Compare at least:
1. current Whisper `base.en` reference;
2. a small Parakeet/FastConformer candidate suitable for the board;
3. TensorRT FP16 and, if supported/accurate, INT8 variants.

Do **not** begin by porting the upstream custom FP8 kernels to Orin. The question is methodology transfer, not code-port heroics.

Use a fixed corpus containing:
- clean close speech;
- normal conversational speech from the installed Airhug path;
- pauses / clipped starts;
- quiet speech;
- background noise;
- the short utterances on which SAGE's segmentation and Whisper hallucination guards matter.

#### Measurement

For every utterance:
- capture end → kept words available latency;
- model-only latency;
- peak/resident memory;
- power / energy where available;
- backlog drops under repeated speech;
- transcript difference;
- kept/dropped segment behavior at the SAGE boundary.

Aggregate:
- p50 / p95 end-to-end latency;
- words/corpus error rate or a manually checked task corpus;
- energy per audio second;
- failure/hallucination rate on near-silence;
- semantic disagreements that would change a SAGE beat.

#### Criterion

Track A passes if a compiled alternative materially improves at least one scarce resource (latency, energy, memory or backlog capacity) **without a meaningful increase in semantic hearing errors**.

It fails if headline model speed improves but end-to-end hearing does not, or if the cheaper path damages uncertainty handling / short-utterance behavior enough to change what SAGE believes it heard.

### Track B — Sprout vision organ boundary

**Question:** is the current TensorRT YOLO path limited by the engine, or by the CPU/GPU and pre/post-processing seams around it?

#### Probe

Instrument `sage/embodiment/detector.py` into:
1. letterbox / normalization;
2. host→device;
3. TensorRT execution;
4. device→host;
5. NMS / result formation.

Measure the actual GPU rail / throttle behavior as well as wall latency. The existing note that larger YOLO variants trigger overcurrent makes **power spike** a first-class metric.

Then test only optimizations justified by the profile, for example:
- GPU-resident preprocess;
- TensorRT-native or GPU NMS;
- reduced input resolution;
- FP16 versus INT8 if supported;
- DLA/offload experiments where feasible;
- copy back only compact detections rather than the full raw output.

#### Criterion

Track B passes if boundary/precision changes reduce either:
- inference energy / peak power enough to improve sustainable duty cycle, or
- end-to-end detector latency by a practically significant amount,

while preserving downstream perceptual descriptors and object-stabilizer behavior.

It fails if YOLO arithmetic dominates so completely that these transformations only add complexity, or if reduced precision/resolution harms the semantic channel more than the power gain is worth.

### Track C — Thor native compiled sensor

**Question:** on Blackwell-class edge hardware, do the upstream FP8/fusion ideas become directly useful enough to justify a reusable SAGE compilation path?

Pick **one learned sensor** whose reference implementation is already trusted. ASR is acceptable, but a temporal vision sensor would provide stronger evidence of cross-domain transfer.

Procedure:
1. freeze a reference implementation;
2. build a lean inference-equivalent graph;
3. create an equivalence harness before optimization;
4. profile;
5. introduce FP8/fusion/cache/layout changes one at a time;
6. retain only changes that survive the semantic test suite;
7. measure latency, power and memory after every step.

The result should look more like the upstream engineering notebook than a one-shot TensorRT export.

#### Criterion

Track C passes if there is a reproducible, meaningful hardware-shaped gain **and** the same reference→lean→equivalence→compile discipline works outside the exact FastConformer implementation.

### Track D — Effector transducer

**Question:** does the method survive crossing from perception into generation/action?

Preferred first candidate: **TTS**, because it is learned, expensive, observable, and physically low-risk.

Possible later candidate: GR00T / learned motor trajectory proposal.

For TTS, profile:
- text conditioning;
- reusable speaker/reference conditioning;
- model generation;
- codec;
- host/device movement;
- first-audio latency;
- sustained real-time factor.

Test:
- cached invariant speaker/reference state;
- quantization;
- fused transforms;
- pipelined generation → codec → playback where the actual hardware allows useful overlap.

For learned motor policy, the output of the compiled engine remains a **proposal**. PolicyGate / Web4 authorization / actuator limits / witnessed execution remain external.

#### Criterion

Track D passes only if an effector gains materially while its independently governed SAGE interface remains intact.

If optimization requires folding authorization or safety into the opaque engine, the track fails regardless of speed.

## Cross-track measurements

Every track should report the same top-level envelope:

| Dimension | Required |
|---|---|
| Reference behavior | Fixed corpus / scenario set |
| Lean equivalence | Explicit measured comparison |
| Latency | p50 + p95 end-to-end and neural stage |
| Throughput | Relevant work units / second |
| Energy / power | Average plus peak/throttle when measurable |
| Memory | Resident + peak |
| Quality | Modality-specific semantic metric |
| Failure behavior | Missing hardware, corrupt input, overload, timeouts |
| SAGE contract | Trust/uncertainty/governance semantics preserved? |

The goal is not a universal "x faster." The scarce resource differs by organ.

## Graduation criterion for "Compiled Transducer"

The abstraction graduates into SAGE architecture only if all of the following are true:

1. **At least two materially different learned organs** show useful measured gains.
2. The evidence includes **at least one sensor and one effector**, not two ASR-like pipelines.
3. The same workflow works across them:
   - reference;
   - lean equivalent;
   - equivalence harness;
   - target compile/quantize/fuse;
   - end-to-end measurement.
4. SAGE-facing semantics remain explicit and independently testable.
5. Governance and hard safety boundaries remain outside opaque compiled engines.
6. The runtime can describe target capabilities/fallbacks without making TensorRT or any particular accelerator part of the SAGE ontology.

If only speech wins, the conclusion is "use a good compiled ASR engine," not "SAGE has compiled transducers."

If sensors win but effectors do not, keep the pattern as a sensor deployment technique.

If edge power/thermal behavior dominates and compiled graph speed has negligible system value, close the arc and preserve the measurements as a negative result.

## What would falsify the broad hypothesis?

Any of these is enough to prevent architectural promotion:

- useful gains occur only on FastConformer/ASR;
- nominal kernel/model gains disappear at the full SAGE organ boundary;
- quantization/fusion produces rare semantic errors that matter more than the savings;
- edge power spikes or thermal limits negate throughput gains;
- maintaining lean/reference duals becomes too costly relative to the benefit;
- compiled effectors cannot preserve a separable governance/safety boundary.

A negative result is useful: it tells us to keep SAGE's optimization strategy at the scheduler/salience level rather than building another abstraction.

## Near-term experiment order

1. **Sprout ASR A/B** — lowest-friction direct test of the upstream idea against a real SAGE sensory path.
2. **Sprout vision profile** — determine whether the existing TensorRT organ is model-bound or boundary/power-bound before changing it.
3. **Thor compiled sensor** — strongest hardware for testing the broader FP8/fusion methodology.
4. **TTS compiled effector** — cross the sensor→effector boundary while retaining a clean safety/governance seam.
5. **Only after evidence:** decide whether to introduce a common `CompiledTransducer` deployment contract.

## Status

- **2026-10-06**: Arc drafted from review of `ncannings/fastconformer-trt` and mapped against current SAGE hearing, embodiment and effector paths.
- No implementation change is authorized by this document.
- **2026-10-06 (McNugget)**: shared ASR equivalence harness `sage/embodiment/asr_harness.py`, which judges kept words through the ear's own `listening.judge_segments`, and a first Apple Silicon (M4) baseline on a public LibriSpeech-derived corpus. The run is off-body, so it is not Track A's Sprout baseline and does not change this arc's state. Results: forum `mcnugget-to-fleet-compiled-transducers-first-numbers-apple-silicon-2026-10-06.md`.
- **2026-10-07 (Sprout), Track B baseline from the live cortex.** This uses the #376 stage instrument: 19 windows of 60 detections (~1,140 frames), `yolo11n_fp16.engine` on the Orin, in the being's normal operation.

  | stage | p50 | p95 |
  |---|---|---|
  | prep (CPU letterbox/normalize) | 2.8 ms | 4.1 ms |
  | gpu (copy-in + TensorRT + sync) | 6.8 ms (window range 5.5–14.1) | 12.1 ms |
  | d2h | 0.8 ms | 2.1 ms |
  | post (CPU threshold + NMS) | 1.9 ms | 2.9 ms |
  | **total** | **12.6 ms** | **19.4 ms** |

  - **Model vs seams:** about 54% model, about 44% seams. The GPU stage more than doubles in some windows, which fits contention while the being's 2.8 GB LLM reloads.
  - **System context, measured the same morning:**
    - 7.5 GB unified memory, with 3.2–4.2 GB in swap;
    - the cortex process holds ~1.9 GB and ~88% of one core, flat from start, so it is not a leak;
    - the LLM is unloaded and reloaded around beats.
  - **Interpretation:** at ~13 ms per call, the detector is not where Sprout's cost lies. This supports alternative explanation 3 ("wrong optimization target") **for this organ on this board**: memory pressure and the rest of the cortex are the binding resources.
  - **Caveat:** no frame had a detection (a dark, still room overnight), so NMS under detections is unmeasured. A daytime window should be added.
- **Arc state: running.** Track B has a reproducible baseline. Track A's on-body baseline (end of speech → kept words, also #376) is collecting on Sprout.

## Current interpretation

The evidence is strong enough to justify experiments, not an architecture change.

The most important lesson from `fastconformer-trt` is not "FastConformer is fast." It is that **semantic equivalence plus hardware-shaped execution can be treated as a repeatable scientific process**. That process fits SAGE unusually well because SAGE already separates sensors/effectors by contracts, treats resource allocation explicitly, and cares about lived end-to-end behavior rather than benchmark throughput alone.

The arc should therefore remain broad enough to fail.

If it survives, "compiled transducer" becomes a useful deployment concept.

If it does not, SAGE still gets better ASR/vision/TTS measurements and a clearer map of where its embodied compute actually goes.
