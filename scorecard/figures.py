"""Matplotlib figures for the report. Labels are English (technical terms) to avoid CJK font issues."""

from __future__ import annotations

from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402
from matplotlib.ticker import PercentFormatter  # noqa: E402

from scorecard.binning import BinSpec  # noqa: E402

GOOD_COLOR, BAD_COLOR, ACCENT, NEUTRAL = "#2a78d6", "#eb6834", "#1baf7a", "#898781"
INK = {"primary": "#0b0b0b", "secondary": "#52514e", "muted": "#898781", "grid": "#e1e0d9", "axis": "#c3c2b7", "surface": "#ffffff"}


def apply_style() -> None:
    plt.rcParams.update(
        {
            "figure.facecolor": INK["surface"],
            "axes.facecolor": INK["surface"],
            "savefig.facecolor": INK["surface"],
            "font.family": "sans-serif",
            "font.sans-serif": ["Segoe UI", "Arial", "DejaVu Sans"],
            "font.size": 10,
            "axes.titlesize": 11,
            "axes.titleweight": "semibold",
            "axes.titlelocation": "left",
            "axes.labelcolor": INK["secondary"],
            "axes.edgecolor": INK["axis"],
            "axes.spines.top": False,
            "axes.spines.right": False,
            "axes.grid": True,
            "axes.axisbelow": True,
            "grid.color": INK["grid"],
            "grid.linewidth": 0.8,
            "xtick.color": INK["axis"],
            "ytick.color": INK["axis"],
            "xtick.labelcolor": INK["secondary"],
            "ytick.labelcolor": INK["secondary"],
            "lines.linewidth": 2,
            "legend.frameon": False,
        }
    )


def save(fig: plt.Figure, path: Path) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(path, dpi=140, bbox_inches="tight")
    plt.close(fig)
    return path


def plot_bad_rate_by_period(table: pd.DataFrame, path: Path, title: str, period_col: str = "period") -> Path:
    fig, ax = plt.subplots(figsize=(9, 3.8))
    x = np.arange(len(table))
    ax.bar(x, table["n"], color=INK["grid"], width=0.8, label="loans (count)")
    ax.set_ylabel("Loans")
    ax2 = ax.twinx()
    ax2.plot(x, table["bad_rate"], color=BAD_COLOR, marker="o", markersize=3, label="bad rate")
    ax2.yaxis.set_major_formatter(PercentFormatter(1.0, decimals=0))
    ax2.set_ylabel("Bad rate")
    ax2.grid(False)
    ax2.spines["right"].set_visible(True)
    ax.set_xticks(x)
    ax.set_xticklabels([str(p) for p in table[period_col]], rotation=60, ha="right", fontsize=8)
    ax.set_title(title)
    handles = ax.get_legend_handles_labels()[0] + ax2.get_legend_handles_labels()[0]
    labels = ax.get_legend_handles_labels()[1] + ax2.get_legend_handles_labels()[1]
    ax.legend(handles, labels, loc="upper left")
    return save(fig, path)


def plot_woe(spec: BinSpec, path: Path) -> Path:
    table = spec.table()
    fig, ax = plt.subplots(figsize=(7.5, 3.4))
    colors = [GOOD_COLOR if w >= 0 else BAD_COLOR for w in table["woe"]]
    x = np.arange(len(table))
    ax.bar(x, table["woe"], color=colors, width=0.7)
    for i, (w, share) in enumerate(zip(table["woe"], table["share"])):
        ax.annotate(f"{share:.0%}", (i, w), textcoords="offset points", xytext=(0, 4 if w >= 0 else -11), ha="center", fontsize=8, color=INK["muted"])
    ax.axhline(0, color=INK["axis"], linewidth=0.8)
    ax.set_xticks(x)
    ax.set_xticklabels(table["bin"], rotation=30, ha="right", fontsize=8)
    ax.set_ylabel("WOE = ln(good share / bad share)")
    ax.set_title(f"{spec.name}: WOE by bin (IV = {spec.iv:.3f}); labels = share of loans")
    return save(fig, path)


def plot_roc(curves: dict[str, pd.DataFrame], path: Path, title: str = "ROC curves") -> Path:
    fig, ax = plt.subplots(figsize=(5.2, 5))
    palette = [GOOD_COLOR, BAD_COLOR, ACCENT, "#8e44ad", "#f1c40f", "#34495e"]
    styles = ["-", "--", ":", "-."]
    for i, (name, curve) in enumerate(curves.items()):
        ax.plot(curve["fpr"], curve["tpr"], label=name, color=palette[i % len(palette)], linestyle=styles[(i // len(palette)) % len(styles)])
    ax.plot([0, 1], [0, 1], color=INK["axis"], linewidth=1, linestyle="--")
    ax.set_xlabel("False positive rate (goods flagged)")
    ax.set_ylabel("True positive rate (bads caught)")
    ax.set_title(title)
    ax.legend(loc="lower right", fontsize=8)
    return save(fig, path)


def plot_ks(y_true, y_score, path: Path, title: str = "KS curve (test)") -> Path:
    y_true = np.asarray(y_true)
    order = np.argsort(-np.asarray(y_score))
    y_sorted = y_true[order]
    n = len(y_sorted)
    cum_bad = np.cumsum(y_sorted) / max(y_sorted.sum(), 1)
    cum_good = np.cumsum(1 - y_sorted) / max((1 - y_sorted).sum(), 1)
    pct = np.arange(1, n + 1) / n
    ks_idx = int(np.argmax(cum_bad - cum_good))
    fig, ax = plt.subplots(figsize=(6.5, 4))
    ax.plot(pct, cum_bad, color=BAD_COLOR, label="cumulative bads")
    ax.plot(pct, cum_good, color=GOOD_COLOR, label="cumulative goods")
    ax.vlines(pct[ks_idx], cum_good[ks_idx], cum_bad[ks_idx], color=INK["primary"], linestyle="--", linewidth=1.2,
              label=f"KS = {cum_bad[ks_idx] - cum_good[ks_idx]:.3f} at {pct[ks_idx]:.0%} riskiest")
    ax.set_xlabel("Share of loans, ranked riskiest first")
    ax.set_ylabel("Cumulative share")
    ax.xaxis.set_major_formatter(PercentFormatter(1.0, decimals=0))
    ax.yaxis.set_major_formatter(PercentFormatter(1.0, decimals=0))
    ax.set_title(title)
    ax.legend(loc="lower right")
    return save(fig, path)


def plot_score_distribution(scores: np.ndarray, y_true: np.ndarray, path: Path, title: str) -> Path:
    scores = np.asarray(scores, dtype=float)
    y_true = np.asarray(y_true)
    lo, hi = np.floor(scores.min() / 10) * 10, np.ceil(scores.max() / 10) * 10 + 10
    bins = np.arange(lo, hi + 1, 10)
    fig, ax = plt.subplots(figsize=(8, 4))
    for value, label, color in [(0, "good (no default)", GOOD_COLOR), (1, "bad (default)", BAD_COLOR)]:
        s = scores[y_true == value]
        if len(s) == 0:
            continue
        ax.hist(s, bins=bins, weights=np.full(len(s), 1 / len(s)), histtype="step", linewidth=2, color=color,
                label=f"{label}: median {np.median(s):.0f}")
    ax.set_xlabel("Score (bins of 10 points; higher = lower risk)")
    ax.set_ylabel("Share of group")
    ax.yaxis.set_major_formatter(PercentFormatter(1.0, decimals=0))
    ax.set_title(title)
    ax.legend(loc="upper left")
    return save(fig, path)


def plot_iv_bars(iv_table: pd.DataFrame, path: Path, top: int = 30, min_iv: float = 0.02, leakage_iv: float = 0.5) -> Path:
    table = iv_table.head(top).iloc[::-1]
    fig, ax = plt.subplots(figsize=(8, max(3.5, 0.26 * len(table))))
    colors = [ACCENT if s else INK["axis"] for s in table.get("selected", [True] * len(table))]
    ax.barh(table["feature"], table["iv"], color=colors)
    ax.axvline(min_iv, color=INK["muted"], linestyle="--", linewidth=1, label=f"min IV {min_iv}")
    if table["iv"].max() > leakage_iv * 0.8:
        ax.axvline(leakage_iv, color=BAD_COLOR, linestyle="--", linewidth=1, label=f"leakage IV {leakage_iv}")
    ax.set_xlabel("Information Value (train)")
    ax.set_title(f"IV ranking, top {len(table)} (green = selected into the scorecard)")
    ax.legend(loc="lower right", fontsize=8)
    ax.tick_params(axis="y", labelsize=8)
    return save(fig, path)


# --------------------------------------------------------------------------- Phase 2: strategy
def plot_approval_curve(curves: dict[str, pd.DataFrame], cutoffs: dict[str, pd.DataFrame], path: Path, title: str) -> Path:
    fig, ax = plt.subplots(figsize=(7.5, 4.3))
    palette = [GOOD_COLOR, BAD_COLOR, ACCENT]
    for i, (label, curve) in enumerate(curves.items()):
        color = palette[i % len(palette)]
        ax.plot(curve["approval_rate"], curve["bad_rate_approved"], color=color, label=f"{label}: bad rate of approved loans")
        c = cutoffs.get(label)
        if c is not None and len(c):
            ax.scatter(c["approval_rate"], c["bad_rate_approved"], color=color, s=30, zorder=3)
            if i == 0:
                for row in c.itertuples(index=False):
                    ax.annotate(f"cut-off {int(row.cutoff_score)}", (row.approval_rate, row.bad_rate_approved), textcoords="offset points",
                                xytext=(6, -12), fontsize=8, color=INK["secondary"])
        ax.axhline(float(curve["bad_rate_approved"].iloc[-1]), color=color, linestyle=":", linewidth=1, alpha=0.7)
    ax.set_xlabel("Approval rate (share of loans with score >= cut-off)")
    ax.set_ylabel("Bad rate of approved loans")
    ax.xaxis.set_major_formatter(PercentFormatter(1.0, decimals=0))
    ax.yaxis.set_major_formatter(PercentFormatter(1.0, decimals=0))
    ax.set_xlim(0, 1)
    ax.set_title(title)
    ax.legend(loc="upper left", fontsize=8, title="dotted = approve everyone", title_fontsize=8)
    return save(fig, path)


def plot_profit_curve(curves: dict[str, pd.DataFrame], optima: dict[str, dict], path: Path, title: str) -> Path:
    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(11, 4.2))
    palette = [GOOD_COLOR, BAD_COLOR, ACCENT]
    for i, (label, curve) in enumerate(curves.items()):
        color = palette[i % len(palette)]
        ax1.plot(curve["approval_rate"], curve["net_cash_total"] / 1e6, color=color, label=label)
        ax2.plot(curve["approval_rate"], curve["net_cash_per_loan"], color=color, label=label)
        best = optima.get(label)
        if best:
            bt, bl = best["best_total"], best["best_per_loan"]
            ax1.scatter([bt["approval_rate"]], [bt["net_cash_total"] / 1e6], color=color, s=40, zorder=3)
            ax1.annotate(f"max: cut-off {int(bt['cutoff_score'])} @ {bt['approval_rate']:.0%}", (bt["approval_rate"], bt["net_cash_total"] / 1e6),
                         textcoords="offset points", xytext=(-6, 8 + 12 * i), fontsize=8, color=color, ha="right")
            ax2.scatter([bl["approval_rate"]], [bl["net_cash_per_loan"]], color=color, s=40, zorder=3)
            ax2.annotate(f"max: cut-off {int(bl['cutoff_score'])} @ {bl['approval_rate']:.0%}", (bl["approval_rate"], bl["net_cash_per_loan"]),
                         textcoords="offset points", xytext=(8, 10 - 24 * i), fontsize=8, color=color)
    for ax, ylabel in ((ax1, "Total net cash of approved loans (millions)"), (ax2, "Net cash per approved loan")):
        ax.set_xlabel("Approval rate")
        ax.set_ylabel(ylabel)
        ax.xaxis.set_major_formatter(PercentFormatter(1.0, decimals=0))
        ax.set_xlim(0, 1)
        ax.axhline(0, color=INK["axis"], linewidth=0.8)
        ax.legend(loc="lower right", fontsize=8)
    ax1.set_title(title)
    ax2.set_title("Per-loan view (searched at approval rate >= min)")
    return save(fig, path)


# --------------------------------------------------------------------------- Phase 2: monitoring
def plot_psi_bands(wide: pd.DataFrame, segments: list[str], path: Path, title: str) -> Path:
    labels = {"test": "test", "oot": "OOT"}
    series = [("train", "train", INK["axis"])] + [(seg, labels.get(seg, seg), [GOOD_COLOR, BAD_COLOR][i % 2]) for i, seg in enumerate(segments)]
    x = np.arange(len(wide))
    width = 0.8 / len(series)
    fig, ax = plt.subplots(figsize=(8.5, 3.8))
    for j, (col, label, color) in enumerate(series):
        ax.bar(x + (j - (len(series) - 1) / 2) * width, wide[col], width=width, color=color, label=label)
    ax.set_xticks(x)
    ax.set_xticklabels(wide["interval"], rotation=30, ha="right", fontsize=8)
    ax.set_ylabel("Share of loans")
    ax.yaxis.set_major_formatter(PercentFormatter(1.0, decimals=0))
    ax.set_xlabel("Score band (train deciles, low to high)")
    ax.set_title(title)
    ax.legend(loc="upper right", fontsize=8)
    return save(fig, path)


def plot_csi_bars(csi: pd.DataFrame, key: str, path: Path, title: str, warn: float, alert: float) -> Path:
    table = csi.sort_values(key).reset_index(drop=True)
    colors = [BAD_COLOR if v >= alert else ("#f0b429" if v >= warn else ACCENT) for v in table[key]]
    fig, ax = plt.subplots(figsize=(8, max(3.2, 0.3 * len(table) + 1)))
    ax.barh(table["feature"], table[key], color=colors)
    ax.axvline(warn, color=INK["muted"], linestyle="--", linewidth=1, label=f"warn {warn}")
    ax.axvline(alert, color=BAD_COLOR, linestyle="--", linewidth=1, label=f"alert {alert}")
    ax.set_xlabel("CSI (PSI of the scorecard-bin distribution)")
    ax.set_title(title)
    ax.legend(loc="lower right", fontsize=8)
    ax.tick_params(axis="y", labelsize=8)
    return save(fig, path)


def plot_vintage(wide: pd.DataFrame, path: Path, title: str) -> Path:
    fig, ax = plt.subplots(figsize=(9, 4.6))
    cmap = plt.get_cmap("viridis")
    n = len(wide)
    for i, (cohort, row) in enumerate(wide.iterrows()):
        ax.plot(np.asarray(row.index, dtype=float), row.to_numpy(dtype=float), color=cmap(i / max(n - 1, 1)), linewidth=1.4, label=str(cohort))
    ax.set_xlabel("Months on book (event month - issue month)")
    ax.set_ylabel("Cumulative default rate")
    ax.yaxis.set_major_formatter(PercentFormatter(1.0, decimals=0))
    ax.set_xlim(0, float(wide.columns.max()))
    ax.set_title(title)
    ax.legend(loc="center left", bbox_to_anchor=(1.01, 0.5), fontsize=7, ncol=1 if n <= 14 else 2, title="issue quarter", title_fontsize=8)
    return save(fig, path)
