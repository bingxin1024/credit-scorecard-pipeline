"""Lending Club accepted-loans adapter (PLAN.md §4).

Raw file: `accepted_2007_to_2018Q4.csv.gz` (Kaggle `wordsforthewise/lending-club`).
All dataset knowledge — column names, field groups, sample-definition rules, derived
variables — lives here and in `configs/lendingclub.yaml`. The engine never sees a raw name.
"""

from __future__ import annotations

import fnmatch
import hashlib
import pickle
import re
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from scorecard.adapters.base import (
    DERIVED,
    DROP,
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

BAD_STATUSES = ("Charged Off", "Default")
GOOD_STATUSES = ("Fully Paid",)
CREDIT_POLICY_PREFIX = "Does not meet the credit policy"

# Columns read as strings regardless of what pandas would infer.
STRING_COLUMNS = (
    "id",
    "term",
    "grade",
    "sub_grade",
    "emp_length",
    "home_ownership",
    "verification_status",
    "issue_d",
    "loan_status",
    "purpose",
    "addr_state",
    "earliest_cr_line",
    "initial_list_status",
    "application_type",
    "verification_status_joint",
    "last_pymnt_d",
    "disbursement_method",
    "sec_app_earliest_cr_line",
    "int_rate",
    "revol_util",
)

# Default field groups (PLAN.md §4.3). `configs/lendingclub.yaml` can override them; a column that
# matches no group is a candidate feature (group I). Wildcards use fnmatch syntax.
DEFAULT_FIELD_GROUPS: dict[str, list[str]] = {
    "A": ["loan_status"],
    "B": [
        "total_pymnt",
        "total_pymnt_inv",
        "total_rec_prncp",
        "total_rec_int",
        "total_rec_late_fee",
        "recoveries",
        "collection_recovery_fee",
        "out_prncp",
        "out_prncp_inv",
        "last_pymnt_d",
        "last_pymnt_amnt",
        "next_pymnt_d",
        "last_credit_pull_d",
    ],
    "C": ["last_fico_range_high", "last_fico_range_low"],
    "D": [
        "hardship_*",
        "settlement_*",
        "debt_settlement_flag*",
        "deferral_term",
        "payment_plan_start_date",
        "orig_projected_additional_accrued_interest",
        "pymnt_plan",
    ],
    "E": ["id", "member_id", "url", "desc", "title", "policy_code", "emp_title", "zip_code"],
    "F": ["funded_amnt_inv"],
    "G": ["grade", "sub_grade", "int_rate", "installment"],
    "H": ["annual_inc_joint", "dti_joint", "verification_status_joint", "revol_bal_joint", "sec_app_*"],
}

GROUP_NAMES = {
    "A": "target source",
    "B": "post-loan payment / balance (leakage)",
    "C": "post-loan credit update (leakage)",
    "D": "hardship / settlement / payment plan (leakage)",
    "E": "identifier / free text / no information",
    "F": "investor side",
    "G": "platform rating (switch: use_platform_rating)",
    "H": "joint application",
    "I": "available at application (candidate feature)",
    "X": "derived by adapter",
}

# Group-B columns that the strategy / monitoring layers need (never features).
STRATEGY_ONLY = {
    "total_pymnt": "net_cash input (strategy layer only)",
    "collection_recovery_fee": "net_cash input (strategy layer only)",
    "recoveries": "net_cash consistency check only",
    "total_rec_prncp": "net_cash consistency check only",
    "total_rec_int": "net_cash consistency check only",
    "total_rec_late_fee": "net_cash consistency check only",
    "last_pymnt_d": "event_date for vintage curves (monitor layer only)",
}

EMP_LENGTH_MAP = {
    "< 1 year": 0,
    "1 year": 1,
    "2 years": 2,
    "3 years": 3,
    "4 years": 4,
    "5 years": 5,
    "6 years": 6,
    "7 years": 7,
    "8 years": 8,
    "9 years": 9,
    "10+ years": 10,
}

CATEGORICAL_FEATURES = (
    "home_ownership",
    "verification_status",
    "purpose",
    "addr_state",
    "initial_list_status",
    "application_type",
    "disbursement_method",
    "verification_status_joint",
)
PLATFORM_CATEGORICAL = ("grade", "sub_grade")
GRADE_ORDER = list("ABCDEFG")


def _match_group(column: str, groups: dict[str, list[str]]) -> str:
    for letter, patterns in groups.items():
        for pattern in patterns:
            if fnmatch.fnmatchcase(column, pattern):
                return letter
    return "I"


def _to_number(series: pd.Series) -> pd.Series:
    """'13.56%' -> 13.56; already-numeric columns pass through."""
    if pd.api.types.is_numeric_dtype(series):
        return series.astype("float64")
    cleaned = series.astype("string").str.strip().str.rstrip("%")
    return pd.to_numeric(cleaned, errors="coerce").astype("float64")


def _months_between(later: pd.Series, earlier: pd.Series) -> pd.Series:
    return (later.dt.year - earlier.dt.year) * 12 + (later.dt.month - earlier.dt.month)


class LendingClubAdapter(Adapter):
    name = "lendingclub"
    version = "3"

    # ------------------------------------------------------------------ reading
    def _field_groups(self) -> dict[str, list[str]]:
        """Groups from config; the built-in leakage patterns (B / C / D) are always re-added."""
        groups = self.options.get("field_groups")
        if not groups:
            return {k: list(v) for k, v in DEFAULT_FIELD_GROUPS.items()}
        merged = {str(k)[0].upper(): list(v or []) for k, v in groups.items()}
        self._readded_patterns: list[str] = []
        for letter in ("B", "C", "D"):
            present = {p for patterns in merged.values() for p in patterns}
            for pattern in DEFAULT_FIELD_GROUPS[letter]:
                if pattern not in present:
                    merged.setdefault(letter, []).append(pattern)
                    self._readded_patterns.append(f"{letter}:{pattern}")
        return merged

    def _usecols(self, header: list[str]) -> list[str]:
        groups = self._field_groups()
        keep: list[str] = []
        for col in header:
            letter = _match_group(col, groups)
            if letter in ("A", "G", "H", "I"):
                keep.append(col)
            elif letter == "B" and col in STRATEGY_ONLY:
                keep.append(col)
            elif col == "id":
                keep.append(col)
        return keep

    def _cache_path(self, path: Path, usecols: list[str]) -> Path:
        stat = path.stat()
        key = "|".join(
            [
                path.name,
                str(stat.st_size),
                str(int(stat.st_mtime)),
                str(self.config.dataset.nrows),
                str(self.options.get("sample_frac")),
                str(self.options.get("sample_random_state", 42)),
                self.version,
                hashlib.sha1(",".join(usecols).encode()).hexdigest()[:10],
            ]
        )
        digest = hashlib.sha1(key.encode()).hexdigest()[:16]
        return Path(self.config.dataset.cache_dir) / f"lendingclub_{digest}.pkl"

    def load_raw(self) -> pd.DataFrame:
        path = Path(self.config.dataset.path or "data/raw/accepted_2007_to_2018Q4.csv.gz")
        if not path.exists():
            raise FileNotFoundError(f"Lending Club file not found: {path} (see data/README.md)")
        header = list(pd.read_csv(path, nrows=0).columns)
        usecols = self._usecols(header)
        cache_path = self._cache_path(path, usecols)
        if self.config.dataset.cache and cache_path.exists():
            with cache_path.open("rb") as fh:
                payload = pickle.load(fh)
            frame = payload["frame"]
            frame.attrs["all_columns"] = payload["all_columns"]
            frame.attrs["cache_hit"] = str(cache_path)
            self._cache_hit = str(cache_path)
            return frame
        self._cache_hit = None

        dtype = {c: "string" for c in STRING_COLUMNS if c in usecols}
        read_kwargs: dict[str, Any] = dict(usecols=usecols, dtype=dtype, low_memory=False)
        if self.config.dataset.nrows:
            read_kwargs["nrows"] = int(self.config.dataset.nrows)
        sample_frac = self.options.get("sample_frac")
        if sample_frac:
            rng = np.random.default_rng(int(self.options.get("sample_random_state", 42)))
            frac = float(sample_frac)
            read_kwargs["skiprows"] = lambda i: i > 0 and rng.random() > frac
        frame = pd.read_csv(path, **read_kwargs)
        frame.attrs["all_columns"] = header
        if self.config.dataset.cache:
            cache_path.parent.mkdir(parents=True, exist_ok=True)
            with cache_path.open("wb") as fh:
                pickle.dump({"frame": frame, "all_columns": header}, fh, protocol=pickle.HIGHEST_PROTOCOL)
        return frame

    # ------------------------------------------------------------------ parsing
    def _parse_keys(self, df: pd.DataFrame) -> pd.DataFrame:
        """Parse only what the sample rules need (issue_d, term); runs on the full file."""
        date_format = self.options.get("date_format", "%b-%Y")
        if "term" in df:
            df["term"] = pd.to_numeric(df["term"].astype("string").str.extract(r"(\d+)")[0], errors="coerce")
        if "issue_d" in df:
            df["issue_d"] = pd.to_datetime(df["issue_d"].astype("string"), format=date_format, errors="coerce")
        return df

    def _parse_rest(self, df: pd.DataFrame) -> pd.DataFrame:
        """Parse the remaining string columns; runs after the sample rules on ~30 % of the rows."""
        date_format = self.options.get("date_format", "%b-%Y")
        if "emp_length" in df:
            df["emp_length"] = df["emp_length"].map(EMP_LENGTH_MAP).astype("float64")
        for col in ("earliest_cr_line", "last_pymnt_d", "sec_app_earliest_cr_line"):
            if col in df:
                df[col] = pd.to_datetime(df[col].astype("string"), format=date_format, errors="coerce")
        for col in ("int_rate", "revol_util"):
            if col in df:
                df[col] = _to_number(df[col])
        return df

    # ------------------------------------------------------------------ helpers
    @staticmethod
    def _bad_rate(df: pd.DataFrame) -> float | None:
        status = df["loan_status"]
        terminal = status.isin(BAD_STATUSES + GOOD_STATUSES)
        if terminal.sum() == 0:
            return None
        return float(status[terminal].isin(BAD_STATUSES).mean())

    # ------------------------------------------------------------------ transform
    def transform(self, raw: pd.DataFrame, source: str = "<frame>") -> tuple[pd.DataFrame, AdapterMeta]:
        all_columns = list(raw.attrs.get("all_columns") or raw.columns)
        groups = self._field_groups()
        log = SampleLog()
        warnings: list[str] = []
        notes: dict[str, Any] = {}
        extra_tables: dict[str, pd.DataFrame] = {}

        n_raw = len(raw)
        df = raw
        notes["cache_hit"] = raw.attrs.get("cache_hit") or getattr(self, "_cache_hit", None)
        readded = getattr(self, "_readded_patterns", [])
        if readded:
            warnings.append("config 的 field_groups 缺少内置的泄漏字段模式，已自动补回：" + ", ".join(readded))
        # Rule 0 — summary rows at the end of the file ("Total amount funded in policy code ...").
        id_ok = df["id"].astype("string").str.fullmatch(r"\d+").fillna(False) if "id" in df else True
        df = df[df["loan_status"].notna() & id_ok]
        del raw  # transform owns the only reference (see Adapter.load); free the 2 M-row frame early
        log.add(
            "drop_summary_rows",
            "剔除文件末尾的汇总行（id 非数字或 loan_status 为空）",
            n_raw,
            len(df),
            self._bad_rate(df),
        )
        df = self._parse_keys(df)

        # Rule 1 — early loans accepted under a different credit policy.
        n_before = len(df)
        df = df[~df["loan_status"].astype("string").str.startswith(CREDIT_POLICY_PREFIX).fillna(False)]
        log.add(
            "credit_policy",
            f"剔除 loan_status 以 “{CREDIT_POLICY_PREFIX}” 开头的贷款（早期不同准入政策）",
            n_before,
            len(df),
            self._bad_rate(df),
        )

        # Rule 2 — maturity: issue month + term <= data cut-off month (max issue month in the data).
        n_before = len(df)
        issue_months = df["issue_d"].dt.year * 12 + df["issue_d"].dt.month
        cutoff_override = self.options.get("data_cutoff_month")
        if cutoff_override:
            cutoff_label = pd.Period(str(cutoff_override), freq="M")
        else:
            cutoff_label = df["issue_d"].max().to_period("M")
        cutoff_month = int(cutoff_label.year * 12 + cutoff_label.month)
        terms_allowed = self.options.get("terms_allowed")
        if terms_allowed:
            allowed = [float(t) for t in terms_allowed]
            df = df[df["term"].isin(allowed)]
            log.add(
                "term_filter",
                f"只保留 term ∈ {sorted(int(t) for t in allowed)} 的贷款（config terms_allowed）",
                n_before,
                len(df),
                self._bad_rate(df),
            )
            n_before = len(df)
            issue_months = df["issue_d"].dt.year * 12 + df["issue_d"].dt.month
        matured = (issue_months + df["term"]) <= cutoff_month
        df = df[matured.fillna(False)]
        notes["data_cutoff_month"] = str(cutoff_label)
        # Which issue months are complete for each term: the OOT window (last months) can only hold
        # the shortest term, so a mixed-term sample has a term mix that shifts over time.
        completeness = {}
        for term in sorted(df["term"].dropna().unique()):
            completeness[int(term)] = str(cutoff_label - int(term))
        notes["term_completeness"] = completeness
        if len(completeness) > 1:
            parts = "，".join(f"{t} 期贷款 issue_d <= {m}" for t, m in completeness.items())
            warnings.append(
                f"到期规则使不同期限的完整放款窗口不同（{parts}）：最后几个月只有短期限贷款，"
                "train 与 OOT 的 term 构成不同（DECISIONS.md D5；可用 terms_allowed 只建单一期限的卡）"
            )
        log.add(
            "maturity",
            f"到期筛选：issue_d + term 个月 <= 数据截止月 {cutoff_label}（保证 performance window 完整）",
            n_before,
            len(df),
            self._bad_rate(df),
        )

        # Rule 3 — terminal status mapping; everything else is indeterminate and dropped.
        n_before = len(df)
        status = df["loan_status"]
        indeterminate_counts = status[~status.isin(BAD_STATUSES + GOOD_STATUSES)].value_counts()
        df = df[status.isin(BAD_STATUSES + GOOD_STATUSES)].copy()
        df[TARGET] = df["loan_status"].isin(BAD_STATUSES).astype("int8")
        notes["indeterminate_statuses"] = {str(k): int(v) for k, v in indeterminate_counts.items()}
        log.add(
            "terminal_status",
            "终态映射：Charged Off / Default → 1；Fully Paid → 0；Current / Late / In Grace Period 为 indeterminate，剔除",
            n_before,
            len(df),
            float(df[TARGET].mean()) if len(df) else None,
        )

        # Bad rate by issue year BEFORE the min_issue_date filter (evidence for rule 4).
        by_year = (
            df.assign(issue_year=df["issue_d"].dt.year)
            .groupby("issue_year")
            .agg(n=(TARGET, "size"), bad_rate=(TARGET, "mean"), term_60_share=("term", lambda s: float((s == 60).mean())))
            .reset_index()
        )
        extra_tables["bad_rate_by_year_before_min_issue_date"] = by_year

        # Rule 4 — issue-date window.
        min_issue = self.config.sample.min_issue_date
        max_issue = self.config.sample.max_issue_date
        if min_issue:
            n_before = len(df)
            df = df[df["issue_d"] >= pd.Timestamp(min_issue)]
            log.add(
                "min_issue_date",
                f"只保留 issue_d >= {min_issue}（2007–2011 量小且产品、客群与后期不同）",
                n_before,
                len(df),
                float(df[TARGET].mean()) if len(df) else None,
            )
        if max_issue:
            n_before = len(df)
            df = df[df["issue_d"] <= pd.Timestamp(max_issue)]
            log.add("max_issue_date", f"只保留 issue_d <= {max_issue}", n_before, len(df),
                    float(df[TARGET].mean()) if len(df) else None)

        # Rule 5 — final sample.
        log.add("final_sample", "最终样本量与 bad rate", len(df), len(df), float(df[TARGET].mean()) if len(df) else None)
        if len(df) == 0:
            raise ValueError("Lending Club sample definition left no rows; check nrows / min_issue_date")
        df = self._parse_rest(df)
        final_bad_rate = float(df[TARGET].mean())
        if not 0.01 <= final_bad_rate <= 0.40:
            warnings.append(f"样本 bad rate = {final_bad_rate:.2%}，超出常见的 1–40% 区间，请检查标签定义")

        # ---------------------------------------------------------- net_cash consistency check
        if {"total_pymnt", "total_rec_prncp", "total_rec_int", "total_rec_late_fee", "recoveries"} <= set(df.columns):
            co = df[df[TARGET] == 1]
            components = co["total_rec_prncp"] + co["total_rec_int"] + co["total_rec_late_fee"]
            diff_with = (co["total_pymnt"] - (components + co["recoveries"])).abs()
            diff_without = (co["total_pymnt"] - components).abs()
            share_with = float((diff_with < 1.0).mean()) if len(co) else float("nan")
            share_without = float((diff_without < 1.0).mean()) if len(co) else float("nan")
            # Robust decision: the formula that matches >= 99 % of charged-off loans wins; a handful of
            # rows with rounding / adjustment differences must not flip it. Ties -> "included" (never
            # add recoveries twice).
            if len(co) == 0 or (share_with < 0.99 and share_without < 0.99):
                includes = True
                warnings.append("net_cash 一致性检验不确定（两种公式都不能解释 >= 99% 的 Charged Off 贷款），按 total_pymnt 已含 recoveries 处理")
            else:
                includes = share_with >= share_without
            notes["net_cash_check"] = {
                "n_charged_off_checked": int(len(co)),
                "share_within_1_if_recoveries_included": share_with,
                "share_within_1_if_recoveries_excluded": share_without,
                "max_abs_diff_if_recoveries_included": float(diff_with.max()) if len(co) else None,
                "max_abs_diff_if_recoveries_excluded": float(diff_without.max()) if len(co) else None,
                "total_pymnt_includes_recoveries": includes,
            }
        else:
            includes = True

        # ---------------------------------------------------------- reserved columns
        out = pd.DataFrame(index=df.index)
        out[TARGET] = df[TARGET].astype("int8")
        out[ISSUE_DATE] = df["issue_d"]
        if "last_pymnt_d" in df:
            out[EVENT_DATE] = df["last_pymnt_d"]
            notes["event_date_note"] = (
                "Lending Club 没有逐月表现数据，vintage 的账龄用 last_pymnt_d − issue_d（月）近似违约发生月："
                "最后一次还款之后约 120 天以上才被 Charged Off，所以曲线比真实违约时点早约 4–5 个月；"
                "Fully Paid 贷款的 last_pymnt_d 是结清月，不参与分子。"
            )
        if "funded_amnt" in df:
            out[LOAN_AMOUNT] = df["funded_amnt"].astype("float64")
        subtract_fee = bool(self.options.get("net_cash_subtract_collection_fee", True))
        if "total_pymnt" in df and "funded_amnt" in df:
            net = df["total_pymnt"].astype("float64") - df["funded_amnt"].astype("float64")
            if not includes and "recoveries" in df:
                net = net + df["recoveries"].fillna(0.0)
            if subtract_fee and "collection_recovery_fee" in df:
                net = net - df["collection_recovery_fee"].fillna(0.0)
            out[NET_CASH] = net
            notes["net_cash_definition"] = (
                "net_cash = total_pymnt"
                + ("" if includes else " + recoveries")
                + (" - collection_recovery_fee" if subtract_fee else "")
                + " - funded_amnt（实际回款减放款本金；仅策略层使用）"
            )

        # ---------------------------------------------------------- field audit + features
        audit_rows: list[dict[str, Any]] = []
        feature_cols: list[str] = []
        categorical_cols: list[str] = []
        platform_cols: list[str] = []
        rare_share = float(self.options.get("rare_category_min_share", 0.01))
        rare_cols = list(self.options.get("rare_category_cols", ["purpose", "home_ownership", "addr_state"]))
        derived_from = {
            "issue_d": (RESERVED, "issue_date：时间切分 / OOT / vintage，不作为特征"),
            "earliest_cr_line": (DERIVED, "→ credit_hist_months = months(issue_d − earliest_cr_line)"),
            "fico_range_low": (DERIVED, "→ fico_mid = (fico_range_low + fico_range_high) / 2"),
            "fico_range_high": (DERIVED, "→ fico_mid"),
            "emp_length": (DERIVED, "→ emp_length_years（'10+ years' → 10，'< 1 year' → 0，n/a → NaN）"),
            "sec_app_earliest_cr_line": (DERIVED, "→ sec_app_credit_hist_months"),
        }

        for col in all_columns:
            letter = _match_group(col, groups)
            if letter == "A":
                audit_rows.append(dict(column=col, group=letter, decision=RESERVED, reason="→ target（终态映射）"))
            elif letter == "B":
                if col in STRATEGY_ONLY:
                    audit_rows.append(dict(column=col, group=letter, decision=RESERVED, reason=STRATEGY_ONLY[col]))
                else:
                    audit_rows.append(dict(column=col, group=letter, decision=DROP, reason="贷后回款 / 余额，泄漏"))
            elif letter == "C":
                audit_rows.append(dict(column=col, group=letter, decision=DROP, reason="贷后信用更新，泄漏"))
            elif letter == "D":
                audit_rows.append(dict(column=col, group=letter, decision=DROP, reason="困难 / 和解 / 还款计划，贷后信息"))
            elif letter == "E":
                audit_rows.append(dict(column=col, group=letter, decision=DROP, reason="标识 / 自由文本 / 无信息"))
            elif letter == "F":
                audit_rows.append(dict(column=col, group=letter, decision=DROP, reason="投资人侧"))
            elif letter == "G":
                platform_cols.append(col)
                audit_rows.append(dict(column=col, group=letter, decision=PLATFORM, reason="平台评级，按 use_platform_rating 开关"))
            elif col in derived_from:
                decision, reason = derived_from[col]
                audit_rows.append(dict(column=col, group=letter, decision=decision, reason=reason))
            else:  # H or I: candidate feature
                reason = "联合申请字段，缺失 = 非联合申请" if letter == "H" else "申请时可得"
                if col in df.columns:
                    feature_cols.append(col)
                    audit_rows.append(dict(column=col, group=letter, decision=KEEP, reason=reason))
                else:
                    audit_rows.append(dict(column=col, group=letter, decision=DROP, reason="未读取"))

        # Copy candidate features with cleaned dtypes.
        for col in feature_cols:
            if col in CATEGORICAL_FEATURES:
                out[col] = df[col].astype("string")
                categorical_cols.append(col)
            else:
                out[col] = _to_number(df[col])

        # Platform-rating columns stay in the frame (switched on/off by config).
        for col in platform_cols:
            if col not in df.columns:
                continue
            if col in PLATFORM_CATEGORICAL:
                out[col] = df[col].astype("string")
                categorical_cols.append(col)
            else:
                out[col] = _to_number(df[col])

        # Derived variables (PLAN.md §4.4).
        def add_derived(name: str, values: pd.Series, reason: str) -> None:
            out[name] = values.astype("float64")
            feature_cols.append(name)
            audit_rows.append(dict(column=name, group="X", decision=KEEP, reason=reason))

        if {"fico_range_low", "fico_range_high"} <= set(df.columns):
            add_derived("fico_mid", (df["fico_range_low"] + df["fico_range_high"]) / 2.0, "(fico_range_low + fico_range_high) / 2")
        if "earliest_cr_line" in df:
            add_derived("credit_hist_months", _months_between(df["issue_d"], df["earliest_cr_line"]), "months(issue_d − earliest_cr_line)")
        if "emp_length" in df:
            add_derived("emp_length_years", df["emp_length"], "emp_length 解析为年数")
        if "annual_inc" in df:
            add_derived("log_annual_inc", np.log1p(df["annual_inc"].clip(lower=0)), "log1p(annual_inc)")
        if {"loan_amnt", "annual_inc"} <= set(df.columns):
            inc = df["annual_inc"].where(df["annual_inc"] > 0)
            add_derived("loan_to_inc", df["loan_amnt"] / inc, "loan_amnt / annual_inc（annual_inc = 0 → NaN）")
        if "sec_app_earliest_cr_line" in df:
            add_derived(
                "sec_app_credit_hist_months",
                _months_between(df["issue_d"], df["sec_app_earliest_cr_line"]),
                "months(issue_d − sec_app_earliest_cr_line)",
            )

        # Rare categories -> one pooled level (frequency only, no labels involved; evaluated on the
        # whole sample before the split, which is label-free but transductive — see DECISIONS.md).
        rare_label = str(self.options.get("rare_category_label", "OTHER_RARE"))
        merged_categories: dict[str, list[str]] = {}
        for col in rare_cols:
            if col in out.columns and col in categorical_cols:
                share = out[col].value_counts(normalize=True, dropna=True)
                rare = share[share < rare_share].index.tolist()
                if rare:
                    out[col] = out[col].where(~out[col].isin(rare), rare_label)
                    merged_categories[col] = [str(r) for r in rare]
        notes["rare_category_label"] = rare_label
        notes["rare_category_min_share"] = rare_share
        notes["rare_categories_merged"] = merged_categories
        notes["sample_definition_note"] = (
            "bad rate 按剩余行中已有终态（Charged Off / Default / Fully Paid）的贷款计算；"
            "终态映射之前的行里还包含 Current 等未终态贷款，不计入分母。"
        )
        notes["missing_by_year_note"] = (
            "征信类字段（num_* / mo_sin_* / il / rv 等）在早期年份缺失率极高；select 步骤按 max_missing 阈值处理。"
        )
        notes["group_labels"] = {
            "A": "A 目标来源",
            "B": "B 贷后回款 / 余额（泄漏，剔除）",
            "C": "C 贷后信用更新（泄漏，剔除）",
            "D": "D 困难 / 和解 / 还款计划（泄漏，剔除）",
            "E": "E 无信息 / 标识 / 自由文本（剔除）",
            "F": "F 投资人侧（剔除）",
            "G": "G 平台评级（use_platform_rating 开关）",
            "H": "H 联合申请字段",
            "I": "I 申请时可得（候选特征）",
            "X": "X adapter 派生变量",
        }

        for col in categorical_cols:
            if col == "grade":
                out[col] = pd.Categorical(out[col], categories=GRADE_ORDER, ordered=True)
            else:
                out[col] = out[col].astype("category")

        out = out.sort_values(ISSUE_DATE, kind="stable").reset_index(drop=True)
        field_audit = pd.DataFrame(audit_rows)
        field_audit["group_name"] = field_audit["group"].map(GROUP_NAMES)
        notes["feature_count"] = len(feature_cols)
        notes["rows_sorted_by"] = ISSUE_DATE

        meta = AdapterMeta(
            name=self.name,
            source=source,
            n_raw_rows=int(n_raw),
            n_raw_cols=len(all_columns),
            feature_cols=feature_cols,
            categorical_cols=[c for c in categorical_cols if c in feature_cols or c in platform_cols],
            sample_definition_log=log.as_list(),
            field_audit=field_audit,
            platform_rating_cols=[c for c in platform_cols if c in out.columns],
            platform_grade_col="grade" if "grade" in out.columns else None,
            warnings=warnings,
            notes=notes,
            extra_tables=extra_tables,
        )
        return out, meta


def parse_term(value: str) -> float:
    """' 36 months' -> 36.0 (kept as a tiny public helper for tests)."""
    match = re.search(r"(\d+)", str(value))
    return float(match.group(1)) if match else float("nan")
