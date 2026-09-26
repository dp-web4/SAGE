"""The seat channel's header names THIS being's seat, not CBP's (a literal since #100)."""
from pathlib import Path

from sage.gateway import heartbeat as H


def _state(tmp_path, monkeypatch, seat):
    home = tmp_path / "home"
    (home / "notes").mkdir(parents=True)
    (home / "notes" / "from-the-seat.md").write_text("measured for you: the gate is up\n")
    if seat is None:
        monkeypatch.delenv("SAGE_SEAT", raising=False)
    else:
        monkeypatch.setenv("SAGE_SEAT", seat)
    return H.own_state(home)


def test_the_header_names_the_seat_from_sage_seat(tmp_path, monkeypatch):
    s = _state(tmp_path, monkeypatch, "legion-claude")
    assert "## From the seat (legion-claude), directly" in s
    assert "cbp-claude" not in s


def test_unset_it_says_your_seat_and_names_no_one(tmp_path, monkeypatch):
    s = _state(tmp_path, monkeypatch, None)
    assert "## From the seat (your seat), directly" in s
    assert "cbp-claude" not in s
