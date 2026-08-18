# station_analysis_short.py —— 多站光伏预测分析（一个脚本、两层视图）

给定「宽表 `input` + `dtime×station` 预测表」这套输入，**一次运行同产两层视图**：逐站两线对比曲线（预测 vs 真实，标 RMSE）+ 全场总览仪表盘（定位「谁最离谱」）；必含上线关心的两个 24h 切片（D+1、D+4）+ 历史曲线。可选反事实归因。

> **完全自包含**：不 import 任何 skill / data_utils，只依赖 `pandas / numpy / pyarrow / matplotlib`。单个 `station_analysis_short.py` 拷到任何机器都能跑。
>
> **唯一能讲的因果故事**只有一个：全场总览 B 散点（GHI 输入差 vs 功率差）。要更强的因果证据（把误差分解成「模型的锅」vs「GHI 输入的锅」），用 `--counterfactual`（需本地 `inference.py` 与 checkpoints，不走 HTTP）。

## 数据契约（两张表）

| 表 | 内容 | 关键列 |
|----|------|--------|
| `input`（宽表） | 每行一个 (站, 起报窗口)，列为 list | `station`、`timestamp_win`、`observe_power_future`（功率真值 list）、`GHI_SOLARGIS_predict`/`GHI_real_future`（GHI 预测/真值 list）等 |
| `predict` | 各站功率预测 | `dtime` 列 + 每站一列（`predict_power_<站>`，回退裸站名），单元格为标量 |

- 列名可改：`--station-col` / `--win-col` / `--power-col` / `--dtime-col` / `--pred-col-template`。
- **特征对** = `预测列:真值列[:label]`，默认 `GHI_SOLARGIS_predict:GHI_real_future:GHI`；`--feature-pairs` 可加更多（`GHI_real_future` 是这些预测量的公共真值 label）。
- **RMSE** = 对齐后公共时点上 `sqrt(mean((pred−true)²))`（功率与特征同一定义）。

## 视图

### ① 逐站细看（`<切片目录>/station_<站>.png`，每站一张 2×2 组合图）
四个子图（尺寸 32×12，每个子图约等于旧版单图大小）：
- **左上** —— 历史 `GHI_SOLARGIS` 单线曲线（全部历史点，不截窗、不去夜间）。
- **左下** —— 历史 `observe_power` 单线曲线（同上）。
- **右上** —— 本切片（D+1 或 D+4）GHI 预测 vs 真值两线对比，标 RMSE。
- **右下** —— 本切片功率预测（predict 表 `dtime×站列`）vs 真实功率（`observe_power_future`）两线对比，标 RMSE。

某面板数据缺失 → 该面板显示 `no data`，其余照出。散点校准量（slope / r² / 高值压缩）不再单独出图，仍写入 `fleet_ranking.csv`。

### ② 全场总览（`<切片目录>/`）
单张 `fleet_overview.png`（2×2 仪表盘）+ `theil_decomposition.png`：
- **A1/A2 排行榜** —— 各站 **nRMSE** 降序（worst 在顶），中位线 + 离群站红标（功率 + GHI）。
- **B 散点** —— GHI-nRMSE vs 功率-nRMSE，一站一点：功率差落在右上（GHI 输入差可解释）还是左上（GHI 好但功率仍差 = 模型/其它问题）。
- **C 热力图** —— 时刻 × 场站的功率 nRMSE，看谁在哪个钟点坏（正午 vs 日出日落爬坡）。
- **Theil 分解** —— 每站功率 MSE 的 100% 堆叠份额：`u_bias`（水平偏移）/ `u_var`（幅度失配）/ `u_cov`（形状-时序失配），主导份额 ≥50% 指向先修哪里。

**为什么归一化（关键）**：绝对 RMSE 被电站规模支配（大站天然大，排名无意义）。`nRMSE = RMSE / 该站峰值功率`（自包含代理容量；有真实装机用 `--capacity` 更准），单位 %。「离谱」= nRMSE 排名靠前 **且** 异常高于全场（> 中位数 + `--mad-k`×MAD，默认 3，红标）。只用 `observe_power_future`（功率真值）与 `GHI_real_future`（GHI 真值）两种 label——温度等无真值列评不了，总览不涉及。

### ③ 反事实（`--counterfactual` 门控，可选，需**本地 inference.py**）
oracle GHI swap：把 GHI 预测列换成 GHI 真值，经**本地 `multi_station_inference` 重预测**，把每站误差**因果地**分解为 `nRMSE基线 = 模型底线（GHI 完美仍剩）+ GHI 归因（换真值即消失）`——B 散点的相关性暗示由此升级成证据。不走任何 HTTP。

**这一档只能在有模型栈的机器上跑**（`inference.py` + 其 `Base`/`utils` 依赖 + checkpoints）；脚本其余功能在任何机器照常。

必给参数：`--checkpoints-dir`、`--config`（yaml 路径），二者原样透传给 `multi_station_inference`；`--inference-dir` 指向 `inference.py` 所在目录（**插在 `sys.path` 最前**，否则会被脚本自己目录下的同名文件遮蔽）；`--forecasting-type` 默认 `short`。

**`--cf-input`（推理专用输入表）**：喂给模型的那张 parquet，需含 `station` / `timestamp_win` + 模型全部特征 + `--cf-swap` 的预测与真值两列；**缺省回退用 `--input`**（分析输入本身即推理就绪时，如 `mock_input.parquet` 那 46 列）。分析表有、推理表没有的站 → 告警 + 该站 `cf_status=missing`，其它站照常。

**调用结构**：按 `timestamp_win` 分组，**每窗一次调用、该窗全部站一起送**（`multi_station_inference` 断言 station 唯一 + 窗口单一，正是这个形状）。跑**两趟**：基线（原特征）+ 换真值，故总调用数 = 窗口数 × 2。一窗 480 点的输出横跨 5 天，D+1 与 D+4 共用同一份结果，**推理只在切片循环之前跑一次**。结果落盘 `<out>/<YYYYMMDD>/cf_base_pred.parquet` 与 `cf_swap_pred.parquet`，重跑直接命中缓存（零调用），`--cf-force` 重算。

**行守卫**：swap 两列为空、或真值列长度 ≠ 预测列长度的行，推理前就剔除（喂 None 会让模型崩、长度不等会悄悄改变预测长度）；该站因此记 `cf_status=missing`。窗口内无真值功率 → `cf_status=no_overlap`。

**三道告警**：① 若 `utils.get_past_future_cols` 可导入（即在模型机上），swap 列不在模型 future/extra 特征表里 → 告警「换了也不会变」；② 基线与换真值输出**逐点全等** → 告警模型对该列不敏感、下面的 Δ 无意义；③ 本地基线 vs `--predict` 表 nRMSE 超 `--cf-check-tol`%（默认 1）→ 告警版本/配置可能不一致，并把该站记 `cf_status=baseline_mismatch`（分解仍用本地基线，故自洽）。

**产出**：反事实是**右下功率面板的第三条绿线**（`counterfactual (GHI->truth)`，标题补 `cf RMSE=`），`--cf-show-local-base` 再加一条本地基线灰虚线。指标并入既有 CSV（不再有 `counterfactual_results.csv`）：`fleet_ranking.csv` / `station_power_rmse.csv` 增 `cf_status`、`power_rmse_cf`、`power_nrmse_cf`、`power_nrmse_localbase`、`delta_nrmse`、`frac_explained`、`coadapt`、`base_vs_parquet_pct`，配 `--info-csv` 时另增 `nanwang_official_power_cf`（只出官方口径，不带 factor 扫描）。**Δ 一律用本地基线减本地反事实**，两侧同一批 checkpoints、同一批时点（`truth ∩ base ∩ cf` 三方交集），不掺 predict 表的版本差。

仍产 `counterfactual_overview.png`：左图堆叠条（灰 = 模型的锅、橙 = GHI 输入的锅、蓝 = 换真值反而差 = **共适应警示**，Δ<−0.1 个百分点才标），右图各站「GHI 可解释比例 %」。两条诚实注意（已写进图注）：① Δ≈0 ≠ GHI 预报没问题（模型可能不敏感或已共适应）；② 「模型底线」含其它无真值输入（温度等）的误差，是模型自身误差的上界。

```bash
python3 station_analysis_short.py --input input.parquet --predict predict.parquet --out-dir out \
  --counterfactual --cf-input infer_input.parquet \
  --inference-dir /path/to/model --checkpoints-dir /path/to/checkpoints --config chunk_config.yaml
```

### ④ 短期视图（D+1、D+4、历史）
上线关心的两个 24h 切片：**D+1**（次日）与 **D+4**（第 4 天），各出一整套产物（逐站图 + 总览 + CSV，`--worst-only` 等开关照常在每个切片内独立生效）。起报日 `D` 用 `--date YYYY-MM-DD` 指定（缺省自动取 input 表最早 `timestamp_win` 的日期，终端播报 `using D = ...`）。切片按绝对时刻 `[D+1 00:00, +24h)` / `[D+4 00:00, +24h)` 各取 24h（15min 步长即 96 点），逐站 RMSE 只在切片内计算。

**目录结构**：全部产物落在 `<out>/<YYYYMMDD>/` 下，只有 `D+1`/`D+4` 两个子目录（历史曲线并入每站组合图左列，不再有独立 `history/` 目录）。

### ⑤ 历史面板（组合图左列）
历史（过去实测）列 `observe_power` 与 `GHI_SOLARGIS` 是预测列 `observe_power_future` / `GHI_SOLARGIS_predict` 的历史对照，其 list **反向**排列——最后一个元素落在起报时间 `T`（`list[-1] → T`），逐元素往前退 15min。组合图左列画**全部**历史点（不截天数窗、不去夜间）；某站某列缺失/为空 → 该面板 `no data` 并告警。

## 时间对齐

- **预测/未来 list**：input 某行 `timestamp_win=T`，任意 list 列（`observe_power_future` / `*_predict` / `GHI_real_future`）第 k 个元素时间 = `T+15min×(k+1)`（首元素 = T+15min）。同站各窗摊平、按绝对时间 groupby 去重成连续序列；power 的预测再与 predict 表 `dtime` 对齐。
- **历史 list**（`observe_power` / `GHI_SOLARGIS`）：反向，第 i 个元素（长度 L）时间 = `T − 15min×(L−1−i)`，即 `list[-1] → T`（起报时间）。

## 鲁棒

每张图/每项指标独立成败——某列缺失、或**某站**该列全空 → 只跳那一项并告警，power 与其它站/其它特征/总览照常输出，绝不整体报错。

## 用法

```bash
python3 station_analysis_short.py --input input.parquet --predict predict.parquet --out-dir out \
  [--drop-night --night-end-hour 5]    # 去掉每天 00:00–05:00（RMSE 也按去掉后算）
  [--tick-hours 1] [--step-min 15]     # x 轴刻度间隔 / list 步长
  [--feature-pairs "GHI_SOLARGIS_predict:GHI_real_future:GHI,ssrd_pos_1_predict:GHI_real_future:ssrd1"]
  [--top-n 30] [--mad-k 3] [--capacity "st1:500,st2:5"]        # 总览：榜单条数 / 离群阈 / 装机
  [--info-csv info.csv]  # 或 --info；每站 GCCAPCITY/GCCAPACITY → 南网 nanwang_official 指标 + city 列。
                         # join 列：info.csv 里有 --station-col 就用它，否则自动探测（值匹配最多的列，如 plantid）
  [--ghi-pred GHI_SOLARGIS_predict --ghi-true GHI_real_future] # 总览 GHI 排名/散点用列
  [--station-col station --win-col timestamp_win --power-col observe_power_future --dtime-col dtime]
  [--pred-col-template "predict_power_{station}"]
  [--no-plots] [--no-station-plots] [--no-fleet] [--worst-only 5]
  [--counterfactual --checkpoints-dir DIR --config cfg.yaml]    # 反事实：本地 inference.py，二者必给
  [--inference-dir DIR] [--forecasting-type short]              # inference.py 所在目录（插 sys.path 最前）
  [--cf-input infer_input.parquet]                              # 推理专用输入表，缺省回退 --input
  [--cf-swap "GHI_SOLARGIS_predict:GHI_real_future"]            # 可多对 = 联合替换
  [--cf-force] [--cf-check-tol 1.0] [--cf-show-local-base]      # 忽略缓存重算 / 复现闸阈值 / 加画本地基线虚线
  [--date YYYY-MM-DD]                 # 起报日（缺省自动取 timestamp_win 最早日期）；<out>/<YYYYMMDD>/ 下 D+1、D+4 各一套 + history
```

## 产物

**常规产物**（`<out>/<YYYYMMDD>/D+1/` 与 `D+4/` 下各一份）：
- 逐站 `station_<站>.png` —— 2×2 组合图（左列历史 GHI/功率全量点，右列本切片 GHI/功率预测对真值，标 RMSE）。
- `station_power_rmse.csv` + `station_feature_rmse.csv`。
- 全场 `fleet_overview.png` + `theil_decomposition.png` + `fleet_ranking.csv`（每站 nRMSE / bias / Theil 份额 / 斜率 / r² / 离群标记 / 排名；给 `--info-csv` 时再加 `city` + `GCCAPCITY` + `nanwang_official_power` 及其 factor 扫描列，见下）。
- 反事实（`--counterfactual`）：`counterfactual_overview.png`，加上右下功率面板的第三条绿线；指标并入 `fleet_ranking.csv` / `station_power_rmse.csv`（`cf_status` / `power_rmse_cf` / `power_nrmse_cf` / `power_nrmse_localbase` / `delta_nrmse` / `frac_explained` / `coadapt` / `base_vs_parquet_pct`；给 `--info-csv` 时再加 `nanwang_official_power_cf`）。推理结果缓存在 `<out>/<YYYYMMDD>/cf_base_pred.parquet` 与 `cf_swap_pred.parquet`。

> **南网官方口径 `nanwang_official`**（需 `--info-csv`/`--info` 提供各站 `GCCAPCITY` 或 `GCCAPACITY`）：准确率 = `(1 − sqrt( mean( ((p_real − p_pred) / max(p_real, 0.2·GCCAPCITY))² ) )) × 100%`。分母 `0.2·GCCAPCITY` 下限使夜间/近零点良态，故**该指标始终用全窗所有点（含夜间，不受 `--drop-night` 影响）**，D+1/D+4 各按自己的 24h 窗独立计算。`GCCAPCITY` 只用于此指标，不改变既有 nRMSE 的归一化口径。info.csv 缺某站 → 该站留空并告警。

> **南网 factor 灵敏度扫描**（仅 `fleet_ranking.csv`，随 `nanwang_official_power` 一同出现）：把该站该窗的预测序列**每一个点**乘以同一个 factor 后，用完全相同的南网口径重算准确率，得到 5 个附加列。列顺序为 `nanwang_official_power_x1.4` / `_x1.2` / `nanwang_official_power`（即 factor 1.0，官方口径本身）/ `_x0.8` / `_x0.6` / `_x0.4`，官方口径居中，便于左右对读上调/下调的收益。**不做任何截断**：factor > 1 时预测可以超过 `GCCAPCITY`。逐窗独立缩放（D+1/D+4 各按自己的窗），点集与官方口径一致（含夜间）。缺 `GCCAPCITY` 的站，这 5 列与官方列一并留空。`station_power_rmse.csv` 不带 factor 列，反事实侧也只出 `nanwang_official_power_cf` 官方口径一列。图不受影响。

**短期视图**：常规产物（逐站组合图、全场总览、CSV 等）各出一份到 `<out>/<YYYYMMDD>/D+1/` 与 `<out>/<YYYYMMDD>/D+4/`（每份只覆盖对应 24h 切片）。

## 超短期：station_analysis_ultra_short.py

自包含，同样只依赖 pandas / numpy / pyarrow / matplotlib。

```bash
python3 station_analysis_ultra_short.py --input-dir <根目录> --predict-dir <预测目录> \
  --date 20260723 --out-dir out_us
```

**预测侧（--predict-dir）**：扁平目录，每 15min 一个 起报、每 起报 一个 parquet，文件名含 `YYYYMMDDHHMM`（按该 token glob，容忍文件名拼写漂移；同 token 多文件报错退出）。表结构 = `dtime` 列 + 每站一列（`--pred-col-template`，默认 `predict_power_{station}`）；行自 起报+15min 起，只取前 16 点（lead 1..16 = 15min..4h）。

**真值侧（--input-dir）**：Hive 分区 `date=YYYY-MM-DD/time=HH:MM/` 下唯一 parquet（schema 同短期 input，list 列）；取 `observe_power_future` / `GHI_real_future` / `GHI_SOLARGIS_predict` 各 list 的第 0 个元素（= 起报+15min 处的值）。

**历史侧**：历史列 `observe_power` / `GHI_SOLARGIS` 走另一条路——只读 `date=D` 下**最早**一个可用起报目录（当天没有 `time=00:00` 就自动取实际存在的第一个，如 `time=02:15`；日志播报 `[history] 起报 ... 用于左列两个面板`），把该行的**整条 list 反向展开**（`list[-1]` 落在该起报时刻，往前每格 15min），672 长即画出往前 7 天的历史曲线。不逐目录取点（相邻起报的历史窗高度重叠，取整条更快且信息完整）。整天无可用目录或表里无历史列 → 告警 + 两个历史面板 `no data`；`--no-plots` 时完全不读历史。

**重建**：目标网格 = D 00:00..23:45（96 点）。目标 t 的 16 个预测来自 起报 t-4h..t-15min；线 `p_j` = 恒定 lead(17-j)：**p1 = 4h 前（最旧），p16 = 15min 前（最新）**。t=00:00 的真值来自 `date=D-1/time=23:45`；p1 需要 `D-1 20:00` 起的预测 parquet。缺 起报 → 告警 + NaN 缺口，不中断。

**产物**（`<out>/<YYYYMMDD>/`）：
- `stations/station_<站>.png` — 每站一张 2×2 组合图（布局同短期）：**左上** 历史 `GHI_SOLARGIS` 单线、**左下** 历史 `observe_power` 单线（当日最早起报的整条 list 反向展开 = 往前 7 天全部点，不去夜间，标题带时间范围与点数）；**右上** lead-1 GHI 预测 vs 真值 2 线（标 RMSE，两者都来自 input 侧 = 特征质量图）；**右下** 17 线（真值黑粗 + p1..p16 由浅到深，标合并 RMSE）。左列跨 7 天、右列只当日 96 点，两列各用各的 x 轴（刻度间隔按跨度自动稀疏）。某面板全空 → `no data` + 告警，其余照出。
- `station_power_rmse.csv` — 每站 16 lead 合并 RMSE（降序 = 排名）
- `station_feature_rmse.csv` — 每站 lead-1 GHI RMSE

无散点 / Theil / 舰队总览 / 反事实。

**南网超短期准确率**（可选，给 `--info-csv`/`--info` 即开启——每站 `GCCAPCITY`/`GCCAPACITY`，join 列同短期规则（有 `--station-col` 列用它，否则按值自动探测），可复用短期同一 info.csv；info.csv 有 `city` 列时 `station_power_rmse.csv` 加 `city` 列）：
`Acc = (1 − mean_t mean_i |P_real(t) − p_i(t)| / max(P_real(t), 0.2·GCCAPCITY)) × 100%`，每时刻对 16 条
lead 取绝对误差均值、再对全天 96 时刻取均值。恒用全部目标点（含夜间，`0.2·GCCAPCITY` 分母下限保证良态，
不受 `--drop-night` 影响）；缺 (lead,时刻) 项按可用项平均。**仅逐站打印到日志（附 fleet mean），不写入任何
CSV**；info-csv 缺某站 → 该站告警跳过。
