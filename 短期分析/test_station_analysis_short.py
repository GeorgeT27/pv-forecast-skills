"""station_analysis_short.py 单测（合并脚本，一趟同产逐站图 + 全场总览）。

逐站层（power/特征/鲁棒/夜间）：
  data  —— station1 两重叠窗→5唯一点 RMSE=2；station2 RMSE=3；station3 无预测列→跳过 Power。
  data2 —— station1 power(含夜间窗)+GHI(pred=真值+4→RMSE4，仅白天)；station2 只 power(GHI 全 None
           →GHI 跳过但 power 照出)；station3 预测表无列(power 跳过)但 GHI 齐(+5→RMSE5)。
全场层（nRMSE/排名/离群/GHI）：
  fleet —— 4 站真值恒 10、峰值=10，预测偏移造 nRMSE 5/10/10/100%；s4 必被 MAD 标离群。
反事实层（假本地 inference 模块，零网络；契约 = multi_station_inference 逐窗返回 dtime×predict_power_<站>）：
  cf_data —— 假模型每窗 power = GHI_SOLARGIS_predict/10；真功率 = GHI_true/10、
  predict 表用同公式 → 基线复现闸 0%。c1 两窗 GHI 偏 +40 → nRMSE_base=8%、cf=0；
  c2 三窗偏 +20 → 10/3 %。逐窗调用：3 个 timestamp_win × 2 趟（基线 + 换真值）= 6 次。
"""
import json
import os
import subprocess
import sys

import numpy as np
import pandas as pd
import pytest

HERE = os.path.dirname(os.path.abspath(__file__))
SCRIPT = os.path.join(HERE, "station_analysis_short.py")


def _run(wd, extra=()):
    r = subprocess.run(
        [sys.executable, SCRIPT, "--input", str(wd / "input.parquet"),
         "--predict", str(wd / "predict.parquet"), "--out-dir", str(wd / "out"),
         "--date", "2026-07-15", "--pred-col-template", "{station}"] + list(extra),
        cwd=str(wd), capture_output=True, text=True)
    assert r.returncode == 0, r.stdout + r.stderr

    def load(name):
        p = wd / "out" / "20260715" / "D+1" / name
        return pd.read_csv(p) if os.path.exists(p) else None
    return {"power": load("station_power_rmse.csv"), "feat": load("station_feature_rmse.csv"),
            "fleet": load("fleet_ranking.csv"), "out": r.stdout}


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


# ============================================================ 反事实：假本地 inference 模块 + 确定数据
# 真实契约（inference.py:96-118）：断言 station 唯一 + timestamp_win 单一；返回
# pred_length 行 × (dtime + 每站一列 predict_power_<站>) 的标量表。假模型 power = GHI/10。
# FAKE_INFER_MODE=insensitive 时忽略 GHI 返回常数 → 基线与反事实全等（触发无效换闸）。
FAKE_INFERENCE = '''
import json, os
import pandas as pd


def multi_station_inference(ds_dataframe, df_plants_info, checkpoints_dir,
                            forecasting_type="short", config="config_test.yaml"):
    assert ds_dataframe["station"].is_unique, "输入错误：存在重复的station"
    assert ds_dataframe["timestamp_win"].nunique() == 1, "输入错误：timestamp_win 未对齐"
    base = pd.Timestamp(ds_dataframe["timestamp_win"].iloc[0])
    with open(os.environ["FAKE_INFER_LOG"], "a") as f:
        f.write(json.dumps({
            "window": str(base),
            "checkpoints_dir": str(checkpoints_dir),
            "config": str(config),
            "forecasting_type": forecasting_type,
            "stations": [str(s) for s in ds_dataframe["station"]],
            "index": [int(i) for i in ds_dataframe.index],
            "win_dtype": str(ds_dataframe["timestamp_win"].dtype),
            "ghi": {str(r["station"]): [float(v) for v in r["GHI_SOLARGIS_predict"]]
                    for _, r in ds_dataframe.iterrows()},
            "columns": list(ds_dataframe.columns)}) + "\\n")
    n = len(ds_dataframe["GHI_SOLARGIS_predict"].iloc[0])
    out = {"dtime": pd.date_range(base + pd.Timedelta(minutes=15), periods=n, freq="15min")}
    insensitive = os.environ.get("FAKE_INFER_MODE") == "insensitive"
    for _, r in ds_dataframe.iterrows():
        out[f"predict_power_{r['station']}"] = (
            [1.0] * n if insensitive else [float(v) / 10.0 for v in r["GHI_SOLARGIS_predict"]])
    return pd.DataFrame(out)
'''

FAKE_UTILS = '''
def get_past_future_cols(config):
    """契约同 utils.get_past_future_cols：(past, future, extra, target)。"""
    return ([], list(config.get("future_cols", [])), [], "observe_power_future")
'''


class _FakeInfer:
    def __init__(self, d, log):
        self.dir, self.log = str(d), str(log)

    @property
    def calls(self):
        if not os.path.exists(self.log):
            return []
        with open(self.log) as f:
            return [json.loads(ln) for ln in f if ln.strip()]

    @property
    def count(self):
        return len(self.calls)


@pytest.fixture
def fake_infer(tmp_path, monkeypatch):
    d = tmp_path / "fake_model"
    d.mkdir()
    (d / "inference.py").write_text(FAKE_INFERENCE)
    log = tmp_path / "infer_calls.jsonl"
    monkeypatch.setenv("FAKE_INFER_LOG", str(log))
    return _FakeInfer(d, log)


def _cf_args(fi, wd, extra=()):
    """反事实公共参数：假 inference 目录 + checkpoints/config 占位。"""
    return ["--counterfactual", "--inference-dir", fi.dir,
            "--checkpoints-dir", str(wd / "ckpt"),
            "--config", str(wd / "config.yaml")] + list(extra)


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
    pngs = [f for _, _, fs in os.walk(data / "out") for f in fs if f.endswith("_Power.png")]
    assert pngs == []


# ---------------------------------------------------------------- 反事实测试（本地 inference）
def test_cf_decomposition(cf_data, fake_infer):
    """解析可知：c1 基线 8%→反事实 0（frac=100）、c2 10/3%→0；复现闸 0%；出总览图。"""
    r = _run(cf_data, _cf_args(fake_infer, cf_data, ["--no-station-plots"]))
    d = r["fleet"].set_index("station")
    assert d.loc["c1", "cf_status"] == "ok" and d.loc["c2", "cf_status"] == "ok"
    assert d.loc["c1", "power_nrmse_localbase"] == pytest.approx(8.0)      # 4 / cap50 ×100
    assert d.loc["c1", "power_nrmse_cf"] == pytest.approx(0.0, abs=1e-9)
    assert d.loc["c1", "frac_explained"] == pytest.approx(100.0)
    assert d.loc["c2", "power_nrmse_localbase"] == pytest.approx(10.0 / 3, abs=1e-3)  # 2 / cap60 ×100
    assert float(d.loc["c1", "base_vs_parquet_pct"]) == pytest.approx(0.0, abs=1e-9)
    assert int(d.loc["c1", "coadapt"]) == 0
    assert os.path.exists(cf_data / "out" / "20260715" / "D+1" / "counterfactual_overview.png")


def test_cf_one_call_per_window_two_passes(cf_data, fake_infer):
    """逐窗调用：3 个 timestamp_win × 2 趟 = 6 次；每次 station 唯一且只含一个窗口。"""
    _run(cf_data, _cf_args(fake_infer, cf_data, ["--no-plots"]))
    calls = fake_infer.calls
    assert fake_infer.count == 6
    assert sorted({c["window"] for c in calls}) == [
        "2026-07-16 10:00:00", "2026-07-16 10:15:00", "2026-07-16 10:30:00"]
    for c in calls:
        assert len(c["stations"]) == len(set(c["stations"]))       # 断言 station 唯一未被触发
    per_win = {}
    for c in calls:
        per_win.setdefault(c["window"], []).append(c)
    assert all(len(v) == 2 for v in per_win.values())              # 每窗恰好基线 + 换真值


def test_cf_passes_contiguous_index(cf_data, fake_infer):
    """inference.py 内部用 pd.concat(..., axis=1) 合并模型输出 —— axis=1 按 index 对齐。
    groupby 切出的子帧带原表的稀疏 index（如 [0,2,4]），会与模型的 RangeIndex 错位成 NaN。
    交给模型的每个子帧必须是 0..n-1 连续 index，和 read_parquet 的结果无从区分。"""
    _run(cf_data, _cf_args(fake_infer, cf_data, ["--no-plots"]))
    for c in fake_infer.calls:
        assert c["index"] == list(range(len(c["stations"]))), \
            f"window {c['window']} got non-contiguous index {c['index']}"


def test_cf_swap_reaches_model(cf_data, fake_infer):
    """换真值那一趟，模型真的收到 GHI_real_future 的值（而非原预测值）。"""
    _run(cf_data, _cf_args(fake_infer, cf_data, ["--no-plots"]))
    w = [c for c in fake_infer.calls if c["window"] == "2026-07-16 10:00:00"]
    ghis = sorted([c["ghi"]["c1"] for c in w])
    assert ghis == [[100.0, 200.0, 300.0, 400.0],                  # 换真值趟 = GHI_real_future
                    [140.0, 240.0, 340.0, 440.0]]                  # 基线趟 = GHI_SOLARGIS_predict


def test_cf_input_separate_parquet_is_what_model_sees(cf_data, fake_infer):
    """--cf-input：模型吃的是这张推理专用表（带模型特征、无真值功率列），不是 --input。"""
    inp = pd.read_parquet(cf_data / "input.parquet")
    cfi = inp.drop(columns=["observe_power_future"]).copy()
    cfi["ssrd_pos_1_predict"] = [[1.0, 2.0, 3.0, 4.0]] * len(cfi)   # 只有推理表才有的模型特征
    cfi.to_parquet(cf_data / "cf_input.parquet")
    r = _run(cf_data, _cf_args(fake_infer, cf_data,
                               ["--no-plots", "--cf-input", str(cf_data / "cf_input.parquet")]))
    cols = fake_infer.calls[0]["columns"]
    assert "ssrd_pos_1_predict" in cols and "observe_power_future" not in cols
    assert r["fleet"].set_index("station").loc["c1", "power_nrmse_cf"] == pytest.approx(0.0, abs=1e-9)


def test_cf_columns_use_predict_power_template(cf_data, fake_infer):
    """inference.py 固定产 predict_power_<站> 列；--pred-col-template 只管 --predict 表，不得混用。"""
    r = _run(cf_data, _cf_args(fake_infer, cf_data, ["--no-plots"]))
    d = r["fleet"].set_index("station")
    assert np.isfinite(d.loc["c1", "power_nrmse_cf"])              # 裸站名模板下仍解析到 cf 列
    assert np.isfinite(d.loc["c2", "power_nrmse_cf"])


def test_cf_cache_skips_second_run(cf_data, fake_infer):
    """推理结果落盘缓存：第二遍零调用；--cf-force 重算。"""
    _run(cf_data, _cf_args(fake_infer, cf_data, ["--no-plots"]))
    assert fake_infer.count == 6
    _run(cf_data, _cf_args(fake_infer, cf_data, ["--no-plots"]))
    assert fake_infer.count == 6                                   # 命中缓存，未再推理
    _run(cf_data, _cf_args(fake_infer, cf_data, ["--no-plots", "--cf-force"]))
    assert fake_infer.count == 12


def test_cf_identical_output_warns(cf_data, fake_infer, monkeypatch):
    """模型对 GHI 不敏感（基线与反事实全等）→ 必须告警，不得静默报 Δ=0。"""
    monkeypatch.setenv("FAKE_INFER_MODE", "insensitive")
    r = _run(cf_data, _cf_args(fake_infer, cf_data, ["--no-plots"]))
    assert "identical" in r["out"].lower()


def test_cf_without_predict_table(cf_data, fake_infer):
    """无 --predict：本地基线顶上「预测」这一路，反事实照常分解；复现闸无对照物故不出。"""
    r = subprocess.run(
        [sys.executable, SCRIPT, "--input", str(cf_data / "input.parquet"),
         "--out-dir", str(cf_data / "out"), "--date", "2026-07-15", "--no-plots"]
        + _cf_args(fake_infer, cf_data),
        cwd=str(cf_data), capture_output=True, text=True)
    assert r.returncode == 0, r.stdout + r.stderr
    d = pd.read_csv(cf_data / "out" / "20260715" / "D+1" / "fleet_ranking.csv").set_index("station")
    assert d.loc["c1", "cf_status"] == "ok"
    assert d.loc["c1", "power_nrmse_cf"] == pytest.approx(0.0, abs=1e-9)
    # 「预测」这一路就是本地基线本身，两列必然相等
    assert d.loc["c1", "power_nrmse"] == pytest.approx(d.loc["c1", "power_nrmse_localbase"])
    # 拿基线跟自己比毫无意义 -> 复现闸必须整列不出，而不是填 0 假装通过
    assert "base_vs_parquet_pct" not in d.columns


def test_no_predict_without_counterfactual_errors(cf_data):
    """既无 --predict 又无 --counterfactual：没有任何预测来源，必须明确报错而不是空跑。"""
    r = subprocess.run(
        [sys.executable, SCRIPT, "--input", str(cf_data / "input.parquet"),
         "--out-dir", str(cf_data / "out"), "--date", "2026-07-15", "--no-plots"],
        cwd=str(cf_data), capture_output=True, text=True)
    assert r.returncode != 0
    assert "--predict" in (r.stdout + r.stderr)


def test_cf_off_unchanged(cf_data):
    """不加 --counterfactual：无反事实列、零推理，常规产物照常。"""
    r = _run(cf_data, ["--no-plots"])
    assert r["power"] is not None
    assert "power_nrmse_cf" not in r["fleet"].columns


def test_cf_requires_checkpoints_and_config(cf_data, fake_infer):
    """--counterfactual 缺 --checkpoints-dir/--config → 明确报错退出，不静默跳过。"""
    p = subprocess.run(
        [sys.executable, SCRIPT, "--input", str(cf_data / "input.parquet"),
         "--predict", str(cf_data / "predict.parquet"), "--out-dir", str(cf_data / "out"),
         "--date", "2026-07-15", "--pred-col-template", "{station}", "--no-plots",
         "--counterfactual", "--inference-dir", fake_infer.dir],
        cwd=str(cf_data), capture_output=True, text=True)
    assert p.returncode != 0
    assert "--checkpoints-dir" in (p.stdout + p.stderr)


def test_cf_station_missing_from_cf_input_warns(cf_data, fake_infer):
    """站在 --input 有、--cf-input 没有 → 告警 + 该站无反事实列，其它站照常。"""
    inp = pd.read_parquet(cf_data / "input.parquet")
    inp[inp.station != "c2"].to_parquet(cf_data / "cf_input.parquet")
    r = _run(cf_data, _cf_args(fake_infer, cf_data,
                               ["--no-plots", "--cf-input", str(cf_data / "cf_input.parquet")]))
    d = r["fleet"].set_index("station")
    assert d.loc["c1", "power_nrmse_cf"] == pytest.approx(0.0, abs=1e-9)
    assert d.loc["c2", "cf_status"] == "missing"
    assert "c2" in r["out"]


def test_cf_empty_truth_series_no_crash(tmp_path, fake_infer):
    """站的 observe_power_future 全 None（空真值序列）-> cf_status=no_overlap、不崩溃。"""
    def ghi(v0):
        return [float(v0 + 100 * k) for k in range(4)]

    OFF = {"c1": 40.0, "c2": 20.0, "c3": 0.0}
    rows = []

    def add(st, T, gt):
        rows.append({"station": st, "timestamp_win": pd.Timestamp(T), "observe_power": 1.0,
                     "observe_power_future": [g / 10.0 for g in gt] if gt else None,
                     "GHI_SOLARGIS_predict": [g + OFF[st] for g in gt] if gt else None,
                     "GHI_real_future": gt if gt else None})

    add("c1", "2026-07-16 10:00:00", ghi(100)); add("c1", "2026-07-16 10:15:00", ghi(200))
    add("c2", "2026-07-16 10:00:00", ghi(100)); add("c2", "2026-07-16 10:15:00", ghi(200))
    add("c3", "2026-07-16 10:00:00", None)                    # 空真值
    pd.DataFrame(rows).to_parquet(tmp_path / "input.parquet")

    dt = pd.date_range("2026-07-16 10:15:00", "2026-07-16 11:30:00", freq="15min")
    flat = {"c1": [100., 200, 300, 400, 500], "c2": [100., 200, 300, 400, 500, 600],
            "c3": [0., 100, 200, 300, 400, 500]}
    pred = pd.DataFrame({"dtime": dt})
    pred["c1"] = [(flat["c1"][i] + 40) / 10 if i < 5 else float('nan') for i in range(6)]
    pred["c2"] = [(flat["c2"][i] + 20) / 10 for i in range(6)]
    pred["c3"] = [(flat["c3"][i] + 0) / 10 for i in range(6)]
    pred.to_parquet(tmp_path / "predict.parquet")

    r = _run(tmp_path, _cf_args(fake_infer, tmp_path, ["--no-station-plots"]))
    d = r["fleet"].set_index("station")
    assert d.loc["c1", "cf_status"] == "ok" and d.loc["c2", "cf_status"] == "ok"
    assert d.loc["c3", "cf_status"] == "no_overlap"


# ---------------------------------------------------------------- 南网 nanwang_official 指标测试
def _write_info(wd, mapping):
    pd.DataFrame([{"station": s, "GCCAPCITY": g} for s, g in mapping.items()]).to_csv(wd / "info.csv", index=False)
    return str(wd / "info.csv")


def _nanwang(p_real, p_pred, gc):
    a, p = np.asarray(p_real, float), np.asarray(p_pred, float)
    return (1.0 - np.sqrt(np.mean(((a - p) / np.maximum(a, 0.2 * gc)) ** 2))) * 100.0


def test_nanwang_fleet_ranking(cf_data):
    """--info-csv：fleet_ranking 增列 GCCAPCITY + nanwang_official_power，值与公式一致，join 用各站自己的 GCCAPCITY。"""
    info = _write_info(cf_data, {"c1": 100.0, "c2": 200.0})
    fr = _run(cf_data, ["--no-plots", "--info-csv", info])["fleet"].set_index("station")
    assert fr.loc["c1", "GCCAPCITY"] == 100.0 and fr.loc["c2", "GCCAPCITY"] == 200.0
    assert fr.loc["c1", "nanwang_official_power"] == pytest.approx(
        _nanwang([10, 20, 30, 40, 50], [14, 24, 34, 44, 54], 100.0), abs=1e-2)   # predict = 真值+4
    assert fr.loc["c2", "nanwang_official_power"] == pytest.approx(
        _nanwang([10, 20, 30, 40, 50, 60], [12, 22, 32, 42, 52, 62], 200.0), abs=1e-2)  # predict = 真值+2


def test_nanwang_counterfactual(cf_data, fake_infer):
    """反事实：fleet_ranking 增 nanwang_official_power_cf，换真值 GHI 后功率完美 → cf=100%。"""
    info = _write_info(cf_data, {"c1": 100.0, "c2": 200.0})
    d = _run(cf_data, _cf_args(fake_infer, cf_data,
                               ["--no-plots", "--info-csv", info]))["fleet"].set_index("station")
    assert d.loc["c1", "GCCAPCITY"] == 100.0
    assert d.loc["c1", "nanwang_official_power"] == pytest.approx(
        _nanwang([10, 20, 30, 40, 50], [14, 24, 34, 44, 54], 100.0), abs=1e-2)
    assert d.loc["c1", "nanwang_official_power_cf"] == pytest.approx(100.0, abs=1e-6)


def test_nanwang_missing_station_blank(cf_data):
    """info-csv 缺某站：该站 GCCAPCITY/nanwang 留空 + 告警，其余站照常。"""
    info = _write_info(cf_data, {"c1": 100.0})               # c2 缺
    r = _run(cf_data, ["--no-plots", "--info-csv", info])
    fr = r["fleet"].set_index("station")
    assert fr.loc["c1", "GCCAPCITY"] == 100.0
    assert pd.isna(fr.loc["c2", "GCCAPCITY"])
    assert "no GCCAPCITY" in r["out"]


def test_info_real_shape_autojoin_city(cf_data):
    """真实 info.csv 形态：无 station 列（plantid join 自动探测）、拼写 GCCAPACITY、含 city；
    fleet_ranking 增 city 列且 nanwang 指标照常；--info 为 --info-csv 别名。"""
    pd.DataFrame([
        {"plantid": "c1", "plantname": "光伏c1", "city": "阳江", "GCCAPACITY": 100.0},
        {"plantid": "c2", "plantname": "光伏c2", "city": "南宁", "GCCAPACITY": 200.0},
    ]).to_csv(cf_data / "info.csv", index=False)
    r = _run(cf_data, ["--no-plots", "--info", str(cf_data / "info.csv")])
    fr = r["fleet"].set_index("station")
    assert fr.loc["c1", "city"] == "阳江" and fr.loc["c2", "city"] == "南宁"
    assert fr.loc["c1", "GCCAPCITY"] == 100.0 and fr.loc["c2", "GCCAPCITY"] == 200.0
    assert fr.loc["c1", "nanwang_official_power"] == pytest.approx(
        _nanwang([10, 20, 30, 40, 50], [14, 24, 34, 44, 54], 100.0), abs=1e-2)
    assert "join column auto-detected: 'plantid'" in r["out"]


def test_nanwang_off_when_no_info(cf_data):
    """不给 --info-csv：无 GCCAPCITY / nanwang 列（含 factor 扫描列），向后兼容。"""
    fr = _run(cf_data, ["--no-plots"])["fleet"]
    assert "GCCAPCITY" not in fr.columns and "nanwang_official_power" not in fr.columns
    assert not [c for c in fr.columns if c.startswith("nanwang_official_power_x")]


# ---------------------------------------------------------------- 南网 factor 灵敏度扫描
FACTOR_COLS = ["nanwang_official_power_x1.4", "nanwang_official_power_x1.2",
               "nanwang_official_power", "nanwang_official_power_x0.8",
               "nanwang_official_power_x0.6", "nanwang_official_power_x0.4"]


def test_nanwang_factor_columns_values(cf_data):
    """fleet_ranking 每站补 5 个 factor 列：预测的每个点乘以 factor 后按南网口径重算。"""
    info = _write_info(cf_data, {"c1": 100.0, "c2": 200.0})
    fr = _run(cf_data, ["--no-plots", "--info-csv", info])["fleet"].set_index("station")
    c1_true, c1_pred = [10, 20, 30, 40, 50], [14, 24, 34, 44, 54]
    for f in (1.4, 1.2, 0.8, 0.6, 0.4):
        assert fr.loc["c1", f"nanwang_official_power_x{f:g}"] == pytest.approx(
            _nanwang(c1_true, [p * f for p in c1_pred], 100.0), abs=1e-2)
    assert fr.loc["c2", "nanwang_official_power_x0.4"] == pytest.approx(
        _nanwang([10, 20, 30, 40, 50, 60], [p * 0.4 for p in [12, 22, 32, 42, 52, 62]], 200.0), abs=1e-2)


def test_nanwang_factor_column_order(cf_data):
    """factor 列顺序 x1.4 / x1.2 / 官方(=x1.0) / x0.8 / x0.6 / x0.4，官方口径居中。"""
    info = _write_info(cf_data, {"c1": 100.0, "c2": 200.0})
    cols = list(_run(cf_data, ["--no-plots", "--info-csv", info])["fleet"].columns)
    assert [c for c in cols if c.startswith("nanwang_official_power")] == FACTOR_COLS


def test_nanwang_factor_not_in_station_power_csv(cf_data):
    """station_power_rmse.csv 只保留原 nanwang_official_power，不加 factor 列。"""
    info = _write_info(cf_data, {"c1": 100.0, "c2": 200.0})
    pw = _run(cf_data, ["--no-plots", "--info-csv", info])["power"]
    assert "nanwang_official_power" in pw.columns
    assert not [c for c in pw.columns if c.startswith("nanwang_official_power_x")]


def test_nanwang_factor_missing_station_blank(cf_data):
    """info-csv 缺某站：该站所有 factor 列一并留空，其余站照常。"""
    info = _write_info(cf_data, {"c1": 100.0})               # c2 缺
    fr = _run(cf_data, ["--no-plots", "--info-csv", info])["fleet"].set_index("station")
    assert fr.loc["c1", "nanwang_official_power_x1.4"] == pytest.approx(
        _nanwang([10, 20, 30, 40, 50], [p * 1.4 for p in [14, 24, 34, 44, 54]], 100.0), abs=1e-2)
    for c in FACTOR_COLS:
        assert pd.isna(fr.loc["c2", c])


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


# ---------------------------------------------------------------- 三线共轴 + 三方交集
def test_display_multi_puts_every_series_on_one_x_axis():
    """真值/基线/反事实覆盖各不相同 -> 并集一根 x 轴，缺口填 0，三条线等长。"""
    idx = pd.date_range("2026-07-27 00:00", periods=4, freq="15min")
    truth = pd.Series([1., 2, 3, 4], index=idx)
    base = pd.Series([1., 2], index=idx[:2])                   # 少后两点
    cf = pd.Series([9., 9], index=idx[2:])                     # 少前两点
    times, tv, others = sa._display_multi(truth, [base, cf], False, 5.0)
    assert list(times) == list(idx)                            # 并集 = 4 点
    assert [len(o) for o in others] == [4, 4] and len(tv) == 4
    assert list(others[0]) == [1.0, 2.0, 0.0, 0.0]             # base 缺口填 0
    assert list(others[1]) == [0.0, 0.0, 9.0, 9.0]             # cf 缺口填 0


def test_display_multi_matches_display_for_two_series():
    """两序列时与既有 _display 完全一致（包装器不得改变旧行为）。"""
    idx = pd.date_range("2026-07-27 00:00", periods=4, freq="15min")
    a = pd.Series([1., 2, 3, 4], index=idx)
    b = pd.Series([5., 6], index=idx[:2])
    t1, av1, bv1 = sa._display(a, b, False, 5.0)
    t2, av2, others = sa._display_multi(a, [b], False, 5.0)
    assert list(t1) == list(t2) and list(av1) == list(av2) and list(bv1) == list(others[0])


def test_win_panel_draws_counterfactual_as_third_line():
    """win_pw 面板带 extras 时，右下子图真的多画一条线且带反事实图例。"""
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    idx = pd.date_range("2026-07-27 00:00", periods=4, freq="15min")
    panel = ("Power", idx, np.array([1., 2, 3, 4]), np.array([2., 3, 4, 5]), 1.0, 4,
             "observed power", "predicted power",
             [(np.array([1., 2, 3, 4]), "counterfactual (GHI->truth)", "#2ca02c", "-",
               "cf RMSE=0.000")])
    fig, ax = plt.subplots()
    sa._draw_win_panel(ax, panel, "Power", "D+1", 1)
    labels = [ln.get_label() for ln in ax.get_lines()]
    assert len(ax.get_lines()) == 3
    assert "counterfactual (GHI->truth)" in labels
    plt.close(fig)


def test_cf_metrics_scores_on_three_way_intersection():
    """基线与反事实覆盖不同 -> 只在 truth∩base∩cf 上打分，两侧点集必须一致。"""
    idx = pd.date_range("2026-07-27 00:00", periods=4, freq="15min")
    truth = pd.Series([10., 10, 10, 10], index=idx)
    base = pd.Series([12., 12, 12], index=idx[:3])             # 缺最后一点
    cf = pd.Series([10., 10, 10], index=idx[1:])               # 缺第一点
    got = sa.cf_metrics(truth, base, cf, False, 5.0, cap=10.0)
    assert got is not None
    m, (times, t, b, c) = got
    assert m["n_points"] == 2 and list(times) == list(idx[1:3])   # 交集只剩 2 点
    assert m["nrmse_base"] == pytest.approx(20.0)                # |12-10|/10 ×100
    assert m["nrmse_cf"] == pytest.approx(0.0, abs=1e-9)


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
         "--predict", str(wd / "predict.parquet"), "--out-dir", str(wd / "out")] + list(extra),
        cwd=str(wd), capture_output=True, text=True)
    assert r.returncode == 0, r.stdout + r.stderr
    return r


def _rep(wd, name="20260726"):
    """Report root for --short runs: <out>/<起报日 YYYYMMDD>/."""
    return wd / "out" / name


def test_short_makes_two_folders_96pts(short_data):
    r = _run_short(short_data, ["--no-plots", "--pred-col-template", "{station}"])
    for sub in ("D+1", "D+4"):
        d = _rep(short_data) / sub
        assert d.is_dir(), f"missing {sub}"
        pw = pd.read_csv(d / "station_power_rmse.csv")
        assert set(pw["n_points"]) == {96}, f"{sub}: {pw['n_points'].tolist()}"
    assert "using D = 2026-07-26" in r.stdout               # auto-fallback announced


def test_short_date_override(short_data):
    r = _run_short(short_data, ["--no-plots", "--pred-col-template", "{station}",
                                "--date", "2026-07-26"])
    pw = pd.read_csv(_rep(short_data) / "D+1" / "station_power_rmse.csv")
    assert set(pw["n_points"]) == {96}
    assert "using D" not in r.stdout                        # explicit date -> no fallback line


def test_short_date_shifts_window(short_data):
    """--date 给一个与自动推断不同的日期(2026-07-27 vs 自动的 2026-07-26)，应真正把切片挪到新日期上，
    而不只是凑巧和自动推断值相同（test_short_date_override 覆盖的是后一种情况）。"""
    r = _run_short(short_data, ["--no-plots", "--pred-col-template", "{station}",
                                "--date", "2026-07-27"])
    pw = pd.read_csv(_rep(short_data, "20260727") / "D+1" / "station_power_rmse.csv")
    assert set(pw["n_points"]) == {96}
    assert set(pw["t_start"]) == {"2026-07-28 00:00:00"}    # D+1 = --date + 1 day, moved off the auto-inferred D+1
    assert "using D" not in r.stdout                        # explicit date -> no fallback line


def test_short_worst_only(short_data):
    # --worst-only 1：每个切片只画最差 1 站的组合图，CSV 仍含全部站
    r = _run_short(short_data, ["--pred-col-template", "{station}", "--worst-only", "1"])
    pw = pd.read_csv(_rep(short_data) / "D+1" / "station_power_rmse.csv")
    assert len(pw) == 2                                     # CSV 全量
    pngs = [f for f in os.listdir(_rep(short_data) / "D+1")
            if f.startswith("station_") and f.endswith(".png")]
    assert len(pngs) == 1                                   # 仅最差 1 站出组合图


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
        d = _rep(short_data) / sub
        assert (d / "fleet_overview.png").exists()
        assert (d / "theil_decomposition.png").exists()
        assert (d / "fleet_ranking.csv").exists()
        assert (d / "station_s1.png").exists()              # 每站一张 2x2 组合图，直接落在切片目录
        assert (d / "station_s2.png").exists()
        assert not (d / "stations").exists()                # 旧版逐图目录已随 API 反事实一并删除


def test_short_counterfactual_per_window(short_cf_data, fake_infer):
    """480 点单窗：推理只跑一次（1 窗 × 2 趟），两个切片各自复用同一份结果切片打分。"""
    r = subprocess.run(
        [sys.executable, SCRIPT, "--input", str(short_cf_data / "input.parquet"),
         "--predict", str(short_cf_data / "predict.parquet"),
         "--out-dir", str(short_cf_data / "out"), "--no-plots", "--pred-col-template", "{station}",
         "--counterfactual", "--inference-dir", fake_infer.dir,
         "--checkpoints-dir", str(short_cf_data / "ckpt"),
         "--config", str(short_cf_data / "config.yaml")],
        cwd=str(short_cf_data), capture_output=True, text=True)
    assert r.returncode == 0, r.stdout + r.stderr
    for sub in ("D+1", "D+4"):
        p = _rep(short_cf_data) / sub / "fleet_ranking.csv"
        assert p.exists(), f"missing fleet_ranking in {sub}"
        d = pd.read_csv(p).set_index("station")
        assert d.loc["c1", "cf_status"] == "ok"
        assert int(d.loc["c1", "n_points"]) == 96              # 每切片 96 点
        assert d.loc["c1", "power_nrmse_cf"] == pytest.approx(0.0, abs=1e-9)
    assert fake_infer.count == 2                                # 1 窗 × 2 趟，两切片共用


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
    d1_pw = pd.read_csv(_rep(short_data_missing_d4) / "D+1" / "station_power_rmse.csv")
    assert set(d1_pw["n_points"]) == {96}
    d4_path = _rep(short_data_missing_d4) / "D+4" / "station_power_rmse.csv"
    # "nothing produced -> warn+return" 路径下该文件根本不会被写出；即便某天该路径的行为改成写空文件，也应容忍
    assert (not d4_path.exists()) or pd.read_csv(d4_path).empty


@pytest.fixture
def hist_data(tmp_path):
    """起报 T=2026-07-26 10:00. Historical list cols observe_power/GHI_SOLARGIS: 7-day (672-pt, 15min)
    lists whose LAST element sits at T. Forward observe_power_future + predict cover D+1/D+4 so --short's
    metric pass also runs without crashing."""
    T = pd.Timestamp("2026-07-26 10:00:00")
    n_hist, n_fut = 672, 480
    hist_power = {"s1": [float(k) for k in range(n_hist)], "s2": [float(k + 1000) for k in range(n_hist)]}
    hist_ghi = {"s1": [float(2 * k) for k in range(n_hist)], "s2": [float(2 * k + 1) for k in range(n_hist)]}
    fut = {"s1": [float(10 + (k % 96)) for k in range(n_fut)], "s2": [float(5 + (k % 96)) for k in range(n_fut)]}
    rows = [{"station": st, "timestamp_win": T, "observe_power_future": fut[st],
             "observe_power": hist_power[st], "GHI_SOLARGIS": hist_ghi[st]} for st in ("s1", "s2")]
    pd.DataFrame(rows).to_parquet(tmp_path / "input.parquet")
    times = [T + pd.Timedelta(minutes=15 * (k + 1)) for k in range(n_fut)]
    pred = pd.DataFrame({"dtime": times})
    for st in ("s1", "s2"):
        pred[st] = fut[st]
    pred.to_parquet(tmp_path / "predict.parquet")
    return tmp_path


def test_history_panels_in_combined_plot(hist_data):
    # 历史列齐全 -> 每切片每站一张组合图（含 history 面板），不再有独立 history/ 目录
    r = _run_short(hist_data, ["--pred-col-template", "{station}", "--no-fleet"])
    for sub in ("D+1", "D+4"):
        assert (_rep(hist_data) / sub / "station_s1.png").exists()
        assert (_rep(hist_data) / sub / "station_s2.png").exists()
    assert not (_rep(hist_data) / "history").exists()
    assert "history column" not in r.stdout                 # 无缺列告警


def test_history_no_plots_flag_skips(hist_data):
    r = _run_short(hist_data, ["--no-plots", "--pred-col-template", "{station}"])
    assert not (_rep(hist_data) / "history").exists()
    assert not (_rep(hist_data) / "D+1" / "station_s1.png").exists()


def test_history_missing_column_warns(short_data):
    # short_data has no observe_power / GHI_SOLARGIS columns -> warn per missing col, combined plot still produced
    r = _run_short(short_data, ["--no-fleet", "--pred-col-template", "{station}"])
    assert "history column 'observe_power' missing" in r.stdout
    assert "history column 'GHI_SOLARGIS' missing" in r.stdout
    assert (_rep(short_data) / "D+1" / "station_s1.png").exists()
