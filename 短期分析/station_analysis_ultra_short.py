#!/usr/bin/env python3
"""PV 多站超短期预测结果分析：对指定日期 D 重建 16 条等 lead 预测线并对照真值。

数据源（两侧都按 起报时间 组织，每 15min 一个 起报）：
  --predict-dir  扁平目录，每个 起报 一个 parquet，文件名含 YYYYMMDDHHMM token；表 = dtime 列 +
                 每站一列（--pred-col-template，默认 predict_power_{station}）；行自 起报+15min 起，
                 只取前 16 点（lead 1..16 = 15min..4h）。
  --input-dir    Hive 分区 date=YYYY-MM-DD/time=HH:MM/ 下单个 parquet；行=station、列=特征
                 （schema 同短期 input，list 列）；未来列只取第 0 个元素 = 起报+15min 值。历史列
                 observe_power / GHI_SOLARGIS 另取：只读 date=D 下**最早**一个可用起报目录，把整条
                 list（长 672 = 往前 7 天）反向展开（list[-1] 落在该起报时刻）画成历史曲线。

目标网格 = D 00:00..23:45 共 96 点。目标 t 的 16 个预测来自 起报 S=t-4h..t-15min；线 p_j = 恒定
lead(17-j)：p1=4h 前（最旧）、p16=15min 前（最新）。真值/GHI 取 time=(t-15min) 目录的 list[0]
（t=00:00 → date=D-1/time=23:45）。缺 起报 → 告警+NaN 缺口，不中断；同 token 多文件 → 退出。
产物：stations/station_<站>.png 每站一张 2×2 组合图（左列历史 GHI/功率单线 = 往前 7 天，右上 2 线
GHI、右下 17 线 Power = 当日 96 点）；station_power_rmse.csv（16 lead 合并 RMSE）、
station_feature_rmse.csv（lead-1 GHI RMSE）。无散点/Theil/舰队图/反事实。
给 --info-csv/--info（每站 GCCAPCITY/GCCAPACITY，join 列缺省自动探测）时逐站打印南网超短期准确率到日志
（仅打印，不进 CSV），info.csv 有 city 列时 station_power_rmse.csv 加 city 列。

本文件只留参数解析与主流程，实现全在 pvcore/（指标 pvcore.metrics、loader pvcore.ultra_loaders、
绘图 pvcore.plots_ultra），其中 metrics / inputs / plotting 与短期分析共用同一份。"""
from __future__ import annotations

import argparse
import os

import numpy as np
import pandas as pd

from pvcore.inputs import load_station_info, stations_from_columns
from pvcore.metrics import nanwang_ultrashort, pooled_rmse, rmse
from pvcore.plots_ultra import plot_station_combo
from pvcore.timeseries import night_mask
from pvcore.ultra_loaders import (find_parquet, issue_times, load_history, load_predict_matrix,
                                  load_truth, target_grid)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--input-dir", required=True, help="真值侧根目录：date=YYYY-MM-DD/time=HH:MM/ 分区")
    ap.add_argument("--predict-dir", required=True, help="预测侧扁平目录：每 起报 一个 parquet，文件名含 YYYYMMDDHHMM")
    ap.add_argument("--date", required=True, help="分析日 D，如 20260723 或 2026-07-23")
    ap.add_argument("--out-dir", default="station_analysis_ultra_short_out")
    ap.add_argument("--pred-col-template", default="predict_power_{station}")
    ap.add_argument("--station-col", default="station")
    ap.add_argument("--drop-night", action="store_true", help="remove each day's 00:00-night_end_hour points")
    ap.add_argument("--night-end-hour", type=float, default=5.0)
    ap.add_argument("--tick-hours", type=int, default=1)
    ap.add_argument("--no-plots", action="store_true", help="no plots, still writes CSVs")
    ap.add_argument("--info-csv", "--info", dest="info_csv", default=None,
                    help="CSV 含每站 GCCAPCITY/GCCAPACITY（有 --station-col 列就按它 join，否则按值匹配自动探测，"
                         "如 plantid/plant_pointname）；给了就逐站打印南网超短期准确率（仅日志，不进 CSV），"
                         "并在 station_power_rmse.csv 加 city 列（info.csv 有 city 列时）")
    args = ap.parse_args()
    D = pd.Timestamp(args.date).normalize()

    truth, miss_in = load_truth(args.input_dir, D, args.station_col)
    if not truth:
        raise SystemExit("no input data found in any 起报 dir -- check --input-dir/--date")
    probe = None
    for S in issue_times(D):
        probe = find_parquet(args.predict_dir, S.strftime("%Y%m%d%H%M"))
        if probe:
            break
    if probe is None:
        raise SystemExit("no predict parquet found for any 起报 -- check --predict-dir/--date")
    pred_sts = set(stations_from_columns(pd.read_parquet(probe).columns, args.pred_col_template))
    sts = sorted(set(truth) & pred_sts, key=str)
    only_in, only_pred = sorted(set(truth) - pred_sts), sorted(pred_sts - set(truth))
    if only_in:
        print(f"  [warn] stations only on input side, skipped: {only_in}")
    if only_pred:
        print(f"  [warn] stations only on predict side, skipped: {only_pred}")
    if not sts:
        raise SystemExit("no station present on both input and predict sides")
    hist, hist_S = ({}, None) if args.no_plots else load_history(args.input_dir, D, args.station_col)
    if hist_S is not None:
        print(f"  [history] 起报 {hist_S:%Y-%m-%d %H:%M} 的整条历史 list（往前展开）用于左列两个面板")
    info_map = load_station_info(args.info_csv, args.station_col, sts) if args.info_csv else {}
    gccap_map = {k: v["gccap"] for k, v in info_map.items() if v["gccap"] is not None}
    city_map = {k: v["city"] for k, v in info_map.items() if v["city"] is not None}
    mats, miss_pred = load_predict_matrix(args.predict_dir, D, sts, args.pred_col_template)

    out_root = os.path.join(args.out_dir, D.strftime("%Y%m%d"))
    os.makedirs(out_root, exist_ok=True)
    keep = night_mask(target_grid(D), args.drop_night, args.night_end_hour)
    power_rows, feat_rows = [], []
    for st in sts:
        tr = truth[st]
        rv, n = pooled_rmse(tr["power_true"], mats[st], keep)
        if rv is not None:
            prow = {"station": st, "power_rmse": round(rv, 6), "n_points": n}
            ct = city_map.get(str(st))
            if ct is not None:
                prow["city"] = ct
            power_rows.append(prow)
        else:
            print(f"  [warn] station {st}: no scored (lead, target) pairs, power skipped")
        gt, gp = tr["ghi_true"][keep], tr["ghi_pred"][keep]
        both = np.isfinite(gt.to_numpy(float)) & np.isfinite(gp.to_numpy(float))
        grm = rmse(gp.to_numpy(float)[both], gt.to_numpy(float)[both]) if both.any() else None
        if grm is not None:
            feat_rows.append({"station": st, "feature": "GHI", "rmse": round(grm, 6),
                              "n_points": int(both.sum())})
        if not args.no_plots:
            plot_station_combo(st, tr, mats[st], rv, n, grm, keep, hist.get(st, {}),
                               out_root, args.tick_hours)

    if power_rows:
        pd.DataFrame(power_rows).sort_values("power_rmse", ascending=False).to_csv(
            os.path.join(out_root, "station_power_rmse.csv"), index=False)
    if feat_rows:
        pd.DataFrame(feat_rows).sort_values("rmse", ascending=False).to_csv(
            os.path.join(out_root, "station_feature_rmse.csv"), index=False)

    if gccap_map:
        accs = []
        for st in sts:
            gc = gccap_map.get(str(st))
            if gc is None:
                print(f"  [warn] station {st}: not in --info-csv, nanwang_ultrashort skipped")
                continue
            acc, n_t = nanwang_ultrashort(truth[st]["power_true"], mats[st], gc)
            if acc is None:
                print(f"  [warn] station {st}: no valid (truth, lead) pair, nanwang_ultrashort skipped")
                continue
            accs.append(acc)
            print(f"[nanwang_ultrashort] station {st}: {acc:.2f}%   (C={gc:g}, {n_t}/96 时刻, 全点含夜间)")
        if accs:
            print(f"[nanwang_ultrashort] fleet mean: {float(np.mean(accs)):.2f}%   ({len(accs)} stations)")

    print(f"[ultra_short] D={D:%Y-%m-%d}   stations x{len(sts)}   "
          f"missing 起报: predict {miss_pred}/{len(issue_times(D))}, input {miss_in}/96   -> {out_root}/")


if __name__ == "__main__":
    main()
