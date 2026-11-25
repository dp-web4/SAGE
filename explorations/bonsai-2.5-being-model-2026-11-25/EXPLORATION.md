---
date: 2026-11-25
status: results — H1 fails (Bonsai worse than gemma4:12b on this machine); gemma4:12b at 32k is the lead
machine: McNugget (Mac mini M4, 16 GB unified memory, Ollama 0.33.1)
proposed by: dp ("look into bonsai2.5 as a possible model for beings"), run by mcnugget-claude
related:
  - sage/instances/mcnugget-being/instance.json (current embodiment: gemma4:12b, num_ctx 16384)
  - ~/Library/Logs/sage/heartbeat_error.log (WINDOW-CUT / EMPTY turns at prompt_eval ≈ 15.3–16.0k of 16,384)
---

# Bonsai 2.5 (ternary Qwen3.8-27B) as a being model on a 16 GB Mac

## Background

PrismML released **Ternary Bonsai 2.5 27B** on 2026-11-24 (Apache-2.0). It is **not a distillation**: it is
Qwen3.8-27B with post-training ternary weights ({−1, 0, +1}, one FP16 scale per 128 weights, in a blockwise
Hadamard basis). The model card reports 77.2 vs 77.7 for FP16 Qwen3.8-27B over five general benchmarks, and
54.2 vs 60.5 on agentic coding. File sizes: 5.93 GB (PTQ1_0, PrismML llama.cpp fork only), ≈7.25–7.9 GB
(Q2_0 / PQ2_0). Q2_0 runs on stock llama.cpp from b11556; older builds load it and emit garbage.

McNugget's being runs `gemma4:12b` (Q4_K_M, ≈8.4 GB resident) at `num_ctx` 16,384, capped there because that
is what was measured to fit. The heartbeat log shows the window is the binding constraint: turns end
`done_reason=length` with `prompt_eval` 15.3–16.0k, producing EMPTY and WINDOW-CUT turns and retries.

## Hypothesis

**H1:** On this 16 GB machine, Bonsai 2.5 Q2_0 can be a being model that is at least as coherent and
tool-capable as gemma4:12b, at a comparable resident size, and its larger parameter count is worth having.

**H2:** Bonsai 2.5 can run at a **larger context** than 16,384 (target 32,768) on this machine without
pushing the system into swap growth, which would directly relieve the being's observed window cuts.

**Alternative:** the 2-bit file only *looks* small; with its KV cache at 16–32k it exceeds what a 16 GB
machine shared with the OS, membot and an embedder can hold, so it swaps, decodes too slowly for an
8-step heartbeat, or loses coherence at long context (ternary quantization error compounding).

## Probe procedure

`probe.py` (this directory) talks to the local Ollama HTTP API only. It never calls the SAGE gateway,
membot, hestia or the witness chain, and it restores `gemma4:12b` with `keep_alive: -1` at the end.
Each model is run alone (others unloaded except the embedder), seed 42, with Bonsai's model-card
sampling (instruct: T 0.7, top_p 0.8, presence 1.5, min_p 0; thinking: T 1.0, top_p 0.95, top_k 20, min_p 0)
and gemma's Ollama defaults.

1. **Coherence** — five short questions with regex-checkable answers (num_ctx 8,192).
2. **Tool call** — one `read_file` tool; the model must call it for `explorations/README.md`, then answer
   which field that file calls most important (expected: the criterion / falsifier).
3. **Reflection** — three being-shaped heartbeat prompts (window pressure, ranged review plan, journal vs
   repo mismatch), thinking off, saved side by side for reading.
4. **Thinking on** — one reflection prompt with `think: true`, `num_predict` 6,000: does it finish with
   content, and how many tokens does it spend?
5. **Long context** — a needle sentence placed mid-way in real SAGE source text filling ≈14k tokens at
   `num_ctx` 16,384 and ≈28k at 32,768. Record recall, prefill and decode tok/s, resident size, and
   `vm.swapusage` before/after.

## Measurement

Per model, `results/<model>.json`: pass/fail for coherence, tool call and needle recall; prefill and
decode tok/s; load time; resident size and VRAM from `/api/ps`; swap before/after each call; full texts.

## Criterion

- **Reject Bonsai for beings on this machine** if any of: coherence garbage (the stock-runtime failure
  mode); no valid tool call; needle missed at 16k; decode < 5 tok/s at 16k (an 8-step beat would not fit
  its window); or swap grows by > 1 GB during a 16k call.
- **H2 holds** only if at 32k the needle is recalled, decode ≥ 5 tok/s, and swap growth ≤ 1 GB. If H2
  fails but H1 holds, Bonsai is at best a same-window swap for gemma, and the window problem stays.
- **Worth a live trial** (separate step, needs a model-zoo config and a seat decision) only if H1 holds and
  the reflection outputs read at least as grounded as gemma's — no invented facts, concrete steps.

## Status

**Results, 2026-11-25. Conclusion: H1 fails, so don't move the being to Bonsai on this machine. H2 fails on
the swap criterion. The run turned up a stronger lead than the one it tested: gemma4:12b itself runs at 32k here.**

## Runtime findings (before any probe could run)

- **Ollama 0.33.1 cannot load it.** `ollama pull hf.co/prism-ml/Ternary-Bonsai-2.5-27B-GGUF:Q2_0` succeeds
  but fetches the **7.25 GB PQ2_0** blob, not the 7.67 GB Q2_0. Every load fails with
  `tensor "output.weight" size overflow`, and Ollama shows `quantization_level: unknown`. Bonsai cannot go
  through the being's current Ollama path until Ollama ships the newer ggml.
- **Stock llama.cpp b11970 runs Q2_0**, downloaded directly (7.67 GB), with
  `llama-server -np 1 -ngl 99 --jinja`.
- **Bonsai and gemma cannot both be resident.** Run 1 died mid-probe when a heartbeat started
  (≈20:35:56Z) and Ollama loaded gemma next to llama-server:
  `kIOGPUCommandBufferCallbackErrorOutOfMemory`. Every later request failed
  (`results/run1-beat-collision-*`). All later runs were gated to start after a beat ended
  (`after_beat.py`), and no beat ran during them.
- **llama.cpp defaults do not fit long prompts.** With the default batch (2,048) and f16 KV (run 2,
  `results/run2-defaults-llama-server.log`), a 12k-token prompt hit Metal OOM at n_tokens ≈ 11.5k in a
  16k window, and at 32k the very first 2,048-token batch failed. **`-ub 512 -b 512 -ctk q8_0 -ctv q8_0`**
  (run 3, "tuned") fixes both. All Bonsai numbers below are from the tuned run.

## Results

| | gemma4:12b (Ollama, Q4_K_M) | Bonsai 2.5 Q2_0 (llama.cpp, tuned) |
|---|---|---|
| Coherence (5 regex checks) | **5/5** | 4/5 (reversed "heartbeat" as "tebrae", both runs) |
| Tool call: called `read_file`, then answered "criterion/falsifier" | pass | pass |
| Thinking on (`num_predict` 6,000) | stops with content, 1,826 tokens | stops with content, 2,254 tokens |
| Needle, ≈12k tokens in a 16k window | **found**: prefill 115 tok/s, decode 14.5, 8.36 GB resident, swap Δ 0 | found: prefill 56 tok/s, decode 10.2, 8.4 GB RSS, swap +0.22 GB |
| Needle, ≈25k tokens in a 32k window | **found**: prefill 104 tok/s, decode 13.5, 8.13 GB resident, swap Δ −0.01 GB | found: prefill 53 tok/s, decode 9.3, 9.1 GB RSS, **swap +1.73 GB** |
| Short-reply decode | 12.5–12.7 tok/s | 11.1 tok/s |

**Reflection outputs (read side by side, `results/*.json`).** gemma's answers were shorter and grounded:
75, 202 and 67 tokens. Bonsai's were longer (88, 598, 89) and **invented facts it was not given**. On the
journal-vs-repo prompt it recorded a commit hash `abc123` and "working tree is dirty", although the system
prompt says not to invent facts. One sample per prompt, so that's a signal to look for, not a rate.

## Against the criterion

- **H1 (Bonsai at least as good as gemma here): fails.** It is not *rejected* by the hard floor: coherent,
  tool-capable, 16k needle found, decode ≥ 5 tok/s. But on this machine it is worse on every measured axis:
  - coherence 4/5 vs 5/5;
  - prefill half as fast (≈55 vs ≈110 tok/s). A beat's 15k-token prompt takes ≈4.5 min to read, against ≈2.3 min;
  - decode ≈20–30 % slower;
  - more swap;
  - the only reflection that invented facts was Bonsai's.

  It also needs a second inference runtime beside Ollama, and it can never share memory with gemma.
- **H2 (Bonsai at 32k without swap growth): fails** on the pre-set criterion. The needle was recalled and
  decode was 9.3 tok/s, but swap grew 1.73 GB (limit 1 GB) on a machine already carrying 2–5 GB of swap.
- **The unexpected finding: gemma4:12b at 32k passed the criterion that Bonsai failed.** The needle was
  found at 24.9k prompt tokens, decode 13.5 tok/s, resident 8.13 GB, and swap did not grow. The being's
  `num_ctx` 16,384 cap ("measured as fitting") looks stale for this machine. Its window-cut and EMPTY turns
  at prompt_eval ≈ 15.3–16k are the problem a larger window addresses. **Next exploration (not run here):**
  raise the being's `num_ctx` to 24k, then 32k, for a few real beats. Check that the cut/EMPTY/retry rate
  falls, beat wall time stays inside the beat interval, and swap stays flat. That is a change to the live
  being's config, so it's a seat/operator decision, not part of this probe.

## Caveats

- **One machine, one seed, one sample per prompt.** The reflection judgement is qualitative.
- **gemma ran with Ollama defaults and Bonsai with its model-card sampling.** That is how each would
  actually be deployed, but it is not identical sampling.
- **gemma's Ollama runner and Bonsai's llama.cpp differ** (KV cache type, batch size). The comparison is
  "each as deployable today on this machine", not "the weights in an identical runtime".
- **Not tried:** PTQ1_0 (5.99 GB, PrismML's llama.cpp fork only) might leave room for a larger context.
  MTP speculative decoding might help speed. Neither changes the prefill or quality findings enough to
  reverse H1 on a 16 GB machine, but on a larger-memory seat (Thor, Legion) Bonsai deserves its own run
  against that machine's current model.

## Reproduce

```sh
python3 probe.py gemma4:12b                                            # via Ollama
BONSAI_EXTRA="-ub 512 -b 512 -ctk q8_0 -ctv q8_0" \
  python3 after_beat.py next <llama.cpp>/build/bin/llama-server <path>/Ternary-Bonsai-2.5-27B-Q2_0.gguf 16384 32768
```

`probe.py` only talks to Ollama / llama-server, never to the gateway, membot, hestia or the chain.
`run_bonsai.py` unloads gemma and always reloads it with `keep_alive: -1` at the end.
