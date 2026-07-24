#!/usr/bin/env python3
"""subset-influence 金标准输入生成器——确定性构造，零随机。

场景：3 个训练条目 e1/e2/e3，K=2 chunk/迭代（chunk 1 装 2 个条目，chunk 2 装 1 个条目），
12 次迭代循环三种"chunk1 的一对条目"组合（e1e2 / e1e3 / e2e3 各出现 4 次），chunk2 装剩下
那个条目——设计上保证每个条目在两种 chunk 位置（size=2 与 size=1）都出现过、且共现对完全
均衡，唯一系统性差异来自条目本身对 ΔRMSE 的边际贡献。

已知效应（写死进 ΔRMSE 生成公式，不用任何随机数）：
  - e3 是"有害"条目：只要 chunk 里含 e3，ΔRMSE 比不含它高 0.30（系统性、跨位置一致）。
  - e1 / e2 中性：无系统性边际效应，只有极小的确定性摆动（sin/cos 驱动，避免设计矩阵退化
    到常数导致岭回归数值问题），不构成"有害"信号。
  - 全局慢趋势通过 iteration 线性项叠加（influence_regression._delta_rmse 应已用差分消掉，
    金标准据此验证差分/控制变量真的在起作用，而不是摆设）。

这是 Stage 2（influence_regression.py）的输入：assignments.csv + rmse_series.csv，
外加 Stage 2 读取的工作目录配置 influence_config.json（stations/models 字段）。
"""
import math
import os

HERE = os.path.dirname(os.path.abspath(__file__))
ENTRIES = ["e1", "e2", "e3"]
HARMFUL = "e3"
HARM_EFFECT = 0.30
N_ITERS = 12
MODEL = "M1"

# chunk1 的一对条目按迭代循环三种组合，chunk2 装剩下那个条目。
PAIR_CYCLE = [("e1", "e2"), ("e1", "e3"), ("e2", "e3")]


def _chunk1_pair(it):
    return PAIR_CYCLE[(it - 1) % len(PAIR_CYCLE)]


def _rmse_base(it, pos):
    """基线 RMSE：整体缓慢下降的训练趋势 + 小幅确定性摆动（sin/cos，非随机）。"""
    trend = 2.0 - 0.01 * (it * 2 + pos)  # 缓慢下降，验证差分能消掉这个趋势
    wiggle = 0.02 * math.sin(it * 0.7 + pos * 1.3)
    return trend + wiggle


def build_rows():
    """→ (assignments_rows, rmse_rows)。"""
    asg_rows = ["iteration,chunk,position,size,stations"]
    rmse_rows = ["iteration,chunk,position,model,rmse"]
    rmse_val = 2.0  # 累积游走：下一行 = 上一行 + 基线增量(含条目效应)
    for it in range(1, N_ITERS + 1):
        pair = _chunk1_pair(it)
        singleton = [e for e in ENTRIES if e not in pair][0]
        chunks = [(1, list(pair)), (2, [singleton])]
        for pos, (chunk_id, members) in enumerate(chunks, 1):
            asg_rows.append(
                f"{it},{chunk_id},{pos},{len(members)},{';'.join(members)}")
            delta = _rmse_base(it, pos) - 2.0  # 基线增量（含缓慢趋势+摆动，去掉常数偏置）
            if HARMFUL in members:
                delta += HARM_EFFECT
            rmse_val += delta
            rmse_rows.append(f"{it},{chunk_id},{pos},{MODEL},{rmse_val:.6f}")
    return asg_rows, rmse_rows


def main():
    asg_rows, rmse_rows = build_rows()
    with open(os.path.join(HERE, "assignments.csv"), "w", encoding="utf-8") as f:
        f.write("\n".join(asg_rows) + "\n")
    with open(os.path.join(HERE, "rmse_series.csv"), "w", encoding="utf-8") as f:
        f.write("\n".join(rmse_rows) + "\n")
    print(f"写出 assignments.csv（{len(asg_rows) - 1} 行）、"
          f"rmse_series.csv（{len(rmse_rows) - 1} 行），"
          f"{N_ITERS} 迭代 × 2 chunk，有害条目={HARMFUL}（效应={HARM_EFFECT}）")


if __name__ == "__main__":
    main()
