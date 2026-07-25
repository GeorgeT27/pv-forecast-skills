---
name: ts-diagnose
description: 泛化的时序模型诊断引擎（单入口，覆盖时序/预测任务的全部诊断与评估目标，含 11 个可插拔 playbook）。触发场景："训练是否充分/是不是 batch 不足/训练分配（chunk/fold 构成）有没有问题/为什么 loss 震荡或收敛慢"（training-sufficiency）、"结论/模型在扰动与分组切片下稳不稳"（robustness）、"哪个输入变量对误差影响最大/有 feature_true 对照的预测特征质量归因/反事实验证"（feature-importance）、"为什么模型 A 比 B 好/多模型对比归因"（model-comparison）、"模型上线后是不是退化了/误差从什么时候开始变大/漂移诊断"（deployment-drift）、"只想把标准分析图画一遍看现象、不要结论"（fact-scan）、"分析模型代码/生成模型档案"（model-audit）、"评估预测结果/算指标/月度或时段归因"（result-eval）、"把原始预测/真值先规范成长表与对齐报告（各分析目标的必需前置，通常由引擎自动先跑）"（data-setup）、"N 个训练条目里哪个拖累留出目标/负迁移归因"（subset-influence）、"只算指标/算个 RMSE/给我指标表，不用分析"（metric-eval）。已固化代理技能（经 crystallize 产出）若覆盖当前场景则优先级最高。
---

# ts-diagnose：Layer 0 路由层

本文件只做三件事：**识别诊断目标 → 匹配 playbook → 转发**。不含任何 playbook 的执行细节；
命中之前不要读引擎的其他文件。

## 路由优先级（两级）

1. **已固化代理技能**最高——命中其场景直接短路（`orient.py --profile` 入口，已验证脚本 + 免重复提问）；
2. **本引擎**——其余诊断与评估目标一律由下方 11 个 playbook 覆盖。

## 路由表（识别目标 → 匹配 playbook）

| 用户的目标像这样 | playbook |
|---|---|
| 训练是否充分 / batch 或数据量不足 / chunk·fold 构成与分配 / loss 震荡收敛慢 | `training-sufficiency` |
| 结论或模型在扰动、分组切片、子期下稳不稳 | `robustness` |
| 哪个输入变量对误差/目标指标影响最大 / 有 feature_true 对照的预测特征质量归因与反事实验证 | `feature-importance` |
| 为什么模型 A 比 B 好/差、多模型对比归因 | `model-comparison` |
| 上线/部署后是不是退化了、误差从什么时候开始变大、漂移诊断 | `deployment-drift` |
| 只想体检/把标准分析图画一遍/看现象不要结论 | `fact-scan` |
| 给定模型代码目录：分析模型/生成模型档案/核验描述与代码一致 | `model-audit` |
| 评估一次预测结果 / 算指标（默认 rmse_192）/ 月度或时段归因 / 深度分析 | `result-eval` |
| N 个训练条目里哪些拖累留出目标（负迁移）/ chunk loss 震荡解释 | `subset-influence` |
| 只想先把原始数据规范成长表/对齐报告（其他目标的必需前置，一般自动先跑） | `data-setup` |
| 只算指标 / 算个 RMSE / 给我指标表，不用分析 | `metric-eval` |

都不像 → 先跑下方 orient 看菜单再与用户确认；菜单里也没有 → 按 `playbooks/_playbook-spec.md`
写新 playbook（先征得用户同意）。

## 转发（命中 playbook 后，按顺序）

1. 读 `references/engine-core.md`（执行纪律：提问/推进/结论/常见错误）＋
   `playbooks/<id>/playbook.md`（该目标的阶段与菜谱）；
2. 在工作目录跑 orient（引擎目录 `<ENGINE>` = 本 SKILL.md 所在目录）：

   ```bash
   python3 "<ENGINE>/scripts/orient.py" [--playbook <id> | --profile <技能>/profile.yaml] [--goto N]
   ```

3. 照 orient 输出与 engine-core 纪律执行；固化操作见 `references/crystallize.md`。

<!-- Layer 边界（scripts/tests/test_layering.py 守卫）：本文件 ≤60 行 / ~6K token，
     禁止出现任何 playbook 方法词汇与阶段内容——想加执行细节，去 engine-core.md 或 playbook。 -->
