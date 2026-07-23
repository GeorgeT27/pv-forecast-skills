"""合成 lookback 适配器(golden):历史窗全 1(L=8),y[s]=10+hist[-1]——
只依赖最近一步;lookback_mask 区间内历史置 0。契约见 _recipe-spec §6。"""
import pandas as pd

CAPABILITIES = {"perturb_features": False, "perturb_lookback": True,
                "torch_module": False, "lookback_steps": 8, "features": []}
HORIZON = 4


def predict(requests):
    rows = []
    for i, r in enumerate(requests):
        hist = [1.0] * 8
        for a, b in (r.get("lookback_mask") or []):
            for j in range(max(0, int(a)), min(8, int(b))):
                hist[j] = 0.0
        y = 10.0 + hist[-1]
        for s in range(HORIZON):
            rows.append({"request_idx": i, "unit_id": r["unit_id"],
                         "window_ts": r["window_ts"],
                         "horizon_step": s, "y_pred": y})
    return pd.DataFrame(rows)
