"""On macOS an event wakes the being through launchd, not systemd.

McNugget, 2026-10-05: sage.gateway.arousal started beats only with `systemctl`. There is none on
a Mac, so every wake there, dp's turns through the daemon included, ended "no systemctl: wake
request could not be submitted", and the being ran only on its 30-minute launchd timer. The
launchd path keeps the same evidence contract (SAGE #271): exit 0 is acceptance and never beat
entry; no launchctl or no label is a definite non-submission; any other failure is unknown.

Nothing here reaches the real scheduler. The in-process door (`arousal._systemd`) is replaced by
a fake, and the successor script runs against a fake `launchctl` on PATH.

Plain asserts, so a failure fails under pytest as well as the script runner.
Run: python3 sage/gateway/tests/test_arousal_launchd.py   (or pytest)
"""
import os
import subprocess
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parents[2]))
from sage.gateway import arousal  # noqa: E402

LABEL = "com.web4.sage-heartbeat.testbox"
NEXT = "com.web4.sage-heartbeat-next.testbox"
GUI = f"gui/{os.getuid()}/{LABEL}"
SCRIPT = HERE.parents[1] / "scripts" / "launchd_next_beat.sh"


class Fake:
    """The scheduler door. `states` maps a label to its `state = ...` value; a label absent from
    it is a job launchd does not know (print exits 113, as the real one does)."""

    def __init__(self, states=None, kick_rc=0, missing=False):
        self.calls, self.states, self.kick_rc, self.missing = [], dict(states or {}), kick_rc, missing

    def __call__(self, args, timeout=10):
        self.calls.append(list(args))
        if self.missing:
            raise FileNotFoundError("launchctl")
        if args[:2] == ["launchctl", "kickstart"]:
            return subprocess.CompletedProcess(args, self.kick_rc, "", "" if self.kick_rc == 0 else "boom")
        if args[:2] == ["launchctl", "print"]:
            label = args[2].rsplit("/", 1)[-1]
            if label not in self.states:
                return subprocess.CompletedProcess(args, 113, "", "Could not find service")
            return subprocess.CompletedProcess(args, 0, f"{args[2]} = {{\n\tstate = {self.states[label]}\n}}\n", "")
        raise AssertionError(f"unexpected scheduler call: {args}")


class Env:
    """Set/restore env and module attributes around one test, without pytest fixtures."""

    def __init__(self, **env):
        self.env, self.saved, self.attrs = env, {}, {}

    def __enter__(self):
        self.tmp = tempfile.TemporaryDirectory()
        base = {"SAGE_WAKE_BACKEND": "launchd", "SAGE_HEARTBEAT_LABEL": LABEL, "SAGE_MACHINE": None,
                "SAGE_PENDING_EVENTS": str(Path(self.tmp.name) / "pending.json")}
        base.update(self.env)
        for k, v in base.items():
            self.saved[k] = os.environ.get(k)
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v
        for name, val in (("NEXT_QUEUE_DIR", str(Path(self.tmp.name) / "queue")),
                          ("PENDING_PATH", base["SAGE_PENDING_EVENTS"])):
            self.attrs[name] = getattr(arousal, name)
            setattr(arousal, name, val)
        self.attrs["_systemd"] = arousal._systemd
        # The wake marker too: request_beat writes ~/.sprout/beat_wake.json, which the live
        # being's next beat would read as who woke it. The conftest isolates it under pytest;
        # this does it for the script runner as well (it reached the live marker once).
        from sage.gateway import being_join
        marker = str(Path(self.tmp.name) / "beat_wake.json")
        self.real_write = being_join.write_wake_marker
        being_join.write_wake_marker = lambda d, s, path=marker: self.real_write(d, s, path=path)
        return self

    def door(self, fake):
        arousal._systemd = fake
        return fake

    def __exit__(self, *exc):
        for k, v in self.saved.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v
        for name, val in self.attrs.items():
            setattr(arousal, name, val)
        from sage.gateway import being_join
        being_join.write_wake_marker = self.real_write
        self.tmp.cleanup()


def test_a_wake_is_a_kickstart_that_never_kills_a_running_beat():
    with Env() as e:
        fake = e.door(Fake())
        w = arousal._start_wake()
        assert fake.calls == [["launchctl", "kickstart", GUI]], fake.calls
        assert "-k" not in fake.calls[0]
        assert w["start_accepted"] is True and w["started"] is None and w["wake_evidence_version"] == 2, w


def test_a_failed_kickstart_is_unknown_not_rejected():
    with Env() as e:
        e.door(Fake(kick_rc=5))
        w = arousal._start_wake()
        assert w["start_accepted"] is None and "launchctl exit 5" in w["wake_error"], w


def test_no_launchctl_is_a_definite_non_submission():
    with Env() as e:
        e.door(Fake(missing=True))
        w = arousal._start_wake()
        assert w["start_accepted"] is False and "no launchctl" in w["wake_error"], w


def test_no_label_is_a_definite_non_submission():
    with Env(SAGE_HEARTBEAT_LABEL=None, HOME=tempfile.mkdtemp()) as e:
        fake = e.door(Fake())
        w = arousal._start_wake()
        assert w["start_accepted"] is False and "label" in w["wake_error"], w
        assert fake.calls == [], "nothing may be kickstarted without a label"


def test_the_label_comes_from_the_machine_or_the_one_installed_agent():
    with Env(SAGE_HEARTBEAT_LABEL=None, SAGE_MACHINE="mcnugget"):
        assert arousal.heartbeat_label() == "com.web4.sage-heartbeat.mcnugget"
    home = tempfile.mkdtemp()
    agents = Path(home) / "Library" / "LaunchAgents"
    agents.mkdir(parents=True)
    (agents / "com.web4.sage-heartbeat.box.plist").write_text("")
    (agents / "com.web4.sage-heartbeat-next.box.plist").write_text("")
    with Env(SAGE_HEARTBEAT_LABEL=None, HOME=home):
        assert arousal.heartbeat_label() == "com.web4.sage-heartbeat.box", arousal.heartbeat_label()


def test_a_running_beat_is_read_from_launchctl_print():
    with Env() as e:
        e.door(Fake(states={LABEL: "running"}))
        assert arousal.beat_running() is True
        e.door(Fake(states={LABEL: "not running"}))
        assert arousal.beat_running() is False
        e.door(Fake(states={}))
        assert arousal.beat_running() is False


def test_arm_next_queues_one_file_and_reports_armed_only_with_the_agent_loaded():
    with Env() as e:
        e.door(Fake(states={NEXT: "not running"}))
        a = arousal.arm_next()
        f = Path(arousal.NEXT_QUEUE_DIR) / LABEL
        assert a == {"armed": True, "by": NEXT}, a
        assert f.exists()
        b = arousal.arm_next()
        assert b.get("already_armed") is True and sorted(os.listdir(arousal.NEXT_QUEUE_DIR)) == [LABEL], b
        e.door(Fake(states={}))
        c = arousal.arm_next()
        assert c["armed"] is False and "not loaded" in c["error"], c


def test_an_event_starts_a_beat_or_queues_behind_the_running_one():
    with Env() as e:
        fake = e.door(Fake(states={LABEL: "not running", NEXT: "not running"}))
        d = arousal.request_beat("dp_turn", "dp spoke", instance=Path(e.tmp.name))
        assert d["engage"] is True and d["start_accepted"] is True, d
        assert ["launchctl", "kickstart", GUI] in fake.calls
        fake = e.door(Fake(states={LABEL: "running", NEXT: "not running"}))
        d = arousal.request_beat("dp_turn", "dp spoke again", instance=Path(e.tmp.name))
        assert d["engage"] is False and d["next"]["armed"] is True, d
        assert not any(c[:2] == ["launchctl", "kickstart"] for c in fake.calls), "a running beat is never restarted"


def test_the_backend_is_launchd_only_without_systemctl():
    import shutil
    real = shutil.which
    try:
        with Env(SAGE_WAKE_BACKEND=None):
            shutil.which = lambda n: "/bin/launchctl" if n == "launchctl" else None
            assert arousal._backend() == "launchd"
            shutil.which = lambda n: "/usr/bin/" + n
            assert arousal._backend() == "systemd"
    finally:
        shutil.which = real


def _run_successor(states, queued=True, max_wait="30"):
    """Run the real successor script against a fake launchctl that answers `states` in order
    (the last repeats) and records every call."""
    d = Path(tempfile.mkdtemp())
    q = d / "queue"
    q.mkdir()
    if queued:
        (q / LABEL).write_text("1\n")
    (d / "states").write_text("\n".join(states) + "\n")
    log = d / "calls"
    fake = d / "launchctl"
    fake.write_text(f"""#!/bin/sh
echo "$*" >> "{log}"
if [ "$1" = print ]; then
  s=$(head -n 1 "{d}/states")
  n=$(wc -l < "{d}/states")
  if [ "$n" -gt 1 ]; then tail -n +2 "{d}/states" > "{d}/states.t"; mv "{d}/states.t" "{d}/states"; fi
  printf '%s = {{\\n\\tstate = %s\\n}}\\n' "$2" "$s"
fi
exit 0
""")
    fake.chmod(0o755)
    env = dict(os.environ, LAUNCHCTL=str(fake), SLEEP_S="1")
    p = subprocess.run(["sh", str(SCRIPT), LABEL, str(q), max_wait], capture_output=True, text=True, env=env, timeout=60)
    calls = log.read_text().splitlines() if log.exists() else []
    return p, calls, (q / LABEL).exists()


def test_the_successor_waits_for_the_beat_to_end_then_kickstarts_once():
    p, calls, still = _run_successor(["running", "running", "not running"])
    kicks = [c for c in calls if c.startswith("kickstart")]
    assert p.returncode == 0, p.stdout + p.stderr
    assert kicks == [f"kickstart {GUI}"], calls
    assert sum(c.startswith("print") for c in calls) == 3, calls
    assert not still, "the queue file must be cleared, or launchd runs the successor forever"


def test_the_successor_does_nothing_when_nothing_is_queued():
    p, calls, _ = _run_successor(["not running"], queued=False)
    assert p.returncode == 0 and calls == [], calls


def test_the_successor_gives_up_without_losing_the_request():
    p, calls, still = _run_successor(["running"], max_wait="2")
    assert p.returncode == 1, p.stdout
    assert not any(c.startswith("kickstart") for c in calls), calls
    assert still, "a request it could not serve stays queued"


if __name__ == "__main__":
    os.environ.setdefault("SAGE_NO_SYSTEMD", "1")
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
