"""#834 S1.5: the cap drop-ins are well-formed and ordered, so installing them cannot silently cap nothing."""
import configparser
import re
from pathlib import Path

CAPS = Path(__file__).resolve().parents[1] / "systemd" / "caps"
_SIZE = re.compile(r"^(\d+)([KMG])$")


def _bytes(v: str) -> int:
    m = _SIZE.match(v)
    assert m, v
    return int(m.group(1)) * {"K": 2**10, "M": 2**20, "G": 2**30}[m.group(2)]


def _service(p: Path):
    c = configparser.ConfigParser(strict=True)
    c.optionxform = str
    c.read_string(p.read_text())
    assert c.sections() == ["Service"], p
    return c["Service"]


def test_every_cap_drop_in_is_a_service_section_with_high_below_max():
    files = sorted(CAPS.glob("*.caps.conf"))
    assert [f.name for f in files] == ["membot-sprout.caps.conf", "sage-daemon.caps.conf", "sage-heartbeat.caps.conf"]
    for f in files:
        s = _service(f)
        assert s["MemoryAccounting"] == "yes", f
        assert _bytes(s["MemoryHigh"]) < _bytes(s["MemoryMax"]), f
        assert int(s["TasksMax"]) >= 16, f
        assert "measured" in f.read_text(), f           # each file names where its numbers came from


def test_the_beat_cap_sits_above_its_measured_peak():
    s = _service(CAPS / "sage-heartbeat.caps.conf")
    assert _bytes(s["MemoryHigh"]) > 694 * 2**20      # the largest of 22 measured beats, 2026-11-28


def test_the_install_and_undo_lines_name_every_drop_in():
    readme = (CAPS / "README.md").read_text()
    for f in CAPS.glob("*.caps.conf"):
        unit = f.name[: -len(".caps.conf")]
        assert unit in readme.split("## Install")[1].split("## Check")[0], unit
        assert f"{unit}.service.d/caps.conf" in readme.split("## Undo")[1], unit
