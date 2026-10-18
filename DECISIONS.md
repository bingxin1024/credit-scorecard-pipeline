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
