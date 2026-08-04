#!/usr/bin/env python3
"""单行诊断（per-row feature blame）——给定一个窗口时间戳，输出该行的完整特征归因。

回答的问题（对**一行**）：这行预测有多坏（全局排第几）？哪个特征坏、坏到什么程度、
行内排名第几、够不够格被点名？并出图佐证。

⚠️ 纪律（与 SKILL.md 一致，单行诊断尤其吃紧）：
  1. **单行 = 样本量 1**：结论最高只能到「现象」。z 分数与全局 ρ 都是拿**全体行**做基线
     算出来的（这行只提供自己的特征误差，总体提供校准），单行本身证不了因果——反事实
     （Stage 4）才是唯一仲裁。JSON/图里都标注这一点。
  2. **两关点名**沿用 feature_blame：z ≥ z_hi 且 全局 ρ ≥ spearman_min 且 行内进 top_k
     且可约（reducibility ≥ 阈）且未被补偿（sys_frac < 阈）。误差大但全局无关的诱饵不点名。
  3. **共线簇内不单点名**：报簇，图里灰显同簇成员。
  4. 误差源默认 ε_res（读 Stage 1.5 的 feature_decomp.json + eps_res_*.npy）；缺则回退
     原始 ε 并打印警示（decomp=off，两道分解闸放行）。

用法（工作目录下，Stage 0（probe→feature_pairs.json）就位；ε_res 需 Stage 1.5 产物）：
  python3 <SKILL>/scripts/analyze_row.py --row "2025-01-02 09:00:00"   # 指定时间戳
  python3 <SKILL>/scripts/analyze_row.py --worst                        # 该口径×焦点模型最坏行
  [--metric rmse_192] [--model auto|pred_M1] [--feature-true F.parquet]
  [--z-hi 2.0 --spearman-min 0.3 --top-k 3 --reducibility-min 0.1 --sys-frac-max 0.85]
  [--no-plots] [--out-dir . --prefix row]

产物：<prefix>_<ts>.csv（该行 × 全模型 × 全特征：feature_err/z/rank/rho/blame_score/verdict…）
      <prefix>_<ts>.json（焦点模型的行画像 + 被点名清单 + 逐特征 + 免责声明）
      <prefix>_<ts>_dashboard.png（功率序列 / 特征归因条 / 行误差分布 / z–ρ 散点 四联）
      <prefix>_<ts>_culprit_<feat>.png（头号嫌疑特征 pred vs true 序列，逐点看哪里报错）
"""
from __future__ import annotations

import argparse
import os
import sys

import numpy as np
import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import fb_common as fb  # noqa: E402
from feature_blame import collinearity_clusters  # noqa: E402  复用同一共线簇定义
from probe_schema import discover_models  # noqa: E402


# ---------------------------------------------------------------- ε_res 载入（与 feature_blame 同规矩）
def load_residual_mats(raw_mats: dict, n_rows: int):
    """返回 (err_mats, decomp_meta, mode)。decomp=on 时读 eps_res_<feat>.npy 覆盖 raw。"""
    dec = fb.read_json("feature_decomp.json")
    if not dec:
        print("  ⚠ 未找到 feature_decomp.json —— 回退原始 ε（decomp=off；spec 建议先跑 Stage 1.5）")
        return raw_mats, {}, "off"
    if int(dec.get("n_rows", -1)) != n_rows:
        raise SystemExit("feature_decomp.json 行数与 feature_true 不符——分解产物过期，先重跑 feature_decompose.py。")
    res = {}
    for feat in raw_mats:
        p = f"eps_res_{fb.sanitize(feat)}.npy"
        if not os.path.exists(p):
            raise SystemExit(f"缺 {p}——分解产物不全，先重跑 feature_decompose.py。")
        res[feat] = np.load(p)
    return res, dec.get("features", {}), "on"


def gate_reason(z, rho, rank_f, score, reducible, compensated, args):
    """点名失败时给出人类可读原因（图与 JSON 共用）。返回 '' 表示通过（被点名）。"""
    if compensated:
        return "compensated (sys_frac high — model absorbs stable bias)"
    if not reducible:
        return "irreducible (near white-noise — upstream can't fix)"
    reasons = []
    if z < args.z_hi:
        reasons.append(f"z {z:.2f} < {args.z_hi}")
    if rho < args.spearman_min:
        reasons.append(f"global ρ {rho:.2f} < {args.spearman_min}")
    if rank_f > args.top_k:
        reasons.append(f"row-rank {rank_f} > top_{args.top_k}")
    if score <= 0:
        reasons.append("score ≤ 0")
    return "; ".join(reasons) if reasons else ""


def analyze_model(model, target_ts, ft_ts, ft_index, err_mats, raw_mats, sl,
                  red_frac, sys_frac, pred_df, test_df, metric, args):
    """对单个模型算该行的逐特征画像。返回 dict 或 None（该行不在此模型的对齐集中）。"""
    d = fb.require_du()
    ts, P, Y = d.align(pred_df, test_df, model)
    sel, err = fb.row_errors(ts, P, Y, metric)
    ts_sel = pd.DatetimeIndex(ts)[sel]
    rowerr_by_ts = dict(zip(ts_sel, err))

    # 总体 = 既在 feature_true 又在该模型对齐集里的行（z / ρ 的公共基线）
    pop_idx, pop_ts = [], []
    for i, t in enumerate(ft_ts):
        if t in rowerr_by_ts:
            pop_idx.append(i)
            pop_ts.append(t)
    if target_ts not in rowerr_by_ts or target_ts not in ft_index:
        return None
    pop_idx = np.array(pop_idx)
    row_err_pop = np.array([rowerr_by_ts[t] for t in pop_ts], float)
    k = pop_ts.index(target_ts)                      # 目标行在总体里的位置

    fe_pop, fe_raw_pop, fe_full_pop, z_pop, rho = {}, {}, {}, {}, {}
    for feat, E in err_mats.items():
        Ep = E[pop_idx]
        fe = np.sqrt(np.nanmean(Ep[:, sl] ** 2, axis=1))
        fe_pop[feat] = fe
        fe_full_pop[feat] = np.sqrt(np.nanmean(Ep ** 2, axis=1))
        z_pop[feat] = fb.zscores(fe)
        rho[feat] = round(fb.spearman(row_err_pop, fe), 4)
    for feat, E in raw_mats.items():
        fe_raw_pop[feat] = np.sqrt(np.nanmean(E[pop_idx][:, sl] ** 2, axis=1))

    # 行内按 blame_score 排名（与 feature_blame 逐行 scored 同式）
    scored = sorted(((f, z_pop[f][k] * max(rho[f], 0.0)) for f in err_mats),
                    key=lambda kv: -kv[1])
    rank_of = {f: r for r, (f, _) in enumerate(scored, 1)}

    n = len(row_err_pop)
    row_rank = int(1 + np.sum(row_err_pop > row_err_pop[k]))
    row_pctl = round(float(np.mean(row_err_pop <= row_err_pop[k]) * 100), 1)
    is_bad = bool(fb.bad_mask(row_err_pop, args.top_pct)[k])

    feats = {}
    for feat in err_mats:
        z = float(z_pop[feat][k])
        score = float(z * max(rho[feat], 0.0))
        reducible = red_frac(feat) >= args.reducibility_min
        compensated = sys_frac(feat) >= args.sys_frac_max
        blamed = (z >= args.z_hi and rho[feat] >= args.spearman_min
                  and rank_of[feat] <= args.top_k and score > 0
                  and reducible and not compensated)
        fe = float(fe_pop[feat][k])
        fe_pctl = round(float(np.mean(fe_pop[feat] <= fe) * 100), 1)
        feats[feat] = {
            "feature_err": round(fe, 6),
            "feature_err_raw": round(float(fe_raw_pop[feat][k]), 6),
            "feature_err_sys": round(float(fe_raw_pop[feat][k] - fe), 6),
            "feature_err_full192": round(float(fe_full_pop[feat][k]), 6),
            "feature_err_z": round(z, 4),
            "feature_err_pctl": fe_pctl,
            "global_spearman": rho[feat],
            "reducibility_frac": round(float(red_frac(feat)), 4),
            "sys_frac": round(float(sys_frac(feat)), 4),
            "row_blame_rank": rank_of[feat],
            "blame_score": round(score, 4),
            "blamed": blamed,
            "gate_reason": "" if blamed else gate_reason(
                z, rho[feat], rank_of[feat], score, reducible, compensated, args),
        }

    clusters = collinearity_clusters(fe_pop)
    in_cluster = {f: c for c in clusters for f in c}
    named = [f for f in feats if feats[f]["blamed"]]
    # 共线簇内被点名 → 降级为「簇级」提示（不单点名）
    cluster_flags = {f: in_cluster.get(f) for f in named if f in in_cluster}

    return {
        "model": model, "metric": metric,
        "row_error": round(float(row_err_pop[k]), 6),
        "row_rank": row_rank, "row_pctl": row_pctl, "n_rows": n,
        "row_error_mean": round(float(np.nanmean(row_err_pop)), 6),
        "row_error_std": round(float(np.nanstd(row_err_pop)), 6),
        "is_bad_row": is_bad,
        "named_features": named,
        "collinearity_clusters": clusters,
        "named_in_cluster": cluster_flags,
        "features": feats,
        "_arrays": {  # 画图用，不进 JSON 摘要
            "P_row": P[np.where(pd.DatetimeIndex(ts) == target_ts)[0][0]],
            "Y_row": Y[np.where(pd.DatetimeIndex(ts) == target_ts)[0][0]],
            "row_err_pop": row_err_pop, "k": k,
        },
    }


# ---------------------------------------------------------------- 画图
def make_plots(focus, target_ts, ft, pairs, err_mats, raw_mats, sl, prefix, out_dir):
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

    d = fb.require_du()
    ts_tag = fb.sanitize(str(target_ts))
    arr = focus["_arrays"]
    feats = focus["features"]
    order = sorted(feats, key=lambda f: -feats[f]["blame_score"])

    fig, axes = plt.subplots(2, 2, figsize=(15, 10))
    fig.suptitle(f"Row diagnosis  {target_ts}   model={focus['model']}  metric={focus['metric']}",
                 fontsize=14, fontweight="bold")

    # (1) 功率 pred vs true
    ax = axes[0, 0]
    ax.plot(arr["Y_row"], label="true power", color="#1f77b4", lw=1.6)
    ax.plot(arr["P_row"], label="predicted", color="#d62728", lw=1.4, alpha=0.85)
    ax.fill_between(range(len(arr["Y_row"])), arr["Y_row"], arr["P_row"],
                    color="#d62728", alpha=0.12)
    ax.set_title(f"Power (192 steps)  row_error={focus['row_error']:.3f}  "
                 f"rank {focus['row_rank']}/{focus['n_rows']} (p{focus['row_pctl']})"
                 f"{'  [BAD ROW]' if focus['is_bad_row'] else ''}")
    ax.set_xlabel("horizon step"); ax.set_ylabel("power"); ax.legend(fontsize=8)
    ax.grid(alpha=0.25)

    # (2) 特征归因条：blame_score，红=点名 灰=被闸挡
    ax = axes[0, 1]
    scores = [feats[f]["blame_score"] for f in order]
    colors = []
    for f in order:
        if feats[f]["blamed"] and f in focus["named_in_cluster"]:
            colors.append("#ff7f0e")            # 点名但在共线簇 → 橙（簇级）
        elif feats[f]["blamed"]:
            colors.append("#d62728")            # 点名 → 红
        else:
            colors.append("#b0b0b0")            # 未点名 → 灰
    ax.barh(range(len(order)), scores, color=colors)
    ax.set_yticks(range(len(order)))
    ax.set_yticklabels([f"{f}  (z={feats[f]['feature_err_z']:.1f}, ρ={feats[f]['global_spearman']:.2f})"
                        for f in order], fontsize=8)
    ax.invert_yaxis()
    ax.set_title("Feature blame score = z × max(ρ,0)   "
                 "red=named  orange=named(collinear cluster)  grey=cleared")
    ax.set_xlabel("blame_score")
    ax.grid(alpha=0.25, axis="x")
    for i, f in enumerate(order):                # 未点名标原因
        if not feats[f]["blamed"] and feats[f]["gate_reason"]:
            ax.text(max(scores + [0.01]) * 0.02, i, feats[f]["gate_reason"],
                    va="center", fontsize=6, color="#555")

    # (3) 行误差分布 + 本行位置
    ax = axes[1, 0]
    pop = arr["row_err_pop"]
    ax.hist(pop, bins=min(30, max(8, len(pop) // 3)), color="#8fb3d9", edgecolor="white")
    ax.axvline(focus["row_error"], color="#d62728", lw=2,
               label=f"this row (p{focus['row_pctl']})")
    ax.axvline(focus["row_error_mean"], color="#333", ls="--", lw=1, label="mean")
    ax.set_title("Where this row sits in the global row-error distribution")
    ax.set_xlabel(f"{focus['metric']} row error"); ax.set_ylabel("rows"); ax.legend(fontsize=8)
    ax.grid(alpha=0.25)

    # (4) z vs ρ 散点（两关门槛画线）
    ax = axes[1, 1]
    for f in order:
        z, rho = feats[f]["feature_err_z"], feats[f]["global_spearman"]
        c = "#d62728" if feats[f]["blamed"] else "#b0b0b0"
        ax.scatter(rho, z, color=c, s=45, zorder=3)
        ax.annotate(f, (rho, z), fontsize=7, xytext=(3, 3), textcoords="offset points")
    ax.axhline(focus.get("_z_hi", 2.0), color="#888", ls="--", lw=1)
    ax.axvline(focus.get("_rho_min", 0.3), color="#888", ls="--", lw=1)
    ax.set_title("Two gates: named must be top-right (z≥z_hi & ρ≥ρ_min)")
    ax.set_xlabel("global Spearman ρ (feature err vs row err)")
    ax.set_ylabel("feature_err z (this row vs population)")
    ax.grid(alpha=0.25)

    fig.tight_layout(rect=[0, 0, 1, 0.97])
    dash = os.path.join(out_dir, f"{prefix}_{ts_tag}_dashboard.png")
    fig.savefig(dash, dpi=110); plt.close(fig)

    # 头号嫌疑（或最高分特征）的 pred vs true 序列
    culprit = focus["named_features"][0] if focus["named_features"] else order[0]
    pair = next(p for p in pairs if p["feature"] == culprit)
    ft_pos = np.where(pd.DatetimeIndex(ft[d.TIMESTAMP_COL]) == target_ts)[0][0]
    pv = d.to_matrix(ft, pair["pred_col"])[ft_pos]
    tv = d.to_matrix(ft, pair["label_col"])[ft_pos]
    fig2, ax = plt.subplots(figsize=(11, 4.5))
    ax.plot(tv, label=f"{culprit} true", color="#1f77b4", lw=1.6)
    ax.plot(pv, label=f"{culprit} predicted", color="#d62728", lw=1.4, alpha=0.85)
    ax.fill_between(range(len(tv)), tv, pv, color="#d62728", alpha=0.12)
    verdict = "NAMED" if focus["named_features"] else f"not named ({feats[culprit]['gate_reason']})"
    ax.set_title(f"Top suspect '{culprit}' pred vs true  [{verdict}]   "
                 f"feature_err={feats[culprit]['feature_err']:.3f} "
                 f"(z={feats[culprit]['feature_err_z']:.2f}, p{feats[culprit]['feature_err_pctl']}), "
                 f"ρ={feats[culprit]['global_spearman']:.2f}")
    ax.set_xlabel("horizon step"); ax.set_ylabel(culprit); ax.legend(fontsize=9)
    ax.grid(alpha=0.25)
    fig2.tight_layout()
    cul = os.path.join(out_dir, f"{prefix}_{ts_tag}_culprit_{fb.sanitize(culprit)}.png")
    fig2.savefig(cul, dpi=110); plt.close(fig2)
    return [dash, cul]


def main():
    cfg = fb.config_or_empty()
    blame_cfg = cfg.get("blame", {})
    dcfg = cfg.get("decompose", {})
    ap = argparse.ArgumentParser()
    ap.add_argument("--row", help="窗口时间戳，如 '2025-01-02 09:00:00'")
    ap.add_argument("--worst", action="store_true", help="取该口径×焦点模型误差最大的行")
    ap.add_argument("--metric", default=(cfg.get("metrics") or ["rmse_192"])[0])
    ap.add_argument("--model", default="auto", help="auto=全部模型；焦点=第一个或最坏行所属")
    ap.add_argument("--feature-true", default=cfg.get("feature_true"))
    ap.add_argument("--test", default=cfg.get("test_label"))
    ap.add_argument("--predict", default=cfg.get("predict"))
    ap.add_argument("--pairs", default="feature_pairs.json")
    ap.add_argument("--top-pct", type=float, default=cfg.get("top_pct", 10))
    ap.add_argument("--z-hi", type=float, default=blame_cfg.get("z_hi", 2.0))
    ap.add_argument("--spearman-min", type=float, default=blame_cfg.get("spearman_min", 0.3))
    ap.add_argument("--top-k", type=int, default=blame_cfg.get("top_k", 3))
    ap.add_argument("--reducibility-min", type=float, default=dcfg.get("reducibility_min", 0.1))
    ap.add_argument("--sys-frac-max", type=float, default=dcfg.get("sys_frac_max", 0.85))
    ap.add_argument("--use-residual", action=argparse.BooleanOptionalAction,
                    default=dcfg.get("enabled", True))
    ap.add_argument("--no-plots", action="store_true")
    ap.add_argument("--out-dir", default=".")
    ap.add_argument("--prefix", default="row")
    args = ap.parse_args()
    if not args.row and not args.worst:
        raise SystemExit("给一个行：--row '<时间戳>' 或 --worst。")
    for name, val in (("--feature-true", args.feature_true), ("--test", args.test),
                      ("--predict", args.predict)):
        if not val:
            raise SystemExit(f"缺 {name}（或先写 blame_config.json）。feature_true 没有就先问用户——绝不静默降级。")

    d = fb.require_du()
    pairs = (fb.read_json(args.pairs) or {}).get("pairs") or []
    if not pairs:
        raise SystemExit(f"{args.pairs} 无特征对——先跑 Stage 0 probe_schema.py。")

    ft, _ = fb.load_any(args.feature_true)
    ft_ts = pd.DatetimeIndex(ft[d.TIMESTAMP_COL])
    ft_index = {t: i for i, t in enumerate(ft_ts)}
    raw_mats = fb.eps_matrices(ft, pairs)
    err_mats, decomp_meta, decomp_mode = (raw_mats, {}, "off")
    if args.use_residual:
        err_mats, decomp_meta, decomp_mode = load_residual_mats(raw_mats, len(ft))

    def red_frac(feat):
        if decomp_mode != "on":
            return 1.0
        v = (decomp_meta.get(feat) or {}).get("reducibility")
        return float(v) if v is not None else 1.0

    def sys_frac(feat):
        if decomp_mode != "on":
            return 0.0
        v = (decomp_meta.get(feat) or {}).get("sys_frac")
        return float(v) if v is not None else 0.0

    test_df, _ = fb.load_any(args.test)
    pred_df, _ = fb.load_any(args.predict)
    models = (discover_models(fb.list_columns(pred_df), d.HORIZON)
              if args.model == "auto" else [args.model])
    if not models:
        raise SystemExit("predict 里找不到模型列（192 点 list 列）。")
    slices = fb.metric_slices()
    sl = slices[args.metric]

    # 解析目标行：--worst 用焦点模型（首个）最坏行；否则解析时间戳
    focus_model = models[0]
    if args.worst:
        ts, P, Y = d.align(pred_df, test_df, focus_model)
        sel, err = fb.row_errors(ts, P, Y, args.metric)
        target_ts = pd.DatetimeIndex(ts)[sel][int(np.argmax(err))]
    else:
        target_ts = pd.Timestamp(args.row)
    if target_ts not in ft_index:
        raise SystemExit(f"时间戳 {target_ts} 不在 feature_true 里。可用范围 "
                         f"{ft_ts.min()} .. {ft_ts.max()}（{len(ft_ts)} 行）。")

    per_model = {}
    for m in models:
        res = analyze_model(m, target_ts, ft_ts, ft_index, err_mats, raw_mats, sl,
                            red_frac, sys_frac, pred_df, test_df, args.metric, args)
        if res is not None:
            per_model[m] = res
    if not per_model:
        raise SystemExit(f"行 {target_ts} 不在任何模型的对齐集里（predict∩test 无此时间戳）。")
    focus = per_model.get(focus_model) or next(iter(per_model.values()))
    focus["_z_hi"], focus["_rho_min"] = args.z_hi, args.spearman_min

    # ---- CSV：该行 × 全模型 × 全特征
    rows = []
    for m, r in per_model.items():
        for feat, v in r["features"].items():
            rows.append({"timestamp_win": target_ts, "model": m, "metric": args.metric,
                         "row_error": r["row_error"], "row_rank": r["row_rank"],
                         "row_pctl": r["row_pctl"], "is_bad_row": r["is_bad_row"],
                         "feature": feat, **{k: v[k] for k in
                         ("feature_err", "feature_err_raw", "feature_err_sys",
                          "feature_err_full192", "feature_err_z", "feature_err_pctl",
                          "global_spearman", "reducibility_frac", "sys_frac",
                          "row_blame_rank", "blame_score", "blamed", "gate_reason")}})
    ts_tag = fb.sanitize(str(target_ts))
    csv_path = os.path.join(args.out_dir, f"{args.prefix}_{ts_tag}.csv")
    pd.DataFrame(rows).sort_values(["model", "blame_score"], ascending=[True, False]).to_csv(
        csv_path, index=False)

    # ---- JSON 摘要（焦点模型 + 各模型 row_error 一览 + 免责声明）
    clean = {m: {k: v for k, v in r.items() if k != "_arrays"} for m, r in per_model.items()}
    summary = {
        "timestamp_win": str(target_ts),
        "selector": "worst" if args.worst else "explicit",
        "focus_model": focus_model,
        "params": {"metric": args.metric, "z_hi": args.z_hi, "spearman_min": args.spearman_min,
                   "top_k": args.top_k, "reducibility_min": args.reducibility_min,
                   "sys_frac_max": args.sys_frac_max, "top_pct": args.top_pct,
                   "decomp": decomp_mode},
        "row_error_by_model": {m: {"row_error": r["row_error"], "row_rank": r["row_rank"],
                                   "row_pctl": r["row_pctl"], "is_bad_row": r["is_bad_row"],
                                   "named_features": r["named_features"]}
                               for m, r in per_model.items()},
        "focus": {k: clean[focus_model][k] for k in
                  ("model", "metric", "row_error", "row_rank", "row_pctl", "n_rows",
                   "is_bad_row", "named_features", "collinearity_clusters",
                   "named_in_cluster", "features")},
        "evidence_level": "phenomenon",
        "caveats": [
            "单行 = 样本量 1：结论最高只能到「现象」。z 与全局 ρ 是拿全体行做基线算的，"
            "单行本身证不了因果。",
            "点名过两关（z≥z_hi 且全局 ρ≥ρ_min）+ 可约性/洗清闸；误差大但全局无关的诱饵不点名。",
            "共线簇内不单点名（named_in_cluster 标出）；簇内定罪只能靠 Stage 4 反事实逐个替换。",
            "「已证实」唯一通道 = Stage 4 反事实（把被点名特征换真值重预测，看该行指标是否变好）。",
        ],
    }
    if decomp_mode == "off":
        summary["caveats"].append("decomp=off：未剥系统偏差 ε_sys，可能冤枉被模型补偿的稳定偏差"
                                  "（先跑 Stage 1.5 feature_decompose.py）。")
    json_path = os.path.join(args.out_dir, f"{args.prefix}_{ts_tag}.json")
    fb.dump_json(json_path, summary)

    imgs = []
    if not args.no_plots:
        try:
            imgs = make_plots(focus, target_ts, ft, pairs, err_mats, raw_mats, sl,
                              args.prefix, args.out_dir)
        except ImportError:
            print("  ⚠ 未装 matplotlib，跳过出图（pip install matplotlib）。")

    # ---- 终端摘要（≤30 行）
    f = focus
    print(f"[analyze_row] {target_ts}   焦点模型 {focus_model}  口径 {args.metric}  decomp={decomp_mode}")
    print(f"  行误差 {f['row_error']:.4f}  全局排名 {f['row_rank']}/{f['n_rows']} "
          f"(p{f['row_pctl']})  {'★坏行' if f['is_bad_row'] else '正常行'}")
    print(f"  被点名特征: {f['named_features'] or '无（本行无特征过两关）'}")
    if f["named_in_cluster"]:
        print(f"  ⚠ 其中在共线簇内（不单点名，报簇）: {f['named_in_cluster']}")
    order = sorted(f["features"], key=lambda x: -f["features"][x]["blame_score"])
    print("  逐特征（按 blame_score 降序，前 5）:")
    for feat in order[:5]:
        v = f["features"][feat]
        tag = "点名" if v["blamed"] else f"洗清:{v['gate_reason']}"
        print(f"    {feat:16s} score={v['blame_score']:6.2f} z={v['feature_err_z']:5.2f} "
              f"ρ={v['global_spearman']:5.2f} err={v['feature_err']:.3f}(p{v['feature_err_pctl']}) [{tag}]")
    print(f"  证据级别: 现象（单行样本量 1；已证实须过 Stage 4 反事实）")
    print(f"  产物: {csv_path}  {json_path}" + ("  " + "  ".join(imgs) if imgs else ""))


if __name__ == "__main__":
    main()
