#!/usr/bin/env python3
"""Persistent open brainstorming: init, prepare, import, round, answer, converge, export."""
import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from runtime.open_storm import Storm, ROLES, OPERATIONS, now
from adapters.storm_provider import invoke, ProviderError


def emit(value):
    print(json.dumps(value, ensure_ascii=False, indent=2))


def read_json(path):
    return json.loads(Path(path).read_text(encoding='utf-8'))


def exclusive_write(path, text):
    with Path(path).open('x', encoding='utf-8') as stream:
        stream.write(text)


def parser():
    p = argparse.ArgumentParser(description=__doc__)
    subs = p.add_subparsers(dest='command', required=True)
    for command in ('init', 'prepare', 'import', 'round', 'answer', 'converge', 'explore', 'export', 'status', 'role'):
        c = subs.add_parser(command)
        c.add_argument('--session', required=True)
        if command == 'init':
            c.add_argument('--topic', required=True)
        if command in ('prepare', 'import', 'round'):
            c.add_argument('--operation', choices=list(OPERATIONS), default='expand')
            c.add_argument('--parents', nargs='*', default=[])
        if command in ('prepare', 'import'):
            c.add_argument('--role', required=True, help='Built-in or session-specific role ID')
        if command == 'import':
            c.add_argument('--input', required=True, help='JSON supplied by host Codex or another researcher')
        if command == 'round':
            c.add_argument('--config', required=True)
            c.add_argument('--members', nargs='+', required=True, help='Explicit member IDs to call')
        if command == 'answer':
            c.add_argument('--question', required=True)
            c.add_argument('--text', required=True)
        if command == 'converge':
            c.add_argument('--select', nargs='+', required=True)
        if command == 'export':
            c.add_argument('--output', help='New Markdown file, otherwise stdout')
        if command == 'role':
            c.add_argument('--id', required=True)
            c.add_argument('--description', required=True)
    return p


def main(argv=None):
    args = parser().parse_args(argv)
    path = Path(args.session)
    try:
        if args.command == 'init':
            path.parent.mkdir(parents=True, exist_ok=True)
            s = Storm.create(args.topic)
            exclusive_write(path, json.dumps(s.data, ensure_ascii=False, indent=2))
            emit({'session': str(path), 'id': s.data['id'], 'mode': 'explore'})
            return 0
        s = Storm.load(path)
        if args.command == 'prepare':
            emit({'role': args.role, 'operation': args.operation,
                  'parents': args.parents, 'prompt': s.prompt(args.role, args.operation, args.parents)})
            return 0
        if args.command == 'export':
            if args.output:
                exclusive_write(args.output, s.export())
                emit({'output': args.output})
            else:
                print(s.export())
            return 0
        if args.command == 'status':
            emit(s.data)
            return 0
        if args.command == 'import':
            ids = s.add_output(args.role, args.operation, read_json(args.input), args.parents)
            result = {'added': ids}
        elif args.command == 'answer':
            result = {'added': s.answer(args.question, args.text)}
        elif args.command == 'converge':
            s.converge(args.select)
            result = {'mode': 'converge', 'selected': args.select, 'approved': False}
        elif args.command == 'explore':
            s.data['mode'] = 'explore'
            s.data['events'].append({'type': 'return_to_exploration', 'time': now()})
            result = {'mode': 'explore'}
        elif args.command == 'role':
            if not args.id.strip() or not args.description.strip() or args.id in s.data['roles']:
                raise ValueError('new role needs a unique ID and non-empty description')
            s.data['roles'][args.id] = args.description
            result = {'role': args.id}
        else:
            config = read_json(args.config)
            if (not isinstance(config, dict) or not isinstance(config.get('providers'), dict)
                    or not isinstance(config.get('members'), list)
                    or any(not isinstance(m, dict) for m in config['members'])):
                raise ValueError('configuration needs providers object and members array')
            if len(args.members) != len(set(args.members)):
                raise ValueError('member IDs must be unique')
            limit = config.get('max_calls_per_round', 5)
            if type(limit) is not int or not 1 <= limit <= 32 or len(args.members) > limit:
                raise ValueError('round exceeds configured call limit')
            members = {m['id']: m for m in config['members']}
            if len(members) != len(config['members']):
                raise ValueError('configured member IDs must be unique')
            # Snapshot every prompt before any member result is committed.
            calls = []
            for member_id in args.members:
                member = members[member_id]
                provider = config['providers'][member['provider']]
                role = member['role']
                calls.append((member_id, member, provider, s.prompt(role, args.operation, args.parents)))
            round_id = __import__('uuid').uuid4().hex
            results = []
            for member_id, member, provider, prompt in calls:
                event = {'time': now(), 'type': 'provider_call', 'round_id': round_id,
                         'member': member_id, 'provider': member['provider'], 'status': 'pending'}
                s.data['events'].append(event)
                s.save(path)  # Interrupted pending calls are visible; never automatically replayed.
                try:
                    output, usage = invoke(provider, prompt)
                    ids = s.add_output(member['role'], args.operation, output, args.parents,
                                       member['provider'], provider.get('model'), usage)
                    event['status'] = 'success'
                    results.append({'member': member_id, 'added': ids})
                except (ProviderError, ValueError) as exc:
                    event.update(status='failed', error=str(exc))
                    results.append({'member': member_id, 'error': str(exc)})
                s.save(path)
            successes = [r for r in results if 'added' in r]
            providers = {members[r['member']]['provider'] for r in successes}
            emit({'round_id': round_id, 'results': results, 'successful_providers': sorted(providers),
                  'council': len(providers) >= 2, 'partial': len(successes) < len(results)})
            return 0 if len(successes) == len(results) else 1
        s.save(path)
        emit(result)
        return 0
    except (OSError, UnicodeError, ValueError, KeyError, TypeError) as exc:
        emit({'valid': False, 'error': str(exc)})
        return 2


if __name__ == '__main__':
    raise SystemExit(main())
