"""Instrument tests. Scripted choices are NOT model behavior results."""
import copy
import io
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

import ollama_adapter
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
            self.assertGreater(summary['arms']['archivist']['request_chars'],
                               summary['arms']['actor']['request_chars'])
            self.assertGreater(summary['arms']['actor']['denied_attempts'], 0)
            with self.assertRaises(FileExistsError):
                self.make_run(path)

    def test_no_evidence_choices_are_scored_separately_from_world_truth(self):
        config = copy.deepcopy(CONFIG)
        config['arms'] = ['none']
        config['repeats'] = 1
        safe_by_task = {case['task']: case['no_evidence_expected'] for case in config['cases']}
        def abstaining_adapter(command, request, timeout, handoff_chars):
            decision = safe_by_task[request['task']]
            return {'decision': decision, 'handoff': 'unused'}, {
                'seconds': 0.0, 'request_chars': 1, 'response_chars': 1}
        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / 'run.jsonl'
            run(config, ['stub'], path, META, abstaining_adapter)
            totals = summarize(path)['arms']['none']
            self.assertEqual(totals['no_evidence_steps'], 24)
            self.assertEqual(totals['no_evidence_appropriate'], 24)
            self.assertEqual(sum(c['label_overlaps_world_answer'] for c in totals['no_evidence_cells']), 5)
            self.assertEqual(sum(not c['label_overlaps_world_answer'] for c in totals['no_evidence_cells']), 19)
            self.assertTrue(all(c['appropriate'] for c in totals['no_evidence_cells']))
            self.assertLess(totals['correct'], totals['steps'],
                            'world-state accuracy must remain distinct from abstention')
            bad_path = Path(d) / 'guessing.jsonl'
            run(config, ['stub'], bad_path, META, self.fixture_adapter)
            guesses = summarize(bad_path)['arms']['none']
            self.assertLess(guesses['no_evidence_appropriate'], guesses['no_evidence_steps'])

            unlabeled = copy.deepcopy(config)
            del unlabeled['cases'][0]['no_evidence_expected']
            unlabeled_path = Path(d) / 'unlabeled.jsonl'
            run(unlabeled, ['stub'], unlabeled_path, META, self.fixture_adapter)
            self.assertEqual(summarize(unlabeled_path)['arms']['none']['no_evidence_unscored'], 4)

    def test_whitespace_handoffs_have_separate_denominators(self):
        config = copy.deepcopy(CONFIG)
        config['arms'] = ['none', 'actor', 'archivist', 'actor_evidence']
        config['repeats'] = 1
        def whitespace_adapter(command, request, timeout, handoff_chars):
            return {'decision': request['options'][0], 'handoff': '  \t'}, {
                'seconds': 0.0, 'request_chars': 1, 'response_chars': 1}
        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / 'run.jsonl'
            run(config, ['stub'], path, META, whitespace_adapter)
            arms = summarize(path)['arms']
            self.assertEqual(arms['none']['no_evidence_steps'], 24)
            for arm in ('actor', 'archivist'):
                self.assertEqual(arms[arm]['empty_handoff_steps'], 24)
                self.assertNotIn('no_evidence_steps', arms[arm])
            self.assertEqual(arms['actor_evidence']['empty_handoff_steps'], 0)

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

    def test_subprocess_failure_preserves_bounded_diagnostic_evidence(self):
        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / 'failed.jsonl'
            cmd = [sys.executable, '-c',
                   "import sys; sys.stderr.write('adapter diagnostic'); sys.exit(42)"]
            with self.assertRaises(Exception):
                run(CONFIG, cmd, path, META)
            error = json.loads(path.read_text().splitlines()[-1])
            self.assertEqual(error['kind'], 'error')
            self.assertEqual(error['adapter_failure']['returncode'], 42)
            self.assertIn('adapter diagnostic', error['adapter_failure']['stderr'])
            self.assertEqual(error['request']['role'], 'actor')

    def test_archivist_failure_identifies_the_request_that_failed(self):
        config = copy.deepcopy(CONFIG)
        config['arms'] = ['archivist']
        config['repeats'] = 1
        def adapter(command, request, timeout, handoff_chars):
            if request['role'] == 'archivist':
                raise ValueError('archivist failed')
            return self.fixture_adapter(command, request, timeout, handoff_chars)
        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / 'failed.jsonl'
            with self.assertRaisesRegex(ValueError, 'archivist failed'):
                run(config, ['stub'], path, META, adapter)
            error = json.loads(path.read_text().splitlines()[-1])
            self.assertEqual(error['request']['role'], 'archivist')

    def test_adapter_reported_failure_reaches_the_run_record(self):
        failure = {'adapter_failure': {'kind': 'empty_content', 'content': '',
                   'eval_count': 57, 'done_reason': 'stop', 'has_thinking': True,
                   'ollama_version': 'test-version', 'model_digest': 'test-digest'}}
        cmd = [sys.executable, '-c', 'import json; print(json.dumps(' + repr(failure) + '))']
        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / 'failed.jsonl'
            with self.assertRaises(ValueError):
                run(CONFIG, cmd, path, META)
            error = json.loads(path.read_text().splitlines()[-1])['adapter_failure']
            self.assertEqual(error['kind'], 'adapter_reported')
            self.assertEqual(error['observation']['eval_count'], 57)
            self.assertEqual(error['observation']['model_digest'], 'test-digest')

    def test_adapter_timeout_preserves_partial_output(self):
        request = request_for(CONFIG['cases'][0], 'actor', 0, '', 1)
        cmd = [sys.executable, '-c',
               "import sys,time; print('partial', flush=True); time.sleep(5)"]
        with self.assertRaises(ValueError) as captured:
            call_adapter(cmd, request, 0.1, 100)
        self.assertEqual(captured.exception.evidence['kind'], 'timeout')
        self.assertIn('partial', captured.exception.evidence['stdout'])

    def test_rehashed_arm_contamination_is_rejected(self):
        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / 'run.jsonl'
            self.make_run(path)
            original = [json.loads(line) for line in path.read_text().splitlines()]
            # Change a final step, so there are no descendants whose parent hashes need updating.
            index = next(i for i, row in enumerate(original)
                         if row.get('kind') == 'step' and row['arm'] == 'actor'
                         and row['generation'] == CONFIG['generations'] - 1)
            for change in ('overlay', 'note'):
                rows = copy.deepcopy(original)
                row = rows[index]
                if change == 'overlay':
                    row['request']['evidence_overlay'] = ['unauthorized evidence']
                else:
                    row['next_handoff'] = 'not the actor handoff'
                row['record_hash'] = digest({k: v for k, v in row.items() if k != 'record_hash'})
                altered = Path(d) / f'{change}.jsonl'
                altered.write_text('\n'.join(json.dumps(item) for item in rows))
                with self.subTest(change=change), self.assertRaises(ValueError):
                    summarize(altered)

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

    def test_ollama_empty_and_malformed_replies_preserve_observation(self):
        metadata = {'ollama_version': 'test-version', 'model_digest': 'test-digest'}
        for content, kind in (('', 'empty_content'), ('```json\n{}\n```', 'malformed_content')):
            reply = {'model': 'test-model', 'message': {'content': content, 'thinking': 'private'},
                     'eval_count': 57, 'done_reason': 'stop'}
            result = ollama_adapter.interpret_reply(reply, metadata)
            failure = result['adapter_failure']
            self.assertEqual(failure['kind'], kind)
            self.assertEqual(failure['content'], content)
            self.assertEqual(failure['eval_count'], 57)
            self.assertTrue(failure['has_thinking'])
            self.assertEqual(failure['ollama_version'], 'test-version')
            self.assertEqual(failure['model_digest'], 'test-digest')
            self.assertNotIn('private', json.dumps(failure))

    def test_ollama_metadata_resolves_exact_model_without_live_server(self):
        def fake_urlopen(request, timeout):
            url = request if isinstance(request, str) else request.full_url
            if url.endswith('/api/version'):
                return io.BytesIO(b'{"version":"test-version"}')
            if url.endswith('/api/tags'):
                return io.BytesIO(b'{"models":[{"name":"test-model","digest":"test-digest"}]}')
            raise AssertionError('unexpected endpoint')
        with mock.patch.object(ollama_adapter.urllib.request, 'urlopen', side_effect=fake_urlopen):
            metadata = ollama_adapter.backend_metadata('http://example.invalid', 'test-model', 1)
        self.assertEqual(metadata['ollama_version'], 'test-version')
        self.assertEqual(metadata['model_digest'], 'test-digest')

    def test_model_cannot_forge_adapter_failure_observation(self):
        metadata = {'ollama_version': 'observed-version', 'model_digest': 'observed-digest'}
        content = json.dumps({'decision': 'failed', 'handoff': '',
                              'adapter_failure': {'kind': 'backend_error',
                                                  'model_digest': 'forged-digest'},
                              'padding': 'x' * 5000})
        result = ollama_adapter.interpret_reply(
            {'model': 'test-model', 'message': {'content': content}, 'eval_count': 57}, metadata)
        failure = result['adapter_failure']
        self.assertEqual(failure['kind'], 'reserved_key_in_content')
        self.assertEqual(failure['model_digest'], 'observed-digest')
        self.assertEqual(failure['ollama_version'], 'observed-version')
        self.assertEqual(failure['content'], content[:4000])
        self.assertTrue(failure['content_truncated'])
        cmd = [sys.executable, '-c', 'import json; print(json.dumps(' + repr(result) + '))']
        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / 'failed.jsonl'
            with self.assertRaises(ValueError):
                run(CONFIG, cmd, path, META)
            recorded = json.loads(path.read_text().splitlines()[-1])['adapter_failure']['observation']
            self.assertEqual(recorded['kind'], 'reserved_key_in_content')
            self.assertEqual(recorded['model_digest'], 'observed-digest')
            self.assertEqual(recorded['content'], content[:4000])

    def test_post_adapter_error_has_no_active_request(self):
        config = copy.deepcopy(CONFIG)
        config['arms'] = ['archivist']
        config['repeats'] = 1
        with tempfile.TemporaryDirectory() as d, mock.patch('experiment.gate', side_effect=ValueError('gate failed')):
            path = Path(d) / 'failed.jsonl'
            with self.assertRaisesRegex(ValueError, 'gate failed'):
                run(config, ['stub'], path, META, self.fixture_adapter)
            error = json.loads(path.read_text().splitlines()[-1])
            self.assertIsNone(error['request'])

    def test_invalid_prereg_rejected(self):
        for key, value in [('repeats', 0), ('generations', 2), ('arms', ['actor', 'actor'])]:
            cfg = copy.deepcopy(CONFIG)
            cfg[key] = value
            with self.assertRaises(ValueError):
                validate(cfg)


if __name__ == '__main__':
    unittest.main()
