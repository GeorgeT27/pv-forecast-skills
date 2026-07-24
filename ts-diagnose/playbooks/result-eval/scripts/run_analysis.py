#!/usr/bin/env python3
"""Step 3 可视化分析（固化脚本，取代 SKILL.md 里的 heredoc）。

用法（在有 analysis_config.json 的工作目录）：
    python <skill>/scripts/run_analysis.py --range 2025-06 --figs 1,2,4,8
    # --range  输出子目录名 + fig04 的月份过滤（如 2025-06 或 all）
    # --figs   要画哪些图（默认月度诊断四张 1,2,4,8）；可选 1,2,4,5,6,7,8,9

跑完对每张图：先读同名 .stats.json（现含完整曲线 + 形状描述符 trend/max_jump_idx/
roughness，判形态对号 references/figure-diagnostics.md），再 Read PNG，写结论进 ANALYSIS.md。
不要现写 pandas——计算与画图都在 data_utils/plots 里。
"""
import argparse
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import numpy as np
import pandas as pd
import data_utils as du
import plots


def detect_pred_col(pred_df, label_col=du.LABEL_COL):
    """自动侦测预测列：取第一个能堆成 (n,192) 的非 timestamp/label 列。"""
    for c in pred_df.columns:
        if c in (du.TIMESTAMP_COL, label_col):
            continue
        try:
            if du.to_matrix(pred_df, c).shape[1] == du.HORIZON:
                return c
        except Exception:
            continue
    raise ValueError("未能自动侦测预测列——在 analysis_config.json 里显式给 'pred_col'")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--range", default="all", help="输出子目录 + fig04 月份过滤")
    ap.add_argument("--figs", default="1,2,4,8", help="逗号分隔图号")
    ap.add_argument("--config", default="analysis_config.json")
    args = ap.parse_args()
    figs = {int(x) for x in args.figs.split(",") if x.strip()}

    cfg = json.load(open(args.config))
    label = du.load_table(cfg["true_label"])
    month = None if args.range == "all" else args.range
    out = f"figures/{cfg['station']}/{args.range}"
    os.makedirs(out, exist_ok=True)

    pred_col = cfg.get("pred_col")   # 可选；缺则自动侦测（打印所用列名）
    errs, rmses, PY = {}, {}, {}
    for name, path in cfg["predicted"].items():
        pdf = du.load_table(path)
        col = pred_col or detect_pred_col(pdf)
        if not pred_col:
            print(f"[{name}] 自动侦测预测列 = {col}")
        ts, P, Y = du.align(pdf, label, pred_col=col)
        errs[name], rmses[name] = du.error_matrices(P, Y, ts)
        PY[name] = (P, Y, ts)

    # 天气分型（图#8 与月度归因共用）
    ghi = du.rebuild_series(label, du.GHI_COL)
    wc = du.daily_weather_class(ghi)
    wc.to_csv("weather_class.csv")

    if 1 in figs:
        for name, (P, Y, _) in PY.items():
            plots.fig01_true_vs_pred(P, Y, name, f"{out}/01_true_vs_pred_{name}.png")
    if 2 in figs:
        # 逐日 over_error 均值，保留 DatetimeIndex（fig02 by_month 要 to_period）
        daily_err = {}
        for n, e in errs.items():
            s = pd.Series(e.mean(axis=1), index=rmses[n].index)
            daily_err[n] = s.groupby(s.index.normalize()).mean()
        plots.fig02_error_corr(daily_err, f"{out}/02_error_corr.png", by_month=True)
    if 4 in figs:
        plots.fig04_sample_rmse_ts(rmses, f"{out}/04_sample_rmse.png", month=month)
    if 5 in figs:
        plots.fig05_horizon_error(errs, f"{out}/05_horizon_error.png")
    if 6 in figs:
        plots.fig06_intraday_profile(errs, PY[list(PY)[0]][2], f"{out}/06_intraday.png")
    if 7 in figs:
        for name in rmses:
            plots.fig07_daily_rmse(rmses[name], name, f"{out}/07_daily_rmse_{name}.png")
    if 8 in figs:
        plots.fig08_weather_conditional(rmses, wc, f"{out}/08_weather_cond.png")
    if 9 in figs:
        plots.fig09_oracle_gap(rmses, f"{out}/09_oracle_gap.png")

    # 模型对比结论前必过稳健性门槛（示例：前两个模型）
    names = list(rmses)
    if len(names) >= 2:
        print("稳健性门槛（%s vs %s）：" % (names[0], names[1]),
              du.robustness_check(rmses[names[0]], rmses[names[1]]))
    print(f"\n完成。图与 stats.json 在 {out}/ —— 先读 stats.json 曲线判形态，再 Read PNG，写 ANALYSIS.md。")


if __name__ == "__main__":
    main()
