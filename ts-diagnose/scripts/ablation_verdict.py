#!/usr/bin/env python3
"""干预判定：delta 与噪声底 3σ 比较 + 预测方向核对 → 确认/否证/未决。

CLI 额外把判定结果格式化成一行 receipt——格式须匹配 conclusion_gate.RECEIPT_LINE_RE
（含 confirmed/refuted/undecided 三态之一 + switch/delta + seeds=N），供 architecture-attribution
的「## 消融证据」节直接抄录。"""
from __future__ import annotations

import argparse
import hashlib
import json


def verdict(delta, noise_floor_3sigma, pred_direction):
    if abs(delta) < noise_floor_3sigma:
        return "undecided"
    got = "increase" if delta > 0 else "decrease"
    return "confirmed" if got == pred_direction else "refuted"


def pred_miss(delta, noise_floor_3sigma, delta2=None, noise_floor2=None):
    """判据②「预测落空」是否成立：预登记说「|delta| 应超噪声底」，实测 |delta| ≤ 噪声底一半，
    **且保守第二口径同判**。→ {"main":bool,"second":bool|None,"eligible":bool,"note":str}。
    第二口径缺席时 eligible=False：只凭主口径不许升级为 refuted，只能停在 undecided
    （全链路联调 F11：worker 删掉预测数组后第二口径复核做不了，判定被迫悬空）。"""
    main = abs(delta) <= noise_floor_3sigma / 2.0
    if delta2 is None or noise_floor2 is None:
        return {"main": main, "second": None, "eligible": False,
                "note": "缺第二口径复核（--delta2/--noise-floor2）——判据②不可用，只能 undecided"}
    second = abs(delta2) <= noise_floor2 / 2.0
    return {"main": main, "second": second, "eligible": bool(main and second),
            "note": "两口径同判「预测落空」" if main and second else "两口径判定不一致或未落空"}


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
    ap.add_argument("--script", default=None,
                     help="算出本 delta 的 eval 脚本路径（receipt 记 produced_by + "
                          "script_sha256，让回执与脚本版本对得上）")
    ap.add_argument("--t-start", default=None, dest="t_start",
                     help="干预执行起始时刻（ISO8601），受访日志用真实时间，不用 mtime")
    ap.add_argument("--t-end", default=None, dest="t_end",
                     help="干预执行结束时刻（ISO8601）")
    ap.add_argument("--delta2", type=float, default=None,
                     help="保守第二口径下的同一 delta（判据②「预测落空」必须两口径同判）")
    ap.add_argument("--noise-floor2", type=float, default=None, dest="noise_floor2",
                     help="第二口径的噪声底 3σ")
    ap.add_argument("--caliber2", default=None,
                     help="第二口径名（如 rmse_96）——写进 receipt，供结论逐条披露")
    ap.add_argument("--selftest", default=None,
                     help="eval 脚本自检结果一句话（如「植入回收 3/3 通过」）——"
                          "把“认真验证过”变成机器可读信号")
    args = ap.parse_args()

    script_sha256 = None
    if args.script:
        h = hashlib.sha256()
        with open(args.script, "rb") as f:  # 路径写错必须当场炸，不许静默记空指纹
            for blk in iter(lambda: f.read(65536), b""):
                h.update(blk)
        script_sha256 = h.hexdigest()

    v, line = receipt_line(args.hypothesis_id, args.switch, args.delta,
                            args.noise_floor, args.seeds, args.direction)
    print(line)
    pm = pred_miss(args.delta, args.noise_floor, args.delta2, args.noise_floor2)
    if v == "undecided":
        print(f"  判据②（预测落空）：{'成立' if pm['eligible'] else '不成立'}——{pm['note']}")

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
            # 溯源块：脚本指纹让回执与代码版本对得上；t_start/t_end 让 journal
            # 摆脱 mtime；selftest 让「验证过」可观测。缺省 None = 未提供，显式可见
            "produced_by": args.script, "script_sha256": script_sha256,
            "t_start": args.t_start, "t_end": args.t_end,
            "script_selftest": args.selftest,
            # 第二口径：判据②(预测落空)要求保守口径同判；缺了就只能停在 undecided
            "second_caliber": ({"name": args.caliber2, "delta": args.delta2,
                                "noise_floor_3sigma": args.noise_floor2,
                                "verdict": verdict(args.delta2, args.noise_floor2,
                                                   args.direction)}
                               if args.delta2 is not None and args.noise_floor2 is not None
                               else None),
            "pred_miss": pred_miss(args.delta, args.noise_floor,
                                   args.delta2, args.noise_floor2),
        })
        with open(args.out, "w", encoding="utf-8") as f:
            json.dump(receipts, f, ensure_ascii=False, indent=2)


if __name__ == "__main__":
    main()
