"""true-vs-pred-scatter golden：构造 y_pred = 0.8*y_true + 0.5（无噪声）→
slope/intercept/R² 精确回收；pred_by_true_bin 单调。"""
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

import chart_true_vs_pred_scatter as cts  # noqa: E402
from synth import make_long               # noqa: E402


def _df():
    df = make_long(["A"], ["U1"], ["2024-01-01", "2024-01-02"], 50,
                   err_fn=lambda m, u, w, s: -0.2 * (10.0 + s) + 0.5,
                   y_fn=lambda w, u, s: 10.0 + s)
    df["window_ts"] = pd.to_datetime(df["window_ts"])
    df["err"] = df["y_pred"] - df["y_true"]
    return df


def test_slope_intercept_r2():
    st = cts.compute(_df())
    a = st["models"]["A"]
    assert np.isclose(a["slope"], 0.8)
    assert np.isclose(a["intercept"], 0.5)
    assert a["r2"] > 0.9999
    assert a["n"] == 100


def test_bins_monotone():
    st = cts.compute(_df())
    binned = st["models"]["A"]["pred_by_true_bin"]
    vals = list(binned.values())
    assert vals == sorted(vals)
    assert len(binned) >= 5


def test_constant_truth_raises():
    df = _df()
    df["y_true"] = 7.0
    with pytest.raises(ValueError, match="y_true"):
        cts.compute(df)


def test_main_writes_outputs(tmp_path):
    p = tmp_path / "pred.csv"
    _df().drop(columns=["err"]).to_csv(p, index=False)
    cts.main(["--pred", str(p), "--out-dir", str(tmp_path)])
    assert (tmp_path / "true-vs-pred-scatter.json").exists()
    assert (tmp_path / "true-vs-pred-scatter.png").exists()
