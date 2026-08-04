"""worst-points：|err| top-N 点 + 自动标签（极值/转折点/高波动/普通）。

标签阈值均为该单元自身分布的分位数（pct，默认 0.95）——跨单元量纲不可比，
绝不 pool 阈值。标签可叠加；都不命中记「普通」。
"""
from __future__ import annotations

import argparse

import numpy as np
import pandas as pd

import chart_common as cc

RECIPE_ID = "worst-points"


def _annotate(d: pd.DataFrame, pct: float, vol_window: int) -> pd.DataFrame:
    """按 (unit, window) 序列算 |Δy| 与局部波动，阈值按 unit 分位数。"""
    d = d.sort_values(["unit_id", "window_ts", "horizon_step"]).copy()
    g = d.groupby(["unit_id", "window_ts"], sort=False)["y_true"]
    d["abs_dy"] = g.diff().abs()
    d["local_std"] = (g.rolling(vol_window, center=True, min_periods=2)
                      .std().reset_index(level=[0, 1], drop=True))
    for col, thr_col in (("abs_dy", "ramp_thr"), ("local_std", "vol_thr")):
        d[thr_col] = d.groupby("unit_id")[col].transform(
            lambda s: s.quantile(pct))
    d["y_hi"] = d.groupby("unit_id")["y_true"].transform(
        lambda s: s.quantile(pct))
    d["y_lo"] = d.groupby("unit_id")["y_true"].transform(
        lambda s: s.quantile(1 - pct))
    d["y_quantile"] = d.groupby("unit_id")["y_true"].rank(pct=True)
    return d


def _labels(row) -> list[str]:
    lab = []
    if row.y_true >= row.y_hi or row.y_true <= row.y_lo:
        lab.append("极值")
    if np.isfinite(row.abs_dy) and row.abs_dy >= row.ramp_thr:
        lab.append("转折点")
    if np.isfinite(row.local_std) and row.local_std >= row.vol_thr:
        lab.append("高波动")
    return lab or ["普通"]


def compute(df: pd.DataFrame, top_n: int = 20, freq: str = "15min",
            pct: float = 0.95, vol_window: int = 5) -> dict:
    base = _annotate(df[df["model"] == df["model"].iloc[0]]
                     [["unit_id", "window_ts", "horizon_step", "y_true"]]
                     .drop_duplicates(), pct, vol_window)
    key = ["unit_id", "window_ts", "horizon_step"]
    out = {"recipe": RECIPE_ID,
           "params": {"top_n": top_n, "pct": pct, "vol_window": vol_window},
           "models": {},
           "note": "标签阈值 = 单元自身 y_true/|Δy|/局部σ 的 pct 分位；可叠加。"}
    for m, g in df.groupby("model"):
        gg = g.merge(base[key + ["abs_dy", "local_std", "ramp_thr",
                                 "vol_thr", "y_hi", "y_lo", "y_quantile"]],
                     on=key, how="left")
        top = gg.reindex(gg["err"].abs().sort_values(ascending=False).index) \
                .head(top_n)
        pts, counts = [], {}
        for row in top.itertuples():
            labs = _labels(row)
            for lb in labs:
                counts[lb] = counts.get(lb, 0) + 1
            target = row.window_ts + row.horizon_step * pd.Timedelta(freq)
            pts.append({
                "target_ts": str(target), "window_ts": str(row.window_ts),
                "unit": str(row.unit_id), "step": int(row.horizon_step),
                "y_true": round(float(row.y_true), 4),
                "y_pred": round(float(row.y_pred), 4),
                "err": round(float(row.err), 4), "labels": labs,
                "context": {
                    "abs_dy": (round(float(row.abs_dy), 4)
                               if np.isfinite(row.abs_dy) else None),
                    "local_std": (round(float(row.local_std), 4)
                                  if np.isfinite(row.local_std) else None),
                    "y_quantile": round(float(row.y_quantile), 3)},
            })
        out["models"][str(m)] = {
            "points": pts,
            "label_share": {k: round(v / max(len(pts), 1), 3)
                            for k, v in sorted(counts.items())}}
    return out


def render(stats: dict):
    import matplotlib.pyplot as plt
    cc.setup_font()
    colors = {"极值": "firebrick", "转折点": "darkorange",
              "高波动": "purple", "普通": "gray"}
    models = list(stats["models"])
    fig, axes = plt.subplots(len(models), 1,
                             figsize=(11, 3 * len(models)), squeeze=False)
    for ax, m in zip(axes.ravel(), models):
        for p in stats["models"][m]["points"]:
            c = colors.get(p["labels"][0], "gray")
            ax.scatter(pd.Timestamp(p["target_ts"]), abs(p["err"]),
                       color=c, s=30)
        handles = [plt.Line2D([], [], marker="o", ls="", color=c, label=k)
                   for k, c in colors.items()]
        ax.legend(handles=handles, fontsize=7, ncol=4)
        ax.set_title(f"worst-points |err| top-{len(stats['models'][m]['points'])}"
                     f" — {m}", fontsize=10)
        ax.set_ylabel("|err|")
    fig.autofmt_xdate()
    fig.tight_layout()
    return fig


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--pred", required=True)
    ap.add_argument("--out-dir", required=True)
    ap.add_argument("--top-n", type=int, default=20)
    ap.add_argument("--freq", default="15min")
    ap.add_argument("--pct", type=float, default=0.95)
    ap.add_argument("--vol-window", type=int, default=5)
    a = ap.parse_args(argv)
    stats = compute(cc.load_predictions(a.pred), top_n=a.top_n, freq=a.freq,
                    pct=a.pct, vol_window=a.vol_window)
    cc.save_outputs(render(stats), a.out_dir, RECIPE_ID, stats)


if __name__ == "__main__":
    main()
