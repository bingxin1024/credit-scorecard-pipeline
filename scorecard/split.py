"""Train / test / OOT split (PLAN.md §4.5).

With an `issue_date`: the last `oot_months` calendar months are the out-of-time sample; the rest
is split stratified-at-random into train / test by `train_ratio`. Without a date: a stratified
hold-out of `oot_fraction` plays the role of OOT (clearly labelled as such in the report).
"""

from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd
from sklearn.model_selection import train_test_split

from scorecard.adapters.base import ISSUE_DATE, TARGET
from scorecard.config import SplitConfig

TRAIN, TEST, OOT = "train", "test", "oot"
SEGMENTS = (TRAIN, TEST, OOT)


def make_split(df: pd.DataFrame, cfg: SplitConfig) -> tuple[pd.Series, dict[str, Any]]:
    """Return a label Series aligned with `df` ('train' / 'test' / 'oot') and a summary dict."""
    n = len(df)
    labels = pd.Series(np.empty(n, dtype=object), index=df.index)
    info: dict[str, Any] = {"method": None, "warnings": []}
    y = df[TARGET].to_numpy()

    has_date = ISSUE_DATE in df.columns and df[ISSUE_DATE].notna().any()
    if has_date:
        months = df[ISSUE_DATE].dt.to_period("M")
        last = months.max()
        n_months_total = int(last.ordinal - months.min().ordinal + 1)
        oot_months = int(cfg.oot_months)
        if n_months_total <= oot_months:
            info["warnings"].append(
                f"数据只覆盖 {n_months_total} 个月，不足以切出 {oot_months} 个月的 OOT，改用分层 hold-out"
            )
            has_date = False
        else:
            oot_mask = (months > (last - oot_months)).to_numpy()
            while oot_mask.mean() > 0.5 and oot_months > 1:
                oot_months -= 1
                oot_mask = (months > (last - oot_months)).to_numpy()
            if oot_months != int(cfg.oot_months):
                info["warnings"].append(
                    f"OOT 按 {cfg.oot_months} 个月会超过一半样本，已缩短为 {oot_months} 个月"
                )
            info["method"] = "time"
            info["oot_months"] = oot_months
            info["oot_start"] = str(last - oot_months + 1)
            info["oot_end"] = str(last)
            rest_idx = np.flatnonzero(~oot_mask)
            labels.iloc[np.flatnonzero(oot_mask)] = OOT
    if not has_date:
        info["method"] = "stratified_holdout"
        all_idx = np.arange(n)
        rest_idx, oot_idx = train_test_split(
            all_idx, test_size=float(cfg.oot_fraction), stratify=y, random_state=cfg.random_state
        )
        labels.iloc[oot_idx] = OOT

    train_idx, test_idx = train_test_split(
        rest_idx, train_size=float(cfg.train_ratio), stratify=y[rest_idx], random_state=cfg.random_state
    )
    labels.iloc[train_idx] = TRAIN
    labels.iloc[test_idx] = TEST

    rows = []
    for seg in SEGMENTS:
        mask = (labels == seg).to_numpy()
        row: dict[str, Any] = {
            "segment": seg,
            "n": int(mask.sum()),
            "share": float(mask.mean()),
            "bad_rate": float(y[mask].mean()) if mask.any() else np.nan,
        }
        if ISSUE_DATE in df.columns and mask.any():
            dates = df.loc[mask, ISSUE_DATE]
            row["date_min"] = str(dates.min().to_period("M")) if dates.notna().any() else ""
            row["date_max"] = str(dates.max().to_period("M")) if dates.notna().any() else ""
        rows.append(row)
    info["summary"] = pd.DataFrame(rows)
    info["train_ratio"] = cfg.train_ratio
    info["random_state"] = cfg.random_state
    return labels, info
