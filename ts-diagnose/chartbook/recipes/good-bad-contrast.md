---
id: good-bad-contrast
category: sample-contrast
needs_materials: [predict, truth, features]
适用问题: 预测最坏的窗口和最好的窗口,输入特征与上下文有什么系统性差别?
outputs:
  json: good-bad-contrast.json
  png: good-bad-contrast.png
json_schema: >
  每模型:k(每组窗口数)、features{名: {basis(quality|level), d(Cohen), ks, p,
  mean_best, mean_worst, direction}}(按 |d| 降序的 ranked 列表)、context
  (y_level/volatility/window_hour 三个通用协变量的同款对比)。f_true 全缺时
  basis 自动降级 level。
bridge_hooks: >
  某特征 quality 基 |d|≥0.8 且 KS p 小 → 该输入质量与坏样本强关联候选——
  与 feature-error-conditional 的 effect_ratio 交叉,两线一致才升假设;
  所有特征 |d| 都小但 context.volatility 分离 → 误差由目标自身动力学驱动
  (输入无辜),转 bad-window-clustering 看失败形态。
验证步: worst 组植入质量差 d≈2 真凶 + 两组同分布诱饵 → 真凶居 ranked 首、诱饵 |d|<0.2(tests/test_chart_good_bad_contrast.py)
---

# good-bad-contrast：best-K vs worst-K 特征对照

## 适用问题
直接回答「坏样本的特征有什么特性、好样本有什么特质」。做法：按行 RMSE
取两端各 K 窗，逐特征对比三层——量值分布、预测质量（有 f_true 时）、
通用上下文。

## CLI 与参数
```bash
python3 chartbook/scripts/chart_good_bad_contrast.py \
  --pred predictions.parquet --features features.parquet \
  --out-dir <workdir>/charts [--k 50]
```
k 默认 min(50, ⌈10% 行数⌉)，不足 5 时抛 ValueError（样本太少不出对比）。

## JSON schema
见 frontmatter；每行（窗口）的特征 level=窗内 f_pred 均值、quality=窗内
|f_pred−f_true| 均值；d=(mean_worst−mean_best)/pooled_std；direction=d 的符号。

## 判读
- ranked 首位特征 basis=quality 且 |d|≥0.8 → 候选：该输入的预测质量分辨
  好坏样本——回 feature-error-conditional 看全局耦合是否同证；
- basis=level 的高 |d| 只说明「坏样本发生在该特征的某值域」（如高值段），
  是条件不是罪证——转 feature-regime-error 看制式；
- context 三项都分离而特征不分离 → 目标自身难度驱动，转 bad-window-clustering。
只给候选假设；结论回 playbook 三道门。

## 验证步
真凶特征在 worst 组 quality≈4、best 组≈0.5（合成 σ 使 d≈2）；诱饵特征两组
同分布(d≈0)→ ranked[0]=真凶且 d≥1.5、诱饵 |d|<0.2 必须不上榜前二。
