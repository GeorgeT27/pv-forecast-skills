---
id: feature-trend-overlay
category: input-side
needs_materials: [predict, truth, features]
适用问题: 最差月份里 feature 是不是也在坏？输入质量恶化与 y 误差在时间上同步吗？
outputs:
  json: feature-trend-overlay.json
  png: feature-trend-overlay.png
json_schema: >
  slice（自动选焦点模型最差月，可指定）、每 feature：aligned 日对齐序列
  （y_rmse/f_pred/f_true?/quality?，降采样）、sync_basis(quality|level)、
  sync_corr、n_days。
bridge_hooks: >
  sync_corr 高（≥0.7）且 basis=quality → 输入质量事件驱动坏片的候选，与
  feature-error-conditional 的高比值 feature 交叉印证；坏片里 quality 平稳而
  y_rmse 突跳 → 输入无辜，转 rolling-stability 变点/外生事件类候选。
验证步: 坏月内日质量与日误差完全耦合 → 切片自动选中、corr>0.99、量值精确回收（tests/test_chart_feature_trend_overlay.py）
---

# feature-trend-overlay：坏片上的输入-误差对照

## 适用问题
error-breakdown / worst-slice-compare 定位坏片之后，看该片内输入质量走势是否
与误差同步——归因方向的第一道分流（输入侧 vs 模型侧）。

## CLI 与参数
```bash
python3 chartbook/scripts/chart_feature_trend_overlay.py \
  --pred predictions.parquet --features features.parquet \
  --out-dir <workdir>/charts [--model A] [--slice-month 2024-02]
```

## JSON schema
见 frontmatter；y 日指标 = 焦点模型日均行 RMSE（与 rolling-stability 同口径）。

## 判读
- `sync_corr ≥ 0.7` 且 basis=quality → 候选：输入质量事件——回
  feature-error-conditional 看该 feature 的 effect_ratio 是否也高（两线一致才升假设）；
- corr 低但坏片存在 → 候选：模型侧/其他输入——转 worst-points 看点级性质；
- basis=level 时 corr 高只说明"误差跟着量值走"（如辐照高误差大是正常物理），
  **不可**据此点名 feature 质量。
只给候选假设；结论回 playbook 三道门。

## 验证步
见 frontmatter。
