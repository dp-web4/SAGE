"""Hermetic: the being's inbound hub drain (S4). Fake hub read, fake seat notify."""
import os
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "..")))
from sage.gateway.being_inbox_drain import drain_once, map_kind, persist_notice  # noqa: E402


def _inst():
    return Path(tempfile.mkdtemp(prefix="inbox-"))


def test_kind_mapping_hub_roots_to_hestia_member_kinds():
    assert map_kind("review") == "review_request" and map_kind("review.request.pr") == "review_request"
    assert map_kind("forum.note") == "forum-note" and map_kind("reply") == "reply"
    assert map_kind("weird") == "coordination" and map_kind("") == "coordination"


def test_drain_persists_before_notifying_with_provenance_and_is_idempotent():
    inst = _inst()
    notes = [{"kind": "reply", "pointer_uri": "shared-context/forum/x.md", "from": "4a7f7eeb-legion-sage", "pair_id": "n-1"},
             {"kind": "review.request", "pointer_uri": "https://github.com/dp-web4/SAGE/pull/99", "from": "61525719-legion", "pair_id": "n-2"}]
    sent = []
    r = drain_once(inst, env_file="unused", fetch=lambda: notes, notify=lambda k, p: (sent.append((k, p)) or {"ok": True}))
    assert r["fetched"] == 2 and r["persisted"] == 2 and r["notified"] == 2 and r["errors"] == []
    files = sorted((inst / "notes" / "inbox").glob("*.md"))
    assert len(files) == 2
    body = files[0].read_text()
    assert "from: 4a7f7eeb-legion-sage" in body and "pointer: shared-context/forum/x.md" in body and "hub_notice_id: n-1" in body
    assert "relayed_by: sprout-claude" in body and "not by you and not by the sender" in body
    assert [k for k, _ in sent] == ["reply", "review_request"] and all(p.endswith(".md") for _, p in sent)
    # second pass with the same ids: nothing new, nothing re-notified
    sent.clear()
    r2 = drain_once(inst, env_file="unused", fetch=lambda: notes, notify=lambda k, p: (sent.append((k, p)) or {"ok": True}))
    assert r2["skipped"] == 2 and r2["persisted"] == 0 and sent == []
    assert (inst / "notes" / "inbox" / ".seen").read_text().split() == ["n-1", "n-2"]


def test_notify_failure_is_reported_not_raised_and_the_file_stays():
    inst = _inst()
    r = drain_once(inst, env_file="unused", fetch=lambda: [{"kind": "ack", "pointer_uri": "p", "from": "f", "pair_id": "n-9"}],
                   notify=lambda k, p: {"ok": False, "error": "hestia.member_notify_self"})
    assert r["persisted"] == 1 and r["notified"] == 0 and "member_notify_self" in r["errors"][0]
    assert list((inst / "notes" / "inbox").glob("*.md"))


def test_fetch_failure_is_reported_not_raised():
    def boom():
        raise RuntimeError("hub down")
    r = drain_once(_inst(), env_file="unused", fetch=boom, notify=lambda k, p: {"ok": True})
    assert r["fetched"] == 0 and r["errors"] and "hub down" in r["errors"][0]


def test_pointer_is_workspace_relative_when_inside_the_workspace():
    ws = Path(tempfile.mkdtemp(prefix="ws-")) / "sage"
    inst = ws / "sage" / "instances" / "x"
    inst.mkdir(parents=True)
    sent = []
    drain_once(inst, env_file="unused", fetch=lambda: [{"kind": "reply", "pointer_uri": "p", "from": "f", "pair_id": "n-3"}],
               notify=lambda k, p: (sent.append(p) or {"ok": True}), workspace=str(ws))
    assert sent and sent[0].startswith("sage/sage/instances/x/notes/inbox/")


def test_env_file_expands_shell_variables_and_tilde():
    from sage.gateway.being_inbox_drain import _env_from_file
    p = Path(tempfile.mkdtemp(prefix="env-")) / "hub.env"
    p.write_text('# comment\nHUB_URL="http://hub:8770"\nMY_LCT=abc   # trailing comment\nCHANNEL_CLIENT=$HOME/bin/cc\nMY_KEYPAIR=~/.web4/k.bin\n')
    e = _env_from_file(str(p))
    assert e["HUB_URL"] == "http://hub:8770" and e["MY_LCT"] == "abc"
    assert e["CHANNEL_CLIENT"] == os.path.expanduser("~/bin/cc") and e["MY_KEYPAIR"] == os.path.expanduser("~/.web4/k.bin")


def test_default_notify_targets_the_drained_being_not_sprout(monkeypatch=None):
    """Legion 2026-09-05: the mirror drain must tell legion-being's hestia inbox, labelled
    legion-claude — not sprout-being / sprout-claude, which the first cut hard-coded."""
    import sage.gateway.being_inbox_drain as m
    inst = _inst()
    calls = []
    orig = m._seat_notify
    m._seat_notify = lambda kind, pointer, member="sprout-being": (calls.append((kind, pointer, member)) or {"ok": True})
    try:
        r = m.drain_once(inst, env_file="unused", fetch=lambda: [{"kind": "reply", "pointer_uri": "p", "from": "2e175714-sprout-being", "pair_id": "n-7"}],
                         member="legion-being", relayed_by="legion-claude")
    finally:
        m._seat_notify = orig
    assert r["notified"] == 1 and calls == [("reply", calls[0][1], "legion-being")]
    body = next((inst / "notes" / "inbox").glob("*.md")).read_text()
    assert "relayed_by: legion-claude" in body and "sprout-claude" not in body


if __name__ == "__main__":
    n = 0
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            fn(); n += 1; print(f"PASS {name}")
    print(f"\n{n} passed")


def _client(stdout: str, rc: int = 0, stderr: str = ""):
    """A fake channel_client and the identity file naming it."""
    d = Path(tempfile.mkdtemp(prefix="cc-"))
    cc = d / "cc.sh"
    cc.write_text(f"#!/bin/sh\nprintf '%s' {json_quote(stdout)}\nprintf '%s' {json_quote(stderr)} >&2\nexit {rc}\n")
    cc.chmod(0o755)
    ident = d / "ident"
    ident.write_text(f"CHANNEL_CLIENT='{cc}'\nHUB_URL='http://127.0.0.1:1'\nMY_LCT='lct'\nMY_KEYPAIR='{d}/k'\n")
    return str(ident)


def json_quote(s: str) -> str:
    return "'" + s.replace("'", "'\\''") + "'"


def test_cannot_tell_is_not_empty():
    """Sprout, 2026-10-03: a failed or unreadable fetch returned [] and the beat recorded fetched 0 with no
    error -- 1,778 drains of sprout-being's mailbox, never one fetch. Each failure now lands in `errors`."""
    for env, why in ((_client("", rc=1, stderr="no pinned pubkey for lct"), "exited 1: no pinned pubkey"),
                     (_client("banner text, not json"), "unreadable reply"),
                     (_client('{"error": "forbidden"}'), "no notifications field")):
        r = drain_once(_inst(), env_file=env, notify=lambda k, p: {"ok": True})
        assert r["fetched"] == 0 and r["errors"] and why in r["errors"][0], (why, r)


def test_an_empty_mailbox_is_still_empty_with_no_error():
    r = drain_once(_inst(), env_file=_client('{"notifications": []}'), notify=lambda k, p: {"ok": True})
    assert r["fetched"] == 0 and r["errors"] == []


def test_a_real_notice_is_fetched_through_the_client():
    body = '{"notifications": [{"kind": "reply", "pointer_uri": "p", "from": "f", "pair_id": "n-7"}]}'
    r = drain_once(_inst(), env_file=_client(body), notify=lambda k, p: {"ok": True})
    assert r["fetched"] == 1 and r["persisted"] == 1 and r["errors"] == []


def _recording_client(ident_text: str):
    """A fake channel_client that records its argv, and an identity file in the given shape."""
    d = Path(tempfile.mkdtemp(prefix="cc-"))
    cc = d / "cc.sh"
    cc.write_text(f"#!/bin/sh\nprintf '%s\\n' \"$@\" > {d}/argv\nprintf '{{\"notifications\": []}}'\n")
    cc.chmod(0o755)
    ident = d / "ident"
    ident.write_text(ident_text.replace("@CC@", str(cc)).replace("@D@", str(d)))
    return str(ident), d


def test_the_drain_reads_the_identity_file_exactly_as_hub_notify_sources_it():
    """Sprout 2026-10-03: sends (hub-notify sources the file) were accepted while every mailbox read failed
    "invalid length: found 94". The old parser kept a quoted value's trailing comment and keyed `export X=`
    lines as "export X". Now the file is sourced, so both read one set of values."""
    text = ('# a being identity file\n'
            'export CHANNEL_CLIENT="@CC@"\n'
            "HUB_URL='http://127.0.0.1:1'   # the hub\n"
            'MY_LCT="2e175714-4b01-4063-a997-27a6dade7044"  # the being\n'
            'MY_KEYPAIR="@D@/seed"\n')
    ident, d = _recording_client(text)
    r = drain_once(_inst(), env_file=ident, notify=lambda k, p: {"ok": True})
    assert r["errors"] == [], r
    argv = (d / "argv").read_text().splitlines()
    assert argv[:4] == ["http://127.0.0.1:1", "2e175714-4b01-4063-a997-27a6dade7044", f"{d}/seed", "notifications"], argv


def test_a_missing_or_unsourceable_identity_is_an_error_not_empty():
    r = drain_once(_inst(), env_file="/nonexistent/ident", notify=lambda k, p: {"ok": True})
    assert r["fetched"] == 0 and "no identity file" in r["errors"][0]
    ident, _ = _recording_client("HUB_URL='http://127.0.0.1:1'\n")
    r = drain_once(_inst(), env_file=ident, notify=lambda k, p: {"ok": True})
    assert "sets no CHANNEL_CLIENT, MY_LCT, MY_KEYPAIR" in r["errors"][0], r
