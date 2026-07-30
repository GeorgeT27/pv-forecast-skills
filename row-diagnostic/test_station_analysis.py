"""station_analysis.py 单测（合并脚本，一趟同产逐站图 + 全场总览）。

逐站层（power/特征/鲁棒/夜间）：
  data  —— station1 两重叠窗→5唯一点 RMSE=2；station2 RMSE=3；station3 无预测列→跳过 Power。
  data2 —— station1 power(含夜间窗)+GHI(pred=真值+4→RMSE4，仅白天)；station2 只 power(GHI 全 None
           →GHI 跳过但 power 照出)；station3 预测表无列(power 跳过)但 GHI 齐(+5→RMSE5)。
全场层（nRMSE/排名/离群/GHI）：
  fleet —— 4 站真值恒 10、峰值=10，预测偏移造 nRMSE 5/10/10/100%；s4 必被 MAD 标离群。
反事实层（假 API，零真网络，真实契约 = 逐窗 predictions[].ensemble）：
  cf_data —— 假模型每窗 power = GHI_SOLARGIS_predict/10；真功率 = GHI_true/10、
  predict 表用同公式 → 基线复现闸 0%。c1 两窗 GHI 偏 +40 → nRMSE_base=8%、cf=0；
  c2 三窗偏 +20 → 10/3 %。bad2 模式：对 2 窗的站少返回一窗 → 窗数对齐闸鲁棒性。
"""
import http.server
import os
import subprocess
import sys
import threading

import numpy as np
import pandas as pd
import pytest

HERE = os.path.dirname(os.path.abspath(__file__))
SCRIPT = os.path.join(HERE, "station_analysis.py")


def _run(wd, extra=()):
    r = subprocess.run(
        [sys.executable, SCRIPT, "--input", str(wd / "input.parquet"),
         "--predict", str(wd / "predict.parquet"), "--out-dir", str(wd / "out")] + list(extra),
        cwd=str(wd), capture_output=True, text=True)
    assert r.returncode == 0, r.stdout + r.stderr

    def load(name):
        p = wd / "out" / name
        return pd.read_csv(p) if os.path.exists(p) else None
    return {"power": load("station_power_rmse.csv"), "feat": load("station_feature_rmse.csv"),
            "fleet": load("fleet_ranking.csv"), "cf": load("counterfactual_results.csv"),
            "out": r.stdout}


# ============================================================ 逐站：power 基本盘
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


# ============================================================ 逐站：特征 + 鲁棒 + 夜间
@pytest.fixture
def data2(tmp_path):
    def row(station, T, power, ghi_pred, ghi_true):
        return {"station": station, "timestamp_win": pd.Timestamp(T), "observe_power": 1.0,
                "observe_power_future": power, "GHI_SOLARGIS_predict": ghi_pred,
                "GHI_real_future": ghi_true}
    rows = [
        row("station1", "2026-07-16 10:00:00", [10., 20, 30, 40], [104., 114, 124, 134], [100., 110, 120, 130]),
        row("station1", "2026-07-16 10:15:00", [20., 30, 40, 50], [114., 124, 134, 144], [110., 120, 130, 140]),
        row("station1", "2026-07-16 03:00:00", [1., 2, 3, 4], None, None),
        row("station2", "2026-07-16 10:00:00", [5., 15, 25, 35], None, [1., 2, 3, 4]),
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


# ============================================================ 全场：nRMSE / 排名 / 离群
@pytest.fixture
def fleet(tmp_path):
    def win(rows, st, T, power, ghi_pred, ghi_true):
        rows.append({"station": st, "timestamp_win": pd.Timestamp(T), "observe_power": 10.0,
                     "observe_power_future": [float(x) for x in power],
                     "GHI_SOLARGIS_predict": ghi_pred, "GHI_real_future": ghi_true})
    rows = []
    for st in ("s1", "s2", "s3", "s4"):
        win(rows, st, "2026-07-16 10:00:00", [10, 10, 10, 10],
            [101., 101, 101, 101], [100., 100, 100, 100])          # GHI pred=true+1 → RMSE1
        win(rows, st, "2026-07-16 10:15:00", [10, 10, 10, 10],
            [101., 101, 101, 101], [100., 100, 100, 100])
    pd.DataFrame(rows).to_parquet(tmp_path / "input.parquet")
    dt = pd.date_range("2026-07-16 10:15:00", "2026-07-16 11:15:00", freq="15min")
    offs = {"s1": 0.5, "s2": 1.0, "s3": 1.0, "s4": 10.0}
    pred = pd.DataFrame({"dtime": dt})
    for st, off in offs.items():
        pred[st] = 10.0 + off
    pred.to_parquet(tmp_path / "predict.parquet")
    return tmp_path


# ============================================================ 反事实：假 API + 确定数据
class _FakeAPI(http.server.BaseHTTPRequestHandler):
    """真实契约：逐窗返回 predictions=[{timestamp_win, ensemble}]，模型 = 每窗 GHI/10。
    mode="bad2" 时对 data 恰 2 行的请求少返回 1 窗（触发窗数对齐闸）。"""

    def do_POST(self):
        import json
        self.server.hits += 1
        payload = json.loads(self.rfile.read(int(self.headers.get("Content-Length", 0))))
        preds = [{"timestamp_win": r["timestamp_win"],
                  "ensemble": [float(v) / 10.0 for v in r["GHI_SOLARGIS_predict"]]}
                 for r in payload["data"]]
        if self.server.mode == "bad2" and len(payload["data"]) == 2:
            preds = preds[:-1]
        body = json.dumps({"status": "success",
                           "message": f"successfully processed {len(preds)} items",
                           "predictions": preds}).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *a):
        pass


@pytest.fixture
def fake_api():
    srv = http.server.ThreadingHTTPServer(("127.0.0.1", 0), _FakeAPI)
    srv.hits, srv.mode = 0, "ok"
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    yield srv
    srv.shutdown()


def _url(srv):
    return f"http://127.0.0.1:{srv.server_address[1]}"


@pytest.fixture
def cf_data(tmp_path):
    def ghi(v0):
        return [float(v0 + 100 * k) for k in range(4)]

    OFF = {"c1": 40.0, "c2": 20.0}
    rows = []

    def add(st, T, gt):
        rows.append({"station": st, "timestamp_win": pd.Timestamp(T), "observe_power": 1.0,
                     "observe_power_future": [g / 10.0 for g in gt],
                     "GHI_SOLARGIS_predict": [g + OFF[st] for g in gt],
                     "GHI_real_future": gt})

    add("c1", "2026-07-16 10:00:00", ghi(100)); add("c1", "2026-07-16 10:15:00", ghi(200))
    add("c2", "2026-07-16 10:00:00", ghi(100)); add("c2", "2026-07-16 10:15:00", ghi(200))
    add("c2", "2026-07-16 10:30:00", ghi(300))
    pd.DataFrame(rows).to_parquet(tmp_path / "input.parquet")
    dt = pd.date_range("2026-07-16 10:15:00", "2026-07-16 11:30:00", freq="15min")   # 6 点
    flat = {"c1": [100., 200, 300, 400, 500], "c2": [100., 200, 300, 400, 500, 600]}
    pred = pd.DataFrame({"dtime": dt})
    pred["c1"] = [(flat["c1"][i] + 40) / 10 if i < 5 else np.nan for i in range(6)]
    pred["c2"] = [(flat["c2"][i] + 20) / 10 for i in range(6)]
    pred.to_parquet(tmp_path / "predict.parquet")
    return tmp_path


# ---------------------------------------------------------------- 逐站测试
def test_rmse_and_overlap_dedupe(data):
    r = _run(data, ["--no-plots"])
    s1 = r["power"][r["power"].station == "station1"].iloc[0]
    s2 = r["power"][r["power"].station == "station2"].iloc[0]
    assert s1["power_rmse"] == pytest.approx(2.0) and s1["n_points"] == 5
    assert s2["power_rmse"] == pytest.approx(3.0) and s2["n_points"] == 4


def test_missing_station_skipped(data):
    r = _run(data, ["--no-plots"])
    assert "station3" not in set(r["power"]["station"]) and "station3" in r["out"]


def test_feature_plot_rmse(data2):
    r = _run(data2, ["--no-plots"])
    g = r["feat"][r["feat"].feature == "GHI"].set_index("station")["rmse"]
    assert g["station1"] == pytest.approx(4.0)
    assert g["station3"] == pytest.approx(5.0)


def test_missing_feature_keeps_power(data2):
    r = _run(data2, ["--no-plots"])
    assert r["power"][r["power"].station == "station2"].iloc[0]["power_rmse"] == pytest.approx(3.0)
    assert "station2" not in set(r["feat"][r["feat"].feature == "GHI"]["station"])


def test_feature_without_power(data2):
    r = _run(data2, ["--no-plots"])
    assert "station3" not in set(r["power"]["station"])
    assert "station3" in set(r["feat"][r["feat"].feature == "GHI"]["station"])


def test_drop_night_reduces_points(data2):
    r_all = _run(data2, ["--no-plots"])
    r_day = _run(data2, ["--no-plots", "--drop-night"])
    n_all = r_all["power"][r_all["power"].station == "station1"].iloc[0]["n_points"]
    n_day = r_day["power"][r_day["power"].station == "station1"].iloc[0]["n_points"]
    assert n_all == 9 and n_day == 5
    assert r_day["power"][r_day["power"].station == "station1"].iloc[0]["power_rmse"] == pytest.approx(2.0)


# ---------------------------------------------------------------- 全场测试
def test_nrmse_and_rank(fleet):
    d = _run(fleet, ["--no-plots"])["fleet"].set_index("station")
    assert d.loc["s1", "power_nrmse"] == pytest.approx(5.0)
    assert d.loc["s2", "power_nrmse"] == pytest.approx(10.0)
    assert d.loc["s4", "power_nrmse"] == pytest.approx(100.0)
    assert d.loc["s4", "power_rank"] == 1 and d.loc["s1", "power_rank"] == 4


def test_outlier_flagged(fleet):
    r = _run(fleet, ["--no-plots"])
    d = r["fleet"].set_index("station")
    assert bool(d.loc["s4", "power_outlier"]) is True
    assert not bool(d.loc["s1", "power_outlier"])
    assert "s4" in r["out"]


def test_ghi_metric_present(fleet):
    d = _run(fleet, ["--no-plots"])["fleet"].set_index("station")
    assert d.loc["s1", "ghi_nrmse"] == pytest.approx(1.0)   # GHI pred=true+1、峰值100 → 1%


def test_no_fleet_skips_ranking(fleet):
    r = _run(fleet, ["--no-plots", "--no-fleet"])
    assert r["fleet"] is None                               # 不产总览
    assert r["power"] is not None                           # 站级仍在


def test_no_station_plots_keeps_csv(data, tmp_path):
    """--no-station-plots：不出逐站图，但站级 CSV 与总览仍在。"""
    r = _run(data, ["--no-station-plots"])
    assert r["power"] is not None
    assert not any(f.endswith("_Power.png") for f in os.listdir(data / "out"))


# ---------------------------------------------------------------- 反事实测试
def test_cf_decomposition(cf_data, fake_api):
    """基线/反事实 nRMSE 解析可知：c1 8%→0（frac=100）、c2 10/3%→0；复现闸 0%；出总览图。"""
    r = _run(cf_data, ["--no-station-plots", "--counterfactual", "--api-url", _url(fake_api)])
    d = r["cf"].set_index("station")
    assert d.loc["c1", "status"] == "ok" and d.loc["c2", "status"] == "ok"
    assert d.loc["c1", "nrmse_base"] == pytest.approx(8.0)        # 4 / cap50 ×100
    assert d.loc["c1", "nrmse_cf"] == pytest.approx(0.0, abs=1e-9)
    assert d.loc["c1", "frac_explained"] == pytest.approx(100.0)
    assert d.loc["c2", "nrmse_base"] == pytest.approx(10.0 / 3, abs=1e-3)   # 2 / cap60 ×100
    assert float(d.loc["c1", "base_vs_parquet_pct"]) == pytest.approx(0.0, abs=1e-9)
    assert int(d.loc["c1", "coadapt"]) == 0
    assert fake_api.hits == 4                                     # 2 站 × 2 次
    assert os.path.exists(cf_data / "out" / "counterfactual_overview.png")


def test_cf_dry_run_zero_calls(cf_data, fake_api):
    """dry-run：零 HTTP、不写结果 CSV，只打印 payload 骨架（且骨架不含 label/station 字段）。"""
    r = _run(cf_data, ["--no-plots", "--counterfactual", "--api-url", _url(fake_api),
                       "--cf-dry-run"])
    assert fake_api.hits == 0 and r["cf"] is None
    assert "payload skeleton" in r["out"] and "GHI_SOLARGIS_predict" in r["out"]
    assert "GHI_real_future:" not in r["out"] and "observe_power_future:" not in r["out"]


def test_cf_resume_skips_done(cf_data, fake_api):
    """断点续跑：第二遍不再调 API（已完成站全部跳过）。"""
    _run(cf_data, ["--no-plots", "--counterfactual", "--api-url", _url(fake_api)])
    assert fake_api.hits == 4
    r = _run(cf_data, ["--no-plots", "--counterfactual", "--api-url", _url(fake_api)])
    assert fake_api.hits == 4
    assert len(r["cf"]) == 2                                      # 无重复追加


def test_cf_align_mismatch_robust(cf_data, fake_api):
    """对齐闸鲁棒：c1（2 窗）被假 API 少返回一窗 → align_mismatch；c2 照常 ok。"""
    fake_api.mode = "bad2"
    r = _run(cf_data, ["--no-plots", "--counterfactual", "--api-url", _url(fake_api)])
    d = r["cf"].set_index("station")
    assert d.loc["c1", "status"] == "align_mismatch"
    assert d.loc["c2", "status"] == "ok"
    assert d.loc["c2", "nrmse_base"] == pytest.approx(10.0 / 3, abs=1e-3)


def test_cf_off_unchanged(cf_data):
    """不加 --counterfactual：无任何反事实产物，常规产物照常。"""
    r = _run(cf_data, ["--no-plots"])
    assert r["cf"] is None and r["power"] is not None


import importlib.util
_spec = importlib.util.spec_from_file_location("sa", SCRIPT)
sa = importlib.util.module_from_spec(_spec); _spec.loader.exec_module(sa)


def test_window_mask_half_open():
    idx = pd.date_range("2026-07-27 00:00", periods=4, freq="15min")
    m = sa.window_mask(idx, (pd.Timestamp("2026-07-27 00:00"), pd.Timestamp("2026-07-27 00:45")))
    assert list(m) == [True, True, True, False]          # end is exclusive
    assert list(sa.window_mask(idx, None)) == [True] * 4


def test_aligned_applies_window():
    idx = pd.date_range("2026-07-27 00:00", periods=4, freq="15min")
    a = pd.Series([1., 2, 3, 4], index=idx)
    b = pd.Series([1., 2, 3, 4], index=idx)
    out = sa._aligned(a, b, False, 5.0,
                      (pd.Timestamp("2026-07-27 00:00"), pd.Timestamp("2026-07-27 00:30")))
    times, av, bv = out
    assert len(times) == 2 and list(av) == [1.0, 2.0]     # only 00:00, 00:15 kept


def test_series_from_lists_history_endpoint():
    t0 = pd.Timestamp("2026-07-26 10:00")
    step = pd.Timedelta(minutes=15)
    s = sa.series_from_lists_history([t0], [[1.0, 2.0, 3.0, 4.0]], step)
    assert s.index[-1] == t0                       # last element sits at 起报时间
    assert s.iloc[-1] == 4.0
    assert s.index[-2] == t0 - step                # one 15-min step back
    assert s.iloc[-2] == 3.0
    assert s.index[0] == t0 - step * 3             # first element = t0 - step*(L-1)


def test_series_from_lists_history_skips_nan_and_empty():
    t0 = pd.Timestamp("2026-07-26 10:00")
    step = pd.Timedelta(minutes=15)
    s = sa.series_from_lists_history([t0], [[float("nan"), 2.0]], step)
    assert list(s.to_numpy()) == [2.0]             # NaN dropped
    assert s.index[0] == t0                        # the surviving value is the endpoint
    assert sa.series_from_lists_history([t0], [None], step).empty
    assert sa.series_from_lists_history([t0], [[]], step).empty


# ---------------------------------------------------------------- --short 双切片
@pytest.fixture
def short_data(tmp_path):
    """起报 D=2026-07-26 10:00, 每站一窗、480 点、15min。predict 覆盖全部 480 绝对时刻。"""
    D = pd.Timestamp("2026-07-26 10:00:00")
    n = 480
    times = [D + pd.Timedelta(minutes=15 * (k + 1)) for k in range(n)]
    truth = {"s1": [float(10 + (k % 96)) for k in range(n)],       # 日内 0..95 变化
             "s2": [float(5 + (k % 96)) for k in range(n)]}
    off = {"s1": 2.0, "s2": 3.0}
    rows = [{"station": st, "timestamp_win": D, "observe_power_future": truth[st]}
            for st in ("s1", "s2")]
    pd.DataFrame(rows).to_parquet(tmp_path / "input.parquet")
    pred = pd.DataFrame({"dtime": times})
    for st in ("s1", "s2"):
        pred[st] = [v + off[st] for v in truth[st]]
    pred.to_parquet(tmp_path / "predict.parquet")
    return tmp_path


def _run_short(wd, extra=()):
    r = subprocess.run(
        [sys.executable, SCRIPT, "--input", str(wd / "input.parquet"),
         "--predict", str(wd / "predict.parquet"), "--out-dir", str(wd / "out"),
         "--short"] + list(extra),
        cwd=str(wd), capture_output=True, text=True)
    assert r.returncode == 0, r.stdout + r.stderr
    return r


def test_short_makes_two_folders_96pts(short_data):
    r = _run_short(short_data, ["--no-plots", "--pred-col-template", "{station}"])
    for sub in ("D+1", "D+4"):
        d = short_data / "out" / sub
        assert d.is_dir(), f"missing {sub}"
        pw = pd.read_csv(d / "station_power_rmse.csv")
        assert set(pw["n_points"]) == {96}, f"{sub}: {pw['n_points'].tolist()}"
    assert "using D = 2026-07-26" in r.stdout               # auto-fallback announced


def test_short_date_override(short_data):
    r = _run_short(short_data, ["--no-plots", "--pred-col-template", "{station}",
                                "--date", "2026-07-26"])
    pw = pd.read_csv(short_data / "out" / "D+1" / "station_power_rmse.csv")
    assert set(pw["n_points"]) == {96}
    assert "using D" not in r.stdout                        # explicit date -> no fallback line


def test_short_date_shifts_window(short_data):
    """--date 给一个与自动推断不同的日期(2026-07-27 vs 自动的 2026-07-26)，应真正把切片挪到新日期上，
    而不只是凑巧和自动推断值相同（test_short_date_override 覆盖的是后一种情况）。"""
    r = _run_short(short_data, ["--no-plots", "--pred-col-template", "{station}",
                                "--date", "2026-07-27"])
    pw = pd.read_csv(short_data / "out" / "D+1" / "station_power_rmse.csv")
    assert set(pw["n_points"]) == {96}
    assert set(pw["t_start"]) == {"2026-07-28 00:00:00"}    # D+1 = --date + 1 day, moved off the auto-inferred D+1
    assert "using D" not in r.stdout                        # explicit date -> no fallback line


def test_default_no_short_folders(short_data):
    # 常规模式（无 --short）：直接写 out/，不建 D+1/D+4
    subprocess.run(
        [sys.executable, SCRIPT, "--input", str(short_data / "input.parquet"),
         "--predict", str(short_data / "predict.parquet"), "--out-dir", str(short_data / "out"),
         "--no-plots", "--pred-col-template", "{station}"],
        cwd=str(short_data), capture_output=True, text=True, check=True)
    assert not (short_data / "out" / "D+1").exists()
    assert (short_data / "out" / "station_power_rmse.csv").exists()


def test_short_worst_only(short_data):
    # --worst-only 1：每个切片图只画最差 1 站，CSV 仍含全部站
    r = _run_short(short_data, ["--pred-col-template", "{station}", "--worst-only", "1"])
    pw = pd.read_csv(short_data / "out" / "D+1" / "station_power_rmse.csv")
    assert len(pw) == 2                                     # CSV 全量
    pngs = os.listdir(short_data / "out" / "D+1" / "stations")
    powers = [f for f in pngs if f.endswith("_Power.png")]
    assert len(powers) == 1                                 # 仅最差 1 站出图


@pytest.fixture
def short_cf_data(tmp_path):
    """短期反事实：D=2026-07-26 10:00、每站一窗 480 点。假模型 power=GHI/10。"""
    D = pd.Timestamp("2026-07-26 10:00:00")
    n = 480
    times = [D + pd.Timedelta(minutes=15 * (k + 1)) for k in range(n)]
    OFF = {"c1": 40.0}
    gt = {"c1": [float(100 + k) for k in range(n)]}                 # GHI 真值
    rows = [{"station": "c1", "timestamp_win": D,
             "observe_power_future": [g / 10.0 for g in gt["c1"]],
             "GHI_SOLARGIS_predict": [g + OFF["c1"] for g in gt["c1"]],
             "GHI_real_future": gt["c1"]}]
    pd.DataFrame(rows).to_parquet(tmp_path / "input.parquet")
    pred = pd.DataFrame({"dtime": times})
    pred["c1"] = [(g + OFF["c1"]) / 10.0 for g in gt["c1"]]         # 复现基线（=API baseline）
    pred.to_parquet(tmp_path / "predict.parquet")
    return tmp_path


def test_short_end_to_end_with_plots(short_data):
    r = _run_short(short_data, ["--pred-col-template", "{station}", "--worst-only", "2"])
    for sub in ("D+1", "D+4"):
        d = short_data / "out" / sub
        assert (d / "fleet_overview.png").exists()
        assert (d / "theil_decomposition.png").exists()
        assert (d / "fleet_ranking.csv").exists()
        stn = os.listdir(d / "stations")
        assert any(f.endswith("_Power.png") for f in stn)
        assert any(f.endswith("_scatter.png") for f in stn)


def test_short_counterfactual_per_window(short_cf_data, fake_api):
    r = subprocess.run(
        [sys.executable, SCRIPT, "--input", str(short_cf_data / "input.parquet"),
         "--predict", str(short_cf_data / "predict.parquet"),
         "--out-dir", str(short_cf_data / "out"), "--short", "--no-plots",
         "--counterfactual", "--api-url", _url(fake_api)],
        cwd=str(short_cf_data), capture_output=True, text=True)
    assert r.returncode == 0, r.stdout + r.stderr
    for sub in ("D+1", "D+4"):
        p = short_cf_data / "out" / sub / "counterfactual_results.csv"
        assert p.exists(), f"missing CF csv in {sub}"
        d = pd.read_csv(p).set_index("station")
        assert d.loc["c1", "status"] == "ok"
        assert int(d.loc["c1", "n_points"]) == 96              # 每切片 96 点
    assert fake_api.hits == 4                                   # 1 站 × 2 次 × 2 切片


@pytest.fixture
def short_data_missing_d4(tmp_path):
    """同 short_data，但 predict 表只覆盖到 2026-07-30 00:00 之前（D+1 窗口齐全，D+4 窗口无任何预测点）；
    input 侧的 observe_power_future 仍完整覆盖到 D+4，用来验证 D+4 切片缺预测数据时的鲁棒退出（不崩、不产 D+4 power）。"""
    D = pd.Timestamp("2026-07-26 10:00:00")
    n = 480
    times = [D + pd.Timedelta(minutes=15 * (k + 1)) for k in range(n)]
    truth = {"s1": [float(10 + (k % 96)) for k in range(n)],
             "s2": [float(5 + (k % 96)) for k in range(n)]}
    off = {"s1": 2.0, "s2": 3.0}
    rows = [{"station": st, "timestamp_win": D, "observe_power_future": truth[st]}
            for st in ("s1", "s2")]
    pd.DataFrame(rows).to_parquet(tmp_path / "input.parquet")
    cutoff = pd.Timestamp("2026-07-30 00:00:00")
    keep = [t < cutoff for t in times]                          # drop all D+4-window dtimes from predict
    pred = pd.DataFrame({"dtime": [t for t, k in zip(times, keep) if k]})
    for st in ("s1", "s2"):
        pred[st] = [v + off[st] for v, k in zip(truth[st], keep) if k]
    pred.to_parquet(tmp_path / "predict.parquet")
    return tmp_path


def test_short_missing_d4_slice_skips_gracefully(short_data_missing_d4):
    """D+4 切片的 predict 表没有任何落点 -> power 对齐结果为空 -> 该切片走 warn+return 早退路径，
    不应导致整个进程崩溃；D+1 切片不受影响，照常产出 96 点。"""
    r = _run_short(short_data_missing_d4, ["--no-plots", "--pred-col-template", "{station}"])
    assert r.returncode == 0, r.stdout + r.stderr
    d1_pw = pd.read_csv(short_data_missing_d4 / "out" / "D+1" / "station_power_rmse.csv")
    assert set(d1_pw["n_points"]) == {96}
    d4_path = short_data_missing_d4 / "out" / "D+4" / "station_power_rmse.csv"
    # "nothing produced -> warn+return" 路径下该文件根本不会被写出；即便某天该路径的行为改成写空文件，也应容忍
    assert (not d4_path.exists()) or pd.read_csv(d4_path).empty
