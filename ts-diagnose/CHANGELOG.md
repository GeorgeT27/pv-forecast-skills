# CHANGELOG —— ts-diagnose

<!-- 每行：日期 | 改了哪个文件的哪节 | 触发这次改动的反馈原文（一句话） | 为什么这么改 -->

- 2026-07-14 | 首版落地（机制层 + SKILL + references 五篇 + playbook 三个） | 用户："现有技能针对特有情况写死，需要提取 workflow 做泛化技能，不确定时必须问用户，且要能固化回专用技能" | 引擎+playbook+profile 三层：workflow 与领域解耦；设计 spec 见 docs/superpowers/specs/2026-07-14-ts-diagnose-engine-design.md
- 2026-07-14 | 验证记录 | —— | 机制层 pytest 23 项全绿；training-sufficiency 合成数据影子验证全程走通（植入效应 m03/m08 均召回、五个验证步 PASS、必答题零跳过）；robustness / feature-importance orient dry-run 通过；crystallize 固化演练三步验证（冷启动 --profile / 快照冒烟 / 影子重跑 Stage 0 一致）全 PASS
- 2026-07-14 | 加固轮（三层加载/两道闸/三关判据/路由消歧/接口版本化，spec：docs/superpowers/specs/2026-07-14-ts-diagnose-hardening-design.md） | 用户："这些建议非常好，可不可以借鉴一下加强 skill？不一定全用，挑好的 idea" | SKILL.md 压成 41 行纯路由层（执行细节下沉 references/engine-core.md，test_layering.py 守预算 ≤60 行/~6K token）；playbook 目录化并各自带 golden/ 金标准（确定性植入效应）+ gen_gate.py 生成闸（金标准算错不许碰真实数据）+ provenance.py 归因闸（结论必附代码/数据 hash）；crystallize 升级三关判据（crystallize_gate.py 可执行：多样性 N≥3/ts=5、held-out、快照自洽）；路由优先级进四技能 description（test_routing.py 漂移守卫）；profile 的 experiment_line 打 interface_version: v0-draft 占位不生效。裁剪：模拟打分路由器（伪测试）→ 存在性守卫；held-out 场景库 / regression baselines 只预留接口位置（spec §6）。pytest 56 项全绿
