#!/usr/bin/env python3
"""Stage 1：坏行定位——每口径 × 每模型，各自找坏行。

行级误差定义（常量一律 import 自 pv-result-analysis 的 data_utils，绝不本地重定义）：
  ultra_short：每行第 ULTRA_SHORT_IDX(16) 点的绝对误差（全部行参与）；
  short：仅 09:00 行，SHORT_SLICE([59:155]，次日全天 96 点) 上的 RMSE。
坏行 = 误差 > 该口径均值 且 进 top --top-pct%（两个条件都要；数据量小时阈值可调）。
输出**全量排名**而不只坏行——Stage 2 的 z 归一和全局相关需要全行分布。

用法（在工作目录下；缺省从 blame_config.json 取路径与参数）：
  python3 <SKILL>/scripts/find_bad_rows.py \
      [--test T.parquet --predict P.parquet] [--models auto|pred_M1,pred_ensemble] \
      [--metrics ultra_short,short] [--top-pct 10] [--out-dir .]

产物：bad_rows_<metric>_<model>.csv（timestamp,row_error,row_rank,is_bad，按时间序）
      bad_rows_summary.json（每口径×模型的 n/均值/阈值/坏行数/最坏时间戳/CSV 文件名）
"""
from __future__ import annotations

import argparse
import os
import sys

import numpy as np
import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import fb_common as fb  # noqa: E402
from probe_schema import discover_models  # noqa: E402  复用模型列发现（1..N 鲁棒）


def main():
    cfg = fb.config_or_empty()
    ap = argparse.ArgumentParser()
    ap.add_argument("--test", default=cfg.get("test_label"))
    ap.add_argument("--predict", default=cfg.get("predict"))
    ap.add_argument("--models", default="auto", help="auto=全部 192 点列；或逗号分隔列名")
    ap.add_argument("--metrics", default=",".join(cfg.get("metrics", ["ultra_short", "short"])))
    ap.add_argument("--top-pct", type=float, default=cfg.get("top_pct", 10))
    ap.add_argument("--out-dir", default=".")
    ap.add_argument("--summary-out", default="bad_rows_summary.json")
    args = ap.parse_args()
    if not args.test or not args.predict:
        raise SystemExit("缺 --test/--predict（或先写 blame_config.json）。")

    d = fb.require_du()
    test_df, _ = fb.load_any(args.test)
    pred_df, _ = fb.load_any(args.predict)
    if args.models == "auto":
        models = discover_models(fb.list_columns(pred_df), d.HORIZON)
    else:
        models = [m.strip() for m in args.models.split(",") if m.strip()]
    if not models:
        raise SystemExit("predict 里找不到任何模型列（192 点 list 列）。")
    metrics = [m.strip() for m in args.metrics.split(",") if m.strip()]

    summary = {"top_pct": args.top_pct, "threshold_rule": "top_pct_above_mean",
               "models": models, "metrics": {}}
    lines = []
    for model in models:
        ts, P, Y = d.align(pred_df, test_df, model)      # 内连接对齐，(n,192)
        for metric in metrics:
            sel, err = fb.row_errors(ts, P, Y, metric)
            mask = fb.bad_mask(err, args.top_pct)
            rank = np.empty(len(err), int)
            rank[np.argsort(-err)] = np.arange(1, len(err) + 1)
            out = pd.DataFrame({"timestamp": pd.DatetimeIndex(ts)[sel],
                                "row_error": np.round(err, 6),
                                "row_rank": rank, "is_bad": mask})
            csv = f"bad_rows_{metric}_{fb.sanitize(model)}.csv"
            out.to_csv(os.path.join(args.out_dir, csv), index=False)
            worst = str(out.loc[out["row_error"].idxmax(), "timestamp"]) if len(out) else None
            top5 = [str(t) for t in out.sort_values("row_error", ascending=False)
                    ["timestamp"].head(5)]
            summary["metrics"].setdefault(metric, {})[model] = {
                "csv": csv, "n_rows": int(len(out)),
                "mean_error": round(float(np.nanmean(err)), 6) if len(err) else None,
                "std_error": round(float(np.nanstd(err)), 6) if len(err) else None,
                "n_bad": int(mask.sum()), "worst_timestamp": worst, "top5_timestamps": top5,
            }
            lines.append(f"  {metric:12s} × {model:16s} n={len(out):5d}  坏行={int(mask.sum()):4d}"
                         f"  最坏 {worst}")
    fb.dump_json(os.path.join(args.out_dir, args.summary_out), summary)

    print(f"[find_bad_rows] 模型 ×{len(models)} {models}   口径 {metrics}   "
          f"规则 top {args.top_pct}% 且 >均值")
    for ln in lines[:20]:
        print(ln)
    print(f"  产物: bad_rows_<metric>_<model>.csv ×{len(lines)} + {args.summary_out}")


if __name__ == "__main__":
    main()
