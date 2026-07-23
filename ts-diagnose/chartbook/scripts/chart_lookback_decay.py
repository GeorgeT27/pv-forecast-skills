"""lookback-decay:按桶遮蔽历史窗,Δ=遮蔽后预测相对未遮蔽的 RMSE——
模型依赖多长的历史。Δ 与真值无关(纯依赖度量)。"""
from __future__ import annotations

import argparse

import numpy as np
import pandas as pd

import attribution_common as ac
import chart_common as cc

RECIPE_ID = "lookback-decay"


def _buckets(L: int, period_steps=None):
    """近→远:[L-1,L) 最近一步、近四分位、至主周期(缺省半窗)、更远。"""
    cuts = {L, L - 1, L - 1 - max(1, L // 4),
            L - period_steps if period_steps else L // 2, 0}
    edges = sorted((c for c in cuts if 0 <= c <= L), reverse=True)
    return [(b, a) for a, b in zip(edges[:-1], edges[1:]) if a > b]


def _delta(base, masked):
    return float(np.sqrt(np.mean(
        (np.concatenate(masked) - np.concatenate(base)) ** 2)))


def compute(pred_df, adapter, period_steps=None, max_windows: int = 30,
            seed: int = 0, max_calls: int = 5000, per_instance: bool = False,
            cache_path=None) -> dict:
    caps = adapter.CAPABILITIES
    if not caps.get("perturb_lookback"):
        raise ValueError("适配器 perturb_lookback=False,本图不可画(§6)")
    L = int(caps["lookback_steps"])
    bks = _buckets(L, period_steps)
    wins = (pred_df[["unit_id", "window_ts"]].drop_duplicates()
            .itertuples(index=False))
    cand = [(str(u), w) for u, w in wins]
    rng = np.random.RandomState(seed)
    if len(cand) > max_windows:
        cand = [cand[i] for i in sorted(
            rng.choice(len(cand), max_windows, replace=False))]
    ba = ac.BudgetedAdapter(adapter, max_calls=max_calls,
                            cache_path=cache_path)
    out = {"recipe": RECIPE_ID, "lookback_steps": L,
           "bucket_defs": [list(b) for b in bks], "seed": seed,
           "note": "Δ=遮蔽该桶后预测相对未遮蔽预测的 RMSE(纯依赖度量);"
                   "weights=Δ⁺ 归一;短记忆是 Transformer 系文献常态,"
                   "平坦≠模型差。"}
    truncated = False
    try:
        base = ba.predict([{"unit_id": u, "window_ts": w} for u, w in cand])
        deltas = []
        for a, b in bks:
            masked = ba.predict([{"unit_id": u, "window_ts": w,
                                  "lookback_mask": [[a, b]]}
                                 for u, w in cand])
            deltas.append(round(_delta(base, masked), 6))
        out["delta_by_bucket"] = deltas
        tot = sum(d for d in deltas if d > 0)
        out["weights"] = ([round(max(d, 0.0) / tot, 4) for d in deltas]
                          if tot > 1e-12 else None)
        cutoff = L - (period_steps if period_steps else max(1, L // 4))
        out["short_term_share"] = (
            round(sum(w for (a, _b), w in zip(bks, out["weights"])
                      if a >= cutoff), 4) if out["weights"] else None)
        if per_instance:
            hs = []
            for i, (u, w) in enumerate(cand):
                ref = float(np.sqrt(np.mean(
                    (ba.predict([{"unit_id": u, "window_ts": w,
                                  "lookback_mask": [[0, L]]}])[0]
                     - base[i]) ** 2)))
                if ref < 1e-12:
                    hs.append(0)
                    continue
                h_star = L
                for h in range(1, L + 1):
                    d = float(np.sqrt(np.mean(
                        (ba.predict([{"unit_id": u, "window_ts": w,
                                      "lookback_mask": [[0, L - h]]}])[0]
                         - base[i]) ** 2)))
                    if d <= 0.05 * ref:
                        h_star = h
                        break
                hs.append(h_star)
            vals, counts = np.unique(hs, return_counts=True)
            out["per_instance"] = {
                "hist": {str(int(v)): int(c) for v, c in zip(vals, counts)},
                "median": int(np.median(hs))}
    except ac.BudgetExceeded:
        truncated = True
    out["coverage"] = {"windows_evaluated": len(cand),
                       "calls_used": ba.calls, "truncated": truncated}
    if truncated and "delta_by_bucket" not in out:
        raise ValueError("预算不足以完成任何桶——调大 --max-calls")
    return out


def render(stats: dict):
    import matplotlib.pyplot as plt
    cc.setup_font()
    fig, ax = plt.subplots(figsize=(7, 4))
    labels = [f"[{a},{b})" for a, b in stats["bucket_defs"]]
    ax.bar(range(len(labels)), stats["delta_by_bucket"])
    ax.set_xticks(range(len(labels)))
    ax.set_xticklabels(labels, fontsize=8)
    ax.set_xlabel("遮蔽的历史步区间(左=近)")
    ax.set_ylabel("Δ RMSE(相对未遮蔽)")
    st = stats.get("short_term_share")
    ax.set_title(f"lookback-decay 历史依赖(short_term_share={st})")
    return fig


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--pred", required=True)
    ap.add_argument("--adapter", required=True)
    ap.add_argument("--out-dir", required=True)
    ap.add_argument("--period-steps", type=int, default=None)
    ap.add_argument("--max-windows", type=int, default=30)
    ap.add_argument("--seed", type=int, default=0)
    ap.add_argument("--max-calls", type=int, default=5000)
    ap.add_argument("--per-instance", action="store_true")
    a = ap.parse_args(argv)
    from pathlib import Path
    stats = compute(cc.load_predictions(a.pred), ac.load_adapter(a.adapter),
                    period_steps=a.period_steps, max_windows=a.max_windows,
                    seed=a.seed, max_calls=a.max_calls,
                    per_instance=a.per_instance,
                    cache_path=Path(a.out_dir) / "attribution_cache.jsonl")
    cc.save_outputs(render(stats), a.out_dir, RECIPE_ID, stats)


if __name__ == "__main__":
    main()
