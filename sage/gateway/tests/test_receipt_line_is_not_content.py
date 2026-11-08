"""The witness id must not render as the last line of a tool result's content.

cbp-being, 2026-11-07: a memory_read body ends in a newline, and the old renderer glued
"  (witnessed <id>)" to it, so the id read as the file's last line. The being copied it into
`old` in four memory_edit calls (each refused) and wrote it into its file twice.
"""
from sage.gateway.being_gate_client import ResultEnvelope

FILE_TEXT = "## Conclusion\n\nlarger gaps converge faster.\n"


def _last_content_line(msg: str) -> str:
    lines = [ln for ln in msg.split("\n") if ln.strip()]
    return lines[-1]


def test_ok_result_keeps_its_own_last_line_and_brackets_the_receipt():
    msg = ResultEnvelope(ok=True, result=FILE_TEXT, witness_id="ef77e0f0").to_tool_message()
    assert msg.startswith(FILE_TEXT)
    tail = msg[len(FILE_TEXT):]
    assert tail.lstrip("\n").startswith("[receipt ef77e0f0")
    assert tail.rstrip().endswith("]")
    assert "(witnessed" not in msg


def test_receipt_on_its_own_line_even_when_body_has_no_trailing_newline():
    msg = ResultEnvelope(ok=True, result="exit 0", witness_id="w1").to_tool_message()
    assert msg.split("\n")[0] == "exit 0"
    assert _last_content_line(msg).startswith("[receipt w1")


def test_failed_result_receipt_is_bracketed_too():
    msg = ResultEnvelope(ok=False, result={"why": "x"}, witness_id="w2").to_tool_message()
    assert msg.split("\n")[0].startswith("[failed — ")
    assert "\n[receipt w2" in msg


def test_no_witness_no_receipt_line():
    assert ResultEnvelope(ok=True, result="a\n").to_tool_message() == "a\n"
