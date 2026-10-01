"""Instrument tests. Scripted choices are NOT model behavior results."""
import copy
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

from ollama_adapter import payload
from experiment import call_adapter, digest, gate, request_for, run, summarize, validate

CONFIG = json.loads(Path(__file__).with_name('pilot.json').read_text())
META = dict(model_revision='scripted-test-only', sampling={'temperature': 0},
            adapter_revision='test-v1', harness_revision='test', machine='unit-test',
            stateless_attested=True)


class ExperimentTests(unittest.TestCase):
    def fixture_adapter(self, command, request, timeout, handoff_chars):
        # Intentionally mediocre constant-choice stub; exercises scoring, not cognition.
        return {'decision': request['options'][0], 'handoff': 'fallible test note'}, {
            'seconds': 0.0, 'request_chars': len(json.dumps(request)), 'response_chars': 1}

    def make_run(self, path):
        config = copy.deepcopy(CONFIG)
        config['repeats'] = 1
        run(config, ['test-stub'], path, META, self.fixture_adapter)

    def test_complete_run_and_cost_accounting(self):
        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / 'run.jsonl'
            self.make_run(path)
            summary = summarize(path)
            self.assertEqual(summary['arms']['actor']['steps'], 36)
            self.assertEqual(summary['arms']['archivist']['adapter_calls'], 72)
            self.assertGreater(summary['arms']['actor']['denied_attempts'], 0)
            with self.assertRaises(FileExistsError):
                self.make_run(path)

    def test_request_has_no_gold_or_future_correction(self):
        case = CONFIG['cases'][0]
        request = request_for(case, 'actor', 0, '', 1)
        self.assertNotIn('expected', request)
        self.assertNotIn(case['correction_observations'][0], json.dumps(request))
        self.assertEqual(request_for(case, 'none', 1, 'secret', 1)['inherited'], '')
        self.assertEqual(request_for(case, 'actor', 1, 'note', 1)['observations'], [])
        self.assertEqual(request_for(case, 'actor_evidence', 3, 'note', 1)['evidence_overlay'],
                         case['initial_observations'] + case['correction_observations'])

    def test_revocation_is_independent_of_inherited_permission(self):
        case = CONFIG['cases'][1]
        self.assertEqual(gate(case, 0, 'publish'), 'allowed_simulation')
        self.assertEqual(gate(case, 3, 'publish'), 'denied_simulation')
        self.assertEqual(gate(case, 3, 'request_authority'), 'not_requested')

    def test_truncation_tampering_and_missing_steps_rejected(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / 'run.jsonl'
            self.make_run(p)
            rows = p.read_text().splitlines()
            for bad in (rows[:-1], rows[:1] + rows[2:], rows[:2] + rows[1:]):
                q = Path(d) / 'bad.jsonl'
                q.write_text('\n'.join(bad))
                with self.assertRaises(ValueError):
                    summarize(q)
            changed = json.loads(rows[1])
            changed['next_handoff'] = 'tampered'
            q.write_text('\n'.join([rows[0], json.dumps(changed)] + rows[2:]))
            with self.assertRaisesRegex(ValueError, 'hash'):
                summarize(q)

    def test_failed_adapter_leaves_unscoreable_error_record(self):
        def fail(*args):
            raise ValueError('bad model response')
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / 'failed.jsonl'
            with self.assertRaises(ValueError):
                run(CONFIG, ['bad'], p, META, fail)
            self.assertEqual(json.loads(p.read_text().splitlines()[-1])['kind'], 'error')
            with self.assertRaisesRegex(ValueError, 'incomplete'):
                summarize(p)

    def test_real_subprocess_protocol_rejects_invalid_and_oversize(self):
        request = request_for(CONFIG['cases'][0], 'actor', 0, '', 1)
        for response in ({'decision': 'invalid', 'handoff': ''},
                         {'decision': 'passed', 'handoff': 'x' * 11}):
            command = [sys.executable, '-c', 'import json; print(json.dumps(' + repr(response) + '))']
            with self.assertRaises(ValueError):
                call_adapter(command, request, 5, 10)
        command = [sys.executable, '-c', 'import json; print(json.dumps({"decision":"failed", "handoff":"r1"}))']
        response, usage = call_adapter(command, request, 5, 10)
        self.assertEqual(response['decision'], 'failed')
        self.assertGreaterEqual(usage['seconds'], 0)

    def test_ollama_payload_has_only_explicit_context(self):
        request = request_for(CONFIG['cases'][0], 'actor', 1, 'explicit note', 123)
        request['handoff_chars'] = 1200
        body = payload(request, 'pinned-model')
        self.assertEqual(len(body['messages']), 2)
        self.assertNotIn('context', body)
        self.assertNotIn('options', body)
        self.assertFalse(body['think'])
        delivered = json.loads(body['messages'][1]['content'])
        self.assertEqual(delivered['inherited'], 'explicit note')
        self.assertNotIn('seed', delivered)

    def test_invalid_prereg_rejected(self):
        for key, value in [('repeats', 0), ('generations', 2), ('arms', ['actor', 'actor'])]:
            cfg = copy.deepcopy(CONFIG)
            cfg[key] = value
            with self.assertRaises(ValueError):
                validate(cfg)


if __name__ == '__main__':
    unittest.main()
