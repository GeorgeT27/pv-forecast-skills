---
id: error-breakdown
category: error-structure
needs_materials: [predict, truth]
适用问题: 什么单元(站点)什么时候 RMSE 最大？误差集中在哪些月/时段/horizon 带？
outputs:
  json: error-breakdown.json
  png: error-breakdown.png
json_schema: >
  每模型：unit_month_rmse / unit_hour_rmse / unit_band_rmse 三个矩阵、
  argmax_cell（最差单元格+数值+样本量）、per_unit_rmse、per_month 与 per_hour
  边际 curve_stats、top_worst 前 K 组合。
bridge_hooks: >
  单一单元格独大（argmax 显著高于 top_worst 次位）→ 局部事件/数据质量类假设；
  某月整行同衰（per_month max_jump 大）→ 季节/分布漂移类假设，去 train-test-drift 交叉；
  band3 独差 → 长 horizon 衰减，去 horizon-degradation 交叉。
验证步: 植入 (U2, 2024-02) 幅度 3（其余 1）→ argmax_cell 与 Top-K 必须回收（tests/test_chart_error_breakdown.py）
---

# error-breakdown：单元×日历×horizon 误差分解

## 适用问题
y-label 误差「谁、什么时候、错在哪」的第一张图；A 组入口，几乎所有 playbook 的
事实阶段都该先看它。

## CLI 与参数
```bash
python3 chartbook/scripts/chart_error_breakdown.py \
  --pred predictions.parquet --out-dir <workdir>/charts [--freq 15min] [--top-k 10]
```
`--freq`：horizon 步长（目标时刻 = window_ts + step×freq，hour 维度据此算）。

## JSON schema
见 frontmatter json_schema；所有 RMSE 为点级 sqrt(mean(err²))，跨单元格可比；
n 为单元格样本量（判读时先看 n，样本 < 100 的单元格不下断言）。

## 判读
- `argmax_cell` 与 `top_worst` 断层大（首位 ≫ 次位）→ 候选：局部事件（限电/检修/
  数据缺陷）——去 worst-points 看该单元格内点级标签交叉验证；
- `per_month.curve` 整体抬升某月 → 候选：分布漂移——有 train_y 材料时去
  train-test-drift 交叉；
- `per_hour` 峰值时段 → 候选：日内物理过程（如爬坡时段）——去 intraday-profile
  看 bias 方向；
- `unit_band_rmse` 仅 band3 高 → 候选：长程衰减——去 horizon-degradation 看斜率。
只给候选假设；结论回 playbook 三道门。

## 验证步
合成 2 单元×3 月、幅度植入见 frontmatter；断言 argmax、边际 argmax、Top-K 排序、
非植入格数值恰为 1。
