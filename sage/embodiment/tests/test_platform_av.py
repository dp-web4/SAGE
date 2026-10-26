"""The body's audio plumbing per platform: Linux unchanged, a Mac through AVFoundation/afplay/say.

McNugget, 2026-10-14: a USB mic, a USB camera and the monitor's speakers arrive for a Mac body, and
sage/embodiment named PipeWire programs directly (pw-record, pw-play, pw-dump, espeak-ng). These pin:
  * pipewire argv is byte-identical to what Sprout ran before this module existed;
  * avfoundation captures with ffmpeg as RAW s16le (no WAV header, so audio.py skips no header),
    plays with afplay, and its fallback voice keeps the words out of argv (`say -f <file>`);
  * the inventory reads system_profiler's JSON into pw-dump's {sinks, sources} shape;
  * the backend is $SAGE_AUDIO_BACKEND when set, else avfoundation on Darwin only.
No device is touched: subprocess.run is replaced where a program would run.

Plain asserts, so a failure fails under pytest as well as the script runner.
"""
import os
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))
from sage.embodiment import platform_av as pav  # noqa: E402

REAL_SP = ('{"SPAudioDataType":[{"_items":['
           '{"_name":"M156F1","coreaudio_device_output":2,"coreaudio_device_transport":"coreaudio_device_type_displayport"},'
           '{"_name":"Mac mini Speakers","coreaudio_default_audio_output_device":"spaudio_yes","coreaudio_device_output":2,'
           '"coreaudio_device_transport":"coreaudio_device_type_builtin"},'
           '{"_name":"USB Mic","coreaudio_device_input":1,"coreaudio_default_audio_input_device":"spaudio_yes",'
           '"coreaudio_device_transport":"coreaudio_device_type_usb"},'
           '{"_name":"AirPods","coreaudio_device_input":1,"coreaudio_device_output":2,'
           '"coreaudio_device_transport":"coreaudio_device_type_bluetooth"}]}]}')


class Backend:
    def __init__(self, value):
        self.value = value

    def __enter__(self):
        self.saved = os.environ.get("SAGE_AUDIO_BACKEND")
        os.environ["SAGE_AUDIO_BACKEND"] = self.value
        return self

    def __exit__(self, *a):
        if self.saved is None:
            os.environ.pop("SAGE_AUDIO_BACKEND", None)
        else:
            os.environ["SAGE_AUDIO_BACKEND"] = self.saved


def test_pipewire_argv_is_what_sprout_ran_before():
    with Backend("pipewire"):
        argv, header = pav.capture_cmd("bluez_input.41_42_5A_A0_6B_ED.0", 16000)
        assert argv == ["pw-record", "--target", "bluez_input.41_42_5A_A0_6B_ED.0", "--rate", "16000",
                        "--channels", "1", "--format", "s16", "-"] and header is True
        assert pav.play_cmd("/x.wav", "node") == ["pw-play", "--target", "node", "/x.wav"]
        assert pav.play_cmd("/x.wav") == ["pw-play", "/x.wav"]
        assert pav.voice_tools() == ("espeak-ng", "pw-play")
        assert pav.capture_source("bluez_input.x") == "bluez_input.x"


def test_avfoundation_captures_raw_pcm_and_plays_with_afplay():
    with Backend("avfoundation"):
        argv, header = pav.capture_cmd("ignored", 16000)
        assert argv[0] == "ffmpeg" and "avfoundation" in argv and ":default" in argv
        assert argv[-3:] == ["-f", "s16le", "-"] and "16000" in argv and header is False
        assert pav.play_cmd("/x.wav", "ignored") == ["afplay", "/x.wav"]
        assert pav.voice_tools() == ("say", "afplay")
        assert pav.capture_source("ignored") == "avfoundation:default"


def test_the_mac_device_is_chosen_by_name_or_index():
    saved = os.environ.get("SAGE_AUDIO_DEVICE")
    os.environ["SAGE_AUDIO_DEVICE"] = "USB Mic"
    try:
        with Backend("avfoundation"):
            assert ":USB Mic" in pav.capture_cmd("x", 16000)[0]
    finally:
        if saved is None:
            os.environ.pop("SAGE_AUDIO_DEVICE", None)
        else:
            os.environ["SAGE_AUDIO_DEVICE"] = saved


def test_the_mac_fallback_voice_never_puts_the_words_in_argv():
    seen = []
    real = subprocess.run
    subprocess.run = lambda argv, **kw: seen.append((list(argv), open(argv[argv.index("-f") + 1]).read()))
    try:
        with Backend("avfoundation"):
            pav.synth_fallback("rm -rf / ; hello", "/tmp/out.wav", 10)
    finally:
        subprocess.run = real
    argv, text = seen[0]
    assert argv[0] == "say" and "-o" in argv and "/tmp/out.wav" in argv
    assert "rm -rf / ; hello" not in " ".join(argv) and text == "rm -rf / ; hello"


def test_system_profiler_is_called_by_absolute_path():
    """A launchd job's PATH has no /usr/sbin: called by name, the speaker went unseen and every spoken answer was
    refused (McNugget, 2026-10-24..26)."""
    seen = []
    real = subprocess.run
    subprocess.run = lambda argv, **kw: (seen.append(list(argv)),
                                         subprocess.CompletedProcess(argv, 0, stdout=REAL_SP, stderr=""))[1]
    try:
        inv = pav.mac_audio()
    finally:
        subprocess.run = real
    assert seen[0][0] == "/usr/sbin/system_profiler", seen
    assert "Mac mini Speakers" in [s["name"] for s in inv["sinks"]]


def test_the_mac_inventory_has_pw_dumps_shape():
    inv = pav.mac_audio(raw=REAL_SP)
    sinks = {s["name"]: s for s in inv["sinks"]}
    sources = {s["name"]: s for s in inv["sources"]}
    assert set(sinks) == {"M156F1", "Mac mini Speakers", "AirPods"}
    assert set(sources) == {"USB Mic", "AirPods"}
    assert sinks["Mac mini Speakers"]["default"] is True and sinks["M156F1"]["default"] is False
    assert sinks["AirPods"]["kind"] == "bluetooth" and sources["USB Mic"]["kind"] == "wired"
    assert pav.mac_audio(raw="not json") == {}


def test_the_backend_follows_the_platform_unless_set():
    saved, real = os.environ.pop("SAGE_AUDIO_BACKEND", None), sys.platform
    try:
        sys.platform = "darwin"
        assert pav.backend() == "avfoundation"
        sys.platform = "linux"
        assert pav.backend() == "pipewire"
    finally:
        sys.platform = real
        if saved is not None:
            os.environ["SAGE_AUDIO_BACKEND"] = saved


def test_audio_reads_no_header_from_a_headerless_capture():
    from sage.embodiment import audio
    with Backend("avfoundation"):
        assert audio._capture_has_header() is False
    with Backend("pipewire"):
        assert audio._capture_has_header() is True


# ffmpeg -f avfoundation -list_devices true -i "" on McNugget, 2026-10-15 (stderr, verbatim)
REAL_LIST = ("[AVFoundation indev @ 0x9f2c18140] AVFoundation video devices:\n"
             "[AVFoundation indev @ 0x9f2c18140] [0] AIRHUG 02\n"
             "[AVFoundation indev @ 0x9f2c18140] [1] Capture screen 0\n"
             "[AVFoundation indev @ 0x9f2c18140] AVFoundation audio devices:\n"
             "[AVFoundation indev @ 0x9f2c18140] [0] USB Mic\n"
             "[in#0 @ 0x9f2c18000] Error opening input: Input/output error\n")


class Cameras:
    """Replace the AVFoundation device list (no ffmpeg runs) and $SAGE_CAMERA_DEVICE."""
    def __init__(self, names, pinned=None):
        self.names, self.pinned = names, pinned

    def __enter__(self):
        self.real, self.saved = pav.mac_cameras, os.environ.pop("SAGE_CAMERA_DEVICE", None)
        pav.mac_cameras = lambda *a, **k: list(self.names)
        if self.pinned is not None:
            os.environ["SAGE_CAMERA_DEVICE"] = self.pinned
        return self

    def __exit__(self, *a):
        pav.mac_cameras = self.real
        os.environ.pop("SAGE_CAMERA_DEVICE", None)
        if self.saved is not None:
            os.environ["SAGE_CAMERA_DEVICE"] = self.saved


def test_the_mac_camera_list_leaves_the_screens_out():
    assert pav.mac_cameras(raw=REAL_LIST) == ["AIRHUG 02"]
    assert pav.mac_cameras(raw="") == []


def test_a_pinned_screen_is_not_a_camera():
    with Cameras(["AIRHUG 02"]):
        assert pav.mac_camera() == "AIRHUG 02"
    with Cameras(["AIRHUG 02"], pinned="Capture screen 0"):
        assert pav.mac_camera() is None
    with Cameras([]):
        assert pav.mac_camera() is None


def test_the_mac_frame_skips_the_warmup_and_is_written_atomically():
    argv = pav.mac_camera_cmd("AIRHUG 02", "/h/scratch/camera/last-frame.jpg")
    assert argv[argv.index("-i") + 1] == "AIRHUG 02:none"
    assert argv[argv.index("-ss") + 1] == str(pav.CAMERA_WARMUP_S) and argv.index("-ss") > argv.index("-i")
    assert argv[-4:] == ["image2", "-atomic_writing", "1", "/h/scratch/camera/last-frame.jpg"]


def test_a_mac_camera_is_on_when_attached_and_never_a_screen(tmp_path=None):
    import shlex
    import tempfile
    from sage.gateway.being_gate_client import camera_command
    home = os.path.realpath(str(tmp_path or tempfile.mkdtemp()))
    ctx = {"worktree": "/wt", "memory_root": home}
    with Backend("avfoundation"), Cameras(["AIRHUG 02"]):
        cmd = camera_command({"device": "Capture screen 0"}, ctx)
        argv = shlex.split(cmd)
        # the being's device is not used: the seat picks the camera, never a screen
        assert argv[argv.index("-i") + 1] == "AIRHUG 02:none" and "screen" not in cmd
        assert argv[-1] == os.path.join(home, "scratch/camera/last-frame.jpg")
    with Backend("avfoundation"), Cameras([]):
        try:
            camera_command({}, ctx)
            raise AssertionError("no camera, yet a command was composed")
        except ValueError as e:
            assert "no camera attached" in str(e)
    with Backend("pipewire"):
        assert "-f v4l2 -i /dev/video0" in camera_command({}, ctx)       # Linux unchanged


def test_unplugging_the_camera_is_seen_as_it_going_away():
    from sage.gateway import body, toolset
    with Backend("avfoundation"), Cameras(["AIRHUG 02"]):
        on = body.inventory()
    with Backend("avfoundation"), Cameras([]):
        off = body.inventory()
    assert on["video_devices"] == ["AIRHUG 02"] and "camera" in on["verbs"]
    assert "you can capture from with `camera`" in body.render_inventory(on)
    assert "camera" not in toolset.unavailable({"inventory": on}, "/wt")
    assert "camera" not in off["verbs"] and "no camera" in toolset.unavailable({"inventory": off}, "/wt")["camera"]
    gone = body.camera_change(off, on)
    assert "AIRHUG 02 is no longer attached" in gone and "unavailable until it comes back" in gone
    back = body.camera_change(on, off)
    assert "AIRHUG 02 is now attached" in back and "`camera` is available" in back
    assert body.camera_change(on, on) == "" and body.camera_change(on, None) == ""
    with Backend("avfoundation"):
        # a Mac body has no cortex: an attached camera is not "senses offline"
        text = body.render({"inventory": on, "perception": {}, "metabolism": {"live": True}, "gaze": {}},
                           {"inventory": off})
    assert "offline" not in text and "is now attached" in text


if __name__ == "__main__":
    fails = 0
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            try:
                fn()
            except AssertionError as e:
                fails += 1
                print(f"FAIL {name}: {e}")
    print(f"{'FAILED' if fails else 'ok'}: {fails} failure(s)")
    sys.exit(1 if fails else 0)
