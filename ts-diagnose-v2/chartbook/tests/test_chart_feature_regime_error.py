"""feature-regime-error golden:双制式质心 (0,0)/(10,10)、制式 2 三倍误差 → 精确回收。"""
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

import chart_feature_regime_error as cfr  # noqa: E402
from synth import make_long, alt          # noqa: E402

R1 = [f"2024-01-{d:02d}" for d in range(1, 11)]
R2 = [f"2024-01-{d:02d}" for d in range(11, 21)]
WINDOWS = R1 + R2


def _prep(df):
    df["window_ts"] = pd.to_datetime(df["window_ts"])
    df["err"] = df["y_pred"] - df["y_true"]
    return df


def _feats():
    rows = []
    for w in WINDOWS:
        base = 0.0 if w in R1 else 10.0
        for s in range(6):
            for name in ("fa", "fb"):
                rows.append({"window_ts": w, "unit_id": "U1", "feature": name,
                             "horizon_step": s, "f_pred": base})
    df = pd.DataFrame(rows)
    df["window_ts"] = pd.to_datetime(df["window_ts"])
    return df


def _err(m, u, w, s):
    return alt(3.0 if w in R2 else 1.0, s)


def test_regimes_recovered():
    df = _prep(make_long(["A"], ["U1"], WINDOWS, 6, _err))
    st = cfr.compute(df, _feats(), seed=0)
    assert st["chosen_k"] == 2
    regs = sorted(st["regimes"], key=lambda r: r["centroid"]["fa"])
    assert np.isclose(regs[0]["centroid"]["fa"], 0.0)
    assert np.isclose(regs[1]["centroid"]["fa"], 10.0)
    assert np.isclose(regs[0]["share"], 0.5) and np.isclose(regs[1]["share"], 0.5)
    assert np.isclose(regs[0]["rmse_by_model"]["A"], 1.0)
    assert np.isclose(regs[1]["rmse_by_model"]["A"], 3.0)
    assert np.isclose(st["worst_best_ratio_by_model"]["A"], 3.0)


def test_main_writes_outputs(tmp_path):
    df = make_long(["A"], ["U1"], WINDOWS, 6, _err)
    p, f = tmp_path / "pred.csv", tmp_path / "feat.csv"
    df.to_csv(p, index=False)
    _feats().to_csv(f, index=False)
    cfr.main(["--pred", str(p), "--features", str(f),
              "--out-dir", str(tmp_path), "--seed", "0"])
    assert (tmp_path / "feature-regime-error.json").exists()
    assert (tmp_path / "feature-regime-error.png").exists()
