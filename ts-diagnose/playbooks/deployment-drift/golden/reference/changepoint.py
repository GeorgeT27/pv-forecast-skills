#!/usr/bin/env python3
"""Stage 1 参考实现：退化判定与时点定位（菜谱见 playbook.md Stage 1）。

三件事，缺一不可：
  1. 最大分离切分点（Welch z 最大的两段切分）+ 置换基线（argmax 型统计量必须过随机基线）；
  2. onset 首离判据（切分点估计的是效应最大化点，渐变时系统性晚于起始点——
     baseline 带 = 切分点前留 buffer 的纯净前段 μ±3σ，onset = 首次连续 2 窗越带）；
  3. 形态判定 gradual/abrupt（split − onset ≥ 3 窗 = 渐变）与奇偶交错正交重切一致性。
"""
import argparse
import json
import math

import numpy as np
import pandas as pd

MIN_SEG = 5          # 切分扫描两侧最短段
ONSET_BUFFER = 10    # onset 基线段 = [0, split-buffer)，防 ramp 污染基线带
SUSTAIN = 2          # 越带需连续窗数（防单窗尖峰）
GRADUAL_GAP = 3      # split − onset ≥ 该值 → gradual
STD_FLOOR = 1e-9


def welch_z(a, b):
    va = np.var(a, ddof=1) if len(a) > 1 else 0.0
    vb = np.var(b, ddof=1) if len(b) > 1 else 0.0
    denom = math.sqrt(max(va / len(a) + vb / len(b), STD_FLOOR))
    return (np.mean(b) - np.mean(a)) / denom


def best_split(x):
    zs = {s: welch_z(x[:s], x[s:]) for s in range(MIN_SEG, len(x) - MIN_SEG + 1)}
    s = max(zs, key=lambda k: abs(zs[k]))
    return s, zs[s]


def first_departure(x, split):
    base_end = max(MIN_SEG, split - ONSET_BUFFER)
    base = x[:base_end]
    mu, sd = float(np.mean(base)), max(float(np.std(base, ddof=1)), STD_FLOOR)
    band = mu + 3 * sd
    for d in range(base_end, len(x) - SUSTAIN + 1):
        if all(x[d + k] > band for k in range(SUSTAIN)):
            return d, mu, sd, band
    return None, mu, sd, band


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--series", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--seed", type=int, default=0)
    ap.add_argument("--n-perm", type=int, default=200)
    args = ap.parse_args()

    df = pd.read_csv(args.series)
    x = df["rmse"].to_numpy(dtype=float)
    ts = df["window_ts"].astype(str).tolist()
    n = len(x)

    split, gap_z = best_split(x)
    onset, base_mu, base_sd, band = first_departure(x, split)
    shape = "unknown"
    if onset is not None:
        shape = "gradual" if split - onset >= GRADUAL_GAP else "abrupt"

    pre, post = x[:split], x[split:]

    # 奇偶交错正交重切：两半独立看 pre/post 差值方向是否一致
    even, odd = np.arange(n) % 2 == 0, np.arange(n) % 2 == 1
    gap_even = float(np.mean(x[(np.arange(n) >= split) & even])
                     - np.mean(x[(np.arange(n) < split) & even]))
    gap_odd = float(np.mean(x[(np.arange(n) >= split) & odd])
                    - np.mean(x[(np.arange(n) < split) & odd]))
    interleave_consistent = (gap_even > 0) == (gap_odd > 0)

    # 稳健性：剔后段最缓和 3 窗，方向不变才算稳
    if len(post) > 4:
        trimmed = np.sort(post)[3:]
        direction_preserved = (np.mean(trimmed) - np.mean(pre)) * gap_z > 0
    else:
        direction_preserved = False

    # 置换基线：全序打乱下 max|Welch z| 的 null 分布（固定种子，CLI 显式传入）
    rng = np.random.default_rng(args.seed)
    null_stats = []
    for _ in range(args.n_perm):
        xp = rng.permutation(x)
        _, z = best_split(xp)
        null_stats.append(abs(z))
    null_stats = np.array(null_stats)
    real_stat = abs(gap_z)
    p = float((1 + np.sum(null_stats >= real_stat)) / (args.n_perm + 1))
    verdict = "significant" if p <= 0.05 else "not-significant"

    out = {
        "n": n,
        "split_index": int(split),
        "split_ts": ts[split],
        "onset_index": int(onset) if onset is not None else None,
        "onset_ts": ts[onset] if onset is not None else None,
        "shape": shape,
        "pre": {"n": int(len(pre)), "mean": float(np.mean(pre)),
                "std": float(np.std(pre, ddof=1))},
        "post": {"n": int(len(post)), "mean": float(np.mean(post)),
                 "std": float(np.std(post, ddof=1))},
        "gap_z": float(gap_z),
        "onset_rule": {"baseline_mean": base_mu, "baseline_std": base_sd,
                       "band": band, "sustain": SUSTAIN, "buffer": ONSET_BUFFER},
        "interleave": {"gap_even": gap_even, "gap_odd": gap_odd,
                       "consistent": bool(interleave_consistent)},
        "stability": {"direction_preserved": bool(direction_preserved),
                      "trim_n": 3},
        "perm": {"seed": args.seed, "n_perm": args.n_perm,
                 "real_stat": float(real_stat),
                 "null_q95": float(np.quantile(null_stats, 0.95)),
                 "p": p, "verdict": verdict},
        "note": ("split_index=效应最大化点；shape=gradual 时真实起始≤onset_index"
                 "（首次连续越带），时间结论必须双点齐报，只报 split 属渐变-突变混淆"),
    }
    with open(args.out, "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=2)
    print(f"split={split}({ts[split]}) onset={onset} shape={shape} "
          f"gap_z={gap_z:.2f} perm_p={p:.4f}")


if __name__ == "__main__":
    main()
