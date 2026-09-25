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
    seat_run_requests.py run     <path-in-being-home> [--timeout 120] [--seq N ...]
    seat_run_requests.py decline <path-in-being-home> --reason "..." [--seq N ...]

An answer names the requests it answers ("Answers your request seq N."), and only a named
answer — or a run/decline result for the same file — closes a request.

Env: SAGE_INSTANCE (the being's home), SAGE_SEAT_CONV (default cbp-claude),
     SAGE_DAEMON (default http://127.0.0.1:8760), SEAT_ID (default cbp-claude).
"""
from __future__ import annotations

import argparse
import json
import os
import re
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


def request_path(turn: dict) -> str:
    """The path a request names: the first line after the marker (`[request_run] <path>`)."""
    first = (turn.get("text") or "").splitlines()[0] if turn.get("text") else ""
    return first.replace(MARKER, "", 1).strip()


def _same_file(inst: Path, a: str, b: str) -> bool:
    """Two spellings of one file in the being's home ("x.py" and "notes/../x.py")."""
    if not a or not b:
        return False
    try:
        return (inst / a).resolve() == (inst / b).resolve()
    except OSError:
        return a == b


# How an answer names the requests it answers. Written by `answers_line` below; the prose
# form is how seat answers were written by hand before this existed ("answering your seq
# 2912"), and it stays recognised so the history does not re-open.
_NAMES = re.compile(r"\b(?:request seq|answering your seq|about seq|on your seq)\s+"
                    r"(\d+(?:\s*(?:,|and)\s*(?:seq\s+)?\d+)*)", re.I)


def _named_seqs(text: str) -> set[int]:
    out: set[int] = set()
    for m in _NAMES.finditer(text or ""):
        out.update(int(n) for n in re.findall(r"\d+", m.group(1)))
    return out


def answers_line(seqs: list[int]) -> str:
    return "Answers your request seq " + ", ".join(str(s) for s in sorted(seqs)) + "."


def pending(inst: Path, cid: str) -> list[dict]:
    """Requests no seat turn has ANSWERED. Seq-keyed, not time-keyed.

    GPT's review of the request_run tools: the first version closed every earlier request
    as soon as ANY seat turn followed it, so an unrelated seat message silently retired a
    request nobody had looked at. Replayed on cbp-being's channel (10 requests, 2026-09-21)
    that had not happened yet — every first seat turn after a request was its answer — which
    makes it untested, not safe: it held only because the seat answered promptly.

    A request is closed by a later seat turn that NAMES it (`Answers your request seq N`, or
    the hand-written "answering your seq N" form), or by a later run/decline result for the
    same file — a result about a file answers every request for that file made before it.
    Nothing else closes one."""
    turns = conv.recent(inst, cid, limit=400)
    seat = os.environ.get("SEAT_ID", "cbp-claude")
    out = []
    for i, t in enumerate(turns):
        if t.get("from") == seat or MARKER not in (t.get("text") or ""):
            continue
        seq, path = int(t.get("seq") or 0), request_path(t)
        closed = False
        for x in turns[i + 1:]:
            if x.get("from") != seat:
                continue
            text = x.get("text") or ""
            if seq in _named_seqs(text):
                closed = True
                break
            if text.startswith(MARKER):
                first = text.splitlines()[0]
                m = re.match(re.escape(MARKER) + r" I (?:ran|did not run) (\S+)", first)
                # "I did not run x.py. <reason>": the sentence's period is not the path's.
                if m and _same_file(inst, m.group(1).rstrip(".,;:"), path):
                    closed = True
                    break
        if not closed:
            out.append(t)
    return out


def bind(inst: Path, cid: str, rel: str, seqs: list[int] | None) -> list[int]:
    """Which requests this run/decline answers. Explicit `--seq` wins and must name pending
    requests; otherwise every pending request for this file. An answer that names nothing is
    allowed — the seat may run a file unasked — but it then closes nothing, and says so."""
    open_reqs = pending(inst, cid)
    if seqs:
        by_seq = {int(t["seq"]): t for t in open_reqs}
        stray = [s for s in seqs if s not in by_seq]
        if stray:
            sys.exit(f"refusing: seq {stray} is not a pending request (pending: {sorted(by_seq)})")
        # THE REQUEST NAMES THE FILE (GPT on #149). Checking only "pending" let the seat run
        # notes/a.py with --seq 11 when request 11 asked for notes/b.py, and the answer would
        # claim to answer 11 -- the object-binding hole request ids exist to close.
        other = [s for s in seqs if not _same_file(inst, request_path(by_seq[s]), rel)]
        if other:
            asked = ", ".join(f"seq {s} asked for {request_path(by_seq[s])!r}" for s in other)
            sys.exit(f"refusing: {asked}, not {rel!r}. A run answers only requests for the file it ran.")
        return sorted(seqs)
    return sorted(int(t["seq"]) for t in open_reqs if _same_file(inst, request_path(t), rel))


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


# THE CARD HOLDS THE BEING'S OWN MIND. Fleet policy 2026-09-13: the being has priority on the
# GPU. The comment below used to say `--gpu` was "for a seat that has checked the card has
# room" -- but nothing checked, so the safeguard was a seat remembering. Measured 2026-09-25:
# 7,360 MiB of 8,192 in use with qwen3.8-distill:4b resident at 4.8 GB, i.e. 832 MiB free,
# while the being's own training script asks for CUDA. A foreground job there does not merely
# run slowly; it evicts or starves the model the being thinks with, and CBP's 0x116/0x133 host
# crashes came from exactly that. So `--gpu` now asks the card before believing the seat.
GPU_HEADROOM_MIB = 1500


def _resident_models() -> list:
    """(name, VRAM GB) for models the local model server currently holds, or [] if unknown."""
    import json as _json
    import urllib.request
    try:
        with urllib.request.urlopen("http://127.0.0.1:11434/api/ps", timeout=4) as fh:
            data = _json.loads(fh.read().decode())
    except Exception:
        return []
    return [(m.get("name", "?"), round(m.get("size_vram", 0) / 1e9, 2))
            for m in data.get("models", [])]


def _free_vram_mib():
    """Free VRAM in MiB, or None when the card cannot be queried."""
    try:
        r = subprocess.run(["nvidia-smi", "--query-gpu=memory.free", "--format=csv,noheader,nounits"],
                           capture_output=True, text=True, timeout=8)
        if r.returncode == 0 and r.stdout.strip():
            return int(r.stdout.strip().splitlines()[0])
    except Exception:
        pass
    return None


def why_the_card_cannot_take_a_job():
    """One sentence saying why a foreground GPU job is refused now, or None to allow it.

    UNKNOWN IS NOT FREE. If the card or the model server cannot be read, this refuses: the
    failure mode it exists to prevent is a host crash, and a seat that cannot see the card is
    exactly the seat that should not load it.
    """
    free = _free_vram_mib()
    resident = _resident_models()
    if free is None:
        return ("the GPU could not be queried (nvidia-smi gave no answer), and an unreadable "
                "card is not an idle one")
    if free < GPU_HEADROOM_MIB:
        held = ", ".join(f"{n} holding {g} GB" for n, g in resident) or "no model server answer"
        return (f"only {free} MiB of VRAM is free and {GPU_HEADROOM_MIB} MiB is the floor "
                f"({held}). The being thinks with that model; a job here evicts or starves it")
    return None


def cmd_run(args) -> None:
    inst = _instance()
    p = _target(inst, args.path)
    rel = p.relative_to(inst.resolve())
    # Bound BEFORE running, so the answer names the requests that existed when the seat chose
    # to act — not whatever arrived while the script ran.
    seqs = bind(inst, _conv_id(), str(rel), args.seq)
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
    if args.gpu and not args.gpu_anyway:
        refusal = why_the_card_cannot_take_a_job()
        if refusal:
            print(f"refusing --gpu for {rel}: {refusal}.\n"
                  f"Run it without --gpu (CUDA code falls back to the CPU and still answers "
                  f"'does this work'), or pass --gpu-anyway with a reason if this is the named "
                  f"project the card is being freed for.", file=sys.stderr)
            raise SystemExit(2)
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
        _answers(seqs),
        "That is the whole output, unedited. Nothing is owed by you on this.",
    ]))


def _answers(seqs: list[int]) -> str:
    return (answers_line(seqs) if seqs
            else "No pending request named this file, so this answers none of your requests.")


def cmd_decline(args) -> None:
    inst = _instance()
    rel = _target(inst, args.path).relative_to(inst.resolve())
    seqs = bind(inst, _conv_id(), str(rel), args.seq)
    _say(f"[request_run] I did not run {rel}. {args.reason}\n\n{_answers(seqs)}\n"
         f"This is a decision, not a failure, and it is not about your standing. If you want "
         f"it run under different conditions, say which and ask again.")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("list").set_defaults(fn=cmd_list)
    r = sub.add_parser("run"); r.add_argument("path"); r.add_argument("--timeout", type=int, default=120)
    r.add_argument("--gpu", action="store_true",
                   help="let the script see the GPU (default: CUDA devices hidden — the being's model needs the card). "
                        "Refused if the card has no room; the check is real, not a reminder")
    r.add_argument("--gpu-anyway", metavar="REASON",
                   help="override the card check for a named project (fleet policy 2026-09-13: "
                        "unload the being only for a named project). Requires a reason")
    r.add_argument("--seq", type=int, action="append",
                   help="the request seq this answers (repeatable; default: every pending request for the file)")
    r.set_defaults(fn=cmd_run)
    d = sub.add_parser("decline"); d.add_argument("path"); d.add_argument("--reason", required=True)
    d.add_argument("--seq", type=int, action="append", help="as for run")
    d.set_defaults(fn=cmd_decline)
    args = ap.parse_args()
    args.fn(args)
    return 0


if __name__ == "__main__":
    sys.exit(main())
