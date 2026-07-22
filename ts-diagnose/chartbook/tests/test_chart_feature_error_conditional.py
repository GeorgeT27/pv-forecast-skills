"""feature-error-conditional golden：真凶 ghi 的质量误差 q∈{0,20} 与 y 误差幅度
1+0.1q 完全耦合（effect_ratio=3、rho=1）；诱饵 temp 的 q 与 y 误差按奇偶交替解耦
（effect_ratio<1.3）——防冤枉埋点。"""
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

import chart_feature_error_conditional as cfe  # noqa: E402
import chart_common as cc                      # noqa: E402
from synth import make_long, alt               # noqa: E402

WINDOWS = [f"2024-01-{d:02d}" for d in range(1, 11)]   # w 索引 = 日-1


def _q_ghi(w):
    return 0.0 if int(w[-2:]) - 1 < 5 else 20.0


def _q_temp(w):
    return 20.0 if (int(w[-2:]) - 1) % 2 == 0 else 0.0


def _pred_df():
    df = make_long(["A"], ["U1"], WINDOWS, 8,
                   lambda m, u, w, s: alt(1.0 + 0.1 * _q_ghi(w), s))
    df["window_ts"] = pd.to_datetime(df["window_ts"])
    df["err"] = df["y_pred"] - df["y_true"]
    return df


def _feat_df():
    rows = []
    for w in WINDOWS:
        for s in range(8):
            rows.append({"window_ts": w, "unit_id": "U1", "feature": "ghi",
                         "horizon_step": s, "f_pred": 100.0 + _q_ghi(w),
                         "f_true": 100.0})
            rows.append({"window_ts": w, "unit_id": "U1", "feature": "temp",
                         "horizon_step": s, "f_pred": 50.0 + _q_temp(w),
                         "f_true": 50.0})
    df = pd.DataFrame(rows)
    df["window_ts"] = pd.to_datetime(df["window_ts"])
    return df


def test_load_features_contract(tmp_path):
    p = tmp_path / "f.csv"
    _feat_df().drop(columns=["f_true"]).to_csv(p, index=False)
    out = cc.load_features(p)
    assert "f_true" in out.columns and out["f_true"].isna().all()
    import pytest
    with pytest.raises(ValueError, match="feature"):
        bad = tmp_path / "bad.csv"
        _feat_df().drop(columns=["feature"]).to_csv(bad, index=False)
        cc.load_features(bad)


def test_culprit_and_decoy():
    st = cfe.compute(_pred_df(), _feat_df(), n_bins=5)
    ghi = st["models"]["A"]["ghi"]
    temp = st["models"]["A"]["temp"]
    assert np.isclose(ghi["quality_effect_ratio"], 3.0)
    assert ghi["quality_monotonic_rho"] == 1.0
    assert temp["quality_effect_ratio"] < 1.3          # 诱饵不得被点名
    assert set(ghi["quality_bins"]) and set(ghi["value_bins"])


def test_no_ftrue_falls_back_to_value_bins_only():
    fd = _feat_df()
    fd["f_true"] = np.nan
    st = cfe.compute(_pred_df(), fd, n_bins=5)
    a = st["models"]["A"]["ghi"]
    assert a["quality_bins"] is None and a["quality_effect_ratio"] is None
    assert a["value_bins"]


def test_main_writes_outputs(tmp_path):
    pp, fp = tmp_path / "p.csv", tmp_path / "f.csv"
    _pred_df().drop(columns=["err"]).to_csv(pp, index=False)
    _feat_df().to_csv(fp, index=False)
    cfe.main(["--pred", str(pp), "--features", str(fp),
              "--out-dir", str(tmp_path)])
    assert (tmp_path / "feature-error-conditional.json").exists()
    assert (tmp_path / "feature-error-conditional.png").exists()
