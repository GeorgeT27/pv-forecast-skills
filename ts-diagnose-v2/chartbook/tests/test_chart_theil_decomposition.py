"""theil-decomposition golden:纯偏移→u_bias=1;纯幅度失配(均值对齐、r=1)→u_var=1。"""
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

import chart_theil_decomposition as ctd  # noqa: E402
from synth import make_long              # noqa: E402


def _prep(df):
    df["window_ts"] = pd.to_datetime(df["window_ts"])
    df["err"] = df["y_pred"] - df["y_true"]
    return df


def test_pure_bias():
    df = _prep(make_long(["A"], ["U1"], ["2024-01-01"], 24,
                         lambda m, u, w, s: 2.0, y_fn=lambda w, u, s: 10.0 + s))
    o = ctd.compute(df)["models"]["A"]["overall"]
    assert np.isclose(o["u_bias"], 1.0)
    assert np.isclose(o["u_var"], 0.0) and np.isclose(o["u_cov"], 0.0)
    assert np.isclose(o["mse"], 4.0)


def test_pure_variance():
    # y_t = s (mean 11.5), y_p = 2s − 11.5 (同均值、2 倍标准差、r=1) → u_var=1
    df = _prep(make_long(["A"], ["U1"], ["2024-01-01"], 24,
                         lambda m, u, w, s: float(s) - 11.5,
                         y_fn=lambda w, u, s: float(s)))
    o = ctd.compute(df)["models"]["A"]["overall"]
    assert np.isclose(o["u_var"], 1.0)
    assert np.isclose(o["u_bias"], 0.0) and np.isclose(o["u_cov"], 0.0)


def test_zero_mse_gives_null():
    df = _prep(make_long(["A"], ["U1"], ["2024-01-01"], 24,
                         lambda m, u, w, s: 0.0, y_fn=lambda w, u, s: 10.0 + s))
    o = ctd.compute(df)["models"]["A"]["overall"]
    assert o["u_bias"] is None and o["mse"] == 0.0


def test_main_writes_outputs(tmp_path):
    df = make_long(["A"], ["U1"], ["2024-01-01"], 24,
                   lambda m, u, w, s: 2.0, y_fn=lambda w, u, s: 10.0 + s)
    p = tmp_path / "pred.csv"
    df.to_csv(p, index=False)
    ctd.main(["--pred", str(p), "--out-dir", str(tmp_path)])
    assert (tmp_path / "theil-decomposition.json").exists()
    assert (tmp_path / "theil-decomposition.png").exists()
