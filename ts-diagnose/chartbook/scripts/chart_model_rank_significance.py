"""model-rank-significance:平均秩+Nemenyi 临界差+成对 Diebold-Mariano(HAC)——
模型排名差异是真是噪声。"""
from __future__ import annotations

import argparse
import itertools

import numpy as np
import pandas as pd
from scipy.stats import norm

import chart_common as cc

RECIPE_ID = "model-rank-significance"
# Nemenyi q_alpha (α=0.05), k=2..10
Q_ALPHA = {2: 1.959964, 3: 2.343701, 4: 2.569032, 5: 2.727774,
           6: 2.849705, 7: 2.948319, 8: 3.030879, 9: 3.102173, 10: 3.163684}


def _dm(d: np.ndarray) -> dict:
    """损失差序列(已按时间排序)的 DM 检验;HAC(Bartlett)方差,lag=⌊n^{1/3}⌋。"""
    n = len(d)
    mean = float(np.mean(d))
    if np.allclose(d, d[0]):
        if abs(mean) < 1e-12:
            return {"stat": 0.0, "p": 1.0, "degenerate": True}
        return {"stat": None, "p": 0.0, "degenerate": True}
    dc = d - mean
    L = max(1, int(np.floor(n ** (1 / 3))))
    g0 = float(np.dot(dc, dc)) / n
    var = g0
    for l in range(1, L + 1):
        gl = float(np.dot(dc[:-l], dc[l:])) / n
        var += 2 * (1 - l / (L + 1)) * gl
    var = max(var, 1e-12)
    stat = mean / np.sqrt(var / n)
    p = float(2 * norm.sf(abs(stat)))
    return {"stat": round(float(stat), 4), "p": round(p, 6),
            "degenerate": False}


def compute(df: pd.DataFrame) -> dict:
    models = sorted(df["model"].unique().tolist())
    k = len(models)
    if k < 2:
        raise ValueError("model-rank-significance 需要 ≥2 模型(§5.5)")
    if k > 10:
        raise ValueError("Nemenyi q 表内置至 k=10")
    rr = cc.row_rmse(df)
    mat = rr.pivot_table(index=["unit_id", "window_ts"], columns="model",
                         values="rmse").dropna()
    mat = mat.sort_index(level="window_ts")
    n = len(mat)
    ranks = mat.rank(axis=1, method="average")
    avg = ranks.mean()
    cd = float(Q_ALPHA[k] * np.sqrt(k * (k + 1) / (6.0 * n)))
    dm = {}
    for a, b in itertools.combinations(models, 2):
        dm[f"{a}|{b}"] = _dm((mat[a] - mat[b]).values)
    best = avg.idxmin()
    best_group = sorted([m for m in models if avg[m] - avg[best] <= cd])
    out = {"recipe": RECIPE_ID, "n_rows": n, "cd": round(cd, 4),
           "avg_ranks": {m: round(float(avg[m]), 4) for m in models},
           "dm": dm, "best_group": best_group,
           "note": "损失=行 RMSE(全模型齐的行);cd=Nemenyi α=0.05;"
                   "dm 为成对 HAC 方差 DM 检验,克隆/恒差记 degenerate。"}
    return out


def render(stats: dict):
    import matplotlib.pyplot as plt
    cc.setup_font()
    fig, axes = plt.subplots(2, 1, figsize=(7, 6),
                             gridspec_kw={"height_ratios": [1, 1.2]})
    ax = axes[0]
    items = sorted(stats["avg_ranks"].items(), key=lambda kv: kv[1])
    names = [kv[0] for kv in items]
    vals = [kv[1] for kv in items]
    ax.errorbar(vals, range(len(names)), xerr=stats["cd"] / 2, fmt="o",
                capsize=4)
    ax.set_yticks(range(len(names))), ax.set_yticklabels(
        [n + (" ★" if n in stats["best_group"] else "") for n in names])
    ax.invert_yaxis()
    ax.set_xlabel(f"mean rank (bar=cd/2, cd={stats['cd']})")
    ax.set_title("model-rank-significance")
    ax2 = axes[1]
    pairs = list(stats["dm"])
    ps = [stats["dm"][p]["p"] for p in pairs]
    ax2.barh(range(len(pairs)), ps)
    ax2.axvline(0.05, color="r", ls="--", lw=0.8)
    ax2.set_yticks(range(len(pairs))), ax2.set_yticklabels(pairs, fontsize=8)
    ax2.set_xlabel("DM p-value (dashed=0.05)")
    fig.tight_layout()
    return fig


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--pred", required=True)
    ap.add_argument("--out-dir", required=True)
    a = ap.parse_args(argv)
    stats = compute(cc.load_predictions(a.pred))
    cc.save_outputs(render(stats), a.out_dir, RECIPE_ID, stats)


if __name__ == "__main__":
    main()
