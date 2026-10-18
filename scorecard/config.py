"""Configuration: YAML -> typed dataclasses, with defaults, `extends` and a stable hash.

Every knob referenced in PLAN.md §9 has a default here, so a config file only has to say what
differs. `extends: default.yaml` (relative to the file) deep-merges another file underneath.
"""

from __future__ import annotations

import copy
import hashlib
import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

DEFAULTS: dict[str, Any] = {
    "dataset": {
        "adapter": "synthetic",
        "path": None,
        "nrows": None,
        "cache": True,
        "cache_dir": "data/cache",
        "options": {},
    },
    "sample": {
        "min_issue_date": "2012-01",
        "max_issue_date": None,
    },
    "split": {
        "oot_months": 6,
        "oot_fraction": 0.15,  # only used when the adapter provides no issue_date
        "train_ratio": 0.7,
        "random_state": 42,
    },
    "features": {
        # false -> one model without platform rating; true -> with; [false, true] -> both (Phase 2)
        "use_platform_rating": False,
        "exclude": [],
    },
    "binning": {
        "backend": "auto",  # auto | toad | optbinning | tree
        "method": "chi",
        "min_samples": 0.05,
        "max_bins": 6,
        "monotonic": True,
        "sample_size": 200000,
        "prebins": 200,  # continuous features are quantile pre-binned before the split search
    },
    "select": {
        "max_missing": 0.5,
        "min_iv": 0.02,
        "leakage_iv": 0.5,
        "max_corr": 0.7,
        "max_vif": 5.0,
        "drop_positive_coef": True,
        "max_features": None,
        "max_time_csi": 0.25,  # train-internal CSI (earliest vs latest issue year) above this -> dropped
    },
    "model": {
        "lr_C": 1.0,
        "lr_max_iter": 1000,
        "cv_folds": 5,
        "cv_challenger": True,
        "gbdt": {
            "learning_rate": 0.05,
            "max_iter": 300,
            "max_leaf_nodes": 8,
            "min_samples_leaf": 200,
            "l2_regularization": 1.0,
            "early_stopping": False,
        },
    },
    "scorecard": {
        "pdo": 20,
        "base_score": 600,
        "base_odds": 20,
    },
    "strategy": {
        "approval_rates": [0.5, 0.6, 0.7, 0.8, 0.9],
        "score_bands": 10,
        "target_approval_rate": 0.7,  # constrained cut-off (b) and the 2x2 swap-set table use this candidate
        "max_bad_rate": 0.10,  # constrained cut-off (a): highest approval rate with approved bad rate <= this
        "profit_min_approval_rate": 0.1,  # profit-maximising cut-offs are searched at or above this
    },
    "monitor": {
        "psi_bins": 10,
        "psi_warn": 0.10,
        "psi_alert": 0.25,
        "vintage_max_mob": 60,  # months on book shown on the vintage curves
    },
    "checks": {
        "leakage_iv": 0.5,
        "single_bin_share": 0.9,
        "ks_gap": 0.05,
        "psi_alert": 0.25,
        "missing_in_model": 0.5,
    },
    "report": {
        "title": None,
        "top_missing": 20,
        "top_woe_plots": 8,
        "embed_figures": True,
    },
    "output": {
        "dir": "outputs/run",
    },
}


def deep_merge(base: dict, override: dict) -> dict:
    out = copy.deepcopy(base)
    for key, value in (override or {}).items():
        if isinstance(value, dict) and isinstance(out.get(key), dict):
            out[key] = deep_merge(out[key], value)
        else:
            out[key] = copy.deepcopy(value)
    return out


def _load_yaml_with_extends(path: Path, _seen: tuple[Path, ...] = ()) -> dict:
    path = path.resolve()
    if path in _seen:
        raise ValueError(f"circular `extends` in config: {path}")
    raw = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    parent = raw.pop("extends", None)
    if parent:
        parent_cfg = _load_yaml_with_extends(path.parent / parent, _seen + (path,))
        return deep_merge(parent_cfg, raw)
    return raw


@dataclass
class DatasetConfig:
    adapter: str
    path: str | None
    nrows: int | None
    cache: bool
    cache_dir: str
    options: dict[str, Any] = field(default_factory=dict)


@dataclass
class SampleConfig:
    min_issue_date: str | None
    max_issue_date: str | None


@dataclass
class SplitConfig:
    oot_months: int
    oot_fraction: float
    train_ratio: float
    random_state: int


@dataclass
class FeaturesConfig:
    use_platform_rating: bool | list[bool]
    exclude: list[str]

    @property
    def variants(self) -> list[bool]:
        value = self.use_platform_rating
        if isinstance(value, list):
            return [bool(v) for v in value]
        return [bool(value)]


@dataclass
class BinningConfig:
    backend: str
    method: str
    min_samples: float
    max_bins: int
    monotonic: bool
    sample_size: int
    prebins: int = 200


@dataclass
class SelectConfig:
    max_missing: float
    min_iv: float
    leakage_iv: float
    max_corr: float
    max_vif: float
    drop_positive_coef: bool
    max_features: int | None
    max_time_csi: float = 0.25


@dataclass
class ModelConfig:
    lr_C: float
    lr_max_iter: int
    cv_folds: int
    cv_challenger: bool
    gbdt: dict[str, Any]


@dataclass
class ScorecardConfig:
    pdo: float
    base_score: float
    base_odds: float


@dataclass
class StrategyConfig:
    approval_rates: list[float]
    score_bands: int
    target_approval_rate: float = 0.7
    max_bad_rate: float = 0.10
    profit_min_approval_rate: float = 0.1


@dataclass
class MonitorConfig:
    psi_bins: int
    psi_warn: float
    psi_alert: float
    vintage_max_mob: int = 60


@dataclass
class ChecksConfig:
    leakage_iv: float
    single_bin_share: float
    ks_gap: float
    psi_alert: float
    missing_in_model: float


@dataclass
class ReportConfig:
    title: str | None
    top_missing: int
    top_woe_plots: int
    embed_figures: bool


@dataclass
class OutputConfig:
    dir: str


@dataclass
class Config:
    dataset: DatasetConfig
    sample: SampleConfig
    split: SplitConfig
    features: FeaturesConfig
    binning: BinningConfig
    select: SelectConfig
    model: ModelConfig
    scorecard: ScorecardConfig
    strategy: StrategyConfig
    monitor: MonitorConfig
    checks: ChecksConfig
    report: ReportConfig
    output: OutputConfig
    raw: dict[str, Any] = field(default_factory=dict, repr=False)
    source_path: str | None = None

    @property
    def hash(self) -> str:
        """Stable short hash of the resolved configuration (sha256 of sorted JSON)."""
        payload = json.dumps(self.raw, sort_keys=True, default=str, ensure_ascii=False)
        return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:12]

    @property
    def output_dir(self) -> Path:
        return Path(self.output.dir)


def _build(section: type, data: dict) -> Any:
    fields = set(section.__dataclass_fields__)  # type: ignore[attr-defined]
    unknown = set(data) - fields
    if unknown:
        raise ValueError(f"unknown keys in config section `{section.__name__}`: {sorted(unknown)}")
    return section(**data)


def config_from_dict(data: dict, source_path: str | None = None) -> Config:
    resolved = deep_merge(DEFAULTS, data or {})
    unknown = set(resolved) - set(DEFAULTS)
    if unknown:
        raise ValueError(f"unknown top-level config sections: {sorted(unknown)}")
    return Config(
        dataset=_build(DatasetConfig, resolved["dataset"]),
        sample=_build(SampleConfig, resolved["sample"]),
        split=_build(SplitConfig, resolved["split"]),
        features=_build(FeaturesConfig, resolved["features"]),
        binning=_build(BinningConfig, resolved["binning"]),
        select=_build(SelectConfig, resolved["select"]),
        model=_build(ModelConfig, resolved["model"]),
        scorecard=_build(ScorecardConfig, resolved["scorecard"]),
        strategy=_build(StrategyConfig, resolved["strategy"]),
        monitor=_build(MonitorConfig, resolved["monitor"]),
        checks=_build(ChecksConfig, resolved["checks"]),
        report=_build(ReportConfig, resolved["report"]),
        output=_build(OutputConfig, resolved["output"]),
        raw=resolved,
        source_path=source_path,
    )


def load_config(path: str | Path) -> Config:
    path = Path(path)
    data = _load_yaml_with_extends(path)
    return config_from_dict(data, source_path=str(path))
