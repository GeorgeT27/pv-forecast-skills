# 引擎执行核心（engine-core）——命中 playbook 后必读

<!-- Layer 0（SKILL.md）只做路由；本文件承载执行纪律，与 playbooks/<id>/playbook.md
     一起加载。这里只有引擎级（领域无关）规则；目标特有的阶段/公式/陷阱在 playbook 正文。 -->

## Step 0：Orient —— 每次进入先跑

**引擎第一纪律（弱模型尤其守）：每个回合开工前先跑 orient，本阶段做完再跑一次核对——
不凭记忆推进（真相以产物为准，状态落盘、可断点续跑）。orient 的输出就是你这一回合的
行动清单：照它的 ✗、前置、必答问题、以及末尾打印的「恒问五类」自检逐条办；办完一步就
重跑 orient 拿下一步，不要一口气脑补多个阶段。**

```bash
python3 "<ENGINE>/scripts/orient.py"                                 # 已有 config：报阶段+问题清单+前置
python3 "<ENGINE>/scripts/orient.py" --playbook <id>                  # 首次进入：绑定 playbook
python3 "<ENGINE>/scripts/orient.py" --profile <skill>/profile.yaml   # 固化技能入口：合并已答问题
python3 "<ENGINE>/scripts/orient.py" --goto 3                        # 直达校验
```

真相以产物为准：orient 每次重扫工作目录，报第一个未完成阶段、变体跳过、上下文三分支、**问题清单**（✓已答/✓固化/✓实验线/✓默认/✗未答·阻塞 Stage N）与目标阶段前置。没有 config → 它会打印 playbook 菜单与 project-context 实验线，回来按「提问纪律」收集。

**Step 0.5（可选）**：orient 发现 project-context 时会列出实验线——AskUserQuestion 问用户是否用某条预填；同意则把实验线 json 路径写进 `config.experiment_line`，orient 自动合并已填字段（【待补】不搬、已填不覆盖），对应问题标 ✓实验线。运行中补齐的【待补】路径按仓库纪律**补写回实验线 json**。

**Step 0.75：材料盘点（playbook 声明了 materials 时）**：orient 报「必需材料未就绪」→
按 `references/intake.md` 盘点：一次多选 AskUserQuestion（checklist + 「还有别的吗」
开放项）→ 逐材料追问模板补齐路径/格式/schema（y 列、时间列、id 列——猜错污染全部下游，
必问）→ 落 `config.materials`（status 三值；用户确认没有 = absent-confirmed，required
材料降级须用户再确认后写 degraded_ok）。材料状态驱动 `material:` DSL（变体/前置/skip_if）。

### 三道闸（脚本强制）

引擎用三道机械闸把纪律钉死在脚本里，不指望模型自觉：

1. **入口闸**（orient）：材料未盘点齐 → `BLOCKED`，orient 只吐追问清单，不打印任何阶段/前置信息——盘点不完不许看到下一步。
2. **阶段闸**（`--goto` 护栏 + chart 阶段 INDEX.md 判据）：`--goto` 直达前置不齐的阶段默认拒绝，须显式 `--force` 才放行（且留痕 PROGRESS，仅在确实跳过未齐前置时才写"跳过前置"）；声明了 `charts:` 的阶段，`done_when.artifacts` 必须含 `INDEX.md`（build_index.py 产物），画完图不建索引不算阶段完成。
3. **结论闸**（`conclusion_gate.py`）：结论阶段的 `done_when.artifacts` 必须同时含 `gate_reports/conclusion_gate.json`——该 receipt 是结论阶段唯一完成判据，且只能由 `conclusion_gate.py` 通过后生成（加载期 `_validate_frontmatter` 强制校验，缺则 playbook 直接加载失败）。

## 提问纪律（一等公民——本引擎与专用技能的最大差异）

引擎面向没见过的任务，**不许用假设填补不确定**。细则见 `question-discipline.md`，硬规则：

1. orient 报 ✗ 的问题，在其 stage 开工前**必须** AskUserQuestion——同一阶段的多个未答题合并成一次提问（每题带 playbook 声明的 options）。
2. **引擎级恒问五类**（无论 playbook 有没有声明）：① 数据 schema/单位/口径不明；② 成功判据未定义；③ 证据不足以升级结论（问"接受降级还是补证据"，列补证据成本）；④ 破坏性/昂贵操作（GPU 重训、覆盖已有产物）；⑤ 多候选文件/版本选哪个。
3. 有 default 的问题可不问，但采用默认须在 PROGRESS.md 记一行"按默认"。
4. 答案落 `diagnose_config.json` 的 questions 块：`{"<qid>": {"answer": "...", "source": "user", "date": "YYYY-MM-DD"}}`——这是将来 crystallize 的原料。
5. **subagent 无提问权**：所有停顿点与提问只在主 agent。

## 执行模型

- **阶段由 playbook 定义**（frontmatter，规范见 `playbooks/_playbook-spec.md`）；orient 是通用求值器。推进 = 照 playbook 正文该阶段的菜谱做。菜谱是编号步骤时，进入阶段先把各步逐条建 todo，做一步勾一步；标【硬规则】的步骤不得合并或跳过。
- **分析代码运行时生成**：引擎不带分析脚本。按菜谱把脚本写进工作目录 `analysis_scripts/`，**每个脚本先过菜谱声明的验证步**（对账/合成小样/植入回收），验证结果记 PROGRESS.md——没验证记录的脚本产出不可引用，crystallize 也不快照它。

  **chartbook 豁免**：chartbook（`<ENGINE>/chartbook/`）已覆盖的图**必须**直接调用其
  预写脚本 `chartbook/scripts/chart_*.py`，禁止现场重写同类图；运行时生成只用于
  chartbook 没有的 playbook 特有分析。现场唯一要写的画图相关代码是薄适配器
  `analysis_scripts/adapter.py`（用户数据 → 规范长表，样例见
  `chartbook/golden/example_adapter/`），先过对账两关（行数守恒 + 抽 3 窗核对）
  再喂图脚本，对账记录写 PROGRESS.md。

  **对账两关适用于一切整形脚本**：执行中临时冒出的、菜谱没预见的数据整形/格式转换
  脚本（宽转长、逐窗聚合、单位换算……）同样必须过对账两关再消费其产出——
  菜谱没声明验证步 ≠ 免验证；转换口径（聚合公式、缺失处理）记 PROGRESS.md，
  否则两次执行各自发明口径，结果不可比。
- **图表选择门**（声明了 `charts:` 的阶段，画图前必停一次）。orient 把图分三组
  （①声明且可画 ②声明但缺材料自动跳过 ③未声明但材料已满足的可加画池，按六类
  category 分组、各图带类别标签）。**按序逐条办**（orient 也会打印这份清单）：
  1. **一次** AskUserQuestion 多选；**默认全勾①**（草绘全覆盖是事实阶段的本分，
     被动接受默认＝画全套，守住压测教训的完整性），别自作主张少画；
  2. 用户取消勾选的删图**不静默**：记 PROGRESS.md 一行 + 在 CONCLUSION 声明覆盖缺口
     （同「抽样/截断必须披露」纪律）；
  3. 可从③勾选加图（跨 playbook 任取材料满足的 recipe）；缺材料的②自动跳过，不重复问；
  4. 画最终选定集 → 跑 `chartbook/scripts/build_index.py --charts-dir <workdir>/charts`
     出 `INDEX.md`（按类别分节、只索引本次实际产物，判读入口从索引进）→ 再进
     `pause_after` 停顿汇报。

  **选择门＝画前定范围，停顿点＝画后定深挖，两者不同不可合并。**
- **生成闸**：playbook 的 `golden/manifest.json` 覆盖到的阶段，脚本必须先过 `scripts/gen_gate.py`（静态检查 + 在结果已知的金标准输入上跑一遍），PASS 才许碰真实数据；FAIL → 改脚本不改期望。闸报告落工作目录 `gate_reports/`。
- **事实阶段 ⏸**：playbook 标 `pause_after` 的事实提取阶段产「现象清单」（观察+数字+来源，**禁机制语言**），完成后停下向用户汇报，等用户点名要深挖的项再进结论阶段。用户给模糊授权（"挑最强的/你看着办"）时的操作判据：**效应量最大且样本数过功效阈值**的那条现象（并列取来源产物证据线更多者），选了哪条、按什么判据，记 PROGRESS.md 一行。
- **上游产物三分支**：playbook 声明的 `upstream[]` 产物 absent 时——`required: true` 由主 agent
  **立即内联生产**（不问用户：在 `<product-id>/` 子目录内跑生产方 playbook 的完整正文，写回
  `config.products.<id>={workdir,status:'built'}` 后重跑 orient）；`required: false` 走
  AskUserQuestion 三分支（现在内联生产 / 链接已有目录写 `workdir+status=linked` / 放弃
  `status=declined` 且结论须声明缺此产物与代价）。linked/built 时核验 manifest 与
  marker_files 才消费；stale（输入材料已变）须用户二选一：重建或 `accept_stale=true` 确认沿用
  （结论须声明）。产物内联生产即「upstream 产物内联生产」——不是外部技能接线，是引擎内
  playbook 间既定的生产者/消费者关系，见 `_playbook-spec.md` §`produces`/`upstream`。
- **subagent 编排**：重活（大日志解析、批量计算、逐产物事实提取）外包，brief 模板见 `subagent-briefs.md`；分片各写各的 `--out`，主 agent 合并；`diagnose_config/diagnose_state/PROGRESS/FINDINGS` 只由主 agent 写。
  **分层原则**：生产者 playbook（声明 `produces`、无结论阶段、执行段无用户裁决与
  FINDINGS 写入——如 data-setup、metric-eval）由主 agent 收齐 questions 答案后按
  `Brief-PRODUCER` **整体外包**，主 agent 只做提问-派发-收汇报-写 config.products 回填；
  不满足条件的生产者（model-audit、fact-scan）按各自 §5 拆分。分析类 playbook 由
  主 agent 亲自执行，只外包其 §5 列的机械子任务——**结论永远由主 agent 落笔**。
- **上下文预算**：产物自足（json 带完整数字与形状描述），判读读 json 不读 PNG、不读原始大文件；每阶段落盘可断点续跑。

## 结论纪律（精简硬规则，细则见 mechanisms.md）

1. **三道门**（结论阶段逐条办，orient 在产 `CONCLUSION.md` 的阶段会打印这份清单；三门全过才可在 FINDINGS.md 标「已证实」）：
   - **门1 稳健性**：配对检验过 + 剔除最极端 10% 方向不变；
   - **门2 假设登记**：先在 HYPOTHESES.md 写下预测，**再**看数（禁事后编故事）；
   - **门3 反驳门**：替代解释逐条排除，排不掉就显式降级（含 playbook 特有反驳门条目）。
   收尾：写 CONCLUSION.md 前跑 `provenance.py` 附 Provenance 块，写完直接呈现给用户。
2. **多证据线**：playbook 声明 ≥2 条 evidence_lines 时，按其 upgrade_rule（通常排名一致性）才升「假设」；单证据线结论上限「现象」。
3. **功效诚实**：样本/单元数不足（playbook 给阈值，默认 <10）只报排名与趋势，不报显著性。
4. FINDINGS.md 状态只用保留字：**现象/假设/已证实/被推翻**（orient 判定依赖）。
5. 结论写完按 `conclusion-reporting.md` 产 CONCLUSION.md 并**直接呈现给用户**，不只丢路径。

## 常见错误

- ❌ orient 报 ✗ 的必答题没问用户就靠"合理假设"开工（schema 猜错污染全部下游）。
- ❌ 生成的分析脚本没过验证步就引用其产出（或 crystallize 快照了无验证记录的脚本）。
- ❌ 事实阶段写机制语言（"因为遗忘/因为 batch 小"）——现象与解释物理隔离，解释只在结论阶段。
- ❌ 单证据线就下"某成员/某变量有害"的判定（噪声易带偏；按 upgrade_rule 两线一致才升级）。
- ❌ 跨 series/模型 pool 不可比量纲的数值（只比排名）。
- ❌ subagent 写 state/PROGRESS/FINDINGS/config，或两个 subagent 追加同一个文件（分片各写各的 `--out`）。
- ❌ 把 PNG/原始日志/大 parquet 读进上下文（一切解析与计算在脚本内落盘）。
- ❌ 上游产物 [absent] 不按三分支处理就开跑，或 linked/built 时不核验 manifest/marker 就消费。
- ❌ 用户的任务其实命中专用技能（见 SKILL.md 路由优先级与 description 负面清单）却用引擎从头问一遍。
- ❌ 忘了把运行中补齐的实验线【待补】路径写回 project-context（下次还得问）。
- ❌ orient 报「必需材料未就绪」却跳过盘点直接开工，或材料 unknown 时按"大概有"处理
  （unknown ≠ absent-confirmed：前者必须问，后者才允许走确认过的降级）。
- ❌ 内联生产 upstream 产物时没收齐其 questions 答案就丢给 subagent（提问与用户裁决
  只在主 agent；答案齐后纯机械生产者才可按 `Brief-PRODUCER` 整体外包执行段），或跑完
  不写 manifest/marker/config 回填就继续（下次 orient 仍报 absent，白跑）。

## 运行后回顾（每次实跑收尾必做）

1. 回顾本次执行轨迹：哪条指令/菜谱缺失或有歧义、哪个生成脚本被迫返工、哪个问题该预声明进 playbook questions；
2. 修正写回：菜谱问题 → 改对应 `playbooks/<id>/playbook.md`；机制问题 → 改 `scripts/`（跑 pytest）；提问疲劳或漏问 → 调 playbook questions 的 default/skip_if；
3. `CHANGELOG.md` 追加一行（日期 | 改了什么 | 触发反馈原文 | 为什么）；
4. 若用户表示会复用 → 提议 crystallize（`crystallize.md`）。
