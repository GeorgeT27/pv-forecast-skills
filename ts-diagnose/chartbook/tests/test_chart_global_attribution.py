"""global-attribution golden:线性适配器 3:1:0 精确回收;预算截断如实。

pytestmark 过滤的 RuntimeWarning 与 shap/golden 断言无关：本环境 anaconda
的 numpy/scipy 绑的 Intel OpenMP(libiomp)与 shap 依赖链带的 LLVM
OpenMP(libomp)同进程加载时 threadpoolctl 会告警(仅当 shap 与 sklearn
的 KMeans 同 session 加载才触发,纯环境二进制共存提示，非 shap API
弃用、非本任务代码逻辑问题)。禁改 numpy/scipy/sklearn/shap 版本，按来源
精确过滤本文件内的告警，不做全局静默(跨文件的同一告警见 task-3-report.md
"其他发现"节)。"""
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

pytestmark = pytest.mark.filterwarnings(
    "ignore:(?s).*Found Intel OpenMP.*LLVM OpenMP.*:RuntimeWarning")

shap = pytest.importorskip("shap")  # noqa: F841

import attribution_common as ac      # noqa: E402
import chart_global_attribution as cga  # noqa: E402

ADAPTER = Path(__file__).resolve().parents[1] / "golden" / \
    "example_predict_adapter" / "predict_adapter.py"
WINDOWS = [f"2024-01-{d:02d}" for d in range(1, 9)]


def _feats():
    rows = []
    for i, w in enumerate(WINDOWS):
        v = 0.0 if i < 4 else 1.0
        for s in range(6):
            for fn in ("fa", "fb", "fc"):
                rows.append({"window_ts": w, "unit_id": "U1", "feature": fn,
                             "horizon_step": s, "f_pred": v})
    df = pd.DataFrame(rows)
    df["window_ts"] = pd.to_datetime(df["window_ts"])
    return df


def _pred():
    rows = [{"window_ts": w, "unit_id": "U1", "model": "A",
             "horizon_step": s, "y_true": 4.0, "y_pred": 4.0}
            for w in WINDOWS for s in range(6)]
    df = pd.DataFrame(rows)
    df["window_ts"] = pd.to_datetime(df["window_ts"])
    df["err"] = df["y_pred"] - df["y_true"]
    return df


def test_linear_ratios_recovered():
    adapter = ac.load_adapter(ADAPTER)
    st = cga.compute(_pred(), _feats(), adapter, buckets=2, max_windows=8,
                     background_k=2, seed=0, max_calls=5000)
    o = st["overall"]
    assert o["fc"] < 1e-9
    assert np.isclose(o["fa"] / o["fb"], 3.0)
    assert st["ranking"][0] == "fa" and st["ranking"][-1] == "fc"
    for row in st["by_bucket"]:
        assert np.isclose(row["fa"] / row["fb"], 3.0)
    assert st["coverage"]["truncated"] is False
    assert st["coverage"]["windows_evaluated"] == 8
    assert st["background_meta"]["k"] == 2
    assert st["explainer"] == "kernel"


def test_budget_truncation_recorded():
    adapter = ac.load_adapter(ADAPTER)
    st = cga.compute(_pred(), _feats(), adapter, buckets=2, max_windows=8,
                     background_k=2, seed=0, max_calls=20)
    assert st["coverage"]["truncated"] is True
    assert 0 < st["coverage"]["windows_evaluated"] < 8
    assert st["coverage"]["calls_used"] <= 20


def test_main_writes_outputs(tmp_path):
    p, f = tmp_path / "pred.csv", tmp_path / "feat.csv"
    _pred().to_csv(p, index=False)
    _feats().to_csv(f, index=False)
    cga.main(["--pred", str(p), "--features", str(f),
              "--adapter", str(ADAPTER), "--out-dir", str(tmp_path),
              "--buckets", "2", "--background-k", "2"])
    assert (tmp_path / "global-attribution.json").exists()
    assert (tmp_path / "global-attribution.png").exists()


def _write_torch_adapter(tmp_path):
    torch = pytest.importorskip("torch")  # noqa: F841
    p = tmp_path / "torch_adapter.py"
    p.write_text('''
"""微型 torch 线性适配器(梯度路 golden):W 两行均 [3,1,0],B=2 输出。"""
import pandas as pd
import torch

CAPABILITIES = {"perturb_features": True, "perturb_lookback": False,
                "torch_module": True, "lookback_steps": 0,
                "features": ["fa", "fb", "fc"]}

_model = torch.nn.Linear(3, 2, bias=False)
with torch.no_grad():
    _model.weight.copy_(torch.tensor([[3.0, 1.0, 0.0], [3.0, 1.0, 0.0]]))


def predict(requests):
    rows = []
    for i, r in enumerate(requests):
        ov = r.get("feature_overrides") or {}
        x = torch.tensor([[float(ov.get(f, [1.0] * 2)[0])
                           for f in ("fa", "fb", "fc")]])
        y = _model(x).detach().numpy().ravel()
        for s, v in enumerate(y):
            rows.append({"request_idx": i, "unit_id": r["unit_id"],
                         "window_ts": r["window_ts"],
                         "horizon_step": s, "y_pred": float(v)})
    return pd.DataFrame(rows)


def get_model():
    import torch as _t
    background = _t.zeros((4, 3))
    explain = _t.ones((4, 3))
    return _model, background, explain, ["fa", "fb", "fc"]
''')
    return p


def test_gradient_path_ratios(tmp_path):
    pytest.importorskip("torch")
    adapter = ac.load_adapter(_write_torch_adapter(tmp_path))
    st = cga.compute(_pred(), _feats(), adapter, buckets=2, max_windows=4,
                     background_k=2, seed=0, max_calls=5000,
                     explainer="auto")
    assert st["explainer"] == "gradient"
    o = st["overall"]
    assert o["fc"] < 1e-6
    assert np.isclose(o["fa"] / o["fb"], 3.0)
    assert st["coverage"]["calls_used"] == 0, "梯度路不打推理入口"


def test_gradient_without_torch_capability():
    """explicitly requesting gradient on a non-torch adapter should raise ValueError."""
    adapter = ac.load_adapter(ADAPTER)
    # Verify adapter indeed lacks torch capability
    assert not adapter.CAPABILITIES.get("torch_module")
    # Requesting gradient should raise ValueError with clear message
    with pytest.raises(ValueError, match=r"gradient.*torch_module.*get_model"):
        cga.compute(_pred(), _feats(), adapter, buckets=2, max_windows=4,
                    background_k=2, seed=0, max_calls=5000,
                    explainer="gradient")
