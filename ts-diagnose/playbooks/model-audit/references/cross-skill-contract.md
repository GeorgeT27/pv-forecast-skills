# 跨技能契约：桥接假设如何对接 pv-result-analysis

桥接假设引用「图#」与「H-ID」，二者归 pv-result-analysis 所有。产出 models.md 的桥接节前：

## 读入（作为输入，不复制）
- `../../pv-result-analysis/references/hypotheses.md` —— 现有 H-ID 与写法（可判别预测、验证手段、状态）。
- `../../pv-result-analysis/SKILL.md` 的「图谱目录」小节 + `../../pv-result-analysis/references/figure-diagnostics.md`
  —— 图#1–#12 各自查什么，桥接假设的「哪张图检验」必须指真实的图。

## H-ID 注册（写回，不臆造）
- 每条桥接假设给一个 H-ID，遵循现有命名（`H-CHRONOS-1`/`H-WXSRC-1`/`H-<model>-<n>`）。
- **先读 hypotheses.md**：命中已有条目→复用其 ID；没有→在 hypotheses.md 追加一行，状态
  `预注册`，末尾标 `预注册 by pv-model-analysis YYYY-MM-DD`，并写清可判别预测 + 验证手段（哪张图）。
- 绝不引用 hypotheses.md 里不存在的 H-ID（否则消费端 H-ID 门解析失败）。

## 接口面（两技能只通过这三样耦合）
1. pointer 文件（model-ref.pointer）
2. hypotheses.md 的 H-ID 登记表
3. 图谱目录 / figure-diagnostics.md
模型事实不在两技能间复制粘贴。
