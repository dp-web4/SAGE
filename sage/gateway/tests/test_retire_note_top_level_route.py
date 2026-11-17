"""retire_note refused on a top-level note names the route that reaches it (#742).

cbp-being, 2026-11-16: refused four times on the top-level xor-verification-summary.md, it wrote a
scratch/ copy of the same name, retired the copy, and told dp the file was retired; the top-level
note was still live. The refusal now says the file is unchanged, names memory_edit, and names a
same-named file under notes/ or scratch/ as a different file. The verb's reach is unchanged."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

from sage.gateway.being_gate_client import BeingIntent  # noqa: E402
from sage.gateway.tests.test_hestia_dispatch import _ALLOW, _disp  # noqa: E402

NAME = "xor-verification-summary.md"


def _home():
    d, root = _disp()
    home = Path(root)
    (home / NAME).write_text("# XOR\n\nXOR is **linearly separable**.\n")
    return d, home


def _retire(d, path):
    return d(BeingIntent("retire_note", {"path": path, "reason": "contradicts s649"}), _ALLOW)


def test_top_level_refusal_names_memory_edit_and_leaves_the_file():
    d, home = _home()
    env = _retire(d, NAME)
    assert not env.ok
    e = env.error
    assert "does not reach the top of your home" in e and f"'{NAME}' is still live and unchanged" in e, e
    assert "use memory_edit on it" in e, e
    assert "a copy into notes/ or scratch/ and retiring the copy leaves" in e, e
    assert (home / NAME).read_text().endswith("linearly separable**.\n")


def test_a_same_named_scratch_file_is_named_as_a_different_file():
    d, home = _home()
    (home / "scratch").mkdir(exist_ok=True)
    (home / "scratch" / NAME).write_text("a stand-in\n")
    e = _retire(d, NAME).error
    assert f"'scratch/{NAME}' is a different file with the same name; retiring it leaves '{NAME}' as it is." in e, e
    assert "a copy into notes/" not in e


def test_twins_in_both_trees_are_both_named():
    d, home = _home()
    for sub in ("notes", "scratch"):
        (home / sub).mkdir(exist_ok=True)
        (home / sub / NAME).write_text("x\n")
    e = _retire(d, NAME).error
    assert f"'notes/{NAME}' and 'scratch/{NAME}' are different files" in e and "retiring them" in e, e


def test_scratch_note_still_retires_and_other_refusals_are_unchanged():
    d, home = _home()
    (home / "scratch").mkdir(exist_ok=True)
    (home / "scratch" / NAME).write_text("a stand-in\n")
    assert _retire(d, f"scratch/{NAME}").ok
    (home / "deep" / "er").mkdir(parents=True)
    (home / "deep" / "er" / "n.md").write_text("x\n")
    e = _retire(d, "deep/er/n.md").error
    assert "is not directly inside your notes/ or scratch/" in e, e
