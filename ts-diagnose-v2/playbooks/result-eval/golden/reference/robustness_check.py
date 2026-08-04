"""Stage 1/结论三道门 参考实现：稳健性门槛（playbook.md §2 Stage 4 引用的三道门第一道）。

钉住 `data_utils.robustness_check` 的判据契约：① 按天配对 Wilcoxon 符号秩检验显著
(p<0.05)；② 剔除差值最大的 3 天后均值差方向不变。两者都满足才 `passed=true`——
写"模型 A 比 B 好/差"之前必须先过这一步，否则只能写"差异不显著/由个别极端天驱动"。
金标准植入了两个大误差天（"个别极端天"），用来验证 trim 逻辑真的在起作用，不是
摆设：若脚本吞掉了 trim 步骤或 trim 数量算错，这两天会让方向稳定性判断跑偏。
"""
import argparse
import json
import os
import sys

import pandas as pd

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                 "..", "..", "scripts"))
import data_utils as du  # noqa: E402


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--data", required=True, help="CSV: timestamp,rmse_a,rmse_b")
    ap.add_argument("--trim", type=int, default=3)
    ap.add_argument("--out", required=True)
    a = ap.parse_args()

    df = pd.read_csv(a.data, parse_dates=["timestamp"])
    df = df.set_index("timestamp")
    result = du.robustness_check(df["rmse_a"], df["rmse_b"], trim=a.trim)
    result["n_rows"] = int(len(df))
    json.dump(result, open(a.out, "w", encoding="utf-8"), ensure_ascii=False, indent=2)


if __name__ == "__main__":
    main()
