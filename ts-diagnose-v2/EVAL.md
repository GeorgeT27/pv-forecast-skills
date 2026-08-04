# EVAL.md——v1/v2 准确率 A/B 对比口径（人工，无自动打分器）

> 目标读者：拿到真实数据后要跑 v1 vs v2 对比评估的人。本文件不含分析逻辑、不改
> 引擎，只写「怎么跑、比什么、怎么记」。

## 1. 目的与单变量框架

v2 相对 v1 **只替换派发机制**（谁执行、怎么派、身份怎么定）：菜谱
（`playbooks/<id>/playbook.md`）、确定性闸（`gen_gate`/`conclusion_gate`/
`provenance` + golden）、提问上浮/停顿归主/结论归主/禁嵌套/单写者纪律，v2 与 v1
逐字相同（见设计规格 §2 表、§17 全局约束）。因此：**A/B 观测到的任何差异，理论上
只应源于派发架构本身**（预定义具名卡片 vs 现场注入 Brief），不应源于分析逻辑分叉。
若某次对比出现了看起来像「分析结论不同」的差异，先检查是不是有人动了 v2 里冻结的
`scripts/ playbooks/ chartbook/ golden/ references/`（除
`subagent-briefs.md` 那一行路径修正）——一旦改了，A/B 就从「测派发架构」退化成
「测两套菜谱」，实验作废，需先撤回改动再重跑。

本版不接真实数据，不做首次实跑；下面的流程与对比表就绪，等用户给真实路径后按本
文件执行首个 A/B（呼应设计规格 §18「待定/后续」）。

## 2. Claude Code 限制

- 只有落在 `.claude/agents/*.md` 的文件会被 Claude Code 注册成可按名字派发的
  `subagent_type`。`ts-diagnose-v2/agents/` 下的 11 张卡片不在那个目录里，因此在
  一次真实 CC 会话中**不能按名字直接派发**——Task 工具的 `subagent_type` 枚举里
  不会出现 `model-comparison-compute` 这样的名字。
- 这对本项目目标无碍：v2 卡片从一开始就设计成**可移植源文件**，目标运行环境是
  「你自己的 Claude SDK」（见第 3 节），不是 CC 的 `subagent_type` 注册机制。
  A/B 对比因此不在 CC 里用真派发跑，而是按第 4 节的口径，在能真正按名字加载卡片
  的环境里跑（你自己的 SDK，或至少是能把卡片当 system prompt 加载的宿主）。
- **CC 内如果仍想演示/冒烟测试派发效果**（比如验证卡片文字本身是否可执行、
  没有真 SDK 环境时先看个大概）：主 agent 派一个通用 `general-purpose` worker，
  把目标卡片文件整份当 context 交给它——"读 `agents/<id>-compute.md`，按其
  身份/输入/步骤/红线/输出契约执行"。worker 的行为由卡片内容驱动，但它注册的
  身份仍是 `general-purpose`，不是 `<id>-compute`：**这是模拟，不是真派发**，
  不能当作 A/B 里「v2 派发架构」的正式跑法，只用于卡片文字本身的可执行性冒烟。

## 3. 你自己的 Claude SDK

- SDK 里 agent 定义通常是一个 `name → 定义` 的查表结构（`agents[name]`）；派发即
  传 `subagent_type=name`，运行时用这张表查出对应卡片当 system prompt 加载——
  这正是 v2 卡片「文件名 = agent name = 派发 key」命名律（`<id>-compute`）存在的
  原因：11 张卡片天然就是这张表的 11 条记录，不需要额外的名字映射层。
- 卡片当前形态是「薄壳 + 指向 `playbook.md` 的指针」（步骤节写「按
  `playbooks/<id>/playbook.md` 的 Stage `<compute_stages>` 执行」，不内联菜谱
  正文）。如果目标 SDK 运行环境的 worker 不能像 v2 引擎那样按相对路径读取
  `playbook.md`（例如 worker 没有文件系统访问权限，或卡片要打包成单文件 payload
  跨环境分发），移植时需要 **flatten-on-export**：把卡片指向的那段
  `playbook.md` Stage 内容内联进卡片正文，生成一份「胖卡」。卡片当前的薄+指针
  形态使这一步内联无痛——只需替换「步骤」节这一处指针，其余五节（你是谁/输入/
  红线/输出契约/停顿）不用动。
- flatten-on-export 脚本本版不做（设计规格 §18 明确列为后续工作）；本版交付的是
  「薄卡 + 指针」这个可移植中间形态本身。

## 4. A/B 对比口径

**跑法**：同一个诊断目标 + 同一份数据，分别完整跑一遍：

- **v1**：入口 `ts-diagnose/SKILL.md`（通用 worker + 现场注入 Brief）；
- **v2**：入口 `ts-diagnose-v2/SKILL.md`（按名字派发预定义卡片，见
  `references/dispatch-protocol.md`）。

两边各自产出一份完整的诊断产物目录（含 `CONCLUSION.md`、`gate_reports/`、
`FINDINGS.md`、phenomena 文件等），互不共享工作目录、互不复用中间产物——要测的是
从头到尾的派发路径差异，不是抄近道对齐。

**对比维度（四项，逐项记录 v1 与 v2 各自结果，列出差异）**：

1. **`CONCLUSION.md` 证据层级**：同一条陈述在 v1/v2 下是否被打上同样的
   现象/假设/已证实/被推翻标签（engine-core.md「结论纪律」的四个保留字）；
   不一致时定位到具体是哪一道门（稳健性/假设登记/反驳门）导致升级判定分叉，而
   不是笼统写「结论不一样」。
2. **`gate_reports/conclusion_gate.json` receipt**：两边是否都拿到了通过的
   receipt（结论阶段唯一的完成判据，只能由 `conclusion_gate.py` 生成）；receipt
   里记录的具体检验项（配对检验、剔除极端 10% 后方向、反驳门条目排除情况）是否
   一致。
3. **现象清单与被点名的切片/特征**：v1 与 v2 各自 `phenomena_<id>.json`/
   `FINDINGS.md` 的条目数、内容是否一致；用户在停顿点点名要深挖的切片/特征集合
   是否一致——这一项容易被两边呈现现象清单的格式差异带偏（v2 卡片输出契约是固定
   JSON，v1 是 Brief-FACT 的自然语言清单），记录差异时把呈现格式本身一并写下，
   避免把「格式不同」误判成「内容不同」。
4. **到结论的往返轮次与提问次数**：从进入 playbook 到 `CONCLUSION.md` 写完，
   AskUserQuestion 触发几次、每次问的是哪个 question id、总共停顿/恢复几轮——
   这项直接反映派发架构（现场拼 Brief vs 按名字派发定型卡片）对交互效率与提问
   纪律执行力度的影响，是本次 A/B 最想测的东西之一。

**记录方式**：人工填表，不写自动打分脚本。每次 A/B 针对一个诊断目标产三份东西：
v1 跑法的完整产物目录、v2 跑法的完整产物目录、一份按上述四项写的对比小结。小结
聚焦「差异点 + 可能的架构成因」，不复述整份 `CONCLUSION.md`——`CONCLUSION.md`
本身已经在各自的产物目录里，读原文即可核对。

**强调单变量框架**：填表时如果某一项差异明显是分析逻辑造成的（比如某个 playbook
在 v2 副本里 golden 或菜谱被误改），先回到第 1 节按冻结约束排查，不要把它计入
「派发架构差异」——那会污染 A/B 的结论。
