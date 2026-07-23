"""local-waterfall:worst-K 行的单行 Shapley 拆账(mask=1 实际输入/=0 参考
输入,参考=f_true 缺则背景)。需 shap(pip install shap==0.44.1)。"""
from __future__ import annotations

import argparse

import numpy as np

import attribution_common as ac
import chart_common as cc

RECIPE_ID = "local-waterfall"

try:
    import shap
except ImportError as e:  # pragma: no cover
    raise ImportError(
        "local-waterfall 需要 shap:pip install shap==0.44.1") from e


def compute(pred_df, feats, adapter, k: int = 20, model=None, seed: int = 0,
            max_calls: int = 5000, background_k: int = 5,
            cache_path=None) -> dict:
    if not adapter.CAPABILITIES.get("perturb_features"):
        raise ValueError("适配器 perturb_features=False,本图不可画(§6)")
    models = sorted(pred_df["model"].unique())
    focal = model or models[0]
    if focal not in models:
        raise ValueError(f"焦点模型 '{focal}' 不在数据中:{models}")
    rr = cc.row_rmse(pred_df[pred_df["model"] == focal])
    worst = rr.sort_values("rmse").tail(k).iloc[::-1]
    fq = feats.copy()
    has_true_by_f = (fq.groupby("feature")["f_true"]
                     .apply(lambda s: s.notna().any()).to_dict())
    need_bg = not all(has_true_by_f.values())
    background, bg_meta = (ac.background_set(feats, k=background_k, seed=seed)
                           if need_bg else ({}, None))
    ba = ac.BudgetedAdapter(adapter, max_calls=max_calls,
                            cache_path=cache_path)
    truth = pred_df[pred_df["model"] == focal].set_index(
        ["unit_id", "window_ts"])
    rows_out, truncated = [], False
    np.random.seed(seed)
    for _, wrow in worst.iterrows():
        unit, wts = wrow["unit_id"], wrow["window_ts"]
        g = feats[(feats["unit_id"] == unit) & (feats["window_ts"] == wts)]
        actual, ref, basis = {}, {}, {}
        for fn, gg in g.groupby("feature"):
            gg = gg.sort_values("horizon_step")
            actual[str(fn)] = gg["f_pred"].tolist()
            if has_true_by_f.get(fn):
                ref[str(fn)] = gg["f_true"].tolist()
                basis[str(fn)] = "f_true"
            else:
                ref[str(fn)] = background[str(fn)]
                basis[str(fn)] = "background"
        names = sorted(actual)
        D = len(names)
        y_true = (truth.loc[(unit, wts)].sort_values("horizon_step")
                  ["y_true"].values)

        def f(masks):
            reqs = []
            for m in masks:
                ov = {fn: (actual[fn] if m[j] >= 0.5 else ref[fn])
                      for j, fn in enumerate(names)}
                reqs.append({"unit_id": unit, "window_ts": wts,
                             "feature_overrides": ov})
            preds = ba.predict(reqs)
            return np.array([[float(np.sqrt(np.mean((p - y_true) ** 2)))]
                             for p in preds])

        nsamples = 2 ** D if D <= 8 else 2 * D + 64
        try:
            ex = shap.KernelExplainer(f, np.zeros((1, D)))
            sv = np.asarray(ex.shap_values(np.ones((1, D)),
                                           nsamples=nsamples,
                                           silent=True)).ravel()
            base_value = float(np.asarray(ex.expected_value).ravel()[0])
        except ac.BudgetExceeded:
            truncated = True
            break
        contrib = {n: round(float(sv[j]), 6) for j, n in enumerate(names)}
        rows_out.append({
            "unit_id": str(unit), "window_ts": str(wts),
            "rmse_actual": round(float(wrow["rmse"]), 6),
            "base_value": round(base_value, 6),
            "contributions": contrib,
            "check_sum": round(base_value + float(sv.sum()), 6),
            "basis": basis})
    if not rows_out:
        raise ValueError("预算不足以拆任何一行——调大 --max-calls")
    return {"recipe": RECIPE_ID, "k": k, "model": str(focal),
            "rows": rows_out, "background_meta": bg_meta,
            "explainer": "kernel", "seed": seed,
            "coverage": {"rows_evaluated": len(rows_out),
                         "calls_used": ba.calls, "truncated": truncated},
            "note": "mask=1 实际输入/=0 参考输入(f_true 缺则背景);"
                    "check_sum=base+Σφ 应≈rmse_actual(效率性自检);"
                    "单行=样本量 1,点名须与全局线交叉。"}


def render(stats: dict):
    import matplotlib.pyplot as plt
    cc.setup_font()
    rows = stats["rows"][:6]
    n = len(rows)
    fig, axes = plt.subplots(1, n, figsize=(4 * n, 3.5), squeeze=False)
    for ax, row in zip(axes[0], rows):
        names = sorted(row["contributions"],
                       key=lambda x: -abs(row["contributions"][x]))
        cum = row["base_value"]
        for i, fn in enumerate(names):
            v = row["contributions"][fn]
            ax.bar(i, v, bottom=cum, color="#c0504d" if v >= 0 else "#4f81bd")
            cum += v
        ax.axhline(row["rmse_actual"], color="k", lw=0.6, ls="--")
        ax.set_xticks(range(len(names)))
        ax.set_xticklabels(names, fontsize=7, rotation=45)
        ax.set_title(f"{row['window_ts'][:10]} rmse={row['rmse_actual']:.2f}",
                     fontsize=8)
    fig.suptitle(f"local-waterfall worst-{stats['k']}({stats['model']})")
    return fig


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--pred", required=True)
    ap.add_argument("--features", required=True)
    ap.add_argument("--adapter", required=True)
    ap.add_argument("--out-dir", required=True)
    ap.add_argument("--k", type=int, default=20)
    ap.add_argument("--model", default=None)
    ap.add_argument("--background-k", type=int, default=5)
    ap.add_argument("--seed", type=int, default=0)
    ap.add_argument("--max-calls", type=int, default=5000)
    a = ap.parse_args(argv)
    from pathlib import Path
    stats = compute(cc.load_predictions(a.pred), cc.load_features(a.features),
                    ac.load_adapter(a.adapter), k=a.k, model=a.model,
                    seed=a.seed, max_calls=a.max_calls,
                    background_k=a.background_k,
                    cache_path=Path(a.out_dir) / "attribution_cache.jsonl")
    cc.save_outputs(render(stats), a.out_dir, RECIPE_ID, stats)


if __name__ == "__main__":
    main()
