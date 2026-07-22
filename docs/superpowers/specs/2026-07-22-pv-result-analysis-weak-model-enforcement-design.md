# pv-result-analysis 弱模型执行强制 —— 设计文档

- 日期：2026-07-22
- 范围：`pv-result-analysis` 技能（钩子脚本写成可扩展到 `pv-feature-blame` / `pv-station-influence`）
- 状态：已通过头脑风暴，待写实现计划

## 1. 问题

弱模型（255k 上下文的小模型）跑 `/pv-result-analysis` 时，把整份 SKILL.md（260 行散文）当作**建议**而非**命令**，四种失败同时出现（用户确认四种全中）：

1. **跳步/乱序**——不跑 orient、不质检、直接冲到画图或归因；该停下问用户时不停。
2. **不派 subagent**——所有画图 + 读图都在主上下文自己干，图和 stats 全进主上下文，很快爆 context / 变慢。
3. **不问就猜**——缺路径 / 缺实验线 / 不确定该干嘛时，不 AskUserQuestion，直接猜一个往下跑。
4. **不守纪律门**——没过稳健性门 / 反驳门就下"已证实"；读图不读 stats.json；只报路径不报数字。

**关键复盘**：用户以为有 hook 在起作用（且以为只对 `/pv-feature-blame` 生效）。实测**全仓、全局 `~/.claude/settings.json` 都没有任何 Claude Code hook**——`pv-feature-blame` 表现更好只是因为它把强制写进了**内容**（`## ⚠️ 首要框定` 硬规则 + `硬规则: feature_true 没给 → AskUserQuestion` + golden/pytest 闸），而 `pv-result-analysis` 的编排（主 agent 调度 + subagent 外包）只是一张**散文表**，弱模型读成建议。

**根因**：对弱模型，步骤遵循与 subagent 派发必须由**结构（脚本/闸门吐出单一祈使式下一步）**强制，而不是靠它自己从 260 行散文里综合。

## 2. 方案总览：两层

- **Layer 1（技能内，可移植，零配置，hook 关掉也生效）**——把决策面收缩成"每步一个祈使式下一步动作"。这是主干，独立成立。
- **Layer 2（user 级 hook，物理兜底）**——`~/.claude/settings.json` 里两个自限定作用域的 hook，物理拦截跳步与主上下文画图。

运行目录事实：用户在**独立的分析工作目录**跑本技能（不是技能仓库目录），所以 hook 必须放 **user 级**（`~/.claude/settings.json`，全局生效），并靠脚本自检"当前是不是 pv-result-analysis 会话"，不相关就 `exit 0` 放行。

## 3. Layer 1 —— 技能内主干

### 3.1 `run_orient.py` 增加 `NEXT ACTION` 块

现状：`run_orient.py` 打印一张阶段状态板（各阶段 ✓/✗），是**信息式**的——模型看完还得自己决定干嘛。

改动：在报告**最后**追加一个醒目、唯一的 `NEXT ACTION` 块，只给一个祈使动作。规则按当前阶段与前置：

- **前置有 ✗（缺 config / 缺路径 / 缺实验线）** → NEXT ACTION =
  `STOP。用 AskUserQuestion 问用户 <具体缺的那项>。不要继续、不要猜。`
  （对应失败 3 不问就猜）

- **Stage 1（config 齐、无产物）** → NEXT ACTION = 逐字给出 Stage 1 的下一条命令：先 `run_quality_check.py`，再按 Step 2 跑 metric（或派 Brief B subagent，二选一给出材料化文本）。

- **Stage 2–3（该画图）** → NEXT ACTION = **完全材料化的 `Agent` 派发块**（Brief A，把 `<绝对工作目录>` / `<RANGE>` / `<FIGS>` 用本次实参替换好），让模型**照抄**，而不是自己决定要不要派 subagent。
  （对应失败 2 不派 subagent）
  同时明确写："不要自己跑 run_analysis.py，不要 Read PNG。"

- **Stage 3→4 边界（现象已出、未归因）** → NEXT ACTION =
  `STOP。把现象清单报用户 + AskUserQuestion 让用户点名哪几条进 Stage 4。subagent 不能问用户，这一步只能主 agent 做。`
  （对应失败 1 跳步/乱序里"该停不停"）

- **Stage 4（用户已点名）** → NEXT ACTION = 提示走 Playbook + 三道门 + 写 CONCLUSION.md，并列出"标'已证实'前必过反驳门"这条硬提醒。
  （对应失败 4 不守纪律门）

- **四阶段全完成（current_stage=5）** → NEXT ACTION = 收尾提示（刷新 CONCLUSION.md / 按 --goto 复核）。

材料化来源：Brief A / Brief B 的固化文本在 `references/subagent-briefs.md`。orient 读取该文件模板并做占位替换，或（更稳）在 orient 里内联一份精简派发块常量，避免脚本去解析 markdown。**实现取内联常量**（脚本自足、不依赖解析 references）。RANGE/FIGS 的默认：月度诊断默认 `--figs 1,2,4,8`；RANGE 若 config 未指定则 NEXT ACTION 里提示"缺 range 先问用户要分析哪个月/all"。

`NEXT ACTION` 块用固定醒目分隔（如 `#### NEXT ACTION（逐字执行，不要自行发挥）####`），保证弱模型在长输出里也一眼可见。

### 3.2 SKILL.md 顶部加"弱模型铁律"前言（约 15 行）

放在 frontmatter 之后、`# 光伏功率预测结果分析` 标题之前（或紧随标题），作为全篇第一段可执行指令：

- 你的循环恒为：**跑 `run_orient.py` → 逐字执行它给的唯一 NEXT ACTION → 回到 orient**。
- 正文（下面 260 行）是给 NEXT ACTION **背书的参考**，不是让你自行编排的清单——不要凭正文跳步。
- 任何时候不确定 / 缺输入 / 缺路径 → 立刻 **AskUserQuestion**，绝不猜。
- 画图 + 读图**必派 subagent**（NEXT ACTION 会给你现成派发块）；图与 stats.json 不进主上下文。
- 标"已证实"前必过三道门（稳健性 / 假设登记 / 反驳门）。

不删除既有正文与常见错误清单——只在最上面加一个"驱动器"，把 260 行从"驱动"降级为"参考"。

## 4. Layer 2 —— user 级 hook

两个 hook 都自限定作用域，无关项目静默 `exit 0`。脚本放 `pv-result-analysis/hooks/`，用 Python，从 stdin 读 JSON。

### 4.1 自限定作用域机制

- **PreToolUse(Bash) gate**：只在 `tool_input.command` 里**出现本技能 `scripts/` 绝对路径**时才动作（命令碰了本技能脚本才管）。其余一律放行。零误伤无关项目。
- **UserPromptSubmit injector**：只在 `cwd` 下存在 `analysis_config.json` 时注入（= 一个活跃分析会话）。否则放行。

技能脚本路径常量：`/Users/tqa946816/Documents/华为/光伏预测/结果分析skill/pv-result-analysis/scripts`（与 SKILL.md 里既有硬编码绝对路径一致，本机可用）。为将来扩展，脚本内维护一个"受管技能 scripts 路径列表"，加一行即可纳管 `pv-feature-blame` / `pv-station-influence`。

### 4.2 `PreToolUse(Bash)` —— 编排闸

输入判定字段：`tool_input.command`、`cwd`、`agent_id`（主会话为空，subagent 非空）。逐条判定（命中即 `deny`，都不命中则不输出、`exit 0` 放行）：

1. **强制先 orient**：命令跑本技能某脚本，但**不是** `run_orient.py`，且 cwd 下**没有 `analysis_state.json`**（orient 从没跑过）→ deny，reason：`先跑 run_orient.py 定位阶段，再按它的 NEXT ACTION 行动。` → 治**跳步**。
2. **缺 config 别猜**：命令跑本技能某脚本，但 cwd 下**没有 `analysis_config.json`**，且不是 orient（orient 自己处理无 config）→ deny，reason：`缺 analysis_config.json——还没收集路径。用 AskUserQuestion 向用户要 metric.py / true_label / predicted 路径，别猜。` → 治**不问就猜**。
3. **画图必派 subagent**：命令跑 `run_analysis.py` 或 `run_drift.py`，且 `agent_id` 为空（= 主上下文）→ deny，reason：`图谱画图 + 事实提取必须外包 subagent（Brief A），不要在主上下文跑（图与 stats 会爆主上下文）。请派 general-purpose Agent，照抄 references/subagent-briefs.md 的 Brief A。` → 治**不派 subagent**。subagent 内 `agent_id` 非空 → 放行。

判定顺序：先 3（最具体）还是先 1？——按"最具体先判"：命令是 run_analysis 且主上下文 → 出 3 的 reason（最贴切）。但若同时 orient 没跑过，1 也成立。取**顺序 3 → 1 → 2**，命中第一条即返回，reason 最贴合当前动作。

`deny` 输出格式：
```json
{"hookSpecificOutput":{"hookEventName":"PreToolUse","permissionDecision":"deny","permissionDecisionReason":"<上面的中文 reason>"}}
```
`exit 0`。reason 文本会回给模型、促其改道。

**已知取舍**：本闸硬拦主上下文的 run_analysis/run_drift，会同时挡掉 SKILL 里"单张补图/调试主 agent 也可直接跑"的合法用法。对弱模型这是**有意为之**；reason 里附一句"若确需主上下文调试单图，请先跟用户确认再由用户临时移除本 hook"。放宽只需改脚本一行（如只在 `--figs` 含多图时拦）。

### 4.3 `UserPromptSubmit` —— 纪律注入

- 判定：`cwd` 下有 `analysis_config.json` → 注入；否则放行（无输出、`exit 0`）。
- 注入内容（`hookSpecificOutput.additionalContext`，必须嵌在 `hookSpecificOutput` 内，顶层会被静默忽略）：一段铁律提醒——你在跑 pv-result-analysis：① 每步先 `run_orient.py` 看 NEXT ACTION 并逐字执行；② 画图必派 subagent；③ 不确定/缺输入立刻 AskUserQuestion，绝不猜；④ 标"已证实"前过三道门。
- 输出格式：
```json
{"hookSpecificOutput":{"hookEventName":"UserPromptSubmit","additionalContext":"<铁律文本>"}}
```
`exit 0`。

### 4.4 不做 Stop hook（记录决策）

失败模式是模型**冲过** 3→4 停顿点，而非过早停止——那属 PreToolUse/orient 管辖。Stop hook 多会误伤合法暂停，且需 `stop_hook_active` 防循环、有 8 次连拦上限，收益不抵复杂度。暂不做；若将来 3→4 仍漏，再加一个只在"Stage 3 done 且 Stage 4 未开始且 last_assistant_message 不含向用户提问"时 block 的窄 Stop hook。

## 5. 安装与配置

- hook 脚本：`pv-result-analysis/hooks/pretooluse_gate.py`、`pv-result-analysis/hooks/userpromptsubmit_inject.py`（可执行，`#!/usr/bin/env python3`，从 stdin 读 JSON）。
- 提供 `pv-result-analysis/hooks/README.md`：说明作用、自限定作用域、如何关（删 settings 段或临时改）。
- 提供一段可复制的 `~/.claude/settings.json` `hooks` 片段（PreToolUse matcher=`Bash`、UserPromptSubmit matcher=`""`），指向两个脚本绝对路径。
- **不自动改用户全局 settings**——安装是用户手动动作（改全局配置属外向、需用户确认）。实现计划里安装步骤为"给出片段 + 让用户确认写入"，或提供一个幂等的 `install_hooks.py`（读现有 settings、合并 hooks 段、写回，先备份），但**默认只打印片段让用户自行粘贴**，除非用户明确让脚本写。

## 6. 测试

- **Layer 1（orient NEXT ACTION）**：pytest 覆盖每个阶段状态 → 期望的 NEXT ACTION 关键字（缺 config → "AskUserQuestion"；Stage 2–3 → 含材料化 Agent 派发块与正确 RANGE/FIGS；3→4 → "STOP…报用户"）。复用现有 orient 测试骨架（若有）。
- **Layer 2 hook 脚本**：pytest 喂各种 stdin JSON，断言输出/退出码——
  - PreToolUse：run_analysis + 无 agent_id → deny 且 reason 含"subagent"；run_analysis + 有 agent_id → 放行(空输出/exit 0)；skill 脚本 + 无 config → deny 含"AskUserQuestion"；非 skill 命令 → 放行；非本技能脚本路径 → 放行。
  - UserPromptSubmit：cwd 有 config（用 tmp_path + monkeypatch cwd 或 stdin 的 cwd 字段）→ 注入；无 config → 放行。
- 全仓既有 pytest 必须仍绿。
- hook 脚本零第三方依赖（只标准库 `sys/json/os`），启动快（PreToolUse 有超时预算）。

## 7. 回滚

- Layer 1 纯增量（orient 追加块 + SKILL 顶部前言），可单独 revert。
- Layer 2 完全外置于 `~/.claude/settings.json`：删掉那两段 hooks 即彻底停用，技能行为回落到 Layer 1。

## 8. 收尾纪律（沿用本技能既有约定）

- 每处改动在 `pv-result-analysis/CHANGELOG.md` 追加一行（日期 | 改哪节 | 触发反馈 | 为什么）。
- 运行后回顾：真实跑一次弱模型验证四种失败是否被拦，暴露的新问题写回 SKILL/scripts/hooks。
