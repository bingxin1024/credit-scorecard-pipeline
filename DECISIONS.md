# DECISIONS.md — 决策记录

每条：问题 / 证据 → 选择 → 依据 → 代码位置。PLAN.md §9 的默认值直接采用，不另记；这里只记偏离、补充和需要用户确认的点。
标注 **[待确认]** 的条目是我拿不准、但先按默认做了的决定。

## Phase 1（2026-10-19）

### D1 分箱库：toad 0.1.7 在 Python 3.13 上可用，保留 optbinning / tree 两级兜底
- `pip install toad` 在 Python 3.13.2 上直接装上了（`toad-0.1.7-cp39-abi3-win_amd64.whl`，abi3 轮子），不需要改用 optbinning。
- `scorecard/binning.py` 把切点搜索做成可插拔后端：`backend: auto` 依次尝试 toad → optbinning → tree（sklearn `DecisionTreeClassifier`，包内实现）。
  WOE / IV / 单调合并 / 缺失箱 / 类别分组全部在包内统一实现，三个后端只负责给数值切点，引擎看不出用的是谁。
- 四个补丁：(a) 取值数 ≤ `max_bins` 的特征（`term` 36/60、`inq_last_6mths` 这类小整数）不走库，每个取值先各成一箱再合并——toad 的 chi 分箱对二值特征会返回 0 个切点；
  (b) 库返回 0 个切点但特征并非常数时退到 tree 切点；
  (c) 连续特征先做 200 段等频预分箱（`binning.prebins`）再交给库：toad 的 chi-merge 从每个不同取值起步，20 万行样本上单个连续特征要 130 s，预分箱后 1.6 s，IV 几乎不变（0.5485 → 0.5408）；
  (d) toad 0.1.7 的 `constraint_mode` 默认 `'any'`，满足 `min_samples` 就停、不管 `n_bins`，传 `'all'`；并在包内再做一次"合并 bad rate 最接近的相邻箱直到 ≤ max_bins"，保证任何后端都不超箱数。
- 代码：`scorecard/binning.py` → `resolve_backend`、`Binner._numeric_splits`、`reduce_to_max_bins`。

### D2 字段审计与 PLAN.md §4.3 的出入
对 `accepted_2007_to_2018Q4.csv.gz` 前 50,000 行探查（151 列）后，和 §4.3 的分组对照，差异如下：
- `int_rate`、`revol_util` 在 Kaggle 版本里已经是数值（没有 `%`），adapter 仍保留"带 % 则去掉"的解析，但实际不触发。
- `revol_bal_joint` 不在 §4.3 的 H 组清单里，归入 H（联合申请）。
- B 组里 `total_pymnt`、`collection_recovery_fee`、`recoveries`、`total_rec_prncp/int/late_fee` 读入但**只用于策略层 net_cash 及其一致性检验**，`last_pymnt_d` 只用于 vintage（`event_date`）；审计表里标为"保留列（非特征）"，绝不进特征。其余 B / C / D / E / F 组字段不读取。
- `issue_d` 只作为 `issue_date`（切分 / 按季度 bad rate / vintage），不作为特征；`earliest_cr_line`、`fico_range_low/high`、`emp_length`、`sec_app_earliest_cr_line` 派生后删掉原列。
- `id` 读入只为识别文件末尾汇总行（id 非数字），随后剔除。
- `member_id`、`desc`、`sec_app_*`、`revol_bal_joint` 等在前 50,000 行里 100% 缺失（这批列 2016 年以后才有），在 2012–2015 的样本里同样接近全缺失，由 `max_missing` 处理。
- 分组写在 `configs/lendingclub.yaml` → `dataset.options.field_groups`，支持通配符；未列出的列一律是 I 组候选特征。
- 代码：`scorecard/adapters/lendingclub.py` → `DEFAULT_FIELD_GROUPS`、`STRATEGY_ONLY`。

### D3 net_cash 定义：total_pymnt 已含 recoveries，不再加；减去 collection_recovery_fee
- 检验（PLAN §4.4）：前 50,000 行里 9,027 笔 Charged Off，`total_pymnt` 与 `total_rec_prncp + total_rec_int + total_rec_late_fee + recoveries` 的最大绝对差 0.01；不含 recoveries 时最大差 33,407 → **total_pymnt 已包含 recoveries**。全量运行时 adapter 再做一次同样的检验并写进报告 1.9。
- 选择：`net_cash = total_pymnt − collection_recovery_fee − funded_amnt`。催收费是为了拿回 recoveries 付出的成本，从放款方视角应扣除（`net_cash_subtract_collection_fee: true` 可关）。
- 代码：`scorecard/adapters/lendingclub.py` → `transform()` 的 net_cash 段。

### D4 子集试跑不能用 `nrows=200000`，改用随机 10% 行
- 文件开头 20 万行全是 2015 年 11–12 月的贷款（Kaggle 文件按年度分块拼接，2015 在最前）。到期规则用"数据里最大 issue 月"做截止，子集的截止月就是 2015-12，没有任何贷款到期，样本为 0。
- 选择：adapter 增加 `sample_frac`（按种子随机抽行，`--sample-frac 0.1`）和 `data_cutoff_month`（可显式指定截止月）。试跑用 `--sample-frac 0.1`，约 22.6 万原始行，时间结构与全量一致。
- 代码：`scorecard/adapters/lendingclub.py` → `load_raw()`；`scorecard/cli.py`。

### D5 **[待确认]** 到期规则导致 OOT 只有 36 期贷款
- 截止月 2018-12 时，36 期贷款要 issue ≤ 2015-12，60 期贷款要 issue ≤ 2013-12。于是 2014–2015 的样本只有 36 期，OOT（2015-07 ~ 2015-12）全是 36 期；train 里 2012–2013 含 60 期。
- 先按 PLAN 原样执行，`term` 作为特征入模；Phase 2 的 CSI 预计会在 `term` 上报警。可选方案：`sample.terms_allowed: [36]` 只建 36 期卡，或把 60 期截止提前。这是建模口径问题，留给用户决定。

### D5b **[待确认]** OOT 占样本 25.6%
- `oot_months = 6` 按 PLAN 默认；但 Lending Club 放款量逐年放大，2015-07 ~ 2015-12 这 6 个月有 162,236 笔，占最终样本的 25.6%，train 只有 330,071 笔。
- 先照默认执行（OOT 大一点只是让 OOT 指标更稳，不影响 train 质量）。若希望 train 更大，可把 `split.oot_months` 改成 3。

### D6 分箱 `max_bins = 6`
- PLAN 只给了 `method = chi`、`min_samples = 0.05`，没有给箱数上限。chi 合并不设上限时 5% 下限意味着最多 20 箱，分数解释性差。
- 选择：`max_bins = 6`（旧 UCI 项目用 5），加上单调合并后多数变量 3–6 箱。

### D7 特征筛选增加"系数符号检查"，并提供 `max_features` 开关
- PLAN §5 的 select 只写了缺失率 / IV / 相关性 / VIF 标警。沿用旧项目 D10 的做法：WOE = ln(good/bad) 时 LR 系数必须为负，出现正系数说明该变量被其他变量"反转"，分数会误导业务 → 剔除正系数变量中 IV 最低的一个并重拟合，循环到全负。
- `select.max_features`（默认 null）可按 IV 截断入模变量数；Lending Club 候选特征多（90+），如果用户希望评分卡控制在 10–15 个变量，改这一项即可。
- 代码：`scorecard/select.py`。

### D8 GBDT challenger 参数沿用旧项目，并剔除全缺失列
- `learning_rate 0.05, max_iter 300, max_leaf_nodes 8, min_samples_leaf 200, l2 1.0, early_stopping False`（旧项目 D13，事先设定不调参）。
- challenger 直接吃全部候选原始特征（含缺失、类别用 code）；在 2012–2015 样本里 `sec_app_*` 等列全缺失，sklearn 的分箱器会报错，fit 时跳过训练集里没有任何观测值的列。
- 代码：`scorecard/model.py` → `GBDTChallenger`。

### D9 交叉验证：每折重做分箱 + WOE，但特征清单来自全 train
- 和旧项目 D16 一样：5 折分层 CV 在 train 内进行，每折重新拟合分箱和 WOE（验证折标签不参与编码），但入模变量清单是在全 train 上选好的，CV 结果略偏乐观；test / OOT 不受影响。
- challenger 同样做 5 折 CV（`model.cv_challenger`，可关以省时间）。

### D10 WOE 约定与平滑
- WOE = ln(good 占比 / bad 占比)，越大越安全，LR 系数应为负；分数 = −Factor × 系数 × WOE。每箱 good / bad 计数各加 0.5 平滑，避免全 good 箱 WOE 无穷大。
- 缺失值单独一箱；训练集没有缺失的变量，预测时遇到缺失给 WOE 0（中性）。类别型变量按 train bad rate 排序后当作有序变量分箱，未见过的类别落到缺失箱。

### D11 `log_annual_inc` 按 PLAN 保留，但会被相关性过滤掉一个
- WOE 分箱只看排序，`log1p(annual_inc)` 与 `annual_inc` 的分箱完全一致、WOE 相关系数 = 1，相关性过滤会按 IV 留一个。保留是为了忠实 PLAN §4.4；对结果无影响。

### D12 无 `issue_date` 的数据集：OOT 用 15% 分层 hold-out 代替
- CLAUDE.md 规定没有日期时 OOT 用分层 hold-out。新增 `split.oot_fraction = 0.15`；报告 1.8 会写明是 hold-out 而非真正的时间外样本。

### D13 UCI adapter 挪到 Phase 3（用户指示）
- Phase 1 只做 Lending Club；UCI 到 Phase 3 用 `ucimlrepo` 的 `fetch_ucirepo(id=350)` 自动下载，参数沿用旧 repo `results/` 里的表（决策树分箱 5 箱 / 单调 / IV ≥ 0.02 / |ρ| ≤ 0.7 / VIF ≤ 5 / 符号检查 / PDO 20、600、20:1）。

### D14 语言
- 代码、docstring、README.md、FAQ.md 英文；README_zh.md、本文件、生成的报告中文（术语英文）。图里的文字用英文，避免 matplotlib 默认字体缺少中文字形。

### D15 环境
- Python 3.13.2，pandas 3.0.6（默认 `str` dtype、copy-on-write），scikit-learn 1.9.1（`LogisticRegression(penalty=...)` 已弃用，改用默认 L2 + `C`），toad 0.1.7。
- 解析后的原始子集缓存为 `data/cache/*.pkl`（gitignored），key 含文件名、大小、mtime、nrows、sample_frac、adapter 版本、usecols；重跑只需几秒。

### D16 代码审查（多视角 + 对抗复核）后的修正
Phase 1 代码写完后跑了一轮 5 个视角（leakage / 数学 / adapter / 报告 / 健壮性）的独立审查，每条发现再由两个"反驳者"复核。确认并修正的点：
- **toad / optbinning 的切点是左闭（lower bin = x < s），引擎是右闭（x <= s）**：直接套用会让取值等于切点的行掉到下一箱，对整数型特征（pub_rec、inq 这类）影响很大。现在把库的切点换算为"严格小于 s 的最大观测值"，行归属与库完全一致（`left_closed_to_right_closed`，有单元测试）。
- 类别型特征的类别如果不是字符串（int / bool 类别）会全部落进缺失箱：分箱与查表统一字符串化。
- 没有训练样本的箱（含 100% 缺失的特征）原来因为 0.5 平滑得到一个很负的 WOE 和一点 IV，现在这类箱 WOE = 0、IV = 0；平滑只对"没有 good 或没有 bad"的箱生效，其余箱是教科书公式。
- HTML 模板的 autoescape 原来没生效（`select_autoescape` 只看最后一个后缀 `.j2`），现在按完整文件名开启；Markdown 不转义。
- net_cash 一致性检验原来看最大绝对差，一行异常就会翻转公式并把 recoveries 重复加进去；现在看"相差 < 1 的占比 ≥ 99%"，两种公式都不满足时按"已包含"处理并给出警告。
- `data_cutoff_month` 在 `configs/lendingclub.yaml` 里固定为 2018-12（文件事实），`nrows` 的头部子集不再因为截止月被子集带偏而得到 0 行。
- 稀有类别合并标签改为 `OTHER_RARE`（真实数据里本来就有 `other` / `OTHER`）；合并按全样本频率计算、不用标签，报告 1.9 注明这是 label-free 但 transductive 的一步。
- `field_groups` 若在 YAML 里漏掉 B / C / D 的内置泄漏模式，adapter 自动补回并警告。
- 报告：issue 年不再带千分位；IV 表按 IV 降序；筛选漏斗列序；"缺失率（train）"标注；第 3 节结尾按实际变体措辞；附录耗时含 report 步骤；缓存命中正确记录；第 2 节按变体循环；LC 专有措辞移到 adapter 的 `meta.notes`。
- 未改（记录）：CV 的入模变量清单固定自全 train（D9），README 措辞已改正；到期规则导致的 term 构成差异见 D5，adapter 现在会在报告警告里直接写出各期限的完整放款窗口。

## Phase 2（2026-10-19）

### D17 cut-off 的匹配规则：取实际通过率最接近目标的整数分数，并报告边际一档
- 分数是整数，50/60/70/80/90% 的目标通过率不可能精确命中。选择：在"按分数降序累计"的曲线上取 |实际通过率 − 目标| 最小的 cut-off，表里同时给出目标与实际通过率（LC test 70% → cut-off 558，实际 69.55%）。
- 候选 cut-off 表增加"边际新增人数 / 边际 bad rate / 边际净现金/笔"：相邻两档之间多放进来的客户才是放松 cut-off 的真实代价，比累计 bad rate 更能回答"再放一档划不划算"。
- 分数段表按分数分位数切右闭区间（不重叠），人数近似相等而非严格等频；PLAN 的"等频 10 段"按此解释，报告注明。
- 代码：`scorecard/strategy.py` → `cutoff_curve`、`pick_cutoffs`、`score_bands`。

### D18 利润曲线：名义净现金、不折现；每笔净现金最大化只在通过率 ≥ 10% 内搜索
- net_cash 按 D3（total_pymnt − collection_recovery_fee − funded_amnt），名义金额，不折现、不扣资金与运营成本，报告 5.0 口径写明。
- 每笔净现金的曲线在通过率很低时只剩几十个高分客户、噪声极大，所以只在通过率 ≥ `strategy.profit_min_approval_rate`（默认 0.1）内取最大值；总净现金不受此限制。另给"全部通过"参照行。
- LC 结果：风险定价使 test 上各分数段的净现金/笔几乎持平（最高分段 1,380，最低分段 1,665），总净现金在 100% 通过时最大；OOT（2015H2 放款）最低分段只剩 73/笔，总净现金最大点移到 cut-off 535 / 98.60%。在定价充分的平台上"利润最大化 cut-off"接近全部通过，模型的价值在定价与分层而不是拒绝——FAQ 8。
- net_cash 缺失按 0 处理并在报告注明行数（LC 为 0 行）。
- 代码：`scorecard/strategy.py` → `profit_optimum`。

### D19 swap set 基准：平台评级逐档往下批、边际档内随机；2×2 表只展示 70% 一档
- 基准 = `meta.platform_grade_col`（LC 的 grade，有序 category），从最好一档往下批到与模型相同的通过人数；边际档内（70% 通常落在某个 grade 中间）按固定种子随机排序。不用 sub_grade 细分是刻意的：引擎只认识 adapter 声明的那一个 grade 列，不碰数据集特定字段。
- 没有平台评级的数据集用同通过率的随机策略做基准（generic adapter 不配 platform_rating_cols 时）。
- 2×2 表只展示最接近 `strategy.swap_set_approval_rate`（默认 0.7；Phase 3 起改名为 `target_approval_rate`，见 D27）的一档；5 个通过率的 swap-in / swap-out 人数与 bad rate 放在折叠汇总表，避免 20 张表。
- 第 7 节加了"swap-in bad rate 应低于 swap-out"的自动检查（OOT，展示档）。LC：不含平台评级的卡在 OOT 70% 只比 grade 好 0.25 pp，60% 一档反而输给 grade（9.55% vs 9.35%）——grade 本身含征信 + 定价信息，这是诚实的结果而不是 bug。
- 代码：`scorecard/strategy.py` → `baseline_order`、`swap_set`。

### D20 PSI / CSI 口径
- score PSI 的分段 = train 分数的 10 个分位数切点（去重；整数分数并列时段数可能少于 10），右闭区间，test / OOT 套同一套边界。CSI 直接用评分卡的分箱（含缺失箱），即"该特征分箱分布的 PSI"。
- 占比为 0 的段按 1e-4 处理（行业惯例）。后果：一个箱从 5.84% 变成 0% 贡献 0.37——LC 的 6 个征信字段（`num_tl_op_past_12m`、`tot_hi_cred_lim` 等）2015 年后不再缺失，CSI 全部 > 0.25，而 score PSI 只有 0.027。这正是 FAQ 10 的"分数稳定、特征不稳"情形；报告 6.2 的"偏移最大的箱"列直接指出是 Missing 箱。
- `term` CSI 0.6447：D5 预告的结果（OOT 只有 36 期）。仍按 PLAN 保留 term 入模；要消除它用 `terms_allowed: [36]`。
- 判定以 train → OOT 为准（没有 OOT 时用 test）；阈值 `monitor.psi_warn / psi_alert` = 0.10 / 0.25，表里用 🟢🟡🔴 文本标色（HTML 与 Markdown 一致，不依赖 CSS）。
- 代码：`scorecard/monitor.py` → `score_psi`、`feature_csi`、`status`。

### D21 vintage：账龄 = event_date − issue_date；截止月取 adapter 的 data_cutoff_month 与数据里最晚违约事件月的较大者
- Lending Club 没有逐月表现，adapter 把 last_pymnt_d 作为 `event_date`；报告写明曲线比真实 Charged Off 时点早约 4–5 个月（adapter 的 `event_date_note`，引擎不认识 last_pymnt_d）。
- 没有 last_pymnt_d 的违约（从未还款，LC 443 笔）记为账龄 0；账龄超过 `monitor.vintage_max_mob`（默认 60）的违约（LC 27 笔）计入最后一个月。
- 观察期：截止月 = max(adapter 的 data_cutoff_month，最晚 issue 月，最晚违约事件月)，LC 为 2019-03（charged-off 贷款的 last_pymnt_d 可以晚于 2018-12）；超过观察期的格子留空。好客户的 event_date 是结清月，不参与截止月（否则合成数据会把截止月推到 2022-12）。
- 2014 年起的 cohort 只有 36 期贷款（D5），曲线在 36 个月后走平；2012–2013 含 60 期，继续升到 60 个月。
- 代码：`scorecard/monitor.py` → `vintage_table`；`scorecard/adapters/lendingclub.py` → `event_date_note`。

### D22 第 7 节检查项与判定语义
- 每行：检查项 / 范围（变体）/ 阈值 / 结果 / 判定 / 说明。判定：🟢 通过、🟡 警告（需人工判断）、🔴 不通过（不应直接上线）、ℹ️ 提示（adapter / 切分 / 建模警告原样转录）。
- PLAN 的 5 项之外补了：bad rate 在 1–40% 之间、test KS > 0.9、LR 系数为正、VIF > max_vif、swap-in 应优于 swap-out、GBDT 的 train–test KS 差。
- IV > 0.5 的特征：未入模为警告，已入模为不通过（adapter 给出 `iv_review` 说明时降为警告，见 D29）。合成数据的 fico_mid 当时 IV 0.805 会触发，D28 调弱生成器后不再触发。
- 结果只提示、不自动改模型。LC Phase 2：21 通过 / 4 警告 / 0 不通过 / 1 提示；警告 = term 单箱占比 90.7%（两套）和 7 个特征 CSI > 0.25（两套）。
- 代码：`scorecard/checks.py`。

### D23 两套模型并排：configs/lendingclub.yaml 与 configs/synthetic.yaml 都设 `use_platform_rating: [false, true]`
- 第 5–7 节与 2–4 节一样按变体循环加前缀；第 5 节末尾新增 5.5 表，按同通过率比较两套模型的通过客群 bad rate（cut-off 本身不可比）。
- 含平台评级时 sub_grade 以 IV 0.3546 入模，grade / int_rate / installment 被相关性过滤掉，入模仍是 20 个变量。OOT AUC 0.6750 → 0.6978，70% 通过率下 bad rate 10.60% → 9.91%。
- 全量运行时间 80 s → 145 s（两套各跑一遍 binning / GBDT / CV）。

### D24 第 5–7 节的 artifacts 与测试
- 每张表都有 CSV（`strategy_*.csv`、`monitor_*.csv`、`checks.csv`），results.json 增加 strategy / monitor / checks 摘要。
- 每个模块暴露 `analyse()` / `run_checks()`、`build_section()`、`write_artifacts()`、`to_summary()`；report.py 只在 `IMPLEMENTED` 为真时调用 `build_section`，占位逻辑保留给未来的节。
- 测试 `tests/test_phase2.py`（合成数据）：cut-off 表单调、分数段人数相加、swap set 四格相加且 swap-in = swap-out 人数、PSI 恒等样本为 0 / 平移 25 分 > 0.25、CSI 捕捉人为平移、vintage 单调且末值 = cohort bad rate、植入 leakage 特征触发不通过、无 net_cash / 无评级时的跳过文案。

## Phase 2 修正 + Phase 3（2026-10-19）

### D25 D5 定案：按产品分卡，Lending Club 只建 36 期评分卡
- `configs/lendingclub.yaml` → `terms_allowed: [36]`；样本定义表第 3 条"仅保留 36 期（按产品分卡）"剔除 650,603 笔 60 期贷款。
- 理由：不同期限是不同产品（定价、客群、久期都不同）；数据截止 2018-12 时只有 2013-12 前放款的 60 期贷款才到期，OOT 窗口（2015-07 ~ 2015-12）里不可能有 60 期贷款，混合建模会让 term 在 train / OOT 之间出现结构性漂移（Phase 2 报告里 term 的 CSI 0.6447 就是这个）。
- 结果：最终样本 589,488 笔（bad rate 14.03%），train 299,076 / test 128,176 / OOT 162,236；term 成为常数被 IV 筛掉。要建 60 期卡，改 `terms_allowed: [60]` 并把 `data_cutoff_month` / `min_issue_date` 调到 60 期能到期的窗口。

### D26 **[待确认]** select 新增时间稳定性筛选（`select.max_time_csi` = 0.25）：Lending Club 上剔除 15 个征信字段，AUC 降约 0.02
- 做法：train 内取 issue 年最早的一年（2012）与最晚的一年（2015，上半年）为两个样本，对每个通过缺失率 / IV 筛选的候选特征按评分卡分箱（含缺失箱）算 CSI，> 0.25 剔除；放在相关性筛选之前，避免不稳定的高 IV 特征挤掉稳定的相关特征。报告 2.3b 列出被剔除的特征和偏移最大的箱；无 issue_date 的数据集跳过并在漏斗里注明。
- Lending Club：15 个特征被剔除，全部是 Missing 箱的变化——`num_tl_op_past_12m`、`tot_hi_cred_lim` 等 6 个字段 2012 年缺失 51.65%、2015 年 0%（CSI 4.8），`acc_open_past_24mths`、`mort_acc` 等 13.8% → 0%（CSI 1.0），`bc_open_to_buy`、`percent_bc_gt_75` 等 14.9% → 1%（CSI 0.4）。这些字段 2012 年中才开始由征信局提供。
- 代价（同一 36 期样本、同一配置，只关掉筛选的对照跑，`--no-cv`）：入模 15 个特征，test AUC 0.6656 / KS 0.2378，OOT 0.6743 / 0.2508；开着筛选是 6 个特征，test 0.6473 / 0.2134，OOT 0.6508 / 0.2149。筛选换来第 6 节零漂移、评分卡只用申请时一直有的 6 个变量，代价是约 0.02 AUC（OOT 0.024），而且 OOT 上的 swap set 输给 grade 0.42 pp（第 7 节警告）。
- 备选（已试跑）：`sample.min_issue_date: "2013-01"` 让这批字段在 train 内全程有值——筛选照常开着也保留 15 个特征，546,018 笔，test AUC 0.6624 / KS 0.2319，OOT 0.6737 / 0.2491。这是我建议的口径，但它改变了 PLAN 的 2012-01 起点，留给用户决定；本次提交按用户原话执行（2012-01 起、阈值 0.25）。
- 代码：`scorecard/select.py` → `time_stability_table`；报告 2.3 漏斗与 2.3b。

### D27 约束下的最优 cut-off 作为第 5 节主要结论；利润曲线退为参照
- 新增 `strategy.max_bad_rate`（默认 0.10）与 `strategy.target_approval_rate`（默认 0.70，取代 Phase 2 的 `swap_set_approval_rate`；swap set 也按这档展示）。5.3 表：(a) 通过客群 bad rate ≤ 上限时通过率最高的 cut-off；(b) 目标通过率下的坏账率与净现金。报告头部也显示 (a)。
- 第 5 节加一段按数据判断的说明：若无约束总净现金的最大点在通过率 ≥ 95%（LC：OOT 99.68%），写明平台已实施 risk-based pricing、各分数段每笔净现金接近持平、评分卡的价值在风险约束下的准入与分层定价；否则写明利润与坏账率约束指向同一方向。
- LC（不含平台评级，OOT）：bad rate ≤ 10% → score ≥ 567，通过 56.2%，bad rate 9.95%；70% → score ≥ 561，11.27%。含平台评级：≤ 10% → score ≥ 563，66.95%。
- 代码：`scorecard/strategy.py` → `constrained_cutoffs`；`scorecard/report.py` 头部。

### D28 合成数据生成器调弱：所有特征 IV < 0.5，demo 的第 7 节全部通过
- fico 系数 −0.03 → −0.019，其余系数居中并微调，grade 噪声 0.8 → 0.9；bad rate 27.4% → 17.9%，最高 IV fico_mid 0.39–0.41（三个测试种子），5 个特征的 LR AUC 仍 > 0.70（`tests/test_scorecard.py` 的阈值）。
- demo 的 GBDT 改为 120 棵树 / 6 叶 / 叶最少 300 行（`configs/synthetic.yaml`）：默认 300 棵树按 30 万行设计，在 1.2 万行 train 上 train–test KS 差 0.11 会触发第 7 节警告。UCI（1.8 万行 train）同样改为 150 棵树 / 6 叶。合成 demo：25 通过 / 0 警告 / 0 不通过。

### D29 UCI adapter（Phase 3）
- `scorecard/adapters/uci.py` + `configs/uci.yaml`：`ucimlrepo` 下载 id=350 并缓存为 `data/raw/uci_default_of_credit_card_clients.csv`（gitignored）；X1..X23 用 UCI 变量表的 description 改回 LIMIT_BAL / PAY_0 等名字。
- 沿用旧 repo（credit-default-scorecard）的决定：EDUCATION 0/5/6 → 4、MARRIAGE 0 → 3；SEX、MARRIAGE 受保护属性不入模（留在数据帧里供公平性检查）；PAY_* 按有序数值；BILL_AMT 负值保留、比率特征中按 0；11 个行为派生特征（UTIL_*、PAY_RATIO_*、DELQ_*、NO_BILL_MONTHS_6M）。参数：tree 分箱 5 箱、单调、IV ≥ 0.02、|ρ| ≤ 0.7、VIF ≤ 5、符号检查、PDO 20 / 600 / 20:1。
- 与旧 repo 的差异：切分是 15% 分层 hold-out 充当 OOT + 其余 70/30（旧 repo 只有 70/30）；旧 repo test AUC 0.7616 / KS 0.3992，这里 test 0.7667 / 0.4212、hold-out 0.7641 / 0.4020，量级一致。
- PAY_0（IV 0.849）等 4 个特征 IV > 0.5：adapter 通过 `meta.notes["iv_review"]` 说明它们是标签之前的还款状态、不是贷后信息；checks.py 读到该说明时把"已入模的高 IV"从不通过降为警告并附上说明（引擎不认识 PAY_0，只认识 adapter 给的说明）。
- 无 issue_date → 时间稳定性筛选跳过；无 net_cash → 5.4 显示"数据不含回款信息，跳过"；无平台评级 → swap set 用随机基准。

### D30 Phase 3 其余
- `SKILL.md`：输入（CSV + target_col 或 adapter 名）、步骤（先 `--dry-run` 看样本定义表）、输出、护栏。护栏由 CLI 强制：不改原数据；建模前打印样本定义表；bad rate 不在 1–40% 时退出码 2（`--allow-any-bad-rate` 覆盖）；空样本停止；保留列不能做特征；第 7 节判定原样转述。
- README.md / README_zh.md：顶部示例报告截图（`docs/images/report-lendingclub.jpg`）、一行复现命令、架构图；全部数字重抄自新报告。FAQ.md 14 题补齐。
- CI（`.github/workflows/ci.yml`，Phase 1 已有）：ruff + pytest + 合成数据冒烟，Python 3.11 / 3.13；不跑 UCI（需要联网）。mkdocs 未做（可选项）。
- 打 tag v1.0。
