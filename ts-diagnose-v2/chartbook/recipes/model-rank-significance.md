---
id: model-rank-significance
category: model-comparison
needs_materials: [predict, truth]
needs_models: 2
适用问题: 模型排名的差异是真差异还是噪声?哪些模型统计上不可区分?
outputs:
  json: model-rank-significance.json
  png: model-rank-significance.png
json_schema: >
  avg_ranks(每模型平均秩,损失=行 RMSE,秩按行取、并列取均秩)、cd
  (Nemenyi 临界差,α=0.05)、groups(秩差≤cd 的不可区分组,含最优组
  best_group)、dm(成对{stat,p};损失差按 window_ts 排序、Newey-West HAC
  方差,d 恒 0 时 p=1、方差退化且均值≠0 时 p=0 并记 degenerate)、n_rows。
bridge_hooks: >
  焦点模型与次优在同一 group 且 dm p 大 → 排名差异不可靠,结论只能说
  "无显著差异"——喂给 model-comparison playbook 的准入门;分离显著 →
  差距真实,转 worst-slice-compare 查差在哪。
验证步: 恒 3 倍误差对 → dm p<0.05 且秩分离;同款模型对 → 同组且 p=1(tests/test_chart_model_rank_significance.py)
---

# model-rank-significance：平均秩 + 临界差 + DM 检验

## 适用问题
多模型对比的最后一道统计门。平均秩差超过 Nemenyi 临界差（多模型两两
比较的显著性阈值）才算「排名可信」。成对 DM 检验（Diebold-Mariano，
检验两模型损失差是否显著）给逐对 p 值；其 HAC 方差估计能容忍误差自相关。

## CLI 与参数
```bash
python3 chartbook/scripts/chart_model_rank_significance.py \
  --pred predictions.parquet --out-dir <workdir>/charts
```
< 2 模型抛 ValueError(§5.5)。

## JSON schema
见 frontmatter；损失矩阵 = 每 (unit_id,window_ts) 行的行 RMSE，只保留全模型
齐的行；Nemenyi q_α 表内置 k=2..10。

## 判读
- best_group 只有一个成员且它对第二名 dm p<0.05 → 排名可信，可下「谁最优」；
- best_group 多成员 → 只能说「这几个不可区分地并列最优」，禁止点单一冠军；
- dm.degenerate 出现 → 损失差没有变化（克隆/恒差），对照数据核实而非下结论。
只给候选假设；结论回 playbook 三道门。

## 验证步
A 恒 1 倍、B 恒 3+0.5·(widx%2) 倍误差 → 每行 A 胜，avg_rank A=1、B=2，
40 窗下秩差 1 > cd≈0.31，dm p<0.05；C 与 D 同款（恒同损失）→ 同组、p=1。
