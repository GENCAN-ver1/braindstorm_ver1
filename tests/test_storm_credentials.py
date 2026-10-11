import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from adapters.storm_credentials import load_credentials
from adapters.storm_provider import credential
from runtime.open_storm import Storm
from scripts.open_storm import main


class CredentialTests(unittest.TestCase):
    def test_literal_keys_and_allowlist_without_environment_mutation(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / '.env'
            p.write_text('# comment\nKEY="literal$VALUE#suffix"\nOTHER=ignore\n', encoding='utf-8')
            original = dict(os.environ)
            self.assertEqual(load_credentials(p, {'KEY'}), {'KEY': 'literal$VALUE#suffix'})
            self.assertEqual(dict(os.environ), original)
            self.assertEqual(credential({'credential_env': 'KEY'}, {'KEY': 'local'}), 'local')

    def test_invalid_key_file_does_not_echo_values(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / '.env'
            for payload in (b'KEY=secret\nKEY=secret', b'KEY="secret', b'KEY=\xff', b'x' * 65537):
                p.write_bytes(payload)
                with self.assertRaises(ValueError) as error:
                    load_credentials(p, {'KEY'})
                self.assertNotIn('secret', str(error.exception))

    def test_host_init_does_not_read_credentials_or_call_provider(self):
        with tempfile.TemporaryDirectory() as d:
            with patch('scripts.open_storm.load_credentials') as read, patch('scripts.open_storm.invoke') as invoke:
                with patch('scripts.open_storm.emit'):
                    self.assertEqual(main(['init', '--session', str(Path(d)/'s.json'), '--topic', 'topic']), 0)
                read.assert_not_called()
                invoke.assert_not_called()

    def test_missing_key_blocks_all_calls_and_preserves_session(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            session = root/'s.json'
            Storm.create('topic').save(session)
            original = session.read_bytes()
            config = root/'config.json'
            config.write_text(json.dumps({'providers': {
                'a': {'enabled': True, 'transport': 'codex'},
                'b': {'enabled': True, 'transport': 'chat_completions', 'credential_env': 'MISSING_TEST_KEY'}},
                'members': [{'id':'a','provider':'a','role':'bank'}, {'id':'b','provider':'b','role':'venture'}]}))
            env = root/'.env';env.write_text('MISSING_TEST_KEY=\n')
            with patch.dict(os.environ, {}, clear=True), patch('scripts.open_storm.invoke') as invoke:
                with patch('scripts.open_storm.emit'):
                    self.assertEqual(main(['round','--session',str(session),'--config',str(config),
                                           '--env-file',str(env),'--members','a','b']), 2)
                invoke.assert_not_called()
            self.assertEqual(session.read_bytes(), original)

    def test_local_keys_only_reach_adapter_not_saved_state(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d); session = root/'s.json'; Storm.create('topic').save(session)
            config = root/'config.json'
            config.write_text(json.dumps({'providers': {'a': {'enabled': True, 'transport':'chat_completions',
                'credential_env':'KEY'}}, 'members':[{'id':'a','provider':'a','role':'bank'}]}))
            env = root/'.env';env.write_text('KEY=secret-canary\nOTHER=unused\n')
            with patch('scripts.open_storm.invoke',return_value=({'ideas':[{'text':'idea'}]},None)) as invoke:
                with patch('scripts.open_storm.emit'):
                    self.assertEqual(main(['round','--session',str(session),'--config',str(config),
                                           '--env-file',str(env),'--members','a']), 0)
                self.assertEqual(invoke.call_args.kwargs['credentials'], {'KEY':'secret-canary'})
            self.assertNotIn('secret-canary',session.read_text(encoding='utf-8'))
