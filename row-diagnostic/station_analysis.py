#!/usr/bin/env python3
"""PV multi-station forecast analysis -- one script, one run, produces two-layer views. Fully self-contained (pandas/numpy/matplotlib).

[Per-station detail] For each station, several two-line comparison plots (predicted vs true), annotated with RMSE:
  1) Power    -- predicted power (predict table: dtime x per-station columns named by --pred-col-template,
     default predict_power_{station}, bare station name as fallback) vs true power (observe_power_future in input).
  2) Features -- predicted feature vs true feature, both in the input wide table (list columns). Default 1 plot:
     GHI = GHI_SOLARGIS_predict vs GHI_real_future (the latter is the common true label for these predicted quantities).
     --feature-pairs can add more, e.g. ssrd_pos_1_predict:GHI_real_future:ssrd1.
  3) Scatter  -- station_*_scatter.png: true-vs-pred power scatter + OLS fit + decile-bin means, answering
     "systematically high/low? high values compressed?" (slope<1 + negative top-20% bias = compression candidate);
     textbox carries Theil u_bias/u_var/u_cov shares.

[Fleet overview] A single fleet_overview.png (2x2 dashboard) + fleet_ranking.csv, to locate "who is most off":
  A1/A2 rankings -- stations sorted by nRMSE descending (worst on top), median line + outlier stations flagged red (power + GHI).
  B  scatter     -- GHI-nRMSE vs power-nRMSE, one point per station: is the power error due to GHI input error (top-right)
                    or model/other issues (top-left = GHI good but power still bad).
  C  heatmap     -- time-of-day x station power nRMSE, see who is bad at which hour.
  Plus theil_decomposition.png -- per-station 100%-stacked Theil split of power MSE (u_bias level offset /
  u_var amplitude mismatch / u_cov shape-timing mismatch; dominant >=50% points at the fix); shares, slope, r2,
  high_bias_pct also land in fleet_ranking.csv.

Why normalize (key): absolute RMSE is dominated by plant scale (big plants are naturally big, ranking is meaningless).
  nRMSE = RMSE / that station's peak power (self-contained proxy capacity; use --capacity if real installed capacity is available), unit %.
  "Off" = ranks high in nRMSE **and** is abnormally above the fleet (> median + --mad-k x MAD, default 3, flagged red).
  Only observe_power_future (power truth) and GHI_real_future (GHI truth) two labels are used --
  columns with no truth (e.g. temperature) cannot be scored; the overview does not involve them.

Robust (key): each plot / each metric succeeds or fails independently. If a column is missing, or **a station's** column is entirely empty ->
  only that one item is skipped with a warning; power and other stations/features/overview are still output, never a whole-run error.

[Counterfactual] (--counterfactual gated, optional) oracle GHI swap: replace the GHI predicted column with the GHI truth,
  re-predict via the user's unified FastAPI model, decompose each station's error = model floor (remains even with perfect GHI) + GHI attribution (vanishes when swapped to truth).
  2 calls per station: baseline reproduction (send original features as-is, cross-check with predict table = reproduction gate) + swap to truth. Written to disk per station, resumable.
  First run requires --cf-dry-run to confirm the payload. Produces counterfactual_results.csv +
  counterfactual_overview.png (stacked bars: gray = model's fault, orange = GHI input's fault, blue = swapping to truth makes it worse = co-adaptation).
  API contract: POST {"data":[{row dict}]} (fields = parquet column names, list as-is, without station name and truth label columns);
  response = {"status":..., "predictions":[{"timestamp_win":..., "ensemble":[192 values]}, ...]} --
  returned per window, take only ensemble, flatten and dedup by the response's own timestamp_win (same rule as input table);
  n_windows != n_sent_rows = alignment gate catches it. Backward-compatible fallback: response may also be a single flat power list (matched pointwise
  to that station's predict-table column by dtime sort order).

Time alignment: if input row timestamp_win=T, then for any list column (observe_power_future / *_predict /
  GHI_real_future) the k-th element's time = T+15min x (k+1) (first element = T+15min). Flatten windows per station, groupby absolute
  time and dedup into a continuous series; the power prediction is further aligned to predict-table dtime.

Config: --drop-night removes each day's 00:00-night_end_hour (RMSE is also computed after removal); --tick-hours one x tick
  every few hours; plot width auto-adapts to point count, spreads out even 600+ points. Switches: --no-plots (no plots at all, still writes CSV),
  --no-station-plots (no per-station curves, still writes station-level CSV), --no-fleet (no overview and no fleet_ranking).
  --worst-only N: draw images only for the worst N stations by power nRMSE -- ranking is computed on the FULL fleet first,
  then per-station curves and all dashboard panels are restricted to those stations; CSVs still cover every station.

Output layout (everything under one --out-dir, default station_analysis_out/):
  <out-dir>/                     overview pngs (fleet_overview / theil_decomposition / counterfactual_overview) + all CSVs
  <out-dir>/stations/            per-station pngs (Power / feature curves, scatter, counterfactual three-line)
  --short mode nests one level deeper under the 起报日: <out-dir>/<YYYYMMDD>/{D+1,D+4,history}/, each D+1/D+4
  carrying the same overview+stations layout above; history/ holds plots only (see below).
  All plots draw automatically on every run -- no extra flag for Theil or scatter; --no-plots / --no-station-plots /
  --no-fleet turn layers off, --worst-only restricts which stations get images.

Usage:
  python3 station_analysis.py --input input.parquet --predict predict.parquet [--out-dir OUT]
    [--drop-night --night-end-hour 5] [--tick-hours 1] [--step-min 15]
    [--feature-pairs "GHI_SOLARGIS_predict:GHI_real_future:GHI,ssrd_pos_1_predict:GHI_real_future:ssrd1"]
    [--top-n 30] [--mad-k 3] [--capacity "st1:500,st2:5"] [--ghi-pred ... --ghi-true ...]
    [--station-col station --win-col timestamp_win --power-col observe_power_future --dtime-col dtime]
    [--no-plots] [--no-station-plots] [--no-fleet] [--worst-only 5]
    [--counterfactual --api-url URL [--cf-dry-run] [--cf-stations st1,st2] [--cf-force]
     [--cf-swap "GHI_SOLARGIS_predict:GHI_real_future"] [--cf-exclude-cols ...]
     [--cf-timeout 120] [--cf-retries 1] [--cf-check-tol 1.0] [--cf-curves]]
    [--short [--date 2026-07-26]]   # 短期：D+1/D+4 两个 24h 切片，各产一套到 out_dir/D+1、out_dir/D+4
"""
from __future__ import annotations

import argparse
import json
import os
import urllib.request

import numpy as np
import pandas as pd

DEFAULT_FEATURE_PAIRS = [("GHI_SOLARGIS_predict", "GHI_real_future", "GHI")]


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


def _display(a: pd.Series, b: pd.Series, drop_night, night_end_hour, win=None, fill=0.0):
    """PLOT-ONLY: union of both series' timestamps (within win, minus night), reindex both, fill gaps with `fill`.
    Metrics keep using _aligned (intersection); this only makes the two lines span the full window so gaps are
    visible instead of silently dropped. Reindex is by timestamp, so the two lines always share one x-axis."""
    idx = a.index.union(b.index).sort_values()
    keep = night_mask(idx, drop_night, night_end_hour) & window_mask(idx, win)
    idx = idx[keep]
    if len(idx) == 0:
        return None
    return idx, a.reindex(idx).fillna(fill).to_numpy(), b.reindex(idx).fillna(fill).to_numpy()


def rmse(a, b):
    return float(np.sqrt(np.mean((a - b) ** 2)))


def resolve_pred_col(st, pred, template):
    """Station -> predict-table column name: try the template (e.g. predict_power_{station}) first,
    then the bare station name (old-style tables). None = this station has no column (caller warns + skips)."""
    for cand in (template.format(station=st), st, str(st)):
        if cand in pred.columns:
            return cand
    return None


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


# ================================================================ Per-station two-line comparison plot
def plot_two_lines(st, name, times, true_v, pred_v, rmse_v, out_dir,
                   tick_hours, true_label, pred_label, n_real=None):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.dates as mdates
    import matplotlib.pyplot as plt
    _cn_font()

    times = pd.DatetimeIndex(times)
    n_hours = max(1.0, (times[-1] - times[0]).total_seconds() / 3600.0)
    width = min(60.0, max(16.0, n_hours * 0.3))       # auto-adapt to time span, spreads out even 600+ points
    fig, ax = plt.subplots(figsize=(width, 6))
    ax.plot(times, true_v, label=true_label, color="#1f77b4", lw=1.3)
    ax.plot(times, pred_v, label=pred_label, color="#d62728", lw=1.1, alpha=0.85)
    ax.fill_between(times, true_v, pred_v, color="#d62728", alpha=0.12)
    n_scored = len(times) if n_real is None else n_real
    gap_note = f", {len(times) - n_scored} gaps filled 0" if n_scored < len(times) else ""
    ax.set_title(f"Station {st}  -  {name}   RMSE={rmse_v:.3f}   "
                 f"start {times[0]:%Y-%m-%d %H:%M}   (n={n_scored} scored{gap_note})",
                 fontsize=13, fontweight="bold")
    ax.xaxis.set_major_locator(mdates.HourLocator(interval=max(1, int(tick_hours))))
    ax.xaxis.set_major_formatter(mdates.DateFormatter("%m-%d %H:%M"))
    plt.setp(ax.get_xticklabels(), rotation=90, fontsize=7)
    ax.set_xlabel("time"); ax.set_ylabel(name); ax.legend(loc="upper right"); ax.grid(alpha=0.25)
    fig.tight_layout()
    path = os.path.join(_station_dir(out_dir), f"station_{sanitize(st)}_{sanitize(name)}.png")
    fig.savefig(path, dpi=110); plt.close(fig)
    return path


def _station_dir(out_dir):
    """Per-station images live in <out_dir>/stations/ so the root stays browsable (overview pngs + CSVs only)."""
    d = os.path.join(out_dir, "stations")
    os.makedirs(d, exist_ok=True)
    return d


def plot_scatter(st, t, p, sc, th, cap, out_dir):
    """True-vs-pred power scatter: y=x + OLS fit + decile-bin means; textbox carries bias / top-20% bias / Theil shares.
    slope<1 with negative top-bin bias = high-value compression candidate (candidate only, per recipe discipline)."""
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    _cn_font()
    t, p = np.asarray(t, float), np.asarray(p, float)
    fig, ax = plt.subplots(figsize=(7.5, 7))
    ax.scatter(t, p, s=9, alpha=0.35, color="#4c78a8", edgecolors="none", label="15-min points")
    lo = min(0.0, float(np.min(t)), float(np.min(p)))
    hi = max(float(np.max(t)), float(np.max(p))) * 1.05 or 1.0
    ax.plot([lo, hi], [lo, hi], ls="--", lw=1.2, color="#333", label="y = x (perfect)")
    xs = np.array([lo, hi])
    ax.plot(xs, sc["slope"] * xs + sc["intercept"], color="#d62728", lw=1.5,
            label=f"fit: pred = {sc['slope']:.2f} x true {sc['intercept']:+.1f}")
    edges = np.quantile(t, np.linspace(0, 1, 11))            # decile-bin means: a bend = that power band is off
    idx = np.clip(np.searchsorted(edges, t, side="right") - 1, 0, 9)
    bt = [float(np.mean(t[idx == i])) for i in range(10) if (idx == i).any()]
    bp = [float(np.mean(p[idx == i])) for i in range(10) if (idx == i).any()]
    ax.plot(bt, bp, "o-", color="#f28e2b", lw=1.8, ms=5, label="decile-bin mean")
    bias = float(np.mean(p - t)) / cap * 100.0
    hb = sc["high_bias"] / cap * 100.0
    txt = (f"slope = {sc['slope']:.3f}   R$^2$ = {sc['r2']:.3f}\n"
           f"overall bias = {bias:+.2f}% of cap\n"
           f"top-20% truth bias = {hb:+.2f}% of cap")
    if th:
        txt += f"\nTheil: u_bias {th[0]:.0%} / u_var {th[1]:.0%} / u_cov {th[2]:.0%}"
    ax.text(0.02, 0.98, txt, transform=ax.transAxes, va="top", fontsize=9,
            bbox=dict(boxstyle="round", fc="white", ec="#999", alpha=0.85))
    flag = "\ncandidate: high-value compression (slope<0.9, top-bin bias<0)" if sc["slope"] < 0.9 and hb < 0 else ""
    ax.set_title(f"Station {st} - true vs pred power{flag}", fontsize=12, fontweight="bold")
    ax.set_xlabel("observed power (true)"); ax.set_ylabel("predicted power")
    ax.set_xlim(lo, hi); ax.set_ylim(lo, hi)
    ax.legend(loc="lower right", fontsize=8); ax.grid(alpha=0.25)
    fig.tight_layout()
    path = os.path.join(_station_dir(out_dir), f"station_{sanitize(st)}_scatter.png")
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


# ================================================================ Counterfactual (oracle GHI swap)
CF_COLS = ["station", "status", "n_points", "capacity", "nrmse_base", "nrmse_cf",
           "delta_nrmse", "frac_explained", "base_vs_parquet_pct", "coadapt"]


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


def _jsonable(v):
    """parquet cell -> JSON-able: Timestamp->ISO string, array/list->list, NaN->None."""
    if isinstance(v, pd.Timestamp):
        return v.isoformat()
    if v is None:
        return None
    if np.ndim(v) > 0:
        arr = np.asarray(v, dtype=float).ravel()
        return [float(x) if np.isfinite(x) else None for x in arr]
    if isinstance(v, (bool, np.bool_)):
        return bool(v)
    if isinstance(v, (int, np.integer)):
        return int(v)
    if isinstance(v, (float, np.floating)):
        return float(v) if np.isfinite(v) else None
    return str(v)


def cf_build_payload(sub: pd.DataFrame, exclude: set, swap: dict | None):
    """One station's window rows -> {"data": [row dict]}. Field names = parquet column names; when swap is given,
    the swapped column's field name is unchanged, value taken from the same row's truth column (oracle replacement)."""
    rows = []
    for _, r in sub.iterrows():
        d = {}
        for col in sub.columns:
            if col in exclude:
                continue
            src = swap.get(col, col) if swap else col
            d[col] = _jsonable(r[src])
        rows.append(d)
    return {"data": rows}


def _payload_skeleton(payload, n_preview=4):
    lines = []
    for k, v in payload["data"][0].items():
        if isinstance(v, list):
            prev = ", ".join("None" if x is None else f"{x:.4g}" for x in v[:n_preview])
            lines.append(f"    {k}: list[{len(v)}]  [{prev}, ...]")
        else:
            lines.append(f"    {k}: {type(v).__name__}  {v!r}")
    return "\n".join(lines)


def _extract_response(obj):
    """Parse the API response, return (kind, data):
    (1) per-window (real contract): "predictions": [{"timestamp_win":..., "ensemble":[192 values]}, ...]
       -> ("windows", [(Timestamp, list), ...]), take only ensemble, ignore other keys.
    (2) flat list (compat fallback): bare list or {"prediction":[...]} -> ("flat", [...])."""
    if isinstance(obj, dict):
        preds = obj.get("predictions")
        if isinstance(preds, list) and preds and isinstance(preds[0], dict):
            out = []
            for p in preds:
                if "timestamp_win" not in p or "ensemble" not in p:
                    raise RuntimeError(f"response predictions element missing timestamp_win/ensemble key"
                                       f"(actual keys: {list(p)[:6]})")
                out.append((pd.Timestamp(p["timestamp_win"]), p["ensemble"]))
            return "windows", out
    if isinstance(obj, list):
        return "flat", obj
    if isinstance(obj, dict):
        for k in ("prediction", "predictions", "result", "power", "data", "output"):
            if isinstance(obj.get(k), list):
                return "flat", obj[k]
        for v in obj.values():
            if isinstance(v, list):
                return "flat", v
    raise RuntimeError(f"cannot extract predictions from API response (response keys: "
                       f"{list(obj)[:5] if isinstance(obj, dict) else type(obj).__name__})")


def cf_call_api(url, payload, timeout, retries):
    body = json.dumps(payload).encode()
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))  # intranet API direct connection, bypass system proxy
    last = None
    for _ in range(int(retries) + 1):
        try:
            req = urllib.request.Request(url, data=body,
                                         headers={"Content-Type": "application/json"})
            with opener.open(req, timeout=timeout) as resp:
                return _extract_response(json.loads(resp.read().decode()))
        except Exception as e:                        # noqa: BLE001 -- re-raise uniformly after retries
            last = e
    raise RuntimeError(f"API call failed (after {retries} retries): {last}")


def cf_series(kind, data, dtimes, n_sent, step):
    """API response -> power series with absolute timestamps. Misaligned -> (None, reason).
    windows: validate n_returned_windows = n_sent_rows, flatten and dedup by the response's own timestamp_win
             (same rule as input table: T+step x (k+1), overlapping windows averaged).
    flat   : validate length = that station's non-empty dtime count in predict table, matched pointwise."""
    if kind == "windows":
        if len(data) != n_sent:
            return None, f"returned {len(data)} windows != sent {n_sent} windows"
        wins = [t for t, _ in data]
        lists = [[np.nan if v is None else float(v) for v in lst] for _, lst in data]
        s = series_from_lists(wins, lists, step)
        if s.empty:
            return None, "all windows' ensemble empty"
        return s, ""
    if data is None or len(data) != len(dtimes):
        return None, f"returned {0 if data is None else len(data)} points != predict table {len(dtimes)} points"
    return pd.Series([np.nan if v is None else float(v) for v in data], index=dtimes), ""


def cf_metrics(p_true, p_base, p_cf, drop_night, night_end_hour, cap, win=None):
    """Take common time points of three series (respecting drop-night + win) -> decomposition metrics. Returns (metrics dict, (times,t,b,c)) or None."""
    common = p_true.index.intersection(p_base.index).intersection(p_cf.index).sort_values()
    if len(common) == 0:
        return None
    common = common[night_mask(common, drop_night, night_end_hour) & window_mask(common, win)]
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
    return m, (common, t, b, c)


def _cf_append(path, row):
    pd.DataFrame([{c: row.get(c, "") for c in CF_COLS}]).to_csv(
        path, mode="a", header=not os.path.exists(path), index=False)


def plot_cf_curves(st, times, t, b, c, out_dir, tick_hours):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.dates as mdates
    import matplotlib.pyplot as plt
    _cn_font()
    times = pd.DatetimeIndex(times)
    n_hours = max(1.0, (times[-1] - times[0]).total_seconds() / 3600.0)
    fig, ax = plt.subplots(figsize=(min(60.0, max(16.0, n_hours * 0.3)), 6))
    ax.plot(times, t, label="observed power", color="#1f77b4", lw=1.4)
    ax.plot(times, b, label="baseline pred (API, original features)", color="#d62728", lw=1.1, alpha=0.85)
    ax.plot(times, c, label="counterfactual pred (GHI->truth)", color="#2ca02c", lw=1.1, alpha=0.85)
    ax.set_title(f"Station {st} - counterfactual   base RMSE={rmse(b, t):.3f} -> "
                 f"cf RMSE={rmse(c, t):.3f}", fontsize=13, fontweight="bold")
    ax.xaxis.set_major_locator(mdates.HourLocator(interval=max(1, int(tick_hours))))
    ax.xaxis.set_major_formatter(mdates.DateFormatter("%m-%d %H:%M"))
    plt.setp(ax.get_xticklabels(), rotation=90, fontsize=7)
    ax.legend(loc="upper right"); ax.grid(alpha=0.25)
    fig.tight_layout()
    path = os.path.join(_station_dir(out_dir), f"station_{sanitize(st)}_counterfactual.png")
    fig.savefig(path, dpi=110); plt.close(fig)
    return path


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


def run_counterfactual(inp, pred, args, cap_map, step, out_dir=None, win=None):
    """Orchestration: 2 API calls per station (baseline reproduction + swap to truth), written to disk per station, resumable.
    out_dir defaults to args.out_dir; win=(start,end) restricts cf_metrics to that window (None = whole series)."""
    out_dir = out_dir if out_dir is not None else args.out_dir
    swap = parse_cf_swap(args.cf_swap)
    miss = sorted({c for pair in swap.items() for c in pair if c not in inp.columns})
    if miss:
        print(f"  [warn] counterfactual skipped: --cf-swap columns missing {miss}")
        return
    exclude = {c.strip() for c in args.cf_exclude_cols.split(",") if c.strip()}
    exclude.add(args.station_col)
    exclude |= set(swap.values())               # truth columns are labels, not sent as fields

    stations = [s for s in pd.unique(inp[args.station_col])
                if resolve_pred_col(s, pred, args.pred_col_template) is not None]
    if args.cf_stations:
        want = {s.strip() for s in args.cf_stations.split(",")}
        stations = [s for s in stations if str(s) in want]
    if not stations:
        print("  [warn] counterfactual: no runnable stations (station name must be in both input and predict tables)")
        return

    csv_path = os.path.join(out_dir, "counterfactual_results.csv")
    if args.cf_force and os.path.exists(csv_path):
        os.remove(csv_path)
    done = set()
    if os.path.exists(csv_path):
        prev = pd.read_csv(csv_path)
        done = set(prev[prev["status"].isin(["ok", "baseline_mismatch"])]["station"].astype(str))
    todo = [s for s in stations if str(s) not in done]
    swap_label = "+".join(p[: -len("_predict")] if p.endswith("_predict") else p for p in swap)
    print(f"[counterfactual] plan: stations x{len(stations)} (resume skips {len(stations) - len(todo)}), "
          f"2 calls per station (baseline reproduction + {swap_label} swap to truth) = {len(todo) * 2} calls total")

    if args.cf_dry_run:
        st0 = todo[0] if todo else stations[0]
        sub0 = inp[inp[args.station_col] == st0].sort_values(args.win_col)
        pl = cf_build_payload(sub0, exclude, None)
        print(f"  -- dry-run (zero HTTP): payload skeleton for station {st0} "
              f"(data has {len(pl['data'])} rows, fields = parquet column names, first row shown only) --")
        print(_payload_skeleton(pl))
        print("  counterfactual call's only difference from baseline: " +
              "; ".join(f"{p}'s value swapped to same-row {t}" for p, t in swap.items()))
        print("  after confirming the format, remove --cf-dry-run to run for real.")
        return
    if not args.api_url:
        raise SystemExit("--counterfactual real run requires --api-url (or --cf-dry-run first to check payload)")

    for st in todo:
        col = resolve_pred_col(st, pred, args.pred_col_template)   # non-None: the station list was filtered above
        sub = inp[inp[args.station_col] == st].sort_values(args.win_col)
        pq = pred[col].dropna()
        dtimes = pq.index.sort_values()
        try:
            kind, data = cf_call_api(args.api_url, cf_build_payload(sub, exclude, None),
                                     args.cf_timeout, args.cf_retries)
            p_base, why = cf_series(kind, data, dtimes, len(sub), step)
            if p_base is None:
                print(f"  [warn] station {st}: baseline API output misaligned ({why}), skipped")
                _cf_append(csv_path, {"station": st, "status": "align_mismatch"})
                continue
            kind, data = cf_call_api(args.api_url, cf_build_payload(sub, exclude, swap),
                                     args.cf_timeout, args.cf_retries)
            p_cf, why = cf_series(kind, data, dtimes, len(sub), step)
            if p_cf is None:
                print(f"  [warn] station {st}: counterfactual API output misaligned ({why}), skipped")
                _cf_append(csv_path, {"station": st, "status": "align_mismatch"})
                continue
        except RuntimeError as e:
            print(f"  [warn] station {st}: {e}")
            _cf_append(csv_path, {"station": st, "status": "api_error"})
            continue
        truth = series_from_lists(sub[args.win_col].to_numpy(),
                                  sub[args.power_col].to_numpy(), step)
        cap = cap_map.get(str(st)) or cap_map.get(st)
        got = cf_metrics(truth, p_base, p_cf, args.drop_night, args.night_end_hour, cap, win)
        if got is None:
            print(f"  [warn] station {st}: no common time points between truth and API output, skipped")
            _cf_append(csv_path, {"station": st, "status": "no_overlap"})
            continue
        m, (times, t, b, c) = got
        al_pq = _aligned(p_base, pq, args.drop_night, args.night_end_hour, win)   # reproduction gate: compare on common time points, windowed in --short
        bvp = rmse(al_pq[1], al_pq[2]) / m["capacity"] * 100.0 if al_pq else float("inf")
        m["base_vs_parquet_pct"] = round(bvp, 4) if np.isfinite(bvp) else ""
        m["status"] = "ok" if bvp <= args.cf_check_tol else "baseline_mismatch"
        if m["status"] == "baseline_mismatch":
            print(f"  [warn] station {st}: API baseline differs from predict table by {bvp:.2f}% (>{args.cf_check_tol}%)"
                  " -- contract/alignment may be off, decomposition still computed on API baseline")
        m["station"] = st
        _cf_append(csv_path, m)
        if args.cf_curves and not args.no_plots:
            plot_cf_curves(st, times, t, b, c, out_dir, args.tick_hours)
        print(f"  station {st}: nRMSE baseline {m['nrmse_base']:.2f}% -> swap-to-truth {m['nrmse_cf']:.2f}%   "
              f"delta={m['delta_nrmse']:+.2f}%"
              + (f" ({m['frac_explained']:.0f}% explained by {swap_label})"
                 if np.isfinite(m['frac_explained']) else ""))

    # ---- Summary: plot + conclusion overview (including stations completed in earlier resume runs) ----
    if not os.path.exists(csv_path):
        return
    res = pd.read_csv(csv_path).drop_duplicates("station", keep="last")
    okd = res[res["status"].isin(["ok", "baseline_mismatch"])].copy()
    for c in ("nrmse_base", "nrmse_cf", "delta_nrmse", "frac_explained", "coadapt"):
        if c in okd:
            okd[c] = pd.to_numeric(okd[c], errors="coerce")
    img = None
    if not okd.empty and not args.no_plots:
        img = plot_cf_overview(okd, out_dir, swap_label)
    n_bad = len(res) - len(okd)
    print(f"[counterfactual] done: ok/reproduction-warning x{len(okd)}"
          + (f", failed/misaligned x{n_bad}" if n_bad else "")
          + f" -> counterfactual_results.csv" + (" + counterfactual_overview.png" if img else ""))
    if not okd.empty:
        good = okd[np.isfinite(okd["frac_explained"])]
        if not good.empty:
            top_in = good.sort_values("frac_explained", ascending=False).head(2)
            print("  biggest input problem (swap-to-truth improves most): " +
                  ", ".join(f"{r.station}({r.frac_explained:.0f}%)" for _, r in top_in.iterrows()))
        top_md = okd[np.isfinite(okd["nrmse_cf"])].sort_values("nrmse_cf", ascending=False).head(2)
        if not top_md.empty:
            print("  biggest model problem (high residual error even after swap-to-truth): " +
                  ", ".join(f"{r.station}({r.nrmse_cf:.2f}%)" for _, r in top_md.iterrows()))
        co = okd[okd["coadapt"].fillna(0) > 0]
        if not co.empty:
            print(f"  co-adaptation warning (swap-to-truth is worse): {co.station.tolist()}")


# ================================================================ One window's full analysis (per-station + fleet)
def run_analysis(inp, pred, args, step, active_pairs, have_ghi, cap_map, out_dir, win, label):
    """Run the full per-station + fleet analysis for ONE window into out_dir.
    win=(start,end) restricts every aligned series to [start,end); win=None = whole series.
    label prefixes log lines ('D+1'/'D+4'); None = default single pass."""
    pfx = f"[{label}] " if label else ""
    plot_station = not (args.no_plots or args.no_station_plots)
    stations = list(pd.unique(inp[args.station_col]))
    power_rows, feat_rows, imgs = [], [], []
    fleet_recs, hourly = [], {}
    plot_jobs = []              # per-station plots deferred: --worst-only must rank the full fleet before drawing
    scatter_jobs = []           # (st, t, p, sc, th, cap) -- true-vs-pred scatter, same deferred treatment

    for st in stations:
        sub = inp[inp[args.station_col] == st]
        wins = sub[args.win_col].to_numpy()
        cache = {}

        def ser(col):                                 # per-station column memoization: flatten each column only once
            if col not in cache:
                cache[col] = series_from_lists(wins, sub[col].to_numpy(), step)
            return cache[col]

        rec = {"station": st}

        # ---- Power (prediction from predict table) ----
        truth = ser(args.power_col)
        col = resolve_pred_col(st, pred, args.pred_col_template)
        if col is None:
            print(f"  [warn] station {st}: predict table has no column "
                  f"'{args.pred_col_template.format(station=st)}' (nor the bare station name), skip Power plot")
        else:
            al = _aligned(truth, pred[col].dropna(), args.drop_night, args.night_end_hour, win)
            if al is None:
                print(f"  [warn] station {st}: Power truth/pred have no common time points (or all removed as night), skipped")
            else:
                times, t, p = al
                rv = rmse(p, t)
                power_rows.append({"station": st, "power_rmse": round(rv, 6),
                                   "n_points": int(len(times)),
                                   "t_start": str(times.min()), "t_end": str(times.max())})
                if plot_station:
                    disp = _display(truth, pred[col].dropna(), args.drop_night, args.night_end_hour, win) \
                           or (times, t, p)
                    plot_jobs.append((st, "Power", disp[0], disp[1], disp[2], rv,
                                      "observed power", "predicted power", int(len(times))))
                # Overview: power nRMSE / bias / hourly
                cap = cap_map.get(str(st)) or cap_map.get(st) or float(np.max(t))
                cap = cap if cap and cap > 0 else 1.0
                rec.update(power_rmse=round(rv, 4), power_nrmse=round(rv / cap * 100, 4),
                           power_bias_pct=round(float(np.mean(p - t)) / cap * 100, 4),
                           capacity=round(cap, 4), n_points=int(len(times)))
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
                if plot_station and sc:
                    scatter_jobs.append((st, t, p, sc, th, cap))

        # ---- Per-station feature plots (prediction and truth both in input) ----
        for pcol, tcol, label in active_pairs:
            pser, tser = ser(pcol), ser(tcol)
            if pser.empty or tser.empty:
                print(f"  [warn] station {st}: feature '{label}' data missing/empty for this station, skipped (does not affect other plots)")
                continue
            al = _aligned(tser, pser, args.drop_night, args.night_end_hour, win)
            if al is None:
                print(f"  [warn] station {st}: feature '{label}' has no common time points, skipped")
                continue
            times, tv, pv = al
            rv = rmse(pv, tv)
            feat_rows.append({"station": st, "feature": label, "rmse": round(rv, 6),
                              "n_points": int(len(times))})
            if plot_station:
                disp = _display(tser, pser, args.drop_night, args.night_end_hour, win) \
                       or (times, tv, pv)
                plot_jobs.append((st, label, disp[0], disp[1], disp[2], rv,
                                  f"{tcol} (true)", f"{pcol} (pred)", int(len(times))))

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
    for st, name, times, tv, pv, rv, tlab, plab, n_real in plot_jobs:
        if sel is not None and st not in sel:
            continue
        imgs.append(plot_two_lines(st, name, times, tv, pv, rv, out_dir,
                                   args.tick_hours, tlab, plab, n_real))
    for st, tv, pv, sc, th, cap in scatter_jobs:
        if sel is not None and st not in sel:
            continue
        imgs.append(plot_scatter(st, tv, pv, sc, th, cap, out_dir))

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

    if not power_rows and not feat_rows and fleet_img is None:
        msg = ("nothing could be produced (check --pred-col-template against the predict-table column names, "
               "whether times align, whether columns exist).")
        if win is None:
            raise SystemExit(msg)
        print(f"  {pfx}[warn] {msg}")
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
        prod.append(f"stations/ per-station plots x{len(imgs)}")
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


def compute_windows(args, inp):
    """(report_name, [(label, start, end), ...]). report_name = D.strftime('%Y%m%d') (起报日) in --short,
    else None. 非 short：单趟全序列 (None,None,None)。short：D = --date 或最早 timestamp_win 的日期，
    切 [D+1 00:00, +24h) 与 [D+4 00:00, +24h)。"""
    if not args.short:
        if args.date:
            print("  [warn] --date is ignored without --short")
        return None, [(None, None, None)]
    if args.date:
        try:
            D = pd.Timestamp(args.date).normalize()
        except (ValueError, TypeError):
            raise SystemExit(f"--date must be a valid date (YYYY-MM-DD), got '{args.date}'")
    else:
        D = pd.Timestamp(inp[args.win_col].min()).normalize()
        print(f"  [short] --date not given; using D = {D:%Y-%m-%d} (from earliest {args.win_col})")
    day = pd.Timedelta(days=1)
    d1, d4 = D + day, D + 4 * day
    return D.strftime("%Y%m%d"), [("D+1", d1, d1 + day), ("D+4", d4, d4 + day)]


# ================================================================ Main flow: compute both layers in one pass
def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--input", required=True)
    ap.add_argument("--predict", required=True)
    ap.add_argument("--out-dir", default="station_analysis_out")
    ap.add_argument("--step-min", type=int, default=15)
    ap.add_argument("--drop-night", action="store_true", help="remove each day's 00:00-night_end_hour points")
    ap.add_argument("--night-end-hour", type=float, default=5.0)
    ap.add_argument("--tick-hours", type=int, default=1, help="one x tick every few hours in per-station plots")
    ap.add_argument("--feature-pairs", default=None,
                    help="pred:true[:label] comma-separated; default GHI_SOLARGIS_predict:GHI_real_future:GHI")
    ap.add_argument("--top-n", type=int, default=30, help="max stations shown in ranking (0=all)")
    ap.add_argument("--mad-k", type=float, default=3.0, help="outlier threshold: median + k x MAD")
    ap.add_argument("--capacity", default=None, help='per-station capacity "st1:500,st2:5", default uses peak as proxy')
    ap.add_argument("--ghi-pred", default="GHI_SOLARGIS_predict", help="predicted column for overview scatter/GHI ranking")
    ap.add_argument("--ghi-true", default="GHI_real_future", help="truth column for overview scatter/GHI ranking")
    ap.add_argument("--station-col", default="station")
    ap.add_argument("--win-col", default="timestamp_win")
    ap.add_argument("--power-col", default="observe_power_future")
    ap.add_argument("--dtime-col", default="dtime")
    ap.add_argument("--pred-col-template", default="predict_power_{station}",
                    help='predict-table column name per station; "{station}" is replaced by the station name. '
                         "Falls back to the bare station name when the templated column is absent")
    ap.add_argument("--no-plots", action="store_true", help="no plots at all, still writes CSV")
    ap.add_argument("--no-station-plots", action="store_true", help="no per-station curves, still writes station-level CSV")
    ap.add_argument("--no-fleet", action="store_true", help="no overview and no fleet_ranking.csv")
    ap.add_argument("--worst-only", type=int, default=0,
                    help="draw images only for the worst N stations by power nRMSE (0=all; ranking uses the full "
                         "fleet, CSVs unchanged; counterfactual not affected -- use --cf-stations for that)")
    ap.add_argument("--counterfactual", action="store_true",
                    help="counterfactual: swap GHI prediction to truth and re-predict via API, decompose input's fault vs model's fault")
    ap.add_argument("--api-url", default=None, help="FastAPI prediction service URL (POST JSON)")
    ap.add_argument("--cf-dry-run", action="store_true",
                    help="zero HTTP: print call plan + first station's payload skeleton only, confirm contract before real run")
    ap.add_argument("--cf-stations", default=None, help='only run these stations "st1,st2" (default all)')
    ap.add_argument("--cf-force", action="store_true", help="ignore completed records, recompute all")
    ap.add_argument("--cf-swap", default="GHI_SOLARGIS_predict:GHI_real_future",
                    help="pred:true comma-separated, multiple pairs allowed (multiple = joint replacement)")
    ap.add_argument("--cf-exclude-cols", default="observe_power_future,GHI_real_future",
                    help="columns not sent to API (truth labels; station column auto-removed)")
    ap.add_argument("--cf-timeout", type=float, default=120.0)
    ap.add_argument("--cf-retries", type=int, default=1)
    ap.add_argument("--cf-check-tol", type=float, default=1.0,
                    help="baseline reproduction gate: warn if API baseline vs predict table nRMSE%% exceeds this")
    ap.add_argument("--cf-curves", action="store_true", help="per-station three-line plot (truth/baseline/counterfactual)")
    ap.add_argument("--short", action="store_true",
                    help="短期模式：只看 D+1 与 D+4 两个 24h 切片，各产一份全套产物到 out_dir/D+1、out_dir/D+4")
    ap.add_argument("--date", default=None,
                    help="起报日 YYYY-MM-DD；D+1/D+4 从此日算。--short 专用，缺省则取最早 timestamp_win 的日期")
    args = ap.parse_args()
    step = pd.Timedelta(minutes=args.step_min)
    feature_pairs = parse_feature_pairs(args.feature_pairs)
    cap_map = parse_capacity(args.capacity)

    inp = pd.read_parquet(args.input)
    pred = pd.read_parquet(args.predict)
    for c in (args.station_col, args.win_col, args.power_col):
        if c not in inp.columns:
            raise SystemExit(f"input table missing column '{c}'; actual columns: {list(inp.columns)[:30]}")
    if args.dtime_col not in pred.columns:
        raise SystemExit(f"predict table missing column '{args.dtime_col}'; actual columns: {list(pred.columns)[:30]}")
    inp[args.win_col] = pd.to_datetime(inp[args.win_col])
    pred[args.dtime_col] = pd.to_datetime(pred[args.dtime_col])
    pred = pred.groupby(args.dtime_col).mean(numeric_only=True).sort_index()

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
    report_name, windows = compute_windows(args, inp)
    report_root = args.out_dir if report_name is None else os.path.join(args.out_dir, report_name)
    os.makedirs(report_root, exist_ok=True)
    for label, start, end in windows:
        sub_out = report_root if label is None else os.path.join(report_root, label)
        os.makedirs(sub_out, exist_ok=True)
        run_analysis(inp, pred, args, step, active_pairs, have_ghi, cap_map,
                     sub_out, (start, end) if label else None, label)

    if args.counterfactual:
        # sub_out dirs already created by the run_analysis loop above (same windows)
        for label, start, end in windows:
            sub_out = report_root if label is None else os.path.join(report_root, label)
            run_counterfactual(inp, pred, args, cap_map, step,
                               out_dir=sub_out, win=(start, end) if label else None)


if __name__ == "__main__":
    main()
