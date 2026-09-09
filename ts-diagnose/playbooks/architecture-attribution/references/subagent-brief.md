# subagent 派发契约（强制外包，非可选）

## 契约（一字不改）

```
每一个干预必须派一个 subagent 执行。

subagent 拿到：账本里的 1 条假设 + 它的 intervention 配置
subagent 干：  重训、评估、和噪声底比、下确认/否证/未决判定
subagent 只回：一条紧凑 receipt（配置 diff + 实测 delta + 噪声底对照 + 种子数 + 判定）
              —— 不回训练日志、不回中间产物
主 agent 只持有：假设账本 + 各条 receipt。全程不吃训练过程的上下文。
```

这不是"建议外包"，是**硬规则**：Stage 3 的每一条干预，不管看起来多快多便宜，都必须走
subagent，不许主 agent 图省事亲自跑。同理 Stage 0 的基线重训（噪声底现算）也走
subagent——两者都是"改配置 + 重训 + 评估"的同类耗时操作。

分工原则：主 agent 只做编排——选假设、批预算、收 receipt、判定升级、写结论。
**训练日志、checkpoint 权重、中间预测张量都不进主 agent 的上下文**；解析和数值计算全部
在 subagent 内部的脚本里做。用通用 subagent（general-purpose）即可。

派发纪律：

- **并行**：预算阶梯里判别力相当、互不冲突的多条干预可以一条消息里发多个 Agent 调用
  并行验证（design doc §7 的第二个好处）；单卡训练不要对同一张卡分片。
- **回传要瘦**：只回传固定格式的 receipt 行 + 极少数摘要数字，不回大段日志或正文。
- **单写者**：`hypothesis_ledger.json` / `PROGRESS.md` / `FINDINGS.md` /
  `intervention_plan.json` **只由主 agent 写**。subagent 只写自己那条干预的 receipt 文件
  （`receipts/<hypothesis_id>.json`），不碰其他干预的产物、不碰上面四个共享文件。
- **成本轴可验**：receipt 数应等于已执行的干预数；任何一条干预如果主 agent 上下文里
  出现了训练日志片段或逐 iteration loss，都是契约违反，要在 PROGRESS.md 记一笔。

---

## Brief A：噪声底基线重训（Stage 0，`noise-floor` 问题答"需现算"时）

```
你是一个计算子 agent，只负责【同配置基线模型的 ≥3 种子重训 + 评估】，不做任何判定。

工作目录：<绝对路径>（已有 checkpoint 起点/训练入口 与 experiment_config）
技能目录 SKILL：<本 playbook 目录>（即 ts-diagnose/playbooks/architecture-attribution）

任务：
1. 用给定的 checkpoint 起点 + experiment_config，仅改随机种子（种子集：<种子列表，
   与后续干预共用同一批>），其余超参/数据/训练步数全部不变，跑 ≥3 次训练+评估。
2. 每个种子落一行到 <绝对路径>/baseline_seed_metrics.csv（列：seed,metric），口径与
   noise-floor 问题里约定的口径一致（缺省 rmse_192）。
3. 绝不把 checkpoint 权重、逐 iteration loss、训练日志读进上下文——脚本内跑、脚本内落盘。

只回传（≤8 行）：
- 每个种子的口径指标值（seed → 数值）
- mean / std（ddof=1）/ noise_floor_3sigma = std*3
- 若某个种子训练失败/发散：种子号 + 一句失败原因，不带日志片段
禁止：解释指标为什么是这个数（那是主 agent 在 Stage 0 综合的活）。
```

**主 agent 收到后**：落 `noise_floor.json`（自足 schema 见正文 Stage 0），继续切片测量。

---

## Brief B：单条消融干预（Stage 3，强制，每条干预必须独立一个 subagent）

```
你是一个计算子 agent，只负责【执行 intervention_plan.json 里的 1 条干预 + 算 delta + 判定】。

工作目录：<绝对路径>（已有 intervention_plan.json、checkpoint、experiment_config；
用户已在 intervention-budget-confirmed 问题里确认花费本轮训练预算）
技能目录 SKILL：<本 playbook 目录>（即 ts-diagnose/playbooks/architecture-attribution）
你负责的干预：<从 intervention_plan.json 里摘出的这一条：hypothesis_id / component /
              switch / kind / seeds / pred_direction / kill_criterion / confirm_criterion>

任务：
1. 只改 <switch> 这一个开关，种子固定为 <seeds>（与噪声底同批或另起 ≥3 个），其余
   超参/数据/训练步数与基线完全一致——单变量纪律不许有第二处改动。
2. 每个种子跑训练+评估，得到口径指标；delta = mean(干预后指标) − mean(基线指标)
   （基线 = noise_floor.json 里同口径的 mean，或另跑同批种子的基线均值——用哪个在
   派发时写清楚，两条干预不要混用不同基线）。
3. delta 的计算逻辑写成脚本落盘到 analysis_scripts/eval_<hypothesis_id>.py（不许
   在临时命令里散算——脚本是回执的判断依据，必须留档可查）。脚本里带一个自检
   （如切片选取逻辑的已知答案对照、植入回收），跑通后把结果压成一句话。
4. 记下干预执行的起止时刻（开跑第一个种子前、最后一次评估后，ISO8601），跑判定
   并生成 receipt 行：
   python3 "<ENGINE>/scripts/ablation_verdict.py" \
     --hypothesis-id <hypothesis_id> --switch=<switch> \
     --delta <delta> --noise-floor <noise_floor_3sigma> \
     --direction <pred_direction> --seeds <N> \
     --script analysis_scripts/eval_<hypothesis_id>.py \
     --t-start <起始时刻> --t-end <结束时刻> \
     --selftest "<自检结果一句话>" \
     --out receipts/<hypothesis_id>.json
5. 绝不把 checkpoint 权重、逐 iteration loss、训练日志读进上下文。

只回传（≤6 行，就是 receipt 本身，不要额外解释）：
- ablation_verdict.py 打印的那一行 receipt（原样，不要改措辞）
- 实际配置 diff（只列改了哪个 flag，不贴完整 config 文件）
- 若种子间指标不稳定（跨种子标准差异常大）：一句话标注，供主 agent 判"未决"时参考
禁止：自行下"confirmed 支持了整条因果结论"之类的综合判断——升级判定与结论撰写是
主 agent 的活。
```

**主 agent 收到后**：把 receipt 行原样存进 `receipts/receipts.json`（追加，不覆盖）；
把 `intervention_plan.json` 该条的 `script` 回填为 receipt 的 `produced_by`；
按 §2 Stage 3 三态规则更新 `hypothesis_ledger.json` 该假设的 `status`
（`refuted` 必须同时填 `kill_receipt`）；汇总 `verdict_summary.json`（含 `unexplained_real_slices`：
Stage 0 判 real、又没被任何干预推动的切片，逐条列名）；跑 `harvest_check.py` 收口并按 §4
向用户汇报收成、等 `harvest-decision` 答复；更新 FINDINGS/PROGRESS。

---

## 主 agent 保留清单（不外包）

问用户（噪声底来源、账本来源、干预预算确认、收成后的下一步 `harvest-decision`）· 假设按判别力排序拍板 ·
干预设计的单变量/双向可判合规性判断 · 收 receipt 后的三态判定与账本状态更新 ·
三道门 + 本 playbook 特有反驳门 · FINDINGS/CONCLUSION 撰写 · conclusion_gate 前的
`## 消融证据` 组装 · `hypothesis_ledger.json`/`intervention_plan.json`/PROGRESS/FINDINGS
的全部写入。
