"""horizon-error-quantiles:逐 horizon 的经验误差分位扇形带——该配多宽的置信带、
分布是否偏斜。"""
from __future__ import annotations

import argparse

import numpy as np
import pandas as pd

import chart_common as cc

RECIPE_ID = "horizon-error-quantiles"
BAND_QS = {"p05": 0.05, "p25": 0.25, "p50": 0.5, "p75": 0.75, "p95": 0.95}


def compute(df: pd.DataFrame) -> dict:
    out = {"recipe": RECIPE_ID, "models": {},
           "note": "分位在每 (model,horizon_step) 全样本上算(pool 单元与窗口);"
                   "width90=p95−p05;growth_ratio=末步 width90/首步 width90。"}
    for m, g in df.groupby("model"):
        grp = g.groupby("horizon_step")["err"]
        steps = sorted(g["horizon_step"].unique().tolist())
        bands = {k: grp.quantile(q) for k, q in BAND_QS.items()}
        s = {k: cc.curve_stats(v.values, index=steps) for k, v in bands.items()}
        w90 = bands["p95"].values - bands["p05"].values
        s["width90"] = cc.curve_stats(w90, index=steps)
        first, last = float(w90[0]), float(w90[-1])
        s["growth_ratio"] = round(last / first, 4) if abs(first) > 1e-12 else None
        s["median_skew"] = round(float(np.mean(bands["p50"].values)), 4)
        s["n_per_step"] = int(grp.count().min())
        out["models"][str(m)] = s
    return out


def render(stats: dict):
    import matplotlib.pyplot as plt
    cc.setup_font()
    n = len(stats["models"])
    fig, axes = plt.subplots(1, n, figsize=(6 * n, 4), squeeze=False)
    for ax, (m, s) in zip(axes[0], stats["models"].items()):
        xs = [int(k) for k in s["p50"]["curve"]]
        get = lambda key: [s[key]["curve"][str(x)] for x in xs]
        ax.fill_between(xs, get("p05"), get("p95"), alpha=0.2, label="p05–p95")
        ax.fill_between(xs, get("p25"), get("p75"), alpha=0.35, label="p25–p75")
        ax.plot(xs, get("p50"), lw=1.2, label="p50")
        ax.axhline(0, color="k", lw=0.5)
        ax.set_title(f"{m} error-quantile fan"), ax.set_xlabel("horizon step")
        ax.legend(fontsize=8)
    return fig


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--pred", required=True)
    ap.add_argument("--out-dir", required=True)
    a = ap.parse_args(argv)
    stats = compute(cc.load_predictions(a.pred))
    cc.save_outputs(render(stats), a.out_dir, RECIPE_ID, stats)


if __name__ == "__main__":
    main()
