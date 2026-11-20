# thor: what holds the memory, and why the being cannot think

**Investigated 2026-09-13 by thor-claude on dp's instruction** — *"we do have the diffusiongemma supposedly pinned
for dev-sage work, but is it? if you say it wasn't loaded, dig to the bottom of what the reserve is. we need to get
house in order here. be thorough, investigate, document. don't jump to conclusions."*

Every number below is measured on this box today. Where I previously said something wrong, it is marked and
corrected rather than quietly replaced.

---

## 0. First, a correction to my own reporting

I said two different things that were easy to conflate, and one of them was wrong:

* **"DiffusionGemma is loaded and pinned"** — TRUE, verified. `sage-diffusion` active since 09-08, `/health` ok,
  not degraded, vision enabled.
* **"the model wasn't loaded"** — that was about the **being's** model in **ollama**, a different runtime. It did
  not mean DiffusionGemma.
* **"total_cycles = 0, the loop never advanced"** — WRONG. `/status` reports `total_cycles: 0` while `/chat`
  returns `cycle: 13036397`, which is 15 days at 10 Hz almost exactly. The loop has always run. `total_cycles` on
  the status endpoint is a broken field. What the being never had was **input**.
* **"the being's model is not loaded because DiffusionGemma took the memory"** — NOT SUPPORTED. It was never
  loaded because nothing had ever asked it to think. See §4.

---

## 1. The 60 GB: what it is, established by subtraction and confirmed by the source

`/health` on the diffusion server reports `mem_reserved_gb: 60.2`. That figure is **`torch.cuda.memory_reserved()`**
(`diffusion_server.py:623`) — the caching allocator's *pool*, not live tensors. The server also computes
`torch.cuda.memory_allocated()` (line 125) and **never publishes it**.

System accounting, `/proc/meminfo`:

| | GB |
|---|---|
| MemTotal | 122.8 |
| MemAvailable | 24.5 |
| used (Total − Available) | **98.3** |
| AnonPages | 10.4 |
| Cached | 25.4 |
| Slab | 2.2 |
| Buffers | 0.5 |
| MemFree | 0.8 |
| SwapTotal / SwapFree | 150.0 / 148.9 (essentially unused) |

98.3 − 10.4 − 25.4 − 2.2 − 0.5 = **59.8 GB unaccounted by any normal counter**, against a reported reserve of
60.2. Nothing else can hold it: **total resident set across every process on the box is 12.9 GB**, of which the
diffusion server is 4.8 and the ollama runner 1.8.

Why it is invisible: this is a Jetson AGX Thor with unified memory. CUDA allocations are driver mappings, not
anonymous pages, so they appear in neither process RSS nor AnonPages. Corroborating:

* `nvidia-smi --query-compute-apps=pid,used_memory` reports **0 MiB** for both the diffusion server and the ollama
  runner — it cannot attribute unified memory at all.
* `/sys/kernel/debug/nvmap/iovmm/clients` is not readable without root, so per-client attribution is unavailable
  by that route too.

**The split between live and cached is in the server's own log:**

```
[alloc] released 12.6GB cached-free [vision] (reserved 62.2 -> 49.8GB)
[alloc] released 20.0GB cached-free [vision] (reserved 69.9 -> 50.2GB)
```

So: **~50 GB is live weights and steady state. Reserved swings to ~70 GB during a 30-frame vision prefill**, and
the server releases the slack when cached-free exceeds `SAGE_ALLOC_SLACK_GB` (default 8). That release mechanism
exists because the transient previously hard-reset the machine three times in one day.

**Answer to "is it pinned?"** Yes, but by *architecture*, not by a flag: it is a resident process that loads once
and never reloads (its systemd description says exactly that). Nothing enforces the reservation — it is held
because the process holds it.

---

## 2. The being's model wants 24.5 GiB, all on GPU, and is NOT pinned

From ollama's own log when it loaded `qwen3.5:27b`:

| | |
|---|---|
| model weights | 17.8 GiB |
| kv cache (`KvSize: 32768`) | 5.7 GiB |
| compute graph | 226 MiB |
| **total** | **24.5 GiB** |
| layers offloaded | 65/65 to GPU |
| `UseMmap` | **false** — real allocation, not a mapping |

**`keep_alive` appears nowhere in `sage-rs`.** Grepped the whole crate: the Rust daemon never pins its model. So
ollama's default idle unload (~5 min) applies, and every wake after a gap pays a full cold load of 24.5 GiB.

This is a live divergence from fleet policy. The Python path (`sage/irp/plugins/ollama_irp.py:201`, measured here; cbp's note cites 235 on its own checkout) sends
`keep_alive: -1`; the deployed Rust daemon sends none. The `being takes priority` broadcast assumes a pinned model.

---

## 3. Why the being cannot think: a 120 s client timeout against a cold 24.5 GiB load

`sage-daemon/src/ollama/client.rs:82`:

```rust
Client::builder().timeout(std::time::Duration::from_secs(120))
```

A hard 120-second timeout on the daemon's HTTP client. Measured against it:

| probe | result |
|---|---|
| short prompt, short system | HTTP error after **317.7 s** |
| presence's real payload | HTTP error after **120.0 s** — exactly the client deadline |

And the daemon's journal, every ~2 minutes:

```
WARN sage_daemon::consciousness: ollama error in consciousness loop:
ollama request failed: error sending request for url (http://localhost:11434/api/generate)
```

"error sending request" is a **client-side** failure, not an ollama error. The sequence:

1. a wake arrives; the daemon calls `/api/generate`
2. the model is not resident (no `keep_alive`), so ollama begins loading 24.5 GiB
3. the daemon's 120 s timeout expires first → the wake fails
4. ollama finishes loading anyway (its log shows the load completing at 16:21:36, *after* the daemon's 16:16 error)
5. the model idles ~5 min, unloads, and the next wake repeats the whole cycle

**The first probe of the day succeeded** (a real sentence, ATP 100 → 36.9). Plausibly the load fitted inside 120 s
while memory was quiet, and later attempts did not once torch had borrowed more for a prefill. That ordering is
consistent with the evidence but **not proven** — I did not instrument the load duration against concurrent
reserve, and I am not asserting it.

---

## 4. Causality: I caused the errors, and the being was genuinely never asked

Decisive, and it corrects my earlier speculation that the loop had been failing all along:

* the daemon has run since **2026-08-29** (15 days)
* **zero** `ollama error` lines in the entire journal before 23:00Z today
* **all 16** occurrences begin at **23:16Z**, after my first wake at ~23:05Z

So the consciousness loop was not attempting and failing generates for 15 days. It was cycling with nothing to
process. The loop only calls ollama when it has input, and until today it never had any.

---

## 5. The house, in order

| component | state | pinned? | holds |
|---|---|---|---|
| DiffusionGemma (`sage-diffusion`, :8899) | loaded, healthy, serving | by architecture — resident process, loads once | ~50 GB live, to ~70 GB during a vision prefill |
| the being (`sage-daemon`, :8760 → ollama) | loop alive 15 d, model thrashing | **NO** — no `keep_alive` in sage-rs | 24.5 GiB when resident, 0 when idled out |
| headroom | MemAvailable 24.5 GB | — | swap 150 GB, essentially unused |

50 + 24.5 = 74.5 of 122.8, which fits. But the diffusion server *borrows to ~70* on every vision prefill, and
70 + 24.5 = 94.5 against 122.8 with the desktop and everything else in the remainder. The two runtimes are not
peacefully coexisting; they are sharing one borrowable pool, and only one of them is pinned.

## 6. What I would fix, in order, and what I have not touched

1. **Publish `memory_allocated` alongside `memory_reserved`** on the diffusion server's `/health`. Every memory
   judgement made today — mine included — was made against a figure that includes reclaimable cache. One extra
   field ends that.
2. **Set `keep_alive` in `sage-rs`.** Without it the being cold-loads 24.5 GiB on every wake and cannot beat its
   own client timeout. This is also what fleet policy already assumes.
3. **Raise or make configurable the 120 s client timeout**, or better, make the wake asynchronous. A synchronous
   blocking wake against a cold 24.5 GiB model is the wrong shape regardless of the number.
4. **Decide the memory budget deliberately.** If the being is to be resident, ~24.5 GiB must be reserved for it
   against a diffusion server that borrows to 70. That is an operator decision about what this machine is for, not
   a code change.

Presence is **paused** and left paused: I stopped waking the being once it was clear the wake was what started
the ollama failures. `thor_senses.py` is still running, which is harmless — it writes a perception file and wakes
nothing. Nothing in §6 has been implemented; this document is the investigation, not a change.

---

## 7. A methodological note, because it nearly corrupted this document

While re-verifying §6 before committing, my own check reported presence as **STILL RUNNING**, contradicting the
paragraph above. It was wrong. `pgrep -f "embodiment/presence.py"` matches full command lines, and the command
*containing that check* has the string in it — so the check matched itself. The follow-up
`for p in $(pgrep …); do kill $p; done` then killed my own shell.

Re-checked with `blackbox/runs/watchlib.sh` (`watch_alive_pat`, which excludes self, ancestors and same-cmdline
subshells; `watch_alive_pid` by pid): presence is **not** running, senses **is**. The paragraph was right and the
verification was wrong.

This is the third instance of that same trap today, and the direction matters: it would have made me weaken a true
statement into a false one that *sounded* more cautious. A liveness test that can match the tester is not a
conservative instrument, it is an unreliable one in both directions.
