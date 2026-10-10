"""EGAI re-read trial plumbing (2026-10-10): the arm is assigned ABAB by beat index, recorded on
every beat, the pointer appears only on ON beats, and the being cannot tune its own arm."""
import inspect
import json

from sage.gateway import being_params as bp
from sage.gateway.heartbeat import egai_arm, ESTABLISHED_POINTER


def _home(tmp_path, mode):
    (tmp_path / "instance.json").write_text(json.dumps({"params": {"established_note": mode}}))
    return tmp_path


def test_alternate_is_abab_by_beat_index(tmp_path):
    h = _home(tmp_path, "alternate")
    log = h / "heartbeats.jsonl"
    arms = []
    for i in range(4):
        arms.append(egai_arm(h, log)["arm"])
        with open(log, "a") as f:
            f.write("{}\n")
    assert arms == ["on", "off", "on", "off"]


def test_off_and_on_and_default(tmp_path):
    assert egai_arm(_home(tmp_path, "on"), tmp_path / "x")["arm"] == "on"
    assert egai_arm(_home(tmp_path, "off"), tmp_path / "x")["arm"] == "off"
    (tmp_path / "instance.json").write_text("{}")
    assert egai_arm(tmp_path, tmp_path / "x") == {"mode": "off", "arm": "off"}


def test_the_being_cannot_tune_its_own_arm(tmp_path):
    ok, text = bp.tune(_home(tmp_path, "alternate"), "established_note", "on", "I want it")
    assert not ok and "seat" in text


def test_main_injects_the_pointer_only_on_an_on_beat_and_records_the_arm():
    from sage.gateway import heartbeat
    src = inspect.getsource(heartbeat.main)
    assert 'if _egai["arm"] == "on":' in src and "ESTABLISHED_POINTER.format" in src
    assert 'record["egai"] = _egai' in src
    assert "notes/established.md" in ESTABLISHED_POINTER
