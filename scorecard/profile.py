"""Data profiling for report section 1: shapes, dtypes, missing rates, distributions, bad rate over time."""

from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd

from scorecard.adapters.base import ISSUE_DATE, TARGET, AdapterMeta


def feature_summary(df: pd.DataFrame, features: list[str], categorical: list[str]) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []
    for col in features:
        s = df[col]
        row: dict[str, Any] = {
            "feature": col,
            "kind": "categorical" if col in categorical else "numeric",
            "dtype": str(s.dtype),
            "missing_rate": float(s.isna().mean()),
            "n_unique": int(s.nunique(dropna=True)),
        }
        if col in categorical or not pd.api.types.is_numeric_dtype(s):
            counts = s.value_counts(dropna=True)
            if len(counts):
                row["top_value"] = str(counts.index[0])
                row["top_share"] = float(counts.iloc[0] / max(len(s), 1))
        else:
            q = s.quantile([0.0, 0.25, 0.5, 0.75, 1.0]) if s.notna().any() else pd.Series([np.nan] * 5)
            row.update(
                {
                    "min": float(q.iloc[0]),
                    "p25": float(q.iloc[1]),
                    "median": float(q.iloc[2]),
                    "p75": float(q.iloc[3]),
                    "max": float(q.iloc[4]),
                    "mean": float(s.mean()) if s.notna().any() else np.nan,
                }
            )
        rows.append(row)
    return pd.DataFrame(rows)


def bad_rate_by_period(df: pd.DataFrame, freq: str = "Q") -> pd.DataFrame:
    if ISSUE_DATE not in df.columns:
        return pd.DataFrame(columns=["period", "n", "bad", "bad_rate"])
    period = df[ISSUE_DATE].dt.to_period(freq).astype(str)
    table = (
        df.assign(period=period)
        .groupby("period")
        .agg(n=(TARGET, "size"), bad=(TARGET, "sum"), bad_rate=(TARGET, "mean"))
        .reset_index()
    )
    return table


def missing_rate_by_year(df: pd.DataFrame, features: list[str], min_missing: float = 0.05) -> pd.DataFrame:
    """Missing rate per issue year for features whose overall missing rate exceeds `min_missing`."""
    if ISSUE_DATE not in df.columns:
        return pd.DataFrame()
    overall = df[features].isna().mean()
    cols = overall[overall > min_missing].sort_values(ascending=False).index.tolist()
    if not cols:
        return pd.DataFrame()
    year = df[ISSUE_DATE].dt.year
    table = df[cols].isna().groupby(year).mean().T
    table.columns = [str(c) for c in table.columns]
    table.insert(0, "overall", overall[cols].values)
    return table.rename_axis("feature").reset_index()


def profile_frame(df: pd.DataFrame, meta: AdapterMeta, features: list[str], categorical: list[str],
                  labels: pd.Series, top_missing: int = 20) -> dict[str, Any]:
    summary = feature_summary(df, features, categorical)
    missing_top = (
        summary[["feature", "kind", "missing_rate", "n_unique"]]
        .sort_values("missing_rate", ascending=False)
        .head(top_missing)
        .reset_index(drop=True)
    )
    overview = {
        "source": meta.source,
        "n_raw_rows": meta.n_raw_rows,
        "n_raw_cols": meta.n_raw_cols,
        "n_rows": int(len(df)),
        "n_columns": int(df.shape[1]),
        "n_features": len(features),
        "n_categorical": len([c for c in features if c in categorical]),
        "bad_rate": float(df[TARGET].mean()),
        "n_bad": int(df[TARGET].sum()),
        "has_issue_date": ISSUE_DATE in df.columns,
    }
    if ISSUE_DATE in df.columns:
        overview["issue_date_min"] = str(df[ISSUE_DATE].min().to_period("M"))
        overview["issue_date_max"] = str(df[ISSUE_DATE].max().to_period("M"))
    return {
        "overview": overview,
        "feature_summary": summary,
        "missing_top": missing_top,
        "bad_rate_by_quarter": bad_rate_by_period(df, "Q"),
        "bad_rate_by_year": bad_rate_by_period(df, "Y"),
        "missing_by_year": missing_rate_by_year(df, features),
    }
