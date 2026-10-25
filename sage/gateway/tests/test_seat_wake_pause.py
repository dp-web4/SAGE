"""A seat that jumps in pauses the mesh wakes; only it answers while the pause holds.

Policy, dp 2026-10-16: mesh wakes answer beings by default; a seat that wants to talk to the being
directly pauses them. Measured that day on sprout: an interactive seat ran request 995 (answer at
seq 996) while a mesh wake for the same seat, knowing nothing of it, ran the same file again (997)
and answered a byte-identical repeat the seat had left unanswered on purpose (998). Both spoke as
"sprout-claude". These pin the three parts of the fix: no wake while paused (and the run stays
owed), run/decline refuse a session without the holder's token, and one answerer at a time.
"""
import importlib.util
import json
from pathlib import Path

import pytest

from sage.gateway import conversations as conv

_SCRIPT = Path(__file__).resolve().parents[2] / "scripts" / "seat_run_requests.py"
_spec = importlib.util.spec_from_file_location("seat_run_requests_pause", _SCRIPT)
srr = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(srr)

BEING, SEAT = "sprout-being", "sprout-claude"


@pytest.fixture
def inst(tmp_path, monkeypatch):
    monkeypatch.setenv("SAGE_CONV_NOTIFY_DIR", str(tmp_path / "notify"))
    monkeypatch.setenv("SAGE_SEAT_CONV", SEAT)
    monkeypatch.delenv("SEAT_ID", raising=False)
    monkeypatch.delenv("SEAT_PAUSE_TOKEN", raising=False)
    d = tmp_path / "inst"
    (d / "scratch").mkdir(parents=True)
    (d / "scratch" / "x.py").write_text("print('x')\n")
    conv.create(d, SEAT, title="seat", participants=[BEING, SEAT], writable_by=[BEING, SEAT], summary="")
    monkeypatch.setenv("SAGE_INSTANCE", str(d))
    return d


def ask(inst, path="scratch/x.py"):
    return conv.append(inst, SEAT, speaker=BEING, text=f"[request_run] {path}\nwhy: check")["seq"]


# -- the pause record -----------------------------------------------------------------------

def test_a_pause_holds_until_resumed(inst):
    assert conv.wake_pause(inst, SEAT) is None
    p = conv.pause_wakes(inst, SEAT, by=SEAT, minutes=30, reason="talking directly")
    held = conv.wake_pause(inst, SEAT)
    assert held and held["token"] == p["token"] and held["by"] == SEAT
    assert conv.resume_wakes(inst, SEAT, token=p["token"]) is True
    assert conv.wake_pause(inst, SEAT) is None
    assert conv.resume_wakes(inst, SEAT) is False


def test_a_pause_expires_on_its_own(inst):
    """A seat that leaves without resuming must not silence the being for long."""
    conv.pause_wakes(inst, SEAT, by=SEAT)
    path = conv.wake_pause_path(inst, SEAT)
    pause = json.loads(path.read_text())
    pause["until"] = "2000-01-01T00:00:00Z"
    path.write_text(json.dumps(pause))
    assert conv.wake_pause(inst, SEAT) is None


def test_an_unreadable_pause_is_no_pause(inst):
    """Doubt resolves toward waking: the worse failure is a being nobody answers."""
    path = conv.wake_pause_path(inst, SEAT)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("{not json")
    assert conv.wake_pause(inst, SEAT) is None


def test_renewing_takes_the_holders_token_and_keeps_it(inst):
    first = conv.pause_wakes(inst, SEAT, by=SEAT, minutes=5)
    again = conv.pause_wakes(inst, SEAT, by=SEAT, minutes=60, token=first["token"])
    assert again["token"] == first["token"] and again["since"] == first["since"]


def test_another_session_of_the_same_seat_cannot_take_or_end_the_pause(inst):
    """GPT on #461: ownership rode on the seat name, which every session for the seat shares,
    so any of them was handed the holder's token, and resume needed none."""
    held = conv.pause_wakes(inst, SEAT, by=SEAT)
    with pytest.raises(conv.PauseHeld):
        conv.pause_wakes(inst, SEAT, by=SEAT)                      # same seat, no token
    with pytest.raises(conv.PauseHeld):
        conv.pause_wakes(inst, SEAT, by=SEAT, token="not-it")
    with pytest.raises(conv.PauseHeld):
        conv.resume_wakes(inst, SEAT)
    assert conv.wake_pause(inst, SEAT)["token"] == held["token"], "the holder is unchanged"
    assert conv.resume_wakes(inst, SEAT, token=held["token"]) is True


def test_a_gone_holder_can_be_displaced_only_by_saying_why(inst):
    held = conv.pause_wakes(inst, SEAT, by=SEAT)
    taken = conv.pause_wakes(inst, SEAT, by=SEAT, take_over="holder session exited")
    assert taken["token"] != held["token"]
    assert taken["took_over"]["why"] == "holder session exited"
    assert conv.resume_wakes(inst, SEAT, force="cleanup after a crash") is True
    assert conv.wake_pause(inst, SEAT) is None


def test_resume_from_the_tool_needs_the_token(inst, monkeypatch):
    import argparse
    held = conv.pause_wakes(inst, SEAT, by=SEAT)
    with pytest.raises(SystemExit) as e:
        srr.cmd_resume(argparse.Namespace(force=None))
    assert "did not present its token" in str(e.value)
    monkeypatch.setenv("SEAT_PAUSE_TOKEN", held["token"])
    srr.cmd_resume(argparse.Namespace(force=None))
    assert conv.wake_pause(inst, SEAT) is None


# -- the being's say wakes nobody while paused ----------------------------------------------

def test_no_wake_while_paused_and_the_run_is_owed_after(inst, monkeypatch):
    from sage.gateway.tests.test_hestia_dispatch import FakeMcp, _ALLOW, _disp
    from sage.gateway.being_gate_client import BeingIntent
    d, root = _disp()
    home = Path(root)
    conv.create(home, "seat", title="seat", participants=["seat", "sprout-being"],
                writable_by=["seat", "sprout-being"])
    meta = conv.get_meta(home, "seat"); meta["notify"] = {"seat": "claude-code"}
    conv._write_meta(home, "seat", meta)
    held = conv.pause_wakes(home, "seat", by="seat")

    FakeMcp.calls.clear()
    r = d(BeingIntent("say", {"to": "seat", "text": "Please run scratch/x.py."}), _ALLOW)
    assert r.ok and "woke" not in r.result, "a paused conversation wakes nobody"
    assert not [a for n, a in FakeMcp.calls if n == "hestia_member_notify"]

    conv.resume_wakes(home, "seat", token=held["token"])
    FakeMcp.calls.clear()
    r = d(BeingIntent("say", {"to": "seat", "text": "Still waiting on scratch/x.py."}), _ALLOW)
    assert r.ok and r.result.get("woke") == "seat", "the run stayed owed through the pause"
    assert len([a for n, a in FakeMcp.calls if n == "hestia_member_notify"]) == 1


def test_the_owed_wake_follows_a_resume_without_a_new_turn(inst):
    """GPT on #461: `_wake_addressee` ran only on the being's own turn, so a being that asked
    once during the pause and then went quiet was owed a wake nobody sent. The beat's sweep
    sends it once the pause is gone, and never twice for one run."""
    from sage.gateway.tests.test_hestia_dispatch import FakeMcp, _ALLOW, _disp
    from sage.gateway.being_gate_client import BeingIntent
    d, root = _disp()
    home = Path(root)
    conv.create(home, "seat", title="seat", participants=["seat", "sprout-being"],
                writable_by=["seat", "sprout-being"])
    meta = conv.get_meta(home, "seat"); meta["notify"] = {"seat": "claude-code"}
    conv._write_meta(home, "seat", meta)
    held = conv.pause_wakes(home, "seat", by="seat")
    assert d(BeingIntent("say", {"to": "seat", "text": "Please run scratch/x.py."}), _ALLOW).ok

    notifies = lambda: [a for n, a in FakeMcp.calls if n == "hestia_member_notify"]  # noqa: E731
    FakeMcp.calls.clear()
    assert d.rearm_owed_wakes() == [] and not notifies(), "still paused: nothing is sent"

    conv.resume_wakes(home, "seat", token=held["token"])
    assert d.rearm_owed_wakes() == ["seat"], "the being said nothing new; the sweep sends the wake"
    assert len(notifies()) == 1
    FakeMcp.calls.clear()
    assert d.rearm_owed_wakes() == [] and not notifies(), "one wake per run, not one per beat"


def test_the_sweep_wakes_nobody_once_the_seat_has_answered(inst):
    from sage.gateway.tests.test_hestia_dispatch import FakeMcp, _ALLOW, _disp
    from sage.gateway.being_gate_client import BeingIntent
    d, root = _disp()
    home = Path(root)
    conv.create(home, "seat", title="seat", participants=["seat", "sprout-being"],
                writable_by=["seat", "sprout-being"])
    meta = conv.get_meta(home, "seat"); meta["notify"] = {"seat": "claude-code"}
    conv._write_meta(home, "seat", meta)
    held = conv.pause_wakes(home, "seat", by="seat")
    d(BeingIntent("say", {"to": "seat", "text": "Please run scratch/x.py."}), _ALLOW)
    conv.append(home, "seat", speaker="seat", text="Ran it; see above.", via="seat")
    conv.resume_wakes(home, "seat", token=held["token"])
    FakeMcp.calls.clear()
    assert d.rearm_owed_wakes() == []
    assert not [a for n, a in FakeMcp.calls if n == "hestia_member_notify"]


def test_a_paused_conversation_is_still_the_seat_conversation(inst):
    """Pausing must not be done by emptying `notify`: the dispatcher finds the seat
    conversation by its notify map, and request_run would find no seat at all."""
    meta = conv.get_meta(inst, SEAT); meta["notify"] = {SEAT: "claude-code"}
    conv._write_meta(inst, SEAT, meta)
    conv.pause_wakes(inst, SEAT, by=SEAT)
    assert conv.get_meta(inst, SEAT)["notify"] == {SEAT: "claude-code"}


# -- run and decline refuse anyone but the holder -------------------------------------------

def _decline_args(seq):
    import argparse
    return argparse.Namespace(path="scratch/x.py", reason="not now", seq=[seq], cut_anyway=False)


def test_decline_is_refused_to_a_session_without_the_token(inst, monkeypatch):
    s = ask(inst)
    conv.pause_wakes(inst, SEAT, by=SEAT, reason="talking directly")
    posted = []
    monkeypatch.setattr(srr, "_say", posted.append)
    with pytest.raises(SystemExit) as e:
        srr.cmd_decline(_decline_args(s))
    assert "paused wakes" in str(e.value) and "talking directly" in str(e.value)
    assert posted == [], "nothing is posted by a session that does not hold the pause"


def test_the_holder_answers_while_paused(inst, monkeypatch):
    s = ask(inst)
    p = conv.pause_wakes(inst, SEAT, by=SEAT)
    monkeypatch.setenv("SEAT_PAUSE_TOKEN", p["token"])
    posted = []
    monkeypatch.setattr(srr, "_say", posted.append)
    srr.cmd_decline(_decline_args(s))
    assert len(posted) == 1 and f"seq {s}" in posted[0]


def test_unpaused_any_seat_session_answers(inst, monkeypatch):
    s = ask(inst)
    posted = []
    monkeypatch.setattr(srr, "_say", posted.append)
    srr.cmd_decline(_decline_args(s))
    assert len(posted) == 1


# -- one answerer at a time ------------------------------------------------------------------

def test_a_second_answerer_waits_then_refuses(inst, monkeypatch):
    import fcntl
    s = ask(inst)
    monkeypatch.setattr(srr, "LOCK_WAIT_S", 0.3)
    posted = []
    monkeypatch.setattr(srr, "_say", posted.append)
    lock = inst / "conversations" / f".{SEAT}.answering.lock"
    lock.parent.mkdir(parents=True, exist_ok=True)
    with open(lock, "a+") as fh:
        fcntl.flock(fh, fcntl.LOCK_EX)                  # another seat process is mid-answer
        with pytest.raises(SystemExit) as e:
            srr.cmd_decline(_decline_args(s))
    assert "another seat process" in str(e.value) and posted == []


def test_the_second_answerer_finds_the_request_already_answered(inst, monkeypatch):
    """The double-run of seq 996/997: binding happens inside the lock, so whoever goes second
    sees the first one's answer and has nothing pending to bind."""
    s = ask(inst)
    monkeypatch.setattr(srr, "_say",
                        lambda text: conv.append(inst, SEAT, speaker=SEAT, text=text))
    srr.cmd_decline(_decline_args(s))
    with pytest.raises(SystemExit) as e:
        srr.cmd_decline(_decline_args(s))
    assert "not a pending request" in str(e.value)


def _run_args(**kw):
    import argparse
    base = dict(path="scratch/x.py", seq=None, gpu=False, gpu_anyway=False, timeout=10,
                unrequested=False, script_args=[])
    base.update(kw)
    return argparse.Namespace(**base)


def test_two_runs_without_seq_execute_the_file_once(inst, monkeypatch):
    """GPT's reproducer on #461: the second `run` (no --seq) bound nothing because the first had
    answered, and ran the file anyway as an unrequested run: 996/997, serialized, not prevented."""
    ask(inst)
    executions = []
    monkeypatch.setattr(srr, "run_child", lambda *a, **k: (executions.append(1), (0, "x\n", "", False))[1])
    monkeypatch.setattr(srr, "_say", lambda text: conv.append(inst, SEAT, speaker=SEAT, text=text))
    srr.cmd_run(_run_args())
    with pytest.raises(SystemExit) as e:
        srr.cmd_run(_run_args())
    assert "no pending request" in str(e.value)
    assert executions == [1], "the file ran exactly once"


def test_an_unrequested_run_is_still_possible_by_saying_so(inst, monkeypatch):
    executions = []
    monkeypatch.setattr(srr, "run_child", lambda *a, **k: (executions.append(1), (0, "", "", False))[1])
    posted = []
    monkeypatch.setattr(srr, "_say", posted.append)
    srr.cmd_run(_run_args(unrequested=True))
    assert executions == [1] and "answers none of your requests" in posted[0]


def test_concurrent_runs_without_seq_execute_the_file_once(inst, tmp_path):
    """The same reproducer with two real processes started together. The script holds for a
    second so the second process is waiting on the lock while the first runs it."""
    import http.server
    import os
    import subprocess
    import sys
    import threading

    counter = tmp_path / "executions.txt"
    (inst / "scratch" / "x.py").write_text(
        "import time\n"
        f"open({str(counter)!r}, 'a').write('ran\\n')\n"
        "time.sleep(1.0)\n")
    ask(inst)

    class Daemon(http.server.BaseHTTPRequestHandler):
        def do_POST(self):                                # the daemon's /say, minus arousal
            cid = self.path.split("/")[2]
            body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
            turn = conv.append(inst, cid, speaker=body["from"], text=body["message"])
            out = json.dumps({"turn": {"seq": turn["seq"]}}).encode()
            self.send_response(200); self.send_header("Content-Length", str(len(out))); self.end_headers()
            self.wfile.write(out)

        def log_message(self, *a):
            pass

    srv = http.server.ThreadingHTTPServer(("127.0.0.1", 0), Daemon)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    env = dict(os.environ, SAGE_INSTANCE=str(inst), SAGE_SEAT_CONV=SEAT,
               SAGE_DAEMON=f"http://127.0.0.1:{srv.server_address[1]}")
    env.pop("SEAT_ID", None)
    cmd = [sys.executable, str(_SCRIPT), "run", "scratch/x.py", "--timeout", "20"]
    try:
        procs = [subprocess.Popen(cmd, env=env, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
                 for _ in range(2)]
        results = [p.communicate(timeout=60) for p in procs]
    finally:
        srv.shutdown()
    assert counter.read_text().count("ran") == 1, "one actual child execution"
    codes = sorted(p.returncode for p in procs)
    assert codes[0] == 0 and codes[1] != 0, results
    assert any("no pending request" in err for _, err in results), results


def test_a_pause_taken_while_waiting_for_the_lock_is_honoured(inst, monkeypatch):
    """GPT on #461: the pause was checked before the lock, so a session that checked "not
    paused" and then waited could act after a seat paused in the meantime."""
    import fcntl
    import threading
    s = ask(inst)
    posted, outcome = [], {}
    monkeypatch.setattr(srr, "_say", posted.append)
    lock = inst / "conversations" / f".{SEAT}.answering.lock"
    lock.parent.mkdir(parents=True, exist_ok=True)
    fh = open(lock, "a+")
    fcntl.flock(fh, fcntl.LOCK_EX)                       # someone is mid-answer

    def session_b():
        try:
            srr.cmd_decline(_decline_args(s))           # no token; at this moment, not paused
            outcome["done"] = True
        except SystemExit as e:
            outcome["exit"] = str(e)

    t = threading.Thread(target=session_b)
    t.start()
    import time
    time.sleep(0.5)                                      # B is waiting on the lock
    conv.pause_wakes(inst, SEAT, by=SEAT, reason="jumping in")
    fcntl.flock(fh, fcntl.LOCK_UN)
    fh.close()
    t.join(10)
    assert "exit" in outcome and "paused wakes" in outcome["exit"], outcome
    assert posted == []


# -- who the seat is -------------------------------------------------------------------------

def test_the_seat_id_follows_the_seat_conversation(inst):
    """With SEAT_ID unset the default was "cbp-claude" on every machine: on sprout, `pending`
    counted sprout-claude's own answers as requests."""
    assert srr._seat_id() == SEAT
    s = ask(inst)
    conv.append(inst, SEAT, speaker=SEAT, text="[request_run] I ran scratch/x.py (sha abc). exit code 0.\n\n"
                + srr.answers_line([s]))
    assert srr.pending(inst, SEAT) == []
