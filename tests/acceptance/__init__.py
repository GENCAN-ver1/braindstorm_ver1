"""Acceptance tests for AC-01 through AC-08."""
"""Acceptance tests with access to the repository acceptance runtime package."""

from pathlib import Path


# ``unittest discover -s tests`` imports this directory as top-level
# ``acceptance``. Extend that package path so ``acceptance.full_version`` still
# resolves to the repository runtime instead of being shadowed by the tests.
_runtime_package = Path(__file__).parents[2] / "acceptance"
if str(_runtime_package) not in __path__:
    __path__.append(str(_runtime_package))
