"""oracle-gap golden：A 前 4 窗 RMSE 1/后 4 窗 2，B 相反 → 单模型均值 1.5、
oracle 均值 1.0、gap 0.5、pick_share 各 0.5。单模型抛错。"""
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

import chart_oracle_gap as cog    # noqa: E402
from synth import make_long, alt  # noqa: E402


def _df():
    windows = [f"2024-01-{d:02d}" for d in range(1, 9)]

    def err(m, u, w, s):
        i = int(w[-2:]) - 1
        first_half = i < 4
        amp = (1.0 if first_half else 2.0) if m == "A" else \
              (2.0 if first_half else 1.0)
        return alt(amp, s)

    df = make_long(["A", "B"], ["U1"], windows, 4, err)
    df["window_ts"] = pd.to_datetime(df["window_ts"])
    df["err"] = df["y_pred"] - df["y_true"]
    return df


def test_oracle_and_pick_share():
    st = cog.compute(_df())
    assert np.isclose(st["mean_rmse"]["A"], 1.5)
    assert np.isclose(st["mean_rmse"]["B"], 1.5)
    assert np.isclose(st["mean_rmse"]["oracle"], 1.0)
    assert np.isclose(st["best_single_minus_oracle"], 0.5)
    assert np.isclose(st["oracle_pick_share"]["A"], 0.5)
    assert np.isclose(st["oracle_pick_share"]["B"], 0.5)
    assert st["ensemble_minus_oracle"] is None


def test_single_model_raises():
    df = _df()
    with pytest.raises(ValueError, match="2"):
        cog.compute(df[df["model"] == "A"])


def test_main_writes_outputs(tmp_path):
    p = tmp_path / "pred.csv"
    _df().drop(columns=["err"]).to_csv(p, index=False)
    cog.main(["--pred", str(p), "--out-dir", str(tmp_path)])
    assert (tmp_path / "oracle-gap.json").exists()
    assert (tmp_path / "oracle-gap.png").exists()
