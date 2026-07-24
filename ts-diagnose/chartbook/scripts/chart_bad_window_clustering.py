"""bad-window-clustering:worst-N 窗口真值曲线归一化聚类——坏样本是几种失败模式。"""
from __future__ import annotations

import argparse
import warnings

import numpy as np
import pandas as pd
from sklearn.cluster import KMeans
from sklearn.exceptions import ConvergenceWarning
from sklearn.metrics import silhouette_score

import chart_common as cc

RECIPE_ID = "bad-window-clustering"
MAX_POINTS = 24


def _curve(y: np.ndarray):
    """z 归一化 + 重采样 ≤MAX_POINTS;平坦窗返回 None。"""
    sd = float(np.std(y))
    if sd < 1e-9:
        return None
    z = (y - np.mean(y)) / sd
    if len(z) > MAX_POINTS:
        idx = np.linspace(0, len(z) - 1, MAX_POINTS).round().astype(int)
        z = z[idx]
    return z


def compute(df: pd.DataFrame, top_n: int = 50, seed: int = 0) -> dict:
    rr = cc.row_rmse(df)
    out = {"recipe": RECIPE_ID, "top_n": top_n, "models": {},
           "note": "每窗 y_true z 归一化后 k-means;k∈2..4 由轮廓系数选;"
                   "σ≈0 平坦窗跳过(skipped_flat);簇命名交判读层。"}
    truth = df[df["model"] == df["model"].iloc[0]]
    for m, g in rr.groupby("model"):
        worst = g.sort_values("rmse").tail(top_n)
        curves, keys, rmses, skipped = [], [], [], 0
        for _, row in worst.iterrows():
            gw = truth[(truth["unit_id"] == row["unit_id"]) &
                       (truth["window_ts"] == row["window_ts"])]
            gw = gw.sort_values("horizon_step")
            z = _curve(gw["y_true"].values)
            if z is None:
                skipped += 1
                continue
            curves.append(z), keys.append(
                f"{row['unit_id']}|{row['window_ts']}"), rmses.append(row["rmse"])
        entry = {"chosen_k": None, "silhouette_by_k": {}, "seed": seed,
                 "clusters": [], "skipped_flat": skipped, "n_clustered": len(curves)}
        if len(curves) >= 6:
            X = np.vstack(curves)
            best_k, best_s, best_labels = None, -np.inf, None
            for k in (2, 3, 4):
                if k >= len(X):
                    continue
                with warnings.catch_warnings():
                    # k > 真实形状数时重复点必然簇合并——固有告警,局部消音防污染测试输出
                    warnings.simplefilter("ignore", ConvergenceWarning)
                    km = KMeans(n_clusters=k, n_init=10, random_state=seed).fit(X)
                    s = float(silhouette_score(X, km.labels_))
                entry["silhouette_by_k"][str(k)] = round(s, 4)
                if s > best_s:
                    best_k, best_s, best_labels = k, s, km.labels_
            entry["chosen_k"] = best_k
            for ci in range(best_k):
                mask = best_labels == ci
                entry["clusters"].append({
                    "share": round(float(np.mean(mask)), 4),
                    "n": int(mask.sum()),
                    "mean_rmse": round(float(np.mean(np.array(rmses)[mask])), 4),
                    "members": [keys[i] for i in np.where(mask)[0]],
                    "prototype": [round(float(v), 4)
                                  for v in X[mask].mean(axis=0)]})
        out["models"][str(m)] = entry
    return out


def render(stats: dict):
    import matplotlib.pyplot as plt
    cc.setup_font()
    n = len(stats["models"])
    fig, axes = plt.subplots(1, n, figsize=(6 * n, 4), squeeze=False)
    for ax, (m, s) in zip(axes[0], stats["models"].items()):
        for i, c in enumerate(s["clusters"]):
            ax.plot(c["prototype"], lw=1.5,
                    label=f"cluster {i} share={c['share']:.2f} rmse={c['mean_rmse']:.2f}")
        ax.set_title(f"{m} bad-window prototypes (k={s['chosen_k']})")
        ax.set_xlabel("normalized position in window"), ax.set_ylabel("z(y_true)")
        if s["clusters"]:
            ax.legend(fontsize=8)
    return fig


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--pred", required=True)
    ap.add_argument("--out-dir", required=True)
    ap.add_argument("--top-n", type=int, default=50)
    ap.add_argument("--seed", type=int, default=0)
    a = ap.parse_args(argv)
    stats = compute(cc.load_predictions(a.pred), top_n=a.top_n, seed=a.seed)
    cc.save_outputs(render(stats), a.out_dir, RECIPE_ID, stats)


if __name__ == "__main__":
    main()
