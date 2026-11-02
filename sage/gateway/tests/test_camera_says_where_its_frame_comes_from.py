"""camera says where its frame comes from on THIS seat. Its registry text is the ffmpeg path ("The seat runs
ffmpeg against /dev/video0 (or a plain device node you name)", `device` defaulting to /dev/video0). On a seat
with camera_source "cortex" the frame comes from the cortex and `device` is never read. Measured on Sprout
2026-10-14..27: 612 of the being's 1,010 request_runs were about the device node, while its own camera text
said, every beat, that its camera reads that node."""
from sage.gateway import toolset
from sage.gateway.being_gate_client import _TOOL_SCHEMAS, BeingIntent, ResultEnvelope
from sage.gateway.being_tool_loop import run_tool_turn

CORTEX = {"camera_source": "cortex"}


def _camera(specs):
    return next(t["function"] for t in specs if t["function"]["name"] == "camera")


def test_a_cortex_seat_is_told_its_frame_comes_from_the_cortex_and_offered_no_device():
    cam = _camera(toolset.specs({}, cfg=CORTEX))
    assert "cortex" in cam["description"] and "no device node" in cam["description"]
    assert "ffmpeg" not in cam["description"] and "/dev/video" not in cam["description"]
    assert list(cam["parameters"]["properties"]) == ["out_path"]


def test_every_other_seat_keeps_the_registry_text():
    for cfg in (None, {}, {"camera_source": "ffmpeg"}):
        cam = _camera(toolset.specs({}, cfg=cfg))
        assert cam["description"] == _TOOL_SCHEMAS["camera"][0]
        assert "device" in cam["parameters"]["properties"]


def test_brief_mode_and_an_unavailable_camera_still_follow_the_seat():
    # "ffmpeg" is absent from the registry's first sentence too, so these assert on the cortex text itself
    brief = _camera(toolset.specs({}, brief=True, cfg=CORTEX))["description"]
    assert brief.startswith("Take ONE frame from your own eye")
    gone = _camera(toolset.specs({"camera": "your eyes' organ (the cortex) is not running"}, cfg=CORTEX))
    assert "CANNOT WORK" in gone["description"] and gone["description"].startswith("Take ONE frame from your own eye")


def test_describe_answers_as_this_seat_offers_it():
    assert "ffmpeg" not in toolset.full_text("camera", CORTEX)
    assert "ffmpeg" in toolset.full_text("camera")

    class C:
        camera_source = "cortex"

        def gate(self, intent):
            raise AssertionError("describe is never gated")

        def dispatch(self, intent, v):
            return ResultEnvelope(ok=True, result="r")
    seq = iter([{"content": "", "intents": [BeingIntent("describe", {"verb": "camera"})]},
                {"content": "done", "intents": []}])
    r = run_tool_turn(C(), lambda convo: next(seq), [{"role": "user", "content": "beat"}], max_steps=3)
    assert "cortex" in r.trace[0][1].result and "ffmpeg" not in r.trace[0][1].result


def test_the_dispatcher_never_reads_device_on_a_cortex_seat():
    # what the text says must be what happens: camera_command ignores `device` when the source is cortex
    from sage.gateway.being_gate_client import camera_command
    cmd = camera_command({"device": "/dev/video9"}, {"memory_root": "/tmp/h", "camera_source": "cortex"})
    assert "/dev/video9" not in cmd and "sage.embodiment.look" in cmd


def _raising_offer(tmp_path, monkeypatch, cfg):
    """Run the raising session's tool offer far enough to see what both halves were built with.

    `autonomous-sprout-sage.service` runs this path, not governed_turn (pub's review of #575):
    the description followed `cfg` while both constructors were built without `camera_source`."""
    import importlib.util
    import json
    from types import SimpleNamespace
    from pathlib import Path
    import sage.gateway.being_gate_client as bgc
    import sage.gateway.being_tool_loop as btl
    import sage.gateway.hestia_dispatch as hd

    (tmp_path / "instance.json").write_text(json.dumps(cfg))
    built = {}

    class Rec:
        def __init__(self, name):
            self.name = name

        def __call__(self, *a, **kw):
            built[self.name] = kw
            return SimpleNamespace(**kw)

    monkeypatch.setattr(hd, "HestiaF1aDispatcher", Rec("dispatcher"))
    monkeypatch.setattr(bgc, "BeingGateClient", Rec("client"))
    monkeypatch.setattr(btl, "run_ollama_tool_turn", lambda *a, **kw: None)
    monkeypatch.setenv("SAGE_TOOLS", "1")
    script = Path(__file__).resolve().parents[2] / "raising" / "scripts" / "ollama_raising_session.py"
    spec = importlib.util.spec_from_file_location("ollama_raising_session_camera", script)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    me = SimpleNamespace(instance=SimpleNamespace(root=tmp_path, identity=tmp_path / "identity.json"),
                         llm=None, machine="testseat", _record_tool_turn=lambda r: None)
    mod.OllamaRaisingSession._maybe_offer_tools(me)
    return built


def test_the_raising_session_tells_both_halves_it_is_a_cortex_seat(tmp_path, monkeypatch):
    built = _raising_offer(tmp_path, monkeypatch, {"camera_source": "cortex"})
    assert built["dispatcher"]["camera_source"] == "cortex"
    assert built["client"]["camera_source"] == "cortex"


def test_the_raising_session_keeps_the_device_path_elsewhere(tmp_path, monkeypatch):
    built = _raising_offer(tmp_path, monkeypatch, {})
    assert built["dispatcher"]["camera_source"] is None
    assert built["client"]["camera_source"] is None
