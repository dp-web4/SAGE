"""The todo view puts hestia's live status beside an open item that names a scope request.

cbp-being 2026-11-15: two asks refused at 20:06 UTC stayed "pending, lapses in ~6 hours" in its todo; at 21:25
it asked dp to renew them. The refusal was in the same beat's scope block, never beside the stale item."""
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

from sage.gateway import todo_membot as tm
from sage.gateway.heartbeat import todo_view

REFUSED = {"request_id": "scope-8b0be4d34333", "status": "refused", "decided_by": "peer:claude-code",
           "path": "/home/dp/.local/bin"}
PENDING = {"request_id": "scope-6ec4bf5583c4", "status": "pending", "path": "/home/dp/.local/bin"}
ROWS = {"scope-8b0be4d34333": REFUSED, "scope-6ec4bf5583c4": PENDING}


def test_note_names_status_and_ruler():
    assert (tm.scope_status_note("scope-8b0be4d34333: pending, lapses in ~6 hours", ROWS)
            == "hestia now: scope-8b0be4d34333: refused by peer:claude-code")


def test_pending_has_no_ruler():
    assert tm.scope_status_note("renew scope-6ec4bf5583c4", ROWS) == "hestia now: scope-6ec4bf5583c4: pending"


def test_two_ids_each_get_a_fact_once():
    note = tm.scope_status_note("find scope-8b0be4d34333 and scope-6ec4bf5583c4 (scope-8b0be4d34333 again)", ROWS)
    assert note == ("hestia now: scope-8b0be4d34333: refused by peer:claude-code; "
                    "scope-6ec4bf5583c4: pending")


def test_unknown_id_is_said_not_on_record():
    assert tm.scope_status_note("scope-000000000000 waiting", ROWS) == "hestia now: scope-000000000000: not on record for you"


def test_unmeasured_and_no_id_write_nothing():
    assert tm.scope_status_note("scope-8b0be4d34333 pending", None) == ""
    assert tm.scope_status_note("verify numpy in the sandbox", ROWS) == ""


def test_todo_view_shows_live_status_under_the_stale_item():
    with tempfile.TemporaryDirectory() as d:
        inst = Path(d)
        from datetime import datetime, timezone
        stamp = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M")
        (inst / "todo.md").write_text(
            f"{stamp} UTC\n"
            "- [ ] scope-8b0be4d34333: pending for /home/dp/.local/bin, lapses in ~6 hours\n"
            "- [ ] verify the sandbox has numpy\n")
        out = todo_view(inst, scope_rows=ROWS)
        lines = out.splitlines()
        i = next(k for k, l in enumerate(lines) if "lapses in ~6 hours" in l)
        assert lines[i + 1] == "  (hestia now: scope-8b0be4d34333: refused by peer:claude-code)"
        assert "hestia now" not in lines[next(k for k, l in enumerate(lines) if "numpy" in l) + 1]
        # unmeasured beat: the view is as before
        assert "hestia now" not in todo_view(inst)


if __name__ == "__main__":
    for name, fn in list(globals().items()):
        if name.startswith("test_") and callable(fn):
            fn()
            print("ok", name)
