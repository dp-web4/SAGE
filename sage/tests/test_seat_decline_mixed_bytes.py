"""#806: a decline without --seq must not close a request made about bytes its reason never saw.

cbp-being 2026-11-21: requests 16946/16947 asked about sha daa818ef148c; the seat wrote "the file
has not changed"; the being's edit landed (a84d5fb1d8c2) and request 16948 followed eight seconds
before the decline posted. The bare decline closed all three."""
import hashlib
import importlib.util
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO))
spec = importlib.util.spec_from_file_location("seat_run_requests", REPO / "sage/scripts/seat_run_requests.py")
srr = importlib.util.module_from_spec(spec)
spec.loader.exec_module(srr)

REL = "scratch/list-inbox.py"


def _req(seq: int, data: bytes) -> dict:
    d = hashlib.sha256(data).hexdigest()[:12]
    return {"seq": seq, "text": f"{srr.MARKER} {REL}\nwhy: list it\n"
                                f"({len(data)} bytes, sha256:{d}; the seat decides whether to run it)"}


@pytest.fixture
def seat(monkeypatch, tmp_path):
    (tmp_path / "scratch").mkdir()
    posted, reqs = [], []
    monkeypatch.setattr(srr, "_say", lambda t: posted.append(t))
    monkeypatch.setattr(srr, "_instance", lambda: tmp_path)
    monkeypatch.setattr(srr, "_conv_id", lambda: "cbp-claude")
    monkeypatch.setattr(srr, "pending", lambda inst, cid: list(reqs))
    return tmp_path, posted, reqs


class A:
    path = REL; seq = None; cut_anyway = False; unrequested = False
    reason = "The file has not changed since the run at seq 16942."


OLD, NEW = b'INBOX = expanduser("~")\n', b'INBOX_DIR = "notes/inbox"\n'


def test_bare_decline_over_two_shas_refuses_and_names_each(seat):
    home, posted, reqs = seat
    (home / REL).write_bytes(NEW)
    reqs += [_req(16946, OLD), _req(16947, OLD), _req(16948, NEW)]
    with pytest.raises(SystemExit) as e:
        srr._decline(A())
    msg = str(e.value)
    assert posted == []
    assert "file changed between these requests" in msg and "Nothing was posted" in msg
    old_d, new_d = hashlib.sha256(OLD).hexdigest()[:12], hashlib.sha256(NEW).hexdigest()[:12]
    assert f"seq 16946: sha {old_d}" in msg and f"seq 16948: sha {new_d}" in msg
    assert f"now sha {new_d}" in msg


def test_seq_still_closes_only_the_named_old_requests(seat):
    home, posted, reqs = seat
    (home / REL).write_bytes(NEW)
    reqs += [_req(16946, OLD), _req(16947, OLD), _req(16948, NEW)]
    a = A(); a.seq = [16946, 16947]
    srr._decline(a)
    assert len(posted) == 1 and srr.answers_line([16946, 16947]) in posted[0]
    assert "16948" not in posted[0]


def test_bare_decline_of_one_request_about_bytes_the_file_no_longer_has_refuses(seat):
    # the being's edit landed but it has not re-asked yet: the reason was written about OLD
    home, posted, reqs = seat
    (home / REL).write_bytes(NEW)
    reqs += [_req(16946, OLD)]
    with pytest.raises(SystemExit) as e:
        srr._decline(A())
    assert posted == [] and "file changed" in str(e.value)


def test_bare_decline_of_re_asks_for_the_current_bytes_still_closes_them_all(seat):
    # the documented shortcut: a run of re-asks for unchanged bytes
    home, posted, reqs = seat
    (home / REL).write_bytes(OLD)
    reqs += [_req(16946, OLD), _req(16947, OLD)]
    srr._decline(A())
    assert len(posted) == 1 and srr.answers_line([16946, 16947]) in posted[0]


def test_untagged_or_retired_requests_are_not_judged(seat):
    # #721: the file is gone and the request carries no sha tag; nothing to compare
    home, posted, reqs = seat
    reqs += [{"seq": 15545, "text": f"{srr.MARKER} {REL}\nwhy: check it"}]
    srr._decline(A())
    assert len(posted) == 1


def test_retired_file_with_two_tagged_shas_still_refuses(seat):
    home, posted, reqs = seat
    reqs += [_req(1, OLD), _req(2, NEW)]
    with pytest.raises(SystemExit) as e:
        srr._decline(A())
    assert posted == [] and "gone from that path" in str(e.value)
