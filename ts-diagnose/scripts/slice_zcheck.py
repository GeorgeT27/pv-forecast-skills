#!/usr/bin/env python3
"""切片配对 z 检验：跨种子成对差值的 z 统计，判定切片级差异是否超噪声底。

输入：长表 CSV，每行 = 一个 (slice, seed) 观测，含两模型在该 (slice, seed) 上的口径指标值
（同一 seed 同一 slice 下两模型才可配对相减，其余变量——数据/训练步数/超参——须固定）。
z = mean(diff) / (std(diff, ddof=1) / sqrt(n))；|z| > 阈值（默认 3）记 `real`（真实差异），
否则 `~noise`。见 docs/自进化计划/阶段1-architecture-attribution-playbook.md §3.1。"""
from __future__ import annotations

import argparse
import csv
import json
import math
from collections import defaultdict


def paired_z(diffs):
    """→ (mean_diff, z)。diffs：同一切片跨种子的配对差值列表（model_b − model_a）。
    n<2 时统计量不可算，z 记 0.0——呼叫方靠返回结果里的 n_seeds 字段判样本量是否够，
    不要把 z=0.0 误读成"确认无差异"。"""
    n = len(diffs)
    if n < 2:
        return (diffs[0] if diffs else 0.0), 0.0
    mean = sum(diffs) / n
    var = sum((d - mean) ** 2 for d in diffs) / (n - 1)
    std = math.sqrt(var)
    if std == 0:
        return mean, (math.inf if mean > 0 else (-math.inf if mean < 0 else 0.0))
    return mean, mean / (std / math.sqrt(n))


def slice_zcheck(rows, z_threshold=3.0):
    """rows：[{"slice":str,"seed":str,"model_a":float,"model_b":float}, ...]
    （同一 seed 下两模型在同一切片上的口径指标值，越小越好）。
    → {slice: {"n_seeds":int,"mean_diff":float,"z":float,"verdict":"real"|"~noise"}}
    mean_diff = model_b − model_a：>0 表示 A 在该切片更优（误差更小）。"""
    by_slice = defaultdict(list)
    for r in rows:
        by_slice[r["slice"]].append(float(r["model_b"]) - float(r["model_a"]))
    out = {}
    for sl, diffs in sorted(by_slice.items()):
        mean, z = paired_z(diffs)
        out[sl] = {"n_seeds": len(diffs), "mean_diff": mean, "z": z,
                    "verdict": "real" if abs(z) > z_threshold else "~noise"}
    return out


def main():
    ap = argparse.ArgumentParser(description="切片配对 z 检验（跨种子）")
    ap.add_argument("--metrics", required=True,
                     help="CSV 长表，列：slice,seed,model_a,model_b")
    ap.add_argument("--z-threshold", type=float, default=3.0, dest="z_threshold",
                     help="判真实差异的 z 阈值（默认 3）")
    ap.add_argument("--out", required=True)
    args = ap.parse_args()

    with open(args.metrics, newline="", encoding="utf-8") as f:
        rows = list(csv.DictReader(f))
    result = slice_zcheck(rows, z_threshold=args.z_threshold)
    n_real = sum(1 for v in result.values() if v["verdict"] == "real")
    summary = {
        "z_threshold": args.z_threshold,
        "n_slices": len(result),
        "n_real": n_real,
        "n_noise": len(result) - n_real,
        "slices": result,
    }
    with open(args.out, "w", encoding="utf-8") as f:
        json.dump(summary, f, ensure_ascii=False, indent=2)
    print(f"✓ {len(result)} 个切片，{n_real} 个超噪声底（|z|>{args.z_threshold}，记 real），"
          f"{len(result) - n_real} 个 ~noise → {args.out}")


if __name__ == "__main__":
    main()
