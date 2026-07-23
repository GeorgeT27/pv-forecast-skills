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
    assert "payload 骨架" in r["out"] and "GHI_SOLARGIS_predict" in r["out"]
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
