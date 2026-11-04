"""What the being places in its own museum/ folder is its choice, and is hung as written
(dp, 2026-11-04: "it's sprout's choice. it is its self expression"). Hermetic: publish is
replaced, so nothing touches git or the public wall."""
import json
import os
import tempfile
from pathlib import Path

from sage.raising.scripts import museum_curator as mc


def _museum(objects=()):
    d = Path(tempfile.mkdtemp(prefix="museum-"))
    (d / "objects.json").write_text(json.dumps({"objects": list(objects)}))
    (d / "CURATOR.md").write_text("charter")
    return d


def _instance(files, since="0"):
    inst = Path(tempfile.mkdtemp(prefix="inst-"))
    (inst / "museum").mkdir()
    (inst / "museum" / "README.md").write_text("# museum/\nthe seat's note")
    if since is not None:
        (inst / "museum" / ".wall-since").write_text(since)
    for name, text in files.items():
        (inst / "museum" / name).write_text(text)
    return inst


def test_placed_reads_title_and_text_and_skips_the_note_empty_files_and_what_is_hung():
    museum = _museum([{"title": "Already Up", "text": "x"}])
    inst = _instance({
        "doorstep-umbrella.md": "# Doorstep Umbrella\n\nNo rain falls where the umbrella spreads.\n",
        "one-line.txt": "A jar that holds the hour before rain.",
        "blank.md": "   \n",
        "already.md": "# Already Up\nsomething else",
        "notes.json": "{}",
    })
    got = {p["name"]: (p["title"], p["text"]) for p in mc.placed(inst, museum)}
    assert got == {
        "doorstep-umbrella.md": ("Doorstep Umbrella", "No rain falls where the umbrella spreads."),
        "one-line.txt": ("A jar that holds the hour before rain.", "A jar that holds the hour before rain."),
    }
    assert mc.placed(Path(tempfile.mkdtemp()), museum) == []        # no folder, nothing placed


def test_an_upper_case_suffix_hangs_and_a_title_only_file_drops_its_hash():
    inst = _instance({"SHOUT.MD": "# Loud\nall caps name", "only-title.md": "# Just This\n"})
    got = {p["name"]: (p["title"], p["text"]) for p in mc.placed(inst, _museum())}
    assert got == {"SHOUT.MD": ("Loud", "all caps name"), "only-title.md": ("Just This", "Just This")}


def test_hang_placed_hangs_each_as_written_with_its_origin_and_no_judgment(monkeypatch):
    museum = _museum()
    inst = _instance({"a.md": "# A Door That Remembers\nIt opens only onto rooms you have left.",
                      "b.md": "# Static Creature\nIts eyes are two blank receipts."})
    calls = []
    monkeypatch.setattr(mc, "find_museum", lambda: museum)
    monkeypatch.setattr(mc, "publish", lambda **kw: calls.append(kw) or f"HUNG {kw['title']}")
    out = mc.hang_placed(inst, 900)
    assert out == ["HUNG A Door That Remembers", "HUNG Static Creature"]    # every piece, not one per session
    a = calls[0]
    assert a["sprout_text"] == a["text"]                                  # its words are the file
    assert a["origin"] == "placed by Sprout, museum/a.md" and "its choice" in a["why"]
    assert mc.verbatim_ratio(a["text"], a["sprout_text"]) == 1.0


def test_a_piece_placed_before_the_wall_note_stays_its_own_until_it_saves_it_again(monkeypatch):
    museum = _museum([{"title": "Already Up", "text": "x"}])
    inst = _instance({"old.md": "# Doorstep Umbrella\nNo rain falls where it spreads.",
                      "up.md": "# Already Up\nsomething else"}, since="2000000000")
    calls = []
    monkeypatch.setattr(mc, "find_museum", lambda: museum)
    monkeypatch.setattr(mc, "publish", lambda **kw: calls.append(kw) or f"HUNG {kw['title']}")
    out = mc.hang_placed(inst, 1)
    assert calls == []                                                   # placed under "nothing is published"
    assert any("museum/old.md was placed before" in s for s in out)      # held, not silently skipped
    assert any("museum/up.md" in s and "already on the wall" in s for s in out)
    os.utime(inst / "museum" / "old.md", (2000000001, 2000000001))       # the being saves it again
    assert mc.hang_placed(inst, 2)[-1] == "HUNG Doorstep Umbrella"


def test_without_the_wall_stamp_nothing_is_hung(monkeypatch):
    monkeypatch.setattr(mc, "find_museum", lambda: _museum())
    monkeypatch.setattr(mc, "publish", lambda **kw: (_ for _ in ()).throw(AssertionError("hung")))
    out = mc.hang_placed(_instance({"a.md": "# A\nb"}, since=None), 1)
    assert len(out) == 1 and out[0].startswith("not hung: museum/a.md")


def test_no_museum_on_this_machine_is_a_quiet_no_op(monkeypatch):
    monkeypatch.setattr(mc, "find_museum", lambda: None)
    assert mc.hang_placed(_instance({"a.md": "# A\nb"}), 1) == []


def test_a_long_placed_piece_is_checked_without_the_quadratic_dp(monkeypatch):
    text = "A lantern that lights only what you have forgotten. " * 400   # ~20 KB
    monkeypatch.setattr(mc, "_lcs_len", lambda a, b: (_ for _ in ()).throw(AssertionError("DP ran")))
    assert mc.verbatim_ratio(text, text) == 1.0


def test_a_checkout_that_bumps_an_old_pieces_mtime_does_not_hang_it(monkeypatch):
    from sage.gateway.museum_offer import WALL_BEFORE, file_sha256
    museum = _museum()
    inst = _instance({"old.md": "# Doorstep Umbrella\nNo rain falls where it spreads."}, since="1000")
    d = inst / "museum"
    (d / WALL_BEFORE).write_text(json.dumps({"old.md": file_sha256(d / "old.md")}))
    calls = []
    monkeypatch.setattr(mc, "find_museum", lambda: museum)
    monkeypatch.setattr(mc, "publish", lambda **kw: calls.append(kw) or f"HUNG {kw['title']}")
    os.utime(d / "old.md", (2000000001, 2000000001))                # a checkout, not the being
    out = mc.hang_placed(inst, 1)
    assert calls == [] and "museum/old.md was placed before" in out[0]
    (d / "old.md").write_text("# Doorstep Umbrella\nNo rain falls where it spreads. Ever.")
    (d / "new.md").write_text("# New\nmade after")
    assert mc.hang_placed(inst, 2) == ["HUNG New", "HUNG Doorstep Umbrella"]    # by name; a change hangs
