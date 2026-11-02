"""The body's audio plumbing, per platform: one place that knows which program captures and plays.

Sprout's body is PipeWire on Linux: `pw-record` from the Airhug's HFP mic, `pw-play`, `espeak-ng`,
and `pw-dump` for the inventory. McNugget's body (2026-10-15: a USB mic, a USB camera and the monitor's
speakers) is a Mac: no PipeWire. The ear, the voice and the inventory keep their designs -- a capture
SUBPROCESS writing 16 kHz mono s16le to stdout and respawned if it dies, a played file, a measured
inventory -- and only the programs change:

  | act             | pipewire (Linux)               | avfoundation (macOS)                                 |
  |-----------------|--------------------------------|------------------------------------------------------|
  | capture         | pw-record --target <node>      | ffmpeg -f avfoundation -i :<device> -f s16le (no header) |
  | play a file     | pw-play [--target <node>]      | afplay (the system default output)                   |
  | fallback voice  | espeak-ng -w out.wav -- text   | say -o out.wav -f <text file> (the words never in argv) |
  | inventory       | pw-dump                        | system_profiler -json SPAudioDataType                |
  | camera frame    | ffmpeg -f v4l2 -i /dev/videoN  | ffmpeg -f avfoundation -i "<camera>:none"            |

Chosen like the launchd wake path (SAGE #359): $SAGE_AUDIO_BACKEND ("pipewire" | "avfoundation")
when set, otherwise avfoundation on Darwin and pipewire everywhere else. Nothing here changes what
Linux runs. ffmpeg writes RAW PCM, not WAV: its WAV header carries a LIST chunk that would put
`data` past audio.py's 64-byte header skip, so the capture reports whether a header follows.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
from typing import Dict, List, Optional, Tuple


def backend() -> str:
    explicit = os.environ.get("SAGE_AUDIO_BACKEND", "").strip().lower()
    if explicit in ("pipewire", "avfoundation"):
        return explicit
    return "avfoundation" if sys.platform == "darwin" else "pipewire"


def mac_device() -> str:
    """The AVFoundation audio input: $SAGE_AUDIO_DEVICE (a name or an index), else the default input."""
    return os.environ.get("SAGE_AUDIO_DEVICE", "").strip() or "default"


def capture_cmd(source: str, rate: int) -> Tuple[List[str], bool]:
    """(argv, has_wav_header) for a process writing `rate` Hz mono s16le to stdout."""
    if backend() == "avfoundation":
        return (["ffmpeg", "-nostdin", "-hide_banner", "-loglevel", "error",
                 "-f", "avfoundation", "-i", f":{mac_device()}",
                 "-ac", "1", "-ar", str(rate), "-f", "s16le", "-"], False)
    return (["pw-record", "--target", source, "--rate", str(rate),
             "--channels", "1", "--format", "s16", "-"], True)


def capture_source(default_source: str) -> str:
    """The label the ear records its words under: the PipeWire node, or the AVFoundation device."""
    return f"avfoundation:{mac_device()}" if backend() == "avfoundation" else default_source


def play_cmd(path: str, target: Optional[str] = None) -> List[str]:
    """argv that plays one audio file. afplay has no device choice: it plays on the system default
    output, so on a Mac the speaker is chosen in System Settings (or the default output)."""
    if backend() == "avfoundation":
        return ["afplay", str(path)]
    return ["pw-play"] + (["--target", target] if target else []) + [str(path)]


def voice_tools() -> Tuple[str, str]:
    """(synthesizer, player) the fallback voice needs installed."""
    return ("say", "afplay") if backend() == "avfoundation" else ("espeak-ng", "pw-play")


def synth_fallback(text: str, out_wav: str, timeout: float) -> None:
    """Render `text` to a WAV with the platform's built-in voice. Raises on failure.
    The words are never a shell string; on macOS they never reach argv at all (`say -f`)."""
    if backend() == "avfoundation":
        import tempfile
        with tempfile.NamedTemporaryFile("w", suffix=".txt", encoding="utf-8") as tf:
            tf.write(text)
            tf.flush()
            subprocess.run(["say", "-o", out_wav, "--file-format=WAVE", "--data-format=LEI16@22050",
                            "-f", tf.name], check=True, capture_output=True, timeout=timeout)
        return
    subprocess.run(["espeak-ng", "-v", "en-us", "-s", "160", "-w", out_wav, "--", text],
                   check=True, capture_output=True, timeout=timeout)


# THE CAMERA ON A MAC (2026-10-15, McNugget: a UVC camera, "AIRHUG 02"). Linux names a camera by its
# /dev/video node; AVFoundation names it by its device name. The same AVFoundation list holds the
# SCREENS ("Capture screen 0"), so the being never picks the device: the seat does, from the cameras
# alone. It is on whenever one is attached; unplugging it is the off switch, and the being sees that
# as the camera going away (gateway/body.camera_change). The sensor needs about a second to settle
# (the first frames come out solid green, then underexposed), so the capture discards 1.5 s first.
CAMERA_WARMUP_S = 1.5


def mac_cameras(timeout: float = 6.0, raw: Optional[str] = None) -> List[str]:
    """The AVFoundation VIDEO devices that are cameras (screens dropped), in ffmpeg's order.
    [] when ffmpeg is missing or unreadable. `raw` is a test seam (ffmpeg's -list_devices stderr)."""
    try:
        if raw is None:
            raw = subprocess.run(["ffmpeg", "-hide_banner", "-f", "avfoundation", "-list_devices", "true",
                                  "-i", ""], capture_output=True, text=True, timeout=timeout).stderr
    except Exception:
        return []
    names, in_video = [], False
    for line in raw.splitlines():
        if "AVFoundation video devices" in line:
            in_video = True
        elif "AVFoundation audio devices" in line:
            in_video = False
        elif in_video and "] [" in line:
            name = line.split("] [", 1)[1].split("] ", 1)[-1].strip()
            if name and not name.lower().startswith("capture screen"):
                names.append(name)
    return names


def mac_camera(cameras: Optional[List[str]] = None) -> Optional[str]:
    """The camera the seat captures from: $SAGE_CAMERA_DEVICE if it names a camera, else the first
    camera. None when there is none. A pinned name that is not a camera (a screen) is refused."""
    cams = mac_cameras() if cameras is None else cameras
    pinned = os.environ.get("SAGE_CAMERA_DEVICE", "").strip()
    if pinned:
        return pinned if pinned in cams else None
    return cams[0] if cams else None


def mac_camera_cmd(camera: str, out_path: str) -> List[str]:
    """argv for one JPEG from an AVFoundation camera, after the warm-up, written atomically by image2."""
    return ["ffmpeg", "-hide_banner", "-loglevel", "error", "-y", "-f", "avfoundation",
            "-framerate", "30", "-pixel_format", "nv12", "-i", f"{camera}:none",
            "-ss", str(CAMERA_WARMUP_S), "-frames:v", "1", "-qscale:v", "3",
            "-f", "image2", "-atomic_writing", "1", out_path]


# BY ABSOLUTE PATH: system_profiler is in /usr/sbin, which a launchd job's PATH does not carry (the heartbeat's is
# /opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin). Called by name it failed in every beat, mac_audio returned {}, and
# speak_provider said "no audio output is connected": every spoken answer mcnugget-being gave the room from
# 2026-10-24 ("I can hear you clearly") was refused, with the Mac mini speaker connected (2026-10-26).
SYSTEM_PROFILER = "/usr/sbin/system_profiler"


def mac_audio(timeout: float = 6.0, raw: Optional[str] = None) -> Dict:
    """Audio sinks and sources as macOS sees them, in the shape pw-dump gives: {} when unreadable.
    `raw` is a test seam (system_profiler's JSON)."""
    try:
        if raw is None:
            raw = subprocess.run([SYSTEM_PROFILER, "-json", "SPAudioDataType"],
                                 capture_output=True, text=True, timeout=timeout).stdout
        data = json.loads(raw)
    except Exception:
        return {}
    sinks, sources = [], []
    for group in data.get("SPAudioDataType") or []:
        for d in group.get("_items") or []:
            name = str(d.get("_name") or "?")
            transport = str(d.get("coreaudio_device_transport") or "")
            kind = "bluetooth" if "bluetooth" in transport.lower() else "wired"
            entry = {"name": name, "kind": kind, "node": name}
            if d.get("coreaudio_device_output"):
                sinks.append(dict(entry, default=d.get("coreaudio_default_audio_output_device") == "spaudio_yes"))
            if d.get("coreaudio_device_input"):
                sources.append(dict(entry, default=d.get("coreaudio_default_audio_input_device") == "spaudio_yes"))
    return {"sinks": sinks, "sources": sources}
