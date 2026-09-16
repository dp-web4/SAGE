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
    assert "no journal entries" in (inst / "notes" / "hestia-recent.log").read_text(), \
        "an empty export says why it is empty, never a silent blank file"


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
