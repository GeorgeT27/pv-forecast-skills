---
id: cross-dim-stability
needs_materials: [predict, truth]
needs_models: 2
适用问题: A 比 B 好——换时间对半/换口径后方向还成立吗？（多图同源之外的正交稳定性证据）
outputs:
  json: cross-dim-stability.json
  png: cross-dim-stability.png
json_schema: >
  pairs.<other>.time_split（cut_ts/两半窗数/两半配对差 first_half_diff、
  second_half_diff/consistent 两半同号）、caliber_switch（row_diff 行 RMSE
  均值口径差 / pooled_diff 点级 pool 口径差 / consistent 同号）、
  verdict（time_stable / caliber_stable）。
bridge_hooks: >
  time_stable=false → 差距是「半程运气」候选：去 rolling-stability 找变点、
  worst-slice-compare 看是否单片驱动；caliber_stable=false → 少数 horizon
  step 拖爆 pool 口径候选：去 horizon-degradation 看交叉点；两维都稳 →
  差距结构性候选，进 playbook 升级判定。
验证步: 双稳构造（A 恒 0.8 vs B 恒 1.0）两半差与两口径差全 −0.2 精确回收；口径翻转构造（0.8/2.5/0.8 vs 恒 1.5）回收 time_stable=true + caliber_stable=false（tests/test_chart_cross_dim_stability.py）
---

# cross-dim-stability：正交切分稳定性

## 适用问题
「现象→假设」升级的第三条腿：同一份 predictions 派生的多张图属**同一证据维度**，
方向一致只是内部自洽；本图检验差距在两条正交切分（时间对半、口径切换）下是否保持。

## CLI 与参数
```bash
python3 chartbook/scripts/chart_cross_dim_stability.py \
  --pred predictions.parquet --out-dir <workdir>/charts --focal-model <模型名>
```
模型数 <2 抛 ValueError；对 focal 之外每个他模型各出一组配对结果。

## JSON schema
- `pairs.<other>.time_split`：distinct window_ts 排序对半（奇数窗前半多一窗），
  `cut_ts` = 前半末窗；`first/second_half_diff` = 该半区
  mean(row_rmse_focal) − mean(row_rmse_other)；`consistent` = 两半差同号
  （任一为零 → false）。
- `pairs.<other>.caliber_switch`：`row_diff`（行 RMSE 均值口径）与
  `pooled_diff`（点级 pool 口径，全点 sqrt(mean(err²))）同号才 `consistent`。
- `verdict`：`time_stable` / `caliber_stable`。

## 判读
- `time_stable=false` → 总差距是「半程运气」候选：禁升假设，去 rolling-stability
  看变点、worst-slice-compare 看是否单片驱动；
- `caliber_stable=false` → 结论限定口径（「A 更好」只在行均值口径成立），去
  horizon-degradation 看是否少数 step 拖爆 pool 口径；
- 两维都稳 ≠ 独立数据验证——仍是同一份数据的重切分；「已证实」层级照旧要走
  playbook 三道门之门 2（先预测后看数）或外部实验。
只给候选假设；结论回 playbook 三道门。

## 验证步
见 frontmatter。
