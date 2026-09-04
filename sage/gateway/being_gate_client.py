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
    (peer_ask, memory_write, channel_egress, mesh) hard-deny; only OBSERVATIONAL effectors
    (witness, memory_read) soft-pass, since they carry no external effect and
    witness is itself the accountability primitive. Local-law admission (Stage 1)
    is never enough on its own for a consequential act — end-to-end execution
    authority requires the society governor too.
  * BOUNDED REGISTRY: the being's only effectors are mesh/peer_ask, witness,
    memory (its own dir), channel egress. No shell, no raw FS. Enforced twice:
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
    env = os.environ.get("HESTIA_GATE_SHARED")
    if env and os.path.isdir(env):
        return env
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

# The most a being may post in one review. Without a cap the grammar lets a being put its
# whole context window into a fleet PR in one act; with it the gate raises and records
# (gate.raised) instead of GitHub receiving it. Sprout's nit on #34, 2026-09-03.
PR_REVIEW_BODY_CAP = 16000


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
    body = str(args.get("body", ""))
    if not body.strip():
        raise ValueError("pr_review needs a non-empty 'body'")
    if len(body) > PR_REVIEW_BODY_CAP:
        raise ValueError(f"pr_review 'body' is {len(body)} chars; the cap is {PR_REVIEW_BODY_CAP}")
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
    # repo_arg: the validated arg naming the repository the act targets. _normalize stamps
    # it into NormalizedEvent.repos so the law's mrh.repo branch rules the act BY NAME.
    # Measured (Sprout 2026-09-03, reproduced on Legion): the composed gh line names no
    # filesystem path, so command-scope judges it "not a reach" and ALLOWS it under an
    # EMPTY grant. The one outward act in this registry was the one act scope never saw.
    "pr_review":      dict(tool="pr_review",    path_args=(),       cmd_arg=None,
                           compose=pr_review_command, repo_arg="repo"),
}


# Society-safety failure boundary per effector class. Observational acts carry no
# external effect and may soft-pass when the society governor is unavailable;
# consequential acts must not proceed without it (fail-closed).
_OBSERVATIONAL = frozenset({"witness", "memory_read"})
_CONSEQUENTIAL = frozenset({"peer_ask", "memory_write", "channel_egress", "mesh", "pr_review"})

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


@dataclass(frozen=True)
class GatewayVerdict:
    decision: str          # "allow" | "warn" | "deny"
    rule: str = ""
    reason: str = ""
    innate: bool = False
    stage: str = ""        # which stage decided: registry | local-law | society

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
                 dispatcher: "Optional[Dispatcher]" = None,
                 host_session_id: Optional[str] = None):
        self.member_id = member_id
        self.workspace = workspace
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
            # a COMPOSED verb: the seat builds the exact outward act (a shell line) from the
            # being's args, and THAT is what the law judges. Bad args raise here and gate()
            # turns that into a deny (gate.raised), never a silent pass. The being never
            # fills a command; the registry never carries a cmd_arg for a composed verb.
            command = compose(intent.args)
        repos: List[str] = []
        if spec.get("repo_arg"):
            # The act is scoped by the NAME it carries (gate 1b, mrh.repo), the grant the
            # being asks for and dp says yes to. Stamped AFTER compose, so it is the same
            # validated value the command line carries. Full `dp-web4/<name>` on purpose: a
            # bare `SAGE` scope is also a path grant on the seat's SAGE checkout (measured:
            # scope ["SAGE"] allows read_file on <ws>/SAGE/README.md), while `dp-web4/SAGE`
            # never matches a workspace segment, so the outward grant does not double as
            # filesystem reach. Spell the grant as GitHub spells the repo, case-sensitive.
            repos = [str(intent.args.get(spec["repo_arg"], "")).strip()]
        return self._core.NormalizedEvent(
            tool=spec["tool"], paths=paths, repos=repos, command=command,
            cwd=self.workspace, raw={"effector": intent.effector, **intent.args},
        )

    # -- gate one intent (intent -> verdict), fail-closed --------------------
    def gate(self, intent: BeingIntent) -> GatewayVerdict:
        # Stage 0: bounded registry. Unknown effector never reaches the law.
        if intent.effector not in _REGISTRY:
            return GatewayVerdict("deny", "registry.unbounded", stage="registry",
                                  reason=f"'{intent.effector}' is not a gateway-member effector")
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
        return GatewayVerdict(v.decision, v.rule, v.reason or "ok", v.innate, stage="local-law")

    # -- the F1a seam: gate, then dispatch, then consume the result ----------
    def dispatch(self, intent: BeingIntent) -> ResultEnvelope:
        v = self.gate(intent)
        if v.blocks:
            return ResultEnvelope(ok=False, refused=True, verdict=v,
                                  error=f"{v.rule}: {v.reason}")
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
