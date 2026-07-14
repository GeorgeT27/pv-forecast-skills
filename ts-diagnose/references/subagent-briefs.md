# 子 agent 派发模板（参数化 Brief）

<!-- 泛化自两个专用技能的 subagent-briefs：那边的 Brief 绑定具体脚本与站点，
     这里的 Brief 绑定"角色 + 纪律 + 回传格式"，具体任务由主 agent 按 playbook 菜谱填。 -->

主 agent 只做编排：提问、升级判定、反驳门、FINDINGS/CONCLUSION、state/config 更新、分片合并。
重活（大日志解析、批量计算、逐产物事实提取）外包 subagent（general-purpose 即可），派发时把
brief **照抄进 Agent prompt**（`<...>` 占位换实参）。

派发纪律（全部 brief 共用）：

- **并行**：一条消息发多个 Agent 调用（无共享状态才并行；GPU 任务单卡不分片）。
- **单写者**：`diagnose_config.json` / `diagnose_state.json` / `PROGRESS.md` / `FINDINGS.md`
  只由主 agent 写。subagent 只写脚本产物与自己的分片文件。
- **分片防竞态**：并发时各写各的 `--out <name>.<shard>.csv`，主 agent 收齐后合并；
  绝不让两个 subagent 追加同一个文件。
- **上下文纪律**：subagent 只读结构化产物（JSON/CSV/样例行），不读 PNG、不逐行读原始日志、
  不 load 大二进制进上下文（一切在脚本内 load→算→释放）。
- **无提问权**：缺信息/报错**原样回报**主 agent，不自行假设、不带病继续。
- **回传要瘦**：只回 brief 规定的固定格式清单（数字+排名+覆盖披露），不回大段正文。

---

## Brief-COMPUTE：计算子 agent（生成/运行分析脚本，产出落盘）

```
你是一个计算子 agent，只负责【<任务一句话，如：loss 曲线提取与动力学指标>】，不做归因分析。

工作目录：<绝对路径，含 diagnose_config.json>
引擎目录 ENGINE：/Users/tqa946816/Documents/华为/光伏预测/结果分析skill/ts-diagnose
playbook 菜谱：读 <ENGINE>/playbooks/<id>.md 的「Stage <N>」节，照它的伪代码/公式/产物 schema 写脚本。

任务：
1. 把脚本写进 analysis_scripts/<name>.py（已存在且本次无 schema 变化 → 直接复用别重写）。
2. 先跑菜谱声明的**验证步**（对账/合成小样/植入回收），验证不过就修脚本，禁止跳过。
3. 验证过了再跑真数据，产物落盘：<产物文件名>（按菜谱 schema，带自足 summary）。
4. 纪律：原始数据流式处理不进上下文；报错原样回传。

只回传（≤12 行）：
- 验证步结果（哪个验证、数字、过/不过）——主 agent 要把它记进 PROGRESS.md
- 产物文件名 + 关键 summary 数字（≤5 个）
- 覆盖披露：处理了多少 series/单元/行，缺口清单
- 抽样/截断披露（如有）
禁止：解释机制、下"某成员有害"类结论（升级判定是主 agent 的活）。
```

## Brief-FACT：事实提取子 agent（现象清单，禁机制语言）

```
你是一个事实提取子 agent，只负责【从分析产物提取现象清单】，不解释机制。

工作目录：<绝对路径>
输入产物：<json/csv 列表，如 dynamics_metrics.json, composition_effects.json>
（只读这些产物的 summary 字段；需要画图按 config.questions.fig-style 的答案画进 figures/，
 每图配自足 stats.json，判读读 json 不读 PNG。）

只回传【现象清单】（≤15 条，每条固定格式）：
- [现象] <观察一句话> | 数字：<关键数值> | 来源：<产物文件>
句式约束：只写"是什么"（分布/排名/差异/趋势 + 数字），禁止"因为/说明/导致/可能是"。
主 agent 会把清单挑选后落 FINDINGS.md（状态=现象）并向用户停顿汇报。
```

## Brief-EMBED 提示（嵌入运行其他技能）

playbook 的 context 需要嵌入跑**另一个技能**（如先跑某个专用技能建立上下文）时，
**由主 agent 亲自编排**（subagent 不能再派 subagent，且被嵌入技能自己的停顿点要问用户）：
建独立子目录（绝不写其他实验线/已有分析目录）→ 照被嵌入技能的 SKILL.md 走到 playbook
需要的阶段为止 → 回填本工作目录 config 的 `<workdir_key>` + `<status_key>="linked"` → 重跑 orient 确认。
