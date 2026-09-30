"""The FUEL line does not carry the daemon's internal ATP (SAGE #291).

Experience records are stamped with the daemon controller's `atp_percentage`, a free-running
oscillator; `reserves()` used to publish it as the being's fuel.
"""
import json
import time

from sage.embodiment import liveness_binding as L


def test_reserves_do_not_read_atp_off_experience_records(monkeypatch, tmp_path):
    rec = tmp_path / "experience_buffer_rs.jsonl"
    rec.write_text(json.dumps({"timestamp": time.time(), "atp_percentage": 17.0,
                               "prompt": "p", "response": "r"}) + "\n")
    monkeypatch.setattr(L, "EXPERIENCE_GLOB", str(tmp_path / "*.jsonl"))
    out = L.reserves()
    assert "ATP" not in out and "17%" not in out
