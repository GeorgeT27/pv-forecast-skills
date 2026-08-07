# 重构设计：假设验证循环（pilot 一对）

状态：设计定稿（2026-08-07），待实施。定位：这是"先人工瘦身、再自进化"路线里的**瘦身重构**，是阶段 3 自进化循环的前置——把 skill 变轻、并让运行时结构与自进化循环同构。

## 0. 一句话目标

把散落在每个分析 playbook 里、各写一遍的"三条腿（切片测量→机理假设→干预验证→结论）"抽出来，变成**引擎编排的运行时主循环**：分析 playbook 只产**假设**，architecture-attribution 做**验证**，结论只在循环出口产**一次**。

同时解决两件事：
- **太重**：分析 playbook 砍掉重复的"结论模板 + 证据升级规则 + 反驳门"，每个瘦 30–50%。加 architecture-attribution 不是 +1 个重兄弟，而是让其余 playbook 变瘦的**共享主脊**，净重量下降。
- **提升分析能力**：从"一竿子给结论"升级为"提假设→干预验证→否证则自我纠错重提"的科学方法循环。

## 1. 落地范围（pilot）

只接一对，验证循环真能跑通、真变轻，再推广到其余 6 个分析 playbook。

| 组件 | 角色 | 本轮动作 |
|---|---|---|
| model-comparison | 假设生成器 | 手术瘦身（193→~90 行），不再产结论 |
| architecture-attribution | 验证主脊（共享） | 新建，强制 subagent 外包干预 |
| engine-core | 循环编排 | 新增"假设验证循环"一节 |
| conclusion_gate | 结论唯一出口 | 已规划的 `ablation_receipts` 字段（阶段 1 A3） |

**不动**：其余 6 个分析 playbook（result-eval / feature-importance / subset-influence / training-sufficiency / deployment-drift / robustness）本轮不转型，待 pilot 验证后推广。纯事实生产者（data-setup / fact-scan / metric-eval / model-audit）本就该薄，永不转型。

## 2. 核心架构

```
        ┌─────────────────────────────────────────────┐
        │  model-comparison（假设生成器）              │
        │  切片测量 + 差距分解 → 吐【结构化假设账本】  │  ← 不再产结论
        └───────────────────────┬─────────────────────┘
                                 │ hypotheses[]
                                 ▼
        ┌─────────────────────────────────────────────┐
        │  architecture-attribution（验证主脊）        │
        │  取判别力最高的假设 → 单变量干预 → 判定      │  ← 每个干预强制 subagent
        └───────────────────────┬─────────────────────┘
                                 │ verdict + receipt
             ┌───────────────────┼────────────────────┐
        否证 & 有预算            确认              预算耗尽/无新假设
             │                   │                    │
             ▼                   ▼                    ▼
   回生成器提修正假设      ──────→ conclusion_gate 落【唯一一次结论】
   （标 post-hoc）               （确认因 + 否证因带 kill-receipt + 未决）
```

循环由**引擎（engine-core）编排**，不塞进任何单个 playbook 内部。

## 3. 共享工件：假设账本（hypothesis ledger）

生成器与验证脊之间的唯一接口，是结构化账本（不是散文）。三条纪律直接编码进 schema。

```json
{
  "slice_map": [
    {"dim": "lead_time", "bucket": "far", "z": 10.2, "winner": "iTransformer"}
  ],
  "hypotheses": [
    {
      "id": "H1",
      "claim": "iTransformer 跨变量注意力混合带来近端优势",
      "component": "itransformer.attention (cross-variable)",
      "falsifiable_pred": "置零跨变量注意力后，近端优势应消失",
      "discriminating_power": 3,
      "intervention": {"switch": "--itrans_no_attn", "seeds": 3},
      "status": "pending",
      "kill_receipt": null,
      "provenance": "pre-registered"
    }
  ]
}
```

字段纪律：
- `component`：必须指向模型代码中的具体组件（来自 model-audit），否则不合法。
- `falsifiable_pred`：必须给出可否证预测。
- `discriminating_power`：一次干预能区分几个假设，验证脊按此排序优先。
- `provenance`：`pre-registered`（干预前登记）或 `post-hoc`（否证后新提）——事后假设必须标注，且需新干预才能升级为确认，不许同批数据既生成又确认。
- `status`：`pending → confirmed / refuted / undecided`。
- `kill_receipt`：否证时填（配置 diff + 实测 delta + 噪声底对照 + 种子数）。**否证的假设不删，转 kill-receipt 留档**（= C1 已在做，= SkillOpt 的拒绝缓冲）。

## 4. model-comparison 手术（砍什么、留什么）

对照现有 8 节：

| 现有节 | 处置 |
|---|---|
| §1 问题框定与首要陷阱 | 留（瘦身） |
| §2 Stage 0 总差距 / Stage 1 差距分解 | 留——测量→版图，生成器核心 |
| §2 Stage 2 机制归因 | 改：只到"生成假设账本"为止，不做判定 |
| §2 Stage 3 结论 | **删**——移交验证主脊 |
| §3 证据升级规则 | **删**——移到主脊统一一份 |
| §4 停顿点与汇报 | 留（瘦身：停顿点 = 交账本给主脊） |
| §5 subagent 拆分建议 | 留 |
| §6 结论模板与特有反驳门 | **删**——移到主脊 |
| §7 材料降级说明 | 留 |
| §8 chartbook 覆盖声明 | **改**：见 §5 画图重设计 |

预计 193 行 → ~90 行。删掉的 §3/§6/Stage3 正是在 11 个 playbook 里重复了 11 遍的那套。

后果说明：model-comparison 单独跑（无验证材料）时**不再自己出结论**，而是出"带标注的未验证假设"（见 §7 回退）。

## 5. 画图重设计：主题调色板 + 假设驱动选图

**问题**：现在预设"画固定 5 张图"。若某张没实质结果、需 post-hoc 重画，固定清单里没有额外的图，弱模型（如 DeepSeek）会卡住（"清单跑完了，然后呢？"）。但完全不规定画什么，弱模型会更懵。

**解法**：中间态——主题调色板（给弱模型兜底的具体菜单）+ 假设驱动的选图规则。

```
规则：每一轮，只画"生成或区分当前假设所必需"的图；画什么，从本 playbook 主题调色板里选。

model-comparison 主题调色板（每项标注"何时用"）：
  ├─ 分 lead-time 误差曲线   ← 想看"差距在远端还是近端"时画
  ├─ 分时段/hour 误差热图    ← 想看"差距集中在哪些时刻"时画
  ├─ 分变量/通道误差柱       ← 想看"哪个变量吃亏"时画
  ├─ 波动性分位 vs 误差      ← 想看"是不是高波动段吃亏"时画
  └─ 残差/签名对比           ← 想区分两个机制假设时画
```

三条原则：
1. **调色板给弱模型兜底**：不是自由发挥，是从菜单里挑，每项标了"何时用"。
2. **选图由假设驱动**：要提假设 H → 画能看见 H 签名的图；要区分 H1/H2 → 画能分开它们的图。没有假设就不画。post-hoc 时"再挑一张"是天然动作，不卡住。
3. **落地零新增**：调色板 = 现有 `plots.py`（390 行）+ `figure-diagnostics.md`（500 行）。把 figure-diagnostics 从"每次全读"降为"按需查阅的选图手册"——顺带把 500 行踢出主上下文（渐进式加载），又一笔瘦身。

## 6. 引擎循环控制（engine-core 新增"假设验证循环"节）

不新建引擎文件，写进 `references/engine-core.md`。

- **预算**：沿用 architecture-attribution 的干预预算阶梯，单轮上限 ~10 次训练；循环总轮数上限 3 轮，防死循环。
- **终止条件**（任一满足即收）：
  1. 某假设确认且能解释切片版图；
  2. 预算耗尽；
  3. 生成器提不出新的判别性假设。
- **结论只在循环出口产一次**，过 conclusion_gate，带 `ablation_receipts`。
- **验证脊 subagent 契约**（见 §7）。

## 7. 验证脊 subagent 契约（强制外包）

**问题**：干预（改开关 + ≥3 种子重训 + 评估 + 算 delta）耗时耗上下文。若在主 agent 里跑，会烧掉大量 token（"结论对但成本爆"）。

**契约**（写进 architecture-attribution 的 subagent-brief）：

```
每一个干预必须派一个 subagent 执行。

subagent 拿到：账本里的 1 条假设 + 它的 intervention 配置
subagent 干：  重训、评估、和噪声底比、下确认/否证/未决判定
subagent 只回：一条紧凑 receipt（配置 diff + 实测 delta + 噪声底对照 + 种子数 + 判定）
              —— 不回训练日志、不回中间产物

主 agent 只持有：假设账本 + 各条 receipt。全程不吃训练过程的上下文。
```

三个好处：
1. **主 agent 上下文恒定轻**——不管跑几轮干预，主 agent 只攒 receipt。
2. **天然并行**——多个判别力相当的假设，可多个 subagent 同时验证（引擎 Workflow 编排）。
3. **自进化直接可评分**——"该外包的干预有没有外包"是 log 里脚本可数的过程/成本指标；硬编进契约后，评分器读 receipt 数 vs 干预数即可判。

## 8. 回退：无 trainable_framework 时

architecture-attribution 需要 `trainable_framework` 材料（训练入口 + 可复现配置）才能干预。缺此材料：

- 验证脊跳过，循环退化为"生成器吐带标注的未验证假设"；
- conclusion_gate 显式标注"未验证假设"；
- **= 现状行为，对无可重训框架的老用法零破坏**（硬底线）。

## 9. 为自进化铺路（收口）

运行时的"生成→验证→精炼"与未来自进化的"提编辑→gold 验证→精炼"**同构、共用 C1/C2/C3 gold**。两层循环一套地基：

- 运行时循环：假设账本 → 干预验证 → 否证重提 → 结论。
- 自进化循环（阶段 3）：skill 编辑 → holdout 验证 → 降分回滚 → 采纳。

pilot 完成后，自进化只需优化"一条薄主脊 + 一批薄假设生成器"，而非"12 个胖结论机器"。

## 10. 验收标准（复用阶段 2 现成资产）

C1/C2/C3 三个已定稿案例盲跑（不给 gold），要求循环能：
1. 生成含正确假设的结构化账本（切片版图 + 指向组件的可否证假设）；
2. 干预否证错误假设，并留 kill-receipt；
3. 在无 `trainable_framework` 的案例上退化为"未验证假设"判定；
4. 最终只产一次结论，且架构因果表述附 `ablation_receipts`；
5. 每个干预经 subagent 执行，主 agent 上下文只见 receipt（成本轴可验）。

不需要新造数据。

## 11. 工程改动清单

| 文件 | 改动 |
|---|---|
| `playbooks/model-comparison/playbook.md` | 手术瘦身（§4）；删 Stage3/§3/§6；§8 改调色板 |
| `playbooks/model-comparison/references/figure-diagnostics*` | figure-diagnostics 降为按需选图手册（若在 model-comparison 无则复用 result-eval 的） |
| `playbooks/architecture-attribution/`（新建） | 验证主脊 playbook + subagent-brief（强制外包契约） |
| `references/engine-core.md` | 新增"假设验证循环"节（§6 控制逻辑） |
| `scripts/conclusion_gate.py` | `ablation_receipts` 字段 + 无 receipt 的架构因果结论拦截（阶段 1 A3） |
| 仓库清理 | 删 `__pycache__` 等垃圾（维护面顺带减） |

依赖：阶段 1 上游清单 A1（model-audit 产 `ablation_switches`）、A3（conclusion_gate）、噪声底产物（阶段 2 phase0 已有）。

## 12. 非目标（本轮明确不做）

- 其余 6 个分析 playbook 的转型（pilot 验证后再推广）。
- 阶段 3 自进化循环本体（本重构是其前置）。
- 纯事实生产者的改动。
- 新造评测案例。
