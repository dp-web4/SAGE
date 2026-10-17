#!/usr/bin/env python3
"""ASR equivalence harness — the first step of every track in the compiled-transducers arc.

explorations/2026-10-06-compiled-transducers-sensors-effectors.md (#373) asks, before any
optimization, for "an equivalence harness" that measures a candidate recognizer at SAGE's own
boundary: what the being would have been told it heard, not a benchmark score. This is that
harness, hardware-neutral, so Sprout (Orin), Thor (Blackwell) and McNugget (Apple Silicon) run
the same measurement on the same corpus.

WHAT IT MEASURES, per utterance and candidate:
  * end-to-end latency: audio in -> kept words out, with SAGE's keep/drop judgement included,
    and the model-only part of that;
  * the kept words, through `listening.judge_segments` -- the REAL guard the ear uses, imported,
    never copied -- so "kept/dropped segment behaviour at the SAGE boundary" is the same code;
  * word errors against the reference text, and on near-silence or noise-only clips (no reference
    words), whether anything was kept: a hallucination the being would have believed.
Aggregated per candidate: load time, p50/p95 latency, real-time factor, WER by category, the
near-silence hallucination rate, peak resident memory, and every utterance where the kept words
differ from the reference candidate's -- the disagreements that would change a beat.

THE GUARD IS PART OF THE CONTRACT. `judge_segments` drops a segment on Whisper's own confidences
(no_speech_prob, avg_logprob); that is what stops Whisper's stock phrases on near-silence from
reaching the being. A candidate that produces no such confidences cannot be judged by it, so it
is recorded `unguarded` and its words go through as they are. That is a contract finding in its
own right (the arc's Track A failure clause: "damages uncertainty handling"), never hidden by
quietly treating the missing confidences as 0.

One candidate per process (`run`), so peak memory belongs to that candidate alone; `summarize`
reads every candidate's rows from the output directory.

  python -m sage.embodiment.asr_harness build-sample-corpus --out DIR
  python -m sage.embodiment.asr_harness run --manifest DIR/manifest.jsonl --candidate whisper_ref --out RUN
  python -m sage.embodiment.asr_harness summarize --out RUN [--reference whisper_ref]

The manifest is JSONL: {"id", "wav" (16 kHz mono, path relative to the manifest), "text"
(reference; "" when there are no words), "category"}. Any corpus in that shape works unchanged,
including a body's real recordings.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import statistics
import sys
import time
from pathlib import Path
from typing import Callable, Dict, List, Optional

RATE = 16000
NO_WORDS = ("near_silence", "noise_only")   # categories whose reference is "no words"


# ---------------------------------------------------------------------------------------------
# text and errors

# Spoken forms a reference writes out and a recognizer abbreviates (LibriSpeech: MISTER; Whisper: Mr.).
_SPOKEN = {"mr": "mister", "mrs": "missus", "dr": "doctor"}


def normalize(text: str) -> List[str]:
    """Words for comparison: lower case, letters/digits/apostrophes only, common titles spelled out."""
    t = re.sub(r"[^a-z0-9' ]+", " ", str(text or "").lower().replace("-", " "))
    words = [w.strip("'") for w in t.split() if w.strip("'")]
    return [_SPOKEN.get(w, w) for w in words]


def word_edits(ref: str, hyp: str) -> int:
    """Word-level Levenshtein distance (substitutions + deletions + insertions)."""
    r, h = normalize(ref), normalize(hyp)
    prev = list(range(len(h) + 1))
    for i, rw in enumerate(r, 1):
        cur = [i] + [0] * len(h)
        for j, hw in enumerate(h, 1):
            cur[j] = min(prev[j] + 1, cur[j - 1] + 1, prev[j - 1] + (rw != hw))
        prev = cur
    return prev[-1]


# ---------------------------------------------------------------------------------------------
# candidates: name -> object with .name, .guarded, .load(), .segments(audio, wav_path)

class Candidate:
    name = "?"
    guarded = True          # its segments carry no_speech_prob / avg_logprob for the ear's guard

    def load(self) -> None:
        raise NotImplementedError

    def segments(self, audio, wav_path: str) -> List[dict]:
        raise NotImplementedError


class WhisperRef(Candidate):
    """The reference: openai-whisper, called exactly as listening.Transcriber calls it."""
    name, model_name = "whisper_ref", "base.en"

    def load(self):
        import torch
        import whisper
        dev = "cuda" if torch.cuda.is_available() else "cpu"
        self.model, self.fp16 = whisper.load_model(self.model_name, device=dev), dev == "cuda"

    def segments(self, audio, wav_path):
        r = self.model.transcribe(audio, fp16=self.fp16, language="en", condition_on_previous_text=False)
        return r.get("segments") or []


class MlxWhisper(Candidate):
    """The same model compiled for Apple Silicon (MLX): the arc's 'lean equivalent + target
    compile' step without changing the model."""
    name, repo = "mlx_whisper", "mlx-community/whisper-base.en-mlx"

    def load(self):
        import mlx_whisper
        self.mod = mlx_whisper
        import numpy as np
        self.mod.transcribe(np.zeros(RATE, dtype=np.float32), path_or_hf_repo=self.repo)  # fetch + compile

    def segments(self, audio, wav_path):
        r = self.mod.transcribe(audio, path_or_hf_repo=self.repo, language="en",
                                condition_on_previous_text=False)
        return r.get("segments") or []


class ParakeetMlx(Candidate):
    """A different model (FastConformer/Parakeet TDT) on MLX. No per-segment silence/confidence
    signal of Whisper's kind, so the ear's guard cannot judge it: unguarded."""
    name, repo, guarded = "parakeet_mlx", "mlx-community/parakeet-tdt-0.6b-v2", False

    def load(self):
        import mlx.core as mx
        from parakeet_mlx import from_pretrained
        from parakeet_mlx.audio import get_logmel
        self.model, self.mx, self.logmel = from_pretrained(self.repo), mx, get_logmel

    def segments(self, audio, wav_path):
        # The array the ear already holds, not the file: transcribe(path) decodes through FFmpeg,
        # which the ear never needs. Same steps as parakeet_mlx's own transcribe for one chunk.
        mel = self.logmel(self.mx.array(audio, dtype=self.mx.float32), self.model.preprocessor_config)
        r = self.model.generate(mel)[0]
        return [{"text": str(getattr(r, "text", "") or "")}]


class WhisperCpp(Candidate):
    """The same Whisper models through whisper.cpp on the CPU (sage/embodiment/whispercpp.py): no torch, no
    GPU memory. Its server reports Whisper's own no_speech_prob / avg_logprob, so it is guarded. The
    server is a child process, so its memory is reported from the child (`extra_meta`), not this process."""
    name, model_name, full_ctx = "whispercpp_base", "base.en", True

    def load(self):
        from sage.embodiment.whispercpp import WhisperCpp as Server
        self.server = Server(self.model_name, full_ctx=self.full_ctx)
        self.server.start()

    def segments(self, audio, wav_path):
        import numpy as np
        return self.server.segments((np.clip(audio, -1, 1) * 32767).astype("<i2").tobytes())

    def extra_meta(self) -> dict:
        m = {"server_peak_rss_mb": self.server.peak_rss_mb(), "model": self.model_name,
             "audio_ctx": "full" if self.full_ctx else "fitted"}
        self.server.stop()
        return m


class WhisperCppTiny(WhisperCpp):
    name, model_name = "whispercpp_tiny", "tiny.en"


class WhisperCppBaseFit(WhisperCpp):
    """audio_ctx fitted to the clip: 3-4x faster, and measured to invent words on silence (whispercpp.py)."""
    name, full_ctx = "whispercpp_base_fitctx", False


class WhisperCppTinyFit(WhisperCppTiny):
    name, full_ctx = "whispercpp_tiny_fitctx", False


class WhisperKitAne(Candidate):
    """Whisper base.en compiled with Core ML and run on the Apple Neural Engine (WhisperKit, Argmax),
    the third compute rail on Apple Silicon: the CPU (whisper_ref) and GPU (mlx_whisper) rails ran
    with the ANE at 0 J (McNugget, 2026-10-11). Called through `whisperkit-cli serve` (encoder and
    decoder default to cpuAndNeuralEngine), OpenAI-compatible verbose_json, whose segments carry
    Whisper's own avg_logprob / no_speech_prob: guarded, judged by the ear's guard like the
    reference. The server is started outside the harness (it compiles the model on first load);
    its URL is $SAGE_WHISPERKIT_URL, default http://127.0.0.1:50060."""
    name, model_name = "whisperkit_ane", "base.en"

    def load(self):
        import os
        self.url = os.environ.get("SAGE_WHISPERKIT_URL", "http://127.0.0.1:50060").rstrip("/")
        import numpy as np
        self.segments(np.zeros(RATE, dtype=np.float32), "")      # fails here, not mid-run, if it is down

    def segments(self, audio, wav_path):
        import io
        import uuid
        import urllib.request
        import wave
        import numpy as np
        buf = io.BytesIO()
        with wave.open(buf, "wb") as w:
            w.setnchannels(1); w.setsampwidth(2); w.setframerate(RATE)
            w.writeframes((np.clip(audio, -1, 1) * 32767).astype("<i2").tobytes())
        b = uuid.uuid4().hex
        fields = {"model": self.model_name, "language": "en", "temperature": "0",
                  "response_format": "verbose_json"}
        body = b"".join(f'--{b}\r\nContent-Disposition: form-data; name="{k}"\r\n\r\n{v}\r\n'.encode()
                        for k, v in fields.items())
        body += (f'--{b}\r\nContent-Disposition: form-data; name="file"; filename="clip.wav"\r\n'
                 f"Content-Type: audio/wav\r\n\r\n").encode() + buf.getvalue() + f"\r\n--{b}--\r\n".encode()
        req = urllib.request.Request(self.url + "/v1/audio/transcriptions", data=body,
                                     headers={"Content-Type": f"multipart/form-data; boundary={b}"})
        with urllib.request.urlopen(req, timeout=120) as r:
            out = json.loads(r.read())
        segs = out.get("segments") or []
        # WHAT THE GUARD CAN USE IS MEASURED, NOT ASSUMED (McNugget, 2026-10-14): WhisperKit returns
        # no_speech_prob as 0 on near-silence, where the reference reports it high, so the ear's
        # silence test cannot fire and only its logprob test remains. A field that is always 0 would
        # read as "guarded" while guarding nothing; extra_meta says how often it was informative.
        self.seen = getattr(self, "seen", 0) + len(segs)
        self.ns_nonzero = getattr(self, "ns_nonzero", 0) + sum(1 for s in segs if s.get("no_speech_prob"))
        return [{"text": s.get("text", ""), "no_speech_prob": s.get("no_speech_prob", 0.0),
                 "avg_logprob": s.get("avg_logprob", 0.0)} for s in segs]

    def extra_meta(self) -> dict:
        return {"model": self.model_name, "compute_units": "cpuAndNeuralEngine (encoder and decoder)",
                "server": "whisperkit-cli serve (separate process; its memory is not in peak_rss_mb)",
                "segments_seen": getattr(self, "seen", 0),
                "no_speech_prob_nonzero": getattr(self, "ns_nonzero", 0)}


class GemmaNativeAudio(Candidate):
    """The being's OWN model hearing raw audio: gemma4 lists native audio, and Ollama takes the WAV in
    `images` (its `audio` field does not reach the model; measured on McNugget 2026-10-14). The
    question is whether a being can hear in its own model instead of reading a transcript. It
    returns no per-segment confidences, so the ear's guard cannot judge it: UNGUARDED, and its
    behaviour on silence is exactly what this run measures. It shares the GPU with the being's beats;
    run it in a quiet window. Model: $SAGE_NATIVE_AUDIO_MODEL (default gemma4:12b)."""
    name, guarded = "gemma_native_audio", False
    PROMPT = ("Transcribe exactly the words spoken in this audio. Output only those words, with no "
              "commentary, quotes or description. If no one speaks, output nothing at all.")

    def load(self):
        import os
        self.model = os.environ.get("SAGE_NATIVE_AUDIO_MODEL", "gemma4:12b")
        self.url = os.environ.get("SAGE_OLLAMA_URL", "http://127.0.0.1:11434").rstrip("/")

    def segments(self, audio, wav_path):
        import base64
        import urllib.request
        req = {"model": self.model, "prompt": self.PROMPT, "stream": False, "think": False,
               "keep_alive": "-1m", "images": [base64.b64encode(open(wav_path, "rb").read()).decode()],
               "options": {"temperature": 0, "num_predict": 200}}
        r = urllib.request.urlopen(urllib.request.Request(
            self.url + "/api/generate", data=json.dumps(req).encode(),
            headers={"Content-Type": "application/json"}), timeout=300)
        text = str(json.loads(r.read()).get("response") or "").strip()
        return [{"text": text}] if text else []

    def extra_meta(self) -> dict:
        return {"model": self.model, "via": "ollama /api/generate, WAV in images, temperature 0, think off"}


CANDIDATES: Dict[str, Callable[[], Candidate]] = {
    "whisper_ref": WhisperRef, "mlx_whisper": MlxWhisper, "parakeet_mlx": ParakeetMlx,
    "whispercpp_base": WhisperCpp, "whispercpp_tiny": WhisperCppTiny,
    "whispercpp_base_fitctx": WhisperCppBaseFit, "whispercpp_tiny_fitctx": WhisperCppTinyFit,
    "whisperkit_ane": WhisperKitAne, "gemma_native_audio": GemmaNativeAudio,
}


# ---------------------------------------------------------------------------------------------
# judging and running

def judge(candidate: Candidate, segs: List[dict], seconds: float) -> dict:
    """What the being would be told: the ear's own guard for a guarded candidate; the raw words,
    marked unguarded, for one that cannot be judged."""
    if candidate.guarded:
        from sage.embodiment.listening import judge_segments
        return judge_segments(segs, seconds=seconds, source=f"harness:{candidate.name}")
    text = " ".join(str(s.get("text", "")).strip() for s in segs).strip()
    return {"text": text, "seconds": seconds, "unguarded": True}


def load_manifest(path: str) -> List[dict]:
    base = Path(path).resolve().parent
    items = []
    for line in open(path):
        if line.strip():
            d = json.loads(line)
            d["wav"] = str((base / d["wav"]).resolve())
            items.append(d)
    return items


def read_wav(path: str):
    import numpy as np
    try:
        import soundfile as sf
        a, sr = sf.read(path, dtype="float32", always_2d=False)
    except ImportError:
        # 16-bit PCM (what build-sample-corpus writes) needs no soundfile: Sprout's ear venv has none.
        import wave
        with wave.open(path, "rb") as w:
            if w.getsampwidth() != 2:
                raise ValueError(f"{path}: {8 * w.getsampwidth()}-bit; without soundfile the harness reads 16-bit PCM")
            sr, ch = w.getframerate(), w.getnchannels()
            a = np.frombuffer(w.readframes(w.getnframes()), "<i2").astype(np.float32) / 32768.0
            a = a.reshape(-1, ch) if ch > 1 else a
    if getattr(a, "ndim", 1) > 1:
        a = a.mean(axis=1)
    if sr != RATE:
        raise ValueError(f"{path}: {sr} Hz; the harness takes {RATE} Hz mono (the ear's rate)")
    return np.ascontiguousarray(a, dtype=np.float32)


def run_one(candidate: Candidate, item: dict, audio) -> dict:
    seconds = round(len(audio) / RATE, 3)
    t0 = time.perf_counter()
    segs = candidate.segments(audio, item["wav"])
    t1 = time.perf_counter()
    rec = judge(candidate, segs, seconds)
    t2 = time.perf_counter()
    ref = str(item.get("text") or "")
    kept = str(rec.get("text") or "")
    return {
        "id": item["id"], "category": item.get("category", ""), "candidate": candidate.name,
        "audio_s": seconds, "model_s": round(t1 - t0, 4), "e2e_s": round(t2 - t0, 4),
        "ref": ref, "kept": kept, "raw": " ".join(str(s.get("text", "")).strip() for s in segs).strip(),
        "edits": word_edits(ref, kept), "ref_words": len(normalize(ref)),
        "dropped": len(rec.get("dropped") or []), "unguarded": bool(rec.get("unguarded")),
        "hallucination": (not normalize(ref)) and bool(normalize(kept)),
    }


def peak_rss_mb() -> float:
    import resource
    r = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    return round(r / (1024 * 1024) if sys.platform == "darwin" else r / 1024, 1)   # bytes on macOS, KiB on Linux


def run(manifest: str, name: str, out: str, warmup: int = 1) -> dict:
    items = load_manifest(manifest)
    cand = CANDIDATES[name]()
    t0 = time.perf_counter()
    cand.load()
    load_s = round(time.perf_counter() - t0, 3)
    audios = {it["id"]: read_wav(it["wav"]) for it in items}
    for it in items[:warmup]:                      # first-call costs belong to load, not to an utterance
        cand.segments(audios[it["id"]], it["wav"])
    rows = [run_one(cand, it, audios[it["id"]]) for it in items]
    Path(out).mkdir(parents=True, exist_ok=True)
    with open(Path(out) / f"rows_{name}.jsonl", "w") as f:
        for r in rows:
            f.write(json.dumps(r) + "\n")
    meta = {"candidate": name, "guarded": cand.guarded, "load_s": load_s, "peak_rss_mb": peak_rss_mb(),
            "n": len(rows), "host": os.uname().nodename, "machine": os.uname().machine,
            "ts": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())}
    meta.update(getattr(cand, "extra_meta", dict)())
    (Path(out) / f"meta_{name}.json").write_text(json.dumps(meta, indent=2) + "\n")
    return meta


# ---------------------------------------------------------------------------------------------
# summary

def _pct(xs: List[float], q: float) -> Optional[float]:
    if not xs:
        return None
    xs = sorted(xs)
    return round(xs[min(len(xs) - 1, int(round(q * (len(xs) - 1))))], 4)


def summarize_rows(rows: List[dict], metas: Dict[str, dict], reference: Optional[str] = None) -> dict:
    by: Dict[str, List[dict]] = {}
    for r in rows:
        # Errors are recomputed from the stored texts, so a normalizer change never needs a re-run.
        r = dict(r, edits=word_edits(r["ref"], r["kept"]), ref_words=len(normalize(r["ref"])),
                 hallucination=(not normalize(r["ref"])) and bool(normalize(r["kept"])))
        by.setdefault(r["candidate"], []).append(r)
    ref_kept = {r["id"]: normalize(r["kept"]) for r in by.get(reference or "", [])}
    out = {}
    for name, rs in sorted(by.items()):
        worded = [r for r in rs if r["ref_words"]]
        silent = [r for r in rs if not r["ref_words"]]
        cats = {}
        for c in sorted({r["category"] for r in worded}):
            cr = [r for r in worded if r["category"] == c]
            cats[c] = round(sum(r["edits"] for r in cr) / max(1, sum(r["ref_words"] for r in cr)), 4)
        audio = sum(r["audio_s"] for r in rs)
        dis = [r["id"] for r in rs if reference and name != reference and r["id"] in ref_kept
               and normalize(r["kept"]) != ref_kept[r["id"]]]
        m = metas.get(name, {})
        out[name] = {
            "n": len(rs), "guarded": m.get("guarded", not any(r["unguarded"] for r in rs)),
            "load_s": m.get("load_s"), "peak_rss_mb": m.get("peak_rss_mb"),
            "server_peak_rss_mb": m.get("server_peak_rss_mb"),
            "e2e_p50_s": _pct([r["e2e_s"] for r in rs], 0.5), "e2e_p95_s": _pct([r["e2e_s"] for r in rs], 0.95),
            "model_p50_s": _pct([r["model_s"] for r in rs], 0.5),
            "rtf": round(sum(r["e2e_s"] for r in rs) / audio, 4) if audio else None,
            "wer": round(sum(r["edits"] for r in worded) / max(1, sum(r["ref_words"] for r in worded)), 4),
            "wer_by_category": cats,
            "silent_clips": len(silent),
            "hallucinations": sum(r["hallucination"] for r in silent),
            "segments_dropped": sum(r["dropped"] for r in rs),
            "disagrees_with_reference": len(dis), "disagreement_ids": dis[:50],
        }
    return out


def summarize(out: str, reference: Optional[str] = "whisper_ref") -> dict:
    rows, metas = [], {}
    for f in sorted(Path(out).glob("rows_*.jsonl")):
        rows += [json.loads(l) for l in open(f) if l.strip()]
    for f in sorted(Path(out).glob("meta_*.json")):
        m = json.loads(f.read_text())
        metas[m["candidate"]] = m
    s = summarize_rows(rows, metas, reference if reference in metas else None)
    (Path(out) / "summary.json").write_text(json.dumps(s, indent=2) + "\n")
    return s


def table(s: dict) -> str:
    cols = ["guarded", "load_s", "peak_rss_mb", "server_peak_rss_mb", "e2e_p50_s", "e2e_p95_s", "rtf", "wer",
            "hallucinations", "silent_clips", "segments_dropped", "disagrees_with_reference"]
    lines = ["| candidate | " + " | ".join(cols) + " |", "|---" * (len(cols) + 1) + "|"]
    for name, v in s.items():
        lines.append(f"| {name} | " + " | ".join(str(v.get(c)) for c in cols) + " |")
    return "\n".join(lines)


# ---------------------------------------------------------------------------------------------
# a small public corpus, for building and checking the harness (a body's real recordings are the
# corpus the arc means; they go in the same manifest shape)

SAMPLE_REPO = "hf-internal-testing/librispeech_asr_dummy"
SAMPLE_FILE = "clean/validation-00000-of-00001.parquet"


def build_sample_corpus(out: str, seed: int = 7) -> int:
    """LibriSpeech dummy (73 clean read utterances), plus derived categories the ear meets:
    quiet (-24 dB), clipped_start (first 150 ms cut), noisy (white noise at 5 dB SNR), and
    generated near_silence / noise_only clips whose reference is no words."""
    import io

    import numpy as np
    import pyarrow.parquet as pq
    import soundfile as sf
    from huggingface_hub import hf_hub_download

    rng = np.random.default_rng(seed)
    o = Path(out)
    (o / "wav").mkdir(parents=True, exist_ok=True)
    t = pq.read_table(hf_hub_download(SAMPLE_REPO, SAMPLE_FILE, repo_type="dataset")).to_pylist()
    rows = []

    def put(id_, a, text, cat):
        sf.write(o / "wav" / f"{id_}.wav", np.clip(a, -1, 1).astype(np.float32), RATE, subtype="PCM_16")
        rows.append({"id": id_, "wav": f"wav/{id_}.wav", "text": text, "category": cat})

    for r in t:
        a, sr = sf.read(io.BytesIO(r["audio"]["bytes"]), dtype="float32")
        if sr != RATE:
            raise ValueError(f"sample at {sr} Hz")
        base, text = str(r["id"]), str(r["text"])
        put(f"{base}", a, text, "clean")
        put(f"{base}-quiet", a * 10 ** (-24 / 20), text, "quiet")
        put(f"{base}-clip", a[int(0.15 * RATE):], text, "clipped_start")
        noise = rng.standard_normal(len(a)).astype(np.float32)
        noise *= np.sqrt(np.mean(a ** 2) / (10 ** (5 / 10)) / np.mean(noise ** 2))
        put(f"{base}-noisy", a + noise, text, "noisy")
    for i in range(20):
        n = rng.standard_normal(int(2.0 * RATE)).astype(np.float32)
        put(f"near-silence-{i:02d}", n * 10 ** (-60 / 20), "", "near_silence")
        put(f"noise-only-{i:02d}", n * 10 ** (-30 / 20), "", "noise_only")
    with open(o / "manifest.jsonl", "w") as f:
        for r in rows:
            f.write(json.dumps(r) + "\n")
    return len(rows)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="python -m sage.embodiment.asr_harness")
    sub = ap.add_subparsers(dest="cmd", required=True)
    b = sub.add_parser("build-sample-corpus"); b.add_argument("--out", required=True)
    r = sub.add_parser("run"); r.add_argument("--manifest", required=True)
    r.add_argument("--candidate", required=True, choices=sorted(CANDIDATES)); r.add_argument("--out", required=True)
    r.add_argument("--warmup", type=int, default=1)
    s = sub.add_parser("summarize"); s.add_argument("--out", required=True); s.add_argument("--reference", default="whisper_ref")
    a = ap.parse_args(argv)
    if a.cmd == "build-sample-corpus":
        print(f"{build_sample_corpus(a.out)} clips -> {a.out}/manifest.jsonl")
    elif a.cmd == "run":
        print(json.dumps(run(a.manifest, a.candidate, a.out, a.warmup)))
    else:
        print(table(summarize(a.out, a.reference)))
    return 0


if __name__ == "__main__":
    sys.exit(main())
