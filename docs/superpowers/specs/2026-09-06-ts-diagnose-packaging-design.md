# 设计：ts-diagnose 打包（agents/hooks/workflows 归位）+ 逐回合负载缩短 + v2 退役

日期：2026-09-06
状态：待用户审阅（用户已拍板三项决策，见 §1.2）

## 1. 背景与目标

### 1.1 起因

用户问「ts-diagnose 到底是 skill 还是 workflow」。对实现的核查结论（§2）：它是三样东西共用一个
SKILL.md——**skill 壳**（路由）+ **workflow 运行时**（orient/闸/钩子/frontmatter 状态机）+
**可插拔方法库**（playbook 正文/references/chartbook）。用户要把它整理成一个可搬到另一台
设备的完整包：卡片进 agents 目录、编排进 workflows 目录、钩子可安装，并缩短每回合进入
上下文的指令量；同时**必须**继续对 DeepSeek 一类弱模型有效。

### 1.2 用户拍板的三项决策

| # | 决策 | 内容 |
|---|------|------|
| 1 | 另一台设备的宿主 | **Claude Code**（agents / workflows / hooks 三个原生位置全部适用） |
| 2 | 安装方式 | **symlink 安装脚本**：包内文件一律不搬家，`install.sh` 把它们链接进 `~/.claude/{skills,agents,workflows}` 并把钩子合并进 `~/.claude/settings.json` |
| 3 | ts-diagnose-v2 | **删除**：其 11 张卡片移植进 v1；v2 已落后 v1（12 个 playbook 文件、5 个脚本有差异，4 个脚本 v2 没有） |

### 1.3 不做的事（YAGNI）

- 不做 Claude Code plugin manifest（用户选 symlink）；不把 SKILL.md 搬进 `skills/` 子目录。
- 不把 playbook 正文拆成逐阶段文件——用 orient 按标题抽取当前阶段即可，文件不动。
- 不改任何闸的语义（gen_gate / conclusion_gate / crystallize_gate / provenance）。
- 不新增 playbook、不动 chartbook。
- 不把 playbook 做成独立 skill（12 条 description 会吃掉 skill 列表预算，见 §4.6.3）。

## 2. 分类结论（供 README 落笔）

判据不是「能力 vs 过程」，而是**下一步由谁决定**：

| 层 | 文件 | 谁决定下一步 | 本质 |
|---|---|---|---|
| 壳 | `SKILL.md` | 模型 | skill：触发 + 路由 + 转发 |
| 运行时 | `scripts/orient.py`、`engine_common.py`、三个闸、三个钩子、playbook frontmatter | 代码 | workflow：磁盘状态机，阶段/前置/完成判据/闸全由代码求值 |
| 方法库 | 12 个 `playbook.md` 正文、`references/`、`chartbook/` | 模型 | skill 内容：某一阶段怎么做、陷阱、选图 |

Claude Code 原生 Workflow（JS 脚本）不能中途问用户，而 pause_after / 图表选择门 / 恒问五类
都是用户裁决点，所以**整个引擎不可能变成一个 workflow 脚本**；只有两段无交互的计算段
适合（§4.8）。

## 3. 目录结构（改后）

```
ts-diagnose/                          # 一个目录 = 整个产品；install.sh 只做链接
├── SKILL.md                          # 不动（skill 壳；ENGINE = 本文件所在目录）
├── agents/                           # 新增：13 张卡片 + _agent-spec.md（可移植 markdown）
├── hooks/                            # 从仓库根迁入：gate_guard.py / orient_reminder.py / stage_probe.py
│   ├── hooks.json                    #   三钩子事件声明（命令用绝对路径占位，install 时替换）
│   └── install_hooks.py              #   幂等合并进 ~/.claude/settings.json；--uninstall 反向
├── workflows/                        # 新增：ts-batch-compute.js / ts-ablation-loop.js（仅 Claude Code）
├── scripts/  references/  playbooks/  chartbook/   # 不动
├── INSTALL.md                        # 新增：另一台设备的安装步骤 + 校验 + 卸载 + SDK 附录
├── install.sh                        # 新增：link / --check / --uninstall / --copy
└── CHANGELOG.md
<仓库根>/hooks  →  symlink → ts-diagnose/hooks   # 保住外部引用（skill-evolve 的 run_blind.wire_hooks、docs/自进化计划）
```

安装后 Claude Code 看到的：

```
~/.claude/skills/ts-diagnose        → <pkg>              （已有）
~/.claude/agents/<id>-compute.md    → <pkg>/agents/…     （13 个链接；_agent-spec.md 不链）
~/.claude/workflows/ts-*.js         → <pkg>/workflows/…
~/.claude/settings.json             ← hooks 三条合并（PostToolUse / Stop / UserPromptSubmit）
```

**跨目录触发为什么成立**：Claude Code 启动时只加载每个 skill 的 name+description；命中后
加载 SKILL.md 正文；`~/.claude/agents/*.md` 自动注册为可按名字派发的 subagent 类型；
`~/.claude/workflows/*.js` 按名字调用，且「skill 指令要求调用 Workflow」算作用户 opt-in。
所以 SKILL.md / engine-core 只需**按名字**点名卡片与 workflow，不需要知道它们装在哪。

## 4. 组件设计

### 4.1 agents/ 卡片集（13 张）

四种 mode（前三种原样承接 v2 `_agent-spec.md`，第四种新增）：

| mode | 覆盖 | 卡片 |
|---|---|---|
| producer | 整个生产者 playbook 跑到产物落盘 | data-setup / metric-eval / model-audit |
| compute | Stage 0 到第一个 pause_after 的计算区间 | training-sufficiency / robustness / feature-importance / model-comparison / deployment-drift / fact-scan / result-eval / **architecture-attribution（新，区间 "0-0"）** |
| compute-fine | 每次只跑主 agent 指派的一个具名脚本 | subset-influence |
| **worker（新）** | 每次只执行一条「改配置 + 重训 + 评估」任务，回一张 receipt | **architecture-attribution-worker（新）** |

**不是每个 playbook 都由 subagent 驱动**：提问、停顿、假设选择、干预设计、结论三道门、
conclusion_gate 永远在主 agent（`subagent_ok:false` 的阶段卡片天然不覆盖）。

**worker 卡设计**（承接 `playbooks/architecture-attribution/references/subagent-brief.md` 的
Brief A / Brief B，正文不复述菜谱，只指针）：

- frontmatter：`name: architecture-attribution-worker`、`mode: worker`、
  `playbook: architecture-attribution`、`compute_stages: "scripts"`、`serves_stages: [0, 3]`、
  `tools: [Bash, Read, Write]`、`model: sonnet`。
- 输入节多一个字段 `task: noise-floor | intervention`，其余按派发填：工作目录、种子集、
  该条干预（hypothesis_id / switch / kind / seeds / pred_direction / kill_criterion /
  confirm_criterion）、噪声底、基线口径。
- 步骤节指向 `playbooks/architecture-attribution/playbook.md` 的 Stage 0「第一步」与 Stage 3
  「执行契约」，并写死 `scripts/ablation_verdict.py` 的调用形态（含 `--script/--t-start/--t-end/--selftest/--out receipts/<id>.json`）。
- 红线：单变量（只改一个 switch）、不读权重/逐 iteration loss/训练日志、只写
  `receipts/<hypothesis_id>.json` 与 `analysis_scripts/eval_<id>.py`、不写四个共享文件、不下综合判定、不再派 subagent。
- 输出契约（JSON 即 final message）：
  `{"status": "COMPUTE_DONE|NEED_INFO|BLOCKED", "task": "...", "hypothesis_id": "...",
    "receipt_line": "<ablation_verdict 打印原行>", "receipt_file": "receipts/H3.json",
    "config_diff": ["--foo=off"], "per_seed": [..], "instability_note": "", "need_info": [...],
    "blocked_reason": ""}`；noise-floor 任务把 `per_seed / mean / std / noise_floor_3sigma` 放进同一 JSON。
- 若 60 行装不下两种任务，拆成 `architecture-attribution-worker.md`（intervention）与
  `architecture-attribution-baseline.md`（noise-floor），命名律同为 `<playbook>-<role>`。

**命名律**：文件名 = `name` + `.md`；`name` ∈ {`<playbook>-compute`, `<playbook>-worker`,
`<playbook>-baseline`}。全局 agents 目录里名字够独特，不加 `ts-` 前缀。

**卡片守卫**：`scripts/tests/test_cards.py` 从 v2 移植，路径改为 v1；glob 扩到
`*-compute.md` + `*-worker.md` + `*-baseline.md`；新增 worker 分支断言：`serves_stages`
里每个 stage 在 playbook 里 `subagent_ok:true`，`compute_stages == "scripts"`。
`BODY_LINE_BUDGET` 60 → **80**（为 §4.7 的输出示例留位）。11 张移植卡逐张对照 v1 当前
frontmatter 重核 `compute_stages`（v1/v2 已漂移）。

### 4.2 派发规则（替换现场注入 Brief）

`references/engine-core.md`「subagent 编排」节改为：

1. 命中 playbook `X` → 派卡片 `X-compute`（producer 整体、compute 到区间终点、compute-fine /
   worker 逐任务）；派发前先按该 playbook `questions:` 问齐 `stage ≤` 区间终点的题，答案随
   「输入」节带入；`upstream[]` required 产物缺 → 先派对应 producer 卡（`setup`→data-setup、
   `model_profile`→model-audit、`metric_table`→metric-eval）。
2. **回退（可移植性）**：`Agent` 工具可用类型里没有该名字 → 把 `agents/<name>.md` 全文作为
   prompt 派 `general-purpose`，行为等价，只是身份标签不同；PROGRESS.md 记一行「卡片未注册，
   走回退」。
3. `NEED_INFO` 回环、`BLOCKED` 处理、禁嵌套、单写者、`COMPUTE_DONE` 后的停顿——承接 v2
   `dispatch-protocol.md` §2/§4，合并进 `references/subagent-briefs.md`（文件名不改，
   playbook 正文里的引用不动；内容改为：共用派发纪律 + 卡片索引 + 回退规则 + NEED_INFO
   回环 + Brief-EMBED 主 agent 编排提示）。Brief-COMPUTE / Brief-PRODUCER / Brief-FACT
   三个模板删除（被卡片取代）。
4. `references/batch-orchestration.md` Phase C：worker = 具名卡片，`Brief-BATCH-COMPUTE`
   模板删除；其余 Phase A–E 逐字不动。
5. `scripts/orient.py` 在「🤝 生产者 playbook」提示与目标阶段块里，把「按 §5 派发
   subagent」措辞改为「派卡片 `<id>-compute`（agents/），未注册则回退」。

### 4.3 hooks/

- 三个脚本迁入 `ts-diagnose/hooks/`；仓库根 `hooks` 变成指向它的 symlink（git 跟踪
  symlink），外部路径 `hooks/stage_probe.py` 继续有效。
- `hooks/hooks.json`：
  - `PostToolUse` matcher `Bash|Write|Edit` → `stage_probe.py`（现有；env 未设时零行为）；
  - `Stop` → `gate_guard.py`（结论闸 harness 级守卫，`CAP=3` 防死循环）；
  - `UserPromptSubmit` → `orient_reminder.py`（软提醒）。
  命令写成 `python3 "<PKG>/hooks/<name>.py" 2>/dev/null || true`，`<PKG>` 由
  `install_hooks.py` 替换为绝对路径。
- `install_hooks.py`：读 `~/.claude/settings.json`（无则建），按「命令串含
  `/ts-diagnose/hooks/`」识别自家条目，先删后加（幂等）；`--uninstall` 只删自家条目；
  `--dry-run` 打印将写入的 JSON。本仓库 `.claude/settings.json` 里现有的绝对路径条目改指新位置。
- 实施时用一次真实 Stop 触发核对 `gate_guard` 的 block 输出格式与 `orient_reminder` 的
  `additionalContext` 字段名（脚本注释里写着「以你的 hooks 版本为准」）。

### 4.4 install.sh / INSTALL.md

`install.sh`（bash，macOS/Linux）：

- 无参：`ln -sfn` 三处（skills 整目录、agents 逐文件、workflows 逐文件）+ `install_hooks.py`；
  顺手删除残留的 `~/.claude/skills/ts-diagnose-v2` 链接。
- `--check`：逐项打印链接是否存在且指向本包、settings.json 是否含三条钩子、
  `python3 hooks/gate_guard.py --selftest` 与 `stage_probe.py --selftest` 是否通过、
  `pytest` 是否可 collect。
- `--uninstall`：反向。
- `--copy`：agents/workflows 改为复制而非链接（若实测 Claude Code 不跟随 agents 目录下的
  symlink，则 `--copy` 成为默认，INSTALL.md 同步）。
- 幂等，可重复跑。

`INSTALL.md`：前置（python3、pyyaml、requirements.txt）、三步安装、`--check` 期望输出、
如何确认卡片已注册（Agent 工具可用类型里出现 `model-comparison-compute`）、卸载、
附录「非 Claude Code 宿主」（承接 v2 `EVAL.md` §3：自研 SDK 按 `agents[name]` 加载卡片，
钩子不装，靠 orient/闸）。

### 4.5 v2 退役

- `git rm -r ts-diagnose-v2`；删 `~/.claude/skills/ts-diagnose-v2` 链接；
  `.claude/settings.local.json` 的 `skillOverrides.ts-diagnose-v2` 删除；README 表格与
  介绍文档去掉 v2 行；`docs/superpowers/specs/2026-08-04-ts-diagnose-v2-agent-cards-design.md`
  保留作沿革。
- v2 独有且仍有价值的内容在删除前搬走：11 张卡片、`_agent-spec.md`、`test_cards.py`、
  `dispatch-protocol.md` §2/§4、`EVAL.md` §3。其余全部是 v1 的落后副本，不搬。

### 4.6 逐回合负载缩短（内容不删，只改出现时机）

现状实测（粗估 token）：一次典型运行读 SKILL.md 1.9K + engine-core 6.7K + 常用
references 9.7K + 一个 playbook 7.6K（最大 12.5K），≈26K；orient 每回合只报阶段名，
模型仍要整份读 playbook。

#### 4.6.1 orient 打印当前阶段菜谱

- 抽取规则：playbook 正文中 `^### Stage <id>` 起、到下一个 `^### ` 或 `^## ` 止；标题允许
  范围写法 `### Stage 5–6` / `### Stage 5-6`（feature-importance 7 个阶段只有 5 个标题）。
- 默认行为：当前阶段前置齐（orient 已打印「→ 前置齐，可开工」）时，紧接着打印
  「📖 本阶段菜谱（playbook.md §Stage N 原文）」+ 该节原文 + 该阶段 `done_when` 一行；
  前置不齐时不打印（先补前置）。`--no-recipe` 关闭；`--recipe N` 单独打印某阶段供复核。
- 打印顺序：前置 → 菜谱 → 该阶段类型的清单（图表选择门 / 三道门，现有）→ 脚注。
- 新守卫 `scripts/tests/test_recipe_sections.py`：12 个 playbook 的每个 stage id 都能映射到
  **恰好一个**正文小节；抽取结果非空。
- 首次进入 playbook（state 无已完成阶段）时多打印一行「示例轨迹：playbooks/<id>/EXAMPLE-RUN.md（如有）」。

#### 4.6.2 engine-core.md 精简

保留（代码查不了的判断规则）：提问纪律五条与恒问五类、事实/机制隔离、单写者、subagent
无提问权、上下文预算、对账两关适用一切整形脚本、chartbook 豁免、假设验证循环的预算阶梯
与终止条件、结论纪律 2–5 条、**常见错误表全文**（弱模型的合理化对照表）、运行后回顾。

改为一行指针（orient 已打印或闸已强制）：Step 0 的 orient 用法段、三道闸细节、图表选择门
四步、上游产物三分支操作步骤、结论三道门清单、批量编排。

「subagent 编排」按 §4.2 改写。目标：按 `test_layering.estimate_tokens` 口径 ≤ **4000**
（实施时先量现值再定，写进新测试 `test_engine_core_token_budget`）。`test_engine.py`
里对 engine-core 文案的断言随之更新。

#### 4.6.3 SKILL.md description 精简

- 现 603 字符。Claude Code 每 skill 的 description 上限 1,536 字符，但**整份 skill 列表**预算
  默认 = 上下文窗口的 1%，超出时最少使用的 skill 会被丢出列表。本机链接了约 30 个 skill，
  这一条占比过大。
- 改为只保留触发短语（用户会怎么说），去掉括号里的 playbook id 与「已固化代理…」句，
  目标 ≤ 350 字符；路由表留在正文。
- `test_routing.py`：`test_engine_description_enumerates_all_playbooks` 改为断言**正文路由表**
  枚举全部 id（`test_skill_md_line_budget_and_full_playbook_coverage` 已覆盖，去重即可）；
  `test_engine_keeps_trigger_phrases` 保留。

### 4.7 运行示例

- `playbooks/<id>/EXAMPLE-RUN.md`，先做 result-eval / model-comparison / feature-importance
  三个：在临时目录用各自 `golden/` 走一遍（orient 输出 → 执行的命令 → 产物清单 → 现象清单
  节选 → 停顿汇报样例），录成 ≤2K token 的轨迹；文件头写明「来自 golden，数字仅示例」。
  只在 orient 首次进入时提示路径（§4.6.1），其余时候零成本。
- 每张卡片「输出契约」节下加一个**填好的** JSON 示例（golden 数字），弱模型最常见的失败是
  契约格式；行预算见 §4.1。
- 新守卫：EXAMPLE-RUN.md 里出现的 `python3 …/scripts/xxx.py` / `chart_*.py` 路径必须真实存在。

### 4.8 workflows/（仅 Claude Code；两段无交互计算）

共同约束：JS、`export const meta` 纯字面量、脚本无文件系统访问（读写全在 agent 内）、
不能问用户、`Date.now()` 不可用（时间戳由 worker 在自己的 shell 里记）。派发用
`agentType: '<name>'` 走原生注册的卡片；`schema` = 卡片输出契约的 JSON Schema，返回即校验。

**`ts-batch-compute.js`**（批量 Phase A + C；Phase B 提问在前、Phase D 停顿与 Phase E 结论
在后，都归主 agent）：

- `args = {workdir, producers: [{id, inputs}], computes: [{id, inputs}]}`，`inputs` 就是各卡
  「输入」节字段（主 agent 已问齐的答案、上游产物目录）。
- Phase Producers：按 `producers` 顺序**串行** `agent(fill(card, inputs), {agentType: id+'-compute', schema: CONTRACT})`
  （data-setup 先于其消费者）。
- Phase Compute：`parallel(computes.map(...))`——barrier 合理：主 agent 要把全部现象合并
  后一次停顿。
- 返回 `{producers: [...], computes: [...]}` 原样契约。任何 `NEED_INFO` → 主 agent 问用户、
  写 config、用 `resumeFromRunId` 重跑（已完成的卡片命中缓存不重跑）。
- `batch.py --mark` 由主 agent 收到结果后逐条执行（单写者）。

**`ts-ablation-loop.js`**（architecture-attribution Stage 3 的一轮干预）：

- `args = {workdir, noise_floor_3sigma, baseline_mean, seeds, interventions: [<plan 条目>], max_parallel}`，
  由主 agent 从 `intervention_plan.json` 摘出（跳过 `skipped_reason` 与 `script` 非空的复核项）。
- Phase Ablate：`parallel` 派 `architecture-attribution-worker`（`task: intervention`），
  每条独立 receipt；返回 receipts 数组。
- 三态判定、账本更新、`verdict_summary.json`、post-hoc 新假设、下一轮——全部主 agent；
  每轮一次 workflow 调用，轮数上限 3 由主 agent 守。
- 不在 workflow 里放示例（编排脚本不是教学文档）。

SKILL.md 不提 workflow（Layer 0 预算）；engine-core「批量编排」与 architecture-attribution
§5 各加一句「Claude Code 下可调 workflow `ts-batch-compute` / `ts-ablation-loop`」。

## 5. 弱模型保障（DeepSeek 一类）

1. 指令总量不减，只改**出现时机**：每回合 orient 打印当前阶段菜谱 + 该阶段清单——这正是
   2026-07-24 三轮加固里唯一证明有效的手段（散文不绑定，打印到眼前才绑定）。
2. 合理化对照表（常见错误）、红线、恒问五类横幅、「每回合先跑 orient」脚注全部保留。
3. 卡片自带红线 + 输出契约 + 填好的示例；subagent 原生无 AskUserQuestion。
4. 强制全在 Python（orient/闸）——任何宿主都生效；钩子是 Claude Code 上的加层。
5. 派发回退规则让同一套卡片在不能按名字派发的宿主上也能用。

## 6. 测试与验收

| 阶段 | 自动 | 手动/实跑 |
|---|---|---|
| 1 卡片+包 | 现有 410 + `test_cards.py`（13）+ hooks `--selftest` ×2 + `install_hooks.py --dry-run` 快照测试 | `install.sh --check` 全绿；Agent 工具可用类型出现 `model-comparison-compute`；在 model-comparison golden 上真派一次卡片，回合法 JSON；CHANGELOG 2026-07-24 的四步弱模型冒烟复演 |
| 2 缩短 | `test_recipe_sections.py`、`test_engine_core_token_budget`、`test_routing` 更新后全绿 | 四步冒烟复演；记录缩短前后每回合 token 量进 CHANGELOG |
| 3 示例 | 示例路径存在性守卫 | 三份 EXAMPLE-RUN.md 人工通读一遍可复现 |
| 4 workflows | 语法：`node --check`（若有 node） | 需用户一句「run the workflow」才能真跑（Workflow 工具要求 opt-in）；在 golden 上跑一次 batch，一次 ablation（worker 用 golden 假干预） |

## 7. 风险与裁决

- **agents 目录是否跟随 symlink**：未验证。实施时实测；不跟随则 `install.sh` 默认 `--copy`。
- **Stop 钩子误拦**：`gate_guard` 只在 cwd 下存在 `diagnose_config.json` 且 playbook 非生产者时
  生效，`CAP=3`；本仓库根目录就有一份 `diagnose_config.json`，工程会话里可能被拦——
  接受（这正是它的用途），INSTALL.md 写明如何临时 `--uninstall`。
- **hooks 迁移的外部引用**：skill-evolve 仓库的 `run_blind.wire_hooks()` 按 `hooks/stage_probe.py`
  路径接线——根目录 symlink 保住路径，零改动。
- **worker 卡 60/80 行装不下两种任务**：拆成两张（§4.1 已给命名）。
- **未提交的现有改动**：ts-diagnose 下有 31 个文件、+517/−185 的未提交 diff（含 08-31
  conclusion_gate 规则 5+6）。打包工作开始前先把它单独提交（Task 0），否则本次提交会混入。

## 8. 实施顺序与 git 纪律

Phase 1（卡片 + 包）→ Phase 2（缩短）→ Phase 3（示例）→ Phase 4（workflows，最后、
仅 Claude Code）。每个 task 原子提交、只按显式路径 stage、绝不 `git add -A`；每阶段收尾
CHANGELOG 一行（日期 | 改了什么 | 触发反馈原文 | 为什么）。本机 `~/.claude` 用 `install.sh`
重装一次作为端到端验证。
