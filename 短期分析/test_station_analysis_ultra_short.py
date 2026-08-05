"""station_analysis_ultra_short.py 单测。
数据模型：真值 v(t) = 自 D 00:00 起的 15min 槽序号；起报 S、lead k 的预测 = v(S+k*step) + scale*k。
→ p16 线 = v+scale、p1 线 = v+16*scale；合并 RMSE = scale*sqrt(mean(k², k=1..16)) = scale*sqrt(93.5)。
GHI：真值 2v、lead-1 预测 2v+5 → RMSE 5。文件名带拼写漂移（gunagxi/porvince）以测 token glob。"""
import math
import os
import shutil
import subprocess
import sys

import numpy as np
import pandas as pd
import pytest

HERE = os.path.dirname(os.path.abspath(__file__))
SCRIPT = os.path.join(HERE, "station_analysis_ultra_short.py")

import importlib.util
_spec = importlib.util.spec_from_file_location("us", SCRIPT)
us = importlib.util.module_from_spec(_spec); _spec.loader.exec_module(us)

D = pd.Timestamp("2026-07-23")
STEP = pd.Timedelta(minutes=15)


def _slot(t):                                  # 15-min slots since D 00:00
    return (t - D).total_seconds() / 900.0


@pytest.fixture
def us_data(tmp_path):
    scale = {"s1": 1.0, "s2": 2.0}
    pdir = tmp_path / "predict"; pdir.mkdir()
    for S in [D - 16 * STEP + k * STEP for k in range(111)]:
        dt = [S + STEP * (k + 1) for k in range(20)]          # 20 rows, script keeps first 16
        df = pd.DataFrame({"dtime": dt})
        for st, sc in scale.items():
            df[f"predict_power_{st}"] = [_slot(t) + sc * (i + 1) for i, t in enumerate(dt)]
        df.to_parquet(pdir / f"hw_nuoya_{S:%Y%m%d%H%M}_ultra_short_province_gunagxi_solar.parquet")
    idir = tmp_path / "input"
    for t in pd.date_range(D, D + pd.Timedelta(days=1) - STEP, freq="15min"):
        S = t - STEP
        d = idir / f"date={S:%Y-%m-%d}" / f"time={S:%H:%M}"; d.mkdir(parents=True)
        rows = [{"station": st,
                 "observe_power_future": [_slot(t), 999.0],   # only list[0] must be read
                 "GHI_real_future": [2 * _slot(t), 999.0],
                 "GHI_SOLARGIS_predict": [2 * _slot(t) + 5.0, 999.0]} for st in scale]
        pd.DataFrame(rows).to_parquet(
            d / f"hw_nuoya_ds_{S:%Y-%m-%d}_ultra_short_porvince_guangxi_solar.parquet")
    return tmp_path


def test_issue_times_and_grid():
    ts = us.issue_times(D)
    assert len(ts) == 111
    assert ts[0] == D - pd.Timedelta(hours=4)                 # D-1 20:00
    assert ts[-1] == D + pd.Timedelta(hours=23, minutes=30)
    g = us.target_grid(D)
    assert len(g) == 96 and g[0] == D and g[-1] == D + pd.Timedelta(hours=23, minutes=45)


def test_lead_mapping_full_coverage(us_data):
    mats, miss = us.load_predict_matrix(str(us_data / "predict"), D, ["s1"], "predict_power_{station}")
    assert miss == 0
    m = mats["s1"]
    assert list(m.columns) == [f"p{j}" for j in range(1, 17)]
    t = D + pd.Timedelta(hours=12)
    assert m.loc[t, "p16"] == pytest.approx(_slot(t) + 1)     # 起报 11:45, lead 1
    assert m.loc[t, "p1"] == pytest.approx(_slot(t) + 16)     # 起报 08:00, lead 16
    assert m.notna().all().all()                              # full 96x16


def test_cross_midnight_sources(us_data):
    mats, _ = us.load_predict_matrix(str(us_data / "predict"), D, ["s1"], "predict_power_{station}")
    assert mats["s1"].loc[D, "p1"] == pytest.approx(16.0)     # from D-1 20:00 起报
    truth, miss = us.load_truth(str(us_data / "input"), D)
    assert miss == 0
    assert truth["s1"].loc[D, "power_true"] == pytest.approx(0.0)   # from date=D-1/time=23:45 list[0]
    assert truth["s1"].loc[D, "ghi_pred"] == pytest.approx(5.0)


def test_find_parquet_glob_and_dup(us_data, tmp_path):
    tok = "202607231200"
    assert us.find_parquet(str(us_data / "predict"), tok) is not None   # matched despite name drift
    assert us.find_parquet(str(us_data / "predict"), "209901010000") is None
    dup = tmp_path / "dup"; dup.mkdir()
    for n in ("a_202607231200_x.parquet", "b_202607231200_y.parquet"):
        pd.DataFrame({"dtime": [D]}).to_parquet(dup / n)
    with pytest.raises(SystemExit):
        us.find_parquet(str(dup), tok)


def test_stations_from_columns():
    cols = ["dtime", "predict_power_s1", "predict_power_s2", "other"]
    assert us.stations_from_columns(cols, "predict_power_{station}") == ["s1", "s2"]
    assert us.stations_from_columns(["dtime", "s1", "s2"], "{station}") == ["s1", "s2"]


def test_missing_predict_file_gap(us_data):
    victim = us.find_parquet(str(us_data / "predict"), "202607231200")
    os.remove(victim)
    mats, miss = us.load_predict_matrix(str(us_data / "predict"), D, ["s1"], "predict_power_{station}")
    assert miss == 1
    assert int(mats["s1"].isna().sum().sum()) == 16           # 16 targets lose exactly one lead each
