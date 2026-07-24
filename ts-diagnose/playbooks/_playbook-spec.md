# Playbook 接口规范（_playbook-spec）

playbook = 一个诊断目标的完整定义：**frontmatter**（YAML，`orient.py` 机器读，驱动阶段/前置/提问/变体判定）+ **正文**（agent 读的菜谱，指导运行时生成分析代码与判读）。新增 playbook 按本规范写：**每个 playbook 一个独立目录** `playbooks/<id>/`，正文在 `<id>/playbook.md`，金标准基线在 `<id>/golden/`（§6）。三个 playbook 之间零共享内联、互不引用（Layer 1 纪律，test_layering.py 守卫）。

## 1. Frontmatter schema

```yaml
---
id: training-sufficiency          # 必填，= 文件名（不含 .md），kebab-case
name: 训练充分性/训练动力学          # 必填，人读短名
goal: 一句话诊断目标                # 必填
stages:                           # 必填，按执行顺序；id 为整数（不必连续，orient 按列表顺序推进）
  - id: 0
    name: 探测记录源
    done_when:                    # 完成判定（真相以产物为准），三种可组合/择一：
      artifacts: ["probe_summary.json"]   # 每个 glob 至少命中工作目录一个文件
      findings_marker: "现象"              # 该词出现在 FINDINGS.md 中（用下面的保留字表）
      manual: false                        # true = 由主 agent 人工判定后写 state（逃生门）
    prereqs:                      # 进入前置，check 用 DSL（见 §2）；desc 以（可选）开头 = 不阻塞
      - desc: 记录源问题已答
        check: "question:loss-source"
    pause_after: false            # true = 本阶段完成后强制停顿，主 agent 向用户汇报并等点名
    subagent_ok: true             # false = 必须主 agent 亲自做（如反驳门/结论）
    charts: [horizon-degradation]     # 可选。本阶段消费的 chartbook recipe id（须存在于 chartbook/recipes/）；orient 按 needs_materials × 盘点结果逐图报可画/缺材料自动跳过
                                       # 阶段闸：声明了 charts 的阶段，done_when.artifacts 必须含 "INDEX.md"（build_index.py 产物）——画完不建索引不算阶段完成（加载期 _validate_frontmatter 校验，见 test_materials.py::test_chart_stage_requires_index_artifact）
materials:                        # 可选。本 playbook 的材料需求（intake 引擎级机制）
  required: [predict, truth]      #   unknown/absent 均阻塞开工（absent 可经用户确认降级）
  optional: [model_code]          #   不阻塞；驱动变体/图表可用性
variants:                         # 可选。条件变体：when 不成立 → unlocks_stages 里的阶段
  - id: grouped                   #   在 orient 中标"变体未激活（跳过，不阻塞）"
    when: "config:units_multiple"
    unlocks_stages: [3]
questions:                        # 提问声明（引擎提问纪律的载体，见 references/question-discipline.md）
  - id: loss-source               # 稳定 id；答案落 diagnose_config.json 的 questions 块
    stage: 0                      # 进入该 stage 前必须已答（或有 default / skip_if 命中）
    ask: "训练 loss 记录在哪里、每行什么格式？（贴 2-3 行样例）"
    why: "猜错 schema 会污染全部下游"
    options: ["结构化 CSV/JSON", "文本日志", "只在 checkpoint 里", "没记录"]
    default: null                 # null = 必问；非 null = 可默认（orient 标 ✓默认，不阻塞）
    skip_if: "artifact:loss_records.csv"   # 可选：DSL 成立 = 证据自答，不问不阻塞
contexts:                         # 可选。外部分析上下文（泛化 ask-then-embed 三分支）
  - id: upstream-analysis
    name: 预测侧上下文
    workdir_key: linked_workdir   # config 里存路径的键
    status_key: linked_status     # config 里存状态的键：linked / declined /（空 = absent）
    marker_files: ["FINDINGS.md"] # linked 有效性核验：目录下这些文件须存在
    on_absent: ask                # absent 时主 agent 必须先问用户（orient 只打印指引）
    provider_playbook: model-audit      # 可选：谁能生产本上下文（触发嵌入执行提示，engine 内 playbook 用此字段）
    # provider_skill: pv-model-analysis  # 二选一的旧式/外部形态：provider 是外部技能而非 engine 内 playbook 时用这个（legacy，engine 内一律用 provider_playbook）
    trigger_material: model_code        # 可选：该材料 present 才提议嵌入（须为合法材料 id）
evidence_lines:                   # 可选。独立证据线登记（多证据线一致性判定的依据）
  - id: composition-regression
    stage: 3
    output: composition_effects.json
upgrade_rule: "两线 Spearman 排名一致才把嫌疑从「现象」升「假设」"   # evidence_lines ≥2 时必填
crystallize_min_cases: 5          # 可选。固化三关之关1（多样性）所需的互异成功 case 数，
                                  # 默认 3（engine_common.CRYSTALLIZE_MIN_CASES_DEFAULT）
---
```

## 2. check-DSL（prereqs.check / variants.when / questions.skip_if 通用）

| 表达式 | 语义 |
|---|---|
| `config:<dotted.key>` | `diagnose_config.json` 该键存在且值为真（非空/非 null/非【待补】） |
| `file:config.<dotted.key>` | 该 config 键的值是路径且文件/目录存在 |
| `artifact:<glob>` | 工作目录下该 glob 至少命中一个文件 |
| `stage:<id>` | 该阶段已完成（done_when 判定） |
| `question:<qid>` | 该问题已答（含 profile/默认/实验线/证据自答） |
| `material:<id>` | config.materials 该材料 status 为 present（id 必须 ∈ engine_common.MATERIAL_IDS，拼错报错） |
| `not <expr>` | 取反（只允许一层） |

不追求图灵完备：组合逻辑写不下就拆成多条 prereq，或用 `manual`。

## 3. findings_marker 保留字表

`done_when.findings_marker` 只允许下列词（FINDINGS.md 的状态枚举，见 templates/FINDINGS.template.md）：**现象 / 假设 / 已证实 / 被推翻**。不要用自造措辞——文本标记本就脆弱，收敛到保留字才可判定。

## 4. 正文必备节（agent 菜谱）

1. **问题框定与首要陷阱**——本目标最容易犯的归因错误（对应 pv-station-influence 的"震荡≠有罪"层级），放最前。
2. **逐阶段菜谱**——每阶段：目标 / 输入 / **脚本菜谱**（伪代码 + 关键公式 + 落盘产物 schema + 自足 summary 要求 + **脚本验证步**）/ done 判据。分析脚本由 agent 运行时生成进工作目录 `analysis_scripts/`，每个脚本必须先过本节声明的验证步（对账 / 合成小样自检）才可信其产出——验证结果记 PROGRESS.md（crystallize 只快照有验证记录的脚本）。**golden 覆盖到的阶段另有生成闸硬规则**：先过 `scripts/gen_gate.py`（金标准算对）才许碰真实数据（§6），正文里要写出闸命令。声明了 charts 的阶段，正文菜谱写清各图的调用命令与参数（预写脚本，禁现场重写；见 engine-core chartbook 豁免）。
   结论阶段的菜谱必须包含**归因闸**：写 CONCLUSION.md 前跑 `scripts/provenance.py`，末尾附 Provenance 块（代码 hash + 数据 hash + 金标准自检），见引擎 references/conclusion-reporting.md。
3. **证据升级规则**——哪些证据组合能把结论从"现象"升"假设"升"已证实"；每条规则必须映射到结论三道门之一（references/mechanisms.md）。
4. **停顿点与汇报**——`pause_after` 阶段完成后向用户汇报什么、请用户点名什么。
5. **subagent 拆分建议**——哪些阶段可并发、分片 `--out` 命名约定（防竞态，见 references/subagent-briefs.md）。
6. **结论模板与本 playbook 特有反驳门条目**。
7. **材料降级说明**（声明了 materials 时）——required 材料 absent-confirmed 时本
   playbook 怎么降级（哪些阶段跳过/结论上限降到什么），主 agent 据此向用户描述
   降级成本再请求 degraded_ok 确认。
8. **chartbook 覆盖声明**（硬规则，弱模型压力测试教训：作者没有清单就会漏掉标准分析
   维度——日内时段集中度整段缺席）——新写/改写 playbook 时**逐条过一遍**
   `chartbook/recipes/` 全部 recipe：适用的进对应 stage 的 `charts:` 声明；不适用的在
   本节列出 id + 一句跳过理由（如"需 ≥2 模型，本目标单模型"）。全部 recipe 必须出现在
   「声明」或「跳过」之一，不许缺席。声明进 `charts:` 的图＝默认草绘集（运行时经
   engine-core「图表选择门」让用户增删）；跳过的图仍在选择门的「可加画池」里，用户可
   临时加画——所以跳过理由要写清是"结构性不适用"（如需 ≥2 模型）还是"本目标默认不看
   但可选"。

## 5. golden/ 金标准基线（每个 playbook 必带）

```
playbooks/<id>/golden/
├── make_golden.py     # 确定性生成器：解析式构造，零随机（Date/random 都不许）
├── <输入数据文件>      # 小体量（几 KB），植入已知效应，随仓库提交
├── manifest.json      # 机器契约：inputs / args（各阶段脚本 CLI）/ expect（断言 DSL）
│                      #   op ∈ eq/ge/le/between/contains/first_is/argmax/argmin/exists
│                      #   每个 stage 条目必带 reference 字段（test_gen_gate 据此动态
│                      #   收集过闸对象——不声明就不进 CI，会被 test_every_playbook_has_golden 抓）
└── reference/*.py     # 按菜谱写的参考实现：CLI 契约的可执行示例 + CI 端到端被闸对象
```

- **期望值来自 reference 实跑并留容差**；生成脚本金标准算错 → 改脚本不改期望；要改期望，
  必须连 make_golden.py 一起改并重跑 pytest（test_gen_gate.py 会用 reference 验证自洽）。
- **植入难例形态，不只植最易检出形态**（弱模型压力测试教训：golden 只植阶跃、真实数据是
  渐变 ramp，最大分离切分点系统性晚于起始点，闸全绿但"何时开始"答错一周）——正文 §1
  「首要陷阱」里列的每个易误判形态，golden 至少植入一个对应难例（渐变 onset、诱饵变量、
  集中 vs 普遍等），expect 断言必须能区分"检出效应"与"答对形态"。
- **种子豁免边界**：「零随机」约束的是 make_golden 的数据构造；分析/图脚本内的
  **固定种子置换**允许——种子必须是显式 CLI 参数并写进产物 JSON，期望值来自
  reference 同种子实跑；改种子=改期望，须连 manifest 一起改并重跑 pytest。
- 覆盖不了的阶段（依赖真实记录源格式/真实模型入口）在 manifest note 写明原因，
  由菜谱声明的对账/植入回收验证步兜底。

## 6. 预留接口位置（本轮只占位，实施排后续轮）

- **`playbooks/<id>/heldout/`（held-out 场景库）**：固化三关之关2 的场景来源——从未参与
  开发调参的输入 + 期望，结构与 golden/ 同构（manifest + 数据）。落地前，关2 由
  crystallize_record.json 里的 heldout 记录（passed + input_hash 不重合）人工保障。
- **`regression/baselines/`（机制脚本回归 evals，引擎级目录）**：存每个 playbook 在其
  金标准上的期望输出快照；任何 `scripts/` 机制脚本改动 → 重跑全部 playbook 金标准逐一
  比对，并重跑固化代理快照确认隔离生效（引擎改了、固化产物输出不变）。
- **experiment_line v0→v1 迁移**：profile 中实验线引用现为 `interface_version: v0-draft`
  （占位不生效，见 references/crystallize.md）；project-context 消费接口定稿轮统一迁移
  到 v1 并启用合并。

## 7. 编写纪律

- **产物自足**：每个落盘 JSON/CSV 带完整数字与形状描述，判读只读产物 summary，不读图（PNG）、不读原始大文件。
- **显式标出事实阶段**：哪个阶段产"现象清单"（禁机制语言）要在正文写明，且该阶段 `pause_after: true`。
- **量纲纪律**：跨模型/跨组不可比的量只比排名（Spearman），不 pool 数值。
- 引擎级恒问五类（question-discipline.md）**不需要**在 questions 里重复声明——那是主 agent 的常备纪律；questions 只声明本目标特有的、可预知的问题。
- **default 与菜谱同法**：questions 的 default 文案里若含判据/算法（如"相对某基线窗口"），
  必须与对应 stage 菜谱实际用的方法一致——两套判据并存时结论可能分岔（弱模型压力测试
  G-6）。写完 frontmatter 自查一遍：每个带方法词的 default 都能在正文菜谱找到同一方法。
