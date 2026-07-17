# pv-feature-blame 上下文预算编排（thin-orchestrator subagent 调用）设计

日期：2026-07-17
技能：`pv-feature-blame`
状态：已批准，待写实现计划

## 1. 问题

运行本技能的机器上主模型上下文只有 **256k**，偏小。一次完整的六阶段归因（探查 → 坏行 → 归因 → 现象 → 反事实 → 结论）如果由主 agent 串行、且把 parquet / CSV 正文 / API payload 读进上下文，主 agent 上下文会撑爆，长任务难以完成。

现状：技能**已经**为上下文隔离打好底子——阶段化、产物落盘、`run_orient.py` 每次从磁盘重扫定位阶段（不信任记忆）、单写者纪律已成文。缺口是：**subagent 外包被当成"主 agent 可选的优化"，而主 agent 经常忘记调用**，正文里只有一句软提示 `重活外包 subagent`。

补充确认（非本技能缺陷，只是澄清）：
- 本技能**不用也不需要 git worktree**。subagent 走单写者纪律，各写各的产物分片，共享同一工作目录即可。机器没连 GitHub 对本技能零影响。
- `adapter.py` 技能里没有是**故意的**——只有模板 `scripts/api_adapter_template.py`，用户在工作目录 `cp` 成 `adapter.py` 填契约，仅 Stage 4 反事实用。

## 2. 目标

把主 agent 变成**只调度、不碰数据的 thin orchestrator**，并让"每个计算阶段外包给 subagent"从"靠模型记性"变成"**被 `run_orient.py` 打印出来的确定性指令**"。

成功判据：一次完整运行，主 agent 上下文只累积「orient 输出 + 每阶段 ≤30 行数字摘要」；parquet / CSV 正文 / payload 明细**永不进主 agent 上下文**；主 agent 不再漏调 subagent。

## 3. 编排契约（谁拥有什么）

| 拥有者 | 职责 | 理由 |
|--------|------|------|
| **主 agent** | 跑 `run_orient.py`；按 orient 的 NEXT ACTION 派发 subagent；读 ≤30 行摘要；写状态文件（`blame_state.json` / `PROGRESS.md` / `FINDINGS.md` / `blame_config.json` / `feature_pairs.json`）；**一切用户交互**（AskUserQuestion、Stage 3 停顿、Stage 4 `--dry-run` payload 确认）；反驳门 | 需要对话上下文 + 是单写者；token 便宜 |
| **subagent（各自新的 256k）** | 跑该阶段脚本；**自己**跑 `run_orient.py` 从磁盘重建所需状态；只写自己的产物分片；只回数字 | 重上下文（parquet / CSV / payload）在 subagent 内生灭，永不回主 agent |

关键使能点已存在：`run_orient.py` 每次从磁盘重推真相，所以主 agent 派发时**只传「工作目录绝对路径 + 阶段号」，不传任何数据**；subagent 靠自己跑 orient 重建上下文。

### 用户交互边界（已批准）

三个"需要用户"的环节留在主 agent inline，其余纯计算外包：

- **Stage 0 unmapped**：subagent 跑 `probe_schema.py`；若返回 `unmapped` 非空 → 主 agent inline 处理（AskUserQuestion → 写 `feature_pairs.json` → 重新派发）。
- **Stage 3 停顿**：主 agent inline 汇报现象、问是否做反事实。
- **Stage 4 dry-run 确认**：主 agent inline 跑 `--dry-run`、拿用户确认 payload；确认后批量调用才外包。

（subagent 不能调 AskUserQuestion，故这三处必须 inline。）

## 4. 三处改动

### 改动 1 —— `run_orient.py` 打印派发决策（核心修复）

新增 `next_action(cur, cfg, ev)`，把当前阶段映射为 **DISPATCH** 或 **INLINE**，DISPATCH 时打印一段可直接粘贴的 brief，其中的**活事实**由 orient 就地读取的廉价 JSON 提供（模型列取自 `bad_rows_summary.json`，口径取自 `config.metrics`——都不读 parquet）。

| 阶段 | 决策 | orient 打印内容 |
|------|------|----------------|
| 0 probe | **DISPATCH**（可能回弹） | 派 subagent 跑 `probe_schema.py`；若 `unmapped` 非空 → 主 agent inline 问用户、写 `feature_pairs.json`、重派 |
| 1 bad-rows | **DISPATCH** | brief 内列出已发现的模型 + 口径 |
| 2 blame+revision | **DISPATCH** | "按模型分片：`<M1, M3, ensemble>`（就地取名）"，各写 `*_<model>` 分片 |
| 3 findings | **INLINE** | "HANDLE INLINE —— Stage 3 是用户停顿点，汇报现象、问反事实" |
| 4 counterfactual | **INLINE → 再 DISPATCH** | "INLINE：跑 `--dry-run` 拿用户确认；然后派发批量（Brief H/I）" |
| 5 conclusion | **INLINE** | "HANDLE INLINE —— 在小摘要上做综合 + 反驳门" |

orient 输出末尾因此总有一条无歧义、可粘贴的指令。**这是 brief 的唯一操作来源**——不再有手写 brief 让模型跳过。

打印的 brief 模板（DISPATCH 通用形，orient 就地填 `<...>`）：

```
── NEXT ACTION (context-budget mode) ─────────────────────
Stage <N> 是计算阶段 → 派发 subagent（general-purpose），别 inline 跑。
把下面这段贴进 Agent 调用：

  工作目录：<abs path>
  先跑：python3 <SKILL>/scripts/run_orient.py   （自校 Stage <N> 前置）
  再跑：<该阶段脚本 + 参数；≥2 模型则分片 --models <名>，各写 *_<model> 产物>
  只回：<该阶段的数字摘要清单>。不要贴 CSV 正文 / parquet 行 / payload 明细。
  禁碰：blame_state.json / PROGRESS.md / FINDINGS.md / blame_config.json / feature_pairs.json
───────────────────────────────────────────────────────────
```

INLINE 形：
```
── NEXT ACTION (context-budget mode) ─────────────────────
Stage <N> 需要用户交互 → 主 agent 亲自处理，别派 subagent。
<该阶段的 inline 动作：问什么 / 确认什么>
───────────────────────────────────────────────────────────
```

实现约束：`next_action` 只读已有的 `ev`（scan 结果）+ cfg + 廉价 JSON（`bad_rows_summary.json` 取模型名），**不新增任何 parquet 读取**；`<SKILL>` 用 `os.path.dirname(os.path.dirname(__file__))` 推导，不硬编码绝对路径。

### 改动 2 —— `SKILL.md` 加一段硬编排契约（替换软提示）

把现有软行 `## 编排：主 agent 调度，重活外包 subagent` 替换成靠前的短硬协议：

> **上下文预算模式（默认）。** 你是调度者，永不加载 parquet / CSV / payload。循环：跑 `run_orient.py` → **严格照** 其 `NEXT ACTION` 块执行 → 遇 DISPATCH 行**必须**派 subagent（绝不 inline 跑该阶段）→ 读其 ≤30 行摘要 → 再跑 `run_orient.py`。只有 INLINE 行才由你亲自执行。

### 改动 3 —— `references/subagent-briefs.md` 降为原理说明

操作用 brief 改由 orient 就地打印（带活事实、永不失真）。briefs.md 精简为**为什么**（单写者纪律、什么绝不进对话）+ Stage 4 阶梯（G/H/I）的细节保留。消除静态 brief 与现实漂移。

## 5. 影响与非目标

- **主 agent 上下文**：一次完整运行 = orient 输出 + 每阶段 30 行摘要。重活在 subagent 内生灭。
- **非目标**：不改任何分析数学（z 分数 / 全局 Spearman / cf_logic / 阶梯）；不引入 git/worktree；不动 adapter 契约机制；本次只做 pv-feature-blame（但 orient 的 next_action 模式设计成可复制到三姊妹技能）。
- **质量闸**：改了 `run_orient.py` 属编排层、不入 gen_gate 的分析脚本闸；但 orient 的 `next_action` 需要单元测试覆盖「每阶段映射到正确的 DISPATCH/INLINE + brief 里模型名填对」。

## 6. 测试

- `run_orient.py` 新增 `next_action` 的单测：构造六种阶段的工作目录 fixture（靠 touch 空产物文件 + 最小 JSON），断言每阶段打印 DISPATCH/INLINE 正确、Stage 2 的 brief 含 `bad_rows_summary.json` 里的模型名、Stage 0 回弹提示存在。
- 回归：现有 orient 行为（阶段定位、前置校验、feature_true 硬规则、state/PROGRESS 写入）不变。
- 全仓 `pytest` 保持绿。
