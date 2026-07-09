#!/usr/bin/env python3
"""Step 1 数据质检（固化脚本，取代 SKILL.md 里的 heredoc）。

用法：在工作目录（有 analysis_config.json 的地方）跑
    python <skill>/scripts/run_quality_check.py

坏 label 会污染所有下游结论，所以这一步先于一切指标计算。逻辑与口径不在这里改——
列名对不上只改 data_utils.py 顶部 CONFIG 常量。
"""
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import data_utils as du


def _print_schema(path):
    """列名侦察：优先用 pyarrow 读 schema，缺则回退到 pandas dtypes。"""
    try:
        import pyarrow.parquet as pq
        print(pq.read_schema(path))
    except Exception:
        print(du.load_table(path).dtypes)


def main(config_path="analysis_config.json"):
    cfg = json.load(open(config_path))

    # 0) 列名侦察：与 data_utils.py 顶部 CONFIG 对不上时只改 CONFIG，不改逻辑。
    #    predicted.parquet 常把 timestamp 存成 index，schema 里看不到属正常，load_table 已兼容。
    print("=== schema (true_label) ===")
    _print_schema(cfg["true_label"])

    label = du.load_table(cfg["true_label"])
    print("\n=== 基础质检（重复戳 / 15min 网格缺口 / 常值段）===")
    print(du.basic_quality_checks(label))

    bad = du.check_window_consistency(label, du.LABEL_COL)   # 滚动窗口一致性抽查
    assert bad == 0, f"窗口不一致 {bad} 处——停下报告用户，取点口径全部不可信"
    print(f"窗口一致性: OK (bad={bad})")

    power = du.rebuild_series(label, du.LABEL_COL)            # 重建物理连续序列
    suspect = du.scan_suspect_days(power)
    suspect.to_csv("suspect_days.csv")
    print(f"\n可疑日 {len(suspect)} 天 → suspect_days.csv（交用户核对：限电/停机 vs 传感器故障）")

    # 训练集（5 站 2025 pooled）：不参与指标计算，是跨站漂移诊断的基准。
    # 可选——没放训练集时跳过（跨站漂移诊断 run_drift.py / 图#11/#12 也随之不可用，其余照常）。
    if cfg.get("train_set"):
        train = du.load_table(cfg["train_set"])
        print("\n=== 训练集抽查 ===")
        print("train:", du.basic_quality_checks(train))
        assert du.check_window_consistency(train, du.LABEL_COL) == 0, "训练集窗口不一致"
        print("训练集窗口一致性: OK")
    else:
        print("\n[跳过] 未配置 train_set —— 跨站漂移诊断（run_drift.py / 图#11/#12）本次不可用。")
    print("\n质检通过。可以进 Step 2（metric.py）与 Step 3（run_analysis.py）。")


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else "analysis_config.json")
