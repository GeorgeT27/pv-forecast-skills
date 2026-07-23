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


def _paired_df(bias=0.0, d=1.0, n_pairs=20):
    """配对 ±d 正交噪声:MZ OLS 精确回收 a=bias,b=1(零随机解析 golden)。"""
    p = np.repeat(np.linspace(1.0, 20.0, n_pairs), 2)
    e = np.tile([d, -d], n_pairs)
    return pd.DataFrame({"model": "A", "y_true": bias + p + e, "y_pred": p})


def test_mz_unbiased_exact():
    """无偏预测:a=0,b=1 精确回收,F=0,p=1——不拒绝无偏。"""
    mz = cts.compute(_paired_df())["models"]["A"]["mz"]
    assert np.isclose(mz["a"], 0.0, atol=1e-9)
    assert np.isclose(mz["b"], 1.0, atol=1e-9)
    assert np.isclose(mz["f_stat"], 0.0, atol=1e-9)
    assert np.isclose(mz["p_value"], 1.0)


def test_mz_biased_exact():
    """常数偏置 c=2:a=2,b=1 精确回收;F=(c²n/2)/(Σd²/(n−2)) 解析值,p≈0 拒绝。
    n=40,d=1:SSR_u=40,F=(4·40/2)/(40/38)=76·38/40=76.0。"""
    mz = cts.compute(_paired_df(bias=2.0))["models"]["A"]["mz"]
    assert np.isclose(mz["a"], 2.0, atol=1e-9)
    assert np.isclose(mz["b"], 1.0, atol=1e-9)
    assert np.isclose(mz["f_stat"], 76.0, atol=1e-6)
    assert mz["p_value"] < 1e-6


def test_mz_noiseless_degenerate():
    """既有无噪声夹具(y_pred=0.8y+0.5):SSR_u=0,F 发散→f_stat=None;
    SSR_r>0 → p=0 拒绝。反解 b=1/0.8=1.25,a=-0.5/0.8=-0.625。"""
    mz = cts.compute(_df())["models"]["A"]["mz"]
    assert np.isclose(mz["b"], 1.25)
    assert np.isclose(mz["a"], -0.625)
    assert mz["f_stat"] is None
    assert mz["p_value"] == 0.0


def test_mz_perfect_forecast():
    """y_pred==y_true:SSR_u=SSR_r=0,恰为无偏 → p=1。"""
    y = np.linspace(1.0, 9.0, 30)
    df = pd.DataFrame({"model": "A", "y_true": y, "y_pred": y})
    mz = cts.compute(df)["models"]["A"]["mz"]
    assert mz["f_stat"] is None
    assert mz["p_value"] == 1.0
