"""Reproducible Open Storm lifecycle acceptance; optional real subscription calls."""
import argparse
import contextlib
import io
import json
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from scripts.open_storm import main
from runtime.open_storm import Storm
from evals.version_fingerprint import compute_version_fingerprint


def run(live=False):
    cases = []
    with tempfile.TemporaryDirectory(prefix='storm-acceptance-') as work:
        root = Path(work)
        session = root / 'session.json'

        def command(name, args, expected=0):
            stream = io.StringIO()
            with contextlib.redirect_stdout(stream):
                code = main(args + ['--session', str(session)])
            if code != expected:
                raise RuntimeError(f'{name}: expected {expected}, got {code}: {stream.getvalue()}')
            cases.append({'case': name, 'status': 'PASS', 'return_code': code})
            return stream.getvalue()

        command('initialize_plain_topic', ['init', '--topic', '虚构读书小组如何分享书籍？'])
        original = session.read_bytes()
        command('refuse_overwrite', ['init', '--topic', 'another'], 2)
        assert session.read_bytes() == original
        command('custom_role', ['role', '--id', 'librarian', '--description', '图书维护与流转参与者'])
        command('independent_prompt', ['prepare', '--role', 'librarian'])
        supplied = root / 'host.json'
        supplied.write_text(json.dumps({'ideas': [{'text': '虚构共享书架'}, {'text': '虚构借阅时间互换'}]}), encoding='utf-8')
        command('host_import', ['import', '--role', 'librarian', '--input', str(supplied)])
        parents = [n['id'] for n in Storm.load(session).data['nodes']]
        for operation in ('combine', 'mutate', 'invert', 'stress'):
            command(operation + '_prompt', ['prepare', '--role', 'bank', '--operation', operation, '--parents', *parents])
        supplied.write_text(json.dumps({'questions': [{'text': '如果所有人只能交换时间会怎样？'}]}), encoding='utf-8')
        command('generative_question', ['import', '--role', 'affected', '--operation', 'question', '--input', str(supplied)])
        question = Storm.load(session).data['nodes'][-1]['id']
        command('unanswered_does_not_block', ['prepare', '--role', 'venture'])
        command('user_answer', ['answer', '--question', question, '--text', '这是待探索假设'])
        command('explicit_convergence', ['converge', '--select', *parents])
        command('return_to_exploration', ['explore'])
        config = root / 'providers.json'
        config.write_text(json.dumps({'providers': {'openai': {'enabled': live, 'transport': 'codex', 'timeout_seconds': 180}},
            'members': [{'id': 'subscription', 'provider': 'openai', 'role': 'outsider'}]}), encoding='utf-8')
        command('subscription_round' if live else 'disabled_provider_failure',
                ['round', '--config', str(config), '--members', 'subscription'], 0 if live else 1)
        restored = Storm.load(session)
        assert restored.data['events'][-1]['type'] in ('output', 'provider_call')
        command('resume_status', ['status'])
        output = root / 'export.md'
        command('export', ['export', '--output', str(output)])
        command('refuse_export_overwrite', ['export', '--output', str(output)], 2)
        assert 'USER_STATEMENT' in output.read_text(encoding='utf-8')
        usage = [e.get('usage') for e in restored.data['events'] if e.get('usage')]
    return {'result': 'PASS', 'scope': 'Open Storm lifecycle', 'live_subscription': live,
            'version_fingerprint': compute_version_fingerprint(ROOT / 'evals/version-inputs.json', project_root=ROOT).to_dict(),
            'external_api_providers': 'NOT_CONFIGURED', 'cases': cases, 'reported_usage': usage,
            'boundaries': ['Single writer; pending calls require manual review before retry.',
                           'Model flagship selection and four external providers are deployment acceptance items.',
                           'Structural acceptance does not establish creative quality.']}


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--live-codex', action='store_true')
    parser.add_argument('--report', required=True)
    args = parser.parse_args()
    try:
        report = run(args.live_codex)
    except Exception as exc:
        report = {'result': 'FAIL', 'error_type': type(exc).__name__, 'error': str(exc)}
    Path(args.report).write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n', encoding='utf-8', newline='\n')
    print(json.dumps(report, ensure_ascii=False, indent=2))
    raise SystemExit(0 if report['result'] == 'PASS' else 1)
