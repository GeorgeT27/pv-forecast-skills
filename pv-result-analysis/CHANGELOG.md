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
