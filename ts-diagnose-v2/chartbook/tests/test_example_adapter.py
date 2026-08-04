"""示例适配器 golden：非标宽表（每行一窗、y_0..y_3/p_0..p_3 列）→ 规范长表，
对账两关（行数守恒 + 抽 3 窗数值核对）必须可执行且有牙（篡改即报）。"""
import sys
from pathlib import Path

import pandas as pd
import pytest

CB = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(CB / "scripts"))
sys.path.insert(0, str(CB / "golden" / "example_adapter"))

import chart_common as cc            # noqa: E402
import example_adapter as ea         # noqa: E402


def _wide():
    rows = []
    for m in ("A", "B"):
        for d in (1, 2, 3):
            rows.append({"station": "S1", "ts": f"2024-01-0{d} 00:00",
                         "model": m,
                         **{f"y_{s}": 10.0 + s for s in range(4)},
                         **{f"p_{s}": 10.0 + s + (0.5 if m == "A" else 1.0)
                            for s in range(4)}})
    return pd.DataFrame(rows)


def test_to_long_shape_and_values():
    wide = _wide()
    long = ea.to_long(wide, n_steps=4)
    assert list(long.columns) == list(cc.REQUIRED_COLS)
    assert len(long) == len(wide) * 4
    one = long[(long["model"] == "A") & (long["horizon_step"] == 2)].iloc[0]
    assert one["y_true"] == 12.0 and one["y_pred"] == 12.5


def test_reconcile_passes_and_has_teeth():
    wide = _wide()
    long = ea.to_long(wide, n_steps=4)
    rep = ea.reconcile(wide, long, n_steps=4)
    assert rep["row_conservation"] is True and len(rep["spot_checks"]) == 3
    with pytest.raises(AssertionError):
        ea.reconcile(wide, long.iloc[:-1], n_steps=4)   # 少一行 → 守恒破
    bad = long.copy()
    bad.loc[bad.index[0], "y_pred"] += 99
    with pytest.raises(AssertionError):
        ea.reconcile(wide, bad, n_steps=4)              # 数值篡改 → 抽查破


def test_long_feeds_chartbook(tmp_path):
    import chart_error_breakdown as ceb
    long = ea.to_long(_wide(), n_steps=4)
    p = tmp_path / "pred.csv"
    long.to_csv(p, index=False)
    st = ceb.compute(cc.load_predictions(p))
    assert set(st["models"]) == {"A", "B"}
