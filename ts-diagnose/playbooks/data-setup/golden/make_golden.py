#!/usr/bin/env python3
"""data-setup 金标准：确定性宽表（零随机）。难例植入：B 缺第 3 窗（不对称覆盖）
——对齐后 n_aligned=2、dropped 不对称，适配器必须如实入报告而非静默取交集。"""
import pandas as pd


def main():
    rows = []
    for m, bias, n_win in (("A", 0.0, 3), ("B", 0.5, 2)):
        for w in range(n_win):
            row = {"ts": f"2024-01-0{w + 1}T00:00:00", "station": "S1", "model": m}
            for s in range(4):
                row[f"y_{s}"] = float(w + s)
                row[f"p_{s}"] = float(w + s) + bias
            rows.append(row)
    pd.DataFrame(rows).to_csv("wide.csv", index=False)


if __name__ == "__main__":
    main()
