---
id: bad-window-clustering
category: sample-contrast
needs_materials: [predict, truth]
适用问题: 坏样本是一种失败模式还是几种?各占多少?
outputs:
  json: bad-window-clustering.json
  png: bad-window-clustering.png
json_schema: >
  每模型:top_n、chosen_k、silhouette_by_k、seed、clusters[{share, n,
  mean_rmse, prototype(归一化质心曲线,≤24 点)}]。簇不做领域命名——质心
  形状事实归 JSON,命名交运行时判读结合 intake 背景。
bridge_hooks: >
  单簇占比 ≥0.8 → 单一失败模式候选,对照 worst-points 标签看是哪类形态;
  多簇均衡 → 多机制并存,逐簇回 error-breakdown 查时间聚集;某簇 mean_rmse
  显著更高 → 优先攻那一簇。
验证步: 植入升/降两种确定形状的坏窗 → chosen_k=2、成员精确分离、share 各 0.5(tests/test_chart_bad_window_clustering.py)
---

# bad-window-clustering：worst-N 窗口形态聚类

## 适用问题
worst-points 给「点」贴标签，本图对「整窗曲线」做聚类。它回答：坏样本的
真值形态是一种失败模式，还是好几种？答案决定要修一个机制还是修几个。

## CLI 与参数
```bash
python3 chartbook/scripts/chart_bad_window_clustering.py \
  --pred predictions.parquet --out-dir <workdir>/charts \
  [--top-n 50] [--seed 0]
```
k 在 2..4 由轮廓系数选；seed 显式落 JSON（_recipe-spec §5.3 种子例外）。

## JSON schema
见 frontmatter；每窗曲线 z 归一化（σ≈0 的平坦窗跳过并计入 skipped_flat），
曲线重采样到 ≤24 点后聚类。

## 判读
- 本图强制 k≥2，不会产出「chosen_k=1」；silhouette（轮廓系数，衡量聚类
  分离质量）全低时也一样。想判「单一失败模式」，看 share 是否极不均衡（≥0.8）；
- 各簇 prototype 的形状差异（升/降/尖峰）用 curve 数字描述，领域命名结合
  intake 背景在判读层给；
- 簇间 mean_rmse 差异大 → 优先修误差最重的簇对应机制。
只给候选假设；结论回 playbook 三道门。

## 验证步
12 个坏窗（误差幅度 5）：6 窗 y=s 升形 + 6 窗 y=23−s 降形；8 个好窗(0.1)
→ top-12 恰为坏窗、chosen_k=2、两簇成员精确分离、share 各 0.5。
