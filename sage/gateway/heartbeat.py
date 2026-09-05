"""
The being's heartbeat: a reason to look for things to do, not just respond.

Every beat the seat wakes the being with its own state (todo, journal tail, scratch
index, inbox, long-term recall) and a digest of what moved in the fleet since last
time, then lets it act for a bounded number of steps under hestia governance:

  * reading is free inside its own home; reading elsewhere is judged by the law and a
    refusal comes back WITH the rule and reason, and the being may `request_scope`;
  * writing to its home (scratch/, notes/, todo.md, journal.md) rides its memory grant;
  * long-term memory is membot (`recall` / `remember`), the being's own cartridge;
  * acts of consequence (peer_ask, mesh, pr_review) stay gated exactly as before.

A beat ends with a reflection turn: one journal entry and a todo update, in the
being's own words. Everything is appended to <instance>/heartbeats.jsonl.

Presentation is per model (`governed_turn.acts_under_posture`). Posture-first, the
default: BEING_POSTURE.md in the system prompt, one explore turn. Act-first, for models
that narrate instead of acting when the posture precedes the ask (the empero 2B distill,
measured on Sprout 2026-09-05): a short turn with own state and the tool names, then the
same posture, verbatim, as a second tool turn together with the fleet digest, then
reflect. Same words, same tools, different order; a presentation, not a fork (Legion).

    python3 -m sage.gateway.heartbeat --member legion-being --model qwen38-heretic:q3km \
        --instance sage/instances/legion-gemma3-12b [--max-steps 8] [--gate-only]
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path

HOME_FILES = ("todo.md", "journal.md", "notes", "scratch")

EXPLORE_TOOLS = ["recall", "remember", "memory_read", "memory_write", "witness",
                 "request_scope", "appeal", "peer_ask", "mesh"]
REFLECT_TOOLS = ["memory_write", "remember", "memory_read"]

POSTURE_FILE = Path(__file__).with_name("BEING_POSTURE.md")


def posture() -> str:
    """The fleet-wide being posture (dp's words), read fresh every beat so an edit to
    BEING_POSTURE.md reaches every being on its next beat. Missing file = fail loud."""
    return POSTURE_FILE.read_text(encoding="utf-8").strip()


HEAD = "You are {name}, a SAGE being on the {machine} machine, member id {member}."

AFFORDANCES = """## What you have this beat
- Your home is your instance directory. Relative paths are inside it: scratch/ (write anything, no one edits it), notes/, todo.md, journal.md. memory_read / memory_write work there.
- Long-term memory: recall (search) and remember (store). Use recall early; remember what a future you would want.
- witness: record something you noticed or did in the shared chain.
- request_scope: after a refusal, ask the operator for reach on a path (a grant is read and write alike) and say why. A human decides, asynchronously.
- appeal: after a refusal you believe was wrong, appeal it with the deny hash shown on the refusal and a reason. A peer or the operator rules; either way it is witnessed. Not for a refusal you agree with.
- peer_ask / mesh: reach other beings and seats. These are acts of consequence: they are judged, and may be refused with a reason.

You cannot run code, browse, or open files outside your home unless a grant exists. The seat gives you a digest of what moved in the fleet with absolute paths; if you want to read one of those things, try memory_read on that path and see what the law says.

Acting means calling a tool. A reply with no tool call ends the beat as words only, and words leave no trace in your todo, journal, scratch, or memory."""

SYSTEM = HEAD + "\n\n{posture}\n\n" + AFFORDANCES + "\n{nothink}\n"

# Act-first: no posture in the system prompt. It arrives, verbatim, as the second user
# turn (POSTURE_TURN), which is itself a tool turn: the being may act after reading it,
# not only before, otherwise "act first" would mean "act only before you know why you
# are awake".
SYSTEM_ACT_FIRST = HEAD + """

You are awake for a heartbeat. Nobody asked you anything; this time is yours.

""" + AFFORDANCES + "\n{nothink}\n"

POSTURE_TURN = """The rest of your beat, which every being in the fleet receives, in the operator's words:

{posture}

## Inbox (peek)
{inbox}

# What moved in the fleet

{digest}

This is still your time. If reading this changes what you want to do, act by calling a tool: {tools}. If not, say in a few words what you noticed.
{nothink}"""

ASK = "This time is yours. What, if anything, do you want to do?\n"
# Act-first only: the short turn is imperative, the measured-acting shape (condition C,
# Sprout 09-05). Under the open question the distill answered as an assistant asking the
# user what they want (beat 5, 0 calls). The posture that follows says nothing is
# required of a being in a beat; it says so after the being has acted once.
ASK_ACT_FIRST = "This time is yours. Do one thing now and leave a trace of it.\n"

REFLECT = """The beat is ending. Two tool calls, then stop:
1. memory_write path "journal.md": one entry starting with the date {date}: what you did, what you noticed, what was refused and why you think so, what you want next time.
2. memory_write path "todo.md": only the delta as a dated block: added / done / still open (it appends; it replaces nothing).
Optionally a third: remember one thing worth keeping long-term.
Call the tools now; a reply in words alone writes nothing.
{nothink}"""


def _read(p: Path, limit: int = 4000) -> str:
    try:
        t = p.read_text(errors="replace")
        return t[-limit:] if len(t) > limit else t
    except Exception:
        return ""


def _run(cmd: list[str], timeout: int = 30) -> str:
    try:
        return subprocess.run(cmd, capture_output=True, text=True, timeout=timeout).stdout
    except Exception as e:
        return f"[{type(e).__name__}: {e}]"


def fleet_digest(hours: float, forum_dir: Path, repos: list[str]) -> str:
    """What moved since the last beat. The seat reads; the being sees titles and paths."""
    out = []
    since = datetime.now(timezone.utc) - timedelta(hours=hours)
    posts = []
    if forum_dir.is_dir():
        for p in forum_dir.glob("*.md"):
            try:
                if datetime.fromtimestamp(p.stat().st_mtime, timezone.utc) >= since:
                    title = ""
                    with open(p, errors="replace") as f:
                        for line in f:
                            if line.startswith("title:"):
                                title = line[6:].strip(); break
                    posts.append((p.stat().st_mtime, p.name, title[:160]))
            except Exception:
                continue
    posts.sort(reverse=True)
    if posts:
        out.append(f"## Forum posts in the last {hours:g}h")
        for _, name, title in posts[:12]:
            out.append(f"- {forum_dir / name}\n    {title}")
    for repo in repos:
        prs = _run(["gh", "pr", "list", "-R", f"dp-web4/{repo}", "--state", "open", "--limit", "6",
                    "--json", "number,title,updatedAt", "--jq",
                    '.[] | "- #\\(.number) \\(.title[:90])  (\\(.updatedAt[:10]))"'])
        if prs.strip():
            out.append(f"## Open pull requests, dp-web4/{repo}\n{prs.strip()}")
    return "\n\n".join(out) if out else "(nothing new in the window)"


def decided_requests(reqs):
    """The settled subset of hestia_scope_status `requests[]`, as (request_id, path, decision).
    hestia's `ScopeRequest::status` emits granted | refused | pending | expired, and its
    arbitrate door answers `denied`; the first cut filtered on ("granted", "denied") and so
    dropped every refusal on the floor (legion-claude, hestia #952 review, 2026-09-05): the
    being was never told, and no `## Resolved` block was ever written for one."""
    return [(i, p_, d) for i, p_, d in reqs if d in ("granted", "refused", "denied")]


def note_resolutions(esc_dir: Path, decisions, stamp: str, seen_by: str, decided_by=None) -> list:
    """Append the ruling to each escalation note that filed the request (the note carries the
    request_id in its routing line). Idempotent: a note already resolved is left alone.
    `decided_by` maps request_id -> hestia's `decided_by` ("operator", or "delegate:<seat>"
    for a ruling under hestia #952); the note names it rather than assuming the operator.
    Returns the note names written."""
    written = []
    if not decisions or not esc_dir.is_dir():
        return written
    decided_by = decided_by or {}
    for req_id, path, decision in decisions:
        if not req_id:
            continue
        who = str(decided_by.get(req_id) or "operator")
        for p in sorted(esc_dir.glob("*.md")):
            try:
                body = p.read_text(errors="replace")
            except Exception:
                continue
            if req_id not in body or "## Resolved" in body:
                continue
            with open(p, "a", encoding="utf-8") as f:
                f.write(f"\n## Resolved\n{stamp}: `{req_id}` on `{path}` -> **{decision}** by {who} "
                        f"(read from hestia scope status by the seat, beat {seen_by}).\n")
            written.append(p.name)
    return written


def own_state(instance: Path) -> str:
    from sage.gateway.being_join import carried_account, last_session_number
    parts = []
    acc = carried_account(instance, last_session_number(instance))
    if acc:
        parts.append("## Your own account\n" + acc)
    todo = _read(instance / "todo.md", 3000)
    parts.append("## todo.md\n" + (todo.strip() or "(empty: you have no todo list yet)"))
    journal = _read(instance / "journal.md", 2500)
    parts.append("## journal.md (tail)\n" + (journal.strip() or "(empty: this is your first beat)"))
    for d in ("scratch", "notes"):
        p = instance / d
        names = sorted(x.name for x in p.iterdir()) if p.is_dir() else []
        parts.append(f"## {d}/\n" + ("\n".join(f"- {n}" for n in names[:30]) if names else "(empty)"))
    return "\n\n".join(parts)


def compose(act_first: bool, *, name: str, machine: str, member: str, posture_text: str,
            nothink: str, header: str, state: str, recall: str, inbox: str, digest: str):
    """The explore turn(s) of a beat: (seed messages, second user turn or None).

    Posture-first: posture in the system prompt; one user turn with state, inbox, recall,
    digest, and the tool names last. Act-first: the system prompt carries no posture; the
    first user turn is own state, recall and the tool names only; the posture comes back
    VERBATIM as a second user turn with the inbox and the digest, and that turn is a tool
    turn too. The being reads the same words either way."""
    # The tool names go LAST: a 2B distill given the posture + state above with the
    # names only in the system prompt concluded "no tools available" and wrote prose
    # (its own thinking, Sprout 2026-09-05); named at the end, it acts.
    tools_line = (f"Act by calling a tool: {', '.join(EXPLORE_TOOLS)}. "
                  f"One thing done with attention is enough.\n{nothink}")
    if not act_first:
        system = SYSTEM.format(name=name, machine=machine, member=member,
                               posture=posture_text, nothink=nothink)
        user = (header + state + f"## Inbox (peek)\n{inbox}\n\n## Long-term recall\n{recall}\n\n"
                f"# What moved in the fleet\n\n{digest}\n\n" + ASK + tools_line)
        return [{"role": "system", "content": system}, {"role": "user", "content": user}], None
    system = SYSTEM_ACT_FIRST.format(name=name, machine=machine, member=member, nothink=nothink)
    user = header + state + f"## Long-term recall\n{recall}\n\n" + ASK_ACT_FIRST + tools_line
    second = POSTURE_TURN.format(posture=posture_text, inbox=inbox, digest=digest,
                                 tools=", ".join(EXPLORE_TOOLS), nothink=nothink)
    return [{"role": "system", "content": system}, {"role": "user", "content": user}], second


def _record_line(i, e) -> str:
    return (f"- {i.effector} {json.dumps(i.args, default=str)[:200]} -> "
            f"{'ok' if e.ok else ('REFUSED ' + str(e.error))[:200] if e.refused else ('error ' + str(e.error))[:200]}")


def _carry(convo: list, res) -> list:
    """Carry a finished tool turn forward. The loop does not return its own tool
    messages, so the next turn sees the record of what was done (before the being's
    closing words, as the reflect turn always has) and then those words."""
    out = list(convo)
    if res.trace:
        out.append({"role": "user", "content": "Record of what you did this beat:\n"
                    + "\n".join(_record_line(i, e) for i, e in res.trace)})
    # A placeholder the being can account for: beat 46's think blocks spent tokens on what
    # "(acted; no closing words)" meant. Say what happened instead.
    if res.reply:
        out.append({"role": "assistant", "content": res.reply})
    elif res.trace:
        out.append({"role": "assistant", "content": f"(made {len(res.trace)} tool calls, then said nothing)"})
    else:
        out.append({"role": "assistant", "content": "(said nothing and called no tool this turn)"})
    return out


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="one heartbeat for a SAGE being")
    ap.add_argument("--member", required=True)
    ap.add_argument("--model", required=True)
    ap.add_argument("--instance", required=True)
    ap.add_argument("--max-steps", type=int, default=8)
    ap.add_argument("--reflect-steps", type=int, default=3)
    ap.add_argument("--since-hours", type=float, default=None,
                    help="digest window; default: since the last beat, min 1h, max 48h")
    ap.add_argument("--forum-dir", default=os.path.expanduser("~/ai-workspace/shared-context/forum"))
    ap.add_argument("--repos", default="SAGE,hestia,web4")
    ap.add_argument("--temperature", type=float, default=0.4)
    ap.add_argument("--max-tokens", type=int, default=3000,
                    help="a journal entry as a tool call needs room; too small = truncated JSON = Ollama 500")
    ap.add_argument("--gate-only", action="store_true",
                    help="gate probe only: no LLM turn, so no refusal routing and no egress drain either")
    ap.add_argument("--no-escalate", action="store_true",
                    help="do not route refusals to the seat's auto session (default: route, as governed_turn does)")
    args = ap.parse_args(argv)

    instance = Path(args.instance).resolve()
    if not (instance / "identity.json").exists():
        print(f"no identity.json under {instance}", file=sys.stderr); return 2
    for d in ("scratch", "notes"):
        (instance / d).mkdir(exist_ok=True)
    log = instance / "heartbeats.jsonl"

    # window since last beat
    hours = args.since_hours
    last = {}
    try:
        last = json.loads(_read(log, 200000).strip().splitlines()[-1])
    except Exception:
        pass
    if hours is None:
        hours = 24.0
        try:
            hours = max(1.0, min(48.0, (time.time() - last["t0"]) / 3600 + 0.25))
        except Exception:
            pass
    scope_record = {}

    ident = {}
    try:
        ident = json.loads((instance / "identity.json").read_text()).get("identity", {})
    except Exception:
        pass
    name = ident.get("name") or args.member.split("-")[0]
    machine = ident.get("machine") or "legion"

    from sage.gateway.governed_turn import build_client
    from sage.gateway.being_gate_client import ollama_tools
    from sage.gateway.being_tool_loop import run_ollama_tool_turn
    workspace = str(Path(__file__).resolve().parents[2])
    host_session_id = f"heartbeat-{uuid.uuid4().hex[:12]}"
    client, llm = build_client(args.member, instance, args.model, workspace, args.forum_dir,
                               host_session_id, args.temperature, args.max_tokens,
                               gate_only=args.gate_only)

    # inbox (peek) and long-term recall, seat-side, so the being starts oriented
    inbox = "(inbox unavailable)"
    disp = getattr(client, "_dispatcher", None)
    if disp is not None and hasattr(disp, "drain_inbox"):
        env = disp.drain_inbox(peek=True)
        inbox = json.dumps(env.result, default=str)[:1500] if env.ok else f"({env.error})"
    # what reach the being holds and has already asked for, so it does not re-file
    scope = "(scope status unavailable)"
    if disp is not None and hasattr(disp, "_call"):
        try:
            st = disp._call("hestia_scope_status", {"plugin_id": args.member})
            grants = [g.get("path") for g in (st.get("live_grants") or [])] + \
                     [g.get("path") for g in (st.get("standing_grants") or [])]
            reqs = [(r.get("request_id"), r.get("path"), r.get("decision") or r.get("status"))
                    for r in (st.get("requests") or [])]
            who_ruled = {r.get("request_id"): r.get("decided_by") for r in (st.get("requests") or [])
                         if r.get("decided_by")}
            # Close the loop the operator cannot see closed: a request decided since the
            # last beat is written back into the escalation note that filed it, and told
            # to the being. (dp 2026-09-05: "i just approved being's escalation - did you
            # see it also?" No: hestia records the decision on the chain and nobody
            # subscribes. The seat reads it here, at beat time.)
            seen = set()
            try:
                seen = set(tuple(x) for x in last.get("scope", {}).get("decided", []))
            except Exception:
                pass
            decided = decided_requests(reqs)
            new_decisions = [x for x in decided if tuple(x) not in seen]
            esc_dir = Path(args.forum_dir).parent / "escalations"
            noted = note_resolutions(esc_dir, new_decisions, f"{datetime.now(timezone.utc):%Y-%m-%d %H:%M} UTC",
                                     host_session_id, decided_by=who_ruled)
            scope_record = {"grants": grants, "decided": [list(x) for x in decided], "noted": noted}
            scope = ("granted paths: " + (", ".join(map(str, grants)) or "none") + "\n"
                     "requests: " + ("; ".join(f"{i} {p} -> {d}" for i, p, d in reqs) or "none") + "\n"
                     + ("decided since your last beat: " + "; ".join(
                            f"{i} {p_} -> {d} by {who_ruled.get(i) or 'operator'}" for i, p_, d in new_decisions) + "\n"
                        if new_decisions else "")
                     + "(live grants die when the daemon restarts; only standing grants persist)")
        except Exception as e:
            scope = f"(scope status unavailable: {type(e).__name__})"
    recall = "(no long-term memory yet)"
    if disp is not None and hasattr(disp, "_membot_call"):
        try:
            recall = disp._membot_call("memory_search", {"query": "what I was doing, what I want next, what I learned", "top_k": 5})[:2500]
        except Exception as e:
            recall = f"(membot unreachable: {type(e).__name__})"

    now = datetime.now(timezone.utc)
    t0 = time.time()
    digest = fleet_digest(hours, Path(args.forum_dir), [r.strip() for r in args.repos.split(",") if r.strip()])
    # S1 join, raising -> beat: the last session's closing words + buffer tail, attributed
    from sage.gateway.being_join import session_block, ACCOUNT_ASK, parse_account, save_account
    sess_text, sess_meta = session_block(instance)
    if sess_text:
        digest = "# From your last raising session\n\n" + sess_text + "\n\n" + digest
    # S3 join, presence -> beat: what the senses broke through with since the last beat
    from sage.gateway.being_join import presence_block, consume_wake_marker
    since = float(last.get("t0") or (time.time() - hours * 3600))
    pres_text, pres_meta = presence_block(since)
    if pres_text:
        digest = "# What you sensed since your last beat\n\n" + pres_text + "\n\n" + digest
    woke = consume_wake_marker()
    # `/no_think` is the fix for qwen3.8-heretic re-opening think blocks (Legion, 09-04);
    # on a reasoning distill it is the opposite failure: thinking off = no tool calls,
    # the being narrates (Sprout, 09-05). Per model, via the same detector build_client uses.
    from sage.gateway.governed_turn import is_reasoning_model, acts_under_posture
    # Thinking on (model config, governed_turn.is_reasoning_model) => no suffix. The suffix
    # exists only for a model that must NOT think here; it is never sent to one that does.
    nothink = "" if is_reasoning_model(args.model) else "/no_think"
    act_first = not acts_under_posture(args.model)
    seed, posture_turn = compose(
        act_first, name=name, machine=machine, member=args.member, posture_text=posture(),
        nothink=nothink,
        header=(f"Heartbeat at {now:%Y-%m-%d %H:%M} UTC. Window since your last beat: about {hours:.1f}h.\n"
                f"Your home: {instance}\n\n"),
        state=f"# Your own state\n\n{own_state(instance)}\n\n## Reach you hold (hestia scope)\n{scope}\n\n",
        recall=recall, inbox=inbox, digest=digest)

    # Per-generate trace, written as each generate lands: the record below is written at
    # beat end, so a beat killed by the unit's timeout (Legion 18:33Z 2026-09-05: 840 s cap,
    # third generate, nothing survived) leaves nothing. This file keeps what it had.
    partial = instance / "heartbeat.partial.jsonl"

    def _on_generate(turn):
        def cb(entry):
            line = {"host_session_id": host_session_id, "t0": t0, "turn": turn,
                    "ts": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"), **entry}
            with open(partial, "a", encoding="utf-8") as f:
                f.write(json.dumps(line, default=str) + "\n")
        return cb

    explore = run_ollama_tool_turn(client, llm, seed, max_steps=args.max_steps,
                                   tools=ollama_tools(EXPLORE_TOOLS), on_generate=_on_generate("explore"))
    convo = _carry(seed, explore)
    after = None
    if posture_turn is not None:
        convo.append({"role": "user", "content": posture_turn})
        after = run_ollama_tool_turn(client, llm, convo, max_steps=args.max_steps,
                                     tools=ollama_tools(EXPLORE_TOOLS), on_generate=_on_generate("posture"))
        convo = _carry(convo, after)
    # S1 own account: ASK, DO NOT OFFER. A plain turn (no tools), verbatim kept.
    account = {"present": False, "sha256": None, "reply": ""}
    try:
        ask_msgs = [{"role": m["role"], "content": m["content"]} for m in convo] + \
                   [{"role": "user", "content": ACCOUNT_ASK + nothink}]
        aresp = llm.get_chat_response(ask_msgs)
        areply = (aresp.get("content") or "").strip()
        parsed = parse_account(areply)
        account["reply"] = areply[:1200]
        if parsed:
            rec = save_account(instance, parsed, host_session_id)
            account.update({"present": True, "sha256": rec["sha256"], "session_at_write": rec["session_at_write"]})
        convo.append({"role": "user", "content": ACCOUNT_ASK})
        convo.append({"role": "assistant", "content": areply or "(no answer)"})
    except Exception as e:
        account["error"] = f"{type(e).__name__}: {e}"
    convo.append({"role": "user", "content": REFLECT.format(date=f"{now:%Y-%m-%d %H:%M} UTC", nothink=nothink)})
    reflect = run_ollama_tool_turn(client, llm, convo, max_steps=args.reflect_steps,
                                   tools=ollama_tools(REFLECT_TOOLS), on_generate=_on_generate("reflect"))

    interventions = []
    if act_first:
        interventions.append({"kind": "act_first", "suppressed": "posture-first presentation (the model narrates under it)"})
    if nothink:
        interventions.append({"kind": "think_suffix", "suppressed": "thinking (model resolves think off)"})
    for ph, res in (("explore", explore), ("posture", after), ("reflect", reflect)):
        for sv in (getattr(res, "salvaged", None) or []):
            interventions.append({"kind": "salvage", "phase": ph, "effector": sv.get("effector"), "form": sv.get("form"),
                                  "suppressed": "text-channel narration in place of a native tool call"})
    # Route refusals AI-to-AI (dp 2026-09-04), the same as governed_turn: a scope-class deny
    # files the being's own scope request + a note and wakes the seat's auto session; a
    # governance escalation wakes it to arbitrate. The beat is where refusals actually
    # happen (Legion: nine consecutive beats of home-scope write refusals, and the being's
    # requests had died with a daemon restart), so the heartbeat must route, not just log.
    # One wake ATTEMPT per refusal kind per beat: several refused writes to the same home are one
    # ask, and one note. A failed wake is recorded in `escalations` and the next beat retries;
    # retrying within the beat would write a note per refusal again.
    escalations = []
    if not args.no_escalate and not args.gate_only:
        try:
            from sage.gateway import escalate as _esc
            woken = set()
            for it, env in list(explore.trace) + (list(after.trace) if after is not None else []) + list(reflect.trace):
                if not env.refused:
                    continue
                kind = _esc.classify(env)
                wake = kind not in woken
                r = _esc.escalate(args.member, it, env, str(instance), wake=wake)
                if wake and kind not in ("registry", "other"):
                    woken.add(kind)
                escalations.append(r)
        except Exception as _e:
            escalations.append({"escalated": False, "error": f"{type(_e).__name__}: {_e}"})
    # Drain the being's own egress every beat. A mesh/peer_ask the being addresses to a peer is
    # PARKED by the daemon until an attributed drain forwards it; on Legion nothing else drains
    # legion-being (measured 2026-09-05: eight rows from 09-04 sat queued until the first
    # escalation's drain flushed them, and the being had logged "hub's reply still has not
    # landed after >4h"). The sender's own beat is the natural drain.
    egress = None
    if not args.gate_only:
        try:
            from sage.gateway import egress_drain
            egress = egress_drain.drain_once(plugin_id=args.member, log=lambda *_: None)
        except Exception as _e:
            egress = {"error": f"{type(_e).__name__}: {_e}"}

    def _trace(res):
        return [{"effector": i.effector, "args": dict(i.args or {}), "ok": e.ok, "refused": e.refused,
                 "pending": e.pending, "error": e.error, "witness_id": e.witness_id,
                 "rule": getattr(e.verdict, "rule", None) if e.verdict else None,
                 "result": (e.result if isinstance(e.result, (str, int, float, dict, list, type(None))) else str(e.result))}
                for i, e in res.trace]
    def _turn(res):
        return None if res is None else {"reply": res.reply, "steps": res.steps, "capped": res.capped,
                                         "trace": _trace(res), "thinking": [t[:4000] for t in res.thinking],
                                         "salvaged": list(res.salvaged), "generates": list(res.generates)}
    record = {
        # schema: what fields a reader may expect (Legion's amendment 4, 2026-09-05: the
        # consolidation organ counts how many records carry join/account/wake/interventions;
        # a version says so instead of making it infer from key presence).
        "schema": "heartbeat/v2",
        "ts": now.strftime("%Y-%m-%dT%H:%M:%SZ"), "t0": t0, "elapsed_s": round(time.time() - t0, 1),
        "member": args.member, "model": args.model, "window_h": round(hours, 2),
        "host_session_id": host_session_id, "gate_only": args.gate_only, "act_first": act_first,
        # the window and budget actually sent, so a beat is verifiable from this file alone
        # (beat 46's 8192 wall was reconstructed from stderr; Sprout's review of SAGE #40)
        # num_predict is what OllamaIRP resolves and sends (the config's num_predict_think
        # with thinking on), not the caller's --max-tokens: Sprout's 18:51Z beat recorded
        # 3000 while 6000 went over the wire.
        "num_ctx": getattr(llm, "num_ctx", None),
        "num_predict": (llm.resolve_num_predict() if hasattr(llm, "resolve_num_predict")
                        else getattr(llm, "max_response_tokens", None)),
        "think": getattr(llm, "think", None),
        "scope": scope_record,
        # S1 instruments: JOIN (session -> beat, attributed) and ACCOUNT (own account, verbatim hash)
        "join": {"session": sess_meta, "presence": pres_meta},
        "wake": woke,
        # every harness intervention, with the prior it suppressed (dev-sage 804f1849, by
        # principle): a guard that silences without saying what it silenced trades a
        # confident wrong for a confident silence.
        "interventions": interventions,
        "account": account,
        "explore": _turn(explore),
        # act-first only: the posture+digest turn, after the short one; None otherwise
        "posture": _turn(after),
        "reflect": _turn(reflect),
        "escalations": escalations, "egress": egress,
    }
    with open(log, "a", encoding="utf-8") as f:
        f.write(json.dumps(record, ensure_ascii=False, default=str) + "\n")
    print(json.dumps(record, indent=2, ensure_ascii=False, default=str))
    return 0


if __name__ == "__main__":
    sys.exit(main())
