---
name: pv-analysis-resume
description: 光伏功率预测结果分析的续跑入口——此前已用 pv-result-analysis 跑过（metric 指标 Excel 已生成、analysis_config.json 已存在），本次按既有产物判定已完成到哪个阶段，从第一个未完成阶段进入，跳过前面已做的步骤。覆盖两种续跑：①从可视化续跑（相关性热力图、逐样本 RMSE、天气分型对比等事实提取）；②**现象/事实已看完，直达 Stage 4 深度归因**——结合电站背景（station.md/seasonality.md）与模型设计（models.md）解释"为什么 X 月变差/为什么某模型在突变日掉得多/为什么某模型多云天更好"。当用户说"指标已经算过了""接着上次分析""直接画图/做相关性/数据分析"，或"现象/事实已经看过了""做深度分析""结合电站和模型解释为什么""深入归因某个现象""进 Stage 4"时，务必使用本技能而不是从头走 pv-result-analysis。
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

从 Step 0/1 判定出的**第一个未完成阶段**进入。两条常见路径：

### 路径 A：从可视化/事实提取续跑（Stage 2–3）

按主技能 SKILL.md 的 **Step 3** 执行：标准命令序列、按问题选图（月度诊断必画
#1/#2/#4/#8）、每图 stats.json → PNG 回看 → 结论、沉淀到
`figures/<电站>/<范围>/ANALYSIS.md` 与 `FINDINGS.md`。到 Stage 3 结束停下报现象清单。

### 路径 B：现象已看完，直达 Stage 4 深归因

用户说"现象/事实已经看过了""结合电站和模型解释为什么""深入归因某个现象"时走这条。

**进入前提（必须核对，不满足则退回路径 A 先补 Stage 3）**：
- `FINDINGS.md` 里确有状态="现象"的条目，且每条带**具体数字 + 图链接**（Stage 4 是给
  这些现象找原因，没有登记在案的现象就无从归因，也容易变成凭空编故事）。
- 现象引用的图（如 #2/#4/#8）的 PNG + `.stats.json` 仍在 `figures/` 下可读——
  Stage 4 要复核这些证据数字，不是另起炉灶。

**直达 Stage 4 读什么、做什么**（对应主技能"诊断 Playbook"一节）：
1. 先读 `FINDINGS.md` 现象条目 + 它们引用的图的 `.stats.json`（拿精确数字），
   必要时 Read PNG 复核形态——**这些图已在，通常无需重画**。
2. `ls references/` 扫全，读齐 `models.md`（模型架构/特征差异）、`station.md`、
   `seasonality.md`（该站该月气候机制）、`event-log.md`（跨月归因前必查）、
   `hypotheses.md`（认领对应 H-* 假设 ID）。
3. 按现象类型走对应 Playbook：月度变差→Playbook A，模型间强弱→Playbook B。
4. 结论落 `FINDINGS.md` 前**必过反驳门七条 + 稳健性门槛**（见主技能输出规范），
   把现象条目状态从"现象"升级为"假设/已证实"，并在 ANALYSIS.md 留反驳门记录。
5. 展示图 + 数字 + 结论给用户。

**Stage 4 何时仍需重算**：某条 Playbook 步骤要用一张 Stage 3 没画过的图（如现象只登记了
#8，但归因需要 #5 分时效对比）——这时按主技能 Step 3 标准命令序列**重算误差矩阵**
（errs/rmses 不落盘）补画那一张，质检行可省略。已有的图不重画。

### 通用
- 产物写回**同一** figures/ 目录结构；将要覆盖同名旧图时，先 Read 旧图和旧结论，
  确认是刷新而不是误覆盖不同范围的分析。
- 环境依赖同主技能：缺包先 `pip install -r <仓库根>/requirements.txt`。
