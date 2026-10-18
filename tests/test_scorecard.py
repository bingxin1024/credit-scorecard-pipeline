import math

import numpy as np
from sklearn.metrics import roc_auc_score

from scorecard.adapters.base import TARGET
from scorecard.binning import Binner
from scorecard.config import BinningConfig, ScorecardConfig
from scorecard.model import fit_lr, predict_lr
from scorecard.scorecard import Scorecard, scaling_constants


def test_pdo_scaling_constants_match_plan():
    factor, offset = scaling_constants(pdo=20, base_score=600, base_odds=20)
    assert math.isclose(factor, 28.8539, abs_tol=1e-4)
    assert math.isclose(offset, 513.5614, abs_tol=1e-4)
    # 600 points <-> odds 20:1 ; +20 points -> odds double
    assert math.isclose(offset + factor * math.log(20), 600, abs_tol=1e-9)
    assert math.isclose(offset + factor * math.log(40), 620, abs_tol=1e-9)


def _fit(synthetic_frame):
    features = ["fico_mid", "dti", "revol_util", "purpose", "term"]
    y = synthetic_frame[TARGET].to_numpy()
    binner = Binner(BinningConfig("tree", "chi", 0.05, 6, True, 100000)).fit(synthetic_frame[features], y, ["purpose"])
    woe = binner.transform(synthetic_frame, features)
    lr = fit_lr(woe, y)
    card = Scorecard.from_binner(binner, features, lr.coef_[0], float(lr.intercept_[0]), ScorecardConfig(20, 600, 20))
    return features, y, binner, woe, lr, card


def test_score_equals_base_plus_bin_points(synthetic_frame):
    features, y, binner, woe, lr, card = _fit(synthetic_frame)
    scores = card.score(synthetic_frame)
    table = card.table()
    manual = np.full(len(synthetic_frame), card.base_points_int)
    for f in features:
        ids = binner.bins_[f].bin_ids(synthetic_frame[f])
        manual = manual + card.points_int[f][ids]
    assert np.array_equal(scores, manual)
    assert table.iloc[0]["variable"] == "BASE"
    assert (table["points_int"].iloc[1:].abs() <= 100).all()
    assert card.min_score <= scores.min() and scores.max() <= card.max_score


def test_all_coefficients_negative_and_integer_score_ranks_like_probability(synthetic_frame):
    features, y, binner, woe, lr, card = _fit(synthetic_frame)
    assert (lr.coef_[0] < 0).all()
    auc_prob = roc_auc_score(y, predict_lr(lr, woe))
    auc_score = roc_auc_score(y, -card.score(synthetic_frame))
    assert abs(auc_prob - auc_score) < 0.01 and auc_prob > 0.7


def test_score_to_pd_inverts_pd_to_score(synthetic_frame):
    _, _, _, _, _, card = _fit(synthetic_frame)
    p = np.array([0.01, 0.1, 0.5, 0.9])
    assert np.allclose(card.score_to_pd(card.pd_to_score(p)), p)
    assert math.isclose(float(card.score_to_pd(600)), 1 / 21, rel_tol=1e-9)


def test_scorecard_json_roundtrip(synthetic_frame):
    _, _, _, _, _, card = _fit(synthetic_frame)
    clone = Scorecard.from_dict(card.to_dict())
    assert np.array_equal(clone.score(synthetic_frame), card.score(synthetic_frame))
    assert clone.base_points_int == card.base_points_int
