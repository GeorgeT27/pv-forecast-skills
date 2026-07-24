# row-diagnostic —— 单行预测反常诊断（独立工具）

给定**某模型在某时间戳的预测**，跟它自己在离线测试集上的**历史统计**比，指出哪里反常：
功率 RMSE 高/低多少、几个 σ，以及**哪个特征反常、排第几、差多少**。上线模型与离线测试集
同构，故线上样本直接当测试行处理——先从离线测试集抽一个时间戳验证，通过即等价于线上可用。

> **完全自包含**：不 import 任何 skill / data_utils，只依赖 `pandas / numpy / pyarrow /
> matplotlib`。整个 `row-diagnostic/` 文件夹拷到任何机器都能跑。
>
> **定位**：本工具只做「跟自身历史比、谁反常」。反常特征 **≠** 证明它导致功率变差；
> 因果验证（z+全局相关、系统偏差分解、反事实替换）请用 `ts-diagnose` 的
> `feature-importance` playbook（feature-quality/counterfactual 变体）。

## 数据契约（三张大表，线上/离线同构）

| 表 | 内容 | 关键列 |
|----|------|--------|
| `predict` | 各模型功率预测 | 每个模型一列，单元格 = 全时域 list（如 192 点） |
| `test` | 真实功率 | `observe_power_future`（同长 list；可 `--true-power-col` 改） |
| `feature_true` | 每个特征的预测与真值 | `X_pred`=预测、`X`=真值（**真值列 = 去掉 `_pred` 的基名**） |

- 每行一个窗口，`timestamp` 列自动侦测（`timestamp/timestamp_win/time/ts/datetime`，或 index）。
- **模型** = `predict` 里所有 list 列。**特征对** = 凡 `X_pred` 且基名 `X` 也在即配对，
  配不上的列（孤立 `_pred`、无 `_pred` 的裸 list、时间戳）跳过并在日志列出。
- **RMSE** = 该行整条序列上 `sqrt(nanmean((pred−true)²))`（功率与特征同一定义）。

## 用法

### ① 离线跑一次，生成基线
```bash
python3 build_baseline.py \
  --predict predict.parquet --test test.parquet --feature-true feature_true.parquet \
  [--true-power-col observe_power_future] [--models auto|pred_M1,pred_M2] [--out baseline.json]
```
产出 `baseline.json`：每模型 power、每特征 的 RMSE 历史统计，**global 与 by_hour（'HH:MM'）
两层**，每层含 `mean/std/median/p10/p25/p75/p90/min/max/n`。特征统计与功率模型无关，存顶层一份。

### ② 对某行做诊断
```bash
python3 row_analysis.py --model pred_M1 --row "2025-01-02 09:00:00"   # 指定时间戳
python3 row_analysis.py --model pred_M1 --worst                        # 该模型 power 最坏行
# 缺省从 baseline.meta 读三张表路径；也可 --predict/--test/--feature-true 显式覆盖
```

产出（`--out-dir` 下）：
- `row_<ts>_features.csv` —— 特征表，**按 z 降序**（最反常在最上 = 头号可疑）：
  `feature, row_rmse, base_mean, base_std, base_median, diff, z, z_robust, pctl_band,
  hour_mean, hour_z, status`。
- `row_<ts>.json` —— 全摘要（功率画像 + 特征 + 反常名单 + 头号可疑 + 免责声明）。
- `row_<ts>_dashboard.png` —— 2×2：功率 pred/true、特征 z 条形、头号可疑特征 pred/true、
  功率误差沿时域剖面（错在 48h 哪一段）。
- 终端 ≤20 行大白话摘要。

## 怎么读

- **`z`**（= `(本行值 − 历史均值)/历史std`）：这行比自己平时高/低几个标准差。
  `|z|<1` 正常、`1≤|z|<2` 略、`≥2` 显著（`status` 列已标）。
- **`hour_z`**：只跟**同一钟点**的历史比——光伏误差极度依赖时刻，同钟点比才公平。
- **核心**：排在最上、`z` 最大的特征，就是这行最反常的可疑元凶。
  注意「一贯就很坏」的特征 `z≈0` 不会被点（它没变反常），这正是「跟自身历史比」的意义。

## 另一套：多站预测分析（`station_analysis.py`，一个脚本、两层视图，独立契约）

用于「宽表 input + `dtime×station` 预测表」这套输入，**一次运行同产两层**：

**① 逐站细看** —— 每站若干张两线对比图（预测 vs 真实，标 RMSE）：
- **Power**：预测功率（predict 表 `dtime×站列`）vs 真实功率（input 的 `observe_power_future`，list）。
- **特征**：预测 vs 真值，二者都在 input 宽表里（list 列）。默认 1 张 `GHI`
  = `GHI_SOLARGIS_predict` vs `GHI_real_future`；`--feature-pairs` 可加更多
  （`GHI_real_future` 是这些预测量的公共真值 label）。

**② 全场总览** —— 单张 `fleet_overview.png`（2×2 仪表盘）定位「谁最离谱」，再按需下钻逐站曲线：
- **A1/A2 排行榜**：各站 **nRMSE** 降序（worst 在顶），中位线 + 离群站红标（功率 + GHI）。
- **B 散点**：GHI-nRMSE vs 功率-nRMSE，一站一点。**唯一能讲的因果故事**——功率差落在
  右上（GHI 输入差可解释）还是左上（GHI 好但功率仍差 = 模型/其它问题）。
- **C 热力图**：时刻 × 场站的功率 nRMSE，看谁在哪个钟点坏（正午 vs 日出日落爬坡）。

**为什么归一化（关键）**：绝对 RMSE 被电站规模支配（大站天然大，排名无意义）。
`nRMSE = RMSE / 该站峰值功率`（自包含代理容量；有真实装机用 `--capacity` 更准），单位 %。
「离谱」= nRMSE 排名靠前 **且** 异常高于全场（> 中位数 + `--mad-k`×MAD，默认 3，红标）。
只用 `observe_power_future`（功率真值）与 `GHI_real_future`（GHI 真值）两种 label——
温度等无真值列评不了，本工具不涉及。

**③ 反事实**（`--counterfactual` 门控，可选，需用户的 FastAPI 预测服务）—— oracle GHI swap：
把 GHI 预测列换成 GHI 真值经统一模型重预测，把每站误差**因果地**分解为
`nRMSE基线 = 模型底线（GHI 完美仍剩）+ GHI 归因（换真值即消失）`——B 散点的相关性暗示由此
升级成证据。每站 2 次调用：**基线复现**（原特征原样发，输出与 predict 表核对 = 复现闸，
差超 `--cf-check-tol`% 告警）+ **换真值**。逐站算完立即落盘 `counterfactual_results.csv`，
中断重跑自动跳过已完成站（`--cf-force` 重算）。**首跑必 `--cf-dry-run`**：零 HTTP，打印
调用计划 + 首站 payload 骨架，确认契约后再实跑。产出单张 `counterfactual_overview.png`：
左图堆叠条（灰 = 模型的锅、橙 = GHI 输入的锅、蓝 = 换真值反而差 = **共适应警示**，
Δ<−0.1 个百分点才标），右图各站「GHI 可解释比例 %」。
API 契约：`POST {"data":[{行dict}]}`（字段 = parquet 列名、list 原样、不带站名，真值 label
列不发）；响应 = `{"status":..., "predictions":[{"timestamp_win":..., "ensemble":[192值]},
...]}` —— 逐窗返回、只取 `ensemble`，按响应自带 `timestamp_win` 摊平去重（同 input 表
规则），返回窗数 ≠ 发送行数 = 对齐闸拦下只跳该站；也兼容扁平 list 响应（与 predict 表该站列
按 dtime 逐点对应）。两条诚实注意事项（已写进图注）：① Δ≈0 ≠ GHI 预报没问题——模型可能
不敏感或已共适应；② 「模型底线」含其它无真值输入（温度等）的误差，是模型自身误差的上界。

**时间对齐**：input 某行 `timestamp_win=T`，任意 list 列第 k 个元素时间 = `T+15min×(k+1)`
（首元素=T+15min）。同站各窗摊平、按绝对时间 groupby 去重成连续序列；power 的预测再与
predict 表 `dtime` 对齐。

**鲁棒**：每张图/每项指标独立成败——某列缺失或**某站**该列全空 → 只跳那一项并告警，
power 与其它站/其它特征/总览照常输出，绝不整体报错。

```bash
python3 station_analysis.py --input input.parquet --predict predict.parquet --out-dir out \
  [--drop-night --night-end-hour 5]   # 去掉每天 00:00–05:00（RMSE 也按去掉后算）
  [--tick-hours 1]                     # 逐站图 x 轴每几小时一刻度（长跨度可调大防糊）
  [--feature-pairs "GHI_SOLARGIS_predict:GHI_real_future:GHI,ssrd_pos_1_predict:GHI_real_future:ssrd1"]
  [--top-n 30] [--mad-k 3] [--capacity "st1:500,st2:5"]   # 总览：榜单条数 / 离群阈 / 装机
  [--no-station-plots]   # 站多时只要总览：不出逐站曲线，站级 CSV 仍写
  [--no-fleet]           # 只要逐站：不出总览与 fleet_ranking
  [--counterfactual --api-url http://... ]      # 反事实（先 --cf-dry-run 确认 payload！）
  [--cf-stations st1,st2] [--cf-force]          # 子集 / 忽略续跑记录全部重算
  [--cf-swap "GHI_SOLARGIS_predict:GHI_real_future"]   # 可多对 = 联合替换
  [--cf-exclude-cols "observe_power_future,GHI_real_future"]  # 不发给 API 的 label 列
  [--cf-timeout 120] [--cf-retries 1] [--cf-check-tol 1.0] [--cf-curves]
```
产物：`out/` 下 —— 逐站 `station_<名>_Power.png` / `station_<名>_<特征>.png`（图宽随点数自适应、
标题含站名+起始时间戳）+ `station_power_rmse.csv` + `station_feature_rmse.csv`；
全场 `fleet_overview.png` + `fleet_ranking.csv`（每站 nRMSE / bias / 离群标记 / 排名）；
反事实 `counterfactual_overview.png` + `counterfactual_results.csv`（每站 status /
nrmse_base / nrmse_cf / delta / frac_explained / 复现闸偏差 / coadapt）+ 可选逐站三线图。

## 组件

- `rd_common.py` —— 读表 / 配对 / RMSE / 统计块 / 偏离度（单行诊断两脚本共用）。
- `build_baseline.py` —— 生成 `baseline.json`。
- `row_analysis.py` —— 单行诊断。
- `station_analysis.py` —— 多站预测分析（逐站曲线 + 全场总览，一个脚本、独立自包含）。
- `test_row_diagnostic.py` / `test_station_analysis.py` —— 自造确定性小数据的单测（`python3 -m pytest`）。
- `demo_out/` —— mock 数据脚本 + 样例产出图（`per_station/` 逐站+小总览、`fleet/` 12 站总览、
  `cf/` 8 站反事实；`make_mock.py` 造逐站数据、`make_fleet_mock.py` 造多站数据、
  `make_cf_demo.py` 造反事实数据 + 内嵌假 FastAPI 全链路实跑）。
