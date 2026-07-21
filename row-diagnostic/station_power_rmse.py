#!/usr/bin/env python3
"""每站若干张两线对比图（预测 vs 真实），标注 RMSE。完全自包含（pandas/numpy/matplotlib）。

产出（每站）：
  1) Power   —— 预测功率（来自 predict 表 dtime×站列）vs 真实功率（input 的 observe_power_future）。
  2) 各特征 —— 预测特征 vs 真值特征，二者都在 input 宽表里（list 列）。默认 1 张：
     GHI = GHI_SOLARGIS_predict（预测） vs GHI_real_future（真值）。用 --feature-pairs 可加更多，
     如 ssrd_pos_1_predict:GHI_real_future:ssrd1（GHI_real_future 是这些预测量的公共真值 label）。

鲁棒（关键）：每张图独立成败。某图所需列缺失、或**某站**该列全空 → 只跳过那一张并告警，
  power 图与其它站/其它特征图照常输出，绝不整体报错。

时间对齐：input 某行 timestamp_win=T，则任意 list 列（observe_power_future / *_predict /
  GHI_real_future）的第 k 个元素时间 = T+15min×(k+1)（首元素=T+15min）。同站各窗摊平、按绝对
  时间 groupby 去重成连续序列；power 的预测再与 predict 表 dtime 对齐。

配置：--drop-night 去掉每天 00:00–05:00（可 --night-end-hour 改界，RMSE 也按去掉后算）；
  --tick-hours 每几小时一个 x 刻度（默认 1）；图宽随点数自适应，600+ 点也铺得开。

用法：
  python3 station_power_rmse.py --input input.parquet --predict predict.parquet [--out-dir OUT]
  [--drop-night] [--night-end-hour 5] [--tick-hours 1] [--step-min 15]
  [--feature-pairs "GHI_SOLARGIS_predict:GHI_real_future:GHI,ssrd_pos_1_predict:GHI_real_future:ssrd1"]
  [--station-col station --win-col timestamp_win --power-col observe_power_future --dtime-col dtime]
  [--no-plots]
"""
from __future__ import annotations

import argparse
import os

import numpy as np
import pandas as pd

DEFAULT_FEATURE_PAIRS = [("GHI_SOLARGIS_predict", "GHI_real_future", "GHI")]


def sanitize(s) -> str:
    return "".join(c if str(c).isalnum() else "_" for c in str(s))


def series_from_lists(wins, lists, step) -> pd.Series:
    """把一个站某 list 列的所有窗摊平成 (绝对时间→值) 序列，按时间 groupby 去重。
    非 list / None / NaN 单元格自动跳过（鲁棒：某站该特征缺失 → 返回空序列）。"""
    times, vals = [], []
    for t0, fut in zip(wins, lists):
        if fut is None or np.ndim(fut) == 0:          # 标量/None/NaN → 跳过
            continue
        arr = np.asarray(fut, dtype=float).ravel()
        if arr.size == 0:
            continue
        t0 = pd.Timestamp(t0)
        for k, v in enumerate(arr):
            if np.isfinite(v):
                times.append(t0 + step * (k + 1))
                vals.append(float(v))
    if not times:
        return pd.Series(dtype=float)
    s = pd.Series(vals, index=pd.DatetimeIndex(times))
    return s.groupby(s.index).mean().sort_index()


def night_mask(idx: pd.DatetimeIndex, drop_night: bool, night_end_hour: float) -> np.ndarray:
    """True=保留。drop_night 时去掉 [00:00, night_end_hour) 的点。"""
    if not drop_night:
        return np.ones(len(idx), bool)
    hod = idx.hour + idx.minute / 60.0
    return ~(hod < night_end_hour)


def plot_two_lines(st, name, times, true_v, pred_v, rmse, out_dir,
                   tick_hours, true_label, pred_label):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.dates as mdates
    import matplotlib.pyplot as plt

    times = pd.DatetimeIndex(times)
    n_hours = max(1.0, (times[-1] - times[0]).total_seconds() / 3600.0)
    width = min(60.0, max(16.0, n_hours * 0.3))       # 随时间跨度自适应，600+ 点也铺得开
    fig, ax = plt.subplots(figsize=(width, 6))
    ax.plot(times, true_v, label=true_label, color="#1f77b4", lw=1.3)
    ax.plot(times, pred_v, label=pred_label, color="#d62728", lw=1.1, alpha=0.85)
    ax.fill_between(times, true_v, pred_v, color="#d62728", alpha=0.12)
    ax.set_title(f"Station {st}  —  {name}   RMSE={rmse:.3f}   "
                 f"start {times[0]:%Y-%m-%d %H:%M}   (n={len(times)} pts)",
                 fontsize=13, fontweight="bold")
    ax.xaxis.set_major_locator(mdates.HourLocator(interval=max(1, int(tick_hours))))
    ax.xaxis.set_major_formatter(mdates.DateFormatter("%m-%d %H:%M"))
    plt.setp(ax.get_xticklabels(), rotation=90, fontsize=7)
    ax.set_xlabel("time"); ax.set_ylabel(name); ax.legend(loc="upper right"); ax.grid(alpha=0.25)
    fig.tight_layout()
    path = os.path.join(out_dir, f"station_{sanitize(st)}_{sanitize(name)}.png")
    fig.savefig(path, dpi=110); plt.close(fig)
    return path


def _aligned(a: pd.Series, b: pd.Series, drop_night, night_end_hour):
    """两条时间序列取公共时间点 + 去夜间。返回 (times, a_vals, b_vals) 或 None（无公共点）。"""
    common = a.index.intersection(b.index).sort_values()
    if len(common) == 0:
        return None
    keep = night_mask(common, drop_night, night_end_hour)
    common = common[keep]
    if len(common) == 0:
        return None
    return common, a.loc[common].to_numpy(), b.loc[common].to_numpy()


def parse_feature_pairs(spec):
    if not spec:
        return list(DEFAULT_FEATURE_PAIRS)
    out = []
    for item in spec.split(","):
        parts = [p.strip() for p in item.split(":")]
        if len(parts) == 2:
            parts.append(parts[0])
        if len(parts) != 3 or not all(parts[:2]):
            raise SystemExit(f"--feature-pairs 项格式应为 pred:true[:label]，收到 '{item}'")
        out.append(tuple(parts))
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--input", required=True)
    ap.add_argument("--predict", required=True)
    ap.add_argument("--out-dir", default="station_rmse_out")
    ap.add_argument("--step-min", type=int, default=15)
    ap.add_argument("--drop-night", action="store_true", help="去掉每天 00:00–night_end_hour 的点")
    ap.add_argument("--night-end-hour", type=float, default=5.0)
    ap.add_argument("--tick-hours", type=int, default=1, help="每几小时一个 x 刻度")
    ap.add_argument("--feature-pairs", default=None,
                    help="pred:true[:label] 逗号分隔；缺省 GHI_SOLARGIS_predict:GHI_real_future:GHI")
    ap.add_argument("--station-col", default="station")
    ap.add_argument("--win-col", default="timestamp_win")
    ap.add_argument("--power-col", default="observe_power_future")
    ap.add_argument("--dtime-col", default="dtime")
    ap.add_argument("--no-plots", action="store_true")
    args = ap.parse_args()
    step = pd.Timedelta(minutes=args.step_min)
    feature_pairs = parse_feature_pairs(args.feature_pairs)

    inp = pd.read_parquet(args.input)
    pred = pd.read_parquet(args.predict)
    for c in (args.station_col, args.win_col, args.power_col):
        if c not in inp.columns:
            raise SystemExit(f"输入表缺列 '{c}'；实际列: {list(inp.columns)[:30]}")
    if args.dtime_col not in pred.columns:
        raise SystemExit(f"预测表缺列 '{args.dtime_col}'；实际列: {list(pred.columns)[:30]}")
    inp[args.win_col] = pd.to_datetime(inp[args.win_col])
    pred[args.dtime_col] = pd.to_datetime(pred[args.dtime_col])
    pred = pred.groupby(args.dtime_col).mean(numeric_only=True).sort_index()

    # 特征对里列全局缺失的先整对剔除（告警一次）
    active_pairs = []
    for pcol, tcol, label in feature_pairs:
        miss = [c for c in (pcol, tcol) if c not in inp.columns]
        if miss:
            print(f"  ⚠ 特征图 '{label}' 跳过：输入表缺列 {miss}")
        else:
            active_pairs.append((pcol, tcol, label))

    os.makedirs(args.out_dir, exist_ok=True)
    stations = list(pd.unique(inp[args.station_col]))
    power_rows, feat_rows, imgs = [], [], []

    for st in stations:
        sub = inp[inp[args.station_col] == st]
        wins = sub[args.win_col].to_numpy()

        # ---- Power（预测来自 predict 表）----
        truth = series_from_lists(wins, sub[args.power_col].to_numpy(), step)
        col = st if st in pred.columns else (str(st) if str(st) in pred.columns else None)
        if col is None:
            print(f"  ⚠ 站 {st}: 预测表无此列，跳过 Power 图")
        else:
            al = _aligned(truth, pred[col].dropna(), args.drop_night, args.night_end_hour)
            if al is None:
                print(f"  ⚠ 站 {st}: Power 真值/预测无公共时间点（或全在夜间被去掉），跳过")
            else:
                times, t, p = al
                rmse = float(np.sqrt(np.mean((p - t) ** 2)))
                power_rows.append({"station": st, "power_rmse": round(rmse, 6),
                                   "n_points": int(len(times)),
                                   "t_start": str(times.min()), "t_end": str(times.max())})
                if not args.no_plots:
                    imgs.append(plot_two_lines(st, "Power", times, t, p, rmse, args.out_dir,
                                               args.tick_hours, "observed power", "predicted power"))

        # ---- 特征（预测与真值都在 input）----
        for pcol, tcol, label in active_pairs:
            pser = series_from_lists(wins, sub[pcol].to_numpy(), step)
            tser = series_from_lists(wins, sub[tcol].to_numpy(), step)
            if pser.empty or tser.empty:
                print(f"  ⚠ 站 {st}: 特征 '{label}' 该站数据缺失/为空，跳过（不影响其它图）")
                continue
            al = _aligned(tser, pser, args.drop_night, args.night_end_hour)
            if al is None:
                print(f"  ⚠ 站 {st}: 特征 '{label}' 无公共时间点，跳过")
                continue
            times, tv, pv = al
            rmse = float(np.sqrt(np.mean((pv - tv) ** 2)))
            feat_rows.append({"station": st, "feature": label, "rmse": round(rmse, 6),
                              "n_points": int(len(times))})
            if not args.no_plots:
                imgs.append(plot_two_lines(st, label, times, tv, pv, rmse, args.out_dir,
                                           args.tick_hours, f"{tcol} (true)", f"{pcol} (pred)"))

    if not power_rows and not feat_rows:
        raise SystemExit("没有任何图能画（检查 station 是否等于预测表列名、时间是否对得上、列是否存在）。")
    if power_rows:
        pw = pd.DataFrame(power_rows).sort_values("power_rmse", ascending=False)
        pw.to_csv(os.path.join(args.out_dir, "station_power_rmse.csv"), index=False)
    if feat_rows:
        pd.DataFrame(feat_rows).sort_values(["feature", "rmse"], ascending=[True, False]).to_csv(
            os.path.join(args.out_dir, "station_feature_rmse.csv"), index=False)

    print(f"[station_power_rmse] 站 ×{len(stations)}   特征对 {[p[2] for p in active_pairs] or '无'}   "
          f"drop_night={args.drop_night}   → {args.out_dir}/")
    if power_rows:
        print("  Power RMSE:")
        print(pw.to_string(index=False))
    print(f"  产物: 图 ×{len(imgs)}"
          + ("  + station_power_rmse.csv" if power_rows else "")
          + ("  + station_feature_rmse.csv" if feat_rows else ""))


if __name__ == "__main__":
    main()
