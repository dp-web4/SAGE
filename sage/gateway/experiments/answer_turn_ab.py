#!/usr/bin/env python3
"""A/B the answer turn offline: tool call (A) vs JSON {answer, message} with the beat's extra
material (B) vs JSON with only the pending turn and the ask (C). NOTHING IS SENT.

Inputs are real and read-only: a pending turn from the being's own conversations (the heartbeat's
selector, or --seq in --conv), its own recent reflect prose (for A/B's "earlier this beat"), the
heartbeat's ANSWER_SYSTEM/ANSWER_ASK/ANSWER_ASK_JSON, and its model settings. Outputs are the
being's words in reply to a real person's message, so write them somewhere PRIVATE.

Classification uses SAGE's own guards (is_stub, echo_of); "on topic" is a human judgement and is
not computed here.

  python3 -m sage.gateway.experiments.answer_turn_ab --home <instance> --member sprout-being \\
      --model qwen3.8-distill:2b --reps 2 --out /private/path/answer_turn_ab.jsonl

Run for SAGE #237 on 2026-09-27 (Sprout, 2B): A 0/8 calls, B 8/8 (~4 on topic), C 8/8 (~7).
"""
import argparse, json, subprocess, time, urllib.request
from pathlib import Path

from sage.gateway import heartbeat as hb, conversations as conv
from sage.gateway.being_gate_client import ollama_tools


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--home", required=True); ap.add_argument("--member", required=True)
    ap.add_argument("--model", required=True); ap.add_argument("--reps", type=int, default=2)
    ap.add_argument("--conv"); ap.add_argument("--seq", type=int)
    ap.add_argument("--arms", default="A,B,C"); ap.add_argument("--out", required=True)
    ap.add_argument("--host", default="http://127.0.0.1:11434")
    a = ap.parse_args(argv)
    home = Path(a.home)
    if a.conv and a.seq:
        t = [x for x in conv.recent(home, a.conv, limit=10000) if int(x.get("seq", 0)) == a.seq][0]
        sel = hb.SelectedTurn(a.conv, t)
    else:
        sel = hb.pending_selection(home, a.member)[4]
    assert sel is not None, "nothing pending; pass --conv and --seq"
    words = []
    for line in reversed(open(home / "heartbeats.jsonl").readlines()[-60:]):
        w = ((json.loads(line).get("reflect") or {}).get("reply") or "").strip()
        if len(w) > 120 and not conv.is_stub(w) and w not in words:
            words.append(w)
        if len(words) == 4:
            break
    system = hb.ANSWER_SYSTEM.format(name=a.member.split("-")[0], machine=a.member.split("-")[0], member=a.member)

    def chat(messages, tools=None, fmt=None):
        p = {"model": a.model, "messages": messages, "stream": False, "think": True, "keep_alive": "5m",
             "options": {"num_predict": 6000, "temperature": 0.4, "num_ctx": 8192}}
        if tools: p["tools"] = tools
        if fmt: p["format"] = fmt
        req = urllib.request.Request(a.host + "/api/chat", json.dumps(p).encode(), {"Content-Type": "application/json"})
        t0 = time.time()
        return json.load(urllib.request.urlopen(req, timeout=600)).get("message") or {}, round(time.time() - t0, 1)

    def idle():
        while subprocess.run(["systemctl", "--user", "is-active", "sage-heartbeat.service"],
                             capture_output=True, text=True).stdout.strip() in ("active", "activating"):
            time.sleep(15)

    def classify(text):
        t = (text or "").strip()
        return ("silent" if not t else "placeholder" if conv.is_stub(t)
                else "echo" if conv.echo_of(home, sel.cid, a.member, t) is not None else "sent")

    class R:
        def __init__(self, reply): self.reply = reply

    arms = a.arms.split(",")
    out = open(a.out, "a")
    for rep in range(a.reps):
        for wi, w in enumerate(words or [""]):
            tool_ask = hb.ANSWER_ASK.format(pending=sel.render(), target=sel.cid, words=hb._prior_words(R(w)))
            json_ask_b = tool_ask[: tool_ask.index("You have not answered yet.")] + \
                hb.ANSWER_ASK_JSON[hb.ANSWER_ASK_JSON.index("You have not answered yet."):]
            for arm in arms:
                if arm == "C" and wi > 0:
                    continue            # C ignores the prior words; one run per rep is enough
                idle()
                if arm == "A":
                    m, secs = chat([{"role": "system", "content": system},
                                    {"role": "user", "content": "You called no tools this beat.\n\n" + tool_ask}],
                                   tools=ollama_tools(["say"]))
                    say = [c["function"]["arguments"] for c in (m.get("tool_calls") or [])
                           if c.get("function", {}).get("name") == "say"]
                    text = (say[0].get("text") if say and isinstance(say[0], dict) else "") or ""
                    outcome = classify(text) if say else ("prose-only" if (m.get("content") or "").strip() else "silent")
                else:
                    user = ("You called no tools this beat.\n\n" + json_ask_b) if arm == "B" \
                        else hb.ANSWER_ASK_JSON.format(pending=sel.render())
                    m, secs = chat([{"role": "system", "content": system}, {"role": "user", "content": user}],
                                   fmt=hb.ANSWER_SCHEMA)
                    try:
                        j = json.loads(m.get("content") or "{}")
                    except Exception:
                        j = {}
                    text = (j.get("message") or "") if j.get("answer") else ""
                    outcome = classify(text) if j.get("answer") else ("silent" if j else "unparsed")
                rec = {"arm": arm, "rep": rep, "w": wi, "secs": secs, "outcome": outcome,
                       "text": text, "content": (m.get("content") or "")[:600], "pending_seq": sel.seq}
                out.write(json.dumps(rec) + "\n"); out.flush()
                print(arm, rep, wi, secs, outcome, "|", (text or rec["content"])[:120].replace("\n", " "), flush=True)


if __name__ == "__main__":
    main()
