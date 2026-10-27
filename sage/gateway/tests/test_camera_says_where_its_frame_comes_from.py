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
    assert "ffmpeg" not in _camera(toolset.specs({}, brief=True, cfg=CORTEX))["description"]
    gone = _camera(toolset.specs({"camera": "your eyes' organ (the cortex) is not running"}, cfg=CORTEX))
    assert "CANNOT WORK" in gone["description"] and "ffmpeg" not in gone["description"]


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
