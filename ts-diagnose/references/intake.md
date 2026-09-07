# 材料盘点（intake）——「我们有什么」的引擎级 checklist

<!-- 单一真源分工：材料 id 全集在 engine_common.MATERIAL_IDS（机器校验用），
     本文件是每类材料的人读定义 + 追问模板（test_materials.py 交叉校验两边一致）。
     新增材料类：两边同时加，测试逼你保持同步。 -->

playbook frontmatter 声明 `materials: {required: [...], optional: [...]}` 后，
orient 会报盘点状态。主 agent 按本文件流程收集，答案落 `diagnose_config.json`
的 `materials` 块。

## 盘点流程（orient 报「必需材料未就绪」时执行）

1. **一次多选 AskUserQuestion**：「你手头有哪些材料？」——选项 = 该 playbook 声明的
   required + optional 材料（每项带下表的一句话说明），**末尾固定加一项开放的
   「还有别的吗？（自由描述）」**——用户不会一次说全，checklist 就是提醒器。
2. 对每个勾选的材料，按其小节的**追问模板**批量补齐（同一批 ≤4 题；先问 required）。
   **schema 类问题请用户贴 2-3 行样例**（存 `sample_rows`，原话不转述）。
3. 落盘 `config.materials`，status 三值：
   - `present`：有，路径/schema 已问清；
   - `absent-confirmed`：**用户明确说没有**——required 材料走降级前还须用户确认
     「接受降级结论」，确认后主 agent 写 `degraded_ok: true`（PROGRESS.md 记一行）；
   - 没问过 = 无记录 = unknown：**阻塞，绝不静默降级**。
4. **路径永远不许猜**。就算工作目录里已经躺着一个很像的文件（比如明显的 predict
   parquet），它也只算**候选**——必须 AskUserQuestion 确认：「发现 <路径>，这就是
   <材料> 吗？」，用户确认后才能写 present。多个候选时按恒问五类第⑤条照问。
   路径确认了也**免不了 schema 追问**——列名语义猜错会污染全部下游（恒问五类第①条）。

## 引擎级材料规则

入口只阻塞 playbook frontmatter 声明的 `required` 材料。`optional` 材料、未声明材料和
未激活变体的材料不阻塞；它们在对应变体或图表真正启用时再盘点。`truth` 等材料若同时
是 required，仍按上面的 absent-confirmed + `degraded_ok` 规则处理。

## config.materials 条目格式

```json
"materials": {
  "predict": {
    "status": "present",
    "paths": ["runs/mA/pred.parquet", "runs/mB/pred.parquet"],
    "layout": "per-model",
    "schema": {"y_col": "power_pred", "time_col": "ts", "id_col": "station"},
    "sample_rows": "<用户贴的原话样例>",
    "source": "user", "date": "2026-07-22"
  },
  "training_log": {"status": "absent-confirmed", "degraded_ok": true,
                    "source": "user", "date": "2026-07-22"}
}
```

`source` 枚举同 questions 块：`user` / `profile` / `default` / `experiment-line`。
跨次稳定的条目（layout/schema）是 crystallize 固化原料；具体路径通常每次不同，不固化。

## 材料分类表

## `predict`

模型的预测结果（1..N 个模型）。
**追问**：在哪（每模型一个文件还是合并一个）？哪列是预测值（`y_col`）？时间戳列？
单元/站点 id 列？每行是单点还是一个窗口（如 192 点 list）？覆盖什么时间范围？贴样例行。

## `truth`

与预测同期的真值（test 集 y-label）。
**追问**：在哪？真值列名？与 predict 怎么对齐（时间戳键？窗口起点？）？有没有缺失段？贴样例行。

## `model_code`

模型实现代码仓库/目录。
**追问**：路径？里面有几个模型、名字分别是什么？哪个是产线版本（多版本必问，不许自行裁决）？
（optional 时不阻塞事实分析；需要机制归因时再走 `model_profile` 的 built/linked/declined 三分支。）

## `training_log`

训练日志。
**追问**：在哪？什么格式（结构化 CSV/JSON 还是文本）？记录了什么（loss/lr/iteration/chunk）？
贴 2-3 行样例。

## `features`

模型输入的预测特征序列（如 NWP 气象预报，与预测同期未来窗口）。
**追问**：在哪？哪些列是特征、各自什么含义与单位？与 predict 的行怎么对应？贴样例行。

## `feature_true`

特征的真值对照（每特征"预报 vs 实况"成对序列）。
**追问**：在哪？结构（每行一个窗口时间戳、每格 192 点 list？）？覆盖哪些特征？
（有此材料的特征质量归因场景走 feature-importance playbook 的 feature-quality 变体，可选再接 counterfactual 变体做反事实验证——见 playbooks/feature-importance/playbook.md §7-8。）

## `train_y`

训练集数据（train.parquet：训练期真值，特征列可选；漂移对比与训练侧诊断用）。
**追问**：在哪？时间范围？含哪些列（真值列名？带不带特征）？与 test 真值同单位同口径吗？

## `checkpoint`

模型权重/检查点（可支持重训、梯度类证据）。
**追问**：在哪？对应哪个模型哪个版本？加载入口（框架/脚本）？用它属昂贵操作——必问授权。

## `serving_api`

可调用的预测服务（反事实验证入口，如 FastAPI）。
**追问**：endpoint 与调用契约（输入输出格式）？调一次的成本/时长？有调用示例代码吗？

## `experiment_config`

实验设定（站点全集/留出划分/chunk 方案/超参）。
**追问**：在哪（文件还是口述）？project-context 实验线覆盖了吗（覆盖则走 Step 0.5 预填，
不重复问）？

## `data_profile`

数据画像/统计摘要（已有的探索性分析产物）。
**追问**：在哪？基于哪份数据、什么时候做的（过期画像误导大）？

## 适配器对账（材料 → 规范长表，chartbook/分析消费前必过）

用 materials.schema 写薄适配器把用户格式转规范长表后，**先过对账验证步再消费**：

1. 行数守恒：转换前后样本数对得上（窗口展开的按 `窗口数 × horizon` 核对）；
2. 抽 3 个窗口人工核对数值（原文件 vs 长表，逐点相等）；
3. 不得把 window/horizon/channel 等分析轴压成 run-level 汇总；保留所需数值列，记录 `rows_expected` 及公式；
4. 结果记 PROGRESS.md 一行（没对账记录的长表不可引用）。适配器 note 不构成豁免。
