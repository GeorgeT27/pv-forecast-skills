---
name: pv-feature-blame
description: 光伏功率预测的「预测特征质量归因」——当输入特征本身是预报量（NWP/气象预报特征，未来 192 点与预测功率同期）且预报错了会拖累功率预测时，找出**哪些 feature 导致指标变差**，并可反事实验证。当用户说"我需要看看哪些feature导致我的指标变差/是不是辐照或某个气象预报不准拖累了准确率/哪个特征害了这些坏样本/feature 预测质量归因/把坏 feature 换成真值再预测验证一下（反事实）/相邻两行对同一时刻的预测差距巨大（预报翻新跳变、预测不稳）/是不是几个坏特征一起才把这行带坏（联合致坏）"时使用。输入三件套：test.parquet（真值）、predict.parquet（1..N 个模型预测列，给几个分析几个）、**feature_true.parquet（每特征的预测序列与真值序列对照，每行一个窗口时间戳、每格 192 点 list）——用户没给必须先 AskUserQuestion 索要，只有用户明确确认"没有"才走窗口重叠重建的降级模式，绝不静默降级**。方法 = 逐行特征误差 z 分数 + 全局校准（该行该特征异常 且 与该口径行误差全局相关，两者都命中才点名），可选反事实：经用户的 FastAPI 预测服务把被点名特征替换为真值重预测，看指标变差是否消失。区别于 pv-result-analysis（评估预测结果与月度归因，不做特征侧对照）：本技能要 feature_true 对照文件。路由优先级：本技能是专用技能，在上述场景内优先于泛化引擎 ts-diagnose，但让位于覆盖同场景的已固化代理技能；触发边界收窄——无 feature_true 对照的一般变量重要性/重要性排序 → ts-diagnose 的 feature-importance。
---

# 光伏预测特征质量归因（feature blame + 反事实验证）

**问题**：预测输入里的一部分特征本身是预报量（历史 672 点 = 观测值，未来 192 点 = NWP 预报，
与预测功率同期）。预报错的特征会把功率预测带坏。目标：**先按考核口径找出坏行（每行 = 一个
窗口起点时间戳），再对坏行逐特征对比 预测 vs 真值，点名元凶特征（CSV），最后（可选）反事实
验证——把被点名特征换成真值经用户的 FastAPI 重预测，看指标变差是否消失。**

## ⚠️ 首要框定：特征误差大 ≠ 该特征有罪

1. **模型可能对该特征根本不敏感**——特征预报错得离谱但预测纹丝不动。所以点名要过两关：
   该行该特征误差异常（z ≥ 阈值）**且**该特征误差与该口径行误差全局相关（Spearman ≥ 阈值）。
   反事实（Stage 4）是最终仲裁——没跑反事实不得标「已证实」。
2. **共线特征成簇**——辐照/云量/温度的预报误差往往同涨落，统计上分不开谁是元凶。同簇只报簇
   不点名单个（blame_summary 的 collinearity_clusters 为证），簇内定罪只能靠反事实逐个替换。
3. **坏天气日一切特征同时坏**——大风雪天所有 NWP 都错、功率也难预测，全局相关可能只是天气
   共变。升「假设」前按天气型条件化复算（借 pv-result-analysis 的 weather_class）。
4. **单换无效 ≠ 无罪**——冗余结构下两个坏特征各自单换都修不好、一起换才修好（金标准彩排
   实测 Δ=0 但最小修复集 = 两特征）。断「特征无罪」前先过 Stage 4 的 minimal-set。
5. **跳变大 ≠ 有罪**——相邻行是同一物理时刻的两次起报，预报翻新跳变是预期物理且文献实证
   跳变与预报误差只有弱相关。点名「翻新致不稳」须过 churn 两关 + neighbor-swap 反事实。
6. **稳定的系统偏差 ≠ 有罪**——功率模型在有偏预报上训练会学会补偿它（共适应）；点名基于
   剥掉 ε_sys 后的波动 ε_res（Stage 1.5），sys_frac 高的特征"修了"对固定模型可能有害。
   白噪声 ε_res 也不点名（可约性闸）——上游改不了的误差点名是废话。

## 数据契约（时间戳语义与主技能一致：每行 = 序列窗口，相邻行 15 分钟）

- `test.parquet`：真值。评估只用 `observe_power_future`（未来 192 点功率）；特征列若为
  ≥672 点 list（历史观测 + 未来预报拼接），Stage 0 会拿历史段交叉核验 feature_true 的真值。
- `predict.parquet`：模型预测。**全部 192 点 list 列都当模型列**（只给 1 个模型就分析 1 个）。
- `feature_true.parquet`：**本技能的核心新输入**。每行一个窗口时间戳（列名可能是
  timestamp_win，Stage 0 自动侦测），每特征两列：预测序列 + 真值序列（各 192 点 list），
  命名约定不限（_pred/_true、pred_/label_ 等，Stage 0 启发式配对，配不上的问用户）。
- **硬规则**：feature_true 没给 → AskUserQuestion 索要；用户明确说"没有"→ 写
  `feature_true_status="user_confirmed_missing"` 走降级（窗口重叠重建真值，见
  references/blame-methods.md，证据自动降一级）。**绝不静默降级。**
- 口径：坏行按 config.metrics 里的口径各自找——默认 **`rmse_192`** = 每行全 192 点 RMSE
  （全行参与，2026-07 起的考核口径）；可选 `ultra_short` = 每行第 16 点误差、`short` =
  09:00 行的 [59:155] 切片 RMSE。常量 import 自 `pv-result-analysis/scripts/data_utils.py`，
  绝不本地重定义。

## Step 0.5：载入项目上下文与实验线（首次问一次，之后自动复用）

1. **定位 project-context**：读 `references/project-context.pointer` 的 `path:` 行；缺失 →
   探 `<技能目录>/../project-context`；仍无 → AskUserQuestion 问路径，写回 pointer。
2. **选实验线**：`blame_config.json` 已有 `experiment` → 直接载入 `experiments/<名>.json`，
   不再问；没有 → 列出 experiments/*.json 让用户选或新建。
3. 载入后：`data_paths.test_label/predictions` 直接复用；`data_paths.feature_true` 与
   `predict_api` 缺【待补】且本次要用 → 追问一次并**补写回实验线 json**。

## Step 0：Orient —— 每次进入先定位阶段（真相以产物为准，续跑无需记忆）

```bash
python3 "<SKILL>/scripts/run_orient.py"          # 报当前阶段 + 前置 ✓/✗ + feature_true 硬规则
python3 "<SKILL>/scripts/run_orient.py" --goto 2 # 想直达某阶段：校验前置
```

（`<SKILL>` = `/Users/tqa946816/Documents/华为/光伏预测/结果分析skill/pv-feature-blame`。）
没有 config → 回 Step 1 收集路径。orient 重扫 probe_schema.json / bad_rows_summary.json /
blame_report.csv / FINDINGS.md 等产物定位第一个未完成阶段。

## Step 1：收集路径写 blame_config.json（字段说明见 scripts/fb_common.py 头部）

用户通常按 `references/prompt-template.md` 的标准模板发起——字段直接映射 config
（三件套路径 / 模型列 → --models / 口径默认 rmse_192 / top_pct / API 地址与契约 / 实验线），
缺的字段才问。用户给了 FastAPI 示例代码时：照示例填 adapter.py 的 payload/响应契约，
仍必须 --dry-run 给用户过目。top_pct 默认 10：坏行 = 高于均值且误差进 top 10%，数据量小时
跟用户确认要不要调。**环境**：`python3 -c "import pandas,numpy,scipy,pyarrow"`，缺则
`pip install -r 结果分析skill/requirements.txt`。

## 六个阶段（每阶段一个脚本，产物落盘自足，可断点续跑）

| 阶段 | 做什么 | 脚本 → 产物 |
|------|--------|-------------|
| **0 探查** | 时间戳列/模型列/特征对发现 + 对齐 + 窗一致性 + 真值交叉核验；unmapped 列问用户后写回 | `probe_schema.py` → `probe_schema.json` + `feature_pairs.json` |
| **1 坏行** | 每口径×每模型定位坏行（>均值 且 top N%），**全量排名**落盘 | `find_bad_rows.py` → `bad_rows_<口径>_<模型>.csv` + `bad_rows_summary.json` |
| **2 归因** | 三步：**剥系统偏差**（feature_decompose.py：稳健加性回归 ε_sys→ε_res+可约性，Stage 1.5）→ ε_res 两关（z + 全局 Spearman）点名 + 可约性闸 + 共线簇 → 翻新跳变两关（免 API） | `feature_decompose.py` → `feature_decomp.json` + `eps_res_*.npy`；`feature_blame.py` → `blame_report.csv` + `blame_summary.json`；`feature_revision.py` → `revision_report.csv` + `revision_summary.json` |
| **3 现象** | **停顿**：主 agent 把坏行清单+被点名特征+翻新画像报给用户，问要不要做反事实 | `FINDINGS.md`（含"现象"） |
| **4 反事实** | 门控·可选·**预算阶梯**：`oracle`（全换测缺口 G，防冤枉）→ `per-feature`/`all-blamed`（边际）→ `minimal-set`（最小修复集，抓联合致坏）→ `lattice`（最差行 Shapley+交互）→ `neighbor-swap`（翻新致不稳仲裁）；首跑必 `--dry-run` 给用户确认计划表+payload | `counterfactual_api.py`（决策数学在 `cf_logic.py`，已过闸）+ `adapter.py` → `counterfactual_results.csv` + `counterfactual_summary.json` |
| **5 结论** | 反驳门（十条，见 references/blame-discipline.md）+ 升级判定 | `CONCLUSION.md` |

## 质量闸（改脚本后必须重过闸才碰真实数据）

```bash
python3 "<ENGINE>/scripts/gen_gate.py" --script "<SKILL>/scripts/feature_blame.py" \
    --playbook "<SKILL>/SKILL.md" --stage 2      # 同理 stage 0/1；<ENGINE> = ts-diagnose 目录
```

金标准埋点：f_blame（崩坏且耦合进预测→必须点名）、f_decoy（误差更大但零耦合→必须不点名）、
f_jumpy（翻新跳变耦合进 pred_M3 → revision 两关必点名；其真值误差路径 ρ=0.28 恰低于点名线——
新轴的存在理由）、f_jumpy_decoy（跳变更大但零耦合→必须不点名）。Stage 4 的决策数学在
`cf_logic.py` 以 `--selfcheck` 过闸（stage "4"）；HTTP 层要活 API 无法闸——以 `--dry-run`
计划表+payload 用户确认步兜底。

## 编排：主 agent 调度，重活外包 subagent（brief 见 references/subagent-briefs.md）

Brief G：Stage 2 模型多时按模型分片（`--models` 各写各的产物，防竞态）；Brief H：Stage 4
批量 API 调用（结果逐行追加、可中断续跑）；Brief I：Stage 4 阶梯按层分批（subagent 跑一层
只回 JSON 摘要，禁自行放宽 τ/G 阈值）。**单写者纪律**：`blame_state.json`/`PROGRESS.md`/
`FINDINGS.md`/`blame_config.json`/`feature_pairs.json` 只由主 agent 写；subagent 只读
JSON/CSV、只写自己的产物分片。parquet 内容与 payload 明细永不进对话。

## 结论纪律（细则见 references/blame-discipline.md）

- **现象**：z 高且全局相关（单口径单模型的 blame_report 行）。
- **假设**：跨模型或跨月稳定 + 天气型条件化后仍在 + 有机制解释（该特征的 NWP 上游，可借
  pv-result-analysis 的 drift-and-nwp.md）。
- **已证实**：唯一通道 = Stage 4 反事实。真值替换类须先过 oracle 的 G 闸（缺口不显著 =
  「非特征问题」，不得归因该行）；单换有效 = 单特征可修；单换无效但最小修复集找到 = 需联合
  修复（点名整个集合）；「翻新致不稳」的已证实 = neighbor-swap 后 churn 消减。
  **用户拒绝反事实 → 结论最高只能到「假设」并注明。**
- 坏行样本 <10 只描述不定论；共线簇内不点名单个。

## 常见错误

- ❌ feature_true 没给就拿窗口重叠重建凑数（硬规则：先问用户，确认没有才降级且注明）。
- ❌ 只看特征误差大就点名，不看全局相关（诱饵：误差大但模型不敏感——金标准里专门埋了）。
- ❌ 共线簇里挑一个点名（辐照/云量同涨落分不开，簇内定罪只能靠反事实逐个替换）。
- ❌ 坏天全特征同坏不做天气型条件化就升「假设」。
- ❌ 自己重新定义第 16 点/[59:155] 而不 import data_utils（口径漂移 = 整条归因链作废）。
- ❌ 反事实不先 `--dry-run` 给用户确认 payload 就打真实 API（neighbor-swap 还须单独确认
  `api.neighbor_swap_confirmed`——拼接序列行间不连续，服务端可能拒收）。
- ❌ 把预报翻新跳变当窗口构造 bug（窗一致性闸只闸真值列；predict/预报特征行间差是预期物理，
  是 feature_revision 的信号）。
- ❌ 单特征替换 Δ≈0 就断言该特征无罪（先跑 minimal-set 排除联合致坏——冗余结构单换必然无效）。
- ❌ 看到某特征翻新跳变大就点名（文献：跳变与误差弱相关；须 churn 两关 + neighbor-swap 仲裁）。
- ❌ 对 192 点 list 做跨行分布统计不先重建物理序列（窗口重叠 671/672，同一物理点重复几百次）。
- ❌ 把 blame_report 的相关性结论直接写成"已证实"（相关 ≠ 因果，反事实才是仲裁）。
- ❌ 在原始 ε 上点名不剥系统偏差（冤枉被模型吃掉的稳定偏差——金标准 f_sys_bias 专门埋了
  这个陷阱：raw Spearman 高但剥后必须洗清；且 z/ρ 尺度不变，光靠塌 ε_res 量级挡不住，必须
  过 sys_frac 代码闸）。
- ❌ 点名 reducibility_frac < 0.1 的白噪声特征（上游改不了；金标准 f_irreducible 双关全过、
  唯可约性闸挡得住）。

## 运行后回顾

每次实跑把暴露的问题写回：脚本 bug → 改 `scripts/` 并**重过 gen_gate**；新遇到的特征命名
约定 → 补 `probe_schema.py` 的启发式表；确认的项目事实（如某特征的 NWP 供应商变更）→
`<project-context>/event-log.md`；API 契约变化 → 改 `scripts/api_adapter_template.py` 说明。
