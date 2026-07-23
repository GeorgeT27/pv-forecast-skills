---
id: baseline-skill
category: model-comparison
needs_materials: [predict, truth]
适用问题: 模型比"抄上次/抄同相位/抄均值"好多少?有没有模型退化成抄 persistence?
outputs:
  json: baseline-skill.json
  png: baseline-skill.png
json_schema: >
  period_steps(来源:CLI 或 ACF 自动检测,null=无周期)、baselines{persistence/
  seasonal_naive?/climatology: rmse}、每模型{rmse, skill_vs_persistence,
  skill_vs_seasonal?, skill_vs_climatology, corr_with_truth,
  corr_with_persistence, dist_to_persistence, copies_persistence(bool)}、
  n_scored(基线可算的行数)。
bridge_hooks: >
  skill≤0 的模型 → 不如朴素基线,存在性存疑——查它是不是 copies_persistence
  (dist_to_persistence < 0.5×自身误差 RMSE,即离基线比离真值近一倍以上);
  全模型 skill 都低 → 该数据可预测上限本身低(与 oracle-gap 互证);seasonal
  skill 高但 persistence skill 低 → 模型只学到了周期形。
验证步: 一模型恰等于季节朴素 → skill_vs_seasonal=0;半误差模型 → 0.5;抄 persistence 模型 → copies_persistence=true(tests/test_chart_baseline_skill.py)
---

# baseline-skill:朴素基线技能阶梯

## 适用问题
全图库唯一的朴素参照系:skill = 1 − RMSE_model/RMSE_baseline。回答"模型
值不值得存在"以及"深度模型是否退化成抄 persistence"。

## CLI 与参数
```bash
python3 chartbook/scripts/chart_baseline_skill.py \
  --pred predictions.parquet --out-dir <workdir>/charts \
  [--period-steps 96] [--freq 15min]
```
period 未给时用 detect_period_steps 对真值序列自动检测;检测不到 →
seasonal 基线缺省(JSON 记 null),只算 persistence 与 climatology。

## JSON schema
见 frontmatter;真值全局序列按 target_ts=window_ts+step·freq 建;persistence
基线 = 发起时刻真值 y(window_ts);seasonal = y(target−period);climatology =
全局均值。基线值缺失的行跳过,分母为 n_scored。

## 判读
- `skill_vs_persistence ≤ 0` → 候选:模型无增值——先查 copies_persistence
  (预测到 persistence 基线的 RMSE < 0.5×自身(同行)误差 RMSE),是则模型在
  "抄输入",转 revision-stability 看翻新形态;
- persistence skill 低而 seasonal skill 高 → 只学到周期形,突变段必差,
  与 worst-points 的转折占比互证;
- 全模型 skill 均低且 oracle-gap 也小 → 数据可预测上限低,不是模型问题。
只给候选假设;结论回 playbook 三道门。

## 验证步
y=100·widx+s(日间水平位移+日内斜坡)、period=24 显式传入 → 抄 seasonal 的
模型 skill_vs_seasonal=0;误差减半模型 =0.5;恰抄 persistence 的模型
copies_persistence=true。
