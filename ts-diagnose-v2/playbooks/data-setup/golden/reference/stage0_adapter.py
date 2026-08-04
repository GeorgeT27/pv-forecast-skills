#!/usr/bin/env python3
"""data-setup Stage 0 参考实现：薄适配器 + 对账两关 + 对齐报告。
CLI 契约 = playbook 菜谱声明；现场 adapter.py 照此契约写，gen_gate 用金标准闸它。"""
import argparse
import json

import pandas as pd


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--in", dest="inp", required=True)
    ap.add_argument("--n-steps", type=int, required=True)
    ap.add_argument("--freq", required=True)
    ap.add_argument("--out", default="predictions.csv")
    ap.add_argument("--alignment", default="alignment_report.json")
    ap.add_argument("--report", default="adapter_report.json")
    a = ap.parse_args()
    wide = pd.read_csv(a.inp)
    rows = []
    for r in wide.itertuples():
        for s in range(a.n_steps):
            rows.append({"window_ts": r.ts, "unit_id": r.station, "model": r.model,
                         "horizon_step": s, "y_true": getattr(r, f"y_{s}"),
                         "y_pred": getattr(r, f"p_{s}")})
    long = pd.DataFrame(rows)
    assert len(long) == len(wide) * a.n_steps, "对账关1：行数守恒破产"
    spot = []
    for r in wide.head(3).itertuples():
        sub = long[(long.window_ts == r.ts) & (long.model == r.model)]
        for s in range(a.n_steps):
            assert sub[sub.horizon_step == s].iloc[0]["y_pred"] == \
                getattr(r, f"p_{s}"), "对账关2：抽查数值不符"
        spot.append({"ts": str(r.ts), "model": str(r.model), "ok": True})
    long.to_csv(a.out, index=False)
    models = sorted(long.model.astype(str).unique())
    per_model = {m: set(long[long.model == m].window_ts) for m in models}
    aligned = set.intersection(*per_model.values()) if models else set()
    with open(a.alignment, "w", encoding="utf-8") as f:
        json.dump({"models": models,
                   "n_rows_per_model": {m: len(v) for m, v in per_model.items()},
                   "n_aligned": len(aligned),
                   "n_dropped_per_model": {m: len(v) - len(aligned)
                                           for m, v in per_model.items()},
                   "freq": a.freq,
                   "note": "dropped 不对称时下游只在对齐子集上比较"},
                  f, ensure_ascii=False, indent=2)
    with open(a.report, "w", encoding="utf-8") as f:
        json.dump({"rows_wide": len(wide), "rows_long": len(long),
                   "spot_checks": spot, "ok": True}, f, ensure_ascii=False, indent=2)


if __name__ == "__main__":
    main()
