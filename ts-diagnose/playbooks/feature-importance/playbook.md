---
id: feature-importance
name: 变量重要性/归因
goal: 找出哪些输入变量对目标指标（预测误差/性能）影响最大，为特征取舍与数据投入排优先级
upstream:
  - product: setup
    required: true
stages:
  - id: 0
    name: 相关筛查（对齐由 setup 承接）
    done_when:
      artifacts: ["correlation_screen.json"]
    prereqs:
      - desc: setup 产物就绪
        check: "product:setup"
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
      artifacts: ["CONCLUSION.md", "gate_reports/conclusion_gate.json"]
    prereqs:
      - desc: 现象清单已有（Stage 3）
        check: "stage:3"
    pause_after: false
    subagent_ok: false
  - id: 5
    name: 预测特征质量归因（feature_true 对照）
    done_when:
      artifacts: ["feature_blame_report.json"]
    prereqs:
      - desc: feature_true 材料已就位
        check: "material:feature_true"
    pause_after: false
    subagent_ok: true
  - id: 6
    name: 反事实验证（预算阶梯）
    done_when:
      artifacts: ["cf_summary.json"]
    prereqs:
      - desc: 特征质量归因已点名
        check: "stage:5"
      - desc: serving_api 材料已就位
        check: "material:serving_api"
    pause_after: false
    subagent_ok: true
materials:
  required: [predict, truth, features]
  optional: [feature_true, serving_api]
variants:
  - id: rerun
    when: "config:model_predict_entry"
    unlocks_stages: [1]
  - id: ablation
    when: "config:ablation_authorized"
    unlocks_stages: [2]
  - id: feature-quality
    when: "material:feature_true"
    unlocks_stages: [5]
  - id: counterfactual
    when: "material:serving_api"
    unlocks_stages: [6]
questions:
  - id: importance-scope
    stage: 0
    ask: "『重要』对什么口径说？（整体误差 / 某类时段或条件下的误差 / 某个业务指标）目标列取 setup 长表的哪个误差口径？"
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

**生成闸（硬规则）**：Stage 0 的脚本生成后、碰真实数据前，必须先过金标准闸——
`python3 <ENGINE>/scripts/gen_gate.py --script analysis_scripts/<name>.py --playbook feature-importance --stage 0`
（金标准植入了主导变量 x1 与泄漏列 x3，筛查必须隔离泄漏、排出 x1；CLI 契约见 `golden/manifest.json`，示例见 `golden/reference/`）。算错 → 改脚本，不改期望。Stage 1/2 需真实模型入口，用菜谱声明的植入回收验证步。

### Stage 0：相关筛查（对齐由 setup 承接） → `correlation_screen.json`
- 分析表 = **setup 产物的 features.csv × predictions.csv 逐窗误差**（orient 注入 manifest 摘要定位两表；对齐键与丢行数由 setup 的 alignment_report 披露，本阶段只做特征×误差的合表核对）；逐变量算与误差的 Spearman/互信息 + 分位条件均值（误差最高 10% 时段里各变量的分布偏移）；共线组检测（|ρ|>0.9 聚组）。
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

## 7. 变体 feature-quality：预测特征质量归因（Stage 5，`material:feature_true` 解锁）

主线 Stage 0-4 回答"变量对模型重要吗"；本变体回答另一个问题：**输入特征本身是预报量**
（上游预报特征，未来窗口与预测目标量同期）时，**哪些特征的预报错误拖累了目标指标**。
回答它必须有 `feature_true` 材料——每特征"预报 vs 实况"成对序列（每行一个窗口时间戳，
每格与预测窗口同长的点列 list，命名约定不限，脚本启发式配对）。方法迁自专用技能
pv-feature-blame（2026-07-24 并入：预写脚本在 `<本 playbook 目录>/scripts/`，金标准在
`<本 playbook 目录>/golden-feature-blame/`——与本 playbook 自己的引擎金标准 `golden/`
是两回事，勿混用勿合并；方法细则见 `references/blame-methods.md`、结论纪律见
`references/blame-discipline.md`、用户标准调用模板见 `references/prompt-template.md`）。

**硬规则（原话保留）：feature_true 材料 unknown 时本变体不解锁——由入口闸的 intake
盘点解决，绝不静默降级。** 用户明确确认"没有"（absent-confirmed）→ 若仍要做，走窗口
重叠重建实况的降级模式（见 `references/blame-methods.md`），证据自动降一级且结论注明；
绝不在未问用户的情况下静默重建。

### 首要陷阱：特征误差大 ≠ 该特征有罪

1. **模型可能对该特征不敏感**——预报错得离谱但预测纹丝不动。点名必须过**双关**：该行该
   特征误差异常（z ≥ 阈值）**且**该特征误差与该口径行误差全局相关（Spearman ρ ≥ 阈值），
   两者都命中才点名（金标准专门埋了 f_decoy：误差更大但零耦合，点了名闸就拦）。反事实
   （Stage 6）是最终仲裁——没跑反事实不得标"已证实"。
2. **共线特征成簇**——同源上游的预报误差往往同涨落，统计上分不开谁是元凶。同簇只报簇不
   点名单个（blame_summary 的 collinearity_clusters 为证），簇内定罪只能靠反事实逐个替换。
3. **坏天/极端条件下一切特征同时坏**——全局相关可能只是条件共变。升"假设"前按分组条件
   （如天气分型，同项目预测侧分析已有分组产物时直接复用）条件化复算。
4. **单换无效 ≠ 无罪**——冗余结构下两个坏特征各自单换都修不好、一起换才修好。断"特征
   无罪"前先过 Stage 6 的 minimal-set。
5. **跳变大 ≠ 有罪**——相邻行是同一物理时刻的两次起报，预报翻新跳变是预期物理，且文献
   实证跳变与预报误差只有弱相关。点名"翻新致不稳"须过 churn 两关（跳变幅度显著 + 跳变
   与该模型行误差全局相关）+ neighbor-swap 反事实仲裁。金标准埋点 f_jumpy_decoy：跳变
   更大但零耦合，必须不点名。
6. **稳定的系统偏差 ≠ 有罪**——模型在有偏预报上训练会学会补偿它（共适应）。点名基于剥掉
   ε_sys 后的波动 ε_res（稳健加性回归分解）；sys_frac 高的特征被补偿闸洗清（"修了"对
   固定模型反而可能有害）；白噪声 ε_res 也不点名（可约性闸——上游改不了的误差点名是
   废话；金标准埋点 f_sys_bias/f_irreducible 分别钉这两道闸）。

### 菜谱（预写脚本流水线，产物自足可断点续跑）

| 步骤 | 脚本 → 产物 |
|---|---|
| 探查配对 | `scripts/probe_schema.py` → probe_schema.json + feature_pairs.json（时间戳列/模型列/特征对启发式配对 + 窗一致性 + 真值交叉核验；unmapped 列问用户后写回） |
| 坏行定位 | `scripts/find_bad_rows.py` → bad_rows_<口径>_<模型>.csv + bad_rows_summary.json（每口径×每模型：>均值 且 top N%，全量排名落盘） |
| ε 分解 | `scripts/feature_decompose.py` → feature_decomp.json + eps_res_*.npy（剥 ε_sys → ε_res + 可约性） |
| 双关点名 | `scripts/feature_blame.py` → blame_report.csv + blame_summary.json（z + 全局 ρ 双关 + sys_frac 补偿闸 + 可约性闸 + 共线簇） |
| 翻新跳变 | `scripts/feature_revision.py` → revision_report.csv + revision_summary.json（churn 两关，免 API） |
| 单行深查 | `scripts/analyze_row.py`（可选：对指定/最坏行逐特征画像，单行证据级别恒为"现象"） |
| 汇总 | 主 agent 合并被点名清单 + 翻新画像 + 各产物路径 → **feature_blame_report.json**（本阶段 done 判据） |

口径行级化（默认 rmse_192 = 每行全窗 RMSE；可选短临/日前切片口径）与切片常量一律经
`scripts/fb_common.py` 接线的共享 data_utils import，绝不本地重定义（口径漂移 = 整条归因
链作废）。工作目录配置 blame_config.json 字段见 `scripts/fb_common.py` 头部（键名是原技能
遗留命名，语义已泛化为通用单元/条目表述）。**质量闸**：改任何预写脚本后必须重跑
`python3 -m pytest <本 playbook 目录>/scripts/ -q`——金标准埋点（f_blame 必点名）、诱饵
（f_decoy/f_jumpy_decoy 必不点名）、补偿/可约性闸埋点（f_sys_bias/f_irreducible 必洗清）
全绿才许碰真实数据。

### 升级规则（映射三道门）

- **现象**：单口径单模型 z+ρ 双关命中（blame_report 行）；翻新画像同级。
- **假设**：跨模型或跨时段稳定 + 分组条件化后仍在 + 有上游机制解释，登记 H-ID。
- **已证实**：唯一通道 = Stage 6 反事实（见 §8）。用户拒绝反事实 → 最高只能到"假设"并注明。
- 坏行样本 <10 只描述不定论；共线簇内不点名单个。

## 8. 变体 counterfactual：反事实验证预算阶梯（Stage 6，`material:serving_api` 解锁）

把被点名特征替换为实况、经用户的预测服务（`serving_api` 材料，如 FastAPI）重预测，看指标
变差是否消失——特征质量结论升"已证实"的唯一通道。前置 `stage:5`（先有点名才有可换对象）。
**决策数学全部在 `scripts/cf_logic.py`**（零网络、以 `--selfcheck` 过金标准闸）；HTTP 层在
`scripts/counterfactual_api.py` + 工作目录 adapter.py（模板 `scripts/api_adapter_template.py`；
活 API 无法金标准化，以 `--dry-run` 计划表+payload 用户确认步兜底——**首跑必 dry-run 给
用户过目才许打真实 API**）。

**预算阶梯**（按证据价值/成本排序，逐层花预算，subagent brief 见 `references/subagent-briefs.md`）：

1. **oracle G 闸（防冤枉）**：坏行全部配对特征都换成实况，测指标缺口 G。G 不显著（< g_min）
   = 该行变差不是特征质量问题（模型/其它原因），**不得归因任何特征**——先过此闸再花下面的钱。
2. **per-feature / all-blamed（边际）**：逐个被点名特征单换 + 全部被点名一起换，按修复谓词
   （τ 阈）报修复率。单换有效 = 单特征可修。
3. **minimal-set（联合致坏）**：单换全无效但 all-blamed 有效 → 搜最小修复集（冗余结构下
   单换必然无效，抓"几个坏特征一起才把这行带坏"，点名整个集合）。
4. **lattice Shapley（最差行精查）**：对最差几行做子集格上的 Shapley 归因 + 交互项，量化
   各特征边际贡献。
5. **neighbor-swap（翻新仲裁）**：相邻起报的特征序列互换重预测，churn 消减才可把"翻新致
   不稳"升"已证实"（拼接序列行间不连续，服务端可能拒收——须单独确认
   api.neighbor_swap_confirmed）。

分片纪律：按模型分片各写各的产物防竞态；阶梯按层分批，subagent 只回 JSON 摘要，**禁自行
放宽 τ/G 阈值**；结果逐行追加、可中断续跑。最终把各层结果与判定汇总落盘
**cf_summary.json**（本阶段 done 判据）。

### 两变体的材料降级说明

predict/truth/features 缺 → 本 playbook 不可做（升为 required，setup 内联生产时同样要求）。

- `feature_true` unknown → 变体不解锁（§7 硬规则）；absent-confirmed → 用户知情后可走窗口
  重叠重建降级（证据降一级）。Stage 5/6 未激活不阻塞主线 Stage 0-4。
- `serving_api` absent/unknown → Stage 6 结构性跳过，特征质量结论上限"假设"
  （CONCLUSION.md 须注明未做反事实）。
