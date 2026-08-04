# 派发协议（dispatch-protocol）——SKILL.md「派发增量段」的详细承接

<!-- 分层说明：SKILL.md（Layer 0）只留一句话指针到本文件；本文件承载「怎么选卡、
     怎么派、怎么处理中途卡壳、批量下怎么复用」的全部细节。执行纪律本身（提问上浮/
     停顿归主/结论归主/禁嵌套/单写者/三道闸）不在本文件重复，见 engine-core.md；
     批量 Phase A–E 的完整机制不在本文件重复，见 batch-orchestration.md。 -->

命中 playbook 之后，本文件回答「派谁、怎么派、卡壳了怎么办」；「问什么、何时停、
谁下结论」仍按 engine-core.md 的通用纪律与各 playbook 正文执行，与 v1 一字不差。

## 1. 选卡

- **单 playbook 命中**：主 agent 按 SKILL.md 路由表命中 playbook `X` 后，派发
  `agents/X-compute.md`——派发 key = 文件名去 `.md` = `X-compute`，与路由结果一一
  对应，确定性名字匹配，不需要语义判断。
- **批量模式**：先跑 `scripts/batch.py`（见第 3 节）得到 Phase C 的
  dispatch 列表（status=pending 的 playbook id 集合），逐条按同一条命名律映射到
  `<id>-compute` 卡片名——批量与单 playbook 用的是同一张映射表，没有第二套命名。
- **`description` 字段**：卡片 frontmatter 里的 `description`（一句话覆盖范围）
  只在目标模糊、SKILL.md 路由表 11 行都不像时，供主 agent 浏览 11 张卡片辅助判断
  该选哪个 playbook；一旦 playbook id 已经确定（无论是路由表命中还是用户直接点名），
  派发永远走第一条的确定性命名匹配，不依赖 `description` 做实际派发决策。

## 2. 单 playbook 三明治（六步）

对着 `agents/_agent-spec.md` 的三种 mode，六步框架对 `compute`（7 张）与
`producer`（3 张，②③步坍缩，见下方「producer 目标的变体」）都适用；`compute-fine`
（subset-influence 一张）不走这个三明治，见第 4 节末尾单列。

1. **上浮问题**：读该 playbook frontmatter 的 `questions:` 块，取 `stage` ≤ 该
   playbook 的 pause 阶段（`compute` 卡片的 `compute_stages` 终点）的题——即卡片
   索引表「主 agent 派发前须答的问题」列出的那些 question id。**只取
   `questions:` 块，不取 `evidence_lines`（后者是产物证据行，不是要问用户的
   问题）。** 同一阶段的题合并成一次 AskUserQuestion（各带 playbook 声明的
   `options`），答案落 `diagnose_config.json`。
2. **确保必需上游产物就绪**：按该 playbook `upstream[]` 声明检查
   `required: true` 的产物是否已 built/linked。缺失时按 engine-core.md「上游产物
   三分支」处理——`required: true` 的产物主 agent 不问用户、立即内联生产：如果
   该产物由某张 **producer** 卡片生产（`setup`→`data-setup-compute`，
   `model_profile`→`model-audit-compute`，`metric_table`→`metric-eval-compute`），
   先答齐该 producer 卡片自己的上浮问题（第 1 步同法），整体派发该 producer 卡片
   跑到产物落盘，回填 `config.products.<id>`；`required: false` 的可选产物三分支
   裁决（现在内联生产 / 链接已有目录 / 放弃且结论声明缺此产物）**必须 AskUserQuestion
   问用户**，compute 卡片不能替用户拍板，这一步留在主 agent 手上，且必须在③之前
   做完。
3. **派 `X-compute`**：把①②收集到的「已答问题」「已就绪的上游产物目录」填进卡片
   「输入」节对应字段，派发，等待其 final message——即 §11 输出契约那份 JSON。
4. **处理 NEED_INFO / BLOCKED**：见第 4 节回环；`BLOCKED`（材料缺失、脚本报错、
   对账不过等）由主 agent 排查修复材料或改脚本后，同样重派同一张卡片，不换卡。
5. **停顿**：卡片回 `COMPUTE_DONE` 后，主 agent 读 `phenomena_file`/`artifacts`
   （只读 json 摘要，不读原始产物明细），向用户展示现象清单，请用户点名要深挖哪些
   （可跨图/跨切片，模糊授权时按 engine-core.md 的判据自动选）。
6. **主 agent 亲跑变体 + 结论 + 闸**：用户点名后，若该卡片声明了
   `on_demand_stages`（目前仅 `feature-importance-compute` 的 `5-6`），按需
   **再派同一张卡片**跑这些阶段——仍是 compute 语义，只到证据合流前止步，不下
   结论；随后进入结论阶段（`subagent_ok:false`，卡片天然不覆盖），由主 agent
   亲自跑三道门（稳健性/假设登记/反驳门）+ `conclusion_gate.py`，写
   `CONCLUSION.md` 并直接呈现给用户，不外包这一步。

**result-eval 的 Stage 4 特例**：`result-eval-compute` 只覆盖 Stage 0–3，
frontmatter **不声明 `produces`**——`eval_report` 的 manifest
（`gate_reports/conclusion_gate.json`）与 marker（`CONCLUSION.md`）只在 Stage 4
（结论阶段，`subagent_ok:false`）落盘，落在卡片计算区间之外。这意味着：当
某个批量目标或某条 playbook 的 `upstream[]` 把 `eval_report` 列为可选上游产物、
用户选择「现在内联生产」时，光把 `result-eval-compute` 派完拿到 `COMPUTE_DONE`
**不构成 `eval_report` 产物就绪**；主 agent 必须在该 result-eval 子目录里接着
自己走完第 6 步（用户点名/默认深挖 → 三道门 → `conclusion_gate.py` →
`CONCLUSION.md`），产物 manifest 落盘后才能把 `config.products.eval_report`
标记 `built`。

**producer 目标的变体**：当命中的 playbook 本身就是 producer
（data-setup/model-audit/metric-eval），②③坍缩——不存在「先派 producer 保上游
就绪」这一层递归（producer 没有自己的必需上游要另外派卡），直接①问齐问题→③整体
派发→卡片跑到产物落盘即返回 `COMPUTE_DONE, produces_dir: <path>`，任务结束。
producer 的 playbook 没有 `pause_after`、没有结论阶段，因此④⑤⑥（现象停顿、用户
点名、变体、结论三道门）全部不适用——`produces_dir` 落盘即整条任务完成。

## 3. 批量 A–E 复用

批量模式完全复用 v1 `scripts/batch.py` 与 `references/batch-orchestration.md`
（Phase A 生产者只跑一次、Phase B 一次合并提问、Phase C 并行计算 fan-out、
Phase D 一次合并停顿、Phase E 结论），**逐字不改**。唯一差异在 Phase C：v1 每个
fan-out worker 是主 agent 现场拼的 Brief-BATCH-COMPUTE 注入；v2 每个 worker
换成第 1 节「选卡」映射出的**具名卡片**，其余（`batch.py --mark`、收齐后重跑
`batch.py`、`_shared/` 产物目录、`diagnose_config.json` 回填）不变。

**禁嵌套**：某条 playbook 计算量单窗口扛不住时，主 agent（唯一派发者）把它的
子任务拆成**平级**的 Phase-C 兄弟卡片重派，不允许卡片自己再往下派 subagent——
与批量协议原有的禁嵌套规则完全一致，只是「拆分出的子任务」现在也是具名卡片而不是
临时 Brief。

## 4. NEED_INFO 回环

worker 不猜——中途撞到未答的 prereq（不在派发时「已答问题」清单里、卡片执行中才
发现缺的信息）时，返回 `status: NEED_INFO` + `need_info: [{question_id, ask,
why}, …]`，不推进、不假设。主 agent 收到后：把 `need_info` 里的题按第 2 节第①步
同法问用户（AskUserQuestion，合并同阶段的题），答案落 `diagnose_config.json`，
然后**重派同一张卡片**，「输入」节的「已答问题」补上新答案。卡片对同一批已完成的
子步骤没有记忆负担——它下次进来先跑 `orient.py` 从磁盘状态续接，不会重做已落盘的
部分。

`compute-fine`（`subset-influence-compute`）不走本节以外的三明治框架：它没有
整段停顿交回，主 agent 逐阶段指派**一个**具名重活脚本（`probe_logs.py` /
`replay_assignments.py` / `loss_dynamics.py` / `ckpt_eval.py` /
`influence_regression.py` / `tracin_influence.py` / `run_drift.py`
之一），卡片跑完这一个脚本即回数字摘要，等下一次指派；NEED_INFO 回环同样适用
（缺参数/材料就返回 `need_info`，主 agent 问完用户后带着答案重派同一个脚本任务，
不换成派另一个脚本顶替）。Stage 5（微调探针 + 剔除重训确认）`subagent_ok:false`，
主 agent 永不外包这一阶段。
