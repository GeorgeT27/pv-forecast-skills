---
id: true-vs-pred-scatter
needs_materials: [predict, truth]
适用问题: 预测系统性偏低/偏高？大值段被压低？误差是「不齐」还是「不正」？
outputs:
  json: true-vs-pred-scatter.json
  png: true-vs-pred-scatter.png
json_schema: >
  每模型：slope / intercept / r2 / n / true_max / pred_max、pred_by_true_bin
  （真值分位箱均值→预测均值）、resid_quantiles_by_bin（每箱残差 p10/p50/p90）。
bridge_hooks: >
  slope<1 且压低集中高段 → 幅值压缩类假设（归一化/RevIN 反变换、损失对大值欠罚）；
  slope≈1 而 R² 低 → 时序错位类假设（相位/滞后），去 worst-points 看转折点占比；
  intercept 显著非 0 → 基线偏置类假设。
验证步: 无噪声 y_pred=0.8y+0.5 → slope/intercept 精确回收、R²>0.9999、分箱单调（tests/test_chart_true_vs_pred_scatter.py）
---

# true-vs-pred-scatter：真值-预测回归诊断

## 适用问题
判读纪律：**R² 管齐不齐、slope 管正不正**——两者解耦，别混着下结论。

## CLI 与参数
```bash
python3 chartbook/scripts/chart_true_vs_pred_scatter.py \
  --pred predictions.parquet --out-dir <workdir>/charts [--n-bins 10]
```

## JSON schema
见 frontmatter；y_true 无方差时抛错（适配器填错列的常见症状，先回对账）。

## 判读
- `slope < 1`、`resid_quantiles_by_bin` 高段 p50 显著为负 → 候选：大值压低——
  对照 worst-points 的「极值」标签占比交叉；
- `r2` 低、slope≈1 → 候选：错位/离散——非幅值问题，去 intraday-profile 看
  bias 时段结构；
- 各模型 slope 都 <1 且接近 → 候选：共同的标签/输入侧原因，非单模型缺陷；
- `pred_by_true_bin` 在某箱折弯 → 候选：该功率段训练样本稀疏。
只给候选假设；结论回 playbook 三道门。

## 验证步
见 frontmatter。
