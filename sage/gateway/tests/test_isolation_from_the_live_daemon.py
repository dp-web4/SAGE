"""Gateway tests cannot reach the seat's live hestia daemon, even when the seat exports its endpoint.

GPT, review of SAGE #257: the first cut used `setdefault`, so an inherited HESTIA_ENDPOINT -- which a
seat exports as ordinary configuration -- still pointed every test at the real society, where
connecting mints the test's id as a member. This file starts each entry point with a LIVE-SHAPED
inherited endpoint and asserts it cannot be the one selected, and that the transport refuses the
live address. Each probe runs in a fresh subprocess and never opens a connection: the pytest setup
(conftest), and both test files that also run as plain scripts (loaded with runpy under a non-main
name, so their top level -- where isolation happens -- runs and their tests do not).

Run: python3 sage/gateway/tests/test_isolation_from_the_live_daemon.py   (or pytest)
"""
import json
import os
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
LIVE = "http://127.0.0.1:7711/mcp"
FAILS = []
# UNDER PYTEST A FAILED CHECK MUST FAIL THE TEST (GPT, review of SAGE #257: check() only appended
# to FAILS, which only the __main__ runner reads -- so under pytest every test here returned
# normally, whatever it found). _fail() raises unless the standalone runner has set STANDALONE,
# which it does so it can report every failure in one pass instead of stopping at the first.
STANDALONE = False


def _fail(msg):
    FAILS.append(msg)
    if not STANDALONE:
        raise AssertionError(msg)

PROBE = r"""
import json, os, runpy, sys, urllib.error, urllib.request
# THE TRANSPORT IS STUBBED BEFORE THE ENTRY POINT LOADS (GPT, review of #257: the first cut called
# the real urlopen, so the opt-in probe could reach a live daemon -- a 1 ms timeout does not stop a
# request from being sent). The stub records the URL and returns nothing; the isolation, if it
# installs, wraps THIS stub. So a guarded request raises before the stub is reached, an opt-in
# request reaches the stub, and no request in this process ever reaches a socket.
reached = []
def _stub(url, *a, **k):
    reached.append(url.full_url if isinstance(url, urllib.request.Request) else str(url))
    return None
urllib.request.urlopen = _stub
sys.path.insert(0, sys.argv[2]); sys.path.insert(0, sys.argv[3])
entry = sys.argv[1]
if entry == "conftest":
    # By PATH: the repo root has its own conftest.py, and `import conftest` found that one first
    # (the first run of this probe). This is the gateway conftest pytest loads for these tests.
    runpy.run_path(os.path.join(sys.argv[2], "conftest.py"), run_name="conftest")
else:
    runpy.run_path(entry, run_name="isolation_probe")
refused = False
try:
    urllib.request.urlopen(sys.argv[4])
except urllib.error.URLError as e:
    refused = "test isolation" in str(e.reason)
print(json.dumps({"endpoint": os.getenv("HESTIA_ENDPOINT"), "live_refused": refused,
                  "stub_reached": reached}))
"""


def check(name, got, want=True):
    if got != want:
        _fail(f"{name}: got {got!r}, want {want!r}")


def probe(entry, opt_in=False):
    env = dict(os.environ, HESTIA_ENDPOINT=LIVE)
    env.pop("SAGE_TEST_LIVE_HESTIA", None)
    if opt_in:
        env["SAGE_TEST_LIVE_HESTIA"] = "1"
    r = subprocess.run([sys.executable, "-c", PROBE, entry, str(HERE), str(ROOT), LIVE],
                       capture_output=True, text=True, env=env, timeout=120)
    if r.returncode != 0:
        _fail(f"{entry}: probe crashed: {r.stderr.strip()[-300:]}")
        return {}
    return json.loads(r.stdout.strip().splitlines()[-1])


ENTRIES = ["conftest",
           str(HERE / "test_patch_apply_is_governed.py"),
           str(HERE / "test_worktree_reaches_the_gate.py")]


def test_an_inherited_live_endpoint_is_never_the_one_selected():
    for entry in ENTRIES:
        name = Path(entry).name
        got = probe(entry)
        check(f"{name}: the inherited live endpoint is overwritten", got.get("endpoint") == LIVE, False)
        check(f"{name}: ...with the .invalid isolation host",
              "hestia-isolated-for-tests.invalid" in (got.get("endpoint") or ""), True)
        check(f"{name}: a request to the live daemon address is refused by the transport",
              got.get("live_refused"), True)
        check(f"{name}: ...before it reaches the transport at all", got.get("stub_reached"), [])


def test_only_the_explicit_opt_in_restores_a_real_daemon():
    """Verified against the STUB, never a real daemon: opted in, the request passes the guard and
    reaches the (stubbed) transport."""
    got = probe("conftest", opt_in=True)
    check("opt-in: the inherited endpoint is left alone", got.get("endpoint"), LIVE)
    check("opt-in: the request is not refused", got.get("live_refused"), False)
    check("opt-in: it reaches the transport -- the stub, not a socket", got.get("stub_reached"), [LIVE])


def test_the_guard_matches_only_the_live_address():
    sys.path.insert(0, str(HERE))
    import _isolate_hestia as iso
    ports = {7711}
    for url, want in (("http://127.0.0.1:7711/mcp", True), ("http://localhost:7711/x", True),
                      ("http://[::1]:7711/mcp", True), ("http://127.0.0.1:8760/health", False),
                      ("http://hub:8770/v1", False), ("http://10.0.0.5:7711/mcp", False)):
        check(f"guard({url})", iso.is_live_daemon_url(url, ports), want)


if __name__ == "__main__":
    STANDALONE = True
    for fn in (test_an_inherited_live_endpoint_is_never_the_one_selected,
               test_only_the_explicit_opt_in_restores_a_real_daemon,
               test_the_guard_matches_only_the_live_address):
        fn()
    for f in FAILS:
        print("FAIL", f)
    print(f"{'FAILED' if FAILS else 'ok'}: {len(FAILS)} failure(s)")
    sys.exit(1 if FAILS else 0)
