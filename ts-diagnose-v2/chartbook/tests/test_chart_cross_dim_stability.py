"""cross-dim-stability golden：双稳构造精确回收（A 恒 0.8 vs B 恒 1.0 ⇒
两半差与两口径差全 −0.2）；口径翻转构造复刻 model-comparison 金标准
（A 按月 0.8/2.5/0.8 vs B 恒 1.5 ⇒ 时间对半各 −0.1333 稳、pooled 反超
+0.0843 翻转）。"""
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

import chart_cross_dim_stability as ccds  # noqa: E402
from synth import make_long, alt          # noqa: E402

WINDOWS = [f"2024-{mm:02d}-{dd:02d}" for mm in (1, 2, 3)
           for dd in (5, 10, 15, 20)]


def _prep(df):
    df["window_ts"] = pd.to_datetime(df["window_ts"])
    df["err"] = df["y_pred"] - df["y_true"]
    return df


def test_both_stable_exact():
    df = _prep(make_long(["A", "B"], ["U1"], WINDOWS, 8,
                         lambda m, u, w, s: alt(0.8 if m == "A" else 1.0, s)))
    st = ccds.compute(df, focal_model="A")
    p = st["pairs"]["B"]
    assert np.isclose(p["time_split"]["first_half_diff"], -0.2)
    assert np.isclose(p["time_split"]["second_half_diff"], -0.2)
    assert np.isclose(p["caliber_switch"]["row_diff"], -0.2)
    assert np.isclose(p["caliber_switch"]["pooled_diff"], -0.2)
    assert p["verdict"] == {"time_stable": True, "caliber_stable": True}


def test_caliber_flip_recovered():
    """复刻 playbook 金标准构造：时间对半两半各 −0.1333（稳），
    pooled 口径 A sqrt(2.51)=1.5843 反超 B 1.5（翻转）。"""
    amps = {"2024-01": 0.8, "2024-02": 2.5, "2024-03": 0.8}
    df = _prep(make_long(
        ["A", "B"], ["U1"], WINDOWS, 8,
        lambda m, u, w, s: alt(amps[w[:7]] if m == "A" else 1.5, s)))
    st = ccds.compute(df, focal_model="A")
    p = st["pairs"]["B"]
    ts = p["time_split"]
    assert ts["cut_ts"] == "2024-02-10" and ts["n_first"] == 6
    assert np.isclose(ts["first_half_diff"], -0.1333, atol=1e-3)
    assert np.isclose(ts["second_half_diff"], -0.1333, atol=1e-3)
    assert ts["consistent"] is True
    cs = p["caliber_switch"]
    assert np.isclose(cs["row_diff"], -0.1333, atol=1e-3)
    assert np.isclose(cs["pooled_diff"], 0.0843, atol=1e-3)
    assert cs["consistent"] is False
    assert p["verdict"] == {"time_stable": True, "caliber_stable": False}


def test_zero_half_diff_counts_as_unstable():
    """两半差为零（A、B 同幅）→ 按不稳处理，不算「稳定」。"""
    df = _prep(make_long(["A", "B"], ["U1"], WINDOWS, 8,
                         lambda m, u, w, s: alt(1.0, s)))
    st = ccds.compute(df, focal_model="A")
    assert st["pairs"]["B"]["verdict"]["time_stable"] is False


def test_unknown_focal_raises():
    df = _prep(make_long(["A", "B"], ["U1"], WINDOWS[:2], 4,
                         lambda m, u, w, s: alt(1.0, s)))
    with pytest.raises(ValueError, match="focal"):
        ccds.compute(df, focal_model="Z")


def test_single_model_raises():
    df = _prep(make_long(["A"], ["U1"], WINDOWS[:2], 4,
                         lambda m, u, w, s: alt(1.0, s)))
    with pytest.raises(ValueError, match="2"):
        ccds.compute(df, focal_model="A")


def test_main_writes_outputs(tmp_path):
    df = make_long(["A", "B"], ["U1"], WINDOWS[:4], 4,
                   lambda m, u, w, s: alt(1.0 if m == "A" else 1.2, s))
    p = tmp_path / "pred.csv"
    df.to_csv(p, index=False)
    ccds.main(["--pred", str(p), "--out-dir", str(tmp_path),
               "--focal-model", "A"])
    assert (tmp_path / "cross-dim-stability.json").exists()
    assert (tmp_path / "cross-dim-stability.png").exists()
