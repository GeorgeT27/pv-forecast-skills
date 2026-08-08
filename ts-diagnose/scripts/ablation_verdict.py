#!/usr/bin/env python3
"""干预判定：delta 与噪声底 3σ 比较 + 预测方向核对 → 确认/否证/未决。

CLI 额外把判定结果格式化成一行 receipt——格式须匹配 conclusion_gate.RECEIPT_LINE_RE
（含 confirmed/refuted/undecided 三态之一 + switch/delta + seeds=N），供 architecture-attribution
的「## 消融证据」节直接抄录。"""
from __future__ import annotations

import argparse
import json


def verdict(delta, noise_floor_3sigma, pred_direction):
    if abs(delta) < noise_floor_3sigma:
        return "undecided"
    got = "increase" if delta > 0 else "decrease"
    return "confirmed" if got == pred_direction else "refuted"


def receipt_line(hypothesis_id, switch, delta, noise_floor_3sigma, seeds, pred_direction):
    """→ (verdict, line)。line 格式固定为
    `- <id> <verdict>: switch=<switch> delta=<±.3f> noise_floor=<.4f> seeds=<N>`。"""
    v = verdict(delta, noise_floor_3sigma, pred_direction)
    line = (f"- {hypothesis_id} {v}: switch={switch} delta={delta:+.3f} "
            f"noise_floor={noise_floor_3sigma:.4f} seeds={seeds}")
    return v, line


def main():
    ap = argparse.ArgumentParser(
        description="干预判定：delta vs 噪声底 3σ + 预测方向核对 → confirmed/refuted/undecided")
    ap.add_argument("--hypothesis-id", required=True, help="账本里的假设 H-ID")
    ap.add_argument("--switch", required=True,
                     help="干预开关（值本身以 -- 开头时用 --switch=--foo 形式传，避免被 argparse 误判）")
    ap.add_argument("--delta", type=float, required=True,
                     help="干预后−干预前 的口径指标差（同一口径、同一种子集）")
    ap.add_argument("--noise-floor", type=float, required=True, dest="noise_floor",
                     help="噪声底 3σ（同配置 ≥3 种子指标标准差 × 3）")
    ap.add_argument("--direction", choices=["increase", "decrease"], required=True,
                     help="假设预登记的可否证预测方向")
    ap.add_argument("--seeds", type=int, required=True, help="本次干预实跑的种子数")
    ap.add_argument("--out", default=None,
                     help="可选：把 receipt 追加写入的 JSON 文件（数组，重复调用安全）")
    args = ap.parse_args()

    v, line = receipt_line(args.hypothesis_id, args.switch, args.delta,
                            args.noise_floor, args.seeds, args.direction)
    print(line)

    if args.out:
        try:
            with open(args.out, encoding="utf-8") as f:
                receipts = json.load(f)
        except (FileNotFoundError, json.JSONDecodeError):
            receipts = []
        receipts.append({
            "hypothesis_id": args.hypothesis_id, "switch": args.switch,
            "delta": args.delta, "noise_floor_3sigma": args.noise_floor,
            "seeds": args.seeds, "pred_direction": args.direction,
            "verdict": v, "line": line,
        })
        with open(args.out, "w", encoding="utf-8") as f:
            json.dump(receipts, f, ensure_ascii=False, indent=2)


if __name__ == "__main__":
    main()
