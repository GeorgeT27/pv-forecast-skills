---
id: worst-slice-compare
category: model-comparison
needs_materials: [predict, truth]
needs_models: 2
适用问题: 模型 A 最差的月份/片上，其他模型表现如何？差距是集中爆发还是普遍落后？该集中超出随机了吗？
outputs:
  json: worst-slice-compare.json
  png: worst-slice-compare.png
json_schema: >
  worst_slice（按焦点模型片 RMSE argmax）、basis（焦点逐片曲线）、overall /
  in_slice（各模型全期/片内指标）、daily_in_slice（片内逐日）、slice_gaps
  （逐片 焦点−最优他模型）、concentration_ratio（最差片 gap 占比，描述量）、
  perm（最差片正差距的按日块置换基线：stat/real_stat/null_q95/perm_p/verdict；
  不适用时为 null 且原因追加在 note）。
bridge_hooks: >
  perm.verdict=significant 且 concentration_ratio→1 且他模型片内不受影响 →
  焦点模型特有机制（架构对该片形态失配），对照 model-profile 桥接假设；
  全模型片内同差 → 数据侧事件，去 rolling-stability 变点与 error-breakdown
  交叉；perm.verdict=not-significant → 集中叙事不成立，不点名切片。
验证步: A 仅 2024-02 植入 3 倍误差 → 最差片、片内数值、gap 集中度 1.0 全回收；8日/月加密版置换基线 significant（perm_p=1/201）；弥散诱饵（各月同幅小差）必须 not-significant（tests/test_chart_worst_slice_compare.py）
---

# worst-slice-compare：最差片同期对比

## 适用问题
「为什么 A 比 B 差」的切片化：先回答差在**哪儿**（集中 or 普遍），再回答该集中
**超出随机了吗**（置换基线）——切片够多时「最差片」必然存在，未过基线不许点名。

## CLI 与参数
```bash
python3 chartbook/scripts/chart_worst_slice_compare.py \
  --pred predictions.parquet --out-dir <workdir>/charts \
  --focal-model <模型名> [--slice-by month] [--n-perm 200] [--perm-seed 0]
```
v1 仅支持按月切片；焦点模型必须在数据里（typo 直接抛错）。置换基线默认开
（200 次、种子 0，两者均落盘进 JSON）；`--n-perm 0` 显式关闭。

## JSON schema
见 frontmatter；片指标 = 片内行 RMSE 均值（与 rolling-stability 同口径）。
置换统计量是**最差片正差距**而非 concentration_ratio——正差稀疏时任意重排的
占比仍近 1（null 退化无检验力）；坏日被打散后片均值被稀释，gap 幅度才有检验力。
按日块整块置换、片日数配额保持；`perm_p = (1+#{null≥real})/(n_perm+1)`。

## 判读
- **先看 `perm.verdict`**：not-significant → 必须写「最差片差距未超随机基线
  （perm_p=…），不点名切片」，切片证据线在 playbook 升级判定中弃权；
  以下条目只在 significant 时适用。
- `concentration_ratio > 0.7` → 差距集中：焦点模型在该片塌方——去该片跑
  worst-points 看点级性质、error-breakdown 看单元贡献；
- `concentration_ratio` 低（各片均摊）→ 普遍落后：候选为全局性机制（容量/
  损失/输入集差异），切片证据不再增益，转 horizon-degradation 与
  true-vs-pred-scatter；
- 片内逐日曲线他模型同步抬升（只是幅度小）→ 候选：共同外因+焦点更敏感。
- 已知局限：按日块置换只抵消日内自相关，月内跨日相关未校正——significant 是
  点名的**必要条件而非充分证明**。
只给候选假设；结论回 playbook 三道门。

## 验证步
见 frontmatter。
