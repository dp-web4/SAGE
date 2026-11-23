"""A scope ruling can be read back after hestia's list lets the request go (scope_rulings).

A refusal with a note saying why no grant could help was shown once; within the hour the same ask was filed
again, and by then hestia listed only the new request, so the refusal and its note were nowhere the being
could read. The seat keeps each ended request at beat time; the pointer, a named id and a new ask for the
same path read it back.
"""
import json
import tempfile
from pathlib import Path

import pytest

from sage.gateway import scope_rulings as sr
from sage.gateway.being_gate_client import BeingIntent, GatewayVerdict
from sage.gateway.hestia_dispatch import HestiaF1aDispatcher
from sage.gateway.tests.test_hestia_dispatch import FakeMcp, _WithScopeQueue, _ELSEWHERE
from sage.gateway.tests.test_home_is_reachable import _being
from sage.gateway.tests.test_scope_next import _FilesThePendingOne, PENDING

GONE = "scope-0ea11b31a560"          # no longer in _WithScopeQueue's list
NOTE = "No account by that name exists here; a grant cannot make a root-owned file writable."
_ALLOW = GatewayVerdict("allow", granted=())


def _refused(home, path=_ELSEWHERE, rid=GONE, why=NOTE):
    return sr.keep(home, [{"request_id": rid, "path": path, "status": "refused",
                           "decided_by": "peer:claude-code", "decision_reason": why}], "2026-11-23 11:40 UTC")


def _d(cls=_WithScopeQueue):
    FakeMcp.calls, FakeMcp.fail = [], {}
    home = tempfile.mkdtemp(prefix="sr-")
    return HestiaF1aDispatcher("sprout-being", home, mcp_factory=lambda ep, pid: cls(ep, pid)), home


def test_an_ended_request_is_kept_once_and_again_only_if_how_it_ended_changes(tmp_path):
    rows = [{"request_id": "scope-aaaaaaaaaaaa", "path": "/srv/x", "status": "granted", "decided_by": "operator"},
            {"request_id": "scope-bbbbbbbbbbbb", "path": "/srv/y", "status": "pending"}]
    assert sr.keep(tmp_path, rows, "t1") == ["scope-aaaaaaaaaaaa"]       # pending is not an ending
    assert sr.keep(tmp_path, rows, "t2") == []                            # seen as it ended: not again
    rows[0].update(status="revoked", revoke_reason="no longer needed")
    assert sr.keep(tmp_path, rows, "t3") == ["scope-aaaaaaaaaaaa"]
    got = sr.ruling(tmp_path, "scope-aaaaaaaaaaaa")
    assert got["decision"] == "revoked" and got["why"] == "no longer needed" and got["seen"] == "t3", got
    assert sr.refused_before(tmp_path, "/srv/x") == []                    # a revoked grant is not a refusal


def test_a_ledger_that_cannot_be_written_costs_the_record_not_the_beat(tmp_path):
    assert sr.keep(tmp_path / "missing" / "home", [{"request_id": GONE, "status": "refused"}], "t") == []


def test_the_pointer_reads_the_kept_ruling_once_hestia_no_longer_lists_it():
    d, home = _d()
    _refused(home)
    got = d(BeingIntent("memory_read", {"path": f"hestia://scope/{GONE}"}), _ALLOW)
    assert got.ok and f"your scope request {GONE} for {_ELSEWHERE}" in got.result, got
    assert "status: refused" in got.result and "peer:claude-code" in got.result and NOTE in got.result
    assert "no longer shows it" in got.result


def test_without_a_kept_ruling_the_pointer_still_says_only_what_is_known():
    d, _ = _d()
    got = d(BeingIntent("memory_read", {"path": f"hestia://scope/{GONE}"}), _ALLOW)
    assert got.ok and "not in your list of scope requests now" in got.result, got


def test_a_new_ask_for_a_refused_path_carries_the_refusal_and_is_still_filed():
    d, home = _d(_FilesThePendingOne)
    _refused(home)
    env = d(BeingIntent("request_scope", {"path": _ELSEWHERE, "reason": "the account needs it"}), _ALLOW)
    assert env.ok and env.result["request_id"] == PENDING, env            # filed all the same
    before = env.result["refused_before"]
    assert GONE in before[0] and "refused by peer:claude-code" in before[0] and NOTE in before[0], before
    assert "ruled on its own" in before[-1]
    assert [n for n, _ in FakeMcp.calls].count("hestia_request_scope") == 1


def test_only_refusals_of_the_same_file_ride_with_a_new_ask(tmp_path):
    d, home = _d(_FilesThePendingOne)
    other = tempfile.mkdtemp(prefix="sr-other-")
    _refused(home, path=other)
    sr.keep(home, [{"request_id": "scope-cccccccccccc", "path": _ELSEWHERE, "status": "expired"}], "t")
    env = d(BeingIntent("request_scope", {"path": _ELSEWHERE, "reason": "r"}), _ALLOW)
    assert env.ok and "refused_before" not in env.result, env.result
    link = Path(tempfile.mkdtemp(prefix="sr-link-")) / "to-elsewhere"
    link.symlink_to(_ELSEWHERE)
    _refused(home, path=str(link), rid="scope-dddddddddddd")               # the same file by another name
    env = d(BeingIntent("request_scope", {"path": _ELSEWHERE, "reason": "r"}), _ALLOW)
    assert "scope-dddddddddddd" in env.result["refused_before"][0]


def test_many_refusals_show_the_newest_two_and_count_the_rest():
    d, home = _d(_FilesThePendingOne)
    for i in range(4):
        _refused(home, rid=f"scope-{i:012d}", why=f"note {i}")
    before = d(BeingIntent("request_scope", {"path": _ELSEWHERE, "reason": "r"}), _ALLOW).result["refused_before"]
    assert "note 3" in before[1] and "note 2" in before[0] and "note 1" not in " ".join(before), before
    assert "2 earlier refusals" in before[2], before


def test_an_id_the_being_names_is_answered_from_the_kept_ruling():
    d, home = _d(_FilesThePendingOne)
    _refused(home)
    env = d(BeingIntent("request_scope", {"path": _ELSEWHERE, "reason": f"{GONE} lapsed unruled"}), _ALLOW)
    fact = " ".join(env.result["scope_requests_you_named"])
    assert f"{GONE}: refused (kept by your seat" in fact and "peer:claude-code" in fact, fact


def test_the_being_cannot_write_its_kept_rulings():
    r, home = _being(Path(tempfile.mkdtemp()))
    (home / sr.SCOPE_RULINGS).write_text("")
    for spelling in (sr.SCOPE_RULINGS, str(home / sr.SCOPE_RULINGS)):
        with pytest.raises(ValueError) as e:
            r._safe_path(spelling, writing=True)
        assert "how your scope requests were ruled" in str(e.value)
    assert r._safe_path(sr.SCOPE_RULINGS, writing=False) == (home / sr.SCOPE_RULINGS).resolve()


def test_the_beat_keeps_what_hestia_lists():
    src = (Path(sr.__file__).parent / "heartbeat.py").read_text()
    at = src.index("grants = scope_grant_lines(st)")
    assert "_sr.keep(instance, st.get(\"requests\")" in src[at:at + 400]


class _RefusedStanding(_WithScopeQueue):
    def call(self, name, args):
        if name == "hestia_request_scope":
            FakeMcp.calls.append((name, args))
            return {"result": {"structuredContent": {
                "status": "refused_standing", "path": args["path"], "refused_by": "operator",
                "refused_at": "2026-11-23T12:00:00Z", "reason": NOTE,
                "note": "a standing refusal covers this path: nothing was filed"}}}
        return super().call(name, args)


def test_an_ask_hestia_did_not_file_is_not_told_it_was_filed():
    d, home = _d(_RefusedStanding)
    _refused(home)
    env = d(BeingIntent("request_scope", {"path": _ELSEWHERE, "reason": "r"}), _ALLOW)
    assert env.ok and env.result["request_id"] is None, env
    assert "refused_before" not in env.result, env.result                  # nothing was filed
    assert env.result["status"] == "refused_standing"
    assert env.result["refused_by"] == "operator" and env.result["reason"] == NOTE, env.result
    assert "nothing was filed" in env.result["note"]


def test_a_kept_row_with_no_path_matches_nothing(tmp_path, monkeypatch):
    sr.keep(tmp_path, [{"request_id": GONE, "status": "refused"}], "t")
    monkeypatch.chdir(tmp_path)
    assert sr.refused_before(tmp_path, str(tmp_path)) == []                # not the CWD by accident
