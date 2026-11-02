import sys, json
sys.path.insert(0, "/home/dp/ai-workspace/SAGE")
from sage.gateway import relevance as R

inst = "/home/dp/ai-workspace/SAGE/sage/instances/cbp-qwen3.8-distill-4b"
turns = [json.loads(l) for l in open(inst + "/conversations/dp.jsonl") if l.strip()]
posture = open("/home/dp/ai-workspace/private-context/beings/cbp-being/posture.md").read().split("\n\n")
settled = json.load(open(inst + "/settled.json"))["entries"]
texts = ([("dp:" + str(t["seq"]), t["text"]) for t in turns[:-1]]
         + [("posture:%d" % i, p) for i, p in enumerate(posture)]
         + [("settled:" + e["id"], e["question"] + " " + e["answer"]) for e in settled])
cls = [c for c in vars(R).values() if isinstance(c, type) and hasattr(c, "related")][0]
coll = cls([t for _, t in texts])
for q in ("why do you need hestia?  why do you need to access 7711?",
          "we talked earlier today.  check your memory and your logs."):
    hits = coll.related(q, threshold=0.2)[:8]
    print("Q:", q)
    for s, i in hits:
        print("  %.2f %s | %s" % (s, texts[i][0], texts[i][1][:90].replace("\n", " ")))
    print("  hits:", len(coll.related(q, threshold=0.2)))
