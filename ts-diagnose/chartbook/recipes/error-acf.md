---
id: error-acf
category: error-structure
needs_materials: [predict, truth]
适用问题: 误差序列里还有可预测结构吗?(持续性偏差=漏了慢变量/可后处理修正)
outputs:
  json: error-acf.json
  png: error-acf.png
json_schema: >
  每模型:窗口级序列(每窗均值误差,按 window_ts 排序)的 acf(lag 1..L 曲线)、
  argmax_lag、acf1、ljung_box{stat,p,lags}、n。多步预测纪律:窗口重叠时
  低阶自相关天然存在(h 步最优残差为 MA(h−1)),判读只对超出重叠尺度的
  lag 下断言,note 记窗口步数。
bridge_hooks: >
  acf 在某 lag 有孤立峰 → 周期性残余候选(漏了该周期的驱动变量),与
  intraday-profile 的时段剖面互证;acf1 高且缓衰减 → 慢变量缺失/水平漂移
  候选,转 rolling-stability 看变点;全 lag ≈0 → 误差近白噪,系统性成分已榨干。
验证步: 逐窗均值误差植入周期 8 的余弦 → argmax_lag=8、acf[8]≥0.75、Ljung-Box p<0.01(tests/test_chart_error_acf.py)
---

# error-acf：窗口级误差自相关

## 适用问题
误差是「白噪声」还是「有结构」直接决定两件事：还能不能免费改进（后处理
校正），以及模型是否漏了慢变量/周期变量。

## CLI 与参数
```bash
python3 chartbook/scripts/chart_error_acf.py \
  --pred predictions.parquet --out-dir <workdir>/charts [--max-lag 12]
```

## JSON schema
见 frontmatter。序列 = 每个 window_ts 上全模型行的均值误差（单元池化），
按时间排序。Ljung-Box（检验序列整体是否白噪声的 χ² 检验）在 lag 1..L 上算，
p 值落 JSON。

## 判读
- `argmax_lag = P` 且 `acf[P]` 显著 → 候选：周期 P 的残余结构——对照
  数据背景确认 P 对应什么物理周期，该周期驱动变量缺失或用错；
- `acf1 ≥ 0.5` 且缓衰减 → 候选：慢变量缺失/概念漂移，转 rolling-stability；
- **窗口重叠纪律**：相邻窗口共享真值区间时低阶 lag 自相关是结构必然，
  不做病灶断言——只看超出重叠尺度的 lag。
只给候选假设；结论回 playbook 三道门。

## 验证步
40 窗、逐窗常数误差 = 3·cos(2π·widx/8)（窗内各步同值，窗间余弦周期 8）→
acf argmax_lag=8、acf[8]≈(n−8)/n=0.8、Ljung-Box p<0.01。
