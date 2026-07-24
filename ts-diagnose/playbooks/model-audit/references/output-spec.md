# 产物规范：`<repo>/.modelmap/` + pointer

所有产物写到 `<model-repo>/.modelmap/`；pointer 写到消费方 playbook 的固定相对路径
`references/model-ref.pointer`（如 result-eval playbook 消费时即
`ts-diagnose/playbooks/result-eval/references/model-ref.pointer`；哪个 playbook 内联执行
model-audit 就写到该 playbook 自己的 `references/` 下，见各 playbook 的 subagent-briefs.md
「读固定 pointer：`references/model-ref.pointer`」）。

## 文件清单
| 文件 | 读者 | 内容 |
|------|------|------|
| `START-HERE.md` | 人 | 5 行 TL;DR + 阅读顺序 + "改哪找哪"表 |
| `pipeline.md` | 人 | 逐模型工程流程图（machinery.md 四要素）|
| `math.md` | 人 | 逐方法数学，一个 `##` 一方法，符号与 symbol-map 一致 |
| `models.md` | **result-eval / model-comparison / deployment-drift 等消费方 playbook** | 分析就绪档案：逐模型 代码类名/架构/输入特征/损失/训练窗口/强弱项 + 架构→结果分析含义桥接假设。结构见 models-template.md |
| `symbol-map.md` | 双方 | 符号 ↔ 代码变量 ↔ 位置 ↔ 形状/dtype |
| `ledger.md` | 双方 | 断言 ↔ `file:line` 证据（reconcile 审计轨迹）|
| `open-questions.md` | 双方 | ⚠️ + 待确认，需人解决 |
| `data-profile.md` | 双方 | 仅当给了数据样本：profile_data.py 实测统计 |

`models.md` 是从 `pipeline.md`+`math.md` 蒸馏出的分析面视图；产出时三者事实/锚点必须一致。

## pointer 文件格式（`scripts/pointer.py` 读写）
```
path:   /abs/.../<repo>/.modelmap
repo:   /abs/.../<repo>
commit: <git sha 或 no-git>
date:   YYYY-MM-DD
models: M1, M2, M3, M4, ensemble
```
陈旧判定：`is_stale` 比对 pointer.commit 与 `git -C <repo> rev-parse HEAD`；`no-git`/空 → 无法判定按不陈旧。
