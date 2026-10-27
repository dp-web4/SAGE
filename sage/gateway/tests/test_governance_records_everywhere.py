"""SAGE #552: a home's records are refused by name in every directory, not only in a home.

_looks_like_a_home sees a home only once its records exist. In a granted dir holding neither
identity.json nor instance.json, `memory_write identity.json` succeeded (cbp's probe on #551), so a
being could plant the record that later makes the dir a home, `machine` included (#541)."""
import pytest

from sage.gateway.being_gate_client import BeingIntent, GatewayVerdict
from sage.gateway.reference_f1a import _is_governance_record
from sage.gateway.tests.test_being_self import _disp


def _bare_grant(tmp_path):
    d, root = _disp()
    bare = tmp_path / "not-yet-a-home"
    bare.mkdir()
    reach = GatewayVerdict("allow", granted=(str(root), str(bare)),
                           granted_reach=((str(root), True), (str(bare), True)))
    return d, bare, reach


@pytest.mark.parametrize("name", ["identity.json", "identity.sealed", "identity.attest.json",
                                  "instance.json", "identity.sealed.tmp", "identity.sealed.v1",
                                  "identity.json.retired-2026-10-27", "Identity.json"])
def test_a_record_is_not_planted_where_no_home_is_yet(tmp_path, name):
    d, bare, reach = _bare_grant(tmp_path)
    env = d(BeingIntent("memory_write", {"path": str(bare / name),
                                         "content": '{"identity": {"machine": "mine"}}'}), reach)
    assert not env.ok and "governance record" in env.error, (name, env)
    assert not (bare / name).exists(), name


def test_a_record_is_not_planted_in_a_subdirectory_either(tmp_path):
    d, bare, reach = _bare_grant(tmp_path)
    (bare / "deep").mkdir()
    env = d(BeingIntent("memory_write", {"path": str(bare / "deep" / "instance.json"), "content": "{}"}), reach)
    assert not env.ok and "governance record" in env.error, env


def test_notes_about_identity_stay_writable_outside_a_home(tmp_path):
    # the broad `identity.` prefix stays tied to homes: elsewhere it would refuse ordinary notes
    d, bare, reach = _bare_grant(tmp_path)
    for name in ("identity.md", "identity.notes.txt", "my-identity.json"):
        env = d(BeingIntent("memory_write", {"path": str(bare / name), "content": "hi"}), reach)
        assert env.ok, (name, env.error)


def test_the_name_rule():
    assert _is_governance_record("identity.json")
    assert _is_governance_record("INSTANCE.JSON")
    assert _is_governance_record("identity.sealed.tmp")
    assert not _is_governance_record("identity.md")
    assert not _is_governance_record("instance.jsonl")
    assert not _is_governance_record("my-identity.json")
