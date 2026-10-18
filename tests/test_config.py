from pathlib import Path

import pytest

from scorecard.config import DEFAULTS, config_from_dict, load_config

ROOT = Path(__file__).resolve().parents[1]


def test_defaults_match_plan_section_9():
    cfg = config_from_dict({})
    assert cfg.sample.min_issue_date == "2012-01"
    assert cfg.split.oot_months == 6 and cfg.split.train_ratio == 0.7 and cfg.split.random_state == 42
    assert cfg.binning.method == "chi" and cfg.binning.min_samples == 0.05 and cfg.binning.sample_size == 200000
    assert (cfg.scorecard.pdo, cfg.scorecard.base_score, cfg.scorecard.base_odds) == (20, 600, 20)
    assert cfg.features.variants == [False]


def test_extends_and_override():
    cfg = load_config(ROOT / "configs" / "lendingclub.yaml")
    assert cfg.dataset.adapter == "lendingclub"
    assert cfg.output.dir == "outputs/lendingclub"
    assert cfg.binning.max_bins == DEFAULTS["binning"]["max_bins"]
    assert "field_groups" in cfg.dataset.options


def test_hash_is_stable_and_sensitive():
    a = config_from_dict({"split": {"oot_months": 6}})
    b = config_from_dict({"split": {"oot_months": 6}})
    c = config_from_dict({"split": {"oot_months": 3}})
    assert a.hash == b.hash and len(a.hash) == 12
    assert a.hash != c.hash


def test_unknown_key_rejected():
    with pytest.raises(ValueError):
        config_from_dict({"split": {"oot_month": 6}})
    with pytest.raises(ValueError):
        config_from_dict({"splits": {}})


def test_variants_list():
    cfg = config_from_dict({"features": {"use_platform_rating": [False, True]}})
    assert cfg.features.variants == [False, True]
