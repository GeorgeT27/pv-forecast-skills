"""theil-decomposition:MSE 的 Theil 三分(bias/variance/covariance 占比)——
误差是平移、幅度还是形状问题。"""
from __future__ import annotations

import argparse

import numpy as np
import pandas as pd

import chart_common as cc

RECIPE_ID = "theil-decomposition"


def _theil(y_true: np.ndarray, y_pred: np.ndarray) -> dict:
    mse = float(np.mean((y_pred - y_true) ** 2))
    if mse < 1e-12:
        return {"u_bias": None, "u_var": None, "u_cov": None,
                "mse": round(mse, 6)}
    st, sp = float(np.std(y_true)), float(np.std(y_pred))
    bias2 = (float(np.mean(y_pred)) - float(np.mean(y_true))) ** 2
    var2 = (sp - st) ** 2
    if st > 1e-12 and sp > 1e-12:
        r = float(np.corrcoef(y_true, y_pred)[0, 1])
        cov = 2 * (1 - r) * sp * st
    else:
        cov = mse - bias2 - var2
    return {"u_bias": round(bias2 / mse, 4), "u_var": round(var2 / mse, 4),
            "u_cov": round(cov / mse, 4), "mse": round(mse, 6)}


def compute(df: pd.DataFrame) -> dict:
    out = {"recipe": RECIPE_ID, "models": {},
           "note": "u_bias+u_var+u_cov=1(浮点容差);segment 按 horizon 三等分;"
                   "mse≈0 时四值 null。"}
    for m, g in df.groupby("model"):
        seg = {}
        smax = int(g["horizon_step"].max()) + 1
        bounds = [(0, smax // 3), (smax // 3, 2 * smax // 3), (2 * smax // 3, smax)]
        for name, (lo, hi) in zip(("early", "mid", "late"), bounds):
            gs = g[(g["horizon_step"] >= lo) & (g["horizon_step"] < hi)]
            if len(gs):
                seg[name] = _theil(gs["y_true"].values, gs["y_pred"].values)
        out["models"][str(m)] = {
            "overall": _theil(g["y_true"].values, g["y_pred"].values),
            "by_segment": seg, "n": int(len(g))}
    return out


def render(stats: dict):
    import matplotlib.pyplot as plt
    cc.setup_font()
    models = list(stats["models"])
    fig, ax = plt.subplots(figsize=(1.5 + 1.2 * len(models), 4))
    bottoms = np.zeros(len(models))
    for key, label in (("u_bias", "偏移"), ("u_var", "幅度"), ("u_cov", "形状")):
        vals = np.array([stats["models"][m]["overall"][key] or 0.0
                         for m in models])
        ax.bar(models, vals, bottom=bottoms, label=label)
        bottoms += vals
    ax.set_ylabel("MSE 占比"), ax.set_ylim(0, 1.05)
    ax.set_title("theil-decomposition 误差性质三分")
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
