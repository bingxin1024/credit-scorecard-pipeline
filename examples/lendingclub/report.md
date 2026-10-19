# Lending Club 信用评分卡与策略分析报告

- **数据**：data/raw/accepted_2007_to_2018Q4.csv.gz（546,018 行）
- **config hash**：a2fc5b0e633b
- **git commit**：b951183
- **生成时间**：2026-10-19 13:01:15

- **样本**：546,018 笔，bad rate 14.07%
- **入模特征**：15 / 99
- **train AUC / KS**：0.6657 / 0.2377
- **test AUC / KS**：0.6624 / 0.2319
- **OOT AUC / KS**：0.6737 / 0.2491
- **cut-off（OOT，bad rate ≤ 10%）**：score ≥ 564：通过率 63.8%，bad rate 9.93%

## 1. 样本与数据概况

_数据来源、样本定义的每条规则及其影响、字段审计（哪些字段因为是贷后信息而剔除）、缺失率与 bad rate 随时间的变化。_

### 1.1 数据来源与规模

- **数据来源**：data/raw/accepted_2007_to_2018Q4.csv.gz
- **adapter**：lendingclub
- **原始行 × 列**：2,260,701 × 151
- **样本定义后行数**：546,018
- **候选特征数**：99（其中类别型 8）
- **bad rate**：14.07%（bad = 76,825）
- **issue_date 范围**：2013-01 ~ 2015-12

### 1.2 样本定义影响表

| 步骤 | 规则 | 说明 | 剔除行数 | 剩余行数 | 剩余 bad rate |
|---|---|---|---|---|---|
| 1 | drop_summary_rows | 剔除文件末尾的汇总行（id 非数字或 loan_status 为空） | 33 | 2,260,668 | 19.96% |
| 2 | credit_policy | 剔除 loan_status 以 “Does not meet the credit policy” 开头的贷款（早期不同准入政策） | 2,749 | 2,257,919 | 19.96% |
| 3 | term_filter | 仅保留 36 期（按产品分卡：不同期限是不同产品，且长期限贷款在 OOT 窗口内无法到期；config terms_allowed） | 650,603 | 1,607,316 | 16.00% |
| 4 | maturity | 到期筛选：issue_d + term 个月 <= 数据截止月 2018-12（保证 performance window 完整） | 988,585 | 618,731 | 13.90% |
| 5 | terminal_status | 终态映射：Charged Off / Default → 1；Fully Paid → 0；Current / Late / In Grace Period 为 indeterminate，剔除 | 147 | 618,584 | 13.90% |
| 6 | min_issue_date | 只保留 issue_d >= 2013-01：主要征信字段自 2012 年中起才由征信局提供，起点取在字段可得性稳定之后；2007–2012 另有量小、产品与客群不同的问题 | 72,566 | 546,018 | 14.07% |
| 7 | final_sample | 最终样本量与 bad rate | 0 | 546,018 | 14.07% |

_bad rate 按剩余行中已有终态（Charged Off / Default / Fully Paid）的贷款计算；终态映射之前的行里还包含 Current 等未终态贷款，不计入分母。_

### 1.3 min_issue_date 之前：bad rate 按 issue 年

| issue 年 | 贷款数 | bad rate |
|---|---|---|
| 2007 | 251 | 17.93% |
| 2008 | 1,562 | 15.81% |
| 2009 | 4,716 | 12.60% |
| 2010 | 8,466 | 9.95% |
| 2011 | 14,101 | 10.63% |
| 2012 | 43,470 | 13.58% |
| 2013 | 100,422 | 12.33% |
| 2014 | 162,570 | 13.73% |
| 2015 | 283,026 | 14.89% |

_min_issue_date 规则只保留 issue_date >= 2013-01；到期 + 终态样本。早期年份样本少，bad rate 与后期不同。_

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
| il_util | numeric | 97.65% | 155 |
| mths_since_rcnt_il | numeric | 97.36% | 193 |
| open_acc_6m | numeric | 97.27% | 13 |
| open_rv_24m | numeric | 97.27% | 28 |

![图 1.2 bad rate 按 issue 季度（最终样本）](figures/02_bad_rate_by_quarter.png)

_图 1.2 bad rate 按 issue 季度（最终样本）_

### 1.6 bad rate 按 issue 季度

| 季度 | 贷款数 | bad 数 | bad rate |
|---|---|---|---|
| 2013Q1 | 17,988 | 2,264 | 12.59% |
| 2013Q2 | 23,136 | 2,970 | 12.84% |
| 2013Q3 | 27,318 | 3,336 | 12.21% |
| 2013Q4 | 31,980 | 3,808 | 11.91% |
| 2014Q1 | 34,074 | 4,384 | 12.87% |
| 2014Q2 | 37,881 | 5,131 | 13.55% |
| 2014Q3 | 40,595 | 5,533 | 13.63% |
| 2014Q4 | 50,020 | 7,267 | 14.53% |
| 2015Q1 | 56,568 | 8,391 | 14.83% |
| 2015Q2 | 64,222 | 9,878 | 15.38% |
| 2015Q3 | 73,567 | 10,725 | 14.58% |
| 2015Q4 | 88,669 | 13,138 | 14.82% |

### 1.7 缺失率按 issue 年（总缺失率 > 5% 的特征）

| 特征 | 总缺失率 | 2013 | 2014 | 2015 |
|---|---|---|---|---|
| sec_app_chargeoff_within_12_mths | 100.0% | 100.0% | 100.0% | 100.0% |
| sec_app_credit_hist_months | 100.0% | 100.0% | 100.0% | 100.0% |
| sec_app_open_acc | 100.0% | 100.0% | 100.0% | 100.0% |
| sec_app_open_act_il | 100.0% | 100.0% | 100.0% | 100.0% |
| sec_app_revol_util | 100.0% | 100.0% | 100.0% | 100.0% |
| sec_app_fico_range_high | 100.0% | 100.0% | 100.0% | 100.0% |
| sec_app_inq_last_6mths | 100.0% | 100.0% | 100.0% | 100.0% |
| revol_bal_joint | 100.0% | 100.0% | 100.0% | 100.0% |
| sec_app_mort_acc | 100.0% | 100.0% | 100.0% | 100.0% |
| sec_app_fico_range_low | 100.0% | 100.0% | 100.0% | 100.0% |
| sec_app_num_rev_accts | 100.0% | 100.0% | 100.0% | 100.0% |
| sec_app_mths_since_last_major_derog | 100.0% | 100.0% | 100.0% | 100.0% |
| sec_app_collections_12_mths_ex_med | 100.0% | 100.0% | 100.0% | 100.0% |
| dti_joint | 100.0% | 100.0% | 100.0% | 99.9% |
| verification_status_joint | 100.0% | 100.0% | 100.0% | 99.9% |
| annual_inc_joint | 100.0% | 100.0% | 100.0% | 99.9% |
| il_util | 97.7% | 100.0% | 100.0% | 95.5% |
| mths_since_rcnt_il | 97.4% | 100.0% | 100.0% | 94.9% |
| total_bal_il | 97.3% | 100.0% | 100.0% | 94.7% |
| total_cu_tl | 97.3% | 100.0% | 100.0% | 94.7% |
| inq_last_12m | 97.3% | 100.0% | 100.0% | 94.7% |
| open_acc_6m | 97.3% | 100.0% | 100.0% | 94.7% |
| open_il_24m | 97.3% | 100.0% | 100.0% | 94.7% |
| open_act_il | 97.3% | 100.0% | 100.0% | 94.7% |
| inq_fi | 97.3% | 100.0% | 100.0% | 94.7% |
| all_util | 97.3% | 100.0% | 100.0% | 94.7% |
| max_bal_bc | 97.3% | 100.0% | 100.0% | 94.7% |
| open_rv_24m | 97.3% | 100.0% | 100.0% | 94.7% |
| open_rv_12m | 97.3% | 100.0% | 100.0% | 94.7% |
| open_il_12m | 97.3% | 100.0% | 100.0% | 94.7% |
| mths_since_last_record | 82.4% | 87.4% | 81.1% | 81.3% |
| mths_since_recent_bc_dlq | 74.3% | 77.6% | 73.1% | 73.8% |
| mths_since_last_major_derog | 71.9% | 79.5% | 70.7% | 69.8% |
| mths_since_recent_revol_delinq | 64.6% | 69.8% | 63.5% | 63.5% |
| mths_since_last_delinq | 49.8% | 56.5% | 48.9% | 48.0% |
| mths_since_recent_inq | 10.6% | 11.2% | 9.5% | 11.0% |
| emp_length_years | 6.2% | 5.0% | 5.9% | 6.7% |

_征信类字段（num_* / mo_sin_* / il / rv 等）在早期年份缺失率极高；select 步骤按 max_missing 阈值处理。_

### 1.8 样本切分

| 样本 | 行数 | 占比 | bad rate | issue 起 | issue 止 |
|---|---|---|---|---|---|
| train | 268,647 | 49.20% | 13.80% | 2013-01 | 2015-06 |
| test | 115,135 | 21.09% | 13.80% | 2013-01 | 2015-06 |
| oot | 162,236 | 29.71% | 14.71% | 2015-07 | 2015-12 |

_按 issue_date 切 OOT（最后 6 个月：2015-07 ~ 2015-12），其余按 target 分层随机切 train / test；train_ratio = 0.7，random_state = 42。分箱、WOE、特征选择与模型只在 train 上拟合。_

### 1.9 adapter 说明

- net_cash 一致性检验（Charged Off 样本 76,825 笔）：total_pymnt 与 total_rec_prncp + total_rec_int + total_rec_late_fee + recoveries 相差 < 1 的占 100.00%（最大绝对差 0.01）；不含 recoveries 时占 25.24%（最大绝对差 34,294）→ total_pymnt 已包含 recoveries。
- net_cash = total_pymnt - collection_recovery_fee - funded_amnt（实际回款减放款本金；仅策略层使用）
- 占比 < 1% 的类别并入 OTHER_RARE（按全样本频率计算，不使用标签）：purpose: car, small_business, moving, vacation, house, wedding, renewable_energy, educational；home_ownership: ANY；addr_state: KY, OK, KS, AR, UT, NM, HI, NH, MS, WV, RI, MT, DC, DE, AK, WY, SD, VT, NE, ME, ND, ID, IA
- 终态映射时剔除的 indeterminate 状态：Current 72，Late (31-120 days) 61，In Grace Period 9，Late (16-30 days) 5

## 2. 分箱与 IV

_在 train 上做单调 WOE 分箱并计算 IV；按缺失率、IV、相关性和系数符号筛选入模特征。_

### [不含平台评级] 2.1 分箱设置

- **分箱后端**：toad（5 个特征库未给出切点，退到 tree：collections_12_mths_ex_med, acc_now_delinq, chargeoff_within_12_mths, delinq_amnt, tax_liens）
- **method / min_samples / max_bins**：chi / 0.05 / 6
- **单调性约束**：是（不单调则合并相邻箱直至单调或退到 2 箱）
- **切点搜索样本量**：200,000（WOE / IV 在全部 train 上计算；筛选阈值也在 train 上评估）
- **WOE 定义**：WOE = ln(good 占比 / bad 占比)，越大越安全；缺失单独一箱
- **候选特征 → 入模特征**：99 → 15

![[不含平台评级] 图 2.1 IV 排名（前 30；绿色 = 入模）](figures/03_iv_ranking_no_platform_rating.png)

_[不含平台评级] 图 2.1 IV 排名（前 30；绿色 = 入模）_

### [不含平台评级] 2.2 IV 排名表（全部候选特征，按 IV 降序）

| 特征 | 类型 | IV | 缺失率（train） | 箱数 | 入模 | 剔除步骤 | 原因 |
|---|---|---|---|---|---|---|---|
| fico_mid | numeric | 0.1388 | 0.00% | 6 | 是 |  | selected |
| bc_open_to_buy | numeric | 0.0772 | 1.00% | 7 | 是 |  | selected |
| tot_hi_cred_lim | numeric | 0.0765 | 0.00% | 6 | 是 |  | selected |
| log_annual_inc | numeric | 0.0764 | 0.00% | 6 | 是 |  | selected |
| annual_inc | numeric | 0.0764 | 0.00% | 6 | 否 | 3_corr | \|corr\| = 1.00 with log_annual_inc (IV 0.076) |
| avg_cur_bal | numeric | 0.0737 | 0.00% | 7 | 否 | 3_corr | \|corr\| = 0.85 with tot_hi_cred_lim (IV 0.077) |
| total_bc_limit | numeric | 0.0714 | 0.00% | 6 | 否 | 3_corr | \|corr\| = 0.78 with bc_open_to_buy (IV 0.077) |
| acc_open_past_24mths | numeric | 0.0711 | 0.00% | 6 | 是 |  | selected |
| tot_cur_bal | numeric | 0.0609 | 0.00% | 4 | 否 | 3_corr | \|corr\| = 0.94 with tot_hi_cred_lim (IV 0.077) |
| num_tl_op_past_12m | numeric | 0.0579 | 0.00% | 5 | 否 | 3_corr | \|corr\| = 0.71 with acc_open_past_24mths (IV 0.071) |
| total_rev_hi_lim | numeric | 0.0557 | 0.00% | 6 | 是 |  | selected |
| dti | numeric | 0.0507 | 0.00% | 4 | 是 |  | selected |
| mort_acc | numeric | 0.0485 | 0.00% | 5 | 是 |  | selected |
| home_ownership | categorical | 0.0451 | 0.00% | 3 | 是 |  | selected |
| mo_sin_rcnt_tl | numeric | 0.0410 | 0.00% | 6 | 是 |  | selected |
| mths_since_recent_inq | numeric | 0.0370 | 10.22% | 7 | 是 |  | selected |
| mo_sin_old_rev_tl_op | numeric | 0.0369 | 0.00% | 6 | 是 |  | selected |
| loan_to_inc | numeric | 0.0369 | 0.00% | 6 | 是 |  | selected |
| percent_bc_gt_75 | numeric | 0.0339 | 1.04% | 6 | 是 |  | selected |
| mths_since_recent_bc | numeric | 0.0331 | 0.92% | 7 | 是 |  | selected |
| mo_sin_rcnt_rev_tl_op | numeric | 0.0319 | 0.00% | 3 | 否 | 5_sign | coefficient +0.2718 is not negative |
| inq_last_6mths | numeric | 0.0318 | 0.00% | 4 | 否 | 3_corr | \|corr\| = 0.71 with mths_since_recent_inq (IV 0.037) |
| bc_util | numeric | 0.0235 | 1.07% | 4 | 否 | 3_corr | \|corr\| = 0.77 with percent_bc_gt_75 (IV 0.034) |
| credit_hist_months | numeric | 0.0227 | 0.00% | 5 | 否 | 3_corr | \|corr\| = 0.80 with mo_sin_old_rev_tl_op (IV 0.037) |
| num_actv_rev_tl | numeric | 0.0199 | 0.00% | 4 | 否 | 2_iv | IV 0.0199 < 0.02 |
| mo_sin_old_il_acct | numeric | 0.0196 | 3.79% | 5 | 否 | 2_iv | IV 0.0196 < 0.02 |
| num_rev_tl_bal_gt_0 | numeric | 0.0195 | 0.00% | 4 | 否 | 2_iv | IV 0.0195 < 0.02 |
| emp_length_years | numeric | 0.0194 | 5.80% | 5 | 否 | 2_iv | IV 0.0194 < 0.02 |
| revol_bal | numeric | 0.0191 | 0.00% | 5 | 否 | 2_iv | IV 0.0191 < 0.02 |
| purpose | categorical | 0.0186 | 0.00% | 4 | 否 | 2_iv | IV 0.0186 < 0.02 |
| revol_util | numeric | 0.0168 | 0.05% | 7 | 否 | 2_iv | IV 0.0168 < 0.02 |
| verification_status | categorical | 0.0152 | 0.00% | 3 | 否 | 2_iv | IV 0.0152 < 0.02 |
| addr_state | categorical | 0.0103 | 0.00% | 5 | 否 | 2_iv | IV 0.0103 < 0.02 |
| funded_amnt | numeric | 0.0086 | 0.00% | 3 | 否 | 2_iv | IV 0.0086 < 0.02 |
| loan_amnt | numeric | 0.0086 | 0.00% | 3 | 否 | 2_iv | IV 0.0086 < 0.02 |
| total_acc | numeric | 0.0076 | 0.00% | 3 | 否 | 2_iv | IV 0.0076 < 0.02 |
| total_bal_ex_mort | numeric | 0.0061 | 0.00% | 3 | 否 | 2_iv | IV 0.0061 < 0.02 |
| num_bc_tl | numeric | 0.0058 | 0.00% | 6 | 否 | 2_iv | IV 0.0058 < 0.02 |
| mths_since_last_record | numeric | 0.0054 | 82.78% | 3 | 否 | 1_missing | missing rate 82.8% > 50% |
| mths_since_last_major_derog | numeric | 0.0054 | 72.77% | 3 | 否 | 1_missing | missing rate 72.8% > 50% |
| initial_list_status | categorical | 0.0053 | 0.00% | 2 | 否 | 2_iv | IV 0.0053 < 0.02 |
| pub_rec | numeric | 0.0044 | 0.00% | 2 | 否 | 2_iv | IV 0.0044 < 0.02 |
| total_il_high_credit_limit | numeric | 0.0043 | 0.00% | 3 | 否 | 2_iv | IV 0.0043 < 0.02 |
| num_op_rev_tl | numeric | 0.0041 | 0.00% | 4 | 否 | 2_iv | IV 0.0041 < 0.02 |
| num_il_tl | numeric | 0.0038 | 0.00% | 3 | 否 | 2_iv | IV 0.0038 < 0.02 |
| num_actv_bc_tl | numeric | 0.0035 | 0.00% | 3 | 否 | 2_iv | IV 0.0035 < 0.02 |
| num_accts_ever_120_pd | numeric | 0.0034 | 0.00% | 3 | 否 | 2_iv | IV 0.0034 < 0.02 |
| pub_rec_bankruptcies | numeric | 0.0033 | 0.00% | 2 | 否 | 2_iv | IV 0.0033 < 0.02 |
| tot_coll_amt | numeric | 0.0027 | 0.00% | 2 | 否 | 2_iv | IV 0.0027 < 0.02 |
| delinq_2yrs | numeric | 0.0019 | 0.00% | 3 | 否 | 2_iv | IV 0.0019 < 0.02 |
| num_tl_120dpd_2m | numeric | 0.0018 | 2.84% | 2 | 否 | 2_iv | IV 0.0018 < 0.02 |
| num_rev_accts | numeric | 0.0017 | 0.00% | 3 | 否 | 2_iv | IV 0.0017 < 0.02 |
| mths_since_recent_bc_dlq | numeric | 0.0012 | 74.36% | 3 | 否 | 1_missing | missing rate 74.4% > 50% |
| pct_tl_nvr_dlq | numeric | 0.0010 | 0.03% | 3 | 否 | 2_iv | IV 0.0010 < 0.02 |
| num_tl_90g_dpd_24m | numeric | 0.0009 | 0.00% | 2 | 否 | 2_iv | IV 0.0009 < 0.02 |
| mths_since_last_delinq | numeric | 0.0009 | 50.44% | 3 | 否 | 1_missing | missing rate 50.4% > 50% |
| num_bc_sats | numeric | 0.0008 | 0.00% | 2 | 否 | 2_iv | IV 0.0008 < 0.02 |
| mths_since_recent_revol_delinq | numeric | 0.0008 | 65.01% | 3 | 否 | 1_missing | missing rate 65.0% > 50% |
| num_sats | numeric | 0.0007 | 0.00% | 2 | 否 | 2_iv | IV 0.0007 < 0.02 |
| open_acc | numeric | 0.0006 | 0.00% | 2 | 否 | 2_iv | IV 0.0006 < 0.02 |
| verification_status_joint | categorical | 0.0000 | 100.00% | 1 | 否 | 1_missing | missing rate 100.0% > 50% |
| collections_12_mths_ex_med | numeric | 0.0000 | 0.00% | 1 | 否 | 2_iv | IV 0.0000 < 0.02 |
| annual_inc_joint | numeric | 0.0000 | 100.00% | 2 | 否 | 1_missing | missing rate 100.0% > 50% |
| application_type | categorical | 0.0000 | 0.00% | 1 | 否 | 2_iv | IV 0.0000 < 0.02 |
| term | numeric | 0.0000 | 0.00% | 1 | 否 | 2_iv | IV 0.0000 < 0.02 |
| dti_joint | numeric | 0.0000 | 100.00% | 2 | 否 | 1_missing | missing rate 100.0% > 50% |
| acc_now_delinq | numeric | 0.0000 | 0.00% | 1 | 否 | 2_iv | IV 0.0000 < 0.02 |
| il_util | numeric | 0.0000 | 100.00% | 2 | 否 | 1_missing | missing rate 100.0% > 50% |
| total_bal_il | numeric | 0.0000 | 100.00% | 2 | 否 | 1_missing | missing rate 100.0% > 50% |
| mths_since_rcnt_il | numeric | 0.0000 | 100.00% | 2 | 否 | 1_missing | missing rate 100.0% > 50% |
| open_il_24m | numeric | 0.0000 | 100.00% | 2 | 否 | 1_missing | missing rate 100.0% > 50% |
| open_il_12m | numeric | 0.0000 | 100.00% | 2 | 否 | 1_missing | missing rate 100.0% > 50% |
| open_act_il | numeric | 0.0000 | 100.00% | 2 | 否 | 1_missing | missing rate 100.0% > 50% |
| open_acc_6m | numeric | 0.0000 | 100.00% | 2 | 否 | 1_missing | missing rate 100.0% > 50% |
| inq_last_12m | numeric | 0.0000 | 100.00% | 2 | 否 | 1_missing | missing rate 100.0% > 50% |
| chargeoff_within_12_mths | numeric | 0.0000 | 0.00% | 1 | 否 | 2_iv | IV 0.0000 < 0.02 |
| total_cu_tl | numeric | 0.0000 | 100.00% | 2 | 否 | 1_missing | missing rate 100.0% > 50% |
| inq_fi | numeric | 0.0000 | 100.00% | 2 | 否 | 1_missing | missing rate 100.0% > 50% |
| all_util | numeric | 0.0000 | 100.00% | 2 | 否 | 1_missing | missing rate 100.0% > 50% |
| open_rv_24m | numeric | 0.0000 | 100.00% | 2 | 否 | 1_missing | missing rate 100.0% > 50% |
| max_bal_bc | numeric | 0.0000 | 100.00% | 2 | 否 | 1_missing | missing rate 100.0% > 50% |
| delinq_amnt | numeric | 0.0000 | 0.00% | 1 | 否 | 2_iv | IV 0.0000 < 0.02 |
| open_rv_12m | numeric | 0.0000 | 100.00% | 2 | 否 | 1_missing | missing rate 100.0% > 50% |
| sec_app_fico_range_high | numeric | 0.0000 | 100.00% | 2 | 否 | 1_missing | missing rate 100.0% > 50% |
| sec_app_fico_range_low | numeric | 0.0000 | 100.00% | 2 | 否 | 1_missing | missing rate 100.0% > 50% |
| revol_bal_joint | numeric | 0.0000 | 100.00% | 2 | 否 | 1_missing | missing rate 100.0% > 50% |
| tax_liens | numeric | 0.0000 | 0.00% | 1 | 否 | 2_iv | IV 0.0000 < 0.02 |
| num_tl_30dpd | numeric | 0.0000 | 0.00% | 1 | 否 | 2_iv | IV 0.0000 < 0.02 |
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
| IV < 0.02 | 40 | 24 |
| 时间稳定性 CSI > 0.25（train 内 2013 vs 2015） | 0 | 24 |
| \|corr\| > 0.7（保留 IV 高者） | 8 | 16 |
| LR 系数为正（WOE 方向反转） | 1 | 15 |

[不含平台评级] 2.3b 时间稳定性：没有特征因 train 内 2013 vs 2015 的 CSI > 0.25 被剔除（最大 0.057，acc_open_past_24mths）。

### [不含平台评级] 时间稳定性 CSI（通过缺失率与 IV 筛选的全部候选特征）

| 特征 | IV | time CSI | 偏移最大的箱 | 2013 占比 | 2015 占比 |
|---|---|---|---|---|---|
| acc_open_past_24mths | 0.0711 | 0.0570 | > 8 | 5.51% | 10.46% |
| num_tl_op_past_12m | 0.0579 | 0.0512 | > 3 | 12.00% | 19.10% |
| mo_sin_old_rev_tl_op | 0.0369 | 0.0478 | (58, 84] | 8.98% | 5.22% |
| inq_last_6mths | 0.0318 | 0.0376 | <= 0 | 52.39% | 59.96% |
| percent_bc_gt_75 | 0.0339 | 0.0372 | <= 0 | 15.16% | 21.92% |
| mths_since_recent_bc | 0.0331 | 0.0284 | > 49 | 16.54% | 12.28% |
| dti | 0.0507 | 0.0266 | > 23.02 | 22.92% | 29.84% |
| bc_util | 0.0235 | 0.0246 | <= 50.5 | 26.57% | 33.45% |
| fico_mid | 0.1388 | 0.0242 | <= 672 | 24.10% | 30.52% |
| mo_sin_rcnt_tl | 0.0410 | 0.0231 | > 13 | 18.50% | 14.50% |
| loan_to_inc | 0.0369 | 0.0177 | > 0.3571 | 6.90% | 9.74% |
| avg_cur_bal | 0.0737 | 0.0130 | (2,482, 5,250] | 22.29% | 24.90% |
| home_ownership | 0.0451 | 0.0124 | {OTHER_RARE, MORTGAGE} | 49.95% | 44.83% |
| credit_hist_months | 0.0227 | 0.0117 | > 223 | 27.16% | 31.76% |
| total_rev_hi_lim | 0.0557 | 0.0115 | > 53,700 | 10.59% | 13.21% |
| tot_hi_cred_lim | 0.0765 | 0.0101 | (67,226, 177,490] | 24.31% | 27.19% |
| mo_sin_rcnt_rev_tl_op | 0.0319 | 0.0098 | > 16 | 26.28% | 22.75% |
| total_bc_limit | 0.0714 | 0.0085 | <= 4,550 | 12.26% | 14.81% |
| mths_since_recent_inq | 0.0370 | 0.0079 | (10, 16] | 15.06% | 12.99% |
| tot_cur_bal | 0.0609 | 0.0066 | (54,380, 137,313] | 17.48% | 20.01% |
| bc_open_to_buy | 0.0772 | 0.0059 | (800, 2,750] | 23.40% | 21.89% |
| mort_acc | 0.0485 | 0.0050 | > 3 | 18.63% | 16.13% |
| annual_inc | 0.0764 | 0.0024 | > 110,000 | 11.77% | 13.17% |
| log_annual_inc | 0.0764 | 0.0024 | > 11.61 | 11.77% | 13.17% |

### [不含平台评级] 2.4 单调性检查（入模特征）

| 特征 | 类型 | 切点来源 | 初始箱数 | 初始单调 | 最终箱数（含缺失箱） | 最终单调 | 最大箱占比 |
|---|---|---|---|---|---|---|---|
| fico_mid | numeric | toad | 6 | 是 | 6 | 是 | 28.81% |
| bc_open_to_buy | numeric | toad | 6 | 是 | 7 | 是 | 22.75% |
| tot_hi_cred_lim | numeric | toad | 6 | 是 | 6 | 是 | 25.96% |
| log_annual_inc | numeric | toad | 6 | 是 | 6 | 是 | 27.16% |
| acc_open_past_24mths | numeric | toad | 6 | 是 | 6 | 是 | 26.76% |
| total_rev_hi_lim | numeric | toad | 6 | 是 | 6 | 是 | 34.24% |
| dti | numeric | toad | 4 | 是 | 4 | 是 | 30.09% |
| mort_acc | numeric | toad | 5 | 是 | 5 | 是 | 43.04% |
| home_ownership | categorical | unique_values | 3 | 是 | 3 | 是 | 47.12% |
| mo_sin_rcnt_tl | numeric | toad | 6 | 是 | 6 | 是 | 24.58% |
| mths_since_recent_inq | numeric | toad | 6 | 是 | 7 | 是 | 23.01% |
| mo_sin_old_rev_tl_op | numeric | toad | 6 | 是 | 6 | 是 | 39.68% |
| loan_to_inc | numeric | toad | 6 | 是 | 6 | 是 | 29.15% |
| percent_bc_gt_75 | numeric | toad | 6 | 否 | 6 | 是 | 30.23% |
| mths_since_recent_bc | numeric | toad | 6 | 是 | 7 | 是 | 25.91% |

_类别型特征按 train bad rate 排序后再分箱，因此天然单调。数值型不单调时合并相邻箱，直到 bad rate 单调或只剩 2 箱。切点来源 unique_values = 取值数不超过 max_bins、逐值成箱。_

![[不含平台评级] 图 2.2 fico_mid 的 WOE（IV 第 1 名）](figures/04_woe_no_platform_rating_01_fico_mid.png)

_[不含平台评级] 图 2.2 fico_mid 的 WOE（IV 第 1 名）_

![[不含平台评级] 图 2.3 bc_open_to_buy 的 WOE（IV 第 2 名）](figures/04_woe_no_platform_rating_02_bc_open_to_buy.png)

_[不含平台评级] 图 2.3 bc_open_to_buy 的 WOE（IV 第 2 名）_

![[不含平台评级] 图 2.4 tot_hi_cred_lim 的 WOE（IV 第 3 名）](figures/04_woe_no_platform_rating_03_tot_hi_cred_lim.png)

_[不含平台评级] 图 2.4 tot_hi_cred_lim 的 WOE（IV 第 3 名）_

![[不含平台评级] 图 2.5 log_annual_inc 的 WOE（IV 第 4 名）](figures/04_woe_no_platform_rating_04_log_annual_inc.png)

_[不含平台评级] 图 2.5 log_annual_inc 的 WOE（IV 第 4 名）_

![[不含平台评级] 图 2.6 acc_open_past_24mths 的 WOE（IV 第 5 名）](figures/04_woe_no_platform_rating_05_acc_open_past_24mths.png)

_[不含平台评级] 图 2.6 acc_open_past_24mths 的 WOE（IV 第 5 名）_

![[不含平台评级] 图 2.7 total_rev_hi_lim 的 WOE（IV 第 6 名）](figures/04_woe_no_platform_rating_06_total_rev_hi_lim.png)

_[不含平台评级] 图 2.7 total_rev_hi_lim 的 WOE（IV 第 6 名）_

![[不含平台评级] 图 2.8 dti 的 WOE（IV 第 7 名）](figures/04_woe_no_platform_rating_07_dti.png)

_[不含平台评级] 图 2.8 dti 的 WOE（IV 第 7 名）_

![[不含平台评级] 图 2.9 mort_acc 的 WOE（IV 第 8 名）](figures/04_woe_no_platform_rating_08_mort_acc.png)

_[不含平台评级] 图 2.9 mort_acc 的 WOE（IV 第 8 名）_

### [不含平台评级] 分箱表：fico_mid（IV = 0.1388）

| 分箱 | 人数 | 占比 | bad 数 | bad rate | WOE |
|---|---|---|---|---|---|
| <= 672 | 77,393 | 28.81% | 14,134 | 18.26% | -0.3334 |
| (672, 687] | 63,337 | 23.58% | 9,956 | 15.72% | -0.1527 |
| (687, 697] | 34,434 | 12.82% | 4,673 | 13.57% | 0.0194 |
| (697, 717] | 47,365 | 17.63% | 5,167 | 10.91% | 0.2681 |
| (717, 742] | 26,968 | 10.04% | 2,146 | 7.96% | 0.6161 |
| > 742 | 19,150 | 7.13% | 997 | 5.21% | 1.0698 |

### [不含平台评级] 分箱表：bc_open_to_buy（IV = 0.0772）

| 分箱 | 人数 | 占比 | bad 数 | bad rate | WOE |
|---|---|---|---|---|---|
| <= 800 | 53,442 | 19.89% | 9,450 | 17.68% | -0.2940 |
| (800, 2,750] | 61,114 | 22.75% | 9,673 | 15.83% | -0.1609 |
| (2,750, 4,993] | 39,648 | 14.76% | 5,661 | 14.28% | -0.0396 |
| (4,993, 9,403] | 41,150 | 15.32% | 5,248 | 12.75% | 0.0909 |
| (9,403, 21,001] | 41,250 | 15.35% | 4,376 | 10.61% | 0.2994 |
| > 21,001 | 29,351 | 10.93% | 2,234 | 7.61% | 0.6644 |
| Missing | 2,692 | 1.00% | 431 | 16.01% | -0.1746 |

### [不含平台评级] 分箱表：tot_hi_cred_lim（IV = 0.0765）

| 分箱 | 人数 | 占比 | bad 数 | bad rate | WOE |
|---|---|---|---|---|---|
| <= 39,077 | 60,481 | 22.51% | 10,642 | 17.60% | -0.2880 |
| (39,077, 67,226] | 49,643 | 18.48% | 7,931 | 15.98% | -0.1720 |
| (67,226, 177,490] | 69,742 | 25.96% | 9,782 | 14.03% | -0.0189 |
| (177,490, 254,061] | 32,276 | 12.01% | 3,683 | 11.41% | 0.2174 |
| (254,061, 381,767] | 32,356 | 12.04% | 3,126 | 9.66% | 0.4034 |
| > 381,767 | 24,149 | 8.99% | 1,909 | 7.91% | 0.6233 |

### [不含平台评级] 分箱表：log_annual_inc（IV = 0.0764）

| 分箱 | 人数 | 占比 | bad 数 | bad rate | WOE |
|---|---|---|---|---|---|
| <= 10.52 | 44,777 | 16.67% | 8,700 | 19.43% | -0.4097 |
| (10.52, 10.71] | 33,252 | 12.38% | 5,425 | 16.31% | -0.1970 |
| (10.71, 11.08] | 72,958 | 27.16% | 10,323 | 14.15% | -0.0291 |
| (11.08, 11.29] | 39,234 | 14.60% | 4,841 | 12.34% | 0.1287 |
| (11.29, 11.61] | 44,329 | 16.50% | 4,601 | 10.38% | 0.3238 |
| > 11.61 | 34,097 | 12.69% | 3,183 | 9.34% | 0.4414 |

### [不含平台评级] 分箱表：acc_open_past_24mths（IV = 0.0711）

| 分箱 | 人数 | 占比 | bad 数 | bad rate | WOE |
|---|---|---|---|---|---|
| <= 1 | 40,110 | 14.93% | 3,757 | 9.37% | 0.4376 |
| (1, 2] | 38,101 | 14.18% | 4,174 | 10.96% | 0.2633 |
| (2, 3] | 41,982 | 15.63% | 5,191 | 12.36% | 0.1263 |
| (3, 5] | 71,883 | 26.76% | 10,280 | 14.30% | -0.0415 |
| (5, 8] | 54,620 | 20.33% | 9,090 | 16.64% | -0.2208 |
| > 8 | 21,951 | 8.17% | 4,581 | 20.87% | -0.4992 |

### [不含平台评级] 分箱表：total_rev_hi_lim（IV = 0.0557）

| 分箱 | 人数 | 占比 | bad 数 | bad rate | WOE |
|---|---|---|---|---|---|
| <= 6,700 | 20,769 | 7.73% | 3,761 | 18.11% | -0.3230 |
| (6,700, 18,200] | 91,982 | 34.24% | 14,640 | 15.92% | -0.1675 |
| (18,200, 31,000] | 69,873 | 26.01% | 9,666 | 13.83% | -0.0028 |
| (31,000, 38,400] | 24,201 | 9.01% | 2,992 | 12.36% | 0.1265 |
| (38,400, 53,700] | 29,547 | 11.00% | 3,250 | 11.00% | 0.2588 |
| > 53,700 | 32,275 | 12.01% | 2,764 | 8.56% | 0.5361 |

### [不含平台评级] 分箱表：dti（IV = 0.0507）

| 分箱 | 人数 | 占比 | bad 数 | bad rate | WOE |
|---|---|---|---|---|---|
| <= 12.7 | 80,844 | 30.09% | 8,747 | 10.82% | 0.2773 |
| (12.7, 19] | 75,228 | 28.00% | 9,585 | 12.74% | 0.0920 |
| (19, 23.02] | 41,695 | 15.52% | 6,134 | 14.71% | -0.0746 |
| > 23.02 | 70,880 | 26.38% | 12,607 | 17.79% | -0.3011 |

### [不含平台评级] 分箱表：mort_acc（IV = 0.0485）

| 分箱 | 人数 | 占比 | bad 数 | bad rate | WOE |
|---|---|---|---|---|---|
| <= 0 | 115,629 | 43.04% | 19,122 | 16.54% | -0.2132 |
| (0, 1] | 43,360 | 16.14% | 5,844 | 13.48% | 0.0273 |
| (1, 2] | 35,272 | 13.13% | 4,294 | 12.17% | 0.1440 |
| (2, 3] | 26,918 | 10.02% | 3,024 | 11.23% | 0.2350 |
| > 3 | 47,468 | 17.67% | 4,789 | 10.09% | 0.3554 |

### [不含平台评级] 分箱表：home_ownership（IV = 0.0451）

| 分箱 | 人数 | 占比 | bad 数 | bad rate | WOE |
|---|---|---|---|---|---|
| {OTHER_RARE, MORTGAGE} | 126,598 | 47.12% | 14,181 | 11.20% | 0.2383 |
| {OWN} | 26,822 | 9.98% | 3,901 | 14.54% | -0.0612 |
| {RENT} | 115,227 | 42.89% | 18,991 | 16.48% | -0.2092 |

### [不含平台评级] 分箱表：mo_sin_rcnt_tl（IV = 0.0410）

| 分箱 | 人数 | 占比 | bad 数 | bad rate | WOE |
|---|---|---|---|---|---|
| <= 1 | 26,704 | 9.94% | 4,691 | 17.57% | -0.2860 |
| (1, 3] | 55,709 | 20.74% | 8,885 | 15.95% | -0.1700 |
| (3, 6] | 66,024 | 24.58% | 9,550 | 14.46% | -0.0548 |
| (6, 9] | 45,151 | 16.81% | 5,889 | 13.04% | 0.0652 |
| (9, 13] | 33,085 | 12.32% | 3,981 | 12.03% | 0.1573 |
| > 13 | 41,974 | 15.62% | 4,077 | 9.71% | 0.3975 |

### [不含平台评级] 分箱表：mths_since_recent_inq（IV = 0.0370）

| 分箱 | 人数 | 占比 | bad 数 | bad rate | WOE |
|---|---|---|---|---|---|
| <= 1 | 47,045 | 17.51% | 8,021 | 17.05% | -0.2499 |
| (1, 3] | 40,214 | 14.97% | 6,268 | 15.59% | -0.1427 |
| (3, 7] | 61,816 | 23.01% | 8,850 | 14.32% | -0.0428 |
| (7, 10] | 32,280 | 12.02% | 4,195 | 13.00% | 0.0693 |
| (10, 16] | 37,702 | 14.03% | 4,608 | 12.22% | 0.1395 |
| > 16 | 22,130 | 8.24% | 2,436 | 11.01% | 0.2579 |
| Missing | 27,460 | 10.22% | 2,695 | 9.81% | 0.3860 |

### [不含平台评级] 分箱表：mo_sin_old_rev_tl_op（IV = 0.0369）

| 分箱 | 人数 | 占比 | bad 数 | bad rate | WOE |
|---|---|---|---|---|---|
| <= 58 | 13,469 | 5.01% | 2,829 | 21.00% | -0.5073 |
| (58, 84] | 17,872 | 6.65% | 3,084 | 17.26% | -0.2644 |
| (84, 119] | 42,815 | 15.94% | 6,607 | 15.43% | -0.1309 |
| (119, 203] | 106,606 | 39.68% | 14,407 | 13.51% | 0.0242 |
| (203, 253] | 37,252 | 13.87% | 4,498 | 12.07% | 0.1534 |
| > 253 | 50,633 | 18.85% | 5,648 | 11.15% | 0.2430 |

### [不含平台评级] 分箱表：loan_to_inc（IV = 0.0369）

| 分箱 | 人数 | 占比 | bad 数 | bad rate | WOE |
|---|---|---|---|---|---|
| <= 0.06667 | 22,792 | 8.48% | 2,408 | 10.57% | 0.3039 |
| (0.06667, 0.15] | 78,320 | 29.15% | 9,452 | 12.07% | 0.1540 |
| (0.15, 0.1963] | 43,886 | 16.34% | 5,572 | 12.70% | 0.0961 |
| (0.1963, 0.27] | 57,883 | 21.55% | 8,144 | 14.07% | -0.0225 |
| (0.27, 0.3571] | 42,312 | 15.75% | 7,198 | 17.01% | -0.2472 |
| > 0.3571 | 23,454 | 8.73% | 4,299 | 18.33% | -0.3378 |

### [不含平台评级] 分箱表：percent_bc_gt_75（IV = 0.0339）

| 分箱 | 人数 | 占比 | bad 数 | bad rate | WOE |
|---|---|---|---|---|---|
| <= 0 | 50,871 | 18.94% | 5,404 | 10.62% | 0.2978 |
| (0, 25] | 33,385 | 12.43% | 3,917 | 11.73% | 0.1860 |
| (25, 50] | 68,191 | 25.38% | 9,186 | 13.47% | 0.0279 |
| (50, 66.7] | 32,195 | 11.98% | 4,819 | 14.97% | -0.0949 |
| > 66.7 | 81,206 | 30.23% | 13,298 | 16.38% | -0.2015 |
| Missing | 2,799 | 1.04% | 449 | 16.04% | -0.1769 |

### [不含平台评级] 分箱表：mths_since_recent_bc（IV = 0.0331）

| 分箱 | 人数 | 占比 | bad 数 | bad rate | WOE |
|---|---|---|---|---|---|
| <= 2 | 22,697 | 8.45% | 3,983 | 17.55% | -0.2848 |
| (2, 7] | 57,991 | 21.59% | 8,893 | 15.34% | -0.1235 |
| (7, 16] | 69,601 | 25.91% | 10,146 | 14.58% | -0.0639 |
| (16, 31] | 53,821 | 20.03% | 7,043 | 13.09% | 0.0614 |
| (31, 49] | 25,532 | 9.50% | 3,012 | 11.80% | 0.1798 |
| > 49 | 36,540 | 13.60% | 3,604 | 9.86% | 0.3805 |
| Missing | 2,465 | 0.92% | 392 | 15.90% | -0.1665 |

### [含平台评级] 2.1 分箱设置

- **分箱后端**：toad（5 个特征库未给出切点，退到 tree：collections_12_mths_ex_med, acc_now_delinq, chargeoff_within_12_mths, delinq_amnt, tax_liens）
- **method / min_samples / max_bins**：chi / 0.05 / 6
- **单调性约束**：是（不单调则合并相邻箱直至单调或退到 2 箱）
- **切点搜索样本量**：200,000（WOE / IV 在全部 train 上计算；筛选阈值也在 train 上评估）
- **WOE 定义**：WOE = ln(good 占比 / bad 占比)，越大越安全；缺失单独一箱
- **候选特征 → 入模特征**：103 → 16

![[含平台评级] 图 2.1 IV 排名（前 30；绿色 = 入模）](figures/03_iv_ranking_with_platform_rating.png)

_[含平台评级] 图 2.1 IV 排名（前 30；绿色 = 入模）_

### [含平台评级] 2.2 IV 排名表（全部候选特征，按 IV 降序）

| 特征 | 类型 | IV | 缺失率（train） | 箱数 | 入模 | 剔除步骤 | 原因 |
|---|---|---|---|---|---|---|---|
| sub_grade | categorical | 0.3378 | 0.00% | 5 | 是 |  | selected |
| int_rate | numeric | 0.3178 | 0.00% | 6 | 否 | 3_corr | \|corr\| = 0.95 with sub_grade (IV 0.338) |
| grade | categorical | 0.3150 | 0.00% | 4 | 否 | 3_corr | \|corr\| = 0.91 with sub_grade (IV 0.338) |
| fico_mid | numeric | 0.1388 | 0.00% | 6 | 是 |  | selected |
| bc_open_to_buy | numeric | 0.0772 | 1.00% | 7 | 是 |  | selected |
| tot_hi_cred_lim | numeric | 0.0765 | 0.00% | 6 | 是 |  | selected |
| annual_inc | numeric | 0.0764 | 0.00% | 6 | 是 |  | selected |
| log_annual_inc | numeric | 0.0764 | 0.00% | 6 | 否 | 3_corr | \|corr\| = 1.00 with annual_inc (IV 0.076) |
| avg_cur_bal | numeric | 0.0737 | 0.00% | 7 | 否 | 3_corr | \|corr\| = 0.85 with tot_hi_cred_lim (IV 0.077) |
| total_bc_limit | numeric | 0.0714 | 0.00% | 6 | 否 | 3_corr | \|corr\| = 0.78 with bc_open_to_buy (IV 0.077) |
| acc_open_past_24mths | numeric | 0.0711 | 0.00% | 6 | 是 |  | selected |
| tot_cur_bal | numeric | 0.0609 | 0.00% | 4 | 否 | 3_corr | \|corr\| = 0.94 with tot_hi_cred_lim (IV 0.077) |
| num_tl_op_past_12m | numeric | 0.0579 | 0.00% | 5 | 否 | 3_corr | \|corr\| = 0.71 with acc_open_past_24mths (IV 0.071) |
| total_rev_hi_lim | numeric | 0.0557 | 0.00% | 6 | 是 |  | selected |
| dti | numeric | 0.0507 | 0.00% | 4 | 是 |  | selected |
| mort_acc | numeric | 0.0485 | 0.00% | 5 | 是 |  | selected |
| home_ownership | categorical | 0.0451 | 0.00% | 3 | 是 |  | selected |
| mo_sin_rcnt_tl | numeric | 0.0410 | 0.00% | 6 | 是 |  | selected |
| mths_since_recent_inq | numeric | 0.0370 | 10.22% | 7 | 是 |  | selected |
| mo_sin_old_rev_tl_op | numeric | 0.0369 | 0.00% | 6 | 是 |  | selected |
| loan_to_inc | numeric | 0.0369 | 0.00% | 6 | 是 |  | selected |
| percent_bc_gt_75 | numeric | 0.0339 | 1.04% | 6 | 是 |  | selected |
| mths_since_recent_bc | numeric | 0.0331 | 0.92% | 7 | 是 |  | selected |
| mo_sin_rcnt_rev_tl_op | numeric | 0.0319 | 0.00% | 3 | 否 | 5_sign | coefficient +0.2218 is not negative |
| inq_last_6mths | numeric | 0.0318 | 0.00% | 4 | 否 | 3_corr | \|corr\| = 0.71 with mths_since_recent_inq (IV 0.037) |
| bc_util | numeric | 0.0235 | 1.07% | 4 | 否 | 3_corr | \|corr\| = 0.77 with percent_bc_gt_75 (IV 0.034) |
| credit_hist_months | numeric | 0.0227 | 0.00% | 5 | 否 | 3_corr | \|corr\| = 0.80 with mo_sin_old_rev_tl_op (IV 0.037) |
| num_actv_rev_tl | numeric | 0.0199 | 0.00% | 4 | 否 | 2_iv | IV 0.0199 < 0.02 |
| mo_sin_old_il_acct | numeric | 0.0196 | 3.79% | 5 | 否 | 2_iv | IV 0.0196 < 0.02 |
| num_rev_tl_bal_gt_0 | numeric | 0.0195 | 0.00% | 4 | 否 | 2_iv | IV 0.0195 < 0.02 |
| emp_length_years | numeric | 0.0194 | 5.80% | 5 | 否 | 2_iv | IV 0.0194 < 0.02 |
| revol_bal | numeric | 0.0191 | 0.00% | 5 | 否 | 2_iv | IV 0.0191 < 0.02 |
| purpose | categorical | 0.0186 | 0.00% | 4 | 否 | 2_iv | IV 0.0186 < 0.02 |
| revol_util | numeric | 0.0168 | 0.05% | 7 | 否 | 2_iv | IV 0.0168 < 0.02 |
| verification_status | categorical | 0.0152 | 0.00% | 3 | 否 | 2_iv | IV 0.0152 < 0.02 |
| addr_state | categorical | 0.0103 | 0.00% | 5 | 否 | 2_iv | IV 0.0103 < 0.02 |
| loan_amnt | numeric | 0.0086 | 0.00% | 3 | 否 | 2_iv | IV 0.0086 < 0.02 |
| funded_amnt | numeric | 0.0086 | 0.00% | 3 | 否 | 2_iv | IV 0.0086 < 0.02 |
| total_acc | numeric | 0.0076 | 0.00% | 3 | 否 | 2_iv | IV 0.0076 < 0.02 |
| total_bal_ex_mort | numeric | 0.0061 | 0.00% | 3 | 否 | 2_iv | IV 0.0061 < 0.02 |
| num_bc_tl | numeric | 0.0058 | 0.00% | 6 | 否 | 2_iv | IV 0.0058 < 0.02 |
| mths_since_last_record | numeric | 0.0054 | 82.78% | 3 | 否 | 1_missing | missing rate 82.8% > 50% |
| mths_since_last_major_derog | numeric | 0.0054 | 72.77% | 3 | 否 | 1_missing | missing rate 72.8% > 50% |
| initial_list_status | categorical | 0.0053 | 0.00% | 2 | 否 | 2_iv | IV 0.0053 < 0.02 |
| pub_rec | numeric | 0.0044 | 0.00% | 2 | 否 | 2_iv | IV 0.0044 < 0.02 |
| total_il_high_credit_limit | numeric | 0.0043 | 0.00% | 3 | 否 | 2_iv | IV 0.0043 < 0.02 |
| num_op_rev_tl | numeric | 0.0041 | 0.00% | 4 | 否 | 2_iv | IV 0.0041 < 0.02 |
| num_il_tl | numeric | 0.0038 | 0.00% | 3 | 否 | 2_iv | IV 0.0038 < 0.02 |
| num_actv_bc_tl | numeric | 0.0035 | 0.00% | 3 | 否 | 2_iv | IV 0.0035 < 0.02 |
| num_accts_ever_120_pd | numeric | 0.0034 | 0.00% | 3 | 否 | 2_iv | IV 0.0034 < 0.02 |
| pub_rec_bankruptcies | numeric | 0.0033 | 0.00% | 2 | 否 | 2_iv | IV 0.0033 < 0.02 |
| tot_coll_amt | numeric | 0.0027 | 0.00% | 2 | 否 | 2_iv | IV 0.0027 < 0.02 |
| installment | numeric | 0.0024 | 0.00% | 2 | 否 | 2_iv | IV 0.0024 < 0.02 |
| delinq_2yrs | numeric | 0.0019 | 0.00% | 3 | 否 | 2_iv | IV 0.0019 < 0.02 |
| num_tl_120dpd_2m | numeric | 0.0018 | 2.84% | 2 | 否 | 2_iv | IV 0.0018 < 0.02 |
| num_rev_accts | numeric | 0.0017 | 0.00% | 3 | 否 | 2_iv | IV 0.0017 < 0.02 |
| mths_since_recent_bc_dlq | numeric | 0.0012 | 74.36% | 3 | 否 | 1_missing | missing rate 74.4% > 50% |
| pct_tl_nvr_dlq | numeric | 0.0010 | 0.03% | 3 | 否 | 2_iv | IV 0.0010 < 0.02 |
| num_tl_90g_dpd_24m | numeric | 0.0009 | 0.00% | 2 | 否 | 2_iv | IV 0.0009 < 0.02 |
| mths_since_last_delinq | numeric | 0.0009 | 50.44% | 3 | 否 | 1_missing | missing rate 50.4% > 50% |
| num_bc_sats | numeric | 0.0008 | 0.00% | 2 | 否 | 2_iv | IV 0.0008 < 0.02 |
| mths_since_recent_revol_delinq | numeric | 0.0008 | 65.01% | 3 | 否 | 1_missing | missing rate 65.0% > 50% |
| num_sats | numeric | 0.0007 | 0.00% | 2 | 否 | 2_iv | IV 0.0007 < 0.02 |
| open_acc | numeric | 0.0006 | 0.00% | 2 | 否 | 2_iv | IV 0.0006 < 0.02 |
| term | numeric | 0.0000 | 0.00% | 1 | 否 | 2_iv | IV 0.0000 < 0.02 |
| collections_12_mths_ex_med | numeric | 0.0000 | 0.00% | 1 | 否 | 2_iv | IV 0.0000 < 0.02 |
| acc_now_delinq | numeric | 0.0000 | 0.00% | 1 | 否 | 2_iv | IV 0.0000 < 0.02 |
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
| inq_fi | numeric | 0.0000 | 100.00% | 2 | 否 | 1_missing | missing rate 100.0% > 50% |
| total_cu_tl | numeric | 0.0000 | 100.00% | 2 | 否 | 1_missing | missing rate 100.0% > 50% |
| delinq_amnt | numeric | 0.0000 | 0.00% | 1 | 否 | 2_iv | IV 0.0000 < 0.02 |
| chargeoff_within_12_mths | numeric | 0.0000 | 0.00% | 1 | 否 | 2_iv | IV 0.0000 < 0.02 |
| inq_last_12m | numeric | 0.0000 | 100.00% | 2 | 否 | 1_missing | missing rate 100.0% > 50% |
| num_tl_30dpd | numeric | 0.0000 | 0.00% | 1 | 否 | 2_iv | IV 0.0000 < 0.02 |
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
| IV < 0.02 | 41 | 27 |
| 时间稳定性 CSI > 0.25（train 内 2013 vs 2015） | 0 | 27 |
| \|corr\| > 0.7（保留 IV 高者） | 10 | 17 |
| LR 系数为正（WOE 方向反转） | 1 | 16 |

[含平台评级] 2.3b 时间稳定性：没有特征因 train 内 2013 vs 2015 的 CSI > 0.25 被剔除（最大 0.179，int_rate）。

### [含平台评级] 时间稳定性 CSI（通过缺失率与 IV 筛选的全部候选特征）

| 特征 | IV | time CSI | 偏移最大的箱 | 2013 占比 | 2015 占比 |
|---|---|---|---|---|---|
| int_rate | 0.3178 | 0.1787 | > 15.88 | 25.14% | 13.53% |
| grade | 0.3150 | 0.0687 | {B} | 40.07% | 29.57% |
| sub_grade | 0.3378 | 0.0651 | {B2, B3, B4} | 27.52% | 17.62% |
| acc_open_past_24mths | 0.0711 | 0.0570 | > 8 | 5.51% | 10.46% |
| num_tl_op_past_12m | 0.0579 | 0.0512 | > 3 | 12.00% | 19.10% |
| mo_sin_old_rev_tl_op | 0.0369 | 0.0478 | (58, 84] | 8.98% | 5.22% |
| inq_last_6mths | 0.0318 | 0.0376 | <= 0 | 52.39% | 59.96% |
| percent_bc_gt_75 | 0.0339 | 0.0372 | <= 0 | 15.16% | 21.92% |
| mths_since_recent_bc | 0.0331 | 0.0284 | > 49 | 16.54% | 12.28% |
| dti | 0.0507 | 0.0266 | > 23.02 | 22.92% | 29.84% |
| bc_util | 0.0235 | 0.0246 | <= 50.5 | 26.57% | 33.45% |
| fico_mid | 0.1388 | 0.0242 | <= 672 | 24.10% | 30.52% |
| mo_sin_rcnt_tl | 0.0410 | 0.0231 | > 13 | 18.50% | 14.50% |
| loan_to_inc | 0.0369 | 0.0177 | > 0.3571 | 6.90% | 9.74% |
| avg_cur_bal | 0.0737 | 0.0130 | (2,482, 5,250] | 22.29% | 24.90% |
| home_ownership | 0.0451 | 0.0124 | {OTHER_RARE, MORTGAGE} | 49.95% | 44.83% |
| credit_hist_months | 0.0227 | 0.0117 | > 223 | 27.16% | 31.76% |
| total_rev_hi_lim | 0.0557 | 0.0115 | > 53,700 | 10.59% | 13.21% |
| tot_hi_cred_lim | 0.0765 | 0.0101 | (67,226, 177,490] | 24.31% | 27.19% |
| mo_sin_rcnt_rev_tl_op | 0.0319 | 0.0098 | > 16 | 26.28% | 22.75% |
| total_bc_limit | 0.0714 | 0.0085 | <= 4,550 | 12.26% | 14.81% |
| mths_since_recent_inq | 0.0370 | 0.0079 | (10, 16] | 15.06% | 12.99% |
| tot_cur_bal | 0.0609 | 0.0066 | (54,380, 137,313] | 17.48% | 20.01% |
| bc_open_to_buy | 0.0772 | 0.0059 | (800, 2,750] | 23.40% | 21.89% |
| mort_acc | 0.0485 | 0.0050 | > 3 | 18.63% | 16.13% |
| log_annual_inc | 0.0764 | 0.0024 | > 11.61 | 11.77% | 13.17% |
| annual_inc | 0.0764 | 0.0024 | > 110,000 | 11.77% | 13.17% |

### [含平台评级] 2.4 单调性检查（入模特征）

| 特征 | 类型 | 切点来源 | 初始箱数 | 初始单调 | 最终箱数（含缺失箱） | 最终单调 | 最大箱占比 |
|---|---|---|---|---|---|---|---|
| sub_grade | categorical | toad | 5 | 是 | 5 | 是 | 26.87% |
| fico_mid | numeric | toad | 6 | 是 | 6 | 是 | 28.81% |
| bc_open_to_buy | numeric | toad | 6 | 是 | 7 | 是 | 22.75% |
| tot_hi_cred_lim | numeric | toad | 6 | 是 | 6 | 是 | 25.96% |
| annual_inc | numeric | toad | 6 | 是 | 6 | 是 | 27.16% |
| acc_open_past_24mths | numeric | toad | 6 | 是 | 6 | 是 | 26.76% |
| total_rev_hi_lim | numeric | toad | 6 | 是 | 6 | 是 | 34.24% |
| dti | numeric | toad | 4 | 是 | 4 | 是 | 30.09% |
| mort_acc | numeric | toad | 5 | 是 | 5 | 是 | 43.04% |
| home_ownership | categorical | unique_values | 3 | 是 | 3 | 是 | 47.12% |
| mo_sin_rcnt_tl | numeric | toad | 6 | 是 | 6 | 是 | 24.58% |
| mths_since_recent_inq | numeric | toad | 6 | 是 | 7 | 是 | 23.01% |
| mo_sin_old_rev_tl_op | numeric | toad | 6 | 是 | 6 | 是 | 39.68% |
| loan_to_inc | numeric | toad | 6 | 是 | 6 | 是 | 29.15% |
| percent_bc_gt_75 | numeric | toad | 6 | 否 | 6 | 是 | 30.23% |
| mths_since_recent_bc | numeric | toad | 6 | 是 | 7 | 是 | 25.91% |

_类别型特征按 train bad rate 排序后再分箱，因此天然单调。数值型不单调时合并相邻箱，直到 bad rate 单调或只剩 2 箱。切点来源 unique_values = 取值数不超过 max_bins、逐值成箱。_

![[含平台评级] 图 2.2 sub_grade 的 WOE（IV 第 1 名）](figures/04_woe_with_platform_rating_01_sub_grade.png)

_[含平台评级] 图 2.2 sub_grade 的 WOE（IV 第 1 名）_

![[含平台评级] 图 2.3 fico_mid 的 WOE（IV 第 2 名）](figures/04_woe_with_platform_rating_02_fico_mid.png)

_[含平台评级] 图 2.3 fico_mid 的 WOE（IV 第 2 名）_

![[含平台评级] 图 2.4 bc_open_to_buy 的 WOE（IV 第 3 名）](figures/04_woe_with_platform_rating_03_bc_open_to_buy.png)

_[含平台评级] 图 2.4 bc_open_to_buy 的 WOE（IV 第 3 名）_

![[含平台评级] 图 2.5 tot_hi_cred_lim 的 WOE（IV 第 4 名）](figures/04_woe_with_platform_rating_04_tot_hi_cred_lim.png)

_[含平台评级] 图 2.5 tot_hi_cred_lim 的 WOE（IV 第 4 名）_

![[含平台评级] 图 2.6 annual_inc 的 WOE（IV 第 5 名）](figures/04_woe_with_platform_rating_05_annual_inc.png)

_[含平台评级] 图 2.6 annual_inc 的 WOE（IV 第 5 名）_

![[含平台评级] 图 2.7 acc_open_past_24mths 的 WOE（IV 第 6 名）](figures/04_woe_with_platform_rating_06_acc_open_past_24mths.png)

_[含平台评级] 图 2.7 acc_open_past_24mths 的 WOE（IV 第 6 名）_

![[含平台评级] 图 2.8 total_rev_hi_lim 的 WOE（IV 第 7 名）](figures/04_woe_with_platform_rating_07_total_rev_hi_lim.png)

_[含平台评级] 图 2.8 total_rev_hi_lim 的 WOE（IV 第 7 名）_

![[含平台评级] 图 2.9 dti 的 WOE（IV 第 8 名）](figures/04_woe_with_platform_rating_08_dti.png)

_[含平台评级] 图 2.9 dti 的 WOE（IV 第 8 名）_

### [含平台评级] 分箱表：sub_grade（IV = 0.3378）

| 分箱 | 人数 | 占比 | bad 数 | bad rate | WOE |
|---|---|---|---|---|---|
| {A1, A2, A3} | 26,862 | 10.00% | 985 | 3.67% | 1.4365 |
| {A4, A5, B1} | 47,288 | 17.60% | 3,454 | 7.30% | 0.7089 |
| {B2, B3, B4} | 57,086 | 21.25% | 6,015 | 10.54% | 0.3069 |
| {B5, C1, C2, C3} | 65,231 | 24.28% | 10,169 | 15.59% | -0.1429 |
| {C4, C5, D1, D3, D2, D4, D5, E2, E1, F2, E3, E4, G2, F1, E5, G4, G1, F3, G3, F4, F5, G5} | 72,180 | 26.87% | 16,450 | 22.79% | -0.6118 |

### [含平台评级] 分箱表：fico_mid（IV = 0.1388）

| 分箱 | 人数 | 占比 | bad 数 | bad rate | WOE |
|---|---|---|---|---|---|
| <= 672 | 77,393 | 28.81% | 14,134 | 18.26% | -0.3334 |
| (672, 687] | 63,337 | 23.58% | 9,956 | 15.72% | -0.1527 |
| (687, 697] | 34,434 | 12.82% | 4,673 | 13.57% | 0.0194 |
| (697, 717] | 47,365 | 17.63% | 5,167 | 10.91% | 0.2681 |
| (717, 742] | 26,968 | 10.04% | 2,146 | 7.96% | 0.6161 |
| > 742 | 19,150 | 7.13% | 997 | 5.21% | 1.0698 |

### [含平台评级] 分箱表：bc_open_to_buy（IV = 0.0772）

| 分箱 | 人数 | 占比 | bad 数 | bad rate | WOE |
|---|---|---|---|---|---|
| <= 800 | 53,442 | 19.89% | 9,450 | 17.68% | -0.2940 |
| (800, 2,750] | 61,114 | 22.75% | 9,673 | 15.83% | -0.1609 |
| (2,750, 4,993] | 39,648 | 14.76% | 5,661 | 14.28% | -0.0396 |
| (4,993, 9,403] | 41,150 | 15.32% | 5,248 | 12.75% | 0.0909 |
| (9,403, 21,001] | 41,250 | 15.35% | 4,376 | 10.61% | 0.2994 |
| > 21,001 | 29,351 | 10.93% | 2,234 | 7.61% | 0.6644 |
| Missing | 2,692 | 1.00% | 431 | 16.01% | -0.1746 |

### [含平台评级] 分箱表：tot_hi_cred_lim（IV = 0.0765）

| 分箱 | 人数 | 占比 | bad 数 | bad rate | WOE |
|---|---|---|---|---|---|
| <= 39,077 | 60,481 | 22.51% | 10,642 | 17.60% | -0.2880 |
| (39,077, 67,226] | 49,643 | 18.48% | 7,931 | 15.98% | -0.1720 |
| (67,226, 177,490] | 69,742 | 25.96% | 9,782 | 14.03% | -0.0189 |
| (177,490, 254,061] | 32,276 | 12.01% | 3,683 | 11.41% | 0.2174 |
| (254,061, 381,767] | 32,356 | 12.04% | 3,126 | 9.66% | 0.4034 |
| > 381,767 | 24,149 | 8.99% | 1,909 | 7.91% | 0.6233 |

### [含平台评级] 分箱表：annual_inc（IV = 0.0764）

| 分箱 | 人数 | 占比 | bad 数 | bad rate | WOE |
|---|---|---|---|---|---|
| <= 37,000 | 44,777 | 16.67% | 8,700 | 19.43% | -0.4097 |
| (37,000, 45,000] | 33,252 | 12.38% | 5,425 | 16.31% | -0.1970 |
| (45,000, 65,000] | 72,958 | 27.16% | 10,323 | 14.15% | -0.0291 |
| (65,000, 80,000] | 39,234 | 14.60% | 4,841 | 12.34% | 0.1287 |
| (80,000, 110,000] | 44,329 | 16.50% | 4,601 | 10.38% | 0.3238 |
| > 110,000 | 34,097 | 12.69% | 3,183 | 9.34% | 0.4414 |

### [含平台评级] 分箱表：acc_open_past_24mths（IV = 0.0711）

| 分箱 | 人数 | 占比 | bad 数 | bad rate | WOE |
|---|---|---|---|---|---|
| <= 1 | 40,110 | 14.93% | 3,757 | 9.37% | 0.4376 |
| (1, 2] | 38,101 | 14.18% | 4,174 | 10.96% | 0.2633 |
| (2, 3] | 41,982 | 15.63% | 5,191 | 12.36% | 0.1263 |
| (3, 5] | 71,883 | 26.76% | 10,280 | 14.30% | -0.0415 |
| (5, 8] | 54,620 | 20.33% | 9,090 | 16.64% | -0.2208 |
| > 8 | 21,951 | 8.17% | 4,581 | 20.87% | -0.4992 |

### [含平台评级] 分箱表：total_rev_hi_lim（IV = 0.0557）

| 分箱 | 人数 | 占比 | bad 数 | bad rate | WOE |
|---|---|---|---|---|---|
| <= 6,700 | 20,769 | 7.73% | 3,761 | 18.11% | -0.3230 |
| (6,700, 18,200] | 91,982 | 34.24% | 14,640 | 15.92% | -0.1675 |
| (18,200, 31,000] | 69,873 | 26.01% | 9,666 | 13.83% | -0.0028 |
| (31,000, 38,400] | 24,201 | 9.01% | 2,992 | 12.36% | 0.1265 |
| (38,400, 53,700] | 29,547 | 11.00% | 3,250 | 11.00% | 0.2588 |
| > 53,700 | 32,275 | 12.01% | 2,764 | 8.56% | 0.5361 |

### [含平台评级] 分箱表：dti（IV = 0.0507）

| 分箱 | 人数 | 占比 | bad 数 | bad rate | WOE |
|---|---|---|---|---|---|
| <= 12.7 | 80,844 | 30.09% | 8,747 | 10.82% | 0.2773 |
| (12.7, 19] | 75,228 | 28.00% | 9,585 | 12.74% | 0.0920 |
| (19, 23.02] | 41,695 | 15.52% | 6,134 | 14.71% | -0.0746 |
| > 23.02 | 70,880 | 26.38% | 12,607 | 17.79% | -0.3011 |

### [含平台评级] 分箱表：mort_acc（IV = 0.0485）

| 分箱 | 人数 | 占比 | bad 数 | bad rate | WOE |
|---|---|---|---|---|---|
| <= 0 | 115,629 | 43.04% | 19,122 | 16.54% | -0.2132 |
| (0, 1] | 43,360 | 16.14% | 5,844 | 13.48% | 0.0273 |
| (1, 2] | 35,272 | 13.13% | 4,294 | 12.17% | 0.1440 |
| (2, 3] | 26,918 | 10.02% | 3,024 | 11.23% | 0.2350 |
| > 3 | 47,468 | 17.67% | 4,789 | 10.09% | 0.3554 |

### [含平台评级] 分箱表：home_ownership（IV = 0.0451）

| 分箱 | 人数 | 占比 | bad 数 | bad rate | WOE |
|---|---|---|---|---|---|
| {OTHER_RARE, MORTGAGE} | 126,598 | 47.12% | 14,181 | 11.20% | 0.2383 |
| {OWN} | 26,822 | 9.98% | 3,901 | 14.54% | -0.0612 |
| {RENT} | 115,227 | 42.89% | 18,991 | 16.48% | -0.2092 |

### [含平台评级] 分箱表：mo_sin_rcnt_tl（IV = 0.0410）

| 分箱 | 人数 | 占比 | bad 数 | bad rate | WOE |
|---|---|---|---|---|---|
| <= 1 | 26,704 | 9.94% | 4,691 | 17.57% | -0.2860 |
| (1, 3] | 55,709 | 20.74% | 8,885 | 15.95% | -0.1700 |
| (3, 6] | 66,024 | 24.58% | 9,550 | 14.46% | -0.0548 |
| (6, 9] | 45,151 | 16.81% | 5,889 | 13.04% | 0.0652 |
| (9, 13] | 33,085 | 12.32% | 3,981 | 12.03% | 0.1573 |
| > 13 | 41,974 | 15.62% | 4,077 | 9.71% | 0.3975 |

### [含平台评级] 分箱表：mths_since_recent_inq（IV = 0.0370）

| 分箱 | 人数 | 占比 | bad 数 | bad rate | WOE |
|---|---|---|---|---|---|
| <= 1 | 47,045 | 17.51% | 8,021 | 17.05% | -0.2499 |
| (1, 3] | 40,214 | 14.97% | 6,268 | 15.59% | -0.1427 |
| (3, 7] | 61,816 | 23.01% | 8,850 | 14.32% | -0.0428 |
| (7, 10] | 32,280 | 12.02% | 4,195 | 13.00% | 0.0693 |
| (10, 16] | 37,702 | 14.03% | 4,608 | 12.22% | 0.1395 |
| > 16 | 22,130 | 8.24% | 2,436 | 11.01% | 0.2579 |
| Missing | 27,460 | 10.22% | 2,695 | 9.81% | 0.3860 |

### [含平台评级] 分箱表：mo_sin_old_rev_tl_op（IV = 0.0369）

| 分箱 | 人数 | 占比 | bad 数 | bad rate | WOE |
|---|---|---|---|---|---|
| <= 58 | 13,469 | 5.01% | 2,829 | 21.00% | -0.5073 |
| (58, 84] | 17,872 | 6.65% | 3,084 | 17.26% | -0.2644 |
| (84, 119] | 42,815 | 15.94% | 6,607 | 15.43% | -0.1309 |
| (119, 203] | 106,606 | 39.68% | 14,407 | 13.51% | 0.0242 |
| (203, 253] | 37,252 | 13.87% | 4,498 | 12.07% | 0.1534 |
| > 253 | 50,633 | 18.85% | 5,648 | 11.15% | 0.2430 |

### [含平台评级] 分箱表：loan_to_inc（IV = 0.0369）

| 分箱 | 人数 | 占比 | bad 数 | bad rate | WOE |
|---|---|---|---|---|---|
| <= 0.06667 | 22,792 | 8.48% | 2,408 | 10.57% | 0.3039 |
| (0.06667, 0.15] | 78,320 | 29.15% | 9,452 | 12.07% | 0.1540 |
| (0.15, 0.1963] | 43,886 | 16.34% | 5,572 | 12.70% | 0.0961 |
| (0.1963, 0.27] | 57,883 | 21.55% | 8,144 | 14.07% | -0.0225 |
| (0.27, 0.3571] | 42,312 | 15.75% | 7,198 | 17.01% | -0.2472 |
| > 0.3571 | 23,454 | 8.73% | 4,299 | 18.33% | -0.3378 |

### [含平台评级] 分箱表：percent_bc_gt_75（IV = 0.0339）

| 分箱 | 人数 | 占比 | bad 数 | bad rate | WOE |
|---|---|---|---|---|---|
| <= 0 | 50,871 | 18.94% | 5,404 | 10.62% | 0.2978 |
| (0, 25] | 33,385 | 12.43% | 3,917 | 11.73% | 0.1860 |
| (25, 50] | 68,191 | 25.38% | 9,186 | 13.47% | 0.0279 |
| (50, 66.7] | 32,195 | 11.98% | 4,819 | 14.97% | -0.0949 |
| > 66.7 | 81,206 | 30.23% | 13,298 | 16.38% | -0.2015 |
| Missing | 2,799 | 1.04% | 449 | 16.04% | -0.1769 |

### [含平台评级] 分箱表：mths_since_recent_bc（IV = 0.0331）

| 分箱 | 人数 | 占比 | bad 数 | bad rate | WOE |
|---|---|---|---|---|---|
| <= 2 | 22,697 | 8.45% | 3,983 | 17.55% | -0.2848 |
| (2, 7] | 57,991 | 21.59% | 8,893 | 15.34% | -0.1235 |
| (7, 16] | 69,601 | 25.91% | 10,146 | 14.58% | -0.0639 |
| (16, 31] | 53,821 | 20.03% | 7,043 | 13.09% | 0.0614 |
| (31, 49] | 25,532 | 9.50% | 3,012 | 11.80% | 0.1798 |
| > 49 | 36,540 | 13.60% | 3,604 | 9.86% | 0.3805 |
| Missing | 2,465 | 0.92% | 392 | 15.90% | -0.1665 |

## 3. 模型表现

_WOE 逻辑回归评分卡与 GBDT challenger 在 train / test / OOT 上的 AUC、KS、Gini，以及 train 内交叉验证（每折重做分箱与 WOE；入模变量清单固定自全 train）。_

### [不含平台评级] 3.1 LR 系数表（WOE 输入；WOE 越大越安全，系数应为负）

| 特征 | 系数 | IV | VIF |
|---|---|---|---|
| (intercept) | -1.8355 |  |  |
| fico_mid | -0.5373 | 0.1388 | 1.5447 |
| bc_open_to_buy | -0.4215 | 0.0772 | 3.3737 |
| tot_hi_cred_lim | -0.3208 | 0.0765 | 2.7037 |
| log_annual_inc | -0.2172 | 0.0764 | 1.9139 |
| acc_open_past_24mths | -0.7490 | 0.0711 | 1.6131 |
| total_rev_hi_lim | -0.1050 | 0.0557 | 2.9033 |
| dti | -0.5597 | 0.0507 | 1.2619 |
| mort_acc | -0.1827 | 0.0485 | 2.1105 |
| home_ownership | -0.3742 | 0.0451 | 1.8938 |
| mo_sin_rcnt_tl | -0.2757 | 0.0410 | 1.5695 |
| mths_since_recent_inq | -0.6631 | 0.0370 | 1.2094 |
| mo_sin_old_rev_tl_op | -0.3320 | 0.0369 | 1.2657 |
| loan_to_inc | -0.9087 | 0.0369 | 1.2477 |
| percent_bc_gt_75 | -0.4040 | 0.0339 | 1.7885 |
| mths_since_recent_bc | -0.3932 | 0.0331 | 1.4035 |

_LogisticRegression(penalty=l2, C=1.0)；VIF > 5.0 标警。_

### [不含平台评级] 3.2 train / test / OOT 表现

| 模型 | 样本 | 行数 | bad rate | AUC | KS | Gini |
|---|---|---|---|---|---|---|
| LR scorecard | train | 268,647 | 13.80% | 0.6657 | 0.2377 | 0.3315 |
| GBDT challenger | train | 268,647 | 13.80% | 0.7022 | 0.2943 | 0.4043 |
| LR scorecard | test | 115,135 | 13.80% | 0.6624 | 0.2319 | 0.3249 |
| GBDT challenger | test | 115,135 | 13.80% | 0.6865 | 0.2677 | 0.3729 |
| LR scorecard | OOT | 162,236 | 14.71% | 0.6737 | 0.2491 | 0.3475 |
| GBDT challenger | OOT | 162,236 | 14.71% | 0.6968 | 0.2848 | 0.3937 |

### [不含平台评级] 3.3 5 折 CV（train 内；每折重做分箱与 WOE）

| 模型 | AUC 均值 ± std | KS 均值 ± std | 折数 |
|---|---|---|---|
| LR scorecard | 0.6636 ± 0.0030 | 0.2373 ± 0.0039 | 5 |
| GBDT challenger | 0.6867 ± 0.0033 | 0.2726 ± 0.0056 | 5 |

### [不含平台评级] 3.4 LR vs GBDT challenger

| 指标 | LR scorecard | GBDT | GBDT − LR |
|---|---|---|---|
| test AUC | 0.6624 | 0.6865 | +0.0240 |
| test KS | 0.2319 | 0.2677 | +0.0358 |
| OOT AUC | 0.6737 | 0.6968 | +0.0231 |
| OOT KS | 0.2491 | 0.2848 | +0.0357 |

_challenger 直接使用未 WOE 的原始候选特征（含缺失），只作为性能上限参照，不上线。_

![[不含平台评级] 图 3.1 ROC 曲线](figures/05_roc_no_platform_rating.png)

_[不含平台评级] 图 3.1 ROC 曲线_

![[不含平台评级] 图 3.2 KS 曲线（LR，test）](figures/06_ks_no_platform_rating.png)

_[不含平台评级] 图 3.2 KS 曲线（LR，test）_

### [不含平台评级] KS 分段表（test，按 LR 预测概率从高风险到低风险 10 等分）

| 分段 | 人数 | bad 数 | bad rate | 累计 bad 占比 | 累计 good 占比 | KS |
|---|---|---|---|---|---|---|
| 1 | 11,514 | 3,259 | 28.30% | 20.51% | 8.32% | 0.1219 |
| 2 | 11,513 | 2,441 | 21.20% | 35.87% | 17.46% | 0.1842 |
| 3 | 11,514 | 1,988 | 17.27% | 48.39% | 27.06% | 0.2133 |
| 4 | 11,513 | 1,781 | 15.47% | 59.59% | 36.86% | 0.2273 |
| 5 | 11,514 | 1,612 | 14.00% | 69.74% | 46.84% | 0.2290 |
| 6 | 11,513 | 1,382 | 12.00% | 78.44% | 57.05% | 0.2139 |
| 7 | 11,513 | 1,194 | 10.37% | 85.95% | 67.45% | 0.1851 |
| 8 | 11,514 | 987 | 8.57% | 92.16% | 78.05% | 0.1411 |
| 9 | 11,513 | 799 | 6.94% | 97.19% | 88.85% | 0.0835 |
| 10 | 11,514 | 446 | 3.87% | 100.00% | 100.00% | 0.0000 |

### [含平台评级] 3.1 LR 系数表（WOE 输入；WOE 越大越安全，系数应为负）

| 特征 | 系数 | IV | VIF |
|---|---|---|---|
| (intercept) | -1.8362 |  |  |
| sub_grade | -0.6657 | 0.3378 | 1.7079 |
| fico_mid | -0.2595 | 0.1388 | 1.6927 |
| bc_open_to_buy | -0.1283 | 0.0772 | 3.4594 |
| tot_hi_cred_lim | -0.2402 | 0.0765 | 2.7110 |
| annual_inc | -0.1360 | 0.0764 | 1.9225 |
| acc_open_past_24mths | -0.6307 | 0.0711 | 1.6252 |
| total_rev_hi_lim | -0.0849 | 0.0557 | 2.9033 |
| dti | -0.4736 | 0.0507 | 1.2668 |
| mort_acc | -0.1388 | 0.0485 | 2.1110 |
| home_ownership | -0.3560 | 0.0451 | 1.8945 |
| mo_sin_rcnt_tl | -0.0977 | 0.0410 | 1.5811 |
| mths_since_recent_inq | -0.3654 | 0.0370 | 1.2462 |
| mo_sin_old_rev_tl_op | -0.2192 | 0.0369 | 1.2712 |
| loan_to_inc | -0.7717 | 0.0369 | 1.2555 |
| percent_bc_gt_75 | -0.2246 | 0.0339 | 1.8011 |
| mths_since_recent_bc | -0.2996 | 0.0331 | 1.4066 |

_LogisticRegression(penalty=l2, C=1.0)；VIF > 5.0 标警。_

### [含平台评级] 3.2 train / test / OOT 表现

| 模型 | 样本 | 行数 | bad rate | AUC | KS | Gini |
|---|---|---|---|---|---|---|
| LR scorecard | train | 268,647 | 13.80% | 0.6846 | 0.2705 | 0.3692 |
| GBDT challenger | train | 268,647 | 13.80% | 0.7090 | 0.3056 | 0.4179 |
| LR scorecard | test | 115,135 | 13.80% | 0.6816 | 0.2614 | 0.3632 |
| GBDT challenger | test | 115,135 | 13.80% | 0.6938 | 0.2797 | 0.3877 |
| LR scorecard | OOT | 162,236 | 14.71% | 0.6981 | 0.2884 | 0.3962 |
| GBDT challenger | OOT | 162,236 | 14.71% | 0.7106 | 0.3076 | 0.4212 |

### [含平台评级] 3.3 5 折 CV（train 内；每折重做分箱与 WOE）

| 模型 | AUC 均值 ± std | KS 均值 ± std | 折数 |
|---|---|---|---|
| LR scorecard | 0.6838 ± 0.0021 | 0.2705 ± 0.0033 | 5 |
| GBDT challenger | 0.6940 ± 0.0022 | 0.2859 ± 0.0029 | 5 |

### [含平台评级] 3.4 LR vs GBDT challenger

| 指标 | LR scorecard | GBDT | GBDT − LR |
|---|---|---|---|
| test AUC | 0.6816 | 0.6938 | +0.0122 |
| test KS | 0.2614 | 0.2797 | +0.0183 |
| OOT AUC | 0.6981 | 0.7106 | +0.0125 |
| OOT KS | 0.2884 | 0.3076 | +0.0192 |

_challenger 直接使用未 WOE 的原始候选特征（含缺失），只作为性能上限参照，不上线。_

![[含平台评级] 图 3.1 ROC 曲线](figures/05_roc_with_platform_rating.png)

_[含平台评级] 图 3.1 ROC 曲线_

![[含平台评级] 图 3.2 KS 曲线（LR，test）](figures/06_ks_with_platform_rating.png)

_[含平台评级] 图 3.2 KS 曲线（LR，test）_

### [含平台评级] KS 分段表（test，按 LR 预测概率从高风险到低风险 10 等分）

| 分段 | 人数 | bad 数 | bad rate | 累计 bad 占比 | 累计 good 占比 | KS |
|---|---|---|---|---|---|---|
| 1 | 11,514 | 3,439 | 29.87% | 21.64% | 8.14% | 0.1351 |
| 2 | 11,513 | 2,587 | 22.47% | 37.93% | 17.13% | 0.2080 |
| 3 | 11,514 | 2,123 | 18.44% | 51.29% | 26.59% | 0.2469 |
| 4 | 11,513 | 1,751 | 15.21% | 62.31% | 36.43% | 0.2588 |
| 5 | 11,514 | 1,560 | 13.55% | 72.13% | 46.46% | 0.2567 |
| 6 | 11,513 | 1,311 | 11.39% | 80.38% | 56.74% | 0.2364 |
| 7 | 11,513 | 1,134 | 9.85% | 87.51% | 67.20% | 0.2032 |
| 8 | 11,514 | 950 | 8.25% | 93.49% | 77.84% | 0.1565 |
| 9 | 11,513 | 687 | 5.97% | 97.82% | 88.75% | 0.0907 |
| 10 | 11,514 | 347 | 3.01% | 100.00% | 100.00% | 0.0000 |

## 4. 评分卡

_把 WOE 逻辑回归换算为评分卡：PDO、base score、base odds，每个变量每个分箱的分数，以及分数分布。_

### [不含平台评级] 4.1 PDO 换算

- **PDO / base score / base odds**：20 / 600 / 20:1
- **Factor = PDO / ln2**：28.8539
- **Offset = base − Factor × ln(odds)**：600 − 28.8539 × ln(20) = 513.5614
- **LR 截距 b0**：-1.8355
- **基础分 = Offset − Factor × b0**：566.52 → 取整 567
- **分箱分数**：points = −Factor × 系数 × WOE，取整
- **可能的分数范围**：506 ~ 648
- **整数分数的 AUC（test / OOT）**：test 0.6626 / OOT 0.6736

### [不含平台评级] 4.2 评分卡表

| 变量 | 分箱 | train 人数 | 占比 | bad rate | WOE | 系数 | 分数 | 整数分 |
|---|---|---|---|---|---|---|---|---|
| BASE | (every applicant) |  |  |  |  |  | 566.52 | 567 |
| fico_mid | <= 672 | 77,393 | 28.81% | 18.26% | -0.3334 | -0.5373 | -5.17 | -5 |
| fico_mid | (672, 687] | 63,337 | 23.58% | 15.72% | -0.1527 | -0.5373 | -2.37 | -2 |
| fico_mid | (687, 697] | 34,434 | 12.82% | 13.57% | 0.0194 | -0.5373 | 0.30 | 0 |
| fico_mid | (697, 717] | 47,365 | 17.63% | 10.91% | 0.2681 | -0.5373 | 4.16 | 4 |
| fico_mid | (717, 742] | 26,968 | 10.04% | 7.96% | 0.6161 | -0.5373 | 9.55 | 10 |
| fico_mid | > 742 | 19,150 | 7.13% | 5.21% | 1.0698 | -0.5373 | 16.59 | 17 |
| bc_open_to_buy | <= 800 | 53,442 | 19.89% | 17.68% | -0.2940 | -0.4215 | -3.58 | -4 |
| bc_open_to_buy | (800, 2,750] | 61,114 | 22.75% | 15.83% | -0.1609 | -0.4215 | -1.96 | -2 |
| bc_open_to_buy | (2,750, 4,993] | 39,648 | 14.76% | 14.28% | -0.0396 | -0.4215 | -0.48 | 0 |
| bc_open_to_buy | (4,993, 9,403] | 41,150 | 15.32% | 12.75% | 0.0909 | -0.4215 | 1.11 | 1 |
| bc_open_to_buy | (9,403, 21,001] | 41,250 | 15.35% | 10.61% | 0.2994 | -0.4215 | 3.64 | 4 |
| bc_open_to_buy | > 21,001 | 29,351 | 10.93% | 7.61% | 0.6644 | -0.4215 | 8.08 | 8 |
| bc_open_to_buy | Missing | 2,692 | 1.00% | 16.01% | -0.1746 | -0.4215 | -2.12 | -2 |
| tot_hi_cred_lim | <= 39,077 | 60,481 | 22.51% | 17.60% | -0.2880 | -0.3208 | -2.67 | -3 |
| tot_hi_cred_lim | (39,077, 67,226] | 49,643 | 18.48% | 15.98% | -0.1720 | -0.3208 | -1.59 | -2 |
| tot_hi_cred_lim | (67,226, 177,490] | 69,742 | 25.96% | 14.03% | -0.0189 | -0.3208 | -0.17 | 0 |
| tot_hi_cred_lim | (177,490, 254,061] | 32,276 | 12.01% | 11.41% | 0.2174 | -0.3208 | 2.01 | 2 |
| tot_hi_cred_lim | (254,061, 381,767] | 32,356 | 12.04% | 9.66% | 0.4034 | -0.3208 | 3.73 | 4 |
| tot_hi_cred_lim | > 381,767 | 24,149 | 8.99% | 7.91% | 0.6233 | -0.3208 | 5.77 | 6 |
| log_annual_inc | <= 10.52 | 44,777 | 16.67% | 19.43% | -0.4097 | -0.2172 | -2.57 | -3 |
| log_annual_inc | (10.52, 10.71] | 33,252 | 12.38% | 16.31% | -0.1970 | -0.2172 | -1.23 | -1 |
| log_annual_inc | (10.71, 11.08] | 72,958 | 27.16% | 14.15% | -0.0291 | -0.2172 | -0.18 | 0 |
| log_annual_inc | (11.08, 11.29] | 39,234 | 14.60% | 12.34% | 0.1287 | -0.2172 | 0.81 | 1 |
| log_annual_inc | (11.29, 11.61] | 44,329 | 16.50% | 10.38% | 0.3238 | -0.2172 | 2.03 | 2 |
| log_annual_inc | > 11.61 | 34,097 | 12.69% | 9.34% | 0.4414 | -0.2172 | 2.77 | 3 |
| acc_open_past_24mths | <= 1 | 40,110 | 14.93% | 9.37% | 0.4376 | -0.7490 | 9.46 | 9 |
| acc_open_past_24mths | (1, 2] | 38,101 | 14.18% | 10.96% | 0.2633 | -0.7490 | 5.69 | 6 |
| acc_open_past_24mths | (2, 3] | 41,982 | 15.63% | 12.36% | 0.1263 | -0.7490 | 2.73 | 3 |
| acc_open_past_24mths | (3, 5] | 71,883 | 26.76% | 14.30% | -0.0415 | -0.7490 | -0.90 | -1 |
| acc_open_past_24mths | (5, 8] | 54,620 | 20.33% | 16.64% | -0.2208 | -0.7490 | -4.77 | -5 |
| acc_open_past_24mths | > 8 | 21,951 | 8.17% | 20.87% | -0.4992 | -0.7490 | -10.79 | -11 |
| total_rev_hi_lim | <= 6,700 | 20,769 | 7.73% | 18.11% | -0.3230 | -0.1050 | -0.98 | -1 |
| total_rev_hi_lim | (6,700, 18,200] | 91,982 | 34.24% | 15.92% | -0.1675 | -0.1050 | -0.51 | -1 |
| total_rev_hi_lim | (18,200, 31,000] | 69,873 | 26.01% | 13.83% | -0.0028 | -0.1050 | -0.01 | 0 |
| total_rev_hi_lim | (31,000, 38,400] | 24,201 | 9.01% | 12.36% | 0.1265 | -0.1050 | 0.38 | 0 |
| total_rev_hi_lim | (38,400, 53,700] | 29,547 | 11.00% | 11.00% | 0.2588 | -0.1050 | 0.78 | 1 |
| total_rev_hi_lim | > 53,700 | 32,275 | 12.01% | 8.56% | 0.5361 | -0.1050 | 1.62 | 2 |
| dti | <= 12.7 | 80,844 | 30.09% | 10.82% | 0.2773 | -0.5597 | 4.48 | 4 |
| dti | (12.7, 19] | 75,228 | 28.00% | 12.74% | 0.0920 | -0.5597 | 1.49 | 1 |
| dti | (19, 23.02] | 41,695 | 15.52% | 14.71% | -0.0746 | -0.5597 | -1.20 | -1 |
| dti | > 23.02 | 70,880 | 26.38% | 17.79% | -0.3011 | -0.5597 | -4.86 | -5 |
| mort_acc | <= 0 | 115,629 | 43.04% | 16.54% | -0.2132 | -0.1827 | -1.12 | -1 |
| mort_acc | (0, 1] | 43,360 | 16.14% | 13.48% | 0.0273 | -0.1827 | 0.14 | 0 |
| mort_acc | (1, 2] | 35,272 | 13.13% | 12.17% | 0.1440 | -0.1827 | 0.76 | 1 |
| mort_acc | (2, 3] | 26,918 | 10.02% | 11.23% | 0.2350 | -0.1827 | 1.24 | 1 |
| mort_acc | > 3 | 47,468 | 17.67% | 10.09% | 0.3554 | -0.1827 | 1.87 | 2 |
| home_ownership | {OTHER_RARE, MORTGAGE} | 126,598 | 47.12% | 11.20% | 0.2383 | -0.3742 | 2.57 | 3 |
| home_ownership | {OWN} | 26,822 | 9.98% | 14.54% | -0.0612 | -0.3742 | -0.66 | -1 |
| home_ownership | {RENT} | 115,227 | 42.89% | 16.48% | -0.2092 | -0.3742 | -2.26 | -2 |
| mo_sin_rcnt_tl | <= 1 | 26,704 | 9.94% | 17.57% | -0.2860 | -0.2757 | -2.28 | -2 |
| mo_sin_rcnt_tl | (1, 3] | 55,709 | 20.74% | 15.95% | -0.1700 | -0.2757 | -1.35 | -1 |
| mo_sin_rcnt_tl | (3, 6] | 66,024 | 24.58% | 14.46% | -0.0548 | -0.2757 | -0.44 | 0 |
| mo_sin_rcnt_tl | (6, 9] | 45,151 | 16.81% | 13.04% | 0.0652 | -0.2757 | 0.52 | 1 |
| mo_sin_rcnt_tl | (9, 13] | 33,085 | 12.32% | 12.03% | 0.1573 | -0.2757 | 1.25 | 1 |
| mo_sin_rcnt_tl | > 13 | 41,974 | 15.62% | 9.71% | 0.3975 | -0.2757 | 3.16 | 3 |
| mths_since_recent_inq | <= 1 | 47,045 | 17.51% | 17.05% | -0.2499 | -0.6631 | -4.78 | -5 |
| mths_since_recent_inq | (1, 3] | 40,214 | 14.97% | 15.59% | -0.1427 | -0.6631 | -2.73 | -3 |
| mths_since_recent_inq | (3, 7] | 61,816 | 23.01% | 14.32% | -0.0428 | -0.6631 | -0.82 | -1 |
| mths_since_recent_inq | (7, 10] | 32,280 | 12.02% | 13.00% | 0.0693 | -0.6631 | 1.33 | 1 |
| mths_since_recent_inq | (10, 16] | 37,702 | 14.03% | 12.22% | 0.1395 | -0.6631 | 2.67 | 3 |
| mths_since_recent_inq | > 16 | 22,130 | 8.24% | 11.01% | 0.2579 | -0.6631 | 4.94 | 5 |
| mths_since_recent_inq | Missing | 27,460 | 10.22% | 9.81% | 0.3860 | -0.6631 | 7.39 | 7 |
| mo_sin_old_rev_tl_op | <= 58 | 13,469 | 5.01% | 21.00% | -0.5073 | -0.3320 | -4.86 | -5 |
| mo_sin_old_rev_tl_op | (58, 84] | 17,872 | 6.65% | 17.26% | -0.2644 | -0.3320 | -2.53 | -3 |
| mo_sin_old_rev_tl_op | (84, 119] | 42,815 | 15.94% | 15.43% | -0.1309 | -0.3320 | -1.25 | -1 |
| mo_sin_old_rev_tl_op | (119, 203] | 106,606 | 39.68% | 13.51% | 0.0242 | -0.3320 | 0.23 | 0 |
| mo_sin_old_rev_tl_op | (203, 253] | 37,252 | 13.87% | 12.07% | 0.1534 | -0.3320 | 1.47 | 1 |
| mo_sin_old_rev_tl_op | > 253 | 50,633 | 18.85% | 11.15% | 0.2430 | -0.3320 | 2.33 | 2 |
| loan_to_inc | <= 0.06667 | 22,792 | 8.48% | 10.57% | 0.3039 | -0.9087 | 7.97 | 8 |
| loan_to_inc | (0.06667, 0.15] | 78,320 | 29.15% | 12.07% | 0.1540 | -0.9087 | 4.04 | 4 |
| loan_to_inc | (0.15, 0.1963] | 43,886 | 16.34% | 12.70% | 0.0961 | -0.9087 | 2.52 | 3 |
| loan_to_inc | (0.1963, 0.27] | 57,883 | 21.55% | 14.07% | -0.0225 | -0.9087 | -0.59 | -1 |
| loan_to_inc | (0.27, 0.3571] | 42,312 | 15.75% | 17.01% | -0.2472 | -0.9087 | -6.48 | -6 |
| loan_to_inc | > 0.3571 | 23,454 | 8.73% | 18.33% | -0.3378 | -0.9087 | -8.86 | -9 |
| percent_bc_gt_75 | <= 0 | 50,871 | 18.94% | 10.62% | 0.2978 | -0.4040 | 3.47 | 3 |
| percent_bc_gt_75 | (0, 25] | 33,385 | 12.43% | 11.73% | 0.1860 | -0.4040 | 2.17 | 2 |
| percent_bc_gt_75 | (25, 50] | 68,191 | 25.38% | 13.47% | 0.0279 | -0.4040 | 0.33 | 0 |
| percent_bc_gt_75 | (50, 66.7] | 32,195 | 11.98% | 14.97% | -0.0949 | -0.4040 | -1.11 | -1 |
| percent_bc_gt_75 | > 66.7 | 81,206 | 30.23% | 16.38% | -0.2015 | -0.4040 | -2.35 | -2 |
| percent_bc_gt_75 | Missing | 2,799 | 1.04% | 16.04% | -0.1769 | -0.4040 | -2.06 | -2 |
| mths_since_recent_bc | <= 2 | 22,697 | 8.45% | 17.55% | -0.2848 | -0.3932 | -3.23 | -3 |
| mths_since_recent_bc | (2, 7] | 57,991 | 21.59% | 15.34% | -0.1235 | -0.3932 | -1.40 | -1 |
| mths_since_recent_bc | (7, 16] | 69,601 | 25.91% | 14.58% | -0.0639 | -0.3932 | -0.72 | -1 |
| mths_since_recent_bc | (16, 31] | 53,821 | 20.03% | 13.09% | 0.0614 | -0.3932 | 0.70 | 1 |
| mths_since_recent_bc | (31, 49] | 25,532 | 9.50% | 11.80% | 0.1798 | -0.3932 | 2.04 | 2 |
| mths_since_recent_bc | > 49 | 36,540 | 13.60% | 9.86% | 0.3805 | -0.3932 | 4.32 | 4 |
| mths_since_recent_bc | Missing | 2,465 | 0.92% | 15.90% | -0.1665 | -0.3932 | -1.89 | -2 |

![[不含平台评级] 图 4.1 分数分布（test，good / bad 分开）](figures/07_score_dist_no_platform_rating_test.png)

_[不含平台评级] 图 4.1 分数分布（test，good / bad 分开）_

![[不含平台评级] 图 4.2 分数分布（OOT，good / bad 分开）](figures/07_score_dist_no_platform_rating_oot.png)

_[不含平台评级] 图 4.2 分数分布（OOT，good / bad 分开）_

### [含平台评级] 4.1 PDO 换算

- **PDO / base score / base odds**：20 / 600 / 20:1
- **Factor = PDO / ln2**：28.8539
- **Offset = base − Factor × ln(odds)**：600 − 28.8539 × ln(20) = 513.5614
- **LR 截距 b0**：-1.8362
- **基础分 = Offset − Factor × b0**：566.54 → 取整 567
- **分箱分数**：points = −Factor × 系数 × WOE，取整
- **可能的分数范围**：513 ~ 646
- **整数分数的 AUC（test / OOT）**：test 0.6815 / OOT 0.6980

### [含平台评级] 4.2 评分卡表

| 变量 | 分箱 | train 人数 | 占比 | bad rate | WOE | 系数 | 分数 | 整数分 |
|---|---|---|---|---|---|---|---|---|
| BASE | (every applicant) |  |  |  |  |  | 566.54 | 567 |
| sub_grade | {A1, A2, A3} | 26,862 | 10.00% | 3.67% | 1.4365 | -0.6657 | 27.59 | 28 |
| sub_grade | {A4, A5, B1} | 47,288 | 17.60% | 7.30% | 0.7089 | -0.6657 | 13.61 | 14 |
| sub_grade | {B2, B3, B4} | 57,086 | 21.25% | 10.54% | 0.3069 | -0.6657 | 5.90 | 6 |
| sub_grade | {B5, C1, C2, C3} | 65,231 | 24.28% | 15.59% | -0.1429 | -0.6657 | -2.74 | -3 |
| sub_grade | {C4, C5, D1, D3, D2, D4, D5, E2, E1, F2, E3, E4, G2, F1, E5, G4, G1, F3, G3, F4, F5, G5} | 72,180 | 26.87% | 22.79% | -0.6118 | -0.6657 | -11.75 | -12 |
| fico_mid | <= 672 | 77,393 | 28.81% | 18.26% | -0.3334 | -0.2595 | -2.50 | -2 |
| fico_mid | (672, 687] | 63,337 | 23.58% | 15.72% | -0.1527 | -0.2595 | -1.14 | -1 |
| fico_mid | (687, 697] | 34,434 | 12.82% | 13.57% | 0.0194 | -0.2595 | 0.15 | 0 |
| fico_mid | (697, 717] | 47,365 | 17.63% | 10.91% | 0.2681 | -0.2595 | 2.01 | 2 |
| fico_mid | (717, 742] | 26,968 | 10.04% | 7.96% | 0.6161 | -0.2595 | 4.61 | 5 |
| fico_mid | > 742 | 19,150 | 7.13% | 5.21% | 1.0698 | -0.2595 | 8.01 | 8 |
| bc_open_to_buy | <= 800 | 53,442 | 19.89% | 17.68% | -0.2940 | -0.1283 | -1.09 | -1 |
| bc_open_to_buy | (800, 2,750] | 61,114 | 22.75% | 15.83% | -0.1609 | -0.1283 | -0.60 | -1 |
| bc_open_to_buy | (2,750, 4,993] | 39,648 | 14.76% | 14.28% | -0.0396 | -0.1283 | -0.15 | 0 |
| bc_open_to_buy | (4,993, 9,403] | 41,150 | 15.32% | 12.75% | 0.0909 | -0.1283 | 0.34 | 0 |
| bc_open_to_buy | (9,403, 21,001] | 41,250 | 15.35% | 10.61% | 0.2994 | -0.1283 | 1.11 | 1 |
| bc_open_to_buy | > 21,001 | 29,351 | 10.93% | 7.61% | 0.6644 | -0.1283 | 2.46 | 2 |
| bc_open_to_buy | Missing | 2,692 | 1.00% | 16.01% | -0.1746 | -0.1283 | -0.65 | -1 |
| tot_hi_cred_lim | <= 39,077 | 60,481 | 22.51% | 17.60% | -0.2880 | -0.2402 | -2.00 | -2 |
| tot_hi_cred_lim | (39,077, 67,226] | 49,643 | 18.48% | 15.98% | -0.1720 | -0.2402 | -1.19 | -1 |
| tot_hi_cred_lim | (67,226, 177,490] | 69,742 | 25.96% | 14.03% | -0.0189 | -0.2402 | -0.13 | 0 |
| tot_hi_cred_lim | (177,490, 254,061] | 32,276 | 12.01% | 11.41% | 0.2174 | -0.2402 | 1.51 | 2 |
| tot_hi_cred_lim | (254,061, 381,767] | 32,356 | 12.04% | 9.66% | 0.4034 | -0.2402 | 2.80 | 3 |
| tot_hi_cred_lim | > 381,767 | 24,149 | 8.99% | 7.91% | 0.6233 | -0.2402 | 4.32 | 4 |
| annual_inc | <= 37,000 | 44,777 | 16.67% | 19.43% | -0.4097 | -0.1360 | -1.61 | -2 |
| annual_inc | (37,000, 45,000] | 33,252 | 12.38% | 16.31% | -0.1970 | -0.1360 | -0.77 | -1 |
| annual_inc | (45,000, 65,000] | 72,958 | 27.16% | 14.15% | -0.0291 | -0.1360 | -0.11 | 0 |
| annual_inc | (65,000, 80,000] | 39,234 | 14.60% | 12.34% | 0.1287 | -0.1360 | 0.51 | 1 |
| annual_inc | (80,000, 110,000] | 44,329 | 16.50% | 10.38% | 0.3238 | -0.1360 | 1.27 | 1 |
| annual_inc | > 110,000 | 34,097 | 12.69% | 9.34% | 0.4414 | -0.1360 | 1.73 | 2 |
| acc_open_past_24mths | <= 1 | 40,110 | 14.93% | 9.37% | 0.4376 | -0.6307 | 7.96 | 8 |
| acc_open_past_24mths | (1, 2] | 38,101 | 14.18% | 10.96% | 0.2633 | -0.6307 | 4.79 | 5 |
| acc_open_past_24mths | (2, 3] | 41,982 | 15.63% | 12.36% | 0.1263 | -0.6307 | 2.30 | 2 |
| acc_open_past_24mths | (3, 5] | 71,883 | 26.76% | 14.30% | -0.0415 | -0.6307 | -0.76 | -1 |
| acc_open_past_24mths | (5, 8] | 54,620 | 20.33% | 16.64% | -0.2208 | -0.6307 | -4.02 | -4 |
| acc_open_past_24mths | > 8 | 21,951 | 8.17% | 20.87% | -0.4992 | -0.6307 | -9.08 | -9 |
| total_rev_hi_lim | <= 6,700 | 20,769 | 7.73% | 18.11% | -0.3230 | -0.0849 | -0.79 | -1 |
| total_rev_hi_lim | (6,700, 18,200] | 91,982 | 34.24% | 15.92% | -0.1675 | -0.0849 | -0.41 | 0 |
| total_rev_hi_lim | (18,200, 31,000] | 69,873 | 26.01% | 13.83% | -0.0028 | -0.0849 | -0.01 | 0 |
| total_rev_hi_lim | (31,000, 38,400] | 24,201 | 9.01% | 12.36% | 0.1265 | -0.0849 | 0.31 | 0 |
| total_rev_hi_lim | (38,400, 53,700] | 29,547 | 11.00% | 11.00% | 0.2588 | -0.0849 | 0.63 | 1 |
| total_rev_hi_lim | > 53,700 | 32,275 | 12.01% | 8.56% | 0.5361 | -0.0849 | 1.31 | 1 |
| dti | <= 12.7 | 80,844 | 30.09% | 10.82% | 0.2773 | -0.4736 | 3.79 | 4 |
| dti | (12.7, 19] | 75,228 | 28.00% | 12.74% | 0.0920 | -0.4736 | 1.26 | 1 |
| dti | (19, 23.02] | 41,695 | 15.52% | 14.71% | -0.0746 | -0.4736 | -1.02 | -1 |
| dti | > 23.02 | 70,880 | 26.38% | 17.79% | -0.3011 | -0.4736 | -4.12 | -4 |
| mort_acc | <= 0 | 115,629 | 43.04% | 16.54% | -0.2132 | -0.1388 | -0.85 | -1 |
| mort_acc | (0, 1] | 43,360 | 16.14% | 13.48% | 0.0273 | -0.1388 | 0.11 | 0 |
| mort_acc | (1, 2] | 35,272 | 13.13% | 12.17% | 0.1440 | -0.1388 | 0.58 | 1 |
| mort_acc | (2, 3] | 26,918 | 10.02% | 11.23% | 0.2350 | -0.1388 | 0.94 | 1 |
| mort_acc | > 3 | 47,468 | 17.67% | 10.09% | 0.3554 | -0.1388 | 1.42 | 1 |
| home_ownership | {OTHER_RARE, MORTGAGE} | 126,598 | 47.12% | 11.20% | 0.2383 | -0.3560 | 2.45 | 2 |
| home_ownership | {OWN} | 26,822 | 9.98% | 14.54% | -0.0612 | -0.3560 | -0.63 | -1 |
| home_ownership | {RENT} | 115,227 | 42.89% | 16.48% | -0.2092 | -0.3560 | -2.15 | -2 |
| mo_sin_rcnt_tl | <= 1 | 26,704 | 9.94% | 17.57% | -0.2860 | -0.0977 | -0.81 | -1 |
| mo_sin_rcnt_tl | (1, 3] | 55,709 | 20.74% | 15.95% | -0.1700 | -0.0977 | -0.48 | 0 |
| mo_sin_rcnt_tl | (3, 6] | 66,024 | 24.58% | 14.46% | -0.0548 | -0.0977 | -0.15 | 0 |
| mo_sin_rcnt_tl | (6, 9] | 45,151 | 16.81% | 13.04% | 0.0652 | -0.0977 | 0.18 | 0 |
| mo_sin_rcnt_tl | (9, 13] | 33,085 | 12.32% | 12.03% | 0.1573 | -0.0977 | 0.44 | 0 |
| mo_sin_rcnt_tl | > 13 | 41,974 | 15.62% | 9.71% | 0.3975 | -0.0977 | 1.12 | 1 |
| mths_since_recent_inq | <= 1 | 47,045 | 17.51% | 17.05% | -0.2499 | -0.3654 | -2.63 | -3 |
| mths_since_recent_inq | (1, 3] | 40,214 | 14.97% | 15.59% | -0.1427 | -0.3654 | -1.50 | -2 |
| mths_since_recent_inq | (3, 7] | 61,816 | 23.01% | 14.32% | -0.0428 | -0.3654 | -0.45 | 0 |
| mths_since_recent_inq | (7, 10] | 32,280 | 12.02% | 13.00% | 0.0693 | -0.3654 | 0.73 | 1 |
| mths_since_recent_inq | (10, 16] | 37,702 | 14.03% | 12.22% | 0.1395 | -0.3654 | 1.47 | 1 |
| mths_since_recent_inq | > 16 | 22,130 | 8.24% | 11.01% | 0.2579 | -0.3654 | 2.72 | 3 |
| mths_since_recent_inq | Missing | 27,460 | 10.22% | 9.81% | 0.3860 | -0.3654 | 4.07 | 4 |
| mo_sin_old_rev_tl_op | <= 58 | 13,469 | 5.01% | 21.00% | -0.5073 | -0.2192 | -3.21 | -3 |
| mo_sin_old_rev_tl_op | (58, 84] | 17,872 | 6.65% | 17.26% | -0.2644 | -0.2192 | -1.67 | -2 |
| mo_sin_old_rev_tl_op | (84, 119] | 42,815 | 15.94% | 15.43% | -0.1309 | -0.2192 | -0.83 | -1 |
| mo_sin_old_rev_tl_op | (119, 203] | 106,606 | 39.68% | 13.51% | 0.0242 | -0.2192 | 0.15 | 0 |
| mo_sin_old_rev_tl_op | (203, 253] | 37,252 | 13.87% | 12.07% | 0.1534 | -0.2192 | 0.97 | 1 |
| mo_sin_old_rev_tl_op | > 253 | 50,633 | 18.85% | 11.15% | 0.2430 | -0.2192 | 1.54 | 2 |
| loan_to_inc | <= 0.06667 | 22,792 | 8.48% | 10.57% | 0.3039 | -0.7717 | 6.77 | 7 |
| loan_to_inc | (0.06667, 0.15] | 78,320 | 29.15% | 12.07% | 0.1540 | -0.7717 | 3.43 | 3 |
| loan_to_inc | (0.15, 0.1963] | 43,886 | 16.34% | 12.70% | 0.0961 | -0.7717 | 2.14 | 2 |
| loan_to_inc | (0.1963, 0.27] | 57,883 | 21.55% | 14.07% | -0.0225 | -0.7717 | -0.50 | -1 |
| loan_to_inc | (0.27, 0.3571] | 42,312 | 15.75% | 17.01% | -0.2472 | -0.7717 | -5.50 | -6 |
| loan_to_inc | > 0.3571 | 23,454 | 8.73% | 18.33% | -0.3378 | -0.7717 | -7.52 | -8 |
| percent_bc_gt_75 | <= 0 | 50,871 | 18.94% | 10.62% | 0.2978 | -0.2246 | 1.93 | 2 |
| percent_bc_gt_75 | (0, 25] | 33,385 | 12.43% | 11.73% | 0.1860 | -0.2246 | 1.21 | 1 |
| percent_bc_gt_75 | (25, 50] | 68,191 | 25.38% | 13.47% | 0.0279 | -0.2246 | 0.18 | 0 |
| percent_bc_gt_75 | (50, 66.7] | 32,195 | 11.98% | 14.97% | -0.0949 | -0.2246 | -0.62 | -1 |
| percent_bc_gt_75 | > 66.7 | 81,206 | 30.23% | 16.38% | -0.2015 | -0.2246 | -1.31 | -1 |
| percent_bc_gt_75 | Missing | 2,799 | 1.04% | 16.04% | -0.1769 | -0.2246 | -1.15 | -1 |
| mths_since_recent_bc | <= 2 | 22,697 | 8.45% | 17.55% | -0.2848 | -0.2996 | -2.46 | -2 |
| mths_since_recent_bc | (2, 7] | 57,991 | 21.59% | 15.34% | -0.1235 | -0.2996 | -1.07 | -1 |
| mths_since_recent_bc | (7, 16] | 69,601 | 25.91% | 14.58% | -0.0639 | -0.2996 | -0.55 | -1 |
| mths_since_recent_bc | (16, 31] | 53,821 | 20.03% | 13.09% | 0.0614 | -0.2996 | 0.53 | 1 |
| mths_since_recent_bc | (31, 49] | 25,532 | 9.50% | 11.80% | 0.1798 | -0.2996 | 1.55 | 2 |
| mths_since_recent_bc | > 49 | 36,540 | 13.60% | 9.86% | 0.3805 | -0.2996 | 3.29 | 3 |
| mths_since_recent_bc | Missing | 2,465 | 0.92% | 15.90% | -0.1665 | -0.2996 | -1.44 | -1 |

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
- **约束条件**：坏账率上限 10%（5.3 的主要结论）；目标通过率 70%（5.3 的第二行，swap set 也按这一档展示）

### [不含平台评级] 5.1 分数段表（test，等频 10 段，分数从高到低）

| 分段 | 分数区间 | 人数 | 占比 | bad 数 | bad rate | 累计通过率 | 累计 bad rate | 净现金/笔 |
|---|---|---|---|---|---|---|---|---|
| 1 | 597–646 | 11,411 | 9.91% | 439 | 3.85% | 9.91% | 3.85% | 1,426 |
| 2 | 587–596 | 11,469 | 9.96% | 782 | 6.82% | 19.87% | 5.34% | 1,376 |
| 3 | 581–586 | 10,301 | 8.95% | 883 | 8.57% | 28.82% | 6.34% | 1,322 |
| 4 | 575–580 | 12,715 | 11.04% | 1,306 | 10.27% | 39.86% | 7.43% | 1,258 |
| 5 | 571–574 | 9,509 | 8.26% | 1,120 | 11.78% | 48.12% | 8.18% | 1,174 |
| 6 | 566–570 | 12,419 | 10.79% | 1,682 | 13.54% | 58.91% | 9.16% | 1,140 |
| 7 | 561–565 | 12,137 | 10.54% | 1,896 | 15.62% | 69.45% | 10.14% | 1,022 |
| 8 | 556–560 | 10,936 | 9.50% | 1,857 | 16.98% | 78.95% | 10.96% | 913 |
| 9 | 549–555 | 11,851 | 10.29% | 2,480 | 20.93% | 89.24% | 12.11% | 797 |
| 10 | 515–548 | 12,387 | 10.76% | 3,444 | 27.80% | 100.00% | 13.80% | 459 |

_累计通过率 / 累计 bad rate = 以该段下边界为 cut-off 时的通过率与通过客群 bad rate。按分数分位数切段，整数分数有并列，各段人数近似相等。_

### [不含平台评级] 5.1 分数段表（OOT，等频 10 段，分数从高到低）

| 分段 | 分数区间 | 人数 | 占比 | bad 数 | bad rate | 累计通过率 | 累计 bad rate | 净现金/笔 |
|---|---|---|---|---|---|---|---|---|
| 1 | 599–647 | 15,476 | 9.54% | 556 | 3.59% | 9.54% | 3.59% | 1,220 |
| 2 | 589–598 | 15,423 | 9.51% | 980 | 6.35% | 19.05% | 4.97% | 1,176 |
| 3 | 582–588 | 15,711 | 9.68% | 1,408 | 8.96% | 28.73% | 6.32% | 1,036 |
| 4 | 576–581 | 17,113 | 10.55% | 1,801 | 10.52% | 39.28% | 7.45% | 988 |
| 5 | 571–575 | 15,949 | 9.83% | 1,980 | 12.41% | 49.11% | 8.44% | 897 |
| 6 | 566–570 | 17,028 | 10.50% | 2,493 | 14.64% | 59.60% | 9.53% | 822 |
| 7 | 561–565 | 16,641 | 10.26% | 2,769 | 16.64% | 69.86% | 10.58% | 737 |
| 8 | 556–560 | 14,925 | 9.20% | 2,811 | 18.83% | 79.06% | 11.54% | 620 |
| 9 | 549–555 | 16,496 | 10.17% | 3,832 | 23.23% | 89.23% | 12.87% | 397 |
| 10 | 513–548 | 17,474 | 10.77% | 5,233 | 29.95% | 100.00% | 14.71% | 92 |

![[不含平台评级] 图 5.1 通过率–坏账率曲线（点 = 候选 cut-off）](figures/08_approval_curve_no_platform_rating.png)

_[不含平台评级] 图 5.1 通过率–坏账率曲线（点 = 候选 cut-off）_

### [不含平台评级] 5.2 候选 cut-off（test；样本 bad rate 13.80%）

| 目标通过率 | cut-off | 实际通过率 | 通过人数 | 通过客群 bad rate | 拒绝客群 bad rate | 边际新增人数 | 边际 bad rate | 总净现金 | 净现金/笔 | 边际净现金/笔 |
|---|---|---|---|---|---|---|---|---|---|---|
| 50.00% | 570 | 50.23% | 57,834 | 8.32% | 19.33% | 57,834 | 8.32% | 75,686,922 | 1,309 | 1,309 |
| 60.00% | 566 | 58.91% | 67,824 | 9.16% | 20.45% | 9,990 | 14.00% | 86,974,421 | 1,282 | 1,130 |
| 70.00% | 561 | 69.45% | 79,961 | 10.14% | 22.12% | 12,137 | 15.62% | 99,381,268 | 1,243 | 1,022 |
| 80.00% | 555 | 80.69% | 92,906 | 11.14% | 24.91% | 12,945 | 17.33% | 111,163,709 | 1,197 | 910 |
| 90.00% | 548 | 90.38% | 104,054 | 12.25% | 28.37% | 11,148 | 21.47% | 119,860,043 | 1,152 | 780 |

_边际 = 比上一档宽松的 cut-off 多放进来的那一批客户；边际 bad rate 和边际净现金/笔决定了再放松一档是否划算。_

### [不含平台评级] 5.2 候选 cut-off（OOT；样本 bad rate 14.71%）

| 目标通过率 | cut-off | 实际通过率 | 通过人数 | 通过客群 bad rate | 拒绝客群 bad rate | 边际新增人数 | 边际 bad rate | 总净现金 | 净现金/笔 | 边际净现金/笔 |
|---|---|---|---|---|---|---|---|---|---|---|
| 50.00% | 571 | 49.11% | 79,672 | 8.44% | 20.76% | 79,672 | 8.44% | 84,512,773 | 1,061 | 1,061 |
| 60.00% | 566 | 59.60% | 96,700 | 9.53% | 22.35% | 17,028 | 14.64% | 98,510,427 | 1,019 | 822 |
| 70.00% | 561 | 69.86% | 113,341 | 10.58% | 24.29% | 16,641 | 16.64% | 110,781,012 | 977 | 737 |
| 80.00% | 555 | 80.74% | 130,984 | 11.75% | 27.11% | 17,643 | 19.29% | 121,287,824 | 926 | 596 |
| 90.00% | 548 | 90.34% | 146,561 | 13.03% | 30.42% | 15,577 | 23.78% | 126,975,185 | 866 | 365 |

### [不含平台评级] 5.3 约束下的最优 cut-off（主要结论）

| 样本 | 准则 | cut-off | 实际通过率 | 通过人数 | 通过客群 bad rate | 总净现金 | 净现金/笔 |
|---|---|---|---|---|---|---|---|
| test | 坏账率上限 10% 下通过率最高 | 562 | 67.44% | 77,648 | 9.97% | 96,925,344 | 1,248 |
| test | 目标通过率 70% 下的坏账率与净现金 | 561 | 69.45% | 79,961 | 10.14% | 99,381,268 | 1,243 |
| OOT | 坏账率上限 10% 下通过率最高 | 564 | 63.78% | 103,475 | 9.93% | 103,682,526 | 1,002 |
| OOT | 目标通过率 70% 下的坏账率与净现金 | 561 | 69.86% | 113,341 | 10.58% | 110,781,012 | 977 |

_第一行：通过客群 bad rate ≤ 10% 的前提下通过率最高的 cut-off（空白 = 没有任何 cut-off 能满足）；第二行：通过率 70% 时的坏账率与净现金。_

OOT 上无约束的总净现金在通过率 96.7%（cut-off 540，接近全部通过）处最大：各分数段的每笔净现金接近持平，说明平台已对风险定价（risk-based pricing），低分客户的高利率覆盖了更高的损失。因此评分卡在这里的价值不是靠拒绝提高利润，而是风险约束下的准入（坏账率上限）与分层定价；本报告以 5.3 的约束下 cut-off 为主要结论，下面的利润曲线只作参照。

![[不含平台评级] 图 5.2 利润曲线（左：总净现金；右：每笔净现金）](figures/09_profit_curve_no_platform_rating.png)

_[不含平台评级] 图 5.2 利润曲线（左：总净现金；右：每笔净现金）_

### [不含平台评级] 5.4 利润最大化 cut-off（无约束参照：总净现金 vs 每笔净现金）

| 样本 | 准则 | cut-off | 实际通过率 | 通过人数 | 通过客群 bad rate | 总净现金 | 净现金/笔 |
|---|---|---|---|---|---|---|---|
| test | 总净现金最大 | 529 | 99.67% | 114,751 | 13.72% | 124,527,392 | 1,085 |
| test | 每笔净现金最大 | 594 | 12.43% | 14,316 | 4.30% | 20,568,759 | 1,437 |
| test | 全部通过（参照） | 515 | 100.00% | 115,135 | 13.80% | 124,498,955 | 1,081 |
| OOT | 总净现金最大 | 540 | 96.70% | 156,887 | 13.99% | 129,233,043 | 824 |
| OOT | 每笔净现金最大 | 598 | 10.24% | 16,620 | 3.75% | 20,138,009 | 1,212 |
| OOT | 全部通过（参照） | 513 | 100.00% | 162,236 | 14.71% | 128,191,612 | 790 |

_净现金来自实际回款（见 5.0 口径）。每笔净现金最大的 cut-off 只在通过率 ≥ 10% 的范围内搜索，避免只剩几十个高分客户时的噪声。总净现金最大的 cut-off 通常比坏账率最低的 cut-off 宽松得多：多放进来的一档客户只要利息收入高于损失，总额就继续上升（风险定价越充分，越接近全部通过）。_

### [不含平台评级] 5.5 swap set（test；cut-off 561，通过率 69.4%，目标 70%）

| 模型 \ 基准 | 基准批 | 基准拒 | 合计 |
|---|---|---|---|
| 模型批（score ≥ cut-off） | 63,503 笔 · bad rate 8.45% · 净现金/笔 1,231 | 16,458 笔 · bad rate 16.67% · 净现金/笔 1,290  ← swap-in | 79,961 笔 · bad rate 10.14% · 净现金/笔 1,243 |
| 模型拒 | 16,458 笔 · bad rate 17.58% · 净现金/笔 790  ← swap-out | 18,716 笔 · bad rate 26.11% · 净现金/笔 647 | 35,174 笔 · bad rate 22.12% · 净现金/笔 714 |
| 合计 | 79,961 笔 · bad rate 10.33% · 净现金/笔 1,140 | 35,174 笔 · bad rate 21.70% · 净现金/笔 948 | 115,135 笔 · bad rate 13.80% · 净现金/笔 1,081 |

_swap-in（模型批、基准拒）16,458 笔，bad rate 16.67%；swap-out（模型拒、基准批）16,458 笔，bad rate 17.58%。两格人数相同，模型换进了更好的客户；同通过率下模型通过客群 bad rate 10.14%，基准（平台评级） 10.33%（-0.19 pp）。 通过客群净现金：模型 99,381,268，基准 91,154,070。_

### [不含平台评级] 5.5 swap set（OOT；cut-off 561，通过率 69.9%，目标 70%）

| 模型 \ 基准 | 基准批 | 基准拒 | 合计 |
|---|---|---|---|
| 模型批（score ≥ cut-off） | 90,922 笔 · bad rate 8.62% · 净现金/笔 995 | 22,419 笔 · bad rate 18.53% · 净现金/笔 906  ← swap-in | 113,341 笔 · bad rate 10.58% · 净现金/笔 977 |
| 模型拒 | 22,419 笔 · bad rate 19.25% · 净现金/笔 496  ← swap-out | 26,476 笔 · bad rate 28.55% · 净现金/笔 237 | 48,895 笔 · bad rate 24.29% · 净现金/笔 356 |
| 合计 | 113,341 笔 · bad rate 10.72% · 净现金/笔 896 | 48,895 笔 · bad rate 23.96% · 净现金/笔 544 | 162,236 笔 · bad rate 14.71% · 净现金/笔 790 |

_swap-in（模型批、基准拒）22,419 笔，bad rate 18.53%；swap-out（模型拒、基准批）22,419 笔，bad rate 19.25%。两格人数相同，模型换进了更好的客户；同通过率下模型通过客群 bad rate 10.58%，基准（平台评级） 10.72%（-0.14 pp）。 通过客群净现金：模型 110,781,012，基准 101,599,139。_

### [不含平台评级] 各候选通过率下的 swap set 汇总

| 样本 | 目标通过率 | cut-off | 实际通过率 | 模型通过客群 bad rate | 基准通过客群 bad rate | swap-in 人数 | swap-in bad rate | swap-out 人数 | swap-out bad rate | 模型通过客群净现金 | 基准通过客群净现金 |
|---|---|---|---|---|---|---|---|---|---|---|---|
| test | 50.00% | 570 | 50.23% | 8.32% | 8.46% | 17,418 | 12.50% | 17,418 | 12.95% | 75,686,922 | 65,628,891 |
| test | 60.00% | 566 | 58.91% | 9.16% | 9.16% | 17,155 | 14.61% | 17,155 | 14.61% | 86,974,421 | 77,102,504 |
| test | 70.00% | 561 | 69.45% | 10.14% | 10.33% | 16,458 | 16.67% | 16,458 | 17.58% | 99,381,268 | 91,154,070 |
| test | 80.00% | 555 | 80.69% | 11.14% | 11.36% | 12,820 | 19.66% | 12,820 | 21.26% | 111,163,709 | 104,964,763 |
| test | 90.00% | 548 | 90.38% | 12.25% | 12.52% | 8,070 | 22.84% | 8,070 | 26.29% | 119,860,043 | 115,377,140 |
| OOT | 50.00% | 571 | 49.11% | 8.44% | 8.43% | 24,476 | 13.50% | 24,476 | 13.47% | 84,512,773 | 75,422,259 |
| OOT | 60.00% | 566 | 59.60% | 9.53% | 9.17% | 23,169 | 16.83% | 23,169 | 15.31% | 98,510,427 | 89,697,275 |
| OOT | 70.00% | 561 | 69.86% | 10.58% | 10.72% | 22,419 | 18.53% | 22,419 | 19.25% | 110,781,012 | 101,599,139 |
| OOT | 80.00% | 555 | 80.74% | 11.75% | 11.93% | 17,959 | 21.70% | 17,959 | 23.04% | 121,287,824 | 114,270,126 |
| OOT | 90.00% | 548 | 90.34% | 13.03% | 13.12% | 10,970 | 26.02% | 10,970 | 27.18% | 126,975,185 | 123,279,220 |

### [含平台评级] 5.1 分数段表（test，等频 10 段，分数从高到低）

| 分段 | 分数区间 | 人数 | 占比 | bad 数 | bad rate | 累计通过率 | 累计 bad rate | 净现金/笔 |
|---|---|---|---|---|---|---|---|---|
| 1 | 603–645 | 11,177 | 9.71% | 329 | 2.94% | 9.71% | 2.94% | 1,167 |
| 2 | 591–602 | 11,597 | 10.07% | 689 | 5.94% | 19.78% | 4.47% | 1,262 |
| 3 | 583–590 | 11,660 | 10.13% | 970 | 8.32% | 29.91% | 5.77% | 1,207 |
| 4 | 577–582 | 10,587 | 9.20% | 1,024 | 9.67% | 39.10% | 6.69% | 1,241 |
| 5 | 571–576 | 11,384 | 9.89% | 1,284 | 11.28% | 48.99% | 7.62% | 1,257 |
| 6 | 565–570 | 11,988 | 10.41% | 1,593 | 13.29% | 59.40% | 8.61% | 1,173 |
| 7 | 559–564 | 12,115 | 10.52% | 1,839 | 15.18% | 69.92% | 9.60% | 1,173 |
| 8 | 554–558 | 9,733 | 8.45% | 1,760 | 18.08% | 78.38% | 10.51% | 1,022 |
| 9 | 546–553 | 13,118 | 11.39% | 2,919 | 22.25% | 89.77% | 12.00% | 870 |
| 10 | 518–545 | 11,776 | 10.23% | 3,482 | 29.57% | 100.00% | 13.80% | 482 |

_累计通过率 / 累计 bad rate = 以该段下边界为 cut-off 时的通过率与通过客群 bad rate。按分数分位数切段，整数分数有并列，各段人数近似相等。_

### [含平台评级] 5.1 分数段表（OOT，等频 10 段，分数从高到低）

| 分段 | 分数区间 | 人数 | 占比 | bad 数 | bad rate | 累计通过率 | 累计 bad rate | 净现金/笔 |
|---|---|---|---|---|---|---|---|---|
| 1 | 606–645 | 15,943 | 9.83% | 470 | 2.95% | 9.83% | 2.95% | 1,030 |
| 2 | 594–605 | 15,200 | 9.37% | 769 | 5.06% | 19.20% | 3.98% | 1,090 |
| 3 | 585–593 | 17,066 | 10.52% | 1,275 | 7.47% | 29.72% | 5.21% | 1,049 |
| 4 | 579–584 | 14,253 | 8.79% | 1,390 | 9.75% | 38.50% | 6.25% | 984 |
| 5 | 572–578 | 18,013 | 11.10% | 2,162 | 12.00% | 49.60% | 7.54% | 915 |
| 6 | 566–571 | 16,348 | 10.08% | 2,345 | 14.34% | 59.68% | 8.69% | 850 |
| 7 | 560–565 | 16,234 | 10.01% | 2,745 | 16.91% | 69.69% | 9.87% | 814 |
| 8 | 554–559 | 15,647 | 9.64% | 3,229 | 20.64% | 79.33% | 11.18% | 685 |
| 9 | 547–553 | 15,666 | 9.66% | 3,737 | 23.85% | 88.99% | 12.55% | 502 |
| 10 | 517–546 | 17,866 | 11.01% | 5,741 | 32.13% | 100.00% | 14.71% | 63 |

![[含平台评级] 图 5.1 通过率–坏账率曲线（点 = 候选 cut-off）](figures/08_approval_curve_with_platform_rating.png)

_[含平台评级] 图 5.1 通过率–坏账率曲线（点 = 候选 cut-off）_

### [含平台评级] 5.2 候选 cut-off（test；样本 bad rate 13.80%）

| 目标通过率 | cut-off | 实际通过率 | 通过人数 | 通过客群 bad rate | 拒绝客群 bad rate | 边际新增人数 | 边际 bad rate | 总净现金 | 净现金/笔 | 边际净现金/笔 |
|---|---|---|---|---|---|---|---|---|---|---|
| 50.00% | 570 | 50.69% | 58,365 | 7.75% | 20.02% | 58,365 | 7.75% | 71,671,312 | 1,228 | 1,228 |
| 60.00% | 565 | 59.40% | 68,393 | 8.61% | 21.39% | 10,028 | 13.64% | 83,259,339 | 1,217 | 1,156 |
| 70.00% | 559 | 69.92% | 80,508 | 9.60% | 23.57% | 12,115 | 15.18% | 97,467,596 | 1,211 | 1,173 |
| 80.00% | 553 | 80.03% | 92,138 | 10.73% | 26.11% | 11,630 | 18.54% | 109,217,781 | 1,185 | 1,010 |
| 90.00% | 546 | 89.77% | 103,359 | 12.00% | 29.57% | 11,221 | 22.48% | 118,828,691 | 1,150 | 857 |

_边际 = 比上一档宽松的 cut-off 多放进来的那一批客户；边际 bad rate 和边际净现金/笔决定了再放松一档是否划算。_

### [含平台评级] 5.2 候选 cut-off（OOT；样本 bad rate 14.71%）

| 目标通过率 | cut-off | 实际通过率 | 通过人数 | 通过客群 bad rate | 拒绝客群 bad rate | 边际新增人数 | 边际 bad rate | 总净现金 | 净现金/笔 | 边际净现金/笔 |
|---|---|---|---|---|---|---|---|---|---|---|
| 50.00% | 572 | 49.60% | 80,475 | 7.54% | 21.77% | 80,475 | 7.54% | 81,383,158 | 1,011 | 1,011 |
| 60.00% | 566 | 59.68% | 96,823 | 8.69% | 23.62% | 16,348 | 14.34% | 95,277,704 | 984 | 850 |
| 70.00% | 560 | 69.69% | 113,057 | 9.87% | 25.84% | 16,234 | 16.91% | 108,490,923 | 960 | 814 |
| 80.00% | 554 | 79.33% | 128,704 | 11.18% | 28.27% | 15,647 | 20.64% | 119,213,223 | 926 | 685 |
| 90.00% | 546 | 90.11% | 146,186 | 12.76% | 32.47% | 17,482 | 24.41% | 127,289,450 | 871 | 462 |

### [含平台评级] 5.3 约束下的最优 cut-off（主要结论）

| 样本 | 准则 | cut-off | 实际通过率 | 通过人数 | 通过客群 bad rate | 总净现金 | 净现金/笔 |
|---|---|---|---|---|---|---|---|
| test | 坏账率上限 10% 下通过率最高 | 557 | 73.38% | 84,482 | 9.94% | 101,706,334 | 1,204 |
| test | 目标通过率 70% 下的坏账率与净现金 | 559 | 69.92% | 80,508 | 9.60% | 97,467,596 | 1,211 |
| OOT | 坏账率上限 10% 下通过率最高 | 560 | 69.69% | 113,057 | 9.87% | 108,490,923 | 960 |
| OOT | 目标通过率 70% 下的坏账率与净现金 | 560 | 69.69% | 113,057 | 9.87% | 108,490,923 | 960 |

_第一行：通过客群 bad rate ≤ 10% 的前提下通过率最高的 cut-off（空白 = 没有任何 cut-off 能满足）；第二行：通过率 70% 时的坏账率与净现金。_

OOT 上无约束的总净现金在通过率 97.2%（cut-off 537，接近全部通过）处最大：各分数段的每笔净现金接近持平，说明平台已对风险定价（risk-based pricing），低分客户的高利率覆盖了更高的损失。因此评分卡在这里的价值不是靠拒绝提高利润，而是风险约束下的准入（坏账率上限）与分层定价；本报告以 5.3 的约束下 cut-off 为主要结论，下面的利润曲线只作参照。

![[含平台评级] 图 5.2 利润曲线（左：总净现金；右：每笔净现金）](figures/09_profit_curve_with_platform_rating.png)

_[含平台评级] 图 5.2 利润曲线（左：总净现金；右：每笔净现金）_

### [含平台评级] 5.4 利润最大化 cut-off（无约束参照：总净现金 vs 每笔净现金）

| 样本 | 准则 | cut-off | 实际通过率 | 通过人数 | 通过客群 bad rate | 总净现金 | 净现金/笔 |
|---|---|---|---|---|---|---|---|
| test | 总净现金最大 | 527 | 99.80% | 114,900 | 13.74% | 124,625,100 | 1,085 |
| test | 每笔净现金最大 | 570 | 50.69% | 58,365 | 7.75% | 71,671,312 | 1,228 |
| test | 全部通过（参照） | 518 | 100.00% | 115,135 | 13.80% | 124,498,955 | 1,081 |
| OOT | 总净现金最大 | 537 | 97.24% | 157,753 | 14.05% | 129,545,537 | 821 |
| OOT | 每笔净现金最大 | 588 | 25.83% | 41,899 | 4.68% | 44,790,888 | 1,069 |
| OOT | 全部通过（参照） | 517 | 100.00% | 162,236 | 14.71% | 128,191,612 | 790 |

_净现金来自实际回款（见 5.0 口径）。每笔净现金最大的 cut-off 只在通过率 ≥ 10% 的范围内搜索，避免只剩几十个高分客户时的噪声。总净现金最大的 cut-off 通常比坏账率最低的 cut-off 宽松得多：多放进来的一档客户只要利息收入高于损失，总额就继续上升（风险定价越充分，越接近全部通过）。_

### [含平台评级] 5.5 swap set（test；cut-off 559，通过率 69.9%，目标 70%）

| 模型 \ 基准 | 基准批 | 基准拒 | 合计 |
|---|---|---|---|
| 模型批（score ≥ cut-off） | 69,322 笔 · bad rate 8.77% · 净现金/笔 1,187 | 11,186 笔 · bad rate 14.75% · 净现金/笔 1,359  ← swap-in | 80,508 笔 · bad rate 9.60% · 净现金/笔 1,211 |
| 模型拒 | 11,186 笔 · bad rate 20.39% · 净现金/笔 840  ← swap-out | 23,441 笔 · bad rate 25.08% · 净现金/笔 753 | 34,627 笔 · bad rate 23.57% · 净现金/笔 781 |
| 合计 | 80,508 笔 · bad rate 10.38% · 净现金/笔 1,138 | 34,627 笔 · bad rate 21.75% · 净现金/笔 949 | 115,135 笔 · bad rate 13.80% · 净现金/笔 1,081 |

_swap-in（模型批、基准拒）11,186 笔，bad rate 14.75%；swap-out（模型拒、基准批）11,186 笔，bad rate 20.39%。两格人数相同，模型换进了更好的客户；同通过率下模型通过客群 bad rate 9.60%，基准（平台评级） 10.38%（-0.78 pp）。 通过客群净现金：模型 97,467,596，基准 91,653,254。_

### [含平台评级] 5.5 swap set（OOT；cut-off 560，通过率 69.7%，目标 70%）

| 模型 \ 基准 | 基准批 | 基准拒 | 合计 |
|---|---|---|---|
| 模型批（score ≥ cut-off） | 98,100 笔 · bad rate 8.96% · 净现金/笔 957 | 14,957 笔 · bad rate 15.83% · 净现金/笔 980  ← swap-in | 113,057 笔 · bad rate 9.87% · 净现金/笔 960 |
| 模型拒 | 14,957 笔 · bad rate 22.06% · 净现金/笔 516  ← swap-out | 34,222 笔 · bad rate 27.49% · 净现金/笔 350 | 49,179 笔 · bad rate 25.84% · 净现金/笔 401 |
| 合计 | 113,057 笔 · bad rate 10.69% · 净现金/笔 898 | 49,179 笔 · bad rate 23.95% · 净现金/笔 542 | 162,236 笔 · bad rate 14.71% · 净现金/笔 790 |

_swap-in（模型批、基准拒）14,957 笔，bad rate 15.83%；swap-out（模型拒、基准批）14,957 笔，bad rate 22.06%。两格人数相同，模型换进了更好的客户；同通过率下模型通过客群 bad rate 9.87%，基准（平台评级） 10.69%（-0.82 pp）。 通过客群净现金：模型 108,490,923，基准 101,556,498。_

### [含平台评级] 各候选通过率下的 swap set 汇总

| 样本 | 目标通过率 | cut-off | 实际通过率 | 模型通过客群 bad rate | 基准通过客群 bad rate | swap-in 人数 | swap-in bad rate | swap-out 人数 | swap-out bad rate | 模型通过客群净现金 | 基准通过客群净现金 |
|---|---|---|---|---|---|---|---|---|---|---|---|
| test | 50.00% | 570 | 50.69% | 7.75% | 8.46% | 10,268 | 10.43% | 10,268 | 14.50% | 71,671,312 | 66,284,769 |
| test | 60.00% | 565 | 59.40% | 8.61% | 9.20% | 10,082 | 12.96% | 10,082 | 16.94% | 83,259,339 | 77,837,287 |
| test | 70.00% | 559 | 69.92% | 9.60% | 10.38% | 11,186 | 14.75% | 11,186 | 20.39% | 97,467,596 | 91,653,254 |
| test | 80.00% | 553 | 80.03% | 10.73% | 11.30% | 9,427 | 17.46% | 9,427 | 23.04% | 109,217,781 | 104,091,470 |
| test | 90.00% | 546 | 89.77% | 12.00% | 12.43% | 7,288 | 21.61% | 7,288 | 27.66% | 118,828,691 | 114,960,495 |
| OOT | 50.00% | 572 | 49.60% | 7.54% | 8.48% | 15,662 | 10.81% | 15,662 | 15.67% | 81,383,158 | 76,008,928 |
| OOT | 60.00% | 566 | 59.68% | 8.69% | 9.19% | 12,643 | 14.02% | 12,643 | 17.87% | 95,277,704 | 89,719,501 |
| OOT | 70.00% | 560 | 69.69% | 9.87% | 10.69% | 14,957 | 15.83% | 14,957 | 22.06% | 108,490,923 | 101,556,498 |
| OOT | 80.00% | 554 | 79.33% | 11.18% | 11.80% | 13,537 | 18.97% | 13,537 | 24.92% | 119,213,223 | 112,700,550 |
| OOT | 90.00% | 546 | 90.11% | 12.76% | 13.08% | 9,037 | 24.83% | 9,037 | 30.04% | 127,289,450 | 123,145,264 |

### 5.6 两套模型对比：同通过率下的通过客群 bad rate（不含平台评级 vs 含平台评级）

| 样本 | 目标通过率 | cut-off（不含平台评级） | bad rate（不含平台评级） | cut-off（含平台评级） | bad rate（含平台评级） | 差（pp） |
|---|---|---|---|---|---|---|
| test | 50.00% | 570 | 8.32% | 570 | 7.75% | -0.58 |
| test | 60.00% | 566 | 9.16% | 565 | 8.61% | -0.55 |
| test | 70.00% | 561 | 10.14% | 559 | 9.60% | -0.54 |
| test | 80.00% | 555 | 11.14% | 553 | 10.73% | -0.42 |
| test | 90.00% | 548 | 12.25% | 546 | 12.00% | -0.24 |
| OOT | 50.00% | 571 | 8.44% | 572 | 7.54% | -0.90 |
| OOT | 60.00% | 566 | 9.53% | 566 | 8.69% | -0.85 |
| OOT | 70.00% | 561 | 10.58% | 560 | 9.87% | -0.71 |
| OOT | 80.00% | 555 | 11.75% | 554 | 11.18% | -0.57 |
| OOT | 90.00% | 548 | 13.03% | 546 | 12.76% | -0.27 |

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
| train → test | 268,647 | 115,135 | 0.0002 | 🟢 稳定 |
| train → OOT | 268,647 | 162,236 | 0.0020 | 🟢 稳定 |

![[不含平台评级] 图 6.1 分数分布按 train 等频段（train vs test vs OOT）](figures/10_score_psi_no_platform_rating.png)

_[不含平台评级] 图 6.1 分数分布按 train 等频段（train vs test vs OOT）_

### [不含平台评级] score PSI 分段明细

| 段 | 分数区间 | train 占比 | test 占比 | OOT 占比 | PSI 贡献（test） | PSI 贡献（OOT） |
|---|---|---|---|---|---|---|
| 1 | <= 548 | 10.92% | 10.76% | 10.77% | 0.0000 | 0.0000 |
| 2 | (548, 555] | 10.44% | 10.29% | 10.17% | 0.0000 | 0.0001 |
| 3 | (555, 560] | 9.60% | 9.50% | 9.20% | 0.0000 | 0.0002 |
| 4 | (560, 565] | 10.64% | 10.54% | 10.26% | 0.0000 | 0.0001 |
| 5 | (565, 569] | 8.64% | 8.68% | 8.45% | 0.0000 | 0.0000 |
| 6 | (569, 574] | 10.08% | 10.37% | 9.94% | 0.0001 | 0.0000 |
| 7 | (574, 580] | 10.92% | 11.04% | 10.78% | 0.0000 | 0.0000 |
| 8 | (580, 586] | 8.84% | 8.95% | 8.88% | 0.0000 | 0.0000 |
| 9 | (586, 596] | 10.07% | 9.96% | 10.54% | 0.0000 | 0.0002 |
| 10 | > 596 | 9.85% | 9.91% | 11.00% | 0.0000 | 0.0013 |

### [不含平台评级] 6.2 入模特征 CSI（判定按 train → OOT）

| 特征 | CSI train→test | CSI train→OOT | 判定 | 偏移最大的箱 | train 占比 | OOT 占比 |
|---|---|---|---|---|---|---|
| percent_bc_gt_75 | 0.0000 | 0.0250 | 🟢 稳定 | <= 0 | 18.94% | 24.75% |
| mo_sin_old_rev_tl_op | 0.0000 | 0.0144 | 🟢 稳定 | (58, 84] | 6.65% | 4.75% |
| bc_open_to_buy | 0.0000 | 0.0142 | 🟢 稳定 | (800, 2,750] | 22.75% | 20.15% |
| total_rev_hi_lim | 0.0000 | 0.0108 | 🟢 稳定 | (6,700, 18,200] | 34.24% | 30.98% |
| acc_open_past_24mths | 0.0001 | 0.0090 | 🟢 稳定 | > 8 | 8.17% | 10.66% |
| dti | 0.0001 | 0.0072 | 🟢 稳定 | > 23.02 | 26.38% | 30.13% |
| loan_to_inc | 0.0001 | 0.0054 | 🟢 稳定 | (0.27, 0.3571] | 15.75% | 14.07% |
| tot_hi_cred_lim | 0.0000 | 0.0053 | 🟢 稳定 | <= 39,077 | 22.51% | 20.03% |
| mort_acc | 0.0000 | 0.0044 | 🟢 稳定 | > 3 | 17.67% | 15.40% |
| fico_mid | 0.0002 | 0.0040 | 🟢 稳定 | > 742 | 7.13% | 8.50% |
| mo_sin_rcnt_tl | 0.0000 | 0.0037 | 🟢 稳定 | (1, 3] | 20.74% | 22.58% |
| mths_since_recent_inq | 0.0001 | 0.0036 | 🟢 稳定 | (7, 10] | 12.02% | 10.82% |
| log_annual_inc | 0.0000 | 0.0035 | 🟢 稳定 | > 11.61 | 12.69% | 14.49% |
| home_ownership | 0.0000 | 0.0023 | 🟢 稳定 | {OWN} | 9.98% | 11.48% |
| mths_since_recent_bc | 0.0001 | 0.0011 | 🟢 稳定 | (7, 16] | 25.91% | 26.67% |

_CSI 高说明该特征的客群分布变了，不一定意味着模型失效：先看 score PSI 是否稳定，再看该特征的分箱是否仍合理、含义是否变化（例如某个征信字段从某年开始才有值）。_

![[不含平台评级] 图 6.2 入模特征 CSI（虚线 = 0.10 / 0.25）](figures/11_csi_no_platform_rating.png)

_[不含平台评级] 图 6.2 入模特征 CSI（虚线 = 0.10 / 0.25）_

### [不含平台评级] CSI 分箱明细（train → OOT）

| 特征 | 分箱 | train 占比 | 对比样本占比 | PSI 贡献 |
|---|---|---|---|---|
| fico_mid | <= 672 | 28.81% | 28.63% | 0.0000 |
| fico_mid | (672, 687] | 23.58% | 22.36% | 0.0006 |
| fico_mid | (687, 697] | 12.82% | 12.02% | 0.0005 |
| fico_mid | (697, 717] | 17.63% | 17.83% | 0.0000 |
| fico_mid | (717, 742] | 10.04% | 10.65% | 0.0004 |
| fico_mid | > 742 | 7.13% | 8.50% | 0.0024 |
| bc_open_to_buy | <= 800 | 19.89% | 17.35% | 0.0035 |
| bc_open_to_buy | (800, 2,750] | 22.75% | 20.15% | 0.0031 |
| bc_open_to_buy | (2,750, 4,993] | 14.76% | 14.54% | 0.0000 |
| bc_open_to_buy | (4,993, 9,403] | 15.32% | 16.47% | 0.0008 |
| bc_open_to_buy | (9,403, 21,001] | 15.35% | 17.24% | 0.0022 |
| bc_open_to_buy | > 21,001 | 10.93% | 13.25% | 0.0045 |
| bc_open_to_buy | Missing | 1.00% | 0.98% | 0.0000 |
| tot_hi_cred_lim | <= 39,077 | 22.51% | 20.03% | 0.0029 |
| tot_hi_cred_lim | (39,077, 67,226] | 18.48% | 18.36% | 0.0000 |
| tot_hi_cred_lim | (67,226, 177,490] | 25.96% | 27.55% | 0.0009 |
| tot_hi_cred_lim | (177,490, 254,061] | 12.01% | 11.61% | 0.0001 |
| tot_hi_cred_lim | (254,061, 381,767] | 12.04% | 12.37% | 0.0001 |
| tot_hi_cred_lim | > 381,767 | 8.99% | 10.08% | 0.0013 |
| log_annual_inc | <= 10.52 | 16.67% | 16.07% | 0.0002 |
| log_annual_inc | (10.52, 10.71] | 12.38% | 11.51% | 0.0006 |
| log_annual_inc | (10.71, 11.08] | 27.16% | 26.44% | 0.0002 |
| log_annual_inc | (11.08, 11.29] | 14.60% | 14.71% | 0.0000 |
| log_annual_inc | (11.29, 11.61] | 16.50% | 16.79% | 0.0001 |
| log_annual_inc | > 11.61 | 12.69% | 14.49% | 0.0024 |
| acc_open_past_24mths | <= 1 | 14.93% | 14.28% | 0.0003 |
| acc_open_past_24mths | (1, 2] | 14.18% | 13.45% | 0.0004 |
| acc_open_past_24mths | (2, 3] | 15.63% | 14.56% | 0.0007 |
| acc_open_past_24mths | (3, 5] | 26.76% | 25.65% | 0.0005 |
| acc_open_past_24mths | (5, 8] | 20.33% | 21.39% | 0.0005 |
| acc_open_past_24mths | > 8 | 8.17% | 10.66% | 0.0066 |
| total_rev_hi_lim | <= 6,700 | 7.73% | 7.39% | 0.0002 |
| total_rev_hi_lim | (6,700, 18,200] | 34.24% | 30.98% | 0.0033 |
| total_rev_hi_lim | (18,200, 31,000] | 26.01% | 25.63% | 0.0001 |
| total_rev_hi_lim | (31,000, 38,400] | 9.01% | 9.31% | 0.0001 |
| total_rev_hi_lim | (38,400, 53,700] | 11.00% | 11.64% | 0.0004 |
| total_rev_hi_lim | > 53,700 | 12.01% | 15.06% | 0.0069 |
| dti | <= 12.7 | 30.09% | 28.04% | 0.0014 |
| dti | (12.7, 19] | 28.00% | 26.64% | 0.0007 |
| dti | (19, 23.02] | 15.52% | 15.18% | 0.0001 |
| dti | > 23.02 | 26.38% | 30.13% | 0.0050 |
| dti | Missing | 0.00% | 0.00% | 0.0000 |
| mort_acc | <= 0 | 43.04% | 43.09% | 0.0000 |
| mort_acc | (0, 1] | 16.14% | 16.88% | 0.0003 |
| mort_acc | (1, 2] | 13.13% | 14.16% | 0.0008 |
| mort_acc | (2, 3] | 10.02% | 10.48% | 0.0002 |
| mort_acc | > 3 | 17.67% | 15.40% | 0.0031 |
| home_ownership | {OTHER_RARE, MORTGAGE} | 47.12% | 46.54% | 0.0001 |
| home_ownership | {OWN} | 9.98% | 11.48% | 0.0021 |
| home_ownership | {RENT} | 42.89% | 41.99% | 0.0002 |
| mo_sin_rcnt_tl | <= 1 | 9.94% | 10.65% | 0.0005 |
| mo_sin_rcnt_tl | (1, 3] | 20.74% | 22.58% | 0.0016 |
| mo_sin_rcnt_tl | (3, 6] | 24.58% | 23.86% | 0.0002 |
| mo_sin_rcnt_tl | (6, 9] | 16.81% | 15.32% | 0.0014 |
| mo_sin_rcnt_tl | (9, 13] | 12.32% | 12.28% | 0.0000 |
| mo_sin_rcnt_tl | > 13 | 15.62% | 15.30% | 0.0001 |
| mths_since_recent_inq | <= 1 | 17.51% | 18.35% | 0.0004 |
| mths_since_recent_inq | (1, 3] | 14.97% | 15.70% | 0.0003 |
| mths_since_recent_inq | (3, 7] | 23.01% | 22.25% | 0.0003 |
| mths_since_recent_inq | (7, 10] | 12.02% | 10.82% | 0.0013 |
| mths_since_recent_inq | (10, 16] | 14.03% | 13.62% | 0.0001 |
| mths_since_recent_inq | > 16 | 8.24% | 7.94% | 0.0001 |
| mths_since_recent_inq | Missing | 10.22% | 11.33% | 0.0011 |
| mo_sin_old_rev_tl_op | <= 58 | 5.01% | 6.75% | 0.0051 |
| mo_sin_old_rev_tl_op | (58, 84] | 6.65% | 4.75% | 0.0064 |
| mo_sin_old_rev_tl_op | (84, 119] | 15.94% | 14.70% | 0.0010 |
| mo_sin_old_rev_tl_op | (119, 203] | 39.68% | 39.11% | 0.0001 |
| mo_sin_old_rev_tl_op | (203, 253] | 13.87% | 14.01% | 0.0000 |
| mo_sin_old_rev_tl_op | > 253 | 18.85% | 20.69% | 0.0017 |
| loan_to_inc | <= 0.06667 | 8.48% | 9.91% | 0.0022 |
| loan_to_inc | (0.06667, 0.15] | 29.15% | 30.34% | 0.0005 |
| loan_to_inc | (0.15, 0.1963] | 16.34% | 15.96% | 0.0001 |
| loan_to_inc | (0.1963, 0.27] | 21.55% | 20.54% | 0.0005 |
| loan_to_inc | (0.27, 0.3571] | 15.75% | 14.07% | 0.0019 |
| loan_to_inc | > 0.3571 | 8.73% | 9.19% | 0.0002 |
| loan_to_inc | Missing | 0.00% | 0.00% | 0.0000 |
| percent_bc_gt_75 | <= 0 | 18.94% | 24.75% | 0.0155 |
| percent_bc_gt_75 | (0, 25] | 12.43% | 13.46% | 0.0008 |
| percent_bc_gt_75 | (25, 50] | 25.38% | 23.72% | 0.0011 |
| percent_bc_gt_75 | (50, 66.7] | 11.98% | 9.92% | 0.0039 |
| percent_bc_gt_75 | > 66.7 | 30.23% | 27.05% | 0.0035 |
| percent_bc_gt_75 | Missing | 1.04% | 1.10% | 0.0000 |
| mths_since_recent_bc | <= 2 | 8.45% | 8.63% | 0.0000 |
| mths_since_recent_bc | (2, 7] | 21.59% | 21.67% | 0.0000 |
| mths_since_recent_bc | (7, 16] | 25.91% | 26.67% | 0.0002 |
| mths_since_recent_bc | (16, 31] | 20.03% | 19.30% | 0.0003 |
| mths_since_recent_bc | (31, 49] | 9.50% | 9.88% | 0.0001 |
| mths_since_recent_bc | > 49 | 13.60% | 12.89% | 0.0004 |
| mths_since_recent_bc | Missing | 0.92% | 0.96% | 0.0000 |

### [含平台评级] 6.1 score PSI

| 对比 | train 行数 | 对比样本行数 | PSI | 判定 |
|---|---|---|---|---|
| train → test | 268,647 | 115,135 | 0.0001 | 🟢 稳定 |
| train → OOT | 268,647 | 162,236 | 0.0061 | 🟢 稳定 |

![[含平台评级] 图 6.1 分数分布按 train 等频段（train vs test vs OOT）](figures/10_score_psi_with_platform_rating.png)

_[含平台评级] 图 6.1 分数分布按 train 等频段（train vs test vs OOT）_

### [含平台评级] score PSI 分段明细

| 段 | 分数区间 | train 占比 | test 占比 | OOT 占比 | PSI 贡献（test） | PSI 贡献（OOT） |
|---|---|---|---|---|---|---|
| 1 | <= 545 | 10.40% | 10.23% | 9.89% | 0.0000 | 0.0002 |
| 2 | (545, 552] | 9.83% | 9.75% | 9.28% | 0.0000 | 0.0003 |
| 3 | (552, 558] | 10.14% | 10.10% | 9.45% | 0.0000 | 0.0005 |
| 4 | (558, 564] | 10.66% | 10.52% | 10.03% | 0.0000 | 0.0004 |
| 5 | (564, 570] | 10.46% | 10.41% | 10.07% | 0.0000 | 0.0002 |
| 6 | (570, 576] | 9.87% | 9.89% | 9.73% | 0.0000 | 0.0000 |
| 7 | (576, 582] | 8.99% | 9.20% | 9.05% | 0.0000 | 0.0000 |
| 8 | (582, 590] | 9.96% | 10.13% | 10.16% | 0.0000 | 0.0000 |
| 9 | (590, 602] | 9.97% | 10.07% | 10.49% | 0.0000 | 0.0003 |
| 10 | > 602 | 9.71% | 9.71% | 11.84% | 0.0000 | 0.0042 |

### [含平台评级] 6.2 入模特征 CSI（判定按 train → OOT）

| 特征 | CSI train→test | CSI train→OOT | 判定 | 偏移最大的箱 | train 占比 | OOT 占比 |
|---|---|---|---|---|---|---|
| percent_bc_gt_75 | 0.0000 | 0.0250 | 🟢 稳定 | <= 0 | 18.94% | 24.75% |
| mo_sin_old_rev_tl_op | 0.0000 | 0.0144 | 🟢 稳定 | (58, 84] | 6.65% | 4.75% |
| sub_grade | 0.0001 | 0.0142 | 🟢 稳定 | {C4, C5, D1, D3, D2, D4, D5, E2, E1, F2, E3, E4, G2, F1, E5, G4, G1, F3, G3, F4, F5, G5} | 26.87% | 22.96% |
| bc_open_to_buy | 0.0000 | 0.0142 | 🟢 稳定 | (800, 2,750] | 22.75% | 20.15% |
| total_rev_hi_lim | 0.0000 | 0.0108 | 🟢 稳定 | (6,700, 18,200] | 34.24% | 30.98% |
| acc_open_past_24mths | 0.0001 | 0.0090 | 🟢 稳定 | > 8 | 8.17% | 10.66% |
| dti | 0.0001 | 0.0072 | 🟢 稳定 | > 23.02 | 26.38% | 30.13% |
| loan_to_inc | 0.0001 | 0.0054 | 🟢 稳定 | (0.27, 0.3571] | 15.75% | 14.07% |
| tot_hi_cred_lim | 0.0000 | 0.0053 | 🟢 稳定 | <= 39,077 | 22.51% | 20.03% |
| mort_acc | 0.0000 | 0.0044 | 🟢 稳定 | > 3 | 17.67% | 15.40% |
| fico_mid | 0.0002 | 0.0040 | 🟢 稳定 | > 742 | 7.13% | 8.50% |
| mo_sin_rcnt_tl | 0.0000 | 0.0037 | 🟢 稳定 | (1, 3] | 20.74% | 22.58% |
| mths_since_recent_inq | 0.0001 | 0.0036 | 🟢 稳定 | (7, 10] | 12.02% | 10.82% |
| annual_inc | 0.0000 | 0.0035 | 🟢 稳定 | > 110,000 | 12.69% | 14.49% |
| home_ownership | 0.0000 | 0.0023 | 🟢 稳定 | {OWN} | 9.98% | 11.48% |
| mths_since_recent_bc | 0.0001 | 0.0011 | 🟢 稳定 | (7, 16] | 25.91% | 26.67% |

_CSI 高说明该特征的客群分布变了，不一定意味着模型失效：先看 score PSI 是否稳定，再看该特征的分箱是否仍合理、含义是否变化（例如某个征信字段从某年开始才有值）。_

![[含平台评级] 图 6.2 入模特征 CSI（虚线 = 0.10 / 0.25）](figures/11_csi_with_platform_rating.png)

_[含平台评级] 图 6.2 入模特征 CSI（虚线 = 0.10 / 0.25）_

### [含平台评级] CSI 分箱明细（train → OOT）

| 特征 | 分箱 | train 占比 | 对比样本占比 | PSI 贡献 |
|---|---|---|---|---|
| sub_grade | {A1, A2, A3} | 10.00% | 12.88% | 0.0073 |
| sub_grade | {A4, A5, B1} | 17.60% | 18.49% | 0.0004 |
| sub_grade | {B2, B3, B4} | 21.25% | 20.68% | 0.0002 |
| sub_grade | {B5, C1, C2, C3} | 24.28% | 24.99% | 0.0002 |
| sub_grade | {C4, C5, D1, D3, D2, D4, D5, E2, E1, F2, E3, E4, G2, F1, E5, G4, G1, F3, G3, F4, F5, G5} | 26.87% | 22.96% | 0.0061 |
| fico_mid | <= 672 | 28.81% | 28.63% | 0.0000 |
| fico_mid | (672, 687] | 23.58% | 22.36% | 0.0006 |
| fico_mid | (687, 697] | 12.82% | 12.02% | 0.0005 |
| fico_mid | (697, 717] | 17.63% | 17.83% | 0.0000 |
| fico_mid | (717, 742] | 10.04% | 10.65% | 0.0004 |
| fico_mid | > 742 | 7.13% | 8.50% | 0.0024 |
| bc_open_to_buy | <= 800 | 19.89% | 17.35% | 0.0035 |
| bc_open_to_buy | (800, 2,750] | 22.75% | 20.15% | 0.0031 |
| bc_open_to_buy | (2,750, 4,993] | 14.76% | 14.54% | 0.0000 |
| bc_open_to_buy | (4,993, 9,403] | 15.32% | 16.47% | 0.0008 |
| bc_open_to_buy | (9,403, 21,001] | 15.35% | 17.24% | 0.0022 |
| bc_open_to_buy | > 21,001 | 10.93% | 13.25% | 0.0045 |
| bc_open_to_buy | Missing | 1.00% | 0.98% | 0.0000 |
| tot_hi_cred_lim | <= 39,077 | 22.51% | 20.03% | 0.0029 |
| tot_hi_cred_lim | (39,077, 67,226] | 18.48% | 18.36% | 0.0000 |
| tot_hi_cred_lim | (67,226, 177,490] | 25.96% | 27.55% | 0.0009 |
| tot_hi_cred_lim | (177,490, 254,061] | 12.01% | 11.61% | 0.0001 |
| tot_hi_cred_lim | (254,061, 381,767] | 12.04% | 12.37% | 0.0001 |
| tot_hi_cred_lim | > 381,767 | 8.99% | 10.08% | 0.0013 |
| annual_inc | <= 37,000 | 16.67% | 16.07% | 0.0002 |
| annual_inc | (37,000, 45,000] | 12.38% | 11.51% | 0.0006 |
| annual_inc | (45,000, 65,000] | 27.16% | 26.44% | 0.0002 |
| annual_inc | (65,000, 80,000] | 14.60% | 14.71% | 0.0000 |
| annual_inc | (80,000, 110,000] | 16.50% | 16.79% | 0.0001 |
| annual_inc | > 110,000 | 12.69% | 14.49% | 0.0024 |
| acc_open_past_24mths | <= 1 | 14.93% | 14.28% | 0.0003 |
| acc_open_past_24mths | (1, 2] | 14.18% | 13.45% | 0.0004 |
| acc_open_past_24mths | (2, 3] | 15.63% | 14.56% | 0.0007 |
| acc_open_past_24mths | (3, 5] | 26.76% | 25.65% | 0.0005 |
| acc_open_past_24mths | (5, 8] | 20.33% | 21.39% | 0.0005 |
| acc_open_past_24mths | > 8 | 8.17% | 10.66% | 0.0066 |
| total_rev_hi_lim | <= 6,700 | 7.73% | 7.39% | 0.0002 |
| total_rev_hi_lim | (6,700, 18,200] | 34.24% | 30.98% | 0.0033 |
| total_rev_hi_lim | (18,200, 31,000] | 26.01% | 25.63% | 0.0001 |
| total_rev_hi_lim | (31,000, 38,400] | 9.01% | 9.31% | 0.0001 |
| total_rev_hi_lim | (38,400, 53,700] | 11.00% | 11.64% | 0.0004 |
| total_rev_hi_lim | > 53,700 | 12.01% | 15.06% | 0.0069 |
| dti | <= 12.7 | 30.09% | 28.04% | 0.0014 |
| dti | (12.7, 19] | 28.00% | 26.64% | 0.0007 |
| dti | (19, 23.02] | 15.52% | 15.18% | 0.0001 |
| dti | > 23.02 | 26.38% | 30.13% | 0.0050 |
| dti | Missing | 0.00% | 0.00% | 0.0000 |
| mort_acc | <= 0 | 43.04% | 43.09% | 0.0000 |
| mort_acc | (0, 1] | 16.14% | 16.88% | 0.0003 |
| mort_acc | (1, 2] | 13.13% | 14.16% | 0.0008 |
| mort_acc | (2, 3] | 10.02% | 10.48% | 0.0002 |
| mort_acc | > 3 | 17.67% | 15.40% | 0.0031 |
| home_ownership | {OTHER_RARE, MORTGAGE} | 47.12% | 46.54% | 0.0001 |
| home_ownership | {OWN} | 9.98% | 11.48% | 0.0021 |
| home_ownership | {RENT} | 42.89% | 41.99% | 0.0002 |
| mo_sin_rcnt_tl | <= 1 | 9.94% | 10.65% | 0.0005 |
| mo_sin_rcnt_tl | (1, 3] | 20.74% | 22.58% | 0.0016 |
| mo_sin_rcnt_tl | (3, 6] | 24.58% | 23.86% | 0.0002 |
| mo_sin_rcnt_tl | (6, 9] | 16.81% | 15.32% | 0.0014 |
| mo_sin_rcnt_tl | (9, 13] | 12.32% | 12.28% | 0.0000 |
| mo_sin_rcnt_tl | > 13 | 15.62% | 15.30% | 0.0001 |
| mths_since_recent_inq | <= 1 | 17.51% | 18.35% | 0.0004 |
| mths_since_recent_inq | (1, 3] | 14.97% | 15.70% | 0.0003 |
| mths_since_recent_inq | (3, 7] | 23.01% | 22.25% | 0.0003 |
| mths_since_recent_inq | (7, 10] | 12.02% | 10.82% | 0.0013 |
| mths_since_recent_inq | (10, 16] | 14.03% | 13.62% | 0.0001 |
| mths_since_recent_inq | > 16 | 8.24% | 7.94% | 0.0001 |
| mths_since_recent_inq | Missing | 10.22% | 11.33% | 0.0011 |
| mo_sin_old_rev_tl_op | <= 58 | 5.01% | 6.75% | 0.0051 |
| mo_sin_old_rev_tl_op | (58, 84] | 6.65% | 4.75% | 0.0064 |
| mo_sin_old_rev_tl_op | (84, 119] | 15.94% | 14.70% | 0.0010 |
| mo_sin_old_rev_tl_op | (119, 203] | 39.68% | 39.11% | 0.0001 |
| mo_sin_old_rev_tl_op | (203, 253] | 13.87% | 14.01% | 0.0000 |
| mo_sin_old_rev_tl_op | > 253 | 18.85% | 20.69% | 0.0017 |
| loan_to_inc | <= 0.06667 | 8.48% | 9.91% | 0.0022 |
| loan_to_inc | (0.06667, 0.15] | 29.15% | 30.34% | 0.0005 |
| loan_to_inc | (0.15, 0.1963] | 16.34% | 15.96% | 0.0001 |
| loan_to_inc | (0.1963, 0.27] | 21.55% | 20.54% | 0.0005 |
| loan_to_inc | (0.27, 0.3571] | 15.75% | 14.07% | 0.0019 |
| loan_to_inc | > 0.3571 | 8.73% | 9.19% | 0.0002 |
| loan_to_inc | Missing | 0.00% | 0.00% | 0.0000 |
| percent_bc_gt_75 | <= 0 | 18.94% | 24.75% | 0.0155 |
| percent_bc_gt_75 | (0, 25] | 12.43% | 13.46% | 0.0008 |
| percent_bc_gt_75 | (25, 50] | 25.38% | 23.72% | 0.0011 |
| percent_bc_gt_75 | (50, 66.7] | 11.98% | 9.92% | 0.0039 |
| percent_bc_gt_75 | > 66.7 | 30.23% | 27.05% | 0.0035 |
| percent_bc_gt_75 | Missing | 1.04% | 1.10% | 0.0000 |
| mths_since_recent_bc | <= 2 | 8.45% | 8.63% | 0.0000 |
| mths_since_recent_bc | (2, 7] | 21.59% | 21.67% | 0.0000 |
| mths_since_recent_bc | (7, 16] | 25.91% | 26.67% | 0.0002 |
| mths_since_recent_bc | (16, 31] | 20.03% | 19.30% | 0.0003 |
| mths_since_recent_bc | (31, 49] | 9.50% | 9.88% | 0.0001 |
| mths_since_recent_bc | > 49 | 13.60% | 12.89% | 0.0004 |
| mths_since_recent_bc | Missing | 0.92% | 0.96% | 0.0000 |

![图 6.3 vintage 曲线（按 issue 季度的累计违约率 vs 账龄）](figures/12_vintage.png)

_图 6.3 vintage 曲线（按 issue 季度的累计违约率 vs 账龄）_

### 6.3 vintage 表：累计违约率按 issue 季度 × 账龄（月）

| issue 季度 | 贷款数 | MOB 3 | MOB 6 | MOB 9 | MOB 12 | MOB 18 | MOB 24 | MOB 30 | MOB 36 | MOB 48 | MOB 60 |
|---|---|---|---|---|---|---|---|---|---|---|---|
| 2013Q1 | 17,988 | 0.63% | 1.71% | 3.04% | 4.32% | 7.33% | 9.77% | 11.62% | 12.54% | 12.59% | 12.59% |
| 2013Q2 | 23,136 | 0.72% | 1.75% | 3.13% | 4.39% | 7.44% | 9.76% | 11.84% | 12.79% | 12.84% | 12.84% |
| 2013Q3 | 27,318 | 0.78% | 1.61% | 2.84% | 4.33% | 7.04% | 9.51% | 11.19% | 12.17% | 12.21% | 12.21% |
| 2013Q4 | 31,980 | 0.47% | 1.32% | 2.58% | 3.96% | 6.52% | 9.04% | 10.80% | 11.88% | 11.91% | 11.91% |
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
- 数据截止月 2019-03；账龄超过 60 个月的违约（0 笔）计入最后一个月。
- 373 笔违约没有 event_date（从未还款），记为账龄 0。

## 7. 自动检查与风险提示

_对 leakage、单箱占比、train–test KS 差、PSI / CSI、高缺失率入模、系数符号与 VIF 的自动检查，并汇总 adapter 与建模警告。_

### 7.0 汇总

- **通过 / 警告 / 不通过 / 提示**：25 / 0 / 0 / 0
- **结论**：全部检查通过

### 7.1 检查清单

| 检查项 | 范围 | 阈值 | 结果 | 判定 | 说明 |
|---|---|---|---|---|---|
| 样本 bad rate 在合理区间 | 数据 | 1%–40% | 14.07% | 🟢 通过 |  |
| IV 过高（疑似 leakage） | 不含平台评级 | IV > 0.5 | 最高 IV 0.1388（fico_mid） | 🟢 通过 |  |
| 入模特征单一分箱占比过高 | 不含平台评级 | 最大箱占比 > 90% | 最大 47.1%（home_ownership） | 🟢 通过 |  |
| train–test KS 差（LR scorecard） | 不含平台评级 | KS(train) − KS(test) > 0.05 | 0.2377 − 0.2319 = +0.0058 | 🟢 通过 |  |
| train–test KS 差（GBDT challenger） | 不含平台评级 | KS(train) − KS(test) > 0.05 | 0.2943 − 0.2677 = +0.0266 | 🟢 通过 |  |
| test KS 高得不合理 | 不含平台评级 | KS > 0.9 | 0.2319 | 🟢 通过 |  |
| score PSI train → test | 不含平台评级 | PSI > 0.25 | 0.0002 | 🟢 通过 |  |
| score PSI train → OOT | 不含平台评级 | PSI > 0.25 | 0.0020 | 🟢 通过 |  |
| 入模特征 CSI（train → OOT） | 不含平台评级 | CSI > 0.25 | 0 / 15 个特征 | 🟢 通过 |  |
| 入模特征缺失率过高 | 不含平台评级 | train 缺失率 > 50% | 最高 10.2%（mths_since_recent_inq） | 🟢 通过 |  |
| LR 系数符号（WOE 越大越安全，系数应为负） | 不含平台评级 | 系数 > 0 | 0 / 15 个为正 | 🟢 通过 |  |
| 入模特征 VIF | 不含平台评级 | VIF > 5.0 | 最高 3.37（bc_open_to_buy） | 🟢 通过 |  |
| swap set：swap-in bad rate 低于 swap-out（OOT，基准 = 平台评级） | 不含平台评级 | swap-in > swap-out | 18.53% vs 19.25% | 🟢 通过 |  |
| IV 过高（疑似 leakage） | 含平台评级 | IV > 0.5 | 最高 IV 0.3378（sub_grade） | 🟢 通过 |  |
| 入模特征单一分箱占比过高 | 含平台评级 | 最大箱占比 > 90% | 最大 47.1%（home_ownership） | 🟢 通过 |  |
| train–test KS 差（LR scorecard） | 含平台评级 | KS(train) − KS(test) > 0.05 | 0.2705 − 0.2614 = +0.0091 | 🟢 通过 |  |
| train–test KS 差（GBDT challenger） | 含平台评级 | KS(train) − KS(test) > 0.05 | 0.3056 − 0.2797 = +0.0259 | 🟢 通过 |  |
| test KS 高得不合理 | 含平台评级 | KS > 0.9 | 0.2614 | 🟢 通过 |  |
| score PSI train → test | 含平台评级 | PSI > 0.25 | 0.0001 | 🟢 通过 |  |
| score PSI train → OOT | 含平台评级 | PSI > 0.25 | 0.0061 | 🟢 通过 |  |
| 入模特征 CSI（train → OOT） | 含平台评级 | CSI > 0.25 | 0 / 16 个特征 | 🟢 通过 |  |
| 入模特征缺失率过高 | 含平台评级 | train 缺失率 > 50% | 最高 10.2%（mths_since_recent_inq） | 🟢 通过 |  |
| LR 系数符号（WOE 越大越安全，系数应为负） | 含平台评级 | 系数 > 0 | 0 / 16 个为正 | 🟢 通过 |  |
| 入模特征 VIF | 含平台评级 | VIF > 5.0 | 最高 3.46（bc_open_to_buy） | 🟢 通过 |  |
| swap set：swap-in bad rate 低于 swap-out（OOT，基准 = 平台评级） | 含平台评级 | swap-in > swap-out | 15.83% vs 22.06% | 🟢 通过 |  |

阈值来自 config `checks`；IV / 单箱占比 / 缺失率在 train 上计算，PSI / CSI 见第 6 节，KS 见第 3 节，swap set 见第 5 节。这些检查只提示风险，不会自动改模型。

## 附录：运行元数据

### 运行元数据

- **config**：configs\lendingclub.yaml（hash a2fc5b0e633b）
- **数据文件**：data/raw/accepted_2007_to_2018Q4.csv.gz；原始 2,260,701 行 → 样本 546,018 行
- **git commit**：b951183
- **运行时间**：2026-10-19 13:01:15
- **总耗时**：124.3 s
- **版本**：python 3.13.2, credit-scorecard-pipeline 0.1.0, pandas 3.0.6, numpy 2.5.4, sklearn 1.9.1, toad 0.1.7, matplotlib 3.11.2
- **缓存**：data\cache\lendingclub_2767e594d504e290.pkl

### 各步骤耗时

| 步骤 | 秒 |
|---|---|
| load | 13.9 |
| split | 0.2 |
| profile | 2.0 |
| variants | 105.2 |
| strategy | 0.5 |
| monitor | 2.3 |
| checks | 0.0 |
| artifacts | 0.1 |
| variant.no_platform_rating.binning | 4.9 |
| variant.no_platform_rating.select_and_lr | 2.0 |
| variant.no_platform_rating.gbdt | 5.2 |
| variant.no_platform_rating.scoring | 6.2 |
| variant.no_platform_rating.cv_lr | 9.6 |
| variant.no_platform_rating.cv_gbdt | 24.9 |
| variant.with_platform_rating.binning | 5.5 |
| variant.with_platform_rating.select_and_lr | 2.5 |
| variant.with_platform_rating.gbdt | 5.3 |
| variant.with_platform_rating.scoring | 6.3 |
| variant.with_platform_rating.cv_lr | 9.5 |
| variant.with_platform_rating.cv_gbdt | 23.3 |

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
    terms_allowed:
    - 36
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
  min_issue_date: 2013-01
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
  max_time_csi: 0.25
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
  target_approval_rate: 0.7
  max_bad_rate: 0.1
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

