#!/usr/bin/env python3
"""Stage 1.5：ε_sys/ε_res 分解——稳健加性回归剥系统偏差，只留波动给 Stage 2 点名。

方法（spec: docs/superpowers/specs/2026-07-17-pv-feature-blame-epsilon-decomp-design.md）：
  ε_f = pred − label（逐点；仅 feature_pairs.json 配对特征——未配对的真实值列无 ε）
  ε_sys_f ≈ Huber 岭 [1 | 谐波(钟点≤3阶) | 谐波(DoY≤2阶) | hinge(提前期) | hinge(X_pred_g) ∀g]
    ——不分箱：无稀疏格子、无人为边界、无 weather_class 标签依赖（天气型由各特征
    pred 值的样条隐式承载）；加性主效应成本随特征数线性。
  跨期稳定性：前段拟合 → 后段验证 λ = clip(⟨ε_b,ŝ_b⟩/⟨ŝ_b,ŝ_b⟩, 0, 1)；
    后段空/拟合失败 → λ=0（保守：宁少剥不过剥）。ε_res = ε − λ·ŝ。
  可约性 = 逐行 lag-1 自相关中位数²（Stage 2 闸用：< min 不点名，白噪声硬追是废话）。
  波动保全：回归只减条件均值不碰条件方差——res_var_front/back 落盘供检查。

用法（工作目录下，Stage 0 产物就位后）：
  python3 <SKILL>/scripts/feature_decompose.py \
      [--feature-true F.parquet] [--pairs feature_pairs.json] \
      [--embargo 48h] [--alpha 1e-3] [--fit-cap 400000] [--out feature_decomp.json]

产物：eps_res_<feature>.npy（n_rows×192，行序 = feature_true 行序）+ feature_decomp.json
"""
from __future__ import annotations

import argparse
import os
import sys

import numpy as np
import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import fb_common as fb  # noqa: E402


def build_design(ts_rows, pred_mats: dict, orders_hod: int, orders_doy: int,
                 n_knots: int) -> np.ndarray:
    """全部特征共用的设计矩阵 (n_rows·H, p)：截距 + 钟点/DoY 谐波 + 提前期 hinge
    + 每个配对特征的 pred 值 hinge（列序 = sorted(特征名)，确定性）。"""
    d = fb.require_du()
    H = d.HORIZON
    ts = pd.DatetimeIndex(ts_rows)
    k = np.arange(H)
    t_ns = ts.asi8[:, None] + (k * d.FREQ.value)[None, :]
    tt = pd.DatetimeIndex(t_ns.ravel())
    hod = tt.hour + tt.minute / 60.0
    doy = tt.dayofyear + hod / 24.0
    lead = np.tile(k.astype(float), len(ts))
    blocks = [np.ones((len(tt), 1)),
              fb.harmonic_basis(hod, 24.0, orders_hod),
              fb.harmonic_basis(doy, 365.25, orders_doy),
              fb.hinge_basis(lead, n_knots)]
    for g in sorted(pred_mats):
        blocks.append(fb.hinge_basis(pred_mats[g].ravel(), n_knots))
    return np.column_stack(blocks)


def point_mask(row_idx: np.ndarray, n_rows: int, H: int) -> np.ndarray:
    m = np.zeros(n_rows, bool)
    m[row_idx] = True
    return np.repeat(m, H)


def decompose_one(eps: np.ndarray, X: np.ndarray, fmask: np.ndarray,
                  bmask: np.ndarray, alpha: float, fit_cap: int):
    """单特征：前段拟合 → 后段 λ → ε_sys/ε_res。返回 (eps_res, meta)。"""
    y = eps.ravel()
    fidx = np.where(fmask)[0]
    if len(fidx) > fit_cap:                          # 等距抽样（确定性，无随机）
        fidx = fidx[:: max(1, len(fidx) // fit_cap)]
    coef = fb.huber_ridge(X[fidx], y[fidx], alpha=alpha)
    if coef is None:
        return eps.copy(), {"stability_lambda": 0.0, "fit": "insufficient_data"}
    s_hat = X @ coef
    yb, sb = y[bmask], s_hat[bmask]
    m = np.isfinite(yb) & np.isfinite(sb)
    lam = 0.0
    if m.sum() >= 100:
        denom = float(sb[m] @ sb[m])
        if denom > 0:
            lam = float(np.clip((yb[m] @ sb[m]) / denom, 0.0, 1.0))
    sys_flat = lam * np.where(np.isfinite(s_hat), s_hat, 0.0)   # 未知处不剥（保守）
    res = (y - sys_flat).reshape(eps.shape)
    return res, {"stability_lambda": round(lam, 4), "fit": "ok"}


def main():
    cfg = fb.config_or_empty()
    dcfg = cfg.get("decompose", {})
    ap = argparse.ArgumentParser()
    ap.add_argument("--feature-true", default=cfg.get("feature_true"))
    ap.add_argument("--pairs", default="feature_pairs.json")
    ap.add_argument("--embargo", default=dcfg.get("embargo", "48h"))
    ap.add_argument("--alpha", type=float, default=dcfg.get("alpha", 1e-3))
    ap.add_argument("--fit-cap", type=int, default=dcfg.get("fit_cap", 400000))
    ap.add_argument("--orders-hod", type=int, default=dcfg.get("max_orders_hod", 3))
    ap.add_argument("--orders-doy", type=int, default=dcfg.get("max_orders_doy", 2))
    ap.add_argument("--n-knots", type=int, default=dcfg.get("n_knots", 4))
    ap.add_argument("--out", default="feature_decomp.json")
    args = ap.parse_args()
    if not args.feature_true:
        raise SystemExit("缺 --feature-true（或先写 blame_config.json）。")

    d = fb.require_du()
    pj = fb.read_json(args.pairs) or {}
    pairs = pj.get("pairs") or []
    if not pairs:
        raise SystemExit(f"{args.pairs} 里没有特征对——先跑 Stage 0 probe_schema.py。")
    ft, _ = fb.load_any(args.feature_true)
    ts_rows = ft[d.TIMESTAMP_COL]
    n_rows, H = len(ft), d.HORIZON

    eps = fb.eps_matrices(ft, pairs)
    pred_mats = {p["feature"]: d.to_matrix(ft, p["pred_col"]) for p in pairs}
    X = build_design(ts_rows, pred_mats, args.orders_hod, args.orders_doy, args.n_knots)
    front, back = fb.temporal_split(ts_rows, embargo=args.embargo)
    fmask = point_mask(front, n_rows, H)
    bmask = point_mask(back, n_rows, H)
    frow = np.zeros(n_rows, bool); frow[front] = True
    brow = np.zeros(n_rows, bool); brow[back] = True

    feats, lines = {}, []
    for feat in sorted(eps):
        res, meta = decompose_one(eps[feat], X, fmask, bmask, args.alpha, args.fit_cap)
        np.save(f"eps_res_{fb.sanitize(feat)}.npy", res)
        var_raw = float(np.nanvar(eps[feat]))
        var_res = float(np.nanvar(res))
        meta.update({
            "var_raw": round(var_raw, 6), "var_res": round(var_res, 6),
            "sys_frac": round(max(0.0, 1.0 - var_res / var_raw), 4) if var_raw > 0 else 0.0,
            "reducibility": fb.lag1_reducibility(res),
            "res_var_front": round(float(np.nanvar(res[frow])), 6),
            "res_var_back": round(float(np.nanvar(res[brow])), 6) if brow.any() else None,
        })
        feats[feat] = meta
        lines.append(f"  {feat:16s} λ={meta['stability_lambda']:.2f} sys_frac="
                     f"{meta['sys_frac']:.2f} 可约性={meta['reducibility']:.2f} [{meta['fit']}]")

    out = {"params": {"embargo": args.embargo, "alpha": args.alpha,
                      "orders_hod": args.orders_hod, "orders_doy": args.orders_doy,
                      "n_knots": args.n_knots, "fit_cap": args.fit_cap,
                      "n_front_rows": int(len(front)), "n_back_rows": int(len(back))},
           "n_rows": n_rows, "n_features": len(pairs),
           "skipped_unpaired": list(pj.get("unmapped") or []),
           "features": feats}
    fb.dump_json(args.out, out)

    print(f"[feature_decompose] 特征 ×{len(pairs)}  前段 {len(front)} 行 / 后段 {len(back)} 行"
          f"（embargo {args.embargo}；后段空 → λ=0 全部不剥）")
    for ln in lines[:20]:
        print(ln)
    print(f"  产物: eps_res_<feat>.npy ×{len(pairs)} + {args.out}")


if __name__ == "__main__":
    main()
