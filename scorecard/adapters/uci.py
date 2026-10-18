"""UCI "Default of Credit Card Clients" adapter (UCI Machine Learning Repository id = 350).

30,000 Taiwanese credit-card clients, 23 raw attributes observed April–September 2005 and the label
"default payment next month" (October 2005). The dataset has no origination date, no cash flows and
no platform rating, so this adapter exercises the engine's fall-backs: stratified hold-out instead
of a time-based OOT, "no net_cash" in the strategy section, a random swap-set baseline.

Dataset knowledge lives here only (CLAUDE.md hard rule 2):

* the download (`ucimlrepo`, cached as a CSV under `data/raw/`) and the X1..X23 -> real-name mapping;
* cleaning: undocumented EDUCATION codes 0 / 5 / 6 -> 4 (others), MARRIAGE 0 -> 3 (others);
* SEX and MARRIAGE are protected attributes and are excluded from the candidate features;
* PAY_0..PAY_6 stay ordinal codes (<= 0 means "not late"); BILL_AMT may be negative (credit balance);
* eleven engineered behaviour features (utilisation, repayment coverage, delinquency counts), each a
  row-wise rule with no parameter learned from the data, so building them before the split cannot leak.

Options (`dataset.options`): `uci_id` (350), `exclude_protected` (default [SEX, MARRIAGE]),
`engineer_features` (default true).
"""

from __future__ import annotations

import logging
import time
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from scorecard.adapters.base import (
    DROP,
    KEEP,
    RESERVED,
    TARGET,
    Adapter,
    AdapterMeta,
    SampleLog,
)

log = logging.getLogger(__name__)

UCI_ID = 350
DEFAULT_PATH = Path("data/raw/uci_default_of_credit_card_clients.csv")
TARGET_NAMES = ("default payment next month", "default_payment_next_month", "Y", "default")
PAY_STATUS = [f"PAY_{i}" for i in (0, 2, 3, 4, 5, 6)]
BILL_AMT = [f"BILL_AMT{i}" for i in range(1, 7)]
PAY_AMT = [f"PAY_AMT{i}" for i in range(1, 7)]
RAW_FEATURES = ["LIMIT_BAL", "SEX", "EDUCATION", "MARRIAGE", "AGE"] + PAY_STATUS + BILL_AMT + PAY_AMT
PROTECTED_DEFAULT = ["SEX", "MARRIAGE"]

RAW_MEANING = {
    "LIMIT_BAL": "授信额度（含附属卡，NT$）",
    "SEX": "性别（1 男 2 女）——受保护属性，不入模",
    "EDUCATION": "教育程度（1 研究生 2 大学 3 高中 4 其他；0/5/6 并入 4）",
    "MARRIAGE": "婚姻（1 已婚 2 单身 3 其他；0 并入 3）——受保护属性，不入模",
    "AGE": "年龄",
    **{c: f"还款状态码（{m}）：-2/-1/0 未逾期，1..8 逾期月数" for c, m in zip(PAY_STATUS, ["9 月", "8 月", "7 月", "6 月", "5 月", "4 月"])},
    **{c: f"账单金额（{m}，NT$；负数 = 贷方余额）" for c, m in zip(BILL_AMT, ["9 月", "8 月", "7 月", "6 月", "5 月", "4 月"])},
    **{c: f"还款金额（{m}，NT$）" for c, m in zip(PAY_AMT, ["9 月", "8 月", "7 月", "6 月", "5 月", "4 月"])},
}
ENGINEERED = {
    "UTIL_1": "max(BILL_AMT1, 0) / LIMIT_BAL：最近一个月的额度使用率",
    "UTIL_MEAN_6M": "6 个月 max(BILL_AMTk, 0) / LIMIT_BAL 的均值：持续的额度使用水平",
    "UTIL_MAX_6M": "6 个月额度使用率的最大值（> 1 = 超限）",
    "BILL_TREND_3M": "近 3 个月使用率均值 − 前 3 个月使用率均值：余额在涨还是在降",
    "PAY_RATIO_1": "PAY_AMT1 / BILL_AMT2（上期账单的还款覆盖率，封顶 1；上期账单 <= 0 时缺失）",
    "PAY_RATIO_MEAN_5M": "5 个月还款覆盖率的均值：全额还款型 vs 最低还款型",
    "PAY_RATIO_MIN_5M": "5 个月还款覆盖率的最小值：最差的一个月",
    "DELQ_MONTHS_6M": "6 个月中逾期（PAY >= 1）的月数",
    "MAX_DELQ_6M": "6 个月中最严重的逾期月数 max(PAY, 0)",
    "DELQ_TREND_3M": "近 3 个月逾期月数 − 前 3 个月逾期月数：在恶化还是在恢复",
    "NO_BILL_MONTHS_6M": "6 个月中账单 <= 0 的月数：账户不活跃",
}


def fetch_uci_frame(uci_id: int = UCI_ID, attempts: int = 4) -> pd.DataFrame:
    """Download via ucimlrepo and rename the generic X1..X23 / Y columns to the paper's names."""
    from ucimlrepo import fetch_ucirepo

    last: Exception | None = None
    for attempt in range(1, attempts + 1):
        try:
            dataset = fetch_ucirepo(id=uci_id)
            break
        except Exception as exc:  # noqa: BLE001 - the UCI API drops connections now and then
            last = exc
            log.warning("ucimlrepo attempt %d failed: %s", attempt, exc)
            time.sleep(5 * attempt)
    else:
        raise ConnectionError(f"could not download UCI dataset {uci_id}: {last}")
    variables = dataset.variables
    rename: dict[str, str] = {}
    for name, description in zip(variables["name"], variables["description"]):
        if str(name).startswith("X") and isinstance(description, str) and description:
            rename[str(name)] = description.strip()
    frame = dataset.data.original.rename(columns=rename)
    return frame


class UCIAdapter(Adapter):
    name = "uci"
    version = "1"

    def load_raw(self) -> pd.DataFrame:
        path = Path(self.config.dataset.path or DEFAULT_PATH)
        if not path.exists():
            log.info("UCI dataset not found at %s; downloading with ucimlrepo (id=%s)", path, self.options.get("uci_id", UCI_ID))
            frame = fetch_uci_frame(int(self.options.get("uci_id", UCI_ID)))
            path.parent.mkdir(parents=True, exist_ok=True)
            frame.to_csv(path, index=False)
        raw = pd.read_csv(path)
        if self.config.dataset.nrows:
            raw = raw.head(int(self.config.dataset.nrows))
        raw.attrs["all_columns"] = list(raw.columns)
        return raw

    @staticmethod
    def _target_column(raw: pd.DataFrame) -> str:
        for name in TARGET_NAMES:
            if name in raw.columns:
                return name
        raise ValueError(f"UCI frame has no label column among {TARGET_NAMES}: {list(raw.columns)[:10]}")

    def transform(self, raw: pd.DataFrame, source: str = "uci") -> tuple[pd.DataFrame, AdapterMeta]:
        opts = self.options
        protected = [c for c in (opts.get("exclude_protected", PROTECTED_DEFAULT) or []) if c in raw.columns]
        engineer = bool(opts.get("engineer_features", True))
        all_columns = list(raw.attrs.get("all_columns", raw.columns))
        n0 = len(raw)
        target_col = self._target_column(raw)
        log_ = SampleLog()
        df = raw[raw[target_col].notna()].copy()
        df[TARGET] = pd.to_numeric(df[target_col], errors="coerce").astype("int8")
        log_.add("drop_missing_target", "剔除 label 缺失的行", n0, len(df), float(df[TARGET].mean()))
        missing_feature = [c for c in RAW_FEATURES if c not in df.columns]
        if missing_feature:
            raise ValueError(f"UCI frame is missing columns {missing_feature}")

        # ---------------------------------------------------------- cleaning (documented codes only)
        notes: dict[str, Any] = {"uci_id": int(opts.get("uci_id", UCI_ID))}
        edu_undefined = ~df["EDUCATION"].isin([1, 2, 3, 4])
        mar_undefined = ~df["MARRIAGE"].isin([1, 2, 3])
        df.loc[edu_undefined, "EDUCATION"] = 4
        df.loc[mar_undefined, "MARRIAGE"] = 3
        notes["education_recoded_to_others"] = int(edu_undefined.sum())
        notes["marriage_recoded_to_others"] = int(mar_undefined.sum())
        notes["n_negative_bill_clients"] = int((df[BILL_AMT] < 0).any(axis=1).sum())
        log_.add("final_sample", "最终样本量与 bad rate（UCI 数据无日期、无回款，样本不再筛选）", len(df), len(df), float(df[TARGET].mean()))

        # ---------------------------------------------------------- engineered behaviour features
        out = pd.DataFrame(index=df.index)
        out[TARGET] = df[TARGET]
        for c in RAW_FEATURES:
            out[c] = pd.to_numeric(df[c], errors="coerce")
        out["EDUCATION"] = pd.Categorical(out["EDUCATION"].astype(int).astype(str))
        out["SEX"] = pd.Categorical(out["SEX"].astype(int).astype(str))
        out["MARRIAGE"] = pd.Categorical(out["MARRIAGE"].astype(int).astype(str))
        engineered: list[str] = []
        if engineer:
            limit = out["LIMIT_BAL"].replace(0, np.nan)
            util = out[BILL_AMT].clip(lower=0).div(limit, axis=0)
            out["UTIL_1"] = util.iloc[:, 0]
            out["UTIL_MEAN_6M"] = util.mean(axis=1)
            out["UTIL_MAX_6M"] = util.max(axis=1)
            out["BILL_TREND_3M"] = util.iloc[:, :3].mean(axis=1) - util.iloc[:, 3:].mean(axis=1)
            ratios = pd.concat(
                [(out[f"PAY_AMT{k}"] / out[f"BILL_AMT{k + 1}"]).where(out[f"BILL_AMT{k + 1}"] > 0).clip(upper=1.0) for k in range(1, 6)],
                axis=1,
            )
            out["PAY_RATIO_1"] = ratios.iloc[:, 0]
            out["PAY_RATIO_MEAN_5M"] = ratios.mean(axis=1)
            out["PAY_RATIO_MIN_5M"] = ratios.min(axis=1)
            late = out[PAY_STATUS] >= 1
            out["DELQ_MONTHS_6M"] = late.sum(axis=1).astype(float)
            out["MAX_DELQ_6M"] = out[PAY_STATUS].clip(lower=0).max(axis=1).astype(float)
            out["DELQ_TREND_3M"] = (late.iloc[:, :3].sum(axis=1) - late.iloc[:, 3:].sum(axis=1)).astype(float)
            out["NO_BILL_MONTHS_6M"] = (out[BILL_AMT] <= 0).sum(axis=1).astype(float)
            engineered = list(ENGINEERED)

        # ---------------------------------------------------------- field audit
        rows: list[dict[str, Any]] = []
        feature_cols: list[str] = []
        for col in all_columns:
            if col == target_col:
                rows.append(dict(column=col, group="A", decision=RESERVED, reason="目标：下月是否违约（1 = 违约）"))
            elif col == "ID":
                rows.append(dict(column=col, group="E", decision=DROP, reason="客户编号，无信息"))
            elif col in protected:
                rows.append(dict(column=col, group="F", decision=DROP, reason="受保护属性（公平性），两套模型都不入模；保留在数据表里供公平性检查"))
            elif col in RAW_FEATURES:
                rows.append(dict(column=col, group="I", decision=KEEP, reason=RAW_MEANING.get(col, "原始申请 / 行为字段")))
                feature_cols.append(col)
            else:
                rows.append(dict(column=col, group="E", decision=DROP, reason="未知列，未使用"))
        for col in engineered:
            rows.append(dict(column=col, group="X", decision=KEEP, reason=ENGINEERED[col]))
            feature_cols.append(col)
        audit = pd.DataFrame(rows)
        audit["group_name"] = audit["group"].map({"A": "target", "E": "identifier", "F": "protected attribute", "I": "candidate", "X": "derived"})
        keep_cols = [TARGET] + feature_cols + [c for c in protected if c in out.columns]
        out = out[keep_cols].reset_index(drop=True)
        categorical = [c for c in ("EDUCATION", "SEX", "MARRIAGE") if c in feature_cols]
        notes["group_labels"] = {"F": "F 受保护属性（公平性，剔除）", "E": "E 标识 / 未用（剔除）", "X": "X adapter 派生变量（行为特征）"}
        notes["sample_definition_note"] = (
            "UCI 数据是 2005 年 4–9 月的 30,000 名信用卡客户快照，标签是 10 月是否违约；没有放款日期（OOT 用分层 hold-out 代替）、没有回款（跳过利润曲线）、没有平台评级（swap set 用随机基准）。"
        )
        notes["iv_review"] = (
            "PAY_0 / PAY_2 及由还款状态派生的 DELQ_MONTHS_6M、MAX_DELQ_6M 的 IV 超过 0.5：它们是 2005 年 4–9 月的还款状态，"
            "标签是 10 月是否违约，时间上在前，不是贷后信息；IV 高是因为已经逾期的人更可能继续违约（已人工核对，保留）。"
        )
        notes["cleaning_note"] = (
            f"EDUCATION 文档外取值 0/5/6 并入 4（{notes['education_recoded_to_others']} 行），MARRIAGE 0 并入 3（{notes['marriage_recoded_to_others']} 行）；"
            f"BILL_AMT 为负（贷方余额）的客户 {notes['n_negative_bill_clients']:,} 名，原值保留，比率特征中按 0 处理。"
        )
        meta = AdapterMeta(
            name=self.name,
            source=source,
            n_raw_rows=n0,
            n_raw_cols=len(all_columns),
            feature_cols=feature_cols,
            categorical_cols=categorical,
            sample_definition_log=log_.as_list(),
            field_audit=audit,
            platform_rating_cols=[],
            platform_grade_col=None,
            notes=notes,
            extra_tables={"uci_feature_dictionary": pd.DataFrame([{"feature": k, "definition": v} for k, v in {**RAW_MEANING, **ENGINEERED}.items() if k in feature_cols])},
        )
        return out, meta
