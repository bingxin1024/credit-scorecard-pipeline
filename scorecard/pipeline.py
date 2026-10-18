"""Orchestration: adapter -> split -> profile -> (binning -> select -> LR + GBDT -> scorecard) per
variant -> strategy -> monitor -> checks -> report. Collects timings and run metadata."""

from __future__ import annotations

import json
import logging
import platform
import subprocess
import time
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from scorecard import __version__
from scorecard.adapters import get_adapter_class
from scorecard.adapters.base import ISSUE_DATE, TARGET, AdapterMeta, validate_standard_frame
from scorecard.binning import Binner
from scorecard.config import Config
from scorecard.model import (
    GBDTChallenger,
    binary_metrics,
    cross_validate_challenger,
    cross_validate_scorecard,
    fit_lr,
    ks_table,
    lr_coefficient_table,
    predict_lr,
    roc_points,
)
from scorecard.profile import profile_frame
from scorecard.scorecard import Scorecard
from scorecard.select import SelectionResult, select_features
from scorecard.split import OOT, SEGMENTS, TEST, TRAIN, make_split

log = logging.getLogger("scorecard")


@dataclass
class VariantResult:
    name: str
    use_platform_rating: bool
    candidate_features: list[str]
    categorical: list[str]
    binner: Binner
    iv_table: pd.DataFrame
    selection: SelectionResult
    selected: list[str]
    coef_table: pd.DataFrame
    metrics: pd.DataFrame
    cv: dict[str, Any]
    scorecard: Scorecard
    scorecard_table: pd.DataFrame
    scores: pd.DataFrame  # one row per loan: segment, target, score, pd_lr, pd_gbdt
    roc: dict[str, pd.DataFrame]
    ks_table: pd.DataFrame
    bin_tables: pd.DataFrame
    score_auc: dict[str, float]
    challenger: GBDTChallenger | None = None
    timings: dict[str, float] = field(default_factory=dict)
    warnings: list[str] = field(default_factory=list)


@dataclass
class RunResult:
    config: Config
    meta: AdapterMeta
    frame: pd.DataFrame
    labels: pd.Series
    split_info: dict[str, Any]
    profile: dict[str, Any]
    variants: list[VariantResult]
    run_info: dict[str, Any]
    warnings: list[str] = field(default_factory=list)
    strategy: dict[str, Any] | None = None
    monitor: dict[str, Any] | None = None
    checks: dict[str, Any] | None = None
    figures: dict[str, Path] = field(default_factory=dict)
    output_dir: Path | None = None

    @property
    def primary(self) -> VariantResult:
        return self.variants[0]


class Timer:
    def __init__(self) -> None:
        self.steps: dict[str, float] = {}
        self._t0 = time.perf_counter()

    def mark(self, name: str) -> None:
        now = time.perf_counter()
        self.steps[name] = round(now - self._t0, 2)
        log.info("step %-28s %8.1fs", name, self.steps[name])
        self._t0 = now


def git_commit() -> str | None:
    try:
        out = subprocess.run(["git", "rev-parse", "--short", "HEAD"], capture_output=True, text=True, timeout=5)
        return out.stdout.strip() or None
    except Exception:  # noqa: BLE001
        return None


def _library_versions() -> dict[str, str]:
    versions: dict[str, str] = {"python": platform.python_version(), "credit-scorecard-pipeline": __version__}
    for name in ("pandas", "numpy", "sklearn", "toad", "optbinning", "matplotlib"):
        try:
            module = __import__(name)
            versions[name] = getattr(module, "__version__", "?")
        except Exception:  # noqa: BLE001
            continue
    return versions


def fit_variant(name: str, use_platform: bool, df: pd.DataFrame, labels: pd.Series, meta: AdapterMeta,
                cfg: Config) -> VariantResult:
    timer = Timer()
    warnings: list[str] = []
    exclude = set(cfg.features.exclude or [])
    features = [c for c in meta.feature_cols if c not in exclude]
    if use_platform:
        features += [c for c in meta.platform_rating_cols if c not in exclude and c not in features]
    categorical = [c for c in meta.categorical_cols if c in features]
    train = df[labels == TRAIN]
    y_train = train[TARGET].to_numpy(dtype=int)
    log.info("variant %s: %d candidate features (%d categorical), train rows %d", name, len(features), len(categorical), len(train))

    # Binning (fitted on train only)
    binner = Binner(cfg.binning, random_state=cfg.split.random_state).fit(train[features], y_train, categorical)
    iv_table = binner.iv_table()
    timer.mark("binning")

    # Selection + LR
    selection = select_features(binner, train[features], y_train, cfg.select, cfg.model.lr_C, cfg.model.lr_max_iter,
                                issue_dates=train[ISSUE_DATE] if ISSUE_DATE in train.columns else None)
    selected = selection.selected
    warnings += selection.warnings
    if not selected:
        raise RuntimeError("feature selection left no features; relax select.min_iv / max_missing")
    woe_train = binner.transform(train, selected)
    lr = fit_lr(woe_train, y_train, cfg.model.lr_C, cfg.model.lr_max_iter)
    iv_series = iv_table.set_index("feature")["iv"]
    coef_table = lr_coefficient_table(lr, selected, iv_series, selection.vif)
    timer.mark("select_and_lr")

    # Challenger on raw candidate features
    challenger = GBDTChallenger(dict(cfg.model.gbdt), categorical, cfg.split.random_state).fit(train[features], y_train)
    timer.mark("gbdt")

    # Scorecard
    card = Scorecard.from_binner(binner, selected, lr.coef_[0], float(lr.intercept_[0]), cfg.scorecard)
    scorecard_table = card.table()

    # Predictions and metrics on every segment
    scores = pd.DataFrame(index=df.index)
    scores["segment"] = labels.to_numpy()
    scores[TARGET] = df[TARGET].to_numpy()
    scores["pd_lr"] = predict_lr(lr, binner.transform(df, selected))
    scores["pd_gbdt"] = challenger.predict_proba(df[features])
    scores["score"] = card.score(df)
    scores["pd_score"] = card.score_to_pd(scores["score"])
    rows = []
    roc: dict[str, pd.DataFrame] = {}
    score_auc: dict[str, float] = {}
    for seg in SEGMENTS:
        part = scores[scores["segment"] == seg]
        if part.empty:
            continue
        for model_name, col in (("LR scorecard", "pd_lr"), ("GBDT challenger", "pd_gbdt")):
            m = binary_metrics(part[TARGET], part[col])
            rows.append({"model": model_name, "segment": seg, "n": len(part), "bad_rate": float(part[TARGET].mean()), **m})
            roc[f"{model_name}|{seg}"] = roc_points(part[TARGET], part[col])
        score_auc[seg] = binary_metrics(part[TARGET], -part["score"].to_numpy(dtype=float))["auc"]
    metrics = pd.DataFrame(rows)
    test_part = scores[scores["segment"] == TEST]
    ks = ks_table(test_part[TARGET], test_part["pd_lr"]) if not test_part.empty else pd.DataFrame()
    timer.mark("scoring")

    # Cross-validation (binning refitted per fold)
    cv: dict[str, Any] = {"lr": cross_validate_scorecard(train, y_train, selected, categorical, cfg.binning, cfg.model, cfg.split.random_state)}
    timer.mark("cv_lr")
    if cfg.model.cv_challenger:
        cv["gbdt"] = cross_validate_challenger(train[features], y_train, categorical, dict(cfg.model.gbdt), cfg.model.cv_folds, cfg.split.random_state)
        timer.mark("cv_gbdt")

    # Sanity warnings
    for seg in (TEST, OOT):
        a = metrics[(metrics["model"] == "LR scorecard") & (metrics["segment"] == seg)]
        if not a.empty and float(a["ks"].iloc[0]) > 0.9:
            warnings.append(f"{seg} KS = {float(a['ks'].iloc[0]):.3f} > 0.9，几乎肯定存在 leakage")

    return VariantResult(
        name=name,
        use_platform_rating=use_platform,
        candidate_features=features,
        categorical=categorical,
        binner=binner,
        iv_table=iv_table,
        selection=selection,
        selected=selected,
        coef_table=coef_table,
        metrics=metrics,
        cv=cv,
        scorecard=card,
        scorecard_table=scorecard_table,
        scores=scores,
        roc=roc,
        ks_table=ks,
        bin_tables=binner.bin_tables(selected),
        score_auc=score_auc,
        challenger=challenger,
        timings=timer.steps,
        warnings=warnings,
    )


class BadRateOutOfRange(RuntimeError):
    """Guardrail (SKILL.md): the sample's bad rate is outside the plausible range for a credit label."""


BAD_RATE_RANGE = (0.01, 0.40)


def sample_definition_text(meta: AdapterMeta) -> str:
    """Fixed-width sample-definition impact table, printed before any modelling starts."""
    lines = [f"{'step':>4}  {'rule':<22} {'removed':>10} {'remaining':>10} {'bad rate':>9}  description"]
    for r in meta.sample_definition_log:
        br = f"{r['bad_rate']:.2%}" if r.get("bad_rate") is not None else "-"
        lines.append(f"{r['step']:>4}  {r['rule']:<22} {r['removed']:>10,} {r['remaining']:>10,} {br:>9}  {r['description']}")
    return "\n".join(lines)


def check_bad_rate(df: pd.DataFrame, allow_any: bool = False) -> float:
    bad_rate = float(df[TARGET].mean()) if len(df) else float("nan")
    lo, hi = BAD_RATE_RANGE
    if len(df) == 0:
        raise BadRateOutOfRange("the sample definition left 0 rows; check the adapter options and sample rules")
    if not allow_any and not (lo <= bad_rate <= hi):
        raise BadRateOutOfRange(
            f"sample bad rate {bad_rate:.2%} is outside {lo:.0%}-{hi:.0%}: check the label definition / positive_label "
            "before modelling, or pass --allow-any-bad-rate to continue anyway"
        )
    return bad_rate


def run(cfg: Config, output_dir: str | Path | None = None, render: bool = True, dry_run: bool = False,
        allow_any_bad_rate: bool = False) -> RunResult | None:
    from scorecard import checks as checks_mod
    from scorecard import monitor as monitor_mod
    from scorecard import strategy as strategy_mod
    from scorecard.report import render_report

    out_dir = Path(output_dir or cfg.output.dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    started = datetime.now()
    timer = Timer()
    run_info: dict[str, Any] = {
        "config_path": cfg.source_path,
        "config_hash": cfg.hash,
        "git_commit": git_commit(),
        "timestamp": started.strftime("%Y-%m-%d %H:%M:%S"),
        "versions": _library_versions(),
        "output_dir": str(out_dir),
    }

    adapter = get_adapter_class(cfg.dataset.adapter)(cfg)
    df, meta = adapter.load()
    problems = validate_standard_frame(df, meta)
    if problems:
        raise ValueError("standard frame contract violated: " + "; ".join(problems))
    run_info["data_file"] = meta.source
    run_info["n_raw_rows"] = meta.n_raw_rows
    run_info["n_rows"] = int(len(df))
    run_info["cache_hit"] = meta.notes.get("cache_hit")
    timer.mark("load")
    # Guardrails (SKILL.md): show the sample definition first, refuse an implausible bad rate.
    log.info("sample definition (%s):\n%s", meta.source, sample_definition_text(meta))
    bad_rate = check_bad_rate(df, allow_any_bad_rate)
    if dry_run:
        pd.DataFrame(meta.sample_definition_log).to_csv(out_dir / "sample_definition.csv", index=False)
        meta.field_audit.to_csv(out_dir / "field_audit.csv", index=False)
        log.info("dry run: %d rows, bad rate %.2f%%, %d candidate features; stopping before modelling", len(df), 100 * bad_rate, len(meta.feature_cols))
        return None

    labels, split_info = make_split(df, cfg.split)
    timer.mark("split")
    features_all = [c for c in meta.feature_cols if c not in set(cfg.features.exclude or [])]
    profile = profile_frame(df, meta, features_all, meta.categorical_cols, labels, cfg.report.top_missing)
    timer.mark("profile")

    variants: list[VariantResult] = []
    for use_platform in cfg.features.variants:
        name = "with_platform_rating" if use_platform else "no_platform_rating"
        variants.append(fit_variant(name, use_platform, df, labels, meta, cfg))
    timer.mark("variants")

    result = RunResult(
        config=cfg,
        meta=meta,
        frame=df,
        labels=labels,
        split_info=split_info,
        profile=profile,
        variants=variants,
        run_info=run_info,
        warnings=list(meta.warnings) + list(split_info.get("warnings", [])) + [w for v in variants for w in v.warnings],
        output_dir=out_dir,
    )
    result.strategy = strategy_mod.analyse(result)
    timer.mark("strategy")
    result.monitor = monitor_mod.analyse(result)
    timer.mark("monitor")
    result.checks = checks_mod.run_checks(result)
    timer.mark("checks")

    write_artifacts(result, out_dir)
    timer.mark("artifacts")

    def _finalize() -> None:
        run_info["timings"] = {**timer.steps, **{f"variant.{v.name}.{k}": s for v in variants for k, s in v.timings.items()}}
        run_info["duration_seconds"] = round((datetime.now() - started).total_seconds(), 1)
        (out_dir / "run_meta.json").write_text(json.dumps(_jsonable(run_info), indent=2, ensure_ascii=False), encoding="utf-8")

    _finalize()  # the report appendix reads run_info; refreshed again after rendering
    if render:
        render_report(result, out_dir)
        timer.mark("report")
        _finalize()
    return result


def _jsonable(obj: Any) -> Any:
    if isinstance(obj, dict):
        return {str(k): _jsonable(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [_jsonable(v) for v in obj]
    if isinstance(obj, (np.bool_, bool)):
        return bool(obj)
    if isinstance(obj, (np.integer, int)):
        return int(obj)
    if isinstance(obj, (np.floating, float)):
        v = float(obj)
        return None if np.isnan(v) else v
    if isinstance(obj, (pd.Timestamp, pd.Period, datetime)):
        return str(obj)
    if isinstance(obj, Path):
        return str(obj)
    return obj


def write_artifacts(result: RunResult, out_dir: Path) -> None:
    """CSV / JSON artifacts next to the report so every number is traceable."""
    from scorecard import checks as checks_mod
    from scorecard import monitor as monitor_mod
    from scorecard import strategy as strategy_mod

    meta = result.meta
    pd.DataFrame(meta.sample_definition_log).to_csv(out_dir / "sample_definition.csv", index=False)
    meta.field_audit.to_csv(out_dir / "field_audit.csv", index=False)
    result.split_info["summary"].to_csv(out_dir / "split_summary.csv", index=False)
    result.profile["feature_summary"].to_csv(out_dir / "feature_summary.csv", index=False)
    result.profile["bad_rate_by_quarter"].to_csv(out_dir / "bad_rate_by_quarter.csv", index=False)
    for name, table in meta.extra_tables.items():
        table.to_csv(out_dir / f"{name}.csv", index=False)
    for v in result.variants:
        prefix = "" if len(result.variants) == 1 else f"{v.name}_"
        v.iv_table.to_csv(out_dir / f"{prefix}iv_table.csv", index=False)
        v.selection.table.to_csv(out_dir / f"{prefix}feature_selection.csv", index=False)
        v.bin_tables.to_csv(out_dir / f"{prefix}bin_tables.csv", index=False)
        v.coef_table.to_csv(out_dir / f"{prefix}lr_coefficients.csv", index=False)
        v.metrics.to_csv(out_dir / f"{prefix}model_metrics.csv", index=False)
        v.scorecard_table.to_csv(out_dir / f"{prefix}scorecard.csv", index=False)
        v.ks_table.to_csv(out_dir / f"{prefix}ks_table.csv", index=False)
        (out_dir / f"{prefix}scorecard_model.json").write_text(
            json.dumps(_jsonable(v.scorecard.to_dict()), indent=2, ensure_ascii=False), encoding="utf-8"
        )
        (out_dir / f"{prefix}cv_metrics.json").write_text(json.dumps(_jsonable(v.cv), indent=2), encoding="utf-8")
    summary = {
        "config_hash": result.config.hash,
        "n_rows": int(len(result.frame)),
        "bad_rate": float(result.frame[TARGET].mean()),
        "split": result.split_info["summary"].to_dict(orient="records"),
        "variants": {
            v.name: {
                "n_candidate_features": len(v.candidate_features),
                "n_selected": len(v.selected),
                "selected": v.selected,
                "metrics": v.metrics.to_dict(orient="records"),
                "cv": v.cv,
                "score_auc": v.score_auc,
                "scaling": v.scorecard.to_dict()["scaling"],
            }
            for v in result.variants
        },
        "warnings": result.warnings,
    }
    for mod in (strategy_mod, monitor_mod, checks_mod):
        if getattr(mod, "IMPLEMENTED", False):
            mod.write_artifacts(result, out_dir)
    if result.strategy:
        summary["strategy"] = strategy_mod.to_summary(result.strategy)
    if result.monitor:
        summary["monitor"] = monitor_mod.to_summary(result.monitor)
    if result.checks:
        summary["checks"] = {k: v for k, v in result.checks.items() if k != "table"}
        summary["checks"]["rows"] = result.checks["table"].to_dict(orient="records")
    (out_dir / "results.json").write_text(json.dumps(_jsonable(summary), indent=2, ensure_ascii=False), encoding="utf-8")
