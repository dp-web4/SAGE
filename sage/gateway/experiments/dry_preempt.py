"""Dry run of hb.main() for PREEMPTION, on a COPY of a being's home (never a live home). No model call, no
dispatch, no outside effect: tool turns, the account generate and the answer turn are fakes; the pending set,
wake marker, egress and successor are stubbed. A person "arrives" at a chosen moment of the beat:

  none     nobody speaks                                   -> not preempted, reflection runs
  a        right after the beat's first claim (GPT on #310: before the record's later t0)
  b        while the account generate is in flight
  c        while reflection is in flight

usage: python3 dry_preempt.py <sage checkout> <COPY of a being home> <scenario>"""
import json, sys, time
from pathlib import Path
sys.path.insert(0, sys.argv[1])
from sage.gateway import heartbeat as hb, arousal, being_join, being_tool_loop, egress_drain, governed_turn, conversations as conv
from sage.gateway.being_tool_loop import ToolTurnResult

home, case = Path(sys.argv[2]), sys.argv[3]
WORDS = "What do you want to remember about today?"
state = {"arrived": None, "claims": [], "turns": [], "answer": None, "account_calls": 0}


def arrive():
    """A person speaks now: presence writes the room turn (#309) and the pending set holds the event."""
    if state["arrived"] is None:
        state["arrived"] = time.time()
        conv.append(home, "room", speaker="voice", text=WORDS, via="voice", enforce_write=False,
                    extra={"heard_id": f"dry-{case}", "mic": "AIRHUG 01"})


def event():
    t = state["arrived"]
    return {"kind": "heard", "descriptor": f'heard a voice: "{WORDS}"', "first_ts": t, "last_ts": t,
            "count": 1, "salience": 1.0, "source": "presence:heard", "key": f"heard:{t}:{WORDS}"}


def claim(beat_id, path=None):
    state["claims"].append(beat_id)
    if beat_id.endswith(".preempt"):
        return [event()] if state["arrived"] else []
    if case == "a":
        arrive()                      # lands right after the first claim
    return []


arousal.claim_pending = claim
arousal.peek_pending = lambda path=None: [event()] if state["arrived"] else []
arousal.release_claim = lambda *a, **k: None
arousal.after_beat = lambda **k: {"continuing": False, "why": "dry run"}
being_join.consume_wake_marker = lambda *a, **k: {"by": "presence", "descriptor": "dry run"}
hb._phase = lambda *a, **k: None
egress_drain.drain_once = lambda **k: {"dry_run": True}
REFLECT = set(hb.REFLECT_TOOLS)


def fake_turn(client, llm, seed, max_steps=2, tools=None, on_generate=None, should_yield=None, act_form="tools"):
    names = {t["function"]["name"] for t in (tools or [])}
    phase = "reflect" if names and names <= REFLECT else "explore/posture"
    if phase == "reflect" and case == "c":
        arrive()                      # lands while reflection is generating
    why = should_yield() if should_yield else None
    state["turns"].append({"phase": phase, "yield_checked": should_yield is not None, "yielded": why})
    return ToolTurnResult(reply="", yielded=why)


being_tool_loop.run_ollama_tool_turn = fake_turn
_build = governed_turn.build_client


def build(*a, **k):
    client, llm = _build(*a, **k)

    def account(messages, tools=None, fmt=None):
        state["account_calls"] += 1
        if case == "b":
            arrive()                  # lands while the account generate is in flight
        return {"content": "(dry run account)", "tool_calls": [], "raw": {"done_reason": "stop"}}
    llm.get_chat_response = account
    return client, llm


governed_turn.build_client = build


def fake_answer(client, llm, selected, **k):
    state["answer"] = {"cid": selected.cid, "text": selected.text, "woke": selected.woke}
    r = ToolTurnResult(reply="")
    r.answer_form = {"sent": False, "why": "dry run"}
    return r


hb.answer_turn_json = fake_answer
cfg = json.loads((home / "instance.json").read_text())
cfg.update(preempt=True, answer_turn="json")
(home / "instance.json").write_text(json.dumps(cfg))
hb.main(["--member", "sprout-being", "--model", "qwen3.8-distill:2b", "--instance", str(home),
         "--no-hub-drain", "--no-escalate"])
rec = json.loads((home / "heartbeats.jsonl").read_text().splitlines()[-1])
pre = rec.get("preempted") or {}
print(json.dumps({"case": case, "preempted_phase": pre.get("phase"), "selected": pre.get("selected"),
                  "late_events": len(pre.get("events") or []), "account": {k: v for k, v in (rec.get("account") or {}).items() if k in ("skipped", "error")},
                  "account_calls": state["account_calls"], "turns": state["turns"],
                  "reflect_ran": any(t["phase"] == "reflect" for t in state["turns"]),
                  "answer": state["answer"], "claims": state["claims"]}, default=str))
