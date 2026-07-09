# scripts/ —— 固化的分析与画图代码

数据格式固定（滚动窗口 parquet，见 SKILL.md 项目背景），所以这些代码一次写好反复用。
**不要每次现写 pandas**：优先调这里的函数；列名不符时只改 `data_utils.py` 顶部 CONFIG，不改逻辑。

每个画图函数产出两个文件：`xxx.png`（人看 + 模型 Read 回看）和 `xxx.stats.json`
（相关系数、R²、PSI、KS p 值等分析数值）——**模型直接读 stats.json 拿数字，
结合 references/ 背景写结论**，不必从图上目测。**走势图的 stats.json 现在存整条曲线**：
`fig05` 全 192 步、`fig06` 全时段、`fig04/07/09` 逐日、`fig01` 按功率分箱，每条曲线附形状描述符
`trend`/`monotonic`/`max_jump_idx`/`max_jump`/`roughness`/`argmax`（由 `_curve_stats` 产出）——
先读整条曲线判走势（别只看单点），再对号 `references/figure-diagnostics.md` 的形态。

## 典型流程：优先用固化脚本（不要现写 pandas）

三个入口脚本读工作目录下的 `analysis_config.json`，一行跑通：

```bash
python <skill>/scripts/run_quality_check.py                              # Step 1 质检
python <skill>/scripts/run_analysis.py  --range 2025-06 --figs 1,2,4,8   # Step 3 可视化
python <skill>/scripts/run_drift.py     --cols "GHI-solargis,observe_power_future"  # 分布漂移
```

`run_analysis.py` 的预测列名优先取 config 的 `pred_col`，缺省则自动侦测（唯一 192 宽的非 label 列）。
需要自定义流程时再直接调底层函数（见下方函数索引）；**注意 `fig02` 的逐日输入要保留 DatetimeIndex**
（`s.groupby(s.index.normalize()).mean()`，别用 `.index.date`，否则 `to_period` 报错）。

## 函数索引

| 文件 | 函数 | 对应 |
|------|------|------|
| **run_quality_check.py** | Step 1 质检入口（读 config，取代旧 heredoc） | `python run_quality_check.py` |
| **run_analysis.py** | Step 3 可视化入口（`--range` `--figs`，pred_col 自动侦测） | `python run_analysis.py --range 2025-06 --figs 1,2,4,8` |
| **run_drift.py** | 分布漂移诊断入口（`--cols`） | `python run_drift.py --cols "GHI-solargis,observe_power_future"` |
| plots | _curve_stats | 曲线序列化 + 形状描述符（走势图 stats.json 用） |
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
