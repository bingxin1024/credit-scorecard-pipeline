---
name: credit-scorecard-pipeline
description: Build a full retail-credit scorecard and strategy report from any loan-level table with a binary default label (sample definition, WOE binning, LR scorecard + GBDT challenger, PDO scaling, cut-off / swap set / profit, PSI / CSI / vintage, automatic checks). Use when asked to build, refresh or audit a credit scorecard, or to analyse approval cut-offs on a loan dataset.
---

# credit-scorecard-pipeline (agent skill)

One command turns a loan-level dataset with a default label into a fixed seven-section report
(HTML + Markdown, Chinese with English technical terms) plus every table behind it as CSV / JSON.
The engine never modifies the input data and never references dataset-specific column names;
dataset knowledge lives in an adapter and a YAML config.

## Inputs

Pick one of the two entry points.

1. **A CSV with a label column** (no code needed): the `generic` adapter.
   - required: `target_col` (binary label), the CSV path
   - optional: `positive_label` (value that means default; default 1), `date_col` (origination date,
     enables the time-based OOT split and vintage curves), `loan_amount_col`, `net_cash_col`
     (realised net cash flow, strategy layer only), `platform_rating_cols` (an existing rating to
     compare against in the swap set), `drop_cols`, `categorical_cols`
2. **A registered adapter** for a raw dataset: `lendingclub` (Kaggle accepted loans 2007–2018Q4),
   `uci` (UCI id 350, downloaded automatically), `synthetic` (no data needed, 10-second demo).

Write a config that `extends: default.yaml` and run it:

```yaml
# configs/my_loans.yaml
extends: default.yaml
dataset:
  adapter: generic
  path: data/raw/my_loans.csv
  options: {target_col: defaulted, positive_label: yes, date_col: orig_date, loan_amount_col: amount}
output:
  dir: outputs/my_loans
```

## Steps (what the agent does, in order)

1. **Dry run first.** `python -m scorecard run --config configs/my_loans.yaml --dry-run` loads the
   data, prints the sample-definition impact table (every rule, rows removed, remaining bad rate) and
   stops before any modelling. Show that table to the user and confirm the label and the rules.
2. **Full run.** `python -m scorecard run --config configs/my_loans.yaml` (synthetic < 10 s,
   UCI < 1 min, Lending Club full data about 3 min with the parse cache).
3. **Read `outputs/<name>/report.md`** section by section; quote numbers from it, never from memory.
   Section 7 lists every automatic check with its threshold and verdict; treat a 🔴 as "do not ship"
   and a 🟡 as "needs a human decision", and say so.
4. **Hand over** `report.html` (self-contained) and point to the CSVs for any number the user wants
   to trace (`results.json`, `scorecard.csv`, `strategy_cutoffs.csv`, `monitor_csi.csv`, `checks.csv`).

Useful flags: `--output <dir>`, `--sample-frac 0.1` (seeded row sample for a smoke run on a large
file), `--no-cv` (skip the challenger cross-validation), `--nrows N`, `--no-cache`, `-v`.

## Outputs

`outputs/<name>/`: `report.html`, `report.md`, `figures/*.png`, and the tables behind the report
(`sample_definition.csv`, `field_audit.csv`, `iv_table.csv`, `feature_selection.csv`, `bin_tables.csv`,
`lr_coefficients.csv`, `model_metrics.csv`, `scorecard.csv`, `scorecard_model.json`,
`strategy_*.csv`, `monitor_*.csv`, `checks.csv`, `results.json`, `run_meta.json`). With
`features.use_platform_rating: [false, true]` the per-variant tables carry a
`no_platform_rating_` / `with_platform_rating_` prefix.

The report header records the config hash, data file, row count, git commit and timestamp, so a
run can be reproduced exactly.

## Guardrails (built into the CLI; do not work around them)

- **The input data is never modified.** Parsed subsets are cached under `data/cache/` only.
- **The sample-definition table is printed before modelling** (and `--dry-run` stops there).
  Do not start a full run until the user has seen which rules removed how many rows.
- **The run stops when the sample bad rate is outside 1–40 %** (exit code 2, message `STOP: …`).
  This almost always means a wrong `positive_label`, a wrong label column or an unmatured sample.
  Fix the config and rerun; pass `--allow-any-bad-rate` only when the user has confirmed the label
  is right and the rate is genuinely that unusual.
- **An empty sample stops the run** instead of producing an empty report.
- **Section 7 verdicts are not optional.** A feature with IV > 0.5 in the scorecard, a test KS above
  0.9, a positive LR coefficient or a score PSI above 0.25 means something is wrong with the data or
  the label; report it to the user instead of silently lowering a threshold.
- **Reserved columns are never features.** `net_cash`, `loan_amount`, `event_date`, `issue_date`
  feed only the strategy and monitoring sections; the engine refuses a frame that lists one as a
  feature.
- **Do not add dataset-specific logic to the engine.** A new dataset is one adapter under
  `scorecard/adapters/` plus one YAML; see `README.md` → Adding a dataset.
- Keep `random_state` fixed (config `split.random_state`) so that reruns are comparable.

## When to stop and ask

- The dry run shows a sample-definition rule removing most rows, or a bad rate the user did not expect.
- The label column is ambiguous (several candidate columns, or a status field that needs mapping).
- Section 7 reports a 🔴 verdict.
- The dataset has no date column and the user cares about out-of-time validation (the hold-out
  used instead is random, and the report says so).
