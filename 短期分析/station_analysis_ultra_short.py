#!/usr/bin/env python3
"""PV 多站超短期预测结果分析：对指定日期 D 重建 16 条等 lead 预测线并对照真值。

数据源（两侧都按 起报时间 组织，每 15min 一个 起报）：
  --predict-dir  扁平目录，每个 起报 一个 parquet，文件名含 YYYYMMDDHHMM token；表 = dtime 列 +
                 每站一列（--pred-col-template，默认 predict_power_{station}）；行自 起报+15min 起，
                 只取前 16 点（lead 1..16 = 15min..4h）。
  --input-dir    Hive 分区 date=YYYY-MM-DD/time=HH:MM/ 下单个 parquet；行=station、列=特征
                 （schema 同短期 input，list 列，长 192）；只取每个 list 的第 0 个元素 = 起报+15min 值。

目标网格 = D 00:00..23:45 共 96 点。目标 t 的 16 个预测来自 起报 S=t-4h..t-15min；线 p_j = 恒定
lead(17-j)：p1=4h 前（最旧）、p16=15min 前（最新）。真值/GHI 取 time=(t-15min) 目录的 list[0]
（t=00:00 → date=D-1/time=23:45）。缺 起报 → 告警+NaN 缺口，不中断；同 token 多文件 → 退出。
产物：stations/ 17 线 Power 图 + 2 线 GHI 图；station_power_rmse.csv（16 lead 合并 RMSE）、
station_feature_rmse.csv（lead-1 GHI RMSE）。无散点/Theil/舰队图/反事实/history。
给 --info-csv（station+GCCAPCITY）时逐站打印南网超短期准确率到日志（仅打印，不进 CSV）。"""
from __future__ import annotations

import argparse
import glob
import os

import numpy as np
import pandas as pd

STEP = pd.Timedelta(minutes=15)
N_LEADS = 16
TRUTH_COLS = {"power_true": "observe_power_future",
              "ghi_true": "GHI_real_future",
              "ghi_pred": "GHI_SOLARGIS_predict"}


# ================================================================ shared helpers (copied from station_analysis_short.py)
def sanitize(s) -> str:
    return "".join(c if str(c).isalnum() else "_" for c in str(s))


def night_mask(idx: pd.DatetimeIndex, drop_night: bool, night_end_hour: float) -> np.ndarray:
    """True = keep. When drop_night, remove points in [00:00, night_end_hour)."""
    if not drop_night:
        return np.ones(len(idx), bool)
    hod = idx.hour + idx.minute / 60.0
    return ~(hod < night_end_hour)


def rmse(a, b):
    return float(np.sqrt(np.mean((a - b) ** 2)))


def _cn_font():
    import matplotlib
    try:
        matplotlib.rcParams["font.sans-serif"] = ["DejaVu Sans", "Arial", "Helvetica"]
        matplotlib.rcParams["axes.unicode_minus"] = False
    except Exception:
        pass


def _station_dir(out_dir):
    d = os.path.join(out_dir, "stations")
    os.makedirs(d, exist_ok=True)
    return d


# ================================================================ time grid / file resolution
def target_grid(D: pd.Timestamp) -> pd.DatetimeIndex:
    """D 00:00 .. 23:45, 96 points."""
    return pd.date_range(D, D + pd.Timedelta(days=1) - STEP, freq="15min")


def issue_times(D: pd.Timestamp) -> list:
    """预测侧所需 起报：D-1 20:00 .. D 23:30（111 个）。首 = 最早目标 00:00 的 lead-16 起报。"""
    first = D - N_LEADS * STEP
    return [first + k * STEP for k in range(N_LEADS + 96 - 1)]


def find_parquet(dirpath: str, token: str):
    """glob *token*.parquet：0 个 → None（调用方 warn+缺口）；>1 → 退出（目录被污染）。"""
    hits = sorted(glob.glob(os.path.join(dirpath, f"*{token}*.parquet")))
    if len(hits) > 1:
        raise SystemExit(f"{dirpath}: token '{token}' matches {len(hits)} parquets: {hits[:3]}")
    return hits[0] if hits else None


def stations_from_columns(cols, template: str, skip=("dtime",)) -> list:
    """按模板反解列名里的站名；template 需含 {station} 占位。"""
    pre, _, suf = template.partition("{station}")
    out = []
    for c in cols:
        c = str(c)
        if c in skip:
            continue
        if c.startswith(pre) and c.endswith(suf) and len(c) > len(pre) + len(suf):
            out.append(c[len(pre):len(c) - len(suf)] if suf else c[len(pre):])
    return out


# ================================================================ loaders
def load_predict_matrix(predict_dir: str, D: pd.Timestamp, stations: list, template: str,
                        dtime_col: str = "dtime"):
    """-> ({station: DataFrame(index=96 目标, columns=p1..p16 float)}, 缺文件数)。
    每个 起报 S 的 lead k 值放到 目标 S+k*step 的列 p{17-k}；目标不在当日网格的行忽略。"""
    grid = target_grid(D)
    labels = [f"p{j}" for j in range(1, N_LEADS + 1)]
    mats = {st: pd.DataFrame(np.nan, index=grid, columns=labels) for st in stations}
    n_missing = 0
    for S in issue_times(D):
        path = find_parquet(predict_dir, S.strftime("%Y%m%d%H%M"))
        if path is None:
            print(f"  [warn] predict 起报 {S:%Y-%m-%d %H:%M}: parquet not found -> gap")
            n_missing += 1
            continue
        df = pd.read_parquet(path)
        if dtime_col not in df.columns:
            print(f"  [warn] {os.path.basename(path)}: no '{dtime_col}' column -> skipped")
            n_missing += 1
            continue
        df = df.set_index(pd.to_datetime(df[dtime_col])).sort_index()
        df = df[~df.index.duplicated(keep="first")]
        for k in range(1, N_LEADS + 1):
            t = S + k * STEP
            if t not in grid or t not in df.index:
                continue
            lab = f"p{N_LEADS + 1 - k}"
            for st in stations:
                col = template.format(station=st)
                if col in df.columns:
                    v = df.at[t, col]
                    if pd.notna(v) and np.isfinite(float(v)):
                        mats[st].at[t, lab] = float(v)
    return mats, n_missing


def load_truth(input_dir: str, D: pd.Timestamp, station_col: str = "station"):
    """-> ({station: DataFrame(index=96 目标, columns=power_true/ghi_true/ghi_pred)}, 缺目录数)。
    目标 t 的值来自 起报 S=t-15min 目录内唯一 parquet 各 list 列的第 0 个元素。"""
    grid = target_grid(D)
    frames, n_missing = {}, 0
    for t in grid:
        S = t - STEP
        d = os.path.join(input_dir, f"date={S:%Y-%m-%d}", f"time={S:%H:%M}")
        hits = sorted(glob.glob(os.path.join(d, "*.parquet")))
        if not hits:
            print(f"  [warn] input 起报 {S:%Y-%m-%d %H:%M}: no parquet in {d} -> gap")
            n_missing += 1
            continue
        if len(hits) > 1:
            raise SystemExit(f"{d}: {len(hits)} parquets, expected exactly 1: {hits}")
        df = pd.read_parquet(hits[0])
        if station_col not in df.columns:
            print(f"  [warn] {hits[0]}: no '{station_col}' column -> skipped")
            n_missing += 1
            continue
        for _, row in df.iterrows():
            st = str(row[station_col])
            fr = frames.setdefault(st, pd.DataFrame(np.nan, index=grid, columns=list(TRUTH_COLS)))
            for out_col, src_col in TRUTH_COLS.items():
                if src_col not in df.columns:
                    continue
                cell = row[src_col]
                if cell is None or np.ndim(cell) == 0:
                    continue
                arr = np.asarray(cell, dtype=float).ravel()
                if arr.size and np.isfinite(arr[0]):
                    fr.at[t, out_col] = float(arr[0])
    return frames, n_missing


# ================================================================ metrics
def pooled_rmse(truth: pd.Series, leads: pd.DataFrame, keep: np.ndarray):
    """16 lead 合并 RMSE：leads 每列减 truth，keep（夜滤）行内所有有限 (lead,目标) 对。-> (rmse|None, n)。"""
    err = leads.sub(truth, axis=0).to_numpy(float)[keep]
    err = err[np.isfinite(err)]
    if err.size == 0:
        return None, 0
    return float(np.sqrt(np.mean(err ** 2))), int(err.size)


def load_gccap(path, station_col, cap_col="GCCAPCITY"):
    """info_csv -> {str(station): GCCAPCITY float}. Joins on station_col; needs station_col + GCCAPCITY columns.
    Rows with a missing/blank GCCAPCITY are skipped. Used only for the 南网 nanwang_ultrashort metric."""
    df = pd.read_csv(path)
    miss = [c for c in (station_col, cap_col) if c not in df.columns]
    if miss:
        raise SystemExit(f"--info-csv missing columns {miss}; actual columns: {list(df.columns)[:30]}")
    out = {}
    for _, r in df.iterrows():
        v = r[cap_col]
        if pd.notna(v):
            out[str(r[station_col])] = float(v)
    return out


def nanwang_ultrashort(truth: pd.Series, leads: pd.DataFrame, gccap):
    """南网超短期准确率（仅打印不落 CSV）：
        Acc = (1 − mean_t mean_i |P_real(t) − p_i(t)| / max(P_real(t), 0.2·GCCAPCITY)) × 100，
    逐项 sqrt(x²) 即 |x|。恒用全 96 目标点（含夜间，0.2C 分母下限保证良态，不受 --drop-night 影响）。
    缺项跳过：时刻内对可用 lead 取均值，日内对（真值有效且 ≥1 lead 有值）的时刻取均值。
    返回 (百分比, 有效时刻数)；gccap 缺失/非正或无有效时刻 → (None, 0)。"""
    if gccap is None or not (gccap > 0):
        return None, 0
    t = truth.to_numpy(float)
    P = leads.to_numpy(float)
    r = np.abs(t[:, None] - P) / np.maximum(t, 0.2 * gccap)[:, None]
    ok = np.isfinite(r)
    valid_t = np.flatnonzero(ok.any(axis=1))
    if valid_t.size == 0:
        return None, 0
    per_t = np.array([r[j][ok[j]].mean() for j in valid_t])
    return (1.0 - float(per_t.mean())) * 100.0, int(valid_t.size)


# ================================================================ plots
def plot_power_17(st, truth: pd.Series, leads: pd.DataFrame, rmse_v, n, out_dir, tick_hours):
    """17 线：真值黑粗 + p1..p16 由浅到深（p1=4h 前最旧最浅、p16=15min 前最新最深）。"""
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.dates as mdates
    import matplotlib.pyplot as plt
    from matplotlib import cm
    _cn_font()
    fig, ax = plt.subplots(figsize=(24, 7))
    colors = cm.viridis(np.linspace(0.88, 0.10, N_LEADS))
    for j, lab in enumerate(leads.columns):
        ax.plot(leads.index, leads[lab], color=colors[j], lw=0.9, alpha=0.8,
                label=f"{lab} ({(N_LEADS - j) * 15}min ahead)")
    ax.plot(truth.index, truth, color="#000000", lw=2.2, label="observed power")
    rtxt = f"pooled RMSE={rmse_v:.3f}" if rmse_v is not None else "no scored points"
    ax.set_title(f"Station {st} - ultra-short 16-lead power   {rtxt}   (n={n} lead-target pairs)",
                 fontsize=13, fontweight="bold")
    ax.xaxis.set_major_locator(mdates.HourLocator(interval=max(1, int(tick_hours))))
    ax.xaxis.set_major_formatter(mdates.DateFormatter("%m-%d %H:%M"))
    plt.setp(ax.get_xticklabels(), rotation=90, fontsize=7)
    ax.set_xlabel("time"); ax.set_ylabel("power")
    ax.legend(loc="upper right", fontsize=6, ncol=2); ax.grid(alpha=0.25)
    fig.tight_layout()
    path = os.path.join(_station_dir(out_dir), f"station_{sanitize(st)}_Power.png")
    fig.savefig(path, dpi=110); plt.close(fig)
    return path


def plot_ghi(st, ghi_true: pd.Series, ghi_pred: pd.Series, rmse_v, out_dir, tick_hours):
    """2 线：lead-1 GHI 预测 vs GHI 真值（都来自 input 侧 list[0]，是特征质量图不是模型输出图）。"""
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.dates as mdates
    import matplotlib.pyplot as plt
    _cn_font()
    fig, ax = plt.subplots(figsize=(24, 6))
    ax.plot(ghi_true.index, ghi_true, label="GHI_real_future (true)", color="#1f77b4", lw=1.3)
    ax.plot(ghi_pred.index, ghi_pred, label="GHI_SOLARGIS_predict (lead-1 pred)",
            color="#d62728", lw=1.1, alpha=0.85)
    ax.fill_between(ghi_true.index, ghi_true.to_numpy(float), ghi_pred.to_numpy(float),
                    color="#d62728", alpha=0.12)
    ax.set_title(f"Station {st} - GHI (lead-1)   RMSE={rmse_v:.3f}", fontsize=13, fontweight="bold")
    ax.xaxis.set_major_locator(mdates.HourLocator(interval=max(1, int(tick_hours))))
    ax.xaxis.set_major_formatter(mdates.DateFormatter("%m-%d %H:%M"))
    plt.setp(ax.get_xticklabels(), rotation=90, fontsize=7)
    ax.set_xlabel("time"); ax.set_ylabel("GHI"); ax.legend(loc="upper right"); ax.grid(alpha=0.25)
    fig.tight_layout()
    path = os.path.join(_station_dir(out_dir), f"station_{sanitize(st)}_GHI.png")
    fig.savefig(path, dpi=110); plt.close(fig)
    return path


# ================================================================ main
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
    ap.add_argument("--info-csv", default=None,
                    help="CSV 含 station+GCCAPCITY 两列；给了就逐站打印南网超短期准确率（仅日志，不进 CSV）")
    args = ap.parse_args()
    D = pd.Timestamp(args.date).normalize()
    gccap_map = load_gccap(args.info_csv, args.station_col) if args.info_csv else {}

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
    mats, miss_pred = load_predict_matrix(args.predict_dir, D, sts, args.pred_col_template)

    out_root = os.path.join(args.out_dir, D.strftime("%Y%m%d"))
    os.makedirs(out_root, exist_ok=True)
    keep = night_mask(target_grid(D), args.drop_night, args.night_end_hour)
    power_rows, feat_rows = [], []
    for st in sts:
        tr = truth[st]
        rv, n = pooled_rmse(tr["power_true"], mats[st], keep)
        if rv is not None:
            power_rows.append({"station": st, "power_rmse": round(rv, 6), "n_points": n})
        else:
            print(f"  [warn] station {st}: no scored (lead, target) pairs, power skipped")
        gt, gp = tr["ghi_true"][keep], tr["ghi_pred"][keep]
        both = np.isfinite(gt.to_numpy(float)) & np.isfinite(gp.to_numpy(float))
        grm = rmse(gp.to_numpy(float)[both], gt.to_numpy(float)[both]) if both.any() else None
        if grm is not None:
            feat_rows.append({"station": st, "feature": "GHI", "rmse": round(grm, 6),
                              "n_points": int(both.sum())})
        if not args.no_plots:
            plot_power_17(st, tr["power_true"][keep], mats[st][keep], rv, n, out_root, args.tick_hours)
            if grm is not None:
                plot_ghi(st, gt, gp, grm, out_root, args.tick_hours)

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
