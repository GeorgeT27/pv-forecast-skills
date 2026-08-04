#!/usr/bin/env python3
"""robustness 金标准输入生成器——确定性构造，零随机。

场景：结论 C1「模型 A 优于 B」（metric 为误差，越小越好；diff = b−a，>0 = A 优）。
植入：差异**全部由 2 个极端单位驱动**（d03/d07 的 b−a = +2.0/+1.8，且都落在子期 1），
其余 18 个单位 B 略优（b−a 为 −0.033…−0.087 的小负数）。
已知结果：整体 baseline_diff > 0（A 看似优），但剔最差 k=3 后方向翻转、
子期 2 方向翻转、符号秩中位差为负——正是"假差异"的指纹，扰动矩阵必须抓出来。
"""
import os

HERE = os.path.dirname(os.path.abspath(__file__))
EXTREME = {"d03": 2.0, "d07": 1.8}


def main():
    rows = ["unit,period,metric_a,metric_b"]
    for i in range(1, 21):
        u = f"d{i:02d}"
        period = 1 if i <= 10 else 2
        a = 1.0 + 0.01 * i                       # 基线误差水平（确定性变化）
        d = EXTREME.get(u, -0.03 - 0.003 * i)    # b − a
        rows.append(f"{u},{period},{a:.6f},{a + d:.6f}")
    path = os.path.join(HERE, "paired_metrics.csv")
    with open(path, "w", encoding="utf-8") as f:
        f.write("\n".join(rows) + "\n")
    print(f"写出 paired_metrics.csv（{len(rows) - 1} 行）")


if __name__ == "__main__":
    main()
