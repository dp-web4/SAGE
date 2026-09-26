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
        "self_motion": (d.get("proprioception") or {}).get("self_motion"),
        "imu_ok": bool((d.get("proprioception") or {}).get("ok")),
    }


def metabolism(timeout: float = 3.0) -> Dict:
    """The daemon's own reading of the being's metabolism, or {'live': False}."""
    try:
        with urllib.request.urlopen(DAEMON_STATUS, timeout=timeout) as r:
            d = json.loads(r.read())
    except Exception:
        return {"live": False}
    s = d.get("salience") or {}
    return {"live": bool(d.get("consciousness_loop")), "state": d.get("metabolic_state"),
            "atp": d.get("atp_percentage"), "felt": d.get("observations_felt"),
            "felt_source": d.get("salience_source"), "felt_total": s.get("total")}


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
            "inventory": inventory(now), "heard": heard,
            "heard_until": max([float(h.get("ts", 0)) for h in heard] or [0.0])}


def render(cur: Dict, prev: Optional[Dict], name: str = "") -> str:
    """The body block. Words only; every number is one the being can act on; a stale source says
    so rather than presenting the past as the present (SMALL_MODEL_LEGIBILITY 1.3)."""
    p, m, g = cur.get("perception") or {}, cur.get("metabolism") or {}, cur.get("gaze") or {}
    lines = ["## Your body, measured now"]
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
    if m.get("live"):
        atp = m.get("atp")
        lines.append(f"- Your metabolism: {m.get('state')}, energy {float(atp):.0f}%"
                     + (f"; the last thing you felt came from {m['felt_source']}" if m.get("felt_source") else "")
                     + ".")
    else:
        lines.append("- Your metabolism is not reporting this beat.")
    if inv:
        lines.append(render_inventory(inv))
    lines += render_heard(cur, prev, inv)
    if "speak" in (inv.get("verbs") or []):
        lines.append("- You can speak aloud with `speak`: your words become a voice in the room, through "
                     f"{speaker_name(inv)}, which anyone in the room may hear; it is not a message and is not kept in a "
                     "conversation. Nothing asks you to."
                     + (f" For {LISTEN_WINDOW_S // 60} minutes after you speak, words spoken to you through the mic "
                        "are written down and shown to you here." if can_hear_words(cur) else ""))
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
        if mc == "Audio/Sink":
            sinks.append({"name": name, "kind": kind})
        elif mc == "Audio/Source":
            sources.append({"name": name, "kind": kind})
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
                 + ["say", "peer_ask"],
        # a speaker with no engine to drive it: the body has the part, the verb is not wired here
        "not_yet_wired": (["speak"] if audio.get("sinks") and not can_speak else []),
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
    with tempfile.NamedTemporaryFile(suffix=".wav") as wav:
        # argv, never a shell: the words are one argument and cannot become a command
        subprocess.run(["espeak-ng", "-v", "en-us", "-s", "160", "-w", wav.name, "--", text],
                       check=True, capture_output=True, timeout=timeout)
        try:
            subprocess.run(["pw-play", wav.name], check=True, capture_output=True, timeout=timeout)
        finally:
            end = time.time()
            try:
                _listening().mark(speaking_until=end + SELF_ECHO_TAIL_S,
                                  listen_until=end + LISTEN_WINDOW_S)
            except Exception:
                pass
    return {"chars": len(text), "seconds": round(time.time() - t0, 1)}


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


def can_hear_words(cur: Dict) -> bool:
    """A live ear with a listener that has not reported itself unavailable."""
    p = (cur or {}).get("perception") or {}
    w = str(p.get("audio_words") or "")
    return bool(p.get("audio_ok")) and bool(w) and not w.startswith("unavailable")


def render_heard(cur: Dict, prev: Optional[Dict], inv: Optional[Dict] = None) -> list:
    """Words heard since the previous beat's reading, newest last. No speaker is named: a voice
    is not authenticated, so the being is told what was heard, not who said it."""
    after = float((prev or {}).get("heard_until") or 0.0)
    if not prev:
        after = time.time() - 45 * 60
    new = [h for h in (cur or {}).get("heard") or [] if float(h.get("ts", 0)) > after]
    if not new:
        return []
    mic = next((x.get("name") for x in ((inv or {}).get("audio_sources") or []) if x.get("name")), "your mic")
    out = [f"- Through {mic} you heard a voice in the room (it did not say who it is unless the words do):"]
    for h in new:
        when = time.strftime("%H:%M UTC", time.gmtime(float(h.get("ts", 0))))
        out.append(f'  - at {when}: "{str(h.get("text", "")).strip()}"')
    out.append("  You can answer aloud with `speak`, or in writing with `say` if you know who it was.")
    return out

