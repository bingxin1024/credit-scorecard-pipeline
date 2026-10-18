"""Strategy layer (PLAN.md §6.1–6.2): score bands, approval-rate / bad-rate curve, candidate
cut-offs, profit curve from realised net cash, and the swap set against the platform baseline.

Conventions
* Higher score = safer. A cut-off c approves every loan with score >= c. Scores are integers, so a
  target approval rate is matched by the cut-off whose actual approval rate is closest to it, and
  the actual rate is reported next to the target.
* Everything is evaluated on test and OOT separately; train is never used for strategy numbers.
* `net_cash` is the realised net cash flow the adapter supplies (strategy layer only, never a
  feature). Datasets without it skip the profit curve and say so.
* Swap-set baseline: the platform grade, approving from the best grade downwards until exactly as
  many loans are approved as the model's cut-off approves (ties inside the marginal grade are
  broken at random, seeded). Without a platform grade: a random strategy at the same approval rate.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import TYPE_CHECKING, Any

import numpy as np
import pandas as pd

from scorecard.adapters.base import NET_CASH, TARGET
from scorecard.split import OOT, TEST

if TYPE_CHECKING:
    from scorecard.pipeline import RunResult

log = logging.getLogger(__name__)

IMPLEMENTED = True
SEGMENTS = (TEST, OOT)
NO_NET_CASH = "数据不含回款信息，跳过"
CELL_LABELS = {
    "both_approve": "双批（模型批、基准批）",
    "swap_in": "swap-in（模型批、基准拒）",
    "swap_out": "swap-out（模型拒、基准批）",
    "both_reject": "双拒（模型拒、基准拒）",
}
PROFIT_CRITERIA = {"best_total": "总净现金最大", "best_per_loan": "每笔净现金最大", "approve_all": "全部通过（参照）"}


def _fmt_score(value: float) -> str:
    value = float(value)
    return f"{int(value)}" if value.is_integer() else f"{value:.4g}"


# --------------------------------------------------------------------------- §6.1 bands / curve / cut-offs
def score_bands(scores, y, n_bands: int = 10, net_cash=None) -> pd.DataFrame:
    """Approximately equal-frequency score bands; band 1 = highest scores (safest).

    Bands are right-closed score intervals cut at the score quantiles, so they never overlap. With
    integer scores the counts are only approximately equal because tied scores stay in one band.
    """
    s = np.asarray(scores, dtype=float)
    y = np.asarray(y, dtype=float)
    n = len(s)
    edges = np.unique(np.quantile(s, np.linspace(0, 1, n_bands + 1)[1:-1]))
    edges = edges[edges < s.max()]
    ids = np.searchsorted(edges, s, side="left")  # 0 = lowest scores
    frame = pd.DataFrame({"band": len(edges) + 1 - ids, "score": s, "y": y})
    agg: dict[str, tuple[str, str]] = {
        "score_min": ("score", "min"),
        "score_max": ("score", "max"),
        "n": ("y", "size"),
        "bad": ("y", "sum"),
    }
    if net_cash is not None:
        frame["net_cash"] = np.asarray(net_cash, dtype=float)
        agg["net_cash_total"] = ("net_cash", "sum")
    g = frame.groupby("band").agg(**agg).sort_index()
    g["interval"] = [f"{_fmt_score(a)}–{_fmt_score(b)}" if a != b else _fmt_score(a) for a, b in zip(g["score_min"], g["score_max"])]
    g["share"] = g["n"] / n
    g["bad_rate"] = g["bad"] / g["n"]
    g["cum_n"] = g["n"].cumsum()
    g["cum_approval_rate"] = g["cum_n"] / n
    g["cum_bad_rate"] = g["bad"].cumsum() / g["cum_n"]
    cols = ["band", "interval", "n", "share", "bad", "bad_rate", "cum_n", "cum_approval_rate", "cum_bad_rate"]
    if net_cash is not None:
        g["net_cash_per_loan"] = g["net_cash_total"] / g["n"]
        cols += ["net_cash_total", "net_cash_per_loan"]
    g["bad"] = g["bad"].astype(int)
    return g.reset_index()[cols]


def cutoff_curve(scores, y, net_cash=None) -> pd.DataFrame:
    """One row per distinct score c = 'approve everyone with score >= c', from tight to loose."""
    frame = pd.DataFrame({"score": np.asarray(scores, dtype=float), "y": np.asarray(y, dtype=float)})
    has_cash = net_cash is not None
    agg: dict[str, tuple[str, str]] = {"n": ("y", "size"), "bad": ("y", "sum")}
    if has_cash:
        frame["net_cash"] = np.asarray(net_cash, dtype=float)
        agg["net_cash"] = ("net_cash", "sum")
    g = frame.groupby("score").agg(**agg).sort_index(ascending=False)
    n_total, bad_total = len(frame), float(frame["y"].sum())
    out = pd.DataFrame({"cutoff_score": g.index.to_numpy(dtype=float)})
    out["n_approved"] = g["n"].cumsum().to_numpy()
    out["approval_rate"] = out["n_approved"] / n_total
    out["bad_approved"] = g["bad"].cumsum().to_numpy()
    out["bad_rate_approved"] = out["bad_approved"] / out["n_approved"]
    out["n_rejected"] = n_total - out["n_approved"]
    rejected_bad = bad_total - out["bad_approved"]
    out["bad_rate_rejected"] = np.where(out["n_rejected"] > 0, rejected_bad / np.maximum(out["n_rejected"], 1), np.nan)
    if has_cash:
        out["net_cash_total"] = g["net_cash"].cumsum().to_numpy()
        out["net_cash_per_loan"] = out["net_cash_total"] / out["n_approved"]
    out["bad_approved"] = out["bad_approved"].astype(int)
    return out


def pick_cutoffs(curve: pd.DataFrame, targets: list[float]) -> pd.DataFrame:
    """For each target approval rate: the cut-off whose actual approval rate is closest, plus the
    marginal tranche (loans between this cut-off and the previous, tighter candidate)."""
    rows: list[dict[str, Any]] = []
    prev: dict[str, Any] | None = None
    approval = curve["approval_rate"].to_numpy()
    for target in sorted(float(t) for t in targets):
        i = int(np.argmin(np.abs(approval - target)))
        row = curve.iloc[i].to_dict()
        row["target_approval_rate"] = target
        prev_n = prev["n_approved"] if prev else 0
        prev_bad = prev["bad_approved"] if prev else 0
        m_n = int(row["n_approved"] - prev_n)
        row["marginal_n"] = m_n
        row["marginal_bad_rate"] = (row["bad_approved"] - prev_bad) / m_n if m_n > 0 else np.nan
        if "net_cash_total" in row:
            prev_cash = prev["net_cash_total"] if prev else 0.0
            row["marginal_net_cash_per_loan"] = (row["net_cash_total"] - prev_cash) / m_n if m_n > 0 else np.nan
        rows.append(row)
        prev = row
    lead = ["target_approval_rate", "cutoff_score", "approval_rate", "n_approved", "bad_rate_approved", "bad_rate_rejected", "marginal_n", "marginal_bad_rate"]
    frame = pd.DataFrame(rows)
    return frame[lead + [c for c in frame.columns if c not in lead]]


def profit_optimum(curve: pd.DataFrame, min_approval_rate: float = 0.1) -> dict[str, Any]:
    """Cut-offs maximising total and per-loan net cash (searched at approval rate >= min), plus the
    approve-everyone reference."""
    sub = curve[curve["approval_rate"] >= min_approval_rate]
    if sub.empty:
        sub = curve
    cols = ["cutoff_score", "n_approved", "approval_rate", "bad_rate_approved", "net_cash_total", "net_cash_per_loan"]
    picks = {
        "best_total": curve.loc[sub["net_cash_total"].idxmax(), cols].to_dict(),
        "best_per_loan": curve.loc[sub["net_cash_per_loan"].idxmax(), cols].to_dict(),
        "approve_all": curve.iloc[-1][cols].to_dict(),
    }
    table = pd.DataFrame([{"criterion": PROFIT_CRITERIA[k], **v} for k, v in picks.items()])
    return {"table": table, **picks, "min_approval_rate": min_approval_rate}


def constrained_cutoffs(curve: pd.DataFrame, max_bad_rate: float, target_approval_rate: float) -> dict[str, Any]:
    """(a) the loosest cut-off whose approved bad rate stays <= max_bad_rate; (b) the cut-off at the
    target approval rate (closest actual rate) with its bad rate and net cash."""
    cols = ["cutoff_score", "n_approved", "approval_rate", "bad_rate_approved"] + [c for c in ("net_cash_total", "net_cash_per_loan") if c in curve.columns]
    feasible = curve[curve["bad_rate_approved"] <= max_bad_rate]
    if feasible.empty:
        by_bad = {"criterion": f"坏账率上限 {max_bad_rate:.0%} 下通过率最高", **{c: np.nan for c in cols}, "feasible": False}
    else:
        by_bad = {"criterion": f"坏账率上限 {max_bad_rate:.0%} 下通过率最高", **curve.loc[feasible["approval_rate"].idxmax(), cols].to_dict(), "feasible": True}
    i = int(np.argmin(np.abs(curve["approval_rate"].to_numpy() - target_approval_rate)))
    by_rate = {"criterion": f"目标通过率 {target_approval_rate:.0%} 下的坏账率与净现金", **curve.iloc[i][cols].to_dict(), "feasible": True}
    table = pd.DataFrame([by_bad, by_rate])
    return {"table": table, "by_bad_rate": by_bad, "by_approval_rate": by_rate, "max_bad_rate": max_bad_rate, "target_approval_rate": target_approval_rate}


# --------------------------------------------------------------------------- §6.2 swap set
def baseline_order(n: int, grade: pd.Series | None, rng: np.random.Generator) -> tuple[np.ndarray, str]:
    """Row order in which the baseline strategy approves loans (best first).

    Platform grade: ordered category -> its category order; unordered category / strings -> sorted
    ascending (A before B); numeric -> ascending. Missing grade is approved last. Ties (all loans of
    the marginal grade) are broken by a seeded random draw. No grade -> purely random order.
    """
    tie = rng.random(n)
    if grade is None:
        return np.argsort(tie, kind="stable"), "random"
    if isinstance(grade.dtype, pd.CategoricalDtype) and grade.cat.ordered:
        codes = grade.cat.codes.to_numpy(dtype=float)
        codes[codes < 0] = np.nan
    elif pd.api.types.is_numeric_dtype(grade):
        codes = grade.to_numpy(dtype=float)
    else:
        values = grade.astype("object")
        present = sorted({str(v) for v in values if pd.notna(v)})
        rank = {v: i for i, v in enumerate(present)}
        codes = np.array([rank[str(v)] if pd.notna(v) else np.nan for v in values], dtype=float)
    codes = np.where(np.isnan(codes), np.inf, codes)
    return np.lexsort((tie, codes)), "platform_grade"


def swap_set(scores, y, cutoff: float, order: np.ndarray, net_cash=None) -> dict[str, Any]:
    """2x2 model-vs-baseline table at one cut-off; the baseline approves the same number of loans."""
    s = np.asarray(scores, dtype=float)
    y = np.asarray(y, dtype=float)
    n = len(s)
    model = s >= cutoff
    k = int(model.sum())
    base = np.zeros(n, dtype=bool)
    base[order[:k]] = True
    cells = {
        "both_approve": model & base,
        "swap_in": model & ~base,
        "swap_out": ~model & base,
        "both_reject": ~model & ~base,
    }
    cash = np.asarray(net_cash, dtype=float) if net_cash is not None else None
    rows = []
    for key, mask in cells.items():
        row: dict[str, Any] = {
            "cell": key,
            "label": CELL_LABELS[key],
            "n": int(mask.sum()),
            "share": float(mask.mean()),
            "bad": int(y[mask].sum()),
            "bad_rate": float(y[mask].mean()) if mask.any() else np.nan,
        }
        if cash is not None:
            row["net_cash_total"] = float(cash[mask].sum())
            row["net_cash_per_loan"] = row["net_cash_total"] / row["n"] if row["n"] else np.nan
        rows.append(row)
    table = pd.DataFrame(rows)
    by = table.set_index("cell")
    out: dict[str, Any] = {
        "table": table,
        "cutoff_score": float(cutoff),
        "n_approved": k,
        "approval_rate": k / n if n else np.nan,
        "model_bad_rate": float(y[model].mean()) if k else np.nan,
        "baseline_bad_rate": float(y[base].mean()) if k else np.nan,
        "swap_in_n": int(by.loc["swap_in", "n"]),
        "swap_in_bad_rate": float(by.loc["swap_in", "bad_rate"]),
        "swap_out_n": int(by.loc["swap_out", "n"]),
        "swap_out_bad_rate": float(by.loc["swap_out", "bad_rate"]),
    }
    if cash is not None:
        out["model_net_cash"] = float(cash[model].sum())
        out["baseline_net_cash"] = float(cash[base].sum())
    return out


# --------------------------------------------------------------------------- entry point
def analyse(result: RunResult) -> dict[str, Any]:
    cfg = result.config.strategy
    frame, labels, meta = result.frame, result.labels, result.meta
    has_cash = NET_CASH in frame.columns and bool(frame[NET_CASH].notna().any())
    grade_col = meta.platform_grade_col if meta.platform_grade_col and meta.platform_grade_col in frame.columns else None
    seed = result.config.split.random_state
    out: dict[str, Any] = {
        "has_net_cash": has_cash,
        "n_net_cash_missing": int(frame[NET_CASH].isna().sum()) if has_cash else 0,
        "net_cash_definition": meta.notes.get("net_cash_definition"),
        "baseline": {"kind": "platform_grade" if grade_col else "random", "column": grade_col},
        "approval_rates": [float(r) for r in cfg.approval_rates],
        "target_approval_rate": float(cfg.target_approval_rate),
        "max_bad_rate": float(cfg.max_bad_rate),
        "profit_min_approval_rate": float(cfg.profit_min_approval_rate),
        "segments": [],
        "variants": {},
    }
    for v in result.variants:
        per_seg: dict[str, Any] = {}
        for seg in SEGMENTS:
            mask = (labels == seg).to_numpy()
            if not mask.any():
                continue
            part = v.scores.loc[mask]
            s = part["score"].to_numpy(dtype=float)
            y = part[TARGET].to_numpy(dtype=float)
            cash = np.nan_to_num(frame.loc[mask, NET_CASH].to_numpy(dtype=float)) if has_cash else None
            curve = cutoff_curve(s, y, cash)
            cutoffs = pick_cutoffs(curve, cfg.approval_rates)
            grade = frame.loc[mask, grade_col] if grade_col else None
            order, _ = baseline_order(len(s), grade, np.random.default_rng(seed))
            ref = int(np.argmin(np.abs(cutoffs["target_approval_rate"].to_numpy() - cfg.target_approval_rate)))
            swap = swap_set(s, y, float(cutoffs["cutoff_score"].iloc[ref]), order, cash)
            swap["target_approval_rate"] = float(cutoffs["target_approval_rate"].iloc[ref])
            summary_rows = []
            for row in cutoffs.itertuples(index=False):
                sw = swap_set(s, y, float(row.cutoff_score), order, cash)
                sw.pop("table")
                summary_rows.append({"target_approval_rate": float(row.target_approval_rate), **sw})
            per_seg[seg] = {
                "n": int(mask.sum()),
                "bad_rate": float(y.mean()),
                "bands": score_bands(s, y, cfg.score_bands, cash),
                "curve": curve,
                "cutoffs": cutoffs,
                "profit": profit_optimum(curve, cfg.profit_min_approval_rate) if has_cash else None,
                "constrained": constrained_cutoffs(curve, cfg.max_bad_rate, cfg.target_approval_rate),
                "swap": swap,
                "swap_summary": pd.DataFrame(summary_rows),
            }
        out["variants"][v.name] = per_seg
    out["segments"] = [seg for seg in SEGMENTS if any(seg in d for d in out["variants"].values())]
    log.info("strategy: %d variants x %s, net_cash=%s, baseline=%s", len(result.variants), out["segments"], has_cash, out["baseline"]["kind"])
    return out


def to_summary(strategy: dict[str, Any]) -> dict[str, Any]:
    """JSON-friendly extract for results.json."""
    out: dict[str, Any] = {k: v for k, v in strategy.items() if k != "variants"}
    out["variants"] = {}
    for name, segs in strategy["variants"].items():
        out["variants"][name] = {}
        for seg, d in segs.items():
            swap = {k: v for k, v in d["swap"].items() if k != "table"}
            out["variants"][name][seg] = {
                "n": d["n"],
                "bad_rate": d["bad_rate"],
                "cutoffs": d["cutoffs"].to_dict(orient="records"),
                "profit": d["profit"]["table"].to_dict(orient="records") if d["profit"] else None,
                "constrained": d["constrained"]["table"].to_dict(orient="records"),
                "swap_set": {**swap, "cells": d["swap"]["table"].to_dict(orient="records")},
            }
    return out


def write_artifacts(result: RunResult, out_dir: Path) -> None:
    st = result.strategy
    if not st:
        return
    stacks: dict[str, list[pd.DataFrame]] = {"score_bands": [], "cutoffs": [], "curve": [], "swap_set": [], "swap_summary": [], "profit": [], "constrained": []}
    for name, segs in st["variants"].items():
        for seg, d in segs.items():
            for key, table in (("score_bands", d["bands"]), ("cutoffs", d["cutoffs"]), ("curve", d["curve"]), ("swap_set", d["swap"]["table"]), ("swap_summary", d["swap_summary"])):
                stacks[key].append(table.assign(variant=name, segment=seg))
            stacks["constrained"].append(d["constrained"]["table"].assign(variant=name, segment=seg))
            if d["profit"]:
                stacks["profit"].append(d["profit"]["table"].assign(variant=name, segment=seg))
    for key, parts in stacks.items():
        if parts:
            table = pd.concat(parts, ignore_index=True)
            lead = ["variant", "segment"]
            table[lead + [c for c in table.columns if c not in lead]].to_csv(out_dir / f"strategy_{key}.csv", index=False)


# --------------------------------------------------------------------------- report section 5
def _swap_matrix(sw: dict[str, Any], cash: bool) -> pd.DataFrame:
    by = sw["table"].set_index("cell")

    def cell(key: str) -> str:
        n, br = int(by.loc[key, "n"]), by.loc[key, "bad_rate"]
        text = f"{n:,} 笔 · bad rate {br:.2%}" if n else "0 笔"
        if cash and n:
            text += f" · 净现金/笔 {by.loc[key, 'net_cash_per_loan']:,.0f}"
        return text

    def total(keys: list[str]) -> str:
        n = int(by.loc[keys, "n"].sum())
        bad = int(by.loc[keys, "bad"].sum())
        text = f"{n:,} 笔 · bad rate {bad / n:.2%}" if n else "0 笔"
        if cash and n:
            text += f" · 净现金/笔 {by.loc[keys, 'net_cash_total'].sum() / n:,.0f}"
        return text

    return pd.DataFrame(
        [
            {"模型 \\ 基准": "模型批（score ≥ cut-off）", "基准批": cell("both_approve"), "基准拒": cell("swap_in") + "  ← swap-in", "合计": total(["both_approve", "swap_in"])},
            {"模型 \\ 基准": "模型拒", "基准批": cell("swap_out") + "  ← swap-out", "基准拒": cell("both_reject"), "合计": total(["swap_out", "both_reject"])},
            {"模型 \\ 基准": "合计", "基准批": total(["both_approve", "swap_out"]), "基准拒": total(["swap_in", "both_reject"]), "合计": total(list(by.index))},
        ]
    )


def _swap_interpretation(sw: dict[str, Any], baseline_label: str) -> str:
    diff_pp = (sw["model_bad_rate"] - sw["baseline_bad_rate"]) * 100
    better = sw["swap_in_bad_rate"] < sw["swap_out_bad_rate"]
    text = (
        f"swap-in（模型批、基准拒）{sw['swap_in_n']:,} 笔，bad rate {sw['swap_in_bad_rate']:.2%}；"
        f"swap-out（模型拒、基准批）{sw['swap_out_n']:,} 笔，bad rate {sw['swap_out_bad_rate']:.2%}。"
        f"两格人数相同，模型{'换进了更好的客户' if better else '换进的客户反而更差'}；"
        f"同通过率下模型通过客群 bad rate {sw['model_bad_rate']:.2%}，{baseline_label} {sw['baseline_bad_rate']:.2%}（{diff_pp:+.2f} pp）。"
    )
    if "model_net_cash" in sw:
        text += f" 通过客群净现金：模型 {sw['model_net_cash']:,.0f}，基准 {sw['baseline_net_cash']:,.0f}。"
    return text


def build_section(result: RunResult, out_dir: Path, embed: bool) -> dict[str, Any]:
    from scorecard import figures as fig
    from scorecard.report import SEGMENT_LABELS, _variant_prefix, figure_block, kv, p, section, table_block

    st = result.strategy
    assert st is not None
    cfg = result.config.strategy
    has_cash = st["has_net_cash"]
    baseline = st["baseline"]
    baseline_label = "基准（平台评级）" if baseline["kind"] == "platform_grade" else "基准（随机）"
    baseline_text = (
        f"平台评级 {baseline['column']} 从最好一档往下批，批到与模型 cut-off 相同的通过人数（边际一档内按固定种子随机排序）"
        if baseline["kind"] == "platform_grade"
        else "数据没有平台评级：用随机策略（同通过率，固定种子）做基准"
    )
    money_fmt = {"net_cash_total": "{:,.0f}", "net_cash_per_loan": "{:,.0f}", "marginal_net_cash_per_loan": "{:,.0f}", "model_net_cash": "{:,.0f}", "baseline_net_cash": "{:,.0f}"}
    blocks: list[dict[str, Any]] = []
    profit_text = (st["net_cash_definition"] or "net_cash 由 adapter 提供（实际回款减放款本金）") + "。这是用贷后实际结果做的策略评估，不是预测；净现金为名义金额，未折现、未扣资金成本与运营成本" if has_cash else NO_NET_CASH
    blocks.append(
        kv(
            [
                ("评分方向与通过规则", "分数越高越安全；cut-off 规则为 score ≥ cut-off 通过。分数为整数，所以每个候选通过率取实际通过率最接近的 cut-off，并同时报告实际通过率"),
                ("评估样本", " / ".join(SEGMENT_LABELS[s] for s in st["segments"]) + "（train 不参与策略评估）"),
                ("候选通过率", " / ".join(f"{r:.0%}" for r in st["approval_rates"])),
                ("利润口径", profit_text),
                ("swap set 基准", baseline_text),
                ("约束条件", f"坏账率上限 {cfg.max_bad_rate:.0%}（5.3 的主要结论）；目标通过率 {cfg.target_approval_rate:.0%}（5.3 的第二行，swap set 也按这一档展示）"),
            ],
            title="5.0 口径",
        )
    )
    seg_label = {seg: SEGMENT_LABELS[seg] for seg in st["segments"]}
    for v in result.variants:
        prefix = _variant_prefix(result, v)
        segs = st["variants"][v.name]
        band_cols = ["band", "interval", "n", "share", "bad", "bad_rate", "cum_approval_rate", "cum_bad_rate"] + (["net_cash_per_loan"] if has_cash else [])
        for seg, d in segs.items():
            blocks.append(
                table_block(
                    d["bands"][band_cols],
                    title=f"{prefix}5.1 分数段表（{seg_label[seg]}，等频 {cfg.score_bands} 段，分数从高到低）",
                    rename={"band": "分段", "interval": "分数区间", "n": "人数", "share": "占比", "bad": "bad 数", "bad_rate": "bad rate", "cum_approval_rate": "累计通过率", "cum_bad_rate": "累计 bad rate", "net_cash_per_loan": "净现金/笔"},
                    formats=money_fmt,
                    collapsed=seg != TEST,
                    note="累计通过率 / 累计 bad rate = 以该段下边界为 cut-off 时的通过率与通过客群 bad rate。按分数分位数切段，整数分数有并列，各段人数近似相等。" if seg == TEST else None,
                )
            )
        path = fig.plot_approval_curve(
            {seg_label[seg]: d["curve"] for seg, d in segs.items()},
            {seg_label[seg]: d["cutoffs"] for seg, d in segs.items()},
            out_dir / "figures" / f"08_approval_curve_{v.name}.png",
            "Approval rate vs bad rate of approved loans (dots = candidate cut-offs)",
        )
        blocks.append(figure_block(path, out_dir, f"{prefix}图 5.1 通过率–坏账率曲线（点 = 候选 cut-off）", embed))
        cut_cols = ["target_approval_rate", "cutoff_score", "approval_rate", "n_approved", "bad_rate_approved", "bad_rate_rejected", "marginal_n", "marginal_bad_rate"] + (["net_cash_total", "net_cash_per_loan", "marginal_net_cash_per_loan"] if has_cash else [])
        for seg, d in segs.items():
            blocks.append(
                table_block(
                    d["cutoffs"][cut_cols],
                    title=f"{prefix}5.2 候选 cut-off（{seg_label[seg]}；样本 bad rate {d['bad_rate']:.2%}）",
                    rename={"target_approval_rate": "目标通过率", "cutoff_score": "cut-off", "approval_rate": "实际通过率", "n_approved": "通过人数", "bad_rate_approved": "通过客群 bad rate", "bad_rate_rejected": "拒绝客群 bad rate", "marginal_n": "边际新增人数", "marginal_bad_rate": "边际 bad rate", "net_cash_total": "总净现金", "net_cash_per_loan": "净现金/笔", "marginal_net_cash_per_loan": "边际净现金/笔"},
                    formats=money_fmt,
                    note="边际 = 比上一档宽松的 cut-off 多放进来的那一批客户；边际 bad rate 和边际净现金/笔决定了再放松一档是否划算。" if seg == TEST else None,
                )
            )
        con = pd.concat([d["constrained"]["table"].assign(segment=seg_label[seg]) for seg, d in segs.items()], ignore_index=True)
        con_cols = ["segment", "criterion", "cutoff_score", "approval_rate", "n_approved", "bad_rate_approved"] + (["net_cash_total", "net_cash_per_loan"] if has_cash else [])
        blocks.append(
            table_block(
                con[con_cols],
                title=f"{prefix}5.3 约束下的最优 cut-off（主要结论）",
                rename={"segment": "样本", "criterion": "准则", "cutoff_score": "cut-off", "approval_rate": "实际通过率", "n_approved": "通过人数", "bad_rate_approved": "通过客群 bad rate", "net_cash_total": "总净现金", "net_cash_per_loan": "净现金/笔"},
                formats=money_fmt,
                note=f"第一行：通过客群 bad rate ≤ {cfg.max_bad_rate:.0%} 的前提下通过率最高的 cut-off（空白 = 没有任何 cut-off 能满足）；第二行：通过率 {cfg.target_approval_rate:.0%} 时的坏账率与净现金。",
            )
        )
        if has_cash:
            seg0 = OOT if OOT in segs else next(iter(segs))
            bt = segs[seg0]["profit"]["best_total"]
            if bt["approval_rate"] >= 0.95:
                blocks.append(p(f"{seg_label[seg0]} 上无约束的总净现金在通过率 {bt['approval_rate']:.1%}（cut-off {_fmt_score(bt['cutoff_score'])}，接近全部通过）处最大：各分数段的每笔净现金接近持平，说明平台已对风险定价（risk-based pricing），低分客户的高利率覆盖了更高的损失。因此评分卡在这里的价值不是靠拒绝提高利润，而是风险约束下的准入（坏账率上限）与分层定价；本报告以 5.3 的约束下 cut-off 为主要结论，下面的利润曲线只作参照。"))
            else:
                blocks.append(p(f"{seg_label[seg0]} 上总净现金在通过率 {bt['approval_rate']:.1%}（cut-off {_fmt_score(bt['cutoff_score'])}）处最大，低于全部通过：低分段的利息收入不足以覆盖损失，利润与坏账率约束指向同一方向。本报告以 5.3 的约束下 cut-off 为主要结论。"))
            path = fig.plot_profit_curve(
                {seg_label[seg]: d["curve"] for seg, d in segs.items()},
                {seg_label[seg]: d["profit"] for seg, d in segs.items()},
                out_dir / "figures" / f"09_profit_curve_{v.name}.png",
                "Net cash of approved loans vs approval rate",
            )
            blocks.append(figure_block(path, out_dir, f"{prefix}图 5.2 利润曲线（左：总净现金；右：每笔净现金）", embed))
            rows = pd.concat([d["profit"]["table"].assign(segment=seg_label[seg]) for seg, d in segs.items()], ignore_index=True)
            rows = rows[["segment", "criterion", "cutoff_score", "approval_rate", "n_approved", "bad_rate_approved", "net_cash_total", "net_cash_per_loan"]]
            blocks.append(
                table_block(
                    rows,
                    title=f"{prefix}5.4 利润最大化 cut-off（无约束参照：总净现金 vs 每笔净现金）",
                    rename={"segment": "样本", "criterion": "准则", "cutoff_score": "cut-off", "approval_rate": "实际通过率", "n_approved": "通过人数", "bad_rate_approved": "通过客群 bad rate", "net_cash_total": "总净现金", "net_cash_per_loan": "净现金/笔"},
                    formats=money_fmt,
                    note=f"净现金来自实际回款（见 5.0 口径）。每笔净现金最大的 cut-off 只在通过率 ≥ {cfg.profit_min_approval_rate:.0%} 的范围内搜索，避免只剩几十个高分客户时的噪声。总净现金最大的 cut-off 通常比坏账率最低的 cut-off 宽松得多：多放进来的一档客户只要利息收入高于损失，总额就继续上升（风险定价越充分，越接近全部通过）。",
                )
            )
        else:
            blocks.append(kv([("利润曲线", NO_NET_CASH)], title=f"{prefix}5.4 利润曲线"))
        for seg, d in segs.items():
            sw = d["swap"]
            blocks.append(
                table_block(
                    _swap_matrix(sw, has_cash),
                    title=f"{prefix}5.5 swap set（{seg_label[seg]}；cut-off {_fmt_score(sw['cutoff_score'])}，通过率 {sw['approval_rate']:.1%}，目标 {sw['target_approval_rate']:.0%}）",
                    note=_swap_interpretation(sw, baseline_label),
                )
            )
        summary = pd.concat([d["swap_summary"].assign(segment=seg_label[seg]) for seg, d in segs.items()], ignore_index=True)
        sum_cols = ["segment", "target_approval_rate", "cutoff_score", "approval_rate", "model_bad_rate", "baseline_bad_rate", "swap_in_n", "swap_in_bad_rate", "swap_out_n", "swap_out_bad_rate"] + (["model_net_cash", "baseline_net_cash"] if has_cash else [])
        blocks.append(
            table_block(
                summary[sum_cols],
                title=f"{prefix}各候选通过率下的 swap set 汇总",
                rename={"segment": "样本", "target_approval_rate": "目标通过率", "cutoff_score": "cut-off", "approval_rate": "实际通过率", "model_bad_rate": "模型通过客群 bad rate", "baseline_bad_rate": "基准通过客群 bad rate", "swap_in_n": "swap-in 人数", "swap_in_bad_rate": "swap-in bad rate", "swap_out_n": "swap-out 人数", "swap_out_bad_rate": "swap-out bad rate", "model_net_cash": "模型通过客群净现金", "baseline_net_cash": "基准通过客群净现金"},
                formats=money_fmt,
                collapsed=True,
            )
        )
    if len(result.variants) > 1:
        a, b = result.variants[0], result.variants[1]
        la, lb = ("含" if a.use_platform_rating else "不含") + "平台评级", ("含" if b.use_platform_rating else "不含") + "平台评级"
        rows = []
        for seg in st["segments"]:
            ca, cb = st["variants"][a.name][seg]["cutoffs"], st["variants"][b.name][seg]["cutoffs"]
            for ra, rb in zip(ca.itertuples(index=False), cb.itertuples(index=False)):
                rows.append({"segment": seg_label[seg], "target_approval_rate": ra.target_approval_rate, "cutoff_a": ra.cutoff_score, "bad_rate_a": ra.bad_rate_approved, "cutoff_b": rb.cutoff_score, "bad_rate_b": rb.bad_rate_approved, "diff_pp": (rb.bad_rate_approved - ra.bad_rate_approved) * 100})
        blocks.append(
            table_block(
                pd.DataFrame(rows),
                title=f"5.6 两套模型对比：同通过率下的通过客群 bad rate（{la} vs {lb}）",
                rename={"segment": "样本", "target_approval_rate": "目标通过率", "cutoff_a": f"cut-off（{la}）", "bad_rate_a": f"bad rate（{la}）", "cutoff_b": f"cut-off（{lb}）", "bad_rate_b": f"bad rate（{lb}）", "diff_pp": "差（pp）"},
                formats={"cutoff_a": "{:.0f}", "cutoff_b": "{:.0f}", "bad_rate_a": "{:.2%}", "bad_rate_b": "{:.2%}", "diff_pp": "{:+.2f}"},
                note="两套模型的 cut-off 不可比（分数刻度相同但变量不同），应比较同通过率下的 bad rate。",
            )
        )
    if st["n_net_cash_missing"]:
        blocks.append(p(f"net_cash 缺失 {st['n_net_cash_missing']:,} 行按 0 处理。"))
    intro = "在 test 与 OOT 上评估评分卡的业务用法：分数段表、通过率–坏账率曲线、候选 cut-off、用实际回款算的利润曲线，以及与平台基准的 swap set。"
    return section(5, "策略分析", intro, blocks)
