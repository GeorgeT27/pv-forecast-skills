---
id: feature-importance
name: 变量重要性/归因
goal: 找出哪些输入变量对目标指标（预测误差/性能）影响最大，为特征取舍与数据投入排优先级
stages:
  - id: 0
    name: 数据对齐与相关筛查（无需模型）
    done_when:
      artifacts: ["correlation_screen.json"]
    prereqs:
      - desc: 目标口径已答
        check: "question:importance-scope"
      - desc: 候选变量与泄漏风险已答
        check: "question:feature-list"
    pause_after: false
    subagent_ok: true
  - id: 1
    name: Permutation 重要性（需可重跑推理）
    done_when:
      artifacts: ["permutation_importance.json"]
    prereqs:
      - desc: 相关筛查在（Stage 0）
        check: "artifact:correlation_screen.json"
      - desc: 模型推理入口已填
        check: "config:model_predict_entry"
    pause_after: false
    subagent_ok: true
  - id: 2
    name: 剔除重算（需可重训或有对照）
    done_when:
      artifacts: ["ablation_importance.json"]
    prereqs:
      - desc: 相关筛查在（Stage 0）
        check: "artifact:correlation_screen.json"
      - desc: 用户已授权重训/已提供消融对照
        check: "config:ablation_authorized"
    pause_after: false
    subagent_ok: true
  - id: 3
    name: 事实提取（现象清单，禁机制语言）
    done_when:
      findings_marker: "现象"
    prereqs:
      - desc: 至少一条重要性证据线在
        check: "artifact:correlation_screen.json"
    pause_after: true
    subagent_ok: true
  - id: 4
    name: 结论（重要性排名判级 + CONCLUSION.md）
    done_when:
      artifacts: ["CONCLUSION.md"]
    prereqs:
      - desc: 现象清单已有（Stage 3）
        check: "stage:3"
    pause_after: false
    subagent_ok: false
variants:
  - id: rerun
    when: "config:model_predict_entry"
    unlocks_stages: [1]
  - id: ablation
    when: "config:ablation_authorized"
    unlocks_stages: [2]
questions:
  - id: importance-scope
    stage: 0
    ask: "『重要』对什么口径说？（整体误差 / 某类时段或条件下的误差 / 某个业务指标）目标列与数据路径？"
    why: "同一变量对整体和对突变时段的重要性可以完全相反"
    default: null
  - id: feature-list
    stage: 0
    ask: "候选变量清单（列名+含义+单位）？其中哪些列有『泄漏风险』（事后才可得、或本身由目标算出）？"
    why: "泄漏列会以最高重要性霸榜并且是错的——必须先排除或标记"
    default: null
  - id: model-access
    stage: 1
    ask: "能对模型做什么？（可批量重跑推理 → permutation 可做；可重训 → 剔除重算可做；都不行 → 只有相关筛查）入口脚本/命令？"
    why: "决定证据线数量与结论上限（见 upgrade_rule）"
    options: ["可批量推理（给入口）", "可推理也可重训", "都不行（只做观测筛查）"]
    default: null
  - id: collinearity-handling
    stage: 1
    ask: "高相关变量成组吗？（如多个辐照源）permutation 对共线组要整组置换还是逐列？"
    why: "共线变量逐列置换会互相顶替、重要性被摊薄——整组置换才反映信息源价值"
    default: "自动检测 |ρ|>0.9 的组，组内逐列 + 整组各报一份"
evidence_lines:
  - id: correlation
    stage: 0
    output: correlation_screen.json
  - id: permutation
    stage: 1
    output: permutation_importance.json
  - id: ablation
    stage: 2
    output: ablation_importance.json
upgrade_rule: "变量重要性排名要升「假设」：≥2 条证据线（permutation/剔除重算/相关筛查）top-k 排名 Spearman 一致；只有相关筛查一线时上限「现象」且必须带『相关非因果』限定语"
---

# Playbook：变量重要性/归因

## 1. 问题框定与首要陷阱

1. **重要 ≠ 因果**：permutation/相关都回答"模型用了它多少"，不回答"世界由它驱动多少"。结论措辞必须区分"对模型重要"与"对现象重要"。
2. **泄漏列霸榜**：事后可得或由目标派生的列（未来观测、标签变换）重要性会是第一名——是分析错误不是发现。`feature-list` 必问泄漏风险，被标记的列只做对照展示。
3. **共线摊薄**：高相关变量逐列置换互相顶替，各自重要性被低估；按 `collinearity-handling` 答案整组置换。
4. **口径依赖**：对整体误差不重要的变量可能主导突变时段——按 `importance-scope` 的答案报告，别擅自换口径。

## 2. 逐阶段菜谱

脚本生成进 `analysis_scripts/`，验证步过了才可信（记 PROGRESS.md）。

### Stage 0：数据对齐与相关筛查 → `correlation_screen.json`
- 变量与目标误差对齐成一张分析表（对齐键与丢行数落盘披露）；逐变量算与误差的 Spearman/互信息 + 分位条件均值（误差最高 10% 时段里各变量的分布偏移）；共线组检测（|ρ|>0.9 聚组）。
- schema：`{n_rows, dropped_rows, features: {col: {spearman_vs_error, mi, tail_shift}}, collinear_groups: [...], leakage_flagged: [...]}`。
- **验证步（对账）**：对齐后行数与原表核对，丢行原因分类列出（缺失/时间对不上），不许静默丢。

### Stage 1：Permutation 重要性 → `permutation_importance.json`（变体 rerun）
- 逐变量（共线组按答案处理）置换后经 `model_predict_entry` 批量重跑推理，`importance = metric(置换) − metric(基线)`；每变量重复 ≥5 次置换报均值±std；基线 metric 与 Stage 0 对账。
- schema：`{baseline_metric, features: {col: {importance_mean, importance_std, n_repeats}}, groups: {...}, ranking: [...]}`。
- **验证步（植入回收）**：造一个 `y = 3·x1 + 噪声` 的玩具模型/数据，断言 x1 permutation 重要性 top-1——过了才跑真模型。
- **成本披露**：重跑次数 = 变量数 × 重复数，先估算耗时报给主 agent；太贵 → 问用户（恒问第 3/4 类）缩小变量集。

### Stage 2：剔除重算 → `ablation_importance.json`（变体 ablation）
- 对 top 嫌疑变量（Stage 0/1 的 top-k，k≤5）逐个剔除后重训（或使用用户已有的消融实验结果），报 `Δmetric`；重训是昂贵操作——**动手前必须已获用户显式授权**（config.ablation_authorized 由主 agent 问过后写入）。
- **验证步**：重训配置与基线配置 diff 只有被剔变量（落盘 diff 供审计）。

### Stage 3：事实提取 ⏸
- 只读三份 json 产现象清单（每条带数字与来源）；共线组与泄漏列的处理方式如实写进清单。停顿，等用户点名。

### Stage 4：结论（主 agent）
- 按 upgrade_rule 判级：两线一致的 top 变量 → 假设（登记 H-ID）；有剔除重算确认的 → 可议已证实（还须过反驳门）；单线 → 现象 + 限定语。
- 结论落到行动：保留/剔除/替换数据源/对某变量补数据质量核查。写 CONCLUSION.md。

## 3. 证据升级规则（映射三道门）

| 结论 | 上限 | 条件 | 对应门 |
|---|---|---|---|
| 变量 X 对模型最重要 | 假设 | permutation ×（剔除重算 或 相关筛查）top-k Spearman 一致 + 登记 H-ID | 假设登记 + 多证据线 |
| 剔除 X 可改善/不损性能 | 已证实 | Stage 2 重训对照 + 配对检验显著 + 反驳门过 | 稳健性门 + 反驳门 |
| 仅相关筛查的排名 | 现象 | ——（带"相关非因果"限定语） | —— |

## 4. Subagent 拆分建议

Stage 1 按变量组分片（`--out perm.<group>.json`），推理批量在脚本内做；Stage 0/3 可给 Brief-FACT。GPU 单卡不分片。

## 5. 本 playbook 特有反驳门条目

1. **泄漏未排除**：榜首变量过一遍"事后可得性"审查，过不了 → 整条结论降级并标记。
2. **置换破坏联合分布**：permutation 制造了现实中不存在的组合（如夜间高辐照）——重要性可能高估；对强物理约束的变量注明此保留。
3. **共线顶替**：逐列与整组两份排名不一致时，以整组为准报告信息源价值。
4. **口径漂移**：三条证据线用的 metric/时段窗口必须完全一致，不一致先统一再比。

## 6. 结论模板

一句话（最重要的变量/信息源 + 一个数字）→ top 变量逐条（判级 + 两线数字 + 大白话含义）→ 行动建议（数据投入/特征取舍优先级）→ 可信度说明（哪些有干预确认、哪些只是模型依赖度）。
