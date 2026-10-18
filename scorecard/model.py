"""Models and metrics: WOE logistic regression (the scorecard), GBDT challenger, AUC / KS / Gini, CV.

The scorecard LR is fitted on WOE values; cross-validation refits the binning + WOE inside every
fold on the already-selected feature list (so the validation fold's labels never touch the WOE
encoding that scores it). The challenger eats raw features (NaN allowed, categoricals as codes).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import numpy as np
import pandas as pd
from sklearn.ensemble import HistGradientBoostingClassifier
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import roc_auc_score, roc_curve
from sklearn.model_selection import StratifiedKFold

from scorecard.binning import Binner
from scorecard.config import BinningConfig, ModelConfig


# --------------------------------------------------------------------------- metrics
def ks_statistic(y_true, y_score) -> float:
    """KS = max distance between the cumulative distributions of bads and goods = max(TPR - FPR)."""
    fpr, tpr, _ = roc_curve(y_true, y_score)
    return float(np.max(tpr - fpr))


def binary_metrics(y_true, y_score) -> dict[str, float]:
    """AUC, KS, Gini for a score where higher = more likely to default."""
    y_true = np.asarray(y_true)
    if len(np.unique(y_true)) < 2:
        return {"auc": float("nan"), "ks": float("nan"), "gini": float("nan")}
    auc = float(roc_auc_score(y_true, y_score))
    return {"auc": auc, "ks": ks_statistic(y_true, y_score), "gini": 2 * auc - 1}


def roc_points(y_true, y_score, max_points: int = 400) -> pd.DataFrame:
    fpr, tpr, thr = roc_curve(y_true, y_score)
    if len(fpr) > max_points:
        idx = np.unique(np.linspace(0, len(fpr) - 1, max_points).astype(int))
        fpr, tpr, thr = fpr[idx], tpr[idx], thr[idx]
    return pd.DataFrame({"fpr": fpr, "tpr": tpr, "threshold": thr})


def ks_table(y_true, y_score, n_bands: int = 10) -> pd.DataFrame:
    """Decile-style KS table: bands of the score (higher = riskier), cumulative bad / good shares."""
    frame = pd.DataFrame({"y": np.asarray(y_true), "s": np.asarray(y_score)})
    frame["band"] = pd.qcut(frame["s"].rank(method="first", ascending=False), n_bands, labels=False) + 1
    g = frame.groupby("band").agg(n=("y", "size"), bad=("y", "sum"), score_min=("s", "min"), score_max=("s", "max"))
    g["good"] = g["n"] - g["bad"]
    g["bad_rate"] = g["bad"] / g["n"]
    g["cum_bad_share"] = g["bad"].cumsum() / g["bad"].sum()
    g["cum_good_share"] = g["good"].cumsum() / g["good"].sum()
    g["ks"] = (g["cum_bad_share"] - g["cum_good_share"]).abs()
    return g.reset_index()


# --------------------------------------------------------------------------- logistic regression
def fit_lr(woe: pd.DataFrame, y, C: float = 1.0, max_iter: int = 1000) -> LogisticRegression:
    # sklearn's default is an L2 penalty; passing `penalty` explicitly is deprecated since 1.8.
    model = LogisticRegression(C=C, solver="lbfgs", max_iter=max_iter)
    model.fit(woe.to_numpy(dtype=float), np.asarray(y, dtype=int))
    return model


def predict_lr(model: LogisticRegression, woe: pd.DataFrame) -> np.ndarray:
    return model.predict_proba(woe.to_numpy(dtype=float))[:, 1]


def vif_table(woe: pd.DataFrame) -> pd.Series:
    """Variance inflation factors = diagonal of the inverse correlation matrix."""
    values = woe.to_numpy(dtype=float)
    std = values.std(axis=0)
    keep = std > 0
    out = pd.Series(np.nan, index=woe.columns, dtype=float)
    if keep.sum() < 2:
        out[keep] = 1.0
        return out
    corr = np.corrcoef(values[:, keep], rowvar=False)
    inv = np.linalg.pinv(corr)
    out[woe.columns[keep]] = np.diag(inv)
    return out


def lr_coefficient_table(model: LogisticRegression, features: list[str], iv: pd.Series | None = None,
                         vif: pd.Series | None = None) -> pd.DataFrame:
    rows = [{"feature": "(intercept)", "coefficient": float(model.intercept_[0]), "iv": np.nan, "vif": np.nan}]
    for f, c in zip(features, model.coef_[0]):
        rows.append(
            {
                "feature": f,
                "coefficient": float(c),
                "iv": float(iv[f]) if iv is not None and f in iv.index else np.nan,
                "vif": float(vif[f]) if vif is not None and f in vif.index else np.nan,
            }
        )
    return pd.DataFrame(rows)


# --------------------------------------------------------------------------- GBDT challenger
@dataclass
class GBDTChallenger:
    params: dict[str, Any]
    categorical: list[str]
    random_state: int = 42
    features: list[str] = field(default_factory=list)
    categories_: dict[str, list] = field(default_factory=dict)
    model_: HistGradientBoostingClassifier | None = None

    MAX_CATEGORIES = 254  # sklearn HistGradientBoosting allows at most max_bins (255) categories
    OTHER_CODE_LABEL = "__OTHER__"

    def _encode(self, X: pd.DataFrame, fit: bool = False) -> np.ndarray:
        out = np.empty((len(X), len(self.features)), dtype=float)
        for j, col in enumerate(self.features):
            s = X[col]
            if col in self.categorical:
                values = s.astype("object").astype(str).where(s.notna())
                if fit:
                    counts = values.value_counts()
                    top = [str(c) for c in counts.index[: self.MAX_CATEGORIES]]
                    if len(counts) > self.MAX_CATEGORIES:
                        top.append(self.OTHER_CODE_LABEL)
                    self.categories_[col] = top
                cats = self.categories_[col]
                if cats and cats[-1] == self.OTHER_CODE_LABEL:
                    known = set(cats[:-1])
                    values = values.where(values.isna() | values.isin(known), self.OTHER_CODE_LABEL)
                codes = pd.Categorical(values, categories=cats).codes
                out[:, j] = np.where(codes < 0, np.nan, codes)
            else:
                out[:, j] = pd.to_numeric(s, errors="coerce").to_numpy(dtype=float)
        return out

    def fit(self, X: pd.DataFrame, y) -> GBDTChallenger:
        # Columns without a single observed value in training cannot be binned by sklearn.
        self.features = [c for c in X.columns if X[c].notna().any()]
        values = self._encode(X, fit=True)
        mask = [c in self.categorical for c in self.features]
        self.model_ = HistGradientBoostingClassifier(
            categorical_features=mask if any(mask) else None, random_state=self.random_state, **self.params
        )
        self.model_.fit(values, np.asarray(y, dtype=int))
        return self

    def predict_proba(self, X: pd.DataFrame) -> np.ndarray:
        assert self.model_ is not None, "fit first"
        return self.model_.predict_proba(self._encode(X[self.features]))[:, 1]


# --------------------------------------------------------------------------- cross-validation
def cross_validate_scorecard(X: pd.DataFrame, y, features: list[str], categorical: list[str],
                             binning_cfg: BinningConfig, model_cfg: ModelConfig, random_state: int) -> dict[str, Any]:
    """Stratified K-fold on the training set; binning + WOE + LR refitted inside each fold."""
    y = np.asarray(y, dtype=int)
    folds = StratifiedKFold(n_splits=model_cfg.cv_folds, shuffle=True, random_state=random_state)
    aucs, kss = [], []
    for fit_idx, val_idx in folds.split(X, y):
        binner = Binner(binning_cfg, random_state=random_state).fit(
            X.iloc[fit_idx][features], y[fit_idx], [c for c in categorical if c in features]
        )
        model = fit_lr(binner.transform(X.iloc[fit_idx], features), y[fit_idx], model_cfg.lr_C, model_cfg.lr_max_iter)
        p = predict_lr(model, binner.transform(X.iloc[val_idx], features))
        m = binary_metrics(y[val_idx], p)
        aucs.append(m["auc"])
        kss.append(m["ks"])
    return _cv_summary(aucs, kss)


def cross_validate_challenger(X: pd.DataFrame, y, categorical: list[str], params: dict[str, Any],
                              n_folds: int, random_state: int) -> dict[str, Any]:
    y = np.asarray(y, dtype=int)
    folds = StratifiedKFold(n_splits=n_folds, shuffle=True, random_state=random_state)
    aucs, kss = [], []
    for fit_idx, val_idx in folds.split(X, y):
        model = GBDTChallenger(params, [c for c in categorical if c in X.columns], random_state).fit(X.iloc[fit_idx], y[fit_idx])
        m = binary_metrics(y[val_idx], model.predict_proba(X.iloc[val_idx]))
        aucs.append(m["auc"])
        kss.append(m["ks"])
    return _cv_summary(aucs, kss)


def _cv_summary(aucs: list[float], kss: list[float]) -> dict[str, Any]:
    return {
        "cv_auc_mean": float(np.mean(aucs)),
        "cv_auc_std": float(np.std(aucs, ddof=1)) if len(aucs) > 1 else 0.0,
        "cv_ks_mean": float(np.mean(kss)),
        "cv_ks_std": float(np.std(kss, ddof=1)) if len(kss) > 1 else 0.0,
        "cv_auc_folds": [float(a) for a in aucs],
        "cv_ks_folds": [float(k) for k in kss],
    }
