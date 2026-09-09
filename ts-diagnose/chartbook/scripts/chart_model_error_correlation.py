"""model-error-correlation：模型间逐样本误差相关（口径由 --metric 定，默认 RMSE）——高相关=同质化
（组合增益有限），低相关=互补（动态选模/加权有空间）。"""
from __future__ import annotations

import argparse
from itertools import combinations

import numpy as np
import pandas as pd

import chart_common as cc

RECIPE_ID = "model-error-correlation"


def _pivot(df: pd.DataFrame, metric: str = "rmse") -> pd.DataFrame:
    rr = cc.row_metric(df, metric)
    piv = rr.pivot_table(index=["unit_id", "window_ts"], columns="model",
                         values="rmse").dropna()
    if piv.shape[1] < 2:
        raise ValueError("模型间相关至少需要 2 个模型的对齐样本")
    return piv


def compute(df: pd.DataFrame, by_month: bool = False,
            metric: str = "rmse") -> dict:
    piv = _pivot(df, metric)
    corr = piv.corr()
    pairs = {(a, b): float(corr.loc[a, b])
             for a, b in combinations(sorted(corr.columns), 2)}
    comp = min(pairs, key=pairs.get)
    red = max(pairs, key=pairs.get)
    out = {"recipe": RECIPE_ID, "metric": metric, "n_samples": int(len(piv)),
           "corr": {"all": {a: {b: round(float(corr.loc[a, b]), 4)
                                for b in corr.columns}
                            for a in corr.columns}},
           "most_complementary": {"pair": list(comp),
                                  "corr": round(pairs[comp], 4)},
           "most_redundant": {"pair": list(red),
                              "corr": round(pairs[red], 4)},
           "note": "相关>0.95 → 高度同质化，ensemble 组合增益有限；"
                   "最互补对是动态选模/加权的首选组合。"}
    if by_month:
        months = piv.index.get_level_values("window_ts").to_period("M")
        for mo in sorted(set(months)):
            sub = piv[months == mo]
            if len(sub) >= 3:
                c = sub.corr()
                out["corr"][str(mo)] = {a: {b: round(float(c.loc[a, b]), 4)
                                            for b in c.columns}
                                        for a in c.columns}
    return out


def render(stats: dict):
    import matplotlib.pyplot as plt
    cc.setup_font()
    names = list(stats["corr"]["all"])
    mat = np.array([[stats["corr"]["all"][a][b] for b in names]
                    for a in names], float)
    fig, ax = plt.subplots(figsize=(1.2 * len(names) + 2.5,
                                    1.2 * len(names) + 2))
    im = ax.imshow(mat, vmin=-1, vmax=1, cmap="RdYlGn_r")
    ax.set_xticks(range(len(names)), names, rotation=45, fontsize=8)
    ax.set_yticks(range(len(names)), names, fontsize=8)
    for i in range(len(names)):
        for j in range(len(names)):
            ax.text(j, i, f"{mat[i, j]:.2f}", ha="center", va="center",
                    fontsize=8)
    ax.set_title("model-error-correlation: per-sample "
                 f"{cc.metric_label(stats.get('metric', 'rmse'))} correlation")
    fig.colorbar(im, ax=ax, shrink=0.8)
    fig.tight_layout()
    return fig


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--pred", required=True)
    ap.add_argument("--out-dir", required=True)
    ap.add_argument("--by-month", action="store_true")
    ap.add_argument("--metric", default="rmse", choices=("rmse", "mse"),
                    help="逐行口径；分析主口径是逐行 MSE 时传 mse")
    a = ap.parse_args(argv)
    stats = compute(cc.load_predictions(a.pred), by_month=a.by_month,
                    metric=a.metric)
    cc.save_outputs(render(stats), a.out_dir, RECIPE_ID, stats)


if __name__ == "__main__":
    main()
