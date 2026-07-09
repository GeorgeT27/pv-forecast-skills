#!/usr/bin/env python3
"""分布漂移诊断（固化脚本，取代 SKILL.md 里的 heredoc）。

跨站设定（2026-07-09）：train_set = 5 站 2025 pooled，true_label = 留出测试站雅砻江。
漂移是**跨站**的——回答"雅砻江是不是落在训练站没覆盖的分布里、最像哪个训练站"。

用法（在有 analysis_config.json 的工作目录）：
    python <skill>/scripts/run_drift.py --cols GHI-solargis,observe_power_future
    # --cols  逗号分隔要查的列：气象列=特征漂移、功率标签列=标签漂移；
    #         SSRD_pos_* / t2m_pos_* / temp solargis 等按 schema 真实列名补。
    # 逐站对比：config 里给 "train_stations": {站名: 路径}，脚本对每个训练站单独 vs 雅砻江，
    #          输出逐站 PSI 便于排"最像→最不像"，找迁移锚与盲区。

三类漂移分开看，含义完全不同——特征漂移（气象）/ 标签漂移（功率，看尺度台阶）/ 映射漂移
（功率-辐照曲线位移）。天气型跨站对比**必须用训练站作共享基准**（weather_class_drift 已内置），
否则各自归一化会把"雅砻江整体更亮/更少波动"抹平。详见 references/drift-and-nwp.md。
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
    train = du.load_table(cfg["train_set"])    # 5 站 pooled 2025
    test = du.load_table(cfg["true_label"])    # 雅砻江（留出测试站）2025
    out = f"figures/{cfg['station']}/drift"
    os.makedirs(out, exist_ok=True)

    # 1) 特征 + 标签漂移数值总表（先定位哪个变量哪个月漂了，再看图）
    dt = du.drift_table(train, test, cols)
    dt.to_csv(f"{out}/drift_table.csv", index=False)
    print("=== 漂移总表（只列非稳定项）===")
    print(dt[dt.drift != "稳定"].to_string(index=False))

    # 2) 天气型漂移（kt/σΔ 分布 + 五类占比），训练站作共享基准
    wd = du.weather_class_drift(du.rebuild_series(train, du.GHI_COL),
                                du.rebuild_series(test, du.GHI_COL))
    print("\n=== 五类天气占比：训练站(pooled) vs 雅砻江 ===")
    print(wd["share"])
    print("kt 漂移:", wd["kt"], "\nσΔ 漂移:", wd["sigma"])

    # 2b) 逐站对比（可选）：找雅砻江最像哪个训练站——按 GHI 的 PSI 排序
    if cfg.get("train_stations"):
        print("\n=== 逐站漂移：雅砻江 vs 各训练站（GHI PSI，小=最像）===")
        rows = []
        for name, path in cfg["train_stations"].items():
            st = du.load_table(path)
            p = du.psi(du.rebuild_series(st, du.GHI_COL).dropna().to_numpy(),
                       du.rebuild_series(test, du.GHI_COL).dropna().to_numpy())
            rows.append((name, round(float(p), 3)))
        for name, p in sorted(rows, key=lambda x: x[1]):
            print(f"  {name:20s} GHI_PSI={p}")
        print("  → 最小=迁移锚（雅砻江最像的训练站），最大=盲区")

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
