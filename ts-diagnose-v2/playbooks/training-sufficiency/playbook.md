---
id: training-sufficiency
name: 训练充分性/训练动力学
goal: 判断训练是否充分（收敛/平台期/batch与数据量瓶颈），并解释训练分配（chunk/fold/run 构成）如何影响 loss 动力学
upstream:
  - product: setup
    required: false
stages:
  - id: 0
    name: 探测记录源与结构确认
    done_when:
      artifacts: ["probe_summary.json"]
    prereqs:
      - desc: 记录源问题已答（loss 在哪、什么格式）
        check: "question:loss-source"
      - desc: 训练组织结构已确认（分块/fold/多run/单曲线）
        check: "question:unit-structure"
    pause_after: false
    subagent_ok: true
  - id: 1
    name: 曲线提取（loss_records.csv 长表）
    done_when:
      artifacts: ["loss_records.csv"]
    prereqs:
      - desc: Stage 0 探测完成
        check: "stage:0"
    pause_after: false
    subagent_ok: true
  - id: 2
    name: 动力学指标（final_loss / conv_slope / plateau_epoch / 边际增益）
    done_when:
      artifacts: ["dynamics_metrics.json"]
    prereqs:
      - desc: loss_records.csv 在（Stage 1）
        check: "artifact:loss_records.csv"
    pause_after: false
    subagent_ok: true
  - id: 3
    name: 成分回归（loss 动力学 ~ 单元成员，仅分组结构）
    done_when:
      artifacts: ["composition_effects.json"]
    prereqs:
      - desc: dynamics_metrics.json 在（Stage 2）
        check: "artifact:dynamics_metrics.json"
      - desc: 单元成员表 assignments.csv 在（分组记录解析或回放生成）
        check: "artifact:assignments.csv"
    pause_after: false
    subagent_ok: true
  - id: 4
    name: 外部指标关联（loss 侧 × 目标侧，仅佐证）
    done_when:
      artifacts: ["external_link.json"]
    prereqs:
      - desc: dynamics_metrics.json 在（Stage 2）
        check: "artifact:dynamics_metrics.json"
      - desc: 外部指标序列路径已填
        check: "file:config.external_metric_path"
    pause_after: false
    subagent_ok: true
  - id: 5
    name: 事实提取（现象清单，禁机制语言）
    done_when:
      findings_marker: "现象"
    prereqs:
      - desc: 动力学指标在（Stage 2）
        check: "artifact:dynamics_metrics.json"
    pause_after: true
    subagent_ok: true
  - id: 6
    name: 结论（充分性判定 + CONCLUSION.md）
    done_when:
      artifacts: ["CONCLUSION.md", "gate_reports/conclusion_gate.json"]
    prereqs:
      - desc: 现象清单已有（Stage 5）
        check: "stage:5"
      - desc: 充分性判据口径已答
        check: "question:sufficiency-criterion"
    pause_after: false
    subagent_ok: false
variants:
  - id: grouped
    when: "config:grouped"
    unlocks_stages: [3]
  - id: external
    when: "config:external_metric_path"
    unlocks_stages: [4]
questions:
  - id: loss-source
    stage: 0
    ask: "训练 loss 记录在哪里、每行/每条什么格式？（贴 2-3 行样例最好；结构化 CSV/JSON、文本日志、TensorBoard、只在 checkpoint 里，还是没记录？）"
    why: "决定 Stage 0/1 解析器怎么写；猜错 schema 会污染全部下游"
    options: ["结构化 CSV/JSON", "文本日志（有样例行）", "TensorBoard/事件文件", "只在 checkpoint 里 / 没记录"]
    default: null
  - id: unit-structure
    stage: 0
    ask: "训练怎么组织的？（分块 chunk 轮换 / 交叉验证 fold / 多次独立 run / 单一连续训练）有分组的话，各单元的成员构成记在哪里？"
    why: "决定长表的 unit 语义与 Stage 3 成分回归是否可做"
    options: ["分块 chunk 轮换（多迭代随机重排）", "交叉验证 fold", "多次独立 run（不同种子/配置）", "单一连续训练（单曲线，无分组）"]
    default: null
    skip_if: "config:chunking"
  - id: training-config
    stage: 0
    ask: "训练配置概要：batch size、每单元样本量/数据量、epoch 数、优化器与学习率调度？"
    why: "『是否 batch 不足 / 数据量不足』的归因需要这些事实；不提供则只做曲线形态判读"
    default: "未提供——只做曲线形态判读，batch/数据量归因降级为『待补配置后确认』"
  - id: external-metric
    stage: 4
    ask: "有没有外部评估指标序列（如留出集逐段 RMSE / 验证集指标）？有的话路径与格式？"
    why: "有它才能把 loss 侧现象与目标侧效应关联（Stage 4）；没有则跳过该阶段"
    default: "无（Stage 4 跳过）"
    skip_if: "config:external_metric_path"
  - id: sufficiency-criterion
    stage: 6
    ask: "『训练充分』按什么口径判？（到达平台期 / 边际增益低于阈值（给阈值）/ 对齐某外部业务指标 / 其他）"
    why: "充分性是相对口径的结论；口径不定，Stage 6 无法下判"
    options: ["平台期判据（尾部斜率≈0）", "边际增益阈值（最后 k epoch 改善 < x%）", "对齐外部指标（外部指标不再改善即充分）"]
    default: null
  - id: fig-style
    stage: 5
    ask: "图表语言/配色偏好？"
    why: "纯呈现类选择"
    default: "中文标注、matplotlib 默认配色、每图配自足 stats.json"
evidence_lines:
  - id: loss-composition
    stage: 3
    output: composition_effects.json
  - id: target-link
    stage: 4
    output: external_link.json
upgrade_rule: "『某单元成员拖累/拉高 loss』要升「假设」：成分回归（loss 侧）与外部指标关联（目标侧）两线 Spearman 排名一致；只有一线（无外部指标）时结论上限是「现象」+『loss 侧』限定语"
crystallize_min_cases: 5   # 固化为代理技能前的多样性门槛：需要 5 个互不相同的成功案例（一般 playbook 默认 3 个；本 playbook 流程最深，所以门槛更高）
---

# Playbook：训练充分性 / 训练动力学

> 本 playbook 分析的对象是**任何**"分段训练产生的 loss 曲线族"，外加两样可选材料：分组成员构成表、外部指标序列。

## 1. 问题框定与首要陷阱

本 playbook 回答三个子问题：**训练充分吗**——每条 loss 曲线是否已进入平台期、剩余的边际增益还有多少；**为什么不同单元的 loss 不同**——"单元"指训练被切分出的段（一个 chunk、一个交叉验证 fold、或一次独立 run），差异可能来自成员构成、训练顺序或规模；**训练分配有问题吗**——是否有某些成员或某种排列方式在系统性地推高 loss 或拖慢收敛。

动手前先立三条纪律。违反任何一条，结论直接不可信：

1. **震荡不等于异常**。分段/分块训练时，loss 和外部指标随段起伏是预期动力学（每个新段把参数拉向本段分布），不是病。不许把某个段上的一次跳变直接归咎于该段的成员。
2. **loss 高不等于有害**。"含成员 s 的单元 loss 高"只说明 s **自己难学**；"s 拖累目标指标"是另一回事。两者组合出四个象限（见 §4），其中"loss 低但目标侧有害"才是分布冲突的典型指纹。
3. **跨系列不 pool 数值**。不同 series（模型/配置）的损失函数与量纲可能不同，绝不把 loss 数值跨 series 平均、也不把它们合进同一个回归。跨 series 只比 Spearman 排名。

## 2. 逐阶段菜谱

分析脚本不是预置的。agent 按下面各阶段的"菜谱"在运行时现写脚本，放进工作目录 `analysis_scripts/`。每个脚本必须先通过该阶段声明的验证步，并把验证结果记进 PROGRESS.md，它的产出才算可信。crystallize 只快照有验证记录的脚本。

所有产物必须自足：json 里带完整数字与形状描述。后续判读只读这些 json，不回头读原始日志，也不读 PNG 图片。

**生成闸（硬规则）**：Stage 2/3/4 的脚本写好之后、接触真实数据之前，必须先过金标准闸：
`python3 <ENGINE>/scripts/gen_gate.py --script analysis_scripts/<name>.py --playbook training-sufficiency --stage <N>`。
CLI 参数与产物的最小 schema 以 `golden/manifest.json` 为准，可执行示例见 `golden/reference/`。脚本在金标准数据上算错 → 改脚本，**不改期望**。闸报告落在 `gate_reports/`，供 provenance 汇总用。Stage 0/1 的解析逻辑取决于真实记录源的格式，没法预置金标准，改用各自的对账验证步。

### Stage 0：探测记录源与结构确认 → `probe_summary.json`

- **输入**：两个提问的答案——question `loss-source`（loss 记录在哪、什么格式）与 `unit-structure`（训练怎么组织）；再加 config 里的日志/记录路径。
- **可以少问的情况**：**setup 产物 built/linked 时**，先读它的 setup_manifest.json 里的 materials 清单。training_log / experiment_config 的位置与格式在 setup 盘点时已经记录，『在哪』这个问题免问直接用，`loss-source` 只需要补格式细节与样例行。
- **菜谱**：生成 `analysis_scripts/probe.py`，按记录源类型扫描三件事：能否找到 loss 记录；覆盖了哪些 series/iteration/unit/epoch 范围；抽 3-5 条样例行原文。结果落 `probe_summary.json`，结构为 `{loss_found, sample_lines, coverage: {series: [...], n_iterations, n_units, epochs_per_unit}, gaps: [...]}`。
- **验证步**：样例行与用户描述的格式人工比对；coverage 要与用户宣称的训练规模一致。不一致 → 问用户，不许猜。
- **无记录分支**：`loss_found=false`、且 checkpoint 里也拿不到 loss 时，本 playbook 只剩外部指标这一条线可做——Stage 4 不依赖 loss，可以单独分析外部指标自身的充分性形态。此时在 FINDINGS 里注明"loss 侧无料"。

### Stage 1：曲线提取 → `loss_records.csv`

- **长表列固定**：`series,iteration,unit,position,epoch,loss`。各列语义：series=模型/配置；iteration=重复轮次（没有就填 0）；unit=训练段（chunk/fold/run；单一连续训练退化为 `all`）；position=该段在本轮里的先后顺序（没有就填 0）。原始记录是 step 级的，先按 epoch 聚合取均值。
- **菜谱**：生成 `analysis_scripts/extract_loss.py`，按 Stage 0 抽出的样例行写解析器。只读必要的列，逐行流式处理，绝不把原始日志整体读进上下文。
- **验证步（对账）**：随机抽 3 个 (series,iteration,unit) 组合，把解析出的值与原始记录逐条核对；总行数要等于 coverage 推算出的期望行数，有差异必须能解释（比如确实缺失了某些段）。

### Stage 2：动力学指标 → `dynamics_metrics.json`

逐 `(series, iteration, unit)` 计算下列指标：

- **final_loss**：最后 `tail_k=3` 个 epoch 的 loss 均值。
- **conv_slope**：对 `log(loss) ~ epoch` 做 OLS 回归得到的斜率。斜率越负 = 收敛越快；≈0 = 已平台或停滞。
- **plateau_epoch**：loss 首次降进 `final_loss × 1.05` 范围的 epoch。
- **marginal_gain**：最后 `tail_k` 个 epoch 的相对改善，公式 `(loss[-k]-loss[-1])/loss[-k]`。充分性判据里的"边际增益阈值"直接用这个数。
- **充分性形态汇总**（逐 series）：`{n_units_plateaued, n_units_still_falling, worst_marginal_gain, tail_slope_distribution}`。
- **菜谱**：生成 `analysis_scripts/dynamics.py`。输出 json 里要带三部分：每条曲线的完整指标；每个 series 内的排名（`highest_final_loss / slowest_converging` 的 top-k）；`cross_series_spearman`（各 series 之间 unit 排名的两两 Spearman 相关）。
- **验证步（合成小样自检）**：先造一条形态已知的合成曲线（如 `loss=2·exp(-0.3·epoch)+1`），断言算出的 conv_slope<0、plateau_epoch 落在解析解 ±1 之内——自检过了才允许跑真实数据。

### Stage 3：成分回归 → `composition_effects.json`（变体 grouped）

只在训练有分组结构（chunk/fold 有成员构成）时激活。回答"哪个成员让所在单元难学、或收敛慢"。

- **输入**：`assignments.csv`，列为 `iteration,unit,position,member`。这张表必须来自用户提供的分组记录，或由回放脚本重新生成。分组记录缺失且无法复现 → 本阶段做不了，如实降级说明；**不要**凭"看起来像"去猜分组。
- **设计**：因变量取 final_loss 或 conv_slope；自变量是成员指示变量（某成员在不在这个单元里，0/1）。若每轮每个成员恰好进一个单元，指示变量与回归截距完全共线，因此分三步处理：① **中心化成员指示**——每个指示变量减去该单元的平均占用；② 用**岭回归**稳住共线方向（截距不罚）；③ 系数 θ_m 要读作**该成员相对于平均成员的相对效应**（sum-to-zero 语义），只比较排名，不过度解读绝对值。回归还必须加控制变量：`iteration`（训练成熟度）、`position`（新近效应）、`size`（单元大小），否则成员效应会被训练阶段效应污染。
- **不确定性**：对观测行做 bootstrap 重采样，给每个 θ_m 一个 95% CI；CI 排除 0，效应方向才算可信。**功效诚实**：这套回归的观测数 ≈ 轮数×单元数，参数个数 ≈ 成员数+4。轮数 <10 时样本太少，只报排名、不报显著性，并在 json 里写明 `power_note`。
- **逐 series 独立回归**；跨 series 只报 Spearman 排名相关。
- **验证步（植入回收）**：合成一组 θ 已知的假数据（如让成员 A 所在单元的 final_loss 恒 +0.5σ），断言回归能把 A 排进 top-1——自检过了才跑真实数据。

### Stage 4：外部指标关联 → `external_link.json`（变体 external）

- **输入**：`config.external_metric_path`，指向一条逐段的外部指标序列，比如每个单元训完后在留出集上的 RMSE。
- **菜谱**：生成 `analysis_scripts/external_link.py`，做三件事：① 外部指标自身的充分性形态——随训练推进的趋势、末端是否仍在改善；② loss 侧 unit 排名 × 外部指标侧 unit 排名的 Spearman 相关；③ 若 Stage 3 的成分回归已做，把 θ_loss 与 θ_target 按 §4 的四象限归类。
- **纪律**：这条线只是**佐证**。Spearman 排名同现不足以给任何成员单独定罪；它与 Stage 3 构成两条相互独立的证据线（升级规则见 frontmatter `upgrade_rule`）。
- **验证步**：对齐检查——外部指标的 (iteration,unit) 键集合必须与 loss 侧一致；有缺口要列出来，不许静默丢行。

### Stage 5：事实提取 ⏸（现象清单，禁机制语言）

- 只读 Stage 2–4 的 json summary，产出 FINDINGS.md 的「现象」条目。每条 = 观察 + 数字 + 来源产物，句式如"series M2 的 32/32 条曲线 marginal_gain < 1%（dynamics_metrics.json）"。**禁止**写机制解释（如"因为 batch 不足""因为遗忘"），只陈述看到了什么。
- 需要画图时，按 `fig-style` 问题的答案画进 `figures/`，每张图配一份自足的 stats.json；判读只读 json，不读 PNG。
- **停顿**：本阶段完成后暂停，向用户汇报现象清单（≤15 条），请用户点名要深挖的条目，得到答复后才进 Stage 6。

### Stage 6：结论（主 agent 亲自做，subagent_ok: false）

- 按 `sufficiency-criterion` 问题确定的判定口径，逐 series 给出"充分/不充分/证据不足"三者之一，每个判定都要引用具体数字。
- "训练分配有问题"这类结论要走完整升级流程：满足 frontmatter 的升级规则，过引擎的三道门（见引擎 references/mechanisms.md），再过本 playbook 自己的反驳门（§6）。
- `training-config` 问题若按默认处理（用户未提供配置），batch/数据量归因一律写"待补配置后确认"，不许只凭曲线形态硬推 batch 结论。
- 写 CONCLUSION.md（面向主管的写法见引擎 references/conclusion-reporting.md），并直接呈现给用户。

## 3. 证据升级规则（映射三道门）

每类结论有一个证据上限；想升级必须满足升级条件，并通过对应的门：

| 结论类型 | 上限 | 升级条件 | 对应门 |
|---|---|---|---|
| 某 series 已到平台/仍在下降 | 已证实 | 判据口径明确 + 尾部形态跨 iteration 稳定（剔除最差 10% 单元后方向不变） | 稳健性门 |
| 某成员拉高 loss/拖慢收敛 | 现象→假设 | Stage 3 的 CI 排除 0 **且** 与 Stage 4 目标侧排名的 Spearman 一致；升级前先在 HYPOTHESES.md 登记 | 假设登记 + 多证据线 |
| 训练分配（顺序/规模）有问题 | 假设 | position/size 控制变量效应显著 + 反驳门过 | 反驳门 |
| batch/数据量不足 | 假设 | 需要 training-config 的配置事实 +（最好）不同 batch 的对照曲线；单靠曲线形态最多标"现象" | 反驳门 |

## 4. 四象限（loss 效应 × 目标效应）

两个坐标轴：θ_loss 来自 Stage 3，衡量某成员让单元变得多难学；θ_target 来自 Stage 4 或外部归因，衡量该成员对目标指标的危害度。两轴交叉出四种情况：

| | θ_target 高（拖累目标） | θ_target 低 |
|---|---|---|
| **θ_loss 高（难学）** | 脏数据既难学又污染 → 数据质量红旗优先 | 难学但无害 → 留着无妨 |
| **θ_loss 低（学得顺）** | **学得顺却把参数拉离目标 = 分布冲突指纹** | 双低，正常 |

## 5. Subagent 拆分建议

- Stage 0/1/2 可以打包交给一个数据 subagent，用 Brief-COMPUTE 模板下任务（见引擎 references/subagent-briefs.md）。多 series、大日志时按 series 分片并行：各自输出 `--out loss_records.<series>.csv`，最后由主 agent 合并。
- Stage 3/4 计算量轻，主 agent 自己做或交给单个 subagent 都行。Stage 5 的现象提取可交给 Brief-FACT。
- **单写者纪律**：state/PROGRESS/FINDINGS/config 这几个全局文件只有主 agent 能写，subagent 一律不碰，避免并发写坏状态。

## 6. 本 playbook 特有反驳门条目（结论标"已证实/假设"前逐条过）

给结论标级前逐条过；任何一条命中且没解决，结论降级或作废：

1. **记录截断/解析错位**：Stage 0 的 coverage 有缺口、或 Stage 1 对账差异没解释清 → 一切下游结论不可信，先回 Stage 1 修数据。
2. **学习率调度混淆**：loss 进入平台可能只是学习率已衰减到接近 0，不是"学完了"。只有 training-config 里有调度信息才可能排除这种解释；没有 → 充分性结论降一级并注明。
3. **新近效应冒充成员效应**：position 控制变量显著时，先怀疑是训练顺序在起作用，而不是成员本身有问题。顺序问题用混洗/回放验证，成员问题才考虑剔除。
4. **单元规模混淆**：size 没控制、或与成员构成强相关 → θ_m 可能只是"大单元 loss 低"造成的伪影。
5. **量纲穿帮**：任何跨 series 合并（pool）过 loss 数值的中间结果 → 作废重算。

## 7. 结论模板（CONCLUSION.md 骨架）

按下面顺序写：

1. 一句话结论：充分/不充分 + 最关键的一个数字。
2. 关键发现 3–5 条。每条 = 结论 + 一个数字 + 大白话原因。
3. 对训练的建议。例如延长 epoch、调 batch、改分配顺序、查某成员数据质量、补结构化 loss 日志。
4. 可信度说明：哪些结论站得住、哪些只是初步、还缺什么材料。
