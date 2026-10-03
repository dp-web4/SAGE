"""The SAGE-canonical toolset: every being is offered every verb.

dp, 2026-09-29: "we need a sage-canonical toolset that every being is offered. not all will
choose to use every tool, and some may not be able to. but the tools should be there for all."

Until this module, what a being was OFFERED depended on the launcher and the machine: the
heartbeat's explore turn offered a filtered list (body verbs only where the body had the part,
worktree verbs only with a worktree, no PR verbs and no `game` at all on main), governed_turn
offered the registry minus `game`, and the raising sessions offered the whole registry with no
word about what could work. A verb in the registry but not in the offered set is a verb the
being does not have. So on main a being on Sprout or Nomad could not open a pull request or
play ARC, whatever its gate would have allowed.

THE RULE NOW: every verb in the registry is offered, everywhere, by every launcher, from this
one list. What differs by machine is AVAILABILITY, and availability is SAID, never enacted by
hiding the verb. GPT's point on #183 ("offering gaze to a headless being is a false
affordance") stands, and is met by honesty instead of omission: a verb that cannot work here
is offered with a one-line description that says why ("On this machine: no camera"), and its
parameters stay intact, so calling it still returns the reason from the verb itself.

Why a short description for the unavailable ones: the full toolset is ~19k chars of schema,
and a being on a small window cannot spend a third of it on verbs it cannot use. Full text for
what can work, one line for what cannot. Nothing is hidden, and the cost follows use.

Phase-specific turns are not the toolset. The heartbeat's reflect and answer phases narrow what
they offer, because a phase has a purpose (write your record; answer the one turn waiting).
That narrowing is about the beat's structure, not about which being this is.
"""
from typing import Dict, List, Optional

from sage.gateway.being_gate_client import _TOOL_SCHEMAS

# Verbs that act on a BODY part, and the part the measured inventory must carry for them.
BODY_VERBS = ("camera", "gaze", "speak", "pair_audio")
# Verbs that act in the being's own git worktree.
WORKTREE_VERBS = ("git_read", "search", "check", "patch_apply", "git_restore", "pr_open", "pr_amend", "pr_sync", "git_clean")


def canonical_toolset() -> List[str]:
    """Every verb, in registry order, with `rest` last: the being's own way to stop is the
    last choice on the list, never the first thing it reads."""
    names = [n for n in _TOOL_SCHEMAS if n != "rest"]
    return names + (["rest"] if "rest" in _TOOL_SCHEMAS else [])


def unavailable(body_reading: Optional[dict] = None, worktree: Optional[str] = None,
                cfg: Optional[dict] = None) -> Dict[str, str]:
    """{verb: why it cannot work on THIS machine}, from what was measured. A verb absent from
    the result is available. `body_reading` is body.reading() (None = not measured: body verbs
    are then reported as unmeasured, not as absent)."""
    out: Dict[str, str] = {}
    inv = (body_reading or {}).get("inventory") if body_reading is not None else None
    have = set((inv or {}).get("verbs") or [])
    for v in BODY_VERBS:
        if v not in _TOOL_SCHEMAS:
            continue
        if inv is None:
            out[v] = "availability unknown: this machine's body was not measured this turn"
        elif v not in have:
            part = {"camera": "camera", "gaze": "movable eyes (no gaze-capable cortex is running)",
                    "speak": "speaker it can drive (a speaker, and a speech engine to feed it)",
                    "pair_audio": "audio link to pair"}.get(v, "such part")
            out[v] = f"this machine's body has no {part} (measured)"
    if not worktree:
        for v in WORKTREE_VERBS:
            if v in _TOOL_SCHEMAS:
                out[v] = "you have no git worktree on this seat (instance.json declares none)"
    if "game" in _TOOL_SCHEMAS and not (cfg or {}).get("game_stepper"):
        out["game"] = "no game is set up on this seat (instance.json has no game_stepper)"
    return out


def specs(unavail: Optional[Dict[str, str]] = None, enums: Optional[Dict[tuple, list]] = None) -> List[dict]:
    """The Ollama tool specs for the whole canonical toolset. Available verbs carry their full
    description; an unavailable one carries one line and the reason, parameters intact."""
    unavail = unavail or {}
    # CLOSED VALUE SETS reach the explore turn too (2026-10-01): SAGE #312 put gaze.mode / git_read.op enums
    # in ollama_tools(), but explore is built here, so they never reached the turn where gaze is used.
    # `enums` adds per-beat sets, e.g. {("peer_ask", "to"): the siblings and seats this being can reach}.
    from sage.gateway.being_gate_client import _param_enums
    closed = {**_param_enums(), **(enums or {})}
    out = []
    for name in canonical_toolset():
        desc, props, required = _TOOL_SCHEMAS[name]
        if name in unavail:
            first = desc.split(". ")[0].rstrip(".")
            desc = (f"{first}. ON THIS MACHINE IT CANNOT WORK: {unavail[name]}. Offered because "
                    f"every being has the whole toolset; calling it says the same.")
            # the parameter NAMES stay (the verb is callable, and says why it cannot work); their
            # long descriptions go, since they are what made an unusable verb cost ~700 chars
            properties = {k: {"type": "string"} for k in props}
        else:
            properties = {k: dict({"type": "string", "description": v},
                                  **({"enum": list(closed[(name, k)])} if closed.get((name, k)) else {}))
                          for k, v in props.items()}
        out.append({"type": "function", "function": {
            "name": name, "description": desc,
            "parameters": {"type": "object", "properties": properties, "required": required}}})
    return out
