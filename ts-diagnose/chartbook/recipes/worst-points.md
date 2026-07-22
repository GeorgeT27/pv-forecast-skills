---
id: worst-points
needs_materials: [predict, truth]
适用问题: 误差最大的 N 个点是什么性质——极值、转折点(ramp)、还是高波动时段？
outputs:
  json: worst-points.json
  png: worst-points.png
json_schema: >
  每模型：points 列表（target_ts/window_ts/unit/step/y_true/y_pred/err/labels/
  context{abs_dy,local_std,y_quantile}）+ label_share 标签占比。
bridge_hooks: >
  「极值」占比高 → 幅值压缩类假设（RevIN/归一化裁剪），去 true-vs-pred-scatter 看
  高功率段 slope；「转折点」占比高 → 平滑/滞后类假设（模型对 ramp 反应慢）；
  「高波动」占比高 → 高频容量不足类假设（patch 太粗/下采样）。
验证步: 三单元各植入一类点（配误差 5、底噪 0.1；植入统计量为单元内最大值保证过阈值）→ top-3 恰为三点且标签命中（tests/test_chart_worst_points.py）
---

# worst-points：最差点定位与性质标签

## 适用问题
把「误差大」翻译成「误差发生在什么形态的真值上」——error-breakdown 找到最差单元格后，
用本图看单元格内部的点级性质。

## CLI 与参数
```bash
python3 chartbook/scripts/chart_worst_points.py \
  --pred predictions.parquet --out-dir <workdir>/charts \
  [--top-n 20] [--freq 15min] [--pct 0.95] [--vol-window 5]
```

## JSON schema
见 frontmatter。标签阈值均为**单元自身分布**的 pct 分位（跨单元不 pool）；
标签可叠加（一个尖峰点常同时是极值+转折点+高波动），label_share 分母是点数、
分子按标签计，故各标签占比之和可 >1。y_true 以首个模型的序列为准（各模型
y_true 应一致；不一致说明适配器有错，先回对账）。

## 判读
- label_share 由某一类主导（>0.6）→ 对应 bridge_hooks 里的候选机制；
- 三类都不占优、多为「普通」→ 候选：误差非形态驱动（外生事件/数据质量），
  回 error-breakdown 看时间聚集性；
- 同一 target_ts 在多模型的 points 里反复出现 → 候选：输入侧问题（所有模型
  同时受害），有 feature 材料时转 D 组图交叉。
只给候选假设；结论回 playbook 三道门。

## 验证步
见 frontmatter；context 三字段契约（abs_dy/local_std/y_quantile）被测试锁定。
