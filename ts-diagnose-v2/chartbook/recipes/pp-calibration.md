---
id: pp-calibration
category: error-structure
needs_materials: [predict, truth]
适用问题: 预测的取值分布与真值分布对齐吗?模型是否系统性压缩高值/抬高低值(归一化副作用)?
outputs:
  json: pp-calibration.json
  png: pp-calibration.png
json_schema: >
  每模型:quantiles(q/y_true_q/y_pred_q/ratio 列表)、slope(分位数对 OLS 斜率)、
  high_tail_ratio(q95_pred/q95_true)、low_tail_ratio(q05 同理,分母近 0 时 null)、n。
bridge_hooks: >
  slope<1 且 high_tail_ratio 明显<1 → 幅值压缩类候选(归一化/裁剪副作用),
  与 true-vs-pred-scatter 高值段 slope 交叉;slope≈1 但尾部比值偏离 → 仅尾部
  失真,转 horizon-error-quantiles 看误差分布形态。
验证步: 植入 y_pred=0.8·y_true → slope 与两尾比值精确回收 0.8(tests/test_chart_pp_calibration.py)
---

# pp-calibration：分位数-分位数校准

## 适用问题
边缘分布层面的校准：不看逐点误差，看「预测值的分布」与「真值的分布」是否同形。
系统性压缩/抬升在散点图上易被点云掩盖，分位数对上一目了然。

## CLI 与参数
```bash
python3 chartbook/scripts/chart_pp_calibration.py \
  --pred predictions.parquet --out-dir <workdir>/charts
```

## JSON schema
见 frontmatter；分位点固定 q ∈ {0.01,0.05,0.1,...,0.9,0.95,0.99}（0.1 步进主体）；
ratio = y_pred_q / y_true_q，|y_true_q| < 1e-9 时该点 ratio 为 null。

## 判读
- `slope < 0.9` 且 `high_tail_ratio < 0.9` → 候选：整体幅值压缩——去
  true-vs-pred-scatter 看高值段是否同证；
- 两尾比值一高一低 → 候选：分布被「往中间挤」（过平滑），转 worst-points 看
  极值点占比；
- slope≈1、尾比≈1 但误差仍大 → 分布对齐、逐点错位，转 time-shift-diagnosis。
只给候选假设；结论回 playbook 三道门。

## 验证步
golden 植入 y_pred = 0.8·y_true（y 随 step 变化保证分位数非退化）→
slope、high_tail_ratio、low_tail_ratio 全部精确回收 0.8。
