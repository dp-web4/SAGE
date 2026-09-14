"""SAGE #92: the being's state carries a MEASURED service line and its own ask counts, so a
stale journal claim ("my memory server has been offline ~6 hours") meets a current fact in the
same prompt, and a being that has asked one peer many times can see that it has."""
import json
import os
import socket
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))
from sage.gateway import heartbeat  # noqa: E402


def test_measure_service_reports_reachable_and_unreachable():
    srv = socket.socket(); srv.bind(("127.0.0.1", 0)); srv.listen(1)
    port = srv.getsockname()[1]
    try:
        line = heartbeat.measure_service("long-term memory", f"http://127.0.0.1:{port}/mcp")
        assert "reachable, connected in" in line and "NOT" not in line, line
    finally:
        srv.close()
    closed = socket.socket(); closed.bind(("127.0.0.1", 0)); dead = closed.getsockname()[1]; closed.close()
    line = heartbeat.measure_service("long-term memory", f"http://127.0.0.1:{dead}/mcp", timeout=1.0)
    assert "NOT reachable" in line, line


def test_own_state_carries_the_measured_line_ahead_of_the_journal_and_says_which_is_current(tmp_path):
    (tmp_path / "journal.md").write_text("2026-09-14 04:00 UTC: MCP server at 127.0.0.1:8010 offline ~6 hours\n")
    out = heartbeat.own_state(tmp_path, "", services="- long-term memory (membot) (127.0.0.1:8010): reachable, connected in 1 ms")
    i, j = out.find("## Your services, measured"), out.find("## journal.md")
    assert 0 <= i < j, "the measurement must come before the journal tail"
    assert "this line is current" in out


def test_recent_asks_block_counts_per_peer(tmp_path):
    now = time.time()
    rows = [{"t": now - 60 * k, "peer": "hub"} for k in (5, 35, 65)] + [{"t": now - 600, "peer": "legion"},
                                                                         {"t": now - 3 * 86400, "peer": "old"}]
    (tmp_path / "asks_sent.jsonl").write_text("".join(json.dumps(r) + "\n" for r in rows))
    block = heartbeat.recent_asks_block(tmp_path, now=now)
    assert "- hub: 3 ask(s) in the last 24 h, most recently 5 min ago" in block, block
    assert "- legion: 1 ask(s)" in block and "old" not in block
    assert "An ask is not an answer" in block
    assert heartbeat.recent_asks_block(tmp_path / "nowhere", now=now) == ""
