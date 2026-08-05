# station_analysis_short.py —— 多站光伏预测分析（一个脚本、两层视图）

给定「宽表 `input` + `dtime×station` 预测表」这套输入，**一次运行同产两层视图**：逐站两线对比曲线（预测 vs 真实，标 RMSE）+ 全场总览仪表盘（定位「谁最离谱」）；必含上线关心的两个 24h 切片（D+1、D+4）+ 历史曲线。可选反事实归因。

> **完全自包含**：不 import 任何 skill / data_utils，只依赖 `pandas / numpy / pyarrow / matplotlib`。单个 `station_analysis_short.py` 拷到任何机器都能跑。
>
> **唯一能讲的因果故事**只有一个：全场总览 B 散点（GHI 输入差 vs 功率差）。要更强的因果证据（把误差分解成「模型的锅」vs「GHI 输入的锅」），用 `--counterfactual`（需你自己的 FastAPI 预测服务）。

## 数据契约（两张表）

| 表 | 内容 | 关键列 |
|----|------|--------|
| `input`（宽表） | 每行一个 (站, 起报窗口)，列为 list | `station`、`timestamp_win`、`observe_power_future`（功率真值 list）、`GHI_SOLARGIS_predict`/`GHI_real_future`（GHI 预测/真值 list）等 |
| `predict` | 各站功率预测 | `dtime` 列 + 每站一列（`predict_power_<站>`，回退裸站名），单元格为标量 |

- 列名可改：`--station-col` / `--win-col` / `--power-col` / `--dtime-col` / `--pred-col-template`。
- **特征对** = `预测列:真值列[:label]`，默认 `GHI_SOLARGIS_predict:GHI_real_future:GHI`；`--feature-pairs` 可加更多（`GHI_real_future` 是这些预测量的公共真值 label）。
- **RMSE** = 对齐后公共时点上 `sqrt(mean((pred−true)²))`（功率与特征同一定义）。

## 视图

### ① 逐站细看（`<切片目录>/stations/`）
每站若干张图：
- **Power** —— 预测功率（predict 表 `dtime×站列`）vs 真实功率（input 的 `observe_power_future`）两线对比，标 RMSE。
- **特征** —— 预测 vs 真值两线对比（默认 `GHI`），二者都在 input 宽表 list 列里。
- **散点** —— `station_<站>_scatter.png`：真值-预测散点 + OLS 拟合 + 十分位分箱均值，回答「系统性偏高/低？高值被压缩？」（斜率<1 且顶部 20% 负偏 = 压缩嫌疑）；文本框附 Theil `u_bias/u_var/u_cov` 份额。

### ② 全场总览（`<切片目录>/`）
单张 `fleet_overview.png`（2×2 仪表盘）+ `theil_decomposition.png`：
- **A1/A2 排行榜** —— 各站 **nRMSE** 降序（worst 在顶），中位线 + 离群站红标（功率 + GHI）。
- **B 散点** —— GHI-nRMSE vs 功率-nRMSE，一站一点：功率差落在右上（GHI 输入差可解释）还是左上（GHI 好但功率仍差 = 模型/其它问题）。
- **C 热力图** —— 时刻 × 场站的功率 nRMSE，看谁在哪个钟点坏（正午 vs 日出日落爬坡）。
- **Theil 分解** —— 每站功率 MSE 的 100% 堆叠份额：`u_bias`（水平偏移）/ `u_var`（幅度失配）/ `u_cov`（形状-时序失配），主导份额 ≥50% 指向先修哪里。

**为什么归一化（关键）**：绝对 RMSE 被电站规模支配（大站天然大，排名无意义）。`nRMSE = RMSE / 该站峰值功率`（自包含代理容量；有真实装机用 `--capacity` 更准），单位 %。「离谱」= nRMSE 排名靠前 **且** 异常高于全场（> 中位数 + `--mad-k`×MAD，默认 3，红标）。只用 `observe_power_future`（功率真值）与 `GHI_real_future`（GHI 真值）两种 label——温度等无真值列评不了，总览不涉及。

### ③ 反事实（`--counterfactual` 门控，可选，需 FastAPI 预测服务）
oracle GHI swap：把 GHI 预测列换成 GHI 真值经统一模型重预测，把每站误差**因果地**分解为 `nRMSE基线 = 模型底线（GHI 完美仍剩）+ GHI 归因（换真值即消失）`——B 散点的相关性暗示由此升级成证据。

**窗口守卫**：某站某窗口内真值列全空 → 该站该窗口记 `no_overlap` 状态，**零 API 调用**（不发往预测服务）。整站全窗口真值都空 → 整站跳过、不调用。每站最多 2 次调用：**基线复现**（原特征原样发，输出与 predict 表核对 = 复现闸，差超 `--cf-check-tol`% 告警）+ **换真值**。逐站算完立即落盘 `counterfactual_results.csv`，中断重跑自动跳过已完成站（`--cf-force` 重算）。**首跑必 `--cf-dry-run`**：零 HTTP，打印调用计划 + 首站 payload 骨架，确认契约后再实跑。**跑哪些站**：默认全部；`--cf-stations st1,st2` 指定显式子集；`--cf-worst N` 只跑功率 nRMSE 最差 N 站（复用本切片 `fleet_ranking.csv`，D+1/D+4 各按自己的排名选最差 N 站；无 ranking 文件或 `--no-fleet` 时告警回退跑全部）。两者同时给时 `--cf-stations` 优先、`--cf-worst` 忽略。

产出 `counterfactual_overview.png`：左图堆叠条（灰 = 模型的锅、橙 = GHI 输入的锅、蓝 = 换真值反而差 = **共适应警示**，Δ<−0.1 个百分点才标），右图各站「GHI 可解释比例 %」。

API 契约：`POST {"data":[{行dict}]}`（字段 = parquet 列名、list 原样、不带站名与真值 label 列）；响应 = `{"status":..., "predictions":[{"timestamp_win":..., "ensemble":[192值]}, ...]}` —— 逐窗返回、只取 `ensemble`，按响应自带 `timestamp_win` 摊平去重，返回窗数 ≠ 发送行数 = 对齐闸拦下只跳该站；也兼容扁平 list 响应（与 predict 表该站列按 dtime 逐点对应）。两条诚实注意（已写进图注）：① Δ≈0 ≠ GHI 预报没问题（模型可能不敏感或已共适应）；② 「模型底线」含其它无真值输入（温度等）的误差，是模型自身误差的上界。

### ④ 短期视图（D+1、D+4、历史）
上线关心的两个 24h 切片：**D+1**（次日）与 **D+4**（第 4 天），各出一整套产物（逐站图 + 总览 + CSV，`--worst-only` 等开关照常在每个切片内独立生效）。起报日 `D` 用 `--date YYYY-MM-DD` 指定（缺省自动取 input 表最早 `timestamp_win` 的日期，终端播报 `using D = ...`）。切片按绝对时刻 `[D+1 00:00, +24h)` / `[D+4 00:00, +24h)` 各取 24h（15min 步长即 96 点），逐站 RMSE 只在切片内计算。

**目录结构**：全部产物落在 `<out>/<YYYYMMDD>/` 下，`D+1`/`D+4`/`history` 三个子目录并列。

### ⑤ 历史曲线（`history/`）
每站两张单线图（无真值对照、不算指标）：历史（过去实测）列 `observe_power` 与 `GHI_SOLARGIS` 的**最近 2 天**曲线。这两列是预测列 `observe_power_future` / `GHI_SOLARGIS_predict` 的历史对照，其 list **反向**排列——最后一个元素落在起报时间 `T`（`list[-1] → T`），逐元素往前退 15min，故 7 天历史里只画 `[T−2天, T]` 这段，避免太长糊成一团。落 `<out>/<YYYYMMDD>/history/stations/station_<站>_observe_power.png` 与 `..._GHI_SOLARGIS.png`；某站某列缺失/窗口内空 → 只跳那一张并告警，终端汇总 `[history] observe_power: N plotted, M skipped`。`--no-plots` / `--no-station-plots` 时整段跳过；`--worst-only` 对 history 不生效（无 nRMSE 可排，画全部站）。

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
  [--info-csv info.csv]                                        # 每站 GCCAPCITY（按 station 列 join）→ 南网 nanwang_official 指标
  [--ghi-pred GHI_SOLARGIS_predict --ghi-true GHI_real_future] # 总览 GHI 排名/散点用列
  [--station-col station --win-col timestamp_win --power-col observe_power_future --dtime-col dtime]
  [--pred-col-template "predict_power_{station}"]
  [--no-plots] [--no-station-plots] [--no-fleet] [--worst-only 5]
  [--counterfactual --api-url http://... [--cf-dry-run]]       # 反事实（先 --cf-dry-run 确认 payload！）
  [--cf-stations st1,st2] [--cf-worst N] [--cf-force]           # 子集（显式列表 / 最差 N 站）/ 忽略续跑记录全部重算
  [--cf-swap "GHI_SOLARGIS_predict:GHI_real_future"]            # 可多对 = 联合替换
  [--cf-exclude-cols "observe_power_future,GHI_real_future"]    # 不发给 API 的 label 列
  [--cf-timeout 120] [--cf-retries 1] [--cf-check-tol 1.0] [--cf-curves]
  [--date YYYY-MM-DD]                 # 起报日（缺省自动取 timestamp_win 最早日期）；<out>/<YYYYMMDD>/ 下 D+1、D+4 各一套 + history
```

## 产物

**常规产物**（`<out>/<YYYYMMDD>/D+1/` 与 `D+4/` 下各一份）：
- 逐站 `stations/station_<站>_Power.png` / `station_<站>_<特征>.png` / `station_<站>_scatter.png`（图宽随点数自适应，标题含站名 + 起始时间戳）。
- `station_power_rmse.csv` + `station_feature_rmse.csv`。
- 全场 `fleet_overview.png` + `theil_decomposition.png` + `fleet_ranking.csv`（每站 nRMSE / bias / Theil 份额 / 斜率 / r² / 离群标记 / 排名；给 `--info-csv` 时再加 `GCCAPCITY` + `nanwang_official_power` 两列）。
- 反事实 `counterfactual_overview.png` + `counterfactual_results.csv`（每站 status / nrmse_base / nrmse_cf / delta / frac_explained / 复现闸偏差 / coadapt；给 `--info-csv` 时再加 `GCCAPCITY` + `nanwang_official_base` + `nanwang_official_cf`）+ 可选逐站三线图 `station_<站>_counterfactual.png`。

> **南网官方口径 `nanwang_official`**（需 `--info-csv` 提供各站 `GCCAPCITY`）：准确率 = `(1 − sqrt( mean( ((p_real − p_pred) / max(p_real, 0.2·GCCAPCITY))² ) )) × 100%`。分母 `0.2·GCCAPCITY` 下限使夜间/近零点良态，故**该指标始终用全窗所有点（含夜间，不受 `--drop-night` 影响）**。`GCCAPCITY` 只用于此指标，不改变既有 nRMSE 的归一化口径。info.csv 缺某站 → 该站留空并告警。

**短期视图**：常规产物（逐站图、全场总览、CSV 等）各出一份到 `<out>/<YYYYMMDD>/D+1/` 与 `<out>/<YYYYMMDD>/D+4/`（结构不变，每份只覆盖对应 24h 切片），外加 `<out>/<YYYYMMDD>/history/stations/` 的两日历史曲线。

## 超短期：station_analysis_ultra_short.py

自包含，同样只依赖 pandas / numpy / pyarrow / matplotlib。

```bash
python3 station_analysis_ultra_short.py --input-dir <根目录> --predict-dir <预测目录> \
  --date 20260723 --out-dir out_us
```

**预测侧（--predict-dir）**：扁平目录，每 15min 一个 起报、每 起报 一个 parquet，文件名含 `YYYYMMDDHHMM`（按该 token glob，容忍文件名拼写漂移；同 token 多文件报错退出）。表结构 = `dtime` 列 + 每站一列（`--pred-col-template`，默认 `predict_power_{station}`）；行自 起报+15min 起，只取前 16 点（lead 1..16 = 15min..4h）。

**真值侧（--input-dir）**：Hive 分区 `date=YYYY-MM-DD/time=HH:MM/` 下唯一 parquet（schema 同短期 input，list 列长 192）；只取 `observe_power_future` / `GHI_real_future` / `GHI_SOLARGIS_predict` 各 list 的第 0 个元素（= 起报+15min 处的值）。

**重建**：目标网格 = D 00:00..23:45（96 点）。目标 t 的 16 个预测来自 起报 t-4h..t-15min；线 `p_j` = 恒定 lead(17-j)：**p1 = 4h 前（最旧），p16 = 15min 前（最新）**。t=00:00 的真值来自 `date=D-1/time=23:45`；p1 需要 `D-1 20:00` 起的预测 parquet。缺 起报 → 告警 + NaN 缺口，不中断。

**产物**（`<out>/<YYYYMMDD>/`）：
- `stations/station_<站>_Power.png` — 17 线（真值黑粗 + p1..p16 由浅到深）
- `stations/station_<站>_GHI.png` — 2 线（lead-1 GHI 预测 vs 真值；两者都来自 input 侧 = 特征质量图）
- `station_power_rmse.csv` — 每站 16 lead 合并 RMSE（降序 = 排名）
- `station_feature_rmse.csv` — 每站 lead-1 GHI RMSE

无散点 / Theil / 舰队总览 / 反事实 / history。

**南网超短期准确率**（可选，给 `--info-csv`——两列 `station,GCCAPCITY`，可复用短期同一文件——即开启）：
`Acc = (1 − mean_t mean_i |P_real(t) − p_i(t)| / max(P_real(t), 0.2·GCCAPCITY)) × 100%`，每时刻对 16 条
lead 取绝对误差均值、再对全天 96 时刻取均值。恒用全部目标点（含夜间，`0.2·GCCAPCITY` 分母下限保证良态，
不受 `--drop-night` 影响）；缺 (lead,时刻) 项按可用项平均。**仅逐站打印到日志（附 fleet mean），不写入任何
CSV**；info-csv 缺某站 → 该站告警跳过。
