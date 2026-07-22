"""feature-error-conditional：按 feature 值分箱与质量(|f_pred−f_true|)分箱的条件
y 误差——「feature 不准的时候，y-label 误差变大多少」。

只产图级事实（分箱指标+单调性+效应幅度），不做完整重要性归因（那属于
feature-importance playbook / 专用特征归因技能）。effect_ratio = 最差箱 RMSE /
最好箱 RMSE；rho = 箱序与 RMSE 的 Spearman（质量单调放大误差 → rho→1）。
"""
from __future__ import annotations

import argparse

import numpy as np
import pandas as pd

import chart_common as cc

RECIPE_ID = "feature-error-conditional"
JOIN = ["window_ts", "unit_id", "horizon_step"]


def _bin_rmse(joined, by_col, n_bins):
    d = joined.dropna(subset=[by_col])
    if d.empty or d[by_col].nunique() < 2:
        return None
    d = d.copy()
    if d[by_col].nunique() <= n_bins:
        # 离散少值（如质量误差只有 0/20 两档）：qcut 会塌箱，按值精确分组
        d["bin"] = d[by_col]
        g = d.groupby("bin")
    else:
        d["bin"] = pd.qcut(d[by_col], n_bins, duplicates="drop")
        g = d.groupby("bin", observed=True)
    rmse = g["err"].apply(lambda e: float(np.sqrt(np.mean(np.square(e)))))
    centers = g[by_col].mean()
    return {f"{c:.2f}": round(float(r), 4)
            for c, r in zip(centers.values, rmse.values)}, rmse


def _stats_of(rmse_series):
    v = rmse_series.values.astype(float)
    ratio = round(float(v.max() / v.min()), 4) if v.min() > 0 else None
    rho = float(pd.Series(range(len(v))).corr(pd.Series(v),
                                              method="spearman")) \
        if len(v) >= 2 else None
    return ratio, (round(rho, 4) if rho is not None else None)


def compute(pred_df: pd.DataFrame, feat_df: pd.DataFrame,
            n_bins: int = 5) -> dict:
    out = {"recipe": RECIPE_ID, "n_bins": n_bins, "models": {},
           "note": "quality=|f_pred−f_true|；effect_ratio=最差箱/最好箱 RMSE；"
                   "rho→1 = 质量越差误差单调越大。f_true 全缺 → 质量分箱记 null，"
                   "只看值分箱。只产图级事实，归因回 playbook。"}
    feat_df = feat_df.copy()
    feat_df["quality"] = (feat_df["f_pred"] - feat_df["f_true"]).abs()
    for m, g in pred_df.groupby("model"):
        per_feature = {}
        for feat, fg in feat_df.groupby("feature"):
            joined = g.merge(fg[JOIN + ["f_pred", "quality"]], on=JOIN,
                             how="inner")
            if joined.empty:
                continue
            vb = _bin_rmse(joined, "f_pred", n_bins)
            qb = _bin_rmse(joined, "quality", n_bins)
            entry = {"n": int(len(joined)),
                     "value_bins": vb[0] if vb else None,
                     "quality_bins": qb[0] if qb else None,
                     "value_effect_ratio": None, "value_monotonic_rho": None,
                     "quality_effect_ratio": None,
                     "quality_monotonic_rho": None}
            if vb:
                entry["value_effect_ratio"], entry["value_monotonic_rho"] = \
                    _stats_of(vb[1])
            if qb:
                entry["quality_effect_ratio"], entry["quality_monotonic_rho"] = \
                    _stats_of(qb[1])
            per_feature[str(feat)] = entry
        out["models"][str(m)] = per_feature
    return out


def render(stats: dict):
    import matplotlib.pyplot as plt
    cc.setup_font()
    models = list(stats["models"])
    fig, axes = plt.subplots(len(models), 1,
                             figsize=(10, 3.2 * len(models)), squeeze=False)
    for ax, m in zip(axes.ravel(), models):
        for feat, e in stats["models"][m].items():
            bins = e["quality_bins"] or e["value_bins"] or {}
            ax.plot(range(len(bins)), list(bins.values()), "-o", ms=3,
                    label=f"{feat}"
                          f"(ratio={e['quality_effect_ratio'] or e['value_effect_ratio']})")
        ax.set_title(f"feature-error-conditional 分箱条件 RMSE — {m}",
                     fontsize=10)
        ax.set_xlabel("箱序（质量/值 由低到高）"), ax.set_ylabel("RMSE")
        ax.legend(fontsize=7)
    fig.tight_layout()
    return fig


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--pred", required=True)
    ap.add_argument("--features", required=True)
    ap.add_argument("--out-dir", required=True)
    ap.add_argument("--n-bins", type=int, default=5)
    a = ap.parse_args(argv)
    stats = compute(cc.load_predictions(a.pred), cc.load_features(a.features),
                    n_bins=a.n_bins)
    cc.save_outputs(render(stats), a.out_dir, RECIPE_ID, stats)


if __name__ == "__main__":
    main()
