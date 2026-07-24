---
id: result-eval
name: 预测结果评估与归因
goal: 评估一次预测结果（指标口径可配，默认 rmse_192），画标准图集，把指标变化归因到时段/单元/输入
materials:
  required: [predict, truth]
  optional: [features, train_y, model_code, training_log, experiment_config]
stages:
  - id: 0
    name: 路径与质检（数据与指标前置）
    done_when:
      artifacts: ["suspect_days.csv"]
    prereqs:
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
             horizon-degradation, rolling-stability, true-vs-pred-scatter,
             train-test-drift, feature-error-conditional, feature-trend-overlay,
             y-vs-feature-mapping, cross-dim-stability]
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
contexts:
  - id: model-profile
    name: 模型架构档案
    workdir_key: modelmap_dir
    status_key: modelmap_status
    marker_files: [models.md]
    on_absent: ask
    provider_playbook: model-audit
    trigger_material: model_code
---

# result-eval：预测结果评估与归因

对一次已完成的预测结果（`predict` 材料）与真值（`truth` 材料）做指标计算与深入分析。
本 playbook 由专用技能 pv-result-analysis 的方法泛化而来——**续跑/直达能力已由引擎
orient 承接**（不再需要专属的 run_orient.py：orient 每次进入自动核对产物、定位第一个
未完成阶段、支持 `--goto`）。

## 1. 问题框定与首要陷阱

- **口径先问、口径贯穿全程**：本 playbook 不内置固定的多口径体系——考核用哪种聚合/取点
  规则由 `metric-caliber` 问题决定，默认 `rmse_192`（每行全部 192 个 horizon 点的
  RMSE）。若用户的专项口径涉及"先按天/单元聚合再平均"与"整段直接合并算"两种不同聚合
  方式，两者数值天然不同（合并算法给长误差段更大权重），不要误判为 bug；专项口径的精确
  定义（取点索引、聚合方式）落在 project-context 或用户提供的评估脚本里，不写死在本
  playbook。
- **模型集不预设专名**：分析对象是 intake 阶段 `predict` 材料盘点出来的实际模型/预测列
  集合（1 个或多个），不假定固定的模型编号或数量——盘点几个模型就分析几个，跨模型对比类
  图（`needs_models: 2`）在单模型数据上自动跳过，不算失败。
- **滚动窗口重叠陷阱**：若预测/真值以"每行一个窗口、行间滚动步进"的形式组织（相邻行窗口
  高度重叠），**任何分布统计（直方图、分位数、KS 检验）前必须先把滚动窗口重建为物理连续
  序列**，否则同一物理点会被重复计数几百次。是否是这种滚动窗口结构、重叠了多少步，属于
  Stage 0 对齐时要确认的 schema 事实，不能凭经验假设。
- **训练数据是可选输入，只用于漂移诊断**：`train_y` 不参与指标计算，唯一用途是给
  `train-test-drift` 一类图提供基准分布（回答"预测单元是不是落在训练没覆盖的分布里"）。
  没有 `train_y` 就跳过漂移类图，其余指标与图谱照常。
- **事实与归因物理隔离**：Stage 3 只写"看到了什么"（现象 + 数字 + 稳健性检验结果），
  **禁止机制语言**；Stage 4 才允许"为什么"，且必须过结论三道门（`references/mechanisms.md`
  或本目录 `references/analysis-discipline.md`）。混着写会导致"看图编故事"，且让最贵的
  归因步骤花在用户不关心的现象上。

## 2. 逐阶段菜谱

### Stage 0：路径与质检

输入：intake 盘点到的 `predict`/`truth`（及可选 `features`/`train_y`）材料路径。

菜谱：
1. 用户调用本 playbook 时通常会同时给出预测值与真值路径；缺任一直接问，不自行搜索猜测——
   不同批次/模型会有多份候选文件，选错整个分析都错。
2. 若用户的评估口径依赖一个外部指标脚本（原体系里的 `metric.py` 一类工具），路径由用户给，
   本 playbook 不内置猜测逻辑；找不到用户指定路径时可在项目目录内按文件名搜索列候选，
   由用户确认，不自行裁决。
3. **质检先于一切指标计算**（坏 label 会污染所有下游结论）。复用
   `<本 playbook 目录>/scripts/run_quality_check.py`（原技能固化脚本，逻辑不变，仅路径
   随本次迁移调整）：schema 侦察（列名与脚本顶部 CONFIG 对不上只改 CONFIG 不改逻辑）、
   基础完整性（重复戳/网格缺口/常值段）、滚动窗口一致性抽查（不一致则取点口径全不可信，
   停下报告用户）、重建序列扫可疑日 → `suspect_days.csv`。
4. **可疑日二分处理**：区分"错误"（录入/传感器故障 → 从统计剔除并记录）与"事件"（限电/
   停机/极端天气 → 保留数据、进 project-context 的事件台账、归因时显式考虑）——两者处理
   相反，不可一律当异常"修掉"。

done：`suspect_days.csv` 落盘。

### Stage 1：指标计算

输入：Stage 0 质检通过的 predict/truth；`metric-caliber` 问题的答案。

菜谱：按 `metric-caliber` 选定口径计算每个模型的指标（RMSE/MAE/ACC 等，视用户口径定义），
产出模型集的指标表（Excel 或等价表格）。**模型集来自 intake 的 predict 材料盘点**——盘点
到几个预测列/模型就出几份表，不假定固定数量。若用户提供外部评估脚本，首次运行先确认其
调用签名（构造参数、预测怎么传、输出写哪），跑通后把确切调用固化下来供本次会话复用；随后
做一次口径对账（任选一段数据自算一遍与脚本输出比对，相对差 <1% 视为一致），验证取点/聚合
理解没有跑偏，之后可跳过。复用 `<本 playbook 目录>/scripts/run_analysis.py` 中与指标相关
的部分或用户外部脚本，不现写 pandas 重复实现。

done：`*.xlsx`（或用户口径约定的等价指标表）落盘。

### Stage 2：相关性与画图

输入：Stage 1 产出的指标表；对齐后的 predict/truth（及可选 features/train_y）。

菜谱：**不写图代码**——frontmatter `charts:` 声明的图全部用 chartbook 预写脚本
（engine-core chartbook 豁免），orient 已按材料盘点结果标好可画/跳过。命令模板：

```bash
python3 <ENGINE>/chartbook/scripts/chart_<蛇形id>.py \
  --pred predictions.csv --truth truth.csv --out-dir charts/ [各图特有参数]
```

画完跑 `<ENGINE>/scripts/build_index.py` 建 `INDEX.md`（阶段闸的产物判据之一）。
每张图落盘 PNG + 同名 `.stats.json`；**PNG 只给人看，分析一律读 stats.json，不 Read
图**——stats.json 已做到自足（把图上一切可判读的数字都写进去），判读流程 = 读
stats.json 的完整曲线/数字判走势 → 对号本目录 `references/figure-diagnostics.md` 的
形态判读 → 结合 project-context 背景写结论，全程无需读图。

原技能固化的旧版画图脚本（`<本 playbook 目录>/scripts/plots.py` +
`<本 playbook 目录>/scripts/run_analysis.py`）仍可作为参考实现或补充图（chartbook 尚未
覆盖的图形）；chartbook 已覆盖的图不要用旧脚本重复画，避免两套产物打架。分布漂移诊断
（需要 `train_y`）用 `<本 playbook 目录>/scripts/run_drift.py`（跨数据集对比 pooled 与
逐条对比，逐条对比在缺训练集时自动跳过，指标与其余图谱照常）。

done：`charts/*.json`（至少一张）+ `INDEX.md` 落盘。

### Stage 3：事实提取（现象清单，停顿点）

输入：Stage 2 的图与指标表。

菜谱：判读各图 stats.json + 指标表，写现象清单进 `FINDINGS.md`（状态="现象"）：每条 =
一句现象陈述 + 支撑数字 + 图/表链接，**禁止出现机制语言**（不写"因为模型的 XX 机制…"）。

done：`FINDINGS.md` 含"现象"标记 → **停下来**：向用户报现象清单，问哪几条要进 Stage 4
深挖（`pause_after: true`，唯一强制停顿点）。

### Stage 4：深归因与结论

输入：用户点名的现象子集；Stage 0-2 的全部产物；project-context/模型档案等背景。

菜谱：两类高频归因问题走固定流程（详见本目录 `references/playbooks.md`，已去域名化的
版本待整体迁移，当前文档仍含原技能的具体图号叙述，读取时按"图号 → chartbook recipe id"
对照本 playbook frontmatter 的 `charts:` 列表自行换算）：

- **"为什么某段变差了？"**：查台账/事件 → 定位口径/时段 → 定位坏样本 → 占比分解（构成
  变化 vs 能力变化）→ 分布漂移（有 train_y 时）→ 过反驳门写结论。
- **"为什么模型 A 比 B 好（差）？"**：同质化程度 → 分组条件对比 → 定位时间/时效 →
  对照模型架构档案（Stage 0 已声明的 `model-profile` 上下文，`model_code` present 时
  经 model-audit 提供）验证机制 → 过反驳门。

下结论前必过**结论三道门**（稳健性门槛 → 假设登记 → 反驳门），细则见本目录
`references/analysis-discipline.md`；机制结论必须引用假设登记文档中的一条 H-ID。

`CONCLUSION.md`（面向管理层，Stage 4 收尾）：把 FINDINGS 已证实结论**翻译**成管理层语言，
叙述优先、全文表格≤1 张、方法论机器不进正文、金字塔先结论后给建议，模板见引擎
`references/conclusion-reporting.md`。

done：`CONCLUSION.md` 落盘。`subagent_ok: false`——深归因涉及结论三道门与反驳门，需要
跨结果的全局视角，不外包给子代理。

## 3. 证据升级规则

单证据线（本 playbook 未声明 `evidence_lines`，无需 `upgrade_rule`）：现象升级到假设、
假设升级到已证实，走结论三道门（稳健性门槛 → 假设登记 → 反驳门），细则见
`references/analysis-discipline.md`。反驳门七类替代解释（事件/样本量/构成变化/分布外/
上游原料变化/共享组件混淆/外部事件）逐条排除，每条给排除证据或显式标"未排除"并降级。

## 4. 停顿点与汇报

Stage 3 完成是唯一强制停顿点：向用户汇报现象清单（按图/表分组），请用户点名哪几条进
Stage 4 深挖；Stage 4 收尾把 `CONCLUSION.md` 内容（含关键数字）直接展示给用户，不只报
路径。

## 5. subagent 拆分建议

Stage 2 画图与 Stage 3 逐图事实提取天然可并发：一个图组/一个 range 一个 subagent，图像
和逐图 stats.json 都不进主 agent 上下文（最大的 token 收益）；Stage 0/1 质检与指标计算
可交给一个子代理串行跑（产出表格、不占图像上下文，并行收益有限）；Stage 4 深归因全程
主 agent 亲自做（结论三道门 + 反驳门需要跨结果的全局判断，且 `subagent_ok: false`）。

## 6. 结论模板与本 playbook 特有反驳门条目

结论模板见引擎 `references/conclusion-reporting.md`。特有反驳门条目：

- **口径混淆**：结论是否在同一考核口径下成立？换一种口径（如按天平均 vs 整段合并）方向
  是否翻转？翻转则原结论降级为"仅在 XX 口径下成立"。
- **构成 vs 能力**：某段/某模型变差，是"难例（坏天气/异常段）占比升高"还是"同类样本内
  能力退化"？没有用分组条件对比拆分 → 未排除。
- **分布外/漂移**：预测单元是否落在训练数据没覆盖的分布区间（有 `train_y` 时用漂移图
  核验，无则显式标"未排除，缺训练侧基准"）。

## 7. 材料降级说明

- `predict`/`truth` 缺：不可做——两者是评估的最小闭环，没有降级路径。
- `features` 缺：`feature-error-conditional`/`feature-trend-overlay`/
  `y-vs-feature-mapping` 三张输入侧图跳过，Stage 4 的"输入原料变化"反驳门条目降级为
  "未排除，缺特征侧证据"。
- `train_y` 缺：`train-test-drift` 跳过，Stage 4 分布外/漂移反驳门条目降级为"未排除"。
- `model_code` 缺：`model-profile` 上下文保持 absent，Stage 4 的模型对比归因只能停在
  现象/统计层面，机制层面的"为什么"标注"缺代码锚定的架构档案，暂不可深究"。
- `training_log`/`experiment_config` 缺：不阻塞主线，仅在核验训练窗口/超参相关假设时
  少一路交叉验证来源，缺席记 `open-questions.md`。

## 8. chartbook 覆盖声明

声明进 Stage 2 charts：error-breakdown、intraday-profile、worst-points、
horizon-degradation、rolling-stability、true-vs-pred-scatter、train-test-drift、
feature-error-conditional、feature-trend-overlay、y-vs-feature-mapping、
cross-dim-stability。

跳过：model-error-correlation / oracle-gap / worst-slice-compare /
model-rank-significance / baseline-skill——五者定位是"多模型/多方案对比"，本 playbook
的模型集大小不预设，present ≥2 个预测列时这些图仍可按需临时加画（图表选择门的可加画池），
只是不作为默认草绘集，因为本目标的核心主线是单一预测结果自身的质量归因而非多方案竞赛；
global-attribution / local-waterfall / lookback-decay——三者需要 `serving_api`（在线
预测服务），本 playbook 的 materials 未声明该材料，结构性不适用；
bad-window-clustering / good-bad-contrast——聚焦"坏样本聚类/对比"，与 Stage 3 的现象
提取存在功能重叠，默认不进草绘集但保留在可加画池供用户按需补充；
error-acf / pp-calibration / theil-decomposition / time-shift-diagnosis /
horizon-error-quantiles——均为误差结构的补充切面，默认不进草绘集（Stage 2 的 11 张
已覆盖误差结构/时间稳定性/输入侧/跨维度四大主线），用户按需可加画。

## 9. 运行后回顾

本 playbook 靠"用得越多越准"——每次实跑暴露的问题写回：脚本 bug/列名 → 改
`<本 playbook 目录>/scripts/`；指令歧义/缺步骤 → 改本文件；确认的新项目事实 → 补
project-context；方法类知识 → 补 `<本 playbook 目录>/references/`。
