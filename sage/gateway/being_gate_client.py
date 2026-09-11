"""
SAGE-side reference thin-client for the gateway-member design (PRD_FLEET §7 / F2).

A SAGE being holds NO effectors of its own. It emits an INTENT; this client
normalizes it to the hestia gate's NormalizedEvent, asks the real, shared gate
law for a Verdict (fail-CLOSED), and only on ALLOW hands the intent to the F1a
dispatcher that actually executes and witnesses it — today `HestiaF1aDispatcher`
(sage/gateway/hestia_dispatch.py) against the running daemon; hestia's own F1a
(PR #579) replaces it when it lands.

This is the SAGE half of F2. It pins the exact contract F1a must satisfy:

    intent  ->  gate.evaluate (+ society safety)  ->  [F1a dispatch]  ->  result

Design invariants (answering CBP's REQUEST_CHANGES on #579):
  * FAIL-CLOSED: a being that cannot reach the law is STOPPED, never ungoverned.
    When society-safety (Stage 2) is unavailable or errors, CONSEQUENTIAL effectors
    (peer_ask, memory_write, channel_egress, mesh, pr_review, remember, request_scope)
    hard-deny; only OBSERVATIONAL effectors (witness, memory_read, recall) soft-pass,
    since they carry no external effect and witness is itself the accountability
    primitive. Local-law admission (Stage 1)
    is never enough on its own for a consequential act — end-to-end execution
    authority requires the society governor too.
  * BOUNDED REGISTRY: the being's only effectors are mesh/peer_ask, witness,
    memory (its own dir), long-term memory (recall/remember, its own membot
    cartridge), request_scope, pr_review (advisory), channel egress. No shell, no
    raw FS. Enforced twice:
    the registry below will not emit an intent outside it, AND the gate denies it.
  * A2-by-construction: the being never holds the tool; dispatch is hestia's.

The gate core is the SAME multi-harness law codex/kimi/gemini/cursor call
(hestia/plugins/_shared/hestia_gate_core.py). We import it lazily so this module
is safe to import on a host without hestia — instantiation fails closed instead.
"""
from __future__ import annotations

import os
import sys
from dataclasses import dataclass
from typing import Any, Callable, List, Optional


# --------------------------------------------------------------------------
# Locate the shared hestia gate law portably (env override, then fleet layout).
# --------------------------------------------------------------------------
def _resolve_hestia_shared() -> Optional[str]:
    """Locate the shared law this client imports.

    Order is deliberate: an explicit override, then the INSTALLED law the deploy
    maintains, then the source checkout. The installed copy is what the seats on
    this box actually enforce and what `hestia-deploy` keeps current and attests
    in the manifest, so a being judged by anything else is judged by a different
    law than its seat.

    `HESTIA_SHARED_DIR` and `HESTIA_HOME` are the fleet's own config vocabulary:
    the vault projection at `$HESTIA_HOME/seats/<plugin_id>.env` publishes both.
    Reading them here means a box that is correctly configured for its seats is
    correctly configured for its beings, with nothing further to set.

    The `~/ai-workspace` entries are kept last for the machines laid out that
    way; they are one layout, not a location every box has. On a box that checks
    out elsewhere the old list resolved to None and EVERY intent fail-closed on
    `gate.unreachable: No module named 'hestia_gate_core'`, which reads like a
    broken gate rather than an unconfigured path (measured 2026-09-09).
    """
    for env_key in ("HESTIA_GATE_SHARED", "HESTIA_SHARED_DIR"):
        env = os.environ.get(env_key)
        if env and os.path.isdir(env):
            return env
    home = os.environ.get("HESTIA_HOME")
    if home:
        p = os.path.join(os.path.expanduser(home), "shared")
        if os.path.isdir(p):
            return p
    for base in ("~/ai-workspace/hestia", "~/ai-workspace/HESTIA"):
        p = os.path.join(os.path.expanduser(base), "plugins", "_shared")
        if os.path.isdir(p):
            return p
    return None


# --------------------------------------------------------------------------
# The bounded gateway-member registry. Each entry says how a being intent maps
# onto a NormalizedEvent (the gate's only input). Anything not here cannot be
# emitted at all — the first of two enforcement layers.
# --------------------------------------------------------------------------
@dataclass(frozen=True)
class BeingIntent:
    effector: str    # registry key the being names
    args: dict        # effector-specific arguments


# What the being's gate client calls itself when it connects to the daemon.
_HOST_AGENT = "sage-gateway"

def pr_review_command(args: dict) -> str:
    """The shell command the seat runs for a pr_review intent, built from validated args.
    Raises ValueError on anything the grammar cannot represent; never interpolates the body
    (it travels by --body-file, so no review text can reach the shell)."""
    import re
    repo = str(args.get("repo", "")).strip()
    number = str(args.get("number", "")).strip()
    # fleet repos only: the seat's gh identity never posts outside dp-web4 on a being's behalf
    if not re.fullmatch(r"dp-web4/[A-Za-z0-9._-]+", repo):
        raise ValueError(f"pr_review 'repo' must be a dp-web4/<name> repo, got {repo!r}")
    if not re.fullmatch(r"[0-9]{1,7}", number):
        raise ValueError(f"pr_review 'number' must be a PR number, got {number!r}")
    if not str(args.get("body", "")).strip():
        raise ValueError("pr_review needs a non-empty 'body'")
    return f"gh pr review {number} --repo {repo} --comment --body-file -"


def pr_review_signature(member_id: str, action_id: Optional[str], being_lct: Optional[str]) -> str:
    """The fixed trailer on every review a being posts: who, under what record, and that
    it is advisory. The being cannot omit or alter it; the dispatcher appends it."""
    lines = ["", "---",
             f"Review by **{member_id}**, a SAGE being acting under hestia governance. "
             "Advisory and non-binding: the being holds no reviewer role, so this comment "
             "does not count toward merge. The seat's reviewers decide."]
    if being_lct:
        lines.append(f"LCT: `{being_lct}`")
    if action_id:
        lines.append(f"hestia witness action: `{action_id}`")
    lines.append(f"— {member_id}")
    return "\n".join(lines)


# The test targets a being may name, and the command each one becomes (#M0, PRD
# "Beings improve their own harness"). An ALLOW-LIST, not a grammar: `check` exists so a
# being can verify a claim about its own harness, and the smallest thing that does that is
# a fixed set of suites plus a single node id inside them. Anything wider is a shell with a
# friendly name, which is the one thing the bounded registry exists to prevent.
CHECK_TARGETS = {
    "gateway": "sage/gateway/tests/",
    "irp": "sage/irp/tests/",
}


def _takes_ctx(fn) -> bool:
    """Whether a registry `compose` accepts the client's context as a second argument.
    Older composes (pr_review_command) take args alone and must keep working."""
    import inspect
    try:
        return len(inspect.signature(fn).parameters) >= 2
    except (TypeError, ValueError):
        return False


def check_argv(args: dict, ctx: Optional[dict] = None) -> List[str]:
    """The canonical argv for ``check`` after validating its bounded target."""
    import re
    import os
    worktree = (ctx or {}).get("worktree")
    if not worktree:
        raise ValueError(
            "check needs a worktree of your own: there is nothing to run tests in, and a "
            "relative path would be judged against a tree you do not hold (PRD M1)")
    worktree = os.path.realpath(os.path.expanduser(str(worktree)))
    target = str(args.get("target", "")).strip()
    node = None
    if target in CHECK_TARGETS:
        suite = target
    else:
        # A single node id INSIDE a declared suite: "gateway::test_name". Nothing else.
        suite, sep, node = target.partition("::")
        if not sep or suite not in CHECK_TARGETS:
            raise ValueError(
                f"check 'target' must be one of {sorted(CHECK_TARGETS)} or "
                f"'<suite>::<test_name>'; got {target!r}")
        if not re.fullmatch(r"[A-Za-z0-9_]+", node):
            raise ValueError(f"check test name must be a bare identifier; got {node!r}")
    path = os.path.join(worktree, CHECK_TARGETS[suite])
    argv = ["python3", "-m", "pytest", "-q", "-c", "/dev/null",
            f"--rootdir={worktree}", path]
    if node is not None:
        argv.extend(("-k", node))
    return argv


def check_command(args: dict, ctx: Optional[dict] = None) -> str:
    """The shell command the seat runs for a `check` intent, built from validated args.

    Raises ValueError on anything the allow-list cannot represent, so a malformed target is
    a `gate.raised` deny rather than a silent pass. `-c /dev/null` because the repo's
    pytest.ini declares an asyncio_mode this interpreter does not have (measured: bare
    pytest errors before collecting), and a checking organ that reports an infrastructure
    error as a test failure would teach the being the opposite of what it asked.

    THE PATHS ARE ABSOLUTE, AND THAT IS THE WHOLE POINT (measured 2026-09-07). The command
    runs with cwd = the being's worktree, but the gate resolves a RELATIVE path against the
    workspace it was handed — the shared checkout. So `sage/gateway/tests/` was judged at
    `<shared>/sage/gateway/tests/`, which the being has no grant for, while the command
    would have touched the worktree it does. The law must judge the path the command will
    actually touch; anything else is the `_safe_path` defect again, one layer over. No
    worktree means no check: fail closed, and say which affordance is missing.
    """
    import shlex
    return shlex.join(check_argv(args, ctx))


_REGISTRY = {
    "peer_ask":       dict(tool="peer_ask",     path_args=(),       cmd_arg=None),
    "witness":        dict(tool="witness",      path_args=(),       cmd_arg=None),
    "memory_read":    dict(tool="read_file",    path_args=("path",), cmd_arg=None),
    "memory_write":   dict(tool="write_note",   path_args=("path",), cmd_arg=None),
    "channel_egress": dict(tool="channel_send", path_args=(),       cmd_arg=None),
    "mesh":           dict(tool="mesh_notify",  path_args=(),       cmd_arg=None),  # §7.2 5th verb
    # pr_review: the being reviews a pull request. The seat posts the comment; the gate
    # judges the exact shell command the seat will run (see pr_review_command), so the
    # law sees an outward `gh` act, not a friendly verb name. Advisory by construction:
    # a being holds no reviewer role, so the comment never counts toward merge.
    "pr_review":      dict(tool="pr_review",    path_args=(),       cmd_arg=None,
                           compose=pr_review_command),
    # check: RUN a test suite in the being's own worktree and read the result. The first
    # organ, and the ordering is argued from measurement (PRD §2): given only a diff this
    # being asserted a compile error that did not exist; given the same diff plus a real
    # test result it made zero false claims. Composed like pr_review — the being names a
    # target from an allow-list, the SEAT builds the command, the law judges THAT, and the
    # being never holds a shell. A failing check is a first-class result, not an error.
    "check":          dict(tool="check",       path_args=(),       cmd_arg=None,
                           compose=check_command),
    # Long-term semantic memory (membot brain cartridge, the being's own): recall is
    # observational; remember is consequential but passes local law under ANY grant
    # (paths=()), and that is not because it is "classed with memory_write" (which the
    # law judges by mrh.path): its reach is bounded by construction. The cartridge it
    # writes is `membot_cartridge or plugin_id`, fixed by the seat, unreachable from the
    # being's args.
    # request_scope asks hestia for reach the being lacks: the sanctioned answer to a
    # deny, decided by the operator, witnessed either way. path_args=() is CORRECT here
    # and must stay so: the requested path is, by definition, outside the grant, so a
    # request judged under mrh.path at stage 1 would die before it ever reached the
    # daemon (pinned by test_request_scope_path_is_not_judged_under_mrh_path).
    "recall":         dict(tool="recall",       path_args=(),       cmd_arg=None),
    "remember":       dict(tool="remember",     path_args=(),       cmd_arg=None),
    "request_scope":  dict(tool="request_scope", path_args=(),      cmd_arg=None),
    # appeal: the being contests a refusal it believes was wrong (PRD_FLEET §7.3, the
    # deny -> appeal -> temperament loop). The refusal's chain hash is the handle: the
    # gate witnesses every deny as a policy_decision (Dispatcher.witness_deny) so there
    # is something to appeal, and hestia_appeal refuses anything that is not a deny,
    # not yours, already under appeal, or unreasoned. No external effect: chain only.
    "appeal":         dict(tool="appeal",        path_args=(),      cmd_arg=None),
}


# Society-safety failure boundary per effector class. Observational acts carry no
# external effect and may soft-pass when the society governor is unavailable;
# consequential acts must not proceed without it (fail-closed).
_OBSERVATIONAL = frozenset({"witness", "memory_read", "recall", "appeal"})
_CONSEQUENTIAL = frozenset({"peer_ask", "memory_write", "channel_egress", "mesh", "pr_review",
                            "remember", "request_scope", "check"})

# Native-tool schema for the bounded registry — what the being is offered.
_TOOL_SCHEMAS = {
    "peer_ask": ("Ask another being in the fleet a question through the hub.",
                 {"to": "the being's name, e.g. 'legion'", "body": "your message"}, ["to", "body"]),
    "witness": ("Record a witnessed note of something you did or noticed.",
                {"event": "what to witness"}, ["event"]),
    "memory_read": ("Read one of your own memory notes.",
                    {"path": "path to your note"}, ["path"]),
    "memory_write": ("Write a note into your own memory.",
                     {"path": "path to your note", "content": "what to write"}, ["path", "content"]),
    "channel_egress": ("Send a message out through a sealed channel.",
                       {"to": "recipient", "body": "your message"}, ["to", "body"]),
    "mesh": ("Wake another member through the fractal mesh with a pointer-based notice "
             "(no body — point at content you already posted).",
             {"to": "member name", "kind": "notice kind, e.g. coordination, reply, ack",
              "pointer": "URI of the content (a shared-context path, PR, or thread)"},
             ["to", "kind", "pointer"]),
    "pr_review": ("Post your review of a pull request as a comment. Advisory: it does not "
                  "approve or block. Say what you checked, what you found, and what you "
                  "would change, with file and line references where you can.",
                  {"repo": "owner/name, e.g. dp-web4/SAGE", "number": "the PR number",
                   "body": "your review, in markdown"}, ["repo", "number", "body"]),
    "check": ("Run a test suite in your own worktree and read the result. This is how you "
              "find out whether something you believe about your harness is true, instead of "
              "asserting it. A failure is a real answer, not a problem.",
              {"target": "'gateway' or 'irp' for a whole suite, or '<suite>::<test_name>' "
                         "for one test, e.g. 'gateway::test_relative_memory_path'"},
              ["target"]),
    "recall": ("Search your long-term memory (semantic search over everything you have "
               "remembered). Use it before deciding what to do; use it when something "
               "feels familiar.",
               {"query": "what you are trying to remember", "top_k": "how many results (default 5)"},
               ["query"]),
    "remember": ("Store something in your long-term memory so a future you can recall it: "
                 "a fact, a lesson, a question, what you were doing and why.",
                 {"content": "the memory, in your own words", "tags": "comma-separated tags (optional)"},
                 ["content"]),
    # No read/write mode: measured against hestia a5e18af (handler.rs::tool_request_scope)
    # the daemon reads plugin_id/role/path/reason only, and a grant is a `path:<p>` entry
    # in in_scope that rules mrh.path for reads and writes alike. Offering a mode would be
    # a choice the law cannot honour.
    "request_scope": ("Ask the operator for reach you do not have, after a refusal. SAGE "
                      "can read an external granted path, but keeps external writes disabled "
                      "until being-code execution has its own principal. Say why. A human decides; "
                      "no answer within the window is a refusal. A live grant dies with the "
                      "daemon; only a standing grant persists.",
                      {"path": "absolute path you want reach to",
                       "reason": "why you want it, in one or two sentences"},
                      ["path", "reason"]),
    "appeal": ("Appeal a refusal you believe was wrong. Give the deny hash shown on the "
               "refusal and a reason of at least 12 characters. A peer or the operator "
               "rules, asynchronously; the ruling is witnessed either way. Not for a "
               "refusal you agree with.",
               {"deny_hash": "the witness hash shown on the refusal (deny_hash=...)",
                "reason": "why the refusal was wrong, one or two sentences"},
               ["deny_hash", "reason"]),
}


def ollama_tools(only: Optional[List[str]] = None) -> List[dict]:
    """Ollama native-tool specs for the bounded gateway-member registry (nothing else).
    `only` narrows what the being is OFFERED for a task (e.g. a review turn offers
    pr_review + witness); it never widens: a name outside the registry is ignored."""
    out = []
    for name, (desc, props, required) in _TOOL_SCHEMAS.items():
        if only is not None and name not in only:
            continue
        out.append({"type": "function", "function": {
            "name": name, "description": desc,
            "parameters": {"type": "object",
                           "properties": {k: {"type": "string", "description": v} for k, v in props.items()},
                           "required": required}}})
    return out


def parse_tool_calls(tool_calls: list) -> List["BeingIntent"]:
    """Map Ollama tool_calls into BeingIntents. Unknown names still become intents so the
    gate can refuse them at the registry stage (never silently dropped)."""
    intents = []
    for c in tool_calls or []:
        fn = c.get("function", {}) if isinstance(c, dict) else {}
        name = fn.get("name") or "?"
        args = fn.get("arguments") or {}
        if isinstance(args, str):
            try:
                import json as _json
                args = _json.loads(args)
            except Exception:
                args = {"_raw": args}
        intents.append(BeingIntent(effector=name, args=args if isinstance(args, dict) else {}))
    return intents


_HOME_FILENAMES = ("journal.md", "todo.md", "account.json", "notes", "scratch")


def _home_hint(intent: "BeingIntent", dispatcher) -> str:
    """When a refused path names one of the being's OWN home files but is rooted elsewhere,
    the remedy is the right path, not a grant. Say so in the refusal the being reads, so it
    can correct inside the same beat (dp, 2026-09-07: "mistakes become lessons"). Measured on
    Sprout: it wrote journal.md and todo.md to `<repo>/sage/` and to `/home/user/`, a generic
    placeholder path, while writing its real journal correctly 51 times in the same period."""
    try:
        raw = str((intent.args or {}).get("path", "")).strip()
        name = os.path.basename(raw.rstrip("/"))
        if not raw or name not in _HOME_FILENAMES:
            return ""
        root = getattr(getattr(dispatcher, "_local", None), "memory_root", None) \
            or getattr(dispatcher, "memory_root", None)
        if not root:
            return ""
        correct = os.path.join(os.path.realpath(str(root)), name)
        if os.path.realpath(raw) == correct:
            return ""
        return (f" — no grant is needed for this: your own '{name}' is at {correct}, "
                f"and a bare '{name}' is resolved inside your home.")
    except Exception:
        return ""


def _granted_roots(core, policy, workspace: str) -> tuple:
    """``((abs_root, recursive), ...)`` for every `path:` scope a resolved policy grants.

    REACH TRAVELS WITH THE ROOT (hestia #1002; GPT review of #55/#56). This used to return
    bare roots via `_scope_parts(...)[1]`, and the dispatcher then admitted `p == root OR
    root in p.parents` — so an EXACT hestia grant on /x became recursive /x/** inside SAGE's
    own defense-in-depth layer, wider than the law that produced it. Now the pair is kept:
    the core's `_scope_roots_with_reach` when it has one (post-#1002), else parsed here from
    the `/**` spelling, so an older core still yields exact-by-default rather than a guess."""
    if policy is None:
        return ()
    try:
        scopes = list(getattr(policy, "scope", ()) or ())
        with_reach = getattr(core, "_scope_roots_with_reach", None)
        if with_reach is not None:
            return tuple((str(r), bool(rec)) for r, rec in with_reach(scopes, workspace))
        out = []
        for sc in scopes:
            if isinstance(sc, str) and sc.startswith("path:"):
                raw = sc[5:]
                rec = raw.endswith("/**")
                if rec:
                    raw = raw[:-3]
                out.append((os.path.realpath(os.path.expanduser(raw)), rec))
        return tuple(out)
    except Exception:
        return ()


@dataclass(frozen=True)
class GatewayVerdict:
    decision: str          # "allow" | "warn" | "deny"
    rule: str = ""
    reason: str = ""
    innate: bool = False
    stage: str = ""        # which stage decided: registry | local-law | society
    witness_id: Optional[str] = None   # the deny's chain hash once witnessed (appeal handle)
    # The path roots the law consulted for this verdict (the member's grants, resolved):
    # the dispatcher's own confinement follows THESE, not only the home. Legion measured
    # 2026-09-05 that a shared-context read grant "cannot be used at all" because the local
    # dispatcher confined memory_read to the instance dir before hestia's gate was consulted.
    granted: tuple = ()
    # For a composed effector, this is the exact command the law judged. Dispatch executes
    # this value rather than independently rebuilding a lookalike command.
    command: Optional[str] = None

    @property
    def blocks(self) -> bool:
        return self.decision == "deny"


@dataclass
class ResultEnvelope:
    """What comes back from an intent — the being's tool-result. On ALLOW this is
    produced by the F1a dispatcher (hestia executing + witnessing); on DENY it is a
    refusal; when F1a is not yet wired it is `pending`. Never fabricated."""
    ok: bool = False
    result: Any = None
    error: Optional[str] = None
    witness_id: Optional[str] = None
    refused: bool = False
    pending: bool = False
    note: str = ""
    verdict: Optional[GatewayVerdict] = None

    def to_tool_message(self) -> str:
        """Render for re-injection into the being's conversation as the tool result."""
        if self.refused:
            return f"[refused by hestia — {self.error}]"
        if self.pending:
            return f"[allowed by law, not yet executed — {self.note}]"
        if self.ok:
            import json as _json
            body = self.result if isinstance(self.result, str) else _json.dumps(self.result)
            return body + (f"  (witnessed {self.witness_id})" if self.witness_id else "")
        return f"[dispatch error — {self.error}]"


# A Dispatcher is F1a's contract, SAGE-side: given an ALLOWED intent + its verdict,
# execute it on the being's behalf and return a witnessed ResultEnvelope. Injected,
# so the real one is hestia's F1a; tests pass a mock; unset means "pending F1a".
Dispatcher = Callable[["BeingIntent", GatewayVerdict], ResultEnvelope]


class BeingGateClient:
    """One per being. Governs every intent through the real hestia law, fail-closed."""

    def __init__(self, member_id: str, identity_path: str, workspace: str,
                 worktree: Optional[str] = None,
                 dispatcher: "Optional[Dispatcher]" = None,
                 host_session_id: Optional[str] = None):
        self.member_id = member_id
        self.workspace = workspace
        # the being's own worktree; composed commands name paths inside it
        self.worktree = (os.path.realpath(os.path.expanduser(str(worktree)))
                         if worktree else None)
        # The being's memory root: the instance dir that holds its identity. Relative
        # memory paths the being emits are rooted here (see _normalize).
        self.memory_root = os.path.dirname(os.path.abspath(os.path.expanduser(identity_path)))
        # Stable per-run id handed to hestia_connect for connect idempotency (the
        # society stage connects per query; this keeps those sessions one lineage).
        self.host_session_id = host_session_id
        self._dispatcher = dispatcher  # F1a; None until the hestia substrate exists
        self._core = None
        self._mech = None
        self._import_error = "hestia gate core not located"

        shared = _resolve_hestia_shared()
        if shared and shared not in sys.path:
            sys.path.insert(0, shared)
        self._identity_path = identity_path
        # Single gate (hestia #934): when installed, ONE law-bearing sequence decides and this
        # client is a shim — profile data + syntax translation, no policy sequencing of its
        # own. Absent (pre-#934 engine), the per-primitive path below stays as the fallback.
        try:
            import hestia_single_gate as _sg  # type: ignore
            self._single_gate = _sg
            self._single_gate_error = None
        except Exception as e:
            self._single_gate = None
            self._single_gate_error = repr(e)
        # Import the ONE shared law. A broken/missing core is fail-closed (gate()).
        try:
            import hestia_gate_core as _core  # type: ignore
            self._core = _core
            self._profile = _core.HarnessProfile(
                member_id=member_id,
                identity_path=identity_path,
                default_role="role:constellation:member",
            )
        except Exception as e:  # import failure == being is DENIED all effectors
            self._import_error = repr(e)
        # society-safety second stage (daemon round-trip); optional, fail-closed
        try:
            import hestia_gate_mechanism as _mech  # type: ignore
            self._mech = _mech
        except Exception:
            self._mech = None

    # -- which law-bearing path this client will take (measured, not asserted) --------
    @property
    def gate_path(self) -> str:
        """'single-gate' when hestia_single_gate (#934) imported, else 'local-law' (the
        pre-#934 per-primitive fallback). A conformance report must print this: a green
        run on 'local-law' says nothing about the shim."""
        return "single-gate" if getattr(self, "_single_gate", None) is not None else "local-law"

    @property
    def single_gate_status(self) -> str:
        """'present' or 'absent: <import error>' — the marker Legion asked for, so a 5/0/3
        cannot be read as 'the single-gate shim passed' when the module was never there."""
        if getattr(self, "_single_gate", None) is not None:
            return "present"
        return f"absent: {getattr(self, '_single_gate_error', None) or 'not imported'}"

    # -- normalize a being intent into the gate's NormalizedEvent -------------
    def _normalize(self, intent: BeingIntent):
        spec = _REGISTRY[intent.effector]
        paths: List[str] = []
        for a in spec["path_args"]:
            v = intent.args.get(a)
            if v:
                p = os.path.expanduser(str(v))
                # The being's memory paths are relative to ITS OWN memory root (the
                # instance dir), never to the process cwd: the gate must judge the same
                # path the dispatcher will touch (reference_f1a._safe_path roots the same way).
                if not os.path.isabs(p):
                    p = os.path.join(self.memory_root, p)
                # realpath, not abspath: the dispatcher resolves symlinks (_safe_path), so the
                # judged path and the touched path must be the same real path
                paths.append(os.path.realpath(p))
        command = intent.args.get(spec["cmd_arg"]) if spec["cmd_arg"] else None
        compose = spec.get("compose")
        if compose is not None:
            ctx = {"worktree": getattr(self, "worktree", None)}
            # a COMPOSED verb: the seat builds the exact outward act (a shell line) from the
            # being's args, and THAT is what the law judges. Bad args raise here and gate()
            # turns that into a deny (gate.raised), never a silent pass. The being never
            # fills a command; the registry never carries a cmd_arg for a composed verb.
            command = compose(intent.args, ctx) if _takes_ctx(compose) else compose(intent.args)
        raw = {"effector": intent.effector, **intent.args}
        if command is not None:
            # Society safety consumes raw/tool_input rather than NormalizedEvent.command.
            # Carry the composed act there too; otherwise stage 1 and stage 2 judge
            # different objects.
            raw["command"] = command
        return self._core.NormalizedEvent(
            tool=spec["tool"], paths=paths, command=command,
            cwd=self.workspace, raw=raw,
        )

    # -- gate one intent (intent -> verdict), fail-closed --------------------
    def gate(self, intent: BeingIntent) -> GatewayVerdict:
        # Stage 0: bounded registry. Unknown effector never reaches the law.
        if intent.effector not in _REGISTRY:
            return GatewayVerdict("deny", "registry.unbounded", stage="registry",
                                  reason=f"'{intent.effector}' is not a gateway-member effector")
        # --- Single gate (#934): the shim contract. The registry stage above is harness
        # syntax (which verbs exist); everything law-bearing happens in decide(). ---
        sg = getattr(self, "_single_gate", None)
        if sg is not None and self._core is not None:
            try:
                ev = self._normalize(intent)
                tool = _REGISTRY[intent.effector]["tool"]  # the spec is the source, not the event
                gp = sg.GateProfile(member_id=self.member_id, identity_path=self._identity_path,
                                    default_role="role:constellation:member",
                                    host_agent=getattr(self, "_host_agent", "sage-raising"),
                                    client_name=f"sage-{self.member_id}-gate")
                tool_input = dict(intent.args)
                if getattr(ev, "command", None) is not None:
                    # The single gate derives NormalizedEvent.command from tool_input. Merely
                    # calling _normalize above validates the compose but does not make the
                    # gate judge it; the composed command must cross this seam explicitly.
                    tool_input["command"] = ev.command
                ge = sg.GateEvent(tool=tool, tool_input=tool_input, cwd=self.workspace,
                                  session_id=getattr(self, "host_session_id", None),
                                  raw={"effector": intent.effector, **intent.args})
                d = sg.decide(ge, gp)
                available = getattr(d, "verdict_available", True)
                dec = d.decision if (available and d.decision in ("allow", "warn", "deny")) else "deny"
                rule = d.rule or ("" if available else "gate.no_verdict")
                return GatewayVerdict(dec, rule, getattr(d, "reason", "") or ("ok" if dec != "deny" else ""),
                                      innate=False, stage="single-gate",
                                      command=getattr(ev, "command", None))
            except Exception as e:  # a gate that raises is a refused act, never an ungoverned one
                return GatewayVerdict("deny", "gate.raised", innate=True, stage="single-gate",
                                      reason=f"{type(e).__name__}: {e}")
        # Fail-closed: no law core -> stopped, not ungoverned.
        if self._core is None:
            return GatewayVerdict("deny", "gate.unreachable", innate=True, stage="local-law",
                                  reason=f"gate core unavailable: {self._import_error}")
        # Stage 1: local law (innate egress/secret + MRH path/command scope).
        try:
            ev = self._normalize(intent)
            # Resolve the member's LIVE policy (its grants) the way every real shim does:
            # fetch the daemon's snapshot and feed it to resolve_agent_policy as the vault
            # reader. With policy=None the core sees `granted: ()` and an operator's live
            # grant is never consulted (measured 2026-09-03: dp granted scope-311387783493
            # and memory_write still denied mrh.path). No snapshot => degrade to policy=None
            # (the core's own fail-closed path), never a manufactured grant.
            policy = None
            if self._mech is not None:
                try:
                    snap = self._mech.fetch_policy_snapshot(
                        self.member_id, host_agent=getattr(self, "_host_agent", "sage-raising"))
                    if snap is not None:
                        policy = self._core.resolve_agent_policy(self._profile,
                                                                 vault_reader=lambda _m: snap)
                except Exception:
                    policy = None
            v = self._core.evaluate(ev, self._profile, self.workspace, policy=policy)
            granted = _granted_roots(self._core, policy, self.workspace)
        except Exception as e:
            return GatewayVerdict("deny", "gate.raised", innate=True, stage="local-law",
                                  reason=f"{type(e).__name__}: {e}")
        if v.decision == "deny":
            return GatewayVerdict("deny", v.rule, v.reason, v.innate, stage="local-law")
        # Stage 2: society safety (daemon). A consequential act the society cannot
        # vet must NOT proceed — fail-closed. Observational acts soft-pass when the
        # mechanism is unavailable (no external effect; witness is accountability).
        consequential = intent.effector in _CONSEQUENTIAL
        if self._mech is None:
            if consequential:
                return GatewayVerdict("deny", "society.unavailable", stage="society",
                                      reason="society-safety mechanism unavailable; consequential act denied")
        else:
            try:
                # The mechanism's REAL contract (hestia plugins/_shared/hestia_gate_mechanism.py
                # `query_society_safety(event, *, plugin_id, host_agent, ...)`): the event is
                # {tool_name, tool_input} and the answer is a SafetyVerdict whose `allow` is the
                # only field a caller may proceed on; `decided=False` is a fail-closed non-verdict.
                # Until 2026-09-02 this was called as `query_society_safety(ev.raw)`, which raised
                # TypeError on every call — so every consequential act was denied
                # `society.unreachable` and the "governor" was never actually consulted.
                safe = self._mech.query_society_safety(
                    {"tool_name": ev.tool, "tool_input": dict(ev.raw)},
                    plugin_id=self.member_id, host_agent=_HOST_AGENT,
                    host_session_id=self.host_session_id)
                if not getattr(safe, "allow", False):
                    decided = getattr(safe, "decided", False)
                    return GatewayVerdict(
                        "deny", "society.unsafe" if decided else "society.no_verdict",
                        stage="society",
                        reason=getattr(safe, "message", None) or "society denied")
            except Exception as e:
                if consequential:
                    return GatewayVerdict("deny", "society.unreachable", stage="society",
                                          reason=f"society-safety failed ({type(e).__name__}); consequential act denied")
                # observational: local law already allowed, soft-pass
        return GatewayVerdict(v.decision, v.rule, v.reason or "ok", v.innate, stage="local-law",
                              granted=granted, command=getattr(ev, "command", None))

    # -- the F1a seam: gate, then dispatch, then consume the result ----------
    def dispatch(self, intent: BeingIntent) -> ResultEnvelope:
        v = self.gate(intent)
        if v.blocks:
            # A refusal is witnessed on the chain as a policy_decision, so the being holds
            # a hash it can appeal (hestia_appeal needs one; a client-side deny that never
            # reached the chain was unappealable, measured 2026-09-05). Unwitnessed when the
            # daemon is unreachable: the refusal stands either way, and says so.
            wid = None
            wd = getattr(self._dispatcher, "witness_deny", None)
            if wd is not None:
                try:
                    wid = wd(intent, v)
                except Exception:
                    wid = None
            import dataclasses as _dc
            v = _dc.replace(v, witness_id=wid)      # GatewayVerdict is frozen
            err = f"{v.rule}: {v.reason}"
            err += _home_hint(intent, self._dispatcher)
            err += (f" (deny witnessed {wid}; if you think this is wrong, appeal with deny_hash={wid})"
                    if wid else " (deny not witnessed: daemon unreachable, so it cannot be appealed yet)")
            return ResultEnvelope(ok=False, refused=True, verdict=v, error=err, witness_id=wid)
        if self._dispatcher is None:
            # F1a not wired: allowed by law, but nothing can execute it yet. We
            # surface that honestly — we do NOT fabricate a result (PR #579 / F1a).
            return ResultEnvelope(ok=False, pending=True, verdict=v,
                                  note="awaiting hestia dispatch substrate (F1a)")
        # F1a executes on the being's behalf and returns a witnessed envelope; we
        # consume it verbatim. A dispatcher that throws is a failed act, not an
        # ungoverned one — the intent was already gated ALLOW above.
        try:
            env = self._dispatcher(intent, v)
        except Exception as e:
            return ResultEnvelope(ok=False, verdict=v,
                                  error=f"dispatch failed ({type(e).__name__}): {e}")
        env.verdict = v
        return env


if __name__ == "__main__":  # runnable demo / smoke test
    inst = os.path.expanduser(
        "~/ai-workspace/sage/sage/instances/sprout-qwen3.8-distill-2b")
    c = BeingGateClient("sprout-being", inst + "/identity.json",
                        os.path.expanduser("~/ai-workspace/sage"))
    demos = [
        ("peer_ask -> legion",      BeingIntent("peer_ask", {"to": "legion", "body": "hi"})),
        ("witness session close",   BeingIntent("witness", {"event": "session_close"})),
        ("memory_write own note",   BeingIntent("memory_write", {"path": inst + "/notes.md", "content": "x"})),
        ("shell (not in registry)", BeingIntent("shell", {"command": "rm -rf /"})),
        ("memory_write ESCAPE",     BeingIntent("memory_write", {"path": "/etc/cron.d/x", "content": "x"})),
        ("memory_read credential",  BeingIntent("memory_read", {"path": "~/.ssh/id_ed25519"})),
    ]
    print(f"{'intent':26} {'dec':6} {'rule@stage':28} reason")
    for label, it in demos:
        v = c.gate(it)
        print(f"{label:26} {v.decision.upper():6} {(v.rule or '-') + '@' + v.stage:28} {(v.reason or '')[:44]}")
    env = c.dispatch(demos[0][1])
    print(f"dispatch(peer_ask): verdict={env.verdict.decision} pending={env.pending} "
          f"-> {env.to_tool_message()}")
