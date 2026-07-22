"""rolling-stability golden：60 天单模型，第 31 天起日 RMSE 从 1.0 跳 2.0 →
变点日期 2024-01-31（±0 天，构造是干净台阶）、before/after 均值与 shift 回收；
平坦段不得再报变点（阈值闸有牙）。"""
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

import chart_rolling_stability as crs  # noqa: E402
from synth import make_long, alt       # noqa: E402


def _df():
    days = pd.date_range("2024-01-01", periods=60, freq="D")
    windows = [d.strftime("%Y-%m-%d") for d in days]

    def err(m, u, w, s):
        day_idx = (pd.Timestamp(w) - days[0]).days
        return alt(1.0 if day_idx < 30 else 2.0, s)

    df = make_long(["A"], ["U1"], windows, 4, err)
    df["window_ts"] = pd.to_datetime(df["window_ts"])
    df["err"] = df["y_pred"] - df["y_true"]
    return df


def test_changepoint_recovered():
    st = crs.compute(_df())
    cps = st["models"]["A"]["changepoints"]
    assert len(cps) == 1
    cp = cps[0]
    assert cp["date"] == "2024-01-31"
    assert np.isclose(cp["before_mean"], 1.0)
    assert np.isclose(cp["after_mean"], 2.0)
    assert np.isclose(cp["shift"], 1.0)


def test_calendar_slices():
    st = crs.compute(_df())
    a = st["models"]["A"]
    assert np.isclose(a["by_month"]["2024-02"], 2.0)
    assert set(a["by_dayofweek"]) <= {"0", "1", "2", "3", "4", "5", "6"}


def test_series_and_curve_present():
    st = crs.compute(_df())
    a = st["models"]["A"]
    assert len(a["daily_rmse"]) == 60
    assert len(a["rolling_rmse"]) == 60
    # curve_stats 的 max_jump_idx 取跳变的左端点日（与变点 date=后段首日相邻一天）
    assert a["daily_curve"]["max_jump_idx"] == "2024-01-30"


def test_main_writes_outputs(tmp_path):
    p = tmp_path / "pred.csv"
    _df().drop(columns=["err"]).to_csv(p, index=False)
    crs.main(["--pred", str(p), "--out-dir", str(tmp_path)])
    assert (tmp_path / "rolling-stability.json").exists()
    assert (tmp_path / "rolling-stability.png").exists()
