"""model-error-correlation golden：三模型行 RMSE 模式——A、B 逐窗完全同步
（corr=1，最同质对），C 与 A/B 正交交替（corr=0，最互补对）。<2 模型抛错。"""
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

import chart_model_error_correlation as cmc  # noqa: E402
from synth import make_long, alt             # noqa: E402


def _df():
    windows = [f"2024-01-{d:02d}" for d in range(1, 9)]   # 8 窗，idx=日-1

    def err(m, u, w, s):
        i = int(w[-2:]) - 1
        if m in ("A", "B"):
            amp = 1.0 if i % 2 == 0 else 2.0        # 1,2,1,2,...
        else:
            amp = 1.0 if (i // 2) % 2 == 0 else 2.0  # 1,1,2,2,...
        return alt(amp, s)

    df = make_long(["A", "B", "C"], ["U1"], windows, 4, err)
    df["window_ts"] = pd.to_datetime(df["window_ts"])
    df["err"] = df["y_pred"] - df["y_true"]
    return df


def test_corr_structure_recovered():
    st = cmc.compute(_df())
    corr = st["corr"]["all"]
    assert np.isclose(corr["A"]["B"], 1.0)
    assert abs(corr["A"]["C"]) < 1e-9
    assert st["most_redundant"]["pair"] == ["A", "B"]
    assert "C" in st["most_complementary"]["pair"]
    assert abs(st["most_complementary"]["corr"]) < 1e-9
    assert st["n_samples"] == 8


def test_single_model_raises():
    df = _df()
    with pytest.raises(ValueError, match="2"):
        cmc.compute(df[df["model"] == "A"])


def test_main_writes_outputs(tmp_path):
    p = tmp_path / "pred.csv"
    _df().drop(columns=["err"]).to_csv(p, index=False)
    cmc.main(["--pred", str(p), "--out-dir", str(tmp_path)])
    assert (tmp_path / "model-error-correlation.json").exists()
    assert (tmp_path / "model-error-correlation.png").exists()
