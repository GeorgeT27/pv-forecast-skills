#!/usr/bin/env python3
"""① 离线跑一次：在测试集三张大表上，算每模型 power / 每特征 的 RMSE 历史统计 → baseline.json。

统计块 = mean/std/median/p10/p25/p75/p90/min/max/n，并存 global 与 by_hour（'HH:MM'）两层。
- power 依赖模型（每个模型一套）；
- feature（X_pred vs X）与功率模型无关（上游预报误差），故存在顶层一份，不按模型重复。

用法：
  python3 build_baseline.py --predict P.parquet --test T.parquet --feature-true F.parquet \
    [--true-power-col observe_power_future] [--models auto|pred_M1,pred_M2] [--out baseline.json]
"""
from __future__ import annotations

import argparse
import json
import os
import sys

import numpy as np
import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import rd_common as rc  # noqa: E402


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--predict", required=True)
    ap.add_argument("--test", required=True)
    ap.add_argument("--feature-true", required=True)
    ap.add_argument("--true-power-col", default=rc.DEFAULT_TRUE_POWER_COL)
    ap.add_argument("--models", default="auto", help="auto=全部192点list列；或逗号分隔列名")
    ap.add_argument("--out", default="baseline.json")
    args = ap.parse_args()

    pred_df = rc.load_table(args.predict)
    test_df = rc.load_table(args.test)
    ft_df = rc.load_table(args.feature_true)

    models = (rc.discover_models(pred_df) if args.models == "auto"
              else [m.strip() for m in args.models.split(",") if m.strip()])
    if not models:
        raise SystemExit("predict 里找不到任何模型列（192点list列）。")

    pairs, unmapped = rc.feature_pairs(ft_df)
    if not pairs:
        raise SystemExit("feature_true 里配不出任何 X_pred/X 特征对——检查列名（真值列须为去掉 _pred 的基名）。")
    if unmapped:
        print(f"  ⚠ 未配对的 list 列（跳过，不进基线）: {unmapped}")

    # ---- feature 基线（模型无关，顶层一份）
    features = {}
    for feat, cc in pairs.items():
        E = rc.to_matrix(ft_df, cc["pred"]) - rc.to_matrix(ft_df, cc["true"])
        rmse = np.sqrt(np.nanmean(E ** 2, axis=1))
        features[feat] = rc.stats_global_and_hourly(rmse, ft_df["timestamp"])

    # ---- power 基线（每模型一套）
    models_out = {}
    for m in models:
        ts, P, Y = rc.align_power(pred_df, test_df, m, args.true_power_col)
        rmse = rc.row_rmse(P, Y)
        models_out[m] = {"power": rc.stats_global_and_hourly(rmse, ts)}

    baseline = {
        "meta": {
            "generated_from": {"predict": os.path.abspath(args.predict),
                               "test": os.path.abspath(args.test),
                               "feature_true": os.path.abspath(args.feature_true)},
            "true_power_col": args.true_power_col,
            "rmse_def": "sqrt(nanmean((pred-true)^2)) over full horizon",
            "n_feature_rows": int(len(ft_df)),
            "unmapped_feature_cols": unmapped,
        },
        "feature_pairs": pairs,
        "features": features,
        "models": models_out,
    }
    with open(args.out, "w", encoding="utf-8") as f:
        json.dump(baseline, f, ensure_ascii=False, indent=2)

    # 终端摘要
    print(f"[build_baseline] 模型 ×{len(models)} {models}   特征 ×{len(pairs)}   → {args.out}")
    for m in models:
        g = models_out[m]["power"]["global"]
        print(f"  {m:16s} power RMSE  均值 {g['mean']}  std {g['std']}  "
              f"中位 {g['median']}  (n={g['n']}, 钟点组 {len(models_out[m]['power']['by_hour'])})")
    hi = sorted(features, key=lambda f: -(features[f]['global']['mean'] or 0))[:3]
    print(f"  特征历史 RMSE 均值最高 Top3: "
          + ", ".join(f"{f}={features[f]['global']['mean']}" for f in hi))


if __name__ == "__main__":
    main()
