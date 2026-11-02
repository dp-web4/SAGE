"""A live trial labels what the being produces, beside its words (dp, 2026-10-03: "in trial messages you might want
to include a note that it's a test message"). The trial's "Add a turn to the conversation with dp: 'I'm sorry I was
late…'" reached dp looking like the being's own words; with instance.json "trial" set, it would have carried
{"trial": <name>}. Never in the words, never in the audio."""
import json
import os
import sys
from pathlib import Path

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "..")))
from sage.gateway import conversations as conv, governed_turn as gt  # noqa: E402
from sage.gateway.being_gate_client import BeingIntent  # noqa: E402
from sage.gateway.tests.test_hestia_dispatch import _ALLOW, _disp  # noqa: E402
from sage.gateway.tests.test_speak import _dispatcher  # noqa: E402


def _set(home, **cfg):
    (Path(home) / "instance.json").write_text(json.dumps(cfg))


def test_trial_name_reads_only_a_nonempty_string(tmp_path):
    for cfg, want in (({}, None), ({"trial": ""}, None), ({"trial": True}, None), ({"trial": " json-act "}, "json-act")):
        _set(tmp_path, **cfg)
        assert gt.trial_name(tmp_path) == want, cfg


def _say(text):
    d, root = _disp()
    home = Path(root)
    conv.create(home, "dp", title="dp", participants=["dp", "sprout-being"], writable_by=["dp", "sprout-being"])
    return d, home


def test_a_say_during_a_trial_carries_the_label_beside_its_words():
    d, home = _say("x")
    _set(home, trial="answer-then-act")
    r = d(BeingIntent("say", {"to": "dp", "text": "I looked, and here is what I saw."}), _ALLOW)
    assert r.ok, r.error
    turn = conv.recent(home, "dp", limit=1)[-1]
    assert turn["trial"] == "answer-then-act"
    assert turn["text"] == "I looked, and here is what I saw.", "the being's words are untouched"


def test_no_trial_no_label():
    d, home = _say("x")
    r = d(BeingIntent("say", {"to": "dp", "text": "hello"}), _ALLOW)
    assert r.ok and "trial" not in conv.recent(home, "dp", limit=1)[-1]


def test_speech_during_a_trial_is_labelled_in_the_record_not_the_audio(monkeypatch):
    played = []
    d, home, _ = _dispatcher(monkeypatch, played)
    _set(home, trial="answer-then-act")
    assert d._do_speak(BeingIntent("speak", {"text": "Hello, dp."})).ok
    row = json.loads(open(os.path.join(home, "spoken.jsonl")).read().splitlines()[-1])
    assert row["trial"] == "answer-then-act" and row["text"] == "Hello, dp."
    assert played == ["Hello, dp."], "nothing about the trial is spoken"


def test_the_beat_record_names_the_trial():
    src = (Path(__file__).resolve().parents[1] / "heartbeat.py").read_text()
    assert '"trial": _trial_name(instance),' in src
