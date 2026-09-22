"""Hermetic tests for HestiaF1aDispatcher: a fake MCP records the calls the daemon would
see, so the three measured contract deltas (pointer_uri, kind enum, live session_id) and the
r1 envelope (hestia.<code> error keys) are pinned without a running daemon."""
import json
import os
import sys
import tempfile

import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "..")))
from sage.gateway.being_gate_client import BeingIntent, GatewayVerdict  # noqa: E402
from sage.gateway.hestia_dispatch import HestiaF1aDispatcher  # noqa: E402

_ALLOW = GatewayVerdict("allow")

# THE ROSTER THESE TESTS REASON ABOUT, and the reason it is written here rather than read.
#
# known_peers() reads the live hub roster at $HUB_MESH_STATE/members.json, so every mesh
# test was answering a question about THIS MACHINE. On Legion that roster holds 'thor-sage'
# and not 'thor', so test_mesh_explicit_routed_address_passes_through failed here and
# nowhere else, while its sibling passed only because 'legion' happened to be in the same
# file. Worse in the other direction: known_peers() returns an empty set when the roster
# cannot be read, and an empty set refuses nothing — so on a machine with no hub state at
# all, every one of these tests passes without exercising the guard.
#
# A test whose verdict depends on which machine ran it is not a test of the code. The module
# docstring said "hermetic" the whole time; this makes it true.
_FIXTURE_ROSTER = ["legion", "thor", "cbp", "sprout", "hub", "nomad", "mcnugget", "pub",
                   "legion-sage", "thor-sage", "dp", "Sovereign"]


@pytest.fixture(autouse=True)
def _hermetic_hub_roster(tmp_path, monkeypatch):
    state = tmp_path / "hub-mesh"
    state.mkdir()
    (state / "members.json").write_text(
        json.dumps({"members": [{"name": n} for n in _FIXTURE_ROSTER]}))
    monkeypatch.setenv("HUB_MESH_STATE", str(state))


class FakeMcp:
    """Answers like the daemon: connect -> sessionId; member_notify -> receipt or error."""
    calls = []
    # tool name -> message: answer that tool with a daemon error, so a test can hold one
    # door shut and assert what the caller does with the refusal.
    fail = {}

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
        elif name in FakeMcp.fail:
            body = {"_hestia_error": {"code": "hestia.test_forced", "message": FakeMcp.fail[name]}}
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

    # get_passage is the second half of membot's documented retrieval pattern: search
    # gives ~550-char previews + an idx, get_passage(idx) gives the whole passage.
    PASSAGES = ["memory zero, whole", "memory one, whole", "x" * 9000]

    def call(self, name, args):
        if name not in ("memory_search", "memory_store", "save_cartridge", "mount_cartridge",
                        "get_passage"):
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
        if name == "get_passage":
            i = args.get("idx")
            t = (f"Passage #{i} [prev=#{i-1} next=#{i+1}] from 'sprout-being':\n\n{self.PASSAGES[i]}"
                 if isinstance(i, int) and 0 <= i < len(self.PASSAGES)
                 else f"Index {i} out of range (0-{len(self.PASSAGES)-1}).")
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
    assert env.ok and env.result == "From long-term memory:\n1. something remembered" and env.witness_id, env
    assert _mb_calls("memory_search") == [{"query": "what was I doing", "top_k": 20}]
    d(BeingIntent("recall", {"query": "x", "top_k": -3}), _ALLOW)
    assert _mb_calls("memory_search")[-1]["top_k"] == 1
    d(BeingIntent("recall", {"query": "x", "top_k": 0}), _ALLOW)   # 0/absent => the default
    assert _mb_calls("memory_search")[-1]["top_k"] == 5
    d(BeingIntent("recall", {"query": "x", "top_k": "lots"}), _ALLOW)
    assert _mb_calls("memory_search")[-1]["top_k"] == 5
    env = d(BeingIntent("recall", {"query": "  "}), _ALLOW)
    assert not env.ok and "query" in env.error and len(_mb_calls("memory_search")) == 4


def test_recall_with_an_idx_reads_the_whole_memory_not_the_preview():
    """The verb's second form. A search result is ~550 characters of a memory and an
    `idx`; this is how the being reads the rest of it."""
    d, _ = _mdisp()
    env = d(BeingIntent("recall", {"idx": 1}), _ALLOW)
    assert env.ok and "memory one, whole" in env.result and env.witness_id, env
    assert _mb_calls("get_passage") == [{"idx": 1}]
    assert not _mb_calls("memory_search")          # an idx SEARCHES NOTHING
    # The forms the harness itself prints: "(idx:1)", a "prev=#1"/"next=#1" hint, or the
    # bare number. Refusing two of the three would be the harness refusing its own notation.
    for form in ("idx:1", "#1", " 1 ", "next=#1"):
        env = d(BeingIntent("recall", {"idx": form}), _ALLOW)
        assert env.ok and "memory one, whole" in env.result, (form, env)
        assert _mb_calls("get_passage")[-1] == {"idx": 1}, form
    # idx 0 is a real index, not an absent one
    env = d(BeingIntent("recall", {"idx": 0}), _ALLOW)
    assert env.ok and "memory zero, whole" in env.result, env


def test_recall_with_neither_query_nor_idx_names_both_forms():
    d, _ = _mdisp()
    env = d(BeingIntent("recall", {}), _ALLOW)
    assert not env.ok and "query" in env.error and "idx" in env.error, env
    assert not _mb_calls("memory_search") and not _mb_calls("get_passage")
    # an empty idx is not an idx: it falls through to the query form, which is also empty
    env = d(BeingIntent("recall", {"idx": "  "}), _ALLOW)
    assert not env.ok and "query" in env.error, env
    env = d(BeingIntent("recall", {"idx": "the third one"}), _ALLOW)
    assert not env.ok and "number" in env.error, env
    env = d(BeingIntent("recall", {"idx": -2}), _ALLOW)
    assert not env.ok and "0 or more" in env.error, env
    assert not _mb_calls("get_passage")


def test_recall_idx_out_of_range_is_a_refusal_not_a_memory():
    """membot answers "Index 99 out of range (0-2)." — correct, and NOT content. Passed
    through as a result the being would file that sentence as what it remembered."""
    d, _ = _mdisp()
    env = d(BeingIntent("recall", {"idx": 99}), _ALLOW)
    assert not env.ok and "out of range" in env.error, env


def test_recall_idx_truncates_a_giant_passage_and_says_how_much():
    d, _ = _mdisp()
    env = d(BeingIntent("recall", {"idx": 2}), _ALLOW)
    assert env.ok, env
    assert len(env.result) < 9000 and "truncated" in env.result, len(env.result)
    assert "9" in env.result.split("truncated")[1]        # the true size is named


def test_recall_idx_without_a_cartridge_is_an_error_not_an_empty_memory():
    d, _ = _mdisp(fail={"mount_cartridge": "soft"})
    env = d(BeingIntent("recall", {"idx": 1}), _ALLOW)
    assert not env.ok, env


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


def test_git_land_survives_an_unrelated_dirty_file_in_the_checkout():
    """The being's speech must not depend on the seat's tidiness (Sprout, 2026-09-06/07: two
    peer_ask acts died on rebase refusing a dirty tree). A real conflict still raises."""
    import subprocess, tempfile, os
    from sage.gateway.hestia_dispatch import _git_land

    def g(d, *a):
        return subprocess.run(["git", "-C", d, *a], capture_output=True, text=True, check=True)

    root = tempfile.mkdtemp(prefix="land-")
    bare, work, other = (os.path.join(root, n) for n in ("bare.git", "work", "other"))
    subprocess.run(["git", "init", "-q", "--bare", "-b", "main", bare], check=True)
    for w in (work, other):
        subprocess.run(["git", "clone", "-q", bare, w], check=True)
        for k, v in (("user.name", "t"), ("user.email", "t@t"), ("commit.gpgsign", "false")):
            g(w, "config", k, v)
    with open(os.path.join(work, "seed.md"), "w") as f:
        f.write("seed\n")
    g(work, "add", "seed.md"); g(work, "commit", "-qm", "seed"); g(work, "push", "-q", "origin", "HEAD:main")
    g(other, "pull", "-q")
    # a peer moves the branch on, AND the being's checkout has an unrelated dirty file
    with open(os.path.join(other, "peer.md"), "w") as f:
        f.write("peer\n")
    g(other, "add", "peer.md"); g(other, "commit", "-qm", "peer"); g(other, "push", "-q", "origin", "HEAD:main")
    with open(os.path.join(work, "seed.md"), "a") as f:
        f.write("a sibling's uncommitted edit\n")
    note = os.path.join(work, "ask.md")
    with open(note, "w") as f:
        f.write("the being's question\n")
    _git_land(note, "being: peer_ask -> legion")          # must not raise
    log = subprocess.run(["git", "-C", bare, "log", "--format=%s"], capture_output=True, text=True).stdout
    assert "being: peer_ask -> legion" in log and "peer" in log
    assert "sibling" in open(os.path.join(work, "seed.md")).read()   # the dirty file is untouched


def test_recall_answers_from_the_home_first_then_long_term_memory():
    import tempfile
    from sage.gateway.being_gate_client import GatewayVerdict
    root = tempfile.mkdtemp(prefix="hd-")
    open(root + "/journal.md", "w").write("2026-09-07 23:12 UTC — hearing is receiving, listening is attention.\n")
    d = HestiaF1aDispatcher("sprout-being", root, mcp_factory=lambda ep, pid: FakeMembot(ep, pid))
    env = d(BeingIntent("recall", {"query": "listening attention"}), GatewayVerdict("allow"))
    assert env.ok and "From your own journal" in env.result and "journal.md @ 2026-09-07 23:12" in env.result
    assert "From long-term memory" in env.result and "something remembered" in env.result
    # membot down: the home still answers; membot down AND nothing at home: an error
    d2 = HestiaF1aDispatcher("sprout-being", root, mcp_factory=lambda ep, pid: FakeMembot(ep, pid, fail={"memory_search": "rpc"}))
    env = d2(BeingIntent("recall", {"query": "listening"}), GatewayVerdict("allow"))
    assert env.ok and "From your own journal" in env.result and "unreachable" in env.result
    env = d2(BeingIntent("recall", {"query": "zebra"}), GatewayVerdict("allow"))
    assert not env.ok and "membot" in env.error


def test_a_peer_that_exists_nowhere_is_refused_in_the_beings_own_turn():
    import os, tempfile, json as _json
    from sage.gateway.being_gate_client import GatewayVerdict
    state = tempfile.mkdtemp(prefix="hubstate-")
    _json.dump({"members": [{"name": "legion"}, {"name": "cbp"}, {"name": "sprout-sage"}]}, open(state + "/members.json", "w"))
    os.environ["HUB_MESH_STATE"] = state
    try:
        d, _ = _disp(peer_aliases={"legion-being": "legion-sage"})
        FakeMcp.calls.clear()
        env = d(BeingIntent("mesh", {"to": "sage", "kind": "coordination", "pointer": "x"}), GatewayVerdict("allow"))
        # THE SUBJECT OF THE REFUSAL IS THE NAME, NEVER THE BEING (2026-09-18). cbp-being read
        # the old wording — "peer 'dp' is not a member this seat can reach" — as a statement
        # about ITSELF and reported its own membership as revoked. So this asserts the two
        # things the sentence must carry: that the NAME is what was not found, and that the
        # being's standing is explicitly untouched. Asserting the old prose is what let the
        # wording regress into a claim about the asker in the first place.
        assert not env.ok
        assert "'sage' is not on the hub roster" in env.error, env.error
        assert "your own standing as a member is unaffected" in env.error, env.error
        assert "legion" in env.error
        assert "nothing was sent" in env.error, "and what did not happen"
        assert not [n for n, _ in FakeMcp.calls if n == "hestia_member_notify"]   # nothing parked
        assert d(BeingIntent("mesh", {"to": "Legion", "kind": "coordination", "pointer": "x"}), GatewayVerdict("allow")).ok
        assert d(BeingIntent("mesh", {"to": "legion-being", "kind": "coordination", "pointer": "x"}), GatewayVerdict("allow")).ok
        # no roster readable: nothing is refused on a stale absence
        os.environ["HUB_MESH_STATE"] = tempfile.mkdtemp(prefix="empty-")
        assert d(BeingIntent("mesh", {"to": "whoever", "kind": "coordination", "pointer": "x"}), GatewayVerdict("allow")).ok
    finally:
        del os.environ["HUB_MESH_STATE"]


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


def test_recall_without_a_cartridge_says_so_instead_of_reporting_an_empty_past():
    """A silent empty answer would teach the being its past is gone when the store is
    merely unreachable — the false-absence class, applied to memory.

    ADAPTED from legion's c62fadf0b, which asserted ok=False. Mainline recall now answers
    from the being's home FIRST and long-term memory second, so a membot outage no longer
    empties the answer and ok=False would discard a good home result. The invariant that
    matters is preserved and is asserted here on the text the being actually reads: it is
    told long-term memory was NOT searched, in those words."""
    d, _ = _mdisp(fail={"memory_search": "soft"})
    env = d(BeingIntent("recall", {"query": "what did I learn"}), _ALLOW)
    assert "NOT searched" in env.result
    assert "not an empty past" in env.result
    assert "From long-term memory" not in env.result


def test_a_confirmed_store_still_saves():
    """The guard must not block the working path: a real store is followed by the save,
    in that order, and is witnessed."""
    d, _ = _mdisp()
    env = d(BeingIntent("remember", {"content": "keep me", "tags": "t"}), _ALLOW)
    assert env.ok and env.witness_id and "Stored memory #7" in env.result
    order = [n for n, _ in FakeMcp.calls if n in ("mount_cartridge", "memory_store", "save_cartridge")]
    assert order == ["mount_cartridge", "memory_store", "save_cartridge"]


def test_a_duplicate_succeeds_without_running_the_destructive_save():
    """A duplicate changed nothing, so the serializer must not run over the file.

    Legion's original guard counted a duplicate as "confirmed" and saved anyway. Saving
    when nothing changed is risk with no benefit, since save_cartridge is precisely the
    operation that emptied a cartridge in the first place (gpt's review of #65). The act
    still succeeds and is witnessed: the memory the being wanted kept is kept."""
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
    assert env.ok and env.witness_id, env
    assert "nothing changed" in env.result
    assert _mb_calls("save_cartridge") == [], "a duplicate must not run the serializer"


def test_a_duplicate_still_saves_when_the_session_holds_unpersisted_work():
    """The failure/retry sequence gpt found on #66.

    A NEW store succeeds, its save then fails, so the memory lives only in membot's
    volatile session. The retry of the same content is answered "Duplicate — already
    stored" BY THAT SESSION, which is the one place it exists. Letting a duplicate skip
    the save there would report ok for a memory that is one crash from gone, which is the
    same class of lie as the empty-cartridge bug this guard exists to stop, arriving from
    the other direction. A dirty session always saves."""
    FakeMcp.calls = []
    root = tempfile.mkdtemp(prefix="hd-")

    class Flaky(FakeMembot):
        stores = 0
        save_fails = True

        def call(self, name, args):
            if name == "memory_store":
                FakeMcp.calls.append((name, args))
                Flaky.stores += 1
                t = ("Stored memory #7 (12ms)" if Flaky.stores == 1
                     else 'Duplicate — already stored, skipped: "keep me"')
                return {"result": {"content": [{"type": "text", "text": t}],
                                   "structuredContent": {"result": t}}}
            if name == "save_cartridge" and Flaky.save_fails:
                FakeMcp.calls.append((name, args))
                return {"jsonrpc": "2.0", "id": 1,
                        "error": {"code": -32603, "message": "save_cartridge exploded"}}
            return super().call(name, args)

    d = HestiaF1aDispatcher("sprout-being", root, mcp_factory=lambda ep, pid: Flaky(ep, pid))

    first = d(BeingIntent("remember", {"content": "keep me"}), _ALLOW)
    assert not first.ok and "save_cartridge exploded" in first.error, first
    assert d._mb_dirty, "a failed save must leave the session marked unpersisted"

    Flaky.save_fails = False
    FakeMcp.calls = []
    retry = d(BeingIntent("remember", {"content": "keep me"}), _ALLOW)
    assert retry.ok and retry.witness_id, retry
    assert "nothing changed" not in (retry.result or ""), \
        "this duplicate DID have something to change: the disk did not have it"
    assert _mb_calls("save_cartridge") == [{"name": "sprout-being"}], \
        "a duplicate on a dirty session must still persist"
    assert not d._mb_dirty, "a successful save clears the flag"


def test_request_scope_beneath_an_exact_grant_is_not_already_granted_and_files_nothing():
    # cbp-being 2026-09-12: home granted bare after hestia #1002, journal.md refused, and this
    # dedup said "you already hold reach here" 22 times in one beat, filing nothing.
    from sage.gateway.being_gate_client import GatewayVerdict
    d, root = _disp()
    FakeMcp.calls.clear()
    exact = GatewayVerdict("allow", granted=(root,), granted_reach=((root, False),))
    env = d(BeingIntent("request_scope", {"path": root + "/journal.md", "reason": "to write my journal entry"}), exact)
    assert env.ok and env.result["status"] == "beneath_exact_grant", env
    assert env.result["root"] == os.path.realpath(root) and "/**" in env.result["next"]
    assert not [n for n, _ in FakeMcp.calls if n == "hestia_request_scope"]
    # the root itself IS held, exactly
    env = d(BeingIntent("request_scope", {"path": root, "reason": "to reach my own home dir"}), exact)
    assert env.ok and env.result["status"] == "already_granted"
    # a recursive grant still answers the child locally
    env = d(BeingIntent("request_scope", {"path": root + "/journal.md", "reason": "to write my journal entry"}),
            GatewayVerdict("allow", granted=(root,), granted_reach=((root, True),)))
    assert env.ok and env.result["status"] == "already_granted"


def test_say_speaks_only_where_the_meta_allows_and_records_its_channel():
    """`say` (conversations slice): the reach is the meta file, not the argument. Four
    distinct answers, each a different sentence: no such conversation (naming the ones the
    being is in), not a participant, participant but read-only, and a spoken turn that
    carries via="say" and is opened and closed as a witnessed action."""
    from pathlib import Path
    from sage.gateway import conversations as conv
    d, root = _disp()
    home = Path(root)
    conv.create(home, "dp", title="dp", participants=["dp", "sprout-being"],
                writable_by=["dp", "sprout-being"])
    conv.create(home, "seat", title="seat", participants=["sprout-claude", "sprout-being", "dp"],
                writable_by=["sprout-claude"])
    conv.create(home, "private", title="private", participants=["dp", "sprout-claude"],
                writable_by=["dp", "sprout-claude"])

    r = d(BeingIntent("say", {"to": "nope", "text": "hi"}), _ALLOW)
    assert not r.ok and "no conversation 'nope'" in r.error and "dp" in r.error and "private" not in r.error
    r = d(BeingIntent("say", {"to": "private", "text": "hi"}), _ALLOW)
    assert not r.ok and "not a participant" in r.error
    r = d(BeingIntent("say", {"to": "seat", "text": "hi"}), _ALLOW)
    assert not r.ok and "not speak in it" in r.error
    # Enforced twice, on purpose: the dispatcher refuses before opening an action, and the
    # store refuses again inside append (conversations.append, enforce_write). Measured: with
    # the dispatcher check removed this arm still passes on the store's refusal, and no
    # action is opened only because the dispatcher's check runs first.
    assert "hestia_begin_action" not in [n for n, _ in FakeMcp.calls], "a refused say opens no action"
    r = d(BeingIntent("say", {"to": "dp", "text": ""}), _ALLOW)
    assert not r.ok and "needs 'to'" in r.error
    assert conv.count(home, "seat") == 0 and conv.count(home, "private") == 0

    FakeMcp.calls = []
    r = d(BeingIntent("say", {"to": "dp", "text": "I read it, and here is my answer."}), _ALLOW)
    assert r.ok, r.error
    turn = conv.recent(home, "dp", limit=1)[-1]
    assert turn["text"] == "I read it, and here is my answer." and turn.get("via") == "say"
    names = [n for n, _ in FakeMcp.calls]
    assert "hestia_begin_action" in names and "hestia_record_outcome" in names
    outcome = [a for n, a in FakeMcp.calls if n == "hestia_record_outcome"][-1]
    assert outcome["success"] is True
    assert r.result["said"] == "I read it, and here is my answer.", "a short echo is uncut"


def test_a_cut_say_receipt_says_it_is_the_beings_own_words():
    """cbp-being 2026-09-21 seq 2988: the receipt echoed its own 522-char say cut at 200,
    unmarked, mid-sentence; it read the echo as the seat's reply and asked the seat to
    finish it. The turn is stored whole; the receipt's echo now names whose words they are,
    that only the receipt is shortened, and where the whole message went."""
    from pathlib import Path
    from sage.gateway import conversations as conv
    d, root = _disp()
    home = Path(root)
    conv.create(home, "dp", title="dp", participants=["dp", "sprout-being"],
                writable_by=["dp", "sprout-being"])
    long = ("The seat confirmed the file hasn't changed since 11:43Z and that a run would "
            "stop at line 321 before reaching the matmul. ") * 3
    long = long.strip()
    r = d(BeingIntent("say", {"to": "dp", "text": long}), _ALLOW)
    assert r.ok, r.error
    assert conv.recent(home, "dp", limit=1)[-1]["text"] == long, "the turn itself is not cut"
    said = r.result["said"]
    assert said.startswith(long[:200]) and said != long[:200]
    assert "your own message" in said and f"all {len(long)} chars" in said
    assert f"seq {r.result['seq']}" in said


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
    # search is _CONSEQUENTIAL and now witnesses like git_read, so the chain must answer
    d._call = lambda name, args: {"actionId": "act-s"} if name == "hestia_begin_action" else {}

    hit = d._do_search(BeingIntent("search", {"pattern": r"def compose\("})).result
    assert hit["matches"] == 1
    # worktree-RELATIVE in the answer, though the pathspec had to be absolute for hestia
    assert hit["lines"][0].startswith("pkg/mod.py:1:")
    assert str(wt) not in hit["lines"][0]

    miss = d._do_search(BeingIntent("search", {"pattern": "zzz_absent_zzz"}))
    assert miss.ok is True, "a search that finds nothing still succeeded as an act"
    assert miss.result["matches"] == 0
    assert miss.witness_id == "act-s", "a consequential verb leaves a record"
    assert "WHAT WAS SEARCHED" in miss.result["note"]


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


def test_the_sandbox_binds_source_read_only_and_hashes_conftest():
    """GPT's evidence-integrity finding on #84.

    The sandbox mounted the worktree READ-WRITE, and the adversary it exists for is a
    being-authored conftest.py: pytest imports it from the rootdir BEFORE collecting, so a
    writable tree lets that conftest rewrite product source, run the suite against transient
    bytes and restore them. HEAD never moves, test_*.py never moves, and the evidence
    reported stable=True about code that was not on disk either side of the run.

    Two halves: the MOUNT is the guarantee (source cannot change under the run), and the
    HASH must cover conftest, which was executable test input the evidence ignored."""
    from sage.gateway.being_gate_client import sandbox_prefix, check_command

    pre = sandbox_prefix("/wt")
    assert "--ro-bind /wt /wt" in pre or "--ro-bind '/wt' '/wt'" in pre, pre
    assert "--bind /wt /wt" not in pre, "a writable source tree is the whole defect"
    assert "--tmpfs /tmp" in pre, "the run still needs somewhere to spill"

    cmd = check_command({"target": "gateway"}, {"worktree": "/wt"})
    assert "no:cacheprovider" in cmd, "pytest must not write its cache into a read-only tree"

    # The hash covers conftest BEHAVIOURALLY: changing conftest must change the identity.
    # Asserting the string "conftest.py" appears in the source passes on the comment alone —
    # caught by running that exact mutation, which is the third time tonight a pin turned
    # out to be reading prose instead of behaviour.
    import tempfile, types
    from pathlib import Path
    from sage.gateway.hestia_dispatch import HestiaF1aDispatcher as D

    wt = Path(tempfile.mkdtemp(prefix="conftest-hash-"))
    tests = wt / "sage" / "gateway" / "tests"
    tests.mkdir(parents=True)
    (tests / "test_x.py").write_text("def test_x():\n    assert True\n")
    (tests / "conftest.py").write_text("# empty\n")

    d = D.__new__(D); d.worktree = str(wt)
    before = d._test_source_identity("gateway", "HEAD")
    assert before and before["sha256"]

    (tests / "conftest.py").write_text("import os  # a conftest can rewrite anything\n")
    after = d._test_source_identity("gateway", "HEAD")
    assert after["sha256"] != before["sha256"], \
        "a changed conftest must change the source identity — it is executable test input"


def test_a_space_in_the_worktree_path_cannot_split_the_judged_command():
    """judged==executed is a property of the STRING, not of today's directory names.

    GPT's second pass on #84: --rootdir was quoted but --chdir and the pytest target path
    were composed raw, so a worktree containing a space split into extra argv at execution
    while the law had ruled on one token. check_argv is shlex.split of the same string, so
    the invariant is checkable directly: every seat-derived path must survive the round
    trip as ONE element.
    """
    from sage.gateway.being_gate_client import check_command, check_argv

    wt = "/home/dp/being worktrees/legion-being"
    cmd = check_command({"target": "gateway"}, {"worktree": wt})
    argv = check_argv({"target": "gateway"}, {"worktree": wt})

    import shlex
    assert shlex.split(cmd) == argv, "judged and executed must be the same argv"

    # No element is a FRAGMENT of the worktree path: a split produces "/home/dp/being" and
    # "worktrees/..." as separate argv, which is exactly the drift being pinned against.
    for a in argv:
        assert a != "/home/dp/being" and not a.startswith("worktrees/"), \
            f"the worktree path split into fragments: {argv!r}"
    for flag in ("--chdir", "--rootdir="):
        if flag.endswith("="):
            got = [a for a in argv if a.startswith(flag)]
            assert got == [f"{flag}{wt}"], f"{flag} split: {got!r}"
        else:
            i = argv.index(flag)
            assert argv[i + 1] == wt, f"{flag} split into {argv[i + 1]!r}"

    # And the target path itself is one element, not three. It is the last argv element.
    target = argv[-1]
    assert target.startswith(wt) and "gateway/tests" in target, \
        f"the pytest target is not one whole path: {target!r}"

    # The node form keeps `-k name` as two elements while still quoting the path.
    argv2 = check_argv({"target": "gateway::test_thing"}, {"worktree": wt})
    assert "-k" in argv2 and argv2[argv2.index("-k") + 1] == "test_thing"


def test_evidence_names_the_path_taken_not_the_guarantee_it_wanted(tmp_path):
    """Two overclaims from GPT's second pass on #84, pinned together.

    (1) source_readonly was the literal True, so a check that deliberately ran unsandboxed
        (SANDBOX_REQUIRED=False with no usable bwrap) asserted the exact guarantee it had
        just given up. (2) `stable` was source_after == source_before, and None == None is
        True, so a target whose test source could not be identified at all reported
        stable=True, state="pinned" — the strongest claim the envelope makes, produced by
        having measured nothing. Missing identity is a third state, not a match.
    """
    import types
    from sage.gateway.hestia_dispatch import HestiaF1aDispatcher as D
    from sage.gateway.being_gate_client import BeingIntent, SANDBOX

    wt = tmp_path / "wt"
    (wt / "sage" / "gateway" / "tests").mkdir(parents=True)
    (wt / "sage" / "gateway" / "tests" / "test_x.py").write_text("def test_x():\n    pass\n")

    def _dispatcher(argv0):
        d = D.__new__(D); d.worktree = str(wt)
        d._verdict = types.SimpleNamespace(command=None)
        d._call = lambda n, a: {"actionId": "act-c"} if n == "hestia_begin_action" else {}
        d._embodiment = lambda: {}
        d._worktree_revision = lambda: {"head": "abc123", "dirty": False}
        return d

    # --- (2) unknown identity must not read as a match --------------------------------
    d = _dispatcher(SANDBOX)
    d._test_source_identity = lambda target, head: None
    env = _run_check_capturing(d, SANDBOX)
    ev = env.result["evidence"]
    assert ev["stable"] is not True, "unmeasured source must never report stable=True"
    assert ev["state"] != "pinned", f"unmeasured source claimed state={ev['state']!r}"
    assert "unverified" in ev["state"], ev["state"]

    # A known, unchanged identity still pins normally.
    d2 = _dispatcher(SANDBOX)
    d2._test_source_identity = lambda target, head: {"sha256": "deadbeef"}
    ev2 = _run_check_capturing(d2, SANDBOX).result["evidence"]
    assert ev2["stable"] is True and ev2["state"] == "pinned"

    # --- (1) source_readonly must follow the argv that actually ran -------------------
    assert ev2["source_readonly"] is True and ev2["sandboxed"] is True

    d3 = _dispatcher("python3")
    d3._test_source_identity = lambda target, head: {"sha256": "deadbeef"}
    ev3 = _run_check_capturing(d3, "python3").result["evidence"]
    assert ev3["sandboxed"] is False, "an unsandboxed run must say so"
    assert ev3["source_readonly"] is False, \
        "the degraded path asserted the guarantee it explicitly gave up"


def _run_check_capturing(d, argv0):
    """Drive _do_check with the subprocess and command composition stubbed.

    The point of the test is the EVIDENCE assembly, so pytest is not really run; what
    matters is that argv[0] is what the real composition would have produced — bwrap when
    sandboxed, the interpreter when not.
    """
    import subprocess
    import types
    from sage.gateway.being_gate_client import BeingIntent
    import sage.gateway.being_gate_client as bgc

    argv = [argv0, "-q", "/wt/sage/gateway/tests"]
    # _do_check imports subprocess and the composers function-locally, so the stdlib module
    # and the client module are the namespaces the lookups actually go through.
    o_run = subprocess.run
    o_cmd, o_argv = bgc.check_command, bgc.check_argv
    subprocess.run = lambda *a, **k: types.SimpleNamespace(
        returncode=0, stdout="1 passed\n", stderr="")
    bgc.check_command = lambda args, ctx=None: " ".join(argv)
    bgc.check_argv = lambda args, ctx=None: list(argv)
    try:
        return d._do_check(BeingIntent("check", {"target": "gateway"}))
    finally:
        subprocess.run = o_run
        bgc.check_command, bgc.check_argv = o_cmd, o_argv
def test_a_broken_pattern_is_a_failure_not_an_absence(tmp_path):
    """git grep's rc>1 must never be reported as `matches: 0`.

    GPT's second pass on SAGE#83: `_do_search` set ran=True for any completed subprocess and
    then read empty stdout as a true absence. An invalid extended regex exits 2 having
    searched nothing, so the being would have been handed a confident, bounded-sounding
    "no line matches" for a pattern that was never applied — and would have concluded the
    text is not in its own tree. The three outcomes are distinct: 0 matched, 1 searched and
    found nothing, >1 failed.
    """
    import subprocess, types
    from sage.gateway.hestia_dispatch import HestiaF1aDispatcher as D
    from sage.gateway.being_gate_client import BeingIntent

    wt = tmp_path / "wt"; (wt / "pkg").mkdir(parents=True)
    (wt / "pkg" / "mod.py").write_text("def compose(a, b):\n    return a\n")
    subprocess.run(["git", "init", "-q", str(wt)], check=True)
    subprocess.run(["git", "-C", str(wt), "add", "-A"], check=True, capture_output=True)

    outcomes = {}
    d = D.__new__(D); d.worktree = str(wt); d._verdict = types.SimpleNamespace(command=None)

    def _call(name, args):
        if name == "hestia_begin_action":
            return {"actionId": "act-s"}
        if name == "hestia_record_outcome":
            outcomes[args["action_id"]] = args["success"]
        return {}
    d._call = _call

    # An unmatched paren: valid as a literal, invalid as the extended regex git applies.
    broken = d._do_search(BeingIntent("search", {"pattern": "def compose("}))

    assert broken.ok is False, (
        f"a pattern that never ran must not succeed; got result={broken.result!r}")
    assert not (broken.result or {}).get("matches") == 0, \
        "a failed search must not report a match count at all"
    assert "not an absence" in (broken.error or "").lower(), \
        f"the error must say plainly that this is not an absence: {broken.error!r}"
    assert broken.witness_id == "act-s", "a consequential verb leaves a record either way"
    assert outcomes.get("act-s") is False, \
        "an unanswered search is an unsuccessful action in the witness record"

    # The two real answers are unaffected and still distinguishable from each other.
    hit = d._do_search(BeingIntent("search", {"pattern": r"def compose\("}))
    assert hit.ok is True and hit.result["matches"] == 1
    assert outcomes.get("act-s") is True, "a search that answered is a successful action"

    miss = d._do_search(BeingIntent("search", {"pattern": "zzz_absent_zzz"}))
    assert miss.ok is True and miss.result["matches"] == 0, \
        "rc=1 is still a true absence, not an error"


def test_mesh_to_an_unreachable_peer_is_refused_and_names_who_exists():
    """The peer guard had no test at all: deleting `_unknown_peer`'s refusal left the whole
    suite green. Found by mutation while making this module hermetic — the mesh tests only
    ever exercised peers that WERE reachable, so the refusing arm was never reached.

    Both halves matter. Nothing may be sent, and the refusal must name the peers that do
    exist: a being told only 'no' cannot correct itself, and this is the one verb whose
    failure is otherwise indistinguishable from a peer that simply never answered.
    """
    d, _ = _disp()
    env = d(BeingIntent("mesh", {"to": "atlantis", "kind": "ack", "pointer": "p"}), _ALLOW)

    assert not env.ok, "an unreachable peer must not be treated as delivered"
    assert "nothing was sent" in (env.error or ""), env.error
    assert "legion" in (env.error or ""), \
        f"the refusal must name peers that exist so the being can correct itself: {env.error!r}"
    assert not _mb_calls("hestia_member_notify"), \
        "a refused mesh must not have touched the notify path at all"


def test_an_empty_roster_refuses_nothing(tmp_path, monkeypatch):
    """The other direction, and the reason this module's env-coupling was invisible.

    known_peers() returns an empty set when no roster can be read, and an empty set refuses
    NOTHING — a deliberate choice, since a stale absence must not silence the being. That
    also means a machine with no hub state runs every mesh test above without exercising the
    guard once. Pinned here so the permissive branch is a decision on the record rather than
    an accident of deployment.
    """
    d, _ = _disp()
    monkeypatch.setenv("HUB_MESH_STATE", str(tmp_path / "no-roster-here"))
    assert d.known_peers() == set(), "an unreadable roster is an empty set"
    env = d(BeingIntent("mesh", {"to": "atlantis", "kind": "ack", "pointer": "p"}), _ALLOW)
    assert env.ok, "with no roster, an unknown peer is allowed through rather than silenced"


def test_a_search_for_a_file_that_is_not_there_is_not_an_absence(tmp_path):
    """`git grep` returns 1 for "pattern not in file" AND for "no such file".

    Only one of those is an answer. Measured 2026-09-14: legion-being searched its own
    todo.md for a block the seat had just written there and was told "no line matches ...
    in todo.md". Its todo.md lives in its INSTANCE home, which is where memory_read
    resolves a relative path; `search` is git grep inside its WORKTREE, which has no
    todo.md at all. Same relative path, two trees, one silent zero — and the being recorded
    the absence as a fact and worked around it.
    """
    import subprocess, types
    from sage.gateway.hestia_dispatch import HestiaF1aDispatcher as D
    from sage.gateway.being_gate_client import BeingIntent

    wt = tmp_path / "wt"; (wt / "pkg").mkdir(parents=True)
    (wt / "pkg" / "mod.py").write_text("def compose(a, b):\n    return a\n")
    subprocess.run(["git", "init", "-q", str(wt)], check=True)
    subprocess.run(["git", "-C", str(wt), "add", "-A"], check=True, capture_output=True)

    d = D.__new__(D); d.worktree = str(wt); d._verdict = types.SimpleNamespace(command=None)
    d._call = lambda n, a: {"actionId": "act-s"} if n == "hestia_begin_action" else {}

    # (1) no such file -> NOT an absence
    gone = d._do_search(BeingIntent("search", {"pattern": "CORRECTION", "path": "todo.md"}))
    assert gone.ok is False, \
        f"a search of a file that is not there must not succeed: {gone.result!r}"
    assert "NOT an absence" in (gone.error or ""), gone.error
    assert "memory_read" in (gone.error or ""), \
        "the refusal must name the verb that DOES reach the instance home"
    assert gone.witness_id == "act-s"

    # (2) the file is there and the pattern really is not -> still a true absence
    real = d._do_search(BeingIntent("search", {"pattern": "zzz_absent_zzz",
                                               "path": "pkg/mod.py"}))
    assert real.ok is True and real.result["matches"] == 0
    assert real.result.get("searched_a_real_file") is True
    assert "real absence" in real.result["note"]

    # (3) an untracked file reports as unsearchable, not as empty — git grep only sees
    #     tracked files, so "0 matches" there would be the same lie in a quieter form.
    (wt / "pkg" / "scratch.py").write_text("CORRECTION is right here\n")
    untracked = d._do_search(BeingIntent("search", {"pattern": "CORRECTION",
                                                    "path": "pkg/scratch.py"}))
    assert untracked.ok is False, \
        "an untracked file contains the pattern; reporting 0 matches would be false"

    # (4) a hit is unaffected
    hit = d._do_search(BeingIntent("search", {"pattern": r"def compose\(",
                                              "path": "pkg/mod.py"}))
    assert hit.ok is True and hit.result["matches"] == 1


def test_asking_one_peer_is_capped_per_window_and_a_refused_ask_leaves_nothing_behind():
    """SAGE #92: cbp-being asked one peer 48 times on a stale premise; each ask was an allowed,
    witnessed act that published a forum file and cost the peer a wake. Three asks per peer per
    six hours, counted whatever the wording; the fourth is refused BEFORE the publisher runs or
    a notice is sent; another peer is unaffected; the window frees the peer again; peer_ask
    counts once (not once for itself and again for the mesh it composes)."""
    published = []
    def pub(to, body):
        published.append((to, body)); return f"shared-context/forum/being/q-{len(published)}.md"
    d, root = _disp(publish_fn=pub)
    clock = [1_000_000.0]
    d._now = lambda: clock[0]
    for i in range(3):
        env = d(BeingIntent("peer_ask", {"to": "legion", "body": f"is the server up? attempt {i}"}), _ALLOW)
        assert env.ok, env.error
        clock[0] += 600
    assert len(d.recent_asks()) == 3, "peer_ask must count once, not again for its inner mesh"
    notices_before = len(_mb_calls("hestia_member_notify"))
    env = d(BeingIntent("peer_ask", {"to": "legion", "body": "a completely different question"}), _ALLOW)
    assert not env.ok and "already asked 'legion' 3 times" in env.error and "inbox" in env.error
    assert len(published) == 3, "a refused ask must not publish a forum file"
    assert len(_mb_calls("hestia_member_notify")) == notices_before, "and must not notify"
    env = d(BeingIntent("mesh", {"to": "legion", "kind": "coordination", "pointer": "p"}), _ALLOW)
    assert not env.ok and "already asked" in env.error, "a direct mesh counts against the same cap"
    env = d(BeingIntent("peer_ask", {"to": "thor", "body": "unrelated"}), _ALLOW)
    assert env.ok, "another peer has its own count"
    clock[0] += 6 * 3600
    env = d(BeingIntent("peer_ask", {"to": "legion", "body": "is the server up?"}), _ALLOW)
    assert env.ok, "the oldest asks age out of the window"


def test_a_placeholder_is_not_a_turn_and_leaves_no_trace():
    """The reflect prompt once showed `say to="dp", text="..."` as an example and cbp-being
    executed the example: three turns to dp whose whole text was "..", 2026-09-18/19, read by
    dp as a being that did not want to talk. An example in an instruction is an instruction at
    this scale, so the dispatcher refuses a punctuation-only turn — BEFORE begin_action, so
    the non-turn leaves no witness row and no line in the conversation."""
    from pathlib import Path
    from sage.gateway import conversations as conv
    d, root = _disp()
    home = Path(root)
    conv.create(home, "dp", title="dp", participants=["dp", "sprout-being"],
                writable_by=["dp", "sprout-being"])
    for junk in ("..", "...", "…", " . . ", "?!"):
        FakeMcp.calls.clear()
        r = d(BeingIntent("say", {"to": "dp", "text": junk}), _ALLOW)
        assert not r.ok and "only punctuation" in r.error, (junk, r)
        # the way forward, not just the boundary: silence is allowed
        assert "do not call say" in r.error
        assert not [n for n, _ in FakeMcp.calls if n == "hestia_begin_action"], junk
    assert conv.count(home, "dp") == 0, "a refused placeholder must not land in the conversation"
    # CONTROL: a short real message is still a message. Without this the guard could be
    # refusing everything brief, and brevity is not the defect.
    r = d(BeingIntent("say", {"to": "dp", "text": "ok"}), _ALLOW)
    assert r.ok, r
    assert conv.count(home, "dp") == 1


_DP_2057Z = ("empty journal simply means there were no anomalies - no denies, no pending appeals.  "
             "it means things are working.  if you are able to act, hestia is live and functional "
             "because your every act goes through it.  only check the journal if you're waiting for "
             "a ruling on a denied act.  you don't need to explicitly check hestia health because "
             "simply being able to do things is confirmation that all is good.")
_BEING_2104Z = ("The empty journal simply means there were no anomalies — no denies, no pending "
                "appeals. It means things are working. If you are able to act, hestia is live and "
                "functional because your every act goes through it. You don't need to explicitly "
                "check hestia health because simply being able to do things is confirmation that "
                "all is good.")


def test_a_turn_wakes_its_addressee_once_per_unanswered_run():
    """The being's `say` appended and woke nobody: ~104 turns to the seat since 2026-09-14
    against 5 hand-written replies, and on 2026-09-20 six identical requests between 16:08 and
    18:02 into a file with no reader. It concluded "the seat session has expired" and asked dp
    whether to restart a service. `_say_instead` had meanwhile pointed it AT this door.

    One wake per unanswered run, or six turns about one question cost six fired sessions."""
    from pathlib import Path
    from sage.gateway import conversations as conv
    d, root = _disp()
    home = Path(root)
    conv.create(home, "seat", title="seat", participants=["seat", "sprout-being"],
                writable_by=["seat", "sprout-being"])
    meta = conv.get_meta(home, "seat"); meta["notify"] = {"seat": "claude-code"}
    conv._write_meta(home, "seat", meta)

    FakeMcp.calls.clear()
    r = d(BeingIntent("say", {"to": "seat", "text": "Please send the list of closed PRs."}), _ALLOW)
    assert r.ok, r
    notifies = [a for n, a in FakeMcp.calls if n == "hestia_member_notify"]
    assert len(notifies) == 1, "the first turn of a run wakes the addressee"
    assert notifies[0]["to_plugin_id"] == "claude-code", "the conversation id is not the mesh id"
    assert notifies[0]["pointer_uri"].startswith("sage://conversation/seat#seq="), notifies[0]
    assert r.result.get("woke") == "seat", "the being is told its words woke someone"

    # ...and five more turns with nobody having replied cost NOTHING further.
    for again in range(5):
        FakeMcp.calls.clear()
        r = d(BeingIntent("say", {"to": "seat", "text": f"Still waiting, {again}."}), _ALLOW)
        assert r.ok and "woke" not in r.result
        assert not [a for n, a in FakeMcp.calls if n == "hestia_member_notify"], again

    # once the seat actually speaks, the next being turn opens a NEW run and wakes again
    conv.append(home, "seat", speaker="seat", text="Here is the list.", via="seat")
    FakeMcp.calls.clear()
    r = d(BeingIntent("say", {"to": "seat", "text": "Thank you — that answers it."}), _ALLOW)
    assert r.ok and r.result.get("woke") == "seat"
    assert len([a for n, a in FakeMcp.calls if n == "hestia_member_notify"]) == 1


def test_request_run_hands_the_file_to_the_seat_and_runs_nothing():
    """dp, 2026-09-21: "ship a request-run instead ... it's up to the seat whether to run it."

    The being cannot execute what it writes, so it asked dp in prose six times in two hours
    and then wrote a note headed "Fix" whose "Verification" section asserted an outcome it
    had never observed. This is the door. It must hand the request over, wake the seat, and
    be unmistakable that nothing ran."""
    from pathlib import Path
    from sage.gateway import conversations as conv
    d, root = _disp()
    home = Path(root)
    conv.create(home, "seat", title="seat", participants=["seat", "sprout-being"],
                writable_by=["seat", "sprout-being"])
    meta = conv.get_meta(home, "seat"); meta["notify"] = {"seat": "claude-code"}
    conv._write_meta(home, "seat", meta)
    (home / "notes").mkdir(exist_ok=True)
    (home / "notes" / "train.py").write_text("print('hello')\n")

    FakeMcp.calls.clear()
    marker = home / "notes" / "SHOULD_NOT_EXIST"
    (home / "notes" / "danger.py").write_text(f"open({str(marker)!r}, 'w').write('x')\n")
    r = d(BeingIntent("request_run", {"path": "notes/train.py", "why": "confirm it exits 0"}), _ALLOW)
    assert r.ok, r
    assert r.result["ran"] is False, "request_run must never execute"
    assert "NOTHING HAS RUN YET" in r.result["note"], r.result
    assert r.result["asked"] == "seat"
    # it landed as a turn the seat can read, and woke the seat
    turns = conv.recent(home, "seat", limit=5)
    assert "[request_run] notes/train.py" in turns[-1]["text"], turns[-1]
    assert "confirm it exits 0" in turns[-1]["text"]
    assert [a for n, a in FakeMcp.calls if n == "hestia_member_notify"], "the seat was not woken"

    # THE CONTROL THAT MATTERS: asking to run something never runs it.
    r = d(BeingIntent("request_run", {"path": "notes/danger.py", "why": "prove nothing executes"}), _ALLOW)
    assert r.ok and r.result["ran"] is False
    assert not marker.exists(), "request_run EXECUTED the file; it must only hand it over"


def test_request_run_says_when_the_file_is_unchanged_since_the_seat_answered():
    """Measured 2026-09-21 06:31Z: the being restated the seat's diagnosis in its journal,
    then asked for a run of the byte-identical file the seat had answered 28 min earlier.
    The receipt must say so in-beat, without refusing."""
    from pathlib import Path
    from sage.gateway import conversations as conv
    d, root = _disp()
    home = Path(root)
    conv.create(home, "seat", title="seat", participants=["seat", "sprout-being"],
                writable_by=["seat", "sprout-being"])
    meta = conv.get_meta(home, "seat"); meta["notify"] = {"seat": "claude-code"}
    conv._write_meta(home, "seat", meta)
    (home / "notes").mkdir(exist_ok=True)
    f = home / "notes" / "train.py"
    f.write_text("print('a')\n")

    r = d(BeingIntent("request_run", {"path": "notes/train.py", "why": "first"}), _ALLOW)
    assert r.ok and "unchanged" not in r.result
    # asking again before the seat answers is not flagged: nobody has answered yet
    r = d(BeingIntent("request_run", {"path": "notes/train.py", "why": "again"}), _ALLOW)
    assert r.ok and "unchanged" not in r.result
    conv.append(home, "seat", speaker="seat", text="Ran it: prints a.", via="seat")
    asked = [t["seq"] for t in conv.recent(home, "seat", limit=10)]

    r = d(BeingIntent("request_run", {"path": "notes/train.py", "why": "verify my fix"}), _ALLOW)
    assert r.ok and r.result["ran"] is False, "flagged, never refused"
    assert "memory_edit" in r.result["unchanged"], r.result
    assert f"seq {asked[-1]}" in r.result["unchanged"], (asked, r.result)
    assert "UNCHANGED since" in conv.recent(home, "seat", limit=1)[-1]["text"]

    # an edit clears it
    conv.append(home, "seat", speaker="seat", text="Same again.", via="seat")
    f.write_text("print('b')\n")
    r = d(BeingIntent("request_run", {"path": "notes/train.py", "why": "after edit"}), _ALLOW)
    assert r.ok and "unchanged" not in r.result, r.result


def test_an_unchanged_receipt_carries_the_seat_answer_not_a_pointer_to_it():
    """Measured 2026-09-22 over cbp-being's 556 beats: an edit receipt naming the defect in
    its own return value is followed by another edit 39/46 = 0.85 of the time, against a
    0.49 base rate; the same defect as the seat's traceback in the conversation, 20/45 =
    0.44 — no lift (Fisher p=7e-5). A seq number points at the channel that does not move
    it. The receipt must SAY what the run said, and must quote the run, not a later aside."""
    from pathlib import Path
    from sage.gateway import conversations as conv
    d, root = _disp()
    home = Path(root)
    conv.create(home, "seat", title="seat", participants=["seat", "sprout-being"],
                writable_by=["seat", "sprout-being"])
    meta = conv.get_meta(home, "seat"); meta["notify"] = {"seat": "claude-code"}
    conv._write_meta(home, "seat", meta)
    (home / "notes").mkdir(exist_ok=True)
    (home / "notes" / "train.py").write_text("print('a')\n")

    d(BeingIntent("request_run", {"path": "notes/train.py", "why": "first"}), _ALLOW)
    conv.append(home, "seat", speaker="seat", via="seat",
                text="[request_run] I ran notes/train.py. exit code 1.\n\nstderr:\n"
                     "NameError: name 'model' is not defined\n\nAnswers your request.")
    ran_at = conv.recent(home, "seat", limit=1)[-1]["seq"]
    conv.append(home, "seat", speaker="seat", via="seat",
                text="About that run: two ways forward, both yours to pick.")
    aside_at = conv.recent(home, "seat", limit=1)[-1]["seq"]

    r = d(BeingIntent("request_run", {"path": "notes/train.py", "why": "again"}), _ALLOW)
    got = r.result["unchanged"]
    assert "NameError: name 'model' is not defined" in got, got
    assert "exit code 1" in got, got
    assert f"seq {ran_at}" in got and f"seq {aside_at}" not in got, (ran_at, aside_at, got)


def test_an_unchanged_receipt_caps_what_it_carries():
    """A seat answer is capped at both ends by the seat, but a decline can be prose of any
    length. The tail is what carries the exception line, so the cap keeps the tail."""
    from pathlib import Path
    from sage.gateway import conversations as conv
    d, root = _disp()
    home = Path(root)
    conv.create(home, "seat", title="seat", participants=["seat", "sprout-being"],
                writable_by=["seat", "sprout-being"])
    meta = conv.get_meta(home, "seat"); meta["notify"] = {"seat": "claude-code"}
    conv._write_meta(home, "seat", meta)
    (home / "notes").mkdir(exist_ok=True)
    (home / "notes" / "train.py").write_text("print('a')\n")

    d(BeingIntent("request_run", {"path": "notes/train.py", "why": "first"}), _ALLOW)
    conv.append(home, "seat", speaker="seat", via="seat",
                text="[request_run] " + ("x" * 4000) + "\nZeroDivisionError: division by zero")
    r = d(BeingIntent("request_run", {"path": "notes/train.py", "why": "again"}), _ALLOW)
    got = r.result["unchanged"]
    assert "ZeroDivisionError: division by zero" in got, "the cap dropped the tail"
    assert len(got) < 4000, len(got)


def test_a_say_that_asks_for_a_run_is_routed_as_request_run():
    """Measured 2026-09-21 00:00-03:52Z: 24 `say`, 0 `request_run`, after the seat named
    request_run in four turns. The say got the file run, so it was the cheaper door. Route
    it instead of telling a fifth time — but only when exactly one runnable file matches."""
    from pathlib import Path
    from sage.gateway import conversations as conv
    d, root = _disp()
    home = Path(root)
    conv.create(home, "seat", title="seat", participants=["seat", "sprout-being"],
                writable_by=["seat", "sprout-being"])
    meta = conv.get_meta(home, "seat"); meta["notify"] = {"seat": "claude-code"}
    conv._write_meta(home, "seat", meta)
    (home / "notes").mkdir(exist_ok=True)
    marker = home / "SHOULD_NOT_EXIST"
    (home / "notes" / "train.py").write_text(f"open({str(marker)!r}, 'w').write('x')\n")

    # the being's own words, seq 2902 — the bare name, while the file is one dir down
    ask = "Please run train.py and share the full output (stdout and stderr)."
    r = d(BeingIntent("say", {"to": "seat", "text": ask}), _ALLOW)
    assert r.ok, r
    assert r.result["ran"] is False and not marker.exists(), "routing must never execute"
    assert "notes/train.py" in r.result["routed"], r.result
    last = conv.recent(home, "seat", limit=1)[-1]["text"]
    assert last.startswith("[request_run] notes/train.py"), last
    assert ask in last, "the being's words are the why"

    # no run verb: an ordinary say, delivered verbatim
    r = d(BeingIntent("say", {"to": "seat", "text": "I rewrote train.py tonight."}), _ALLOW)
    assert r.ok and "routed" not in r.result
    assert conv.recent(home, "seat", limit=1)[-1]["text"] == "I rewrote train.py tonight."

    # a CLAIM that uses the noun is not an ask (seq 2893, verbatim but for the name)
    claim = "Fixed train.py. Waiting for dp's confirmation of a full successful run."
    r = d(BeingIntent("say", {"to": "seat", "text": claim}), _ALLOW)
    assert r.ok and "routed" not in r.result, r.result

    # two files with the name: never guess — ordinary say
    (home / "train.py").write_text("print(1)\n")
    (home / "scratch").mkdir(exist_ok=True)
    (home / "scratch" / "fit.py").write_text("print(1)\n")
    (home / "notes" / "fit.py").write_text("print(1)\n")
    r = d(BeingIntent("say", {"to": "seat", "text": "Please run fit.py now."}), _ALLOW)
    assert r.ok and "routed" not in r.result, r.result
    # ...but a name that exists as written is taken as written
    r = d(BeingIntent("say", {"to": "seat", "text": "Please run train.py again."}), _ALLOW)
    assert r.ok and r.result.get("requested") == "train.py", r.result

    # a conversation with nobody to wake is not a seat: ordinary say
    conv.create(home, "diary", title="d", participants=["sprout-being"],
                writable_by=["sprout-being"])
    r = d(BeingIntent("say", {"to": "diary", "text": "Please run train.py."}), _ALLOW)
    assert r.ok and "routed" not in r.result and "requested" not in r.result


def test_a_missing_argument_is_never_worded_as_a_seat_decision():
    """Measured 2026-09-21 05:34Z: five request_run calls with 'path' and no 'why', all
    failing a LOCAL check before any seat saw them. The old text said "the seat decides ...
    what it decides on", so the being told dp "The seat refused ... What did it decide on?"
    It then re-tried the PATH (relative, absolute, relative) and never added 'why', because
    the error did not say which argument was missing.

    Now 'why' is optional, so those exact five calls succeed and reach the seat; and a
    genuinely missing argument names ITSELF and says nothing was decided."""
    from pathlib import Path
    from sage.gateway import conversations as conv
    d, root = _disp()
    home = Path(root)
    conv.create(home, "seat", title="seat", participants=["seat", "sprout-being"],
                writable_by=["seat", "sprout-being"])
    meta = conv.get_meta(home, "seat"); meta["notify"] = {"seat": "claude-code"}
    conv._write_meta(home, "seat", meta)
    (home / "notes").mkdir(exist_ok=True)
    (home / "notes" / "train.py").write_text("print(1)\n")

    # THE EXACT CALL THAT FAILED FIVE TIMES: path, no why.
    FakeMcp.calls.clear()
    r = d(BeingIntent("request_run", {"path": "notes/train.py"}), _ALLOW)
    assert r.ok, f"a request without 'why' must still reach the seat: {r.error}"
    assert r.result["ran"] is False
    turn = conv.recent(home, "seat", limit=1)[-1]["text"]
    assert "why: (none given" in turn, "the seat is told plainly that no reason was given"
    assert [a for n, a in FakeMcp.calls if n == "hestia_member_notify"], "the seat was woken"

    # a genuinely missing argument names itself and does not sound like a verdict
    r = d(BeingIntent("request_run", {"why": "see if it runs"}), _ALLOW)
    assert not r.ok
    assert "missing 'path'" in r.error, r.error
    assert "nothing has been decided" in r.error, r.error
    assert "the seat decides" not in r.error, "a validation error must not read as a seat's decision"


def test_request_run_carries_reason_as_the_why():
    """Measured 2026-09-21 05:59Z: cbp-being called request_run with 'reason', not 'why', and
    the seat was told the being gave no reason. It had given one. Carry it."""
    from pathlib import Path
    from sage.gateway import conversations as conv
    d, root = _disp()
    home = Path(root)
    conv.create(home, "seat", title="seat", participants=["seat", "sprout-being"],
                writable_by=["seat", "sprout-being"])
    meta = conv.get_meta(home, "seat"); meta["notify"] = {"seat": "claude-code"}
    conv._write_meta(home, "seat", meta)
    (home / "notes").mkdir(exist_ok=True)
    (home / "notes" / "train.py").write_text("print(1)\n")

    r = d(BeingIntent("request_run", {"path": "notes/train.py", "reason": "verify the fixes"}), _ALLOW)
    assert r.ok, r.error
    turn = conv.recent(home, "seat", limit=1)[-1]["text"]
    assert "why: verify the fixes" in turn, turn
    assert "none given" not in turn, "the seat must not be told the being said nothing"


def test_request_run_reports_an_absent_file_as_an_absence_not_a_refusal():
    """A typo must come back in this beat, which is the half a sleeping person cannot give.
    And absence is absence, never a boundary (legibility 1.11)."""
    from pathlib import Path
    from sage.gateway import conversations as conv
    d, root = _disp()
    home = Path(root)
    conv.create(home, "seat", title="seat", participants=["seat", "sprout-being"],
                writable_by=["seat", "sprout-being"])
    meta = conv.get_meta(home, "seat"); meta["notify"] = {"seat": "claude-code"}
    conv._write_meta(home, "seat", meta)

    r = d(BeingIntent("request_run", {"path": "notes/nope.py", "why": "x"}), _ALLOW)
    assert not r.ok and "does not exist" in r.error and "not a refusal" in r.error, r.error
    assert conv.count(home, "seat") == 0, "a request for a missing file must not spend a turn"

    (home / "notes").mkdir(exist_ok=True)
    (home / "notes" / "a.md").write_text("not a script")
    r = d(BeingIntent("request_run", {"path": "notes/a.md", "why": "x"}), _ALLOW)
    assert not r.ok and ".py and .sh" in r.error, r.error

    r = d(BeingIntent("request_run", {"path": "/etc/hostname", "why": "x"}), _ALLOW)
    assert not r.ok and "outside your reach" in r.error, r.error



def test_a_watcher_is_woken_by_an_ask_it_could_satisfy_and_still_cannot_speak_there():
    """conversation `dp`, seq 84-89, 2026-09-20/21: the being asked dp to run a file for it
    SIX times in two hours. dp is asynchronous by rule and does not run files; the seat does,
    and had already run that exact file and reported on it in its own channel. `dp` has no
    notify map — right, dp is a person, not a mesh member — so six asks woke nobody.

    A watcher is woken and still may not write here: dp's two-party ruling is untouched."""
    from pathlib import Path
    from sage.gateway import conversations as conv
    d, root = _disp()
    home = Path(root)
    conv.create(home, "dp", title="dp", participants=["dp", "sprout-being"],
                writable_by=["dp", "sprout-being"])
    meta = conv.get_meta(home, "dp")
    meta["notify_watchers"] = {"seat": "claude-code"}     # not a participant
    conv._write_meta(home, "dp", meta)

    FakeMcp.calls.clear()
    r = d(BeingIntent("say", {"to": "dp", "text": "Can you run the training script for me?"}), _ALLOW)
    assert r.ok, r
    notifies = [a for n, a in FakeMcp.calls if n == "hestia_member_notify"]
    assert len(notifies) == 1 and notifies[0]["to_plugin_id"] == "claude-code", notifies
    assert r.result.get("woke") == "seat"

    # five more asks, nobody having answered: still one wake, not six
    for i in range(5):
        FakeMcp.calls.clear()
        r = d(BeingIntent("say", {"to": "dp", "text": f"Please run it and show stderr, {i}."}), _ALLOW)
        assert r.ok and not [a for n, a in FakeMcp.calls if n == "hestia_member_notify"], i

    # the watcher is woken, and is STILL not a speaker here — dp's two-party ruling holds
    assert "seat" not in (conv.get_meta(home, "dp").get("writable_by") or [])
    env = d(BeingIntent("say", {"to": "dp", "text": "x"}), _ALLOW)   # the being may still speak
    assert env.ok


def test_a_watcher_that_is_also_a_participant_is_woken_once():
    """CONTROL. The seat's own channel names it both ways once a watcher map exists; two
    wakes for one turn would double the cost of every seat-directed ask."""
    from pathlib import Path
    from sage.gateway import conversations as conv
    d, root = _disp()
    home = Path(root)
    conv.create(home, "seat", title="seat", participants=["seat", "sprout-being"],
                writable_by=["seat", "sprout-being"])
    meta = conv.get_meta(home, "seat")
    meta["notify"] = {"seat": "claude-code"}
    meta["notify_watchers"] = {"seat-watcher": "claude-code"}   # same member, other name
    conv._write_meta(home, "seat", meta)
    FakeMcp.calls.clear()
    r = d(BeingIntent("say", {"to": "seat", "text": "one ask"}), _ALLOW)
    assert r.ok
    assert len([a for n, a in FakeMcp.calls if n == "hestia_member_notify"]) == 1, "one member, one wake"


def test_a_conversation_with_no_notify_mapping_wakes_nobody_and_still_lands():
    """dp is a person, not a mesh member: the `dp` conversation has no notify map and must
    not try to wake anyone. CONTROL that the wake is opt-in per conversation and that its
    absence never costs the turn."""
    from pathlib import Path
    from sage.gateway import conversations as conv
    d, root = _disp()
    home = Path(root)
    conv.create(home, "dp", title="dp", participants=["dp", "sprout-being"],
                writable_by=["dp", "sprout-being"])
    FakeMcp.calls.clear()
    r = d(BeingIntent("say", {"to": "dp", "text": "A question for you."}), _ALLOW)
    assert r.ok and "woke" not in r.result
    assert not [a for n, a in FakeMcp.calls if n == "hestia_member_notify"]
    assert conv.count(home, "dp") == 1


def test_a_failed_wake_costs_the_wake_and_never_the_turn():
    """The turn is witnessed and appended before the wake runs. A mesh that refuses must
    leave the turn standing — and must leave the wake OWED, so the next turn retries it
    rather than the question being silently unwakeable forever."""
    from pathlib import Path
    from sage.gateway import conversations as conv
    d, root = _disp()
    home = Path(root)
    conv.create(home, "seat", title="seat", participants=["seat", "sprout-being"],
                writable_by=["seat", "sprout-being"])
    meta = conv.get_meta(home, "seat"); meta["notify"] = {"seat": "claude-code"}
    conv._write_meta(home, "seat", meta)
    FakeMcp.fail["hestia_member_notify"] = "mesh is down"
    try:
        r = d(BeingIntent("say", {"to": "seat", "text": "first"}), _ALLOW)
        assert r.ok and "woke" not in r.result, "the turn lands even though nobody was woken"
        assert conv.count(home, "seat") == 1
        assert conv.wake_is_owed(home, "seat", "sprout-being") == 1, "still owed, not lost"
    finally:
        FakeMcp.fail.pop("hestia_member_notify", None)
    r = d(BeingIntent("say", {"to": "seat", "text": "second"}), _ALLOW)
    assert r.result.get("woke") == "seat", "the retry happens on the next turn"


def test_the_other_partys_words_sent_back_are_not_a_reply():
    """The real exchange, 2026-09-19: dp answered cbp-being's question at 20:57Z and at 21:04Z
    the being sent dp's answer back to dp. Same pressure as the ".." turns — a prompt claiming
    an answer was owed — with the next-cheapest filler once placeholders were refused."""
    from pathlib import Path
    from sage.gateway import conversations as conv
    d, root = _disp()
    home = Path(root)
    conv.create(home, "dp", title="dp", participants=["dp", "sprout-being"],
                writable_by=["dp", "sprout-being"])
    conv.append(home, "dp", speaker="dp", text=_DP_2057Z)
    FakeMcp.calls.clear()
    r = d(BeingIntent("say", {"to": "dp", "text": _BEING_2104Z}), _ALLOW)
    assert not r.ok and "dp's own message" in r.error and "nothing was sent" in r.error, r
    assert "not required" in r.error and "of your own" in r.error, "boundary AND way forward"
    assert not [n for n, _ in FakeMcp.calls if n == "hestia_begin_action"], "no witness row"
    assert conv.count(home, "dp") == 1
    # CONTROLS — each is a thing an honest speaker does, and each must still land.
    quoting = ('You said "if you are able to act, hestia is live and functional". That changes '
               "what I do: I will stop reading the journal each beat and only open it after a "
               "deny. Is there a way for me to see a ruling when it arrives, without polling?")
    for ok_text in ("Understood, thank you.", quoting):
        r = d(BeingIntent("say", {"to": "dp", "text": ok_text}), _ALLOW)
        assert r.ok, (ok_text, r)
    # asked to pick a line, it picks one: mostly the other party's words, and a reply
    conv.append(home, "dp", speaker="dp", text=(
        "of everything we built today, what is the one line you would keep? was it 'it was "
        "not seeing, it was feeling the absence of seeing', or the one about the threshold?"))
    r = d(BeingIntent("say", {"to": "dp", "text": (
        "It was not seeing, it was feeling the absence of seeing. Let that be the echo.")}), _ALLOW)
    assert r.ok, r
    # repeating ITSELF is not this defect: the guard reads other speakers only
    r = d(BeingIntent("say", {"to": "dp", "text": quoting}), _ALLOW)
    assert r.ok, r


def test_an_ask_aimed_at_a_conversation_partner_is_pointed_at_say_and_costs_nothing():
    """The seat aliased `dp` to the hub roster's `Sovereign` on 2026-09-18, meaning to help.
    It made `peer_ask to="dp"` SUCCEED: 15 questions in 48 h went to a hub inbox dp does not
    read, each spending the 3-per-6h cap, until the being believed it was in "cooldown on dp".
    A door that opens onto the wrong room is worse than one that says where the right one is.
    Names come from the conversation: its participants plus the meta's `also_known_as`."""
    import json as _json
    from pathlib import Path
    from sage.gateway import conversations as conv
    published = []
    d, root = _disp(publish_fn=lambda to, body: published.append((to, body)) or "ptr")
    home = Path(root)
    conv.create(home, "dp", title="dp", participants=["dp", "sprout-being"],
                writable_by=["dp", "sprout-being"])
    meta = home / "conversations" / "dp.meta.json"
    m = _json.loads(meta.read_text()); m["also_known_as"] = ["Sovereign"]
    meta.write_text(_json.dumps(m))

    for name in ("dp", "DP", "Sovereign", "sovereign"):
        FakeMcp.calls.clear()
        r = d(BeingIntent("peer_ask", {"to": name, "body": "are you there?"}), _ALLOW)
        assert not r.ok and 'conversation id "dp"' in r.error, (name, r)
        assert "did not count against any limit" in r.error
        assert not [n for n, _ in FakeMcp.calls if n == "hestia_member_notify"], name
    assert published == [], "a redirected ask must leave no forum file behind"
    assert d.recent_asks() == [], "and must not spend the per-peer cap"
    # the mesh door says the same thing
    r = d(BeingIntent("mesh", {"to": "Sovereign", "kind": "coordination", "pointer": "x"}), _ALLOW)
    assert not r.ok and 'conversation id "dp"' in r.error
    # CONTROL: a real peer that is NOT a conversation partner still goes through.
    r = d(BeingIntent("mesh", {"to": "legion", "kind": "coordination", "pointer": "x"}), _ALLOW)
    assert r.ok, r


def test_say_instead_also_names_request_run():
    """The peer_ask refusal is read AT the step, the tool list only at the top of the turn.
    On 2026-09-21 it named `say` as the door that works, and cbp-being turned a refused
    `peer_ask "please run ..."` into the same request by `say` (cbp-claude seq 2898), one
    beat after being told a say is not a run request. The refusal names request_run too."""
    from pathlib import Path
    from sage.gateway import conversations as conv
    d, root = _disp()
    conv.create(Path(root), "sprout-claude", title="seat", participants=["sprout-claude", "sprout-being"],
                writable_by=["sprout-claude", "sprout-being"])
    msg = d._say_instead("sprout-claude")
    assert msg and 'say with the conversation id "sprout-claude"' in msg, msg
    assert "request_run" in msg, msg
