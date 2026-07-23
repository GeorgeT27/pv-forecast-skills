"""pp-calibration:y_pred 与 y_true 的分位数-分位数对齐——系统性压缩/抬升的直接证据。"""
from __future__ import annotations

import argparse

import numpy as np
import pandas as pd

import chart_common as cc

RECIPE_ID = "pp-calibration"
QS = [0.01, 0.05, 0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8, 0.9, 0.95, 0.99]


def compute(df: pd.DataFrame) -> dict:
    out = {"recipe": RECIPE_ID, "models": {},
           "note": "ratio=y_pred_q/y_true_q;|y_true_q|<1e-9 时 ratio=null;"
                   "slope 为分位数对过原点 OLS 斜率。"}
    for m, g in df.groupby("model"):
        qt = np.quantile(g["y_true"], QS)
        qp = np.quantile(g["y_pred"], QS)
        pairs = []
        for q, t, p in zip(QS, qt, qp):
            ratio = round(float(p / t), 4) if abs(t) > 1e-9 else None
            pairs.append({"q": q, "y_true_q": round(float(t), 4),
                          "y_pred_q": round(float(p), 4), "ratio": ratio})
        denom = float(np.dot(qt, qt))
        slope = round(float(np.dot(qt, qp) / denom), 4) if denom > 1e-12 else None
        def _tail(i):
            return round(float(qp[i] / qt[i]), 4) if abs(qt[i]) > 1e-9 else None
        out["models"][str(m)] = {
            "quantiles": pairs, "slope": slope,
            "high_tail_ratio": _tail(QS.index(0.95)),
            "low_tail_ratio": _tail(QS.index(0.05)),
            "n": int(len(g))}
    return out


def render(stats: dict):
    import matplotlib.pyplot as plt
    cc.setup_font()
    fig, ax = plt.subplots(figsize=(6, 6))
    lo, hi = np.inf, -np.inf
    for m, s in stats["models"].items():
        xs = [q["y_true_q"] for q in s["quantiles"]]
        ys = [q["y_pred_q"] for q in s["quantiles"]]
        ax.plot(xs, ys, marker="o", ms=3, label=f"{m} (slope={s['slope']})")
        lo, hi = min(lo, min(xs + ys)), max(hi, max(xs + ys))
    ax.plot([lo, hi], [lo, hi], "k--", lw=0.8, label="y=x")
    ax.set_xlabel("真值分位数"), ax.set_ylabel("预测分位数")
    ax.set_title("pp-calibration 分位数校准")
    ax.legend()
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
