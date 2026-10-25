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
    seat_run_requests.py pause   [--minutes 120] [--reason "..."]   (prints the holder token)
    seat_run_requests.py resume
    seat_run_requests.py status
    seat_run_requests.py run    <path-in-being-home> [--timeout 120] [--seq N ...] [-- <script args>]
      (a long answer is posted whole; the being's beat shows CONV_TURN_CHARS of it, head and tail)
    seat_run_requests.py decline <path-in-being-home> --reason "..." [--seq N ...]

An answer names the requests it answers ("Answers your request seq N."), and only a named
answer — or a run/decline result for the same file — closes a request.

WHO ANSWERS (dp, 2026-10-16): mesh wakes answer beings by default. A seat that wants to talk to
the being directly runs `pause`, which stops new wakes for the conversation and makes `run` and
`decline` refuse any session not holding the printed token (SEAT_PAUSE_TOKEN). `resume` hands the
conversation back; the pause also expires on its own.

Env: SAGE_INSTANCE (the being's home), SAGE_SEAT_CONV (default cbp-claude),
     SAGE_DAEMON (default http://127.0.0.1:8760), SEAT_ID (default: the seat conversation's id),
     SEAT_PAUSE_TOKEN (the token `pause` printed; only the pausing seat has it).
"""
from __future__ import annotations

import argparse
import contextlib
import fcntl
import hashlib
import time
import json
import os
import re
import shlex
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
    # The being's conversation with ITS seat is named for the seat (legion-being's is
    # `legion-claude`). The default was the literal "cbp-claude" on every machine, so a seat that
    # set neither variable read CBP's conversation id and found none of its own requests. SAGE_SEAT
    # is the fleet's name for the seat; the literal stays last only so CBP, which may set
    # neither yet, keeps working.
    return (os.environ.get("SAGE_SEAT_CONV") or os.environ.get("SAGE_SEAT") or "cbp-claude").strip()


def _seat_id() -> str:
    """Who the seat speaks as. The default was the literal "cbp-claude" while the conversation id
    already fell back through SAGE_SEAT_CONV/SAGE_SEAT; on Sprout, with SEAT_ID unset, `pending`
    counted sprout-claude's own answers as requests and `_say` was refused by `writable_by`. A
    being's seat conversation is named for its seat, so the seat id falls back to that name."""
    return (os.environ.get("SEAT_ID") or _conv_id()).strip()


# ONE ANSWERER AT A TIME. `list` then `run` was read-then-act with no lock: two seat processes
# (an interactive seat and a mesh wake, sprout 2026-10-16, seq 996-997) both saw request 995
# pending and both ran it. Run and decline now hold this lock from binding the request to posting
# the answer, so the second one binds after the first has answered and finds nothing pending.
LOCK_WAIT_S = 90.0


@contextlib.contextmanager
def answering_lock(inst: Path, cid: str, wait: float | None = None):
    path = inst / "conversations" / f".{cid}.answering.lock"
    path.parent.mkdir(parents=True, exist_ok=True)
    wait = LOCK_WAIT_S if wait is None else wait
    with open(path, "a+") as fh:
        deadline = time.monotonic() + wait
        while True:
            try:
                fcntl.flock(fh, fcntl.LOCK_EX | fcntl.LOCK_NB)
                break
            except BlockingIOError:
                if time.monotonic() >= deadline:
                    sys.exit(f"refusing: another seat process has been answering {cid} for over "
                             f"{wait:.0f}s. Nothing was run or posted; `list` again when it is done.")
                time.sleep(0.2)
        try:
            yield
        finally:
            fcntl.flock(fh, fcntl.LOCK_UN)


def check_pause_holder(inst: Path, cid: str) -> None:
    """Refuse a session that is not the one that paused this conversation's wakes."""
    pause = conv.wake_pause(inst, cid)
    if pause and os.environ.get("SEAT_PAUSE_TOKEN", "") != pause.get("token"):
        sys.exit(f"refusing: {pause.get('by')} has paused wakes for {cid} since {pause.get('since')} "
                 f"(until {pause.get('until')}) and is answering the being itself"
                 f"{': ' + pause['reason'] if pause.get('reason') else ''}. Nothing was run or "
                 f"posted. Policy (dp, 2026-10-16): while a seat holds the pause, other sessions "
                 f"stand down.")


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
    same file — a result about a file answers every request for that file made before it,
    except one newer than every seq the result names. Nothing else closes one."""
    turns = conv.recent(inst, cid, limit=400)
    seat = _seat_id()
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
            named = _named_seqs(text)
            if seq in named:
                closed = True
                break
            # A result never closes a request NEWER than every seq it names. Measured 2026-09-27
            # on cbp-being: the seat declined seq 4068 (an old sha) as superseded by seq 4069
            # (the file edited since); the same-file rule below closed 4069 too, and the answer
            # the decline promised could no longer be posted through this script. Older
            # same-file requests still close: answers naming only the latest re-ask have always
            # relied on that (replayed: 50+ historical requests reopen without it).
            if text.startswith(MARKER) and not (named and seq > max(named)):
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


def _window_cap() -> int:
    """How many chars of one LIVE turn the being's beat shows. Anything longer is cut in the
    MIDDLE (conversations._shown_text keeps 2/5 head, 3/5 tail). The record keeps the whole turn;
    only what the being sees per beat is bounded."""
    try:
        from sage.gateway.heartbeat import CONV_TURN_CHARS  # noqa: E402  (0.05 s, measured)
        return int(CONV_TURN_CHARS)
    except Exception:  # pragma: no cover - the constant moved; the measured value on 2026-09-28
        return 1200


def as_shown(text: str, cap: int | None = None) -> tuple[str, str]:
    """(what the being will see of `text`, what it will NOT see). Empty second value: shown whole.

    Measured 2026-09-28, seq 4211 -> 4214: a `decline` whose --reason pasted a whole run (1,939
    chars) showed the being its first 480 and last 720 chars. The head said "I did not run" and
    quoted an earlier "timed out after 400s"; every epoch line, the exit code and the traceback
    were in the 739 omitted chars. The being's next three requests said the seat "ran the file
    but it timed out ... no exit code, no stdout, no stderr" -- a faithful reading of what it
    was shown. The seat had posted the evidence into the one place the being cannot see."""
    cap = cap or _window_cap()
    if len(text) <= cap:
        return text, ""
    head_n = cap * 2 // 5
    tail_n = cap - head_n
    shown = conv._shown_text({"text": text, "seq": "N"}, cap, _conv_id())
    return shown, text[head_n:len(text) - tail_n]


def _say(text: str) -> None:
    body = json.dumps({"from": _seat_id(), "message": text}).encode()
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
# "to keep the card for your own model" read as a reservation that ends: cbp-being logged a
# .cuda() stop as "pending GPU, retry when available" (2026-10-09, seq 8156). Say it is the default.
WHERE_HIDDEN = ("with the GPU hidden from it (CUDA_VISIBLE_DEVICES was empty), as every seat run "
                "is by default, so code that asks for cuda stops there on every rerun")
WHERE_GPU = "with the GPU visible to it"

# SAY IT ONLY TO CODE THAT ASKS. Measured on sprout-being 2026-10-14 (seq 256-257): the seat ran
# a script that called cv2 without importing it; the receipt carried WHERE_HIDDEN as always, and
# the being concluded "the GPU guard short-circuits everything" and that the NameError came from
# CUDA_VISIBLE_DEVICES. A clause about a device the code never names is a cause on offer. So the
# clause rides only when the file mentions a GPU stack, or when the seat chose --gpu. The child
# still runs with the devices hidden either way (child_env); only the sentence is conditional.
# The scan reads the requested file, not what it spawns -- a shell script that runs another
# file's torch code gets no clause; its own traceback still names cuda.
# Jetson's GStreamer elements need CUDA too without the file saying so. Measured on sprout-being
# 2026-10-17 (seq 1100-1101): nvvidconv under the hidden GPU failed "no CUDA-capable device is
# detected" after Argus had opened sensor 0, the receipt carried no clause, and the cause read
# as the hardware's. So the NVMM-path elements count as naming a GPU stack.
_GPU_WORDS = re.compile(r"cuda|torch|tensorflow|\bjax\b|cupy|\bgpu\b|nvidia|tensorrt"
                        r"|nvvidconv|nvjpegenc|nvv4l2|nvarguscamerasrc|nvbufsurf|memory:NVMM", re.I)


def where_clause(gpu: bool, source: str) -> str:
    """The receipt's GPU clause: WHERE_GPU under --gpu, WHERE_HIDDEN when the code names a GPU
    stack, and nothing when it does not."""
    if gpu:
        return WHERE_GPU
    return WHERE_HIDDEN if _GPU_WORDS.search(source or "") else ""


def child_env(gpu: bool, home: str | None = None) -> dict:
    """The environment the being's code runs under: the seat's own, with CUDA devices hidden
    unless the seat chose `--gpu`, and the being's home first on PYTHONPATH.

    IMPORTS RESOLVE FROM THE HOME, LIKE FILE PATHS DO. The child runs with cwd = home, so
    `np.load("data/X.npy")` finds the home's data/. But `python scratch/X.py` puts scratch/ on
    sys.path, not the cwd, so `from data.autoencoder import AutoEncoder` -- the same home, the
    same data/ -- failed "No module named 'data'". The being wrote that import four times
    (seq 6405, 6406, 6520, 6759 on CBP), each a run spent on a mismatch it could not see. Some of
    its files work around it with a sys.path line; those still work, since this only adds.

    OUTPUT IS UNBUFFERED, SO A TIMED-OUT RUN KEEPS WHAT IT PRINTED. Into a pipe, Python holds
    stdout in a block buffer; the timeout kills the child before it flushes, and the receipt said
    "stdout: (empty)" for a script that had printed. On Sprout 2026-10-14 two runs that each
    opened /dev/video0 and then blocked on a read (seq 489, 531) came back empty, and the being
    read the empty output as "nothing ran" and asked again."""
    env = dict(os.environ)
    env["PYTHONUNBUFFERED"] = "1"
    if not gpu:
        env["CUDA_VISIBLE_DEVICES"] = ""
    if home:
        env["PYTHONPATH"] = os.pathsep.join(x for x in (home, env.get("PYTHONPATH")) if x)
    return env


def ran_line(script_args: list[str]) -> str:
    """The command as the receipt states it. The being names flags in its `why`
    (36 of its first 77 requests did: `--output-dim 5`, then 20/25/30); the runner passed none,
    and a receipt reading "I ran X" let it read default-argument runs as its own experiments.
    So the receipt always says exactly which arguments went in, including none."""
    if not script_args:
        return "with no arguments (the script's defaults)"
    return f"with arguments: {shlex.join(script_args)}"


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


def _text(b) -> str:
    return b.decode("utf-8", "replace") if isinstance(b, bytes) else (b or "")


def run_child(argv: list[str], cwd: str, timeout: float, env: dict):
    """(returncode, stdout, stderr, timed_out). On a timeout CPython hands back the partial
    output as BYTES even under text=True, so it is decoded here; before this, every run that
    timed out raised a TypeError after the run and posted no answer (2026-09-25, seq 3755)."""
    try:
        r = subprocess.run(argv, cwd=cwd, capture_output=True, text=True, timeout=timeout, env=env)
        return r.returncode, r.stdout, r.stderr, False
    except subprocess.TimeoutExpired as e:
        return None, _text(e.stdout), _text(e.stderr), True


def cmd_run(args) -> None:
    inst = _instance()
    with answering_lock(inst, _conv_id()):
        # Checked UNDER the lock: a session that checked before waiting for it could act after a
        # seat paused in the meantime (GPT on #461).
        check_pause_holder(inst, _conv_id())
        _run(args)


def require_pending(seqs: list[int], rel, args, verb: str) -> None:
    """NOTHING PENDING MEANS SOMEONE ALREADY ANSWERED. The lock alone serialized the seq 996/997
    double run without preventing it (GPT on #461): the second `run` bound nothing, because the
    first had answered, and executed the file anyway as an unrequested run. Binding happens
    under the lock, so an empty binding here is the answer already given. A deliberate run of
    a file nobody asked about is still possible, but only by saying so (--unrequested)."""
    if seqs or getattr(args, "unrequested", False):
        return
    sys.exit(f"refusing: no pending request for {rel}; it was answered already or never asked "
             f"(`list` shows what is open). Nothing was {verb}. Pass --unrequested to {verb.rstrip('ed')} "
             f"it anyway.")


def _run(args) -> None:
    script_args = list(getattr(args, "script_args", None) or [])
    inst = _instance()
    p = _target(inst, args.path)
    rel = p.relative_to(inst.resolve())
    # Bound BEFORE running, so the answer names the requests that existed when the seat chose
    # to act — not whatever arrived while the script ran.
    seqs = bind(inst, _conv_id(), str(rel), args.seq)
    require_pending(seqs, rel, args, "run")
    interp = [sys.executable] if p.suffix == ".py" else ["bash"]
    # GPU HIDDEN, BY DEFAULT. The being shares this GPU with its own model. Measured on CBP
    # 2026-09-21: a beat holds the card at ~88-90% of 8 GB, and a model left resident after a
    # beat plus a foreground GPU load crashed the host twice (0x116, 0x133). At 06:43Z the
    # being rewrote its training script in PyTorch and it printed "Using device: cuda" — the
    # next run past its line-26 bug would have started training on that same card, possibly
    # beside its own resident model. A request to RUN code is a request to check that it works;
    # with the devices hidden, CUDA code falls back to the CPU and answers that question without
    # loading the card. That covers the measured path, not every path (see WHERE_HIDDEN).
    # `--gpu` is the deliberate, visible exception, and the check below is real rather than a
    # reminder: it asks the card and refuses when the being's model is holding it.
    if args.gpu and not args.gpu_anyway:
        refusal = why_the_card_cannot_take_a_job()
        if refusal:
            print(f"refusing --gpu for {rel}: {refusal}.\n"
                  f"Run it without --gpu (CUDA code falls back to the CPU and still answers "
                  f"'does this work'), or pass --gpu-anyway with a reason if this is the named "
                  f"project the card is being freed for.", file=sys.stderr)
            raise SystemExit(2)
    # The receipt names its input: WHICH version of the file ran, hashed BEFORE the run. A run can
    # outlast a beat, and a file edited mid-run would otherwise be named as the version that ran,
    # and the heartbeat would call code that never ran "unchanged since that run" (sprout's
    # review of SAGE #224). heartbeat.files_and_runs compares this sha with the file now.
    source_bytes = p.read_bytes()
    ran_sha = hashlib.sha256(source_bytes).hexdigest()[:12]
    where = where_clause(args.gpu, source_bytes.decode("utf-8", "replace"))
    rc, out, err, timed = run_child(interp + [str(p)] + script_args, str(inst), args.timeout, child_env(args.gpu, str(inst)))

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
    text = "\n".join([
        f"[request_run] I ran {rel} (sha {ran_sha}) {ran_line(script_args)}"
        f"{', ' + where if where else ''}. {verdict}.",
        "",
        block("stdout", out),
        "",
        block("stderr", err),
        "",
        _answers(seqs),
        "That is the whole output, unedited. Nothing is owed by you on this.",
    ])
    shown, hidden = as_shown(text)
    if hidden:
        # The run answer is shaped for the cut (verdict first, stderr and the answers line last),
        # so it posts; the seat just gets told what the being will and will not see of it.
        print(f"note: {len(text)} chars; the being's beat shows {_window_cap()} and cuts "
              f"{len(hidden)} from the middle (stdout's later lines). The verdict and the end of "
              f"stderr are in the shown part.", file=sys.stderr)
    _say(text)


def _answers(seqs: list[int]) -> str:
    return (answers_line(seqs) if seqs
            else "No pending request named this file, so this answers none of your requests.")


STANDING = "This is a decision, not a failure, and it is not about your standing."
STOCK_DOOR = "If you want it run under different conditions, say which and ask again."


def decline_closing(inst: Path) -> str | None:
    """This being's `decline_closing` policy from its instance.json (heartbeat.decline_closing_for,
    the same reader the beat record uses), or None for the default."""
    try:
        from sage.gateway.heartbeat import decline_closing_for  # noqa: E402
        return decline_closing_for(json.loads((Path(inst) / "instance.json").read_text()))
    except Exception:
        return None


def decline_text(rel, reason: str, seqs: list[int], closing: str | None = None) -> str:
    """The decline turn. By default it closes on the standing line and the stock door (STOCK_DOOR).

    `closing="standing_only"` is a PER-INSTANCE experiment (instance.json "decline_closing",
    RESEARCH_GENERALIZATION_RULE; SAGE #289): the turn ends on the standing line and names no way
    forward of its own, so the seat's reason is the only one. Measured on cbp-being alone,
    2026-09-21..30: 96 declines carried the stock door; the phrase was in 0 of the 433 beats before
    the first one and in 15 of the 666 since (13 within ten minutes of a decline), seven times as a
    todo line such as "[ ] Re-run ... under different conditions"; and 0 of 377 request_run calls
    named a condition. Most of those declines were for an unchanged file, where what the seat
    needed was a different sha and the stock sentence pointed somewhere else. That measures the
    PHRASE's uptake; what removing it does (to todo lines, re-asks) is the untested part."""
    tail = STANDING if closing == "standing_only" else f"{STANDING} {STOCK_DOOR}"
    return f"[request_run] I did not run {rel}. {reason}\n\n{_answers(seqs)}\n{tail}"


def cmd_decline(args) -> None:
    inst = _instance()
    with answering_lock(inst, _conv_id()):
        check_pause_holder(inst, _conv_id())
        _decline(args)


def _decline(args) -> None:
    inst = _instance()
    rel = _target(inst, args.path).relative_to(inst.resolve())
    seqs = bind(inst, _conv_id(), str(rel), args.seq)
    require_pending(seqs, rel, args, "declined")
    text = decline_text(rel, args.reason, seqs, decline_closing(inst))
    shown, hidden = as_shown(text)
    if hidden and not args.cut_anyway:
        # A decline says why not. Evidence pasted into one falls in the cut (see as_shown): the
        # being reads the head, "I did not run", and asks again. The refusal shows the seat the
        # being's view so the fix is a choice, not a guess.
        sys.exit(f"refusing: this decline is {len(text)} chars and the being's beat shows "
                 f"{_window_cap()} of a live turn, cutting the middle. Nothing was posted.\n"
                 f"The being would see:\n---\n{shown}\n---\nand would NOT see these "
                 f"{len(hidden)} chars:\n---\n{hidden[:400]}{'...' if len(hidden) > 400 else ''}\n---\n"
                 f"If that hidden part is a run's output, use `run` (its answer puts the verdict "
                 f"first and stderr last, and the tail survives the cut) or shorten the reason to "
                 f"the decision and where the result already is (a seq). Pass --cut-anyway to post "
                 f"it as it stands.")
    _say(text)


def _held_exit(e: "conv.PauseHeld", what: str, escape: str) -> None:
    sys.exit(f"refusing to {what}: the pause on {_conv_id()} is {e}, and this session did not "
             f"present its token (SEAT_PAUSE_TOKEN). If its holder is gone, {escape}.")


def cmd_pause(args) -> None:
    inst, cid = _instance(), _conv_id()
    try:
        pause = conv.pause_wakes(inst, cid, by=_seat_id(), minutes=args.minutes, reason=args.reason or "",
                                 token=os.environ.get("SEAT_PAUSE_TOKEN") or None,
                                 take_over=args.take_over or "")
    except conv.PauseHeld as e:
        _held_exit(e, "pause", 'pass --take-over "<why>" (recorded in the new pause)')
    print(f"wakes paused for {cid} until {pause['until']} (by {pause['by']}).\n"
          f"Set SEAT_PAUSE_TOKEN={pause['token']} on this session's run/decline/pause/resume calls; "
          f"other sessions are refused. A notice already queued before the pause can still fire one "
          f"wake, and that wake is refused here too. `resume` when you are done.")


def cmd_resume(args) -> None:
    inst, cid = _instance(), _conv_id()
    try:
        held = conv.resume_wakes(inst, cid, token=os.environ.get("SEAT_PAUSE_TOKEN") or None,
                                 force=args.force or "")
    except conv.PauseHeld as e:
        _held_exit(e, "resume", 'pass --force "<why>"')
    print(f"wakes resumed for {cid}; a wake still owed goes out at the end of the being's next beat"
          if held else f"{cid} was not paused")


def cmd_status(args) -> None:
    inst, cid = _instance(), _conv_id()
    pause = conv.wake_pause(inst, cid)
    if not pause:
        print(f"{cid}: not paused; mesh wakes answer the being")
    else:
        print(f"{cid}: paused by {pause['by']} since {pause['since']} until {pause['until']}"
              f"{' (' + pause['reason'] + ')' if pause.get('reason') else ''}")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("list").set_defaults(fn=cmd_list)
    pz = sub.add_parser("pause", help="jump in: stop mesh wakes for this conversation while you answer")
    pz.add_argument("--minutes", type=int, default=conv.WAKE_PAUSE_DEFAULT_MINUTES)
    pz.add_argument("--reason", default="")
    pz.add_argument("--take-over", metavar="WHY",
                    help="displace a pause held by another session (its holder is gone); recorded")
    pz.set_defaults(fn=cmd_pause)
    rs = sub.add_parser("resume", help="hand the conversation back to mesh wakes (holder's token)")
    rs.add_argument("--force", metavar="WHY", help="end a pause whose holder is gone")
    rs.set_defaults(fn=cmd_resume)
    sub.add_parser("status", help="who answers this conversation now").set_defaults(fn=cmd_status)
    r = sub.add_parser("run"); r.add_argument("path"); r.add_argument("--timeout", type=int, default=120)
    r.add_argument("--gpu", action="store_true",
                   help="let the script see the GPU (default: CUDA devices hidden — the being's model needs the card). "
                        "Refused if the card has no room; the check is real, not a reminder")
    r.add_argument("--gpu-anyway", metavar="REASON",
                   help="override the card check for a named project (fleet policy 2026-09-13: "
                        "unload the being only for a named project). Requires a reason")
    r.add_argument("--seq", type=int, action="append",
                   help="the request seq this answers (repeatable; default: every pending request for the file)")
    r.add_argument("--unrequested", action="store_true",
                   help="run a file no pending request names (refused by default: an empty binding "
                        "usually means another session already answered it)")
    r.set_defaults(fn=cmd_run)
    d = sub.add_parser("decline"); d.add_argument("path"); d.add_argument("--reason", required=True)
    d.add_argument("--seq", type=int, action="append", help="as for run")
    d.add_argument("--unrequested", action="store_true", help="as for run")
    d.add_argument("--cut-anyway", action="store_true",
                   help="post a reason longer than the being's per-turn window even though its "
                        "middle will not be shown (the refusal prints exactly what would be seen)")
    d.set_defaults(fn=cmd_decline)
    # Everything after `--` is the being's script's own argv. Split by hand: argparse
    # subparsers reject `--` followed by option-shaped words ("unrecognized arguments").
    argv = sys.argv[1:]
    script_args: list[str] = []
    if "--" in argv:
        i = argv.index("--")
        argv, script_args = argv[:i], argv[i + 1:]
    args = ap.parse_args(argv)
    if script_args and args.cmd != "run":
        ap.error("arguments after `--` go to the script, so only `run` takes them")
    args.script_args = script_args
    args.fn(args)
    return 0


if __name__ == "__main__":
    sys.exit(main())
