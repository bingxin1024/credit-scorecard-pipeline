"""Generic CSV adapter: any loan-level CSV with a binary default label.

Options (`dataset.options`):
    target_col        required; column with the label
    positive_label    value that means default (default: 1 / "1" / True / "yes")
    date_col          optional; parsed to `issue_date`
    date_format       optional strftime pattern for `date_col`
    loan_amount_col   optional -> `loan_amount`
    net_cash_col      optional -> `net_cash` (strategy layer only)
    drop_cols         columns to ignore
    categorical_cols  force these columns to category dtype (object columns are categorical anyway)
    platform_rating_cols  columns switched by `features.use_platform_rating`
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pandas as pd

from scorecard.adapters.base import (
    DROP,
    ISSUE_DATE,
    KEEP,
    LOAN_AMOUNT,
    NET_CASH,
    PLATFORM,
    RESERVED,
    TARGET,
    Adapter,
    AdapterMeta,
    SampleLog,
)


class GenericCSVAdapter(Adapter):
    name = "generic"
    version = "1"

    def load_raw(self) -> pd.DataFrame:
        path = Path(self.config.dataset.path or "")
        if not path.exists():
            raise FileNotFoundError(f"CSV not found: {path}")
        kwargs: dict[str, Any] = {"low_memory": False}
        if self.config.dataset.nrows:
            kwargs["nrows"] = int(self.config.dataset.nrows)
        return pd.read_csv(path, **kwargs)

    def transform(self, raw: pd.DataFrame, source: str = "<frame>") -> tuple[pd.DataFrame, AdapterMeta]:
        opts = self.options
        target_col = opts.get("target_col")
        if not target_col or target_col not in raw.columns:
            raise ValueError("generic adapter needs `dataset.options.target_col` present in the CSV")
        positive = opts.get("positive_label", 1)
        date_col = opts.get("date_col")
        drop_cols = set(opts.get("drop_cols", []) or [])
        forced_cat = set(opts.get("categorical_cols", []) or [])
        platform_cols = [c for c in (opts.get("platform_rating_cols", []) or []) if c in raw.columns]
        loan_amount_col = opts.get("loan_amount_col")
        net_cash_col = opts.get("net_cash_col")

        log = SampleLog()
        n0 = len(raw)
        df = raw[raw[target_col].notna()].copy()
        y = df[target_col]
        target = (y.astype(str).str.lower() == str(positive).lower()) | (y == positive)
        df[TARGET] = target.astype("int8")
        log.add("drop_missing_target", f"剔除 {target_col} 缺失的行", n0, len(df), float(df[TARGET].mean()))

        if date_col and date_col in df:
            df[ISSUE_DATE] = pd.to_datetime(df[date_col], format=opts.get("date_format"), errors="coerce")
            n_before = len(df)
            df = df[df[ISSUE_DATE].notna()]
            log.add("drop_missing_date", f"剔除 {date_col} 无法解析的行", n_before, len(df), float(df[TARGET].mean()))
            min_issue = self.config.sample.min_issue_date
            if min_issue:
                n_before = len(df)
                df = df[df[ISSUE_DATE] >= pd.Timestamp(min_issue)]
                log.add("min_issue_date", f"只保留 {date_col} >= {min_issue}", n_before, len(df), float(df[TARGET].mean()))
        log.add("final_sample", "最终样本量与 bad rate", len(df), len(df), float(df[TARGET].mean()))

        out = pd.DataFrame(index=df.index)
        out[TARGET] = df[TARGET]
        if ISSUE_DATE in df:
            out[ISSUE_DATE] = df[ISSUE_DATE]
        if loan_amount_col and loan_amount_col in df:
            out[LOAN_AMOUNT] = pd.to_numeric(df[loan_amount_col], errors="coerce")
        if net_cash_col and net_cash_col in df:
            out[NET_CASH] = pd.to_numeric(df[net_cash_col], errors="coerce")

        rows: list[dict[str, Any]] = []
        feature_cols: list[str] = []
        categorical: list[str] = []
        skip = {target_col, date_col, loan_amount_col, net_cash_col} | drop_cols
        for col in raw.columns:
            if col == target_col:
                rows.append(dict(column=col, group="A", decision=RESERVED, reason="→ target"))
            elif col == date_col:
                rows.append(dict(column=col, group="I", decision=RESERVED, reason="→ issue_date"))
            elif col in (loan_amount_col, net_cash_col):
                rows.append(dict(column=col, group="B", decision=RESERVED, reason="策略层字段"))
            elif col in drop_cols:
                rows.append(dict(column=col, group="E", decision=DROP, reason="config drop_cols"))
            elif col in platform_cols:
                rows.append(dict(column=col, group="G", decision=PLATFORM, reason="平台评级"))
            elif col in skip:
                continue
            else:
                rows.append(dict(column=col, group="I", decision=KEEP, reason="候选特征"))
                feature_cols.append(col)
        for col in feature_cols + platform_cols:
            series = df[col]
            if col in forced_cat or not pd.api.types.is_numeric_dtype(series):
                out[col] = series.astype("string").astype("category")
                categorical.append(col)
            else:
                out[col] = pd.to_numeric(series, errors="coerce").astype("float64")

        if ISSUE_DATE in out:
            out = out.sort_values(ISSUE_DATE, kind="stable")
        audit = pd.DataFrame(rows)
        audit["group_name"] = audit["group"].map(
            {"A": "target", "B": "strategy only", "E": "dropped", "G": "platform rating", "I": "candidate"}
        )
        meta = AdapterMeta(
            name=self.name,
            source=source,
            n_raw_rows=n0,
            n_raw_cols=raw.shape[1],
            feature_cols=feature_cols,
            categorical_cols=categorical,
            sample_definition_log=log.as_list(),
            field_audit=audit,
            platform_rating_cols=platform_cols,
            platform_grade_col=platform_cols[0] if platform_cols else None,
        )
        return out.reset_index(drop=True), meta
