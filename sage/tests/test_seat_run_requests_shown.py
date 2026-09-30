"""The seat's answer to a request_run must survive the being's per-turn window.

Measured 2026-09-28 (cbp-being seq 4211 -> 4214): a decline that pasted a whole run showed the
being "I did not run" and an old "timed out after 400s", and hid every line of the result in
the cut middle. The being then asked three times for a run whose output it had been sent."""
import importlib.util
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO))
spec = importlib.util.spec_from_file_location("seat_run_requests", REPO / "sage/scripts/seat_run_requests.py")
srr = importlib.util.module_from_spec(spec)
spec.loader.exec_module(srr)


def test_window_cap_is_the_heartbeat_constant():
    from sage.gateway.heartbeat import CONV_TURN_CHARS
    assert srr._window_cap() == CONV_TURN_CHARS


def test_short_text_is_shown_whole():
    shown, hidden = srr.as_shown("x" * 100, cap=1200)
    assert shown == "x" * 100 and hidden == ""


def test_long_text_hides_exactly_the_middle():
    text = "H" * 480 + "M" * 739 + "T" * 720  # the 4211 shape: 1939 chars at cap 1200
    shown, hidden = srr.as_shown(text, cap=1200)
    assert hidden == "M" * 739
    assert shown.startswith("H" * 480) and shown.endswith("T" * 720)
    assert "739 chars omitted" in shown


def test_run_paste_in_a_decline_is_hidden_from_the_being():
    # The 4211 shape: ~500 chars of context first, the run in the middle, ~800 chars of reading after.
    pre = ("Re 4208, 4209 and 4210, all for sha 0276cb3ecc19. The file on disk is unchanged. " * 8)[:500]
    epochs = "\n".join(f"Epoch {i}/100, Loss: 19{i}.0" for i in range(10, 101, 10))
    trace = 'Traceback (most recent call last):\n  File "f.py", line 87\nNameError: name x is not defined\nExit code 1.'
    post = ("That is identical to 4202 run 2. The stop is line 87 and lines 88 to 105 never run. " * 12)[:800]
    text = srr.decline_text("f.py", pre + "\n\n" + epochs + "\n" + trace + "\n\n" + post, [4210])
    shown, hidden = srr.as_shown(text, cap=1200)
    assert hidden, "a decline this long must be flagged"
    assert "Epoch 50/100" in hidden and "Epoch 50/100" not in shown
    assert "NameError" in hidden and "NameError" not in shown
    assert shown.startswith("[request_run] I did not run f.py.")


def test_a_decline_closes_on_the_standing_line_and_names_no_door_of_its_own():
    """The stock "run under different conditions" door: offered on 96 declines, written into
    cbp-being's todo as an open item seven times, used by 0 of 377 request_run calls. The way
    forward belongs to the reason, which knows why this file was declined."""
    reason = "sha dc129ac0a7a9 is the file 4538 ran. Ask again when the sha differs."
    text = srr.decline_text("scratch/f.py", reason, [4540, 4541])
    assert text.startswith("[request_run] I did not run scratch/f.py. " + reason)
    assert text.endswith("This is a decision, not a failure, and it is not about your standing.")
    after_reason = text.split(reason, 1)[1]
    assert "condition" not in after_reason and "ask again" not in after_reason.lower()
    assert srr.answers_line([4540, 4541]) in after_reason


def test_cmd_decline_refuses_a_cut_reason_and_posts_nothing(monkeypatch, tmp_path):
    posted = []
    monkeypatch.setattr(srr, "_say", lambda t: posted.append(t))
    monkeypatch.setattr(srr, "_instance", lambda: tmp_path)
    monkeypatch.setattr(srr, "_target", lambda inst, raw: (tmp_path / raw))
    monkeypatch.setattr(srr, "bind", lambda *a: [4210])
    monkeypatch.setattr(srr, "_conv_id", lambda: "cbp-claude")

    class A:
        path = "f.py"; seq = [4210]; cut_anyway = False
        reason = "long " * 400
    with pytest.raises(SystemExit) as e:
        srr.cmd_decline(A())
    assert "refusing" in str(e.value) and "would NOT see" in str(e.value)
    assert posted == []

    A.cut_anyway = True
    srr.cmd_decline(A())
    assert len(posted) == 1 and posted[0].startswith("[request_run] I did not run f.py.")

    posted.clear(); A.cut_anyway = False; A.reason = "The result is at seq 4211; the sha has not moved."
    srr.cmd_decline(A())
    assert len(posted) == 1
