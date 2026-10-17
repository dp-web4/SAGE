"""An ask gets its own turn (option (c), 2026-10-16). With #424 and #452 the words arrived (10 of 25
envelopes on HUB) and hub-being still sent 0 say / 0 peer_ask: in view among the full tool set, the words
did not make an answer. So one ask is offered the answer turn's shape: the asker, its words, the JSON
{answer, message}. answer=true goes through the gate as the being's own peer_ask to the asker."""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))
from sage.gateway import being_inbox_drain as d  # noqa: E402
from sage.gateway import heartbeat as hb  # noqa: E402
from sage.gateway.being_gate_client import ResultEnvelope  # noqa: E402

ASK = ("---\nfrom: cbp-being\nto: hub-being\nkind: coordination\ndate: 2026-10-15\n---\n\n"
       "Hello hub. What does your camera see right now?")


def _home(tmp_path, posts):
    """A being home whose inbox holds one envelope per (id, kind, post text or None for pointer-only)."""
    root = tmp_path / "ai"
    (root / "sage").mkdir(parents=True)
    (root / "shared-context" / "forum").mkdir(parents=True)
    home = root / "sage" / "home"
    home.mkdir()
    notices = []
    for nid, kind, text in posts:
        ptr = f"shared-context/forum/ask-{nid}.md"
        if text is not None:
            (root / ptr).write_text(text)
        p = d.persist_notice(home, {"id": f"h{nid}", "kind": kind, "from": "7ba65c0d", "pointer_uri": ptr},
                             "seat", workspace=str(root / "sage"))
        notices.append({"id": nid, "kind": kind, "from_plugin": "seat",
                        "pointer_uri": str(p), "queued_at": "2026-10-15T19:33:21Z"})
    return home, notices


class LLM:
    def __init__(self, content):
        self.content, self.calls = content, []

    def resolve_num_predict(self):
        return 6000

    def get_chat_response(self, messages, tools=None, fmt=None):
        self.calls.append({"messages": messages, "fmt": fmt})
        return {"content": self.content, "tool_calls": [],
                "raw": {"message": {}, "done_reason": "stop", "prompt_eval_count": 200, "eval_count": 40}}


class Client:
    def __init__(self, ok=True, error=None):
        self.sent, self.ok, self.error = [], ok, error

    def dispatch(self, intent):
        self.sent.append(intent)
        return ResultEnvelope(ok=self.ok, error=self.error, result={} if self.ok else None)


def test_the_newest_inlined_ask_with_a_named_sender_is_selected(tmp_path):
    home, ns = _home(tmp_path, [(1, "coordination", ASK), (2, "reply", "no front matter, no sender"),
                                (3, "coordination", None), (4, "review_done", ASK)])
    got = hb.select_ask(ns, set(), home)
    assert (got["id"], got["asker"]) == (1, "cbp-being") and "camera" in got["words"]


def test_a_handled_or_twice_tried_ask_is_not_offered(tmp_path):
    home, ns = _home(tmp_path, [(1, "coordination", ASK), (2, "coordination", ASK)])
    assert hb.select_ask(ns, {2}, home)["id"] == 1
    assert hb.select_ask(ns, {2}, home, {"1": hb.ASK_TURN_TRIES}) is None
    assert hb.select_ask(ns, set(), None) is None


def test_an_asker_at_the_peer_ask_limit_is_skipped_not_spent(tmp_path):
    """HUB review of #459: a refused peer_ask counted as a try, so an asker the being had already asked
    3 times in 6 h spent both tries on the limit and was left. Now it is skipped while capped (another
    asker's ask goes instead) and offered again once the window frees, with no try spent."""
    other = ASK.replace("from: cbp-being", "from: sprout-being")
    home, ns = _home(tmp_path, [(1, "coordination", other), (2, "coordination", ASK)])
    t0 = 1_000_000.0
    (home / "asks_sent.jsonl").write_text("".join(
        json.dumps({"t": t0 - 60 * i, "peer": "cbp-being"}) + "\n" for i in range(3)))
    got = hb.select_ask(ns, set(), home, now=t0)
    assert (got["id"], got["asker"]) == (1, "sprout-being")
    assert hb.select_ask(ns, {1}, home, now=t0) is None
    assert hb.select_ask(ns, {1}, home, now=t0 + 6 * 3600)["id"] == 2


def test_an_answer_is_dispatched_as_the_beings_own_peer_ask_to_the_asker(tmp_path):
    home, ns = _home(tmp_path, [(1, "coordination", ASK)])
    ask, client = hb.select_ask(ns, set(), home), Client()
    llm = LLM(json.dumps({"answer": True, "message": "A desk and a window."}))
    res = hb.ask_turn_json(client, llm, ask, name="hub", machine="hub", member="hub-being")
    assert [(i.effector, i.args) for i in client.sent] == [("peer_ask", {"to": "cbp-being", "body": "A desk and a window."})]
    assert res.answer_form["sent"] and res.answer_form["decided"] and res.answer_form["notice"] == 1
    # only the asker and its words are in view: no tools, no record, no inbox
    user = llm.calls[0]["messages"][1]["content"]
    assert user.startswith("cbp-being sent you this message") and "camera" in user
    assert llm.calls[0]["fmt"] == hb.ANSWER_SCHEMA and "memory_read" not in user and "tool" not in user


def test_silence_is_a_decision_an_unparsed_or_refused_reply_is_not(tmp_path):
    home, ns = _home(tmp_path, [(1, "coordination", ASK)])
    ask = hb.select_ask(ns, set(), home)
    quiet = hb.ask_turn_json(Client(), LLM(json.dumps({"answer": False, "message": ""})), ask,
                             name="h", machine="h", member="m").answer_form
    prose = hb.ask_turn_json(Client(), LLM("I see a desk."), ask, name="h", machine="h", member="m").answer_form
    refused = hb.ask_turn_json(Client(ok=False, error="asked cbp-being 3 times in 6 h"),
                               LLM(json.dumps({"answer": True, "message": "hi"})), ask,
                               name="h", machine="h", member="m").answer_form
    assert (quiet["why"], quiet["decided"]) == ("chose silence", True)
    assert (prose["parsed"], prose["decided"]) == (False, False)
    assert (refused["sent"], refused["decided"]) == (False, False) and "3 times" in refused["refused"]



def test_an_answer_must_be_a_json_boolean_and_message_a_string(tmp_path):
    """Nonboolean model output cannot authorize peer_ask, even when truthy."""
    home, ns = _home(tmp_path, [(1, "coordination", ASK)])
    ask = hb.select_ask(ns, set(), home)
    for answer in ("false", "true", 1, 0, None, [], {}):
        client = Client()
        res = hb.ask_turn_json(client, LLM(json.dumps({"answer": answer, "message": "A reply"})), ask,
                               name="h", machine="h", member="m")
        assert client.sent == [], (answer, client.sent)
        assert res.answer_form["parsed"] is False and not res.answer_form.get("decided"), res.answer_form
    client = Client()
    bad_message = hb.ask_turn_json(client, LLM(json.dumps({"answer": True, "message": 42})), ask,
                                   name="h", machine="h", member="m")
    assert client.sent == [] and bad_message.answer_form["parsed"] is False

def test_the_ledger_folds_a_decided_ask_and_counts_an_undecided_try(tmp_path):
    ns = [{"id": 1, "kind": "coordination", "pointer_uri": "a", "queued_at": "2026-10-15T00:00:00Z"},
          {"id": 2, "kind": "coordination", "pointer_uri": "b", "queued_at": "2026-10-15T00:00:00Z"}]
    led = hb.inbox_ledger({}, ns, [], False, [], asked_now={"notice": 2, "decided": False})
    assert led["asked"] == [] and led["ask_tries"] == {"2": 1}
    led = hb.inbox_ledger({"inbox": led}, ns, [], False, [], asked_now={"notice": 1, "decided": True})
    assert led["asked"] == [1] and led["ask_tries"] == {"2": 1} and led["opened"] == []
    assert hb.inbox_handled({"inbox": led}) == {1}
    # pruned with the inbox, carried when the inbox could not be read
    assert hb.inbox_ledger({"inbox": led}, ns[1:], [], False, [])["asked"] == []
    assert hb.inbox_ledger({"inbox": led}, [], [], False, [])["asked"] == [1]


def test_it_is_off_unless_the_instance_opts_in(tmp_path):
    assert hb.ask_turn_on(tmp_path) is False
    (tmp_path / "instance.json").write_text(json.dumps({"ask_turn": "true"}))
    assert hb.ask_turn_on(tmp_path) is False
    (tmp_path / "instance.json").write_text(json.dumps({"ask_turn": True}))
    assert hb.ask_turn_on(tmp_path) is True


def test_main_runs_the_ask_turn_and_the_next_beat_folds_the_ask(tmp_path, monkeypatch):
    """Driven through heartbeat.main(), as test_inbox_ledger_wiring.py drives the ledger: an opted-in
    instance with one inlined ask sends one peer_ask to the asker, records the turn, and the next beat
    neither offers it again nor counts it unopened."""
    from types import SimpleNamespace as NS
    from sage.gateway import governed_turn, being_tool_loop, egress_drain
    root = tmp_path / "ai"
    (root / "sage").mkdir(parents=True)
    (root / "shared-context" / "forum").mkdir(parents=True)
    (root / "shared-context/forum/ask.md").write_text(ASK)
    inst = root / "sage" / "inst"
    inst.mkdir()
    (inst / "identity.json").write_text(json.dumps({"identity": {"name": "t", "machine": "testbox"}}))
    (inst / "instance.json").write_text(json.dumps({"machine": "testbox", "ask_turn": True}))
    env = d.persist_notice(inst, {"id": "h1", "kind": "coordination", "from": "7ba65c0d",
                                  "pointer_uri": "shared-context/forum/ask.md"}, "seat", workspace=str(root / "sage"))
    notice = {"id": 601, "kind": "coordination", "from_plugin": "seat",
              "queued_at": "2026-10-15T19:33:21Z", "pointer_uri": str(env)}
    forum = tmp_path / "forum"
    forum.mkdir()

    class Disp:
        endpoint = membot_endpoint = "http://127.0.0.1:9/mcp"

        def drain_inbox(self, peek=False):
            return ResultEnvelope(ok=True, result={"notices": [notice]})

    sent = []

    def dispatch(intent):
        sent.append(intent)
        return ResultEnvelope(ok=True, result={})

    asks = []

    def chat(messages, **kw):
        asks.append(messages)
        return {"content": json.dumps({"answer": True, "message": "A desk and a window."}),
                "raw": {"message": {}, "done_reason": "stop"}}

    llm = NS(num_ctx=32768, get_chat_response=chat)
    monkeypatch.setattr(governed_turn, "build_client", lambda *a, **k: (NS(_dispatcher=Disp(), dispatch=dispatch), llm))
    monkeypatch.setattr(being_tool_loop, "run_ollama_tool_turn",
                        lambda *a, **k: being_tool_loop.ToolTurnResult(reply="", trace=[], steps=0))
    monkeypatch.setattr(hb, "fleet_digest", lambda *a, **k: "(no digest)")
    monkeypatch.setattr(egress_drain, "drain_once", lambda **k: {"drained": 0})

    def beat():
        assert hb.main(["--member", "test-being", "--model", "qwen3.8-distill:4b", "--instance", str(inst),
                        "--forum-dir", str(forum), "--repos", "", "--no-hub-drain", "--no-escalate"]) == 0
        return json.loads((inst / "heartbeats.jsonl").read_text().strip().splitlines()[-1])

    rec1 = beat()
    assert [(i.effector, i.args) for i in sent] == [("peer_ask", {"to": "cbp-being", "body": "A desk and a window."})]
    form = [i for i in rec1["interventions"] if i["kind"] == "ask_turn"]
    assert form and form[0]["sent"] and form[0]["notice"] == 601, rec1["interventions"]
    assert rec1["ask_turn"]["trace"], rec1["ask_turn"]
    assert rec1["inbox"]["asked"] == [601] and rec1["inbox"]["unopened_asks"] == 0, rec1["inbox"]
    rec2 = beat()
    offered = [m for m in asks if "cbp-being sent you this message" in str(m[-1].get("content"))]
    assert len(sent) == 1 and len(offered) == 1, "a decided ask is not offered again"
    assert rec2["ask_turn"] is None and rec2["inbox"]["asked"] == [601]
