---
name: pv-result-analysis
description: 光伏功率预测（PV power forecasting）结果评估与分析。当用户需要评估模型预测结果、对比 predicted.parquet 与 true_label.parquet、运行 metric.py 计算准确率指标（ods_ultra_short / ultra_short / ods_short / short / 48hours 五种口径）、生成 M1-M4 及 ensemble 的月度指标 Excel，或诊断准确率变化（如"为什么6月预测准确率比5月下降"）时，务必使用本技能。凡是涉及光伏预测结果评估、指标计算、误差归因、月度/时段对比分析的任务，即使用户没有明确说"结果分析"，也应使用本技能。
---

# 光伏功率预测结果分析

对已完成的光伏功率预测结果（predicted.parquet）与真实标签（true_label.parquet）进行指标计算与深入分析。

## 项目背景与数据结构

理解数据结构是正确分析的前提，先读这一节再动手。

- **任务**：光伏（PV）功率预测，时间序列问题，15 分钟粒度（96 点/天）。
- **跨站设定（2026-07-09；2026-07-10 更正测试站位置）**：**5 个电站的 2025 全年数据联合训练**（华能北方润达、国能和熙光储、泗洪、白马湖、西北戈壁小壕兔），**测试留出站 = 雅砻江（在江苏苏州），完全不在训练里**——**零样本跨站迁移**。⚠️ 雅砻江**不是**四川高原水光站（旧稿"柯拉/4600m"系检索误判，已作废）；它在江苏苏州，**与训练站泗洪/白马湖同气候带（江苏平原湖区北亚热带湿润），气候上在训练分布内**。训练站跨两类气候带（江苏平原湿润 + 西北干旱高辐照），雅砻江属前者（详见 `references/station.md`/`seasonality.md`）。因此**第一大分析主线是"雅砻江离训练分布多远、最像哪个训练站"**——预期最像泗洪/白马湖、跨站漂移小，跨站差异更可能来自站点特异（渔光/限电/本地微气候）而非气候没见过。
- **测试输出是单站（雅砻江）**：指标 Excel、图、结论都只针对雅砻江，不存在"两个测试站混算"的问题。但**训练侧要分站看**——判断雅砻江像谁时，5 训练站要逐站比较（跨站漂移诊断），不能 pooled 成一个平均气候。
- **训练/测试都是 2025**：无跨年成分。训练集不参与指标计算，用途是**跨站漂移诊断的基准**（5 训练站 pooled + 逐站 vs 雅砻江，见 `references/drift-and-nwp.md`）——回答"模型是不是没见过这个站的这种天"。数据结构：训练与测试同构（同样的滚动窗口时序表）。**训练集是可选输入**：没放（如本次只评估雅砻江预测）就跳过跨站漂移诊断（`run_drift.py` / 图#11/#12），metric 与其余图谱照常。
- **时间戳语义（关键，取点全靠它）**：
  - 每一行的 timestamp 是该样本序列的**起点**。例如某行标为 `2025-01-01 00:15:00`，表示该行的序列从 00:15 开始。
  - 行与行之间间隔 15 分钟（滚动窗口，每行前进一步）。
  - 每行从起点开始有 672 个历史点；预测时域为 192 个点 = 48 小时（`48hours` 口径的由来）。
  - **推论：相邻行窗口重叠 671/672 个点。** 做任何分布统计（直方图、分位数、KS 检验）前，必须先把滚动窗口**重建为物理连续序列**（`data_utils.rebuild_series`），直接对行级 list 统计会把同一物理点重复计数几百次。
- **特征列**（每个时间戳一行，值都是 list）：
  - `observe_power`：672 个历史功率点。
  - `observe_power_future`：未来 192 个真实功率点，**这是标签（label）**。
  - `GHI-solargis`、`temp solargis`：各 672+192 个点；未来 192 段是气象预报，作特征。
  - `SSRD_pos_1`~`SSRD_pos_9`、`t2m_pos_1`~`t2m_pos_9`：9 个网格点位的数值天气预报（辐照与 2 米气温）。
- **本技能的输入不是模型**，而是两份已生成的结果文件：`predicted.parquet`（对未来 192 点的预测）与 `true_label.parquet`（对应真实功率）。
- **⚠️ true_label.parquet 常沿用完整训练 schema（带上面所有特征列）——指标计算只用 `observe_power_future` 这一列（=真值 label），其余列（observe_power/GHI-solargis/temp/SSRD_pos/t2m_pos…）对评估无关，不要拿它们算指标或下结论。** 之所以强调：schema 侦察会把这些训练列一并打印出来，容易误当作评估输入；scripts 取 label 一律走 `data_utils.LABEL_COL`，别手写 pandas 时顺手把气象列也算进去。跨站漂移诊断（图#11/#12）确实要气象/功率特征——train 侧来自训练集 parquet，**test 侧（雅砻江）若要用 true_label 里的气象列，先跟用户确认这些列是雅砻江的真实值还是训练遗留的占位**，拿不准就别用、只报 label 指标。

## 执行流程：四个阶段

一次完整分析产出很长，一口气全生成既拖慢反馈也容易在最贵的归因环节浪费在用户不关心的现象上。因此按四个阶段推进——**1→2→3 连续执行**，每个边界只向用户报一段摘要；**阶段 3→4 之间是唯一的强制停顿点**：把现象清单报给用户，由用户点名哪几条值得深挖，再进入阶段 4。

| 阶段 | 做什么 | 交付物 | 边界动作 |
|------|------|--------|---------|
| **Stage 1 数据与指标** | Step 1（路径+质检）+ Step 2（metric.py） | `analysis_config.json`、`suspect_days.csv`、5 个指标 Excel | 报指标摘要（各模型各口径月度值 + ensemble 是否确实最优），继续 |
| **Stage 2 相关性** | Step 3 前半：误差矩阵 + 图#2（+图#1） | `02_error_corr.png` + stats.json | 报同质化结论（相关矩阵 + M2 是否如预期相关最低），继续 |
| **Stage 3 事实提取** | 图#3/#4/#7/#8（按需 #5/#6），过稳健性门槛 | **现象清单**：FINDINGS.md 中状态="现象"的条目（带数字+图链接） | **停下来**：向用户报现象清单，问哪几条进 Stage 4 |
| **Stage 4 深归因** | 诊断 Playbook A/B + references 全套 + hypotheses.md + 反驳门 | 升级为"假设/已证实"的 FINDINGS 条目 + ANALYSIS.md 反驳门记录 + 面向主管的 `CONCLUSION.md` | 展示图 + 数字 + 结论 |

阶段纪律：

- **Stage 3 只写"看到了什么"**：现象 + 数字 + 稳健性检验结果，**禁止机制语言**（不写"因为 PatchTST 的 RevIN…"）。**Stage 4 才允许"为什么"**：必须引用 models.md/station.md/seasonality.md 已填字段 + hypotheses.md 假设 ID，并过反驳门。把"事实"与"故事"物理隔开，既防事后编故事，也让最贵的步骤只花在用户点名的现象上。
- **阶段进度靠产物判定，不设状态文件**：指标 Excel 在 → Stage 1 完成；`02_error_corr.png` 在 → Stage 2 完成；FINDINGS.md 有"现象"条目 → Stage 3 完成。续跑（pv-analysis-resume）从第一个未完成阶段进入。
- **ensemble 的分析边界**：ensemble 是 M1-M4 的均值组合，无独立特征与机制（models.md 该节为空）。指标层（Stage 1 摘要、图#3、Stage 3 现象）**必须报告**它——是否优于最佳单模型、哪些月不是；但机制层（Stage 4、Playbook B、图#4–#8 的模型聚焦）**只做 M1-M4**——"ensemble 为什么好/不好"的正确问法是"成员误差是否分散"（图#2）与"离事后最优还有多远"（图#9），不是给它编独立机制故事。

## Step 1：定位路径 + 质检（Stage 1）

任何分析开始前必须先确认三个路径，缺一不可：`metric.py`（指标脚本）、`true_label.parquet`（测试集真值）、`predicted.parquet`（预测值）。

- **调用契约**：用户调用本技能时会同时给出**训练集 parquet、测试集（true label）parquet、metric.py** 三个路径；预测值文件如单独提供也一并记录。缺任何一个直接开口问，不要自行搜索猜测——不同月份/模型会有多份文件，选错整个分析都错。拿到后 `ls` 逐一确认存在。
- `metric.py` 例外：没给可在项目目录内搜（`find <项目根> -maxdepth 4 -name "metric*.py"`），多个候选列出让用户确认。
- 测试站固定是**雅砻江**。`train_set`（5 站联合训练集）**可选**：放了才能做跨站漂移诊断，确认它是**一个 pooled 文件**还是**逐站多个文件**（逐站填 `train_stations`）；本次不放训练集就省略这两个字段，跳过漂移诊断，其余照常。

把路径写进工作目录下的 `analysis_config.json`（供本次及续跑复用）：

```json
{
  "station": "yalongjiang",
  "metric_py": "<metric.py 绝对路径>",
  "train_set": "<5 站联合训练集 parquet（pooled）；可选——不做跨站漂移可省略>",
  "true_label": "<雅砻江 test/true_label parquet 绝对路径>",
  "predicted": {"M1": "<路径>", "M2": "<路径>", "M3": "<路径>", "M4": "<路径>", "ensemble": "<路径>"},
  "pred_col": "<可选：预测列名；缺省则 run_analysis.py 自动侦测 192 宽的列>",
  "train_stations": {"泗洪": "<路径>", "白马湖": "<路径>", "小壕兔": "<路径>", "润达": "<路径>", "和熙": "<路径>"}
}
```

`predicted` 按模型名记字典（只给部分就填有的）。`train_stations` 可选——给了 `run_drift.py` 就做**逐站漂移**（找雅砻江最像哪个训练站）；没有则只做 pooled。

**环境准备（本会话第一次跑 Python 前一次）**：缺包则装（requirements.txt 在技能目录上一级）：

```bash
python3 -c "import pandas, numpy, matplotlib, pyarrow, scipy, openpyxl" 2>/dev/null \
  || pip install -r "/Users/tqa946816/Documents/华为/光伏预测/结果分析skill/requirements.txt"
```

**质检（先于一切指标计算——坏 label 会污染所有下游结论）**。已固化成脚本，在工作目录跑：

```bash
python3 "/Users/tqa946816/Documents/华为/光伏预测/结果分析skill/pv-result-analysis/scripts/run_quality_check.py"
```

它做：schema 侦察（列名与 `data_utils.py` 顶部 CONFIG 对不上时**只改 CONFIG，不改逻辑**；predicted 常把 timestamp 存成 index，schema 看不到属正常；**true_label 的 schema 里那一堆训练特征列是 schema 沿用、与评估无关，只认 `observe_power_future`**）、基础完整性（重复戳/15min 网格缺口/常值段）、滚动窗口一致性抽查（不一致则取点口径全不可信，停下报告用户）、重建序列扫可疑日 → `suspect_days.csv`、载训练集抽查。

**可疑日的二分处理**：区分"错误"（录入/传感器故障 → 从统计剔除并记录）与"事件"（限电/停机/极端天气 → 保留数据、进 `references/event-log.md`、归因时显式考虑）。两者处理相反，不可一律当异常"修掉"——修掉真实事件等于把最有信息量的样本扔了。

## Step 2：调用 metric.py 生成五个 Excel（Stage 1）

产出 **5 个 Excel**（M1、M2、M3、M4、ensemble）。每表：列 = YearMonth；行 = RMSE/MAE/ACC，每个模型覆盖下面 5 种口径（口径 × 指标的 sheet/行布局以 metric.py 实际输出为准）。

**五种口径**（取点全靠"timestamp=序列起点、第 n 点=起点后第 n 个 15 分钟"，动手前回读时间戳语义；索引 0-indexed）：

| 口径 | 取点 | 聚合 |
|------|---------|------|
| `ods_ultra_short` | 每行第 **16** 点（起点后 4h，超短期考核点） | 先按天算指标，再当月各天求平均 |
| `ultra_short` | 同上（第 16 点） | 当月所有点合并直接算 |
| `ods_short` | 只取 **timestamp=09:00** 的行，其第 **59–155** 点（次日全天，切片 `[59:155]`=96 点） | 先按天算，再当月平均 |
| `short` | 同上（09:00 行第 59–155 点） | 当月合并直接算 |
| `48hours` | 全部 **192** 点 | 整体精度，不取点/不拆天 |

`ods_` 前缀 = **先按天算再对天平均**；无前缀 = **当月全部点合并一次算**。两者数值不同是正常的（按天平均每天等权，整月合并让点多/大误差天权重更高），别误判为 bug。

**入口 = metric.py 的 `SolarMetricCalculator.generate_report`**（五口径逻辑都在内部）。按路径 `importlib` 动态加载后调用：

1. **首次运行**：先 `inspect.signature` 确认 `__init__` 与 `generate_report` 参数（训练集用在哪、预测怎么传、输出写哪），跑通后把确切调用填进下方"已固化调用"——之后照抄。
2. 对照上面五口径定义核对源码取点逻辑（第 16 点、`[59:155]`、0-indexed），不一致以源码为准、报告用户并更新本文档。
3. 按 M1-M4 与 ensemble 分别运行，产出 5 个 Excel（测试站只有雅砻江，产物存 `figures/yalongjiang/`）。
4. 首跑做**口径对账**：任选一月用 pandas 自算 RMSE 与 generate_report 对比（相对差 <1% 视为一致），验证取点理解没跑偏。之后可跳过。

#### 已固化调用

<!-- 待首跑后填入：SolarMetricCalculator 的确切构造参数与 generate_report 调用示例（含输出路径约定）。填入后上面第 1、2、4 步对后续会话不再适用。 -->

## Step 3：可视化深入分析（Stage 2–3）

Excel 只能告诉你"哪个月/哪个口径变差了"，回答"为什么"要回到逐样本误差做可视化。本节内部：**误差矩阵 + 图#2 = Stage 2**；**其余图谱的事实提取 = Stage 3**（产出现象清单后停下问用户）；机制归因是 Stage 4。

**数据准备**：读 predicted 与 true_label 按 timestamp 对齐得两个 `(样本 × 192)` 矩阵 → signed 误差 `over_error = pred − true`（正=高估，负=低估）→ 逐样本 RMSE。另做**日级天气分型**（GHI 算日晴空指数 kt 与日内波动 σΔ → 五类：晴稳 kt≥0.65 / 多云平稳 0.35≤kt<0.65 / 阴稳 kt<0.35 / 多云波动 σΔ 超分位 / 突变日 kt 骤变，优先级最高），存 `weather_class.csv`。天气分型是"为什么"类问题的核心工具：把"X 月变差"分解成"坏天占比变了"和"类内能力变了"两个可分别验证的因子。

**以上计算与全部图谱已固化在 `scripts/`**（`data_utils.py` + `plots.py`，用法见 `scripts/README.md`）。**优先复用脚本，不要现写 pandas。** 标准命令（质检通过后跑；范围按问题改）：

```bash
# 月度诊断（必画 #1/#2/#4/#8；可加 5,6,7,9）：
python3 "<SKILL>/scripts/run_analysis.py" --range 2025-06 --figs 1,2,4,8
# 分布漂移诊断（需训练集，详见 references/drift-and-nwp.md）：
python3 "<SKILL>/scripts/run_drift.py" --cols "GHI-solargis,observe_power_future"
```

（`<SKILL>` = `/Users/tqa946816/Documents/华为/光伏预测/结果分析skill/pv-result-analysis`。）

**每张图落盘 PNG + 同名 `.stats.json`；PNG 只给人看，分析一律读 stats.json，不要 Read 图。** stats.json 已做到**自足**——把图上一切可判读的数字都写进去了：#5/#6 存全 192 步/全时段完整曲线 + `trend`/`max_jump_idx`/`roughness` 形状描述符，#4/#7/#9 存逐日序列，#1 存 slope/intercept/`pred_by_true_bin`，#11 存逐月分位数摘要，#2/#8/#12 存完整矩阵/曲线。所以判读流程 = **读 stats.json 的完整曲线/数字判走势（不要只看单点）→ 对号 `references/figure-diagnostics.md` 的形态判读 → 结合 references/ 背景写结论**，全程无需读图（读图费上下文，小上下文模型会爆）。若发现某图上有信息 stats.json 没给，那是 `plots.py` 的 bug，去补 stats.json，而不是改成读图。列名不符只改 `data_utils.py` 顶部 CONFIG；首跑修正提交回 scripts/。

### 图谱目录（判读见 `references/figure-diagnostics.md`，调用见 `scripts/README.md`）

月度对比诊断必画 #1/#2/#4/#8。

- **#1 True vs Pred 散点**：系统性高/低估？slope<1 → 大功率段被压低（配 R²=corr² 看齐不齐）。
- **#2 模型间 over_error 相关热力图**：同质化程度 → ensemble 组合增益空间；M2 是否如预期相关最低。
- **#3 月度指标对比**（来自 Excel）：哪月/哪口径/哪模型变差；ods 与非 ods 差距 → 误差是否集中在坏天。
- **#4 逐样本 RMSE 时间序列**：坏天/坏时段定位；坏天是共因还是单模型特异。
- **#5 按预报时效误差曲线**：误差随时效增长形态；超短期 vs 短期口径差异来源。
- **#6 日内时段误差剖面**：早晚坡段 vs 正午谁差；低估/高估的时段不对称性。
- **#7 坏天定位**：坏天是否集中成片（天气过程）vs 散布（系统退化）。
- **#8 天气分型条件对比**：模型强弱本质对比；月度变差是坏天占比升还是类内退化（核心分解）。
- **#9 ensemble oracle 差距**：动态选模型还有多少空间（ensemble 专属，配 #2）。
- **#11/#12**：训练/测试分布漂移、功率-辐照映射（见 `drift-and-nwp.md`）。

### 输出与结论规范

**PNG 是给人看的交付物，分析闭环走 stats.json，不 Read 图。** 闭环 = 读 stats.json（完整曲线/矩阵/分位数）→ 写结论（这张图说明什么、支持/否定哪个假设）→ 数字异常或缺失就查 `plots.py`/补 stats.json/重画 → 结论沉淀到 `figures/<电站>/<范围>/ANALYSIS.md`。只出图不给结论等于没分析。图仍要"可被人视觉阅读"（关键数值标注在图上、固定配色）供人复核，但**模型不靠读图下结论**。图输出目录 `figures/yalongjiang/<范围>/`（测试站固定雅砻江），命名 `<图号>_<内容>_<范围>.png`。

**结论三道门**（下结论、尤其标"已证实"前必过——完整细则见 `references/analysis-discipline.md`）：

1. **稳健性门槛**：写"A 比 B 好"前必过 Wilcoxon 配对显著 + 剔最差 3 天方向不变（`data_utils.robustness_check`，`passed=True`）。任一不过 → 改写"差异不显著/由个别极端天驱动"。
2. **假设登记**：任何机制结论落 FINDINGS.md 前必引 `references/hypotheses.md` 一条 H-ID；无对应先加"预注册"再验（防事后编故事）。
3. **反驳门**：标"已证实"前逐条排除七类替代解释（事件/样本量/天气占比/漂移/NWP 原料/Chronos 共享上游/口径错），每条给排除证据或标"未排除"并降级为"假设"；在 ANALYSIS.md 留反驳门记录。

**其他纪律**：分组统计先报每组天数（<10 天只描趋势、不进 FINDINGS.md）；分析完直接把关键图 + stats 数字 + 结论展示给用户，不只报路径；顶层 `FINDINGS.md`（工作目录根下）每条结论一行——结论/证据链接/状态（现象/假设/已证实/被推翻）/日期，每次分析同步、开工前先读。

## Stage 4：诊断 Playbook 与结论汇报

两类高频归因问题走固定流程，**详见 `references/playbooks.md`**：

- **Playbook A："为什么 X 月变差了？"**——查台账/事件 → 图#3 定位口径 → 图#4/#7 定位坏天 → 图#8 占比分解（天变坏 vs 模型变弱）→ 图#11/#12 分布漂移 → 过反驳门写结论。
- **Playbook B："为什么模型 A 比 B 好（差）？"**——图#2 同质化 → 图#8 分天气 → 图#4/#6 定位时间 → 图#5 分时效 → 对照 models.md/hypotheses.md 验证机制（想不出机制查 `figure-diagnostics.md`）→ 过门。
- **CONCLUSION.md（面向主管，Stage 4 收尾）**：把 FINDINGS 已证实结论**翻译**成管理层语言，叙述优先、全文表格≤1 张、方法论机器不进正文、金字塔先结论后给建议。写法与模板见 `references/playbooks.md`。

## 背景知识库（references/）

数据只能回答"误差在哪、什么时候变"，"为什么"取决于数据之外的项目事实。这些存在 `references/`，是离线环境唯一的项目知识来源：

| 文档 | 什么时候读 |
|------|-----------|
| `event-log.md` | **任何跨月归因之前必查**——突变点附近有事件先排除再谈模型能力 |
| `models.md` | 模型间对比归因时读（架构/特征/训练窗口） |
| `hypotheses.md` | **任何模型对比或月度归因下结论前必读**——认领假设 ID，先预测后看图 |
| `station.md` | ACC 归一化基准、限电导致的"假高估"、日出日落判断时读 |
| `seasonality.md` | **回答"为什么 X 月变差"必读**——按排查清单形成假设再验 |
| `figure-diagnostics.md` | **Stage 4 从 stats.json 读到某形态、要展开归因时读**——形态→候选机制反向索引，查到的是候选假设非结论 |
| `analysis-discipline.md` | 结论三道门完整细则（稳健性门槛/假设登记/反驳门七条/样本量/台账/运行后回顾） |
| `playbooks.md` | Stage 4 归因（Playbook A/B）与写 CONCLUSION.md 时读 |
| `drift-and-nwp.md` | 分布漂移诊断（run_drift.py）与 NWP 误差分离模块 |

使用纪律：**已填写的字段才可引用；空字段（"待填"）视为未知——宁可写"缺少 XX 背景无法进一步归因"，也不编造。** references/ 是常开收纳位，**每次分析开始前 `ls references/` 扫一遍**，纳入新出现/新填的文档。`models.md` 由用户口述、可能与代码有出入：用户给代码仓库路径要求核验时，走配套技能 **`pv-model-verify`**。

## 常见错误

- ❌ 跨站漂移把 5 训练站 pooled 成一个"平均气候"（掩盖"很像泗洪/白马湖、很不像小壕兔"），逐站要分开看。
- ❌ 把雅砻江当"没见过的高原/异气候站"来解释变差——它在江苏苏州、气候在训练分布内；PSI 低还变差要查站点特异（渔光/限电/口径）而非硬套跨站 OOD。
- ❌ 对滚动窗口的行级 list 直接做分布统计（同一物理点重复计数几百次，必须先 `rebuild_series`）。
- ❌ 未过稳健性门槛（Wilcoxon + 剔坏天）就写"A 比 B 好"。
- ❌ 把限电/停机时段误差算进模型能力（先查 suspect_days 与 event-log.md）。
- ❌ 把真实事件（限电/极端天气）当异常值"修掉"。
- ❌ 只看 stats.json 单点不看整条曲线走势就下判断；只发图不给结论；结论不引 stats 数值。
- ❌ 引用 references/ 的空字段，或编造项目事实。
- ❌ 在样本不足的分组上下定论（如当月突变日只有 3 天）。
- ❌ 取点索引搞混 0/1-index（首跑必对账，之后信"已固化调用"）。
- ❌ 未走反驳门就把结论标"已证实"进 FINDINGS.md（差异不是噪声 ≠ 差异不是别的原因造成的）。
- ❌ 先看图再补机制说法当结论，却不在 `hypotheses.md` 登记预测（事后编故事）。

## 运行后回顾（每次实跑收尾必做）

本技能靠"用得越多越准"——但只有把每次实跑暴露的问题**写回技能文件**才算数：脚本 bug/列名 → 改 `scripts/`；指令歧义/缺步骤 → 改 `SKILL.md`；确认的新项目事实 → 补 `references/`；首跑固化的 `generate_report` 调用 → 填"已固化调用"。**每次改动在 `CHANGELOG.md` 追加一行**（日期 | 改哪节 | 触发反馈 | 为什么）。完整三步见 `references/analysis-discipline.md`。
