# CHANGELOG —— ts-diagnose

<!-- 每行：日期 | 改了哪个文件的哪节 | 触发这次改动的反馈原文（一句话） | 为什么这么改 -->

- 2026-07-14 | 首版落地（机制层 + SKILL + references 五篇 + playbook 三个） | 用户："现有技能针对特有情况写死，需要提取 workflow 做泛化技能，不确定时必须问用户，且要能固化回专用技能" | 引擎+playbook+profile 三层：workflow 与领域解耦；设计 spec 见 docs/superpowers/specs/2026-07-14-ts-diagnose-engine-design.md
- 2026-07-14 | 验证记录 | —— | 机制层 pytest 23 项全绿；training-sufficiency 合成数据影子验证全程走通（植入效应 m03/m08 均召回、五个验证步 PASS、必答题零跳过）；robustness / feature-importance orient dry-run 通过；crystallize 固化演练三步验证（冷启动 --profile / 快照冒烟 / 影子重跑 Stage 0 一致）全 PASS
