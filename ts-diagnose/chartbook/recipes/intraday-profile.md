---
id: intraday-profile
category: error-structure
needs_materials: [predict, truth]
适用问题: 误差集中在一天中的什么时段？系统性高估还是低估、集中在哪个物理时刻？
outputs:
  json: intraday-profile.json
  png: intraday-profile.png
json_schema: >
  每模型：rmse_by_tod / bias_by_tod（curve_stats，索引为目标时刻小时）、worst_hour、
  bias_asymmetry（mean_under/mean_over）、unit_worst_hour（每单元最差时刻）。
bridge_hooks: >
  bias 单向偏移（mean_over ≫ |mean_under| 或反之）→ 系统性标定/损失不对称类假设；
  worst_hour 落在物理过程转换时段（如爬坡）→ 输入变量分辨率/滞后类假设，
  去 error-breakdown 的 unit_hour_rmse 看是否全单元一致。
验证步: 植入 12 时幅度 3（其余 1）→ worst_hour==12.0 且曲线数值精确回收（tests/test_chart_intraday_profile.py）
---

# intraday-profile：日内时段误差剖面

## 适用问题
> ⚠️ 周期性数据专用：本图假设序列存在日周期。无日周期的数据不适用；
> 适不适用由 orient/判读按 intake 的 data_profile 判断。

时段维度的误差定位；与 error-breakdown 的 hour 边际互为印证（本图多出 bias 方向
与不对称度）。

## CLI 与参数
```bash
python3 chartbook/scripts/chart_intraday_profile.py \
  --pred predictions.parquet --out-dir <workdir>/charts [--freq 15min]
```
tod = window_ts + step×freq 的物理时刻，**不是**预报发起时刻。

## JSON schema
见 frontmatter；curve_stats 索引为小时浮点（"11.0"、"11.25"…）。

## 判读
- `bias_by_tod` 全时段同号 → 候选：全局标定偏差（去 true-vs-pred-scatter 看 slope）；
- `bias_by_tod` 峰谷各偏一侧（早升段低估、午后高估）→ 候选：滞后/平滑类机制；
- `rmse_by_tod.argmax` 与 `unit_worst_hour` 不一致（各单元峰值时刻分散）→ 候选：
  单元本地因素主导，去 error-breakdown 的 unit_hour_rmse 交叉；
- roughness 大（剖面毛刺）→ 样本量不足的时段在支配曲线，先查每时段 n 再判读。
只给候选假设；结论回 playbook 三道门。

## 验证步
见 frontmatter；另断言纯正误差时 mean_under==0（无该侧误差记 0 的契约）。
