"""The run note says what the being's home looks like inside the sandbox, and how to bring a file in.

cbp-being, 2026-11-27 15:39Z: under a grant that covers its home's parent, the home is masked with
an empty tmpfs. Its copy_image_full.py printed "Home dir exists: True" / "Contents of home: []"
while the note said the home "does not exist in there". It stored "permission denied" (nothing
printed that) and asked the seat twice to copy a home file "to /work", which is what run's `data`
does. The note never named `data`.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

from sage.gateway import being_gate_client as B  # noqa: E402
from sage.gateway.hestia_dispatch import _run_reach_note  # noqa: E402


def test_masked_home_is_said_to_be_an_empty_folder():
    note = _run_reach_note([("/ws/SAGE/sage", "dir", "ro")], [], mask_home=True)
    assert "EMPTY read-only folder" in note
    assert "your home included, does not exist" not in note
    assert "every file in it reads as absent" in note


def test_unmasked_home_keeps_the_absent_wording():
    note = _run_reach_note([], [], mask_home=False)
    assert "your home included, does not exist in there" in note
    assert "EMPTY" not in note


def test_note_names_data_as_the_way_in_either_way():
    for mask in (True, False):
        note = _run_reach_note([], [], mask_home=mask)
        assert "name it in run's data" in note and "copied into /work under its base name" in note


def test_a_grant_around_the_home_masks_it_and_the_note_follows(tmp_path):
    root = tmp_path / "ws"
    home = root / "inst" / "being"
    (home / "scratch").mkdir(parents=True)
    mounts, skipped, mask = B.run_grant_mounts(
        {"memory_root": str(home), "granted_reach": ((str(root), True),)})
    assert mask
    assert "EMPTY read-only folder" in _run_reach_note(list(mounts), list(skipped), mask_home=bool(mask))
