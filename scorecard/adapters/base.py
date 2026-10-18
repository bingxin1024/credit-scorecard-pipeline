"""Adapter contract: raw data -> standard frame + AdapterMeta (PLAN.md §2).

The engine (everything outside `scorecard/adapters/`) only ever sees the standard frame:

* `target`            0/1, 1 = default (required)
* feature columns     numeric or category dtype; the adapter cleans the types
* `issue_date`        datetime, optional; used for the OOT split, bad rate by quarter, vintage
* `event_date`        datetime, optional; approximate date of the default / last payment (vintage only)
* `loan_amount`       optional; strategy layer only
* `net_cash`          optional; realised net cash flow, strategy layer ONLY, never a feature

Reserved columns are never features. Platform-rating columns (e.g. Lending Club `grade`) are
kept in the frame and switched on/off as features by `features.use_platform_rating`.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

import pandas as pd

if TYPE_CHECKING:
    from scorecard.config import Config

TARGET = "target"
ISSUE_DATE = "issue_date"
EVENT_DATE = "event_date"
LOAN_AMOUNT = "loan_amount"
NET_CASH = "net_cash"
RESERVED_COLUMNS: tuple[str, ...] = (TARGET, ISSUE_DATE, EVENT_DATE, LOAN_AMOUNT, NET_CASH)

# Field-audit decision labels (English keys; the report translates them).
KEEP = "keep"
DROP = "drop"
RESERVED = "reserved"
PLATFORM = "platform_rating"
DERIVED = "derived"


@dataclass
class AdapterMeta:
    """Everything the engine and the report need to know about how the frame was produced."""

    name: str
    source: str
    n_raw_rows: int
    n_raw_cols: int
    feature_cols: list[str]
    categorical_cols: list[str]
    sample_definition_log: list[dict[str, Any]]
    field_audit: pd.DataFrame
    platform_rating_cols: list[str] = field(default_factory=list)
    platform_grade_col: str | None = None
    warnings: list[str] = field(default_factory=list)
    notes: dict[str, Any] = field(default_factory=dict)
    extra_tables: dict[str, pd.DataFrame] = field(default_factory=dict)


class SampleLog:
    """Collects one row per sample-definition rule: rule, removed, remaining, bad rate."""

    def __init__(self) -> None:
        self.rows: list[dict[str, Any]] = []

    def add(self, rule: str, description: str, before: int, after: int, bad_rate: float | None) -> None:
        self.rows.append(
            {
                "step": len(self.rows) + 1,
                "rule": rule,
                "description": description,
                "removed": int(before - after),
                "remaining": int(after),
                "bad_rate": None if bad_rate is None or pd.isna(bad_rate) else float(bad_rate),
            }
        )

    def as_list(self) -> list[dict[str, Any]]:
        return list(self.rows)


class Adapter(ABC):
    """Base class. Subclasses implement `load_raw()` (file -> raw frame) and `transform(raw)`."""

    name: str = "base"
    version: str = "1"

    def __init__(self, config: Config):
        self.config = config
        self.options: dict[str, Any] = dict(config.dataset.options or {})

    @abstractmethod
    def load_raw(self) -> pd.DataFrame:
        """Read the raw file(s) configured in `config.dataset` into a DataFrame."""

    @abstractmethod
    def transform(self, raw: pd.DataFrame, source: str = "<frame>") -> tuple[pd.DataFrame, AdapterMeta]:
        """Apply sample definition, field audit and feature construction to a raw frame."""

    def load(self) -> tuple[pd.DataFrame, AdapterMeta]:
        # No local variable holds the raw frame, so `transform` owns the only reference and can
        # release it once the sample rules have dropped most rows (peak-memory matters at 2 M rows).
        return self.transform(self.load_raw(), source=str(self.config.dataset.path or self.name))


def validate_standard_frame(frame: pd.DataFrame, meta: AdapterMeta) -> list[str]:
    """Return a list of contract violations (empty = OK)."""
    problems: list[str] = []
    if TARGET not in frame.columns:
        problems.append("missing `target` column")
    else:
        values = set(pd.unique(frame[TARGET].dropna()))
        if not values <= {0, 1}:
            problems.append(f"`target` must be 0/1, found {sorted(values)[:5]}")
        if frame[TARGET].isna().any():
            problems.append("`target` contains missing values")
    for col in meta.feature_cols:
        if col not in frame.columns:
            problems.append(f"feature `{col}` listed in meta but missing from frame")
            continue
        if col in RESERVED_COLUMNS:
            problems.append(f"reserved column `{col}` used as a feature")
        if not (pd.api.types.is_numeric_dtype(frame[col]) or isinstance(frame[col].dtype, pd.CategoricalDtype)):
            problems.append(f"feature `{col}` is neither numeric nor category dtype ({frame[col].dtype})")
    if ISSUE_DATE in frame.columns and not pd.api.types.is_datetime64_any_dtype(frame[ISSUE_DATE]):
        problems.append("`issue_date` is not datetime")
    return problems
