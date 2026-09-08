# 评估器契约（改进环的训练入口）

工作目录放 `evaluator.json`，主 agent 在 model-improve Stage 0 按用户答案写；写完先跑
`python3 "<ENGINE>/scripts/evaluator.py" validate evaluator.json`。

字段：`adapter`（适配器脚本绝对路径）、`base_config`（冠军起点的全量配置）、`knobs`（每个可改
配置项 → `{"family": architecture|training|features|data, "type": flag|int|float|str}`；`config_diff`
只许改这里登记过的键）、`metric`（`{"id", "direction": lower_is_better|higher_is_better}`）、
`slices`（适配器必须产出的切片 id 列表，守护切片从中选）、`seeds`（≥3 个整数）、
`time_limit_s`（单次训练上限，超过记 timeout）、可选 `kill_grace_s`（超时后再等几秒，缺省 60）。

适配器 CLI：`python3 <adapter> --config <cfg.json> --seed <int> --out <dir> [--time-limit <秒>]`。
适配器必须写 `<dir>/metrics.json`：`status`（ok|crash|timeout）、`primary`（该种子的指标）、
`metric_id`、`slices`（切片 id → 指标）、`t_start`、`t_end`、`config`、`error`。
测试集指标只写 `<dir>/sealed/test_metrics.json`（键 `test_primary`），环内任何脚本不读它，
`experiment_log.py finalize` 在收敛后读一次。

跑法：`evaluator.py run-seeds --evaluator evaluator.json --config-diff '<json>' --out-root runs/<exp_id>`
→ `runs/<exp_id>/seed_<n>/metrics.json` 与 `runs/<exp_id>/summary.json`（per_seed / slices_per_seed /
run_status / metrics_dirs / mean / std）。任一种子非 ok，退出码 2，summary 仍写。

参考实现：`playbooks/model-improve/golden/reference/fake_adapter.py`（解析式假适配器，不训练）；
`eval-cases/adapters/lsf_mini_adapter.py`（lsf-mini 真训练，仓库根下）。
