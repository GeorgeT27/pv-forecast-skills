# 产物规范：`<repo>/.modelmap/` + pointer

产物放两处：

- **档案本体**：全部写到模型仓库的 `<model-repo>/.modelmap/` 目录下。
- **pointer**：由运行中的消费方 playbook 生成到**本次诊断工作目录**的
  `references/model-ref.pointer`，即 `<workdir>/references/model-ref.pointer`
  （`<workdir>` = 该 playbook 的 `diagnose_config.json` 所在目录）。
  **绝不写进引擎包目录**（`ts-diagnose/playbooks/*/references/`）——那是随技能分发的只读
  文件，运行时往里写会把某一次诊断的路径污染给之后所有项目。各 playbook 的
  subagent-briefs.md 写作「读运行时 pointer：`references/model-ref.pointer`」，
  路径相对工作目录解析。引擎按 `MODELMAP_RECEIPT.json` 的 `modelmap_dir` 消费，pointer
  是给人和下游卡片看的索引。

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

`models.md` 是从 `pipeline.md` + `math.md` 蒸馏出来的"分析面视图"；三个文件的事实与
锚点必须一致，产出时互相对齐。

## models.md 新增字段：`ablation_switches` / `diff_list`

`model_profile` 产物 schema 新增两个字段，都写进 `models.md`，不新增独立文件、不改
pointer 格式；结构模板见 `models-template.md`。

- **`ablation_switches`**（每个模型一份，紧跟该模型的桥接假设小节）：
  `[{component, switch, kind, values}]`。`values` = 该开关值得一试的取值数组（`config-flag`
  与 `code-stub` 必填，布尔开关写 `[true]`，`not-intervenable` 可省）——
  下游 model-improve 的素版候选按 values 逐值排队，缺了它取值就只能靠人拍。
  `kind ∈ {config-flag, code-stub, not-intervenable}`：
  现成配置项（如 `--n_heads`）标 `config-flag`；需新写代码才能触发的置零/替换/初始化
  覆盖（如 `--itrans_no_attn`）标 `code-stub`；确无法干预的标 `not-intervenable` 并写
  清原因。范围须覆盖 `__init__`/初始化/默认参数，不能只看 forward——初始化差异常年
  藏在这里，漏掉会把差距错记到别的组件。供 architecture-attribution 等验证脊 playbook
  据此选 intervention。
- **`diff_list`**（仅当本次审计涉及 ≥2 个模型对比时产出）：逐行列出两模型代码差异，
  同样须覆盖 `__init__`/初始化/默认参数，不能只对比 forward；末尾附完备性自检声明——
  声明已逐项核对 forward + `__init__` + 默认参数三处，或如实列出未覆盖处。清单不完备
  ＝假设空间有洞＝错误归因，不许静默省略未覆盖处。

## pointer 文件格式（`scripts/pointer.py` 读写）
```
path:   /abs/.../<repo>/.modelmap
repo:   /abs/.../<repo>
commit: <git sha 或 no-git>
date:   YYYY-MM-DD
models: M1, M2, M3, M4, ensemble
```
陈旧判定：`is_stale` 比对 pointer 记录的 commit 与 `git -C <repo> rev-parse HEAD`，
不一致即视为档案陈旧；commit 是 `no-git` 或为空时无法判定，按不陈旧处理。
