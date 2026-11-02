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
                                        (JSON true/false; the string "false" is unrecognized, not false)
  {"levels_completed": n}               after the batch
  {"state": "WIN" | "GAME_OVER" | "NOT_FINISHED"}   after the batch, compared exactly (no suffix match)
  {"cell": [x, y], "value": v}          the cell reads v -- checked against the LAST LOOK in this batch
                                        that covers (x, y); with no such LOOK it is "unverifiable", not guessed
Each predicate is exactly one of these key sets, with JSON types. Anything else is reported as
"unrecognized", with the reason (said, never silently dropped or coerced).
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


# THE SCHEMA IS TYPED, NOT TRUTHY (NOVA HOLD at 3a4c2d7a). `bool("false")` is True, and
# `"GameState.WIN".endswith("")` is True: a prediction of the string "false", or of an empty state,
# was CONFIRMED by any result. Each predicate must be exactly one of these key sets, with JSON types
# (a boolean is true/false, never a string; an integer is never a boolean); anything else is
# "unrecognized" with the reason, never coerced into a claim the being did not make.
STATES = ("WIN", "GAME_OVER", "NOT_FINISHED")
_SCHEMAS = ({"probe", "changes"}, {"levels_completed"}, {"state"}, {"cell", "value"})


class _Malformed(ValueError):
    pass


def _int(v, what: str) -> int:
    if isinstance(v, bool) or not isinstance(v, int):
        raise _Malformed(f"{what} must be a whole number, not {json.dumps(v)}")
    return v


def _bool(v, what: str) -> bool:
    if not isinstance(v, bool):
        raise _Malformed(f"{what} must be true or false (JSON), not {json.dumps(v)}")
    return v


def _state(v, what: str) -> str:
    """One of STATES, exactly. The game reports `GameState.<NAME>`; that one prefix is the only
    spelling it is canonicalised from. Case is not folded, so "win" is not WIN."""
    if not isinstance(v, str):
        raise _Malformed(f"{what} must be one of {', '.join(STATES)}, not {json.dumps(v)}")
    name = v[len("GameState."):] if v.startswith("GameState.") else v
    if name not in STATES:
        raise _Malformed(f"{what} must be one of {', '.join(STATES)}, not {json.dumps(v)}")
    return name


def check_game(preds: List[dict], payload: dict) -> List[Dict[str, Any]]:
    out = []
    moves = _moves(payload)
    after = payload.get("state_after") or {}
    for p in preds:
        rec = {"expect": p}
        try:
            keys = set(p) if isinstance(p, dict) else None
            if keys not in _SCHEMAS:
                rec.update(outcome="unrecognized", observed=(
                    "not a predicate this verb checks: use exactly one of "
                    + "; ".join("{" + ", ".join(sorted(k)) + "}" for k in _SCHEMAS)))
            elif keys == {"probe", "changes"}:
                i, want = _int(p["probe"], "probe"), _bool(p["changes"], "changes")
                if not 1 <= i <= len(moves):
                    rec.update(outcome="unverifiable", observed=f"there is no move {i} in this batch ({len(moves)} moves)")
                else:
                    n = moves[i - 1].get("cells_changed")
                    if isinstance(n, bool) or not isinstance(n, int):
                        rec.update(outcome="unverifiable", observed="the move reported no cell count")
                    else:
                        rec.update(outcome="confirmed" if (n > 0) == want else "contradicted",
                                   observed=f"{n} cells changed")
            elif keys == {"levels_completed"}:
                want = _int(p["levels_completed"], "levels_completed")
                got = after.get("levels_completed")
                if isinstance(got, bool) or not isinstance(got, int):
                    rec.update(outcome="unverifiable", observed=f"levels_completed {json.dumps(got)}")
                else:
                    rec.update(outcome="confirmed" if got == want else "contradicted",
                               observed=f"levels_completed {got}")
            elif keys == {"state"}:
                want = _state(p["state"], "state")
                raw = after.get("state")
                try:
                    got = _state(raw, "the reported state")
                except _Malformed:
                    rec.update(outcome="unverifiable", observed=f"the game reported no known state ({json.dumps(raw)})")
                else:
                    rec.update(outcome="confirmed" if got == want else "contradicted", observed=got)
            else:  # {"cell", "value"}
                c = p["cell"]
                if not isinstance(c, list) or len(c) != 2:
                    raise _Malformed(f"cell must be [x, y], not {json.dumps(c)}")
                x, y = _int(c[0], "cell x"), _int(c[1], "cell y")
                want = _int(p["value"], "value")
                got = _look_value(payload, x, y)
                rec.update(outcome="unverifiable" if got is None else
                           ("confirmed" if got == want else "contradicted"),
                           observed=("no LOOK in this batch covers that cell" if got is None
                                     else f"cell ({x},{y}) reads {got}"))
        except _Malformed as e:
            rec.update(outcome="unrecognized", observed=f"malformed: {e}")
        except (TypeError, ValueError, KeyError) as e:
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
