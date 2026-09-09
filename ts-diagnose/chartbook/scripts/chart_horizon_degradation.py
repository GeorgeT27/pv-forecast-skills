"""horizon-degradation：指标随预报步退化——早/晚段斜率、模型交叉点、
per-unit 崩溃 horizon（短期准长期失效的量化）。"""
from __future__ import annotations

import argparse
from itertools import combinations

import numpy as np
import pandas as pd

import chart_common as cc

RECIPE_ID = "horizon-degradation"


def _metric_by_step(g, metric="rmse"):
    """按预报步池化的误差曲线；metric ∈ {rmse, mse}，与分析主口径同源。"""
    return g.groupby("horizon_step")["err"].apply(
        cc.metric_fn(metric)).sort_index()


def compute(df: pd.DataFrame, early_frac: float = 0.25,
            late_frac: float = 0.25, collapse_mult: float = 1.5,
            metric: str = "rmse") -> dict:
    n_steps = int(df["horizon_step"].max()) + 1
    n_early = max(2, int(np.ceil(n_steps * early_frac)))
    n_late = max(2, int(np.ceil(n_steps * late_frac)))
    out = {"recipe": RECIPE_ID, "n_steps": n_steps,
           "params": {"early_frac": early_frac, "late_frac": late_frac,
                      "collapse_mult": collapse_mult,
                      "n_early": n_early, "n_late": n_late},
           "metric": metric,
           "models": {}, "crossings": {}, "collapse_horizon": {},
           "note": f"曲线口径=按预报步池化的 {cc.metric_label(metric)}；"
                   "斜率=对应段最小二乘；崩溃点=首个值 >collapse_mult×早段均值"
                   "的 step（该单元该模型自身早段为基准，跨模型可比排名不比数值）。"}
    curves = {}
    for m, g in df.groupby("model"):
        rmse = _metric_by_step(g, metric)
        bias = g.groupby("horizon_step")["err"].mean().sort_index()
        v = rmse.values
        steps = np.arange(n_steps, dtype=float)
        out["models"][str(m)] = {
            "rmse_by_step": cc.curve_stats(v),  # 列名固定，口径以 metric 字段为准
            "bias_by_step": cc.curve_stats(bias.values),
            "early_slope": round(float(np.polyfit(steps[:n_early],
                                                  v[:n_early], 1)[0]), 6),
            "late_slope": round(float(np.polyfit(steps[-n_late:],
                                                 v[-n_late:], 1)[0]), 6),
        }
        curves[str(m)] = v
        coll = {}
        for u, gu in g.groupby("unit_id"):
            vu = _metric_by_step(gu, metric).values
            base = float(np.mean(vu[:n_early]))
            over = np.nonzero(vu > collapse_mult * base)[0]
            coll[str(u)] = int(over[0]) if len(over) else None
        out["collapse_horizon"][str(m)] = coll
    for a, b in combinations(sorted(curves), 2):
        diff = curves[a] - curves[b]
        sign = np.sign(diff)
        nz = sign != 0
        cross = None
        prev = None
        for i in range(len(diff)):
            if not nz[i]:
                continue
            if prev is not None and sign[i] != prev:
                cross = i
                break
            prev = sign[i]
        out["crossings"][f"{a}|{b}"] = cross
    return out


def render(stats: dict):
    import matplotlib.pyplot as plt
    cc.setup_font()
    fig, axes = plt.subplots(2, 1, figsize=(10, 6), sharex=True)
    for m, s in stats["models"].items():
        for ax, key in zip(axes, ("rmse_by_step", "bias_by_step")):
            curve = s[key]["curve"]
            ax.plot([int(k) for k in curve], list(curve.values()), label=m)
    axes[0].set_ylabel(cc.metric_label(stats.get("metric", "rmse")))
    axes[1].set_ylabel("bias")
    axes[1].axhline(0, color="k", lw=0.5)
    axes[1].set_xlabel(f"forecast step (0–{stats['n_steps'] - 1})")
    axes[0].set_title("horizon-degradation: error vs lead time "
                      f"[{cc.metric_label(stats.get('metric', 'rmse'))}]")
    axes[0].legend(ncol=max(1, len(stats["models"])))
    return fig


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--pred", required=True)
    ap.add_argument("--out-dir", required=True)
    ap.add_argument("--early-frac", type=float, default=0.25)
    ap.add_argument("--late-frac", type=float, default=0.25)
    ap.add_argument("--collapse-mult", type=float, default=1.5)
    ap.add_argument("--metric", choices=("rmse", "mse"), default="rmse",
                    help="曲线口径，须与分析主口径同源（gap_summary 的 caliber）")
    a = ap.parse_args(argv)
    stats = compute(cc.load_predictions(a.pred), early_frac=a.early_frac,
                    late_frac=a.late_frac, collapse_mult=a.collapse_mult,
                    metric=a.metric)
    cc.save_outputs(render(stats), a.out_dir, RECIPE_ID, stats)


if __name__ == "__main__":
    main()
