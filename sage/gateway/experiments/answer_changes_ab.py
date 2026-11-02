#!/usr/bin/env python3
"""A/B the recent-changes line in the JSON answer turn, on a being's own model and real turns.
Nothing is sent; outputs are the being's replies to a person, so write them somewhere PRIVATE.
Run for SAGE (answer knows what changed), 2026-09-27, Sprout 2B: gated line in the user turn ->
4/6 named real changes, 0/6 invented (baseline 0/12 named, invented every time)."""
import json, re, subprocess, sys, time, urllib.request
import argparse
ap = argparse.ArgumentParser(description="A/B: the recent-changes line in the answer turn (nothing is sent)")
ap.add_argument("--home", required=True); ap.add_argument("--member", required=True)
ap.add_argument("--model", default="qwen3.8-distill:2b"); ap.add_argument("--conv", default="dp")
ap.add_argument("--seqs", default="76,67"); ap.add_argument("--reps", type=int, default=6); ap.add_argument("--out", required=True)
A = ap.parse_args()
from pathlib import Path
from sage.gateway import heartbeat as hb
I = Path(A.home)
LINE = hb.recent_changes(I)
turns = {t["seq"]: t for t in (json.loads(l) for l in open(I / f"conversations/{A.conv}.jsonl"))}
sysC = hb.ANSWER_SYSTEM.format(name=A.member.split("-")[0], machine=A.member.split("-")[0], member=A.member)
REAL = re.compile(r"\bspeak|aloud|my voice|hear (spoken|words|you)|clock|local time|\broom\b|conversation", re.I)
INVENT = re.compile(r"palette|colou?r|font|version \d|interface|brighter|warmer tones|calibration", re.I)
def chat(msgs):
    p = {"model": A.model, "messages": msgs, "stream": False, "think": True, "keep_alive": "5m",
         "format": hb.ANSWER_SCHEMA, "options": {"num_predict": 6000, "temperature": 0.4, "num_ctx": 8192}}
    r = json.load(urllib.request.urlopen(urllib.request.Request("http://127.0.0.1:11434/api/chat", json.dumps(p).encode(), {"Content-Type": "application/json"}), timeout=600))
    return r.get("message", {}).get("content") or ""
out = open(A.out, "w")
print("LINE:", LINE)
for seq in [int(x) for x in A.seqs.split(",")]:
    sel = hb.SelectedTurn(A.conv, turns[seq]); gated = hb.asks_about_change(sel.text)
    print("Q:", sel.text[:70], "| gate:", gated)
    for rep in range(A.reps):
        while subprocess.run(["systemctl","--user","is-active","sage-heartbeat.service"],capture_output=True,text=True).stdout.strip() in ("active","activating"): time.sleep(15)
        user = "\n\n".join(p for p in ((LINE if gated else ""), hb.ANSWER_ASK_JSON.format(pending=sel.render())) if p)
        c = chat([{"role": "system", "content": sysC}, {"role": "user", "content": user}])
        try: j = json.loads(c)
        except Exception: j = {}
        msg = (j.get("message") or "") if j.get("answer") else ""
        rec = {"q": seq, "rep": rep, "gated": gated, "real": bool(REAL.search(msg)), "invented": bool(INVENT.search(msg)), "msg": msg}
        out.write(json.dumps(rec) + "\n"); out.flush()
        print(rep, "REAL" if rec["real"] else "    ", "INVENT" if rec["invented"] else "      ", "|", msg[:230].replace("\n", " "), flush=True)
