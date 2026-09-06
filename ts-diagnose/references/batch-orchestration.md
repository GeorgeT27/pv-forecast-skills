# 批量编排协议（batch-orchestration）——主 agent 照此驱动

前置：用户要在同一份数据上一次诊断多条 level-2 playbook。第一次先跑
`python3 <ENGINE>/scripts/batch.py --select <id1,id2,...> --workdir <批量工作目录>`
初始化；之后每回合跑 `python3 <ENGINE>/scripts/batch.py --workdir <批量工作目录>`（不带
--select 刷新），照它报的 phase 与下一步办。状态以落盘产物为准，随时断点续跑。

## Phase A — 生产者只跑一次
`producer_union` 只并入选中 playbook 里 **required: true** 的 upstream 产物——只有这些
才门 Phase A，只跑一次进 `<批量工作目录>/_shared/<产物id>/`。batch.py 报 phase=A 时：
按 `producer_union` 逐个内联跑生产方 playbook。收齐其问题答案后按名字派 producer 卡整体
外包：data-setup → `data-setup-compute`、metric-eval → `metric-eval-compute`、
model-audit → `model-audit-compute`；没有 producer 卡的生产方按各自 §5 拆分外包，不整体
外包。产物就绪后**两处登记**：写 `batch_config.json` 的 `products.<id> = {workdir, status: built}`（供 batch.py 判 phase），
**并**把该 products 条目拷进每条消费它的 playbook 子目录 `<pb>/diagnose_config.json` 的
`products`（compute subagent 跑 orient 时只读本地 diagnose_config.json，不读
batch_config.json——不拷则它看不到上游）。重跑 batch.py。

**required: false 的可选上游**（model_profile、chart_sweep……）不进 `producer_union`，
不门 Phase A——不然一个用户压根不打算建的可选产物会永久卡住整批。可选上游改由**主
agent**在 Phase A 期间逐 playbook 走 engine-core 的「上游产物三分支」裁决（现在内联生产 /
链接已有目录 / 放弃且结论须声明缺此产物）：三分支要 AskUserQuestion 问用户，Phase C 派
的 compute 子代理不能自己问用户，所以这活留在主 agent 手上，且必须在该 playbook 进
Phase C 派发之前做完。裁决结果写进该 playbook 子目录 `<pb>/diagnose_config.json` 的
`products`（build/link 时登记 workdir+status；decline 时登记 status: declined），不登记进
`batch_config.json`（那是 required 产物专用的批量级登记）。

## Phase B — 一次合并提问
phase=B 时：把 `question_union` 一次性问用户（同一阶段多题合并成一次 AskUserQuestion，
每题带 options）。`question_conflicts` 里的 qid 必须显式呈现两种语义请用户裁决，不静默取一。
答案写 `batch_config.json` 的 `answers`，并拷进每条 playbook 子目录的 `diagnose_config.json`
（用户答过的不重复问）。重跑 batch.py。

## Phase C — 并行计算 fan-out
phase=C 时：为每条 status=pending 的 playbook 派一个子代理——每个 worker = 该 playbook 的
具名卡片 `<id>-compute`（索引见 `subagent-briefs.md`），「输入」节由主 agent 填 `_shared/`
产物目录与合并后的答案；名字不可用走回退（卡片全文作 prompt 派 `general-purpose`）。
派发前 `batch.py --mark <pb>:running`；子代理返回后不写 status（磁盘出现 phenomena 即自动判
compute-done）；子代理报错则 `batch.py --mark <pb>:failed` 并向用户报告，供单条重派。某条 playbook 计算重到单窗口扛不住时，**主 agent**把它的 §5
子任务作为额外的扁平 Phase-C 兄弟子代理派发（主 agent 是唯一派发者，不让 compute 子代理
自己再派）。收齐后重跑 batch.py。

## Phase D — 一次合并停顿
phase=D ⟺ 全部派发 status 都已到 compute-done 或更后（没有 pending/running/failed）**且**
`BATCH_REPORT.md` 尚未写。phase=D 时：读齐所有 `<pb>/phenomena_<pb>.json`（自足 json，不读
大文件），一并呈现现象清单，请用户点名要深挖哪些（可跨 playbook）。选了哪些、按什么判据，
记 BATCH_PROGRESS.md。**没被点名深挖的、或本来就没有结论阶段的 playbook（如
fact-scan）停在 compute-done 是正常状态，不是阻塞**——不必等它们变成 done 才能往下走。

## Phase E — 结论
对每个选中的深挖目标，在其 `<pb>/` 子目录跑 orient 进结论阶段：三道门 +
`conclusion_gate.json` receipt，结论永远由主 agent 落笔。选中的深挖目标全部出结论后写
BATCH_REPORT.md（合并各 CONCLUSION.md 要点 + 覆盖缺口声明，含未深挖 playbook 的说明）
直接呈现用户。**phase=E ⟺ `BATCH_REPORT.md` 已存在**——写这份报告是唯一让批量进入 E 的
动作；写之前哪怕所有选中目标都已 done，phase 仍报 D，提醒主 agent 该收尾了。

## 上下文预算
主 agent 全程只吃 json 摘要（批量计划、提问答案、各 ≤30 行摘要、现象清单 json），
从不摄入原始数据，稳在 256k。每个计算子代理各吃各的 256k，重活落盘只回摘要。单条 playbook
若逼近 256k，compute 子代理不自己嵌套；返回后主 agent 把其 §5 子任务拆成扁平 Phase-C
兄弟子代理重派。不靠记忆——每步先跑 batch.py / orient 从磁盘重建状态。golden 是磁盘上的
验证闸，不进上下文。
