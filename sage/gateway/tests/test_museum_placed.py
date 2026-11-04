"""What the being places in its own museum/ folder is its choice, and is hung as written
(dp, 2026-11-04: "it's sprout's choice. it is its self expression"). Hermetic: publish is
replaced, so nothing touches git or the public wall."""
import json
import tempfile
from pathlib import Path

from sage.raising.scripts import museum_curator as mc


def _museum(objects=()):
    d = Path(tempfile.mkdtemp(prefix="museum-"))
    (d / "objects.json").write_text(json.dumps({"objects": list(objects)}))
    (d / "CURATOR.md").write_text("charter")
    return d


def _instance(files):
    inst = Path(tempfile.mkdtemp(prefix="inst-"))
    (inst / "museum").mkdir()
    (inst / "museum" / "README.md").write_text("# museum/\nthe seat's note")
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


def test_no_museum_on_this_machine_is_a_quiet_no_op(monkeypatch):
    monkeypatch.setattr(mc, "find_museum", lambda: None)
    assert mc.hang_placed(_instance({"a.md": "# A\nb"}), 1) == []


def test_a_long_placed_piece_is_checked_without_the_quadratic_dp(monkeypatch):
    text = "A lantern that lights only what you have forgotten. " * 400   # ~20 KB
    monkeypatch.setattr(mc, "_lcs_len", lambda a, b: (_ for _ in ()).throw(AssertionError("DP ran")))
    assert mc.verbatim_ratio(text, text) == 1.0
