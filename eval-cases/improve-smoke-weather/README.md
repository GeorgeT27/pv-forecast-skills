# improve-smoke-weather

目的：脚本驱动跑通改进环机器件（`experiment_log.py` + `evaluator.py` + `improve_verdict.py` + `conclusion_gate.py`），验证 orient 逐阶段推进、`{round}` 占位展开、收敛判定与结论过闸规则 7。不经 agent 交互，`smoke_driver.py` 代替 worker 卡片。目标模型 TSMixer @ Weather pl96，候选来源 `switches.json`（素版，无假设账本）。

## 复现命令

```bash
cd <REPO>/eval-cases/improve-smoke-weather
ENGINE=<REPO>/ts-diagnose
python3 "$ENGINE/scripts/orient.py" | head -20
python3 "$ENGINE/scripts/evaluator.py" validate evaluator.json
python3 smoke_driver.py "$ENGINE" baseline
python3 "$ENGINE/scripts/experiment_log.py" init --evaluator evaluator.json --baseline runs/E000/summary.json \
        --max-trainings 30 --max-rounds 2 --max-per-round 4
python3 "$ENGINE/scripts/orient.py" | head -20
python3 "$ENGINE/scripts/experiment_log.py" candidates --switches switches.json --target TSMixer \
        --guard horizon:near,horizon:mid,horizon:far
python3 "$ENGINE/scripts/orient.py" | head -20
python3 "$ENGINE/scripts/experiment_log.py" confirm-round
python3 "$ENGINE/scripts/orient.py" | head -20
python3 smoke_driver.py "$ENGINE" round
python3 "$ENGINE/scripts/experiment_log.py" append --batch rounds/round_1/batch_result.json
python3 "$ENGINE/scripts/orient.py" | head -20
python3 "$ENGINE/scripts/experiment_log.py" decide
python3 "$ENGINE/scripts/orient.py" | head -20
python3 "$ENGINE/scripts/experiment_log.py" new-round
python3 "$ENGINE/scripts/orient.py" | head -20
python3 "$ENGINE/scripts/experiment_log.py" candidates --switches switches.json --target TSMixer \
        --guard horizon:near,horizon:mid,horizon:far
python3 "$ENGINE/scripts/experiment_log.py" confirm-round
python3 smoke_driver.py "$ENGINE" round
python3 "$ENGINE/scripts/experiment_log.py" append --batch rounds/round_2/batch_result.json
python3 "$ENGINE/scripts/experiment_log.py" decide
python3 "$ENGINE/scripts/orient.py" | head -20
python3 "$ENGINE/scripts/experiment_log.py" finalize
python3 "$ENGINE/scripts/experiment_log.py" status
python3 "$ENGINE/scripts/provenance.py" --code ../adapters/lsf_mini_adapter.py \
        --data evaluator.json experiment_log.jsonl --out provenance.json
python3 "$ENGINE/scripts/conclusion_gate.py"
python3 "$ENGINE/scripts/orient.py" | head -5
```

## 运行记录

以下每步取 orient 输出中标注当前阶段的那一行（Stage 列表里带 `← 当前` 的行，或前置校验行），与子命令自己打印的 `✓` 行。实测均与预期一致，无需修脚本或剧本。

| 步骤 | 命令 | orient / 子命令输出 | 与预期对照 |
|---|---|---|---|
| 1 | `orient`（首次，config 已建好） | `Stage 0 冻结评估器与冠军基线 ⏸ [← 当前]` | 预期 Stage 0，符合 |
| 2 | `evaluator.py validate` | `✓ evaluator.json 合法` | 通过 |
| 3 | `smoke_driver.py baseline` | `{"run_status": ["ok","ok","ok"], "mean": 0.3889119823773702, "std": 0.0022465363786872746, "summary": "runs/E000/summary.json"}` | 3 种子全 ok |
| 4 | `experiment_log.py init` | `✓ 冠军 E000：mean=0.388912 std=0.002247 噪声底3σ=0.006740；预算 30 次训练 / 2 轮 / 每轮 ≤4 候选；已用 3` | — |
| 5 | `orient` | `Stage 1 候选队列 [← 当前]`；`改进环：第 1 轮` | 预期 Stage 1（第 1 轮），符合 |
| 6 | `experiment_log.py candidates`（round 1） | `✓ 第 1 轮候选 4 条（× 3 种子 = 12 次训练），顺延 2 条 → rounds/round_1/candidates.json` | 预期 4 条候选、顺延 2 条，符合 |
| 7 | `orient` | `进入 Stage 2 的前置：[✓] 本轮候选已排 [✗] 用户已确认本轮训练次数（candidates.json.confirmed）` | 预期 Stage 2 前置 ✗（未确认），符合 |
| 8 | `experiment_log.py confirm-round` | `✓ 第 1 轮已确认开跑：['E001', 'E002', 'E003', 'E004']` | — |
| 9 | `orient` | `Stage 2 跑一轮 [← 当前]`；前置 `[✓][✓]` 全过 | 预期 Stage 2，符合 |
| 10 | `smoke_driver.py round`（round 1，12 训练） | `✓ batch_result.json: [('E001','COMPUTE_DONE'),('E002','COMPUTE_DONE'),('E003','COMPUTE_DONE'),('E004','COMPUTE_DONE')]` | 全部 COMPUTE_DONE，无 BLOCKED |
| 11 | `experiment_log.py append`（round 1） | `✓ 追加 4 行：E001=undecided, E002=undecided, E003=undecided, E004=undecided` | — |
| 12 | `orient` | `Stage 3 轮次裁决 ⏸ [← 当前]` | 预期 Stage 3，符合 |
| 13 | `experiment_log.py decide`（round 1） | `✓ 第 1 轮裁决：{'undecided': 4}；冠军 E000 → E000（mean=0.388912）；已用训练 15/30；未收敛 → new-round 或 stop` | 预期未收敛（round 1<2），符合 |
| 14 | `orient` | `进入 Stage 4 的前置：[✗] 已收敛（预算耗尽 / 轮数封顶 / 连续无 keep / 用户 stop）` | 预期 Stage 4 前置 ✗（未收敛），符合 |
| 15 | `experiment_log.py new-round` | `✓ 进入第 2 轮——下一步 candidates（回生成器补的候选标 provenance=post-hoc）` | — |
| 16 | `orient` | `Stage 1 候选队列 [← 当前]`；`改进环：第 2 轮` | 预期 Stage 1（第 2 轮），符合 |
| 17 | `experiment_log.py candidates`（round 2） | `✓ 第 2 轮候选 2 条（× 3 种子 = 6 次训练），顺延 0 条 → rounds/round_2/candidates.json`（`d_model`/`e_layers`） | 预期 2 条、去重后剩 d_model/e_layers，符合 |
| 18 | `experiment_log.py confirm-round` | `✓ 第 2 轮已确认开跑：['E005', 'E006']` | — |
| 19 | `smoke_driver.py round`（round 2，6 训练） | `✓ batch_result.json: [('E005','COMPUTE_DONE'),('E006','COMPUTE_DONE')]` | 全部 COMPUTE_DONE |
| 20 | `experiment_log.py append`（round 2） | `✓ 追加 2 行：E005=discard, E006=discard` | — |
| 21 | `experiment_log.py decide`（round 2） | `✓ 第 2 轮裁决：{'discard': 2}；冠军 E000 → E000（mean=0.388912）；已用训练 21/30；已收敛（max_rounds）→ 进结论阶段` | 预期已收敛（max_rounds），符合 |
| 22 | `orient` | `Stage 4 结论落笔 [← 当前]` | 预期 Stage 4，符合 |
| 23 | `experiment_log.py finalize` | `- final_test no_change: champion=E000 delta=+0.0000 noise_floor=0.0188 seeds=3` | 冠军自始至终未变，测试集终评 no_change |
| 24 | `provenance.py` | 写 `provenance.json`；代码 hash `5cce87d0527446c6`，数据 hash `6b962af36a723d83` | — |
| 25 | `conclusion_gate.py` | `✓ 结论闸通过，receipt 已写 gate_reports/conclusion_gate.json` | 通过 |
| 26 | `orient` | `Stage 0/1/2/3/4 全部 [已完成]`；`全部阶段完成——可写/刷新 CONCLUSION.md` | 预期全部阶段完成，符合 |

## 结果摘要表

来自 `experiment_log.jsonl`（val_mse，lower_is_better；噪声底 3σ=0.006740）：

| exp_id | round | config_diff | mean | delta vs 基线 | verdict |
|---|---|---|---|---|---|
| E000 | 0 | `{}`（基线） | 0.388912 | 0.0000 | baseline |
| E001 | 1 | `{"batch_size": 64}` | 0.384061 | -0.004851 | undecided |
| E002 | 1 | `{"dropout": 0.2}` | 0.389533 | +0.000621 | undecided |
| E003 | 1 | `{"learning_rate": 0.0005}` | 0.383685 | -0.005227 | undecided |
| E004 | 1 | `{"tsmixer_no_channel_mix": true}` | 0.391598 | +0.002686 | undecided（守护退化 horizon:far/mid，未触发否决） |
| E005 | 2 | `{"d_model": 256}` | 0.403204 | +0.014292 | discard（守护退化 + 整体变差） |
| E006 | 2 | `{"e_layers": 3}` | 0.406073 | +0.017161 | discard（守护退化 + 整体变差） |

冠军自始至终为 E000（未换）。封存测试集终评（`final_test.json`）：no_change，delta=+0.0000，噪声底 3σ=0.018807，seeds=3。收敛原因 `max_rounds`（budget.used_trainings=21/30，未耗尽预算，是轮数封顶先触发）。

## 说明

- `receipts/*.json` 的 `produced_by` 字段是本机绝对路径（`/private/tmp/improve-loop-phase4/eval-cases/adapters/lsf_mini_adapter.py`）；换一台机器重跑 `conclusion_gate.py`，该路径不存在会导致规则 7 校验不过——这是预期行为，不是 bug，重跑前须在目标机器上重新走一遍改进环产生本机自己的 receipts。
- 本机绝对路径不止 receipt 一处：`evaluator.json` 的 `adapter` 是 `/private/tmp/improve-loop-phase4/eval-cases/adapters/lsf_mini_adapter.py`，`base_config.lsf_mini_dir` 指向 `/Users/tqa946816/Documents/华为/光伏预测/lsf-mini`，`base_config.root_path` 比它深一级、指向该目录下的 `dataset/`，`champion.json` 的 `base_config` 存了同样这两个路径。
- 所以在本用例上跑 `evaluator.py validate` 与 `conclusion_gate.py`，上述路径必须在本机存在，否则校验不过。
- 下一次冒烟把 `evaluator.json` 的 `adapter` 写成相对路径 `../adapters/lsf_mini_adapter.py`，只留数据集目录一处按机器改。
- 本目录不读、不参考 `eval-cases/holdout/HW1/`（同数据集上的冻结留出用例）。
