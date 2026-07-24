# 结论纪律：事实/故事分离 + 升级表 + 十条反驳门

## 事实与故事分离（同主技能 Stage 3/4 边界）

Stage 0–2 的产物与 FINDINGS 的"现象"条目只写**看到什么**（哪行坏、哪个特征 z 多少、ρ 多少、
样本几个），禁机制语言；"为什么"（NWP 上游、天气过程、模型敏感性）从"假设"起步，
逐级升级。

## 升级表

| 状态 | 判据 | 谁给的 |
|------|------|--------|
| 现象 | 真值误差轴：z ≥ z_hi 且 ρ ≥ spearman_min（blame_report 行；v3 起基于 ε_res，且须过可约性闸+系统偏差门，decomp=off 须在结论注明未剥系统偏差）；翻新轴：jumpiness 且 churn ρ 双过（revision named） | Stage 2 |
| 假设 | 跨模型或跨月排名稳定 + 天气型条件化后 ρ 仍在 + 机制解释（特征的 NWP 上游） | 主 agent 综合 |
| 已证实·单特征可修 | **唯一通道** Stage 4：过 oracle 的 G 闸 + 单换后 R ≥ τ（或最小修复集为单元素） | Stage 4 |
| 已证实·需联合修复 | G 闸过 + 单换全不达标 + 最小修复集 ≥2 元素（点名整个集合，Shapley/交互佐证） | Stage 4 |
| 已证实·翻新致不稳 | neighbor-swap 后 churn 消减占比高（churn_reduction，消减>50% 对占比） | Stage 4 |
| 非特征问题 | oracle 全换后缺口不显著（G 闸不过）——模型/label 的锅，撤销对该行的一切特征归因 | Stage 4 |
| 被推翻 | 反事实 Δ≈0 或反向 → 回写 FINDINGS，该特征从嫌疑名单移除 | Stage 4 |

**单换 Δ≈0 不是"被推翻"的充分条件**——冗余结构下单换必然无效，须 minimal-set 排除联合
致坏后才可移出嫌疑名单。

用户拒绝反事实（config.api.declined）→ 结论最高到「假设」，CONCLUSION 显式注明
"未经反事实验证"。

## 十条反驳门（标「已证实」前逐条排除，CONCLUSION 附勾选）

1. **模型不敏感**：特征误差大但模型可能不信它——反事实是仲裁，没跑不许"已证实"。
2. **共线簇**：被点名特征与别的特征误差相关 ≥0.8（看 blame_summary.collinearity_clusters）
   → 只报簇；簇内定罪须 per-feature 反事实逐个替换。
3. **天气共变**：坏天全特征同坏。按天气型（借主技能 weather_class.csv，linked 时现成）
   条件化复算 ρ——晴稳日仍相关才可信。
4. **样本量**：坏行 <10 只描述不定论；z 与 ρ 都是小样本下的脆弱量。
5. **label 侧有假**：feature_true 的"真值"也可能错（缺测/插值/换源）。Stage 0 交叉核验
   agree_rate ≥0.99 是底线；可疑区段剔除并披露。
6. **口径错位**：行级化口径必须与考核口径对上——首跑用 metric.py 复算一个月，对照行级
   聚合方向一致（行级坏 ↔ 月度差）再信全链；`align_offset_steps ≠ 0` 未与用户确认前
   一切结论无效。
7. **版本漂移**：API 基线与离线 parquet 行误差漂移大（counterfactual_summary.version_drift）
   → API 后面的模型不是产出 predict.parquet 的版本，反事实结论只对 API 版本成立，须注明。
8. **跳变冤枉**：翻新跳变大的特征若 churn 相关 ≈0（revision 里的 jumpy 诱饵模式）不得点名；
   点名了也要 neighbor-swap 仲裁（文献：跳变与误差弱相关）。
9. **系统偏差门（代码闸，decomp=on 时 feature_blame.py 强制执行，非纯人读纪律）**：
   `sys_frac ≥ sys_frac_max`（默认 0.85）的特征即便 raw ε 大也不得升"假设"——疑似模型已
   补偿（共适应），修它需重训验证。**为什么不能只靠剥 ε_res 让它自然洗清**：z/Spearman
   都是尺度不变统计量，被补偿特征的 ε_res 即使量级塌了几十倍（如金标准 f_sys_bias 剥前
   剥后 11.83→0.27），只要残影**秩结构**没塌，两关照样双过——所以必须是显式阈值闸，命中
   即 `blamed=False`、`note="compensated"`。举证看 `blame_summary` 每特征的
   `global_spearman_raw`（剥前，对 f_sys_bias 会很高）vs `global_spearman`（剥后 ε_res 上
   算的，应显著回落甚至不显著）对照——即"**剥前会冤枉、剥后洗清**"。decomp=off（未跑
   Stage 1.5）时点名基于原始 ε，无 sys_frac 可查，结论最高到"现象"并注明未剥系统偏差。
10. **可约性门（代码闸，decomp=on 时同步执行）**：`reducibility_frac < reducibility_min`
    （默认 0.1）的特征标 `irreducible`，只描述不点名——白噪声上游改不了，硬追是废话
    （金标准 f_irreducible：z/ρ 双关都过、唯此闸挡）。

## Provenance（CONCLUSION.md 末尾必附）

- 脚本 gate_reports/*.json 的 `script_sha256`（gen_gate 报告）+ 过闸日期；
- 三件套输入文件路径 + 行数（probe_schema.json 里有）；
- 阈值参数（top_pct / z_hi / spearman_min / top_k）与是否调过默认值。
两次结论不一致时，据此可判是代码变了还是数据变了。
