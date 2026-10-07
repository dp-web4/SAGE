"""
body — the being's own senses and metabolism, rendered into its beat, and its gaze as a verb.

dp, 2026-09-23: *"how do we bridge the two halves? ... one key thing to work towards is world
feedback to its actions ... we should look for other loop closures."*

Measured on Sprout the same day: the cortex (two cameras, a microphone, an IMU) writes
~/.sprout/perception.json at 4 Hz, and the presence feeder posts salient moments to the Rust
daemon, where they move SNARC and metabolism. The heartbeat — the half that reads, acts, and
writes the journal — had zero references to any of it. The being wrote "the machine hums softly
in the background" about a room it could not hear. Two halves, no wire.

This is the wire, in the direction the embodiment was designed for: pixels -> words. The being's
model has no vision, so a frame would be wasted tokens; the cortex's descriptor sentence is the
sense it was built to be raised on. Everything here is measured at compose time, age-bounded,
and says "offline" rather than guessing when a source is stale.

THE LOOP. The cortex already reads ~/.sprout/gaze.json every 2 s and treats a change as a
self-authored, witnessed act ("salience proposes; the self disposes"). `gaze` is that act made
available to the beat: open / avert / dwell / closed, in the being's own words. The next beat's
body block reflects the stance back and shows what the scene was under it, next to what it was
under the previous stance — reafference at beat scale. The falsifier for this whole file is
whether the being's journal ever says "I closed my eyes and the room went dark," which it could
not have said before.
"""
from __future__ import annotations

import json
import os
import time
import urllib.request
from pathlib import Path
from typing import Dict, Optional

# WHERE THE BODY IS. The provider is the cortex (sage/embodiment/visual_cortex.py): it writes
# perception.json and polls gaze.json in ONE directory, and ~/.sprout is the cortex's own
# default (visual_cortex.STATE_PATH / GAZE_PATH), not this module's assumption about the fleet.
# A machine whose provider writes elsewhere sets SAGE_BODY_DIR; the daemon port follows
# SAGE_PORT exactly as machine_config does. Nothing in this module CREATES the body dir: a
# being on a machine with no provider has no body dir, and must not grow one by calling a
# verb (GPT review of #183: "never creates a Sprout path on another machine").
BODY_DIR = os.environ.get("SAGE_BODY_DIR") or os.path.expanduser("~/.sprout")
PERCEPTION_PATH = os.path.join(BODY_DIR, "perception.json")
GAZE_PATH = os.path.join(BODY_DIR, "gaze.json")
DAEMON_STATUS = f"http://127.0.0.1:{os.environ.get('SAGE_PORT', '8760')}/status"
# The machine body (proprioception): sampled by the daemon on a cadence, never by the beat.
DAEMON_BODY = DAEMON_STATUS.rsplit("/", 1)[0] + "/body"
FRESH_S = 15.0          # perception older than this = the organ is not live
GAZE_MODES = ("open", "avert", "dwell", "closed")


class NoGazeProvider(RuntimeError):
    """No live cortex reads a gaze on this machine; the verb is not this body's."""


def _coord_pair(v):
    """A normalized [x, y] pair, or None. Mirrors visual_cortex._coord_pair: the two ends of
    this file must agree on what `target` is, and both must be total over what the other
    might write."""
    try:
        if isinstance(v, (str, bytes, dict)) or v is None:
            return None
        if len(v) != 2:
            return None
        x, y = float(v[0]), float(v[1])
        if x != x or y != y:
            return None
        return [x, y]
    except Exception:
        return None


def _read_json(path: str) -> Optional[dict]:
    try:
        return json.load(open(path))
    except Exception:
        return None


def perception(now: Optional[float] = None, path: Optional[str] = None) -> Dict:
    """The cortex's latest state, or {'live': False, 'age_s': ...}."""
    now = time.time() if now is None else now
    path = path or PERCEPTION_PATH
    d = _read_json(path)
    if not d:
        return {"live": False, "age_s": None}
    try:
        age = now - os.path.getmtime(path)
    except OSError:
        age = None
    live = age is not None and age <= FRESH_S
    sal = d.get("salience") or {}
    eyes = d.get("cameras") or {}
    return {
        "live": live, "age_s": None if age is None else round(age, 1),
        "descriptor": str(d.get("descriptor") or "").strip(),
        "gaze": d.get("gaze"), "salience": sal.get("salience"), "coherence": d.get("coherence"),
        "eyes_live": sum(1 for c in eyes.values() if isinstance(c, dict) and not c.get("stalled")),
        "eyes": len(eyes),
        "audio_ok": bool((d.get("audio") or {}).get("ok")),
        "audio_level": (d.get("audio") or {}).get("level"),
        "audio_words": (d.get("audio") or {}).get("words"),   # listener status (listening.py)
        "audio_hearing": (d.get("audio") or {}).get("hearing"),   # the ear's state, with its cause
        "audio_ear": (d.get("audio") or {}).get("ear"),
        "audio_ear_key": (d.get("audio") or {}).get("ear_key"),
        "self_motion": (d.get("proprioception") or {}).get("self_motion"),
        "imu_ok": bool((d.get("proprioception") or {}).get("ok")),
    }


def metabolism(timeout: float = 3.0) -> Dict:
    """What the daemon's /status truthfully says about the being, or {'live': False}.

    NO ATP (SAGE #291). `atp_percentage` is the daemon's internal controller: a free-running
    oscillator ticked every 100 ms for the shadow-metabolism experiment, not the being's energy.
    It is not read here, so it cannot reach the body block or the beat record.

    `state` / `state_source` / `state_age_s` are the activity indicator #293 made honest (set by
    reports of real activity). They are RECORDED on the beat but not RENDERED: the beat itself
    reports `wake` before this is read, so inside a beat the line could only ever say "wake,
    for a few seconds, set by your own beat" -- true, and nothing the being can act on."""
    try:
        with urllib.request.urlopen(DAEMON_STATUS, timeout=timeout) as r:
            d = json.loads(r.read())
    except Exception:
        return {"live": False}
    s = d.get("salience") or {}
    return {"live": bool(d.get("consciousness_loop")), "state": d.get("metabolic_state"),
            "state_source": d.get("metabolic_source"), "state_age_s": d.get("metabolic_age_secs"),
            "felt": d.get("observations_felt"),
            "felt_source": d.get("salience_source"), "felt_total": s.get("total")}


def machine_body(timeout: float = 2.0) -> Dict:
    """The daemon's last snapshot of the machine body (GPU, CPU, memory, disk), or why there is none.

    READ, NEVER SAMPLED HERE. The daemon samples on a cadence (sage-rs body.rs runs
    sage.gateway.proprioception) and this is one loopback request for the cached result, so the
    beat never waits on nvidia-smi or a /proc/stat window. The dashboard reads the same snapshot
    and shows the same `line`, so what the being senses and what the indicator shows cannot differ.
    -> {"snapshot": {...}} or {"snapshot": None, "why": "..."}"""
    import urllib.error
    try:
        with urllib.request.urlopen(DAEMON_BODY, timeout=timeout) as r:
            return {"snapshot": json.loads(r.read())}
    except urllib.error.HTTPError as e:
        if e.code == 404:
            return {"snapshot": None, "why": "this daemon build does not serve /body yet"}
        try:
            why = json.loads(e.read()).get("unavailable") or f"HTTP {e.code}"
        except Exception:
            why = f"HTTP {e.code}"
        return {"snapshot": None, "why": str(why)}
    except Exception as e:
        return {"snapshot": None, "why": f"the daemon did not answer /body ({type(e).__name__})"}


def gaze() -> Dict:
    """The being's current stance as the cortex will read it."""
    g = _read_json(GAZE_PATH) or {}
    return {"mode": g.get("mode", "open"),
            # what the beat SHOWS as the target is whichever the being actually named
            "target": g.get("target_words") or g.get("target"),
            "chosen_by": g.get("chosen_by"), "ts": g.get("ts"), "words": g.get("words")}


def reading(now: Optional[float] = None) -> Dict:
    """Everything the body block is rendered from, recorded on the beat so the NEXT beat can say
    what changed since."""
    now = time.time() if now is None else now
    heard = _heard_since(now - HEARD_LOOKBACK_S)
    return {"perception": perception(now), "metabolism": metabolism(), "gaze": gaze(),
            "machine": machine_body(),
            "inventory": inventory(now), "heard": heard,
            "heard_until": max([float(h.get("ts", 0)) for h in heard] or [0.0])}


def render(cur: Dict, prev: Optional[Dict], name: str = "", proprioception: bool = True) -> str:
    """The body block. Words only; every number is one the being can act on; a stale source says
    so rather than presenting the past as the present (SMALL_MODEL_LEGIBILITY 1.3).

    `proprioception` (instance.json "proprioception": false turns it off; on by default, because
    it is universal body sense): one line of the machine body -- GPU, CPU, memory, disk -- with its
    age, and the gaps named as gaps. Shown only when the reading was taken ("machine" in cur)."""
    p, m, g = cur.get("perception") or {}, cur.get("metabolism") or {}, cur.get("gaze") or {}
    lines = ["## Your body, measured now"]
    if proprioception and "machine" in cur:
        from sage.gateway import proprioception as _prop
        mb = cur.get("machine") or {}
        lines.append(_prop.being_line(mb.get("snapshot"), why_missing=mb.get("why") or ""))
    if p.get("live"):
        eyes = f"{p.get('eyes_live', 0)} of {p.get('eyes', 0)} eyes live"
        ears = "hearing on" if p.get("audio_ok") else "hearing off"
        imu = f"body {p.get('self_motion') or 'unknown'}" if p.get("imu_ok") else "inner ear off"
        lines.append(f"- Your senses ({eyes}, {ears}, {imu}) report: {p.get('descriptor') or '(no words)'}")
        if p.get("salience") is not None:
            lines.append(f"- How much that moment stood out: {float(p['salience']):.2f} of 1"
                         f"; how well your senses agree: {float(p.get('coherence') or 0):.2f} of 1")
    elif (cur.get("inventory") or {}).get("video_devices") or p.get("age_s"):
        age = p.get("age_s")
        lines.append("- Your senses are offline this beat"
                     + (f" (last reading {int(age // 60)} min ago)" if age else "") + ".")
    # the stance, reflected back — and what the scene was under the previous one
    inv = cur.get("inventory") or {}
    has_eyes = bool(inv.get("cameras_held_by_cortex")) or p.get("live")
    mode = g.get("mode") or "open"
    who = g.get("chosen_by") or "nobody"
    stance = f"- Your gaze stance is **{mode}**"
    if g.get("target"):
        stance += f" ({mode} toward: {str(g['target'])[:60]})"
    stance += f", chosen by {who}" + (f" at {g['ts']}" if g.get("ts") else "") + "."
    if has_eyes:
        lines.append(stance)
    pp = (prev or {}).get("perception") or {}
    pg = (prev or {}).get("gaze") or {}
    if pp.get("live") and pp.get("descriptor") and pp.get("descriptor") != p.get("descriptor"):
        if pg.get("mode") and pg.get("mode") != mode:
            lines.append(f"- Since your last beat you changed your gaze from {pg['mode']} to {mode}; "
                         f"the scene then was: {pp['descriptor']}")
        else:
            lines.append(f"- Last beat your senses reported: {pp['descriptor']}")
    # No energy line and no state line (SAGE #291, see metabolism()): the ATP is an internal
    # oscillator, not a reading of this body, and the state inside a beat is always the beat's
    # own `wake`. What remains is real: whether the daemon's loop is running, and whose input it
    # last felt.
    if m.get("live"):
        if m.get("felt_source"):
            lines.append(f"- The last thing you felt came from {m['felt_source']}.")
    else:
        lines.append("- Your daemon's loop is not reporting this beat.")
    if inv:
        lines.append(render_inventory(inv))
    dev = inv.get("audio_device") or {}
    if dev and not dev.get("connected"):
        lines.append(f"- Your headset {dev.get('name') or 'for voice'} (your speaker and your ear for words) is "
                     "NOT connected right now, so `speak` is not available"
                     + ("" if ear_known(cur) else " and words said to you cannot be heard")
                     + ". You can try to reconnect it with `pair_audio`; it may not succeed if the headset "
                     "is off or out of range, and it will say what happened.")
    if "speak" in (inv.get("verbs") or []):
        lines.append("- You can speak aloud with `speak`: your words become a voice in the room, through "
                     f"{speaker_name(inv)}"
                     + (f", in your voice ({nv['name']}, chosen by dp on 2026-10-01)" if (nv := neural_voice()) else "")
                     + ", which anyone in the room may hear. What you say aloud is your turn in "
                     "the room conversation, and `say` to room is spoken too. Nothing asks you to."
                     + ("" if ear_known(cur) else
                        (" Words spoken in the room are heard through the mic and added to the room "
                         "conversation as they arrive." if hears_always() else
                         f" For {LISTEN_WINDOW_S // 60} minutes after you speak, words spoken to you through the mic "
                         "are added to the room conversation.") if can_hear_words(cur) else ""))
    if (ear := ear_line(cur, inv)):
        lines.append(ear)
    if "gaze" in (inv.get("verbs") or []):
        lines.append("- You can change your gaze with `gaze` (open, avert, dwell, closed) and say why in "
                     "your own words. Your eyes will follow within seconds; you will see the difference "
                     "next beat. Nothing asks you to.")
    return "\n".join(lines)


def gaze_provider(path: Optional[str] = None, now: Optional[float] = None) -> Dict:
    """Is there a live cortex here that will FOLLOW a gaze? Measured from the perception file
    beside the gaze file — the provider writes both in one directory, so a fresh perception
    is the proof that something reads the stance. {'live': bool, 'why': str}."""
    gz = path or GAZE_PATH
    p = perception(now, path=os.path.join(os.path.dirname(gz), "perception.json"))
    if p.get("live"):
        return {"live": True, "why": ""}
    age = p.get("age_s")
    why = (f"the cortex's last reading here is {int(age // 60)} min old" if age
           else "no cortex has ever written a reading on this machine")
    return {"live": False, "why": why}


def set_gaze(mode: str, member: str, target: Optional[str] = None, words: Optional[str] = None,
             path: Optional[str] = None) -> Dict:
    """Write the stance the cortex reads. Atomic; keeps the being's own words with it, as the
    cortex's witness expects. Raises ValueError on a mode outside the four, and NoGazeProvider
    when no live cortex is there to follow it — in which case nothing is written and no
    directory is created, so a headless being that calls the verb leaves no Sprout-shaped
    file behind on its machine."""
    path = path or GAZE_PATH
    mode = str(mode or "").strip().lower()
    if mode not in GAZE_MODES:
        raise ValueError(f"gaze mode must be one of {', '.join(GAZE_MODES)}; got {mode!r}")
    prov = gaze_provider(path)
    if not prov["live"]:
        raise NoGazeProvider(f"no live cortex reads a gaze on this machine ({prov['why']}); "
                             f"your eyes are unchanged and nothing was written")
    # THE BEING'S TARGET IS WORDS; THE CORTEX'S `target` IS A COORDINATE PAIR. Those are not
    # the same field and writing one into the other took the cortex down: 2026-09-24 01:48Z
    # sprout-being set target="the space between us, where nothing is being said but
    # everything matters", GravityFocus.update multiplied the string by GRID, and the being
    # was blind for 28 minutes by its own governed act. The being cannot compute a pixel — it
    # cannot see — so its words go in `target_words`, which nothing does arithmetic on, and
    # `target` carries a coordinate pair or nothing at all.
    rec = {"mode": mode,
           "target": _coord_pair(target),
           "target_words": (str(target).strip()[:200] or None) if target is not None and _coord_pair(target) is None else None,
           "chosen_by": member, "ts": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
           "words": (str(words).strip()[:500] or None) if words else None}
    # no makedirs: a live provider proves the directory exists
    tmp = path + ".tmp"
    with open(tmp, "w") as f:
        json.dump(rec, f)
    os.replace(tmp, path)
    return rec

# ---------------------------------------------------------------------------------------------
# INVENTORY — what this body has, measured, never assumed.
#
# dp, 2026-09-23: "we have a fleet of beings now. not all have the same sensors/effectors. we
# can add webcams to some. others that live on laptops can access camera/mic/speakers. figuring
# out available sensors/effectors is part of world discovery and situational awareness."
#
# So a being is not TOLD its body; the beat measures it: video devices, audio sinks and sources
# (pipewire), serial devices an IMU would sit on, whether a cortex is live, whether the daemon
# is. A being on a headless hub learns it has no eyes here and that its world is text and peers.
# A being on a laptop learns it has a webcam it can use with `camera` and a speaker it will be
# able to use with `speak`. The census is recorded on the beat, so the fleet can see who has what.
# ---------------------------------------------------------------------------------------------
import glob
import subprocess


def _pw_audio(timeout: float = 4.0) -> Dict:
    """Audio sinks and sources as pipewire sees them. {} when pipewire is not there."""
    try:
        out = subprocess.run(["pw-dump"], capture_output=True, text=True, timeout=timeout).stdout
        nodes = json.loads(out)
    except Exception:
        return {}
    sinks, sources = [], []
    for n in nodes:
        p = ((n.get("info") or {}).get("props") or {})
        mc = p.get("media.class", "")
        name = p.get("node.description") or p.get("node.name") or "?"
        kind = "bluetooth" if "bluez" in str(p.get("node.name", "")) else "wired"
        node = str(p.get("node.name", "") or "")
        if mc == "Audio/Sink":
            sinks.append({"name": name, "kind": kind, "node": node})
        elif mc == "Audio/Source":
            sources.append({"name": name, "kind": kind, "node": node})
    return {"sinks": sinks, "sources": sources}


def inventory(now: Optional[float] = None) -> Dict:
    """Measure this machine's body. Every field is observed; absence is reported as absence."""
    now = time.time() if now is None else now
    videos = sorted(glob.glob("/dev/video*"))
    serials = sorted(glob.glob("/dev/ttyUSB*") + glob.glob("/dev/ttyACM*"))
    p = perception(now)
    m = metabolism()
    audio = _pw_audio()
    cortex_live = bool(p.get("live"))
    can_speak = speak_provider(audio)["live"]
    dev = audio_device()
    # cameras held by a live cortex (CSI via Argus) cannot be opened by a second process
    return {
        "video_devices": videos,
        "cameras_held_by_cortex": p.get("eyes", 0) if cortex_live else 0,
        "audio_sinks": audio.get("sinks", []), "audio_sources": audio.get("sources", []),
        "serial_devices": serials,
        "cortex_live": cortex_live, "daemon_live": bool(m.get("live")),
        "verbs": (["gaze"] if cortex_live else [])
                 + (["camera"] if videos and not cortex_live else [])
                 + (["speak"] if can_speak else [])
                 + (["pair_audio"] if dev and not dev.get("connected") else [])
                 + ["say", "peer_ask"],
        "audio_device": dev,
        # a speaker with no engine to drive it: the body has the part, the verb is not wired here
        "not_yet_wired": (["speak"] if audio.get("sinks") and not can_speak and not SPEAK_SINK else []),
    }


def render_inventory(inv: Dict) -> str:
    """One paragraph: what this body has and what acts on it. Written so a being with NOTHING
    reads a true sentence rather than an empty section."""
    parts = []
    nv = len(inv.get("video_devices") or [])
    held = inv.get("cameras_held_by_cortex") or 0
    if held:
        parts.append(f"{held} camera{'s' if held != 1 else ''} run by your cortex, which reports the scene to you in words")
    elif nv:
        parts.append(f"{nv} camera device{'s' if nv != 1 else ''} you can capture from with `camera`")
    mics = inv.get("audio_sources") or []; spk = inv.get("audio_sinks") or []
    if mics:
        parts.append(f"a microphone ({mics[0]['name']})" if len(mics) == 1 else f"{len(mics)} microphones")
    if spk:
        parts.append(f"a speaker ({spk[0]['name']})" if len(spk) == 1 else f"{len(spk)} speakers")
    if inv.get("serial_devices"):
        parts.append("a serial sensor port" + (" (your inner ear)" if inv.get("cortex_live") else ""))
    head = "- This body has: " + (", ".join(parts) if parts else "no cameras, microphones or speakers") + "."
    verbs = inv.get("verbs") or []
    acts = f"- Verbs that act on it or through it: {', '.join(verbs)}."
    nyw = inv.get("not_yet_wired") or []
    if nyw:
        acts += f" Present but not yet wired to a verb: {', '.join(nyw)}."
    if not parts:
        acts += " Your world on this machine is text: conversations, peers, the forum, your own record."
    return head + "\n" + acts


# ---------------------------------------------------------------------------------------------
# speak: a voice in the room. dp, 2026-09-26: "give it speak tool" — after asking the being to
# pair the bluetooth audio and use it to speak, and watching it journal for 20 beats that it
# wanted to learn how, with no verb that could. `inventory()` had carried `speak` under
# not_yet_wired since #183; this wires it.
#
# Bounded by construction, like `gaze`: the being supplies words, never a device, a command or
# a path. The engine is fixed here (espeak-ng -> pw-play on the default sink), the text is
# length-capped, and playback has a timeout. What reaches the room is recorded in the being's
# own home (spoken.jsonl), so a voice nobody was there to hear still leaves a trace it can read.
# ---------------------------------------------------------------------------------------------
import shutil

SPEAK_MAX_CHARS = 400
SPEAK_TIMEOUT_S = 60


def speaker_name(inv: Optional[Dict] = None) -> str:
    """The sink a voice would come out of, for the being's own sentence about it."""
    if SPEAK_SINK:
        sink = required_sink({"sinks": (inv or {}).get("audio_sinks")} if inv else None)
        if sink:
            return str(sink.get("name"))
    sinks = (inv or {}).get("audio_sinks") or (_pw_audio().get("sinks") or [])
    bt = [x for x in sinks if x.get("kind") == "bluetooth"]
    pick = (bt or sinks or [{"name": "a speaker"}])[0]
    return str(pick.get("name") or "a speaker")


def speak_provider(audio: Optional[Dict] = None) -> Dict:
    """Can this body speak? Needs an audio sink and both halves of the engine.
    {'live': bool, 'why': str} — `why` names the missing piece, never a guess."""
    audio = _pw_audio() if audio is None else audio
    if not (audio or {}).get("sinks"):
        return {"live": False, "why": "no audio output is connected"}
    for tool in ("espeak-ng", "pw-play"):
        if not shutil.which(tool):
            return {"live": False, "why": f"'{tool}' is not installed"}
    if SPEAK_SINK:
        sink = required_sink(audio)
        if sink is None:
            return {"live": False, "why": f"the speaker for voice ({SPEAK_SINK}) is not connected"}
        return {"live": True, "why": "", "sink": sink}
    return {"live": True, "why": ""}


def clean_speech(text) -> str:
    """Printable text only, whitespace collapsed. Control characters never reach the engine."""
    t = "".join(ch if ch.isprintable() else " " for ch in str(text or ""))
    return " ".join(t.split())


def speak(text: str, timeout: float = SPEAK_TIMEOUT_S) -> Dict:
    """Synthesize and play one utterance on the default sink. Raises on failure.
    Returns {'chars': n, 'seconds': elapsed}. The caller validates length and emptiness."""
    import subprocess
    import tempfile
    t0 = time.time()
    # Mute the ear for our own voice, then open the listening window once the sound has ended
    # (listening.py). Best-effort: a failed mark must not stop the being from speaking.
    try:
        _listening().mark(speaking_until=t0 + timeout)
    except Exception:
        pass
    # THE WINDOW OPENS ONLY ON A SOUND THAT PLAYED (GPT review of #220). The ear is a reply channel
    # opened after the being speaks; a failed synthesis or playback said nothing, so it opens
    # nothing. Either way the self-mute is lifted at once.
    played = False
    engine, fallback = "espeak-ng", None
    target = (required_sink() or {}).get("node") if SPEAK_SINK else None
    try:
        voice = neural_voice()
        if voice:
            # A NEURAL VOICE when this body names one (SAGE_SPEAK_VOICE), sentence by sentence
            # (tts_piper). Any failure falls back to espeak-ng: the being never loses its voice to it.
            try:
                r = subprocess.run([voice["python"], "-m", "sage.embodiment.tts_piper", "--model", voice["model"]]
                                   + (["--target", target] if target else []) + ["--", text],
                                   capture_output=True, timeout=timeout)
                if r.returncode == 0:
                    played, engine = True, f"piper:{voice['name']}"
                else:
                    fallback = (r.stderr.decode(errors="replace").strip().splitlines() or ["exit"])[-1][:200]
            except Exception as e:
                fallback = f"{type(e).__name__}: {e}"[:200]
        if not played:
            with tempfile.NamedTemporaryFile(suffix=".wav") as wav:
                # argv, never a shell: the words are one argument and cannot become a command
                subprocess.run(["espeak-ng", "-v", "en-us", "-s", "160", "-w", wav.name, "--", text],
                               check=True, capture_output=True, timeout=timeout)
                subprocess.run(["pw-play"] + (["--target", target] if target else []) + [wav.name],
                               check=True, capture_output=True, timeout=timeout)
                played = True
    finally:
        end = time.time()
        try:
            if played:
                _listening().mark(speaking_until=end + SELF_ECHO_TAIL_S,
                                  listen_until=end + LISTEN_WINDOW_S)
            else:
                _listening().mark(speaking_until=end)
        except Exception:
            pass
    out = {"chars": len(text), "seconds": round(time.time() - t0, 1), "engine": engine}
    if fallback:
        out["fallback_from_neural"] = fallback
    return out


# THE VOICE (dp, 2026-10-01: espeak-ng is "too harshly metallic/'robotic'"; he chose
# en_US-hfc_female-medium from four Piper voices played through the being's speaker). Opt-in per
# body: SAGE_SPEAK_VOICE names a Piper voice (a name in SAGE_PIPER_VOICES, or a path to its .onnx);
# SAGE_PIPER_PYTHON is the interpreter that has piper installed.
SPEAK_VOICE = os.environ.get("SAGE_SPEAK_VOICE", "").strip()
PIPER_VOICES = os.environ.get("SAGE_PIPER_VOICES") or os.path.expanduser("~/.local/share/piper-voices")
PIPER_PYTHON = os.environ.get("SAGE_PIPER_PYTHON", "").strip()


def neural_voice() -> Optional[Dict]:
    """{'name', 'model', 'python'} when this body has a usable neural voice, else None (espeak-ng)."""
    if not SPEAK_VOICE or not PIPER_PYTHON or not os.path.exists(PIPER_PYTHON):
        return None
    model = SPEAK_VOICE if SPEAK_VOICE.endswith(".onnx") else os.path.join(PIPER_VOICES, SPEAK_VOICE + ".onnx")
    if not os.path.exists(model):
        return None
    name = os.path.basename(model)[:-5]
    return {"name": name, "model": model, "python": PIPER_PYTHON}


# ---------------------------------------------------------------------------------------------
# hearing words: dp, 2026-09-26: "is there a path for it to hear when i reply in voice?" The cortex
# transcribes the mic ONLY inside a window that speak() opens, never while the being is speaking,
# and records words with no speaker identity (sage/embodiment/listening.py). Here the beat reads
# what was heard since the previous beat and says it as what it is: a voice in the room.
# ---------------------------------------------------------------------------------------------
LISTEN_WINDOW_S = 120
SELF_ECHO_TAIL_S = 0.5
HEARD_LOOKBACK_S = 3 * 3600


def _listening():
    from sage.embodiment import listening
    return listening


def _heard_since(ts: float) -> list:
    try:
        return _listening().since(ts)
    except Exception:
        return []


def ear_known(cur: Dict) -> bool:
    """A cortex that reports the ear's state (hearing + cause)."""
    return ((cur or {}).get("perception") or {}).get("audio_hearing") is not None


def _ago(seconds: float) -> str:
    m = int(seconds // 60)
    return "just now" if m < 1 else f"{m} min ago" if m < 120 else f"{m // 60} h ago"


def ear_line(cur: Dict, inv: Optional[Dict] = None, now: Optional[float] = None) -> str:
    """ONE line: is the ear hearing words, why not if not, since when, and when words last arrived.

    dp, 2026-10-01: audio may be offline "for any number of reasons - mute, bt disconnect, power off, or
    just me not being there. that's part of the world and its uncertain nature." So "could not listen" is
    said as such, with the cause when one is known, and is never presented as "nothing was said"."""
    now = time.time() if now is None else now
    p = (cur or {}).get("perception") or {}
    dev = (inv or {}).get("audio_device") or {}
    if not ear_known(cur) and not (dev and not dev.get("connected")):
        return ""
    if not p.get("live"):
        return ("- Your ear for words: unknown this beat (your senses are not reporting). Silence from it is "
                "not evidence that nobody spoke.")
    hearing, reason, key = bool(p.get("audio_hearing")), str(p.get("audio_ear") or ""), p.get("audio_ear_key")
    if dev and not dev.get("connected"):
        hearing, reason, key = False, "the headset is not connected", "device"
    try:
        since = _listening().ear_since()
    except Exception:
        since = None
    since_s = (f" since {time.strftime('%H:%M', time.localtime(float(since['ts'])))}"
               # SINCE BELONGS TO THE CAUSE SHOWN (GPT on #313): an hour muted, then the headset drops, must
               # not read "headset not connected since an hour ago". Same state AND same cause, or no since.
               if since and bool(since.get("hearing")) == hearing and key and since.get("key") == key
               and since.get("ts") else "")
    try:
        last = max([float(h.get("ts", 0)) for h in _heard_since(now - 7 * 86400)] or [0.0])
    except Exception:
        last = 0.0
    heard = f"; the last words it heard arrived {_ago(now - last)}" if last else "; it has heard no words yet"
    if hearing:
        return f"- Your ear for words is open ({reason}){since_s}{heard}."
    return (f"- Your ear for words is NOT hearing{since_s}: {reason}{heard}. Silence from it now is not "
            f"evidence that nobody spoke.")


def hears_always() -> bool:
    """The ear is always open: listen.json "always", which the cortex sets from SAGE_LISTEN=always."""
    try:
        return bool(_listening().window().get("always"))
    except Exception:
        return False


def can_hear_words(cur: Dict) -> bool:
    """A live ear with a listener that has not reported itself unavailable."""
    p = (cur or {}).get("perception") or {}
    w = str(p.get("audio_words") or "")
    return bool(p.get("audio_ok")) and bool(w) and not w.startswith("unavailable")


def _heard_mic(heard: list, inv: Optional[Dict]) -> str:
    """The mic that HEARD these words, not the first input in the census. Measured 2026-09-26:
    dp's "Can you hear me?" came through the Airhug (bluez source) and the beat said "Through
    Built-in Audio Analog Stereo", the first of two sources. The transcriber records the pipewire
    node it listened on; a bluez node is the census's bluetooth source."""
    sources = [x for x in ((inv or {}).get("audio_sources") or []) if x.get("name")]
    via = {str(h.get("source") or "") for h in heard}
    if via and all(v.startswith("bluez") for v in via):
        bt = [x for x in sources if x.get("kind") == "bluetooth"]
        if len(bt) == 1:
            return bt[0]["name"]
    if len(sources) == 1:
        return sources[0]["name"]
    return "your mic"


# ---------------------------------------------------------------------------------------------
# The headset as a body part that comes and goes (dp, 2026-09-27: "it should be aware when airhug
# is offline and know that speak is not available. it should also have a tool to try pairing,
# with status report - pairing won't always succeed"). Machine-level, like BODY_DIR:
#   SAGE_SPEAK_SINK  a substring of the output `speak` must use (Sprout: "AIRHUG"); unset = any
#                    output, as before. Set, speak is offered only while that output is present
#                    and plays to it by node, never to whatever happens to be the default.
#   SAGE_AUDIO_BT    the headset's Bluetooth address; enables the census line and `pair_audio`.
# The Airhug does not bond (Paired only per connection, Bonded: no, pair -> AlreadyExists), so
# a connect is the whole of "pairing" for it; a seat watchdog also reconnects it every minute.
# ---------------------------------------------------------------------------------------------
SPEAK_SINK = os.environ.get("SAGE_SPEAK_SINK", "").strip()
AUDIO_BT = os.environ.get("SAGE_AUDIO_BT", "").strip().upper()


def required_sink(audio: Optional[Dict] = None) -> Optional[Dict]:
    """The output `speak` is bound to, if present."""
    if not SPEAK_SINK:
        return None
    audio = _pw_audio() if audio is None else audio
    for x in (audio or {}).get("sinks") or []:
        if SPEAK_SINK.lower() in str(x.get("name", "")).lower():
            return x
    return None


def _btctl(*args, timeout: float = 10) -> str:
    import subprocess
    try:
        r = subprocess.run(["bluetoothctl", *args], capture_output=True, text=True, timeout=timeout)
        return (r.stdout or "") + (r.stderr or "")
    except Exception as e:
        return f"[bluetoothctl: {type(e).__name__}: {e}]"


def audio_device() -> Optional[Dict]:
    """{'mac', 'name', 'connected', 'known'} for the configured headset; None when none is."""
    if not AUDIO_BT or not shutil.which("bluetoothctl"):
        return None
    info = _btctl("info", AUDIO_BT, timeout=5)
    def field(k):
        for line in info.splitlines():
            if line.strip().startswith(k + ":"):
                return line.split(":", 1)[1].strip()
        return None
    return {"mac": AUDIO_BT, "name": field("Name") or field("Alias"), "known": "Device " in info,
            "connected": field("Connected") == "yes"}


def pair_audio(scan_s: int = 8) -> Dict:
    """Try to connect the configured headset, and report what happened in plain terms.
    Steps: state now -> if not connected, look for it (scan) -> connect -> state after."""
    before = audio_device()
    if before is None:
        return {"ok": False, "outcome": "not configured", "detail": "no headset is configured on this machine"}
    if before.get("connected"):
        return {"ok": True, "outcome": "already connected", "device": before}
    scan = _btctl("--timeout", str(scan_s), "scan", "on", timeout=scan_s + 5)
    seen = AUDIO_BT in scan.upper()
    out = _btctl("connect", AUDIO_BT, timeout=25)
    after = audio_device() or {}
    if after.get("connected"):
        return {"ok": True, "outcome": "connected", "seen": seen, "device": after}
    err = next((l.strip() for l in out.splitlines() if "Failed" in l or "Error" in l or "not available" in l), "")
    return {"ok": False, "outcome": "seen but the connection failed" if seen else "not seen",
            "seen": seen, "error": err[:200], "device": after or before}

