"""retire_note on a file with an unanswered request_run says so in its receipt (#755).

cbp-being, 2026-11-17 08:03Z: edit a script, request_run it, remember it "runs successfully" (nothing had
run), retire_note the script. The seat's answer then named a path with nothing at it. The retire is not
refused; its receipt names the open request and where the same code still is."""
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

from sage.gateway import conversations as conv  # noqa: E402
from sage.gateway.being_gate_client import BeingIntent  # noqa: E402
from sage.gateway.tests.test_hestia_dispatch import _ALLOW, _disp  # noqa: E402
from sage.gateway.tests.test_peer_ask_provenance import _seat_conv  # noqa: E402

SEAT, BEING = "sprout-claude", "sprout-being"
REL = "notes/mechanism-training-numpy.py"


def _home(turns, monkeypatch):
    for k in ("SEAT_ID", "SAGE_SEAT_CONV", "SAGE_SEAT"):
        monkeypatch.delenv(k, raising=False)
    d, root = _disp()
    home = Path(root)
    (home / "notes").mkdir()
    (home / REL).write_text("def main():\n    return 1\n\nmain()\n")
    _seat_conv(home, SEAT, BEING)
    for who, text in turns:
        conv.append(home, SEAT, speaker=who, text=text, enforce_write=False)
    return d, home


def _retire(d, path=REL):
    return d(BeingIntent("retire_note", {"path": path, "reason": "done with it"}), _ALLOW)


def _seqs(home):
    return [t["seq"] for t in conv.recent(home, SEAT, limit=50)]


def test_an_unanswered_request_is_named_and_the_retired_copy_is_pointed_to(monkeypatch):
    d, home = _home([(BEING, f"[request_run] {REL}\nwhy: check the fix")], monkeypatch)
    seq = _seqs(home)[-1]
    env = _retire(d)
    assert env.ok, env
    r = env.result
    assert r.startswith(f"retired mechanism-training-numpy.py -> mechanism-training-numpy.retired-"), r
    assert f"request seq {seq}) and no answer has come yet, so no run of it has happened" in r, r
    assert f"The answer will name {REL}, where nothing is now." in r
    assert "notes/mechanism-training-numpy.retired-" in r and "request_run on that path runs it" in r
    assert not (home / REL).exists(), "the retire itself is not refused"


def test_an_answered_request_adds_nothing(monkeypatch):
    d, home = _home([(BEING, f"[request_run] {REL}"), (SEAT, f"[request_run] I ran {REL} (sha abc). exit 0")],
                    monkeypatch)
    env = _retire(d)
    assert env.ok and "no answer has come yet" not in env.result, env.result


def test_a_request_for_another_file_adds_nothing(monkeypatch):
    d, home = _home([(BEING, "[request_run] notes/other.py")], monkeypatch)
    env = _retire(d)
    assert env.ok and "no answer has come yet" not in env.result


def test_two_open_requests_are_both_named(monkeypatch):
    d, home = _home([(BEING, f"[request_run] {REL}"), (BEING, f"[request_run] ./{REL}")], monkeypatch)
    a, b = _seqs(home)[-2:]
    env = _retire(d)
    assert f"request seq {a}, {b})" in env.result and "those requests are" in env.result, env.result


def test_no_seat_conversation_adds_nothing_and_never_breaks_the_retire(monkeypatch):
    for k in ("SEAT_ID", "SAGE_SEAT_CONV", "SAGE_SEAT"):
        monkeypatch.delenv(k, raising=False)
    d, root = _disp()
    home = Path(root)
    (home / "notes").mkdir()
    (home / REL).write_text("x = 1\n")
    env = _retire(d)
    assert env.ok and env.result.startswith("retired ") and "request seq" not in env.result


def test_a_refused_retire_is_untouched(monkeypatch):
    d, home = _home([(BEING, "[request_run] top.py")], monkeypatch)
    (home / "top.py").write_text("x = 1\n")
    env = _retire(d, "top.py")
    assert not env.ok and "request seq" not in (env.error or "")
