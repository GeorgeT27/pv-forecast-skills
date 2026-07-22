---
id: worst-slice-compare
needs_materials: [predict, truth]
适用问题: 模型 A 最差的月份/片上，其他模型表现如何？A 的差距是集中爆发还是普遍落后？
outputs:
  json: worst-slice-compare.json
  png: worst-slice-compare.png
json_schema: >
  worst_slice（按焦点模型片 RMSE argmax）、basis（焦点逐片曲线）、overall /
  in_slice（各模型全期/片内指标）、daily_in_slice（片内逐日）、slice_gaps
  （逐片 焦点−最优他模型）、concentration_ratio（最差片 gap 占比）。
bridge_hooks: >
  concentration_ratio→1 且他模型片内不受影响 → 焦点模型特有机制（架构对该片
  形态失配），对照 model-profile 桥接假设；全模型片内同差 → 数据侧事件，
  去 rolling-stability 变点与 error-breakdown 交叉。
验证步: A 仅 2024-02 植入 3 倍误差 → 最差片、片内数值、gap 集中度 1.0 全回收（tests/test_chart_worst_slice_compare.py）
---

# worst-slice-compare：最差片同期对比

## 适用问题
「为什么 A 比 B 差」的切片化：先回答差在**哪儿**（集中 or 普遍），再谈为什么。

## CLI 与参数
```bash
python3 chartbook/scripts/chart_worst_slice_compare.py \
  --pred predictions.parquet --out-dir <workdir>/charts \
  --focal-model <模型名> [--slice-by month]
```
v1 仅支持按月切片；焦点模型必须在数据里（typo 直接抛错）。

## JSON schema
见 frontmatter；片指标 = 片内行 RMSE 均值（与 rolling-stability 同口径）。

## 判读
- `concentration_ratio > 0.7` → 差距集中：焦点模型在该片塌方——去该片跑
  worst-points 看点级性质、error-breakdown 看单元贡献；
- `concentration_ratio` 低（各片均摊）→ 普遍落后：候选为全局性机制（容量/
  损失/输入集差异），切片证据不再增益，转 horizon-degradation 与
  true-vs-pred-scatter；
- 片内逐日曲线他模型同步抬升（只是幅度小）→ 候选：共同外因+焦点更敏感。
只给候选假设；结论回 playbook 三道门。

## 验证步
见 frontmatter。
