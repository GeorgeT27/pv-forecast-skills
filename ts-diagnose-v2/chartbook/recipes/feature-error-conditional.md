---
id: feature-error-conditional
category: input-side
needs_materials: [predict, truth, features]
适用问题: feature 不准的时候 y 误差变大多少？哪个 feature 的质量与误差耦合最强？
outputs:
  json: feature-error-conditional.json
  png: feature-error-conditional.png
json_schema: >
  每模型每 feature：value_bins / quality_bins（分箱 RMSE）、value/quality 的
  effect_ratio（最差箱/最好箱）与 monotonic_rho（箱序 Spearman）、n。
  f_true 全缺时 quality_* 为 null（自动降级为值分箱）。
bridge_hooks: >
  某 feature quality_effect_ratio 高且 rho→1 → 该输入质量主导误差的候选（错在
  输入不在模型）；全 feature 比值都低 → 误差非输入质量驱动，转结构类假设
  （horizon-degradation / true-vs-pred-scatter 交叉）。
验证步: 真凶(耦合 ratio=3, rho=1)+诱饵(解耦 ratio<1.3)双埋点，诱饵必须不被点名（tests/test_chart_feature_error_conditional.py）
---

# feature-error-conditional：feature 质量条件误差

## 适用问题
「feature 什么时候不准、对 y-label 影响大不大」的第一张图。只产图级事实；
完整重要性归因走 feature-importance playbook 或专用特征归因技能。

## CLI 与参数
```bash
python3 chartbook/scripts/chart_feature_error_conditional.py \
  --pred predictions.parquet --features features.parquet \
  --out-dir <workdir>/charts [--n-bins 5]
```
features 长表：`window_ts|unit_id|feature|horizon_step|f_pred|f_true(可选)`。

## JSON schema
见 frontmatter；分箱按分位（qcut），键为箱内均值。n < 200 的 feature 不下断言。

## 判读
- `quality_effect_ratio ≥ 2` 且 `quality_monotonic_rho ≥ 0.8` → 候选：该 feature
  质量主导——去 feature-trend-overlay 看坏片上是否同步；
- 多个 feature 同时高比值 → 候选：共线（同一上游源坏了），先看它们 quality 的
  相互相关再点名；
- `value_bins` 有效应而 `quality_bins` 无 → 候选：模型对该值域欠拟合（非输入质量
  问题），转 true-vs-pred-scatter 的分箱残差交叉。
只给候选假设；结论回 playbook 三道门。

## 验证步
见 frontmatter；防冤枉纪律：诱饵 feature 的质量波动与误差解耦，比值必须≈1。
