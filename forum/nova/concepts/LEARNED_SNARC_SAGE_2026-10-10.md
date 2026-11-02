# Learned SNARC — SAGE integration exploration (2026-10-10)
**Status:** proposal; existing SAGE SNARC implementations are not being replaced here.

## Why
Typed decision inference is becoming inexpensive enough for frequent attention selection. But SAGE's target is *outcome-calibrated allocation of cognition across sensor, effector, memory, MRH and puzzle tiles*, not a yes/no relevance API. Preserve the five-dimensional SNARC vector and the IRP-key (salience metadata, not necessarily raw values) boundary described in [SNARC specification](../../claude/SAGE/SNARC_SPECIFICATION.md) and [NOVA SAGE–SNARC discussion](SAGE-SNARC.md).

## Existing SAGE surfaces to audit
- `sage/attention/snarc_scorer.py`: neural hidden-state scorer and attention bias; this is an existing learned-capable substrate, not a new proposal.
- `sage/attention/experience_salience.py`: algorithmic experience scores.
- `sage/attention/sensor_snarc.py`: per-sensor and spatial maps.
- `sage/raising/training/experience_collector.py`: conversational salience and deduplication.
- `sage/embodiment/salience.py`: embodied prediction errors, habituation, visual/IMU conflict.
- `sage/services/snarc/snarc_service.py`: service-level attention.
- Standalone `dp-web4/snarc`: hook/capture and memory tier lifecycle; June 2026 crossfeed audit identifies divergent dimension weights and behavior.

## Proposed architectural path
IRP observation (key + bounded history + MRH context) → deterministic safety/quality filters → learned 5D SNARC with confidence, attention-mode and abstention → SAGE attention/puzzle allocation and appropriate reasoning effort → subsequent experience/outcomes → versioned training/evaluation evidence. Spatial attention stays spatial when necessary; adapters must not destroy modality shape. The model may recommend deeper reasoning or observation, *never permissions*. Hestia/Web4 enforce real action authority. Where R6 enters, use Web4's actual **Rules + Role + Request + Reference + Resource → Result**, not invented shorthand.

## Immediate experiments
Inventory field semantics and reward definitions; instrument event-to-delayed-outcome joins without leakage; benchmark algorithmic vs existing neural vs tiny MLP/temporal model vs hybrid; train first as heuristic imitation then against evidence-backed delayed utility. Evaluate rare high-consequence missed events, contradiction detection, stale memory, compute/energy and calibration/abstention. Run shadow mode on a small fleet node before anything can change attention allocation.

Full requirements, risks, milestones, data provenance and acceptance gates: [SNARC PRD](https://github.com/dp-web4/snarc/blob/main/prd/LEARNED_SNARC_PRD_2026-10-10.md). Coordinate with dev-SAGE for ARC/SWE competition-specific ablations.

**No implementation or training results are asserted by this note.**
