# 子 agent 派发模板（固化 brief）+ 嵌入式主技能运行

主 agent 只做编排：跑脚本 + 读产物摘要外包给 subagent，**checkpoint/parquet 原始内容、
逐行日志、PNG 都不进主上下文**；跨证据线的综合（Stage 2 vs 3 排名一致性）、反驳门、
FINDINGS/CONCLUSION 撰写留主 agent 最后做。派发时把对应 brief **照抄进 Agent 调用的
prompt**（`<...>` 占位换实参）。用通用 subagent（general-purpose）即可。

派发纪律（沿用主技能 subagent-briefs.md + 本技能特有）：

- **并行**：一条消息里发多个 Agent 调用（无共享状态才并行；GPU 任务单卡时不要分片）。
- **subagent 只读结构化产物**：JSON/CSV/probe 样例行；绝不 load checkpoint 权重、
  不逐行读原始日志入上下文、不 Read PNG（解析/计算全在脚本里）。
- **回传要瘦**：只回传固定格式清单（各 brief 末尾规定），不回大段正文。
- **单写者**：`influence_state.json` / `PROGRESS.md` / `FINDINGS.md` /
  `influence_config.json` **只由主 agent 写**。subagent 只写脚本产物与自己的分片文件。
- **分片防竞态**：多 subagent 并发时各写各的 `--out`/`--raw` 分片文件，主 agent 收齐后合并
  （`python3 -c "import pandas as pd,glob; pd.concat(map(pd.read_csv, glob.glob('rmse_series.M*.csv'))).to_csv('rmse_series.csv', index=False)"`），
  绝不让两个 subagent 追加同一个 CSV。

---

## 嵌入式主技能运行（主 agent 的编排程序，非 brief）

**何时**：orient 报预测侧上下文 [absent] 且用户同意先跑留出站的 pv-result-analysis。
**为什么由主 agent 亲自编排**：subagent 不能再派 subagent，且主技能 Stage 3→4 的停顿
要问用户——所以嵌入运行的 Brief A/B 派发必须由主 agent 做。

```
1. mkdir <influence 工作目录>/result_analysis_<留出站拼音>/（独立目录——绝不写其他实验线的
   任何已有分析目录）。在其中写 analysis_config.json：
     station      = "<留出站拼音>"
     metric_py    = <主线同一个 metric.py>
     true_label   = influence_config.test_label（同一份留出站真值）
     predicted    = {M1..M4, ensemble: 留出站【最终模型】预测 parquet}
                    ——influence_config 里没有这些路径，向用户要；
                      逐 chunk 预测属本技能 Stage 2 的 rmse_series，不进主技能流程。
     train_stations = {全部训练站: 逐站 parquet}（可选；给了本技能 Stage 4 漂移就白捡）
2. cd 该目录跑主技能 orient；随后照主技能 references/subagent-briefs.md 派发：
   Brief B（metric）×1 → 完成后 Brief A（figure+fact）×N 并行。
   参数覆盖：工作目录 = result_analysis_<留出站拼音> 绝对路径；Brief B 原文里
   "产物存 figures/<其他实验线拼音>/" 改为 figures/<留出站拼音>/（站名以 analysis_config.station 为准）。
3. 跑到主技能 Stage 3 现象清单为止（其 Stage 4 深归因不跑——由本技能 Stage 2–5 接管）。
4. 回 influence 工作目录：往 influence_config.json 回填
   result_analysis_workdir=<该目录绝对路径> + result_analysis_status="linked"；
   把现象清单摘要（≤15 行）记入 PROGRESS.md；重跑 orient 确认 [linked]；继续 Stage 0。
```

用户拒绝 → 回填 `result_analysis_status="declined"`，继续 influence-only；
FINDINGS/CONCLUSION 里注明"缺预测侧上下文（基线指标/天气分型/数据质量未核）"。

---

## Brief C：ckpt 批量评估 subagent（Stage 2 补料，Mode B，可按模型并行）

```
你是一个计算子 agent，只负责【逐 checkpoint 重算留出站 RMSE】，不做归因分析。

工作目录：<绝对路径，含 influence_config.json 与 adapter.py>
技能目录 SKILL：/Users/tqa946816/Documents/华为/光伏预测/结果分析skill/pv-station-influence

任务：
1. 跑：python3 "<SKILL>/scripts/ckpt_eval.py" --models <M> --out rmse_series.<M>.csv \
       [--device <DEV>] [--pattern <PAT>]
   （中断可续：已算过的 (iteration,chunk) 自动跳过。缺 checkpoint 会打 [skip]。）
2. 纪律：绝不把 checkpoint 权重/预测张量读进上下文（脚本内 load→算→释放）。
   报错原样回传，不要带病继续。

只回传（≤10 行）：
- 新增行数 / 分片文件名
- 迭代覆盖：哪些 iter 齐、哪些缺
- [skip] 清单（缺的 checkpoint 路径模式）
- RMSE 序列粗貌：min / max / std（读你自己写的分片 CSV 算，一行）
```

**主 agent 收到后**：收齐各分片 → concat 成 `rmse_series.csv`（见开头合并命令）→
更新 state/PROGRESS → Stage 2 可跑。

---

## Brief D：TracIn 梯度 subagent（Stage 3，Mode B）

单卡：派 1 个跑全量（GPU 不并行时分片无收益）。多卡/多机才按 `--models` 分片。

```
你是一个计算子 agent，只负责【TracIn 梯度对齐计算】，不做升级判定。

工作目录：<绝对路径，含 influence_config.json 与 adapter.py>
技能目录 SKILL：/Users/tqa946816/Documents/华为/光伏预测/结果分析skill/pv-station-influence

任务：
1. 跑：python3 "<SKILL>/scripts/tracin_influence.py" --every <N> --n-windows <K> \
       [--models <M> --raw tracin_dots.<M>.csv --out tracin_scores.<M>.json] [--device <DEV>]
2. 纪律：梯度向量不进上下文（脚本只落标量内积）；中断可续。

只回传（≤12 行）：
- 每模型 harm 排名前 5 + 后 3（读汇总 JSON 的 ranking_harmful_first）
- 覆盖率披露：实际取了多少 checkpoint（--every）、每站多少窗口（--n-windows）
  ——抽样别让主 agent 读成全量（silent cap 必须写明）
- 汇总 JSON 里 cross_model_spearman（有就转述数字）
禁止：自行下"与 Stage 2 排名一致 → 假设成立"之类结论（升级判定是主 agent 的活）。
```

**主 agent 收到后**：分片则 concat 原始 CSV 为 `tracin_dots.csv` 后重跑一次
`tracin_influence.py`（无 --raw/--out，秒级，只做汇总）得合并版 `tracin_scores.json`；
对照 `influence_coefs.json` 算/核 Spearman → 升级判定 + 更新 state/PROGRESS。

---

## Brief E：训练动力学 subagent（Stage 1，Mode A/B）

```
你是一个数据子 agent，只负责【训练 loss 动力学提取与回归】，不解释气候机制。

工作目录：<绝对路径>
技能目录 SKILL：/Users/tqa946816/Documents/华为/光伏预测/结果分析skill/pv-station-influence

任务：
1. 若无 probe_summary.json：先跑 python3 "<SKILL>/scripts/probe_logs.py"。
2. 若 probe 报 loss_found：读 probe_summary.json 的 sample_lines.loss（只读样例行，
   不逐行读原始日志），据格式写一次性小解析器把日志落成 loss_records.csv，
   列固定：iteration,chunk,position,model,epoch,loss（step 级记录先按 epoch 聚合均值）。
3. 跑：python3 "<SKILL>/scripts/loss_dynamics.py" [--from-ckpt]（日志没 loss 且 Mode B 才
   加 --from-ckpt；需要 adapter.load_loss_history，没实现就回报"Stage 1 跳过"）。
4. 判读只读 chunk_loss_dynamics.json（自足摘要），不读 loss_records.csv 全量。

只回传（≤15 行）：
- 每模型：终态 loss 最高前 3（loss_level ranking）+ 收敛最慢前 3（conv_slope ranking），
  各标 CI 是否排除 0
- 每模型 rmse_link 数字（spearman + p + top5 同现数；没有 rmse_series 就写"未算"）
- power_note 原文 + models_without_loss（哪些模型没 loss 记录）
只报数字与排名，禁止：解释"为什么这个站难学"（气候/数据质量归因是主 agent
结合 <project-context>/stations.md / event-log 的 Stage 4+ 工作），禁止把 loss 排名说成"拖累留出站排名"。
```

**主 agent 收到后**：把清单记入 FINDINGS（状态="现象"，注明是 loss 侧现象）→
更新 state/PROGRESS。解释（气候/容量/数据质量四象限）等 Stage 2/3 排名出来后一起做。

---

## Brief F：漂移解释 subagent（Stage 4）

```
你是一个数据分析子 agent，只负责【逐站分布漂移计算 + 现象提取】，不做机制归因。

influence 工作目录：<绝对路径>
主技能 MAIN：/Users/tqa946816/Documents/华为/光伏预测/结果分析skill/pv-result-analysis
预测侧上下文：<linked 时给 result_analysis_workdir；否则写 "无">

任务：
1. 定位运行目录：
   - linked：cd <result_analysis_workdir>（其 analysis_config.json 已含 train_stations
     全部训练站路径）。若 figures/<留出站拼音>/drift/ 已有产物且新于配置 → 不重跑直接读。
   - 无 linked：在 influence 工作目录写一个**最小** analysis_config.json
     （station="<留出站拼音>"、true_label=influence_config.test_label、
     train_stations=<全部训练站逐站 parquet，向主 agent 要>）——该文件只服务 run_drift，
     不代表跑过主技能；绝不碰任何已有分析目录。
2. 跑：python3 "<MAIN>/scripts/run_drift.py" --cols "GHI-solargis,observe_power_future"
3. 判读只读 drift 产物表/脚本打印摘要，不 Read PNG。

只回传【现象清单】（仿主技能 Brief A 格式，每条带数字）：
- [现象] 逐站 GHI PSI 排名（最像留出站 → 最不像）| 数字：各站 PSI | 来源：drift 表
- [现象] 嫌疑站 <占位：主 agent 传入 Stage 2/3 top 站> 在气候距离榜第 X 位 | 数字：PSI
- [现象] "气候相似却有害"红旗站：<有则点名，无则写无> | 数字：PSI + θ/harm
（禁止"为什么"；红旗站只标记，数据质量核查是主 agent 反驳门#3 的活。）
```

**主 agent 收到后**：现象入 FINDINGS →（linked 时）对照 suspect_days/event-log 走反驳门 →
两法一致 + 有机制解释的站升"假设"（登记 H-XSTN-*）→ 决定是否进 Stage 5。

---

## 主 agent 保留清单（不外包）

问用户（嵌入决定、Stage 5 重训授权）· Stage 2 vs 3 排名 Spearman 一致性综合 ·
反驳门七条 · loss×harm 四象限解读（influence-methods.md）· FINDINGS/CONCLUSION 撰写 ·
influence_state/PROGRESS/config 更新 · 分片合并。
