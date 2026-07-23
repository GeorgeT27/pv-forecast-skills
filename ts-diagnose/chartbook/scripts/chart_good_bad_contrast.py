"""good-bad-contrast:best-K vs worst-K 窗口的特征/上下文分布对照——坏样本
的输入有什么系统性不同。"""
from __future__ import annotations

import argparse

import numpy as np
import pandas as pd
from scipy.stats import ks_2samp

import chart_common as cc

RECIPE_ID = "good-bad-contrast"
MIN_K = 5


def _contrast(worst: np.ndarray, best: np.ndarray) -> dict:
    mw, mb = float(np.mean(worst)), float(np.mean(best))
    pooled = np.sqrt((np.var(worst, ddof=1) + np.var(best, ddof=1)) / 2)
    d = (mw - mb) / pooled if pooled > 1e-12 else 0.0
    ks, p = ks_2samp(worst, best)
    return {"d": round(float(d), 4), "ks": round(float(ks), 4),
            "p": round(float(p), 6), "mean_best": round(mb, 4),
            "mean_worst": round(mw, 4),
            "direction": int(np.sign(d)) if abs(d) > 1e-12 else 0}


def compute(df: pd.DataFrame, feats: pd.DataFrame, k: int = None) -> dict:
    rr = cc.row_rmse(df)
    out = {"recipe": RECIPE_ID, "models": {},
           "note": "level=窗内 f_pred 均值;quality=窗内|f_pred−f_true|均值"
                   "(f_true 全缺时 basis 降级 level);d=(worst−best)/pooled_std。"}
    fq = feats.copy()
    fq["quality"] = (fq["f_pred"] - fq["f_true"]).abs()
    per_row = fq.groupby(["unit_id", "window_ts", "feature"]).agg(
        level=("f_pred", "mean"), quality=("quality", "mean")).reset_index()
    ctx_y = df[df["model"] == df["model"].iloc[0]]
    ctx = ctx_y.groupby(["unit_id", "window_ts"]).agg(
        y_level=("y_true", "mean"),
        volatility=("y_true", lambda v: float(np.std(np.diff(v)))),
    ).reset_index()
    ctx["window_hour"] = pd.to_datetime(ctx["window_ts"]).dt.hour.astype(float)
    for m, g in rr.groupby("model"):
        n = len(g)
        kk = k if k is not None else min(50, max(MIN_K, int(np.ceil(0.1 * n))))
        if kk < MIN_K or n < 2 * kk:
            raise ValueError(
                f"行数 {n} 不足以取两组各 {kk}(最少每组 {MIN_K});样本太少不出对比")
        g = g.sort_values("rmse")
        best = g.head(kk)[["unit_id", "window_ts"]]
        worst = g.tail(kk)[["unit_id", "window_ts"]]
        def _pick(tbl, rows, col):
            j = tbl.merge(rows, on=["unit_id", "window_ts"])
            return j[col].values
        features, ranked = {}, []
        for fname, ft in per_row.groupby("feature"):
            has_true = ft["quality"].notna().any()
            basis = "quality" if has_true else "level"
            wv = _pick(ft, worst, basis)
            bv = _pick(ft, best, basis)
            if len(wv) < MIN_K or len(bv) < MIN_K:
                continue
            features[str(fname)] = {"basis": basis,
                                    **_contrast(wv, bv)}
        ranked = sorted(features, key=lambda f: -abs(features[f]["d"]))
        context = {}
        for col in ("y_level", "volatility", "window_hour"):
            context[col] = _contrast(_pick(ctx, worst, col), _pick(ctx, best, col))
        out["models"][str(m)] = {"k": kk, "features": features,
                                 "ranked": ranked, "context": context}
    return out


def render(stats: dict):
    import matplotlib.pyplot as plt
    cc.setup_font()
    n = len(stats["models"])
    fig, axes = plt.subplots(1, n, figsize=(6 * n, 4), squeeze=False)
    for ax, (m, s) in zip(axes[0], stats["models"].items()):
        names = s["ranked"]
        ds = [s["features"][f]["d"] for f in names]
        ax.barh(range(len(names)), ds)
        ax.set_yticks(range(len(names))), ax.set_yticklabels(names, fontsize=8)
        ax.axvline(0, color="k", lw=0.5)
        ax.invert_yaxis()
        ax.set_xlabel("Cohen's d (worst−best)")
        ax.set_title(f"{m} 好/坏样本特征分离度 (k={s['k']})")
    return fig


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--pred", required=True)
    ap.add_argument("--features", required=True)
    ap.add_argument("--out-dir", required=True)
    ap.add_argument("--k", type=int, default=None)
    a = ap.parse_args(argv)
    stats = compute(cc.load_predictions(a.pred), cc.load_features(a.features),
                    k=a.k)
    cc.save_outputs(render(stats), a.out_dir, RECIPE_ID, stats)


if __name__ == "__main__":
    main()
