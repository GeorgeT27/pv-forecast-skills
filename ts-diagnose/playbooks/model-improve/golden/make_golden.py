#!/usr/bin/env python3
"""确定性金标准：一轮四条候选，答案已知——E001 keep / E002 discard（更差）/ E003 undecided（噪声内）
/ E004 discard（整体变好但守护切片 far 退化）。零随机；改期望先改这里并重跑 pytest。"""
import json
import os

HERE = os.path.dirname(os.path.abspath(__file__))
DOC = {"champion_mean": 0.2000, "noise_floor_3sigma": 0.0060,
       "candidates": [
           {"exp_id": "E001", "hypothesis_id": "F1", "per_seed": [0.180, 0.181, 0.179]},
           {"exp_id": "E002", "hypothesis_id": "F2", "per_seed": [0.221, 0.220, 0.219]},
           {"exp_id": "E003", "hypothesis_id": "F3", "per_seed": [0.199, 0.198, 0.200]},
           {"exp_id": "E004", "hypothesis_id": "F4", "per_seed": [0.178, 0.179, 0.180],
            "guards": {"horizon:far": {"per_seed": [0.30, 0.31, 0.29], "champion_mean": 0.26,
                                       "noise_floor": 0.006}}}]}

if __name__ == "__main__":
    with open(os.path.join(HERE, "fake_round.json"), "w", encoding="utf-8") as f:
        json.dump(DOC, f, ensure_ascii=False, indent=2)
    print("✓ fake_round.json")
