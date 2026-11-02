"""Whisper through whisper.cpp's server: the ear without torch (compiled-transducers arc, Track A).

Why (measured on Sprout 2026-10-11, Orin, 7.4 GB unified, desktop kept): openai-whisper on the GPU holds
325 MB (tiny.en) / 511 MB (base.en) of GPU memory plus 580-700 MB resident, nearly all of it torch's CUDA
runtime, not the model. The same models through whisper.cpp on the CPU hold 153 / 242 MB resident and no
GPU memory at all, start in 0.3 s, and give the ear's guard what it needs: per-segment `no_speech_prob` and
`avg_logprob` (the server's `verbose_json`), so `listening.judge_segments` judges them unchanged.

One `whisper-server` child per ear, bound to 127.0.0.1 on a free port, started on the first utterance and
stopped by `stop()` (the ear's idle unload). Nothing here imports numpy or torch: the ear hands 16 kHz mono
int16 PCM, which is what goes on the wire.

SETUP, per body (whisper.cpp is not vendored; SAGE_WHISPERCPP_HOME points at the checkout, default
~/ai-workspace/whisper.cpp):
    git clone https://github.com/ggml-org/whisper.cpp && cd whisper.cpp
    git checkout 7e26d3b          # the commit measured; the client needs verbose_json's no_speech_prob
    cmake -B build -DGGML_CUDA=OFF -DCMAKE_BUILD_TYPE=Release && cmake --build build -j --target whisper-server
    sh ./models/download-ggml-model.sh base.en        # or tiny.en; the ear's SAGE_LISTEN_MODEL picks
Then SAGE_LISTEN_BACKEND=whispercpp in the cortex's service environment.

AUDIO CONTEXT: FULL BY DEFAULT, BECAUSE THE FITTED ONE INVENTS WORDS. Whisper pads every clip to 30 s, so the
encoder costs the same for a 2 s "hey Sprout" as for 30 s of speech. `audio_ctx` sizes the encoder to the
clip instead (50 frames per second plus a margin) and is 3-4x faster, but on the arc's corpus (asr_harness,
332 clips, Sprout 2026-10-11) base.en with it put words on 39 of 40 near-silence / noise-only clips
("consequently", "(water splashing)") with a no_speech_prob low enough to pass judge_segments, and clean-
speech WER rose 9.6% -> 15.3%. A shortened context makes the guard's own signal unreliable, so it is opt-in
(SAGE_WHISPERCPP_FIT_CTX=1) and never the default.
"""
from __future__ import annotations

import io
import json
import os
import socket
import subprocess
import time
import urllib.request
import wave
from typing import List, Optional

RATE = 16000
HOME = os.path.expanduser(os.environ.get("SAGE_WHISPERCPP_HOME") or "~/ai-workspace/whisper.cpp")
BIN = os.environ.get("SAGE_WHISPERCPP_BIN") or os.path.join(HOME, "build", "bin", "whisper-server")
MODELS = os.environ.get("SAGE_WHISPERCPP_MODELS") or os.path.join(HOME, "models")
try:
    THREADS = max(1, int(os.environ.get("SAGE_WHISPERCPP_THREADS") or 4))   # 4 beat 6 on Sprout's 6 cores
except ValueError:
    THREADS = 4
FULL_CTX = (os.environ.get("SAGE_WHISPERCPP_FIT_CTX") or "").strip() != "1"


def model_path(name: str) -> str:
    """'base.en' -> <models>/ggml-base.en.bin; a path is taken as given."""
    return name if os.sep in name or name.endswith(".bin") else os.path.join(MODELS, f"ggml-{name}.bin")


def audio_ctx(seconds: float) -> int:
    """Encoder frames for a clip: 50 per second of audio plus a margin, never more than Whisper's 1500."""
    return min(1500, int(seconds * 50) + 128)


def wav_bytes(pcm16: bytes, rate: int = RATE) -> bytes:
    b = io.BytesIO()
    with wave.open(b, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(rate)
        w.writeframes(pcm16)
    return b.getvalue()


def join_split_words(raw: List[dict]) -> List[dict]:
    """whisper.cpp ends a segment mid-word ("how lumin" | "ous these criticisms"); the continuation is the one
    that does not start with whitespace. judge_segments strips each segment and joins them with spaces, so left
    split it reads "lumin ous" (arc corpus, base.en: 39 utterances worse than the reference and 24 better
    before this join, 26 and 24 after). A continuation is folded into the segment before it, so the guard judges whole words: the larger
    no_speech_prob (the cautious one; whisper.cpp reports it once per window) and avg_logprob weighted by tokens."""
    out: List[dict] = []
    for s in raw:
        text = str(s.get("text") or "")
        n = max(1, len(s.get("tokens") or []))
        seg = {"text": text, "start": s.get("start"), "end": s.get("end"),
               "no_speech_prob": s.get("no_speech_prob"), "avg_logprob": s.get("avg_logprob"), "_n": n}
        if out and text and not text[0].isspace():
            p = out[-1]
            lp = [x for x in (p["avg_logprob"], seg["avg_logprob"]) if x is not None]
            p["avg_logprob"] = (((p["avg_logprob"] or 0) * p["_n"] + (seg["avg_logprob"] or 0) * n) / (p["_n"] + n)
                                if len(lp) == 2 else (lp[0] if lp else None))
            ns = [x for x in (p["no_speech_prob"], seg["no_speech_prob"]) if x is not None]
            p["no_speech_prob"] = max(ns) if ns else None
            p["text"], p["end"], p["_n"] = p["text"] + text, seg["end"], p["_n"] + n
        else:
            out.append(seg)
    for s in out:
        s.pop("_n")
    return out


def _die_with_parent() -> List[str]:
    """The server must not outlive the ear: a cortex killed without its finally (SIGKILL, a watchdog restart
    outside systemd's cgroup) would otherwise leave ~240 MB behind. util-linux `setpriv --pdeathsig` sets
    PR_SET_PDEATHSIG in the child before exec; not `preexec_fn`, which Python documents as unsafe in a threaded
    process (the cortex is one). The signal follows the spawning THREAD, which is the ear's long-lived
    transcriber. Without setpriv the server only stops with the ear's own stop() or the service's cgroup."""
    import shutil
    return ["setpriv", "--pdeathsig", "TERM"] if shutil.which("setpriv") else []


class NoConfidence(RuntimeError):
    """The server gave a segment without Whisper's confidences. judge_segments would read the missing values as
    0 and keep everything, which switches off the guard against words on silence, so this is an error (the ear
    logs a transcribe_error, never speech), not a default."""


def _free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


class WhisperCpp:
    """A whisper-server child. `segments(pcm16)` -> Whisper-shaped segments (text, no_speech_prob,
    avg_logprob, start, end). Raises on failure; the caller decides what a failure means."""

    def __init__(self, model: str, bin_path: Optional[str] = None, threads: Optional[int] = None,
                 full_ctx: Optional[bool] = None):
        self.model = model_path(model)
        self.bin = bin_path or BIN
        self.threads = threads or THREADS
        self.full_ctx = FULL_CTX if full_ctx is None else full_ctx
        self.proc: Optional[subprocess.Popen] = None
        self.port = 0

    def start(self, timeout: float = 30.0) -> None:
        for p, what in ((self.bin, "whisper-server"), (self.model, "model")):
            if not os.path.exists(p):
                raise FileNotFoundError(f"{what} not found: {p}")
        self.port = _free_port()
        # AN UNGUESSABLE PATH. whisper-server also serves POST /load, which swaps the model for any file path;
        # on a bare 127.0.0.1 port any local process could change what the ear hears with. Every route sits
        # under a random prefix only this client knows, so a stranger gets 404 (and so does a different server
        # that took the port between _free_port and bind).
        self.path = "/" + os.urandom(12).hex()
        # -ng (--no-gpu): CPU ONLY, whatever the binary was built with. The docstring asks for a
        # -DGGML_CUDA=OFF build, but SAGE_WHISPERCPP_BIN can point at a CUDA build, and whisper-server
        # defaults use_gpu=true -- the ear would then load onto the card the being's model needs
        # (fleet policy: the being takes GPU priority). One flag makes the policy the code's, not the build's.
        self.proc = subprocess.Popen(
            _die_with_parent() + [self.bin, "-ng", "-m", self.model, "-t", str(self.threads), "--host", "127.0.0.1",
                                  "--port", str(self.port), "--request-path", self.path],
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        end = time.time() + timeout
        while time.time() < end:
            if self.proc.poll() is not None:
                raise RuntimeError(f"whisper-server exited with {self.proc.returncode}")
            try:
                urllib.request.urlopen(f"http://127.0.0.1:{self.port}{self.path}/", timeout=1)
                return
            except Exception:
                time.sleep(0.1)
        self.stop()
        raise TimeoutError("whisper-server did not come up")

    def alive(self) -> bool:
        return self.proc is not None and self.proc.poll() is None

    def segments(self, pcm16: bytes, timeout: float = 60.0) -> List[dict]:
        if not self.alive():
            self.start()
        fields = {"response_format": "verbose_json", "temperature": "0.0", "temperature_inc": "0.2"}
        if not self.full_ctx:
            fields["audio_ctx"] = str(audio_ctx(len(pcm16) / 2 / RATE))
        bd = "sage-ear-" + os.urandom(8).hex()
        parts = [f"--{bd}\r\nContent-Disposition: form-data; name=\"file\"; filename=\"u.wav\"\r\n"
                 f"Content-Type: audio/wav\r\n\r\n".encode() + wav_bytes(pcm16) + b"\r\n"]
        parts += [f"--{bd}\r\nContent-Disposition: form-data; name=\"{k}\"\r\n\r\n{v}\r\n".encode()
                  for k, v in fields.items()]
        req = urllib.request.Request(f"http://127.0.0.1:{self.port}{self.path}/inference",
                                     b"".join(parts) + f"--{bd}--\r\n".encode(),
                                     {"Content-Type": f"multipart/form-data; boundary={bd}"})
        r = json.load(urllib.request.urlopen(req, timeout=timeout))
        if "error" in r:
            raise RuntimeError(str(r["error"])[:120])
        raw = r.get("segments") or []
        if any(s.get("no_speech_prob") is None or s.get("avg_logprob") is None for s in raw):
            raise NoConfidence("whisper-server returned a segment without no_speech_prob / avg_logprob")
        return join_split_words(raw)

    def peak_rss_mb(self) -> Optional[float]:
        """The child's resident high-water mark (Linux), for the harness and the budget."""
        try:
            for line in open(f"/proc/{self.proc.pid}/status"):
                if line.startswith("VmHWM"):
                    return round(int(line.split()[1]) / 1024, 1)
        except Exception:
            return None
        return None

    def stop(self) -> None:
        if self.proc is not None and self.proc.poll() is None:
            self.proc.terminate()
            try:
                self.proc.wait(timeout=5)
            except Exception:
                self.proc.kill()
        self.proc = None
