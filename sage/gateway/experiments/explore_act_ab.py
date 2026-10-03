"""E11: explore's first act as a native tool call (A, today) vs one closed JSON object (B).
The being's REAL explore seed (captured from a copy of its home) and its own model. Nothing is executed.

usage: explore_ab.py <seed.json> <out.jsonl> [reps]"""
import json, re, sys, time, urllib.request
sys.path.insert(0, "/home/dp/ai-workspace/sage")
from sage.gateway.being_tool_loop import salvage_tool_calls

d = json.load(open(sys.argv[1]))
seed, tools = d["seed"], d["tools"]
reps = int(sys.argv[3]) if len(sys.argv) > 3 else 6
names = [t["function"]["name"] for t in tools]
req = {t["function"]["name"]: list((t["function"].get("parameters") or {}).get("required") or []) for t in tools}
msgs = [{k: m[k] for k in ("role", "content", "images") if k in m} for m in seed]
OPTS = {"num_ctx": 16384, "num_predict": 3000, "temperature": 0.4}
PLACEHOLDER = re.compile(r"^\s*[\[<{].*[\]>}]\s*$|placeholder|your_|example\.|\.\.\.$", re.I)

ASK_B = ("Choose ONE thing to do now, as one of your tools. Reply as JSON: "
         '{"act": "<tool name>", "args": {<that tool\'s arguments>}, "why": "one short sentence"}. '
         'If nothing needs doing, choose "rest".')
ASK_B2 = ("Choose ONE thing to do now, as one of your tools. Reply as JSON: "
          '{"act": "<tool name>", "why": "one short sentence"}. If nothing needs doing, choose "rest".')
SCHEMA_B2 = {"type": "object", "properties": {"act": {"type": "string", "enum": names},
             "why": {"type": "string"}}, "required": ["act", "why"]}
SCHEMA_B = {"type": "object", "properties": {"act": {"type": "string", "enum": names},
            "args": {"type": "object"}, "why": {"type": "string"}}, "required": ["act", "args", "why"]}


def chat(payload):
    t = time.time()
    r = json.load(urllib.request.urlopen(urllib.request.Request(
        "http://127.0.0.1:11434/api/chat", json.dumps(payload).encode(), {"Content-Type": "application/json"}),
        timeout=900))
    return r, round(time.time() - t, 1)


def args_ok(act, args):
    if not isinstance(args, dict):
        return False
    missing = [k for k in req.get(act, []) if not str(args.get(k, "")).strip()]
    fake = [k for k, v in args.items() if isinstance(v, str) and PLACEHOLDER.search(v)]
    return not missing and not fake


ARMS = sys.argv[4].split(",") if len(sys.argv) > 4 else ["A", "B"]
spec = {t["function"]["name"]: t["function"].get("parameters") or {"type": "object"} for t in tools}
out = open(sys.argv[2], "a")
for rep in range(reps):
    for arm in ARMS:
        p = {"model": "qwen3.8-distill:2b", "stream": False, "think": True, "keep_alive": "5m", "options": OPTS}
        if arm == "A":
            p.update(messages=msgs, tools=tools)
        elif arm == "B2":
            p.update(messages=msgs + [{"role": "user", "content": ASK_B2}], format=SCHEMA_B2)
        else:
            p.update(messages=msgs + [{"role": "user", "content": ASK_B}], format=SCHEMA_B)
        r, secs = chat(p)
        m = r.get("message") or {}
        content = m.get("content") or ""
        rec = {"arm": arm, "rep": rep, "secs": secs, "prompt_tokens": r.get("prompt_eval_count"),
               "eval": r.get("eval_count"), "content": content[:600]}
        if arm == "A":
            calls = m.get("tool_calls") or []
            how = "native"
            if not calls and content:
                calls = salvage_tool_calls(content, tools); how = "salvaged"
            acts = [((c.get("function") or {}).get("name"), (c.get("function") or {}).get("arguments")) for c in calls]
            acts = [(n, json.loads(a) if isinstance(a, str) else a) for n, a in acts]
            rec.update(form=how if calls else "none", acts=acts,
                       valid=bool(acts) and all(n in names and args_ok(n, a) for n, a in acts))
        elif arm == "B2":
            try:
                j = json.loads(content); parsed = True
            except Exception:
                j, parsed = {}, False
            act = j.get("act")
            args = {}
            if act in spec:
                p2 = dict(p, messages=p["messages"] + [{"role": "assistant", "content": content},
                          {"role": "user", "content": f"Now the arguments for {act}, as JSON."}], format=spec[act])
                r2, s2 = chat(p2); secs += s2
                try:
                    args = json.loads((r2.get("message") or {}).get("content") or "")
                except Exception:
                    args = {}
            rec.update(form="json2" if parsed else "unparsed", acts=[(act, args)], why=j.get("why", ""),
                       valid=parsed and act in names and args_ok(act, args), secs=secs)
        else:
            try:
                j = json.loads(content); parsed = True
            except Exception:
                j, parsed = {}, False
            act, args = j.get("act"), j.get("args")
            rec.update(form="json" if parsed else "unparsed", acts=[(act, args)], why=j.get("why", ""),
                       valid=parsed and act in names and args_ok(act, args))
        out.write(json.dumps(rec, default=str) + "\n"); out.flush()
        print(arm, rep, rec["form"], "valid" if rec["valid"] else "--", rec["acts"], f"{secs}s",
              "|", content[:90].replace("\n", " "), flush=True)
