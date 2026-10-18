"""Shared fixtures. Tests never read data/raw; everything is synthetic."""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from scorecard.adapters.synthetic import make_synthetic_loans
from scorecard.config import Config, config_from_dict


@pytest.fixture(scope="session")
def synthetic_frame() -> pd.DataFrame:
    return make_synthetic_loans(n_rows=8000, random_state=7, n_months=30)


@pytest.fixture()
def small_config(tmp_path) -> Config:
    return config_from_dict(
        {
            "dataset": {"adapter": "synthetic", "options": {"n_rows": 6000, "n_months": 30, "random_state": 3}},
            "sample": {"min_issue_date": None},
            "binning": {"backend": "tree", "sample_size": 6000},
            "model": {"cv_folds": 3, "cv_challenger": False, "gbdt": {"max_iter": 60}},
            "report": {"embed_figures": False},
            "output": {"dir": str(tmp_path / "out")},
        }
    )


def lendingclub_raw(n: int = 400, seed: int = 11) -> pd.DataFrame:
    """A tiny raw frame with the Lending Club column names the adapter cares about."""
    rng = np.random.default_rng(seed)
    months = pd.period_range("2010-01", "2018-12", freq="M")
    issue = rng.choice(months, n)
    term = rng.choice([" 36 months", " 60 months"], n, p=[0.7, 0.3])
    status = rng.choice(
        ["Fully Paid", "Charged Off", "Current", "Late (31-120 days)", "In Grace Period", "Default"],
        n,
        p=[0.6, 0.15, 0.17, 0.04, 0.03, 0.01],
    )
    frame = pd.DataFrame(
        {
            "id": [str(100000 + i) for i in range(n)],
            "member_id": np.nan,
            "loan_amnt": rng.choice([5000.0, 10000.0, 15000.0, 20000.0], n),
            "funded_amnt": np.nan,
            "funded_amnt_inv": np.nan,
            "term": term,
            "int_rate": rng.uniform(6, 25, n).round(2),
            "installment": rng.uniform(100, 800, n).round(2),
            "grade": rng.choice(list("ABCDEFG"), n),
            "sub_grade": rng.choice(["A1", "B2", "C3", "D4"], n),
            "emp_title": rng.choice(["Nurse", "Teacher", None], n),
            "emp_length": rng.choice(["10+ years", "< 1 year", "3 years", "n/a", None], n),
            "home_ownership": rng.choice(["MORTGAGE", "RENT", "OWN", "ANY"], n, p=[0.5, 0.4, 0.095, 0.005]),
            "annual_inc": rng.choice([0.0, 30000.0, 60000.0, 120000.0], n, p=[0.02, 0.3, 0.5, 0.18]),
            "verification_status": rng.choice(["Verified", "Not Verified", "Source Verified"], n),
            "issue_d": [p.strftime("%b-%Y") for p in issue],
            "loan_status": status,
            "pymnt_plan": "n",
            "url": "https://x",
            "desc": None,
            "purpose": rng.choice(["debt_consolidation", "credit_card", "car", "wedding"], n, p=[0.6, 0.3, 0.095, 0.005]),
            "title": "x",
            "zip_code": "123xx",
            "addr_state": rng.choice(["CA", "TX", "NY", "WY"], n, p=[0.5, 0.3, 0.195, 0.005]),
            "dti": rng.uniform(0, 40, n).round(2),
            "delinq_2yrs": rng.poisson(0.2, n).astype(float),
            "earliest_cr_line": [(p - int(rng.integers(36, 300))).strftime("%b-%Y") for p in issue],
            "fico_range_low": rng.choice([660.0, 680.0, 700.0, 740.0], n),
            "fico_range_high": np.nan,
            "revol_util": rng.uniform(0, 100, n).round(1),
            "total_pymnt": np.nan,
            "total_rec_prncp": np.nan,
            "total_rec_int": rng.uniform(100, 3000, n).round(2),
            "total_rec_late_fee": 0.0,
            "recoveries": np.nan,
            "collection_recovery_fee": np.nan,
            "last_pymnt_d": [(p + int(rng.integers(1, 36))).strftime("%b-%Y") for p in issue],
            "last_fico_range_high": 700.0,
            "last_fico_range_low": 696.0,
            "application_type": rng.choice(["Individual", "Joint App"], n, p=[0.97, 0.03]),
            "annual_inc_joint": np.nan,
            "hardship_flag": "N",
            "settlement_status": None,
            "debt_settlement_flag": "N",
            "initial_list_status": rng.choice(["w", "f"], n),
            "disbursement_method": "Cash",
            "mths_since_last_delinq": np.where(rng.random(n) < 0.5, rng.integers(1, 80, n), np.nan),
        }
    )
    frame["funded_amnt"] = frame["loan_amnt"]
    frame["funded_amnt_inv"] = frame["loan_amnt"] - 25
    frame["fico_range_high"] = frame["fico_range_low"] + 4
    charged = frame["loan_status"].isin(["Charged Off", "Default"])
    frame["total_rec_prncp"] = np.where(charged, frame["loan_amnt"] * 0.4, frame["loan_amnt"])
    frame["recoveries"] = np.where(charged, 500.0, 0.0)
    frame["collection_recovery_fee"] = np.where(charged, 80.0, 0.0)
    frame["total_pymnt"] = frame["total_rec_prncp"] + frame["total_rec_int"] + frame["total_rec_late_fee"] + frame["recoveries"]
    # Early loans under the old credit policy + a summary row like the real file.
    policy = frame.index[:6]
    frame.loc[policy, "loan_status"] = "Does not meet the credit policy. Status:Fully Paid"
    summary = {c: np.nan for c in frame.columns}
    summary["id"] = "Total amount funded in policy code 1: 123"
    frame = pd.concat([frame, pd.DataFrame([summary])], ignore_index=True)
    frame.attrs["all_columns"] = list(frame.columns)
    return frame
