# PLAN.md — 建设计划

> 给 Claude Code 的执行计划。CLAUDE.md 是约定，这里是细节和验收标准。
> 术语保留英文；用户没有回答的决定按 §9 默认执行，并记入 DECISIONS.md。

## 0. 一句话目标

把"对一份数据做一次评分卡分析"变成"给任何一份带违约标签的贷款数据，自动跑完
样本定义 → 分箱 → 建模 → 评分卡 → 策略 → 监控，并交出一份固定结构报告"的工具，
外加一个 SKILL.md 让 agent 能直接调用。主数据集 Lending Club，第二数据集 UCI。

## 1. 架构

```
raw data ──adapter──▶ standard frame ──engine──▶ artifacts ──report──▶ report.html / report.md
                                        │
                                        ├─ profile  → 数据体检
                                        ├─ binning  → 分箱 / WOE / IV
                                        ├─ select   → IV + 相关性 + 缺失率筛选
                                        ├─ model    → LR scorecard + GBDT challenger
                                        ├─ scorecard→ PDO 换算、评分卡表
                                        ├─ strategy → cut-off / swap set / 利润
                                        └─ monitor  → PSI / CSI / vintage
SKILL.md ──▶ cli.py run --config <yaml>
```

换数据集 = 新增一个 adapter + 一个 yaml，engine 一行不改。

## 2. 标准数据帧（adapter 的输出契约）

adapter 返回 `pandas.DataFrame` + `AdapterMeta`：

| 列 / 字段 | 必须 | 说明 |
|---|---|---|
| `target` | 是 | 0/1，1 = 违约 |
| 特征列 | 是 | 数值或 category dtype；adapter 负责类型清理 |
| `issue_date` | 否 | datetime；有则按时间切 OOT、画 vintage |
| `loan_amount`, `net_cash` | 否 | 用于策略层利润计算；`net_cash` 是贷后实际结果，**只能进策略层，禁止进特征** |
| `platform_rating_cols` (meta) | 否 | 平台自有评级字段名列表，engine 按 config 开关决定是否作为特征 |
| `sample_definition_log` (meta) | 是 | 每条筛选规则：规则名、剔除行数、剩余行数、剩余 bad rate |
| `field_audit` (meta) | 是 | 每个原始字段：保留 / 剔除、原因分组（见 §4.3） |

## 3. 报告固定七节

每节有标题、一段说明、表格/图；未实现的节显示"（本阶段未实现）"。

1. **样本与数据概况** — 数据来源、行列数；样本定义影响表（§2 的 log）；字段审计清单；
   缺失率 Top 20；bad rate 按时间（有 issue_date 时按季度）。
2. **分箱与 IV** — IV 排名表（全部特征）；入模特征的分箱表（bin、count、bad rate、WOE）；
   Top 8 特征的 WOE 图；单调性检查结果。
3. **模型表现** — LR 系数表（含 VIF）；train / test / OOT 的 AUC、KS、Gini；
   LR vs GBDT challenger 对比表（同一指标）；KS 曲线、ROC 图；
   若 config 开启了"含 / 不含平台评级"两套，并排展示。
4. **评分卡** — PDO、base score、base odds；评分卡表（变量、分箱、分数）；
   分数分布直方图（good / bad 分开）。
5. **策略分析** — 分数段表（等频 10 段：区间、人数、累计通过率、bad rate、累计 bad rate）；
   通过率–坏账率曲线；候选 cut-off 表（通过率 50/60/70/80% 对应的 cut-off 与坏账率）；
   利润曲线（§6.1）与利润最大化 cut-off；swap set 表（§6.2）。
6. **稳定性** — score PSI（train→test、train→OOT）；每个入模特征的 CSI；
   PSI 阈值 0.10 / 0.25 标色；vintage 曲线（§6.3）。
7. **自动检查与风险提示** — IV > 0.5 的特征（疑似 leakage）；单一分箱占比 > 90% 的特征；
   train–test KS 差 > 0.05；PSI > 0.25；缺失率 > 50% 仍入模；以及任何 adapter 报告的
   警告。每条写清"检查了什么、阈值、结果"。

附录：运行元数据（config 哈希、数据文件、行数、git commit、时间、各步骤耗时）。

## 4. Lending Club adapter 规范

文件：`data/raw/accepted_2007_to_2018Q4.csv.gz`（Kaggle `wordsforthewise/lending-club`）。
数据字典若有（`LCDataDictionary.xlsx`）放同目录，adapter 优先用它核对字段。

### 4.1 读取
- `pd.read_csv(..., compression="gzip", usecols=<白名单>, low_memory=False)`；
  内存按 16 GB 机器考虑，先用 `nrows=50000` 探查类型，再全量读。
- 文件末尾有汇总行（`id` 非数字、`loan_status` 为空），先剔除。
- 字符串字段解析：`term`（" 36 months" → 36）、`emp_length`（"10+ years" → 10，"< 1 year" → 0，
  "n/a" → NaN）、`issue_d` / `earliest_cr_line`（"Dec-2015" → datetime）、
  `int_rate` / `revol_util`（若带 % 则去掉）。

### 4.2 样本定义（每条规则写入 sample_definition_log）
1. 剔除 `loan_status` 以 "Does not meet the credit policy" 开头的贷款（早期不同准入政策）。
2. 到期筛选：`issue_d + term 个月 <= 数据截止月`（截止月 = 数据中 `issue_d` 最大值）。
   保证 performance window 完整。
3. 终态映射：`Charged Off`、`Default` → 1；`Fully Paid` → 0；
   其余（`Current`、`Late (16-30 days)`、`Late (31-120 days)`、`In Grace Period`）
   → indeterminate，剔除。
4. 起始年份：默认只保留 `issue_d >= 2012-01`（config `min_issue_date`，可改）。
   理由：2007–2011 量小且产品、客群与后期不同；在报告第 1 节用"bad rate 按年"图证明。
5. 记录最终样本量与 bad rate。

### 4.3 字段审计（field_audit 分组）
每个原始字段归入且仅归入一组；分组写进 config，adapter 执行并输出清单。
初稿如下，Claude Code 需对照数据字典核对并在 DECISIONS.md 记录改动：

- **A 目标来源**：`loan_status`
- **B 贷后回款 / 余额（泄漏，剔除）**：`total_pymnt`, `total_pymnt_inv`, `total_rec_prncp`,
  `total_rec_int`, `total_rec_late_fee`, `recoveries`, `collection_recovery_fee`,
  `out_prncp`, `out_prncp_inv`, `last_pymnt_d`, `last_pymnt_amnt`, `next_pymnt_d`,
  `last_credit_pull_d`
- **C 贷后信用更新（泄漏，剔除）**：`last_fico_range_high`, `last_fico_range_low`
- **D 困难 / 和解 / 还款计划（泄漏，剔除）**：所有 `hardship_*`、`settlement_*`、
  `debt_settlement_flag*`、`deferral_term`、`payment_plan_start_date`,
  `orig_projected_additional_accrued_interest`, `pymnt_plan`
- **E 无信息 / 标识 / 自由文本（剔除）**：`id`, `member_id`, `url`, `desc`, `title`,
  `policy_code`, `emp_title`（可选：保留 Top 20 类别 + OTHER，默认剔除）, `zip_code`（默认剔除）
- **F 投资人侧（剔除）**：`funded_amnt_inv`
- **G 平台评级（单独开关 `use_platform_rating`）**：`grade`, `sub_grade`, `int_rate`, `installment`
- **H 联合申请字段**：`annual_inc_joint`, `dti_joint`, `verification_status_joint`, `sec_app_*`，
  默认保留，缺失按"非联合申请"处理
- **I 申请时可得（候选特征）**：其余全部，包括 `loan_amnt`, `funded_amnt`, `term`, `emp_length`,
  `home_ownership`, `annual_inc`, `verification_status`, `purpose`, `addr_state`, `dti`,
  `delinq_2yrs`, `earliest_cr_line`, `fico_range_low/high`, `inq_last_6mths`, `mths_since_*`,
  `open_acc`, `pub_rec`, `revol_bal`, `revol_util`, `total_acc`, `application_type`,
  `acc_open_past_24mths`, `mort_acc`, `num_*`, `pct_tl_nvr_dlq`, `tot_*`, `total_*`,
  `initial_list_status`, `disbursement_method` 等。
  注意：一批征信字段（`num_*`、`mo_sin_*` 等）2015 年前缺失率极高，由 select 的
  缺失率阈值处理，并在第 1 节按年展示缺失率。

### 4.4 变量构造
- `fico_mid = (fico_range_low + fico_range_high) / 2`，然后删掉原两列
- `credit_hist_months = months_between(issue_d, earliest_cr_line)`
- `emp_length_years`（数值）
- `log_annual_inc = log1p(annual_inc)`
- `loan_to_inc = loan_amnt / annual_inc`（annual_inc = 0 时 NaN）
- 类别合并：占比 < 1% 的类别并入 `OTHER`（`purpose`, `home_ownership`, `addr_state`）
- 策略层用：`loan_amount = funded_amnt`；
  `net_cash = total_pymnt − funded_amnt`。先用数据检验 `total_pymnt` 是否已包含
  `recoveries`（对 Charged Off 样本比较 `total_pymnt` 与
  `total_rec_prncp + total_rec_int + total_rec_late_fee + recoveries`），
  按检验结果决定是否再加 `recoveries − collection_recovery_fee`，结论写 DECISIONS.md。

### 4.5 切分
- 按 `issue_date` 排序；最后 `oot_months`（默认 6 个月）为 OOT。
- 其余按 `train_ratio`（默认 0.7）分层随机切 train / test。
- 分箱、WOE、特征选择、模型全部只在 train 上拟合；CV 时在每个 fold 内重做分箱与 WOE。

## 5. 引擎规范

- **profile**：行列数、dtype、缺失率、数值分布分位数、类别基数；bad rate 按 issue 季度。
- **binning**：数值用 toad `Combiner`（method 默认 `chi`，`min_samples` 默认 0.05），
  类别按 WOE 排序合并；对数值特征强制单调（不单调则减少箱数直至单调或退到 2 箱）；
  缺失单独一箱。大样本时按 config `binning_sample_size`（默认 200000）抽样拟合。
- **select**：缺失率 > `max_missing`（默认 0.5）剔除；IV < `min_iv`（默认 0.02）剔除；
  IV > `leakage_iv`（默认 0.5）标警但不自动剔除；相关性 > `max_corr`（默认 0.7）保留 IV 高者；
  入模后 VIF > 5 标警。
- **model**：LR 用 `LogisticRegression(penalty="l2", C=config)`，WOE 输入；
  challenger 用 `HistGradientBoostingClassifier` 直接吃原始（未 WOE）特征；
  指标：AUC、KS、Gini，train / test / OOT；5-fold CV 报均值 ± std。
- **scorecard**：`PDO = 20`，`base_score = 600`，`base_odds = 20`（即 600 分 ↔ good:bad = 20:1）；
  分数 = offset + factor × ln(odds)，分到每个变量的每个分箱；输出评分卡表。
- 若 `use_platform_rating` 两档都跑：输出两套模型并在第 3 节并排。

## 6. 策略层与监控层规范

### 6.1 cut-off 与利润
- 在 test 与 OOT 上分别计算：按分数降序累计通过率、累计 bad rate。
- 候选 cut-off：通过率 50 / 60 / 70 / 80 / 90 % 对应的分数与 bad rate。
- 利润曲线：对每个 cut-off，`总净现金 = Σ net_cash（通过样本）`、`每笔净现金 = 总 / 通过数`；
  给出总净现金最大的 cut-off 和每笔净现金最大的 cut-off，两者并列报告。
  `net_cash` 来自实际回款（§4.4），这是"策略评估用实际结果"，报告里写明。
- 没有 `net_cash` 的数据集（UCI）：该小节显示"数据不含回款信息，跳过"。

### 6.2 swap set
- 基准策略：平台评级（`grade`）从 A 往下批，取到与模型 cut-off 相同的通过率。
- 2×2 表：双批、双拒、模型批基准拒（swap-in）、模型拒基准批（swap-out），每格人数与 bad rate。
- 没有平台评级的数据集：用"随机策略（同通过率）"做基准。

### 6.3 监控
- score PSI：train → test、train → OOT（10 等频段，以 train 为 expected）。
- CSI：每个入模特征，train → OOT。
- vintage：有 `issue_date` 时，按 issue 季度画累计违约率随账龄（月）变化；
  账龄用 `last_pymnt_d − issue_d` 近似违约发生月（Lending Club 没有逐月表现，报告注明是近似）。

## 7. 分阶段与验收标准

### Phase 1 — 跑通 + 报告 1–4 节（目标：首个工作段完成）
- [ ] 包骨架、`pyproject.toml`、`configs/`、`.gitignore`（含 `data/raw/`）
- [ ] `adapters/lendingclub.py` 完整实现 §4；`adapters/uci.py` 复用旧 repo 的处理
- [ ] profile / binning / select / model / scorecard
- [ ] report：七节框架 + 1–4 节内容；5–7 节占位
- [ ] `python -m scorecard run --config configs/uci.yaml` < 1 分钟
- [ ] `python -m scorecard run --config configs/lendingclub.yaml` < 15 分钟
- [ ] 打开 report.html 人工检查；`examples/` 放入两份报告
- [ ] tests：synthetic 数据的端到端 + adapter 样本定义规则 + 分箱单调 + PDO 换算（≥ 10 个用例）
- [ ] DECISIONS.md、FAQ.md 初稿；commit + push

### Phase 2 — 策略 + 监控（5–6 节）
- [ ] strategy.py：§6.1、§6.2
- [ ] monitor.py：§6.3
- [ ] 第 7 节自动检查
- [ ] 两套模型（含 / 不含平台评级）并排
- [ ] 更新 examples、FAQ、DECISIONS；commit + push

### Phase 3 — 作品集化
- [ ] SKILL.md：输入（csv 路径 + target 列，或 adapter 名）、步骤、输出、护栏
      （不改原数据；先打印样本定义影响表；bad rate 不在 1–40% 时停下问人）
- [ ] README.md（英文，顶部示例报告截图 + 一行命令复现 + 架构图）、README_zh.md
- [ ] FAQ.md 完整（§8）
- [ ] GitHub Actions：ruff + pytest（synthetic，不需要 data/raw）
- [ ] mkdocs 最小站点（可选）
- [ ] 版本 v1.0 tag

## 8. FAQ.md 必须回答的面试问题

每题：一段口头回答（≤ 150 字）+ 项目里对应的文件 / 报告节 + 实际数字。

1. 违约标签怎么定义的？为什么剔除未到期和 indeterminate？表现期是多久？
2. 剔除了哪些泄漏字段？举三个，说明为什么是贷后信息。`last_fico_range_*` 为什么算泄漏？
3. 为什么 WOE 要在每个 fold 里重做？放在外面会怎样？
4. 分箱怎么保证单调？不单调怎么办？
5. IV 的阈值怎么定？IV 特别高说明什么？
6. 为什么最终用 LR 不用 GBDT？challenger 的意义是什么？
7. 600 分对应 20:1 odds、PDO 20，offset 和 factor 怎么算？写出公式和数字。
8. cut-off 怎么定？通过率和坏账率怎么权衡？利润最大化的 cut-off 和坏账率最低的 cut-off 为什么不同？
9. swap set 怎么看？swap-in 的 bad rate 比 swap-out 高说明什么？
10. PSI 公式和 0.1 / 0.25 阈值的由来；score PSI 稳定但某特征 CSI 很高怎么处理？
11. OOT 和普通 hold-out 的区别；为什么按时间切？
12. 含平台评级和不含的两套模型差多少？实际业务里该不该用？
13. 换一个数据集要改什么？（答：一个 adapter + 一个 yaml）
14. agent 调用时怎么防止它乱跑？（答：SKILL.md 的护栏）

## 9. 默认决定（用户未回答时）

- 项目名 / repo 名：`credit-scorecard-pipeline`
- README 英文，README_zh 中文；报告中文，术语英文
- Python 3.11；MIT License
- `min_issue_date = 2012-01`；`oot_months = 6`；`train_ratio = 0.7`；`random_state = 42`
- `use_platform_rating`：Phase 1 只跑"不含"；Phase 2 两档都跑
- `emp_title`、`zip_code` 剔除；`addr_state` 保留
- 分箱 `method = chi`，`min_samples = 0.05`，`binning_sample_size = 200000`
- PDO 20、base 600、odds 20:1
