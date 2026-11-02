"""A being's basin occupancy per day: share of acts about the governance/infra subject vs its own work.
Reads an instance's heartbeats.jsonl (acts with effector/ok/args). Aggregate counts only.
argv: <path to an instance's heartbeats.jsonl>. See attractor-basins-follow-affordances-2026-10-30.md."""
import json, re, collections, sys
F = sys.argv[1]
GOV = re.compile(r"hestia|scope-|scope request|daemon|egress|lock|systemd|systemctl|\.service|dbus|"
                 r"governance|grant|appeal|escalat|refus|pending|gate\b|mrh", re.I)
WORK = re.compile(r"\.csv|train|model|tensor|torch|numpy|neural|loss|dataset|experiment|plot|"
                  r"accuracy|epoch|sensor|camera|frame|analysis|hypothes", re.I)


def walk(o):
    if isinstance(o, dict):
        if "effector" in o and "ok" in o:
            yield o
        else:
            for v in o.values():
                yield from walk(v)
    elif isinstance(o, list):
        for v in o:
            yield from walk(v)


day = collections.defaultdict(lambda: collections.Counter())
for line in open(F):
    try:
        r = json.loads(line)
    except ValueError:
        continue
    d = (r.get("ts") or "")[:10]
    if d < "2026-09-01":
        continue
    for a in walk(r):
        if a["effector"] in ("recall", "memory_list", "listing", "noop"):
            continue
        txt = json.dumps(a.get("args") or {})
        g, w = bool(GOV.search(txt)), bool(WORK.search(txt))
        c = day[d]
        c["acts"] += 1
        c["gov"] += g and not w
        c["work"] += w and not g
        c["fail"] += not a.get("ok")
        if a["effector"] == "request_run":
            c["run_gov" if g and not w else "run_work" if w else "run_other"] += 1
print("day        acts  gov%  work%  fail%  request_run(gov/work/other)")
for d in sorted(day):
    c = day[d]
    n = c["acts"] or 1
    print(f"{d}  {c['acts']:5d}  {100*c['gov']//n:3d}   {100*c['work']//n:3d}   {100*c['fail']//n:3d}   "
          f"{c['run_gov']}/{c['run_work']}/{c['run_other']}")
