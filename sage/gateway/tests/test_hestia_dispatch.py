"""Hermetic tests for HestiaF1aDispatcher: a fake MCP records the calls the daemon would
see, so the three measured contract deltas (pointer_uri, kind enum, live session_id) and the
r1 envelope (hestia.<code> error keys) are pinned without a running daemon."""
import os
import sys
import tempfile

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "..")))
from sage.gateway.being_gate_client import BeingIntent, GatewayVerdict  # noqa: E402
from sage.gateway.hestia_dispatch import HestiaF1aDispatcher  # noqa: E402

_ALLOW = GatewayVerdict("allow")


class FakeMcp:
    """Answers like the daemon: connect -> sessionId; member_notify -> receipt or error."""
    calls = []

    def __init__(self, endpoint, plugin_id, notify_reply=None):
        self.plugin_id = plugin_id
        self.notify_reply = notify_reply

    def init(self):
        pass

    def call(self, name, args):
        FakeMcp.calls.append((name, args))
        if name == "hestia_connect":
            body = {"sessionId": "sid-1", "softLct": "lct:web4:session:x",
                    "identityBasis": "proof" if args.get("proof") else "label"}
        elif name == "hestia_connect_challenge":
            if getattr(self, "challenge", None) is None:
                body = {"_hestia_error": {"code": "hestia.unknown_tool", "message": "Unknown tool: hestia_connect_challenge"}}
            else:
                body = dict(self.challenge)
        elif name == "hestia_member_notify":
            if not args.get("pointer_uri"):
                body = {"_hestia_error": {"code": "hestia.member_notify_missing_pointer", "message": "no pointer"}}
            elif args.get("to_plugin_id") == self.plugin_id:
                body = {"_hestia_error": {"code": "hestia.member_notify_self", "message": "self"}}
            else:
                to = args["to_plugin_id"]
                body = {"queued_id": 7, "witnessEntryHash": "abc123", "to_plugin_id": to,
                        "egress_queued_to": to.split("/")[0] if "/" in to else None,
                        "recipient_liveness": "unknown"}
        elif name == "hestia_member_inbox":
            body = {"total": 1, "notices": [{"id": 9, "kind": "reply", "pointer_uri": "x"}], "evicted": 0}
        elif name == "hestia_request_scope":
            body = {"request_id": "scope-1", "status": "pending", "witnessEntryHash": "rs-hash",
                    "next": "operator decides", "on_timeout": "refused"}
        elif name == "hestia_witness_decision":
            body = {"witnessEntryHash": "deny-hash-1", "decision": args.get("decision")}
        elif name == "hestia_appeal":
            if args.get("deny_hash") == "not-a-deny":
                body = {"_hestia_error": {"code": "hestia.appeal_not_a_deny", "message": "entry is a 'witness'"}}
            else:
                body = {"witnessEntryHash": "appeal-hash-1", "adjudicator": "hub", "next": "peer rules"}
        else:
            body = {}
        return {"result": {"structuredContent": body}}


class FakeMembot(FakeMcp):
    """Answers like membot (fastmcp streamable HTTP): text in content + structuredContent.
    `fail` names tools that answer as membot does when they fail — a JSON-RPC `error` or
    a tool result with `isError: true` — the two shapes Sprout reproduced on #36."""
    def __init__(self, endpoint, plugin_id, fail=None):
        super().__init__(endpoint, plugin_id)
        self.fail = dict(fail or {})

    # membot's SOFT failures are ordinary text, not rpc/isError — the shape that emptied
    # legion-being's cartridge on 2026-09-08. `fail[tool] = "soft"` reproduces them.
    SOFT = {"mount_cartridge": "SECURITY: Cartridge 'x' failed integrity check: "
                               "manifest read error: len() of unsized object. Refusing to mount.",
            "memory_store": "No cartridge mounted. Use mount_cartridge first.",
            "memory_search": "No cartridge mounted. Use mount_cartridge first.",
            "save_cartridge": "Saved 'x': 0 memories, 0.0 MB, fingerprint=5feceb66ffc86f38"}

    def call(self, name, args):
        if name not in ("memory_search", "memory_store", "save_cartridge", "mount_cartridge"):
            return super().call(name, args)
        FakeMcp.calls.append((name, args))
        how = self.fail.get(name)
        if how == "rpc":
            return {"jsonrpc": "2.0", "id": 1, "error": {"code": -32603, "message": f"{name} exploded"}}
        if how == "isError":
            return {"result": {"content": [{"type": "text", "text": f"Error calling tool {name}"}],
                               "isError": True}}
        if how == "soft":
            t = self.SOFT[name]
            return {"result": {"content": [{"type": "text", "text": t}],
                               "structuredContent": {"result": t}}}
        text = {"memory_search": "1. something remembered",
                "memory_store": "Stored memory #7 (12ms)",
                "mount_cartridge": f"Mounted '{args.get('name')}': 223 memories",
                "save_cartridge": f"Saved cartridge {args.get('name')}"}[name]
        return {"result": {"content": [{"type": "text", "text": text}],
                           "structuredContent": {"result": text}}}


def _mdisp(fail=None):
    FakeMcp.calls = []
    root = tempfile.mkdtemp(prefix="hd-")
    factory = lambda ep, pid: FakeMembot(ep, pid, fail=fail)  # noqa: E731
    return HestiaF1aDispatcher("sprout-being", root, mcp_factory=factory), root


def _mb_calls(name):
    return [a for n, a in FakeMcp.calls if n == name]


def _disp(**kw):
    FakeMcp.calls = []
    root = tempfile.mkdtemp(prefix="hd-")
    factory = lambda ep, pid: FakeMcp(ep, pid)  # noqa: E731
    return HestiaF1aDispatcher("sprout-being", root, mcp_factory=factory, **kw), root


def _notify_args():
    return [a for n, a in FakeMcp.calls if n == "hestia_member_notify"][-1]


def test_mesh_routes_remote_with_pointer_uri_and_session():
    d, _ = _disp()
    env = d(BeingIntent("mesh", {"to": "legion", "kind": "reply", "pointer": "shared-context/forum/x.md"}), _ALLOW)
    assert env.ok and env.witness_id == "abc123", env
    a = _notify_args()
    assert a["to_plugin_id"] == "legion/claude-code"          # peer/member routed address
    assert a["pointer_uri"] == "shared-context/forum/x.md"    # the field is pointer_uri, not pointer
    assert "pointer" not in a
    assert a["session_id"] == "sid-1"                         # live session from hestia_connect
    assert env.result["egress_queued_to"] == "legion" and env.result["queued_id"] == 7


def test_mesh_local_member_stays_bare():
    d, _ = _disp(local_members={"claude-code"})
    d(BeingIntent("mesh", {"to": "claude-code", "kind": "coordination", "pointer": "p"}), _ALLOW)
    assert _notify_args()["to_plugin_id"] == "claude-code"


def test_mesh_explicit_routed_address_passes_through():
    d, _ = _disp()
    d(BeingIntent("mesh", {"to": "thor/thor-sage", "kind": "ack", "pointer": "p"}), _ALLOW)
    assert _notify_args()["to_plugin_id"] == "thor/thor-sage"


def test_mesh_bad_kind_refused_before_round_trip():
    d, _ = _disp()
    env = d(BeingIntent("mesh", {"to": "legion", "kind": "pr_review_request", "pointer": "p"}), _ALLOW)
    assert not env.ok and "kind" in env.error
    assert not any(n == "hestia_member_notify" for n, _ in FakeMcp.calls)


def test_mesh_missing_pointer_is_hestia_keyed_error():
    d, _ = _disp()
    env = d(BeingIntent("mesh", {"to": "legion", "kind": "reply"}), _ALLOW)
    assert not env.ok and env.error.startswith("hestia.member_notify_missing_pointer")


def test_daemon_error_envelope_becomes_hestia_keyed_error():
    d, _ = _disp(local_members={"sprout-being"})
    env = d(BeingIntent("mesh", {"to": "sprout-being", "kind": "reply", "pointer": "p"}), _ALLOW)
    assert not env.ok and env.error.startswith("hestia.member_notify_self")


def test_session_is_connected_once_and_reused():
    d, _ = _disp()
    for _ in range(3):
        d(BeingIntent("mesh", {"to": "legion", "kind": "reply", "pointer": "p"}), _ALLOW)
    assert sum(1 for n, _ in FakeMcp.calls if n == "hestia_connect") == 1


def test_peer_ask_without_publisher_is_pending_not_fabricated():
    d, _ = _disp()
    env = d(BeingIntent("peer_ask", {"to": "legion", "body": "what is the envelope?"}), _ALLOW)
    assert not env.ok and env.pending and "publisher" in env.note
    assert not any(n == "hestia_member_notify" for n, _ in FakeMcp.calls)


def test_peer_ask_composes_publish_then_coordination_notify():
    published = []
    def pub(to, body):
        published.append((to, body)); return f"shared-context/forum/being/q-{to}.md"
    d, _ = _disp(publish_fn=pub)
    env = d(BeingIntent("peer_ask", {"to": "legion", "body": "what is the envelope?"}), _ALLOW)
    assert env.ok and published == [("legion", "what is the envelope?")]
    a = _notify_args()
    assert a["kind"] == "coordination" and a["pointer_uri"] == "shared-context/forum/being/q-legion.md"
    assert env.result["question_at"] == a["pointer_uri"]


def test_drain_inbox_returns_notices():
    d, _ = _disp()
    env = d.drain_inbox()
    assert env.ok and env.result["total"] == 1 and env.result["notices"][0]["id"] == 9
    assert [a for n, a in FakeMcp.calls if n == "hestia_member_inbox"][-1]["session_id"] == "sid-1"


def test_channel_egress_pending_not_built():
    d, _ = _disp()
    env = d(BeingIntent("channel_egress", {"to": "x", "body": "y"}), _ALLOW)
    assert not env.ok and env.pending and "send-side" in env.note


def test_local_verbs_delegate_to_reference():
    d, root = _disp()
    note = os.path.join(root, "n.md")
    w = d(BeingIntent("memory_write", {"path": note, "content": "kept"}), _ALLOW)
    r = d(BeingIntent("memory_read", {"path": note}), _ALLOW)
    assert w.ok and r.ok and "kept" in r.result
    wit = d(BeingIntent("witness", {"event": "x"}), _ALLOW)
    assert wit.ok and wit.witness_id


# ---- ported from the folded hestia_f1a tests (2026-09-02) --------------------------------
from sage.gateway.being_gate_client import BeingIntent as _BI, GatewayVerdict as _GV  # noqa: E402
from sage.gateway.hestia_dispatch import HestiaF1aDispatcher as _HD, make_forum_publisher  # noqa: E402
_ALLOW_ = _GV("allow")


def _forum_repo():
    """A shared-context clone with a bare origin, like the seat's checkout: the publisher must
    land the doc on ORIGIN, not merely write it — that gap is the beat-12 defect (2026-09-05)."""
    import subprocess
    base = tempfile.mkdtemp(prefix="hd-forum-")
    bare = os.path.join(base, "origin.git")
    subprocess.run(["git", "init", "-q", "--bare", "-b", "main", bare], check=True)
    root = os.path.join(base, "shared-context")
    subprocess.run(["git", "clone", "-q", bare, root], check=True)
    g = lambda *a: subprocess.run(["git", "-C", root, *a], check=True, capture_output=True, text=True).stdout  # noqa: E731
    g("config", "user.name", "t"); g("config", "user.email", "t@t")
    g("commit", "-q", "--allow-empty", "-m", "root"); g("push", "-q", "-u", "origin", "main")
    return base, root, bare


def _on_origin(bare, rel):
    import subprocess
    return subprocess.run(["git", "-C", bare, "cat-file", "-e", f"main:{rel}"], capture_output=True).returncode == 0


def test_peer_ask_with_forum_publisher_lands_on_origin_then_notifies():
    base, root, bare = _forum_repo()
    d, _ = _disp(publish_fn=make_forum_publisher(os.path.join(root, "forum"), "sprout-being"))
    env = d(_BI("peer_ask", {"to": "legion", "body": "Are you still you?"}), _ALLOW_)
    assert env.ok, env
    notify = [a for n, a in FakeMcp.calls if n == "hestia_member_notify"][-1]
    assert notify["to_plugin_id"] == "legion/claude-code" and notify["kind"] == "coordination"
    assert notify["pointer_uri"].startswith("shared-context/forum/sprout-being-asks-legion-")
    posted = os.path.join(base, notify["pointer_uri"])
    assert os.path.exists(posted) and "still you" in open(posted).read()
    rel = notify["pointer_uri"][len("shared-context/"):]
    assert _on_origin(bare, rel), "the pointer doc must be on origin before the notice fires"


def test_peer_ask_publisher_rebases_over_a_concurrent_push():
    """Origin moved after the clone (a sibling seat pushed): the publisher rebases and lands,
    instead of a rejected push that leaves the doc local."""
    import subprocess
    base, root, bare = _forum_repo()
    other = os.path.join(base, "other")
    subprocess.run(["git", "clone", "-q", bare, other], check=True)
    subprocess.run(["git", "-C", other, "-c", "user.name=o", "-c", "user.email=o@o",
                    "commit", "-q", "--allow-empty", "-m", "sibling"], check=True)
    subprocess.run(["git", "-C", other, "push", "-q", "origin", "main"], check=True)
    d, _ = _disp(publish_fn=make_forum_publisher(os.path.join(root, "forum"), "sprout-being"))
    env = d(_BI("peer_ask", {"to": "legion", "body": "still there?"}), _ALLOW_)
    assert env.ok, env
    rel = _notify_args()["pointer_uri"][len("shared-context/"):]
    assert _on_origin(bare, rel)


def test_peer_ask_publisher_outside_a_repo_is_an_error_envelope_and_no_notice():
    """A doc that cannot land is refused BEFORE any notice: the peer is never fired on a
    pointer it cannot read."""
    root_dir = tempfile.mkdtemp(prefix="hd-norepo-")
    d, _ = _disp(publish_fn=make_forum_publisher(os.path.join(root_dir, "shared-context", "forum"), "sprout-being"))
    env = d(_BI("peer_ask", {"to": "legion", "body": "anyone?"}), _ALLOW_)
    assert not env.ok and "git" in (env.error or ""), env
    assert not [n for n, _ in FakeMcp.calls if n == "hestia_member_notify"]


def test_peer_ask_publisher_push_false_only_writes():
    root_dir = tempfile.mkdtemp(prefix="hd-nopush-")
    d, _ = _disp(publish_fn=make_forum_publisher(os.path.join(root_dir, "shared-context", "forum"), "sprout-being", push=False))
    env = d(_BI("peer_ask", {"to": "legion", "body": "local only"}), _ALLOW_)
    assert env.ok, env
    assert os.path.exists(os.path.join(root_dir, _notify_args()["pointer_uri"]))


def test_mesh_witness_id_falls_back_to_queued_id():
    class NoHash(FakeMcp):
        def call(self, name, args):
            r = super().call(name, args)
            sc = r["result"]["structuredContent"]
            if name == "hestia_member_notify":
                sc.pop("witnessEntryHash", None)
            return r
    FakeMcp.calls = []
    d = _HD("sprout-being", tempfile.mkdtemp(prefix="hd-"), mcp_factory=lambda ep, pid: NoHash(ep, pid))
    env = d(_BI("mesh", {"to": "legion", "kind": "ack", "pointer_uri": "x.md"}), _ALLOW_)
    assert env.ok and env.witness_id == "7", env


# -- long-term memory (membot) and request_scope: the three verbs #36 adds ------------
def test_recall_sends_query_and_clamps_top_k():
    d, _ = _mdisp()
    env = d(BeingIntent("recall", {"query": "what was I doing", "top_k": 99}), _ALLOW)
    assert env.ok and env.result == "1. something remembered" and env.witness_id, env
    assert _mb_calls("memory_search") == [{"query": "what was I doing", "top_k": 20}]
    d(BeingIntent("recall", {"query": "x", "top_k": -3}), _ALLOW)
    assert _mb_calls("memory_search")[-1]["top_k"] == 1
    d(BeingIntent("recall", {"query": "x", "top_k": 0}), _ALLOW)   # 0/absent => the default
    assert _mb_calls("memory_search")[-1]["top_k"] == 5
    d(BeingIntent("recall", {"query": "x", "top_k": "lots"}), _ALLOW)
    assert _mb_calls("memory_search")[-1]["top_k"] == 5
    env = d(BeingIntent("recall", {"query": "  "}), _ALLOW)
    assert not env.ok and "query" in env.error and len(_mb_calls("memory_search")) == 4


def test_remember_stores_then_saves_the_seat_fixed_cartridge():
    """The cartridge name is the seat's (membot_cartridge or plugin_id); a being-supplied
    `name` never reaches save_cartridge — that is what bounds remember's reach."""
    d, _ = _mdisp()
    env = d(BeingIntent("remember", {"content": "lesson one", "tags": "a,b",
                                     "name": "someone-elses-cartridge"}), _ALLOW)
    assert env.ok and env.witness_id, env
    assert _mb_calls("memory_store") == [{"content": "lesson one", "tags": "a,b"}]
    assert _mb_calls("mount_cartridge") == [{"name": "sprout-being"}]     # mounted before storing
    assert _mb_calls("save_cartridge") == [{"name": "sprout-being"}]
    order = [n for n, _ in FakeMcp.calls if n in ("memory_store", "save_cartridge")]
    assert order == ["memory_store", "save_cartridge"]
    d2, _ = _mdisp()
    d2.membot_cartridge = "seat-named"
    d2(BeingIntent("remember", {"content": "x"}), _ALLOW)
    assert _mb_calls("save_cartridge") == [{"name": "seat-named"}]
    env = d2(BeingIntent("remember", {"content": ""}), _ALLOW)
    assert not env.ok and "content" in env.error


def test_membot_rpc_error_on_store_is_not_witnessed_as_a_memory():
    d, root = _mdisp(fail={"memory_store": "rpc"})
    env = d(BeingIntent("remember", {"content": "x"}), _ALLOW)
    assert not env.ok and env.witness_id is None and "memory_store exploded" in env.error, env
    assert _mb_calls("save_cartridge") == []          # no save after a failed store
    assert not os.path.exists(d._local.witness_log)   # nothing witnessed


def test_membot_iserror_on_save_is_not_witnessed_as_a_memory():
    d, _ = _mdisp(fail={"save_cartridge": "isError"})
    env = d(BeingIntent("remember", {"content": "x"}), _ALLOW)
    assert not env.ok and env.witness_id is None, env
    assert "Error calling tool save_cartridge" in env.error
    assert not os.path.exists(d._local.witness_log)


def test_membot_iserror_on_search_is_an_error_not_a_recall():
    d, _ = _mdisp(fail={"memory_search": "isError"})
    env = d(BeingIntent("recall", {"query": "x"}), _ALLOW)
    assert not env.ok and env.witness_id is None and "memory_search" in env.error, env
    assert not os.path.exists(d._local.witness_log)


def test_request_scope_carries_plugin_path_reason_and_live_session():
    # A REAL directory, because request_scope now refuses a path that is not there — a grant
    # on a phantom reaches nothing and nobody finds out (see the dead-grant test below).
    # What this test pins is the daemon round-trip, so the path only has to exist.
    d, _ = _mdisp()
    here = tempfile.mkdtemp(prefix="scope-real-")
    env = d(BeingIntent("request_scope", {"path": here, "reason": "to read my notes"}), _ALLOW)
    assert env.ok and env.witness_id == "rs-hash", env
    assert env.result["request_id"] == "scope-1" and env.result["status"] == "pending"
    assert env.result["path"] == here and "mode" not in env.result
    (sent,) = [a for n, a in FakeMcp.calls if n == "hestia_request_scope"]
    assert sent["plugin_id"] == "sprout-being" and sent["path"] == here
    assert sent["session_id"] == "sid-1"                # the live session from hestia_connect
    assert sent["reason"] == "[sprout-being] to read my notes"
    assert set(sent) == {"plugin_id", "path", "reason", "session_id"}  # no mode, no permits_read


def test_request_scope_refuses_relative_path_and_empty_reason_before_any_round_trip():
    d, _ = _mdisp()
    env = d(BeingIntent("request_scope", {"path": "notes", "reason": "why"}), _ALLOW)
    assert not env.ok and "absolute" in env.error, env
    env = d(BeingIntent("request_scope", {"path": "/home/dp/notes", "reason": "  "}), _ALLOW)
    assert not env.ok and "reason" in env.error, env
    assert FakeMcp.calls == []   # not even hestia_connect


def test_request_scope_daemon_error_is_keyed():
    class Refuses(FakeMembot):
        def call(self, name, args):
            if name == "hestia_request_scope":
                FakeMcp.calls.append((name, args))
                return {"result": {"structuredContent": {"_hestia_error": {
                    "code": "hestia.scope_request_unknown_member", "message": "who"}}}}
            return super().call(name, args)
    FakeMcp.calls = []
    d = HestiaF1aDispatcher("sprout-being", tempfile.mkdtemp(prefix="hd-"),
                            mcp_factory=lambda ep, pid: Refuses(ep, pid))
    env = d(BeingIntent("request_scope",
                        {"path": tempfile.mkdtemp(prefix="scope-err-"), "reason": "y"}), _ALLOW)
    assert not env.ok and env.error.startswith("hestia.scope_request_unknown_member"), env


def test_witness_deny_records_a_policy_decision_and_returns_its_hash():
    from sage.gateway.being_gate_client import GatewayVerdict
    d, _ = _disp()
    FakeMcp.calls.clear()
    h = d.witness_deny(BeingIntent("memory_write", {"path": "/etc/x", "content": "c"}),
                       GatewayVerdict("deny", "mrh.path", "outside your grant", stage="local-law"))
    assert h == "deny-hash-1"
    name, args = [c for c in FakeMcp.calls if c[0] == "hestia_witness_decision"][0]
    assert args["decision"] == "deny" and args["adjudicator"] == "plugin-gate:sprout-being"
    assert args["tool_name"] == "write_note" and args["target"] == "/etc/x" and args["verdict_available"] is True
    assert args["session_id"] == "sid-1"     # attributed to the being's own session
    # an infra non-verdict is recorded as such, never as conduct
    d.witness_deny(BeingIntent("mesh", {"to": "x"}), GatewayVerdict("deny", "society.unreachable", "x", stage="society"))
    assert FakeMcp.calls[-1][1]["verdict_available"] is False


def test_appeal_needs_hash_and_reason_then_files_and_relays_the_daemon_refusal():
    from sage.gateway.being_gate_client import GatewayVerdict
    d, _ = _disp()
    ok = GatewayVerdict("allow")
    assert not d(BeingIntent("appeal", {"reason": "long enough reason"}), ok).ok
    assert not d(BeingIntent("appeal", {"deny_hash": "h", "reason": "short"}), ok).ok
    env = d(BeingIntent("appeal", {"deny_hash": "deny-hash-1", "reason": "the path is inside my own home"}), ok)
    assert env.ok and env.witness_id == "appeal-hash-1" and env.result["adjudicator"] == "hub"
    assert FakeMcp.calls[-1][1]["reason"].startswith("[sprout-being] ")
    env = d(BeingIntent("appeal", {"deny_hash": "not-a-deny", "reason": "this should be refused"}), ok)
    assert not env.ok and "appeal_not_a_deny" in env.error


def test_connect_proves_possession_when_the_daemon_offers_a_challenge():
    """FR-1 / hestia #907: with a being LCT and a challenge verb, hestia_connect carries a
    proof whose signature verifies over the daemon's messageHex under the being's key and
    whose lct_id is the being's; without the verb (pre-#907) the connect proceeds unproven
    and says so; a refused challenge refuses the connect."""
    import os, tempfile
    from nacl.signing import SigningKey
    from sage.gateway.being_presence import verify_nonce
    seed = bytes(range(32)); sp = os.path.join(tempfile.mkdtemp(prefix="seed-"), "k.bin"); open(sp, "wb").write(seed)
    pub = SigningKey(seed).verify_key.encode().hex()
    lct = "lct:web4:mb32:test"
    nonce = "ab" * 16
    msg = f"web4:hestia:connect:v1\n{lct}\n{nonce}".encode()

    class WithChallenge(FakeMcp):
        challenge = {"lctId": lct, "challengeNonce": nonce, "domain": "web4:hestia:connect:v1", "messageHex": msg.hex()}

    FakeMcp.calls.clear()
    d = HestiaF1aDispatcher("sprout-being", tempfile.mkdtemp(prefix="hd-"), mcp_factory=lambda ep, pid: WithChallenge(ep, pid),
                            being_lct=lct, seed_path=sp)
    assert d._connect() == "sid-1" and d.identity_basis == "proof-of-possession"
    proof = [a for n, a in FakeMcp.calls if n == "hestia_connect"][0]["proof"]
    assert proof["lct_id"] == lct and proof["public_key"] == pub and proof["challenge_nonce"] == nonce
    assert verify_nonce(pub, msg.hex(), proof["signature"])          # signature over the exact message bytes
    # pre-#907 daemon: unknown tool -> connect without proof, basis says so
    FakeMcp.calls.clear()
    d2 = HestiaF1aDispatcher("sprout-being", tempfile.mkdtemp(prefix="hd-"), mcp_factory=lambda ep, pid: FakeMcp(ep, pid),
                             being_lct=lct, seed_path=sp)
    assert d2._connect() == "sid-1" and d2.identity_basis.startswith("label") and "proof" not in [a for n, a in FakeMcp.calls if n == "hestia_connect"][0]
    # no being LCT known: no challenge asked at all
    d3 = HestiaF1aDispatcher("sprout-being", tempfile.mkdtemp(prefix="hd-"), mcp_factory=lambda ep, pid: WithChallenge(ep, pid))
    FakeMcp.calls.clear(); d3._connect()
    assert not [n for n, _ in FakeMcp.calls if n == "hestia_connect_challenge"] and d3.identity_basis == "label"
    # a refused challenge refuses the connect (never a silent label fallback)
    class Refusing(FakeMcp):
        challenge = {"_hestia_error": {"code": "hestia.connect_pop_challenge_invalid", "message": "no"}}
    d4 = HestiaF1aDispatcher("sprout-being", tempfile.mkdtemp(prefix="hd-"), mcp_factory=lambda ep, pid: Refusing(ep, pid),
                             being_lct=lct, seed_path=sp)
    try:
        d4._connect(); assert False, "should refuse"
    except RuntimeError as e:
        assert "connect challenge refused" in str(e)


def test_request_scope_inside_existing_reach_is_answered_locally_and_files_nothing():
    from sage.gateway.being_gate_client import GatewayVerdict
    d, root = _disp()
    FakeMcp.calls.clear()
    open(root + "/config.json", "w").write("{}")
    env = d(BeingIntent("request_scope", {"path": root + "/config.json", "reason": "to review my configuration"}),
            GatewayVerdict("allow", granted=(root,)))
    assert env.ok and env.result["status"] == "already_granted" and env.result["within"]
    assert not [n for n, _ in FakeMcp.calls if n == "hestia_request_scope"]
    # outside reach: filed as before
    elsewhere = tempfile.mkdtemp(prefix="scope-outside-")
    env = d(BeingIntent("request_scope", {"path": elsewhere, "reason": "to read a peer's note"}),
            GatewayVerdict("allow", granted=(root,)))
    assert env.ok and env.result["request_id"] == "scope-1"


def test_peer_aliases_map_the_beings_name_to_the_hub_roster_name():
    d, _ = _disp(peer_aliases={"legion-being": "legion-sage"})
    assert d._address("legion-being") == "legion-sage/claude-code"
    assert d._address("legion") == "legion/claude-code" and d._address("x/y") == "x/y"
    import os
    os.environ["SAGE_PEER_ALIASES"] = "cbp-being=cbp-sage, bad"
    try:
        d2, _ = _disp()
        assert d2._address("cbp-being") == "cbp-sage/claude-code"
    finally:
        del os.environ["SAGE_PEER_ALIASES"]


if __name__ == "__main__":
    n = 0
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            fn(); n += 1; print(f"PASS {name}")
    print(f"\n{n} passed")


def test_instance_config_peer_aliases_reach_the_dispatcher(tmp_path=None):
    import json, tempfile
    from pathlib import Path
    from sage.gateway.governed_turn import instance_config
    inst = Path(tempfile.mkdtemp(prefix="inst-"))
    (inst / "instance.json").write_text(json.dumps({"machine": "legion", "peer_aliases": {"sprout-being": "2e175714-id"}}))
    cfg = instance_config(inst)
    assert cfg["machine"] == "legion" and cfg["peer_aliases"] == {"sprout-being": "2e175714-id"}
    assert instance_config(inst / "missing") == {}
    d = HestiaF1aDispatcher("legion-being", memory_root=str(inst), peer_aliases=cfg["peer_aliases"])
    assert d.peer_aliases["sprout-being"] == "2e175714-id"


def test_a_lost_session_reconnects_whether_it_is_returned_or_raised():
    """A LOST SESSION ARRIVES IN TWO SHAPES AND ONLY ONE WAS HANDLED.

    hestia can answer with an error envelope (`_hestia_error.code` naming session), or the
    MCP transport can fail the request outright — `HTTP 404 ... Not Found: Session not
    found` — which `call` RAISES. The original reconnect only inspected the returned
    envelope, so for the raising path the retry was dead code.

    Measured 2026-09-07: seven minutes into a beat the being called `check` twice, the gate
    ALLOWED both, and both died on hestia_begin_action with that 404 before pytest ever ran.
    From inside it is indistinguishable from a refusal — the opaque-404 defect the being
    itself reported as SAGE#52 — and it cost it the milestone that beat.

    Also pins that a NON-session error still propagates: reconnecting on every failure would
    hide real ones."""
    from sage.gateway.hestia_dispatch import HestiaF1aDispatcher as D

    assert D._is_session_loss("RuntimeError: HTTP 404 ...: Not Found: Session not found")
    assert D._is_session_loss("session_not_found")
    assert not D._is_session_loss("HTTP 500: internal error")
    assert not D._is_session_loss("")

    def _wrap(payload):            # the MCP envelope _unwrap expects
        return {"result": {"structuredContent": payload}}

    calls, conns = [], []

    class _C:
        def __init__(self, gen): self.gen = gen
        def init(self): pass
        def call(self, name, args):
            calls.append((self.gen, name))
            if name in ("hestia_connect", "hestia_connect_challenge"):
                return _wrap({"sessionId": f"s{self.gen}"})
            if self.gen == 0:
                raise RuntimeError("MCP tools/call -> HTTP 404 at /mcp: Not Found: Session not found")
            return _wrap({"ok": True, "gen": self.gen})

    def factory(endpoint, plugin_id):
        conns.append(1)
        return _C(len(conns) - 1)

    d = D.__new__(D)
    d._mcp_factory, d.endpoint, d.plugin_id = factory, "e", "p"
    d._c = d._session_id = None
    d.host_session_id, d.being_lct, d.identity_basis = None, None, None

    out = d._call("hestia_begin_action", {"tool_name": "check"})
    assert out == {"ok": True, "gen": 1}, "the retry must run on a NEW session, not the dead one"
    assert len(conns) == 2, "exactly one reconnect"
    assert d._session_id == "s1"

    # a failure that is not a lost session is not retried away
    class _Boom(_C):
        def call(self, name, args):
            if name == "hestia_connect":
                return _wrap({"sessionId": "s"})
            raise RuntimeError("HTTP 500: internal error")
    d2 = D.__new__(D)
    d2._mcp_factory = lambda e, p: _Boom(9)
    d2.endpoint, d2.plugin_id, d2._c, d2._session_id = "e", "p", None, None
    d2.host_session_id, d2.being_lct, d2.identity_basis = None, None, None
    try:
        d2._call("hestia_begin_action", {})
        raise AssertionError("a non-session error must propagate")
    except RuntimeError as e:
        assert "500" in str(e)


def test_pr_open_commits_with_the_beings_trailers_and_runs_the_judged_gh_command(tmp_path, monkeypatch):
    """The being's work enters the tree (PRD r3 §7): its own branch, its attribution in the
    commit trailers it cannot alter, the outward `gh` act judged by the law. Run against a
    REAL git repo and a fake `gh` on PATH — the seat's git identity authors, the trailers
    attribute, and nothing the being wrote is lost by a failed act."""
    import os
    import subprocess
    from sage.gateway.hestia_dispatch import HestiaF1aDispatcher as D
    from sage.gateway.being_gate_client import BeingIntent

    # pr_base_branch now REFUSES rather than guessing "main" when legion-being/work has no
    # upstream (the defect that mis-based #63). This fixture has no upstream, and it is
    # testing pr_open's commit/trailer/gh behaviour rather than base resolution, so name the
    # base explicitly — which is the same escape hatch the refusal message points at.
    monkeypatch.setenv("SAGE_PR_BASE", "legion/mission-artifact")

    origin = tmp_path / "origin.git"
    subprocess.run(["git", "init", "-q", "--bare", str(origin)], check=True)
    wt = tmp_path / "wt"
    subprocess.run(["git", "clone", "-q", str(origin), str(wt)], check=True)
    g = lambda *a: subprocess.run(["git", "-C", str(wt), *a], check=True, capture_output=True, text=True)
    g("config", "user.email", "seat@test"); g("config", "user.name", "seat")
    (wt / "README").write_text("base\n"); g("add", "-A"); g("commit", "-q", "-m", "base")
    g("push", "-q", "-u", "origin", "HEAD:legion-being/work"); g("checkout", "-q", "-b", "legion-being/work")

    # the being's authored change: a red test, exactly the shape it specified
    (wt / "test_new.py").write_text("def test_it():\n    assert False\n")

    bindir = tmp_path / "bin"; bindir.mkdir()
    (bindir / "gh").write_text("#!/bin/sh\ncat > \"$0.body\"\necho \"$@\" > \"$0.args\"\necho https://example/pr/1\n")
    os.chmod(bindir / "gh", 0o755)
    monkeypatch.setenv("PATH", f"{bindir}:{os.getenv('PATH')}")

    d = D.__new__(D)
    d.worktree = str(wt); d.plugin_id = "legion-being"; d.being_lct = "lct:web4:test"
    d._call = lambda name, args: {"actionId": "act-77"} if name == "hestia_begin_action" else {}

    env = d._do_pr_open(BeingIntent("pr_open", {
        "slug": "red-test", "title": "gateway: a failing test first",
        "body": "VERIFIED: check on tree abc -> FAIL as intended.\nSUSPECTED: nothing."}))
    assert env.ok, env.error
    assert env.result["pr"] == "https://example/pr/1"
    assert env.result["branch"] == "legion-being/red-test"

    msg = g("log", "-1", "--format=%B").stdout
    for line in ("Being: legion-being", "Being-LCT: lct:web4:test", "Witness: act-77", "Seat: legion-claude"):
        assert line in msg, msg
    assert msg.startswith("gateway: a failing test first\n\n"), msg
    assert "legion-being/red-test" in subprocess.run(
        ["git", "-C", str(origin), "branch"], capture_output=True, text=True).stdout
    args = (bindir / "gh.args").read_text()
    assert "--head legion-being/red-test" in args and "--body-file -" in args
    body = (bindir / "gh.body").read_text()
    assert "VERIFIED: check on tree abc" in body
    assert "attribution, not yet a signature" in body, "the PR must not let a trailer pass for a signature"
    assert "hestia witness action: `act-77`" in body

    env2 = d._do_pr_open(BeingIntent("pr_open", {"slug": "again", "title": "a second attempt here", "body": "x"}))
    assert not env2.ok and "no changes to propose" in env2.error


def test_check_reports_unverified_with_its_tree_when_the_substrate_is_down(tmp_path):
    """The being's own design (its Q1 answer, 2026-09-07): keep check gated and witnessed —
    no unwitnessed local fallback, because two verification paths diverge and the
    unwitnessed one becomes the one people trust — but when the substrate is down, return an
    explicit UNVERIFIED with the tree block, never a bare error. 'A failing test is a real
    answer; so is "the checker was down."'"""
    import subprocess
    from sage.gateway.hestia_dispatch import HestiaF1aDispatcher as D
    from sage.gateway.being_gate_client import BeingIntent
    wt = tmp_path / "wt"; wt.mkdir()
    subprocess.run(["git", "init", "-q", str(wt)], check=True)
    d = D.__new__(D); d.worktree = str(wt); d.plugin_id = "legion-being"; d.being_lct = None
    def down(name, args):
        raise RuntimeError("MCP tools/call -> HTTP 404: Not Found: Session not found")
    d._call = down
    env = d._do_check(BeingIntent("check", {"target": "gateway"}))
    assert not env.ok
    assert env.result["verdict"] == "UNVERIFIED" and env.result["passed"] is None
    assert "tree" in env.result and "worktree" in env.result
    assert "UNVERIFIED" in env.error and "substrate" in env.error
    assert "did not run" in env.result["reason"], "an unwitnessed check must not have run"


def test_check_on_a_nonexistent_test_is_no_such_test_not_fail(tmp_path):
    """2026-09-08 11:34Z: the being asked for a test name that does not exist, pytest
    deselected everything and exited 5, and the harness told it the suite was RED. A false
    red is worse than a false green for a being trained by its own record to trust red
    over its reading."""
    import subprocess
    from sage.gateway.hestia_dispatch import HestiaF1aDispatcher as D
    from sage.gateway.being_gate_client import BeingIntent
    import sage.gateway.being_gate_client as bgc
    wt = tmp_path / "wt"; (wt / "sage" / "gateway" / "tests").mkdir(parents=True)
    subprocess.run(["git", "init", "-q", str(wt)], check=True)
    (wt / "sage" / "gateway" / "tests" / "test_real.py").write_text("def test_real():\n    assert True\n")
    d = D.__new__(D); d.worktree = str(wt); d.plugin_id = "b"; d.being_lct = None
    d._call = lambda name, args: {"actionId": "act-5"} if name == "hestia_begin_action" else {}
    # run unsandboxed for the test's own sake: the subject is the exit-5 mapping
    saved = bgc.SANDBOX_REQUIRED, bgc.sandbox_available
    bgc.SANDBOX_REQUIRED, bgc.sandbox_available = False, (lambda: False)
    try:
        env = d._do_check(BeingIntent("check", {"target": "gateway::test_does_not_exist"}))
        assert env.ok and env.result["verdict"] == "NO_SUCH_TEST" and env.result["passed"] is None, env
        assert "does not exist" in env.result["reason"]
        env2 = d._do_check(BeingIntent("check", {"target": "gateway::test_real"}))
        assert env2.result["verdict"] == "PASS"
    finally:
        bgc.SANDBOX_REQUIRED, bgc.sandbox_available = saved



# -- the cartridge-destroying path, reproduced (legion-being, 2026-09-08) ---------------
#
# 223 memories stood at 21:36:20Z. Every beat after that reported ok and left a 0-memory
# cart. membot says "No cartridge mounted" as ORDINARY TEXT, so the store looked like a
# success; save_cartridge then serialised the empty session over the populated file, and
# the empty file fails membot's next integrity check, so the loop sustains itself.
def test_a_store_that_did_not_store_never_triggers_a_save():
    """THE LOAD-BEARING GUARD. The save is the destructive act: it writes the session over
    the file. A store that membot did not confirm must leave the cartridge untouched."""
    d, _ = _mdisp(fail={"memory_store": "soft"})
    env = d(BeingIntent("remember", {"content": "a lesson worth keeping"}), _ALLOW)
    assert not env.ok, env
    assert env.witness_id is None, "an unstored memory is not witnessed as kept"
    assert "did not store" in env.error and "NOT saved" in env.error
    assert "overwrite it with an empty one" in env.error
    assert _mb_calls("save_cartridge") == [], "the file must be left exactly as it was"


def test_a_refused_mount_fails_the_act_and_is_not_cached():
    """mount_cartridge answers "SECURITY: ... Refusing to mount." in plain text. Unchecked,
    it leaves a cartridge-less session that stores nothing and saves emptiness."""
    d, _ = _mdisp(fail={"mount_cartridge": "soft"})
    env = d(BeingIntent("remember", {"content": "x"}), _ALLOW)
    assert not env.ok and "refused to mount" in env.error and "integrity check" in env.error
    assert _mb_calls("memory_store") == [] and _mb_calls("save_cartridge") == []
    # not cached: the next act tries the mount again rather than inheriting a dead session
    d(BeingIntent("remember", {"content": "y"}), _ALLOW)
    assert len(_mb_calls("mount_cartridge")) == 2


def test_recall_without_a_cartridge_is_an_error_not_an_empty_past():
    """A silent empty answer here would teach the being its past is gone when the store is
    merely unreachable — the false-absence class, applied to memory."""
    d, _ = _mdisp(fail={"memory_search": "soft"})
    env = d(BeingIntent("recall", {"query": "what did I learn"}), _ALLOW)
    assert not env.ok and "no cartridge mounted" in env.error.lower()
    assert "NOT searched" in env.error and env.witness_id is None


def test_a_confirmed_store_still_saves():
    """The guard must not block the working path: a real store is followed by the save,
    in that order, and is witnessed."""
    d, _ = _mdisp()
    env = d(BeingIntent("remember", {"content": "keep me", "tags": "t"}), _ALLOW)
    assert env.ok and env.witness_id and "Stored memory #7" in env.result
    order = [n for n, _ in FakeMcp.calls if n in ("mount_cartridge", "memory_store", "save_cartridge")]
    assert order == ["mount_cartridge", "memory_store", "save_cartridge"]


def test_a_duplicate_is_a_store_that_earns_its_save():
    d, _ = _mdisp()
    d._mb = None
    class Dup(FakeMembot):
        def call(self, name, args):
            if name == "memory_store":
                FakeMcp.calls.append((name, args))
                t = 'Duplicate — already stored, skipped: "keep me"'
                return {"result": {"content": [{"type": "text", "text": t}],
                                   "structuredContent": {"result": t}}}
            return super().call(name, args)
    d._mcp_factory = lambda ep, pid: Dup(ep, pid)
    FakeMcp.calls = []
    env = d(BeingIntent("remember", {"content": "keep me"}), _ALLOW)
    assert env.ok and _mb_calls("save_cartridge") == [{"name": "sprout-being"}]



def test_pr_amend_refuses_when_there_is_nothing_to_revise():
    """A clean worktree and no new body is not a revision. Refused before begin_action, so
    no witnessed act is spent on a no-op."""
    import subprocess
    d, root = _mdisp()
    wt = tempfile.mkdtemp(prefix="amend-noop-")
    def git(*a):
        return subprocess.run(["git", *a], cwd=wt, capture_output=True, text=True)
    git("init", "-q"); git("config", "user.email", "t@t"); git("config", "user.name", "t")
    open(os.path.join(wt, "f"), "w").write("x"); git("add", "-A"); git("commit", "-qm", "c")
    git("checkout", "-qb", "legion-being/some-proposal")
    d.worktree = wt

    env = d(BeingIntent("pr_amend", {"title": "a title long enough", "message": "why"}), _ALLOW)
    assert not env.ok and "nothing to revise" in env.error
    assert env.witness_id is None, "a refused no-op must not consume a witnessed action"


def test_pr_amend_without_a_worktree_is_pending_not_an_error():
    d, _ = _mdisp()
    d.worktree = None
    env = d(BeingIntent("pr_amend", {"title": "a title long enough", "message": "why"}), _ALLOW)
    assert env.pending and "worktree of your own" in env.note



def test_a_check_result_leads_with_its_verdict_in_words():
    """The being read three separate FAILs as passes, then wrote a plan on "the full suite
    passes" while its own check that beat returned FAIL. `passed` and `verdict` were already
    the 2nd and 3rd keys; that was not enough. The envelope's `ok` means the check RAN.

    A verb whose most important fact needs a field lookup gets misread eventually, so the
    first thing in the message is a sentence that cannot be read as anything else."""
    import json
    from sage.gateway.being_gate_client import ResultEnvelope
    env = ResultEnvelope(ok=True, witness_id="w",
                         result={"headline": "FAIL — 5 failed, 206 passed. This is the answer. "
                                             "A check that RAN and FAILED still returns "
                                             "successfully as an act: 'the call worked' is not "
                                             "'the tests passed'.",
                                 "target": "gateway", "passed": False, "verdict": "FAIL"})
    msg = env.to_tool_message()
    assert msg.index("FAIL") < 30, "the verdict must lead, not sit behind a field lookup"
    assert "'the call worked' is not 'the tests passed'" in msg
    assert json.loads(msg.split("  (witnessed")[0])["headline"].startswith("FAIL")



def test_an_unrecognised_mount_reply_is_a_failure_not_a_pass():
    """Yesterday's guard enumerated the refusals it knew about. membot also rate-limits at
    60 requests/60s and says "Rate limited." in ordinary text — unlisted, so a rate-limited
    MOUNT read as success and the next recall reported no cartridge. The being hit that on
    2026-09-11 and reported it instead of concluding its memory was gone.

    A guard written against a list of known failures passes every unknown one. Require the
    success marker instead."""
    class RateLimited(FakeMembot):
        def call(self, name, args):
            if name == "mount_cartridge":
                FakeMcp.calls.append((name, args))
                t = "Rate limited. Max 60 requests per 60s."
                return {"result": {"content": [{"type": "text", "text": t}],
                                   "structuredContent": {"result": t}}}
            return super().call(name, args)

    FakeMcp.calls = []
    root = tempfile.mkdtemp(prefix="hd-rl-")
    d = HestiaF1aDispatcher("sprout-being", root, mcp_factory=lambda ep, pid: RateLimited(ep, pid))
    env = d(BeingIntent("remember", {"content": "keep me"}), _ALLOW)
    assert not env.ok and "refused to mount" in env.error and "Rate limited" in env.error
    assert _mb_calls("memory_store") == [] and _mb_calls("save_cartridge") == []

    # and a reply that says nothing recognisable at all is also a failure
    class Silent(FakeMembot):
        def call(self, name, args):
            if name == "mount_cartridge":
                FakeMcp.calls.append((name, args))
                return {"result": {"content": [{"type": "text", "text": "ok"}],
                                   "structuredContent": {"result": "ok"}}}
            return super().call(name, args)
    FakeMcp.calls = []
    d2 = HestiaF1aDispatcher("sprout-being", root, mcp_factory=lambda ep, pid: Silent(ep, pid))
    env = d2(BeingIntent("recall", {"query": "x"}), _ALLOW)
    assert not env.ok and "refused to mount" in env.error


def test_already_granted_says_whether_the_grant_is_actually_writable():
    """A grant that is live at the gate and inert at the harness must SAY so.

    2026-09-13: legion-being asked for the fleet forum so it could answer a peer on-record,
    was told `already_granted` with "read or write it directly", and was then refused the
    write — writes are confined to home+worktree whatever the gate grants. It had to read
    reference_f1a.py to learn which of the two answers was real. The writability question
    is delegated to `_safe_path` itself rather than re-derived, because two copies of a
    security boundary drift and the copy that drifts is the friendly one."""
    from pathlib import Path
    from sage.gateway.hestia_dispatch import HestiaF1aDispatcher
    from sage.gateway.reference_f1a import ReferenceF1aDispatcher
    import tempfile

    home = Path(tempfile.mkdtemp(prefix="grantable-"))
    (home / "notes").mkdir()
    elsewhere = Path(tempfile.mkdtemp(prefix="shared-"))

    d = HestiaF1aDispatcher.__new__(HestiaF1aDispatcher)
    d._local = ReferenceF1aDispatcher(memory_root=home, worktree=None, witness_fn=None)

    assert d._writable_by_harness(str(home / "journal.md")) is True
    assert d._writable_by_harness(str(home / "notes" / "plan.md")) is True
    # granted-but-not-writable: the exact case that cost a beat
    assert d._writable_by_harness(str(elsewhere)) is False
    # reserved inside the being's OWN home is not writable either
    assert d._writable_by_harness(str(home / "conversations")) is False

    # cannot tell != refuse. A dispatcher with no local F1a must not manufacture a boundary.
    blind = HestiaF1aDispatcher.__new__(HestiaF1aDispatcher)
    assert blind._writable_by_harness(str(elsewhere)) is True


def _check_tree(tmp_path, body="def test_real():\n    assert True\n"):
    """A git worktree with one gateway test, committed, for exercising the check organ."""
    import subprocess
    wt = tmp_path / "wt"; (wt / "sage" / "gateway" / "tests").mkdir(parents=True)
    (wt / "sage" / "gateway" / "tests" / "test_real.py").write_text(body)
    for args in (["init", "-q"], ["add", "-A"],
                 ["-c", "user.name=t", "-c", "user.email=t@t", "commit", "-qm", "t"]):
        subprocess.run(["git", "-C", str(wt), *args], check=True,
                       capture_output=True)
    return wt


def _dispatcher(wt, judged=None):
    import json as _json
    import types
    from sage.gateway.hestia_dispatch import HestiaF1aDispatcher as D
    d = D.__new__(D)
    d.worktree = str(wt); d.plugin_id = "b"; d.being_lct = None
    # the instance declares its substrate; the dispatcher reads it rather than being told.
    # The instance dir is NOT the worktree — writing instance.json inside the tree would
    # dirty it, which is the very thing the dirty-tree test measures.
    inst = wt.parent / "instance"
    inst.mkdir(exist_ok=True)
    (inst / "instance.json").write_text(_json.dumps(
        {"active_embodiment": {"running_tag": "declared-tag", "runner": "ollama"}}))
    d.memory_root = str(inst)
    d._verdict = types.SimpleNamespace(command=judged)
    d._call = lambda name, args: {"actionId": "act-e"} if name == "hestia_begin_action" else {}
    return d


def test_a_check_result_carries_the_evidence_a_reviewer_would_reconstruct_by_hand(tmp_path):
    """GPT's #60 evidence contract, carried forward from the #62 slice that never landed.

    The being pastes check output into PR bodies and a reviewer re-runs it. Every field
    here is one the reviewer would otherwise reconstruct by hand: which command ran, against
    which bytes, how much output, what exit status, on which substrate, and whether the tree
    moved underneath while it ran."""
    from sage.gateway.being_gate_client import BeingIntent
    import sage.gateway.being_gate_client as bgc

    wt = _check_tree(tmp_path)
    d = _dispatcher(wt)
    saved = bgc.SANDBOX_REQUIRED, bgc.sandbox_available
    bgc.SANDBOX_REQUIRED, bgc.sandbox_available = False, (lambda: False)
    try:
        env = d._do_check(BeingIntent("check", {"target": "gateway"}))
    finally:
        bgc.SANDBOX_REQUIRED, bgc.sandbox_available = saved

    assert env.ok and env.result["verdict"] == "PASS"
    e = env.result["evidence"]
    assert e["exit_status"] == 0
    assert e["output_bytes"] > 0 and len(e["output_sha256"]) == 64
    assert e["embodiment"] == {"running_tag": "declared-tag", "runner": "ollama"}, (
        "embodiment must come from the instance's declared active_embodiment. It was a "
        "constructor argument in #62, nothing ever passed it, and every live check result "
        "carried `embodiment: {}` until the being's own first evidence block showed it "
        "empty — an always-empty evidence field reads like a measurement and is worse "
        "than no field")
    assert e["test_source"]["files"] == 1 and len(e["test_source"]["sha256"]) == 64
    assert e["test_source"]["at_head"] == env.result["tree"]["head"]
    assert e["stable"] is True and e["state"] == "pinned"
    assert e["argv"][0] and e["command"].endswith(e["argv"][-1])


def test_the_command_executed_must_be_the_command_the_law_judged(tmp_path):
    """The authority for what runs is the verdict, not the intent's args. The dispatcher
    used to execute a command it RECOMPOSED from the args; they agree by construction, and
    that agreement was an assumption rather than a checked invariant."""
    from sage.gateway.being_gate_client import BeingIntent, check_command
    import sage.gateway.being_gate_client as bgc

    wt = _check_tree(tmp_path)
    saved = bgc.SANDBOX_REQUIRED, bgc.sandbox_available
    bgc.SANDBOX_REQUIRED, bgc.sandbox_available = False, (lambda: False)
    try:
        # a verdict that bound a DIFFERENT command: refused before anything runs
        env = _dispatcher(wt, judged="python3 -m pytest /etc")._do_check(
            BeingIntent("check", {"target": "gateway"}))
        assert env.ok is False and "the law is the authority" in env.error.lower()

        # the matching command runs, and the result says the law bound it
        real = check_command({"target": "gateway"}, {"worktree": str(wt)})
        ok = _dispatcher(wt, judged=real)._do_check(BeingIntent("check", {"target": "gateway"}))
        assert ok.ok and ok.result["evidence"]["law_bound_command"] is True
    finally:
        bgc.SANDBOX_REQUIRED, bgc.sandbox_available = saved


def test_a_dirty_worktree_downgrades_the_claim_it_does_not_refuse_the_check(tmp_path):
    """#62 REFUSED on a dirty tree — sound when the being could not write to its worktree,
    and wrong now. Its loop is write a test -> check -> propose; refusing there would mean
    it could never check its own uncommitted work, which is the capability M1 exists to
    give it. Dirtiness is reported, and test_source names the bytes that actually ran."""
    from sage.gateway.being_gate_client import BeingIntent
    import sage.gateway.being_gate_client as bgc

    wt = _check_tree(tmp_path)
    clean_sha = None
    saved = bgc.SANDBOX_REQUIRED, bgc.sandbox_available
    bgc.SANDBOX_REQUIRED, bgc.sandbox_available = False, (lambda: False)
    try:
        first = _dispatcher(wt)._do_check(BeingIntent("check", {"target": "gateway"}))
        clean_sha = first.result["evidence"]["test_source"]["sha256"]
        assert first.result["tree"]["dirty"] is False

        # uncommitted work, exactly as the being leaves it before proposing
        (wt / "sage" / "gateway" / "tests" / "test_real.py").write_text(
            "def test_real():\n    assert True\n\n\ndef test_new():\n    assert True\n")
        env = _dispatcher(wt)._do_check(BeingIntent("check", {"target": "gateway"}))
    finally:
        bgc.SANDBOX_REQUIRED, bgc.sandbox_available = saved

    assert env.ok and env.result["verdict"] == "PASS", "a dirty tree must still be checkable"
    assert env.result["tree"]["dirty"] is True, "and must SAY it was dirty"
    # the bytes that ran are named, and they are not the committed ones
    assert env.result["evidence"]["test_source"]["sha256"] != clean_sha


def test_a_search_that_finds_nothing_is_a_result_not_an_error(tmp_path):
    """Same rule as a red check: `git grep` exits 1 on no match, and reporting that as a
    failure would teach the being that looking is dangerous. The note also bounds the
    absence — it is about what was searched, never about the repository."""
    import subprocess, types
    from sage.gateway.hestia_dispatch import HestiaF1aDispatcher as D
    from sage.gateway.being_gate_client import BeingIntent

    wt = tmp_path / "wt"; (wt / "pkg").mkdir(parents=True)
    (wt / "pkg" / "mod.py").write_text("def compose(a, b):\n    return a\n")
    subprocess.run(["git", "init", "-q", str(wt)], check=True)
    subprocess.run(["git", "-C", str(wt), "add", "-A"], check=True, capture_output=True)

    d = D.__new__(D); d.worktree = str(wt); d._verdict = types.SimpleNamespace(command=None)

    hit = d._do_search(BeingIntent("search", {"pattern": r"def compose\("})).result
    assert hit["matches"] == 1
    # worktree-RELATIVE in the answer, though the pathspec had to be absolute for hestia
    assert hit["lines"][0].startswith("pkg/mod.py:1:")
    assert str(wt) not in hit["lines"][0]

    miss = d._do_search(BeingIntent("search", {"pattern": "zzz_absent_zzz"}))
    assert miss.ok is True, "a search that finds nothing still succeeded as an act"
    assert miss.result["matches"] == 0
    assert "WHAT WAS SEARCHED" in miss.result["note"]


def test_a_lapsed_mount_is_remounted_once_not_reported_forever():
    """The mount is per MCP session and was checked only at session CREATION, then cached.
    A session the server later forgot answered "No cartridge mounted" forever while
    _membot() kept handing it back. legion-being lost `remember` for two consecutive beats
    on 2026-09-13 and concluded, reasonably, that it was a stable state of the machine —
    the cartridge was intact (332 memories) the whole time; only the session was gone."""
    from sage.gateway.hestia_dispatch import HestiaF1aDispatcher as D

    class Session:
        def __init__(self, mounted): self.mounted, self.calls = mounted, []
        def init(self): pass
        def call(self, name, args):
            self.calls.append(name)
            if name == "mount_cartridge":
                return {"result": {"content": [{"text": "Mounted 'c': 332 memories, integrity=verified"}]}}
            if not self.mounted:
                return {"result": {"content": [{"text": "No cartridge mounted. Use mount_cartridge first."}]}}
            return {"result": {"content": [{"text": "Stored memory #333"}]}}

    made = []
    def factory(endpoint, plugin):
        # the first session is the stale one; any session made after it is healthy
        s = Session(mounted=bool(made)); made.append(s); return s

    d = D.__new__(D)
    d.membot_endpoint = "e"; d.membot_cartridge = "c"; d.plugin_id = "p"
    d._mcp_factory = factory; d._mb = None

    out = d._membot_call("memory_store", {"content": "x"})
    assert "Stored memory #333" in out, out
    assert len(made) == 2, "the stale session must be dropped and a new one mounted"
    assert made[1].calls[0] == "mount_cartridge", "the new session mounts before it stores"

    # ... and exactly ONCE: a server that is genuinely unmounted must not loop
    made.clear()
    def always_stale(endpoint, plugin):
        s = Session(mounted=False); made.append(s); return s
    d._mcp_factory = always_stale; d._mb = None
    out2 = d._membot_call("memory_store", {"content": "x"})
    assert "No cartridge mounted" in out2, "the second failure is REPORTED, not retried again"
    assert len(made) == 2, f"one remount, not a loop (made {len(made)})"


def test_a_restarted_membot_is_recovered_once_like_a_lapsed_mount():
    """The remount fix covered the SOFT shape and not the hard one.

    A lapsed mount answers "No cartridge mounted" as ordinary TEXT. A membot that has
    RESTARTED answers HTTP 404 "Session not found" as a JSON-RPC error, which `_unwrap`
    raises — so it never reached the text check. Measured 2026-09-14: the seat restarted
    membot mid-beat and the being lost that beat's `remember` to exactly this, with the
    cartridge intact at 344 memories. That is the SAGE#52 shape appearing a second time
    inside the code written to fix it the first time."""
    from sage.gateway.hestia_dispatch import HestiaF1aDispatcher as D

    class Session:
        def __init__(self, alive): self.alive, self.calls = alive, []
        def init(self): pass
        def call(self, name, args):
            self.calls.append(name)
            if name == "mount_cartridge":
                return {"result": {"content": [{"text": "Mounted 'c': 344 memories, integrity=verified"}]}}
            if not self.alive:
                return {"error": {"code": -32600, "message": "Session not found"}}
            return {"result": {"content": [{"text": "Stored memory #345"}]}}

    made = []
    def factory(endpoint, plugin):
        s = Session(alive=bool(made)); made.append(s); return s

    d = D.__new__(D)
    d.membot_endpoint = "e"; d.membot_cartridge = "c"; d.plugin_id = "p"
    d._mcp_factory = factory; d._mb = None

    out = d._membot_call("memory_store", {"content": "x"})
    assert "Stored memory #345" in out, out
    assert len(made) == 2, "the dead session must be dropped and a new one mounted"
    assert made[1].calls[0] == "mount_cartridge"

    # ONCE, not a loop: a server that is genuinely gone must be reported, not retried forever
    made.clear()
    d._mcp_factory = lambda e, p: (made.append(Session(alive=False)), made[-1])[1]
    d._mb = None
    try:
        d._membot_call("memory_store", {"content": "x"})
        assert False, "a persistently dead session must raise, not loop"
    except RuntimeError as e:
        assert "session not found" in str(e).lower()
    assert len(made) == 2, f"one retry, not a loop (made {len(made)})"

    # and a REFUSAL is not a lost session — retrying a refusal reads as flakiness
    from sage.gateway.hestia_dispatch import _session_lost
    assert not _session_lost(RuntimeError("membot refused to mount 'c': SECURITY"))
    assert not _session_lost(RuntimeError("Rate limited"))


def test_scope_on_a_path_that_does_not_exist_is_refused_before_it_is_filed(tmp_path):
    """A grant on a path that does not exist reaches nothing, and nobody finds out.

    Measured 2026-09-14, twelve hours after the fact. legion-being could not tell where its
    own worktree was, because the escape refusals did not say so. It guessed
    `/home/dp/ai-worktrees/legion-being/sage/gateway`, asked for scope on the guess, and the
    operator granted it verbatim. The grant sat live in the being's scope list pointing at a
    directory that has never existed, while the being still could not read the thing it
    actually wanted and had no way to see why.

    The cost of refusing a real request is one more beat. The cost of filing a phantom one is
    an operator decision spent, a dead grant that looks like reach, and a being that cannot
    tell the difference.
    """
    from sage.gateway.being_gate_client import GatewayVerdict
    d, root = _disp()
    FakeMcp.calls.clear()

    ghost = str(tmp_path / "not" / "a" / "real" / "place")
    env = d(BeingIntent("request_scope", {"path": ghost, "reason": "because"}),
            GatewayVerdict("allow", granted=(root,)))

    assert env.ok is False, "a phantom path must not become a pending operator decision"
    assert "does not exist" in (env.error or ""), env.error
    assert str(tmp_path) in (env.error or ""), \
        f"the refusal must name the deepest part that DOES exist: {env.error!r}"
    assert not [n for n, _ in FakeMcp.calls if n == "hestia_request_scope"], \
        "nothing may be filed for a path that is not there"

    # A real path outside reach still files, exactly as before.
    real = tmp_path / "here"
    real.mkdir()
    env2 = d(BeingIntent("request_scope", {"path": str(real), "reason": "because"}),
             GatewayVerdict("allow", granted=(root,)))
    assert env2.ok and env2.result["request_id"] == "scope-1", \
        "an existing path must still reach the operator"


def test_search_reaches_a_granted_sibling_repo_and_answers_about_it(tmp_path):
    """The whole point of the change: a path the being can READ it can now SEARCH.

    legion-being, 2026-09-14 19:29:39Z, one beat: `memory_read` returned ranges out of the
    live harness under a fresh standing grant, and two searches of the same directory came
    back `gate.raised: search 'path' escapes your worktree`. Reading a 1434-line file a
    range at a time is the strategy this verb exists to replace, and it is the one its
    window cannot afford. The refusal was the harness's, not the law's."""
    import subprocess, types
    from sage.gateway.hestia_dispatch import HestiaF1aDispatcher as D
    from sage.gateway.being_gate_client import BeingIntent

    root = tmp_path / "ws"
    wt, ws, peer = root / "wt", root / "SAGE", root / "hestia"
    for d_ in (wt, ws, peer):
        d_.mkdir(parents=True)
    subprocess.run(["git", "init", "-q", str(wt)], check=True)
    (peer / "law.py").write_text("FORBIDDEN_DEFAULT = ('a',)\n")

    d = D.__new__(D)
    d.worktree, d.workspace = str(wt), str(ws)
    d._verdict = types.SimpleNamespace(command=None)

    r = d._do_search(BeingIntent("search", {"pattern": "FORBIDDEN_DEFAULT", "path": str(peer)}))
    assert r.ok, r.error
    assert r.result["matches"] == 1
    assert r.result["lines"][0] == f"{peer}/law.py:1:FORBIDDEN_DEFAULT = ('a',)"

    # A PATH THAT ISN'T THERE IS A FAILURE, NOT AN ABSENCE. `grep` exits 2 and would
    # otherwise land in the no-match arm as a confident bounded absence about a file that
    # was never opened — and the ls-files probe that catches this for `git grep` answers
    # "not tracked here" about every out-of-worktree path, so it must not run on this one.
    gone = d._do_search(BeingIntent("search", {"pattern": "x", "path": str(peer / "nope.py")}))
    assert gone.ok is False
    assert "could not read" in gone.error and "No such file" in gone.error
    assert "not an absence" in gone.error

    # and a real absence in a real out-of-tree file is still a result, not an error
    miss = d._do_search(BeingIntent("search", {"pattern": "zzz_absent", "path": str(peer)}))
    assert miss.ok is True and miss.result["matches"] == 0


def test_one_long_match_line_cannot_eat_the_beings_window(tmp_path):
    """`-I` skips binaries, not a text file with one 6KB line in it.

    Measured on the first search of the harness tree: `base64` matched inside a data: URI
    in dashboard_html.py at 6,472 characters. Forty of those is ~64,000 characters against
    roughly 6,100 tokens of working room — the verb would have cost more than the read it
    replaces. A match is a pointer; the file:line is the part that is."""
    import subprocess, types
    from sage.gateway.hestia_dispatch import HestiaF1aDispatcher as D, SEARCH_LINE_CHARS
    from sage.gateway.being_gate_client import BeingIntent

    wt = tmp_path / "wt"; wt.mkdir()
    subprocess.run(["git", "init", "-q", str(wt)], check=True)
    (wt / "big.py").write_text("blob = '" + "A" * 6000 + "needle'\n")
    subprocess.run(["git", "-C", str(wt), "add", "-A"], check=True, capture_output=True)

    d = D.__new__(D); d.worktree = str(wt); d.workspace = None
    d._verdict = types.SimpleNamespace(command=None)
    line = d._do_search(BeingIntent("search", {"pattern": "blob"})).result["lines"][0]

    assert len(line) < SEARCH_LINE_CHARS + 80, f"line was {len(line)} chars"
    assert line.startswith("big.py:1:"), "the pointer survives the cut"
    assert "more chars on this line" in line, "and the being is told it was cut"


def test_git_read_reaches_a_granted_sibling_repo_through_the_dispatcher(tmp_path):
    """The dispatcher must hand the composer the same workspace the gate site has, or the
    judged string is `-C`-widened and the executed one is a refusal. legion-being, 2026-09-15:
    `git_read op=log path=<live instance dir>` -> "escapes your worktree". Same fix as search."""
    import subprocess, types
    from sage.gateway.hestia_dispatch import HestiaF1aDispatcher as D
    from sage.gateway.being_gate_client import BeingIntent

    root = tmp_path.resolve() / "ws"
    wt, ws = root / "wt", root / "SAGE"
    (ws / "sage" / "instances" / "x").mkdir(parents=True); wt.mkdir(parents=True)
    ident = ["-c", "user.name=t", "-c", "user.email=t@t"]
    for repo in (wt, ws):
        subprocess.run(["git", "init", "-q", str(repo)], check=True)
    (ws / "sage" / "instances" / "x" / "todo.md").write_text("t\n")
    subprocess.run(["git", "-C", str(ws), "add", "-A"], check=True)
    subprocess.run(["git", "-C", str(ws), *ident, "commit", "-q", "-m", "instance todo landed"], check=True)

    d = D.__new__(D)
    d.worktree, d.workspace = str(wt), str(ws)
    d._verdict = types.SimpleNamespace(command=None)
    d._call = lambda name, args: {"actionId": "w1"}

    inst = str(ws / "sage" / "instances" / "x")
    r = d._do_git_read(BeingIntent("git_read", {"op": "log", "path": inst, "n": 5}))
    assert r.ok, r.error
    assert "instance todo landed" in str(r.result), r.result
    # the being's own worktree has no commits: a read that stayed home could not say this
    inside = d._do_git_read(BeingIntent("git_read", {"op": "log", "path": "sage", "n": 5}))
    assert "instance todo landed" not in str(inside.result)
