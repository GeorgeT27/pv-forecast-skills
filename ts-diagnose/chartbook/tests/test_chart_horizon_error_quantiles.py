"""horizon-error-quantiles golden:幅度 0.1(h+1)、窗口奇偶定符号 → 分位带逐步精确回收。"""
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

import chart_horizon_error_quantiles as chq  # noqa: E402
from synth import make_long                  # noqa: E402

WINDOWS = ["2024-01-01", "2024-01-02", "2024-01-03", "2024-01-04"]


def _prep(df):
    df["window_ts"] = pd.to_datetime(df["window_ts"])
    df["err"] = df["y_pred"] - df["y_true"]
    return df


def _err(m, u, w, s):
    sign = 1.0 if WINDOWS.index(w) % 2 == 0 else -1.0
    return sign * 0.1 * (s + 1)


def test_bands_recovered():
    df = _prep(make_long(["A"], ["U1"], WINDOWS, 12, _err))
    st = chq.compute(df)
    a = st["models"]["A"]
    for h in range(12):
        amp = 0.1 * (h + 1)
        assert np.isclose(a["p95"]["curve"][str(h)], amp)
        assert np.isclose(a["p05"]["curve"][str(h)], -amp)
        assert np.isclose(a["p50"]["curve"][str(h)], 0.0)
        assert np.isclose(a["width90"]["curve"][str(h)], 2 * amp)
    assert np.isclose(a["growth_ratio"], 12.0)
    assert np.isclose(a["median_skew"], 0.0)
    assert a["n_per_step"] == 4


def test_main_writes_outputs(tmp_path):
    df = make_long(["A"], ["U1"], WINDOWS, 12, _err)
    p = tmp_path / "pred.csv"
    df.to_csv(p, index=False)
    chq.main(["--pred", str(p), "--out-dir", str(tmp_path)])
    assert (tmp_path / "horizon-error-quantiles.json").exists()
    assert (tmp_path / "horizon-error-quantiles.png").exists()
