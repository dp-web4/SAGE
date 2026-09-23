"""scripts/delegate_seat_for_being.sh, run against a fake `hestia` and fake unit control.

GPT, review of #180: a daemon restart drops every pending scope request, and the script must
make "nothing pending" a machine-checked precondition — pinned in both directions:
  renewal due + pending request  => no stop, no vault mutation;
  renewal due + zero pending     => stop / grant / start proceeds.
Plus: a daemon that cannot report the queue is refused, not read as empty; and expiry parsing
does not depend on GNU date.
"""
import os
import stat
import subprocess
import tempfile
import time

SCRIPT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "..",
                                      "scripts", "delegate_seat_for_being.sh"))

FAKE_HESTIA = r'''#!/bin/bash
# records every call; answers from env: FAKE_PENDING (json), FAKE_EXPIRES (delegate list line or empty)
echo "$*" >> "$FAKE_LOG"
case "$1 $2" in
  "delegate agent-id") echo "agent-id for $3: 11111111-2222-3333-4444-555555555555";;
  "delegate list") [ -n "$FAKE_EXPIRES" ] && echo "d-1 → agent=11111111-2222-3333-4444-555555555555 actions=[$FAKE_ACTION] expires=$FAKE_EXPIRES"; true;;
  "gate pending") echo "$FAKE_PENDING";;
  "scope arbitrate") echo "error: hestia.scope_request_unknown"; exit 1;;
  "delegate grant") echo "granted";;
  "witness onboard") echo "onboarded";;
esac
'''


def _run(tmp, pending, expires="", extra_env=None):
    hb = os.path.join(tmp, "hestia")
    with open(hb, "w") as f:
        f.write(FAKE_HESTIA)
    os.chmod(hb, os.stat(hb).st_mode | stat.S_IEXEC)
    pf = os.path.join(tmp, "pass")
    open(pf, "w").write("x\n")
    log = os.path.join(tmp, "calls.log")
    unit = os.path.join(tmp, "unit.log")
    env = dict(os.environ, HESTIA_BIN=hb, HESTIA_PASSPHRASE_FILE=pf, FAKE_LOG=log,
               FAKE_PENDING=pending, FAKE_EXPIRES=expires,
               FAKE_ACTION="scope.decide:test-being:/w/sage",
               SAGE_BEING="test-being", SAGE_ROOT="/w/sage", SEAT="test-seat",
               HESTIA_STOP=f"echo stop >> {unit}", HESTIA_START=f"echo start >> {unit}",
               RENEW_DAYS="7")
    env.update(extra_env or {})
    r = subprocess.run(["bash", SCRIPT], env=env, capture_output=True, text=True, timeout=60)
    calls = open(log).read() if os.path.exists(log) else ""
    units = open(unit).read() if os.path.exists(unit) else ""
    return r, calls, units


def test_pending_scope_request_from_any_member_blocks_the_stop_and_the_grant():
    tmp = tempfile.mkdtemp()
    pending = ('{"count": 0, "pending_scope_count": 1, "pending_scope_requests": '
               '[{"request_id": "scope-abc", "claimed_by": "cbp-being", "path": "/w/x"}]}')
    r, calls, units = _run(tmp, pending)
    assert r.returncode == 4, r.stdout + r.stderr
    assert "scope-abc (cbp-being)" in r.stdout and "not restarting" in r.stdout
    assert units == "", "no stop, no start"
    assert "delegate grant" not in calls and "witness onboard" not in calls, "no vault mutation"


def test_pending_gate_escalation_blocks_too():
    tmp = tempfile.mkdtemp()
    r, calls, units = _run(tmp, '{"count": 2, "pending_scope_count": 0, "pending_scope_requests": []}')
    assert r.returncode == 4 and units == "" and "delegate grant" not in calls


def test_zero_pending_proceeds_stop_grant_start_in_that_order():
    tmp = tempfile.mkdtemp()
    r, calls, units = _run(tmp, '{"count": 0, "pending_scope_count": 0, "pending_scope_requests": []}')
    assert r.returncode == 0, r.stdout + r.stderr
    assert units.split() == ["stop", "start"]
    lines = calls.splitlines()
    i_pend = next(i for i, l in enumerate(lines) if l.startswith("gate pending"))
    i_grant = next(i for i, l in enumerate(lines) if l.startswith("delegate grant"))
    assert i_pend < i_grant, "the check precedes the mutation"
    assert "--action scope.decide:test-being:/w/sage" in calls
    assert "verified" in r.stdout


def test_a_daemon_that_cannot_report_pending_is_refused_not_read_as_empty():
    tmp = tempfile.mkdtemp()
    r, calls, units = _run(tmp, '{"count": 0}')          # pre-#1109 daemon: no scope field
    assert r.returncode == 5, r.stdout + r.stderr
    assert "cannot prove the queue empty" in r.stdout
    assert units == "" and "delegate grant" not in calls
    r, calls, units = _run(tempfile.mkdtemp(), "not json at all")
    assert r.returncode == 5 and units == ""


def test_expiry_is_parsed_without_gnu_date_and_a_far_expiry_does_nothing():
    tmp = tempfile.mkdtemp()
    far = time.strftime("%Y-%m-%d %H:%M", time.gmtime(time.time() + 30 * 86400))
    r, calls, units = _run(tmp, '{"count": 0, "pending_scope_count": 0}', expires=far)
    assert r.returncode == 0 and "ok: test-seat may rule test-being" in r.stdout
    assert units == "" and "gate pending" not in calls, "covered: no check, no restart"
    near = time.strftime("%Y-%m-%d %H:%M:%S", time.gmtime(time.time() + 2 * 86400))
    r, calls, units = _run(tempfile.mkdtemp(), '{"count": 0, "pending_scope_count": 0}', expires=near)
    assert r.returncode == 0 and "renewing" in r.stdout and units.split() == ["stop", "start"]
    r, calls, units = _run(tempfile.mkdtemp(), '{"count": 0, "pending_scope_count": 0}', expires="yesterday-ish")
    assert r.returncode == 1 and "cannot parse expiry" in r.stdout and units == "", \
        "an unparseable expiry is not 'due'"
