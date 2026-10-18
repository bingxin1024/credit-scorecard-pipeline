"""Synthetic loan-level data for tests, CI and a no-data demo.

Generates a frame that exercises every optional part of the contract: issue dates over several
years (OOT split, bad rate by quarter), an ordered platform grade, numeric + categorical features
with missing values, a pure-noise feature, `loan_amount` / `net_cash` / `event_date`.
"""

from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd

from scorecard.adapters.base import (
    DERIVED,
    EVENT_DATE,
    ISSUE_DATE,
    KEEP,
    LOAN_AMOUNT,
    NET_CASH,
    PLATFORM,
    RESERVED,
    TARGET,
    Adapter,
    AdapterMeta,
    SampleLog,
)


def make_synthetic_loans(n_rows: int = 20000, random_state: int = 42, n_months: int = 36,
                         base_bad_rate: float = 0.15) -> pd.DataFrame:
    rng = np.random.default_rng(random_state)
    start = pd.Timestamp("2015-01-01")
    month_offsets = rng.integers(0, n_months, size=n_rows)
    issue = pd.to_datetime(start) + pd.to_timedelta(month_offsets * 30.4375, unit="D")
    issue = issue.to_period("M").to_timestamp()

    fico = rng.normal(700, 35, n_rows).clip(600, 850).round()
    dti = rng.gamma(4, 5, n_rows).clip(0, 60)
    income = np.exp(rng.normal(11.0, 0.5, n_rows)).round(-2)
    util = rng.beta(2, 2, n_rows) * 100
    inq = rng.poisson(0.8, n_rows).astype(float)
    delinq = rng.poisson(0.3, n_rows).astype(float)
    hist_months = rng.gamma(6, 30, n_rows).round()
    noise = rng.normal(0, 1, n_rows)
    loan_amount = rng.choice([5000, 8000, 10000, 12000, 15000, 20000, 25000, 30000], n_rows).astype(float)
    term = rng.choice([36.0, 60.0], n_rows, p=[0.75, 0.25])
    purpose = rng.choice(["debt_consolidation", "credit_card", "home_improvement", "other", "car", "medical"],
                         n_rows, p=[0.55, 0.22, 0.08, 0.08, 0.04, 0.03])
    home = rng.choice(["MORTGAGE", "RENT", "OWN"], n_rows, p=[0.5, 0.4, 0.1])

    # Coefficients are deliberately moderate so that no single feature reaches IV 0.5 (the engine
    # treats IV > 0.5 as a leakage suspect) and the demo report's section 7 checks all pass.
    logit = (
        np.log(base_bad_rate / (1 - base_bad_rate))
        - 0.019 * (fico - 700)
        + 0.028 * (dti - 20)
        + 0.011 * (util - 50)
        + 0.30 * (inq - 0.8)
        + 0.40 * (delinq - 0.3)
        - 0.0024 * (hist_months - 180)
        + 0.45 * (term == 60) - 0.11
        + np.where(purpose == "small_business", 0.6, 0.0)
        + np.where(home == "RENT", 0.2, 0.0) - 0.08
        + 0.0015 * (month_offsets - n_months / 2)  # mild drift over time
    )
    p = 1 / (1 + np.exp(-logit))
    target = (rng.random(n_rows) < p).astype(int)

    # Platform grade: ordered, correlated with risk (built from the true logit plus noise).
    grade_score = logit + rng.normal(0, 0.9, n_rows)
    grade_idx = pd.qcut(grade_score, 7, labels=False)
    grade = np.array(list("ABCDEFG"), dtype=object)[grade_idx]

    # Realised cash flow: goods repay principal + interest, bads lose part of principal.
    rate = 0.08 + 0.02 * grade_idx
    interest = loan_amount * rate * (term / 12) * 0.55
    net_cash = np.where(target == 1, -loan_amount * rng.uniform(0.3, 0.8, n_rows), interest)
    months_to_event = np.where(target == 1, rng.integers(3, 30, n_rows), term.astype(int))
    event = (issue.to_period("M") + months_to_event).to_timestamp()

    frame = pd.DataFrame(
        {
            TARGET: target,
            ISSUE_DATE: issue,
            EVENT_DATE: event,
            LOAN_AMOUNT: loan_amount,
            NET_CASH: net_cash.round(2),
            "grade": pd.Categorical(grade, categories=list("ABCDEFG"), ordered=True),
            "fico_mid": fico,
            "dti": dti.round(2),
            "annual_inc": income,
            "revol_util": util.round(1),
            "inq_last_6mths": inq,
            "delinq_2yrs": delinq,
            "credit_hist_months": hist_months,
            "term": term,
            "noise_feature": noise.round(3),
            "purpose": pd.Categorical(purpose),
            "home_ownership": pd.Categorical(home),
            "loan_amnt": loan_amount,
        }
    )
    # Missing values: MCAR in one numeric, informative missing in another (no delinquency -> NaN).
    frame.loc[rng.random(n_rows) < 0.08, "revol_util"] = np.nan
    months_since = rng.integers(1, 80, n_rows).astype(float)
    frame["mths_since_last_delinq"] = np.where(delinq > 0, months_since, np.nan)
    # A feature that is almost entirely missing (should be dropped by max_missing).
    frame["mostly_missing"] = np.where(rng.random(n_rows) < 0.05, rng.normal(size=n_rows), np.nan)
    return frame.sort_values(ISSUE_DATE, kind="stable").reset_index(drop=True)


class SyntheticAdapter(Adapter):
    name = "synthetic"
    version = "1"

    def load_raw(self) -> pd.DataFrame:
        return make_synthetic_loans(
            n_rows=int(self.options.get("n_rows", 20000)),
            random_state=int(self.options.get("random_state", self.config.split.random_state)),
            n_months=int(self.options.get("n_months", 36)),
            base_bad_rate=float(self.options.get("base_bad_rate", 0.15)),
        )

    def transform(self, raw: pd.DataFrame, source: str = "synthetic") -> tuple[pd.DataFrame, AdapterMeta]:
        log = SampleLog()
        n0 = len(raw)
        df = raw[raw[TARGET].notna()].copy()
        log.add("drop_missing_target", "剔除 target 缺失的行", n0, len(df), float(df[TARGET].mean()))
        min_issue = self.config.sample.min_issue_date
        if min_issue and ISSUE_DATE in df:
            n_before = len(df)
            df = df[df[ISSUE_DATE] >= pd.Timestamp(min_issue)]
            log.add("min_issue_date", f"只保留 issue_date >= {min_issue}", n_before, len(df), float(df[TARGET].mean()))
        log.add("final_sample", "最终样本量与 bad rate", len(df), len(df), float(df[TARGET].mean()))

        reserved = {TARGET, ISSUE_DATE, EVENT_DATE, LOAN_AMOUNT, NET_CASH}
        platform = ["grade"] if "grade" in df else []
        feature_cols = [c for c in df.columns if c not in reserved and c not in platform]
        categorical = [c for c in df.columns if isinstance(df[c].dtype, pd.CategoricalDtype)]
        rows: list[dict[str, Any]] = []
        for col in df.columns:
            if col in reserved:
                rows.append(dict(column=col, group="A", decision=RESERVED, reason="保留列（target / 日期 / 金额）"))
            elif col in platform:
                rows.append(dict(column=col, group="G", decision=PLATFORM, reason="平台评级"))
            elif col == "noise_feature":
                rows.append(dict(column=col, group="I", decision=KEEP, reason="纯噪声特征（应被 IV 筛掉）"))
            else:
                rows.append(dict(column=col, group="I", decision=KEEP, reason="合成特征"))
        audit = pd.DataFrame(rows)
        audit["group_name"] = audit["group"].map({"A": "reserved", "G": "platform rating", "I": "candidate", "X": DERIVED})
        meta = AdapterMeta(
            name=self.name,
            source=source,
            n_raw_rows=n0,
            n_raw_cols=raw.shape[1],
            feature_cols=feature_cols,
            categorical_cols=categorical,
            sample_definition_log=log.as_list(),
            field_audit=audit,
            platform_rating_cols=platform,
            platform_grade_col="grade" if platform else None,
            notes={"generator": "scorecard.adapters.synthetic.make_synthetic_loans"},
        )
        return df.reset_index(drop=True), meta
