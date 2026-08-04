"""time-shift-diagnosis golden:周期 8 正弦形、y_pred=y_true 平移 2 步 → mode_shift=2。"""
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

import chart_time_shift_diagnosis as cts  # noqa: E402
from synth import make_long               # noqa: E402


def _y(s):
    return round(10.0 + 5.0 * np.sin(2 * np.pi * s / 8.0), 6)


def _prep(df):
    df["window_ts"] = pd.to_datetime(df["window_ts"])
    df["err"] = df["y_pred"] - df["y_true"]
    return df


def test_shift_2_recovered():
    # y_pred[s] = y_true[s−2] → 预测滞后 2 步
    df = _prep(make_long(["A"], ["U1", "U2"], ["2024-01-01", "2024-01-02"], 24,
                         lambda m, u, w, s: _y(s - 2) - _y(s),
                         y_fn=lambda w, u, s: _y(s)))
    a = cts.compute(df, max_shift=4)["models"]["A"]
    assert a["mode_shift"] == 2
    assert np.isclose(a["share_nonzero"], 1.0)
    assert np.isclose(a["mean_abs_shift"], 2.0)
    assert a["n_windows"] == 4


def test_zero_shift_control():
    df = _prep(make_long(["A"], ["U1"], ["2024-01-01"], 24,
                         lambda m, u, w, s: 0.0, y_fn=lambda w, u, s: _y(s)))
    a = cts.compute(df, max_shift=4)["models"]["A"]
    assert a["mode_shift"] == 0 and a["share_nonzero"] == 0.0


def test_main_writes_outputs(tmp_path):
    df = make_long(["A"], ["U1"], ["2024-01-01"], 24,
                   lambda m, u, w, s: 0.0, y_fn=lambda w, u, s: _y(s))
    p = tmp_path / "pred.csv"
    df.to_csv(p, index=False)
    cts.main(["--pred", str(p), "--out-dir", str(tmp_path), "--max-shift", "4"])
    assert (tmp_path / "time-shift-diagnosis.json").exists()
    assert (tmp_path / "time-shift-diagnosis.png").exists()
