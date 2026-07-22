---
id: horizon-degradation
needs_materials: [predict, truth]
适用问题: 短期准长期崩？退化速度谁快？哪个单元在长 horizon 崩溃？模型排序在哪个步反转？
outputs:
  json: horizon-degradation.json
  png: horizon-degradation.png
json_schema: >
  每模型：rmse_by_step / bias_by_step（curve_stats）、early_slope / late_slope；
  全局：crossings（模型对→首个排序反转步）、collapse_horizon（模型→单元→崩溃步）。
bridge_hooks: >
  晚段斜率陡且早段平 → 长程依赖衰减类假设（attention 有效窗口/位置编码外推）；
  开头台阶（max_jump_idx 靠前）→ 起报对齐/输入延迟类假设；
  roughness 大（毛刺）→ 高频分量拟合类假设；交叉点存在 → 「哪个模型好」
  依赖考核 horizon 段——先问口径再下对比结论。
验证步: 解析式双模型（平坦+折线 vs 缓降）→ 早晚斜率、交叉步 31、崩溃步 30 精确回收（tests/test_chart_horizon_degradation.py）
---

# horizon-degradation：误差随预报时效退化

## 适用问题
「模型 A 比 B 好」是否随 horizon 反转；长期失效从哪一步开始、哪些单元先崩。

## CLI 与参数
```bash
python3 chartbook/scripts/chart_horizon_degradation.py \
  --pred predictions.parquet --out-dir <workdir>/charts \
  [--early-frac 0.25] [--late-frac 0.25] [--collapse-mult 1.5]
```

## JSON schema
见 frontmatter。崩溃点基准是**该单元该模型自身早段均值**——跨模型只比崩溃步的
排名/有无，不比数值（量纲纪律）。

## 判读
- `late_slope ≫ early_slope`（如 >5×）→ 候选：长程依赖衰减，有 model_code 材料时
  对照架构桥接假设（H-ID）验证；
- `crossings` 非空 → 候选：结论依赖口径——回 Stage 0 确认考核 horizon 段再比；
- `collapse_horizon` 集中在少数单元 → 候选：单元本地可预测性差，去
  error-breakdown 的 unit_band_rmse 交叉；
- `bias_by_step.trend == 上升/下降`（单调漂移）→ 候选：递推累积偏差类机制。
只给候选假设；结论回 playbook 三道门。

## 验证步
见 frontmatter；斜率用早/晚各 25% 段最小二乘，容差 1e-9/精确浮点。
