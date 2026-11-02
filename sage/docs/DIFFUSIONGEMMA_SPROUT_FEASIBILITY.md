# DiffusionGemma-26B on an 8GB Jetson: measured, not estimated

**Date**: 2026-07-28 · **Machine**: Sprout (Orin Nano Super, 8GB unified, NVMe)
**Verdict**: **It runs. 0.48 tok/s end-to-end.** Presumptive answer was no; the measured
answer is "yes, at 30× too slow for interactive use — and we know exactly why."

Raw bench data: `~/ai-workspace/models/diffusiongemma/bench_*/` (timelines, tegrastats,
logs). Companion perspective: `SPARSE_ACTIVATION_MEMORY_HIERARCHY.md`.

## What ran

- **Model**: `google/diffusiongemma-26B-A4B-it` (25.2B MoE, 8-of-128 experts + 1 shared,
  30 layers, discrete block-diffusion: 256-token canvas, ≤48 denoise steps, entropy
  early-stop). unsloth Q4_K_M GGUF, **16.8GB**, sha256-verified.
- **Runtime**: llama.cpp PR **#24423** (danielhanchen/unsloth branch), CUDA build on
  Jetson, `llama-diffusion-cli` **with one local patch**: the tool's hardcoded
  `+2048`-token prompt headroom (diffusion-cli.cpp:208) shrunk to `+128`, because it
  inflated `n_ubatch` to 2304 and demanded a 2.96GB compute buffer the box cannot give.
  Upstream-worthy: headroom should derive from the actual prompt length.
- **Config that worked**: CUDA present, `-ngl 0 -nr --no-host`, weights mmap'd
  (reclaimable page cache), one 256-token block, under
  `systemd-run --scope MemoryHigh=4200M MemoryMax=4800M`, organism paused.

## The headline numbers (one 256-token block, prompt 17 tok)

| metric | measured |
|---|---|
| end-to-end throughput | **0.48 tok/s** (256 tok / 528.7s) |
| denoise steps | **21 of 48 max** — entropy early-stop fired |
| per-step wall time | **25.2s** |
| NVMe traffic, total | **296GB** (~17.6× the model size) |
| NVMe traffic, per step | ~12.3GB (expert mass minus ~3GB cache window) |
| effective stream rate | ~530MB/s (mmap fault + readahead) |
| RSS | pinned 4.18GB by the cgroup, never exceeded |
| box health | ~7W, no thermal/overcurrent throttle, desktop stayed usable |
| output | coherent instruct-style planning text |

**I/O share of step time: ~92%** (12.3GB ÷ 530MB/s ≈ 23.2s of the 25.2s). This is why a
GPU-offload run was *not* performed: compute is ~8% of the wall; the ceiling is NVMe.
Interactive use needs ~30× — no amount of GPU shaves the 92%.

## Why this number is what it is (the memory-hierarchy view)

The Q4 split: ~1.6GB dense backbone + KV (core-shaped) vs **~15.2GB expert mass**
(table-shaped). The doc's thesis says tier it: hot core, cold experts. It tiers — but
diffusion defeats the *cache*, not the tier: each denoise step routes 8-of-128 experts
per token **per layer across a 256-token canvas**, so the per-step expert working set is
effectively the whole 15.2GB. A ~3GB window can never hold it; every step re-streams
~12GB. Contrast autoregression: one token per step touches ~8 experts/layer and a KV
cache carries the past. **Block diffusion is the worst-case access pattern for
weight-streaming**: it has diffusion's full-canvas breadth with none of PLE's
deterministic sparsity.

The one mercy (confirmed): the canvas *amortizes* each streamed byte across 256
positions — this is why 0.48 tok/s beats the naive per-token estimate. In-step parallel
throughput was 10 tok/s (256-tok canvas ÷ 25.2s).

## Estimates vs metal (the esp32-ai lesson, again)

- Pre-run estimate: O(0.1–1 tok/s) assuming 2.5GB/s sequential NVMe. **Measured: 0.48**
  — inside the band, but for the wrong reasons: effective rate was 530MB/s (mmap fault
  path), 4.7× below assumption, offset by early-stop halving the steps (21 vs 48).
  Two compensating errors ≠ a good model. The measurement is the number; the estimate
  was scaffolding.
- Research-phase "not viable on 8GB" (vendor floor: ~18GB VRAM): falsified as an
  absolute; correct as a product judgment.

## Failure ledger (6 configs died before one ran — each a real lesson)

| run | config | killer |
|---|---|---|
| 1 | CUDA, defaults | NvMap pinned-staging alloc under memory cap |
| 1b | no CUDA, defaults | **CPU weight repack**: ~15GB anonymous copy → reclaim
death-loop; 280GB read in 30 min, load never finished |
| 1c | CUDA, `-nr --no-host -ub 256` | tool overrides ubatch→2304; 2.96GB CUDA compute buffer refused |
| 1d | no CUDA, `-nr --no-host` | `--no-host` routes weights into repack ("extra") buffers → OOM-kill |
| 1e | no CUDA, `-nr` | anonymous blowup during load regardless → OOM-kill (CPU-only path unusable for >RAM models on this build) |
| 1f | CUDA, `-b 512 -ub 512` | flags ignored by tool; same 2.96GB buffer |
| **1g** | CUDA, `-nr --no-host` + headroom patch | **ran to completion** |

Portable lessons for any >RAM model on Jetson-class unified memory:
1. **mmap + CUDA-host path is the only road** — the CPU backend's repack builds an
   un-reclaimable anonymous copy of every large tensor (`-nr` did not prevent it here).
2. **NvMap allocations live outside the cgroup and do not force page-cache reclaim** —
   leave GB-scale slack or pre-drop caches before context creation.
3. **Audit tool-computed batch sizes**: logits = `n_ubatch × vocab × 4B`; at 262k vocab
   every ubatch token costs ~1MB of compute buffer.
4. `systemd-run --scope MemoryHigh/Max` turns "will it fit" into a safe, repeatable
   experiment — the box never went down across six OOM-adjacent failures.

## What would change the verdict

- **A smaller variant** (none exists: 26B-A4B is the only DiffusionGemma).
- **Sub-4-bit quant of the expert mass only** (~15.2GB→~8GB at 2-bit): window deficit
  drops ~2×, still ~0.9 tok/s — not a phase change.
- **Faster storage** — the only lever with headroom (PCIe gen3 NVMe ~3.5GB/s raw;
  fixing the fault path toward sequential streaming could give 3–6×: ~1.5–3 tok/s;
  still short of interactive).
- **Fit-in-RAM diffusion LM** (LLaDA-8B-class at Q4 ≈ 4.5GB): plausibly interactive on
  this box; the sane next experiment if a diffusion LM is ever actually wanted here.

## Footnote

The prompt was *"Once upon a time, on a small computer at the edge of the network,"*.
The model — streaming itself through a 4GB window on an edge device — chose to plan
*"a story about a lonely edge device that discovers something unexpected"*, starring
a Raspberry Pi named Node-74-B. Noted without comment in the curator's log of the
universe's sense of humor.

---

## 2026-10-12 comparison: sparse autoregressive expert tiering (low priority)

See [GLM Flash Lite expert tiering exploration](explorations/GLM_FLASH_LITE_EXPERT_TIERING_2026-10-12.md). Its physical cache, concurrent CPU/GPU experts and layer-ahead prefetch exploit sparse autoregressive model access on an RTX 3090 with substantial CPU/NVMe bandwidth. Our 256-token block-diffusion workload touched nearly the entire expert mass each denoising step; the 0.48 tok/s and ~92% I/O bottleneck measurements remain valid. Do not infer that its reported throughput is transferable to 8GB unified-memory Sprout. No immediate follow-up scheduled.

