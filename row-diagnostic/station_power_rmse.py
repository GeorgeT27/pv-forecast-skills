#!/usr/bin/env python3
"""每站一张图：功率预测 vs 真实，标注 power RMSE。完全自包含（pandas/numpy/matplotlib）。

输入两张 parquet：
  --input   真值宽表：列含 station、timestamp_win、observe_power_future(list=未来功率真值，
            长度不限，可 >192)，以及各特征列（本脚本只用功率，特征列忽略）。
  --predict 预测表：列 dtime、<站名1>、<站名2>… —— 每行一个 15min 时间点，每列一个站的预测功率
            （不是划窗，每行前进 15min）。输入表的 station 取值 = 本表的列名。

时间对齐（关键）：输入某行 timestamp_win=T，则 observe_power_future[k] 的真值时间 = T+15min×(k+1)
  （win=10:00 → 首元素 10:15、次元素 10:30…）。把该站所有窗的 future 摊平、按绝对时间 groupby
  去重成一条连续真值序列，再与预测表 dtime 对齐，逐点算 RMSE。

用法：
  python3 station_power_rmse.py --input input.parquet --predict predict.parquet [--out-dir OUT]
  [--step-min 15] [--station-col station --win-col timestamp_win --power-col observe_power_future
   --dtime-col dtime] [--no-plots]
产物：OUT/ 下每站一张 station_<名>_power_rmse.png + 汇总 station_power_rmse.csv。
"""
from __future__ import annotations

import argparse
import os

import numpy as np
import pandas as pd


def sanitize(s) -> str:
    return "".join(c if str(c).isalnum() else "_" for c in str(s))


def build_truth_series(wins, futures, step) -> pd.Series:
    """把一个站的所有窗的 observe_power_future 摊平成 (绝对时间→真值) 序列，按时间 groupby 去重。"""
    times, vals = [], []
    for t0, fut in zip(wins, futures):
        t0 = pd.Timestamp(t0)
        for k, v in enumerate(np.asarray(fut, dtype=float)):
            times.append(t0 + step * (k + 1))
            vals.append(float(v))
    if not times:
        return pd.Series(dtype=float)
    s = pd.Series(vals, index=pd.DatetimeIndex(times))
    return s.groupby(s.index).mean().sort_index()      # 重叠窗同一物理时刻去重


def plot_station(st, times, true_p, pred_p, rmse, out_dir):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    fig, ax = plt.subplots(figsize=(14, 5))
    ax.plot(times, true_p, label="observed power", color="#1f77b4", lw=1.3)
    ax.plot(times, pred_p, label="predicted power", color="#d62728", lw=1.1, alpha=0.85)
    ax.fill_between(times, true_p, pred_p, color="#d62728", alpha=0.12)
    ax.set_title(f"Station {st}  —  power RMSE = {rmse:.3f}   (n={len(times)} points, "
                 f"{pd.Timestamp(times[0]):%Y-%m-%d %H:%M} → {pd.Timestamp(times[-1]):%Y-%m-%d %H:%M})")
    ax.set_xlabel("time"); ax.set_ylabel("power"); ax.legend(); ax.grid(alpha=0.25)
    fig.autofmt_xdate(); fig.tight_layout()
    path = os.path.join(out_dir, f"station_{sanitize(st)}_power_rmse.png")
    fig.savefig(path, dpi=110); plt.close(fig)
    return path


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--input", required=True)
    ap.add_argument("--predict", required=True)
    ap.add_argument("--out-dir", default="station_rmse_out")
    ap.add_argument("--step-min", type=int, default=15)
    ap.add_argument("--station-col", default="station")
    ap.add_argument("--win-col", default="timestamp_win")
    ap.add_argument("--power-col", default="observe_power_future")
    ap.add_argument("--dtime-col", default="dtime")
    ap.add_argument("--no-plots", action="store_true")
    args = ap.parse_args()
    step = pd.Timedelta(minutes=args.step_min)

    inp = pd.read_parquet(args.input)
    pred = pd.read_parquet(args.predict)
    for c in (args.station_col, args.win_col, args.power_col):
        if c not in inp.columns:
            raise SystemExit(f"输入表缺列 '{c}'；实际列: {list(inp.columns)[:30]}")
    if args.dtime_col not in pred.columns:
        raise SystemExit(f"预测表缺列 '{args.dtime_col}'；实际列: {list(pred.columns)[:30]}")

    inp[args.win_col] = pd.to_datetime(inp[args.win_col])
    pred[args.dtime_col] = pd.to_datetime(pred[args.dtime_col])
    # 预测表按 dtime groupby 去重（每行前进15min；若有重复时间取均值），index=dtime、列=各站
    pred = pred.groupby(args.dtime_col).mean(numeric_only=True).sort_index()

    os.makedirs(args.out_dir, exist_ok=True)
    stations = list(pd.unique(inp[args.station_col]))
    rows, imgs = [], []
    for st in stations:
        sub = inp[inp[args.station_col] == st]
        truth = build_truth_series(sub[args.win_col].to_numpy(),
                                   sub[args.power_col].to_numpy(), step)
        # 站名 → 预测表列名（先原值、再字符串化兜底）
        col = st if st in pred.columns else (str(st) if str(st) in pred.columns else None)
        if col is None:
            print(f"  ⚠ 预测表里没有站 '{st}' 的列，跳过")
            continue
        pseries = pred[col].dropna()
        common = truth.index.intersection(pseries.index).sort_values()
        if len(common) == 0:
            print(f"  ⚠ 站 {st}: 真值与预测无共同时间点，跳过")
            continue
        t = truth.loc[common].to_numpy()
        p = pseries.loc[common].to_numpy()
        rmse = float(np.sqrt(np.mean((p - t) ** 2)))
        rows.append({"station": st, "power_rmse": round(rmse, 6), "n_points": int(len(common)),
                     "t_start": str(common.min()), "t_end": str(common.max())})
        if not args.no_plots:
            imgs.append(plot_station(st, common.to_pydatetime(), t, p, rmse, args.out_dir))

    if not rows:
        raise SystemExit("没有任何站算出 RMSE（检查 station 取值是否等于预测表列名、时间是否对得上）。")
    summ = pd.DataFrame(rows).sort_values("power_rmse", ascending=False)
    csv_path = os.path.join(args.out_dir, "station_power_rmse.csv")
    summ.to_csv(csv_path, index=False)

    print(f"[station_power_rmse] 站 ×{len(rows)}   步长 {args.step_min}min   → {args.out_dir}/")
    print(summ.to_string(index=False))
    print(f"  产物: 每站一张 png ×{len(imgs)} + {csv_path}")


if __name__ == "__main__":
    main()
