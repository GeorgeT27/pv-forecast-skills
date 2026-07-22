---
id: rolling-stability
needs_materials: [predict, truth]
适用问题: 性能随时间稳不稳？从哪天开始变差？变点前后差多少？不同日历时段有无规律？
outputs:
  json: rolling-stability.json
  png: rolling-stability.png
json_schema: >
  每模型：daily_rmse / rolling_rmse / daily_bias（降采样序列）、changepoints
  （date/before_mean/after_mean/shift）、by_month、by_dayofweek、daily_curve
  （curve_stats，含 max_jump_idx）。
bridge_hooks: >
  存在显著变点且各模型同日变 → 数据侧事件类假设（输入源切换/单元扩容/限电），
  非模型问题；仅单模型变 → 该模型 checkpoint/服务侧类假设；
  by_month 峰值月 → 季节漂移，去 train-test-drift（有 train_y 时）交叉。
验证步: 60 天台阶（第 31 天 1.0→2.0）→ 变点日期/前后均值/shift 精确回收，平坦段零误报（tests/test_chart_rolling_stability.py）
---

# rolling-stability：时间稳定性与变点

## 适用问题
「模型是不是从某天开始变差」的量化；月度归因前先看这张图确认差是突变还是渐变。

## CLI 与参数
```bash
python3 chartbook/scripts/chart_rolling_stability.py \
  --pred predictions.parquet --out-dir <workdir>/charts \
  [--roll-days 7] [--max-cp 3] [--min-shift-frac 0.3] [--min-seg 5]
```

## JSON schema
见 frontmatter。日指标 = 当日各行 row_rmse 的**均值**（行等权），与点级 pool
口径不同——与其他图对数值时只比走势不比绝对值。

## 判读
- `changepoints` 非空且 `daily_curve.max_jump_idx` 紧邻首变点（max_jump_idx 是跳变
  左端点日、变点 date 是后段首日，正常相差一天）→ 台阶型突变，
  候选：外生事件——去 error-breakdown 看该月是否单一单元贡献；
- `changepoints` 空但 `daily_curve.trend == 上升` → 渐变漂移，候选：分布缓慢
  漂移/设备衰减，去 train-test-drift 交叉；
- `by_dayofweek` 有结构（工作日/周末分层）→ 候选：负荷/调度行为混入 y-label；
- 多模型 changepoints 同日 → 数据侧；仅一家 → 模型侧（bridge_hooks）。
只给候选假设；结论回 playbook 三道门。

## 验证步
见 frontmatter；变点检测为贪心二分分段 + `min_shift_frac×std` 幅度闸，
阈值闸有牙由「只报 1 个变点」断言锁定。
