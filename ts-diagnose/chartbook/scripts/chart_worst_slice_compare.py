"""worst-slice-compare：焦点模型最差片（默认按月）上的全模型同期对比——
「A 输掉的是一个月还是整个周期」。片指标 = 片内行 RMSE 均值。
内置置换基线：最差片正差距按日块置换检验——未超随机基线不许点名切片。"""
from __future__ import annotations

import argparse
import random

import numpy as np
import pandas as pd

import chart_common as cc

RECIPE_ID = "worst-slice-compare"


def _worst_gap_stat(rr: pd.DataFrame, focal_model: str, others: list) -> float:
    """统计量：焦点自身最差片（片 RMSE argmax）上的正差距（焦点−同片最优他模型）。
    不用 concentration_ratio 做统计量——正差稀疏时任意重排的占比仍近 1（null
    退化无检验力）；坏日被打散后片均值被稀释，gap 幅度才有检验力。"""
    focal = rr[rr["model"] == focal_model]
    basis = focal.groupby("slice")["rmse"].mean()
    worst = basis.idxmax()
    per = rr.groupby(["slice", "model"])["rmse"].mean().unstack()
    gaps = (per[focal_model] - per[others].min(axis=1)).fillna(0.0)
    return float(gaps.clip(lower=0.0)[worst])


def _perm_baseline(rr, focal_model, others, n_perm, seed):
    """→ (perm 块 | None, 跳过原因)。按日块置换，片日数配额保持。"""
    real = _worst_gap_stat(rr, focal_model, others)
    if real <= 0:
        return None, "焦点最差片无正差距（焦点未落后），置换基线不适用"
    if n_perm <= 0:
        return None, "n_perm=0 显式关闭"
    slice_of_date = (rr.drop_duplicates("date")
                     .set_index("date")["slice"].sort_index())
    quota = slice_of_date.value_counts().sort_index()
    dates = list(slice_of_date.index)
    if len(quota) < 2:
        return None, "切片数 < 2，置换无意义"
    if len(dates) < len(quota):
        return None, "日块数少于切片数，置换无意义"
    rng = random.Random(seed)
    null = []
    for _ in range(n_perm):
        shuffled = dates[:]
        rng.shuffle(shuffled)
        mapping, i = {}, 0
        for sl, k in quota.items():
            for d in shuffled[i:i + int(k)]:
                mapping[d] = sl
            i += int(k)
        pr = rr.assign(slice=rr["date"].map(mapping))
        null.append(_worst_gap_stat(pr, focal_model, others))
    p = (1 + sum(1 for c in null if c >= real)) / (n_perm + 1)
    return {"stat": "worst_slice_gap", "n_perm": n_perm, "seed": seed,
            "real_stat": round(real, 4),
            "null_q95": round(float(np.quantile(null, 0.95)), 4),
            "perm_p": round(p, 4),
            "verdict": "significant" if p < 0.05 else "not-significant",
            "note": "按日块置换、片日数配额保持；月内跨日相关未校正——"
                    "significant 是点名的必要条件而非充分证明"}, None


def compute(df: pd.DataFrame, focal_model: str, slice_by: str = "month",
            n_perm: int = 200, perm_seed: int = 0) -> dict:
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
    perm, skip = _perm_baseline(rr, focal_model, others, n_perm, perm_seed)
    note = ("片指标=片内行 RMSE 均值；gap=焦点−同片最优他模型；"
            "concentration_ratio→1 表示差距集中于最差片，→均匀表示普遍性落后。")
    if perm is None:
        note += f"perm 未做：{skip}。"
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
        "perm": perm,
        "note": note}


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
    ap.add_argument("--n-perm", type=int, default=200)
    ap.add_argument("--perm-seed", type=int, default=0)
    a = ap.parse_args(argv)
    stats = compute(cc.load_predictions(a.pred), focal_model=a.focal_model,
                    slice_by=a.slice_by, n_perm=a.n_perm, perm_seed=a.perm_seed)
    cc.save_outputs(render(stats), a.out_dir, RECIPE_ID, stats)


if __name__ == "__main__":
    main()
