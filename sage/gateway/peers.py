"""Who a being can reach on the hub, from the roster cache, in the names beings use.

dp, 2026-10-01: "peer-peer comms via hub are the next frontier". Asked "Do you know how to reach them?", sprout-
being answered "press the designated call button": nothing in view said who its siblings were or how to reach
them, and peer_ask's `to` was free text (offline it was filled with "[name]" and with the being's own name).
The hub joined the beings as <machine>-sage; beings say <machine>-being. SAGE #317 resolves either when sending;
this module names the siblings for the being, and closes peer_ask's `to` over real names."""
from __future__ import annotations

import json
import os
from typing import List

HUMANS = {"dp", "sovereign"}


def roster_names() -> List[str]:
    """Member names as the roster cache spells them; [] when unreadable (then nothing is claimed)."""
    path = os.path.join(os.path.expanduser(os.environ.get("HUB_MESH_STATE", "~/.local/state/hub-mesh")),
                        "members.json")
    try:
        m = json.load(open(path))
        ms = m.get("members", m) if isinstance(m, dict) else m
        return [str(x.get("name")).strip() for x in ms if str(x.get("name") or "").strip()]
    except Exception:
        return []


def _machine(member: str) -> str:
    return member.lower().rsplit("-being", 1)[0] if member.lower().endswith("-being") else member.lower()


def siblings(member: str, names: List[str] = None) -> List[str]:
    """Other beings on the hub, as being-names: <m>-sage -> <m>-being, and any member already named <m>-being."""
    names = roster_names() if names is None else names
    me = _machine(member)
    out = set()
    for n in names:
        low = n.lower()
        if low.endswith("-sage"):
            out.add(low[:-len("-sage")] + "-being")
        elif low.endswith("-being"):
            out.add(low)
    return sorted(s for s in out if _machine(s) != me)


def reachable(member: str, names: List[str] = None) -> List[str]:
    """Names peer_ask can address: siblings, then other machines' seats. Never a human (people are reached
    with `say` in a conversation), never this being or its own machine's seat (its seat is a conversation)."""
    names = roster_names() if names is None else names
    me = _machine(member)
    seats = sorted({n.lower() for n in names
                    if not n.lower().endswith(("-sage", "-being")) and n.lower() not in HUMANS and n.lower() != me})
    return siblings(member, names) + seats


def sibling_line(member: str, names: List[str] = None) -> str:
    """One sentence for the being, or '' when the roster says nothing."""
    s = siblings(member, names)
    if not s:
        return ""
    return (f"Your siblings on the hub (other SAGE beings): {', '.join(s)}. You are {member.lower()}. "
            f"You reach one with peer_ask (to = its name); an answer arrives later, in your inbox, not at once.")
