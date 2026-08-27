#!/usr/bin/env python3
"""PV 多站短期预测结果分析（数据格式锁定：起报时间恒为当日 10:00，输入 list 列长 480、首元素 10:15、步长 15min，预测表 dtime 从次日 00:00 起）。
按 起报日 D 切 D+1、D+4 两个 24h 窗，每窗每站产一张 2x2 组合图（左列 history GHI/功率全量点，右列本窗 GHI/功率预测对真值）
+ 舰队总览与排名；可选 --counterfactual 经本地 inference.py 做 GHI oracle 替换归因。

本文件只留参数解析与主流程，实现全在 pvcore/（指标 pvcore.metrics、绘图 pvcore.plots_short、
反事实 pvcore.counterfactual、单窗编排 pvcore.short_analysis）。"""
from __future__ import annotations

import argparse
import os

import pandas as pd

from pvcore.counterfactual import (CF_PRED_COL_TEMPLATE, cf_build_predictions, kt_coords_from_info,
                                   kt_geometry_check, parse_cf_swap, parse_kt_factors)
from pvcore.inputs import load_station_info, parse_capacity, parse_feature_pairs
from pvcore.short_analysis import compute_windows, run_analysis
from pvcore.timeseries import STEP, hist_span

# 单测把本文件当模块加载后按这些名字取用（sa.window_mask / sa.cf_metrics ...），
# 保留这一段 re-export，它们就还是从这里可见的。
from pvcore.metrics import cf_decomposition as cf_metrics                       # noqa: F401
from pvcore.plotting import _draw_hist_panel, _draw_win_panel                   # noqa: F401
from pvcore.timeseries import (_aligned, _display, _display_multi,              # noqa: F401
                               series_from_lists_history, window_mask)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--input", required=True)
    ap.add_argument("--predict", default=None,
                    help="生产预测表（dtime + 每站一列）。省略时必须开 --counterfactual，"
                         "由本地基线推理顶上「预测」这一路（此时无对照物，不出复现闸列）")
    ap.add_argument("--out-dir", default="station_analysis_out")
    ap.add_argument("--drop-night", action="store_true", help="remove each day's 00:00-night_end_hour points")
    ap.add_argument("--night-end-hour", type=float, default=5.0)
    ap.add_argument("--tick-hours", type=int, default=1, help="one x tick every few hours in per-station plots")
    ap.add_argument("--feature-pairs", default=None,
                    help="pred:true[:label] comma-separated; default GHI_SOLARGIS_predict:GHI_real_future:GHI")
    ap.add_argument("--top-n", type=int, default=30, help="max stations shown in ranking (0=all)")
    ap.add_argument("--mad-k", type=float, default=3.0, help="outlier threshold: median + k x MAD")
    ap.add_argument("--capacity", default=None, help='per-station capacity "st1:500,st2:5", default uses peak as proxy')
    ap.add_argument("--info-csv", "--info", dest="info_csv", default=None,
                    help="CSV with per-station GCCAPCITY/GCCAPACITY (join on --station-col when present, else "
                         "auto-detected by value match, e.g. plantid/plantname/plant_pointname). Adds GCCAPCITY + 南网 "
                         "nanwang_official_power (+ x1.4/x1.2/x0.8/x0.6/x0.4 factor-scan columns) + city to "
                         "fleet_ranking.csv, and nanwang_official_power_cf when --counterfactual is on")
    ap.add_argument("--hist-root", default=None,
                    help="南网 IN 侧原始可用功率宽表的根目录，指到「含日期文件夹」那一层，例 "
                         ".../products/data/qy/63/1002；每站按 "
                         "{root}/{YYYY-MM-DD}/IN/{plantid}/DQYC_IN_HISTORY_AVAIL_POWER_WIDE.txt 读，"
                         "plantid 取站名末尾连续数字（plant_guangfu1358 -> 1358）。给了就在左下历史功率面板上"
                         "叠一条原始线（主表 observe_power 是调整后的），两条线裁到同一起止")
    ap.add_argument("--hist-tjlx", type=int, default=1,
                    help="原始宽表取哪种统计类型：0-调度端 1-场站端 2-agc限电标志位（默认 1）")
    ap.add_argument("--ghi-pred", default="GHI_SOLARGIS_predict", help="predicted column for overview scatter/GHI ranking")
    ap.add_argument("--ghi-true", default="GHI_real_future", help="truth column for overview scatter/GHI ranking")
    ap.add_argument("--station-col", default="station")
    ap.add_argument("--date", default=None, help="起报日 YYYY-MM-DD；缺省取 timestamp_win 最早日期并播报")
    ap.add_argument("--pred-col-template", default="predict_power_{station}",
                    help='预测表列名模板，{station} 占位，如 "{station}" 或 "predict_power_{station}"')
    ap.add_argument("--win-col", default="timestamp_win")
    ap.add_argument("--power-col", default="observe_power_future")
    ap.add_argument("--dtime-col", default="dtime")
    ap.add_argument("--no-plots", action="store_true", help="no plots at all, still writes CSV")
    ap.add_argument("--no-station-plots", action="store_true", help="no per-station curves, still writes station-level CSV")
    ap.add_argument("--no-fleet", action="store_true", help="no overview and no fleet_ranking.csv")
    ap.add_argument("--worst-only", type=int, default=0,
                    help="draw images only for the worst N stations by power nRMSE (0=all; ranking uses the full "
                         "fleet, CSVs unchanged; counterfactual is unaffected -- inference always covers every "
                         "station in --cf-input)")
    ap.add_argument("--counterfactual", action="store_true",
                    help="counterfactual: swap GHI prediction to truth and re-predict via LOCAL inference.py, "
                         "decompose input's fault vs model's fault (needs the machine with Base/utils/checkpoints)")
    ap.add_argument("--cf-input", default=None,
                    help="inference-ready parquet fed to multi_station_inference (station/timestamp_win + all "
                         "model features + the --cf-swap pair). Default: reuse --input")
    ap.add_argument("--checkpoints-dir", default=None, help="模型 checkpoints 目录，传给 multi_station_inference")
    ap.add_argument("--config", default=None, help="模型 config（yaml 路径），传给 multi_station_inference")
    ap.add_argument("--inference-dir", default=None,
                    help="inference.py 所在目录（连同 Base/utils 依赖）；置于 sys.path 最前，避免被同名文件遮蔽")
    ap.add_argument("--forecasting-type", default="short", help="传给 multi_station_inference 的预测类型")
    ap.add_argument("--cf-show-local-base", action="store_true",
                    help="右下面板再加一条本地基线虚线（默认只入指标与复现闸，不画）")
    ap.add_argument("--cf-force", action="store_true",
                    help="ignore the cached inference results and re-run both passes")
    ap.add_argument("--cf-swap", default="GHI_SOLARGIS_predict:GHI_real_future",
                    help="pred:true comma-separated, multiple pairs allowed (multiple = joint replacement)")
    ap.add_argument("--cf-check-tol", type=float, default=1.0,
                    help="baseline reproduction gate: warn if the local baseline vs predict table nRMSE%% exceeds this")
    ap.add_argument("--cf-kt-scale", default=None,
                    help="K_t 乘性反事实：逗号分隔的缩放系数，如 \"0.8,0.9,1.1,1.2\"。每个 k 把预报 GHI 在"
                         "晴空指数空间乘 k（GHI' = clip(K_t*k, 0, --cf-kt-max) * GHI_cs）后重推一趟，看"
                         "「按比例缩放预报」能不能改善功率预测。需要 --info-csv 带 LATITUDE/LONGITUDE 列"
                         "（算 GHI_cs）与推理三件套（--checkpoints-dir/--config/--inference-dir）。"
                         "k=1.0 会被剔掉（那就是基线）；成本 = 系数个数 x 起报窗数 次推理")
    ap.add_argument("--cf-kt-col", default="GHI_SOLARGIS_predict",
                    help="--cf-kt-scale 缩放哪一列（应当就是模型吃的那个 GHI 预报列）")
    ap.add_argument("--cf-kt-max", type=float, default=1.2,
                    help="K_t 天花板：缩放后不许超过当时晴空辐照的这个倍数（默认 1.2，余量留给云增强）")
    ap.add_argument("--cf-kt-tz-offset", type=float, default=8.0,
                    help="表里时间戳相对 UTC 的小时数，用于算太阳位置（北京时间 = 8）。传错会让晴空曲线整体"
                         "平移，开跑前的 [kt] geometry check 会当场把它显示成几小时的偏差")
    ap.add_argument("--cf-kt-lines", action="store_true",
                    help="右下功率面板再把每个 k 的预测画成点线（默认只入指标与扫描图，不画）")
    args = ap.parse_args()
    step = args.kt_step = STEP
    feature_pairs = parse_feature_pairs(args.feature_pairs)
    cap_map = parse_capacity(args.capacity)
    kt_factors = parse_kt_factors(args.cf_kt_scale)

    if not args.predict and not (args.counterfactual or kt_factors):
        raise SystemExit("--predict is required unless --counterfactual / --cf-kt-scale is given "
                         "(with them, the local baseline inference supplies the predictions instead)")
    if kt_factors and not args.info_csv:
        raise SystemExit("--cf-kt-scale needs --info-csv with LATITUDE/LONGITUDE columns "
                         "(GHI_cs is computed from each station's own coordinates and the timestamp)")

    inp = pd.read_parquet(args.input)
    for c in (args.station_col, args.win_col, args.power_col):
        if c not in inp.columns:
            raise SystemExit(f"input table missing column '{c}'; actual columns: {list(inp.columns)[:30]}")
    inp[args.win_col] = pd.to_datetime(inp[args.win_col])

    pred = None                                    # None until read, or until the local baseline stands in
    if args.predict:
        pred = pd.read_parquet(args.predict)
        if args.dtime_col not in pred.columns:
            raise SystemExit(f"predict table missing column '{args.dtime_col}'; "
                             f"actual columns: {list(pred.columns)[:30]}")
        pred[args.dtime_col] = pd.to_datetime(pred[args.dtime_col])
        pred = pred.groupby(args.dtime_col).mean(numeric_only=True).sort_index()

    info_map = (load_station_info(args.info_csv, args.station_col, pd.unique(inp[args.station_col]))
                if args.info_csv else {})
    gccap_map = {k: v["gccap"] for k, v in info_map.items() if v["gccap"] is not None}
    city_map = {k: v["city"] for k, v in info_map.items() if v["city"] is not None}

    # Drop whole feature pairs that are globally missing (warn once)
    active_pairs = []
    for pcol, tcol, label in feature_pairs:
        miss = [c for c in (pcol, tcol) if c not in inp.columns]
        if miss:
            print(f"  [warn] feature plot '{label}' skipped: input table missing columns {miss}")
        else:
            active_pairs.append((pcol, tcol, label))
    have_ghi = args.ghi_pred in inp.columns and args.ghi_true in inp.columns
    if not have_ghi and not args.no_fleet:
        miss = [c for c in (args.ghi_pred, args.ghi_true) if c not in inp.columns]
        print(f"  [warn] overview GHI columns missing {miss} -> skip GHI ranking and scatter (power overview still output)")

    os.makedirs(args.out_dir, exist_ok=True)
    report_name, windows = compute_windows(inp, args.win_col, args.date)
    report_root = os.path.join(args.out_dir, report_name)
    os.makedirs(report_root, exist_ok=True)
    args.report_root = report_root

    # Counterfactual runs ONCE over every 起报 window before the slice loop: one window's 480-point output spans
    # 5 days, so D+1 and D+4 both draw from the same predictions and must not trigger inference twice.
    cf_base = cf_swap_pred = None
    kt_preds = {}
    swap_label = "GHI"
    if args.counterfactual or kt_factors:
        flag = "--counterfactual" if args.counterfactual else "--cf-kt-scale"
        missing = [f for f, v in (("--checkpoints-dir", args.checkpoints_dir),
                                  ("--config", args.config)) if not v]
        if missing:
            raise SystemExit(f"{flag} needs {', '.join(missing)} "
                             f"(passed straight to multi_station_inference)")
        swap = parse_cf_swap(args.cf_swap) if args.counterfactual else None
        if swap:
            swap_label = "+".join(p[: -len("_predict")] if p.endswith("_predict") else p for p in swap)
        coords = {}
        if kt_factors:
            coords = kt_coords_from_info(info_map, pd.unique(inp[args.station_col]))
            if not coords:
                raise SystemExit("--cf-kt-scale: no station has usable LATITUDE/LONGITUDE in --info-csv "
                                 "-- GHI_cs cannot be computed for anyone, nothing would be scaled")
            kt_geometry_check(inp, args, coords, step)
        cf_base, cf_swap_pred, kt_preds = cf_build_predictions(inp, args, swap, kt_factors, coords)
        if args.counterfactual and (cf_swap_pred is None or cf_swap_pred.empty):
            print("  [warn] counterfactual produced no swap predictions -> continuing without the oracle swap")
            cf_swap_pred = None
        kt_preds = {k: v for k, v in (kt_preds or {}).items() if v is not None and not v.empty}
        if kt_factors and not kt_preds:
            print("  [warn] --cf-kt-scale produced no predictions -> continuing without the K_t scan")
        if (cf_base is None or cf_base.empty) and (cf_swap_pred is not None or kt_preds):
            print("  [warn] local baseline inference produced nothing -> counterfactual layers dropped")
            cf_swap_pred, kt_preds = None, {}

    # No --predict: the local baseline stands in as the prediction source. It is already a
    # dtime x predict_power_<station> frame, so run_analysis consumes it unchanged -- only the
    # column template and the panel label change, and the reproduction gate is dropped (comparing
    # the baseline against itself would report a meaningless 0%).
    if pred is None:
        if cf_base is None or cf_base.empty:
            raise SystemExit("no --predict given and the local baseline inference produced nothing "
                             "-- cannot score anything; check --cf-input / --checkpoints-dir / --config")
        print("[counterfactual] no --predict given -> local baseline inference supplies the predictions "
              "(reproduction gate skipped: nothing independent to reproduce)")
        pred = cf_base
        args.pred_col_template = CF_PRED_COL_TEMPLATE
        args.cf_check_tol = None                   # None = gate disabled, distinct from a 0.0 threshold

    # Raw 可用功率 also loads ONCE: history is window-independent, so D+1 and D+4 share one pass over the txt.
    raw_hist = None
    if args.hist_root and not (args.no_plots or args.no_station_plots):   # 面板不画就别读 txt
        span = hist_span(inp, args.win_col, "observe_power", step)
        if span is None:
            print("  [warn] --hist-root given but the input table has no usable 'observe_power' history "
                  "lists -> nothing to align the raw line against, skipped")
        else:
            from pvcore import history_raw
            # 线长 = 所有起报窗 672 点摊平去重后的并集，起报日越多线越长；单起报日才恰好 7 天。
            # 文件夹数是「要开几个 txt」，跨度落在自然日边界内侧时比天数多 1，别把两者看成一回事。
            ndays = len(pd.date_range(span[0].normalize(), span[1].normalize(), freq="D"))
            nwin = int(pd.Series(inp[args.win_col].to_numpy()).nunique())
            print(f"  [hist-raw] span {span[0]:%Y-%m-%d %H:%M} -> {span[1]:%Y-%m-%d %H:%M} = "
                  f"{(span[1] - span[0]) / pd.Timedelta('1D') + 1 / 96:.1f} days "
                  f"(union of {nwin} 起报日; opening {ndays} date folder(s)), Tjlx={args.hist_tjlx}")
            raw_hist = history_raw.load_raw_history(
                args.hist_root, pd.unique(inp[args.station_col]), span[0], span[1], args.hist_tjlx)

    for label, start, end in windows:
        sub_out = os.path.join(report_root, label)
        os.makedirs(sub_out, exist_ok=True)
        run_analysis(inp, pred, args, step, active_pairs, have_ghi, cap_map, gccap_map, city_map,
                     sub_out, (start, end), label, cf_base, cf_swap_pred, swap_label, raw_hist,
                     kt_preds)


if __name__ == "__main__":
    main()
