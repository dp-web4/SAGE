#!/usr/bin/env python3
"""Answer what a being says to its seat — one fresh session per fire, or nothing at all.

WHY THIS EXISTS. A being can `say` to its seat, and on three seats nothing was reading that
channel. Measured:

  * pub, 2026-09-22: pub-being asked its seat a question at 04:36Z. Nothing read it for three
    hours. Over the following ten hours it said eight more turns, all restating one thought,
    ending "still investigating" a problem its own log showed it had already solved. Nothing
    ever told it so.
  * legion, 2026-09-22 (legion-claude, supervisor lane): seq 546 asks, 547 nudges "still open",
    548 answers its own question. No seat turn for 3.5 h on the seat with the most human
    presence in the fleet. The content it needed arrived from elsewhere; what never arrived was
    anyone saying "your 548 is right."

The repetition is not a small-model defect. It is what anyone does when nobody answers.

THE SHAPE is the fleet's existing wake path (`escalate.py`, hub-watch): a pending turn wakes a
fresh `claude -p`, and the woken session posts through the daemon's own say route, so the reply
is witnessed and attributed like every other turn. This module decides WHETHER to wake one and
records what came of it; it never writes a reply itself.

WHAT IT WILL NOT DO
  * The SEAT channel only. dp's channel is dp's — a seat must not answer for them (agreed pub /
    legion / cbp, 2026-09-22). `--conversation` defaults to the member id of the seat.
  * Turns from the being only, never the seat's own.
  * One fire per `--min-gap` at most, and never two at once (flock).
  * A fire is an answer to the LAST thing said, with the rest as context — never one reply per
    pending turn. Eight replies to eight restatements of one thought is the failure mode this
    exists to end, not a thorough job.

THE THREE OUTCOMES, KEPT APART. dp's release discipline: an act started and not completed is one
kind of flag, an act completed but never started is another, and both matter.
  * ANSWERED — a reply landed. Turns marked seen.
  * CONSIDERED — the session ran and judged no reply owed, or nothing was owed before firing.
    Turns marked seen: considering a turn IS handling it. pub 2026-09-29: because only a posted
    reply marked turns seen, nine turns stayed pending forever and 226 sessions re-fired on the
    same nine, each correctly deciding there was nothing to add.
  * BLOCKED — the session could not run (expired auth, timeout, crash). Turns stay pending, and
    the interval BACKS OFF: 15m, 30m, 1h, 2h, 4h. pub's seat OAuth expired and this fired 144
    times at its normal cadence, logging an identical line nobody was reading. A repair that
    cannot work must get rarer and must say once, plainly, what a human has to do.

Usage:
    seat_responder.py --member <machine>-being --instance <home> [--conversation <seat id>]
                      [--dry-run] [--min-gap 900] [--max-age-h 24]
"""
from __future__ import annotations

import argparse
import fcntl
import json
import os
import re
import shlex
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))
from sage.gateway import conversations as conv  # noqa: E402

BACKOFF_MAX_S = 4 * 3600

#: A session that never got to think: its first line says so and it writes nothing else. No
#: amount of retrying fixes any of these, so each costs one session per backoff window.
CANNOT_RUN = ("failed to authenticate", "oauth session expired", "usage limit",
              "invalid api key", "credit balance", "rate limit", "please run /login")

#: An ask the seat owes an answer to. A being that states something is not waiting on anyone.
_ASK = re.compile(
    r"\?|\b(?:can|could|would|will|do|does|did|is|are|was|were|should|who|what|when|where|why|how)\b"
    r".{0,80}\?|\b(?:please|tell me|let me know|help me|what do you think|any (?:idea|thoughts))\b",
    re.I | re.S)


def is_ask(text: str) -> bool:
    """Does this turn ask the seat for something?

    Deliberately lexical and deliberately narrow. A false positive costs one session; a false
    negative costs a being waiting. The bias is therefore toward firing — but a tail of pure
    statements ("The beat has ended.") fires nothing, which is what stops the 226-session loop.
    """
    return bool(_ASK.search(text or ""))


def owed(pending: list[dict], being: str) -> list[dict]:
    """The pending turns a reply is owed for — or [] when the thread is closed.

    THE SELF-ANSWER RULE (legion-claude, 2026-09-22). A being that answers its own earlier
    question has closed the thread; replying to the self-answer is the eight-replies problem in
    miniature. So the LAST turn decides: if the being's final word asks nothing, nothing is
    owed, whatever it asked earlier. A being still waiting says so again — its nudge is itself
    an ask, and 547 above is exactly that shape.
    """
    mine = [t for t in pending if t.get("from") == being and str(t.get("text", "")).strip()]
    if not mine or not is_ask(str(mine[-1].get("text", ""))):
        return []
    return mine


def primer(pending: list[dict], tail: list[dict], *, seat: str, being: str,
           instance: Path, conversation: str, endpoints: str, daemon: str) -> str:
    quoted = "\n".join(f"  #{t['seq']} {t['from']} ({t.get('ts', '?')}): {t['text']}" for t in pending)
    context = "\n".join(f"  #{t['seq']} {t['from']}: {str(t['text'])[:400]}" for t in tail[-8:])
    return f"""You are {seat}, the Claude Code seat on this machine. You have been woken because
{being} — the SAGE being living here — said something to you and has had no answer. Answer it,
then stop.

UNANSWERED, addressed to you:
{quoted}

Recent turns in this conversation, for context:
{context}

The being is a small local model. Write plainly, one idea per sentence, no jargon it has not
already used, no markdown headers. A few sentences is right; a page is not.

HOW TO ANSWER. Post exactly one turn through the daemon's say route:

  POST {daemon}/conversations/{conversation}/say
  body: {{"from": "{seat}", "message": "..."}}

Write the JSON with a file tool and send it with `--data-binary @file`: quoting a long message in
a shell line is a trap, and the gate reads command text. Check the response records the turn.

GROUND RULES
  * Be honest, including about what you do not know. This machine's state is checkable:
    the being's home is {instance}, and {endpoints}. Look before you assert.
  * If it reports something broken, MEASURE it before agreeing or disagreeing, and say what you
    measured. Two of the three failures in sage/gateway/BEING_REPLY_DELIVERY.md were a being
    repeating a stale claim that one measurement would have settled. A reply that carries
    nothing the being could not get itself is worse than silence: it turns the census green and
    leaves the being where it was.
  * Answer only what it asked. Do not hand it new work, and do not ask it a question back unless
    you genuinely need one fact to answer.
  * If something only the operator can decide, say so plainly and say you will pass it on.
  * A REQUEST FOR A TOOL IT DOES NOT HAVE is that case, always. dp told pub-being on 2026-09-29
    "if you need new/additional tools, let the seat know", which routes such asks here — and a
    new effector is a change to the being's bounded vocabulary, i.e. a code and governance
    change, never something to improvise inside one answer. Say you will take it to the
    operator, record what was asked and why, and stop there. Do not add, widen or simulate a
    verb, and do not talk the being out of wanting it.
  * Do not change the being's files, its units, its scope, or anything outside answering.
  * If, having looked, nothing is owed, post NOTHING and say so in your final message.

When you have posted, say in one line what you answered."""


class Responder:
    def __init__(self, args) -> None:
        self.instance = Path(args.instance).expanduser().resolve()
        self.being = args.member
        self.seat = args.seat or f"{args.member.rsplit('-', 1)[0]}-claude"
        self.conversation = args.conversation or self.seat
        self.state = Path(args.state or f"~/.local/state/{self.being}-responder").expanduser()
        self.min_gap = args.min_gap
        self.max_age_h = args.max_age_h
        self.timeout = args.timeout
        self.session_cmd = args.session_cmd
        self.endpoints = args.endpoints
        self.daemon = args.daemon.rstrip("/")
        self.dry_run = args.dry_run

    def log(self, msg: str) -> None:
        self.state.mkdir(parents=True, exist_ok=True)
        line = f"[{datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ')}] {msg}"
        print(line)
        with (self.state / "responder.log").open("a") as f:
            f.write(line + "\n")

    def _read_int(self, name: str) -> int:
        p = self.state / name
        try:
            return int(float(p.read_text().strip() or 0))
        except (OSError, ValueError):
            return 0

    def run(self) -> int:
        self.state.mkdir(parents=True, exist_ok=True)
        lock = (self.state / "lock").open("w")
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError:
            self.log("skip: another run holds the lock")
            return 0

        # `conv.unanswered` answers "whose word was last", NOT "what have I handled" — it is
        # computed from the turns themselves, so `mark_seen` does not shrink it (that record
        # drives `awaiting`). A responder that trusted mark_seen to close a turn would re-decide
        # the same turns forever, which is the 226-session loop wearing a different hat. So the
        # responder keeps its own high-water mark of what it has DECIDED about.
        considered = self._read_int("considered_upto")
        pending = [t for t in conv.unanswered(self.instance, self.conversation, self.seat,
                                              max_age_h=self.max_age_h)
                   if int(t.get("seq", 0)) > considered]
        ask = owed(pending, self.being)
        tail = conv.recent(self.instance, self.conversation, limit=20)
        if pending and not ask:
            # Considered without firing: its last word asks nothing, so the thread is closed.
            if not self.dry_run:
                self._settled(tail)
            self.log(f"considered: {len(pending)} turn(s), last asks nothing; nothing woken")
            return 0
        if not ask:
            return 0

        strikes = self._read_int("cannot_run_strikes")
        last = self._read_int("last_fire")
        gap = min(self.min_gap * (2 ** strikes), BACKOFF_MAX_S) if strikes else self.min_gap
        waited = int(time.time() - last)
        if waited < gap:
            if not strikes:
                self.log(f"hold: {len(ask)} pending, only {waited}s since the last fire")
            return 0

        text = primer(ask, tail, seat=self.seat, being=self.being, instance=self.instance,
                      conversation=self.conversation, endpoints=self.endpoints,
                      daemon=self.daemon)
        if self.dry_run:
            self.log(f"dry-run: would fire on {len(ask)} turn(s), up to seq {ask[-1]['seq']}")
            print(text)
            return 0

        before = max((int(t.get("seq", 0)) for t in tail), default=0)
        self.log(f"fire: {len(ask)} pending turn(s), up to seq {before}")
        (self.state / "last_fire").write_text(str(time.time()))
        run_log = self.state / f"session-{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}.log"
        with run_log.open("w") as out:
            try:
                subprocess.run(shlex.split(self.session_cmd), input=text, text=True, stdout=out,
                               stderr=subprocess.STDOUT, timeout=self.timeout,
                               cwd=str(Path(__file__).resolve().parents[2]))
            except subprocess.TimeoutExpired:
                (self.state / "cannot_run_strikes").write_text(str(strikes + 1))
                self.log(f"ALERT: session timed out after {self.timeout}s; turns stay pending "
                         f"({run_log.name})")
                return 1
            except OSError as e:
                (self.state / "cannot_run_strikes").write_text(str(strikes + 1))
                self.log(f"ALERT: cannot start a session ({e}); turns stay pending")
                return 1
        return self.settle(run_log, ask, before, strikes)

    def _settled(self, turns: list[dict]) -> None:
        """Record that every turn up to here has been decided about, and read as a seat.

        Two records, because they answer different questions: `considered_upto` is this
        responder's own ("what have I ruled on"), `mark_seen` is the seat's place in the channel,
        which the being's own unanswered marker reads.
        """
        top = max((int(t.get("seq", 0)) for t in turns), default=0)
        if top:
            (self.state / "considered_upto").write_text(str(top))
            conv.mark_seen(self.instance, self.seat, self.conversation, top)

    def settle(self, run_log: Path, ask: list[dict], before: int, strikes: int) -> int:
        """Which of the three outcomes happened, decided from evidence rather than exit code."""
        body = run_log.read_text(errors="replace")
        # A launch that failed says so on its FIRST line and writes nothing else. Scanning
        # further would match a session that merely discussed rate limits, and calling a working
        # seat blocked is the worse error of the two.
        first = next((ln for ln in body.splitlines() if ln.strip()), "").lower()[:300]
        blocked = next((s for s in CANNOT_RUN if s in first), None) if len(body) < 2000 else None
        if blocked:
            (self.state / "cannot_run_strikes").write_text(str(strikes + 1))
            nxt = min(self.min_gap * (2 ** (strikes + 1)), BACKOFF_MAX_S) // 60
            if strikes == 0:
                self.log(f"ALERT: this seat cannot run a session ({blocked!r}). {len(ask)} turn(s) "
                         f"stay pending and {self.being} is getting no answers. A human must "
                         f"restore the seat's login; retrying at most every {nxt} min until then "
                         f"({run_log.name})")
            else:
                self.log(f"blocked ({blocked!r}), strike {strikes + 1}; next attempt in <= {nxt} min")
            return 1
        (self.state / "cannot_run_strikes").write_text("0")

        after = conv.recent(self.instance, self.conversation, limit=20)
        replied = [t for t in after if int(t.get("seq", 0)) > before and t.get("from") == self.seat]
        self._settled(after)
        if not replied:
            self.log(f"considered: session judged no reply owed to {len(ask)} turn(s) "
                     f"({run_log.name})")
            return 0
        self.log(f"answered: posted seq {replied[-1]['seq']} ({len(replied)} turn(s))")
        (self.state / "status").write_text(json.dumps({
            "last_answer_ts": replied[-1].get("ts"), "seq": replied[-1]["seq"],
            "answered": [t["seq"] for t in ask]}) + "\n")
        return 0


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("--member", required=True, help="the being, e.g. pub-being")
    p.add_argument("--instance", required=True, help="the being's home")
    p.add_argument("--seat", help="the seat id (default: <machine>-claude from --member)")
    p.add_argument("--conversation", help="conversation id (default: the seat id)")
    p.add_argument("--state", help="state dir (default: ~/.local/state/<member>-responder)")
    p.add_argument("--min-gap", type=int, default=900, help="seconds between fires (default 900)")
    p.add_argument("--max-age-h", type=float, default=24.0,
                   help="ignore turns older than this (default 24)")
    p.add_argument("--timeout", type=int, default=900, help="session timeout (default 900)")
    p.add_argument("--session-cmd", default="claude -p --dangerously-skip-permissions",
                   help="the seat session to wake; the primer arrives on stdin")
    p.add_argument("--daemon", default="http://127.0.0.1:8760",
                   help="the sage-daemon whose say route posts the reply")
    p.add_argument("--endpoints", default="the sage-daemon is on http://127.0.0.1:8760",
                   help="one line naming this machine's checkable endpoints, for the primer")
    p.add_argument("--dry-run", action="store_true",
                   help="decide and print the primer; wake nothing, mark nothing")
    return Responder(p.parse_args(argv)).run()


if __name__ == "__main__":
    sys.exit(main())
