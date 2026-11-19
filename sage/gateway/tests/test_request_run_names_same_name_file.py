"""request_run on a bare name whose file sits one directory over names where it is, as memory_read does.

Measured 2026-11-17 04:55Z on cbp-being: request_run 'mechanism-training-numpy.py' (the file lives in notes/)
answered only "does not exist", and the being told the seat the file was missing and might need recreating."""
from pathlib import Path

from sage.gateway import conversations as conv
from sage.gateway.being_gate_client import BeingIntent
from sage.gateway.tests.test_hestia_dispatch import _ALLOW, _disp


def _seat_home():
    d, root = _disp()
    home = Path(root)
    conv.create(home, "seat", title="seat", participants=["seat", "sprout-being"],
                writable_by=["seat", "sprout-being"])
    meta = conv.get_meta(home, "seat"); meta["notify"] = {"seat": "claude-code"}
    conv._write_meta(home, "seat", meta)
    (home / "notes").mkdir(exist_ok=True)
    return d, home


def test_a_bare_name_for_a_notes_file_names_the_notes_path():
    d, home = _seat_home()
    (home / "notes" / "mech.py").write_text("print('a')\n")
    r = d(BeingIntent("request_run", {"path": "mech.py", "why": "see the next error"}), _ALLOW)
    assert not r.ok
    assert "DOES exist at 'notes/mech.py'" in r.error, r.error
    assert 'request_run {"path": "notes/mech.py"}' in r.error, r.error
    assert "not missing" in r.error
    # nothing reached the seat thread
    assert not any("[request_run]" in (t.get("text") or "") for t in conv.recent(home, "seat", limit=5))


def test_two_same_name_files_are_listed_without_picking_one():
    d, home = _seat_home()
    (home / "notes" / "mech.py").write_text("print('a')\n")
    (home / "scratch").mkdir(exist_ok=True)
    (home / "scratch" / "mech.py").write_text("print('b')\n")
    r = d(BeingIntent("request_run", {"path": "mech.py", "why": "x"}), _ALLOW)
    assert not r.ok
    assert "2 files with that name exist" in r.error, r.error
    assert "'notes/mech.py'" in r.error and "'scratch/mech.py'" in r.error


def test_a_true_absence_still_reads_as_an_absence():
    d, home = _seat_home()
    r = d(BeingIntent("request_run", {"path": "nowhere.py", "why": "x"}), _ALLOW)
    assert not r.ok
    assert "This is an absence, not a refusal" in r.error
    assert "DOES exist" not in r.error
