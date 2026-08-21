#!/usr/bin/env python3
"""Zero-dependency structural validator for the checked-in Codex skill."""

from __future__ import annotations

import argparse
import re
from pathlib import Path
from typing import Sequence


ALLOWED_KEYS = {"name", "description", "license", "allowed-tools", "metadata"}


def validate_skill(path: str | Path) -> tuple[bool, str]:
    skill_path = Path(path)
    skill_md = skill_path / "SKILL.md"
    if not skill_md.is_file():
        return False, "SKILL.md not found"
    content = skill_md.read_text(encoding="utf-8")
    match = re.match(r"^---\r?\n(.*?)\r?\n---", content, re.DOTALL)
    if match is None:
        return False, "Invalid frontmatter format"
    frontmatter: dict[str, str] = {}
    for line in match.group(1).splitlines():
        if not line.strip() or line.startswith((" ", "\t")):
            continue
        key, separator, value = line.partition(":")
        if not separator or not key.strip():
            return False, "Invalid YAML in frontmatter"
        frontmatter[key.strip()] = value.strip().strip('"\'')
    unexpected = set(frontmatter) - ALLOWED_KEYS
    if unexpected:
        return False, f"Unexpected frontmatter keys: {sorted(unexpected)}"
    if "name" not in frontmatter or "description" not in frontmatter:
        return False, "Missing name or description in frontmatter"
    name = frontmatter["name"]
    if (
        not re.fullmatch(r"[a-z0-9-]+", name)
        or name.startswith("-")
        or name.endswith("-")
        or "--" in name
        or len(name) > 64
    ):
        return False, "Skill name is invalid"
    description = frontmatter["description"]
    if (
        not description
        or description.startswith("[TODO:")
        or "<" in description
        or ">" in description
        or len(description) > 1024
    ):
        return False, "Skill description is invalid"
    body = content[match.end() :]
    if re.search(r"(?m)^[ ]{0,3}\[TODO:[^\n]*\][ \t]*$", body):
        return False, "Skill instructions contain an unfinished TODO placeholder"
    return True, "Skill is valid!"


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("skill_path")
    args = parser.parse_args(argv)
    valid, message = validate_skill(args.skill_path)
    print(message)
    return 0 if valid else 1


if __name__ == "__main__":
    raise SystemExit(main())


__all__ = ["validate_skill"]
