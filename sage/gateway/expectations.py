"""
expectations -- a prediction attached to an act, checked by the harness against what happened.

dp, 2026-10-10, to legion-being: "isn't it more interesting to write your own and test vs reality?
... reality doesn't usually give you source :) the goal here is to learn how to discover the workings
of the world around you." The `game` verb already ended "Predict before you read." -- an instruction
with no mechanism: nothing carried a prediction and nothing checked one. Thor's M2 pilot (2026-10-10)
and Legion's re-read trial both found that epistemic instruments kept BESIDE the act get ignored; so
this sits ON the act. The being says what it expects; the receipt says confirmed / CONTRADICTED /
unverifiable, from the result itself, never from the being's own reading of it.

Predicates for `game` (a JSON list; each is one of):
  {"probe": i, "changes": true|false}   probe i (1-based, moves only, LOOKs not counted) changes the board
  {"levels_completed": n}               after the batch
  {"state": "WIN" | "GAME_OVER" | "NOT_FINISHED"}   after the batch
  {"cell": [x, y], "value": v}          the cell reads v -- checked against the LAST LOOK in this batch
                                        that covers (x, y); with no such LOOK it is "unverifiable", not guessed
Anything else is reported as "unrecognized" (said, never silently dropped).
"""
from __future__ import annotations

import json
import re
from typing import Any, Dict, List, Optional

OUTCOMES = ("confirmed", "contradicted", "unverifiable", "unrecognized")


def parse(raw) -> List[dict]:
    """The being's `expect` arg as a list of predicates. Accepts a list, a single dict, or JSON
    text of either. Raises ValueError with a sentence the being can act on."""
    if raw is None or raw == "":
        return []
    v = raw
    if isinstance(raw, str):
        try:
            v = json.loads(raw)
        except ValueError:
            raise ValueError("expect must be JSON: a list of predicates, e.g. "
                             '[{"probe": 1, "changes": true}, {"cell": [19, 15], "value": 5}]') from None
    if isinstance(v, dict):
        v = [v]
    if not isinstance(v, list) or not all(isinstance(p, dict) for p in v):
        raise ValueError("expect must be a list of predicate objects")
    if len(v) > 16:
        raise ValueError("expect holds at most 16 predicates")
    return v


def _moves(payload: dict) -> List[dict]:
    return [p for p in (payload.get("probes") or []) if isinstance(p, dict) and "move" in p]


def _look_value(payload: dict, x: int, y: int) -> Optional[int]:
    """The value at (x, y) in the LAST LOOK window that covers it, or None."""
    for look in reversed(payload.get("looks") or []):
        w = look.get("window") or {}
        xs, ys = w.get("x") or [None, None], w.get("y") or [None, None]
        if None in xs or None in ys or not (xs[0] <= x <= xs[1] and ys[0] <= y <= ys[1]):
            continue
        for row in look.get("rows") or []:
            m = re.match(r"\s*y=(\d+):\s*(.*)$", str(row))
            if m and int(m.group(1)) == y:
                vals = m.group(2).split()
                i = x - xs[0]
                if 0 <= i < len(vals):
                    try:
                        return int(vals[i])
                    except ValueError:
                        return None
    return None


def check_game(preds: List[dict], payload: dict) -> List[Dict[str, Any]]:
    out = []
    moves = _moves(payload)
    after = payload.get("state_after") or {}
    for p in preds:
        rec = {"expect": p}
        try:
            if "probe" in p and "changes" in p:
                i = int(p["probe"])
                if not 1 <= i <= len(moves):
                    rec.update(outcome="unverifiable", observed=f"there is no move {i} in this batch ({len(moves)} moves)")
                else:
                    n = int(moves[i - 1].get("cells_changed") or 0)
                    want = bool(p["changes"])
                    rec.update(outcome="confirmed" if (n > 0) == want else "contradicted",
                               observed=f"{n} cells changed")
            elif "levels_completed" in p:
                got = after.get("levels_completed")
                rec.update(outcome="unverifiable" if got is None else
                           ("confirmed" if int(got) == int(p["levels_completed"]) else "contradicted"),
                           observed=f"levels_completed {got}")
            elif "state" in p:
                got = str(after.get("state") or "")
                want = str(p["state"]).upper()
                rec.update(outcome="unverifiable" if not got else
                           ("confirmed" if got.upper().endswith(want) else "contradicted"),
                           observed=got or "no state reported")
            elif "cell" in p and "value" in p:
                x, y = (int(c) for c in p["cell"])
                got = _look_value(payload, x, y)
                rec.update(outcome="unverifiable" if got is None else
                           ("confirmed" if got == int(p["value"]) else "contradicted"),
                           observed=("no LOOK in this batch covers that cell" if got is None
                                     else f"cell ({x},{y}) reads {got}"))
            else:
                rec.update(outcome="unrecognized", observed="not a predicate this verb checks")
        except (TypeError, ValueError) as e:
            rec.update(outcome="unrecognized", observed=f"malformed: {type(e).__name__}")
        out.append(rec)
    return out


def summary(checked: List[Dict[str, Any]]) -> str:
    """One line the being reads first: what held, and every contradiction named."""
    if not checked:
        return ""
    n = {k: sum(1 for c in checked if c["outcome"] == k) for k in OUTCOMES}
    parts = [f"{n['confirmed']} confirmed"]
    if n["contradicted"]:
        parts.append(f"{n['contradicted']} CONTRADICTED: " + "; ".join(
            f"{json.dumps(c['expect'])} -> {c['observed']}" for c in checked if c["outcome"] == "contradicted"))
    if n["unverifiable"]:
        parts.append(f"{n['unverifiable']} unverifiable")
    if n["unrecognized"]:
        parts.append(f"{n['unrecognized']} unrecognized")
    return "Your expectations: " + ", ".join(parts) + "."
