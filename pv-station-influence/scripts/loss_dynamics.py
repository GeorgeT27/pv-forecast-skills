#!/usr/bin/env python3
"""Stage 1 —— 训练动力学：为什么不同 (迭代, chunk) 的 training loss 不同。

对每个 chunk 提取 final_loss（尾 k epoch 均值）/ conv_slope（log-loss~epoch 斜率）/
plateau_epoch，再把这些指标回归到 17 站成员上（与 Stage 2 完全同款的中心化+岭设计，
复用 influence_regression 的实现）——"含站 s 的 chunk 终态 loss 更高 / 收敛更慢"
就是站 s 的 loss 效应。最后（若 rmse_series.csv 在）报 loss 指标与留出站 ΔRMSE 的
Spearman 关联，回答"高 loss chunk 是否与 RMSE 跳升同现"。

⚠️ 结论纪律：**loss 高 ≠ 有罪**。loss 是训练站自己身上的量——站的 loss 效应说明
它"难学"（数据脏/分布难拟合/容量异质），**不是**留出站负迁移排名，禁止直接当
harm 榜用。四象限解读与 station.md 连接流程见 references/influence-methods.md
「Stage 1 训练动力学」节。M1–M4 损失函数/量纲不同 ⇒ 逐模型独立回归、
**绝不跨模型 pool loss**，跨模型只比 Spearman 排名。

输入（工作目录）：
  loss_records.csv  : iteration,chunk,position,model,epoch,loss（日志解析或 --from-ckpt 产出）
  assignments.csv   : Stage 0 产物（chunk 组成）
  rmse_series.csv   : 可选；在则做 loss×ΔRMSE 关联
输出：
  chunk_loss_curves.csv    : 逐 (model,iteration,chunk) 的 loss 指标明细（人/复查用）
  chunk_loss_dynamics.json : 自足摘要（站效应 θ + CI + 排名 + rmse_link + 功效提示）

用法：
  python <skill>/scripts/loss_dynamics.py                 # 读 loss_records.csv 做主分析
  python <skill>/scripts/loss_dynamics.py --from-ckpt     # Mode B：adapter.load_loss_history
                                                          #   逐 checkpoint 抽 loss 追加
                                                          #   loss_records.csv（可中断续跑）
  python <skill>/scripts/loss_dynamics.py --lam 1.0 --tail-k 3 --boot 1000
"""
from __future__ import annotations

import argparse
import gc
import os
import sys

import numpy as np
import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import si_common as sic
import influence_regression as ir  # 复用 _design/_fit_ridge/_delta_rmse（单一实现，不复制）

RECORDS = "loss_records.csv"
CURVES = "chunk_loss_curves.csv"
OUT = "chunk_loss_dynamics.json"


# ---------------------------------------------------------------- Mode B 补料
def from_ckpt(cfg, args):
    """遍历 (model, iter, pos)，用 adapter.load_loss_history 从 checkpoint 抽 loss 历史，
    追加 loss_records.csv。纪律同 ckpt_eval：顺序 load→读小标量→释放，权重不进对话。"""
    adapter = sic.load_adapter()
    if not hasattr(adapter, "load_loss_history"):
        sys.exit("adapter.py 未实现 load_loss_history（可选函数，见 adapter_template.py）。"
                 "没有它且日志无 loss 记录 → Stage 1 跳过。")
    models = (args.models.split(",") if args.models else cfg.get("models")) or ["M1", "M2", "M3", "M4"]
    n_iters = int((cfg.get("sampler") or {}).get("n_iters") or 0)
    if n_iters <= 0:
        sys.exit("config.sampler.n_iters 缺失。")
    layout = cfg.get("chunk_layout") or {"n_chunks": 4}
    n_chunks = int(layout.get("n_chunks", 4))

    done = set()
    if os.path.exists(RECORDS):
        d = pd.read_csv(RECORDS)
        done = set(zip(d["model"], d["iteration"], d["position"]))
    n_new, n_none = 0, 0
    for model in models:
        for it in range(1, n_iters + 1):
            for pos in range(1, n_chunks + 1):
                if (model, it, pos) in done:
                    continue
                if hasattr(adapter, "locate_checkpoint"):
                    ckpt = adapter.locate_checkpoint(model, it, pos, cfg)
                else:
                    ckpt = os.path.join(cfg["checkpoint_dir"],
                                        args.pattern.format(model=model, it=it, pos=pos, chunk=pos))
                if not os.path.exists(ckpt):
                    print(f"  [skip] 缺 checkpoint: {ckpt}")
                    continue
                hist = adapter.load_loss_history(model, ckpt)
                if not hist:
                    n_none += 1
                    continue
                rows = [{"iteration": it, "chunk": pos, "position": pos,
                         "model": model, "epoch": int(e), "loss": float(l)}
                        for e, l in hist]
                pd.DataFrame(rows).to_csv(RECORDS, mode="a",
                                          header=not os.path.exists(RECORDS), index=False)
                n_new += len(rows)
                gc.collect()
    print(f"--from-ckpt 完成：新增 {n_new} 行 → {RECORDS}"
          f"（{n_none} 个 checkpoint 未存 loss 历史）。")
    if n_new == 0 and not os.path.exists(RECORDS):
        sys.exit("没有任何 checkpoint 存了 loss 历史 → Stage 1 跳过（orient 不阻塞）。")


# ---------------------------------------------------------------- 逐 chunk 指标
def chunk_metrics(recs: pd.DataFrame, tail_k: int) -> pd.DataFrame:
    """逐 (model, iteration, chunk) 提取 final_loss / start_loss / conv_slope / plateau_epoch。"""
    rows = []
    for (model, it, ch), g in recs.groupby(["model", "iteration", "chunk"]):
        g = g.sort_values("epoch")
        loss = g["loss"].to_numpy(float)
        ep = g["epoch"].to_numpy(float)
        pos = int(g["position"].iloc[0])
        if len(loss) < 2 or not np.isfinite(loss).all() or (loss <= 0).any():
            # loss<=0 无法取 log（异常记录），跳过并留痕
            rows.append({"model": model, "iteration": int(it), "chunk": int(ch),
                         "position": pos, "n_epochs": len(loss), "final_loss": np.nan,
                         "start_loss": np.nan, "conv_slope": np.nan, "plateau_epoch": np.nan})
            continue
        final = float(loss[-tail_k:].mean())
        # log-loss ~ epoch 的 OLS 斜率（尺度稳健；负得越多=收敛越快）
        slope = float(np.polyfit(ep, np.log(loss), 1)[0])
        plateau = int(ep[np.argmax(loss <= final * 1.05)])  # 首个进入 final±5% 的 epoch
        rows.append({"model": model, "iteration": int(it), "chunk": int(ch),
                     "position": pos, "n_epochs": len(loss),
                     "final_loss": round(final, 6), "start_loss": round(float(loss[0]), 6),
                     "conv_slope": round(slope, 6), "plateau_epoch": plateau})
    return pd.DataFrame(rows)


# ---------------------------------------------------------------- 站效应回归（复用 Stage 2 设计）
def station_effect(cm: pd.DataFrame, key2mem, station_list, yvar, lam, boot, rng_seed=0):
    """把 chunk 级指标 yvar 回归到站成员（中心化+岭+控制），返回 (theta, lo, hi, n_obs) 或 None。

    设计矩阵构造直接走 influence_regression._build_xy——rows 的第 4 元换成 yvar。"""
    sub = cm.dropna(subset=[yvar])
    rows = list(zip(sub["iteration"].astype(int), sub["chunk"].astype(int),
                    sub["position"].astype(int), sub[yvar].astype(float)))
    X, y = ir._build_xy(rows, key2mem, len(station_list))
    if len(y) < 3:
        return None
    beta = ir._fit_ridge(X, y, lam)
    n_st = len(station_list)
    theta = beta[1:1 + n_st]
    bs = np.zeros((boot, n_st))
    idxs = np.arange(len(y))
    for b in range(boot):
        samp = np.random.default_rng(rng_seed + b).choice(idxs, len(idxs), replace=True)
        bs[b] = ir._fit_ridge(X[samp], y[samp], lam)[1:1 + n_st]
    lo, hi = np.percentile(bs, [2.5, 97.5], axis=0)
    return theta, lo, hi, len(y)


def _pack(theta, lo, hi, station_list, higher_is=None):
    order = np.argsort(theta)[::-1]
    return {
        "theta": {station_list[i]: round(float(theta[i]), 6) for i in order},
        "ci95": {station_list[i]: [round(float(lo[i]), 6), round(float(hi[i]), 6)] for i in order},
        "ranking": [station_list[i] for i in order],
        "ci_excludes_zero": [station_list[i] for i in order if lo[i] > 0 or hi[i] < 0],
        "note": higher_is,
    }


# ---------------------------------------------------------------- 主流程
def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--from-ckpt", action="store_true",
                    help="Mode B：先从 checkpoint 抽 loss 历史补 loss_records.csv 再分析")
    ap.add_argument("--models", default=None)
    ap.add_argument("--pattern", default="{model}/iter{it}_chunk{pos}.pt")
    ap.add_argument("--lam", type=float, default=1.0)
    ap.add_argument("--boot", type=int, default=1000)
    ap.add_argument("--tail-k", type=int, default=3, help="final_loss 取尾部 k 个 epoch 均值")
    args = ap.parse_args()

    cfg = sic.load_config()
    if args.from_ckpt:
        from_ckpt(cfg, args)

    if not os.path.exists(RECORDS):
        sys.exit(f"缺 {RECORDS} —— 日志有 loss 就按 probe_summary.json 样例行写解析器落它；"
                 "没有且 Mode B 可 --from-ckpt；都不行则 Stage 1 跳过（不阻塞后续阶段）。")
    if not os.path.exists("assignments.csv"):
        sys.exit("缺 assignments.csv —— 先跑 Stage 0（replay_assignments.py）。")

    station_list = sic.stations(cfg)
    recs = pd.read_csv(RECORDS)
    asg = pd.read_csv("assignments.csv")
    key2mem = ir._design(asg, station_list)

    cm = chunk_metrics(recs, args.tail_k)
    cm.to_csv(CURVES, index=False)
    models = [m for m in (cfg.get("models") or ["M1", "M2", "M3", "M4"])
              if m in set(cm["model"])]
    skipped_models = [m for m in (cfg.get("models") or ["M1", "M2", "M3", "M4"])
                      if m not in set(cm["model"])]

    n_iters = int(recs["iteration"].nunique())
    out = {"n_iterations": n_iters, "tail_k": args.tail_k, "lambda": args.lam,
           "n_boot": args.boot, "stations": station_list, "per_model": {},
           "models_without_loss": skipped_models,
           "power_note": ("迭代数 < 10：只报排名，不下显著性结论" if n_iters < 10
                          else f"迭代数 {n_iters}：CI 排除 0 的站可报为'现象'（仍需过反驳门）"),
           "discipline_note": ("loss 效应=机制线索（该站难学），非留出站负迁移排名；"
                               "解读须结合 station.md 气候/容量/数据质量与 influence-methods.md 四象限")}

    theta_by_model = {}
    rmse_d = None
    if os.path.exists("rmse_series.csv"):
        rmse_d = ir._delta_rmse(pd.read_csv("rmse_series.csv"))

    for model in models:
        sub = cm[cm["model"] == model]
        entry = {"n_chunks": int(len(sub))}
        lvl = station_effect(sub, key2mem, station_list, "final_loss", args.lam, args.boot)
        slp = station_effect(sub, key2mem, station_list, "conv_slope", args.lam, args.boot)
        if lvl:
            entry["loss_level"] = _pack(*lvl[:3], station_list,
                                        higher_is="θ 高 = 含它的 chunk 终态 loss 更高（相对平均站）")
            entry["loss_level"]["n_obs"] = lvl[3]
            entry["highest_final_loss_stations"] = entry["loss_level"]["ranking"][:3]
        if slp:
            entry["conv_slope"] = _pack(*slp[:3], station_list,
                                        higher_is="θ 高 = 含它的 chunk 收敛更慢（斜率更接近 0）")
            entry["conv_slope"]["n_obs"] = slp[3]
            entry["slowest_converging_stations"] = entry["conv_slope"]["ranking"][:3]
        if lvl:
            theta_by_model[model] = lvl[0]

        # 与留出站 RMSE 震荡的关联（同现证据，非定罪）
        if rmse_d is not None:
            j = sub.merge(rmse_d[rmse_d["model"] == model],
                          on=["model", "iteration", "position"], how="inner")
            j = j.dropna(subset=["final_loss", "drmse"])
            if len(j) >= 5:
                try:
                    from scipy.stats import spearmanr
                    r1, p1 = spearmanr(j["final_loss"], j["drmse"])
                    r2, p2 = spearmanr(j["conv_slope"], j["drmse"])
                    topq = j["final_loss"].quantile(0.75)
                    top5 = j.nlargest(5, "drmse")
                    entry["rmse_link"] = {
                        "n": int(len(j)),
                        "spearman_final_vs_drmse": round(float(r1), 3), "p_final": round(float(p1), 4),
                        "spearman_slope_vs_drmse": round(float(r2), 3), "p_slope": round(float(p2), 4),
                        "top5_drmse_chunks_in_top_quartile_loss": int((top5["final_loss"] >= topq).sum()),
                    }
                except Exception:
                    pass
        out["per_model"][model] = entry

    # 跨模型排名一致性（loss 量纲不可比 ⇒ 只比 Spearman）
    if len(theta_by_model) >= 2:
        try:
            from scipy.stats import spearmanr
            names = list(theta_by_model)
            sp = {}
            for a in range(len(names)):
                for b in range(a + 1, len(names)):
                    r, _ = spearmanr(theta_by_model[names[a]], theta_by_model[names[b]])
                    sp[f"{names[a]}~{names[b]}"] = round(float(r), 3)
            out["cross_model_spearman"] = sp
        except Exception:
            pass

    sic.dump_json(OUT, out)

    # ≤30 行摘要
    print("=" * 56)
    print(f"Stage 1 训练动力学  迭代数={n_iters}  tail_k={args.tail_k}  λ={args.lam}")
    print(f"  {out['power_note']}")
    if skipped_models:
        print(f"  ⚠ 无 loss 记录的模型（未分析）: {skipped_models}")
    for m, e in out["per_model"].items():
        hi = e.get("highest_final_loss_stations", "—")
        sl = e.get("slowest_converging_stations", "—")
        print(f"  [{m}] n_chunks={e['n_chunks']}  终态loss最高前三: {hi}  收敛最慢前三: {sl}")
        if "rmse_link" in e:
            rl = e["rmse_link"]
            print(f"        ×ΔRMSE 同现: spearman={rl['spearman_final_vs_drmse']}(p={rl['p_final']})"
                  f"  ΔRMSE前5落在高loss四分位: {rl['top5_drmse_chunks_in_top_quartile_loss']}/5")
    if "cross_model_spearman" in out:
        print(f"  跨模型排名一致性 Spearman: {out['cross_model_spearman']}")
    print("  ⚠ loss 高≠有罪：以上是'难学'排名，非负迁移排名（见 influence-methods.md 四象限）。")
    print(f"→ {OUT} / {CURVES} 已写。下一步：Stage 2 影响力回归。")
    print("=" * 56)


if __name__ == "__main__":
    main()
