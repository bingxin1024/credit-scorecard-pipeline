"""Phase 2: strategy (cut-offs, profit, swap set), monitoring (PSI / CSI / vintage), checks.
Synthetic data only."""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from scorecard import monitor, strategy
from scorecard.adapters.base import ISSUE_DATE, TARGET
from scorecard.config import config_from_dict
from scorecard.pipeline import run
from scorecard.split import OOT, TEST


@pytest.fixture(scope="module")
def two_variant_result(tmp_path_factory):
    cfg = config_from_dict(
        {
            "dataset": {"adapter": "synthetic", "options": {"n_rows": 8000, "n_months": 30, "random_state": 5}},
            "sample": {"min_issue_date": None},
            "features": {"use_platform_rating": [False, True]},
            "binning": {"backend": "tree", "sample_size": 8000},
            "model": {"cv_folds": 2, "cv_challenger": False, "gbdt": {"max_iter": 40}},
            "report": {"embed_figures": False},
            "output": {"dir": str(tmp_path_factory.mktemp("phase2") / "out")},
        }
    )
    return run(cfg)


def test_sections_5_to_7_render_for_both_variants(two_variant_result):
    out = two_variant_result.output_dir
    html = (out / "report.html").read_text(encoding="utf-8")
    md = (out / "report.md").read_text(encoding="utf-8")
    assert "（本阶段未实现）" not in html and "（本阶段未实现）" not in md
    for text in ("5.2 候选 cut-off", "5.3 约束下的最优 cut-off", "利润最大化 cut-off", "swap-in", "6.1 score PSI", "6.2 入模特征 CSI", "vintage", "7.1 检查清单", "两套模型对比", "2.3b 时间稳定性"):
        assert text in md, text
    assert "[含平台评级]" in md and "[不含平台评级]" in md
    assert "nan" not in md.replace("nanoseconds", "").lower().replace("financ", "")
    for name in ("strategy_cutoffs.csv", "strategy_swap_set.csv", "strategy_profit.csv", "monitor_score_psi.csv", "monitor_csi.csv", "monitor_vintage.csv", "checks.csv"):
        assert (out / name).exists(), name
    figures = {p.name for p in (out / "figures").glob("*.png")}
    assert {"08_approval_curve_no_platform_rating.png", "09_profit_curve_with_platform_rating.png", "10_score_psi_no_platform_rating.png", "11_csi_with_platform_rating.png", "12_vintage.png"} <= figures


def test_cutoff_table_is_monotone_and_bands_add_up(two_variant_result):
    st = two_variant_result.strategy
    assert st["has_net_cash"] and st["baseline"]["kind"] == "platform_grade" and st["segments"] == [TEST, OOT]
    for name, segs in st["variants"].items():
        for seg, d in segs.items():
            c = d["cutoffs"]
            assert list(c["target_approval_rate"]) == sorted(st["approval_rates"])
            assert (np.diff(c["cutoff_score"]) <= 0).all(), (name, seg)
            assert (np.diff(c["approval_rate"]) >= 0).all() and (np.diff(c["bad_rate_approved"]) >= 0).all()
            assert (np.abs(c["approval_rate"] - c["target_approval_rate"]) < 0.03).all()  # integer scores: close, not exact
            assert c["marginal_n"].sum() == c["n_approved"].iloc[-1]
            # approving everyone with the loosest candidate must leave rejects riskier than approved
            assert (c["bad_rate_rejected"] > c["bad_rate_approved"]).all()
            b = d["bands"]
            assert len(b) == 10 and b["n"].sum() == d["n"] and b["cum_approval_rate"].iloc[-1] == pytest.approx(1.0)
            assert b["bad_rate"].iloc[0] < b["bad_rate"].iloc[-1]
            assert b["cum_bad_rate"].iloc[-1] == pytest.approx(d["bad_rate"])


def test_profit_optimum_dominates_candidates(two_variant_result):
    st = two_variant_result.strategy
    for segs in st["variants"].values():
        for d in segs.values():
            best = d["profit"]["best_total"]
            assert best["net_cash_total"] >= d["cutoffs"]["net_cash_total"].max()
            assert best["net_cash_total"] >= d["profit"]["approve_all"]["net_cash_total"]
            assert d["profit"]["best_per_loan"]["approval_rate"] >= st["profit_min_approval_rate"]
            assert d["profit"]["best_per_loan"]["bad_rate_approved"] <= best["bad_rate_approved"]


def test_swap_set_cells_add_up(two_variant_result):
    st = two_variant_result.strategy
    for segs in st["variants"].values():
        for d in segs.values():
            sw = d["swap"]
            cells = sw["table"].set_index("cell")
            assert cells["n"].sum() == d["n"]
            assert cells.loc["both_approve", "n"] + cells.loc["swap_in", "n"] == sw["n_approved"]
            assert cells.loc["both_approve", "n"] + cells.loc["swap_out", "n"] == sw["n_approved"]  # baseline approves the same count
            assert sw["swap_in_n"] == sw["swap_out_n"] > 0
            assert sw["cutoff_score"] in set(d["cutoffs"]["cutoff_score"])
            assert len(d["swap_summary"]) == len(d["cutoffs"])


def test_swap_set_random_baseline_and_grade_order(synthetic_frame):
    rng = np.random.default_rng(0)
    order, kind = strategy.baseline_order(len(synthetic_frame), synthetic_frame["grade"], rng)
    assert kind == "platform_grade"
    grades = synthetic_frame["grade"].astype(str).to_numpy()[order]
    assert (np.diff(pd.Categorical(grades, categories=list("ABCDEFG"), ordered=True).codes) >= 0).all()
    order_r, kind_r = strategy.baseline_order(len(synthetic_frame), None, np.random.default_rng(0))
    assert kind_r == "random" and set(order_r) == set(range(len(synthetic_frame)))
    y = synthetic_frame[TARGET].to_numpy()
    scores = -synthetic_frame["dti"].to_numpy()  # any ranking works for the arithmetic
    sw = strategy.swap_set(scores, y, float(np.quantile(scores, 0.3)), order_r)
    assert sw["table"]["n"].sum() == len(y) and sw["swap_in_n"] == sw["swap_out_n"]


def test_psi_zero_for_identical_and_large_for_shift():
    rng = np.random.default_rng(1)
    train = rng.normal(600, 30, 20000).round()
    same, _ = monitor.score_psi(train, {"same": train.copy()}, 10)
    assert same["psi"].iloc[0] == pytest.approx(0.0, abs=1e-12)
    shifted, detail = monitor.score_psi(train, {"shift": train + 25}, 10)
    assert shifted["psi"].iloc[0] > 0.25
    assert len(detail) == 10 and detail["expected_pct"].sum() == pytest.approx(1.0)
    assert monitor.status(0.05, 0.1, 0.25) == "stable" and monitor.status(0.1, 0.1, 0.25) == "warn" and monitor.status(0.3, 0.1, 0.25) == "alert"


def test_csi_flags_a_shifted_feature(two_variant_result):
    result = two_variant_result
    v = result.primary
    mon = result.monitor["variants"][v.name]
    assert set(mon["csi"]["feature"]) == set(v.selected)
    assert (mon["csi"]["csi_oot"] < 0.1).all()  # synthetic drift is mild
    frame = result.frame.copy()
    oot = (result.labels == OOT).to_numpy()
    frame.loc[oot, "fico_mid"] = frame.loc[oot, "fico_mid"] - 60
    csi, detail = monitor.feature_csi(v.binner, ["fico_mid", "dti"], frame, result.labels)
    by = csi.set_index("feature")
    assert by.loc["fico_mid", "csi_oot"] > 0.25 and by.loc["dti", "csi_oot"] < 0.1
    assert by.loc["fico_mid", "csi_test"] < 0.1  # test rows were not shifted


def test_vintage_curves_are_cumulative_and_end_at_cohort_bad_rate(two_variant_result):
    vt = two_variant_result.monitor["vintage"]
    wide = vt["wide"]
    frame = two_variant_result.frame
    cohort_bad = frame.groupby(frame[ISSUE_DATE].dt.to_period("Q").astype(str))[TARGET].mean()
    assert vt["n_cohorts"] == len(cohort_bad) and vt["n_bad_missing_event"] == 0
    for cohort, row in wide.iterrows():
        values = row.dropna().to_numpy()
        assert (np.diff(values) >= -1e-12).all()
        assert values[-1] == pytest.approx(cohort_bad[cohort])


def test_checks_fire_on_planted_leakage_and_no_net_cash(tmp_path, synthetic_frame):
    frame = synthetic_frame.drop(columns=["event_date", "net_cash", "grade"]).copy()
    rng = np.random.default_rng(3)
    frame["leak"] = frame[TARGET] * 5 + rng.normal(0, 1, len(frame))  # observed after the outcome
    csv = tmp_path / "loans.csv"
    frame.to_csv(csv, index=False)
    cfg = config_from_dict(
        {
            "dataset": {"adapter": "generic", "path": str(csv), "options": {"target_col": "target", "date_col": "issue_date", "loan_amount_col": "loan_amount"}},
            "sample": {"min_issue_date": None},
            "binning": {"backend": "tree"},
            "model": {"cv_folds": 2, "cv_challenger": False, "gbdt": {"max_iter": 40}},
            "report": {"embed_figures": False},
            "output": {"dir": str(tmp_path / "out")},
        }
    )
    result = run(cfg)
    table = result.checks["table"]
    leak_rows = table[table["check"].str.contains("leakage")]
    assert (leak_rows["status"] == "fail").all() and leak_rows["detail"].str.contains("leak").all()
    assert (table[table["check"].str.contains("KS 高")]["status"] == "fail").all()
    assert result.checks["n_fail"] >= 2
    st = result.strategy
    assert not st["has_net_cash"] and st["baseline"]["kind"] == "random"
    assert st["variants"][result.primary.name][TEST]["profit"] is None
    md = (tmp_path / "out" / "report.md").read_text(encoding="utf-8")
    assert "数据不含回款信息，跳过" in md and "随机策略" in md
    assert "🔴 不通过" in md


def test_constrained_cutoffs_respect_bad_rate_cap_and_target(two_variant_result):
    st = two_variant_result.strategy
    for segs in st["variants"].values():
        for d in segs.values():
            c = d["constrained"]
            a, b = c["by_bad_rate"], c["by_approval_rate"]
            curve = d["curve"]
            assert a["feasible"]  # synthetic top bands are well below the 10 % cap
            assert a["bad_rate_approved"] <= st["max_bad_rate"]
            feasible = curve[curve["bad_rate_approved"] <= st["max_bad_rate"]]
            assert a["approval_rate"] == feasible["approval_rate"].max()
            assert abs(b["approval_rate"] - st["target_approval_rate"]) < 0.03
            assert b["cutoff_score"] == d["swap"]["cutoff_score"]
    md = (two_variant_result.output_dir / "report.md").read_text(encoding="utf-8")
    assert "cut-off（OOT，bad rate ≤ 10%）" in md


def test_time_stability_filter_drops_a_feature_populated_only_in_later_years(synthetic_frame):
    from scorecard.binning import Binner
    from scorecard.config import BinningConfig, SelectConfig
    from scorecard.select import select_features

    frame = synthetic_frame.copy()
    years = frame[ISSUE_DATE].dt.year
    frame["new_bureau_field"] = np.where(years == years.min(), np.nan, frame["dti"] * 1.5)  # unpopulated in the first year
    features = ["fico_mid", "dti", "new_bureau_field", "term"]
    y = frame[TARGET].to_numpy()
    binner = Binner(BinningConfig("tree", "chi", 0.05, 6, True, 100000)).fit(frame[features], y, [])
    cfg = SelectConfig(0.5, 0.02, 0.5, 0.7, 5.0, True, None, max_time_csi=0.25)
    res = select_features(binner, frame[features], y, cfg, issue_dates=frame[ISSUE_DATE])
    table = res.table.set_index("feature")
    assert res.time_years[0] < res.time_years[1]
    assert table.loc["new_bureau_field", "step"] == "2b_time_csi" and not table.loc["new_bureau_field", "selected"]
    assert table.loc["dti", "selected"] and table.loc["fico_mid", "time_csi"] < 0.1
    assert res.time_csi.set_index("feature").loc["new_bureau_field", "time_csi"] > 0.25
    # without issue dates the step is skipped and the shifted feature stays in the scorecard
    res2 = select_features(binner, frame[features], y, cfg)
    assert res2.time_csi is None and res2.table.set_index("feature").loc["new_bureau_field", "selected"]


def test_guardrails_dry_run_and_bad_rate_stop(tmp_path, synthetic_frame, capsys):
    from scorecard.cli import main

    csv = tmp_path / "loans.csv"
    frame = synthetic_frame.drop(columns=["event_date", "net_cash", "grade"]).copy()
    frame.to_csv(csv, index=False)
    cfg_text = (
        "dataset:\n  adapter: generic\n  path: '{path}'\n  options: {{target_col: target, date_col: issue_date, loan_amount_col: loan_amount, positive_label: {pos}}}\n"
        "sample:\n  min_issue_date: null\nbinning: {{backend: tree}}\nmodel: {{cv_folds: 2, cv_challenger: false, gbdt: {{max_iter: 40}}}}\n"
        "report: {{embed_figures: false}}\noutput: {{dir: '{out}'}}\n"
    )
    good = tmp_path / "good.yaml"
    good.write_text(cfg_text.format(path=csv.as_posix(), pos=1, out=(tmp_path / "o1").as_posix()), encoding="utf-8")
    assert main(["run", "--config", str(good), "--dry-run"]) == 0
    out = capsys.readouterr().out
    assert "dry run finished" in out and (tmp_path / "o1" / "sample_definition.csv").exists()
    assert not (tmp_path / "o1" / "report.html").exists()
    # a wrong positive label gives a bad rate of ~82 %: the run must stop with exit code 2
    bad = tmp_path / "bad.yaml"
    bad.write_text(cfg_text.format(path=csv.as_posix(), pos=0, out=(tmp_path / "o2").as_posix()), encoding="utf-8")
    assert main(["run", "--config", str(bad), "--dry-run"]) == 2
    assert "STOP" in capsys.readouterr().out
    assert main(["run", "--config", str(bad), "--dry-run", "--allow-any-bad-rate"]) == 0
