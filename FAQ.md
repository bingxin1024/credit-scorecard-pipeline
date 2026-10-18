# FAQ — interview questions this project answers

Each answer: a spoken-style reply (≤ 150 words), the file / report section that backs it, and the
actual numbers from `examples/lendingclub/report.md` (36-month Lending Club scorecard, both
variants; numbers are copied from the report, never typed from memory; unless stated otherwise
they refer to the scorecard *without* the platform rating). UCI numbers come from
`examples/uci/report.md`.

### 1. How is the default label defined? Why drop unmatured and indeterminate loans? What is the performance window?

A loan is bad (1) if its final status is *Charged Off* or *Default*, good (0) if *Fully Paid*.
We build one scorecard per product, so only 36-month loans are kept, and only loans whose full term
has elapsed by the data cut-off (issue month + 36 ≤ 2018-12), so every loan has had the same
opportunity to go bad — a 2017 loan that is still *Current* would otherwise look "good" simply
because it is young. Loans still *Current*, *Late* or *In Grace Period* at cut-off are
indeterminate: we do not know their outcome and labelling them either way would bias the bad rate.
The performance window is therefore the whole 36-month term, longer than the 12–18 months a bank
would use, which is why the bad rate is higher than a "12-month bad" definition would give.

*Where:* `scorecard/adapters/lendingclub.py` (`transform`, rules 3–5), report §1.2.
*Numbers:* term filter removes 650,603 60-month loans, maturity rule 988,585, terminal-status rule
147 indeterminate ones, min_issue_date 29,096; final sample 589,488 loans, bad rate 14.03 %.

### 2. Which leakage fields were removed? Give three and explain why `last_fico_range_*` is leakage.

Anything observed after origination is removed before modelling: (1) `total_pymnt`, `recoveries`,
`out_prncp` — realised repayments and balances, they *are* the outcome; (2) `last_pymnt_d`,
`last_credit_pull_d`, `next_pymnt_d` — payment-timeline fields that reveal whether the loan is
still alive; (3) all `hardship_*`, `settlement_*`, `debt_settlement_flag` — servicing actions that
only happen to distressed loans. `last_fico_range_high/low` is the FICO refreshed at the *last*
credit pull, typically after months of delinquency have already hit the bureau; it encodes the
outcome, not the applicant's risk at application. The field audit classifies every one of the
151 raw columns into one group so nothing slips through by default; `total_pymnt` and
`last_pymnt_d` are read but only feed the strategy / vintage sections, never the features.

*Where:* `configs/lendingclub.yaml` → `field_groups`, report §1.4 (field audit).
*Numbers:* 31 columns dropped as leakage (groups B / C / D), 99 candidate features kept.

### 3. Why is WOE refitted inside every CV fold? What goes wrong if it is done outside?

WOE encoding uses the label: each bin's value is ln(good share / bad share) computed from the
training rows. If you encode the whole training set once and then cross-validate, every
validation fold's labels have already been "seen" by the encoding that scores it, so the CV
estimate is optimistic — exactly like fitting a target encoder on the full data. Refitting the
bins and WOE on the fitting folds only keeps the validation fold honest. The same logic drives
the train / test / OOT design: binning, WOE, selection and the LR are fitted on train only.

*Where:* `scorecard/model.py` → `cross_validate_scorecard`; `scorecard/pipeline.py` → `fit_variant`.
*Numbers:* 5-fold CV AUC 0.6416 ± 0.0025 (KS 0.2050 ± 0.0038) vs test AUC 0.6473 — close, as
they should be.

### 4. How is monotonicity enforced? What happens when a feature is not monotone?

Numeric features are first cut by the backend (toad chi-merge, max 6 bins, ≥ 5 % of rows per
bin). Then the bad rate per bin is checked: if it is not monotone, the adjacent pair that
violates the direction with the smallest bad-rate gap is merged, repeatedly, until the series is
monotone or only 2 bins remain. Categorical features are ordered by training bad rate first, so
their grouping is monotone by construction. Monotone bins give scores that can be explained
("higher DTI never gains points") and are less likely to fit noise. The price is a little IV on
genuinely U-shaped features.

*Where:* `scorecard/binning.py` → `merge_to_monotonic`, report §2.4.
*Numbers:* 0 of 6 scorecard features needed merging; `fico_mid` 6 bins, `dti` 4, `loan_to_inc` 4.

### 5. How were the IV thresholds set? What does a very high IV mean?

Rule of thumb: IV < 0.02 carries no usable signal, 0.02–0.1 weak, 0.1–0.3 medium, 0.3–0.5
strong, > 0.5 suspiciously strong. We drop below 0.02 and flag above 0.5 as a leakage suspect but
keep it for a human to decide. On Lending Club no application-time feature comes close, which is
itself a sanity check that the leakage fields were really removed; on UCI `PAY_0` reaches 0.849
and the adapter documents why that is legitimate (September status, October label). Thresholds
are config (`select.min_iv`, `select.leakage_iv`), and the selection table records which rule
removed each feature.

*Where:* `scorecard/select.py`, report §2.2–2.3.
*Numbers:* top IV `fico_mid` = 0.1307; 41 features dropped for IV < 0.02, 35 for missing > 50 %,
15 for time instability, 2 for correlation; 0 flagged > 0.5.

### 6. Why ship the logistic regression and not the GBDT? What is the challenger for?

The scorecard is a WOE logistic regression because every point is traceable to one bin of one
variable, it can be implemented in a decision engine as a lookup table, and reason codes for
declines fall out of it. The GBDT (HistGradientBoosting on raw features, missing values included)
is a *challenger*: it tells us how much signal we leave on the table by insisting on a linear,
monotone, binned model with few variables. Here the gap is about 0.04 AUC, most of it from the
bureau fields the time-stability filter removed from the scorecard but not from the challenger;
that is the price of a card that is stable across years, and it is worth stating rather than hiding.

*Where:* `scorecard/model.py` → `GBDTChallenger`, report §3.4.
*Numbers:* test AUC LR 0.6473 vs GBDT 0.6890; OOT 0.6508 vs 0.6968 (KS 0.2149 vs 0.2866).

### 7. 600 points ↔ 20:1 odds, PDO 20: how are offset and factor computed?

Score = Offset + Factor × ln(odds), odds = good:bad. Factor = PDO / ln 2 = 20 / 0.6931 = 28.8539,
so every 20 points double the odds. Offset = 600 − Factor × ln 20 = 600 − 28.8539 × 2.9957 =
513.5614. The LR gives ln(P(bad)/P(good)) = b0 + Σ bᵢ·WOEᵢ, and ln(odds) is its negative, so
base points = Offset − Factor × b0 and each bin scores −Factor × bᵢ × WOEᵢ, rounded to integers.

*Where:* `scorecard/scorecard.py`, report §4.1.
*Numbers:* b0 = −1.8348, base points 566.50 → 567, score range 527–620, integer-score AUC test
0.6472 / OOT 0.6504.

### 8. How is the cut-off chosen? Why do the profit-maximising and lowest-bad-rate cut-offs differ?

Two numbers answer the business question, and the report leads with them: (a) the loosest cut-off
whose approved bad rate stays under a cap (default 10 %), and (b) the bad rate and net cash at a
target approval rate (default 70 %). The unconstrained profit curve is shown next to them as a
reference. Profit uses realised net cash (`total_pymnt − collection_recovery_fee − funded_amnt`,
nominal and undiscounted). The lowest bad rate is always at the tightest cut-off, but every extra
tranche still earns interest from its goods, so total net cash keeps rising as long as the
marginal tranche's interest covers its losses. Lending Club prices risk, so net cash per loan is
almost flat across score bands and total net cash peaks at "approve everyone": on such a platform
the scorecard's value is admission under a bad-rate cap and tiered pricing, not rejection.

*Where:* `scorecard/strategy.py` (`constrained_cutoffs`, `pick_cutoffs`, `profit_optimum`), report §5.2–5.4.
*Numbers (OOT):* bad rate ≤ 10 % → score ≥ 567, approval 56.2 %, bad rate 9.95 %; at 70 % approval
→ score ≥ 561 (actual 70.85 %), bad rate 11.27 % vs 14.71 % overall, marginal tranche 16.83 %.
Total net cash peaks at 99.68 % approval (128.2 M, same as approve-all); per-loan net cash peaks at
score ≥ 593 / 10.08 % approval (1,127 per loan vs 790 approve-all). With the platform rating the
10 % cap allows 66.95 % approval (score ≥ 563).

### 9. How to read a swap set? What if swap-ins have a higher bad rate than swap-outs?

At equal approval rate, swap-ins are loans the scorecard approves that the baseline rejects,
swap-outs the reverse; both cells hold the same number of loans by construction, so their bad
rates are directly comparable. The baseline is the platform grade, approving from A downwards until
the model's approval count is reached (ties inside the marginal grade broken at random with a fixed
seed). The model adds value when swap-ins have a lower bad rate than swap-outs — those are exactly
the loans the two strategies disagree on. Here the application-only scorecard *loses* that
comparison on OOT: with six stable variables it cannot match a grade that already contains the
bureau data plus pricing. Section 7 flags it as a warning rather than hiding it, and the
with-platform variant shows the gap closing once `sub_grade` is allowed in.

*Where:* `scorecard/strategy.py` (`baseline_order`, `swap_set`), report §5.5; check in §7.
*Numbers (OOT, score ≥ 561, 70.9 % approval):* swap-in 23,905 loans at 19.84 % vs swap-out 23,905
at 17.82 %; approved bad rate model 11.27 % vs grade baseline 10.85 % (+0.42 pp). Test: 17.23 % vs
16.79 % (+0.09 pp). With the platform rating: OOT swap-in 17.22 % vs swap-out 21.34 %, approved
10.34 % vs 10.85 % (−0.51 pp).

### 10. PSI formula and the 0.10 / 0.25 thresholds; score PSI stable but a feature CSI high?

PSI = Σ (actual% − expected%) × ln(actual% / expected%) over bands fixed on the training sample:
10 train-decile score bands for the score, the scorecard's own bins (including the missing bin)
for each feature (that is the CSI). An empty band is floored at 0.01 % so the log is defined.
0.10 / 0.25 are industry conventions (no action / investigate / act), not statistical tests. A
stable score with an unstable feature means the population moved on that feature while the score
absorbed it: look at *which* bin moved. Most such alerts are data-availability shifts — a bureau
field that started being populated — so this project removes them *before* modelling: the
selection step computes the same CSI between the earliest and latest issue year inside train and
drops features above 0.25 (report §2.3b). Section 6 then only reports real drift.

*Where:* `scorecard/select.py` (`time_stability_table`), `scorecard/monitor.py` (`score_psi`, `feature_csi`), report §2.3b, §6.1–6.2.
*Numbers:* 15 features dropped for time instability, e.g. `num_tl_op_past_12m` CSI 4.82 (Missing
51.65 % in 2012 → 0.00 % in 2015), `acc_open_past_24mths` 1.08 (13.8 % → 0.0 %). After that:
score PSI train→test 0.0002, train→OOT 0.0003; every scorecard feature's CSI < 0.10 (max `dti` 0.0116).

### 11. OOT vs a random hold-out; why split by time?

A random hold-out answers "does the model generalise to loans like the ones I trained on"; an
out-of-time sample answers "does it generalise to *next period's* loans", which is what deployment
means. Time brings product-mix and macro drift, so OOT metrics are the honest number to quote.
Here the last six issue months are OOT and everything before them is split stratified at random
into train / test. Restricting the card to one product (36-month) matters for exactly this reason:
60-month loans cannot mature inside the OOT window, so a mixed-term card would see a structurally
different population out of time. Without a date column the pipeline falls back to a stratified
hold-out and says so (UCI).

*Where:* `scorecard/split.py`, report §1.8; vintage curves in §6.3.
*Numbers:* test AUC 0.6473 vs OOT 0.6508 (KS 0.2134 vs 0.2149); OOT = 162,236 loans issued
2015-07 … 2015-12. Vintage: 2012Q1 reaches 5.03 % cumulative default at month 12 and 13.11 % at
month 36; 2015Q4 reaches 5.48 % at month 12 and 14.71 % at month 36.

### 12. With vs without the platform rating — how big is the gap, and should it be used?

Both variants run side by side (`features.use_platform_rating: [false, true]`). Without the rating
the scorecard uses only application data that is stable across years; with it, `sub_grade` enters
as the strongest variable (IV 0.3154, 2.4 times `fico_mid`) while `grade`, `int_rate` and
`installment` fall to the correlation filter. The gain is large on this restricted card — about
+0.04 AUC on OOT and 0.9 pp less bad rate at 70 % approval — because the grade encodes the bureau
history the time filter removed, plus pricing. Whether to use it depends on who owns the decision:
the platform can (it is their own model, and the combined card beats grade alone in the swap set),
a third-party lender should not, because it would be modelling someone else's model and could not
score an applicant without it.

*Where:* `configs/lendingclub.yaml` → `features.use_platform_rating`, report §3 (both variants), §5.6.
*Numbers:* LR AUC / KS test 0.6473 / 0.2134 → 0.6753 / 0.2566, OOT 0.6508 / 0.2149 → 0.6897 /
0.2793; 5-fold CV AUC 0.6416 ± 0.0025 → 0.6704 ± 0.0027. Approved bad rate at 70 % approval:
test 10.46 % → 9.94 % (−0.52 pp), OOT 11.27 % → 10.34 % (−0.93 pp); at 50 % on OOT 9.47 % → 7.74 %.

### 13. What changes for a new dataset?

One adapter (raw file → standard frame: `target`, features, optional `issue_date` /
`loan_amount` / `net_cash` / `event_date`, plus the sample-definition log and field audit) and one
YAML. Nothing in the engine references a column name. A plain CSV with a label column needs no code
at all — the `generic` adapter takes `target_col` and `date_col` from config. The UCI credit-card
dataset is the proof: a 300-line adapter (download, two documented code clean-ups, eleven
behaviour features, protected attributes excluded) and a 30-line YAML, and every section renders —
with the fall-backs the data forces: stratified hold-out instead of OOT, "no cash flow" in the
profit section, a random swap-set baseline.

*Where:* `scorecard/adapters/base.py`, `scorecard/adapters/uci.py`, `configs/uci.yaml`, `examples/uci/`.
*Numbers (UCI):* 30,000 clients, bad rate 22.12 %, 17 of 32 candidates in the card; LR AUC / KS
train 0.7755 / 0.4176, test 0.7667 / 0.4212, hold-out 0.7641 / 0.4020; bad rate ≤ 10 % allows
51.75 % approval on test (score ≥ 568); run time under 20 s.

### 14. How is an agent kept from running wild when it calls this as a skill?

`SKILL.md` lists the inputs, the steps and the guardrails, and the guardrails are enforced by the
CLI, not by the prompt: the input data is never modified; `--dry-run` loads the data, prints the
sample-definition impact table and stops, so the agent has to show the user which rules removed how
many rows before any modelling; a run whose sample bad rate falls outside 1–40 % stops with exit
code 2 (`STOP: …`) unless `--allow-any-bad-rate` is passed explicitly, which catches a wrong
`positive_label` before it produces a confident but meaningless report; an empty sample stops too;
reserved columns can never become features; and section 7's verdicts are printed in the report so
the agent has to relay a 🔴 instead of lowering a threshold. Every run records its config hash,
data file, row count and git commit, so what the agent did can be reproduced.

*Where:* `SKILL.md`, `scorecard/cli.py` (`--dry-run`, `--allow-any-bad-rate`), `scorecard/pipeline.py`
(`check_bad_rate`, `sample_definition_text`), `tests/test_phase2.py::test_guardrails_dry_run_and_bad_rate_stop`.
*Numbers:* the guardrail test labels the synthetic data with the wrong positive value, gets a bad
rate of about 82 % and exit code 2; with the right label the dry run exits 0 and writes
`sample_definition.csv` without a report.
