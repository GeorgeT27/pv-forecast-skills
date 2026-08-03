---
id: horizon-error-quantiles
category: error-structure
needs_materials: [predict, truth]
适用问题: h 步预测该配多宽的经验置信带?误差分布随 horizon 是否偏斜/厚尾?
outputs:
  json: horizon-error-quantiles.json
  png: horizon-error-quantiles.png
json_schema: >
  每模型:p05/p25/p50/p75/p95 逐 horizon 曲线(curve_stats)、width90 曲线
  (p95−p05)、growth_ratio(末步 width90/首步 width90)、median_skew
  (p50 偏离 0 的均值)、n_per_step。
bridge_hooks: >
  width90 随 horizon 线性/超线性增长 → 误差累积类候选,与 horizon-degradation
  的 RMSE 曲线互证;p50 持续偏一侧 → 系统性偏差候选,转 theil-decomposition
  看 U_bias 占比;带宽不增但 RMSE 增 → 少数大误差点驱动,转 worst-points。
验证步: 植入误差幅度 0.1·(h+1)、窗口间对称正负 → 每步 p05/p95=∓/+幅度、width90 线性增长精确回收(tests/test_chart_horizon_error_quantiles.py)
---

# horizon-error-quantiles：逐步误差分位扇形带

## 适用问题
点预测场景下「该给下游多宽的置信带」的经验答案；同时把「误差大」细化成
「分布宽」还是「分布偏」。

## CLI 与参数
```bash
python3 chartbook/scripts/chart_horizon_error_quantiles.py \
  --pred predictions.parquet --out-dir <workdir>/charts
```

## JSON schema
见 frontmatter；分位在每 (model, horizon_step) 的全部 err 样本上算（pool 单元与窗口）。

## 判读
- `growth_ratio` 大（>3）且 width90 曲线单调 → 候选：误差随 horizon 累积——
  与 horizon-degradation 退化斜率互证；
- `median_skew` 显著非 0 → 候选：系统性偏差主导，转 theil-decomposition；
- 带对称且窄、但 RMSE 高 → 厚尾/离群驱动，转 worst-points 看点级性质。
只给候选假设；结论回 playbook 三道门。

## 验证步
4 窗口、误差幅度 0.1·(h+1)、窗口按奇偶取正负号（每步样本恰为 {−a,−a,+a,+a}）→
p05=−a、p95=+a、p50=0、width90=0.2·(h+1) 逐步精确回收，growth_ratio=末步/首步。
