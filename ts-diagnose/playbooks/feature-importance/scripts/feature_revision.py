#!/usr/bin/env python3
"""Stage 2（并行产物·免 API）：预报翻新跳变分析——相邻行是同一物理时刻的两次起报，
行 T 第 j+1 点与行 T+Δ 第 j 点真值相同，但预报值可以差距巨大（逐行重新起报）。
本脚本回答：哪些特征翻新最跳？跳变带来精度改善吗（健康翻新 vs 纯噪声抖动）？
哪个特征的跳变把哪个模型的预测搅得行间不稳（churn）？

文献纪律（Zsoter jumpiness；实证跳变与预报误差仅弱相关）：**跳变大 ≠ 有罪**。
点名「翻新致不稳」须过两关（与 Stage 2 真值误差归因同哲学）：
  关一：特征跳变可观（jumpiness ≥ jumpiness_min，量纲归一后）；
  关二：特征跳变与模型 churn 跨相邻对 Spearman ≥ spearman_min。
且模型自身 churn 可观才有案可查（churn_rel < stable_max 直接判「行间稳定」）。
升「已证实」唯一通道 = counterfactual_api.py 的 neighbor-swap 模式。

对齐数学（authority: data_utils.rebuild_series——未来段从窗口起点当步开始）：
相邻对 (r, r+1)（须 Δts==FREQ，真实数据有缺行）：r+1 第 j 点 = r 第 j+1 点（物理时刻同），
j ∈ [0, 190]。per-pair 标量按**口径匹配切片**算（全 191 点平均会把随时刻变化的信号洗平）。

用法（在工作目录下；缺省从 blame_config.json 取路径）：
  python3 <SKILL>/scripts/feature_revision.py \
      [--test T.parquet --predict P.parquet --feature-true F.parquet] [--pairs feature_pairs.json] \
      [--spearman-min 0.3] [--jumpiness-min 0.05] [--stable-max 0.02] \
      [--out revision_report.csv] [--summary revision_summary.json]

产物：revision_report.csv（每 口径×模型×特征 一行）+ revision_summary.json
"""
from __future__ import annotations

import argparse
import os
import sys

import numpy as np
import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import fb_common as fb  # noqa: E402


def pair_scalar(mat: np.ndarray, i: int, sl: slice) -> np.ndarray:
    """相邻对 (i, i+1) 的跳变向量在切片 sl 上：new[j] − old[j+1]，j 限 [0,190]。"""
    j = np.arange(192)[sl]
    j = j[j <= 190]
    return mat[i + 1, j] - mat[i, j + 1]


def rms(v: np.ndarray) -> float:
    v = v[np.isfinite(v)]
    return float(np.sqrt(np.mean(v ** 2))) if v.size else float("nan")


def adjacent_pairs(ts: pd.DatetimeIndex, freq) -> list[int]:
    return [i for i in range(len(ts) - 1) if ts[i + 1] - ts[i] == freq]


def flipflop_rate(signed_means: np.ndarray, eps: float) -> float | None:
    """连续两对的切片平均跳变符号交替率（都超 eps 才计入——零跳对不算翻转）。"""
    s = signed_means[np.isfinite(signed_means)]
    live = np.abs(s) > eps
    flips = total = 0
    for a, b in zip(range(len(s) - 1), range(1, len(s))):
        if live[a] and live[b]:
            total += 1
            flips += (np.sign(s[a]) != np.sign(s[b]))
    return round(flips / total, 4) if total else None


def improvement(mat: np.ndarray, truth: np.ndarray, i: int, sl: slice) -> np.ndarray:
    """翻新是否更准：|新−真| − |旧−真|（新 = 行 i+1 第 j 点，旧 = 行 i 第 j+1 点，
    真值取行 i+1 的 label——交叉核验已保证 label 跨行一致）。负 = 翻新改善。"""
    j = np.arange(192)[sl]
    j = j[j <= 190]
    return (np.abs(mat[i + 1, j] - truth[i + 1, j])
            - np.abs(mat[i, j + 1] - truth[i + 1, j]))


def main():
    cfg = fb.config_or_empty()
    rev_cfg = cfg.get("revision") or {}
    ap = argparse.ArgumentParser()
    ap.add_argument("--test", default=cfg.get("test_label"))
    ap.add_argument("--predict", default=cfg.get("predict"))
    ap.add_argument("--feature-true", default=cfg.get("feature_true"))
    ap.add_argument("--pairs", default="feature_pairs.json")
    ap.add_argument("--spearman-min", type=float, default=rev_cfg.get("spearman_min", 0.3))
    ap.add_argument("--jumpiness-min", type=float, default=rev_cfg.get("jumpiness_min", 0.05))
    ap.add_argument("--stable-max", type=float, default=rev_cfg.get("stable_max", 0.02))
    ap.add_argument("--out", default="revision_report.csv")
    ap.add_argument("--summary", default="revision_summary.json")
    args = ap.parse_args()
    for k in ("test", "predict", "feature_true"):
        if not getattr(args, k):
            raise SystemExit(f"缺 --{k.replace('_', '-')}（或先写 blame_config.json）。")

    d = fb.require_du()
    pairs_doc = fb.read_json(args.pairs) or {}
    fpairs = pairs_doc.get("pairs") or []
    if not fpairs:
        raise SystemExit("feature_pairs.json 缺特征对——先跑 Stage 0（probe_schema.py）。")

    test_df, _ = fb.load_any(args.test)
    pred_df, _ = fb.load_any(args.predict)
    ft_df, _ = fb.load_any(args.feature_true)
    # 三方 inner-join（predict 逐模型与 feature_true 的行集可能不一致）
    common = (set(pd.DatetimeIndex(test_df[d.TIMESTAMP_COL]))
              & set(pd.DatetimeIndex(pred_df[d.TIMESTAMP_COL]))
              & set(pd.DatetimeIndex(ft_df[d.TIMESTAMP_COL])))
    order = sorted(common)
    def take(df):
        m = {t: i for i, t in enumerate(pd.DatetimeIndex(df[d.TIMESTAMP_COL]))}
        return df.iloc[[m[t] for t in order]].reset_index(drop=True)
    test_df, pred_df, ft_df = take(test_df), take(pred_df), take(ft_df)
    ts = pd.DatetimeIndex(order)
    idx_pairs = adjacent_pairs(ts, d.FREQ)
    if not idx_pairs:
        raise SystemExit("找不到相邻行对（Δts==15min）——行集太稀疏，翻新分析无法进行。")

    model_cols = [c for c in pred_df.columns
                  if c != d.TIMESTAMP_COL and fb.list_columns(pred_df).get(c) == d.HORIZON]
    Y = d.to_matrix(test_df, d.LABEL_COL)
    slices = fb.metric_slices()

    fmats = {p["feature"]: (d.to_matrix(ft_df, p["pred_col"]), d.to_matrix(ft_df, p["label_col"]))
             for p in fpairs}
    mmats = {m: d.to_matrix(pred_df, m) for m in model_cols}
    scales = {f: float(np.nanstd(mat)) or 1.0 for f, (mat, _) in fmats.items()}
    mscales = {m: float(np.nanstd(mat)) or 1.0 for m, mat in mmats.items()}

    rows, summary = [], {"params": {"spearman_min": args.spearman_min,
                                    "jumpiness_min": args.jumpiness_min,
                                    "stable_max": args.stable_max},
                         "n_rows_used": len(order), "n_adjacent_pairs": len(idx_pairs),
                         "metrics": {}, "features": {}}

    # 模型无关的特征翻新画像（全 191 点参考口径）
    full = slice(0, 192)
    for f, (mat, lab) in fmats.items():
        jr = np.array([rms(pair_scalar(mat, i, full)) for i in idx_pairs])
        sm = np.array([float(np.nanmean(pair_scalar(mat, i, full))) for i in idx_pairs])
        imp = np.concatenate([improvement(mat, lab, i, full) for i in idx_pairs])
        imp = imp[np.isfinite(imp)]
        jumpy = imp[np.abs(imp) > 1e-9]      # 只统计翻新实际动了的点
        summary["features"][f] = {
            "jump_mean_full192": round(float(np.nanmean(jr)), 6),
            "jumpiness_full192": round(float(np.nanmean(jr)) / scales[f], 6),
            "flipflop_rate_full192": flipflop_rate(sm, 1e-9 * max(scales[f], 1.0)),
            "improve_rate": round(float((jumpy < 0).mean()), 4) if jumpy.size else None,
            "mean_improvement": round(float(np.mean(imp)), 6) if imp.size else None,
        }

    for metric, sl in slices.items():
        summary["metrics"][metric] = {}
        for m in model_cols:
            churn = np.array([rms(pair_scalar(mmats[m], i, sl)) for i in idx_pairs])
            churn_mean = float(np.nanmean(churn))
            churn_rel = churn_mean / mscales[m]
            stable = churn_rel < args.stable_max
            # 模型自身翻新是否更准（对功率真值）
            mimp = np.concatenate([improvement(mmats[m], Y, i, sl) for i in idx_pairs])
            mimp = mimp[np.isfinite(mimp)]
            ment = {"churn_mean": round(churn_mean, 6), "churn_rel": round(churn_rel, 6),
                    "stable": bool(stable),
                    "pred_improve_rate": (round(float((mimp[np.abs(mimp) > 1e-9] < 0).mean()), 4)
                                          if (np.abs(mimp) > 1e-9).any() else None),
                    "features": {}, "named": []}
            for f, (mat, _) in fmats.items():
                jr = np.array([rms(pair_scalar(mat, i, sl)) for i in idx_pairs])
                jumpiness = float(np.nanmean(jr)) / scales[f]
                rho = fb.spearman(jr, churn)
                named = bool((not stable) and jumpiness >= args.jumpiness_min
                             and rho >= args.spearman_min)
                ment["features"][f] = {"jump_mean": round(float(np.nanmean(jr)), 6),
                                       "jumpiness": round(jumpiness, 6),
                                       "churn_spearman": round(rho, 4), "named": named}
                if named:
                    ment["named"].append(f)
                rows.append({"metric": metric, "model": m, "feature": f,
                             "jump_mean": round(float(np.nanmean(jr)), 6),
                             "jumpiness": round(jumpiness, 6),
                             "churn_spearman": round(rho, 4),
                             "model_churn_mean": round(churn_mean, 6),
                             "model_stable": bool(stable), "named": named})
            ment["named"].sort(
                key=lambda f: -ment["features"][f]["churn_spearman"])
            summary["metrics"][metric][m] = ment

    pd.DataFrame(rows).to_csv(args.out, index=False)
    fb.dump_json(args.summary, summary)

    print(f"[feature_revision] 行 {len(order)}  相邻对 {len(idx_pairs)}  模型 ×{len(model_cols)}  "
          f"特征 ×{len(fmats)}   两关: jumpiness≥{args.jumpiness_min} ∧ ρ≥{args.spearman_min}")
    for metric, by_m in summary["metrics"].items():
        for m, ent in by_m.items():
            tag = "行间稳定" if ent["stable"] else (f"点名: {ent['named']}" if ent["named"]
                                                    else "churn 可观但无特征过两关")
            print(f"  {metric:12s} × {m:15s} churn={ent['churn_mean']:.4g} "
                  f"(rel={ent['churn_rel']:.4g})  {tag}")
    top = sorted(summary["features"].items(),
                 key=lambda kv: -(kv[1]["jumpiness_full192"] or 0))[:3]
    print("  特征翻新画像 top3（与有罪与否无关）: "
          + ", ".join(f"{f}(jumpiness={v['jumpiness_full192']:.3g}, 改善率={v['improve_rate']})"
                      for f, v in top))
    print(f"  产物: {args.out} + {args.summary}   —— 点名≠定罪：升「已证实」走 neighbor-swap 反事实")


if __name__ == "__main__":
    main()
