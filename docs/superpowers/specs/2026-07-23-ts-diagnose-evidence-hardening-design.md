# ts-diagnose 证据可靠性加固：置换基线 + 跨维稳定性门

日期：2026-07-23
范围决策（用户已确认）：**引擎原则进 mechanisms.md（对所有 playbook 生效），可执行部分只在 model-comparison 完整落地**；其余 4 个 playbook 后续轮按需接入。

## 1. 背景：图证据链的两个统计漏洞

v2 完成后，model-comparison 的证据升级链是：两条证据线方向一致（total-gap ↔ slice-gap）+ 噪声门（|sign_z| ≥ 2）→「现象」升「假设」。这条链有两个漏洞：

1. **多重比较虚警**：worst-slice-compare 按 argmax 点名"最差片"——切片足够多时最差片必然存在，`concentration_ratio` 高也可能只是随机波动恰好堆在一处。现在没有任何机制回答"这个集中度超出随机了吗"。
2. **伪独立收敛**：13 张图全部派生自同一份 predictions 长表，"多图方向一致"共享同一份数据的同一个偶然，不构成独立验证。真正的正交维度是：换时间切分方向不变、换口径方向不变、外部材料给出一致解释。

## 2. 目标 / 非目标

**目标**
- 切片点名必须先过置换基线：集中度未显著高于随机重排 → 不许点名切片。
- 「现象 → 假设」升级加第三条腿：至少一条正交切分上稳定（时间对半为必查项）。
- 两个机制都走 chartbook 预写脚本 + golden + conformance 的既有基础设施，判读只读 JSON。

**非目标（YAGNI）**
- 不接入其余 4 个 playbook（fact-scan 无结论阶段本就不适用；其余 3 个引擎原则已覆盖，落地排后续轮）。
- 口径对只做 rmse_192 行均值 ↔ 点级 pool 一对，不做口径菜单泛化。
- 不做更复杂的自相关校正（block-by-day 置换是第一版的诚实近似，局限写进判读节）。
- SKILL.md 与路由不动（无新入口）。

## 3. 机制 1：worst-slice-compare 内置置换基线

落点：扩展 `chartbook/scripts/chart_worst_slice_compare.py` 的 `compute()`（图 JSON 自足原则——判读仍只读一个文件），不新建脚本。

### 3.1 算法

现行口径（不变）：`gaps[slice] = per[focal] − per[others].min(axis=1)`，`pos = gaps.clip(lower=0)`，`concentration_ratio = pos[worst] / pos.sum()`。

置换检验（新增）：
- **置换单元 = 自然日块**（`date = window_ts 的 %Y-%m-%d`）：把 distinct dates 列表用 `random.Random(perm_seed)` 洗牌后，按原各切片的**日数配额**顺序重新分配 slice 标签（保持每片日数不变）。同一日的所有行（全模型、全 unit）整块移动——防止拆散配对结构，也部分抵消日内自相关把 null 做窄。
- 每次置换在新的 slice 标签下重算 `concentration_ratio`（同一公式，worst 取置换后的 argmax）；`pos.sum()==0` 的置换记 0。
- `perm_p = (1 + #{null_conc ≥ real_conc}) / (n_perm + 1)`（plus-one 修正，避免 p=0）。
- `null_q95` = null 分布的 95 分位（`quantile(0.95)`）。
- `verdict = "significant"` 当 `perm_p < 0.05`，否则 `"not-significant"`。

### 3.2 CLI 与 JSON 增量

新参数：`--n-perm`（默认 200）、`--perm-seed`(默认 0）；`--n-perm 0` 显式关闭（perm 块置 null 并 note 原因）。

JSON 新增顶层 `perm` 块（其余字段全部不变，纯增量，不破坏现有 expects）：

```json
"perm": {"n_perm": 200, "seed": 0, "real_concentration": 1.0,
         "null_q95": 0.62, "perm_p": 0.005, "verdict": "significant",
         "note": "按日块置换，slice 日数配额保持；月内自相关未校正，显著性偏乐观时以此为限"}
```

跳过条件（`perm` 置 null + note）：切片数 < 2、`concentration_ratio` 为 null（pos.sum()==0）、distinct 日数 < 切片数、`--n-perm 0`。

### 3.3 判读规则收紧（recipe 判读节改写）

- `verdict = significant` 且 `concentration_ratio > 0.7` → 才允许现象清单写"差距集中于切片 X"；
- `verdict = not-significant` → **必须**写"集中度未超随机基线（perm_p=…），不点名切片"，切片线不参与升级；
- 已知局限写进判读：block=日 只抵消日内自相关，月内多日相关仍可能使显著性偏乐观——significant 是点名的必要条件而非充分证明。

## 4. 机制 2：新 recipe `cross-dim-stability`

新预写脚本 `chartbook/scripts/chart_cross_dim_stability.py` + `chartbook/recipes/cross-dim-stability.md`，复用 conformance 闸与 golden 测试基础设施。只吃 predictions 长表。

### 4.1 CLI

```bash
python3 chartbook/scripts/chart_cross_dim_stability.py \
  --pred predictions.parquet --out-dir <workdir>/charts --focal-model <模型名>
```

模型数 ≥ 2（否则抛错，与 worst-slice-compare 同风格）；对 focal 之外的**每个**他模型各算一组配对结果。

### 4.2 两个正交维度（逐配对 focal vs other，均在对齐行上算）

1. **time_split（时间对半）**：distinct `window_ts` 排序后对半切（奇数窗前半多一窗，`cut_ts` 落盘）；每半算 `diff = mean(row_rmse_focal) − mean(row_rmse_other)`；`consistent = (d1 * d2 > 0)`（任一为 0 → false 并 note "半区差为零，视为不稳"）。
2. **caliber_switch（口径切换）**：`row_diff` = 行 RMSE 均值口径下的 focal−other；`pooled_diff` = 点级 pool RMSE（全点 sqrt(mean(err²))）口径下的 focal−other；`consistent = (row_diff * pooled_diff > 0)`。

### 4.3 JSON schema

```json
{"recipe": "cross-dim-stability", "focal": "A",
 "pairs": {"B": {
   "time_split": {"cut_ts": "2024-02-10", "n_first": 6, "n_second": 6,
                  "first_half_diff": -0.1333, "second_half_diff": -0.1333,
                  "consistent": true},
   "caliber_switch": {"row_diff": -0.1333, "pooled_diff": 0.0843,
                      "consistent": false},
   "verdict": {"time_stable": true, "caliber_stable": false}}},
 "note": "同一份 predictions 的图属同一证据维度；本图给正交切分稳定性。
          time_stable 是假设升级必查项；caliber_stable=false 不阻塞升级，
          但结论必须标注口径敏感、限定口径。"}
```

PNG 副产品：每配对两组柱（两半差 / 两口径差），焦点色与 chartbook 现有图一致。

### 4.4 判读节要点

- `time_stable=false` → 总差距是"半程运气"候选，禁升假设，回 rolling-stability 看变点；
- `caliber_stable=false` → 结论限定口径（"A 更好"只在行均值口径成立），提示去 horizon-degradation 看是否少数 step 拖爆 pooled 口径；
- 两维都稳 ≠ 独立数据验证——仍是同一份数据的重切分，"已证实"层级依旧要走三道门之门 2（先预测后看数）或外部实验。

## 5. 引擎层改动

### 5.1 mechanisms.md §2「多证据线一致性」增补小节「证据维度」

要点（原则级，对所有 playbook 生效）：
- 同一份原始数据派生的所有产物（全部 13+1 张图、gap 统计）属**同一证据维度**；同维度内多产物方向一致只能算一条线的内部自洽，不叠加置信度。
- 「现象 → 假设」除既有条件外，须至少一条**正交切分**上方向稳定：时间重切 / 口径切换 / 外部材料（训练日志、特征真值、模型档案）三类任一。各 playbook 在自己的 upgrade_rule 里声明具体用哪条（本轮 model-comparison 用 cross-dim-stability 的 time_split）。
- argmax 型点名（最差片/最差点/最差 step）必须先过随机基线（置换或解析 null），未过者只能写"存在波动"不能点名对象。

### 5.2 golden 纪律的种子豁免（`playbooks/_playbook-spec.md` §5 + `chartbook/_recipe-spec.md` 验证步节）

现行"零随机（Date/random 都不许）"约束的是 **make_golden 的数据构造**。增补边界：分析脚本内的**固定种子置换**是允许的伪随机——种子必须是 CLI 显式参数且进 JSON 落盘，期望值来自 reference 同种子实跑（改种子=改期望，须连 manifest 一起改并重跑 pytest）。

## 6. model-comparison 落地清单

### 6.1 frontmatter

- Stage 2 `charts` 列表加 `cross-dim-stability`（13 → 14 张）。
- `evidence_lines` 增第三条：`{id: cross-dim, stage: 2, output: charts/cross-dim-stability.json}`。
- `upgrade_rule` 改为："总差距方向与主导切片方向一致（slice-gap 仅在 perm verdict=significant 时计入）**且** cross-dim 的 time_split 一致，才把差距结论从「现象」升「假设」"。

### 6.2 正文

- §1 首要陷阱补第四条：**多图同源≠多证据**（13 张图共享一份 predictions，方向一致只是内部自洽）。
- §2 Stage 2 命令模板补 cross-dim-stability 一行（传 `--focal-model`）；worst-slice-compare 说明 perm 默认开、种子 0。
- §3 证据升级规则改三条腿：两线一致（slice 线以 significant 为准入）+ |sign_z| ≥ 2 + time_stable=true；caliber_stable=false 时升级不阻塞但结论须限定口径。
- §4 停顿汇报增两项：perm verdict（点名/不点名切片）与 cross-dim 两维结论。
- §6 反驳门增两条目："切片点名过了置换基线吗（perm_p、null_q95 抄进结论）""换时间对半/换口径方向变了吗"。

### 6.3 golden（数据不变，纯增量）

`make_golden.py` 与 `predictions.csv` **不动**。现有构造（A 按月 0.8/2.5/0.8、B 恒 1.5、每月 4 日 × 8 step 符号交替）解析可得：

- **time_split**：12 窗对半（cut 在 2024-02-10 后），前半 = 1 月 4 窗(−0.7) + 2 月 2 窗(+1.0) → diff = −0.1333；后半 = 2 月 2 窗(+1.0) + 3 月 4 窗(−0.7) → diff = −0.1333 ⇒ `time_stable = true`。
- **caliber_switch**：pooled A = sqrt((8×0.8² + 4×2.5²)/12) = sqrt(2.51) = 1.5843 > B 1.5 ⇒ `pooled_diff = +0.0843` 与 `row_diff = −0.1333` 反号 ⇒ `caliber_stable = false`。现有构造**天然给出判别性结构**：时间稳、口径翻转——正好走通"升级不阻塞但限定口径"分支。
- **perm**：4 个 2 月日块全落一片才有 conc=1.0，随机 4-4-4 分配下概率极低 ⇒ `verdict = significant`（`perm_p`、`null_q95` 期望值由 reference 以 seed=0/n_perm=200 实跑取得，manifest 用 `le`/`between` 留容差）。

manifest stage 2 `expect` 增量：`perm.verdict eq significant`、`perm.perm_p le 0.05`、`pairs.B.time_split.consistent eq true`、`pairs.B.caliber_switch.consistent eq false`、两半 diff `between` −0.14/−0.13。新增 `reference/stage2_crossdim.py`（照 §4 菜谱经 sys.path 引 chartbook 脚本，与 stage2_slice.py 同构），注册进 `test_gen_gate.py` 的 REFS。

## 7. 测试与守卫

- `chartbook/tests/test_chart_worst_slice_compare.py` 扩展：现有植入（A 仅 2024-02 三倍误差）加 perm 断言 significant；新增**弥散诱饵** case（A 各月同幅小差 ⇒ conc ≈ 1/3、not-significant）——防"逢集中必点名"。
- 新 `chartbook/tests/test_chart_cross_dim_stability.py`：一个双稳 case（同幅同向）+ 一个口径翻转 case（复用 golden 构造思路），数值精确回收。
- `test_recipes_conform.py` 自动覆盖新 recipe（frontmatter 7 键 + 判读节）；`test_charts_decl.py` 的全 playbook frontmatter 加载守卫自动覆盖 stage charts 引用新 recipe id 的合法性。
- 顺序约束：新 recipe 文件先于 playbook frontmatter 改动落地（否则 charts 校验红）。
- 验收：全仓 pytest 绿（246 + 新增）；上述判别性数字全部回收；未触碰 row-diagnostic/ 与 docs/skill解析/ 的既有工作区改动。

## 8. 已知局限（写进产物，不藏在 spec）

- 置换基线的 block=日：月内跨日相关未校正，显著性偏乐观——判读节写明"必要条件而非充分证明"。
- 时间对半/口径切换仍是**同一份数据的重切分**，只防"运气与口径伪影"，不等于独立数据验证；「已证实」层级的门 2（先预测后看数）与外部实验要求不变。
