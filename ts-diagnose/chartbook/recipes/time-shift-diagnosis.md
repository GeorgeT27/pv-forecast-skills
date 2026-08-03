---
id: time-shift-diagnosis
category: error-structure
needs_materials: [predict, truth]
适用问题: 预测曲线是不是整体提前/滞后了几步?(形状对、对时错)
outputs:
  json: time-shift-diagnosis.json
  png: time-shift-diagnosis.png
json_schema: >
  每模型:shift_hist(各平移步数的窗口计数)、mode_shift(众数)、
  share_nonzero(最优平移≠0 的窗口占比)、mean_abs_shift、n_windows、
  max_shift(搜索半径)。shift>0=预测滞后(晚),<0=超前。
bridge_hooks: >
  mode_shift≠0 且 share_nonzero 高 → 系统性对时错位候选(输入时间基准/
  时区/发布延迟类),与 theil-decomposition 的 u_cov 主导互证;shift 集中 0
  但 u_cov 仍高 → 非平移型形状失配,转 error-acf/worst-points。
验证步: y_pred=y_true 平移 2 步(非线性周期形)→ mode_shift=2、share_nonzero=1 精确回收(tests/test_chart_time_shift_diagnosis.py)
---

# time-shift-diagnosis：逐窗最优时移分布

## 适用问题
逐点误差大而形状描述符都正常时，第一个该排查的就是「对时错位」——整体
提前/滞后 k 步会造出大 RMSE 却完全可修（对齐输入时间基准）。

## CLI 与参数
```bash
python3 chartbook/scripts/chart_time_shift_diagnosis.py \
  --pred predictions.parquet --out-dir <workdir>/charts [--max-shift 8]
```

## JSON schema
见 frontmatter；每 (model,unit,window) 求 k* = argmin_k MSE(y_pred[t], y_true[t−k])，
k ∈ [−max_shift, max_shift]，重叠段 < 8 点的窗口跳过并计入 skipped。

## 判读
- `mode_shift ≠ 0` 且 `share_nonzero ≥ 0.7` → 候选：系统性对时错位——查数据
  管道时间基准（采样对齐/时区/发布延迟），修好即免费收益；
- shift 分布双峰/弥散 → 候选：间歇性延迟（部分批次晚到），回 error-breakdown
  看时间聚集；
- 全部 ≈0 → 排除平移型错位，u_cov 高时转非平移形状假设。
只给候选假设；结论回 playbook 三道门。

## 验证步
y 为周期 8 的确定性正弦形，y_pred 恰为 y_true 平移 2 步 → 每窗 k*=2 唯一，
mode_shift=2、share_nonzero=1.0、mean_abs_shift=2 精确回收；零平移对照 mode=0。
