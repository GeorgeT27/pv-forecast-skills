"""worst-slice-compare golden：A 仅 2024-02 差（RMSE 3，其余 1），B 恒 1 →
最差片=2024-02、片内 A=3/B=1、gap 全部集中该片（concentration_ratio=1）。"""
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

import chart_worst_slice_compare as cwsc  # noqa: E402
from synth import make_long, alt          # noqa: E402


def _df():
    windows = [f"2024-{mm:02d}-{dd:02d}" for mm in (1, 2, 3)
               for dd in (5, 15, 25)]

    def err(m, u, w, s):
        amp = 3.0 if (m == "A" and w.startswith("2024-02")) else 1.0
        return alt(amp, s)

    df = make_long(["A", "B"], ["U1"], windows, 4, err)
    df["window_ts"] = pd.to_datetime(df["window_ts"])
    df["err"] = df["y_pred"] - df["y_true"]
    return df


def test_worst_slice_and_compare():
    st = cwsc.compute(_df(), focal_model="A")
    assert st["worst_slice"] == "2024-02"
    assert np.isclose(st["in_slice"]["A"], 3.0)
    assert np.isclose(st["in_slice"]["B"], 1.0)
    assert np.isclose(st["slice_gaps"]["2024-02"], 2.0)
    assert np.isclose(st["slice_gaps"]["2024-01"], 0.0)
    assert np.isclose(st["concentration_ratio"], 1.0)
    assert "2024-02-15" in st["daily_in_slice"]["A"]


def test_unknown_focal_raises():
    with pytest.raises(ValueError, match="focal"):
        cwsc.compute(_df(), focal_model="Z")


def test_single_model_raises():
    df = _df()
    with pytest.raises(ValueError, match="2"):
        cwsc.compute(df[df["model"] == "A"], focal_model="A")


def test_main_writes_outputs(tmp_path):
    p = tmp_path / "pred.csv"
    _df().drop(columns=["err"]).to_csv(p, index=False)
    cwsc.main(["--pred", str(p), "--out-dir", str(tmp_path),
               "--focal-model", "A"])
    assert (tmp_path / "worst-slice-compare.json").exists()
    assert (tmp_path / "worst-slice-compare.png").exists()
