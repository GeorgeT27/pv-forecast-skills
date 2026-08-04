#!/usr/bin/env python3
"""Stage 3 参考实现（成分回归；CLI 契约 + gen_gate 被闸对象）。

CLI：--dynamics <json> --assignments <csv> --out <json>
方法（承 playbook §2 Stage 3）：因变量 = final_loss；自变量 = 中心化成员指示
（减该成员的平均占用）+ 控制变量 iteration/position；岭回归（截距不罚，λ=1）；
θ 读作相对平均成员的相对效应，只比排名。
产物：{"series": {<s>: {"theta": {member: val}, "ranking": [降序成员], "power_note": str}}}
"""
import argparse
import json

import numpy as np
import pandas as pd

RIDGE_LAMBDA = 1.0


def fit_series(dyn_curves, assign):
    rows, members = [], sorted(assign["member"].unique())
    memof = assign.groupby(["iteration", "unit"])["member"].apply(list).to_dict()
    posof = assign.groupby(["iteration", "unit"])["position"].first().to_dict()
    for c in dyn_curves:
        key = (c["iteration"], c["unit"])
        rows.append({"y": c["final_loss"], "iteration": c["iteration"],
                     "position": posof[key], "members": memof[key]})
    n, p = len(rows), len(members)
    X = np.zeros((n, p + 3))
    y = np.array([r["y"] for r in rows])
    occupancy = {m: sum(m in r["members"] for r in rows) / n for m in members}
    for i, r in enumerate(rows):
        for j, m in enumerate(members):
            X[i, j] = (1.0 if m in r["members"] else 0.0) - occupancy[m]
        X[i, p] = r["iteration"]
        X[i, p + 1] = r["position"]
        X[i, p + 2] = 1.0  # 截距
    pen = np.eye(p + 3) * RIDGE_LAMBDA
    pen[p + 2, p + 2] = 0.0  # 截距不罚
    beta = np.linalg.solve(X.T @ X + pen, X.T @ y)
    theta = {m: float(beta[j]) for j, m in enumerate(members)}
    note = f"观测 {n} 行 / 参数 {p + 3}；" + ("迭代数充足" if n >= 10 else "轮数<10：只报排名不报显著性")
    return theta, note


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dynamics", required=True)
    ap.add_argument("--assignments", required=True)
    ap.add_argument("--out", required=True)
    a = ap.parse_args()

    dyn = json.load(open(a.dynamics, encoding="utf-8"))
    assign = pd.read_csv(a.assignments)
    out = {"series": {}}
    for s in sorted({c["series"] for c in dyn["curves"]}):
        theta, note = fit_series([c for c in dyn["curves"] if c["series"] == s], assign)
        ranking = sorted(theta, key=theta.get, reverse=True)
        out["series"][s] = {"theta": theta, "ranking": ranking, "power_note": note}
    with open(a.out, "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=1)


if __name__ == "__main__":
    main()
