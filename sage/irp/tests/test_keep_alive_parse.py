"""SAGE_OLLAMA_KEEP_ALIVE: the natural spelling of "pin it" must not break every generate.

Measured 2026-09-19 against ollama on Legion: keep_alive "-1" as a STRING is rejected
(`time: missing unit in duration "-1"`), while -1 as a number and "-1s" both pin. The host
setting arrives as a string, so a bare integer is converted to a number here."""
from sage.irp.adapters.model_adapter import _parse_keep_alive


def test_a_bare_integer_becomes_a_number_and_a_duration_stays_a_string():
    assert _parse_keep_alive("-1") == -1 and isinstance(_parse_keep_alive("-1"), int)
    assert _parse_keep_alive(" 300 ") == 300
    assert _parse_keep_alive("5m") == "5m"
    assert _parse_keep_alive("-1s") == "-1s"
