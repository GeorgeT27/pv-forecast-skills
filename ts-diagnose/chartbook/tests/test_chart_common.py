"""chart_common 单测：长表校验 / row_rmse / 形状描述符 / 落盘双产物。"""
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))
sys.path.insert(0, str(Path(__file__).resolve().parent))

import chart_common as cc          # noqa: E402
from synth import make_long        # noqa: E402


def _write_csv(tmp_path, df):
    p = tmp_path / "pred.csv"
    df.to_csv(p, index=False)
    return p


def test_load_predictions_missing_col_raises(tmp_path):
    df = make_long(["A"], ["U1"], ["2024-01-01"], 4,
                   lambda m, u, w, s: 1.0).drop(columns=["y_pred"])
    with pytest.raises(ValueError, match="y_pred"):
        cc.load_predictions(_write_csv(tmp_path, df))


def test_load_predictions_adds_err_and_datetime(tmp_path):
    df = make_long(["A"], ["U1"], ["2024-01-01"], 4, lambda m, u, w, s: 2.0)
    out = cc.load_predictions(_write_csv(tmp_path, df))
    assert np.allclose(out["err"], 2.0)
    assert pd.api.types.is_datetime64_any_dtype(out["window_ts"])


def test_row_rmse_exact():
    # err = ±3 交替 ⇒ 每行 RMSE 恰为 3
    df = make_long(["A"], ["U1"], ["2024-01-01", "2024-01-02"], 8,
                   lambda m, u, w, s: 3.0 * (1 if s % 2 == 0 else -1))
    df["window_ts"] = pd.to_datetime(df["window_ts"])
    df["err"] = df["y_pred"] - df["y_true"]
    rr = cc.row_rmse(df)
    assert len(rr) == 2
    assert np.allclose(rr["rmse"], 3.0)
    assert set(rr.columns) == {"model", "unit_id", "window_ts", "rmse"}


def test_curve_stats_fields_and_values():
    st = cc.curve_stats([1.0, 1.0, 4.0, 2.0])
    assert st["trend"] == "上升"
    assert st["monotonic"] is False
    assert st["max_jump_idx"] == "1" and st["max_jump"] == 3.0
    assert st["argmax"] == "2" and st["argmin"] == "0"
    assert set(st) == {"curve", "trend", "monotonic", "max_jump_idx",
                       "max_jump", "roughness", "argmax", "argmin"}


def test_downsample_keeps_ends_and_bound():
    d = {str(i): i for i in range(2000)}
    out = cc.downsample(d, max_points=100)
    assert len(out) <= 100
    assert "0" in out and "1999" in out


def test_save_outputs_writes_json_and_png(tmp_path):
    import matplotlib.pyplot as plt
    fig, ax = plt.subplots()
    ax.plot([0, 1], [0, 1])
    stats = cc.save_outputs(fig, tmp_path, "demo-recipe", {"a": 1})
    assert stats == {"a": 1}
    assert (tmp_path / "demo-recipe.png").exists()
    loaded = json.loads((tmp_path / "demo-recipe.json").read_text())
    assert loaded == {"a": 1}
