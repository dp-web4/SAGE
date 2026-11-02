"""No test writes the machine's live ear (2026-10-09).

A full-suite run on Sprout built a real audio.Hearing(); its start-up mark() wrote mode "" into the LIVE
~/.sprout/listen.json, and the cortex, running with SAGE_LISTEN=wake, stopped listening for its name. The conftests
route every ear path to a temp body dir; this pins it."""
import os

from sage.embodiment import listening


def _live(name):
    return os.path.join(os.environ.get("SAGE_BODY_DIR") or os.path.expanduser("~/.sprout"), name)


def test_every_ear_path_is_a_temp_path_under_test():
    for attr, name in (("LISTEN_PATH", "listen.json"), ("HEARD_PATH", "heard.jsonl"), ("EAR_LOG", "ear.jsonl"),
                       ("UNHEARD_PATH", "unheard.jsonl"), ("CHIME_PATH", "chime.wav")):
        assert getattr(listening, attr) != _live(name), attr


def test_a_real_hearing_and_a_mark_leave_the_live_file_untouched():
    from sage.embodiment import audio
    live = _live("listen.json")
    before = open(live).read() if os.path.exists(live) else None
    audio.Hearing()
    listening.mark(mode="", speaking_until=0)
    after = open(live).read() if os.path.exists(live) else None
    assert after == before
