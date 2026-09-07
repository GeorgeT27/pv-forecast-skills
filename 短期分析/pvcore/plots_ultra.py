"""超短期每站 2x2 组合图（布局同短期，右下换成 17 条线）。"""
from __future__ import annotations

import os

import numpy as np

from .plotting import _cn_font, _panel_no_data, fmt_time_axis
from .timeseries import sanitize
from .ultra_loaders import HIST_COLS, N_LEADS


def _station_dir(out_dir):
    d = os.path.join(out_dir, "stations")
    os.makedirs(d, exist_ok=True)
    return d


def plot_station_combo(st, tr, leads, rmse_v, n, ghi_rmse, keep, hist, out_dir, tick_hours):
    """每站一张 2×2 组合图（布局同 station_analysis_short.py）：
    左上 历史 GHI_SOLARGIS、左下 历史 observe_power（当日最早起报的整条 list 反向展开 = 往前 7 天，
    全点不去夜间）；右上 lead-1 GHI 预测 vs 真值 2 线（标 RMSE）；右下 真值黑粗 + p1..p16 由浅到深
    17 线（标合并 RMSE）。左右两列时间跨度不同，各用各的 x 轴。某面板全空 -> 'no data' + 告警。"""
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from matplotlib import cm
    _cn_font()
    fig, axes = plt.subplots(2, 2, figsize=(32, 13))
    (ax_hg, ax_g), (ax_hp, ax_p) = axes

    for ax, key, src, color in ((ax_hg, "ghi_hist", HIST_COLS["ghi_hist"], "#8c564b"),
                                (ax_hp, "power_hist", HIST_COLS["power_hist"], "#2c7fb8")):
        h = hist.get(key)
        if h is None or h.empty:
            _panel_no_data(ax, st, f"Station {st} - history {src}")
            continue
        ax.plot(h.index, h, color=color, lw=1.3, label=f"{src} (observed history)")
        ax.set_title(f"Station {st} - history {src}   {h.index[0]:%Y-%m-%d %H:%M} -> "
                     f"{h.index[-1]:%Y-%m-%d %H:%M}   (n={len(h)})", fontsize=13, fontweight="bold")
        ax.legend(loc="upper right")
        fmt_time_axis(ax, tick_hours, h.index, src, tick_fontsize=7)

    gt, gp = tr["ghi_true"][keep], tr["ghi_pred"][keep]
    if np.isfinite(gt.to_numpy(float)).any() or np.isfinite(gp.to_numpy(float)).any():
        ax_g.plot(gt.index, gt, label="GHI_real_future (true)", color="#1f77b4", lw=1.3)
        ax_g.plot(gp.index, gp, label="GHI_SOLARGIS_predict (lead-1 pred)",
                  color="#d62728", lw=1.1, alpha=0.85)
        ax_g.fill_between(gt.index, gt.to_numpy(float), gp.to_numpy(float),
                          color="#d62728", alpha=0.12)
        rtxt = f"RMSE={ghi_rmse:.3f}" if ghi_rmse is not None else "no scored points"
        ax_g.set_title(f"Station {st} - GHI (lead-1)   {rtxt}", fontsize=13, fontweight="bold")
        ax_g.legend(loc="upper right")
        fmt_time_axis(ax_g, tick_hours, None, "GHI", tick_fontsize=7)
    else:
        _panel_no_data(ax_g, st, f"Station {st} - GHI (lead-1)")

    ptr, L = tr["power_true"][keep], leads[keep]
    if np.isfinite(ptr.to_numpy(float)).any() or np.isfinite(L.to_numpy(float)).any():
        colors = cm.viridis(np.linspace(0.88, 0.10, N_LEADS))
        for j, lab in enumerate(L.columns):
            ax_p.plot(L.index, L[lab], color=colors[j], lw=0.9, alpha=0.8,
                      label=f"{lab} ({(N_LEADS - j) * 15}min ahead)")
        ax_p.plot(ptr.index, ptr, color="#000000", lw=2.2, label="observed power")
        rtxt = f"pooled RMSE={rmse_v:.3f}" if rmse_v is not None else "no scored points"
        ax_p.set_title(f"Station {st} - ultra-short 16-lead power   {rtxt}   (n={n} lead-target pairs)",
                       fontsize=13, fontweight="bold")
        ax_p.legend(loc="upper right", fontsize=6, ncol=2)
        fmt_time_axis(ax_p, tick_hours, None, "power", tick_fontsize=7)
    else:
        _panel_no_data(ax_p, st, f"Station {st} - ultra-short 16-lead power")

    fig.tight_layout()
    path = os.path.join(_station_dir(out_dir), f"station_{sanitize(st)}.png")
    fig.savefig(path, dpi=110)
    plt.close(fig)
    return path
