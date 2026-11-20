"""The being's output as it is produced: its thinking, its words and its tool calls, live.

dp, 2026-11-20: "having the agent's stream in all major cli harnesses is a key feature and liveness indicator,
which sage has left out so far." A beat called the model with stream off, so nothing it produced was visible
until each call returned (a minute or more on Sprout), and a beat that was generating looked the same as one
that had hung. Here each call in a beat streams, and what arrives is appended to <instance>/STREAM_FILE as it
comes. The TUI's stream page and the daemon's dashboard read that file; nothing the beat decides reads it.

ONE LINE PER EVENT, JSON:
  {"t": epoch s, "beat": host session id, "k": kind, ...}
  k = "beat"   a beat began                       (+ "member", "model")
      "call"   a model call began                 (+ "turn", "phase")
      "think"  thinking text, as it came          (+ "s")
      "text"   the reply's words, as they came    (+ "s")
      "tool"   a tool call the model made         (+ "name", "args": first ARGS_SHOWN chars of its arguments)
      "done"   the call ended                     (+ "reason", "eval_count", "s_elapsed")
      "error"  the call failed                    (+ "s")
      "end"    the beat ended

Text is gathered and written at most every FLUSH_S, and at every change of kind, so a fast model costs a
handful of writes a second, not one per token. A STREAM SINK NEVER COSTS THE BEAT ANYTHING: every write is
guarded, and a failing disk turns the sink off for the rest of the beat rather than raising into the call.
The file is kept to MAX_BYTES: at a beat's start, a file past it is moved to STREAM_FILE + ".1" (one older
copy), so the view starts on a clean beat and the disk use is bounded at about twice MAX_BYTES.
"""
from __future__ import annotations

import json
import os
import threading
import time
from pathlib import Path
from typing import Optional

STREAM_FILE = "output_stream.jsonl"
FLUSH_S = 0.25
MAX_BYTES = 2 * 1024 * 1024
ARGS_SHOWN = 600

_current: Optional["Stream"] = None


class Stream:
    """One beat's sink. Methods never raise."""

    def __init__(self, instance, beat: str):
        self.path = Path(instance) / STREAM_FILE
        self.beat = beat
        self.turn = ""
        self._buf_kind = ""
        self._buf = []
        self._last_flush = 0.0
        self._t_call = 0.0
        self._dead = False
        self._lock = threading.Lock()

    # -- writing ------------------------------------------------------------------------------------------

    def _write(self, rec: dict) -> None:
        if self._dead:
            return
        rec = {"t": round(time.time(), 3), "beat": self.beat, **rec}
        try:
            with open(self.path, "a", encoding="utf-8") as f:
                f.write(json.dumps(rec, ensure_ascii=False, default=str) + "\n")
        except Exception:
            self._dead = True          # a sink that cannot write stops trying; the beat goes on

    def _flush(self) -> None:
        if self._buf:
            self._write({"k": self._buf_kind, "s": "".join(self._buf)})
        self._buf, self._buf_kind = [], ""
        self._last_flush = time.time()

    def _add(self, kind: str, s: str) -> None:
        if not s:
            return
        if self._buf_kind and kind != self._buf_kind:
            self._flush()
        self._buf_kind = kind
        self._buf.append(s)
        if time.time() - self._last_flush >= FLUSH_S:
            self._flush()

    # -- the beat's side ----------------------------------------------------------------------------------

    def begin_beat(self, member: str = "", model: str = "") -> None:
        try:
            if self.path.exists() and self.path.stat().st_size > MAX_BYTES:
                os.replace(self.path, str(self.path) + ".1")
        except Exception:
            pass
        self._write({"k": "beat", "member": member, "model": model})

    def end_beat(self) -> None:
        with self._lock:
            self._flush()
            self._write({"k": "end"})

    def begin_call(self, phase: str) -> None:
        with self._lock:
            self._flush()
            self._t_call = time.time()
            self._write({"k": "call", "turn": self.turn, "phase": phase})

    def chunk(self, message: dict) -> None:
        """One streamed piece of the reply: ollama's chunk["message"]."""
        try:
            with self._lock:
                m = message or {}
                self._add("think", str(m.get("thinking") or ""))
                self._add("text", str(m.get("content") or ""))
                for tc in m.get("tool_calls") or []:
                    self._flush()
                    fn = (tc or {}).get("function") or {}
                    args = fn.get("arguments")
                    args = args if isinstance(args, str) else json.dumps(args, ensure_ascii=False, default=str)
                    self._write({"k": "tool", "name": str(fn.get("name") or "?"), "args": args[:ARGS_SHOWN]})
        except Exception:
            pass

    def end_call(self, raw: Optional[dict], content: str = "") -> None:
        try:
            with self._lock:
                self._flush()
                raw = raw or {}
                if content.startswith("[OllamaIRP:"):
                    self._write({"k": "error", "s": content[:300]})
                    return
                self._write({"k": "done", "reason": raw.get("done_reason"), "eval_count": raw.get("eval_count"),
                             "s_elapsed": round(time.time() - self._t_call, 1)})
        except Exception:
            pass


# -- the process-wide current beat -------------------------------------------------------------------------

def start(instance, beat: str, member: str = "", model: str = "") -> Optional[Stream]:
    """Open this beat's sink and make it current. None when the instance cannot be written."""
    global _current
    try:
        s = Stream(instance, beat)
        s.begin_beat(member, model)
        _current = s
        return s
    except Exception:
        _current = None
        return None


def stop() -> None:
    global _current
    s, _current = _current, None
    if s is not None:
        s.end_beat()


def current() -> Optional[Stream]:
    return _current


def set_turn(turn: str) -> None:
    if _current is not None:
        _current.turn = turn


# -- reading (the TUI, tests) ------------------------------------------------------------------------------

def read_tail(path, max_bytes: int = 256 * 1024) -> list:
    """The last events in the file, oldest first; a first line cut by the window is dropped."""
    try:
        with open(path, "rb") as f:
            f.seek(0, os.SEEK_END)
            size = f.tell()
            start = max(0, size - max_bytes)
            f.seek(max(0, start - 1))
            data = f.read()
    except OSError:
        return []
    if start > 0:
        # one byte before the window: a newline there means the window starts a line, which is whole
        whole, data = data[:1] == b"\n", data[1:]
    lines = data.split(b"\n")
    if start > 0 and not whole:
        lines = lines[1:]
    out = []
    for l in lines:
        try:
            out.append(json.loads(l))
        except ValueError:
            continue
    return out
