# credit-scorecard-pipeline

An automated credit-scorecard and strategy-analysis pipeline for retail lending, packaged as a
Python package, a CLI and an agent skill (`SKILL.md`). Point it at any loan-level table with a
binary default label and it runs the whole retail-credit modelling workflow and renders a
fixed-structure, seven-section report (HTML + Markdown) with every number traceable to a CSV.

![Report header: sample, scorecard size, train / test / OOT AUC and KS, and the constrained cut-off](docs/images/report-lendingclub.jpg)

Reproduce the Lending Club report in one command (data under `data/raw/`, see `data/README.md`):

```bash
python -m scorecard run --config configs/lendingclub.yaml
```

```
raw data ──adapter──▶ standard frame ──engine──▶ artifacts ──report──▶ report.html / report.md
                      (target, issue_date,   │
                       features, loan_amount,├─ profile.py   data health, bad rate by quarter
                       net_cash, event_date) ├─ binning.py   toad / optbinning / tree → monotone WOE, IV
                                             ├─ select.py    missing, IV, time stability, correlation, sign, VIF
                                             ├─ model.py     WOE logistic regression + HistGradientBoosting challenger
                                             ├─ scorecard.py PDO scaling, points table
                                             ├─ strategy.py  cut-offs under constraints, profit, swap set
                                             ├─ monitor.py   score PSI, feature CSI, vintage curves
                                             └─ checks.py    automatic checks (section 7)
SKILL.md ──▶ python -m scorecard run --config <yaml> [--dry-run]
```

The engine never references a dataset-specific column name: dataset knowledge lives only in
`scorecard/adapters/` and `configs/`. Swapping datasets = one adapter + one YAML. Three adapters
ship: Lending Club (Kaggle accepted loans 2007–2018Q4, 2.26 M raw loans, 151 columns), the UCI
credit-card default data (id 350, downloaded automatically) and a synthetic loan book for tests
and demos. Example reports are committed under [`examples/`](examples/).

## Quick start

```bash
python -m venv .venv && .venv/Scripts/activate      # Windows; use source .venv/bin/activate elsewhere
pip install -e ".[dev,uci]" toad                    # toad = binning backend (optbinning / internal tree
                                                    # are used if it is missing); ucimlrepo for the UCI data
pytest -q && ruff check .

python -m scorecard run --config configs/synthetic.yaml                  # no data needed, ~10 s
python -m scorecard run --config configs/uci.yaml                        # downloads 30k rows, ~20 s
python -m scorecard run --config configs/lendingclub.yaml --dry-run      # sample-definition table only
python -m scorecard run --config configs/lendingclub.yaml                # full run, ~2 min with the parse cache
python -m scorecard run --config configs/lendingclub.yaml --sample-frac 0.1   # 1-minute smoke run
```

Outputs land in `outputs/<dataset>/`: `report.html` (self-contained), `report.md`, `figures/`, and
every table behind the report (`scorecard.csv`, `scorecard_model.json`, `feature_selection.csv`,
`model_metrics.csv`, `strategy_*.csv`, `monitor_*.csv`, `checks.csv`, `results.json`, `run_meta.json`).

Guardrails built into the CLI (details in `SKILL.md`): the input data is never modified, the
sample-definition impact table is printed before modelling (`--dry-run` stops there), and a run
whose bad rate falls outside 1–40 % stops with exit code 2 unless `--allow-any-bad-rate` is given.

## What the Lending Club run produces

Numbers below are copied from [`examples/lendingclub/report.md`](examples/lendingclub/report.md);
the report header records the config hash, data file, row count, git commit and timestamp that
produced them. The card is built for one product (36-month loans) and runs in two variants, with
and without the platform's own rating.

| Item | Value |
|---|---|
| Raw loans → final sample | 2,260,701 → 589,488 matured 36-month loans issued 2012-01 … 2015-12 |
| Bad rate (Charged Off / Default vs Fully Paid) | 14.03 % |
| Split | train 299,076 / test 128,176 stratified 70/30 on 2012-01 … 2015-06; OOT = 162,236 loans issued 2015-07 … 2015-12 |
| Candidate features → scorecard | 99 → 6 (missing > 50 %: 35 → IV < 0.02: 41 → time-stability CSI > 0.25: 15 → \|ρ\| > 0.7: 2 → sign check: 0) |
| LR scorecard AUC / KS — train | 0.6429 / 0.2047 |
| LR scorecard AUC / KS — test | 0.6473 / 0.2134 |
| LR scorecard AUC / KS — OOT | 0.6508 / 0.2149 |
| 5-fold CV AUC (binning refitted per fold) | 0.6416 ± 0.0025 |
| GBDT challenger AUC — test / OOT | 0.6890 / 0.6968 |
| Variant with the platform rating, AUC / KS — test / OOT | 0.6753 / 0.2566 and 0.6897 / 0.2793 (`sub_grade` enters with IV 0.3154) |
| Scale | PDO 20, 600 points ↔ 20:1 good:bad odds; score range 527–620 |
| Constrained cut-off (OOT, approved bad rate ≤ 10 %) | score ≥ 567 approves 56.2 % at 9.95 % bad rate (with the platform rating: score ≥ 563, 66.95 %) |
| At 70 % approval (OOT) | score ≥ 561 (actual 70.85 %), approved bad rate 11.27 % vs 14.71 % overall |
| Swap set vs platform grade at 70 % (OOT) | swap-in 19.84 % vs swap-out 17.82 %: the application-only card loses to the grade by 0.42 pp; with the rating it wins by 0.51 pp |
| Score PSI train → test / train → OOT | 0.0002 / 0.0003; every scorecard feature's CSI < 0.10 after the time-stability step removed 15 bureau fields |
| Automatic checks | 24 pass / 1 warn (the swap set above) / 0 fail |
| Run time (full data, both variants, cached parse) | 1.9 min |

The time-stability step (section 2.3b) drops features whose bin distribution differs between the
earliest and latest issue year inside train; on Lending Club those are the bureau fields that
only started being populated during 2012. It buys a card whose section 6 shows no drift at all,
at the price of about 0.02 AUC on test and 0.024 on OOT against a card that keeps them
(`select.max_time_csi: null`: 15 features, test 0.6656 / OOT 0.6743). Starting the sample at
2013-01 keeps both the filter and the features (test 0.6624 / OOT 0.6737); the trade-off is
recorded in `DECISIONS.md` (D26) and left to the user.

### UCI credit-card default (second dataset)

From [`examples/uci/report.md`](examples/uci/report.md): 30,000 clients, bad rate 22.12 %, 17 of
32 candidate features in the card; LR AUC / KS train 0.7755 / 0.4176, test 0.7667 / 0.4212,
hold-out 0.7641 / 0.4020 (no date column, so a stratified hold-out plays the OOT role); approved
bad rate ≤ 10 % allows 51.75 % approval on test. Checks: 12 pass / 1 warn / 0 fail — the warning
is the IV > 0.5 review of `PAY_0` and friends, which the adapter documents as legitimate.

## Report structure (fixed, 7 sections)

1. **Sample and data overview** — source, sample-definition impact table (every rule with rows
   removed and remaining bad rate), field audit (every raw column classified: target / post-loan
   leakage / identifier / investor side / platform rating / joint application / candidate),
   missing-rate top 20, bad rate by issue quarter, missing rate by year, split summary.
2. **Binning and IV** — IV ranking of all candidates, selection funnel, features dropped for time
   instability, monotonicity check, WOE plots of the top 8 features, bin tables of every scorecard feature.
3. **Model performance** — LR coefficients with VIF, train / test / OOT AUC-KS-Gini, LR vs GBDT
   challenger, 5-fold CV, ROC and KS curves; both variants side by side.
4. **Scorecard** — PDO scaling with the actual numbers, points table, score distributions.
5. **Strategy analysis** — equal-frequency score bands, approval-rate vs bad-rate curve, candidate
   cut-offs at 50–90 % approval with the marginal tranche, **constrained optimal cut-offs** (highest
   approval under a bad-rate cap; bad rate and net cash at a target approval rate) as the headline,
   profit curve on realised net cash as a reference, swap set vs the platform grade, both variants
   compared at equal approval.
6. **Stability** — score PSI (train → test / OOT on train-decile bands), CSI of every scorecard
   feature on its own bins with the bin that moved most, vintage curves by issue quarter.
7. **Automatic checks** — leakage IV, degenerate bins, train–test KS gap, PSI / CSI, missing-in-model,
   coefficient signs, VIF, swap-set sanity, plus every adapter warning; each row states what was
   checked, the threshold, the value and a pass / warn / fail verdict.

A section whose module is switched off renders a visible "（本阶段未实现）" placeholder instead of
disappearing. The report body is Chinese with English technical terms (WOE, IV, KS, PSI, cut-off,
swap set …).

Hard rules the code follows (see `CLAUDE.md`): `data/raw/` is never committed; binning, WOE,
selection and models are fitted on train only, and binning + WOE are refitted inside every CV fold
(the selected feature list is fixed from the full training set, so CV is slightly optimistic); the
OOT split is by issue date; every number in the report comes from the run that produced it.

## Adding a dataset

1. Write an adapter under `scorecard/adapters/` that returns the standard frame
   (`target` 0/1, feature columns, optional `issue_date`, `event_date`, `loan_amount`, `net_cash`)
   plus an `AdapterMeta` with the sample-definition log and field audit. `generic.py` already covers
   any CSV with a label column (`dataset.options.target_col`); `uci.py` is a 300-line example with
   a download step, documented clean-ups and engineered behaviour features.
2. Add a YAML under `configs/` that `extends: default.yaml`.
3. `python -m scorecard run --config configs/<name>.yaml --dry-run`, then without `--dry-run`.

## Repository layout

```
scorecard/          package: cli.py, config.py, pipeline.py, adapters/ (base, lendingclub, uci,
                    generic, synthetic), binning.py, select.py, model.py, scorecard.py,
                    strategy.py, monitor.py, checks.py, report.py, figures.py, templates/
configs/            default.yaml, lendingclub.yaml, uci.yaml, synthetic.yaml
examples/           committed reports + figures (lendingclub, uci, synthetic)
tests/              synthetic fixtures only (never read data/raw); CI runs ruff + pytest + a synthetic smoke run
SKILL.md            agent entry point: inputs, steps, outputs, guardrails
DECISIONS.md        decision log (Chinese)      FAQ.md   interview Q&A with the actual numbers
```

## Status

- Phase 1: pipeline end to end, report sections 1–4, Lending Club adapter.
- Phase 2: strategy + monitoring layers, section 7 checks, with / without platform-rating scorecards.
- Phase 3 (v1.0): `SKILL.md` with CLI guardrails, UCI adapter, time-stability feature filter,
  constrained cut-offs, GitHub Actions CI.

License: MIT.
