"""matplotlib 共用件：字体、时间轴、以及短期两列面板的画法。

matplotlib 一律在函数体内 import —— 不画图的跑法（--no-plots、只跑指标的单测）不该为它付启动代价。
fmt_time_axis 合并了原先短期/超短期两份几乎相同的实现，两边的字号差异走参数。
"""
from __future__ import annotations

import numpy as np
import pandas as pd


def _cn_font():
    import matplotlib
    try:
        matplotlib.rcParams["font.sans-serif"] = ["DejaVu Sans", "Arial", "Helvetica"]
        matplotlib.rcParams["axes.unicode_minus"] = False
    except Exception:
        pass


def fmt_time_axis(ax, tick_hours, times=None, ylabel=None, tick_fontsize=8, xlabel_fontsize=None):
    """刻度间隔 = max(--tick-hours, 跨度/36)：历史面板跨 7 天时自动稀疏，不至于挤成一团。
    times 省略则只按 tick_hours 定间隔；ylabel 省略则由调用方自己设。"""
    import matplotlib.dates as mdates
    step_h = max(1, int(tick_hours))
    if times is not None and len(times) > 1:
        span_h = (pd.Timestamp(times[-1]) - pd.Timestamp(times[0])).total_seconds() / 3600.0
        step_h = max(step_h, int(np.ceil(max(1.0, span_h) / 36.0)))
    ax.xaxis.set_major_locator(mdates.HourLocator(interval=step_h))
    ax.xaxis.set_major_formatter(mdates.DateFormatter("%m-%d %H:%M"))
    for lb in ax.get_xticklabels():
        lb.set_rotation(90)
        lb.set_fontsize(tick_fontsize)
    ax.set_xlabel("time", **({"fontsize": xlabel_fontsize} if xlabel_fontsize else {}))
    if ylabel is not None:
        ax.set_ylabel(ylabel)
    ax.grid(alpha=0.25)


def _panel_no_data(ax, st, title):
    ax.text(0.5, 0.5, "no data", ha="center", va="center", fontsize=22, color="#999999",
            transform=ax.transAxes)
    ax.set_title(title, fontsize=13, fontweight="bold")
    ax.set_xticks([]); ax.set_yticks([])
    print(f"  [warn] station {st}: {title}: no data")


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
        n_ok = int(np.isfinite(np.asarray(yv, dtype=float)).sum())   # NaN = 缺测空洞，不计入点数
        notes += f"   {lab} n={n_ok}" + (f" (+{len(yv) - n_ok} missing)" if n_ok < len(yv) else "")
    ax.set_title(f"{name} (history)   {times[0]:%Y-%m-%d %H:%M} -> {times[-1]:%Y-%m-%d %H:%M}   "
                 f"(n={len(times)}){notes}", fontsize=13, fontweight="bold")
    ax.set_ylabel(name, fontsize=11); ax.legend(loc="upper right", fontsize=9)
    fmt_time_axis(ax, tick_hours, times, tick_fontsize=8, xlabel_fontsize=10)


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
    fmt_time_axis(ax, tick_hours, times, tick_fontsize=8, xlabel_fontsize=10)
