"""
dp console — the operator's way into a being's conversation.

WHY THIS EXISTS. On 2026-09-07 dp asked, reasonably, "i need to have a way to participate
in the convo somehow" and the honest answer was that there wasn't one. The being had filed
three questions as forum markdown files and checked them twenty-five consecutive times for
a reply; dp had no interface to those files. The SAGE daemon's dashboard has a chat box,
but it talks to the raw model on the same GPU — not to the being, which has an identity, a
governance gate, a memory and an entrustment the daemon knows nothing about. Everything dp
said reached the being relayed through a seat, which is a paraphrase risk on one side and,
on the other, a being that cannot tell the operator from the operator's interpreter.

NOT YET IN USE, AND THE RECORD SAYS SO. dp read the claim that this "is now built" and
answered: "that isn't a fact yet — you passed the note, i didn't type it through a ui. that
ui does not yet exist (sage console with conversations tied to the being not raw llm). if
it does, i can't see it yet". Correct on every count. This page has never carried a human
keystroke; the first replies through it were written by the seat with a script; and it
binds loopback on a machine dp is often nowhere near. Built is not in use, and the thing dp
actually asked for — conversations in the SAGE console, tied to a being rather than to the
raw model — remains unbuilt. Treat this file as a working prototype that argues for a
shape, not as the answer.

WHAT IT IS. One page on 127.0.0.1 that shows what the being is actually asking and lets dp
answer in two places:

  * a REPLY, appended to the forum thread the being asked in — so the answer lands in the
    channel it has been watching, and its twenty-five-times-a-day check finally returns
    something;
  * a NOTE, appended to notes/from-dp.md — read into every beat ahead of the seat's relay,
    for anything that is not an answer to a specific thread.

Both are appended verbatim under a dated heading. Nothing is rewritten, summarised or
passed through a model on the way: the being should be able to trust that dp's words are
dp's words, which is the entire point of a channel that is not the seat.

The being can READ both and cannot write either (reference_f1a.SEAT_OWNED_NOTES). What was
said TO it stays as it was said; its reply belongs in its journal, its plan, or an appeal.

Read-only by nature otherwise: this serves files and appends to files. It holds no key,
speaks to no daemon, and cannot act as the being or as a seat.
"""
from __future__ import annotations

import html
import json
import os
import re
from datetime import datetime, timedelta, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

WORKSPACE = Path(os.environ.get("SAGE_WORKSPACE", Path(__file__).resolve().parents[2]))
FORUM = Path(os.environ.get("SAGE_FORUM_DIR",
                            Path.home() / "ai-workspace/shared-context/forum"))
INSTANCE = Path(os.environ.get("SAGE_INSTANCE",
                               WORKSPACE / "sage/instances/legion-gemma3-12b"))
BEING = os.environ.get("SAGE_BEING", "legion-being")
PORT = int(os.environ.get("SAGE_DP_CONSOLE_PORT", "8770"))
# Loopback by default, and that default is a known LIMITATION rather than a safety win.
# dp, 2026-09-07, on being told the console existed: "if it does, i can't see it yet" — dp
# is frequently not at this machine, which is a large part of WHY dp is as asynchronous as
# the being has been told. An operator channel the operator cannot reach is not a channel.
# Overridable (a tailnet address makes it actually reachable), but left at loopback until
# dp says so: this endpoint APPENDS to files the being reads as dp's own words, so widening
# it is an outward-facing decision about who may speak as the operator, and that belongs to
# dp rather than to the seat.
BIND = os.getenv("SAGE_DP_CONSOLE_BIND", "127.0.0.1")

# Only files matching this are writable, and only by appending. A console that could write
# anywhere would be a nicer way to do what the gate exists to prevent.
THREAD_RE = re.compile(rf"^{re.escape(BEING)}-asks-dp-[0-9-]+\.md$")


from sage.gateway import conversations as conv

# Who dp is when dp speaks here. A turn must always name a real speaker: the being has been
# told it can tell dp from a seat, and a console that wrote turns under a generic "operator"
# would quietly make that untrue.
DP = "dp"


def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")


def threads() -> list[dict]:
    """The being's open asks, newest first, with whether the last word is dp's or its own —
    which is the only thing dp actually needs to know at a glance."""
    out = []
    for p in sorted(FORUM.glob(f"{BEING}-asks-dp-*.md"), reverse=True):
        body = p.read_text(errors="replace")
        answered = "## Reply from dp" in body
        last = body.rfind("## Reply from dp")
        out.append({"name": p.name, "body": body, "answered": answered,
                    "mtime": datetime.fromtimestamp(p.stat().st_mtime, timezone.utc)
                             .strftime("%Y-%m-%d %H:%M UTC"),
                    "tail_is_dp": answered and last > body.rfind("\n---\n")})
    return out


def latest_beat() -> dict:
    """One line of context so a reply is written against what the being is actually doing,
    not against what it was doing when the question was filed."""
    try:
        rec = json.loads((INSTANCE / "heartbeats.jsonl").read_text(errors="replace")
                         .strip().splitlines()[-1])
    except Exception:
        return {}
    cfg = rec.get("config") or {}
    acts = [e for k in ("explore", "posture", "reflect")
            for e in ((rec.get(k) or {}).get("trace") or [])]
    return {"ts": rec.get("ts"), "drive": rec.get("drive_source"),
            "elapsed": rec.get("elapsed_s"),
            "harness": (rec.get("harness") or {}).get("short"),
            "ctx": cfg.get("num_ctx_resolved"),
            "acts": [f"{e['effector']}{'' if e.get('ok') else ' (refused)' if e.get('refused') else ' (error)'}"
                     for e in acts],
            "reply": ((rec.get("reflect") or {}).get("reply") or "")[:600]}


def beat_clock() -> dict:
    """When the being next wakes, and how long it is likely to take.

    dp asked "how frequent are the beats?" straight after posting a turn, which is the
    right question and one the page should not have made necessary: a conversation whose
    other party wakes on a timer needs the timer on screen, or every message feels like
    silence for reasons that have nothing to do with the being."""
    import re
    import subprocess

    def _run(*a):
        try:
            return subprocess.run(a, text=True, capture_output=True, timeout=10).stdout
        except Exception:
            return ""

    # The machine-readable form, not `list-timers`: its NEXT column contains spaces, so
    # column-splitting it produced "—" for the one number dp actually wanted.
    # `list-timers --output=json` gives raw microseconds. The two `show -p ... --value`
    # forms both failed here and failed DIFFERENTLY, which is why this is worth a comment:
    # NextElapseUSecRealtime is EMPTY for an OnUnitActiveSec timer (it is scheduled on
    # CLOCK_MONOTONIC), and NextElapseUSecMonotonic --value renders a human string
    # ("1month 6d 2h 22min"), so int() on it raises. Both rendered "—" exactly where dp
    # wanted a number.
    nxt, left = "—", "—"
    try:
        rows = json.loads(_run("systemctl", "--user", "list-timers",
                               "sage-heartbeat.timer", "--output=json") or "[]")
        usec = int(rows[0]["next"])
        when = datetime.fromtimestamp(usec / 1_000_000, timezone.utc)
        secs = int((when - datetime.now(timezone.utc)).total_seconds())
        nxt = when.strftime("%H:%M:%SZ")
        left = "now" if secs <= 0 else (f"in {secs // 60} min" if secs >= 60 else f"in {secs}s")
    except (ValueError, KeyError, IndexError, TypeError):
        pass
    running = _run("systemctl", "--user", "is-active", "sage-heartbeat.service").strip()

    import json as _j
    import statistics as _stat
    el = []
    try:
        rows = [_j.loads(l) for l in
                (INSTANCE / "heartbeats.jsonl").read_text(errors="replace").splitlines() if l.strip()]
        el = [r["elapsed_s"] for r in rows[-30:] if r.get("elapsed_s")]
    except Exception:
        pass
    return {"next": nxt, "left": left, "running": running in ("active", "activating"),
            "median_min": round(_stat.median(el) / 60, 1) if el else None}


def journal_tail(n: int = 2600) -> str:
    try:
        t = (INSTANCE / "journal.md").read_text(errors="replace")
        return t[-n:]
    except Exception:
        return ""


def append_reply(thread: str, text: str) -> Path:
    if not THREAD_RE.match(thread):
        raise ValueError(f"not one of this being's ask threads: {thread!r}")
    p = FORUM / thread
    if not p.is_file():
        raise ValueError(f"no such thread: {thread}")
    text = text.strip()
    if not text:
        raise ValueError("empty reply")
    with open(p, "a", encoding="utf-8") as f:
        f.write(f"\n\n## Reply from dp\n\n_{_now()}, via the dp console._\n\n{text}\n")
    return p


def append_note(text: str) -> Path:
    text = text.strip()
    if not text:
        raise ValueError("empty note")
    p = INSTANCE / "notes" / "from-dp.md"
    p.parent.mkdir(parents=True, exist_ok=True)
    if not p.exists():
        p.write_text("# From dp\n\ndp's own words, written directly rather than relayed by a "
                     "seat. You read this; you cannot edit it. Newest last.\n")
    with open(p, "a", encoding="utf-8") as f:
        f.write(f"\n---\n\n## {_now()}\n\n{text}\n")
    return p


def _clock_line() -> str:
    bc = beat_clock()
    if bc["running"]:
        return "<b>Beat running now</b> — it will read anything already posted."
    return (f"<b>Next beat {html.escape(bc['left'])}</b> · every 30 min ±2 · "
            f"~{bc['median_min'] or '?'} min per beat · a reply lands at the end of one")


def _kind(speaker: str) -> str:
    return "dp" if speaker == DP else ("being" if speaker.endswith("-being") else "seat")


def render_conv_list() -> str:
    """Every conversation, and — the thing dp actually needs at a glance — whose move it is."""
    rows = []
    for m in conv.listing(INSTANCE):
        writable = DP in m.get("writable_by", [])
        last = m.get("last") or {}
        turns = conv.recent(INSTANCE, m["id"], limit=1)
        pend = conv.awaiting(INSTANCE, m["id"], BEING)
        state = (f'<span class="pill ro">read-only for you</span>' if not writable
                 else '<span class="pill rw">you can speak here</span>')
        waiting = (f'<span class="pill">{len(pend)} awaiting {html.escape(BEING)}</span>'
                   if pend else "")
        rows.append(
            f'<div class="card"><div><a href="/c/{html.escape(m["id"])}"><b>{html.escape(m["title"])}</b></a>'
            f'{state}{waiting}</div>'
            f'<div class="meta">{m["count"]} turns, all kept'
            + (f' · last: <b>{html.escape(last.get("from",""))}</b> at {html.escape(last.get("ts",""))}'
               if last else " · nothing said yet")
            + f'</div><div class="meta" style="margin-top:6px">{html.escape(m.get("summary",""))}</div></div>')
    return "".join(rows) or '<div class="card meta">no conversations yet</div>'


def render_conv(conv_id: str, limit: int = conv.DEFAULT_LIMIT, flash: str = "") -> str:
    m = conv.get_meta(INSTANCE, conv_id)
    if m is None:
        return None
    total = conv.count(INSTANCE, conv_id)
    turns = conv.recent(INSTANCE, conv_id, limit=limit)
    writable = DP in m.get("writable_by", [])

    head = ""
    if total > len(turns):
        head = (f'<div class="card meta">Showing the last {len(turns)} of {total} turns. '
                f'Nothing is ever deleted — <a href="/c/{html.escape(conv_id)}?limit={total}">'
                f'show all {total}</a>.</div>')

    body = []
    for t in turns:
        who = t.get("from", "?")
        wit = (f'<span class="wit"> · witnessed {html.escape(str(t.get("witness"))[:8])}</span>'
               if t.get("witness") else "")
        body.append(
            f'<div class="turn {_kind(who)}"><span class="who">{html.escape(who)}</span>'
            f'<span class="when">{html.escape(t.get("ts",""))} · #{t.get("seq","")}</span>{wit}'
            f'<div class="text">{html.escape(t.get("text",""))}</div></div>')

    if writable:
        form = (f'<div class="card"><div class="meta">Your words go to {html.escape(BEING)} '
                f'verbatim, attributed to <b>dp</b>, and reach it at its next beat.</div>'
                f'<form method="POST" action="/say"><input type="hidden" name="to" value="{html.escape(conv_id)}">'
                f'<textarea name="text" placeholder="…"></textarea>'
                f'<button type="submit">Send</button></form></div>')
    else:
        form = ('<div class="card meta"><b>Read-only for you.</b> This is the seat\'s conversation '
                'with the being. You asked for it this way — view but not comment, until multiparty '
                'is designed carefully, because a third voice appearing mid-thread changes what the '
                'earlier turns meant.</div>')

    pend = conv.awaiting(INSTANCE, conv_id, BEING)
    note = (f'<div class="card meta">{len(pend)} turn(s) since {html.escape(BEING)} last spoke here. '
            f'It sees them in its next beat and may answer or not — saying nothing is a choice and '
            f'is recorded as one.</div>') if pend else ""

    return head + "".join(body) + note + form


PAGE = """<!doctype html><html><head><meta charset="utf-8">
<title>dp console — {being}</title>
<style>
 :root{{--bg:#0d1117;--card:#161b22;--bd:#30363d;--tx:#c9d1d9;--ac:#58a6ff;--gn:#3fb950;--am:#d29922;--mu:#8b949e}}
 *{{box-sizing:border-box}}
 body{{background:var(--bg);color:var(--tx);font:14px/1.55 ui-sans-serif,system-ui,-apple-system,sans-serif;margin:0;padding:24px}}
 .wrap{{max-width:920px;margin:0 auto}}
 h1{{font-size:19px;margin:0 0 4px}} h2{{font-size:15px;margin:22px 0 8px;color:var(--ac)}}
 .sub{{color:var(--mu);font-size:12px;margin-bottom:20px}}
 .card{{background:var(--card);border:1px solid var(--bd);border-radius:8px;padding:14px 16px;margin-bottom:14px}}
 pre{{white-space:pre-wrap;word-wrap:break-word;font:12px/1.5 ui-monospace,SFMono-Regular,Menlo,monospace;
      margin:0;max-height:340px;overflow:auto;color:var(--tx)}}
 textarea{{width:100%;min-height:110px;background:#0b0f14;color:var(--tx);border:1px solid var(--bd);
           border-radius:6px;padding:10px;font:13px/1.5 ui-monospace,monospace;resize:vertical}}
 button{{background:var(--ac);color:#04101f;border:0;border-radius:6px;padding:8px 16px;font-weight:600;
         cursor:pointer;margin-top:8px}} button:hover{{filter:brightness(1.1)}}
 .pill{{display:inline-block;font-size:11px;padding:2px 8px;border-radius:99px;border:1px solid var(--bd);margin-left:6px}}
 .wait{{color:var(--am);border-color:var(--am)}} .done{{color:var(--gn);border-color:var(--gn)}}
 .meta{{color:var(--mu);font-size:12px}} a{{color:var(--ac)}}
 .acts{{font:12px ui-monospace,monospace;color:var(--mu)}}
</style></head><body><div class="wrap">
<h1>dp console — {being}</h1>
<div class="sub">{clock}<br><a href="/conversations"><b>Conversations →</b></a> &nbsp;·&nbsp; Your words go to the being verbatim. Nothing here is relayed, summarised, or passed through a model.
 &nbsp;·&nbsp; <a href="/">refresh</a></div>
{flash}
<h2>Where it is right now</h2>
<div class="card">
 <div class="meta">beat {beat_ts} &nbsp;·&nbsp; drive <b>{beat_drive}</b> &nbsp;·&nbsp; {beat_elapsed}s
  &nbsp;·&nbsp; harness {beat_harness} &nbsp;·&nbsp; ctx {beat_ctx}</div>
 <div class="acts" style="margin-top:6px">{beat_acts}</div>
 <pre style="margin-top:10px">{beat_reply}</pre>
</div>

<h2>A note to the being</h2>
<div class="card">
 <div class="meta">Appended to <code>notes/from-dp.md</code>, which it reads at the top of every beat,
  above the seat's relay. Use this for anything that is not an answer to a specific thread.</div>
 <form method="POST" action="/note"><textarea name="text" placeholder="…"></textarea>
 <button type="submit">Send to {being}</button></form>
</div>

<h2>Its open questions to you</h2>
{threads}

<h2>Its journal, most recent</h2>
<div class="card"><pre>{journal}</pre></div>
</div></body></html>"""

CONV_SHELL = """<!doctype html><html><head><meta charset="utf-8">
<title>{title}</title>
<style>
 :root{{--bg:#0d1117;--card:#161b22;--bd:#30363d;--tx:#c9d1d9;--ac:#58a6ff;--gn:#3fb950;--am:#d29922;--mu:#8b949e;--dp:#a371f7}}
 *{{box-sizing:border-box}}
 body{{background:var(--bg);color:var(--tx);font:14px/1.6 ui-sans-serif,system-ui,-apple-system,sans-serif;margin:0;padding:24px}}
 .wrap{{max-width:900px;margin:0 auto}}
 h1{{font-size:19px;margin:0 0 4px}}
 .sub{{color:var(--mu);font-size:12px;margin-bottom:18px}}
 a{{color:var(--ac);text-decoration:none}} a:hover{{text-decoration:underline}}
 .card{{background:var(--card);border:1px solid var(--bd);border-radius:8px;padding:14px 16px;margin-bottom:12px}}
 .turn{{border-left:3px solid var(--bd);padding:2px 0 2px 12px;margin:16px 0}}
 .turn.being{{border-color:var(--gn)}} .turn.dp{{border-color:var(--dp)}} .turn.seat{{border-color:var(--ac)}}
 .who{{font-weight:600;font-size:13px}} .when{{color:var(--mu);font-size:11px;margin-left:8px}}
 .text{{white-space:pre-wrap;word-wrap:break-word;margin-top:4px}}
 .pill{{display:inline-block;font-size:11px;padding:2px 8px;border-radius:99px;border:1px solid var(--bd);margin-left:8px;color:var(--mu)}}
 .ro{{color:var(--am);border-color:var(--am)}} .rw{{color:var(--gn);border-color:var(--gn)}}
 textarea{{width:100%;min-height:100px;background:#0b0f14;color:var(--tx);border:1px solid var(--bd);
           border-radius:6px;padding:10px;font:13px/1.5 ui-monospace,monospace;resize:vertical}}
 button{{background:var(--ac);color:#04101f;border:0;border-radius:6px;padding:8px 16px;font-weight:600;cursor:pointer;margin-top:8px}}
 .meta{{color:var(--mu);font-size:12px}} .wit{{color:var(--mu);font-size:11px;font-family:ui-monospace,monospace}}
</style></head><body><div class="wrap">
<h1>{heading}</h1>
<div class="sub">{sub}</div>
{flash}
{body}
</div></body></html>"""


THREAD_BLOCK = """<div class="card">
 <div><b>{name}</b><span class="pill {cls}">{state}</span>
  <span class="meta"> · last touched {mtime}</span></div>
 <pre style="margin-top:10px">{body}</pre>
 <form method="POST" action="/reply">
  <input type="hidden" name="thread" value="{name}">
  <textarea name="text" placeholder="Your reply is appended to this thread. The being reads it in full every beat."></textarea>
  <button type="submit">Reply in this thread</button>
 </form>
</div>"""


def render(flash: str = "") -> str:
    b = latest_beat()
    ts = []
    for t in threads():
        answered = t["tail_is_dp"]
        ts.append(THREAD_BLOCK.format(
            name=html.escape(t["name"]), mtime=t["mtime"],
            cls="done" if answered else "wait",
            state="you answered last" if answered else "waiting on you",
            body=html.escape(t["body"])))
    bc = beat_clock()
    clock = (("<b>Beat running now</b> — it will read anything you have posted." if bc["running"]
              else f"<b>Next beat {html.escape(bc['left'])}</b> (at {html.escape(bc['next'])})")
             + f" &nbsp;·&nbsp; every 30 min ±2 · a beat takes ~{bc['median_min'] or '?'} min"
               " · your turn is read at the START of a beat, its reply lands at the end")
    return PAGE.format(
        clock=clock,
        being=html.escape(BEING),
        flash=f'<div class="card" style="border-color:var(--gn)">{html.escape(flash)}</div>' if flash else "",
        beat_ts=b.get("ts") or "—", beat_drive=b.get("drive") or "—",
        beat_elapsed=b.get("elapsed") or "—", beat_harness=b.get("harness") or "—",
        beat_ctx=b.get("ctx") or "—",
        beat_acts=html.escape(", ".join(b.get("acts") or []) or "no acts recorded"),
        beat_reply=html.escape(b.get("reply") or ""),
        threads="".join(ts) or '<div class="card meta">no ask threads on disk</div>',
        journal=html.escape(journal_tail()))


class Handler(BaseHTTPRequestHandler):
    def _send(self, code: int, body: str, ctype="text/html; charset=utf-8"):
        raw = body.encode()
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(raw)))
        self.end_headers()
        self.wfile.write(raw)

    def do_GET(self):
        from urllib.parse import parse_qs, urlparse
        u = urlparse(self.path)
        if u.path == "/":
            return self._send(200, render())
        if u.path == "/conversations":
            return self._send(200, CONV_SHELL.format(
                title=f"SAGE conversations — {html.escape(BEING)}",
                heading=f"Conversations with {html.escape(BEING)}",
                sub=(_clock_line() + '<br>Both directions, in one ordered record, kept forever. '
                     'You speak in your own; the seat\'s is read-only for you. '
                     '<a href="/">beat + threads</a>'),
                flash="", body=render_conv_list()))
        if u.path.startswith("/c/"):
            cid = u.path[3:]
            limit = int((parse_qs(u.query).get("limit") or [conv.DEFAULT_LIMIT])[0] or conv.DEFAULT_LIMIT)
            body = render_conv(cid, limit=limit)
            if body is None:
                return self._send(404, "no such conversation", "text/plain")
            m = conv.get_meta(INSTANCE, cid)
            return self._send(200, CONV_SHELL.format(
                title=html.escape(m["title"]),
                heading=html.escape(m["title"]),
                sub=(_clock_line() + f'<br>participants: {html.escape(", ".join(m["participants"]))} · '
                     f'<a href="/conversations">all conversations</a> · <a href="/">beat + threads</a>'),
                flash="", body=body))
        return self._send(404, "not found", "text/plain")

    def do_POST(self):
        from urllib.parse import parse_qs
        n = int(self.headers.get("Content-Length") or 0)
        form = parse_qs(self.rfile.read(n).decode(errors="replace"))
        text = (form.get("text") or [""])[0]
        try:
            if self.path == "/note":
                p = append_note(text)
                flash = f"Sent. It lands in the being's next beat, at the top: {p}"
            elif self.path == "/say":
                cid = (form.get("to") or [""])[0]
                # provenance travels with the turn: this is a loopback page, its "dp" is
                # whoever sits at this machine — asserted, not signed (GPT, SAGE#56)
                turn = conv.append(INSTANCE, cid, speaker=DP, text=text, via="dp-console")
                # A world input, not a filing. dp: "beat is default idle state. world
                # inputs require engagement." The policy lives in arousal, not here.
                from sage.gateway import arousal
                woke = arousal.respond(INSTANCE, "dp_turn",
                                       descriptor=f"dp spoke in conversation '{cid}'")
                m = conv.get_meta(INSTANCE, cid)
                body = render_conv(cid)
                return self._send(200, CONV_SHELL.format(
                    title=html.escape(m["title"]), heading=html.escape(m["title"]),
                    sub=f'participants: {html.escape(", ".join(m["participants"]))} · '
                        f'<a href="/conversations">all conversations</a>',
                    flash=f'<div class="card" style="border-color:var(--gn)">Sent as turn '
                          f'#{turn["seq"]}. '
                          + (f'<b>Waking {html.escape(BEING)} now</b> — a beat is starting for this.'
                             if woke.get("engage")
                             else f'It will be read at the next beat: {html.escape(woke["reason"])}.')
                          + '</div>',
                    body=body))
            elif self.path == "/reply":
                p = append_reply((form.get("thread") or [""])[0], text)
                flash = (f"Replied in {p.name}. It reads this thread in full every beat — "
                         "the next check will finally return something.")
            else:
                return self._send(404, "not found", "text/plain")
        except ValueError as e:
            return self._send(400, render(f"Not sent: {e}"))
        self._send(200, render(flash))

    def log_message(self, *a):
        pass


def main() -> int:
    print(f"dp console for {BEING} on http://{BIND}:{PORT}\n"
          f"  threads: {FORUM}\n  instance: {INSTANCE}", flush=True)
    ThreadingHTTPServer((BIND, PORT), Handler).serve_forever()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
