"""SAGE #557: a run's read-only mounts are judged as the reads they are, not with the run's re.

cbp-being, 2026-10-27 02:54Z, the first hour #547 was live there: every `run` was refused
"narrowed to r; this act needs re (missing e)" on shared-context/escalations, a society-floor
grant it holds r-only and the box binds --ro-bind. These rows compose the REAL line (_normalize,
run_command, run_grant_mounts, sandbox_reach); decide() is a fake that applies the gate's mode
rule: a path covered only by an r grant refuses an act that needs more than r."""
import os
from types import SimpleNamespace

from sage.gateway.being_gate_client import BeingIntent, sandbox_reach, sandbox_read_mounts
from sage.gateway.tests.test_being_gate_client import _line_bind_sources, _real_run_client

_NEEDS = {"run": "re", "read_file": "r"}


def _mode_gate(c, r_only=(), unreadable=()):
    """decide(): deny an act whose paths reach an r-only root unless the act needs only r; deny any
    act on an `unreadable` root. Records every event."""
    calls = []

    def decide(ev, prof):
        calls.append((ev.kw, prof.kw))
        need = _NEEDS.get(ev.kw["tool"], "rwed")
        for p in ev.kw["tool_input"].get("paths") or []:
            if any(p == u or p.startswith(u + os.sep) for u in unreadable):
                return SimpleNamespace(decision="deny", rule="mrh.path", verdict_available=True,
                                       reason=f"'{p}' is outside your granted scope")
            if need != "r" and any(p == r or p.startswith(r + os.sep) for r in r_only):
                return SimpleNamespace(decision="deny", rule="mrh.path", verdict_available=True,
                                       reason=f"narrowed to r; this act needs {need}")
        return SimpleNamespace(decision="allow", rule="", reason="ok", verdict_available=True)

    c._single_gate.decide = decide
    return calls


def _floor_client(tmp_path, monkeypatch, extra=()):
    floor = tmp_path / "shared-context" / "escalations"
    floor.mkdir(parents=True)
    c, _calls, home, wt = _real_run_client(tmp_path, monkeypatch, [(str(floor), True, "r"), *extra])
    (home / "scratch" / "s.py").write_text("print(1)\n")
    return c, home, wt, os.path.realpath(floor)


def test_an_r_only_floor_mount_does_not_refuse_the_run(tmp_path, monkeypatch):
    c, home, wt, floor = _floor_client(tmp_path, monkeypatch)
    calls = _mode_gate(c, r_only=[floor])
    v = c.gate(BeingIntent("run", {"path": "scratch/s.py"}))
    assert v.decision == "allow", v
    run_ev, read_ev = calls[0][0], calls[1][0]
    assert floor not in run_ev["tool_input"]["paths"]
    assert read_ev["tool"] == "read_file" and read_ev["tool_input"]["paths"] == [floor]
    # still bound read-only: the box, not the gate, is what stops a write there
    toks = run_ev["egress"][-1].split()
    assert toks[toks.index(floor) - 1] == "--ro-bind", run_ev["egress"][-1]


def test_a_refused_read_only_mount_refuses_the_run(tmp_path, monkeypatch):
    c, home, wt, floor = _floor_client(tmp_path, monkeypatch)
    _mode_gate(c, unreadable=[floor])
    v = c.gate(BeingIntent("run", {"path": "scratch/s.py"}))
    assert v.decision == "deny" and v.rule == "mrh.path", v
    assert "read-only" in v.reason and floor in v.reason, v.reason


def test_a_refused_act_is_final_and_no_read_is_judged(tmp_path, monkeypatch):
    c, home, wt, floor = _floor_client(tmp_path, monkeypatch)
    calls = _mode_gate(c, unreadable=[os.path.realpath(home / "scratch" / "s.py")])
    v = c.gate(BeingIntent("run", {"path": "scratch/s.py"}))
    assert v.decision == "deny" and len(calls) == 1, (v, calls)


def test_a_writable_mount_is_still_judged_with_the_run(tmp_path, monkeypatch):
    rw = tmp_path / "granted-rw"; rw.mkdir()
    c, home, wt, floor = _floor_client(tmp_path, monkeypatch, extra=[(str(rw), True, "rwed")])
    calls = _mode_gate(c, r_only=[floor])
    assert c.gate(BeingIntent("run", {"path": "scratch/s.py"})).decision == "allow"
    assert os.path.realpath(rw) in calls[0][0]["tool_input"]["paths"]


def test_a_mask_exposes_nothing_and_is_judged_as_nothing(tmp_path, monkeypatch):
    # nearest rule: a no-r grant beneath an r mount is masked (an empty read-only tmpfs over it)
    root = tmp_path / "floor"; (root / "closed").mkdir(parents=True)
    c, _calls, home, wt = _real_run_client(
        tmp_path, monkeypatch, [(str(root), True, "r"), (str(root / "closed"), True, "w")])
    c._reach_rule = lambda: "nearest"
    (home / "scratch" / "s.py").write_text("print(1)\n")
    closed = os.path.realpath(root / "closed")
    calls = _mode_gate(c, r_only=[os.path.realpath(root)], unreadable=[closed])
    v = c.gate(BeingIntent("run", {"path": "scratch/s.py"}))
    assert v.decision == "allow", v
    line = calls[0][0]["egress"][-1]
    assert f"--tmpfs {closed}" in line, line
    assert closed not in {p for e, _ in calls for p in e["tool_input"].get("paths") or []}
    assert closed not in _line_bind_sources(line)


def test_the_split(tmp_path):
    home = tmp_path / "home"; home.mkdir()
    ro = tmp_path / "ro"; ro.mkdir()
    rw = tmp_path / "rw"; rw.mkdir()
    ctx = {"memory_root": str(home), "granted_reach": [(str(ro), True, "r"), (str(rw), True, "rwed")]}
    assert sandbox_reach("run", {}, ctx) == [os.path.realpath(rw)]
    assert sandbox_read_mounts("run", ctx) == [os.path.realpath(ro)]
    assert sandbox_read_mounts("check", ctx) == []
