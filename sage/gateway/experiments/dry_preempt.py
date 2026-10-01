"""Dry run of a beat that is PREEMPTED for a person, on a COPY of the being's home. No model call, no
dispatch, no outside effect: the tool turns and the answer turn are fakes, every pending-set / wake /
egress / successor call is stubbed. Checks the R2 branch end to end through hb.main()."""
import json, sys, time
from types import SimpleNamespace
sys.path.insert(0, sys.argv[1])          # the SAGE checkout under test
# usage: python3 -m ... <sage checkout> <a COPY of a being home>   (never a live home)
from sage.gateway import heartbeat as hb, arousal, being_join, being_tool_loop, egress_drain, conversations as conv
from sage.gateway.being_tool_loop import ToolTurnResult

home = sys.argv[2]
T = time.time()
HEARD = {"kind": "heard", "descriptor": 'heard a voice: "What do you want to remember about today?"',
         "first_ts": T + 3600, "last_ts": T + 3600, "count": 1, "salience": 1.0, "source": "presence:heard",
         "key": f"heard:{T+5}:What do you want to remember about today?"}
calls = {"turns": [], "claims": [], "answer": None}

def claim(beat_id, path=None):
    calls["claims"].append(beat_id)
    return [HEARD] if beat_id.endswith(".preempt") else []
arousal.claim_pending = claim
arousal.peek_pending = lambda path=None: [HEARD] if time.time() >= T else []
arousal.release_claim = lambda *a, **k: None
arousal.after_beat = lambda **k: {"continuing": False, "why": "dry run"}
being_join.consume_wake_marker = lambda *a, **k: {"by": "presence", "descriptor": "dry run"}
hb._phase = lambda *a, **k: None
egress_drain.drain_once = lambda **k: {"dry_run": True}

def fake_turn(client, llm, seed, max_steps=2, tools=None, on_generate=None, should_yield=None):
    why = should_yield() if should_yield else None
    calls["turns"].append({"yield_checked": should_yield is not None, "yielded": why})
    return ToolTurnResult(reply="", yielded=why)
being_tool_loop.run_ollama_tool_turn = fake_turn

def fake_answer(client, llm, selected, **k):
    calls["answer"] = {"cid": selected.cid, "text": selected.text, "woke": selected.woke}
    r = ToolTurnResult(reply="")
    r.answer_form = {"sent": False, "why": "dry run"}
    return r
hb.answer_turn_json = fake_answer

# the person's words, as presence (#309) writes them on arrival
conv.append(__import__("pathlib").Path(home), "room", speaker="voice",
            text="What do you want to remember about today?", via="voice", enforce_write=False,
            extra={"heard_id": "dryrun-1", "mic": "AIRHUG 01"})
cfg = json.load(open(f"{home}/instance.json")); cfg["preempt"] = True; json.dump(cfg, open(f"{home}/instance.json", "w"))
hb.main(["--member", "sprout-being", "--model", "qwen3.8-distill:2b", "--instance", home,
         "--no-hub-drain", "--no-escalate"])
rec = json.loads(open(f"{home}/heartbeats.jsonl").read().splitlines()[-1])
print("\n=== DRY RUN ===")
print("turns:", calls["turns"])
print("claims:", calls["claims"])
print("preempted:", json.dumps(rec.get("preempted"), default=str)[:600])
print("account:", str(rec.get("account"))[:200])
print("reflect ran:", rec.get("reflect") is not None)
print("answer turn on:", calls["answer"])
print("wake classes:", (rec.get("wake") or {}).get("classes"))
