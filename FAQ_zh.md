# FAQ（中文口头版）— 面试怎么讲这个项目

每题一段 150 字以内的口语化回答，术语保留英文；"出处"指向代码文件和报告章节，"数字"抄自
`examples/lendingclub/report.md`（2013-01 起放款的 36 期 Lending Club 评分卡，默认指不含平台评级的那套）和
`examples/uci/report.md`，与英文版 `FAQ.md` 一致。

### 1. 违约标签怎么定义的？为什么剔除未到期和 indeterminate？表现期多长？

终态是 Charged Off 或 Default 记 1，Fully Paid 记 0。按产品分卡，只留 36 期；只留到数据截止时已经到期的贷款，这样每笔都有同样长的时间去出事，不然 2017 年还在 Current 的贷款会被当成好客户。截止时仍是 Current、Late、宽限期的，结果未知，划到哪边都会扭曲 bad rate，所以剔除。表现期就是整个 36 个月，比银行常用的 12–18 个月长，bad rate 也就偏高。

*出处：* `scorecard/adapters/lendingclub.py`，报告 1.2。
*数字：* 36 期筛选剔除 650,603 笔，到期规则 988,585 笔，indeterminate 147 笔，2013-01 起点 72,566 笔；最终 546,018 笔，bad rate 14.07%。

### 2. 剔除了哪些泄漏字段？举三个，为什么 last_fico_range_* 算泄漏？

放款之后才产生的信息一律不进模型：一是 total_pymnt、recoveries、out_prncp 这类回款和余额，它们本身就是结果；二是 last_pymnt_d、next_pymnt_d 这类还款时间线，直接暴露贷款还活不活着；三是 hardship_*、settlement_* 这类只有出问题的贷款才会有的处置动作。last_fico_range 是最后一次拉征信时的 FICO，通常已经逾期好几个月了，反映的是结果不是申请时的风险。151 个原始字段每个都归了组，默认不会漏网。

*出处：* `configs/lendingclub.yaml` 的 field_groups，报告 1.4。
*数字：* B / C / D 三组共 31 个字段按泄漏剔除，候选特征 99 个。

### 3. 为什么 WOE 要在每个 fold 里重做？放在外面会怎样？

WOE 用了标签：每个箱的值是 ln(good 占比 / bad 占比)。如果先在全部训练集上编码再做 CV，验证折的标签已经被编码"看过"了，CV 结果就偏乐观，和把 target encoding 拟合在全量数据上是一回事。每折只用训练折重新分箱、重算 WOE，验证折才是干净的。train / test / OOT 也是同一个道理：分箱、WOE、变量筛选、模型全部只在 train 上拟合。

*出处：* `scorecard/model.py` 的 cross_validate_scorecard，`scorecard/pipeline.py`。
*数字：* 5 折 CV AUC 0.6636 ± 0.0030（KS 0.2373 ± 0.0039），test AUC 0.6624，两者很接近。

### 4. 分箱怎么保证单调？不单调怎么办？

数值变量先用 toad 的 chi-merge 切箱，最多 6 箱、每箱至少 5% 样本；然后看各箱 bad rate 是否单向变化，不单调就把违反方向、bad rate 最接近的相邻两箱合并，直到单调或只剩 2 箱。类别变量先按 train 的 bad rate 排序再分箱，天然单调。单调的好处是分数能解释——DTI 越高不可能反而加分——也不容易拟合噪声，代价是 U 形变量会损失一点 IV。

*出处：* `scorecard/binning.py` 的 merge_to_monotonic，报告 2.4。
*数字：* 15 个入模变量里只有 percent_bc_gt_75 初始不单调、合并后单调；最终 15 个全部单调。

### 5. IV 阈值怎么定？IV 特别高说明什么？

经验值：IV 小于 0.02 基本没信息，0.02–0.1 弱，0.1–0.3 中等，0.3–0.5 强，超过 0.5 就要怀疑。低于 0.02 剔除，高于 0.5 标记为疑似 leakage 但保留，交给人判断。Lending Club 上申请时字段没有一个接近 0.5，这本身就说明泄漏字段确实清干净了；UCI 的 PAY_0 到 0.849，adapter 写明了它是标签之前的还款状态，合理。阈值在 config 里，筛选表会记每个变量被哪条规则剔掉。

*出处：* `scorecard/select.py`，报告 2.2–2.3。
*数字：* 最高 IV 是 fico_mid 0.1388；IV < 0.02 剔除 40 个，缺失率 > 50% 剔除 35 个，时间稳定性 0 个，相关性 8 个，系数符号 1 个；没有 IV > 0.5 的。

### 6. 为什么最终用 LR 不用 GBDT？challenger 的意义是什么？

评分卡用 WOE 逻辑回归，因为每一分都能追到某个变量的某个箱，决策引擎里就是一张查找表，拒绝原因码也能直接给出来。GBDT 直接吃原始特征（含缺失）作 challenger，用来量化"坚持线性、单调、分箱"到底丢了多少信息。这里差距约 0.02 AUC，说明评分卡已经接近这份数据的上限；差距大的话就该回头改分箱或加交互项。

*出处：* `scorecard/model.py` 的 GBDTChallenger，报告 3.4。
*数字：* test AUC LR 0.6624 vs GBDT 0.6865；OOT 0.6737 vs 0.6968（KS 0.2491 vs 0.2848）。

### 7. 600 分对应 20:1、PDO 20，offset 和 factor 怎么算？

分数 = Offset + Factor × ln(odds)，odds 是 good:bad。Factor = PDO / ln2 = 20 / 0.6931 = 28.8539，每加 20 分 odds 翻倍。Offset = 600 − 28.8539 × ln20 = 513.5614。LR 给的是 ln(P(bad)/P(good)) = b0 + Σ bᵢ·WOEᵢ，取负号就是 ln(odds)，所以基础分 = Offset − Factor × b0，每个箱的分数 = −Factor × bᵢ × WOEᵢ，取整。

*出处：* `scorecard/scorecard.py`，报告 4.1。
*数字：* b0 = −1.8355，基础分 566.52 → 567，分数范围 506–648，整数分数的 AUC test 0.6626 / OOT 0.6736。

### 8. cut-off 怎么定？通过率和坏账率怎么权衡？利润最大和坏账率最低的 cut-off 为什么不同？

报告给两个主结论：一是坏账率上限（默认 10%）下通过率最高的 cut-off，二是目标通过率（默认 70%）下的坏账率和净现金；无约束的利润曲线放旁边做参照。利润用实际回款算，名义值不折现。坏账率最低永远在最严的 cut-off，但每多放一档，好客户的利息还在进账，只要边际那档的利息盖得住损失，总额就继续涨。Lending Club 做了 risk-based pricing，各分数段每笔净现金差不多平，总利润接近全批时最大，所以评分卡在这里的价值是约束下的准入和分层定价，不是靠拒绝赚钱。

*出处：* `scorecard/strategy.py` 的 constrained_cutoffs / profit_optimum，报告 5.2–5.4。
*数字（OOT）：* bad rate ≤ 10% → score ≥ 564，通过 63.8%，bad rate 9.93%；70% → score ≥ 561（实际 69.86%），bad rate 10.58%（整体 14.71%），边际一档 16.64%。总净现金在 96.70% 通过时最大（1.292 亿 vs 全批 1.282 亿）；每笔净现金在 score ≥ 598 / 10.24% 时最大（1,212 / 笔 vs 全批 790）。含平台评级时 10% 上限下可通过 69.69%（score ≥ 560）。

### 9. swap set 怎么看？swap-in 的 bad rate 比 swap-out 高说明什么？

同一通过率下，模型批、基准拒的是 swap-in，模型拒、基准批的是 swap-out，两格人数一样多，bad rate 可以直接比。基准是平台 grade 从 A 往下批到同样的人数，边际那档随机、固定种子。swap-in 的 bad rate 低于 swap-out，说明在两边意见不同的客户上模型选得更好；反过来就是模型在最关键的地方输给了基准，要停下来查 leakage、客群变化，或者基准是不是用了模型不能用的信息。这里只用申请信息的卡小胜 grade，放进 sub_grade 以后优势明显。第 7 节把这项做成了自动检查。

*出处：* `scorecard/strategy.py` 的 baseline_order / swap_set，报告 5.5；第 7 节检查。
*数字（OOT，score ≥ 561，通过 69.9%）：* swap-in 22,419 笔 bad rate 18.53% vs swap-out 22,419 笔 19.25%；通过客群 bad rate 模型 10.58% vs grade 10.72%（−0.14 pp）。test：16.67% vs 17.58%，10.14% vs 10.33%（−0.19 pp）。含平台评级：OOT swap-in 15.83% vs swap-out 22.06%，通过客群 9.87% vs 10.69%（−0.82 pp）。

### 10. PSI 公式和 0.10 / 0.25 的由来？score PSI 稳定但某个特征 CSI 很高怎么处理？

PSI = Σ (actual% − expected%) × ln(actual% / expected%)，分段固定在训练样本上：分数用 train 的 10 等频段，特征用评分卡自己的分箱（含缺失箱），这就是 CSI；空段按 0.01% 处理。0.10 / 0.25 是行业惯例，不是统计检验。分数稳、特征不稳，说明客群在那个特征上动了但分数吸收掉了，要看是哪个箱在动。多数这种报警是数据可得性变了——某个征信字段从某年起才有值——所以这个项目在建模前就处理：筛选阶段用 train 内最早和最晚一年算同样的 CSI，超过 0.25 的剔除，样本起点也取在征信字段稳定之后。这样第 6 节报的都是真漂移。

*出处：* `scorecard/select.py` 的 time_stability_table，`scorecard/monitor.py`，报告 2.3b、6.1–6.2。
*数字：* 从 2012-01 起建样时该筛选剔除 15 个征信字段（如 num_tl_op_past_12m CSI 4.82，Missing 51.65% → 0%）；从 2013-01 起一个都不剔（最大 0.057，acc_open_past_24mths）。score PSI train→test 0.0002、train→OOT 0.0020；入模特征 CSI 全部 < 0.10（最高 percent_bc_gt_75 0.0250）。

### 11. OOT 和普通 hold-out 的区别？为什么按时间切？

随机 hold-out 回答的是"对和训练集同类的贷款好不好用"，OOT 回答的是"对下一个时期的贷款好不好用"，上线面对的是后者。时间会带来产品结构和宏观的变化，OOT 的指标才是该报的数。这里最后 6 个放款月做 OOT，之前的按标签分层随机切 train / test。只建 36 期的卡也是这个原因：60 期贷款在 OOT 窗口里根本到不了期，混着建的卡在时间外看到的是另一个客群。没有日期的数据集退回分层 hold-out，报告会注明（UCI）。

*出处：* `scorecard/split.py`，报告 1.8；vintage 见 6.3。
*数字：* test AUC 0.6624 vs OOT 0.6737（KS 0.2319 vs 0.2491）；OOT 是 2015-07 … 2015-12 的 162,236 笔。vintage：2013Q1 第 12 个月累计违约 4.32%、第 36 个月 12.54%；2015Q4 分别是 5.48% 和 14.71%。

### 12. 含平台评级和不含的两套模型差多少？实际业务里该不该用？

两套并排跑。不含的只用申请和征信信息；含的话 sub_grade 以最高 IV 进模，grade、int_rate、installment 因为和它高度相关被过滤掉。提升真实但不大——test 和 OOT 都约 +0.02 AUC，70% 通过率下 bad rate 低 0.7 pp——因为 grade 本来就是用同一批征信数据加定价信息做出来的。用不用看决策归谁：平台自己可以用，那是它自己的模型，而且 swap set 显示合起来比单用 grade 强；第三方机构不该用，等于在建模别人的模型，而且没有这个字段就打不了分。

*出处：* `configs/lendingclub.yaml` 的 use_platform_rating，报告第 3 节两套并排、5.6。
*数字：* LR AUC / KS test 0.6624 / 0.2319 → 0.6816 / 0.2614，OOT 0.6737 / 0.2491 → 0.6981 / 0.2884；CV AUC 0.6636 ± 0.0030 → 0.6838 ± 0.0021；sub_grade IV 0.3378。70% 通过率下的 bad rate：test 10.14% → 9.60%（−0.54 pp），OOT 10.58% → 9.87%（−0.71 pp）；OOT 50% 时 8.44% → 7.54%。

### 13. 换一个数据集要改什么？

一个 adapter 加一个 yaml。adapter 把原始数据变成标准数据帧——target、特征列、可选的 issue_date / loan_amount / net_cash / event_date——再加样本定义日志和字段审计；引擎里没有任何数据集的列名。普通带标签的 CSV 连代码都不用写，generic adapter 从 config 读 target_col 和 date_col。UCI 信用卡数据就是证明：300 行 adapter（下载、两处编码清洗、11 个行为特征、受保护属性不入模）加 30 行 yaml，七节全部出来，缺什么就退什么——没日期用分层 hold-out，没回款跳过利润曲线，没评级用随机基准做 swap set。

*出处：* `scorecard/adapters/base.py`、`scorecard/adapters/uci.py`、`configs/uci.yaml`、`examples/uci/`。
*数字（UCI）：* 30,000 名客户，bad rate 22.12%，32 个候选入模 17 个；LR AUC / KS train 0.7755 / 0.4176，test 0.7667 / 0.4212，hold-out 0.7641 / 0.4020；bad rate ≤ 10% 时 test 可通过 51.75%（score ≥ 568）；全程不到 20 秒。

### 14. agent 调用时怎么防止它乱跑？

SKILL.md 写了输入、步骤和护栏，但护栏是 CLI 强制的，不靠提示词。原数据从不修改；`--dry-run` 只加载数据、打印样本定义影响表就停，agent 必须先让用户看到每条规则删了多少行；样本 bad rate 不在 1–40% 就以退出码 2 停下，除非显式传 `--allow-any-bad-rate`，这一招专门抓 positive_label 写错；空样本也停；保留列永远做不了特征；第 7 节的判定印在报告里，agent 只能原样转述，不能偷偷放宽阈值。每次运行记录 config hash、数据文件、行数和 git commit，做过什么都能复现。

*出处：* `SKILL.md`，`scorecard/cli.py`，`scorecard/pipeline.py` 的 check_bad_rate，`tests/test_phase2.py` 的护栏测试。
*数字：* 护栏测试故意把合成数据的正例标签写反，bad rate 约 82%，退出码 2；标签写对时 dry run 退出码 0，只写出 sample_definition.csv、不出报告。
