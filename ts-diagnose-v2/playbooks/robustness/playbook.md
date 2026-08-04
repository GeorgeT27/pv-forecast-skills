---
id: robustness
name: 鲁棒性分析
goal: 检验结论/模型表现在扰动（剔极端、子期、切片、重采样）下稳不稳——区分"真差异"与"个别极端单位/特定窗口驱动的假差异"
upstream:
  - product: setup
    required: true
  - product: chart_sweep
    required: false
stages:
  - id: 0
    name: 基线复算（被检结论的原始数字）
    done_when:
      artifacts: ["baseline_metrics.json"]
    prereqs:
      - desc: setup 产物就绪
        check: "product:setup"
      - desc: 被检结论清单已答
        check: "question:conclusions-under-test"
      - desc: 指标与配对单位已答
        check: "question:metric-and-pairing"
    pause_after: false
    subagent_ok: true
  - id: 1
    name: 扰动矩阵（剔最差 k / 子期重算 / bootstrap 重采样）
    done_when:
      artifacts: ["perturbation_matrix.json"]
    prereqs:
      - desc: 基线在（Stage 0）
        check: "artifact:baseline_metrics.json"
    pause_after: false
    subagent_ok: true
  - id: 2
    name: 分组切片（按条件维度拆开看方向）
    done_when:
      artifacts: ["group_slices.json"]
    prereqs:
      - desc: 基线在（Stage 0）
        check: "artifact:baseline_metrics.json"
      - desc: 分组维度已填
        check: "config:group_columns"
    pause_after: false
    subagent_ok: true
  - id: 3
    name: 事实提取（现象清单，禁机制语言）
    done_when:
      findings_marker: "现象"
    prereqs:
      - desc: 扰动矩阵在（Stage 1）
        check: "artifact:perturbation_matrix.json"
    pause_after: true
    subagent_ok: true
  - id: 4
    name: 稳定性结论（逐条判稳/不稳 + CONCLUSION.md）
    done_when:
      artifacts: ["CONCLUSION.md", "gate_reports/conclusion_gate.json"]
    prereqs:
      - desc: 现象清单已有（Stage 3）
        check: "stage:3"
    pause_after: false
    subagent_ok: false
variants:
  - id: grouped-slices
    when: "config:group_columns"
    unlocks_stages: [2]
questions:
  - id: conclusions-under-test
    stage: 0
    ask: "要检验哪些结论/对比？（如『A 比 B 好』『X 段比 Y 段差』，逐条列出；或『整体模型表现』）"
    why: "鲁棒性是对具体结论说的；对象不定，扰动无从设计"
    default: null
  - id: metric-and-pairing
    stage: 0
    ask: "评估指标是什么、按什么单位配对？（如按天配对的 RMSE、按 fold 配对的 loss；数据一律来自 setup 产物的规范长表，不再另给路径）"
    why: "配对单位决定 Wilcoxon/剔除的粒度；猜错配对粒度检验无效"
    default: null
  - id: perturbation-families
    stage: 1
    ask: "扰动族选哪些？"
    why: "≥2 个独立扰动族才能构成升级证据"
    options: ["剔最差 k 单位 + 子期重算（默认组合）", "加 bootstrap 重采样", "加标签/输入噪声注入（需可重跑）", "自定义"]
    default: "剔最差 k 单位 + 子期重算"
  - id: group-columns
    stage: 2
    ask: "有没有想拆开看的条件维度（天气类型/季节/负载区间等）？列名或分组文件？"
    why: "切片能暴露『整体稳但某类内翻向』的隐患；没有就跳过 Stage 2"
    default: "无（Stage 2 跳过）"
    skip_if: "config:group_columns"
evidence_lines:
  - id: perturbation
    stage: 1
    output: perturbation_matrix.json
  - id: slices
    stage: 2
    output: group_slices.json
upgrade_rule: "结论要升「假设」：≥2 个独立扰动族下方向不变；要升「已证实」：另过配对检验（Wilcoxon 显著）且切片无翻向（或翻向组已解释并注明）"
---

# Playbook：鲁棒性分析

> 本 playbook 系统性地量化每条结论在多个扰动族（一类扰动方式为一族）下的稳定性。

## 1. 问题框定与首要陷阱

1. **平均数会说谎**：整体指标上的差异，可能全部由个别极端单位（比如某几天）贡献。
   剔掉最差 k 个单位后方向翻转 = 假差异。
2. **窗口选择效应**：只在某个时间子段成立的结论不是结论，只是对那个子段的描述。
3. **切片翻向（Simpson 悖论风险）**：整体上 A 优于 B，但在某类条件内 B 反超。这不是
   噪声，是结构性发现，必须单独报告。
4. **扰动不独立不算两票**："剔最差 k"和"bootstrap"吃的都是"极端单位"这同一个信号，
   两者一致不能算两票；"子期重算"看的是时间维度，才是独立视角。选扰动族时先想清楚
   它们各吃什么信号。

## 2. 逐阶段菜谱

两条通用规则：

- 广谱图形证据不属于本 playbook 的默认产物。chart_sweep 产物状态为 built/linked 时，
  直接复用它的图 JSON；确实需要跨维稳定性图时，经图表选择门加画 cross-dim-stability。
- 生成的分析脚本统一放 `analysis_scripts/`；每个脚本过了它的验证步才算可信，
  验证结果记入 PROGRESS.md。

**生成闸（硬规则）**：Stage 1 的脚本生成后、接触真实数据前，必须先过金标准闸——

`python3 <ENGINE>/scripts/gen_gate.py --script analysis_scripts/<name>.py --playbook robustness --stage 1`

金标准数据里的"差异"完全由 2 个极端单位驱动，是设计好的假差异，正确的脚本必须能识破。
CLI 契约见 `golden/manifest.json`，参考实现见 `golden/reference/`。脚本算错 → 改脚本，
不许改期望值。Stage 0 例外：基线是对用户原始数字做对账，无法预置金标准，不走这道闸。

### Stage 0：基线复算 → `baseline_metrics.json`
- 依据 `metric-and-pairing` 问题的答案，**从 setup 产物的 predictions.csv**（orient 会把
  manifest 摘要注入上下文）重算被检结论涉及的全部指标。原则：
  **不信任来路数字，自己算一遍**。按配对单位逐条落长表，另给汇总。
  schema：`{conclusions: [{id, claim, baseline_diff, n_units}], per_unit: <路径或内嵌>}`。
- **验证步（对账）**：自己算的汇总值与用户提供的原始数字比对。相对差 >1% 必须解释清楚
  （常见原因：口径、窗口或取点方式不同）；解释不了就不许继续。

### Stage 1：扰动矩阵 → `perturbation_matrix.json`
- 对每个（结论 × 扰动族）组合，计算扰动后的差异方向与幅度：
  - **剔最差 k**：按配对差的绝对值降序，剔掉 k=max(3, 10%) 个单位后重算；
  - **子期重算**：按时间把全期平分成 2–3 段，各段分别重算（段内单位数 <10 时只描述、
    不判定）；
  - **bootstrap**：在配对单位层面重采样 ≥500 次，报告方向一致率与 95% CI；
  - **配对检验**：Wilcoxon 符号秩检验（scipy.stats.wilcoxon）的 p 值。
- schema：`{conclusion_id: {family: {direction_preserved: bool, effect_before, effect_after, detail}}}`，
  另外每条结论算一个 `stability_score`（方向保持的族数 / 总族数）。
- **验证步（植入回收）**：先合成一组假配对数据，差异全部由 2 个极端单位驱动；断言脚本
  对它算出剔最差 k 后 direction_preserved=false。过了这一步才允许跑真实数据。

### Stage 2：分组切片 → `group_slices.json`（变体 grouped-slices）
- 按 `group_columns` 拆组，逐组重算差异方向与幅度。每组样本数一并落盘；样本数 <10 的
  组标"样本不足只描述"。
- **验证步**：各组样本数之和 = 总数，确保没有静默丢行。

### Stage 3：事实提取 ⏸
- 只读各 json 的 summary，产出现象清单。每条一个数字加一句陈述，例如：
  "[现象] 结论 C1 在 4/4 个扰动族方向不变 | stability_score=1.0"；
  "[现象] C2 剔最差 3 天后差异从 +0.8% 变 -0.1%（方向翻转）"。
  禁机制语言——"因为/导致/说明模型…"一律不许出现。产出后停顿，
  等用户点名要深入哪条。

### Stage 4：稳定性结论（主 agent）
- 逐条结论按 frontmatter 的 upgrade_rule 判级，三档：稳（已证实级）/ 条件稳（假设级，
  注明在哪类条件下成立）/ 不稳（原结论降级或推翻，写明差异由什么驱动）。
- 切片翻向的组必须单独成条，不许平均掉。按 references/conclusion-reporting.md 的格式写
  CONCLUSION.md。

## 3. 证据升级规则（映射三道门）

本 playbook 的判定与引擎三道门的对应关系：

| 判定 | 条件 | 对应门 |
|---|---|---|
| 结论「稳」 | ≥2 独立扰动族方向不变 + Wilcoxon 显著 + 切片无未解释翻向 | 稳健性门（全量化版） |
| 结论「条件稳」 | 整体过但某切片翻向且可解释 → 加限定语后成立 | 反驳门 |
| 结论「不稳/被推翻」 | 任一主扰动族翻向且可复现 | ——（原结论进 FINDINGS 标被推翻） |

## 4. Subagent 拆分建议

扰动矩阵按（结论 × 扰动族）分片并行：每个分片用
`--out perturb.<conclusion>.<family>.json` 各写各的文件，互不冲突；主 agent 最后合并成
perturbation_matrix.json。子代理任务模板 Brief-COMPUTE / Brief-FACT 见引擎
references/subagent-briefs.md。

## 5. 本 playbook 特有反驳门条目

写结论前逐条自问并记录，特有四条：

1. **扰动族不独立**：两个族吃的是同一个信号（见 §1 第 4 条），却按"两票一致"给结论
   升级 → 降级处理。
2. **剔除标准内生**：按"对我的结论有利"的方式挑选剔除单位（例如只剔对方模型表现好的
   天）→ 检验作废。剔除只允许按配对差绝对值这一个标准。
3. **多重比较**：必须报告总共检验了多少个组合、命中多少，不许只报命中的那几个。
4. **子期切点选择**：子期的切分点恰好落在某个已知事件上时，子期之间的差异可能反映的
   是那个事件本身，而不是时间上的不稳定。

## 6. 结论模板

按这个顺序写：一句话总评（几条结论里几条站得住）→ 逐条结论：判级 + 最关键的一个扰动
数字 + 大白话解释 → 建议（哪些结论可以对外引用、哪些要补数据再验）→ 可信度说明。
