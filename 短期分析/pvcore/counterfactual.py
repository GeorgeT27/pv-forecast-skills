"""反事实：改一件输入、经本地 inference.py 重推一遍，看模型的预测跟着变多少。

两种改法，可以同开：
  oracle swap（--counterfactual）  把预报气象整列换成真值 —— 分解「输入的错」与「模型的错」，
                                   回答「就算气象报准了，还剩多少误差」。
  K_t 乘性扫描（--cf-kt-scale）    把预报 GHI 在晴空指数空间乘一个 k 再放回去 —— 回答
                                   「预报 GHI 是不是系统性偏高/偏低，按比例缩放能不能变好」。
                                   走 K_t 而不是直接乘，是为了拿 GHI_cs 当时变天花板：k>1 时
                                   不让任何一点冲出「当时晴空的 kt_max 倍」这条物理边界（那种值
                                   模型也没见过，喂进去测的就不再是缩放本身了）。见 solar.scale_in_kt。

所有趟共用同一批行（cf_usable_rows 先筛过）、逐趟缓存 parquet，所以打分永远是同点集比较，
重跑或加一个 k 都只推缺的那趟。
"""
from __future__ import annotations

import os
import sys

import numpy as np
import pandas as pd

from .metrics import cf_decomposition, nrmse_pct, rmse
from .solar import check_alignment, check_coords, clear_sky_ghi, scale_in_kt
from .timeseries import _aligned, _fillna0, _has_nan, _listlen

CF_PRED_COL_TEMPLATE = "predict_power_{station}"   # inference.py hardcodes this; --pred-col-template governs
                                                   # only the --predict table and must not be applied here


def parse_cf_swap(spec):
    """"pred:true[,pred2:true2]" -> {pred col: truth col}. Multiple pairs = joint replacement."""
    out = {}
    for item in spec.split(","):
        p, _, t = item.partition(":")
        p, t = p.strip(), t.strip()
        if not p or not t:
            raise SystemExit(f"--cf-swap item format should be pred:true, got '{item}'")
        out[p] = t
    return out


def cf_load_inference(inference_dir):
    """Import multi_station_inference lazily so the rest of the script still runs on machines without the
    model stack. inference_dir goes to sys.path FRONT: this script's own directory is sys.path[0] and may
    hold a same-named inference.py, which would otherwise shadow the one the user pointed at."""
    if inference_dir:
        sys.path.insert(0, os.path.abspath(inference_dir))
    try:
        from inference import multi_station_inference
    except ImportError as e:
        raise SystemExit(
            f"--counterfactual needs inference.py importable (multi_station_inference): {e}\n"
            f"  point --inference-dir at the directory holding inference.py + its Base/utils deps.")
    return multi_station_inference


def cf_check_swap_consumed(config_path, swap):
    """Best-effort pre-flight: if utils.get_past_future_cols is importable (i.e. we are on the model machine),
    warn when a swapped column is not among the model's future inputs -- swapping it would then be a no-op.
    Silent when utils or the config cannot be read: this is a warning, never a gate."""
    try:
        from utils import get_past_future_cols, load_config
    except ImportError:
        return
    try:
        cfg = load_config(config_path) if isinstance(config_path, str) else config_path
        _, future_list, extra_list, _ = get_past_future_cols(cfg)
    except Exception as e:                            # noqa: BLE001 -- config shapes vary; never block on it
        print(f"  [warn] counterfactual: cannot read model feature list from config ({e}), swap check skipped")
        return
    known = set(future_list or []) | set(extra_list or [])
    unused = [p for p in swap if p not in known]
    if unused:
        print(f"  [warn] counterfactual: {unused} not in the model's future/extra feature list -- "
              f"swapping it will not change the prediction. Check --cf-swap against your config.")


def cf_usable_rows(cf_inp, swap, station_col, win_col):
    """Keep only rows the swap can actually be performed on: every (pred, truth) pair present, non-empty and
    the same length. Feeding a None cell to the model crashes it, and a length-mismatched truth would silently
    change the row's horizon -- both get dropped before inference, not discovered inside it. NaN hiding inside
    an otherwise valid-length list is filled with 0.0 in place instead of dropping the row: these are GHI-like
    series (non-negative, 0 at night), so 0.0 is a physically sane stand-in and would otherwise only surface as
    a crash inside the model's own data_check mid-window."""
    ok = np.ones(len(cf_inp), dtype=bool)
    reasons = {}
    for pcol, tcol in swap.items():
        pcol_idx, tcol_idx = cf_inp.columns.get_loc(pcol), cf_inp.columns.get_loc(tcol)
        for i, (pv, tv) in enumerate(zip(cf_inp[pcol].to_numpy(), cf_inp[tcol].to_numpy())):
            lp, lt = _listlen(pv), _listlen(tv)
            if lp == 0 or lt == 0:
                ok[i] = False
                reasons.setdefault("empty", set()).add(str(cf_inp[station_col].iloc[i]))
            elif lp != lt:
                ok[i] = False
                reasons.setdefault("length", set()).add(str(cf_inp[station_col].iloc[i]))
            elif _has_nan(pv) or _has_nan(tv):
                reasons.setdefault("nan", set()).add(str(cf_inp[station_col].iloc[i]))
                cf_inp.iat[i, pcol_idx] = _fillna0(pv)
                cf_inp.iat[i, tcol_idx] = _fillna0(tv)
    if "empty" in reasons:
        print(f"  [warn] counterfactual: dropping rows with empty {list(swap)} / truth cells "
              f"(stations {sorted(reasons['empty'])[:10]}) -- they get cf_status=missing, 0 inference calls")
    if "length" in reasons:
        print(f"  [warn] counterfactual: dropping rows where the truth column length != forecast length "
              f"(stations {sorted(reasons['length'])[:10]}) -- swapping would change the horizon")
    if "nan" in reasons:
        print(f"  [warn] counterfactual: filled NaN points with 0.0 inside otherwise valid-length {list(swap)} / "
              f"truth cells (stations {sorted(reasons['nan'])[:10]}) -- row kept, not dropped")
    return cf_inp[ok]


def cf_infer_windows(cf_inp, args, infer_fn, swap=None, label="", transform=None):
    """Run local inference over every 起报 window of cf_inp -> dtime-indexed frame of predict_power_<站> columns.
    One call per window with all that window's stations, which is exactly what multi_station_inference asserts
    (station unique + single timestamp_win). swap={pred_col: truth_col} replaces the forecast with its truth
    before predicting; swap=None reproduces the baseline from the same checkpoints.
    transform(sub, win_time) 是另一种改法：就地改这一窗的特征（K_t 缩放走这条），swap 之后执行。
    Frames are copied because multi_station_inference mutates the caller's dataframe in place."""
    outs = []
    wins = list(cf_inp.groupby(args.win_col, sort=True))
    print(f"[counterfactual] {label}: {len(wins)} window(s) x 1 call each")
    for wt, g in wins:
        # reset_index is NOT cosmetic: inference.py merges model outputs with pd.concat(..., axis=1),
        # which aligns on index. A groupby subset carries the source table's sparse index ([0,10,20,...]),
        # which would misalign against the model's fresh RangeIndex and silently produce NaN rows.
        # read_parquet always yields 0..N-1, so hand the model exactly that.
        sub = g.copy().reset_index(drop=True)
        if sub[args.station_col].duplicated().any():
            dup = sorted(set(sub[args.station_col][sub[args.station_col].duplicated()].astype(str)))
            print(f"  [warn] window {wt}: duplicate stations {dup} in --cf-input, keeping the first row of each")
            sub = sub.drop_duplicates(subset=[args.station_col], keep="first")
        if swap:
            for pcol, tcol in swap.items():
                sub[pcol] = sub[tcol]
        if transform is not None:
            transform(sub, wt)
        res = infer_fn(sub, None, args.checkpoints_dir, args.forecasting_type, args.config)
        if res is None or len(res) == 0:
            print(f"  [warn] window {wt}: inference returned nothing, skipped")
            continue
        outs.append(res)
    if not outs:
        return pd.DataFrame()
    out = pd.concat(outs, axis=0, ignore_index=True)
    out[args.dtime_col] = pd.to_datetime(out[args.dtime_col])
    return out.groupby(args.dtime_col).mean(numeric_only=True).sort_index()


def cf_build_predictions(inp, args, swap=None, kt_factors=(), coords=None):
    """Local inference passes over --cf-input, each cached to its own parquet beside the report.
    -> (base_df, swap_df|None, {k: df})；任何一项都可能为空。
    swap=None 时不跑换真值那趟；kt_factors 每个 k 一趟。缓存逐趟判定，所以补一个新的 k 只推那一趟，
    --cf-force 则全部重推。"""
    root = args.report_root
    jobs = [("base", os.path.join(root, "cf_base_pred.parquet"), "baseline pass (original features)")]
    if swap:
        jobs.append(("swap", os.path.join(root, "cf_swap_pred.parquet"),
                     "swap pass (" + ", ".join(f"{p}->{t}" for p, t in swap.items()) + ")"))
    for k in kt_factors:
        jobs.append((("kt", k), os.path.join(root, f"cf_kt_{k:g}_pred.parquet"),
                     f"K_t scale pass (x{k:g} on {args.cf_kt_col})"))

    got, todo = {}, []
    for key, path, label in jobs:
        if not args.cf_force and os.path.exists(path):
            got[key] = pd.read_parquet(path).sort_index()
        else:
            todo.append((key, path, label))

    def assemble():
        return (got.get("base", pd.DataFrame()), got.get("swap"),
                {k: got[("kt", k)] for k in kt_factors if ("kt", k) in got})

    if not todo:
        print(f"[counterfactual] cache hit -> {len(jobs)} pass(es) under {root} "
              f"(0 inference calls; --cf-force to redo)")
        return assemble()

    cf_path = args.cf_input or args.input
    cf_inp = pd.read_parquet(cf_path)
    for c in (args.station_col, args.win_col):
        if c not in cf_inp.columns:
            raise SystemExit(f"--cf-input '{cf_path}' missing column '{c}'; "
                             f"actual columns: {list(cf_inp.columns)[:30]}")
    need = sorted({c for pair in (swap or {}).items() for c in pair}
                  | ({args.cf_kt_col} if kt_factors else set()))
    miss = [c for c in need if c not in cf_inp.columns]
    if miss:
        raise SystemExit(f"--cf-input '{cf_path}' missing counterfactual columns {miss}; "
                         f"actual columns: {list(cf_inp.columns)[:30]}")
    cf_inp[args.win_col] = pd.to_datetime(cf_inp[args.win_col])
    # 无 swap 时也要过一遍可用性：K_t 缩放同样吃不了空单元格 / 内嵌 NaN
    guard = dict(swap) if swap else {args.cf_kt_col: args.cf_kt_col}
    cf_inp = cf_usable_rows(cf_inp, guard, args.station_col, args.win_col)   # 同一批行喂给每一趟
    if cf_inp.empty:
        print("  [warn] counterfactual: no row in --cf-input is usable, skipping inference entirely")
        return pd.DataFrame(), (pd.DataFrame() if swap else None), {}
    print(f"[counterfactual] cf-input {cf_path}: {len(cf_inp)} rows, "
          f"{cf_inp[args.station_col].nunique()} stations, {cf_inp[args.win_col].nunique()} windows; "
          f"{len(todo)} pass(es) to run x {cf_inp[args.win_col].nunique()} window(s) = "
          f"{len(todo) * cf_inp[args.win_col].nunique()} inference call(s)")

    if swap:
        cf_check_swap_consumed(args.config, swap)
    infer_fn = cf_load_inference(args.inference_dir)
    for key, path, label in todo:
        if key == "base":
            df = cf_infer_windows(cf_inp, args, infer_fn, None, label)
        elif key == "swap":
            df = cf_infer_windows(cf_inp, args, infer_fn, swap, label)
        else:
            k = key[1]
            stats = {"clip": 0, "day": 0, "skip": set()}
            df = cf_infer_windows(cf_inp, args, infer_fn, None, label,
                                  transform=_kt_transform(args, coords or {}, k, stats))
            _kt_report(k, stats, args)
        got[key] = df
        if not df.empty:
            df.to_parquet(path)

    base, cf = got.get("base", pd.DataFrame()), got.get("swap")
    if base is not None and not base.empty and cf is not None and not cf.empty:
        shared = [c for c in base.columns if c in cf.columns]
        if shared and base[shared].reindex(cf.index).equals(cf[shared]):
            print("  [warn] counterfactual: baseline and swapped predictions are IDENTICAL -- the model did not "
                  "react to the swap. Either it does not consume the swapped column (check --cf-swap against "
                  "your config's feature list) or it is insensitive to it. Any delta below is meaningless.")
    return assemble()


# ================================================================ K_t 乘性扫描
def parse_kt_factors(spec):
    """"0.8,0.9,1.1,1.2" -> [0.8, 0.9, 1.1, 1.2]（去重升序）。1.0 会被剔掉并说明原因：
    那一趟就是基线，已经推过了，再推一遍纯属白花钱。"""
    if not spec:
        return []
    out = set()
    for item in spec.split(","):
        item = item.strip()
        if not item:
            continue
        try:
            v = float(item)
        except ValueError:
            raise SystemExit(f"--cf-kt-scale item should be a number, got '{item}'")
        if v <= 0:
            raise SystemExit(f"--cf-kt-scale must be positive, got {v} (k<=0 would zero out the whole forecast)")
        if v == 1.0:
            print("  [kt] factor 1.0 dropped -- that pass IS the baseline, which always runs")
            continue
        out.add(v)
    return sorted(out)


def kt_coords_from_info(info_map, stations, verbose=True):
    """{站: (lat, lon)}，只留坐标体检过关的站。info.csv 没有经纬度列时返回 {}，调用方据此关掉扫描。"""
    coords, bad = {}, []
    for st in stations:
        rec = info_map.get(str(st)) or {}
        lat, lon = rec.get("lat"), rec.get("lon")
        if check_coords(lat, lon, st, verbose):
            coords[str(st)] = (float(lat), float(lon))
        else:
            bad.append(str(st))
    if bad and verbose:
        print(f"  [warn] --cf-kt-scale: {len(bad)} station(s) have no usable LATITUDE/LONGITUDE in --info-csv "
              f"{sorted(bad)[:10]}{' ...' if len(bad) > 10 else ''} -> their GHI is left unscaled "
              f"(they will show a flat scan curve; that is missing coordinates, not model insensitivity)")
    return coords


def _kt_transform(args, coords, k, stats):
    """-> transform(sub, win_time)：就地把这一窗每行 args.cf_kt_col 的 list 在 K_t 空间乘 k。
    list 第 j 个元素落在 起报时刻 + 15min*(j+1)（与 series_from_lists 同一约定），晴空曲线就按这些
    绝对时刻算。没坐标的站原样放行 —— 缩不了就别缩，绝不拿别人的坐标凑。"""
    def transform(sub, win_time):
        col_idx = sub.columns.get_loc(args.cf_kt_col)
        t0 = pd.Timestamp(win_time)
        for i, (st, cell) in enumerate(zip(sub[args.station_col].to_numpy(),
                                           sub[args.cf_kt_col].to_numpy())):
            c = coords.get(str(st))
            if c is None:
                stats["skip"].add(str(st))
                continue
            arr = np.asarray(cell, dtype=float).ravel()
            if arr.size == 0:
                continue
            times = pd.date_range(t0 + args.kt_step, periods=arr.size, freq=args.kt_step)
            cs = clear_sky_ghi(times, c[0], c[1], args.cf_kt_tz_offset)
            new, n_clip, n_day = scale_in_kt(arr, cs, k, args.cf_kt_max)
            sub.iat[i, col_idx] = new.tolist()
            stats["clip"] += n_clip
            stats["day"] += n_day
    return transform


def _kt_report(k, stats, args):
    day, clip = stats["day"], stats["clip"]
    pct = f" ({clip / day * 100:.1f}% of daytime points)" if day else ""
    print(f"  [kt] x{k:g}: {clip} point(s) hit the K_t<={args.cf_kt_max:g} ceiling{pct}"
          + ("  -- ceiling never fired, this pass is a plain multiplicative scale"
             if clip == 0 else "  -- those points were held at kt_max x GHI_cs"))
    if stats["skip"]:
        print(f"  [kt] x{k:g}: {len(stats['skip'])} station(s) left unscaled for want of coordinates")


def kt_geometry_check(inp, args, coords, step):
    """开工前先体检一次时区与坐标：拿一个有坐标的站的历史 GHI 摊平，比它的日峰值时刻和真太阳正午。
    时区传错 8 小时、经纬度串了列，都会在这里显示成几小时的偏差。只播报，不拦。"""
    from .timeseries import series_from_lists_history
    if not coords or "GHI_SOLARGIS" not in inp.columns:
        return
    for st, (lat, lon) in coords.items():
        sub = inp[inp[args.station_col].astype(str) == st]
        if sub.empty:
            continue
        s = series_from_lists_history(sub[args.win_col].to_numpy(), sub["GHI_SOLARGIS"].to_numpy(), step)
        if s.empty:
            continue
        check_alignment(s.index, s.to_numpy(), lat, lon, args.cf_kt_tz_offset, f"station {st}")
        return                                    # 一个站够了：时区/列错位是全表性的


def cf_kt_station(st, truth, cf_base, kt_preds, args, cap, win, gccap):
    """One station's K_t scan: 每个 k 与基线在 truth∩base∩k 上同点集打分。
    -> (给 CSV 的列, [(series, label, color, linestyle, note), ...])。
    delta_nrmse_kt<k> > 0 = 按 k 缩放让预测变好，也就是原预报在这个方向上系统性偏了。"""
    ccol = CF_PRED_COL_TEMPLATE.format(station=st)
    if cf_base is None or ccol not in cf_base.columns:
        return {}, []
    p_base = cf_base[ccol].dropna()
    row, lines, best_k, best_n, base_n = {}, [], 1.0, None, None
    palette = ["#9467bd", "#8c564b", "#17becf", "#bcbd22", "#e377c2", "#7f7f7f"]
    for j, (k, dfk) in enumerate(sorted(kt_preds.items())):
        if dfk is None or ccol not in dfk.columns:
            continue
        p_k = dfk[ccol].dropna()
        got = cf_decomposition(truth, p_base, p_k, args.drop_night, args.night_end_hour, cap, win, gccap)
        if got is None:
            continue
        m, _ = got
        tag = f"{k:g}"
        row[f"power_nrmse_kt{tag}"] = m["nrmse_cf"]
        row[f"delta_nrmse_kt{tag}"] = m["delta_nrmse"]     # >0 = 缩放后更好
        if "nanwang_official_cf" in m:
            row[f"nanwang_official_power_kt{tag}"] = m["nanwang_official_cf"]
        base_n = m["nrmse_base"]                            # 每个 k 的三方交集一致，取哪个都一样
        row["power_nrmse_localbase"] = base_n               # 只开 --cf-kt-scale 时也得有基线这一列
        if best_n is None or m["nrmse_cf"] < best_n:
            best_n, best_k = m["nrmse_cf"], k
        if args.cf_kt_lines:
            lines.append((p_k, f"GHI x{tag} (K_t)", palette[j % len(palette)], ":", ""))
    if base_n is None:
        return {}, []
    if best_n is None or base_n <= best_n:                  # 没有哪个 k 比原样更好
        best_k, best_n = 1.0, base_n
    row["kt_best_factor"] = best_k
    row["kt_best_gain"] = round(base_n - best_n, 4)         # 相对基线省下的 nRMSE 百分点，1.0 时为 0
    return row, lines


def kt_report_summary(fdf, factors, pfx=""):
    """终端结论：谁的 GHI 预报有系统性缩放偏差，往哪个方向偏。"""
    if "kt_best_factor" not in fdf.columns:
        return
    d = fdf[np.isfinite(fdf["kt_best_factor"])]
    if d.empty:
        return
    moved = d[(d["kt_best_factor"] != 1.0) & (d["kt_best_gain"] > 0)]
    print(f"  {pfx}K_t scan over k={[f'{k:g}' for k in factors]}: "
          f"{len(moved)}/{len(d)} station(s) improve when the GHI forecast is rescaled")
    if moved.empty:
        print(f"  {pfx}  -> no station prefers a rescaled GHI: no systematic multiplicative bias at these k")
        return
    for _, r in moved.sort_values("kt_best_gain", ascending=False).head(5).iterrows():
        why = "forecast reads too LOW" if r.kt_best_factor > 1 else "forecast reads too HIGH"
        print(f"    {r.station}: best k={r.kt_best_factor:g} (-{r.kt_best_gain:.2f} nRMSE pct pt) -- {why}")
    lo = int((moved["kt_best_factor"] < 1).sum())
    print(f"  {pfx}  -> {lo} station(s) want k<1 (GHI over-forecast), "
          f"{len(moved) - lo} want k>1 (GHI under-forecast)")


def cf_station(st, truth, prod_pred, cf_base, cf_swap_pred, args, cap, win, gccap, swap_label):
    """One station's counterfactual: pull its column out of the local-inference frames, score the decomposition
    on truth∩base∩cf (three-way, so both sides are judged on identical points), and return the extra plot lines.
    Returns (columns for the CSVs, [(series, label, color, linestyle, title_note), ...])."""
    ccol = CF_PRED_COL_TEMPLATE.format(station=st)     # inference.py's naming, NOT --pred-col-template
    if cf_base is None or ccol not in cf_base.columns or ccol not in cf_swap_pred.columns:
        print(f"  [warn] station {st}: local inference produced no column '{ccol}' "
              f"(station absent from --cf-input?), counterfactual skipped for it")
        return {"cf_status": "missing"}, []
    p_base, p_cf = cf_base[ccol].dropna(), cf_swap_pred[ccol].dropna()
    got = cf_decomposition(truth, p_base, p_cf, args.drop_night, args.night_end_hour, cap, win, gccap)
    if got is None:
        print(f"  [warn] station {st}: truth and counterfactual share no time points in this window, skipped")
        return {"cf_status": "no_overlap"}, []
    m, (_, ct, _, cc) = got
    row = {"cf_status": "ok", "power_rmse_cf": round(rmse(cc, ct), 6),
           "power_nrmse_cf": m["nrmse_cf"], "power_nrmse_localbase": m["nrmse_base"],
           "delta_nrmse": m["delta_nrmse"], "frac_explained": m["frac_explained"],
           "coadapt": m["coadapt"]}
    if "nanwang_official_cf" in m:
        row["nanwang_official_power_cf"] = m["nanwang_official_cf"]
    # Reproduction gate: local baseline vs the production predict table, on this window's common points.
    # cf_check_tol is None when there IS no production table (the baseline is standing in for it), and
    # comparing the baseline against itself would report a meaningless 0% -- omit the column entirely.
    al = None if args.cf_check_tol is None else _aligned(p_base, prod_pred, args.drop_night,
                                                         args.night_end_hour, win)
    if al is not None:
        bvp = nrmse_pct(al[1], al[2], cap)
        row["base_vs_parquet_pct"] = round(bvp, 4)
        if bvp > args.cf_check_tol:
            row["cf_status"] = "baseline_mismatch"
            print(f"  [warn] station {st}: local baseline differs from the --predict table by {bvp:.2f}% "
                  f"(>{args.cf_check_tol}%) -- different model version or config? The decomposition still uses "
                  f"the local baseline, so it stays self-consistent, but --predict may not be this model.")
    lines = [(p_cf, f"counterfactual ({swap_label}->truth)", "#2ca02c", "-", f"cf RMSE={rmse(cc, ct):.3f}")]
    if args.cf_show_local_base and args.cf_check_tol is not None:   # without --predict the red line
        lines.append((p_base, "local baseline (original features)",  # already IS the local baseline
                      "#7f7f7f", "--", ""))
    return row, lines


def cf_report_summary(okd, swap_label, pfx=""):
    """Terminal conclusion: who is input-limited, who is model-limited, who got worse when handed the truth."""
    if okd.empty:
        return
    good = okd[np.isfinite(okd["frac_explained"])]
    if not good.empty:
        top_in = good.sort_values("frac_explained", ascending=False).head(2)
        print(f"  {pfx}biggest input problem (swap-to-truth improves most): " +
              ", ".join(f"{r.station}({r.frac_explained:.0f}%)" for _, r in top_in.iterrows()))
    top_md = okd[np.isfinite(okd["nrmse_cf"])].sort_values("nrmse_cf", ascending=False).head(2)
    if not top_md.empty:
        print(f"  {pfx}biggest model problem (high residual error even after swap-to-truth): " +
              ", ".join(f"{r.station}({r.nrmse_cf:.2f}%)" for _, r in top_md.iterrows()))
    co = okd[okd["coadapt"].fillna(0) > 0]
    if not co.empty:
        print(f"  {pfx}co-adaptation warning (swap-to-truth is worse): {co.station.tolist()}")
