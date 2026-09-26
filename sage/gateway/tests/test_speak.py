"""speak: a being's words become a voice in the room (dp, 2026-09-26: "give it speak tool").

Asked to pair the bluetooth audio and speak, sprout-being journaled for 20 beats that it wanted
to learn how, and held no verb that could. These pin the verb's bounds: offered only on a body
that can speak, words only (no device, command or path), length-capped, refused before any
action opens when the body cannot, and every utterance kept in the being's own home.
"""
import json
import os
import sys
import tempfile

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "..")))
from sage.gateway import body  # noqa: E402
from sage.gateway.being_gate_client import BeingIntent, GatewayVerdict  # noqa: E402

_ALLOW = GatewayVerdict("allow")
_SPEAKER = {"sinks": [{"name": "AIRHUG 01", "kind": "bluetooth"}], "sources": []}


def _dispatcher(monkeypatch, played, live=True):
    from sage.gateway import hestia_dispatch as hd
    calls = []
    home = tempfile.mkdtemp(prefix="speak-")
    d = hd.HestiaF1aDispatcher.__new__(hd.HestiaF1aDispatcher)
    d.memory_root = home
    d._call = lambda name, args: (calls.append((name, args)) or {"actionId": "a1"})
    d._local = type("L", (), {"_witness": staticmethod(lambda e: "w-1")})()
    monkeypatch.setattr(body, "speak_provider",
                        lambda audio=None: {"live": live, "why": "" if live else "no audio output is connected"})
    monkeypatch.setattr(body, "speak", lambda text, timeout=60: (played.append(text) or {"chars": len(text), "seconds": 1.2}))
    return d, home, calls


def test_it_speaks_the_words_and_keeps_them_in_its_own_home(monkeypatch):
    played = []
    d, home, calls = _dispatcher(monkeypatch, played)
    env = d._do_speak(BeingIntent("speak", {"text": "Hello, dp.\nI can hear you now."}))
    assert env.ok and env.witness_id == "w-1"
    assert played == ["Hello, dp. I can hear you now."], "control characters never reach the engine"
    assert [c[0] for c in calls] == ["hestia_begin_action", "hestia_record_outcome"]
    rec = [json.loads(l) for l in open(os.path.join(home, "spoken.jsonl"))]
    assert rec[0]["text"] == "Hello, dp. I can hear you now."
    assert "not in any conversation" in env.result, "sound is not a message; say is the written answer"


def test_empty_words_are_refused_and_name_text(monkeypatch):
    played = []
    d, home, calls = _dispatcher(monkeypatch, played)
    for args in ({}, {"text": "   \n"}, {"message": "hi"}):
        env = d._do_speak(BeingIntent("speak", args))
        assert not env.ok and "needs 'text'" in env.error
    assert "you passed 'message'" in d._do_speak(BeingIntent("speak", {"message": "hi"})).error
    assert played == [] and calls == [] and not os.path.exists(os.path.join(home, "spoken.jsonl"))


def test_an_overlong_utterance_is_refused_whole_not_truncated(monkeypatch):
    played = []
    d, _, calls = _dispatcher(monkeypatch, played)
    env = d._do_speak(BeingIntent("speak", {"text": "a" * (body.SPEAK_MAX_CHARS + 1)}))
    assert not env.ok and str(body.SPEAK_MAX_CHARS) in env.error and "Nothing was said" in env.error
    assert played == [] and calls == []


def test_a_body_that_cannot_speak_refuses_before_any_action_opens(monkeypatch):
    played = []
    d, home, calls = _dispatcher(monkeypatch, played, live=False)
    env = d._do_speak(BeingIntent("speak", {"text": "hello"}))
    assert not env.ok and "no audio output is connected" in env.error and "use say" in env.error
    assert played == [] and calls == [], "no hestia action, no sound"


def test_a_playback_failure_is_reported_as_not_heard(monkeypatch):
    played = []
    d, home, calls = _dispatcher(monkeypatch, played)
    def boom(text, timeout=60):
        raise RuntimeError("sink gone")
    monkeypatch.setattr(body, "speak", boom)
    env = d._do_speak(BeingIntent("speak", {"text": "hello"}))
    assert not env.ok and "nothing was heard" in env.error
    assert calls[-1][1]["outcome"] == "failed"
    assert not os.path.exists(os.path.join(home, "spoken.jsonl")), "only what was heard is recorded"


def test_offered_only_where_the_body_can_speak(monkeypatch):
    from sage.gateway.heartbeat import offered_explore_tools, BODY_VERBS
    assert "speak" in BODY_VERBS
    monkeypatch.setattr(body.shutil, "which", lambda t: "/usr/bin/" + t)
    assert body.speak_provider(_SPEAKER)["live"]
    assert not body.speak_provider({"sinks": []})["live"]
    monkeypatch.setattr(body.shutil, "which", lambda t: None if t == "pw-play" else "/usr/bin/" + t)
    assert body.speak_provider(_SPEAKER)["why"] == "'pw-play' is not installed"
    assert "speak" in offered_explore_tools({"inventory": {"verbs": ["speak"]}})
    assert "speak" not in offered_explore_tools({"inventory": {"verbs": ["gaze"]}})


def test_registered_pathless_consequential_and_words_only():
    from sage.gateway.being_gate_client import _REGISTRY, _CONSEQUENTIAL, ollama_tools
    assert _REGISTRY["speak"]["path_args"] == () and _REGISTRY["speak"]["cmd_arg"] is None
    assert "speak" in _CONSEQUENTIAL, "sound in a room is an external effect; fail closed"
    t = ollama_tools(["speak"])[0]["function"]
    assert list(t["parameters"]["properties"]) == ["text"] and t["parameters"]["required"] == ["text"]
    assert "use say" in t["description"]


def test_the_engine_gets_the_words_as_one_argv_item_never_a_shell(monkeypatch):
    seen = []
    import subprocess
    monkeypatch.setattr(subprocess, "run", lambda argv, **k: seen.append((argv, k)))
    body.speak("hello; rm -rf ~")
    assert all(isinstance(a, list) and not k.get("shell") for a, k in seen)
    assert seen[0][0][-1] == "hello; rm -rf ~" and seen[0][0][-2] == "--"
    assert seen[1][0][0] == "pw-play"
