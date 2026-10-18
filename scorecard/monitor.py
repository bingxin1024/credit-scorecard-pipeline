"""Monitoring layer (PLAN.md §6.3): score PSI, feature CSI, vintage curves.

Phase 1 ships the interface only; `analyse()` returns None and the report shows the
"not implemented" placeholder for section 6. Phase 2 fills it in.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from scorecard.pipeline import RunResult

IMPLEMENTED = False


def analyse(result: RunResult) -> dict[str, Any] | None:  # noqa: ARG001
    return None
