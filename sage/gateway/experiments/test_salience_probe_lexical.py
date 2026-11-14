"""Synthetic controls only: they demonstrate overlap, not a retrieval benchmark."""
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

from sage.gateway.experiments import salience_probe_lexical_2026_11_02 as probe


class ProbeTests(unittest.TestCase):
    def test_synthetic_contradiction_and_deictic_control(self):
        payload = json.loads(probe.SYNTHETIC_FIXTURE.read_text())
        result = probe.probe(payload)
        self.assertEqual(result["results"][0]["total_hits"], 2)
        self.assertEqual({h["record_index"] for h in result["results"][0]["hits"]}, {0, 1})
        self.assertEqual(result["results"][1]["hits"], [])

    def test_untrusted_input_validation_and_bounds(self):
        for payload in (None, {}, {"records": [None], "queries": []},
                        {"records": [], "queries": [{"text": 5}]}):
            with self.subTest(payload=payload), self.assertRaises(ValueError):
                probe.probe(payload)
        with self.assertRaises(ValueError):
            probe.probe({"records": [], "queries": []}, threshold=float("nan"))
        with self.assertRaises(ValueError):
            probe.probe({"records": [], "queries": []}, limit=0)
        with self.assertRaises(ValueError):
            probe.probe({"records": [{"text": "x"}] * 1001,
                         "queries": [{"text": "x"}] * 100})

    def test_cli_explicit_input_does_not_print_input_text_or_identifiers(self):
        payload = {"records": [{"text": "canarysecret garden policy open", "id": "privateid"}],
                   "queries": [{"text": "canarysecret garden policy"}]}
        root = Path(__file__).resolve().parents[3]
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "fixture.json"
            path.write_text(json.dumps(payload))
            result = subprocess.run(
                [sys.executable, "-m", "sage.gateway.experiments.salience_probe_lexical_2026_11_02",
                 "--input", str(path)], cwd=root, text=True, capture_output=True,
                env={**os.environ, "PYTHONDONTWRITEBYTECODE": "1"}, check=True,
            )
        self.assertNotIn("canarysecret", result.stdout + result.stderr)
        self.assertNotIn("privateid", result.stdout + result.stderr)
        self.assertEqual(json.loads(result.stdout)["results"][0]["total_hits"], 1)

    def test_bad_or_oversize_input_fails_without_echoing_contents_or_path(self):
        root = Path(__file__).resolve().parents[3]
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "private-file.json"
            for raw in (b'{"bad": "canarysecret"', b"x" * (probe.MAX_INPUT_BYTES + 1)):
                path.write_bytes(raw)
                result = subprocess.run(
                    [sys.executable, "-m", "sage.gateway.experiments.salience_probe_lexical_2026_11_02",
                     "--input", str(path)], cwd=root, text=True, capture_output=True,
                    env={**os.environ, "PYTHONDONTWRITEBYTECODE": "1"},
                )
                self.assertEqual(result.returncode, 2)
                self.assertNotIn("canarysecret", result.stdout + result.stderr)
                self.assertNotIn(str(path), result.stdout + result.stderr)


if __name__ == "__main__":
    unittest.main()
