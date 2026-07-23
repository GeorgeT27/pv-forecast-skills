"""revision-stability golden:收敛 vs 跳变双模型;单覆盖抛 ValueError。"""
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

import chart_revision_stability as crs  # noqa: E402
from synth import make_long             # noqa: E402

WINDOWS = [f"2024-01-01 {h:02d}:00:00" for h in range(6)]  # 1h 间隔 6 窗


def _err(m, u, w, s):
    lead = s  # horizon_step 即 lead
    if m == "converge":
        return float(lead)
    if m == "jumpy":
        return 2.0 if lead % 2 == 0 else -2.0
    raise AssertionError(m)


def _prep(df):
    df["window_ts"] = pd.to_datetime(df["window_ts"])
    df["err"] = df["y_pred"] - df["y_true"]
    return df


def test_converge_vs_jumpy():
    df = _prep(make_long(["converge", "jumpy"], ["U1"], WINDOWS, 6, _err))
    st = crs.compute(df, freq="1h")
    c, j = st["models"]["converge"], st["models"]["jumpy"]
    assert c["n_targets"] >= 2 and j["n_targets"] >= 2
    assert j["smapc"] > 2 * c["smapc"]
    assert c["convergence_ratio"] < 0.5
    assert len(c["sample_trajectories"]) >= 1


def test_no_overlap_raises():
    df = _prep(make_long(["converge"], ["U1"],
                         ["2024-01-01", "2024-02-01"], 6, _err))
    try:
        crs.compute(df, freq="1h")
        assert False, "应抛 ValueError"
    except ValueError as e:
        assert "覆盖" in str(e)


def test_main_writes_outputs(tmp_path):
    df = make_long(["converge"], ["U1"], WINDOWS, 6, _err)
    p = tmp_path / "pred.csv"
    df.to_csv(p, index=False)
    crs.main(["--pred", str(p), "--out-dir", str(tmp_path), "--freq", "1h"])
    assert (tmp_path / "revision-stability.json").exists()
    assert (tmp_path / "revision-stability.png").exists()
