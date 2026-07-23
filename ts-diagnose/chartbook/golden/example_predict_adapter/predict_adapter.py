"""合成线性适配器——契约示例兼 golden 夹具:y[s] = 3·fa[s] + 1·fb[s] + 0·fc[s],
缺省特征全 1。真实项目把 predict 换成 FastAPI/本地模型调用,接口不变
(契约见 chartbook/_recipe-spec.md §6)。"""
import pandas as pd

CAPABILITIES = {"perturb_features": True, "perturb_lookback": False,
                "torch_module": False, "lookback_steps": 0,
                "features": ["fa", "fb", "fc"]}
COEF = {"fa": 3.0, "fb": 1.0, "fc": 0.0}
HORIZON = 6


def predict(requests):
    rows = []
    for r in requests:
        ov = r.get("feature_overrides") or {}
        for s in range(HORIZON):
            y = sum(c * (ov[f][s] if f in ov else 1.0)
                    for f, c in COEF.items())
            rows.append({"unit_id": r["unit_id"], "window_ts": r["window_ts"],
                         "horizon_step": s, "y_pred": y})
    return pd.DataFrame(rows)
