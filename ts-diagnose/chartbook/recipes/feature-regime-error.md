---
id: feature-regime-error
category: input-side
needs_materials: [predict, truth, features]
适用问题: 按多变量输入状态聚出的"制式"里,哪个制式下误差最重?占比多少?
outputs:
  json: feature-regime-error.json
  png: feature-regime-error.png
json_schema: >
  chosen_k、silhouette_by_k、seed、regimes[{share, n, centroid{特征:原始
  单位均值}, rmse_by_model, }]、worst_best_ratio_by_model。制式不做领域
  命名——质心事实归 JSON,命名交运行时判读结合 intake 背景。
bridge_hooks: >
  某制式 rmse 比值 ≥2 且占比可观 → 模型对该输入状态失配候选——与
  feature-error-conditional 的单特征分箱互证(多变量制式 vs 单变量条件);
  全制式误差均衡 → 输入状态不是分辨维度,转 temporal/结构类图。
验证步: 两个分离制式、一制式 3 倍误差 → chosen_k=2、质心与比值精确回收(tests/test_chart_feature_regime_error.py)
---

# feature-regime-error:多变量制式条件误差

## 适用问题
单特征分箱(feature-error-conditional)看不到"多个输入共同定义的状态"。
本图对窗口级特征向量聚类,回答"误差集中在哪种输入状态"。

## CLI 与参数
```bash
python3 chartbook/scripts/chart_feature_regime_error.py \
  --pred predictions.parquet --features features.parquet \
  --out-dir <workdir>/charts [--seed 0]
```
k 在 2..4 由轮廓系数选;seed 落 JSON。

## JSON schema
见 frontmatter;窗口特征向量 = 每特征窗内 f_pred 均值,聚类前逐特征标准化,
centroid 以原始单位报告。

## 判读
- worst_best_ratio ≥ 2 的模型 → 候选:该模型对高误差制式的输入状态失配;
  对照 centroid 数字与 intake 背景给制式起名后再入结论;
- 所有模型在同一制式同倍率变差 → 数据侧难度(该状态本身难预测),不是
  单模型失配——与 model-error-correlation 互证;
- share < 0.05 的小制式不下断言(n 太小)。
只给候选假设;结论回 playbook 三道门。

## 验证步
两特征、两制式(质心 (0,0) vs (10,10))、制式 2 植入 3 倍误差 →
chosen_k=2、centroid 精确回收、worst_best_ratio≈3。
