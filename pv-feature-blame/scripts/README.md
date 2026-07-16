# scripts/ 速查（详细字段说明见各脚本 docstring 与 fb_common.py 头部）

所有脚本在**工作目录**下运行（读 `blame_config.json` 取默认，CLI flag 覆盖），
打印 ≤30 行摘要，产物落盘自足。`<SKILL>` = 本技能目录绝对路径。

| 脚本 | 阶段 | 命令要点 | 产物 |
|------|------|----------|------|
| `run_orient.py` | Step 0 | `[--goto N]`；执行 feature_true 硬规则 | blame_state.json + PROGRESS.md |
| `probe_schema.py` | 0 | `[--test --predict --feature-true] [--n-overlap-checks 200]` | probe_schema.json + feature_pairs.json |
| `find_bad_rows.py` | 1 | `[--models auto|列名,..] [--metrics ultra_short,short] [--top-pct 10] [--summary-out ...]` | bad_rows_<口径>_<模型>.csv + bad_rows_summary.json |
| `feature_blame.py` | 2 | `[--pairs feature_pairs.json] [--bad-rows bad_rows_summary.json] [--z-hi 2.0 --spearman-min 0.3 --top-k 3]` | blame_report.csv + blame_summary.json |
| `feature_revision.py` | 2 | 翻新跳变两关（免 API）：`[--spearman-min 0.3 --jumpiness-min 0.05 --stable-max 0.02]` | revision_report.csv + revision_summary.json |
| `counterfactual_api.py` | 4 | **先 `--dry-run`（计划表+payload）**；`--mode oracle|per-feature|all-blamed|minimal-set|lattice|neighbor-swap [--metric --model --max-calls 400 --lattice-rows 3 --pairs-top 5]`；跨层缓存去重 + 断点续跑 + 版本漂移闸 | counterfactual_results.csv + neighbor_swap_results.csv + counterfactual_summary.json |
| `cf_logic.py` | 4 | 纯决策逻辑（零网络）；`--selfcheck` 跑合成模型断言（过闸 stage "4"） | cf_logic_selfcheck.json |
| `api_adapter_template.py` | 4 | `cp` 成工作目录 `adapter.py` 填 TODO（payload/响应契约；row 含 model 字段） | — |
| `fb_common.py` | 共享 | config / 口径切片（import data_utils）/ 统计工具 | — |

## 质量闸与测试

```bash
# 改了阶段脚本后必须重过闸（<ENGINE> = ts-diagnose 目录）：
python3 "<ENGINE>/scripts/gen_gate.py" --script "<SKILL>/scripts/<脚本>" \
    --playbook "<SKILL>/SKILL.md" --stage <0|1|2|revision|4>
# 全量测试（含金标准端到端 + 放水必拦）：
python3 -m pytest "<SKILL>/scripts/" -q
# 重生成金标准（改埋点后：期望值跟着改 manifest.json，中间产物重拷）：
python3 "<SKILL>/golden/make_golden.py"
```
