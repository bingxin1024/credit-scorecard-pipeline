import numpy as np
import pandas as pd

from scorecard.adapters.base import ISSUE_DATE, TARGET
from scorecard.binning import Binner
from scorecard.config import BinningConfig, SelectConfig, SplitConfig
from scorecard.select import select_features
from scorecard.split import OOT, TEST, TRAIN, make_split


def test_time_split_takes_last_months_as_oot(synthetic_frame):
    labels, info = make_split(synthetic_frame, SplitConfig(oot_months=6, oot_fraction=0.15, train_ratio=0.7, random_state=1))
    assert info["method"] == "time"
    last = synthetic_frame[ISSUE_DATE].dt.to_period("M").max()
    oot_dates = synthetic_frame.loc[labels == OOT, ISSUE_DATE].dt.to_period("M")
    rest_dates = synthetic_frame.loc[labels != OOT, ISSUE_DATE].dt.to_period("M")
    assert oot_dates.min() == last - 5 and rest_dates.max() == last - 6
    n_rest = (labels != OOT).sum()
    assert abs((labels == TRAIN).sum() / n_rest - 0.7) < 0.01
    # stratified: train and test bad rates close
    y = synthetic_frame[TARGET]
    assert abs(y[labels == TRAIN].mean() - y[labels == TEST].mean()) < 0.01
    assert set(info["summary"]["segment"]) == {TRAIN, TEST, OOT}


def test_split_without_issue_date_falls_back_to_stratified_holdout(synthetic_frame):
    frame = synthetic_frame.drop(columns=[ISSUE_DATE])
    labels, info = make_split(frame, SplitConfig(oot_months=6, oot_fraction=0.2, train_ratio=0.7, random_state=1))
    assert info["method"] == "stratified_holdout"
    assert abs((labels == OOT).mean() - 0.2) < 0.01


def test_selection_drops_missing_noise_and_duplicates(synthetic_frame):
    frame = synthetic_frame.copy()
    frame["fico_copy"] = frame["fico_mid"] * 1.0001  # perfectly correlated duplicate
    features = ["fico_mid", "fico_copy", "dti", "revol_util", "noise_feature", "mostly_missing", "purpose", "term"]
    y = frame[TARGET].to_numpy()
    binner = Binner(BinningConfig("tree", "chi", 0.05, 6, True, 100000)).fit(frame[features], y, ["purpose"])
    res = select_features(binner, frame[features], y, SelectConfig(0.5, 0.02, 0.5, 0.7, 5.0, True, None))
    table = res.table.set_index("feature")
    assert table.loc["mostly_missing", "step"] == "1_missing"
    assert table.loc["noise_feature", "step"] == "2_iv"
    assert table.loc["fico_copy", "step"] == "3_corr" or table.loc["fico_mid", "step"] == "3_corr"
    assert ("fico_mid" in res.selected) != ("fico_copy" in res.selected)
    assert "dti" in res.selected and res.vif is not None
    assert (res.table["selected"] == res.table["feature"].isin(res.selected)).all()


def test_max_features_cap(synthetic_frame):
    features = ["fico_mid", "dti", "revol_util", "purpose", "term", "inq_last_6mths"]
    y = synthetic_frame[TARGET].to_numpy()
    binner = Binner(BinningConfig("tree", "chi", 0.05, 6, True, 100000)).fit(synthetic_frame[features], y, ["purpose"])
    res = select_features(binner, synthetic_frame[features], y, SelectConfig(0.5, 0.02, 0.5, 0.7, 5.0, True, 3))
    assert len(res.selected) <= 3
    assert (res.table[res.table["step"] == "4_max_features"].shape[0]) >= 1


def test_metrics_helpers():
    from scorecard.model import binary_metrics, ks_table

    rng = np.random.default_rng(0)
    y = rng.integers(0, 2, 5000)
    s = y + rng.normal(0, 1, 5000)
    m = binary_metrics(y, s)
    assert 0.7 < m["auc"] < 0.9 and 0 < m["ks"] < 1 and abs(m["gini"] - (2 * m["auc"] - 1)) < 1e-12
    t = ks_table(y, s, 10)
    assert len(t) == 10 and abs(t["ks"].max() - m["ks"]) < 0.05
    assert pd.Series(t["cum_bad_share"]).is_monotonic_increasing


def test_gbdt_challenger_caps_categorical_levels():
    from scorecard.model import GBDTChallenger

    rng = np.random.default_rng(1)
    n = 3000
    frame = pd.DataFrame({"c": pd.Categorical(rng.integers(0, 400, n).astype(str)), "x": rng.normal(size=n)})
    y = (rng.random(n) < 0.2).astype(int)
    model = GBDTChallenger({"max_iter": 5}, ["c"], 0).fit(frame, y)
    assert len(model.categories_["c"]) == 255 and model.categories_["c"][-1] == GBDTChallenger.OTHER_CODE_LABEL
    p = model.predict_proba(pd.DataFrame({"c": pd.Categorical(["never_seen", "0"]), "x": [0.0, 1.0]}))
    assert p.shape == (2,) and np.all((p >= 0) & (p <= 1))
