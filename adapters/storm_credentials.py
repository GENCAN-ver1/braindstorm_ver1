"""Read literal local Council keys; never modify the process environment."""
import re
from pathlib import Path


def load_credentials(path, allowed_names):
    source = Path(path)
    with source.open('rb') as stream:
        raw = stream.read(64 * 1024 + 1)
    if len(raw) > 64 * 1024:
        raise ValueError('Council key file exceeds 64 KiB')
    try:
        lines = raw.decode('utf-8-sig').splitlines()
    except UnicodeDecodeError:
        raise ValueError('Council key file must use UTF-8') from None
    result = {}
    seen = set()
    for number, line in enumerate(lines, 1):
        line = line.strip()
        if not line or line.startswith('#'):
            continue
        name, separator, value = line.partition('=')
        name = name.strip()
        if not separator or not re.fullmatch(r'[A-Za-z_][A-Za-z0-9_]*', name) or name in seen:
            raise ValueError(f'invalid or duplicate key entry on line {number}')
        seen.add(name)
        value = value.strip()
        if value.startswith(('"', "'")):
            if len(value) < 2 or value[-1] != value[0]:
                raise ValueError(f'unclosed quoted key on line {number}')
            value = value[1:-1]
        if name in allowed_names:
            result[name] = value
    return result
