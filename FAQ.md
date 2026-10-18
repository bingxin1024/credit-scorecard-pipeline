# FAQ — interview questions this project answers

Each answer: a spoken-style reply (≤ 150 words), the file / report section that backs it, and the
actual numbers from `examples/lendingclub/report.md` (Phase 1 run; numbers are copied, never typed
from memory). Questions 8–12 are only partly answerable until Phase 2 ships sections 5–7.

### 1. How is the default label defined? Why drop unmatured and indeterminate loans? What is the performance window?

A loan is bad (1) if its final status is *Charged Off* or *Default*, good (0) if *Fully Paid*.
We only keep loans whose full term has elapsed by the data cut-off (issue month + term ≤ 2018-12),
so every loan has had the same opportunity to go bad — otherwise a 2017 loan that is still
*Current* would look "good" simply because it is young. Loans that are still *Current*, *Late* or
*In Grace Period* at cut-off are indeterminate: we don't know their outcome, and labelling them
either way would bias the bad rate. The performance window is therefore the whole term
(36 or 60 months) — longer than the 12–18 months a bank would use, which is why the bad rate is
higher than a "12-month bad" definition would give.

*Where:* `scorecard/adapters/lendingclub.py` (`transform`, rules 2–3), report §1.2.
*Numbers:* maturity rule removes 1,584,209 loans, terminal-status rule removes
157 indeterminate ones; final sample 633,767 loans, bad rate 14.85%.

### 2. Which leakage fields were removed? Give three and explain why `last_fico_range_*` is leakage.

Anything observed after origination is removed before modelling: (1) `total_pymnt`, `recoveries`,
`out_prncp` — realised repayments and balances, they *are* the outcome; (2) `last_pymnt_d`,
`last_credit_pull_d`, `next_pymnt_d` — payment-timeline fields that reveal whether the loan is
still alive; (3) all `hardship_*`, `settlement_*`, `debt_settlement_flag` — servicing actions that
only happen to distressed loans. `last_fico_range_high/low` is the FICO refreshed at the *last*
credit pull, typically after months of delinquency have already hit the bureau; it encodes the
outcome, not the applicant's risk at application. The field audit classifies every one of the
151 raw columns into one group so nothing slips through by default.

*Where:* `configs/lendingclub.yaml` → `field_groups`, report §1.4 (field audit).
*Numbers:* 31 columns dropped as leakage (groups B/C/D), 99 candidates kept.

### 3. Why is WOE refitted inside every CV fold? What goes wrong if it is done outside?

WOE encoding uses the label: each bin's value is ln(good share / bad share) computed from the
training rows. If you encode the whole training set once and then cross-validate, every
validation fold's labels have already been "seen" by the encoding that scores it, so the CV
estimate is optimistic — exactly like fitting a target encoder on the full data. Refitting the
bins and WOE on the fitting folds only keeps the validation fold honest. The same logic drives
the train / test / OOT design: binning, WOE, selection and the LR are fitted on train only.

*Where:* `scorecard/model.py` → `cross_validate_scorecard`; `scorecard/pipeline.py` → `fit_variant`.
*Numbers:* 5-fold CV AUC 0.6719 ± 0.0026 vs test AUC 0.6744 — close, as they should be.

### 4. How is monotonicity enforced? What happens when a feature is not monotone?

Numeric features are first cut by the backend (toad chi-merge, max 6 bins, ≥ 5 % of rows per
bin). Then the bad rate per bin is checked: if it is not monotone, the adjacent pair that
violates the direction with the smallest bad-rate gap is merged, repeatedly, until the series is
monotone or only 2 bins remain. Categorical features are ordered by training bad rate first, so
their grouping is monotone by construction. Monotone bins give scores that can be explained
("higher DTI never gains points") and are less likely to fit noise. The price is a little IV on
genuinely U-shaped features.

*Where:* `scorecard/binning.py` → `merge_to_monotonic`, report §2.4.
*Numbers:* 0 of 20 scorecard features needed merging; all are monotone after.

### 5. How were the IV thresholds set? What does a very high IV mean?

Rule of thumb: IV < 0.02 carries no usable signal, 0.02–0.1 weak, 0.1–0.3 medium, 0.3–0.5
strong, > 0.5 suspiciously strong. We drop below 0.02 and flag above 0.5 as a leakage suspect but
keep it for a human to decide — on Lending Club no application-time feature comes close, which
is itself a sanity check that the leakage fields were really removed. Thresholds are config
(`select.min_iv`, `select.leakage_iv`), and the selection table records which rule removed each
feature.

*Where:* `scorecard/select.py`, report §2.2–2.3.
*Numbers:* top IV fico_mid = 0.1168; 36 features dropped for IV < 0.02; 0 flagged > 0.5.

### 6. Why ship the logistic regression and not the GBDT? What is the challenger for?

The scorecard is a WOE logistic regression because every point is traceable to one bin of one
variable, it can be implemented in a decision engine as a lookup table, and reason codes for
declines fall out of it. The GBDT (HistGradientBoosting on raw features) is a *challenger*: it
tells us how much signal we leave on the table by insisting on a linear, monotone, binned model.
If the gap were large, we would revisit binning or add interactions; a small gap is evidence the
scorecard is near the ceiling of this data.

*Where:* `scorecard/model.py` → `GBDTChallenger`, report §3.4.
*Numbers:* test AUC LR 0.6744 vs GBDT 0.6941; OOT 0.6750 vs 0.6959.

### 7. 600 points ↔ 20:1 odds, PDO 20: how are offset and factor computed?

Score = Offset + Factor × ln(odds), odds = good:bad. Factor = PDO / ln 2 = 20 / 0.6931 = 28.8539,
so every 20 points double the odds. Offset = 600 − Factor × ln 20 = 600 − 28.8539 × 2.9957 =
513.5614. The LR gives ln(P(bad)/P(good)) = b0 + Σ bᵢ·WOEᵢ, and ln(odds) is its negative, so
base points = Offset − Factor × b0 and each bin scores −Factor × bᵢ × WOEᵢ, rounded to integers.

*Where:* `scorecard/scorecard.py`, report §4.1.
*Numbers:* b0 = -1.7453, base points 563.92 → 564, score range 485–640, integer-score test AUC 0.6740.

### 8. How is the cut-off chosen? Why do the profit-maximising and lowest-bad-rate cut-offs differ?

*Phase 2.* Candidate cut-offs are read off the approval-rate / bad-rate curve (50–90 % approval);
profit uses realised net cash (`total_pymnt − collection_recovery_fee − funded_amnt`). The
lowest bad rate is always at the tightest cut-off, but each extra approved tranche still earns
interest from its goods, so total profit peaks where the marginal tranche's interest just covers
its losses — usually far looser than the bad-rate minimum.

*Where:* `scorecard/strategy.py` (Phase 2), report §5.

### 9. How to read a swap set? What if swap-ins have a higher bad rate than swap-outs?

*Phase 2.* At equal approval rate, swap-ins are loans the scorecard approves that the baseline
(platform grade) rejects; swap-outs the reverse. The model adds value when swap-ins have a lower
bad rate than swap-outs. If it is the other way round, the model is worse than the baseline on
exactly the loans where they disagree — stop and check leakage, segment shift, or the baseline.

*Where:* `scorecard/strategy.py` (Phase 2), report §5.

### 10. PSI formula and the 0.10 / 0.25 thresholds; score PSI stable but a feature CSI high?

*Phase 2.* PSI = Σ (actual% − expected%) × ln(actual% / expected%) over 10 train-decile bands.
0.10 / 0.25 are industry conventions (roughly: no action / investigate / act). A stable score
with one unstable feature means the population moved on that feature while the others offset it;
keep monitoring, but check whether the bin definition still makes sense and whether the feature's
meaning changed (e.g. a bureau field that started being populated).

*Where:* `scorecard/monitor.py` (Phase 2), report §6.

### 11. OOT vs a random hold-out; why split by time?

A random hold-out answers "does the model generalise to loans like the ones I trained on"; an
out-of-time sample answers "does it generalise to *next period's* loans", which is what deployment
means. Time brings product-mix and macro drift, so OOT metrics are usually a bit lower and are the
honest number to quote. Here the last six issue months are OOT and everything before them is
split stratified at random into train / test.

*Where:* `scorecard/split.py`, report §1.8.
*Numbers:* test AUC 0.6744 vs OOT AUC 0.6750; OOT = 162,236 loans issued 2015-07 … 2015-12.

### 12. With vs without the platform rating — how big is the gap, and should it be used?

*Phase 2* runs both variants side by side. Phase 1 deliberately excludes `grade`, `sub_grade`,
`int_rate` and `installment`: they are the platform's own risk model, so a scorecard built on them
mostly re-learns that model and cannot be used by a lender who does not have it. Whether to use it
depends on who owns the decision: a platform may, a third party should not.

*Where:* `configs/lendingclub.yaml` → `features.use_platform_rating`, report §3.

### 13. What changes for a new dataset?

One adapter (raw file → standard frame: `target`, features, optional `issue_date` /
`loan_amount` / `net_cash`, plus the sample-definition log and field audit) and one YAML.
Nothing in the engine references a column name. A plain CSV with a label column needs no code
at all — the `generic` adapter takes `target_col` and `date_col` from config.

*Where:* `scorecard/adapters/base.py`, `scorecard/adapters/generic.py`, `configs/`.

### 14. How is an agent kept from running wild when it calls this as a skill?

*Phase 3* (`SKILL.md`). The CLI never modifies input data, prints the sample-definition impact
table first, and the adapter refuses to continue when the sample is empty; the skill adds the
rule to stop and ask when the bad rate falls outside 1–40 %, and runs are reproducible from the
config hash recorded in the report.
