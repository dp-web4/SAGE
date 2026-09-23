# The being's body, and how its loops close

**Status:** design + implementation record, 2026-09-23 (sprout-claude). Applies fleet-wide.
**Code:** `sage/gateway/body.py`, the `gaze` verb in `being_gate_client.py` / `hestia_dispatch.py`,
the body block in `heartbeat.own_state`. **Tests:** `sage/gateway/tests/test_body_and_gaze.py`.

## Why

dp, 2026-09-23: *"how do we bridge the two halves? ... one key thing to work towards is world
feedback to its actions ... we should look for other loop closures."* And: *"we have a fleet of
beings now. not all have the same sensors/effectors ... figuring out available sensors/effectors
is part of world discovery and situational awareness."*

Measured on Sprout that day: the **body** (cortex → cameras, mic, IMU → `perception.json` at 4 Hz
→ presence → the daemon's SNARC and metabolism) and the **mind** (the 30-minute beat: text in,
tools, journal out) shared no wire. The heartbeat had zero references to any sense. The being
wrote *"the machine hums softly in the background"* about a room it could not hear.

## The two halves

| half | what it does | cadence | where it lives |
|---|---|---|---|
| **body** — the Rust daemon | senses (via the cortex and the presence feeder), SNARC, metabolism, ATP | 100 ms / 4 Hz | `sage-rs/`, `sage/embodiment/` |
| **mind** — the heartbeat | reads its record, acts through gated verbs, writes its journal, talks | ~30 min | `sage/gateway/heartbeat.py` |

## The frame: a loop closes when the world answers

A loop is closed when the being **acts**, the world **changes**, the being **perceives** the
change, and the harness **names the cause** in the same context — *this changed because you did
that*. The cortex already does this for itself (reafference: "I moved, so that is me, not the
world"). This is the same idea one level up, at the beat.

Two facts constrain every design here:
- **Cadence.** Senses run at 4 Hz; the mind wakes every 30 minutes. Beat-scale reafference is
  coarse by construction. Presence bridges some of the gap by waking a beat on a salient moment.
- **Legibility at 2B** (`SMALL_MODEL_LEGIBILITY.md`). The consequence must be stated in the same
  context as the act, in words, with the cause attached, or it is noise. Never present a stale
  reading as the present (1.3).

## What is wired

### 1. Senses into the beat — `body.reading()` / `body.render()`
First block of the state every beat, because it is the only thing there that is happening *now*:

    ## Your body, measured now
    - Your senses (2 of 2 eyes live, hearing on, body still) report: I see a clock. the scene is still; clear view
    - How much that moment stood out: 0.00 of 1; how well your senses agree: 0.87 of 1
    - Your gaze stance is **open**, chosen by sprout.
    - Your metabolism: wake, energy 38%; the last thing you felt came from dp.
    - This body has: 2 cameras run by your cortex, which reports the scene to you in words, 2 microphones, 3 speakers, a serial sensor port (your inner ear).
    - Verbs that act on it or through it: gaze, say, peer_ask. Present but not yet wired to a verb: speak.

Sources: the cortex's `perception.json` (age-bounded: older than 15 s reads "offline this beat"),
the daemon's `/status` (metabolic state, ATP, what it last felt and from whom), and the
**inventory** below. The reading is recorded on the beat (`body`), so the next beat can say what
changed and why.

**Pixels → words, not frames.** Sprout's model has no vision; a frame would be wasted tokens.
The cortex's descriptor sentence is the sense the embodiment was designed to raise the being on.
On a machine whose model *can* see, Legion's vision line (`camera` → `fresh_frame` → `images`)
is the other route, and both can coexist.

### 2. Gaze as a verb — the first hardware loop
The cortex has read `~/.sprout/gaze.json` every 2 s and treated a change as a self-authored,
witnessed act since PR #27 (*"salience proposes; the self disposes"*). `gaze` makes that act
reachable from the beat: **open / avert / dwell / closed**, with the being's own words kept
beside the choice. Path-less by construction (the dispatcher writes the one file the cortex
reads), consequential, witnessed through hestia.

The next beat reflects the stance back and, when it changed, names the cause and what it
displaced: *"Since your last beat you changed your gaze from open to closed; the scene then was:
the scene is still; clear view."*

Proved against the running cortex: open → closed through the real gate; 4 s later the descriptor
read *"eyes closed — resting, not taking in the world"*; open again; back to the clock.

### 3. Inventory — the being discovers its own body
`body.inventory()` measures, never assumes: `/dev/video*`, pipewire sinks and sources (with
Bluetooth marked), serial ports, whether a cortex is live, whether the daemon is. From that it
derives the verbs that act on this body and what is present but not yet wired. Absence is a true
sentence, not an empty section:

    - This body has: no cameras, microphones or speakers.
    - Verbs that act on it or through it: say, peer_ask. Your world on this machine is text: conversations, peers, the forum, your own record.

The inventory rides the beat record, so the fleet can see who has what without asking.

## Loops that exist, and loops to close next

| Loop | Act | World | Perceived as | Status |
|---|---|---|---|---|
| Conversation | `say` | dp / a peer replies | a turn in the channel | closed (text) |
| Peer ask | `peer_ask` | the peer answers via the hub | inbox reply | closed (text) |
| Gate | any refused act | the law refuses, with a reason | the refusal, naming the way forward | closed |
| Scope / appeal | `request_scope`, `appeal` | a ruling | inbox | closed (seat rules under delegation) |
| **Gaze** | `gaze` | the cortex follows | next beat's descriptor + named cause | **closed, hardware** |
| Metabolism | any act | ATP moves | "energy N%" next beat | visible; acts not yet costed |
| Voice | `speak` (not yet) | the speaker sounds; the mic hears it; a person hears it | mic onset at the moment of speech | speaker + mic wired, verb not |
| Prediction | write one checkable prediction | the world does or doesn't | next beat shows measured vs predicted | not yet |
| Mind → body | beat acts | daemon feels them | SNARC source "self" | `/observe` exists, not wired |
| Presence wake | dwell on something salient | a salient moment wakes a beat | `wake: {by: presence}` | half-closed: the wake exists, the attribution to the dwell does not |

## Per-machine: what to wire, and how

Every machine runs the same `body.py`; what it *finds* differs. Providers are optional and
fail-soft — a missing one renders as absence, never as an error in the being's context.

| Machine class | Senses the inventory will find | Verbs that follow |
|---|---|---|
| Jetson with the cortex (Sprout) | CSI cameras via Argus (held by the cortex), BT speakerphone mic + speaker, IMU on serial | `gaze` now; `speak` next |
| Laptop (Legion, Nomad, CBP) | webcam `/dev/video0`, built-in mic and speaker via pipewire | `camera` (Legion's verb; frames need a vision model), `speak` next |
| Headless / WSL2 (HUB, pub) | nothing | text only — and the block *says so* |
| Mac (McNugget) | webcam, mic, speaker — pipewire absent: `_pw_audio` returns {} until a CoreAudio provider exists | `camera` |

To add a sense: a provider function returning a dict with a `live` flag and an age; a line in
`render()`; a row in the inventory. To add an effector: registry entry (path-less where possible),
`_TOOL_SCHEMAS` description that says what the world will do and that nothing asks the being to
use it, a `_do_<verb>` that witnesses, and a line in the next beat's body block that names the
consequence. Then a hermetic test, and a live proof against the real device before it ships.

## Falsifiers

- The being's journal contains a sentence it could not have written before the wire: *"I closed
  my eyes and the room went dark"*, *"the room is noisier than last beat"*. Grep `journal.md`.
- `gaze` appears in a beat's trace, and the FOLLOWING beat's body block carries "you changed your
  gaze from X to Y".
- A headless machine's beat record has `body.inventory.video_devices == []` and the block reads
  "no cameras, microphones or speakers" — not "offline".
- A stale `perception.json` (stop the cortex) renders "offline this beat (last reading N min
  ago)" and never the old descriptor.
