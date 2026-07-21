# row-diagnostic —— 单行预测反常诊断（独立工具）

给定**某模型在某时间戳的预测**，跟它自己在离线测试集上的**历史统计**比，指出哪里反常：
功率 RMSE 高/低多少、几个 σ，以及**哪个特征反常、排第几、差多少**。上线模型与离线测试集
同构，故线上样本直接当测试行处理——先从离线测试集抽一个时间戳验证，通过即等价于线上可用。

> **完全自包含**：不 import 任何 skill / data_utils，只依赖 `pandas / numpy / pyarrow /
> matplotlib`。整个 `row-diagnostic/` 文件夹拷到任何机器都能跑。
>
> **定位**：本工具只做「跟自身历史比、谁反常」。反常特征 **≠** 证明它导致功率变差；
> 因果验证（z+全局相关、系统偏差分解、反事实替换）请用 `pv-feature-blame` 技能。

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

## 组件

- `rd_common.py` —— 读表 / 配对 / RMSE / 统计块 / 偏离度（两脚本共用）。
- `build_baseline.py` —— 生成 `baseline.json`。
- `row_analysis.py` —— 单行诊断。
- `test_row_diagnostic.py` —— 自造确定性小数据的单测（`python3 -m pytest`）。
