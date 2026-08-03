# 批量编排协议（batch-orchestration）——主 agent 照此驱动

前置：用户要在同一份数据上一次诊断多条 level-2 playbook。第一次先跑
`python3 <ENGINE>/scripts/batch.py --select <id1,id2,...> --workdir <批量工作目录>`
初始化；之后每回合跑 `python3 <ENGINE>/scripts/batch.py --workdir <批量工作目录>`（不带
--select 刷新），照它报的 phase 与下一步办。状态以落盘产物为准，随时断点续跑。

## Phase A — 生产者只跑一次
batch.py 报 phase=A 时：按 `producer_union` 逐个在 `<批量工作目录>/_shared/<产物id>/`
内联跑生产方 playbook。收齐其问题答案后按 engine-core 分层原则外包：满足三条件的
（data-setup / metric-eval）按 `Brief-PRODUCER` 整体外包；model-audit / fact-scan 保留主
agent 裁决，按各自 §5 拆分外包，不整体外包。产物就绪后**两处登记**：写 `batch_config.json`
的 `products.<id> = {workdir, status: built}`（供 batch.py 判 phase），**并**把该 products
条目拷进每条消费它的 playbook 子目录 `<pb>/diagnose_config.json` 的 `products`（compute
subagent 跑 orient 时只读本地 diagnose_config.json，不读 batch_config.json——不拷则它看不到
上游）。重跑 batch.py。

## Phase B — 一次合并提问
phase=B 时：把 `question_union` 一次性问用户（同一阶段多题合并成一次 AskUserQuestion，
每题带 options）。`question_conflicts` 里的 qid 必须显式呈现两种语义请用户裁决，不静默取一。
答案写 `batch_config.json` 的 `answers`，并拷进每条 playbook 子目录的 `diagnose_config.json`
（用户答过的不重复问）。重跑 batch.py。

## Phase C — 并行计算 fan-out
phase=C 时：为每条 status=pending 的 playbook 派一个子代理，brief 用下方
Brief-BATCH-COMPUTE。派发前 `batch.py --mark <pb>:running`；子代理返回后不写 status
（磁盘出现 phenomena 即自动判 compute-done）；子代理报错则 `batch.py --mark <pb>:failed`
并向用户报告，供单条重派。某条 playbook 计算重到单窗口扛不住时，**主 agent**把它的 §5
子任务作为额外的扁平 Phase-C 兄弟子代理派发（主 agent 是唯一派发者，不让 compute 子代理
自己再派）。收齐后重跑 batch.py。

## Phase D — 一次合并停顿
phase=D 时：读齐所有 `<pb>/phenomena_<pb>.json`（自足 json，不读大文件），一并呈现现象
清单，请用户点名要深挖哪些（可跨 playbook）。选了哪些、按什么判据，记 BATCH_PROGRESS.md。

## Phase E — 结论
对每个选中的深挖目标，在其 `<pb>/` 子目录跑 orient 进结论阶段：三道门 +
`conclusion_gate.json` receipt，结论永远由主 agent 落笔。全部完成后写 BATCH_REPORT.md
（合并各 CONCLUSION.md 要点 + 覆盖缺口声明）直接呈现用户。

## Brief-BATCH-COMPUTE
> 工作目录：`<批量工作目录>/<playbook>/`（已含预填的 diagnose_config.json，products 已登记）。
> 共享产物：`<批量工作目录>/_shared/<产物id>/`（本 playbook upstream 的各产物，如 setup、
>   model_profile、chart_sweep——已就绪，已登记进本地 diagnose_config.json 的 products）。
> 入口：在工作目录内跑 `python3 <ENGINE>/scripts/orient.py`，被它逐阶带走。
> 跑：stage 0 → 事实提取 stage（含），产出 `phenomena_<playbook>.json`（观察+数字+来源，
>   禁机制语言）。
> 停：事实提取 stage 完成、phenomena 写盘即止——不得进结论 stage。
> 回：≤30 行数字摘要 + phenomena 文件路径；不贴 CSV/parquet/大日志。
> 闸：golden 覆盖的 stage 必过 gen_gate.py；整形脚本必过对账两关。
> 禁：再派子代理（引擎硬规则 subagent 不能再派 subagent——扛不住就返回，主 agent 拆扁平
>   兄弟重派）；改任何共享状态文件（batch_*、别的 playbook 产物、FINDINGS/CONCLUSION）；
>   提问用户；进结论 stage；跨越停止点。出错即返回错误摘要，不重试破坏性操作。

## 上下文预算
主 agent 全程只吃 json 摘要（批量计划、提问答案、各 ≤30 行摘要、现象清单 json），
从不摄入原始数据，稳在 256k。每个计算子代理各吃各的 256k，重活落盘只回摘要。单条 playbook
若逼近 256k，compute 子代理不自己嵌套；返回后主 agent 把其 §5 子任务拆成扁平 Phase-C
兄弟子代理重派。不靠记忆——每步先跑 batch.py / orient 从磁盘重建状态。golden 是磁盘上的
验证闸，不进上下文。
