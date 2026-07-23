"""baseline-skill:persistence/季节朴素/气候均值三基线的技能阶梯——模型比
"抄"好多少、有没有模型退化成抄 persistence。"""
from __future__ import annotations

import argparse

import numpy as np
import pandas as pd

import chart_common as cc

RECIPE_ID = "baseline-skill"


def _rmse(x):
    return float(np.sqrt(np.mean(np.square(x))))


def compute(df: pd.DataFrame, period_steps=None, freq: str = "15min",
            auto_detect: bool = True) -> dict:
    d = df.copy()
    d["target_ts"] = d["window_ts"] + d["horizon_step"] * pd.Timedelta(freq)
    first = d["model"].iloc[0]
    truth = (d[d["model"] == first]
             .drop_duplicates(["unit_id", "target_ts"])
             .set_index(["unit_id", "target_ts"])["y_true"])
    if period_steps is None and auto_detect:
        u0 = d["unit_id"].iloc[0]
        ser = truth.loc[u0].sort_index().values
        period_steps = cc.detect_period_steps(ser)
    step = pd.Timedelta(freq)
    keys = list(zip(d["unit_id"], d["window_ts"]))
    d["base_persistence"] = [truth.get(k, np.nan) for k in keys]
    if period_steps:
        keys_s = list(zip(d["unit_id"], d["target_ts"] - period_steps * step))
        d["base_seasonal"] = [truth.get(k, np.nan) for k in keys_s]
    clim = float(truth.mean())
    out = {"recipe": RECIPE_ID, "period_steps": period_steps,
           "freq": freq, "baselines": {}, "models": {},
           "note": "skill=1−RMSE_model/RMSE_baseline,基线可算的行上对齐比较;"
                   "copies_persistence: corr(pred,persistence)>corr(pred,truth)。"}
    scored = d.dropna(subset=["base_persistence"])
    out["n_scored"] = int(len(scored) / max(1, d["model"].nunique()))
    rmse_p = _rmse(scored["base_persistence"] - scored["y_true"])
    out["baselines"]["persistence"] = round(rmse_p, 4)
    if period_steps and d["base_seasonal"].notna().any():
        ds = d.dropna(subset=["base_seasonal"])
        rmse_s = _rmse(ds["base_seasonal"] - ds["y_true"])
        out["baselines"]["seasonal_naive"] = round(rmse_s, 4)
    else:
        rmse_s = None
    out["baselines"]["climatology"] = round(_rmse(truth.values - clim), 4)
    for m, g in d.groupby("model"):
        rmse_m = _rmse(g["err"])
        gp = g.dropna(subset=["base_persistence"])
        entry = {"rmse": round(rmse_m, 4)}
        def _skill(base_rmse):
            return round(1 - rmse_m / base_rmse, 4) if base_rmse and base_rmse > 1e-12 else None
        entry["skill_vs_persistence"] = _skill(
            _rmse(gp["base_persistence"] - gp["y_true"]) if len(gp) else None)
        if rmse_s is not None:
            gs = g.dropna(subset=["base_seasonal"])
            entry["skill_vs_seasonal"] = _skill(
                _rmse(gs["base_seasonal"] - gs["y_true"]) if len(gs) else None)
        entry["skill_vs_climatology"] = _skill(out["baselines"]["climatology"])
        ct = float(np.corrcoef(g["y_pred"], g["y_true"])[0, 1])
        cp = float(np.corrcoef(gp["y_pred"], gp["base_persistence"])[0, 1]) \
            if len(gp) > 2 else np.nan
        entry["corr_with_truth"] = round(ct, 4)
        entry["corr_with_persistence"] = round(cp, 4) if np.isfinite(cp) else None
        entry["copies_persistence"] = bool(np.isfinite(cp) and cp > ct)
        out["models"][str(m)] = entry
    return out


def render(stats: dict):
    import matplotlib.pyplot as plt
    cc.setup_font()
    fig, ax = plt.subplots(figsize=(7, 4))
    models = list(stats["models"])
    skills = ["skill_vs_persistence", "skill_vs_seasonal", "skill_vs_climatology"]
    labels = {"skill_vs_persistence": "vs persistence",
              "skill_vs_seasonal": "vs 季节朴素",
              "skill_vs_climatology": "vs 均值"}
    x = np.arange(len(models))
    present = [s for s in skills if any(s in stats["models"][m] for m in models)]
    w = 0.8 / max(1, len(present))
    for i, sk in enumerate(present):
        vals = [stats["models"][m].get(sk) or 0.0 for m in models]
        ax.bar(x + i * w, vals, width=w, label=labels[sk])
    ax.axhline(0, color="k", lw=0.8)
    ax.set_xticks(x + 0.4 - w / 2), ax.set_xticklabels(models, fontsize=8)
    ax.set_ylabel("skill = 1 − RMSE/RMSE_base")
    ax.set_title("baseline-skill 基线技能阶梯")
    ax.legend(fontsize=8)
    return fig


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--pred", required=True)
    ap.add_argument("--out-dir", required=True)
    ap.add_argument("--period-steps", type=int, default=None)
    ap.add_argument("--freq", default="15min")
    a = ap.parse_args(argv)
    stats = compute(cc.load_predictions(a.pred),
                    period_steps=a.period_steps, freq=a.freq)
    cc.save_outputs(render(stats), a.out_dir, RECIPE_ID, stats)


if __name__ == "__main__":
    main()
