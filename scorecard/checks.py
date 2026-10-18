"""Automatic checks and risk flags (report section 7, PLAN.md §3).

Every row says what was checked, the threshold, the observed value and a status:
pass / warn / fail / info. Thresholds come from config `checks`. Adapter and split warnings are
appended as info rows so nothing an earlier step flagged can get lost.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import TYPE_CHECKING, Any

import pandas as pd

from scorecard.adapters.base import TARGET
from scorecard.split import OOT, TEST, TRAIN

if TYPE_CHECKING:
    from scorecard.pipeline import RunResult, VariantResult

log = logging.getLogger(__name__)

IMPLEMENTED = True
PASS, WARN, FAIL, INFO = "pass", "warn", "fail", "info"
STATUS_LABELS = {PASS: "🟢 通过", WARN: "🟡 警告", FAIL: "🔴 不通过", INFO: "ℹ️ 提示"}
BAD_RATE_RANGE = (0.01, 0.40)
KS_SUSPICIOUS = 0.9


def _variant_label(result: RunResult, v: VariantResult) -> str:
    if len(result.variants) == 1:
        return "模型"
    return "含平台评级" if v.use_platform_rating else "不含平台评级"


def _metric(v: VariantResult, model: str, segment: str, metric: str) -> float:
    m = v.metrics[(v.metrics["model"] == model) & (v.metrics["segment"] == segment)]
    return float(m[metric].iloc[0]) if not m.empty else float("nan")


def run_checks(result: RunResult) -> dict[str, Any]:
    cfg = result.config.checks
    rows: list[dict[str, Any]] = []

    def add(check: str, scope: str, threshold: str, value: str, status: str, detail: str = "") -> None:
        rows.append({"check": check, "scope": scope, "threshold": threshold, "value": value, "status": status, "detail": detail})

    # ----- dataset level
    bad_rate = float(result.frame[TARGET].mean())
    lo, hi = BAD_RATE_RANGE
    add("样本 bad rate 在合理区间", "数据", f"{lo:.0%}–{hi:.0%}", f"{bad_rate:.2%}", PASS if lo <= bad_rate <= hi else FAIL,
        "" if lo <= bad_rate <= hi else "bad rate 异常：检查标签定义 / 样本定义规则")

    monitor = result.monitor or {}
    strategy = result.strategy or {}
    for v in result.variants:
        scope = _variant_label(result, v)
        iv = v.iv_table.set_index("feature")
        selected = list(v.selected)

        # 1. IV > leakage threshold (any candidate feature)
        suspects = iv[iv["iv"] > cfg.leakage_iv]
        in_model = [f for f in suspects.index if f in selected]
        if len(suspects) == 0:
            add("IV 过高（疑似 leakage）", scope, f"IV > {cfg.leakage_iv}", f"最高 IV {float(iv['iv'].max()):.4f}（{iv['iv'].idxmax()}）", PASS)
        else:
            listed = ", ".join(f"{f} {float(suspects.loc[f, 'iv']):.3f}" for f in suspects.index[:8])
            review = result.meta.notes.get("iv_review")
            add("IV 过高（疑似 leakage）", scope, f"IV > {cfg.leakage_iv}", f"{len(suspects)} 个特征", (WARN if review else FAIL) if in_model else WARN,
                ("已入模：" + ", ".join(in_model) + "。" if in_model else "未入模。") + f"清单：{listed}。" + (f"adapter 说明：{review}" if review else "请核对这些字段是否为贷后信息"))

        # 2. single bin share > threshold (scorecard features)
        shares = iv.loc[selected, "max_bin_share"]
        heavy = shares[shares > cfg.single_bin_share]
        add("入模特征单一分箱占比过高", scope, f"最大箱占比 > {cfg.single_bin_share:.0%}", f"最大 {float(shares.max()):.1%}（{shares.idxmax()}）" if len(shares) else "—",
            WARN if len(heavy) else PASS, ("几乎所有人落在同一箱，区分度来自极少数人：" + ", ".join(f"{f} {s:.1%}" for f, s in heavy.items())) if len(heavy) else "")

        # 3. train-test KS gap (overfitting)
        for model_name in ("LR scorecard", "GBDT challenger"):
            ks_tr, ks_te = _metric(v, model_name, TRAIN, "ks"), _metric(v, model_name, TEST, "ks")
            gap = ks_tr - ks_te
            add(f"train–test KS 差（{model_name}）", scope, f"KS(train) − KS(test) > {cfg.ks_gap}", f"{ks_tr:.4f} − {ks_te:.4f} = {gap:+.4f}",
                WARN if gap > cfg.ks_gap else PASS, "train 明显好于 test，模型可能过拟合" if gap > cfg.ks_gap else "")
        ks_te = _metric(v, "LR scorecard", TEST, "ks")
        add("test KS 高得不合理", scope, f"KS > {KS_SUSPICIOUS}", f"{ks_te:.4f}", FAIL if ks_te > KS_SUSPICIOUS else PASS,
            "几乎肯定存在 leakage" if ks_te > KS_SUSPICIOUS else "")

        # 4. PSI / CSI above the alert threshold
        mv = monitor.get("variants", {}).get(v.name)
        if mv is not None:
            for r in mv["score_psi"].itertuples(index=False):
                seg_label = {TEST: "test", OOT: "OOT"}.get(r.segment, r.segment)
                add(f"score PSI train → {seg_label}", scope, f"PSI > {cfg.psi_alert}", f"{r.psi:.4f}", FAIL if r.psi > cfg.psi_alert else (WARN if r.psi > monitor["thresholds"]["warn"] else PASS),
                    "分数分布已明显偏移，需重新评估 cut-off" if r.psi > cfg.psi_alert else "")
            key = mv["csi_key"]
            alerts = mv["csi"][mv["csi"][key] > cfg.psi_alert]
            add(f"入模特征 CSI（train → {'OOT' if key == 'csi_oot' else 'test'}）", scope, f"CSI > {cfg.psi_alert}", f"{len(alerts)} / {len(mv['csi'])} 个特征",
                WARN if len(alerts) else PASS, ("分布偏移：" + ", ".join(f"{r.feature} {getattr(r, key):.3f}" for r in alerts.itertuples(index=False))) if len(alerts) else "")

        # 5. missing rate > threshold among scorecard features (train)
        miss = iv.loc[selected, "missing_share"]
        high = miss[miss > cfg.missing_in_model]
        add("入模特征缺失率过高", scope, f"train 缺失率 > {cfg.missing_in_model:.0%}", f"最高 {float(miss.max()):.1%}（{miss.idxmax()}）" if len(miss) else "—",
            WARN if len(high) else PASS, ("缺失箱承担了大部分样本：" + ", ".join(f"{f} {s:.1%}" for f, s in high.items())) if len(high) else "")

        # 6. coefficient signs and VIF
        coef = v.coef_table[v.coef_table["feature"] != "(intercept)"]
        positive = coef[coef["coefficient"] > 0]
        add("LR 系数符号（WOE 越大越安全，系数应为负）", scope, "系数 > 0", f"{len(positive)} / {len(coef)} 个为正", FAIL if len(positive) else PASS,
            ("分数方向被反转：" + ", ".join(positive["feature"])) if len(positive) else "")
        vif = coef["vif"].dropna()
        max_vif = result.config.select.max_vif
        high_vif = coef[coef["vif"] > max_vif]
        add("入模特征 VIF", scope, f"VIF > {max_vif}", f"最高 {float(vif.max()):.2f}（{coef.loc[vif.idxmax(), 'feature']}）" if len(vif) else "—",
            WARN if len(high_vif) else PASS, ("共线性：" + ", ".join(f"{r.feature} {r.vif:.1f}" for r in high_vif.itertuples(index=False))) if len(high_vif) else "")

        # 7. swap set: the model should swap in better loans than it swaps out
        sv = strategy.get("variants", {}).get(v.name, {})
        for seg in (OOT, TEST):
            if seg in sv:
                sw = sv[seg]["swap"]
                worse = sw["swap_in_bad_rate"] > sw["swap_out_bad_rate"]
                base = "平台评级" if strategy["baseline"]["kind"] == "platform_grade" else "随机"
                add(f"swap set：swap-in bad rate 低于 swap-out（{'OOT' if seg == OOT else 'test'}，基准 = {base}）", scope, "swap-in > swap-out", f"{sw['swap_in_bad_rate']:.2%} vs {sw['swap_out_bad_rate']:.2%}",
                    WARN if worse else PASS, "在模型与基准意见不同的客户上，模型反而更差：检查 leakage、客群变化或基准定义" if worse else "")
                break

    # ----- warnings from earlier steps
    for w in list(result.meta.warnings) + list(result.split_info.get("warnings", [])):
        add("adapter / 切分警告", "数据", "—", "—", INFO, w)
    for v in result.variants:
        for w in v.warnings:
            add("建模警告", _variant_label(result, v), "—", "—", INFO, w)

    table = pd.DataFrame(rows, columns=["check", "scope", "threshold", "value", "status", "detail"])
    counts = table["status"].value_counts()
    out = {"table": table, **{f"n_{s}": int(counts.get(s, 0)) for s in (PASS, WARN, FAIL, INFO)}}
    log.info("checks: %d pass, %d warn, %d fail, %d info", out["n_pass"], out["n_warn"], out["n_fail"], out["n_info"])
    return out


def write_artifacts(result: RunResult, out_dir: Path) -> None:
    if result.checks:
        result.checks["table"].to_csv(out_dir / "checks.csv", index=False)


def build_section(result: RunResult, out_dir: Path, embed: bool) -> dict[str, Any]:  # noqa: ARG001
    from scorecard.report import kv, p, section, table_block

    checks = result.checks
    assert checks is not None
    table = checks["table"].copy()
    table["status"] = table["status"].map(STATUS_LABELS)
    blocks: list[dict[str, Any]] = [
        kv(
            [
                ("通过 / 警告 / 不通过 / 提示", f"{checks['n_pass']} / {checks['n_warn']} / {checks['n_fail']} / {checks['n_info']}"),
                ("结论", "存在不通过项，报告中的模型不应直接上线，先处理第 7 节列出的问题" if checks["n_fail"] else ("有警告项，需要人工判断" if checks["n_warn"] else "全部检查通过")),
            ],
            title="7.0 汇总",
        ),
        table_block(
            table,
            title="7.1 检查清单",
            rename={"check": "检查项", "scope": "范围", "threshold": "阈值", "value": "结果", "status": "判定", "detail": "说明"},
        ),
        p("阈值来自 config `checks`；IV / 单箱占比 / 缺失率在 train 上计算，PSI / CSI 见第 6 节，KS 见第 3 节，swap set 见第 5 节。这些检查只提示风险，不会自动改模型。"),
    ]
    intro = "对 leakage、单箱占比、train–test KS 差、PSI / CSI、高缺失率入模、系数符号与 VIF 的自动检查，并汇总 adapter 与建模警告。"
    return section(7, "自动检查与风险提示", intro, blocks)
