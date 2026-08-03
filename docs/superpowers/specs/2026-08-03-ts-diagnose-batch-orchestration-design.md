# ts-diagnose 批量编排层设计（batch orchestration）

日期：2026-08-03
状态：设计已批准，待实现计划

## 1. 背景与目标

当前 ts-diagnose 是"单入口 + orient 单 playbook 求值器"。用户一次只能顺序跑一条
playbook。目标：让用户在**一份数据、多个诊断角度**的场景下，一次性并行跑多条
level-2 playbook（如 robustness + feature-importance + deployment-drift 同时诊断
一次模型运行），把 2×N 个分散的人机停顿点收敛成 **2 个合并停顿点**，并用独立的
subagent 窗口承载重活、保护主 agent 的 256k 上下文。

批量的形状（本设计只覆盖这一种）：**不同 playbook，同一份数据**。生产者
（data-setup）只跑一次、被所有 level-2 playbook 共享；提问在 playbook 之间去重。

## 2. 硬约束（决定整个架构的两条事实）

1. **subagent 无提问权**：`AskUserQuestion` 在 subagent 内被禁用，且没有把问题上抛回
   主 agent 的通道。引擎已有此纪律（`engine-core.md:69`）。**推论**：任何要问用户的
   动作都必须在主 agent，且必须在派发 subagent **之前**收齐。
2. **消息传递是单向返回 + 续跑**：subagent → 主 agent 只回一段最终文本（本引擎更进一
   步：subagent 写自己的 `--out` 文件，主 agent 读）；主 agent → subagent 只能新派或
   用 SendMessage 续跑同一 subagent（保留其上下文）。**这两条通道都不经过用户**。

并行能力充裕：默认 ~20 并发 subagent（200/会话），嵌套深度 ≤3，另有 Workflow 工具可
做脚本化 fan-out/fan-in。瓶颈不是吞吐，而是**交互点的摆放位置**。

## 3. 设计核心洞察

一条 level-2 playbook 不是单块自治单元，而是一个三明治：

```
上游提问        →   [ 计算 stage ]   →   pause_after 现象清单   →   结论
(交互·主 agent)     (自治·subagent)      (交互·主 agent)          (交互·主 agent)
```

`pause_after: true` 的事实提取 stage 正是"自治计算"与"需要人"之间的天然切缝。已核实
feature-importance、robustness 两条的事实提取 stage **本就是 `subagent_ok: true`**，
结论 stage 是 `subagent_ok: false`——切缝画在正确的位置。其余三条
（result-eval/deployment-drift/model-comparison）早期与事实提取 stage 未显式声明
`subagent_ok`，需按 §11 审计确认默认为 `true`（或显式补上），这是本设计唯一可能触发的
playbook 改动。

## 4. 分层架构（批量层纯增量）

```
Layer -1  batch.py            ← 新增：计划器 + 汇聚器（生产者并集 / 问题并集 / 派发 / fan-in）
Layer 0   orient.py           ← 不变：单 playbook 求值器（每个 subagent 与主 agent 仍各自调它）
Layer 1   playbooks/<id>/     ← 近乎不变：方法
```

**职责边界**：`batch.py` **计划并汇聚**；`orient.py` 仍在各自工作目录里**逐 playbook
求值**。两者不重叠、不重写。单 playbook 流程完全不变。

固定 DAG 的高度：**Layer -1（playbook 之间）钉死**——生产者并集 → N 条 playbook 并行
跑到事实提取 → 合并停顿 → 选中的结论，写进 `batch_plan.json`；**Layer 0（playbook 内
部 stage 顺序）不再手写固定 DAG**——orient 已是该 DAG 的确定性求值器，重写就是重复其
逻辑且两处易不同步。playbook 的 frontmatter 仍是其 stage 图的唯一真相源。

## 5. 文件布局

```
<batch_workdir>/
  batch_config.json      # 选中的 playbook + 共享答案 + 产物登记        （主 agent 写）
  batch_plan.json        # 生产者并集 / 问题并集 / 派发清单 / 各 pb 状态 （batch.py 写）
  BATCH_PROGRESS.md      # 批量级日志                                    （主 agent 写）
  _shared/setup/         # 共享 data-setup 产物——只生产一次
  <playbook>/            # 每条 playbook 自己的工作目录 + 自己的 diagnose_config.json
    phenomena_<pb>.json  # subagent 的 --out：现象清单（观察+数字+来源，禁机制语言）
  BATCH_REPORT.md        # 最终合并报告                                  （主 agent 写）
```

**单写者纪律保持不变**：subagent 只写自己的 `phenomena_<pb>.json` 与自身工作目录产物；
主 agent 独占所有批量级文件与全部 FINDINGS/CONCLUSION。

## 6. 五阶段协议（主 agent 驱动，batch.py 强制）

- **A — 生产者只跑一次**：`batch.py` 从选中 playbook 的 `upstream` 算出生产者并集
  （单数据集场景即 `setup`），只跑一次进 `_shared/setup/`，把它登记进每条 playbook 的
  `config.products`。
- **B — 一次合并提问**：`batch.py` 生成问题并集——`setup` 本就"拥有" schema/freq/对齐键
  （随生产者问一次）；恒问五类（口径/成功判据）去重成一问；再加每条 playbook 自己
  frontmatter 里声明的问题。`batch.py` 标出两条 playbook 想要同一 qid 但语义分歧的冲突。
  主 agent 问一次，把答案写进每个子 `diagnose_config.json`。
- **C — 并行计算 fan-out**：每条 playbook 一个 subagent（远低于 20 并发上限；每个还可
  再嵌自己 §5 的计算子-subagent，深度 ≤3）。brief 用 `Brief-BATCH-COMPUTE`（见 §7）。
  失败隔离天然成立：某 subagent 挂掉只在 `batch_plan.json` 把该 playbook 标 `failed`，
  其余继续。
- **D — 一次合并停顿**：主 agent 收齐所有 `phenomena_<pb>.json`，一并呈现，用户点名
  要深挖哪些（可跨 playbook 选）。这是 N 个分散 `pause_after` 停顿的唯一替代。
- **E — 结论**：对每个选中的深挖目标，主 agent 照今天的流程跑该 playbook 的结论
  stage——三道门 + `conclusion_gate.json` 收据，`结论永远由主 agent 落笔`。串行即可；
  结论是高裁决、低并行的部分。

## 7. Brief-BATCH-COMPUTE 完整字段（补充项 a）

批量派发的 subagent brief 模板，收进 `references/batch-orchestration.md`。每个字段
在 brief 里钉死，subagent 的作用域/停止点/输出契约无歧义：

| 字段 | 内容 | 说明 |
|---|---|---|
| `workdir` | `<batch_workdir>/<playbook>/`（绝对路径） | subagent 的工作目录，已含预填好的 `diagnose_config.json` |
| `playbook` | playbook id | 只跑这一条 |
| `shared_setup` | `<batch_workdir>/_shared/setup/`（绝对路径） | 已就绪的共享产物，已登记进 `config.products` |
| `entry` | `python3 <ENGINE>/scripts/orient.py`（在 workdir 内） | subagent 自己反复调 orient 被逐阶带走 |
| `run_range` | `stage 0 → 事实提取 stage（含）` | **停止点钉死**：跑到 `pause_after` 那个 stage 产出现象清单为止 |
| `stop_after` | 事实提取 stage 完成、`phenomena_<pb>.json` 写盘 | **不得进入结论 stage**（结论 `subagent_ok:false`，且属主 agent） |
| `out` | `phenomena_<pb>.json`（现象清单：观察+数字+来源，禁机制语言） | `--out` 命名钉死，防并发写冲突 |
| `return` | ≤30 行数字摘要 + `phenomena_<pb>.json` 路径 | 回主 agent 的唯一内容；不贴 CSV/parquet/大日志 |
| `gates` | golden 覆盖的 stage 必过 `gen_gate.py`；整形脚本必过对账两关 | 与单跑同规矩，不放松 |
| `nesting` | 重 stage（按模型分片、批量 API…）可嵌 §5 子-subagent，深度 ≤3 | 单窗口扛不住时的逃生门 |
| `forbid` | 改任何共享状态文件（`batch_*`、别的 playbook 的产物、FINDINGS/CONCLUSION）；提问用户；进结论 stage；跨越 `stop_after` | **禁止项钉死** |
| `on_fail` | 出错即返回错误摘要，不重试破坏性操作 | 主 agent 据此标 `failed` 并向用户报告，供单条重派 |

## 8. 上下文预算（补充项 b）

- **主 agent 全程只吃 json 摘要**：批量计划、提问 Q&A、N 份 ≤30 行摘要 + 现象清单
  json 路径；合并停顿时读 `phenomena_<pb>.json`（自足）；结论时读该 playbook 工作目录的
  自足 json。**从不摄入原始数据（PNG/大日志/parquet）**，因此稳在 256k 内。
- **每个计算 subagent 各吃各的 256k**：重活（解析大日志、parquet、permutation 重跑、
  反事实 API）全在 subagent 自己窗口发生，产物落盘，只把 ≤30 行摘要回传主 agent。
  N 条 playbook 并行 = N 份独立 256k 分担重活。
- **不靠记忆**：subagent 每步先跑 orient，从磁盘重算"下一步"，上下文即便变长/被压缩，
  `落盘 → orient → 下一步` 循环可随时重建状态。主 agent 同理，断点续跑。
- **重 stage 再嵌 §5**：单条 playbook 若仍逼近 256k，其重 stage 下钻子-subagent
  （各自新 256k），把明细挡在下层，只上浮摘要。
- **golden 不进上下文**：golden 是磁盘上的验证闸（`gen_gate.py` 调用），不是 subagent
  要"记住"的任务；运行期只作为一条命令的输入存在。

## 9. 问题并集机制（Phase B 细节）

问题并集 = `setup` 的问题（随生产者问一次，其他 playbook 按 `_playbook-spec.md`
不得重复声明上游拥有的问题）+ 恒问五类去重成一问 + ∪(各 playbook frontmatter 的
`questions`)。`batch.py` 检测 qid 冲突：两条 playbook 引用同一 qid 但 `options`/语义
分歧时，在 `batch_plan.json` 标 `question_conflicts[]`，由主 agent 在合并提问里显式
呈现给用户裁决，不静默取其一。

## 10. 机器契约 schema（草案）

`batch_plan.json`（batch.py 写，主 agent 只读）：

```json
{
  "playbooks": ["robustness", "feature-importance", "deployment-drift"],
  "producer_union": ["setup"],
  "question_union": [{"qid": "口径", "ask": "...", "options": ["..."], "owners": ["robustness", "..."]}],
  "question_conflicts": [],
  "dispatch": [{"playbook": "robustness", "workdir": "./robustness", "out": "phenomena_robustness.json", "status": "pending"}],
  "phase": "A|B|C|D|E"
}
```

`batch_config.json`（主 agent 写）：选中的 playbook 列表、合并提问的答案、
`products` 登记（指向 `_shared/setup`）。`status` 取值：`pending / running / done /
failed`。

## 11. 新增 / 改动 / 审计 清单

- **新增** `scripts/batch.py`——计划器 + 汇聚器（复用 `engine_common` 的 frontmatter
  加载；产出 `batch_plan.json`）。
- **新增** `references/batch-orchestration.md`——主 agent 协议（五阶段 A–E、fan-in 规则、
  失败/续跑、合并停顿的汇报格式、`Brief-BATCH-COMPUTE` 模板、上下文预算说明）。
- **改动** `SKILL.md`——2–3 行路由："同时/批量跑多个 playbook（一份数据、多角度）" →
  batch 模式。**必须保持 ≤60 行 / ~6K token**（`test_layering.py` 守卫）。
- **审计** `result-eval` / `deployment-drift` / `model-comparison` 的早期 stage 未声明
  `subagent_ok`——确认默认为 `true`（或显式设 `true`），使其计算可外包。
- **新增测试** `scripts/tests/test_batch.py`——golden：给定一组 playbook id，断言
  生产者并集、问题并集（含去重）、派发清单三者正确。

## 12. 明确不变的部分

orient 的单 playbook 流程、每条 playbook 的菜单、三道门、crystallize、chartbook 路径。
批量是可选、增量的。单跑一条 playbook 与今天完全一致。

## 13. 风险与未决

- **审计结果可能触发小改**：若 result-eval/deployment-drift/model-comparison 早期
  stage 的 `subagent_ok` 默认不是 `true`，需逐条显式设 `true` 并跑 pytest。
- **结论阶段的主 agent 上下文累积**：Phase E 串行跑 N 个结论，每个读自足 json、写
  CONCLUSION.md，单个都轻；若逼近预算，可把结论的**计算**部分下钻 subagent，但
  **裁决与落笔仍在主 agent**（`结论永远由主 agent 落笔`）。
- **本设计不覆盖**："同一 playbook × 多输入"（如 result-eval 跑 17 站）与"通用
  M×N DAG"两种形状——留作后续轮次，接口预留在 `batch.py` 的 producer/question 并集
  逻辑里（按输入维度扩展）。
- **Workflow 工具**作为 Phase C fan-out 的可选实现（确定性并发 + 干净 fan-in）留作
  内部优化项，需用户显式 opt-in，不作骨干。
```
