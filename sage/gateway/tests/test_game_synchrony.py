"""The game's pictures arrive in the turn they belong to; RESET and game choice are SAID.

dp, 2026-09-19, to the being: "when the game engine supplies the frame as text, we must first run
the visualizer and generate the visual frame for you... you look at the visual and the text,
reason from both." Until now a rendered board could only ride the NEXT beat. And on the same day
the being asked dp for a seat-side reset and "a new game instance" — both of which it already
had, in a grammar that never said so."""
import base64
import os
import tempfile
import types

import pytest

from sage.gateway.being_gate_client import (BeingIntent, ResultEnvelope, game_command, ollama_tools,
                                            GAME_HOLDOUTS, GAME_PLAYABLE)

_CTX = {"game_stepper": "/seat/stepper.py", "memory_root": "/home/being"}


def test_a_holdout_is_refused_where_the_string_is_composed():
    """dev-SAGE non-negotiable 3: the holdouts are the test, "excluded by code". This verb was
    not part of that code until 2026-09-19 — it took any four-character id."""
    for g in GAME_HOLDOUTS:
        with pytest.raises(ValueError) as e:
            game_command({"game": g, "probes": [["RESET"]]}, _CTX)
        assert "HOLDOUT" in str(e.value) and "ft09" in str(e.value), "and it names what CAN be picked"
    assert not set(GAME_HOLDOUTS) & set(GAME_PLAYABLE)
    with pytest.raises(ValueError) as e:
        game_command({"game": "zzzz", "probes": [["RESET"]]}, _CTX)
    assert "no game 'zzzz'" in str(e.value) and "ls20" in str(e.value)


def test_reset_and_another_game_compose():
    assert game_command({"probes": [["RESET"]]}, _CTX).split()[-3:] == ["RESET", "--instance", "/home/being"]
    cmd = game_command({"game": "ls20", "probes": [["ACTION1"], ["LOOK", 0, 0, 15, 15]]}, _CTX)
    assert " --batch ls20 ACTION1+LOOK:0:0:15:15 " in cmd


def test_the_schema_says_reset_and_names_the_games():
    (spec,) = ollama_tools(["game"])
    desc = spec["function"]["description"]
    games = spec["function"]["parameters"]["properties"]["game"]["description"]
    assert "RESET" in desc and "GAME_OVER" in desc, "a verb it holds and is not told about is not held"
    assert "not your camera" in desc, "two feeds, two worlds (dp to the being, 2026-09-19)"
    assert all(g in games for g in GAME_PLAYABLE) and not any(h in games for h in GAME_HOLDOUTS)


def _dispatcher(home):
    from sage.gateway.hestia_dispatch import HestiaF1aDispatcher as D
    d = D.__new__(D); d.memory_root = home
    return d


def test_windows_become_images_and_only_from_the_windows_directory():
    home = tempfile.mkdtemp(prefix="gw-")
    wdir = os.path.join(home, "scratch", "game", "windows"); os.makedirs(wdir)
    open(os.path.join(wdir, "ft09-look-0.jpg"), "wb").write(b"JPEGBYTES")
    open(os.path.join(home, "identity.json"), "w").write("{}")
    d = _dispatcher(home)
    ok = {"file": "scratch/game/windows/ft09-look-0.jpg", "x": [30, 45], "y": [30, 45], "what": "the window"}
    imgs, caps = d._game_windows({"windows": [ok]})
    assert imgs == (base64.b64encode(b"JPEGBYTES").decode(),) and "x 30-45, y 30-45" in caps[0]
    # a name that walks out of the windows directory is not read, whatever reported it
    for bad in ("identity.json", "scratch/game/windows/../../../identity.json", "/etc/hostname"):
        assert d._game_windows({"windows": [dict(ok, file=bad)]}) == ((), ()), bad
    # a missing picture costs the picture, never the result
    assert d._game_windows({"windows": [dict(ok, file="scratch/game/windows/gone.jpg")]}) == ((), ())
    assert d._game_windows({}) == ((), ()) and d._game_windows({"windows": None}) == ((), ())
    # capped per call
    assert len(d._game_windows({"windows": [ok] * 5})[0]) == d.GAME_WINDOW_MAX


def _turn(envelopes, max_steps=0):
    """Run the loop against a fake client that answers `game` with the given envelopes in order."""
    from sage.gateway.being_tool_loop import run_tool_turn
    seen, it = [], iter(envelopes)
    client = types.SimpleNamespace(dispatch=lambda intent: next(it))

    def generate(convo):
        seen.append([dict(m) for m in convo])
        if len(seen) <= len(envelopes):
            k = len(seen)     # a DIFFERENT window each call: identical calls trip the loop's repetition nudge
            return {"content": "", "intents": [BeingIntent("game", {"probes": [["LOOK", k, 0, k + 3, 3]]})]}
        return {"content": "done", "intents": []}
    res = run_tool_turn(client, generate, [{"role": "user", "content": "seed"}], max_steps=max_steps,
                        deadline=None)
    return res, seen


def test_the_picture_arrives_in_the_same_turn_right_after_its_result():
    env = ResultEnvelope(ok=True, result={"looks": []}, images=("B64A", "B64B"),
                         image_captions=("x 0-3, y 0-3: the window", "x 4-7, y 0-3: after move #2"))
    res, seen = _turn([env])
    convo = seen[1]                                   # what the model saw on its NEXT generate
    assert [m["role"] for m in convo[-2:]] == ["tool", "user"], "the picture follows its own result"
    pic = convo[-1]
    assert pic["images"] == ["B64A", "B64B"]
    assert "synthetic feed, not your camera" in pic["content"] and "image 2: x 4-7" in pic["content"]
    assert {"step": 0, "images": 2, "effector": "game"} in res.interjected, "and the record says so"


def test_a_result_with_no_images_adds_nothing():
    res, seen = _turn([ResultEnvelope(ok=True, result={"looks": []})])
    assert seen[1][-1]["role"] == "tool" and not any(i.get("images") for i in res.interjected)


def test_pictures_are_bounded_per_turn_and_the_being_is_told_when_they_stop():
    from sage.gateway.being_tool_loop import MIDTURN_IMAGES_MAX
    two = ResultEnvelope(ok=True, result={}, images=("A", "B"), image_captions=("a", "b"))
    n = MIDTURN_IMAGES_MAX // 2 + 1
    res, seen = _turn([two] * n, max_steps=n + 2)
    carried = sum(len(m.get("images") or []) for m in seen[-1])
    assert carried == MIDTURN_IMAGES_MAX, carried
    told = [m for m in seen[-1] if "pictures resume next beat" in (m.get("content") or "")]
    assert len(told) == 1 and not told[0].get("images")
    assert "text above is complete" in told[0]["content"], "the text never stops; only the pictures do"


def test_an_image_is_counted_once_everywhere_a_conversation_is_sized():
    """It is not characters, so the estimator was blind to it; and if the (tokens, chars) anchor
    counted content only while the estimate counted images, each image would be charged twice."""
    import inspect
    from sage.gateway import being_tool_loop as L
    msgs = [{"role": "user", "content": "abc", "images": ["x"]}, {"role": "tool", "content": "de"}]
    assert L._convo_chars(msgs) == 5 + int(L.MIDTURN_IMAGE_TOKENS * L._CPT_ADDED)
    src = inspect.getsource(L)
    assert 'sum(len(m.get("content") or "") for m in' not in src.replace(inspect.getsource(L._convo_chars), ""), \
        "every sizing site must go through _convo_chars"
