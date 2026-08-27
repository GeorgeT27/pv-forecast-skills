"""短期分析的三张图：每站 2x2 组合图、舰队总览四宫格、反事实分解左右图。"""
from __future__ import annotations

import os

import numpy as np

from .metrics import flag_outliers
from .plotting import _cn_font, _draw_hist_panel, _draw_win_panel
from .timeseries import sanitize


# ================================================================ 每站 2x2
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


# ================================================================ 舰队总览
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


# ================================================================ K_t 乘性扫描
def plot_kt_scan(df, out_dir, factors, kt_max=1.2, ghi_col="GHI"):
    """左：每站 nRMSE 随缩放系数 k 的走势（k=1 处即基线，竖线标出）＋ 舰队中位线加粗；
    右：真正被缩放改善的站，按改善幅度排序，条上标最优 k。曲线在 k=1 触底 = 该站 GHI 预报
    没有系统性乘性偏差；底部落在 k<1 = 预报整体偏高，k>1 = 偏低。"""
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from matplotlib.patches import Patch
    _cn_font()
    ks = sorted(set(list(factors) + [1.0]))
    cols = {k: ("power_nrmse_localbase" if k == 1.0 else f"power_nrmse_kt{k:g}") for k in ks}
    missing = [c for c in cols.values() if c not in df.columns]
    if missing or df.empty:
        return None
    curves, names = [], []
    for _, r in df.iterrows():
        y = np.array([r[cols[k]] for k in ks], dtype=float)
        if np.isfinite(y).all():
            curves.append(y); names.append(str(r["station"]))
    if not curves:
        return None
    M = np.vstack(curves)
    fig, (axL, axR) = plt.subplots(1, 2, figsize=(16, max(6.5, 1.2 + len(df) * 0.32)),
                                   gridspec_kw={"width_ratios": [1.25, 1]})
    for y in M:
        axL.plot(ks, y, color="#4c78a8", lw=0.8, alpha=0.35, marker="o", ms=2.5)
    med = np.median(M, axis=0)
    axL.plot(ks, med, color="#d62728", lw=2.4, marker="o", ms=5,
             label=f"fleet median ({len(M)} stations)")
    kbest = ks[int(np.argmin(med))]
    axL.axvline(1.0, color="#333", ls="--", lw=1, label="k=1 (unscaled forecast)")
    axL.scatter([kbest], [med.min()], s=110, facecolors="none", edgecolors="#d62728", lw=2,
                zorder=5, label=f"median-best k={kbest:g}")
    axL.set_xlabel(f"multiplicative factor k applied to {ghi_col} in K_t space "
                   f"(capped at K_t<={kt_max:g})")
    axL.set_ylabel("power nRMSE (%)")
    axL.set_title("Does rescaling the GHI forecast help?  (curve bottoming at k=1 = no scale bias)",
                  fontsize=12, fontweight="bold")
    axL.set_xticks(ks); axL.set_xticklabels([f"{k:g}" for k in ks])
    axL.legend(loc="best", fontsize=8); axL.grid(alpha=0.25)

    if "kt_best_gain" in df.columns:
        d = df[np.isfinite(df["kt_best_gain"]) & (df["kt_best_gain"] > 0)] \
            .sort_values("kt_best_gain", ascending=False).head(30)
    else:
        d = df.iloc[:0]
    if d.empty:
        axR.text(0.5, 0.5, "no station improves under any k\n(no systematic multiplicative GHI bias)",
                 ha="center", va="center", fontsize=11, color="#666")
    else:
        y = np.arange(len(d))[::-1]
        axR.barh(y, d.kt_best_gain,
                 color=["#f28e2b" if f < 1 else "#4c78a8" for f in d.kt_best_factor])
        for yi, (_, r) in zip(y, d.iterrows()):
            axR.text(r.kt_best_gain, yi, f"  k={r.kt_best_factor:g}", va="center", fontsize=7)
        axR.set_yticks(y); axR.set_yticklabels(d.station.astype(str), fontsize=8)
        axR.set_xlim(0, float(d.kt_best_gain.max()) * 1.35)
        axR.legend(handles=[Patch(color="#f28e2b", label="best k<1 -> forecast reads too HIGH"),
                            Patch(color="#4c78a8", label="best k>1 -> forecast reads too LOW")],
                   loc="lower right", fontsize=8)
    axR.set_xlabel("nRMSE improvement at the best k (percentage points)")
    axR.set_title("Who is helped, and in which direction" + ("" if len(d) < 30 else "  (top 30)"),
                  fontsize=12, fontweight="bold")
    axR.grid(axis="x", alpha=0.25)
    fig.suptitle(f"K_t multiplicative counterfactual -- {ghi_col} forecast scaled by k and re-predicted",
                 fontsize=14, fontweight="bold")
    fig.text(0.01, 0.005,
             "Note: k rescales the forecast in clear-sky-index space, so no point is pushed above "
             f"{kt_max:g}x the clear-sky irradiance for its own time and place. A flat curve means either the "
             "model is insensitive to GHI scale, or the station had no usable coordinates (check the log).",
             fontsize=8, color="#666")
    fig.tight_layout(rect=(0, 0.03, 1, 0.96))
    path = os.path.join(out_dir, "counterfactual_kt_scan.png")
    fig.savefig(path, dpi=120); plt.close(fig)
    return path


# ================================================================ 反事实分解
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
