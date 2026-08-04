#!/usr/bin/env python3
"""deployment-drift 金标准生成器（确定性，零随机——spec §5）。

植入结构（全部解析式构造，奇偶/模三交替提供确定性"噪声"）：
  E1 渐变退化（难例形态，spec §5 硬规则）：rmse 前 40 窗均值 1.0（±0.1 交替），
     窗 40 起 ramp（每窗 +0.25，8 窗爬到 3.0），窗 48 起稳定 3.0（±0.1 交替）。
     真实 onset = 40；最大分离切分点会落在 ramp 中段（晚于 onset）——期望断言
     必须同时答对 shape=gradual 与 onset∈[40,42]，只报切分点过不了闸。
  E2 诱因特征 drift_feat：基线 10（±0.05 交替），窗 40 起均值漂移（每窗 +0.5，
     封顶 +4）——onset 与误差侧重合。
  D1 诱饵特征 decoy_feat：基线 5 + 模三循环（+0.5/0/-0.5），全期无偏移。
"""
import csv
import os

HERE = os.path.dirname(os.path.abspath(__file__))
N, ONSET, RAMP_END = 60, 40, 48


def rmse_at(d):
    if d < ONSET:
        return 1.0 + (0.1 if d % 2 == 0 else -0.1)
    if d < RAMP_END:
        return 1.0 + 0.25 * (d - ONSET + 1)
    return 3.0 + (0.1 if d % 2 == 0 else -0.1)


def drift_base(d):
    if d < ONSET:
        return 10.0 + (0.05 if d % 2 == 0 else -0.05)
    return 10.0 + min(0.5 * (d - ONSET + 1), 4.0)


def decoy_base(d):
    return 5.0 + (0.5, 0.0, -0.5)[d % 3]


def window_ts(d):
    return f"W{d:03d}"  # 合成窗标签即可——真实日期语义由 Stage 0 适配器负责


with open(os.path.join(HERE, "error_series.csv"), "w", newline="") as f:
    w = csv.writer(f)
    w.writerow(["window_idx", "window_ts", "rmse"])
    for d in range(N):
        w.writerow([d, window_ts(d), f"{rmse_at(d):.4f}"])

with open(os.path.join(HERE, "features.csv"), "w", newline="") as f:
    w = csv.writer(f)
    w.writerow(["window_idx", "window_ts", "feature", "v0", "v1", "v2", "v3"])
    for d in range(N):
        for name, base in (("drift_feat", drift_base(d)), ("decoy_feat", decoy_base(d))):
            spread = 0.05 if name == "drift_feat" else 0.1
            pts = (base - spread, base, base + spread, base)
            w.writerow([d, window_ts(d), name] + [f"{p:.4f}" for p in pts])

print(f"golden 数据已生成：{N} 窗，真实 onset={ONSET}，ramp 至 {RAMP_END}")
