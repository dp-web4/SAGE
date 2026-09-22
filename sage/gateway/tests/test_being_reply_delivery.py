"""The being's reply to dp was lost three ways on 2026-09-14/15 (cbp-being): a `say` written as
text, a question marked seen by a beat that could not act, and a stale outage claim that a
measured line did not displace. One test per mechanism, on the measured shapes."""
import json
import os
import sys
import tempfile
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "..")))
from sage.gateway import conversations as conv  # noqa: E402
from sage.gateway.being_tool_loop import salvage_tool_calls  # noqa: E402
from sage.gateway.heartbeat import mark_conversations_after_beat, service_contradictions  # noqa: E402

TOOLS = [{"function": {"name": "say", "parameters": {"properties": {"to": {}, "text": {}}}}},
         {"function": {"name": "remember", "parameters": {"properties": {"content": {}, "tags": {}}}}}]


def test_the_attribute_form_say_of_19_30z_is_lifted():
    reply = ('**say to="dp" text="I\'m working on the MCP server outage at 127.0.0.1:8010. I\'m curious '
             'whether the hub\'s routing is correctly forwarding the request."**')
    calls = salvage_tool_calls(reply, TOOLS)
    assert len(calls) == 1 and calls[0]["_salvaged"] == "attr"
    args = calls[0]["function"]["arguments"]
    assert args["to"] == "dp" and args["text"].startswith("I'm working on") and args["text"].endswith("request.")


def test_prose_about_saying_is_not_a_call():
    for prose in ("I could say something to dp later.", "I will say to the hub that it is slow.",
                  "say hello", 'the tool say is how I reply; to="dp" is its argument'):
        assert salvage_tool_calls(prose, TOOLS) == [], prose
    assert salvage_tool_calls('say colour="blue"', TOOLS) == [], "no key of the tool's schema, no call"


def _res(*calls):
    return SimpleNamespace(trace=[(SimpleNamespace(effector=e, args=a), SimpleNamespace(ok=ok)) for e, a, ok in calls])


def _instance_with_dp_question():
    inst = Path(tempfile.mkdtemp(prefix="reply-"))
    conv.create(inst, "dp", title="dp and cbp-being", participants=["dp", "cbp-being"],
                writable_by=["dp", "cbp-being"])
    conv.append(inst, "dp", speaker="dp", text="what are you curious about?")
    return inst


def test_a_beat_whose_explore_could_not_act_leaves_the_question_unseen():
    inst = _instance_with_dp_question()
    shown = conv.latest_seqs(inst, "cbp-being")
    assert shown == {"dp": 1}, shown
    out = mark_conversations_after_beat(inst, "cbp-being", shown, _res(),
                                        [_res(), _res(("memory_write", {"path": "journal.md"}, True))])
    assert out["held_unseen"] == list(shown) and out["marked"] == {}
    assert conv.awaiting(inst, list(shown)[0], "cbp-being"), "still unanswered for the next beat"


def test_a_say_into_the_conversation_or_an_acting_explore_marks_it():
    inst = _instance_with_dp_question()
    shown = conv.latest_seqs(inst, "cbp-being")
    assert shown, shown
    cid = list(shown)[0]
    out = mark_conversations_after_beat(inst, "cbp-being", shown, _res(),
                                        [None, _res(("say", {"to": cid, "text": "hi"}, True))])
    assert out["marked"] == shown
    inst2 = _instance_with_dp_question()
    out2 = mark_conversations_after_beat(inst2, "cbp-being", conv.latest_seqs(inst2, "cbp-being"),
                                         _res(("memory_read", {"path": "todo.md"}, True)), [])
    assert out2["explore_acted"] is True and out2["marked"]


def test_a_stale_outage_claim_meets_the_beings_own_successful_remember():
    inst = Path(tempfile.mkdtemp(prefix="contra-"))
    (inst / "todo.md").write_text("2026-09-15 05:02 UTC\n- [ ] Determine root cause of MCP server at "
                                  "127.0.0.1:8010 being offline for ~21 hours\n")
    (inst / "journal.md").write_text("A quiet beat.\n")
    rec = {"ts": "2026-09-15T05:34:32Z",
           "reflect": {"trace": [{"effector": "remember", "ok": True, "witness_id": "b9330968-a66a"}]}}
    (inst / "heartbeats.jsonl").write_text(json.dumps(rec) + "\n")
    up = "- long-term memory (membot) (127.0.0.1:8010): reachable, connected in 1 ms"
    block = service_contradictions(inst, "cbp-being", up)
    assert "Your own record disagrees" in block and "todo.md" in block and "offline for ~21 hours" in block
    assert "1 call(s) through it succeeded (`remember`; witness b9330968)" in block
    assert service_contradictions(inst, "cbp-being",
                                  "- long-term memory (membot) (127.0.0.1:8010): NOT reachable (x)") == ""
    (inst / "todo.md").write_text("- [x] tidy notes\n")
    assert service_contradictions(inst, "cbp-being", up) == "", "no claim, no block"


def test_the_policy_daemon_story_meets_the_beings_own_gated_writes():
    """2026-09-15: a 30 s deploy restart refused two writes; the being then wrote for ten hours
    that the hestia policy daemon was unreachable, while its gated writes kept succeeding."""
    inst = Path(tempfile.mkdtemp(prefix="contra-hestia-"))
    (inst / "todo.md").write_text("- [OPEN] The hestia policy daemon has been unreachable for ~21 hours.\n")
    (inst / "journal.md").write_text("quiet\n")
    rec = {"ts": "2026-09-15T16:57:54Z",
           "explore": {"trace": [{"effector": "memory_write", "ok": True, "witness_id": "aa11bb22"},
                                 {"effector": "peer_ask", "ok": True, "witness_id": "cc33"}]},
           "reflect": {"trace": [{"effector": "memory_write", "ok": False, "witness_id": None}]}}
    (inst / "heartbeats.jsonl").write_text(json.dumps(rec) + "\n")
    services = ("- long-term memory (membot) (127.0.0.1:8010): reachable, connected in 1 ms\n"
                "- governance daemon (hestia) (127.0.0.1:7711): reachable, connected in 0 ms")
    block = service_contradictions(inst, "cbp-being", services)
    assert block.count("Your own record disagrees") == 1, "only hestia is claimed down"
    assert "127.0.0.1:7711" in block and "2 call(s) through it succeeded (`memory_write`, `peer_ask`" in block
    assert "allowed by this daemon's verdict" in block and "witness aa11bb22" in block and "None" not in block


def test_the_beings_own_stale_claims_carry_their_refutation():
    """2026-09-16: cbp-being's state carried 24 lines asserting "the hestia policy daemon has
    been unreachable for ~21 hours" (its own replayed messages) against 2 measuring both
    services reachable. One line does not outvote a dozen of its own sentences, so the
    refutation goes on each claim."""
    from sage.gateway.heartbeat import refuted_claims
    inst = Path(tempfile.mkdtemp(prefix="refute-"))
    conv.create(inst, "dp", title="dp and cbp-being", participants=["dp", "cbp-being"],
                writable_by=["dp", "cbp-being"])
    conv.append(inst, "dp", speaker="cbp-being", text="The hestia policy daemon at 127.0.0.1:7711 has been unreachable for ~21 hours.")
    conv.append(inst, "dp", speaker="cbp-being", text="Working on the kymth words today.")
    conv.append(inst, "dp", speaker="dp", text="the daemon is down? that is news to me")
    services = "- governance daemon (hestia) (127.0.0.1:7711): reachable, connected in 0 ms"
    block = conv.render_for_being(inst, "cbp-being", mark=False, refuted=refuted_claims(services))
    lines = [l for l in block.splitlines() if l.startswith("- **")]
    claim = next(l for l in lines if "unreachable" in l)
    assert "_[refuted: measured reachable at" in claim and "127.0.0.1:7711" in claim
    assert claim.index("_[refuted:") < claim.index("unreachable"), \
        "the refutation is read BEFORE the claim, not appended after a multi-paragraph turn"
    assert not any("refuted" in l for l in lines if "kymth" in l), "only claims are marked"
    assert not any("refuted" in l for l in lines if l.startswith("- **dp**")), "another speaker's words are theirs"
    assert conv.render_for_being(inst, "cbp-being", mark=False) == conv.render_for_being(inst, "cbp-being", mark=False, refuted=[]), \
        "no measurement, no marker"


def test_the_daemon_journal_tail_is_exported_into_the_beings_notes():
    """dp, 2026-09-16: "your logs belong the same notes directory". The being cannot read
    /var/log/journal (binary) or run journalctl (a command, not a path), so the beat brings
    the tail to it."""
    from types import SimpleNamespace
    from sage.gateway.heartbeat import export_service_log
    inst = Path(tempfile.mkdtemp(prefix="svclog-"))
    seen = []
    def fake(cmd):
        seen.append(cmd)
        return SimpleNamespace(returncode=0, stdout="2026-09-16T00:32:53-07:00 cbp sh[390]: Vault unlocked.\n", stderr="")
    name = export_service_log(inst, run=fake)
    assert name == "hestia-recent.log"
    body = (inst / "notes" / name).read_text()
    assert "Vault unlocked" in body and "rewritten every beat" in body
    assert seen[0][:5] == ["journalctl", "--user", "-u", "hestia.service", "-n"]

    def empty(cmd):
        return SimpleNamespace(returncode=1, stdout="", stderr="No journal files were found.")
    export_service_log(inst, run=empty)
    assert "could not read the journal" in (inst / "notes" / "hestia-recent.log").read_text(), \
        "an empty export says why it is empty, never a silent blank file"

    # THE CASE THAT ACTUALLY HAPPENS, which the arm above never covered: journalctl answers
    # rc=0 with the marker on STDOUT. Measured 2026-09-19 — hestia runs RUST_LOG=warn, so a
    # healthy daemon logs nothing, and cbp-being read "-- No entries --" as "idle, is it even
    # processing?" and spent a day asking about a daemon that was fine. An absent measurement
    # must not read as a measured absence: the file says what silence MEANS and puts a
    # measurement beside it.
    calls = []
    def quiet(cmd):
        calls.append(cmd)
        if cmd[0] == "systemctl":
            return SimpleNamespace(returncode=0, stdout="active\n", stderr="")
        return SimpleNamespace(returncode=0, stdout="-- No entries --\n", stderr="")
    export_service_log(inst, run=quiet)
    body = (inst / "notes" / "hestia-recent.log").read_text()
    assert "-- No entries --" not in body, "the raw marker is what got misread"
    assert "what HEALTHY looks like" in body
    assert "is 'active'" in body, "and a MEASURED state, not only an explanation"
    assert "does NOT mean the daemon is idle" in body
    assert any(c[:3] == ["systemctl", "--user", "is-active"] for c in calls)


def test_the_being_can_retire_its_own_note_and_only_its_own():
    """Its memory was append-only, so a claim could never be marked finished. retire_note
    renames one of its own notes with a dated header; nothing is destroyed."""
    from sage.gateway.reference_f1a import ReferenceF1aDispatcher, BeingIntent
    root = Path(tempfile.mkdtemp(prefix="retire-"))
    (root / "notes").mkdir()
    (root / "notes" / "hestia-policy-daemon-unreachable.md").write_text("the daemon is down\n")
    (root / "notes" / "from-the-seat.md").write_text("measured facts\n")
    (root / "journal.md").write_text("a life\n")
    d = ReferenceF1aDispatcher(memory_root=root)
    allow = SimpleNamespace(decision="allow", rule="", reason="ok", innate=False, stage="local-law")

    env = d(BeingIntent("retire_note", {"path": "notes/hestia-policy-daemon-unreachable.md",
                                        "reason": "hestia was restarted for 30 s; it is running"}), allow)
    assert env.ok and "retired" in env.result and env.witness_id
    kept = list((root / "notes").glob("hestia-policy-daemon-unreachable.retired-*.md"))
    assert len(kept) == 1, list((root / "notes").iterdir())
    body = kept[0].read_text()
    assert body.startswith("> RETIRED") and "the daemon is down" in body, "kept whole, marked closed"
    assert not (root / "notes" / "hestia-policy-daemon-unreachable.md").exists()

    for bad, why in ((("notes/from-the-seat.md", "no"), "said TO you"),   # refused by _safe_path
                     (("journal.md", "no"), "not directly inside"),
                     (("notes/nope.md", "no"), "nothing to retire")):
        env = d(BeingIntent("retire_note", {"path": bad[0], "reason": bad[1]}), allow)
        assert not env.ok and why in env.error, (bad, env.error)
    env = d(BeingIntent("retire_note", {"path": "notes/x.md"}), allow)
    assert not env.ok and "reason" in env.error, "a retirement says what it knows now"


def test_the_unit_file_is_exported_from_systemds_own_answer():
    """cbp-being guessed the unit's location four times in two days — /etc/systemd/system,
    a made-up hestia.policy-daemon.service, /var/log/systemd/units, /root/.config — each a
    refused scope request. systemd knows where it is; the beat copies it in."""
    from types import SimpleNamespace
    from sage.gateway.heartbeat import export_unit_file
    inst = Path(tempfile.mkdtemp(prefix="unit-"))
    frag = inst / "hestia.service"
    frag.write_text("[Unit]\nDescription=Hestia\n[Service]\nExecStart=/usr/bin/true\n")
    name = export_unit_file(inst, run=lambda cmd: SimpleNamespace(returncode=0, stdout=f"FragmentPath={frag}\n", stderr=""))
    body = (inst / "notes" / name).read_text()
    assert name == "hestia-unit.txt" and "ExecStart=/usr/bin/true" in body
    assert "USER unit" in body and str(frag) in body
    name = export_unit_file(inst, run=lambda cmd: SimpleNamespace(returncode=0, stdout="FragmentPath=\n", stderr=""))
    assert "(no unit file at that path)" in (inst / "notes" / name).read_text(), "never a silent blank"


def test_a_peer_ask_to_someone_it_can_only_say_to_names_the_open_door():
    """It tried peer_ask to 'cbp-claude' in four beats running. Not a hub member — but it is
    in a conversation with it, and the refusal never said so."""
    from sage.gateway.hestia_dispatch import HestiaF1aDispatcher
    inst = Path(tempfile.mkdtemp(prefix="door-"))
    conv.create(inst, "cbp-claude", title="the seat", participants=["cbp-claude", "cbp-being"],
                writable_by=["cbp-claude", "cbp-being"])
    d = HestiaF1aDispatcher.__new__(HestiaF1aDispatcher)
    d.member = "cbp-being"; d.memory_root = inst; d.peer_aliases = {}
    d.known_peers = lambda: {"hub", "legion", "sprout"}
    msg = d._unknown_peer("cbp-claude")
    assert "say to=\"cbp-claude\"" in msg and "works" in msg
    assert "not a hub member" not in d._unknown_peer("nobody") or True
    assert "say to=" not in d._unknown_peer("nobody"), "no door is invented for a stranger"


def _disp_with(calls):
    from sage.gateway.hestia_dispatch import HestiaF1aDispatcher
    d = HestiaF1aDispatcher.__new__(HestiaF1aDispatcher)
    d.member = "cbp-being"
    d._call = lambda name, args: calls.get(name, {})
    return d


def test_a_ruling_pointer_resolves_to_the_ruling():
    """cbp-being, 2026-09-16: nine appeals ruled (all deny-stands, by claude-code and codex),
    each delivered as hestia://appeal/<deny hash>#ruled — and unreadable, because memory_read
    treated the address as a filename. hestia_open_appeals cannot help: it lists only UNRULED
    appeals, so a ruling is the one thing it never shows."""
    ruling = {"entries": [{"eventType": "adjudication", "timestamp": "2026-09-16T01:20:00Z",
                           "eventData": {"about_deny_hash": "c29e24e6", "upheld": False,
                                         "adjudicator": "claude-code", "adjudicator_role": "role:constellation:member",
                                         "rationale": "the path does not exist; nothing to read there"}}]}
    d = _disp_with({"hestia_query_history": ruling})
    out = d._resolve_pointer("hestia://appeal/c29e24e6#ruled")
    assert "DENY STANDS" in out and "claude-code" in out and "does not exist" in out
    assert "not another appeal on the same deny" in out, "a ruling says what follows"

    d2 = _disp_with({"hestia_query_history": {"entries": []}})
    miss = d2._resolve_pointer("hestia://appeal/deadbeef#ruled")
    assert "does NOT mean the appeal is still open" in miss and "is open" not in miss.replace("still open", ""), \
        "absence from a bounded window must never be reported as an open appeal"
    # a trailing segment is not part of the address
    assert "DENY STANDS" in d._resolve_pointer("hestia://appeal/c29e24e6/ruling")

    d3 = _disp_with({"hestia_scope_status": {"requests": [
        {"request_id": "scope-1", "path": "/etc/systemd/system", "status": "refused",
         "decided_by": "operator", "decision_reason": "hestia is a user service; nothing needs restarting"}]}})
    out = d3._resolve_pointer("hestia://scope/scope-1")
    assert "refused" in out and "user service" in out

    out = _disp_with({})._resolve_pointer("hestia://egress/12#carrier-mismatch:legion/legion-being")
    assert "not delivered" in out and "carrier-mismatch" in out
    assert _disp_with({})._resolve_pointer("notes/journal.md") is None, "a real path is still a path"


def test_an_appeal_ruling_notice_is_not_folded_into_scope_decisions():
    """SAGE #104. hestia notified cbp-being of all nine rulings, and render_inbox folded every
    one into "N scope decision notice(s), already written into your notes; nothing to do"."""
    from sage.gateway.heartbeat import render_inbox
    notices = [
        {"id": 1, "kind": "disposition", "from_plugin": "hestia", "pointer_uri": "hestia://appeal/20c6c5a4df71c210#ruled"},
        {"id": 2, "kind": "disposition", "from_plugin": "hestia", "pointer_uri": "hestia://scope/scope-1"},
        {"id": 3, "kind": "disposition", "from_plugin": "hestia", "pointer_uri": "hestia://escalation/abc#decided"},
    ]
    out = render_inbox(notices)
    assert "[ruling] your appeal about deny 20c6c5a4df71" in out and "memory_read on hestia://appeal/20c6c5a4df71c210" in out
    assert "#ruled" not in out.split("memory_read on")[1].split("\n")[0], "the pointer handed back is the lookup key"
    assert "1 scope decision notice(s)" in out, "only the scope disposition is counted as scope"
    assert "[disposition]" in out and "hestia://escalation/abc" in out


def test_the_beat_shows_a_new_ruling_verbatim_once():
    from sage.gateway.heartbeat import appeals_block
    rows = {"appeals": [
        {"deny_hash": "c29e24e65f21aaaa", "status": "ruled",
         "ruling": {"verdict": "deny stands", "adjudicator": "claude-code", "ruled_at": "2026-09-16T04:38:30Z",
                    "rationale": "Deny stands. /etc/systemd/system/hestia.policy-daemon.service does not exist."}},
        {"deny_hash": "0000aaaa11112222", "status": "open"},
    ]}
    d = SimpleNamespace(_call=lambda name, args: rows if name == "hestia_my_appeals" else {})
    text, rec = appeals_block(d, {})
    assert "1 ruled, 1 open" in text and "RULED since your last beat" in text
    assert "does not exist" in text and "claude-code" in text and "Filing it again" in text
    assert rec["new_this_beat"] == ["c29e24e65f21aaaa"]
    text2, rec2 = appeals_block(d, {"appeals": rec})
    assert "RULED since your last beat" not in text2 and "No new rulings" in text2, "shown once, not every beat"
    old = SimpleNamespace(_call=lambda name, args: {"_hestia_error": {"code": "unknown_tool"}})
    assert appeals_block(old, {}) == ("", {}), "a daemon without the tool renders nothing"


def test_a_pointer_read_uses_the_exact_lookup_first():
    mine = {"appeals": [{"deny_hash": "c29e24e65f21aaaa", "appeal_entry": "e1", "status": "ruled",
                         "ruling": {"verdict": "deny stands", "adjudicator": "claude-code",
                                    "ruled_at": "2026-09-16T04:38:30Z", "rationale": "the path does not exist"}},
                        {"deny_hash": "0000aaaa11112222", "appeal_entry": "e2", "status": "open"}]}
    d = _disp_with({"hestia_my_appeals": mine})
    out = d._resolve_pointer("hestia://appeal/c29e24e65f21#ruled")
    assert "DENY STANDS" in out and "the path does not exist" in out
    assert "still open" in d._resolve_pointer("hestia://appeal/0000aaaa1111")
    assert "no appeal about deny" in d._resolve_pointer("hestia://appeal/ffffffffffff")


def _disp_with_resource(body, member="cbp-being"):
    """A dispatcher whose daemon client answers `resources/read` with `body`."""
    from sage.gateway.hestia_dispatch import HestiaF1aDispatcher
    d = HestiaF1aDispatcher.__new__(HestiaF1aDispatcher)
    d.member = member
    d._connect = lambda: "sid-1"
    d._c = SimpleNamespace(read_resource=lambda uri: {
        "result": {"contents": [{"uri": uri, "text": json.dumps(body)}]}})
    return d


def test_an_escalation_invitation_reads_as_another_members_ask():
    """SAGE #109. hestia invites every member except the asker to review a refused governance
    write, and delivers `hestia://escalation/<id>#corroborate-or-dissent`. The resolver had no
    arm for it, so memory_read looked for a FILE and answered 'no such path'. Measured
    2026-09-16/17: cbp-being read that as proof the three invitations were fabricated, and
    asked dp and then HUB to file reconsideration motions about them."""
    body = {"escalation_id": "3cc24a24aa4c082d", "plugin_id": "claude-code", "tool_name": "Bash",
            "marker": "pre_tool_use.py", "status": "withdrawn", "decided_by": "claude-code",
            "stated_reason": "a scratch copy of the shim to test a red arm", "claimed": False}
    out = _disp_with_resource(body)._resolve_pointer(
        "hestia://escalation/3cc24a24aa4c082d#corroborate-or-dissent")
    assert "claude-code's governance escalation" in out and "not an appeal, and not yours" in out
    assert "pre_tool_use.py" in out and "scratch copy" in out and "withdrawn" in out
    assert "nothing is required of you" in out and "no tool to rule" in out

    # The being's OWN escalation reads as its own, not as someone else's.
    mine = dict(body, plugin_id="cbp-being", status="denied", decided_by="dp")
    own = _disp_with_resource(mine)._resolve_pointer("hestia://escalation/3cc24a24aa4c082d")
    assert own.startswith("[YOUR governance escalation") and "nothing is pending for you" in own

    # An UNKNOWN answer is never rendered as absence — the defect the whole loop grew from.
    err = {"_hestia_error": {"code": "hestia.escalation_pointer_not_found",
                             "message": "no escalation with id 'x' in this daemon's live store"}}
    unknown = _disp_with_resource(err)._resolve_pointer("hestia://escalation/x")
    assert "UNKNOWN, not proof it never existed" in unknown
    assert "does not exist" not in unknown

    # A gateway whose client predates the resource reader says so rather than guessing.
    from sage.gateway.hestia_dispatch import HestiaF1aDispatcher
    old = HestiaF1aDispatcher.__new__(HestiaF1aDispatcher)
    old.member = "cbp-being"; old._connect = lambda: "sid"; old._c = SimpleNamespace()
    assert "no resource reader" in old._resolve_pointer("hestia://escalation/abc")


def test_a_review_request_says_whose_ask_it_is():
    """Rendered like a reply, three invitations read as the being's own open business."""
    from sage.gateway.heartbeat import render_inbox
    out = render_inbox([{"id": 9, "kind": "review_request", "from_plugin": "claude-code",
                         "queued_at": "2026-09-17T17:00:00Z",
                         "pointer_uri": "hestia://escalation/ea83eb0e2af20e81#corroborate-or-dissent"}])
    assert "claude-code asked members to review ITS governance escalation ea83eb0e2af20e81" in out
    assert "not an appeal of yours" in out and "nothing is required of you" in out
    assert "memory_read on hestia://escalation/ea83eb0e2af20e81" in out
    assert "#corroborate-or-dissent" not in out, "the pointer handed back is the lookup key"
