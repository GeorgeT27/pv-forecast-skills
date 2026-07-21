"""row-diagnostic 自包含单测：脚本内确定性合成三张小表（零随机、不依赖任何 skill/golden）。

埋点：
  - wind：平时 RMSE≈1，仅目标行飙到 20 → 必须被 row_analysis 顶到 z 榜首、status=⚠️偏高。
  - always_bad：一直很坏（RMSE 在 9/11 抖，目标行=10=历史均值）→ z≈0、绝不被点反常
    （证明"跟自己历史比"而非"绝对误差大"）。
  - good：pred==true，RMSE=0。orphan_pred / mystery：配不上对 → 进 unmapped、不崩。
目标行 = 2025-01-03 10:00（day2, 10:00），也是 power 最坏行 → 验 --worst 命中它。
"""
import json
import os
import subprocess
import sys

import pandas as pd
import pytest

HERE = os.path.dirname(os.path.abspath(__file__))
H = 8                                   # 短时域，跑得快
TARGET = pd.Timestamp("2025-01-03 10:00:00")


def _rows():
    rows = []
    for d in range(8):
        for h in (8, 9, 10):
            ts = pd.Timestamp("2025-01-01 00:00:00") + pd.Timedelta(days=d, hours=h)
            is_target = (ts == TARGET)
            tp = [float(h * 10 + i) for i in range(H)]
            perr = 5.0 if is_target else 0.1
            wdelta = 20.0 if is_target else 1.0
            adelta = 10.0 if is_target else (9.0 if (d + h) % 2 == 0 else 11.0)
            rows.append({
                "timestamp": ts,
                "pred_M1": [x + perr for x in tp],
                "observe_power_future": tp,
                "good_pred": [float(i) for i in range(H)],
                "good": [float(i) for i in range(H)],
                "wind_pred": [50.0 + i + wdelta for i in range(H)],
                "wind": [50.0 + i for i in range(H)],
                "always_bad_pred": [20.0 + i + adelta for i in range(H)],
                "always_bad": [20.0 + i for i in range(H)],
                "orphan_pred": [1.0] * H,        # 无 orphan 基名 → unmapped
                "mystery": [2.0] * H,            # 无 _pred → unmapped
            })
    return pd.DataFrame(rows)


@pytest.fixture
def workdir(tmp_path):
    df = _rows()
    df[["timestamp", "pred_M1"]].to_parquet(tmp_path / "predict.parquet")
    df[["timestamp", "observe_power_future"]].to_parquet(tmp_path / "test.parquet")
    fcols = ["timestamp", "good_pred", "good", "wind_pred", "wind",
             "always_bad_pred", "always_bad", "orphan_pred", "mystery"]
    df[fcols].to_parquet(tmp_path / "feature_true.parquet")
    r = subprocess.run(
        [sys.executable, os.path.join(HERE, "build_baseline.py"),
         "--predict", str(tmp_path / "predict.parquet"),
         "--test", str(tmp_path / "test.parquet"),
         "--feature-true", str(tmp_path / "feature_true.parquet"),
         "--out", str(tmp_path / "baseline.json")],
        cwd=str(tmp_path), capture_output=True, text=True)
    assert r.returncode == 0, r.stdout + r.stderr
    return tmp_path


def _run_row(workdir, extra):
    r = subprocess.run(
        [sys.executable, os.path.join(HERE, "row_analysis.py"),
         "--model", "pred_M1", "--baseline", str(workdir / "baseline.json"),
         "--no-plots", "--out-dir", str(workdir), "--prefix", "t"] + extra,
        cwd=str(workdir), capture_output=True, text=True)
    assert r.returncode == 0, r.stdout + r.stderr
    js = [f for f in os.listdir(workdir) if f.startswith("t_") and f.endswith(".json")]
    return json.load(open(workdir / js[0], encoding="utf-8"))


def test_baseline_has_global_hourly_and_unmapped(workdir):
    base = json.load(open(workdir / "baseline.json", encoding="utf-8"))
    assert set(base["feature_pairs"]) == {"good", "wind", "always_bad"}
    assert set(base["meta"]["unmapped_feature_cols"]) == {"orphan_pred", "mystery"}
    pw = base["models"]["pred_M1"]["power"]
    assert pw["global"]["n"] == 24 and pw["by_hour"]["10:00"]["n"] == 8
    assert base["features"]["wind"]["global"]["mean"] > 0


def test_anomaly_feature_is_top_suspect(workdir):
    """目标行：wind 顶到 z 榜首且 ⚠️偏高；power 也反常。"""
    s = _run_row(workdir, ["--row", "2025-01-03 10:00:00"])
    assert s["top_suspect"] == "wind"
    assert "wind" in s["abnormal_features"]
    wind = next(f for f in s["features"] if f["feature"] == "wind")
    assert wind["z"] >= 2 and wind["status"] == "⚠️偏高"
    assert s["power"]["vs_global"]["z"] >= 2


def test_consistently_bad_feature_not_flagged(workdir):
    """always_bad 绝对误差大但一贯如此 → z≈0、不进反常名单（核心纪律）。"""
    s = _run_row(workdir, ["--row", "2025-01-03 10:00:00"])
    ab = next(f for f in s["features"] if f["feature"] == "always_bad")
    assert abs(ab["z"]) < 1
    assert "always_bad" not in s["abnormal_features"]
    assert ab["base_mean"] > 5           # 历史均值确实很高（大误差），但不反常


def test_worst_selects_target_row(workdir):
    s = _run_row(workdir, ["--worst"])
    assert s["timestamp"] == "2025-01-03 10:00:00"


def test_out_of_range_timestamp_errors(workdir):
    r = subprocess.run(
        [sys.executable, os.path.join(HERE, "row_analysis.py"),
         "--model", "pred_M1", "--baseline", str(workdir / "baseline.json"),
         "--no-plots", "--row", "2099-01-01 00:00:00"],
        cwd=str(workdir), capture_output=True, text=True)
    assert r.returncode != 0
    assert "不在" in (r.stdout + r.stderr)
