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
  ALWAYS LISTENING (opt-in per body, dp 2026-10-01): with SAGE_LISTEN=always in the cortex's environment
     the window is always open. dp asked aloud "what do you want to remember about today" long after the
     being last spoke; nothing was transcribed and nothing reached the being. dp: "any recognized voice
     input should be logged in the voice chat as it arrives. and hopefully presented to the being also."
     Bound 2 (never its own voice) and bound 3 (no speaker identity) still hold. The cortex records the
     mode in listen.json ("always"), so the being is told what its ear does (body.hears_always).
  WAKE PHRASE (opt-in per body, dp 2026-10-08): with SAGE_LISTEN=wake the ear still hears everything, but a
     voice becomes WORDS FOR THE BEING only after someone says its name ("hey Sprout"). That opens an
     engaged window of KEEPALIVE_S (dp: 30-45 s), extended by each addressed utterance and each of the
     being's spoken replies; "bye Sprout" closes it. Speech heard while not engaged is recorded only as the
     fact "speech nearby, not addressed to you" -- never its words (a news reel the being answered as if dp
     had spoken it, 2026-10-08). A short chime says the window opened. An interim step: the direction is a
     learned addressee/translation organ in the IRP stack, not a keyword.
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
EAR_LOG = os.path.join(BODY_DIR, "ear.jsonl")      # transitions of the ear's state, so "since when" is known

RATE = 16000
SPEECH_JUMP = 0.03         # a window this far above ambient baseline counts as voiced
SPEECH_FLOOR = 0.03        # ...and above this absolute level
# this much unvoiced audio ends an utterance. Per body (SAGE_LISTEN_PAUSE_S): at 0.8 s, dp's sentences
# arrived as several turns a second apart wherever he paused for breath (2026-10-01).
END_SILENCE_S = float(os.environ.get("SAGE_LISTEN_PAUSE_S") or 0.8)
UNHEARD_PATH = os.path.join(BODY_DIR, "unheard.jsonl")   # audio that produced no kept words, for measurement
MIN_VOICED_S = 0.4         # shorter than this is a knock or a cough, not words
MAX_UTTERANCE_S = 20.0     # cut and transcribe rather than buffer forever
PRE_ROLL_S = 0.3           # keep a little audio from before the onset so first syllables survive
# whisper hallucinates short stock phrases on near-silence; these gates drop them
NO_SPEECH_MAX = 0.6
LOGPROB_MIN = -1.0
KEEPALIVE_S = float(os.environ.get("SAGE_LISTEN_KEEPALIVE_S") or 40)   # wake mode: engaged window (dp: 30-45 s)

import re as _re
# The name as whisper actually writes it: "Sprout", and the near-misses it produces for it.
_NAME = r"(?:sprout|sprouts|spout|sprite|spraut)"
WAKE_RE = _re.compile(r"(?:^\W*" + _NAME + r"\b|\b(?:hey|hi|hello|ok|okay|yo)\W+" + _NAME + r"\b)\W*", _re.I)
BYE_RE = _re.compile(r"\b(?:bye|goodbye|good\s*night|that'?s\s+all)\W+" + _NAME + r"\b", _re.I)


def wake_match(text: str):
    """(addressed by name?, the words after the name). 'Hey Sprout, what do you see?' -> (True, 'what do you see?')."""
    m = WAKE_RE.search(text or "")
    if not m:
        return False, ""
    return True, (text[m.end():] or "").strip()


def says_goodbye(text: str) -> bool:
    return bool(BYE_RE.search(text or ""))


def always_listening() -> bool:
    """This body's opt-in: SAGE_LISTEN=always in this process's environment."""
    return os.environ.get("SAGE_LISTEN", "").strip().lower() == "always"


def wake_listening() -> bool:
    """This body's opt-in: SAGE_LISTEN=wake (hear everything, take words only after its name)."""
    return os.environ.get("SAGE_LISTEN", "").strip().lower() == "wake"


def window(now: Optional[float] = None, path: Optional[str] = None) -> dict:
    """{'listening', 'speaking', 'always'} from listen.json, plus this process's opt-in.
    Absent/unreadable file → closed unless the opt-in is set."""
    now = time.time() if now is None else now
    path = path or LISTEN_PATH
    try:
        d = json.load(open(path))
    except Exception:
        d = {}
    wake = wake_listening() or d.get("mode") == "wake"
    always = (always_listening() or bool(d.get("always"))) and not wake
    engaged = now < float(d.get("listen_until", 0))
    muted_until = float(d.get("muted_until", 0) or 0)
    muted = {"until": muted_until, "by": str(d.get("muted_by") or "")} if now < muted_until else None
    # In wake mode the segmenter must run while NOT engaged, or the name could never be heard.
    return {"listening": (always or wake or engaged) and not muted,
            "speaking": now < float(d.get("speaking_until", 0)),
            "always": always, "muted": muted, "wake": wake, "engaged": engaged,
            "keepalive_s": float(d.get("keepalive_s") or KEEPALIVE_S),
            "last_overheard": float(d.get("last_overheard") or 0)}


def engage(seconds: Optional[float] = None, path: Optional[str] = None, now: Optional[float] = None) -> float:
    """Open (or extend) the engaged window. Returns its end."""
    now = time.time() if now is None else now
    until = now + float(seconds if seconds is not None else window(now, path)["keepalive_s"])
    mark(path, listen_until=until)
    return until


def disengage(path: Optional[str] = None) -> None:
    mark(path, listen_until=0)


# THE EAR CAN BE OFF FOR ANY REASON (dp, 2026-10-01): "it should be resilient to audio being offline for
# any number of reasons - mute, bt disconnect, power off, or just me not being there. that's part of the
# world and its uncertain nature." So the ear's state is itself a sensed fact, with the cause when one is
# known, and "could not listen" is never presented as "heard nothing".
MUTE_MAX_MIN = 240          # a forgotten mute must not leave the being deaf for a day


def mute(minutes: float, by: str = "", path: Optional[str] = None) -> float:
    """Stop transcribing for `minutes` (capped); the being is told who and until when. Returns the end."""
    until = time.time() + max(0.0, min(float(minutes), MUTE_MAX_MIN)) * 60
    mark(path, muted_until=until, muted_by=by)
    return until


def unmute(path: Optional[str] = None) -> None:
    mark(path, muted_until=0, muted_by="")


def ear_state(ok: bool, words, win: dict, device_connected: Optional[bool] = None) -> tuple:
    """(hearing words?, reason in words, reason key). The first known cause wins, most physical first."""
    if device_connected is False:
        return False, "the headset is not connected", "device"
    if not ok:
        return False, "no sound is reaching the mic (the audio stream is down)", "stream"
    if str(words or "").startswith("unavailable"):
        return False, "word recognition is not available", "recognizer"
    m = (win or {}).get("muted")
    if m:
        return False, (f"muted by {m.get('by') or 'someone'} until "
                       f"{time.strftime('%H:%M', time.localtime(m['until']))}"), "muted"
    if not (win or {}).get("listening"):
        return False, "it only listens in the minutes after you speak", "window"
    if (win or {}).get("wake"):
        if (win or {}).get("engaged"):
            return True, "open since someone said your name", "engaged"
        return True, ("listening for your name ('hey Sprout'); other speech nearby is not given to you as "
                      "words"), "wake"
    return True, ("always open" if (win or {}).get("always") else "open since you spoke"), \
        ("always" if (win or {}).get("always") else "window")


def note_ear(hearing: bool, reason: str, key: str, path: Optional[str] = None,
             now: Optional[float] = None) -> Optional[dict]:
    """Append a line to ear.jsonl when the ear's state CHANGES (by hearing + key). Fails open."""
    path, now = path or EAR_LOG, time.time() if now is None else now
    try:
        last = ear_since(path)
        if last and bool(last.get("hearing")) == bool(hearing) and last.get("key") == key:
            return None
        line = {"ts": round(now, 2), "hearing": bool(hearing), "key": key, "reason": reason}
        with open(path, "a") as f:
            f.write(json.dumps(line) + "\n")
        return line
    except Exception:
        return None


def ear_since(path: Optional[str] = None) -> Optional[dict]:
    """The last ear transition (its ts is "since when"), or None."""
    try:
        with open(path or EAR_LOG, "rb") as f:
            f.seek(0, 2)
            f.seek(max(0, f.tell() - 4096))
            lines = f.read().decode(errors="replace").splitlines()
        return json.loads(lines[-1]) if lines else None
    except Exception:
        return None


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
        self.backlog_drops = 0        # utterances dropped because transcription fell behind (counted, logged)

    def submit(self, audio: bytes, ended_at: Optional[float] = None) -> bool:
        """Queue one utterance. `ended_at` is when the segmenter closed it (the person stopped speaking):
        the start of the latency the compiled-transducers arc's Track A measures (end of speech -> kept words)."""
        try:
            self.q.put_nowait((audio, time.time() if ended_at is None else float(ended_at)))
            return True
        except queue.Full:
            # a backlog means we are behind; drop rather than lag forever, but never silently
            self.backlog_drops += 1
            _append(UNHEARD_PATH, {"ts": round(time.time(), 2), "why": "backlog", "seconds":
                                   round(len(audio) / 2 / RATE, 1), "source": self.source})
            return False

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
        return judge_segments(r.get("segments") or [], seconds=round(len(a) / RATE, 1), source=self.source)

    def run(self):
        while self.running:
            try:
                item = self.q.get(timeout=1.0)
            except queue.Empty:
                continue
            audio, ended_at = item if isinstance(item, tuple) else (item, None)
            if self.model is None and not self.status.startswith("unavailable"):
                self._load()
            if self.model is None:
                continue
            self._handle(audio, ended_at)

    def _handle(self, audio: bytes, ended_at: Optional[float] = None) -> None:
        # TIMING BESIDE THE WORDS (compiled-transducers arc, Track A baseline): when the utterance ended, how long
        # it waited in the queue, and how long whisper took. Measurement only; nothing about what is kept changes.
        t0 = time.time()
        timing = {"asr_s": None}
        if ended_at is not None:
            timing.update({"t_end": round(float(ended_at), 2), "queue_s": round(t0 - float(ended_at), 3)})
        try:
            rec = self.transcribe(audio)
            timing["asr_s"] = round(time.time() - t0, 3)
        except Exception as e:
            # A TRANSCRIBER FAILURE IS NOT SILENCE (GPT on #325): measured, never shown as speech. The error's
            # class only, never its text (it can carry paths or audio-derived content).
            self.transcribe_errors = getattr(self, "transcribe_errors", 0) + 1
            _append(UNHEARD_PATH, {"ts": round(time.time(), 2), "why": "transcribe_error",
                                   "error": type(e).__name__, "seconds": round(len(audio) / 2 / RATE, 1),
                                   "source": self.source, **timing})
            return
        self._route(rec, timing)

    def _route(self, rec: Optional[dict], timing: dict, now: Optional[float] = None) -> str:
        """Where a transcription goes. Returns 'heard' | 'woke' | 'overheard' | 'unheard' (for tests and logs).

        Outside wake mode: kept words are heard, as before. In wake mode: engaged -> heard and the window is
        extended ("bye Sprout" closes it); the name -> the window opens (chime), and the words AFTER the name
        are this utterance's turn; anything else -> only the fact of speech nearby, never its words."""
        now = time.time() if now is None else now
        if not rec:
            return "none"
        if not rec.get("text"):
            _append(UNHEARD_PATH, dict(rec, why="no kept words", **timing))
            return "unheard"
        win = window(now)
        if not win.get("wake"):
            _append(self.heard_path, dict(rec, **timing))
            return "heard"
        text = rec["text"]
        if win.get("engaged"):
            _append(self.heard_path, dict(rec, **timing))
            if says_goodbye(text):
                disengage()
            else:
                engage(now=now)
            return "heard"
        named, rest = wake_match(text)
        if named:
            engage(now=now)
            chime()
            if rest:
                _append(self.heard_path, dict(rec, text=rest, by_name=True, **timing))
            return "woke"
        # Not addressed: the fact, not the words (other people's speech, a TV, a news reel).
        _append(UNHEARD_PATH, {"ts": rec.get("ts"), "why": "not addressed", "seconds": rec.get("seconds"),
                               "source": rec.get("source"), **timing})
        mark(last_overheard=round(now, 2))
        return "overheard"


CHIME_PATH = os.path.join(BODY_DIR, "chime.wav")


def chime() -> None:
    """A short, soft two-note chime: the engaged window opened. Fire-and-forget, never fatal. The ear is marked
    speaking for its length so it does not hear itself."""
    try:
        if not os.path.exists(CHIME_PATH):
            import math
            import struct
            import wave
            frames = b""
            for f, dur in ((880.0, 0.09), (1320.0, 0.12)):
                n = int(RATE * dur)
                for i in range(n):
                    env = min(1.0, i / 400, (n - i) / 400)          # no clicks
                    frames += struct.pack("<h", int(0.18 * 32767 * env * math.sin(2 * math.pi * f * i / RATE)))
            os.makedirs(os.path.dirname(CHIME_PATH), exist_ok=True)
            with wave.open(CHIME_PATH, "wb") as w:
                w.setnchannels(1); w.setsampwidth(2); w.setframerate(RATE); w.writeframes(frames)
        mark(speaking_until=time.time() + 0.6)
        import subprocess
        subprocess.Popen(["pw-play", CHIME_PATH], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    except Exception:
        pass   # measured, never shown as speech


def _append(path: str, rec: dict) -> None:
    try:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "a") as f:
            f.write(json.dumps(rec) + "\n")
    except Exception:
        pass


def judge_segments(segs: list, seconds: float = 0.0, source: str = "", now: Optional[float] = None) -> dict:
    """Whisper's segments -> one heard record. NOTHING IS DROPPED SILENTLY (dp, 2026-10-01: "voice transcription
    now cuts off what i said"). A segment is still left out of the words when it is probably silence
    (no_speech_prob >= NO_SPEECH_MAX, where whisper hallucinates stock phrases) or unclear speech
    (avg_logprob <= LOGPROB_MIN). But each left-out segment is kept in `dropped` with its reason, confidences
    and place, and `unclear` says where UNCLEAR speech was left out (head / middle / tail), so the room can
    say "the rest was unclear" instead of ending the sentence where the transcriber gave up."""
    kept_i, dropped = [], []
    for i, s in enumerate(segs):
        ns, lp = float(s.get("no_speech_prob", 0) or 0), float(s.get("avg_logprob", 0) or 0)
        if ns < NO_SPEECH_MAX and lp > LOGPROB_MIN:
            kept_i.append(i)
        else:
            dropped.append({"i": i, "text": str(s.get("text", "")).strip()[:200], "no_speech_prob": round(ns, 3),
                            "avg_logprob": round(lp, 3), "why": "silence" if ns >= NO_SPEECH_MAX else "unclear"})
    text = " ".join(str(segs[i].get("text", "")).strip() for i in kept_i).strip()
    rec = {"ts": round(time.time() if now is None else now, 2), "text": text, "seconds": seconds, "source": source}
    if dropped:
        for d in dropped:
            d["at"] = ("head" if kept_i and d["i"] < kept_i[0] else "tail" if kept_i and d["i"] > kept_i[-1]
                       else "middle" if kept_i else "all")
        rec["dropped"] = dropped
        places = [d["at"] for d in dropped if d["why"] == "unclear" and d["at"] != "all"]
        if places:
            rec["unclear"] = "tail" if "tail" in places else "head" if "head" in places else "middle"
    return rec


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


def main(argv=None) -> int:
    """sprout's ear, by hand:  python -m sage.embodiment.listening mute 45 [--by dp]  |  on  |  status"""
    import argparse
    ap = argparse.ArgumentParser(prog="python -m sage.embodiment.listening")
    sub = ap.add_subparsers(dest="cmd", required=True)
    m = sub.add_parser("mute"); m.add_argument("minutes", type=float); m.add_argument("--by", default="")
    sub.add_parser("on"); sub.add_parser("status")
    a = ap.parse_args(argv)
    if a.cmd == "mute":
        until = mute(a.minutes, a.by)
        print(f"ear muted until {time.strftime('%H:%M', time.localtime(until))} (max {MUTE_MAX_MIN} min)")
    elif a.cmd == "on":
        unmute(); print("ear unmuted")
    print(json.dumps({"window": window(), "since": ear_since()}, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
