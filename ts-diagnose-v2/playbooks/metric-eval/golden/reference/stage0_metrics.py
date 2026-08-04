#!/usr/bin/env python3
"""metric-eval Stage 0 参考实现：按口径逐模型算指标，产 metrics.csv（逐模型×逐单元
长表）+ metrics_summary.json（自足汇总，caliber 字段落口径定义原文——下游只读这个）。
CLI 契约 = playbook 菜谱声明；现场 analysis_scripts/metrics.py 照此契约写，gen_gate
用金标准闸它。目前仅实现 rmse_192（默认口径：每行全部 horizon 点的 RMSE）——其余口径
（子段/MAE/外部脚本）由现场脚本按用户答案扩展，不在参考实现里预写全部分支。"""
import argparse
import json

import pandas as pd

CALIBER_DEFS = {
    "rmse_192": "每行全部 horizon 点的 RMSE：逐 (model,window,horizon_step) 误差平方，"
                "按模型聚合后开方",
}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--pred", required=True)
    ap.add_argument("--caliber", default="rmse_192")
    ap.add_argument("--out", default="metrics.csv")
    ap.add_argument("--summary", default="metrics_summary.json")
    a = ap.parse_args()
    if a.caliber not in CALIBER_DEFS:
        raise SystemExit(f"未知口径：{a.caliber}（参考实现目前只覆盖 rmse_192）")

    df = pd.read_csv(a.pred)
    df["sq_err"] = (df.y_pred - df.y_true) ** 2

    rows = []
    per_model = {}
    for model, g in df.groupby("model"):
        rmse = (g["sq_err"].mean()) ** 0.5
        per_model[str(model)] = rmse
        for unit_id, gu in g.groupby("unit_id"):
            for window_ts, gw in gu.groupby("window_ts"):
                row_rmse = (gw["sq_err"].mean()) ** 0.5
                rows.append({"model": model, "unit_id": unit_id,
                             "window_ts": window_ts, "metric": a.caliber,
                             "value": row_rmse})

    out = pd.DataFrame(rows, columns=["model", "unit_id", "window_ts", "metric", "value"])
    out.to_csv(a.out, index=False)

    with open(a.summary, "w", encoding="utf-8") as f:
        json.dump({
            "caliber": CALIBER_DEFS[a.caliber],
            "models": per_model,
            "n_rows": int(len(df)),
            "window_range": [str(df.window_ts.min()), str(df.window_ts.max())],
        }, f, ensure_ascii=False, indent=2)


if __name__ == "__main__":
    main()
