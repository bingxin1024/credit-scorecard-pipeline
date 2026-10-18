# credit-scorecard-pipeline（中文说明）

把"对一份数据做一次评分卡分析"变成"给任何一份带违约标签的贷款数据，自动跑完
样本定义 → 分箱 → 建模 → 评分卡 → 策略 → 监控，并交出一份固定结构报告"的工具。
Python 包 + CLI（Phase 3 加 SKILL.md 供 agent 调用）。

```
样本定义 → 数据体检 → 单调 WOE 分箱 → IV / 相关性筛选 → LR 评分卡 + GBDT challenger
→ PDO 换算 → cut-off / swap set / 利润（Phase 2）→ PSI / CSI / vintage（Phase 2）
```

主数据集：Lending Club 2007–2018Q4 accepted loans（226 万原始行，151 列）。
引擎不认识任何数据集特定的列名，数据集知识只在 `scorecard/adapters/` 和 `configs/` 里；换数据集 = 一个 adapter + 一个 yaml。

Lending Club 的示例报告在 [`examples/lendingclub/`](examples/lendingclub/)（`report.html` 单文件自包含；`report.md` 同内容）。

## 快速开始

```bash
python -m venv .venv && .venv/Scripts/activate
pip install -e ".[dev]" toad
pytest -q && ruff check .

python -m scorecard run --config configs/synthetic.yaml                      # 合成数据，10 秒
python -m scorecard run --config configs/lendingclub.yaml                    # 全量（数据放 data/raw/）
python -m scorecard run --config configs/lendingclub.yaml --sample-frac 0.1  # 随机 10% 试跑，约 1 分钟
```

输出在 `outputs/<dataset>/`：`report.html`、`report.md`、`figures/`，以及报告背后的全部表格（`scorecard.csv`、`scorecard_model.json`、`iv_table.csv`、`feature_selection.csv`、`model_metrics.csv`、`results.json`、`run_meta.json` …）。

## Lending Club 结果（Phase 1）

以下数字抄自 [`examples/lendingclub/report.md`](examples/lendingclub/report.md)；报告头部记录了产生这些数字的 config hash、数据文件、行数、git commit 和时间。

| 项目 | 数值 |
|---|---|
| 原始贷款 → 最终样本 | 2,260,701 → 633,767（2012-01 … 2015-12 放款、已到期） |
| bad rate（Charged Off / Default vs Fully Paid） | 14.85% |
| 切分 | 2012-01 … 2015-06 分层随机 train / test 70/30；OOT = 2015-07 … 2015-12（162,236 笔） |
| 候选特征 → 入模 | 99 → 20（缺失 > 50% → IV < 0.02 → \|ρ\| > 0.7 → 系数符号） |
| LR 评分卡 AUC / KS — train | 0.6733 / 0.2467 |
| LR 评分卡 AUC / KS — test | 0.6744 / 0.2513 |
| LR 评分卡 AUC / KS — OOT | 0.6750 / 0.2526 |
| GBDT challenger AUC — test / OOT | 0.6941 / 0.6959 |
| 5 折 CV AUC（每折重做分箱） | 0.6719 ± 0.0026 |
| 刻度 | PDO 20，600 分 ↔ 20:1 好坏比；分数范围 485–640 |
| 全量运行时间（解析已缓存） | 1.3 min |

评分卡刻意不用平台自己的评级（`grade`、`sub_grade`、`int_rate`、`installment`）；Phase 2 会把"含 / 不含平台评级"两套模型并排展示。

## 报告固定七节

1. 样本与数据概况 — 样本定义影响表、字段审计、缺失率 Top 20、bad rate 按季度、缺失率按年、切分
2. 分箱与 IV — IV 排名、筛选漏斗、单调性检查、Top 8 WOE 图、入模特征分箱表
3. 模型表现 — LR 系数（含 VIF）、train / test / OOT 的 AUC / KS / Gini、LR vs GBDT、5 折 CV、ROC / KS 图
4. 评分卡 — PDO 换算、评分卡表、分数分布
5. 策略分析 — Phase 2
6. 稳定性 — Phase 2
7. 自动检查与风险提示 — Phase 2

未实现的节显示"（本阶段未实现）"占位，不会消失。

## 换数据集

1. 在 `scorecard/adapters/` 写一个 adapter，返回标准数据帧（`target`、特征列、可选 `issue_date` / `loan_amount` / `net_cash`）和 `AdapterMeta`（样本定义 log、字段审计）。任意带标签列的 CSV 可直接用 `generic` adapter。
2. 在 `configs/` 加一个 `extends: default.yaml` 的 yaml。
3. `python -m scorecard run --config configs/<name>.yaml`。

决策记录见 `DECISIONS.md`，面试问答见 `FAQ.md`（英文）。MIT License。
