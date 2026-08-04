# 提问纪律（何时必问 · 何时可默认 · 怎么问 · 怎么落盘）

<!-- 引擎的"一等公民"机制。设计张力：不许假设 vs 提问疲劳——
     解法是把"必问"限定为五类硬场景 + 声明式 default + 批量提问。 -->

## 1. 必问五类（引擎级恒问，无论 playbook 有没有声明）

| # | 场景 | 为什么不能默认 |
|---|------|----------------|
| 1 | 数据 schema/单位/口径不明（列语义、时间粒度、聚合方式拿不准） | 猜错污染全部下游，且错得安静 |
| 2 | 成功判据/目标口径未定义（"充分""稳健""重要"按什么标准） | 判据不定，结论无意义 |
| 3 | 证据不足以升级结论 | 不许静默降级了事：问"接受降级还是补证据"，**列出补证据的具体成本**（要什么数据/算力/时间） |
| 4 | 破坏性/昂贵操作（GPU 重训、覆盖已有产物、写外部目录） | 授权必须显式 |
| 5 | 多候选文件/多版本选哪个 | 选错版本 = 分析错对象 |

命中任何一类，**停下 AskUserQuestion**，不管 playbook questions 里有没有对应条目。

## 2. 可默认类

- playbook questions 里声明了 `default` 的（纯呈现类选择、目录命名、图样式等）；
- `skip_if` 命中的（证据自答：如所需产物已在盘上且探测通过）；
- profile / 实验线已固化答案的。

采用默认必须在 PROGRESS.md 记一行：`按默认（<qid>: <default 值>）`——留痕，事后用户不认可可回溯改。

## 3. 怎么问

- **批量**：同一阶段的多个未答题合并成**一次** AskUserQuestion（≤4 题/次是工具上限，超了分两次、按 stage 顺序）。
- **带选项**：playbook 声明了 `options` 就用它（另加自由输入天然可用）；问 schema 时请用户**贴样例行**，比描述可靠。
- **带 why**：问题里带一句为什么要问（playbook 的 `why` 字段），用户答得准。
- **subagent 无提问权**：brief 里写死"缺信息原样回报，不要自行假设"——停顿点只在主 agent。

## 4. 怎么落盘

答案统一写 `diagnose_config.json` 的 questions 块（主 agent 写，单写者）：

```json
"questions": {
  "loss-source": {"answer": "文本日志，样例：[iter 3][chunk 2] epoch 14 loss=0.0312",
                   "source": "user", "date": "2026-07-14"}
}
```

`source` 枚举：`user`（本次问的）/ `profile`（固化技能带来）/ `default`（按声明默认）/ `experiment-line`（project-context 实验线预填）。**answer 存原话**（尤其样例行），不要存你的转述——转述丢信息且没法核对。派生出的结构化配置（路径、列名映射）另存 config 其他键，问答对保持原始。

## 上游产物拥有的问题

生产者 playbook 拥有其领域的形状问题（data-setup：freq、align-keys），消费者
**不得重复声明同 id 问题**——validate_upstream 在 load_frontmatter 时机器拒绝，
不是约定是闸。消费者要用答案时读上游产物的 manifest（orient 已注入摘要），
不再问用户第二遍。目标特有口径问题（metric-caliber、model-set 等）留在消费者。

这份 questions 块是 crystallize 的核心原料：固化 = 把其中"跨次稳定"的条目搬进 profile.yaml。
