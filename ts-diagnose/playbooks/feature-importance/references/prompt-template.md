# 标准调用 prompt 模板

（用户口径约定，2026-07-16 定稿；2026-07-24 随方法并入 ts-diagnose 的 feature-importance playbook 后更新槽位映射与阶段号。）

用户按下面模板发起本变体。路由链条：ts-diagnose 引擎 → `feature-importance` playbook → `feature-quality`/`counterfactual` 变体，由 `material:feature_true` 解锁。**方括号是槽位**：用户填了的内容直接映射进 `blame_config.json`；缺了的才用 AskUserQuestion 问。不要重复问模板里已经写明的内容。

```text
目标：光伏功率预测的预测特征质量归因（ts-diagnose 引擎 feature-importance playbook）——
先按考核口径找坏行，
再对坏行逐特征对比 预测 vs 真值 点名元凶特征，最后（我确认后）跑反事实验证。

【数据三件套】
- test.parquet：      [/path/to/test.parquet]
- predict.parquet：   [/path/to/predict.parquet]      # 模型列：[全部 / 只分析 M3,ensemble 等]
- feature_true.parquet：[/path/to/feature_true.parquet]

【口径 / 参数】
- 口径：[默认 rmse_192（每行 192 点 RMSE 平均）/ 也可 ultra_short / short，可多选]
- top_pct（坏行阈值，默认10）：[10 / 或说明我的数据量]

【反事实 API（可选，用于把坏特征换真值重预测验证）】
- 我的 FastAPI 预测服务地址：[http://... 或 "暂时没有，先不做反事实"]
- 请求/响应契约说明：[FastAPI 示例代码/调用示例，或说 "按 api_adapter_template.py 走，
  先 dry-run 给我看 payload"]

【实验线 / 项目上下文】（若之前建过就填，没有就留空让它问我）
- experiment 名：[已有实验线名 / 或 "新建"]

请先跑 orient 定位阶段（feature_true 材料就位会自动解锁 Stage 5 变体），
Stage 5（特征质量归因）事实提取后停下来等我点名，
Stage 6 反事实先 --dry-run 给我确认计划表和 payload 再打真实 API。
```

## 槽位 → 执行的映射

| 槽位 | 映射 |
|------|------|
| 三件套路径 | `config.test_label / predict / feature_true`（feature_true 硬规则不变：缺了 Stage 5 不解锁，必须问用户） |
| 模型列 | `find_bad_rows.py --models`（填"全部" = auto） |
| 口径 | `config.metrics`。**当前默认 `rmse_192` = 每行全 192 点 RMSE、全部行参与**（用户 2026-07-16 定：不再默认看 ultra_short/short，除非模板里点名） |
| top_pct | `config.top_pct`（数据量小时跟用户确认，见 playbook.md §7） |
| FastAPI 地址 | `config.api.endpoint`；填"暂时没有" → Stage 6（counterfactual 变体）不解锁，Stage 5 点名后停下，不追问反事实 |
| 契约说明 | 用户给了**示例代码**，就照示例填工作目录 `adapter.py`（build_payload/parse_response），不臆测字段名；给不出 → 复制 `<本 playbook 目录>/scripts/api_adapter_template.py` 让用户填。无论哪种，首跑必 `--dry-run` 给用户确认 |
| experiment 名 | 走 project-context 实验线流程（Step 0.5）；留空 → 列出 experiments/*.json 问用户一次 |

模板尾部两条流程约定与 playbook.md §7-8 一致：Stage 5 事实提取后停下（pause_after）、Stage 6 先 dry-run 确认再打真实 API。模板的出现不豁免任何门控——api.confirmed / neighbor_swap_confirmed 仍须逐项确认。
