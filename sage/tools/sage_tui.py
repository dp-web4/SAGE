#!/usr/bin/env python3
"""sage-tui: the daemon dashboard as a terminal app (stdlib only: curses + urllib).

dp, 2026-10-08: "it's silly that something which only paints some text and bar graphs on the screen should take
half a gig of ram". The web dashboard needed a browser (Firefox ~550 MB on a 7.5 GB Sprout already in swap).
This paints the same facts in a terminal: state, ATP, SNARC salience, the current beat, conversations, and an
input line that speaks as dp through the same loopback route the dp console uses. Run it ON the machine (or over
`ssh -t <machine> python3 -m sage.tools.sage_tui`): it reads 127.0.0.1, so the daemon's loopback-only rules hold.

Keys: Up/Down or j/k pick a conversation, i types a message (Enter sends, Esc cancels), r refreshes, q quits.
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
TURNS = 60


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
    st = TuiState()
    last = 0.0
    health = status = listing = conv = {}
    err = None
    while True:
        if time.time() - last >= REFRESH_S:
            health, _ = fetch("/health")
            status, _ = fetch("/status")
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
        top = header_lines(health, status, w - 1)
        for i, l in enumerate(top):
            stdscr.addnstr(i, 0, l, w - 1, curses.A_BOLD if i == 0 else 0)
        y0 = len(top) + 1
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
        for i, l in enumerate(lines[-room:] if room > 0 else []):
            stdscr.addnstr(y0 + i, left, l, w - left - 1)
        meta = (conv or {}).get("meta") or {}
        foot = (f"to {st.target}> {st.draft}" if st.typing else
                st.flash or ("i: write  ↑↓: conversation  r: refresh  q: quit" if writable(meta)
                             else "(read-only here)  ↑↓: conversation  r: refresh  q: quit"))
        stdscr.addnstr(h - 1, 0, foot[-(w - 1):], w - 1, curses.A_REVERSE)
        stdscr.refresh()
        k = stdscr.getch()
        if k == -1:
            continue
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


def main() -> None:
    import curses
    curses.wrapper(run)


if __name__ == "__main__":
    main()
