---
name: pv-analysis-resume
description: 光伏功率预测结果分析的续跑入口——此前已用 pv-result-analysis 跑过（metric 指标 Excel 已生成、analysis_config.json 已存在），本次跳过路径收集与 metric.py 调用，直接进入可视化与归因分析（相关性热力图、逐样本 RMSE、天气分型对比等）。当用户说"指标已经算过了""之前跑过这个分析""接着上次分析""直接画图/做相关性/数据分析"时，务必使用本技能而不是从头走 pv-result-analysis。
---

# 续跑：直达可视化与归因分析

前提：工作目录中此前已完成主技能 pv-result-analysis 的 Step 1（路径+质检）与 Step 2（metric.py 指标）。
本技能只做一件事——**验证既有产物、决定哪些步骤可以跳过，然后进入主技能 Step 3**。
分析逻辑、图谱定义、结论纪律全部沿用主技能，不在此重复：

主技能 = `/Users/tqa946816/Documents/华为/光伏预测/结果分析skill/pv-result-analysis/SKILL.md`

## Step 0：定位并验证既有产物

1. 找 `analysis_config.json`（先当前工作目录，找不到问用户上次分析在哪个目录做的）。
   **没有 config → 说明此前并没有完整跑过，回主技能走完整流程**，不要凭记忆猜路径。
2. `ls` 验证 config 里的 parquet 路径仍然存在且可读——文件被移动/更新过则先向用户确认，
   数据换了版本的话质检不能跳（旧质检结论对新数据无效）。
3. 盘点既有产物并把清单报给用户：`suspect_days.csv`、`weather_class.csv`、
   `figures/<电站>/**`（PNG + stats.json + ANALYSIS.md）、`FINDINGS.md`、metric 指标 Excel。
4. **先读 `FINDINGS.md`（如存在）**：本次要回答的问题若已有结论，直接引用并问用户是否需要
   更新，而不是重做一遍——这是续跑的最大价值。

## Step 1：跳过规则

| 既有产物 | 可跳过的步骤 | 前提 |
|---------|-------------|------|
| `analysis_config.json` | 主技能 Step 1 的路径收集 | 路径验证通过 |
| `suspect_days.csv` | 数据质检 | parquet 未换版本 |
| metric 指标 Excel | 主技能 Step 2（metric.py 调用） | 图#3 直接读现成 Excel |
| `weather_class.csv` | 天气分型重算 | 直接 `pd.read_csv` 复用 |
| `figures/**/*.stats.json` + `ANALYSIS.md` | 对应图的重画 | 先 Read 旧图与旧结论，够用就引用 |

主技能现在按**四个阶段**推进（见主技能"执行流程：四个阶段"一节）。续跑先按既有产物
判定已完成到哪个阶段，**从第一个未完成的阶段进入**：指标 Excel 在 → Stage 1 已完成；
`02_error_corr.png` 在 → Stage 2 已完成；FINDINGS.md 有"现象"条目 → Stage 3 已完成，
可直接进 Stage 4 深归因。跳过规则与阶段一一对应，上表就是判定依据。

**不可跳过的（结论纪律，不是计算步骤）**：稳健性门槛（Wilcoxon + 剔坏天）、反驳门、
结论必须引用 `references/hypotheses.md` 的假设 ID、分组样本量披露；Stage 3→4 的
强制停顿点（把现象清单报用户、由用户点名深挖项）同样不跳。

**必须重算的**：逐样本误差矩阵（errs/rmses）不落盘，每次会话进入分析前都要按主技能
Step 3 的"标准命令序列"重算一遍（几秒钟的事）；命令序列中的质检行可以省略。

## Step 2：进入分析

按主技能 SKILL.md 的 **Step 3 + 诊断 Playbook** 执行：标准命令序列、按问题选图
（月度诊断必画 #1/#2/#4/#8）、每图 stats.json → PNG 回看 → 结论、沉淀到
`figures/<电站>/<范围>/ANALYSIS.md` 与 `FINDINGS.md`。

- 产物写回**同一** figures/ 目录结构；将要覆盖同名旧图时，先 Read 旧图和旧结论，
  确认是刷新而不是误覆盖不同范围的分析。
- 环境依赖同主技能：缺包先 `pip install -r <仓库根>/requirements.txt`。
