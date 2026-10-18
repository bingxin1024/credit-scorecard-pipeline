import numpy as np
import pandas as pd

from scorecard.adapters.base import (
    EVENT_DATE,
    ISSUE_DATE,
    LOAN_AMOUNT,
    NET_CASH,
    TARGET,
    validate_standard_frame,
)
from scorecard.adapters.lendingclub import EMP_LENGTH_MAP, LendingClubAdapter, parse_term
from scorecard.config import config_from_dict
from tests.conftest import lendingclub_raw


def _adapter(min_issue="2012-01"):
    cfg = config_from_dict({"dataset": {"adapter": "lendingclub"}, "sample": {"min_issue_date": min_issue}})
    return LendingClubAdapter(cfg)


def test_sample_definition_rules_in_order():
    raw = lendingclub_raw()
    frame, meta = _adapter().transform(raw)
    rules = [r["rule"] for r in meta.sample_definition_log]
    assert rules == ["drop_summary_rows", "credit_policy", "maturity", "terminal_status", "min_issue_date", "final_sample"]
    log = {r["rule"]: r for r in meta.sample_definition_log}
    assert log["drop_summary_rows"]["removed"] == 1
    assert log["credit_policy"]["removed"] == 6
    assert log["terminal_status"]["removed"] > 0  # Current / Late / Grace are dropped
    assert log["final_sample"]["remaining"] == len(frame)
    # remaining counts are monotone non-increasing
    remaining = [r["remaining"] for r in meta.sample_definition_log]
    assert all(a >= b for a, b in zip(remaining, remaining[1:]))
    assert all(0 <= r["bad_rate"] <= 1 for r in meta.sample_definition_log if r["bad_rate"] is not None)


def test_maturity_and_target_mapping():
    raw = lendingclub_raw()
    frame, meta = _adapter(min_issue=None).transform(raw)
    # every kept loan has issue + term <= Dec 2018 (the max issue month in the fixture)
    cutoff = pd.Period("2018-12", freq="M")
    issue = frame[ISSUE_DATE].dt.to_period("M")
    assert ((issue + frame["term"].astype(int)) <= cutoff).all()
    assert set(frame[TARGET].unique()) <= {0, 1}
    assert frame[ISSUE_DATE].min() < pd.Timestamp("2012-01-01")  # min_issue_date disabled here
    assert validate_standard_frame(frame, meta) == []


def test_min_issue_date_applied_and_evidence_table():
    raw = lendingclub_raw()
    frame, meta = _adapter("2012-01").transform(raw)
    assert frame[ISSUE_DATE].min() >= pd.Timestamp("2012-01-01")
    table = meta.extra_tables["bad_rate_by_year_before_min_issue_date"]
    assert table["issue_year"].min() < 2012


def test_field_audit_groups_and_leakage_dropped():
    raw = lendingclub_raw()
    frame, meta = _adapter().transform(raw)
    audit = meta.field_audit.set_index("column")
    assert audit.loc["loan_status", "group"] == "A"
    assert audit.loc["total_pymnt", "group"] == "B" and audit.loc["total_pymnt", "decision"] == "reserved"
    assert audit.loc["last_fico_range_high", "decision"] == "drop"
    assert audit.loc["hardship_flag", "group"] == "D"
    assert audit.loc["grade", "decision"] == "platform_rating"
    assert audit.loc["annual_inc_joint", "group"] == "H"
    assert audit.loc["dti", "group"] == "I"
    # every raw column appears exactly once; leakage columns are not features
    assert audit.index.is_unique and set(raw.columns) <= set(audit.index)
    for col in ("total_pymnt", "last_fico_range_high", "recoveries", "hardship_flag", "int_rate", "grade"):
        assert col not in meta.feature_cols
    assert "grade" in meta.platform_rating_cols and "grade" in frame.columns


def test_derived_features_and_parsing():
    raw = lendingclub_raw()
    frame, meta = _adapter(min_issue=None).transform(raw)
    for col in ("fico_mid", "credit_hist_months", "emp_length_years", "log_annual_inc", "loan_to_inc"):
        assert col in meta.feature_cols
    assert "fico_range_low" not in frame.columns
    assert np.allclose(frame["fico_mid"], frame["fico_mid"].round(0))
    assert (frame["credit_hist_months"] >= 36).all()
    assert set(frame["term"].dropna().unique()) <= {36.0, 60.0}
    assert frame.loc[frame["loan_to_inc"].notna(), "loan_to_inc"].gt(0).all()
    assert parse_term(" 36 months") == 36 and EMP_LENGTH_MAP["< 1 year"] == 0 and EMP_LENGTH_MAP["10+ years"] == 10
    assert str(frame["purpose"].dtype) == "category"
    # rare categories merged into OTHER
    assert "OTHER_RARE" in set(frame["purpose"].cat.categories) and "wedding" not in set(frame["purpose"].cat.categories)


def test_net_cash_definition_uses_recoveries_check():
    raw = lendingclub_raw()
    frame, meta = _adapter(min_issue=None).transform(raw)
    chk = meta.notes["net_cash_check"]
    assert chk["total_pymnt_includes_recoveries"] is True
    assert "recoveries" not in meta.notes["net_cash_definition"].split("（")[0].replace("collection_recovery_fee", "")
    assert LOAN_AMOUNT in frame and NET_CASH in frame and EVENT_DATE in frame
    bad = frame[frame[TARGET] == 1]
    assert (bad[NET_CASH] < 0).mean() > 0.9
    assert frame[ISSUE_DATE].is_monotonic_increasing


def test_net_cash_check_is_robust_to_single_outlier():
    raw = lendingclub_raw(n=3000)  # enough charged-off loans for the 99 % rule
    charged = raw.index[raw["loan_status"] == "Charged Off"][:1]
    raw.loc[charged, "total_pymnt"] += 1.5  # one row with a rounding / adjustment difference
    frame, meta = _adapter(min_issue=None).transform(raw)
    chk = meta.notes["net_cash_check"]
    assert chk["total_pymnt_includes_recoveries"] is True
    assert chk["share_within_1_if_recoveries_included"] > 0.98
    assert "+ recoveries" not in meta.notes["net_cash_definition"]


def test_terms_allowed_and_explicit_cutoff():
    cfg = config_from_dict(
        {"dataset": {"adapter": "lendingclub", "options": {"terms_allowed": [36], "data_cutoff_month": "2018-06"}}, "sample": {"min_issue_date": None}}
    )
    frame, meta = LendingClubAdapter(cfg).transform(lendingclub_raw())
    assert set(frame["term"].unique()) == {36.0}
    assert frame[ISSUE_DATE].max() <= pd.Timestamp("2015-06-01")
    assert "term_filter" in [r["rule"] for r in meta.sample_definition_log]
    assert meta.notes["data_cutoff_month"] == "2018-06"


def test_missing_leakage_group_patterns_are_readded():
    cfg = config_from_dict(
        {"dataset": {"adapter": "lendingclub", "options": {"field_groups": {"A": ["loan_status"], "G": ["grade"]}}}, "sample": {"min_issue_date": None}}
    )
    frame, meta = LendingClubAdapter(cfg).transform(lendingclub_raw())
    audit = meta.field_audit.set_index("column")
    assert audit.loc["last_fico_range_high", "decision"] == "drop"
    assert "total_pymnt" not in meta.feature_cols and "hardship_flag" not in meta.feature_cols
    assert any("field_groups" in w for w in meta.warnings)
