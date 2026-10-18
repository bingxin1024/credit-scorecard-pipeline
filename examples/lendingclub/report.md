# Lending Club 信用评分卡与策略分析报告

- **数据**：data/raw/accepted_2007_to_2018Q4.csv.gz（633,767 行）
- **config hash**：c5a5c873cbd5
- **git commit**：ca6f10e
- **生成时间**：2026-10-19 01:13:22

- **样本**：633,767 笔，bad rate 14.85%
- **入模特征**：20 / 99
- **train AUC / KS**：0.6733 / 0.2467
- **test AUC / KS**：0.6744 / 0.2513
- **OOT AUC / KS**：0.6750 / 0.2526

> **运行警告**
> - 到期规则使不同期限的完整放款窗口不同（36 期贷款 issue_d <= 2015-12，60 期贷款 issue_d <= 2013-12）：最后几个月只有短期限贷款，train 与 OOT 的 term 构成不同（DECISIONS.md D5；可用 terms_allowed 只建单一期限的卡）

## 1. 样本与数据概况

_数据来源、样本定义的每条规则及其影响、字段审计（哪些字段因为是贷后信息而剔除）、缺失率与 bad rate 随时间的变化。_

### 1.1 数据来源与规模

- **数据来源**：data/raw/accepted_2007_to_2018Q4.csv.gz
- **adapter**：lendingclub
- **原始行 × 列**：2,260,701 × 151
- **样本定义后行数**：633,767
- **候选特征数**：99（其中类别型 8）
- **bad rate**：14.85%（bad = 94,115）
- **issue_date 范围**：2012-01 ~ 2015-12

### 1.2 样本定义影响表

| 步骤 | 规则 | 说明 | 剔除行数 | 剩余行数 | 剩余 bad rate |
|---|---|---|---|---|---|
| 1 | drop_summary_rows | 剔除文件末尾的汇总行（id 非数字或 loan_status 为空） | 33 | 2,260,668 | 19.96% |
| 2 | credit_policy | 剔除 loan_status 以 “Does not meet the credit policy” 开头的贷款（早期不同准入政策） | 2,749 | 2,257,919 | 19.96% |
| 3 | maturity | 到期筛选：issue_d + term 个月 <= 数据截止月 2018-12（保证 performance window 完整） | 1,584,209 | 673,710 | 14.81% |
| 4 | terminal_status | 终态映射：Charged Off / Default → 1；Fully Paid → 0；Current / Late / In Grace Period 为 indeterminate，剔除 | 157 | 673,553 | 14.81% |
| 5 | min_issue_date | 只保留 issue_d >= 2012-01（2007–2011 量小且产品、客群与后期不同） | 39,786 | 633,767 | 14.85% |
| 6 | final_sample | 最终样本量与 bad rate | 0 | 633,767 | 14.85% |

_bad rate 按剩余行中已有终态（Charged Off / Default / Fully Paid）的贷款计算；终态映射之前的行里还包含 Current 等未终态贷款，不计入分母。_

### 1.3 min_issue_date 之前：bad rate 按 issue 年（到期 + 终态样本）

| issue 年 | 贷款数 | bad rate | 60 期占比 |
|---|---|---|---|
| 2007 | 251 | 17.93% | 0.00% |
| 2008 | 1,562 | 15.81% | 0.00% |
| 2009 | 4,716 | 12.60% | 0.00% |
| 2010 | 11,536 | 12.89% | 26.61% |
| 2011 | 21,721 | 15.18% | 35.08% |
| 2012 | 53,367 | 16.20% | 18.55% |
| 2013 | 134,804 | 15.60% | 25.51% |
| 2014 | 162,570 | 13.73% | 0.00% |
| 2015 | 283,026 | 14.89% | 0.00% |

_min_issue_date 规则只保留 issue_date >= 2012-01 的依据：早期年份样本少、产品结构（60 期占比）和 bad rate 与后期不同。_

![图 1.1 min_issue_date 过滤前的 bad rate 按 issue 年](figures/01_bad_rate_by_year_prefilter.png)

_图 1.1 min_issue_date 过滤前的 bad rate 按 issue 年_

### 1.4 字段审计：按分组汇总

| 分组 | 字段数 | 处理 |
|---|---|---|
| A 目标来源 | 1 | 保留列（非特征） 1 |
| B 贷后回款 / 余额（泄漏，剔除） | 13 | 保留列（非特征） 7, 剔除 6 |
| C 贷后信用更新（泄漏，剔除） | 2 | 剔除 2 |
| D 困难 / 和解 / 还款计划（泄漏，剔除） | 23 | 剔除 23 |
| E 无信息 / 标识 / 自由文本（剔除） | 8 | 剔除 8 |
| F 投资人侧（剔除） | 1 | 剔除 1 |
| G 平台评级（use_platform_rating 开关） | 4 | 平台评级（开关） 4 |
| H 联合申请字段 | 16 | 入模候选 15, 派生后剔除原列 1 |
| I 申请时可得（候选特征） | 83 | 入模候选 78, 派生后剔除原列 4, 保留列（非特征） 1 |
| X adapter 派生变量 | 6 | 入模候选 6 |

### 字段审计清单（全部原始字段 + 派生变量）

| 字段 | 分组 | 处理 | 原因 |
|---|---|---|---|
| id | E 无信息 / 标识 / 自由文本（剔除） | 剔除 | 标识 / 自由文本 / 无信息 |
| member_id | E 无信息 / 标识 / 自由文本（剔除） | 剔除 | 标识 / 自由文本 / 无信息 |
| loan_amnt | I 申请时可得（候选特征） | 入模候选 | 申请时可得 |
| funded_amnt | I 申请时可得（候选特征） | 入模候选 | 申请时可得 |
| funded_amnt_inv | F 投资人侧（剔除） | 剔除 | 投资人侧 |
| term | I 申请时可得（候选特征） | 入模候选 | 申请时可得 |
| int_rate | G 平台评级（use_platform_rating 开关） | 平台评级（开关） | 平台评级，按 use_platform_rating 开关 |
| installment | G 平台评级（use_platform_rating 开关） | 平台评级（开关） | 平台评级，按 use_platform_rating 开关 |
| grade | G 平台评级（use_platform_rating 开关） | 平台评级（开关） | 平台评级，按 use_platform_rating 开关 |
| sub_grade | G 平台评级（use_platform_rating 开关） | 平台评级（开关） | 平台评级，按 use_platform_rating 开关 |
| emp_title | E 无信息 / 标识 / 自由文本（剔除） | 剔除 | 标识 / 自由文本 / 无信息 |
| emp_length | I 申请时可得（候选特征） | 派生后剔除原列 | → emp_length_years（'10+ years' → 10，'< 1 year' → 0，n/a → NaN） |
| home_ownership | I 申请时可得（候选特征） | 入模候选 | 申请时可得 |
| annual_inc | I 申请时可得（候选特征） | 入模候选 | 申请时可得 |
| verification_status | I 申请时可得（候选特征） | 入模候选 | 申请时可得 |
| issue_d | I 申请时可得（候选特征） | 保留列（非特征） | issue_date：时间切分 / OOT / vintage，不作为特征 |
| loan_status | A 目标来源 | 保留列（非特征） | → target（终态映射） |
| pymnt_plan | D 困难 / 和解 / 还款计划（泄漏，剔除） | 剔除 | 困难 / 和解 / 还款计划，贷后信息 |
| url | E 无信息 / 标识 / 自由文本（剔除） | 剔除 | 标识 / 自由文本 / 无信息 |
| desc | E 无信息 / 标识 / 自由文本（剔除） | 剔除 | 标识 / 自由文本 / 无信息 |
| purpose | I 申请时可得（候选特征） | 入模候选 | 申请时可得 |
| title | E 无信息 / 标识 / 自由文本（剔除） | 剔除 | 标识 / 自由文本 / 无信息 |
| zip_code | E 无信息 / 标识 / 自由文本（剔除） | 剔除 | 标识 / 自由文本 / 无信息 |
| addr_state | I 申请时可得（候选特征） | 入模候选 | 申请时可得 |
| dti | I 申请时可得（候选特征） | 入模候选 | 申请时可得 |
| delinq_2yrs | I 申请时可得（候选特征） | 入模候选 | 申请时可得 |
| earliest_cr_line | I 申请时可得（候选特征） | 派生后剔除原列 | → credit_hist_months = months(issue_d − earliest_cr_line) |
| fico_range_low | I 申请时可得（候选特征） | 派生后剔除原列 | → fico_mid = (fico_range_low + fico_range_high) / 2 |
| fico_range_high | I 申请时可得（候选特征） | 派生后剔除原列 | → fico_mid |
| inq_last_6mths | I 申请时可得（候选特征） | 入模候选 | 申请时可得 |
| mths_since_last_delinq | I 申请时可得（候选特征） | 入模候选 | 申请时可得 |
| mths_since_last_record | I 申请时可得（候选特征） | 入模候选 | 申请时可得 |
| open_acc | I 申请时可得（候选特征） | 入模候选 | 申请时可得 |
| pub_rec | I 申请时可得（候选特征） | 入模候选 | 申请时可得 |
| revol_bal | I 申请时可得（候选特征） | 入模候选 | 申请时可得 |
| revol_util | I 申请时可得（候选特征） | 入模候选 | 申请时可得 |
| total_acc | I 申请时可得（候选特征） | 入模候选 | 申请时可得 |
| initial_list_status | I 申请时可得（候选特征） | 入模候选 | 申请时可得 |
| out_prncp | B 贷后回款 / 余额（泄漏，剔除） | 剔除 | 贷后回款 / 余额，泄漏 |
| out_prncp_inv | B 贷后回款 / 余额（泄漏，剔除） | 剔除 | 贷后回款 / 余额，泄漏 |
| total_pymnt | B 贷后回款 / 余额（泄漏，剔除） | 保留列（非特征） | net_cash input (strategy layer only) |
| total_pymnt_inv | B 贷后回款 / 余额（泄漏，剔除） | 剔除 | 贷后回款 / 余额，泄漏 |
| total_rec_prncp | B 贷后回款 / 余额（泄漏，剔除） | 保留列（非特征） | net_cash consistency check only |
| total_rec_int | B 贷后回款 / 余额（泄漏，剔除） | 保留列（非特征） | net_cash consistency check only |
| total_rec_late_fee | B 贷后回款 / 余额（泄漏，剔除） | 保留列（非特征） | net_cash consistency check only |
| recoveries | B 贷后回款 / 余额（泄漏，剔除） | 保留列（非特征） | net_cash consistency check only |
| collection_recovery_fee | B 贷后回款 / 余额（泄漏，剔除） | 保留列（非特征） | net_cash input (strategy layer only) |
| last_pymnt_d | B 贷后回款 / 余额（泄漏，剔除） | 保留列（非特征） | event_date for vintage curves (monitor layer only) |
| last_pymnt_amnt | B 贷后回款 / 余额（泄漏，剔除） | 剔除 | 贷后回款 / 余额，泄漏 |
| next_pymnt_d | B 贷后回款 / 余额（泄漏，剔除） | 剔除 | 贷后回款 / 余额，泄漏 |
| last_credit_pull_d | B 贷后回款 / 余额（泄漏，剔除） | 剔除 | 贷后回款 / 余额，泄漏 |
| last_fico_range_high | C 贷后信用更新（泄漏，剔除） | 剔除 | 贷后信用更新，泄漏 |
| last_fico_range_low | C 贷后信用更新（泄漏，剔除） | 剔除 | 贷后信用更新，泄漏 |
| collections_12_mths_ex_med | I 申请时可得（候选特征） | 入模候选 | 申请时可得 |
| mths_since_last_major_derog | I 申请时可得（候选特征） | 入模候选 | 申请时可得 |
| policy_code | E 无信息 / 标识 / 自由文本（剔除） | 剔除 | 标识 / 自由文本 / 无信息 |
| application_type | I 申请时可得（候选特征） | 入模候选 | 申请时可得 |
| annual_inc_joint | H 联合申请字段 | 入模候选 | 联合申请字段，缺失 = 非联合申请 |
| dti_joint | H 联合申请字段 | 入模候选 | 联合申请字段，缺失 = 非联合申请 |
| verification_status_joint | H 联合申请字段 | 入模候选 | 联合申请字段，缺失 = 非联合申请 |
| acc_now_delinq | I 申请时可得（候选特征） | 入模候选 | 申请时可得 |
| tot_coll_amt | I 申请时可得（候选特征） | 入模候选 | 申请时可得 |
| tot_cur_bal | I 申请时可得（候选特征） | 入模候选 | 申请时可得 |
| open_acc_6m | I 申请时可得（候选特征） | 入模候选 | 申请时可得 |
| open_act_il | I 申请时可得（候选特征） | 入模候选 | 申请时可得 |
| open_il_12m | I 申请时可得（候选特征） | 入模候选 | 申请时可得 |
| open_il_24m | I 申请时可得（候选特征） | 入模候选 | 申请时可得 |
| mths_since_rcnt_il | I 申请时可得（候选特征） | 入模候选 | 申请时可得 |
| total_bal_il | I 申请时可得（候选特征） | 入模候选 | 申请时可得 |
| il_util | I 申请时可得（候选特征） | 入模候选 | 申请时可得 |
| open_rv_12m | I 申请时可得（候选特征） | 入模候选 | 申请时可得 |
| open_rv_24m | I 申请时可得（候选特征） | 入模候选 | 申请时可得 |
| max_bal_bc | I 申请时可得（候选特征） | 入模候选 | 申请时可得 |
| all_util | I 申请时可得（候选特征） | 入模候选 | 申请时可得 |
| total_rev_hi_lim | I 申请时可得（候选特征） | 入模候选 | 申请时可得 |
| inq_fi | I 申请时可得（候选特征） | 入模候选 | 申请时可得 |
| total_cu_tl | I 申请时可得（候选特征） | 入模候选 | 申请时可得 |
| inq_last_12m | I 申请时可得（候选特征） | 入模候选 | 申请时可得 |
| acc_open_past_24mths | I 申请时可得（候选特征） | 入模候选 | 申请时可得 |
| avg_cur_bal | I 申请时可得（候选特征） | 入模候选 | 申请时可得 |
| bc_open_to_buy | I 申请时可得（候选特征） | 入模候选 | 申请时可得 |
| bc_util | I 申请时可得（候选特征） | 入模候选 | 申请时可得 |
| chargeoff_within_12_mths | I 申请时可得（候选特征） | 入模候选 | 申请时可得 |
| delinq_amnt | I 申请时可得（候选特征） | 入模候选 | 申请时可得 |
| mo_sin_old_il_acct | I 申请时可得（候选特征） | 入模候选 | 申请时可得 |
| mo_sin_old_rev_tl_op | I 申请时可得（候选特征） | 入模候选 | 申请时可得 |
| mo_sin_rcnt_rev_tl_op | I 申请时可得（候选特征） | 入模候选 | 申请时可得 |
| mo_sin_rcnt_tl | I 申请时可得（候选特征） | 入模候选 | 申请时可得 |
| mort_acc | I 申请时可得（候选特征） | 入模候选 | 申请时可得 |
| mths_since_recent_bc | I 申请时可得（候选特征） | 入模候选 | 申请时可得 |
| mths_since_recent_bc_dlq | I 申请时可得（候选特征） | 入模候选 | 申请时可得 |
| mths_since_recent_inq | I 申请时可得（候选特征） | 入模候选 | 申请时可得 |
| mths_since_recent_revol_delinq | I 申请时可得（候选特征） | 入模候选 | 申请时可得 |
| num_accts_ever_120_pd | I 申请时可得（候选特征） | 入模候选 | 申请时可得 |
| num_actv_bc_tl | I 申请时可得（候选特征） | 入模候选 | 申请时可得 |
| num_actv_rev_tl | I 申请时可得（候选特征） | 入模候选 | 申请时可得 |
| num_bc_sats | I 申请时可得（候选特征） | 入模候选 | 申请时可得 |
| num_bc_tl | I 申请时可得（候选特征） | 入模候选 | 申请时可得 |
| num_il_tl | I 申请时可得（候选特征） | 入模候选 | 申请时可得 |
| num_op_rev_tl | I 申请时可得（候选特征） | 入模候选 | 申请时可得 |
| num_rev_accts | I 申请时可得（候选特征） | 入模候选 | 申请时可得 |
| num_rev_tl_bal_gt_0 | I 申请时可得（候选特征） | 入模候选 | 申请时可得 |
| num_sats | I 申请时可得（候选特征） | 入模候选 | 申请时可得 |
| num_tl_120dpd_2m | I 申请时可得（候选特征） | 入模候选 | 申请时可得 |
| num_tl_30dpd | I 申请时可得（候选特征） | 入模候选 | 申请时可得 |
| num_tl_90g_dpd_24m | I 申请时可得（候选特征） | 入模候选 | 申请时可得 |
| num_tl_op_past_12m | I 申请时可得（候选特征） | 入模候选 | 申请时可得 |
| pct_tl_nvr_dlq | I 申请时可得（候选特征） | 入模候选 | 申请时可得 |
| percent_bc_gt_75 | I 申请时可得（候选特征） | 入模候选 | 申请时可得 |
| pub_rec_bankruptcies | I 申请时可得（候选特征） | 入模候选 | 申请时可得 |
| tax_liens | I 申请时可得（候选特征） | 入模候选 | 申请时可得 |
| tot_hi_cred_lim | I 申请时可得（候选特征） | 入模候选 | 申请时可得 |
| total_bal_ex_mort | I 申请时可得（候选特征） | 入模候选 | 申请时可得 |
| total_bc_limit | I 申请时可得（候选特征） | 入模候选 | 申请时可得 |
| total_il_high_credit_limit | I 申请时可得（候选特征） | 入模候选 | 申请时可得 |
| revol_bal_joint | H 联合申请字段 | 入模候选 | 联合申请字段，缺失 = 非联合申请 |
| sec_app_fico_range_low | H 联合申请字段 | 入模候选 | 联合申请字段，缺失 = 非联合申请 |
| sec_app_fico_range_high | H 联合申请字段 | 入模候选 | 联合申请字段，缺失 = 非联合申请 |
| sec_app_earliest_cr_line | H 联合申请字段 | 派生后剔除原列 | → sec_app_credit_hist_months |
| sec_app_inq_last_6mths | H 联合申请字段 | 入模候选 | 联合申请字段，缺失 = 非联合申请 |
| sec_app_mort_acc | H 联合申请字段 | 入模候选 | 联合申请字段，缺失 = 非联合申请 |
| sec_app_open_acc | H 联合申请字段 | 入模候选 | 联合申请字段，缺失 = 非联合申请 |
| sec_app_revol_util | H 联合申请字段 | 入模候选 | 联合申请字段，缺失 = 非联合申请 |
| sec_app_open_act_il | H 联合申请字段 | 入模候选 | 联合申请字段，缺失 = 非联合申请 |
| sec_app_num_rev_accts | H 联合申请字段 | 入模候选 | 联合申请字段，缺失 = 非联合申请 |
| sec_app_chargeoff_within_12_mths | H 联合申请字段 | 入模候选 | 联合申请字段，缺失 = 非联合申请 |
| sec_app_collections_12_mths_ex_med | H 联合申请字段 | 入模候选 | 联合申请字段，缺失 = 非联合申请 |
| sec_app_mths_since_last_major_derog | H 联合申请字段 | 入模候选 | 联合申请字段，缺失 = 非联合申请 |
| hardship_flag | D 困难 / 和解 / 还款计划（泄漏，剔除） | 剔除 | 困难 / 和解 / 还款计划，贷后信息 |
| hardship_type | D 困难 / 和解 / 还款计划（泄漏，剔除） | 剔除 | 困难 / 和解 / 还款计划，贷后信息 |
| hardship_reason | D 困难 / 和解 / 还款计划（泄漏，剔除） | 剔除 | 困难 / 和解 / 还款计划，贷后信息 |
| hardship_status | D 困难 / 和解 / 还款计划（泄漏，剔除） | 剔除 | 困难 / 和解 / 还款计划，贷后信息 |
| deferral_term | D 困难 / 和解 / 还款计划（泄漏，剔除） | 剔除 | 困难 / 和解 / 还款计划，贷后信息 |
| hardship_amount | D 困难 / 和解 / 还款计划（泄漏，剔除） | 剔除 | 困难 / 和解 / 还款计划，贷后信息 |
| hardship_start_date | D 困难 / 和解 / 还款计划（泄漏，剔除） | 剔除 | 困难 / 和解 / 还款计划，贷后信息 |
| hardship_end_date | D 困难 / 和解 / 还款计划（泄漏，剔除） | 剔除 | 困难 / 和解 / 还款计划，贷后信息 |
| payment_plan_start_date | D 困难 / 和解 / 还款计划（泄漏，剔除） | 剔除 | 困难 / 和解 / 还款计划，贷后信息 |
| hardship_length | D 困难 / 和解 / 还款计划（泄漏，剔除） | 剔除 | 困难 / 和解 / 还款计划，贷后信息 |
| hardship_dpd | D 困难 / 和解 / 还款计划（泄漏，剔除） | 剔除 | 困难 / 和解 / 还款计划，贷后信息 |
| hardship_loan_status | D 困难 / 和解 / 还款计划（泄漏，剔除） | 剔除 | 困难 / 和解 / 还款计划，贷后信息 |
| orig_projected_additional_accrued_interest | D 困难 / 和解 / 还款计划（泄漏，剔除） | 剔除 | 困难 / 和解 / 还款计划，贷后信息 |
| hardship_payoff_balance_amount | D 困难 / 和解 / 还款计划（泄漏，剔除） | 剔除 | 困难 / 和解 / 还款计划，贷后信息 |
| hardship_last_payment_amount | D 困难 / 和解 / 还款计划（泄漏，剔除） | 剔除 | 困难 / 和解 / 还款计划，贷后信息 |
| disbursement_method | I 申请时可得（候选特征） | 入模候选 | 申请时可得 |
| debt_settlement_flag | D 困难 / 和解 / 还款计划（泄漏，剔除） | 剔除 | 困难 / 和解 / 还款计划，贷后信息 |
| debt_settlement_flag_date | D 困难 / 和解 / 还款计划（泄漏，剔除） | 剔除 | 困难 / 和解 / 还款计划，贷后信息 |
| settlement_status | D 困难 / 和解 / 还款计划（泄漏，剔除） | 剔除 | 困难 / 和解 / 还款计划，贷后信息 |
| settlement_date | D 困难 / 和解 / 还款计划（泄漏，剔除） | 剔除 | 困难 / 和解 / 还款计划，贷后信息 |
| settlement_amount | D 困难 / 和解 / 还款计划（泄漏，剔除） | 剔除 | 困难 / 和解 / 还款计划，贷后信息 |
| settlement_percentage | D 困难 / 和解 / 还款计划（泄漏，剔除） | 剔除 | 困难 / 和解 / 还款计划，贷后信息 |
| settlement_term | D 困难 / 和解 / 还款计划（泄漏，剔除） | 剔除 | 困难 / 和解 / 还款计划，贷后信息 |
| fico_mid | X adapter 派生变量 | 入模候选 | (fico_range_low + fico_range_high) / 2 |
| credit_hist_months | X adapter 派生变量 | 入模候选 | months(issue_d − earliest_cr_line) |
| emp_length_years | X adapter 派生变量 | 入模候选 | emp_length 解析为年数 |
| log_annual_inc | X adapter 派生变量 | 入模候选 | log1p(annual_inc) |
| loan_to_inc | X adapter 派生变量 | 入模候选 | loan_amnt / annual_inc（annual_inc = 0 → NaN） |
| sec_app_credit_hist_months | X adapter 派生变量 | 入模候选 | months(issue_d − sec_app_earliest_cr_line) |

### 1.5 缺失率 Top 20（候选特征，全样本）

| 特征 | 类型 | 缺失率 | 取值数 |
|---|---|---|---|
| sec_app_open_acc | numeric | 100.00% | 0 |
| sec_app_credit_hist_months | numeric | 100.00% | 0 |
| sec_app_mths_since_last_major_derog | numeric | 100.00% | 0 |
| sec_app_collections_12_mths_ex_med | numeric | 100.00% | 0 |
| sec_app_chargeoff_within_12_mths | numeric | 100.00% | 0 |
| sec_app_num_rev_accts | numeric | 100.00% | 0 |
| sec_app_fico_range_high | numeric | 100.00% | 0 |
| sec_app_revol_util | numeric | 100.00% | 0 |
| revol_bal_joint | numeric | 100.00% | 0 |
| sec_app_fico_range_low | numeric | 100.00% | 0 |
| sec_app_open_act_il | numeric | 100.00% | 0 |
| sec_app_mort_acc | numeric | 100.00% | 0 |
| sec_app_inq_last_6mths | numeric | 100.00% | 0 |
| dti_joint | numeric | 99.96% | 225 |
| annual_inc_joint | numeric | 99.96% | 183 |
| verification_status_joint | categorical | 99.96% | 1 |
| il_util | numeric | 97.98% | 155 |
| mths_since_rcnt_il | numeric | 97.72% | 193 |
| open_acc_6m | numeric | 97.65% | 13 |
| open_rv_24m | numeric | 97.65% | 28 |

![图 1.2 bad rate 按 issue 季度（最终样本）](figures/02_bad_rate_by_quarter.png)

_图 1.2 bad rate 按 issue 季度（最终样本）_

### 1.6 bad rate 按 issue 季度

| 季度 | 贷款数 | bad 数 | bad rate |
|---|---|---|---|
| 2012Q1 | 8,076 | 1,304 | 16.15% |
| 2012Q2 | 10,447 | 1,779 | 17.03% |
| 2012Q3 | 16,133 | 2,654 | 16.45% |
| 2012Q4 | 18,711 | 2,907 | 15.54% |
| 2013Q1 | 22,706 | 3,410 | 15.02% |
| 2013Q2 | 30,668 | 4,985 | 16.25% |
| 2013Q3 | 37,571 | 5,847 | 15.56% |
| 2013Q4 | 43,859 | 6,782 | 15.46% |
| 2014Q1 | 34,074 | 4,384 | 12.87% |
| 2014Q2 | 37,881 | 5,131 | 13.55% |
| 2014Q3 | 40,595 | 5,533 | 13.63% |
| 2014Q4 | 50,020 | 7,267 | 14.53% |
| 2015Q1 | 56,568 | 8,391 | 14.83% |
| 2015Q2 | 64,222 | 9,878 | 15.38% |
| 2015Q3 | 73,567 | 10,725 | 14.58% |
| 2015Q4 | 88,669 | 13,138 | 14.82% |

### 1.7 缺失率按 issue 年（总缺失率 > 5% 的特征）

| 特征 | 总缺失率 | 2012 | 2013 | 2014 | 2015 |
|---|---|---|---|---|---|
| sec_app_mths_since_last_major_derog | 100.0% | 100.0% | 100.0% | 100.0% | 100.0% |
| sec_app_num_rev_accts | 100.0% | 100.0% | 100.0% | 100.0% | 100.0% |
| sec_app_chargeoff_within_12_mths | 100.0% | 100.0% | 100.0% | 100.0% | 100.0% |
| sec_app_credit_hist_months | 100.0% | 100.0% | 100.0% | 100.0% | 100.0% |
| sec_app_open_acc | 100.0% | 100.0% | 100.0% | 100.0% | 100.0% |
| sec_app_open_act_il | 100.0% | 100.0% | 100.0% | 100.0% | 100.0% |
| sec_app_revol_util | 100.0% | 100.0% | 100.0% | 100.0% | 100.0% |
| sec_app_fico_range_high | 100.0% | 100.0% | 100.0% | 100.0% | 100.0% |
| sec_app_inq_last_6mths | 100.0% | 100.0% | 100.0% | 100.0% | 100.0% |
| revol_bal_joint | 100.0% | 100.0% | 100.0% | 100.0% | 100.0% |
| sec_app_mort_acc | 100.0% | 100.0% | 100.0% | 100.0% | 100.0% |
| sec_app_fico_range_low | 100.0% | 100.0% | 100.0% | 100.0% | 100.0% |
| sec_app_collections_12_mths_ex_med | 100.0% | 100.0% | 100.0% | 100.0% | 100.0% |
| dti_joint | 100.0% | 100.0% | 100.0% | 100.0% | 99.9% |
| annual_inc_joint | 100.0% | 100.0% | 100.0% | 100.0% | 99.9% |
| verification_status_joint | 100.0% | 100.0% | 100.0% | 100.0% | 99.9% |
| il_util | 98.0% | 100.0% | 100.0% | 100.0% | 95.5% |
| mths_since_rcnt_il | 97.7% | 100.0% | 100.0% | 100.0% | 94.9% |
| open_acc_6m | 97.7% | 100.0% | 100.0% | 100.0% | 94.7% |
| open_rv_24m | 97.7% | 100.0% | 100.0% | 100.0% | 94.7% |
| open_rv_12m | 97.7% | 100.0% | 100.0% | 100.0% | 94.7% |
| total_bal_il | 97.7% | 100.0% | 100.0% | 100.0% | 94.7% |
| open_il_12m | 97.7% | 100.0% | 100.0% | 100.0% | 94.7% |
| open_act_il | 97.7% | 100.0% | 100.0% | 100.0% | 94.7% |
| open_il_24m | 97.7% | 100.0% | 100.0% | 100.0% | 94.7% |
| all_util | 97.7% | 100.0% | 100.0% | 100.0% | 94.7% |
| inq_last_12m | 97.7% | 100.0% | 100.0% | 100.0% | 94.7% |
| total_cu_tl | 97.7% | 100.0% | 100.0% | 100.0% | 94.7% |
| inq_fi | 97.7% | 100.0% | 100.0% | 100.0% | 94.7% |
| max_bal_bc | 97.7% | 100.0% | 100.0% | 100.0% | 94.7% |
| mths_since_last_record | 84.1% | 97.2% | 88.1% | 81.1% | 81.3% |
| mths_since_recent_bc_dlq | 75.6% | 87.4% | 77.7% | 73.1% | 73.8% |
| mths_since_last_major_derog | 73.9% | 89.9% | 79.9% | 70.7% | 69.8% |
| mths_since_recent_revol_delinq | 65.7% | 73.9% | 69.9% | 63.5% | 63.5% |
| mths_since_last_delinq | 51.0% | 58.8% | 56.5% | 48.9% | 48.0% |
| mths_since_recent_inq | 11.8% | 24.9% | 10.8% | 9.5% | 11.0% |
| mo_sin_old_il_acct | 7.9% | 54.2% | 3.7% | 3.6% | 3.5% |
| num_tl_120dpd_2m | 7.7% | 52.0% | 0.2% | 4.0% | 5.0% |
| emp_length_years | 5.8% | 3.6% | 4.4% | 5.9% | 6.7% |

_征信类字段（num_* / mo_sin_* / il / rv 等）在早期年份缺失率极高；select 步骤按 max_missing 阈值处理。_

### 1.8 样本切分

| 样本 | 行数 | 占比 | bad rate | issue 起 | issue 止 |
|---|---|---|---|---|---|
| train | 330,071 | 52.08% | 14.90% | 2012-01 | 2015-06 |
| test | 141,460 | 22.32% | 14.90% | 2012-01 | 2015-06 |
| oot | 162,236 | 25.60% | 14.71% | 2015-07 | 2015-12 |

_按 issue_date 切 OOT（最后 6 个月：2015-07 ~ 2015-12），其余按 target 分层随机切 train / test；train_ratio = 0.7，random_state = 42。分箱、WOE、特征选择与模型只在 train 上拟合。_

### 1.9 adapter 说明

- net_cash 一致性检验（Charged Off 样本 94,115 笔）：total_pymnt 与 total_rec_prncp + total_rec_int + total_rec_late_fee + recoveries 相差 < 1 的占 100.00%（最大绝对差 0.01）；不含 recoveries 时占 22.54%（最大绝对差 39,444）→ total_pymnt 已包含 recoveries。
- net_cash = total_pymnt - collection_recovery_fee - funded_amnt（实际回款减放款本金；仅策略层使用）
- 占比 < 1% 的类别并入 OTHER_RARE（按全样本频率计算，不使用标签）：purpose: car, moving, vacation, house, wedding, renewable_energy, educational；home_ownership: OTHER, NONE, ANY；addr_state: KY, OK, KS, AR, UT, NM, HI, NH, WV, RI, MS, MT, DC, DE, AK, WY, SD, VT, NE, ME, ND, ID, IA
- 终态映射时剔除的 indeterminate 状态：Current 78，Late (31-120 days) 64，In Grace Period 10，Late (16-30 days) 5

> **adapter / 切分警告**
> - 到期规则使不同期限的完整放款窗口不同（36 期贷款 issue_d <= 2015-12，60 期贷款 issue_d <= 2013-12）：最后几个月只有短期限贷款，train 与 OOT 的 term 构成不同（DECISIONS.md D5；可用 terms_allowed 只建单一期限的卡）

## 2. 分箱与 IV

_在 train 上做单调 WOE 分箱并计算 IV；按缺失率、IV、相关性和系数符号筛选入模特征。_

### [不含平台评级] 2.1 分箱设置

- **分箱后端**：toad（5 个特征库未给出切点，退到 tree：collections_12_mths_ex_med, acc_now_delinq, chargeoff_within_12_mths, delinq_amnt, tax_liens）
- **method / min_samples / max_bins**：chi / 0.05 / 6
- **单调性约束**：是（不单调则合并相邻箱直至单调或退到 2 箱）
- **切点搜索样本量**：200,000（WOE / IV 在全部 train 上计算；筛选阈值也在 train 上评估）
- **WOE 定义**：WOE = ln(good 占比 / bad 占比)，越大越安全；缺失单独一箱
- **候选特征 → 入模特征**：99 → 20

![[不含平台评级] 图 2.1 IV 排名（前 30；绿色 = 入模）](figures/03_iv_ranking_no_platform_rating.png)

_[不含平台评级] 图 2.1 IV 排名（前 30；绿色 = 入模）_

### [不含平台评级] 2.2 IV 排名表（全部候选特征，按 IV 降序）

| 特征 | 类型 | IV | 缺失率（train） | 箱数 | 入模 | 剔除步骤 | 原因 |
|---|---|---|---|---|---|---|---|
| fico_mid | numeric | 0.1168 | 0.00% | 6 | 是 |  | selected |
| loan_to_inc | numeric | 0.0632 | 0.00% | 4 | 是 |  | selected |
| term | numeric | 0.0612 | 0.00% | 2 | 是 |  | selected |
| acc_open_past_24mths | numeric | 0.0607 | 1.58% | 7 | 是 |  | selected |
| bc_open_to_buy | numeric | 0.0583 | 2.54% | 4 | 是 |  | selected |
| annual_inc | numeric | 0.0551 | 0.00% | 6 | 是 |  | selected |
| log_annual_inc | numeric | 0.0551 | 0.00% | 6 | 否 | 3_corr | \|corr\| = 1.00 with annual_inc (IV 0.055) |
| tot_hi_cred_lim | numeric | 0.0520 | 5.84% | 7 | 是 |  | selected |
| avg_cur_bal | numeric | 0.0498 | 5.84% | 7 | 否 | 3_corr | \|corr\| = 0.85 with tot_hi_cred_lim (IV 0.052) |
| num_tl_op_past_12m | numeric | 0.0493 | 5.84% | 6 | 是 |  | selected |
| dti | numeric | 0.0483 | 0.00% | 5 | 是 |  | selected |
| total_bc_limit | numeric | 0.0479 | 1.58% | 5 | 否 | 3_corr | \|corr\| = 0.71 with bc_open_to_buy (IV 0.058) |
| total_rev_hi_lim | numeric | 0.0405 | 5.84% | 7 | 是 |  | selected |
| tot_cur_bal | numeric | 0.0398 | 5.84% | 5 | 否 | 3_corr | \|corr\| = 0.93 with tot_hi_cred_lim (IV 0.052) |
| mo_sin_rcnt_tl | numeric | 0.0370 | 5.84% | 7 | 是 |  | selected |
| percent_bc_gt_75 | numeric | 0.0351 | 2.57% | 6 | 是 |  | selected |
| inq_last_6mths | numeric | 0.0335 | 0.00% | 4 | 是 |  | selected |
| mths_since_recent_inq | numeric | 0.0328 | 11.90% | 7 | 否 | 3_corr | \|corr\| = 0.73 with inq_last_6mths (IV 0.033) |
| mort_acc | numeric | 0.0325 | 1.58% | 6 | 是 |  | selected |
| bc_util | numeric | 0.0323 | 2.61% | 7 | 否 | 3_corr | \|corr\| = 0.79 with percent_bc_gt_75 (IV 0.035) |
| verification_status | categorical | 0.0313 | 0.00% | 3 | 是 |  | selected |
| mo_sin_rcnt_rev_tl_op | numeric | 0.0307 | 5.84% | 7 | 否 | 3_corr | \|corr\| = 0.74 with mo_sin_rcnt_tl (IV 0.037) |
| mths_since_recent_bc | numeric | 0.0288 | 2.45% | 7 | 是 |  | selected |
| home_ownership | categorical | 0.0276 | 0.00% | 3 | 是 |  | selected |
| mo_sin_old_rev_tl_op | numeric | 0.0274 | 5.84% | 6 | 是 |  | selected |
| revol_util | numeric | 0.0233 | 0.05% | 7 | 是 |  | selected |
| num_rev_tl_bal_gt_0 | numeric | 0.0208 | 5.84% | 7 | 是 |  | selected |
| num_actv_rev_tl | numeric | 0.0207 | 5.84% | 7 | 否 | 3_corr | \|corr\| = 0.99 with num_rev_tl_bal_gt_0 (IV 0.021) |
| purpose | categorical | 0.0190 | 0.00% | 3 | 否 | 2_iv | IV 0.0190 < 0.02 |
| credit_hist_months | numeric | 0.0173 | 0.00% | 5 | 否 | 2_iv | IV 0.0173 < 0.02 |
| mo_sin_old_il_acct | numeric | 0.0135 | 9.36% | 4 | 否 | 2_iv | IV 0.0135 < 0.02 |
| emp_length_years | numeric | 0.0116 | 5.33% | 4 | 否 | 2_iv | IV 0.0116 < 0.02 |
| revol_bal | numeric | 0.0100 | 0.00% | 4 | 否 | 2_iv | IV 0.0100 < 0.02 |
| addr_state | categorical | 0.0100 | 0.00% | 4 | 否 | 2_iv | IV 0.0100 < 0.02 |
| initial_list_status | categorical | 0.0081 | 0.00% | 2 | 否 | 2_iv | IV 0.0081 < 0.02 |
| num_op_rev_tl | numeric | 0.0056 | 5.84% | 7 | 否 | 2_iv | IV 0.0056 < 0.02 |
| num_actv_bc_tl | numeric | 0.0053 | 5.84% | 5 | 否 | 2_iv | IV 0.0053 < 0.02 |
| total_bal_ex_mort | numeric | 0.0041 | 1.58% | 5 | 否 | 2_iv | IV 0.0041 < 0.02 |
| total_acc | numeric | 0.0037 | 0.00% | 4 | 否 | 2_iv | IV 0.0037 < 0.02 |
| total_il_high_credit_limit | numeric | 0.0035 | 5.84% | 4 | 否 | 2_iv | IV 0.0035 < 0.02 |
| num_bc_tl | numeric | 0.0034 | 5.84% | 4 | 否 | 2_iv | IV 0.0034 < 0.02 |
| mths_since_last_record | numeric | 0.0030 | 84.98% | 3 | 否 | 1_missing | missing rate 85.0% > 50% |
| num_il_tl | numeric | 0.0026 | 5.84% | 5 | 否 | 2_iv | IV 0.0026 < 0.02 |
| num_accts_ever_120_pd | numeric | 0.0024 | 5.84% | 3 | 否 | 2_iv | IV 0.0024 < 0.02 |
| tot_coll_amt | numeric | 0.0023 | 5.84% | 3 | 否 | 2_iv | IV 0.0023 < 0.02 |
| pub_rec | numeric | 0.0021 | 0.00% | 2 | 否 | 2_iv | IV 0.0021 < 0.02 |
| mths_since_last_major_derog | numeric | 0.0019 | 75.37% | 3 | 否 | 1_missing | missing rate 75.4% > 50% |
| pub_rec_bankruptcies | numeric | 0.0018 | 0.00% | 2 | 否 | 2_iv | IV 0.0018 < 0.02 |
| num_sats | numeric | 0.0018 | 3.37% | 6 | 否 | 2_iv | IV 0.0018 < 0.02 |
| num_tl_120dpd_2m | numeric | 0.0018 | 8.17% | 2 | 否 | 2_iv | IV 0.0018 < 0.02 |
| num_rev_accts | numeric | 0.0016 | 5.84% | 3 | 否 | 2_iv | IV 0.0016 < 0.02 |
| pct_tl_nvr_dlq | numeric | 0.0015 | 5.87% | 3 | 否 | 2_iv | IV 0.0015 < 0.02 |
| num_tl_90g_dpd_24m | numeric | 0.0015 | 5.84% | 3 | 否 | 2_iv | IV 0.0015 < 0.02 |
| loan_amnt | numeric | 0.0011 | 0.00% | 4 | 否 | 2_iv | IV 0.0011 < 0.02 |
| funded_amnt | numeric | 0.0011 | 0.00% | 4 | 否 | 2_iv | IV 0.0011 < 0.02 |
| open_acc | numeric | 0.0011 | 0.00% | 3 | 否 | 2_iv | IV 0.0011 < 0.02 |
| num_tl_30dpd | numeric | 0.0011 | 5.84% | 2 | 否 | 2_iv | IV 0.0011 < 0.02 |
| delinq_2yrs | numeric | 0.0009 | 0.00% | 3 | 否 | 2_iv | IV 0.0009 < 0.02 |
| mths_since_last_delinq | numeric | 0.0006 | 52.06% | 3 | 否 | 1_missing | missing rate 52.1% > 50% |
| num_bc_sats | numeric | 0.0006 | 3.37% | 3 | 否 | 2_iv | IV 0.0006 < 0.02 |
| mths_since_recent_bc_dlq | numeric | 0.0002 | 76.20% | 3 | 否 | 1_missing | missing rate 76.2% > 50% |
| mths_since_recent_revol_delinq | numeric | 0.0002 | 66.50% | 3 | 否 | 1_missing | missing rate 66.5% > 50% |
| collections_12_mths_ex_med | numeric | 0.0000 | 0.00% | 1 | 否 | 2_iv | IV 0.0000 < 0.02 |
| application_type | categorical | 0.0000 | 0.00% | 1 | 否 | 2_iv | IV 0.0000 < 0.02 |
| verification_status_joint | categorical | 0.0000 | 100.00% | 1 | 否 | 1_missing | missing rate 100.0% > 50% |
| dti_joint | numeric | 0.0000 | 100.00% | 2 | 否 | 1_missing | missing rate 100.0% > 50% |
| annual_inc_joint | numeric | 0.0000 | 100.00% | 2 | 否 | 1_missing | missing rate 100.0% > 50% |
| il_util | numeric | 0.0000 | 100.00% | 2 | 否 | 1_missing | missing rate 100.0% > 50% |
| total_bal_il | numeric | 0.0000 | 100.00% | 2 | 否 | 1_missing | missing rate 100.0% > 50% |
| mths_since_rcnt_il | numeric | 0.0000 | 100.00% | 2 | 否 | 1_missing | missing rate 100.0% > 50% |
| open_il_24m | numeric | 0.0000 | 100.00% | 2 | 否 | 1_missing | missing rate 100.0% > 50% |
| open_il_12m | numeric | 0.0000 | 100.00% | 2 | 否 | 1_missing | missing rate 100.0% > 50% |
| open_act_il | numeric | 0.0000 | 100.00% | 2 | 否 | 1_missing | missing rate 100.0% > 50% |
| open_acc_6m | numeric | 0.0000 | 100.00% | 2 | 否 | 1_missing | missing rate 100.0% > 50% |
| acc_now_delinq | numeric | 0.0000 | 0.00% | 1 | 否 | 2_iv | IV 0.0000 < 0.02 |
| chargeoff_within_12_mths | numeric | 0.0000 | 0.00% | 1 | 否 | 2_iv | IV 0.0000 < 0.02 |
| total_cu_tl | numeric | 0.0000 | 100.00% | 2 | 否 | 1_missing | missing rate 100.0% > 50% |
| inq_fi | numeric | 0.0000 | 100.00% | 2 | 否 | 1_missing | missing rate 100.0% > 50% |
| all_util | numeric | 0.0000 | 100.00% | 2 | 否 | 1_missing | missing rate 100.0% > 50% |
| open_rv_24m | numeric | 0.0000 | 100.00% | 2 | 否 | 1_missing | missing rate 100.0% > 50% |
| max_bal_bc | numeric | 0.0000 | 100.00% | 2 | 否 | 1_missing | missing rate 100.0% > 50% |
| delinq_amnt | numeric | 0.0000 | 0.00% | 1 | 否 | 2_iv | IV 0.0000 < 0.02 |
| open_rv_12m | numeric | 0.0000 | 100.00% | 2 | 否 | 1_missing | missing rate 100.0% > 50% |
| inq_last_12m | numeric | 0.0000 | 100.00% | 2 | 否 | 1_missing | missing rate 100.0% > 50% |
| sec_app_fico_range_low | numeric | 0.0000 | 100.00% | 2 | 否 | 1_missing | missing rate 100.0% > 50% |
| revol_bal_joint | numeric | 0.0000 | 100.00% | 2 | 否 | 1_missing | missing rate 100.0% > 50% |
| tax_liens | numeric | 0.0000 | 0.00% | 1 | 否 | 2_iv | IV 0.0000 < 0.02 |
| sec_app_fico_range_high | numeric | 0.0000 | 100.00% | 2 | 否 | 1_missing | missing rate 100.0% > 50% |
| sec_app_inq_last_6mths | numeric | 0.0000 | 100.00% | 2 | 否 | 1_missing | missing rate 100.0% > 50% |
| sec_app_open_acc | numeric | 0.0000 | 100.00% | 2 | 否 | 1_missing | missing rate 100.0% > 50% |
| sec_app_mort_acc | numeric | 0.0000 | 100.00% | 2 | 否 | 1_missing | missing rate 100.0% > 50% |
| sec_app_collections_12_mths_ex_med | numeric | 0.0000 | 100.00% | 2 | 否 | 1_missing | missing rate 100.0% > 50% |
| sec_app_chargeoff_within_12_mths | numeric | 0.0000 | 100.00% | 2 | 否 | 1_missing | missing rate 100.0% > 50% |
| sec_app_num_rev_accts | numeric | 0.0000 | 100.00% | 2 | 否 | 1_missing | missing rate 100.0% > 50% |
| sec_app_open_act_il | numeric | 0.0000 | 100.00% | 2 | 否 | 1_missing | missing rate 100.0% > 50% |
| sec_app_revol_util | numeric | 0.0000 | 100.00% | 2 | 否 | 1_missing | missing rate 100.0% > 50% |
| disbursement_method | categorical | 0.0000 | 0.00% | 1 | 否 | 2_iv | IV 0.0000 < 0.02 |
| sec_app_mths_since_last_major_derog | numeric | 0.0000 | 100.00% | 2 | 否 | 1_missing | missing rate 100.0% > 50% |
| sec_app_credit_hist_months | numeric | 0.0000 | 100.00% | 2 | 否 | 1_missing | missing rate 100.0% > 50% |

### [不含平台评级] 2.3 特征筛选漏斗

| 步骤 | 剔除 | 剩余 |
|---|---|---|
| 候选特征 |  | 99 |
| 缺失率 > 50% | 35 | 64 |
| IV < 0.02 | 36 | 28 |
| \|corr\| > 0.7（保留 IV 高者） | 8 | 20 |
| LR 系数为正（WOE 方向反转） | 0 | 20 |

### [不含平台评级] 2.4 单调性检查（入模特征）

| 特征 | 类型 | 切点来源 | 初始箱数 | 初始单调 | 最终箱数（含缺失箱） | 最终单调 | 最大箱占比 |
|---|---|---|---|---|---|---|---|
| fico_mid | numeric | toad | 6 | 是 | 6 | 是 | 27.09% |
| loan_to_inc | numeric | toad | 4 | 是 | 4 | 是 | 35.56% |
| term | numeric | unique_values | 2 | 是 | 2 | 是 | 90.69% |
| acc_open_past_24mths | numeric | toad | 6 | 是 | 7 | 是 | 26.29% |
| bc_open_to_buy | numeric | toad | 3 | 是 | 4 | 是 | 38.93% |
| annual_inc | numeric | toad | 6 | 是 | 6 | 是 | 24.16% |
| tot_hi_cred_lim | numeric | toad | 6 | 是 | 7 | 是 | 30.03% |
| num_tl_op_past_12m | numeric | toad | 5 | 是 | 6 | 是 | 24.92% |
| dti | numeric | toad | 5 | 是 | 5 | 是 | 25.54% |
| total_rev_hi_lim | numeric | toad | 6 | 是 | 7 | 是 | 31.11% |
| mo_sin_rcnt_tl | numeric | toad | 6 | 是 | 7 | 是 | 29.01% |
| percent_bc_gt_75 | numeric | toad | 5 | 是 | 6 | 是 | 24.83% |
| inq_last_6mths | numeric | toad | 4 | 是 | 4 | 是 | 54.12% |
| mort_acc | numeric | toad | 5 | 是 | 6 | 是 | 41.51% |
| verification_status | categorical | unique_values | 3 | 是 | 3 | 是 | 34.00% |
| mths_since_recent_bc | numeric | toad | 6 | 是 | 7 | 是 | 37.45% |
| home_ownership | categorical | unique_values | 3 | 是 | 3 | 是 | 48.22% |
| mo_sin_old_rev_tl_op | numeric | toad | 5 | 是 | 6 | 是 | 29.66% |
| revol_util | numeric | toad | 6 | 是 | 7 | 是 | 36.94% |
| num_rev_tl_bal_gt_0 | numeric | toad | 6 | 是 | 7 | 是 | 29.22% |

_类别型特征按 train bad rate 排序后再分箱，因此天然单调。数值型不单调时合并相邻箱，直到 bad rate 单调或只剩 2 箱。切点来源 unique_values = 取值数不超过 max_bins、逐值成箱。_

![[不含平台评级] 图 2.2 fico_mid 的 WOE（IV 第 1 名）](figures/04_woe_no_platform_rating_01_fico_mid.png)

_[不含平台评级] 图 2.2 fico_mid 的 WOE（IV 第 1 名）_

![[不含平台评级] 图 2.3 loan_to_inc 的 WOE（IV 第 2 名）](figures/04_woe_no_platform_rating_02_loan_to_inc.png)

_[不含平台评级] 图 2.3 loan_to_inc 的 WOE（IV 第 2 名）_

![[不含平台评级] 图 2.4 term 的 WOE（IV 第 3 名）](figures/04_woe_no_platform_rating_03_term.png)

_[不含平台评级] 图 2.4 term 的 WOE（IV 第 3 名）_

![[不含平台评级] 图 2.5 acc_open_past_24mths 的 WOE（IV 第 4 名）](figures/04_woe_no_platform_rating_04_acc_open_past_24mths.png)

_[不含平台评级] 图 2.5 acc_open_past_24mths 的 WOE（IV 第 4 名）_

![[不含平台评级] 图 2.6 bc_open_to_buy 的 WOE（IV 第 5 名）](figures/04_woe_no_platform_rating_05_bc_open_to_buy.png)

_[不含平台评级] 图 2.6 bc_open_to_buy 的 WOE（IV 第 5 名）_

![[不含平台评级] 图 2.7 annual_inc 的 WOE（IV 第 6 名）](figures/04_woe_no_platform_rating_06_annual_inc.png)

_[不含平台评级] 图 2.7 annual_inc 的 WOE（IV 第 6 名）_

![[不含平台评级] 图 2.8 tot_hi_cred_lim 的 WOE（IV 第 7 名）](figures/04_woe_no_platform_rating_07_tot_hi_cred_lim.png)

_[不含平台评级] 图 2.8 tot_hi_cred_lim 的 WOE（IV 第 7 名）_

![[不含平台评级] 图 2.9 num_tl_op_past_12m 的 WOE（IV 第 8 名）](figures/04_woe_no_platform_rating_08_num_tl_op_past_12m.png)

_[不含平台评级] 图 2.9 num_tl_op_past_12m 的 WOE（IV 第 8 名）_

### [不含平台评级] 分箱表：fico_mid（IV = 0.1168）

| 分箱 | 人数 | 占比 | bad 数 | bad rate | WOE |
|---|---|---|---|---|---|
| <= 672 | 89,431 | 27.09% | 17,304 | 19.35% | -0.3151 |
| (672, 687] | 76,714 | 23.24% | 13,058 | 17.02% | -0.1585 |
| (687, 702] | 61,435 | 18.61% | 8,893 | 14.48% | 0.0338 |
| (702, 717] | 42,487 | 12.87% | 5,021 | 11.82% | 0.2672 |
| (717, 737] | 30,608 | 9.27% | 2,974 | 9.72% | 0.4866 |
| > 737 | 29,396 | 8.91% | 1,926 | 6.55% | 0.9151 |

### [不含平台评级] 分箱表：loan_to_inc（IV = 0.0632）

| 分箱 | 人数 | 占比 | bad 数 | bad rate | WOE |
|---|---|---|---|---|---|
| <= 0.1516 | 117,364 | 35.56% | 13,952 | 11.89% | 0.2605 |
| (0.1516, 0.2632] | 115,822 | 35.09% | 16,297 | 14.07% | 0.0669 |
| (0.2632, 0.3333] | 49,428 | 14.97% | 8,764 | 17.73% | -0.2079 |
| > 0.3333 | 47,457 | 14.38% | 10,163 | 21.42% | -0.4425 |

### [不含平台评级] 分箱表：term（IV = 0.0612）

| 分箱 | 人数 | 占比 | bad 数 | bad rate | WOE |
|---|---|---|---|---|---|
| <= 36 | 299,349 | 90.69% | 41,279 | 13.79% | 0.0903 |
| > 36 | 30,722 | 9.31% | 7,897 | 25.70% | -0.6812 |

### [不含平台评级] 分箱表：acc_open_past_24mths（IV = 0.0607）

| 分箱 | 人数 | 占比 | bad 数 | bad rate | WOE |
|---|---|---|---|---|---|
| <= 1 | 49,373 | 14.96% | 5,120 | 10.37% | 0.4142 |
| (1, 2] | 46,993 | 14.24% | 5,681 | 12.09% | 0.2415 |
| (2, 3] | 51,455 | 15.59% | 7,026 | 13.65% | 0.1017 |
| (3, 5] | 86,775 | 26.29% | 13,421 | 15.47% | -0.0441 |
| (5, 7] | 50,464 | 15.29% | 8,797 | 17.43% | -0.1873 |
| > 7 | 39,790 | 12.05% | 8,289 | 20.83% | -0.4075 |
| Missing | 5,221 | 1.58% | 842 | 16.13% | -0.0938 |

### [不含平台评级] 分箱表：bc_open_to_buy（IV = 0.0583）

| 分箱 | 人数 | 占比 | bad 数 | bad rate | WOE |
|---|---|---|---|---|---|
| <= 2,396 | 128,506 | 38.93% | 23,049 | 17.94% | -0.2219 |
| (2,396, 8,449] | 100,030 | 30.31% | 14,851 | 14.85% | 0.0041 |
| > 8,449 | 93,150 | 28.22% | 9,882 | 10.61% | 0.3888 |
| Missing | 8,385 | 2.54% | 1,394 | 16.62% | -0.1301 |

### [不含平台评级] 分箱表：annual_inc（IV = 0.0551）

| 分箱 | 人数 | 占比 | bad 数 | bad rate | WOE |
|---|---|---|---|---|---|
| <= 37,000 | 51,705 | 15.66% | 10,106 | 19.55% | -0.3276 |
| (37,000, 49,000] | 53,858 | 16.32% | 9,323 | 17.31% | -0.1788 |
| (49,000, 66,000] | 79,735 | 24.16% | 12,239 | 15.35% | -0.0351 |
| (66,000, 82,000] | 50,755 | 15.38% | 7,018 | 13.83% | 0.0871 |
| (82,000, 110,000] | 52,533 | 15.92% | 6,196 | 11.79% | 0.2695 |
| > 110,000 | 41,485 | 12.57% | 4,294 | 10.35% | 0.4163 |

### [不含平台评级] 分箱表：tot_hi_cred_lim（IV = 0.0520）

| 分箱 | 人数 | 占比 | bad 数 | bad rate | WOE |
|---|---|---|---|---|---|
| <= 53,148 | 99,117 | 30.03% | 17,658 | 17.82% | -0.2137 |
| (53,148, 156,798] | 93,447 | 28.31% | 14,554 | 15.57% | -0.0523 |
| (156,798, 234,986] | 41,750 | 12.65% | 5,640 | 13.51% | 0.1141 |
| (234,986, 300,194] | 26,500 | 8.03% | 3,162 | 11.93% | 0.2563 |
| (300,194, 431,415] | 29,502 | 8.94% | 3,161 | 10.71% | 0.3777 |
| > 431,415 | 20,483 | 6.21% | 1,800 | 8.79% | 0.5973 |
| Missing | 19,272 | 5.84% | 3,201 | 16.61% | -0.1290 |

### [不含平台评级] 分箱表：num_tl_op_past_12m（IV = 0.0493）

| 分箱 | 人数 | 占比 | bad 数 | bad rate | WOE |
|---|---|---|---|---|---|
| <= 0 | 56,712 | 17.18% | 6,236 | 11.00% | 0.3486 |
| (0, 1] | 82,243 | 24.92% | 10,599 | 12.89% | 0.1684 |
| (1, 2] | 73,053 | 22.13% | 11,071 | 15.15% | -0.0201 |
| (2, 3] | 50,501 | 15.30% | 8,486 | 16.80% | -0.1430 |
| > 3 | 48,290 | 14.63% | 9,583 | 19.84% | -0.3465 |
| Missing | 19,272 | 5.84% | 3,201 | 16.61% | -0.1290 |

### [不含平台评级] 分箱表：dti（IV = 0.0483）

| 分箱 | 人数 | 占比 | bad 数 | bad rate | WOE |
|---|---|---|---|---|---|
| <= 11.65 | 84,294 | 25.54% | 9,797 | 11.62% | 0.2861 |
| (11.65, 17.11] | 80,650 | 24.43% | 10,726 | 13.30% | 0.1322 |
| (17.11, 21.74] | 64,496 | 19.54% | 10,003 | 15.51% | -0.0474 |
| (21.74, 25.16] | 38,066 | 11.53% | 6,493 | 17.06% | -0.1610 |
| > 25.16 | 62,565 | 18.96% | 12,157 | 19.43% | -0.3203 |

### [不含平台评级] 分箱表：total_rev_hi_lim（IV = 0.0405）

| 分箱 | 人数 | 占比 | bad 数 | bad rate | WOE |
|---|---|---|---|---|---|
| <= 6,600 | 22,028 | 6.67% | 4,085 | 18.54% | -0.2627 |
| (6,600, 18,000] | 102,697 | 31.11% | 17,119 | 16.67% | -0.1333 |
| (18,000, 23,216] | 39,735 | 12.04% | 6,198 | 15.60% | -0.0542 |
| (23,216, 37,900] | 71,579 | 21.69% | 10,296 | 14.38% | 0.0412 |
| (37,900, 55,900] | 40,344 | 12.22% | 5,017 | 12.44% | 0.2092 |
| > 55,900 | 34,416 | 10.43% | 3,260 | 9.47% | 0.5147 |
| Missing | 19,272 | 5.84% | 3,201 | 16.61% | -0.1290 |

### [不含平台评级] 分箱表：mo_sin_rcnt_tl（IV = 0.0370）

| 分箱 | 人数 | 占比 | bad 数 | bad rate | WOE |
|---|---|---|---|---|---|
| <= 1 | 30,622 | 9.28% | 5,666 | 18.50% | -0.2599 |
| (1, 3] | 64,147 | 19.43% | 11,021 | 17.18% | -0.1697 |
| (3, 7] | 95,765 | 29.01% | 14,549 | 15.19% | -0.0230 |
| (7, 13] | 71,222 | 21.58% | 9,460 | 13.28% | 0.1336 |
| (13, 22] | 31,266 | 9.47% | 3,592 | 11.49% | 0.2992 |
| > 22 | 17,777 | 5.39% | 1,687 | 9.49% | 0.5127 |
| Missing | 19,272 | 5.84% | 3,201 | 16.61% | -0.1290 |

### [不含平台评级] 分箱表：percent_bc_gt_75（IV = 0.0351）

| 分箱 | 人数 | 占比 | bad 数 | bad rate | WOE |
|---|---|---|---|---|---|
| <= 0 | 58,860 | 17.83% | 6,624 | 11.25% | 0.3225 |
| (0, 26.7] | 39,576 | 11.99% | 5,021 | 12.69% | 0.1863 |
| (26.7, 50] | 81,970 | 24.83% | 11,861 | 14.47% | 0.0342 |
| (50, 83.3] | 71,318 | 21.61% | 11,833 | 16.59% | -0.1277 |
| > 83.3 | 69,851 | 21.16% | 12,430 | 17.80% | -0.2123 |
| Missing | 8,496 | 2.57% | 1,407 | 16.56% | -0.1255 |

### [不含平台评级] 分箱表：inq_last_6mths（IV = 0.0335）

| 分箱 | 人数 | 占比 | bad 数 | bad rate | WOE |
|---|---|---|---|---|---|
| <= 0 | 178,636 | 54.12% | 23,141 | 12.95% | 0.1624 |
| (0, 1] | 91,969 | 27.86% | 14,717 | 16.00% | -0.0845 |
| (1, 2] | 37,743 | 11.43% | 6,937 | 18.38% | -0.2517 |
| > 2 | 21,723 | 6.58% | 4,381 | 20.17% | -0.3667 |

### [不含平台评级] 分箱表：mort_acc（IV = 0.0325）

| 分箱 | 人数 | 占比 | bad 数 | bad rate | WOE |
|---|---|---|---|---|---|
| <= 0 | 137,007 | 41.51% | 23,685 | 17.29% | -0.1772 |
| (0, 1] | 52,801 | 16.00% | 7,826 | 14.82% | 0.0061 |
| (1, 2] | 42,862 | 12.99% | 5,759 | 13.44% | 0.1204 |
| (2, 4] | 56,673 | 17.17% | 7,053 | 12.45% | 0.2084 |
| > 4 | 35,507 | 10.76% | 4,011 | 11.30% | 0.3182 |
| Missing | 5,221 | 1.58% | 842 | 16.13% | -0.0938 |

### [不含平台评级] 分箱表：verification_status（IV = 0.0313）

| 分箱 | 人数 | 占比 | bad 数 | bad rate | WOE |
|---|---|---|---|---|---|
| {Not Verified} | 111,190 | 33.69% | 13,427 | 12.08% | 0.2427 |
| {Source Verified} | 106,649 | 32.31% | 16,159 | 15.15% | -0.0198 |
| {Verified} | 112,232 | 34.00% | 19,590 | 17.45% | -0.1889 |

### [不含平台评级] 分箱表：mths_since_recent_bc（IV = 0.0288）

| 分箱 | 人数 | 占比 | bad 数 | bad rate | WOE |
|---|---|---|---|---|---|
| <= 3 | 42,266 | 12.81% | 7,728 | 18.28% | -0.2454 |
| (3, 14] | 123,612 | 37.45% | 19,619 | 15.87% | -0.0748 |
| (14, 23] | 52,179 | 15.81% | 7,725 | 14.80% | 0.0074 |
| (23, 37] | 40,336 | 12.22% | 5,455 | 13.52% | 0.1128 |
| (37, 68] | 35,211 | 10.67% | 4,281 | 12.16% | 0.2350 |
| > 68 | 28,370 | 8.60% | 3,029 | 10.68% | 0.3816 |
| Missing | 8,097 | 2.45% | 1,339 | 16.54% | -0.1238 |

### [不含平台评级] 分箱表：home_ownership（IV = 0.0276）

| 分箱 | 人数 | 占比 | bad 数 | bad rate | WOE |
|---|---|---|---|---|---|
| {OTHER_RARE, MORTGAGE} | 159,173 | 48.22% | 20,345 | 12.78% | 0.1778 |
| {OWN} | 31,615 | 9.58% | 4,877 | 15.43% | -0.0410 |
| {RENT} | 139,283 | 42.20% | 23,954 | 17.20% | -0.1709 |

### [不含平台评级] 分箱表：mo_sin_old_rev_tl_op（IV = 0.0274）

| 分箱 | 人数 | 占比 | bad 数 | bad rate | WOE |
|---|---|---|---|---|---|
| <= 82 | 33,105 | 10.03% | 6,476 | 19.56% | -0.3287 |
| (82, 115] | 44,700 | 13.54% | 7,332 | 16.40% | -0.1140 |
| (115, 154] | 62,369 | 18.90% | 9,596 | 15.39% | -0.0379 |
| (154, 233] | 97,907 | 29.66% | 13,675 | 13.97% | 0.0754 |
| > 233 | 72,718 | 22.03% | 8,896 | 12.23% | 0.2279 |
| Missing | 19,272 | 5.84% | 3,201 | 16.61% | -0.1290 |

### [不含平台评级] 分箱表：revol_util（IV = 0.0233）

| 分箱 | 人数 | 占比 | bad 数 | bad rate | WOE |
|---|---|---|---|---|---|
| <= 18.1 | 21,601 | 6.54% | 2,229 | 10.32% | 0.4197 |
| (18.1, 25.5] | 16,619 | 5.03% | 1,987 | 11.96% | 0.2540 |
| (25.5, 44.8] | 70,600 | 21.39% | 9,587 | 13.58% | 0.1081 |
| (44.8, 58.8] | 67,701 | 20.51% | 10,032 | 14.82% | 0.0064 |
| (58.8, 86.9] | 121,944 | 36.94% | 19,757 | 16.20% | -0.0993 |
| > 86.9 | 31,430 | 9.52% | 5,555 | 17.67% | -0.2040 |
| Missing | 176 | 0.05% | 29 | 16.48% | -0.1194 |

### [不含平台评级] 分箱表：num_rev_tl_bal_gt_0（IV = 0.0208）

| 分箱 | 人数 | 占比 | bad 数 | bad rate | WOE |
|---|---|---|---|---|---|
| <= 2 | 34,285 | 10.39% | 4,076 | 11.89% | 0.2604 |
| (2, 3] | 42,309 | 12.82% | 5,500 | 13.00% | 0.1584 |
| (3, 5] | 96,433 | 29.22% | 13,661 | 14.17% | 0.0590 |
| (5, 7] | 68,586 | 20.78% | 10,609 | 15.47% | -0.0442 |
| (7, 8] | 21,549 | 6.53% | 3,569 | 16.56% | -0.1256 |
| > 8 | 47,637 | 14.43% | 8,560 | 17.97% | -0.2241 |
| Missing | 19,272 | 5.84% | 3,201 | 16.61% | -0.1290 |

### [含平台评级] 2.1 分箱设置

- **分箱后端**：toad（5 个特征库未给出切点，退到 tree：collections_12_mths_ex_med, acc_now_delinq, chargeoff_within_12_mths, delinq_amnt, tax_liens）
- **method / min_samples / max_bins**：chi / 0.05 / 6
- **单调性约束**：是（不单调则合并相邻箱直至单调或退到 2 箱）
- **切点搜索样本量**：200,000（WOE / IV 在全部 train 上计算；筛选阈值也在 train 上评估）
- **WOE 定义**：WOE = ln(good 占比 / bad 占比)，越大越安全；缺失单独一箱
- **候选特征 → 入模特征**：103 → 20

![[含平台评级] 图 2.1 IV 排名（前 30；绿色 = 入模）](figures/03_iv_ranking_with_platform_rating.png)

_[含平台评级] 图 2.1 IV 排名（前 30；绿色 = 入模）_

### [含平台评级] 2.2 IV 排名表（全部候选特征，按 IV 降序）

| 特征 | 类型 | IV | 缺失率（train） | 箱数 | 入模 | 剔除步骤 | 原因 |
|---|---|---|---|---|---|---|---|
| sub_grade | categorical | 0.3546 | 0.00% | 6 | 是 |  | selected |
| grade | categorical | 0.3364 | 0.00% | 5 | 否 | 3_corr | \|corr\| = 0.93 with sub_grade (IV 0.355) |
| int_rate | numeric | 0.3109 | 0.00% | 4 | 否 | 3_corr | \|corr\| = 0.92 with sub_grade (IV 0.355) |
| fico_mid | numeric | 0.1168 | 0.00% | 6 | 是 |  | selected |
| loan_to_inc | numeric | 0.0632 | 0.00% | 4 | 是 |  | selected |
| term | numeric | 0.0612 | 0.00% | 2 | 是 |  | selected |
| acc_open_past_24mths | numeric | 0.0607 | 1.58% | 7 | 是 |  | selected |
| bc_open_to_buy | numeric | 0.0583 | 2.54% | 4 | 是 |  | selected |
| log_annual_inc | numeric | 0.0551 | 0.00% | 6 | 是 |  | selected |
| annual_inc | numeric | 0.0551 | 0.00% | 6 | 否 | 3_corr | \|corr\| = 1.00 with log_annual_inc (IV 0.055) |
| tot_hi_cred_lim | numeric | 0.0520 | 5.84% | 7 | 是 |  | selected |
| avg_cur_bal | numeric | 0.0498 | 5.84% | 7 | 否 | 3_corr | \|corr\| = 0.85 with tot_hi_cred_lim (IV 0.052) |
| num_tl_op_past_12m | numeric | 0.0493 | 5.84% | 6 | 是 |  | selected |
| dti | numeric | 0.0483 | 0.00% | 5 | 是 |  | selected |
| total_bc_limit | numeric | 0.0479 | 1.58% | 5 | 否 | 3_corr | \|corr\| = 0.71 with bc_open_to_buy (IV 0.058) |
| total_rev_hi_lim | numeric | 0.0405 | 5.84% | 7 | 是 |  | selected |
| tot_cur_bal | numeric | 0.0398 | 5.84% | 5 | 否 | 3_corr | \|corr\| = 0.93 with tot_hi_cred_lim (IV 0.052) |
| mo_sin_rcnt_tl | numeric | 0.0370 | 5.84% | 7 | 是 |  | selected |
| percent_bc_gt_75 | numeric | 0.0351 | 2.57% | 6 | 是 |  | selected |
| inq_last_6mths | numeric | 0.0335 | 0.00% | 4 | 是 |  | selected |
| mths_since_recent_inq | numeric | 0.0328 | 11.90% | 7 | 否 | 3_corr | \|corr\| = 0.73 with inq_last_6mths (IV 0.033) |
| mort_acc | numeric | 0.0325 | 1.58% | 6 | 是 |  | selected |
| bc_util | numeric | 0.0323 | 2.61% | 7 | 否 | 3_corr | \|corr\| = 0.79 with percent_bc_gt_75 (IV 0.035) |
| verification_status | categorical | 0.0313 | 0.00% | 3 | 是 |  | selected |
| mo_sin_rcnt_rev_tl_op | numeric | 0.0307 | 5.84% | 7 | 否 | 3_corr | \|corr\| = 0.74 with mo_sin_rcnt_tl (IV 0.037) |
| mths_since_recent_bc | numeric | 0.0288 | 2.45% | 7 | 是 |  | selected |
| home_ownership | categorical | 0.0276 | 0.00% | 3 | 是 |  | selected |
| mo_sin_old_rev_tl_op | numeric | 0.0274 | 5.84% | 6 | 是 |  | selected |
| revol_util | numeric | 0.0233 | 0.05% | 7 | 否 | 5_sign | coefficient +0.0224 is not negative |
| num_rev_tl_bal_gt_0 | numeric | 0.0208 | 5.84% | 7 | 是 |  | selected |
| num_actv_rev_tl | numeric | 0.0207 | 5.84% | 7 | 否 | 3_corr | \|corr\| = 0.99 with num_rev_tl_bal_gt_0 (IV 0.021) |
| purpose | categorical | 0.0190 | 0.00% | 3 | 否 | 2_iv | IV 0.0190 < 0.02 |
| credit_hist_months | numeric | 0.0173 | 0.00% | 5 | 否 | 2_iv | IV 0.0173 < 0.02 |
| mo_sin_old_il_acct | numeric | 0.0135 | 9.36% | 4 | 否 | 2_iv | IV 0.0135 < 0.02 |
| emp_length_years | numeric | 0.0116 | 5.33% | 4 | 否 | 2_iv | IV 0.0116 < 0.02 |
| revol_bal | numeric | 0.0100 | 0.00% | 4 | 否 | 2_iv | IV 0.0100 < 0.02 |
| addr_state | categorical | 0.0100 | 0.00% | 4 | 否 | 2_iv | IV 0.0100 < 0.02 |
| initial_list_status | categorical | 0.0081 | 0.00% | 2 | 否 | 2_iv | IV 0.0081 < 0.02 |
| num_op_rev_tl | numeric | 0.0056 | 5.84% | 7 | 否 | 2_iv | IV 0.0056 < 0.02 |
| num_actv_bc_tl | numeric | 0.0053 | 5.84% | 5 | 否 | 2_iv | IV 0.0053 < 0.02 |
| total_bal_ex_mort | numeric | 0.0041 | 1.58% | 5 | 否 | 2_iv | IV 0.0041 < 0.02 |
| total_acc | numeric | 0.0037 | 0.00% | 4 | 否 | 2_iv | IV 0.0037 < 0.02 |
| total_il_high_credit_limit | numeric | 0.0035 | 5.84% | 4 | 否 | 2_iv | IV 0.0035 < 0.02 |
| num_bc_tl | numeric | 0.0034 | 5.84% | 4 | 否 | 2_iv | IV 0.0034 < 0.02 |
| mths_since_last_record | numeric | 0.0030 | 84.98% | 3 | 否 | 1_missing | missing rate 85.0% > 50% |
| installment | numeric | 0.0028 | 0.00% | 2 | 否 | 2_iv | IV 0.0028 < 0.02 |
| num_il_tl | numeric | 0.0026 | 5.84% | 5 | 否 | 2_iv | IV 0.0026 < 0.02 |
| num_accts_ever_120_pd | numeric | 0.0024 | 5.84% | 3 | 否 | 2_iv | IV 0.0024 < 0.02 |
| tot_coll_amt | numeric | 0.0023 | 5.84% | 3 | 否 | 2_iv | IV 0.0023 < 0.02 |
| pub_rec | numeric | 0.0021 | 0.00% | 2 | 否 | 2_iv | IV 0.0021 < 0.02 |
| mths_since_last_major_derog | numeric | 0.0019 | 75.37% | 3 | 否 | 1_missing | missing rate 75.4% > 50% |
| pub_rec_bankruptcies | numeric | 0.0018 | 0.00% | 2 | 否 | 2_iv | IV 0.0018 < 0.02 |
| num_sats | numeric | 0.0018 | 3.37% | 6 | 否 | 2_iv | IV 0.0018 < 0.02 |
| num_tl_120dpd_2m | numeric | 0.0018 | 8.17% | 2 | 否 | 2_iv | IV 0.0018 < 0.02 |
| num_rev_accts | numeric | 0.0016 | 5.84% | 3 | 否 | 2_iv | IV 0.0016 < 0.02 |
| pct_tl_nvr_dlq | numeric | 0.0015 | 5.87% | 3 | 否 | 2_iv | IV 0.0015 < 0.02 |
| num_tl_90g_dpd_24m | numeric | 0.0015 | 5.84% | 3 | 否 | 2_iv | IV 0.0015 < 0.02 |
| loan_amnt | numeric | 0.0011 | 0.00% | 4 | 否 | 2_iv | IV 0.0011 < 0.02 |
| funded_amnt | numeric | 0.0011 | 0.00% | 4 | 否 | 2_iv | IV 0.0011 < 0.02 |
| open_acc | numeric | 0.0011 | 0.00% | 3 | 否 | 2_iv | IV 0.0011 < 0.02 |
| num_tl_30dpd | numeric | 0.0011 | 5.84% | 2 | 否 | 2_iv | IV 0.0011 < 0.02 |
| delinq_2yrs | numeric | 0.0009 | 0.00% | 3 | 否 | 2_iv | IV 0.0009 < 0.02 |
| mths_since_last_delinq | numeric | 0.0006 | 52.06% | 3 | 否 | 1_missing | missing rate 52.1% > 50% |
| num_bc_sats | numeric | 0.0006 | 3.37% | 3 | 否 | 2_iv | IV 0.0006 < 0.02 |
| mths_since_recent_bc_dlq | numeric | 0.0002 | 76.20% | 3 | 否 | 1_missing | missing rate 76.2% > 50% |
| mths_since_recent_revol_delinq | numeric | 0.0002 | 66.50% | 3 | 否 | 1_missing | missing rate 66.5% > 50% |
| collections_12_mths_ex_med | numeric | 0.0000 | 0.00% | 1 | 否 | 2_iv | IV 0.0000 < 0.02 |
| dti_joint | numeric | 0.0000 | 100.00% | 2 | 否 | 1_missing | missing rate 100.0% > 50% |
| verification_status_joint | categorical | 0.0000 | 100.00% | 1 | 否 | 1_missing | missing rate 100.0% > 50% |
| application_type | categorical | 0.0000 | 0.00% | 1 | 否 | 2_iv | IV 0.0000 < 0.02 |
| annual_inc_joint | numeric | 0.0000 | 100.00% | 2 | 否 | 1_missing | missing rate 100.0% > 50% |
| all_util | numeric | 0.0000 | 100.00% | 2 | 否 | 1_missing | missing rate 100.0% > 50% |
| max_bal_bc | numeric | 0.0000 | 100.00% | 2 | 否 | 1_missing | missing rate 100.0% > 50% |
| open_rv_24m | numeric | 0.0000 | 100.00% | 2 | 否 | 1_missing | missing rate 100.0% > 50% |
| open_rv_12m | numeric | 0.0000 | 100.00% | 2 | 否 | 1_missing | missing rate 100.0% > 50% |
| il_util | numeric | 0.0000 | 100.00% | 2 | 否 | 1_missing | missing rate 100.0% > 50% |
| total_bal_il | numeric | 0.0000 | 100.00% | 2 | 否 | 1_missing | missing rate 100.0% > 50% |
| mths_since_rcnt_il | numeric | 0.0000 | 100.00% | 2 | 否 | 1_missing | missing rate 100.0% > 50% |
| open_il_24m | numeric | 0.0000 | 100.00% | 2 | 否 | 1_missing | missing rate 100.0% > 50% |
| open_il_12m | numeric | 0.0000 | 100.00% | 2 | 否 | 1_missing | missing rate 100.0% > 50% |
| open_act_il | numeric | 0.0000 | 100.00% | 2 | 否 | 1_missing | missing rate 100.0% > 50% |
| open_acc_6m | numeric | 0.0000 | 100.00% | 2 | 否 | 1_missing | missing rate 100.0% > 50% |
| acc_now_delinq | numeric | 0.0000 | 0.00% | 1 | 否 | 2_iv | IV 0.0000 < 0.02 |
| delinq_amnt | numeric | 0.0000 | 0.00% | 1 | 否 | 2_iv | IV 0.0000 < 0.02 |
| inq_fi | numeric | 0.0000 | 100.00% | 2 | 否 | 1_missing | missing rate 100.0% > 50% |
| chargeoff_within_12_mths | numeric | 0.0000 | 0.00% | 1 | 否 | 2_iv | IV 0.0000 < 0.02 |
| inq_last_12m | numeric | 0.0000 | 100.00% | 2 | 否 | 1_missing | missing rate 100.0% > 50% |
| total_cu_tl | numeric | 0.0000 | 100.00% | 2 | 否 | 1_missing | missing rate 100.0% > 50% |
| sec_app_open_acc | numeric | 0.0000 | 100.00% | 2 | 否 | 1_missing | missing rate 100.0% > 50% |
| sec_app_mort_acc | numeric | 0.0000 | 100.00% | 2 | 否 | 1_missing | missing rate 100.0% > 50% |
| sec_app_inq_last_6mths | numeric | 0.0000 | 100.00% | 2 | 否 | 1_missing | missing rate 100.0% > 50% |
| sec_app_fico_range_high | numeric | 0.0000 | 100.00% | 2 | 否 | 1_missing | missing rate 100.0% > 50% |
| sec_app_fico_range_low | numeric | 0.0000 | 100.00% | 2 | 否 | 1_missing | missing rate 100.0% > 50% |
| revol_bal_joint | numeric | 0.0000 | 100.00% | 2 | 否 | 1_missing | missing rate 100.0% > 50% |
| tax_liens | numeric | 0.0000 | 0.00% | 1 | 否 | 2_iv | IV 0.0000 < 0.02 |
| sec_app_revol_util | numeric | 0.0000 | 100.00% | 2 | 否 | 1_missing | missing rate 100.0% > 50% |
| disbursement_method | categorical | 0.0000 | 0.00% | 1 | 否 | 2_iv | IV 0.0000 < 0.02 |
| sec_app_mths_since_last_major_derog | numeric | 0.0000 | 100.00% | 2 | 否 | 1_missing | missing rate 100.0% > 50% |
| sec_app_collections_12_mths_ex_med | numeric | 0.0000 | 100.00% | 2 | 否 | 1_missing | missing rate 100.0% > 50% |
| sec_app_num_rev_accts | numeric | 0.0000 | 100.00% | 2 | 否 | 1_missing | missing rate 100.0% > 50% |
| sec_app_open_act_il | numeric | 0.0000 | 100.00% | 2 | 否 | 1_missing | missing rate 100.0% > 50% |
| sec_app_chargeoff_within_12_mths | numeric | 0.0000 | 100.00% | 2 | 否 | 1_missing | missing rate 100.0% > 50% |
| sec_app_credit_hist_months | numeric | 0.0000 | 100.00% | 2 | 否 | 1_missing | missing rate 100.0% > 50% |

### [含平台评级] 2.3 特征筛选漏斗

| 步骤 | 剔除 | 剩余 |
|---|---|---|
| 候选特征 |  | 103 |
| 缺失率 > 50% | 35 | 68 |
| IV < 0.02 | 37 | 31 |
| \|corr\| > 0.7（保留 IV 高者） | 10 | 21 |
| LR 系数为正（WOE 方向反转） | 1 | 20 |

### [含平台评级] 2.4 单调性检查（入模特征）

| 特征 | 类型 | 切点来源 | 初始箱数 | 初始单调 | 最终箱数（含缺失箱） | 最终单调 | 最大箱占比 |
|---|---|---|---|---|---|---|---|
| sub_grade | categorical | toad | 6 | 是 | 6 | 是 | 23.76% |
| fico_mid | numeric | toad | 6 | 是 | 6 | 是 | 27.09% |
| loan_to_inc | numeric | toad | 4 | 是 | 4 | 是 | 35.56% |
| term | numeric | unique_values | 2 | 是 | 2 | 是 | 90.69% |
| acc_open_past_24mths | numeric | toad | 6 | 是 | 7 | 是 | 26.29% |
| bc_open_to_buy | numeric | toad | 3 | 是 | 4 | 是 | 38.93% |
| log_annual_inc | numeric | toad | 6 | 是 | 6 | 是 | 24.16% |
| tot_hi_cred_lim | numeric | toad | 6 | 是 | 7 | 是 | 30.03% |
| num_tl_op_past_12m | numeric | toad | 5 | 是 | 6 | 是 | 24.92% |
| dti | numeric | toad | 5 | 是 | 5 | 是 | 25.54% |
| total_rev_hi_lim | numeric | toad | 6 | 是 | 7 | 是 | 31.11% |
| mo_sin_rcnt_tl | numeric | toad | 6 | 是 | 7 | 是 | 29.01% |
| percent_bc_gt_75 | numeric | toad | 5 | 是 | 6 | 是 | 24.83% |
| inq_last_6mths | numeric | toad | 4 | 是 | 4 | 是 | 54.12% |
| mort_acc | numeric | toad | 5 | 是 | 6 | 是 | 41.51% |
| verification_status | categorical | unique_values | 3 | 是 | 3 | 是 | 34.00% |
| mths_since_recent_bc | numeric | toad | 6 | 是 | 7 | 是 | 37.45% |
| home_ownership | categorical | unique_values | 3 | 是 | 3 | 是 | 48.22% |
| mo_sin_old_rev_tl_op | numeric | toad | 5 | 是 | 6 | 是 | 29.66% |
| num_rev_tl_bal_gt_0 | numeric | toad | 6 | 是 | 7 | 是 | 29.22% |

_类别型特征按 train bad rate 排序后再分箱，因此天然单调。数值型不单调时合并相邻箱，直到 bad rate 单调或只剩 2 箱。切点来源 unique_values = 取值数不超过 max_bins、逐值成箱。_

![[含平台评级] 图 2.2 sub_grade 的 WOE（IV 第 1 名）](figures/04_woe_with_platform_rating_01_sub_grade.png)

_[含平台评级] 图 2.2 sub_grade 的 WOE（IV 第 1 名）_

![[含平台评级] 图 2.3 fico_mid 的 WOE（IV 第 2 名）](figures/04_woe_with_platform_rating_02_fico_mid.png)

_[含平台评级] 图 2.3 fico_mid 的 WOE（IV 第 2 名）_

![[含平台评级] 图 2.4 loan_to_inc 的 WOE（IV 第 3 名）](figures/04_woe_with_platform_rating_03_loan_to_inc.png)

_[含平台评级] 图 2.4 loan_to_inc 的 WOE（IV 第 3 名）_

![[含平台评级] 图 2.5 term 的 WOE（IV 第 4 名）](figures/04_woe_with_platform_rating_04_term.png)

_[含平台评级] 图 2.5 term 的 WOE（IV 第 4 名）_

![[含平台评级] 图 2.6 acc_open_past_24mths 的 WOE（IV 第 5 名）](figures/04_woe_with_platform_rating_05_acc_open_past_24mths.png)

_[含平台评级] 图 2.6 acc_open_past_24mths 的 WOE（IV 第 5 名）_

![[含平台评级] 图 2.7 bc_open_to_buy 的 WOE（IV 第 6 名）](figures/04_woe_with_platform_rating_06_bc_open_to_buy.png)

_[含平台评级] 图 2.7 bc_open_to_buy 的 WOE（IV 第 6 名）_

![[含平台评级] 图 2.8 log_annual_inc 的 WOE（IV 第 7 名）](figures/04_woe_with_platform_rating_07_log_annual_inc.png)

_[含平台评级] 图 2.8 log_annual_inc 的 WOE（IV 第 7 名）_

![[含平台评级] 图 2.9 tot_hi_cred_lim 的 WOE（IV 第 8 名）](figures/04_woe_with_platform_rating_08_tot_hi_cred_lim.png)

_[含平台评级] 图 2.9 tot_hi_cred_lim 的 WOE（IV 第 8 名）_

### [含平台评级] 分箱表：sub_grade（IV = 0.3546）

| 分箱 | 人数 | 占比 | bad 数 | bad rate | WOE |
|---|---|---|---|---|---|
| {A1, A2, A3, A4} | 46,725 | 14.16% | 2,175 | 4.65% | 1.2770 |
| {A5, B1, B2} | 59,098 | 17.90% | 5,158 | 8.73% | 0.6047 |
| {B3, B4} | 46,719 | 14.15% | 5,467 | 11.70% | 0.2784 |
| {B5, C1, C2, C3} | 78,440 | 23.76% | 12,509 | 15.95% | -0.0804 |
| {C4, C5, D1, D3, D2} | 61,734 | 18.70% | 13,105 | 21.23% | -0.4313 |
| {D4, D5, G4, E2, E1, E3, E4, F1, E5, G2, F2, F3, F4, F5, G5, G1, G3} | 37,355 | 11.32% | 10,762 | 28.81% | -0.8379 |

### [含平台评级] 分箱表：fico_mid（IV = 0.1168）

| 分箱 | 人数 | 占比 | bad 数 | bad rate | WOE |
|---|---|---|---|---|---|
| <= 672 | 89,431 | 27.09% | 17,304 | 19.35% | -0.3151 |
| (672, 687] | 76,714 | 23.24% | 13,058 | 17.02% | -0.1585 |
| (687, 702] | 61,435 | 18.61% | 8,893 | 14.48% | 0.0338 |
| (702, 717] | 42,487 | 12.87% | 5,021 | 11.82% | 0.2672 |
| (717, 737] | 30,608 | 9.27% | 2,974 | 9.72% | 0.4866 |
| > 737 | 29,396 | 8.91% | 1,926 | 6.55% | 0.9151 |

### [含平台评级] 分箱表：loan_to_inc（IV = 0.0632）

| 分箱 | 人数 | 占比 | bad 数 | bad rate | WOE |
|---|---|---|---|---|---|
| <= 0.1516 | 117,364 | 35.56% | 13,952 | 11.89% | 0.2605 |
| (0.1516, 0.2632] | 115,822 | 35.09% | 16,297 | 14.07% | 0.0669 |
| (0.2632, 0.3333] | 49,428 | 14.97% | 8,764 | 17.73% | -0.2079 |
| > 0.3333 | 47,457 | 14.38% | 10,163 | 21.42% | -0.4425 |

### [含平台评级] 分箱表：term（IV = 0.0612）

| 分箱 | 人数 | 占比 | bad 数 | bad rate | WOE |
|---|---|---|---|---|---|
| <= 36 | 299,349 | 90.69% | 41,279 | 13.79% | 0.0903 |
| > 36 | 30,722 | 9.31% | 7,897 | 25.70% | -0.6812 |

### [含平台评级] 分箱表：acc_open_past_24mths（IV = 0.0607）

| 分箱 | 人数 | 占比 | bad 数 | bad rate | WOE |
|---|---|---|---|---|---|
| <= 1 | 49,373 | 14.96% | 5,120 | 10.37% | 0.4142 |
| (1, 2] | 46,993 | 14.24% | 5,681 | 12.09% | 0.2415 |
| (2, 3] | 51,455 | 15.59% | 7,026 | 13.65% | 0.1017 |
| (3, 5] | 86,775 | 26.29% | 13,421 | 15.47% | -0.0441 |
| (5, 7] | 50,464 | 15.29% | 8,797 | 17.43% | -0.1873 |
| > 7 | 39,790 | 12.05% | 8,289 | 20.83% | -0.4075 |
| Missing | 5,221 | 1.58% | 842 | 16.13% | -0.0938 |

### [含平台评级] 分箱表：bc_open_to_buy（IV = 0.0583）

| 分箱 | 人数 | 占比 | bad 数 | bad rate | WOE |
|---|---|---|---|---|---|
| <= 2,396 | 128,506 | 38.93% | 23,049 | 17.94% | -0.2219 |
| (2,396, 8,449] | 100,030 | 30.31% | 14,851 | 14.85% | 0.0041 |
| > 8,449 | 93,150 | 28.22% | 9,882 | 10.61% | 0.3888 |
| Missing | 8,385 | 2.54% | 1,394 | 16.62% | -0.1301 |

### [含平台评级] 分箱表：log_annual_inc（IV = 0.0551）

| 分箱 | 人数 | 占比 | bad 数 | bad rate | WOE |
|---|---|---|---|---|---|
| <= 10.52 | 51,705 | 15.66% | 10,106 | 19.55% | -0.3276 |
| (10.52, 10.8] | 53,858 | 16.32% | 9,323 | 17.31% | -0.1788 |
| (10.8, 11.1] | 79,735 | 24.16% | 12,239 | 15.35% | -0.0351 |
| (11.1, 11.31] | 50,755 | 15.38% | 7,018 | 13.83% | 0.0871 |
| (11.31, 11.61] | 52,533 | 15.92% | 6,196 | 11.79% | 0.2695 |
| > 11.61 | 41,485 | 12.57% | 4,294 | 10.35% | 0.4163 |

### [含平台评级] 分箱表：tot_hi_cred_lim（IV = 0.0520）

| 分箱 | 人数 | 占比 | bad 数 | bad rate | WOE |
|---|---|---|---|---|---|
| <= 53,148 | 99,117 | 30.03% | 17,658 | 17.82% | -0.2137 |
| (53,148, 156,798] | 93,447 | 28.31% | 14,554 | 15.57% | -0.0523 |
| (156,798, 234,986] | 41,750 | 12.65% | 5,640 | 13.51% | 0.1141 |
| (234,986, 300,194] | 26,500 | 8.03% | 3,162 | 11.93% | 0.2563 |
| (300,194, 431,415] | 29,502 | 8.94% | 3,161 | 10.71% | 0.3777 |
| > 431,415 | 20,483 | 6.21% | 1,800 | 8.79% | 0.5973 |
| Missing | 19,272 | 5.84% | 3,201 | 16.61% | -0.1290 |

### [含平台评级] 分箱表：num_tl_op_past_12m（IV = 0.0493）

| 分箱 | 人数 | 占比 | bad 数 | bad rate | WOE |
|---|---|---|---|---|---|
| <= 0 | 56,712 | 17.18% | 6,236 | 11.00% | 0.3486 |
| (0, 1] | 82,243 | 24.92% | 10,599 | 12.89% | 0.1684 |
| (1, 2] | 73,053 | 22.13% | 11,071 | 15.15% | -0.0201 |
| (2, 3] | 50,501 | 15.30% | 8,486 | 16.80% | -0.1430 |
| > 3 | 48,290 | 14.63% | 9,583 | 19.84% | -0.3465 |
| Missing | 19,272 | 5.84% | 3,201 | 16.61% | -0.1290 |

### [含平台评级] 分箱表：dti（IV = 0.0483）

| 分箱 | 人数 | 占比 | bad 数 | bad rate | WOE |
|---|---|---|---|---|---|
| <= 11.65 | 84,294 | 25.54% | 9,797 | 11.62% | 0.2861 |
| (11.65, 17.11] | 80,650 | 24.43% | 10,726 | 13.30% | 0.1322 |
| (17.11, 21.74] | 64,496 | 19.54% | 10,003 | 15.51% | -0.0474 |
| (21.74, 25.16] | 38,066 | 11.53% | 6,493 | 17.06% | -0.1610 |
| > 25.16 | 62,565 | 18.96% | 12,157 | 19.43% | -0.3203 |

### [含平台评级] 分箱表：total_rev_hi_lim（IV = 0.0405）

| 分箱 | 人数 | 占比 | bad 数 | bad rate | WOE |
|---|---|---|---|---|---|
| <= 6,600 | 22,028 | 6.67% | 4,085 | 18.54% | -0.2627 |
| (6,600, 18,000] | 102,697 | 31.11% | 17,119 | 16.67% | -0.1333 |
| (18,000, 23,216] | 39,735 | 12.04% | 6,198 | 15.60% | -0.0542 |
| (23,216, 37,900] | 71,579 | 21.69% | 10,296 | 14.38% | 0.0412 |
| (37,900, 55,900] | 40,344 | 12.22% | 5,017 | 12.44% | 0.2092 |
| > 55,900 | 34,416 | 10.43% | 3,260 | 9.47% | 0.5147 |
| Missing | 19,272 | 5.84% | 3,201 | 16.61% | -0.1290 |

### [含平台评级] 分箱表：mo_sin_rcnt_tl（IV = 0.0370）

| 分箱 | 人数 | 占比 | bad 数 | bad rate | WOE |
|---|---|---|---|---|---|
| <= 1 | 30,622 | 9.28% | 5,666 | 18.50% | -0.2599 |
| (1, 3] | 64,147 | 19.43% | 11,021 | 17.18% | -0.1697 |
| (3, 7] | 95,765 | 29.01% | 14,549 | 15.19% | -0.0230 |
| (7, 13] | 71,222 | 21.58% | 9,460 | 13.28% | 0.1336 |
| (13, 22] | 31,266 | 9.47% | 3,592 | 11.49% | 0.2992 |
| > 22 | 17,777 | 5.39% | 1,687 | 9.49% | 0.5127 |
| Missing | 19,272 | 5.84% | 3,201 | 16.61% | -0.1290 |

### [含平台评级] 分箱表：percent_bc_gt_75（IV = 0.0351）

| 分箱 | 人数 | 占比 | bad 数 | bad rate | WOE |
|---|---|---|---|---|---|
| <= 0 | 58,860 | 17.83% | 6,624 | 11.25% | 0.3225 |
| (0, 26.7] | 39,576 | 11.99% | 5,021 | 12.69% | 0.1863 |
| (26.7, 50] | 81,970 | 24.83% | 11,861 | 14.47% | 0.0342 |
| (50, 83.3] | 71,318 | 21.61% | 11,833 | 16.59% | -0.1277 |
| > 83.3 | 69,851 | 21.16% | 12,430 | 17.80% | -0.2123 |
| Missing | 8,496 | 2.57% | 1,407 | 16.56% | -0.1255 |

### [含平台评级] 分箱表：inq_last_6mths（IV = 0.0335）

| 分箱 | 人数 | 占比 | bad 数 | bad rate | WOE |
|---|---|---|---|---|---|
| <= 0 | 178,636 | 54.12% | 23,141 | 12.95% | 0.1624 |
| (0, 1] | 91,969 | 27.86% | 14,717 | 16.00% | -0.0845 |
| (1, 2] | 37,743 | 11.43% | 6,937 | 18.38% | -0.2517 |
| > 2 | 21,723 | 6.58% | 4,381 | 20.17% | -0.3667 |

### [含平台评级] 分箱表：mort_acc（IV = 0.0325）

| 分箱 | 人数 | 占比 | bad 数 | bad rate | WOE |
|---|---|---|---|---|---|
| <= 0 | 137,007 | 41.51% | 23,685 | 17.29% | -0.1772 |
| (0, 1] | 52,801 | 16.00% | 7,826 | 14.82% | 0.0061 |
| (1, 2] | 42,862 | 12.99% | 5,759 | 13.44% | 0.1204 |
| (2, 4] | 56,673 | 17.17% | 7,053 | 12.45% | 0.2084 |
| > 4 | 35,507 | 10.76% | 4,011 | 11.30% | 0.3182 |
| Missing | 5,221 | 1.58% | 842 | 16.13% | -0.0938 |

### [含平台评级] 分箱表：verification_status（IV = 0.0313）

| 分箱 | 人数 | 占比 | bad 数 | bad rate | WOE |
|---|---|---|---|---|---|
| {Not Verified} | 111,190 | 33.69% | 13,427 | 12.08% | 0.2427 |
| {Source Verified} | 106,649 | 32.31% | 16,159 | 15.15% | -0.0198 |
| {Verified} | 112,232 | 34.00% | 19,590 | 17.45% | -0.1889 |

### [含平台评级] 分箱表：mths_since_recent_bc（IV = 0.0288）

| 分箱 | 人数 | 占比 | bad 数 | bad rate | WOE |
|---|---|---|---|---|---|
| <= 3 | 42,266 | 12.81% | 7,728 | 18.28% | -0.2454 |
| (3, 14] | 123,612 | 37.45% | 19,619 | 15.87% | -0.0748 |
| (14, 23] | 52,179 | 15.81% | 7,725 | 14.80% | 0.0074 |
| (23, 37] | 40,336 | 12.22% | 5,455 | 13.52% | 0.1128 |
| (37, 68] | 35,211 | 10.67% | 4,281 | 12.16% | 0.2350 |
| > 68 | 28,370 | 8.60% | 3,029 | 10.68% | 0.3816 |
| Missing | 8,097 | 2.45% | 1,339 | 16.54% | -0.1238 |

### [含平台评级] 分箱表：home_ownership（IV = 0.0276）

| 分箱 | 人数 | 占比 | bad 数 | bad rate | WOE |
|---|---|---|---|---|---|
| {OTHER_RARE, MORTGAGE} | 159,173 | 48.22% | 20,345 | 12.78% | 0.1778 |
| {OWN} | 31,615 | 9.58% | 4,877 | 15.43% | -0.0410 |
| {RENT} | 139,283 | 42.20% | 23,954 | 17.20% | -0.1709 |

### [含平台评级] 分箱表：mo_sin_old_rev_tl_op（IV = 0.0274）

| 分箱 | 人数 | 占比 | bad 数 | bad rate | WOE |
|---|---|---|---|---|---|
| <= 82 | 33,105 | 10.03% | 6,476 | 19.56% | -0.3287 |
| (82, 115] | 44,700 | 13.54% | 7,332 | 16.40% | -0.1140 |
| (115, 154] | 62,369 | 18.90% | 9,596 | 15.39% | -0.0379 |
| (154, 233] | 97,907 | 29.66% | 13,675 | 13.97% | 0.0754 |
| > 233 | 72,718 | 22.03% | 8,896 | 12.23% | 0.2279 |
| Missing | 19,272 | 5.84% | 3,201 | 16.61% | -0.1290 |

### [含平台评级] 分箱表：num_rev_tl_bal_gt_0（IV = 0.0208）

| 分箱 | 人数 | 占比 | bad 数 | bad rate | WOE |
|---|---|---|---|---|---|
| <= 2 | 34,285 | 10.39% | 4,076 | 11.89% | 0.2604 |
| (2, 3] | 42,309 | 12.82% | 5,500 | 13.00% | 0.1584 |
| (3, 5] | 96,433 | 29.22% | 13,661 | 14.17% | 0.0590 |
| (5, 7] | 68,586 | 20.78% | 10,609 | 15.47% | -0.0442 |
| (7, 8] | 21,549 | 6.53% | 3,569 | 16.56% | -0.1256 |
| > 8 | 47,637 | 14.43% | 8,560 | 17.97% | -0.2241 |
| Missing | 19,272 | 5.84% | 3,201 | 16.61% | -0.1290 |

## 3. 模型表现

_WOE 逻辑回归评分卡与 GBDT challenger 在 train / test / OOT 上的 AUC、KS、Gini，以及 train 内交叉验证（每折重做分箱与 WOE；入模变量清单固定自全 train）。_

### [不含平台评级] 3.1 LR 系数表（WOE 输入；WOE 越大越安全，系数应为负）

| 特征 | 系数 | IV | VIF |
|---|---|---|---|
| (intercept) | -1.7453 |  |  |
| fico_mid | -0.6103 | 0.1168 | 1.5947 |
| loan_to_inc | -0.6391 | 0.0632 | 1.4140 |
| term | -0.9009 | 0.0612 | 1.1583 |
| acc_open_past_24mths | -0.6347 | 0.0607 | 2.1604 |
| bc_open_to_buy | -0.3870 | 0.0583 | 2.4636 |
| annual_inc | -0.3421 | 0.0551 | 1.9384 |
| tot_hi_cred_lim | -0.2889 | 0.0520 | 2.4684 |
| num_tl_op_past_12m | -0.2714 | 0.0493 | 2.7492 |
| dti | -0.5140 | 0.0483 | 1.2970 |
| total_rev_hi_lim | -0.2358 | 0.0405 | 2.4729 |
| mo_sin_rcnt_tl | -0.0867 | 0.0370 | 2.1272 |
| percent_bc_gt_75 | -0.2651 | 0.0351 | 2.0241 |
| inq_last_6mths | -0.6494 | 0.0335 | 1.1389 |
| mort_acc | -0.2553 | 0.0325 | 2.0681 |
| verification_status | -0.4581 | 0.0313 | 1.1990 |
| mths_since_recent_bc | -0.3796 | 0.0288 | 1.4369 |
| home_ownership | -0.4242 | 0.0276 | 1.8161 |
| mo_sin_old_rev_tl_op | -0.3698 | 0.0274 | 1.2773 |
| revol_util | -0.0286 | 0.0233 | 2.1214 |
| num_rev_tl_bal_gt_0 | -0.2039 | 0.0208 | 1.3856 |

_LogisticRegression(penalty=l2, C=1.0)；VIF > 5.0 标警。_

### [不含平台评级] 3.2 train / test / OOT 表现

| 模型 | 样本 | 行数 | bad rate | AUC | KS | Gini |
|---|---|---|---|---|---|---|
| LR scorecard | train | 330,071 | 14.90% | 0.6733 | 0.2467 | 0.3466 |
| GBDT challenger | train | 330,071 | 14.90% | 0.7031 | 0.2943 | 0.4062 |
| LR scorecard | test | 141,460 | 14.90% | 0.6744 | 0.2513 | 0.3489 |
| GBDT challenger | test | 141,460 | 14.90% | 0.6941 | 0.2790 | 0.3882 |
| LR scorecard | OOT | 162,236 | 14.71% | 0.6750 | 0.2526 | 0.3499 |
| GBDT challenger | OOT | 162,236 | 14.71% | 0.6959 | 0.2838 | 0.3918 |

### [不含平台评级] 3.3 5 折 CV（train 内；每折重做分箱与 WOE）

| 模型 | AUC 均值 ± std | KS 均值 ± std | 折数 |
|---|---|---|---|
| LR scorecard | 0.6719 ± 0.0026 | 0.2471 ± 0.0047 | 5 |
| GBDT challenger | 0.6918 ± 0.0022 | 0.2796 ± 0.0032 | 5 |

### [不含平台评级] 3.4 LR vs GBDT challenger

| 指标 | LR scorecard | GBDT | GBDT − LR |
|---|---|---|---|
| test AUC | 0.6744 | 0.6941 | +0.0196 |
| test KS | 0.2513 | 0.2790 | +0.0277 |
| OOT AUC | 0.6750 | 0.6959 | +0.0209 |
| OOT KS | 0.2526 | 0.2838 | +0.0312 |

_challenger 直接使用未 WOE 的原始候选特征（含缺失），只作为性能上限参照，不上线。_

![[不含平台评级] 图 3.1 ROC 曲线](figures/05_roc_no_platform_rating.png)

_[不含平台评级] 图 3.1 ROC 曲线_

![[不含平台评级] 图 3.2 KS 曲线（LR，test）](figures/06_ks_no_platform_rating.png)

_[不含平台评级] 图 3.2 KS 曲线（LR，test）_

### [不含平台评级] KS 分段表（test，按 LR 预测概率从高风险到低风险 10 等分）

| 分段 | 人数 | bad 数 | bad rate | 累计 bad 占比 | 累计 good 占比 | KS |
|---|---|---|---|---|---|---|
| 1 | 14,146 | 4,444 | 31.42% | 21.09% | 8.06% | 0.1303 |
| 2 | 14,146 | 3,300 | 23.33% | 36.74% | 17.07% | 0.1967 |
| 3 | 14,146 | 2,760 | 19.51% | 49.84% | 26.53% | 0.2331 |
| 4 | 14,146 | 2,379 | 16.82% | 61.13% | 36.30% | 0.2483 |
| 5 | 14,146 | 2,118 | 14.97% | 71.18% | 46.29% | 0.2488 |
| 6 | 14,146 | 1,768 | 12.50% | 79.56% | 56.57% | 0.2299 |
| 7 | 14,146 | 1,471 | 10.40% | 86.54% | 67.10% | 0.1944 |
| 8 | 14,146 | 1,302 | 9.20% | 92.72% | 77.77% | 0.1495 |
| 9 | 14,146 | 961 | 6.79% | 97.28% | 88.73% | 0.0856 |
| 10 | 14,146 | 573 | 4.05% | 100.00% | 100.00% | 0.0000 |

### [含平台评级] 3.1 LR 系数表（WOE 输入；WOE 越大越安全，系数应为负）

| 特征 | 系数 | IV | VIF |
|---|---|---|---|
| (intercept) | -1.7460 |  |  |
| sub_grade | -0.6238 | 0.3546 | 1.9336 |
| fico_mid | -0.2291 | 0.1168 | 1.7322 |
| loan_to_inc | -0.5116 | 0.0632 | 1.4081 |
| term | -0.5285 | 0.0612 | 1.2769 |
| acc_open_past_24mths | -0.5848 | 0.0607 | 2.1136 |
| bc_open_to_buy | -0.1818 | 0.0583 | 2.4244 |
| log_annual_inc | -0.2955 | 0.0551 | 1.8801 |
| tot_hi_cred_lim | -0.2245 | 0.0520 | 2.4647 |
| num_tl_op_past_12m | -0.1023 | 0.0493 | 2.7710 |
| dti | -0.4195 | 0.0483 | 1.2775 |
| total_rev_hi_lim | -0.1881 | 0.0405 | 2.4726 |
| mo_sin_rcnt_tl | -0.0541 | 0.0370 | 2.1252 |
| percent_bc_gt_75 | -0.1208 | 0.0351 | 1.7123 |
| inq_last_6mths | -0.3084 | 0.0335 | 1.1922 |
| mort_acc | -0.1911 | 0.0325 | 2.0697 |
| verification_status | -0.2387 | 0.0313 | 1.2202 |
| mths_since_recent_bc | -0.3255 | 0.0288 | 1.4367 |
| home_ownership | -0.3784 | 0.0276 | 1.8170 |
| mo_sin_old_rev_tl_op | -0.2540 | 0.0274 | 1.2821 |
| num_rev_tl_bal_gt_0 | -0.2966 | 0.0208 | 1.3783 |

_LogisticRegression(penalty=l2, C=1.0)；VIF > 5.0 标警。_

### [含平台评级] 3.2 train / test / OOT 表现

| 模型 | 样本 | 行数 | bad rate | AUC | KS | Gini |
|---|---|---|---|---|---|---|
| LR scorecard | train | 330,071 | 14.90% | 0.6881 | 0.2729 | 0.3762 |
| GBDT challenger | train | 330,071 | 14.90% | 0.7084 | 0.3015 | 0.4167 |
| LR scorecard | test | 141,460 | 14.90% | 0.6886 | 0.2760 | 0.3771 |
| GBDT challenger | test | 141,460 | 14.90% | 0.6992 | 0.2920 | 0.3985 |
| LR scorecard | OOT | 162,236 | 14.71% | 0.6978 | 0.2874 | 0.3956 |
| GBDT challenger | OOT | 162,236 | 14.71% | 0.7095 | 0.3052 | 0.4190 |

### [含平台评级] 3.3 5 折 CV（train 内；每折重做分箱与 WOE）

| 模型 | AUC 均值 ± std | KS 均值 ± std | 折数 |
|---|---|---|---|
| LR scorecard | 0.6869 ± 0.0017 | 0.2726 ± 0.0020 | 5 |
| GBDT challenger | 0.6973 ± 0.0018 | 0.2876 ± 0.0030 | 5 |

### [含平台评级] 3.4 LR vs GBDT challenger

| 指标 | LR scorecard | GBDT | GBDT − LR |
|---|---|---|---|
| test AUC | 0.6886 | 0.6992 | +0.0107 |
| test KS | 0.2760 | 0.2920 | +0.0161 |
| OOT AUC | 0.6978 | 0.7095 | +0.0117 |
| OOT KS | 0.2874 | 0.3052 | +0.0178 |

_challenger 直接使用未 WOE 的原始候选特征（含缺失），只作为性能上限参照，不上线。_

![[含平台评级] 图 3.1 ROC 曲线](figures/05_roc_with_platform_rating.png)

_[含平台评级] 图 3.1 ROC 曲线_

![[含平台评级] 图 3.2 KS 曲线（LR，test）](figures/06_ks_with_platform_rating.png)

_[含平台评级] 图 3.2 KS 曲线（LR，test）_

### [含平台评级] KS 分段表（test，按 LR 预测概率从高风险到低风险 10 等分）

| 分段 | 人数 | bad 数 | bad rate | 累计 bad 占比 | 累计 good 占比 | KS |
|---|---|---|---|---|---|---|
| 1 | 14,146 | 4,586 | 32.42% | 21.76% | 7.94% | 0.1382 |
| 2 | 14,146 | 3,413 | 24.13% | 37.95% | 16.86% | 0.2110 |
| 3 | 14,146 | 2,928 | 20.70% | 51.85% | 26.18% | 0.2567 |
| 4 | 14,146 | 2,407 | 17.02% | 63.27% | 35.93% | 0.2734 |
| 5 | 14,146 | 2,078 | 14.69% | 73.13% | 45.95% | 0.2717 |
| 6 | 14,146 | 1,729 | 12.22% | 81.33% | 56.27% | 0.2506 |
| 7 | 14,146 | 1,415 | 10.00% | 88.04% | 66.84% | 0.2120 |
| 8 | 14,146 | 1,134 | 8.02% | 93.42% | 77.65% | 0.1577 |
| 9 | 14,146 | 881 | 6.23% | 97.60% | 88.67% | 0.0894 |
| 10 | 14,146 | 505 | 3.57% | 100.00% | 100.00% | 0.0000 |

## 4. 评分卡

_把 WOE 逻辑回归换算为评分卡：PDO、base score、base odds，每个变量每个分箱的分数，以及分数分布。_

### [不含平台评级] 4.1 PDO 换算

- **PDO / base score / base odds**：20 / 600 / 20:1
- **Factor = PDO / ln2**：28.8539
- **Offset = base − Factor × ln(odds)**：600 − 28.8539 × ln(20) = 513.5614
- **LR 截距 b0**：-1.7453
- **基础分 = Offset − Factor × b0**：563.92 → 取整 564
- **分箱分数**：points = −Factor × 系数 × WOE，取整
- **可能的分数范围**：485 ~ 640
- **整数分数的 AUC（test / OOT）**：test 0.6740 / OOT 0.6745

### [不含平台评级] 4.2 评分卡表

| 变量 | 分箱 | train 人数 | 占比 | bad rate | WOE | 系数 | 分数 | 整数分 |
|---|---|---|---|---|---|---|---|---|
| BASE | (every applicant) |  |  |  |  |  | 563.92 | 564 |
| fico_mid | <= 672 | 89,431 | 27.09% | 19.35% | -0.3151 | -0.6103 | -5.55 | -6 |
| fico_mid | (672, 687] | 76,714 | 23.24% | 17.02% | -0.1585 | -0.6103 | -2.79 | -3 |
| fico_mid | (687, 702] | 61,435 | 18.61% | 14.48% | 0.0338 | -0.6103 | 0.59 | 1 |
| fico_mid | (702, 717] | 42,487 | 12.87% | 11.82% | 0.2672 | -0.6103 | 4.71 | 5 |
| fico_mid | (717, 737] | 30,608 | 9.27% | 9.72% | 0.4866 | -0.6103 | 8.57 | 9 |
| fico_mid | > 737 | 29,396 | 8.91% | 6.55% | 0.9151 | -0.6103 | 16.11 | 16 |
| loan_to_inc | <= 0.1516 | 117,364 | 35.56% | 11.89% | 0.2605 | -0.6391 | 4.80 | 5 |
| loan_to_inc | (0.1516, 0.2632] | 115,822 | 35.09% | 14.07% | 0.0669 | -0.6391 | 1.23 | 1 |
| loan_to_inc | (0.2632, 0.3333] | 49,428 | 14.97% | 17.73% | -0.2079 | -0.6391 | -3.83 | -4 |
| loan_to_inc | > 0.3333 | 47,457 | 14.38% | 21.42% | -0.4425 | -0.6391 | -8.16 | -8 |
| term | <= 36 | 299,349 | 90.69% | 13.79% | 0.0903 | -0.9009 | 2.35 | 2 |
| term | > 36 | 30,722 | 9.31% | 25.70% | -0.6812 | -0.9009 | -17.71 | -18 |
| acc_open_past_24mths | <= 1 | 49,373 | 14.96% | 10.37% | 0.4142 | -0.6347 | 7.59 | 8 |
| acc_open_past_24mths | (1, 2] | 46,993 | 14.24% | 12.09% | 0.2415 | -0.6347 | 4.42 | 4 |
| acc_open_past_24mths | (2, 3] | 51,455 | 15.59% | 13.65% | 0.1017 | -0.6347 | 1.86 | 2 |
| acc_open_past_24mths | (3, 5] | 86,775 | 26.29% | 15.47% | -0.0441 | -0.6347 | -0.81 | -1 |
| acc_open_past_24mths | (5, 7] | 50,464 | 15.29% | 17.43% | -0.1873 | -0.6347 | -3.43 | -3 |
| acc_open_past_24mths | > 7 | 39,790 | 12.05% | 20.83% | -0.4075 | -0.6347 | -7.46 | -7 |
| acc_open_past_24mths | Missing | 5,221 | 1.58% | 16.13% | -0.0938 | -0.6347 | -1.72 | -2 |
| bc_open_to_buy | <= 2,396 | 128,506 | 38.93% | 17.94% | -0.2219 | -0.3870 | -2.48 | -2 |
| bc_open_to_buy | (2,396, 8,449] | 100,030 | 30.31% | 14.85% | 0.0041 | -0.3870 | 0.05 | 0 |
| bc_open_to_buy | > 8,449 | 93,150 | 28.22% | 10.61% | 0.3888 | -0.3870 | 4.34 | 4 |
| bc_open_to_buy | Missing | 8,385 | 2.54% | 16.62% | -0.1301 | -0.3870 | -1.45 | -1 |
| annual_inc | <= 37,000 | 51,705 | 15.66% | 19.55% | -0.3276 | -0.3421 | -3.23 | -3 |
| annual_inc | (37,000, 49,000] | 53,858 | 16.32% | 17.31% | -0.1788 | -0.3421 | -1.76 | -2 |
| annual_inc | (49,000, 66,000] | 79,735 | 24.16% | 15.35% | -0.0351 | -0.3421 | -0.35 | 0 |
| annual_inc | (66,000, 82,000] | 50,755 | 15.38% | 13.83% | 0.0871 | -0.3421 | 0.86 | 1 |
| annual_inc | (82,000, 110,000] | 52,533 | 15.92% | 11.79% | 0.2695 | -0.3421 | 2.66 | 3 |
| annual_inc | > 110,000 | 41,485 | 12.57% | 10.35% | 0.4163 | -0.3421 | 4.11 | 4 |
| tot_hi_cred_lim | <= 53,148 | 99,117 | 30.03% | 17.82% | -0.2137 | -0.2889 | -1.78 | -2 |
| tot_hi_cred_lim | (53,148, 156,798] | 93,447 | 28.31% | 15.57% | -0.0523 | -0.2889 | -0.44 | 0 |
| tot_hi_cred_lim | (156,798, 234,986] | 41,750 | 12.65% | 13.51% | 0.1141 | -0.2889 | 0.95 | 1 |
| tot_hi_cred_lim | (234,986, 300,194] | 26,500 | 8.03% | 11.93% | 0.2563 | -0.2889 | 2.14 | 2 |
| tot_hi_cred_lim | (300,194, 431,415] | 29,502 | 8.94% | 10.71% | 0.3777 | -0.2889 | 3.15 | 3 |
| tot_hi_cred_lim | > 431,415 | 20,483 | 6.21% | 8.79% | 0.5973 | -0.2889 | 4.98 | 5 |
| tot_hi_cred_lim | Missing | 19,272 | 5.84% | 16.61% | -0.1290 | -0.2889 | -1.08 | -1 |
| num_tl_op_past_12m | <= 0 | 56,712 | 17.18% | 11.00% | 0.3486 | -0.2714 | 2.73 | 3 |
| num_tl_op_past_12m | (0, 1] | 82,243 | 24.92% | 12.89% | 0.1684 | -0.2714 | 1.32 | 1 |
| num_tl_op_past_12m | (1, 2] | 73,053 | 22.13% | 15.15% | -0.0201 | -0.2714 | -0.16 | 0 |
| num_tl_op_past_12m | (2, 3] | 50,501 | 15.30% | 16.80% | -0.1430 | -0.2714 | -1.12 | -1 |
| num_tl_op_past_12m | > 3 | 48,290 | 14.63% | 19.84% | -0.3465 | -0.2714 | -2.71 | -3 |
| num_tl_op_past_12m | Missing | 19,272 | 5.84% | 16.61% | -0.1290 | -0.2714 | -1.01 | -1 |
| dti | <= 11.65 | 84,294 | 25.54% | 11.62% | 0.2861 | -0.5140 | 4.24 | 4 |
| dti | (11.65, 17.11] | 80,650 | 24.43% | 13.30% | 0.1322 | -0.5140 | 1.96 | 2 |
| dti | (17.11, 21.74] | 64,496 | 19.54% | 15.51% | -0.0474 | -0.5140 | -0.70 | -1 |
| dti | (21.74, 25.16] | 38,066 | 11.53% | 17.06% | -0.1610 | -0.5140 | -2.39 | -2 |
| dti | > 25.16 | 62,565 | 18.96% | 19.43% | -0.3203 | -0.5140 | -4.75 | -5 |
| total_rev_hi_lim | <= 6,600 | 22,028 | 6.67% | 18.54% | -0.2627 | -0.2358 | -1.79 | -2 |
| total_rev_hi_lim | (6,600, 18,000] | 102,697 | 31.11% | 16.67% | -0.1333 | -0.2358 | -0.91 | -1 |
| total_rev_hi_lim | (18,000, 23,216] | 39,735 | 12.04% | 15.60% | -0.0542 | -0.2358 | -0.37 | 0 |
| total_rev_hi_lim | (23,216, 37,900] | 71,579 | 21.69% | 14.38% | 0.0412 | -0.2358 | 0.28 | 0 |
| total_rev_hi_lim | (37,900, 55,900] | 40,344 | 12.22% | 12.44% | 0.2092 | -0.2358 | 1.42 | 1 |
| total_rev_hi_lim | > 55,900 | 34,416 | 10.43% | 9.47% | 0.5147 | -0.2358 | 3.50 | 4 |
| total_rev_hi_lim | Missing | 19,272 | 5.84% | 16.61% | -0.1290 | -0.2358 | -0.88 | -1 |
| mo_sin_rcnt_tl | <= 1 | 30,622 | 9.28% | 18.50% | -0.2599 | -0.0867 | -0.65 | -1 |
| mo_sin_rcnt_tl | (1, 3] | 64,147 | 19.43% | 17.18% | -0.1697 | -0.0867 | -0.42 | 0 |
| mo_sin_rcnt_tl | (3, 7] | 95,765 | 29.01% | 15.19% | -0.0230 | -0.0867 | -0.06 | 0 |
| mo_sin_rcnt_tl | (7, 13] | 71,222 | 21.58% | 13.28% | 0.1336 | -0.0867 | 0.33 | 0 |
| mo_sin_rcnt_tl | (13, 22] | 31,266 | 9.47% | 11.49% | 0.2992 | -0.0867 | 0.75 | 1 |
| mo_sin_rcnt_tl | > 22 | 17,777 | 5.39% | 9.49% | 0.5127 | -0.0867 | 1.28 | 1 |
| mo_sin_rcnt_tl | Missing | 19,272 | 5.84% | 16.61% | -0.1290 | -0.0867 | -0.32 | 0 |
| percent_bc_gt_75 | <= 0 | 58,860 | 17.83% | 11.25% | 0.3225 | -0.2651 | 2.47 | 2 |
| percent_bc_gt_75 | (0, 26.7] | 39,576 | 11.99% | 12.69% | 0.1863 | -0.2651 | 1.43 | 1 |
| percent_bc_gt_75 | (26.7, 50] | 81,970 | 24.83% | 14.47% | 0.0342 | -0.2651 | 0.26 | 0 |
| percent_bc_gt_75 | (50, 83.3] | 71,318 | 21.61% | 16.59% | -0.1277 | -0.2651 | -0.98 | -1 |
| percent_bc_gt_75 | > 83.3 | 69,851 | 21.16% | 17.80% | -0.2123 | -0.2651 | -1.62 | -2 |
| percent_bc_gt_75 | Missing | 8,496 | 2.57% | 16.56% | -0.1255 | -0.2651 | -0.96 | -1 |
| inq_last_6mths | <= 0 | 178,636 | 54.12% | 12.95% | 0.1624 | -0.6494 | 3.04 | 3 |
| inq_last_6mths | (0, 1] | 91,969 | 27.86% | 16.00% | -0.0845 | -0.6494 | -1.58 | -2 |
| inq_last_6mths | (1, 2] | 37,743 | 11.43% | 18.38% | -0.2517 | -0.6494 | -4.72 | -5 |
| inq_last_6mths | > 2 | 21,723 | 6.58% | 20.17% | -0.3667 | -0.6494 | -6.87 | -7 |
| mort_acc | <= 0 | 137,007 | 41.51% | 17.29% | -0.1772 | -0.2553 | -1.31 | -1 |
| mort_acc | (0, 1] | 52,801 | 16.00% | 14.82% | 0.0061 | -0.2553 | 0.04 | 0 |
| mort_acc | (1, 2] | 42,862 | 12.99% | 13.44% | 0.1204 | -0.2553 | 0.89 | 1 |
| mort_acc | (2, 4] | 56,673 | 17.17% | 12.45% | 0.2084 | -0.2553 | 1.54 | 2 |
| mort_acc | > 4 | 35,507 | 10.76% | 11.30% | 0.3182 | -0.2553 | 2.34 | 2 |
| mort_acc | Missing | 5,221 | 1.58% | 16.13% | -0.0938 | -0.2553 | -0.69 | -1 |
| verification_status | {Not Verified} | 111,190 | 33.69% | 12.08% | 0.2427 | -0.4581 | 3.21 | 3 |
| verification_status | {Source Verified} | 106,649 | 32.31% | 15.15% | -0.0198 | -0.4581 | -0.26 | 0 |
| verification_status | {Verified} | 112,232 | 34.00% | 17.45% | -0.1889 | -0.4581 | -2.50 | -2 |
| mths_since_recent_bc | <= 3 | 42,266 | 12.81% | 18.28% | -0.2454 | -0.3796 | -2.69 | -3 |
| mths_since_recent_bc | (3, 14] | 123,612 | 37.45% | 15.87% | -0.0748 | -0.3796 | -0.82 | -1 |
| mths_since_recent_bc | (14, 23] | 52,179 | 15.81% | 14.80% | 0.0074 | -0.3796 | 0.08 | 0 |
| mths_since_recent_bc | (23, 37] | 40,336 | 12.22% | 13.52% | 0.1128 | -0.3796 | 1.24 | 1 |
| mths_since_recent_bc | (37, 68] | 35,211 | 10.67% | 12.16% | 0.2350 | -0.3796 | 2.57 | 3 |
| mths_since_recent_bc | > 68 | 28,370 | 8.60% | 10.68% | 0.3816 | -0.3796 | 4.18 | 4 |
| mths_since_recent_bc | Missing | 8,097 | 2.45% | 16.54% | -0.1238 | -0.3796 | -1.36 | -1 |
| home_ownership | {OTHER_RARE, MORTGAGE} | 159,173 | 48.22% | 12.78% | 0.1778 | -0.4242 | 2.18 | 2 |
| home_ownership | {OWN} | 31,615 | 9.58% | 15.43% | -0.0410 | -0.4242 | -0.50 | -1 |
| home_ownership | {RENT} | 139,283 | 42.20% | 17.20% | -0.1709 | -0.4242 | -2.09 | -2 |
| mo_sin_old_rev_tl_op | <= 82 | 33,105 | 10.03% | 19.56% | -0.3287 | -0.3698 | -3.51 | -4 |
| mo_sin_old_rev_tl_op | (82, 115] | 44,700 | 13.54% | 16.40% | -0.1140 | -0.3698 | -1.22 | -1 |
| mo_sin_old_rev_tl_op | (115, 154] | 62,369 | 18.90% | 15.39% | -0.0379 | -0.3698 | -0.40 | 0 |
| mo_sin_old_rev_tl_op | (154, 233] | 97,907 | 29.66% | 13.97% | 0.0754 | -0.3698 | 0.80 | 1 |
| mo_sin_old_rev_tl_op | > 233 | 72,718 | 22.03% | 12.23% | 0.2279 | -0.3698 | 2.43 | 2 |
| mo_sin_old_rev_tl_op | Missing | 19,272 | 5.84% | 16.61% | -0.1290 | -0.3698 | -1.38 | -1 |
| revol_util | <= 18.1 | 21,601 | 6.54% | 10.32% | 0.4197 | -0.0286 | 0.35 | 0 |
| revol_util | (18.1, 25.5] | 16,619 | 5.03% | 11.96% | 0.2540 | -0.0286 | 0.21 | 0 |
| revol_util | (25.5, 44.8] | 70,600 | 21.39% | 13.58% | 0.1081 | -0.0286 | 0.09 | 0 |
| revol_util | (44.8, 58.8] | 67,701 | 20.51% | 14.82% | 0.0064 | -0.0286 | 0.01 | 0 |
| revol_util | (58.8, 86.9] | 121,944 | 36.94% | 16.20% | -0.0993 | -0.0286 | -0.08 | 0 |
| revol_util | > 86.9 | 31,430 | 9.52% | 17.67% | -0.2040 | -0.0286 | -0.17 | 0 |
| revol_util | Missing | 176 | 0.05% | 16.48% | -0.1194 | -0.0286 | -0.10 | 0 |
| num_rev_tl_bal_gt_0 | <= 2 | 34,285 | 10.39% | 11.89% | 0.2604 | -0.2039 | 1.53 | 2 |
| num_rev_tl_bal_gt_0 | (2, 3] | 42,309 | 12.82% | 13.00% | 0.1584 | -0.2039 | 0.93 | 1 |
| num_rev_tl_bal_gt_0 | (3, 5] | 96,433 | 29.22% | 14.17% | 0.0590 | -0.2039 | 0.35 | 0 |
| num_rev_tl_bal_gt_0 | (5, 7] | 68,586 | 20.78% | 15.47% | -0.0442 | -0.2039 | -0.26 | 0 |
| num_rev_tl_bal_gt_0 | (7, 8] | 21,549 | 6.53% | 16.56% | -0.1256 | -0.2039 | -0.74 | -1 |
| num_rev_tl_bal_gt_0 | > 8 | 47,637 | 14.43% | 17.97% | -0.2241 | -0.2039 | -1.32 | -1 |
| num_rev_tl_bal_gt_0 | Missing | 19,272 | 5.84% | 16.61% | -0.1290 | -0.2039 | -0.76 | -1 |

![[不含平台评级] 图 4.1 分数分布（test，good / bad 分开）](figures/07_score_dist_no_platform_rating_test.png)

_[不含平台评级] 图 4.1 分数分布（test，good / bad 分开）_

![[不含平台评级] 图 4.2 分数分布（OOT，good / bad 分开）](figures/07_score_dist_no_platform_rating_oot.png)

_[不含平台评级] 图 4.2 分数分布（OOT，good / bad 分开）_

### [含平台评级] 4.1 PDO 换算

- **PDO / base score / base odds**：20 / 600 / 20:1
- **Factor = PDO / ln2**：28.8539
- **Offset = base − Factor × ln(odds)**：600 − 28.8539 × ln(20) = 513.5614
- **LR 截距 b0**：-1.7460
- **基础分 = Offset − Factor × b0**：563.94 → 取整 564
- **分箱分数**：points = −Factor × 系数 × WOE，取整
- **可能的分数范围**：498 ~ 639
- **整数分数的 AUC（test / OOT）**：test 0.6882 / OOT 0.6969

### [含平台评级] 4.2 评分卡表

| 变量 | 分箱 | train 人数 | 占比 | bad rate | WOE | 系数 | 分数 | 整数分 |
|---|---|---|---|---|---|---|---|---|
| BASE | (every applicant) |  |  |  |  |  | 563.94 | 564 |
| sub_grade | {A1, A2, A3, A4} | 46,725 | 14.16% | 4.65% | 1.2770 | -0.6238 | 22.99 | 23 |
| sub_grade | {A5, B1, B2} | 59,098 | 17.90% | 8.73% | 0.6047 | -0.6238 | 10.88 | 11 |
| sub_grade | {B3, B4} | 46,719 | 14.15% | 11.70% | 0.2784 | -0.6238 | 5.01 | 5 |
| sub_grade | {B5, C1, C2, C3} | 78,440 | 23.76% | 15.95% | -0.0804 | -0.6238 | -1.45 | -1 |
| sub_grade | {C4, C5, D1, D3, D2} | 61,734 | 18.70% | 21.23% | -0.4313 | -0.6238 | -7.76 | -8 |
| sub_grade | {D4, D5, G4, E2, E1, E3, E4, F1, E5, G2, F2, F3, F4, F5, G5, G1, G3} | 37,355 | 11.32% | 28.81% | -0.8379 | -0.6238 | -15.08 | -15 |
| fico_mid | <= 672 | 89,431 | 27.09% | 19.35% | -0.3151 | -0.2291 | -2.08 | -2 |
| fico_mid | (672, 687] | 76,714 | 23.24% | 17.02% | -0.1585 | -0.2291 | -1.05 | -1 |
| fico_mid | (687, 702] | 61,435 | 18.61% | 14.48% | 0.0338 | -0.2291 | 0.22 | 0 |
| fico_mid | (702, 717] | 42,487 | 12.87% | 11.82% | 0.2672 | -0.2291 | 1.77 | 2 |
| fico_mid | (717, 737] | 30,608 | 9.27% | 9.72% | 0.4866 | -0.2291 | 3.22 | 3 |
| fico_mid | > 737 | 29,396 | 8.91% | 6.55% | 0.9151 | -0.2291 | 6.05 | 6 |
| loan_to_inc | <= 0.1516 | 117,364 | 35.56% | 11.89% | 0.2605 | -0.5116 | 3.85 | 4 |
| loan_to_inc | (0.1516, 0.2632] | 115,822 | 35.09% | 14.07% | 0.0669 | -0.5116 | 0.99 | 1 |
| loan_to_inc | (0.2632, 0.3333] | 49,428 | 14.97% | 17.73% | -0.2079 | -0.5116 | -3.07 | -3 |
| loan_to_inc | > 0.3333 | 47,457 | 14.38% | 21.42% | -0.4425 | -0.5116 | -6.53 | -7 |
| term | <= 36 | 299,349 | 90.69% | 13.79% | 0.0903 | -0.5285 | 1.38 | 1 |
| term | > 36 | 30,722 | 9.31% | 25.70% | -0.6812 | -0.5285 | -10.39 | -10 |
| acc_open_past_24mths | <= 1 | 49,373 | 14.96% | 10.37% | 0.4142 | -0.5848 | 6.99 | 7 |
| acc_open_past_24mths | (1, 2] | 46,993 | 14.24% | 12.09% | 0.2415 | -0.5848 | 4.07 | 4 |
| acc_open_past_24mths | (2, 3] | 51,455 | 15.59% | 13.65% | 0.1017 | -0.5848 | 1.72 | 2 |
| acc_open_past_24mths | (3, 5] | 86,775 | 26.29% | 15.47% | -0.0441 | -0.5848 | -0.74 | -1 |
| acc_open_past_24mths | (5, 7] | 50,464 | 15.29% | 17.43% | -0.1873 | -0.5848 | -3.16 | -3 |
| acc_open_past_24mths | > 7 | 39,790 | 12.05% | 20.83% | -0.4075 | -0.5848 | -6.88 | -7 |
| acc_open_past_24mths | Missing | 5,221 | 1.58% | 16.13% | -0.0938 | -0.5848 | -1.58 | -2 |
| bc_open_to_buy | <= 2,396 | 128,506 | 38.93% | 17.94% | -0.2219 | -0.1818 | -1.16 | -1 |
| bc_open_to_buy | (2,396, 8,449] | 100,030 | 30.31% | 14.85% | 0.0041 | -0.1818 | 0.02 | 0 |
| bc_open_to_buy | > 8,449 | 93,150 | 28.22% | 10.61% | 0.3888 | -0.1818 | 2.04 | 2 |
| bc_open_to_buy | Missing | 8,385 | 2.54% | 16.62% | -0.1301 | -0.1818 | -0.68 | -1 |
| log_annual_inc | <= 10.52 | 51,705 | 15.66% | 19.55% | -0.3276 | -0.2955 | -2.79 | -3 |
| log_annual_inc | (10.52, 10.8] | 53,858 | 16.32% | 17.31% | -0.1788 | -0.2955 | -1.52 | -2 |
| log_annual_inc | (10.8, 11.1] | 79,735 | 24.16% | 15.35% | -0.0351 | -0.2955 | -0.30 | 0 |
| log_annual_inc | (11.1, 11.31] | 50,755 | 15.38% | 13.83% | 0.0871 | -0.2955 | 0.74 | 1 |
| log_annual_inc | (11.31, 11.61] | 52,533 | 15.92% | 11.79% | 0.2695 | -0.2955 | 2.30 | 2 |
| log_annual_inc | > 11.61 | 41,485 | 12.57% | 10.35% | 0.4163 | -0.2955 | 3.55 | 4 |
| tot_hi_cred_lim | <= 53,148 | 99,117 | 30.03% | 17.82% | -0.2137 | -0.2245 | -1.38 | -1 |
| tot_hi_cred_lim | (53,148, 156,798] | 93,447 | 28.31% | 15.57% | -0.0523 | -0.2245 | -0.34 | 0 |
| tot_hi_cred_lim | (156,798, 234,986] | 41,750 | 12.65% | 13.51% | 0.1141 | -0.2245 | 0.74 | 1 |
| tot_hi_cred_lim | (234,986, 300,194] | 26,500 | 8.03% | 11.93% | 0.2563 | -0.2245 | 1.66 | 2 |
| tot_hi_cred_lim | (300,194, 431,415] | 29,502 | 8.94% | 10.71% | 0.3777 | -0.2245 | 2.45 | 2 |
| tot_hi_cred_lim | > 431,415 | 20,483 | 6.21% | 8.79% | 0.5973 | -0.2245 | 3.87 | 4 |
| tot_hi_cred_lim | Missing | 19,272 | 5.84% | 16.61% | -0.1290 | -0.2245 | -0.84 | -1 |
| num_tl_op_past_12m | <= 0 | 56,712 | 17.18% | 11.00% | 0.3486 | -0.1023 | 1.03 | 1 |
| num_tl_op_past_12m | (0, 1] | 82,243 | 24.92% | 12.89% | 0.1684 | -0.1023 | 0.50 | 0 |
| num_tl_op_past_12m | (1, 2] | 73,053 | 22.13% | 15.15% | -0.0201 | -0.1023 | -0.06 | 0 |
| num_tl_op_past_12m | (2, 3] | 50,501 | 15.30% | 16.80% | -0.1430 | -0.1023 | -0.42 | 0 |
| num_tl_op_past_12m | > 3 | 48,290 | 14.63% | 19.84% | -0.3465 | -0.1023 | -1.02 | -1 |
| num_tl_op_past_12m | Missing | 19,272 | 5.84% | 16.61% | -0.1290 | -0.1023 | -0.38 | 0 |
| dti | <= 11.65 | 84,294 | 25.54% | 11.62% | 0.2861 | -0.4195 | 3.46 | 3 |
| dti | (11.65, 17.11] | 80,650 | 24.43% | 13.30% | 0.1322 | -0.4195 | 1.60 | 2 |
| dti | (17.11, 21.74] | 64,496 | 19.54% | 15.51% | -0.0474 | -0.4195 | -0.57 | -1 |
| dti | (21.74, 25.16] | 38,066 | 11.53% | 17.06% | -0.1610 | -0.4195 | -1.95 | -2 |
| dti | > 25.16 | 62,565 | 18.96% | 19.43% | -0.3203 | -0.4195 | -3.88 | -4 |
| total_rev_hi_lim | <= 6,600 | 22,028 | 6.67% | 18.54% | -0.2627 | -0.1881 | -1.43 | -1 |
| total_rev_hi_lim | (6,600, 18,000] | 102,697 | 31.11% | 16.67% | -0.1333 | -0.1881 | -0.72 | -1 |
| total_rev_hi_lim | (18,000, 23,216] | 39,735 | 12.04% | 15.60% | -0.0542 | -0.1881 | -0.29 | 0 |
| total_rev_hi_lim | (23,216, 37,900] | 71,579 | 21.69% | 14.38% | 0.0412 | -0.1881 | 0.22 | 0 |
| total_rev_hi_lim | (37,900, 55,900] | 40,344 | 12.22% | 12.44% | 0.2092 | -0.1881 | 1.14 | 1 |
| total_rev_hi_lim | > 55,900 | 34,416 | 10.43% | 9.47% | 0.5147 | -0.1881 | 2.79 | 3 |
| total_rev_hi_lim | Missing | 19,272 | 5.84% | 16.61% | -0.1290 | -0.1881 | -0.70 | -1 |
| mo_sin_rcnt_tl | <= 1 | 30,622 | 9.28% | 18.50% | -0.2599 | -0.0541 | -0.41 | 0 |
| mo_sin_rcnt_tl | (1, 3] | 64,147 | 19.43% | 17.18% | -0.1697 | -0.0541 | -0.27 | 0 |
| mo_sin_rcnt_tl | (3, 7] | 95,765 | 29.01% | 15.19% | -0.0230 | -0.0541 | -0.04 | 0 |
| mo_sin_rcnt_tl | (7, 13] | 71,222 | 21.58% | 13.28% | 0.1336 | -0.0541 | 0.21 | 0 |
| mo_sin_rcnt_tl | (13, 22] | 31,266 | 9.47% | 11.49% | 0.2992 | -0.0541 | 0.47 | 0 |
| mo_sin_rcnt_tl | > 22 | 17,777 | 5.39% | 9.49% | 0.5127 | -0.0541 | 0.80 | 1 |
| mo_sin_rcnt_tl | Missing | 19,272 | 5.84% | 16.61% | -0.1290 | -0.0541 | -0.20 | 0 |
| percent_bc_gt_75 | <= 0 | 58,860 | 17.83% | 11.25% | 0.3225 | -0.1208 | 1.12 | 1 |
| percent_bc_gt_75 | (0, 26.7] | 39,576 | 11.99% | 12.69% | 0.1863 | -0.1208 | 0.65 | 1 |
| percent_bc_gt_75 | (26.7, 50] | 81,970 | 24.83% | 14.47% | 0.0342 | -0.1208 | 0.12 | 0 |
| percent_bc_gt_75 | (50, 83.3] | 71,318 | 21.61% | 16.59% | -0.1277 | -0.1208 | -0.45 | 0 |
| percent_bc_gt_75 | > 83.3 | 69,851 | 21.16% | 17.80% | -0.2123 | -0.1208 | -0.74 | -1 |
| percent_bc_gt_75 | Missing | 8,496 | 2.57% | 16.56% | -0.1255 | -0.1208 | -0.44 | 0 |
| inq_last_6mths | <= 0 | 178,636 | 54.12% | 12.95% | 0.1624 | -0.3084 | 1.45 | 1 |
| inq_last_6mths | (0, 1] | 91,969 | 27.86% | 16.00% | -0.0845 | -0.3084 | -0.75 | -1 |
| inq_last_6mths | (1, 2] | 37,743 | 11.43% | 18.38% | -0.2517 | -0.3084 | -2.24 | -2 |
| inq_last_6mths | > 2 | 21,723 | 6.58% | 20.17% | -0.3667 | -0.3084 | -3.26 | -3 |
| mort_acc | <= 0 | 137,007 | 41.51% | 17.29% | -0.1772 | -0.1911 | -0.98 | -1 |
| mort_acc | (0, 1] | 52,801 | 16.00% | 14.82% | 0.0061 | -0.1911 | 0.03 | 0 |
| mort_acc | (1, 2] | 42,862 | 12.99% | 13.44% | 0.1204 | -0.1911 | 0.66 | 1 |
| mort_acc | (2, 4] | 56,673 | 17.17% | 12.45% | 0.2084 | -0.1911 | 1.15 | 1 |
| mort_acc | > 4 | 35,507 | 10.76% | 11.30% | 0.3182 | -0.1911 | 1.75 | 2 |
| mort_acc | Missing | 5,221 | 1.58% | 16.13% | -0.0938 | -0.1911 | -0.52 | -1 |
| verification_status | {Not Verified} | 111,190 | 33.69% | 12.08% | 0.2427 | -0.2387 | 1.67 | 2 |
| verification_status | {Source Verified} | 106,649 | 32.31% | 15.15% | -0.0198 | -0.2387 | -0.14 | 0 |
| verification_status | {Verified} | 112,232 | 34.00% | 17.45% | -0.1889 | -0.2387 | -1.30 | -1 |
| mths_since_recent_bc | <= 3 | 42,266 | 12.81% | 18.28% | -0.2454 | -0.3255 | -2.30 | -2 |
| mths_since_recent_bc | (3, 14] | 123,612 | 37.45% | 15.87% | -0.0748 | -0.3255 | -0.70 | -1 |
| mths_since_recent_bc | (14, 23] | 52,179 | 15.81% | 14.80% | 0.0074 | -0.3255 | 0.07 | 0 |
| mths_since_recent_bc | (23, 37] | 40,336 | 12.22% | 13.52% | 0.1128 | -0.3255 | 1.06 | 1 |
| mths_since_recent_bc | (37, 68] | 35,211 | 10.67% | 12.16% | 0.2350 | -0.3255 | 2.21 | 2 |
| mths_since_recent_bc | > 68 | 28,370 | 8.60% | 10.68% | 0.3816 | -0.3255 | 3.58 | 4 |
| mths_since_recent_bc | Missing | 8,097 | 2.45% | 16.54% | -0.1238 | -0.3255 | -1.16 | -1 |
| home_ownership | {OTHER_RARE, MORTGAGE} | 159,173 | 48.22% | 12.78% | 0.1778 | -0.3784 | 1.94 | 2 |
| home_ownership | {OWN} | 31,615 | 9.58% | 15.43% | -0.0410 | -0.3784 | -0.45 | 0 |
| home_ownership | {RENT} | 139,283 | 42.20% | 17.20% | -0.1709 | -0.3784 | -1.87 | -2 |
| mo_sin_old_rev_tl_op | <= 82 | 33,105 | 10.03% | 19.56% | -0.3287 | -0.2540 | -2.41 | -2 |
| mo_sin_old_rev_tl_op | (82, 115] | 44,700 | 13.54% | 16.40% | -0.1140 | -0.2540 | -0.84 | -1 |
| mo_sin_old_rev_tl_op | (115, 154] | 62,369 | 18.90% | 15.39% | -0.0379 | -0.2540 | -0.28 | 0 |
| mo_sin_old_rev_tl_op | (154, 233] | 97,907 | 29.66% | 13.97% | 0.0754 | -0.2540 | 0.55 | 1 |
| mo_sin_old_rev_tl_op | > 233 | 72,718 | 22.03% | 12.23% | 0.2279 | -0.2540 | 1.67 | 2 |
| mo_sin_old_rev_tl_op | Missing | 19,272 | 5.84% | 16.61% | -0.1290 | -0.2540 | -0.95 | -1 |
| num_rev_tl_bal_gt_0 | <= 2 | 34,285 | 10.39% | 11.89% | 0.2604 | -0.2966 | 2.23 | 2 |
| num_rev_tl_bal_gt_0 | (2, 3] | 42,309 | 12.82% | 13.00% | 0.1584 | -0.2966 | 1.36 | 1 |
| num_rev_tl_bal_gt_0 | (3, 5] | 96,433 | 29.22% | 14.17% | 0.0590 | -0.2966 | 0.50 | 1 |
| num_rev_tl_bal_gt_0 | (5, 7] | 68,586 | 20.78% | 15.47% | -0.0442 | -0.2966 | -0.38 | 0 |
| num_rev_tl_bal_gt_0 | (7, 8] | 21,549 | 6.53% | 16.56% | -0.1256 | -0.2966 | -1.07 | -1 |
| num_rev_tl_bal_gt_0 | > 8 | 47,637 | 14.43% | 17.97% | -0.2241 | -0.2966 | -1.92 | -2 |
| num_rev_tl_bal_gt_0 | Missing | 19,272 | 5.84% | 16.61% | -0.1290 | -0.2966 | -1.10 | -1 |

![[含平台评级] 图 4.1 分数分布（test，good / bad 分开）](figures/07_score_dist_with_platform_rating_test.png)

_[含平台评级] 图 4.1 分数分布（test，good / bad 分开）_

![[含平台评级] 图 4.2 分数分布（OOT，good / bad 分开）](figures/07_score_dist_with_platform_rating_oot.png)

_[含平台评级] 图 4.2 分数分布（OOT，good / bad 分开）_

## 5. 策略分析

_在 test 与 OOT 上评估评分卡的业务用法：分数段表、通过率–坏账率曲线、候选 cut-off、用实际回款算的利润曲线，以及与平台基准的 swap set。_

### 5.0 口径

- **评分方向与通过规则**：分数越高越安全；cut-off 规则为 score ≥ cut-off 通过。分数为整数，所以每个候选通过率取实际通过率最接近的 cut-off，并同时报告实际通过率
- **评估样本**：test / OOT（train 不参与策略评估）
- **候选通过率**：50% / 60% / 70% / 80% / 90%
- **利润口径**：net_cash = total_pymnt - collection_recovery_fee - funded_amnt（实际回款减放款本金；仅策略层使用）。这是用贷后实际结果做的策略评估，不是预测；净现金为名义金额，未折现、未扣资金成本与运营成本
- **swap set 基准**：平台评级 grade 从最好一档往下批，批到与模型 cut-off 相同的通过人数（边际一档内按固定种子随机排序）
- **swap set 展示的 cut-off**：候选通过率中最接近 70% 的一档（其余通过率见汇总表）

### [不含平台评级] 5.1 分数段表（test，等频 10 段，分数从高到低）

| 分段 | 分数区间 | 人数 | 占比 | bad 数 | bad rate | 累计通过率 | 累计 bad rate | 净现金/笔 |
|---|---|---|---|---|---|---|---|---|
| 1 | 594–639 | 13,246 | 9.36% | 516 | 3.90% | 9.36% | 3.90% | 1,380 |
| 2 | 584–593 | 14,701 | 10.39% | 986 | 6.71% | 19.76% | 5.37% | 1,454 |
| 3 | 578–583 | 13,196 | 9.33% | 1,193 | 9.04% | 29.08% | 6.55% | 1,375 |
| 4 | 573–577 | 12,892 | 9.11% | 1,325 | 10.28% | 38.20% | 7.44% | 1,382 |
| 5 | 568–572 | 14,318 | 10.12% | 1,748 | 12.21% | 48.32% | 8.44% | 1,335 |
| 6 | 563–567 | 15,348 | 10.85% | 2,248 | 14.65% | 59.17% | 9.58% | 1,288 |
| 7 | 558–562 | 14,678 | 10.38% | 2,443 | 16.64% | 69.55% | 10.63% | 1,234 |
| 8 | 553–557 | 12,879 | 9.10% | 2,484 | 19.29% | 78.65% | 11.63% | 1,274 |
| 9 | 545–552 | 15,269 | 10.79% | 3,495 | 22.89% | 89.44% | 12.99% | 1,312 |
| 10 | 499–544 | 14,933 | 10.56% | 4,638 | 31.06% | 100.00% | 14.90% | 1,665 |

_累计通过率 / 累计 bad rate = 以该段下边界为 cut-off 时的通过率与通过客群 bad rate。按分数分位数切段，整数分数有并列，各段人数近似相等。_

### [不含平台评级] 5.1 分数段表（OOT，等频 10 段，分数从高到低）

| 分段 | 分数区间 | 人数 | 占比 | bad 数 | bad rate | 累计通过率 | 累计 bad rate | 净现金/笔 |
|---|---|---|---|---|---|---|---|---|
| 1 | 597–638 | 16,072 | 9.91% | 564 | 3.51% | 9.91% | 3.51% | 1,248 |
| 2 | 588–596 | 14,806 | 9.13% | 960 | 6.48% | 19.03% | 4.94% | 1,145 |
| 3 | 581–587 | 16,592 | 10.23% | 1,524 | 9.19% | 29.26% | 6.42% | 1,037 |
| 4 | 576–580 | 14,296 | 8.81% | 1,477 | 10.33% | 38.07% | 7.33% | 993 |
| 5 | 571–575 | 16,174 | 9.97% | 1,971 | 12.19% | 48.04% | 8.33% | 929 |
| 6 | 566–570 | 16,827 | 10.37% | 2,340 | 13.91% | 58.41% | 9.32% | 826 |
| 7 | 561–565 | 16,947 | 10.45% | 2,760 | 16.29% | 68.86% | 10.38% | 728 |
| 8 | 556–560 | 15,300 | 9.43% | 2,913 | 19.04% | 78.29% | 11.42% | 609 |
| 9 | 548–555 | 18,888 | 11.64% | 4,368 | 23.13% | 89.93% | 12.94% | 423 |
| 10 | 512–547 | 16,334 | 10.07% | 4,986 | 30.53% | 100.00% | 14.71% | 73 |

![[不含平台评级] 图 5.1 通过率–坏账率曲线（点 = 候选 cut-off）](figures/08_approval_curve_no_platform_rating.png)

_[不含平台评级] 图 5.1 通过率–坏账率曲线（点 = 候选 cut-off）_

### [不含平台评级] 5.2 候选 cut-off（test；样本 bad rate 14.90%）

| 目标通过率 | cut-off | 实际通过率 | 通过人数 | 通过客群 bad rate | 拒绝客群 bad rate | 边际新增人数 | 边际 bad rate | 总净现金 | 净现金/笔 | 边际净现金/笔 |
|---|---|---|---|---|---|---|---|---|---|---|
| 50.00% | 567 | 50.45% | 71,367 | 8.65% | 21.26% | 71,367 | 8.65% | 98,799,979 | 1,384 | 1,384 |
| 60.00% | 563 | 59.17% | 83,701 | 9.58% | 22.61% | 12,334 | 14.92% | 114,505,209 | 1,368 | 1,273 |
| 70.00% | 558 | 69.55% | 98,379 | 10.63% | 24.64% | 14,678 | 16.64% | 132,613,687 | 1,348 | 1,234 |
| 80.00% | 552 | 80.26% | 113,530 | 11.81% | 27.47% | 15,151 | 19.44% | 151,990,166 | 1,339 | 1,279 |
| 90.00% | 544 | 90.42% | 127,915 | 13.14% | 31.52% | 14,385 | 23.64% | 170,983,969 | 1,337 | 1,320 |

_边际 = 比上一档宽松的 cut-off 多放进来的那一批客户；边际 bad rate 和边际净现金/笔决定了再放松一档是否划算。_

### [不含平台评级] 5.2 候选 cut-off（OOT；样本 bad rate 14.71%）

| 目标通过率 | cut-off | 实际通过率 | 通过人数 | 通过客群 bad rate | 拒绝客群 bad rate | 边际新增人数 | 边际 bad rate | 总净现金 | 净现金/笔 | 边际净现金/笔 |
|---|---|---|---|---|---|---|---|---|---|---|
| 50.00% | 570 | 50.06% | 81,212 | 8.50% | 20.93% | 81,212 | 8.50% | 86,416,718 | 1,064 | 1,064 |
| 60.00% | 565 | 60.58% | 98,284 | 9.55% | 22.64% | 17,072 | 14.50% | 99,983,967 | 1,017 | 795 |
| 70.00% | 560 | 70.88% | 114,987 | 10.60% | 24.71% | 16,703 | 16.80% | 111,763,192 | 972 | 705 |
| 80.00% | 555 | 80.02% | 129,823 | 11.65% | 26.95% | 14,836 | 19.82% | 120,373,020 | 927 | 580 |
| 90.00% | 548 | 89.93% | 145,902 | 12.94% | 30.53% | 16,079 | 23.31% | 126,999,862 | 870 | 412 |

![[不含平台评级] 图 5.2 利润曲线（左：总净现金；右：每笔净现金）](figures/09_profit_curve_no_platform_rating.png)

_[不含平台评级] 图 5.2 利润曲线（左：总净现金；右：每笔净现金）_

### [不含平台评级] 5.3 利润最大化 cut-off（总净现金 vs 每笔净现金，并列报告）

| 样本 | 准则 | cut-off | 实际通过率 | 通过人数 | 通过客群 bad rate | 总净现金 | 净现金/笔 |
|---|---|---|---|---|---|---|---|
| test | 总净现金最大 | 499 | 100.00% | 141,460 | 14.90% | 193,930,239 | 1,371 |
| test | 每笔净现金最大 | 584 | 19.76% | 27,947 | 5.37% | 39,655,053 | 1,419 |
| test | 全部通过（参照） | 499 | 100.00% | 141,460 | 14.90% | 193,930,239 | 1,371 |
| OOT | 总净现金最大 | 535 | 98.60% | 159,964 | 14.35% | 129,027,554 | 807 |
| OOT | 每笔净现金最大 | 596 | 10.74% | 17,425 | 3.68% | 21,593,049 | 1,239 |
| OOT | 全部通过（参照） | 512 | 100.00% | 162,236 | 14.71% | 128,191,612 | 790 |

_净现金来自实际回款（见 5.0 口径）。每笔净现金最大的 cut-off 只在通过率 ≥ 10% 的范围内搜索，避免只剩几十个高分客户时的噪声。总净现金最大的 cut-off 通常比坏账率最低的 cut-off 宽松得多：多放进来的一档客户只要利息收入高于损失，总额就继续上升（风险定价越充分，越接近全部通过）。_

### [不含平台评级] 5.4 swap set（test；cut-off 558，通过率 69.5%，目标 70%）

| 模型 \ 基准 | 基准批 | 基准拒 | 合计 |
|---|---|---|---|
| 模型批（score ≥ cut-off） | 79,557 笔 · bad rate 9.04% · 净现金/笔 1,294 | 18,822 笔 · bad rate 17.38% · 净现金/笔 1,578  ← swap-in | 98,379 笔 · bad rate 10.63% · 净现金/笔 1,348 |
| 模型拒 | 18,822 笔 · bad rate 20.16% · 净现金/笔 1,085  ← swap-out | 24,259 笔 · bad rate 28.12% · 净现金/笔 1,686 | 43,081 笔 · bad rate 24.64% · 净现金/笔 1,423 |
| 合计 | 98,379 笔 · bad rate 11.16% · 净现金/笔 1,254 | 43,081 笔 · bad rate 23.43% · 净现金/笔 1,639 | 141,460 笔 · bad rate 14.90% · 净现金/笔 1,371 |

_swap-in（模型批、基准拒）18,822 笔，bad rate 17.38%；swap-out（模型拒、基准批）18,822 笔，bad rate 20.16%。两格人数相同，模型换进了更好的客户；同通过率下模型通过客群 bad rate 10.63%，基准（平台评级） 11.16%（-0.53 pp）。 通过客群净现金：模型 132,613,687，基准 123,338,807。_

### [不含平台评级] 5.4 swap set（OOT；cut-off 560，通过率 70.9%，目标 70%）

| 模型 \ 基准 | 基准批 | 基准拒 | 合计 |
|---|---|---|---|
| 模型批（score ≥ cut-off） | 93,344 笔 · bad rate 8.74% · 净现金/笔 992 | 21,643 笔 · bad rate 18.63% · 净现金/笔 887  ← swap-in | 114,987 笔 · bad rate 10.60% · 净现金/笔 972 |
| 模型拒 | 21,643 笔 · bad rate 19.97% · 净现金/笔 474  ← swap-out | 25,606 笔 · bad rate 28.71% · 净现金/笔 241 | 47,249 笔 · bad rate 24.71% · 净现金/笔 348 |
| 合计 | 114,987 笔 · bad rate 10.85% · 净现金/笔 894 | 47,249 笔 · bad rate 24.09% · 净现金/笔 537 | 162,236 笔 · bad rate 14.71% · 净现金/笔 790 |

_swap-in（模型批、基准拒）21,643 笔，bad rate 18.63%；swap-out（模型拒、基准批）21,643 笔，bad rate 19.97%。两格人数相同，模型换进了更好的客户；同通过率下模型通过客群 bad rate 10.60%，基准（平台评级） 10.85%（-0.25 pp）。 通过客群净现金：模型 111,763,192，基准 102,837,845。_

### [不含平台评级] 各候选通过率下的 swap set 汇总

| 样本 | 目标通过率 | cut-off | 实际通过率 | 模型通过客群 bad rate | 基准通过客群 bad rate | swap-in 人数 | swap-in bad rate | swap-out 人数 | swap-out bad rate | 模型通过客群净现金 | 基准通过客群净现金 |
|---|---|---|---|---|---|---|---|---|---|---|---|
| test | 50.00% | 567 | 50.45% | 8.65% | 8.84% | 19,566 | 13.46% | 19,566 | 14.15% | 98,799,979 | 85,122,616 |
| test | 60.00% | 563 | 59.17% | 9.58% | 9.95% | 20,080 | 15.42% | 20,080 | 16.97% | 114,505,209 | 102,749,224 |
| test | 70.00% | 558 | 69.55% | 10.63% | 11.16% | 18,822 | 17.38% | 18,822 | 20.16% | 132,613,687 | 123,338,807 |
| test | 80.00% | 552 | 80.26% | 11.81% | 12.19% | 14,398 | 20.39% | 14,398 | 23.40% | 151,990,166 | 144,228,581 |
| test | 90.00% | 544 | 90.42% | 13.14% | 13.49% | 8,331 | 23.47% | 8,331 | 28.90% | 170,983,969 | 164,034,627 |
| OOT | 50.00% | 570 | 50.06% | 8.50% | 8.50% | 23,952 | 13.79% | 23,952 | 13.79% | 86,416,718 | 76,718,327 |
| OOT | 60.00% | 565 | 60.58% | 9.55% | 9.35% | 22,636 | 16.67% | 22,636 | 15.83% | 99,983,967 | 90,821,679 |
| OOT | 70.00% | 560 | 70.88% | 10.60% | 10.85% | 21,643 | 18.63% | 21,643 | 19.97% | 111,763,192 | 102,837,845 |
| OOT | 80.00% | 555 | 80.02% | 11.65% | 11.87% | 17,954 | 21.37% | 17,954 | 22.95% | 120,373,020 | 113,384,497 |
| OOT | 90.00% | 548 | 89.93% | 12.94% | 13.07% | 11,071 | 25.69% | 11,071 | 27.41% | 126,999,862 | 122,848,332 |

### [含平台评级] 5.1 分数段表（test，等频 10 段，分数从高到低）

| 分段 | 分数区间 | 人数 | 占比 | bad 数 | bad rate | 累计通过率 | 累计 bad rate | 净现金/笔 |
|---|---|---|---|---|---|---|---|---|
| 1 | 600–638 | 13,543 | 9.57% | 466 | 3.44% | 9.57% | 3.44% | 1,193 |
| 2 | 589–599 | 13,560 | 9.59% | 845 | 6.23% | 19.16% | 4.84% | 1,249 |
| 3 | 581–588 | 14,246 | 10.07% | 1,110 | 7.79% | 29.23% | 5.86% | 1,376 |
| 4 | 575–580 | 13,003 | 9.19% | 1,273 | 9.79% | 38.42% | 6.80% | 1,376 |
| 5 | 569–574 | 14,666 | 10.37% | 1,749 | 11.93% | 48.79% | 7.89% | 1,370 |
| 6 | 563–568 | 15,590 | 11.02% | 2,259 | 14.49% | 59.81% | 9.10% | 1,352 |
| 7 | 558–562 | 12,948 | 9.15% | 2,192 | 16.93% | 68.96% | 10.14% | 1,327 |
| 8 | 552–557 | 14,046 | 9.93% | 2,851 | 20.30% | 78.89% | 11.42% | 1,273 |
| 9 | 544–551 | 14,525 | 10.27% | 3,432 | 23.63% | 89.16% | 12.83% | 1,410 |
| 10 | 505–543 | 15,333 | 10.84% | 4,899 | 31.95% | 100.00% | 14.90% | 1,736 |

_累计通过率 / 累计 bad rate = 以该段下边界为 cut-off 时的通过率与通过客群 bad rate。按分数分位数切段，整数分数有并列，各段人数近似相等。_

### [含平台评级] 5.1 分数段表（OOT，等频 10 段，分数从高到低）

| 分段 | 分数区间 | 人数 | 占比 | bad 数 | bad rate | 累计通过率 | 累计 bad rate | 净现金/笔 |
|---|---|---|---|---|---|---|---|---|
| 1 | 604–635 | 15,315 | 9.44% | 449 | 2.93% | 9.44% | 2.93% | 1,120 |
| 2 | 593–603 | 16,013 | 9.87% | 831 | 5.19% | 19.31% | 4.09% | 1,100 |
| 3 | 585–592 | 15,729 | 9.70% | 1,216 | 7.73% | 29.01% | 5.30% | 1,040 |
| 4 | 578–584 | 17,181 | 10.59% | 1,668 | 9.71% | 39.60% | 6.48% | 986 |
| 5 | 572–577 | 16,750 | 10.32% | 2,034 | 12.14% | 49.92% | 7.65% | 904 |
| 6 | 567–571 | 14,680 | 9.05% | 2,064 | 14.06% | 58.97% | 8.64% | 862 |
| 7 | 561–566 | 17,499 | 10.79% | 2,951 | 16.86% | 69.75% | 9.91% | 765 |
| 8 | 555–560 | 16,383 | 10.10% | 3,290 | 20.08% | 79.85% | 11.19% | 684 |
| 9 | 548–554 | 15,112 | 9.31% | 3,678 | 24.34% | 89.17% | 12.57% | 411 |
| 10 | 513–547 | 17,574 | 10.83% | 5,682 | 32.33% | 100.00% | 14.71% | 85 |

![[含平台评级] 图 5.1 通过率–坏账率曲线（点 = 候选 cut-off）](figures/08_approval_curve_with_platform_rating.png)

_[含平台评级] 图 5.1 通过率–坏账率曲线（点 = 候选 cut-off）_

### [含平台评级] 5.2 候选 cut-off（test；样本 bad rate 14.90%）

| 目标通过率 | cut-off | 实际通过率 | 通过人数 | 通过客群 bad rate | 拒绝客群 bad rate | 边际新增人数 | 边际 bad rate | 总净现金 | 净现金/笔 | 边际净现金/笔 |
|---|---|---|---|---|---|---|---|---|---|---|
| 50.00% | 568 | 50.54% | 71,498 | 8.11% | 21.84% | 71,498 | 8.11% | 93,736,139 | 1,311 | 1,311 |
| 60.00% | 563 | 59.81% | 84,608 | 9.10% | 23.52% | 13,110 | 14.54% | 111,760,963 | 1,321 | 1,375 |
| 70.00% | 557 | 70.74% | 100,071 | 10.34% | 25.91% | 15,463 | 17.14% | 132,425,916 | 1,323 | 1,336 |
| 80.00% | 551 | 80.38% | 113,705 | 11.61% | 28.36% | 13,634 | 20.93% | 149,809,087 | 1,318 | 1,275 |
| 90.00% | 543 | 90.16% | 127,544 | 12.98% | 32.49% | 13,839 | 24.19% | 169,726,468 | 1,331 | 1,439 |

_边际 = 比上一档宽松的 cut-off 多放进来的那一批客户；边际 bad rate 和边际净现金/笔决定了再放松一档是否划算。_

### [含平台评级] 5.2 候选 cut-off（OOT；样本 bad rate 14.71%）

| 目标通过率 | cut-off | 实际通过率 | 通过人数 | 通过客群 bad rate | 拒绝客群 bad rate | 边际新增人数 | 边际 bad rate | 总净现金 | 净现金/笔 | 边际净现金/笔 |
|---|---|---|---|---|---|---|---|---|---|---|
| 50.00% | 572 | 49.92% | 80,988 | 7.65% | 21.74% | 80,988 | 7.65% | 83,237,563 | 1,028 | 1,028 |
| 60.00% | 566 | 60.78% | 98,599 | 8.81% | 23.85% | 17,611 | 14.14% | 98,554,427 | 1,000 | 870 |
| 70.00% | 561 | 69.75% | 113,167 | 9.91% | 25.78% | 14,568 | 17.33% | 109,275,649 | 966 | 736 |
| 80.00% | 555 | 79.85% | 129,550 | 11.19% | 28.64% | 16,383 | 20.08% | 120,482,912 | 930 | 684 |
| 90.00% | 547 | 90.20% | 146,340 | 12.72% | 33.00% | 16,790 | 24.50% | 127,391,514 | 871 | 411 |

![[含平台评级] 图 5.2 利润曲线（左：总净现金；右：每笔净现金）](figures/09_profit_curve_with_platform_rating.png)

_[含平台评级] 图 5.2 利润曲线（左：总净现金；右：每笔净现金）_

### [含平台评级] 5.3 利润最大化 cut-off（总净现金 vs 每笔净现金，并列报告）

| 样本 | 准则 | cut-off | 实际通过率 | 通过人数 | 通过客群 bad rate | 总净现金 | 净现金/笔 |
|---|---|---|---|---|---|---|---|
| test | 总净现金最大 | 508 | 100.00% | 141,458 | 14.90% | 193,938,771 | 1,371 |
| test | 每笔净现金最大 | 508 | 100.00% | 141,458 | 14.90% | 193,938,771 | 1,371 |
| test | 全部通过（参照） | 505 | 100.00% | 141,460 | 14.90% | 193,930,239 | 1,371 |
| OOT | 总净现金最大 | 533 | 98.64% | 160,027 | 14.32% | 129,223,126 | 808 |
| OOT | 每笔净现金最大 | 603 | 10.22% | 16,583 | 3.03% | 18,520,351 | 1,117 |
| OOT | 全部通过（参照） | 513 | 100.00% | 162,236 | 14.71% | 128,191,612 | 790 |

_净现金来自实际回款（见 5.0 口径）。每笔净现金最大的 cut-off 只在通过率 ≥ 10% 的范围内搜索，避免只剩几十个高分客户时的噪声。总净现金最大的 cut-off 通常比坏账率最低的 cut-off 宽松得多：多放进来的一档客户只要利息收入高于损失，总额就继续上升（风险定价越充分，越接近全部通过）。_

### [含平台评级] 5.4 swap set（test；cut-off 557，通过率 70.7%，目标 70%）

| 模型 \ 基准 | 基准批 | 基准拒 | 合计 |
|---|---|---|---|
| 模型批（score ≥ cut-off） | 86,810 笔 · bad rate 9.52% · 净现金/笔 1,273 | 13,261 笔 · bad rate 15.75% · 净现金/笔 1,653  ← swap-in | 100,071 笔 · bad rate 10.34% · 净现金/笔 1,323 |
| 模型拒 | 13,261 笔 · bad rate 22.98% · 净现金/笔 1,133  ← swap-out | 28,128 笔 · bad rate 27.29% · 净现金/笔 1,653 | 41,389 笔 · bad rate 25.91% · 净现金/笔 1,486 |
| 合计 | 100,071 笔 · bad rate 11.30% · 净现金/笔 1,254 | 41,389 笔 · bad rate 23.59% · 净现金/笔 1,653 | 141,460 笔 · bad rate 14.90% · 净现金/笔 1,371 |

_swap-in（模型批、基准拒）13,261 笔，bad rate 15.75%；swap-out（模型拒、基准批）13,261 笔，bad rate 22.98%。两格人数相同，模型换进了更好的客户；同通过率下模型通过客群 bad rate 10.34%，基准（平台评级） 11.30%（-0.96 pp）。 通过客群净现金：模型 132,425,916，基准 125,531,940。_

### [含平台评级] 5.4 swap set（OOT；cut-off 561，通过率 69.8%，目标 70%）

| 模型 \ 基准 | 基准批 | 基准拒 | 合计 |
|---|---|---|---|
| 模型批（score ≥ cut-off） | 97,793 笔 · bad rate 8.91% · 净现金/笔 963 | 15,374 笔 · bad rate 16.25% · 净现金/笔 984  ← swap-in | 113,167 笔 · bad rate 9.91% · 净现金/笔 966 |
| 模型拒 | 15,374 笔 · bad rate 22.09% · 净现金/笔 482  ← swap-out | 33,695 笔 · bad rate 27.46% · 净现金/笔 342 | 49,069 笔 · bad rate 25.78% · 净现金/笔 385 |
| 合计 | 113,167 笔 · bad rate 10.70% · 净现金/笔 897 | 49,069 笔 · bad rate 23.95% · 净现金/笔 543 | 162,236 笔 · bad rate 14.71% · 净现金/笔 790 |

_swap-in（模型批、基准拒）15,374 笔，bad rate 16.25%；swap-out（模型拒、基准批）15,374 笔，bad rate 22.09%。两格人数相同，模型换进了更好的客户；同通过率下模型通过客群 bad rate 9.91%，基准（平台评级） 10.70%（-0.79 pp）。 通过客群净现金：模型 109,275,649，基准 101,548,831。_

### [含平台评级] 各候选通过率下的 swap set 汇总

| 样本 | 目标通过率 | cut-off | 实际通过率 | 模型通过客群 bad rate | 基准通过客群 bad rate | swap-in 人数 | swap-in bad rate | swap-out 人数 | swap-out bad rate | 模型通过客群净现金 | 基准通过客群净现金 |
|---|---|---|---|---|---|---|---|---|---|---|---|
| test | 50.00% | 568 | 50.54% | 8.11% | 8.85% | 12,029 | 11.42% | 12,029 | 15.86% | 93,736,139 | 85,266,409 |
| test | 60.00% | 563 | 59.81% | 9.10% | 10.02% | 13,499 | 13.50% | 13,499 | 19.28% | 111,760,963 | 104,022,582 |
| test | 70.00% | 557 | 70.74% | 10.34% | 11.30% | 13,261 | 15.75% | 13,261 | 22.98% | 132,425,916 | 125,531,940 |
| test | 80.00% | 551 | 80.38% | 11.61% | 12.21% | 9,982 | 18.89% | 9,982 | 25.65% | 149,809,087 | 144,503,329 |
| test | 90.00% | 543 | 90.16% | 12.98% | 13.46% | 6,747 | 21.73% | 6,747 | 30.77% | 169,726,468 | 163,474,663 |
| OOT | 50.00% | 572 | 49.92% | 7.65% | 8.50% | 16,350 | 11.19% | 16,350 | 15.39% | 83,237,563 | 76,464,408 |
| OOT | 60.00% | 566 | 60.78% | 8.81% | 9.39% | 13,927 | 14.50% | 13,927 | 18.58% | 98,554,427 | 91,030,591 |
| OOT | 70.00% | 561 | 69.75% | 9.91% | 10.70% | 15,374 | 16.25% | 15,374 | 22.09% | 109,275,649 | 101,548,831 |
| OOT | 80.00% | 555 | 79.85% | 11.19% | 11.85% | 12,940 | 18.86% | 12,940 | 25.46% | 120,482,912 | 113,250,909 |
| OOT | 90.00% | 547 | 90.20% | 12.72% | 13.10% | 7,862 | 23.86% | 7,862 | 30.83% | 127,391,514 | 123,243,186 |

### 5.5 两套模型对比：同通过率下的通过客群 bad rate（不含平台评级 vs 含平台评级）

| 样本 | 目标通过率 | cut-off（不含平台评级） | bad rate（不含平台评级） | cut-off（含平台评级） | bad rate（含平台评级） | 差（pp） |
|---|---|---|---|---|---|---|
| test | 50.00% | 567 | 8.65% | 568 | 8.11% | -0.55 |
| test | 60.00% | 563 | 9.58% | 563 | 9.10% | -0.47 |
| test | 70.00% | 558 | 10.63% | 557 | 10.34% | -0.29 |
| test | 80.00% | 552 | 11.81% | 551 | 11.61% | -0.19 |
| test | 90.00% | 544 | 13.14% | 543 | 12.98% | -0.16 |
| OOT | 50.00% | 570 | 8.50% | 572 | 7.65% | -0.85 |
| OOT | 60.00% | 565 | 9.55% | 566 | 8.81% | -0.73 |
| OOT | 70.00% | 560 | 10.60% | 561 | 9.91% | -0.69 |
| OOT | 80.00% | 555 | 11.65% | 555 | 11.19% | -0.46 |
| OOT | 90.00% | 548 | 12.94% | 547 | 12.72% | -0.22 |

_两套模型的 cut-off 不可比（分数刻度相同但变量不同），应比较同通过率下的 bad rate。_

## 6. 稳定性

_分数与入模特征在 train → test / OOT 上的分布稳定性（PSI / CSI），以及按 issue 季度的 vintage 曲线。_

### 6.0 口径

- **PSI 公式**：PSI = Σ (actual% − expected%) × ln(actual% / expected%)，expected = train；占比为 0 的段按 0.01% 处理
- **score PSI 分段**：train 分数的 10 等频段（右闭区间），同一套边界套到 test / OOT
- **CSI**：每个入模特征按评分卡的分箱（含缺失箱）算分布的 PSI，train → test 与 train → OOT
- **阈值**：🟢 稳定 < 0.10 ≤ 🟡 关注 < 0.25 ≤ 🔴 警戒（行业惯例：< 0.10 不动，0.10–0.25 观察，> 0.25 需处理）

### [不含平台评级] 6.1 score PSI

| 对比 | train 行数 | 对比样本行数 | PSI | 判定 |
|---|---|---|---|---|
| train → test | 330,071 | 141,460 | 0.0001 | 🟢 稳定 |
| train → OOT | 330,071 | 162,236 | 0.0271 | 🟢 稳定 |

![[不含平台评级] 图 6.1 分数分布按 train 等频段（train vs test vs OOT）](figures/10_score_psi_no_platform_rating.png)

_[不含平台评级] 图 6.1 分数分布按 train 等频段（train vs test vs OOT）_

### [不含平台评级] score PSI 分段明细

| 段 | 分数区间 | train 占比 | test 占比 | OOT 占比 | PSI 贡献（test） | PSI 贡献（OOT） |
|---|---|---|---|---|---|---|
| 1 | <= 544 | 10.54% | 10.56% | 7.02% | 0.0000 | 0.0143 |
| 2 | (544, 552] | 10.71% | 10.79% | 9.72% | 0.0000 | 0.0010 |
| 3 | (552, 557] | 9.11% | 9.10% | 8.65% | 0.0000 | 0.0002 |
| 4 | (557, 562] | 10.28% | 10.38% | 9.75% | 0.0000 | 0.0003 |
| 5 | (562, 567] | 10.70% | 10.85% | 10.66% | 0.0000 | 0.0000 |
| 6 | (567, 572] | 10.27% | 10.12% | 10.23% | 0.0000 | 0.0000 |
| 7 | (572, 577] | 9.21% | 9.11% | 9.66% | 0.0000 | 0.0002 |
| 8 | (577, 583] | 9.25% | 9.33% | 9.78% | 0.0000 | 0.0003 |
| 9 | (583, 593] | 10.54% | 10.39% | 12.02% | 0.0000 | 0.0019 |
| 10 | > 593 | 9.39% | 9.36% | 12.51% | 0.0000 | 0.0090 |

### [不含平台评级] 6.2 入模特征 CSI（判定按 train → OOT）

| 特征 | CSI train→test | CSI train→OOT | 判定 | 偏移最大的箱 | train 占比 | OOT 占比 |
|---|---|---|---|---|---|---|
| term | 0.0001 | 0.6447 | 🔴 警戒 | <= 36 | 90.69% | 100.00% |
| num_tl_op_past_12m | 0.0001 | 0.3851 | 🔴 警戒 | Missing | 5.84% | 0.00% |
| total_rev_hi_lim | 0.0002 | 0.3831 | 🔴 警戒 | Missing | 5.84% | 0.00% |
| num_rev_tl_bal_gt_0 | 0.0001 | 0.3812 | 🔴 警戒 | Missing | 5.84% | 0.00% |
| mo_sin_old_rev_tl_op | 0.0001 | 0.3792 | 🔴 警戒 | Missing | 5.84% | 0.00% |
| tot_hi_cred_lim | 0.0001 | 0.3791 | 🔴 警戒 | Missing | 5.84% | 0.00% |
| mo_sin_rcnt_tl | 0.0001 | 0.3783 | 🔴 警戒 | Missing | 5.84% | 0.00% |
| acc_open_past_24mths | 0.0001 | 0.0912 | 🟢 稳定 | > 7 | 12.05% | 15.61% |
| mort_acc | 0.0000 | 0.0873 | 🟢 稳定 | > 4 | 10.76% | 8.45% |
| verification_status | 0.0000 | 0.0520 | 🟢 稳定 | {Source Verified} | 32.31% | 42.95% |
| percent_bc_gt_75 | 0.0001 | 0.0490 | 🟢 稳定 | <= 0 | 17.83% | 24.75% |
| revol_util | 0.0000 | 0.0318 | 🟢 稳定 | (58.8, 86.9] | 36.94% | 30.93% |
| inq_last_6mths | 0.0000 | 0.0292 | 🟢 稳定 | <= 0 | 54.12% | 61.12% |
| bc_open_to_buy | 0.0000 | 0.0285 | 🟢 稳定 | > 8,449 | 28.22% | 33.09% |
| mths_since_recent_bc | 0.0001 | 0.0155 | 🟢 稳定 | Missing | 2.45% | 0.96% |
| loan_to_inc | 0.0001 | 0.0144 | 🟢 稳定 | <= 0.1516 | 35.56% | 40.60% |
| dti | 0.0000 | 0.0108 | 🟢 稳定 | > 25.16 | 18.96% | 23.12% |
| annual_inc | 0.0000 | 0.0041 | 🟢 稳定 | > 110,000 | 12.57% | 14.49% |
| home_ownership | 0.0000 | 0.0040 | 🟢 稳定 | {OWN} | 9.58% | 11.48% |
| fico_mid | 0.0001 | 0.0034 | 🟢 稳定 | <= 672 | 27.09% | 28.63% |

_CSI 高说明该特征的客群分布变了，不一定意味着模型失效：先看 score PSI 是否稳定，再看该特征的分箱是否仍合理、含义是否变化（例如某个征信字段从某年开始才有值）。_

![[不含平台评级] 图 6.2 入模特征 CSI（虚线 = 0.10 / 0.25）](figures/11_csi_no_platform_rating.png)

_[不含平台评级] 图 6.2 入模特征 CSI（虚线 = 0.10 / 0.25）_

### [不含平台评级] CSI 分箱明细（train → OOT）

| 特征 | 分箱 | train 占比 | 对比样本占比 | PSI 贡献 |
|---|---|---|---|---|
| fico_mid | <= 672 | 27.09% | 28.63% | 0.0008 |
| fico_mid | (672, 687] | 23.24% | 22.36% | 0.0003 |
| fico_mid | (687, 702] | 18.61% | 17.25% | 0.0010 |
| fico_mid | (702, 717] | 12.87% | 12.60% | 0.0001 |
| fico_mid | (717, 737] | 9.27% | 9.20% | 0.0000 |
| fico_mid | > 737 | 8.91% | 9.95% | 0.0012 |
| loan_to_inc | <= 0.1516 | 35.56% | 40.60% | 0.0067 |
| loan_to_inc | (0.1516, 0.2632] | 35.09% | 34.57% | 0.0001 |
| loan_to_inc | (0.2632, 0.3333] | 14.97% | 12.85% | 0.0033 |
| loan_to_inc | > 0.3333 | 14.38% | 11.98% | 0.0044 |
| loan_to_inc | Missing | 0.00% | 0.00% | 0.0000 |
| term | <= 36 | 90.69% | 100.00% | 0.0091 |
| term | > 36 | 9.31% | 0.00% | 0.6356 |
| acc_open_past_24mths | <= 1 | 14.96% | 14.28% | 0.0003 |
| acc_open_past_24mths | (1, 2] | 14.24% | 13.45% | 0.0004 |
| acc_open_past_24mths | (2, 3] | 15.59% | 14.56% | 0.0007 |
| acc_open_past_24mths | (3, 5] | 26.29% | 25.65% | 0.0002 |
| acc_open_past_24mths | (5, 7] | 15.29% | 16.44% | 0.0008 |
| acc_open_past_24mths | > 7 | 12.05% | 15.61% | 0.0092 |
| acc_open_past_24mths | Missing | 1.58% | 0.00% | 0.0796 |
| bc_open_to_buy | <= 2,396 | 38.93% | 34.41% | 0.0056 |
| bc_open_to_buy | (2,396, 8,449] | 30.31% | 31.51% | 0.0005 |
| bc_open_to_buy | > 8,449 | 28.22% | 33.09% | 0.0078 |
| bc_open_to_buy | Missing | 2.54% | 0.98% | 0.0147 |
| annual_inc | <= 37,000 | 15.66% | 16.07% | 0.0001 |
| annual_inc | (37,000, 49,000] | 16.32% | 15.19% | 0.0008 |
| annual_inc | (49,000, 66,000] | 24.16% | 23.23% | 0.0004 |
| annual_inc | (66,000, 82,000] | 15.38% | 15.10% | 0.0000 |
| annual_inc | (82,000, 110,000] | 15.92% | 15.92% | 0.0000 |
| annual_inc | > 110,000 | 12.57% | 14.49% | 0.0027 |
| tot_hi_cred_lim | <= 53,148 | 30.03% | 30.17% | 0.0000 |
| tot_hi_cred_lim | (53,148, 156,798] | 28.31% | 32.29% | 0.0052 |
| tot_hi_cred_lim | (156,798, 234,986] | 12.65% | 12.53% | 0.0000 |
| tot_hi_cred_lim | (234,986, 300,194] | 8.03% | 7.99% | 0.0000 |
| tot_hi_cred_lim | (300,194, 431,415] | 8.94% | 9.64% | 0.0005 |
| tot_hi_cred_lim | > 431,415 | 6.21% | 7.37% | 0.0020 |
| tot_hi_cred_lim | Missing | 5.84% | 0.00% | 0.3713 |
| num_tl_op_past_12m | <= 0 | 17.18% | 17.80% | 0.0002 |
| num_tl_op_past_12m | (0, 1] | 24.92% | 24.81% | 0.0000 |
| num_tl_op_past_12m | (1, 2] | 22.13% | 22.10% | 0.0000 |
| num_tl_op_past_12m | (2, 3] | 15.30% | 15.90% | 0.0002 |
| num_tl_op_past_12m | > 3 | 14.63% | 19.39% | 0.0134 |
| num_tl_op_past_12m | Missing | 5.84% | 0.00% | 0.3713 |
| dti | <= 11.65 | 25.54% | 23.86% | 0.0011 |
| dti | (11.65, 17.11] | 24.43% | 22.81% | 0.0011 |
| dti | (17.11, 21.74] | 19.54% | 18.74% | 0.0003 |
| dti | (21.74, 25.16] | 11.53% | 11.47% | 0.0000 |
| dti | > 25.16 | 18.96% | 23.12% | 0.0083 |
| dti | Missing | 0.00% | 0.00% | 0.0000 |
| total_rev_hi_lim | <= 6,600 | 6.67% | 7.18% | 0.0004 |
| total_rev_hi_lim | (6,600, 18,000] | 31.11% | 30.71% | 0.0001 |
| total_rev_hi_lim | (18,000, 23,216] | 12.04% | 12.21% | 0.0000 |
| total_rev_hi_lim | (23,216, 37,900] | 21.69% | 22.63% | 0.0004 |
| total_rev_hi_lim | (37,900, 55,900] | 12.22% | 13.37% | 0.0010 |
| total_rev_hi_lim | > 55,900 | 10.43% | 13.89% | 0.0099 |
| total_rev_hi_lim | Missing | 5.84% | 0.00% | 0.3713 |
| mo_sin_rcnt_tl | <= 1 | 9.28% | 10.65% | 0.0019 |
| mo_sin_rcnt_tl | (1, 3] | 19.43% | 22.58% | 0.0047 |
| mo_sin_rcnt_tl | (3, 7] | 29.01% | 29.94% | 0.0003 |
| mo_sin_rcnt_tl | (7, 13] | 21.58% | 21.53% | 0.0000 |
| mo_sin_rcnt_tl | (13, 22] | 9.47% | 9.79% | 0.0001 |
| mo_sin_rcnt_tl | > 22 | 5.39% | 5.51% | 0.0000 |
| mo_sin_rcnt_tl | Missing | 5.84% | 0.00% | 0.3713 |
| percent_bc_gt_75 | <= 0 | 17.83% | 24.75% | 0.0227 |
| percent_bc_gt_75 | (0, 26.7] | 11.99% | 13.48% | 0.0018 |
| percent_bc_gt_75 | (26.7, 50] | 24.83% | 23.70% | 0.0005 |
| percent_bc_gt_75 | (50, 83.3] | 21.61% | 17.04% | 0.0109 |
| percent_bc_gt_75 | > 83.3 | 21.16% | 19.94% | 0.0007 |
| percent_bc_gt_75 | Missing | 2.57% | 1.10% | 0.0125 |
| inq_last_6mths | <= 0 | 54.12% | 61.12% | 0.0085 |
| inq_last_6mths | (0, 1] | 27.86% | 26.13% | 0.0011 |
| inq_last_6mths | (1, 2] | 11.43% | 8.65% | 0.0078 |
| inq_last_6mths | > 2 | 6.58% | 4.09% | 0.0118 |
| mort_acc | <= 0 | 41.51% | 43.09% | 0.0006 |
| mort_acc | (0, 1] | 16.00% | 16.88% | 0.0005 |
| mort_acc | (1, 2] | 12.99% | 14.16% | 0.0010 |
| mort_acc | (2, 4] | 17.17% | 17.43% | 0.0000 |
| mort_acc | > 4 | 10.76% | 8.45% | 0.0056 |
| mort_acc | Missing | 1.58% | 0.00% | 0.0796 |
| verification_status | {Not Verified} | 33.69% | 26.23% | 0.0187 |
| verification_status | {Source Verified} | 32.31% | 42.95% | 0.0303 |
| verification_status | {Verified} | 34.00% | 30.83% | 0.0031 |
| mths_since_recent_bc | <= 3 | 12.81% | 13.71% | 0.0006 |
| mths_since_recent_bc | (3, 14] | 37.45% | 38.46% | 0.0003 |
| mths_since_recent_bc | (14, 23] | 15.81% | 16.41% | 0.0002 |
| mths_since_recent_bc | (23, 37] | 12.22% | 11.81% | 0.0001 |
| mths_since_recent_bc | (37, 68] | 10.67% | 10.14% | 0.0003 |
| mths_since_recent_bc | > 68 | 8.60% | 8.51% | 0.0000 |
| mths_since_recent_bc | Missing | 2.45% | 0.96% | 0.0140 |
| home_ownership | {OTHER_RARE, MORTGAGE} | 48.22% | 46.54% | 0.0006 |
| home_ownership | {OWN} | 9.58% | 11.48% | 0.0034 |
| home_ownership | {RENT} | 42.20% | 41.99% | 0.0000 |
| mo_sin_old_rev_tl_op | <= 82 | 10.03% | 10.99% | 0.0009 |
| mo_sin_old_rev_tl_op | (82, 115] | 13.54% | 13.13% | 0.0001 |
| mo_sin_old_rev_tl_op | (115, 154] | 18.90% | 19.86% | 0.0005 |
| mo_sin_old_rev_tl_op | (154, 233] | 29.66% | 30.06% | 0.0001 |
| mo_sin_old_rev_tl_op | > 233 | 22.03% | 25.96% | 0.0064 |
| mo_sin_old_rev_tl_op | Missing | 5.84% | 0.00% | 0.3713 |
| revol_util | <= 18.1 | 6.54% | 9.01% | 0.0079 |
| revol_util | (18.1, 25.5] | 5.03% | 6.68% | 0.0047 |
| revol_util | (25.5, 44.8] | 21.39% | 25.17% | 0.0061 |
| revol_util | (44.8, 58.8] | 20.51% | 20.08% | 0.0001 |
| revol_util | (58.8, 86.9] | 36.94% | 30.93% | 0.0107 |
| revol_util | > 86.9 | 9.52% | 8.09% | 0.0023 |
| revol_util | Missing | 0.05% | 0.05% | 0.0000 |
| num_rev_tl_bal_gt_0 | <= 2 | 10.39% | 13.08% | 0.0062 |
| num_rev_tl_bal_gt_0 | (2, 3] | 12.82% | 14.71% | 0.0026 |
| num_rev_tl_bal_gt_0 | (3, 5] | 29.22% | 29.81% | 0.0001 |
| num_rev_tl_bal_gt_0 | (5, 7] | 20.78% | 20.37% | 0.0001 |
| num_rev_tl_bal_gt_0 | (7, 8] | 6.53% | 6.46% | 0.0000 |
| num_rev_tl_bal_gt_0 | > 8 | 14.43% | 15.57% | 0.0009 |
| num_rev_tl_bal_gt_0 | Missing | 5.84% | 0.00% | 0.3713 |

### [含平台评级] 6.1 score PSI

| 对比 | train 行数 | 对比样本行数 | PSI | 判定 |
|---|---|---|---|---|
| train → test | 330,071 | 141,460 | 0.0000 | 🟢 稳定 |
| train → OOT | 330,071 | 162,236 | 0.0316 | 🟢 稳定 |

![[含平台评级] 图 6.1 分数分布按 train 等频段（train vs test vs OOT）](figures/10_score_psi_with_platform_rating.png)

_[含平台评级] 图 6.1 分数分布按 train 等频段（train vs test vs OOT）_

### [含平台评级] score PSI 分段明细

| 段 | 分数区间 | train 占比 | test 占比 | OOT 占比 | PSI 贡献（test） | PSI 贡献（OOT） |
|---|---|---|---|---|---|---|
| 1 | <= 543 | 10.85% | 10.84% | 7.01% | 0.0000 | 0.0168 |
| 2 | (543, 551] | 10.16% | 10.27% | 8.82% | 0.0000 | 0.0019 |
| 3 | (551, 557] | 9.93% | 9.93% | 9.20% | 0.0000 | 0.0006 |
| 4 | (557, 562] | 9.15% | 9.15% | 8.75% | 0.0000 | 0.0002 |
| 5 | (562, 568] | 11.02% | 11.02% | 10.89% | 0.0000 | 0.0000 |
| 6 | (568, 574] | 10.43% | 10.37% | 10.60% | 0.0000 | 0.0000 |
| 7 | (574, 580] | 9.27% | 9.19% | 9.90% | 0.0000 | 0.0004 |
| 8 | (580, 588] | 9.93% | 10.07% | 11.05% | 0.0000 | 0.0012 |
| 9 | (588, 599] | 9.65% | 9.59% | 11.07% | 0.0000 | 0.0019 |
| 10 | > 599 | 9.61% | 9.57% | 12.71% | 0.0000 | 0.0086 |

### [含平台评级] 6.2 入模特征 CSI（判定按 train → OOT）

| 特征 | CSI train→test | CSI train→OOT | 判定 | 偏移最大的箱 | train 占比 | OOT 占比 |
|---|---|---|---|---|---|---|
| term | 0.0001 | 0.6447 | 🔴 警戒 | <= 36 | 90.69% | 100.00% |
| num_tl_op_past_12m | 0.0001 | 0.3851 | 🔴 警戒 | Missing | 5.84% | 0.00% |
| total_rev_hi_lim | 0.0002 | 0.3831 | 🔴 警戒 | Missing | 5.84% | 0.00% |
| num_rev_tl_bal_gt_0 | 0.0001 | 0.3812 | 🔴 警戒 | Missing | 5.84% | 0.00% |
| mo_sin_old_rev_tl_op | 0.0001 | 0.3792 | 🔴 警戒 | Missing | 5.84% | 0.00% |
| tot_hi_cred_lim | 0.0001 | 0.3791 | 🔴 警戒 | Missing | 5.84% | 0.00% |
| mo_sin_rcnt_tl | 0.0001 | 0.3783 | 🔴 警戒 | Missing | 5.84% | 0.00% |
| acc_open_past_24mths | 0.0001 | 0.0912 | 🟢 稳定 | > 7 | 12.05% | 15.61% |
| mort_acc | 0.0000 | 0.0873 | 🟢 稳定 | > 4 | 10.76% | 8.45% |
| verification_status | 0.0000 | 0.0520 | 🟢 稳定 | {Source Verified} | 32.31% | 42.95% |
| percent_bc_gt_75 | 0.0001 | 0.0490 | 🟢 稳定 | <= 0 | 17.83% | 24.75% |
| sub_grade | 0.0000 | 0.0425 | 🟢 稳定 | {D4, D5, G4, E2, E1, E3, E4, F1, E5, G2, F2, F3, F4, F5, G5, G1, G3} | 11.32% | 6.44% |
| inq_last_6mths | 0.0000 | 0.0292 | 🟢 稳定 | <= 0 | 54.12% | 61.12% |
| bc_open_to_buy | 0.0000 | 0.0285 | 🟢 稳定 | > 8,449 | 28.22% | 33.09% |
| mths_since_recent_bc | 0.0001 | 0.0155 | 🟢 稳定 | Missing | 2.45% | 0.96% |
| loan_to_inc | 0.0001 | 0.0144 | 🟢 稳定 | <= 0.1516 | 35.56% | 40.60% |
| dti | 0.0000 | 0.0108 | 🟢 稳定 | > 25.16 | 18.96% | 23.12% |
| log_annual_inc | 0.0000 | 0.0041 | 🟢 稳定 | > 11.61 | 12.57% | 14.49% |
| home_ownership | 0.0000 | 0.0040 | 🟢 稳定 | {OWN} | 9.58% | 11.48% |
| fico_mid | 0.0001 | 0.0034 | 🟢 稳定 | <= 672 | 27.09% | 28.63% |

_CSI 高说明该特征的客群分布变了，不一定意味着模型失效：先看 score PSI 是否稳定，再看该特征的分箱是否仍合理、含义是否变化（例如某个征信字段从某年开始才有值）。_

![[含平台评级] 图 6.2 入模特征 CSI（虚线 = 0.10 / 0.25）](figures/11_csi_with_platform_rating.png)

_[含平台评级] 图 6.2 入模特征 CSI（虚线 = 0.10 / 0.25）_

### [含平台评级] CSI 分箱明细（train → OOT）

| 特征 | 分箱 | train 占比 | 对比样本占比 | PSI 贡献 |
|---|---|---|---|---|
| sub_grade | {A1, A2, A3, A4} | 14.16% | 17.61% | 0.0075 |
| sub_grade | {A5, B1, B2} | 17.90% | 20.71% | 0.0041 |
| sub_grade | {B3, B4} | 14.15% | 13.73% | 0.0001 |
| sub_grade | {B5, C1, C2, C3} | 23.76% | 24.99% | 0.0006 |
| sub_grade | {C4, C5, D1, D3, D2} | 18.70% | 16.52% | 0.0027 |
| sub_grade | {D4, D5, G4, E2, E1, E3, E4, F1, E5, G2, F2, F3, F4, F5, G5, G1, G3} | 11.32% | 6.44% | 0.0275 |
| fico_mid | <= 672 | 27.09% | 28.63% | 0.0008 |
| fico_mid | (672, 687] | 23.24% | 22.36% | 0.0003 |
| fico_mid | (687, 702] | 18.61% | 17.25% | 0.0010 |
| fico_mid | (702, 717] | 12.87% | 12.60% | 0.0001 |
| fico_mid | (717, 737] | 9.27% | 9.20% | 0.0000 |
| fico_mid | > 737 | 8.91% | 9.95% | 0.0012 |
| loan_to_inc | <= 0.1516 | 35.56% | 40.60% | 0.0067 |
| loan_to_inc | (0.1516, 0.2632] | 35.09% | 34.57% | 0.0001 |
| loan_to_inc | (0.2632, 0.3333] | 14.97% | 12.85% | 0.0033 |
| loan_to_inc | > 0.3333 | 14.38% | 11.98% | 0.0044 |
| loan_to_inc | Missing | 0.00% | 0.00% | 0.0000 |
| term | <= 36 | 90.69% | 100.00% | 0.0091 |
| term | > 36 | 9.31% | 0.00% | 0.6356 |
| acc_open_past_24mths | <= 1 | 14.96% | 14.28% | 0.0003 |
| acc_open_past_24mths | (1, 2] | 14.24% | 13.45% | 0.0004 |
| acc_open_past_24mths | (2, 3] | 15.59% | 14.56% | 0.0007 |
| acc_open_past_24mths | (3, 5] | 26.29% | 25.65% | 0.0002 |
| acc_open_past_24mths | (5, 7] | 15.29% | 16.44% | 0.0008 |
| acc_open_past_24mths | > 7 | 12.05% | 15.61% | 0.0092 |
| acc_open_past_24mths | Missing | 1.58% | 0.00% | 0.0796 |
| bc_open_to_buy | <= 2,396 | 38.93% | 34.41% | 0.0056 |
| bc_open_to_buy | (2,396, 8,449] | 30.31% | 31.51% | 0.0005 |
| bc_open_to_buy | > 8,449 | 28.22% | 33.09% | 0.0078 |
| bc_open_to_buy | Missing | 2.54% | 0.98% | 0.0147 |
| log_annual_inc | <= 10.52 | 15.66% | 16.07% | 0.0001 |
| log_annual_inc | (10.52, 10.8] | 16.32% | 15.19% | 0.0008 |
| log_annual_inc | (10.8, 11.1] | 24.16% | 23.23% | 0.0004 |
| log_annual_inc | (11.1, 11.31] | 15.38% | 15.10% | 0.0000 |
| log_annual_inc | (11.31, 11.61] | 15.92% | 15.92% | 0.0000 |
| log_annual_inc | > 11.61 | 12.57% | 14.49% | 0.0027 |
| tot_hi_cred_lim | <= 53,148 | 30.03% | 30.17% | 0.0000 |
| tot_hi_cred_lim | (53,148, 156,798] | 28.31% | 32.29% | 0.0052 |
| tot_hi_cred_lim | (156,798, 234,986] | 12.65% | 12.53% | 0.0000 |
| tot_hi_cred_lim | (234,986, 300,194] | 8.03% | 7.99% | 0.0000 |
| tot_hi_cred_lim | (300,194, 431,415] | 8.94% | 9.64% | 0.0005 |
| tot_hi_cred_lim | > 431,415 | 6.21% | 7.37% | 0.0020 |
| tot_hi_cred_lim | Missing | 5.84% | 0.00% | 0.3713 |
| num_tl_op_past_12m | <= 0 | 17.18% | 17.80% | 0.0002 |
| num_tl_op_past_12m | (0, 1] | 24.92% | 24.81% | 0.0000 |
| num_tl_op_past_12m | (1, 2] | 22.13% | 22.10% | 0.0000 |
| num_tl_op_past_12m | (2, 3] | 15.30% | 15.90% | 0.0002 |
| num_tl_op_past_12m | > 3 | 14.63% | 19.39% | 0.0134 |
| num_tl_op_past_12m | Missing | 5.84% | 0.00% | 0.3713 |
| dti | <= 11.65 | 25.54% | 23.86% | 0.0011 |
| dti | (11.65, 17.11] | 24.43% | 22.81% | 0.0011 |
| dti | (17.11, 21.74] | 19.54% | 18.74% | 0.0003 |
| dti | (21.74, 25.16] | 11.53% | 11.47% | 0.0000 |
| dti | > 25.16 | 18.96% | 23.12% | 0.0083 |
| dti | Missing | 0.00% | 0.00% | 0.0000 |
| total_rev_hi_lim | <= 6,600 | 6.67% | 7.18% | 0.0004 |
| total_rev_hi_lim | (6,600, 18,000] | 31.11% | 30.71% | 0.0001 |
| total_rev_hi_lim | (18,000, 23,216] | 12.04% | 12.21% | 0.0000 |
| total_rev_hi_lim | (23,216, 37,900] | 21.69% | 22.63% | 0.0004 |
| total_rev_hi_lim | (37,900, 55,900] | 12.22% | 13.37% | 0.0010 |
| total_rev_hi_lim | > 55,900 | 10.43% | 13.89% | 0.0099 |
| total_rev_hi_lim | Missing | 5.84% | 0.00% | 0.3713 |
| mo_sin_rcnt_tl | <= 1 | 9.28% | 10.65% | 0.0019 |
| mo_sin_rcnt_tl | (1, 3] | 19.43% | 22.58% | 0.0047 |
| mo_sin_rcnt_tl | (3, 7] | 29.01% | 29.94% | 0.0003 |
| mo_sin_rcnt_tl | (7, 13] | 21.58% | 21.53% | 0.0000 |
| mo_sin_rcnt_tl | (13, 22] | 9.47% | 9.79% | 0.0001 |
| mo_sin_rcnt_tl | > 22 | 5.39% | 5.51% | 0.0000 |
| mo_sin_rcnt_tl | Missing | 5.84% | 0.00% | 0.3713 |
| percent_bc_gt_75 | <= 0 | 17.83% | 24.75% | 0.0227 |
| percent_bc_gt_75 | (0, 26.7] | 11.99% | 13.48% | 0.0018 |
| percent_bc_gt_75 | (26.7, 50] | 24.83% | 23.70% | 0.0005 |
| percent_bc_gt_75 | (50, 83.3] | 21.61% | 17.04% | 0.0109 |
| percent_bc_gt_75 | > 83.3 | 21.16% | 19.94% | 0.0007 |
| percent_bc_gt_75 | Missing | 2.57% | 1.10% | 0.0125 |
| inq_last_6mths | <= 0 | 54.12% | 61.12% | 0.0085 |
| inq_last_6mths | (0, 1] | 27.86% | 26.13% | 0.0011 |
| inq_last_6mths | (1, 2] | 11.43% | 8.65% | 0.0078 |
| inq_last_6mths | > 2 | 6.58% | 4.09% | 0.0118 |
| mort_acc | <= 0 | 41.51% | 43.09% | 0.0006 |
| mort_acc | (0, 1] | 16.00% | 16.88% | 0.0005 |
| mort_acc | (1, 2] | 12.99% | 14.16% | 0.0010 |
| mort_acc | (2, 4] | 17.17% | 17.43% | 0.0000 |
| mort_acc | > 4 | 10.76% | 8.45% | 0.0056 |
| mort_acc | Missing | 1.58% | 0.00% | 0.0796 |
| verification_status | {Not Verified} | 33.69% | 26.23% | 0.0187 |
| verification_status | {Source Verified} | 32.31% | 42.95% | 0.0303 |
| verification_status | {Verified} | 34.00% | 30.83% | 0.0031 |
| mths_since_recent_bc | <= 3 | 12.81% | 13.71% | 0.0006 |
| mths_since_recent_bc | (3, 14] | 37.45% | 38.46% | 0.0003 |
| mths_since_recent_bc | (14, 23] | 15.81% | 16.41% | 0.0002 |
| mths_since_recent_bc | (23, 37] | 12.22% | 11.81% | 0.0001 |
| mths_since_recent_bc | (37, 68] | 10.67% | 10.14% | 0.0003 |
| mths_since_recent_bc | > 68 | 8.60% | 8.51% | 0.0000 |
| mths_since_recent_bc | Missing | 2.45% | 0.96% | 0.0140 |
| home_ownership | {OTHER_RARE, MORTGAGE} | 48.22% | 46.54% | 0.0006 |
| home_ownership | {OWN} | 9.58% | 11.48% | 0.0034 |
| home_ownership | {RENT} | 42.20% | 41.99% | 0.0000 |
| mo_sin_old_rev_tl_op | <= 82 | 10.03% | 10.99% | 0.0009 |
| mo_sin_old_rev_tl_op | (82, 115] | 13.54% | 13.13% | 0.0001 |
| mo_sin_old_rev_tl_op | (115, 154] | 18.90% | 19.86% | 0.0005 |
| mo_sin_old_rev_tl_op | (154, 233] | 29.66% | 30.06% | 0.0001 |
| mo_sin_old_rev_tl_op | > 233 | 22.03% | 25.96% | 0.0064 |
| mo_sin_old_rev_tl_op | Missing | 5.84% | 0.00% | 0.3713 |
| num_rev_tl_bal_gt_0 | <= 2 | 10.39% | 13.08% | 0.0062 |
| num_rev_tl_bal_gt_0 | (2, 3] | 12.82% | 14.71% | 0.0026 |
| num_rev_tl_bal_gt_0 | (3, 5] | 29.22% | 29.81% | 0.0001 |
| num_rev_tl_bal_gt_0 | (5, 7] | 20.78% | 20.37% | 0.0001 |
| num_rev_tl_bal_gt_0 | (7, 8] | 6.53% | 6.46% | 0.0000 |
| num_rev_tl_bal_gt_0 | > 8 | 14.43% | 15.57% | 0.0009 |
| num_rev_tl_bal_gt_0 | Missing | 5.84% | 0.00% | 0.3713 |

![图 6.3 vintage 曲线（按 issue 季度的累计违约率 vs 账龄）](figures/12_vintage.png)

_图 6.3 vintage 曲线（按 issue 季度的累计违约率 vs 账龄）_

### 6.3 vintage 表：累计违约率按 issue 季度 × 账龄（月）

| issue 季度 | 贷款数 | MOB 3 | MOB 6 | MOB 9 | MOB 12 | MOB 18 | MOB 24 | MOB 30 | MOB 36 | MOB 48 | MOB 60 |
|---|---|---|---|---|---|---|---|---|---|---|---|
| 2012Q1 | 8,076 | 0.98% | 2.27% | 4.17% | 5.67% | 8.58% | 11.39% | 13.78% | 15.22% | 15.82% | 16.15% |
| 2012Q2 | 10,447 | 0.88% | 2.38% | 3.95% | 5.70% | 9.39% | 12.31% | 14.71% | 15.96% | 16.75% | 17.03% |
| 2012Q3 | 16,133 | 0.89% | 2.29% | 3.81% | 5.87% | 9.13% | 11.88% | 14.18% | 15.49% | 16.19% | 16.45% |
| 2012Q4 | 18,711 | 0.65% | 1.82% | 3.36% | 5.18% | 8.08% | 10.91% | 13.02% | 14.50% | 15.16% | 15.54% |
| 2013Q1 | 22,706 | 0.62% | 1.75% | 3.22% | 4.64% | 7.76% | 10.50% | 12.67% | 13.94% | 14.72% | 15.02% |
| 2013Q2 | 30,668 | 0.74% | 1.90% | 3.36% | 4.99% | 8.43% | 11.09% | 13.51% | 14.85% | 15.88% | 16.25% |
| 2013Q3 | 37,571 | 0.77% | 1.79% | 3.23% | 4.92% | 7.90% | 10.71% | 12.70% | 14.07% | 15.15% | 15.56% |
| 2013Q4 | 43,859 | 0.53% | 1.51% | 2.98% | 4.60% | 7.48% | 10.39% | 12.54% | 14.05% | 15.06% | 15.46% |
| 2014Q1 | 34,074 | 0.49% | 1.53% | 2.82% | 4.08% | 7.07% | 9.72% | 11.74% | 12.81% | 12.87% | 12.87% |
| 2014Q2 | 37,881 | 0.61% | 1.71% | 2.91% | 4.52% | 7.68% | 10.09% | 12.39% | 13.48% | 13.55% |  |
| 2014Q3 | 40,595 | 0.64% | 1.66% | 3.03% | 4.79% | 7.65% | 10.51% | 12.54% | 13.56% | 13.63% |  |
| 2014Q4 | 50,020 | 0.60% | 1.81% | 3.29% | 5.05% | 8.10% | 11.27% | 13.31% | 14.43% | 14.53% |  |
| 2015Q1 | 56,568 | 0.63% | 1.83% | 3.41% | 4.94% | 8.57% | 11.52% | 13.60% | 14.74% | 14.83% |  |
| 2015Q2 | 64,222 | 0.71% | 2.04% | 3.49% | 5.31% | 9.12% | 11.90% | 14.17% | 15.27% |  |  |
| 2015Q3 | 73,567 | 0.66% | 1.78% | 3.33% | 5.23% | 8.65% | 11.44% | 13.38% | 14.47% |  |  |
| 2015Q4 | 88,669 | 0.63% | 1.81% | 3.66% | 5.48% | 8.79% | 11.59% | 13.49% | 14.71% |  |  |

_空白 = 该季度到数据截止时账龄还没到。_

### vintage 口径

- Lending Club 没有逐月表现数据，vintage 的账龄用 last_pymnt_d − issue_d（月）近似违约发生月：最后一次还款之后约 120 天以上才被 Charged Off，所以曲线比真实违约时点早约 4–5 个月；Fully Paid 贷款的 last_pymnt_d 是结清月，不参与分子。
- 数据截止月 2019-03；账龄超过 60 个月的违约（27 笔）计入最后一个月。
- 443 笔违约没有 event_date（从未还款），记为账龄 0。

## 7. 自动检查与风险提示

_对 leakage、单箱占比、train–test KS 差、PSI / CSI、高缺失率入模、系数符号与 VIF 的自动检查，并汇总 adapter 与建模警告。_

### 7.0 汇总

- **通过 / 警告 / 不通过 / 提示**：21 / 4 / 0 / 1
- **结论**：有警告项，需要人工判断

### 7.1 检查清单

| 检查项 | 范围 | 阈值 | 结果 | 判定 | 说明 |
|---|---|---|---|---|---|
| 样本 bad rate 在合理区间 | 数据 | 1%–40% | 14.85% | 🟢 通过 |  |
| IV 过高（疑似 leakage） | 不含平台评级 | IV > 0.5 | 最高 IV 0.1168（fico_mid） | 🟢 通过 |  |
| 入模特征单一分箱占比过高 | 不含平台评级 | 最大箱占比 > 90% | 最大 90.7%（term） | 🟡 警告 | 几乎所有人落在同一箱，区分度来自极少数人：term 90.7% |
| train–test KS 差（LR scorecard） | 不含平台评级 | KS(train) − KS(test) > 0.05 | 0.2467 − 0.2513 = -0.0045 | 🟢 通过 |  |
| train–test KS 差（GBDT challenger） | 不含平台评级 | KS(train) − KS(test) > 0.05 | 0.2943 − 0.2790 = +0.0153 | 🟢 通过 |  |
| test KS 高得不合理 | 不含平台评级 | KS > 0.9 | 0.2513 | 🟢 通过 |  |
| score PSI train → test | 不含平台评级 | PSI > 0.25 | 0.0001 | 🟢 通过 |  |
| score PSI train → OOT | 不含平台评级 | PSI > 0.25 | 0.0271 | 🟢 通过 |  |
| 入模特征 CSI（train → OOT） | 不含平台评级 | CSI > 0.25 | 7 / 20 个特征 | 🟡 警告 | 分布偏移：term 0.645, num_tl_op_past_12m 0.385, total_rev_hi_lim 0.383, num_rev_tl_bal_gt_0 0.381, mo_sin_old_rev_tl_op 0.379, tot_hi_cred_lim 0.379, mo_sin_rcnt_tl 0.378 |
| 入模特征缺失率过高 | 不含平台评级 | train 缺失率 > 50% | 最高 5.8%（tot_hi_cred_lim） | 🟢 通过 |  |
| LR 系数符号（WOE 越大越安全，系数应为负） | 不含平台评级 | 系数 > 0 | 0 / 20 个为正 | 🟢 通过 |  |
| 入模特征 VIF | 不含平台评级 | VIF > 5.0 | 最高 2.75（num_tl_op_past_12m） | 🟢 通过 |  |
| swap set：swap-in bad rate 低于 swap-out（OOT，基准 = 平台评级） | 不含平台评级 | swap-in > swap-out | 18.63% vs 19.97% | 🟢 通过 |  |
| IV 过高（疑似 leakage） | 含平台评级 | IV > 0.5 | 最高 IV 0.3546（sub_grade） | 🟢 通过 |  |
| 入模特征单一分箱占比过高 | 含平台评级 | 最大箱占比 > 90% | 最大 90.7%（term） | 🟡 警告 | 几乎所有人落在同一箱，区分度来自极少数人：term 90.7% |
| train–test KS 差（LR scorecard） | 含平台评级 | KS(train) − KS(test) > 0.05 | 0.2729 − 0.2760 = -0.0031 | 🟢 通过 |  |
| train–test KS 差（GBDT challenger） | 含平台评级 | KS(train) − KS(test) > 0.05 | 0.3015 − 0.2920 = +0.0095 | 🟢 通过 |  |
| test KS 高得不合理 | 含平台评级 | KS > 0.9 | 0.2760 | 🟢 通过 |  |
| score PSI train → test | 含平台评级 | PSI > 0.25 | 0.0000 | 🟢 通过 |  |
| score PSI train → OOT | 含平台评级 | PSI > 0.25 | 0.0316 | 🟢 通过 |  |
| 入模特征 CSI（train → OOT） | 含平台评级 | CSI > 0.25 | 7 / 20 个特征 | 🟡 警告 | 分布偏移：term 0.645, num_tl_op_past_12m 0.385, total_rev_hi_lim 0.383, num_rev_tl_bal_gt_0 0.381, mo_sin_old_rev_tl_op 0.379, tot_hi_cred_lim 0.379, mo_sin_rcnt_tl 0.378 |
| 入模特征缺失率过高 | 含平台评级 | train 缺失率 > 50% | 最高 5.8%（tot_hi_cred_lim） | 🟢 通过 |  |
| LR 系数符号（WOE 越大越安全，系数应为负） | 含平台评级 | 系数 > 0 | 0 / 20 个为正 | 🟢 通过 |  |
| 入模特征 VIF | 含平台评级 | VIF > 5.0 | 最高 2.77（num_tl_op_past_12m） | 🟢 通过 |  |
| swap set：swap-in bad rate 低于 swap-out（OOT，基准 = 平台评级） | 含平台评级 | swap-in > swap-out | 16.25% vs 22.09% | 🟢 通过 |  |
| adapter / 切分警告 | 数据 | — | — | ℹ️ 提示 | 到期规则使不同期限的完整放款窗口不同（36 期贷款 issue_d <= 2015-12，60 期贷款 issue_d <= 2013-12）：最后几个月只有短期限贷款，train 与 OOT 的 term 构成不同（DECISIONS.md D5；可用 terms_allowed 只建单一期限的卡） |

阈值来自 config `checks`；IV / 单箱占比 / 缺失率在 train 上计算，PSI / CSI 见第 6 节，KS 见第 3 节，swap set 见第 5 节。这些检查只提示风险，不会自动改模型。

## 附录：运行元数据

### 运行元数据

- **config**：configs\lendingclub.yaml（hash c5a5c873cbd5）
- **数据文件**：data/raw/accepted_2007_to_2018Q4.csv.gz；原始 2,260,701 行 → 样本 633,767 行
- **git commit**：ca6f10e
- **运行时间**：2026-10-19 01:13:22
- **总耗时**：143.3 s
- **版本**：python 3.13.2, credit-scorecard-pipeline 0.1.0, pandas 3.0.6, numpy 2.5.4, sklearn 1.9.1, toad 0.1.7, matplotlib 3.11.2
- **缓存**：data\cache\lendingclub_2767e594d504e290.pkl

### 各步骤耗时

| 步骤 | 秒 |
|---|---|
| load | 10.7 |
| split | 0.2 |
| profile | 2.3 |
| variants | 126.1 |
| strategy | 0.6 |
| monitor | 3.5 |
| checks | 0.0 |
| artifacts | 0.1 |
| variant.no_platform_rating.binning | 5.1 |
| variant.no_platform_rating.select_and_lr | 2.4 |
| variant.no_platform_rating.gbdt | 6.1 |
| variant.no_platform_rating.scoring | 7.6 |
| variant.no_platform_rating.cv_lr | 11.1 |
| variant.no_platform_rating.cv_gbdt | 28.1 |
| variant.with_platform_rating.binning | 5.6 |
| variant.with_platform_rating.select_and_lr | 3.5 |
| variant.with_platform_rating.gbdt | 6.7 |
| variant.with_platform_rating.scoring | 7.7 |
| variant.with_platform_rating.cv_lr | 11.9 |
| variant.with_platform_rating.cv_gbdt | 30.1 |

<details><summary>完整 config</summary>

```yaml
dataset:
  adapter: lendingclub
  path: data/raw/accepted_2007_to_2018Q4.csv.gz
  nrows: null
  cache: true
  cache_dir: data/cache
  options:
    date_format: '%b-%Y'
    sample_frac: null
    sample_random_state: 42
    data_cutoff_month: 2018-12
    terms_allowed: null
    net_cash_subtract_collection_fee: true
    rare_category_min_share: 0.01
    rare_category_cols:
    - purpose
    - home_ownership
    - addr_state
    rare_category_label: OTHER_RARE
    field_groups:
      A:
      - loan_status
      B:
      - total_pymnt
      - total_pymnt_inv
      - total_rec_prncp
      - total_rec_int
      - total_rec_late_fee
      - recoveries
      - collection_recovery_fee
      - out_prncp
      - out_prncp_inv
      - last_pymnt_d
      - last_pymnt_amnt
      - next_pymnt_d
      - last_credit_pull_d
      C:
      - last_fico_range_high
      - last_fico_range_low
      D:
      - hardship_*
      - settlement_*
      - debt_settlement_flag*
      - deferral_term
      - payment_plan_start_date
      - orig_projected_additional_accrued_interest
      - pymnt_plan
      E:
      - id
      - member_id
      - url
      - desc
      - title
      - policy_code
      - emp_title
      - zip_code
      F:
      - funded_amnt_inv
      G:
      - grade
      - sub_grade
      - int_rate
      - installment
      H:
      - annual_inc_joint
      - dti_joint
      - verification_status_joint
      - revol_bal_joint
      - sec_app_*
sample:
  min_issue_date: 2012-01
  max_issue_date: null
split:
  oot_months: 6
  oot_fraction: 0.15
  train_ratio: 0.7
  random_state: 42
features:
  use_platform_rating:
  - false
  - true
  exclude: []
binning:
  backend: auto
  method: chi
  min_samples: 0.05
  max_bins: 6
  monotonic: true
  sample_size: 200000
  prebins: 200
select:
  max_missing: 0.5
  min_iv: 0.02
  leakage_iv: 0.5
  max_corr: 0.7
  max_vif: 5.0
  drop_positive_coef: true
  max_features: null
model:
  lr_C: 1.0
  lr_max_iter: 1000
  cv_folds: 5
  cv_challenger: true
  gbdt:
    learning_rate: 0.05
    max_iter: 300
    max_leaf_nodes: 8
    min_samples_leaf: 200
    l2_regularization: 1.0
    early_stopping: false
scorecard:
  pdo: 20
  base_score: 600
  base_odds: 20
strategy:
  approval_rates:
  - 0.5
  - 0.6
  - 0.7
  - 0.8
  - 0.9
  score_bands: 10
  swap_set_approval_rate: 0.7
  profit_min_approval_rate: 0.1
monitor:
  psi_bins: 10
  psi_warn: 0.1
  psi_alert: 0.25
  vintage_max_mob: 60
checks:
  leakage_iv: 0.5
  single_bin_share: 0.9
  ks_gap: 0.05
  psi_alert: 0.25
  missing_in_model: 0.5
report:
  title: Lending Club 信用评分卡与策略分析报告
  top_missing: 20
  top_woe_plots: 8
  embed_figures: true
output:
  dir: outputs/lendingclub
```

</details>

