# pv-feature-blame 改进：系统偏差剥离（ε_sys/ε_res）后再归因

> 状态：设计稿｜日期：2026-07-17｜范围：Phase 1 直接分析路线（不含 DFL）
> 一句话：在 Stage 2 点名前先把特征误差 ε 拆成"模型能补偿的系统偏差 ε_sys"和"补偿不了的波动
> ε_res"，**只对 ε_res 点名**，并加一道"可约性"闸，避免冤枉被模型吃掉的稳定偏差和不可约噪声。

---

## 0. 动机：现状为什么会冤枉

当前 `feature_blame.py`：`err_mats[feat] = pred_col − label_col`（逐点 ε），对 ε 做 z 归一 +
`Spearman(行功率误差, 特征误差)`，两关命中即点名。**问题**：
1. 一个有**稳定系统偏差**的特征（如晴天辐照恒偏高 10%），功率模型很可能已学会补偿它——
   ε 大、且与功率误差相关，于是被**冤枉点名**；但让上游修它对固定模型中性甚至有害（共适应）。
2. 一个 ε_res 是**纯白噪声**的特征，误差大但上游根本改不了——点名也是废话。

**改进目标**：点名对象从 ε 换成 **ε_res 中可约的部分**，把"有舍有得"落到归因层：
舍掉模型已吃的 ε_sys 与不可约噪声，只点名"波动、可约、且与功率相关"的特征×处境。

---

## 1. 数据流改动（新增 Stage 1.5，改造 Stage 2）

```
Stage 0 probe → feature_pairs.json（不变）
Stage 1 find_bad_rows → bad_rows_*（不变；坏行仍按功率误差定义）
★ Stage 1.5 feature_decompose.py（新）
     ε = pred−label  →  稳健加性回归 ε_sys（cyclic 钟点/季节+提前期+全部预测特征）  →  ε_res = ε−ε_sys  →  可约性
     产物：eps_res_<feature>.npy(或 parquet) + feature_decomp.json
Stage 2 feature_blame.py（改）
     读 ε_res（而非现算 ε）做 z + Spearman + 共线 + 点名；加可约性闸；报告 ε/ε_sys/ε_res 三栏
Stage 3/4/5：Stage 4 反事实改"只换 ε_res"（§7），其余不变
```

坏行定义（Stage 1）**不动**——坏行是功率误差定义的，分解只影响"点名哪个特征"。

---

## 2. ε_sys/ε_res 分解方法（透明、无黑箱，符合本技能纪律）

### 2.1 ε_sys = 稳健低维回归（不分桶）
ε_sys 的本质是条件均值 `E[ε | 处境]`。**不用分桶估**（多维分箱 → 稀疏格子 → 箱心是噪声 →
被当 ε_sys 减掉反而污染 ε_res；且要人为切边界、要 weather_class 标签，本项目都给不了）。
改成对**连续、模型可见的坐标**做一个稳健的加性回归（GAM），**逐特征 f 各拟合一条**：

```
ε_f(r,k) = X_pred_f(r,k) − X_true_f(r,k)                 # 逐点误差
ε_sys_f ≈ β0 + s_hour(钟点, cyclic) + s_doy(年内天, cyclic)
              + s_lead(提前期 k)
              + Σ_g s_g( X_pred_g )     # g 遍历「全部预测特征」：GHI/SSRD/温度/风/湿度/云…
ε_res_f(r,k) = ε_f(r,k) − ε_sys_f(r,k)                   # 拟合值=ε_sys，残差=ε_res
```

- **钟点/季节用 cyclic 谐波（sin/cos）**：天然处理午夜、跨年回绕，无需切段、无边界跳变。
- **`Σ_g s_g(X_pred_g)` 是关键**——偏差不只依赖 GHI_pred，**整套预测特征都进回归**。
  - 每个特征一条**光滑主效应**（样条），承载"天气型/量级依赖"：GHI_pred 是主导天气轴，
    温度/风/湿度/云等各自再修一刀。**碎云那种非单调关系靠样条曲率抓，不需要 weather_class 标签。**
  - 特征 f 自己的 `s_f(X_pred_f)` 同时吃掉"**报得越高越偏高**"的乘性偏差（原 v2 内容并进 v1）。
- **加性主效应（不是全张量交互）**：成本随特征数 **线性**增长，不请回维度灾难；
  特征间交互（如"高辐照×高温才偏"）留 v2，需要时再加少量张量项。
- **作用域钉死（`_predict` 口径）**：ε 只对 `feature_pairs.json` 里配对的 **`_predict` 预报特征**
  存在——**被分解/点名/反事实的对象只限它们**。不带 `_predict` 的列是真实观测/已知量：无 ε、
  无反事实语义，但作为"模型可见坐标"**可进回归当协变量**（零预报误差，条件反而更干净）。
- **自由度上限（结构性防偷波动）**：每条 s(·) 样条 df ≤ 6、cyclic 谐波 ≤ 3 阶——低 df 加性曲面
  天生"僵硬"，只装得下慢变偏置、装不下快变波动。过拟合偷 ε_res 的第一道防线是结构，不是验证。
- **稳健损失**（Huber / 中位数回归）：少数极端点不把 ε_sys 拉歪——对应原"稳健均值"的意图。
- **共线不碍事**：GHI/SSRD/温度高度相关会抬高系数方差，但我们只取**拟合值**（ε_sys）不解释系数，
  预测用途下多重共线无害；真正的护栏是下面的跨期稳定性，不是系数可信度。
- **不需要经纬度**：坐标依赖（晴空指数 kt 那条）彻底去掉——天气型由预测特征值隐式承载。

**直觉版**：把 ε 看成一条随钟点/季节/提前期/各预测特征平滑变化的**曲面**，曲面本身=偏置(ε_sys)，
点到曲面的偏离=散布(ε_res)——即"偏置 vs 散布"，只是曲面用回归估、不用查表。

### 2.2 跨期稳定性闸（防把波动当系统偷走）
诚实说：光滑回归也可能过拟合、偷走本属于 ε_res 的波动。**让"减掉"合法的不是拟合多准，而是它
跨时间稳不稳**：
- 按时间切**前段/后段**（连续块，留 embargo 间隔 ≥192 防重叠窗泄漏）；前段拟合，后段验证。
- **收缩**：`ε_sys_used = λ · ε_sys_front`，`λ` 由后段"减 ε_sys 后 ε 方差是否真降"定
  （后段不复现→λ→0，整条退回 ε_res）。可整体一个 λ，也可按分量（某特征主效应不稳则只砍它）。
- **月月漂移的"偏差"模型也吃不稳，就不该当 ε_sys 剥。** 回归比分桶更容易过这关——每个一维分量
  用全量数据、方差小，前后段更容易一致。
- **方向始终保守**：宁可少减（残点系统偏差留在 ε_res，最多没洗净）也不过减（把可约波动当偏差丢，
  那才毁归因）。
- **波动保全检查（验收项）**：回归只减条件均值、不碰条件方差——"阴天/碎云波动更大"这类
  **方差结构必须原样留在 ε_res**。分解后按处境（GHI_pred 分位 × 钟点段）对比 `Var(ε)` vs
  `Var(ε_res)`：处境间方差差异结构必须保持（碎云段仍显著高于晴天段）；若被抹平 = 过剥，λ 收紧。
  此检查同时做成 golden 断言（§8）。

---

## 3. 可约性检验（新闸，落在 ε_res 上）

对每个 (feature, 处境) 的 ε_res 判"上游还够不够得着"：
- **重建物理序列**（`data_utils.rebuild_series`，去重重叠窗）后测：
  ① ε_res 的自相关（lag 1..few）；② 天气型依赖；③ 与 persistence / 侧信息(卫星nowcast，若有) 相关。
- `reducibility_frac ∈ [0,1]` = 上述结构能解释的 ε_res 方差占比。
- **闸**：`reducibility_frac < reducibility_min`(默认 0.1) → 该处境标 `irreducible`，**不点名**
  （白噪声硬追是废话）。
- **v2 占位——ε_res 形状分解**：逐点 RMS 只刻画波动**幅度**；相位错（云到时刻报早 1h）与爬坡错
  （ramp 斜率不对）在 RMS 里同样是"大"，但对上游指导完全不同（改时间 vs 改幅度）。v2 对 ε_res
  加 相位/幅度/爬坡 三分量分解；v1 由自相关粗摸。

---

## 4. Stage 2 点名改动（最小侵入，复用现有两关）

`feature_blame.py` 改 4 处，其余（z/Spearman/共线/blame_score/top_k）逻辑不动：
1. **误差源替换**：`err_mats[feat]` 从 `pred−label` 改为**读 Stage 1.5 的 ε_res 矩阵**
   （`--use-residual` 默认开；缺 decomp 产物则回退原 ε 并在摘要标 `decomp=off`）。
2. **可约性闸**：点名条件追加 `reducibility_frac ≥ reducibility_min`；不过则 `blamed=False` 且
   `note="irreducible"`。
3. **系统偏差门（代码闸，实现期新增——见下方 ⚠）**：点名条件追加 `sys_frac < sys_frac_max`
   （`--sys-frac-max` 默认 0.85）；不过则 `blamed=False`、`note="systematic"`。
4. **报告列**：新增 `feature_err_raw / feature_err_sys / reducibility_frac`（`feature_err` 在
   `decomp=on` 时**即 ε_res**，不再单列 `feature_err_res`）+ summary 加 `global_spearman_raw`
   对照。z 与 Spearman 都基于 ε_res。

> ⚠ **实现期发现（2026-07-20，golden 验证暴露）**：只把误差源换成 ε_res **不足以**让被模型
> 补偿的系统偏差特征洗清——`z=(fe−μ)/σ` 与 Spearman 都是**尺度不变**的，f_sys_bias 的 ε_res
> 虽塌了 40× 量级（金标准实测 11.83→0.27）但**秩结构不塌**，残影伪相关照过两关点名（raw/res
> 都点名 3 行，调 α 无效）。所以「系统偏差高的不点名」必须是**显式代码闸**（sys_frac 门），
> 不能指望 ε_res 化自然实现。这把 §5 原本只写成「人读纪律」的系统偏差门提升为 blamed 条件。

**共线簇**改到 ε_res 向量上算——剥掉公共系统偏差后，虚假共线可能消解，真残差共线才留下。

---

## 5. 报告与结论纪律改动

- `blame_summary.json` 每特征加：`sys_frac`（ε_sys 方差占比）、`reducibility_frac`、
  `stability_lambda`（跨期收缩系数）、`global_spearman_raw`（剥前对照）。
- `references/blame-discipline.md` 反驳门加两条（**⑦已被 §4 的代码闸落实**：sys_frac ≥
  `sys_frac_max`（默认 0.85）的特征在 Stage 2 直接 `blamed=False`、note=systematic；纪律层
  仍保留，供人读时理解「为什么它不该点名」）：
  - **⑦ 系统偏差门**：ε_sys 占比高（`sys_frac ≥ sys_frac_max`）的特征，即便 raw ε 大也
    **不点名 / 不得升"假设"**，注明"疑似模型已补偿，需重训才验证"。对照 `global_spearman_raw`
    可见「剥前会冤枉、剥后洗清」。
  - **⑧ 可约性门**：`irreducible` 特征只描述不点名。
- `SKILL.md` 常见错误加：❌ 在原始 ε 上点名不剥系统偏差（冤枉被模型吃掉的稳定偏差）。

---

## 6. 新增/改动文件清单

| 文件 | 动作 |
|---|---|
| `scripts/feature_decompose.py` | **新**：Stage 1.5，产 `eps_res_*` + `feature_decomp.json` |
| `scripts/fb_common.py` | 加 `fit_bias_field()`（稳健加性回归）、`stability_shrink()`、`reducibility_frac()`、cyclic/样条基构造 + 时间切分工具；config 加 `decompose` 块 |
| `scripts/feature_blame.py` | 改 §4 四处（含系统偏差代码闸 `--sys-frac-max`） |
| `scripts/run_orient.py` | 阶段表插 Stage 1.5，前置校验 `feature_decomp.json` |
| `references/blame-methods.md` | 加"ε_sys/ε_res 分解 + 可约性"节 |
| `references/blame-discipline.md` | 加反驳门 ⑦⑧ |
| `SKILL.md` | 阶段表 + 常见错误 + 首要框定加"剥系统偏差" |

**config 新增块**（`fb_common.py` 头部文档同步）：
```json
"decompose": {"enabled": true,
              "bias_model": "robust_additive_regression",
              "covariates": {"cyclic": ["hour", "doy"],       // sin/cos 谐波
                             "smooth": ["lead"],               // 样条
                             "feature_smooths": "all_pred_features",  // 全部 _predict 特征各一条主效应
                             "extra_covariates": []},          // 可加不带 _predict 的真实值列作条件
              "max_df": 6,                                     // 每条样条自由度上限（谐波 ≤3 阶）
              "robust_loss": "huber",                          // huber | quantile(0.5)
              "stability_split": "temporal_half", "embargo": 192,
              "reducibility_min": 0.1}
```
（删掉了旧的 `conditioners`/`bias_estimator`/`weather_class`——天气型由 `feature_smooths` 隐式承载，
无经纬度依赖。）

---

## 7. 与 Stage 4 反事实的衔接

**作用域**：可反事实的特征 = 且仅 = 配对的 `_predict` 预报特征；不带 `_predict` 的列是真实值，
无"换成真值"可言，绝不进替换集（cf_logic 候选池构造时按 feature_pairs.json 过滤）。

反事实从"整条换真值"改为**只换 ε_res**（`X_true + ε_sys`，即保留系统偏差、只去波动）：
- 保持输入在功率模型分布内（避开 ε_sys 方向的 OOD），使 Δ 可信；
- oracle 的 **G 闸仍用整换**测"这行到底是不是特征问题"，但边际/minimal-set/lattice 层都在
  ε_res 方向做（`cf_logic.py` 加 `residual_mode`，替换向量由 Stage 1.5 的 ε_sys 供给）。
- 结论升级仍以反事实为唯一仲裁；但现在验证的是"**修 ε_res 有没有用**"，与改进后的点名一致。

---

## 8. golden 埋点 + gen_gate 扩展

现有诱饵（f_blame/f_decoy/f_jumpy/f_jumpy_decoy）保留，新增三个：
- **f_sys_bias**：大**系统偏差**但被（造数据的）功率模型补偿 → 在原始 ε 上会被点名，
  **剥 ε_sys 后必须不点名**（证明分解有效）。
- **f_res_culprit**：ε_sys≈0、ε_res 波动驱动功率误差 → **必须点名**。
- **f_irreducible**：ε_res 大但纯白噪声（零结构）→ **必须被可约性闸挡**。

另加两条断言：
- **波动保全断言**：`f_res_culprit` 造成"碎云段方差高、晴天段方差低"的异方差结构，分解后
  `Var(ε_res)` 的处境结构必须保持（§2.2 检查项的金标准化）。
- **作用域断言**：golden 里放一条不带 `_predict` 的真实值列，分解/点名/反事实候选池**必须不含它**。

改脚本后 `gen_gate.py --stage 1.5/2` 必过，再碰真实数据。

---

## 9. 实现顺序（每步可独立过闸）

1. `fb_common` 加 `fit_bias_field`（稳健加性回归）+ `stability_shrink` + `reducibility_frac` + cyclic/样条基 + 时间切分。
2. `feature_decompose.py` 打通，造含 f_sys_bias/f_res_culprit/f_irreducible 的 golden 验证。
3. `feature_blame.py` 接 ε_res + 可约性闸 + 三栏报告；重过 blame golden。
4. `run_orient` / `references` / `SKILL.md` 同步；`blame-discipline` 加门 ⑦⑧。
5. （后置）Stage 4 `residual_mode`。
6. 全仓 `pytest` 绿 + gen_gate 全绿，再上真实数据。

---

## 10. 边界与诚实

- **v1 用稳健加性回归**（cyclic 钟点/季节 + 提前期样条 + 全部预测特征各一条主效应）：乘性偏差与
  多特征天气依赖**已在 v1**，无经纬度依赖；**特征间张量交互**（如"高辐照×高温才偏"）留 v2。
  分桶是退路（数据极小或回归不收敛时才回退到粗 (τ,h,season) 分箱）。
- ε_sys 剥离**只在跨期稳定**处生效（收缩系数兜底）——不稳的偏差不剥，宁可少剥（少剥=保守，
  最多是没剥干净仍在 ε 上留了点系统偏差；过剥=把可约波动当系统偏差丢掉，更糟）。
- 本方案是**直接分析基线**；它与 DFL 方案（另一 spec）互为对照——直接分析看不到但 DFL 抓到的
  联合/交互校正，正是升级 DFL 的理由。
