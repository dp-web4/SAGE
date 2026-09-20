"""A renamed home leaves absolute paths to the OLD one in the being's own notes (Legion,
2026-09-19: legion-gemma3-12b -> legion-being). A write there must be refused AND the refusal
must name where the file lives now — the harness knows; a bare 'escapes your memory root'
would send the being hunting for a grant it does not need."""
import json
import pytest
from sage.gateway.reference_f1a import ReferenceF1aDispatcher


def _homes(tmp_path):
    old, new = tmp_path / "legion-gemma3-12b", tmp_path / "legion-being"
    (old / "notes").mkdir(parents=True); (new / "notes").mkdir(parents=True)
    (new / "instance.json").write_text(json.dumps(
        {"former_homes": [{"path": str(old), "moved": "2026-09-19"}]}))
    return old, new


def test_write_into_former_home_is_refused_and_names_the_new_path(tmp_path):
    old, new = _homes(tmp_path)
    d = ReferenceF1aDispatcher(str(new))
    with pytest.raises(ValueError) as e:
        d._safe_path(str(old / "notes" / "plan.md"), writing=True)
    msg = str(e.value)
    assert "FORMER home" in msg and str(new / "notes" / "plan.md") in msg


def test_unrelated_outside_path_keeps_the_ordinary_refusal(tmp_path):
    old, new = _homes(tmp_path)
    d = ReferenceF1aDispatcher(str(new))
    with pytest.raises(ValueError) as e:
        d._safe_path(str(tmp_path / "legion-gemma3-12b-sibling" / "x.md"), writing=True)
    assert "FORMER home" not in str(e.value), "a sibling sharing a string prefix is not the former home"


def test_no_former_homes_recorded_changes_nothing(tmp_path):
    new = tmp_path / "home"; new.mkdir()
    d = ReferenceF1aDispatcher(str(new))
    with pytest.raises(ValueError) as e:
        d._safe_path(str(tmp_path / "elsewhere" / "x.md"), writing=True)
    assert "FORMER home" not in str(e.value)
    assert d._safe_path("notes/x.md", writing=True) == new / "notes" / "x.md"
