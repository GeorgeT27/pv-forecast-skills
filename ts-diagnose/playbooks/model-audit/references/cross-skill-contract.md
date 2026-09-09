# 跨 playbook 契约：桥接假设如何对接 result-eval

桥接假设引用「图#」与「H-ID」，二者归 result-eval playbook 所有（model-comparison/
deployment-drift 等其他消费方复用同一份 hypotheses.md/figure-diagnostics.md，契约不变）。
产出 models.md 的桥接节前：

## 两份 hypotheses.md：引擎包的是样例，工作目录的才是本项目的账

- 引擎包里的 `../../result-eval/references/hypotheses.md` 与 `figure-diagnostics.md`
  **只读**：前者给表结构、字段含义、状态流转纪律和命名法，后者给图#1–#12 各自查什么。
  它们随技能分发、跨项目共享，里面的假设行属于写它时的那个项目实例。
- 本次诊断的 H-ID 登记表是 `<workdir>/references/hypotheses.md`（工作目录副本）：
  不存在就按引擎包那份的表结构新建，只写本项目的假设行，绝不往引擎包里追加。

## 读入（作为输入，不复制）
- `<workdir>/references/hypotheses.md`（没有则读引擎包那份取表结构）—— 现有 H-ID 与写法
  （可判别预测、验证手段、状态）。
- `../../result-eval/references/figure-diagnostics.md`
  —— 图#1–#12 各自查什么，桥接假设的「哪张图检验」必须指真实的图。

## H-ID 注册（写回工作目录副本，不臆造）
- 每条桥接假设给一个 H-ID，遵循现有命名（`H-CHRONOS-1`/`H-WXSRC-1`/`H-<model>-<n>`）。
- **先读工作目录的 hypotheses.md**：命中已有条目→复用其 ID；没有→在**工作目录副本**追加
  一行，状态 `预注册`，末尾标 `预注册 by model-audit YYYY-MM-DD`，并写清可判别预测 +
  验证手段（哪张图）。
- 绝不引用工作目录 hypotheses.md 里不存在的 H-ID（否则消费端 H-ID 门解析失败）。

## 接口面（两个 playbook 只通过这三样耦合）
1. pointer 文件（`<workdir>/references/model-ref.pointer`）
2. H-ID 登记表（`<workdir>/references/hypotheses.md`）
3. figure-diagnostics.md（引擎包，只读）
模型事实不在两个 playbook 间复制粘贴。
