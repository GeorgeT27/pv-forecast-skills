"""horizon-degradation golden：解析式构造 48 步双模型——
A: s<24 恒 1.0，之后 1.0+0.1*(s-24)（早段斜率 0、晚段 0.1、U1 崩溃点 s=30）；
B: 2.0-0.01*s（缓降）。A/B 首个交叉在 s=31。全部必须回收。"""
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

import chart_horizon_degradation as chd  # noqa: E402
from synth import make_long, alt         # noqa: E402


def _target(m, s):
    if m == "A":
        return 1.0 if s < 24 else 1.0 + 0.1 * (s - 24)
    return 2.0 - 0.01 * s


def _df():
    df = make_long(["A", "B"], ["U1"], ["2024-01-01", "2024-01-02"], 48,
                   lambda m, u, w, s: alt(_target(m, s), s))
    df["window_ts"] = pd.to_datetime(df["window_ts"])
    df["err"] = df["y_pred"] - df["y_true"]
    return df


def test_slopes_recovered():
    st = chd.compute(_df())
    a = st["models"]["A"]
    assert abs(a["early_slope"]) < 1e-9
    assert np.isclose(a["late_slope"], 0.1)
    assert np.isclose(st["models"]["B"]["late_slope"], -0.01)


def test_crossing_and_collapse():
    st = chd.compute(_df())
    assert st["crossings"]["A|B"] == 31
    assert st["collapse_horizon"]["A"]["U1"] == 30
    assert st["collapse_horizon"]["B"]["U1"] is None


def test_curve_stats_present():
    st = chd.compute(_df())
    a = st["models"]["A"]["rmse_by_step"]
    assert np.isclose(a["curve"]["47"], 1.0 + 0.1 * 23)
    assert a["trend"] == "上升"


def test_main_writes_outputs(tmp_path):
    p = tmp_path / "pred.csv"
    _df().drop(columns=["err"]).to_csv(p, index=False)
    chd.main(["--pred", str(p), "--out-dir", str(tmp_path)])
    assert (tmp_path / "horizon-degradation.json").exists()
    assert (tmp_path / "horizon-degradation.png").exists()
