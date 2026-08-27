"""station_analysis_ultra_short.py 单测。
数据模型：真值 v(t) = 自 D 00:00 起的 15min 槽序号；起报 S、lead k 的预测 = v(S+k*step) + scale*k。
→ p16 线 = v+scale、p1 线 = v+16*scale；合并 RMSE = scale*sqrt(mean(k², k=1..16)) = scale*sqrt(93.5)。
GHI：真值 2v、lead-1 预测 2v+5 → RMSE 5。历史列长 8 且反向（list[-1] 落在起报时刻）：构造成
observe_power 在时刻 t 的值 = v(t)、GHI_SOLARGIS = 3v(t)，故可按时间反查值。
文件名带拼写漂移（gunagxi/porvince）以测 token glob。"""
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
    for S in pd.date_range(D - STEP, D + pd.Timedelta(days=1) - STEP, freq="15min"):  # 97 起报目录
        t = S + STEP
        d = idir / f"date={S:%Y-%m-%d}" / f"time={S:%H:%M}"; d.mkdir(parents=True)
        rows = [{"station": st,
                 "observe_power_future": [_slot(t), 999.0],   # only list[0] must be read
                 "GHI_real_future": [2 * _slot(t), 999.0],
                 "GHI_SOLARGIS_predict": [2 * _slot(t) + 5.0, 999.0],
                 # 历史列: 反向 8 点，元素 i -> S-15min*(7-i)，值 = 该时刻 slot（GHI 为 3 倍）
                 "observe_power": [_slot(S) - (7 - i) for i in range(8)],
                 "GHI_SOLARGIS": [3.0 * (_slot(S) - (7 - i)) for i in range(8)]} for st in scale]
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
    assert "power_hist" not in truth["s1"].columns                  # 历史走 load_history，不进 truth


# ---------------------------------------------------------------- history: 当日最早起报的整条 list
def test_history_uses_earliest_dir_and_full_list(us_data):
    """date=D 下最早目录 = time=00:00 → S=D 00:00；8 点反向展开到 D-1 22:15..D 00:00，值=各时刻 slot。"""
    hist, S = us.load_history(str(us_data / "input"), D)
    assert S == D                                                   # 最早起报 = 00:00
    h = hist["s1"]["power_hist"]
    assert len(h) == 8                                              # 整条 list，不是每目录一个点
    assert h.index[-1] == D and h.index[0] == D - 7 * STEP          # list[-1] 落在起报时刻
    assert h.iloc[-1] == pytest.approx(0.0) and h.iloc[0] == pytest.approx(-7.0)
    assert h.loc[D - 3 * STEP] == pytest.approx(-3.0)               # 值 = 该时刻 slot
    g = hist["s1"]["ghi_hist"]
    assert g.loc[D - 3 * STEP] == pytest.approx(-9.0)               # GHI = 3 倍
    assert set(hist) == {"s1", "s2"}


def test_history_skips_missing_early_dirs(us_data):
    """当日没有 00:00/00:15（真实数据从 02:15 才有）→ 自动取第一个存在的目录。"""
    for hhmm in ("00:00", "00:15"):
        shutil.rmtree(us_data / "input" / "date=2026-07-23" / f"time={hhmm}")
    hist, S = us.load_history(str(us_data / "input"), D)
    assert S == D + 2 * STEP                                        # 00:30
    assert hist["s1"]["power_hist"].index[-1] == D + 2 * STEP


def test_history_absent_columns_and_absent_day(us_data, tmp_path):
    """无历史列 → 每站两条空 Series；整天无目录 → ({}, None)。"""
    import pathlib
    for p in sorted(pathlib.Path(us_data / "input").rglob("*.parquet")):
        pd.read_parquet(p).drop(columns=["observe_power", "GHI_SOLARGIS"]).to_parquet(p)
    hist, S = us.load_history(str(us_data / "input"), D)
    assert hist == {} and S is None                                 # 无历史列的目录一律跳过
    assert us.load_history(str(tmp_path / "nope"), D) == ({}, None)


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


# ---------------------------------------------------------------- e2e
def _run_us(wd, extra=()):
    r = subprocess.run(
        [sys.executable, SCRIPT, "--input-dir", str(wd / "input"),
         "--predict-dir", str(wd / "predict"), "--date", "20260723",
         "--out-dir", str(wd / "out")] + list(extra),
        cwd=str(wd), capture_output=True, text=True)
    assert r.returncode == 0, r.stdout + r.stderr
    return r


def _out(wd):
    return wd / "out" / "20260723"


def test_e2e_metrics_and_outputs(us_data):
    _run_us(us_data)
    pw = pd.read_csv(_out(us_data) / "station_power_rmse.csv")
    assert list(pw["station"]) == ["s2", "s1"]                        # sorted worst-first
    pw = pw.set_index("station")
    assert pw.loc["s1", "power_rmse"] == pytest.approx(math.sqrt(93.5), abs=1e-6)
    assert pw.loc["s2", "power_rmse"] == pytest.approx(2 * math.sqrt(93.5), abs=1e-6)
    assert set(pw["n_points"]) == {96 * 16}
    ft = pd.read_csv(_out(us_data) / "station_feature_rmse.csv").set_index("station")
    assert ft.loc["s1", "rmse"] == pytest.approx(5.0)
    assert int(ft.loc["s1", "n_points"]) == 96
    for st in ("s1", "s2"):
        assert (_out(us_data) / "stations" / f"station_{st}.png").exists()          # 2×2 组合图
        assert not (_out(us_data) / "stations" / f"station_{st}_Power.png").exists()  # 旧单图不再产出
        assert not (_out(us_data) / "stations" / f"station_{st}_GHI.png").exists()


def test_e2e_hist_cols_missing_still_runs(us_data):
    """input parquet 无历史列（旧 schema）→ 组合图历史面板 no data + 告警，指标与其余面板照出。"""
    import pathlib
    for p in sorted(pathlib.Path(us_data / "input").rglob("*.parquet")):
        df = pd.read_parquet(p)
        df.drop(columns=["observe_power", "GHI_SOLARGIS"]).to_parquet(p)
    r = _run_us(us_data)
    assert "no usable 起报 dir for history columns" in r.stdout
    assert "history GHI_SOLARGIS: no data" in r.stdout
    assert "history observe_power: no data" in r.stdout
    assert (_out(us_data) / "stations" / "station_s1.png").exists()
    pw = pd.read_csv(_out(us_data) / "station_power_rmse.csv").set_index("station")
    assert pw.loc["s1", "power_rmse"] == pytest.approx(math.sqrt(93.5), abs=1e-6)


def test_e2e_history_logs_chosen_issue_time(us_data):
    """日志播报历史取自哪个起报；--no-plots 时不读历史（省 IO）。"""
    assert "[history] 起报 2026-07-23 00:00" in _run_us(us_data).stdout
    assert "[history]" not in _run_us(us_data, ["--no-plots"]).stdout


def test_e2e_drop_night(us_data):
    _run_us(us_data, ["--drop-night"])                                # removes hod<5 → 20 targets
    pw = pd.read_csv(_out(us_data) / "station_power_rmse.csv").set_index("station")
    assert set(pw["n_points"]) == {76 * 16}
    assert pw.loc["s1", "power_rmse"] == pytest.approx(math.sqrt(93.5), abs=1e-6)   # per-lead常数误差不变


def test_e2e_missing_input_dir_warns_and_gaps(us_data):
    shutil.rmtree(us_data / "input" / "date=2026-07-23" / "time=12:00")
    r = _run_us(us_data)
    assert "input 起报 2026-07-23 12:00" in r.stdout
    pw = pd.read_csv(_out(us_data) / "station_power_rmse.csv").set_index("station")
    assert set(pw["n_points"]) == {96 * 16 - 16}                      # target 12:15 unscored on all 16 leads
    ft = pd.read_csv(_out(us_data) / "station_feature_rmse.csv").set_index("station")
    assert int(ft.loc["s1", "n_points"]) == 95


# ---------------------------------------------------------------- 南网超短期准确率（仅打印）
def _write_info(wd, mapping):
    pd.DataFrame([{"station": s, "GCCAPCITY": g} for s, g in mapping.items()]).to_csv(
        wd / "info.csv", index=False)
    return str(wd / "info.csv")


def test_e2e_nanwang_ultrashort_print_only(us_data):
    """C=500 → 0.2C=100 > 真值峰 95 → 分母恒 100：s1 逐 lead |误差|=k → Acc=1−8.5/100=91.50%；
    s2 |误差|=2k → 83.00%。全点含夜间：--drop-night 不改变该指标。产物 CSV 不得含 nanwang 列。"""
    info = _write_info(us_data, {"s1": 500.0, "s2": 500.0})
    r = _run_us(us_data, ["--info-csv", info, "--no-plots"])
    assert "station s1: 91.50%" in r.stdout
    assert "station s2: 83.00%" in r.stdout
    assert "fleet mean: 87.25%" in r.stdout                           # (91.50+83.00)/2
    pw = pd.read_csv(_out(us_data) / "station_power_rmse.csv")
    ft = pd.read_csv(_out(us_data) / "station_feature_rmse.csv")
    assert not any("nanwang" in c.lower() for c in list(pw.columns) + list(ft.columns))
    r2 = _run_us(us_data, ["--info-csv", info, "--no-plots", "--drop-night"])
    assert "station s1: 91.50%" in r2.stdout                          # 恒用全 96 点，不受夜滤影响


def test_e2e_nanwang_missing_station_warns(us_data):
    info = _write_info(us_data, {"s1": 500.0})                        # s2 缺
    r = _run_us(us_data, ["--info-csv", info, "--no-plots"])
    assert "station s1: 91.50%" in r.stdout
    assert "station s2: not in --info-csv" in r.stdout
    assert "station s2:" not in r.stdout.replace("station s2: not in --info-csv", "")


def test_e2e_info_real_shape_autojoin_city(us_data):
    """真实 info.csv 形态：无 station 列（plantid join 自动探测）、拼写 GCCAPACITY、含 city；
    station_power_rmse.csv 增 city 列、nanwang 照常打印；--info 为 --info-csv 别名。"""
    pd.DataFrame([
        {"plantid": "s1", "plantname": "光伏s1", "city": "阳江", "GCCAPACITY": 500.0},
        {"plantid": "s2", "plantname": "光伏s2", "city": "南宁", "GCCAPACITY": 500.0},
    ]).to_csv(us_data / "info.csv", index=False)
    r = _run_us(us_data, ["--info", str(us_data / "info.csv"), "--no-plots"])
    assert "join column auto-detected: 'plantid'" in r.stdout
    assert "station s1: 91.50%" in r.stdout
    pw = pd.read_csv(_out(us_data) / "station_power_rmse.csv").set_index("station")
    assert pw.loc["s1", "city"] == "阳江" and pw.loc["s2", "city"] == "南宁"
    assert not any("nanwang" in c.lower() for c in pw.columns)


def test_nanwang_ultrashort_gap_handling():
    """真值 NaN 的时刻整时刻剔除；lead 缺失的项按可用 lead 取均值。"""
    idx = pd.date_range("2026-07-23", periods=3, freq="15min")
    truth = pd.Series([10.0, np.nan, 10.0], index=idx)
    leads = pd.DataFrame({"p1": [12.0, 5.0, 14.0], "p2": [8.0, 5.0, np.nan]}, index=idx)
    acc, n_t = us.nanwang_ultrashort(truth, leads, gccap=50.0)        # 0.2C=10=denom
    # t0: (|10−12|+|10−8|)/2/10 = 0.2；t1 剔除；t2: |10−14|/1/10 = 0.4 → mean=0.3 → 70%
    assert n_t == 2
    assert acc == pytest.approx(70.0, abs=1e-9)
    assert us.nanwang_ultrashort(truth, leads, gccap=None) == (None, 0)
    assert us.nanwang_ultrashort(truth, leads, gccap=0.0) == (None, 0)


def test_e2e_no_plots(us_data):
    _run_us(us_data, ["--no-plots"])
    assert not (_out(us_data) / "stations").exists()
    assert (_out(us_data) / "station_power_rmse.csv").exists()
