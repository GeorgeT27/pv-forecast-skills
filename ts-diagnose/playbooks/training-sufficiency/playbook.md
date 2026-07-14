---
id: training-sufficiency
name: 训练充分性/训练动力学
goal: 判断训练是否充分（收敛/平台期/batch与数据量瓶颈），并解释训练分配（chunk/fold/run 构成）如何影响 loss 动力学
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
      artifacts: ["CONCLUSION.md"]
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
crystallize_min_cases: 5   # 最深 playbook：固化三关之关1（多样性）要求 5 个互异 case（默认 3）
---

# Playbook：训练充分性 / 训练动力学

> 泛化自 pv-station-influence 的 Stage 0–2（probe_logs / loss_dynamics / influence_regression 的方法内核），
> 去掉站点/光伏语义：分析对象是**任何**"分段训练产生的 loss 曲线族 +（可选）分组成员构成 +（可选）外部指标序列"。

## 1. 问题框定与首要陷阱

要回答的三个子问题：**训练充分吗**（每条曲线到平台了吗、边际增益还剩多少）；**为什么不同单元的 loss 不同**（组成成分/顺序/规模效应）；**训练分配有问题吗**（某些成员/某种排法系统性地推高 loss 或拖慢收敛）。

先立三条纪律（违反任何一条，结论直接不可信）：

1. **震荡 ≠ 异常**：分段/分块训练下 loss 与外部指标随段震荡是预期动力学（后段把参数拉向本段分布），不是病。别把单个段的跳变归咎于当时的成员。
2. **loss 高 ≠ 有害**："含成员 s 的单元 loss 高"只说明 s **自己难学**；"s 拖累目标指标"是另一回事。两者构成四象限（§4），其中"loss 低但目标侧有害"才是分布冲突的典型指纹。
3. **跨系列不 pool 数值**：不同模型/配置（series）的损失函数与量纲可能不同，绝不把 loss 数值跨 series 平均或合并回归；跨 series 只比 Spearman 排名。

## 2. 逐阶段菜谱

分析脚本由 agent 按下列菜谱**运行时生成**进工作目录 `analysis_scripts/`，每个脚本先过声明的验证步、结果记 PROGRESS.md，才可信其产出（crystallize 只快照有验证记录的脚本）。产物全部自足（json 带完整数字与形状描述），判读不读原始日志、不读 PNG。

**生成闸（硬规则）**：Stage 2/3/4 的脚本生成后、碰真实数据前，必须先过金标准闸——
`python3 <ENGINE>/scripts/gen_gate.py --script analysis_scripts/<name>.py --playbook training-sufficiency --stage <N>`。
CLI 与产物最小 schema 以 `golden/manifest.json` 为准（可执行示例见 `golden/reference/`）。金标准算错 → 改脚本，**不改期望**；闸报告落 `gate_reports/`（provenance 汇总用）。Stage 0/1 依赖真实记录源格式无法预置金标准，用下述对账验证步。

### Stage 0：探测记录源与结构确认 → `probe_summary.json`

- **输入**：question `loss-source` / `unit-structure` 的答案；config 里的日志/记录路径。
- **菜谱**：生成 `analysis_scripts/probe.py`——按记录源类型扫描：能否找到 loss 记录、覆盖哪些 series/iteration/unit/epoch 范围、抽 3-5 条样例行原文；落 `probe_summary.json`：`{loss_found, sample_lines, coverage: {series: [...], n_iterations, n_units, epochs_per_unit}, gaps: [...]}`。
- **验证步**：样例行人工比对用户描述的格式；coverage 与用户宣称的训练规模一致（不一致 → 问用户，不猜）。
- **无记录分支**：`loss_found=false` 且拿不到 checkpoint 内 loss → 本 playbook 只剩外部指标线可做（Stage 4 独立于 loss 也可跑外部指标自身的充分性形态），FINDINGS 注明"loss 侧无料"。

### Stage 1：曲线提取 → `loss_records.csv`

- **长表列固定**：`series,iteration,unit,position,epoch,loss`。语义：series=模型/配置；iteration=重复轮（无则 0）；unit=段（chunk/fold/run；单曲线退化为 `all`）；position=段在轮内顺序（无则 0）。step 级记录先按 epoch 聚合均值。
- **菜谱**：生成 `analysis_scripts/extract_loss.py`，按 probe 的样例行写解析器；只读必要列，逐行流式处理，绝不把原始日志整体读进上下文。
- **验证步（对账）**：随机抽 3 个 (series,iteration,unit)，解析值与原始记录逐条核对；行数 = coverage 推算的期望行数（差异要能解释，如缺失段）。

### Stage 2：动力学指标 → `dynamics_metrics.json`

逐 `(series, iteration, unit)` 计算（公式与理由承自 influence-methods 的 Stage 1，已验证过）：

- **final_loss**：尾 `tail_k=3` 个 epoch 的均值（去尾部抖动，比单末 epoch 稳）。
- **conv_slope**：`log(loss) ~ epoch` 的 OLS 斜率（log 使不同量级曲线尺度稳健；越负 = 收敛越快，≈0 = 平台/停滞）。
- **plateau_epoch**：首个进入 `final_loss × 1.05` 的 epoch（多快到平台）。
- **marginal_gain**：最后 `tail_k` 个 epoch 的相对改善 `(loss[-k]-loss[-1])/loss[-k]`——充分性判据"边际增益阈值"直接用它。
- **充分性形态汇总**（逐 series）：`{n_units_plateaued, n_units_still_falling, worst_marginal_gain, tail_slope_distribution}`。
- **菜谱**：生成 `analysis_scripts/dynamics.py`；json 里带每条曲线的完整指标 + 每 series 的排名（`highest_final_loss / slowest_converging` top-k）+ `cross_series_spearman`（各 series 的 unit 排名两两相关）。
- **验证步（合成小样自检）**：造一条已知形态的合成曲线（如 `loss=2·exp(-0.3·epoch)+1`），断言 conv_slope<0、plateau_epoch 落在解析解 ±1 内——过了才跑真数据。

### Stage 3：成分回归 → `composition_effects.json`（变体 grouped）

只在有分组结构（chunk/fold 有成员构成）时激活。回答"哪个成员让单元难学/收敛慢"。

- **输入**：`assignments.csv`（列 `iteration,unit,position,member`；从用户提供的分组记录或回放脚本生成——分组记录缺失且不可复现 → 本阶段做不了，如实降级，**不要**用"看起来像"的分组猜）。
- **设计（关键坑，承自 influence_regression）**：因变量 = final_loss 或 conv_slope；自变量 = 成员指示。若每轮每成员恰进一个单元，指示和与截距共线（虚拟变量陷阱变体）→ ① **中心化成员指示**（减该单元平均占用）；② **岭回归**（截距不罚）稳共线方向；③ 系数 θ_m 读作**相对平均成员的相对效应**（sum-to-zero 语义），只比排名不过度解读绝对值。控制变量：`iteration`（训练成熟度）、`position`（新近效应）、`size`（单元大小）——不控则成员效应被训练阶段效应污染。
- **不确定性**：bootstrap over 观测行给 θ_m 95% CI，CI 排除 0 才算方向可信。**功效诚实**：观测数 ≈ 轮数×单元数，参数 ≈ 成员数+4；轮数 <10 时只报排名不报显著性（json 里写 `power_note`）。
- **逐 series 独立回归**，跨 series 只报 Spearman。
- **验证步（植入回收）**：合成一组已知 θ 的假数据（如成员 A 的单元 final_loss 恒 +0.5σ），断言回归能把 A 排进 top-1——过了才跑真数据。

### Stage 4：外部指标关联 → `external_link.json`（变体 external）

- **输入**：`config.external_metric_path`（逐段外部指标序列，如留出集每单元训后 RMSE）。
- **菜谱**：生成 `analysis_scripts/external_link.py`：① 外部指标自身充分性形态（随训练推进的趋势、末端是否仍在改善）；② loss 侧 unit 排名 × 外部指标侧 unit 排名的 Spearman（同现证据）；③ 有成分回归时，θ_loss 与 θ_target 的四象限归类（§4）。
- **纪律**：本线是**佐证**，Spearman 同现不给任何成员单独定罪；它的价值是与 Stage 3 构成两条独立证据线（升级规则见 frontmatter `upgrade_rule`）。
- **验证步**：对齐检查——外部指标的 (iteration,unit) 键集合与 loss 侧一致（缺口列出来，不静默丢行）。

### Stage 5：事实提取 ⏸（现象清单，禁机制语言）

- 只读 Stage 2–4 的 json summary，产出 FINDINGS.md「现象」条目：每条 = 观察 + 数字 + 来源产物。句式如"series M2 的 32/32 条曲线 marginal_gain < 1%（dynamics_metrics.json）"；**禁止**"因为 batch 不足/因为遗忘"等机制语言。
- 需要图就按 `fig-style` 答案画进 `figures/`，每图配自足 stats.json；判读读 json 不读 PNG。
- **停顿**：完成后向用户汇报现象清单（≤15 条），请用户点名要深挖的项，才进 Stage 6。

### Stage 6：结论（主 agent 亲自做，subagent_ok: false）

- 按 `sufficiency-criterion` 的答案逐 series 下"充分/不充分/证据不足"判定，每判定引用具体数字。
- "训练分配问题"结论走升级规则 + 三道门（引擎 references/mechanisms.md）+ 本 playbook 反驳门（§6）。
- `training-config` 若按默认（未提供），batch/数据量归因一律写"待补配置后确认"，不得从曲线形态硬推 batch 结论。
- 写 CONCLUSION.md（面向主管，写法见引擎 references/conclusion-reporting.md），并直接呈现给用户。

## 3. 证据升级规则（映射三道门）

| 结论类型 | 上限 | 升级条件 | 对应门 |
|---|---|---|---|
| 某 series 已到平台/仍在下降 | 已证实 | 判据口径明确 + 尾部形态跨 iteration 稳定（剔除最差 10% 单元方向不变） | 稳健性门 |
| 某成员拉高 loss/拖慢收敛 | 现象→假设 | Stage 3 CI 排除 0 **且** 与 Stage 4 目标侧排名 Spearman 一致；先在 HYPOTHESES.md 登记 | 假设登记 + 多证据线 |
| 训练分配（顺序/规模）有问题 | 假设 | position/size 控制变量效应显著 + 反驳门过 | 反驳门 |
| batch/数据量不足 | 假设 | 需要 training-config 事实 +（最好）不同 batch 的对照曲线；单靠形态最多"现象" | 反驳门 |

## 4. 四象限（loss 效应 × 目标效应）

θ_loss（Stage 3，难学度）× θ_target（Stage 4 或外部归因，目标侧危害度）：

| | θ_target 高（拖累目标） | θ_target 低 |
|---|---|---|
| **θ_loss 高（难学）** | 脏数据既难学又污染 → 数据质量红旗优先 | 难学但无害 → 留着无妨 |
| **θ_loss 低（学得顺）** | **学得顺却把参数拉离目标 = 分布冲突指纹** | 双低，正常 |

## 5. Subagent 拆分建议

- Stage 0/1/2 可打包给一个数据 subagent（Brief-COMPUTE，见引擎 references/subagent-briefs.md）；多 series 大日志时按 series 分片，`--out loss_records.<series>.csv` 各写各的，主 agent 合并。
- Stage 3/4 计算轻，主 agent 或单 subagent 即可；Stage 5 现象提取可给 Brief-FACT。
- 单写者纪律：state/PROGRESS/FINDINGS/config 只有主 agent 写。

## 6. 本 playbook 特有反驳门条目（结论标"已证实/假设"前逐条过）

1. **记录截断/解析错位**：coverage 缺口或对账差异未解释 → 一切下游结论不可信，先回 Stage 1。
2. **学习率调度混淆**：loss 平台可能是 lr 衰减到 0，不是"学完了"——training-config 有调度信息才可排除；没有 → 充分性结论降一级并注明。
3. **新近效应冒充成员效应**：position 控制变量显著时，先怀疑训练顺序而非成员本身（处理建议不同：混洗/回放 vs 剔除）。
4. **单元规模混淆**：size 未控制或与成员强相关 → θ_m 可能只是"大单元 loss 低"的伪影。
5. **量纲穿帮**：任何跨 series pool 过数值的中间结果 → 作废重算。

## 7. 结论模板（CONCLUSION.md 骨架）

一句话结论（充分/不充分 + 最关键数字）→ 关键发现 3–5 条（每条：结论 + 一个数字 + 大白话原因）→ 对训练的建议（如：延长 epoch / 调 batch / 改分配顺序 / 查某成员数据质量 / 补结构化 loss 日志）→ 可信度说明（哪些站得住、哪些是初步、缺什么料）。
