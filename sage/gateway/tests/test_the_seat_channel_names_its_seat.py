"""The seat channel's header names THIS being's seat, not CBP's (a literal since #100)."""
from sage.gateway import body, heartbeat as H


def _header(tmp_path, monkeypatch, seat):
    # The body block reads the LIVE daemon's metabolism, which on CBP legitimately says "the last
    # thing you felt came from cbp-claude" (cbp-claude on #231). Stub it: this test is about ONE
    # header line, and asserts on that line only.
    monkeypatch.setattr(body, "metabolism", lambda **k: {"live": False})
    home = tmp_path / "home"
    (home / "notes").mkdir(parents=True)
    (home / "notes" / "from-the-seat.md").write_text("measured for you: the gate is up\n")
    if seat is None:
        monkeypatch.delenv("SAGE_SEAT", raising=False)
    else:
        monkeypatch.setenv("SAGE_SEAT", seat)
    lines = [ln for ln in H.own_state(home).splitlines() if ln.startswith("## From the seat")]
    assert len(lines) == 1, lines
    return lines[0]


def test_the_header_names_the_seat_from_sage_seat(tmp_path, monkeypatch):
    h = _header(tmp_path, monkeypatch, "legion-claude")
    assert h.startswith("## From the seat (legion-claude), directly"), h


def test_unset_it_names_the_machine_and_admits_the_model_is_unknown(tmp_path, monkeypatch):
    """The same spelling the Seat trailer uses (sprout on #231): one name for one missing value."""
    import socket
    from sage.gateway.being_gate_client import pr_attribution, seat_name
    h = _header(tmp_path, monkeypatch, None)
    want = f"{socket.gethostname().split('.')[0].lower()}-unknown"
    assert seat_name() == want
    assert h.startswith(f"## From the seat ({want}), directly"), h
    assert f"Seat: {want}" in pr_attribution("b", "a", None)
    assert "cbp-claude" not in h


def test_the_run_request_seat_reads_its_own_conversation(monkeypatch):
    """seat_run_requests defaulted to the literal "cbp-claude" conversation on every machine."""
    from sage.scripts import seat_run_requests as S
    monkeypatch.delenv("SAGE_SEAT_CONV", raising=False)
    monkeypatch.setenv("SAGE_SEAT", "legion-claude")
    assert S._conv_id() == "legion-claude"
    monkeypatch.setenv("SAGE_SEAT_CONV", "explicit")
    assert S._conv_id() == "explicit", "an explicit conversation still wins"
