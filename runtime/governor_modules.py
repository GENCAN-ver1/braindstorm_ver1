"""Load the existing provider-neutral P0-P6 modules from the local skill."""

from __future__ import annotations

import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).parents[1]
GOVERNOR_SCRIPTS = (
    PROJECT_ROOT / ".agents" / "skills" / "brainstorm-governor" / "scripts"
)
if str(GOVERNOR_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(GOVERNOR_SCRIPTS))

import p0_runtime as p0  # noqa: E402
import p1_core as p1  # noqa: E402
import p2_persistence as p2  # noqa: E402
import p3_challenge as p3  # noqa: E402
import p4_research as p4  # noqa: E402
import p5_orchestration as p5  # noqa: E402
import p6_quality as p6  # noqa: E402


__all__ = ["p0", "p1", "p2", "p3", "p4", "p5", "p6"]
