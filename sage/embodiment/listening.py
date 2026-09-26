#!/usr/bin/env python3
"""Listening — words heard through the mic, in a window after the being speaks.

dp, 2026-09-26, after `speak` landed (#219): "is there a path for it to hear when i reply in
voice?" Hearing (audio.py) already gives LEVEL + ONSET from the Airhug mic. This adds WORDS, with
three bounds chosen so the ear is a reply channel and not a room recorder:

  1. ONLY IN A LISTENING WINDOW. `body.speak()` opens it (listen.json: listen_until = end of
     playback + LISTEN_WINDOW_S). Outside a window nothing is segmented, nothing is transcribed,
     nothing is written. The room is not transcribed while the being is silent.
  2. NEVER ITS OWN VOICE. speak() marks speaking_until before playback; while it holds, the
     segmenter drops audio, so the being is not handed its own words back as someone else's.
  3. NO SPEAKER IDENTITY. A voice is not authenticated. heard.jsonl records words, time and the
     mic — never who. The beat says "a voice in the room", not "dp said".

Transcription is whisper base.en on the GPU, loaded lazily on the first utterance (measured on
Sprout 2026-09-26: 2.3 s load, 0.47 s for a 3 s clip warm, 439 MB). Fails open: no whisper → the
state says so and Hearing's level/onset are untouched.
"""
from __future__ import annotations

import json
import os
import queue
import threading
import time
from typing import Optional

BODY_DIR = os.environ.get("SAGE_BODY_DIR") or os.path.expanduser("~/.sprout")
LISTEN_PATH = os.path.join(BODY_DIR, "listen.json")
HEARD_PATH = os.path.join(BODY_DIR, "heard.jsonl")

RATE = 16000
SPEECH_JUMP = 0.03         # a window this far above ambient baseline counts as voiced
SPEECH_FLOOR = 0.03        # ...and above this absolute level
END_SILENCE_S = 0.8        # this much unvoiced audio ends an utterance
MIN_VOICED_S = 0.4         # shorter than this is a knock or a cough, not words
MAX_UTTERANCE_S = 20.0     # cut and transcribe rather than buffer forever
PRE_ROLL_S = 0.3           # keep a little audio from before the onset so first syllables survive
# whisper hallucinates short stock phrases on near-silence; these gates drop them
NO_SPEECH_MAX = 0.6
LOGPROB_MIN = -1.0


def window(now: Optional[float] = None, path: Optional[str] = None) -> dict:
    """{'listening': bool, 'speaking': bool} from listen.json. Absent/unreadable → neither."""
    now = time.time() if now is None else now
    path = path or LISTEN_PATH
    try:
        d = json.load(open(path))
    except Exception:
        return {"listening": False, "speaking": False}
    return {"listening": now < float(d.get("listen_until", 0)),
            "speaking": now < float(d.get("speaking_until", 0))}


def mark(path: Optional[str] = None, **fields) -> None:
    """Merge fields into listen.json atomically (speak() uses this)."""
    path = path or LISTEN_PATH
    try:
        d = json.load(open(path))
    except Exception:
        d = {}
    d.update(fields)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = path + ".tmp"
    with open(tmp, "w") as f:
        json.dump(d, f)
    os.replace(tmp, path)


class Segmenter:
    """Cuts voiced stretches out of the 0.1 s windows Hearing already reads. Pure: feed() returns
    a finished utterance (bytes of s16le mono) or None; the window/speaking check is the caller's."""

    def __init__(self, win_s: float = 0.1):
        self.win_s = win_s
        self.pre: list = []
        self.buf: list = []
        self.voiced_s = 0.0
        self.silent_s = 0.0

    def reset(self):
        self.pre, self.buf, self.voiced_s, self.silent_s = [], [], 0.0, 0.0

    def feed(self, chunk: bytes, level: float, baseline: float) -> Optional[bytes]:
        voiced = level > SPEECH_FLOOR and level > baseline + SPEECH_JUMP
        if not self.buf:
            if voiced:
                self.buf = self.pre + [chunk]
                self.voiced_s, self.silent_s = self.win_s, 0.0
            else:
                self.pre = (self.pre + [chunk])[-int(PRE_ROLL_S / self.win_s):]
            return None
        self.buf.append(chunk)
        if voiced:
            self.voiced_s += self.win_s
            self.silent_s = 0.0
        else:
            self.silent_s += self.win_s
        length = len(self.buf) * self.win_s
        if self.silent_s >= END_SILENCE_S or length >= MAX_UTTERANCE_S:
            out = b"".join(self.buf) if self.voiced_s >= MIN_VOICED_S else None
            self.reset()
            return out
        return None


class Transcriber(threading.Thread):
    """Turns queued utterances into heard.jsonl lines. Loads whisper on first use; fails open."""

    def __init__(self, source: str, heard_path: Optional[str] = None, model_name: str = "base.en"):
        super().__init__(daemon=True)
        self.q: "queue.Queue[bytes]" = queue.Queue(maxsize=8)
        self.source, self.heard_path, self.model_name = source, heard_path or HEARD_PATH, model_name
        self.model = None
        self.status = "idle"          # idle | loading | ready | unavailable: <why>
        self.running = True

    def submit(self, audio: bytes) -> bool:
        try:
            self.q.put_nowait(audio)
            return True
        except queue.Full:
            return False              # a backlog means we are behind; drop rather than lag forever

    def _load(self):
        self.status = "loading"
        try:
            import torch
            import whisper
            dev = "cuda" if torch.cuda.is_available() else "cpu"
            self.model = whisper.load_model(self.model_name, device=dev)
            self._fp16 = dev == "cuda"
            self.status = "ready"
        except Exception as e:
            self.model = None
            self.status = f"unavailable: {type(e).__name__}: {e}"[:160]

    def transcribe(self, audio: bytes) -> Optional[dict]:
        import numpy as np
        a = np.frombuffer(audio, np.int16).astype(np.float32) / 32768.0
        r = self.model.transcribe(a, fp16=self._fp16, language="en", condition_on_previous_text=False)
        segs = r.get("segments") or []
        keep = [s for s in segs if s.get("no_speech_prob", 0) < NO_SPEECH_MAX
                and s.get("avg_logprob", 0) > LOGPROB_MIN]
        text = " ".join(s.get("text", "").strip() for s in keep).strip()
        if not text:
            return None
        return {"ts": round(time.time(), 2), "text": text, "seconds": round(len(a) / RATE, 1),
                "source": self.source}

    def run(self):
        while self.running:
            try:
                audio = self.q.get(timeout=1.0)
            except queue.Empty:
                continue
            if self.model is None and not self.status.startswith("unavailable"):
                self._load()
            if self.model is None:
                continue
            try:
                rec = self.transcribe(audio)
            except Exception:
                rec = None
            if rec:
                os.makedirs(os.path.dirname(self.heard_path), exist_ok=True)
                with open(self.heard_path, "a") as f:
                    f.write(json.dumps(rec) + "\n")


def since(ts: float, path: Optional[str] = None, limit: int = 10) -> list:
    """heard.jsonl entries newer than ts, oldest first, at most `limit` (the newest ones)."""
    path = path or HEARD_PATH
    out = []
    try:
        for line in open(path, errors="replace"):
            try:
                d = json.loads(line)
            except Exception:
                continue
            if float(d.get("ts", 0)) > ts and str(d.get("text", "")).strip():
                out.append(d)
    except FileNotFoundError:
        return []
    return out[-limit:]
