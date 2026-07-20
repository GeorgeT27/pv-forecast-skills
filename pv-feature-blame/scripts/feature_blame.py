#!/usr/bin/env python3
"""Stage 2：特征归因——逐行特征质量误差 z 分数 + 全局校准，两者都命中才点名。

方法（细节见 references/blame-methods.md）：
  0) 误差源默认 ε_res（Stage 1.5 feature_decompose.py 的分解产物，剥掉可被模型自身吸收的
     系统性偏差，只留残余波动）——`--use-residual`（默认开）读 feature_decomp.json +
     eps_res_<feat>.npy；缺失/行数不符则硬失败或回退原始 ε（decomp=off，打印警示）。
  1) 特征误差：每 (口径, 特征) 在口径匹配切片上算 RMSE(pred − label)
     （rmse_192 → 全窗 192 点；ultra_short → [:ULTRA_SHORT_IDX+1] 考核点及其前导；
      short → SHORT_SLICE；另附全 192 点参考列）；对**全体行**的分布做 z 归一（不同量纲特征才可比）。
  2) 全局校准：跨全体行算 Spearman(行误差, 特征误差)——特征误差再大，若与该口径的
     行误差全局无关（模型可能根本不敏感），没资格被点名（诱饵防冤枉）。
  3) 两道分解闸（decomp=on 才生效）：
     - 可约性闸：reducibility_frac < --reducibility-min → 不点名（近白噪声，上游拿它没辙）。
     - 洗清闸：sys_frac ≥ --sys-frac-max → 不点名。误差方差绝大部分是模型可补偿的系统
       偏差，ε_res 只是量级微不足道的残影；z/ρ 都尺度不变，单靠塌量级挡不住残影的伪相关
       （如乘性稳偏被恒等式模型补偿的特征：raw ε 大且随行涨、ε_res 塌到 ~2% 但秩不变 →
       非此闸无法洗清）。off 模式两闸皆放行（reducibility=1.0、sys_frac=0.0）。
  4) blame_score = z × max(ρ, 0)；blamed = z ≥ z_hi 且 ρ ≥ spearman_min 且 分数进该行
     top_k 且 score > 0 且可约 且 未被补偿。
  共线性：特征误差向量两两相关 ≥0.8 分簇——同簇只报簇不点名单个（反驳门②）。

用法（在工作目录下，Stage 0/1（/1.5）产物就位后）：
  python3 <SKILL>/scripts/feature_blame.py \
      [--feature-true F.parquet] [--pairs feature_pairs.json] [--bad-rows bad_rows_summary.json] \
      [--z-hi 2.0 --spearman-min 0.3 --top-k 3] [--use-residual/--no-use-residual] \
      [--reducibility-min 0.1] [--sys-frac-max 0.85] \
      [--out blame_report.csv --summary blame_summary.json]

产物：blame_report.csv（仅坏行 × 特征：model,metric,timestamp_win,row_error,row_rank,
      feature,feature_err,feature_err_raw,feature_err_sys,reducibility_frac,note,
      feature_err_z,feature_err_full192,global_spearman,blame_score,blamed_topk）
      blame_summary.json（每口径×模型：特征按全局 ρ 排名、raw/res 双 ρ、sys_frac/λ/可约性、
      坏行归罪计数、共线簇、样本量；顶层 params.decomp 标记 "on"/"off"）
"""
from __future__ import annotations

import argparse
import os
import sys

import numpy as np
import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import fb_common as fb  # noqa: E402


def collinearity_clusters(fe_by_feature: dict[str, np.ndarray], thr: float = 0.8) -> list[list[str]]:
    """特征误差向量相关 ≥ thr 的连通分量（常量向量无边）。只报 ≥2 成员的簇。"""
    names = sorted(fe_by_feature)
    parent = {n: n for n in names}

    def find(x):
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    for i, a in enumerate(names):
        for b in names[i + 1:]:
            va, vb = fe_by_feature[a], fe_by_feature[b]
            if np.nanstd(va) == 0 or np.nanstd(vb) == 0:
                continue
            r = np.corrcoef(va, vb)[0, 1]
            if np.isfinite(r) and r >= thr:
                parent[find(a)] = find(b)
    groups: dict[str, list[str]] = {}
    for n in names:
        groups.setdefault(find(n), []).append(n)
    return sorted([sorted(g) for g in groups.values() if len(g) > 1])


def main():
    cfg = fb.config_or_empty()
    blame_cfg = cfg.get("blame", {})
    ap = argparse.ArgumentParser()
    ap.add_argument("--feature-true", default=cfg.get("feature_true"))
    ap.add_argument("--pairs", default="feature_pairs.json")
    ap.add_argument("--bad-rows", default="bad_rows_summary.json")
    ap.add_argument("--z-hi", type=float, default=blame_cfg.get("z_hi", 2.0))
    ap.add_argument("--spearman-min", type=float, default=blame_cfg.get("spearman_min", 0.3))
    ap.add_argument("--top-k", type=int, default=blame_cfg.get("top_k", 3))
    ap.add_argument("--out", default="blame_report.csv")
    ap.add_argument("--summary", default="blame_summary.json")
    dcfg = cfg.get("decompose", {})
    ap.add_argument("--use-residual", action=argparse.BooleanOptionalAction,
                    default=dcfg.get("enabled", True))
    ap.add_argument("--reducibility-min", type=float,
                    default=dcfg.get("reducibility_min", 0.1))
    ap.add_argument("--sys-frac-max", type=float,
                    default=dcfg.get("sys_frac_max", 0.85))
    args = ap.parse_args()
    if not args.feature_true:
        raise SystemExit("缺 --feature-true（或先写 blame_config.json）。没有就先问用户要——绝不静默降级。")

    d = fb.require_du()
    pairs = (fb.read_json(args.pairs) or {}).get("pairs") or []
    if not pairs:
        raise SystemExit(f"{args.pairs} 里没有特征对——先跑 Stage 0 probe_schema.py（unmapped 要问用户）。")
    br = fb.read_json(args.bad_rows)
    if not br or not br.get("metrics"):
        raise SystemExit(f"{args.bad_rows} 缺失或为空——先跑 Stage 1 find_bad_rows.py。")

    ft, _ = fb.load_any(args.feature_true)
    ft_index = {t: i for i, t in enumerate(pd.DatetimeIndex(ft[d.TIMESTAMP_COL]))}
    slices = fb.metric_slices()
    err_mats = fb.eps_matrices(ft, pairs)

    raw_mats = err_mats
    decomp_meta, decomp_mode = {}, "off"
    if args.use_residual:
        dec = fb.read_json("feature_decomp.json")
        if not dec:
            print("  ⚠ 未找到 feature_decomp.json —— 回退原始 ε 点名（decomp=off；"
                  "spec 要求先跑 Stage 1.5 feature_decompose.py）")
        elif int(dec.get("n_rows", -1)) != len(ft):
            raise SystemExit("feature_decomp.json 行数与 feature_true 不符——分解产物过期，"
                             "先重跑 feature_decompose.py。")
        else:
            res_mats = {}
            for feat in raw_mats:
                p = f"eps_res_{fb.sanitize(feat)}.npy"
                if not os.path.exists(p):
                    raise SystemExit(f"缺 {p}——分解产物不全，先重跑 feature_decompose.py。")
                res_mats[feat] = np.load(p)
            err_mats, decomp_meta, decomp_mode = res_mats, dec.get("features", {}), "on"

    report_rows, summary = [], {}
    for metric, by_model in br["metrics"].items():
        sl = slices[metric]
        for model, info in by_model.items():
            rows = pd.read_csv(os.path.join(os.path.dirname(args.bad_rows) or ".", info["csv"]),
                               parse_dates=["timestamp"])
            idx = np.array([ft_index.get(t, -1) for t in rows["timestamp"]])
            keep = idx >= 0
            if (~keep).any():
                print(f"  ⚠ {metric}×{model}: {int((~keep).sum())} 行在 feature_true 里没有对应"
                      "时间戳，已剔除（对齐缺口，回看 probe_schema.json）")
            rows, idx = rows[keep].reset_index(drop=True), idx[keep]
            fe_by_feature, z_by_feature, rho = {}, {}, {}
            for feat, E in err_mats.items():
                fe = np.sqrt(np.nanmean(E[idx][:, sl] ** 2, axis=1))
                fe_by_feature[feat] = fe
                z_by_feature[feat] = fb.zscores(fe)
                rho[feat] = round(fb.spearman(rows["row_error"].to_numpy(), fe), 4)
            fe_full = {feat: np.sqrt(np.nanmean(E[idx] ** 2, axis=1))
                       for feat, E in err_mats.items()}
            fe_raw = {feat: np.sqrt(np.nanmean(E[idx][:, sl] ** 2, axis=1))
                      for feat, E in raw_mats.items()}
            rho_raw = {feat: round(fb.spearman(rows["row_error"].to_numpy(), fe_raw[feat]), 4)
                       for feat in raw_mats}

            def red_frac(feat):
                if decomp_mode != "on":
                    return 1.0
                v = (decomp_meta.get(feat) or {}).get("reducibility")
                return float(v) if v is not None else 1.0

            def sys_frac(feat):                         # off/缺失 → 0（不因系统偏差豁免）
                if decomp_mode != "on":
                    return 0.0
                v = (decomp_meta.get(feat) or {}).get("sys_frac")
                return float(v) if v is not None else 0.0

            blamed_count = {feat: 0 for feat in err_mats}
            bad = rows[rows["is_bad"]]
            for ri in bad.index:
                scored = sorted(
                    ((feat, z_by_feature[feat][ri] * max(rho[feat], 0.0)) for feat in err_mats),
                    key=lambda kv: -kv[1])
                for rank_f, (feat, score) in enumerate(scored, 1):
                    z = float(z_by_feature[feat][ri])
                    reducible = red_frac(feat) >= args.reducibility_min
                    # 洗清闸：≥sys_frac_max 的误差方差是模型可补偿的系统偏差 → ε_res 是量级
                    #   微不足道的残影（z/ρ 尺度不变，光靠塌量级挡不住）→ 不点名。
                    compensated = sys_frac(feat) >= args.sys_frac_max
                    blamed = (z >= args.z_hi and rho[feat] >= args.spearman_min
                              and rank_f <= args.top_k and score > 0 and reducible
                              and not compensated)
                    blamed_count[feat] += blamed
                    report_rows.append({
                        "model": model, "metric": metric,
                        "timestamp_win": rows.loc[ri, "timestamp"],
                        "row_error": rows.loc[ri, "row_error"],
                        "row_rank": int(rows.loc[ri, "row_rank"]),
                        "feature": feat,
                        "feature_err": round(float(fe_by_feature[feat][ri]), 6),
                        "feature_err_raw": round(float(fe_raw[feat][ri]), 6),
                        "feature_err_sys": round(float(fe_raw[feat][ri] - fe_by_feature[feat][ri]), 6),
                        "reducibility_frac": round(red_frac(feat), 4),
                        "note": ("compensated" if compensated else
                                 "" if reducible else "irreducible"),
                        "feature_err_z": round(z, 4),
                        "feature_err_full192": round(float(fe_full[feat][ri]), 6),
                        "global_spearman": rho[feat],
                        "blame_score": round(float(score), 4),
                        "blamed_topk": bool(blamed),
                    })
            summary.setdefault(metric, {})[model] = {
                "n_rows": int(len(rows)), "n_bad": int(len(bad)),
                "features": {feat: {"global_spearman": rho[feat],
                                    "feature_err_mean": round(float(np.nanmean(fe_by_feature[feat])), 6),
                                    "blamed_rows": int(blamed_count[feat]),
                                    "z_max": round(float(np.nanmax(z_by_feature[feat])), 4)
                                    if len(rows) else None,
                                    "global_spearman_raw": rho_raw[feat],
                                    "feature_err_raw_mean": round(float(np.nanmean(fe_raw[feat])), 6),
                                    "sys_frac": (decomp_meta.get(feat) or {}).get("sys_frac"),
                                    "stability_lambda": (decomp_meta.get(feat) or {}).get("stability_lambda"),
                                    "reducibility_frac": round(red_frac(feat), 4)}
                             for feat in err_mats},
                "ranking_by_spearman": sorted(rho, key=lambda f: -rho[f]),
                "collinearity_clusters": collinearity_clusters(fe_by_feature),
            }

    pd.DataFrame(report_rows).to_csv(args.out, index=False)
    fb.dump_json(args.summary, {"params": {"z_hi": args.z_hi, "spearman_min": args.spearman_min,
                                           "top_k": args.top_k, "decomp": decomp_mode},
                                "features": [p["feature"] for p in pairs], **summary})

    print(f"[feature_blame] 特征 ×{len(pairs)}   z_hi={args.z_hi} ρ_min={args.spearman_min} "
          f"top_k={args.top_k} decomp={decomp_mode}")
    for metric, by_model in summary.items():
        for model, s in by_model.items():
            named = [f for f, v in s["features"].items() if v["blamed_rows"] > 0]
            print(f"  {metric:12s} × {model:16s} 坏行 {s['n_bad']}/{s['n_rows']}  "
                  f"被点名: {named or '无'}  全局ρ榜首: {s['ranking_by_spearman'][0]}"
                  f"  共线簇: {s['collinearity_clusters'] or '无'}")
    print(f"  产物: {args.out} + {args.summary}")


if __name__ == "__main__":
    main()
