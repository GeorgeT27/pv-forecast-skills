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

本 playbook 回答一个问题：哪些输入变量对目标指标（预测误差或性能）影响最大。四个首要陷阱：

1. **重要 ≠ 因果**。permutation 和相关性分析回答的都是"模型有多依赖这个变量"，不回答"现实世界里结果有多少是它驱动的"。结论措辞必须区分"对模型重要"与"对现象重要"。
2. **泄漏列霸榜**。泄漏列 = 模型在预测时刻本拿不到的列（事后才产生的观测、或由目标变量派生的列）。这类列的重要性会排第一名——那是分析错误，不是发现。`feature-list` 问题必须问清泄漏风险；被标记为泄漏的列只做对照展示，不进正式排名。
3. **共线摊薄**。高度相关的变量逐列单独置换时会互相顶替，每一列的重要性都被低估。要按 `collinearity-handling` 问题的答案把它们整组一起置换。
4. **口径依赖**。同一个变量，对整体误差可能无足轻重，却主导突变时段的误差。必须按 `importance-scope` 问题的答案选定口径来报告，不许擅自换口径。

## 2. 逐阶段菜谱

生成的分析脚本统一放进 `analysis_scripts/`。每个脚本都要先通过自己的验证步才算可信；验证结果记入 PROGRESS.md。

**生成闸（硬规则）**：Stage 0 的脚本生成之后、接触真实数据之前，必须先通过金标准闸（答案已知的合成数据，校验脚本本身没写错）：

`python3 <ENGINE>/scripts/gen_gate.py --script analysis_scripts/<name>.py --playbook feature-importance --stage 0`

金标准里植入了主导变量 x1 和泄漏列 x3：筛查脚本必须把泄漏列隔离出去、把 x1 排到前面，才算过闸。CLI 契约见 `golden/manifest.json`，参考示例见 `golden/reference/`。脚本算错了 → 改脚本，不改期望值。Stage 1/2 需要真实模型入口、无法金标准化，改用各自菜谱声明的"植入回收"验证步：先造一个答案已知的玩具问题，脚本能把答案找回来，才许上真实数据。

### Stage 0：相关筛查（对齐由 setup 承接） → `correlation_screen.json`

- 分析表 = **setup 产物的 features.csv × predictions.csv 逐窗误差**。两张表的位置由 orient 注入的 manifest 摘要给出；对齐键与丢行数已由 setup 的 alignment_report 披露，本阶段只需核对特征×误差的合表。
- 逐变量算三样：与误差的 Spearman、互信息、分位条件均值（取误差最高的 10% 时段，看各变量在这些时段里相对整体的分布偏移）。
- 共线组检测：两两相关 |ρ|>0.9 的变量聚成一组。
- schema：`{n_rows, dropped_rows, features: {col: {spearman_vs_error, mi, tail_shift}}, collinear_groups: [...], leakage_flagged: [...]}`。
- **验证步（对账）**：对齐后的行数与原表核对；丢掉的行按原因分类列出（缺失/时间对不上），不许静默丢行。

### Stage 1：Permutation 重要性 → `permutation_importance.json`（变体 rerun）

- 逐变量置换取值、其余变量不动，经 `model_predict_entry` 批量重跑推理，`importance = metric(置换) − metric(基线)`。
- 共线组按 `collinearity-handling` 的答案处理（整组或逐列）。每个变量重复置换 ≥5 次，报均值±std；基线 metric 要与 Stage 0 对账。
- schema：`{baseline_metric, features: {col: {importance_mean, importance_std, n_repeats}}, groups: {...}, ranking: [...]}`。
- **验证步（植入回收）**：造一个 `y = 3·x1 + 噪声` 的玩具模型和数据，断言 x1 的 permutation 重要性排第一（top-1）——过了才跑真模型。
- **成本披露**：重跑推理的次数 = 变量数 × 重复数。动手前先估算耗时报给主 agent；太贵就必须问用户是否缩小变量集（恒问第 3/4 类），不许自行拍板。

### Stage 2：剔除重算 → `ablation_importance.json`（变体 ablation）

- 对 Stage 0/1 排出的 top 嫌疑变量（k≤5）逐个剔除后重训，报 `Δmetric`；也可以直接使用用户已有的消融实验结果。
- 重训是昂贵操作——**动手前必须已获用户显式授权**。授权由主 agent 问过用户之后写入 config.ablation_authorized，脚本不许自行开跑。
- **验证步**：重训配置与基线配置做 diff，差异只允许是被剔除的那个变量；diff 落盘供审计。

### Stage 3：事实提取 ⏸

- 只读前面三个阶段的 json 产物，产出现象清单：每条都带数字和来源。共线组与泄漏列是怎么处理的，也如实写进清单。
- 只写"看到什么"，不写"为什么"。写完停顿，等用户点名要深入哪条。

### Stage 4：结论（主 agent）

- 按 frontmatter 的 upgrade_rule 判级：两条证据线排名一致的 top 变量 → 升"假设"，登记 H-ID；有剔除重算确认的 → 可议升"已证实"，但还必须过反驳门（见 §5）；只有单条证据线 → 停在"现象"，并带限定语。
- 结论要落到行动：保留/剔除/替换数据源，或对某个变量补数据质量核查。写 CONCLUSION.md。

## 3. 证据升级规则（映射三道门）

| 结论 | 上限 | 条件 | 对应门 |
|---|---|---|---|
| 变量 X 对模型最重要 | 假设 | permutation ×（剔除重算 或 相关筛查）top-k Spearman 一致 + 登记 H-ID | 假设登记 + 多证据线 |
| 剔除 X 可改善/不损性能 | 已证实 | Stage 2 重训对照 + 配对检验显著 + 反驳门过 | 稳健性门 + 反驳门 |
| 仅相关筛查的排名 | 现象 | ——（带"相关非因果"限定语） | —— |

## 4. Subagent 拆分建议

- Stage 1 可按变量组分片派给多个 subagent 并行，每片写自己的产物（`--out perm.<group>.json`，占位符按实际组名填）；推理的批量化在脚本内部做，不靠多开 subagent。
- Stage 0–3 在 `feature-importance-compute` 卡片区间内，整段派发。
- GPU 只有单卡时不分片。

## 5. 本 playbook 特有反驳门条目

标"已证实"之前逐条排除：

1. **泄漏未排除**：榜首变量过一遍"事后可得性"审查——它在预测时刻真的拿得到吗？过不了 → 整条结论降级并标记。
2. **置换破坏联合分布**：置换会制造现实中不存在的变量组合（如夜间配高辐照），重要性可能被夸大。对有强物理约束的变量，结论要注明这条保留。
3. **共线顶替**：逐列置换与整组置换两份排名不一致时，以整组为准报告信息源价值。
4. **口径漂移**：三条证据线用的 metric 与时段窗口必须完全一致；不一致就先统一口径，再比较。

## 6. 结论模板

按顺序写四块：①一句话总结（最重要的变量/信息源 + 一个关键数字）；②top 变量逐条（判级 + 两条证据线的数字 + 一句大白话含义）；③行动建议（数据投入与特征取舍的优先级）；④可信度说明（哪些结论有干预实验确认，哪些只是模型依赖度的观测）。

### Stage 5 变体 feature-quality：预测特征质量归因（`material:feature_true` 解锁）

主线 Stage 0-4 回答"变量对模型重要吗"。本变体回答另一个问题：当**输入特征本身就是预报量**（上游预报特征，未来窗口与预测目标同期）时，**哪些特征自己报错了、并因此拖累了目标指标**。

回答它必须有 `feature_true` 材料：每个特征的"预报 vs 实况"成对序列。格式约定：每行一个窗口时间戳，每格是与预测窗口同长的点列 list；列的命名约定不限，脚本会启发式配对。

并入的方法资产（原专用技能 pv-feature-blame，2026-07-24 并入）：

- 预写脚本在 `<本 playbook 目录>/scripts/`；
- 自带金标准在 `<本 playbook 目录>/golden-feature-blame/`——与本 playbook 自己的引擎金标准 `golden/` 是两回事，勿混用勿合并；
- 方法细则见 `references/blame-methods.md`，结论纪律见 `references/blame-discipline.md`，用户的标准调用模板见 `references/prompt-template.md`。

**硬规则（原话保留）：feature_true 材料 unknown 时本变体不解锁——由入口闸的 intake 盘点解决，绝不静默降级。** 用户明确确认"没有"（absent-confirmed）→ 若仍要做，走"窗口重叠重建实况"的降级模式（见 `references/blame-methods.md`），证据自动降一级且结论必须注明；绝不在未问用户的情况下静默重建。

#### 首要陷阱：特征误差大 ≠ 该特征有罪

1. **模型可能对该特征不敏感**——特征预报错得离谱，模型预测却纹丝不动。点名必须过**双关**：该行该特征误差异常（z ≥ 阈值），**且**该特征误差与该口径的行误差全局相关（Spearman ρ ≥ 阈值）。两关都命中才点名。金标准埋了诱饵 f_decoy（误差更大但与模型误差零耦合），点了名闸就拦。反事实（Stage 6）是最终仲裁——没跑反事实不得标"已证实"。
2. **共线特征成簇**——同一上游来源的预报误差往往同涨同落，统计上分不出谁是元凶。同簇只报簇、不点名单个成员（以 blame_summary 的 collinearity_clusters 为证）；簇内定罪只能靠反事实逐个替换。
3. **坏天/极端条件下一切特征同时坏**——全局相关可能只是条件共变。升"假设"前要按分组条件（如天气分型）条件化重算；同项目预测侧分析已有分组产物时直接复用。
4. **单换无效 ≠ 无罪**——存在冗余结构时，两个坏特征各自单独替换都修不好，一起替换才修好。断言"该特征无罪"之前，必须先过 Stage 6 的 minimal-set 层。
5. **跳变大 ≠ 有罪**——相邻两行是对同一物理时刻的两次起报，预报翻新带来的跳变是预期物理，且文献实证跳变与预报误差只有弱相关。点名"翻新致不稳"必须过 churn 两关（跳变幅度显著 + 跳变与该模型行误差全局相关），再由 neighbor-swap 反事实仲裁。金标准埋点 f_jumpy_decoy：跳变更大但零耦合，必须不点名。
6. **稳定的系统偏差 ≠ 有罪**——模型在有偏的预报上训练会学会补偿它。点名要基于剥掉系统偏差 ε_sys 之后的波动部分 ε_res（稳健加性回归分解，见方法细则）。sys_frac（系统偏差占比）高的特征被补偿闸洗清——对已学会补偿的固定模型，"把偏差修了"反而可能有害。ε_res 是白噪声的也不点名（可约性闸——上游根本改不了的误差，点名是废话）。金标准埋点 f_sys_bias / f_irreducible 分别钉住这两道闸。

#### 菜谱（预写脚本流水线，产物自足可断点续跑）

| 步骤 | 脚本 → 产物 |
|---|---|
| 探查配对 | `scripts/probe_schema.py` → probe_schema.json + feature_pairs.json（识别时间戳列/模型列、启发式配对预报-实况两列、校验窗一致性并交叉核验真值；unmapped 列问用户后写回） |
| 坏行定位 | `scripts/find_bad_rows.py` → bad_rows_<口径>_<模型>.csv + bad_rows_summary.json（每口径×每模型：误差 >均值 且进 top N%；全量排名落盘） |
| ε 分解 | `scripts/feature_decompose.py` → feature_decomp.json + eps_res_*.npy（剥 ε_sys 得 ε_res，并评估可约性） |
| 双关点名 | `scripts/feature_blame.py` → blame_report.csv + blame_summary.json（z + 全局 ρ 双关，再过 sys_frac 补偿闸与可约性闸，并输出共线簇） |
| 翻新跳变 | `scripts/feature_revision.py` → revision_report.csv + revision_summary.json（churn 两关，免调 API） |
| 单行深查 | `scripts/analyze_row.py`（可选：对指定行或最坏行做逐特征画像；单行证据级别恒为"现象"） |
| 汇总 | 主 agent 合并被点名清单 + 翻新画像 + 各产物路径 → **feature_blame_report.json**（本阶段 done 判据） |

口径的行级化定义（默认 rmse_192 = 每行整个预测窗的 RMSE；可选短临/日前切片口径）与切片常量，一律通过 `scripts/fb_common.py` 接线的共享 data_utils import，绝不本地重定义（口径漂移 = 整条归因链作废）。工作目录配置 blame_config.json 的字段说明见 `scripts/fb_common.py` 头部；键名是遗留命名，语义已泛化为通用单元/条目表述。

**质量闸**：改动任何预写脚本之后，必须重跑 `python3 -m pytest <本 playbook 目录>/scripts/ -q`：真元凶 f_blame 必须被点名，诱饵 f_decoy/f_jumpy_decoy 必须不被点名，补偿/可约性闸埋点 f_sys_bias/f_irreducible 必须被洗清。全绿才许碰真实数据。

#### 升级规则（映射三道门）

- **现象**：单口径单模型下 z+ρ 双关命中（blame_report 行）；翻新画像同级。
- **假设**：跨模型或跨时段稳定 + 分组条件化后信号仍在 + 有上游机制解释，登记 H-ID。
- **已证实**：唯一通道 = Stage 6 反事实（见 §8）。用户拒绝反事实 → 最高只能到"假设"并注明。
- 坏行样本 <10 时只描述、不定论；共线簇内不点名单个成员。

### Stage 6 变体 counterfactual：反事实验证预算阶梯（`material:serving_api` 解锁）

把被点名的特征替换成实况，经用户的预测服务（`serving_api` 材料，例如一个 FastAPI 服务）重新预测，看指标变差是否随之消失。这是特征质量结论升"已证实"的唯一通道。前置条件 `stage:5`：先有点名，才有可替换的对象。

代码分两层：

- **决策数学全部在 `scripts/cf_logic.py`**——零网络依赖，以 `--selfcheck` 过金标准闸；
- HTTP 层在 `scripts/counterfactual_api.py` + 工作目录里的 adapter.py（模板是 `scripts/api_adapter_template.py`）。活的 API 无法金标准化，用 `--dry-run` 兜底：先产出调用计划表和 payload 给用户确认——**首跑必 dry-run 给用户过目才许打真实 API**。

**预算阶梯**：五层按"证据价值/成本"排序，逐层花预算，上一层的结果决定下一层做不做。subagent brief 见 `references/subagent-briefs.md`。

1. **oracle G 闸（防冤枉）**：把坏行的全部配对特征都换成实况，测指标缺口 G。G 不显著（< g_min）= 这一行的变差不是特征质量问题，是模型或其它原因——**不得归因任何特征**。先过此闸，再花下面几层的钱。
2. **per-feature / all-blamed（边际）**：逐个被点名特征单独替换 + 全部被点名特征一起替换，按修复谓词（τ 阈）报修复率。单换有效 = 该特征单独可修。
3. **minimal-set（联合致坏）**：单换全都无效、但 all-blamed 有效 → 搜索最小修复集（冗余结构下单换必然无效，抓"几个坏特征一起才把这行带坏"），点名整个集合。
4. **lattice Shapley（最差行精查）**：对最差的几行，在特征子集格上做 Shapley 归因并算交互项，量化各特征的边际贡献。
5. **neighbor-swap（翻新仲裁）**：把相邻两次起报的特征序列互换后重新预测，churn 随之消减，才可把"翻新致不稳"升"已证实"。拼接出的序列行间不连续，服务端可能拒收——须单独确认 api.neighbor_swap_confirmed。

分片纪律：按模型分片、各写各的产物防竞态；阶梯按层分批派发；subagent 只回 JSON 摘要，**禁自行放宽 τ/G 阈值**；结果逐行追加、可中断续跑。最终把各层结果与判定汇总落盘 **cf_summary.json**（本阶段 done 判据）。

### 两变体的材料降级说明

predict/truth/features 三样缺任何一样 → 本 playbook 整体不可做（三者是 required 材料；由 setup 内联生产时同样要求）。

- `feature_true` unknown → 变体不解锁（§7 硬规则）；absent-confirmed → 用户知情后可走窗口重叠重建的降级模式（证据降一级）。Stage 5/6 未激活不阻塞主线 Stage 0-4。
- `serving_api` absent/unknown → Stage 6 结构性跳过，特征质量结论上限"假设"（CONCLUSION.md 须注明未做反事实）。
