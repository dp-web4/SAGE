"""SAGE #546: the #545 guard extended to the tune records and to any home a grant reaches."""
import json
import tempfile
from pathlib import Path

import pytest

from sage.gateway import being_params as bp
from sage.gateway import being_self as bs
from sage.gateway.being_gate_client import BeingIntent, GatewayVerdict
from sage.gateway.tests.test_being_self import _ALLOW, _disp


@pytest.mark.parametrize("name", list(bp.TUNE_WRITES))
def test_the_tune_records_are_written_only_by_tune(name):
    d, root = _disp()
    (root / bp.TUNE_LOG).write_text('{"name": "num_ctx"}\n')
    before = (root / bp.TUNE_LOG).read_bytes()
    for verb, args in (("memory_write", {"path": name, "content": "{}"}),
                       ("memory_edit", {"path": name, "start_line": 1, "end_line": 1, "content": "{}"})):
        env = d(BeingIntent(verb, dict(args)), _ALLOW)
        assert not env.ok and "only with tune" in env.error, (verb, name, env)
    assert (root / bp.TUNE_LOG).read_bytes() == before


def test_another_beings_records_are_not_writable_through_a_grant():
    d, root = _disp()
    other = Path(tempfile.mkdtemp(prefix="other-home-"))
    (other / "identity.json").write_text(json.dumps({"identity": {"machine": "elsewhere"}}) + "\n")
    (other / "instance.json").write_text("{}\n")
    (other / "notes").mkdir()
    reach = GatewayVerdict("allow", granted=(str(root), str(other)),
                           granted_reach=((str(root), True), (str(other), True)))
    for name in ("identity.json", "identity.sealed", "instance.json", bs.SELF_LOG, bp.TUNE_LOG):
        env = d(BeingIntent("memory_write", {"path": str(other / name), "content": "x"}), reach)
        assert not env.ok, (name, env)
    assert json.loads((other / "identity.json").read_text())["identity"]["machine"] == "elsewhere"
    # an ordinary file in that grant stays writable: the guard is about records, not the grant
    env = d(BeingIntent("memory_write", {"path": str(other / "notes" / "x.md"), "content": "hi"}), reach)
    assert env.ok, env.error


def test_a_listing_takes_no_lock_and_writes_nothing(tmp_path):
    ok, text, changed = bs.edit(tmp_path, None, None, "")
    assert ok and not changed and list(tmp_path.iterdir()) == []
