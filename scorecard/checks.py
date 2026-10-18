"""Automatic checks and risk flags (report section 7, PLAN.md §3).

Phase 1 ships the interface only; `run_checks()` returns None and the report shows the
"not implemented" placeholder for section 7. Phase 2 fills it in.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from scorecard.pipeline import RunResult

IMPLEMENTED = False


def run_checks(result: RunResult) -> dict[str, Any] | None:  # noqa: ARG001
    return None
