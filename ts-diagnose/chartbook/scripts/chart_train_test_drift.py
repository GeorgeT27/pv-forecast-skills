"""train-test-drift：训练期 y 与测试期 y_true 的同日历月分布对比（PSI+分位摘要，
scipy 可用时附 KS p 值）。PSI>psi_alert 的月进告警列表——分布漂移候选。

train_y 长表：ts|unit_id|y；test 侧 y_true 取自 predictions（首模型去重）。
同月对比 = 日历月号（1..12），跨年可比季节位（fig 泛化口径）。
"""
from __future__ import annotations

import argparse

import numpy as np
import pandas as pd

import chart_common as cc

RECIPE_ID = "train-test-drift"
TRAIN_COLS = ("ts", "unit_id", "y")


def load_train_y(path):
    from pathlib import Path
    p = Path(path)
    df = pd.read_parquet(p) if p.suffix == ".parquet" else pd.read_csv(p)
    missing = [c for c in TRAIN_COLS if c not in df.columns]
    if missing:
        raise ValueError(f"train_y 长表缺列 {missing}；需要 {list(TRAIN_COLS)}")
    df = df.copy()
    df["ts"] = pd.to_datetime(df["ts"])
    return df


def psi(a, b, bins: int = 10) -> float:
    """Population Stability Index：分箱边界取 a 的分位（含 ±inf 兜底两侧溢出）。"""
    a, b = np.asarray(a, float), np.asarray(b, float)
    edges = np.unique(np.quantile(a, np.linspace(0, 1, bins + 1)))
    edges[0], edges[-1] = -np.inf, np.inf
    pa, _ = np.histogram(a, bins=edges)
    pb, _ = np.histogram(b, bins=edges)
    fa = np.clip(pa / max(pa.sum(), 1), 1e-4, None)
    fb = np.clip(pb / max(pb.sum(), 1), 1e-4, None)
    return float(np.sum((fa - fb) * np.log(fa / fb)))


def _q(arr, side):
    return {f"n_{side}": int(arr.size),
            f"mean_{side}": round(float(np.mean(arr)), 2),
            f"std_{side}": round(float(np.std(arr)), 2),
            f"p10_{side}": round(float(np.percentile(arr, 10)), 2),
            f"p25_{side}": round(float(np.percentile(arr, 25)), 2),
            f"median_{side}": round(float(np.median(arr)), 2),
            f"p75_{side}": round(float(np.percentile(arr, 75)), 2),
            f"p90_{side}": round(float(np.percentile(arr, 90)), 2)}


def compute(pred_df: pd.DataFrame, train_df: pd.DataFrame,
            psi_alert: float = 0.25) -> dict:
    try:
        from scipy.stats import ks_2samp
    except ImportError:
        ks_2samp = None
    first = pred_df["model"].iloc[0]
    test = pred_df[pred_df["model"] == first][
        ["window_ts", "unit_id", "horizon_step", "y_true"]].drop_duplicates()
    test_month = test["window_ts"].dt.month
    train_month = train_df["ts"].dt.month
    out = {"recipe": RECIPE_ID, "psi_alert": psi_alert, "by_month": {},
           "alert_months": [],
           "note": "同日历月对比（跨年比季节位）；PSI>阈值 → 分布漂移候选，"
                   "所有模型同时受害类机制。"}
    for m in range(1, 13):
        a = train_df.loc[train_month == m, "y"].dropna().to_numpy()
        b = test.loc[test_month == m, "y_true"].dropna().to_numpy()
        if len(a) < 10 or len(b) < 10:
            continue
        p = psi(a, b)
        entry = {"psi": round(p, 4),
                 "ks_p": (float(ks_2samp(a, b).pvalue) if ks_2samp else None),
                 **_q(a, "train"), **_q(b, "test")}
        out["by_month"][str(m)] = entry
        if p > psi_alert:
            out["alert_months"].append(str(m))
    return out


def render(stats: dict):
    import matplotlib.pyplot as plt
    cc.setup_font()
    months = list(stats["by_month"])
    fig, ax = plt.subplots(figsize=(1.1 * max(len(months), 4) + 3, 4))
    vals = [stats["by_month"][m]["psi"] for m in months]
    colors = ["firebrick" if m in stats["alert_months"] else "steelblue"
              for m in months]
    ax.bar(months, vals, color=colors)
    ax.axhline(stats["psi_alert"], color="k", ls="--", lw=0.8,
               label=f"alert={stats['psi_alert']}")
    ax.set_xlabel("日历月"), ax.set_ylabel("PSI")
    ax.set_title("train-test-drift 逐月标签分布漂移"), ax.legend()
    fig.tight_layout()
    return fig


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--pred", required=True)
    ap.add_argument("--train-y", required=True)
    ap.add_argument("--out-dir", required=True)
    ap.add_argument("--psi-alert", type=float, default=0.25)
    a = ap.parse_args(argv)
    stats = compute(cc.load_predictions(a.pred), load_train_y(a.train_y),
                    psi_alert=a.psi_alert)
    cc.save_outputs(render(stats), a.out_dir, RECIPE_ID, stats)


if __name__ == "__main__":
    main()
