#!/usr/bin/env python3
"""Stage 0：schema 探查与对齐守卫。

三件套（test / predict / feature_true）各自探：时间戳列名、list 列清单与长度、
predict 的模型列（1..N 个 192 点列都算）、feature_true 的 (预测列, 真值列) 配对
（启发式配不上的进 unmapped —— 主 agent 拿去 AskUserQuestion，答案写回 feature_pairs.json）。
再做三道守卫：
  1) 三文件时间戳对齐（inner-join 计数；0 偏移对不上时试 ±672 步再报 warning）；
  2) 滚动窗一致性抽查（复用 data_utils.check_window_consistency；只查**真值列**——
     predict/预报特征逐行重新起报，行间不一致是预期物理，不进闸；>0 = 窗口构造有 bug，全链不可信）;
  3) 特征真值交叉核验：feature_true 的 label 序列 vs test.parquet 同名特征列的
     历史段（窗口重叠：后行历史段 = 前行未来段的观测值）——对不齐说明对齐错位或 label 有假。

用法（在工作目录下；缺省从 blame_config.json 取路径）：
  python3 <SKILL>/scripts/probe_schema.py \
      [--test T.parquet --predict P.parquet --feature-true F.parquet] \
      [--n-overlap-checks 200] [--out probe_schema.json] [--pairs-out feature_pairs.json]
"""
from __future__ import annotations

import argparse
import os
import sys

import numpy as np
import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import fb_common as fb  # noqa: E402

# ---------------------------------------------------------------- 配对启发式
PRED_SUFFIXES = ("_pred", "_predict", "_prediction", "_forecast", "_fcst", "_fc", "_nwp")
PRED_PREFIXES = ("pred_", "predict_", "prediction_", "forecast_", "fc_", "nwp_")
LABEL_SUFFIXES = ("_true", "_label", "_obs", "_observe", "_actual", "_real")
LABEL_PREFIXES = ("true_", "label_", "obs_", "actual_", "real_")


def normalize_col(col: str) -> tuple[str, set[str]]:
    """迭代剥掉预测/真值记号（前缀或后缀，可多层，如 nwp_ghi_fc → ghi），
    返回 (词干, 记号种类集合)。两类记号都出现 → 调用方按歧义处理。"""
    stem, kinds = col, set()
    changed = True
    while changed:
        changed = False
        low = stem.lower()
        for suf in PRED_SUFFIXES:
            if low.endswith(suf) and len(stem) > len(suf):
                stem, kinds, changed = stem[: -len(suf)], kinds | {"pred"}, True
                break
        if changed:
            continue
        for suf in LABEL_SUFFIXES:
            if low.endswith(suf) and len(stem) > len(suf):
                stem, kinds, changed = stem[: -len(suf)], kinds | {"label"}, True
                break
        if changed:
            continue
        for pre in PRED_PREFIXES:
            if low.startswith(pre) and len(stem) > len(pre):
                stem, kinds, changed = stem[len(pre):], kinds | {"pred"}, True
                break
        if changed:
            continue
        for pre in LABEL_PREFIXES:
            if low.startswith(pre) and len(stem) > len(pre):
                stem, kinds, changed = stem[len(pre):], kinds | {"label"}, True
                break
    return stem, kinds


def discover_pairs(cols) -> tuple[list[dict], list[str]]:
    """feature_true 的候选列 → (pairs, unmapped)。pair = 同词干下恰好一预测一真值。"""
    by_stem: dict[str, dict[str, list[str]]] = {}
    ambiguous = []
    for c in cols:
        stem, kinds = normalize_col(c)
        if kinds == {"pred"}:
            by_stem.setdefault(stem, {}).setdefault("pred", []).append(c)
        elif kinds == {"label"}:
            by_stem.setdefault(stem, {}).setdefault("label", []).append(c)
        else:                                   # 无记号或双记号 → 配不上
            ambiguous.append(c)
    pairs, unmapped = [], list(ambiguous)
    for stem in sorted(by_stem):
        g = by_stem[stem]
        if len(g.get("pred", [])) == 1 and len(g.get("label", [])) == 1:
            pairs.append({"feature": stem, "pred_col": g["pred"][0],
                          "label_col": g["label"][0], "source": "auto"})
        else:
            unmapped += g.get("pred", []) + g.get("label", [])
    return pairs, sorted(unmapped)


def discover_models(list_cols: dict[str, int], horizon: int, exclude=()) -> list[str]:
    """predict.parquet 的模型列 = 全部 192 点 list 列（1..N 个都算，鲁棒于只给一两个模型）。"""
    return sorted(c for c, ln in list_cols.items() if ln == horizon and c not in exclude)


# ---------------------------------------------------------------- 守卫
def alignment(ts_test, ts_pred, ts_ft, freq) -> dict:
    """三文件时间戳对齐。feature_true 若 0 偏移对不上，试 ±672 步（窗口起点 vs 预报起点歧义）。"""
    st, sp = set(ts_test), set(ts_pred)
    best = {"offset_steps": 0, "n_common": len(st & sp & set(ts_ft))}
    if best["n_common"] < 0.5 * min(len(st), len(ts_ft)):
        for off in (672, -672):
            shifted = {t + off * freq for t in ts_ft}
            n = len(st & sp & shifted)
            if n > best["n_common"]:
                best = {"offset_steps": off, "n_common": n}
    return {"n_test": len(st), "n_predict": len(sp), "n_feature_true": len(ts_ft),
            "align_offset_steps": best["offset_steps"], "n_common": best["n_common"]}


def wc_targets(test_lists: dict[str, int], pairs: list[dict]) -> dict[str, list[str]]:
    """滚动窗一致性只闸**真值列**（物理时间的函数，行间重叠段理应一致）：
    test 的功率真值列 + feature_true 的 label 列。predict 模型列与预报特征列
    **绝不进闸**——逐行重新起报下相邻行对同一物理时刻的预测/预报本来就不同
    （lead time 不同），那是 feature_revision.py 的信号，不是窗口构造 bug。"""
    d = fb.require_du()
    return {"test": [c for c in (d.LABEL_COL,) if c in test_lists],
            "feature_true": [p["label_col"] for p in pairs]}


def window_consistency(dfs: dict[str, tuple[pd.DataFrame, list[str]]], n_checks=300) -> dict:
    """各文件抽 ≤3 个 list 列跑滚动窗一致性；>0 即窗口构造 bug，立即停下报告。"""
    d = fb.require_du()
    out = {}
    for name, (df, cols) in dfs.items():
        for c in cols[:3]:
            rate = d.check_window_consistency(df, c, n_checks=n_checks)
            out[f"{name}:{c}"] = None if np.isnan(rate) else round(float(rate), 4)
    return out


def crosscheck_labels(ft, pairs, test, test_lists, n_checks=200, seed=0) -> dict:
    """label 序列 vs test 特征列历史段的抽样一致性。

    约定：test 特征列 list 长 L≥672，前 672 个点为历史观测；行 T 的历史点 j 的物理时间
    有两种惯例——A: T+(j-672)Δ（历史止于 T，未来 192 从 T 起，与 data_utils 未来列口径一致）；
    B: T+jΔ。两种都试，报吻合率更高的那种。核不上（<0.99）= 对齐错位或 label 侧有假，先停。"""
    d = fb.require_du()
    test_map = {t: i for i, t in enumerate(pd.DatetimeIndex(test[d.TIMESTAMP_COL]))}
    ft_ts = pd.DatetimeIndex(ft[d.TIMESTAMP_COL])
    rng = np.random.default_rng(seed)
    results = {}
    for conv in ("A", "B"):
        agree = checked = 0
        for p in pairs:
            tcol = p["feature"] if p["feature"] in test_lists else None
            if tcol is None or test_lists[tcol] < 672:
                continue
            lab = d.to_matrix(ft, p["label_col"])
            hist = d.to_matrix(test, tcol)[:, :672]
            attempts = 0
            while checked < n_checks and attempts < n_checks * 10:
                attempts += 1
                i = int(rng.integers(0, len(ft_ts)))
                m = int(rng.integers(1, 673))
                t2 = ft_ts[i] + m * d.FREQ
                if t2 not in test_map:
                    continue
                k = int(rng.integers(0, min(192, m)))
                j = 672 + k - m if conv == "A" else k + m  # B: 时间 T+kΔ 在行 T2 的 j=?：T2+jΔ=T+kΔ → j=k-m<0 不可用；
                if conv == "B":                            # 惯例 B 下历史在 T 之后，须用更早的行：j = k+m 超界跳过
                    if j >= 672:
                        continue
                    t2 = ft_ts[i] - m * d.FREQ
                    if t2 not in test_map:
                        continue
                if not (0 <= j < 672):
                    continue
                v_lab = lab[i, k]
                v_hist = hist[test_map[t2], j]
                if np.isnan(v_lab) and np.isnan(v_hist):
                    ok = True
                else:
                    ok = bool(np.isclose(v_lab, v_hist, rtol=1e-4, atol=1e-5))
                agree += ok
                checked += 1
        results[conv] = {"n_checked": checked,
                         "agree_rate": round(agree / checked, 4) if checked else None}
    best = max(results, key=lambda c: (results[c]["agree_rate"] or -1))
    r = dict(results[best])
    r["convention"] = "hist_before_ts" if best == "A" else "hist_after_ts"
    r["by_convention"] = results
    return r


# ---------------------------------------------------------------- 主流程
def main():
    cfg = fb.config_or_empty()
    ap = argparse.ArgumentParser()
    ap.add_argument("--test", default=cfg.get("test_label"))
    ap.add_argument("--predict", default=cfg.get("predict"))
    ap.add_argument("--feature-true", default=cfg.get("feature_true"))
    ap.add_argument("--n-overlap-checks", type=int, default=200)
    ap.add_argument("--out", default="probe_schema.json")
    ap.add_argument("--pairs-out", default="feature_pairs.json")
    args = ap.parse_args()
    for k in ("test", "predict", "feature_true"):
        if not getattr(args, k):
            raise SystemExit(f"缺 --{k.replace('_', '-')}（或先写 blame_config.json）。"
                             "feature_true 没有就先问用户要——绝不静默降级。")

    d = fb.require_du()
    warnings = []
    files, dfs, ts_cols = {}, {}, {}
    for name, path in (("test", args.test), ("predict", args.predict),
                       ("feature_true", args.feature_true)):
        df, orig_ts = fb.load_any(path)
        lists = fb.list_columns(df)
        dfs[name] = (df, lists)
        ts_cols[name] = orig_ts
        files[name] = {"path": os.path.abspath(path), "n_rows": len(df),
                       "timestamp_col": orig_ts, "list_columns": lists,
                       "scalar_columns": [c for c in df.columns
                                          if c not in lists and c != d.TIMESTAMP_COL]}

    model_cols = discover_models(dfs["predict"][1], d.HORIZON)
    if not model_cols:
        warnings.append("predict.parquet 里找不到任何 192 点 list 列——模型列发现失败")

    ft_df, ft_lists = dfs["feature_true"]
    pairs, unmapped = discover_pairs([c for c, ln in ft_lists.items() if ln == d.HORIZON])
    if unmapped:
        warnings.append(f"{len(unmapped)} 个列配不成 (预测,真值) 对 —— 主 agent 拿去问用户，"
                        "答案以 source='user' 写回 feature_pairs.json")

    test_df = dfs["test"][0]
    align = alignment(pd.DatetimeIndex(test_df[d.TIMESTAMP_COL]),
                      pd.DatetimeIndex(dfs["predict"][0][d.TIMESTAMP_COL]),
                      pd.DatetimeIndex(ft_df[d.TIMESTAMP_COL]), d.FREQ)
    if align["align_offset_steps"] != 0:
        warnings.append(f"feature_true 时间戳需偏移 {align['align_offset_steps']} 步才对得上"
                        "（窗口起点 vs 预报起点歧义）——先与用户确认口径再进 Stage 1")
    if align["n_common"] == 0:
        warnings.append("三文件时间戳零交集——路径或口径给错了")

    targets = wc_targets(dfs["test"][1], pairs)
    wc = window_consistency({name: (dfs[name][0], cols) for name, cols in targets.items()})
    wc_rates = [v for v in wc.values() if v is not None]
    wc_bad = max(wc_rates) if wc_rates else None
    if wc_bad and wc_bad > 0:
        warnings.append("真值列滚动窗一致性抽查不通过——窗口构造有 bug，所有取点口径不可信，立刻停下报告")

    cross = crosscheck_labels(ft_df, pairs, test_df, dfs["test"][1],
                              n_checks=args.n_overlap_checks)
    if cross["n_checked"] and (cross["agree_rate"] or 0) < 0.99:
        warnings.append("feature_true 的 label 与 test 特征历史段核不上（<0.99）——"
                        "对齐错位或 label 侧有假，未排除前不得进 Stage 2")

    probe = {
        "files": files,
        "timestamp_cols": ts_cols,
        "n_models": len(model_cols),
        "model_columns": model_cols,
        "feature_names": [p["feature"] for p in pairs],
        "n_pairs": len(pairs),
        "unmapped": unmapped,
        "alignment": align,
        "window_consistency": wc,
        "window_consistency_bad_rate": wc_bad,
        "label_crosscheck": cross,
        "warnings": warnings,
    }
    fb.dump_json(args.out, probe)
    fb.dump_json(args.pairs_out, {"pairs": pairs, "unmapped": unmapped})

    print(f"[probe_schema] 模型列 ×{len(model_cols)}: {model_cols}")
    print(f"  特征对 ×{len(pairs)}: {[p['feature'] for p in pairs]}   unmapped ×{len(unmapped)}: {unmapped}")
    print(f"  时间戳列: {ts_cols}   对齐: 共同 {align['n_common']} 行, 偏移 {align['align_offset_steps']} 步")
    print(f"  真值列窗一致性最坏不合率: {wc_bad}   label 交叉核验: {cross['agree_rate']}"
          f"（{cross['n_checked']} 点, {cross.get('convention')}）")
    for w in warnings:
        print(f"  ⚠ {w}")
    print(f"  产物: {args.out} / {args.pairs_out}")


if __name__ == "__main__":
    main()
