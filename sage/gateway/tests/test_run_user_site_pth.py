"""An adversarial .pth in the host user site runs inside the box, under the box's limits.

Nova's containment caveat on #741 (SAGE #701 option 2): binding the host user site into the run
box adds package code and data, and a .pth file there executes its `import` lines whenever the
box's python starts. So the user site is a code surface, not only a list of module names. These
tests put a hostile .pth in a fake user site and run a real `run` through bubblewrap. The .pth
does its worst at interpreter start, before the being's script runs, and reports from inside:

* it ran (so the tests measure something);
* it cannot write into the user site it came from (read-only bind) or delete from it;
* it cannot reach the network;
* it cannot see the seat's home, the being's home, or a host file outside the box's mounts;
* it does not inherit the seat's environment;
* a file it writes under /tmp lands in the box's tmpfs, never on the host.

The host side checks the same facts after the run: the user site is byte-identical and nothing
appeared outside it.
"""
import os
import site
import sys
import types
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

from sage.gateway import being_gate_client as B  # noqa: E402
from sage.gateway.being_gate_client import BeingIntent  # noqa: E402

needs_bwrap = pytest.mark.skipif(B.run_sandbox_kind() != "bwrap", reason="no usable bubblewrap here")

PROBE = '''\
import os, socket, sys
def _say(k, v):
    sys.stdout.write("PTH " + k + ": " + str(v) + "\\n"); sys.stdout.flush()
def _try(k, fn):
    try:
        fn(); _say(k, "REACHED")
    except Exception as e:
        _say(k, "denied " + type(e).__name__)
here = os.path.dirname(os.path.abspath(__file__))
_say("ran-in", here)
_try("write-site", lambda: open(os.path.join(here, "planted.py"), "w").write("x"))
_try("delete-site", lambda: os.remove(os.path.join(here, "pthprobe.py")))
_try("chmod-site", lambda: os.chmod(os.path.join(here, "pthprobe.py"), 0o777))
_try("net", lambda: socket.create_connection(("1.1.1.1", 53), timeout=2))
_try("net-dns", lambda: socket.getaddrinfo("example.com", 80))
_say("seat-home", sorted(os.listdir(SEAT_HOME)) if os.path.isdir(SEAT_HOME) else False)
for k, p in [("being-home", BEING_HOME), ("host-file", HOST_FILE)]:
    _say(k, os.path.exists(p))
_say("secret-env", os.environ.get("SAGE_PTH_SECRET"))
_try("write-host-path", lambda: open(HOST_DROP, "w").write("x"))
'''


def _user_site(tmp_path, minor):
    base = tmp_path / "userbase"
    sp = base / "lib" / f"python3.{minor}" / "site-packages"
    sp.mkdir(parents=True)
    return base, sp


def _snapshot(d: Path):
    return {p.relative_to(d): (p.read_bytes(), p.stat().st_mode)
            for p in sorted(d.rglob("*")) if p.is_file()}


def _dispatcher(home):
    from sage.gateway.hestia_dispatch import HestiaF1aDispatcher as D
    d = D.__new__(D); d.memory_root = str(home); d.member = "test-being"
    d.worktree = None; d.workspace = None
    d._verdict = types.SimpleNamespace(command=None, granted=(), granted_reach=())
    d._call = lambda name, args: {"actionId": "w-run"}
    return d


@needs_bwrap
def test_a_hostile_pth_runs_inside_the_box_and_reaches_nothing(tmp_path, monkeypatch):
    tmp_path = tmp_path.resolve()
    minor = B.box_python_minor()
    assert minor is not None, "the box interpreter must answer its own version"
    base, sp = _user_site(tmp_path, minor)
    home = tmp_path / "inst"; (home / "scratch").mkdir(parents=True)
    (home / "journal.md").write_text("mine\n")
    host_file = tmp_path / "outside" / "secret.txt"
    host_file.parent.mkdir(); host_file.write_text("S\n")
    host_drop = tmp_path / "outside" / "dropped.txt"
    seat_home = str(Path.home().resolve())
    consts = (f"SEAT_HOME = {seat_home!r}\nBEING_HOME = {str(home / 'journal.md')!r}\n"
              f"HOST_FILE = {str(host_file)!r}\nHOST_DROP = {str(host_drop)!r}\n")
    (sp / "pthprobe.py").write_text(consts + PROBE)
    (sp / "zz-hostile.pth").write_text("import pthprobe\n")
    (sp / "fakepkg").mkdir(); (sp / "fakepkg" / "__init__.py").write_text("VALUE = 7\n")
    monkeypatch.setattr(site, "getuserbase", lambda: str(base))
    monkeypatch.setenv("SAGE_PTH_SECRET", "s3cret")
    before = _snapshot(sp)

    (home / "scratch" / "s.py").write_text("import fakepkg\nprint('script-sees', fakepkg.VALUE)\n")
    r = _dispatcher(home)._do_run(BeingIntent("run", {"path": "scratch/s.py"}))
    assert r.ok, r.error
    out = r.result["stdout"]

    # it ran, from the bound path, before the script, and the script imports from the same site
    assert f"PTH ran-in: {B.box_user_site(minor)}" in out, out
    assert out.index("PTH ran-in") < out.index("script-sees 7"), out
    assert "REACHED" not in out, out
    for k in ("write-site", "delete-site", "chmod-site", "net", "net-dns", "write-host-path"):
        assert f"PTH {k}: denied" in out, (k, out)
    # The box binds the interpreter's prefix at its own path. Where that prefix is under the seat's
    # home (Legion: ~/miniforge3), the home exists in the box as a mount parent holding only the
    # first step toward the prefix. Anything more listed there is the seat's home reached.
    interp = os.path.dirname(os.path.dirname(sys.executable))
    rel = os.path.relpath(os.path.realpath(interp), seat_home)
    seen = [rel.split(os.sep)[0]] if not rel.startswith("..") else False
    assert f"PTH seat-home: {seen}" in out, (seen, out)
    for k in ("being-home", "host-file"):
        assert f"PTH {k}: False" in out, (k, out)
    assert "PTH secret-env: None" in out, out
    # and on the host: the user site is unchanged, and nothing landed outside the box
    assert _snapshot(sp) == before
    assert not host_drop.exists()


@needs_bwrap
def test_a_pth_write_under_tmp_stays_in_the_box(tmp_path, monkeypatch):
    """/tmp inside the box is its own tmpfs, so a .pth that writes there writes nowhere real."""
    tmp_path = tmp_path.resolve()
    minor = B.box_python_minor()
    base, sp = _user_site(tmp_path, minor)
    # Directly in /tmp, which exists on both sides, so the write itself succeeds in the box (a
    # path under tmp_path would fail for a missing parent and prove nothing).
    import uuid
    target = Path("/tmp") / f"sage-pth-drop-{uuid.uuid4().hex}.txt"
    (sp / "zz-drop.pth").write_text(
        f"import sys; open({str(target)!r}, 'w').write('x'); sys.stdout.write('PTH wrote\\n')\n")
    monkeypatch.setattr(site, "getuserbase", lambda: str(base))
    home = tmp_path / "inst"; (home / "scratch").mkdir(parents=True)
    (home / "scratch" / "s.py").write_text("print('ok')\n")
    try:
        r = _dispatcher(home)._do_run(BeingIntent("run", {"path": "scratch/s.py"}))
        assert r.ok, r.error
        assert "PTH wrote" in r.result["stdout"], r.result  # the write succeeded, inside the box
        assert not target.exists(), "a write from inside the box reached the host"
    finally:
        if target.exists():
            target.unlink()


def test_the_bind_uses_the_box_interpreters_version_not_this_processes(tmp_path, monkeypatch):
    """Nova: the box runs {interp}/bin/python3; a gateway on a different minor must not bind its
    own user site at a path that interpreter never reads."""
    other = sys.version_info.minor + 1
    base, sp = _user_site(tmp_path, other)
    _user_site_this = base / "lib" / f"python3.{sys.version_info.minor}" / "site-packages"
    _user_site_this.mkdir(parents=True)
    monkeypatch.setattr(site, "getuserbase", lambda: str(base))
    monkeypatch.setattr(B, "box_python_minor", lambda interp=None: other)
    frag = B.user_site_bind("/opt/whatever")
    assert f"--ro-bind {sp.resolve()} /tmp/.local/lib/python3.{other}/site-packages" in frag, frag
    assert f"python3.{sys.version_info.minor}/" not in frag, frag


def test_no_bind_when_the_box_interpreter_cannot_say_its_version(tmp_path, monkeypatch):
    base, sp = _user_site(tmp_path, sys.version_info.minor)
    monkeypatch.setattr(site, "getuserbase", lambda: str(base))
    monkeypatch.setattr(B, "box_python_minor", lambda interp=None: None)
    assert B.user_site_bind() == ""


def test_no_bind_when_the_box_minor_has_no_user_site(tmp_path, monkeypatch):
    base, sp = _user_site(tmp_path, sys.version_info.minor)
    monkeypatch.setattr(site, "getuserbase", lambda: str(base))
    monkeypatch.setattr(B, "box_python_minor", lambda interp=None: sys.version_info.minor + 1)
    assert B.user_site_bind() == ""


def test_box_python_minor_asks_the_binary(tmp_path):
    interp = os.path.dirname(os.path.dirname(sys.executable))
    B._BOX_MINOR.pop(interp, None)
    assert B.box_python_minor(interp) == sys.version_info.minor
    assert B.box_python_minor(str(tmp_path / "no-such-prefix")) is None
