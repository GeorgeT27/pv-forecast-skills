"""模型归因公共件:适配器加载/能力校验、调用预算与请求哈希缓存;
(Task 2 增补:背景集选择、特征相关分组。)契约见 _recipe-spec §6。"""
from __future__ import annotations

import hashlib
import importlib.util
import json
from pathlib import Path

import numpy as np

REQUIRED_CAPS = ("perturb_features", "perturb_lookback", "torch_module")


class BudgetExceeded(RuntimeError):
    """窗口预测调用超 --max-calls 预算;调用方截断并如实记 coverage。"""


def load_adapter(path):
    p = Path(path)
    if not p.exists():
        raise ValueError(f"适配器不存在: {path}(契约见 chartbook/_recipe-spec.md §6)")
    spec = importlib.util.spec_from_file_location("predict_adapter", p)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    caps = getattr(mod, "CAPABILITIES", None)
    if not isinstance(caps, dict) or not all(k in caps for k in REQUIRED_CAPS):
        raise ValueError(f"适配器缺 CAPABILITIES 或缺键 {REQUIRED_CAPS}(§6)")
    if not callable(getattr(mod, "predict", None)):
        raise ValueError("适配器缺 predict(requests) 函数(§6)")
    if caps["perturb_lookback"] and not int(caps.get("lookback_steps") or 0):
        raise ValueError("perturb_lookback=True 时 CAPABILITIES 必须给 lookback_steps")
    if caps["torch_module"] and not callable(getattr(mod, "get_model", None)):
        raise ValueError("torch_module=True 时适配器必须实现 get_model()(§6)")
    return mod


class BudgetedAdapter:
    """包住 adapter.predict:计窗口预测次数、超预算抛 BudgetExceeded、
    按请求哈希缓存到 jsonl(重跑不重打 API)。"""

    def __init__(self, adapter, max_calls: int = 5000, cache_path=None):
        self.adapter, self.max_calls, self.calls = adapter, max_calls, 0
        self.cache_path = Path(cache_path) if cache_path else None
        self._cache = {}
        if self.cache_path and self.cache_path.exists():
            for line in self.cache_path.read_text().splitlines():
                rec = json.loads(line)
                self._cache[rec["key"]] = rec["y_pred"]

    @staticmethod
    def _key(req) -> str:
        return hashlib.sha1(
            json.dumps(req, sort_keys=True, default=str).encode()).hexdigest()

    def predict(self, requests):
        keys = [self._key(r) for r in requests]
        miss = [(k, r) for k, r in zip(keys, requests) if k not in self._cache]
        if miss:
            if self.calls + len(miss) > self.max_calls:
                raise BudgetExceeded(
                    f"窗口预测调用将超预算 {self.max_calls}(已用 {self.calls},"
                    f"本批需 {len(miss)})")
            self.calls += len(miss)
            df = self.adapter.predict([r for _k, r in miss])
            if "request_idx" not in df.columns:
                raise ValueError(
                    "适配器返回缺 request_idx 列——同批同窗不同扰动的请求无法"
                    "区分(契约见 _recipe-spec §6)")
            for j, (k, _r) in enumerate(miss):
                sub = df[df["request_idx"] == j]
                self._cache[k] = [float(v) for v in
                                  sub.sort_values("horizon_step")["y_pred"]]
                if self.cache_path:
                    with self.cache_path.open("a") as f:
                        f.write(json.dumps(
                            {"key": k, "y_pred": self._cache[k]}) + "\n")
        return [np.array(self._cache[k]) for k in keys]
