#!/usr/bin/env python3
"""feature-importance 金标准输入生成器——确定性构造，零随机。

场景：100 行分析表，目标列 error 由 x1 主导（error = 0.8·x1 + 0.15·sin(1.7k)），
x2 与目标无关（cos(k/5)），x3 为泄漏列（= 1.01·error，由目标派生）。
已知结果：泄漏列 x3 原始相关最高（榜首=分析错误不是发现），排除泄漏后 top-1 必须是 x1，
x2 相关接近 0。
"""
import math
import os

HERE = os.path.dirname(os.path.abspath(__file__))


def main():
    rows = ["x1,x2,x3,error"]
    for k in range(100):
        x1 = math.sin(k / 3.0)
        x2 = math.cos(k / 5.0)
        err = 0.8 * x1 + 0.15 * math.sin(1.7 * k)
        x3 = 1.01 * err
        rows.append(f"{x1:.6f},{x2:.6f},{x3:.6f},{err:.6f}")
    with open(os.path.join(HERE, "features.csv"), "w", encoding="utf-8") as f:
        f.write("\n".join(rows) + "\n")
    print(f"写出 features.csv（{len(rows) - 1} 行）")


if __name__ == "__main__":
    main()
