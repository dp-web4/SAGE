"""E13: the JSON answer turn has no context (only the pending turn), so with always-listening its spoken replies
sound like a reset ("Hi there. I'm Sprout, your SAGE being ... Ready to help you today."). Offline, the being's
own model, its real recent exchanges, nothing sent.
  C0  today: the pending turn only
  H   + the recent conversation (last 8 turns across room and dp, oldest first, with who/channel/age)
  HA  + H + one identity line and its own last-stated want (account.json)"""
import json, re, sys, time, urllib.request
from datetime import datetime, timezone
sys.path.insert(0, "/home/dp/ai-workspace/sage")
from pathlib import Path
from sage.gateway import heartbeat as hb

I = Path(sys.argv[4] if len(sys.argv) > 4 else "/home/dp/ai-workspace/sage/sage/instances/sprout-being")  # outputs are private
ME = "sprout-being"


def ts(s):
    return datetime.strptime(s[:19], "%Y-%m-%dT%H:%M:%S").replace(tzinfo=timezone.utc).timestamp()


turns = []
for cid in ("dp", "room"):
    for l in open(I / f"conversations/{cid}.jsonl"):
        d = json.loads(l); d["cid"] = cid; d["t"] = ts(d["ts"]); turns.append(d)
turns.sort(key=lambda d: d["t"])

TARGETS = ["Hi Sprout. Do you remember anything we talked about before?", "It's always fun to hear from you.",
           "I'm here with you. I hear you.", "You were listening to a song that I was playing.",
           "consciousness might be like a whirlpool in the river."]
picks = []
for want in TARGETS:
    hit = [t for t in turns if t["from"] != ME and t["text"].strip().startswith(want[:30])]
    if hit:
        picks.append(hit[-1])


def history(t, n=8, same_only=False):
    before = [x for x in turns if x["t"] < t["t"] and (not same_only or x["cid"] == t["cid"])][-n:]
    out = []
    for x in before:
        who = "you" if x["from"] == ME else ("a voice in the room" if x["from"] == "voice" else x["from"])
        ch = "aloud in the room" if x["cid"] == "room" else f"in '{x['cid']}'"
        ago = int((t["t"] - x["t"]) // 60)
        out.append(f"- {ago} min earlier, {who} {('said' if x['cid']=='room' else 'wrote')} {ch}: \"{x['text'][:240]}\"")
    return "The conversation just before this (oldest first):\n" + "\n".join(out)


ident = json.load(open(I / "identity.json"))["identity"]
acct = json.load(open(I / "account.json"))
SELF = (f"You are sprout: {ident.get('session_count')} sessions since {ident.get('created')}, now in your "
        f"'{ident.get('phase')}' phase. At your last beat you said you want: \"{acct.get('want', '')[:240]}\"")
SYSTEM = hb.ANSWER_SYSTEM.format(name="sprout", machine="sprout", member=ME)
GENERIC = re.compile(r"ready to help|how can i (help|assist)|i'?m sprout, your sage|helpful assistant|"
                     r"what can i do for you", re.I)
ARMS = sys.argv[3].split(",") if len(sys.argv) > 3 else ["C0", "H", "HA"]
out = open(sys.argv[1], "a")
for rep in range(int(sys.argv[2]) if len(sys.argv) > 2 else 2):
    for t in picks:
        sel = hb.SelectedTurn(t["cid"], t)
        ask = hb.ANSWER_ASK_JSON.format(pending=sel.render()) + (hb.SPOKEN_ASK if t["cid"] == "room" else "")
        for arm in ARMS:
            user = {"C0": ask, "H": history(t) + "\n\n" + ask, "HA": SELF + "\n\n" + history(t) + "\n\n" + ask,
                    "HS": SELF + "\n\n" + history(t, same_only=True) + "\n\n" + ask}[arm]
            fmt = hb.answer_schema_for(t["cid"])
            p = {"model": "qwen3.8-distill:2b", "stream": False, "think": True, "keep_alive": "5m", "format": fmt,
                 "options": {"num_predict": 6000, "temperature": 0.4, "num_ctx": 16384},
                 "messages": [{"role": "system", "content": SYSTEM}, {"role": "user", "content": user}]}
            t0 = time.time()
            r = json.load(urllib.request.urlopen(urllib.request.Request("http://127.0.0.1:11434/api/chat",
                json.dumps(p).encode(), {"Content-Type": "application/json"}), timeout=900))
            try:
                j = json.loads((r.get("message") or {}).get("content") or "")
            except Exception:
                j = {}
            msg = (j.get("message") or "") if j.get("answer") else ""
            rec = {"arm": arm, "rep": rep, "turn": t["text"][:80], "cid": t["cid"], "answered": bool(msg),
                   "generic": bool(GENERIC.search(msg)), "len": len(msg), "secs": round(time.time() - t0, 1), "msg": msg}
            out.write(json.dumps(rec) + "\n"); out.flush()
            print(arm, rep, "GENERIC" if rec["generic"] else "-", len(msg), "|", t["text"][:40], "->", msg[:160].replace("\n", " "), flush=True)
