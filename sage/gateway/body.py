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

PERCEPTION_PATH = os.path.expanduser("~/.sprout/perception.json")   # = visual_cortex.STATE_PATH
GAZE_PATH = os.path.expanduser("~/.sprout/gaze.json")               # = visual_cortex.GAZE_PATH
DAEMON_STATUS = "http://127.0.0.1:8760/status"
FRESH_S = 15.0          # perception older than this = the organ is not live
GAZE_MODES = ("open", "avert", "dwell", "closed")


def _read_json(path: str) -> Optional[dict]:
    try:
        return json.load(open(path))
    except Exception:
        return None


def perception(now: Optional[float] = None) -> Dict:
    """The cortex's latest state, or {'live': False, 'age_s': ...}."""
    now = time.time() if now is None else now
    d = _read_json(PERCEPTION_PATH)
    if not d:
        return {"live": False, "age_s": None}
    try:
        age = now - os.path.getmtime(PERCEPTION_PATH)
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
    return {"mode": g.get("mode", "open"), "target": g.get("target"), "chosen_by": g.get("chosen_by"),
            "ts": g.get("ts"), "words": g.get("words")}


def reading(now: Optional[float] = None) -> Dict:
    """Everything the body block is rendered from, recorded on the beat so the NEXT beat can say
    what changed since."""
    return {"perception": perception(now), "metabolism": metabolism(), "gaze": gaze(),
            "inventory": inventory(now)}


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
    if "gaze" in (inv.get("verbs") or []):
        lines.append("- You can change your gaze with `gaze` (open, avert, dwell, closed) and say why in "
                     "your own words. Your eyes will follow within seconds; you will see the difference "
                     "next beat. Nothing asks you to.")
    return "\n".join(lines)


def set_gaze(mode: str, member: str, target: Optional[str] = None, words: Optional[str] = None,
             path: str = GAZE_PATH) -> Dict:
    """Write the stance the cortex reads. Atomic; keeps the being's own words with it, as the
    cortex's witness expects. Raises ValueError on a mode outside the four."""
    mode = str(mode or "").strip().lower()
    if mode not in GAZE_MODES:
        raise ValueError(f"gaze mode must be one of {', '.join(GAZE_MODES)}; got {mode!r}")
    rec = {"mode": mode, "target": (str(target).strip()[:200] or None) if target else None,
           "chosen_by": member, "ts": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
           "words": (str(words).strip()[:500] or None) if words else None}
    os.makedirs(os.path.dirname(path), exist_ok=True)
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
    # cameras held by a live cortex (CSI via Argus) cannot be opened by a second process
    return {
        "video_devices": videos,
        "cameras_held_by_cortex": p.get("eyes", 0) if cortex_live else 0,
        "audio_sinks": audio.get("sinks", []), "audio_sources": audio.get("sources", []),
        "serial_devices": serials,
        "cortex_live": cortex_live, "daemon_live": bool(m.get("live")),
        "verbs": (["gaze"] if cortex_live else [])
                 + (["camera"] if videos and not cortex_live else [])
                 + ["say", "peer_ask"],
        "not_yet_wired": (["speak"] if audio.get("sinks") else []),
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

