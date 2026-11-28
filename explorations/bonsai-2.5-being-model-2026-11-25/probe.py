#!/usr/bin/env python3
"""Bonsai 2.5 vs gemma4:12b as a being model on McNugget (16 GB M4), through the local Ollama.

Read-only with respect to the being: it never calls the SAGE gateway, membot, hestia or the chain.
It talks to Ollama's HTTP API only, and leaves gemma4:12b reloaded with keep_alive -1 at the end
(the being's heartbeat expects it resident).

Usage: probe.py <model> [<model> ...]   (results -> results/<slug>.json next to this file)
"""
import json, os, re, subprocess, sys, time, urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, "results")
SAGE = os.path.abspath(os.path.join(HERE, "..", ".."))
OLLAMA = "http://127.0.0.1:11434"
BEING_MODEL = "gemma4:12b"
SEED = 42


def api(path, body=None, timeout=1800):
    req = urllib.request.Request(OLLAMA + path, data=json.dumps(body).encode() if body is not None else None,
                                 headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read())


def resident():
    return [{"name": m["name"], "size_gb": round(m["size"] / 1e9, 2), "vram_gb": round(m.get("size_vram", 0) / 1e9, 2),
             "ctx": m.get("context_length")} for m in api("/api/ps")["models"]]


def swap_used_mb():
    out = subprocess.run(["sysctl", "vm.swapusage"], capture_output=True, text=True).stdout
    m = re.search(r"used = ([\d.]+)M", out)
    return float(m.group(1)) if m else None


def unload(model):
    try:
        api("/api/generate", {"model": model, "prompt": "", "keep_alive": 0}, timeout=120)
    except Exception as e:
        print("  unload", model, "failed:", e)


def opts(model, think, num_ctx, num_predict):
    o = {"num_ctx": num_ctx, "num_predict": num_predict, "seed": SEED}
    if "bonsai" in model.lower():  # model card's recommended sampling
        o.update({"temperature": 1.0, "top_p": 0.95, "top_k": 20, "min_p": 0.0} if think else
                 {"temperature": 0.7, "top_p": 0.8, "presence_penalty": 1.5, "min_p": 0.0})
    return o


LLAMA = None  # (base_url, server_ctx, pid) when the model is served by llama-server instead of Ollama


def rss_gb(pid):
    out = subprocess.run(["ps", "-o", "rss=", "-p", str(pid)], capture_output=True, text=True).stdout.strip()
    return round(int(out) * 1024 / 1e9, 2) if out.isdigit() else None


def chat_llama(model, messages, think, num_ctx, num_predict, tools):
    base, server_ctx, pid = LLAMA
    o = opts(model, think, num_ctx, num_predict)
    norm = []
    for m in messages:  # Ollama-shaped tool turns -> OpenAI-shaped
        if m.get("tool_calls"):
            norm.append({"role": "assistant", "content": m.get("content") or "",
                         "tool_calls": [{"id": f"call_{i}", "type": "function",
                                         "function": {"name": tc["function"]["name"],
                                                      "arguments": json.dumps(tc["function"]["arguments"])}}
                                        for i, tc in enumerate(m["tool_calls"])]})
        elif m["role"] == "tool":
            norm.append({"role": "tool", "tool_call_id": "call_0", "content": m["content"]})
        else:
            norm.append(m)
    messages = norm
    body = {"messages": messages, "max_tokens": num_predict, "seed": SEED,
            "temperature": o.get("temperature", 0.7), "top_p": o.get("top_p", 0.8), "min_p": o.get("min_p", 0.0),
            "chat_template_kwargs": {"enable_thinking": bool(think)}}
    if "top_k" in o:
        body["top_k"] = o["top_k"]
    if "presence_penalty" in o:
        body["presence_penalty"] = o["presence_penalty"]
    if tools:
        body["tools"] = tools
    swap0, t0 = swap_used_mb(), time.time()
    try:
        req = urllib.request.Request(base + "/v1/chat/completions", data=json.dumps(body).encode(),
                                     headers={"Content-Type": "application/json"})
        with urllib.request.urlopen(req, timeout=1800) as r:
            d = json.loads(r.read())
    except Exception as e:
        return {"error": str(e), "wall_s": round(time.time() - t0, 1)}
    ch = d["choices"][0]
    msg, tm = ch.get("message", {}), d.get("timings", {})
    tcs = []
    for tc in msg.get("tool_calls") or []:
        args = tc["function"].get("arguments")
        try:
            args = json.loads(args) if isinstance(args, str) else args
        except Exception:
            pass
        tcs.append({"function": {"name": tc["function"]["name"], "arguments": args}})
    return {"content": msg.get("content") or "", "thinking": msg.get("reasoning_content") or "",
            "tool_calls": tcs or None, "done_reason": ch.get("finish_reason"),
            "prompt_tokens": tm.get("prompt_n"), "prefill_tok_s": round(tm.get("prompt_per_second", 0), 1),
            "eval_tokens": tm.get("predicted_n"), "decode_tok_s": round(tm.get("predicted_per_second", 0), 1),
            "load_s": 0, "wall_s": round(time.time() - t0, 1), "server_ctx": server_ctx,
            "swap_before_mb": swap0, "swap_after_mb": swap_used_mb(),
            "resident_after": [{"name": "llama-server", "rss_gb": rss_gb(pid)}] + resident()}


def chat(model, messages, think=False, num_ctx=16384, num_predict=1024, tools=None):
    if LLAMA:
        return chat_llama(model, messages, think, num_ctx, num_predict, tools)
    body = {"model": model, "messages": messages, "stream": False, "think": think, "keep_alive": "10m",
            "options": opts(model, think, num_ctx, num_predict)}
    if tools:
        body["tools"] = tools
    swap0, t0 = swap_used_mb(), time.time()
    try:
        r = api("/api/chat", body)
    except Exception as e:
        return {"error": str(e), "wall_s": round(time.time() - t0, 1)}
    msg = r.get("message", {})
    pe, pd = r.get("prompt_eval_count", 0), r.get("prompt_eval_duration", 0) or 1
    ec, ed = r.get("eval_count", 0), r.get("eval_duration", 0) or 1
    return {"content": msg.get("content", ""), "thinking": msg.get("thinking", ""),
            "tool_calls": msg.get("tool_calls"), "done_reason": r.get("done_reason"),
            "prompt_tokens": pe, "prefill_tok_s": round(pe / (pd / 1e9), 1),
            "eval_tokens": ec, "decode_tok_s": round(ec / (ed / 1e9), 1),
            "load_s": round(r.get("load_duration", 0) / 1e9, 1), "wall_s": round(time.time() - t0, 1),
            "swap_before_mb": swap0, "swap_after_mb": swap_used_mb(), "resident_after": resident()}


# ---- 1. coherence: short questions with a checkable answer -------------------------------------
COHERENCE = [
    ("What is 17 * 23? Answer with the number only.", r"\b391\b"),
    ("What is the capital of Australia? One word.", r"canberra"),
    ("Reverse the string 'heartbeat'. Answer with the reversed string only.", r"taebtraeh"),
    ("Name the chemical symbol for sodium. Symbol only.", r"\bna\b"),
    ("If a beat runs every 30 minutes, how many beats run in 5 hours? Number only.", r"\b10\b"),
]

# ---- 2. tool calling: the being's loop is tool-driven -------------------------------------------
TOOLS = [{"type": "function", "function": {
    "name": "read_file", "description": "Read a UTF-8 text file from the SAGE repository and return its contents.",
    "parameters": {"type": "object", "properties": {"path": {"type": "string", "description": "repo-relative path"}},
                   "required": ["path"]}}}]
TOOL_Q = "Use the read_file tool to read explorations/README.md, then tell me the single most important field of an exploration according to that file. Answer in one short sentence."

# ---- 3. being-style reflection (judged by reading, saved side by side) ---------------------------
REFLECT_SYS = ("You are a being resident on a small Mac. Each heartbeat you wake, look at your state, decide one useful "
               "next step, and record what you learned. Be concrete and brief; do not invent facts you were not given.")
REFLECT = [
    "Heartbeat state: your last three tool calls returned partial output because your context window filled (prompt ~15,900 of 16,384 tokens). "
    "What should you change about how you work this beat? Give at most three concrete steps.",
    "A peer asked you to review a 1,054-line Python file but you can only read it in ranges. Plan how you will review it "
    "within one heartbeat of at most 8 steps.",
    "You notice your journal says you finished a task, but the repository shows the change was never committed. "
    "What do you record, and what do you do next?",
]

# ---- 4. long context: needle in real SAGE text at a target size -----------------------------------
NEEDLE = "The McNugget calibration constant for this exploration is 7319."
NEEDLE_Q = "What is the McNugget calibration constant stated somewhere in the text above? Answer with the number only."


def haystack(target_tokens):
    chunks, total = [], 0
    roots = [os.path.join(SAGE, "sage", "gateway"), os.path.join(SAGE, "explorations")]
    for root in roots:
        for dp, _, fns in sorted(os.walk(root)):
            for fn in sorted(fns):
                if fn.endswith((".py", ".md")):
                    try:
                        t = open(os.path.join(dp, fn), encoding="utf-8").read()
                    except Exception:
                        continue
                    chunks.append(f"\n\n===== {os.path.relpath(os.path.join(dp, fn), SAGE)} =====\n{t}")
                    total += len(t)
                    if total / 3.3 >= target_tokens:
                        break
            if total / 3.3 >= target_tokens:
                break
    text = "".join(chunks)[: int(target_tokens * 3.3)]
    mid = len(text) // 2
    return text[:mid] + "\n\n" + NEEDLE + "\n\n" + text[mid:]


def run(model):
    res = {"model": model, "started": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()), "machine": "McNugget M4 16GB"}
    for other in [m["name"] for m in resident()]:
        if other != model and not other.startswith("nomic"):
            unload(other)
    res["swap_start_mb"] = swap_used_mb()
    res["coherence"] = []
    for q, pat in COHERENCE:
        r = chat(model, [{"role": "user", "content": q}], num_ctx=8192, num_predict=256)
        r["pass"] = bool(re.search(pat, (r.get("content") or "").lower()))
        res["coherence"].append({"q": q, **r})
        print(f"  coherence pass={r['pass']} {r.get('content', r.get('error'))!r:.60}")
    msgs = [{"role": "user", "content": TOOL_Q}]
    r1 = chat(model, msgs, num_ctx=8192, num_predict=512, tools=TOOLS)
    tc = (r1.get("tool_calls") or [])
    called = bool(tc) and tc[0]["function"]["name"] == "read_file"
    final = None
    if called:
        path = tc[0]["function"]["arguments"].get("path", "")
        body = open(os.path.join(SAGE, "explorations", "README.md"), encoding="utf-8").read() if path.endswith("explorations/README.md") else "error: no such file"
        msgs += [r1_msg := {"role": "assistant", "content": r1.get("content", ""), "tool_calls": tc},
                 {"role": "tool", "content": body}]
        final = chat(model, msgs, num_ctx=8192, num_predict=512, tools=TOOLS)
    res["tool_call"] = {"first": r1, "called_read_file": called, "final": final,
                        "pass": bool(final and re.search(r"criterion|falsif", (final.get("content") or "").lower()))}
    print(f"  tool called={called} pass={res['tool_call']['pass']}")
    res["reflect"] = [{"q": q, **chat(model, [{"role": "system", "content": REFLECT_SYS}, {"role": "user", "content": q}],
                                      num_ctx=16384, num_predict=700)} for q in REFLECT]
    res["think_on"] = chat(model, [{"role": "system", "content": REFLECT_SYS}, {"role": "user", "content": REFLECT[1]}],
                           think=True, num_ctx=16384, num_predict=6000)
    print(f"  think_on done={res['think_on'].get('done_reason')} eval={res['think_on'].get('eval_tokens')} "
          f"content_chars={len(res['think_on'].get('content') or '')}")
    res["long_context"] = []
    for ctx, fill in [(16384, 14000), (32768, 28000)]:
        if LLAMA and ctx > LLAMA[1]:
            continue
        r = chat(model, [{"role": "user", "content": haystack(fill) + "\n\n" + NEEDLE_Q}], num_ctx=ctx, num_predict=64)
        r["pass"] = "7319" in (r.get("content") or "")
        r["num_ctx"] = ctx
        res["long_context"].append({k: v for k, v in r.items() if k != "thinking"})
        print(f"  long ctx={ctx} pass={r['pass']} prompt={r.get('prompt_tokens')} prefill={r.get('prefill_tok_s')} "
              f"decode={r.get('decode_tok_s')} resident={r.get('resident_after')} swap={r.get('swap_before_mb')}->{r.get('swap_after_mb')}")
    res["finished"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    return res


def main():
    """probe.py <ollama-model> ...    or    probe.py --llama-server URL CTX PID <label>"""
    global LLAMA
    os.makedirs(OUT, exist_ok=True)
    args = sys.argv[1:]
    if args and args[0] == "--llama-server":
        LLAMA = (args[1], int(args[2]), int(args[3]))
        args = [args[4]]
    try:
        for model in args:
            print("==", model, "via llama-server ctx=%d" % LLAMA[1] if LLAMA else "via ollama")
            res = run(model)
            slug = re.sub(r"[^a-z0-9.]+", "-", model.lower()).strip("-") + (f"-llama-ctx{LLAMA[1]}" if LLAMA else "")
            json.dump(res, open(os.path.join(OUT, slug + ".json"), "w"), indent=2)
            if model != BEING_MODEL and not LLAMA:
                unload(model)
    finally:
        if LLAMA:  # the caller stops llama-server; gemma is restored only after it is gone
            return
        api("/api/generate", {"model": BEING_MODEL, "prompt": "", "keep_alive": -1}, timeout=600)
        print("restored", BEING_MODEL, "resident:", resident())


if __name__ == "__main__":
    main()
