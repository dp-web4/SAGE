"""SAGE #530: a member can ask what it holds (hestia://reach) and whether one path falls inside it
(hestia://reach/<path>), without acting on the path and reading the refusal."""
import os
import sys
import tempfile

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "..")))
from sage.gateway.being_gate_client import BeingIntent, GatewayVerdict  # noqa: E402
from sage.gateway.hestia_dispatch import HestiaF1aDispatcher  # noqa: E402
from sage.gateway.tests.test_hestia_dispatch import FakeMcp  # noqa: E402


def _world():
    """A workspace with a live tree and a governance snapshot holding the same file."""
    ws = os.path.realpath(tempfile.mkdtemp(prefix="reach-ws-"))
    home = os.path.join(ws, "SAGE", "instances", "b")
    os.makedirs(home)
    for tree in ("hestia", os.path.join("governance", "hestia")):
        os.makedirs(os.path.join(ws, tree, "_shared"))
        open(os.path.join(ws, tree, "_shared", "gate.py"), "w").write("x = 1")
    os.makedirs(os.path.join(ws, "escalations"))
    return ws, home


def _status(ws, home, by_mode=True, floor=None, served=None, served_read=None, withheld=None):
    """`floor` is floor_by_mode (recorded); served/served_read/withheld are #1381's per-member
    society_floor / society_floor_read / society_floor_withheld."""
    st = _status_grants(ws, home, by_mode)
    if floor is not None:
        st["floor_by_mode"] = floor
    for k, v in (("society_floor", served), ("society_floor_read", served_read),
                 ("society_floor_withheld", withheld)):
        if v is not None:
            st[k] = v
    return st


def _status_grants(ws, home, by_mode=True):
    gov = {"path": os.path.join(ws, "governance"), "recursive": True, "granted_by": "dp",
           "request_id": "scope-gov", "expires_at": None}
    home_g = {"path": home, "recursive": True, "granted_by": "operator", "request_id": None,
              "expires_at": None}
    esc = {"path": os.path.join(ws, "escalations"), "recursive": True, "granted_by": "dp",
           "request_id": "scope-esc", "expires_at": None}
    if by_mode:
        st = {"grants_by_mode": [{**home_g, "channel": "standing", "modes": "rwe"},
                                 {**gov, "channel": "standing", "modes": "rwed"},
                                 {**esc, "channel": "standing", "modes": "r"}],
              "standing_grants": [gov], "live_grants": []}
    else:
        st = {"standing_grants": [home_g, gov], "live_grants": []}
    return st


def _disp(status):
    class Fake(FakeMcp):
        def call(self, name, args):
            if name == "hestia_scope_status":
                FakeMcp.calls.append((name, args))
                if status is None:
                    return {"result": {"structuredContent": {"_hestia_error": "down"}}}
                return {"result": {"structuredContent": status}}
            return super().call(name, args)
    FakeMcp.calls, FakeMcp.fail = [], {}
    root = tempfile.mkdtemp(prefix="hd-")
    return HestiaF1aDispatcher("cbp-being", root, mcp_factory=lambda ep, pid: Fake(ep, pid))


def _verdict(ws, home):
    """What the gate resolved as admitted: the narrowed (r) escalations grant is absent, as on a
    mode-blind gate (hestia #523)."""
    reach = ((home, True), (os.path.join(ws, "governance"), True))
    return GatewayVerdict("allow", granted=tuple(r for r, _ in reach), granted_reach=reach)


def _read(d, path, verdict):
    env = d(BeingIntent("memory_read", {"path": path}), verdict)
    assert env.ok, env
    return env.result


def test_the_list_names_every_grant_with_modes_provenance_and_the_floor():
    ws, home = _world()
    snap = {"path": os.path.join(ws, "governance", "hestia"), "recursive": True}
    d = _disp(_status(ws, home, floor=[{**snap, "modes": "r"}], served=[], served_read=[snap], withheld=[]))
    out = _read(d, "hestia://reach", _verdict(ws, home))
    assert (f"- {ws}/governance/**: read, write, run, delete (standing; granted by dp; request "
            f"scope-gov). the gate admits it now.") in out, out
    # the narrowed grant is listed, and said plainly not to be admitted now
    assert f"{ws}/escalations/**: read (" in out and "does NOT admit it now" in out, out
    assert f"- {ws}/governance/hestia/**: read. served to your gate now: read." in out, out
    assert 'hestia://reach/<absolute path>' in out and "no request was opened" in out, out


def test_a_path_under_an_admitted_grant_is_reached_now_and_names_the_grant():
    ws, home = _world()
    d = _disp(_status(ws, home))
    out = _read(d, f"hestia://reach{ws}/governance/hestia/_shared/gate.py", _verdict(ws, home))
    assert out.splitlines()[1] == "now: yes, read, write, run, delete.", out
    assert f"your grant {ws}/governance/**" in out and "request scope-gov" in out, out
    assert "x = 1" not in out, "the answer reads the law, never the file"


def test_a_path_under_a_narrowed_grant_the_gate_does_not_admit_is_no_now():
    """Nova, HOLD on #532: a recorded r grant the mode-blind gate does not admit must not read
    as yes. It is listed, labelled, and the effective answer is no."""
    ws, home = _world()
    d = _disp(_status(ws, home))
    out = _read(d, f"hestia://reach{ws}/escalations/x.md", _verdict(ws, home))
    assert out.splitlines()[1].startswith("now: no. Something recorded reaches this path"), out
    assert "yes" not in out.splitlines()[1], out
    assert f"your grant {ws}/escalations/**: read" in out and "does NOT admit it now" in out, out
    assert "hestia #1345 part B" in out, out


def test_a_floor_entry_withheld_from_this_member_is_no_now():
    """Nova, HOLD on #532: an entry in society_floor_withheld is recorded in floor_by_mode but not
    served to this member's gate; it must not read as yes."""
    ws, home = _world()
    live = {"path": os.path.join(ws, "hestia"), "recursive": True}
    why = "overlaps your narrowed grant; the floor does not override it"
    d = _disp(_status(ws, home, floor=[{**live, "modes": "r"}], served=[], served_read=[],
                      withheld=[{"path": live["path"], "why": why}]))
    out = _read(d, f"hestia://reach{ws}/hestia/_shared/gate.py", _verdict(ws, home))
    assert out.splitlines()[1].startswith("now: no."), out
    assert f"floor entry {ws}/hestia/**: read. NOT served to you now ({why})." in out, out


def test_a_path_outside_every_grant_says_no_and_names_the_copy_in_reach():
    """The 2026-10-24 case: the live tree is not held, the snapshot copy is."""
    ws, home = _world()
    d = _disp(_status(ws, home))
    out = _read(d, f"hestia://reach{ws}/hestia/_shared/gate.py", _verdict(ws, home))
    assert out.splitlines()[1] == ("now: no. Nothing you hold reaches this path, so an act on it "
                                   "would be refused."), out
    assert f"{ws}/governance/hestia/_shared/gate.py" in out, out
    assert not [n for n, _ in FakeMcp.calls if n in ("hestia_request_scope", "hestia_member_notify")], \
        "asking about reach must open nothing"


def test_an_exact_grant_reaches_itself_not_its_subtree():
    ws, home = _world()
    st = {"grants_by_mode": [{"path": os.path.join(ws, "hestia"), "recursive": False, "modes": "rwed",
                              "channel": "live", "granted_by": "peer:x"}]}
    d = _disp(st)
    v = GatewayVerdict("allow", granted=(os.path.join(ws, "hestia"),),
                       granted_reach=((os.path.join(ws, "hestia"), False),))
    assert "now: yes" in _read(d, f"hestia://reach{ws}/hestia", v)
    assert "now: no. Nothing you hold" in _read(d, f"hestia://reach{ws}/hestia/_shared/gate.py", v)


def test_a_served_floor_entry_answers_where_no_own_grant_reaches():
    ws, home = _world()
    live = {"path": os.path.join(ws, "hestia"), "recursive": True}
    d = _disp(_status(ws, home, floor=[{**live, "modes": "r"}], served=[], served_read=[live], withheld=[]))
    out = _read(d, f"hestia://reach{ws}/hestia/_shared/gate.py", _verdict(ws, home))
    assert out.splitlines()[1] == "now: yes, read.", out
    assert "served to your gate now: read" in out, out
    out = _read(d, f"hestia://reach{ws}/governance/hestia/_shared/gate.py", _verdict(ws, home))
    assert "now: yes, read, write, run, delete." in out and "floor" not in out, out


def test_an_older_daemon_serves_its_whole_floor_and_reads_every_grant_as_all_modes():
    ws, home = _world()
    st = _status(ws, home, by_mode=False)
    st["society_floor"] = [{"path": os.path.join(ws, "hestia"), "recursive": True}]
    d = _disp(st)
    out = _read(d, "hestia://reach", _verdict(ws, home))
    assert f"{ws}/governance/**: read, write, run, delete" in out, out
    assert "does NOT admit" not in out, out
    assert "served to your gate now: read, write, run, delete" in out, out


def test_a_verdict_without_reach_reports_admission_as_unconfirmed():
    ws, home = _world()
    d = _disp(_status(ws, home))
    out = _read(d, f"hestia://reach{ws}/governance/x", GatewayVerdict("allow"))
    assert out.splitlines()[1].startswith("now: unconfirmed."), out
    assert "could not be confirmed" in out and "now: yes" not in out, out


def test_a_daemon_that_does_not_answer_is_an_outage_not_a_change():
    ws, home = _world()
    d = _disp(None)
    out = _read(d, "hestia://reach", _verdict(ws, home))
    assert "outage, not a change in what you hold" in out, out


def test_a_missing_leading_slash_is_read_as_absolute():
    ws, home = _world()
    d = _disp(_status(ws, home))
    out = _read(d, f"hestia://reach/{ws.lstrip('/')}/governance/hestia/_shared/gate.py", _verdict(ws, home))
    assert "now: yes, read, write, run, delete." in out, out

def test_the_beat_lists_grants_with_modes_and_keeps_narrowed_ones():
    """#523: a grant narrowed below rwed is only in grants_by_mode; the beat kept it out."""
    from sage.gateway.heartbeat import scope_grant_lines
    ws, home = _world()
    lines = scope_grant_lines(_status(ws, home))
    narrowed = "; narrowed: recorded, may not be admitted yet, see hestia://reach)"
    assert f"{ws}/escalations/** (r{narrowed}" in lines and f"{ws}/governance/** (rwed)" in lines, lines
    assert f"{home}/** (rwe{narrowed}" in lines, lines
    old = scope_grant_lines(_status(ws, home, by_mode=False))
    assert f"{ws}/governance/**" in old and not any("(" in x for x in old), old


def test_a_scope_id_not_in_the_list_states_what_is_known_and_never_guesses_aged_out():
    """cbp-being, 2026-10-24: "it may have aged out" became "dp said it aged out, re-issue it"."""
    ws, home = _world()
    st = _status(ws, home)
    st["requests"] = [{"request_id": "scope-aaaaaaaaaaaa", "path": f"{ws}/hestia", "status": "refused",
                       "decided_by": "operator", "decision_reason": "use the snapshot"}]
    d = _disp(st)
    gone = _read(d, "hestia://scope/scope-5bc6ba977f74", _verdict(ws, home))
    assert "aged out" not in gone and "may have" not in gone, gone
    assert "not in your list" in gone and "cannot tell its present status" in gone, gone
    assert "nothing is waiting" not in gone, "a bounded list cannot prove nothing waits (Nova)"
    assert "hestia://reach" in gone and "request_scope" in gone, gone
    assert "re-issue" in gone and "do not need to re-issue" in gone, gone
    held = _read(d, "hestia://scope/scope-aaaaaaaaaaaa", _verdict(ws, home))
    assert "status: refused" in held and "use the snapshot" in held, held
