#!/usr/bin/env python3
"""PV 多站短期预测结果分析（数据格式锁定：起报时间恒为当日 10:00，输入 list 列长 480、首元素 10:15、步长 15min，预测表 dtime 从次日 00:00 起）。
按 起报日 D 切 D+1、D+4 两个 24h 窗，每窗每站产一张 2x2 组合图（左列 history GHI/功率全量点，右列本窗 GHI/功率预测对真值）
+ 舰队总览与排名；可选 --counterfactual 经本地 inference.py 做 GHI oracle 替换归因。"""
from __future__ import annotations

import argparse
import os
import sys

import numpy as np
import pandas as pd

DEFAULT_FEATURE_PAIRS = [("GHI_SOLARGIS_predict", "GHI_real_future", "GHI")]
HISTORY_COLS = ["observe_power", "GHI_SOLARGIS"]  # historical (past-observed) list columns -> 2x2 left column


# ================================================================ Common: flatten / night / align
def sanitize(s) -> str:
    return "".join(c if str(c).isalnum() else "_" for c in str(s))


def series_from_lists(wins, lists, step) -> pd.Series:
    """Flatten all windows of a station's list column into an (absolute time -> value) series, groupby time to dedup.
    Non-list / None / NaN cells are auto-skipped (robust: a station missing this feature -> returns empty series)."""
    times, vals = [], []
    for t0, fut in zip(wins, lists):
        if fut is None or np.ndim(fut) == 0:          # scalar/None/NaN -> skip
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


def series_from_lists_history(wins, lists, step) -> pd.Series:
    """Like series_from_lists but the list runs BACKWARD from the window time (起报时间): for a cell
    with timestamp_win=t0 and finite array of length L, element i -> t0 - step*(L-1-i), so the LAST
    element lands at t0, the second-to-last at t0-step, etc. Non-list / None / NaN cells auto-skipped;
    flatten all windows, groupby absolute time and dedup by mean."""
    times, vals = [], []
    for t0, fut in zip(wins, lists):
        if fut is None or np.ndim(fut) == 0:
            continue
        arr = np.asarray(fut, dtype=float).ravel()
        if arr.size == 0:
            continue
        t0 = pd.Timestamp(t0)
        L = arr.size
        for i, v in enumerate(arr):
            if np.isfinite(v):
                times.append(t0 - step * (L - 1 - i))
                vals.append(float(v))
    if not times:
        return pd.Series(dtype=float)
    s = pd.Series(vals, index=pd.DatetimeIndex(times))
    return s.groupby(s.index).mean().sort_index()


def hist_span(inp, win_col, hist_col, step):
    """(t_start, t_end) covered by series_from_lists_history over the whole table, without flattening it:
    the last element of each list sits at its timestamp_win, so the union runs from
    min(win) - step*(Lmax-1) to max(win). Used to decide which date folders --hist-root must read."""
    if hist_col not in inp.columns or inp.empty:
        return None
    lens = inp[hist_col].map(_listlen)
    L = int(lens.max()) if len(lens) else 0
    if L == 0:
        return None
    wins = pd.to_datetime(pd.Series(inp[win_col].to_numpy()))
    return wins.min() - step * (L - 1), wins.max()


def night_mask(idx: pd.DatetimeIndex, drop_night: bool, night_end_hour: float) -> np.ndarray:
    """True = keep. When drop_night, remove points in [00:00, night_end_hour)."""
    if not drop_night:
        return np.ones(len(idx), bool)
    hod = idx.hour + idx.minute / 60.0
    return ~(hod < night_end_hour)


def window_mask(idx: pd.DatetimeIndex, win) -> np.ndarray:
    """True = keep. win=(start,end) keeps [start, end) (end exclusive); win=None keeps all."""
    if win is None:
        return np.ones(len(idx), bool)
    start, end = win
    return (idx >= start) & (idx < end)


def _aligned(a: pd.Series, b: pd.Series, drop_night, night_end_hour, win=None):
    """Take common time points of two series + drop night + restrict to win. Returns (times, a_vals, b_vals) or None."""
    common = a.index.intersection(b.index).sort_values()
    if len(common) == 0:
        return None
    keep = night_mask(common, drop_night, night_end_hour) & window_mask(common, win)
    common = common[keep]
    if len(common) == 0:
        return None
    return common, a.loc[common].to_numpy(), b.loc[common].to_numpy()


def _display_multi(a: pd.Series, others, drop_night, night_end_hour, win=None, fill=0.0):
    """PLOT-ONLY: union of ALL series' timestamps (within win, minus night), reindex every series onto that
    one index, gaps filled with `fill`. Metrics keep using _aligned (intersection); this only makes the lines
    span the full window so gaps are visible instead of silently dropped. One shared index is what lets the
    truth / prediction / counterfactual lines sit on a single x-axis.
    Returns (times, a_vals, [other_vals, ...]) or None."""
    idx = a.index
    for s in others:
        idx = idx.union(s.index)
    idx = idx.sort_values()
    keep = night_mask(idx, drop_night, night_end_hour) & window_mask(idx, win)
    idx = idx[keep]
    if len(idx) == 0:
        return None
    return (idx, a.reindex(idx).fillna(fill).to_numpy(),
            [s.reindex(idx).fillna(fill).to_numpy() for s in others])


def _display(a: pd.Series, b: pd.Series, drop_night, night_end_hour, win=None, fill=0.0):
    """Two-series form of _display_multi (kept so existing callers read unchanged)."""
    got = _display_multi(a, [b], drop_night, night_end_hour, win, fill)
    return None if got is None else (got[0], got[1], got[2][0])


def rmse(a, b):
    return float(np.sqrt(np.mean((a - b) ** 2)))


def nanwang_official(p_real, p_pred, gccap):
    """南网「两个细则」official forecast accuracy over aligned arrays, returned in percent:
        (1 - sqrt( mean( ((p_real - p_pred) / max(p_real, 0.2*gccap))^2 ) )) * 100.
    The 0.2*gccap denominator floor keeps night/near-zero points well-defined, so callers should pass
    ALL points (night included, NOT the drop-night subset). Returns None if gccap<=0 or no points."""
    if gccap is None or not (gccap > 0):
        return None
    a = np.asarray(p_real, dtype=float)
    p = np.asarray(p_pred, dtype=float)
    if a.size == 0:
        return None
    denom = np.maximum(a, 0.2 * gccap)            # per-point floor; a is nonneg power, denom always > 0
    r = (a - p) / denom
    return (1.0 - float(np.sqrt(np.mean(r ** 2)))) * 100.0


NANWANG_FACTORS = (1.4, 1.2, 1.0, 0.8, 0.6, 0.4)   # 1.0 = 原官方列，居中放置


def nanwang_factor_row(p_real, p_pred, gccap, factors=NANWANG_FACTORS):
    """南网口径的乘性灵敏度扫描：每个 factor 把预测的每一个点乘以 factor 后重算 nanwang_official。
    不做任何截断，factor>1 的预测可以超过 GCCAPCITY。返回按 factors 顺序排列的 {列名: 值}，
    factor 1.0 沿用原列名 nanwang_official_power，其余为 nanwang_official_power_x<factor>。
    gccap 不可用（None/<=0）或无点时返回 {}。"""
    p = np.asarray(p_pred, dtype=float)
    out = {}
    for f in factors:
        v = nanwang_official(p_real, p * f, gccap)
        if v is None:
            return {}
        out["nanwang_official_power" if f == 1.0 else f"nanwang_official_power_x{f:g}"] = round(v, 4)
    return out


def resolve_pred_col(st, pred, template):
    """站点 -> 预测表列名 template.format(station=st)；列不存在返回 None（调用方 warn + skip）。"""
    col = template.format(station=st)
    return col if col in pred.columns else None


def theil_shares(t, p):
    """Theil-U three-way split: MSE = (mean_p-mean_t)^2 + (sd_p-sd_t)^2 + 2(1-r)*sd_p*sd_t.
    Returns (u_bias, u_var, u_cov) shares summing to 1 (level offset / amplitude mismatch / shape-timing mismatch),
    or None when MSE~0 or too few points. Population std (ddof=0) keeps the identity exact."""
    t, p = np.asarray(t, float), np.asarray(p, float)
    if len(t) < 3:
        return None
    mse = float(np.mean((p - t) ** 2))
    if mse <= 1e-12:
        return None
    sd_t, sd_p = float(np.std(t)), float(np.std(p))
    u_bias = (float(np.mean(p)) - float(np.mean(t))) ** 2 / mse
    u_var = (sd_p - sd_t) ** 2 / mse
    r = float(np.corrcoef(p, t)[0, 1]) if sd_p > 0 and sd_t > 0 else 0.0
    u_cov = 2.0 * (1.0 - r) * sd_p * sd_t / mse
    return u_bias, u_var, u_cov


def scatter_stats(t, p):
    """pred = slope*true + intercept fit + R^2 + top-20%-truth mean residual (high-value compression signal).
    Reading discipline (true-vs-pred-scatter recipe): R^2 = scatter, slope = systematic scaling -- decoupled.
    Returns None when truth has no variance (recipe treats that as a data-plumbing symptom)."""
    t, p = np.asarray(t, float), np.asarray(p, float)
    if len(t) < 3 or np.std(t) == 0:
        return None
    slope, intercept = np.polyfit(t, p, 1)
    hi = t >= np.quantile(t, 0.8)
    return {"slope": float(slope), "intercept": float(intercept),
            "r2": float(np.corrcoef(t, p)[0, 1] ** 2),
            "high_bias": float(np.mean(p[hi] - t[hi]))}


def parse_feature_pairs(spec):
    if not spec:
        return list(DEFAULT_FEATURE_PAIRS)
    out = []
    for item in spec.split(","):
        parts = [p.strip() for p in item.split(":")]
        if len(parts) == 2:
            parts.append(parts[0])
        if len(parts) != 3 or not all(parts[:2]):
            raise SystemExit(f"--feature-pairs item format should be pred:true[:label], got '{item}'")
        out.append(tuple(parts))
    return out


def parse_capacity(spec):
    if not spec:
        return {}
    out = {}
    for item in spec.split(","):
        k, _, v = item.partition(":")
        out[k.strip()] = float(v)
    return out


def load_station_info(path, station_col, stations):
    """info_csv -> {str(station): {"gccap": float|None, "city": str|None}}.
    Capacity column: GCCAPCITY or GCCAPACITY (case-insensitive). Join column: station_col when present,
    otherwise auto-detected as the info_csv column whose values (str-compared) match the most stations;
    zero matches anywhere -> SystemExit. city column (case-insensitive "city") is optional."""
    df = pd.read_csv(path)
    cap_col = next((c for c in df.columns if str(c).upper() in ("GCCAPCITY", "GCCAPACITY")), None)
    if cap_col is None:
        raise SystemExit(f"--info-csv has no GCCAPCITY/GCCAPACITY column; actual columns: {list(df.columns)[:30]}")
    city_col = next((c for c in df.columns if str(c).lower() == "city"), None)
    want = {str(s) for s in stations}
    if station_col in df.columns:
        join_col = station_col
    else:
        join_col, hits = None, 0
        for c in df.columns:
            n = int(df[c].astype(str).isin(want).sum())
            if n > hits:
                join_col, hits = c, n
        if join_col is None:
            raise SystemExit(f"--info-csv: no column matches any station value (stations look like "
                             f"{sorted(want)[:3]}; columns: {list(df.columns)[:30]})")
        print(f"  [info-csv] join column auto-detected: '{join_col}' (matches {hits}/{len(want)} stations); "
              f"capacity column: '{cap_col}'")
    out = {}
    for _, r in df.iterrows():
        v = r[cap_col]
        out[str(r[join_col])] = {
            "gccap": float(v) if pd.notna(v) else None,
            "city": str(r[city_col]) if city_col is not None and pd.notna(r[city_col]) else None}
    return out


# ================================================================ Per-station combined 2x2 plot
def _fmt_time_axis(ax, times, tick_hours):
    import matplotlib.dates as mdates
    import matplotlib.pyplot as plt
    n_hours = max(1.0, (times[-1] - times[0]).total_seconds() / 3600.0)
    ax.xaxis.set_major_locator(mdates.HourLocator(
        interval=max(1, int(tick_hours), int(np.ceil(n_hours / 36.0)))))
    ax.xaxis.set_major_formatter(mdates.DateFormatter("%m-%d %H:%M"))
    plt.setp(ax.get_xticklabels(), rotation=90, fontsize=8)
    ax.set_xlabel("time", fontsize=10); ax.grid(alpha=0.25)


def _draw_hist_panel(ax, panel, fallback_name, tick_hours):
    """Left-column history panel: one line over ALL history points, plus any extra lines (raw avail power).
    panel = (name, times, vals[, extras]) or None; extras = [(times, vals, label, color, linestyle), ...].
    Extras carry their OWN x — unlike the window panel there is no fill_between or RMSE here, so a raw
    series with different coverage may simply be shorter instead of being force-aligned."""
    if panel is None:
        ax.text(0.5, 0.5, "no data", ha="center", va="center", fontsize=12)
        ax.set_title(f"{fallback_name} (history)", fontsize=13, fontweight="bold")
        return
    name, times, vals = panel[:3]
    extras = panel[3] if len(panel) > 3 else []
    times = pd.DatetimeIndex(times)
    ax.plot(times, vals, color="#1f77b4", lw=1.3, label=name)
    notes = ""
    for xt, yv, lab, color, ls in extras:
        ax.plot(pd.DatetimeIndex(xt), yv, color=color, lw=1.1, ls=ls, alpha=0.9, label=lab)
        notes += f"   {lab} n={len(yv)}"
    ax.set_title(f"{name} (history)   {times[0]:%Y-%m-%d %H:%M} -> {times[-1]:%Y-%m-%d %H:%M}   "
                 f"(n={len(times)}){notes}", fontsize=13, fontweight="bold")
    ax.set_ylabel(name, fontsize=11); ax.legend(loc="upper right", fontsize=9)
    _fmt_time_axis(ax, times, tick_hours)


def _draw_win_panel(ax, panel, fallback_name, win_label, tick_hours):
    """Right-column window panel: truth vs prediction, plus any extra lines (counterfactual, local baseline).
    panel = (name, times, true_v, pred_v, rmse_v, n_scored, true_label, pred_label[, extras]) or None;
    extras = [(vals, label, color, linestyle, title_note), ...] — all share the panel's single x-axis, and
    title_note carries the already-scored RMSE (display arrays have gaps filled 0, so never re-score here)."""
    if panel is None:
        ax.text(0.5, 0.5, "no data", ha="center", va="center", fontsize=12)
        ax.set_title(f"{fallback_name} ({win_label})", fontsize=13, fontweight="bold")
        return
    name, times, tv, pv, rv, n_scored, tlab, plab = panel[:8]
    extras = panel[8] if len(panel) > 8 else []
    times = pd.DatetimeIndex(times)
    ax.plot(times, tv, label=tlab, color="#1f77b4", lw=1.3)
    ax.plot(times, pv, label=plab, color="#d62728", lw=1.1, alpha=0.85)
    ax.fill_between(times, tv, pv, color="#d62728", alpha=0.12)
    notes = ""
    for vals, lab, color, ls, note in extras:
        ax.plot(times, vals, label=lab, color=color, lw=1.1, ls=ls, alpha=0.9)
        notes += f"   {note}" if note else ""
    gap_note = f", {len(times) - n_scored} gaps filled 0" if n_scored < len(times) else ""
    ax.set_title(f"{name} ({win_label})   RMSE={rv:.3f}{notes}   start {times[0]:%Y-%m-%d %H:%M}   "
                 f"(n={n_scored} scored{gap_note})", fontsize=13, fontweight="bold")
    ax.set_ylabel(name, fontsize=11); ax.legend(loc="upper right", fontsize=9)
    _fmt_time_axis(ax, times, tick_hours)


def plot_station_combined(st, win_label, hist_ghi, hist_pw, win_ghi, win_pw, out_dir, tick_hours):
    """One 2x2 PNG per station per window, saved as <out_dir>/station_<站>.png.
    Left column = history over ALL history points: GHI (top) / power (bottom), each (name, times, vals) or None.
    Right column = this window's pred-vs-true with RMSE: GHI (top) / power (bottom); the power panel may carry
    extra lines (counterfactual / local baseline) — see _draw_win_panel."""
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    _cn_font()
    fig, axes = plt.subplots(2, 2, figsize=(32, 12))
    _draw_hist_panel(axes[0, 0], hist_ghi, "GHI", tick_hours)
    _draw_hist_panel(axes[1, 0], hist_pw, "power", tick_hours)
    _draw_win_panel(axes[0, 1], win_ghi, "GHI", win_label, tick_hours)
    _draw_win_panel(axes[1, 1], win_pw, "Power", win_label, tick_hours)
    fig.suptitle(f"Station {st}  -  {win_label}", fontsize=16, fontweight="bold")
    fig.tight_layout(rect=(0, 0, 1, 0.965))
    path = os.path.join(out_dir, f"station_{sanitize(st)}.png")
    fig.savefig(path, dpi=110); plt.close(fig)
    return path


def plot_theil_overview(df, out_dir, focus_note=""):
    """Per-station 100%-stacked Theil shares, sorted by power nRMSE desc; dominant component labeled at bar end."""
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    _cn_font()
    d = df[np.isfinite(pd.to_numeric(df["theil_u_bias"], errors="coerce"))].copy()
    if d.empty:
        return None
    if "power_nrmse" in d.columns:
        d = d.sort_values("power_nrmse", ascending=False)
    n = len(d)
    fig, ax = plt.subplots(figsize=(12, max(4.0, 1.0 + n * 0.45)))
    y = np.arange(n)[::-1]
    left = np.zeros(n)
    for col, color, lab in (("theil_u_bias", "#f28e2b", "u_bias: level offset (cheapest fix: output shift)"),
                            ("theil_u_var", "#4c78a8", "u_var: amplitude mismatch (calibration / capacity assumption)"),
                            ("theil_u_cov", "#9aa0a6", "u_cov: shape/timing mismatch (check time shift)")):
        v = pd.to_numeric(d[col], errors="coerce").fillna(0.0).to_numpy(float)
        ax.barh(y, v, left=left, color=color, label=lab)
        left += v
    for yi, (_, r) in zip(y, d.iterrows()):
        dom = max((("u_bias", r["theil_u_bias"]), ("u_var", r["theil_u_var"]), ("u_cov", r["theil_u_cov"])),
                  key=lambda x: x[1])
        extra = f"   nRMSE {r['power_nrmse']:.1f}%" if np.isfinite(r.get("power_nrmse", np.nan)) else ""
        ax.text(1.02, yi, f"{dom[0]} {dom[1]:.0%}{extra}", va="center", fontsize=7)
    ax.set_yticks(y); ax.set_yticklabels(d["station"].astype(str), fontsize=8)
    ax.set_xlim(0, 1.35)
    ax.set_xlabel("share of power MSE (u_bias + u_var + u_cov = 1)")
    ax.set_title("Theil decomposition of power MSE (dominant >= 50% -> that fix first)" + focus_note,
                 fontsize=12, fontweight="bold")
    ax.legend(loc="lower right", fontsize=8); ax.grid(axis="x", alpha=0.25)
    fig.tight_layout()
    path = os.path.join(out_dir, "theil_decomposition.png")
    fig.savefig(path, dpi=120); plt.close(fig)
    return path


# ================================================================ Fleet overview: metrics + dashboard
def hourly_nrmse(times, err, cap):
    """Aggregate err's RMSE by hour (0..23) / cap*100. Returns length-24 array (no data = nan)."""
    hod = pd.DatetimeIndex(times).hour
    out = np.full(24, np.nan)
    for h in range(24):
        m = hod == h
        if m.any():
            out[h] = np.sqrt(np.mean(err[m] ** 2)) / cap * 100.0
    return out


def flag_outliers(vals, k):
    """> median + k x MAD is flagged as outlier. Returns bool array (valid count <3 or MAD=0 -> all False)."""
    v = np.asarray(vals, float)
    ok = np.isfinite(v)
    out = np.zeros(len(v), bool)
    if ok.sum() < 3:
        return out
    med = np.median(v[ok])
    mad = np.median(np.abs(v[ok] - med)) * 1.4826  # normal-consistent scaling
    thr = med + k * mad if mad > 0 else np.inf
    out[ok] = v[ok] > thr
    return out


def _cn_font():
    import matplotlib
    try:
        matplotlib.rcParams["font.sans-serif"] = ["DejaVu Sans", "Arial", "Helvetica"]
        matplotlib.rcParams["axes.unicode_minus"] = False
    except Exception:
        pass


def _barh(ax, df, col, title, mad_k, top_n):
    d = df[np.isfinite(df[col])].sort_values(col, ascending=False)
    note = ""
    if top_n and len(d) > top_n:
        note = f"(worst {top_n}/{len(d)})"
        d = d.head(top_n)
    if d.empty:
        ax.text(0.5, 0.5, "no data", ha="center", va="center"); ax.set_title(title); return
    out = flag_outliers(d[col].to_numpy(), mad_k)
    med = float(np.median(df[col][np.isfinite(df[col])]))
    y = np.arange(len(d))[::-1]                       # worst on top
    colors = ["#d62728" if o else "#4c78a8" for o in out]
    ax.barh(y, d[col], color=colors)
    ax.set_yticks(y); ax.set_yticklabels(d["station"].astype(str), fontsize=8)
    ax.axvline(med, color="gray", ls="--", lw=1, label=f"median {med:.1f}%")
    ax.set_xlabel("nRMSE (%)")
    ax.set_xlim(0, float(d[col].max()) * 1.22)        # padding, prevent outlier annotation running off the right edge
    ax.legend(loc="lower right", fontsize=8); ax.grid(axis="x", alpha=0.25)
    for yi, (v, o) in enumerate(zip(d[col], out)):
        ax.text(v, y[yi], f" {v:.1f}" + ("  outlier" if o else ""),
                va="center", fontsize=7, color="#d62728" if o else "#333")
    ax.set_title(title + ("  " + note if note else ""), fontsize=12, fontweight="bold")


def _scatter(ax, df, mad_k):
    if "power_nrmse" not in df or "ghi_nrmse" not in df:
        ax.text(0.5, 0.5, "missing GHI or power, cannot scatter", ha="center", va="center")
        ax.set_title("B  GHI-nRMSE vs power-nRMSE", fontsize=12, fontweight="bold"); return
    d = df[np.isfinite(df["power_nrmse"]) & np.isfinite(df["ghi_nrmse"])]
    if d.empty:
        ax.text(0.5, 0.5, "missing GHI or power, cannot scatter", ha="center", va="center")
        ax.set_title("B  GHI-nRMSE vs power-nRMSE", fontsize=12, fontweight="bold"); return
    xm, ym = float(np.median(d.ghi_nrmse)), float(np.median(d.power_nrmse))
    po = flag_outliers(d.power_nrmse.to_numpy(), mad_k)
    ax.scatter(d.ghi_nrmse, d.power_nrmse, c=["#d62728" if o else "#4c78a8" for o in po], s=60, zorder=3)
    for _, r in d.iterrows():
        ax.annotate(str(r.station), (r.ghi_nrmse, r.power_nrmse),
                    fontsize=7, xytext=(4, 3), textcoords="offset points")
    ax.axvline(xm, color="gray", ls="--", lw=1); ax.axhline(ym, color="gray", ls="--", lw=1)
    ax.set_xlabel("GHI nRMSE (%)  -> worse input"); ax.set_ylabel("power nRMSE (%)  -> worse output")
    ax.set_title("B  Is the power error explained by GHI input error", fontsize=12, fontweight="bold")
    ax.grid(alpha=0.25)
    ax.text(0.98, 0.02, "top-right = GHI bad & power bad\n(input explains it)", transform=ax.transAxes,
            ha="right", va="bottom", fontsize=7, color="#777")
    ax.text(0.02, 0.98, "top-left = GHI good but power bad\n(model/other issue)", transform=ax.transAxes,
            ha="left", va="top", fontsize=7, color="#777")


def _heatmap(fig, ax, df, hourly, drop_night, night_end_hour):
    if "power_nrmse" not in df:
        ax.text(0.5, 0.5, "no hourly power data", ha="center", va="center")
        ax.set_title("C  time-of-day x station power nRMSE", fontsize=12, fontweight="bold"); return
    order = df[np.isfinite(df["power_nrmse"])].sort_values("power_nrmse", ascending=False)
    sts = [s for s in order.station if s in hourly]
    if not sts:
        ax.text(0.5, 0.5, "no hourly power data", ha="center", va="center")
        ax.set_title("C  time-of-day x station power nRMSE", fontsize=12, fontweight="bold"); return
    h0 = int(night_end_hour) if drop_night else 0
    hours = list(range(h0, 24))
    M = np.vstack([hourly[s][h0:24] for s in sts])
    im = ax.imshow(M, aspect="auto", cmap="YlOrRd", interpolation="nearest")
    ax.set_xticks(range(len(hours))); ax.set_xticklabels(hours, fontsize=7)
    ax.set_yticks(range(len(sts))); ax.set_yticklabels([str(s) for s in sts], fontsize=8)
    ax.set_xlabel("hour of day"); ax.set_title("C  time-of-day x station power nRMSE (%)", fontsize=12, fontweight="bold")
    fig.colorbar(im, ax=ax, fraction=0.046, pad=0.04)


def plot_dashboard(df, hourly, have_ghi, args, out_dir, focus_note=""):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    _cn_font()
    n_st = len(df)
    h = max(9.0, 1.0 + n_st * 0.45)                  # height auto-adapts to station count
    fig, axes = plt.subplots(2, 2, figsize=(18, h))
    if "power_nrmse" in df:
        _barh(axes[0, 0], df, "power_nrmse", "A1  power nRMSE ranking", args.mad_k, args.top_n)
    else:
        axes[0, 0].text(0.5, 0.5, "no power data", ha="center", va="center")
        axes[0, 0].set_title("A1  power nRMSE ranking", fontsize=12, fontweight="bold")
    if have_ghi and "ghi_nrmse" in df:
        _barh(axes[0, 1], df, "ghi_nrmse", "A2  GHI nRMSE ranking", args.mad_k, args.top_n)
    else:
        axes[0, 1].text(0.5, 0.5, "no GHI truth/pred, skipped", ha="center", va="center")
        axes[0, 1].set_title("A2  GHI nRMSE ranking", fontsize=12, fontweight="bold")
    _scatter(axes[1, 0], df, args.mad_k)
    _heatmap(fig, axes[1, 1], df, hourly, args.drop_night, args.night_end_hour)
    fig.suptitle(f"Fleet overview -- {n_st} stations   "
                 f"(nRMSE = RMSE / peak power; red bar = outlier: above median + {args.mad_k}xMAD)"
                 + ("   night removed" if args.drop_night else "") + focus_note,
                 fontsize=14, fontweight="bold")
    fig.tight_layout(rect=(0, 0, 1, 0.98))
    path = os.path.join(out_dir, "fleet_overview.png")
    fig.savefig(path, dpi=120); plt.close(fig)
    return path


# ================================================================ Counterfactual (oracle GHI swap, local inference)
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


def _listlen(v):
    """Length of a parquet list cell; 0 for None/NaN/scalar so unusable rows are easy to spot."""
    if v is None or np.ndim(v) == 0:
        return 0
    return len(v)


def cf_usable_rows(cf_inp, swap, station_col, win_col):
    """Keep only rows the swap can actually be performed on: every (pred, truth) pair present, non-empty and
    the same length. Feeding a None cell to the model crashes it, and a length-mismatched truth would silently
    change the row's horizon -- both must be dropped before inference, not discovered inside it."""
    ok = np.ones(len(cf_inp), dtype=bool)
    reasons = {}
    for pcol, tcol in swap.items():
        for i, (pv, tv) in enumerate(zip(cf_inp[pcol].to_numpy(), cf_inp[tcol].to_numpy())):
            lp, lt = _listlen(pv), _listlen(tv)
            if lp == 0 or lt == 0:
                ok[i] = False
                reasons.setdefault("empty", set()).add(str(cf_inp[station_col].iloc[i]))
            elif lp != lt:
                ok[i] = False
                reasons.setdefault("length", set()).add(str(cf_inp[station_col].iloc[i]))
    if "empty" in reasons:
        print(f"  [warn] counterfactual: dropping rows with empty {list(swap)} / truth cells "
              f"(stations {sorted(reasons['empty'])[:10]}) -- they get cf_status=missing, 0 inference calls")
    if "length" in reasons:
        print(f"  [warn] counterfactual: dropping rows where the truth column length != forecast length "
              f"(stations {sorted(reasons['length'])[:10]}) -- swapping would change the horizon")
    return cf_inp[ok]


def cf_infer_windows(cf_inp, args, infer_fn, swap=None, label=""):
    """Run local inference over every 起报 window of cf_inp -> dtime-indexed frame of predict_power_<站> columns.
    One call per window with all that window's stations, which is exactly what multi_station_inference asserts
    (station unique + single timestamp_win). swap={pred_col: truth_col} replaces the forecast with its truth
    before predicting; swap=None reproduces the baseline from the same checkpoints.
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


def cf_build_predictions(inp, args, swap):
    """Two local passes (baseline + GHI swapped to truth) over --cf-input, cached to parquet beside the report.
    Returns (base_df, cf_df); either may be empty. Cache hit means zero inference calls on a rerun."""
    cache_base = os.path.join(args.report_root, "cf_base_pred.parquet")
    cache_cf = os.path.join(args.report_root, "cf_swap_pred.parquet")
    if not args.cf_force and os.path.exists(cache_base) and os.path.exists(cache_cf):
        print(f"[counterfactual] cache hit -> {cache_base} / {cache_cf} (0 inference calls; --cf-force to redo)")
        return (pd.read_parquet(cache_base).sort_index(), pd.read_parquet(cache_cf).sort_index())

    cf_path = args.cf_input or args.input
    cf_inp = pd.read_parquet(cf_path)
    for c in (args.station_col, args.win_col):
        if c not in cf_inp.columns:
            raise SystemExit(f"--cf-input '{cf_path}' missing column '{c}'; "
                             f"actual columns: {list(cf_inp.columns)[:30]}")
    miss = sorted({c for pair in swap.items() for c in pair if c not in cf_inp.columns})
    if miss:
        raise SystemExit(f"--cf-input '{cf_path}' missing --cf-swap columns {miss}; "
                         f"actual columns: {list(cf_inp.columns)[:30]}")
    cf_inp[args.win_col] = pd.to_datetime(cf_inp[args.win_col])
    cf_inp = cf_usable_rows(cf_inp, swap, args.station_col, args.win_col)   # same rows feed BOTH passes
    if cf_inp.empty:
        print("  [warn] counterfactual: no row in --cf-input can be swapped, skipping inference entirely")
        return pd.DataFrame(), pd.DataFrame()
    print(f"[counterfactual] cf-input {cf_path}: {len(cf_inp)} rows, "
          f"{cf_inp[args.station_col].nunique()} stations, {cf_inp[args.win_col].nunique()} windows")

    cf_check_swap_consumed(args.config, swap)
    infer_fn = cf_load_inference(args.inference_dir)
    base = cf_infer_windows(cf_inp, args, infer_fn, None, "baseline pass (original features)")
    cf = cf_infer_windows(cf_inp, args, infer_fn, swap,
                          "swap pass (" + ", ".join(f"{p}->{t}" for p, t in swap.items()) + ")")
    if not base.empty and not cf.empty:
        shared = [c for c in base.columns if c in cf.columns]
        if shared and base[shared].reindex(cf.index).equals(cf[shared]):
            print("  [warn] counterfactual: baseline and swapped predictions are IDENTICAL -- the model did not "
                  "react to the swap. Either it does not consume the swapped column (check --cf-swap against "
                  "your config's feature list) or it is insensitive to it. Any delta below is meaningless.")
    if not base.empty:
        base.to_parquet(cache_base)
    if not cf.empty:
        cf.to_parquet(cache_cf)
    return base, cf


def cf_metrics(p_true, p_base, p_cf, drop_night, night_end_hour, cap, win=None, gccap=None):
    """Take common time points of three series (respecting drop-night + win) -> decomposition metrics. Returns (metrics dict, (times,t,b,c)) or None.
    When gccap is given, also compute the 南网 nanwang_official accuracy for baseline/cf on ALL window points
    (night included, ignoring drop-night, since the 0.2*gccap floor handles zero-power points)."""
    common0 = p_true.index.intersection(p_base.index).intersection(p_cf.index).sort_values()
    if len(common0) == 0:
        return None
    common = common0[night_mask(common0, drop_night, night_end_hour) & window_mask(common0, win)]
    if len(common) == 0:
        return None
    t = p_true.loc[common].to_numpy()
    b = p_base.loc[common].to_numpy()
    c = p_cf.loc[common].to_numpy()
    cap = cap if cap and cap > 0 else (float(np.max(t)) or 1.0)
    nb = rmse(b, t) / cap * 100.0
    nc = rmse(c, t) / cap * 100.0
    m = {"n_points": int(len(common)), "capacity": round(cap, 4),
         "nrmse_base": round(nb, 4), "nrmse_cf": round(nc, 4),
         "delta_nrmse": round(nb - nc, 4),
         "frac_explained": round((nb - nc) / nb * 100.0, 2) if nb > 0 else np.nan,
         "coadapt": int(nb - nc < -0.1)}    # only substantial worsening (>0.1 pct point) counts as co-adaptation, excludes noise-level negative delta
    if gccap is not None and gccap > 0:
        allc = common0[window_mask(common0, win)]            # all points in window, night included
        if len(allc) > 0:
            ta, ba, ca = (p_true.loc[allc].to_numpy(), p_base.loc[allc].to_numpy(), p_cf.loc[allc].to_numpy())
            m["GCCAPCITY"] = round(float(gccap), 4)
            nwb, nwc = nanwang_official(ta, ba, gccap), nanwang_official(ta, ca, gccap)
            if nwb is not None:
                m["nanwang_official_base"] = round(nwb, 4)
            if nwc is not None:
                m["nanwang_official_cf"] = round(nwc, 4)
    return m, (common, t, b, c)


def plot_cf_overview(df, out_dir, swap_label):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from matplotlib.patches import Patch
    _cn_font()
    d = df[np.isfinite(df["nrmse_base"])].sort_values("nrmse_base", ascending=False)
    if d.empty:
        return None
    n = len(d)
    fig, (axL, axR) = plt.subplots(1, 2, figsize=(16, max(7.0, 1.5 + n * 0.5)),
                                   gridspec_kw={"width_ratios": [1.6, 1]})
    # Left: stacked bars -- gray = model floor, orange = GHI attribution, blue = swap-to-truth makes it worse (co-adaptation)
    y = np.arange(n)[::-1]
    for yi, (_, r) in zip(y, d.iterrows()):
        if r.delta_nrmse >= 0:
            axL.barh(yi, r.nrmse_cf, color="#9aa0a6")
            axL.barh(yi, r.delta_nrmse, left=r.nrmse_cf, color="#f28e2b")
            xend = r.nrmse_base
        else:
            axL.barh(yi, r.nrmse_base, color="#9aa0a6")
            axL.barh(yi, r.nrmse_cf - r.nrmse_base, left=r.nrmse_base,
                     color="#4c78a8", hatch="//")
            xend = r.nrmse_cf
        if np.isfinite(r.frac_explained) and r.delta_nrmse >= 0:
            tag = f"  {r.frac_explained:.0f}% explained by {swap_label}"
        elif r.get("coadapt", 0) > 0:
            tag = "  swap-to-truth worse (co-adaptation)"
        else:
            tag = ""
        star = "  baseline not reproduced!" if str(r.status) == "baseline_mismatch" else ""
        axL.text(xend, yi, f" {r.nrmse_base:.1f}%{tag}{star}", va="center", fontsize=7)
    axL.set_yticks(y); axL.set_yticklabels(d.station.astype(str), fontsize=8)
    axL.set_xlim(0, float(max(d.nrmse_base.max(), d.nrmse_cf.max())) * 1.5)
    axL.set_xlabel("power nRMSE (%)")
    axL.legend(handles=[
        Patch(color="#9aa0a6", label=f"model floor (remains after {swap_label} swapped to truth)"),
        Patch(color="#f28e2b", label=f"{swap_label} input attribution (vanishes when swapped to truth)"),
        Patch(facecolor="#4c78a8", hatch="//", label="swap-to-truth is worse (co-adaptation warning)")],
        loc="lower right", fontsize=8)
    axL.set_title(f"Error decomposition: {swap_label} input's fault vs model's fault (sorted by baseline nRMSE desc)",
                  fontsize=12, fontweight="bold")
    axL.grid(axis="x", alpha=0.25)
    # Right: GHI explainable fraction (bar length clipped to [-100,100] to prevent extreme negatives blowing up the x-axis, true value labeled at bar end)
    dr = d[np.isfinite(d["frac_explained"])].sort_values("frac_explained", ascending=False)
    if not dr.empty:
        yr = np.arange(len(dr))[::-1]
        shown = dr.frac_explained.clip(lower=-100.0, upper=100.0)
        axR.barh(yr, shown,
                 color=["#f28e2b" if f >= 0 else "#4c78a8" for f in dr.frac_explained])
        for yi, v, f in zip(yr, shown, dr.frac_explained):
            axR.text(v + (2 if v >= 0 else -2), yi, f"{f:.0f}%", va="center",
                     ha="left" if v >= 0 else "right", fontsize=7,
                     color="#333" if f >= 0 else "#4c78a8")
        axR.set_xlim(-118, 130)
        axR.set_yticks(yr); axR.set_yticklabels(dr.station.astype(str), fontsize=8)
        med = float(np.median(dr.frac_explained))
        axR.axvline(med, color="gray", ls="--", lw=1, label=f"median {med:.0f}%")
        axR.axvline(0, color="#333", lw=0.8)
        axR.legend(loc="lower right", fontsize=8)
    else:
        axR.text(0.5, 0.5, "no data", ha="center", va="center")
    axR.set_xlabel(f"{swap_label} explainable fraction (%)")
    axR.set_title(f"Which stations to push on {swap_label} data source (high fraction = input problem)",
                  fontsize=12, fontweight="bold")
    axR.grid(axis="x", alpha=0.25)
    fig.suptitle(f"Counterfactual -- {swap_label} prediction swapped to truth and re-predicted, how much error vanishes ({n} stations)",
                 fontsize=14, fontweight="bold")
    fig.text(0.01, 0.005,
             f"Note: (1) delta~0 does not mean {swap_label} forecast is fine -- the model may be insensitive to it or already co-adapted; "
             f"(2) 'model floor' includes error from other truthless inputs (e.g. temperature), it is an upper bound on the model's own error.",
             fontsize=8, color="#666")
    fig.tight_layout(rect=(0, 0.03, 1, 0.96))
    path = os.path.join(out_dir, "counterfactual_overview.png")
    fig.savefig(path, dpi=120); plt.close(fig)
    return path


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
    got = cf_metrics(truth, p_base, p_cf, args.drop_night, args.night_end_hour, cap, win, gccap)
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
        bvp = rmse(al[1], al[2]) / cap * 100.0
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


# ================================================================ One window's full analysis (per-station + fleet)
def run_analysis(inp, pred, args, step, active_pairs, have_ghi, cap_map, gccap_map, city_map,
                 out_dir, win, label, cf_base=None, cf_swap_pred=None, swap_label="GHI", raw_hist=None):
    """对单个窗口 [start,end)（label='D+1'/'D+4'，用于日志前缀）跑完整的每站 + 舰队分析，产物写入 out_dir。
    gccap_map={station: GCCAPCITY}（来自 --info-csv）时补 GCCAPCITY + nanwang_official_power 列，
    fleet_ranking.csv 另加 NANWANG_FACTORS 的 factor 扫描列；city_map={station: city} 时 fleet_ranking.csv 补 city 列。
    cf_base/cf_swap_pred（本地推理的基线与换真值预测，dtime×predict_power_<站>）给出时，右下功率面板加画反事实线，
    fleet_ranking.csv/station_power_rmse.csv 补 power_*_cf、delta_nrmse、frac_explained、nanwang_official_power_cf。
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
                cap = cap_map.get(str(st)) or cap_map.get(st) or float(np.max(t))
                cap = cap if cap and cap > 0 else 1.0

                # ---- Counterfactual (local inference): extra panel line + decomposition vs the LOCAL baseline ----
                extra_lines = []
                if cf_swap_pred is not None:
                    cfrow, extra_lines = cf_station(st, truth, pred[col].dropna(), cf_base, cf_swap_pred,
                                                    args, cap, win, gc, swap_label)
                    rec.update(cfrow)
                    prow.update({k: v for k, v in cfrow.items()
                                 if k in ("cf_status", "power_rmse_cf", "power_nrmse_cf",
                                          "nanwang_official_power_cf")})
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
                # Theil three-way split + scatter calibration (systematic offset / high-value compression)
                th = theil_shares(t, p)
                sc = scatter_stats(t, p)
                if th:
                    rec.update(theil_u_bias=round(th[0], 3), theil_u_var=round(th[1], 3),
                               theil_u_cov=round(th[2], 3))
                if sc:
                    rec.update(slope=round(sc["slope"], 3), r2=round(sc["r2"], 3),
                               high_bias_pct=round(sc["high_bias"] / cap * 100, 4))

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
                        if raw is not None and not raw.empty:
                            raw = raw[(raw.index >= hs.index.min()) & (raw.index <= hs.index.max())]
                            if not raw.empty:
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
                    gcap = float(np.max(tvg)) or 1.0
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
    fleet_img = theil_img = None
    if not args.no_fleet and ("power_nrmse" in fdf.columns or "ghi_nrmse" in fdf.columns):
        if "power_nrmse" in fdf.columns:
            fdf["power_outlier"] = flag_outliers(fdf["power_nrmse"].to_numpy(), args.mad_k)
            fdf["power_rank"] = fdf["power_nrmse"].rank(ascending=False, method="min").astype("Int64")
        sort_col = "power_nrmse" if "power_nrmse" in fdf.columns else "station"
        fdf.sort_values(sort_col, ascending=(sort_col == "station")).to_csv(
            os.path.join(out_dir, "fleet_ranking.csv"), index=False)
        if not args.no_plots:
            ddf = fdf if sel is None else fdf[fdf["station"].isin(sel)]
            dh = hourly if sel is None else {s: h for s, h in hourly.items() if s in sel}
            note = "" if sel is None else f"   [focused on worst {len(ddf)} of {len(fdf)} stations]"
            fleet_img = plot_dashboard(ddf, dh, have_ghi, args, out_dir, note)
            if "theil_u_bias" in ddf.columns:
                theil_img = plot_theil_overview(ddf, out_dir, note)

    # ---------------- Counterfactual fleet decomposition (same records, decomposition vocabulary) ----------------
    if cf_swap_pred is not None and "cf_status" in fdf.columns:
        okd = fdf[fdf["cf_status"].isin(["ok", "baseline_mismatch"])].rename(
            columns={"power_nrmse_localbase": "nrmse_base", "power_nrmse_cf": "nrmse_cf",
                     "cf_status": "status"})
        if not okd.empty:
            if not args.no_plots:
                plot_cf_overview(okd, out_dir, swap_label)
            cf_report_summary(okd, swap_label, pfx)

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
    if "theil_u_bias" in fdf.columns:
        show = fdf[np.isfinite(pd.to_numeric(fdf["theil_u_bias"], errors="coerce"))]
        if sel is not None:
            show = show[show["station"].isin(sel)]
        if "power_nrmse" in show.columns:
            show = show.sort_values("power_nrmse", ascending=False)
        show = show.head(args.worst_only or 5)
        if not show.empty:
            print("  Theil / scatter reading (candidates only -- conclusions go through the playbook gates):")
        for _, r in show.iterrows():
            dom = max((("u_bias", r["theil_u_bias"]), ("u_var", r["theil_u_var"]), ("u_cov", r["theil_u_cov"])),
                      key=lambda x: x[1])
            hint = {"u_bias": "systematic level offset (cheapest fix: output shift)",
                    "u_var": "amplitude mismatch (calibration/capacity assumption)",
                    "u_cov": "shape/timing mismatch (check time shift / structure)"}[dom[0]]
            sl, hb = r.get("slope", np.nan), r.get("high_bias_pct", np.nan)
            comp = (f";  slope={sl:.2f} & top-20% truth bias {hb:+.1f}% -> high-value compression candidate"
                    if np.isfinite(sl) and sl < 0.9 and np.isfinite(hb) and hb < 0 else "")
            print(f"    {r['station']}: u_bias/u_var/u_cov = {r['theil_u_bias']:.0%}/{r['theil_u_var']:.0%}/"
                  f"{r['theil_u_cov']:.0%} -> {hint}"
                  f"  (bias {r.get('power_bias_pct', float('nan')):+.2f}%){comp}")
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
    if theil_img:
        prod.append("theil_decomposition.png")
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


# ================================================================ Main flow: compute both layers in one pass
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
    args = ap.parse_args()
    step = pd.Timedelta(minutes=15)
    feature_pairs = parse_feature_pairs(args.feature_pairs)
    cap_map = parse_capacity(args.capacity)

    if not args.predict and not args.counterfactual:
        raise SystemExit("--predict is required unless --counterfactual is given "
                         "(with it, the local baseline inference supplies the predictions instead)")

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
    swap_label = "GHI"
    if args.counterfactual:
        missing = [f for f, v in (("--checkpoints-dir", args.checkpoints_dir),
                                  ("--config", args.config)) if not v]
        if missing:
            raise SystemExit(f"--counterfactual needs {', '.join(missing)} "
                             f"(passed straight to multi_station_inference)")
        swap = parse_cf_swap(args.cf_swap)
        swap_label = "+".join(p[: -len("_predict")] if p.endswith("_predict") else p for p in swap)
        cf_base, cf_swap_pred = cf_build_predictions(inp, args, swap)
        if cf_swap_pred is None or cf_swap_pred.empty:
            print("  [warn] counterfactual produced no predictions -> continuing without it")
            cf_base = cf_swap_pred = None

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
            import history_avail_power
            # 线长 = 所有起报窗 672 点摊平去重后的并集，起报日越多线越长；单起报日才恰好 7 天。
            # 文件夹数是「要开几个 txt」，跨度落在自然日边界内侧时比天数多 1，别把两者看成一回事。
            ndays = len(pd.date_range(span[0].normalize(), span[1].normalize(), freq="D"))
            nwin = int(pd.Series(inp[args.win_col].to_numpy()).nunique())
            print(f"  [hist-raw] span {span[0]:%Y-%m-%d %H:%M} -> {span[1]:%Y-%m-%d %H:%M} = "
                  f"{(span[1] - span[0]) / pd.Timedelta('1D') + 1 / 96:.1f} days "
                  f"(union of {nwin} 起报日; opening {ndays} date folder(s)), Tjlx={args.hist_tjlx}")
            raw_hist = history_avail_power.load_raw_history(
                args.hist_root, pd.unique(inp[args.station_col]), span[0], span[1], args.hist_tjlx)

    for label, start, end in windows:
        sub_out = os.path.join(report_root, label)
        os.makedirs(sub_out, exist_ok=True)
        run_analysis(inp, pred, args, step, active_pairs, have_ghi, cap_map, gccap_map, city_map,
                     sub_out, (start, end), label, cf_base, cf_swap_pred, swap_label, raw_hist)


if __name__ == "__main__":
    main()
