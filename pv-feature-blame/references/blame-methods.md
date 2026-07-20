# 归因方法细节（Stage 0–2 的数学与协议 + Stage 4 阶梯 + 翻新分析）

## 口径 → 切片映射（常量一律 import 自 data_utils，绝不本地重定义）

| 口径 | 行级误差（Stage 1 坏行） | 特征误差切片（Stage 2） | 参与行 |
|------|--------------------------|--------------------------|--------|
| `rmse_192`（默认） | 每行全 192 点 RMSE | 全窗 `[0:192]` | 全部行 |
| `ultra_short` | 每行第 `ULTRA_SHORT_IDX`(16) 点绝对误差 | `[:ULTRA_SHORT_IDX+1]`（考核点及其前导 0–4h） | 全部行 |
| `short` | `SHORT_SLICE`([59:155]) 上 RMSE | `SHORT_SLICE` | 仅 09:00 行 |

另附全 192 点特征误差作参考列（`feature_err_full192`）——只用于人读对照，点名判定
一律用口径匹配切片（超出口径窗口的特征误差不可能影响该口径的行误差；rmse_192 下
两者恰好重合）。

口径由 `config.metrics` 选（可多选各自找坏行）。**2026-07-16 起用户定的考核口径是
rmse_192**——每行功率预测的 192 点 RMSE 取平均看整体，不再默认跑 ultra_short/short；
后两者保留可选：业务含义不同，元凶也可能不同——一个只在 4h 内起效的特征误差伤
ultra_short 不伤 short 的次日段，反之亦然。

## 坏行定义（Stage 1）

`row_error > mean(该口径全体行)` **且** `进 top --top-pct%`（默认 10）。两个条件都要：
只用分位数在"整体都好"的月份会硬拉出假坏行；只用均值在长尾分布下会圈进太多行。
数据量小（如 09:00 行只有几十个）时 top 10% 可能只剩几行——跟用户确认调 `--top-pct`。
CSV 落**全量排名**（is_bad 列标坏行）——Stage 2 的 z 归一与全局相关需要全行分布做参照。

## ε_sys/ε_res 分解（Stage 1.5，v3 起默认；feature_decompose.py）

**为什么**：功率模型在有偏预报上训练，会学会补偿**稳定的系统偏差**（共适应）——这部分
ε 再大也不该点名（修了对固定模型中性甚至有害）；纯白噪声的 ε 上游改不了，点名是废话。
点名对象应是"波动、可约、且与功率误差相关"的部分。

**方法**（稳健加性回归，不分箱——多维分箱会稀疏、要人为边界、要 weather_class 标签）：
`ε_f = pred − label` 逐点 → Huber 岭回归拟合条件均值：截距 + 钟点谐波(≤3 阶, cyclic) +
DoY 谐波(≤2 阶, cyclic) + 提前期 hinge(df≤5) + **每个配对特征的 pred 值 hinge**（天气型由
特征值隐式承载；own-pred 项抓"报得越高越偏高"的乘性偏差）。**回归只减条件均值不碰条件
方差**——"碎云段波动大"这类异方差结构原样留在 ε_res（feature_decomp.json 的
res_var_front/back 可查）。

**跨期稳定性收缩**：前段拟合、后段验证（embargo 48h = 192 步，防重叠窗泄漏），
`λ = clip(⟨ε_b,ŝ_b⟩/⟨ŝ_b,ŝ_b⟩,0,1)`；后段不复现（如一次性崩坏）→ λ→0 整条不剥。
拟合失败/样本不足/后段空一律 λ=0。**方向保守：宁少剥（残留点系统偏差）不过剥（把可约
波动当偏差丢，毁归因）。**

**两道分解闸（decomp=on 才生效，Stage 2 消费，缺一不可）**：
- **可约性闸**：`reducibility_frac = median(逐行 lag-1 自相关)₊²` < `reducibility_min`
  （默认 0.1，CLI `--reducibility-min`）→ 该特征标 `irreducible` **不点名**（近白噪声，
  上游拿它没辙）。v2 占位：ε_res 形状分解（相位/幅度/爬坡——相位错和幅度错对上游的指导
  完全不同）。
- **洗清闸（系统偏差门，代码闸）**：`sys_frac ≥ sys_frac_max`（默认 0.85，CLI
  `--sys-frac-max`）→ 该特征标 `compensated` **不点名**。**为什么必须是代码闸而非只靠
  ε_res 化自然实现**：`z=(fe−μ)/σ` 与 Spearman 都是**尺度不变**的——一个被模型补偿的
  系统偏差特征，ε_res 量级可能塌了几十倍（金标准 f_sys_bias 实测 11.83→0.27），但只要
  残影的**秩结构**没塌，z/ρ 两关照样双过、诱饵照样冤枉点名。所以"系统偏差高的不点名"
  必须显式加一道基于 `sys_frac` 的阈值闸，不能指望剥完 ε_res 后 z/ρ 自动洗清。
  **真实数据提醒**：own-pred hinge 是本方法唯一可能在真实数据上悄悄过剥的地方（金标准
  合成数据无法暴露）——若某特征的 `sys_frac` 反常地高、但独立已知它携带真实可约波动，
  应手动做消融（去掉该特征自身的 own-pred hinge 项重跑分解）复核，而非直接采信洗清闸判定。

**作用域**：只有 feature_pairs.json 配对的预报特征存在 ε——未配对列（真实观测列）无 ε、
无反事实语义，落 feature_decomp.json 的 skipped_unpaired。金标准埋点：f_sys_bias
（乘性稳偏，raw 必冤枉、剥后必洗清）、f_res_culprit（波动元凶必点名）、f_irreducible
（ρ 双关都过、唯可约性闸挡）。缺分解产物 → feature_blame 回退原始 ε 并标 `decomp=off`
（顶层 `params.decomp` 记录 `"on"`/`"off"`）。

## 两关点名（Stage 2）

> v3 起 z 与 Spearman 都算在 ε_res 上（decomp=on 时）；共线簇也在 ε_res 向量上——剥掉
> 公共系统偏差后虚假共线消解。decomp=on 时点名还须再过上面两道分解闸（可约性 + 洗清），
> 四关全过（z、ρ、top_k、两道分解闸）才 `blamed_topk=True`。

- **关一（行内异常）**：特征误差对**全体行**的分布做 z 归一（`z = (fe − μ)/σ`，σ=0 → z=0）。
  不同量纲的特征（W/m² vs ℃）只有归一后才可比。`z ≥ z_hi`（默认 2.0）。
- **关二（全局相关）**：`Spearman(行误差, 特征误差)` 跨全体行 ≥ `spearman_min`（默认 0.3）。
  这一关拦"误差大但模型不敏感"的诱饵——特征烂不等于模型信它。
- `blame_score = z × max(ρ, 0)`；每坏行按分数排 `top_k`（默认 3）内才点名。
- 阈值全部 CLI 可调；调过要在 FINDINGS 披露（阈值敏感性属于反驳门检查项）。
- **报告列**（decomp=on 时）：`feature_err`（即 ε_res，无单独的 feature_err_res 列）/
  `feature_err_raw`（剥前 ε）/ `feature_err_sys`（= raw − res）/ `reducibility_frac`；
  `note` 三态：`""`（正常）/ `"irreducible"`（可约性闸挡）/ `"compensated"`（洗清闸挡）。
  summary 每特征加 `global_spearman_raw`（剥前对照，见门⑨系统偏差门的"剥前冤枉、剥后
  洗清"举证）、`sys_frac`、`stability_lambda`、`reducibility_frac`。

## 共线性聚类

特征误差向量（跨行）两两 Pearson ≥ 0.8 → 同簇（连通分量；常量向量无边）。簇内成员
统计上不可分（同一场天气过程把它们一起带错），报告写"簇 {A,B} 至少其一"，
定罪到单个特征只能靠 Stage 4 逐个替换（`--mode per-feature`）。

## 滚动窗一致性闸的适用边界（v2 修正）

`check_window_consistency`（行 t 第 k 点 == 行 t+1 第 k−1 点）只对**物理时间的函数**成立：
test 的功率真值列、feature_true 的 label 列。**predict 模型列与预报特征的未来段绝不进闸**——
逐行重新起报下，相邻行对同一物理时刻的预测/预报本来就不同（lead time 不同），那是翻新分析
的信号，不是窗口构造 bug。v1 把 predict 列塞进闸会在真实数据上误拦 Stage 1。

## 翻新跳变分析（feature_revision.py，免 API，默认跑）

相邻对 (r, r+1)（须 Δts==FREQ，真实数据有缺行）在重叠段的对齐：**r+1 第 j 点 = r 第 j+1 点**
（j∈[0,190]；权威口径 data_utils.rebuild_series——未来段从窗口起点当步开始）。

- 跳变向量 `J[j] = F[r+1][j] − F[r][j+1]`；per-pair 标量按**口径匹配切片**取 RMS（全 191 点
  平均会把随时刻变化的信号洗平——金标准里 short 切片跨夜恒幅即例证）。
- 指标：Zsoter 式 jumpiness（RMS 跳变 / 该特征全局 std）、flip-flop 率（连续对符号交替）、
  **翻新改善率**（|新−真|−|旧−真| 的负值占比；≈0.5 = 无系统性改善 = 纯噪声抖动，>0.5 明显
  = 健康翻新）、特征跳变 × 模型 churn（predict 同构跳变）的 Spearman。
- **两关点名「翻新致不稳」**：jumpiness ≥ jumpiness_min(0.05) 且 churn Spearman ≥
  spearman_min(0.3)；模型自身 churn_rel < stable_max(0.02) 直接判「行间稳定」无案可查。
- 文献纪律：Zsoter 等的 jumpiness/flip-flop 研究实证**跳变与预报误差只有弱相关**——跳变大
  ≠ 拖指标；改善率区分健康翻新与噪声抖动；升「已证实」唯一通道 = neighbor-swap 反事实。

## 反事实协议（Stage 4·预算阶梯）

决策数学在 `cf_logic.py`（零网络，`--selfcheck` 过 gen_gate stage "4"）；runner 只做
IO/HTTP/缓存。**与基线比而不与离线 parquet 比**——API 后面的模型版本可能与产出
predict.parquet 的不同，基线调用抵消版本差；同时 runner 自动做**版本漂移闸**：基线 vs 离线
行误差漂移 >20% 的行标 version_mismatch，占比 >30% 硬停。开跑先做**确定性探针**（首行基线
重复 2 调，ε = 差值上界，进所有判定阈值）。

| 层 | 每坏行调用 | 判定 |
|---|---|---|
| oracle | 2（基线+全换） | 缺口 G = base − oracle；**G 闸**：G/base ≥ g_min(0.2) 且 G ≥ 5ε，不过 =「非特征问题」，防冤枉。行集 = **全部坏行**（零点名坏行恰是非特征问题候选） |
| per-feature / all-blamed | 1+k / 1 | 边际充分性 Δ_f（v1 语义；跨层 subset 去重不重打基线） |
| minimal-set | ~p+2\|S\| | 修复谓词 R(S)=(base−err_S)/G ≥ τ(0.8)+ε/G；候选池（点名∪共线簇∪z≥1，cap 8，不足则扩全特征）**反向贪心消解**（按嫌疑升序试删+1-minimal 校验；对非单调比 ddmin 稳、顺序确定可续跑重放）。冗余结构「单换无效双换才修」在此现形 |
| lattice | 2^k（k≤5） | 每口径×模型最差 3 行：全子集精确 Shapley φ_i + 成对交互指数 φ_ij（>0 = 修复互补/冗余，≈0 = 可加） |
| neighbor-swap | ≥3/对 | 高 churn 对：r+1 的特征未来段 0..190 ← r 的 1..191（第 191 点保留原值——不在两口径切片内，零污染），churn 消减 = 翻新致不稳已证实。**须 api.neighbor_swap_confirmed**：拼接序列行间不连续，服务端若做输入连续性校验会 4xx |

谓词三态：API 失败/NaN = invalid（保守保留特征，绝不当"没修好"）；替换序列非有限不发
（json.dumps 会产非标 NaN token）；考核点真值 NaN 的行计划期剔除。resume 按
(口径,模型,行,subset_id) 内容去重，旧版 CSV 自动迁移 schema（留 .v1bak）。
预算参考（B 坏行、k̄≈3 点名、p≤8 池、R=3 深挖行）：每口径×模型 ≈ 2B + k̄B + B₂(p+4) +
R·2^5 ≈ 数百；全量典型 800–1500 调，--max-calls 默认 400 分次跑。

## 降级模式：窗口重叠重建特征真值（仅当用户确认没有 feature_true）

滚动窗重叠意味着：行 T 未来段第 k 点（时间 T+kΔ）的**观测值**，会出现在其后行 T+mΔ（m>k）
的历史段第 672+k−m 位。所以从 test.parquet 的特征列历史段可以重建未来段真值，用来对比
特征预报误差。限制（报告必须注明，证据自动降一级）：
- 只覆盖 test.parquet 里带 ≥672 点历史段的特征；
- 序列末尾 192 步内的行重建不全（后面没有行了）；
- 历史段本身若有插值/清洗，"真值"已非原始观测。
Stage 0 的 `label_crosscheck` 用同一机制反向核验 feature_true 的 label 列（抽样比对，
agree_rate < 0.99 = 对齐错位或 label 有假，先排除再进 Stage 2）。

## 时间戳对齐歧义

feature_true 的行时间戳可能是"窗口起点"也可能是"预报起点"（差 672 步）。probe 在 0 偏移
交集过少时自动试 ±672 步并报 `align_offset_steps`——非 0 时先跟用户确认口径，别静默平移。
