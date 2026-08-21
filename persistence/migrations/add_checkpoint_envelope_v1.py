"""Add the FV-02 checkpoint envelope to a legacy P2 Living Brief."""

from __future__ import annotations

from pathlib import Path

from runtime.checkpoint import CheckpointStore
from runtime.fault_injection import Stage
from runtime.governor_modules import p2


def migrate_brief(path: str | Path):
    target = Path(path)
    legacy = p2.load_brief(target)
    return CheckpointStore().open(
        target,
        legacy.runtime_state,
        initial_next_stage=Stage.CONTEXT,
    )

