---
id: y-vs-feature-mapping
needs_materials: [predict, truth, features]
适用问题: y 与关键 feature 的物理映射关系变了吗？（组件衰减/扩容/限电类整体位移）
outputs:
  json: y-vs-feature-mapping.json
  png: y-vs-feature-mapping.png
json_schema: >
  split_date（默认中位窗）、每 feature：curve_a/curve_b（pooled 分箱 → y_true
  均值）、mean_shift / mean_abs_shift、n_a/n_b。
bridge_hooks: >
  曲线整体平移（mean_abs_shift 大且各箱同号）→ 物理映射改变类候选——所有模型
  同时受害，与 model-error-correlation 全对高相关联判；仅高值段偏移 → 容量/
  限电类候选。
验证步: 前后期植入 −5 整体位移 → 每箱 shift 精确回收（tests/test_chart_y_vs_feature_mapping.py）
---

# y-vs-feature-mapping：物理映射前后期对比

## 适用问题
误差抬升是"模型退化"还是"世界变了"——映射位移指向后者。要对比训练期 vs
测试期时，由适配器把训练段并入两张长表后用 `--split-date` 指定训练/测试分界。

## CLI 与参数
```bash
python3 chartbook/scripts/chart_y_vs_feature_mapping.py \
  --pred predictions.parquet --features features.parquet \
  --out-dir <workdir>/charts [--split-date 2024-02-01] [--n-bins 8]
```

## JSON schema
见 frontmatter；f 参考值 = f_true 缺则 f_pred（level 口径时位移解释要谨慎）。

## 判读
- `mean_abs_shift` 显著（相对 y 量级 >10%）且各箱同号 → 候选：物理映射整体改变
  ——去 train-test-drift（有 train_y 时）与 rolling-stability 变点交叉定位发生时点；
- 仅个别箱偏移 → 候选：该值域样本构成变化，先查 n_a/n_b 箱内样本量再判读；
- 无位移但误差抬升 → 排除"世界变了"，归因回模型/输入质量侧。
只给候选假设；结论回 playbook 三道门。

## 验证步
见 frontmatter。
