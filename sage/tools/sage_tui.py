#!/usr/bin/env python3
"""sage-tui: the daemon dashboard as a terminal app (stdlib only: curses + urllib).

dp, 2026-10-08: "it's silly that something which only paints some text and bar graphs on the screen should take
half a gig of ram". The web dashboard needed a browser (Firefox ~550 MB on a 7.5 GB Sprout already in swap).
This paints the same facts in a terminal: state, ATP, SNARC salience, the current beat, the machine body
(memory first, then GPU/CPU/temperature/disk, as the console's /body panel), conversations, and an
input line that speaks as dp through the same loopback route the dp console uses. Run it ON the machine (or over
`ssh -t <machine> python3 -m sage.tools.sage_tui`): it reads 127.0.0.1, so the daemon's loopback-only rules hold.

Keys: Up/Down or j/k pick a conversation; mouse wheel or PgUp/PgDn scroll its text, End (or G) back to the newest;
i types a message (Enter sends, Esc cancels); o (or Tab) switches to the being's output stream and back; r refreshes;
q quits. With the mouse captured, select text with Shift+drag (most terminals).

THE OUTPUT STREAM PAGE (dp, 2026-11-20: "having the agent's stream in all major cli harnesses is a key feature and
liveness indicator, which sage has left out so far"). Each beat's model calls stream into <instance>/
output_stream.jsonl (sage.gateway.being_stream); this page shows it as it is written: per beat, each call's turn,
its thinking, its words, the tools it called and how the call ended, and at the top whether output is arriving now.
It reads the file directly (the instance path comes from the daemon's /conversations), so it is as local as the
rest of this app.
"""
from __future__ import annotations

import json
import os
import textwrap
import time
import urllib.error
import urllib.request

BASE = os.environ.get("SAGE_TUI_BASE", "http://127.0.0.1:8760")
REFRESH_S = 2.0
TURNS = 300            # enough history to scroll back through


def fetch(path: str, body: dict | None = None, timeout: float = 3.0):
    """(json, error). Never raises: a dashboard that crashes on a slow daemon shows nothing."""
    req = urllib.request.Request(BASE + path, data=json.dumps(body).encode() if body is not None else None,
                                 headers={"Content-Type": "application/json"} if body is not None else {})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return json.loads(r.read() or b"{}"), None
    except urllib.error.HTTPError as e:
        try:
            return json.loads(e.read() or b"{}"), f"HTTP {e.code}"
        except Exception:
            return {}, f"HTTP {e.code}"
    except Exception as e:
        return {}, f"{type(e).__name__}: {e}"[:120]


def bar(frac: float, width: int) -> str:
    frac = max(0.0, min(1.0, float(frac or 0)))
    full = int(round(frac * width))
    return "█" * full + "·" * (width - full)


def header_lines(health: dict, status: dict, width: int) -> list[str]:
    """The top of the screen: what state the being is in, and why."""
    st = status.get("metabolic_state") or health.get("metabolic_state") or "?"
    age = status.get("metabolic_age_secs")
    src = status.get("metabolic_source") or ""
    atp = float(status.get("atp_percentage") or health.get("atp_level") or 0)
    beats = status.get("beats") or {}
    cur = beats.get("current") or {}
    out = [f"sage-tui  {health.get('model', '?')}  build {str(health.get('build', '?'))[:28]}",
           f"state {st:<10} ({age}s, {src})   ATP {bar(atp / 100.0, 20)} {atp:5.1f}%",
           (f"beat {cur.get('beat_id', '')[-12:]} phase {cur.get('phase', '?')} age {cur.get('age_secs', '?')}s"
            if cur else f"no beat running; last ended {beats.get('since_last_beat_end_secs', '?')}s ago")
           + f"   beats completed {beats.get('completed', health.get('beats_completed', '?'))}"]
    sal = status.get("salience") or {}
    if sal:
        cols = [f"{k[:4]} {bar(v, 6)}" for k, v in sal.items() if k != "total" and isinstance(v, (int, float))]
        out.append("salience " + "  ".join(cols) + f"   total {float(sal.get('total') or 0):.2f}")
    return [l[:width] for l in out]


GIB = 1024 ** 3


def _v(d: dict, *keys):
    """A sampled value from the body snapshot ({"value": x, "source": ...}), or None when unsensed."""
    for k in keys:
        d = (d or {}).get(k) if isinstance(d, dict) else None
    return d.get("value") if isinstance(d, dict) else None


def _same_model(a: str, b: str) -> bool:
    """The daemon's tag rule (sage-daemon same_model, #433): exact, with a bare name meaning `:latest`."""
    norm = lambda m: m.strip() if ":" in m else m.strip() + ":latest"  # noqa: E731
    return bool(a.strip()) and norm(a) == norm(b)


def body_lines(body: dict, health: dict, width: int) -> list[str]:
    """The machine's metabolism, as the web console shows it (dp 2026-10-18), memory first.

    Memory is a bar, not a number: on a unified-memory machine the being's model, the cortex, the seat and
    a browser all draw on one pool, and that pool is the first thing to run out (Firefox ~550 MB on a 7.5 GB
    Sprout, the reason this TUI exists). The rest is the sampler's own `line` (one renderer, in the
    sampler; the console renders the same string), minus its RAM part, which the bar replaces. A snapshot
    that cannot be read says so; it is never drawn as zero."""
    if not body or not body.get("line"):
        why = (body or {}).get("unavailable") or "the daemon did not answer /body"
        return [f"body: not sensed ({why})"[:width]]
    mem = body.get("memory") or {}
    total, used = _v(mem, "total_bytes"), _v(mem, "used_bytes")
    out = []
    if total and used is not None:
        pool = " one pool, GPU incl." if mem.get("pool") == "unified" else ""
        avail = _v(mem, "available_bytes")
        swap_t, swap_u = _v(mem, "swap_total_bytes"), _v(mem, "swap_used_bytes")
        frac = used / total
        out.append(f"RAM  {bar(frac, 20)} {used / GIB:.1f}/{total / GIB:.1f} GiB {frac * 100:3.0f}%{pool}"
                   + (f"  avail {avail / GIB:.1f}" if avail is not None else "")
                   + (f"  swap {swap_u / GIB:.1f}/{swap_t / GIB:.1f}" if swap_t else ""))
    else:
        out.append("RAM  not sensed")
    # The sampler writes RAM inside the CPU segment ("CPU 52% · 62°C · RAM 2.8/7.4 GiB (…) (+3.5 GiB swap)"):
    # drop only that part, or the CPU reading goes with it.
    rest = []
    for seg in str(body["line"]).split(" | "):
        if seg.startswith("memory:"):
            continue
        keep = [p for p in seg.split(" · ") if not p.startswith("RAM ")]
        if keep:
            rest.append(" · ".join(keep))
    loaded = health.get("loaded_models")
    if loaded is not None:
        # The daemon's own answer (`model_loaded`, #433's same_model) is the contract. Its fallback is the same
        # rule: exact identity, with only a bare name meaning `:latest` -- never the family before the colon,
        # which reported qwen:2b as qwen:4b loaded (NOVA on #469).
        here = health.get("model_loaded")
        if here is None:
            here = any(_same_model(str(m), str(health.get("model") or "")) for m in loaded)
        rest.append(f"model {'loaded' if here else 'not loaded'}" + (f" ({', '.join(map(str, loaded))})" if loaded else ""))
    age = body.get("served_age_s")
    rest.append(f"sampled {age:.0f}s ago" if isinstance(age, (int, float)) else "age unknown")
    out.append("  ".join(rest))
    return [l[:width] for l in out]


def conversation_rows(listing: dict) -> list[dict]:
    return list((listing or {}).get("conversations") or [])


def turn_lines(conv: dict, width: int) -> list[str]:
    """A conversation's turns, wrapped, newest last. A trial label is shown beside the words, never in them."""
    out = []
    for t in (conv or {}).get("turns") or []:
        who = t.get("from", "?")
        tag = f" [TEST {t['trial']}]" if t.get("trial") else ""
        head = f"{str(t.get('ts', ''))[11:19]} {who}{tag}:"
        body = textwrap.wrap(" ".join(str(t.get("text", "")).split()), max(20, width - 4)) or [""]
        out.append(head[:width])
        out.extend(("    " + b)[:width] for b in body)
    return out


STREAM_FILE = "output_stream.jsonl"
STREAM_TAIL_BYTES = 256 * 1024
LIVE_S = 5.0               # output this recent means the being is producing now


def read_stream(path: str, max_bytes: int = STREAM_TAIL_BYTES) -> list:
    """The last events of the output stream, oldest first. Never raises; a missing file is no events."""
    try:
        with open(path, "rb") as f:
            f.seek(0, os.SEEK_END)
            size = f.tell()
            f.seek(max(0, size - max_bytes))
            data = f.read()
    except OSError:
        return []
    lines = data.split(b"\n")
    if size > max_bytes and not _starts_a_line(path, size - max_bytes):
        lines = lines[1:]              # cut by the window
    out = []
    for l in lines:
        try:
            out.append(json.loads(l))
        except ValueError:
            continue
    return out


def _starts_a_line(path: str, at: int) -> bool:
    """Whether byte `at` begins a line (the byte before it is a newline), so a window starting there is not cut."""
    try:
        with open(path, "rb") as f:
            f.seek(at - 1)
            return f.read(1) == b"\n"
    except OSError:
        return False


def _hms(t) -> str:
    try:
        return time.strftime("%H:%M:%S", time.gmtime(float(t)))
    except (TypeError, ValueError):
        return "??:??:??"


def stream_status(events: list, now: float) -> str:
    """One line: is the being producing output right now, and what it is doing."""
    if not events:
        return "○ no output recorded yet (the stream starts with the next beat)"
    last = events[-1]
    age = max(0.0, now - float(last.get("t") or 0))
    turn = next((e.get("turn") for e in reversed(events) if e.get("k") == "call"), "") or "?"
    k = last.get("k")
    if k == "end":
        return f"○ resting: last beat ended {_ago(age)} ago"
    if k == "beat":
        return f"◐ beat starting ({_ago(age)} ago), no model call yet"
    if k in ("think", "text", "tool", "call") and age <= LIVE_S:
        doing = {"think": "thinking", "text": "writing", "tool": "calling a tool", "call": "waiting for the model"}[k]
        return f"● live: {doing} ({turn})"
    if k in ("think", "text", "tool", "call"):
        return f"◐ in a beat, no output for {_ago(age)} ({turn})"
    return f"◐ in a beat ({turn}), last call ended {_ago(age)} ago"


def _ago(s: float) -> str:
    s = int(s)
    return f"{s}s" if s < 120 else f"{s // 60}m" if s < 7200 else f"{s // 3600}h"


def stream_lines(events: list, width: int) -> list:
    """The stream as lines: a rule per beat, a heading per call, its thinking (marked │), its words, its tool
    calls (⚙) and how it ended. Pieces of one kind that arrived in a row are one paragraph."""
    out = []
    w = max(20, width)
    blocks = []                                   # (kind, text) with consecutive think/text joined
    for e in events:
        k = e.get("k")
        if k in ("think", "text"):
            piece = str(e.get("s") or "")
            if blocks and blocks[-1][0] == k:
                blocks[-1] = (k, blocks[-1][1] + piece)
            else:
                blocks.append((k, piece))
        else:
            blocks.append((k, e))
    for k, e in blocks:
        if k == "beat":
            head = f"── beat {str(e.get('beat', ''))[-12:]}  {_hms(e.get('t'))}Z  {e.get('model') or ''} "
            out.append((head + "─" * max(0, w - len(head)))[:w])
        elif k == "call":
            out.append(f"▸ {e.get('turn') or '?'} · {e.get('phase') or ''}  {_hms(e.get('t'))}Z"[:w])
        elif k in ("think", "text"):
            text = e
            mark = "  │ " if k == "think" else "    "
            for para in text.split("\n"):
                for piece in (textwrap.wrap(para, max(10, w - len(mark))) or ([""] if para == "" else [])):
                    out.append((mark + piece)[:w])
        elif k == "tool":
            out.append(f"  ⚙ {e.get('name')}({' '.join(str(e.get('args') or '').split())})"[:w])
        elif k == "done":
            n = e.get("eval_count")
            out.append(f"  ✓ {e.get('reason') or 'done'} · {n if n is not None else '?'} tokens · "
                       f"{e.get('s_elapsed', '?')}s"[:w])
        elif k == "error":
            out.append(f"  ✗ {' '.join(str(e.get('s') or '').split())}"[:w])
        elif k == "end":
            out.append(f"── beat ended {_hms(e.get('t'))}Z"[:w])
    return out


def writable(meta: dict) -> bool:
    return "dp" in ((meta or {}).get("writable_by") or [])


class TuiState:
    """Selection and composition, by conversation ID (GPT on #398, issue #399).

    The list refreshes every REFRESH_S and reorders as conversations get turns. Tracking the selection by
    list INDEX let a reorder during typing send dp's message to whatever conversation now sat at that index.
    Here the selection is an ID; composing pins the destination ID for that draft; send re-reads that
    conversation and refuses (keeping the draft) if it is gone or no longer writable. Never retargets."""

    def __init__(self):
        self.sel_id = None
        self.target = None          # pinned destination while composing
        self.draft = ""
        self.flash = ""
        self.scroll = 0             # lines scrolled UP from the newest; 0 = following the bottom
        self.page = "conversations"  # or "stream": the being's output as it is produced

    def toggle_page(self) -> None:
        """Conversations <-> output stream. Not while composing: the draft's destination stays on screen."""
        if self.typing:
            return
        self.page = "stream" if self.page == "conversations" else "conversations"
        self.scroll = 0

    def scroll_by(self, delta: int, total: int, room: int) -> None:
        """Scroll the conversation text (dp 2026-10-08: the wheel switched conversations instead). Positive =
        older. Clamped so the top of the history stops at the top of the pane."""
        self.scroll = max(0, min(self.scroll + delta, max(0, total - room)))

    def window(self, lines: list, room: int) -> list:
        """The lines to show: the bottom `room` lines, shifted up by `scroll`. A refresh that adds turns keeps
        what dp is reading in place by growing the offset (see grew)."""
        if room <= 0:
            return []
        end = len(lines) - self.scroll
        return lines[max(0, end - room):end]

    def grew(self, added: int) -> None:
        """New lines arrived while scrolled up: keep the same text on screen instead of yanking to the bottom."""
        if self.scroll > 0 and added > 0:
            self.scroll += added

    @property
    def typing(self) -> bool:
        return self.target is not None

    def update(self, rows: list) -> None:
        ids = [c.get("id") for c in rows]
        if self.sel_id not in ids:
            self.sel_id = ids[0] if ids else None

    def move(self, rows: list, delta: int) -> None:
        ids = [c.get("id") for c in rows]
        if not ids or self.typing:
            return
        i = ids.index(self.sel_id) if self.sel_id in ids else 0
        self.sel_id = ids[(i + delta) % len(ids)]
        self.scroll = 0                                  # a different conversation starts at its newest turn

    def begin(self, meta: dict) -> bool:
        """Pin the destination: only the conversation actually on screen, and only if dp may write there."""
        if self.typing or not writable(meta) or meta.get("id") != self.sel_id:
            return False
        self.target, self.draft = meta["id"], ""
        return True

    def cancel(self) -> None:
        self.target, self.draft = None, ""

    def send(self, fetch_fn=None) -> bool:
        """Post the draft to the PINNED target. Refuses visibly (draft kept) if that conversation is gone or
        not writable now; never sends anywhere else."""
        fetch_fn = fetch_fn or fetch
        if not self.typing or not self.draft.strip():
            return False
        cur, err = fetch_fn(f"/conversations/{self.target}?limit=1")
        if err or not writable((cur or {}).get("meta") or {}):
            why = (cur or {}).get("error") or err or "no longer writable by dp"
            self.flash = f"NOT sent: '{self.target}' {why}. Draft kept; Esc to discard."
            return False
        d, e = fetch_fn(f"/conversations/{self.target}/say", {"message": self.draft.strip(), "from": "dp"})
        if e:
            self.flash = f"NOT sent to '{self.target}': {d.get('error') or e}. Draft kept."
            return False
        self.flash = f"sent to '{self.target}' ({d.get('delivery', '')})"
        self.target, self.draft = None, ""
        return True


MIN_W, MIN_H = 40, 8


def run(stdscr) -> None:  # pragma: no cover - exercised by hand; TuiState and the renderers are tested
    import curses
    curses.curs_set(0)
    stdscr.timeout(int(REFRESH_S * 1000))
    stdscr.keypad(True)
    WHEEL_UP = getattr(curses, "BUTTON4_PRESSED", 0x80000)
    WHEEL_DOWN = getattr(curses, "BUTTON5_PRESSED", 0x200000)
    curses.mousemask(WHEEL_UP | WHEEL_DOWN)            # wheel events, not arrow keys (terminal-dependent)
    st = TuiState()
    nlines = 0
    last = 0.0
    health = status = listing = conv = body = {}
    events = []
    err = None
    while True:
        # the stream page reads its file four times a second, so output shows as it arrives
        stdscr.timeout(250 if st.page == "stream" else int(REFRESH_S * 1000))
        inst = os.environ.get("SAGE_TUI_INSTANCE") or (listing or {}).get("instance")
        events = read_stream(os.path.join(inst, STREAM_FILE)) if inst else []
        if time.time() - last >= REFRESH_S:
            health, _ = fetch("/health")
            status, _ = fetch("/status")
            body, body_err = fetch("/body")
            if body_err and not body.get("unavailable"):
                body = {"unavailable": body_err}
            listing, err = fetch("/conversations")
            st.update(conversation_rows(listing))
            conv = fetch(f"/conversations/{st.sel_id}?limit={TURNS}")[0] if st.sel_id else {}
            last = time.time()
        convs = conversation_rows(listing)
        h, w = stdscr.getmaxyx()
        stdscr.erase()
        if h < MIN_H or w < MIN_W:
            try:
                stdscr.addnstr(0, 0, "terminal too small", max(1, w - 1))
            except curses.error:
                pass
            stdscr.refresh()
            if stdscr.getch() in (ord("q"), ord("Q")):
                return
            continue
        top = header_lines(health, status, w - 1) + body_lines(body, health, w - 1)
        live = stream_status(events, time.time())
        top.append(("output " + live)[:w - 1])
        for i, l in enumerate(top):
            stdscr.addnstr(i, 0, l, w - 1, curses.A_BOLD if i in (0, len(top) - 1) and (i == 0 or "●" in l) else 0)
        y0 = len(top) + 1
        if st.page == "stream":
            room = h - y0 - 2
            lines = stream_lines(events, w - 1)
            if nlines and len(lines) > nlines:
                st.grew(len(lines) - nlines)
            nlines = len(lines)
            st.scroll_by(0, len(lines), room)
            if not lines:
                stdscr.addnstr(y0, 0, ("no output stream at " + os.path.join(inst, STREAM_FILE) if inst else
                                       "no instance path yet (the daemon's /conversations gives it)")[:w - 1], w - 1)
            for i, l in enumerate(st.window(lines, room)):
                attr = curses.A_DIM if l.startswith("  │") else curses.A_BOLD if l.startswith(("──", "▸")) else 0
                stdscr.addnstr(y0 + i, 0, l, w - 1, attr)
            up = f"[↑ {st.scroll} lines up — End: newest]  " if st.scroll else ""
            stdscr.addnstr(h - 1, 0, (up + "OUTPUT STREAM  o/Tab: conversations  wheel/PgUp/PgDn: scroll  q: quit")
                           [:w - 1], w - 1, curses.A_REVERSE)
            stdscr.refresh()
            k = stdscr.getch()
            if k == -1:
                continue
            page = max(1, room - 1)
            if k == curses.KEY_MOUSE:
                try:
                    _, _, _, _, bstate = curses.getmouse()
                except curses.error:
                    continue
                if bstate & WHEEL_UP:
                    st.scroll_by(+3, len(lines), room)
                elif bstate & WHEEL_DOWN:
                    st.scroll_by(-3, len(lines), room)
            elif k == curses.KEY_PPAGE:
                st.scroll_by(+page, len(lines), room)
            elif k == curses.KEY_NPAGE:
                st.scroll_by(-page, len(lines), room)
            elif k == curses.KEY_END or k == ord("G"):
                st.scroll = 0
            elif k in (ord("o"), ord("O"), 9):
                st.toggle_page(); nlines = 0
            elif k in (ord("r"), ord("R")):
                last = 0.0
            elif k in (ord("q"), ord("Q")):
                return
            continue
        left = 22
        if err and not convs:
            stdscr.addnstr(y0, 0, f"conversations not readable: {listing.get('error') or err}", w - 1)
        for i, c in enumerate(convs[: max(0, h - y0 - 2)]):
            on = c.get("id") == st.sel_id
            wait = f" +{c.get('awaiting_being')}" if c.get("awaiting_being") else ""
            stdscr.addnstr(y0 + i, 0, f"{'>' if on else ' '}{c['id'][:14]:<14}{c.get('count', ''):>4}{wait}",
                           left - 1, curses.A_REVERSE if on else 0)
        lines = turn_lines(conv, w - left - 1)
        room = h - y0 - 2
        if nlines and len(lines) > nlines:
            st.grew(len(lines) - nlines)
        nlines = len(lines)
        st.scroll_by(0, len(lines), room)               # re-clamp after a resize or a shorter conversation
        for i, l in enumerate(st.window(lines, room)):
            stdscr.addnstr(y0 + i, left, l, w - left - 1)
        meta = (conv or {}).get("meta") or {}
        up = f"[↑ {st.scroll} lines up — End: newest]  " if st.scroll else ""
        foot = (f"to {st.target}> {st.draft}" if st.typing else
                st.flash or (up + ("i: write  ↑↓: conversation  o: output stream  wheel/PgUp/PgDn: scroll  q: quit"
                                   if writable(meta) else
                                   "(read-only here)  ↑↓: conversation  o: output stream  wheel/PgUp/PgDn: scroll  "
                                   "q: quit")))
        stdscr.addnstr(h - 1, 0, foot[-(w - 1):], w - 1, curses.A_REVERSE)
        stdscr.refresh()
        k = stdscr.getch()
        if k == -1:
            continue
        page = max(1, room - 1)
        if k == curses.KEY_MOUSE:
            try:
                _, _, _, _, bstate = curses.getmouse()
            except curses.error:
                continue
            if bstate & WHEEL_UP:
                st.scroll_by(+3, len(lines), room)
            elif bstate & WHEEL_DOWN:
                st.scroll_by(-3, len(lines), room)
            continue
        if k == curses.KEY_PPAGE:
            st.scroll_by(+page, len(lines), room); continue
        if k == curses.KEY_NPAGE:
            st.scroll_by(-page, len(lines), room); continue
        if k == curses.KEY_END or (k == ord("G") and not st.typing):
            st.scroll = 0; continue
        if st.typing:
            if k in (10, 13):
                if st.send():
                    last = 0.0
            elif k == 27:
                st.cancel()
            elif k in (curses.KEY_BACKSPACE, 127, 8):
                st.draft = st.draft[:-1]
            elif 32 <= k < 0x110000:
                st.draft += chr(k)
            continue
        st.flash = ""
        if k in (ord("q"), ord("Q")):
            return
        if k in (curses.KEY_DOWN, ord("j")):
            st.move(convs, +1); last = 0.0
        elif k in (curses.KEY_UP, ord("k")):
            st.move(convs, -1); last = 0.0
        elif k in (ord("r"), ord("R")):
            last = 0.0
        elif k in (ord("i"), ord("I")):
            st.begin(meta)
        elif k in (ord("o"), ord("O"), 9):
            st.toggle_page(); nlines = 0


def main() -> None:
    import curses
    curses.wrapper(run)


if __name__ == "__main__":
    main()
