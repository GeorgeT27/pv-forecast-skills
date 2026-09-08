# 结论

一句话：冠军 E000（无配置变动，2 轮 6 候选全部未能超越基线）验证集 val_mse 维持在 0.388912（基线同值）；封存测试集终评 no_change（见 `final_test.json`）。

## 模型结构依据

absent-confirmed：无模型档案，降级为配置级改进结论。`model_code`/`experiment_config`/`checkpoint` 三项材料均 `absent-confirmed`（用户亲口确认无档案），`model_profile` 产物 `declined`；候选全部来自素版 `switches.json`（配置级开关），不涉及架构机理归因。

## 改进证据

第 1 轮（4 候选，`rounds/round_1/summary.json`）：

- E001 undecided: hyp= delta=-0.0049 noise_floor=0.0067 seeds=3 guard=ok
- E002 undecided: hyp= delta=+0.0006 noise_floor=0.0067 seeds=3 guard=ok
- E003 undecided: hyp= delta=-0.0052 noise_floor=0.0067 seeds=3 guard=ok
- E004 undecided: hyp= delta=+0.0027 noise_floor=0.0067 seeds=3 guard=regress:horizon:far,horizon:mid

第 2 轮（第 1 轮顺延的 2 候选，`rounds/round_2/summary.json`）：

- E005 discard: hyp= delta=+0.0143 noise_floor=0.0067 seeds=3 guard=regress:horizon:far,horizon:mid
- E006 discard: hyp= delta=+0.0172 noise_floor=0.0067 seeds=3 guard=regress:horizon:far,horizon:mid

封存测试集终评（`final_test.json`）：

- final_test no_change: champion=E000 delta=+0.0000 noise_floor=0.0188 seeds=3

## 反驳排除

- 单次运行误判：每条候选 3 种子（`evaluator.json.seeds`=[7,1337,2021]），噪声底 3σ 见 `champion.json`（基线 std=0.002247，噪声底 3σ=0.006740）——6 条候选逐一与该噪声底比较后才判定，无一条只凭单次运行留下。
- 验证集过拟合：测试集封存于各 `runs/E*/seed_*/sealed/test_metrics.json`，`experiment_log.py finalize` 收敛后只开封一次，写入 `final_test.json`，本结论未在环内反复窥探测试集。
- 守护切片：E004/E005/E006 三条候选的 `horizon:far`、`horizon:mid` 切片均退化（delta>0 且 ≥ 该切片噪声底），E005/E006 因此在验证集侧就被判 discard；E004 虽守护退化但整体 |delta| 未过噪声底，判 undecided（守护结果仅作为参考记录，未单独触发否决）。E001–E003 三条候选守护切片均无退化（guard=ok）。守护切片自身的噪声底（`champion.json.slices_noise_floor`）：horizon:near=0.0236、horizon:mid=0.0083、horizon:far=0.0061，均非零，判定有效。
- 未测候选：本次 6 条候选训练全部 3 种子 run_status 均为 ok，无 crash/timeout，untested 名单为空（两轮 `summary.json.untested` 均为 `[]`），不存在"崩溃当推翻"的问题。
- 冠军领先是否只靠一个种子：不适用——本次 6 条候选均未升为冠军（0 keep），冠军自始至终是基线 E000，不存在"新冠军靠单一种子领先"的情形。

## 已知缺口

- 无剩余顺延候选：第 1 轮顺延 2 条（`d_model=256`、`e_layers=3`）已在第 2 轮全部跑完并判 discard；第 2 轮 `deferred=[]`。
- E001–E004 四条候选终态为 undecided（验证集侧效果落在噪声带内，既非改进也非退化），不计入推翻，也不视为改进证据；本冒烟未追加种子去缩小这四条的不确定区间（预算已在第 2 轮触顶，见下）。
- 收敛原因：`max_rounds`（2/2 轮已用满，budget.used_trainings=21/30——预算未耗尽，是轮数封顶先触发，见 `champion.json.budget`）。
- 本次候选来源为素版 `switches.json`（无假设账本），未探测这 6 个开关以外的配置空间，也未做架构级消融；`model_profile` 已 declined，未来若要机理归因需另跑 model-audit + architecture-attribution。

## 证据清单

- `receipts/E001.json` — batch_size=64，undecided
- `receipts/E002.json` — dropout=0.2，undecided
- `receipts/E003.json` — learning_rate=0.0005，undecided
- `receipts/E004.json` — tsmixer_no_channel_mix，undecided（守护退化，未触发否决）
- `receipts/E005.json` — d_model=256，discard（守护退化 + 整体变差）
- `receipts/E006.json` — e_layers=3，discard（守护退化 + 整体变差）
- `experiment_log.jsonl` — 全部候选（含基线 E000 与 E001–E006）逐行记录
- `champion.json` — 冠军状态、预算与收敛原因
- `final_test.json` — 封存测试集终评（no_change）
- `rounds/round_1/summary.json` — 第 1 轮裁决全量（counts/receipt_lines/guard_regress/deferred）
- `rounds/round_2/summary.json` — 第 2 轮裁决全量（counts/receipt_lines/guard_regress/deferred）

## Provenance（结论可归因块）

- 生成代码 hash：`5cce87d0527446c6`（1 个脚本，逐文件见 provenance.json）
- 输入数据 hash：`6b962af36a723d83`（2 个文件）
- 金标准自检：无闸报告（本 playbook 无 golden 覆盖阶段，或漏跑 gen_gate）
- 归因规则：两次运行结论不同 → 代码 hash 变 = 生成不稳定；数据 hash 变 = 真实变化。
