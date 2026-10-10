import json
import io
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from urllib.error import HTTPError

from runtime.open_storm import Storm, ROLES
from adapters.storm_provider import invoke, ProviderError
from scripts.open_storm import main


class OpenStormTests(unittest.TestCase):
    def test_session_save_recovers_windows_lock_and_preserves_old_on_failure(self):
        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / 'session.json'
            storm = Storm.create('X')
            storm.save(path)
            original = path.read_bytes()
            error = PermissionError('sharing violation')
            error.winerror = 32
            with patch('runtime.open_storm.os.replace', side_effect=[error, None]) as call:
                with patch('runtime.open_storm.time.sleep'):
                    storm.save(path)
                self.assertEqual(call.call_count, 2)
            # The mocked successful replace leaves a temp file, cleaned by save.
            with patch('runtime.open_storm.os.replace', side_effect=error):
                with patch('runtime.open_storm.time.sleep'):
                    with self.assertRaises(PermissionError):
                        storm.save(path)
            self.assertEqual(path.read_bytes(), original)
            self.assertEqual(list(Path(d).glob('.storm-*.tmp')), [])

    def test_redirect_cannot_forward_credential(self):
        from adapters.storm_provider import _NoRedirect
        self.assertIsNone(_NoRedirect().redirect_request(None, None, 302, '', {}, 'https://other.test'))

    def test_corrupt_session_rejected_without_overwrite(self):
        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / 'session.json'
            for data in ([], {'version': 2, 'nodes': []},
                         dict(Storm.create('X').data, nodes=[{'id': 'bad'}])):
                path.write_text(json.dumps(data), encoding='utf-8')
                original = path.read_bytes()
                with patch('scripts.open_storm.emit'):
                    self.assertEqual(main(['explore', '--session', str(path)]), 2)
                self.assertEqual(path.read_bytes(), original)

    def test_codex_commentary_and_incomplete_turn(self):
        events = [
            {'type': 'item.completed', 'item': {'type': 'agent_message', 'text': 'Thinking about directions'}},
            {'type': 'item.completed', 'item': {'type': 'agent_message', 'text': '{"ideas":[{"text":"A"}]}'}},
            {'type': 'turn.completed', 'usage': {'input_tokens': 5}},
        ]
        with patch('adapters.storm_provider.subprocess.run') as run:
            run.return_value.returncode = 0
            run.return_value.stdout = '\n'.join(json.dumps(e) for e in events)
            output, _ = invoke({'enabled': True, 'transport': 'codex'}, 'X')
            self.assertEqual(output['ideas'][0]['text'], 'A')
            run.return_value.stdout = json.dumps(events[1])
            with self.assertRaises(ProviderError):
                invoke({'enabled': True, 'transport': 'codex'}, 'X')

    def test_plain_topic_and_independent_prompts(self):
        s = Storm.create('模糊想法')
        self.assertEqual(s.data['mode'], 'explore')
        s.add_output('venture', 'expand', {'ideas': [{'text': '新机制'}]})
        prompt = s.prompt('bank', 'expand')
        self.assertNotIn('新机制', prompt)
        self.assertIn('模糊想法', prompt)

    def test_combine_requires_real_parents_and_preserves_lineage(self):
        s = Storm.create('融资')
        ids = s.add_output('venture', 'expand', {'ideas': [{'text': 'A'}, {'text': 'B'}]})
        self.assertIn('A', s.prompt('bank', 'combine', ids))
        result = s.add_output('bank', 'combine', {'ideas': [{'text': 'C'}]}, ids)
        self.assertEqual(s.data['nodes'][-1]['parents'], ids)
        self.assertEqual(len(result), 1)
        with self.assertRaises(ValueError):
            s.prompt('bank', 'combine', ['missing'])

    def test_atomic_invalid_output_and_deferred_judgment(self):
        s = Storm.create('X')
        with self.assertRaises(ValueError):
            s.add_output('bank', 'expand', {'ideas': [{'text': 'ok'}, {'text': ''}]})
        self.assertEqual(s.data['nodes'], [])
        with self.assertRaises(ValueError):
            s.add_output('bank', 'expand', {'ideas': [{'text': 'A', 'score': 9}]})

    def test_unanswered_questions_do_not_block_and_answer_branches(self):
        s = Storm.create('X')
        ids = s.add_output('affected', 'question', {'questions': [{'text': '谁承担损失？'}]})
        s.add_output('bank', 'expand', {'ideas': [{'text': '继续探索'}]})
        s.answer(ids[0], '可由多个参与方分担')
        self.assertEqual(s.data['nodes'][-1]['parents'], ids)
        self.assertEqual(s.data['nodes'][0]['status'], 'answered')

    def test_resume_and_explicit_convergence(self):
        s = Storm.create('X')
        ids = s.add_output('operator', 'expand', {'ideas': [{'text': 'A'}]})
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / 'session.json'
            s.save(p)
            restored = Storm.load(p)
            restored.converge(ids)
            self.assertEqual(restored.data['selection'], ids)
            self.assertEqual(restored.data['mode'], 'converge')
            self.assertIn('A', restored.export())

    def test_disabled_provider_never_calls(self):
        with patch('adapters.storm_provider.urlopen') as call:
            with self.assertRaises(ProviderError):
                invoke({'enabled': False}, 'X')
            call.assert_not_called()

    def test_missing_endpoint_is_config_error(self):
        with self.assertRaises(ProviderError):
            invoke({'enabled': True, 'transport': 'chat_completions', 'base_url': None}, 'X')

    def test_http_model_payload_and_usage(self):
        class Response:
            def __enter__(self): return self
            def __exit__(self, *args): pass
            def read(self, limit):
                return json.dumps({'choices': [{'message': {'content': '{"ideas":[{"text":"A"}]}'}}],
                                   'usage': {'prompt_tokens': 2, 'completion_tokens': 3, 'private': 'ignore'}}).encode()
        config = {'enabled': True, 'transport': 'chat_completions', 'base_url': 'https://example.test/v1',
                  'model': 'chosen-flagship', 'credential_env': 'STORM_TEST_KEY'}
        with patch.dict(os.environ, {'STORM_TEST_KEY': 'test-key'}):
            with patch('adapters.storm_provider.urlopen', return_value=Response()) as call:
                output, usage = invoke(config, 'prompt')
                request = call.call_args.args[0]
                self.assertEqual(request.full_url, 'https://example.test/v1/chat/completions')
                self.assertEqual(json.loads(request.data)['model'], 'chosen-flagship')
                self.assertEqual(output['ideas'][0]['text'], 'A')
                self.assertNotIn('private', usage)
            error = HTTPError('https://example.test', 401, 'raw secret', {}, io.BytesIO(b'test-key'))
            with patch('adapters.storm_provider.urlopen', side_effect=error):
                with self.assertRaises(ProviderError) as caught:
                    invoke(config, 'prompt')
                self.assertNotIn('test-key', str(caught.exception))
                self.assertNotIn('raw secret', str(caught.exception))

    def test_custom_role_can_prepare_and_init_refuses_overwrite(self):
        with tempfile.TemporaryDirectory() as d:
            path = str(Path(d) / 's.json')
            with patch('scripts.open_storm.emit') as output:
                self.assertEqual(main(['init', '--session', path, '--topic', 'X']), 0)
                original = Path(path).read_bytes()
                self.assertEqual(main(['init', '--session', path, '--topic', 'Y']), 2)
                self.assertEqual(Path(path).read_bytes(), original)
                self.assertEqual(main(['role', '--session', path, '--id', 'scientist', '--description', '科学家']), 0)
                self.assertEqual(main(['prepare', '--session', path, '--role', 'scientist']), 0)

    def test_partial_round_records_failure_and_keeps_independence(self):
        with tempfile.TemporaryDirectory() as d:
            session = Path(d) / 's.json'
            Storm.create('topic').save(session)
            config = Path(d) / 'config.json'
            config.write_text(json.dumps({'providers': {'a': {}, 'b': {}}, 'members': [
                {'id': 'a', 'provider': 'a', 'role': 'venture'},
                {'id': 'b', 'provider': 'b', 'role': 'bank'}]}))
            with patch('scripts.open_storm.invoke', side_effect=[({'ideas': [{'text': 'secret-peer-idea'}]}, None), ProviderError('offline')]) as call:
                with patch('scripts.open_storm.emit'):
                    code = main(['round', '--session', str(session), '--config', str(config), '--members', 'a', 'b'])
            self.assertEqual(code, 1)
            self.assertNotIn('secret-peer-idea', call.call_args_list[1].args[1])
            restored = Storm.load(session)
            self.assertEqual(len(restored.data['nodes']), 1)
            self.assertEqual(restored.data['events'][-1]['status'], 'failed')

    def test_subscription_uses_cli_and_no_api_environment(self):
        events = '\n'.join([json.dumps({'type': 'item.completed', 'item': {'type': 'agent_message', 'text': '{"ideas":[{"text":"A"}]}'}}), json.dumps({'type': 'turn.completed', 'usage': {'input_tokens': 5}})])
        with patch('adapters.storm_provider.subprocess.run') as run:
            run.return_value.returncode = 0
            run.return_value.stdout = events
            run.return_value.stderr = ''
            with patch.dict('os.environ', {'OPENAI_API_KEY': 'must-not-forward'}):
                result, usage = invoke({'enabled': True, 'transport': 'codex', 'timeout_seconds': 10}, 'X')
            self.assertEqual(result['ideas'][0]['text'], 'A')
            self.assertNotIn('OPENAI_API_KEY', run.call_args.kwargs['env'])
            self.assertIn('forced_login_method="chatgpt"', run.call_args.args[0])
            self.assertEqual(usage['input_tokens'], 5)


if __name__ == '__main__':
    unittest.main()
