# CLAUDE.md — credit-scorecard-pipeline

## What this project is

An automated credit-scorecard and strategy-analysis pipeline, packaged as a
Python package + CLI + agent skill. Given any loan-level CSV with a binary
default label (or a raw dataset with a registered adapter), it runs the full
retail-credit modelling workflow — sample definition → data profiling →
monotonic WOE binning → IV / correlation selection → logistic-regression
scorecard with a GBDT challenger → PDO scaling → cut-off / swap-set / profit
analysis → PSI / CSI / vintage monitoring — and renders a fixed-structure
report (HTML + Markdown).

Primary dataset: Lending Club accepted loans (raw, loan-level).
Secondary: UCI credit-card default data (small; used for tests and as a
second adapter to prove the engine is dataset-agnostic).

Audience: hiring managers for retail-credit risk-strategy roles, and agents
that call this as a skill. Optimise for interpretability and defensibility
over model-performance tricks. Every number in a report must come from the
run that produced it.

The detailed build plan, dataset rules and acceptance criteria are in
`PLAN.md` (Chinese). Read it fully before writing any code.

## Stack

- Python 3.11+, pandas, numpy, scikit-learn, matplotlib, jinja2, pyyaml,
  pytest, ruff
- Binning / WOE / IV / scorecard / PSI engine: `toad`. If `pip install toad`
  fails on this machine, fall back to `optbinning` behind the same internal
  interface — `scorecard/binning.py` must hide which library is used.
- GBDT challenger: `sklearn.ensemble.HistGradientBoostingClassifier`
  (no extra dependency). Do not add lightgbm / xgboost.
- No notebooks inside the package. Notebooks, if any, live in `notebooks/`
  and are not part of the pipeline.

## Repository layout

```
credit-scorecard-pipeline/
├── CLAUDE.md  PLAN.md  README.md  README_zh.md  FAQ.md  DECISIONS.md  LICENSE (MIT)
├── SKILL.md                       # agent entry point (Phase 3)
├── pyproject.toml
├── scorecard/
│   ├── __init__.py  cli.py        # python -m scorecard run --config <yaml>
│   ├── adapters/   base.py  lendingclub.py  uci.py   # raw data -> standard frame
│   ├── config.py   profile.py  binning.py  select.py  model.py  scorecard.py
│   ├── strategy.py  monitor.py  report.py
│   └── templates/  report.html.j2  report.md.j2
├── configs/        default.yaml  lendingclub.yaml  uci.yaml
├── data/           raw/ (gitignored)   README.md (how to obtain the data)
├── examples/       lendingclub/  uci/   # committed reports + figures
├── tests/          synthetic fixtures only — tests never read data/raw
├── docs/           (mkdocs, Phase 3)
└── .github/workflows/ci.yml
```

## Hard rules

1. `data/raw/` is never committed. Example reports and figures in
   `examples/` are committed.
2. The engine (everything outside `adapters/`) never references a
   dataset-specific column name. Dataset knowledge lives only in adapters
   and configs.
3. Reproducible: fixed `random_state` from config. The report header records
   config hash, data file name + row count, git commit and timestamp.
4. No leakage: binning / WOE are fitted on train only and refitted inside
   each CV fold. The OOT split is by `issue_date` when the adapter provides
   one, otherwise a stratified hold-out.
5. The report structure is fixed (7 sections, PLAN.md §3). A section that is
   not implemented yet renders a visible "not implemented" placeholder; it
   never silently disappears.
6. Numbers in README / FAQ are copied from `examples/*/report.md`, never
   typed from memory.
7. Keep the user's time cheap: prefer a sensible default plus a line in
   `DECISIONS.md` over asking. Ask only when a wrong guess would cost more
   than an hour to undo.
8. Language: code, docstrings, README.md, FAQ.md in English. README_zh.md
   and the generated report in Chinese with English technical terms kept
   (WOE, IV, KS, PSI, cut-off, swap set ...).

## Workflow for each phase (PLAN.md §7)

1. Read the phase in PLAN.md. Create a todo list.
2. Implement. Run `ruff check .` and `pytest -q`. Then run the real pipeline:
   `python -m scorecard run --config configs/lendingclub.yaml`.
3. Open the generated `report.html` and check every section for empty
   tables, NaN, or numbers that make no sense (bad rate outside 1–40 %,
   KS > 0.9, PSI exactly 0, ...). Fix before moving on.
4. Copy the final report and figures into `examples/<dataset>/`.
5. Append decisions to `DECISIONS.md` and interview Q&A to `FAQ.md`
   (PLAN.md §8).
6. Commit with a conventional message, push, and print a phase summary of at
   most 15 lines: command to run, key metrics, open questions for the user.

## Verification commands

- `pytest -q`
- `ruff check .`
- `python -m scorecard run --config configs/uci.yaml`          # < 1 min
- `python -m scorecard run --config configs/lendingclub.yaml`  # target < 15 min
