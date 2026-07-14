---
name: ts-diagnose
description: 泛化的时序模型诊断引擎（兜底技能——仅当无匹配的专用诊断技能或已固化代理技能时使用）。当用户对时序/预测任务提出**新的诊断目标**时使用："训练是否充分/是不是 batch 不足/训练分配（chunk/fold 构成）有没有问题/为什么 loss 震荡或收敛慢"（training-sufficiency）、"结论/模型在扰动与分组切片下稳不稳"（robustness）、"哪个输入变量对误差影响最大"（feature-importance）。**负面清单（这些场景用专用技能，不用本引擎）**：光伏预测结果评估/指标 Excel/月度归因 → pv-result-analysis；训练站负迁移归因（哪个站拖累留出站）→ pv-station-influence；从模型代码生成参考档案 → pv-model-analysis。已固化代理技能（经 crystallize 产出、orient --profile 入口）若覆盖当前场景则优先级最高，直接用它。
---

# ts-diagnose：Layer 0 路由层

本文件只做三件事：**识别诊断目标 → 匹配 playbook → 转发**。不含任何 playbook 的执行细节；
命中之前不要读引擎的其他文件。

## 路由优先级（四类技能共存的确定顺序）

1. **已固化代理技能**最高——命中其场景直接短路（`orient.py --profile` 入口，已验证脚本 + 免重复提问）；
2. **三个专用技能**次之——见上方 description 负面清单；
3. **本引擎兜底**——只接前两类都不覆盖的新诊断目标。

## 路由表（识别目标 → 匹配 playbook）

| 用户的目标像这样 | playbook |
|---|---|
| 训练是否充分 / batch 或数据量不足 / chunk·fold 构成与分配 / loss 震荡收敛慢 | `training-sufficiency` |
| 结论或模型在扰动、分组切片、子期下稳不稳 | `robustness` |
| 哪个输入变量对误差/目标指标影响最大 | `feature-importance` |

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
