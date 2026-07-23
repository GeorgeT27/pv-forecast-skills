---
id: theil-decomposition
category: error-structure
needs_materials: [predict, truth]
适用问题: 误差是水平偏移(bias)、幅度不匹配(variance)还是形状/错位(covariance)?修法完全不同。
outputs:
  json: theil-decomposition.json
  png: theil-decomposition.png
json_schema: >
  每模型:overall{u_bias,u_var,u_cov,mse}(三者和为 1)+ by_segment(horizon
  三等分 early/mid/late 各一组)+ n;mse≈0 时该组四值为 null 并记 note。
bridge_hooks: >
  u_bias 主导 → 系统性偏移候选(后处理平移可修),与 pp-calibration 的 slope
  截距侧互证;u_var 主导 → 幅度压缩/放大候选,转 true-vs-pred-scatter;
  u_cov 主导 → 形状/时序错位候选,转 time-shift-diagnosis 查时移。
验证步: 纯偏移植入 → u_bias=1;纯幅度失配植入 → u_var=1,精确回收(tests/test_chart_theil_decomposition.py)
---

# theil-decomposition:Theil U 误差三分

## 适用问题
把"误差大"翻译成修复动作:MSE = (ȳp−ȳt)² + (σp−σt)² + 2(1−r)σpσt,
三项占比 u_bias/u_var/u_cov 直接指向平移修正、幅度校准、还是结构问题。

## CLI 与参数
```bash
python3 chartbook/scripts/chart_theil_decomposition.py \
  --pred predictions.parquet --out-dir <workdir>/charts
```

## JSON schema
见 frontmatter;segment 按 horizon_step 三等分(early/mid/late),池化单元与窗口。

## 判读
- `u_bias ≥ 0.5` → 候选:系统性水平偏移——最便宜的修法(输出平移),先查
  by_segment 是否全段一致;
- `u_var ≥ 0.5` → 候选:幅度失配(归一化/容量假设错),与 pp-calibration 互证;
- `u_cov ≥ 0.5` → 误差主要来自"形对不上",转 time-shift-diagnosis 与
  error-acf 找结构;
- 三项均衡 → 无单一主因,回 error-breakdown 先定位坏切片再分解。
只给候选假设;结论回 playbook 三道门。

## 验证步
纯偏移(y_pred=y_true+2,y 随 step 变化)→ overall u_bias=1、其余=0;
纯幅度(y_t=s 均值对齐、y_p=2s−11.5,r=1)→ u_var=1,精确回收。
