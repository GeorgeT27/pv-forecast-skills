# 单行诊断独立工具 row-diagnostic —— 设计文档

**日期**：2026-07-21
**状态**：已与用户确认设计，待 spec 复核

## 1. 背景与动机

`pv-feature-blame` 技能能对单行做特征归因，但它承重了整条纪律链（z + 全局 ρ 两关、
ε_sys/ε_res 分解、共线簇、反事实门控），并**依赖兄弟技能 `pv-result-analysis/scripts/
data_utils.py`** 与 Stage 0/1.5 前置产物。用户反馈两点痛处：

1. 输出列太多、不易懂；
2. 跨技能依赖（缺 `data_utils.py` 就跑不起来），部署到线上不方便。

因此新建一个**完全自包含、简单直观**的独立工具，只回答一个问题：
**「这一行（某模型、某时间戳）的预测，跟它自己在离线测试集上的历史相比，哪里反常？」**

- 对比结构：**上线模型 vs 它自己在离线测试集上的历史统计**（单模型自比，不引入参考模型）。
- 线上样本与离线测试样本**同构**（都是下述三张大表），故线上样本直接当测试行处理；
  用户先从离线测试集抽一个时间戳验证，通过即等价于线上可用。
- 与 `pv-feature-blame` 的关系：**互不依赖**。本工具不做 z/ρ 全局相关、系统偏差分解、
  反事实——那些留在原技能。本工具只做「跟历史比、谁反常」。

## 2. 数据契约（输入适配是地基，先跑通）

三张 parquet 大表（线上/离线同构）：

| 表 | 内容 | 关键列 |
|----|------|--------|
| `predict` | 各模型的功率预测 | 每个模型一列，单元格 = 192 点 list |
| `test` | 真实功率 | `observe_power_future`（192 点 list；列名可配，默认此值） |
| `feature_true` | 每个特征的预测与真值 | `X_pred`=预测、`X`=真值（真值列**去掉 `_pred` 后缀**） |

- 每行 = 一个窗口，`timestamp` 列（自动侦测候选名：`timestamp/timestamp_win/time/ts/datetime`；
  否则用 index）。相邻行 15 分钟。
- 每格 192 点 list（48h × 15min）。读取 = `np.stack` 成 `(n_rows, 192)` 矩阵。
- **模型发现**：`predict` 里所有「192 点 list」列都视作模型列；`build_baseline` 对每个模型
  各算一套；`row_analysis --model <列名>` 选其一。
- **特征配对**：遍历 `feature_true` 的列，凡以 `_pred` 结尾且去掉后缀后的基名列也存在，
  即配成一对 `{pred: "X_pred", true: "X"}`。配不上的列（孤立 `_pred`、或无 `_pred` 的裸列、
  时间戳列）跳过并在日志里列出（不静默）。
- **对齐**：按 `timestamp` 内连接。功率取 `predict ∩ test`；特征取 `feature_true`。
  某时间戳做诊断时须同时在两处存在，否则报错并提示可用范围。

**RMSE 定义（全工具统一，简单）**：单行 = 该行 192 点上的 `sqrt(nanmean((pred−true)²))`。
不做口径切片（超短期/短期留给原技能）。功率与特征同一定义。

## 3. 组件

### 3.1 `build_baseline.py` —— 离线跑一次，产出 `baseline.json`

读三张测试集大表，对**每个模型**计算并落盘：

- **power**：每行 `pred_power` vs `true_power` 的 RMSE → 在测试集上的统计块；
- **每个 feature**：每行 `X_pred` vs `X` 的 RMSE → 统计块。

每个「统计块」= 下面这一套（既有正态口径又有抗偏态稳健口径）：

```
{mean, std, median, p10, p25, p75, p90, min, max, n}
```

且**两层都存**：
- `global`：全体行；
- `by_hour`：按窗口时间戳的钟点（`HH:MM`）分组各算一套 —— 因为光伏误差极度依赖时刻
  （正午 vs 傍晚天差地别），只跟全局均值比会误判；同钟点比才公平。

`baseline.json` 结构（示意）：
```json
{
  "meta": {"generated_from": {...}, "true_power_col": "observe_power_future",
           "rmse_def": "sqrt(nanmean((pred-true)^2)) over 192 pts", "n_rows": 400},
  "feature_pairs": {"ghi": {"pred": "ghi_pred", "true": "ghi"}, "...": {}},
  "models": {
    "pred_M1": {
      "power":   {"global": {"mean": 5.9, "std": 1.2, "median": 5.7, "p10": 4.4,
                             "p25": 5.0, "p75": 6.7, "p90": 7.5, "min": 3.1,
                             "max": 18.0, "n": 400},
                  "by_hour": {"09:00": {...}, "10:00": {...}}},
      "features": {"ghi": {"global": {...}, "by_hour": {...}}, "...": {}}
    }
  }
}
```

CLI：
```
python3 build_baseline.py --predict P.parquet --test T.parquet --feature-true F.parquet \
  [--true-power-col observe_power_future] [--models auto|pred_M1,pred_M2] [--out baseline.json]
```

### 3.2 `row_analysis.py` —— 对某时间戳 + 某模型做单行诊断

```
python3 row_analysis.py --model pred_M1 --row "2025-01-02 09:00:00" \
  [--worst] [--baseline baseline.json] \
  [--predict P.parquet --test T.parquet --feature-true F.parquet] \
  [--out-dir . --prefix row] [--no-plots]
```

流程：载入 `baseline.json` + 三张表 → 定位目标行（`--row` 时间戳或 `--worst` = 该模型
power RMSE 最大行）→ 计算该行 power RMSE 与每特征 RMSE → 对 `global` 与 `by_hour` 两口径
各算：`diff = x − mean`、`z = (x − mean)/std`、稳健 `z_robust = (x − median)/(p75 − p25)`、
落在哪个百分位带 → 特征按 |z| 降序排。

**输出**：

**A. 功率画像**（终端 + JSON）：该行 power RMSE、基线 μ/σ、高/低多少、几个 σ、同钟点 σ、
是否属反常（阈值见下）。

**B. 特征表** `row_<ts>_features.csv`（核心，按 z 降序 → 最反常特征在最上 = 本行头号可疑）：

| 列 | 含义 |
|----|------|
| `feature` | 特征名 |
| `row_rmse` | 本行该特征 RMSE |
| `base_mean` / `base_std` / `base_median` | 全局基线 |
| `diff` | `row_rmse − base_mean` |
| `z` | `(row_rmse − base_mean)/base_std`（高几个 σ） |
| `z_robust` | `(row_rmse − base_median)/IQR` |
| `hour_mean` / `hour_z` | 同钟点基线均值与 z |
| `pctl_band` | 落在历史分布哪一带（如 `>p90`、`p25–p75`） |
| `status` | `正常` / `略偏高` / `⚠️偏高` / `偏低`（阈值：\|z\|<1 正常，1≤\|z\|<2 略，\|z\|≥2 显著） |

**C. JSON 摘要** `row_<ts>.json`：power 块 + 特征块 + meta + 一句话结论 + 免责声明
（「本工具只做与历史统计的偏离对比，指出反常特征≠证明它导致功率变差；因果验证需
反事实替换，见 pv-feature-blame」——一行，不说教）。

**D. 图** `row_<ts>.png`（2×2 dashboard）：
1. 功率 pred vs true（192 点，误差填充）；
2. 特征偏离条形图（各特征 z，红=显著偏高、灰=正常）；
3. 最反常特征的 pred vs true 序列；
4. 误差沿预测时域分布（功率逐点 |pred−true|，定位 48h 里哪段崩 —— "越往后越飘" vs "某段突崩"）。

**E. 终端**：≤20 行大白话摘要（power 反常否 + 头号可疑特征 + 前几名 z）。

## 4. 额外分析（已确认纳入）

1. **同钟点队列**（by_hour）：判断「就算在同为 10:00 的历史里，这行也反常吗」——比全局更公平。
2. **横向排名**：该行 power RMSE 在全体行里的排名/百分位（是不是最差的那几行）。
3. **误差时域剖面**（dashboard 第 4 图）：错在 48h 的哪一段。

**刻意不做**（YAGNI，避免复杂化）：全局 ρ 相关、ε 系统偏差分解、共线簇、反事实——留在原技能。

## 5. 位置与自包含

新建独立目录 `结果分析skill/row-diagnostic/`：
```
row-diagnostic/
  build_baseline.py     # 无外部 skill 依赖
  row_analysis.py       # 无外部 skill 依赖
  README.md             # 用法 + 数据契约 + baseline.json 说明
  test_row_diagnostic.py  # 自造小合成数据的单测（不依赖 golden）
```
只依赖 `pandas / numpy / pyarrow / matplotlib`（`requirements.txt` 已含）。整个文件夹拷到任何
机器都能跑。

## 6. 测试策略

`test_row_diagnostic.py` 用**脚本内确定性合成的 3 张小表**（无随机、不依赖原 skill 的 golden）：
- 埋一个「某行某特征 RMSE 远高于自身历史」的样本 → 断言 row_analysis 把它排到 z 榜首、
  status=`⚠️偏高`；
- 埋一个「误差大但一直都这么大（历史均值也高）」的特征 → 断言它 z≈0、不进榜首
  （证明"跟自己历史比"而非"绝对误差大"）；
- 断言 by_hour 与 global 两口径都产出、越界时间戳非零退出并提示范围、`--worst` 命中最坏行。

## 7. 非目标

- 不替代 `pv-feature-blame` 的因果归因；不产出「已证实」级结论。
- 不做多模型对比（单模型自比；如需两模型对比后续再议）。
- 不接 FastAPI / 反事实。
