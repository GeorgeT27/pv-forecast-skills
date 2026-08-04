"""Stage 2 参考实现：影响力回归（playbook.md §5 Stage 2 引用的 influence_regression.py）。

薄 CLI 包装，直接调用生产脚本 `influence_regression.py` 的真实私有函数
（`_delta_rmse` / `_design` / `_analyze`），不重新实现回归逻辑——金标准钉住的是生产代码
的行为，不是本文件自己的一份平行实现。与生产 `main()` 的差异只是：从显式 CLI 路径读
assignments/rmse 而非 cwd 约定文件，并绕开 `si_common.load_config()` 对
`influence_config.json` 必须存在于 cwd 的硬要求（这里直接传 station_list/models）。

已知效应（见 ../make_golden.py）：条目 e3 系统性有害（跨位置 ΔRMSE +0.30），e1/e2 中性。
预期：influence_coefs.json 里 e3 的 theta 应为三者中最大且 CI 排除 0（>0）；
e1/e2 的 CI 应包含 0（或至少不满足"排除 0 且为正"）。
"""
import argparse
import json
import os
import sys

import pandas as pd

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                 "..", "..", "scripts"))
import influence_regression as ir  # noqa: E402


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--assignments", required=True)
    ap.add_argument("--rmse", required=True)
    ap.add_argument("--stations", required=True, help="逗号分隔条目列表，如 e1,e2,e3")
    ap.add_argument("--models", default="M1")
    ap.add_argument("--lam", type=float, default=1.0)
    ap.add_argument("--boot", type=int, default=1000)
    ap.add_argument("--out", required=True)
    a = ap.parse_args()

    asg = pd.read_csv(a.assignments)
    rms = pd.read_csv(a.rmse)
    station_list = [s.strip() for s in a.stations.split(",") if s.strip()]
    models = [m.strip() for m in a.models.split(",") if m.strip()]

    rms_d = ir._delta_rmse(rms)
    key2mem = ir._design(asg, station_list)
    out = ir._analyze(rms_d, key2mem, station_list, models, a.lam, a.boot)
    out["n_iterations"] = int(rms["iteration"].nunique())
    out["power_note"] = ("迭代数 < 10：只报排名，不下显著性结论"
                          if out["n_iterations"] < 10 else
                          f"迭代数 {out['n_iterations']}：CI 排除 0 的条目可报为'现象'")

    with open(a.out, "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=2)


if __name__ == "__main__":
    main()
