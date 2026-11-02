"""The ASR equivalence harness measures at SAGE's boundary, with the ear's own guard.

explorations/2026-10-06-compiled-transducers-sensors-effectors.md (#373): every track starts with
an equivalence harness. These tests pin what makes its numbers mean what they say, without any
model: fake candidates stand in for recognizers.

  * the guard is the ear's REAL `listening.judge_segments`, so a near-silence segment Whisper
    marks as probably silence is dropped here exactly as the ear drops it;
  * a candidate with no confidences is UNGUARDED, and says so; its words are not silently judged
    as if its confidences were zero;
  * near-silence words count as a hallucination, WER is word-level, disagreements are against
    the reference candidate's KEPT words.

Plain asserts, so a failure fails under pytest as well as the script runner.
Run: python3 sage/embodiment/tests/test_asr_harness.py   (or pytest)
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))
from sage.embodiment import asr_harness as h  # noqa: E402
from sage.embodiment import listening  # noqa: E402


class Fake(h.Candidate):
    def __init__(self, name, segs, guarded=True):
        self.name, self._segs, self.guarded = name, segs, guarded

    def load(self):
        pass

    def segments(self, audio, wav_path):
        return self._segs


def _row(cand, ref="", category="clean", seconds=1.0):
    audio = [0.0] * int(seconds * h.RATE)
    return h.run_one(cand, {"id": "u1", "wav": "/dev/null", "text": ref, "category": category}, audio)


def test_word_edits_is_word_level_and_ignores_case_and_punctuation():
    assert h.word_edits("Mister Quilter is here.", "mister quilter is here") == 0
    assert h.word_edits("the cat sat", "the cat sat down") == 1
    assert h.word_edits("the cat sat", "a cat") == 2
    assert h.word_edits("", "") == 0
    assert h.word_edits("MISTER QUILTER", "Mr. Quilter") == 0, "a title the recognizer abbreviates is not an error"


def test_the_guard_is_the_ears_own_and_drops_what_the_ear_drops():
    silent = {"text": "Thank you.", "no_speech_prob": 0.9, "avg_logprob": -0.2}
    r = _row(Fake("g", [silent]), category="near_silence")
    assert r["kept"] == "" and r["dropped"] == 1 and not r["hallucination"], r
    expected = listening.judge_segments([silent], seconds=1.0)
    assert expected["text"] == r["kept"], "the harness must judge exactly as listening.judge_segments does"


def test_kept_words_on_near_silence_are_a_hallucination():
    sure = {"text": "Thank you.", "no_speech_prob": 0.1, "avg_logprob": -0.2}
    r = _row(Fake("g", [sure]), category="near_silence")
    assert r["kept"] == "Thank you." and r["hallucination"] is True, r


def test_a_candidate_without_confidences_is_unguarded_and_says_so():
    r = _row(Fake("u", [{"text": "Thank you."}], guarded=False), category="near_silence")
    assert r["unguarded"] is True and r["kept"] == "Thank you." and r["hallucination"] is True, r
    g = _row(Fake("g", [{"text": "hello", "no_speech_prob": 0.0, "avg_logprob": -0.1}]), ref="hello")
    assert g["unguarded"] is False and g["edits"] == 0, g


def test_the_summary_reports_wer_hallucinations_and_disagreements_against_the_reference():
    rows = [
        {"id": "a", "category": "clean", "candidate": "ref", "audio_s": 2.0, "model_s": 0.2, "e2e_s": 0.21,
         "ref": "hello world", "kept": "hello world", "raw": "", "edits": 0, "ref_words": 2,
         "dropped": 0, "unguarded": False, "hallucination": False},
        {"id": "s", "category": "near_silence", "candidate": "ref", "audio_s": 2.0, "model_s": 0.1, "e2e_s": 0.11,
         "ref": "", "kept": "", "raw": "", "edits": 0, "ref_words": 0, "dropped": 1, "unguarded": False,
         "hallucination": False},
        {"id": "a", "category": "clean", "candidate": "fast", "audio_s": 2.0, "model_s": 0.05, "e2e_s": 0.05,
         "ref": "hello world", "kept": "hello word", "raw": "", "edits": 1, "ref_words": 2,
         "dropped": 0, "unguarded": True, "hallucination": False},
        {"id": "s", "category": "near_silence", "candidate": "fast", "audio_s": 2.0, "model_s": 0.05,
         "e2e_s": 0.05, "ref": "", "kept": "thank you", "raw": "", "edits": 2, "ref_words": 0, "dropped": 0,
         "unguarded": True, "hallucination": True},
    ]
    s = h.summarize_rows(rows, {"ref": {"guarded": True}, "fast": {"guarded": False}}, reference="ref")
    assert s["ref"]["wer"] == 0.0 and s["ref"]["hallucinations"] == 0 and s["ref"]["segments_dropped"] == 1
    assert s["fast"]["wer"] == 0.5 and s["fast"]["wer_by_category"] == {"clean": 0.5}
    assert s["fast"]["hallucinations"] == 1 and s["fast"]["silent_clips"] == 1
    assert s["fast"]["guarded"] is False
    assert s["fast"]["disagrees_with_reference"] == 2 and s["fast"]["disagreement_ids"] == ["a", "s"]
    assert s["ref"]["disagrees_with_reference"] == 0


def test_every_candidate_is_registered_with_its_guard_status():
    assert set(h.CANDIDATES) >= {"whisper_ref", "mlx_whisper", "parakeet_mlx"}
    assert h.CANDIDATES["whisper_ref"].guarded and h.CANDIDATES["mlx_whisper"].guarded
    assert h.CANDIDATES["parakeet_mlx"].guarded is False


def test_the_ane_candidate_maps_verbose_json_and_counts_an_uninformative_no_speech_prob():
    """WhisperKit (Core ML, Apple Neural Engine) answers OpenAI verbose_json. Its segments carry
    avg_logprob and no_speech_prob, so it is judged by the ear's guard -- but measured on McNugget
    its no_speech_prob is 0 on near-silence, which disables the guard's silence test. The candidate
    must pass the fields through as given and report how often no_speech_prob was nonzero."""
    import http.server
    import json as _j
    import threading
    replies = [{"segments": [{"text": " You", "avg_logprob": -0.77, "no_speech_prob": 0}]},
               {"segments": [{"text": " Hello there.", "avg_logprob": -0.2, "no_speech_prob": 0.01}]}]

    class H(http.server.BaseHTTPRequestHandler):
        def do_POST(self):
            self.rfile.read(int(self.headers.get("Content-Length", 0)))
            body = _j.dumps(replies.pop(0) if replies else {"segments": []}).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, *a):
            pass

    srv = http.server.HTTPServer(("127.0.0.1", 0), H)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    try:
        c = h.WhisperKitAne()
        c.url = f"http://127.0.0.1:{srv.server_address[1]}"
        c.scoring = True            # as run() sets it around the scored rows; setup is counted apart
        audio = [0.0] * h.RATE
        segs = c.segments(audio, "")
        assert segs == [{"text": " You", "no_speech_prob": 0, "avg_logprob": -0.77}], segs
        c.segments(audio, "")
        meta = c.extra_meta()
        assert meta["segments_seen"] == 2 and meta["no_speech_prob_nonzero"] == 1, meta
        assert h.CANDIDATES["whisperkit_ane"].guarded is True
    finally:
        srv.shutdown()


def test_run_scores_only_the_rows_and_reports_setup_apart(tmp_path=None):
    """NOVA on #446: load()'s preflight (1 s of zeros) and run()'s warmup both called segments(), and those
    calls landed in segments_seen / no_speech_prob_nonzero, so the scored totals described more than the
    rows. End to end through run(): 3 manifest items, warmup=1, a fake WhisperKit that answers every request
    with one segment whose no_speech_prob is nonzero. Scored totals must equal the 3 rows exactly; the
    preflight and the 1 warmup clip are the setup bucket; the meta says the candidate is experimental."""
    import http.server
    import json as _j
    import tempfile
    import threading
    import wave
    calls = []

    class H(http.server.BaseHTTPRequestHandler):
        def do_POST(self):
            self.rfile.read(int(self.headers.get("Content-Length", 0)))
            calls.append(1)
            body = _j.dumps({"segments": [{"text": " hi", "avg_logprob": -0.1, "no_speech_prob": 0.5}]}).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, *a):
            pass

    srv = http.server.HTTPServer(("127.0.0.1", 0), H)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    d = Path(tmp_path or tempfile.mkdtemp())
    lines = []
    for i in range(3):
        with wave.open(str(d / f"c{i}.wav"), "wb") as w:
            w.setnchannels(1); w.setsampwidth(2); w.setframerate(h.RATE)
            w.writeframes(b"\x00\x00" * h.RATE)
        lines.append(_j.dumps({"id": f"c{i}", "wav": f"c{i}.wav", "text": "hi", "category": "clean"}))
    (d / "manifest.jsonl").write_text("\n".join(lines) + "\n")
    import os
    old = os.environ.get("SAGE_WHISPERKIT_URL")
    os.environ["SAGE_WHISPERKIT_URL"] = f"http://127.0.0.1:{srv.server_address[1]}"
    try:
        meta = h.run(str(d / "manifest.jsonl"), "whisperkit_ane", str(d / "out"), warmup=1)
    finally:
        srv.shutdown()
        if old is None:
            os.environ.pop("SAGE_WHISPERKIT_URL", None)
        else:
            os.environ["SAGE_WHISPERKIT_URL"] = old
    assert len(calls) == 5, "preflight 1 + warmup 1 + scored 3"
    assert meta["n"] == 3
    assert meta["segments_seen"] == 3 and meta["no_speech_prob_nonzero"] == 3, meta
    assert meta["setup_segments_seen"] == 2 and meta["setup_no_speech_prob_nonzero"] == 2, meta
    assert "Not for the live ear" in meta["experimental"]


def test_research_candidates_say_so_and_the_rest_do_not():
    assert h.CANDIDATES["whisperkit_ane"].experimental and h.CANDIDATES["gemma_native_audio"].experimental
    assert not h.CANDIDATES["whisper_ref"].experimental and not h.CANDIDATES["whispercpp_base"].experimental


def test_the_native_audio_candidate_is_unguarded_and_keeps_what_the_model_said(tmp_path=None):
    """The being's own model hearing raw audio (gemma4 via Ollama): no confidences, so UNGUARDED,
    and its reply is kept as said -- including a refusal sentence on silence, which the harness must
    then count as words kept on a no-word clip rather than quietly treat as silence."""
    import http.server
    import json as _j
    import tempfile
    import threading
    replies = ["Mr. Quilter is the apostle.", "", "I cannot fulfill this request."]

    class H(http.server.BaseHTTPRequestHandler):
        def do_POST(self):
            req = _j.loads(self.rfile.read(int(self.headers.get("Content-Length", 0))))
            assert req["images"] and req["options"]["temperature"] == 0 and req["think"] is False
            body = _j.dumps({"response": replies.pop(0)}).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, *a):
            pass

    srv = http.server.HTTPServer(("127.0.0.1", 0), H)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    wav = Path(tempfile.mkdtemp()) / "c.wav"
    wav.write_bytes(b"RIFF....WAVE")
    try:
        c = h.GemmaNativeAudio()
        c.model, c.url = "gemma4:12b", f"http://127.0.0.1:{srv.server_address[1]}"
        assert c.segments(None, str(wav)) == [{"text": "Mr. Quilter is the apostle."}]
        assert c.segments(None, str(wav)) == []
        r = h.run_one(c, {"id": "s", "wav": str(wav), "text": "", "category": "near_silence"}, [0.0] * h.RATE)
        assert r["unguarded"] is True and r["hallucination"] is True, r
        assert h.CANDIDATES["gemma_native_audio"].guarded is False
    finally:
        srv.shutdown()


if __name__ == "__main__":
    fails = 0
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            try:
                fn()
            except AssertionError as e:
                fails += 1
                print(f"FAIL {name}: {e}")
    print(f"{'FAILED' if fails else 'ok'}: {fails} failure(s)")
    sys.exit(1 if fails else 0)
