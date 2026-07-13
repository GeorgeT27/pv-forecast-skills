#!/usr/bin/env python3
"""Stage 2（Mode B）—— TracIn 式梯度影响力，独立于 RMSE 序列的第二条证据线。

思想：若某训练站 s 的梯度与白马湖验证梯度**持续反向**，说明训到它把参数推离"对白马湖好"
的方向 => 负迁移。影响力分 ≈ Σ_ckpt ⟨g_s, g_test⟩（TracInCP）。与 Stage 1 排名一致才升级
（见 references/attribution-discipline.md 的升级门槛）。

上下文/磁盘纪律同 ckpt_eval：一个进程顺序处理 checkpoint，只把标量内积追加落盘，
梯度向量不进对话。需要 adapter.load_model + adapter.loss_gradient。

用法：
  python <skill>/scripts/tracin_influence.py                    # 全模型，间隔取 checkpoint
  python <skill>/scripts/tracin_influence.py --every 1 --models M4
  # --every N：每 N 个迭代取一个 checkpoint（默认取每迭代最后一个 chunk）降成本。
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

RAW = "tracin_dots.csv"       # 逐 checkpoint 逐站的原始内积（可续跑）
OUT = "tracin_scores.json"    # 汇总


def _done_set():
    if not os.path.exists(RAW):
        return set()
    d = pd.read_csv(RAW)
    return set(zip(d["model"], d["iteration"], d["station"]))


def _append(row):
    pd.DataFrame([row]).to_csv(RAW, mode="a", header=not os.path.exists(RAW), index=False)


def _locate(adapter, cfg, model, it, pos, pattern):
    if hasattr(adapter, "locate_checkpoint"):
        return adapter.locate_checkpoint(model, it, pos, cfg)
    return os.path.join(cfg["checkpoint_dir"], pattern.format(model=model, it=it, pos=pos, chunk=pos))


def _summarize(station_list, models):
    d = pd.read_csv(RAW)
    out = {"note": "influence = Σ_ckpt ⟨g_station, g_test⟩；越正=越拖累白马湖", "models": {}}
    coef = {}
    for model in models:
        sub = d[d["model"] == model]
        if sub.empty:
            continue
        # 每站对所有 checkpoint 的内积求和（TracInCP）。注意符号约定：
        # 训练在降损失 => 有益站的 g_s 与 g_test 同向（内积>0 表示"训它也降白马湖损失"=有益）。
        # 为了让"高=拖累"与 Stage 1 一致，这里取负：harm = -Σ⟨g_s,g_test⟩。
        agg = sub.groupby("station")["dot"].sum()
        harm = (-agg).sort_values(ascending=False)
        coef[model] = harm.reindex(station_list).values
        out["models"][model] = {
            "n_checkpoints": int(sub["iteration"].nunique()),
            "ranking_harmful_first": list(harm.index),
            "harm_score": {k: round(float(v), 6) for k, v in harm.items()},
        }
    if len(coef) >= 2:
        try:
            from scipy.stats import spearmanr
            names = [m for m in models if m in coef]
            sp = {}
            for a in range(len(names)):
                for b in range(a + 1, len(names)):
                    va, vb = coef[names[a]], coef[names[b]]
                    mask = np.isfinite(va) & np.isfinite(vb)
                    if mask.sum() >= 3:
                        r, _ = spearmanr(va[mask], vb[mask])
                        sp[f"{names[a]}~{names[b]}"] = round(float(r), 3)
            out["cross_model_spearman"] = sp
        except Exception:
            pass
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--models", default=None)
    ap.add_argument("--every", type=int, default=1, help="每 N 个迭代取一个 checkpoint")
    ap.add_argument("--pattern", default="{model}/iter{it}_chunk{pos}.pt")
    ap.add_argument("--device", default="cpu")
    ap.add_argument("--n-windows", type=int, default=200)
    args = ap.parse_args()

    cfg = sic.load_config()
    if sic.mode_from_config(cfg) != "B":
        sys.exit("无 checkpoint_dir —— TracIn 属 Mode B。")
    adapter = sic.load_adapter()
    station_list = sic.stations(cfg)
    test_station = cfg["test_station"]
    models = (args.models.split(",") if args.models else cfg.get("models")) or ["M1", "M2", "M3", "M4"]
    n_iters = int((cfg.get("sampler") or {}).get("n_iters") or 0)
    layout = cfg.get("chunk_layout") or {"n_chunks": 4}
    last_pos = int(layout.get("n_chunks", 4))  # 默认取每迭代最后一个 chunk 的 checkpoint

    done = _done_set()
    for model in models:
        for it in range(1, n_iters + 1, max(1, args.every)):
            ckpt = _locate(adapter, cfg, model, it, last_pos, args.pattern)
            if not os.path.exists(ckpt):
                print(f"  [skip] 缺 {ckpt}")
                continue
            if all((model, it, s) in done for s in station_list):
                continue
            m = adapter.load_model(model, ckpt, device=args.device)
            g_test = adapter.loss_gradient(m, test_station, cfg, n_windows=args.n_windows)
            g_test = np.asarray(g_test, float)
            gtn = np.linalg.norm(g_test) + 1e-12
            for s in station_list:
                if (model, it, s) in done:
                    continue
                g_s = np.asarray(adapter.loss_gradient(m, s, cfg, n_windows=args.n_windows), float)
                dot = float(np.dot(g_s, g_test) / (np.linalg.norm(g_s) * gtn + 1e-12))  # 余弦式，跨 ckpt 可比
                _append({"model": model, "iteration": it, "station": s, "dot": round(dot, 8)})
            print(f"  [{model}] iter{it}: 17 站梯度对齐已记")
            del m, g_test
            gc.collect()
            try:
                import torch
                torch.cuda.empty_cache()
            except Exception:
                pass

    out = _summarize(station_list, models)
    sic.dump_json(OUT, out)
    print("=" * 56)
    print("Stage 2 TracIn 完成。各模型最拖累前三：")
    for m, r in out["models"].items():
        print(f"  [{m}] {r['ranking_harmful_first'][:3]}  ({r['n_checkpoints']} checkpoints)")
    if "cross_model_spearman" in out:
        print(f"  跨模型一致性: {out['cross_model_spearman']}")
    print("→ tracin_scores.json 已写。与 influence_coefs.json 的排名对照＝升级门槛核心。")
    print("=" * 56)


if __name__ == "__main__":
    main()
