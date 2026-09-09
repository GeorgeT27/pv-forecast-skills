---
id: model-error-correlation
category: model-comparison
needs_materials: [predict, truth]
needs_models: 2
适用问题: 多个模型是同质还是互补？组合/动态选模有没有空间？谁和谁犯同样的错？
outputs:
  json: model-error-correlation.json
  png: model-error-correlation.png
json_schema: >
  corr.all 全周期相关矩阵（--by-month 时另有逐月矩阵）、most_complementary /
  most_redundant（模型对+相关值）、n_samples。
bridge_hooks: >
  全对高相关（>0.95）→ 共享输入/共享标签缺陷类假设（错在数据不在模型）；
  某对独低 → 架构差异真实有效，对照 model-profile 上下文的架构差异点；
  逐月相关骤变月 → 该月外生事件，去 rolling-stability 变点交叉。
验证步: 三模型植入 A≡B、C 正交 → corr(A,B)=1、corr(A,C)=0、最同质/最互补对回收（tests/test_chart_model_error_correlation.py）
---

# model-error-correlation：模型同质化/互补性

## 适用问题
模型对比归因的前置事实：差距是「一个更强」还是「各错各的」——后者才有组合空间。

## CLI 与参数
```bash
python3 chartbook/scripts/chart_model_error_correlation.py \
  --pred predictions.parquet --out-dir <workdir>/charts [--by-month] [--metric rmse|mse]
```
`--metric`：逐行口径，`rmse`（默认）或 `mse`。**分析主口径不是逐行 RMSE 时必须跟着切**——逐行 RMSE 与逐行 MSE 的模型排名可以相反，不切就等于用另一个口径的图去支撑本次结论。口径写进 JSON 的 `metric` 字段。

样本 = (unit, window) 的行 RMSE；各模型须对齐（缺任一模型的样本被 drop）。

## JSON schema
见 frontmatter；n_samples 是对齐后样本量，先看它够不够（<30 不下断言）。

## 判读
- 所有对 >0.95 → 候选：同质化——ensemble 增益有限；差距归因应转向数据/标签侧；
- `most_complementary.corr` < 0.5 → 候选：互补——去 oracle-gap 量化动态选模空间；
- 与 oracle-gap 的 pick_share 联判：互补且 pick_share 分散 → 组合空间实锤（仍属
  现象，机制回三道门）。
只给候选假设；结论回 playbook 三道门。

## 验证步
见 frontmatter；<2 模型抛 ValueError 的契约被测试锁定。
