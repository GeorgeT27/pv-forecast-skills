"""intraday-profile golden：freq=1h、窗口起点 00:00、24 步 ⇒ 目标时刻==step；
植入 12 时误差幅度 3（其余 1）→ worst_hour 必须回收 12.0；纯正误差 → 偏度不对称回收。"""
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

import chart_intraday_profile as cip  # noqa: E402
from synth import make_long, alt      # noqa: E402


def _prep(df):
    df["window_ts"] = pd.to_datetime(df["window_ts"])
    df["err"] = df["y_pred"] - df["y_true"]
    return df


def test_worst_hour_recovered():
    def err(m, u, w, s):
        return alt(3.0 if s == 12 else 1.0, s)
    df = _prep(make_long(["A"], ["U1", "U2"], ["2024-01-01", "2024-01-02"], 24, err))
    st = cip.compute(df, freq="1h")
    a = st["models"]["A"]
    assert a["worst_hour"] == 12.0
    assert np.isclose(a["rmse_by_tod"]["curve"]["12.0"], 3.0)
    assert np.isclose(a["rmse_by_tod"]["curve"]["11.0"], 1.0)
    assert a["unit_worst_hour"]["U1"] == 12.0


def test_bias_asymmetry_all_positive_err():
    df = _prep(make_long(["A"], ["U1"], ["2024-01-01"], 24,
                         lambda m, u, w, s: 2.0))
    st = cip.compute(df, freq="1h")
    ba = st["models"]["A"]["bias_asymmetry"]
    assert ba["mean_over"] == 2.0 and ba["mean_under"] == 0.0


def test_main_writes_outputs(tmp_path):
    df = make_long(["A"], ["U1"], ["2024-01-01"], 24,
                   lambda m, u, w, s: alt(1.0, s))
    p = tmp_path / "pred.csv"
    df.to_csv(p, index=False)
    cip.main(["--pred", str(p), "--out-dir", str(tmp_path), "--freq", "1h"])
    assert (tmp_path / "intraday-profile.json").exists()
    assert (tmp_path / "intraday-profile.png").exists()
