# 阶段 3：skill 优化循环（自进化）

三阶段总览：阶段 1 = 造能力，阶段 2 = 造裁判，**阶段 3（本报告）= 造优化器**。前置：阶段 1 playbook 可运行、阶段 2 评测集 ≥10 案例定稿。

## 1. 选型结论（2026-08-06 deep research，103 agent，17 论断经 3 票对抗验证）

**采用：GEPA 式循环，先手动驱动，后自动化。不整体采用 SkillOpt。**

依据：
- **SkillOpt（MSR）**排除的三个原因：① 优化目标是单文件 `best_skill.md`，多文件技能（SKILL.md + 12 playbook + references）无文档支持；② 数据需求 "a few dozen" 案例 + 强制 3-way train/val/test 切分，超出 10–15 案例预算；③ 其 vs GEPA 的 52-cell 全胜对比出自 SkillOpt 团队自家基准（利益相关）。
- **GEPA** 可行的依据：最低 3 例可用；生产报告（Decagon）~20 例达峰值、20–100 例优于 500 例；<200 例官方建议 50/50 train/val；原生支持多模块系统与 rubric+文字双通道反馈；已有 Claude Code skill 专用适配开源项目（rartzi/ClaudeSkills-Optimizer-GEFA）。注：GEPA 侧论断因会话限额未完成对抗验证，但均出自一手文档。
- **无 gold 的自监督方案（SSO / ACE 无标签模式 / SRT 多数票）在归因场景全部不可信**：LLM judge 没有 gold 无法判定真因，只会奖励"听起来合理"——正是要消灭的泛化答案模式。

**三处借用**：
1. SkillOpt 的**验证门纪律**：每个编辑必须在 holdout 上不降分才采纳；
2. GEPA 的 **Pareto 候选保留**：不只留一个最优版本，保留在不同案例上各有所长的版本再合并互补改动；
3. ACE 的**条目级增量编辑**：对 playbook 做条目 delta 更新、不整文件重写，防 brevity bias / context collapse（多文件长文档技能的关键）。

## 2. 每轮循环的具体流程

```
快照 → 盲跑 → 评分 → 反思归因 → 条目编辑 → 验证门 → 回归
```

1. **快照**：`cp -r` 当前 skill 版本存档（版本号递增）。
2. **盲跑**：每个案例派一个 subagent，带当前 skill 分析冻结产物（`artifacts/` 只读，**不给 case.json / gold-reasoning**）。每案例跑 2 次取均值（对冲 LLM 方差）。

   **硬前置：必须开轨迹埋点**，否则第 4 步无轨迹可读。埋点默认关（`SKILL_EVOLVE_TRAJECTORY_AGENT` 未设置时零行为，见阶段4 §271），有两路：

   - **orient 内嵌**（`scripts/eval_trajectory.py`）：记 route / blocked / phase_enter / phase_exit / phase_skip / workflow_complete；
   - **PostToolUse hook**（`hooks/stage_probe.py`）：记 segment_enter / segment_exit / gate_report / artifact_write / config_changed，**agent 忘跑 orient 时也有**，须在 `settings.json` 注册才生效。

   ⚠️ **不许用 `export`**：Claude Code 的 Bash 工具每次调用是独立 shell，环境变量不持久，`export` 后下一次调用即失效。必须每次前缀式带：

   ```bash
   SKILL_EVOLVE_TRAJECTORY_AGENT=<run-dir>/trajectory.jsonl \
     python3 <ENGINE>/scripts/orient.py --playbook <id>
   ```

   自检：orient 每次输出应含 `📈 轨迹埋点已开 → <path>（本次 +N 事件）`；跑完 `wc -l trajectory.jsonl` 必须非空。**没有这行 = 埋点没生效 = 本次盲跑对第 4 步无效**。

   另：subagent 的 transcript 事后不可回收（`tasks/*.output` 只留指针）。轨迹只记阶段与产物边界，记不下「为什么没想到某个维度」——这类归因材料必须由盲跑 agent 当场写进 `PROGRESS.md`（每进一个 Stage 先写维度决策段：考虑了哪些、选了哪些、排除哪些及原因，「没想到」是合法答案）。

   > 沿革：2026-08-24 首轮 C4–C7 盲跑四场轨迹全丢，即因本步骤缺此前置——阶段4（08-21 实施）新建的埋点能力未回写进阶段3（08-06 定稿）的流程。补记于此。
3. **评分**：结论层脚本精确匹配 + 过程层 LM judge 对照 gold-reasoning.md（rubric 见阶段 2 报告 §5）。
4. **反思归因**（GEPA 反思步）：读失败案例的完整 transcript，把失败定位到具体 playbook/环节——"切片没做" vs "假设不指向组件" vs "否证后硬编故事"。注意：这一步本身就是对失败轨迹的归因，与技能的业务逻辑同构。
5. **条目编辑**（ACE 式）：针对失败环节产出条目级 diff，附"为什么这条编辑能修这个失败"的说明。
6. **验证门**（SkillOpt 纪律 + 人审）：diff 先过人审（防 rubric-hacking：技能学会背答案格式而非学会归因）；采纳后在 holdout 上跑，**不降分才保留**，降分则回滚进负反馈记录。
7. **回归**：全量案例重跑，记 train 分与 holdout 分差（过拟合监控指标）。

## 3. 数据划分与防过拟合

- 10–12 案例迭代 + 3–5 holdout（小样本下贯彻 GEPA 的 50/50 精神做出的妥协）。
- **holdout 轮换**：每 2–3 轮把 1 个 holdout 换入训练、补 1 个新案例进 holdout。
- **案例记忆化对抗**：定期做改述变体（同一案例换模型名/数字/切片标签），技能若在变体上掉分即为背题，触发回滚。
- **最终迁移检验**：全部循环结束后在用户 PV 真实框架案例上抽查（该案例从未进过任何循环）。

## 4. 终止条件

- 连续 2 轮 holdout 无显著提升（loop-until-dry）；或
- 归因准确率达标（见 §6）；或
- train-holdout 分差持续扩大（过拟合信号，停机回滚）。

## 5. 附带产出：v1 vs v2 的 A/B

同一评测集直接量化 ts-diagnose（实时 Brief）vs ts-diagnose-v2（预定义卡片派发）的归因准确率——即此前计划的派发层 A/B（见 2026-08-04 卡片版记录）。零额外成本，第一轮盲跑时两版各跑一遍即可。

## 6. 成功指标

| 指标 | 定义 | 目标 |
|---|---|---|
| 归因准确率 | 结论层组件命中率（Tier 1+2） | 基线测定后 +30pp 或 ≥80% |
| 否证识别率 | N 类案例上正确判"不显著"的比率 | ≥80%（当前预计接近 0） |
| 三条腿完整率 | Tier 2 结论含测量+假设+干预三要素的比率 | 100%（结论闸硬约束） |
| 泛化答案率 | 只读指标无归因的结论占比 | → 0 |

## 7. 自动化路线

- 第 1–2 轮：手动驱动（skill-creator 循环骨架），人在第 4、6 步。
- 第 3 轮起：盲跑/评分/回归脚本化（Workflow 编排 subagent 并行盲跑）。
- 稳定后：评估接入 gepa 库或 ClaudeSkills-Optimizer-GEFA 做候选生成，人只审 diff；夜间自动回归（借 SkillOpt-Sleep 的形态、不用其实现）。

## 8. 风险与对策

| 风险 | 对策 |
|---|---|
| rubric-hacking（背格式不学归因） | 人审 diff + 改述变体测试 + decoy 倒扣分 |
| 评测集小、评分方差大 | 每案例 2 次重复取均值；z 检验才认提升 |
| 过拟合 ETT 域 | holdout 轮换 + PV 真实域最终迁移检验 |
| LM judge 偏好流利叙事 | 过程层只对照 gold-reasoning 检查步骤存在性，不评文采；结论层纯脚本匹配 |
