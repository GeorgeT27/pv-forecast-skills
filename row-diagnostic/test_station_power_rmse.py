"""station_power_rmse.py 单测：时间对齐 + 重叠窗去重 + 站列匹配 + 特征图 + 鲁棒缺失 + 去夜间。

data 埋点（power 基本盘）：station1 两重叠窗→5唯一点 RMSE=2；station2 RMSE=3；station3 无预测列→跳过。
data2 埋点（特征 + 鲁棒 + 夜间）：
  - station1：power(含 03:00 夜间窗) + GHI(pred=真值+4→RMSE4，仅白天)；
  - station2：只有 power(RMSE3)，GHI_SOLARGIS_predict 全 None → GHI 图跳过但 power 照出；
  - station3：预测表无该列（power 跳过）但 GHI 齐(pred=真值+5→RMSE5) → 仍出 GHI 图。
"""
import os
import subprocess
import sys

import numpy as np
import pandas as pd
import pytest

HERE = os.path.dirname(os.path.abspath(__file__))
SCRIPT = os.path.join(HERE, "station_power_rmse.py")


# ---------------------------------------------------------------- data（power 基本盘）
@pytest.fixture
def data(tmp_path):
    def win(rows, station, T, future):
        rows.append({"station": station, "timestamp_win": pd.Timestamp(T),
                     "observe_power": 1.0, "observe_power_future": [float(x) for x in future]})
    rows = []
    win(rows, "station1", "2026-07-16 10:00:00", [10, 20, 30, 40])
    win(rows, "station1", "2026-07-16 10:15:00", [20, 30, 40, 50])
    win(rows, "station2", "2026-07-16 10:00:00", [5, 15, 25, 35])
    win(rows, "station3", "2026-07-16 10:00:00", [1, 2, 3, 4])
    pd.DataFrame(rows).to_parquet(tmp_path / "input.parquet")
    dt = pd.date_range("2026-07-16 10:15:00", "2026-07-16 11:15:00", freq="15min")
    tr1 = {pd.Timestamp("2026-07-16 10:15"): 10, pd.Timestamp("2026-07-16 10:30"): 20,
           pd.Timestamp("2026-07-16 10:45"): 30, pd.Timestamp("2026-07-16 11:00"): 40,
           pd.Timestamp("2026-07-16 11:15"): 50}
    tr2 = {pd.Timestamp("2026-07-16 10:15"): 5, pd.Timestamp("2026-07-16 10:30"): 15,
           pd.Timestamp("2026-07-16 10:45"): 25, pd.Timestamp("2026-07-16 11:00"): 35}
    pred = pd.DataFrame({"dtime": dt})
    pred["station1"] = [tr1[t] + 2 if t in tr1 else np.nan for t in dt]
    pred["station2"] = [tr2[t] + 3 if t in tr2 else np.nan for t in dt]
    pred.to_parquet(tmp_path / "predict.parquet")
    return tmp_path


# ---------------------------------------------------------------- data2（特征 + 鲁棒 + 夜间）
@pytest.fixture
def data2(tmp_path):
    def row(station, T, power, ghi_pred, ghi_true):
        return {"station": station, "timestamp_win": pd.Timestamp(T), "observe_power": 1.0,
                "observe_power_future": power, "GHI_SOLARGIS_predict": ghi_pred,
                "GHI_real_future": ghi_true}
    rows = [
        # station1: 两白天重叠窗 + 一夜间窗；GHI 仅白天，pred=真值+4
        row("station1", "2026-07-16 10:00:00", [10., 20, 30, 40], [104., 114, 124, 134], [100., 110, 120, 130]),
        row("station1", "2026-07-16 10:15:00", [20., 30, 40, 50], [114., 124, 134, 144], [110., 120, 130, 140]),
        row("station1", "2026-07-16 03:00:00", [1., 2, 3, 4], None, None),
        # station2: 只有 power；GHI_SOLARGIS_predict 全 None → GHI 图跳过
        row("station2", "2026-07-16 10:00:00", [5., 15, 25, 35], None, [1., 2, 3, 4]),
        # station3: 预测表无该列（power 跳过）；GHI 齐，pred=真值+5
        row("station3", "2026-07-16 10:00:00", [1., 2, 3, 4], [205., 215, 225, 235], [200., 210, 220, 230]),
    ]
    pd.DataFrame(rows).to_parquet(tmp_path / "input.parquet")
    dt = pd.date_range("2026-07-16 03:00:00", "2026-07-16 11:30:00", freq="15min")
    tr1 = {pd.Timestamp("2026-07-16 10:15"): 10, pd.Timestamp("2026-07-16 10:30"): 20,
           pd.Timestamp("2026-07-16 10:45"): 30, pd.Timestamp("2026-07-16 11:00"): 40,
           pd.Timestamp("2026-07-16 11:15"): 50,
           pd.Timestamp("2026-07-16 03:15"): 1, pd.Timestamp("2026-07-16 03:30"): 2,
           pd.Timestamp("2026-07-16 03:45"): 3, pd.Timestamp("2026-07-16 04:00"): 4}
    tr2 = {pd.Timestamp("2026-07-16 10:15"): 5, pd.Timestamp("2026-07-16 10:30"): 15,
           pd.Timestamp("2026-07-16 10:45"): 25, pd.Timestamp("2026-07-16 11:00"): 35}
    pred = pd.DataFrame({"dtime": dt})
    pred["station1"] = [tr1[t] + 2 if t in tr1 else np.nan for t in dt]
    pred["station2"] = [tr2[t] + 3 if t in tr2 else np.nan for t in dt]
    pred.to_parquet(tmp_path / "predict.parquet")
    return tmp_path


def run(wd, extra=()):
    r = subprocess.run(
        [sys.executable, SCRIPT, "--input", str(wd / "input.parquet"),
         "--predict", str(wd / "predict.parquet"), "--out-dir", str(wd / "out"), "--no-plots"] + list(extra),
        cwd=str(wd), capture_output=True, text=True)
    assert r.returncode == 0, r.stdout + r.stderr
    power = (pd.read_csv(wd / "out" / "station_power_rmse.csv")
             if os.path.exists(wd / "out" / "station_power_rmse.csv") else None)
    feat = (pd.read_csv(wd / "out" / "station_feature_rmse.csv")
            if os.path.exists(wd / "out" / "station_feature_rmse.csv") else None)
    return power, feat, r.stdout


def test_rmse_and_overlap_dedupe(data):
    power, _, _ = run(data)
    s1 = power[power.station == "station1"].iloc[0]
    s2 = power[power.station == "station2"].iloc[0]
    assert s1["power_rmse"] == pytest.approx(2.0) and s1["n_points"] == 5
    assert s2["power_rmse"] == pytest.approx(3.0) and s2["n_points"] == 4


def test_missing_station_skipped(data):
    power, _, out = run(data)
    assert "station3" not in set(power["station"]) and "station3" in out


def test_feature_plot_rmse(data2):
    """GHI 特征图：station1 RMSE=4、station3 RMSE=5。"""
    _, feat, _ = run(data2)
    assert feat is not None
    g = feat[feat.feature == "GHI"].set_index("station")["rmse"]
    assert g["station1"] == pytest.approx(4.0)
    assert g["station3"] == pytest.approx(5.0)


def test_missing_feature_keeps_power(data2):
    """station2 的 GHI_SOLARGIS_predict 全 None → 无 GHI 行，但 power 照常有。"""
    power, feat, _ = run(data2)
    assert power[power.station == "station2"].iloc[0]["power_rmse"] == pytest.approx(3.0)
    assert "station2" not in set(feat[feat.feature == "GHI"]["station"])


def test_feature_without_power(data2):
    """station3 预测表无列 → 无 power 行，但 GHI 图仍出（互不牵连）。"""
    power, feat, _ = run(data2)
    assert "station3" not in set(power["station"])
    assert "station3" in set(feat[feat.feature == "GHI"]["station"])


def test_drop_night_reduces_points(data2):
    """默认含夜间 station1 power n=9；--drop-night 去掉 03–05 → n=5，RMSE 不变。"""
    p_all, _, _ = run(data2)
    p_day, _, _ = run(data2, extra=["--drop-night"])
    n_all = p_all[p_all.station == "station1"].iloc[0]["n_points"]
    n_day = p_day[p_day.station == "station1"].iloc[0]["n_points"]
    assert n_all == 9 and n_day == 5
    assert p_day[p_day.station == "station1"].iloc[0]["power_rmse"] == pytest.approx(2.0)
