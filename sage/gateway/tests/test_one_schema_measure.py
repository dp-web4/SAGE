"""The window fitter and the beat record measure the verb schemas ONCE, as actually offered.

Found 2026-10-04 on the first brief-descriptions beat: the specs offered were 17,012 chars, but a
second `_schema_chars_for(_explore_tools)` re-measured the FULL descriptions (25,516) and overwrote
the first, so the fitter budgeted verbs that were never sent and the record reported them.
"""
import inspect

from sage.gateway import heartbeat as hb


def test_one_measurement_in_main_and_it_is_the_offered_one():
    src = inspect.getsource(hb.main)
    assert src.count("_schema_measured = _schema_chars_for(") == 1
    assert "_schema_chars_for(_explore_tools)\n" not in src, "no bare full-description re-measure"
    assert "_config_check(instance, args.model, llm, _explore_tools, _schema_chars)" in src


def test_config_check_reports_the_number_it_is_given():
    import types
    llm = types.SimpleNamespace(num_ctx=24576)
    from pathlib import Path
    import tempfile
    c = hb._config_check(Path(tempfile.mkdtemp()), "m", llm, ["rest"], 12345)
    assert c["tool_schema_chars"] == 12345
