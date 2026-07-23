"""local-waterfall golden:线性适配器 φ=(6,1,0) 解析精确回收;诱饵不冤枉。"""
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

shap = pytest.importorskip("shap")  # noqa: F841

import attribution_common as ac      # noqa: E402
import chart_local_waterfall as clw  # noqa: E402

ADAPTER = Path(__file__).resolve().parents[1] / "golden" / \
    "example_predict_adapter" / "predict_adapter.py"
WINDOWS = [f"2024-01-{d:02d}" for d in range(1, 7)]


def _feats():
    rows = []
    for w in WINDOWS:
        for s in range(6):
            for fn, fp in (("fa", 3.0), ("fb", 2.0), ("fc", 6.0)):
                rows.append({"window_ts": w, "unit_id": "U1", "feature": fn,
                             "horizon_step": s, "f_pred": fp, "f_true": 1.0})
    df = pd.DataFrame(rows)
    df["window_ts"] = pd.to_datetime(df["window_ts"])
    return df


def _pred():
    # 真值=适配器吃 f_true(全1)=4;实际预测=适配器吃 f_pred=3*3+1*2+0*6=11
    rows = [{"window_ts": w, "unit_id": "U1", "model": "A",
             "horizon_step": s, "y_true": 4.0, "y_pred": 11.0}
            for w in WINDOWS for s in range(6)]
    df = pd.DataFrame(rows)
    df["window_ts"] = pd.to_datetime(df["window_ts"])
    df["err"] = df["y_pred"] - df["y_true"]
    return df


def test_phi_exact_and_decoy_cleared():
    st = clw.compute(_pred(), _feats(), ac.load_adapter(ADAPTER), k=2,
                     seed=0, max_calls=5000)
    assert len(st["rows"]) == 2
    for row in st["rows"]:
        c = row["contributions"]
        assert np.isclose(c["fa"], 6.0)
        assert np.isclose(c["fb"], 1.0)
        assert np.isclose(c["fc"], 0.0), "零系数大偏差诱饵不得被冤枉"
        assert np.isclose(row["base_value"], 0.0)
        assert np.isclose(row["check_sum"], 7.0)
        assert np.isclose(row["rmse_actual"], 7.0)
        assert row["basis"]["fa"] == "f_true"
    assert st["explainer"] == "kernel"


def test_main_writes_outputs(tmp_path):
    p, f = tmp_path / "pred.csv", tmp_path / "feat.csv"
    _pred().to_csv(p, index=False)
    _feats().to_csv(f, index=False)
    clw.main(["--pred", str(p), "--features", str(f),
              "--adapter", str(ADAPTER), "--out-dir", str(tmp_path),
              "--k", "2"])
    assert (tmp_path / "local-waterfall.json").exists()
    assert (tmp_path / "local-waterfall.png").exists()
