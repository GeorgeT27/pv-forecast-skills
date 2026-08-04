# ts-diagnose v2（预定义 agent 卡片版）设计规格

> 目标读者：实现工程师与后续做 v1/v2 准确率对比评估的人。
> 状态：设计定稿，待用户复核 → 进 writing-plans。
> 日期：2026-08-04。

## 1. 一句话目标

把 ts-diagnose 的**派发层**从「主 agent 给通用 subagent 注入 Brief」改成「主 agent 按名字派发预定义的 agent 卡片」，其余（菜谱、闸、golden、引擎脚本、提问/停顿/结论纪律）全部沿用 v1，产出一个**自包含**的 `ts-diagnose-v2/`，供后续与 v1 做同数据、同目标的准确率 A/B。

## 2. 动机与「只改一个变量」原则

v1 的诊断质量由三部分决定：①菜谱与证据规则（playbook.md + mechanisms + upgrade_rule）；②确定性闸（gen_gate/conclusion_gate/provenance + golden）；③派发与编排（谁来跑、怎么问、何时停、谁下结论）。

本项目**只替换 ③ 里的「派发机制」**，①②与「提问上浮/停顿归主/结论归主/禁嵌套/单写者」纪律逐字保留。这样后续 A/B 测得的差异可归因到唯一变量：

| 维度 | v1（skill） | v2（agent 卡片） |
|---|---|---|
| 主 agent 读什么 | `SKILL.md → engine-core → playbook.md` | `ts-diagnose-v2/SKILL.md`（编排脑） |
| 派谁干活 | **通用** worker + 现场注入 Brief | **预定义具名**卡片 `<id>-compute` |
| worker 身份 | 由 brief 临时拼 | 卡片 frontmatter 固定 |
| 工具权限 | 全量 | 卡片 `tools:` 逐个锁死（无 AskUserQuestion） |
| 菜谱来源 | playbook.md | **同一份** playbook.md（卡片指过去） |
| 提问 / 停顿 / 结论 | 主 agent | 主 agent（**完全一致**） |

## 3. 非目标（YAGNI）

- 不改任何 v1 菜谱、闸、golden、引擎脚本的**逻辑**。
- 不在 Claude Code 里把卡片注册成可按名派发的 `subagent_type`（见 §12，那是 `.claude/agents/` 的机制，不在本项目范围；v2 卡片是可移植源文件 + 供你自己的 Claude SDK 加载）。
- 不接真实用户数据；本版的「跑通」用 v1 golden 冒烟验证即可。
- 不做 v1↔v2 的自动打分器；EVAL.md 只写人工对比口径与流程。

## 4. 架构总览

v2 = **v1 引擎的自包含副本** + **一层派发卡片**。副本部分零逻辑改动（引擎用 `__file__` 自定位，见 §6），派发层是全部新增内容。主 agent 读 v2 的编排脑 SKILL.md，按名字派发 `agents/` 下的卡片；卡片是「薄」的——身份 + 输入 + 指针（去副本里的 playbook.md 拿菜谱）+ 红线 + 输出契约——菜谱与 golden 一律不进卡片。

## 5. 目录布局

```
ts-diagnose-v2/
  # ── 从 v1 逐字复制、不改逻辑（自包含引擎；<ENGINE> 自解析为 ts-diagnose-v2 本身）──
  scripts/          (32 文件)   orient.py batch.py gen_gate.py conclusion_gate.py
                                provenance.py engine_common.py … + tests/
  playbooks/        (152 文件)  全 11 个 playbook.md + 各自 golden/ + references/
  chartbook/        (102 文件)  chart 脚本 + recipes
  references/       (8 文件)    engine-core.md batch-orchestration.md mechanisms.md
                                intake.md question-discipline.md conclusion-reporting.md
                                crystallize.md subagent-briefs.md（1 行路径修正，见 §6）
  # ── v2 新增（派发层）──
  SKILL.md                      编排脑：路由表 + 卡片索引 + 派发增量；≤60 行/≤6000 token
  agents/
    _agent-spec.md             卡片模板 + 约定（三种 mode、命名、输出契约 schema）
    <id>-compute.md × 11       每个 playbook 一张薄卡（命名见 §7）
  references/dispatch-protocol.md   新文件，放进复制来的 references/：选卡 + 单playbook三明治
                                     + 批量 A–E 复用 + NEED_INFO 回环（详细协议）
  EVAL.md                       如何在同数据上跑 v1 与 v2、对比什么（§13）
  scripts/tests/test_cards.py         新增：卡片守卫
  scripts/tests/test_orchestrator.py  新增：编排脑守卫
```

## 6. 「复制」到底是不是纯 copy-paste

**约 99% 是。** 引擎自定位：`ENGINE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))`（`engine_common.py:24`），`PLAYBOOKS_DIR = ENGINE_DIR/playbooks`，`golden = PLAYBOOKS_DIR/<id>/golden`，`chartbook = ENGINE_DIR/chartbook`，`references = ENGINE_DIR/references` 全部相对自身位置解析。把四个目录复制进 `ts-diagnose-v2/` 后，所有脚本自动把 `ENGINE_DIR` 算成 `ts-diagnose-v2`，orient / batch / gen_gate / chartbook / golden **零代码改动即工作**。

**唯三非零改动（都很小）：**

1. **v2 拿一份全新的 `SKILL.md`**（编排脑，不从 v1 复制）。复制来的 `scripts/tests/test_layering.py` 把 `SKILL.md` 钉在 **≤60 行 / ≤6000 token** 且禁方法词（`Stage`/`done_when`/`pause_after`/`evidence_lines`/`findings_marker` 等）。v2 编排脑把细节下沉到 `dispatch-protocol.md`，正文只留路由表 + 卡片索引 + 派发增量，可满足预算 → 复制来的 `test_layering` 保持绿。
2. **`references/subagent-briefs.md:30`** 硬编码了 `.../ts-diagnose` 作为 ENGINE 路径。v2 用卡片、不用 brief，把该行改成 `ts-diagnose-v2`（或删该文件）。
3. **3 个 `project-context.pointer`**（subset-influence / result-eval / feature-importance）是绝对路径指向共享 `project-context/`——**原样复制**，它们正确解析到同一个共享目录，且 `engine_common.py:713` 也会把它当作 `ts-diagnose-v2` 的兄弟目录自动发现。**不改。**

**公平性硬约束（写进 §17）**：复制来的 `scripts/playbooks/chartbook/golden/references(除上述1行)` 此后**冻结**，只往上加 `agents/` 与派发层。一旦改了 v2 的菜谱/golden，A/B 就从「测派发架构」变成「测两套菜谱」，实验作废。

## 7. 卡片分类：三种 mode（11 张卡）

命名统一：文件名 = agent 名 = 主 agent 派发用的 key = `<playbook-id>-compute.md`（含 producer，保持派发端一条命名律；`mode` 字段区分行为）。

「计算阶段」= 从 stage 0 起、连续 `subagent_ok:true` 直到并包含第一个 `pause_after` 的阶段区间。之后的结论阶段（`subagent_ok:false`）永远归主 agent。

| # | playbook | mode | 产物 | 卡片拥有的阶段 | 停顿点 | 主 agent 派发前须答的问题（question id） |
|---|---|---|---|---|---|---|
| 1 | data-setup | **producer** | setup | 0–1（全程到产物） | 无 | freq, align-keys |
| 2 | model-audit | **producer** | model_profile | 0–4（全程到回执） | 无 | production-version |
| 3 | metric-eval | **producer** | metric_table | 0–1（全程到产物） | 无 | metric-spec |
| 4 | fact-scan | compute | chart_sweep | 0（即终点即停顿） | stage 0 | 无 |
| 5 | result-eval | compute | —（见下方说明） | 0–3 | stage 3 | metric-caliber |
| 6 | model-comparison | compute | —（分析） | 0–1 | stage 1 | metric-caliber, model-set |
| 7 | deployment-drift | compute | —（分析） | 0–2 | stage 2 | metric-caliber, deploy-timeline, degradation-criterion |
| 8 | feature-importance | compute | —（分析） | 0–3（+按需变体 5–6） | stage 3 | importance-scope, feature-list, model-access, collinearity-handling |
| 9 | robustness | compute | —（分析） | 0–3 | stage 3 | conclusions-under-test, metric-and-pairing, perturbation-families, group-columns |
| 10 | training-sufficiency | compute | —（分析） | 0–5 | stage 5 | loss-source, unit-structure, training-config, external-metric, fig-style |
| 11 | subset-influence | **compute-fine** | —（分析） | 无整段交接 | 无 | 无（阶段由主 agent 驱动） |

『主 agent 派发前须答的问题』取自各 playbook 的 `questions:` 块（stage ≤ pause），与 `evidence_lines`（产物证据行，非问题）区分。

**result-eval 不声明 `produces`**：`eval_report` 的 manifest（`gate_reports/conclusion_gate.json`）与 marker（`CONCLUSION.md`）只在 Stage 4（结论，`subagent_ok:false`）落盘，落在 `result-eval-compute` 卡片的 `0-3` 计算区间之外。卡片若声明 `produces: eval_report` 会让主 agent 误判该产物已建好，因此卡片 frontmatter 不带 `produces` 字段；卡片本身只回 Stage 0–3 的中间产出（指标表、图谱、FINDINGS.md 现象清单），`eval_report` 产物由主 agent 亲自跑完 Stage 4（结论 + manifest）后才算产出。守卫新增不变式：**compute 卡片一旦声明 `produces`，该产物的 manifest/marker 所在阶段必须落在卡片的 `compute_stages` 区间内**（`scripts/tests/test_cards.py` 里 `mode == "compute"` 分支据 playbook frontmatter 的 `produces.manifest`/`produces.marker_files` 反查其所在 stage 校验）；fact-scan 的 `chart_sweep_manifest.json` 落在 Stage 0（∈ 区间 0–0），因此仍可声明 `produces: chart_sweep`。

**三种 mode 的语义与守卫：**

- **producer**：playbook 有 `produces` 产物、无 `pause_after`、无 `CONCLUSION.md` 阶段。卡片拥有全部生产阶段、跑到产物落盘。其 `subagent_ok:false` 不阻挡外包——生产者外包由「主 agent 先答上游问题、再整体派发」规则治理（沿用 v1 Brief-PRODUCER 思路）。
- **compute**：playbook 至少有一个 `subagent_ok:true` 阶段且有 `pause_after`。卡片拥有「计算阶段」区间，跑到现象清单/产物即停，交回主 agent。区间内每个阶段必须 `subagent_ok:true`；结论阶段不在区间内。位于结论阶段之后、仍为 `subagent_ok:true` 的变体阶段（如 feature-importance 的 5–6）作为「按需变体」列出，主 agent 在停顿后按用户点名再派同一张卡片跑这些阶段。
- **compute-fine**：playbook 无任何 `subagent_ok:true` 阶段、无 `pause_after`（仅 subset-influence）。卡片不做整段交接，而是列出**具名重活脚本**（对照 v1 `subagent-briefs.md`：`find_bad_rows.py` / `feature_blame.py` / 影响力回归 / TracIn / `counterfactual_api.py`），主 agent 逐阶段驱动、按需派发这些脚本工，worker 只回数字摘要。

## 8. 卡片 schema（薄卡，正文 ≤60 行）

frontmatter 字段（全部卡片）：

```yaml
---
name: model-comparison-compute        # 派发 key = 文件名去 .md
description: 为什么模型A比B好/多模型对比归因的计算半段——跑到现象清单为止   # 模糊路由兜底键
mode: compute                         # producer | compute | compute-fine
playbook: model-comparison            # → ./playbooks/model-comparison/playbook.md（v2 自己的副本）
compute_stages: "0-1"                 # producer=全程; compute=计算区间; compute-fine="scripts"
on_demand_stages: "5-6"               # 可省；仅 compute 有结论后变体阶段时写
produces: ""                          # 有产物才填（setup/model_profile/metric_table/chart_sweep/eval_report）
tools: [Bash, Read, Write]            # 逐卡锁死；AskUserQuestion 一律不出现
model: sonnet                         # 计算工默认 sonnet；重推理阶段可提到更高档
---
```

正文固定六节（每节几行，指针化，不复述菜谱）：

1. **你是谁**：一句话身份 + 只做计算、不问用户、不下结论。
2. **输入**（主 agent 派发时给你）：工作目录 `<workdir>`；已答问题（列本卡 §7 的 question id 及答案）；已就绪的上游产物目录（`setup=<path>` 等）。
3. **步骤（去菜谱）**：按 `./playbooks/<id>/playbook.md` 的 Stage `<compute_stages>` 执行；用 `python3 ./scripts/orient.py --playbook <id>` 领阶段与 prereq；生成脚本前必过 `python3 ./scripts/gen_gate.py --playbook <id> --stage <n>`（golden 在副本的 playbook 目录，自动引用）。
4. **红线**：不问用户（缺答案→不猜，走 NEED_INFO）；不下结论（compute 只到「现象」、变体只到证据合流前）；单写者（只写自己产物，不碰 `batch_state.json`/`*config.json` 等共享状态，那些由主 agent 写）；禁再派 subagent（重活拆分由主 agent 做）。
5. **输出契约**：你的 final message **就是** §11 的 JSON，不是给人看的自然语言。
6. **停顿/交回**：跑到 `compute_stages` 终点即返回；结论、变体升级判定、跨图正交检查由主 agent 接手。

### 8.1 producer 卡片示例（data-setup-compute.md）

frontmatter：`mode: producer`，`compute_stages: "0-1"`，`produces: setup`，`tools: [Bash, Read, Write]`。
正文差异：步骤 = 跑 playbook data-setup 全程到 `setup` 产物落盘 + 清单；输入里「已答问题」= freq / align-keys（主 agent 派发前答）；无「停顿」节，改为「产物落盘即返回 `status: COMPUTE_DONE, produces_dir: <setup工作目录>`」。

### 8.2 compute-fine 卡片示例（subset-influence-compute.md）

frontmatter：`mode: compute-fine`，`compute_stages: "scripts"`，`tools: [Bash, Read, Write]`。
正文差异：步骤 = 只按主 agent 指派运行**一个**具名脚本（`find_bad_rows.py` / `feature_blame.py` / 影响力回归 / `tracin` / `counterfactual_api.py`），逐行落各自产物文件，回数字摘要；阶段进度、Mode A/B 选择、结论均由主 agent 驱动。红线额外加：一次只跑被指派的一个脚本/一层，不自行连跑（对照 v1 subagent-briefs.md Brief I）。

## 9. 主 agent 编排脑（ts-diagnose-v2/SKILL.md，≤60 行）

只装三样，其余下沉：

1. **路由表**：逐字复用 v1 SKILL.md 的「用户目标 → playbook」11 行表。
2. **卡片索引**：11 行 `playbook → agents/<id>-compute.md（mode）`。
3. **派发增量（本项目唯一的行为差异）**，原文写明：
   > 执行纪律全部继承 `./references/engine-core.md` + `./references/batch-orchestration.md`（提问上浮、停顿归主、结论归主、禁嵌套、单写者、批量 Phase A–E）。**只替换派发机制**：不再按 `subagent-briefs.md` 注入 Brief，改为按名字派发预定义卡片 `<id>-compute`；派发前先按该 playbook 的 §7 上浮问题问用户、把答案随派发带入；细节见 `./references/dispatch-protocol.md`。

编排脑不得出现被 `test_layering` 禁的方法词；「停顿」等词只出现在 `dispatch-protocol.md`。

## 10. dispatch-protocol.md（详细协议，新文件）

放进复制来的 `references/`，承接编排脑下沉的细节：

- **选卡**：主 agent 命中 playbook `X` → 派发 `X-compute`（确定性名字匹配）；批量模式下派发列表由 v1 `batch.py` 规划的 dispatch_list 逐条映射到卡片名；`description` 字段仅作模糊兜底。
- **单 playbook 三明治**：①主 agent 按 §7 上浮问题问用户 → ②确保必需上游产物就绪（先派 producer 卡片）→ ③派 `X-compute` 拿现象/产物 → ④处理 NEED_INFO（问用户后重派同卡）→ ⑤**停顿**：展示现象、用户点名深挖 → ⑥主 agent 亲跑变体派发（按需再派同卡的 `on_demand_stages`）+ 结论（`subagent_ok:false` 阶段）+ 闸。
- **批量 A–E**：完全复用 v1 `batch.py` 与 `batch-orchestration.md`；唯一差异是「Phase C 计算 fan-out」的每个 worker = 具名卡片而非注入 Brief。禁嵌套：重活由主 agent 拆成 Phase-C 平级兄弟卡片，树保持平。

## 11. 输出契约（每张卡片的 final = 此 JSON）

```json
{
  "status": "COMPUTE_DONE | NEED_INFO | BLOCKED",
  "playbook": "model-comparison",
  "phenomena_file": "phenomena_model-comparison.json",
  "produces_dir": "",
  "artifacts": ["gap_summary.json", "charts/…", "INDEX.md", "FINDINGS.md"],
  "phenomena": ["≤30 行现象摘要，引图 JSON 数字，不贴 CSV/parquet 明细"],
  "need_info": [{"question_id": "metric-caliber", "ask": "…", "why": "…"}],
  "blocked_reason": ""
}
```

- `COMPUTE_DONE`：填 `phenomena_file`/`produces_dir`/`artifacts`/`phenomena`。
- `NEED_INFO`：填 `need_info`（未答的 prereq 问题）；worker 不猜、不推进。
- `BLOCKED`：填 `blocked_reason`（材料缺失/脚本失败等）。

## 12. 问题如何回传主 agent（用户反复关切点）

两条通道，与 v1 硬约束一致（subagent 无提问权、无中途升级、单向返回 + 重派恢复）：

1. **主通道——上浮**：§7 列的上浮问题由**主 agent 在派发前**问用户，答案随派发带入卡片「输入」节。绝大多数问题走这条。
2. **兜底——NEED_INFO**：worker 中途撞到未答 prereq → 返回 `status: NEED_INFO` + `need_info[]`，**不猜**；主 agent 问用户后**重派同一张卡片**并补上答案。

## 13. Claude Code 限制与你自己的 SDK

- **Claude Code**：只有 `.claude/agents/*.md` 会被注册成可按名派发的 `subagent_type`。`ts-diagnose-v2/agents/` 里的卡片在实时 CC 会话中**不能按名直接派发**。这对本项目目标无碍：卡片是可移植的**源文件**，供你自己的 Claude SDK 作为 system prompt 加载。
- **CC 内演示派发**：主 agent 派通用 worker（general-purpose）+ 把对应卡片文件当 context 交给它（"读 `agents/<id>-compute.md` 并按其身份/契约执行"）。
- **你的 SDK**：`agents[name]` 字典查表加载卡片系统提示；派发 = 传 `subagent_type=name`。移植时把 playbook.md 内联进卡片即可（flatten-on-export），卡片当前的薄+指针形态使内联无痛。
- 以上写进 `EVAL.md`。

## 14. EVAL.md（对比口径，人工）

无自动打分器；文档化：同一诊断目标 + 同一份数据，分别过 v1（`ts-diagnose/SKILL.md`）与 v2（`ts-diagnose-v2/SKILL.md`），对比：①`CONCLUSION.md` 的证据层级（现象/假设/已证实）是否一致；②`gate_reports/conclusion_gate.json` receipt 是否都拿到；③现象清单与被点名切片/特征是否一致；④到结论的往返轮次与提问次数。强调单变量框架：任何差异只应源于派发架构。

## 15. 测试策略（无需真实数据）

复制来的 `scripts/tests/*` 测引擎，引擎未改逻辑 → 应全绿（`test_layering` 靠 v2 编排脑守预算保持绿）。新增两支守卫 + 两条 golden 冒烟：

**`scripts/tests/test_cards.py`**（对每张卡片）：
- frontmatter 合法；`playbook` 在 v2 副本里存在；`name == <playbook>-compute`。
- `mode` ∈ {producer, compute, compute-fine}，且与 playbook 实际结构相符（producer↔无 pause 有 produces；compute↔有 pause 且计算区间全 `subagent_ok:true`；compute-fine↔无 subagent_ok:true 阶段）。
- compute 卡片的 `compute_stages` 区间内每个阶段在 playbook 里都是 `subagent_ok:true`；结论阶段不在区间内。
- `tools` 不含 `AskUserQuestion`。
- 六节俱全 + 输出契约节存在；正文 ≤60 行；**无菜谱重复**（正文不得出现 `## 逐阶段菜谱`/`### Stage` 等菜谱标题，必须指向 playbook.md）。

**`scripts/tests/test_orchestrator.py`**：
- 路由表覆盖全 11 playbook；每个 playbook 恰有一张卡片；命名律 `<id>-compute` 处处成立。
- 派发增量节引用 `batch.py` 与 `engine-core.md`；编排脑满足 `test_layering` 预算与禁词。

**两条 golden 冒烟**（model-comparison、training-sufficiency）：在各自 golden 工作目录跑 `python3 scripts/orient.py --playbook <id>`，断言阶段步进正常、`gen_gate.py --playbook <id>` 通过、计算区间跑完产出 `phenomena_<id>.json`。证明卡片指向的管线在副本上真的能跑，无需真实数据。

## 16. 文件职责一览（新增层）

| 文件 | 职责 |
|---|---|
| `SKILL.md` | 编排脑：路由 + 卡片索引 + 派发增量；≤60 行；继承 v1 纪律 |
| `agents/_agent-spec.md` | 卡片模板 + 三 mode 约定 + 命名律 + 输出契约 schema |
| `agents/<id>-compute.md` ×11 | 每 playbook 一张薄卡；身份/输入/指针/红线/契约/停顿 |
| `references/dispatch-protocol.md` | 选卡 + 单playbook三明治 + 批量 A–E + NEED_INFO 回环 |
| `EVAL.md` | v1/v2 对比口径与流程；CC 限制与 SDK 移植说明 |
| `scripts/tests/test_cards.py` | 卡片守卫 |
| `scripts/tests/test_orchestrator.py` | 编排脑守卫 |

## 17. 全局约束（Global Constraints）

- **引擎冻结**：v2 复制来的 `scripts/ playbooks/ chartbook/ golden/ references/`（除 `subagent-briefs.md` 那 1 行路径）逻辑冻结，只往上加派发层。违反即 A/B 作废。
- **薄卡**：每张卡片正文 ≤60 行、零菜谱、golden 绝不进卡片；步骤一律指针化到 playbook.md/orient/gen_gate。
- **命名律**：卡片文件名 = agent name = `<playbook-id>-compute`，无例外。
- **纪律继承**：提问上浮、停顿归主、结论归主、禁嵌套、单写者，全部照搬 v1 engine-core，不重写。
- **工具锁死**：任何卡片 `tools:` 不得含 `AskUserQuestion`。
- **编排脑预算**：`ts-diagnose-v2/SKILL.md` ≤60 行 / ≤6000 token 且禁方法词（复制来的 `test_layering` 守卫）。

## 18. 待定 / 后续

- 真实数据到位后，按 EVAL.md 跑首个 v1/v2 A/B。
- 移植到你自己的 Claude SDK 时的 flatten-on-export 脚本（把 playbook.md 内联进卡片）——本版不做。
- 若 compute-fine（subset-influence）在 A/B 中表现出与 compute 卡片不可比，考虑把它的重活脚本升成显式的 `-compute` 子卡——本版不做。
