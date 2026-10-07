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
