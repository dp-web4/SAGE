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
    assert "`remember` succeeded 1 time(s)" in block and "b9330968" in block
    assert service_contradictions(inst, "cbp-being",
                                  "- long-term memory (membot) (127.0.0.1:8010): NOT reachable (x)") == ""
    (inst / "todo.md").write_text("- [x] tidy notes\n")
    assert service_contradictions(inst, "cbp-being", up) == "", "no claim, no block"
