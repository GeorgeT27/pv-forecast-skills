"""revision-stability:以目标时刻为锚,历次发起窗对它的预测轨迹——收敛、
跳变还是塌缩。"""
from __future__ import annotations

import argparse

import numpy as np
import pandas as pd

import chart_common as cc

RECIPE_ID = "revision-stability"
MAX_SAMPLES = 6


def compute(df: pd.DataFrame, freq: str = "15min") -> dict:
    d = df.copy()
    d["target_ts"] = d["window_ts"] + d["horizon_step"] * pd.Timedelta(freq)
    out = {"recipe": RECIPE_ID, "freq": freq, "models": {},
           "note": "lead=horizon_step;轨迹按 lead 降序;smapc=逐对翻新"
                   "2|Δ|/(|p1|+|p2|) 均值;convergence_ratio=最短/最长 lead "
                   "的 |err| 均值比。"}
    any_covered = False
    for m, g in d.groupby("model"):
        cov = g.groupby(["unit_id", "target_ts"]).size()
        covered = cov[cov >= 2]
        entry = {"n_targets": int(len(covered)),
                 "coverage_hist": {str(int(k)): int(v) for k, v in
                                   cov.value_counts().sort_index().items()}}
        if len(covered) == 0:
            out["models"][str(m)] = entry
            continue
        any_covered = True
        smapc_vals, first_err, last_err, samples = [], [], [], []
        gg = g.set_index(["unit_id", "target_ts"]).sort_index()
        for key in covered.index:
            traj = gg.loc[key].sort_values("horizon_step", ascending=False)
            preds = traj["y_pred"].values
            for p1, p2 in zip(preds[:-1], preds[1:]):
                den = abs(p1) + abs(p2)
                if den > 1e-12:
                    smapc_vals.append(2 * abs(p2 - p1) / den)
            errs = (traj["y_pred"] - traj["y_true"]).abs().values
            first_err.append(errs[0])   # 最长 lead
            last_err.append(errs[-1])   # 最短 lead
            if len(samples) < MAX_SAMPLES:
                samples.append({
                    "unit_id": str(key[0]), "target_ts": str(key[1]),
                    "leads": [int(v) for v in traj["horizon_step"]],
                    "preds": [round(float(v), 4) for v in preds],
                    "y_true": round(float(traj["y_true"].iloc[0]), 4)})
        fe, le = float(np.mean(first_err)), float(np.mean(last_err))
        entry.update({
            "smapc": round(float(np.mean(smapc_vals)), 6) if smapc_vals else None,
            "convergence_ratio": round(le / fe, 4) if fe > 1e-12 else None,
            "sample_trajectories": samples})
        out["models"][str(m)] = entry
    if not any_covered:
        raise ValueError(
            "无任何目标时刻被 ≥2 个发起窗覆盖——数据不含翻新结构,本图结构性"
            "不适用(需要重叠预测窗)")
    return out


def render(stats: dict):
    import matplotlib.pyplot as plt
    cc.setup_font()
    n = len(stats["models"])
    fig, axes = plt.subplots(1, n, figsize=(6 * n, 4), squeeze=False)
    for ax, (m, s) in zip(axes[0], stats["models"].items()):
        for tr in s.get("sample_trajectories", []):
            ax.plot(tr["leads"], tr["preds"], marker="o", ms=3, lw=1, alpha=0.7)
            ax.axhline(tr["y_true"], color="k", lw=0.4, ls=":")
        ax.invert_xaxis()
        ax.set_xlabel("lead(步,右=临近)"), ax.set_ylabel("预测值")
        sm = s.get("smapc")
        ax.set_title(f"{m} 翻新轨迹 (sMAPC={sm if sm is not None else 'n/a'})")
    return fig


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--pred", required=True)
    ap.add_argument("--out-dir", required=True)
    ap.add_argument("--freq", default="15min")
    a = ap.parse_args(argv)
    stats = compute(cc.load_predictions(a.pred), freq=a.freq)
    cc.save_outputs(render(stats), a.out_dir, RECIPE_ID, stats)


if __name__ == "__main__":
    main()
