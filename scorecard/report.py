"""Report rendering: RunResult -> fixed 7-section structure -> report.html + report.md.

The report is built as a list of sections, each a list of typed blocks (paragraph, key-value,
table, figure, list, warning, placeholder). Both Jinja templates just walk that structure, so the
HTML and Markdown versions can never drift apart. A section without an implementation renders a
visible placeholder; it never silently disappears (CLAUDE.md hard rule 5).
"""

from __future__ import annotations

import base64
from pathlib import Path
from typing import TYPE_CHECKING, Any

import numpy as np
import pandas as pd
import yaml
from jinja2 import Environment, PackageLoader

from scorecard import checks as checks_mod
from scorecard import figures as fig
from scorecard import monitor as monitor_mod
from scorecard import strategy as strategy_mod
from scorecard.adapters.base import TARGET
from scorecard.split import OOT, TEST, TRAIN

if TYPE_CHECKING:
    from scorecard.pipeline import RunResult, VariantResult

PLACEHOLDER = "（本阶段未实现）"

# Generic meaning of the field-audit group letters; an adapter can override the wording through
# `meta.notes["group_labels"]` (the Lending Club adapter does, with PLAN.md §4.3 names).
GROUP_LABELS = {
    "A": "A 目标 / 保留列",
    "B": "B 贷后 / 策略层字段（非特征）",
    "C": "C 贷后信用更新（剔除）",
    "D": "D 贷后处置信息（剔除）",
    "E": "E 无信息 / 标识（剔除）",
    "F": "F 其他剔除",
    "G": "G 平台评级（use_platform_rating 开关）",
    "H": "H 联合申请字段",
    "I": "I 候选特征",
    "X": "X adapter 派生变量",
}
LABEL_COLS = {"issue_year", "period", "year", "quarter"}  # never thousands-separated
DECISION_LABELS = {
    "keep": "入模候选",
    "drop": "剔除",
    "reserved": "保留列（非特征）",
    "platform_rating": "平台评级（开关）",
    "derived": "派生后剔除原列",
}
SEGMENT_LABELS = {TRAIN: "train", TEST: "test", OOT: "OOT"}

PCT_COLS = {"bad_rate", "share", "missing_rate", "approval_rate", "top_share", "overall", "cum_bad_share", "cum_good_share",
            "term_60_share", "max_bin_share", "missing_share", "largest_regular_bin_share", "cum_approval_rate", "cum_bad_rate",
            "bad_rate_approved", "bad_rate_rejected", "expected_pct", "actual_pct", "target_approval_rate", "marginal_bad_rate",
            "model_bad_rate", "baseline_bad_rate", "swap_in_bad_rate", "swap_out_bad_rate", "cum_default_rate", "train_share", "shift_share", "early_share", "late_share"}
F4_COLS = {"iv", "woe", "auc", "ks", "gini", "coefficient", "vif", "psi", "csi", "csi_test", "csi_oot", "time_csi", "corr", "psi_contribution", "cv_auc_mean",
           "cv_auc_std", "cv_ks_mean", "cv_ks_std", "factor", "offset"}
INT_COLS = {"n", "count", "bad", "good", "removed", "remaining", "n_raw_rows", "n_rows", "n_unique", "n_bins", "n_bins_initial",
            "points_int", "step", "bin_id", "band", "n_approved", "n_rejected", "cutoff_score", "score_min", "score_max", "cum_n",
            "marginal_n", "swap_in_n", "swap_out_n", "n_expected", "n_actual", "mob"}


# --------------------------------------------------------------------------- formatting
def fmt_value(col: str, value: Any) -> str:
    if value is None or (isinstance(value, float) and np.isnan(value)):
        return ""
    if isinstance(value, (bool, np.bool_)):
        return "是" if value else "否"
    if col in LABEL_COLS:
        return str(int(value)) if isinstance(value, (int, np.integer, float, np.floating)) else str(value)
    if col in PCT_COLS and isinstance(value, (float, np.floating)):
        return f"{value:.2%}"
    if col in F4_COLS and isinstance(value, (float, np.floating, int, np.integer)):
        return f"{float(value):.4f}"
    if col in INT_COLS and isinstance(value, (int, np.integer, float, np.floating)):
        return f"{int(round(float(value))):,}"
    if isinstance(value, (int, np.integer)):
        return f"{int(value):,}"
    if isinstance(value, (float, np.floating)):
        v = float(value)
        if v == int(v) and abs(v) < 1e9:
            return f"{int(v):,}"
        return f"{v:,.4g}" if abs(v) < 1000 else f"{v:,.0f}"
    return str(value)


def table_block(df: pd.DataFrame, title: str | None = None, rename: dict[str, str] | None = None,
                collapsed: bool = False, note: str | None = None, max_rows: int | None = None,
                formats: dict[str, str] | None = None) -> dict[str, Any]:
    rename = rename or {}
    formats = formats or {}
    df = df.copy()
    truncated = False
    if max_rows is not None and len(df) > max_rows:
        df = df.head(max_rows)
        truncated = True
    columns = [rename.get(c, c) for c in df.columns]
    rows = []
    for record in df.itertuples(index=False):
        row = []
        for col, value in zip(df.columns, record):
            if col in formats and value is not None and not (isinstance(value, float) and np.isnan(value)):
                row.append(formats[col].format(value))
            else:
                row.append(fmt_value(col, value))
        rows.append(row)
    return {
        "type": "table",
        "title": title,
        "columns": columns,
        "rows": rows,
        "n_rows": len(rows),
        "collapsed": collapsed,
        "note": note,
        "truncated": truncated,
    }


def p(text: str) -> dict[str, Any]:
    return {"type": "p", "text": text}


def kv(items: list[tuple[str, Any]], title: str | None = None) -> dict[str, Any]:
    return {"type": "kv", "title": title, "items": [(k, "" if v is None else str(v)) for k, v in items]}


def bullet(items: list[str], title: str | None = None) -> dict[str, Any]:
    return {"type": "list", "title": title, "items": items}


def warning_block(items: list[str], title: str = "提示") -> dict[str, Any]:
    return {"type": "warning", "title": title, "items": items}


def figure_block(path: Path, out_dir: Path, caption: str, embed: bool) -> dict[str, Any]:
    rel = path.relative_to(out_dir).as_posix()
    data_uri = None
    if embed:
        data_uri = "data:image/png;base64," + base64.b64encode(path.read_bytes()).decode("ascii")
    return {"type": "figure", "path": rel, "data_uri": data_uri, "caption": caption}


def placeholder_block(planned: list[str]) -> dict[str, Any]:
    return {"type": "placeholder", "text": PLACEHOLDER, "planned": planned}


def section(number: int, title: str, intro: str, blocks: list[dict[str, Any]], implemented: bool = True) -> dict[str, Any]:
    return {"number": number, "title": title, "intro": intro, "blocks": blocks, "implemented": implemented}


# --------------------------------------------------------------------------- sections
def build_section_1(result: RunResult, out_dir: Path, embed: bool) -> dict[str, Any]:
    meta, prof, cfg = result.meta, result.profile, result.config
    ov = prof["overview"]
    blocks: list[dict[str, Any]] = []
    blocks.append(
        kv(
            [
                ("数据来源", ov["source"]),
                ("adapter", meta.name),
                ("原始行 × 列", f"{ov['n_raw_rows']:,} × {ov['n_raw_cols']:,}"),
                ("样本定义后行数", f"{ov['n_rows']:,}"),
                ("候选特征数", f"{ov['n_features']}（其中类别型 {ov['n_categorical']}）"),
                ("bad rate", f"{ov['bad_rate']:.2%}（bad = {ov['n_bad']:,}）"),
                ("issue_date 范围", f"{ov.get('issue_date_min', '—')} ~ {ov.get('issue_date_max', '—')}"),
            ],
            title="1.1 数据来源与规模",
        )
    )
    sample_log = pd.DataFrame(meta.sample_definition_log)
    blocks.append(
        table_block(
            sample_log,
            title="1.2 样本定义影响表",
            rename={"step": "步骤", "rule": "规则", "description": "说明", "removed": "剔除行数", "remaining": "剩余行数", "bad_rate": "剩余 bad rate"},
            note=meta.notes.get("sample_definition_note"),
        )
    )
    pre = meta.extra_tables.get("bad_rate_by_year_before_min_issue_date")
    if pre is not None and len(pre):
        blocks.append(
            table_block(
                pre,
                title="1.3 min_issue_date 之前：bad rate 按 issue 年（到期 + 终态样本）",
                rename={"issue_year": "issue 年", "n": "贷款数", "bad_rate": "bad rate", "term_60_share": "60 期占比"},
                note=f"min_issue_date 规则只保留 issue_date >= {cfg.sample.min_issue_date} 的依据：早期年份样本少、产品结构（60 期占比）和 bad rate 与后期不同。",
            )
        )
        path = fig.plot_bad_rate_by_period(pre.rename(columns={"issue_year": "period"}), out_dir / "figures" / "01_bad_rate_by_year_prefilter.png",
                                           "Bad rate by issue year, before the min_issue_date filter", "period")
        blocks.append(figure_block(path, out_dir, "图 1.1 min_issue_date 过滤前的 bad rate 按 issue 年", embed))

    audit = meta.field_audit.copy()
    group_labels = {**GROUP_LABELS, **(meta.notes.get("group_labels") or {})}
    audit_summary = (
        audit.groupby("group")
        .agg(n_columns=("column", "size"), decisions=("decision", lambda s: ", ".join(f"{DECISION_LABELS.get(k, k)} {v}" for k, v in s.value_counts().items())))
        .reset_index()
    )
    audit_summary["group"] = audit_summary["group"].map(lambda g: group_labels.get(g, g))
    blocks.append(table_block(audit_summary, title="1.4 字段审计：按分组汇总", rename={"group": "分组", "n_columns": "字段数", "decisions": "处理"}))
    audit_full = audit[["column", "group", "decision", "reason"]].copy()
    audit_full["group"] = audit_full["group"].map(lambda g: group_labels.get(g, g))
    audit_full["decision"] = audit_full["decision"].map(lambda d: DECISION_LABELS.get(d, d))
    blocks.append(table_block(audit_full, title="字段审计清单（全部原始字段 + 派生变量）", rename={"column": "字段", "group": "分组", "decision": "处理", "reason": "原因"}, collapsed=True))

    blocks.append(
        table_block(
            prof["missing_top"],
            title=f"1.5 缺失率 Top {cfg.report.top_missing}（候选特征，全样本）",
            rename={"feature": "特征", "kind": "类型", "missing_rate": "缺失率", "n_unique": "取值数"},
        )
    )
    if ov["has_issue_date"]:
        q = prof["bad_rate_by_quarter"]
        path = fig.plot_bad_rate_by_period(q, out_dir / "figures" / "02_bad_rate_by_quarter.png", "Bad rate by issue quarter (final sample)")
        blocks.append(figure_block(path, out_dir, "图 1.2 bad rate 按 issue 季度（最终样本）", embed))
        blocks.append(table_block(q, title="1.6 bad rate 按 issue 季度", rename={"period": "季度", "n": "贷款数", "bad": "bad 数", "bad_rate": "bad rate"}, collapsed=True))
        mby = prof["missing_by_year"]
        if len(mby):
            blocks.append(
                table_block(
                    mby,
                    title="1.7 缺失率按 issue 年（总缺失率 > 5% 的特征）",
                    rename={"feature": "特征", "overall": "总缺失率"},
                    formats={c: "{:.1%}" for c in mby.columns if c not in ("feature",)},
                    collapsed=len(mby) > 15,
                    note=meta.notes.get("missing_by_year_note"),
                )
            )
    split = result.split_info
    method = "按 issue_date 切 OOT（最后 {} 个月：{} ~ {}），其余按 target 分层随机切 train / test".format(
        split.get("oot_months"), split.get("oot_start"), split.get("oot_end")
    ) if split.get("method") == "time" else "无 issue_date：OOT 用分层 hold-out 代替，其余分层随机切 train / test"
    blocks.append(
        table_block(
            split["summary"],
            title="1.8 样本切分",
            rename={"segment": "样本", "n": "行数", "share": "占比", "bad_rate": "bad rate", "date_min": "issue 起", "date_max": "issue 止"},
            note=f"{method}；train_ratio = {split['train_ratio']}，random_state = {split['random_state']}。分箱、WOE、特征选择与模型只在 train 上拟合。",
        )
    )
    notes = meta.notes
    note_items = []
    if "net_cash_check" in notes:
        chk = notes["net_cash_check"]
        note_items.append(
            "net_cash 一致性检验（Charged Off 样本 {:,} 笔）：total_pymnt 与 total_rec_prncp + total_rec_int + total_rec_late_fee + recoveries 相差 < 1 的占 {}（最大绝对差 {}）；不含 recoveries 时占 {}（最大绝对差 {}）→ total_pymnt {}包含 recoveries。".format(
                chk["n_charged_off_checked"],
                fmt_value("share", chk.get("share_within_1_if_recoveries_included")),
                fmt_value("x", chk["max_abs_diff_if_recoveries_included"]),
                fmt_value("share", chk.get("share_within_1_if_recoveries_excluded")),
                fmt_value("x", chk["max_abs_diff_if_recoveries_excluded"]),
                "已" if chk["total_pymnt_includes_recoveries"] else "不",
            )
        )
    if "net_cash_definition" in notes:
        note_items.append(notes["net_cash_definition"])
    if notes.get("rare_categories_merged"):
        merged = notes["rare_categories_merged"]
        label = notes.get("rare_category_label", "OTHER_RARE")
        share = notes.get("rare_category_min_share", 0.01)
        note_items.append(
            f"占比 < {share:.0%} 的类别并入 {label}（按全样本频率计算，不使用标签）：" + "；".join(f"{k}: {', '.join(v)}" for k, v in merged.items())
        )
    if notes.get("indeterminate_statuses"):
        ind = notes["indeterminate_statuses"]
        note_items.append("终态映射时剔除的 indeterminate 状态：" + "，".join(f"{k} {v:,}" for k, v in ind.items()))
    if note_items:
        blocks.append(bullet(note_items, title="1.9 adapter 说明"))
    if meta.warnings or split.get("warnings"):
        blocks.append(warning_block(list(meta.warnings) + list(split.get("warnings", [])), title="adapter / 切分警告"))
    intro = "数据来源、样本定义的每条规则及其影响、字段审计（哪些字段因为是贷后信息而剔除）、缺失率与 bad rate 随时间的变化。"
    return section(1, "样本与数据概况", intro, blocks)


def _variant_prefix(result: RunResult, v: VariantResult) -> str:
    return f"[{'含' if v.use_platform_rating else '不含'}平台评级] " if len(result.variants) > 1 else ""


def build_section_2(result: RunResult, out_dir: Path, embed: bool) -> dict[str, Any]:
    cfg = result.config
    blocks: list[dict[str, Any]] = []
    for v in result.variants:
        prefix = _variant_prefix(result, v)
        fallback = v.binner.fallback_features_
        blocks.append(
            kv(
                [
                    ("分箱后端", v.binner.backend + (f"（{len(fallback)} 个特征库未给出切点，退到 tree：{', '.join(fallback[:8])}{'…' if len(fallback) > 8 else ''}）" if fallback else "")),
                    ("method / min_samples / max_bins", f"{cfg.binning.method} / {cfg.binning.min_samples} / {cfg.binning.max_bins}"),
                    ("单调性约束", "是（不单调则合并相邻箱直至单调或退到 2 箱）" if cfg.binning.monotonic else "否"),
                    ("切点搜索样本量", f"{min(cfg.binning.sample_size, int((result.labels == TRAIN).sum())):,}（WOE / IV 在全部 train 上计算；筛选阈值也在 train 上评估）"),
                    ("WOE 定义", "WOE = ln(good 占比 / bad 占比)，越大越安全；缺失单独一箱"),
                    ("候选特征 → 入模特征", f"{len(v.candidate_features)} → {len(v.selected)}"),
                ],
                title=f"{prefix}2.1 分箱设置",
            )
        )
        sel = v.selection.table.copy()
        iv_full = sel[["feature", "kind", "iv", "missing_rate", "n_bins", "selected", "step", "reason"]].sort_values("iv", ascending=False).reset_index(drop=True)
        path = fig.plot_iv_bars(iv_full, out_dir / "figures" / f"03_iv_ranking_{v.name}.png", top=30, min_iv=cfg.select.min_iv, leakage_iv=cfg.select.leakage_iv)
        blocks.append(figure_block(path, out_dir, f"{prefix}图 2.1 IV 排名（前 30；绿色 = 入模）", embed))
        blocks.append(
            table_block(
                iv_full,
                title=f"{prefix}2.2 IV 排名表（全部候选特征，按 IV 降序）",
                rename={"feature": "特征", "kind": "类型", "iv": "IV", "missing_rate": "缺失率（train）", "n_bins": "箱数", "selected": "入模", "step": "剔除步骤", "reason": "原因"},
                collapsed=len(iv_full) > 40,
            )
        )
        funnel_rows = [{"step": "候选特征", "dropped": np.nan, "n": len(sel)}]
        years = v.selection.time_years
        labels = {"1_missing": f"缺失率 > {cfg.select.max_missing:.0%}", "2_iv": f"IV < {cfg.select.min_iv}",
                  "2b_time_csi": f"时间稳定性 CSI > {cfg.select.max_time_csi}（train 内 {years[0]} vs {years[1]}）" if years else "时间稳定性（无 issue_date，跳过）",
                  "3_corr": f"|corr| > {cfg.select.max_corr}（保留 IV 高者）",
                  "4_max_features": f"超出 max_features = {cfg.select.max_features}", "5_sign": "LR 系数为正（WOE 方向反转）"}
        remaining = len(sel)
        for step, label in labels.items():
            n_dropped = int((sel["step"] == step).sum())
            if n_dropped == 0 and step in ("4_max_features",):
                continue
            remaining -= n_dropped
            funnel_rows.append({"step": label, "dropped": n_dropped, "n": remaining})
        blocks.append(table_block(pd.DataFrame(funnel_rows, columns=["step", "dropped", "n"]), title=f"{prefix}2.3 特征筛选漏斗", rename={"step": "步骤", "dropped": "剔除", "n": "剩余"}))
        if v.selection.time_csi is not None and years:
            tc = v.selection.time_csi.merge(sel[["feature", "iv"]], on="feature", how="left").sort_values("time_csi", ascending=False)
            dropped_tc = tc[tc["time_csi"] > cfg.select.max_time_csi]
            tc_cols = ["feature", "iv", "time_csi", "shift_bin", "early_share", "late_share"]
            tc_rename = {"feature": "特征", "iv": "IV", "time_csi": "time CSI", "shift_bin": "偏移最大的箱", "early_share": f"{years[0]} 占比", "late_share": f"{years[1]} 占比"}
            if len(dropped_tc):
                blocks.append(table_block(dropped_tc[tc_cols], title=f"{prefix}2.3b 因时间不稳定剔除的特征（train 内 {years[0]} vs {years[1]}，CSI > {cfg.select.max_time_csi}）", rename=tc_rename,
                                          note="在 train 内部就已随时间漂移的特征（多数是某年起才有值的字段）不进评分卡，这样第 6 节的 CSI 只反映 OOT 上的真实漂移。"))
            else:
                blocks.append(p(f"{prefix}2.3b 时间稳定性：没有特征因 train 内 {years[0]} vs {years[1]} 的 CSI > {cfg.select.max_time_csi} 被剔除（最大 {float(tc['time_csi'].max()):.3f}，{tc.iloc[0]['feature']}）。"))
            blocks.append(table_block(tc[tc_cols], title=f"{prefix}时间稳定性 CSI（通过缺失率与 IV 筛选的全部候选特征）", rename=tc_rename, collapsed=True))
        if v.selection.leakage_suspects:
            blocks.append(warning_block([f"IV > {cfg.select.leakage_iv} 的特征（疑似 leakage，已保留，需人工确认）：" + ", ".join(v.selection.leakage_suspects)]))

        mono = v.iv_table[v.iv_table["feature"].isin(v.selected)][["feature", "kind", "backend", "n_bins_initial", "monotone_before", "n_bins", "monotone_after", "max_bin_share"]]
        blocks.append(
            table_block(
                mono,
                title=f"{prefix}2.4 单调性检查（入模特征）",
                rename={"feature": "特征", "kind": "类型", "backend": "切点来源", "n_bins_initial": "初始箱数", "monotone_before": "初始单调", "n_bins": "最终箱数（含缺失箱）", "monotone_after": "最终单调", "max_bin_share": "最大箱占比"},
                note="类别型特征按 train bad rate 排序后再分箱，因此天然单调。数值型不单调时合并相邻箱，直到 bad rate 单调或只剩 2 箱。切点来源 unique_values = 取值数不超过 max_bins、逐值成箱。",
            )
        )
        top = [f for f in v.iv_table["feature"] if f in v.selected][: cfg.report.top_woe_plots]
        for i, name in enumerate(top, 1):
            path = fig.plot_woe(v.binner.bins_[name], out_dir / "figures" / f"04_woe_{v.name}_{i:02d}_{name}.png")
            blocks.append(figure_block(path, out_dir, f"{prefix}图 2.{i + 1} {name} 的 WOE（IV 第 {i} 名）", embed))
        for name in v.selected:
            t = v.binner.bins_[name].table()[["bin", "count", "share", "bad", "bad_rate", "woe"]]
            blocks.append(table_block(t, title=f"{prefix}分箱表：{name}（IV = {v.binner.bins_[name].iv:.4f}）", rename={"bin": "分箱", "count": "人数", "share": "占比", "bad": "bad 数", "bad_rate": "bad rate", "woe": "WOE"}, collapsed=True))
    intro = "在 train 上做单调 WOE 分箱并计算 IV；按缺失率、IV、相关性和系数符号筛选入模特征。"
    return section(2, "分箱与 IV", intro, blocks)


def build_section_3(result: RunResult, out_dir: Path, embed: bool) -> dict[str, Any]:
    cfg = result.config
    blocks: list[dict[str, Any]] = []
    for v in result.variants:
        prefix = _variant_prefix(result, v)
        blocks.append(
            table_block(
                v.coef_table,
                title=f"{prefix}3.1 LR 系数表（WOE 输入；WOE 越大越安全，系数应为负）",
                rename={"feature": "特征", "coefficient": "系数", "iv": "IV", "vif": "VIF"},
                note=f"LogisticRegression(penalty=l2, C={cfg.model.lr_C})；VIF > {cfg.select.max_vif} 标警。",
            )
        )
        m = v.metrics.copy()
        m["segment"] = m["segment"].map(SEGMENT_LABELS)
        blocks.append(table_block(m, title=f"{prefix}3.2 train / test / OOT 表现", rename={"model": "模型", "segment": "样本", "n": "行数", "bad_rate": "bad rate", "auc": "AUC", "ks": "KS", "gini": "Gini"}))
        cv_rows = []
        for key, label in (("lr", "LR scorecard"), ("gbdt", "GBDT challenger")):
            c = v.cv.get(key)
            if c:
                cv_rows.append({"model": label, "auc": f"{c['cv_auc_mean']:.4f} ± {c['cv_auc_std']:.4f}", "ks": f"{c['cv_ks_mean']:.4f} ± {c['cv_ks_std']:.4f}", "folds": len(c["cv_auc_folds"])})
        if cv_rows:
            blocks.append(table_block(pd.DataFrame(cv_rows), title=f"{prefix}3.3 {cfg.model.cv_folds} 折 CV（train 内；每折重做分箱与 WOE）", rename={"model": "模型", "auc": "AUC 均值 ± std", "ks": "KS 均值 ± std", "folds": "折数"}))
        comp_rows = []
        for seg in (TEST, OOT):
            for metric in ("auc", "ks"):
                lr = v.metrics[(v.metrics["model"] == "LR scorecard") & (v.metrics["segment"] == seg)]
                gb = v.metrics[(v.metrics["model"] == "GBDT challenger") & (v.metrics["segment"] == seg)]
                if lr.empty or gb.empty:
                    continue
                a, b = float(lr[metric].iloc[0]), float(gb[metric].iloc[0])
                comp_rows.append({"metric": f"{SEGMENT_LABELS[seg]} {metric.upper()}", "lr": a, "gbdt": b, "diff": b - a})
        if comp_rows:
            blocks.append(table_block(pd.DataFrame(comp_rows), title=f"{prefix}3.4 LR vs GBDT challenger", rename={"metric": "指标", "lr": "LR scorecard", "gbdt": "GBDT", "diff": "GBDT − LR"}, formats={"lr": "{:.4f}", "gbdt": "{:.4f}", "diff": "{:+.4f}"}, note="challenger 直接使用未 WOE 的原始候选特征（含缺失），只作为性能上限参照，不上线。"))
        curves = {k.replace("|", " · "): c for k, c in v.roc.items() if k.startswith("LR scorecard") or k.endswith(TEST) or k.endswith(OOT)}
        path = fig.plot_roc(curves, out_dir / "figures" / f"05_roc_{v.name}.png", "ROC: LR scorecard vs GBDT challenger")
        blocks.append(figure_block(path, out_dir, f"{prefix}图 3.1 ROC 曲线", embed))
        test_part = v.scores[v.scores["segment"] == TEST]
        if not test_part.empty:
            path = fig.plot_ks(test_part[TARGET].to_numpy(), test_part["pd_lr"].to_numpy(), out_dir / "figures" / f"06_ks_{v.name}.png", "KS curve, LR scorecard (test)")
            blocks.append(figure_block(path, out_dir, f"{prefix}图 3.2 KS 曲线（LR，test）", embed))
            kst = v.ks_table[["band", "n", "bad", "bad_rate", "cum_bad_share", "cum_good_share", "ks"]]
            blocks.append(table_block(kst, title=f"{prefix}KS 分段表（test，按 LR 预测概率从高风险到低风险 10 等分）", rename={"band": "分段", "n": "人数", "bad": "bad 数", "bad_rate": "bad rate", "cum_bad_share": "累计 bad 占比", "cum_good_share": "累计 good 占比", "ks": "KS"}, collapsed=True))
    if len(result.variants) == 1:
        which = "含" if result.variants[0].use_platform_rating else "不含"
        blocks.append(p(f"本次只跑“{which}平台评级”一套模型；“含 / 不含平台评级”并排对比需要 features.use_platform_rating: [false, true]（configs/lendingclub.yaml 的默认）。"))
    intro = "WOE 逻辑回归评分卡与 GBDT challenger 在 train / test / OOT 上的 AUC、KS、Gini，以及 train 内交叉验证（每折重做分箱与 WOE；入模变量清单固定自全 train）。"
    return section(3, "模型表现", intro, blocks)


def build_section_4(result: RunResult, out_dir: Path, embed: bool) -> dict[str, Any]:
    cfg = result.config
    blocks: list[dict[str, Any]] = []
    for v in result.variants:
        prefix = _variant_prefix(result, v)
        card = v.scorecard
        blocks.append(
            kv(
                [
                    ("PDO / base score / base odds", f"{cfg.scorecard.pdo} / {cfg.scorecard.base_score} / {cfg.scorecard.base_odds}:1"),
                    ("Factor = PDO / ln2", f"{card.factor:.4f}"),
                    ("Offset = base − Factor × ln(odds)", f"{cfg.scorecard.base_score} − {card.factor:.4f} × ln({cfg.scorecard.base_odds}) = {card.offset:.4f}"),
                    ("LR 截距 b0", f"{card.intercept:.4f}"),
                    ("基础分 = Offset − Factor × b0", f"{card.base_points:.2f} → 取整 {card.base_points_int}"),
                    ("分箱分数", "points = −Factor × 系数 × WOE，取整"),
                    ("可能的分数范围", f"{card.min_score} ~ {card.max_score}"),
                    ("整数分数的 AUC（test / OOT）", " / ".join(f"{SEGMENT_LABELS[s]} {a:.4f}" for s, a in v.score_auc.items() if s in (TEST, OOT))),
                ],
                title=f"{prefix}4.1 PDO 换算",
            )
        )
        t = v.scorecard_table[["variable", "bin", "count", "share", "bad_rate", "woe", "coefficient", "points", "points_int"]]
        blocks.append(table_block(t, title=f"{prefix}4.2 评分卡表", rename={"variable": "变量", "bin": "分箱", "count": "train 人数", "share": "占比", "bad_rate": "bad rate", "woe": "WOE", "coefficient": "系数", "points": "分数", "points_int": "整数分"}, formats={"points": "{:.2f}"}))
        for seg in (TEST, OOT):
            part = v.scores[v.scores["segment"] == seg]
            if part.empty:
                continue
            path = fig.plot_score_distribution(part["score"].to_numpy(), part[TARGET].to_numpy(), out_dir / "figures" / f"07_score_dist_{v.name}_{seg}.png", f"Score distribution, {SEGMENT_LABELS[seg]} (good vs bad)")
            blocks.append(figure_block(path, out_dir, f"{prefix}图 4.{1 if seg == TEST else 2} 分数分布（{SEGMENT_LABELS[seg]}，good / bad 分开）", embed))
    intro = "把 WOE 逻辑回归换算为评分卡：PDO、base score、base odds，每个变量每个分箱的分数，以及分数分布。"
    return section(4, "评分卡", intro, blocks)


def build_placeholder_section(number: int, title: str, intro: str, planned: list[str]) -> dict[str, Any]:
    return section(number, title, intro, [placeholder_block(planned)], implemented=False)


def build_appendix(result: RunResult) -> dict[str, Any]:
    ri = result.run_info
    blocks: list[dict[str, Any]] = []
    blocks.append(
        kv(
            [
                ("config", f"{ri.get('config_path')}（hash {ri.get('config_hash')}）"),
                ("数据文件", f"{ri.get('data_file')}；原始 {ri.get('n_raw_rows', 0):,} 行 → 样本 {ri.get('n_rows', 0):,} 行"),
                ("git commit", ri.get("git_commit") or "（未提交）"),
                ("运行时间", ri.get("timestamp")),
                ("总耗时", f"{ri.get('duration_seconds', 0)} s"),
                ("版本", ", ".join(f"{k} {v}" for k, v in ri.get("versions", {}).items())),
                ("缓存", ri.get("cache_hit") or "未命中 / 未启用"),
            ],
            title="运行元数据",
        )
    )
    timings = pd.DataFrame([{"step": k, "seconds": v} for k, v in ri.get("timings", {}).items()])
    if len(timings):
        blocks.append(table_block(timings, title="各步骤耗时", rename={"step": "步骤", "seconds": "秒"}, formats={"seconds": "{:.1f}"}, collapsed=True))
    blocks.append({"type": "code", "title": "完整 config", "text": yaml.safe_dump(result.config.raw, allow_unicode=True, sort_keys=False)})
    return section(8, "附录：运行元数据", "", blocks)


# --------------------------------------------------------------------------- entry point
def build_report(result: RunResult, out_dir: Path) -> dict[str, Any]:
    fig.apply_style()
    embed = bool(result.config.report.embed_figures)
    (out_dir / "figures").mkdir(parents=True, exist_ok=True)
    primary = result.primary
    sections = [
        build_section_1(result, out_dir, embed),
        build_section_2(result, out_dir, embed),
        build_section_3(result, out_dir, embed),
        build_section_4(result, out_dir, embed),
    ]
    if result.strategy is not None and strategy_mod.IMPLEMENTED:
        sections.append(strategy_mod.build_section(result, out_dir, embed))  # type: ignore[attr-defined]
    else:
        sections.append(build_placeholder_section(5, "策略分析", "分数段表、通过率–坏账率曲线、候选 cut-off、利润曲线与 swap set。",
                                                  ["等频 10 段分数段表", "通过率 50/60/70/80/90% 的 cut-off 与 bad rate", "利润曲线与利润最大化 cut-off（基于 net_cash）", "与平台评级基准的 swap set 2×2 表"]))
    if result.monitor is not None and monitor_mod.IMPLEMENTED:
        sections.append(monitor_mod.build_section(result, out_dir, embed))  # type: ignore[attr-defined]
    else:
        sections.append(build_placeholder_section(6, "稳定性", "score PSI、入模特征 CSI、vintage 曲线。",
                                                  ["score PSI：train → test、train → OOT（10 等频段）", "每个入模特征的 CSI（train → OOT）", "PSI 0.10 / 0.25 阈值标色", "vintage 曲线（按 issue 季度）"]))
    if result.checks is not None and checks_mod.IMPLEMENTED:
        sections.append(checks_mod.build_section(result, out_dir, embed))  # type: ignore[attr-defined]
    else:
        sections.append(build_placeholder_section(7, "自动检查与风险提示", "对 leakage、单箱占比、KS 差、PSI、高缺失率入模等做自动检查。",
                                                  ["IV > 0.5 的特征（疑似 leakage）", "单一分箱占比 > 90% 的特征", "train–test KS 差 > 0.05", "PSI > 0.25", "缺失率 > 50% 仍入模", "adapter 报告的警告"]))
    sections.append(build_appendix(result))

    ri = result.run_info
    title = result.config.report.title or f"{result.meta.name} 信用评分卡与策略分析报告"
    header = [
        ("数据", f"{ri.get('data_file')}（{ri.get('n_rows', 0):,} 行）"),
        ("config hash", ri.get("config_hash")),
        ("git commit", ri.get("git_commit") or "—"),
        ("生成时间", ri.get("timestamp")),
    ]
    metrics = primary.metrics[primary.metrics["model"] == "LR scorecard"].set_index("segment")
    headline = [
        ("样本", f"{len(result.frame):,} 笔，bad rate {result.frame[TARGET].mean():.2%}"),
        ("入模特征", f"{len(primary.selected)} / {len(primary.candidate_features)}"),
    ]
    for seg in (TRAIN, TEST, OOT):
        if seg in metrics.index:
            headline.append((f"{SEGMENT_LABELS[seg]} AUC / KS", f"{metrics.loc[seg, 'auc']:.4f} / {metrics.loc[seg, 'ks']:.4f}"))
    st = result.strategy
    if st and strategy_mod.IMPLEMENTED and st["variants"].get(primary.name):
        segs = st["variants"][primary.name]
        seg = OOT if OOT in segs else next(iter(segs))
        c = segs[seg]["constrained"]["by_bad_rate"]
        if c.get("feasible"):
            headline.append((f"cut-off（{SEGMENT_LABELS[seg]}，bad rate ≤ {st['max_bad_rate']:.0%}）", f"score ≥ {int(c['cutoff_score'])}：通过率 {c['approval_rate']:.1%}，bad rate {c['bad_rate_approved']:.2%}"))
    return {
        "title": title,
        "header": header,
        "headline": headline,
        "warnings": result.warnings,
        "sections": sections,
        "placeholder": PLACEHOLDER,
    }


def md_table(block: dict[str, Any]) -> str:
    cols = block["columns"]
    lines = ["| " + " | ".join(str(c) for c in cols) + " |", "|" + "|".join(["---"] * len(cols)) + "|"]
    for row in block["rows"]:
        lines.append("| " + " | ".join(str(c).replace("|", "\\|").replace("\n", " ") for c in row) + " |")
    return "\n".join(lines)


def render_report(result: RunResult, out_dir: Path) -> dict[str, Path]:
    out_dir = Path(out_dir)
    ctx = build_report(result, out_dir)
    # select_autoescape matches on the final suffix only (".j2"), so decide by full name instead.
    env = Environment(
        loader=PackageLoader("scorecard", "templates"),
        autoescape=lambda name: bool(name) and name.endswith(".html.j2"),
        trim_blocks=True,
        lstrip_blocks=True,
    )
    env.globals["md_table"] = md_table
    html = env.get_template("report.html.j2").render(**ctx)
    md = env.get_template("report.md.j2").render(**ctx)
    html_path, md_path = out_dir / "report.html", out_dir / "report.md"
    html_path.write_text(html, encoding="utf-8")
    md_path.write_text(md, encoding="utf-8")
    return {"html": html_path, "md": md_path}
