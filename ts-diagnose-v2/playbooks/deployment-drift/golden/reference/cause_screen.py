#!/usr/bin/env python3
"""Stage 3 参考实现：候选诱因筛查（菜谱见 playbook.md Stage 3）。

输入是逐窗多点宽表（feature, v0..vK）——逐窗聚合公式**在本脚本内**（逐窗均值），
不是外置适配器：口径进闸，两次执行不会各自发明聚合方式。
点名双关（都命中才 shifted）：① 该特征 split 前后分布偏移显著（Welch 正态近似
p<0.01 且 |shift_z|≥3，基线段与误差侧同样留 buffer）；② 与误差序列全期秩相关
（|Spearman|≥0.3）。另报特征自身 onset（与误差侧同一首离判据）供时点重合判定。
"""
import argparse
import json
import math

import numpy as np
import pandas as pd

ONSET_BUFFER = 10
SUSTAIN = 2
MIN_SEG = 5
STD_FLOOR = 1e-9
P_SHIFT, Z_SHIFT, RHO_MIN = 0.01, 3.0, 0.3


def spearman(a, b):
    ra = pd.Series(a).rank().to_numpy()
    rb = pd.Series(b).rank().to_numpy()
    ra, rb = ra - ra.mean(), rb - rb.mean()
    denom = math.sqrt(float((ra ** 2).sum() * (rb ** 2).sum()))
    return float((ra * rb).sum() / denom) if denom > 0 else 0.0


def welch_p(a, b):
    va = np.var(a, ddof=1) if len(a) > 1 else 0.0
    vb = np.var(b, ddof=1) if len(b) > 1 else 0.0
    z = (np.mean(b) - np.mean(a)) / math.sqrt(max(va / len(a) + vb / len(b), STD_FLOOR))
    return float(z), float(math.erfc(abs(z) / math.sqrt(2)))  # 双侧

def first_departure(vals, split):
    base_end = max(MIN_SEG, split - ONSET_BUFFER)
    base = vals[:base_end]
    mu, sd = float(np.mean(base)), max(float(np.std(base, ddof=1)), STD_FLOOR)
    lo, hi = mu - 3 * sd, mu + 3 * sd
    for d in range(base_end, len(vals) - SUSTAIN + 1):
        if all(vals[d + k] > hi or vals[d + k] < lo for k in range(SUSTAIN)):
            return d
    return None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--features", required=True)
    ap.add_argument("--series", required=True)
    ap.add_argument("--split", type=int, required=True)
    ap.add_argument("--out", required=True)
    args = ap.parse_args()

    err = pd.read_csv(args.series).sort_values("window_idx")["rmse"].to_numpy(dtype=float)
    feat = pd.read_csv(args.features)
    vcols = [c for c in feat.columns if c.startswith("v")]
    feat["value"] = feat[vcols].mean(axis=1)  # 逐窗聚合口径：K 点均值（进闸）

    base_end = max(MIN_SEG, args.split - ONSET_BUFFER)
    results = {}
    for name, g in feat.groupby("feature"):
        vals = g.sort_values("window_idx")["value"].to_numpy(dtype=float)
        base, post = vals[:base_end], vals[args.split:]
        sd = max(float(np.std(base, ddof=1)), STD_FLOOR)
        shift_z = float((np.mean(post) - np.mean(base)) / sd)
        _, p = welch_p(base, post)
        rho = spearman(vals, err)
        onset = first_departure(vals, args.split)
        results[name] = {
            "base_mean": float(np.mean(base)), "post_mean": float(np.mean(post)),
            "shift_z": shift_z, "shift_p": p,
            "spearman_vs_error": rho,
            "onset_index": int(onset) if onset is not None else None,
            "shifted": bool(p < P_SHIFT and abs(shift_z) >= Z_SHIFT
                            and abs(rho) >= RHO_MIN),
        }

    ranking = sorted(results, key=lambda k: (not results[k]["shifted"],
                                             -abs(results[k]["spearman_vs_error"])))
    out = {
        "n": int(len(err)), "split": args.split, "base_end": base_end,
        "aggregate": f"逐窗 {len(vcols)} 点均值",
        "features": results, "ranking": ranking,
        "note": ("shifted=偏移显著+与误差秩相关双关命中；点名≠因果——时点重合"
                 "（onset_index 与误差侧 onset ±7 窗）才够格进升级判定"),
    }
    with open(args.out, "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=2)
    for name in ranking:
        r = results[name]
        print(f"{name}: shifted={r['shifted']} z={r['shift_z']:.1f} "
              f"p={r['shift_p']:.2e} rho={r['spearman_vs_error']:.2f} onset={r['onset_index']}")


if __name__ == "__main__":
    main()
