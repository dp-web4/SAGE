import json

from sage.tools import being_stream_census as bsc


def _write(p, events):
    p.write_text("".join(json.dumps(e) + "\n" for e in events) + "not json\n")


def test_counts_split_by_call_and_phase(tmp_path):
    _write(tmp_path / bsc.STREAM_FILE, [
        {"t": 1, "k": "beat"},
        {"t": 2, "k": "call", "turn": "explore"},
        {"t": 3, "k": "think", "s": "<|channel>thought\nThe user"},
        {"t": 4, "k": "think", "s": " wants me to act as `x-being`."},
        {"t": 5, "k": "tool", "name": "memory_write"},
        {"t": 6, "k": "call", "turn": "account"},
        {"t": 7, "k": "think", "s": "*   It must be in the user's own words."},
        {"t": 8, "k": "tool", "name": "memory_read"},
    ])
    rows = bsc.census(bsc.calls_of(bsc.stream_files([str(tmp_path)])))
    assert rows["explore"]["calls"] == 1 and rows["explore"]["user_wants"] == 1
    assert rows["explore"]["opens_user"] == 1 and rows["explore"]["act_as"] == 1
    assert rows["explore"]["reopen"] == 1 and rows["explore"]["mem_w"] == 1
    assert rows["account"]["users_words"] == 1 and rows["account"]["opens_user"] == 0
    assert rows["total"]["calls"] == 2 and rows["total"]["mem_r"] == 1
    assert rows["total"]["user_wants_per_call"] == 0.5


def test_since_drops_older_events(tmp_path):
    _write(tmp_path / bsc.STREAM_FILE, [{"t": 1, "k": "call", "turn": "explore"},
                                        {"t": 10, "k": "call", "turn": "reflect"}])
    rows = bsc.census(bsc.calls_of(bsc.stream_files([str(tmp_path)]), since=5))
    assert set(rows) == {"reflect", "total"}
