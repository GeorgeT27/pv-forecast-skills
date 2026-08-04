#!/usr/bin/env python3
"""training-sufficiency 金标准输入生成器——**确定性解析式构造，零随机**。

场景：1 个 series（S1）、6 个成员（m1..m6）按轮转赛程组成每迭代 3 个 chunk（各 2 成员），
8 个迭代、每 chunk 训 8 个 epoch。植入两个已知效应：
  - m3：loss 侧难学（chunk floor +0.6/成员）→ 成分回归 θ_loss top-1 必须是 m3；
  - m2：目标侧拖累（外部指标 +0.5/成员）→ 目标侧回归 θ_target top-1 必须是 m2。
曲线形态 loss = 2·exp(-0.8·epoch) + floor：8 个 epoch 后全部到平台
（marginal_gain < 0.02）→ 充分性形态判定的期望已知。

改期望前先想清楚：期望错 = 金标准失效；本文件与 expected 一起动，并重跑 pytest。
"""
import math
import os

HERE = os.path.dirname(os.path.abspath(__file__))
MEMBERS = ["m1", "m2", "m3", "m4", "m5", "m6"]
# 6 人轮转赛程（circle method）：5 轮互不重复的 3 组配对
SCHEDULE = [
    [("m1", "m6"), ("m2", "m5"), ("m3", "m4")],
    [("m1", "m5"), ("m6", "m4"), ("m2", "m3")],
    [("m1", "m4"), ("m5", "m3"), ("m6", "m2")],
    [("m1", "m3"), ("m4", "m2"), ("m5", "m6")],
    [("m1", "m2"), ("m3", "m6"), ("m4", "m5")],
]
N_ITER, N_EPOCH = 8, 8
LOSS_EFFECT = {"m3": 0.6}      # loss 侧植入：难学成员
TARGET_EFFECT = {"m2": 0.5}    # 目标侧植入：拖累成员


def chunks_of(it):
    """[(unit, position, (memA, memB))]"""
    return [(f"c{p}", p, pair) for p, pair in enumerate(SCHEDULE[it % len(SCHEDULE)])]


def floor_of(pair, pos):
    return 1.0 + sum(LOSS_EFFECT.get(m, 0.0) for m in pair) / len(pair) + 0.02 * pos


def rmse_of(pair, pos):
    return 1.0 + sum(TARGET_EFFECT.get(m, 0.0) for m in pair) / len(pair) + 0.01 * pos


def main():
    loss_rows = ["series,iteration,unit,position,epoch,loss"]
    assign_rows = ["iteration,unit,position,member"]
    ext_rows = ["iteration,unit,rmse"]
    for it in range(N_ITER):
        for unit, pos, pair in chunks_of(it):
            for m in pair:
                assign_rows.append(f"{it},{unit},{pos},{m}")
            ext_rows.append(f"{it},{unit},{rmse_of(pair, pos):.6f}")
            fl = floor_of(pair, pos)
            for ep in range(1, N_EPOCH + 1):
                loss = 2.0 * math.exp(-0.8 * ep) + fl
                loss_rows.append(f"S1,{it},{unit},{pos},{ep},{loss:.6f}")
    for name, rows in (("loss_records.csv", loss_rows),
                       ("assignments.csv", assign_rows),
                       ("external_metric.csv", ext_rows)):
        with open(os.path.join(HERE, name), "w", encoding="utf-8") as f:
            f.write("\n".join(rows) + "\n")
        print(f"写出 {name}（{len(rows) - 1} 行）")


if __name__ == "__main__":
    main()
