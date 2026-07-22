"""feature-trend-overlay：焦点模型最差月份内，feature 走势/质量与 y 日误差的
对齐 overlay——「坏片上输入是不是也在坏」。

sync_basis：有 f_true → 用日均质量 |f_pred−f_true| 与日 RMSE 求 Pearson（quality）；
f_true 全缺 → 退化用日均 f_pred 水平（level，仅提示同步性、不可归因质量）。
"""
from __future__ import annotations

import argparse

import numpy as np
import pandas as pd

import chart_common as cc

RECIPE_ID = "feature-trend-overlay"


def compute(pred_df: pd.DataFrame, feat_df: pd.DataFrame,
            model: str | None = None, slice_month: str | None = None) -> dict:
    models = sorted(pred_df["model"].unique())
    focal = model or models[0]
    if focal not in models:
        raise ValueError(f"model {focal!r} 不在数据模型集 {models}")
    rr = cc.row_rmse(pred_df[pred_df["model"] == focal])
    rr["month"] = pd.to_datetime(rr["window_ts"]).dt.strftime("%Y-%m")
    rr["date"] = pd.to_datetime(rr["window_ts"]).dt.strftime("%Y-%m-%d")
    sl = slice_month or str(rr.groupby("month")["rmse"].mean().idxmax())
    in_rr = rr[rr["month"] == sl]
    y_daily = in_rr.groupby("date")["rmse"].mean()
    fd = feat_df.copy()
    fd["month"] = fd["window_ts"].dt.strftime("%Y-%m")
    fd["date"] = fd["window_ts"].dt.strftime("%Y-%m-%d")
    fd["quality"] = (fd["f_pred"] - fd["f_true"]).abs()
    out = {"recipe": RECIPE_ID, "model": focal, "slice": sl, "features": {},
           "note": "sync_corr=日 RMSE 与日均质量(或水平)的 Pearson；"
                   "level 口径只提示同步、不可归因质量。"}
    for feat, fg in fd[fd["month"] == sl].groupby("feature"):
        daily = fg.groupby("date").agg(f_pred=("f_pred", "mean"),
                                       f_true=("f_true", "mean"),
                                       quality=("quality", "mean"))
        aligned = daily.join(y_daily.rename("y_rmse"), how="inner").dropna(
            subset=["y_rmse"])
        has_quality = aligned["quality"].notna().any()
        basis_col = "quality" if has_quality else "f_pred"
        corr = float(aligned["y_rmse"].corr(aligned[basis_col])) \
            if len(aligned) >= 3 else None
        rec = {}
        for d, row in aligned.iterrows():
            item = {"y_rmse": round(float(row["y_rmse"]), 4),
                    "f_pred": round(float(row["f_pred"]), 4)}
            if np.isfinite(row["f_true"]):
                item["f_true"] = round(float(row["f_true"]), 4)
            if np.isfinite(row["quality"]):
                item["quality"] = round(float(row["quality"]), 4)
            rec[str(d)] = item
        out["features"][str(feat)] = {
            "aligned": cc.downsample(rec),
            "sync_basis": "quality" if has_quality else "level",
            "sync_corr": (round(corr, 4) if corr is not None
                          and np.isfinite(corr) else None),
            "n_days": int(len(aligned))}
    return out


def render(stats: dict):
    import matplotlib.pyplot as plt
    cc.setup_font()
    feats = list(stats["features"])
    fig, axes = plt.subplots(max(len(feats), 1), 1,
                             figsize=(11, 3 * max(len(feats), 1)),
                             squeeze=False)
    for ax, feat in zip(axes.ravel(), feats):
        e = stats["features"][feat]
        days = pd.to_datetime(list(e["aligned"]))
        ax.plot(days, [v["y_rmse"] for v in e["aligned"].values()],
                color="firebrick", label="y 日RMSE")
        ax2 = ax.twinx()
        key = "quality" if e["sync_basis"] == "quality" else "f_pred"
        ax2.plot(days, [v.get(key) for v in e["aligned"].values()],
                 color="steelblue", ls="--", label=key)
        ax.set_title(f"feature-trend-overlay {stats['slice']} — {feat} "
                     f"(corr={e['sync_corr']})", fontsize=10)
        ax.legend(loc="upper left"), ax2.legend(loc="upper right")
    fig.autofmt_xdate()
    fig.tight_layout()
    return fig


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--pred", required=True)
    ap.add_argument("--features", required=True)
    ap.add_argument("--out-dir", required=True)
    ap.add_argument("--model", default=None)
    ap.add_argument("--slice-month", default=None)
    a = ap.parse_args(argv)
    stats = compute(cc.load_predictions(a.pred), cc.load_features(a.features),
                    model=a.model, slice_month=a.slice_month)
    cc.save_outputs(render(stats), a.out_dir, RECIPE_ID, stats)


if __name__ == "__main__":
    main()
