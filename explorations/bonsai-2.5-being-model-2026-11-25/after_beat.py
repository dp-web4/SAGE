#!/usr/bin/env python3
"""Wait until the being's in-flight heartbeat records its end, then run run_bonsai.py in the quiet gap.

A beat that starts while Bonsai is served loads gemma4:12b next to llama-server and the GPU runs out of
memory (seen 2026-11-25 20:36Z). Beats run 10-30 min and start 40-60 min apart, so the gap after a
beat ends is the window. Usage: after_beat.py <t0 of the in-flight beat> <run_bonsai args...>
"""
import json, os, subprocess, sys, time

HB = os.path.join(os.path.expanduser(os.environ.get(
    "SAGE_INSTANCE_DIR", "~/repos/SAGE/sage/instances/mcnugget-being")), "heartbeats.jsonl")
HERE = os.path.dirname(os.path.abspath(__file__))
def t0s():
    out = []
    with open(HB) as f:
        for line in f.readlines()[-5:]:
            try:
                out.append(float(json.loads(line).get("t0", 0)))
            except Exception:
                pass
    return out


# "next": wait for the next beat (one not yet recorded) to record its end
want = None if sys.argv[1] == "next" else float(sys.argv[1])
seen = set(t0s())
while True:
    now = t0s()
    done = any(abs(t - want) < 1 for t in now) if want is not None else any(t not in seen for t in now)
    if done:
        break
    time.sleep(30)
print(time.strftime("%FT%TZ", time.gmtime()), "beat", want, "recorded its end; starting Bonsai run", flush=True)
subprocess.run([sys.executable, "-I", "-u", os.path.join(HERE, "run_bonsai.py"), *sys.argv[2:]])
