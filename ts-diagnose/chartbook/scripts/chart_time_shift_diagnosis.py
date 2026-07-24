"""time-shift-diagnosis:逐窗最优互相关平移量分布——预测是否整体提前/滞后。
shift>0 = 预测滞后(y_pred[t] ≈ y_true[t−shift])。"""
from __future__ import annotations

import argparse

import numpy as np
import pandas as pd

import chart_common as cc

RECIPE_ID = "time-shift-diagnosis"
MIN_OVERLAP = 8


def _best_shift(y_pred: np.ndarray, y_true: np.ndarray, max_shift: int):
    n = len(y_true)
    best_k, best_mse = None, np.inf
    for k in range(-max_shift, max_shift + 1):
        t = np.arange(n)
        m = (t - k >= 0) & (t - k < n)
        if m.sum() < MIN_OVERLAP:
            continue
        mse = float(np.mean((y_pred[m] - y_true[t[m] - k]) ** 2))
        if mse < best_mse - 1e-12:
            best_k, best_mse = k, mse
    return best_k


def compute(df: pd.DataFrame, max_shift: int = 8) -> dict:
    out = {"recipe": RECIPE_ID, "max_shift": max_shift, "models": {},
           "note": "shift>0=预测滞后;k*=argmin_k MSE(y_pred[t],y_true[t−k]);"
                   f"重叠<{MIN_OVERLAP} 点的窗口跳过。"}
    for m, g in df.groupby("model"):
        shifts, skipped = [], 0
        for (_u, _w), gw in g.groupby(["unit_id", "window_ts"]):
            gw = gw.sort_values("horizon_step")
            k = _best_shift(gw["y_pred"].values, gw["y_true"].values, max_shift)
            if k is None:
                skipped += 1
            else:
                shifts.append(k)
        if not shifts:
            out["models"][str(m)] = {"shift_hist": {}, "mode_shift": None,
                                     "share_nonzero": None, "mean_abs_shift": None,
                                     "n_windows": 0, "skipped": skipped}
            continue
        vals, counts = np.unique(shifts, return_counts=True)
        hist = {str(int(v)): int(c) for v, c in zip(vals, counts)}
        out["models"][str(m)] = {
            "shift_hist": hist,
            "mode_shift": int(vals[int(np.argmax(counts))]),
            "share_nonzero": round(float(np.mean(np.array(shifts) != 0)), 4),
            "mean_abs_shift": round(float(np.mean(np.abs(shifts))), 4),
            "n_windows": len(shifts), "skipped": skipped}
    return out


def render(stats: dict):
    import matplotlib.pyplot as plt
    cc.setup_font()
    n = len(stats["models"])
    fig, axes = plt.subplots(1, n, figsize=(5 * n, 3.5), squeeze=False)
    for ax, (m, s) in zip(axes[0], stats["models"].items()):
        ks = sorted(int(k) for k in s["shift_hist"])
        ax.bar(ks, [s["shift_hist"][str(k)] for k in ks])
        ax.axvline(0, color="k", lw=0.5)
        ax.set_title(f"{m} best-shift distribution (mode={s['mode_shift']})")
        ax.set_xlabel("shift steps (>0=lag)"), ax.set_ylabel("window count")
    return fig


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--pred", required=True)
    ap.add_argument("--out-dir", required=True)
    ap.add_argument("--max-shift", type=int, default=8)
    a = ap.parse_args(argv)
    stats = compute(cc.load_predictions(a.pred), max_shift=a.max_shift)
    cc.save_outputs(render(stats), a.out_dir, RECIPE_ID, stats)


if __name__ == "__main__":
    main()
