"""Always listening (opt-in per body) and heard words in the room as they arrive (dp, 2026-10-01).

dp asked aloud "what do you want to remember about today" long after the being last spoke: the listening
window was closed, nothing was transcribed, nothing reached the being."""
import json
import sys
import tempfile
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))
from sage.embodiment import listening  # noqa: E402
from sage.gateway import body, conversations as conv  # noqa: E402

ME = "sprout-being"


def _listen_file(d):
    p = Path(tempfile.mkdtemp(prefix="listen-")) / "listen.json"
    p.write_text(json.dumps(d))
    return str(p)


def test_without_the_opt_in_a_closed_window_stays_closed(monkeypatch):
    monkeypatch.delenv("SAGE_LISTEN", raising=False)
    w = listening.window(path=_listen_file({"listen_until": time.time() - 60}))
    assert w["listening"] is False and w["always"] is False


def test_always_opens_the_window_but_never_hears_its_own_voice(monkeypatch):
    monkeypatch.setenv("SAGE_LISTEN", "always")
    now = time.time()
    w = listening.window(now, path=_listen_file({"listen_until": now - 3600}))
    assert w["listening"] is True and w["always"] is True
    w = listening.window(now, path=_listen_file({"speaking_until": now + 5}))
    assert w["listening"] is True and w["speaking"] is True, "the caller drops audio while speaking"


def test_the_mode_is_read_from_the_bodys_file_by_a_process_without_the_opt_in(monkeypatch):
    """The heartbeat does not carry the cortex's environment; listen.json says what the ear does."""
    monkeypatch.delenv("SAGE_LISTEN", raising=False)
    p = _listen_file({"always": True})
    assert listening.window(path=p)["listening"] is True
    monkeypatch.setattr(listening, "LISTEN_PATH", p)
    assert body.hears_always() is True
    monkeypatch.setattr(listening, "LISTEN_PATH", _listen_file({}))
    assert body.hears_always() is False


def _home():
    h = Path(tempfile.mkdtemp(prefix="room-"))
    conv.create(h, "dp", title="dp", participants=["dp", ME], writable_by=["dp", ME])
    return h


def test_presence_writes_heard_words_into_the_room_as_they_arrive_once_each(monkeypatch):
    from sage.embodiment.presence import Presence
    h = _home()
    monkeypatch.setenv("SAGE_INSTANCE", str(h))
    monkeypatch.setenv("SAGE_MEMBER", ME)
    heard = {"ts": time.time() - 3, "text": "What do you want to remember about today?",
             "seconds": 2.4, "source": "bluez_input.41_42_5A_A0_6B_ED.0"}
    Presence._into_room(heard)
    Presence._into_room(heard)
    turns = [t for t in conv.recent(h, "room") if t.get("from") == "voice"]
    assert [t["text"] for t in turns] == ["What do you want to remember about today?"]
    assert turns[0]["via"] == "voice" and turns[0].get("heard_id")


def test_the_presence_unit_binds_the_being_home():
    """GPT on #309: the code path is a no-op unless the deployment supplies SAGE_INSTANCE."""
    tpl = (Path(__file__).resolve().parents[1] / "systemd" / "presence.service.template").read_text()
    assert "Environment=SAGE_INSTANCE=@INSTANCE@" in tpl
    assert "@INSTANCE@" in tpl.split("[Unit]")[0], "the install note names the marker"


def test_presence_without_a_home_writes_nothing_and_does_not_raise(monkeypatch):
    from sage.embodiment.presence import Presence
    monkeypatch.delenv("SAGE_INSTANCE", raising=False)
    Presence._into_room({"ts": time.time(), "text": "hello"})
