# Chartbook 扩展 Plan 3/4:模型归因层(adapter 契约 + attribution_common + 3 图)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** chartbook 新增模型归因层——predict_adapter 契约、attribution_common 公共件(背景集/预算/缓存/相关分组)、三张归因图(global-attribution / lookback-decay / local-waterfall),chartbook 25→28 recipe,六类 category 全部有图。

**Architecture:** spec 见 `docs/superpowers/specs/2026-07-23-chartbook-expansion-design.md` §3-§4。核心决策:①预写脚本不碰用户模型,只认运行时薄适配器(`--adapter` 传路径,契约=CAPABILITIES+predict(requests));②Shapley 走 shap 库 `KernelExplainer` 的**二元 mask 玩家设计**(玩家=特征,mask=1 用实际序列、=0 用背景序列;D≤8 时 nsamples=2^D 全枚举=精确无随机);③golden 用合成线性适配器,线性模型 Shapley 解析可知、精确回收;④梯度白盒路(torch_module 能力 + GradientExplainer)为可选加速,golden 用微型 torch 线性模型(环境已有 torch 2.2.2,实跑;无 torch 环境 skipif)。

**Tech Stack:** shap **0.44.1**(本机已装并冒烟通过;注意:环境 numpy 必须保持 1.26.4——曾因 pip 拽升 numpy 2.x 弄坏 pandas,已回滚。任何实施者**禁止**升级 numpy/pandas)。torch 2.2.2(仅 Task 6 用)。其余同 Plan 2。

## Global Constraints

- 仓库根:`/Users/tqa946816/Documents/华为/光伏预测/结果分析skill`;分支 main;untracked 目录(docs/skill解析、gate_reports、row-diagnostic/demo_out)不得 add
- **禁止改动 numpy/pandas/sklearn 版本**;shap 缺失时脚本报错并给安装指引(`pip install shap==0.44.1`),不静默降级
- recipe frontmatter:category 一律 `attribution`;needs_materials 含 `serving_api`;领域名词闸已扩到全 frontmatter(conform CI)
- 归因 JSON 必含:`background_meta`(来源/k/seed/窗口清单)、`coverage`(windows_evaluated/calls_used/truncated)、所用 explainer 与种子——复现性硬规则(spec §3 守卫一)
- 预算:`--max-calls` 默认 5000(单位=窗口预测次数),超限截断并如实记 coverage,不静默;结果按请求哈希缓存(jsonl),重跑不重打
- 每 task:TDD 先红后绿 → `python3 -m pytest ts-diagnose/chartbook/tests/ -q` 全绿 0 warnings → commit(尾行 `Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>`)
- KernelExplainer 调用统一 `silent=True`;D≤8 用 `nsamples=2**D`(全枚举,决定论);D>8 用 `nsamples=2*D+64` 且先 `np.random.seed(seed)`(种子落 JSON)
- 已知风险:shap 0.44 的 `shap_values` 可能发 l1_reg deprecation 警告污染测试输出——若出现,给 shap_values 显式传 `l1_reg=0.0`(全枚举无需正则)消音并在报告注明;shap/torch 的其他警告如实报告交评审判级,不许静默吞

---

### Task 1: adapter 契约 + 合成线性适配器 + 加载校验

**Files:**
- Modify: `ts-diagnose/chartbook/_recipe-spec.md`(新增 §6 适配器契约)
- Create: `ts-diagnose/chartbook/golden/example_predict_adapter/predict_adapter.py`
- Create: `ts-diagnose/chartbook/scripts/attribution_common.py`(本任务只含 load_adapter + BudgetedAdapter)
- Test: `ts-diagnose/chartbook/tests/test_attribution_common.py`

**Interfaces:**
- Produces: `attribution_common.load_adapter(path) -> module`(校验 CAPABILITIES/predict/get_model);`attribution_common.BudgetedAdapter(adapter, max_calls, cache_path).predict(requests) -> list[np.ndarray]`(计数+缓存+BudgetExceeded);合成线性适配器(COEF={"fa":3,"fb":1,"fc":0}, HORIZON=6, 缺省特征全 1)——Task 3/5 golden 复用。

- [ ] **Step 1: _recipe-spec.md 加 §6(文件末尾追加)**

```markdown

## 6. 模型访问契约(predict adapter;attribution 类图专用)

attribution 类图(needs_materials 含 serving_api)不碰用户模型,只认运行时
薄适配器 `analysis_scripts/predict_adapter.py`(与 §1 的 adapter.py 同款纪律:
现场唯一要写的代码;golden 模板在 `golden/example_predict_adapter/`):

```python
CAPABILITIES = {
    "perturb_features": True,    # 支持特征替换(global-attribution/local-waterfall 需要)
    "perturb_lookback": False,   # 支持历史窗遮蔽(lookback-decay 需要)
    "torch_module": False,       # True 时须实现 get_model()(梯度白盒加速路)
    "lookback_steps": 0,         # perturb_lookback=True 时必填:历史窗长度(步)
    "features": ["..."],         # 可扰动特征名全集
}

def predict(requests):
    """requests: list[dict]——unit_id, window_ts,
       feature_overrides: {特征名: list[float] 长=horizon} | 缺省用模型自己的输入,
       lookback_mask: list[[start,end]] 半开步区间(0=最旧) | 缺省不遮蔽。
    返回 DataFrame: unit_id | window_ts | horizon_step | y_pred。"""

def get_model():
    """torch_module=True 时实现:返回 (torch_model, background_X, explain_X,
    feature_names)——model 输入 (N,D) tensor、输出 (N,B);GradientExplainer 用。"""
```

用户给 FastAPI 就在 predict 里打 API,给本地模型就本地推理——预写脚本无感。
能力不满足的图由选择门如实标注不可画。归因脚本经 attribution_common 的
BudgetedAdapter 调用:预算上限(--max-calls,超限截断记 coverage)+ 请求哈希
缓存(jsonl,重跑不重打)。背景集定义与所用 explainer/种子必须落盘进归因
JSON(background_meta)——换背景集=换归因基线。
```

- [ ] **Step 2: 写测试(先跑红)**

`tests/test_attribution_common.py`:

```python
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
```

Run: `python3 -m pytest ts-diagnose/chartbook/tests/test_attribution_common.py -q`
Expected: FAIL(ModuleNotFoundError: attribution_common)

- [ ] **Step 3: 写合成线性适配器**

`golden/example_predict_adapter/predict_adapter.py`:

```python
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
```

- [ ] **Step 4: 写 attribution_common(本任务部分)**

`scripts/attribution_common.py`:

```python
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
            for k, r in miss:
                sub = df[(df["unit_id"].astype(str) == str(r["unit_id"])) &
                         (df["window_ts"].astype(str) == str(r["window_ts"]))]
                self._cache[k] = [float(v) for v in
                                  sub.sort_values("horizon_step")["y_pred"]]
                if self.cache_path:
                    with self.cache_path.open("a") as f:
                        f.write(json.dumps(
                            {"key": k, "y_pred": self._cache[k]}) + "\n")
        return [np.array(self._cache[k]) for k in keys]
```

- [ ] **Step 5: 跑绿 + 全量 + Commit**

Run: `python3 -m pytest ts-diagnose/chartbook/tests/test_attribution_common.py -q` → 3 passed;全量 chartbook → 全绿。

```bash
git add ts-diagnose/chartbook/_recipe-spec.md ts-diagnose/chartbook/golden/example_predict_adapter/predict_adapter.py ts-diagnose/chartbook/scripts/attribution_common.py ts-diagnose/chartbook/tests/test_attribution_common.py
git commit -m "feat(ts-diagnose): 归因层地基——predict_adapter 契约(§6)+合成线性适配器+加载校验+预算缓存

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```

---

### Task 2: attribution_common 增补——背景集选择 + 特征相关分组

**Files:**
- Modify: `ts-diagnose/chartbook/scripts/attribution_common.py`(末尾追加两函数)
- Modify: `ts-diagnose/chartbook/tests/test_attribution_common.py`(末尾追加测试)

**Interfaces:**
- Produces: `background_set(feats_df, k=5, seed=0) -> (series: {feature: list[float]}, meta: dict)`(kmeans-medoid 代表窗,背景序列=代表窗均值,meta 含 method/k/seed/windows);`feature_corr_groups(feats_df, threshold=0.8) -> list[list[str]]`(|ρ|≥阈值成组,组内排序、组间按首元素排序)。

- [ ] **Step 1: 加测试(先跑红)**

```python
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
```

Run → FAIL(AttributeError: background_set)。

- [ ] **Step 2: 实现两函数(attribution_common.py 末尾追加)**

```python
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
```

- [ ] **Step 3: 跑绿 + 全量 + Commit**

```bash
git add ts-diagnose/chartbook/scripts/attribution_common.py ts-diagnose/chartbook/tests/test_attribution_common.py
git commit -m "feat(ts-diagnose): attribution_common 增补背景集(kmeans-medoid+meta 落盘)与特征相关分组(守卫一/二)

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```

---

### Task 3: global-attribution(全局特征贡献 + 特征×horizon 热力图)

**Files:**
- Create: `ts-diagnose/chartbook/recipes/global-attribution.md`
- Create: `ts-diagnose/chartbook/scripts/chart_global_attribution.py`
- Test: `ts-diagnose/chartbook/tests/test_chart_global_attribution.py`

**Interfaces:**
- Consumes: attribution_common(load_adapter/BudgetedAdapter/background_set/feature_corr_groups)、chart_common、shap
- Produces: recipe id `global-attribution`(category attribution)

- [ ] **Step 1: 写 recipe**

```markdown
---
id: global-attribution
category: attribution
needs_materials: [predict, truth, features, serving_api]
适用问题: 哪些输入特征对模型输出贡献最大?哪些只影响短期、哪些拖累远端 horizon?
outputs:
  json: global-attribution.json
  png: global-attribution.png
json_schema: >
  ranking(按 mean|SHAP| 降序的特征列表)、overall{特征: mean|SHAP|}、
  by_bucket(桶×特征矩阵,桶=horizon 等分)、bucket_defs、corr_groups
  (|ρ|≥0.8 特征组,组内归因需合并判读)、background_meta、explainer、seed、
  coverage{windows_evaluated, calls_used, truncated}。
bridge_hooks: >
  某特征 by_bucket 远端桶贡献占比高 → 该输入主导长程预测,其质量恶化优先
  拖累远端(与 horizon-degradation 晚段斜率交叉);corr_groups 内多特征
  分摊贡献 → 按组解读,勿点名单个;贡献极低的特征 → 冗余输入候选,
  剔除验证走 feature-importance playbook 的消融线。
验证步: 线性适配器 y=3fa+1fb+0fc、双簇背景 → overall 比值 3:1、fc≈0 精确回收;预算截断 coverage 如实(tests/test_chart_global_attribution.py)
---

# global-attribution:全局 Shapley 贡献与 horizon 分辨

## 适用问题
"模型主要在用哪些输入"的量化答案:玩家=特征,mask=0 用背景序列、=1 用
实际序列,KernelSHAP 分解每个 horizon 桶的输出。

## CLI 与参数
```bash
python3 chartbook/scripts/chart_global_attribution.py \
  --pred predictions.parquet --features features.parquet \
  --adapter analysis_scripts/predict_adapter.py \
  --out-dir <workdir>/charts [--buckets 4] [--max-windows 30] \
  [--background-k 5] [--seed 0] [--max-calls 5000]
```
适配器需 perturb_features=True;shap 缺失时报错并提示 `pip install shap==0.44.1`。

## JSON schema
见 frontmatter;D≤8 全枚举(精确、零随机),D>8 采样(seed 落盘);
评估窗为 features∩predict 的完整窗采样(--max-windows,seed 同源)。

## 判读
- ranking 首位与末位差一个量级以上 → 输入重要性高度集中,末位是冗余候选;
- by_bucket 某特征远端桶份额显著高于近端 → 长程依赖该输入,与
  horizon-degradation/lookback-decay 交叉;
- corr_groups 非平凡组存在时,组内特征的贡献必须合并判读(相关特征分摊);
- coverage.truncated=true 时只下"已评估窗口内"的结论,不外推。
只给候选假设;结论回 playbook 三道门。

## 验证步
线性适配器(3/1/0)+ 8 窗双簇特征(0/1 各半,背景 k=2 → medoid 均值 0.5)
→ 每窗贡献 = coef×(x−0.5),overall 比值 fa/fb=3、fc≈0 精确回收;
by_bucket 每桶与 overall 同比值;max_calls 压小 → truncated=true 且
windows_evaluated < 全量,不抛崩。
```

- [ ] **Step 2: 写 golden 测试(先跑红)**

```python
"""global-attribution golden:线性适配器 3:1:0 精确回收;预算截断如实。"""
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

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
```

Run → FAIL(ModuleNotFoundError: chart_global_attribution)。

- [ ] **Step 3: 写脚本**

```python
"""global-attribution:玩家=特征的 KernelSHAP 全局贡献(mask=0 背景序列/
=1 实际序列)+ 特征×horizon 桶热力图。需 shap(pip install shap==0.44.1)。"""
from __future__ import annotations

import argparse

import numpy as np
import pandas as pd

import attribution_common as ac
import chart_common as cc

RECIPE_ID = "global-attribution"

try:
    import shap
except ImportError as e:  # pragma: no cover
    raise ImportError(
        "global-attribution 需要 shap:pip install shap==0.44.1") from e


def _bucket_edges(horizon: int, buckets: int):
    edges = np.linspace(0, horizon, buckets + 1).round().astype(int)
    return [(int(a), int(b)) for a, b in zip(edges[:-1], edges[1:]) if b > a]


def _window_series(feats, unit, wts):
    g = feats[(feats["unit_id"] == unit) & (feats["window_ts"] == wts)]
    return {str(fn): gg.sort_values("horizon_step")["f_pred"].tolist()
            for fn, gg in g.groupby("feature")}


def compute(pred_df, feats, adapter, buckets: int = 4, max_windows: int = 30,
            background_k: int = 5, seed: int = 0, max_calls: int = 5000,
            cache_path=None) -> dict:
    if not adapter.CAPABILITIES.get("perturb_features"):
        raise ValueError("适配器 perturb_features=False,本图不可画(§6)")
    background, bg_meta = ac.background_set(feats, k=background_k, seed=seed)
    names = sorted(background)
    D = len(names)
    horizon = len(background[names[0]])
    bks = _bucket_edges(horizon, buckets)
    fw = (feats.groupby(["unit_id", "window_ts"]).size().index)
    pw = set(zip(pred_df["unit_id"].astype(str),
                 pred_df["window_ts"].astype(str)))
    cand = [(u, w) for (u, w) in fw if (str(u), str(w)) in pw]
    rng = np.random.RandomState(seed)
    if len(cand) > max_windows:
        cand = [cand[i] for i in sorted(
            rng.choice(len(cand), max_windows, replace=False))]
    ba = ac.BudgetedAdapter(adapter, max_calls=max_calls,
                            cache_path=cache_path)
    nsamples = 2 ** D if D <= 8 else 2 * D + 64
    np.random.seed(seed)
    acc = np.zeros((len(bks), D))
    done, truncated = 0, False
    for unit, wts in cand:
        actual = _window_series(feats, unit, wts)

        def f(masks):
            reqs = []
            for m in masks:
                ov = {fn: (actual[fn] if m[j] >= 0.5 else background[fn])
                      for j, fn in enumerate(names)}
                reqs.append({"unit_id": unit, "window_ts": wts,
                             "feature_overrides": ov})
            preds = ba.predict(reqs)
            return np.array([[float(np.mean(p[a:b])) for (a, b) in bks]
                             for p in preds])

        try:
            ex = shap.KernelExplainer(f, np.zeros((1, D)))
            sv = ex.shap_values(np.ones((1, D)), nsamples=nsamples,
                                silent=True)
        except ac.BudgetExceeded:
            truncated = True
            break
        acc += np.abs(np.array([np.asarray(s).ravel() for s in sv]))
        done += 1
    if done == 0:
        raise ValueError("预算不足以评估任何一个窗口——调大 --max-calls")
    acc /= done
    overall = {n: round(float(acc[:, j].mean()), 6)
               for j, n in enumerate(names)}
    return {"recipe": RECIPE_ID,
            "ranking": sorted(names, key=lambda n: -overall[n]),
            "overall": overall,
            "by_bucket": [{n: round(float(acc[bi, j]), 6)
                           for j, n in enumerate(names)}
                          for bi in range(len(bks))],
            "bucket_defs": [list(b) for b in bks],
            "corr_groups": ac.feature_corr_groups(feats),
            "background_meta": bg_meta, "explainer": "kernel",
            "seed": seed, "nsamples": nsamples,
            "coverage": {"windows_evaluated": done,
                         "calls_used": ba.calls, "truncated": truncated},
            "note": "mask=0 背景序列/=1 实际序列;D≤8 全枚举精确;"
                    "corr_groups 组内贡献须合并判读(守卫二)。"}


def render(stats: dict):
    import matplotlib.pyplot as plt
    cc.setup_font()
    names = stats["ranking"]
    fig, axes = plt.subplots(1, 2, figsize=(11, 4))
    axes[0].barh(range(len(names)),
                 [stats["overall"][n] for n in names])
    axes[0].set_yticks(range(len(names)))
    axes[0].set_yticklabels(names, fontsize=8)
    axes[0].invert_yaxis()
    axes[0].set_xlabel("mean|SHAP|")
    axes[0].set_title("全局贡献排名")
    mat = np.array([[row[n] for n in names] for row in stats["by_bucket"]])
    im = axes[1].imshow(mat.T, aspect="auto", cmap="viridis")
    axes[1].set_yticks(range(len(names)))
    axes[1].set_yticklabels(names, fontsize=8)
    axes[1].set_xticks(range(len(stats["bucket_defs"])))
    axes[1].set_xticklabels([f"{a}-{b}" for a, b in stats["bucket_defs"]],
                            fontsize=8)
    axes[1].set_xlabel("horizon 桶")
    axes[1].set_title("特征×horizon 贡献")
    fig.colorbar(im, ax=axes[1], shrink=0.8)
    fig.suptitle(f"global-attribution ({stats['explainer']})")
    return fig


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--pred", required=True)
    ap.add_argument("--features", required=True)
    ap.add_argument("--adapter", required=True)
    ap.add_argument("--out-dir", required=True)
    ap.add_argument("--buckets", type=int, default=4)
    ap.add_argument("--max-windows", type=int, default=30)
    ap.add_argument("--background-k", type=int, default=5)
    ap.add_argument("--seed", type=int, default=0)
    ap.add_argument("--max-calls", type=int, default=5000)
    a = ap.parse_args(argv)
    from pathlib import Path
    stats = compute(cc.load_predictions(a.pred), cc.load_features(a.features),
                    ac.load_adapter(a.adapter), buckets=a.buckets,
                    max_windows=a.max_windows, background_k=a.background_k,
                    seed=a.seed, max_calls=a.max_calls,
                    cache_path=Path(a.out_dir) / "attribution_cache.jsonl")
    cc.save_outputs(render(stats), a.out_dir, RECIPE_ID, stats)


if __name__ == "__main__":
    main()
```

- [ ] **Step 4: 跑绿 + 全量 + Commit**

commit message:`feat(ts-diagnose): chartbook 新图 global-attribution——KernelSHAP 全局贡献+特征×horizon 热力图(线性 3:1:0 精确回收 golden+预算截断守卫)`(带 Co-Authored-By 尾行)

---

### Task 4: lookback-decay(历史依赖衰减)

**Files:**
- Create: `ts-diagnose/chartbook/golden/example_lookback_adapter/predict_adapter.py`
- Create: `ts-diagnose/chartbook/recipes/lookback-decay.md`
- Create: `ts-diagnose/chartbook/scripts/chart_lookback_decay.py`
- Test: `ts-diagnose/chartbook/tests/test_chart_lookback_decay.py`

**Interfaces:**
- Consumes: attribution_common、chart_common
- Produces: recipe id `lookback-decay`(category attribution);合成 lookback 适配器(L=8,只读最近一步:y[s]=10+hist[-1],mask 区间置 0,HORIZON=4)

- [ ] **Step 1: 写合成 lookback 适配器**

`golden/example_lookback_adapter/predict_adapter.py`:

```python
"""合成 lookback 适配器(golden):历史窗全 1(L=8),y[s]=10+hist[-1]——
只依赖最近一步;lookback_mask 区间内历史置 0。契约见 _recipe-spec §6。"""
import pandas as pd

CAPABILITIES = {"perturb_features": False, "perturb_lookback": True,
                "torch_module": False, "lookback_steps": 8, "features": []}
HORIZON = 4


def predict(requests):
    rows = []
    for r in requests:
        hist = [1.0] * 8
        for a, b in (r.get("lookback_mask") or []):
            for i in range(max(0, int(a)), min(8, int(b))):
                hist[i] = 0.0
        y = 10.0 + hist[-1]
        for s in range(HORIZON):
            rows.append({"unit_id": r["unit_id"], "window_ts": r["window_ts"],
                         "horizon_step": s, "y_pred": y})
    return pd.DataFrame(rows)
```

- [ ] **Step 2: 写 recipe**

```markdown
---
id: lookback-decay
category: attribution
needs_materials: [predict, truth, serving_api]
适用问题: 模型依赖多长的历史?短期记忆还是长期记忆?
outputs:
  json: lookback-decay.json
  png: lookback-decay.png
json_schema: >
  lookback_steps、bucket_defs(步区间,近→远)、delta_by_bucket(遮蔽该桶后
  预测相对未遮蔽的 RMSE 变化)、weights(Δ⁺ 归一,全零时 null)、
  short_term_share(近期桶权重和;近期=1 主周期内,无周期给近四分之一)、
  per_instance{hist,median}(可选:逐窗有效历史步数)、coverage、seed。
bridge_hooks: >
  weights 集中最近桶 → 短记忆模型:远端 horizon 退化时优先查输入质量而非
  历史长度;远桶权重可观 → 长程依赖:训练数据的久远分布漂移会伤它
  (与 train-test-drift 交叉);全桶 Δ≈0 → 模型几乎不用历史(用协变量),
  与 global-attribution 互证。
验证步: 只读最近一步的合成适配器 → 最近桶 weight=1、其余 0、per-instance 中位数 1;无 lookback 能力适配器抛 ValueError(tests/test_chart_lookback_decay.py)
---

# lookback-decay:按桶遮蔽的历史依赖衰减

## 适用问题
"模型的记忆有多长"——按窗遮蔽(整桶置基线)比逐点便宜一个量级;
Δ 相对**未遮蔽预测**度量(纯依赖度量,与真值无关)。

## CLI 与参数
```bash
python3 chartbook/scripts/chart_lookback_decay.py \
  --pred predictions.parquet --adapter analysis_scripts/predict_adapter.py \
  --out-dir <workdir>/charts [--period-steps N] [--max-windows 30] \
  [--seed 0] [--max-calls 5000] [--per-instance]
```
适配器需 perturb_lookback=True(否则 ValueError,选择门如实标注)。

## JSON schema
见 frontmatter;桶从最近向最远:[最近 1 步] [近四分位] [至主周期(或半窗)]
[更远],由 lookback_steps 与 --period-steps 推出,def 落 JSON。

## 判读
- weights 集中最近桶且曲线陡衰减 → 短记忆——**这在 Transformer 系是文献
  常态,平坦/短依赖 ≠ 模型差**,勿据此单独下负面结论;
- per_instance 分布双峰 → 部分样本依赖长历史,可与 bad-window-clustering
  的坏窗簇交叉(某簇是否都在长依赖侧);
- 全桶 Δ≈0 → 历史几乎不被使用,转 global-attribution 看协变量侧。
只给候选假设;结论回 playbook 三道门。

## 验证步
只读最近一步的适配器(L=8)→ 遮最近桶 Δ=1、其余桶 Δ=0 → weights=[1,0,0,0]、
short_term_share=1;--per-instance 全窗 h*=1;线性(无 lookback)适配器抛 ValueError。
```

- [ ] **Step 3: 写 golden 测试(先跑红)**

```python
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
```

Run → FAIL。

- [ ] **Step 4: 写脚本**

```python
"""lookback-decay:按桶遮蔽历史窗,Δ=遮蔽后预测相对未遮蔽的 RMSE——
模型依赖多长的历史。Δ 与真值无关(纯依赖度量)。"""
from __future__ import annotations

import argparse

import numpy as np
import pandas as pd

import attribution_common as ac
import chart_common as cc

RECIPE_ID = "lookback-decay"


def _buckets(L: int, period_steps=None):
    """近→远:[L-1,L) 最近一步、近四分位、至主周期(缺省半窗)、更远。"""
    cuts = {L, L - 1, L - 1 - max(1, L // 4),
            L - period_steps if period_steps else L // 2, 0}
    edges = sorted((c for c in cuts if 0 <= c <= L), reverse=True)
    return [(b, a) for a, b in zip(edges[:-1], edges[1:]) if a > b]


def _delta(base, masked):
    return float(np.sqrt(np.mean(
        (np.concatenate(masked) - np.concatenate(base)) ** 2)))


def compute(pred_df, adapter, period_steps=None, max_windows: int = 30,
            seed: int = 0, max_calls: int = 5000, per_instance: bool = False,
            cache_path=None) -> dict:
    caps = adapter.CAPABILITIES
    if not caps.get("perturb_lookback"):
        raise ValueError("适配器 perturb_lookback=False,本图不可画(§6)")
    L = int(caps["lookback_steps"])
    bks = _buckets(L, period_steps)
    wins = (pred_df[["unit_id", "window_ts"]].drop_duplicates()
            .itertuples(index=False))
    cand = [(str(u), w) for u, w in wins]
    rng = np.random.RandomState(seed)
    if len(cand) > max_windows:
        cand = [cand[i] for i in sorted(
            rng.choice(len(cand), max_windows, replace=False))]
    ba = ac.BudgetedAdapter(adapter, max_calls=max_calls,
                            cache_path=cache_path)
    out = {"recipe": RECIPE_ID, "lookback_steps": L,
           "bucket_defs": [list(b) for b in bks], "seed": seed,
           "note": "Δ=遮蔽该桶后预测相对未遮蔽预测的 RMSE(纯依赖度量);"
                   "weights=Δ⁺ 归一;短记忆是 Transformer 系文献常态,"
                   "平坦≠模型差。"}
    truncated = False
    try:
        base = ba.predict([{"unit_id": u, "window_ts": w} for u, w in cand])
        deltas = []
        for a, b in bks:
            masked = ba.predict([{"unit_id": u, "window_ts": w,
                                  "lookback_mask": [[a, b]]}
                                 for u, w in cand])
            deltas.append(round(_delta(base, masked), 6))
        out["delta_by_bucket"] = deltas
        tot = sum(d for d in deltas if d > 0)
        out["weights"] = ([round(max(d, 0.0) / tot, 4) for d in deltas]
                          if tot > 1e-12 else None)
        cutoff = L - (period_steps if period_steps else max(1, L // 4))
        out["short_term_share"] = (
            round(sum(w for (a, _b), w in zip(bks, out["weights"])
                      if a >= cutoff), 4) if out["weights"] else None)
        if per_instance:
            hs = []
            for i, (u, w) in enumerate(cand):
                ref = float(np.sqrt(np.mean(
                    (ba.predict([{"unit_id": u, "window_ts": w,
                                  "lookback_mask": [[0, L]]}])[0]
                     - base[i]) ** 2)))
                if ref < 1e-12:
                    hs.append(0)
                    continue
                h_star = L
                for h in range(1, L + 1):
                    d = float(np.sqrt(np.mean(
                        (ba.predict([{"unit_id": u, "window_ts": w,
                                      "lookback_mask": [[0, L - h]]}])[0]
                         - base[i]) ** 2)))
                    if d <= 0.05 * ref:
                        h_star = h
                        break
                hs.append(h_star)
            vals, counts = np.unique(hs, return_counts=True)
            out["per_instance"] = {
                "hist": {str(int(v)): int(c) for v, c in zip(vals, counts)},
                "median": int(np.median(hs))}
    except ac.BudgetExceeded:
        truncated = True
    out["coverage"] = {"windows_evaluated": len(cand),
                       "calls_used": ba.calls, "truncated": truncated}
    if truncated and "delta_by_bucket" not in out:
        raise ValueError("预算不足以完成任何桶——调大 --max-calls")
    return out


def render(stats: dict):
    import matplotlib.pyplot as plt
    cc.setup_font()
    fig, ax = plt.subplots(figsize=(7, 4))
    labels = [f"[{a},{b})" for a, b in stats["bucket_defs"]]
    ax.bar(range(len(labels)), stats["delta_by_bucket"])
    ax.set_xticks(range(len(labels)))
    ax.set_xticklabels(labels, fontsize=8)
    ax.set_xlabel("遮蔽的历史步区间(左=近)")
    ax.set_ylabel("Δ RMSE(相对未遮蔽)")
    st = stats.get("short_term_share")
    ax.set_title(f"lookback-decay 历史依赖(short_term_share={st})")
    return fig


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--pred", required=True)
    ap.add_argument("--adapter", required=True)
    ap.add_argument("--out-dir", required=True)
    ap.add_argument("--period-steps", type=int, default=None)
    ap.add_argument("--max-windows", type=int, default=30)
    ap.add_argument("--seed", type=int, default=0)
    ap.add_argument("--max-calls", type=int, default=5000)
    ap.add_argument("--per-instance", action="store_true")
    a = ap.parse_args(argv)
    from pathlib import Path
    stats = compute(cc.load_predictions(a.pred), ac.load_adapter(a.adapter),
                    period_steps=a.period_steps, max_windows=a.max_windows,
                    seed=a.seed, max_calls=a.max_calls,
                    per_instance=a.per_instance,
                    cache_path=Path(a.out_dir) / "attribution_cache.jsonl")
    cc.save_outputs(render(stats), a.out_dir, RECIPE_ID, stats)


if __name__ == "__main__":
    main()
```

- [ ] **Step 5: 跑绿 + 全量 + Commit**

commit message:`feat(ts-diagnose): chartbook 新图 lookback-decay——按桶遮蔽历史依赖衰减+逐窗有效历史(只读最近步适配器 golden)`(带 Co-Authored-By 尾行)

---

### Task 5: local-waterfall(worst-K 局部归因瀑布)

**Files:**
- Create: `ts-diagnose/chartbook/recipes/local-waterfall.md`
- Create: `ts-diagnose/chartbook/scripts/chart_local_waterfall.py`
- Test: `ts-diagnose/chartbook/tests/test_chart_local_waterfall.py`

**Interfaces:**
- Consumes: attribution_common、chart_common、shap、合成线性适配器(Task 1)
- Produces: recipe id `local-waterfall`(category attribution)

- [ ] **Step 1: 写 recipe**

```markdown
---
id: local-waterfall
category: attribution
needs_materials: [predict, truth, features, serving_api]
适用问题: 误差最大的那几行,分别是哪些输入特征贡献的?各占多少?
outputs:
  json: local-waterfall.json
  png: local-waterfall.png
json_schema: >
  每行(worst-K):unit/window/rmse_actual、base_value(全参考输入时的行
  RMSE)、contributions{特征: Shapley 贡献}、check_sum(base+Σφ,应≈实际
  RMSE——效率性自检)、basis{特征: f_true|background}。顶层:k、
  background_meta(basis=background 时)、explainer、seed、coverage。
bridge_hooks: >
  多数坏行由同一特征主导 → 该输入系统性拖累,与 good-bad-contrast 的
  分离度、feature-error-conditional 的耦合比值三线互证后才升假设;
  各行主导特征不同 → 无单一元凶,回 bad-window-clustering 看失败模式分簇;
  φ 大但该特征 f_true 缺 → basis=background 的贡献解释要降级(背景不是真值)。
验证步: 线性适配器+固定偏差植入 → φ 解析精确回收(6/1/0),零系数大偏差诱饵 φ=0 不被冤枉;check_sum 效率性闭合(tests/test_chart_local_waterfall.py)
---

# local-waterfall:单行 Shapley 瀑布

## 适用问题
"这行为什么这么差"的量化拆账:mask=1 用实际输入(f_pred),=0 用参考输入
(f_true,缺则背景序列),Shapley 分解行 RMSE。

## CLI 与参数
```bash
python3 chartbook/scripts/chart_local_waterfall.py \
  --pred predictions.parquet --features features.parquet \
  --adapter analysis_scripts/predict_adapter.py \
  --out-dir <workdir>/charts [--k 20] [--model auto] \
  [--background-k 5] [--seed 0] [--max-calls 5000]
```
适配器需 perturb_features=True;D≤8 全枚举精确。

## JSON schema
见 frontmatter;worst-K 按焦点模型行 RMSE 降序;PNG 取前 ≤6 行画瀑布网格。

## 判读
- 单特征 φ 占 check_sum 的 ≥60% → 该行的主导元凶候选——但**单行=样本量 1**,
  点名须与全局线(good-bad-contrast / feature-error-conditional)交叉;
- φ 为负的特征 → 该输入实际在"救"这行(替换成参考反而更差),不是元凶;
- check_sum 与 rmse_actual 偏差 >5% → 强交互效应存在,单特征拆账要谨慎
  (JSON 如实给出,不隐藏)。
只给候选假设;结论回 playbook 三道门。

## 验证步
线性适配器(3/1/0)+ 特征偏差植入(fa 偏 2、fb 偏 1、fc 偏 5 但系数 0)→
同号常量偏差下可加:φ_a=6、φ_b=1、φ_c=0 精确回收;fc 是"大偏差但无影响"
的防冤枉诱饵;base_value=0、check_sum=7 闭合。
```

- [ ] **Step 2: 写 golden 测试(先跑红)**

```python
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
```

Run → FAIL。

- [ ] **Step 3: 写脚本**

```python
"""local-waterfall:worst-K 行的单行 Shapley 拆账(mask=1 实际输入/=0 参考
输入,参考=f_true 缺则背景)。需 shap(pip install shap==0.44.1)。"""
from __future__ import annotations

import argparse

import numpy as np
import pandas as pd

import attribution_common as ac
import chart_common as cc

RECIPE_ID = "local-waterfall"

try:
    import shap
except ImportError as e:  # pragma: no cover
    raise ImportError(
        "local-waterfall 需要 shap:pip install shap==0.44.1") from e


def compute(pred_df, feats, adapter, k: int = 20, model=None, seed: int = 0,
            max_calls: int = 5000, background_k: int = 5,
            cache_path=None) -> dict:
    if not adapter.CAPABILITIES.get("perturb_features"):
        raise ValueError("适配器 perturb_features=False,本图不可画(§6)")
    models = sorted(pred_df["model"].unique())
    focal = model or models[0]
    if focal not in models:
        raise ValueError(f"焦点模型 '{focal}' 不在数据中:{models}")
    rr = cc.row_rmse(pred_df[pred_df["model"] == focal])
    worst = rr.sort_values("rmse").tail(k).iloc[::-1]
    fq = feats.copy()
    has_true_by_f = (fq.groupby("feature")["f_true"]
                     .apply(lambda s: s.notna().any()).to_dict())
    need_bg = not all(has_true_by_f.values())
    background, bg_meta = (ac.background_set(feats, k=background_k, seed=seed)
                           if need_bg else ({}, None))
    ba = ac.BudgetedAdapter(adapter, max_calls=max_calls,
                            cache_path=cache_path)
    truth = pred_df[pred_df["model"] == focal].set_index(
        ["unit_id", "window_ts"])
    rows_out, truncated = [], False
    np.random.seed(seed)
    for _, wrow in worst.iterrows():
        unit, wts = wrow["unit_id"], wrow["window_ts"]
        g = feats[(feats["unit_id"] == unit) & (feats["window_ts"] == wts)]
        actual, ref, basis = {}, {}, {}
        for fn, gg in g.groupby("feature"):
            gg = gg.sort_values("horizon_step")
            actual[str(fn)] = gg["f_pred"].tolist()
            if has_true_by_f.get(fn):
                ref[str(fn)] = gg["f_true"].tolist()
                basis[str(fn)] = "f_true"
            else:
                ref[str(fn)] = background[str(fn)]
                basis[str(fn)] = "background"
        names = sorted(actual)
        D = len(names)
        y_true = (truth.loc[(unit, wts)].sort_values("horizon_step")
                  ["y_true"].values)

        def f(masks):
            reqs = []
            for m in masks:
                ov = {fn: (actual[fn] if m[j] >= 0.5 else ref[fn])
                      for j, fn in enumerate(names)}
                reqs.append({"unit_id": unit, "window_ts": wts,
                             "feature_overrides": ov})
            preds = ba.predict(reqs)
            return np.array([[float(np.sqrt(np.mean((p - y_true) ** 2)))]
                             for p in preds])

        nsamples = 2 ** D if D <= 8 else 2 * D + 64
        try:
            ex = shap.KernelExplainer(f, np.zeros((1, D)))
            sv = np.asarray(ex.shap_values(np.ones((1, D)),
                                           nsamples=nsamples,
                                           silent=True)).ravel()
            base_value = float(np.asarray(ex.expected_value).ravel()[0])
        except ac.BudgetExceeded:
            truncated = True
            break
        contrib = {n: round(float(sv[j]), 6) for j, n in enumerate(names)}
        rows_out.append({
            "unit_id": str(unit), "window_ts": str(wts),
            "rmse_actual": round(float(wrow["rmse"]), 6),
            "base_value": round(base_value, 6),
            "contributions": contrib,
            "check_sum": round(base_value + float(sv.sum()), 6),
            "basis": basis})
    if not rows_out:
        raise ValueError("预算不足以拆任何一行——调大 --max-calls")
    return {"recipe": RECIPE_ID, "k": k, "model": str(focal),
            "rows": rows_out, "background_meta": bg_meta,
            "explainer": "kernel", "seed": seed,
            "coverage": {"rows_evaluated": len(rows_out),
                         "calls_used": ba.calls, "truncated": truncated},
            "note": "mask=1 实际输入/=0 参考输入(f_true 缺则背景);"
                    "check_sum=base+Σφ 应≈rmse_actual(效率性自检);"
                    "单行=样本量 1,点名须与全局线交叉。"}


def render(stats: dict):
    import matplotlib.pyplot as plt
    cc.setup_font()
    rows = stats["rows"][:6]
    n = len(rows)
    fig, axes = plt.subplots(1, n, figsize=(4 * n, 3.5), squeeze=False)
    for ax, row in zip(axes[0], rows):
        names = sorted(row["contributions"],
                       key=lambda x: -abs(row["contributions"][x]))
        cum = row["base_value"]
        for i, fn in enumerate(names):
            v = row["contributions"][fn]
            ax.bar(i, v, bottom=cum, color="#c0504d" if v >= 0 else "#4f81bd")
            cum += v
        ax.axhline(row["rmse_actual"], color="k", lw=0.6, ls="--")
        ax.set_xticks(range(len(names)))
        ax.set_xticklabels(names, fontsize=7, rotation=45)
        ax.set_title(f"{row['window_ts'][:10]} rmse={row['rmse_actual']:.2f}",
                     fontsize=8)
    fig.suptitle(f"local-waterfall worst-{stats['k']}({stats['model']})")
    return fig


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--pred", required=True)
    ap.add_argument("--features", required=True)
    ap.add_argument("--adapter", required=True)
    ap.add_argument("--out-dir", required=True)
    ap.add_argument("--k", type=int, default=20)
    ap.add_argument("--model", default=None)
    ap.add_argument("--background-k", type=int, default=5)
    ap.add_argument("--seed", type=int, default=0)
    ap.add_argument("--max-calls", type=int, default=5000)
    a = ap.parse_args(argv)
    from pathlib import Path
    stats = compute(cc.load_predictions(a.pred), cc.load_features(a.features),
                    ac.load_adapter(a.adapter), k=a.k, model=a.model,
                    seed=a.seed, max_calls=a.max_calls,
                    background_k=a.background_k,
                    cache_path=Path(a.out_dir) / "attribution_cache.jsonl")
    cc.save_outputs(render(stats), a.out_dir, RECIPE_ID, stats)


if __name__ == "__main__":
    main()
```

- [ ] **Step 4: 跑绿 + 全量 + Commit**

commit message:`feat(ts-diagnose): chartbook 新图 local-waterfall——worst-K 单行 Shapley 拆账(φ 解析精确回收+防冤枉诱饵 golden)`(带 Co-Authored-By 尾行)

---

### Task 6: 梯度白盒路(torch_module)+ CHANGELOG 收口

**Files:**
- Modify: `ts-diagnose/chartbook/scripts/attribution_common.py`(加 gradient_mean_shap)
- Modify: `ts-diagnose/chartbook/scripts/chart_global_attribution.py`(加 --explainer auto|kernel|gradient)
- Modify: `ts-diagnose/chartbook/tests/test_chart_global_attribution.py`(加梯度路 golden)
- Modify: `ts-diagnose/CHANGELOG.md`(Plan 3 条目)

**Interfaces:**
- Produces: `attribution_common.gradient_mean_shap(adapter) -> (matrix(B,D), feature_names, meta)`;global-attribution `--explainer auto`(torch_module→gradient,否则 kernel),两路同 JSON schema。

- [ ] **Step 1: 加梯度路测试(先跑红)**

`test_chart_global_attribution.py` 末尾追加:

```python
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
    for r in requests:
        ov = r.get("feature_overrides") or {}
        x = torch.tensor([[float(ov.get(f, [1.0] * 2)[0])
                           for f in ("fa", "fb", "fc")]])
        y = _model(x).detach().numpy().ravel()
        for s, v in enumerate(y):
            rows.append({"unit_id": r["unit_id"], "window_ts": r["window_ts"],
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
```

Run → FAIL(compute 无 explainer 参数)。

- [ ] **Step 2: attribution_common 加 gradient_mean_shap**

```python
def gradient_mean_shap(adapter):
    """白盒路:GradientExplainer(期望梯度)。adapter.get_model() 返回
    (torch_model, background_X, explain_X, feature_names);输出维=horizon 桶。
    返回 (mean|SHAP| 矩阵 (B,D), feature_names, meta)。"""
    import shap
    model, background, explain, names = adapter.get_model()
    ex = shap.GradientExplainer(model, background)
    sv = ex.shap_values(explain)
    if not isinstance(sv, list):
        sv = [sv]
    mat = np.array([np.abs(np.asarray(s)).mean(axis=0) for s in sv])
    meta = {"method": "gradient-explainer",
            "n_background": int(len(background)),
            "n_explain": int(len(explain))}
    return mat, [str(n) for n in names], meta
```

- [ ] **Step 3: chart_global_attribution 接 --explainer**

compute 签名加 `explainer: str = "auto"`;函数体开头(perturb_features 校验之后)插入:

```python
    if explainer == "auto":
        explainer = ("gradient" if adapter.CAPABILITIES.get("torch_module")
                     else "kernel")
    if explainer == "gradient":
        mat, names, bg_meta = ac.gradient_mean_shap(adapter)
        overall = {n: round(float(mat[:, j].mean()), 6)
                   for j, n in enumerate(names)}
        return {"recipe": RECIPE_ID,
                "ranking": sorted(names, key=lambda n: -overall[n]),
                "overall": overall,
                "by_bucket": [{n: round(float(mat[bi, j]), 6)
                               for j, n in enumerate(names)}
                              for bi in range(mat.shape[0])],
                "bucket_defs": [[i, i + 1] for i in range(mat.shape[0])],
                "corr_groups": ac.feature_corr_groups(feats),
                "background_meta": bg_meta, "explainer": "gradient",
                "seed": seed, "nsamples": None,
                "coverage": {"windows_evaluated": bg_meta["n_explain"],
                             "calls_used": 0, "truncated": False},
                "note": "白盒期望梯度路:输出维=get_model 的桶;"
                        "corr_groups 组内贡献须合并判读(守卫二)。"}
```

main() 加 `ap.add_argument("--explainer", default="auto", choices=["auto", "kernel", "gradient"])` 并传入 compute。既有 kernel golden 不受影响(线性适配器 torch_module=False → auto 落 kernel)。

- [ ] **Step 4: CHANGELOG 条目(文件末尾按现有格式追加)**

```markdown

## 2026-07-23 chartbook 扩展第三轮:模型归因层

- predict_adapter 契约进 _recipe-spec §6(CAPABILITIES+predict(requests)+get_model 白盒路);合成线性/lookback 双 golden 适配器
- attribution_common:加载校验、BudgetedAdapter(预算+请求哈希 jsonl 缓存)、background_set(kmeans-medoid,meta 落盘=守卫一)、feature_corr_groups(守卫二)
- 三图:global-attribution(KernelSHAP 双面板,梯度白盒路 --explainer auto)、lookback-decay(按桶遮蔽+逐窗有效历史)、local-waterfall(单行 φ 解析回收+防冤枉诱饵)
- chartbook 25→28 recipe,attribution 类首次有图,六类全满;依赖新增 shap==0.44.1(numpy 必须保持 1.26.4)
```

- [ ] **Step 5: 跑绿 + 全量 + Commit**

Run: `python3 -m pytest ts-diagnose/ -q` 全绿 0 warnings。

```bash
git add ts-diagnose/chartbook/scripts/attribution_common.py ts-diagnose/chartbook/scripts/chart_global_attribution.py ts-diagnose/chartbook/tests/test_chart_global_attribution.py ts-diagnose/CHANGELOG.md
git commit -m "feat(ts-diagnose): 归因梯度白盒路(GradientExplainer,--explainer auto)+CHANGELOG 第三轮收口

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```

---

## 后续(本文件不含)

- **Plan 4/4**:orient 选择门按类分组呈现 + build_index.py(INDEX.md 只索引实际产物)+ true-vs-pred-scatter 加 Mincer-Zarnowitz + engine-core.md 同步 + 总 CHANGELOG 收口。
