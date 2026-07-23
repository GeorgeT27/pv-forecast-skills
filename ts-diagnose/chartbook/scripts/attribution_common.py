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


def background_set(feats, k: int = 5, seed: int = 0):
    """背景集:窗口级特征向量 kmeans 后每簇取 medoid(离质心最近的真实窗),
    背景序列 = 代表窗逐步均值。meta 必须随归因 JSON 落盘(守卫一)。"""
    import pandas as pd
    vec = (feats.groupby(["unit_id", "window_ts", "feature"])["f_pred"].mean()
           .unstack("feature").dropna())
    if len(vec) < 1:
        raise ValueError("features 表无完整窗口,无法建背景集")
    k = min(k, len(vec))
    if k < len(vec):
        from sklearn.cluster import KMeans
        km = KMeans(n_clusters=k, n_init=10, random_state=seed).fit(vec.values)
        idx = []
        for ci in range(k):
            members = np.where(km.labels_ == ci)[0]
            d = np.linalg.norm(
                vec.values[members] - km.cluster_centers_[ci], axis=1)
            idx.append(int(members[int(np.argmin(d))]))
    else:
        idx = list(range(len(vec)))
    chosen = [vec.index[i] for i in idx]
    sub = feats.set_index(["unit_id", "window_ts"]).loc[chosen].reset_index()
    series = {}
    for fname, g in sub.groupby("feature"):
        series[str(fname)] = [round(float(v), 6) for v in
                              g.groupby("horizon_step")["f_pred"].mean()
                              .sort_index()]
    meta = {"method": "kmeans-medoid", "k": int(k), "seed": int(seed),
            "windows": [f"{u}|{w}" for u, w in chosen]}
    return series, meta


def feature_corr_groups(feats, threshold: float = 0.8):
    """|ρ|≥threshold 的特征并查集成组(窗口级均值向量口径)——强相关特征
    独立扰动会造分布外样本,归因必须按组呈现/置换(守卫二)。"""
    vec = (feats.groupby(["unit_id", "window_ts", "feature"])["f_pred"].mean()
           .unstack("feature").dropna())
    names = list(vec.columns)
    parent = {n: n for n in names}

    def find(a):
        while parent[a] != a:
            parent[a] = parent[parent[a]]
            a = parent[a]
        return a

    corr = vec.corr().abs()
    for i, a in enumerate(names):
        for b in names[i + 1:]:
            c = corr.loc[a, b]
            if np.isfinite(c) and c >= threshold:
                parent[find(a)] = find(b)
    groups = {}
    for n in names:
        groups.setdefault(find(n), []).append(n)
    return sorted(sorted(g) for g in groups.values())
