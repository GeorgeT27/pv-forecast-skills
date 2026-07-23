"""baseline-skill golden:y=100·widx+s;seasonal 基线 RMSE=100;三模型分别
验 skill=0 / 0.5 / copies_persistence。"""
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

import chart_baseline_skill as cbs  # noqa: E402
from synth import make_long, alt    # noqa: E402

WINDOWS = ["2024-01-01", "2024-01-02", "2024-01-03", "2024-01-04"]


def _y(w, u, s):
    return 100.0 * WINDOWS.index(w) + float(s)


def _err(m, u, w, s):
    if m == "seasonal_copy":       # y_pred = y(target−24) = y − 100
        return -100.0
    if m == "half_err":            # RMSE 50 → skill_vs_seasonal = 0.5
        return alt(50.0, s)
    if m == "persist_copy":        # y_pred = y(window 发起时刻) = 100·widx
        return -float(s)
    raise AssertionError(m)


def _prep(df):
    df["window_ts"] = pd.to_datetime(df["window_ts"])
    df["err"] = df["y_pred"] - df["y_true"]
    return df


def _mk():
    return _prep(make_long(["seasonal_copy", "half_err", "persist_copy"],
                           ["U1"], WINDOWS, 24, _err, y_fn=_y))


def test_seasonal_skills():
    st = cbs.compute(_mk(), period_steps=24, freq="1h")
    assert np.isclose(st["baselines"]["seasonal_naive"], 100.0)
    ms = st["models"]
    assert np.isclose(ms["seasonal_copy"]["skill_vs_seasonal"], 0.0)
    assert np.isclose(ms["half_err"]["skill_vs_seasonal"], 0.5)


def test_persistence_copy_flagged():
    st = cbs.compute(_mk(), period_steps=24, freq="1h")
    m = st["models"]["persist_copy"]
    assert m["copies_persistence"] is True
    assert np.isclose(m["dist_to_persistence"], 0.0)
    # 两个阴性对照:half_err(纯半误差)与 seasonal_copy(抄季节)都不得触发
    assert st["models"]["half_err"]["copies_persistence"] is False
    assert st["models"]["seasonal_copy"]["copies_persistence"] is False


def test_no_period_degrades():
    st = cbs.compute(_mk(), period_steps=None, freq="1h", auto_detect=False)
    assert st["period_steps"] is None
    assert "seasonal_naive" not in st["baselines"]
    assert "skill_vs_seasonal" not in st["models"]["half_err"]


def test_main_writes_outputs(tmp_path):
    df = make_long(["half_err"], ["U1"], WINDOWS, 24,
                   lambda m, u, w, s: alt(50.0, s), y_fn=_y)
    p = tmp_path / "pred.csv"
    df.to_csv(p, index=False)
    cbs.main(["--pred", str(p), "--out-dir", str(tmp_path),
              "--period-steps", "24", "--freq", "1h"])
    assert (tmp_path / "baseline-skill.json").exists()
    assert (tmp_path / "baseline-skill.png").exists()
