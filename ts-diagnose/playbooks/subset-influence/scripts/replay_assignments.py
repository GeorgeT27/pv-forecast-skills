#!/usr/bin/env python3
"""Stage 0 —— 种子回放，还原每 (迭代,chunk) 的站点组成。

分组随机但有种子 + 采样代码在手 => 直接重跑采样即可精确还原（免逐 checkpoint 猜）。
产出 assignments.csv：iteration,chunk,position,size,stations（stations=";" 连接）。

用法：
  python <skill>/scripts/replay_assignments.py            # 用 config.sampler.seeds/n_iters
  python <skill>/scripts/replay_assignments.py --validate # 额外做 checkpoint 指纹抽查（Mode B）

回放 vs 指纹校验：
  回放靠 adapter.sample_assignments(iteration, seed) 复现训练的随机流程。
  --validate（需 checkpoint + adapter.predict_station）：抽 2-3 个 chunk，比"训练该 chunk
  前后在全部训练站上的 RMSE 改善"，改善最大的若干个站应与回放成员吻合（新近效应指纹）。
  不吻合 => 回放的 RNG 与训练不一致，别信 assignments，改走 references/influence-methods.md
  的「指派问题反推」兜底。
"""
from __future__ import annotations

import argparse
import os
import sys

import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import si_common as sic


def replay(cfg) -> pd.DataFrame:
    adapter = sic.load_adapter()
    sampler = cfg.get("sampler") or {}
    n_iters = sampler.get("n_iters")
    seeds = sampler.get("seeds")
    if not n_iters:
        sys.exit("config.sampler.n_iters 缺失：需要实际跑过的迭代数。")
    rows = []
    for it in range(1, int(n_iters) + 1):
        seed = seeds[it - 1] if isinstance(seeds, list) and len(seeds) >= it else \
            (seeds if seeds is not None else None)
        chunks = adapter.sample_assignments(it, seed)  # [[站,...] × 4]
        for pos, members in enumerate(chunks, 1):
            rows.append({
                "iteration": it,
                "chunk": pos,          # 这里 chunk id 就用位置；如训练另有编号可在 adapter 里带出
                "position": pos,       # chunk 在迭代内的先后（新近效应控制变量）
                "size": len(members),
                "stations": ";".join(map(str, members)),
            })
    return pd.DataFrame(rows)


def validate(cfg, asg: pd.DataFrame, k=3):
    """指纹抽查：需要 checkpoint 与 adapter。这里给出协议骨架，重活在 adapter 里。"""
    adapter = sic.load_adapter()
    station_list = sic.stations(cfg)
    checked = []
    # 取前 k 个 chunk 抽查（真实实现里应随机抽不同迭代）
    for _, r in asg.head(k).iterrows():
        it, pos = int(r["iteration"]), int(r["position"])
        replayed = set(str(r["stations"]).split(";"))
        # before/after checkpoint 由 adapter 依 (it,pos) 定位；缺则跳过
        try:
            gains = adapter.station_gain_fingerprint(it, pos, station_list, cfg)  # 可选扩展
        except AttributeError:
            print("  adapter 未实现 station_gain_fingerprint，跳过指纹校验（回放结果仍可用，"
                  "但未独立验证）。")
            return
        top = set([s for s, _ in sorted(gains.items(), key=lambda x: -x[1])[:len(replayed)]])
        overlap = len(replayed & top) / max(1, len(replayed))
        checked.append((it, pos, round(overlap, 2)))
        print(f"  迭代{it} chunk{pos}: 回放∩指纹Top = {overlap:.0%}")
    ok = all(o >= 0.6 for *_, o in checked)
    print("→ 指纹校验" + ("通过，回放可信。" if ok else
                        "未通过！回放 RNG 与训练不一致，改用指派问题反推（见 influence-methods.md）。"))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--validate", action="store_true")
    args = ap.parse_args()
    cfg = sic.load_config()

    asg = replay(cfg)
    asg.to_csv("assignments.csv", index=False)

    # 自足摘要
    summary = {
        "n_iterations": int(asg["iteration"].nunique()),
        "n_chunks_total": int(len(asg)),
        "stations": sic.stations(cfg),
        "coverage_per_station": {
            s: int(asg["stations"].str.split(";").apply(lambda xs: s in xs).sum())
            for s in sic.stations(cfg)
        },
    }
    sic.dump_json("assignments_summary.json", summary)

    print("=" * 56)
    print(f"Stage 0 回放完成：{summary['n_iterations']} 迭代 × 每迭代 {len(asg)//max(1,summary['n_iterations'])} chunk")
    cov = summary["coverage_per_station"]
    lo = min(cov.values()); hi = max(cov.values())
    print(f"  每站出现次数范围 [{lo}, {hi}]（应≈迭代数；偏差大说明回放或站表有问题）")
    print("  → assignments.csv / assignments_summary.json 已写。")
    if args.validate:
        print("指纹抽查：")
        validate(cfg, asg)
    else:
        print("  建议加 --validate 做 checkpoint 指纹抽查（Mode B）确认回放可信。")
    print("=" * 56)


if __name__ == "__main__":
    main()
