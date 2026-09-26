"""A being can play: the ARC-AGI-3 `game` verb (#56 slice 6).

dp, 2026-09-15: "build the game verb, batch with cap 8". The being names a game and up to eight
probes; the SEAT composes the stepper line the law judges; the dispatcher runs exactly that line
and hands back the stepper's own envelope. The holdouts (cn04 / dc22 / lf52 / re86) are refused
where the string is composed — dev-SAGE non-negotiable 3, "excluded by code".

Ported from the Legion carrier. The stepper itself is a per-seat fact (instance.json
`game_stepper`); a seat without one gets a refusal that says so, on both halves alike.
"""
import base64
import os
import tempfile
import types

import pytest

from sage.gateway.being_gate_client import (BeingIntent, game_command, ollama_tools,
                                            GAME_HOLDOUTS, GAME_PLAYABLE)

_CTX = {"game_stepper": "/seat/stepper.py", "memory_root": "/home/being"}



def test_game_command_grammar_cap_and_both_sites(tmp_path):
    """dp 2026-09-15: "build the game verb, batch with cap 8". The being names a game and
    probes; the SEAT composes the stepper line the law judges; whitespace-free by
    construction so judged == executed argv; the cap is refused with the cap named."""
    import pytest, sys, shlex
    from sage.gateway.being_gate_client import game_command, GAME_BATCH_CAP
    step = "/opt/arc/being_board_step.py"; home = str(tmp_path.resolve() / "home")
    ctx = {"memory_root": home, "game_stepper": step}
    cmd = game_command({"probes": [["ACTION6", 39, 47], ["action1"], {"action": "ACTION6", "x": 0, "y": 63}]}, ctx)
    assert cmd == f'{sys.executable} {step} --batch ft09 ACTION6:39:47+ACTION1+ACTION6:0:63 --instance {home}'
    assert shlex.split(cmd)[4] == 'ACTION6:39:47+ACTION1+ACTION6:0:63', "one argv element, judged == run"
    # single-probe form
    assert ' ACTION6:5:6 ' in game_command({"action": "ACTION6", "x": 5, "y": 6}, ctx)
    assert ' RESET ' in game_command({"action": "RESET"}, ctx)
    # probes as a JSON string (the model sometimes serialises the list itself)
    assert ' ACTION2 ' in game_command({"probes": '[["ACTION2"]]'}, ctx)
    # the cap, named
    with pytest.raises(ValueError, match=f"at most {GAME_BATCH_CAP} probes"):
        game_command({"probes": [["ACTION1"]] * (GAME_BATCH_CAP + 1)}, ctx)
    assert GAME_BATCH_CAP == 8
    game_command({"probes": [["ACTION1"]] * GAME_BATCH_CAP}, ctx)       # exactly the cap is fine
    # grammar
    for bad, why in ((["ACTION6", 64, 0], "within 0-63"), (["ACTION6", 1], "exactly"), (["ACTION1", 2, 3], "no coordinates"),
                     (["ACTION9"], "must be one of"), (["ACTION6", "a", 1], "whole numbers")):
        with pytest.raises(ValueError, match=why):
            game_command({"probes": [bad]}, ctx)
    with pytest.raises(ValueError, match="four-character id"):
        game_command({"probes": [["ACTION1"]], "game": "../x"}, ctx)
    # no stepper configured on this seat -> a refusal that says whose fault it is
    with pytest.raises(ValueError, match="no game is set up on this seat"):
        game_command({"probes": [["ACTION1"]]}, {"memory_root": home})
    # both composition sites: the client's ctx carries game_stepper, so the judged string
    # is the executed string (the dispatcher passes the same per-being fact)
    from sage.gateway.hestia_dispatch import HestiaF1aDispatcher as D
    d = D.__new__(D); d.memory_root = home; d.game_stepper = step
    assert game_command({"probes": [["ACTION6", 1, 2]]}, {"memory_root": d.memory_root, "game_stepper": d.game_stepper}) == \
        game_command({"probes": [["ACTION6", 1, 2]]}, ctx)


def test_game_is_registered_composed_and_consequential():
    from sage.gateway import being_gate_client as b
    assert b._REGISTRY["game"]["compose"] is b.game_command and b._REGISTRY["game"]["cmd_arg"] is None
    assert "game" in b._CONSEQUENTIAL
    assert "game" in b._TOOL_SCHEMAS and "8 probes" in b._TOOL_SCHEMAS["game"][0]


def test_game_look_is_a_window_not_a_move():
    """LOOK:x0:y0:x1:y1 rides the same grammar; bounded to 16x16; not a click, not a click's shape."""
    import pytest
    from sage.gateway.being_gate_client import game_command, LOOK_MAX_EDGE
    ctx = {"memory_root": "/tmp/h", "game_stepper": "/opt/arc/being_board_step.py"}
    assert " LOOK:44:44:49:49 " in game_command({"probes": [["LOOK", 44, 44, 49, 49]]}, ctx)
    assert " LOOK:0:0:15:15+ACTION6:1:2 " in game_command({"probes": [["look", 0, 0, 15, 15], ["ACTION6", 1, 2]]}, ctx)
    assert LOOK_MAX_EDGE == 16
    # the off-by-one the being hit twice: inclusive bounds, so 0..16 is 17 cells. The refusal
    # must name the size asked for and the x1 that would have worked.
    try:
        game_command({"probes": [["LOOK", 0, 0, 16, 16]]}, ctx); assert False
    except ValueError as e:
        assert "INCLUSIVE" in str(e) and "is 17x17 cells" in str(e) and "x1=x0+15" in str(e), str(e)
    game_command({"probes": [["LOOK", 0, 0, 15, 15]]}, ctx)          # exactly the cap is fine
    for bad, why in ((["LOOK", 0, 0, 16, 3], "is 17x4 cells"), (["LOOK", 5, 5, 4, 5], "x0 <= x1"), (["LOOK", 0, 0, 64, 0], "x0 <= x1"),
                     (["LOOK", 1, 2], "needs"), (["LOOK", "a", 0, 1, 1], "whole numbers")):
        with pytest.raises(ValueError, match=why):
            game_command({"probes": [bad]}, ctx)


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


def _fake_stepper(tmp_path, body):
    p = tmp_path / "stepper.py"; p.write_text(body); return str(p)


def test_game_dispatch_runs_the_judged_line_and_returns_the_stepper_envelope(tmp_path):
    """The dispatcher executes exactly the composed argv (stub stepper echoes it), hands the
    stepper's LAST stdout line back as the result, witnesses the batch as `game` with the
    probe count, and refuses a judged/executed mismatch."""
    import json, types
    from sage.gateway.hestia_dispatch import HestiaF1aDispatcher as D
    from sage.gateway.being_gate_client import BeingIntent, game_command
    home = tmp_path.resolve() / "home"; home.mkdir()
    step = _fake_stepper(tmp_path, "import sys, json, os\n"
                                   "print('noise the dispatcher must skip')\n"
                                   "print(json.dumps({'argv': sys.argv[1:], 'mode': os.getenv('OPERATION_MODE'), 'probes': [{'move': 1}]}))\n")
    d = D.__new__(D); d.memory_root = str(home); d.game_stepper = step
    calls = []
    d._call = lambda name, args: (calls.append((name, args)) or {"actionId": "w9"})
    d._verdict = types.SimpleNamespace(command=game_command({"probes": [["ACTION6", 3, 4], ["ACTION1"]]},
                                                            {"memory_root": str(home), "game_stepper": step}))
    r = d._do_game(BeingIntent("game", {"probes": [["ACTION6", 3, 4], ["ACTION1"]]}))
    assert r.ok, r.error
    assert r.result["argv"] == ["--batch", "ft09", "ACTION6:3:4+ACTION1", "--instance", str(home)]
    assert r.result["mode"] == "offline"
    assert r.witness_id == "w9"
    assert calls[0] == ("hestia_begin_action", {"tool_name": "game", "target": "ft09:2"})
    assert calls[1][0] == "hestia_record_outcome" and calls[1][1]["success"] is True and calls[1][1]["magnitude"] == 2.0

    # judged != executed -> refused before anything runs
    d._verdict = types.SimpleNamespace(command="something else")
    r2 = d._do_game(BeingIntent("game", {"probes": [["ACTION1"]]}))
    assert r2.ok is False and "not the command this dispatcher would execute" in r2.error

    # the stepper fails -> its own last lines, and where the partial record lives
    d._verdict = types.SimpleNamespace(command=None)
    d.game_stepper = _fake_stepper(tmp_path, "import sys; print('engine: no such game', file=sys.stderr); sys.exit(3)\n")
    r3 = d._do_game(BeingIntent("game", {"probes": [["ACTION1"]]}))
    assert r3.ok is False and "exited 3" in r3.error and "engine: no such game" in r3.error
    assert "ft09_actions.jsonl" in r3.error
    assert calls[-1][1]["success"] is False

    # no stepper on this seat -> the composer's refusal, no witness opened
    n = len(calls); d.game_stepper = None
    r4 = d._do_game(BeingIntent("game", {"probes": [["ACTION1"]]}))
    assert r4.ok is False and "no game is set up on this seat" in r4.error and len(calls) == n


def test_build_client_hands_the_stepper_to_both_halves(tmp_path, monkeypatch):
    """One read of instance.json, both halves — the gate composes the string the law judges and
    the dispatcher composes the string it runs, and a stepper only one of them knows is a verb
    the judged/executed guard refuses every time."""
    import json
    from sage.gateway import governed_turn as gt
    inst = tmp_path / "inst"; inst.mkdir()
    (inst / "instance.json").write_text(json.dumps({"game_stepper": "/seat/stepper.py"}))
    seen = {}
    class Rec:
        def __init__(self, *a, **kw): seen.setdefault(type(self).__name__, kw)
    class BeingGateClient(Rec): pass
    class HestiaF1aDispatcher(Rec): pass
    import sage.gateway.being_gate_client as bgc, sage.gateway.hestia_dispatch as hd
    import sage.irp.plugins.ollama_irp as oi
    monkeypatch.setattr(bgc, "BeingGateClient", BeingGateClient)
    monkeypatch.setattr(hd, "HestiaF1aDispatcher", HestiaF1aDispatcher)
    monkeypatch.setattr(oi, "OllamaIRP", lambda cfg: None)
    gt.build_client("m", inst, "model", str(tmp_path), None, "s", 0.3, 100)
    assert seen["BeingGateClient"]["game_stepper"] == "/seat/stepper.py"
    assert seen["HestiaF1aDispatcher"]["game_stepper"] == "/seat/stepper.py"
