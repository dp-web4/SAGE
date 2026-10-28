"""On a Mac, camera's text says how a Mac's camera works: no device node, picked by name (#575's follow-up).

mcnugget-being (macOS, AVFoundation), 1,230 beats to 2026-10-27: 0 camera calls, 7,005 mentions of the Linux
node its tool text named, in 234 beats; 191 in its todo, 194 in its journal. _do_camera never reads `device`
there; camera_command picks the camera by name. The text now says that, and offers only out_path."""
import os
import sys
import tempfile

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "..")))
from sage.gateway import toolset  # noqa: E402

NODE = "/dev/" + "video"


def test_a_mac_seat_is_told_its_camera_has_no_device_node():
    desc, params = toolset.here({}, backend="avfoundation")["camera"]
    assert desc == toolset.MAC_CAMERA[0] and NODE not in desc and "no device node" in desc
    assert list(params) == ["out_path"], "device does nothing on a Mac, so it is not offered"


def test_a_linux_seat_keeps_the_registry_text():
    assert "camera" not in toolset.here({}, backend="pipewire")


def test_a_cortex_seat_is_the_cortex_whatever_the_platform():
    assert toolset.here({"camera_source": "cortex"}, backend="avfoundation")["camera"] == toolset.CORTEX_CAMERA


def test_what_the_being_is_sent_and_what_describe_says_agree(monkeypatch):
    monkeypatch.setattr(toolset, "_av_backend", lambda: "avfoundation")
    cam = next(s["function"] for s in toolset.specs(cfg={}) if s["function"]["name"] == "camera")
    assert NODE not in cam["description"] and list(cam["parameters"]["properties"]) == ["out_path"]
    assert cam["parameters"]["required"] == []
    assert NODE not in toolset.full_text("camera", {}) and "no device node" in toolset.full_text("camera", {})
    monkeypatch.setattr(toolset, "_av_backend", lambda: "pipewire")
    cam = next(s["function"] for s in toolset.specs(cfg={}) if s["function"]["name"] == "camera")
    assert NODE in cam["description"] and "device" in cam["parameters"]["properties"]


def test_a_home_behind_a_symlink_is_still_home():
    # camera_command compared a realpath'd out_path with an unresolved home: every macOS temp dir (/var ->
    # /private/var) was refused as "escapes your home" for the default path
    from sage.gateway.being_gate_client import camera_command
    real = tempfile.mkdtemp()
    link = real + ".link"
    os.symlink(real, link)
    try:
        cmd = camera_command({}, {"memory_root": link, "worktree": real, "camera_source": "cortex"})
        assert "last-frame.jpg" in cmd
    finally:
        os.unlink(link)
