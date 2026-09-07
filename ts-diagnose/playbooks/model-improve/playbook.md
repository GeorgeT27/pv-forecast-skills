---
id: model-improve
name: 改进环（按轮批跑）
goal: 把假设账本里的改进假设（或素版的可干预开关）排成候选，按轮批跑 ≥3 种子重训，与冠军比较后留弃，停止规则由代码守，收敛后封存测试集只评一次，结论过闸产一次
produces_experiment_log: true
upstream:
  - product: model_profile
    required: false
stages:
  - id: 0
    name: 冻结评估器与冠军基线
    done_when:
      artifacts: ["evaluator.json", "champion.json"]
    prereqs:
      - desc: 评估器适配器已定
        check: "question:evaluator-adapter"
      - desc: 改进目标与起点配置已定
        check: "question:improve-target"
      - desc: 预算已定
        check: "question:improve-budget"
      - desc: 守护切片已定
        check: "question:guard-slices"
    pause_after: true
    subagent_ok: true
  - id: 1
    name: 候选队列
    done_when:
      artifacts: ["rounds/round_{round}/candidates.json"]
    prereqs:
      - desc: 冠军基线已定
        check: "stage:0"
      - desc: 候选来源已定
        check: "question:candidate-source"
  - id: 2
    name: 跑一轮
    done_when:
      artifacts: ["rounds/round_{round}/batch_result.json"]
    prereqs:
      - desc: 本轮候选已排
        check: "stage:1"
      - desc: 用户已确认本轮训练次数（candidates.json.confirmed）
        check: "json:rounds/round_{round}/candidates.json:confirmed"
    subagent_ok: true
  - id: 3
    name: 轮次裁决
    done_when:
      artifacts: ["rounds/round_{round}/summary.json"]
    prereqs:
      - desc: 本轮批结果已落盘
        check: "stage:2"
    pause_after: true
  - id: 4
    name: 结论落笔
    done_when:
      artifacts: ["final_test.json", "CONCLUSION.md", "gate_reports/conclusion_gate.json"]
    prereqs:
      - desc: 已收敛（预算耗尽 / 轮数封顶 / 连续无 keep / 用户 stop）
        check: "json:champion.json:converged"
materials:
  required: []
  optional: [model_code, experiment_config, checkpoint]
questions:
  - id: evaluator-adapter
    stage: 0
    ask: "训练入口适配器脚本的绝对路径？（须实现 references/evaluator-contract.md：--config/--seed/--out，产 metrics.json 与 sealed/test_metrics.json）"
    why: "没有一条命令的评估器就没有环"
    default: null
  - id: improve-target
    stage: 0
    ask: "改进哪个模型？起点配置 base_config 是什么？基线 3 种子用已有产物还是新跑？"
    why: "冠军 E000 与噪声底由它定；候选只接 fix.target_model 相同的条目"
    default: null
  - id: improve-budget
    stage: 0
    ask: "预算：最多几次训练、最多几轮、每轮最多几条候选？"
    why: "停止规则由 experiment_log.py 按这三个数守"
    default: "30 次 / 3 轮 / 每轮 10 条"
  - id: guard-slices
    stage: 0
    ask: "守护切片：哪些切片不许退化？（从 evaluator.json.slices 里选）"
    why: "整体变好但某切片变坏的候选必须弃"
    default: "全部 horizon:* 切片"
  - id: candidate-source
    stage: 1
    ask: "候选来源：假设账本路径（取 kind=improvement 的条目），还是素版（model_profile 的 ablation_switches）？"
    why: "有诊断的候选优先；素版只在没有账本时用"
    default: null
---

# model-improve：改进环（按轮批跑）

## 1. 问题框定与首要陷阱

本 playbook 回答「改了会不会好」，不回答「为什么」。「为什么」归消融验证主脊回答，本 playbook 只把该验证流程产出的假设账本里 `kind: improvement` 的条目拿来试。

首要陷阱：**单次运行就留下改法**。keep 只认三种子均值超冠军且超噪声底 3σ，再加守护切片无退化；一次运行的好成绩不是证据。

第二陷阱：**反复对同一份验证集选择会过拟合**。环内只看验证集指标；测试集在适配器里封存，`experiment_log.py finalize` 在收敛后只开封一次，结论必须报它。

第三陷阱：**崩溃当成推翻**。种子 crash/timeout 的候选记 `untested`，账本状态 `untested` 带原因，不进 refuted。

第四陷阱：**绕过预算再来一轮**。轮数、训练次数、连续无 keep 三条停止规则由 `experiment_log.py decide` 判，收敛后 `new-round` 会拒绝；要多跑只能重新 init 一个新的工作目录并在结论里说明。

## 2. 逐阶段菜谱

引擎目录 `<ENGINE>`；三支脚本：`<ENGINE>/scripts/evaluator.py`、`<ENGINE>/scripts/improve_verdict.py`、`<ENGINE>/scripts/experiment_log.py`。评估器契约见 `<ENGINE>/references/evaluator-contract.md`。

### Stage 0 冻结评估器与冠军基线

输入：四个问题的答案；可选 `model_profile` 的 `ablation_switches`。

菜谱：
1. 按答案写 `evaluator.json`（adapter / base_config / knobs / metric / slices / seeds / time_limit_s），然后跑 `python3 "<ENGINE>/scripts/evaluator.py" validate evaluator.json`，不过不往下。
2. 基线 3 种子：派 `model-improve-worker`（task=baseline，输入：工作目录、引擎目录、`evaluator.json` 路径、`exp_id=E000`）。它跑 `evaluator.py run-seeds --config-diff '{}' --out-root runs/E000`，回 `runs/E000/summary.json` 路径。用户答「用已有产物」时，主 agent 按契约把已有 3 种子产物整理成同结构的 `runs/E000/summary.json`（per_seed / slices_per_seed / metrics_dirs / run_status，metrics_dirs 里必须有 `sealed/test_metrics.json`）。
3. `python3 "<ENGINE>/scripts/experiment_log.py" init --evaluator evaluator.json --baseline runs/E000/summary.json --max-trainings <N> --max-rounds <R> --max-per-round <K>`。

done：`evaluator.json` + `champion.json` 落盘 → **pause_after 停顿**（§4）。

### Stage 1 候选队列

输入：`candidate-source` 的答案。

菜谱：
1. 账本来源：`python3 "<ENGINE>/scripts/experiment_log.py" candidates --ledger <账本路径> --target <improve-target 的模型名>`。只取 `kind=improvement`、`status=pending`、`fix.target_model` 相同的条目，按其 `derived_from` 父假设的 `discriminating_power` 降序。
2. 素版来源：把 `model_profile` 的 `ablation_switches` 存成 JSON，跑 `candidates --switches <该 JSON> --target <模型名> --guard <守护切片,逗号分隔>`。`config-flag` 先于 `code-stub`，`not-intervenable` 不进队。
3. 两种来源可以同时给。已跑过的 `config_diff` 自动去重；超出每轮上限或剩余预算的候选进 `deferred`。
4. 向用户汇报本轮候选清单与训练次数（候选数 × 种子数），用户说开跑后执行 `experiment_log.py confirm-round`。候选为空时不确认，改走 `stop --reason no_candidates`。

第 2 轮起的候选：先看上一轮 `summary.json` 的 `deferred`；需要新假设时回生成器 playbook 重跑（配对写「新冠军 vs 旧冠军」，新条目 `provenance: post-hoc`）。

done：`rounds/round_{round}/candidates.json` 落盘（confirmed 由用户确认后置 true）。

### Stage 2 跑一轮

输入：`rounds/round_{round}/candidates.json`（confirmed=true）。

菜谱：
1. 每条候选一个 worker 任务（task=candidate，输入：工作目录、引擎目录、exp_id、hypothesis_id、config_diff、guard_slices）。Claude Code 下调用 Workflow 工具：`scriptPath="<ENGINE>/workflows/ts-train-batch.js"`，`args={"engine": "<ENGINE>", "workdir": "<工作目录>", "agent_type": "model-improve-worker", "task": "candidate", "candidates": <candidates.json 的 candidates 数组>, "chunk": 4}`；本 playbook 写明的这条调用即 Workflow 的用户授权。Workflow 不可用时，主 agent 在一条消息里并行派多张 `model-improve-worker` 卡（每张一条候选）。
2. 把返回的 `{results, failed}` 原样写成 `rounds/round_{round}/batch_result.json`。
3. `python3 "<ENGINE>/scripts/experiment_log.py" append --batch rounds/round_{round}/batch_result.json`。append 拒收：未确认的轮、不在本轮候选里的 exp_id、重复 exp_id、结果里任何含 `test`/`sealed` 的键名。
4. 每条候选的判定写回账本：keep → 该 F 条目 `status: confirmed`、`receipt: receipts/E<id>.json`；discard → `status: refuted`、`kill_receipt` 同路径；undecided → `undecided`；crash/timeout → `untested` + `untested_reason`。改完跑 `python3 "<ENGINE>/scripts/hypothesis_ledger.py" <账本>`。

done：`rounds/round_{round}/batch_result.json` 落盘且 append 成功。

### Stage 3 轮次裁决

菜谱：`python3 "<ENGINE>/scripts/experiment_log.py" decide`。它在本轮 keep 里取均值最小者为新冠军、累加已用训练次数、判收敛，写 `rounds/round_{round}/summary.json`。

done：`summary.json` 落盘 → **pause_after 停顿**（§4）。用户选择：
- 再来一轮 → `python3 "<ENGINE>/scripts/experiment_log.py" new-round`，然后回 Stage 1（orient 会自动指向第 N+1 轮的候选阶段）。
- 到此为止 → `python3 "<ENGINE>/scripts/experiment_log.py" stop --reason "<用户原话>"`，进 Stage 4。
- decide 已报收敛 → 直接进 Stage 4，`new-round` 会拒绝。

### Stage 4 结论落笔

菜谱：
1. `python3 "<ENGINE>/scripts/experiment_log.py" finalize`——读基线与冠军各种子的 `sealed/test_metrics.json`，写 `final_test.json`。只跑一次。
2. `python3 "<ENGINE>/scripts/provenance.py" --code <适配器路径> --data evaluator.json experiment_log.jsonl --out provenance.json`。
3. 按 §6 模板写 CONCLUSION.md，然后 `python3 "<ENGINE>/scripts/conclusion_gate.py"`。规则 7 检查：「## 改进证据」节含 receipt 行、每张 `receipts/E*.json` 溯源块与适配器 sha 相符、`final_test.json` 存在且被引用、证据清单列全 E receipt / 日志 / 冠军 / 终评。

done：`final_test.json` + `CONCLUSION.md` + `gate_reports/conclusion_gate.json`。

## 3. 证据升级规则

- 候选 → keep：三种子均值低于冠军且 |delta| ≥ 冠军噪声底 3σ，且每个守护切片的 delta 不满足「>0 且 ≥ 该切片噪声底」（门 1 稳健性）。
- keep → 冠军：本轮 keep 里均值最小者（门 2 假设登记先于看数：候选在 confirm-round 前已登记，config_diff 不许事后改）。
- 冠军 → 「改进成立」：`final_test.json.verdict == improved`（封存测试集上超基线且超测试集噪声底）。verdict 为 not_distinguishable 时结论只许写「验证集上改进、测试集上不可分」（门 3 反驳门）。
- 素版候选（无假设）留下的冠军，结论只许写「配置级改进」，不写机制。

## 4. 停顿点与汇报

Stage 0 完成：报基线均值、三种子 std、噪声底 3σ、切片均值与切片噪声底、预算三个数、守护切片；请用户确认候选来源。

Stage 3 完成：报 `summary.json` 的 counts、每条 receipt 行、守护退化名单、untested 名单与原因、冠军是否更换与 delta、已用/总预算、是否收敛与原因、deferred 数量；请用户选「再来一轮 / 到此为止」。收敛时只报结果，不问。

## 5. subagent 拆分建议

Stage 0 基线与 Stage 2 每条候选都派 `model-improve-worker`（mode worker），一次一条任务，输出目录 `runs/<exp_id>/`，receipt `receipts/<exp_id>.json`，天然防竞态。Stage 1/3/4 归主 agent，不拆。Claude Code 下 Stage 2 用 `<ENGINE>/workflows/ts-train-batch.js` 批量派卡。

## 6. 结论模板与本 playbook 特有的反驳门条目

```
# 结论
一句话：冠军 <exp_id>（<config_diff_vs_baseline>）验证集 <metric> 从 <基线均值> 到 <冠军均值>；封存测试集终评 <verdict>（见 final_test.json）。
## 模型结构依据
<有账本：引用 F 条目的 derived_from H-id；素版：absent-confirmed，降级为配置级改进结论>
## 改进证据
<summary.json 里每条 receipt_line 原样贴，含被弃的；末尾贴 final_test.json 的 line>
## 反驳排除
- 单次运行误判：每条候选 ≥3 种子，噪声底 3σ 见 champion.json
- 验证集过拟合：测试集封存，final_test.json 只评一次
- 守护切片：退化候选逐条列出（summary.guard_regress）
- 未测候选：untested 名单与原因，不计入推翻
## 已知缺口
<deferred 未跑的候选；undecided 的候选；收敛原因>
## 证据清单
- `receipts/E001.json` — …（每张都列，含 discard/undecided）
- `experiment_log.jsonl` — 全部候选
- `champion.json` — 冠军与预算
- `final_test.json` — 封存终评
```

反驳门条目：①冠军领先是否只靠一个种子（逐种子符号都同向才写「稳定」）；②守护切片里有没有噪声底为 0 的切片（三种子完全相同）——有则该切片的守护判定标「噪声底不可用」；③`final_test` 为 worse 时结论必须写「验证集改进未迁移到测试集」，不许只报验证集。

## 7. 材料降级说明

本 playbook 不需要 predict/truth 长表；`model_code / experiment_config / checkpoint` 只影响候选来源：三者都 absent-confirmed 且无账本 → 无候选可排，Stage 1 止步并向用户说明。`model_profile` declined → 素版候选不可用，只接账本条目。

## 8. chartbook 覆盖声明

本 playbook 读评估器产的指标 JSON，不读长表，全部 recipe 结构性不适用：bad-window-clustering、baseline-skill、cross-dim-stability、error-acf、error-breakdown、feature-error-conditional、feature-regime-error、feature-trend-overlay、global-attribution、good-bad-contrast、horizon-degradation、horizon-error-quantiles、intraday-profile、local-waterfall、lookback-decay、model-error-correlation、model-rank-significance、oracle-gap、pp-calibration、revision-stability、rolling-stability、theil-decomposition、time-shift-diagnosis、train-test-drift、true-vs-pred-scatter、worst-points、worst-slice-compare、y-vs-feature-mapping——跳过理由相同：输入不是 setup 长表。轮次边界要看「新冠军 vs 旧冠军」的切片版图时，走生成器 playbook 的对比归因。
