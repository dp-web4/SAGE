#!/usr/bin/env python3
"""A/B: does a spoken answer fit? The JSON answer turn on a being's own model, against its recent voice
questions in `room`. Nothing is sent. Outputs are the being's replies to people: write them somewhere PRIVATE.

Arms: C0 (no spoken hint), S1 (hint), S2 (schema maxLength=SPEAK_MAX_CHARS), S1S2 (both, shipped).
Run 2026-09-30, Sprout 2B, 6 questions: C0 2/6 speakable (median 531 chars); S1 6/6 (186); S2 5/6
but cut mid-sentence; S1S2 6/6 (221, max 291).

  python3 -m sage.gateway.experiments.spoken_answer_ab --home <instance> --member sprout-being --out <private.jsonl>
"""
import argparse, copy, json, time, urllib.request
from pathlib import Path
from sage.gateway import heartbeat as hb, conversations as conv, body


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--home", required=True); ap.add_argument("--member", required=True)
    ap.add_argument("--model", default="qwen3.8-distill:2b"); ap.add_argument("--num-ctx", type=int, default=16384)
    ap.add_argument("--questions", type=int, default=6); ap.add_argument("--reps", type=int, default=1)
    ap.add_argument("--out", required=True); ap.add_argument("--host", default="http://127.0.0.1:11434")
    a = ap.parse_args(argv)
    home = Path(a.home)
    voice = [t for t in conv.recent(home, "room", limit=1000) if t.get("from") == "voice" and "?" in t.get("text", "")]
    turns = voice[-a.questions:]
    system = hb.ANSWER_SYSTEM.format(name=a.member.split("-")[0], machine=a.member.split("-")[0], member=a.member)
    capped = copy.deepcopy(hb.ANSWER_SCHEMA); capped["properties"]["message"]["maxLength"] = body.SPEAK_MAX_CHARS
    arms = {"C0": ("", hb.ANSWER_SCHEMA), "S1": (hb.SPOKEN_ASK, hb.ANSWER_SCHEMA),
            "S2": ("", capped), "S1S2": (hb.SPOKEN_ASK, capped)}
    out = open(a.out, "a")
    for rep in range(a.reps):
        for t in turns:
            sel = hb.SelectedTurn("room", t)
            for arm, (extra, fmt) in arms.items():
                p = {"model": a.model, "stream": False, "think": True, "keep_alive": "5m", "format": fmt,
                     "options": {"num_predict": 6000, "temperature": 0.4, "num_ctx": a.num_ctx},
                     "messages": [{"role": "system", "content": system},
                                  {"role": "user", "content": hb.ANSWER_ASK_JSON.format(pending=sel.render()) + extra}]}
                t0 = time.time()
                r = json.load(urllib.request.urlopen(urllib.request.Request(a.host + "/api/chat", json.dumps(p).encode(),
                                                      {"Content-Type": "application/json"}), timeout=600))
                c = (r.get("message") or {}).get("content") or ""
                try:
                    j = json.loads(c)
                except Exception:
                    j = {}
                msg = (j.get("message") or "") if j.get("answer") else ""
                ok = bool(msg) and len(msg) <= body.SPEAK_MAX_CHARS and not conv.is_stub(msg)
                rec = {"arm": arm, "rep": rep, "q": t["text"], "len": len(msg), "speakable": ok,
                       "secs": round(time.time() - t0, 1), "msg": msg}
                out.write(json.dumps(rec) + "\n"); out.flush()
                print(arm, rep, len(msg), "OK" if ok else "--", "|", msg[:100].replace("\n", " "), flush=True)


if __name__ == "__main__":
    main()
