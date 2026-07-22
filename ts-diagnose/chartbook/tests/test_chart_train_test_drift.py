"""train-test-drift golden：1 月 train/test 同分布（PSI≈0）、2 月 test 整体 +20
（PSI 显著）→ 逐月 PSI/分位摘要回收、告警月列表恰为 ["2"]。"""
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

import chart_train_test_drift as ctd  # noqa: E402
from synth import make_long           # noqa: E402

CYCLE = [10.0, 12.0, 14.0, 16.0]


def _train_df():
    rows = []
    for mm in (1, 2):
        for i in range(200):
            rows.append({"ts": f"2023-{mm:02d}-{(i % 27) + 1:02d}",
                         "unit_id": "U1", "y": CYCLE[i % 4]})
    df = pd.DataFrame(rows)
    df["ts"] = pd.to_datetime(df["ts"])
    return df


def _pred_df():
    windows = [f"2024-{mm:02d}-{dd:02d}" for mm in (1, 2)
               for dd in range(1, 26)]

    def y_fn(w, u, s):
        base = CYCLE[(int(w[-2:]) + s) % 4]
        return base if w[5:7] == "01" else base + 20.0

    df = make_long(["A"], ["U1"], windows, 8,
                   err_fn=lambda m, u, w, s: 0.1, y_fn=y_fn)
    df["window_ts"] = pd.to_datetime(df["window_ts"])
    df["err"] = df["y_pred"] - df["y_true"]
    return df


def test_psi_helper_extremes():
    a = np.array(CYCLE * 50)
    assert ctd.psi(a, a) < 1e-6
    assert ctd.psi(a, a + 20.0) > 0.25


def test_monthly_drift_recovered():
    st = ctd.compute(_pred_df(), _train_df())
    assert st["by_month"]["1"]["psi"] < 0.05
    assert st["by_month"]["2"]["psi"] > 0.25
    assert st["alert_months"] == ["2"]
    m1 = st["by_month"]["1"]
    for k in ("n_train", "n_test", "mean_train", "mean_test",
              "median_train", "median_test", "p90_train", "p90_test"):
        assert k in m1
    assert np.isclose(m1["mean_train"], 13.0, atol=0.5)


def test_main_writes_outputs(tmp_path):
    pp, tp = tmp_path / "p.csv", tmp_path / "t.csv"
    _pred_df().drop(columns=["err"]).to_csv(pp, index=False)
    _train_df().to_csv(tp, index=False)
    ctd.main(["--pred", str(pp), "--train-y", str(tp),
              "--out-dir", str(tmp_path)])
    assert (tmp_path / "train-test-drift.json").exists()
    assert (tmp_path / "train-test-drift.png").exists()
