---
name: pv-station-influence
description: 光伏多站分块训练的「站点影响力归因」——找出 17 站联合训练里哪些站拖累了留出测试站（白马湖）的零样本预测（负迁移），并解释训练动力学（为什么不同 iteration/chunk 的 training loss 不同）。当用户说"哪个站拖累白马湖/哪些训练站有负迁移/为什么每个 chunk 的 RMSE 上下震荡/为什么有的 chunk loss 更高、收敛更慢/某些站是不是在帮倒忙/17 站里挑出该剔除的站/训练集构成对某站的影响/先做白马湖结果分析再归因"时使用。区别于 pv-result-analysis（单次预测结果评估）与 pv-model-verify（模型档案代码核验）：本技能做的是**训练集构成 → 目标站性能**的归因；它会检测/复用白马湖线 pv-result-analysis 的产物作预测侧上下文，没跑过会先问用户要不要嵌入跑。两种证据模式：只有预测/日志走观测归因（Mode A，零 GPU），有 checkpoint 可进一步做梯度与重训确认（Mode B），模式由 config 自动识别。
---

# 光伏站点影响力归因（负迁移诊断 + 训练动力学）

**问题**：17 个电站分块联合训练（每迭代把 17 站随机重排进 4 个 chunk = 3×5+2，每 chunk 20 epoch，M1–M4 各自训后取平均 ensemble），留出测试站**白马湖**（江苏平原，不在 17 站内）。每 chunk 后白马湖零样本 RMSE **上下震荡不单调**，怀疑某些站负迁移。目标：**找出拖累白马湖的站，给证据，顺带解释训练 loss 为什么因 chunk 而异，再决定怎么处理。**

## ⚠️ 首要框定：震荡本身不是罪证

顺序分块训练下 RMSE 震荡是**预期现象**，不是异常——连训某 5 站 20 epoch 会把模型拉向那批站的气候（灾难性遗忘动力学），就算 17 站全是好站也会震。所以"有害"必须定义为：**训练到站 X 会系统性地把白马湖 RMSE 推高**，在大量随机 chunk 上估计其边际效应。好在**每迭代重新随机分组 = 一场天然随机化实验**——我们利用它，而不是跟震荡较劲。别一看到某 chunk RMSE 跳升就归咎当时的站，那可能只是遗忘。同理 **loss 高≠有罪**（loss 是训练站自己的量，"难学"≠"害白马湖"，见 references/attribution-discipline.md）。

## 两种证据模式（由 config 自动识别，不用预选）

Mode B = Mode A + checkpoint 专属阶段。orient 看 `influence_config.json` 有没有可用 `checkpoint_dir` 自动判定。

| | **Mode A 观测归因（只有预测/日志）** | **Mode B 干预确认（有 checkpoint）** |
|---|---|---|
| 输入 | 逐 chunk 白马湖 RMSE 序列 + 种子回放代码（+日志里的 loss） | Mode A **加** ~300MB checkpoint + 训练代码 |
| 阶段 | 0 回放 → 1 动力学（日志有 loss 才可）→ 2 影响力回归 → 4 漂移解释 | 上面全部 **加** 3 梯度 TracIn + 5 微调探针/剔除重训（且 1 可 --from-ckpt） |
| 证据 | 嫌疑站**相关性排名** + loss 侧现象 | 独立方法佐证 + 因果确认 |
| 算力 | 几乎零 GPU，纯统计 | GPU 前/反向 + 少量重训 |

**关键前置（用户当前不确定）**：Stage 2 的因变量是"逐 chunk 白马湖 RMSE"，Stage 1 的原料是"逐 epoch training loss"。**任何一次进入，orient 之后第一件事是 `probe_logs.py` 一次探两样**——据 `probe_summary.json` 决定路线：RMSE 入了日志则 Mode A 全程零权重，没入则靠 ckpt_eval 重算；loss 没记且拿不到 checkpoint 内 loss 则 Stage 1 跳过（不阻塞）。

## Step 0：Orient —— 每次进入先定位模式、上下文与阶段

```bash
python3 "<SKILL>/scripts/run_orient.py"          # 报模式 A/B + 预测侧上下文 + 当前阶段 + 前置 ✓/✗
python3 "<SKILL>/scripts/run_orient.py" --goto 4 # 想直达某阶段：校验前置
```

（`<SKILL>` = `/Users/tqa946816/Documents/华为/光伏预测/结果分析skill/pv-station-influence`。）orient 真相以产物为准：重扫 `assignments.csv`/`chunk_loss_dynamics.json`/`influence_coefs.json`/`tracin_scores.json`/`FINDINGS.md`，报第一个未完成阶段；同时报**预测侧上下文**状态（见下节）。没有 config → 回 Step 1 收集路径。

## 预测侧上下文：与 pv-result-analysis 的接续

本技能 = 主技能 pv-result-analysis 的训练侧延伸：归因要以白马湖的**预测侧分析**（指标基线、天气分型、数据质量、现象清单）为上下文。orient 按 `result_analysis_workdir`/`result_analysis_status` 三分支：

- **linked**（目录有效且 station=白马湖）→ 直接消费：指标 Excel=白马湖基线；`weather_class.csv`=天气分型条件；`suspect_days.csv`=反驳门#3 数据质量证据；FINDINGS 现象=归因素材；`figures/baimahu/drift/`=Stage 4 直接复用。station 不匹配（如指到雅砻江线）→ orient 红字警告，**拒绝消费**。
- **null（还没问过）→ 必须先问用户**：要不要先跑主技能 Stage 1–3？同意 → **嵌入式运行**：建独立目录 `<cwd>/result_analysis_baimahu/`（绝不写雅砻江线目录），按 `references/subagent-briefs.md`「嵌入式主技能运行」节由主 agent 派 Brief B→A 跑到现象清单为止，回填 config 两字段；用户不用切技能。
- **declined**（用户拒绝）→ 继续 influence-only，FINDINGS/CONCLUSION 注明"缺预测侧上下文"。

## Step 1：收集路径 + 探日志

向用户要齐（缺就问，别猜），写 `influence_config.json`（字段说明见 `scripts/si_common.py` 头部）：

- `test_label`：白马湖 true_label parquet（算 RMSE 的真值）。
- `stations`：17 个训练站的稳定 id/名（**顺序即回归设计矩阵列序**）。
- `sampler.seeds` + `sampler.n_iters`：种子与**实际跑过的迭代数**（决定统计功效）。
- `train_repo`：训练代码仓库根（Mode B 的 adapter 从这里导入采样器/模型类）。
- `log_dir`：训练日志目录（探 RMSE 与 loss 是否入日志）。
- `checkpoint_dir`：给了就解锁 Mode B（含 optimizer state 更好）。
- `result_analysis_workdir` + `result_analysis_status`：预测侧上下文（见上节；没问过先留空，orient 会提示）。

然后 **`python3 <SKILL>/scripts/probe_logs.py`**：一次探两样、落 `probe_summary.json`——
①白马湖逐 chunk RMSE：找到 → 解析成 `rmse_series.csv`（列 `iteration,chunk,position,model,rmse`）走 Mode A；没找到 + 有 checkpoint → `ckpt_eval.py` 重算；没找到 + 无 checkpoint → Stage 2 阻塞。
②training loss：找到 → 按样例行写小解析器落 `loss_records.csv`（列 `iteration,chunk,position,model,epoch,loss`）；没找到 + Mode B → `loss_dynamics.py --from-ckpt`；都没有 → Stage 1 跳过（orient 不阻塞）。

**环境**：`python3 -c "import pandas,numpy,scipy,pyarrow"`；缺则 `pip install -r 结果分析skill/requirements.txt`。Mode B 另需你训练环境的 torch 等（在 adapter 里 import）。

## 六个阶段（每阶段一个脚本，产物落盘自足，可断点续跑）

| 阶段 | 模式 | 做什么 | 脚本 → 产物 |
|------|------|--------|-------------|
| **0 回放** | 两者 | 种子重跑采样还原每 chunk 组成；Mode B 加 checkpoint 指纹抽查验证 | `replay_assignments.py` → `assignments.csv` |
| **1 动力学** | A(日志)/B(ckpt) | 逐 chunk loss 水平/收敛斜率 ~ 站成员回归；关联白马湖 RMSE 震荡。**无 loss 记录则跳过不阻塞** | `loss_dynamics.py` → `chunk_loss_dynamics.json` |
| **2 回归** | A | ΔRMSE(chunk 前后) ~ 17 站成员 + 控制；站系数>0 且 CI 排除 0 = 嫌疑 | `influence_regression.py` → `influence_coefs.json` |
| **3 梯度** | B | TracIn：站梯度·白马湖梯度，持续反向 = 负迁移；与 Stage 2 排名对照 | `tracin_influence.py` → `tracin_scores.json` |
| **4 漂移** | 两者 | **复用** `pv-result-analysis/scripts/run_drift.py` 逐站 PSI/天气型/kt，解释"为什么"：气候距离；linked 时直接消费已有 drift 产物 | 现象/假设条目 |
| **5 确认** | B | 只对 top 2–3：单站微调探针 → 剔除重训 vs 原 17 站，五口径 + Wilcoxon | 已证实条目 + `CONCLUSION.md` |

方法细节（动力学指标/四象限/回归设计/和为零参数化/TracIn 符号/回放失效的指派问题兜底）见 `references/influence-methods.md`。

## 编排：主 agent 调度，重活外包 subagent

重活（逐 checkpoint 评估、TracIn、动力学提取、嵌入跑主技能、逐站漂移）外包 subagent，固化 brief 见 `references/subagent-briefs.md`：

| 谁 | 做什么 |
|----|--------|
| 主 agent | 问用户（嵌入决定/重训授权）、嵌入式主技能编排、两法排名一致性综合、反驳门、FINDINGS/CONCLUSION、state/PROGRESS/config 更新、分片合并 |
| Brief C | Stage 2 补料：ckpt_eval 按模型分片（`--out` 各写各的，防并发竞态） |
| Brief D | Stage 3：TracIn（单卡单跑全量，多卡才分片） |
| Brief E | Stage 1：probe→解析 loss→loss_dynamics，只回数字排名 |
| Brief F | Stage 4：run_drift 逐站漂移，回现象清单 |

**单写者纪律**：`influence_state.json`/`PROGRESS.md`/`FINDINGS.md`/`influence_config.json` 只由主 agent 写；subagent 只读 JSON/CSV（checkpoint/原始日志/PNG 永不进上下文）、只写脚本产物与自己的分片文件。

## 结论纪律（下结论前必过——细则见 references/attribution-discipline.md）

1. **震荡≠有罪**：任何"某站有害"必须是跨多个随机 chunk 的**系统性**效应（回归/梯度），不是单个 chunk 的跳变。
2. **loss 高≠有罪**：Stage 1 的 loss 效应是"难学"排名（机制线索），不是负迁移排名；loss 低但 harm 高才是分布冲突的典型指纹（四象限见 influence-methods.md）。
3. **两法一致才升级**：Stage 2（回归）与 Stage 3（梯度）是两条独立证据线；只有排名一致（报 Spearman）才把嫌疑站从"现象"升"假设"。
4. **功效诚实**：迭代数 < 10 只报排名、不报显著性。分组样本不足只描述、不定论。
5. **反驳门**（借 `pv-result-analysis/references/analysis-discipline.md` 的七条）：标"已证实"前排除替代解释——尤其**气候相似的站却显示有害 = 数据质量红旗**（限电/坏 NWP），走 suspect_days/event-log（linked 时现成），别当成"该剔除"。
6. **只有 Stage 5 剔除重训在五口径 + Wilcoxon 上改善白马湖，才标"已证实"。** 其余一律"现象/假设"。

## 上下文预算纪律（执行 agent 仅 256k）

同 pv-result-analysis 的"不读图"教训——流水线死于**累积**：

- 每阶段独立脚本 + 落盘产物（`assignments.csv`/`rmse_series.csv`/`loss_records.csv`/`chunk_loss_dynamics.json`/`influence_coefs.json`/`tracin_scores.json`，各带自足 summary）。脚本只 print ≤30 行摘要。
- **checkpoint/parquet 内容永不进对话**：重活全在脚本内（load→算→释放），`ckpt_eval.py`/`tracin_influence.py`/`loss_dynamics.py --from-ckpt` 结果追加落 CSV、可中断续跑。
- 一次会话可只跑一个阶段；`PROGRESS.md` + orient 保证下次无缝续跑。报告（`ANALYSIS.md`/`FINDINGS.md`）每阶段增量写，不留大合成 pass。

## 常见错误

- ❌ 把某个 chunk 的 RMSE 跳升直接归咎当时 chunk 里的站（可能只是灾难性遗忘，不是负迁移）。
- ❌ 把站的 loss 效应（Stage 1）当负迁移排名写进结论——loss 是训练站自己身上的量，"难学"≠"害白马湖"。
- ❌ 跨模型 pool loss 数值（M1–M4 损失函数/量纲不同，只能比 Spearman 排名）。
- ❌ 迭代数太少（<10）还报"某站显著有害"（功效不足，只能排名）。
- ❌ 只信 Stage 2 回归就下结论，不做 Stage 3 梯度佐证（单证据线易被 RMSE 噪声带偏）。
- ❌ 气候与白马湖相似的站显示有害，却不查是不是数据质量问题（限电/坏 NWP）就判"剔除"。
- ❌ 回放没做指纹校验就全信 assignments（RNG 版本漂移会让分组错位，见 influence-methods.md 兜底）。
- ❌ 把 checkpoint 权重/预测张量读进对话上下文（256k 会爆；一切在脚本内落盘）。
- ❌ 没跑 Stage 5 剔除重训就把嫌疑站标"已证实有害"（相关 ≠ 因果）。
- ❌ 预测侧上下文 [absent] 却不问用户就直接开跑（或嵌入运行写进雅砻江线目录/复用雅砻江 analysis_config.json）——这是**并行的另一条实验线**（白马湖/17 站），两者独立。

## 运行后回顾

每次实跑把暴露的问题写回：脚本 bug → 改 `scripts/`；采样/模型接缝变化 → 改 `scripts/adapter_template.py` 说明；确认的项目事实 → 记忆 + `pv-result-analysis/references/station.md`（白马湖背景）。给未来训练的建议固定写进结论：**逐 chunk 组成与逐 epoch loss 直接落结构化日志**（Stage 0/1 的存在只因当初没记），并考虑混站 batch / 小回放缓冲抑制遗忘震荡。
