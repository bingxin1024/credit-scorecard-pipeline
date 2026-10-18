"""PDO scaling and the scorecard points table (PLAN.md §5 `scorecard`).

    score  = Offset + Factor * ln(good:bad odds)
    Factor = PDO / ln(2)                       every PDO points the odds double
    Offset = base_score - Factor * ln(base_odds)

The WOE logistic regression gives ln(P(bad) / P(good)) = b0 + sum_i b_i * WOE_i, and
ln(good:bad odds) is minus that, so

    score = (Offset - Factor * b0)  +  sum_i ( -Factor * b_i * WOE_i )
          =  base points            +  points of the applicant's bin in each variable

Points are rounded to integers, as in a deployed scorecard; every later number uses the integer score.
"""

from __future__ import annotations

import math
from typing import Any

import numpy as np
import pandas as pd

from scorecard.binning import MISSING_LABEL, Binner, BinSpec
from scorecard.config import ScorecardConfig


def scaling_constants(pdo: float, base_score: float, base_odds: float) -> tuple[float, float]:
    factor = pdo / math.log(2)
    offset = base_score - factor * math.log(base_odds)
    return factor, offset


class Scorecard:
    """A fitted scorecard: bins + coefficients + scaling -> integer points per bin."""

    def __init__(self, bins: dict[str, BinSpec], coefficients: dict[str, float], intercept: float, cfg: ScorecardConfig):
        self.bins = {name: bins[name] for name in coefficients}
        self.coefficients = dict(coefficients)
        self.intercept = float(intercept)
        self.pdo, self.base_score, self.base_odds = float(cfg.pdo), float(cfg.base_score), float(cfg.base_odds)
        self.factor, self.offset = scaling_constants(self.pdo, self.base_score, self.base_odds)
        self.base_points = self.offset - self.factor * self.intercept
        self.base_points_int = int(np.rint(self.base_points))
        self.points: dict[str, np.ndarray] = {}
        self.points_int: dict[str, np.ndarray] = {}
        for name, spec in self.bins.items():
            pts = -self.factor * self.coefficients[name] * np.asarray(spec.woe, dtype=float)
            self.points[name] = pts
            self.points_int[name] = np.rint(pts).astype(int)

    @classmethod
    def from_binner(cls, binner: Binner, features: list[str], coef: np.ndarray, intercept: float, cfg: ScorecardConfig) -> Scorecard:
        return cls(binner.bins_, {f: float(c) for f, c in zip(features, coef)}, intercept, cfg)

    # ----- tables
    def table(self) -> pd.DataFrame:
        rows = [
            {
                "variable": "BASE",
                "bin": "(every applicant)",
                "count": np.nan,
                "share": np.nan,
                "bad_rate": np.nan,
                "woe": np.nan,
                "coefficient": np.nan,
                "points": self.base_points,
                "points_int": self.base_points_int,
            }
        ]
        for name, spec in self.bins.items():
            counts = np.asarray(spec.counts, dtype=float)
            total = counts.sum() if counts.sum() else 1.0
            for bin_id, label in enumerate(spec.labels()):
                if label == MISSING_LABEL and not spec.has_missing:
                    continue
                rows.append(
                    {
                        "variable": name,
                        "bin": label,
                        "count": int(counts[bin_id]),
                        "share": counts[bin_id] / total,
                        "bad_rate": spec.bads[bin_id] / max(counts[bin_id], 1),
                        "woe": spec.woe[bin_id],
                        "coefficient": self.coefficients[name],
                        "points": float(self.points[name][bin_id]),
                        "points_int": int(self.points_int[name][bin_id]),
                    }
                )
        return pd.DataFrame(rows)

    @property
    def min_score(self) -> int:
        return self.base_points_int + sum(int(p.min()) for p in self.points_int.values())

    @property
    def max_score(self) -> int:
        return self.base_points_int + sum(int(p.max()) for p in self.points_int.values())

    # ----- scoring
    def score(self, X: pd.DataFrame) -> np.ndarray:
        total = np.full(len(X), self.base_points_int, dtype=int)
        for name, spec in self.bins.items():
            total = total + self.points_int[name][spec.bin_ids(X[name])]
        return total

    def score_to_pd(self, score) -> np.ndarray:
        """Invert the scaling: ln(good:bad odds) = (score - Offset) / Factor."""
        return 1.0 / (1.0 + np.exp((np.asarray(score, dtype=float) - self.offset) / self.factor))

    def pd_to_score(self, p) -> np.ndarray:
        p = np.clip(np.asarray(p, dtype=float), 1e-12, 1 - 1e-12)
        return self.offset + self.factor * np.log((1 - p) / p)

    # ----- persistence
    def to_dict(self) -> dict[str, Any]:
        return {
            "scaling": {
                "pdo": self.pdo,
                "base_score": self.base_score,
                "base_odds": self.base_odds,
                "factor": self.factor,
                "offset": self.offset,
                "intercept": self.intercept,
                "base_points": self.base_points,
                "base_points_int": self.base_points_int,
                "min_score": self.min_score,
                "max_score": self.max_score,
            },
            "features": {
                name: {
                    **spec.to_dict(),
                    "coefficient": self.coefficients[name],
                    "points": [float(p) for p in self.points[name]],
                    "points_int": [int(p) for p in self.points_int[name]],
                }
                for name, spec in self.bins.items()
            },
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any], cfg: ScorecardConfig | None = None) -> Scorecard:
        scaling = data["scaling"]
        cfg = cfg or ScorecardConfig(pdo=scaling["pdo"], base_score=scaling["base_score"], base_odds=scaling["base_odds"])
        bins, coefs = {}, {}
        for name, spec in data["features"].items():
            spec = dict(spec)
            coefs[name] = float(spec.pop("coefficient"))
            spec.pop("points", None)
            spec.pop("points_int", None)
            bins[name] = BinSpec.from_dict(spec)
        return cls(bins, coefs, scaling["intercept"], cfg)
