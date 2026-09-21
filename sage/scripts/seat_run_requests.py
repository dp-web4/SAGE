#!/usr/bin/env python3
"""The seat's half of `request_run`: see what the being asked to have run, run it, answer.

dp, 2026-09-21: "ship a request-run instead, where it passes the request to the seat for
evaluation, and it's up to the seat whether to run it, and provide feedback/diags/etc."

The being cannot execute what it writes, so before this existed it asked people in prose —
six times to dp in two hours for one file — and, getting no answer, wrote a note headed
"Fix" whose "Verification" section asserted an outcome it had never observed. `request_run`
gives it a door; this is what is on the other side of the door.

NOTHING HERE IS AUTOMATIC. `list` shows what is waiting; `run` and `decline` are separate
acts a seat takes deliberately, because the decision to execute a file a 4B just wrote is
the whole point of routing this through a seat rather than granting it `run`. An
auto-runner would be the unconfined capability dp ruled against, with extra steps.

Usage:
    seat_run_requests.py list
    seat_run_requests.py run     <path-in-being-home> [--timeout 120]
    seat_run_requests.py decline <path-in-being-home> --reason "..."

Env: SAGE_INSTANCE (the being's home), SAGE_SEAT_CONV (default cbp-claude),
     SAGE_DAEMON (default http://127.0.0.1:8760), SEAT_ID (default cbp-claude).
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import urllib.error
import urllib.request
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO))

from sage.gateway import conversations as conv  # noqa: E402

MARKER = "[request_run]"
OUT_CAP = 3000          # per stream, in the reply


def _instance() -> Path:
    raw = os.environ.get("SAGE_INSTANCE")
    if not raw:
        sys.exit("SAGE_INSTANCE is not set (the being's home). No default: this script must "
                 "never guess which being it is answering.")
    p = Path(raw)
    if not p.is_dir():
        sys.exit(f"SAGE_INSTANCE={raw} is not a directory")
    return p


def _conv_id() -> str:
    return os.environ.get("SAGE_SEAT_CONV", "cbp-claude")


def pending(inst: Path, cid: str) -> list[dict]:
    """Requests with no seat turn after them. Seq-keyed, not time-keyed: a request answered
    once stays answered, and one the seat has not reached stays visible however old."""
    turns = conv.recent(inst, cid, limit=400)
    seat = os.environ.get("SEAT_ID", "cbp-claude")
    out = []
    for i, t in enumerate(turns):
        if t.get("from") == seat or MARKER not in (t.get("text") or ""):
            continue
        if any(x.get("from") == seat for x in turns[i + 1:]):
            continue
        out.append(t)
    return out


def _target(inst: Path, raw: str) -> Path:
    """Resolve inside the being's home. The being's path check is not trusted a second time:
    this process is the one that will execute, so it does its own."""
    p = (inst / raw).resolve() if not os.path.isabs(raw) else Path(raw).resolve()
    if not (p == inst.resolve() or inst.resolve() in p.parents):
        sys.exit(f"refusing: {p} is outside the being's home {inst.resolve()}")
    if not p.is_file():
        sys.exit(f"refusing: {p} is not a file")
    return p


def _say(text: str) -> None:
    body = json.dumps({"from": os.environ.get("SEAT_ID", "cbp-claude"), "message": text}).encode()
    url = f"{os.environ.get('SAGE_DAEMON', 'http://127.0.0.1:8760')}/conversations/{_conv_id()}/say"
    req = urllib.request.Request(url, data=body, headers={"Content-Type": "application/json"})
    try:
        r = json.load(urllib.request.urlopen(req, timeout=30))
        print(f"answered: seq {r.get('turn', {}).get('seq')}")
    except (urllib.error.URLError, OSError) as e:
        # The being must not be told something landed that did not.
        sys.exit(f"could not post the answer ({e}). The being has NOT been told; nothing was "
                 f"recorded as delivered. Re-run once the daemon is reachable.")


def cmd_list(args) -> None:
    inst = _instance()
    reqs = pending(inst, _conv_id())
    if not reqs:
        print("no unanswered run requests")
        return
    for t in reqs:
        print(f"--- seq {t['seq']}  {t['ts']}")
        print("    " + "\n    ".join((t.get("text") or "").splitlines()))


# What the receipt may claim is what the seat DID, not where the code ran. Hiding the devices is
# a request honoured by CUDA runtimes (PyTorch prints "Using device: cpu" under it — measured
# on CBP 2026-09-21), not a boundary: code that opens the device another way is not stopped.
# GPT on #148: "on the CPU" claimed an observation nobody made. A true CPU-only run needs an
# execution boundary that denies device access (a cgroup/container), which this is not.
WHERE_HIDDEN = ("with the GPU hidden from it (CUDA_VISIBLE_DEVICES was empty), "
                "to keep the card for your own model")
WHERE_GPU = "with the GPU visible to it"


def child_env(gpu: bool) -> dict:
    """The environment the being's code runs under: the seat's own, with CUDA devices hidden
    unless the seat chose `--gpu`."""
    env = dict(os.environ)
    if not gpu:
        env["CUDA_VISIBLE_DEVICES"] = ""
    return env


def cmd_run(args) -> None:
    inst = _instance()
    p = _target(inst, args.path)
    rel = p.relative_to(inst.resolve())
    interp = [sys.executable] if p.suffix == ".py" else ["bash"]
    # GPU HIDDEN, BY DEFAULT. The being shares this GPU with its own model. Measured on CBP
    # 2026-09-21: a beat holds the card at ~88-90% of 8 GB, and a model left resident after a
    # beat plus a foreground GPU load crashed the host twice (0x116, 0x133). At 06:43Z the
    # being rewrote its training script in PyTorch and it printed "Using device: cuda" — the
    # next run past its line-26 bug would have started training on that same card, possibly
    # beside its own resident model. A request to RUN code is a request to check that it works;
    # with the devices hidden, CUDA code falls back to the CPU and answers that question without
    # loading the card. That covers the measured path, not every path (see WHERE_HIDDEN).
    # `--gpu` is the deliberate, visible exception, for a seat that has checked the card has room.
    env = child_env(args.gpu)
    try:
        r = subprocess.run(interp + [str(p)], cwd=str(inst), capture_output=True,
                           text=True, timeout=args.timeout, env=env)
        rc, out, err, timed = r.returncode, r.stdout, r.stderr, False
    except subprocess.TimeoutExpired as e:
        rc, out, err, timed = None, (e.stdout or ""), (e.stderr or ""), True

    def block(name: str, s: str) -> str:
        s = (s or "").rstrip()
        if not s:
            return f"{name}: (empty)"
        clipped = s[-OUT_CAP:]
        head = f"{name} (last {OUT_CAP} chars of {len(s)}):" if len(s) > OUT_CAP else f"{name}:"
        return head + "\n" + clipped

    verdict = (f"timed out after {args.timeout}s — no exit code, so this is not a pass or a fail"
               if timed else f"exit code {rc}")
    print(f"ran {rel}: {verdict}")
    _say("\n".join([
        f"[request_run] I ran {rel} {WHERE_GPU if args.gpu else WHERE_HIDDEN}. {verdict}.",
        "",
        block("stdout", out),
        "",
        block("stderr", err),
        "",
        "That is the whole output, unedited. Nothing is owed by you on this.",
    ]))


def cmd_decline(args) -> None:
    inst = _instance()
    rel = _target(inst, args.path).relative_to(inst.resolve())
    _say(f"[request_run] I did not run {rel}. {args.reason}\n\n"
         f"This is a decision, not a failure, and it is not about your standing. If you want "
         f"it run under different conditions, say which and ask again.")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("list").set_defaults(fn=cmd_list)
    r = sub.add_parser("run"); r.add_argument("path"); r.add_argument("--timeout", type=int, default=120)
    r.add_argument("--gpu", action="store_true",
                   help="let the script see the GPU (default: CUDA devices hidden — the being's model needs the card)")
    r.set_defaults(fn=cmd_run)
    d = sub.add_parser("decline"); d.add_argument("path"); d.add_argument("--reason", required=True)
    d.set_defaults(fn=cmd_decline)
    args = ap.parse_args()
    args.fn(args)
    return 0


if __name__ == "__main__":
    sys.exit(main())
