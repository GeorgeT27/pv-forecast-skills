# subagent 派发模板（重活外包；主 agent 保留问用户/综合/反驳门/状态文件）

**单写者纪律**：`blame_state.json` / `PROGRESS.md` / `FINDINGS.md` / `blame_config.json` /
`feature_pairs.json` 只由主 agent 写。subagent 只读 JSON/CSV、只写自己 brief 指定的产物；
parquet 内容与 API payload 明细不进对话，只回 ≤30 行数字摘要。

## Brief G —— Stage 1+2 按模型分片（模型多或行多时）

> 工作目录：`<绝对路径>`（已有 blame_config.json / probe_schema.json / feature_pairs.json）。
> 你负责模型 `<模型列名>`：
> 1. `python3 <SKILL>/scripts/find_bad_rows.py --models <模型列名>`
>    （注意：多分片并行时各自 `--summary-out bad_rows_summary_<模型>.json`，主 agent 合并）
> 2. `python3 <SKILL>/scripts/feature_blame.py --bad-rows bad_rows_summary_<模型>.json \
>        --out blame_report_<模型>.csv --summary blame_summary_<模型>.json`
> 3. 只回：每口径的 坏行数 / 被点名特征及其 (z, ρ) / 共线簇。不要贴 CSV 内容。
> 禁止：改任何共享状态文件；碰其他模型的产物。

## Brief H —— Stage 4 批量反事实调用

> 工作目录：`<绝对路径>`（已有 adapter.py，config.api.confirmed=true，
> 且主 agent 已用 `--dry-run` 让用户确认过 payload）。
> 执行：`python3 <SKILL>/scripts/counterfactual_api.py --mode <per-feature|all-blamed> \
>     [--metric <口径>] [--model <模型>] [--max-calls <N>]`
> 结果逐行追加落 `counterfactual_results.csv`（脚本自带断点续跑，重复执行安全）。
> 只回：counterfactual_summary.json 里每 (口径×模型×特征) 的 Δ 与改善占比。
> 禁止：改 endpoint / 改 adapter.py / 打 --dry-run 之外未确认的新口径。

## Brief I —— Stage 4 阶梯按层分批（v2）

> 工作目录：`<绝对路径>`（已有 adapter.py + blame_report.csv + revision_summary.json，
> config.api.confirmed=true，主 agent 已 `--dry-run` 让用户确认过计划表与 payload；
> neighbor-swap 层还需 config.api.neighbor_swap_confirmed=true）。
> 执行你被指派的**一层**（跨层缓存自动去重，重复执行安全）：
> `python3 <SKILL>/scripts/counterfactual_api.py --mode <oracle|minimal-set|lattice|neighbor-swap> \
>     [--metric <口径>] [--model <模型>] [--max-calls <N>]`
> 只回：本层新增调用数 + counterfactual_summary.json 的 行判定统计（非特征问题/单特征可修/
> 需联合修复 各多少）/ minimal_sets 频次 / version_drift.share / neighbor_swap 的 churn 消减。
> 禁止：改 τ/g_min/drift 阈值（阈值敏感性由主 agent 披露）；改 endpoint / adapter.py；
> 一次跑多层（主 agent 逐层看结果决定是否继续，oracle 的 G 闸结果决定后面几层的行集）。

## 嵌入式主技能运行（需要预测侧上下文时）

坏行的天气分型 / suspect_days 数据质量证据来自留出站线的 pv-result-analysis 产物；
没跑过且用户同意时，参照 `pv-station-influence/references/subagent-briefs.md`
「嵌入式主技能运行」节（Brief B→A 跑到现象清单为止），产物目录回填进 FINDINGS 引用。
