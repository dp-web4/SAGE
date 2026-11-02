"""The same wire examples are executed by Python and the Rust daemon's unit tests."""
import json
from pathlib import Path

import pytest

from sage.gateway.arousal import delivery_text


CASES = json.loads((Path(__file__).parent / "fixtures" / "wake_delivery.json").read_text())


@pytest.mark.parametrize("case", CASES, ids=lambda case: case["name"])
def test_delivery_evidence_contract(case):
    assert delivery_text(case["input"]) == case["expected"]
