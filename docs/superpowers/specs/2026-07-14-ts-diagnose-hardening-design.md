# ts-diagnose 加固轮设计（择优采纳版）

日期：2026-07-14（同日第二轮）。上一轮 spec：`2026-07-14-ts-diagnose-engine-design.md`。

背景：用户给出六节加固提案（三层渐进加载 / 生成闸+归因闸 / 三关固化判据 / 路由消歧 / 接口版本化 / 回归 evals），并明确"不一定全用，挑好的 idea"。本 spec 记录筛选决策与落地设计。

## 三条硬不变量（提案的目标，采纳）

1. 引擎常驻 token 有上限：命中任何 playbook 之前加载的 ts-diagnose 内容 ≤ 60 行 / ~6K token，进 pytest（本仓库的 CI 等价物），超预算 fail。
2. 进入决策的数字必须可复现：同一输入两次结果一致，或差异可归因到数据而非代码。
3. 固化产物与专用技能同等可信：薄代理技能转正须过与人工技能同强度的门槛。

## 采纳/裁剪决策

| 提案 | 决策 | 理由 |
|---|---|---|
| 三层渐进加载 + token 预算测试 | 采纳 | SKILL.md 每次触发都进上下文，原 82 行大半是命中后才需要的执行细节；预算测试防重新长成单体 |
| 生成闸（金标准基线） | 采纳（价值最高） | 运行时生成分析代码是最大质量风险，原来只靠脚本自报验证步；金标准是独立防线，"金标准算错不许碰真实数据"落成机制脚本 |
| 归因闸（provenance） | 采纳（轻量） | 小 hash 脚本 + 结论约定即可判"结论不同→代码还是数据变了" |
| 三关固化判据 | 采纳（最小实现） | 关3 骑在生成闸上；关1/2 是记录计数/存在性检查，checker 很小；held-out 场景库本身推后 |
| 路由消歧 descriptions | 采纳 | 四类技能共存必须有确定性优先级；用户显式授权动三个专用技能 description（其余零改动） |
| 路由 CI（打分路由器） | 裁剪→漂移守卫 | 关键词打分器模拟不了语义路由，是伪测试；改为断言 description 必含触发短语与优先级/让位条款 |
| experiment_line 版本化 v0-draft | 采纳 | 防对未定稿接口的真实耦合，改动很小 |
| regression/baselines 回归 evals | 只预留接口位置 | 用户已排后续轮；golden/reference_impl.py 设计使将来直接复用 |
| held-out 场景库 | 只预留接口位置 | 同上 |
| "三次探针测量 token 几乎相同" | 简化 | 加载是静态文件；等价保证 = SKILL.md ≤预算 + 不指示命中前加载其他文件 + 禁方法词表内联 |

## 一、三层渐进加载

- **Layer 0 = SKILL.md（≤60 行纯路由）**：识别目标 → 匹配 playbook → 转发（读 `references/engine-core.md` + `playbooks/<id>/playbook.md`）。不含任何 playbook 的分析逻辑描述。原 82 行版的提问纪律 / Step 0.5 / 执行模型 / 结论纪律 / 常见错误 / 运行后回顾下沉到新文件 `references/engine-core.md`（命中后才加载）。
- **Layer 1 = playbook 层**：每个 playbook 一个独立目录 `playbooks/<id>/`（`playbook.md` + `golden/`），互不引用。
- **Layer 2 = 机制脚本层**：`scripts/`（orient / engine_common / gen_gate / provenance / crystallize_gate），不进上下文，只被调用。
- **验收**：`scripts/tests/test_layering.py`——行数与估算 token 预算（CJK≈1 token/字 + 其余 4 字符/token）、SKILL.md 禁 playbook 方法词表、references/ 只允许 engine-core 与 crystallize 指针、playbook 互不引用。

## 二、生成闸 + 金标准基线

- `scripts/gen_gate.py --script <生成脚本> --playbook <id> --stage <k>`：
  1. 静态检查（ast 语法；禁 subprocess/socket/requests、os.system、绝对路径写、shutil 删除）；
  2. 金标准运行：按 `playbooks/<id>/golden/manifest.json` 该 stage 的 `args`（CLI 契约）在沙箱临时目录跑 golden 输入，产物过断言 DSL（eq/le/ge/between/argmax/argmin/contains，带 tol）；
  3. 结果落工作目录 `gate_reports/<script>.json`（含脚本 sha256）；FAIL → 退出非零，不许碰真实数据；改脚本不改期望。
- 每个 playbook 自带 `golden/`：确定性解析式合成（零随机）、`make_golden.py`、输入数据、`manifest.json`、`reference_impl.py`（CLI 契约示例 + CI 端到端被闸对象 + 将来 regression baselines 复用）。
- 归因闸 `scripts/provenance.py`：生成代码逐文件 sha256 + 合并 code_hash、输入数据 input_hash、gate_reports 自检汇总 → `provenance.json`；CONCLUSION.md 末尾必附（约定进 conclusion-reporting.md 与 _playbook-spec.md）。

## 三、三关固化判据

`references/crystallize.md` 由"三步验证"升级：

1. **多样性**：`crystallize_record.json` 记录 ≥N 个 input_hash 互异的成功 case（N = playbook frontmatter `crystallize_min_cases`，默认 3，training-sufficiency 5）；
2. **held-out**：一条未参与开发的场景记录 passed=true 且 hash 不与任何 case 重合（场景库后续轮，本轮只要求记录存在且通过）；
3. **快照自洽**：每个快照脚本经 gen_gate 在其 playbook golden 上 PASS。

`scripts/crystallize_gate.py` 判三关，任一不过退出非零。三关全过才写 profile.yaml + SKILL.md；原三步验证降为交付检查。

## 四、路由消歧

优先级：**已固化代理技能 > 三个专用技能 > 引擎兜底**。引擎 description 加"仅当无匹配的专用诊断技能或已固化代理技能时使用"；三个专用技能 description 各加优先级/让位一句（pv-station-influence 额外收窄：训练动力学仅限站点归因场景）。`tests/test_routing.py` 做描述漂移守卫（存在性断言，非模拟路由）。

## 五、experiment_line 接口版本化

profile 的 `experiment_line` → `{path, interface_version: v0-draft}`（旧字符串视同 v0-draft）；merge_profile 读到 v0-draft → 占位不生效、orient 提示、相关问题照常问。运行时主 agent 现场写入 config.experiment_line 不受影响（约束只针对固化产物）。v0→v1 迁移排 project-context 定稿轮。

## 六、预留接口位置（本轮只留位置）

`_playbook-spec.md` 新增：`heldout/` 场景库目录规范、`regression/baselines/`（机制脚本改动 → 重跑全部 playbook 金标准比对 + 固化代理快照隔离确认）、v0→v1 迁移条目。

## 完成定义与纪律

三层结构 + 预算测试；golden×3 + 生成闸 + 归因闸；三关判据代码可执行；路由优先级进 4 个 description + 漂移守卫；experiment_line 版本化；spec 预留接口位置。三个专用技能除 SKILL.md description 外零改动；project-context/ 零改动；只按显式路径 stage。
