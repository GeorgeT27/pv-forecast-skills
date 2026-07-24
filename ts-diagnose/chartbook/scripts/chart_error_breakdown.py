"""error-breakdown：分单元×日历(月/小时)×horizon 误差矩阵——谁、什么时候、错在哪。

JSON 一等产物；单元格 RMSE = sqrt(mean(err²))（点级聚合，跨单元格可比）。
"""
from __future__ import annotations

import argparse

import numpy as np
import pandas as pd

import chart_common as cc

RECIPE_ID = "error-breakdown"
N_BANDS = 4


def _cell_rmse(df, keys):
    return (df.groupby(keys, observed=False)["err"]
            .apply(lambda e: float(np.sqrt(np.mean(np.square(e))))))


def compute(df: pd.DataFrame, freq: str = "15min", top_k: int = 10) -> dict:
    d = df.copy()
    d["month"] = d["window_ts"].dt.strftime("%Y-%m")
    # 目标时刻 = window_ts + step*freq（hour 维度按目标物理时刻算，不是发起时刻）
    d["target_hour"] = (d["window_ts"]
                        + d["horizon_step"] * pd.Timedelta(freq)).dt.hour
    n_steps = int(d["horizon_step"].max()) + 1
    band_edges = np.linspace(0, n_steps, N_BANDS + 1).astype(int)
    d["band"] = pd.cut(d["horizon_step"], bins=band_edges, right=False,
                       labels=[f"band{i}" for i in range(N_BANDS)],
                       include_lowest=True)
    out = {"recipe": RECIPE_ID, "freq": freq, "n_steps": n_steps,
           "band_edges": band_edges.tolist(), "models": {},
           "note": "单元格 RMSE=sqrt(mean(err^2)) 点级聚合；argmax_cell 即"
                   "「什么单元什么时候最差」；判读读边际 curve_stats 描述符。"}
    for m, g in d.groupby("model"):
        um = _cell_rmse(g, ["unit_id", "month"]).unstack()
        uh = _cell_rmse(g, ["unit_id", "target_hour"]).unstack()
        ub = _cell_rmse(g, ["unit_id", "band"]).unstack()
        flat = _cell_rmse(g, ["unit_id", "month"]).sort_values(ascending=False)
        counts = g.groupby(["unit_id", "month"])["err"].size()
        (u_star, mo_star) = flat.index[0]
        per_month = _cell_rmse(g, ["month"]).sort_index()
        per_hour = _cell_rmse(g, ["target_hour"]).sort_index()
        out["models"][str(m)] = {
            "unit_month_rmse": {u: {k: round(float(v), 4)
                                    for k, v in row.dropna().items()}
                                for u, row in um.iterrows()},
            "unit_hour_rmse": {u: {str(k): round(float(v), 4)
                                   for k, v in row.dropna().items()}
                               for u, row in uh.iterrows()},
            "unit_band_rmse": {u: {str(k): round(float(v), 4)
                                   for k, v in row.dropna().items()}
                               for u, row in ub.iterrows()},
            "argmax_cell": {"unit": str(u_star), "month": str(mo_star),
                            "rmse": round(float(flat.iloc[0]), 4),
                            "n": int(counts[(u_star, mo_star)])},
            "per_unit_rmse": {str(u): round(float(v), 4)
                              for u, v in _cell_rmse(g, ["unit_id"]).items()},
            "per_month": cc.curve_stats(per_month.values,
                                        index=list(per_month.index)),
            "per_hour": cc.curve_stats(per_hour.values,
                                       index=list(per_hour.index)),
            "top_worst": [{"unit": str(u), "month": str(mo),
                           "rmse": round(float(v), 4),
                           "n": int(counts[(u, mo)])}
                          for (u, mo), v in flat.head(top_k).items()],
        }
    return out


def render(stats: dict):
    import matplotlib.pyplot as plt
    cc.setup_font()
    models = list(stats["models"])
    fig, axes = plt.subplots(len(models), 1,
                             figsize=(10, 3.2 * len(models)), squeeze=False)
    for ax, m in zip(axes.ravel(), models):
        um = stats["models"][m]["unit_month_rmse"]
        units = sorted(um)
        months = sorted({mo for u in um for mo in um[u]})
        mat = np.array([[um[u].get(mo, np.nan) for mo in months]
                        for u in units], float)
        im = ax.imshow(mat, cmap="RdYlGn_r", aspect="auto")
        ax.set_xticks(range(len(months)), months, rotation=45, fontsize=7)
        ax.set_yticks(range(len(units)), units, fontsize=8)
        for i in range(len(units)):
            for j in range(len(months)):
                if np.isfinite(mat[i, j]):
                    ax.text(j, i, f"{mat[i, j]:.2f}", ha="center",
                            va="center", fontsize=7)
        ax.set_title(f"error-breakdown: unit x month RMSE — {m}", fontsize=10)
        fig.colorbar(im, ax=ax, shrink=0.8)
    fig.tight_layout()
    return fig


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--pred", required=True)
    ap.add_argument("--out-dir", required=True)
    ap.add_argument("--freq", default="15min")
    ap.add_argument("--top-k", type=int, default=10)
    a = ap.parse_args(argv)
    df = cc.load_predictions(a.pred)
    stats = compute(df, freq=a.freq, top_k=a.top_k)
    cc.save_outputs(render(stats), a.out_dir, RECIPE_ID, stats)


if __name__ == "__main__":
    main()
