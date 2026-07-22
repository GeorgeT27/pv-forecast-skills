"""worst-slice-compare：焦点模型最差片（默认按月）上的全模型同期对比——
「A 输掉的是一个月还是整个周期」。片指标 = 片内行 RMSE 均值。"""
from __future__ import annotations

import argparse

import numpy as np
import pandas as pd

import chart_common as cc

RECIPE_ID = "worst-slice-compare"


def compute(df: pd.DataFrame, focal_model: str,
            slice_by: str = "month") -> dict:
    models = sorted(df["model"].unique())
    if focal_model not in models:
        raise ValueError(f"focal_model {focal_model!r} 不在数据模型集 {models}")
    if len(models) < 2:
        raise ValueError("同期对比至少需要 2 个模型")
    rr = cc.row_rmse(df)
    if slice_by != "month":
        raise ValueError("v1 仅支持 slice_by=month")
    rr["slice"] = pd.to_datetime(rr["window_ts"]).dt.strftime("%Y-%m")
    rr["date"] = pd.to_datetime(rr["window_ts"]).dt.strftime("%Y-%m-%d")
    focal = rr[rr["model"] == focal_model]
    basis = focal.groupby("slice")["rmse"].mean().sort_index()
    worst = str(basis.idxmax())
    per = rr.groupby(["slice", "model"])["rmse"].mean().unstack()
    others = [m for m in models if m != focal_model]
    gaps = (per[focal_model] - per[others].min(axis=1)).fillna(0.0)
    pos = gaps.clip(lower=0.0)
    conc = (round(float(pos[worst] / pos.sum()), 4)
            if float(pos.sum()) > 0 else None)
    sl = rr[rr["slice"] == worst]
    daily = sl.groupby(["model", "date"])["rmse"].mean()
    return {
        "recipe": RECIPE_ID, "focal": focal_model, "slice_by": slice_by,
        "worst_slice": worst,
        "basis": {k: round(float(v), 4) for k, v in basis.items()},
        "overall": {m: round(float(v), 4)
                    for m, v in rr.groupby("model")["rmse"].mean().items()},
        "in_slice": {m: round(float(v), 4)
                     for m, v in sl.groupby("model")["rmse"].mean().items()},
        "daily_in_slice": {m: cc.downsample(
            {d: round(float(v), 4) for d, v in daily[m].items()})
            for m in models if m in daily.index.get_level_values(0)},
        "slice_gaps": {k: round(float(v), 4) for k, v in gaps.items()},
        "concentration_ratio": conc,
        "note": "片指标=片内行 RMSE 均值；gap=焦点−同片最优他模型；"
                "concentration_ratio→1 表示差距集中于最差片，→均匀表示普遍性落后。"}


def render(stats: dict):
    import matplotlib.pyplot as plt
    cc.setup_font()
    fig, axes = plt.subplots(1, 2, figsize=(13, 4.2),
                             gridspec_kw={"width_ratios": [2, 3]})
    models = list(stats["in_slice"])
    axes[0].bar(models, [stats["in_slice"][m] for m in models],
                color=["firebrick" if m == stats["focal"] else "steelblue"
                       for m in models])
    axes[0].set_title(f"最差片 {stats['worst_slice']} 内各模型 RMSE")
    for m, series in stats["daily_in_slice"].items():
        axes[1].plot(pd.to_datetime(list(series)), list(series.values()),
                     label=m, lw=1.5 if m == stats["focal"] else 0.9)
    axes[1].set_title("片内逐日对比"), axes[1].legend()
    fig.autofmt_xdate()
    fig.tight_layout()
    return fig


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--pred", required=True)
    ap.add_argument("--out-dir", required=True)
    ap.add_argument("--focal-model", required=True)
    ap.add_argument("--slice-by", default="month")
    a = ap.parse_args(argv)
    stats = compute(cc.load_predictions(a.pred), focal_model=a.focal_model,
                    slice_by=a.slice_by)
    cc.save_outputs(render(stats), a.out_dir, RECIPE_ID, stats)


if __name__ == "__main__":
    main()
