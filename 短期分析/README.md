# station_analysis_short.py —— 多站光伏预测分析（一个脚本、两层视图）

给定「宽表 `input` + `dtime×station` 预测表」这套输入，**一次运行同产两层视图**：逐站两线对比曲线（预测 vs 真实，标 RMSE）+ 全场总览仪表盘（定位「谁最离谱」）；必含上线关心的两个 24h 切片（D+1、D+4）+ 历史曲线。可选反事实归因。

> **完全自包含**：不 import 任何 skill / data_utils，只依赖 `pandas / numpy / pyarrow / matplotlib`。把 `station_analysis_short.py` 连同同级的 `pvcore/` 一起拷到任何机器都能跑（见文末「代码结构」）。
>
> **唯一能讲的因果故事**只有一个：全场总览 B 散点（GHI 输入差 vs 功率差）。要更强的因果证据（把误差分解成「模型的锅」vs「GHI 输入的锅」），用 `--counterfactual`（需本地 `inference.py` 与 checkpoints，不走 HTTP）。

## 数据契约（两张表）

| 表 | 内容 | 关键列 |
|----|------|--------|
| `input`（宽表） | 每行一个 (站, 起报窗口)，列为 list | `station`、`timestamp_win`、`observe_power_future`（功率真值 list）、`GHI_SOLARGIS_predict`/`GHI_real_future`（GHI 预测/真值 list）等 |
| `predict` | 各站功率预测 | `dtime` 列 + 每站一列（`predict_power_<站>`，回退裸站名），单元格为标量。**开 `--counterfactual` 时可省略**，由本地基线推理顶上 |

- 列名可改：`--station-col` / `--win-col` / `--power-col` / `--dtime-col` / `--pred-col-template`。
- **特征对** = `预测列:真值列[:label]`，默认 `GHI_SOLARGIS_predict:GHI_real_future:GHI`；`--feature-pairs` 可加更多（`GHI_real_future` 是这些预测量的公共真值 label）。
- **RMSE** = 对齐后公共时点上 `sqrt(mean((pred−true)²))`（功率与特征同一定义）。

### mock 数据（`make_mocks.py`）

`python make_mocks.py` 就地生成 `mock_input.parquet` + `mock_predict.parquet` + `mock_info.csv`，
20 个站、起报日 `2026-07-15`、起报时刻 10:00，列名与列序照抄真实表（46 列）。跑一趟全链路：

```bash
python station_analysis_short.py --input mock_input.parquet --predict mock_predict.parquet \
  --info-csv mock_info.csv --out-dir /tmp/mockout
```

- **`station` 全表唯一、`timestamp_win` 全表只有一个值** —— 直接对上 `inference.py` 第 15、16 行的两条
  assert，所以这份 input 不用切片就能喂 `multi_station_inference`。一个起报窗的 480 点横跨 5 天，
  D+1 与 D+4 两个分析窗都从这一窗里取，单窗足够。
- 数值不是白噪声：GHI 由各站自己的经纬度算 `GHI_cs` 再乘平滑云况 `K_t`，功率经温度降额并按装机截断。
  每站带一个固定的 GHI 预报乘性偏差（`make_mocks.py` 里的 `STATIONS` 表，0.80~1.30），
  `--cf-kt-scale` 应当能逐站找回来 —— 拿来验 K_t 扫描正好。
- `mock_info.csv` 带 `GCCAPCITY` / `LATITUDE` / `LONGITUDE` / `city`，南网口径与 K_t 扫描都够用。
- `--out-dir` / `--date` / `--stations` / `--seed` 可调，默认写回本目录（会覆盖现有 mock）。

## 视图

### ① 逐站细看（`<切片目录>/station_<站>.png`，每站一张 2×2 组合图）
四个子图（尺寸 32×12，每个子图约等于旧版单图大小）：
- **左上** —— 历史 `GHI_SOLARGIS` 单线曲线（全部历史点，不截窗、不去夜间）。
- **左下** —— 历史 `observe_power` 曲线（同上）。给了 `--hist-root` 时再叠一条橙色虚线 = 南网 IN 侧**原始**可用功率（主表 `observe_power` 是调整后的），两条线裁到同一起止。
- **右上** —— 本切片（D+1 或 D+4）GHI 预测 vs 真值两线对比，标 RMSE。
- **右下** —— 本切片功率预测（predict 表 `dtime×站列`）vs 真实功率（`observe_power_future`）两线对比，标 RMSE。

某面板数据缺失 → 该面板显示 `no data`，其余照出。

### ② 全场总览（`<切片目录>/`）
单张 `fleet_overview.png`（2×2 仪表盘）：
- **A1/A2 排行榜** —— 各站 **nRMSE** 降序（worst 在顶），中位线 + 离群站红标（功率 + GHI）。
- **B 散点** —— GHI-nRMSE vs 功率-nRMSE，一站一点：功率差落在右上（GHI 输入差可解释）还是左上（GHI 好但功率仍差 = 模型/其它问题）。
- **C 热力图** —— 时刻 × 场站的功率 nRMSE，看谁在哪个钟点坏（正午 vs 日出日落爬坡）。

**为什么归一化（关键）**：绝对 RMSE 被电站规模支配（大站天然大，排名无意义）。`nRMSE = RMSE / 该站峰值功率`（自包含代理容量；有真实装机用 `--capacity` 更准），单位 %。「离谱」= nRMSE 排名靠前 **且** 异常高于全场（> 中位数 + `--mad-k`×MAD，默认 3，红标）。只用 `observe_power_future`（功率真值）与 `GHI_real_future`（GHI 真值）两种 label——温度等无真值列评不了，总览不涉及。

### ③ 反事实（`--counterfactual` 门控，可选，需**本地 inference.py**）
oracle GHI swap：把 GHI 预测列换成 GHI 真值，经**本地 `multi_station_inference` 重预测**，把每站误差**因果地**分解为 `nRMSE基线 = 模型底线（GHI 完美仍剩）+ GHI 归因（换真值即消失）`——B 散点的相关性暗示由此升级成证据。不走任何 HTTP。

**这一档只能在有模型栈的机器上跑**（`inference.py` + 其 `Base`/`utils` 依赖 + checkpoints）；脚本其余功能在任何机器照常。

必给参数：`--checkpoints-dir`、`--config`（yaml 路径），二者原样透传给 `multi_station_inference`；`--inference-dir` 指向 `inference.py` 所在目录（**插在 `sys.path` 最前**，否则会被脚本自己目录下的同名文件遮蔽）；`--forecasting-type` 默认 `short`。

**只跑反事实、没有生产预测表**：`--predict` 可省略（其余情况仍必填）。此时**本地基线推理顶上「预测」这一路**——右下面板的红线即本地基线（图例随之改名），`power_nrmse` 与 `power_nrmse_localbase` 必然相等，**复现闸整列不出**（拿基线跟自己比毫无意义，不能填 0 假装通过），`--cf-show-local-base` 也自动失效（红线已经就是它）。`--input` 仍必填：功率真值 `observe_power_future` 与 D+1/D+4 切窗都来自它。

**`--cf-input`（推理专用输入表）**：喂给模型的那张 parquet，需含 `station` / `timestamp_win` + 模型全部特征 + `--cf-swap` 的预测与真值两列；**缺省回退用 `--input`**（分析输入本身即推理就绪时，如 `mock_input.parquet` 那 46 列）。分析表有、推理表没有的站 → 告警 + 该站 `cf_status=missing`，其它站照常。

**调用结构**：按 `timestamp_win` 分组，**每窗一次调用、该窗全部站一起送**（`multi_station_inference` 断言 station 唯一 + 窗口单一，正是这个形状）。跑**两趟**：基线（原特征）+ 换真值，故总调用数 = 窗口数 × 2。一窗 480 点的输出横跨 5 天，D+1 与 D+4 共用同一份结果，**推理只在切片循环之前跑一次**。结果落盘 `<out>/<YYYYMMDD>/cf_base_pred.parquet` 与 `cf_swap_pred.parquet`，重跑直接命中缓存（零调用），`--cf-force` 重算。

**行守卫**：swap 两列为空、或真值列长度 ≠ 预测列长度的行，推理前就剔除（喂 None 会让模型崩、长度不等会悄悄改变预测长度）；该站因此记 `cf_status=missing`。窗口内无真值功率 → `cf_status=no_overlap`。

**三道告警**：① 若 `utils.get_past_future_cols` 可导入（即在模型机上），swap 列不在模型 future/extra 特征表里 → 告警「换了也不会变」；② 基线与换真值输出**逐点全等** → 告警模型对该列不敏感、下面的 Δ 无意义；③ 本地基线 vs `--predict` 表 nRMSE 超 `--cf-check-tol`%（默认 1）→ 告警版本/配置可能不一致，并把该站记 `cf_status=baseline_mismatch`（分解仍用本地基线，故自洽）。

**产出**：反事实是**右下功率面板的第三条绿线**（`counterfactual (GHI->truth)`，标题补 `cf RMSE=`），`--cf-show-local-base` 再加一条本地基线灰虚线。指标并入既有 CSV（不再有 `counterfactual_results.csv`）：`fleet_ranking.csv` / `station_power_rmse.csv` 增 `cf_status`、`power_rmse_cf`、`power_nrmse_cf`、`power_nrmse_localbase`、`coadapt`、`base_vs_parquet_pct`，配 `--info-csv` 时另增 `nanwang_official_power_cf`（只出官方口径，不带 factor 扫描）。**Δ 一律用本地基线减本地反事实**，两侧同一批 checkpoints、同一批时点（`truth ∩ base ∩ cf` 三方交集），不掺 predict 表的版本差。

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

### ⑥ 原始可用功率叠加线（`--hist-root`，模块 `pvcore/history_raw.py`）

主表 `observe_power` 是**调整后**的历史功率；`--hist-root` 让左下面板再叠一条**原始**线，取自南网 IN 侧宽表：

```
{--hist-root}/{YYYY-MM-DD}/IN/{plantid}/DQYC_IN_HISTORY_AVAIL_POWER_WIDE.txt
```

`--hist-root` 指到「含日期文件夹」那一层（例 `.../products/data/qy/63/1002`）。**场站号**取站名末尾连续数字（`plant_guangfu1358 → 1358`），无数字则用站名原样。

- **宽表格式**：utf-8、回车隔行、空格隔列、大小写不敏感；列 = `PlantID PDate Tjlx V0000 V0015 … V2345`，`V0000` 即当日 00:00 的取值。有无表头行都能读（无表头时按上述文档列序）。
- **缺测 = NaN，不是 0**：`null`/不可解析 → `NaN`；文件里**缺哪个 `V` 列**（如没有 `V1045`）也补上并置 `NaN`。每天恒定 96 个槽位，缺的那些**画图时断线**。功率里 `0` 是合法值（夜间、停机都是真 0），拿 `0` 冒充缺测就再也分不出「没出力」和「没数据」。拼完还会补齐成完整 15min 网格 —— 不补的话索引里直接没有这些点，matplotlib 会从缺口前一点拉直线连到后一点，看着像有数据。
- **`--hist-tjlx`**：`0-调度端 / 1-场站端 / 2-agc限电标志位`，**默认 1**。同一 `plant+date` 多行时只取这一行。
- **时间对齐**：按主表历史线的实际跨度算出要读哪些日期文件夹（672 点 = 往前 7 天），拼完后裁到 `[t_start, t_end]` —— 两条线**同起同止**，终点就是起报时刻当日 **10:00**。
- **读一趟**：历史与切片无关，`D+1`/`D+4` 共用同一份，txt 只读一次。
- **缺失**：整天文件缺失或该天没有请求的 `Tjlx` → **留空洞并告警**（不拿一整天的 0 冒充，否则图上等于假装全天停机）；场站文件夹找不到 → 告警并列出该日期下实际有哪些文件夹；`--hist-root` 路径不存在 → 直接报错退出。
- **单位**：不做换算，日志里打印两条线各自的量级（`range [...]`）供核对。

### ⑦ K_t 乘性反事实扫描（`--cf-kt-scale`，模块 `pvcore/solar.py` + `pvcore/counterfactual.py`）

`--counterfactual` 回答的是「气象报准了还剩多少误差」（oracle 换真值）。这一项回答另一个问题：
**「预报 GHI 是不是系统性偏高/偏低？按比例缩放能不能变好？」**

```
--cf-kt-scale 0.8,0.9,1.1,1.2   每个 k 一趟推理
```

对每个 k，把预报 GHI 在**晴空指数空间**乘以 k 再放回去、重推一遍：

```
K_t  = GHI_pred / GHI_cs                       晴空指数：这一刻实际有多少晴空的量
GHI' = clip(K_t · k, 0, --cf-kt-max) · GHI_cs  白天
     = max(GHI_pred · k, 0)                     夜间（GHI_cs = 0，天花板无定义就不设）
```

- **为什么绕道 K_t 而不直接乘**：白天那条等价于 `clip(GHI·k, 0, kt_max·GHI_cs)` —— 也就是「先按 k 缩放，再拦在**当时**晴空的 `kt_max` 倍」。`GHI_cs` 是随时间起伏的曲线（南宁夏至：08:00 约 395、13:00 约 1035 W/m²），拿固定阈值截会**两头都错**：早上拦不住 760 这种物理上不可能的值，正午又误伤 1034 这种合法值。天花板是护栏，平时不响，只在 `k` 把某点顶出物理边界（也顶出模型见过的分布）时拦一下；日志会报这一趟拦了多少点、占白天点的百分之几，`ceiling never fired` 就说明这趟纯粹是等比缩放。
- **夜间不设上限是刻意的**：`GHI_cs=0` 处一设上限就等于把夜间预报强行归零 —— 那是偷偷做了一次夜间 oracle，会污染这个实验只想测「乘性缩放」的干净因果。
- **`GHI_cs` 怎么来**：Haurwitz(1945) `1098·cosθz·exp(−0.059/cosθz)`，太阳位置用 Spencer(1971)。只吃**经纬度 + 时刻**，不吃任何实测/预报辐照，也不需要 pvlib。因此 `--info-csv` 必须带 `LATITUDE`/`LONGITUDE` 列（大小写不敏感，也认 `LAT`/`LON`/`LNG`）；缺列直接报错退出，不会安静地一个站都不缩放。
- **前置体检（会打印，不拦）**：
  - `[kt] geometry check` 拿历史 `GHI_SOLARGIS` 的日峰值时刻对比模型算出的真太阳正午。时区传错（`--cf-kt-tz-offset`，默认 8 = 北京时）会显示成几小时的偏差并标 `SUSPECT`；对了则在 ±1.5h 内标 `looks right`。
  - 经纬度落在国境粗框外 → 逐站告警（`falls outside China`）。**info.csv 经纬度串行/错列不会报错，只会安静地把晴空曲线算到别的地方去**，这条告警就是拿来接住它的。
- **成本**：`系数个数 × 起报窗数` 次推理。缓存**逐趟**判定（`cf_kt_<k>_pred.parquet`），所以补一个新的 `k` 只推那一趟，基线和已有的 `k` 都不重推；`--cf-force` 全部重推。`k=1.0` 会被自动剔掉并说明原因（那一趟就是基线）。
- **可以只开这一项**：不给 `--counterfactual` 就不推换真值那趟，省一趟。两个都开则 oracle 与扫描两套列并存。

**产物**：
- `fleet_ranking.csv` **末尾**加列（K_t 块恒排在所有其它列之后）：`power_nrmse_kt<k>`、`nanwang_official_power_kt<k>`（给了 `GCCAPCITY` 时），以及汇总的 `kt_best_factor` / `kt_best_gain`（相对基线省下的 nRMSE 百分点）。比基线好不好 = 拿 `power_nrmse_kt<k>` 和 `power_nrmse_localbase` 直接比，`power_nrmse_localbase` 不算 K_t 列、不跟着挪。
- `counterfactual_kt_scan.png`：左图每站 nRMSE 随 k 的走势 + 舰队中位线；右图真正被改善的站按幅度排序、条上标最优 k。
- 终端结论：多少站能被缩放改善、往哪个方向偏（`k<1` = 预报整体偏高，`k>1` = 偏低）。

**怎么读**：曲线在 `k=1` 触底 = 该站 GHI 预报没有系统性乘性偏差，问题在别处；底部落在 `k=0.8` = 预报整体偏高约 25%（`1/0.8`）。曲线**平的**只有两种可能——模型对 GHI 尺度不敏感，或者该站压根没有可用坐标（看日志），别把后者读成前者。

**其他参数**：`--cf-kt-col`（缩放哪一列，默认 `GHI_SOLARGIS_predict`，应当就是模型吃的那个）、`--cf-kt-max`（K_t 天花板，默认 1.2，余量留给云增强）、`--cf-kt-lines`（把每个 k 的预测也画到右下功率面板上，默认不画）。

## 时间对齐

- **预测/未来 list**：input 某行 `timestamp_win=T`，任意 list 列（`observe_power_future` / `*_predict` / `GHI_real_future`）第 k 个元素时间 = `T+15min×(k+1)`（首元素 = T+15min）。同站各窗摊平、按绝对时间 groupby 去重成连续序列；power 的预测再与 predict 表 `dtime` 对齐。
- **历史 list**（`observe_power` / `GHI_SOLARGIS`）：反向，第 i 个元素（长度 L）时间 = `T − 15min×(L−1−i)`，即 `list[-1] → T`（起报时间）。

## 鲁棒

每张图/每项指标独立成败——某列缺失、或**某站**该列全空 → 只跳那一项并告警，power 与其它站/其它特征/总览照常输出，绝不整体报错。

## 用法

### 跑批脚本 `run_short.sh`

不想记参数就用它,六个模式:

```bash
./run_short.sh              # mock：现产 mock 数据再跑全链路，不需要模型，用来验环境
./run_short.sh basic        # 只跑基础分析（input + predict）
./run_short.sh nanwang      # 加 --info-csv：南网口径 + factor 扫描 + city
./run_short.sh cf           # 加 --counterfactual：GHI 换真值的 oracle 归因（需模型）
./run_short.sh kt           # 加 --cf-kt-scale：K_t 乘性扫描（需模型）
./run_short.sh full         # cf + kt 一起
```

路径改脚本里的 CONFIG 段,或用环境变量临时覆盖任意一项
（`INPUT` / `PREDICT` / `INFO` / `OUT` / `DATE` / `CKPT` / `CONFIG` / `INFER_DIR` / `CF_INPUT` / `KT` / `HIST_ROOT` / `PY`）:

```bash
INPUT=/data/in.parquet PREDICT=/data/pred.parquet INFO=/data/info.csv ./run_short.sh nanwang
CKPT=/m/ckpt CONFIG=/m/cfg.yaml INFER_DIR=/m KT=0.8,0.9,1.1,1.2 ./run_short.sh full
```

模式之后的参数原样透传给 `station_analysis_short.py`:`./run_short.sh nanwang --drop-night --worst-only 5`。
脚本会先查文件在不在、`cf`/`kt`/`full` 的三件套给没给,再把完整命令行打出来,跑完列产物清单。

### 直接调

```bash
python3 station_analysis_short.py --input input.parquet [--predict predict.parquet] --out-dir out \
                                       # --predict 仅在开 --counterfactual 时可省略
  [--drop-night --night-end-hour 5]    # 去掉每天 00:00–05:00（RMSE 也按去掉后算）
  [--tick-hours 1]                     # x 轴刻度间隔（list 步长锁死 15min，不可配）
  [--feature-pairs "GHI_SOLARGIS_predict:GHI_real_future:GHI,ssrd_pos_1_predict:GHI_real_future:ssrd1"]
  [--top-n 30] [--mad-k 3] [--capacity "st1:500,st2:5"]        # 总览：榜单条数 / 离群阈 / 装机
  [--info-csv info.csv]  # 或 --info；每站 GCCAPCITY/GCCAPACITY → 南网 nanwang_official 指标 + city 列。
                         # join 列：info.csv 里有 --station-col 就用它，否则自动探测（值匹配最多的列，如 plantid）
  [--ghi-pred GHI_SOLARGIS_predict --ghi-true GHI_real_future] # 总览 GHI 排名/散点用列
  [--station-col station --win-col timestamp_win --power-col observe_power_future --dtime-col dtime]
  [--pred-col-template "predict_power_{station}"]
  [--hist-root .../qy/63/1002] [--hist-tjlx 1]                  # 左下历史面板叠原始可用功率线（宽表根目录 + 统计类型）
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
- 逐站 `station_<站>.png` —— 2×2 组合图（左列历史 GHI/功率全量点，右列本切片 GHI/功率预测对真值，标 RMSE）；给 `--hist-root` 时左下多一条原始可用功率橙色虚线。
- `station_power_rmse.csv` + `station_feature_rmse.csv`。
- 全场 `fleet_overview.png` + `fleet_ranking.csv`（每站 nRMSE / bias / 容量 / 点数 / 离群标记 / 排名；给 `--info-csv` 时再加 `city` + `GCCAPCITY` + `nanwang_official_power` 及其 factor 扫描列，见下）。
- 反事实（`--counterfactual`）：`counterfactual_overview.png`，加上右下功率面板的第三条绿线；指标并入 `fleet_ranking.csv` / `station_power_rmse.csv`（`cf_status` / `power_rmse_cf` / `power_nrmse_cf` / `power_nrmse_localbase` / `coadapt` / `base_vs_parquet_pct`；给 `--info-csv` 时再加 `nanwang_official_power_cf`）。推理结果缓存在 `<out>/<YYYYMMDD>/cf_base_pred.parquet` 与 `cf_swap_pred.parquet`。

> **`fleet_ranking.csv` 的行序与列序**：有 `nanwang_official_power` 时**恒按它从小到大排**，准确率最低的站在第一行，没有该列（没给 `--info-csv` 或全站缺 `GCCAPCITY`）时退回 `power_nrmse` 降序；两种排法都把值为空的站压到最后。列序上，`--cf-kt-scale` 产的那一批恒排在末尾。**不落盘的派生列**：`delta_nrmse`、`frac_explained`、`delta_nrmse_kt<k>` 三类不写进 CSV，要用就现算 —— `delta_nrmse = power_nrmse_localbase − power_nrmse_cf`、`frac_explained = delta_nrmse / power_nrmse_localbase × 100`、`delta_nrmse_kt<k> = power_nrmse_localbase − power_nrmse_kt<k>`。它们仍在内存里，`counterfactual_overview.png` 与终端的反事实结论照常用。

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

无散点 / 舰队总览 / 反事实。

**南网超短期准确率**（可选，给 `--info-csv`/`--info` 即开启——每站 `GCCAPCITY`/`GCCAPACITY`，join 列同短期规则（有 `--station-col` 列用它，否则按值自动探测），可复用短期同一 info.csv；info.csv 有 `city` 列时 `station_power_rmse.csv` 加 `city` 列）：
`Acc = (1 − mean_t mean_i |P_real(t) − p_i(t)| / max(P_real(t), 0.2·GCCAPCITY)) × 100%`，每时刻对 16 条
lead 取绝对误差均值、再对全天 96 时刻取均值。恒用全部目标点（含夜间，`0.2·GCCAPCITY` 分母下限保证良态，
不受 `--drop-night` 影响）；缺 (lead,时刻) 项按可用项平均。**仅逐站打印到日志（附 fleet mean），不写入任何
CSV**；info-csv 缺某站 → 该站告警跳过。

---

## 代码结构

两个 `.py` 是 CLI 入口，只做参数解析与主流程编排；实现在同级的 `pvcore/` 包里，短期与超短期共用。
拷贝部署时**两个入口脚本 + 整个 `pvcore/` 目录一起拷**。

```
短期分析/
├── station_analysis_short.py        # 短期入口：argparse + 主流程
├── station_analysis_ultra_short.py  # 超短期入口：argparse + 主流程
├── inference.py                     # 本地推理（反事实用），独立于本包
├── make_mocks.py                    # 生成 mock_input/mock_predict.parquet + mock_info.csv
├── run_short.sh                     # 短期跑批：mock / basic / nanwang / cf / kt / full 六个模式
└── pvcore/
    ├── timeseries.py      list 单元格展平（正向/反向）、夜间与窗口掩码、交集对齐 _aligned、并集展示 _display*
    ├── metrics.py         ★ 全部指标：rmse / nrmse_pct / resolve_cap / pooled_rmse / hourly_nrmse /
    │                        nanwang_official + factor 扫描 / nanwang_ultrashort / flag_outliers / cf_decomposition
    ├── inputs.py          info.csv 读取（含 join 列自动探测）、--feature-pairs / --capacity 解析、站点列名正反解析
    ├── plotting.py        matplotlib 共用件：字体、时间轴、历史面板、窗口面板
    ├── plots_short.py     短期图：每站 2x2、舰队总览四宫格、反事实分解左右图
    ├── plots_ultra.py     超短期图：每站 2x2（右下 17 线）
    ├── solar.py           晴空辐照 GHI_cs（Haurwitz）、晴空指数 K_t、K_t 空间缩放、时区/坐标体检
    ├── counterfactual.py  反事实：oracle 换真值 + K_t 乘性扫描，逐趟推理与缓存、逐站分解、复现闸
    ├── short_analysis.py  短期单窗口全流程（run_analysis / compute_windows）
    ├── ultra_loaders.py   超短期时间网格与三个 loader（预测矩阵 / 真值 / 历史）
    └── history_raw.py     南网 IN 侧原始可用功率宽表（`--hist-root`）
```

**改口径只改 `metrics.py`。** 短期与超短期原先各有一份 `load_station_info` / `rmse` / `night_mask` /
字体设置 / 时间轴格式化的拷贝，现在都只此一处 —— 改南网口径、改归一化分母、改离群阈值都不会再出现
「改了一边忘了另一边」。

`pvcore/__init__.py` 刻意不 re-export 任何东西：`plots_*` 会拉起 matplotlib、`counterfactual` 会拉起
模型栈，`import pvcore` 保持零成本，各入口按需只导自己那几个模块。
