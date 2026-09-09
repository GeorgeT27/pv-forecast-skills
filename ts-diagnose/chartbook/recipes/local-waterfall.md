---
id: local-waterfall
category: attribution
needs_materials: [predict, truth, features, serving_api]
适用问题: 误差最大的那几行,分别是哪些输入特征贡献的?各占多少?
outputs:
  json: local-waterfall.json
  png: local-waterfall.png
json_schema: >
  每行(worst-K):unit/window/rmse_actual、base_value(全参考输入时的行
  RMSE)、contributions{特征: Shapley 贡献}、check_sum(base+Σφ,应≈实际
  RMSE——效率性自检)、basis{特征: f_true|background}。顶层:k、
  background_meta(basis=background 时)、explainer、seed、coverage。
bridge_hooks: >
  多数坏行由同一特征主导 → 该输入系统性拖累,与 good-bad-contrast 的
  分离度、feature-error-conditional 的耦合比值三线互证后才升假设;
  各行主导特征不同 → 无单一元凶,回 bad-window-clustering 看失败模式分簇;
  φ 大但该特征 f_true 缺 → basis=background 的贡献解释要降级(背景不是真值)。
验证步: 线性适配器+固定偏差植入 → φ 解析精确回收(6/1/0),零系数大偏差诱饵 φ=0 不被冤枉;check_sum 效率性闭合(tests/test_chart_local_waterfall.py)
---

# local-waterfall：单行 Shapley 瀑布

## 适用问题
「这行为什么这么差」的量化拆账。mask=1 时特征用实际输入（f_pred），
mask=0 时用参考输入（f_true，缺则用背景序列）。在这套开关下，Shapley
值把行 RMSE 拆到各特征头上。

## CLI 与参数
```bash
python3 chartbook/scripts/chart_local_waterfall.py \
  --pred predictions.parquet --features features.parquet \
  --adapter analysis_scripts/predict_adapter.py \
  --out-dir <workdir>/charts [--k 20] [--model auto] \
  [--background-k 5] [--seed 0] [--max-calls 5000] [--metric rmse|mse]
```
`--metric`：逐行口径，`rmse`（默认）或 `mse`。**分析主口径不是逐行 RMSE 时必须跟着切**——逐行 RMSE 与逐行 MSE 的模型排名可以相反，不切就等于用另一个口径的图去支撑本次结论。口径写进 JSON 的 `metric` 字段。

适配器需 perturb_features=True；D≤8 全枚举精确。

## JSON schema
见 frontmatter；worst-K 按焦点模型行 RMSE 降序；PNG 取前 ≤6 行画瀑布网格。

## 判读
- 单特征 φ 占 check_sum 的 ≥60% → 该行的主导元凶候选——但**单行=样本量 1**，
  点名须与全局线（good-bad-contrast / feature-error-conditional）交叉；
- φ 为负的特征 → 该输入实际在「救」这行（替换成参考反而更差），不是元凶；
- check_sum 与 rmse_actual 偏差 >5% → 强交互效应存在，单特征拆账要谨慎
  （JSON 如实给出，不隐藏）。
只给候选假设；结论回 playbook 三道门。

## 验证步
线性适配器（系数 3/1/0）+ 特征偏差植入（fa 偏 2、fb 偏 1、fc 偏 5 但系数 0）。
同号常量偏差下贡献可加：φ_a=6、φ_b=1、φ_c=0 精确回收。fc 是「大偏差但
无影响」的防冤枉诱饵。base_value=0、check_sum=7 闭合。
