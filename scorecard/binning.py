"""Monotonic WOE binning with a pluggable split-point backend (toad -> optbinning -> tree).

Conventions (identical for every backend, so the rest of the engine never knows which one ran):

* bad = default (target 1), good = no default (target 0).
* WOE of a bin = ln(good share / bad share); higher WOE = safer bin, so a logistic regression for
  P(default) should give every WOE feature a NEGATIVE coefficient.
* IV = sum over bins of (good share - bad share) * WOE.
* Numeric bins are right-closed: bin i holds splits[i-1] < x <= splits[i].
* Missing values are their own bin. Categories unseen in training fall into the missing bin.
* Categorical features are ordered by training bad rate and then binned like an ordinal number,
  so their bins are monotone by construction.
* Split points are searched on a random subsample of at most `sample_size` training rows; the WOE
  table is always computed on the full training set.
"""

from __future__ import annotations

import importlib
import logging
import warnings
from dataclasses import dataclass, field
from typing import Any

import numpy as np
import pandas as pd

from scorecard.config import BinningConfig

log = logging.getLogger(__name__)

MISSING_LABEL = "Missing"
SMOOTHING = 0.5  # added to good / bad counts of every bin so an all-good bin has a finite WOE


# --------------------------------------------------------------------------- backend resolution
def resolve_backend(name: str = "auto") -> str:
    """Return the backend that will be used: toad, optbinning or tree (internal)."""
    order = ["toad", "optbinning", "tree"] if name == "auto" else [name]
    for candidate in order:
        if candidate == "tree":
            return "tree"
        try:
            importlib.import_module(candidate)
            return candidate
        except Exception:  # noqa: BLE001 - any import problem means "not available"
            continue
    raise ImportError(f"no binning backend available among {order}")


def _splits_tree(x: np.ndarray, y: np.ndarray, max_bins: int, min_bin_size: int, random_state: int) -> np.ndarray:
    from sklearn.tree import DecisionTreeClassifier

    tree = DecisionTreeClassifier(max_leaf_nodes=max_bins, min_samples_leaf=max(min_bin_size, 1), random_state=random_state)
    tree.fit(x.reshape(-1, 1), y)
    internal = tree.tree_.children_left != -1
    return np.unique(tree.tree_.threshold[internal]).astype(float)


def _splits_toad(x: np.ndarray, y: np.ndarray, max_bins: int, min_samples: float, method: str) -> np.ndarray:
    import toad

    frame = pd.DataFrame({"x": x})
    combiner = toad.transform.Combiner()
    kwargs: dict[str, Any] = dict(method=method, min_samples=min_samples, n_bins=max_bins)
    if method == "chi":
        # toad >= 0.1.7: stop only when BOTH n_bins and min_samples are satisfied (legacy 'any' stops early).
        kwargs["constraint_mode"] = "all"
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        try:
            combiner.fit(frame, y=pd.Series(y), **kwargs)
        except TypeError:  # older toad without constraint_mode
            kwargs.pop("constraint_mode", None)
            combiner.fit(frame, y=pd.Series(y), **kwargs)
    splits = combiner.export().get("x", [])
    return np.asarray(splits, dtype=float)


def _splits_optbinning(x: np.ndarray, y: np.ndarray, max_bins: int, min_samples: float, monotonic: bool) -> np.ndarray:
    from optbinning import OptimalBinning

    ob = OptimalBinning(
        name="x",
        dtype="numerical",
        max_n_bins=max_bins,
        min_prebin_size=min_samples,
        min_bin_size=min_samples,
        monotonic_trend="auto_asc_desc" if monotonic else None,
        solver="cp",
    )
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        ob.fit(x, y)
    return np.asarray(ob.splits, dtype=float)


# --------------------------------------------------------------------------- bin arithmetic
def _bin_counts(bin_ids: np.ndarray, y: np.ndarray, n_bins: int) -> tuple[np.ndarray, np.ndarray]:
    n_bad = np.bincount(bin_ids, weights=y, minlength=n_bins)
    n_all = np.bincount(bin_ids, minlength=n_bins).astype(float)
    return n_all - n_bad, n_bad


def left_closed_to_right_closed(splits: np.ndarray, x: np.ndarray) -> np.ndarray:
    """Convert library splits with `lower bin = x < s` semantics (toad, optbinning) to this
    module's `lower bin = x <= s` convention: each split becomes the largest observed value
    strictly below it, so the row assignment is identical to the library's."""
    u = np.unique(x)
    out = []
    for s in np.asarray(splits, dtype=float):
        idx = int(np.searchsorted(u, s, side="left"))  # first observed value >= s
        if idx > 0:
            out.append(u[idx - 1])
    return np.unique(np.asarray(out, dtype=float))


def _stringify(x: pd.Series) -> np.ndarray:
    """Object array of str for non-missing values, None for missing (categories may be ints)."""
    obj = x.astype("object").to_numpy()
    keys = np.full(len(obj), None, dtype=object)
    mask = pd.notna(obj)
    if mask.any():
        keys[mask] = np.asarray(obj[mask]).astype(str)
    return keys


def merge_small_bins(x: np.ndarray, y: np.ndarray, splits: np.ndarray, min_bin_size: int) -> np.ndarray:
    """Merge bins smaller than `min_bin_size` into the neighbour with the closest bad rate."""
    splits = np.asarray(splits, dtype=float)
    while len(splits) > 0:
        good, bad = _bin_counts(np.searchsorted(splits, x, side="left"), y, len(splits) + 1)
        counts = good + bad
        smallest = int(np.argmin(counts))
        if counts[smallest] >= min_bin_size:
            break
        rates = bad / np.maximum(counts, 1)
        if smallest == 0:
            drop = 0
        elif smallest == len(counts) - 1:
            drop = len(splits) - 1
        else:
            closer_left = abs(rates[smallest] - rates[smallest - 1]) <= abs(rates[smallest] - rates[smallest + 1])
            drop = smallest - 1 if closer_left else smallest
        splits = np.delete(splits, drop)
    return splits


def reduce_to_max_bins(x: np.ndarray, y: np.ndarray, splits: np.ndarray, max_bins: int) -> np.ndarray:
    """Merge the adjacent pair with the closest bad rates until at most `max_bins` bins remain."""
    splits = np.asarray(splits, dtype=float)
    while len(splits) + 1 > max_bins and len(splits) > 0:
        good, bad = _bin_counts(np.searchsorted(splits, x, side="left"), y, len(splits) + 1)
        rates = bad / np.maximum(good + bad, 1)
        splits = np.delete(splits, int(np.argmin(np.abs(np.diff(rates)))))
    return splits


def is_monotone(rates: np.ndarray) -> bool:
    steps = np.diff(np.asarray(rates, dtype=float))
    if len(steps) == 0:
        return True
    return bool(np.all(steps >= 0) or np.all(steps <= 0))


def merge_to_monotonic(x: np.ndarray, y: np.ndarray, splits: np.ndarray) -> np.ndarray:
    """Merge adjacent bins until the bad rate moves in one direction only (or 2 bins remain).

    Direction = sign of the correlation between bin order and bad rate; each round merges the
    violating neighbour pair with the smallest bad-rate gap.
    """
    splits = np.asarray(splits, dtype=float)
    while len(splits) > 0:
        good, bad = _bin_counts(np.searchsorted(splits, x, side="left"), y, len(splits) + 1)
        rates = bad / np.maximum(good + bad, 1)
        steps = np.diff(rates)
        if len(rates) > 2:
            direction = np.sign(np.corrcoef(np.arange(len(rates)), rates)[0, 1])
        else:
            direction = np.sign(steps[0]) if len(steps) else 0.0
        if direction == 0 or np.isnan(direction):
            direction = np.sign(rates[-1] - rates[0]) or 1.0
        violations = np.flatnonzero(steps * direction < 0)
        if len(violations) == 0:
            break
        splits = np.delete(splits, violations[np.argmin(np.abs(steps[violations]))])
    return splits


def _fmt(value: float) -> str:
    if abs(value) >= 1000:
        return f"{value:,.0f}"
    if 0 < abs(value) < 1e-3:
        return "~0"
    return f"{value:.4g}"


# --------------------------------------------------------------------------- one feature
@dataclass
class BinSpec:
    """Fitted bins, WOE values and statistics for one feature."""

    name: str
    kind: str  # numeric | categorical
    splits: list[float] = field(default_factory=list)
    groups: list[list[str]] = field(default_factory=list)
    has_missing: bool = False
    woe: list[float] = field(default_factory=list)
    counts: list[int] = field(default_factory=list)
    bads: list[int] = field(default_factory=list)
    iv: float = 0.0
    n_bins_initial: int = 0
    monotone_before: bool | None = None
    monotone_after: bool | None = None
    backend: str = ""

    # ----- structure
    @property
    def n_regular(self) -> int:
        return len(self.splits) + 1 if self.kind == "numeric" else len(self.groups)

    @property
    def n_bins(self) -> int:
        return self.n_regular + 1  # + missing bin

    def labels(self) -> list[str]:
        if self.kind == "categorical":
            regular = ["{" + ", ".join(str(c) for c in group) + "}" for group in self.groups]
        elif len(self.splits) == 0:
            regular = ["all values"]
        else:
            s = self.splits
            regular = [f"<= {_fmt(s[0])}"] + [f"({_fmt(a)}, {_fmt(b)}]" for a, b in zip(s[:-1], s[1:])] + [f"> {_fmt(s[-1])}"]
        return regular + [MISSING_LABEL]

    def bin_ids(self, x: pd.Series) -> np.ndarray:
        """Bin index per row; index n_regular is the missing / unseen bin."""
        if self.kind == "numeric":
            values = pd.to_numeric(x, errors="coerce").to_numpy(dtype=float)
            ids = np.searchsorted(np.asarray(self.splits, dtype=float), values, side="left")
            ids[np.isnan(values)] = self.n_regular
            return ids.astype(int)
        lookup = {str(cat): i for i, group in enumerate(self.groups) for cat in group}
        keys = _stringify(x)
        return np.array([lookup.get(k, self.n_regular) if k is not None else self.n_regular for k in keys], dtype=int)

    # ----- statistics
    def fit_woe(self, x: pd.Series, y: np.ndarray) -> BinSpec:
        ids = self.bin_ids(x)
        good, bad = _bin_counts(ids, y, self.n_bins)
        self.has_missing = bool(good[-1] + bad[-1] > 0)
        # A bin without training rows (incl. an unused Missing bin) is neutral: WOE 0, no IV.
        used = (good + bad) > 0
        # Smoothing only where a bin has no goods or no bads, so populated bins keep the textbook
        # WOE = ln((good/G) / (bad/B)) exactly.
        degenerate = used & ((good == 0) | (bad == 0))
        good_s = good + SMOOTHING * degenerate
        bad_s = bad + SMOOTHING * degenerate
        good_total = max(good_s[used].sum(), SMOOTHING)
        bad_total = max(bad_s[used].sum(), SMOOTHING)
        good_share = np.where(used, good_s / good_total, 1.0)
        bad_share = np.where(used, bad_s / bad_total, 1.0)
        woe = np.log(good_share / bad_share)
        woe[~used] = 0.0
        iv_parts = np.where(used, (good_share - bad_share) * woe, 0.0)
        self.woe = [float(v) for v in woe]
        self.counts = [int(v) for v in good + bad]
        self.bads = [int(v) for v in bad]
        self.iv = float(iv_parts.sum())
        rates = (bad / np.maximum(good + bad, 1))[: self.n_regular]
        self.monotone_after = is_monotone(rates) if self.n_regular > 1 else True
        return self

    def transform_woe(self, x: pd.Series) -> np.ndarray:
        return np.asarray(self.woe, dtype=float)[self.bin_ids(x)]

    def table(self) -> pd.DataFrame:
        counts = np.asarray(self.counts, dtype=float)
        bads = np.asarray(self.bads, dtype=float)
        total = counts.sum() if counts.sum() else 1.0
        rows = pd.DataFrame(
            {
                "feature": self.name,
                "bin_id": np.arange(self.n_bins),
                "bin": self.labels(),
                "count": counts.astype(int),
                "share": counts / total,
                "bad": bads.astype(int),
                "bad_rate": bads / np.maximum(counts, 1),
                "woe": self.woe,
            }
        )
        if not self.has_missing:
            rows = rows[rows["bin_id"] < self.n_regular]
        return rows.reset_index(drop=True)

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "kind": self.kind,
            "splits": [float(s) for s in self.splits],
            "groups": [[str(c) for c in g] for g in self.groups],
            "has_missing": self.has_missing,
            "woe": self.woe,
            "counts": self.counts,
            "bads": self.bads,
            "iv": self.iv,
            "n_bins_initial": self.n_bins_initial,
            "monotone_before": self.monotone_before,
            "monotone_after": self.monotone_after,
            "backend": self.backend,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> BinSpec:
        return cls(**data)


# --------------------------------------------------------------------------- all features
class Binner:
    """Fit bins for many features on a training frame; transform any frame to WOE / bin ids."""

    def __init__(self, config: BinningConfig, random_state: int = 42):
        self.config = config
        self.random_state = random_state
        self.backend = resolve_backend(config.backend)
        self.bins_: dict[str, BinSpec] = {}
        self.categorical_: list[str] = []
        self.fallback_features_: list[str] = []

    # ----- split search for one numeric array (NaN already removed)
    def _numeric_splits(self, x: np.ndarray, y: np.ndarray, min_bin_size: int) -> tuple[np.ndarray, str]:
        """Return (right-closed split points, name of the backend that produced them)."""
        cfg = self.config
        uniques = np.unique(x)
        if len(uniques) <= 1:
            return np.array([], dtype=float), "constant"
        if len(uniques) <= cfg.max_bins:
            # Low-cardinality (binary / small ordinal) feature: every distinct value starts as its own
            # right-closed bin; merge_small_bins / merge_to_monotonic then tidy it up.
            return uniques[:-1].astype(float), "unique_values"
        x_search = x
        if cfg.prebins and len(uniques) > cfg.prebins:
            # Quantile pre-binning: chi-merge starts from every distinct value, which is quadratic on
            # continuous features. Each value is replaced by the right edge of its quantile bucket, so
            # any split the backend returns is a bucket edge and applies exactly to the raw values.
            edges = np.unique(np.quantile(x, np.linspace(0, 1, cfg.prebins + 1)[1:-1]))
            edges = edges[edges < x.max()]
            reps = np.append(edges, x.max())
            x_search = reps[np.searchsorted(edges, x, side="left")]
        used = self.backend
        try:
            if self.backend == "toad":
                # toad / optbinning splits mean `lower bin = x < s`; convert to `x <= s`.
                splits = left_closed_to_right_closed(_splits_toad(x_search, y, cfg.max_bins, cfg.min_samples, cfg.method), x_search)
            elif self.backend == "optbinning":
                splits = left_closed_to_right_closed(_splits_optbinning(x_search, y, cfg.max_bins, cfg.min_samples, cfg.monotonic), x_search)
            else:
                splits = _splits_tree(x_search, y, cfg.max_bins, min_bin_size, self.random_state)
        except Exception as exc:  # noqa: BLE001 - fall back to the internal backend for this feature
            log.warning("binning backend %s failed (%s); using tree splits for this feature", self.backend, exc)
            splits = _splits_tree(x_search, y, cfg.max_bins, min_bin_size, self.random_state)
            used = "tree"
        splits = np.unique(np.asarray(splits, dtype=float))
        splits = splits[(splits >= x.min()) & (splits < x.max())]
        if len(splits) == 0 and used != "tree":
            # The library found no cut (happens for skewed / few-valued features); try the tree.
            splits = _splits_tree(x_search, y, cfg.max_bins, min_bin_size, self.random_state)
            splits = splits[(splits >= x.min()) & (splits < x.max())]
            used = "tree"
        return splits, used

    def _fit_numeric(self, name: str, x: pd.Series, y: np.ndarray) -> BinSpec:
        values = pd.to_numeric(x, errors="coerce").to_numpy(dtype=float)
        mask = ~np.isnan(values)
        xv, yv = values[mask], y[mask]
        min_bin_size = int(np.ceil(self.config.min_samples * len(values)))
        spec = BinSpec(name=name, kind="numeric", backend="all_missing")
        if len(xv) == 0:
            return spec
        splits, spec.backend = self._numeric_splits(xv, yv, min_bin_size)
        if spec.backend == "tree" and self.backend != "tree":
            self.fallback_features_.append(name)
        splits = merge_small_bins(xv, yv, splits, min_bin_size)
        splits = reduce_to_max_bins(xv, yv, splits, self.config.max_bins)
        spec.n_bins_initial = len(splits) + 1
        good, bad = _bin_counts(np.searchsorted(splits, xv, side="left"), yv, len(splits) + 1)
        spec.monotone_before = is_monotone(bad / np.maximum(good + bad, 1))
        if self.config.monotonic:
            splits = merge_to_monotonic(xv, yv, splits)
        spec.splits = [float(s) for s in splits]
        return spec

    def _fit_categorical(self, name: str, x: pd.Series, y: np.ndarray) -> BinSpec:
        keys = _stringify(x)
        mask = np.array([k is not None for k in keys])
        stats = pd.DataFrame({"x": keys[mask], "y": y[mask]}).groupby("x")["y"].agg(["size", "mean"])
        stats = stats.sort_values(["mean", "size"], ascending=[True, False])
        categories = [str(c) for c in stats.index]
        spec = BinSpec(name=name, kind="categorical", backend="all_missing")
        if not categories:
            return spec
        rank = {cat: i for i, cat in enumerate(categories)}
        ordinal = np.array([rank[k] for k in keys[mask]], dtype=float)
        min_bin_size = int(np.ceil(self.config.min_samples * len(keys)))
        splits, spec.backend = self._numeric_splits(ordinal, y[mask], min_bin_size)
        if spec.backend == "tree" and self.backend != "tree":
            self.fallback_features_.append(name)
        splits = merge_small_bins(ordinal, y[mask], splits, min_bin_size)
        splits = reduce_to_max_bins(ordinal, y[mask], splits, self.config.max_bins)
        spec.n_bins_initial = len(splits) + 1
        good, bad = _bin_counts(np.searchsorted(splits, ordinal, side="left"), y[mask], len(splits) + 1)
        spec.monotone_before = is_monotone(bad / np.maximum(good + bad, 1))
        if self.config.monotonic:
            splits = merge_to_monotonic(ordinal, y[mask], splits)
        ids = np.searchsorted(splits, np.arange(len(categories), dtype=float), side="left")
        groups: list[list[str]] = [[] for _ in range(len(splits) + 1)]
        for cat, i in zip(categories, ids):
            groups[int(i)].append(cat)
        spec.groups = [g for g in groups if g]
        return spec

    def fit(self, X: pd.DataFrame, y: pd.Series | np.ndarray, categorical: list[str] | None = None) -> Binner:
        y_all = np.asarray(y, dtype=float)
        self.categorical_ = [c for c in (categorical or []) if c in X.columns]
        n = len(X)
        if self.config.sample_size and n > self.config.sample_size:
            rng = np.random.default_rng(self.random_state)
            idx = np.sort(rng.choice(n, size=int(self.config.sample_size), replace=False))
        else:
            idx = np.arange(n)
        X_s, y_s = X.iloc[idx], y_all[idx]
        self.bins_ = {}
        self.fallback_features_ = []
        for col in X.columns:
            if col in self.categorical_:
                spec = self._fit_categorical(col, X_s[col], y_s)
            else:
                spec = self._fit_numeric(col, X_s[col], y_s)
            spec.fit_woe(X[col], y_all)  # WOE / IV on the FULL training set
            self.bins_[col] = spec
        return self

    def transform(self, X: pd.DataFrame, features: list[str] | None = None) -> pd.DataFrame:
        cols = features or list(self.bins_)
        return pd.DataFrame({c: self.bins_[c].transform_woe(X[c]) for c in cols}, index=X.index)

    def transform_bins(self, X: pd.DataFrame, features: list[str] | None = None) -> pd.DataFrame:
        cols = features or list(self.bins_)
        return pd.DataFrame({c: self.bins_[c].bin_ids(X[c]) for c in cols}, index=X.index)

    def iv_table(self) -> pd.DataFrame:
        rows = []
        for name, spec in self.bins_.items():
            counts = np.asarray(spec.counts, dtype=float)
            regular = counts[: spec.n_regular]
            rows.append(
                {
                    "feature": name,
                    "kind": spec.kind,
                    "backend": spec.backend,
                    "iv": spec.iv,
                    "n_bins": spec.n_regular + (1 if spec.has_missing else 0),
                    "n_bins_initial": spec.n_bins_initial,
                    "monotone_before": spec.monotone_before,
                    "monotone_after": spec.monotone_after,
                    "max_bin_share": float(counts.max() / counts.sum()) if counts.sum() else np.nan,
                    "missing_share": float(counts[-1] / counts.sum()) if counts.sum() else np.nan,
                    "largest_regular_bin_share": float(regular.max() / counts.sum()) if counts.sum() and len(regular) else np.nan,
                }
            )
        return pd.DataFrame(rows).sort_values("iv", ascending=False).reset_index(drop=True)

    def bin_tables(self, features: list[str] | None = None) -> pd.DataFrame:
        cols = features or list(self.bins_)
        return pd.concat([self.bins_[c].table() for c in cols], ignore_index=True)

    def to_dict(self) -> dict[str, Any]:
        return {"backend": self.backend, "features": {k: v.to_dict() for k, v in self.bins_.items()}}
