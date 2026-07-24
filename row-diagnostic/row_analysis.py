#!/usr/bin/env python3
"""② 单行诊断：某模型在某时间戳的预测，跟它自己在测试集上的历史统计比，哪里反常。

读 baseline.json + 三张大表，对目标行算 power/每特征的 RMSE，与 global 及 by_hour（同钟点）
基线比 → diff / z / 稳健z / 百分位带，特征按 |z| 降序（最反常在最上 = 头号可疑）。
出 CSV（特征表）+ JSON（全摘要）+ 2×2 图 + 终端大白话。

用法：
  python3 row_analysis.py --model pred_M1 --row "2025-01-02 09:00:00"
  python3 row_analysis.py --model pred_M1 --worst
  [--baseline baseline.json --predict P --test T --feature-true F --out-dir . --prefix row --no-plots]

⚠️ 本工具只做「与自身历史比、谁反常」。反常特征 ≠ 证明它导致功率变差；因果验证需反事实
   替换（见 ts-diagnose 的 feature-importance playbook，feature-quality/counterfactual
   变体）。结论止于「反常提示」。
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


def sanitize(s: str) -> str:
    return "".join(c if c.isalnum() else "_" for c in str(s))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--model", required=True)
    ap.add_argument("--row", help="窗口时间戳，如 '2025-01-02 09:00:00'")
    ap.add_argument("--worst", action="store_true", help="取该模型 power RMSE 最大的行")
    ap.add_argument("--baseline", default="baseline.json")
    ap.add_argument("--predict", help="缺省用 baseline.meta 里记录的路径")
    ap.add_argument("--test")
    ap.add_argument("--feature-true")
    ap.add_argument("--out-dir", default=".")
    ap.add_argument("--prefix", default="row")
    ap.add_argument("--no-plots", action="store_true")
    args = ap.parse_args()
    if not args.row and not args.worst:
        raise SystemExit("给一个行：--row '<时间戳>' 或 --worst。")

    if not os.path.exists(args.baseline):
        raise SystemExit(f"找不到 {args.baseline}——先跑 build_baseline.py 生成。")
    with open(args.baseline, encoding="utf-8") as f:
        base = json.load(f)
    meta = base["meta"]
    predict = args.predict or meta["generated_from"]["predict"]
    test = args.test or meta["generated_from"]["test"]
    feature_true = args.feature_true or meta["generated_from"]["feature_true"]
    true_power_col = meta["true_power_col"]

    if args.model not in base["models"]:
        raise SystemExit(f"baseline 里没有模型 '{args.model}'；可选: {list(base['models'])}")

    pred_df = rc.load_table(predict)
    test_df = rc.load_table(test)
    ft_df = rc.load_table(feature_true)
    pairs = base["feature_pairs"]

    # ---- 定位目标行
    ts, P, Y = rc.align_power(pred_df, test_df, args.model, true_power_col)
    power_rmse_all = rc.row_rmse(P, Y)
    ts_idx = pd.DatetimeIndex(ts)
    if args.worst:
        pos = int(np.argmax(power_rmse_all))
        target_ts = ts_idx[pos]
    else:
        target_ts = pd.Timestamp(args.row)
        where = np.where(ts_idx == target_ts)[0]
        if not len(where):
            raise SystemExit(f"时间戳 {target_ts} 不在 predict∩test 里。可用范围 "
                             f"{ts_idx.min()} .. {ts_idx.max()}（{len(ts_idx)} 行）。")
        pos = int(where[0])
    ft_where = np.where(pd.DatetimeIndex(ft_df["timestamp"]) == target_ts)[0]
    if not len(ft_where):
        raise SystemExit(f"时间戳 {target_ts} 不在 feature_true 里，无法算特征反常。")
    ft_pos = int(ft_where[0])
    hkey = rc.hour_key(target_ts)

    # ---- 功率画像
    row_power = float(power_rmse_all[pos])
    pw = base["models"][args.model]["power"]
    dev_g = rc.deviation(row_power, pw["global"])
    dev_h = rc.deviation(row_power, pw["by_hour"].get(hkey))
    power_rank = int(1 + np.sum(power_rmse_all > row_power))
    power_pctl = round(float(np.mean(power_rmse_all <= row_power) * 100), 1)
    power = {"row_rmse": round(row_power, 6), "hour": hkey,
             "vs_global": dev_g, "vs_hour": dev_h,
             "global_rank": power_rank, "global_pctl": power_pctl,
             "n_rows": int(len(power_rmse_all)),
             "status": rc.status_from_z(dev_g["z"])}

    # ---- 逐特征
    feat_rows = []
    for feat, cc in pairs.items():
        pv = rc.to_matrix(ft_df.iloc[[ft_pos]], cc["pred"])[0]
        tv = rc.to_matrix(ft_df.iloc[[ft_pos]], cc["true"])[0]
        r = float(np.sqrt(np.nanmean((pv - tv) ** 2)))
        blk_g = base["features"][feat]["global"]
        blk_h = base["features"][feat]["by_hour"].get(hkey)
        dg = rc.deviation(r, blk_g)
        dh = rc.deviation(r, blk_h)
        feat_rows.append({
            "feature": feat, "row_rmse": round(r, 6),
            "base_mean": blk_g["mean"], "base_std": blk_g["std"], "base_median": blk_g["median"],
            "diff": dg["diff"], "z": dg["z"], "z_robust": dg["z_robust"],
            "pctl_band": dg["pctl_band"],
            "hour_mean": (blk_h or {}).get("mean"), "hour_z": dh["z"],
            "status": rc.status_from_z(dg["z"]),
        })
    # 按 z 降序（None 沉底）
    feat_rows.sort(key=lambda d: (d["z"] is None, -(d["z"] if d["z"] is not None else 0)))

    # ---- 落盘 CSV / JSON
    ts_tag = sanitize(str(target_ts))
    os.makedirs(args.out_dir, exist_ok=True)
    csv_path = os.path.join(args.out_dir, f"{args.prefix}_{ts_tag}_features.csv")
    pd.DataFrame(feat_rows).to_csv(csv_path, index=False)

    top = [r for r in feat_rows if r["z"] is not None and r["z"] >= 2]
    summary = {
        "timestamp": str(target_ts), "model": args.model, "hour": hkey,
        "selector": "worst" if args.worst else "explicit",
        "power": power, "features": feat_rows,
        "abnormal_features": [r["feature"] for r in top],
        "top_suspect": feat_rows[0]["feature"] if feat_rows else None,
        "note": ("本工具只做与自身历史统计的偏离对比；反常特征≠证明它导致功率变差，"
                 "因果验证需反事实替换（见 ts-diagnose 的 feature-importance playbook，"
                 "feature-quality/counterfactual 变体）。"),
    }
    json_path = os.path.join(args.out_dir, f"{args.prefix}_{ts_tag}.json")
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(summary, f, ensure_ascii=False, indent=2)

    imgs = []
    if not args.no_plots:
        try:
            imgs = make_plots(target_ts, args.model, hkey, P[pos], Y[pos], power,
                              feat_rows, ft_df, ft_pos, pairs, args.out_dir, args.prefix, ts_tag)
        except ImportError:
            print("  ⚠ 未装 matplotlib，跳过出图（pip install matplotlib）。")

    # ---- 终端大白话
    print(f"[row_analysis] {target_ts}  模型 {args.model}  钟点 {hkey}")
    zt = f"{power['vs_global']['z']:+.2f}σ" if power['vs_global']['z'] is not None else "n/a"
    zh = f"{power['vs_hour']['z']:+.2f}σ" if power['vs_hour']['z'] is not None else "n/a"
    print(f"  功率 RMSE {row_power:.3f}  [{power['status']}]  vs全局 {zt}  vs同钟点 {zh}  "
          f"全局排名 {power_rank}/{power['n_rows']} (p{power_pctl})")
    print(f"  反常特征(z≥2): {summary['abnormal_features'] or '无'}")
    print("  特征偏离榜（按 z 降序，前 5）:")
    for r in feat_rows[:5]:
        zz = f"{r['z']:+.2f}σ" if r["z"] is not None else "n/a"
        hh = f"{r['hour_z']:+.2f}σ" if r["hour_z"] is not None else "n/a"
        print(f"    {r['feature']:16s} RMSE {r['row_rmse']:8.3f}  均值 {r['base_mean']:8.3f}  "
              f"vs全局 {zz:>7}  vs同钟点 {hh:>7}  {r['pctl_band']:>7}  [{r['status']}]")
    print(f"  产物: {csv_path}  {json_path}" + ("  " + "  ".join(imgs) if imgs else ""))


def make_plots(target_ts, model, hkey, P_row, Y_row, power, feat_rows,
               ft_df, ft_pos, pairs, out_dir, prefix, ts_tag):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    import matplotlib.font_manager
    for _f in ("Arial Unicode MS", "PingFang SC", "Hiragino Sans GB", "Heiti TC",
               "SimHei", "Noto Sans CJK SC", "Microsoft YaHei"):
        if _f in {f.name for f in matplotlib.font_manager.fontManager.ttflist}:
            plt.rcParams["font.family"] = "sans-serif"
            plt.rcParams["font.sans-serif"] = [_f, "DejaVu Sans"]
            break
    plt.rcParams["axes.unicode_minus"] = False

    order = feat_rows                          # 已按 z 降序
    fig, axes = plt.subplots(2, 2, figsize=(15, 10))
    fig.suptitle(f"Row diagnosis  {target_ts}   model={model}  hour={hkey}",
                 fontsize=14, fontweight="bold")

    # (1) 功率 pred vs true
    ax = axes[0, 0]
    ax.plot(Y_row, label="true power", color="#1f77b4", lw=1.6)
    ax.plot(P_row, label="predicted", color="#d62728", lw=1.4, alpha=0.85)
    ax.fill_between(range(len(Y_row)), Y_row, P_row, color="#d62728", alpha=0.12)
    zt = power["vs_global"]["z"]
    ax.set_title(f"Power  RMSE={power['row_rmse']:.3f}  "
                 f"z={zt:+.2f}σ (vs history)  rank {power['global_rank']}/{power['n_rows']}"
                 if zt is not None else f"Power  RMSE={power['row_rmse']:.3f}")
    ax.set_xlabel("horizon step"); ax.set_ylabel("power"); ax.legend(fontsize=8); ax.grid(alpha=0.25)

    # (2) 特征 z 条形（红=显著偏高 z≥2，橙=略 1..2，灰=正常，蓝=偏低）
    ax = axes[0, 1]
    zs = [(r["z"] if r["z"] is not None else 0.0) for r in order]
    colors = []
    for z in zs:
        colors.append("#d62728" if z >= 2 else "#ff7f0e" if z >= 1
                      else "#4c72b0" if z <= -1 else "#b0b0b0")
    ax.barh(range(len(order)), zs, color=colors)
    ax.set_yticks(range(len(order)))
    ax.set_yticklabels([r["feature"] for r in order], fontsize=8)
    ax.invert_yaxis()
    ax.axvline(2, color="#d62728", ls="--", lw=1); ax.axvline(-2, color="#4c72b0", ls="--", lw=1)
    ax.set_title("Feature deviation z = (row − hist mean)/hist std   red≥2σ  orange≥1σ")
    ax.set_xlabel("z (σ above/below history)"); ax.grid(alpha=0.25, axis="x")

    # (3) 头号可疑特征 pred vs true
    ax = axes[1, 0]
    top = order[0]["feature"] if order else None
    if top:
        cc = pairs[top]
        pv = rc.to_matrix(ft_df.iloc[[ft_pos]], cc["pred"])[0]
        tv = rc.to_matrix(ft_df.iloc[[ft_pos]], cc["true"])[0]
        ax.plot(tv, label=f"{top} true", color="#1f77b4", lw=1.6)
        ax.plot(pv, label=f"{top} predicted", color="#d62728", lw=1.4, alpha=0.85)
        ax.fill_between(range(len(tv)), tv, pv, color="#d62728", alpha=0.12)
        z0 = order[0]["z"]
        ax.set_title(f"Top suspect '{top}'  RMSE={order[0]['row_rmse']:.3f}  "
                     + (f"z={z0:+.2f}σ ({order[0]['pctl_band']})" if z0 is not None else ""))
        ax.legend(fontsize=8)
    ax.set_xlabel("horizon step"); ax.grid(alpha=0.25)

    # (4) 功率误差沿时域剖面
    ax = axes[1, 1]
    ax.plot(np.abs(P_row - Y_row), color="#8c564b", lw=1.2)
    ax.fill_between(range(len(P_row)), 0, np.abs(P_row - Y_row), color="#8c564b", alpha=0.15)
    ax.set_title("Power abs error along horizon (where in 48h it drifts)")
    ax.set_xlabel("horizon step"); ax.set_ylabel("|pred − true|"); ax.grid(alpha=0.25)

    fig.tight_layout(rect=[0, 0, 1, 0.97])
    path = os.path.join(out_dir, f"{prefix}_{ts_tag}_dashboard.png")
    fig.savefig(path, dpi=110); plt.close(fig)
    return [path]


if __name__ == "__main__":
    main()
