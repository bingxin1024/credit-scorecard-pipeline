import numpy as np
import pandas as pd
import pytest

from scorecard.adapters.base import TARGET
from scorecard.binning import Binner, BinSpec, is_monotone, merge_small_bins, merge_to_monotonic
from scorecard.config import BinningConfig


def _cfg(**over) -> BinningConfig:
    base = dict(backend="tree", method="chi", min_samples=0.05, max_bins=6, monotonic=True, sample_size=100000)
    base.update(over)
    return BinningConfig(**base)


def test_merge_to_monotonic_removes_zigzag():
    rng = np.random.default_rng(0)
    x = rng.uniform(0, 10, 20000)
    # bad rate goes 0.1, 0.3, 0.2, 0.5, 0.6 across 5 bins -> zigzag at bin 3
    rates = np.select([x < 2, x < 4, x < 6, x < 8], [0.1, 0.3, 0.2, 0.5], 0.6)
    y = (rng.random(len(x)) < rates).astype(float)
    splits = np.array([2.0, 4.0, 6.0, 8.0])
    out = merge_to_monotonic(x, y, splits)
    ids = np.searchsorted(out, x, side="left")
    bad_rate = pd.Series(y).groupby(ids).mean().to_numpy()
    assert is_monotone(bad_rate)
    assert 2 <= len(out) + 1 <= 5


def test_merge_small_bins_respects_min_size():
    x = np.concatenate([np.zeros(10), np.ones(990)])
    y = np.concatenate([np.ones(10), np.zeros(990)])
    out = merge_small_bins(x, y, np.array([0.5]), min_bin_size=50)
    assert len(out) == 0


def test_numeric_bins_monotone_and_woe_direction(synthetic_frame):
    X = synthetic_frame[["fico_mid"]]
    y = synthetic_frame[TARGET].to_numpy()
    binner = Binner(_cfg()).fit(X, y, [])
    spec = binner.bins_["fico_mid"]
    table = spec.table()
    assert spec.monotone_after
    assert spec.iv > 0.05
    # higher fico -> lower bad rate -> higher WOE (WOE = ln(good/bad))
    assert table["bad_rate"].is_monotonic_decreasing
    assert table["woe"].is_monotonic_increasing
    assert abs(sum(table["share"]) - 1) < 1e-9


def test_missing_gets_own_bin_and_unseen_category_maps_to_missing(synthetic_frame):
    X = synthetic_frame[["revol_util", "purpose"]]
    y = synthetic_frame[TARGET].to_numpy()
    binner = Binner(_cfg()).fit(X, y, ["purpose"])
    spec = binner.bins_["revol_util"]
    assert spec.has_missing and spec.labels()[-1] == "Missing"
    ids = spec.bin_ids(pd.Series([np.nan, 50.0]))
    assert ids[0] == spec.n_regular and ids[1] < spec.n_regular
    cat = binner.bins_["purpose"]
    assert cat.kind == "categorical" and sum(len(g) for g in cat.groups) == synthetic_frame["purpose"].nunique()
    unseen = cat.bin_ids(pd.Series(["never_seen_before"], dtype="object"))
    assert unseen[0] == cat.n_regular and cat.transform_woe(pd.Series(["never_seen_before"]))[0] == 0.0


def test_categorical_groups_ordered_by_bad_rate(synthetic_frame):
    X = synthetic_frame[["home_ownership"]]
    y = synthetic_frame[TARGET].to_numpy()
    binner = Binner(_cfg(min_samples=0.01)).fit(X, y, ["home_ownership"])
    table = binner.bins_["home_ownership"].table()
    regular = table[table["bin"] != "Missing"]
    assert regular["bad_rate"].is_monotonic_increasing


def test_iv_table_and_transform_shapes(synthetic_frame):
    features = ["fico_mid", "dti", "purpose", "noise_feature", "mostly_missing"]
    y = synthetic_frame[TARGET].to_numpy()
    binner = Binner(_cfg(sample_size=3000)).fit(synthetic_frame[features], y, ["purpose"])
    iv = binner.iv_table()
    assert list(iv.columns[:4]) == ["feature", "kind", "backend", "iv"]
    assert iv["iv"].is_monotonic_decreasing
    assert iv.set_index("feature").loc["noise_feature", "iv"] < 0.02
    woe = binner.transform(synthetic_frame, features)
    assert woe.shape == (len(synthetic_frame), len(features)) and not woe.isna().any().any()
    bins = binner.transform_bins(synthetic_frame, ["fico_mid"])
    assert bins["fico_mid"].max() <= binner.bins_["fico_mid"].n_regular


def test_binspec_roundtrip(synthetic_frame):
    y = synthetic_frame[TARGET].to_numpy()
    binner = Binner(_cfg()).fit(synthetic_frame[["dti", "purpose"]], y, ["purpose"])
    for name in ("dti", "purpose"):
        spec = binner.bins_[name]
        clone = BinSpec.from_dict(spec.to_dict())
        assert np.array_equal(clone.bin_ids(synthetic_frame[name]), spec.bin_ids(synthetic_frame[name]))
        assert clone.labels() == spec.labels()


@pytest.mark.parametrize("backend", ["auto", "tree"])
def test_backend_resolution(backend, synthetic_frame):
    y = synthetic_frame[TARGET].to_numpy()
    binner = Binner(_cfg(backend=backend)).fit(synthetic_frame[["fico_mid"]], y, [])
    assert binner.backend in {"toad", "optbinning", "tree"}
    assert binner.bins_["fico_mid"].n_regular >= 2


def test_prebinning_keeps_max_bins_and_speed():
    rng = np.random.default_rng(3)
    n = 60000
    x = rng.lognormal(10, 1, n)  # tens of thousands of distinct values
    p = 1 / (1 + np.exp(-((np.log(x) - 10) * 0.8 - 1.8)))
    y = (rng.random(n) < p).astype(int)
    frame = pd.DataFrame({"x": x, "x2": rng.normal(size=n)})
    binner = Binner(_cfg(backend="auto", max_bins=4, sample_size=n)).fit(frame, y, [])
    for spec in binner.bins_.values():
        assert spec.n_regular <= 4
    spec = binner.bins_["x"]
    assert spec.n_regular >= 3 and spec.monotone_after and spec.iv > 0.3
    # every split is a value that actually occurs in the data range
    assert all(x.min() <= s < x.max() for s in spec.splits)


def test_left_closed_splits_are_converted_to_right_closed():
    """toad / optbinning mean `lower bin = x < s`; the engine must reproduce the same row assignment."""
    from scorecard.binning import left_closed_to_right_closed

    x = np.array([0, 0, 0, 1, 1, 2, 3, 5, 8], dtype=float)
    converted = left_closed_to_right_closed(np.array([1.0, 3.0]), x)
    assert list(converted) == [0.0, 2.0]
    lib_ids = np.digitize(x, [1.0, 3.0])  # library semantics
    engine_ids = np.searchsorted(converted, x, side="left")
    assert np.array_equal(lib_ids, engine_ids)
    # a split below every value is dropped instead of producing an empty bin
    assert list(left_closed_to_right_closed(np.array([-5.0, 1.0]), x)) == [0.0]


def test_integer_valued_feature_with_toad_or_tree_keeps_rows_out_of_missing_bin():
    rng = np.random.default_rng(5)
    n = 40000
    x = rng.choice([0, 1, 2, 3, 4, 5, 6, 7, 8], n, p=[0.85, 0.08, 0.03, 0.01, 0.01, 0.01, 0.005, 0.0025, 0.0025]).astype(float)
    p = np.select([x == 0, x == 1], [0.12, 0.20], 0.25)
    y = (rng.random(n) < p).astype(int)
    binner = Binner(_cfg(backend="auto")).fit(pd.DataFrame({"x": x}), y, [])
    spec = binner.bins_["x"]
    assert not spec.has_missing and sum(spec.counts[: spec.n_regular]) == n
    table = spec.table()
    assert table["bad_rate"].is_monotonic_increasing and spec.iv > 0.01
    # the zero bucket (85 % of rows) is its own bin
    assert spec.labels()[0] == "<= 0"


def test_integer_categories_are_binned_not_sent_to_missing():
    rng = np.random.default_rng(8)
    n = 6000
    cat = pd.Series(pd.Categorical(rng.integers(0, 3, n)))
    y = (rng.random(n) < np.where(cat.to_numpy() == 2, 0.3, 0.1)).astype(int)
    binner = Binner(_cfg(backend="tree")).fit(pd.DataFrame({"c": cat}), y, ["c"])
    spec = binner.bins_["c"]
    assert not spec.has_missing and sum(spec.counts[: spec.n_regular]) == n
    assert spec.iv > 0.05
    assert spec.bin_ids(pd.Series(pd.Categorical([2, 0, None])))[2] == spec.n_regular


def test_empty_bins_and_all_missing_features_are_neutral():
    from scorecard.binning import BinSpec

    y = np.array([1] * 150 + [0] * 850)
    spec = BinSpec(name="m", kind="numeric").fit_woe(pd.Series([np.nan] * 1000), y)
    assert spec.iv == 0.0 and spec.woe[0] == 0.0 and spec.transform_woe(pd.Series([5.0]))[0] == 0.0
    # populated bins keep the textbook WOE exactly
    x = pd.Series(np.r_[np.zeros(500), np.ones(500)])
    yy = np.r_[np.ones(100), np.zeros(400), np.ones(50), np.zeros(450)]
    spec = BinSpec(name="n", kind="numeric", splits=[0.0]).fit_woe(x, yy)
    expected = np.log((400 / 850) / (100 / 150))
    assert abs(spec.woe[0] - expected) < 1e-12
