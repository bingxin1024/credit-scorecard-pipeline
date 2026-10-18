"""Command line: `python -m scorecard run --config configs/lendingclub.yaml`."""

from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

from scorecard.adapters import available_adapters
from scorecard.config import load_config


def _setup_logging(verbose: bool) -> None:
    for stream in (sys.stdout, sys.stderr):  # Chinese warnings on a Windows console
        try:
            stream.reconfigure(encoding="utf-8")
        except Exception:  # noqa: BLE001
            pass
    logging.basicConfig(
        level=logging.DEBUG if verbose else logging.INFO,
        format="%(asctime)s %(levelname)-7s %(message)s",
        datefmt="%H:%M:%S",
        stream=sys.stdout,
    )
    logging.getLogger("matplotlib").setLevel(logging.WARNING)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="scorecard", description="Automated credit-scorecard pipeline")
    sub = parser.add_subparsers(dest="command", required=True)

    run = sub.add_parser("run", help="run the full pipeline and render the report")
    run.add_argument("--config", required=True, help="YAML config (see configs/)")
    run.add_argument("--output", default=None, help="override output.dir")
    run.add_argument("--nrows", type=int, default=None, help="override dataset.nrows (head of file; smoke runs)")
    run.add_argument("--sample-frac", type=float, default=None, help="random row fraction (seeded) instead of the file head")
    run.add_argument("--no-cache", action="store_true", help="ignore / do not write the parsed-data cache")
    run.add_argument("--no-cv", action="store_true", help="skip the challenger cross-validation (faster)")
    run.add_argument("-v", "--verbose", action="store_true")

    sub.add_parser("adapters", help="list available adapters")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.command == "adapters":
        for name in available_adapters():
            print(name)
        return 0

    _setup_logging(args.verbose)
    cfg = load_config(args.config)
    if args.nrows:
        cfg.dataset.nrows = int(args.nrows)
        cfg.raw["dataset"]["nrows"] = int(args.nrows)
    if args.sample_frac:
        cfg.dataset.options["sample_frac"] = float(args.sample_frac)
        cfg.raw["dataset"].setdefault("options", {})["sample_frac"] = float(args.sample_frac)
    if args.no_cache:
        cfg.dataset.cache = False
    if args.no_cv:
        cfg.model.cv_challenger = False
        cfg.raw["model"]["cv_challenger"] = False
    out_dir = Path(args.output) if args.output else cfg.output_dir

    from scorecard.pipeline import run as run_pipeline

    result = run_pipeline(cfg, output_dir=out_dir)
    primary = result.primary
    print("")
    print(f"report : {out_dir / 'report.html'}")
    print(f"rows   : {len(result.frame):,}   bad rate {result.frame['target'].mean():.2%}")
    print(f"model  : {len(primary.selected)} features in the scorecard (of {len(primary.candidate_features)} candidates)")
    for row in primary.metrics[primary.metrics["model"] == "LR scorecard"].itertuples():
        print(f"  {row.segment:<6} AUC {row.auc:.4f}  KS {row.ks:.4f}  Gini {row.gini:.4f}  (n={row.n:,})")
    if result.warnings:
        print("warnings:")
        for w in result.warnings:
            print(f"  - {w}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
