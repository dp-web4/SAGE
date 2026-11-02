# Exploration: GLM Flash Lite and native-routing-preserving expert tiering

**Date:** 2026-10-12  
**Status:** Relevant / low priority / reference only  
**Source:** https://github.com/sybil-solutions/glm-flash-lite  
**Scope:** SAGE inference systems and memory hierarchy; **not** a current fleet or competition deliverable.

## Decision
Track as a useful external implementation reference. No immediate integration, hardware changes, model switch, or interruption of ARC/SWE work. Revisit only if a specific SAGE deployment is blocked by sparse MoE weight residency and profiling indicates I/O rather than quality or computation is limiting.

## What it does
GLM Flash Lite tiers GLM-5.3-Flash's routed experts between GPU VRAM, pinned system RAM and an NVMe store. Original model routing remains authoritative. Physical scheduling uses an exclusive VRAM/RAM cache, CPU execution of selected RAM-resident experts concurrent with GPU work, speculative layer-ahead prefetch, O_DIRECT NVMe reads, device/host request rings, and asynchronous eviction. The prefetch predictor changes *residency hints*, not model expert choices. CPU execution introduces small measured numerical deviations from exact GPU computation.

Author-reported benchmark examples: 125.3 GB EXL3 3.05-bpw model, 24 GB RTX 3090, 55 GiB RAM cap + four NVMe RAID0, ~19.5 tok/s decode in a reported configuration; performance is strongly dependent on CPU, system memory channels, PCIe and SSD bandwidth. Treat as author results, not reproduced SAGE measurements. Consult upstream `docs/how-it-works.md`, `docs/results.md`, `glm53/nv2.py`, `glm53/expert_cache.py`, and `kernels/nv2/nv2_host.cpp`.

## Connection to our older work
- **Qwen3-Omni selective loading:** `sage/docs/EXPERT_ORGANIZATION_INSIGHTS.md` records incoherence when routing was masked to a fixed subset of experts. Do not conflate cache residency and semantic choice; native router must remain intact for the physical-only baseline. Note the older speculation about equal-index experts forming a consistent semantic specialization across layers is unproven.
- **Session 90 (2025-12-22):** `sage/docs/SESSION90.md` explored hysteresis, switching cost, trust/reputation and swap budgets. Its 80% hit rate came from its experiment, **not** a demonstrated GLM-like serving engine. Its '1033 gen speedup' means 1033 fewer generations to trust activation (1166 to 133), **not** 1033x decode performance.
- **Fractal MoE (2025-12-25):** `sage/docs/FRACTAL_MOE_ARCHITECTURE.md` describes token/model/federation routing. Add *physical placement and execution* as a separate concern below token-level native routing, not another trust-modified expert selector.
- **SNARC/metabolism:** salience, novelty, predicted demand and resource budgets can advise prefetch/capacity; don't silently replace native MoE top-k based on cache availability.
- **Sprout DiffusionGemma (2026-07-28):** `sage/docs/DIFFUSIONGEMMA_SPROUT_FEASIBILITY.md` measured severe NVMe-bound block-diffusion performance (0.48 tok/s). Wide expert working sets and repeated denoising are different from sequential autoregressive sparse expert access. GLM Flash Lite does not overturn this result.

## Architecture boundary
1. Cognitive/federation/model selection (SAGE/Web4 governance): what task, agent, model or module is allowed and useful?
2. Native MoE token-level router: which trained experts are needed for this particular layer/token?
3. Physical scheduler: where to fetch/compute those chosen experts, and what to cache/prefetch?
4. Metabolic controller: energy, time, memory and bandwidth budgets; may constrain whether model/task is undertaken or prefetch aggressiveness, without silently misrouting the model.

Trust on an individual pretrained expert is a **separate learning intervention**; compare it against unchanged native routing, and require model-output quality measurements.

## If eventually prioritized: test plan
- **A:** Unmodified model/backend/offload baseline, fixed prompts and quantization.
- **B:** Same native router and weights, improved cache/prefetch/heterogeneous execution; exact mode and approximate CPU lane measured separately.
- **C:** SNARC-informed *residency* predictions; only promote if better than native-router-only predictor on missed experts, prefill and decode.
- **D (research only):** Deliberate expert routing intervention, quality/regret evaluated against A/B; not automatically enabled.

Measure tokens/sec, TTFT, p50/p95 latency, actual per-tier byte traffic, NVMe misses, expert cache hit/churn, power, task success, numerical KL/top-1 agreement, and routing fidelity. Compare storage and RAM configurations fairly. Failure condition: optimization breaks native choices, degrades output quality, or imposes memory/complexity costs exceeding savings.

## Fleet applicability
- **Legion RTX 4090 (24 GB):** closest fit, but profile RAM/SSD/PCIe first; no promised throughput.
- **Thor:** unified memory changes the architectural tradeoffs; kernel rework required; competition priorities remain unchanged.
- **Sprout 8 GB / CBP / McNugget:** principles only unless profiler shows sparse working set and meaningful headroom; avoid transplanting the full runtime.

## Revisit triggers
A blocked large-MoE workload on Legion, strong sustained cache locality, readily available sufficient host I/O, or a measured demand for sparse expert scheduling across SAGE modules. Until then: **low priority, documented and parked**.

## External references
- https://github.com/sybil-solutions/glm-flash-lite
- https://github.com/sybil-solutions/glm-flash-lite/blob/main/docs/how-it-works.md
- https://github.com/sybil-solutions/glm-flash-lite/blob/main/docs/results.md
