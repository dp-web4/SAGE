"""SAGE #544: the governance records in a being's home are not the being's to write, and the #541
follow-ups (an explicit `changed`, a capped render, a torn audit line)."""
import json
import os

import pytest

from sage.gateway import being_self as bs
from sage.gateway.being_gate_client import BeingIntent
from sage.gateway.tests.test_being_self import _ALLOW, _disp, _log
from sage.gateway.tests.test_hestia_dispatch import FakeMcp

_IDENT = {"identity": {"name": "sprout", "lct": "lct://sage:sprout:agent@raising", "machine": "sprout"},
          "anchor_type": "software", "trust_ceiling": 0.4}


def _gov_home():
    d, root = _disp()
    (root / "identity.json").write_text(json.dumps(_IDENT, indent=2) + "\n")
    (root / "instance.json").write_text(json.dumps({"machine": "sprout", "lct_id": "x"}, indent=2) + "\n")
    (root / "identity.sealed").write_text("sealed\n")
    (root / "identity.attest.json").write_text("{}\n")
    (root / "identity.sealed.v1").write_text("v1 original\n")
    (root / "identity.json.tmp").write_text("{}\n")
    (root / "identity.json.retired-20260922T065744Z").write_text("{}\n")
    (root / "notes").mkdir()
    os.symlink(root / "identity.json", root / "notes" / "me.json")
    return d, root


@pytest.mark.parametrize("name", ["identity.json", "instance.json", "identity.sealed", "identity.attest.json",
                                  "identity.sealed.v1", "identity.json.tmp",
                                  "identity.json.retired-20260922T065744Z", "identity.new"])
def test_no_being_verb_writes_a_governance_record_by_any_path(name):
    from sage.gateway.escalate import seat_for
    d, root = _gov_home()
    seat_before = seat_for("sprout-being", str(root))
    before = {p.name: p.read_bytes() for p in root.iterdir() if p.is_file() and p.name != ".home.lock"}
    forms = [name, str(root / name), os.path.join("notes", os.pardir, name), "./" + name]
    if name == "identity.json":
        forms.append("notes/me.json")                    # a symlink in its own notes/
    for path in forms:
        for verb, args in (("memory_write", {"path": path, "content": '"machine": "elsewhere"'}),
                           ("memory_edit", {"path": path, "start_line": 1, "end_line": 4,
                                            "content": json.dumps(dict(_IDENT, trust_ceiling=1.0))}),
                           ("retire_note", {"path": path, "reason": "a test reason"})):
            env = d(BeingIntent(verb, dict(args)), _ALLOW)
            assert not env.ok and "governance record" in env.error, (verb, path, env)
    after = {p.name: p.read_bytes() for p in root.iterdir() if p.is_file() and p.name != ".home.lock"}
    assert after == before
    ident = json.loads((root / "identity.json").read_text())
    assert (ident["identity"]["machine"], ident["identity"]["lct"], ident["anchor_type"],
            ident["trust_ceiling"]) == ("sprout", "lct://sage:sprout:agent@raising", "software", 0.4)
    assert seat_for("sprout-being", str(root)) == seat_before   # arbitration cannot be redirected


def test_a_governance_record_is_still_readable_and_trusted_python_still_writes_it():
    d, root = _gov_home()
    env = d(BeingIntent("memory_read", {"path": "identity.json"}), _ALLOW)
    assert env.ok and "trust_ceiling" in str(env.result)
    ident = json.loads((root / "identity.json").read_text())      # the raising pipeline's way
    ident["identity"]["session_count"] = 1
    (root / "identity.json").write_text(json.dumps(ident))
    assert json.loads((root / "identity.json").read_text())["identity"]["session_count"] == 1


def test_an_unchanged_edit_is_not_witnessed_and_says_so():
    d, root = _disp()
    args = {"field": "values", "text": "a test value", "why": "a test reason"}
    assert d(BeingIntent("identity_edit", dict(args)), _ALLOW).witness_id
    FakeMcp.calls = []
    env = d(BeingIntent("identity_edit", dict(args)), _ALLOW)
    assert env.ok and env.witness_id is None and "nothing changed" in env.result
    assert len(_log(root)) == 1
    assert bs.edit(root, "values", "a test value", "x")[2] is False
    assert bs.edit(root, None, None, "")[2] is False


def test_the_beat_shows_a_capped_field(tmp_path):
    bs.edit(tmp_path, "learned", "y" * bs.FIELD_MAX_CHARS, "a test reason")
    shown = bs.render(tmp_path)
    assert len(shown) < bs.RENDER_FIELD_CHARS + 200 and "shows it whole" in shown


def test_a_torn_log_line_does_not_swallow_the_next(tmp_path):
    bs.edit(tmp_path, "values", "one", "a")
    with open(tmp_path / bs.SELF_LOG, "a") as f:
        f.write('{"at": "torn')                          # a crash mid-append
    bs.edit(tmp_path, "values", "two", "b")
    last = (tmp_path / bs.SELF_LOG).read_text().splitlines()[-1]
    assert json.loads(last)["to"] == "two"
