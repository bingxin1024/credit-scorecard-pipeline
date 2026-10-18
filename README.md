# credit-scorecard-pipeline

An automated credit-scorecard and strategy-analysis pipeline for retail lending, packaged as a
Python package + CLI (+ agent skill in Phase 3). Point it at any loan-level CSV with a binary
default label (or a raw dataset with a registered adapter) and it runs the full workflow and
renders a fixed-structure report:

```
sample definition → data profiling → monotonic WOE binning → IV / correlation selection
→ logistic-regression scorecard + GBDT challenger → PDO scaling
→ cut-off / swap set / profit → PSI / CSI / vintage monitoring → automatic checks
```

Primary dataset: Lending Club accepted loans 2007–2018Q4 (2.26 M raw loans, 151 columns).
The engine never references a dataset-specific column name: dataset knowledge lives only in
`scorecard/adapters/` and `configs/`. Swapping datasets = one adapter + one YAML.

The example report for Lending Club is committed in [`examples/lendingclub/`](examples/lendingclub/)
(`report.html` is self-contained, `report.md` is the same content as Markdown).

## Quick start

```bash
python -m venv .venv && .venv/Scripts/activate      # Windows; use source .venv/bin/activate elsewhere
pip install -e ".[dev]" toad                        # toad is the binning backend; optbinning or the
                                                    # internal tree backend are used if it is missing
pytest -q && ruff check .

# 10-second demo on synthetic data (no download needed)
python -m scorecard run --config configs/synthetic.yaml

# Lending Club: put accepted_2007_to_2018Q4.csv.gz under data/raw/ (see data/README.md)
python -m scorecard run --config configs/lendingclub.yaml                     # full run
python -m scorecard run --config configs/lendingclub.yaml --sample-frac 0.1   # 1-minute smoke run
```

Outputs land in `outputs/<dataset>/`: `report.html`, `report.md`, `figures/`, and every table
behind the report as CSV / JSON (`scorecard.csv`, `scorecard_model.json`, `iv_table.csv`,
`feature_selection.csv`, `model_metrics.csv`, `results.json`, `run_meta.json`, …).

## What the Lending Club run produces

Numbers below are copied from [`examples/lendingclub/report.md`](examples/lendingclub/report.md);
the report header records the config hash, data file, row count, git commit and timestamp that
produced them.

| Item | Value |
|---|---|
| Raw loans → final sample | 2,260,701 → 633,767 matured loans issued 2012-01 … 2015-12 |
| Bad rate (Charged Off / Default vs Fully Paid) | 14.85% |
| Split | train / test stratified 70/30 on 2012-01 … 2015-06; OOT = 2015-07 … 2015-12 (162,236 loans) |
| Candidate features → scorecard | 99 → 20 (missing > 50 % → IV < 0.02 → \|ρ\| > 0.7 → sign check) |
| LR scorecard AUC / KS — train | 0.6733 / 0.2467 |
| LR scorecard AUC / KS — test | 0.6744 / 0.2513 |
| LR scorecard AUC / KS — OOT | 0.6750 / 0.2526 |
| GBDT challenger AUC — test / OOT | 0.6941 / 0.6959 |
| 5-fold CV AUC (binning refitted per fold) | 0.6719 ± 0.0026 |
| Scale | PDO 20, 600 points ↔ 20:1 good:bad odds; score range 485–640 |
| Scorecard with the platform rating (variant 2) AUC / KS — test / OOT | 0.6886 / 0.2760 and 0.6978 / 0.2874 |
| 70 % approval cut-off (OOT) | score ≥ 560 approves 70.88 %, approved bad rate 10.60 % (14.71 % overall) |
| Swap set vs platform grade at that cut-off (OOT) | swap-in bad rate 18.63 % vs swap-out 19.97 %; approved bad rate 10.60 % vs 10.85 % |
| Score PSI train → test / train → OOT | 0.0001 / 0.0271 (stable); CSI > 0.25 on `term` and six bureau fields (missing-bin shift) |
| Automatic checks | 21 pass / 4 warn / 0 fail / 1 info |
| Run time (full data, both variants, cached parse) | 2.4 min |

The scorecard deliberately excludes the platform's own rating (`grade`, `sub_grade`, `int_rate`,
`installment`); the "with platform rating" variant runs side by side (there `sub_grade` enters with
IV 0.3546 and `grade` / `int_rate` / `installment` fall to the correlation filter).

## Report structure (fixed, 7 sections)

1. **Sample and data overview** — source, sample-definition impact table (every rule with rows
   removed and remaining bad rate), field audit (every raw column classified: target / post-loan
   leakage / identifier / investor side / platform rating / joint application / candidate),
   missing-rate top 20, bad rate by issue quarter, missing rate by year, split summary.
2. **Binning and IV** — IV ranking of all candidates, selection funnel, monotonicity check,
   WOE plots of the top 8 features, bin tables of every scorecard feature.
3. **Model performance** — LR coefficients with VIF, train / test / OOT AUC-KS-Gini, LR vs GBDT
   challenger, 5-fold CV, ROC and KS curves.
4. **Scorecard** — PDO scaling with the actual numbers, points table, score distributions.
5. **Strategy analysis** — equal-frequency score bands, approval-rate vs bad-rate curve, candidate
   cut-offs at 50–90 % approval with the marginal tranche, profit curve on realised net cash (total
   and per loan), swap set vs the platform grade, both scorecard variants compared at equal approval.
6. **Stability** — score PSI (train → test / OOT on train-decile bands), CSI of every scorecard
   feature on its own bins with the bin that moved most, vintage curves by issue quarter.
7. **Automatic checks** — leakage IV, degenerate bins, train–test KS gap, PSI / CSI, missing-in-model,
   coefficient signs, VIF, swap-set sanity, plus every adapter warning; each row states what was
   checked, the threshold, the value and a pass / warn / fail verdict.

A section whose module is switched off renders a visible "（本阶段未实现）" placeholder instead of
disappearing; all seven are implemented.
The report body is Chinese with English technical terms (WOE, IV, KS, PSI, cut-off, swap set …).

## Architecture

```
raw data ──adapter──▶ standard frame ──engine──▶ artifacts ──report──▶ report.html / report.md
                      (target, issue_date,   │
                       features, loan_amount,├─ profile.py   data health
                       net_cash)             ├─ binning.py   toad / optbinning / tree → monotone WOE, IV
                                             ├─ select.py    missing, IV, correlation, sign, VIF
                                             ├─ model.py     WOE logistic regression + HistGradientBoosting
                                             ├─ scorecard.py PDO scaling, points table
                                             ├─ strategy.py  cut-off / swap set / profit
                                             ├─ monitor.py   PSI / CSI / vintage
                                             └─ checks.py    automatic checks (section 7)
```

Hard rules the code follows (see `CLAUDE.md`): `data/raw/` is never committed; binning, WOE,
selection and models are fitted on train only, and binning + WOE are refitted inside every CV fold
(the selected feature list is fixed from the full training set, so CV is slightly optimistic); the OOT split
is by issue date; every number in the report comes from the run that produced it.

## Adding a dataset

1. Write an adapter under `scorecard/adapters/` that returns the standard frame
   (`target` 0/1, feature columns, optional `issue_date`, `loan_amount`, `net_cash`) plus an
   `AdapterMeta` with the sample-definition log and field audit. `generic.py` already covers any
   CSV with a label column (`dataset.options.target_col`).
2. Add a YAML under `configs/` that `extends: default.yaml`.
3. `python -m scorecard run --config configs/<name>.yaml`.

## Repository layout

```
scorecard/          package: cli.py, config.py, pipeline.py, adapters/, binning.py, select.py,
                    model.py, scorecard.py, strategy.py, monitor.py, checks.py, report.py,
                    figures.py, templates/
configs/            default.yaml, lendingclub.yaml, synthetic.yaml
examples/           committed reports + figures
tests/              synthetic fixtures only (never read data/raw)
DECISIONS.md        decision log (Chinese)      FAQ.md   interview Q&A with the actual numbers
```

## Status

- Phase 1: pipeline end to end, report sections 1–4, Lending Club adapter.
- Phase 2 (this release): strategy + monitoring layers, section 7 checks, with / without
  platform-rating scorecards side by side.
- Phase 3: `SKILL.md` for agents, UCI adapter, docs site, v1.0.

License: MIT.
