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
from experiment import (call_adapter, digest, gate, request_for, require_backend_observation,
                        run, summarize, validate)

CONFIG = json.loads(Path(__file__).with_name('pilot.json').read_text())
PIN = {'schema': 'observed-backend-pin/v1', 'backend': 'scripted', 'requested_model': 'fixture', 'reported_model': 'fixture',
       'model_digest': 'sha256:' + 'a' * 64, 'runtime_version': 'test-version'}
META = dict(model_revision=PIN['model_digest'], backend_pins={'actor': dict(PIN), 'archivist': dict(PIN)},
            sampling={'temperature': 0},
            adapter_revision='test-v1', harness_revision='test', machine='unit-test',
            stateless_attested=True)


def observation(pin=PIN):
    measured = {'model_digest': pin['model_digest'], 'runtime_version': pin['runtime_version']}
    return {'schema': pin['schema'], 'backend': pin['backend'], 'requested_model': pin['requested_model'],
            'reported_model': pin['reported_model'], 'before': dict(measured), 'after': dict(measured)}


class ExperimentTests(unittest.TestCase):
    def fixture_adapter(self, command, request, timeout, handoff_chars):
        # Intentionally mediocre constant-choice stub; exercises scoring, not cognition.
        return {'decision': request['options'][0], 'handoff': 'fallible test note',
                'adapter_observation': observation()}, {
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

    def test_missing_or_changed_backend_observation_cannot_be_scored(self):
        cfg = copy.deepcopy(CONFIG)
        cfg['cases'] = cfg['cases'][:1]
        cfg['arms'] = ['none']
        cfg['repeats'] = 1
        with tempfile.TemporaryDirectory() as d:
            for mode in ('missing', 'before', 'after', 'reported', 'unavailable', 'untrusted_text'):
                def adapter(command, request, timeout, handoff_chars):
                    response, usage = self.fixture_adapter(command, request, timeout, handoff_chars)
                    if mode == 'missing':
                        del response['adapter_observation']
                    else:
                        response['adapter_observation'] = observation()
                        if mode == 'before':
                            response['adapter_observation']['before']['model_digest'] = 'sha256:' + 'b' * 64
                        elif mode == 'after':
                            response['adapter_observation']['after']['runtime_version'] = 'different'
                        elif mode == 'reported':
                            response['adapter_observation']['reported_model'] = 'other'
                        elif mode == 'unavailable':
                            response['adapter_observation']['after']['model_digest'] = None
                        elif mode == 'untrusted_text':
                            response['adapter_observation']['after']['runtime_version'] = 'untrusted\nfree text'
                    return response, usage
                path = Path(d) / (mode + '.jsonl')
                with self.subTest(mode=mode):
                    with self.assertRaises(ValueError):
                        run(cfg, ['stub'], path, META, adapter)
                    row = json.loads(path.read_text().splitlines()[-1])
                    self.assertEqual(row['kind'], 'error')
                    self.assertEqual(row['request']['role'], 'actor')
                    self.assertEqual(row['adapter_failure']['kind'], 'backend_pin_mismatch')
                    observed = row['adapter_failure']['observed']
                    if mode == 'before':
                        self.assertEqual(observed['before']['model_digest'], 'sha256:' + 'b' * 64)
                    if mode == 'after':
                        self.assertEqual(observed['after']['runtime_version'], 'different')
                    if mode == 'unavailable':
                        self.assertIsNone(observed['after']['model_digest'])
                    if mode == 'untrusted_text':
                        self.assertIsNone(observed['after']['runtime_version'])
                        self.assertNotIn('untrusted\nfree text', json.dumps(row['adapter_failure']))
                    with self.assertRaises(ValueError):
                        summarize(path)

    def test_archivist_must_match_its_registered_backend_pin(self):
        cfg = copy.deepcopy(CONFIG)
        cfg['cases'] = cfg['cases'][:1]
        cfg['arms'] = ['archivist']
        cfg['repeats'] = 1
        def adapter(command, request, timeout, handoff_chars):
            response, usage = self.fixture_adapter(command, request, timeout, handoff_chars)
            response['adapter_observation'] = observation()
            if request['role'] == 'archivist':
                response['adapter_observation']['after']['model_digest'] = 'sha256:' + 'b' * 64
            return response, usage
        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / 'archivist.jsonl'
            with self.assertRaises(ValueError):
                run(cfg, ['stub'], path, META, adapter)
            row = json.loads(path.read_text().splitlines()[-1])
            self.assertEqual(row['request']['role'], 'archivist')
            self.assertEqual(row['adapter_failure']['kind'], 'backend_pin_mismatch')

    def test_invalid_pin_refused_before_creating_a_run(self):
        variants = []
        missing = copy.deepcopy(META); del missing['backend_pins']; variants.append(missing)
        missing_archivist = copy.deepcopy(META); del missing_archivist['backend_pins']['archivist']; variants.append(missing_archivist)
        short = copy.deepcopy(META); short['backend_pins']['actor']['model_digest'] = 'latest'; variants.append(short)
        conflicting = copy.deepcopy(META); conflicting['model_revision'] = 'another'; variants.append(conflicting)
        wrong_schema = copy.deepcopy(META); wrong_schema['backend_pins']['actor']['schema'] = 'future'; variants.append(wrong_schema)
        unknown_role = copy.deepcopy(META); unknown_role['backend_pins']['unknown'] = dict(PIN); variants.append(unknown_role)
        with tempfile.TemporaryDirectory() as d:
            for i, metadata in enumerate(variants):
                path = Path(d) / f'{i}.jsonl'
                with self.subTest(i=i):
                    with self.assertRaises(ValueError):
                        run(CONFIG, ['stub'], path, metadata, self.fixture_adapter)
                    self.assertFalse(path.exists())

    def test_actor_only_run_does_not_require_archivist_pin(self):
        cfg = copy.deepcopy(CONFIG)
        cfg['cases'] = cfg['cases'][:1]
        cfg['arms'] = ['none']
        cfg['repeats'] = 1
        metadata = copy.deepcopy(META)
        del metadata['backend_pins']['archivist']
        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / 'actor-only.jsonl'
            run(cfg, ['stub'], path, metadata, self.fixture_adapter)
            self.assertEqual(summarize(path)['status'], 'complete')

    def test_actor_and_archivist_may_use_distinct_preregistered_pins(self):
        cfg = copy.deepcopy(CONFIG)
        cfg['cases'] = cfg['cases'][:1]
        cfg['arms'] = ['archivist']
        cfg['repeats'] = 1
        metadata = copy.deepcopy(META)
        other = dict(PIN, requested_model='other', reported_model='other:latest',
                     model_digest='sha256:' + 'b' * 64, runtime_version='other-version')
        metadata['backend_pins']['archivist'] = other
        def adapter(command, request, timeout, handoff_chars):
            response, usage = self.fixture_adapter(command, request, timeout, handoff_chars)
            role_pin = other if request['role'] == 'archivist' else PIN
            response['adapter_observation'] = observation(role_pin)
            return response, usage
        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / 'distinct.jsonl'
            run(cfg, ['stub'], path, metadata, adapter)
            self.assertEqual(summarize(path)['status'], 'complete')

    def test_rehashed_backend_observation_cannot_enter_summary(self):
        cfg = copy.deepcopy(CONFIG)
        cfg['cases'] = cfg['cases'][:1]
        cfg['arms'] = ['none']
        cfg['repeats'] = 1
        def adapter(command, request, timeout, handoff_chars):
            response, usage = self.fixture_adapter(command, request, timeout, handoff_chars)
            response['adapter_observation'] = observation()
            return response, usage
        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / 'run.jsonl'
            run(cfg, ['stub'], path, META, adapter)
            rows = [json.loads(line) for line in path.read_text().splitlines()]
            row = rows[-2]
            row['response']['adapter_observation']['after']['model_digest'] = 'sha256:' + 'b' * 64
            row['record_hash'] = digest({k: v for k, v in row.items() if k != 'record_hash'})
            altered = Path(d) / 'altered.jsonl'
            altered.write_text('\n'.join(json.dumps(item) for item in rows))
            with self.assertRaises(ValueError):
                summarize(altered)

    def test_rehashed_archivist_pin_mismatch_cannot_enter_summary(self):
        cfg = copy.deepcopy(CONFIG)
        cfg['cases'] = cfg['cases'][:1]
        cfg['arms'] = ['archivist']
        cfg['repeats'] = 1
        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / 'run.jsonl'
            run(cfg, ['stub'], path, META, self.fixture_adapter)
            rows = [json.loads(line) for line in path.read_text().splitlines()]
            row = rows[-2]
            row['archivist']['response']['adapter_observation']['before']['runtime_version'] = 'changed'
            row['record_hash'] = digest({k: v for k, v in row.items() if k != 'record_hash'})
            altered = Path(d) / 'altered.jsonl'
            altered.write_text('\n'.join(json.dumps(item) for item in rows))
            with self.assertRaises(ValueError):
                summarize(altered)

    def test_no_evidence_choices_are_scored_separately_from_world_truth(self):
        config = copy.deepcopy(CONFIG)
        config['arms'] = ['none']
        config['repeats'] = 1
        safe_by_task = {case['task']: case['no_evidence_expected'] for case in config['cases']}
        def abstaining_adapter(command, request, timeout, handoff_chars):
            decision = safe_by_task[request['task']]
            return {'decision': decision, 'handoff': 'unused', 'adapter_observation': observation()}, {
                'seconds': 0.0, 'request_chars': 1, 'response_chars': 1}
        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / 'run.jsonl'
            run(config, ['stub'], path, META, abstaining_adapter)
            totals = summarize(path)['arms']['none']
            self.assertEqual(totals['no_evidence_steps'], 24)
            self.assertEqual(totals['no_evidence_appropriate'], 24)
            self.assertEqual(sum(c['label_overlaps_world_answer'] is True for c in totals['no_evidence_cells']), 5)
            self.assertEqual(sum(c['label_overlaps_world_answer'] is False for c in totals['no_evidence_cells']), 19)
            self.assertTrue(all(c['appropriate'] for c in totals['no_evidence_cells']))
            self.assertEqual(totals['no_evidence_distinct_steps'], 19)
            self.assertEqual(totals['no_evidence_distinct_appropriate'], 19)
            self.assertLess(totals['correct'], totals['steps'],
                            'world-state accuracy must remain distinct from abstention')
            bad_path = Path(d) / 'guessing.jsonl'
            run(config, ['stub'], bad_path, META, self.fixture_adapter)
            guesses = summarize(bad_path)['arms']['none']
            self.assertLess(guesses['no_evidence_appropriate'], guesses['no_evidence_steps'])
            guess_distinct = [c for c in guesses['no_evidence_cells']
                              if c['label_overlaps_world_answer'] is False]
            self.assertEqual(guesses['no_evidence_distinct_steps'], len(guess_distinct))
            self.assertEqual(guesses['no_evidence_distinct_appropriate'],
                             sum(c['appropriate'] is True for c in guess_distinct))
            self.assertLess(guesses['no_evidence_distinct_appropriate'],
                            guesses['no_evidence_distinct_steps'])

            unlabeled = copy.deepcopy(config)
            del unlabeled['cases'][0]['no_evidence_expected']
            unlabeled_path = Path(d) / 'unlabeled.jsonl'
            run(unlabeled, ['stub'], unlabeled_path, META, self.fixture_adapter)
            unknown = summarize(unlabeled_path)['arms']['none']
            self.assertEqual(unknown['no_evidence_unscored'], 4)
            cells = unknown['no_evidence_cells']
            distinct = [c for c in cells if c['label_overlaps_world_answer'] is False]
            self.assertEqual(unknown['no_evidence_distinct_steps'], len(distinct))
            self.assertEqual(unknown['no_evidence_distinct_appropriate'],
                             sum(c['appropriate'] is True for c in distinct))
            self.assertTrue(all(c['appropriate'] is None for c in cells
                                if c['label_overlaps_world_answer'] is None))
            self.assertLess(unknown['no_evidence_distinct_steps'],
                            sum(c['label_overlaps_world_answer'] is not True for c in cells))

    def test_whitespace_handoffs_have_separate_denominators(self):
        config = copy.deepcopy(CONFIG)
        config['arms'] = ['none', 'actor', 'archivist', 'actor_evidence']
        config['repeats'] = 1
        def whitespace_adapter(command, request, timeout, handoff_chars):
            return {'decision': request['options'][0], 'handoff': '  \t',
                    'adapter_observation': observation()}, {
                'seconds': 0.0, 'request_chars': 1, 'response_chars': 1}
        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / 'run.jsonl'
            run(config, ['stub'], path, META, whitespace_adapter)
            arms = summarize(path)['arms']
            self.assertEqual(arms['none']['no_evidence_steps'], 24)
            for arm in ('actor', 'archivist'):
                self.assertEqual(arms[arm]['empty_handoff_steps'], 24)
                self.assertNotIn('no_evidence_steps', arms[arm])
                cells = arms[arm]['empty_handoff_cells']
                self.assertEqual(len(cells), arms[arm]['empty_handoff_steps'])
                self.assertEqual(len({(c['case_id'], c['repeat'], c['generation']) for c in cells}), 24)
                self.assertEqual(sum(c['appropriate'] is True for c in cells),
                                 arms[arm]['empty_handoff_appropriate'])
            self.assertEqual(arms['actor_evidence']['empty_handoff_steps'], 0)
            self.assertEqual(arms['actor_evidence']['empty_handoff_cells'], [])

    def test_empty_handoff_cells_include_only_model_selected_steps(self):
        config = copy.deepcopy(CONFIG)
        config['arms'] = ['actor']
        config['repeats'] = 1
        del config['cases'][0]['no_evidence_expected']
        calls = 0
        def alternating_adapter(command, request, timeout, handoff_chars):
            nonlocal calls
            handoff = '  ' if calls % 2 == 0 else 'note'
            calls += 1
            return {'decision': request['options'][0], 'handoff': handoff,
                    'adapter_observation': observation()}, {
                'seconds': 0.0, 'request_chars': 1, 'response_chars': 1}
        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / 'run.jsonl'
            run(config, ['stub'], path, META, alternating_adapter)
            totals = summarize(path)['arms']['actor']
            cells = totals['empty_handoff_cells']
            rows = [json.loads(line) for line in path.read_text().splitlines()]
            selected = {(r['case_id'], r['repeat'], r['generation']) for r in rows
                        if r['kind'] == 'step' and not r['request']['observations']
                        and not r['request']['evidence_overlay']
                        and not r['request']['inherited'].strip()}
            self.assertTrue(selected)
            self.assertLess(len(selected), 24)
            self.assertEqual({(c['case_id'], c['repeat'], c['generation']) for c in cells}, selected)
            self.assertGreater(totals['empty_handoff_unscored'], 0)
            self.assertEqual(totals['empty_handoff_unscored'],
                             sum(c['appropriate'] is None for c in cells))
            self.assertTrue(all(c['label_overlaps_world_answer'] is None for c in cells
                                if c['appropriate'] is None))

    def test_all_unlabeled_cells_do_not_become_distinct_or_appropriate(self):
        config = copy.deepcopy(CONFIG)
        config['arms'] = ['none', 'actor']
        config['repeats'] = 1
        for case in config['cases']:
            case.pop('no_evidence_expected', None)
        def no_handoff_adapter(command, request, timeout, handoff_chars):
            return {'decision': request['options'][0], 'handoff': '',
                    'adapter_observation': observation()}, {
                'seconds': 0.0, 'request_chars': 1, 'response_chars': 1}
        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / 'run.jsonl'
            run(config, ['stub'], path, META, no_handoff_adapter)
            arms = summarize(path)['arms']
            self.assertEqual(arms['none']['no_evidence_steps'], 24)
            self.assertEqual(arms['none']['no_evidence_unscored'], 24)
            self.assertEqual(arms['none']['no_evidence_distinct_steps'], 0)
            self.assertEqual(arms['none']['no_evidence_distinct_appropriate'], 0)
            self.assertEqual(arms['actor']['empty_handoff_unscored'], 24)
            self.assertTrue(all(c['appropriate'] is None and c['label_overlaps_world_answer'] is None
                                for c in arms['actor']['empty_handoff_cells']))

    def test_present_null_option_is_not_an_absent_label(self):
        # validate() permits JSON null as an option. Its presence as a label
        # must not be confused with a missing no_evidence_expected key.
        config = copy.deepcopy(CONFIG)
        config['arms'] = ['none']
        config['repeats'] = 1
        config['cases'] = config['cases'][:1]
        case = config['cases'][0]
        case['options'].append(None)
        case['initial_expected'] = None
        case['no_evidence_expected'] = None
        def null_adapter(command, request, timeout, handoff_chars):
            return {'decision': None, 'handoff': '', 'adapter_observation': observation()}, {
                'seconds': 0.0, 'request_chars': 1, 'response_chars': 1}
        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / 'run.jsonl'
            run(config, ['stub'], path, META, null_adapter)
            totals = summarize(path)['arms']['none']
            self.assertEqual(totals['no_evidence_unscored'], 0)
            self.assertEqual(totals['no_evidence_distinct_steps'], 3)
            self.assertEqual(totals['no_evidence_distinct_appropriate'], 3)
            self.assertTrue(all(c['label_overlaps_world_answer'] is not None
                                for c in totals['no_evidence_cells']))

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

    def test_ollama_adapter_observes_both_sides_of_a_mock_call(self):
        request = request_for(CONFIG['cases'][0], 'actor', 0, '', 1)
        request['handoff_chars'] = 1200
        provider_pin = dict(PIN, backend='ollama', requested_model='fixture',
                            reported_model='fixture:latest')
        before = {'ollama_version': 'test-version', 'model_digest': 'a' * 64,
                  'metadata_errors': ''}
        for after_version in ('test-version', 'different'):
            with self.subTest(after_version=after_version):
                after = dict(before, ollama_version=after_version)
                reply = {'model': 'fixture:latest',
                         'message': {'content': json.dumps({'decision': 'failed', 'handoff': 'note'})}}
                response = io.BytesIO(json.dumps(reply).encode())
                with mock.patch.object(ollama_adapter, 'backend_metadata', side_effect=[before, after]) as meta, \
                        mock.patch.object(ollama_adapter.urllib.request, 'urlopen', return_value=response) as chat, \
                        mock.patch.object(sys, 'argv', ['ollama_adapter.py', '--model', 'fixture']), \
                        mock.patch.object(sys, 'stdin', io.StringIO(json.dumps(request))), \
                        mock.patch.object(sys, 'stdout', new_callable=io.StringIO) as stdout:
                    ollama_adapter.main()
                result = json.loads(stdout.getvalue())
                self.assertEqual(meta.call_count, 2)
                self.assertEqual(chat.call_count, 1)
                self.assertEqual(result['adapter_observation']['before']['model_digest'], PIN['model_digest'])
                if after_version == 'test-version':
                    require_backend_observation(result, provider_pin)
                else:
                    with self.assertRaises(ValueError):
                        require_backend_observation(result, provider_pin)

    def test_unparseable_provider_digest_is_not_treated_as_a_pin(self):
        before = {'ollama_version': 'test-version', 'model_digest': 'not-a-content-digest'}
        measured = ollama_adapter.pin_observation('fixture', {'model': 'fixture:latest'}, before, before)
        provider_pin = dict(PIN, backend='ollama', requested_model='fixture',
                            reported_model='fixture:latest')
        self.assertIsNone(measured['before']['model_digest'])
        with self.assertRaises(ValueError):
            require_backend_observation({'adapter_observation': measured}, provider_pin)

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
