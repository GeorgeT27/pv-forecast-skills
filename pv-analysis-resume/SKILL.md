---
name: pv-analysis-resume
description: 光伏功率预测结果分析的续跑入口——此前已用 pv-result-analysis 跑过（metric 指标 Excel 已生成、analysis_config.json 已存在），本次按既有产物判定已完成到哪个阶段，从第一个未完成阶段进入，跳过前面已做的步骤。覆盖两种续跑：①从可视化续跑（相关性热力图、逐样本 RMSE、天气分型对比等事实提取）；②**现象/事实已看完，直达 Stage 4 深度归因**——结合电站背景（station.md/seasonality.md）与模型设计（models.md）解释"为什么 X 月变差/为什么某模型在突变日掉得多/为什么某模型多云天更好"。③**基于已有结论写面向主管的 CONCLUSION.md**（executive summary，叙述为主、少表格）。当用户说"指标已经算过了""接着上次分析""直接画图/做相关性/数据分析"，或"现象/事实已经看过了""做深度分析""结合电站和模型解释为什么""深入归因某个现象""进 Stage 4"，或"给主管写个总结/汇报""写 executive summary/结论报告"时，务必使用本技能而不是从头走 pv-result-analysis。
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
4. **先读既有结论**：`FINDINGS.md`（如存在）+ `figures/**/ANALYSIS.md`。本次要回答的
   问题若已有结论，直接引用并问用户是否需要更新，而不是重做一遍——这是续跑的最大价值。
   注意 `FINDINGS.md` 是模型手写的软产物、可能缺失，此时结论仍在各图的 `ANALYSIS.md` 里
   （见 Step 2 路径 B 的现象重建优先级）。

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

**必须重算的**：逐样本误差矩阵（errs/rmses）不落盘，每次会话进入分析前都要跑一遍主技能
Step 3 的 `python <skill>/scripts/run_analysis.py --range <范围> --figs <图号>`（几秒钟的事），
质检可省略。

## Step 2：进入分析

从 Step 0/1 判定出的**第一个未完成阶段**进入。两条常见路径：

### 路径 A：从可视化/事实提取续跑（Stage 2–3）

按主技能 SKILL.md 的 **Step 3** 执行：跑 `run_analysis.py`、按问题选图（月度诊断必画
#1/#2/#4/#8）、每图先读 stats.json 整条曲线 → Read PNG 回看 → 对号 `references/figure-diagnostics.md`
形态 → 结论、沉淀到 `figures/<电站>/<范围>/ANALYSIS.md` 与 `FINDINGS.md`。到 Stage 3 结束停下报现象清单。

### 路径 B：现象已看完，直达 Stage 4 深归因

用户说"现象/事实已经看过了""结合电站和模型解释为什么""深入归因某个现象"时走这条。

**现象清单从哪来（`FINDINGS.md` 不是唯一来源）**：`FINDINGS.md` 是模型手写的软产物，
不是脚本自动生成的——上一次跑（尤其在别的机器上）很可能只写了每张图旁的 `ANALYSIS.md`
和 `stats.json`，没落 `FINDINGS.md`。所以进 Stage 4 的现象清单**按下面优先级重建**：

1. 有 `FINDINGS.md` 且含状态="现象"的条目 → 直接用。
2. 没有 FINDINGS，但 `figures/<电站>/<范围>/ANALYSIS.md` 存在 → **从 ANALYSIS.md
   （每图的文字结论）+ 同目录 `.stats.json`（精确数字）汇总出现象清单**，并把这份清单
   **回填进 `FINDINGS.md`**（状态标"现象"、带数字与图链接），让后续会话稳定可续。
3. 连 ANALYSIS.md 都没有，只有 PNG + `.stats.json` → 逐张 Read PNG + 读 stats.json，
   由本会话现读现总结出现象清单，同样回填 FINDINGS.md。
4. 图和 stats.json 都没有 → 无既有事实可归因，**退回路径 A 先跑 Stage 2–3**。

**进入前提（无论现象来自哪一级都要满足）**：现象引用的图的 PNG + `.stats.json` 仍在
`figures/` 下可读——Stage 4 要复核这些证据数字与形态，不是另起炉灶凭空编故事。

**直达 Stage 4 读什么、做什么**（Playbook 全文见 `references/playbooks.md`）：
1. 按上面优先级拿到现象清单；**本次归因直接依据的那几张图，Read PNG 看一遍**
   （本会话没画过这些图，只读 stats.json 数字会漏掉散点弯曲、坏天聚集等形状证据），
   其余图读 stats.json 即可——**这些图已在，通常无需重画**。
2. `ls references/` 扫全，读齐 `models.md`（模型架构/特征差异）、`station.md`、
   `seasonality.md`（该站该月气候机制）、`event-log.md`（跨月归因前必查）、
   `hypotheses.md`（认领对应 H-* 假设 ID）。
3. 按现象类型走对应 Playbook（`references/playbooks.md`）：月度变差→Playbook A，模型间强弱→Playbook B。
4. 结论落 `FINDINGS.md` 前**必过反驳门七条 + 稳健性门槛**（`references/analysis-discipline.md`），
   把现象条目状态从"现象"升级为"假设/已证实"，并在 ANALYSIS.md 留反驳门记录。
5. 写 `CONCLUSION.md`（面向主管，写法见 `references/playbooks.md`），
   再把图 + 数字 + 结论展示给用户。

**只要主管总结（不重做归因）**：用户说"给主管写个总结/汇报""写 executive summary"、
而 `FINDINGS.md`（或 ANALYSIS.md）里已有站得住的结论时——直接综合已成立结论写
`CONCLUSION.md`，不必重跑 Playbook。写法严格按 `references/playbooks.md`：叙述优先、
表格最多一张、方法论机器不进正文、结尾给建议。

**Stage 4 何时仍需重算**：某条 Playbook 步骤要用一张 Stage 3 没画过的图（如现象只登记了
#8，但归因需要 #5 分时效对比）——这时跑 `run_analysis.py` **重算误差矩阵**
（errs/rmses 不落盘）补画那一张，质检行可省略。已有的图不重画。

### 通用
- 产物写回**同一** figures/ 目录结构；将要覆盖同名旧图时，先 Read 旧图和旧结论，
  确认是刷新而不是误覆盖不同范围的分析。
- 环境依赖同主技能：缺包先 `pip install -r <仓库根>/requirements.txt`。
