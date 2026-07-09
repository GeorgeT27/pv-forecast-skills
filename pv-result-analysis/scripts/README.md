# scripts/ —— 固化的分析与画图代码

数据格式固定（滚动窗口 parquet，见 SKILL.md 项目背景），所以这些代码一次写好反复用。
**不要每次现写 pandas**：优先调这里的函数；列名不符时只改 `data_utils.py` 顶部 CONFIG，不改逻辑。

每个画图函数产出两个文件：`xxx.png`（人看 + 模型 Read 回看）和 `xxx.stats.json`
（相关系数、R²、PSI、KS p 值等分析数值）——**模型直接读 stats.json 拿数字，
结合 references/ 背景写结论**，不必从图上目测。

## 典型流程

```python
import sys; sys.path.insert(0, "<skill>/scripts")
import data_utils as du, plots

# 1. 读取 + 质检
label = du.load_table(cfg["true_label"])
assert du.check_window_consistency(label, du.LABEL_COL) == 0   # 窗口一致性
power = du.rebuild_series(label, du.LABEL_COL)                 # 物理连续序列
du.scan_suspect_days(power).to_csv("suspect_days.csv")         # 可疑日 → 用户核对

# 2. 各模型误差矩阵
errs, rmses = {}, {}
for name, path in pred_paths.items():                          # M1..M4, ensemble
    ts, P, Y = du.align(du.load_table(path), label, pred_col)
    errs[name], rmses[name] = du.error_matrices(P, Y, ts)

# 3. 天气分型（图#8 与漂移诊断共用）
ghi = du.rebuild_series(label, du.GHI_COL)
wc = du.daily_weather_class(ghi); wc.to_csv("weather_class.csv")

# 4. 图谱（输出到 figures/<电站>/<范围>/，见 SKILL.md）
plots.fig02_error_corr({k: v.groupby(v.index.date).mean() for k, v in
                        {n: pd.Series(e.mean(1), rmses[n].index)
                         for n, e in errs.items()}.items()}, out, by_month=True)
plots.fig04_sample_rmse_ts(rmses, out, month="2025-06")
plots.fig08_weather_conditional(rmses, wc, out)

# 5. 模型对比结论前必过稳健性门槛
du.robustness_check(rmses["M1"], rmses["M2"])   # passed=True 才能写"谁比谁好"

# 6. 分布漂移（需训练集）
train = du.load_table(cfg["train_set"])
plots.fig11_train_test_dist(du.rebuild_series(train, du.GHI_COL), ghi, "GHI", out)
```

## 函数索引

| 文件 | 函数 | 对应 |
|------|------|------|
| data_utils | load_table / to_matrix / align / error_matrices | 数据准备 |
| data_utils | rebuild_series | 滚动窗口→物理序列（分布统计前必做） |
| data_utils | basic_quality_checks / longest_constant_run | Step 1 质检（重复戳/缺口/常值段） |
| data_utils | check_window_consistency / scan_suspect_days | Step 1 质检 |
| data_utils | clear_sky_envelope / daily_kt_sigma / daily_weather_class | 天气分型（kt+σΔ→五类：晴稳/多云平稳/阴稳/多云波动/突变日；后两者供跨年共享基准） |
| data_utils | psi / robustness_check | 漂移量化 / 结论稳健性门槛 |
| data_utils | drift_table / weather_class_drift | 分布漂移诊断驱动（特征/标签漂移数值表；天气型漂移用 2024 共享基准） |
| plots | fig01…fig09 | 图谱 #1-#9（#3 用 metric.py Excel，无需脚本） |
| plots | fig11 / fig12 | 分布漂移诊断（同月分布对比 / 功率-辐照映射） |
| （待写） | fig10 | NWP 误差月度曲线——前提验证通过后补 |

## 注意

- 运行依赖见仓库根 `requirements.txt`（pandas/numpy/matplotlib/pyarrow/scipy/openpyxl），
  环境缺包先 `pip install -r requirements.txt`。
- 代码尚未在真实数据上跑过：首跑遇到列名/dtype 出入，改 CONFIG 或小修后
  **把修正提交回本目录**，让下次会话直接可用。
- 中文字体在无 CJK 字体的环境会变方块——数值都在 stats.json 里，不影响分析。
