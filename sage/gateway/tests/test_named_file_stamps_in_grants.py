"""SAGE #396: a record write's "Files this names" stamp looks where the being can read, and a miss
says nothing.

cbp-being read "<x>.py was not found in your home" as "<x>.py does not exist" three times. The
third time (2026-10-26 17:40Z) the file was the gate core in its own governance grant, and the
being's next act was a write_note of a model-written gate core to that path."""
import os

from sage.gateway.being_gate_client import BeingIntent, GatewayVerdict
from sage.gateway.tests.test_being_self import _ALLOW, _disp


def _granted(tmp_path, modes="r"):
    d, root = _disp()
    gov = tmp_path / "ws" / "governance"
    (gov / "hestia" / "_shared").mkdir(parents=True)
    core = gov / "hestia" / "_shared" / "gate_core.py"
    core.write_text("x = 1\n")
    reach = GatewayVerdict("allow", granted=(str(root), str(gov)),
                           granted_reach=((str(root), True), (str(gov), True, modes)))
    return d, root, gov, core, reach


def test_a_file_in_a_grant_is_stamped_by_the_spelling_the_being_uses(tmp_path):
    d, root, gov, core, reach = _granted(tmp_path)
    for spelling in ("governance/hestia/_shared/gate_core.py", str(core)):
        env = d(BeingIntent("memory_write", {"path": "journal.md",
                                             "content": f"read {spelling} today"}), reach)
        assert env.ok, env.error
        assert f"{os.path.realpath(core)} (in your grant) was last changed at" in env.result, env.result
        assert "not found" not in env.result, env.result


def test_a_miss_says_nothing(tmp_path):
    d, root, gov, core, reach = _granted(tmp_path)
    env = d(BeingIntent("memory_write", {"path": "journal.md",
                                         "content": "see governance/hestia/_shared/nope.py and ghost.py"}), reach)
    assert env.ok and "Files this names" not in env.result, env.result


def test_a_file_outside_every_grant_is_never_stamped(tmp_path):
    d, root, gov, core, reach = _granted(tmp_path)
    other = tmp_path / "ws" / "private" / "k.py"
    other.parent.mkdir(parents=True)
    other.write_text("k = 1\n")
    env = d(BeingIntent("memory_write", {"path": "journal.md", "content": f"see {other}"}), reach)
    assert env.ok and "k.py" not in env.result, env.result


def test_a_grant_without_r_is_not_read_for_a_stamp(tmp_path):
    d, root, gov, core, reach = _granted(tmp_path, modes="w")
    env = d(BeingIntent("memory_write", {"path": "journal.md", "content": f"see {core}"}), reach)
    assert env.ok and "gate_core.py" not in env.result, env.result
