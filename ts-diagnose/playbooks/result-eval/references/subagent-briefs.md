# 子 agent 派发模板（固化 brief）

主 agent（负责编排的主分析代理）只做编排：把画图和事实提取外包给子 agent（subagent），**图像与逐图 stats.json 都不进主 agent 的上下文**；跨结果的归因/总结留给主 agent 最后做。派发时，把下面对应的 brief（给子 agent 的任务书）**照抄进 Agent 调用的 prompt**，并把里面的 `<...>` 占位符换成本次的实际参数。用通用子 agent（general-purpose）即可，不需要注册自定义 agent 类型。

派发纪律（来自 `superpowers:dispatching-parallel-agents`）：

- **并行**：在一条消息里发出多个 Agent 调用，它们之间没有共享状态、可以同时跑。
- **拆分单位**：优先按"一个 range/月份派一个子 agent"来拆（误差矩阵每个 range 只算一次，range 内多张图复用这份矩阵）；只有单个 range 时才按图组拆（例如 {#1,#2} / {#4,#7} / {#8} 各一个子 agent）。
- **写文件不打架**：每个子 agent 只写**自己 range 目录**下的 `ANALYSIS.md` 与图，互不覆盖。**`analysis_state.json` 与 `PROGRESS.md` 只由主 agent 写**，子 agent 不碰它们——避免并发写冲突。
- **回传要瘦**：子 agent 只回传**固定格式的现象清单**（模板见下），不回大段正文、不回图、不回整份 stats.json。

---

## Brief A：figure+fact subagent（Stage 2–3，可并行多个）

```
你是一个数据分析子 agent，只负责【画图 + 事实提取】，不做机制归因。

工作目录：<绝对路径，含 analysis_config.json 的目录>
技能目录 SKILL：<本 playbook 目录>（即 ts-diagnose/playbooks/result-eval）

任务：
1. 在工作目录跑：
     python3 "<SKILL>/scripts/run_analysis.py" --range <RANGE> --figs <FIGS>
   （做月度诊断时必画 1,2,4,8；范围如 2025-06 或 all。计算与画图都在脚本里做，不要现写 pandas。）
2. 判读时**只读 .stats.json，绝不 Read PNG**——PNG 只给人看；stats.json 已自足：里面有完整曲线/矩阵/分位数，还有形状描述符 trend/max_jump_idx/roughness。
   读整条曲线判走势，别只看单点。对号 "<SKILL>/references/figure-diagnostics.md" 的形态判读。
3. **严守 Stage 3 纪律——只写"看到了什么"，禁止机制语言**：
   - 只允许写：现象 + 数字 + 稳健性检验结果。
   - 禁止：任何"为什么/因为"；禁止引用 models.md 编机制故事；禁止推断架构原因。
     （机制归因是主 agent 的 Stage 4，不是你的活。）
4. **写"A 比 B 好"必须先过稳健性门槛**：用 data_utils.robustness_check（做 Wilcoxon 配对检验 + 剔除最差 3 天后看结论是否稳）；passed=True 才可写"A 比 B 好"，否则写成"差异不显著 / 由个别极端天驱动"。
   做分组统计前先报每组的天数，不足 10 天只描趋势、不下定论。细则见 "<SKILL>/references/analysis-discipline.md"。
5. 把每张图的结论写进 figures/<电站>/<RANGE>/ANALYSIS.md（每图一节：图名 + stats 里的关键数字 + 现象结论）。
   **不要写 analysis_state.json 或 PROGRESS.md**（那是主 agent 的事）。

只回传下面这份【现象清单】，不要回传大段正文或图：

## 现象清单（RANGE=<RANGE>）
- [现象] <一句话现象> | 数字：<关键 stats 数值> | 图：figures/<电站>/<RANGE>/<图名>.png | 稳健性：<passed/不显著/样本不足>
- [现象] ...
（每条必须带数字与图链接；没过稳健性门槛的比较不要写成"A 比 B 好"。）
```

**主 agent 收到回传后**：汇总各子 agent 的现象清单 → 回填 `FINDINGS.md`（状态="现象"）→ 更新 `analysis_state.json` + 追加 `PROGRESS.md` → **走到 Stage 3→4 停顿点**：把现象清单报给用户、由用户点名哪几条进 Stage 4。（停顿点与归因只在主 agent 做，子 agent 不能问用户。）

---

## Brief B：metric subagent（Stage 1，通常只跑一个）

```
你是一个数据子 agent，负责 Stage 1【质检 + 指标计算】。

工作目录：<绝对路径>
技能目录 SKILL：<本 playbook 目录>（即 ts-diagnose/playbooks/result-eval）

任务：
1. 跑质检：python3 "<SKILL>/scripts/run_quality_check.py"
   - 遇到硬问题（窗口一致性不过、对齐失败等）→ 立即停下，把问题原样回传主 agent，不要带病继续。
   - 可疑日写进 suspect_days.csv。
2. 按 `<本 playbook 目录>/playbook.md` 的 Stage 1，用用户指定的外部指标脚本（原体系里 metric.py 一类工具，如 SolarMetricCalculator.generate_report），对 M1-M4 + ensemble 各跑一遍，产出 5 个 Excel（五口径 × RMSE/MAE/ACC）。
   首次跑先用 inspect.signature 对号调用参数，再做一次口径对账（任选一月用 pandas 自算 RMSE 与脚本输出比对，相对差 <1% 视为一致）。
3. 产物存 figures/<留出站拼音>/（留出站名从 analysis_config.json 的 station 字段取）。不要写 analysis_state.json / PROGRESS.md。

回传【指标摘要】：各模型各口径的月度值要点 + **ensemble 是否确实优于最佳单模型、哪些月份不是** + 质检有无红旗（可疑日/缺口/窗口问题）。不要回传整份 Excel。
```

**主 agent 收到回传后**：据摘要更新 `analysis_state.json`（Stage 1 done）+ `PROGRESS.md`，向用户报指标摘要，然后继续 Stage 2。Stage 1 的收益主要在算指标（不占图像上下文），单跑一个子 agent 即可，没有强并行需求。

## Brief：模型参考——定位或生成（Stage 4 / Playbook B 前置）

触发时机：分析进入机制层（Stage 4 / Playbook B），需要"模型看得见/看不见什么"这类事实时。

1. 读消费方运行时生成的 pointer 文件：`references/model-ref.pointer`（路径相对**本次工作目录**解析，不是引擎包里的 playbook 目录）。
   - 若它存在、且 `path` 指向的 `.modelmap/models.md` 在盘上 → 直接读它作为模型参考。
     - 额外检查：`git -C <pointer.repo> rev-parse HEAD` 与 `pointer.commit` 不一致时，提示"模型档案可能已过时，建议重跑 model-audit playbook"，但先用现有档案继续（不阻塞分析）。
   - 若 pointer 不存在、或 `path` 不在盘上 → 向用户要模型代码目录路径，在该目录嵌入执行 **model-audit** playbook（orient 的 modelmap 档案闸会提示「先嵌入执行 playbook「model-audit」」，见 `engine_common.modelmap_blocker`）；产出 `.modelmap/` 与 pointer 后，再读 models.md。
2. 消费纪律：只引用带 ✅/📊/📐 标记且前提清晰的字段；带 ⚠️/待确认/缺失 的一律按未知处理，不编造。
3. 桥接假设里的 H-ID 直接对应档案中的假设登记；落 FINDINGS 前照常过 H-ID 门。
