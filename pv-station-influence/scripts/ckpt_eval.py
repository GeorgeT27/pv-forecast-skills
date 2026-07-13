#!/usr/bin/env python3
"""Stage 1 补料（Mode B）—— 日志没记白马湖 RMSE 时，逐 checkpoint 重算出 rmse_series.csv。

上下文/磁盘纪律（checkpoint ~300MB/个）：**一个进程内顺序** load→前向→算RMSE→释放→
（可选）删除临时解压，绝不把权重或预测张量带进对话。结果**追加**写 rmse_series.csv，
中断可续（已算过的 (iteration,chunk,model) 跳过）。

需要 adapter.load_model + adapter.predict_station（见 adapter_template.py）。
checkpoint 定位：约定 checkpoint_dir/<model>/iter<it>_chunk<pos>.pt，不符则改 --pattern
或在 adapter 里实现 locate_checkpoint(model,it,pos)。

用法：
  python <skill>/scripts/ckpt_eval.py                       # 遍历所有 (模型,迭代,chunk)
  python <skill>/scripts/ckpt_eval.py --models M4 --iters 1,2
"""
from __future__ import annotations

import argparse
import gc
import os
import sys

import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import si_common as sic

OUT = "rmse_series.csv"


def _done_set():
    if not os.path.exists(OUT):
        return set()
    d = pd.read_csv(OUT)
    return set(zip(d["model"], d["iteration"], d["position"]))


def _locate(adapter, cfg, model, it, pos, pattern):
    if hasattr(adapter, "locate_checkpoint"):
        return adapter.locate_checkpoint(model, it, pos, cfg)
    return os.path.join(cfg["checkpoint_dir"],
                        pattern.format(model=model, it=it, pos=pos, chunk=pos))


def _append_row(row):
    df = pd.DataFrame([row])
    df.to_csv(OUT, mode="a", header=not os.path.exists(OUT), index=False)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--models", default=None, help="逗号分隔；缺省用 config.models")
    ap.add_argument("--iters", default=None, help="逗号分隔迭代号；缺省全部")
    ap.add_argument("--pattern", default="{model}/iter{it}_chunk{pos}.pt")
    ap.add_argument("--device", default="cpu")
    args = ap.parse_args()

    cfg = sic.load_config()
    if sic.mode_from_config(cfg) != "B":
        sys.exit("无可用 checkpoint_dir —— ckpt_eval 属 Mode B。若日志有 RMSE 请走 probe_logs 解析。")
    adapter = sic.load_adapter()
    test_station = cfg["test_station"]
    models = (args.models.split(",") if args.models else cfg.get("models")) or ["M1", "M2", "M3", "M4"]
    n_iters = int((cfg.get("sampler") or {}).get("n_iters") or 0)
    if n_iters <= 0:
        sys.exit("config.sampler.n_iters 缺失，无法确定要遍历的迭代范围。")
    iters = [int(x) for x in args.iters.split(",")] if args.iters else list(range(1, n_iters + 1))
    layout = cfg.get("chunk_layout") or {"n_chunks": 4}
    n_chunks = int(layout.get("n_chunks", 4))

    done = _done_set()
    n_new = 0
    for model in models:
        for it in iters:
            for pos in range(1, n_chunks + 1):
                if (model, it, pos) in done:
                    continue
                ckpt = _locate(adapter, cfg, model, it, pos, args.pattern)
                if not os.path.exists(ckpt):
                    print(f"  [skip] 缺 checkpoint: {ckpt}")
                    continue
                m = adapter.load_model(model, ckpt, device=args.device)
                pred, true = adapter.predict_station(m, test_station, cfg)
                val = sic.rmse(pred, true)
                _append_row({"iteration": it, "chunk": pos, "position": pos,
                             "model": model, "rmse": round(val, 6)})
                n_new += 1
                print(f"  [{model}] iter{it} chunk{pos}  白马湖RMSE={val:.4f}")
                del m, pred, true
                gc.collect()
                try:
                    import torch
                    torch.cuda.empty_cache()
                except Exception:
                    pass

    print("=" * 56)
    print(f"ckpt_eval 完成：新增 {n_new} 行 → {OUT}（已算过的自动跳过，可中断续跑）。")
    print("→ 有了 rmse_series.csv 即可跑 influence_regression.py（Stage 1）。")
    print("=" * 56)


if __name__ == "__main__":
    main()
