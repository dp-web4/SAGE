"""run_census: the run box measured, and the being's own todo quoted beside it (dp, 2026-11-05)."""
import json
import os
import time
from datetime import datetime, timezone
from pathlib import Path

from sage.gateway import being_params, run_census as rc

BOX = {"python": "3.12.3", "executable": "/usr/bin/python3",
       "modules": {"numpy": "1.26.4", "imageio": "2.34.0", "torch": None, "pytest": None},
       "tools": {"uv": None, "pip": "/usr/bin/pip", "git": "/usr/bin/git"},
       "network": False, "resolv_conf": False, "usr_writable": False,
       "measured_at": "2026-11-05 10:14 UTC"}


def _fake(calls):
    def m(mods):
        calls.append(tuple(mods))
        return dict(BOX, modules={k: BOX["modules"].get(k) for k in mods}, ts=time.time())
    return m


def test_census_caches_and_remeasures_when_site_packages_change(tmp_path, monkeypatch):
    calls = []
    mods = ("numpy", "imageio")
    monkeypatch.setattr(rc, "_newest_site_mtime", lambda: 0.0)
    rc.census(tmp_path, modules=mods, measure_fn=_fake(calls))
    rc.census(tmp_path, modules=mods, measure_fn=_fake(calls))
    assert len(calls) == 1, "a fresh cache is read, not re-measured"
    # an install on the host touches site-packages after the cache was written
    monkeypatch.setattr(rc, "_newest_site_mtime", lambda: time.time() + 5)
    rc.census(tmp_path, modules=mods, measure_fn=_fake(calls))
    assert len(calls) == 2


def test_census_keeps_last_good_measurement_on_failure(tmp_path, monkeypatch):
    monkeypatch.setattr(rc, "_newest_site_mtime", lambda: 0.0)
    rc.census(tmp_path, modules=("numpy",), measure_fn=_fake([]))
    c = rc.census(tmp_path, modules=("numpy",), force=True,
                  measure_fn=lambda mods: {"error": "TimeoutExpired: probe"})
    assert c["modules"]["numpy"] == "1.26.4"
    assert "TimeoutExpired" in c["stale_because"]
    assert "last good measurement" in rc.render(c)


def test_render_says_what_the_box_has_and_why_dns_fails_there():
    out = rc.render(BOX)
    assert "imageio 2.34.0" in out and "These do not: torch, pytest" in out
    assert "not on PATH: uv" in out
    assert "says nothing about the host" in out and "/etc/resolv.conf is not in the box" in out
    assert "Installing inside the box cannot work" in out


def test_render_is_empty_for_an_error_census():
    assert rc.render({"error": "no bwrap run box on this machine"}) == ""


def test_todo_notes_quote_the_item_beside_the_measurement_most_specific_first():
    items = [("Verify DNS resolution is fixed", None),
             ("Install imageio in sandbox's virtual environment", None),
             ("Run `uv pip install imageio`", None),
             ("Write the SVD notes", None)]
    lines = rc.todo_notes(BOX, items)
    assert lines[0].startswith("## Your open todo items")
    body = lines[1:]
    assert len(body) == 3, "an item the census says nothing about is not quoted"
    assert "imageio imports in your box (2.34.0)" in body[0]          # module match ranks first
    assert body[0].startswith('- "Install imageio')
    assert "uv is not on PATH" in body[1]
    assert "pip is on PATH" not in body[1], "a present tool beside an install step is not offered"
    assert "DNS there cannot be fixed" in body[2]


def test_todo_notes_cap_and_count_the_rest():
    items = [(f"Reinstall uv attempt {i}", None) for i in range(9)]
    lines = rc.todo_notes(BOX, items, most=3)
    assert lines[-1] == "- … and 6 more open items that this measurement also answers."


def test_refusal_fold_counts_seat_declines_by_class_not_the_beings_turns(tmp_path):
    conv = tmp_path / "conversations"
    conv.mkdir()
    now = datetime(2026, 11, 5, 10, 0, tzinfo=timezone.utc)
    rows = [
        {"ts": "2026-11-05T07:03:17Z", "seq": 13709, "from": "cbp-claude",
         "text": "[request_run] I did not run scratch/fix-dns.py. It rewrites system network config, "
                 "only to let an installer fetch packages."},
        {"ts": "2026-11-05T06:32:51Z", "seq": 13700, "from": "cbp-claude",
         "text": "[request_run] I did not run scratch/install-uv-venv.py. Installing uv in a venv is still installing a package."},
        {"ts": "2026-11-05T06:30:45Z", "seq": 13697, "from": "cbp-being",
         "text": "[request_run] I did not run install uv (quoting the seat)"},
        {"ts": "2026-11-01T06:00:00Z", "seq": 13000, "from": "cbp-claude",
         "text": "[request_run] I did not run install-old.py, a package install."},
        {"ts": "2026-11-05T06:40:00Z", "seq": 13705, "from": "cbp-claude",
         "text": "[request_run] I ran scratch/test.py. exit code 0."},
    ]
    (conv / "cbp-claude.jsonl").write_text("\n".join(json.dumps(r) for r in rows) + "\n")
    line = rc.refusal_fold(tmp_path, "cbp-being", now=now)
    assert "1 that would change the host's network config (latest seq 13709)" in line
    assert "1 that would install packages (latest seq 13700)" in line


def test_param_is_operator_only_and_off_by_default(tmp_path):
    p = being_params.PARAMS["run_census"]
    assert p.default is False and p.self_tunable is False
    assert being_params.value(tmp_path, "run_census", False) is False


def test_blocks_fail_open(tmp_path):
    def boom(mods):
        raise RuntimeError("probe exploded")
    assert rc.blocks(tmp_path, [("x", None)], "b", measure_fn=boom) == ("", "")


def test_probe_runs_in_the_real_box_when_available():
    """Live: only where bwrap works. Asserts what the box is for, not which modules this host has."""
    import pytest
    from sage.gateway import being_gate_client as bgc
    if bgc.run_sandbox_kind() != "bwrap":
        pytest.skip("no bwrap here")
    c = rc.measure(("json", "no_such_module_xyz"), ("sh",))
    assert not c.get("error"), c
    assert c["modules"]["json"] and c["modules"]["no_such_module_xyz"] is None
    assert c["network"] is False, "the census box must have no network, like run's"
