#!/usr/bin/env python3
"""Stage 2 参考实现（CLI 契约示例 + gen_gate 端到端被闸对象）。

生成的 dynamics 脚本必须满足同一 CLI 与产物最小 schema（golden/manifest.json 所钉）：
  --loss-csv <长表> --out <json>
产物：{"curves": [{series,iteration,unit,final_loss,conv_slope,plateau_epoch,
marginal_gain}], "summary": {<series>: {n_curves, n_plateaued, worst_marginal_gain}}}
（plateaued 定义 = marginal_gain < 0.02；tail_k = 3。）
"""
import argparse
import json

import numpy as np
import pandas as pd

TAIL_K = 3
PLATEAU_MG = 0.02


def curve_metrics(g):
    g = g.sort_values("epoch")
    loss = g["loss"].to_numpy(float)
    ep = g["epoch"].to_numpy(float)
    final = float(loss[-TAIL_K:].mean())
    slope = float(np.polyfit(ep, np.log(loss), 1)[0])
    within = np.nonzero(loss <= final * 1.05)[0]
    plateau = int(ep[within[0]]) if len(within) else int(ep[-1])
    mg = float((loss[-TAIL_K] - loss[-1]) / loss[-TAIL_K])
    return final, slope, plateau, mg


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--loss-csv", required=True)
    ap.add_argument("--out", required=True)
    a = ap.parse_args()

    df = pd.read_csv(a.loss_csv)
    curves, summary = [], {}
    for (s, it, u), g in df.groupby(["series", "iteration", "unit"]):
        final, slope, plateau, mg = curve_metrics(g)
        curves.append({"series": s, "iteration": int(it), "unit": u,
                       "final_loss": final, "conv_slope": slope,
                       "plateau_epoch": plateau, "marginal_gain": mg})
    for s in sorted({c["series"] for c in curves}):
        cs = [c for c in curves if c["series"] == s]
        summary[s] = {"n_curves": len(cs),
                      "n_plateaued": sum(c["marginal_gain"] < PLATEAU_MG for c in cs),
                      "worst_marginal_gain": max(c["marginal_gain"] for c in cs)}
    with open(a.out, "w", encoding="utf-8") as f:
        json.dump({"curves": curves, "summary": summary}, f, ensure_ascii=False, indent=1)


if __name__ == "__main__":
    main()
