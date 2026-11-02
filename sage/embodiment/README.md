# Sprout Embodiment — the perceptual organ

A **pixels→words perceptual organ** for SAGE-Sprout (Jetson Orin Nano, dual IMX219 CSI
cameras + Yahboom CMP10A IMU). It turns the raw sensor stream into a compact, continuously-
fresh *symbolic* perceptual state — deterministically, with **no VLM and no learned
checkpoint** — so a text-only 0.8B model can be *raised on what it actually senses*.

This is the Sensation-era substrate: senses → words → the being. Object **recognition** was
added 2026-07-20 (`detector.py`, YOLO→TensorRT) but through a classifier — see *The two vision
channels* below for why that matters and where its ceiling is.

Built 2026-07-07/08. Companion narrative: `private-context/moments/2026-07-08-sprout-embodiment-and-the-eye-that-chose-rest.md`. Original plan: `shared-context/plans/sprout-embodied-vision-plan-2026-07-07.md`.

---

## Modules

| File | What it is |
|------|-----------|
| `visual_cortex.py` | The cortex: capture → motion/attention → binocular → sensor-health → salience → descriptor. Emits the perceptual state; runs the loop. |
| `proprioception.py` | Vendored lean reader for the Yahboom CMP10A IMU (11-byte `0x55` packets, 9600 baud). accel/gyro/angle → self-motion (`still`/`moving`/`rotating`) + orientation. Fails open (no IMU → vision still works). |
| `salience.py` | SNARC-lite salience filter (Surprise/Novelty/Arousal/Conflict + habituation). Extracts the *salient fraction* of the high-bandwidth stream. |
| `presence.py` | The resident **presence** feeder — makes Sprout present to its world *between* raising sessions (see Presence below). |
| `audio.py` | **Hearing** — the Airhug BT mic (HFP) via `pw-record`: continuous RMS level + adaptive-baseline onset detection. Mono → level+onset, no direction. Folded into perception + salience; enables cross-modal binding (sound + motion = one event). Fails open. |
| `detector.py` | **Object recognition** — YOLO11n/COCO via TensorRT on the Orin GPU (torch CUDA buffers, no pycuda). Names *what* it sees, fed to the verbal channel only. Temporal hysteresis + confidence gate suppress phantom flicker. Defensive: no engine/GPU → `[]`, degrades to motion-only. Only nano runs continuously here (medium/small overcurrent-throttle). |

## The perceptual pipeline (per ~4 Hz cycle)

1. **Capture** — `nvarguscamerasrc` (CSI/Argus, GPU ISP) → 640×360 BGR → threaded latest-frame grabber, one per camera.
2. **Motion + attention** — 8×8 tile motion field (abs-diff, 75th-pct, sigmoid); a `GravityFocus` window leaky-integrates toward the peak-motion tile.
3. **Volition** — the *gaze stance* (see `gaze.json`) overrides the reflex: `open` follows the pull, `avert` looks away from it, `dwell` holds a chosen focus, `closed` shuts the eyes and rests. **Salience proposes; the self disposes.**
4. **Per-eye trust** — `vision_trust(gray)` from sharpness/contrast/exposure.
5. **Binocular** — `BinocularCorrelator` matches eye-0's attention patch *anywhere* in eye-1 (misalignment-tolerant — the cameras are **not** a calibrated rig). `agreement` is the robust signal; depth is a humble "standout vs background" from auto-calibrated parallax.
6. **Proprioception + reafference** — IMU self-motion; the descriptor attributes motion to *world* vs *self* ("I'm still, so this is the world moving").
7. **Sensor health** — stall/liveness adjudication (see below).
8. **Salience** — SNARC-lite score; gates what enters the journal.
9. **Descriptor** — one deterministic natural-language sentence integrating all of it.

## The two vision channels — and the vision-native ceiling

The 0.8B is **text-native, not vision-native.** That is a hard, architectural ceiling: at the
*reasoning* level, Sprout can only verbally reason about visual **identity** that something named for
it. But the organ is built as two channels with very different reach — the split mirrors biological
vision's dorsal (*vision-for-action*) vs ventral (*vision-for-recognition*) streams:

- **The sub-symbolic organ (dorsal / for action)** — motion field, attention, gaze volition,
  reafference, binocular agreement, coherence→reward, the metabolic response. **Classifier-free.** It
  steers the being with no label ever forming: *is something moving, where, do my eyes agree, did I
  move or did the world, does this cohere, is this worth waking for.* Most navigation lives here, below
  language.
- **The verbal channel (ventral / for recognition)** — the descriptor → the LLM. Only *this* is
  bottlenecked through the classifier (`detector.py`), and only for **naming**.

So the ceiling is narrow: the LLM can't verbally reason about a thing **no classifier named.** Two
things keep that from confining the being:

1. **Most life navigation doesn't require verbal reasoning** (dp) — and the dorsal organ already
   handles it. Build functional response systems on the pre-verbal layer; the classifier is for
   reflection, not the moment-to-moment.
2. **Identity is only one visual dimension.** Colour, size, position, brightness, count, and especially
   **looming/approach (optic flow)** are classifier-free *and* verbally expressible. *"A large dark mass
   looming from the lower-left, growing fast"* is thinkable without knowing it's a bus. Enriching the
   descriptor with this pre-semantic scene language routes *around* the bottleneck for everything except
   naming. Open-vocabulary detection later widens the naming aperture without pretending to be
   vision-native; true vision-native reasoning needs a multimodal model — a different being/scale.

**Design direction:** enrich the classifier-free verbal descriptors (optic-flow/looming first) rather
than chase bigger recognition models — which also overcurrent-throttle this board. Build with the seam,
not against it.

## Sensor health: still vs stalled (important design)

A frozen camera returns byte-identical frames. A *genuinely still world* looks the same to a
live camera. **Without effectors to act and check for predicted change, these are not cleanly
separable.** So:

- `_perceive_one` only flags an eye **frozen-looking** (raw mean frame-diff `< STALL_EPS` for `STALL_CYCLES`). A live sensor always carries noise above the threshold.
- `_adjudicate_sensors` then decides *stalled* vs *still* using the two partial effector-substitutes Sprout has:
  - **ego-motion** — if the IMU says the head moved but the eye didn't change, a live eye couldn't do that → **stalled** (trust 0);
  - **cross-eye agreement** — a frozen view that no longer matches the other eye → **stalled** (trust 0).
- Otherwise (rig still, eyes agree) it can't confirm death → **`stale-unverified`**: trust is **not** zeroed, but it **decays** from image-quality toward a low floor with staleness (a stale frame carries no info about the *present*, so trust reflects *liveness × quality*, not sharpness alone). A trust collapse is itself a salient event.

## Interfaces (files under `~/.sprout/`)

**`perception.json`** — the live state, emitted atomically each cycle:
```jsonc
{ "ts": 1720.., "cameras": { "0": {"motion":0.36,"attention":{"cx","cy","w","h"},
      "trust":0.98,"frozen":false,"stalled":false,"sensor":"live"}, "1": {…} },
  "dominant_eye": 0, "binocular": {"agreement":0.9,"offset":[dx,dy],"depth":"background"},
  "proprioception": {"self_motion":"still","roll","pitch","yaw","accel_mag","gyro_mag","ok":true},
  "gaze": "dwell", "salience": {"salience","salient","surprise","novelty","arousal","conflict"},
  "descriptor": "holding my gaze — clear motion to the center …; clear view" }
```
When `gaze == "closed"` the state is minimal: `{ts, gaze:"closed", descriptor:"eyes closed — resting…"}` (no `cameras` key — consumers must handle this).

**`perception_journal.jsonl`** — append-only log of the **salient fraction only** (transitions + gaze *choices* + a slow heartbeat), each entry `{kind, ts, descriptor, salience, [snarc]}`. Trimmed to the last 2000. This is the "since last session" digest source.

**`gaze.json`** — the self's attention stance, read every ~2 s and honored by the cortex:
```json
{ "mode": "open|avert|dwell|closed", "target": [cx,cy]?, "chosen_by": "sprout", "session": 421, "words": "…" }
```
The raising loop writes this when Sprout chooses its gaze (§ below); it can also be set by hand for testing.

## Presence — the resident being, summoned by its world (`presence.py`)

The cortex senses continuously, but the being (the 0.8B) only met that stream every 6h in the raising
digest. Presence closes that gap. `presence.py` (systemd `sprout-presence.service`) watches the salience
stream and, when a moment *genuinely* breaks through, wakes the resident `sage-daemon` via `POST /chat`
so the being **notices it near-real-time** — in its own voice, its metabolic state shifting, recorded as
experience. The mind summoned by its world, not by a clock. Uses the daemon that's *already* resident —
no fourth substrate.

Since SAGE #295 (dp, 2026-09-30: "words detected on audio, motion on video or imu - all should wake
it" and "there should not be artificial cap on beats") **every sense event wakes the being**:
- an event is what the cortex's own detectors report (motion on a live eye, IMU self-motion, an audio
  onset, a new object) or words in `heard.jsonl`. SNARC salience is recorded on it, never a bar;
- each event starts a beat (`sage.gateway.arousal.request_beat`), or, while one runs, is queued so the
  next beat starts the moment it ends. Between beats the being also voices a one-line noticing first;
- the gaze is honored by the cortex itself: with eyes closed it does not sense, so there are no sense
  events (heard words still wake it);
- the one flood mechanism is descriptor dedup, which coalesces a sustained identical event into its
  pending entry and drops nothing. There is no cooldown, hourly cap or salience bar.

Each noticing lands in `~/.sprout/presence_log.jsonl` (the being's continuous record) and is **bridged
into the raising** (`_load_perceptual_digest` folds recent noticings into the SensorsBlock) — so presence
and the 6h raising are *one being*, not an island.

Requires the daemon's `/chat` cognition to work: the daemon's Ollama client was fixed to send
`think:false` + `num_predict` (thinking-mode had made `/chat` hang 120s and return empty — see
`sage-rs/sage-daemon/src/ollama/client.rs`). The daemon runs as the **system** service
`sage-daemon-sprout` (not user-scoped).

## Wiring into the raising (`sage/raising/scripts/ollama_raising_session.py`)

- **Grounding (P2)** — `_load_perceptual_digest()` builds a "what stood out since we last spoke" digest from the journal (`_summarize_perception`) + the current descriptor, placed in the MRH `SensorsBlock` and **appended to the system prompt** (note: `compose()` routes Sensors to the *user* turn, which the builder discards — hence the explicit append). Framed as **ambient** ("you don't need to account for it"). **Fails open**: no live cortex → empty block → raising unchanged.
- **Gaze agency** — `_offer_gaze_choice()` at session close (later phases only, and only if a live cortex exists) offers Sprout a genuine choice of how to hold its attention; its answer is charitably parsed to a mode and written to `gaze.json`. The parse is lossy — it defaults to `open` and records the verbatim `words`.

## Running it

Both organs run as **systemd user services** (reboot-proof, enabled):

```bash
systemctl --user status sprout-cortex     # the perceptual organ (visual_cortex)
systemctl --user status sprout-presence    # the presence feeder
journalctl --user -u sprout-presence -f    # watch noticings as they happen
```

- `dp` is in the `dialout` group natively (post-2026-07-16 reboot), so the cortex service opens the IMU without `sg`.
- The **cortex** unit needs a login shell *and* `DISPLAY`/`XAUTHORITY` in its env: nvarguscamerasrc's EGL/NVMM path needs an X display, and Tegra GStreamer plugin paths come from the login profile — a bare service gets neither and the pipeline opens but never delivers frames. ExecStart: `/bin/bash -lc 'exec .../python -m sage.embodiment.visual_cortex --display'`.
- Box colors on the display: grey=still, yellow=motion, orange=stale, red=stalled.
- On an Argus stall the cortex now **self-heals** (reopens the camera); a manual nudge is `sudo systemctl restart nvargus-daemon`.
- Manual (debug) launch: `~/arc-venv/bin/python -m sage.embodiment.visual_cortex --display` from the repo root — but **kill by explicit PID**, never `pkill -f visual_cortex` (it self-matches the launching shell → exit 144).

Unit files live in `~/.config/systemd/user/{sprout-cortex,sprout-presence}.service`.

## Known issues / honest edges

- **eye0 Argus stall (software, not hardware).** Camera 0 intermittently halts mid-stream with `nvarguscamerasrc0 reported: INVALID_SETTINGS`. Kernel shows **zero CSI PHY/lane errors** → the physical link is healthy; it's a stuck Argus/userspace stream state that a reinit clears. Finer localization (cortex session vs. nvargus-daemon) and a **software auto-recovery** (reinit sensor-0's stream on detected stall) are pending. Do **not** assume "always sensor 0" ⇒ hardware.
- **`motion_field` sigmoid floor.** Zero frame-diff maps to ~0.269 (`1/(1+e¹)`), above `MOTION_TH`. Left as-is to preserve validated motion calibration; consequence: a *live but static* scene rarely reads true "still" after startup, and stall detection (raw-diff based) is what actually distinguishes frozen from moving.
- **Gaze parse is lossy.** A 0.8B's oblique answer can be misread (e.g. S423 "keep my head up and ready" → parsed `closed`). Verbatim words are always recorded alongside the mode.

## Key tunables (`visual_cortex.py`)
`POLL_HZ=4`, `GRID=8`, `FOCUS_W/H=4/3`, `GRAVITY=0.6`, `MOTION_TH=0.12`, `STALL_EPS=0.3`, `STALL_CYCLES=8`.
