#!/usr/bin/env python3
"""确定性生成 architecture-attribution 的金标准输入（零随机，解析式构造）。

植入两个切片：
- far  ：model_b 对 model_a 的配对差 [0.20, 0.15, 0.25]（3 种子）→ mean=0.20、sd=0.05，z=4.0 > 3 → real。
- near ：配对差 [0.01, -0.02, 0.015] → 均值近 0、被方差主导 → |z|≈0.088 ≤ 3 → ~noise。
z 口径为效应量 mean/sd（不除 √n），见 scripts/slice_zcheck.py 的 paired_z 文档串。

只覆盖 Stage 0（现象定位/切片测量，slice_zcheck.py 的输入）——Stage 1-4（假设账本读取、
干预设计、subagent 执行判定、结论落笔）依赖真实假设账本/真实可训练框架/真实 subagent
执行，无法用确定性合成小样覆盖；ablation_verdict.verdict() 是纯函数，已在
scripts/tests/test_ablation_verdict.py 直接单测覆盖，不需要另外的 golden/gen_gate 包装
（同一取舍见 playbooks/subset-influence/golden/manifest.json 的 note）。"""
import csv
import os

HERE = os.path.dirname(os.path.abspath(__file__))

SEEDS = ("7", "1337", "2021")
FAR_B = ("1.20", "1.15", "1.25")     # model_a 恒 1.00 → diffs [0.20, 0.15, 0.25]
NEAR_B = ("1.01", "0.98", "1.015")   # model_a 恒 1.00 → diffs [0.01, -0.02, 0.015]


def main():
    path = os.path.join(HERE, "slice_metrics.csv")
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["slice", "seed", "model_a", "model_b"])
        for seed, b in zip(SEEDS, FAR_B):
            w.writerow(["far", seed, "1.00", b])
        for seed, b in zip(SEEDS, NEAR_B):
            w.writerow(["near", seed, "1.00", b])
    print(f"✓ 写 {path}")


if __name__ == "__main__":
    main()
