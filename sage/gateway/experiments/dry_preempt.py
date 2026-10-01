"""Dry run of hb.main() for PREEMPTION, on a COPY of a being's home (never a live home). No model call, no
dispatch, no outside effect: tool turns, the account generate and the answer turn are fakes; the wake marker
and egress are stubbed; the PENDING SET IS REAL but lives in a scratch file; arming a successor is stubbed to
FAIL, so whatever is still pending at the end is exactly what a successor would have to recover.

  none     nobody speaks                                   -> not preempted, reflection runs
  a        a person speaks right after the beat's first claim (before the record's later t0)
  b        a person speaks while the account generate is in flight
  c        a person speaks while reflection is in flight
  d        during the account: a person AND a sense event  -> answer the person; the sense stays pending
  e        during the account: two people's lines          -> answer one; the other stays pending

usage: python3 dry_preempt.py <sage checkout> <COPY of a being home> <scenario>"""
import json, os, sys, tempfile, time
from pathlib import Path

PENDING = Path(tempfile.mkdtemp(prefix="dry-pending-")) / "pending_events.json"
os.environ["SAGE_PENDING_EVENTS"] = str(PENDING)          # before arousal is imported
sys.path.insert(0, sys.argv[1])
from sage.gateway import heartbeat as hb, arousal, being_join, being_tool_loop, egress_drain, governed_turn  # noqa
from sage.gateway import conversations as conv  # noqa: E402
from sage.gateway.being_tool_loop import ToolTurnResult  # noqa: E402

home, case = Path(sys.argv[2]), sys.argv[3]
LINES = ["What do you want to remember about today?", "And what would you forget?"]
state = {"arrived": False, "turns": [], "answer": None, "account_calls": 0}


def speak_in_room(words, n):
    """A person speaks: presence writes the room turn (#309) and requests a beat (the real pending set)."""
    t = time.time()
    conv.append(home, "room", speaker="voice", text=words, via="voice", enforce_write=False,
                extra={"heard_id": f"dry-{case}-{n}", "mic": "AIRHUG 01"})
    arousal.add_pending("heard", f'heard a voice: "{words}"', salience=1.0, key=f"heard:{t}:{words[:80]}",
                        source="presence:heard")


def arrive():
    if state["arrived"]:
        return
    state["arrived"] = True
    speak_in_room(LINES[0], 0)
    if case == "d":
        arousal.add_pending("sense", "strong motion to the upper left", salience=0.5, source="presence:sense")
    if case == "e":
        time.sleep(0.05)
        speak_in_room(LINES[1], 1)


_claim = arousal.claim_pending


def claim(beat_id, path=None):
    got = _claim(beat_id, path)
    if case == "a" and not beat_id.endswith(".preempt"):
        arrive()                      # lands right after the first claim
    return got


arousal.claim_pending = claim
arousal.after_beat = lambda **k: {"armed": False, "continuing": False, "error": "dry run: arming FAILED"}
being_join.consume_wake_marker = lambda *a, **k: {"by": "presence", "descriptor": "dry run"}
hb._phase = lambda *a, **k: None
egress_drain.drain_once = lambda **k: {"dry_run": True}
REFLECT = set(hb.REFLECT_TOOLS)


def fake_turn(client, llm, seed, max_steps=2, tools=None, on_generate=None, should_yield=None, act_form="tools"):
    names = {t["function"]["name"] for t in (tools or [])}
    phase = "reflect" if names and names <= REFLECT else "explore/posture"
    if phase == "reflect" and case == "c":
        arrive()
    why = should_yield() if should_yield else None
    state["turns"].append({"phase": phase, "yielded": why})
    return ToolTurnResult(reply="", yielded=why)


being_tool_loop.run_ollama_tool_turn = fake_turn
_build = governed_turn.build_client


def build(*a, **k):
    client, llm = _build(*a, **k)

    def account(messages, tools=None, fmt=None):
        state["account_calls"] += 1
        if case in ("b", "d", "e"):
            arrive()
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
still = [dict(v, key=k) for k, v in (json.loads(PENDING.read_text()) if PENDING.exists() else {}).items()]
print(json.dumps({"case": case, "preempted_phase": pre.get("phase"), "selected": pre.get("selected"),
                  "claimed_late": [e.get("descriptor") for e in pre.get("events") or []],
                  "left_pending_count": pre.get("left_pending"),
                  "still_pending_after_beat": [f'{e["kind"]}: {e["descriptor"]}' for e in still],
                  "reflect_ran": any(t["phase"] == "reflect" for t in state["turns"]),
                  "answer": state["answer"]}, default=str))
