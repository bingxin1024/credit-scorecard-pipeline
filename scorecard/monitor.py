"""Monitoring layer (PLAN.md §6.3): score PSI, feature CSI, vintage curves.

* PSI = sum over bands of (actual% - expected%) * ln(actual% / expected%), expected = train.
  Score bands are the train deciles (10 equal-frequency bands, right-closed); feature CSI uses the
  fitted scorecard bins (incl. the missing bin), so it is the PSI of the bin distribution.
* Thresholds (config `monitor.psi_warn` / `psi_alert`, default 0.10 / 0.25): below warn = stable,
  between = watch, above alert = act.
* Vintage: cumulative default rate by issue quarter against months on book. Months on book of a
  default is `event_date - issue_date` in months, where `event_date` is the adapter's approximation
  of the default month; the adapter's note on what that column is appears in the report.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import TYPE_CHECKING, Any

import numpy as np
import pandas as pd

from scorecard.adapters.base import EVENT_DATE, ISSUE_DATE, TARGET
from scorecard.split import OOT, TEST, TRAIN

if TYPE_CHECKING:
    from scorecard.binning import Binner
    from scorecard.pipeline import RunResult

log = logging.getLogger(__name__)

IMPLEMENTED = True
EPS = 1e-4
STATUS_LABELS = {"stable": "🟢 稳定", "warn": "🟡 关注", "alert": "🔴 警戒"}
VINTAGE_TABLE_MOBS = (3, 6, 9, 12, 18, 24, 30, 36, 48, 60)


# --------------------------------------------------------------------------- PSI arithmetic
def psi_contributions(expected: np.ndarray, actual: np.ndarray, eps: float = EPS) -> np.ndarray:
    """Per-band PSI terms; shares of 0 are floored at `eps` (the usual convention)."""
    e = np.clip(np.asarray(expected, dtype=float), eps, None)
    a = np.clip(np.asarray(actual, dtype=float), eps, None)
    return (a - e) * np.log(a / e)


def psi(expected: np.ndarray, actual: np.ndarray, eps: float = EPS) -> float:
    return float(psi_contributions(expected, actual, eps).sum())


def status(value: float, warn: float, alert: float) -> str:
    if np.isnan(value):
        return "stable"
    if value >= alert:
        return "alert"
    if value >= warn:
        return "warn"
    return "stable"


def score_band_edges(train_scores, n_bins: int = 10) -> np.ndarray:
    """Right-closed decile edges of the train score (unique, so ties never create empty bands)."""
    s = np.asarray(train_scores, dtype=float)
    edges = np.unique(np.quantile(s, np.linspace(0, 1, n_bins + 1)[1:-1]))
    return edges[edges < s.max()]


def band_labels(edges: np.ndarray) -> list[str]:
    def f(v: float) -> str:
        return f"{int(v)}" if float(v).is_integer() else f"{v:.4g}"

    if len(edges) == 0:
        return ["all values"]
    return [f"<= {f(edges[0])}"] + [f"({f(a)}, {f(b)}]" for a, b in zip(edges[:-1], edges[1:])] + [f"> {f(edges[-1])}"]


def shares(ids: np.ndarray, n_bins: int) -> np.ndarray:
    ids = np.asarray(ids, dtype=int)
    return np.bincount(ids, minlength=n_bins) / max(len(ids), 1)


def score_psi(train_scores, others: dict[str, np.ndarray], n_bins: int = 10) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Score PSI of each sample in `others` against train. Returns (summary, per-band detail)."""
    train = np.asarray(train_scores, dtype=float)
    edges = score_band_edges(train, n_bins)
    n_b = len(edges) + 1
    labels = band_labels(edges)
    expected = shares(np.searchsorted(edges, train, side="left"), n_b)
    summary, detail = [], []
    for seg, values in others.items():
        values = np.asarray(values, dtype=float)
        actual = shares(np.searchsorted(edges, values, side="left"), n_b)
        contrib = psi_contributions(expected, actual)
        summary.append({"segment": seg, "n_expected": len(train), "n_actual": len(values), "psi": float(contrib.sum())})
        for b in range(n_b):
            detail.append({"segment": seg, "band": b + 1, "interval": labels[b], "expected_pct": expected[b], "actual_pct": actual[b], "psi_contribution": contrib[b]})
    return pd.DataFrame(summary), pd.DataFrame(detail)


def feature_csi(binner: Binner, features: list[str], frame: pd.DataFrame, labels: pd.Series,
                segments: tuple[str, ...] = (TEST, OOT)) -> tuple[pd.DataFrame, pd.DataFrame]:
    """CSI (PSI of the fitted-bin distribution) of every scorecard feature, train -> each segment."""
    train_mask = (labels == TRAIN).to_numpy()
    rows, detail = [], []
    for name in features:
        spec = binner.bins_[name]
        n_b = spec.n_bins
        bin_names = spec.labels()
        expected = shares(spec.bin_ids(frame.loc[train_mask, name]), n_b)
        row: dict[str, Any] = {"feature": name}
        for seg in segments:
            mask = (labels == seg).to_numpy()
            if not mask.any():
                continue
            actual = shares(spec.bin_ids(frame.loc[mask, name]), n_b)
            contrib = psi_contributions(expected, actual)
            row[f"csi_{seg}"] = float(contrib.sum())
            if seg == OOT or "shift_bin" not in row:
                j = int(np.argmax(np.abs(actual - expected)))
                row["shift_bin"] = bin_names[j]
                row["train_share"] = float(expected[j])
                row["shift_share"] = float(actual[j])
            for b in range(n_b):
                if expected[b] == 0 and actual[b] == 0:
                    continue  # unused missing bin
                detail.append({"feature": name, "segment": seg, "bin": bin_names[b], "expected_pct": expected[b], "actual_pct": actual[b], "psi_contribution": contrib[b]})
        rows.append(row)
    return pd.DataFrame(rows), pd.DataFrame(detail)


# --------------------------------------------------------------------------- vintage
def vintage_table(frame: pd.DataFrame, max_mob: int = 60, cutoff_month: str | None = None) -> dict[str, Any] | None:
    if ISSUE_DATE not in frame.columns or EVENT_DATE not in frame.columns:
        return None
    issue = pd.to_datetime(frame[ISSUE_DATE])
    event = pd.to_datetime(frame[EVENT_DATE])
    if issue.isna().all() or event.isna().all():
        return None
    y = frame[TARGET].to_numpy(dtype=int)
    bad = y == 1
    mob = ((event.dt.year - issue.dt.year) * 12 + (event.dt.month - issue.dt.month)).astype("float64")
    missing_event = bad & mob.isna().to_numpy()
    mob_arr = mob.fillna(0).clip(lower=0, upper=max_mob).to_numpy(dtype=int)
    cohort = issue.dt.to_period("Q").astype(str).to_numpy()
    # Observation horizon: the dataset's cut-off month when the adapter knows it, otherwise the
    # latest issue month or default event month (good loans' event dates are pay-off dates).
    horizon = max(issue.max(), event[bad].max() if bad.any() else issue.max()).to_period("M")
    if cutoff_month:
        horizon = max(horizon, pd.Period(cutoff_month, freq="M"))
    rows = []
    for name in sorted(set(cohort)):
        idx = np.flatnonzero(cohort == name)
        n = len(idx)
        last_issue = issue.iloc[idx].max().to_period("M")
        observable = (horizon.year - last_issue.year) * 12 + (horizon.month - last_issue.month)
        counts = np.bincount(mob_arr[idx][bad[idx]], minlength=max_mob + 1)
        cum = counts.cumsum() / n
        for m in range(max_mob + 1):
            rows.append({"cohort": name, "mob": m, "n": n, "cum_default_rate": float(cum[m]) if m <= observable else np.nan})
    long = pd.DataFrame(rows)
    wide = long.pivot(index="cohort", columns="mob", values="cum_default_rate").sort_index()
    return {
        "long": long,
        "wide": wide,
        "n_cohorts": int(wide.shape[0]),
        "max_mob": int(max_mob),
        "horizon": str(horizon),
        "n_bad_missing_event": int(missing_event.sum()),
        "n_bad_after_max_mob": int((mob[bad] > max_mob).sum()),
    }


# --------------------------------------------------------------------------- entry point
def analyse(result: RunResult) -> dict[str, Any]:
    cfg = result.config.monitor
    labels = result.labels
    out: dict[str, Any] = {
        "thresholds": {"warn": float(cfg.psi_warn), "alert": float(cfg.psi_alert)},
        "psi_bins": int(cfg.psi_bins),
        "variants": {},
        "vintage": None,
        "vintage_skipped": None,
    }
    train_mask = (labels == TRAIN).to_numpy()
    for v in result.variants:
        train_scores = v.scores.loc[train_mask, "score"].to_numpy(dtype=float)
        others = {seg: v.scores.loc[(labels == seg).to_numpy(), "score"].to_numpy(dtype=float) for seg in (TEST, OOT) if (labels == seg).any()}
        psi_summary, psi_detail = score_psi(train_scores, others, cfg.psi_bins)
        psi_summary["status"] = psi_summary["psi"].map(lambda x: status(x, cfg.psi_warn, cfg.psi_alert))
        csi, csi_detail = feature_csi(v.binner, v.selected, result.frame, labels)
        key = "csi_oot" if "csi_oot" in csi.columns else "csi_test"
        csi["status"] = csi[key].map(lambda x: status(x, cfg.psi_warn, cfg.psi_alert))
        csi = csi.sort_values(key, ascending=False).reset_index(drop=True)
        out["variants"][v.name] = {
            "score_psi": psi_summary,
            "score_psi_detail": psi_detail,
            "csi": csi,
            "csi_detail": csi_detail,
            "csi_key": key,
        }
        log.info("monitor %s: score PSI %s; CSI alerts %s", v.name, {r.segment: round(r.psi, 4) for r in psi_summary.itertuples()}, list(csi.loc[csi["status"] == "alert", "feature"]))
    vintage = vintage_table(result.frame, cfg.vintage_max_mob, result.meta.notes.get("data_cutoff_month"))
    if vintage is None:
        out["vintage_skipped"] = "数据不含 issue_date / event_date，无法绘制 vintage 曲线"
    else:
        out["vintage"] = vintage
    return out


def to_summary(monitor: dict[str, Any]) -> dict[str, Any]:
    out: dict[str, Any] = {"thresholds": monitor["thresholds"], "psi_bins": monitor["psi_bins"], "variants": {}}
    for name, d in monitor["variants"].items():
        out["variants"][name] = {"score_psi": d["score_psi"].to_dict(orient="records"), "csi": d["csi"].to_dict(orient="records")}
    if monitor.get("vintage"):
        vt = monitor["vintage"]
        out["vintage"] = {k: v for k, v in vt.items() if k not in ("long", "wide")}
    return out


def write_artifacts(result: RunResult, out_dir: Path) -> None:
    mon = result.monitor
    if not mon:
        return
    for key, fname in (("score_psi", "monitor_score_psi"), ("score_psi_detail", "monitor_score_psi_bands"), ("csi", "monitor_csi"), ("csi_detail", "monitor_csi_bins")):
        parts = [d[key].assign(variant=name) for name, d in mon["variants"].items()]
        if parts:
            table = pd.concat(parts, ignore_index=True)
            table[["variant"] + [c for c in table.columns if c != "variant"]].to_csv(out_dir / f"{fname}.csv", index=False)
    if mon.get("vintage"):
        mon["vintage"]["long"].to_csv(out_dir / "monitor_vintage.csv", index=False)


# --------------------------------------------------------------------------- report section 6
def build_section(result: RunResult, out_dir: Path, embed: bool) -> dict[str, Any]:
    from scorecard import figures as fig
    from scorecard.report import (
        SEGMENT_LABELS,
        _variant_prefix,
        bullet,
        figure_block,
        kv,
        section,
        table_block,
    )

    mon = result.monitor
    assert mon is not None
    warn, alert = mon["thresholds"]["warn"], mon["thresholds"]["alert"]
    blocks: list[dict[str, Any]] = []
    blocks.append(
        kv(
            [
                ("PSI 公式", "PSI = Σ (actual% − expected%) × ln(actual% / expected%)，expected = train；占比为 0 的段按 0.01% 处理"),
                ("score PSI 分段", f"train 分数的 {mon['psi_bins']} 等频段（右闭区间），同一套边界套到 test / OOT"),
                ("CSI", "每个入模特征按评分卡的分箱（含缺失箱）算分布的 PSI，train → test 与 train → OOT"),
                ("阈值", f"{STATUS_LABELS['stable']} < {warn:.2f} ≤ {STATUS_LABELS['warn']} < {alert:.2f} ≤ {STATUS_LABELS['alert']}（行业惯例：< 0.10 不动，0.10–0.25 观察，> 0.25 需处理）"),
            ],
            title="6.0 口径",
        )
    )
    for v in result.variants:
        prefix = _variant_prefix(result, v)
        d = mon["variants"][v.name]
        s = d["score_psi"].copy()
        s["comparison"] = "train → " + s["segment"].map(SEGMENT_LABELS)
        s["status"] = s["status"].map(STATUS_LABELS)
        blocks.append(
            table_block(
                s[["comparison", "n_expected", "n_actual", "psi", "status"]],
                title=f"{prefix}6.1 score PSI",
                rename={"comparison": "对比", "n_expected": "train 行数", "n_actual": "对比样本行数", "psi": "PSI", "status": "判定"},
            )
        )
        detail = d["score_psi_detail"]
        wide = detail.pivot(index=["band", "interval"], columns="segment", values="actual_pct").reset_index()
        exp = detail.drop_duplicates("band").set_index("band")["expected_pct"]
        wide.insert(2, "train", wide["band"].map(exp))
        seg_cols = [c for c in (TEST, OOT) if c in wide.columns]
        wide = wide[["band", "interval", "train"] + seg_cols]
        path = fig.plot_psi_bands(wide, seg_cols, out_dir / "figures" / f"10_score_psi_{v.name}.png", "Score distribution by train-decile band")
        blocks.append(figure_block(path, out_dir, f"{prefix}图 6.1 分数分布按 train 等频段（train vs test vs OOT）", embed))
        show = wide.rename(columns={c: f"{SEGMENT_LABELS[c]}_pct" for c in seg_cols}).rename(columns={"train": "train_pct"})
        contrib = detail.pivot(index="band", columns="segment", values="psi_contribution")
        for c in seg_cols:
            show[f"{SEGMENT_LABELS[c]}_contribution"] = show["band"].map(contrib[c])
        blocks.append(
            table_block(
                show,
                title=f"{prefix}score PSI 分段明细",
                rename={"band": "段", "interval": "分数区间", "train_pct": "train 占比", **{f"{SEGMENT_LABELS[c]}_pct": f"{SEGMENT_LABELS[c]} 占比" for c in seg_cols}, **{f"{SEGMENT_LABELS[c]}_contribution": f"PSI 贡献（{SEGMENT_LABELS[c]}）" for c in seg_cols}},
                formats={**{f"{SEGMENT_LABELS[c]}_pct": "{:.2%}" for c in seg_cols}, "train_pct": "{:.2%}", **{f"{SEGMENT_LABELS[c]}_contribution": "{:.4f}" for c in seg_cols}},
                collapsed=True,
            )
        )
        csi = d["csi"].copy()
        csi["status"] = csi["status"].map(STATUS_LABELS)
        csi_cols = ["feature"] + [c for c in ("csi_test", "csi_oot") if c in csi.columns] + ["status", "shift_bin", "train_share", "shift_share"]
        shift_label = "OOT 占比" if d["csi_key"] == "csi_oot" else "test 占比"
        blocks.append(
            table_block(
                csi[csi_cols],
                title=f"{prefix}6.2 入模特征 CSI（判定按 train → {'OOT' if d['csi_key'] == 'csi_oot' else 'test'}）",
                rename={"feature": "特征", "csi_test": "CSI train→test", "csi_oot": "CSI train→OOT", "status": "判定", "shift_bin": "偏移最大的箱", "train_share": "train 占比", "shift_share": shift_label},
                formats={"csi_test": "{:.4f}", "csi_oot": "{:.4f}", "train_share": "{:.2%}", "shift_share": "{:.2%}"},
                note="CSI 高说明该特征的客群分布变了，不一定意味着模型失效：先看 score PSI 是否稳定，再看该特征的分箱是否仍合理、含义是否变化（例如某个征信字段从某年开始才有值）。",
            )
        )
        path = fig.plot_csi_bars(d["csi"], d["csi_key"], out_dir / "figures" / f"11_csi_{v.name}.png", f"Feature CSI, train -> {'OOT' if d['csi_key'] == 'csi_oot' else 'test'}", warn, alert)
        blocks.append(figure_block(path, out_dir, f"{prefix}图 6.2 入模特征 CSI（虚线 = {warn:.2f} / {alert:.2f}）", embed))
        cd = d["csi_detail"]
        cd = cd[cd["segment"] == (OOT if d["csi_key"] == "csi_oot" else TEST)]
        blocks.append(
            table_block(
                cd[["feature", "bin", "expected_pct", "actual_pct", "psi_contribution"]],
                title=f"{prefix}CSI 分箱明细（train → {'OOT' if d['csi_key'] == 'csi_oot' else 'test'}）",
                rename={"feature": "特征", "bin": "分箱", "expected_pct": "train 占比", "actual_pct": "对比样本占比", "psi_contribution": "PSI 贡献"},
                collapsed=True,
            )
        )
    if mon.get("vintage"):
        vt = mon["vintage"]
        path = fig.plot_vintage(vt["wide"], out_dir / "figures" / "12_vintage.png", "Vintage curves: cumulative default rate by issue quarter")
        blocks.append(figure_block(path, out_dir, "图 6.3 vintage 曲线（按 issue 季度的累计违约率 vs 账龄）", embed))
        mobs = [m for m in VINTAGE_TABLE_MOBS if m <= vt["max_mob"]]
        wide = vt["wide"][[m for m in mobs if m in vt["wide"].columns]].copy()
        wide.columns = [f"MOB {m}" for m in wide.columns]
        wide.insert(0, "n", vt["long"].drop_duplicates("cohort").set_index("cohort")["n"])
        wide = wide.reset_index()
        blocks.append(
            table_block(
                wide,
                title="6.3 vintage 表：累计违约率按 issue 季度 × 账龄（月）",
                rename={"cohort": "issue 季度", "n": "贷款数"},
                formats={c: "{:.2%}" for c in wide.columns if c.startswith("MOB")},
                collapsed=True,
                note="空白 = 该季度到数据截止时账龄还没到。",
            )
        )
        notes = [
            result.meta.notes.get("event_date_note", "账龄 = event_date − issue_date（月），event_date 为 adapter 提供的违约时点近似。"),
            f"数据截止月 {vt['horizon']}；账龄超过 {vt['max_mob']} 个月的违约（{vt['n_bad_after_max_mob']:,} 笔）计入最后一个月。",
        ]
        if vt["n_bad_missing_event"]:
            notes.append(f"{vt['n_bad_missing_event']:,} 笔违约没有 event_date（从未还款），记为账龄 0。")
        blocks.append(bullet(notes, title="vintage 口径"))
    else:
        blocks.append(kv([("vintage 曲线", mon.get("vintage_skipped") or "跳过")], title="6.3 vintage"))
    intro = "分数与入模特征在 train → test / OOT 上的分布稳定性（PSI / CSI），以及按 issue 季度的 vintage 曲线。"
    return section(6, "稳定性", intro, blocks)
