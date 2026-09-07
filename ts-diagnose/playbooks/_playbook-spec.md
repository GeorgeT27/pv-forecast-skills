# Playbook 接口规范（_playbook-spec）

一个 playbook = 一个诊断目标的完整定义，由两部分组成：**frontmatter**（YAML，`orient.py` 机器读：
判断阶段推进、前置、提问、变体）+ **正文**（agent 照做的菜谱：现场写分析脚本、判读结果）。
目录规则：每个 playbook 一个独立目录 `playbooks/<id>/`，正文在 `<id>/playbook.md`，
金标准基线在 `<id>/golden/`（§5）。

**独立性纪律（Layer 1）**：playbook 之间零共享、互不引用——A 的正文里不许出现 B 的 id；
唯一例外是 frontmatter `upstream` 声明的产物关系（§1、§2）。`test_layering.py` 守卫。

## 1. Frontmatter schema

完整示例（各字段规则在示例后逐组说明）：

```yaml
---
id: training-sufficiency          # 必填。等于目录名，kebab-case
name: 训练充分性/训练动力学          # 必填。给人读的短名
goal: 一句话诊断目标                # 必填
stages:                           # 必填。按执行顺序排列
  - id: 0                         # 整数，不必连续（orient 按列表顺序推进）
    name: 探测记录源
    done_when:                    # 阶段完成的判定条件（见下）
      artifacts: ["probe_summary.json"]
      findings_marker: "现象"
      manual: false
    prereqs:                      # 进入本阶段的前置条件（见下）
      - desc: 记录源问题已答
        check: "question:loss-source"
    pause_after: false            # true = 本阶段完成后必须停下向用户汇报
    subagent_ok: true             # false = 必须主 agent 亲自做
    charts: [horizon-degradation] # 可选。本阶段要画的图（chartbook recipe id）
produces:                         # 可选。声明"我是生产者"（见下）
  id: setup
  manifest: setup_manifest.json
  marker_files: [predictions.csv]
upstream:                         # 可选。声明"我消费谁的产物"（见下）
  - product: setup
    required: true
  - product: model_profile
    required: false
materials:                        # 可选。本 playbook 需要用户提供哪些材料
  required: [predict, truth]
  optional: [model_code]
variants:                         # 可选。条件变体（见下）
  - id: grouped
    when: "config:units_multiple"
    unlocks_stages: [3]
questions:                        # 可选。本 playbook 要问用户的问题（见下）
  - id: loss-source
    stage: 0
    ask: "训练 loss 记录在哪里、每行什么格式？（贴 2-3 行样例）"
    why: "猜错 schema 会污染全部下游"
    options: ["结构化 CSV/JSON", "文本日志", "只在 checkpoint 里", "没记录"]
    default: null
    skip_if: "artifact:loss_records.csv"
evidence_lines:                   # 可选。独立证据线登记（见下）
  - id: composition-regression
    stage: 3
    output: composition_effects.json
upgrade_rule: "两线 Spearman 排名一致才把嫌疑从「现象」升「假设」"
crystallize_min_cases: 5          # 可选。固化需要几个互异的成功 case，默认 3
---
```

### stages —— 阶段列表

**done_when**：真相以落盘产物为准，不以 agent 的记忆为准。三种判定方式，可组合可单用：

- `artifacts`：文件 glob 列表，每个 glob 在工作目录至少命中一个文件；
- `findings_marker`：FINDINGS.md 出现指定状态词（只能用 §3 的四个保留字）；
- `manual: true`：主 agent 人工判定后写 state——机器判不了的阶段才用。

`done_when.artifacts` 与 `prereqs.check` 里的 `json:` 路径可以写 `{round}` 占位，orient 用
`diagnose_state.json.round`（缺省 1）替换。按轮重复的阶段把产物放 `rounds/round_{round}/`，
`experiment_log.py new-round` 把 round 加一，这些阶段就自动回到未完成。

**prereqs**：每条 = 一句人话 `desc` + 一个机器可判的 `check`（DSL 见 §2）。
`desc` 以"（可选）"开头的不阻塞推进，只作提示。

**pause_after**：`true` = 完成后必须停下向用户汇报、等用户点名下一步。
产"现象清单"的事实阶段必须设 `true`（§7）。

**subagent_ok**：`false` = 不许外包 subagent，主 agent 亲自做（典型：反驳门、结论阶段）。

**charts**：本阶段要画的图，值是 chartbook recipe id（必须存在于 `chartbook/recipes/`，
拼错加载期报错）。orient 按各 recipe 声明的材料需求逐图报告"可画 / 缺材料跳过"。

加载期硬校验（`_validate_frontmatter` 强制，违反则加载失败）：

1. **阶段闸**：声明了 `charts:` 的阶段，`done_when.artifacts` 必须含 `"INDEX.md"`
   （`build_index.py` 产物）——画完图必须建索引才算阶段完成。
2. **结论闸**：`done_when.artifacts` 含 `"CONCLUSION.md"` 的阶段必须同时含
   `"gate_reports/conclusion_gate.json"`（`conclusion_gate.py` 通过后生成）——没过闸就没有结论。

### produces / upstream —— 生产者与消费者

playbook 之间唯一合法的协作方式：一方声明 `produces`，另一方声明 `upstream`。

**produces**：`id` 产物 id，全引擎唯一（加载期查重）；`manifest` 机器契约文件名
（落在产物工作目录），manifest 记录了 `inputs` 指纹则自动启用过期检测（§2）；
`marker_files` 产物有效性核验清单——缺任何一个视为产物无效。

**upstream**：`product` 引用某 playbook 的 `produces.id`（引用不存在的 id 加载期报错）；
`required: true` 时缺产物 → orient 打印"立即内联生产"指令并阻塞开工，**不问用户**；
`required: false` 时缺产物 → 问用户三选一（现在跑 / 链接已有目录 / 放弃并在结论声明代价）。

### materials —— 材料需求

材料 id 全集见 `engine_common.MATERIAL_IDS`，盘点流程见 `references/intake.md`。

- `required`：状态 unknown（没问）或 absent（用户确认没有）都阻塞开工；
  absent 可经用户确认降级后继续（用户写 `degraded_ok`）；
- `optional`：不阻塞，只影响变体激活与可画的图。

### variants —— 条件变体

`when`（DSL）成立时 `unlocks_stages` 的阶段才启用；不成立时 orient 标
"变体未激活（跳过，不阻塞）"。典型：多机组才需要的分组分析阶段。

### questions —— 提问声明

只声明本目标特有的、可预知的问题（引擎级"恒问五类"是主 agent 常备纪律，不在此重复，见 §7）。

- `id`：稳定标识；答案落 `diagnose_config.json` 的 questions 块；
- `stage`：进入该 stage 前必须已答（除非有 default 或 skip_if 命中）；
- `ask` / `why` / `options`：问题原文、为什么必须问、给用户的选项；
- `default: null` = 必问；给了默认值可不问（orient 标"✓默认"，不阻塞，
  采用默认须在 PROGRESS.md 记一行）；
- `skip_if`：可选，DSL 成立 = 证据已能回答，不问不阻塞。

### evidence_lines / upgrade_rule —— 证据线

`evidence_lines` 登记独立证据线（哪个阶段、产出哪个文件）。声明 ≥2 条时
`upgrade_rule` **必填**：写清什么条件下才能把结论从「现象」升「假设」（通常是多线排名一致）。

### crystallize_min_cases

固化三关之关 1"多样性"所需互异成功 case 数，默认 3（`engine_common.CRYSTALLIZE_MIN_CASES_DEFAULT`）。

## 2. check-DSL（prereqs.check / variants.when / questions.skip_if 通用）

| 表达式 | 成立条件 |
|---|---|
| `config:<dotted.key>` | `diagnose_config.json` 里该键存在且值为真（非空/非 null/非【待补】） |
| `file:config.<dotted.key>` | 该 config 键的值是路径，且文件/目录真实存在 |
| `artifact:<glob>` | 工作目录下该 glob 至少命中一个文件 |
| `stage:<id>` | 该阶段已完成（按 done_when 判定） |
| `question:<qid>` | 该问题已答（用户答的、profile 带的、默认值、实验线、证据自答都算） |
| `material:<id>` | 该材料状态为 present（id 必须 ∈ `engine_common.MATERIAL_IDS`，拼错报错） |
| `json:<文件路径>:<点路径>` | 文件存在且该点路径的值为真（`false`/`null`/空 都算假）；路径可含 `{round}` |
| `product:<id>` | 该产物已就绪（见下；id 必须是某 playbook 的 `produces.id`，拼错报错） |
| `not <expr>` | 取反（只允许套一层） |

不追求图灵完备：组合逻辑写不下就拆成多条 prereq，或用 `manual` 逃生门。

### 产物注册（product: 判定依据）

消费者在自己 `diagnose_config.json` 的 `products` 块登记：

```json
"products": {"setup": {"workdir": "./setup", "status": "built", "accept_stale": false}}
```

`status`：`built` 本次会话内联生产；`linked` 用户链接的已有目录；`declined` 用户放弃
（只有 `required: false` 允许，结论里必须声明缺了它）。

`product:<id>` 判"就绪"须同时满足：status ∈ {built, linked}、`marker_files` 全部存在、
无未经用户确认的过期（stale）。

### 内联生产的规矩

- 生产者在以产物 id 命名的子目录里跑（`./setup/` 等），有自己独立的 `diagnose_config.json`；
- 内联生产时把父 config 的 materials 和 questions 块拷进子 config——用户答过的不重复问；
- 上游产物"拥有"的问题（如 setup 的 freq、对齐键），下游 playbook 不得重复声明（加载期查重报错）；
- 生产者自己也可有 upstream；加载期做环检测。

### 过期检测（stale）

- manifest 记 `inputs.{材料id: {path, fingerprint}}`；每次消费前拿当前材料指纹与
  manifest 对账，不一致 → status=stale；
- stale 时让用户二选一：重建产物，或写 `accept_stale: true` 照用（留痕，结论里声明）；
- 输入文件消失也算 stale；
- 代码也是依赖：setup 的 manifest 把适配器脚本指纹一并记进 inputs——适配逻辑变了，产物即过期。

指纹算法（`engine_common.file_fingerprint`）：文件 ≤64MB 全量 sha256；更大的取
大小 + 头 1MB + 尾 1MB 的 sha256；指纹带版本前缀 `v1:`。已知盲区：同尺寸、只改中段的
超大文件检测不到——要更强保证，调大 `FULL_HASH_MAX_BYTES` 走全量哈希。

### 单写者纪律

frontmatter 声明 = 意图；orient 解析出的状态 = 观测事实。agent 只允许写
`config.products` 的登记字段（workdir / status / accept_stale），**绝不手改判定结果**。

## 3. findings_marker 保留字表

`done_when.findings_marker` 只允许四个词（FINDINGS.md 状态枚举，模板见
`templates/FINDINGS.template.md`）：

> **现象 / 假设 / 已证实 / 被推翻**

不要自造措辞。

## 4. 正文必备节（agent 菜谱）

正文按以下八节写，顺序固定：

1. **问题框定与首要陷阱**——本诊断目标最易犯的归因错误，放最前面。

2. **逐阶段菜谱**——每个阶段写清：目标 / 输入 / 脚本菜谱 / done 判据。脚本菜谱含
   伪代码、关键公式、落盘产物 schema、自足 summary 要求，以及**脚本验证步**。硬规则：
   - 分析脚本由 agent 运行时现场生成，放工作目录 `analysis_scripts/`；
   - 每个脚本先过本节声明的验证步（对账 / 合成小样自检）其产出才可信；
     验证结果记 PROGRESS.md（crystallize 只快照有验证记录的脚本）；
   - golden 覆盖的阶段另有**生成闸**：脚本先过 `scripts/gen_gate.py`（在结果已知的
     金标准上算对）才许碰真实数据（§5）。正文里写出闸命令；
   - 声明 `charts:` 的阶段，正文写清每张图的调用命令与参数——图一律调 chartbook
     预写脚本，禁止现场重写（见 engine-core 的 chartbook 豁免条款）；
   - 结论阶段菜谱必须含**归因闸**：写 CONCLUSION.md 前跑 `scripts/provenance.py`，
     末尾附 Provenance 块（代码 hash + 数据 hash + 金标准自检），
     细则见 `references/conclusion-reporting.md`。

3. **证据升级规则**——哪些证据组合能把结论从"现象"升"假设"、从"假设"升"已证实"。
   每条规则必须对应到结论三道门之一（见 `references/mechanisms.md`）。

4. **停顿点与汇报**——每个 `pause_after` 阶段完成后：向用户汇报什么、请用户点名什么。

5. **subagent 拆分建议**——哪些阶段可并发外包、分片输出的 `--out` 命名约定
   （防止两个 subagent 写同一文件，见 `references/subagent-briefs.md`）。

6. **结论模板与本 playbook 特有的反驳门条目**。

7. **材料降级说明**（声明了 materials 时必写）——required 材料 absent-confirmed 时
   怎么降级：哪些阶段跳过、结论上限降到什么。主 agent 据此向用户描述降级代价，
   再请求 `degraded_ok` 确认。

8. **chartbook 覆盖声明**（硬规则）——新写/改写 playbook 时把 `chartbook/recipes/`
   **全部** recipe 逐条过一遍：适用的写进对应 stage 的 `charts:`；不适用的在本节列
   id + 一句跳过理由。每个 recipe 必须出现在"声明"或"跳过"之一。跳过理由要区分
   **结构性不适用**（如"需 ≥2 模型，本目标只有单模型"）与**默认不看但可选**——
   `charts:` 里的图只是默认草绘集，运行时用户经"图表选择门"可增删，跳过的图仍可临时点名。

## 5. golden/ 金标准基线（每个 playbook 必带）

golden 是一套答案已知的小数据集：解析式构造、植入已知效应，每个阶段"算对了该得什么数"
是确定的。用途是当闸：agent 现场生成的脚本先在 golden 上跑，算对了才许碰真实数据。

```
playbooks/<id>/golden/
├── make_golden.py     # 确定性生成器：解析式构造，零随机（Date/random 都不许用）
├── <输入数据文件>      # 小体量（几 KB），植入已知效应，随仓库提交
├── manifest.json      # 机器契约：inputs / args（各阶段脚本的 CLI）/ expect（断言）
└── reference/*.py     # 参考实现：按菜谱写的可执行示例，也是 CI 端到端的被闸对象
```

manifest 的 expect 断言算子：`eq / ge / le / between / contains / first_is /
argmax / argmin / exists`。**每个 stage 条目必须带 `reference` 字段**——
`test_gen_gate` 靠它收集过闸对象；不声明就不进 CI，会被
`test_every_playbook_has_golden` 抓住。

规则：

- **期望值来自 reference 实跑并留容差**，不是拍脑袋写的。金标准算错了 → 改生成脚本，
  不改期望值。真要改期望值，必须连 `make_golden.py` 一起改并重跑 pytest
  （`test_gen_gate.py` 用 reference 验证自洽）。
- **植入难例形态，不只植最容易检出的形态**：正文 §1"首要陷阱"列的每个易误判形态
  （渐变 onset、诱饵变量、集中 vs 普遍……），golden 至少植入一个对应难例；
  expect 断言必须能区分"检出了效应"与"答对了形态"。
- **种子豁免边界**："零随机"约束 `make_golden.py` 的数据构造；分析/图脚本内部的
  固定种子置换检验允许——但种子必须是显式 CLI 参数并写进产物 JSON，期望值来自
  reference 用同一种子实跑；改种子 = 改期望，连 manifest 一起改并重跑 pytest。
- 覆盖不了的阶段（依赖真实记录源格式、真实模型入口等）在 manifest 的 note 写明原因，
  由菜谱声明的对账/植入回收验证步兜底。

## 6. 预留接口位置（只占位，实施排后续轮）

- **`playbooks/<id>/heldout/`（held-out 场景库）**：固化三关之关 2 的场景来源——
  从未参与开发调参的输入 + 期望，结构与 golden/ 相同。落地前，关 2 由
  crystallize_record.json 的 heldout 记录（passed + input_hash 不重合）人工保障。
- **`regression/baselines/`（机制脚本回归基线，引擎级目录）**：存每个 playbook 在其
  金标准上的期望输出快照。任何 `scripts/` 机制脚本改动 → 重跑全部 playbook 金标准
  逐一比对，并重跑固化代理快照，确认引擎改了、固化产物输出不变。
- **experiment_line v0→v1 迁移**：profile 中实验线引用现为
  `interface_version: v0-draft`（占位不生效，见 `references/crystallize.md`）；
  project-context 消费接口定稿后统一迁 v1 并启用合并。

## 7. 编写纪律

- **产物自足**：每个落盘 JSON/CSV 自带完整数字与形状描述。判读只读产物 summary，
  不读图（PNG）、不读原始大文件。
- **事实阶段显式标出**：哪个阶段产"现象清单"（只写观察和数字，禁机制语言）在正文写明，
  且该阶段 `pause_after: true`。
- **量纲纪律**：跨模型/跨组不可比的量只比排名（Spearman），不把数值 pool 在一起。
- **恒问五类不重复声明**：引擎级五类必问问题（见 `references/question-discipline.md`）
  是主 agent 常备纪律，questions 里只声明本目标特有的问题。
- **default 与菜谱同法**：questions 的 default 文案里含判据/算法的（如"相对某基线窗口"），
  必须与对应 stage 菜谱实际用的方法一致。写完 frontmatter 自查：每个带方法词的 default
  都能在正文菜谱里找到同一方法。
