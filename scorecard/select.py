"""Feature selection on the training set (PLAN.md §5 `select`).

Order of the filters, each recorded in the selection table with the reason it fired:

1. missing rate  > max_missing          -> drop
2. IV            < min_iv               -> drop;  IV > leakage_iv -> warning, kept
3. |corr| (WOE)  > max_corr             -> keep the higher-IV feature of each pair (greedy by IV)
4. max_features  (optional)             -> keep the top-N by IV
5. coefficient sign (optional)          -> a WOE feature with a positive LR coefficient is dropped
                                           (lowest IV first) and the model refitted
6. VIF           > max_vif              -> warning only
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import numpy as np
import pandas as pd

from scorecard.binning import Binner
from scorecard.config import SelectConfig
from scorecard.model import fit_lr, vif_table


@dataclass
class SelectionResult:
    table: pd.DataFrame
    selected: list[str]
    warnings: list[str] = field(default_factory=list)
    leakage_suspects: list[str] = field(default_factory=list)
    vif: pd.Series | None = None
    corr_matrix: pd.DataFrame | None = None
    sign_dropped: list[dict[str, Any]] = field(default_factory=list)


def greedy_correlation_filter(woe: pd.DataFrame, iv: pd.Series, max_corr: float) -> tuple[list[str], list[dict[str, Any]]]:
    """Walk features by IV (desc); drop one whose |corr| with an already-kept feature exceeds max_corr."""
    order = iv.sort_values(ascending=False).index.tolist()
    corr = woe[order].corr().abs()
    kept: list[str] = []
    dropped: list[dict[str, Any]] = []
    for feat in order:
        clash = None
        for k in kept:
            value = corr.loc[feat, k]
            if np.isfinite(value) and value > max_corr:
                clash = (k, float(value))
                break
        if clash is None:
            kept.append(feat)
        else:
            dropped.append({"feature": feat, "with": clash[0], "corr": clash[1], "iv": float(iv[feat]), "with_iv": float(iv[clash[0]])})
    return kept, dropped


def select_features(binner: Binner, X: pd.DataFrame, y: pd.Series | np.ndarray, cfg: SelectConfig,
                    lr_C: float = 1.0, lr_max_iter: int = 1000) -> SelectionResult:
    y = np.asarray(y)
    iv_table = binner.iv_table().set_index("feature")
    features = list(iv_table.index)
    missing_rate = X[features].isna().mean()
    status: dict[str, dict[str, Any]] = {
        f: {"step": "", "reason": "selected", "selected": True} for f in features
    }
    warnings: list[str] = []

    # 1. missing rate
    for f in features:
        if missing_rate[f] > cfg.max_missing:
            status[f] = {"step": "1_missing", "reason": f"missing rate {missing_rate[f]:.1%} > {cfg.max_missing:.0%}", "selected": False}
    remaining = [f for f in features if status[f]["selected"]]

    # 2. IV
    leakage: list[str] = []
    for f in remaining:
        iv = float(iv_table.loc[f, "iv"])
        if iv < cfg.min_iv:
            status[f] = {"step": "2_iv", "reason": f"IV {iv:.4f} < {cfg.min_iv}", "selected": False}
        elif iv > cfg.leakage_iv:
            leakage.append(f)
            warnings.append(f"{f}: IV = {iv:.3f} > {cfg.leakage_iv}，疑似 leakage，已保留但需人工确认")
    remaining = [f for f in features if status[f]["selected"]]

    # 3. correlation on WOE values
    corr_matrix = None
    if len(remaining) > 1:
        woe = binner.transform(X, remaining)
        kept, dropped = greedy_correlation_filter(woe, iv_table.loc[remaining, "iv"], cfg.max_corr)
        for d in dropped:
            status[d["feature"]] = {
                "step": "3_corr",
                "reason": f"|corr| = {d['corr']:.2f} with {d['with']} (IV {d['with_iv']:.3f})",
                "selected": False,
            }
        remaining = kept
        corr_matrix = woe[remaining].corr() if remaining else None

    # 4. optional cap on the number of features
    if cfg.max_features and len(remaining) > cfg.max_features:
        ranked = iv_table.loc[remaining, "iv"].sort_values(ascending=False)
        for f in ranked.index[cfg.max_features:]:
            status[f] = {"step": "4_max_features", "reason": f"outside top {cfg.max_features} by IV", "selected": False}
        remaining = list(ranked.index[: cfg.max_features])

    # 5. coefficient sign check (WOE = ln(good/bad) -> coefficients must be negative)
    sign_dropped: list[dict[str, Any]] = []
    if cfg.drop_positive_coef and remaining:
        while remaining:
            woe = binner.transform(X, remaining)
            model = fit_lr(woe, y, C=lr_C, max_iter=lr_max_iter)
            coefs = pd.Series(model.coef_[0], index=remaining)
            positive = coefs[coefs > 0]
            if positive.empty:
                break
            victim = iv_table.loc[positive.index, "iv"].idxmin()
            status[victim] = {
                "step": "5_sign",
                "reason": f"coefficient +{coefs[victim]:.4f} is not negative",
                "selected": False,
            }
            sign_dropped.append({"feature": victim, "coefficient": float(coefs[victim]), "iv": float(iv_table.loc[victim, "iv"])})
            remaining = [f for f in remaining if f != victim]

    # 6. VIF (warning only)
    vif = None
    if len(remaining) > 1:
        vif = vif_table(binner.transform(X, remaining))
        for f, v in vif.items():
            if v > cfg.max_vif:
                warnings.append(f"{f}: VIF = {v:.2f} > {cfg.max_vif}（共线性偏高，已保留）")

    rows = []
    for f in features:
        rows.append(
            {
                "feature": f,
                "kind": iv_table.loc[f, "kind"],
                "iv": float(iv_table.loc[f, "iv"]),
                "missing_rate": float(missing_rate[f]),
                "n_bins": int(iv_table.loc[f, "n_bins"]),
                "selected": bool(status[f]["selected"]),
                "step": status[f]["step"],
                "reason": status[f]["reason"],
                "vif": float(vif[f]) if vif is not None and f in vif.index else np.nan,
                "leakage_suspect": f in leakage,
            }
        )
    table = pd.DataFrame(rows).sort_values(["selected", "iv"], ascending=[False, False]).reset_index(drop=True)
    return SelectionResult(
        table=table,
        selected=remaining,
        warnings=warnings,
        leakage_suspects=leakage,
        vif=vif,
        corr_matrix=corr_matrix,
        sign_dropped=sign_dropped,
    )
