---
id: result-eval
name: 预测结果评估与归因
goal: 评估一次预测结果（指标口径可配，默认 rmse_192），画标准图集，把指标变化归因到时段/单元/输入
produces:
  id: eval_report
  manifest: gate_reports/conclusion_gate.json
  marker_files: [CONCLUSION.md]
upstream:
  - product: setup
    required: true
  - product: model_profile
    required: false
  - product: chart_sweep
    required: false
  - product: metric_table
    required: false
materials:
  required: [predict, truth]
  optional: [features, train_y, model_code, training_log, experiment_config]
stages:
  - id: 0
    name: 路径与质检（数据与指标前置）
    done_when:
      artifacts: ["suspect_days.csv"]
    prereqs:
      - desc: setup 产物就绪
        check: "product:setup"
      - desc: 口径问题已答
        check: "question:metric-caliber"
  - id: 1
    name: 指标计算（口径 × 模型集 → Excel）
    done_when:
      artifacts: ["*.xlsx"]
    prereqs:
      - desc: 质检已过
        check: "stage:0"
  - id: 2
    name: 相关性与画图（误差矩阵 + 标准图集）
    done_when:
      artifacts: ["charts/*.json", "INDEX.md"]
    prereqs:
      - desc: 指标已算
        check: "stage:1"
    charts: [error-breakdown, intraday-profile, worst-points,
             rolling-stability, cross-dim-stability]
  - id: 3
    name: 事实提取（现象清单，停顿点）
    done_when:
      findings_marker: "现象"
    prereqs:
      - desc: 图已画
        check: "stage:2"
    pause_after: true
  - id: 4
    name: 深归因与结论
    done_when:
      artifacts: ["CONCLUSION.md", "gate_reports/conclusion_gate.json"]
    prereqs:
      - desc: 用户已点名待深挖现象
        check: "stage:3"
    subagent_ok: false
questions:
  - id: metric-caliber
    stage: 0
    ask: "考核口径是什么？（默认 rmse_192=每行全部 192 个 horizon 点的 RMSE）"
    why: "口径不同结论可反转"
    options: ["rmse_192（默认）", "指定子段", "自定义公式"]
    default: "rmse_192"
---

# result-eval：预测结果评估与归因

本 playbook 对一次已完成的预测（`predict` 材料）与真值（`truth` 材料）做定量评估与归因，输出依次是指标表、标准图集、现象清单、最终结论。续跑/直达由引擎 orient 承接（不再有专属的 run_orient.py）：orient 每次进入自动核对已有产物、定位第一个未完成阶段，支持 `--goto` 直达指定阶段。

## 1. 问题框定与首要陷阱

- **口径先问、口径贯穿全程**。本 playbook 不内置固定的多口径体系——考核用哪种取点/聚合规则由 `metric-caliber` 问题的答案决定，默认 `rmse_192`（每行全部 192 个 horizon 点整体算一个 RMSE）。若用户的专项口径同时存在"先按天/按单元聚合再平均"和"整段直接合并算"两种聚合方式，两者数值天然不同（合并算给长误差段更大权重），不要误判为 bug。专项口径的精确定义（取点索引、聚合方式）落在 project-context 或用户提供的评估脚本里，不写死在本 playbook。
- **模型集不预设专名**。分析对象是 intake 阶段从 `predict` 材料盘点出的实际模型/预测列集合，盘点到几个就分析几个，不假定固定的模型编号或数量。声明 `needs_models: 2` 的跨模型对比图在单模型数据上自动跳过，跳过不算失败。
- **滚动窗口重叠陷阱**。若预测以"每行一个窗口、相邻行按固定步长滚动"的形式组织（相邻行窗口高度重叠），**做任何分布统计（直方图、分位数、KS 检验）之前，必须先把滚动窗口重建为物理上连续的时间序列**，否则同一物理时刻的点会被重复统计几百次。是否滚动窗口结构、重叠了多少步，属于 Stage 0 对齐时要确认的 schema 事实，不能凭经验假设；两者在 setup 适配时已确认并写入 alignment_report——本 playbook 直接读那份报告，不重新猜。
- **训练数据是可选输入，只用于漂移诊断**。`train_y` 不参与指标计算，唯一用途是给 `train-test-drift` 这类漂移图提供基准分布（回答"预测单元是不是落在训练数据没覆盖的分布里"）。没有 `train_y` 就跳过漂移类图，其余指标与图谱照常。
- **事实与归因物理隔离**。Stage 3 只写"看到了什么"：现象、数字、稳健性检验结果，**禁止机制语言**。Stage 4 才允许回答"为什么"，且必须过结论三道门（细则见本目录 `references/analysis-discipline.md`，引擎侧对应 `references/mechanisms.md`）。

## 2. 逐阶段菜谱

### Stage 0：质检（消费 setup 长表）

输入：setup 产物的规范长表 `<setup>/predictions.csv`。它的位置和模型清单由 orient 注入的 manifest 摘要给出，不自行摸文件。

菜谱：

1. **对规范长表跑质检脚本**。复用 `<本 playbook 目录>/scripts/run_quality_check.py`。脚本做四件事：
   - schema 侦察：数据列名与脚本顶部的 CONFIG 对不上时，只改 CONFIG，不改脚本逻辑；
   - 基础完整性检查：重复时间戳、时间网格缺口、长时间常值段；
   - 滚动窗口一致性抽查：同一物理时刻在不同行里的取值应当一致——若不一致，取点口径全不可信，必须停下来报告用户；
   - 重建连续序列后扫描可疑日，写出 `suspect_days.csv`。
2. **可疑日二分处理**。两类的处理方式相反，不可一律当异常"修掉"：
   - "错误"：录入或传感器故障——从统计中剔除，并记录剔除了哪些；
   - "事件"：限电、停机、极端天气——数据保留，写进 project-context 的事件台账，归因时显式考虑。

done：`suspect_days.csv` 落盘。

### Stage 1：指标计算

输入：Stage 0 质检通过的 predict/truth；`metric-caliber` 问题的答案。

先查捷径：若上游 metric_table 产物状态为 built/linked，且其 `metrics_summary.json` 里的 `caliber` 字段与本次 `metric-caliber` 答案一致，直接复用它的汇总值作为指标表，不重算。口径不一致则视同该产物 absent：照常自算，并在 FINDINGS 里注明"存在另一口径的指标表"。

菜谱：按选定口径计算每个模型的指标（RMSE/MAE/ACC 等，具体算哪些由用户口径定义决定），产出整个模型集的指标表（Excel 或等价表格）。
**模型集来自 intake 对 predict 材料的盘点**——盘点到几个预测列/模型就出几份表，不假定固定数量。

若用户提供了外部评估脚本，按下面的顺序用它：

1. 首次运行先确认调用签名：构造参数是什么、预测数据怎么传进去、输出写到哪。
2. 跑通后把确切的调用方式固化下来，本次会话内直接复用。
3. 做一次口径对账（验证对取点/聚合规则的理解没有跑偏）：任选一段数据自己算一遍，与脚本输出比对，相对差 <1% 视为一致；通过之后可跳过。

指标计算复用 `<本 playbook 目录>/scripts/run_analysis.py` 中与指标相关的部分，或用户外部脚本；不要现写 pandas 重复实现。

done：`*.xlsx`（或用户口径约定的等价指标表）落盘。

### Stage 2：相关性与画图

输入：Stage 1 产出的指标表；对齐后的 predict/truth（若有 features/train_y 也一并用上）。

菜谱：**不写图代码**。frontmatter `charts:` 声明的图全部用 chartbook 预写脚本画（engine-core chartbook 对该规则天然豁免）。orient 已按材料盘点结果标好每张图可画还是跳过。命令模板：

```bash
python3 <ENGINE>/chartbook/scripts/chart_<蛇形id>.py \
  --pred <setup>/predictions.csv --out-dir charts/ [各图特有参数]
```

复用规则：**chart_sweep 产物状态为 built/linked 时**，与本阶段声明重叠的图直接拿它的 charts/*.json 来判读，不重画；只补画本组缺的图。

画完跑 `<ENGINE>/scripts/build_index.py` 生成 `INDEX.md`（阶段闸的产物判据之一）。

每张图落盘两个文件：PNG 与同名 `.stats.json`。
**PNG 只给人看；分析一律读 stats.json，不 Read 图。**
stats.json 已做到自足——图上一切可判读的数字都写在里面。判读流程固定三步：

1. 读 stats.json 里的完整曲线/数字，判断走势；
2. 对号本目录 `references/figure-diagnostics.md` 的形态判读条目；
3. 结合 project-context 背景写结论。

全程无需读图。

旧版画图脚本（`<本 playbook 目录>/scripts/plots.py` + `<本 playbook 目录>/scripts/run_analysis.py`）可作参考实现，或补画 chartbook 尚未覆盖的图形；chartbook 已覆盖的图不要再用旧脚本重复画，避免两套产物打架。分布漂移诊断（需要 `train_y`）用 `<本 playbook 目录>/scripts/run_drift.py`：跨数据集 pooled 对比与逐条对比；逐条对比在缺训练集时自动跳过，指标与其余图谱照常。

done：`charts/*.json`（至少一张）+ `INDEX.md` 落盘。

### Stage 3：事实提取（现象清单，停顿点）

输入：Stage 2 的图与指标表。

菜谱：逐图判读 stats.json，加上指标表，把观察到的现象写成清单落进 `FINDINGS.md`，状态一律填"现象"。每条现象 = 一句现象陈述 + 支撑数字 + 图/表链接。
**禁止出现机制语言**——不许写"因为模型的 XX 机制…"这类因果解释，那是 Stage 4 的事。

done：`FINDINGS.md` 含"现象"标记 → **停下来**：向用户汇报现象清单，问哪几条要进 Stage 4 深挖（`pause_after: true`，全流程唯一强制停顿点）。

### Stage 4：深归因与结论

输入：用户点名的现象子集；Stage 0-2 的全部产物；project-context、模型档案等背景材料。

菜谱：两类高频归因问题走固定流程，详见本目录 `references/playbooks.md`。那份文档尚未去域名化，正文仍用原技能的图号（#1、#8 之类）叙述；读它时，把图号对照本 playbook frontmatter 的 `charts:` 列表换算成 chartbook recipe id。

两类问题：

- **"为什么某段变差了？"**：查台账/事件 → 定位口径/时段 → 定位坏样本 → 占比分解（区分"难例构成变多"与"能力真退化"）→ 分布漂移检查（有 train_y 时）→ 过反驳门写结论。
- **"为什么模型 A 比 B 好（差）？"**：先看两模型误差的同质化程度 → 分组条件对比 → 定位差距集中的时间/时效 → 对照模型架构档案验证机制 → 过反驳门。架构档案指 `model_profile` 上游产物——`model_code` 材料 present 时经 model-audit 提供。

下结论前必过**结论三道门**：稳健性门槛 → 假设登记 → 反驳门。细则见本目录 `references/analysis-discipline.md`。机制结论必须引用假设登记文档里的一条 H-ID。

`CONCLUSION.md` 是 Stage 4 收尾写的管理层报告：把 FINDINGS 里已证实的结论**翻译**成管理层语言。写法要求：叙述优先；全文表格最多 1 张；方法论机器（检验名、假设编号等）不进正文；金字塔结构——先结论、后建议。模板见引擎 `references/conclusion-reporting.md`。

done：`CONCLUSION.md` 落盘。`subagent_ok: false`：深归因涉及结论三道门与反驳门，需要跨全部结果的全局视角，这一阶段不外包给子代理。

## 3. 证据升级规则

本 playbook 只有一条证据线（frontmatter 未声明 `evidence_lines`，无需 `upgrade_rule`）。现象升级到假设、假设升级到已证实，每一步都走结论三道门（稳健性门槛 → 假设登记 → 反驳门），细则见 `references/analysis-discipline.md`。

反驳门列出七类替代解释：事件、样本量、构成变化、分布外、上游原料变化、共享组件混淆、外部事件。必须逐条排除：每条要么给出排除证据，要么显式标"未排除"并把结论降级。

## 4. 停顿点与汇报

Stage 3 完成是唯一强制停顿点：向用户汇报现象清单（按图/表分组），请用户点名哪几条进 Stage 4 深挖。Stage 4 收尾时，把 `CONCLUSION.md` 的内容（含关键数字）直接展示给用户，不能只报一个文件路径。

## 5. subagent 拆分建议

- Stage 2 画图与 Stage 3 逐图事实提取天然可并发：一个图组或一个 range 派一个 subagent，让图像和逐图 stats.json 都不进主 agent 的上下文（最大的 token 收益）。
- Stage 0/1 的质检与指标计算可交给一个子代理串行跑：只产出表格、不占图像上下文，并行收益有限。
- Stage 4 深归因全程由主 agent 亲自做：结论三道门 + 反驳门需要跨结果的全局判断，且 `subagent_ok: false`。

## 6. 结论模板与本 playbook 特有反驳门条目

结论模板见引擎 `references/conclusion-reporting.md`。除通用反驳门外，本 playbook 另有三条特有条目：

- **口径混淆**：结论是否在同一考核口径下成立？换一种口径（比如从"按天平均"换成"整段合并"）后方向是否翻转？翻转则原结论降级为"仅在 XX 口径下成立"。
- **构成 vs 能力**：某段/某模型变差，到底是"难例（坏天气/异常段）占比升高"，还是"同类样本内的能力真的退化"？没有用分组条件对比把两者拆开 → 该条视为未排除。
- **分布外/漂移**：预测单元是否落在训练数据没覆盖的分布区间？有 `train_y` 时用漂移图核验；没有则显式标"未排除，缺训练侧基准"。

## 7. 材料降级说明

- `predict`/`truth` 缺：不可做——两者是评估的最小闭环，没有降级路径。
- `features` 缺：`feature-error-conditional`/`feature-trend-overlay`/`y-vs-feature-mapping` 三张输入侧图跳过；Stage 4 反驳门里的"输入原料变化"条目降级为"未排除，缺特征侧证据"。
- `train_y` 缺：`train-test-drift` 跳过；Stage 4 的分布外/漂移反驳门条目降级为"未排除"。
- `model_code` 缺：`model_profile` 产物保持 absent/declined 状态；Stage 4 的模型对比归因只能停在现象/统计层面，机制层面的"为什么"要标注"缺代码锚定的架构档案，暂不可深究"。
- `training_log`/`experiment_config` 缺：不阻塞主线，只是核验训练窗口/超参相关假设时少一路交叉验证来源；缺席情况记入 `open-questions.md`。

## 8. chartbook 覆盖声明

声明进 Stage 2 charts 的五张图（月度/时段归因组）：error-breakdown、intraday-profile、worst-points、rolling-stability、cross-dim-stability。

以下图默认不画，需要时经图表选择门加画，或复用 chart_sweep 产物：

- true-vs-pred-scatter / horizon-degradation：单结果广谱体检图，chart_sweep 产物已覆盖，按需复用。
- train-test-drift：漂移专项图（需 train_y），归 Stage 4 深挖时按需加画。
- feature-error-conditional / feature-trend-overlay / y-vs-feature-mapping：输入侧归因三件套（需 features），Stage 4 点名输入侧假设时加画。
- model-error-correlation / oracle-gap / worst-slice-compare /model-rank-significance / baseline-skill：多模型对比定位图，present ≥2 模型时可加画。
- global-attribution / local-waterfall / lookback-decay：需要 serving_api 材料，结构上不适用于本 playbook。
- bad-window-clustering / good-bad-contrast / error-acf / pp-calibration /theil-decomposition / time-shift-diagnosis / horizon-error-quantiles：误差结构的补充切面，属于可加画池。

## 9. 运行后回顾

每次实跑暴露的问题写回对应位置：

- 脚本 bug、列名对不上 → 改 `<本 playbook 目录>/scripts/`；
- 指令歧义、缺步骤 → 改本文件；
- 确认的新项目事实 → 补 project-context；
- 方法类知识 → 补 `<本 playbook 目录>/references/`。
