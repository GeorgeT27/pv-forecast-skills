"""global-attribution:玩家=特征的 KernelSHAP 全局贡献(mask=0 背景序列/
=1 实际序列)+ 特征×horizon 桶热力图。需 shap(pip install shap==0.44.1)。"""
from __future__ import annotations

import argparse

import numpy as np

import attribution_common as ac
import chart_common as cc

RECIPE_ID = "global-attribution"

try:
    import shap
except ImportError as e:  # pragma: no cover
    raise ImportError(
        "global-attribution 需要 shap:pip install shap==0.44.1") from e


def _bucket_edges(horizon: int, buckets: int):
    edges = np.linspace(0, horizon, buckets + 1).round().astype(int)
    return [(int(a), int(b)) for a, b in zip(edges[:-1], edges[1:]) if b > a]


def _window_series(feats, unit, wts):
    g = feats[(feats["unit_id"] == unit) & (feats["window_ts"] == wts)]
    return {str(fn): gg.sort_values("horizon_step")["f_pred"].tolist()
            for fn, gg in g.groupby("feature")}


def compute(pred_df, feats, adapter, buckets: int = 4, max_windows: int = 30,
            background_k: int = 5, seed: int = 0, max_calls: int = 5000,
            cache_path=None, explainer: str = "auto") -> dict:
    if not adapter.CAPABILITIES.get("perturb_features"):
        raise ValueError("适配器 perturb_features=False,本图不可画(§6)")
    if explainer == "auto":
        explainer = ("gradient" if adapter.CAPABILITIES.get("torch_module")
                     else "kernel")
    if explainer == "gradient":
        if not adapter.CAPABILITIES.get("torch_module") or not callable(getattr(adapter, "get_model", None)):
            raise ValueError(
                "explainer='gradient' 需要适配器 CAPABILITIES['torch_module']=True "
                "且实现 get_model() 函数;此适配器不满足(请用 --explainer kernel)")
        mat, names, bg_meta = ac.gradient_mean_shap(adapter)
        overall = {n: round(float(mat[:, j].mean()), 6)
                   for j, n in enumerate(names)}
        return {"recipe": RECIPE_ID,
                "ranking": sorted(names, key=lambda n: -overall[n]),
                "overall": overall,
                "by_bucket": [{n: round(float(mat[bi, j]), 6)
                               for j, n in enumerate(names)}
                              for bi in range(mat.shape[0])],
                "bucket_defs": [[i, i + 1] for i in range(mat.shape[0])],
                "corr_groups": ac.feature_corr_groups(feats),
                "background_meta": bg_meta, "explainer": "gradient",
                "seed": seed, "nsamples": None,
                "coverage": {"windows_evaluated": bg_meta["n_explain"],
                             "calls_used": 0, "truncated": False},
                "note": "白盒期望梯度路:输出维=get_model 的桶;"
                        "corr_groups 组内贡献须合并判读(守卫二)。"}
    background, bg_meta = ac.background_set(feats, k=background_k, seed=seed)
    names = sorted(background)
    D = len(names)
    horizon = len(background[names[0]])
    bks = _bucket_edges(horizon, buckets)
    fw = (feats.groupby(["unit_id", "window_ts"]).size().index)
    pw = set(zip((str(u) for u in pred_df["unit_id"]),
                 (str(w) for w in pred_df["window_ts"])))
    cand = [(u, w) for (u, w) in fw if (str(u), str(w)) in pw]
    rng = np.random.RandomState(seed)
    if len(cand) > max_windows:
        cand = [cand[i] for i in sorted(
            rng.choice(len(cand), max_windows, replace=False))]
    ba = ac.BudgetedAdapter(adapter, max_calls=max_calls,
                            cache_path=cache_path)
    nsamples = 2 ** D if D <= 8 else 2 * D + 64
    # 双重播种非冗余:rng 喂本脚本自己的采样;shap KernelExplainer 内部走全局
    # np.random——两者都不种任一侧就不可复现(Plan3 T3 评审备注)。
    np.random.seed(seed)
    acc = np.zeros((len(bks), D))
    done, truncated = 0, False
    for unit, wts in cand:
        actual = _window_series(feats, unit, wts)

        def f(masks):
            reqs = []
            for m in masks:
                ov = {fn: (actual[fn] if m[j] >= 0.5 else background[fn])
                      for j, fn in enumerate(names)}
                reqs.append({"unit_id": unit, "window_ts": wts,
                             "feature_overrides": ov})
            preds = ba.predict(reqs)
            return np.array([[float(np.mean(p[a:b])) for (a, b) in bks]
                             for p in preds])

        try:
            ex = shap.KernelExplainer(f, np.zeros((1, D)))
            sv = ex.shap_values(np.ones((1, D)), nsamples=nsamples,
                                silent=True)
        except ac.BudgetExceeded:
            truncated = True
            break
        acc += np.abs(np.array([np.asarray(s).ravel() for s in sv]))
        done += 1
    if done == 0:
        raise ValueError("预算不足以评估任何一个窗口——调大 --max-calls")
    acc /= done
    overall = {n: round(float(acc[:, j].mean()), 6)
               for j, n in enumerate(names)}
    return {"recipe": RECIPE_ID,
            "ranking": sorted(names, key=lambda n: -overall[n]),
            "overall": overall,
            "by_bucket": [{n: round(float(acc[bi, j]), 6)
                           for j, n in enumerate(names)}
                          for bi in range(len(bks))],
            "bucket_defs": [list(b) for b in bks],
            "corr_groups": ac.feature_corr_groups(feats),
            "background_meta": bg_meta, "explainer": "kernel",
            "seed": seed, "nsamples": nsamples,
            "coverage": {"windows_evaluated": done,
                         "calls_used": ba.calls, "truncated": truncated},
            "note": "mask=0 背景序列/=1 实际序列;D≤8 全枚举精确;"
                    "corr_groups 组内贡献须合并判读(守卫二)。"}


def render(stats: dict):
    import matplotlib.pyplot as plt
    cc.setup_font()
    names = stats["ranking"]
    fig, axes = plt.subplots(1, 2, figsize=(11, 4))
    axes[0].barh(range(len(names)),
                 [stats["overall"][n] for n in names])
    axes[0].set_yticks(range(len(names)))
    axes[0].set_yticklabels(names, fontsize=8)
    axes[0].invert_yaxis()
    axes[0].set_xlabel("mean|SHAP|")
    axes[0].set_title("global contribution ranking")
    mat = np.array([[row[n] for n in names] for row in stats["by_bucket"]])
    im = axes[1].imshow(mat.T, aspect="auto", cmap="viridis")
    axes[1].set_yticks(range(len(names)))
    axes[1].set_yticklabels(names, fontsize=8)
    axes[1].set_xticks(range(len(stats["bucket_defs"])))
    axes[1].set_xticklabels([f"{a}-{b}" for a, b in stats["bucket_defs"]],
                            fontsize=8)
    axes[1].set_xlabel("horizon bucket")
    axes[1].set_title("feature x horizon contribution")
    fig.colorbar(im, ax=axes[1], shrink=0.8)
    fig.suptitle(f"global-attribution ({stats['explainer']})")
    return fig


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--pred", required=True)
    ap.add_argument("--features", required=True)
    ap.add_argument("--adapter", required=True)
    ap.add_argument("--out-dir", required=True)
    ap.add_argument("--buckets", type=int, default=4)
    ap.add_argument("--max-windows", type=int, default=30)
    ap.add_argument("--background-k", type=int, default=5)
    ap.add_argument("--seed", type=int, default=0)
    ap.add_argument("--max-calls", type=int, default=5000)
    ap.add_argument("--explainer", default="auto",
                    choices=["auto", "kernel", "gradient"])
    a = ap.parse_args(argv)
    from pathlib import Path
    stats = compute(cc.load_predictions(a.pred), cc.load_features(a.features),
                    ac.load_adapter(a.adapter), buckets=a.buckets,
                    max_windows=a.max_windows, background_k=a.background_k,
                    seed=a.seed, max_calls=a.max_calls,
                    cache_path=Path(a.out_dir) / "attribution_cache.jsonl",
                    explainer=a.explainer)
    cc.save_outputs(render(stats), a.out_dir, RECIPE_ID, stats)


if __name__ == "__main__":
    main()
