"""A run sees the being's grants by reference, at the same paths, with the grants' own modes.

dp, 2026-10-23: "the sandbox might need to reflect being's actual grants, including writes where
granted. otherwise there is a misalignment of permissions between what it can do directly vs what
it can do using tools/code." Measured that morning on cbp-being: memory_read had read the
governance closure file on every beat, and scratch/check_file.py, run in the sandbox, printed
"File exists: False" for the same path. The being believed its check and filed a dozen scope
requests for a file it already had.

dp, later the same day: "the intent is that sandbox inherits being's actual grants by reference,
not rewrite (so any that are subsequently changed/modified automatically update in the box)."

The bind type is the grant's mode, failing closed (Nova's HOLD on 76f079bf0): writable only with
both w and d, read-only with r alone or w without d, absent without r. The source is the law's
own policy grants, re-read for every run, so nothing narrower or wider than the law reaches the
box.

The real-run tests assert on what a script prints from INSIDE bubblewrap, so a mount that stopped
mounting, wrote where it must not, or started showing the home, turns them red.
"""
import os
import sys
import types
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

from sage.gateway import being_gate_client as B  # noqa: E402
from sage.gateway.being_gate_client import BeingIntent, run_command, run_grant_mounts  # noqa: E402

needs_bwrap = pytest.mark.skipif(B.run_sandbox_kind() != "bwrap", reason="no usable bubblewrap here")


def _world(tmp_path):
    root = tmp_path.resolve()
    home = root / "inst"; (home / "scratch").mkdir(parents=True)
    (home / "journal.md").write_text("mine\n")
    ws = root / "ws"
    gov = ws / "gov"; gov.mkdir(parents=True); (gov / "closure.py").write_text("CLOSURE = 1\n")
    rw = ws / "rw"; rw.mkdir(); (rw / "keep.txt").write_text("KEEP\n")
    wnod = ws / "wnod"; wnod.mkdir(); (wnod / "w.txt").write_text("W\n")
    one = ws / "one.txt"; one.write_text("ONE\n")
    exact = ws / "exactdir"; exact.mkdir(); (exact / "secret.txt").write_text("S\n")
    nor = ws / "nor"; nor.mkdir(); (nor / "n.txt").write_text("N\n")
    ungranted = ws / "ungranted"; ungranted.mkdir(); (ungranted / "x.txt").write_text("X\n")
    os.symlink(str(ungranted), str(ws / "link"))
    return root, home, ws


def _reach(ws):
    """As the policy would carry them: pairs are mode-blind grants (rwed); triples name modes."""
    return ((str(ws / "rw"), True),                     # mode-blind list: rwed
            (str(ws / "gov"), True, "r"),               # read-only
            (str(ws / "wnod"), True, "rw"),             # write without delete: fails closed to ro
            (str(ws / "one.txt"), False, "r"),          # a file, read-only
            (str(ws / "nor"), True, "wd"),              # no r: not mounted
            (str(ws / "exactdir"), False),
            (str(ws / "link"), True))


def _dispatcher(home, reach):
    from sage.gateway.hestia_dispatch import HestiaF1aDispatcher as D
    d = D.__new__(D); d.memory_root = str(home); d.member = "test-being"
    d.worktree = None; d.workspace = None
    d._verdict = types.SimpleNamespace(command=None, granted=tuple(r[0] for r in reach),
                                       granted_reach=reach)
    d._call = lambda name, args: {"actionId": "w-run"}
    return d


# -- which grants become mounts, and how ---------------------------------------------------------

def test_the_bind_type_is_the_grants_mode_and_it_fails_closed(tmp_path):
    root, home, ws = _world(tmp_path)
    mounts, skipped, mask = run_grant_mounts({"memory_root": str(home), "granted_reach": _reach(ws)})
    assert mounts == sorted([(str(ws / "gov"), "dir", "ro"), (str(ws / "one.txt"), "file", "ro"),
                             (str(ws / "rw"), "dir", "rw"), (str(ws / "wnod"), "dir", "ro")])
    why = dict(skipped)
    assert "without r" in why[str(ws / "nor")]
    assert "exact grant on a directory" in why[str(ws / "exactdir")]
    assert "symlink" in why[str(ws / "link")]
    assert mask is False
    cmd = run_command({"path": "scratch/a.py"},
                      {"memory_root": str(home), "member": "test-being", "granted_reach": _reach(ws)})
    assert f"--bind {ws / 'rw'} {ws / 'rw'}" in cmd
    for p in ("gov", "wnod", "one.txt"):
        assert f"--ro-bind {ws / p} {ws / p}" in cmd and f" --bind {ws / p} " not in cmd
    assert str(ws / "nor") not in cmd


def test_nesting_follows_the_union_of_grants(tmp_path):
    """The law's reach at a path is the union of the grants covering it: an inner grant adds a
    mount only where it is wider, and two grants on one path give the wider bind."""
    root, home, ws = _world(tmp_path)
    (ws / "gov" / "sub").mkdir()
    inner_wider = run_grant_mounts({"memory_root": str(home), "granted_reach": (
        (str(ws / "gov"), True, "r"), (str(ws / "gov" / "sub"), True, "rwed"))})[0]
    assert inner_wider == [(str(ws / "gov"), "dir", "ro"), (str(ws / "gov" / "sub"), "dir", "rw")]
    inner_narrower = run_grant_mounts({"memory_root": str(home), "granted_reach": (
        (str(ws / "gov"), True), (str(ws / "gov" / "sub"), True, "r"))})[0]
    assert inner_narrower == [(str(ws / "gov"), "dir", "rw")]
    same_path = run_grant_mounts({"memory_root": str(home), "granted_reach": (
        (str(ws / "gov"), True, "r"), (str(ws / "gov"), True, "rwed"))})[0]
    assert same_path == [(str(ws / "gov"), "dir", "rw")]


def test_the_home_is_never_a_mount_and_a_grant_around_it_masks_it(tmp_path):
    root, home, ws = _world(tmp_path)
    inside = run_grant_mounts({"memory_root": str(home),
                               "granted_reach": ((str(home), True), (str(home / "scratch"), True))})
    assert inside == ([], [], False)
    around = run_grant_mounts({"memory_root": str(home), "granted_reach": ((str(root), True),)})
    assert around[0] == [(str(root), "dir", "rw")] and around[2] is True
    cmd = run_command({"path": "scratch/a.py"}, {"memory_root": str(home), "member": "test-being",
                                                  "granted_reach": ((str(root), True),)})
    assert f"--tmpfs {home} --remount-ro {home}" in cmd
    assert cmd.index(f"--bind {root} {root}") < cmd.index(f"--tmpfs {home}")


def test_system_paths_and_tmp_itself_are_not_mounted_and_nesting_collapses(tmp_path):
    root, home, ws = _world(tmp_path)
    reach = (("/usr/lib", True), ("/tmp", True), ("/", True), (str(ws), True), (str(ws / "gov"), True))
    mounts, skipped, _ = run_grant_mounts({"memory_root": str(home), "granted_reach": reach})
    assert mounts == [(str(ws), "dir", "rw")]
    assert {p for p, _ in skipped} == {"/usr/lib", "/tmp", "/"}


def test_the_line_is_the_same_whatever_order_the_grants_arrive_in(tmp_path):
    """The gate composes from the snapshot's grants and the dispatcher from the verdict's; the
    dispatcher refuses unless the two lines are byte-identical, so order must not matter."""
    root, home, ws = _world(tmp_path)
    args = {"path": "scratch/a.py"}
    base = {"memory_root": str(home), "member": "test-being"}
    a = run_command(args, {**base, "granted_reach": _reach(ws)})
    b = run_command(args, {**base, "granted_reach": tuple(reversed(_reach(ws)))})
    assert a == b and f"--ro-bind {ws / 'gov'} {ws / 'gov'}" in a and f"--bind {ws / 'rw'} {ws / 'rw'}" in a


def test_the_gate_side_hands_run_the_policy_grants_and_no_other_verb():
    c = B.BeingGateClient.__new__(B.BeingGateClient)
    c._policy_grants = lambda: (("/x",), (("/x", True, "r"),))
    assert c._compose_ctx("run")["granted_reach"] == (("/x", True, "r"),)
    assert "granted_reach" not in c._compose_ctx("search")
    assert "granted_reach" not in c._compose_ctx()


def test_grants_are_read_by_reference_on_every_compose(tmp_path):
    """dp: changed grants "automatically update in the box". Nothing is cached: the gate side
    re-reads the policy for each run's line, so a grant narrowed or revoked between two runs
    changes the second run's mounts with no restart."""
    root, home, ws = _world(tmp_path)
    c = B.BeingGateClient.__new__(B.BeingGateClient)
    c.memory_root = str(home); c.member_id = "test-being"; c.worktree = None
    policy = {"reach": ((str(ws / "rw"), True),)}
    c._policy_grants = lambda: ((), policy["reach"])

    def line():
        return run_command({"path": "scratch/a.py"}, c._compose_ctx("run"))

    first = line()
    assert f"--bind {ws / 'rw'} {ws / 'rw'}" in first
    policy["reach"] = ((str(ws / "rw"), True, "r"),)              # narrowed to read
    second = line()
    assert f"--ro-bind {ws / 'rw'} {ws / 'rw'}" in second and f" --bind {ws / 'rw'} " not in second
    policy["reach"] = ()                                           # revoked
    assert str(ws / "rw") not in line()


def test_granted_reach_passes_a_cores_modes_through_and_defaults_to_pairs():
    """_granted_reach is where the law's grants enter: a core that reports modes is carried
    through as triples, a core that does not stays pairs, which every consumer reads as rwed."""
    class Policy:
        scope = ("path:/a/**", "path:/b")
    with_modes = types.SimpleNamespace(_scope_roots_with_reach=lambda s, w: [("/a", True, "r"), ("/b", False, "rwed")])
    without = types.SimpleNamespace(_scope_roots_with_reach=lambda s, w: [("/a", True), ("/b", False)])
    got = B._granted_reach(with_modes, Policy(), "/ws")
    assert ("/a", True, "r") in got and ("/b", False, "rwed") in got
    assert set(B._granted_reach(without, Policy(), "/ws")) >= {("/a", True), ("/b", False)}


@needs_bwrap
def test_a_line_judged_without_the_grants_is_not_executed_with_them(tmp_path):
    root, home, ws = _world(tmp_path)
    (home / "scratch" / "a.py").write_text("print('ran')\n")
    d = _dispatcher(home, _reach(ws))
    d._verdict.command = run_command({"path": "scratch/a.py"},
                                     {"memory_root": str(home), "member": "test-being"})
    r = d._do_run(BeingIntent("run", {"path": "scratch/a.py"}))
    assert r.ok is False and "not the command this dispatcher" in r.error


# -- from inside the sandbox ------------------------------------------------------------------

_ATTEMPT = ("import os\n"
            "def attempt(name, fn):\n"
            "    try:\n"
            "        fn(); print(name + ': REACHED')\n"
            "    except OSError as e:\n"
            "        print(name + ': denied', type(e).__name__)\n")


@needs_bwrap
def test_a_read_only_or_write_without_delete_grant_supplies_no_write_from_inside(tmp_path):
    """Nova's HOLD on 76f079bf0: a run must never supply a write, a delete or a new file where
    the grant does not allow both writing and deleting. Every target here is writable on disk,
    so only the mount can be what refuses."""
    root, home, ws = _world(tmp_path)
    probes = []
    for name, target in (("gov", ws / "gov" / "closure.py"), ("wnod", ws / "wnod" / "w.txt")):
        probes += [
            f"attempt('{name}-create', lambda: open({str(target.parent / 'new.txt')!r}, 'w').write('x'))\n",
            f"attempt('{name}-overwrite', lambda: open({str(target)!r}, 'w').write('x'))\n",
            f"attempt('{name}-delete', lambda: os.remove({str(target)!r}))\n",
            f"attempt('{name}-chmod', lambda: os.chmod({str(target)!r}, 0o777))\n",
            f"attempt('{name}-mkdir', lambda: os.mkdir({str(target.parent / 'sub')!r}))\n"]
    (home / "scratch" / "probe.py").write_text(
        _ATTEMPT
        + f"print('granted-file:', open({str(ws / 'gov' / 'closure.py')!r}).read().strip())\n"
        + f"print('exact-file:', open({str(ws / 'one.txt')!r}).read().strip())\n"
        + f"attempt('file-append', lambda: open({str(ws / 'one.txt')!r}, 'a').write('x'))\n"
        + "".join(probes)
        + f"print('no-r:', os.path.exists({str(ws / 'nor' / 'n.txt')!r}))\n"
        + f"print('ungranted:', os.path.exists({str(ws / 'ungranted' / 'x.txt')!r}))\n"
        + f"print('exact-dir-content:', os.path.exists({str(ws / 'exactdir' / 'secret.txt')!r}))\n"
        + f"print('via-symlink:', os.path.exists({str(ws / 'link' / 'x.txt')!r}))\n"
        + f"print('home:', os.path.exists({str(home / 'journal.md')!r}))\n")
    targets = (ws / "gov" / "closure.py", ws / "wnod" / "w.txt", ws / "one.txt")
    before = {p: (p.read_bytes(), p.stat().st_mode) for p in targets}
    r = _dispatcher(home, _reach(ws))._do_run(BeingIntent("run", {"path": "scratch/probe.py"}))
    assert r.ok, r.error
    out = r.result["stdout"]
    assert "REACHED" not in out, out
    for line in ("granted-file: CLOSURE = 1", "exact-file: ONE", "file-append: denied",
                 "no-r: False", "ungranted: False", "exact-dir-content: False",
                 "via-symlink: False", "home: False"):
        assert line in out, out
    assert out.count(": denied") == 11, out
    assert {p: (p.read_bytes(), p.stat().st_mode) for p in targets} == before
    for d in ("gov", "wnod"):
        assert not (ws / d / "new.txt").exists() and not (ws / d / "sub").exists()
    assert not any(str(ws / d) in c for d in ("gov", "wnod")
                   for c in r.result.get("changed_in_your_grants", ()))
    note = r.result["note"]
    assert "READ-ONLY" in note and str(ws / "gov") in note and "os.path.exists() is False" in note
    assert "Not mounted" in note and str(ws / "nor") in note


@needs_bwrap
def test_an_rwed_grant_writes_from_inside_and_the_receipt_lists_it(tmp_path):
    root, home, ws = _world(tmp_path)
    (home / "scratch" / "probe.py").write_text(
        _ATTEMPT
        + f"open({str(ws / 'rw' / 'new.txt')!r}, 'w').write('from the run')\n"
        + f"os.remove({str(ws / 'rw' / 'keep.txt')!r})\n"
        + "print('wrote')\n")
    r = _dispatcher(home, _reach(ws))._do_run(BeingIntent("run", {"path": "scratch/probe.py"}))
    assert r.ok and "wrote" in r.result["stdout"], (r.error, r.result)
    assert (ws / "rw" / "new.txt").read_text() == "from the run"
    assert not (ws / "rw" / "keep.txt").exists()
    changed = r.result["changed_in_your_grants"]
    assert str(ws / "rw" / "new.txt") in changed and str(ws / "rw") in changed, changed
    assert "WRITABLE" in r.result["note"] and "except what it wrote through your grants" in r.result["note"]


@needs_bwrap
@pytest.mark.parametrize("around", [False, True])
def test_a_symlink_inside_a_grant_that_points_into_the_home_reaches_nothing(tmp_path, around):
    """Nova: home masking must not be bypassable by a symlink path. A link resolves inside the
    sandbox's namespace, where the home is either absent (grant beside it) or the empty mask
    (grant around it)."""
    root, home, ws = _world(tmp_path)
    os.symlink(str(home / "journal.md"), str(ws / "rw" / "tohome"))
    os.symlink(str(home), str(ws / "rw" / "homedir"))
    (home / "scratch" / "probe.py").write_text(
        "import os\n"
        f"print('link-file:', os.path.exists({str(ws / 'rw' / 'tohome')!r}))\n"
        f"print('link-dir:', os.path.isdir({str(ws / 'rw' / 'homedir')!r}) and "
        f"os.listdir({str(ws / 'rw' / 'homedir')!r}))\n"
        "try:\n"
        f"    open({str(ws / 'rw' / 'tohome')!r}, 'w').write('x'); print('link-write: REACHED')\n"
        "except OSError as e:\n"
        "    print('link-write: denied', type(e).__name__)\n")
    reach = (((str(root), True), (str(home / "scratch"), True)) if around
             else ((str(ws / "rw"), True),))
    r = _dispatcher(home, reach)._do_run(BeingIntent("run", {"path": "scratch/probe.py"}))
    assert r.ok, r.error
    out = r.result["stdout"]
    assert "link-file: False" in out and "REACHED" not in out, out
    assert ("link-dir: []" if around else "link-dir: False") in out, out
    assert (home / "journal.md").read_text() == "mine\n"


@needs_bwrap
def test_a_grant_that_contains_the_home_shows_it_empty_and_read_only(tmp_path):
    root, home, ws = _world(tmp_path)
    (home / "scratch" / "probe.py").write_text(
        "import os\n"
        f"print('home-listing:', sorted(os.listdir({str(home)!r})))\n"
        "try:\n"
        f"    open({str(home / 'journal.md')!r}, 'w').write('x'); print('home-write: REACHED')\n"
        "except OSError as e:\n"
        "    print('home-write: denied', type(e).__name__)\n"
        f"print('around:', os.path.exists({str(ws / 'gov' / 'closure.py')!r}))\n")
    r = _dispatcher(home, ((str(root), True),))._do_run(BeingIntent("run", {"path": "scratch/probe.py"}))
    assert r.ok, r.error
    out = r.result["stdout"]
    assert "home-listing: []" in out and "home-write: denied" in out and "around: True" in out, out
    assert (home / "journal.md").read_text() == "mine\n"


@needs_bwrap
def test_with_no_grants_the_run_is_what_it_was(tmp_path):
    root, home, ws = _world(tmp_path)
    (home / "scratch" / "a.py").write_text("import os\nprint(sorted(os.listdir('.')))\n")
    r = _dispatcher(home, ())._do_run(BeingIntent("run", {"path": "scratch/a.py"}))
    assert r.ok and "['a.py']" in r.result["stdout"]
    assert "changed_in_your_grants" not in r.result
    assert "no grant of yours reaches a path a run can mount" in r.result["note"]
