"""error-acf:窗口级均值误差序列的自相关——误差是白噪声还是有可预测结构。"""
from __future__ import annotations

import argparse

import numpy as np
import pandas as pd
from scipy.stats import chi2

import chart_common as cc

RECIPE_ID = "error-acf"


def _acf(x: np.ndarray, max_lag: int) -> np.ndarray:
    x = x - x.mean()
    denom = float(np.dot(x, x))
    if denom < 1e-12:
        return np.zeros(max_lag)
    return np.array([float(np.dot(x[:-k], x[k:]) / denom)
                     for k in range(1, max_lag + 1)])


def compute(df: pd.DataFrame, max_lag: int = 12) -> dict:
    out = {"recipe": RECIPE_ID, "max_lag": max_lag, "models": {},
           "note": "序列=每窗均值误差(单元池化,按 window_ts 排序);"
                   "窗口重叠时低阶 lag 自相关是结构必然,判读见 recipe。"}
    for m, g in df.groupby("model"):
        ser = (g.groupby("window_ts")["err"].mean().sort_index())
        x = ser.values
        n = len(x)
        lags = list(range(1, max_lag + 1))
        rho = _acf(x, max_lag)
        lb = float(n * (n + 2) * np.sum(rho ** 2 / (n - np.array(lags))))
        p = float(chi2.sf(lb, df=max_lag))
        out["models"][str(m)] = {
            "acf": cc.curve_stats(rho, index=lags),
            "argmax_lag": int(lags[int(np.argmax(rho))]),
            "acf1": round(float(rho[0]), 4),
            "ljung_box": {"stat": round(lb, 4), "p": round(p, 6),
                          "lags": max_lag},
            "n": n, "steps_per_window": int(g["horizon_step"].max()) + 1}
    return out


def render(stats: dict):
    import matplotlib.pyplot as plt
    cc.setup_font()
    n = len(stats["models"])
    fig, axes = plt.subplots(1, n, figsize=(5 * n, 3.5), squeeze=False)
    for ax, (m, s) in zip(axes[0], stats["models"].items()):
        curve = s["acf"]["curve"]
        ks = sorted(int(k) for k in curve)
        ax.bar(ks, [curve[str(k)] for k in ks], width=0.6)
        ax.axhline(0, color="k", lw=0.5)
        nn = s["n"]
        ci = 1.96 / np.sqrt(nn) if nn > 0 else 0
        ax.axhline(ci, color="r", ls="--", lw=0.6)
        ax.axhline(-ci, color="r", ls="--", lw=0.6)
        ax.set_title(f"{m} 误差 ACF (LB p={s['ljung_box']['p']:.3g})")
        ax.set_xlabel("lag(窗)")
    return fig


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--pred", required=True)
    ap.add_argument("--out-dir", required=True)
    ap.add_argument("--max-lag", type=int, default=12)
    a = ap.parse_args(argv)
    stats = compute(cc.load_predictions(a.pred), max_lag=a.max_lag)
    cc.save_outputs(render(stats), a.out_dir, RECIPE_ID, stats)


if __name__ == "__main__":
    main()
