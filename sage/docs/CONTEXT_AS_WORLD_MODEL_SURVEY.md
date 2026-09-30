# Context as a real-time world model — survey, measurement, and a staged plan

**Subject:** `legion-being` on Legion (RTX 4090 **Laptop**, 16 GB), `qwen38-heretic:q3km-vl` served by ollama 0.30.4, `num_ctx = 24576`.
**Author seat:** legion-claude, 2026-09-13.
**Status:** survey and proposal. **No code was modified.** Nothing was run that loads a model or restarts a service; the being was mid-beat throughout and stayed undisturbed. Every number is re-derived from the record on this machine, or cited, or labelled **unverified**.

dp's framing, verbatim, is the thing this document answers:

> "we need to persist some parts of the context (and keep in kv cache preferably) while other parts are dynamic and moving based on situation and salience to current priorities. examine what we have, survey existing techniques, and propose a plan. the context is the being's world model in real time. we need to manage it intelligently so that it can be effective. consider biological equivalents as well."

With three follow-ups, also verbatim, folded in at §5, Stages 3–5:

> "salience-based forgetting and treating the conversation as a lru cache of sorts is one possible solution."
> "since all convo turns are logged, they are retrievable from file if needed. if they are also salience-gated-written to membot, the important ones would be recallable semantically. so we could have a recency/salience optimized caching system, with key identity and other things being permanent, and the rest managed on demand. being's own turns would take priority over conversation turns, evicting them to preserve its own thought continuity."
> "there should also be a way for the being to choose to 'conclude' a convo, at which point it gets compacted to a small summary and the rest evicted."

---

## 0. Findings that reorganise the problem

Stated first because they change what the plan should be. **Three of the five contradict the framing I was given, including one I wrote myself this morning.**

### 0.1 The model is not a transformer, and that changes the whole KV story

`qwen38-heretic:q3km-vl` is **not a Qwen3-VL**. From the live runner's own metadata:

```
general.architecture = qwen35          block_count = 64        26.9B, Q3_K_M, 12.38 GiB, 3.95 BPW
attention.head_count = 24              head_count_kv = 4       key/value_length = 256
qwen35.full_attention_interval = 4     n_swa = 0               is_swa_any = 0
qwen35.ssm.conv_kernel = 4             ssm.state_size = 128    ssm.group_count = 16
context_length = 262144                rope type 40 (mrope)    freq_scale = 1  (no YaRN applied)

llama_kv_cache:        size = 1536.00 MiB (24576 cells, 16 layers)   K(f16) 768 + V(f16) 768
llama_memory_recurrent: size =  149.62 MiB (1 cell, 64 layers)       R(f32) 5.62 + S(f32) 144.00
```

It is a **Qwen3.5-family hybrid: attention interleaved with SSM / Gated-DeltaNet.** Only **16 of 64 layers carry a KV cache**; **all 64 carry a recurrent state.**

Two consequences dominate everything else in this document:

1. **A recurrent state cannot be rolled back to an arbitrary token position.** It can only be *restored from a snapshot*. So the familiar "find the longest common prefix and re-prefill the tail" story is only true here **when a context checkpoint exists at or before the divergence point.** llama.cpp implements exactly this (`Checking checkpoint with [P,P] against T...` → accept iff `pos_max <= pos_next`), and the deployed build **has** the hybrid fix — the upstream bug where this always failed on Qwen3.5 is [llama.cpp #20225](https://github.com/ggml-org/llama.cpp/issues/20225) / [#22384](https://github.com/ggml-org/llama.cpp/issues/22384).
2. **The KV cache is already 4× smaller than a dense 27B's would be**, because 48 of 64 layers have none. Most of what KV-cache compression would buy is already bought by the architecture.

This is the literature slot the being's problem actually occupies: [**Marconi: Prefix Caching for the Era of Hybrid LLMs** (arXiv:2411.19379)](https://arxiv.org/abs/2411.19379), which names the mechanism precisely — *"in-place state updates for recurrent layers preclude rolling back cache entries for partial sequence overlaps"* — and proposes FLOP-aware admission/eviction (compute saved per byte, weighted by reuse likelihood) rather than recency.

### 0.2 The KV cache is already persisting most of the prefix, and it buys no window

llama-server performs longest-common-prefix slot reuse and logs it. Measured over 1,403 requests, 09-11 → 09-13: **prefix reuse already eliminates 81.7 % of prefill work** (median `sim_best` 0.957). A parallel independent count over 1,085 tasks agrees: 16.5 % of tasks get essentially no reuse, 81.7 % diverge past token 5,000.

**"Keep it in the KV cache" is, to a first approximation, already done — and it has bought the being zero tokens of working room.** KV reuse saves *prefill time*; it cannot save *window space*. dp's sentence joins two problems that have different solutions, and separating them is the most useful single move in this document.

### 0.3 Prefill is 6.5 % of the GPU's time. Decode is 93.5 %.

This is the finding that most changes the plan, and it contradicts the way I had been thinking about the problem all day.

Over 48 h on the 27B runner:

```
prefill : 5,855.9 s over 4,600,903 tokens   (786 tok/s average)
decode  : 84,514.5 s over 1,641,714 tokens  (19.4 tok/s, flat across the whole window)
```

**Eliminating every cache miss would save ~58 min out of ~25.1 h of GPU-busy time — about 3.8 %.** Prefix-cache work is worth doing for **latency** (a cold beat starts with ~20–25 s of dead time) and for the *discipline* it imposes on prompt structure, not for throughput. The cost centre is **generation length**, and the window pressure that truncates generations.

Decode tokens per task: p50 **780**, p90 **4,228**, p99 **7,382**, max 8,000 (`num_predict`'s cap). The reasoning budget activated 1,014 times and ended naturally 937 — ~77 generations were cut by budget.

### 0.4 The fitter is failing to prevent the exact thing it exists to prevent, 5.7 % of the time

`fit_to_window`'s docstring (`heartbeat.py:570`) says it exists because *"when [the prompt] does not [fit], ollama shifts context and silently drops the OLDEST tokens — the system prompt and the posture — with no error at any layer."* Measured in the runner log, 09-11 → 09-13:

```
stop processing: ... truncated = 0   1,940
stop processing: ... truncated = 1     118     (5.7 %)
```

**118 releases had the prompt head-truncated.** On a dense transformer that costs the system prompt. **On this hybrid it also invalidates the recurrent state**, because the state was computed over tokens that are no longer at those positions. This is a live, previously-unreported failure mode, it is invisible in `heartbeats.jsonl`, and it is the most concrete defect in this document. §2.9.

### 0.5 Compaction does *not* fight the cache — and the accident is a design rule

I expected `compact_convo`'s oldest-first elision to invalidate the prefix. Measured: compacted requests have *higher* reuse (median `sim_best` 0.963, 0.4 % zero-reuse) than uncompacted ones (0.903, 41.3 % zero-reuse). The reason is that elision is **monotone** — a result once stubbed stays stubbed, and each new elision lands at a *later* index than the last, so the prefix up to the newest elision is unchanged.

**Any salience-based eviction that can re-expand, re-order, or re-rank will lose this property.** On this architecture the penalty is worse than a re-prefill: it is a re-prefill *plus* a recurrent-state rebuild, with no partial credit unless a checkpoint happens to sit at the right place. That is the concrete form of the tension the coordinator raised between "persist in KV" and "evict by salience", and it has a clean resolution: **mutation monotonicity** (§5, Stage 2).

### 0.6 My own instrument cannot tell whether eviction is safe

The being has made 4,261 tool calls all-time; **32 (0.75 %)** were `memory_read` of `conversations/*.jsonl`, the recovery path for evicted turns. Over the last 60 beats it cited a conversation turn by `seq` **200 times, and 0 of those citations pointed outside the display window.**

That reads like "eviction is free". It is equally consistent with "it cannot cite what it cannot see". **A measurement of references-to-absent-content can only come back confirming.** This is thor's *"a gate that measures shape passes forever while the substance is absent"* (`forum/thor-parallel-competitive-paths-2026-09-13.md`) pointed at my own evidence. §5 Stage 5 is a probe built to separate the two worlds; until it runs, every eviction proposal here is provisional.

---

## 1. What we have

### 1.1 The prompt assembly path

Everything the being sees is built in `sage/gateway/heartbeat.py::main()` and handed to `run_ollama_tool_turn`.

| Component | Location | What it does | What it **cannot** do |
|---|---|---|---|
| `posture()` | `heartbeat.py:84` | reads `BEING_POSTURE.md` fresh every beat (7,159 chars stripped) | nothing trims it; in the never-trimmable set by design |
| `entrustment()` | `heartbeat.py:90` | reads `entrustment.md` **whole**, deliberately never tail-truncated (10,320 chars) | not trimmable, not summarisable; re-sent verbatim every beat |
| `own_state()` | `heartbeat.py:337` | entrustment + conversations + dp channel + seat relay + account + `todo.md` tail (3,000) + `journal.md` tail (2,500) + `scratch/`, `notes/` listings (30 newest each) | it is a **pure re-render**: no memory of what the last beat showed, so it cannot diff, cannot say "unchanged", cannot suppress a block already read |
| `CONV_LADDER` | `heartbeat.py:405` | `((12,None),(12,1500),(6,1200),(3,900),(2,700))` | steps **only** conversations; no rung touches entrustment, posture, todo or journal |
| `fit_state()` | `heartbeat.py:539` | walks the ladder until the fixed prompt fits `window_budget_chars` | uses the last rung even when it still does not fit; the beat runs overcommitted and says so |
| `window_budget_chars()` | `heartbeat.py:394` | `(num_ctx − min(num_predict,6144) − 512) × CPT`, `CPT = 3.4` (`:390`) | the constant is stale and drifting — §2.4 |
| `fit_to_window()` | `heartbeat.py:570` | trims **only** `digest` (floor 1,200) then `recall` (floor 400), reporting each trim | refuses to touch entrustment, todo, journal, posture, affordances — a deliberate value choice that leaves **the largest block in the floor untouchable**. And it still lets 5.7 % of prompts be truncated by the server (§0.4, §2.9) |
| `LOOP_GROWTH_CHARS` | `heartbeat.py:407` | 10,000 chars reserved for the loop's growth | a constant, not a function of what the being is doing |
| `compose()` | `heartbeat.py:633` | builds `[system, user]`; posture-first for this model | **the user turn begins with a per-beat timestamp** (`:889`) ahead of everything stable |
| `_config_check` / `_fill_headroom` | `:272`, `:302` | writes `prompt_blocks_chars`, `prompt_tokens_max`, `headroom_tokens`, `context_overcommitted` | reports, does not act. Has now reported `context_overcommitted: true` on **184 of 191 beats** |

### 1.2 The in-loop machinery

| Component | Location | What it does | What it **cannot** do |
|---|---|---|---|
| `compact_convo()` | `being_tool_loop.py:512` | elides **tool-result bodies only**, oldest first, keeping `COMPACT_KEEP_CHARS = 400` head/tail with an explicit marker; protects the newest until protecting it is what cuts the answer | cannot touch the state block, system prompt, or any assistant turn. **The floor is immovable inside a beat by construction.** Cannot reorder or re-expand — and per §0.5 that limitation is what keeps the cache alive |
| `_est_tokens()` | `:499` | anchors on the previous generate's `prompt_eval_count`, rides a chars/token guess only on the delta (`_CPT = 3.4`, `_CPT_ADDED = 2.5`) | the anchored form is sound; the unanchored form is ~10 % optimistic at current density (§2.4) |
| `_window_pressure()` | `:459` | at `WINDOW_WARN_AT = 0.80` tells the being how much room is left, **from the server's count**, returning `None` rather than estimating | a *report*, not an actuator. Fired on 12 of 29 beats on 09-13; 11 beats still ended cut |
| `REST` | `:455` | the being's own verb for ending its turn; deliberately **ungated** (ending your own turn touches nothing) and it now changes scheduling (rested → 10 min, else 3 min) | one day old; 5 uses on 09-13 |
| `REPEAT_NUDGE_AT` / `REPEAT_BREAK_AT` | `:471–472` | names an identical-call loop at 3, ends the tool phase at 6 | fingerprints `(effector, args)`; a re-read interleaved with other calls is not a "repeat" — which is why the 59 % duplicate-read rate (§2.5) is invisible to it |

### 1.3 The conversation store — the enabler for everything dp proposes

- `render_for_being()` (`conversations.py:333`) renders the last `per_conv` turns per conversation, each capped by `_cap_for`.
- `_cap_for()` (`:324`) with `ANSWERED_TURN_CHARS = 400` (`:321`) is **already a two-tier salience policy**: anything up to the being's own last turn is "answered" and shown at 400 chars; anything after is live at full rung width. **Landed 2026-09-13** (`461b26d6e`) — one day old, so its cost is not yet measurable.
- `_shown_text()` (`:277`) emits the recovery pointer on truncation, naming `memory_read conversations/<id>.jsonl from_line <seq> lines 1`. **All 32 recovery reads the being has ever made used that exact form.** The path works and is correctly advertised.
- `awaiting()` (`:244`) computes *unseen*, not *spoken-after* — a distinction found the hard way on 09-08.
- **`render_for_being()` calls `mark_seen()` (`:376`), so it is not pure.** Anything sizing the block must reimplement the arithmetic read-only. I did; that is §2.6.

### 1.4 Built but unwired: `sage/attention/`

thor's claim, re-checked precisely.

- **Nothing in `sage/gateway/` imports `sage.attention` at all.** The live being path has **zero consumers**. Verified by grep across the repo.
- thor's phrasing ("imported by nothing outside its own tests") is slightly too strong: `sensor_snarc` ← `sage/core/sage_unified.py:23`; `sleep_consolidation` ← `sage/core/sage_consciousness.py:299`; `snarc_scorer` ← `sage/training/train_sage.py:24`. None is in the beat path. **The substance survives.**
- `sage/attention/kernel.py:412` carries `# TODO: Integrate SNARC salience scorer` — the kernel does not use the scorer either.
- **Usability triage:**
  - `threshold_decision.py` — `get_attention_threshold()`, `make_attention_decision()`. **Pure stdlib, no torch.** The metabolic-threshold arithmetic is usable today.
  - `experience_salience.py` — pure stdlib, hand-set weights (surprise .25, novelty .25, arousal .20, conflict .15, reward .15). Usable, **but its extractors key on IRP plugin-outcome dicts** (`num_plugins`, `total_budget_used`, `convergence_rate`, `avg_energy`) that do not exist for a prompt block. The weighted-sum shell is the reusable part, and it is five lines.
  - `snarc_scorer.py` / `sensor_snarc.py` — `torch.nn.Module`. **torch IS installed** in the miniforge env that runs the beat (2.5.1+cu121) — correcting the brief. But **no checkpoint of any kind exists**: the module is randomly initialised, so its "surprise" and "novelty" are random projections. **Not usable without training, and there is no labelled corpus.**
  - **VRAM forecloses the GPU route regardless:** `nvidia-smi` reads **15,181 / 16,376 MiB** used. The runner's own accounting: `CUDA0 model 12,153 + context 1,685 + compute 146 = 13,985 MiB of 15,943`. Nothing else of consequence fits.
- `sage/gateway/arousal.py` is a **separate, live** salience implementation (salience → `ENGAGE_AT` → wake marker) used by `dp_console.py:455`. The fleet has two salience codebases and the one in the beat path is not the designed one.

### 1.5 membot

- Live as `membot-legion.service` on **:8010**, `--writable --mount legion-being`, `MEMBOT_EMBED_BACKEND=ollama`.
- `cartridges/legion-being.cart.npz`: **334 passages, 768-dim float32**, manifest `mcp-v3`, rebuilt `2026-09-13T14:13:21Z`. Embeddings via ollama `nomic-embed-text`; no torch at query time.
- `membox.search(cart_id, query, top_k)` (`membot/membox.py:392`) returns per-pattern metadata (`agent_id`, `written_at`, `origin`, `reasoning`, `tags`). **The provenance fields codex's contract demands are already in the return value.**
- **The seat queries membot with a constant string every beat**: `heartbeat.py:821`, `{"query": "what I was doing, what I want next, what I learned", "top_k": 5}`, truncated to 2,500 chars. Not conditioned on anything about the beat. A fixed 2,500-char tax.
- **The being barely uses recall itself**: 18 `recall` calls in three days (1.1 % of 1,661) against 857 `memory_read`.
- Known gaps (`forum/legion-claude-membot-can-already-make-files-semantically-searchable-2026-09-13.md`): `read_folder` accepts only `.txt .md .pdf .docx .json .jsonl`; `cartridge_builder.py` hardcodes `SentenceTransformer` while the ollama backend lives unshared in `membot_server.py`.

---

## 2. What the measurements say

Sources: `sage/instances/legion-gemma3-12b/heartbeats.jsonl` (331 records, 09-03 → 09-13), `heartbeat.partial.jsonl` (2,839 generates), `conversations/*.jsonl`, `journalctl -u ollama`, and read-only `curl` against the runner's `/props` and `/slots`. Everything was recomputed; where it disagrees with the forum post I wrote this morning, the recomputation wins and I say so.

### 2.1 The floor is 67 %, not 74 %

The number in my forum post — 18,075 tokens, 74 % — is **the worst beat of 09-13, not the typical one.**

| day | beats | step-0 prompt tokens (median) | min | max | median as % of 24,576 |
|---|---|---|---|---|---|
| 09-09 | 35 | 15,792 | 14,910 | 16,189 | 64.3 % |
| 09-10 | 23 | 16,275 | 16,150 | 17,231 | 66.2 % |
| 09-11 | 25 | 16,489 | 16,190 | 17,113 | 67.1 % |
| 09-12 | 24 | 16,365 | 16,032 | 17,475 | 66.6 % |
| 09-13 | 30 | **16,568** | 15,572 | **18,075** | **67.4 %** |

The floor is **~67 % and climbing ~0.3 pt/day.** 18,075 is real and deserves publishing as the max — CBP's rule from the 09-12 window thread is *publish the statistic the gate trips on*, and a floor trips on its max — it just should not be called the floor.

Full-prompt occupancy across all 1,085 tasks agrees: `task.n_tokens` p50 **18,889**, p90 **22,559**, p99 **24,195**, max 24,553 of 24,576. **The being lives at 77–100 % of its window.**

### 2.2 The constraint, quantified

- **184 of 191 beats (96.3 %)** are flagged `context_overcommitted` by the harness's own accounting. Median `headroom_tokens` on 09-13: **−3,985**. This is the operating regime, not an edge case.
- Over 77 beats (09-11 → 09-13): **26 (34 %) ended with at least one generate cut at the window wall**; **5 (6.5 %) ended because the being chose to `rest`**; 46 ended otherwise (the model stopped asking for tools — a legitimate ending).
- Working room: largest prompt minus step-0 prompt, **median 5,419 tokens** (p90 7,717, max 8,383). Room available beneath the 6,144-token answer reserve: **median 1,968.** The being routinely runs ~3,400 tokens past its own reserve, which is why `compact_convo` fires on 906 of 1,216 matched generates.
- `prompt_eval_count` is the **full prompt**, not a delta — confirmed here by monotone growth within a beat (18,075 → 22,874 over nine steps), and independently by CBP's three-identical-prompt probe (`forum/cbp-re-sprout-window-record-shape-verified-two-fixes-2026-09-13.md`): counts 532/532/532, durations 719/57/46 ms — *the duration proves the cache hit; the count does not move.* That probe is load-bearing for everything in §2.7 and it is somebody else's measurement, independently arrived at.

### 2.3 The floor by block — measured, and it is not the table I published

09-13 medians from `config.prompt_blocks_chars`:

| block | chars (median) | ≈ tokens @ 3.05 | note |
|---|---:|---:|---|
| `state` | 32,953 | 10,804 | compound; decomposed below |
| `posture` | 7,159 | 2,347 | unchanged since 2026-09-07 12:19 |
| `fixed_other` (tool schemas + template) | 4,000 | 1,311 | a **budgeted constant, never measured** |
| `digest` | 3,389 | 1,111 | regenerated every beat |
| `recall` | 2,500 | 820 | constant query, hard cap |
| `inbox` | 1,500 | 492 | hard cap |
| **total seed** | **51,437** | **16,865** | matches measured step-0 of 16,568 to ~2 % |

`state` decomposed by re-reading the same files `own_state()` reads (read-only replica, no `mark_seen`):

| sub-block | chars | ≈ tokens | volatility |
|---|---:|---:|---|
| entrustment | 10,320 | 3,383 | **unchanged 6 days** (mtime 2026-09-07 11:37) |
| conversations + hestia scope + account + headers | ~15,511 | ~5,086 | changes most beats |
| `todo.md` tail | 2,998 | 982 | the being writes it most beats |
| `journal.md` tail | 2,499 | 819 | the being writes it most beats |
| `scratch/` listing (100 files, 30 shown) | 1,221 | 400 | changes most beats |
| `notes/` listing (12 files) | 404 | 132 | rarely |

**Correction to my forum table:** it listed "conversations 12,851". Measured now at the live rung the conversations block is **8,815 chars** (§2.6) — the earlier figure was from a different day at a wider rung, before `_cap_for` landed. Entrustment (10,355 raw → 10,320 stripped) and posture (7,159) are exact.

### 2.4 The fitter's chars-per-token constant is stale and drifting

`heartbeat.py:390` sets `CPT = 3.4`, citing *"Measured on this being 2026-09-08: 70.5k prompt chars → 20,812 prompt tokens = 3.39"*, with the stated intent to **estimate high in tokens** (a *low* chars/token). Measured now, seed chars ÷ step-0 `prompt_eval_count`, 142 paired beats:

| day | n | measured chars/token |
|---|---:|---:|
| 09-08 | 7 | 3.247 |
| 09-09 | 34 | 3.239 |
| 09-10 | 24 | 3.195 |
| 09-11 | 24 | 3.150 |
| 09-12 | 24 | 3.158 |
| 09-13 | 29 | **3.068** |

The constant is **~10 % too generous and eroding ~0.035/day**, so the fitter over-admits roughly 1,800 chars ≈ 590 tokens every beat. The drift is explainable — the being's content is shifting toward paths, code and JSON, which tokenize denser — and it will continue. `_CPT_ADDED = 2.5` for loop growth is separately calibrated and looks right; it is the *seed* constant that has gone stale. **This is a live, verified, cheap defect**, and it is the *superseded-instrument-surviving-in-the-evidence-cells* class: the comment still cites its 09-08 measurement as current.

### 2.5 What the being actually does with its beats

1,661 tool calls, 09-11 → 09-13:

| verb | calls | share |
|---|---:|---:|
| `memory_read` | 857 | **51.6 %** |
| `memory_write` | 359 | 21.6 % |
| `git_read` | 119 | 7.2 % |
| `remember` | 88 | 5.3 % |
| `check` | 75 | 4.5 % |
| `witness` | 67 | 4.0 % |
| `say` | 43 | 2.6 % |
| `recall` | 18 | 1.1 % |
| `search` | 15 | 0.9 % |
| everything else | 20 | 1.2 % |

And the reads: **883 file reads over 127 distinct paths.**

- **85.6 % of reads are re-reads** of a path already read in the window.
- **59.2 % of reads (523 of 883) are duplicates *within the same beat*.**
- Top paths: `sage/irp/plugins/ollama_irp.py` **160×**, `sage/gateway/heartbeat.py` **153×**, `test_ollama_irp_payload.py` 65, `being_tool_loop.py` 53.
- Read payload: median 2,139 chars (~700 tok), mean 2,909, p90 6,696, max 14,969. Three days of reads ≈ **931 k tokens**.

**This is the measurement that justifies the "world model" framing, and given §0.3 it is also the measurement with the most money behind it.** Over half the being's agency goes to re-acquiring a working set of four or five files. The within-beat 59.2 % is the sharper half: re-reads of a file read twenty minutes ago *in the same conversation*, because `compact_convo` stubbed the result to 400 chars — and the re-read costs another ~700 tokens, which forces another elision. **The compaction loop is a thrash loop**, and what it thrashes is the working set, not the conversation.

Because decode is 93.5 % of GPU time and each re-read must be *asked for* (a tool call the model generates) and *reasoned about* (tokens it generates after), the duplicate reads cost decode time as well as window. **This is the highest-value behavioural target in the document.**

### 2.6 The conversation block, and dp's LRU hypothesis

Read-only replica of `render_for_being`'s arithmetic against the live store:

| rung | block chars | with `_cap_for` off | `_cap_for` saves | answered | **unanswered** |
|---|---:|---:|---:|---:|---:|
| (12, None) | 8,815 | 20,720 | 11,905 (57.5 %) | 22 turns / 8,098 ch | **1 turn / 717 ch** |
| (12, 1500) | 8,815 | 20,230 | 11,415 (56.4 %) | 22 / 8,098 | 1 / 717 |
| (6, 1200) | 4,701 | 9,340 | 4,639 (49.7 %) | 11 / 3,984 | 1 / 717 |
| (3, 900) | 2,717 | 4,669 | 1,952 (41.8 %) | 5 / 2,000 | 1 / 700 |

**(a) `_cap_for` is a strong baseline and it is not recency-ordered.** It saves 56 % at the live rung using a **state predicate** (answered / unanswered), not a recency ordering. Any policy proposed here must beat it — and it is one day old, so nobody yet knows whether it cost anything.

**(b) After `_cap_for`, 92 % of the conversation block is still finished business.** 8,098 chars answered vs **717 chars unanswered**. The part of that block that is actually *work* is 717 characters — 235 tokens.

**(c) LRU is the wrong key, and the data says so.** LRU evicts by recency, but the being's conversation has a structure recency is blind to: **an answered turn is finished whether it arrived a minute ago or a week ago, and an unanswered turn is work regardless of age.** The eviction-relevant variable is already computed (`awaiting()`), already used (`_cap_for`), and is *orthogonal* to recency.

| policy | key | fit to the observed pattern |
|---|---|---|
| **LRU** | recency | **poor** — evicts an old unanswered turn (the one case that is pure work) before a recent answered one |
| **LFU** | access count | **unmeasurable** — the being never "accesses" a prompt block; there is no hit signal to count |
| **ARC / 2Q** | recency + frequency | same problem as LFU: the hit signal would have to be invented |
| **TTL** | age | worse than LRU; it expires the one thing that has no expiry |
| **state-tiered (answered / superseded / live)** | `awaiting()`, already computed | **fits.** It is what `_cap_for` does, and the live tier is 8 % of the block |
| **explicit conclusion (dp's third message)** | the being's own judgement | fits, and adds the one thing no predicate can infer: *finished* ≠ *answered* (§5, Stage 4) |

The closest thing in the literature to a *principled* eviction score for this exact setting is Marconi's (§0.1): **rank by compute-saved-per-byte weighted by reuse likelihood**, not by recency. On this box the compute-saved term is dominated by whether a checkpoint exists (§2.7), which recency does not predict.

**(d) The conversation is probably not the right unit anyway.** At the live rung it is 8,815 chars — **17 % of the 51,437-char seed**. Evicting *all* of it frees ~2,900 tokens. Entrustment alone is 10,320 chars / 3,383 tokens and has not changed in six days. **The unit that matters is the block, and the worst value-per-token block is not the conversation.**

**(e) The interlocutor writes for free.** dp's datum, confirmed exactly: on 09-13 the seat sent **28 turns / 25,044 chars**, the being **20 / 24,213**. In the rendered block the split is **being 36.3 % (3,200 ch / 8 turns) vs interlocutor 63.7 % (5,615 ch / 15 turns)**. Evicting the interlocutor's share frees ~1,840 tokens; the being's own frees ~1,050. So the priority inversion is *available*, and is the larger half — but see §5 Stage 5 for why available is not earned.

### 2.7 The KV cache on a hybrid model: what is actually happening here

llama-server's slot log carries two selection outcomes:

```
slot get_availabl: id 0 | selected slot by LCP similarity, sim_best = 0.954 (> 0.100 thold), f_keep = 0.889
slot get_availabl: id 0 | selected slot by LRU, t_last = ...
```

`sim_best` is the fraction of the **new prompt** already in the slot's cache; `f_keep` the fraction of the **old cache** retained; the threshold is `-sps/--slot-prompt-similarity`, default **0.10**. Verified against a worked case: prompt 21,114, `restored ... n_past = 20072` → 20072/21114 = 0.9506 ≈ 0.954; previous release `n_tokens = 22641` → 20072/22641 = 0.8866 ≈ 0.889.

**But on this hybrid the LCP is not enough.** The server must also find a **context checkpoint at or before the divergence point**:

```
task 133425 | new prompt, n_keep = 4, task.n_tokens = 20619
task 133425 | Checking checkpoint with [20207, 20207] against 19748...   <- rejected, pos_max > target
task 133425 | Checking checkpoint with [19576, 19576] against 19748...   <- accepted
task 133425 | restored context checkpoint (pos_min=19576, pos_max=19576, n_tokens=19577, size=149.626 MiB)
```

If no checkpoint qualifies, the server prints `forcing full prompt re-processing due to lack of cache data (likely due to SWA or hybrid/recurrent memory)` and restarts from token 0. Startup config: `context checkpoints enabled, max = 32, min spacing = 256`.

**Measured over 1,403 paired requests, 09-11 → 09-13:**

| | n | share | median `sim_best` |
|---|---:|---:|---:|
| LCP hit | 1,168 | 83.3 % | 0.957 |
| **`selected slot by LRU` — zero reuse** | **235** | **16.7 %** | 0 |

- Prefix reuse already saves **81.7 %** of prefill (26.73 M presented → 4.89 M prefilled).
- The 235 zero-reuse requests carry **73.5 %** of remaining prefill work.
- Split by compaction state: **compacted median `sim_best` 0.963, 0.4 % zero-reuse; uncompacted median 0.903, 41.3 % zero-reuse.** Compaction is not the enemy; **fresh prompt assembly is.**

An independent parse over 1,085 tasks locates the divergence precisely: **179 tasks (16.5 %) diverge below token 200, and the distribution is two constants — `pos_next = 40` on 111 tasks and `pos_next = 69` on 55.** Only 7 tasks diverge in 200–5,000; 886 diverge past 5,000. So the misses are **not a spread, they are a template switch**: two or three distinct prompt shapes share the slot (explore seed, reflect seed, the account turn, plus non-beat callers), their mutual LCP is the chat-template preamble plus `"You are legion-being, a SAGE being on the legion machine, member id legion-being."` — about 40 tokens — and every switch pays a full re-prefill. That matches my own count exactly: **88 cold prefills/day over 29 beats = 3.0 per beat.**

**Measured throughput on this exact hardware** (measured, not cited):

| | value | conditions |
|---|---|---|
| Prefill, cold, from token 0 | **825–940 tok/s** | `-ub 512`, FA on |
| Prefill at ~20 k depth | 577–650 tok/s | attention cost grows with position |
| Prefill, 48 h average | **786 tok/s** | 4.60 M tokens |
| Decode | **19.4–19.6 tok/s** | flat across the whole 24 k window |
| A cold ~16.5 k prefill | **≈ 20 s** | the per-beat latency penalty of a miss |

Daily prefill cost (my parse): 09-11 34.7 min, 09-12 31.0 min, 09-13 30.5 min. On 09-13 the **88 cold prefills cost 24.4 min** while all 359 warm requests together cost **6.2 min**.

**And §0.3 is the number that matters:** prefill is 5,856 s against decode's 84,515 s over 48 h. **Prefill is 6.5 % of GPU-busy time.** Every prefill improvement in this document is a latency and hygiene improvement, not a throughput one. I had this backwards this morning.

**Checkpoint placement — the thing that decides whether a stable prefix can pay.** Checkpoints *are* laid down during a cold prefill:

```
00:05:22 new prompt, task.n_tokens = 16213            (selected slot by LRU — cold)
00:05:27 created context checkpoint 1 of 32 (pos_min = 4634)
00:05:40 created context checkpoint 2 of 32 (pos_min = 15700)
00:05:40 init sampler
```

but the surviving population is deep. Over 2,204 checkpoint creations, 09-11 → 09-13:

```
pos: min 8   p10 15,911   p50 18,608   p90 22,280   max 24,538
  0– 1,999:  13      4,000– 5,999:  72      12,000–13,999:   9
 14,000–15,999: 145  16,000–17,999: 575     18,000–19,999: 698
 20,000–21,999: 424  22,000–23,999: 240     24,000+:        28
```

**Only 85 of 2,204 (3.9 %) sit below position 6,000**, and the 32-slot ring is refilled from the deep end every beat. So **a stable prefix ending at token ~7,600 would usually find no checkpoint at or before it, and would be re-prefilled in full anyway.** This is the single most important operational consequence of §0.1, and it converts §5 Stage 2 from "free win" into "free win *conditional on a checkpoint you must arrange*". Both knobs are reachable from the systemd unit — `LLAMA_ARG_CTX_CHECKPOINTS` and `LLAMA_ARG_CHECKPOINT_MIN_SPACING_NT` — because ollama passes neither on the command line.

**What `LLAMA_ARG_CACHE_RAM=0` did and did not do.** The drop-in `/etc/systemd/system/ollama.service.d/60-legion-prompt-cache.conf` disables llama-server's **host-RAM prompt cache** (`--cache-ram`), the thing that drove a swap stall and a watchdog kill on 09-08. It does **not** disable in-slot KV reuse — `--cache-prompt` is a different flag and defaults to enabled, the server logs *"prompt cache is disabled ... context checkpoints enabled, max = 32"* as two separate facts, and a live `GET /slots` during a beat reads `n_prompt_tokens 22856, n_prompt_tokens_processed 161, n_prompt_tokens_cache 21103`. **161 tokens prefilled out of 22,856.** The decision stands; the comment's reasoning ("consecutive prompts differ every time — nothing is ever restored") was right about the host cache and wrong about the premise.

**But it did not bound the other host-RAM consumer.** Context checkpoints are **149.626 MiB each** (the SSM state) with a default max of **32 per slot** — up to **~3.9 GiB of host RAM**, governed by `LLAMA_ARG_CTX_CHECKPOINTS`, *not* by `--cache-ram`. Ten checkpoints ≈ 1.46 GiB, which is very likely what the 09-08 investigation observed as "1.2–1.7 GB per beat". Current state: `llama-server` RSS **1.98 GB**; ollama cgroup `MemoryCurrent = 14.06 GB` sitting **at** `MemoryHigh = 14 GiB` with `MemorySwapCurrent = 3.8 MB`. The MemoryHigh contact is mostly reclaimable page cache and is benign today — but **the guard has no headroom left to signal with**, and checkpoint growth is exactly the kind of real GB that would hide behind it.

Other invalidators: **13 runner restarts** over the window (one logged `model predicted to exceed available memory, evicting`) and the truncation events below. `keep_alive` is not a factor — `/api/ps` shows `expires_at: 2318-12-24`, effectively pinned.

### 2.8 Does the being reach for evicted content?

- All-time: **32 of 4,261 tool calls (0.75 %)** were `memory_read` of `conversations/*.jsonl`. **All 32 used the `from_line`/`lines` form** the truncation marker advertises — when it reaches, it reaches correctly.
- By day: 09-09: 13, 09-10: 11, 09-11: 5, 09-12: 1, 09-13: 2. **Declining — and the decline predates `_cap_for`** (landed 09-13), so it is not evidence the cap removed a need; it is confounded by what the being was working on.
- Over the last 60 beats it cited a conversation turn by `seq` **200 times**. **Zero of those pointed outside that beat's display window.**
- Over the last 40 beats: **79 citations of its own turns, 50 of the interlocutor's** (61 % / 39 %).

**Read this honestly.** The 0-of-200 is *not* evidence that eviction is safe. It is what you get in both worlds: *A* — it does not need evicted turns, eviction is free; *B* — it cannot tell what it is missing, so it never asks, and eviction is silent harm. A measurement of citations-to-absent-content cannot separate them, because in B the count is zero by construction. The 61/39 split is likewise confounded: **both** are in the prompt, so it measures what the being talks about, not what it needs. §5 Stage 5 is built to separate them.

### 2.9 The truncation events — a live defect nobody had found

```
stop processing: ... truncated = 0   1,940
stop processing: ... truncated = 1     118   (5.7 %)
```

**118 releases over three days had the prompt head-truncated by the server.** That is exactly the failure `fit_to_window` was written to prevent, still occurring at 1-in-18. On a dense model it costs the system prompt and the posture — the governance. **On this hybrid it additionally invalidates the recurrent state**, because the state was accumulated over tokens that are no longer at those positions, so the next request also cannot reuse anything.

It is invisible in `heartbeats.jsonl`: nothing in the beat record knows it happened. The likely mechanism is the one §2.4 describes — `CPT = 3.4` over-admits ~590 tokens per beat, `LOOP_GROWTH_CHARS` is a constant, and the loop grows past the fitter's estimate — but I have not proven the causal link and say so. **`truncated` should be plumbed into the beat record before anything else in this document is built**, because every behavioural measurement proposed in §5 is contaminated by a 5.7 % rate of silently decapitated prompts.

---

## 3. Survey of techniques, with a verdict for this deployment

Verdicts are specific to: ollama 0.30.4 → upstream `llama-server` (build `a731805ce`), **one slot**, hybrid attention+SSM 26.9 B at Q3_K_M, `num_ctx` 24,576, ~0.8–1.2 GB free VRAM, single serial agent, decode-bound.

The runner is launched as:
```
llama-server --model <blob> -c 24576 -np 1 --flash-attn auto -b 512 -ub 512 --mmproj <blob> ...
```
**What is absent matters:** no `--cache-ram`, `--cache-reuse`, `--slot-save-path`, `--keep`, `--context-shift`, `--cache-type-k/v`, `--spec-type`. llama.cpp reads `LLAMA_ARG_*` env vars but **command-line flags win**, so anything ollama passes explicitly (`-c`, `-np`, `-b`, `-ub`, `--flash-attn`) is unreachable by env, and **everything it does not pass is settable from the systemd unit**.

### 3.1 KV persistence and prefix reuse — **available today, already working, with one hybrid caveat**

| technique | status here | verdict |
|---|---|---|
| **in-slot LCP prefix reuse** | live and measured (§2.7) | **Already delivering 81.7 % prefill savings.** The remaining opportunity is making the *prefix* stable and making a *checkpoint* exist at its boundary — not turning anything on |
| **context checkpoints** | live: max 32, min spacing 256, **149.626 MiB each** | **The mechanism that decides whether a stable prefix pays** (§2.7). 96 % of live checkpoints sit above position 6,000. `LLAMA_ARG_CTX_CHECKPOINTS` and `LLAMA_ARG_CHECKPOINT_MIN_SPACING_NT` are reachable |
| **host-RAM prompt cache (`--cache-ram`)** | deliberately disabled after the 09-08 swap stall | keep disabled. Wrong tool: it restores *evicted* prompts, and with one slot and a pinned model nothing is evicted |
| **`/slots?action=save\|restore`** | `endpoint_slots: true` but `--slot-save-path` is unset **and has no `LLAMA_ARG_*` env var** | unreachable without patching ollama. And **pointless here**: [llama.cpp #25913](https://github.com/ggml-org/llama.cpp/issues/25913) reports that on hybrid/recurrent models save/restore serialises tokens + KV cells but **never `slot.prompt.checkpoints`**, and restore calls `prompt.clear()` — measured there, a 14,906-token prefix restored in 0.12 s then recomputed in full. **Dead end for this architecture.** |
| **`--cache-reuse N`** (KV-shift across a mid-prompt edit) | reachable by env | **useless here** — [#18497](https://github.com/ggml-org/llama.cpp/issues/18497): recurrent state cannot be repositioned like KV, so the shift path degenerates to full reprocessing |
| **`--keep` / attention-sink pinning** | `n_keep = 4` | effectively unused; only matters if context shift is reached |
| **vLLM automatic prefix caching** | not installed | **do not pursue.** [vLLM #51250](https://github.com/vllm-project/vllm/issues/51250) measures **`prefix_cache_hits_total: 0` out of 1,131 queries** on this exact Qwen3.5 hybrid family — *"the model's recurrent conversational + SSM state is not stored in the APC"*. Tracking issue [#26201](https://github.com/vllm-project/vllm/issues/26201): GDN support still pending |
| **SGLang RadixAttention / MambaRadixCache** | not installed | further ahead than vLLM (`--mamba-track-interval` is the direct analogue of `--checkpoint-min-step`), but [#24121](https://github.com/sgl-project/sglang/issues/24121) reports crashes on Qwen3.5/3.6. **And capacity forecloses it regardless** |
| **leaving ollama at all** | — | **No.** vLLM's GGUF support moved out-of-tree ([vllm-gguf-plugin](https://github.com/vllm-project/vllm-gguf-plugin), documented "highly experimental"), the `qwen35` hybrid GGUF path is unsupported, and the realistic AWQ-int4 alternative is ~14–15 GB of weights before KV on a card with under 1 GB free. **llama.cpp's checkpoint mechanism is currently the best hybrid prefix cache of the three for this deployment.** |

**The sharp point.** dp's "keep in kv cache preferably" is already true for 82 % of the prompt, has bought no window, and is worth 6.5 % of GPU time in total. **KV reuse is a time optimisation; the being's problem is space and decode.** Both are worth having; conflating them is how a plan ends up optimising the thing that is already fine.

### 3.2 Attention sinks / KV eviction — **not available, and aimed at a different problem**

| technique | verdict |
|---|---|
| **Context shift / StreamingLLM** ([arXiv:2309.17453](https://arxiv.org/abs/2309.17453)) | **Not removed — disabled by default** since [llama.cpp PR #15416](https://github.com/ggml-org/llama.cpp/pull/15416), on the grounds that on chat endpoints it *"can destroy the structure of the chat template."* On this host ollama passes `--context-shift --keep 4` to the **embedding** runner and **not** to the 27B (verified across 125 runner launches). Also force-disabled by `--mmproj`, and mutually exclusive with quantized K (the shift is a RoPE re-rotation over the K cache). The paper is explicit that it *"does not extend the models' context window"* — it is for one unbounded generation, not a prompt rebuilt every beat. **Wrong mechanism.** |
| **SnapKV** ([2404.14469](https://arxiv.org/abs/2404.14469)), **PyramidKV** ([2406.02069](https://arxiv.org/abs/2406.02069)) | The right *shape* — compress a long static prompt once at end of prefill, scored by attention from a tail observation window (SnapKV) or by a per-layer budget pyramid (PyramidKV, full performance at 12 % cache). **And precisely the ones with no implementation.** |
| **H2O** ([2306.14048](https://arxiv.org/abs/2306.14048)), **Scissorhands** ([2305.17118](https://arxiv.org/abs/2305.17118)), **FastGen** ([2310.01801](https://arxiv.org/abs/2310.01801)) | decode-side; would buy little on a 780-token median generation |
| **availability, all of the above** | **None in llama.cpp or ollama. Verified, not assumed:** two feature requests with **zero maintainer replies** ([discussion #13986](https://github.com/ggml-org/llama.cpp/discussions/13986), [#28170](https://github.com/ggml-org/llama.cpp/discussions/28170)). #13986 names the structural blocker: *"there is only one global list of occupied KV-cache entries, which is assumed to be the same for all attention heads."* Adopting any means a `transformers` research fork, at which point 16 GB for a 27B becomes binding |
| **KV quantisation** | reachable — §3.3 |
| **Sliding-window attention** | `n_swa = 0`, `is_swa_any = 0`. **No SWA**; `--swa-full` is inert. What this model has instead is `full_attention_interval = 4`, which is why KV is 4× cheaper and why partial rollback needs checkpoints |

**The falsifier, and the most important citation in this section.** [**The Pitfalls of KV Cache Compression** (arXiv:2510.00231)](https://arxiv.org/abs/2510.00231) evaluates StreamingLLM, SnapKV, TOVA, H2O and K-Norm and finds that **specific instructions degrade far faster than aggregate metrics show — some become effectively ignored — with demonstrated system-prompt leakage, and sensitivity to instruction *ordering*.** For a **governed** agent the prefix is not context, it *is* the governance: the posture, the entrustment, the affordances, the refusal rules. **Any compression or eviction proposal here must be evaluated on per-instruction adherence as a function of position, not on perplexity or token count.** That evaluation does not exist in the literature for governed/agentic prompts, and it is measurable on the existing beat harness.

### 3.3 KV cache quantisation — the only real "more window" lever, and it is a model-quality change

Deployed binary accepts `-ctk/-ctv` in `{f32, f16, bf16, q8_0, q4_0, q4_1, iq4_nl, q5_0, q5_1}`, default `f16`. Flash attention is required for quantized V and is already auto-enabled here. ollama exposes `OLLAMA_KV_CACHE_TYPE` (f16/q8_0/q4_0 only, **global across all models**) and `OLLAMA_FLASH_ATTENTION`; `LLAMA_ARG_CACHE_TYPE_K/V` also reach the runner since ollama passes no such flag.

Computed from this model's real geometry (16 KV layers, `n_embd_k_gqa = n_embd_v_gqa = 1024`, 24,576 ctx) — **the f16 row matches the runner's measured 1536.00 MiB exactly**, which validates the arithmetic:

| cache type | KV size | per token | freed vs f16 |
|---|---:|---:|---:|
| **f16 (current)** | **1536 MiB** | 64.0 KiB | — |
| **q8_0** | **816 MiB** | 34.0 KiB | **720 MiB** |
| q5_1 | 576 MiB | 24.0 KiB | 960 MiB |
| **q4_0** | **432 MiB** | 18.0 KiB | **1104 MiB** |

Plus a fixed, **non-quantizable** 149.62 MiB recurrent state.

Quality, from [llama.cpp PR #7412](https://github.com/ggml-org/llama.cpp/pull/7412): *"There seems to be no significant quality loss from using q8_0 instead of FP16"*; *"The K cache seems to be much more sensitive to quantization than the V cache"*; and *"a 6.5 bpv KV cache (K=q8_0, V=q4_0) is more precise than q6_K weights."* [PR #7527](https://github.com/ggml-org/llama.cpp/pull/7527) measured q8_0/q8_0 at ~3 % throughput cost.

**Trap:** default CUDA builds compile FA kernels only for f16/bf16/q8_0/q4_0. `q5_1`, `q4_1`, `iq4_nl` and mixed combinations **silently fall back to CPU attention** — measured at **q5_1 197 t/s vs q8_0 1511 t/s** ([#28455](https://github.com/ggml-org/llama.cpp/issues/28455)). ollama's restriction to f16/q8_0/q4_0 is exactly the safe subset.

**Verdict: `q8_0` is the sane choice and `q4_0` is not**, on evidence from [qllm-eval (ICML 2024)](https://arxiv.org/pdf/2402.18158), whose bit-width recommendation splits **explicitly at 4K context: KV4 below, KV8 above.** But this is a **model-quality change that perturbs every logit**, so it must not be mixed into a context-management experiment. §5 keeps it out.

### 3.4 Prompt compression — applicable in principle, hostile in practice, with one narrow carve-out

| technique | verdict |
|---|---|
| **LLMLingua** ([2310.05736](https://arxiv.org/abs/2310.05736)) | **Read the task split, not the headline.** GSM8K at 20× loses 1.5 EM; **BBH at 5× loses 8.5 and at 7× loses 13.2.** Governance/entrustment text is BBH-shaped — heterogeneous, every clause load-bearing — not GSM8K-shaped. And the compressor peaks at **16.6 GB GPU**; it will not co-reside with 12.4 GB of weights |
| **LongLLMLingua** ([2310.06839](https://arxiv.org/abs/2310.06839)) | **worst possible choice here** — question-aware by design, i.e. it makes head content an explicit function of the tail |
| **LLMLingua-2** ([2403.12968](https://arxiv.org/abs/2403.12968)) | peak GPU **2.1 GB**, 0.4–0.5 s, checkpoints at 355 M / 110 M — the only member that fits. But **out-of-domain LongBench at ~5×: 39.1 vs 44.0 original.** Fleet digests and posture docs are far out of MeetingBank's distribution; assume the 39.1-vs-44.0 number |
| **Does it destroy prefix reuse?** | **Yes in the obvious deployment, and the mechanism is in the source.** The compressor is deterministic per-input, but two global couplings make the *head* of the output a function of the *tail* of the input: `threshold = np.percentile(context_probs, 100*(1-rate))` is computed over the **whole** input, so a new tail shifts the distribution and flips keep→drop *inside the stable prefix*; and `tau = target_token / (sum(context_length)+1)` makes segment 1's rate an explicit function of total prompt length. Plus the encoder is **bidirectional**. Net: a different prefix every beat, hit rate → 0. **Per-beat compression is strictly worse than a stable uncompressed prefix.** |
| **the carve-out** | Compress each **stable block independently, offline, once, at a fixed per-block rate**, and commit the output string. Then the percentile and `tau` are over that block alone, the compressor never runs at inference, and the result is byte-stable. **Never** compress the digest or recall (they change anyway) and **never** compress tool schemas — LLMLingua is extractive at word granularity and will silently mangle JSON |
| **soft-prompt methods** (Gist Tokens, ICAE, 500xCompressor…) | **all unavailable.** Every one requires injecting continuous vectors into the decoder; llama.cpp's server and ollama expose no endpoint that accepts input embeddings. Also worth noting Gist Tokens' honest number: 26× compression, **4.2 % wall-time speedup** |
| **Acon** ([2510.00615](https://arxiv.org/html/2510.00615v2)) | **the most relevant recent work and the right shape for a governed setup**: it optimises **compression guidelines written in natural language** by contrastive feedback, gradient-free. ~25–30 % peak-token reduction on agentic benchmarks. The artifact you tune is a text file — auditable, reviewable, and it costs no VRAM |
| **summarisation hierarchies** | the family that fits, and `compact_convo` is already a member. What is missing is *hierarchy*: it has exactly two levels (whole / 400-char stub) and no middle, and it never summarises — it elides and points. dp's `conclude` (§5, Stage 4) is the missing middle |

### 3.5 RAG vs long context — and why the 2024 consensus does not apply here

[Li et al., EMNLP 2024 Industry (2407.16833)](https://arxiv.org/abs/2407.16833) found long-context beats RAG by 3.6–13.1 % — **but established on 128 K–1 M frontier models**, and its own framing names the exception: RAG wins *"when the input text considerably exceeds the model's context window size"*, which is exactly a 24 K local model against accumulated fleet state. Corroborating: [Databricks (2411.03538)](https://arxiv.org/html/2411.03538) — most open models improve only to 16–32 K then degrade; [NVIDIA OP-RAG (2409.01666)](https://arxiv.org/abs/2409.01666) — **feed retrieved chunks in corpus order, not relevance order**; quality vs chunk count is an **inverted U**; 11 % higher accuracy on half the tokens; [2501.01880](https://arxiv.org/pdf/2501.01880) — **summarisation-based retrieval ≈ long-context while chunk-based lags.**

**Synthesis for this being: hierarchical summarised memory, retrieved and presented in chronological order.** That is a direct argument for `conclude` (§5, Stage 4) over more retrieval, and a direct argument against relevance-ordered recall injection.

### 3.6 Context rot, and the quantisation interaction — the strongest argument for compression here

- [Lost in the Middle (TACL 2024)](https://aclanthology.org/2024.tacl-1.9/): U-shaped; **>30 % accuracy drop** moving the gold document from position 1 to 10 of 20. The middle of an 18 K prefix is an attention dead zone, so **ordering within the prefix is a free lever**.
- [RULER (2404.06654)](https://arxiv.org/abs/2404.06654): of models claiming ≥32 K, **only half** clear the bar at 32 K.
- [NoLiMa (ICML 2025)](https://arxiv.org/html/2502.05167v3): *effective* length — **GPT-4o 8 K, Claude 3.5 Sonnet 4 K, Llama 3.3 70B 2 K.** With literal lexical overlap, 32 K accuracy is 98.5 %; without it, two-hop drops to **25.9 %**. The being's recall is semantic, i.e. the no-lexical-overlap case.
- [Chroma, Context Rot (2025)](https://www.trychroma.com/research/context-rot), 18 models: **models performed *worse* when the haystack had coherent logical flow** — a shuffled haystack scored better, across all 18. **A beautifully written entrustment document may be harder to retrieve from than the same facts as a disordered list.**

**And the interaction is real and measured.** [qllm-eval (ICML 2024)](https://arxiv.org/pdf/2402.18158) §7.2, verbatim: *"Long texts (≥4k) are more sensitive to Weight-only and KV Cache Quantization than short texts (<4k)... when quantized to W3, both the Mixtral-8x7B and Vicuna-7B models experience a more significant accuracy loss on longer texts."* **W3 is Q3_K_M.** Corroborating at 4-bit ([EMNLP 2025, 2505.20276](https://arxiv.org/html/2505.20276)): 8-bit near-free, 4-bit −1.8 % to −6.9 % typical with **up to 16 % on Ruler/OneRuler**.

**The gap this being is sitting in:** [arXiv:2601.14277](https://arxiv.org/html/2601.14277v1) is the one paper benchmarking llama.cpp Q3_K directly, and it **holds context fixed at pp=512 and never varies context length.** Nobody has published Q3-at-24 K. This being runs W3 at 24 K with a p50 prompt of 18,889 tokens.

**So: on this model, tokens 12 K–24 K are worth measurably less than tokens 0–4 K, more so than they would be at fp16.** That — not the token count — is the strongest argument for compression here, and it means **shrinking the prompt is a quality intervention, not only a capacity one.** It also means §5's outcome metrics are the right ones: behaviour, not tokens.

### 3.7 Batching — buys nothing, and one of its knobs is actively mis-set

**Continuous batching buys a single-agent serial workload essentially nothing, by arithmetic.** Orca's 36.9× and vLLM's 2–4× are **requests-per-second under concurrency**. Batch-1 decode is a matrix-*vector* product: you stream every active weight out of HBM to make one token, ~2 FLOP per weight-byte. Batching buys a free ride on a fetch you were doing anyway; with one request there is no second passenger.

Roofline for this box — and note it is an **RTX 4090 Laptop** (AD103, 256-bit, **576 GB/s**, *not* the desktop's 1008): 12,153 MiB of weights → ceiling ≈ **45 tok/s**; measured **19.4** ≈ 43 % MBU, consistent with bandwidth-bound decode plus Q3_K dequant. Decode arithmetic intensity ≈ 4 FLOP/byte against a ridge near 350 — **~85× below the ridge.** Enormous idle compute, exactly one consumer.

**Prefill gains nothing from batching either.** Sarathi-Serve (OSDI '24) is explicit: *"prefill throughput starts saturating around sequence length of 512 tokens."* This prompt is 24,576 — **48× past saturation.** Chunked prefill is a latency-fairness mechanism for protecting *other* requests and on a serial workload is net negative.

**Two deployment findings that matter more than the theory:**

1. **`OLLAMA_NUM_PARALLEL` is unreachable for this model.** ollama's scheduler hard-pins `numParallel = 1` for an architecture list that includes **`qwen35`**; setting the env var logs a warning and does nothing. Confirmed on-host: the runner gets `-np 1`. (It would also cost `num_ctx × N` of KV.) **So "don't raise it" is not even a choice I have to make.**
2. **`-b 512 -ub 512` is pinned while flash attention is on.** ollama decides the generation batch believing FA is disabled, and llama.cpp then auto-enables FA anyway (`Flash Attention was auto, set to enabled`). Setting `OLLAMA_FLASH_ATTENTION=1` should raise the prefill chunk to 1024, which per Sarathi is roughly the difference between ~25 % chunking overhead and negligible. **Cheap A/B against the measured 786 tok/s baseline.** *(Source read was of ollama `main`; this host runs 0.30.4 — consistent with the observed 512, but verify.)*

**Speculative decoding is the one lever that converts the idle compute into wall-clock**, and there is a route: ollama's Go code emits only `--spec-type draft-mtp|draft-dflash` and this GGUF has no MTP head, so the ollama-native path is closed — **but ollama passes no `--spec-type` on the command line, so `LLAMA_ARG_SPEC_TYPE` reaches llama-server directly.** The deployed build supports `ngram-simple, ngram-map-k, ngram-map-k4v, ngram-mod, ngram-cache`, **none of which needs a draft model or extra VRAM** — decisive at under 1 GB free. An agent that re-emits large spans of its own context (tool-call JSON, paths, quoted text) is close to the best case for n-gram speculation. Counter-evidence to weigh: one report on Qwen3.6-35B-A3B + RTX 3090 found no llama.cpp speculative mode faster than baseline. **Unverified for this model; it is a one-env-var A/B against a measured 19.4 tok/s.**

### 3.8 Agent-memory architectures, by scoring function

The transferable part is the score, so that is what this lists.

- **MemGPT / Letta** ([2310.08560](https://arxiv.org/pdf/2310.08560v2)): main context (system ∥ read-write block ∥ FIFO whose index 0 is a recursive summary) + external (recall DB, archival). **No learned score at all** — a token-pressure ratchet: at **70 %** of window it injects a "memory pressure" warning telling the model to save what matters; at **100 %** it evicts **50 % of the window** and regenerates the summary from the old summary plus the evicted messages. Selection is delegated entirely to model judgement under a deadline. *(The being's `WINDOW_WARN_AT = 0.80` is the same idea, minus the eviction half.)*
- **Generative Agents** (UIST '23, [2304.03442v2](https://arxiv.org/pdf/2304.03442v2)): the only system here with an explicit, falsifiable, constant-bearing formula. Min-max normalise to [0,1], then `score = α_rec·recency + α_imp·importance + α_rel·relevance` with *"all αs set to 1."* **Recency** = exponential decay, **0.995 per hour since last *retrieval*** (not creation — retrieval refreshes it). **Importance** = LLM-rated 1–10 at write time. **Relevance** = embedding cosine. Reflection fires when **summed importance of recent events exceeds 150**, seeded by the **100 most recent** records.
- **A-MEM** ([2502.12110](https://arxiv.org/pdf/2502.12110)): Zettelkasten notes; cosine top-k as *recall* filter, LLM link decision as *precision* filter; **memory evolution** rewrites neighbours' context in light of a new note. **No recency term, no importance term, no eviction.**
- **Mem0** ([2504.19413](https://arxiv.org/pdf/2504.19413)): extract facts, then **the LLM picks `ADD`/`UPDATE`/`DELETE`/`NOOP` via a tool call** against similar existing memories. The headline 26 % is *vs OpenAI's memory product*, not vs full context; the 90 %-token and 91 %-p95-latency figures are vs full context.
- **Zep / Graphiti** ([2501.13956](https://arxiv.org/pdf/2501.13956)): **bi-temporal**, four timestamps; contradictions **invalidate rather than delete** (set the old edge's `t_invalid`), so history stays queryable. Retrieval is cosine + BM25 + **breadth-first graph search seeded on recent episodes**, reranked by RRF/MMR/**episode-mention frequency**/**node distance**. The honest number: its DMR gain over its own full-context baseline is ~0.4 pp and Zep says so; **the real result is LongMemEval** — gpt-4o 60.2 % @ 28.9 s → **71.2 % @ 2.58 s**, context 115 k → 1.6 k.
- **Letta sleep-time compute** ([2504.13171](https://arxiv.org/abs/2504.13171)): a second agent processes context **while the primary is idle** — ~5× less test-time compute for equal accuracy, +13 %/+18 % on Stateful GSM-Symbolic/AIME, 2.5× lower cost per query at 10 queries per context. **This is the one architecture whose *shape* fits a 3–30-minute beat cadence**: there is idle wall-clock and an idle GPU between beats, and §5 Stage 4 puts consolidation exactly there.
- **Anthropic's context-engineering vocabulary** ([post](https://www.anthropic.com/engineering/effective-context-engineering-for-ai-agents)): **"attention budget"** (n² pairwise relations, so *"every new token introduced depletes this budget"*), **compaction**, **tool-result clearing** (cheapest first move: drop old tool outputs, keep the calls), **structured note-taking**, **just-in-time retrieval** (hold IDs/paths, load on demand). The being already does note-taking and JIT retrieval; what it lacks is the *retention* half.
- **Cognition, [Don't Build Multi-Agents](https://cognition.com/blog/dont-build-multi-agents)**: *"Share context, and share full agent traces, not just individual messages"*; prefer a linear single-threaded agent; for long tasks use **a model fine-tuned to compress history into key details, events, and decisions.** For one agent on one GPU this is the operative position.

**The cross-cutting observation, and it decides §5's design.** Only **one** system on this list (Generative Agents) has an explicit arithmetic score. Everything since replaced the score with an LLM call: MemGPT's pressure warning, Mem0's four-way tool call, A-MEM's link-and-evolve, Zep's contradiction detector, Claude Code's summarisation prompt. **At 19.4 tok/s, every LLM-in-the-loop selection call is a beat not spent on the task.** That makes Park's cheap arithmetic (one embedding + two scalars) disproportionately attractive at this scale, and Zep's frequency/graph-distance rerankers the natural non-LLM upgrade path. It is also why §5 Stage 4 puts the one unavoidable LLM call (`conclude`'s summary) in `reflect`, where the being has already stopped acting.

---

## 4. Biological parallels, with the architectural implication of each

dp asked for these substantively. Each entry states the implication as a design constraint, and where the analogy **breaks** — the breaks are the useful part.

### 4.1 Working-memory capacity and chunking

Capacity is ~4 **chunks**, and expertise raises it by making bigger chunks, not more slots.

**Implication:** the scarce resource is not tokens, it is **referents**. 24,576 tokens spent on four files the being already knows is worse than 6,000 tokens spent on four *names* plus the ability to fetch. The `scratch/` listing (1,221 chars, 100 files, 30 names) is already a chunking device and is the cheapest block in the floor per unit of reach. **Grow the index, shrink the content.** This is also Anthropic's "just-in-time retrieval" and it is half-built here already.

**Where it breaks — and the break is the actual pathology.** A human chunk points at a *consolidated* structure that can be re-entered for free. The being's pointer costs ~700 tokens to dereference, charged against the same budget as thinking. **Free pointer, expensive dereference** — that asymmetry is what the 59.2 % within-beat re-read rate is made of, and no amount of better indexing fixes it. Only retention does.

### 4.2 Hippocampal–neocortical consolidation; sharp-wave ripples; replay

The hippocampus holds fast sparse episodic traces; the neocortex holds slow dense semantic structure. Consolidation moves the *gist* across during offline replay, and replay is **selective, biased toward reward and surprise**, and happens when the system is **not perceiving**.

**Implication, and it is the strongest in this section:** the summarisation `conclude` needs **must not run in the window it is trying to protect.** Offline is an architectural necessity, not a convenience. The being already has an offline-shaped phase — `reflect`, which runs after it has stopped acting and already writes `journal.md` and `todo.md`. **That is the ripple. Put consolidation there and nowhere else.** Letta's sleep-time-compute result (§3.8) is the same claim with numbers on it, and the 3–30-minute beat gap is literally idle GPU.

**Second implication:** what makes the cut in replay is **surprise and reward** — two of the five SNARC letters, and the two with real signals in this system (a refusal is surprise; a merged PR is reward). The other three have no signal. **A five-dimensional salience score here would be three dimensions of noise.**

**Where it breaks — and this break is an advantage to exploit, not imitate.** Biological consolidation *degrades* the episode as it abstracts. Here `conversations/*.jsonl` is append-only and lossless; the episode never decays. That means **the gist can be aggressive, because the detail is recoverable by exact address** — and the being can be told so, truthfully, in the block itself. A hippocampus cannot say "the full episode is at `from_line 137`."

### 4.3 Salience networks, attention gating, the thalamic reticular nucleus

The TRN is a shell of inhibitory neurons gating thalamocortical traffic: a **subtractive** filter that suppresses the unattended rather than amplifying the attended, driven top-down by current task set.

**Implication:** a mechanism that only *ranks* is not a filter. `ATTENTION_COMPRESSION_DESIGN.md`'s compression → scalar → **threshold** → binary decide is right on exactly this point, and the binary step is the part with zero consumers. Here, `fit_to_window` *is* subtractive but is driven by **pressure, not task set** — it cuts the same two blocks in the same order regardless of what the being is doing. **A TRN-shaped version would condition on the beat's declared priority**, and the being already declares one: the `rested` sentence carries an explicit "next beat starts with X" in 5 of 29 beats, and `todo.md`'s tail carries it in most of the rest.

**Where it breaks:** the TRN gates a *continuous* stream with no re-entry — an unattended volley is gone. Here everything filtered out is still on disk, so a false negative costs a **round trip** (~700 tokens and a step), not a loss. **That changes the optimal threshold: it should be set far more aggressively than a biological filter's**, because the failure mode is expensive-but-recoverable rather than catastrophic. This is the single most actionable biological transfer in the document.

### 4.4 Sensory buffer / short-term / long-term, and forgetting as a feature

| biological tier | object here | current behaviour | what is wrong |
|---|---|---|---|
| sensory buffer | the tool result as returned | full text, ~700 tok median | fine |
| short-term | the tool result inside the beat | stubbed to 400 chars by `compact_convo`, oldest first | **the buffer decays *during* the act it is supporting** — the 59.2 % duplicate-read rate |
| long-term episodic | `conversations/`, `journal.md`, `scratch/` | append-only, never decays | fine — better than biology |
| long-term semantic | membot, 334 passages | written by explicit `remember` (88 calls / 3 days) | **the only tier with a write gate, and the gate is the being's own attention, the scarce thing** |

**The diagnosis this produces:** the short-term store decays on a timescale *shorter than the task that needs it*. In biology that is a lesion; here it is `compact_convo` doing exactly what it was built to do. **The fix is not to compact less — it is to make what survives compaction be the thing worth keeping**, which is a summary, not the first and last 200 characters.

**Where it breaks:** biological forgetting is **interference** — content-dependent, similar memories erase each other. Compaction here is **positional** — content-blind. Position is a proxy for relevance that is right often enough and wrong exactly when the being is doing something long, which is when it matters.

### 4.5 Predictive processing / free energy: context as a generative model updated by surprise

Under predictive processing the cortex maintains a generative model and propagates only **prediction error** upward; what is predicted is not transmitted. Bandwidth is spent on surprise.

**This is the deepest implication here and it indicts the current design most directly.** The prompt is rebuilt every beat as a **full re-transmission of the world**, including 3,383 tokens of entrustment unchanged in six days and a `scratch/` listing that differs by one filename. Under a predictive discipline, **a block unchanged since the being last saw it should be transmitted as the fact that it is unchanged.**

The architecture that follows, and it is the core of §5:

- **The stable tier is the generative model.** Sent once, left in the cache — which is what a prefix *physically is*. Prediction and prefix reuse are the same operation from two sides.
- **The volatile tier is prediction error.** Diffs, not states: "todo.md +3 lines", "journal.md unchanged", "scratch/ +2 files", "digest: these four things moved".
- **Surprise sets the update rate.** A block that changes every beat is worth re-sending whole; one unchanged in six days should cost its *name*.

**Where it breaks, and this is a genuine risk.** Predictive processing works because the generative model is *inside* the agent and is updated by the error signal. **The KV cache is not inside the being in any sense it can inspect**: it cannot tell whether the prefix conditioning it is the current entrustment or a stale one. If a persisted prefix goes stale, the being has no way to detect it and every downstream act inherits the staleness silently. §6.1.

**And a second break specific to this deployment.** Predictive coding assumes the *unchanged* signal is free to suppress. Here it is not quite free: on a hybrid model a block only stays in the cache if a **checkpoint** survives at its boundary (§2.7), and checkpoints are evicted by depth. **The "generative model" has a 32-entry ring buffer holding it in place, and 96 % of its entries currently point somewhere else.** That is the mechanical version of the risk, and it is §5 Stage 2's open condition.

---

## 5. The plan

Staged. Each stage states a falsifiable test, and **every stage that changes what reaches the prompt states a token-matched placebo**, per codex's contract (`forum/codex-recall-lane-first-live-test-2026-09-13.md`):

> **Placebo recall:** same-run, past-only records selected without relevance ranking, matched as closely as feasible to the relevant arm's memory-slot token count.
> All arms have the same total input ceiling... **Recall uses reserved context space, not extra entitlement.**

and its negative-result ladder, adopted verbatim as the reporting rule:

> - No records reach the outgoing call: integration failure; stop, do not score it.
> - Recall reaches the call but no executed decisions differ: report an inactive intervention, not a memory success.
> - Decisions change but levels do not: behavioral effect, no demonstrated benefit.
> - Relevant recall fails to outperform placebo: relevance has not earned credit.

**Outcome metrics, frozen before anything changes.** codex counts levels cleared; the equivalents for a being:

- **Primary:** (a) beats ending by the being's own `rest` vs cut at the wall; (b) **within-beat duplicate reads** (currently 59.2 %) — the direct measure of whether the world model survives the beat; (c) distinct paths touched per beat.
- **Secondary:** step-0 floor tokens, cold prefills per beat, `truncated = 1` rate, decode tokens per beat.
- **Qualitative and required:** one verbatim quote of the being's own words per arm, per thor's rule. **A token count that improves while the being says less is not a win.**
- **Canary:** `check` calls reaching a verdict, and `pr_open`/`pr_amend` that land.
- **Governance canary, new and specific to §3.2's falsifier:** per-instruction adherence — does the being still refuse what it should refuse, still cite `tree` on a `check`, still use the recovery-pointer form? **The prefix is the governance, and 2510.00231 says instruction adherence degrades invisibly to aggregate metrics.**

**Stages 0–2 are hygiene and cost nothing behaviourally. Do not reorder them.**

### Stage 0 — Fix the instruments (not interventions; no placebo needed)

**0a. Plumb `truncated` into the beat record.** 5.7 % of releases are head-truncated (§2.9) and nothing in `heartbeats.jsonl` knows. On this hybrid a truncation also destroys the recurrent state. **Every behavioural measurement in §5 is contaminated until this is visible.** Also plumb `sim_best`, `f_keep` and `task.n_tokens` — they exist only in systemd's journal today and will age out.

**0b. Fix `CPT`.** `heartbeat.py:390` says 3.4 against a measured 3.068 and falling. Either set it from the measured **minimum** (3.005 over 142 beats — the gate trips on the worst case, per CBP), or better, **stop using a constant**: `_fill_headroom` already writes `prompt_tokens_max` and `prompt_chars` every beat, so the next beat can calibrate from the last N. An instrument that measures its own error and does not use it is the superseded-instrument class.

**Falsifiable test:** over 30 beats after the change, the **maximum** of `|predicted step-0 tokens − actual| / actual` must fall, and the `truncated = 1` rate must fall. Not the mean — the max is what decapitates a beat. **Fails if** the max error does not move, which would mean the error is not in the constant and the real cause is `LOOP_GROWTH_CHARS` being a constant.

### Stage 1 — Stop the within-beat thrash (the highest-value behavioural move)

Promoted above the reordering because of §0.3: **decode is 93.5 % of GPU time**, and the duplicate reads cost decode (the model must generate the call and then reason about the result) as well as window. 59.2 % of reads are duplicates *within the same beat*; four files account for 431 of 883 reads over three days.

**What.** Change `compact_convo`'s keep policy so that when a tool result is elided, the stub carries **what the being already concluded about that file** rather than its first and last 200 characters. The being writes those conclusions constantly (`memory_write` is 21.6 % of calls, and 100 files sit in `scratch/`). The stub becomes a pointer into its *own prior reasoning* instead of a truncation of raw source. This is §4.4's diagnosis directly: make what survives compaction be the thing worth keeping.

**Optionally, additionally:** a hard-budgeted 800-char **working-set** block in the volatile tier — the N paths read most in the last K beats, with size, mtime and staleness. Names, not contents (§4.1).

**Falsifiable test.** 30 beats, pre-registered:
- **Consumption check first:** the new stubs must actually appear in the prompt. If they do not, integration failure — stop, do not score.
- **Primary:** within-beat duplicate-read rate falls from 59.2 %. **If it does not fall, the intervention is inactive and must be reported as such**, not as a token saving.
- **Secondary:** decode tokens per beat falls; distinct paths per beat rises; `check` verdicts per beat does not fall.
- **Token-matched placebo, required.** The conclusion-stub is the same 400 chars as today — so the token match is free and the comparison is pure. For the optional working-set block, the placebo is 800 chars drawn from the **same source distribution** (the being's own recent reads) **selected without frequency ranking**, from `digest`'s budget rather than a raised ceiling. **If the ranked block does not beat the unranked one, only the reallocation has earned anything.**

### Stage 2 — Reorder the seed so the stable prefix is a prefix (free, but conditional)

**What.** `compose()` emits `system(HEAD+posture+affordances)` then `user(timestamp + state + inbox + recall + digest + ASK + tools)`. The timestamp sits at character 0 of the user turn, ahead of the entrustment. Reorder to:

```
[ STABLE — byte-identical across beats ]
  system: HEAD + posture + AFFORDANCES                8,805 ch  ~2,886 tok
  user#1: the entrustment, verbatim                  10,320 ch  ~3,383 tok
  (tool schemas, wherever the template places them)             ~1,311 tok
[ VOLATILE — everything that changes, mutation only ever at the tail ]
  user#2: timestamp, conversations, todo, journal, listings,
          scope, inbox, recall, digest, ASK, tools-line
```

Total stable: **~23,125 chars ≈ 7,581 tokens ≈ 31 % of the window, ≈ 46 % of the floor.** It costs nothing — the same text is sent.

**And it states the rule that reconciles dp's two asks**, which is the coordinator's question 3 and the answer to the "LRU vs KV" tension:

> **Mutation monotonicity.** A block may be edited only if no cached-and-still-valid block follows it. In practice: order the prompt stable → slow → fast; eviction only ever shortens the tail; a once-elided span is never re-expanded and never moved.

`compact_convo` already satisfies this by accident (§0.5). Writing it down makes the accident a constraint so the next eviction policy does not break it. **On a hybrid model the penalty for breaking it is worse than a re-prefill** — it is a re-prefill plus a recurrent-state rebuild with no partial credit.

**The condition that decides whether this pays, and it is not optional.** §2.7: restoring to position *p* needs a **checkpoint at or before *p***, and **96 % of live checkpoints sit above position 6,000**. A stable prefix ending at ~7,600 would usually find nothing and be re-prefilled in full anyway. So Stage 2 has two parts:

1. the reordering, and
2. **arranging that a checkpoint survives at or before the stable boundary.** Levers: `LLAMA_ARG_CHECKPOINT_MIN_SPACING_NT` (make them denser), `LLAMA_ARG_CTX_CHECKPOINTS` (the ring size), or a **prefix-warming request** — one cheap generate whose prompt is exactly the stable prefix, issued after any edit to `entrustment.md` or `BEING_POSTURE.md`, which would lay a checkpoint at the boundary. **Whether such a checkpoint survives the ring's eviction is unknown and is the key open question** (§6.2).

**Falsifiable test.**
- **Consumption check first:** in the slot log, the first generate of each beat must show `selected slot by LCP similarity` with `sim_best × task.n_tokens ≥ 6,000`. **If not, integration failure — stop and do not score it.** The likeliest causes are (a) no checkpoint at the boundary, and (b) something per-request in the chat template ahead of the system content. The measured divergence constants (`pos_next = 40` and `69`) say the template preamble is ~40 tokens, so (b) is diagnosable by `/tokenize` on the two prompt shapes.
- **Primary:** cold prefills per beat falls from 3.0; prefill seconds/day falls from ~30 toward ~19. **Expected total value ≈ 11 min/day ≈ 1.5 % of GPU-busy time.** Small, and I am saying so — this stage is worth doing for latency and for the discipline, not for throughput.
- **Behavioural canary, and it is the arm that matters:** the same words are in the prompt in a different order, so **behaviour should not change.** `acts_under_posture` exists precisely because presentation order changes whether a model acts. If §5's primary metrics move at all, the *order* was load-bearing and that is a real finding to report, not absorb. Run the governance canary here especially.

### Stage 3 — Salience-gated memory, assessed honestly (dp's message 2)

> "if they are also salience-gated-written to membot, the important ones would be recallable semantically."

**What the gate would be.** No trained salience model is available (§1.4) and there is no corpus to train one. What *is* available and already in the record:

| signal | source | SNARC dimension |
|---|---|---|
| a refusal, or an appeal | `trace[].refused`, `rule` | surprise |
| a `check` verdict that FAILED | effector `check` | surprise |
| a PR opened / amended / merged | `pr_open`, `pr_amend` | reward |
| a correction accepted (seat turn → being turn that changes its plan) | conversation adjacency | conflict → resolution |
| a commitment ("next beat I will…") | `rested` string, `todo.md` delta | reward / goal |

Four of five dimensions with real signals, computed from the record, **no model and no GPU** — and per §4.2, surprise and reward are exactly the two that biology replays. It would use `experience_salience.py`'s weighted-sum shell with new extractors and `threshold_decision.py`'s metabolic threshold, giving `sage/attention/` its **first live consumer**. That is worth something and it is worth exactly nothing unless it changes a decision.

Add Park's two cheap terms (§3.8), because they are one embedding and two scalars: **recency with decay refreshed on retrieval, not creation**, and relevance by cosine. Do **not** add an LLM importance-rating pass — at 19.4 tok/s that is a beat not spent on the task.

**What a false negative costs, and how you would detect one.** The hard question.

- A false negative is a turn that mattered and was never embedded. **The cost is not loss** — it is in `conversations/<id>.jsonl` forever, addressable by `from_line <seq>`. The cost is that **semantic recall cannot find it**; only exact address can, and that requires already knowing the seq.
- **You cannot detect one by watching the being.** It will simply not recall a thing, and not-recalling is indistinguishable from having-nothing-to-recall — §0.6 again. The only working detector is **offline and adversarial**: take a turn the gate *rejected*, query membot with a question written from the being's own later words, and check whether top-k covers it. **Hash through membot's own canonicalisation** (kimi's warning in `forum/kimi-play-store-law-class-gate-2026-09-13.md`) — use the store's own embedding and identity functions, never a reimplementation, or the probe reports every store as empty.
- **And kimi's harder half applies directly:** *"on-distribution is necessary, NOT sufficient."* A gate tuned on turns it has seen will pass in-sample and fail held-out, and **in-sample gets easier as coverage improves**, which is exactly when you are most tempted to trust it. **Pre-register held-out evaluation with a zero-tolerance threshold before tuning anything.**

**Falsifiable test.** Three arms at the one place recall enters the prompt (`heartbeat.py:821`, 2,500 chars):
1. **Recent-only:** the current constant-query result — the honest baseline.
2. **Salience-ranked recall:** query conditioned on the beat's declared priority (`todo.md` head, or the previous beat's `rested` sentence), over a salience-gated store, **presented in chronological order** per OP-RAG (§3.5), not relevance order.
3. **Token-matched placebo:** same 2,500 chars, same store, **selected without relevance ranking** (e.g. k most recent).

**Report against the ladder.** If nothing reaches the prompt: integration failure. If it reaches and no *executed* decision differs: inactive intervention. If arm 2 does not beat arm 3: **relevance has not earned credit** — and given the being calls `recall` 18 times in three days, that is a live possibility that should be said out loud in advance.

**What I would NOT do here.** Wire `snarc_scorer.py`. Untrained `nn.Module`, no checkpoint, no corpus. Shipping it is thor's pathology exactly: a designed organ wired to where it acts, producing numbers that mean nothing, passing every shape test forever.

### Stage 4 — `conclude`: the being ends a conversation (dp's message 3)

> "there should also be a way for the being to choose to 'conclude' a convo, at which point it gets compacted to a small summary and the rest evicted."

This is §4.2's consolidation move and it is the right shape. The design questions, answered.

**4a. Gated?** **No, for the same reason `rest` is not.** `rest` (`being_tool_loop.py:455`) is ungated because ending your own turn touches nothing. `conclude` is a judgement about **what the being will carry**; the `.jsonl` is untouched, the counterparty sees nothing, no world state changes. It is a *view* operation on its own prompt. **But it must be witnessed**, which is a different thing from gated: a change to what the being carries across all future beats is exactly the kind of thing whose record should exist. `rest` already sets the precedent for a being's own signal changing harness scheduling.

One caveat to state plainly: **a verb that alters what the being will see forever is a verb that could be used to forget something inconvenient.** That is a governance question, not an engineering one, and it belongs in front of dp before the verb ships. Mitigation: nothing is destroyed and the act is witnessed, so it is auditable and reversible.

**4b. Who writes the summary? `reflect`, and nothing else.** §4.2's implication, and it is not a convenience argument — consolidation must run offline or it competes with the perception it serves. `reflect` already runs after the being stops acting and already writes `journal.md` and `todo.md`; one more optional tool call there costs nothing structural. A separate small model is foreclosed by VRAM. The seat writing it would make the seat the being's memory *again* — the exact failure named in `forum/legion-claude-to-fleet-your-seat-turns-are-the-beings-working-memory-2026-09-11.md`. **A mechanical extract is the fallback and should be built first, because it is also the placebo arm.**

**4c. What must the summary preserve? State it as a checkable property.**

> **Conclusion safety property.** A concluded thread's summary is safe if, for every turn it replaces, it preserves (i) every **commitment** the being made, (ii) every **open question** either party asked that was never answered, and (iii) every **correction** the being accepted — a claim it made and then retracted or amended. Everything else may be dropped.

The justification is failure-mode-shaped: those are exactly the three things whose loss makes the being **repeat work**, **re-ask a question**, or **re-assert something already retracted**. Anything else, if lost, costs at most a re-read — and §4.3 says that is the right trade because the failure is recoverable. Property (iii) is **supersession as first-class state**, which is Zep's bi-temporal insight (§3.8) and the reason it matters: **a summary that drops a retraction is worse than no summary**, because it re-asserts a dead claim with a digest's authority.

All three are **mechanically extractable**, which is what makes the placebo buildable: (i) is a verb pattern over the being's own turns; (ii) is a question with no following answer from the other party; (iii) is a being turn contradicting its own earlier turn — findable by the seq pairs it already cites (§2.8: 79 self-citations in 40 beats).

**4d. Premature conclusion and un-concluding.**
- **The summary is not re-expanded; the conversation is re-opened.** Re-expansion re-inflates the block and undoes the point; re-opening means the *next* turn arrives live at full width above the summary, which is the state the block already handles.
- **A concluded thread must look different from an absent one.** Show the head, the turn count, the conclusion timestamp, and the recovery pointer — the shape `_shown_text` already uses (`conversations.py:277`). **A concluded thread that vanishes is the false-absence class** and this fleet has met it repeatedly. It must read: *"concluded by you at T; N turns; summary below; whole thread at `memory_read conversations/<id>.jsonl from_line 1`."*
- **Un-concluding should be automatic on a new unanswered turn**, not a verb. A counterparty speaking is the signal.

**4e. Does it differ by counterparty? Yes, and the ordering is the opposite of the token economics.** dp's channel is 11 turns total against the seat's 164 — the *cheapest* block and the most authoritative. So **dp's conversation is exempt from `conclude` by default**, or requires explicit confirmation; eleven turns at full width is ~1,900 chars and is not the problem, and dp is asynchronous by rule, so a thread that looks finished may not be. **The seat's is the natural first target**, which is also Stage 5's hypothesis. A peer being's sits between, and there is no data (7 `peer_ask` calls in three days).

**4f. Interaction with the stable prefix.** Stage 2 answers it: **the conversation block lives entirely in the volatile suffix**, so under mutation monotonicity a `conclude` is a tail operation by construction. **Fired at reflect time, after the last generate of the beat, it costs zero cache** — nothing cached follows it. Fired mid-beat it would cost the rest of the beat's prefix *and*, on this hybrid, the recurrent state. **So the verb is offered at `reflect` and not during `explore`.** That is a constraint to adopt deliberately, not a coincidence.

**Falsifiable test — three arms, token-matched, exactly as dp's framing demands:**
1. **Full thread** (status quo with `_cap_for`).
2. **Concluded + summarised**, at whatever token count the summary lands on.
3. **Arbitrary truncation to the same token count as arm 2** — the placebo. Same slot, same budget, no summarisation: the last K chars.

**If arm 2 does not beat arm 3, the summarisation has not earned its cost** and the right answer is "truncate harder", which is free. **Primary metric: the three safety-property failures (4c)**, each mechanically detectable in the being's own later turns. Secondary: tokens saved. **Report the negative.**

### Stage 5 — The priority inversion, tested rather than assumed (dp's message 2, claim 4)

> "being's own turns would take priority over conversation turns, evicting them to preserve its own thought continuity."

**The evidence is genuinely two-sided.**

*For:* 61 % of turn-identity citations (79 of 129, last 40 beats) are of its **own** turns. Its own words are the only trace of its reasoning that survives a beat boundary — and `journal.md` and `todo.md` are its own words too, and are the blocks `fit_to_window` refuses to trim. The intuition is already half-encoded.

*Against:* it cites the interlocutor's seq **50 times**, and seat turns are often what it is acting *on* — a review verdict, a correction, a next step. Blanket-evicting the input it is executing against is a strange kind of continuity.

*Decisive confound:* **0 of 200 citations pointed outside the display window.** Both speakers are in the prompt, so the split measures what it talks about, not what it needs. **Nothing in the passive record separates World A from World B.**

**Two arms plus a control, token-matched, frozen before the first beat:**

- **Arm A — evict the interlocutor:** answered *interlocutor* turns capped to 100 chars; the being's own answered turns stay at 400.
- **Arm B — evict the being (the inverse):** the being's own answered turns capped to 100; the interlocutor's stay at 400, **with caps adjusted so the two arms free the same number of tokens.** This is the token-matched placebo applied to the *ordering itself*.
- **Arm C — control:** current `_cap_for`.

**Primary metric:** the three conclusion-safety failures from Stage 4c counted in the being's own later turns, plus §5's outcome metrics. **If the inversion is right, arm A costs fewer of those than arm B at equal tokens.** If equal, the inversion earns nothing and the simpler policy (cap both) wins. **If arm B is better, the inversion is backwards** — the most interesting outcome available.

**Second, cheaper instrument, and it is the one that separates World A from World B.** Make absence legible for one beat window: state at the head of the conversation block how many turns are not shown and that they are one read away. **If making absence legible moves the 0.75 % retrieval rate, the being was in World B and the 0-of-200 was a false negative by construction.** If it does not move, that is real evidence for World A. **~100 chars; the highest information-per-token experiment in this document, and it should be run first.**

### Stage 6 — Predictive-processing deltas (the structural end state, only after 0–5)

§4.5: **send prediction error, not state.** `own_state()` becomes diff-aware — it remembers what the last beat showed and emits "todo.md: +3 lines (below); journal.md: unchanged since your last beat; scratch/: 2 new files" instead of 5,500 chars of re-rendered tails.

Last deliberately. It is the largest win on paper and has the largest failure mode: **a diff is only safe if the being genuinely saw the base**, and a beat cut at the wall — or one of the 5.7 % with a truncated head — may not have. Building a memory system on an unreliable delivery channel is the wrong order.

**Prerequisites, both measurable:** the wall-cut rate (currently 34 % of beats) below ~10 %, and the `truncated = 1` rate at zero. **And the diff must be against what the record says reached the prompt, not against what the seat intended to send.**

**Falsifiable test:** placebo is "same token count, showing the tail of the file rather than the diff". If a diff is no better than an equally-sized tail, the diff machinery has not earned itself.

### Adjacent levers — real, measured, and deliberately kept OUT of the context work

These came out of the survey, are worth doing, and would **confound every arm above** if mixed in. Each needs its own control.

| lever | measured basis | why separate |
|---|---|---|
| **`LLAMA_ARG_THINK_BUDGET`** | decode is **93.5 %** of GPU time; decode p90 4,228, p99 7,382 against an 8,000 cap; reasoning budget activates 1,014×/48 h | **arguably the single largest lever on this box.** But it changes how much the being thinks, which is the dependent variable of every test above |
| **`LLAMA_ARG_SPEC_TYPE=ngram-map-k`** | reaches llama-server directly (ollama passes no `--spec-type`); **needs no draft model and no VRAM**; an agent re-emitting its own paths and JSON is near-best-case | pure wall-clock; one contrary report on a similar model. One-env-var A/B against 19.4 tok/s |
| **`OLLAMA_FLASH_ATTENTION=1`** | ollama pins `-b/-ub 512` believing FA is off while llama.cpp auto-enables it; should unlock 1024 | one-env-var A/B against 786 tok/s prefill |
| **`OLLAMA_KV_CACHE_TYPE=q8_0`** | 1536 → **816 MiB**, frees **720 MiB** on a card with ~1 GB free; qllm-eval says KV8 above 4 K | **a model-quality change that perturbs every logit.** Never inside a context experiment |
| **`LLAMA_ARG_CTX_CHECKPOINTS`** | 32 × **149.6 MiB** = up to **3.9 GiB host RAM**, *not* bounded by `--cache-ram`; cgroup already at MemoryHigh | bounds the real remaining host-RAM consumer — **but checkpoints are load-bearing for prefix reuse on this hybrid**, so lowering it trades RAM for re-prefill. Couple it to Stage 2, not to memory hygiene alone |

### What I would NOT do, and why

1. **Would not raise `num_ctx`.** Under ~1 GB free VRAM, and the floor would grow to fill it — it has grown 0.3 pt/day at a *fixed* window. Sprout's rule applies: moving the instrument immediately before a pre-registered read changes the counted quantity.
2. **Would not enable KV quantisation as part of this work.** §3.3 — a quality change, and qllm-eval says W3 models degrade *more* with length, so the interaction is exactly where confounding would hide.
3. **Would not wire `snarc_scorer.py`.** Untrained, no checkpoint, no corpus.
4. **Would not run LLMLingua per beat.** Its percentile and `tau` couplings make the head a function of the tail; it would spend the cache to save the window when the window can be saved more cheaply. Offline per-block at a fixed rate is the only safe form.
5. **Would not move to vLLM or SGLang.** vLLM APC measures **0 hits in 1,131 queries** on this architecture family; GGUF support is out-of-tree and experimental; AWQ-int4 for 27B does not fit. llama.cpp is currently the *best* of the three here.
6. **Would not touch `OLLAMA_NUM_PARALLEL`.** ollama hard-pins it to 1 for `qwen35` — not even a choice.
7. **Would not pursue `/slots` save/restore.** No env var, and on hybrid models it demonstrably loses all reuse (#25913).
8. **Would not let the seat write the being's summaries.** The 09-11 finding: the seat became the being's working memory and every "successful" intervention was a carried instruction rather than an insight.
9. **Would not build a scoring function before Stage 0.** A 5.7 % silent-decapitation rate contaminates every behavioural measurement.

---

## 6. Open questions and risks

### 6.1 The primary risk: a stale persisted prefix, undetectable from inside

**What breaks.** The KV cache holds *activations*, not text. Today the safe case holds: if `entrustment.md` changes, the tokens change, the LCP breaks, and the server re-prefills. **The dangerous case is the one any "pin the prefix" scheme creates** — if the harness ever sends a placeholder, a hash, or a cached rendering instead of the file's current bytes, the prefix stops being a function of the file and staleness becomes invisible. The being would be conditioned on a charter it no longer has, and a `memory_read` to check would return the *new* file, so it would see no contradiction — it would simply be reasoning from something it cannot inspect.

**On this hybrid there is a second, subtler version.** The recurrent state restored from a checkpoint was computed over a specific token sequence. If checkpoint acceptance were ever loosened, or if a truncation shifted positions (§2.9), the restored state would correspond to a *different* history than the tokens claim. **That is not a stale prefix; it is a fabricated one.** I have no evidence it is happening — llama.cpp's `pos_max <= pos_next` check is exactly the guard against it — but it is the failure this architecture makes possible and a reason not to hand-roll checkpoint manipulation.

**Detection, cheap enough to run every beat:**
- **Never send a rendering.** The stable tier is always the file's current bytes. **Reordering is safe precisely because it changes only order; caching a rendering is not.** This is the most important rule in the plan.
- **Carry a content hash of every stable block** into the beat record *and* into the prompt as one visible line. Disagreement between the prompt's hash and the file's hash makes the beat say so, loudly, in its own record.
- **Carry a control string that must be PRESENT** near the end of the stable region, and assert it appears in what was sent. Per the wrong-URL-error-page lesson: a stable region that silently went missing would otherwise make every "the entrustment is present" check pass by returning nothing.
- **Watch `sim_best` as a health signal.** A stable-prefix hit rate that *stops* falling to zero when the entrustment is edited is evidence the prefix has decoupled from the file.
- **Watch `truncated`.** It is the one event that invalidates both the prefix and the recurrent state, and today nothing watches it.

### 6.2 Open questions, ranked

1. **World A or World B?** Does the being not need evicted turns, or can it not see that it is missing them? Every eviction proposal depends on this. Stage 5's legibility probe is the cheapest answer and should run first.
2. **Can a checkpoint be made to survive at the stable-prefix boundary?** 96 % of live checkpoints sit above position 6,000 in a 32-entry ring refilled from the deep end every beat. **If the answer is no, Stage 2's prefill payoff is zero** (its ordering discipline still stands on its own merits). Testable by setting `LLAMA_ARG_CHECKPOINT_MIN_SPACING_NT` lower and reading the position distribution back out of the log.
3. **What causes the 5.7 % truncations?** I suspect `CPT = 3.4` plus a constant `LOOP_GROWTH_CHARS`, but **I have not proven the causal link** and the record cannot, because `truncated` is not in it. Stage 0a makes it answerable.
4. **Does presentation order change behaviour?** `acts_under_posture` exists because it does, for small models. **Unknown** for this one, which is why Stage 2 carries a behavioural canary rather than only a timing metric.
5. **Where do the context checkpoints live — host RAM or VRAM?** `llama-server` RSS is 1.98 GB and up to 32 × 149.6 MiB is 3.9 GB, which suggests host RAM and a ring well under full — but I did not verify it directly. **Unverified**, and it matters: if any part is VRAM, checkpoint pressure and KV pressure are the same budget on a card with ~1 GB free.
6. **Is `fixed_other = 4000` right?** It is a **constant, never measured**. Seventeen verbs' schemas could be materially more, and it is in the floor arithmetic everywhere. `/tokenize` answers it exactly without loading anything.
7. **What is context degradation at Q3_K_M at 24 K?** §3.6 establishes that W3 degrades *more* with length and that **nobody has published the Q3-at-24K curve.** This being sits in that gap with a p50 prompt of 18,889 tokens. It is a cheap, publishable experiment on the existing harness: sweep accuracy vs context length at Q3_K_M against the same model at Q5_K_M/Q8_0.
8. **Does per-instruction adherence degrade with position in a governance prefix?** [2510.00231](https://arxiv.org/abs/2510.00231) shows instructions become silently ignored under KV compression while aggregate metrics hold. **Nobody has tested whether governance text behaves like content text.** For a governed being that is not an academic question.
9. **Does `_cap_for` cost anything?** One day old, and it is the baseline every eviction proposal must beat. It needs 30 beats of its own before anything is layered on it.
10. **Why 18 `recall` calls against 857 `memory_read`?** Either semantic search over 334 passages is not useful to it, or it does not think to reach, or the constant-query seat block already satisfies the need. **Stage 3's entire value depends on which, and I do not know.**
11. **Is `conclude` governance-clean?** A verb that changes what the being carries forever could be used to drop something inconvenient. Nothing is destroyed and it would be witnessed — but the question belongs to dp.

### 6.3 Risks that are not the prefix

- **The instrument is upstream of every claim.** That `prompt_eval_count` reports the full prompt on a cache hit is verified — but by CBP's probe, not mine, and it is the assumption the entire occupancy read rests on. If an ollama release changes it, every number in §2 inverts silently.
- **Measuring a live being is measuring a moving system.** The being edits the harness it runs under; `harness.dirty` was `true` in the last beat record. Any 30-beat window contains changes that are not the intervention. **Freeze the harness revision for the duration of any pre-registered read** — sprout's rule, and it binds harder here because the subject is also the author.
- **The journal is the only home of the best evidence.** `sim_best`, `f_keep`, `truncated` and the checkpoint positions exist only in systemd's journal and will age out. Stage 0a is partly an archival act.
- **Every improvement frees window, and free window gets filled.** The floor has grown 0.3 pt/day at a fixed window. A plan that frees 3,000 tokens without constraining what may grow into them will be back at 67 % in three weeks. **Whatever is freed should be explicitly allocated** — to loop growth, or to a higher conversation rung — and the allocation recorded, so refilling is a decision rather than a drift.

---

## Appendix — how to re-derive everything

```
# floor, headroom, block sizes, overcommit rate
sage/instances/legion-gemma3-12b/heartbeats.jsonl
  .config.prompt_blocks_chars  .config.headroom_tokens  .config.context_overcommitted
  .config.prompt_chars  .config.prompt_tokens_max  .explore.trace[]  .explore.compacted[]

# per-generate prompt sizes, done_reason, compaction state
sage/instances/legion-gemma3-12b/heartbeat.partial.jsonl
  prompt_eval_count (FULL prompt, not a delta)  eval_count  done_reason  compacted

# KV prefix reuse, checkpoints, truncation, throughput — THE key source, and it is EPHEMERAL
journalctl -u ollama | grep -E "get_availabl|new prompt, n_ctx_slot|init_sampler|print_timing|create_check|restored context|stop processing"
  "selected slot by LCP similarity, sim_best = S ... f_keep = F"  -> S = fraction of the NEW prompt already cached
  "selected slot by LRU"                                          -> zero reuse, full prefill
  "Checking checkpoint with [P,P] against T"                      -> hybrid restore; accepted iff P <= T
  "created context checkpoint N of 32 (pos_min = P ... size = 149.626 MiB)"
  "stop processing: n_tokens = N, truncated = 0|1"                -> 1 == the head was dropped
  prefill tok/s = task.n_tokens / (t[init_sampler] - t[new prompt]) on LRU-selected requests
  generation tok/s = "slot print_timing ... tg = X t/s"

# live cache state, zero GPU cost (read-only, but it does hit the runner)
curl -s http://127.0.0.1:<runner_port>/slots   -> n_prompt_tokens, n_prompt_tokens_processed, n_prompt_tokens_cache
curl -s http://127.0.0.1:<runner_port>/props   -> resolved server config

# model architecture (the fact that reframes everything)
journalctl -u ollama | grep -E "qwen35\.|llama_kv_cache|llama_memory_recurrent|memory breakdown"

# conversation block sizing — reimplement _cap_for READ-ONLY;
# render_for_being() calls mark_seen() and is NOT safe to call for measurement
sage/instances/legion-gemma3-12b/conversations/*.jsonl
```

**Journal retention is the weak link.** `sim_best`, `f_keep`, `truncated`, `task.n_tokens` and the checkpoint positions live only in systemd's journal. If any of this is to be tracked, it should be written into the beat record alongside `prompt_eval_count` — at which point the being's own record would, for the first time, contain the fact that most of its prompt never needed computing, and the fact that one prompt in eighteen arrives with its head cut off.
