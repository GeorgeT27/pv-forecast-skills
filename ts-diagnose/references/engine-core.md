# 引擎执行核心（engine-core）——命中 playbook 后必读

<!-- SKILL.md（Layer 0）只做路由；本文件只写领域无关、代码查不了的执行纪律。
     阶段/前置/闸/清单由 orient 与闸脚本打印和强制，这里不复述。 -->

## Step 0：Orient——每回合先跑

每个回合开工前先跑 orient；本阶段做完再跑一次核对。不凭记忆推进——真相以落盘产物为准。
前置齐时 orient 会打印**当前阶段菜谱原文**与该阶段清单（图表选择门 / 三道门）——照打印的做，
不必整份读 playbook；`--recipe N` 单独复核某阶段。

```bash
python3 "<ENGINE>/scripts/orient.py" [--playbook <id> | --profile <skill>/profile.yaml] [--goto N] [--recipe N]
```

- 发现 project-context 时 orient 列实验线：AskUserQuestion 问要不要预填；同意则把路径写
  `config.experiment_line`；运行中补齐的【待补】按仓库纪律写回实验线 json。
- orient 报「必需材料未就绪」→ 按 `intake.md` 盘点：一次多选 checklist（末尾「还有别的吗」）→
  逐项追问路径/格式/schema（y 列、时间列、id 列必须问清）→ 落 `config.materials`。
  用户明确说没有 = absent-confirmed；required 材料降级须用户再确认并写 degraded_ok。

**三道闸（脚本强制）**：入口闸（材料不齐 orient 只打追问清单）· 阶段闸（`--goto` 前置不齐默认拒绝，
`--force` 留痕；声明 `charts:` 的阶段 done 必含 INDEX.md）· 结论闸（`conclusion_gate.py` 通过生成的
receipt 是结论阶段唯一完成判据）。

## 提问纪律

**不许用假设填补不确定**（细则 `question-discipline.md`）：

1. orient 报 ✗ 的问题，在其 stage 开工前必须 AskUserQuestion；同阶段合并一次问，带 playbook 的 options。
2. **恒问五类**——任务用到且信息不明时必问：① schema/单位/口径；② 成功判据；③ 证据不足以升级
   （问「接受降级还是补证据」，列补证据成本）；④ 破坏性或昂贵操作；⑤ 多候选文件/版本。
3. 有 default 的可不问，但采用默认须在 PROGRESS.md 记「按默认」。
4. 答案落 `diagnose_config.json` 的 questions 块：`{"<qid>": {"answer","source":"user","date"}}`。
5. **subagent 无提问权**：停顿与提问只在主 agent。

## 执行模型

- 阶段由 playbook frontmatter 定义（`_playbook-spec.md`），orient 是通用求值器。菜谱是编号步骤时，
  逐条建 todo，做一步勾一步；标【硬规则】的步骤不得合并、不得跳过。
- **分析代码运行时生成**进 `analysis_scripts/`，每个脚本先过菜谱声明的验证步（对账/合成小样/
  植入回收），结果记 PROGRESS.md；无验证记录的脚本产出不可引用，crystallize 不快照。
  golden 覆盖的阶段先过 `gen_gate.py`，PASS 才碰真实数据；FAIL 改脚本不改期望。
- **chartbook 豁免**：chartbook 已覆盖的图**必须**直接调 `chartbook/scripts/chart_*.py`，禁止现场重写；
  唯一现场写的是薄适配器 `analysis_scripts/adapter.py`（样例 `chartbook/golden/example_adapter/`）。
- **对账两关适用一切整形脚本**（行数守恒 + 抽 3 个窗口逐值核对）：菜谱没预见的临时整形/换算脚本
  同样要过；菜谱没声明验证步 ≠ 免验证。转换口径记 PROGRESS.md。
- **图表选择门**：声明 `charts:` 的阶段画图前必停一次（orient 打印四步清单）。默认全勾可画图；
  用户删图不静默（PROGRESS 一行 + CONCLUSION 声明缺口）；画完 `build_index.py` 出 INDEX.md 再停顿。
  选择门 = 画前定范围；停顿点 = 画后定深挖；不可合并。
- **事实阶段 ⏸**：`pause_after` 的事实阶段产出「现象清单」（观察 + 数字 + 来源，**禁机制语言**），
  停下汇报，等用户点名再进结论阶段。用户模糊授权（「挑最强的」）时选**效应量最大且样本过功效阈值**
  的现象，并列取证据线多的；选了哪条、按什么判据记 PROGRESS.md。
- **上游产物**：orient 按 `upstream[]` 打印三分支操作（required 缺 → 立即内联生产不问用户；optional
  缺 → 问用户三选一）。linked/built 的产物核验 manifest 与 marker 才能消费；stale 时让用户二选一
  （重建 / `accept_stale=true` 且结论声明）。
- **派发（卡片制）**：重活按名字派 `agents/` 卡片——`X-compute`（producer 整体 / compute 到第一个
  pause / compute-fine 与 worker 逐任务）。派发前问齐区间内 `questions:`，填「输入」节的答案、上游目录、
  `<ENGINE>`/`<workdir>` 绝对路径；required 上游缺先派 producer 卡。`NEED_INFO` → 问用户、写 config、
  重派同一张；`BLOCKED` → 修后重派，不换卡。**回退**：Agent 可用类型无该名字 → 卡片全文作 prompt 派
  `general-purpose`，PROGRESS 记「卡片未注册，走回退」。索引与六步见 `subagent-briefs.md`。
  **单写者**：`diagnose_config / diagnose_state / PROGRESS / FINDINGS` 只由主 agent 写；卡片不再派 subagent；
  **结论永远由主 agent 落笔**。
- **上下文预算**：产物自足（json 自带数字与形状），判读读 json，不读 PNG、原始日志、大 parquet。

## 假设验证循环

生成器 playbook（吐 `hypothesis_ledger.json`，如 model-comparison）不下结论；结论由跨 playbook 循环
在出口产一次：① 生成器产账本停顿移交 → ② `architecture-attribution` 取判别力最高的假设做单变量
干预（每条干预派 `architecture-attribution-worker`，主 agent 只收 receipt）→ ③ refuted 且预算未耗 →
回生成器提修正假设，标 `provenance: post-hoc`（不许同一批数据既生成又确认）→ ④ confirmed /
预算耗尽 / 无新判别假设 → 收敛 → ⑤ 结论只在出口过 `conclusion_gate` 产一次（架构因果表述附
「## 消融证据」receipt）。**预算阶梯**：单轮干预 ~10 次训练，总轮数 ≤3。
无 `trainable_framework`（checkpoint/experiment_config absent-confirmed）→ 跳过验证主脊，结论标未经干预验证。

## 结论纪律（细则 `mechanisms.md`）

1. 三道门（orient 在结论阶段打印清单）：门 1 稳健性 · 门 2 假设登记先于看数 · 门 3 反驳门逐条排除，
   排不掉显式降级。写 CONCLUSION.md 前跑 `provenance.py`；写完直接呈现给用户，不只丢路径。
2. 多证据线：≥2 条 evidence_lines 按 `upgrade_rule` 一致才升「假设」；单证据线上限「现象」。
3. 功效诚实：单元数不足（默认 <10）**只报排名**与趋势，不报显著性。
4. FINDINGS.md 状态只用保留字：**现象 / 假设 / 已证实 / 被推翻**。
5. CONCLUSION.md 按 `conclusion-reporting.md` 写。

## 常见错误

- ❌ orient 报 ✗ 的必答题没问，靠「合理假设」开工（schema 猜错污染全部下游）。
- ❌ 生成脚本没过验证步就引用其产出（或 crystallize 快照了无验证记录的脚本）。
- ❌ 事实阶段写机制语言（「因为遗忘 / 因为 batch 小」）——解释只出现在结论阶段。
- ❌ 单证据线就下「某成员/某变量有害」的判定。
- ❌ 跨 series/模型把不可比量纲的数值 pool 在一起（只比排名）。
- ❌ subagent 写 state/PROGRESS/FINDINGS/config；两个 subagent 追加同一文件。
- ❌ 把 PNG、原始日志、大 parquet 读进上下文。
- ❌ 上游产物 absent 不走三分支就开跑；linked/built 不核验 manifest/marker 就消费。
- ❌ 任务命中已固化专用技能却用引擎从头问一遍。
- ❌ 运行中补齐的实验线【待补】忘了写回 project-context。
- ❌ 材料 unknown 当「大概有」处理：unknown 必须问，absent-confirmed 才许走用户确认过的降级。
- ❌ 内联生产上游产物时没收齐它的 questions 就派卡；跑完不写 manifest/marker/config 回填。
- ❌ 现场手拼 Brief 派 subagent，而 `agents/` 里已有卡片。
- ❌ 卡片回 `NEED_INFO` 后自己猜答案继续，或换一张卡顶替。
- ❌ 只跑一次 orient 后凭记忆连推多个阶段。

## 批量编排

同一份数据多条 playbook 一起诊断 → `python3 "<ENGINE>/scripts/batch.py" --select <ids> --workdir <dir>`，
照它报的 Phase 办；协议见 `batch-orchestration.md`（生产者一次、提问一次、卡片 fan-out、合并停顿、结论归主）。

## 运行后回顾（每次实跑收尾必做）

1. 哪条菜谱缺失或有歧义、哪个脚本被迫返工、哪个问题该预声明进 questions；
2. 菜谱问题改 `playbooks/<id>/playbook.md`；机制问题改 `scripts/`（跑 pytest）；漏问/提问疲劳调 questions 的 default/skip_if；
3. `CHANGELOG.md` 追加一行（日期 | 改了什么 | 触发反馈原文 | 为什么）；
4. 用户会复用 → 提议 crystallize（`crystallize.md`）。
