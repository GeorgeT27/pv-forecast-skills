#!/usr/bin/env python3
"""Stage 4 参考实现（外部指标关联；CLI 契约 + gen_gate 被闸对象）。

CLI：--dynamics <json> --external <csv: iteration,unit,rmse> --assignments <csv> --out <json>
产物：{"aligned_keys": int, "missing_keys": [...], "spearman_loss_vs_target": float,
       "target_theta": {member: val}, "target_ranking": [...]}
纪律：本线是佐证——对齐先行（键集合一致性披露），θ_target 用与 loss 侧同款回归设计。
"""
import argparse
import json

import numpy as np
import pandas as pd
from scipy.stats import spearmanr

RIDGE_LAMBDA = 1.0


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dynamics", required=True)
    ap.add_argument("--external", required=True)
    ap.add_argument("--assignments", required=True)
    ap.add_argument("--out", required=True)
    a = ap.parse_args()

    dyn = json.load(open(a.dynamics, encoding="utf-8"))
    ext = pd.read_csv(a.external)
    assign = pd.read_csv(a.assignments)

    loss_of = {(c["iteration"], c["unit"]): c["final_loss"] for c in dyn["curves"]}
    rmse_of = {(int(r.iteration), r.unit): float(r.rmse) for r in ext.itertuples()}
    common = sorted(set(loss_of) & set(rmse_of))
    missing = sorted(set(loss_of) ^ set(rmse_of))
    rho = float(spearmanr([loss_of[k] for k in common],
                          [rmse_of[k] for k in common]).statistic)

    members = sorted(assign["member"].unique())
    memof = assign.groupby(["iteration", "unit"])["member"].apply(list).to_dict()
    posof = assign.groupby(["iteration", "unit"])["position"].first().to_dict()
    n, p = len(common), len(members)
    X, y = np.zeros((n, p + 3)), np.array([rmse_of[k] for k in common])
    occ = {m: sum(m in memof[k] for k in common) / n for m in members}
    for i, k in enumerate(common):
        for j, m in enumerate(members):
            X[i, j] = (1.0 if m in memof[k] else 0.0) - occ[m]
        X[i, p], X[i, p + 1], X[i, p + 2] = k[0], posof[k], 1.0
    pen = np.eye(p + 3) * RIDGE_LAMBDA
    pen[p + 2, p + 2] = 0.0
    beta = np.linalg.solve(X.T @ X + pen, X.T @ y)
    theta = {m: float(beta[j]) for j, m in enumerate(members)}

    out = {"aligned_keys": n, "missing_keys": [list(k) for k in missing],
           "spearman_loss_vs_target": rho, "target_theta": theta,
           "target_ranking": sorted(theta, key=theta.get, reverse=True)}
    with open(a.out, "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=1)


if __name__ == "__main__":
    main()
