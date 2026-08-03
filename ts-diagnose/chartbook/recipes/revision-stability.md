---
id: revision-stability
category: temporal-stability
needs_materials: [predict, truth]
适用问题: 对同一目标时刻,随发起窗推进(lead 缩短)预测是收敛到真值还是来回跳?
outputs:
  json: revision-stability.json
  png: revision-stability.png
json_schema: >
  每模型:n_targets(≥2 窗覆盖的目标时刻数)、coverage_hist、smapc(逐对
  翻新 2|Δ|/(|p1|+|p2|) 的均值)、convergence_ratio(最短 lead |err| 均值 /
  最长 lead |err| 均值)、sample_trajectories(≤6 个目标:lead→pred 序列+
  y_true,画刺猬图用)。无任何目标被 ≥2 窗覆盖时抛 ValueError(结构性不适用)。
bridge_hooks: >
  smapc 高且 convergence_ratio≈1 → 翻新抖动不收敛候选(输入翻新噪声直通/
  模型对输入过敏)——有特征对照数据(features 材料)时先查输入翻新是否本身在跳;
  smapc 低但 convergence_ratio≈1 → 稳定地错(系统性偏差),转 theil-decomposition;
  轨迹集体平坦贴均值 → 回归均值塌缩候选,与 pp-calibration 压缩互证。
验证步: 收敛轨迹(每翻新近 1)与跳变轨迹(交替 ±2)双模型 → smapc 排序与 convergence_ratio 阈值回收;单覆盖数据抛 ValueError(tests/test_chart_revision_stability.py)
---

# revision-stability：以目标时刻为锚的翻新稳定性

## 适用问题
长表里同一 target_ts 常被多个发起窗覆盖。「历次预测怎么变」是其他图完全
没利用的轴。三种形态：收敛 = 健康；跳变 = 翻新噪声直通；平坦贴均值 = 塌缩。

## CLI 与参数
```bash
python3 chartbook/scripts/chart_revision_stability.py \
  --pred predictions.parquet --out-dir <workdir>/charts [--freq 15min]
```

## JSON schema
见 frontmatter；lead（步数）= horizon_step；同 (model,unit,target_ts) 按 lead
降序排列构成翻新轨迹。

## 判读
- `smapc` 模型间对比：高者对输入翻新更敏感——有特征对照数据时转特征侧
  翻新分析确认输入是否本身在跳；
- `convergence_ratio < 0.5` → 临近显著变准（正常）；≈1 → 临近不变准，
  lead 信息没被利用或误差是系统性的；
- sample_trajectories 供人工看形态（收敛/跳变/塌缩），数字结论以 smapc 与
  ratio 为准。
只给候选假设；结论回 playbook 三道门。

## 验证步
6 个 1h 间隔发起窗、6 步窗长，中段目标时刻被多窗覆盖。converge 模型
pred=y+lead，每次翻新净变 1；jumpy 模型 pred=y+Δ，lead 为奇取 Δ=+2、
为偶取 Δ=−2，每次翻新跳 4。断言 smapc_jumpy > 2·smapc_converge、
convergence_ratio_converge<0.5；单窗数据（无重叠覆盖）抛 ValueError。
