#!/usr/bin/env python3
"""Stage 1 参考实现（扰动矩阵；CLI 契约 + gen_gate 被闸对象）。

CLI：--pairs <csv: unit,period,metric_a,metric_b> --out <json>
方向型扰动族：drop_worst_k（按 |b−a| 降序剔 k=max(3,10%)）、subperiod（按 period 列
分段重算）；另附 wilcoxon 配对检验。stability_score 只在方向型族上算
（保持方向的族数 / 方向型族数）——bootstrap 类含随机性的族不进分数。
产物 schema 见 golden/manifest.json 的 expect。
"""
import argparse
import json

import pandas as pd
from scipy.stats import wilcoxon


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--pairs", required=True)
    ap.add_argument("--out", required=True)
    a = ap.parse_args()

    df = pd.read_csv(a.pairs)
    d = df["metric_b"] - df["metric_a"]          # >0 = A 优（metric 为误差）
    base = float(d.mean())
    sign = base > 0

    k = max(3, int(round(0.1 * len(d))))
    kept = df.loc[d.abs().sort_values(ascending=False).index[k:]]
    after = float((kept["metric_b"] - kept["metric_a"]).mean())
    drop = {"k": k, "effect_before": base, "effect_after": after,
            "direction_preserved": (after > 0) == sign}

    per = {str(p): float((g["metric_b"] - g["metric_a"]).mean())
           for p, g in df.groupby("period")}
    sub = {"per_period": per,
           "direction_preserved": all((v > 0) == sign for v in per.values())}

    w = wilcoxon(d)
    fam = {"drop_worst_k": drop, "subperiod": sub,
           "wilcoxon": {"p": float(w.pvalue), "median_diff": float(d.median())}}
    score = sum(fam[f]["direction_preserved"] for f in ("drop_worst_k", "subperiod")) / 2
    out = {"conclusions": {"C1": {"baseline_diff": base, "n_units": int(len(d)),
                                  "families": fam, "stability_score": score}}}
    with open(a.out, "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=1)


if __name__ == "__main__":
    main()
