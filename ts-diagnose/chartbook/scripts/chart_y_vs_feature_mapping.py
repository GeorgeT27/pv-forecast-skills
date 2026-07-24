"""y-vs-feature-mapping：y_true 与关键 feature 的映射曲线，按 split 日期分前后
两期对比——映射整体位移 = 物理关系改变（组件衰减/扩容/限电），所有模型同时受害。

分箱边界取全期 pooled 分位（两期同一把尺）；f 参考值 = f_true（缺则退 f_pred）。
把训练期数据并入对比：由适配器把训练段追加进两张长表再指定 --split-date 即可，
本脚本只认 split。
"""
from __future__ import annotations

import argparse

import numpy as np
import pandas as pd

import chart_common as cc

RECIPE_ID = "y-vs-feature-mapping"
JOIN = ["window_ts", "unit_id", "horizon_step"]


def compute(pred_df: pd.DataFrame, feat_df: pd.DataFrame,
            split_date: str | None = None, n_bins: int = 8) -> dict:
    first = pred_df["model"].iloc[0]
    y = pred_df[pred_df["model"] == first][JOIN + ["y_true"]].drop_duplicates()
    split = pd.Timestamp(split_date) if split_date else \
        pred_df["window_ts"].drop_duplicates().sort_values().reset_index(
            drop=True).median()
    fd = feat_df.copy()
    fd["f_ref"] = fd["f_true"].where(fd["f_true"].notna(), fd["f_pred"])
    out = {"recipe": RECIPE_ID, "split_date": str(split), "n_bins": n_bins,
           "features": {},
           "note": "curve_a=split 前、curve_b=split 后；分箱边界全期 pooled；"
                   "mean_shift=各公共箱 (b−a) 均值——整体位移 → 物理映射改变，"
                   "所有模型同时受害。"}
    for feat, fg in fd.groupby("feature"):
        j = fg.merge(y, on=JOIN, how="inner").dropna(subset=["f_ref", "y_true"])
        if j["f_ref"].nunique() < n_bins:
            continue
        edges = np.unique(j["f_ref"].quantile(
            np.linspace(0, 1, n_bins + 1)).values)
        j = j.copy()
        j["bin"] = pd.cut(j["f_ref"], bins=edges, include_lowest=True)
        j["period"] = np.where(j["window_ts"] < split, "a", "b")
        g = j.groupby(["bin", "period"], observed=True).agg(
            f=("f_ref", "mean"), yv=("y_true", "mean"), n=("y_true", "size"))
        curves = {"a": {}, "b": {}}
        shifts = []
        for b in j["bin"].cat.categories:
            try:
                ra = g.loc[(b, "a")]
                rb = g.loc[(b, "b")]
            except KeyError:
                continue
            key = f"{(ra.f + rb.f) / 2:.2f}"
            curves["a"][key] = round(float(ra.yv), 4)
            curves["b"][key] = round(float(rb.yv), 4)
            shifts.append(float(rb.yv - ra.yv))
        out["features"][str(feat)] = {
            "curve_a": curves["a"], "curve_b": curves["b"],
            "mean_shift": round(float(np.mean(shifts)), 4) if shifts else None,
            "mean_abs_shift": (round(float(np.mean(np.abs(shifts))), 4)
                               if shifts else None),
            "n_a": int((j["period"] == "a").sum()),
            "n_b": int((j["period"] == "b").sum())}
    return out


def render(stats: dict):
    import matplotlib.pyplot as plt
    cc.setup_font()
    feats = list(stats["features"])
    fig, axes = plt.subplots(1, max(len(feats), 1),
                             figsize=(6 * max(len(feats), 1), 4.5),
                             squeeze=False)
    for ax, feat in zip(axes.ravel(), feats):
        e = stats["features"][feat]
        for period, color in (("curve_a", "steelblue"), ("curve_b", "firebrick")):
            xs = [float(k) for k in e[period]]
            ax.plot(xs, list(e[period].values()), "-o", ms=3, color=color,
                    label=period[-1] + " period")
        ax.set_title(f"y-vs-feature-mapping — {feat} "
                     f"(shift={e['mean_shift']})", fontsize=10)
        ax.set_xlabel(feat), ax.set_ylabel("mean y_true"), ax.legend()
    fig.tight_layout()
    return fig


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--pred", required=True)
    ap.add_argument("--features", required=True)
    ap.add_argument("--out-dir", required=True)
    ap.add_argument("--split-date", default=None)
    ap.add_argument("--n-bins", type=int, default=8)
    a = ap.parse_args(argv)
    stats = compute(cc.load_predictions(a.pred), cc.load_features(a.features),
                    split_date=a.split_date, n_bins=a.n_bins)
    cc.save_outputs(render(stats), a.out_dir, RECIPE_ID, stats)


if __name__ == "__main__":
    main()
