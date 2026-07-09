#!/usr/bin/env python3
"""分布漂移诊断（固化脚本，取代 SKILL.md 里的 heredoc）。

用法（在有 analysis_config.json 的工作目录）：
    python <skill>/scripts/run_drift.py --cols GHI-solargis,observe_power_future
    # --cols  逗号分隔要查的列：气象列=特征漂移、功率标签列=标签漂移；
    #         SSRD_pos_* / t2m_pos_* / temp solargis 等按 schema 真实列名补。

回答第三类"为什么"：模型是不是遇到了训练年（2024）没见过的分布。三类漂移分开看，
含义完全不同——特征漂移（气象）/ 标签漂移（功率，看台阶）/ 映射漂移（功率-辐照曲线位移）。
天气型跨年对比**必须用 2024 作共享基准**（weather_class_drift 已内置），否则各年自归一化
会把"整体变暗 / 更多波动天"抹平。详见 references/drift-and-nwp.md。
"""
import argparse
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import data_utils as du
import plots


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--cols", default=f"{du.GHI_COL},{du.LABEL_COL}",
                    help="逗号分隔的列名（气象=特征漂移、功率=标签漂移）")
    ap.add_argument("--config", default="analysis_config.json")
    args = ap.parse_args()
    cols = [c.strip() for c in args.cols.split(",") if c.strip()]

    cfg = json.load(open(args.config))
    train = du.load_table(cfg["train_set"])    # 2024
    test = du.load_table(cfg["true_label"])    # 2025
    out = f"figures/{cfg['station']}/drift"
    os.makedirs(out, exist_ok=True)

    # 1) 特征 + 标签漂移数值总表（先定位哪个变量哪个月漂了，再看图）
    dt = du.drift_table(train, test, cols)
    dt.to_csv(f"{out}/drift_table.csv", index=False)
    print("=== 漂移总表（只列非稳定项）===")
    print(dt[dt.drift != "稳定"].to_string(index=False))

    # 2) 天气型漂移（kt/σΔ 分布 + 五类占比），2024 共享基准
    wd = du.weather_class_drift(du.rebuild_series(train, du.GHI_COL),
                                du.rebuild_series(test, du.GHI_COL))
    print("\n=== 五类天气占比 2024 vs 2025 ===")
    print(wd["share"])
    print("kt 漂移:", wd["kt"], "\nσΔ 漂移:", wd["sigma"])

    # 3) 图#11 逐变量同月分布对比、图#12 功率-辐照映射
    for col in cols:
        plots.fig11_train_test_dist(du.rebuild_series(train, col),
                                    du.rebuild_series(test, col), col,
                                    f"{out}/11_dist_{col}.png")
    plots.fig12_power_ghi_mapping(du.rebuild_series(train, du.LABEL_COL),
                                  du.rebuild_series(train, du.GHI_COL),
                                  du.rebuild_series(test, du.LABEL_COL),
                                  du.rebuild_series(test, du.GHI_COL),
                                  f"{out}/12_power_ghi_mapping.png")
    print(f"\n完成。drift_table.csv 与图在 {out}/ —— PSI>0.25 的变量-月份进 fig11 细看；"
          "结论进 Playbook A 第 5 步。")


if __name__ == "__main__":
    main()
