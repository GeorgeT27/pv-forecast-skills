# Agent 卡片规格（`agents/<id>-compute.md` 的唯一模板来源）

本文件不是可派发的卡片，`test_cards.py` 不校验它（文件名不匹配 `*-compute.md`）。
Task 3–7 写卡片时照本文件的模板实例化；写完必须过 `scripts/tests/test_cards.py`。

## 1. 四种 mode（设计 §7）

| mode | 适用 playbook 结构 | 卡片拥有的阶段 | 停顿 | 守卫要点 |
|---|---|---|---|---|
| `producer` | 有 `produces`、无任何 `pause_after`、无结论阶段 | 全部生产阶段，跑到产物落盘 | 无（产物落盘即返回） | `produces` 必须是已知产物之一；playbook 全部 stage 都不得有 `pause_after` |
| `compute` | 至少一个 `subagent_ok:true` 阶段、且有 `pause_after` | 从 stage 0 起连续到并包含第一个 `pause_after` 的「计算区间」 | 区间终点即交回主 agent | `compute_stages` 区间内每个 stage 在 playbook 里必须 `subagent_ok:true`；区间内必须存在至少一个 `pause_after:true` 的 stage；结论阶段（`subagent_ok:false`）不进区间 |
| `compute-fine` | 无任何 `subagent_ok:true` 阶段、无 `pause_after`（目前只有 subset-influence） | 不整段交接；只认领主 agent 逐次指派的**一个**具名重活脚本 | 无整段停顿，每个脚本工跑完即回 | playbook 全部 stage 都不得有 `subagent_ok:true`；`compute_stages` 字面值固定为 `"scripts"` |
| `worker` | 有 `subagent_ok:true` 的重训/评估型阶段，且这些阶段的工作单元是「一条配置 + ≥3 种子」 | 不整段交接；每次只执行主 agent 指派的一条任务，回一张 receipt | 每条任务即回 | `compute_stages` 固定 `"scripts"`；`serves_stages` 列出的 stage 必须 `subagent_ok:true`；输出契约含 `receipt_line`；文件名 `<playbook>-worker.md` 或 `<playbook>-baseline.md` |

`compute` 卡片若在结论阶段之后仍有 `subagent_ok:true` 的变体阶段（如 feature-importance 的 5–6），
在 frontmatter 填 `on_demand_stages`；这些阶段停顿后由主 agent 按用户点名再派同一张卡片，
`test_cards.py` 不校验 `on_demand_stages`。

## 2. frontmatter 字段

```yaml
---
name: <id>-compute                    # 派发 key = 文件名去 .md；必须等于 <playbook>-compute
description: 一句话——覆盖什么诊断目标、跑到哪里止步   # 模糊路由兜底键，不参与守卫
mode: compute                         # producer | compute | compute-fine | worker
playbook: <id>                        # → ./playbooks/<id>/playbook.md
compute_stages: "0-1"                 # producer=全程区间; compute=计算区间 "lo-hi"; compute-fine=固定字面量 "scripts"
on_demand_stages: "5-6"               # 可省；仅 compute 且有结论后变体阶段时写
produces: ""                          # 有产物才填，取值须 ∈ {setup, model_profile, metric_table, chart_sweep, eval_report}
tools: [Bash, Read, Write]            # 逐卡按实际需要锁死；AskUserQuestion 永远不出现在这个列表里
model: sonnet                         # 计算工默认 sonnet；重推理阶段可提到更高档
---
```

- `name` 与文件名的双重命名律：`name == <playbook>-compute` 且 `os.path.basename(文件) == name + ".md"`。
- `playbook` 必须是真实存在的 playbook id（`ec.find_playbook(playbook)` 能找到 `playbooks/<playbook>/playbook.md`）。
- `tools` 缺省视为空列表；不管填不填，都不得出现 `AskUserQuestion`。

## 3. 正文六节模板

六节标题固定用以下写法（守卫按子串匹配，标题多字不影响）：

```markdown
## 你是谁

一句话身份：只做「<该卡片的计算范围>」的计算，不问用户、不下结论。

## 输入（主 agent 派发时给你）

- 工作目录：`<workdir>`
- 引擎目录：`<ENGINE>`（绝对路径，含 scripts/ playbooks/ chartbook/）
- 已答问题：<列出该 playbook §7 对应的 question id 及答案，逐条>
- 已就绪的上游产物目录：<例如 `setup=<path>`；按 playbook upstream 声明列全>

## 步骤（去菜谱）

按 `playbooks/<id>/playbook.md` 的 Stage `<compute_stages>` 执行；
用 `python3 "<ENGINE>/scripts/orient.py" --playbook <id>` 领阶段与 prereq；
生成脚本前必过 `python3 "<ENGINE>/scripts/gen_gate.py" --script <path> --playbook <id> --stage <n>`
（golden 在副本的 playbook 目录，脚本自动引用，卡片不内联菜谱正文）。

## 红线

- 不问用户：缺答案不猜，走 NEED_INFO。
- 不下结论：compute 只到「现象」为止；变体阶段只到证据合流前为止。
- 单写者：只写自己的产物文件，不碰 `batch_state.json`/`*config.json` 等共享状态（那些由主 agent 写）。
- 禁再派 subagent：重活拆分是主 agent 的事，本卡片不得自行派发下一层 subagent。

## 输出契约

你的 final message **就是**下面这个 JSON，不是给人看的自然语言：

```json
{
  "status": "COMPUTE_DONE | NEED_INFO | BLOCKED",
  "playbook": "<id>",
  "phenomena_file": "phenomena_<id>.json",
  "produces_dir": "",
  "artifacts": ["…"],
  "phenomena": ["≤30 行现象摘要，引图 JSON 数字，不贴 CSV/parquet 明细"],
  "verification": ["<验证步/闸名 + 数字 + 过/不过>，如 gen_gate stage1 PASS；对账 行数 12480/12480、抽 3 窗逐值一致"],
  "need_info": [{"question_id": "…", "ask": "…", "why": "…"}],
  "blocked_reason": ""
}
```

- `COMPUTE_DONE`：填 `phenomena_file`/`produces_dir`/`artifacts`/`phenomena`。
- `NEED_INFO`：填 `need_info`（未答的 prereq 问题），不猜、不推进。
- `BLOCKED`：填 `blocked_reason`（材料缺失/脚本失败等）。
- `verification`：区间内跑过的每个验证步/闸各一条（名字 + 数字 + 过/不过）；主 agent 记入 PROGRESS.md。

## 停顿/交回

跑到 `compute_stages` 终点即返回，不继续往后跑结论阶段；
结论、变体升级判定、跨图正交检查由主 agent 接手。
```

### 3.1 producer 卡片的正文差异

- 「步骤」= 跑 playbook 全程到 `produces` 声明的产物落盘 + 产出清单，不停在中途；
  替换后的「步骤」正文**仍必须保留字面指针** `playbooks/<id>/playbook.md`（例如写成
  「按 `playbooks/<id>/playbook.md` 全程跑到产物落盘」），不得只留语义描述、丢了这条指针——
  守卫按字面子串匹配，缺了这行原样字符串就会判卡片不合规。
- 「输入」里「已答问题」= 该 playbook §7 表里列的上游问题（主 agent 派发前已问过）。
- 无「停顿/交回」节的等待语义——改写为：产物落盘即返回
  `status: COMPUTE_DONE, produces_dir: <产物工作目录>`（六节标题本身仍保留「停顿」二字以过守卫）。

### 3.2 compute-fine 卡片的正文差异

- 「步骤」= 只按主 agent 指派运行**一个**具名重活脚本（例如 `find_bad_rows.py` / `feature_blame.py` /
  影响力回归 / `tracin` / `counterfactual_api.py`），逐次落各自产物文件，回数字摘要；
  阶段进度、Mode 选择、结论均由主 agent 驱动，卡片本身不整段交接。
  替换后的「步骤」正文**仍必须保留字面指针** `playbooks/<id>/playbook.md`（例如写成
  「步骤总纲仍指向 `playbooks/<id>/playbook.md`，具名脚本定义在其对应 Stage」）——
  具名脚本本身没有独立菜谱文件，这条指针是卡片与菜谱之间唯一的字面连接，不得省略。
- 「红线」额外加一条：一次只跑被指派的一个脚本/一层，不自行连跑下一个。

### 3.3 worker（架构归因重训工）

- frontmatter：`compute_stages: "scripts"`、`serves_stages: [0, 3]`（列出的 stage 必须 `subagent_ok: true`）。
- 「步骤」= 主 agent 一次派一条任务（`task=noise-floor | intervention`），一条跑完即回，不连跑下一条。
- 「输出契约」= receipt 契约：`receipt_line, receipt_file, config_diff, per_seed, mean, std,
  noise_floor_3sigma, instability_note`（守卫按 `receipt_line` 字面串校验）。
- 本卡不跑 `orient.py`：阶段状态的单写者是主 agent。

## 4. 命名律与薄卡预算

- 命名律：卡片文件名 = agent name = `<playbook-id>-<role>.md`，role ∈ {compute, worker, baseline}；
  每个 playbook 恰好一张 `-compute`，`-worker`/`-baseline` 只在 playbook 声明该角色时存在。
- 薄卡预算：正文非空行数 ≤80 行；正文不得出现 `## 逐阶段菜谱` / `### Stage` / `## 2. 逐阶段`
  等菜谱标题——凡是要讲步骤细节的地方一律指针化到 `playbooks/<id>/playbook.md` /
  `scripts/orient.py` / `scripts/gen_gate.py`，golden 绝不进卡片。
- 每张卡片写完后用 `python3 -m pytest scripts/tests/test_cards.py -q`（在 `ts-diagnose/` 下运行）自检。
