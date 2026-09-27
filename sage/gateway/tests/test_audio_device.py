"""The headset as a body part that comes and goes (dp, 2026-09-27: "it should be aware when airhug
is offline and know that speak is not available. it should also have a tool to try pairing, with
status report - pairing won't always succeed")."""
import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "..")))
from sage.gateway import body  # noqa: E402
from sage.gateway.being_gate_client import BeingIntent  # noqa: E402

MAC = "41:42:5A:A0:6B:ED"
BUILTIN = {"name": "Built-in Audio Analog Stereo", "kind": "wired", "node": "alsa_output.x"}
AIRHUG = {"name": "AIRHUG 01", "kind": "bluetooth", "node": "bluez_output.41_42.1"}


def _cfg(monkeypatch, connected, seen=True, connect_ok=True):
    monkeypatch.setattr(body, "SPEAK_SINK", "AIRHUG")
    monkeypatch.setattr(body, "AUDIO_BT", MAC)
    monkeypatch.setattr(body.shutil, "which", lambda t: "/usr/bin/" + t)
    state = {"connected": connected}
    calls = []

    def btctl(*args, timeout=10):
        calls.append(args)
        if args[0] == "info":
            return f"Device {MAC} (public)\n\tName: AIRHUG 01\n\tConnected: {'yes' if state['connected'] else 'no'}\n"
        if "scan" in args:
            return f"[CHG] Device {MAC} RSSI: -39\n" if seen else "Discovery started\n"
        if args[0] == "connect":
            if connect_ok:
                state["connected"] = True
                return "Connection successful\n"
            return "Failed to connect: org.bluez.Error.Failed br-connection-page-timeout\n"
        return ""
    monkeypatch.setattr(body, "_btctl", btctl)
    return calls


def test_speak_is_not_offered_when_the_headset_output_is_absent(monkeypatch):
    _cfg(monkeypatch, connected=False)
    audio = {"sinks": [BUILTIN], "sources": []}
    prov = body.speak_provider(audio)
    assert not prov["live"] and "AIRHUG" in prov["why"], "a built-in output is not the speaker for voice"
    monkeypatch.setattr(body, "_pw_audio", lambda **k: audio)
    monkeypatch.setattr(body, "perception", lambda now=None: {"live": False})
    monkeypatch.setattr(body, "metabolism", lambda **k: {"live": False})
    inv = body.inventory()
    assert "speak" not in inv["verbs"] and "pair_audio" in inv["verbs"]
    assert inv["not_yet_wired"] == [], "not 'unwired': the part is just not here right now"
    out = body.render({"perception": {}, "metabolism": {}, "gaze": {}, "inventory": inv}, None)
    assert "AIRHUG 01" in out and "NOT connected" in out and "`speak` is not available" in out
    assert "`pair_audio`" in out and "may not succeed" in out


def test_connected_it_speaks_and_plays_to_that_output_by_node(monkeypatch):
    _cfg(monkeypatch, connected=True)
    audio = {"sinks": [BUILTIN, AIRHUG], "sources": []}
    assert body.speak_provider(audio)["live"]
    monkeypatch.setattr(body, "_pw_audio", lambda **k: audio)
    import subprocess
    seen = []
    monkeypatch.setattr(subprocess, "run", lambda argv, **k: seen.append(argv))
    monkeypatch.setattr(body, "_listening", lambda: type("L", (), {"mark": staticmethod(lambda **k: None)})())
    body.speak("hello")
    assert seen[1][:3] == ["pw-play", "--target", "bluez_output.41_42.1"], "never the default by accident"
    assert body.speaker_name({"audio_sinks": audio["sinks"]}) == "AIRHUG 01"


def test_pair_audio_reports_each_outcome(monkeypatch):
    _cfg(monkeypatch, connected=True)
    assert body.pair_audio()["outcome"] == "already connected"
    _cfg(monkeypatch, connected=False, seen=True, connect_ok=True)
    assert body.pair_audio()["outcome"] == "connected"
    _cfg(monkeypatch, connected=False, seen=False, connect_ok=False)
    r = body.pair_audio()
    assert (r["ok"], r["outcome"]) == (False, "not seen")
    _cfg(monkeypatch, connected=False, seen=True, connect_ok=False)
    r = body.pair_audio()
    assert r["outcome"] == "seen but the connection failed" and "page-timeout" in r["error"]


def test_the_dispatcher_turns_it_into_a_plain_report(monkeypatch):
    from sage.gateway import hestia_dispatch as hd
    _cfg(monkeypatch, connected=False, seen=False, connect_ok=False)
    d = hd.HestiaF1aDispatcher.__new__(hd.HestiaF1aDispatcher)
    calls = []
    d._call = lambda n, a: (calls.append((n, a)) or {"actionId": "a1"})
    d._local = type("L", (), {"_witness": staticmethod(lambda e: "w-1")})()
    env = d._do_pair_audio(BeingIntent("pair_audio", {}))
    assert env.ok and env.result["connected"] is False and env.result["outcome"] == "not seen"
    assert "switched off or out of range" in env.result["report"] and "speak is not available" in env.result["report"]
    assert [c[0] for c in calls] == ["hestia_begin_action", "hestia_record_outcome"]
    monkeypatch.setattr(body, "AUDIO_BT", "")
    env = d._do_pair_audio(BeingIntent("pair_audio", {}))
    assert not env.ok and "no headset is configured" in env.error


def test_unconfigured_bodies_are_unchanged(monkeypatch):
    monkeypatch.setattr(body, "SPEAK_SINK", "")
    monkeypatch.setattr(body, "AUDIO_BT", "")
    monkeypatch.setattr(body.shutil, "which", lambda t: "/usr/bin/" + t)
    assert body.speak_provider({"sinks": [BUILTIN]})["live"], "any output, as before"
    assert body.audio_device() is None


def test_registered_pathless_consequential_no_arguments():
    from sage.gateway.being_gate_client import _REGISTRY, _CONSEQUENTIAL, ollama_tools
    from sage.gateway.heartbeat import BODY_VERBS, EXPLORE_TOOLS
    assert _REGISTRY["pair_audio"]["path_args"] == () and "pair_audio" in _CONSEQUENTIAL
    t = ollama_tools(["pair_audio"])[0]["function"]
    assert t["parameters"]["properties"] == {} and "will not always succeed" in t["description"]
    assert "pair_audio" in BODY_VERBS and "pair_audio" in EXPLORE_TOOLS
