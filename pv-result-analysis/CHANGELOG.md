# 变更日志

<!-- 每次改动技能文件追加一行。格式：
     日期 | 改了哪个文件的哪节 | 触发这次改动的反馈原文（一句话） | 为什么这么改
     由 SKILL.md「运行后回顾」小节要求维护。变更可追溯 = 改错了能回滚。 -->

| 日期 | 改动 | 触发反馈 | 原因 |
|------|------|---------|------|
| 2026-07-08 | 新建 `references/hypotheses.md`；`SKILL.md` 加"假设登记 + 反驳门 + 运行后回顾"三节、两个 Playbook 收尾各接反驳门、references 表加一行、常见错误加两条；新建本 `CHANGELOG.md` | 用户问 AutoResearch/CORAL/GEPA 等论文技术能否用于本技能，提升"为什么 A 比 B 好"结论的可解释性与可信度 | 落地核心三件套：①假设登记表（DiscoveryBench 式预注册可判别预测，防事后编故事）②反驳门（多 agent 辩论验证的单机提炼，结论升级前强制排除替代解释）③GEPA 式运行后回顾（用文字反馈定向修正技能文件 + 变更可追溯）。均为流程纪律层，不动计算层 scripts/ 与指标口径 |
| 2026-07-09 | `SKILL.md` 新增"执行流程：四个阶段"总纲，Step 1/2/3、Playbook 加阶段标记，FINDINGS 状态枚举加"现象"；`pv-analysis-resume/SKILL.md` 跳过规则表加阶段入口说明 | 用户要求把一口气跑完的流程拆成四阶段（载数据算指标→相关性→事实提取→深归因），避免产出过长、避免在归因上浪费在用户不关心的现象 | ①Stage 3（只写现象 + 数字）与 Stage 4（才允许"为什么"，引 references + 假设 ID + 过反驳门）物理隔开，防事后编故事、把最贵的步骤只花在用户点名项；②Stage 3→4 设唯一强制停顿点，1→2→3 连续跑；③阶段进度靠产物判定，与续跑跳过规则天然对齐，不新增状态文件 |
| 2026-07-09 | `SKILL.md` 四阶段总纲加"ensemble 的分析边界"段 | 用户：ensemble 是均值组合、无独立机制，指标要报告但深入分析应聚焦 M1-M4 | ensemble 无独立特征（models.md 该节空），机制层只做 M1-M4；"ensemble 为什么好/不好"改由图#2 成员分散度 + 图#9 oracle 差距回答，不编独立机制故事 |
| 2026-07-09 | `scripts/plots.py` `fig02_error_corr` 长模型名改短编号刻度 + 底部图例映射，by_month 只首分面画 y 标签，stats.json 加 `labels` 映射（corr 键保持全名） | 用户：热力图行列标签是模型全名（fourierMoBA/PatchTST…），逐月分面时互相压叠成一团 | >4 字符名用编号，映射放图例；短名（M1/M2）保留原样；下游读 stats 的代码不受影响 |
| 2026-07-09 | `pv-analysis-resume/SKILL.md` description 加"直达 Stage 4 深归因"触发词，Step 2 拆成路径 A（可视化续跑）/ 路径 B（现象已看完直达 Stage 4） | 用户问：现象都看完了想只做深度归因（结合电站+模型讲为什么），怎么让 resume 触发 Stage 4 | 原触发词只有"画图/相关性"，深归因请求命不中；补入口的同时明确前提（FINDINGS 有带图链接的"现象"条目）、读什么（现象 stats + references 全套 + 假设 ID）、何时仍需重算（缺的图才补画） |
| 2026-07-09 | `pv-analysis-resume/SKILL.md` 路径 B 现象来源改为四级优先级（FINDINGS→ANALYSIS.md+stats.json 兜底重建并回填→纯 PNG+stats 现读→都没有退路径 A），Step 0 读结论同时读 ANALYSIS.md，归因所依据的核心图必 Read PNG | 用户：FINDINGS.md 是模型手写软产物、在另一台服务器跑没生成；那次有 ANALYSIS.md + 图 | FINDINGS 无脚本生成、不保证产出，硬依赖它会让路径 B 前提常失败退回重跑；ANALYSIS.md + stats.json 已承载现象，据此兜底重建并回填 FINDINGS 让后续会话稳定；顺带修正"新会话没画过图、只读 JSON 漏形状证据"——核心图必看 PNG |
| 2026-07-09 | `references/models.md` M1-M4 各加"代码类名"字段（FourierMobaTransformer / PatchRegForcast / MoiraiPvForecaster / PatchTSTPvForecaster）；`pv-model-verify/SKILL.md` 定位步骤改为类名 grep 首选、架构签名兜底，签名表补 M2 行 | 用户提供 M1-M4 实际代码类名 | 类名是比架构关键词可靠得多的定位符，pv-model-verify 可直接 grep 直达定义；M2 类名拼写 Forcast/Reg 与 M3/M4 不一致，记容错前缀 PatchReg 并注明以代码为准 |
| 2026-07-09 | M2 类名笔误修正 `PatchRegForcast`→`PatchRegForecast`（models.md + pv-model-verify） | 用户确认代码里是 PatchRegForecast，Forcast 是笔误 | 精确串修对，容错前缀 PatchReg 保留 |
| 2026-07-09 | `SKILL.md` 新增"面向主管的结论汇报（CONCLUSION.md）"一节 + 四阶段表 Stage 4 交付物加 CONCLUSION.md；`pv-analysis-resume` 加"只写主管总结"路径与触发词 | 用户：ANALYSIS.md/FINDINGS.md 很好但太严谨、表格太多，主管读不直接；需要一份面向主管、有数据支撑但逻辑清晰的 conclusion.md | 三文档金字塔按读者分工：CONCLUSION 面向主管=把已成立结论翻译成管理层语言（叙述优先、全文表格≤1 张、方法论机器不进正文、金字塔先结论、结尾给建议、只写站得住的），不产生新结论只综合 FINDINGS 已证实条目 |
| 2026-07-09 | 天气分型从四类改五类：`data_utils.daily_weather_class` 启用此前未使用的 kt_lo，阴稳改为 kt<0.35 的真正厚云阴天，新增"多云平稳"（0.35≤kt<0.65）默认档；`plots.py` fig08 order、SKILL.md 三处、scripts/README、models.md/hypotheses.md 序号引用同步 | 用户发现 kt_lo 参数定义了却没用、"阴稳"实为兜底类（中等 kt 的日子也被划进阴稳）；要求改成真正的阴稳 | 低波动日按 kt 分三档（晴稳/多云平稳/阴稳）语义更准，图#8 归因与占比分解更清晰；"第四类"等位置序号改为"突变日组"避免与类数耦合；合成数据验证三档 kt 边界正确、fig08 五类出图正常 |
| 2026-07-09 | 分布漂移诊断固化成可跑代码：`data_utils` 加 `clear_sky_envelope`/`daily_kt_sigma`（从 daily_weather_class 抽出，daily_weather_class 加 envelope/sig_hi 可选参数）、`drift_table`（特征+标签漂移逐变量逐月 PSI/KS 数值表）、`weather_class_drift`（天气型漂移，用 2024 共享基准）；SKILL.md Step 1 加载 train_set 并抽查、分布漂移诊断节加标准命令序列；scripts/README 函数索引更新 | 用户：分布漂移是重要后续建议，训练/测试都按 list 存（timestamp=序列起点），要 Step 1 也 load 训练集、并把这个 test 写进 script 让技能直接用 | 画图层(fig11/12)早已有，缺的是 Step1 载 train + 把 rebuild_series 对各变量接线的驱动函数；天气型跨年对比的命门是共享基准——各年自归一化会把"整体变暗/更多波动天"抹平，故 weather_class_drift 强制用 2024 包络+σΔ 阈值分类 2025；合成数据验证：变暗被 kt 中位数 0.78→0.48 捕捉、默认路径与 fig08/11/12 回归通过 |
