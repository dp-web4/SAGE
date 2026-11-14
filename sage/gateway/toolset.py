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
# The one-line reason for each worktree verb, short because it is paid every
# turn. The old line, "you have no git worktree on this seat (instance.json declares none)",
# names a config file and so reads as a step someone could take; cbp-being asked dp three times
# for a worktree so `search` could find lines in its own scratch file, which search can never
# read. Each line says what the verb reads and which tool serves the being's own files. The
# full refusal the verb itself returns is being_gate_client.NO_WORKTREE_REFUSAL.
#: Worktree verbs that still work with no worktree, on another target, so they are NOT marked
#: unavailable there. search reads a grant outside the home by absolute path (CBP, 2026-10-21:
#: 15 refused searches in 12 beats on the governance snapshot it holds read grants for).
REACH_VERBS = ("search",)
NO_WORKTREE_HERE = {
    "search": ("it searches a code-repository checkout (a worktree), or with none a folder outside "
               "your home that you hold a grant for, by absolute path; not your home: to find a "
               "line in your own files use memory_read with path and find"),
    "git_read": ("it reads the git history of a code-repository checkout (a worktree), not "
                 "your home, and this seat has none; to read your own files use memory_read"),
    "check": ("it runs the test suites of a code-repository checkout (a worktree), not your "
              "home, and this seat has none; to run one of your own files use run"),
    "patch_apply": ("it changes files in a code-repository checkout (a worktree), not your "
                    "home, and this seat has none; to change lines of your own files use "
                    "memory_edit"),
    "git_restore": ("it restores a file from git history in a code-repository checkout (a "
                    "worktree), not your home, and this seat has none; to put lines of your own "
                    "files back use memory_edit"),
    "pr_open": ("it opens a pull request from commits in a code-repository checkout (a "
                "worktree), and this seat has none"),
    "pr_amend": ("it revises your pull request from a code-repository checkout (a worktree), "
                 "and this seat has none"),
    "pr_sync": ("it updates your pull request inside a code-repository checkout (a worktree), "
                "and this seat has none"),
    "git_clean": ("it deletes an untracked file in a code-repository checkout (a worktree), "
                  "and this seat has none"),
    "camera": ("it is not enabled on this seat: here it is held to the same condition as the "
               "verbs that read a code-repository checkout (a worktree), and this seat has none; "
               "no other tool captures a frame"),
}
# Verbs that never touch a worktree but that the GATE still refuses without one. camera is the
# only one: camera_command raises NO_WORKTREE_REFUSAL["camera"] when ctx has no worktree (a policy
# hold, see the comment there). Until this list, the toolset offered camera in full on such a
# seat (or said "this machine's body has no camera"), while calling it returned "camera is not
# enabled on this seat". Availability now follows the gate's condition, which is unchanged; the
# no-worktree reason wins over the body reason because it is the one calling the verb returns.
WORKTREE_HELD_VERBS = ("camera",)


_SANDBOX_HERE: Optional[bool] = None


def _sandbox_here() -> bool:
    """A sandbox `run` can use (being_gate_client.run_sandbox_kind: bwrap, or Seatbelt on a Mac), once
    per process: it starts a real one."""
    global _SANDBOX_HERE
    if _SANDBOX_HERE is None:
        from sage.gateway.being_gate_client import run_sandbox_kind
        _SANDBOX_HERE = run_sandbox_kind() is not None
    return _SANDBOX_HERE


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
        for v in WORKTREE_VERBS + WORKTREE_HELD_VERBS:
            if v in _TOOL_SCHEMAS and v not in REACH_VERBS:
                out[v] = NO_WORKTREE_HERE.get(
                    v, "it works in a code-repository checkout (a worktree), and this seat has none")
    # A CORTEX-SOURCED CAMERA (instance.json camera_source "cortex", sage/embodiment/look.py) needs no
    # device node and no worktree: it needs the running cortex, which the body inventory measures. The
    # inventory's own "camera" verb means a free device for ffmpeg, which a cortex holding the eyes is not.
    if "camera" in _TOOL_SCHEMAS and (cfg or {}).get("camera_source") == "cortex":
        out.pop("camera", None)
        if inv is None:
            out["camera"] = "availability unknown: this machine's body was not measured this turn"
        elif not inv.get("cortex_live"):
            out["camera"] = "your eyes' organ (the cortex) is not running, so there is no frame to give you (measured)"
    # run needs a sandbox: bubblewrap able to make a user namespace, or Seatbelt on a Mac; without one
    # the verb refuses rather than run the being's code with the seat's authority, so say so here too.
    if "run" in _TOOL_SCHEMAS and not _sandbox_here():
        out["run"] = ("this machine has no usable sandbox (neither bubblewrap nor macOS Seatbelt), "
                      "and your code is never run outside one; request_run asks the seat instead")
    if "game" in _TOOL_SCHEMAS and not (cfg or {}).get("game_stepper"):
        out["game"] = "no game is set up on this seat (instance.json has no game_stepper)"
    return out


# WHAT A VERB SAYS ON THIS MACHINE, where its registry text describes another machine's mechanism.
# camera's registry text is the ffmpeg path: "The seat runs ffmpeg against /dev/video0 (or a plain device
# node you name)", with a `device` parameter defaulting to /dev/video0. On a seat that declares
# camera_source "cortex" none of that is true: the frame comes from the cortex (sage/embodiment/look.py) and
# `device` is never read (camera_command; _do_camera). Measured on Sprout, 2026-10-14..27: 612 of the
# being's 1,010 request_runs were about the device node, across 86 files, while its own tool text said, every
# beat, that its camera reads that node. The text now says where its frame comes from, and offers only the
# parameter that does something.
CORTEX_CAMERA = (
    "Take ONE frame from your own eye, into your own scratch. Here your eyes are run by your cortex, which "
    "holds the camera sensors: the frame comes from the cortex as a finished image, and no device node is "
    "opened or needed. The JPEG lands at out_path (default scratch/camera/last-frame.jpg, replaced each "
    "time) and, if it lands under scratch/camera/, is shown to you at your next beat. If your eyes are closed (gaze) or the cortex has no frame "
    "yet, it says so and writes nothing.",
    {"out_path": "optional: where the JPEG lands, a plain path inside your home "
                 "(default scratch/camera/last-frame.jpg)"})


# THE SAME FAULT ON A MAC (#575's follow-up). A Mac's camera has no device node: _do_camera sets device to
# "avfoundation" and never reads `device`; camera_command picks the camera by NAME (platform_av.mac_camera).
# The registry text told McNugget's being the ffmpeg/device-node story every beat. Measured on mcnugget-being,
# 1,230 beats to 2026-10-27: 0 camera calls, 7,005 mentions of the Linux node in 234 beats, 191 in its todo
# and 194 in its journal, a grant asked for and held on a node this body cannot have.
MAC_CAMERA = (
    "Take ONE frame from this Mac's camera, into your own scratch. A Mac's camera has no device node: the "
    "seat finds the attached camera by its name and captures one JPEG after a short warm-up. The JPEG lands "
    "at out_path (default scratch/camera/last-frame.jpg, replaced each time) and is shown to you at your "
    "next beat, wherever you saved it. If no camera is attached, macOS has not given the "
    "seat the camera, or it cannot be read (for example just unplugged), it says which and writes nothing.",
    {"out_path": "optional: where the JPEG lands, a plain path inside your home "
                 "(default scratch/camera/last-frame.jpg)"})


def _av_backend() -> str:
    """platform_av.backend(): which capture stack this seat's camera and microphone use. "" if unknown."""
    try:
        from sage.embodiment import platform_av
        return platform_av.backend()
    except Exception:
        return ""


def here(cfg: Optional[dict], backend: Optional[str] = None) -> Dict[str, tuple]:
    """{verb: (description, params)} that replace the registry text on THIS seat (see CORTEX_CAMERA,
    MAC_CAMERA). `backend` is platform_av.backend() unless given: the same test _do_camera makes, so the
    text and the act cannot disagree about which camera this is."""
    out: Dict[str, tuple] = {}
    if (cfg or {}).get("camera_source") == "cortex":
        out["camera"] = CORTEX_CAMERA
    elif (backend if backend is not None else _av_backend()) == "avfoundation":
        out["camera"] = MAC_CAMERA
    return out


# BRIEF DESCRIPTIONS (opt-in per instance, `tool_descriptions: "brief"`; dp, 2026-10-03). Measured on
# legion-being: the seed that compaction cannot touch grew 15.7k -> 17.1k tokens in a week, much of it
# verb schemas (33 verbs, 23.8k chars, descriptions 47% of that), leaving ~1.3k tokens of a 18.4k
# compaction target for a whole beat's work; long beats retried ~50% of generates at the window. In
# brief mode an available verb's description is its first sentence, capped, plus a pointer to
# `describe`, which returns the full text. Parameters, enums and required keys are untouched: they
# are what make a call well-formed. Per instance (RESEARCH_GENERALIZATION_RULE): measured on one being.
BRIEF_DESC_CHARS = 160
DESCRIBE = "describe"


# LEAN (opt-in per instance, `tool_descriptions: "lean"`; SAGE #708, dp 2026-11-14: "name + describe is the
# right shape"). Brief, and each parameter's DESCRIPTION also moves behind `describe`. The parameter names,
# required keys and closed value sets (enums) stay: they are what make a call well-formed, and an enum is
# the meaning of a closed parameter. Measured on nomad-being 11-14 (gemma4:e2b, num_ctx 16384, posture
# turn 12,998 tokens): brief specs were 22,236 chars, of which verb descriptions were 4,712 and parameter
# blocks 13,856; lean is 13,801 (-38%). Every verb names where the rest is. Per instance
# (RESEARCH_GENERALIZATION_RULE): whether a small model forms calls as well without parameter prose is
# the open question, measured per being before it spreads.
LEAN_POINTER = "({d} {n}: what each parameter means.)"


def tool_descriptions_mode(cfg: Optional[dict]) -> str:
    """instance.json `tool_descriptions`: "brief" or "lean" opts in; anything else is the full descriptions."""
    mode = str((cfg or {}).get("tool_descriptions", "")).strip().lower()
    return mode if mode in ("brief", "lean") else "full"


def brief_description(name: str, desc: str) -> str:
    """The first sentence of a verb's description, capped at BRIEF_DESC_CHARS, and -- when that cut
    anything -- where the rest is. Never shorter than what it replaces; a short description stays whole."""
    import re
    m = re.match(r"(.+?[.!?])(\s|$)", desc.strip(), re.S)
    first = (m.group(1) if m else desc.strip())
    if len(first) > BRIEF_DESC_CHARS:
        first = first[:BRIEF_DESC_CHARS - 1].rstrip() + "…"
    if first.strip() == desc.strip():
        return desc
    return f"{first} (Full text: {DESCRIBE} {name}.)"


# OFFER BY USE (opt-in per instance, `tool_offer: "by_use"`; dp, 2026-11-10: "try by-name verbs on legion").
# Measured on legion-being that day: the opening prompt was ~19.7k of 32.8k tokens and left ~6k tokens for
# a beat's work (median 8 steps). The verb schemas, already brief, were the largest block at 23.9k chars; in
# its last 74 beats it had called 12 of 41 verbs, and the other 29 cost ~14.3k chars, about two thirds of
# that working room. In this mode a verb the being has not called in its last OFFER_WINDOW_BEATS working
# beats keeps its NAME, one short line and its parameter NAMES, so it is still offered and still callable
# (dp, 2026-09-29: every being is offered the whole toolset). Its parameter descriptions and enums are one
# `describe` away, and a verb the being describes counts as used: from the next beat it is offered like the verbs it uses.
# Per instance (RESEARCH_GENERALIZATION_RULE): measured on one being.
OFFER_WINDOW_BEATS = 100
OFFER_MIN_BEATS = 10          # a record shorter than this says nothing about use: offer everything in full
BY_NAME_DESC_CHARS = 90
ALWAYS_FULL = frozenset({DESCRIBE, "stay_awake", "rest"})   # how it finds the rest, keeps going, and stops
# Mode-neutral on purpose (sprout on #711): under `lean` a described verb comes back lean, not in full, so
# the note says it returns like the verbs the being uses, which is true in every tool_descriptions mode.
BY_NAME_NOTE = (" Verbs you have not called in your last {n} working beats are listed with one line and "
                "parameter names only; describe one and, from your next beat, it is offered like the verbs "
                "you use.")


def tool_offer_mode(cfg: Optional[dict]) -> str:
    """instance.json `tool_offer`: "by_use" opts in; anything else offers every verb in the same form."""
    return "by_use" if str((cfg or {}).get("tool_offer", "")).strip().lower() == "by_use" else "full"


def recently_called(instance, beats: int = OFFER_WINDOW_BEATS) -> Optional[set]:
    """Verbs the being CALLED in its last `beats` working beats, whatever the outcome (a refused or failed
    call is still a verb it reached for), plus every verb it asked `describe` about. A beat with no act at
    all (an outage: the model never answered) is not a working beat and does not use up the window. None
    when the record holds fewer than OFFER_MIN_BEATS working beats."""
    from sage.gateway import beat_health as bh
    called, working = set(), 0
    for rec in bh.iter_beats_newest_first(instance):
        acted = False
        for _, phase in bh._phases(rec):
            for t in phase.get("trace") or ():
                if not isinstance(t, dict) or not t.get("effector"):
                    continue
                acted = True
                called.add(str(t["effector"]))
                if t["effector"] == DESCRIBE and isinstance(t.get("args"), dict):
                    called.add(str(t["args"].get("verb") or "").strip())
        working += acted
        if working >= beats:
            break
    called.discard("")
    return called if working >= OFFER_MIN_BEATS else None


def by_name_verbs(instance, cfg: Optional[dict]) -> Optional[List[str]]:
    """The verbs to list by name this beat, or None when the instance has not opted in or its record is too
    short to say. Never a verb in ALWAYS_FULL."""
    if tool_offer_mode(cfg) != "by_use":
        return None
    try:
        called = recently_called(instance)
    except Exception:
        return None                                  # fail open: a broken reading costs the being nothing
    if called is None:
        return None
    return [n for n in canonical_toolset() if n not in called and n not in ALWAYS_FULL]


def offer_by_name(tool_specs: List[dict], names) -> List[dict]:
    """`tool_specs` with each verb in `names` cut to its name, one short line and its parameter names. The
    verb stays callable and its required keys stay. A verb that cannot work on this machine already carries
    one line and its reason, and is left as it is. `describe` says once how the rest comes back."""
    import copy
    import re
    names = set(names or ())
    out = []
    for spec in tool_specs:
        fn = spec.get("function") or {}
        name = fn.get("name")
        if name == DESCRIBE and names:
            spec = copy.deepcopy(spec)
            spec["function"]["description"] = fn.get("description", "") + BY_NAME_NOTE.format(n=OFFER_WINDOW_BEATS)
        elif name in names and "ON THIS MACHINE IT CANNOT WORK" not in fn.get("description", ""):
            desc = re.sub(r"\s*\(Full text: .*?\)\s*$", "", fn.get("description", "").strip())
            m = re.match(r"(.+?[.!?])(\s|$)", desc, re.S)
            first = m.group(1) if m else desc
            if len(first) > BY_NAME_DESC_CHARS:
                first = first[:BY_NAME_DESC_CHARS - 1].rstrip() + "…"
            params = fn.get("parameters") or {}
            spec = {"type": "function", "function": {
                "name": name, "description": f"{first} ({DESCRIBE} {name})",
                "parameters": {"type": "object",
                               "properties": {k: {"type": "string"} for k in (params.get("properties") or {})},
                               "required": list(params.get("required") or [])}}}
        out.append(spec)
    return out


def full_text(name: str, cfg: Optional[dict] = None) -> str:
    """What `describe` answers: the verb's whole description and each parameter's, from the schema table,
    as this seat offers it (here)."""
    if name not in _TOOL_SCHEMAS:
        return (f"there is no verb called {name!r}. Verbs: " + ", ".join(canonical_toolset()))
    desc, props, required = _TOOL_SCHEMAS[name]
    if name in here(cfg):
        desc, props = here(cfg)[name]
        required = [r for r in required if r in props]
    lines = [f"{name}: {desc}"]
    for k, v in props.items():
        lines.append(f"  {k}{' (required)' if k in required else ''}: {v}")
    return "\n".join(lines)


def specs(unavail: Optional[Dict[str, str]] = None, enums: Optional[Dict[tuple, list]] = None,
          *, brief: bool = False, lean: bool = False, cfg: Optional[dict] = None) -> List[dict]:
    """The Ollama tool specs for the whole canonical toolset. Available verbs carry their full
    description; an unavailable one carries one line and the reason, parameters intact. `lean` is brief
    plus parameter descriptions behind `describe` (names, required keys and enums stay)."""
    brief = brief or lean
    unavail = unavail or {}
    # CLOSED VALUE SETS reach the explore turn too (2026-10-01): SAGE #312 put gaze.mode / git_read.op enums
    # in ollama_tools(), but explore is built here, so they never reached the turn where gaze is used.
    # `enums` adds per-beat sets, e.g. {("peer_ask", "to"): the siblings and seats this being can reach}.
    from sage.gateway.being_gate_client import _param_enums
    closed = {**_param_enums(), **(enums or {})}
    out = []
    local = here(cfg)
    for name in canonical_toolset():
        desc, props, required = _TOOL_SCHEMAS[name]
        if name in local:
            desc, props = local[name]
            required = [r for r in required if r in props]
        if name in unavail:
            first = desc.split(". ")[0].rstrip(".")
            desc = (f"{first}. ON THIS MACHINE IT CANNOT WORK: {unavail[name]}. Offered because "
                    f"every being has the whole toolset; calling it says the same.")
            # the parameter NAMES stay (the verb is callable, and says why it cannot work); their
            # long descriptions go, since they are what made an unusable verb cost ~700 chars
            properties = {k: {"type": "string"} for k in props}
        else:
            if brief and name != DESCRIBE:
                desc = brief_description(name, desc)
            if lean and name != DESCRIBE:
                # the parameter prose goes; the verb says once where it is (replacing brief's pointer)
                import re as _re
                if props:
                    desc = (_re.sub(r"\s*\(Full text: .*?\)\s*$", "", desc.strip()) + " "
                            + LEAN_POINTER.format(d=DESCRIBE, n=name))
                properties = {k: dict({"type": "string"},
                                      **({"enum": list(closed[(name, k)])} if closed.get((name, k)) else {}))
                              for k in props}
            else:
                properties = {k: dict({"type": "string", "description": v},
                                      **({"enum": list(closed[(name, k)])} if closed.get((name, k)) else {}))
                              for k, v in props.items()}
        out.append({"type": "function", "function": {
            "name": name, "description": desc,
            "parameters": {"type": "object", "properties": properties, "required": required}}})
    return out
