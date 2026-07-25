# ts-diagnose Playbook 分层设计（produces / upstream 机制）

日期：2026-07-25　状态：已与用户逐节确认　范围：仅 ts-diagnose（9 playbook 单入口已收口）

## 0. 问题与目标

现状每个 playbook 都是"全流程"：自带 Stage 0（适配器→规范长表→对齐）、自带大而全的默认图集（model-comparison Stage 2 声明 14 张图）。后果：单个 playbook 任务过重、Stage 0 菜谱在 9 个 playbook 里重复、目标聚焦差（"为什么 A 比 B 好"只需要对比侧图）。

目标：把 playbook 分成两层——
- **Level-1（生产者）**：小而基础的 playbook，产出**持久化产物**（product）供下游消费。必需类（data-setup）人人依赖；可选类（model-audit、fact-scan）按需。
- **Level-2（消费者/分析）**：declares 上游产物依赖，砍掉自己的 Stage 0 与图集冗余，只留目标核心菜谱。

外部调研结论（Anthropic skill 最佳实践 + 社区模式）支持该方向：小而单一职责的 skill 是主流实践（"multi-specialist over monolith"）；跨任务依赖的可靠形态是**落盘产物 + 脚本核验**（"hooks not hopes"——纯指令式前置会被跳过）；昂贵生产者缺失时**问用户**、廉价必需生产者**自动跑**是社区共识；已知反模式是**过度拆分**（总是共现的步骤不拆）。

## 1. 已确认的决策

| 决策点 | 结论 |
|---|---|
| 依赖缺失处理 | 混合制：required 缺 → 引擎同会话自动跑生产者（不问）；optional 缺 → 三分支问（现跑 / 链接已有 / 放弃并声明代价） |
| 图集瘦身 | 每个 level-2 只声明目标核心图；fact-scan 成为"大而全体检"的 level-1 可选生产者，产物存在时 level-2 复用不重画；其余图留可加画池 |
| v1 生产者阵容 | 三个：data-setup（必需）、model-audit（可选，产模型档案）、fact-scan（可选，产图谱体检）。训练日志定位**并入 data-setup 的 manifest**，不单独成 playbook（防过度拆分） |
| 机制选型 | 方案 A：produces/upstream frontmatter + orient 机器裁决，泛化并取代现有 contexts: 机制。不做 Make 式通用 DAG（图只有两三层深，通用调度器是为用不到的深度付费）；但吸收其唯一在此有用的能力——**基于输入哈希的过期检测**，放进 manifest，一次哈希对账即可 |
| 范围 | 仅 ts-diagnose；pv-* 技能已并入（9 playbook 单入口），新并入的 playbook 同样按本设计改造 |

## 2. Spec 变更（_playbook-spec.md）

新增两个 frontmatter 块：

```yaml
# 生产者（level-1）声明：
produces:
  id: setup                      # 产物 id，引擎内唯一
  manifest: setup_manifest.json  # 机器契约：内容见 §3；必含输入文件哈希
  marker_files: [predictions.csv, alignment_report.json]   # 有效性核验

# 消费者（level-2）声明：
upstream:
  - product: setup
    required: true               # 缺 → orient 打"立即执行"指令，主 agent 同会话跑完生产者再回来，不问用户
  - product: model_profile
    required: false              # 缺 → 三分支问（沿用今天 contexts 的语义）
```

- check-DSL 新增表达式 `product:<id>`：产物 status ∈ {built, linked} 且 marker_files 核验通过。
- **生产者允许自己声明 upstream**（fact-scan 依赖 setup），orient 递归解析 + 环检测；图天然浅，不引入调度器。
- `contexts:` 机制退役：model-comparison 的 model-profile context 改写为 upstream 条目；全部改造完成后从 spec 与 orient 删除 contexts 代码路径。
- 提问去重纪律：生产者拥有的问题（freq、align-keys 等数据形状问题）下游 playbook **不得重复声明**（test_products.py 守卫）；目标特有问题（metric-caliber、model-set）留在 level-2。

## 3. 新 playbook：data-setup（普适必需前置）

吸收今天散在各 playbook 的 Stage 0：材料盘点 → 薄适配器 → 规范长表（predictions.csv；有材料时加 features.csv / train_y.csv）→ 对账两关 → alignment_report.json。

产物 manifest（setup_manifest.json）记录：
- 各规范长表路径、模型清单、freq、行数、日期范围；
- **完整材料清单，含训练日志 / 实验配置的位置与格式**（"训练分析要知道日志在哪"由此覆盖，一次落盘、全下游可读）；
- **输入文件哈希**（过期检测：orient 发现当前材料哈希 ≠ manifest 记录 → 警告"setup 产物基于旧输入，需重建"，要求用户确认重建）。

数据形状问题（freq、align-keys）只在这里问一次。golden 以 chartbook/golden/example_adapter 为种子。

## 4. 生产者升格：model-audit 与 fact-scan

- **model-audit** → `produces: model_profile`（marker：models.md）。model-comparison / training-sufficiency 等的可选上游。
- **fact-scan** → `produces: chart_sweep`（13 张大而全图 + INDEX + 现象清单），自身 `upstream: setup (required)`。产物存在时，level-2 对重叠图**直接复用已有图 JSON 判读，不重画**。

## 5. Level-2 瘦身

所有分析 playbook：删 Stage 0（由 `upstream: setup` 取代）、`charts:` 收窄到目标核心集、其余图留可加画池。试点 **model-comparison**：
- 阶段 5 → 3：总差距 → 分解+归因 → 结论；
- 图 14 → 5：`worst-slice-compare, model-error-correlation, oracle-gap, horizon-degradation, cross-dim-stability`。

其余 playbook（含新并入的 result-eval / feature-importance / subset-influence 等）按同样手法逐个改造。

## 6. 引擎变更（orient.py + config）

- `diagnose_config.json` 新增 products 注册表：`products.<id> = {workdir, status: built|linked|absent, manifest_hashes}`。
- 工作目录布局：一个会话根目录；生产者在产物 id 命名的子目录跑（`<root>/setup/`、`<root>/model-audit/`…），level-2 在 `<root>/<goal>/` 跑；config 在根目录。
- orient 解析顺序：材料 → 上游产物（required 缺 → 打印立即执行指令；optional 缺 → 三分支问）→ 阶段推进。
- 过期检测见 §3。

## 7. 守卫、golden、测试

- data-setup 带自己的 golden/（种子：chartbook/golden/example_adapter）。
- 新增 test_products.py：upstream 引用必须指向已声明产物；环检测；提问去重守卫（下游不得重声明生产者拥有的问题）。
- test_layering.py 更新：produces/upstream 声明的跨 playbook 引用合法（按声明白名单放行），其余照旧禁止。
- **迁移期向后兼容**：无 upstream 块的 playbook 保留内联 Stage 0 照常工作——逐个转换，闸全程绿。

## 8. 迁移顺序

1. spec + 引擎机制（向后兼容落地）；
2. data-setup playbook + golden；
3. 试点：model-comparison 端到端改造（含图集瘦身）；
4. 其余 playbook 批量改造（含新并入的）；
5. 无引用后退役 contexts: 机制。

## 9. 明确不做（YAGNI）

- 通用 DAG 调度器 / 拓扑排序（两三层深的图用递归解析即可；若未来出现 level-2 产物再被别的 level-2 消费的三层以上链，才重新评估）；
- 独立的 training-setup-discovery playbook（并入 data-setup manifest）;
- pv-* 旧技能路径的改造（已并入，按新 playbook 身份统一处理）。
