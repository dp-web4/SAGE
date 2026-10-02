#!/usr/bin/env python3
"""A neural voice for speak (Piper), sentence by sentence: each sentence plays while the next is made.

dp, 2026-10-01: the espeak-ng voice is "too harshly metallic/'robotic'"; of four Piper voices played through
the being's speaker he chose en_US-hfc_female-medium. Measured on Sprout (Orin Nano, CPU, the GPU left to the
being's model): 3.7 s to load a voice, then ~0.5 s per second of speech. Streaming by sentence puts the first
sound at load + one short sentence instead of load + the whole reply.

Run as a subprocess by body.speak() under the interpreter that has piper installed:
  python -m sage.embodiment.tts_piper --model <voice.onnx> [--target <pipewire node>] -- <text>
Exit 0 only if every sentence played. Any failure exits non-zero and speak() falls back to espeak-ng."""
from __future__ import annotations

import argparse
import re
import subprocess
import sys
import tempfile
import threading
import wave
from pathlib import Path

_SPLIT = re.compile(r"(?<=[.!?…])\s+")


def sentences(text: str) -> list:
    """Split at sentence ends; never return an empty piece."""
    return [s.strip() for s in _SPLIT.split(" ".join(str(text).split())) if s.strip()]


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--model", required=True)
    ap.add_argument("--target", default="")
    ap.add_argument("text", nargs="+")
    a = ap.parse_args(argv)
    from piper import PiperVoice                     # only in this interpreter
    voice = PiperVoice.load(a.model)
    tmp = Path(tempfile.mkdtemp(prefix="speak-"))
    errors: list = []
    player = None

    def play(path: Path, prev):
        if prev is not None:
            prev.join()
        if errors:
            return
        r = subprocess.run(["pw-play"] + (["--target", a.target] if a.target else []) + [str(path)],
                           capture_output=True, timeout=120)
        if r.returncode != 0:
            errors.append(f"pw-play exit {r.returncode}: {r.stderr.decode(errors='replace')[:200]}")

    for i, s in enumerate(sentences(" ".join(a.text))):
        f = tmp / f"{i:02d}.wav"
        with wave.open(str(f), "wb") as w:
            voice.synthesize_wav(s, w)
        player = threading.Thread(target=play, args=(f, player), daemon=True)
        player.start()
    if player is not None:
        player.join()
    for f in tmp.glob("*.wav"):
        f.unlink(missing_ok=True)
    tmp.rmdir()
    if errors:
        print(errors[0], file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
