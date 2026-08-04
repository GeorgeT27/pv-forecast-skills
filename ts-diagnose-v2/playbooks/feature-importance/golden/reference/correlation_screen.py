#!/usr/bin/env python3
"""Stage 0 参考实现（相关筛查；CLI 契约 + gen_gate 被闸对象）。

CLI：--data <csv> --target <目标列名> --leakage <逗号分隔泄漏列，可空> --out <json>
产物：{"n_rows", "dropped_rows", "features": {col: {"spearman_vs_error": v}},
       "leakage_flagged": [...], "ranking_nonleak": [按 |ρ| 降序、排除泄漏列]}
泄漏列只做对照展示（进 features），绝不进 ranking_nonleak。
"""
import argparse
import json

import pandas as pd
from scipy.stats import spearmanr


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--data", required=True)
    ap.add_argument("--target", required=True)
    ap.add_argument("--leakage", default="")
    ap.add_argument("--out", required=True)
    a = ap.parse_args()

    df = pd.read_csv(a.data)
    n0 = len(df)
    df = df.dropna()
    leak = [c for c in a.leakage.split(",") if c]
    feats = [c for c in df.columns if c != a.target]
    rho = {c: float(spearmanr(df[c], df[a.target]).statistic) for c in feats}

    nonleak = [c for c in feats if c not in leak]
    out = {"n_rows": int(len(df)), "dropped_rows": int(n0 - len(df)),
           "features": {c: {"spearman_vs_error": rho[c]} for c in feats},
           "leakage_flagged": leak,
           "ranking_nonleak": sorted(nonleak, key=lambda c: abs(rho[c]), reverse=True)}
    with open(a.out, "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=1)


if __name__ == "__main__":
    main()
