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
    d, _ = _mdisp()
    env = d(BeingIntent("request_scope", {"path": "/home/dp/notes", "reason": "to read my notes"}), _ALLOW)
    assert env.ok and env.witness_id == "rs-hash", env
    assert env.result["request_id"] == "scope-1" and env.result["status"] == "pending"
    assert env.result["path"] == "/home/dp/notes" and "mode" not in env.result
    (sent,) = [a for n, a in FakeMcp.calls if n == "hestia_request_scope"]
    assert sent["plugin_id"] == "sprout-being" and sent["path"] == "/home/dp/notes"
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
    env = d(BeingIntent("request_scope", {"path": "/x", "reason": "y"}), _ALLOW)
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
    env = d(BeingIntent("request_scope", {"path": root + "/config.json", "reason": "to review my configuration"}),
            GatewayVerdict("allow", granted=(root,)))
    assert env.ok and env.result["status"] == "already_granted" and env.result["within"]
    assert not [n for n, _ in FakeMcp.calls if n == "hestia_request_scope"]
    # outside reach: filed as before
    env = d(BeingIntent("request_scope", {"path": "/srv/elsewhere/x", "reason": "to read a peer's note"}),
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
