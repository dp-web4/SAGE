"""E18 (GPT on #322): transport recovery vs prompted agency. One explore step on the being's REAL seed, its own
model, a fake gate that executes nothing.
  N0  native tool call, seed as is (today)
  N1  native tool call + the SAME neutral ask the JSON arm uses (the prompt's own effect)
  J1  JSON act form (its ask is that same sentence)
usage: e18_control.py <sage checkout> <seed.json> <out.jsonl> [reps]"""
import json, sys, time, urllib.request
sys.path.insert(0, sys.argv[1])
from sage.gateway.being_tool_loop import run_ollama_tool_turn, ACT_ASK_JSON
from sage.gateway.being_gate_client import ResultEnvelope
from sage.gateway.tests.test_being_tool_loop import _client

d = json.load(open(sys.argv[2]))
reps = int(sys.argv[4]) if len(sys.argv) > 4 else 6
for t in d["tools"]:
    if t["function"]["name"] == "say":
        t["function"]["parameters"]["properties"]["to"]["enum"] = ["dp", "room", "sprout-claude"]


class LLM:
    num_ctx = 16384

    def resolve_num_predict(self):
        return 3000

    def get_chat_response(self, messages, tools=None, fmt=None):
        p = {"model": "qwen3.8-distill:2b", "stream": False, "think": True, "keep_alive": "5m", "messages": messages,
             "options": {"num_ctx": 16384, "num_predict": 3000, "temperature": 0.4}}
        if tools:
            p["tools"] = tools
        if fmt:
            p["format"] = fmt
        r = json.load(urllib.request.urlopen(urllib.request.Request(
            "http://127.0.0.1:11434/api/chat", json.dumps(p).encode(), {"Content-Type": "application/json"}), timeout=900))
        m = r.get("message") or {}
        return {"content": m.get("content") or "", "tool_calls": m.get("tool_calls") or [], "raw": r}


NOT_RUN = lambda intent, v: ResultEnvelope(ok=True, result="(not executed: offline test)", witness_id="offline")
out = open(sys.argv[3], "a")
for rep in range(reps):
    for arm in ("N0", "N1", "J1"):
        seed = list(d["seed"]) + ([{"role": "user", "content": ACT_ASK_JSON}] if arm == "N1" else [])
        t = time.time()
        r = run_ollama_tool_turn(_client(NOT_RUN), LLM(), seed, max_steps=1, tools=d["tools"],
                                 act_form="json" if arm == "J1" else "tools")
        acts = [(it.effector, dict(it.args or {})) for it, _ in r.trace]
        rec = {"arm": arm, "rep": rep, "acted": bool(acts), "acts": acts, "salvaged": len(r.salvaged or []),
               "reply": (r.reply or "")[:200], "arg_failures": getattr(r, "json_arg_failures", []),
               "secs": round(time.time() - t, 1)}
        out.write(json.dumps(rec, default=str) + "\n"); out.flush()
        print(arm, rep, "ACT" if acts else "-", [a for a, _ in acts], f"{rec['secs']}s", "|",
              (r.reply or "")[:90].replace("\n", " "), flush=True)
