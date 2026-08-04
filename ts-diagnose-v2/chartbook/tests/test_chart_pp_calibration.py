"""pp-calibration golden:y_pred=0.8·y_true(y=10+s 非退化)→ slope 与两尾比值精确回收。"""
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

import chart_pp_calibration as cpc  # noqa: E402
from synth import make_long         # noqa: E402
import pandas as pd                 # noqa: E402


def _prep(df):
    df["window_ts"] = pd.to_datetime(df["window_ts"])
    df["err"] = df["y_pred"] - df["y_true"]
    return df


def test_scale_08_recovered():
    y_fn = lambda w, u, s: 10.0 + s
    df = _prep(make_long(["A"], ["U1"], ["2024-01-01", "2024-01-02"], 24,
                         lambda m, u, w, s: -0.2 * (10.0 + s), y_fn=y_fn))
    st = cpc.compute(df)
    a = st["models"]["A"]
    assert np.isclose(a["slope"], 0.8)
    assert np.isclose(a["high_tail_ratio"], 0.8)
    assert np.isclose(a["low_tail_ratio"], 0.8)
    for q in a["quantiles"]:
        if q["ratio"] is not None:
            assert np.isclose(q["ratio"], 0.8)


def test_identity_gives_slope_1():
    df = _prep(make_long(["A"], ["U1"], ["2024-01-01"], 24,
                         lambda m, u, w, s: 0.0, y_fn=lambda w, u, s: 10.0 + s))
    st = cpc.compute(df)
    assert np.isclose(st["models"]["A"]["slope"], 1.0)


def test_main_writes_outputs(tmp_path):
    df = make_long(["A"], ["U1"], ["2024-01-01"], 24,
                   lambda m, u, w, s: 0.0, y_fn=lambda w, u, s: 10.0 + s)
    p = tmp_path / "pred.csv"
    df.to_csv(p, index=False)
    cpc.main(["--pred", str(p), "--out-dir", str(tmp_path)])
    assert (tmp_path / "pp-calibration.json").exists()
    assert (tmp_path / "pp-calibration.png").exists()
