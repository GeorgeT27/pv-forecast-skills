# 设计：ts-diagnose 单入口化 + 三道硬闸（pv-* 技能收编）

日期：2026-07-24
状态：已与用户逐节确认（泛化形态 / 方法去留 / 强制机制 / 阶段闸 四个决策均已批准）

## 背景与问题

用 deepseek flash 等弱执行模型跑现有技能体系时暴露三类失败：

1. **跑在假设的材料上**：技能没有确认用户实际拥有哪些资产（training logs、test.parquet、
   train.parquet、checkpoint、模型代码），按"以为有"的材料直接执行。现有
   `ts-diagnose/references/intake.md` 已定义 11 类材料与三态盘点流程，但它是散文纪律，
   弱模型直接跳过——没有脚本闸门拦截。
2. **结论不依赖模型结构**：pv-model-analysis 能把模型代码总结成 `.modelmap/` 档案
   （含"架构→预期误差形态→哪张图检验"桥接假设），但它是可选旁路，其他技能不强制消费。
3. **跳阶段**：如 model-comparison 场景跳过 Stage 2 画图直接归因。已有"图表门自检"
   （a61e604）仍是散文自检，弱模型无视。

另一个结构性问题：**路由靠 description 散文 + 三级优先级约定**（固化代理 > 专用 pv-* >
引擎兜底），5 个技能间的仲裁对弱模型太难。而 pv-* 技能本质上都是 ts-diagnose 在光伏
实例上的特化版本。

**病根统一**：前置层与阶段推进是"建议"不是"闸门"。对弱模型唯一有效的强制力在脚本的
exit 路径里，不在散文纪律里。

## 决策总览（用户已批准）

| 决策 | 结论 |
|---|---|
| 泛化形态 | 全部收编进 ts-diagnose，单入口 + playbook 表 |
| 方法去留 | 方法下沉进 playbook，技能壳删除；金标准测试随方法迁移 |
| 强制机制 | 方案 A：orient 硬闸（入口闸）+ 结论闸；材料必须问清 before running |
| 跳阶段 | 第三道闸：阶段闸——orient 按磁盘产物判定阶段完成，只吐当前阶段指令 |

## 1. 技能拓扑（改造后）

只保留 **ts-diagnose 一个技能**。Layer 0 路由 ≤60 行不变，`test_layering.py` 继续卡
行数与 token 预算。

删除：

- 仓库目录：`pv-result-analysis/`、`pv-feature-blame/`、`pv-station-influence/`、
  `pv-model-analysis/`（方法迁移完成后删壳）；
- `~/.claude/skills` 链接：上述四个 + 遗留的 `pv-analysis-resume`、`pv-model-verify`。

playbook 从 6 个变 9 个：

| playbook | 来源 | 说明 |
|---|---|---|
| training-sufficiency / robustness / feature-importance / model-comparison / deployment-drift / fact-scan | 现有 | 不动（feature-importance 吸收 feature-blame 方法，见 §5） |
| `model-audit`（新） | pv-model-analysis | 模型代码 → `.modelmap/` 档案；双重身份见 §4 |
| `result-eval`（新） | pv-result-analysis | 指标计算 / 月度归因 / 深度分析；续跑能力由引擎 orient 阶段模型承接 |
| `subset-influence`（新） | pv-station-influence | "站点"泛化为"训练子集/数据条目"对留出目标的影响归因 |

光伏特有内容（rmse_192 口径、192 点窗口、M1-M4、站点/条目注册表、白马湖实验线）
只存在于 `project-context/` 与 `experiments/*.json`；playbook 零站名零口径硬编码
（沿用现有模式）。

路由变化：

- ts-diagnose description 重写——删除负面清单（不再有专用技能可让位），正面列
  9 个 playbook 触发词；
- "已固化代理技能优先"这一条保留（crystallize 产物仍是最高优先级）；
- 弱模型的路由任务从"5 技能 + 三级仲裁"简化为"1 入口 + 1 张路由表"。

## 2. 入口闸（材料盘点硬闸）——解决"跑在假设的材料上"

**全局必问五件套**升为引擎级规则，不管进哪个 playbook 都必须问到三态之一：

`training_log`、`truth`（test.parquet）、`train_y`（train.parquet）、`checkpoint`、
`model_code`。playbook 自己声明的 required/optional 材料照旧叠加。

注：`train_y` 的定义随之放宽为"训练集数据（train.parquet，含真值，特征列可选）"——
intake.md 与 engine_common.MATERIAL_IDS 两侧同步改（test_materials.py 会逼一致），
不新增材料类。

orient.py 增加 gate 逻辑：

1. 扫 `diagnose_config.json` 的 `materials` 块。任何五件套或 playbook required 材料
   状态为 unknown（没问过）→ 打印 `BLOCKED: 材料盘点未完成`，**只输出待问清单**
   （按 intake.md 追问模板生成现成的 AskUserQuestion 文案），**不打印任何阶段菜单**。
   弱模型拿不到下一步指令，只能去问用户。
2. `present` 有实质校验：schema 必备字段（y_col / time_col / 对齐方式等，按材料类
   在 engine_common.MATERIAL_IDS 侧定义）缺失即不算 present——防"标 present 但没问
   schema"糊弄过闸。
3. `absent-confirmed` 必须带 `source: user`——只有用户亲口说没有才算；required 材料
   降级还须 `degraded_ok: true`（现有 intake.md 规则不变）。

产物：材料答案落 `diagnose_config.json.materials`（现有格式），跨次稳定条目
（layout/schema）仍是 crystallize 固化原料。

## 3. 阶段闸（产物判据推进）——解决"跳过画图直接归因"

把阶段推进权从模型手里收走，交给 orient：

1. **stage manifest**：每个 playbook 的每个阶段在 playbook frontmatter（或伴生
   manifest 文件）声明产物清单——如"Stage 2 完成 = 声明的图表文件存在 +
   INDEX.md 已生成并收录 + 图表 gate 通过"。判据是**磁盘上的文件**，不是模型自称。
2. **orient 只吐当前阶段**：orient 每次只打印当前未完成阶段的执行指令，后续阶段
   的菜谱入口一概不给。模型想归因，orient 只会说"Stage 2 缺这 N 张图，先画"。
3. **--goto 护栏**：目标阶段的前置产物不存在则拒绝直达；`--force` 可跳，但必须
   PROGRESS.md 记一行"用户明确要求跳过 Stage X"——跳过权在用户，且留痕。
4. **与结论闸联动**：归因结论每条论断必须引用图表产物路径，且文件真实存在
   （conclusion_gate 校验，见 §6）。

首批定义 stage manifest 的 playbook：model-comparison、result-eval（跳图问题的
两个现场），其余 playbook 随迁移补齐。

## 4. model-audit 的双重身份——解决"结论不看模型结构"（上半段）

- **作为 playbook**：用户说"帮我分析模型代码/生成模型档案"直接路由到它。内容 =
  原 pv-model-analysis 全流程（定位模型 → 逐模型三层抽取：工程 file:line / 数学 /
  桥接假设 → reconcile → 落盘 `.modelmap/` + pointer → 自检）。泛化点仅一个：
  模型清单不再假定 M1-M4，从 intake 问答或 experiment-line 来。
- **作为 provider**：intake.md `model_code` 材料的 provider 指向 model-audit
  playbook（替换现在的 `provider_skill: pv-model-analysis`）。orient 发现
  `model_code: present` 且 `.modelmap/` 不存在或 pointer commit 过期 → 唯一下一步 =
  "先执行 model-audit 生成档案"。用户不需要记得先跑什么，引擎自己串。
- `.modelmap/` 桥接假设的 H-ID 机制保留，消费方从 pv-result-analysis 扩为所有
  playbook。

## 5. feature-blame 方法下沉（不单独成 playbook）

方法链下沉为 **feature-importance playbook 的进阶阶段**，按材料解锁：

- 基础阶段（现有）：一般变量重要性；
- 有 `feature_true` 对照 → 解锁"预测特征质量归因"：两口径坏行 → 逐行 z 分数 +
  全局校准 ρ 双关点名（防冤枉）；翻新跳变分析（churn 两关）；
- 再有 `serving_api` → 解锁反事实预算阶梯：oracle G 闸 → minimal-set（联合致坏）→
  lattice Shapley → neighbor-swap 仲裁（决策逻辑 `cf_logic.py` 随迁引擎 scripts/）。

金标准埋点 + 诱饵测试随方法迁入引擎 tests/。

## 6. 结论闸——解决"结论不看模型结构"（下半段）+ 图证据

新 gate 脚本 `conclusion_gate.py`（gen_gate / crystallize_gate 同款风格）扫结论报告：

1. 必须含**「模型结构依据」**一节，且满足其一：
   - 引用 ≥1 条 `.modelmap` 桥接假设（带 H-ID 或 file:line 锚），把误差现象与
     架构事实挂钩；
   - 显式降级声明："模型档案缺失（用户已确认无代码，materials.model_code =
     absent-confirmed），结构性解释降级为猜测级"。
2. 归因论断必须引用图表产物路径，且文件在磁盘上真实存在。

gate 不过 → 结论不许交付（写入 PROGRESS.md，orient 下次进入仍报该阶段未完成）。

## 7. 三道闸对照表

| 闸 | 位置 | 拦什么 | 判据 |
|---|---|---|---|
| 入口闸 | orient.py（材料 gate） | 跑在假设的材料上 | diagnose_config.json.materials 三态 + schema 完整性 |
| 阶段闸 | orient.py（stage manifest） | 跳过画图直接归因 | 磁盘产物存在 + gate 通过 |
| 结论闸 | conclusion_gate.py | 结论无模型结构依据 / 无图证据 | 报告节结构 + 锚点/路径实存校验 |

共同原则：**强制力在脚本 exit 路径里，不在散文纪律里**；跳过权只属于用户且必须留痕。

## 8. 迁移顺序（每步 pytest 全绿再进下一步）

1. **引擎加固先行**（不动任何技能）：orient 入口闸 + 五件套全局必问 + 阶段闸框架
   （stage manifest 解析 + --goto 护栏）；
2. model-audit playbook 迁入 + provider 接线；
3. result-eval、subset-influence 迁入（含各自 stage manifest 与续跑完成判据）；
4. feature-blame 方法并入 feature-importance（cf_logic.py 与金标准随迁）；
5. conclusion_gate.py 接入 + 删四个壳 + 清 `~/.claude/skills` 链接 + 更新
   description / README / CHANGELOG / MEMORY。

## 9. 测试与守护

- 现有：test_layering.py（路由层预算）、test_materials.py（intake.md ↔
  engine_common.MATERIAL_IDS 交叉校验）、各 playbook golden、gen_gate、provenance、
  crystallize_gate——全部保留；
- 新增：入口闸单测（unknown 阻塞 / present 缺 schema 阻塞 / absent-confirmed 放行）、
  阶段闸单测（产物缺失不吐后续阶段 / --goto 拒绝 / --force 留痕）、conclusion_gate
  单测（缺"模型结构依据"节打回 / 引用不存在的图打回）；
- 迁移的金标准测试保持绿：feature-blame 金标准埋点 + 诱饵、station-influence 六阶段、
  result-eval 指标口径（rmse_192）。

## 不做的事（YAGNI）

- 不做独立前置技能 /intake（方案 B 已否决——依赖用户与模型自觉，正是这次翻车原因）；
- 不做用户手工维护的 assets.yaml（方案 C 已否决——与"提问一等公民"哲学相反）;
- 不为其余 4 个 playbook 首批补 stage manifest（随后续使用逐个补齐）；
- 不改变 crystallize 固化机制与固化代理技能的最高优先级。
