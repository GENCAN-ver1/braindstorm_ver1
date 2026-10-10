"""Explicit provider calls for Open Storm; no credentials or error bodies persisted."""
import json
import os
import shutil
import subprocess
import tempfile
from urllib.error import HTTPError, URLError
from urllib.parse import urlparse
from urllib.request import Request, HTTPRedirectHandler, build_opener


class _NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, request, response, code, message, headers, url):
        return None  # Never forward a bearer credential to a redirected endpoint.


def urlopen(request, timeout):
    return build_opener(_NoRedirect()).open(request, timeout=timeout)


class ProviderError(ValueError):
    pass


def parse_output(text):
    text = text.strip()
    if text.startswith('```') and text.endswith('```'):
        text = text.split('\n', 1)[1].rsplit('```', 1)[0]
    value = json.loads(text)
    if not isinstance(value, dict):
        raise ValueError('expected JSON object')
    return value


def invoke(config, prompt):
    if not isinstance(config, dict):
        raise ProviderError('provider configuration must be an object')
    if not config.get('enabled'):
        raise ProviderError('provider is disabled')
    timeout = config.get('timeout_seconds', 120)
    if type(timeout) not in (int, float) or not 0 < timeout <= 600:
        raise ProviderError('timeout must be between 0 and 600 seconds')
    try:
        if config.get('transport') == 'codex':
            return _codex(config, prompt, timeout)
        if config.get('transport') != 'chat_completions':
            raise ProviderError('unsupported transport')
        base = config.get('base_url')
        if not isinstance(base, str):
            raise ProviderError('configure an HTTPS base_url')
        base = base.rstrip('/')
        parsed = urlparse(base)
        if (parsed.scheme != 'https' or not parsed.hostname
                or parsed.username or parsed.password or parsed.query or parsed.fragment):
            raise ProviderError('configure an HTTPS base_url')
        model = config.get('model')
        if not isinstance(model, str) or not model.strip():
            raise ProviderError('configure the desired flagship model ID')
        env = config.get('credential_env', '')
        key = os.environ.get(env, '')
        if not key.strip():
            raise ProviderError('credential environment variable is not set: ' + env)
        options = config.get('options', {})
        if not isinstance(options, dict) or set(options) & {'model', 'messages', 'stream'}:
            raise ProviderError('invalid provider options')
        body = dict(options)
        body.update(model=model, stream=False, messages=[{'role': 'user', 'content': prompt}])
        endpoint = base if base.endswith('/chat/completions') else base + '/chat/completions'
        request = Request(endpoint, data=json.dumps(body).encode('utf-8'),
                          headers={'Authorization': 'Bearer ' + key, 'Content-Type': 'application/json'}, method='POST')
        with urlopen(request, timeout=timeout) as response:
            raw = response.read(4 * 1024 * 1024 + 1)
        if len(raw) > 4 * 1024 * 1024:
            raise ProviderError('response exceeds size limit')
        payload = json.loads(raw)
        output = parse_output(payload['choices'][0]['message']['content'])
        usage = payload.get('usage')
        normalized = {k: v for k, v in usage.items() if k in ('prompt_tokens', 'completion_tokens', 'total_tokens') and type(v) is int and v >= 0} if isinstance(usage, dict) else None
        return output, normalized
    except HTTPError as exc:
        raise ProviderError('provider HTTP status ' + str(exc.code)) from None
    except (URLError, TimeoutError, subprocess.TimeoutExpired):
        raise ProviderError('provider timeout or network failure; no automatic retry') from None
    except (OSError, UnicodeError, KeyError, IndexError, TypeError, json.JSONDecodeError):
        raise ProviderError('provider unavailable or invalid response') from None


def _codex(config, prompt, timeout):
    executable = config.get('executable') or shutil.which('codex')
    if not executable:
        raise ProviderError('Codex CLI not found')
    args = [executable, 'exec', '--ignore-user-config', '--ephemeral', '--json',
            '--sandbox', 'read-only', '--skip-git-repo-check',
            '-c', 'forced_login_method="chatgpt"', '-c', 'model_provider="openai"']
    if config.get('model'):
        args.extend(['--model', config['model']])
    args.append('-')
    env = dict(os.environ)
    for name in ('OPENAI_API_KEY', 'OPENAI_BASE_URL', 'CODEX_API_KEY'):
        env.pop(name, None)
    # Keep project rules, files and skills out of isolated role execution.
    with tempfile.TemporaryDirectory(prefix='open-storm-codex-') as work:
        result = subprocess.run(args, input=prompt, text=True, encoding='utf-8',
                                capture_output=True, timeout=timeout, env=env, shell=False, cwd=work)
    if result.returncode:
        raise ProviderError('Codex call failed; check ChatGPT login and model access')
    final_text, usage, completed = None, None, False
    for line in result.stdout.splitlines():
        event = json.loads(line)
        if event.get('type') in ('turn.failed', 'error'):
            raise ProviderError('Codex turn failed')
        item = event.get('item', {})
        if event.get('type') == 'item.completed' and item.get('type') == 'agent_message':
            final_text = item['text']
        if event.get('type') == 'turn.completed':
            usage = event.get('usage')
            completed = True
    if final_text is None or not completed:
        raise ProviderError('Codex returned no final JSON response')
    return parse_output(final_text), usage
