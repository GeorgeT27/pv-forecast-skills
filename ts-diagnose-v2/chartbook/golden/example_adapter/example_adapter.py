"""示例薄适配器：非标宽表 → 规范长表 + 对账两关。

这是 intake 对账纪律（references/intake.md）的可执行样例：现场写 adapter.py 时
照此模式——to_long 只做重排不做清洗，reconcile 行数守恒 + 抽 3 窗数值核对，
过账后才准喂 chartbook 图脚本。
"""
from __future__ import annotations

import pandas as pd


def to_long(wide: pd.DataFrame, n_steps: int) -> pd.DataFrame:
    rows = []
    for r in wide.itertuples():
        for s in range(n_steps):
            rows.append({"window_ts": r.ts, "unit_id": r.station,
                         "model": r.model, "horizon_step": s,
                         "y_true": getattr(r, f"y_{s}"),
                         "y_pred": getattr(r, f"p_{s}")})
    return pd.DataFrame(rows, columns=["window_ts", "unit_id", "model",
                                       "horizon_step", "y_true", "y_pred"])


def reconcile(wide: pd.DataFrame, long: pd.DataFrame, n_steps: int) -> dict:
    """对账两关：①行数守恒；②抽前 3 个源行核对每步数值。返回报告 dict，
    任一关不过直接 AssertionError（绝不静默）。"""
    assert len(long) == len(wide) * n_steps, \
        f"行数守恒破产：long={len(long)} != wide={len(wide)}×{n_steps}"
    checks = []
    for r in wide.head(3).itertuples():
        sub = long[(long["window_ts"] == r.ts) & (long["model"] == r.model)
                   & (long["unit_id"] == r.station)]
        assert len(sub) == n_steps, f"窗口 {r.ts}/{r.model} 步数不齐"
        for s in range(n_steps):
            row = sub[sub["horizon_step"] == s].iloc[0]
            assert row["y_true"] == getattr(r, f"y_{s}"), \
                f"抽查失败 {r.ts}/{r.model} step{s} y_true"
            assert row["y_pred"] == getattr(r, f"p_{s}"), \
                f"抽查失败 {r.ts}/{r.model} step{s} y_pred"
        checks.append({"ts": str(r.ts), "model": str(r.model), "ok": True})
    return {"row_conservation": True, "spot_checks": checks}
