"""attribution_common golden:加载校验有牙、线性适配器数学、预算与缓存。"""
import sys
from pathlib import Path

import numpy as np
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

import attribution_common as ac  # noqa: E402

ADAPTER = Path(__file__).resolve().parents[1] / "golden" / \
    "example_predict_adapter" / "predict_adapter.py"


def test_load_adapter_ok_and_linear_math():
    mod = ac.load_adapter(ADAPTER)
    assert mod.CAPABILITIES["perturb_features"] is True
    out = mod.predict([{"unit_id": "U1", "window_ts": "2024-01-01",
                        "feature_overrides": {"fa": [2.0] * 6}}])
    # y = 3*2 + 1*1 + 0*1 = 7(fb/fc 缺省全 1)
    assert np.allclose(out.sort_values("horizon_step")["y_pred"], 7.0)
    out0 = mod.predict([{"unit_id": "U1", "window_ts": "2024-01-01"}])
    assert np.allclose(out0["y_pred"], 4.0)  # 3+1+0


def test_load_adapter_rejects_bad(tmp_path):
    p = tmp_path / "bad.py"
    p.write_text("CAPABILITIES = {'perturb_features': True}\n")
    with pytest.raises(ValueError, match="CAPABILITIES"):
        ac.load_adapter(p)
    p2 = tmp_path / "bad2.py"
    p2.write_text("CAPABILITIES = {'perturb_features': True,"
                  "'perturb_lookback': True, 'torch_module': False}\n"
                  "def predict(r): return None\n")
    with pytest.raises(ValueError, match="lookback_steps"):
        ac.load_adapter(p2)


def test_budget_and_cache(tmp_path):
    mod = ac.load_adapter(ADAPTER)
    cache = tmp_path / "cache.jsonl"
    ba = ac.BudgetedAdapter(mod, max_calls=3, cache_path=cache)
    req = {"unit_id": "U1", "window_ts": "2024-01-01",
           "feature_overrides": {"fa": [2.0] * 6}}
    y1 = ba.predict([req])[0]
    assert np.allclose(y1, 7.0) and ba.calls == 1
    ba.predict([req])
    assert ba.calls == 1, "同请求命中缓存,不重打"
    ba2 = ac.BudgetedAdapter(mod, max_calls=3, cache_path=cache)
    ba2.predict([req])
    assert ba2.calls == 0, "缓存文件跨实例生效"
    with pytest.raises(ac.BudgetExceeded):
        ba.predict([dict(req, unit_id=f"U{i}") for i in range(2, 6)])


def test_same_window_different_overrides_in_one_batch():
    """同批同窗不同扰动必须各得其值——回填按 request_idx 切(契约修复回归)。"""
    mod = ac.load_adapter(ADAPTER)
    ba = ac.BudgetedAdapter(mod, max_calls=10)
    base = {"unit_id": "U1", "window_ts": "2024-01-01"}
    ys = ba.predict([dict(base),
                     dict(base, feature_overrides={"fa": [9.0] * 6})])
    assert np.allclose(ys[0], 4.0)    # 3+1+0
    assert np.allclose(ys[1], 28.0)   # 3*9+1+0
    assert len(ys[0]) == 6 and len(ys[1]) == 6


def test_missing_request_idx_rejected(tmp_path):
    p = tmp_path / "old_style.py"
    p.write_text(
        "import pandas as pd\n"
        "CAPABILITIES = {'perturb_features': True, 'perturb_lookback': False,\n"
        "                'torch_module': False, 'lookback_steps': 0,\n"
        "                'features': []}\n"
        "def predict(requests):\n"
        "    return pd.DataFrame([{'unit_id': r['unit_id'],\n"
        "                          'window_ts': r['window_ts'],\n"
        "                          'horizon_step': 0, 'y_pred': 1.0}\n"
        "                         for r in requests])\n")
    ba = ac.BudgetedAdapter(ac.load_adapter(p), max_calls=10)
    with pytest.raises(ValueError, match="request_idx"):
        ba.predict([{"unit_id": "U1", "window_ts": "t"}])
