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


def _feats_two_clusters():
    import pandas as pd
    rows = []
    for i, w in enumerate([f"2024-01-{d:02d}" for d in range(1, 9)]):
        base = 0.0 if i < 4 else 1.0
        for s in range(6):
            for fn, v in (("fa", base), ("fb", base), ("fc", 1.0 - base)):
                rows.append({"window_ts": w, "unit_id": "U1", "feature": fn,
                             "horizon_step": s, "f_pred": v})
    df = pd.DataFrame(rows)
    df["window_ts"] = pd.to_datetime(df["window_ts"])
    return df


def test_background_set_medoids_and_meta():
    series, meta = ac.background_set(_feats_two_clusters(), k=2, seed=0)
    assert meta["k"] == 2 and meta["seed"] == 0 and len(meta["windows"]) == 2
    # 两簇 medoid 各一 → 背景序列 = 两窗均值 = 0.5
    assert np.allclose(series["fa"], 0.5)
    assert len(series["fa"]) == 6


def test_feature_corr_groups_clones_grouped():
    groups = ac.feature_corr_groups(_feats_two_clusters(), threshold=0.8)
    # fa/fb 同向克隆成一组;fc 反向(|ρ|=1 也应入组——绝对值口径)
    flat = {f for g in groups for f in g}
    assert flat == {"fa", "fb", "fc"}
    big = max(groups, key=len)
    assert set(big) == {"fa", "fb", "fc"}, "绝对相关 |ρ|≥0.8 全部成一组"


def test_background_set_degenerate_labels_all_windows():
    """k≥完整窗数时未跑聚类,meta.method 不得谎称 kmeans-medoid。"""
    feats = _feats_two_clusters()          # 该文件已有夹具:8 个完整窗
    _series, meta = ac.background_set(feats, k=99, seed=0)
    assert meta["method"] == "all-windows"
    assert meta["k"] == 8
    _series2, meta2 = ac.background_set(feats, k=2, seed=0)
    assert meta2["method"] == "kmeans-medoid"
