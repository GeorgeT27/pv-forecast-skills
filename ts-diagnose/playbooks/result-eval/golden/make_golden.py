#!/usr/bin/env python3
"""result-eval 金标准输入生成器——确定性构造，零随机。

场景：30 天、每天 4 个日内样本点的配对 RMSE 序列（模型 A vs 模型 B）。
A 的 RMSE = 1.0 + 0.05·sin(d+h)（小幅日内波动，无趋势）。
B 的 RMSE = A + 0.15 + 0.03·cos(1.3d+h)（系统性比 A 差 0.15，同样小幅波动）。
另在第 6、18 天（d=5,17，0-indexed）给 B 加 1.2 的大误差（模拟"个别极端天"），
用来验证稳健性门槛的"剔除最差 3 天后方向不变"这条判据真的在起作用——若脚本
错误地不做 trim 或 trim 逻辑错了，这两个植入的极端天会让 mean_diff 与
trimmed_mean_diff 的关系判断错。

已知结果：Wilcoxon 配对检验显著（B 全程系统性更差，p 应远小于 0.05），
剔除最大差值 3 天后均值差方向不变（trimmed_mean_diff 与 mean_diff 同号）——
即 `data_utils.robustness_check` 应返回 `passed: true`。
"""
import math
import os

HERE = os.path.dirname(os.path.abspath(__file__))
N_DAYS = 30
OUTLIER_DAYS = (5, 17)  # 0-indexed，模拟"个别极端天"，不应翻转方向判定


def main():
    rows = ["timestamp,rmse_a,rmse_b"]
    for d in range(N_DAYS):
        for h in range(4):
            ts = f"2025-01-{d + 1:02d}T{h * 6:02d}:00:00"
            a = 1.0 + 0.05 * math.sin(d + h)
            b = a + 0.15 + 0.03 * math.cos(1.3 * d + h)
            if d in OUTLIER_DAYS:
                b += 1.2
            rows.append(f"{ts},{a:.6f},{b:.6f}")
    with open(os.path.join(HERE, "rmse_pairs.csv"), "w", encoding="utf-8") as f:
        f.write("\n".join(rows) + "\n")
    print(f"写出 rmse_pairs.csv（{len(rows) - 1} 行，{N_DAYS} 天）")


if __name__ == "__main__":
    main()
