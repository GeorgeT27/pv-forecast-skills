---
name: ts-diagnose
description: 泛化的时序模型诊断引擎——同一套已验证 workflow（orient 续跑、事实/解释隔离、结论三道门、多证据线、subagent 编排、提问一等公民）+ 可插拔 playbook（训练充分性/训练动力学、鲁棒性、变量重要性）。当用户对时序/预测任务提出**新的诊断目标**时使用："训练是否充分/是不是 batch 不足/训练分配（chunk/fold 构成）有没有问题/为什么 loss 震荡或收敛慢"（training-sufficiency）、"结论/模型在扰动与分组切片下稳不稳"（robustness）、"哪个输入变量对误差影响最大"（feature-importance）。**负面清单（这些场景用专用技能，不用本引擎）**：光伏预测结果评估/指标 Excel/月度归因 → pv-result-analysis；训练站负迁移归因（哪个站拖累留出站）→ pv-station-influence；从模型代码生成参考档案 → pv-model-analysis。本引擎的成熟运行可经 references/crystallize.md 固化成新的薄专用技能（profile.yaml 记住已答问题，下次不再问）。
---

# ts-diagnose：时序诊断引擎（引擎 + playbook + profile）

三个概念：**引擎**（本技能，领域无关的 workflow 与机制脚本）、**playbook**（一个诊断目标的阶段/提问/菜谱定义，`playbooks/`）、**profile**（一次成功运行固化下来的答案与脚本，属于薄专用技能）。一次运行 = 一个工作目录 + 一个 playbook（+ 可选 profile）。

## Step 0：Orient —— 每次进入先跑

```bash
python3 "<ENGINE>/scripts/orient.py"                                 # 已有 config：报阶段+问题清单+前置
python3 "<ENGINE>/scripts/orient.py" --playbook training-sufficiency  # 首次进入：绑定 playbook
python3 "<ENGINE>/scripts/orient.py" --profile <skill>/profile.yaml   # 固化技能入口：合并已答问题
python3 "<ENGINE>/scripts/orient.py" --goto 3                        # 直达校验
```

（`<ENGINE>` = `/Users/tqa946816/Documents/华为/光伏预测/结果分析skill/ts-diagnose`。）真相以产物为准：orient 每次重扫工作目录，报第一个未完成阶段、变体跳过、上下文三分支、**问题清单**（✓已答/✓固化/✓实验线/✓默认/✗未答·阻塞 Stage N）与目标阶段前置。没有 config → 它会打印 playbook 菜单与 project-context 实验线，回来按「提问纪律」收集。

**Step 0.5（可选）**：orient 发现 project-context 时会列出实验线——AskUserQuestion 问用户是否用某条预填；同意则把实验线 json 路径写进 `config.experiment_line`，orient 自动合并已填字段（【待补】不搬、已填不覆盖），对应问题标 ✓实验线。运行中补齐的【待补】路径按仓库纪律**补写回实验线 json**。

## 提问纪律（一等公民——本引擎与专用技能的最大差异）

引擎面向没见过的任务，**不许用假设填补不确定**。细则见 `references/question-discipline.md`，硬规则：

1. orient 报 ✗ 的问题，在其 stage 开工前**必须** AskUserQuestion——同一阶段的多个未答题合并成一次提问（每题带 playbook 声明的 options）。
2. **引擎级恒问五类**（无论 playbook 有没有声明）：① 数据 schema/单位/口径不明；② 成功判据未定义；③ 证据不足以升级结论（问"接受降级还是补证据"，列补证据成本）；④ 破坏性/昂贵操作（GPU 重训、覆盖已有产物）；⑤ 多候选文件/版本选哪个。
3. 有 default 的问题可不问，但采用默认须在 PROGRESS.md 记一行"按默认"。
4. 答案落 `diagnose_config.json` 的 questions 块：`{"<qid>": {"answer": "...", "source": "user", "date": "YYYY-MM-DD"}}`——这是将来 crystallize 的原料。
5. **subagent 无提问权**：所有停顿点与提问只在主 agent。

## 执行模型

- **阶段由 playbook 定义**（frontmatter，规范见 `playbooks/_playbook-spec.md`）；orient 是通用求值器。推进 = 照 playbook 正文该阶段的菜谱做。
- **分析代码运行时生成**：引擎不带分析脚本。按菜谱把脚本写进工作目录 `analysis_scripts/`，**每个脚本先过菜谱声明的验证步**（对账/合成小样/植入回收），验证结果记 PROGRESS.md——没验证记录的脚本产出不可引用，crystallize 也不快照它。
- **事实阶段 ⏸**：playbook 标 `pause_after` 的事实提取阶段产「现象清单」（观察+数字+来源，**禁机制语言**），完成后停下向用户汇报，等用户点名要深挖的项再进结论阶段。
- **上下文三分支**：playbook 声明的外部上下文（contexts）absent 时必须先问用户（要不要先建立/嵌入跑），linked 时核验 marker 文件才消费，declined 时结论注明缺失。
- **subagent 编排**：重活（大日志解析、批量计算、逐产物事实提取）外包，brief 模板见 `references/subagent-briefs.md`；分片各写各的 `--out`，主 agent 合并；`diagnose_config/diagnose_state/PROGRESS/FINDINGS` 只由主 agent 写。
- **上下文预算**：产物自足（json 带完整数字与形状描述），判读读 json 不读 PNG、不读原始大文件；每阶段落盘可断点续跑。

## 结论纪律（精简硬规则，细则见 references/mechanisms.md）

1. **三道门**：稳健性门槛（配对检验+剔极端方向不变）→ 假设登记（HYPOTHESES.md 先预测后看数）→ 反驳门（替代解释逐条排除或显式降级）。三门全过才可在 FINDINGS.md 标「已证实」。
2. **多证据线**：playbook 声明 ≥2 条 evidence_lines 时，按其 upgrade_rule（通常 Spearman 排名一致）才升「假设」；单证据线结论上限「现象」。
3. **功效诚实**：样本/单元数不足（playbook 给阈值，默认 <10）只报排名与趋势，不报显著性。
4. FINDINGS.md 状态只用保留字：**现象/假设/已证实/被推翻**（orient 判定依赖）。
5. 结论写完按 `references/conclusion-reporting.md` 产 CONCLUSION.md 并**直接呈现给用户**，不只丢路径。

## Playbook 目录

| id | 目标 | 深度 |
|----|------|------|
| `training-sufficiency` | 训练充分性/训练动力学（收敛、batch/数据量、chunk 构成与分配） | 深（自 pv-station-influence 泛化，已影子验证） |
| `robustness` | 结论/模型在扰动、分组切片、子期下的稳定性 | 标准 |
| `feature-importance` | 哪个输入变量对目标指标影响最大 | 标准 |

新目标按 `playbooks/_playbook-spec.md` 写新 playbook——frontmatter 会被 orient 直接执行，先跑 `pytest scripts/tests` 确认可解析。

## Crystallize：固化成专用技能

一次运行到达结论阶段、且用户表示"以后还要跑这类分析"（或运行后回顾时你主动提议）→ 按 `references/crystallize.md` 把本次运行固化成薄专用技能（SKILL.md + profile.yaml + 验证过的脚本快照）。固化后该技能经 `orient.py --profile` 进入，已答问题不再问。三个 PV 专用技能是本机制概念上的先例（先于引擎存在，原样保留，不经 profile）。

## 常见错误

- ❌ orient 报 ✗ 的必答题没问用户就靠"合理假设"开工（schema 猜错污染全部下游）。
- ❌ 生成的分析脚本没过验证步就引用其产出（或 crystallize 快照了无验证记录的脚本）。
- ❌ 事实阶段写机制语言（"因为遗忘/因为 batch 小"）——现象与解释物理隔离，解释只在结论阶段。
- ❌ 单证据线就下"某成员/某变量有害"的判定（噪声易带偏；按 upgrade_rule 两线一致才升级）。
- ❌ 跨 series/模型 pool 不可比量纲的数值（只比 Spearman 排名）。
- ❌ subagent 写 state/PROGRESS/FINDINGS/config，或两个 subagent 追加同一个文件（分片各写各的 `--out`）。
- ❌ 把 PNG/原始日志/大 parquet 读进上下文（一切解析与计算在脚本内落盘）。
- ❌ 上下文 [absent] 不问用户就开跑，或 linked 时不核验 marker 就消费。
- ❌ 用户的任务其实命中专用技能（见 description 负面清单）却用引擎从头问一遍。
- ❌ 忘了把运行中补齐的实验线【待补】路径写回 project-context（下次还得问）。

## 运行后回顾（每次实跑收尾必做）

1. 回顾本次执行轨迹：哪条指令/菜谱缺失或有歧义、哪个生成脚本被迫返工、哪个问题该预声明进 playbook questions；
2. 修正写回：菜谱问题 → 改对应 `playbooks/<id>.md`；机制问题 → 改 `scripts/`（跑 pytest）；提问疲劳或漏问 → 调 playbook questions 的 default/skip_if；
3. `CHANGELOG.md` 追加一行（日期 | 改了什么 | 触发反馈原文 | 为什么）；
4. 若用户表示会复用 → 提议 crystallize。
