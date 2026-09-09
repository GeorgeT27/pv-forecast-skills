# ts-diagnose 改进环（auto-research）+ Phase 4 workflow 设计

日期：2026-09-07。状态：待用户审阅。实施计划：`docs/superpowers/plans/2026-09-07-improve-loop-phase4.md`。

## 1. 目标与边界

**目标**：给 ts-diagnose 加一条「改进环」——把假设账本里的改法排成候选，按轮批跑重训，与冠军比较后留或弃，记进实验日志，停止规则由代码守，收敛后过结论闸产一次结论。第一条接入链固定为 `model-comparison → architecture-attribution → model-improve`。同时补上打包设计稿（2026-09-06）里推迟的 Phase 4 workflow，做成一支通用的「一轮候选并行重训」脚本，改进环与 architecture-attribution Stage 3 共用。

**不做**：其余六本分析剧本转生成器（推迟项不变）；串行爬山（候选叠在留下的候选之上，无人值守整夜跑）；`ts-batch-compute.js`；单模型专用的 model-diagnosis 生成器。

**先讨论后定的决策**（2026-09-07 会话）：
- 环放在新的薄剧本 `model-improve` 里，不塞进 model-comparison。model-comparison 只多产「改进假设」条目。
- 环的执行层与消融验证同形：改一处配置、≥3 种子重训、评估、回一张 receipt。判定层不同：消融看方向，改进看「超冠军且守护切片不退化」。
- 一轮 = 一批互相独立的候选，全部与同一冠军比；留弃裁决在轮次边界停顿点，主 agent 执行、用户看见。
- keep 规则用三种子均值与噪声底 3σ，不用单次运行；测试集封存，环内只看验证集，冠军定稿后测试集只评一次。
- 停止规则进代码：预算耗尽 / 轮数封顶 / 连续两轮无 keep / 用户 stop。
- Workflow 只带来可靠性，不带来聪明；聪明来自诊断出的候选、日志与记忆、崩溃与推翻分开。

## 2. 一轮跑起来的样子

```
model-comparison Stage 2 ──账本(H+F)──▶ architecture-attribution（机理验证，照旧）
                                             │
model-improve Stage 0  冻结评估器、跑 3 种子基线 → champion.json（E000，噪声底）   [停顿]
model-improve Stage 1  候选队列：账本 F 条目（或素版：ablation_switches）→ rounds/round_N/candidates.json（用户确认次数后 confirmed:true）
model-improve Stage 2  跑一轮：Workflow ts-train-batch（或 Agent 并行派 worker）→ receipts/E*.json → experiment_log.py append
model-improve Stage 3  裁决：experiment_log.py decide → summary.json、冠军更新、收敛判定            [停顿]
        未收敛 ──new-round──▶ 回 Stage 1（第 N+1 轮；可先重跑 model-comparison 比「新冠军 vs 旧冠军」产 post-hoc 候选）
        收敛   ──────────────▶ Stage 4  finalize（封存测试集只评一次）→ CONCLUSION.md → conclusion_gate 规则 7
```

## 3. 组件

### 3.1 评估器契约（`references/evaluator-contract.md` + `scripts/evaluator.py`）

工作目录里的 `evaluator.json`：

```json
{
  "adapter": "/abs/path/adapter.py",
  "base_config": {"model": "TSMixer", "data": "weather", "...": "..."},
  "knobs": {"tsmixer_no_channel_mix": {"family": "architecture", "type": "flag"},
            "learning_rate": {"family": "training", "type": "float"}},
  "metric": {"id": "val_mse", "direction": "lower_is_better"},
  "slices": ["horizon:near", "horizon:mid", "horizon:far"],
  "seeds": [7, 1337, 2021],
  "time_limit_s": 600
}
```

适配器 CLI：`python3 <adapter> --config <cfg.json> --seed <int> --out <dir> [--time-limit <s>]`。产物：

- `<dir>/metrics.json` = `{"status": "ok|crash|timeout", "primary": float|null, "metric_id": str, "slices": {id: float}, "t_start", "t_end", "config": {...}, "error": str|null}`
- `<dir>/sealed/test_metrics.json`：封存。环内任何脚本不读；`experiment_log.py append` 拒收含 `test`/`sealed` 键名的结果。

`evaluator.py`：`validate`（契约校验）、`run`（单种子，带超时）、`run-seeds`（多种子，产 `summary.json` = per_seed / slices_per_seed / run_status / metrics_dirs / mean / std）。knob 家族固定四种：architecture / training / features / data，`config_diff` 的键必须在 knobs 里。

参考适配器两份：`playbooks/model-improve/golden/reference/fake_adapter.py`（确定性解析式假适配器，测试与 golden 用）；`eval-cases/adapters/lsf_mini_adapter.py`（真训练：子进程跑 lsf-mini `run.py`，载 ckpt 在 val 集推理得 primary=val_mse 与切片 MSE；run.py 自带的 test 指标只写进 sealed/，pred.npy/true.npy 算完即删）。

### 3.2 实验日志与冠军（`scripts/experiment_log.py`）

- `experiment_log.jsonl`：一行一次候选：exp_id、round、hypothesis_id、source、config_diff、seeds、per_seed、mean、std、delta、noise_floor_3sigma、guard、verdict（baseline/keep/discard/undecided/untested）、receipt_file、receipt_line、metrics_dirs、t。
- `champion.json`：exp_id、config（全量）、mean/std/per_seed、noise_floor_3sigma、slices_mean、slices_noise_floor、metrics_dirs、history、budget{max_trainings, max_rounds, max_per_round, stagnation_rounds, used_trainings}、round、converged、converged_reason。
- `rounds/round_N/candidates.json`（confirmed 字段是本轮开跑的门）、`batch_result.json`（workflow 返回原样落盘）、`summary.json`。
- 子命令：`init` / `candidates` / `confirm-round` / `append` / `decide` / `new-round` / `stop` / `finalize` / `status`。全部只由主 agent 执行。
- 停止规则（`decide` 里算）：`used_trainings ≥ max_trainings` → budget_exhausted；`round ≥ max_rounds` → max_rounds；最近 `stagnation_rounds` 轮无 keep → stagnation；`stop` → user。默认 max_trainings 30、max_rounds 3、max_per_round 10、stagnation_rounds 2。
- 冠军更新：本轮 keep 里均值最小者；噪声底改用新冠军自己的三种子 std×3（与消融同约定，已知局限：三种子 std 估计粗）。
- `finalize`：读基线与冠军各种子的 `sealed/test_metrics.json`，写 `final_test.json`（basline/champion 均值、delta、测试集噪声底、verdict improved/not_distinguishable/worse/no_change）。

### 3.3 改进判定（`scripts/improve_verdict.py`）

`delta = mean(候选) − mean(冠军)`（lower_is_better；higher_is_better 时先取负）。守护切片：`delta_s > 0 且 delta_s ≥ 切片噪声底` 即退化。

| 条件 | 判定 |
|---|---|
| \|delta\| < 噪声底 3σ | undecided |
| delta < 0，无守护退化 | keep |
| delta < 0，有守护退化 | discard（receipt 记 guard=regress:切片） |
| delta ≥ 噪声底 | discard |

receipt 写 `receipts/E<id>.json`（追加数组），字段与消融 receipt 同族：exp_id、hypothesis_id、config_diff、per_seed、mean、std、champion_mean、delta、noise_floor_3sigma、seeds、guard、verdict、line、produced_by、script_sha256、t_start、t_end、script_selftest。receipt 行：`- E003 keep: hyp=F1 delta=-0.0123 noise_floor=0.0154 seeds=3 guard=ok`。`--round` 模式批量判定，供 golden 闸。

### 3.4 账本扩展（`scripts/hypothesis_ledger.py`）

只加字段，不改现有规则：`kind ∈ {mechanism（缺省）, improvement}`；improvement 必带 `fix{target_model, config_diff(dict), predicted_gain, guard_slices(list)}`，可带 `derived_from`；状态新增 `untested`（必带 `untested_reason`）；improvement 升 confirmed 必带 `receipt`。改进假设的状态映射：keep→confirmed、discard→refuted（kill_receipt=receipt 路径）、undecided→undecided、crash/timeout→untested。

### 3.5 剧本与卡片

- `playbooks/model-improve/playbook.md`：五段（0 冻结评估器与冠军基线 [停顿] / 1 候选队列 / 2 跑一轮 / 3 轮次裁决 [停顿] / 4 结论）。frontmatter `produces_experiment_log: true`；Stage 1–3 产物路径带 `{round}`；Stage 2 前置 `json:rounds/round_{round}/candidates.json:confirmed`；Stage 4 前置 `json:champion.json:converged`。golden 覆盖判定阶段（假轮次 → 四种判定）。
- `agents/model-improve-worker.md`（mode worker，serves_stages [0, 2]）：task=baseline 或 candidate；跑 `evaluator.py run-seeds` + `improve_verdict.py`；只读 champion.json；不读 sealed/；只写 `runs/<exp_id>/`、`receipts/E*.json`。
- `agents/architecture-attribution-worker.md` 输出契约加 `run_status`（每种子 ok|crash|timeout）与 `metrics_dirs`。
- `playbooks/model-comparison/playbook.md` Stage 2 加一段「改进假设 F<n>」登记规则。
- `playbooks/architecture-attribution/playbook.md` §5 加一句：Claude Code 下一轮干预可调 workflow `ts-train-batch`。

### 3.6 引擎改动（都是加法）

- `engine_common.py`：`expand_round()`（`{round}` → `state.round`，缺省 1）用于 `done_when.artifacts` 与 `json:` 路径；check-DSL 新增 `json:<路径>:<点路径>`（文件不存在或值为假 → False）。
- `orient.py`：state 保留 `round`；剧本用到 `{round}` 时头行打印「第 N 轮」。
- `conclusion_gate.py` 规则 7（只对 `produces_experiment_log: true` 生效）：CONCLUSION 必有「## 改进证据」节且含 receipt 行；`receipts/E*.json` 逐张校验字段、seeds≥3、produced_by 存在且 sha 相符；`final_test.json` 必存在且被结论引用；证据清单必列全部 E receipt、experiment_log.jsonl、champion.json、final_test.json。
- `SKILL.md` 路由表加一行、12→13；`README.md` 同步；`engine-core.md` 假设验证循环节加「改进环」三行（预算 ≤4200）；`_playbook-spec.md` 记 `{round}` 与 `json:`；CHANGELOG 一行。

### 3.7 Workflow（`workflows/ts-train-batch.js`）

`args = {engine, workdir, agent_type, task, candidates: [...], chunk}`。按 chunk 分批，批内 `parallel` 派 `agentType: args.agent_type`，每条候选一个 agent，prompt 只带卡片「输入」节字段，`schema` = 卡片输出契约；返回 `{results, failed}`。判定、账本、冠军、停止全在主 agent。不用 `Date.now`/`Math.random`。剧本里写明调用方式：`Workflow` 工具 `scriptPath=<ENGINE>/workflows/ts-train-batch.js`（按名字注册与否都能跑）；不可用时回退为主 agent 一条消息并行派多张 worker 卡。`install.sh` 已会链接 `workflows/*.js`，`INSTALL.md` 补一句。

## 4. 验证

- 单测：`{round}`/`json:` DSL、账本扩展、improve_verdict 四态、experiment_log 全子命令与四条停止规则、evaluator 契约（假适配器：ok/crash/timeout/切片缺失）、conclusion_gate 规则 7 正反例、workflow 静态检查（+ `node --check`）、卡片守卫自动覆盖新卡、路由/分层/golden 守卫更新。
- 集成：`eval-cases/adapters/lsf_mini_adapter.py` 在 ETTh1 上 1 epoch（lsf-mini 缺席则 skip）。
- 冒烟（计划内、脚本驱动、不经 agent 交互）：`eval-cases/improve-smoke-weather/`，TSMixer @ Weather pl96 素版：3 种子基线（约 1 分钟/次）→ 第 1 轮 4 候选 × 3 种子 → decide → new-round → 第 2 轮 2 候选 → 收敛（max_rounds=2）→ finalize → CONCLUSION.md 过闸；每步跑 orient 断言阶段推进。产物只提交 json/jsonl/md/receipts，训练目录 gitignore。**不读 `eval-cases/holdout/HW1`**（Weather 上的冻结 holdout 案例）。
- 全链路联调（计划外，需用户在场）：model-comparison(TSMixer vs NLinear @ Weather) → 账本 H+F → architecture-attribution → model-improve 经 Workflow 派卡跑一轮。

## 5. 风险与已知局限

- 三种子噪声底估计粗（PatchTST 3σ 曾算出 0.0006），可能把微小 delta 判成显著；沿用引擎现约定，冒烟时观察。
- `~/.claude/workflows/` 按名字注册未实测；用 `scriptPath` 调用规避。
- 训练目录体积：Weather 单次 pred/true 各 84 MB，适配器算完即删。
- 改进环只接账本里 `kind: improvement` 的条目；其余剧本要接入需各自多产候选清单（另出计划）。
