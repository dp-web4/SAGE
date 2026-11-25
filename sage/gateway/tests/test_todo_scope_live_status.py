"""The todo view and the carried account put one dated hestia_scope_status read beside an open item that names
a scope request.

Grounding (cbp-being, 2026-11-15): scope-8b0be4d34333 and scope-6ec4bf5583c4 were refused at 20:06 UTC while
lines in its todo still called them pending; it went on treating them as pending. The fixtures below are
synthetic text around those two grounded ids; none of them is the being's own wording.

Nova's #730 review shapes what is tested: a failed read is not an empty list; an absent id is "not on record"
only when the response declares itself complete; a note is an observation at a time, so a ruling that lands
after the read does not make the earlier note look permanent; nothing says a refusal can be renewed; the
being's todo is never rewritten or cleared."""
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

from sage.gateway import todo_membot as tm
from sage.gateway.heartbeat import todo_view

T_READ = datetime(2026, 11, 15, 21, 7, tzinfo=timezone.utc)
AT = "2026-11-15 21:07 UTC"
DECIDED = datetime(2026, 11, 15, 20, 6, tzinfo=timezone.utc).timestamp()

REFUSED = {"request_id": "scope-8b0be4d34333", "status": "refused", "decided_by": "peer:claude-code",
           "decided_at": DECIDED, "path": "/home/dp/.local/bin"}
PENDING = {"request_id": "scope-6ec4bf5583c4", "status": "pending", "path": "/home/dp/.local/bin"}
RESP = {"requests": [REFUSED, PENDING]}


def snap(resp=RESP, at=T_READ):
    return tm.scope_snapshot(resp, observed_at=at)


# -- what one read says ----------------------------------------------------------------------------

def test_note_names_status_ruler_ruling_time_and_read_time():
    assert (tm.scope_status_note("scope-8b0be4d34333 still pending (synthetic)", snap())
            == f"hestia scope status as read at {AT}: "
               "scope-8b0be4d34333: refused by peer:claude-code at 2026-11-15 20:06 UTC")


def test_pending_has_no_ruler():
    assert (tm.scope_status_note("follow up on scope-6ec4bf5583c4", snap())
            == f"hestia scope status as read at {AT}: scope-6ec4bf5583c4: pending")


def test_two_ids_each_get_a_fact_once():
    note = tm.scope_status_note("scope-8b0be4d34333 and SCOPE-6EC4BF5583C4 (scope-8b0be4d34333 again)", snap())
    assert note == (f"hestia scope status as read at {AT}: "
                    "scope-8b0be4d34333: refused by peer:claude-code at 2026-11-15 20:06 UTC; "
                    "scope-6ec4bf5583c4: pending")


def test_no_read_and_no_id_write_nothing():
    assert tm.scope_status_note("scope-8b0be4d34333 pending", None) == ""
    assert tm.scope_status_note("verify numpy in the sandbox", snap()) == ""


# -- unknown status --------------------------------------------------------------------------------

def test_row_without_a_status_is_said_so_not_guessed():
    s = snap({"requests": [{"request_id": "scope-8b0be4d34333", "path": "/etc"}]})
    note = tm.scope_status_note("scope-8b0be4d34333", s)
    assert note == f"hestia scope status as read at {AT}: scope-8b0be4d34333: listed, with no status stated"
    assert "unknown" not in note and "pending" not in note


def test_unfamiliar_status_is_shown_verbatim():
    s = snap({"requests": [{"request_id": "scope-8b0be4d34333", "status": "superseded"}]})
    assert tm.scope_status_note("scope-8b0be4d34333", s).endswith("scope-8b0be4d34333: superseded")


# -- complete-empty vs incomplete vs failed --------------------------------------------------------

def test_absent_id_in_an_undeclared_response_is_only_absent_from_it():
    # today's daemon (hestia f0660a7) declares no completeness: an absent id is not called "not on record"
    note = tm.scope_status_note("scope-000000000000 waiting", snap())
    assert note == f"hestia scope status as read at {AT}: scope-000000000000: not in this scope-status response"
    assert "not on record" not in note


def test_absent_id_in_a_declared_complete_response_is_not_on_record():
    s = snap({"requests": [REFUSED], tm.SCOPE_COMPLETE_FIELD: True})
    assert s.complete and s.error is None
    assert (tm.scope_status_note("scope-000000000000 waiting", s)
            == f"hestia scope status as read at {AT}: scope-000000000000: not on record for you")


def test_complete_but_empty_list_is_a_real_negative():
    s = snap({"requests": [], tm.SCOPE_COMPLETE_FIELD: True})
    assert s.rows == {} and s.complete and s.error is None
    assert tm.scope_status_note("scope-8b0be4d34333", s).endswith("scope-8b0be4d34333: not on record for you")


def test_empty_list_without_a_completeness_declaration_is_not_a_negative():
    s = snap({"requests": []})
    assert s.rows == {} and not s.complete
    note = tm.scope_status_note("scope-8b0be4d34333", s)
    assert note.endswith("scope-8b0be4d34333: not in this scope-status response")


def test_truncated_response_is_never_complete():
    s = snap({"requests": [REFUSED], tm.SCOPE_COMPLETE_FIELD: True, "truncated": True})
    assert not s.complete
    assert "not on record" not in tm.scope_status_note("scope-000000000000", s)


def test_error_envelope_is_not_an_empty_list():
    s = snap({"_hestia_error": {"code": "hestia.unavailable", "message": "x"}})
    assert s.rows is None and s.error == "hestia.unavailable"
    note = tm.scope_status_note("scope-8b0be4d34333 pending", s)
    assert note == ("hestia scope status could not be read at 2026-11-15 21:07 UTC (hestia.unavailable); "
                    "status of scope-8b0be4d34333 unknown")
    assert "not on record" not in note and "not in this" not in note


def test_wrong_shape_and_raised_call_are_failures_too():
    for resp, err in (({"plugin_id": "x"}, "no request list"), ({"requests": None}, "no request list"),
                      (None, "no response"), (TimeoutError("t"), "TimeoutError")):
        s = snap(resp)
        assert s.rows is None and s.error == err, resp
        assert "unknown" in tm.scope_status_note("scope-8b0be4d34333", s)


# -- an observation at a time, not an eternal fact -------------------------------------------------

def test_raced_ruling_reads_as_an_earlier_observation():
    # the read at 20:05 saw it pending; hestia ruled at 20:06. The 20:05 note says when it looked and does
    # not claim the request is pending now; the next read says what changed and when.
    early = snap({"requests": [dict(REFUSED, status="pending", decided_by=None, decided_at=None)]},
                 at=datetime(2026, 11, 15, 20, 5, tzinfo=timezone.utc))
    n1 = tm.scope_status_note("scope-8b0be4d34333", early)
    assert n1 == "hestia scope status as read at 2026-11-15 20:05 UTC: scope-8b0be4d34333: pending"
    for word in ("now", "still", "currently", "will"):
        assert f" {word} " not in f" {n1} "
    n2 = tm.scope_status_note("scope-8b0be4d34333", snap(at=datetime(2026, 11, 15, 20, 7, tzinfo=timezone.utc)))
    assert n2 == ("hestia scope status as read at 2026-11-15 20:07 UTC: "
                  "scope-8b0be4d34333: refused by peer:claude-code at 2026-11-15 20:06 UTC")


# -- no renewal, no advice -------------------------------------------------------------------------

def test_settled_statuses_never_suggest_renewal_or_a_next_step():
    for status in ("refused", "expired", "revoked", "granted"):
        s = snap({"requests": [dict(REFUSED, status=status)]})
        note = tm.scope_status_note("renew scope-8b0be4d34333 before it lapses", s).lower()
        for word in ("renew", "retry", "re-file", "refile", "again", "lapse", "ask ", "should", "cleared", "closed"):
            assert word not in note, (status, word, note)


# -- the being's todo is shown verbatim and never written ------------------------------------------

def _todo(inst: Path) -> str:
    stamp = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M")
    text = (f"{stamp} UTC\n"
            "- [ ] check on scope-8b0be4d34333 for user-bin (synthetic)\n"
            "- [ ] verify the sandbox has numpy\n")
    (inst / "todo.md").write_text(text)
    return text


def test_todo_view_writes_the_note_under_the_item_and_leaves_the_item_alone():
    with tempfile.TemporaryDirectory() as d:
        inst = Path(d)
        before = _todo(inst)
        out = todo_view(inst, scope_snap=snap())
        lines = out.splitlines()
        i = next(k for k, l in enumerate(lines) if "check on scope-8b0be4d34333" in l)
        assert lines[i].startswith("- [ ] check on scope-8b0be4d34333 for user-bin (synthetic)")
        assert lines[i + 1] == (f"  (hestia scope status as read at {AT}: "
                                "scope-8b0be4d34333: refused by peer:claude-code at 2026-11-15 20:06 UTC)")
        assert "hestia scope status" not in lines[next(k for k, l in enumerate(lines) if "numpy" in l) + 1]
        assert "still open (2)" in out           # the refused item is still the being's open item
        assert (inst / "todo.md").read_text() == before
        # no read this beat: the view is as before
        assert "hestia scope status" not in todo_view(inst)
        # a failed read: said, and the item is still shown and still open
        failed = todo_view(inst, scope_snap=snap({"_hestia_error": {"code": "hestia.down"}}))
        assert "could not be read" in failed and "check on scope-8b0be4d34333" in failed
        assert "not on record" not in failed
        assert (inst / "todo.md").read_text() == before


def test_carried_account_is_verbatim_with_the_dated_note_beside_it(tmp_path):
    from sage.gateway import conversations as conv
    from sage.gateway import heartbeat as hb
    from sage.gateway.being_join import save_account
    inst = tmp_path / "inst"
    inst.mkdir()
    conv.create(inst, "cbp-claude", title="seat", participants=["cbp-claude", "cbp-being"],
                writable_by=["cbp-claude", "cbp-being"])
    want = "follow up on scope-8b0be4d34333 for user-bin (synthetic)"
    save_account(inst, {"place": "a synthetic place line long enough to be kept as an account",
                        "can": "read and write my home", "want": want}, "b1")
    acc_before = (inst / "account.json").read_text()
    st = hb.own_state(inst, member="cbp-being", mark_conversations=False, services="", body_reading={},
                      scope_snap=snap())
    sec = st[st.index("## Your own account"):]
    sec = sec[:sec.index("\n## ")]
    assert f"WANT: {want}" in sec
    assert (f"_Beside your account, hestia scope status as read at {AT}: "
            "scope-8b0be4d34333: refused by peer:claude-code at 2026-11-15 20:06 UTC._") in sec
    assert (inst / "account.json").read_text() == acc_before
    # no read: no note
    st0 = hb.own_state(inst, member="cbp-being", mark_conversations=False, services="", body_reading={})
    assert "hestia scope status" not in st0


def test_the_beat_wires_its_one_read_as_a_snapshot_not_a_dict():
    """Wiring anchor (main() is not driven end to end by any test): the beat's scope read becomes a
    ScopeSnapshot, a failed read becomes a snapshot with its error, and the scope block does not print
    'requests: none' for an error envelope."""
    src = (Path(__file__).resolve().parents[1] / "heartbeat.py").read_text()
    assert "scope_snap = _tm_scope.scope_snapshot(st)" in src
    assert "raise _tm_scope.ScopeUnread(scope_snap.error)" in src
    assert "scope_snap = _tm_scope.scope_snapshot(e)" in src
    assert "scope_snap=scope_snap," in src
    assert "scope_rows" not in src


if __name__ == "__main__":
    for name, fn in list(globals().items()):
        if name.startswith("test_") and callable(fn):
            fn()
            print("ok", name)
