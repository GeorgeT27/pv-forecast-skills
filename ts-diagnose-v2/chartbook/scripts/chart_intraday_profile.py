"""intraday-profile：按目标物理时刻（window_ts + step×freq）聚合的日内
bias/RMSE 剖面——峰值时段、低估/高估不对称。"""
from __future__ import annotations

import argparse

import numpy as np
import pandas as pd

import chart_common as cc

RECIPE_ID = "intraday-profile"


def compute(df: pd.DataFrame, freq: str = "15min") -> dict:
    d = df.copy()
    target = d["window_ts"] + d["horizon_step"] * pd.Timedelta(freq)
    d["tod_h"] = (target.dt.hour * 60 + target.dt.minute) / 60.0
    out = {"recipe": RECIPE_ID, "freq": freq, "models": {},
           "note": "tod 为目标物理时刻（小时）；bias>0 高估、<0 低估；"
                   "mean_under/mean_over 为负/正误差各自的均值（无该侧误差记 0）。"}
    for m, g in d.groupby("model"):
        grp = g.groupby("tod_h")["err"]
        rmse = grp.apply(lambda e: float(np.sqrt(np.mean(np.square(e)))))
        bias = grp.mean()
        hkey = [round(float(h), 2) for h in rmse.index]
        neg, pos = g.loc[g["err"] < 0, "err"], g.loc[g["err"] > 0, "err"]
        uw = {}
        for u, gu in g.groupby("unit_id"):
            r_u = gu.groupby("tod_h")["err"].apply(
                lambda e: float(np.sqrt(np.mean(np.square(e)))))
            uw[str(u)] = round(float(r_u.idxmax()), 2)
        out["models"][str(m)] = {
            "rmse_by_tod": cc.curve_stats(rmse.values, index=hkey),
            "bias_by_tod": cc.curve_stats(bias.values, index=hkey),
            "worst_hour": round(float(rmse.idxmax()), 2),
            "bias_asymmetry": {
                "mean_under": round(float(neg.mean()), 4) if len(neg) else 0.0,
                "mean_over": round(float(pos.mean()), 4) if len(pos) else 0.0},
            "unit_worst_hour": uw,
        }
    return out


def render(stats: dict):
    import matplotlib.pyplot as plt
    cc.setup_font()
    fig, axes = plt.subplots(2, 1, figsize=(10, 6), sharex=True)
    for m, s in stats["models"].items():
        for ax, key in zip(axes, ("rmse_by_tod", "bias_by_tod")):
            curve = s[key]["curve"]
            xs = [float(k) for k in curve]
            ys = [curve[k] for k in curve]
            ax.plot(xs, ys, label=m)
    axes[0].set_ylabel("RMSE"), axes[1].set_ylabel("bias")
    axes[1].axhline(0, color="k", lw=0.5)
    axes[1].set_xlabel("target hour (h)")
    axes[0].set_title("intraday-profile: hourly error profile")
    axes[0].legend(ncol=max(1, len(stats["models"])))
    return fig


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--pred", required=True)
    ap.add_argument("--out-dir", required=True)
    ap.add_argument("--freq", default="15min")
    a = ap.parse_args(argv)
    stats = compute(cc.load_predictions(a.pred), freq=a.freq)
    cc.save_outputs(render(stats), a.out_dir, RECIPE_ID, stats)


if __name__ == "__main__":
    main()
