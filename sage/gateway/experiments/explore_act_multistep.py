"""E11b: the whole explore turn in JSON act form, multi-step, on the REAL seed and the being's own model.
The gate is a FAKE that executes nothing and answers every act with "(not executed: offline test)".
Measures: acts per turn, how the turn ends (done / rest / cap), repeats, time.
usage: multistep.py <sage checkout> <seed.json> <out.jsonl> [runs]"""
import json, sys, time, urllib.request
sys.path.insert(0, sys.argv[1])
from sage.gateway.being_tool_loop import run_ollama_tool_turn
from sage.gateway.being_gate_client import ResultEnvelope
from sage.gateway.tests.test_being_tool_loop import _client

d = json.load(open(sys.argv[2]))
from sage.gateway.being_gate_client import ollama_tools
d["tools"] = ollama_tools([t["function"]["name"] for t in d["tools"]])   # the checkout's own specs
runs = int(sys.argv[4]) if len(sys.argv) > 4 else 3


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
for i in range(runs):
    t = time.time()
    r = run_ollama_tool_turn(_client(NOT_RUN), LLM(), d["seed"], max_steps=3, tools=d["tools"], act_form="json")
    acts = [(it.effector, dict(it.args or {})) for it, _ in r.trace]
    end = "rest" if r.rested is not None else "cap" if r.capped else "done"
    rec = {"run": i, "secs": round(time.time() - t, 1), "acts": acts, "end": end, "reply": (r.reply or "")[:300],
           "steps": r.steps, "generates": len(r.generates)}
    out.write(json.dumps(rec, default=str) + "\n"); out.flush()
    print(i, end, f"{rec['secs']}s", [a for a, _ in acts], "|", (r.reply or "")[:120].replace("\n", " "), flush=True)
