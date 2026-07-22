"""feature-trend-overlay golden：2 月为坏片（日误差幅度=1+0.1q_d，q_d 隔日 0/20），
日 y-RMSE 与日 quality 完全同步 → 切片自动选中 2024-02、sync_corr≈1、basis=quality。"""
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

import chart_feature_trend_overlay as cfo  # noqa: E402
from synth import make_long, alt           # noqa: E402

FEB = [f"2024-02-{d:02d}" for d in range(1, 13)]
OTHER = [f"2024-{mm:02d}-{dd:02d}" for mm in (1, 3) for dd in (5, 15, 25)]


def _q(w):
    if not w.startswith("2024-02"):
        return 0.0
    return 0.0 if int(w[-2:]) % 2 == 0 else 20.0


def _amp(w):
    return 0.5 if not w.startswith("2024-02") else 1.0 + 0.1 * _q(w)


def _pred_df():
    df = make_long(["A"], ["U1"], FEB + OTHER, 4,
                   lambda m, u, w, s: alt(_amp(w), s))
    df["window_ts"] = pd.to_datetime(df["window_ts"])
    df["err"] = df["y_pred"] - df["y_true"]
    return df


def _feat_df():
    rows = []
    for w in FEB + OTHER:
        for s in range(4):
            rows.append({"window_ts": w, "unit_id": "U1", "feature": "ghi",
                         "horizon_step": s, "f_pred": 100.0 + _q(w),
                         "f_true": 100.0})
    df = pd.DataFrame(rows)
    df["window_ts"] = pd.to_datetime(df["window_ts"])
    return df


def test_slice_autopick_and_sync():
    st = cfo.compute(_pred_df(), _feat_df())
    assert st["slice"] == "2024-02" and st["model"] == "A"
    ghi = st["features"]["ghi"]
    assert ghi["sync_basis"] == "quality"
    assert ghi["sync_corr"] > 0.99
    some_day = "2024-02-03"
    rec = ghi["aligned"][some_day]
    assert np.isclose(rec["y_rmse"], 3.0) and np.isclose(rec["quality"], 20.0)


def test_level_fallback_without_ftrue():
    fd = _feat_df()
    fd["f_true"] = np.nan
    st = cfo.compute(_pred_df(), fd)
    assert st["features"]["ghi"]["sync_basis"] == "level"


def test_main_writes_outputs(tmp_path):
    pp, fp = tmp_path / "p.csv", tmp_path / "f.csv"
    _pred_df().drop(columns=["err"]).to_csv(pp, index=False)
    _feat_df().to_csv(fp, index=False)
    cfo.main(["--pred", str(pp), "--features", str(fp),
              "--out-dir", str(tmp_path)])
    assert (tmp_path / "feature-trend-overlay.json").exists()
    assert (tmp_path / "feature-trend-overlay.png").exists()
