"""oracle-gap：逐样本(unit×window)事后选最优单模型的 oracle 下界——
量化「动态选模/组合」的理论提升空间；ensemble 存在时另报 ensemble−oracle。"""
from __future__ import annotations

import argparse

import numpy as np
import pandas as pd

import chart_common as cc

RECIPE_ID = "oracle-gap"


def compute(df: pd.DataFrame, ensemble_key: str | None = None) -> dict:
    rr = cc.row_rmse(df)
    piv = rr.pivot_table(index=["unit_id", "window_ts"], columns="model",
                         values="rmse").dropna()
    singles = [c for c in piv.columns if c != ensemble_key]
    if len(singles) < 2:
        raise ValueError("oracle 至少需要 2 个（非 ensemble）模型的对齐样本")
    oracle = piv[singles].min(axis=1)
    picks = piv[singles].idxmin(axis=1)
    means = piv.mean()
    best_single = float(means[singles].min())
    dates = piv.index.get_level_values("window_ts").strftime("%Y-%m-%d")
    daily = piv.assign(oracle=oracle).groupby(dates).mean()
    return {
        "recipe": RECIPE_ID, "ensemble_key": ensemble_key,
        "n_samples": int(len(piv)),
        "mean_rmse": {**{str(m): round(float(v), 4)
                         for m, v in means.items()},
                      "oracle": round(float(oracle.mean()), 4)},
        "best_single_minus_oracle": round(best_single - float(oracle.mean()), 4),
        "ensemble_minus_oracle": (
            round(float(means[ensemble_key]) - float(oracle.mean()), 4)
            if ensemble_key in piv.columns else None),
        "oracle_pick_share": {str(k): round(float(v), 4)
                              for k, v in picks.value_counts(
                                  normalize=True).items()},
        "daily_rmse": {str(col): cc.downsample(
            {str(d): round(float(v), 4) for d, v in daily[col].items()})
            for col in daily.columns},
        "note": "gap 大 → 动态选模有空间；pick_share 看谁最常是逐样本最优；"
                "ensemble−oracle 大 → 现组合方式远未吃满互补性。"}


def render(stats: dict):
    import matplotlib.pyplot as plt
    cc.setup_font()
    fig, ax = plt.subplots(figsize=(12, 4))
    for col, series in stats["daily_rmse"].items():
        style = (dict(color="black", ls="--", lw=1.5) if col == "oracle"
                 else dict(lw=0.9))
        ax.plot(pd.to_datetime(list(series)), list(series.values()),
                label=col, **style)
    gap = stats["best_single_minus_oracle"]
    ax.set_title(f"oracle-gap（最优单模型−oracle 日均 = {gap:.3f}）")
    ax.set_ylabel("日均行 RMSE"), ax.legend(ncol=len(stats["daily_rmse"]))
    fig.autofmt_xdate()
    return fig


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--pred", required=True)
    ap.add_argument("--out-dir", required=True)
    ap.add_argument("--ensemble-key", default=None)
    a = ap.parse_args(argv)
    stats = compute(cc.load_predictions(a.pred), ensemble_key=a.ensemble_key)
    cc.save_outputs(render(stats), a.out_dir, RECIPE_ID, stats)


if __name__ == "__main__":
    main()
