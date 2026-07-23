---
id: oracle-gap
needs_materials: [predict, truth]
needs_models: 2
适用问题: 逐样本动态选最优模型能提升多少？现有 ensemble 吃满互补性了吗？谁最常是最优？
outputs:
  json: oracle-gap.json
  png: oracle-gap.png
json_schema: >
  mean_rmse（各模型+oracle）、best_single_minus_oracle、ensemble_minus_oracle
  （无 ensemble 记 null）、oracle_pick_share、daily_rmse（各模型+oracle 逐日，降采样）、
  n_samples。
bridge_hooks: >
  gap 大且 pick_share 分散 → 互补性真实存在（与 model-error-correlation 低相关
  联判）；gap 大但 pick_share 一边倒 → 弱模型只在少数场景赢，查那些场景
  （worst-slice-compare）；ensemble−oracle ≈ best_single−oracle → 组合器没学到
  选择能力。
验证步: 双模型前后半期互为最优 → oracle 均值 1.0、gap 0.5、pick_share 0.5/0.5 回收（tests/test_chart_oracle_gap.py）
---

# oracle-gap：动态选优提升空间

## 适用问题
模型对比的收尾图：对比不是为了排名，是为了决定「换模型/组合/维持」——本图给
组合路线的收益上界。

## CLI 与参数
```bash
python3 chartbook/scripts/chart_oracle_gap.py \
  --pred predictions.parquet --out-dir <workdir>/charts [--ensemble-key ensemble]
```
oracle 是**事后**下界（作弊线），不是可部署策略——判读措辞里必须带这句。

## JSON schema
见 frontmatter；样本 = (unit, window) 对齐行（缺任一模型即 drop）。

## 判读
- `best_single_minus_oracle` 占 best_single 的比例 >15% → 候选：互补显著，
  组合路线值得投入——与 model-error-correlation 的低相关交叉后升「假设」；
- `oracle_pick_share` 某模型 <5% → 候选：该模型几乎无场景增益（下线候选），
  但先查它是否在特定片独赢（worst-slice-compare）；
- `daily_rmse` 里 oracle 与最优单模型曲线基本重合的时段 → 该时段无组合空间。
只给候选假设；结论回 playbook 三道门。

## 验证步
见 frontmatter。
