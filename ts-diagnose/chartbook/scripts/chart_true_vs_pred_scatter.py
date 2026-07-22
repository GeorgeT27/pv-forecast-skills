"""true-vs-pred-scatter：真值-预测回归诊断——R² 管「齐不齐」（离散度），
slope 管「正不正」（系统性压低/抬高）；分位分箱看偏差沿功率段的形状。"""
from __future__ import annotations

import argparse

import numpy as np
import pandas as pd

import chart_common as cc

RECIPE_ID = "true-vs-pred-scatter"


def compute(df: pd.DataFrame, n_bins: int = 10) -> dict:
    out = {"recipe": RECIPE_ID, "models": {},
           "note": "slope<1 → 大值段被系统性压低；R² 低而 slope≈1 → 离散不齐；"
                   "pred_by_true_bin 看压低集中在高段还是全段。"}
    for m, g in df.groupby("model"):
        gg = g.dropna(subset=["y_true", "y_pred"])
        y, p = gg["y_true"].to_numpy(float), gg["y_pred"].to_numpy(float)
        if np.unique(y).size < 2:
            raise ValueError(f"模型 {m} 的 y_true 无方差，回归无意义"
                             "（检查适配器是否填错列）")
        slope, intercept = np.polyfit(y, p, 1)
        r2 = float(np.corrcoef(y, p)[0, 1] ** 2)
        dfb = pd.DataFrame({"y": y, "p": p, "e": p - y})
        dfb["bin"] = pd.qcut(dfb["y"], n_bins, duplicates="drop")
        gb = dfb.groupby("bin", observed=True)
        binned = gb.agg(y=("y", "mean"), p=("p", "mean"))
        resid = gb["e"].quantile([0.1, 0.5, 0.9]).unstack()
        out["models"][str(m)] = {
            "slope": round(float(slope), 6),
            "intercept": round(float(intercept), 6),
            "r2": round(r2, 6), "n": int(len(gg)),
            "true_max": round(float(y.max()), 4),
            "pred_max": round(float(p.max()), 4),
            "pred_by_true_bin": {f"{r.y:.2f}": round(float(r.p), 4)
                                 for r in binned.itertuples()},
            "resid_quantiles_by_bin": {
                f"{binned.loc[b, 'y']:.2f}": {
                    "p10": round(float(row[0.1]), 4),
                    "p50": round(float(row[0.5]), 4),
                    "p90": round(float(row[0.9]), 4)}
                for b, row in resid.iterrows()},
        }
    return out


def render_from_df(df: pd.DataFrame, stats: dict):
    import matplotlib.pyplot as plt
    cc.setup_font()
    models = list(stats["models"])
    fig, axes = plt.subplots(1, len(models),
                             figsize=(5.5 * len(models), 5), squeeze=False)
    for ax, m in zip(axes.ravel(), models):
        g = df[df["model"] == m].dropna(subset=["y_true", "y_pred"])
        s = stats["models"][m]
        ax.hexbin(g["y_true"], g["y_pred"], gridsize=60, cmap="viridis",
                  mincnt=1)
        lim = [0, max(float(g["y_true"].max()), float(g["y_pred"].max())) * 1.02]
        ax.plot(lim, lim, "r--", lw=1, label="y = x")
        ax.plot(lim, [s["slope"] * v + s["intercept"] for v in lim],
                color="orange", lw=1.5, label=f"slope={s['slope']:.3f}")
        ax.text(0.03, 0.95, f"R²={s['r2']:.4f}", transform=ax.transAxes,
                va="top", bbox=dict(fc="white", alpha=0.85))
        ax.set_xlabel("y_true"), ax.set_ylabel("y_pred")
        ax.set_title(f"true-vs-pred — {m}"), ax.legend(loc="lower right")
    fig.tight_layout()
    return fig


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--pred", required=True)
    ap.add_argument("--out-dir", required=True)
    ap.add_argument("--n-bins", type=int, default=10)
    a = ap.parse_args(argv)
    df = cc.load_predictions(a.pred)
    stats = compute(df, n_bins=a.n_bins)
    cc.save_outputs(render_from_df(df, stats), a.out_dir, RECIPE_ID, stats)


if __name__ == "__main__":
    main()
