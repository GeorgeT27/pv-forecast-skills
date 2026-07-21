"""station_power_rmse.py 单测：确定性合成数据钉死时间对齐 + 重叠窗去重 + 站列匹配。

埋点：station1 有两个重叠窗（future 在交叠时刻一致）→ 去重后 5 个唯一时间点、预测=真值+2 → RMSE=2；
station2 单窗 4 点、预测=真值+3 → RMSE=3；station3 无预测列 → 跳过。
"""
import os
import subprocess
import sys

import numpy as np
import pandas as pd
import pytest

HERE = os.path.dirname(os.path.abspath(__file__))
SCRIPT = os.path.join(HERE, "station_power_rmse.py")


@pytest.fixture
def data(tmp_path):
    def win(rows, station, T, future):
        rows.append({"station": station, "timestamp_win": pd.Timestamp(T),
                     "observe_power": 1.0, "observe_power_future": [float(x) for x in future]})
    rows = []
    win(rows, "station1", "2026-07-16 10:00:00", [10, 20, 30, 40])   # 10:15..11:00
    win(rows, "station1", "2026-07-16 10:15:00", [20, 30, 40, 50])   # 10:30..11:15（交叠一致）
    win(rows, "station2", "2026-07-16 10:00:00", [5, 15, 25, 35])
    win(rows, "station3", "2026-07-16 10:00:00", [1, 2, 3, 4])       # 预测表无此列 → 跳过
    pd.DataFrame(rows).to_parquet(tmp_path / "input.parquet")

    dt = pd.date_range("2026-07-16 10:15:00", "2026-07-16 11:15:00", freq="15min")
    truth1 = {pd.Timestamp("2026-07-16 10:15"): 10, pd.Timestamp("2026-07-16 10:30"): 20,
              pd.Timestamp("2026-07-16 10:45"): 30, pd.Timestamp("2026-07-16 11:00"): 40,
              pd.Timestamp("2026-07-16 11:15"): 50}
    truth2 = {pd.Timestamp("2026-07-16 10:15"): 5, pd.Timestamp("2026-07-16 10:30"): 15,
              pd.Timestamp("2026-07-16 10:45"): 25, pd.Timestamp("2026-07-16 11:00"): 35}
    pred = pd.DataFrame({"dtime": dt})
    pred["station1"] = [truth1[t] + 2 if t in truth1 else np.nan for t in dt]
    pred["station2"] = [truth2[t] + 3 if t in truth2 else np.nan for t in dt]
    pred.to_parquet(tmp_path / "predict.parquet")
    return tmp_path


def run(data):
    r = subprocess.run(
        [sys.executable, SCRIPT, "--input", str(data / "input.parquet"),
         "--predict", str(data / "predict.parquet"), "--out-dir", str(data / "out"), "--no-plots"],
        cwd=str(data), capture_output=True, text=True)
    assert r.returncode == 0, r.stdout + r.stderr
    return pd.read_csv(data / "out" / "station_power_rmse.csv"), r.stdout


def test_rmse_and_overlap_dedupe(data):
    df, _ = run(data)
    s1 = df[df.station == "station1"].iloc[0]
    s2 = df[df.station == "station2"].iloc[0]
    assert s1["power_rmse"] == pytest.approx(2.0)
    assert s1["n_points"] == 5           # 两个重叠窗去重成 5 个唯一时间点
    assert s2["power_rmse"] == pytest.approx(3.0)
    assert s2["n_points"] == 4


def test_missing_station_skipped(data):
    df, out = run(data)
    assert "station3" not in set(df["station"])   # 预测表无该列 → 跳过，不崩
    assert "station3" in out                        # 但有告警
