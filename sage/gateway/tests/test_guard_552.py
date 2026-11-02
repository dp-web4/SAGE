"""SAGE #552: the governance record names are refused in every directory, not only in a recognised home,
so a being cannot plant identity.json (and choose its arbiter) where no home exists yet."""
import tempfile
from pathlib import Path

import pytest

from sage.gateway.being_gate_client import BeingIntent, GatewayVerdict
from sage.gateway.tests.test_being_self import _ALLOW, _disp


def _granted_empty_dir(root):
    other = Path(tempfile.mkdtemp(prefix="not-yet-a-home-"))
    reach = GatewayVerdict("allow", granted=(str(root), str(other)),
                           granted_reach=((str(root), True), (str(other), True)))
    return other, reach


@pytest.mark.parametrize("name", ["identity.json", "identity.sealed", "identity.attest.json",
                                  "instance.json", "identity.json.tmp", "instance.json.tmp",
                                  "Identity.json", "INSTANCE.JSON", "identity.JSON"])
def test_a_record_name_is_refused_where_no_home_exists_yet(name):
    d, root = _disp()
    other, reach = _granted_empty_dir(root)
    env = d(BeingIntent("memory_write", {"path": str(other / name),
                                         "content": '{"identity": {"machine": "elsewhere"}}'}), reach)
    assert not env.ok and "governance record" in env.error, env
    assert not (other / name).exists()
    (root / "notes").mkdir(exist_ok=True)
    env = d(BeingIntent("memory_write", {"path": f"notes/{name}", "content": "x"}), _ALLOW)
    assert not env.ok and "governance record" in env.error, env


def test_writing_about_identity_is_still_a_being_s_own():
    d, root = _disp()
    other, reach = _granted_empty_dir(root)
    (root / "notes").mkdir()
    assert d(BeingIntent("memory_write", {"path": "notes/identity.md", "content": "who I am"}), _ALLOW).ok
    assert d(BeingIntent("memory_write", {"path": str(other / "identity.md"), "content": "x"}), reach).ok
    assert d(BeingIntent("memory_write", {"path": "notes/identity-thoughts.json", "content": "{}"}), _ALLOW).ok
