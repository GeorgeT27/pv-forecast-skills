# 引擎执行核心（engine-core）——命中 playbook 后必读

<!-- 分层说明：SKILL.md（Layer 0）只做路由；本文件承载引擎级执行纪律，与
     playbooks/<id>/playbook.md 一起加载。这里只写领域无关的通用规则；
     具体目标的阶段、公式、陷阱在各 playbook 正文里。 -->

## Step 0：Orient —— 每次进入先跑

**引擎第一纪律：每个回合开工前先跑 orient；本阶段做完再跑一次核对。不凭记忆推进——
真相以落盘产物为准，状态存在文件里，随时可以断点续跑。**

orient 的输出就是你这一回合的行动清单：照它列的 ✗ 未答问题、前置条件、以及末尾的
"恒问五类"自检逐条办。办完一步就重跑 orient 拿下一步，不要一口气脑补多个阶段。

```bash
python3 "<ENGINE>/scripts/orient.py"                                 # 已有 config：报阶段 + 问题清单 + 前置
python3 "<ENGINE>/scripts/orient.py" --playbook <id>                  # 首次进入：绑定 playbook
python3 "<ENGINE>/scripts/orient.py" --profile <skill>/profile.yaml   # 固化技能入口：合并已答问题
python3 "<ENGINE>/scripts/orient.py" --goto 3                        # 直达某阶段做复核
```

orient 每次重扫工作目录，报告：第一个未完成阶段、跳过的变体、上游产物三分支状态、
**问题清单**（✓已答 / ✓固化 / ✓实验线 / ✓默认 / ✗未答·阻塞 Stage N）、目标阶段的前置。
还没有 config 时打印 playbook 菜单与 project-context 实验线，回来按"提问纪律"收集信息。

**Step 0.5（可选）——实验线预填**：orient 发现 project-context 时会列出实验线。用
AskUserQuestion 问用户要不要拿某条实验线预填；同意就把实验线 json 的路径写进
`config.experiment_line`，orient 会自动合并已填字段（【待补】的不搬、已填的不覆盖），
对应问题标 ✓实验线。运行中把【待补】补齐了的，按仓库纪律**写回实验线 json**——
不写回，下次还得重问。

**Step 0.75——材料盘点（playbook 声明了 materials 时）**：orient 报"必需材料未就绪"
→ 按 `references/intake.md` 盘点。流程：

1. 先来一次多选 AskUserQuestion（材料 checklist + "还有别的吗"开放项）；
2. 逐个材料按追问模板补齐路径、格式、schema——y 列、时间列、id 列必须问清，不许猜；
3. 答案落 `config.materials`（status 三值；用户明确说没有 = absent-confirmed；
   required 材料要降级，须用户再确认一次并写 degraded_ok）。

材料状态驱动 `material:` DSL（变体激活、前置、问题跳过都可能引用它）。

### 三道闸（脚本强制，不靠自觉）

1. **入口闸**（orient）：材料没盘点齐 → 状态 `BLOCKED`，orient 只打印追问清单，
   不打印任何阶段/前置信息。盘点不完，看不到下一步。
2. **阶段闸**（`--goto` 护栏 + 图表阶段的 INDEX.md 判据）：`--goto` 想直达一个前置
   不齐的阶段，默认拒绝；必须显式 `--force` 才放行，且会在 PROGRESS 留痕（只有确实
   跳过了未齐前置时才写"跳过前置"）。另外：声明了 `charts:` 的阶段，
   `done_when.artifacts` 必须含 `INDEX.md`——画完图不建索引，不算阶段完成。
3. **结论闸**（`conclusion_gate.py`）：结论阶段的 `done_when.artifacts` 必须含
   `gate_reports/conclusion_gate.json`——结论阶段唯一的完成判据，只能由
   `conclusion_gate.py` 通过后生成（加载期校验，缺了 playbook 直接加载失败）。

## 提问纪律

**不许用假设填补不确定**。细则见 `question-discipline.md`，硬规则五条：

1. orient 报 ✗ 的问题，在其 stage 开工前**必须** AskUserQuestion。同一阶段的多个
   未答题合并成一次提问，每题带上 playbook 声明的 options。
2. **恒问五类**——任务实际用到且信息不明时必须问：
   ① 数据 schema / 单位 / 口径不明；
   ② 成功判据没定义；
   ③ 证据不足以升级结论（问"接受降级还是补证据"，把补证据的成本列出来）；
   ④ 破坏性或昂贵操作（GPU 重训、覆盖已有产物）；
   ⑤ 多个候选文件/版本，不知道选哪个。
   材料入口只阻塞 playbook 声明的 required；optional 或未激活变体材料按需盘点。
3. 有 default 的问题可以不问，但采用默认必须在 PROGRESS.md 记一行"按默认"。
4. 答案落 `diagnose_config.json` 的 questions 块：
   `{"<qid>": {"answer": "...", "source": "user", "date": "YYYY-MM-DD"}}`。
5. **subagent 无提问权**：所有停顿点与提问只发生在主 agent。

## 执行模型

- **阶段由 playbook 定义**（frontmatter，规范见 `playbooks/_playbook-spec.md`）；
  orient 只是通用求值器。推进 = 照 playbook 正文该阶段的菜谱做。菜谱是编号步骤时，
  进入阶段先把各步逐条建 todo，做一步勾一步；标【硬规则】的步骤不得合并、不得跳过。

- **分析代码运行时生成**：引擎不自带分析脚本。按菜谱把脚本写进工作目录
  `analysis_scripts/`，**每个脚本先过菜谱声明的验证步**（对账 / 合成小样 / 植入回收），
  验证结果记 PROGRESS.md。没有验证记录的脚本，其产出不可引用，crystallize 也不会
  快照它。

  **chartbook 豁免**：chartbook（`<ENGINE>/chartbook/`）已经覆盖的图，**必须**直接
  调用预写脚本 `chartbook/scripts/chart_*.py`，禁止现场重写同类图。运行时生成只用于
  chartbook 没有的、playbook 特有的分析。画图这条链上唯一要现场写的代码是薄适配器
  `analysis_scripts/adapter.py`（把用户数据整形成规范长表，样例见
  `chartbook/golden/example_adapter/`）——适配器先过对账两关（行数守恒 + 抽 3 个
  窗口逐值核对）再喂给图脚本，对账记录写 PROGRESS.md。

  **对账两关适用于一切整形脚本**：执行中临时冒出来的、菜谱没预见的数据整形/格式
  转换脚本（宽转长、逐窗聚合、单位换算……）同样必须过对账两关才能消费其产出。
  菜谱没声明验证步 ≠ 免验证。转换口径（聚合公式、缺失值处理）记 PROGRESS.md。

- **图表选择门**（声明了 `charts:` 的阶段，画图前必停一次）。orient 把图分三组：
  ① 声明且可画；② 声明但缺材料（自动跳过）；③ 未声明但材料已满足的"可加画池"。
  各图带六类 category 标签。按序办（orient 也会打印这份清单）：
  1. **一次** AskUserQuestion 多选，**默认全勾 ①**（用户被动接受默认 = 画全套；
     不要自作主张少画）；
  2. 用户取消勾选的图，删掉可以，但**不静默**：PROGRESS.md 记一行 + CONCLUSION 里
     声明覆盖缺口；
  3. 用户可以从 ③ 里勾选加图（跨 playbook 任取，只要材料满足）；② 缺材料的自动
     跳过，不重复问；
  4. 画最终选定集 → 跑 `chartbook/scripts/build_index.py --charts-dir <workdir>/charts`
     生成 `INDEX.md`（按类别分节、只索引本次实际产物；判读从索引进）→ 然后才进
     `pause_after` 停顿汇报。

  **选择门 = 画之前定范围；停顿点 = 画之后定深挖。两者不同，不可合并成一次。**

- **生成闸**：playbook 的 `golden/manifest.json` 覆盖到的阶段，现场生成的脚本必须
  先过 `scripts/gen_gate.py`（静态检查 + 在结果已知的金标准输入上跑一遍），PASS 才许
  碰真实数据；FAIL → 改脚本，不改期望值。闸报告落工作目录 `gate_reports/`。

- **事实阶段 ⏸**：playbook 标了 `pause_after` 的事实提取阶段，产出是"现象清单"
  （观察 + 数字 + 来源，**禁机制语言**——不写"因为"）。完成后停下向用户汇报，等用户
  点名要深挖哪条，再进结论阶段。用户给模糊授权（"挑最强的 / 你看着办"）时的操作
  判据：选**效应量最大且样本数过功效阈值**的那条现象；并列时取证据线更多的。选了
  哪条、按什么判据，PROGRESS.md 记一行。

- **上游产物三分支**：playbook 声明的 `upstream[]` 产物缺失（absent）时——
  - `required: true`：主 agent **立即内联生产**，不问用户。做法：在 `<product-id>/`
    子目录里跑生产方 playbook 的完整正文，写回
    `config.products.<id> = {workdir, status: 'built'}`，然后重跑 orient；
  - `required: false`：AskUserQuestion 三分支——现在内联生产 / 链接已有目录
    （写 workdir + status=linked）/ 放弃（status=declined，结论必须声明缺此产物
    及其代价）。

  linked 或 built 的产物，核验过 manifest 与 marker_files 才能消费；stale（输入材料
  已变）时让用户二选一：重建，或写 `accept_stale=true` 确认沿用（结论必须声明）。
  机制见 `_playbook-spec.md` 的 `produces`/`upstream` 两节。

- **subagent 编排**：重活（大日志解析、批量计算、逐产物事实提取）外包给 subagent，
  brief 模板见 `subagent-briefs.md`。分片任务各写各的 `--out` 输出文件，主 agent 收齐
  后合并；`diagnose_config / diagnose_state / PROGRESS / FINDINGS` 只由主 agent 写。

  **分层原则**：满足三个条件的生产者 playbook（声明了 `produces`、没有结论阶段、
  执行段没有用户裁决与 FINDINGS 写入——如 data-setup、metric-eval），由主 agent 收齐
  questions 答案后按 `Brief-PRODUCER` **整体外包**，主 agent 只做提问、派发、收汇报、
  写 config.products 回填。不满足条件的生产者（model-audit、fact-scan）按各自 §5
  拆分外包。分析类 playbook 由主 agent 亲自执行，只外包其 §5 列出的机械子任务——
  **结论永远由主 agent 落笔**。

- **上下文预算**：产物自足（json 自带完整数字与形状描述），判读读 json，不读 PNG、
  不读原始大文件；每阶段落盘，随时可断点续跑。

## 假设验证循环

分析 playbook 若声明了假设生成器角色（吐 `hypothesis_ledger.json`，如
model-comparison），不在自己内部下结论——结论由引擎编排一个跨 playbook 的循环
在出口处产一次。

**循环步骤**：

1. 生成器 playbook 产出假设账本（`slice_map` + `hypotheses[]`，字段纪律见
   `scripts/hypothesis_ledger.py`），停顿移交，不下结论；
2. 转入验证主脊 `architecture-attribution`：取账本里判别力最高的假设，单变量消融
   干预，判定 confirmed / refuted / undecided；
3. **否证（refuted）且预算未耗尽** → 回生成器提修正假设，标
   `provenance: post-hoc`——不许用同一批数据既生成又确认；
4. 确认 / 预算耗尽 / 生成器提不出新的判别性假设 → 收敛，退出循环；
5. 结论只在循环出口产**一次**，过 `conclusion_gate`（架构因果表述须附「## 消融证据」
   receipt），循环中途不产结论。

**预算阶梯（防死循环）**：单轮干预上限 ~10 次训练；循环总轮数上限 3 轮。

**终止条件**（任一满足即收）：
1. 某假设确认（confirmed）且能解释切片版图；
2. 预算耗尽；
3. 生成器提不出新的判别性假设。

**subagent 外包（强制）**：验证主脊的每条干预必须外包给 subagent 执行，主 agent
只收一条紧凑 receipt（配置 diff + delta + 噪声底对照 + 种子数 + 判定），不吃训练
过程的上下文。brief 模板见
`playbooks/architecture-attribution/references/subagent-brief.md`，不在此重复。

**回退（无 `trainable_framework`）**：`checkpoint`/`experiment_config` 材料
absent-confirmed 时，验证主脊跳过，循环退化为"生成器吐带标注的未验证假设"；
`conclusion_gate` 显式标注该结论未经干预验证——= 现状行为，对老用法零破坏。

## 结论纪律（硬规则；细则见 mechanisms.md）

1. **三道门**——结论阶段逐条过（orient 在产 CONCLUSION.md 的阶段会打印这份清单；
   三门全过，才可在 FINDINGS.md 标「已证实」）：
   - **门 1 稳健性**：配对检验通过，且剔除最极端 10% 样本后方向不变；
   - **门 2 假设登记**：先在 playbook 的假设账本写下预测与 provenance，**然后**才看数；
   - **门 3 反驳门**：替代解释逐条排除；排不掉的，结论显式降级（含 playbook 特有的
     反驳门条目）。

   收尾：写 CONCLUSION.md 前跑 `provenance.py` 附上 Provenance 块，写完直接把结论
   呈现给用户。
2. **多证据线**：playbook 声明了 ≥2 条 evidence_lines 时，按其 upgrade_rule（通常是
   排名一致性）才能升「假设」；只有单证据线时，结论上限就是「现象」。
3. **功效诚实**：样本/单元数不足（playbook 给阈值，默认 <10）时只报排名与趋势，
   不报显著性。
4. FINDINGS.md 状态只用保留字：**现象 / 假设 / 已证实 / 被推翻**（orient 的判定
   依赖这四个词）。
5. 结论写完按 `conclusion-reporting.md` 产 CONCLUSION.md，并**直接呈现给用户**，
   不能只丢一个文件路径。

## 常见错误

- ❌ orient 报 ✗ 的必答题没问用户，靠"合理假设"开工（schema 猜错污染全部下游）。
- ❌ 生成的分析脚本没过验证步就引用其产出（或 crystallize 快照了无验证记录的脚本）。
- ❌ 事实阶段写机制语言（"因为遗忘 / 因为 batch 小"）——现象与解释物理隔离，
  解释只出现在结论阶段。
- ❌ 单证据线就下"某成员/某变量有害"的判定（噪声容易带偏；按 upgrade_rule
  两线一致才升级）。
- ❌ 跨 series/模型把不可比量纲的数值 pool 在一起（只比排名）。
- ❌ subagent 写 state/PROGRESS/FINDINGS/config；或两个 subagent 追加同一个文件
  （分片必须各写各的 `--out`）。
- ❌ 把 PNG、原始日志、大 parquet 读进上下文（一切解析与计算在脚本内完成并落盘）。
- ❌ 上游产物 absent 却不走三分支就开跑；或 linked/built 的产物不核验
  manifest/marker 就消费。
- ❌ 用户的任务其实命中已固化的专用技能（见 SKILL.md 路由优先级），却用引擎从头
  问一遍。
- ❌ 运行中补齐的实验线【待补】路径忘了写回 project-context（下次还得问）。
- ❌ orient 报"必需材料未就绪"却跳过盘点直接开工；或材料 unknown 时按"大概有"处理。
  unknown ≠ absent-confirmed：前者必须去问，后者才允许走用户确认过的降级。
- ❌ 内联生产 upstream 产物时，没收齐它的 questions 答案就丢给 subagent（提问与用户
  裁决只在主 agent；答案收齐后，纯机械的生产者才可按 `Brief-PRODUCER` 整体外包
  执行段）；或者跑完不写 manifest/marker/config 回填就继续（下次 orient 仍报
  absent，等于白跑）。

## 批量编排（多 playbook 同跑）

同一份数据要一次诊断多条 playbook 时，走 Layer -1 批量层，不逐条串跑。每回合先跑
`python3 "<ENGINE>/scripts/batch.py" --select <id1,id2,...> --workdir <批量工作目录>`
（后续回合去掉 --select 刷新），照它报的 phase 与下一步办；完整协议、Brief-BATCH-COMPUTE
模板、上下文预算见 `references/batch-orchestration.md`。生产者只跑一次入 `_shared/`、
提问一次合并、计算 fan-out 到事实提取、合并停顿、结论仍由主 agent 落笔。

## 运行后回顾（每次实跑收尾必做）

1. 回顾本次执行轨迹：哪条指令/菜谱缺失或有歧义、哪个生成脚本被迫返工、哪个问题
   应该预声明进 playbook 的 questions；
2. 修正写回：菜谱问题 → 改对应 `playbooks/<id>/playbook.md`；机制问题 →
   改 `scripts/`（改完跑 pytest）；提问疲劳或漏问 → 调 playbook questions 的
   default / skip_if；
3. `CHANGELOG.md` 追加一行（日期 | 改了什么 | 触发反馈原文 | 为什么）；
4. 用户表示会复用 → 提议 crystallize（见 `crystallize.md`）。
