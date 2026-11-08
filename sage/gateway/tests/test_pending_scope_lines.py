"""pending_scope_lines: a pending scope request shown with its age, expiry and what pending means (dp, 2026-11-05)."""
from sage.gateway import heartbeat as hb

NOW = 1_800_000_000.0


def test_pending_requests_show_age_expiry_and_meaning_oldest_first():
    reqs = [
        {"request_id": "scope-new", "path": "/srv/b", "status": "pending",
         "requested_at": NOW - 600, "secs_remaining": 20 * 3600},
        {"request_id": "scope-old", "path": "/srv/a", "status": "pending",
         "requested_at": NOW - 3 * 3600, "secs_remaining": 0},
        {"request_id": "scope-done", "path": "/srv/c", "status": "refused"},
    ]
    out = hb.pending_scope_lines(reqs, now=NOW)
    lines = out.splitlines()
    assert lines[0] == "pending (2), oldest first:"
    assert lines[1] == "- scope-old /srv/a: asked 3 h ago"
    assert lines[2] == "- scope-new /srv/b: asked 10 min ago, lapses in 20 h if nobody rules"
    assert "scope-done" not in out, "a ruled request is not listed as pending"
    assert "Asking again" in out and "does not move it" in out
    assert "decided since your last beat" in out


def test_no_pending_means_no_block():
    assert hb.pending_scope_lines([{"request_id": "x", "path": "/srv/a", "status": "granted"}], now=NOW) == ""
    assert hb.pending_scope_lines([], now=NOW) == ""


def test_many_pending_are_capped_and_counted():
    reqs = [{"request_id": f"scope-{i}", "path": f"/srv/{i}", "status": "pending",
             "requested_at": NOW - i} for i in range(11)]
    out = hb.pending_scope_lines(reqs, now=NOW, most=8)
    assert "pending (11)" in out and "- … and 3 more pending." in out


def test_decision_key_spelling_is_read_too():
    out = hb.pending_scope_lines([{"request_id": "s", "path": "/srv/a", "decision": "pending"}], now=NOW)
    assert "asked at an unrecorded time" in out
