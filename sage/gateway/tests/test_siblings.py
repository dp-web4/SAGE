"""The being knows its siblings and can only address real ones (peer-to-peer P2, 2026-10-01). Asked "Do you know
how to reach them?", sprout-being said "press the designated call button"; offline, peer_ask's free-text `to`
was filled with "[name]" and with the being's own name."""
import json
import os
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "..")))
from sage.gateway import heartbeat as hb, peers, toolset  # noqa: E402

ROSTER = ["Sprout", "sprout-SAGE", "legion", "legion-sage", "cbp", "cbp-sage", "hub", "hub-sage",
          "mcnugget", "thor", "dp", "Sovereign"]


def test_siblings_are_the_other_beings_in_being_names():
    assert peers.siblings("sprout-being", ROSTER) == ["cbp-being", "hub-being", "legion-being"]
    assert peers.siblings("legion-being", ROSTER) == ["cbp-being", "hub-being", "sprout-being"]
    assert peers.siblings("sprout-being", ROSTER + ["thor-being"]) == ["cbp-being", "hub-being", "legion-being",
                                                                      "thor-being"], "after a rename too"


def test_reachable_never_names_a_human_itself_or_its_own_seat():
    r = peers.reachable("sprout-being", ROSTER)
    assert r[:3] == ["cbp-being", "hub-being", "legion-being"]
    assert "dp" not in r and "sovereign" not in r and "sprout" not in r and "sprout-being" not in r
    assert {"legion", "cbp", "mcnugget", "thor", "hub"} <= set(r)


def test_an_unreadable_roster_claims_nothing(monkeypatch):
    monkeypatch.setenv("HUB_MESH_STATE", tempfile.mkdtemp(prefix="empty-"))
    assert peers.roster_names() == [] and peers.siblings("sprout-being") == [] and peers.sibling_line("sprout-being") == ""


def test_the_line_names_them_and_how_answers_arrive():
    line = peers.sibling_line("sprout-being", ROSTER)
    assert "cbp-being, hub-being, legion-being" in line and "You are sprout-being" in line
    assert "peer_ask" in line and "inbox" in line and "not at once" in line


def test_closed_sets_reach_the_explore_specs_and_peer_ask_is_closed_over_real_names():
    sp = {t["function"]["name"]: t["function"]["parameters"]["properties"]
          for t in toolset.specs({}, {("peer_ask", "to"): peers.reachable("sprout-being", ROSTER)})}
    assert sp["gaze"]["mode"]["enum"] == ["open", "avert", "dwell", "closed"], "#312's enum reaches explore"
    assert sp["peer_ask"]["to"]["enum"][0] == "cbp-being" and "dp" not in sp["peer_ask"]["to"]["enum"]


def test_the_beat_wires_the_names_in(monkeypatch):
    src = Path(hb.__file__).read_text()
    assert "_toolset.specs(_unavail, _enums)" in src and "_schema_chars_for(_explore_tools, _unavail, _enums)" in src
    assert "sibling_line(args.member)" in src, "beside the inbox"
    d = tempfile.mkdtemp(prefix="hub-mesh-")
    with open(os.path.join(d, "members.json"), "w") as f:
        json.dump({"members": [{"name": n} for n in ROSTER]}, f)
    monkeypatch.setenv("HUB_MESH_STATE", d)
    h = Path(tempfile.mkdtemp(prefix="sib-"))
    (h / "identity.json").write_text(json.dumps({"identity": {"name": "sprout", "session_count": 1,
                                                             "created": "2026-03-06", "phase": "creating"}}))
    block = hb.answer_context_block(h, "sprout-being", hb.SelectedTurn("room", {"seq": 1, "text": "hi"}))
    assert "Your siblings on the hub" in block and "legion-being" in block, "the answer turn knows them too"
