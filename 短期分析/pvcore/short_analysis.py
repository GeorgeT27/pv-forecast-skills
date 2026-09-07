"""短期分析的编排层：一个窗口 [start,end) 的完整逐站 + 舰队流程，产物写进 out_dir。

一个起报窗的 480 点输出横跨 5 天，D+1 与 D+4 都从同一批预测里取，所以反事实推理与原始功率宽表
都在入口那边只跑一次，这里只消费传进来的结果。
"""
from __future__ import annotations

import os

import numpy as np
import pandas as pd

from .counterfactual import cf_kt_station, cf_report_summary, cf_station, kt_report_summary
from .inputs import resolve_pred_col
from .metrics import (flag_outliers, hourly_nrmse, nanwang_factor_row, resolve_cap, rmse)
from .plots_short import plot_cf_overview, plot_dashboard, plot_kt_scan, plot_station_combined
from .timeseries import (_aligned, _display, _display_multi, series_from_lists,
                         series_from_lists_history)

HISTORY_COLS = ["observe_power", "GHI_SOLARGIS"]  # historical (past-observed) list columns -> 2x2 left column

FLEET_CSV_DROP = ("delta_nrmse", "frac_explained")   # 纯派生列，只是不落盘；内存帧里还留着


def _fleet_csv(fdf):
    """把舰队帧整形成 fleet_ranking.csv 的落盘形态，三条规则：
      1. 丢掉 delta_nrmse、frac_explained、以及每个 k 的 delta_nrmse_kt<k>。它们都能由留下的列一步
         算回（delta = power_nrmse_localbase - power_nrmse_cf，frac = delta / localbase x 100），
         但内存帧里必须留着：counterfactual_overview.png 与终端的反事实结论都直接读这两列。
      2. --cf-kt-scale 产的列（power_nrmse_kt<k> / nanwang_official_power_kt<k> / kt_best_*）一律挪到
         最末。power_nrmse_localbase 不跟着走，它是反事实与 K_t 两个块共同的参照基线。
      3. 有 nanwang_official_power 就恒按它从小到大排，准确率最低的站排最前；没有该列（没给
         --info-csv 或全站缺 GCCAPCITY）时退回 power_nrmse 降序。两种排法都把值缺失的站放到最后。"""
    d = fdf.drop(columns=[c for c in FLEET_CSV_DROP if c in fdf.columns])
    d = d.drop(columns=[c for c in d.columns if c.startswith("delta_nrmse_kt")])
    kt = [c for c in d.columns
          if c.startswith(("power_nrmse_kt", "nanwang_official_power_kt", "kt_best_"))]
    if kt:
        d = d[[c for c in d.columns if c not in kt] + kt]
    if "nanwang_official_power" in d.columns:
        return d.sort_values("nanwang_official_power", ascending=True, na_position="last")
    if "power_nrmse" in d.columns:
        return d.sort_values("power_nrmse", ascending=False, na_position="last")
    return d.sort_values("station")


def run_analysis(inp, pred, args, step, active_pairs, have_ghi, cap_map, gccap_map, city_map,
                 out_dir, win, label, cf_base=None, cf_swap_pred=None, swap_label="GHI", raw_hist=None,
                 kt_preds=None):
    """对单个窗口 [start,end)（label='D+1'/'D+4'，用于日志前缀）跑完整的每站 + 舰队分析，产物写入 out_dir。
    gccap_map={station: GCCAPCITY}（来自 --info-csv）时补 GCCAPCITY + nanwang_official_power 列，
    fleet_ranking.csv 另加 NANWANG_FACTORS 的 factor 扫描列；city_map={station: city} 时 fleet_ranking.csv 补 city 列。
    cf_base/cf_swap_pred（本地推理的基线与换真值预测，dtime×predict_power_<站>）给出时，右下功率面板加画反事实线，
    fleet_ranking.csv/station_power_rmse.csv 补 power_*_cf、nanwang_official_power_cf。
    kt_preds={k: 预测帧}（--cf-kt-scale 的每个缩放系数一趟）给出时，fleet_ranking.csv 末尾补
    power_nrmse_kt<k>/nanwang_official_power_kt<k> 与 kt_best_factor/kt_best_gain，另出
    counterfactual_kt_scan.png。fleet_ranking.csv 的落盘列与列序见 _fleet_csv。
    raw_hist={station: Series}（来自 --hist-root 的南网原始可用功率宽表）给出时，左下历史功率面板加画原始线。"""
    pfx = f"[{label}] " if label else ""
    plot_station = not (args.no_plots or args.no_station_plots)
    stations = list(pd.unique(inp[args.station_col]))
    gccap_map = gccap_map or {}
    city_map = city_map or {}
    missing_gccap = set()
    power_rows, feat_rows, imgs = [], [], []
    fleet_recs, hourly = [], {}
    plot_jobs = []              # (st, panels) combined 2x2 plots deferred: --worst-only must rank the fleet first
    if plot_station:
        for c in HISTORY_COLS:
            if c not in inp.columns:
                print(f"  {pfx}[warn] history column '{c}' missing from input table -> that panel shows 'no data'")

    for st in stations:
        sub = inp[inp[args.station_col] == st]
        wins = sub[args.win_col].to_numpy()
        cache = {}

        def ser(col):                                 # per-station column memoization: flatten each column only once
            if col not in cache:
                cache[col] = series_from_lists(wins, sub[col].to_numpy(), step)
            return cache[col]

        rec = {"station": st}
        ct = city_map.get(str(st))
        if ct is not None:
            rec["city"] = ct
        gc = gccap_map.get(str(st)) if gccap_map else None    # GCCAPCITY for 南网 nanwang_official metric
        if gccap_map and gc is None:
            missing_gccap.add(str(st))
        if gc is not None and gc > 0:
            rec["GCCAPCITY"] = round(float(gc), 4)
        panels = {"hist_ghi": None, "hist_pw": None, "win_ghi": None, "win_pw": None}

        # ---- Power (prediction from predict table) ----
        truth = ser(args.power_col)
        col = resolve_pred_col(st, pred, args.pred_col_template)
        if col is None:
            print(f"  [warn] station {st}: predict table has no column "
                  f"'{args.pred_col_template.format(station=st)}', skip Power plot")
        else:
            al = _aligned(truth, pred[col].dropna(), args.drop_night, args.night_end_hour, win)
            if al is None:
                print(f"  [warn] station {st}: Power truth/pred have no common time points (or all removed as night), skipped")
                if cf_swap_pred is not None:
                    rec["cf_status"] = "no_overlap"   # no truth to score against -> say so rather than leave blank
            else:
                times, t, p = al
                rv = rmse(p, t)
                nwrow = {}                                    # 南网 official accuracy + factor 扫描: ALL window points (night incl.), floored by 0.2*GCCAPCITY
                if gc is not None and gc > 0:
                    al_all = _aligned(truth, pred[col].dropna(), False, args.night_end_hour, win)
                    if al_all is not None:
                        nwrow = nanwang_factor_row(al_all[1], al_all[2], gc)
                nw = nwrow.get("nanwang_official_power")
                prow = {"station": st, "power_rmse": round(rv, 6),
                        "n_points": int(len(times)),
                        "t_start": str(times.min()), "t_end": str(times.max())}
                if nw is not None:
                    prow["nanwang_official_power"] = nw     # station_power_rmse.csv 只留官方口径，不带 factor 列
                # Capacity first: both the counterfactual decomposition and the nRMSE columns below need it
                cap = resolve_cap(cap_map.get(str(st)) or cap_map.get(st), t)

                # ---- Counterfactual (local inference): extra panel line + decomposition vs the LOCAL baseline ----
                extra_lines = []
                if cf_swap_pred is not None:
                    cfrow, extra_lines = cf_station(st, truth, pred[col].dropna(), cf_base, cf_swap_pred,
                                                    args, cap, win, gc, swap_label)
                    rec.update(cfrow)
                    prow.update({k: v for k, v in cfrow.items()
                                 if k in ("cf_status", "power_rmse_cf", "power_nrmse_cf",
                                          "nanwang_official_power_cf")})
                # ---- K_t 乘性扫描：每个 k 与本地基线在同一三方交集上比 ----
                if kt_preds:
                    ktrow, kt_lines = cf_kt_station(st, truth, cf_base, kt_preds, args, cap, win, gc)
                    rec.update(ktrow)
                    extra_lines = extra_lines + kt_lines
                power_rows.append(prow)

                if plot_station:
                    got = _display_multi(truth, [pred[col].dropna()] + [e[0] for e in extra_lines],
                                         args.drop_night, args.night_end_hour, win)
                    if got is None:                       # no displayable union: fall back to the scored points
                        dt_, dtruth, dothers = times, t, [p] + [np.zeros(len(times))] * len(extra_lines)
                    else:
                        dt_, dtruth, dothers = got
                    panels["win_pw"] = ("Power", dt_, dtruth, dothers[0], rv, int(len(times)),
                                        "observed power",
                                        "local baseline (original features)" if args.cf_check_tol is None
                                        else "predicted power",
                                        [(vals, lab, color, ls, note) for vals, (_, lab, color, ls, note)
                                         in zip(dothers[1:], extra_lines)])
                # Overview: power nRMSE / bias / hourly
                rec.update(power_rmse=round(rv, 4), power_nrmse=round(rv / cap * 100, 4),
                           power_bias_pct=round(float(np.mean(p - t)) / cap * 100, 4),
                           capacity=round(cap, 4), n_points=int(len(times)))
                rec.update(nwrow)                          # 插入顺序 = fleet_ranking.csv 列顺序：x1.4 / x1.2 / 官方 / x0.8 / x0.6 / x0.4
                hourly[st] = hourly_nrmse(times, p - t, cap)

        # ---- Per-station feature metrics (prediction and truth both in input); first pair feeds the GHI panel ----
        for pcol, tcol, flabel in active_pairs:
            pser, tser = ser(pcol), ser(tcol)
            if pser.empty or tser.empty:
                print(f"  [warn] station {st}: feature '{flabel}' data missing/empty for this station, skipped (does not affect other plots)")
                continue
            al = _aligned(tser, pser, args.drop_night, args.night_end_hour, win)
            if al is None:
                print(f"  [warn] station {st}: feature '{flabel}' has no common time points, skipped")
                continue
            times, tv, pv = al
            rv = rmse(pv, tv)
            feat_rows.append({"station": st, "feature": flabel, "rmse": round(rv, 6),
                              "n_points": int(len(times))})
            if plot_station and panels["win_ghi"] is None:
                disp = _display(tser, pser, args.drop_night, args.night_end_hour, win) \
                       or (times, tv, pv)
                panels["win_ghi"] = (flabel, disp[0], disp[1], disp[2], rv, int(len(times)),
                                     f"{tcol} (true)", f"{pcol} (pred)")

        # ---- History panels: ALL history points (backward lists; no window / night restriction) ----
        if plot_station:
            for key, hcol in (("hist_ghi", "GHI_SOLARGIS"), ("hist_pw", "observe_power")):
                if hcol in inp.columns:
                    hs = series_from_lists_history(wins, sub[hcol].to_numpy(), step)
                    if not hs.empty:
                        panels[key] = (hcol, hs.index, hs.to_numpy())
                        # 原始可用功率（--hist-root）叠成第二条线；裁到和调整后那条一样的起止 = 时间对齐
                        raw = (raw_hist or {}).get(str(st)) if key == "hist_pw" else None
                        if raw is not None and raw.notna().any():
                            raw = raw[(raw.index >= hs.index.min()) & (raw.index <= hs.index.max())]
                            if raw.notna().any():          # 裁完只剩 NaN 就别加图例了，画不出线
                                panels[key] += ([(raw.index, raw.to_numpy(),
                                                  f"raw avail power (Tjlx={args.hist_tjlx})",
                                                  "#ff7f0e", "--")],)
            if any(v is not None for v in panels.values()):
                plot_jobs.append((st, panels))

        # ---- Overview: GHI nRMSE (scatter/GHI ranking; use specified columns, reuse cache to avoid re-flatten) ----
        if have_ghi and not args.no_fleet:
            gp, gt = ser(args.ghi_pred), ser(args.ghi_true)
            if not gp.empty and not gt.empty:
                al = _aligned(gt, gp, args.drop_night, args.night_end_hour, win)
                if al is not None:
                    _, tvg, pvg = al
                    gcap = resolve_cap(None, tvg)
                    gr = rmse(pvg, tvg)
                    rec.update(ghi_rmse=round(gr, 4), ghi_nrmse=round(gr / gcap * 100, 4))
        fleet_recs.append(rec)

    if missing_gccap:
        print(f"  {pfx}[warn] --info-csv has no GCCAPCITY for {len(missing_gccap)} station(s) "
              f"{sorted(missing_gccap)[:10]}{' ...' if len(missing_gccap) > 10 else ''} "
              "-> nanwang_official_power left blank for them")

    # ---------------- --worst-only: rank on the full fleet, then draw only the worst N ----------------
    fdf = pd.DataFrame(fleet_recs)
    sel = None                                        # None = draw every station
    if args.worst_only > 0:
        if "power_nrmse" in fdf.columns and np.isfinite(fdf["power_nrmse"]).any():
            ranked = fdf[np.isfinite(fdf["power_nrmse"])].sort_values("power_nrmse", ascending=False)
            sel = set(ranked.head(args.worst_only)["station"])
            print(f"  [worst-only] images restricted to worst {len(sel)} stations by power nRMSE: "
                  f"{[str(s) for s in ranked.head(args.worst_only)['station']]}  (CSVs still cover all)")
        else:
            print("  [warn] --worst-only: no station has power nRMSE (cannot rank) -> drawing all stations")
    for st, panels in plot_jobs:
        if sel is not None and st not in sel:
            continue
        imgs.append(plot_station_combined(st, label or "window", panels["hist_ghi"], panels["hist_pw"],
                                          panels["win_ghi"], panels["win_pw"], out_dir, args.tick_hours))

    # ---------------- Station-level CSV ----------------
    if power_rows:
        pw = pd.DataFrame(power_rows).sort_values("power_rmse", ascending=False)
        pw.to_csv(os.path.join(out_dir, "station_power_rmse.csv"), index=False)
    if feat_rows:
        pd.DataFrame(feat_rows).sort_values(["feature", "rmse"], ascending=[True, False]).to_csv(
            os.path.join(out_dir, "station_feature_rmse.csv"), index=False)

    # ---------------- Fleet overview ----------------
    fleet_img = None
    if not args.no_fleet and ("power_nrmse" in fdf.columns or "ghi_nrmse" in fdf.columns):
        if "power_nrmse" in fdf.columns:
            fdf["power_outlier"] = flag_outliers(fdf["power_nrmse"].to_numpy(), args.mad_k)
            fdf["power_rank"] = fdf["power_nrmse"].rank(ascending=False, method="min").astype("Int64")
        _fleet_csv(fdf).to_csv(os.path.join(out_dir, "fleet_ranking.csv"), index=False)
        if not args.no_plots:
            ddf = fdf if sel is None else fdf[fdf["station"].isin(sel)]
            dh = hourly if sel is None else {s: h for s, h in hourly.items() if s in sel}
            note = "" if sel is None else f"   [focused on worst {len(ddf)} of {len(fdf)} stations]"
            fleet_img = plot_dashboard(ddf, dh, have_ghi, args, out_dir, note)

    # ---------------- Counterfactual fleet decomposition (same records, decomposition vocabulary) ----------------
    if cf_swap_pred is not None and "cf_status" in fdf.columns:
        okd = fdf[fdf["cf_status"].isin(["ok", "baseline_mismatch"])].rename(
            columns={"power_nrmse_localbase": "nrmse_base", "power_nrmse_cf": "nrmse_cf",
                     "cf_status": "status"})
        if not okd.empty:
            if not args.no_plots:
                plot_cf_overview(okd, out_dir, swap_label)
            cf_report_summary(okd, swap_label, pfx)

    # ---------------- K_t 乘性扫描的舰队视图 ----------------
    kt_img = None
    if kt_preds and "kt_best_factor" in fdf.columns:
        factors = sorted(kt_preds)
        if not args.no_plots:
            kt_img = plot_kt_scan(fdf, out_dir, factors, args.cf_kt_max, args.cf_kt_col)
        kt_report_summary(fdf, factors, pfx)

    if not power_rows and not feat_rows and fleet_img is None:
        print(f"  {pfx}[warn] nothing could be produced for this window "
              f"(check predict_power_{{station}} columns exist and times align).")
        return

    # ---------------- Terminal summary ----------------
    print(f"{pfx}[station_analysis] stations x{len(stations)}   feature pairs {[p[2] for p in active_pairs] or 'none'}   "
          f"drop_night={args.drop_night}   -> {out_dir}/")
    if power_rows:
        print("  Per-station Power RMSE (absolute, for detail):")
        print(pw.to_string(index=False))
    if not args.no_fleet and "power_nrmse" in fdf.columns:
        top = fdf[np.isfinite(fdf.power_nrmse)].sort_values("power_nrmse", ascending=False)
        print("  Fleet power nRMSE most-off Top (%, comparable only after normalization):")
        for _, r in top.head(5).iterrows():
            tag = "  [warn]outlier" if r.get("power_outlier") else ""
            print(f"    {r.station}: {r.power_nrmse:.2f}%  (RMSE={r.power_rmse:.2f}, "
                  f"bias={r.get('power_bias_pct', float('nan')):+.2f}%){tag}")
        outs = top[top.power_outlier == True]["station"].tolist() if "power_outlier" in top else []
        if outs:
            print(f"  [warn] outlier stations (clearly above the fleet): {outs}")
    prod = []
    if imgs:
        prod.append(f"station_<站>.png combined 2x2 plots x{len(imgs)}")
    if power_rows:
        prod.append("station_power_rmse.csv")
    if feat_rows:
        prod.append("station_feature_rmse.csv")
    if not args.no_fleet and ("power_nrmse" in fdf.columns or "ghi_nrmse" in fdf.columns):
        prod.append("fleet_ranking.csv")
    if fleet_img:
        prod.append("fleet_overview.png")
    if kt_img:
        prod.append("counterfactual_kt_scan.png")
    print(f"  {pfx}Products: " + ("  + ".join(prod) if prod else "none"))


def compute_windows(inp, win_col, date_arg):
    """起报日 D：--date 显式给定，否则取 timestamp_win 最早日期并播报；切 [D+1 00:00,+24h) 与 [D+4 00:00,+24h)。"""
    if date_arg:
        D = pd.Timestamp(date_arg).normalize()
    else:
        D = pd.Timestamp(inp[win_col].min()).normalize()
        print(f"  [short] --date not given; using D = {D:%Y-%m-%d} (from earliest {win_col})")
    day = pd.Timedelta(days=1)
    d1, d4 = D + day, D + 4 * day
    return D.strftime("%Y%m%d"), [("D+1", d1, d1 + day), ("D+4", d4, d4 + day)]
