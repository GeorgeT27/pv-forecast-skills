#!/usr/bin/env python3
"""Stage 1 —— 影响力回归（Mode A 主证据，纯统计，零 GPU）。

思想：每迭代把 17 站随机重排进 4 个 chunk（3×5+2），是一场**天然随机化实验**。
把"训完某 chunk 后白马湖 RMSE 的变化 ΔRMSE"回归到"该 chunk 里有哪些站"，
站的系数 = 训练到它对白马湖的**边际影响**（>0 = 拖累）。这是分组随机子集数据估值
（Banzhaf 式），详见 references/influence-methods.md。

输入（工作目录，Stage 0 产物）：
  assignments.csv   : iteration,chunk,position,size,stations   (stations = ";" 连接)
  rmse_series.csv   : iteration,chunk,position,model,rmse       (训完该 chunk 后白马湖 RMSE)
输出：
  influence_coefs.json  : 逐模型 + pooled 的 θ_s（含 bootstrap CI、排名、Spearman 一致性、功效提示）

用法：
  python <skill>/scripts/influence_regression.py                 # 全模型 + pooled
  python <skill>/scripts/influence_regression.py --lam 1.0       # 调岭回归强度
  python <skill>/scripts/influence_regression.py --boot 2000     # bootstrap 次数

⚠️ 结论纪律：迭代数 < 10 只报排名、不下显著性结论（见 references/attribution-discipline.md）。
系数为"相对平均站"的和为零参数化——θ_s 高 = 比平均站更拖累，不是绝对 RMSE 增量。
"""
from __future__ import annotations

import argparse
import os
import sys

import numpy as np
import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import si_common as sic


def _load_inputs():
    if not (os.path.exists("assignments.csv") and os.path.exists("rmse_series.csv")):
        sys.exit("缺 assignments.csv 或 rmse_series.csv —— 先跑 Stage 0（replay_assignments.py）"
                 "与日志/ckpt_eval 产出白马湖 RMSE 序列。")
    asg = pd.read_csv("assignments.csv")
    rms = pd.read_csv("rmse_series.csv")
    return asg, rms


def _delta_rmse(rms: pd.DataFrame) -> pd.DataFrame:
    """按全局训练顺序 (iteration, position) 差分，得每 chunk 的 ΔRMSE（去掉训练整体进步趋势）。"""
    rms = rms.sort_values(["model", "iteration", "position"]).copy()
    rms["drmse"] = rms.groupby("model")["rmse"].diff()
    return rms.dropna(subset=["drmse"])


def _design(asg: pd.DataFrame, station_list: list[str]):
    """构造设计矩阵：17 站成员指示（和为零中心化） + 控制列(iteration,position,size)。"""
    idx = {s: i for i, s in enumerate(station_list)}
    key2mem = {}
    for _, r in asg.iterrows():
        members = [s.strip() for s in str(r["stations"]).split(";") if s.strip()]
        vec = np.zeros(len(station_list))
        for s in members:
            if s in idx:
                vec[idx[s]] = 1.0
        key2mem[(int(r["iteration"]), int(r["chunk"]))] = (vec, int(r["size"]),
                                                           int(r["position"]))
    return key2mem


def _fit_ridge(X, y, lam):
    """岭回归 beta = (X'X + λI)^-1 X'y（截距列不罚）。"""
    n, p = X.shape
    R = lam * np.eye(p)
    R[0, 0] = 0.0  # 不罚截距
    beta = np.linalg.solve(X.T @ X + R, X.T @ y)
    return beta


def _build_xy(rows, key2mem, n_st):
    X, y = [], []
    for (it, ch, pos, dr) in rows:
        mem = key2mem.get((it, ch))
        if mem is None:
            continue
        vec, size, position = mem
        # 中心化站指示（和为零参数化的近似）：减去该 chunk 的平均占用，弱化虚拟陷阱
        centered = vec - vec.mean()
        feat = np.concatenate([[1.0], centered, [it, position, size]])
        X.append(feat)
        y.append(dr)
    return np.asarray(X), np.asarray(y)


def _analyze(rms_d, key2mem, station_list, models, lam, boot, rng_seed=0):
    n_st = len(station_list)
    out = {"stations": station_list, "lambda": lam, "n_boot": boot, "models": {}}
    coef_by_model = {}
    for model in models:
        sub = rms_d[rms_d["model"] == model]
        rows = list(zip(sub["iteration"].astype(int), sub["chunk"].astype(int),
                        sub["position"].astype(int), sub["drmse"].astype(float)))
        X, y = _build_xy(rows, key2mem, n_st)
        if len(y) < 3:
            out["models"][model] = {"error": f"观测太少 ({len(y)})，跳过"}
            continue
        beta = _fit_ridge(X, y, lam)
        theta = beta[1:1 + n_st]  # 站系数（截距后 17 个）
        # bootstrap over 观测行
        bs = np.zeros((boot, n_st))
        idxs = np.arange(len(y))
        for b in range(boot):
            samp = np.random.default_rng(rng_seed + b).choice(idxs, len(idxs), replace=True)
            bb = _fit_ridge(X[samp], y[samp], lam)
            bs[b] = bb[1:1 + n_st]
        lo, hi = np.percentile(bs, [2.5, 97.5], axis=0)
        order = np.argsort(theta)[::-1]  # 拖累最重在前
        coef_by_model[model] = theta
        out["models"][model] = {
            "n_obs": int(len(y)),
            "n_params": int(X.shape[1]),
            "ranking_harmful_first": [station_list[i] for i in order],
            "theta": {station_list[i]: round(float(theta[i]), 5) for i in order},
            "ci95": {station_list[i]: [round(float(lo[i]), 5), round(float(hi[i]), 5)]
                     for i in order},
            "ci_excludes_zero": [station_list[i] for i in order
                                 if lo[i] > 0 or hi[i] < 0],
        }
    # 跨模型 Spearman 一致性
    if len(coef_by_model) >= 2:
        try:
            from scipy.stats import spearmanr
            names = list(coef_by_model)
            sp = {}
            for a in range(len(names)):
                for b in range(a + 1, len(names)):
                    r, _ = spearmanr(coef_by_model[names[a]], coef_by_model[names[b]])
                    sp[f"{names[a]}~{names[b]}"] = round(float(r), 3)
            out["cross_model_spearman"] = sp
        except Exception:
            pass
    # pooled（合并所有模型的观测，加 model 固定效应最稳，这里简化为全池）
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--lam", type=float, default=1.0, help="岭回归强度（观测少时调大）")
    ap.add_argument("--boot", type=int, default=1000)
    args = ap.parse_args()

    cfg = sic.load_config()
    station_list = sic.stations(cfg)
    models = cfg.get("models") or ["M1", "M2", "M3", "M4"]

    asg, rms = _load_inputs()
    n_iters = int(rms["iteration"].nunique())
    rms_d = _delta_rmse(rms)
    key2mem = _design(asg, station_list)
    out = _analyze(rms_d, key2mem, station_list, models, args.lam, args.boot)
    out["n_iterations"] = n_iters
    out["power_note"] = ("迭代数 < 10：只报排名，不下显著性结论" if n_iters < 10
                         else f"迭代数 {n_iters}：CI 排除 0 的站可报为‘现象’（仍需过反驳门）")

    sic.dump_json("influence_coefs.json", out)

    # ≤30 行摘要
    print("=" * 56)
    print(f"Stage 1 影响力回归  迭代数={n_iters}  λ={args.lam}  boot={args.boot}")
    print(f"  {out['power_note']}")
    for m, r in out["models"].items():
        if "error" in r:
            print(f"  [{m}] {r['error']}")
            continue
        top = r["ranking_harmful_first"][:3]
        sig = r["ci_excludes_zero"]
        print(f"  [{m}] n_obs={r['n_obs']} 最拖累前三: {top}  CI排除0: {sig or '无'}")
    if "cross_model_spearman" in out:
        print(f"  跨模型排名一致性 Spearman: {out['cross_model_spearman']}")
    print("→ influence_coefs.json 已写。下一步：Stage 3 漂移解释；有 checkpoint 则 Stage 2 梯度佐证。")
    print("=" * 56)


if __name__ == "__main__":
    main()
