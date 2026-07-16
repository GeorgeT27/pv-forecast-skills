# CHANGELOG —— pv-feature-blame

## 2026-07-16 v2：反事实预算阶梯（联合致坏）+ 预报翻新跳变分析

- 来源：用户指出两个 v1 盲区——(1) 联合致坏：多特征共同致坏且可能冗余结构（单换一个修不好、
  一起换才修好），单特征 Δ≈0 会被误判"无罪"；(2) 相邻行是同一物理时刻的两次起报，预报翻新
  跳变既是新诊断轴也是混淆因素。调研锚点：Zsoter jumpiness（跳变与误差弱相关→跳变大≠有罪）、
  Shapley Sets、delta debugging 最小修复集。用户确认：几千次 API 调用可接受（全阶梯默认开）、
  翻新分析一等公民。
- **修 bug（真实数据阻塞级）**：probe_schema 曾把 predict 模型列塞进滚动窗一致性闸——逐行
  重新起报下模型预测行间必然不一致，会误拦 Stage 1。改为只闸真值列（test 功率 + feature_true
  label），predict 行间差转为翻新分析的信号（wc_targets 纯函数 + 单测钉住）。
- **Stage 2 增翻新轴**：feature_revision.py（免 API，默认跑，revision.enabled 可关）——
  对齐数学 r+1 第 j 点 = r 第 j+1 点；per-pair 标量按口径匹配切片（全 191 点平均会洗平信号）；
  jumpiness/flip-flop/翻新改善率/churn Spearman 两关点名「翻新致不稳」。旧工作目录会被 orient
  指回 Stage 2——补跑 feature_revision.py（本地免 API）即恢复。
- **Stage 4 重构为预算阶梯**：oracle（G 闸防冤枉，用全部坏行——修了 v1 blamed_topk 过滤让
  零点名坏行永远进不了反事实的洞）→ per-feature/all-blamed → minimal-set（候选池反向贪心
  消解 + 1-minimal 校验，非单调下比 ddmin 稳）→ lattice（最差 3 行精确 Shapley + 交互指数）
  → neighbor-swap（换邻行预报测 churn 消减，须单独确认 neighbor_swap_confirmed）。
  决策数学抽到 cf_logic.py（零网络）——**Stage 4 逻辑首次可过 gen_gate**（stage "4"
  --selfcheck）。谓词三态（invalid 保守保留）、确定性探针 ε、版本漂移闸落地成代码（>30% 硬停）、
  NaN 防御、subset 内容去重 resume（跨层不重打基线；旧 CSV 自动迁移 schema 留 .v1bak）、
  --dry-run 升级为按层调用计划表。
- **金标准扩展**：f_jumpy（parity 跳变 s(T)·A(t)，pred_M3 消费→revision 两关必点名；其真值
  误差路径 ρ=0.28 恰低于 0.3 点名线——真值误差轴的盲区正是翻新轴的存在理由）+ f_jumpy_decoy
  （period-4 方波、跳变更大、零耦合→必须不点名）。manifest 新增 stage "revision"/"4"。
- 验证记录：pytest 33 项全绿（cf_logic 14 + revision/stage4 过闸 + 原有）；stub 彩排——
  冗余对 mini 数据集端到端：单换 Δ=0.0 而 minimal-set 判「需联合修复 ['r1','r2']」（G=10.0
  恰为埋点 0.5×20）；neighbor-swap 对 pred_M3×f_jumpy churn 消减 1.0（100% 对）；
  --max-calls 5 中断后续跑结果一致；旧版六列 CSV 自动迁移后缓存复用（oracle 只补 3 调）。

## 2026-07-15 初版（第四个专用技能）

- 来源：用户新需求"我需要看看哪些feature导致我的指标变差"——预测天气特征（NWP）质量归因
  + FastAPI 反事实验证。设计决策（与用户逐条确认）：新建专用技能（先例 pv-station-influence）
  而非 ts-diagnose playbook；两口径（ultra_short/short）各自找坏行；1..N 模型鲁棒；
  feature_true.parquet 硬规则（缺了必须问，绝不静默降级）。
- 六阶段：0 schema 探查（时间戳/模型列/特征对发现 + 窗一致性 + 真值交叉核验）→ 1 坏行
  （>均值 且 top N%）→ 2 归因（逐行 z + 全局 Spearman 双关点名 + 共线簇）→ 3 现象停顿 →
  4 反事实（门控：api.confirmed + adapter.py + --dry-run 用户确认）→ 5 结论（六反驳门）。
- 质量闸：复用 ts-diagnose gen_gate（`--playbook <SKILL>/SKILL.md` 路径形式，引擎零改动）；
  golden 埋点 f_blame（必须点名）/f_decoy（误差更大但零耦合，必须不点名）/奇异命名对
  （nwp_ghi_fc/ghi_obs 练配对）/mystery_x（练 unmapped 问用户）。**埋点按物理时间埋**
  （崩坏区间），否则破坏滚动窗一致性。
- 验证记录：pytest 15 项（probe 单测 10 + gen_gate 端到端 3 + 放水必拦 1 + manifest 完整性 1）
  全绿；三脚本过 gen_gate PASS；orient 彩排（缺 config → 缺 feature_true 阻塞 → unmapped
  卡关 → Stage 3 停顿 → Stage 4 门控 → 删 state 产物重定位）全通过；反事实对本地 stub
  实测 Δ=−18.0（恰为埋点效应 0.6×30）、断点续跑 0 重复调用。
- 常量复用：ULTRA_SHORT_IDX/SHORT_SLICE/load_table/to_matrix/check_window_consistency
  import 自 pv-result-analysis/scripts/data_utils.py（fb_common 缺 sibling 时硬失败）。
