"""lookback-decay golden:只读最近一步 → 全部质量落最近桶;能力缺失抛错。"""
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

import attribution_common as ac    # noqa: E402
import chart_lookback_decay as cld  # noqa: E402

LB_ADAPTER = Path(__file__).resolve().parents[1] / "golden" / \
    "example_lookback_adapter" / "predict_adapter.py"
LIN_ADAPTER = Path(__file__).resolve().parents[1] / "golden" / \
    "example_predict_adapter" / "predict_adapter.py"
WINDOWS = ["2024-01-01", "2024-01-02", "2024-01-03", "2024-01-04"]


def _pred():
    rows = [{"window_ts": w, "unit_id": "U1", "model": "A",
             "horizon_step": s, "y_true": 11.0, "y_pred": 11.0}
            for w in WINDOWS for s in range(4)]
    df = pd.DataFrame(rows)
    df["window_ts"] = pd.to_datetime(df["window_ts"])
    df["err"] = df["y_pred"] - df["y_true"]
    return df


def test_all_weight_on_recent_bucket():
    st = cld.compute(_pred(), ac.load_adapter(LB_ADAPTER), max_windows=4,
                     seed=0, max_calls=5000, per_instance=True)
    assert st["lookback_steps"] == 8
    assert np.isclose(st["weights"][0], 1.0)
    assert all(np.isclose(w, 0.0) for w in st["weights"][1:])
    assert np.isclose(st["short_term_share"], 1.0)
    assert st["per_instance"]["median"] == 1
    assert set(st["per_instance"]["hist"]) == {"1"}
    assert st["coverage"]["truncated"] is False


def test_capability_missing_raises():
    with pytest.raises(ValueError, match="perturb_lookback"):
        cld.compute(_pred(), ac.load_adapter(LIN_ADAPTER), max_windows=4,
                    seed=0, max_calls=100)


def test_main_writes_outputs(tmp_path):
    p = tmp_path / "pred.csv"
    _pred().to_csv(p, index=False)
    cld.main(["--pred", str(p), "--adapter", str(LB_ADAPTER),
              "--out-dir", str(tmp_path)])
    assert (tmp_path / "lookback-decay.json").exists()
    assert (tmp_path / "lookback-decay.png").exists()


def test_budget_truncation_keeps_completed_buckets():
    """max_calls=12:base(4)+桶1(4)+桶2(4) 后截断——已完成桶保留、
    weights/share 置 null、truncated 如实(Critical 修复回归)。"""
    st = cld.compute(_pred(), ac.load_adapter(LB_ADAPTER), max_windows=4,
                     seed=0, max_calls=12)
    assert st["coverage"]["truncated"] is True
    assert st["buckets_evaluated"] == 2
    assert len(st["delta_by_bucket"]) == 2
    assert np.isclose(st["delta_by_bucket"][0], 1.0)
    assert st["weights"] is None and st["short_term_share"] is None
