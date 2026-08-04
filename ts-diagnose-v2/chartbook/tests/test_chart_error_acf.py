"""error-acf golden:逐窗均值误差=3cos(2π widx/8) → argmax_lag=8、acf[8]≈0.8。"""
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

import chart_error_acf as cea  # noqa: E402
from synth import make_long    # noqa: E402

WINDOWS = [f"2024-01-{d:02d}" for d in range(1, 31)] + \
          [f"2024-02-{d:02d}" for d in range(1, 11)]  # 40 窗


def _prep(df):
    df["window_ts"] = pd.to_datetime(df["window_ts"])
    df["err"] = df["y_pred"] - df["y_true"]
    return df


def _err(m, u, w, s):
    widx = WINDOWS.index(w)
    return 3.0 * np.cos(2 * np.pi * widx / 8.0)


def test_period_8_recovered():
    df = _prep(make_long(["A"], ["U1"], WINDOWS, 6, _err))
    a = cea.compute(df, max_lag=12)["models"]["A"]
    assert a["argmax_lag"] == 8
    assert a["acf"]["curve"]["8"] >= 0.75
    assert a["ljung_box"]["p"] < 0.01
    assert a["n"] == 40


def test_main_writes_outputs(tmp_path):
    df = make_long(["A"], ["U1"], WINDOWS, 6, _err)
    p = tmp_path / "pred.csv"
    df.to_csv(p, index=False)
    cea.main(["--pred", str(p), "--out-dir", str(tmp_path), "--max-lag", "12"])
    assert (tmp_path / "error-acf.json").exists()
    assert (tmp_path / "error-acf.png").exists()
