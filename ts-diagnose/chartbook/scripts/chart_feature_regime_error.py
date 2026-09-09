"""feature-regime-error:窗口级多变量特征聚类出"制式",各制式条件误差——
误差集中在哪种输入状态。"""
from __future__ import annotations

import argparse

import warnings

import numpy as np
import pandas as pd
from sklearn.cluster import KMeans
from sklearn.exceptions import ConvergenceWarning
from sklearn.metrics import silhouette_score

import chart_common as cc

RECIPE_ID = "feature-regime-error"


def compute(df: pd.DataFrame, feats: pd.DataFrame, seed: int = 0,
            metric: str = "rmse") -> dict:
    vec = (feats.groupby(["unit_id", "window_ts", "feature"])["f_pred"].mean()
           .unstack("feature").dropna())
    if len(vec) < 8:
        raise ValueError(f"可聚类窗口数 {len(vec)} < 8,不足以分制式")
    X = vec.values
    mu, sd = X.mean(axis=0), X.std(axis=0)
    sd[sd < 1e-12] = 1.0
    Xz = (X - mu) / sd
    sil, best = {}, (None, -np.inf, None)
    for k in (2, 3, 4):
        if k >= len(Xz):
            continue
        with warnings.catch_warnings():
            # k > 真实制式数时重复点必然簇合并——固有告警,局部消音防污染测试输出
            warnings.simplefilter("ignore", ConvergenceWarning)
            km = KMeans(n_clusters=k, n_init=10, random_state=seed).fit(Xz)
            s = float(silhouette_score(Xz, km.labels_))
        sil[str(k)] = round(s, 4)
        if s > best[1]:
            best = (k, s, km.labels_)
    k, _, labels = best
    rr = cc.row_metric(df, metric)
    lab = pd.Series(labels, index=vec.index, name="regime")
    rr = rr.join(lab, on=["unit_id", "window_ts"]).dropna(subset=["regime"])
    out = {"recipe": RECIPE_ID, "chosen_k": int(k), "silhouette_by_k": sil,
           "metric": metric, "seed": seed, "regimes": [], "worst_best_ratio_by_model": {},
           "note": "制式=窗口级 f_pred 均值向量标准化后 k-means;centroid 为"
                   "原始单位;制式命名交判读层结合 intake 背景。"}
    for ci in range(k):
        members = vec.index[labels == ci]
        sub = rr[rr["regime"] == ci]
        out["regimes"].append({
            "share": round(float(np.mean(labels == ci)), 4),
            "n": int((labels == ci).sum()),
            "centroid": {c: round(float(v), 4)
                         for c, v in vec.loc[members].mean().items()},
            "rmse_by_model": {str(m): round(float(g["rmse"].mean()), 4)
                              for m, g in sub.groupby("model")}})
    for m in rr["model"].unique():
        vals = [r["rmse_by_model"].get(str(m)) for r in out["regimes"]
                if r["rmse_by_model"].get(str(m)) is not None]
        if vals and min(vals) > 1e-12:
            out["worst_best_ratio_by_model"][str(m)] = round(
                max(vals) / min(vals), 4)
    return out


def render(stats: dict):
    import matplotlib.pyplot as plt
    cc.setup_font()
    fig, ax = plt.subplots(figsize=(7, 4))
    regimes = stats["regimes"]
    models = sorted({m for r in regimes for m in r["rmse_by_model"]})
    x = np.arange(len(regimes))
    w = 0.8 / max(1, len(models))
    for i, m in enumerate(models):
        ax.bar(x + i * w, [r["rmse_by_model"].get(m, 0) for r in regimes],
               width=w, label=m)
    ax.set_xticks(x + 0.4 - w / 2)
    ax.set_xticklabels([f"regime {i}\nshare={r['share']:.2f}"
                        for i, r in enumerate(regimes)], fontsize=8)
    ax.set_ylabel(f"mean row {cc.metric_label(stats.get('metric', 'rmse'))}")
    ax.set_title(f"feature-regime-error (k={stats['chosen_k']})")
    ax.legend(fontsize=8)
    return fig


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--pred", required=True)
    ap.add_argument("--features", required=True)
    ap.add_argument("--out-dir", required=True)
    ap.add_argument("--seed", type=int, default=0)
    ap.add_argument("--metric", default="rmse", choices=("rmse", "mse"),
                    help="逐行口径；分析主口径是逐行 MSE 时传 mse")
    a = ap.parse_args(argv)
    stats = compute(cc.load_predictions(a.pred), cc.load_features(a.features),
                    seed=a.seed, metric=a.metric)
    cc.save_outputs(render(stats), a.out_dir, RECIPE_ID, stats)


if __name__ == "__main__":
    main()
