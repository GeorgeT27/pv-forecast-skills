"""cross-dim-stability：正交切分稳定性——时间对半 + 口径切换下，焦点与各他
模型的差距方向是否保持。同一份 predictions 派生的多张图属同一证据维度，方向
一致只是内部自洽；本图给「现象→假设」升级所需的跨维稳定性证据。"""
from __future__ import annotations

import argparse

import numpy as np
import pandas as pd

import chart_common as cc

RECIPE_ID = "cross-dim-stability"


def _hm(half_mean, model, half):
    v = half_mean.get((model, half))
    return float(v) if v is not None else float("nan")


def compute(df: pd.DataFrame, focal_model: str, metric: str = "rmse") -> dict:
    models = sorted(df["model"].unique())
    if focal_model not in models:
        raise ValueError(f"focal_model {focal_model!r} 不在数据模型集 {models}")
    if len(models) < 2:
        raise ValueError("跨维稳定性对比至少需要 2 个模型")
    rr = cc.row_metric(df, metric)
    ts_sorted = sorted(rr["window_ts"].unique())
    n_first = (len(ts_sorted) + 1) // 2
    cut_ts = ts_sorted[n_first - 1]
    rr["half"] = np.where(rr["window_ts"] <= cut_ts, "first", "second")
    half_mean = rr.groupby(["model", "half"])["rmse"].mean()
    row_mean = rr.groupby("model")["rmse"].mean()
    pooled = cc.pooled_metric(df, metric)
    pairs = {}
    for other in models:
        if other == focal_model:
            continue
        d1 = _hm(half_mean, focal_model, "first") - _hm(half_mean, other, "first")
        d2 = _hm(half_mean, focal_model, "second") - _hm(half_mean, other, "second")
        time_ok = bool(np.isfinite(d1) and np.isfinite(d2) and d1 * d2 > 0)
        rd = float(row_mean[focal_model] - row_mean[other])
        pooled_d = float(pooled[focal_model] - pooled[other])
        cal_ok = bool(rd * pooled_d > 0)
        pairs[other] = {
            "time_split": {"cut_ts": str(pd.Timestamp(cut_ts).date()),
                           "n_first": int(n_first),
                           "n_second": int(len(ts_sorted) - n_first),
                           "first_half_diff": round(d1, 4),
                           "second_half_diff": round(d2, 4),
                           "consistent": time_ok},
            "caliber_switch": {"row_diff": round(rd, 4),
                               "pooled_diff": round(pooled_d, 4),
                               "consistent": cal_ok},
            "verdict": {"time_stable": time_ok, "caliber_stable": cal_ok}}
    return {"recipe": RECIPE_ID, "focal": focal_model, "metric": metric,
            "pairs": pairs,
            "note": "同一份 predictions 的多图属同一证据维度，方向一致只是内部"
                    "自洽；本图给正交切分稳定性：time_stable 是「现象→假设」"
                    "必查项；caliber_stable=false 不阻塞升级，但结论必须限定"
                    "口径。半区差为零按不稳处理。两维都稳仍是同一份数据的重"
                    "切分——「已证实」照旧要走三道门之门2或外部实验。"}


def render(stats: dict):
    import matplotlib.pyplot as plt
    cc.setup_font()
    others = list(stats["pairs"])
    fig, axes = plt.subplots(len(others), 2, figsize=(9, 3.2 * len(others)),
                             squeeze=False)
    for i, o in enumerate(others):
        p = stats["pairs"][o]
        ts, cs = p["time_split"], p["caliber_switch"]
        axes[i][0].bar(["first half", "second half"],
                       [ts["first_half_diff"], ts["second_half_diff"]],
                       color="steelblue")
        axes[i][0].axhline(0, color="gray", lw=0.8)
        axes[i][0].set_title(f"{stats['focal']}−{o} time-half diff"
                             f" (consistent={ts['consistent']})")
        _lab = cc.metric_label(stats.get("metric", "rmse"))
        axes[i][1].bar([f"row-{_lab} mean", "point pool"],
                       [cs["row_diff"], cs["pooled_diff"]], color="darkorange")
        axes[i][1].axhline(0, color="gray", lw=0.8)
        axes[i][1].set_title(f"metric-switch diff (consistent={cs['consistent']})")
    fig.tight_layout()
    return fig


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--pred", required=True)
    ap.add_argument("--out-dir", required=True)
    ap.add_argument("--focal-model", required=True)
    ap.add_argument("--metric", default="rmse", choices=("rmse", "mse"),
                    help="逐行口径；分析主口径是逐行 MSE 时传 mse，"
                         "否则升级规则的输入与主口径脱钩")
    a = ap.parse_args(argv)
    stats = compute(cc.load_predictions(a.pred), focal_model=a.focal_model,
                    metric=a.metric)
    cc.save_outputs(render(stats), a.out_dir, RECIPE_ID, stats)


if __name__ == "__main__":
    main()
