# pv-feature-blame ε_sys/ε_res 分解 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 在 pv-feature-blame 里插入 Stage 1.5（稳健加性回归剥系统偏差 ε_sys），Stage 2 点名只对波动 ε_res 做并加可约性闸，golden 埋三个新诱饵验证，Stage 4 反事实加 residual 模式。

**Architecture:** ε = pred − label 逐点误差 → Huber 岭加性回归（cyclic 钟点/DoY + 提前期 hinge + 全部配对特征 pred 值 hinge）拟合条件均值 = ε_sys 候选 → 跨期稳定性收缩 λ（前段拟合/后段验证，embargo 48h）→ ε_res = ε − λ·拟合值 → Stage 2 的 z/Spearman/共线全在 ε_res 上算，外加 lag-1 自相关可约性闸。回归只减条件均值不碰条件方差——波动的异方差结构必须原样留在 ε_res（golden 断言钉住）。

**Tech Stack:** Python 3.11、numpy/pandas（scipy 可选）、pytest、ts-diagnose gen_gate（金标准闸）。

**Spec:** `docs/superpowers/specs/2026-07-17-pv-feature-blame-epsilon-decomp-design.md`（已 commit 3fcbcdd）。

## Global Constraints

- 口径常量一律 `import` 自 `pv-result-analysis/scripts/data_utils.py`（`FREQ`/`HORIZON`/`ULTRA_SHORT_IDX`/`SHORT_SLICE`/`LABEL_COL`），绝不本地重定义。
- 作用域：ε/分解/点名/反事实**只对 `feature_pairs.json` 里配对的预报特征**；未配对列（真实值/mystery 列）绝不进任何环节（实现层按 pairs 过滤即天然满足，golden 断言钉住）。
- 自由度上限：钟点谐波 ≤3 阶、DoY 谐波 ≤2 阶、每条 hinge 样条 df = 1+4 knots = 5 ≤ 6。
- 保守方向：拟合失败/样本不足/后段为空 → λ=0 = **不剥**（宁少剥不过剥）。
- golden 必须确定性零随机（解析式函数，真值列纯 f(物理时间 t)，滚动窗一致性天然成立；埋点按物理时间埋不按行埋）。
- 改任何 `scripts/*.py` 后必须重过 gen_gate（`test_blame_golden.py` 参数化覆盖）才算完成。
- 脚本 print ≤30 行摘要；产物落盘 JSON/CSV/npy 自足。
- gen_gate 静态检查禁 subprocess/网络/绝对路径写——新脚本同样受限。
- 每 task 结束 `git commit`，消息尾行 `Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>`。
- 仓库根：`/Users/tqa946816/Documents/华为/光伏预测/结果分析skill`（下文 `<REPO>`）；技能目录 `<REPO>/pv-feature-blame`（下文 `<SKILL>`）。全部命令在 `<REPO>` 下执行。

## 金标准期望值冻结约定（贯穿 Task 3–5、8）

本仓库 golden 的惯例（manifest.json note 原文）："期望值来自 scripts/ 本体在金标准上的实跑并留容差"。流程固定为：
1. 先写**定性必真断言清单**（例：f_sys_bias 必不点名、f_res_culprit 必点名、f_irreducible 必被闸挡）；
2. 跑参考实现取实际值；
3. **逐条核对定性清单成立**（不成立 = 埋点或实现有 bug，回去修，不许改清单迁就）；
4. 把实际值加宽容差写进 manifest（数值断言用 between/ge/le，不锁死脆弱小数）。

---

## File Structure

| 文件 | 动作 | 职责 |
|---|---|---|
| `<SKILL>/scripts/fb_common.py` | 改 | +5 个分解构件函数 + `eps_matrices()` 共用误差矩阵 + config 文档 `decompose` 块 |
| `<SKILL>/scripts/feature_decompose.py` | **新** | Stage 1.5 CLI：回归→λ→ε_res→可约性，产 `eps_res_*.npy` + `feature_decomp.json` |
| `<SKILL>/scripts/test_decompose.py` | **新** | 构件单测 + 合成小样端到端（植入回收：乘性偏差被剥、波动保全） |
| `<SKILL>/scripts/feature_blame.py` | 改 | 误差源换 ε_res、可约性闸、三栏报告、summary 新键 |
| `<SKILL>/scripts/run_orient.py` | 改 | Stage 2 前置加 feature_decomp.json、扫描/提示 |
| `<SKILL>/scripts/cf_logic.py` | 改 | +`residual_replacement()` + selfcheck 新检查 |
| `<SKILL>/scripts/counterfactual_api.py` | 改 | residual 模式（边际/minimal/lattice 层换 ε_res，oracle 仍整换） |
| `<SKILL>/scripts/test_blame_golden.py` | 改 | STAGES 加 `("decomp", "feature_decompose.py")`；BAD_BLAME 更新为新 schema |
| `<SKILL>/golden/make_golden.py` | 改 | +f_sys_bias/f_res_culprit/f_irreducible + pred_M4res；f_jumpy_true 振幅 5→25 |
| `<SKILL>/golden/manifest.json` | 改 | +stage "decomp"；stage 0/1/2/4 期望更新 |
| `<SKILL>/golden/*`（parquet/CSV/json/npy） | 重生成 | 三 parquet + feature_pairs + bad_rows 全套 + eps_res_*.npy + feature_decomp.json |
| `<SKILL>/references/blame-methods.md` | 改 | +「ε_sys/ε_res 分解与可约性」节 |
| `<SKILL>/references/blame-discipline.md` | 改 | +反驳门⑨系统偏差门、⑩可约性门（现有已到⑧，接续编号） |
| `<SKILL>/SKILL.md` | 改 | 阶段表+首要框定+常见错误 |
| `<SKILL>/CHANGELOG.md` | 改 | v3 记录 |

**Stage 编号决策（spec 的实现偏差，已定）**：orient 的 `ALL_STAGES` 是整数元组，不插 1.5——分解作为 **Stage 2 的第一子步**实现（同 v2 的 feature_revision 模式：Stage 2 双产物 → 现在三产物）。概念上仍叫 Stage 1.5，文档如此表述。

**Interfaces 总览（跨 task 契约，签名以此为准）：**

```python
# fb_common.py 新增
def harmonic_basis(x, period, n_orders=3) -> np.ndarray            # (n, 2·n_orders)
def hinge_basis(x, n_knots=4) -> np.ndarray                        # (n, 1+n_knots)；常量列 → (n,1) 全零
def huber_ridge(X, y, alpha=1e-3, iters=10) -> np.ndarray | None   # 系数 p 维；样本不足 → None
def temporal_split(ts, embargo="48h") -> tuple[np.ndarray, np.ndarray]  # (front_idx, back_idx) 行号
def lag1_reducibility(E) -> float                                  # [0,1]
def eps_matrices(ft, pairs) -> dict[str, np.ndarray]               # {feature: (n_rows,192) pred−label}

# feature_decompose.py 产物
# eps_res_<sanitize(feature)>.npy   (n_rows, 192) float64，行序 = feature_true 行序
# feature_decomp.json：
# {"params": {...}, "n_rows": int, "n_features": int, "skipped_unpaired": [...],
#  "features": {feat: {"stability_lambda": float, "sys_frac": float, "var_raw": float,
#                      "var_res": float, "reducibility": float,
#                      "res_var_front": float, "res_var_back": float, "fit": "ok"|...}}}

# cf_logic.py 新增
def residual_replacement(pred, eps_res) -> np.ndarray              # pred − ε_res = label + ε_sys
```

---

### Task 1: fb_common 分解构件（基/稳健回归/时间切分/可约性/共用误差矩阵）

**Files:**
- Modify: `<SKILL>/scripts/fb_common.py`（末尾追加一节；docstring config 示例追加 `decompose` 块）
- Create: `<SKILL>/scripts/test_decompose.py`
- Modify: `<SKILL>/scripts/feature_blame.py:88-89`（err_mats 构造改调 `fb.eps_matrices`——DRY，行为不变）

**Interfaces:**
- Consumes: 现有 `fb.require_du()`、`d.to_matrix`。
- Produces: 上方 Interfaces 总览里 fb_common 的 6 个函数（Task 2/5 消费）。

- [ ] **Step 1: 写失败测试**

`<SKILL>/scripts/test_decompose.py`：

```python
"""ε 分解构件单测 + 合成小样端到端（Task 2 追加）。全部确定性零随机。"""
import os
import sys

import numpy as np
import pandas as pd
import pytest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import fb_common as fb  # noqa: E402


def test_harmonic_basis_wraps_midnight():
    b0 = fb.harmonic_basis(np.array([0.0]), 24.0, 3)
    b24 = fb.harmonic_basis(np.array([24.0]), 24.0, 3)
    assert b0.shape == (1, 6)
    assert np.allclose(b0, b24, atol=1e-9)          # cyclic：午夜无边界跳变


def test_hinge_basis_shape_and_constant_guard():
    x = np.linspace(-3, 7, 100)
    b = fb.hinge_basis(x, n_knots=4)
    assert b.shape == (100, 5)                       # df = 1 + 4 knots = 5 ≤ 6
    c = fb.hinge_basis(np.full(50, 3.0), n_knots=4)
    assert c.shape[0] == 50 and np.all(c == 0.0)     # 常量列：零基不装样子


def test_huber_ridge_recovers_slope_despite_outliers():
    x = np.linspace(0, 10, 400)
    y = 2.0 * x + 1.0
    y[::20] += 80.0                                  # 5% 确定性大离群
    X = np.column_stack([np.ones_like(x), x])
    coef = fb.huber_ridge(X, y)
    assert coef is not None
    assert abs(coef[1] - 2.0) < 0.1                  # 稳健：离群不拉歪斜率
    assert fb.huber_ridge(X[:5], y[:5]) is None      # 样本不足 → None（保守不剥）


def test_temporal_split_embargo():
    ts = pd.date_range("2025-01-01", periods=40, freq="6h")   # 跨 10 天
    front, back = fb.temporal_split(ts, embargo="48h")
    assert len(front) == 20
    cutoff = ts[front].max() + pd.Timedelta("48h")
    assert all(ts[i] >= cutoff for i in back)        # 后段与前段末行至少隔 48h
    assert len(back) > 0
    dense = pd.date_range("2025-01-01", periods=40, freq="15min")  # 只跨 10h
    _, back2 = fb.temporal_split(dense, embargo="48h")
    assert len(back2) == 0                           # 数据太短 → 后段空（调用方 λ=0）


def test_lag1_reducibility():
    n = np.arange(192)
    smooth = np.sin(2 * np.pi * n / 16.0)            # period-16：ρ1=cos(2π/16)≈0.92
    E = np.tile(smooth, (10, 1))
    assert fb.lag1_reducibility(E) > 0.5
    nyq = np.sin(np.pi * n / 2.0 + 0.7)              # period-4 近奈奎斯特：ρ1≈0
    assert fb.lag1_reducibility(np.tile(nyq, (10, 1))) < 0.05
    assert fb.lag1_reducibility(np.zeros((5, 192))) == 0.0   # 常量 → 0
```

- [ ] **Step 2: 跑测试确认失败**

Run: `python3 -m pytest pv-feature-blame/scripts/test_decompose.py -v`
Expected: 5 FAIL，`AttributeError: module 'fb_common' has no attribute 'harmonic_basis'`

- [ ] **Step 3: 实现——fb_common.py 末尾追加**

```python
# ---------------------------------------------------------------- ε 分解构件（Stage 1.5）
def harmonic_basis(x: np.ndarray, period: float, n_orders: int = 3) -> np.ndarray:
    """cyclic 谐波基 sin/cos(2πk·x/period)，k=1..n_orders → (n, 2·n_orders)。
    钟点/DoY 用它——天然处理午夜与跨年回绕，无分箱边界。"""
    x = np.asarray(x, float)
    cols = []
    for k in range(1, n_orders + 1):
        ang = 2.0 * np.pi * k * x / period
        cols += [np.sin(ang), np.cos(ang)]
    return np.column_stack(cols)


def hinge_basis(x: np.ndarray, n_knots: int = 4) -> np.ndarray:
    """线性 + 分位点 hinge 样条基，df = 1+n_knots ≤ 6（结构性防偷波动：低 df 曲面
    只装得下慢变偏置）。x 先稳健标准化（median/IQR）；常量列返回全零基。"""
    x = np.asarray(x, float)
    med = np.nanmedian(x)
    iqr = np.nanpercentile(x, 75) - np.nanpercentile(x, 25)
    if not np.isfinite(iqr) or iqr == 0:
        return np.zeros((len(x), 1))
    z = (x - med) / iqr
    knots = np.nanpercentile(z, np.linspace(20, 80, n_knots))
    return np.column_stack([z] + [np.maximum(0.0, z - q) for q in knots])


def huber_ridge(X: np.ndarray, y: np.ndarray, alpha: float = 1e-3,
                iters: int = 10):
    """Huber-IRLS + 岭（确定性）。返回系数；样本 < max(30, 2p) → None（保守不剥）。
    非有限行剔除后拟合；共线协变量靠岭稳住——只取拟合值不解释系数。"""
    X, y = np.asarray(X, float), np.asarray(y, float)
    m = np.isfinite(y) & np.all(np.isfinite(X), axis=1)
    Xm, ym = X[m], y[m]
    n, p = Xm.shape
    if n < max(30, 2 * p):
        return None
    w, coef, eye = np.ones(n), np.zeros(p), np.eye(p)
    for _ in range(iters):
        Xw = Xm * w[:, None]
        coef = np.linalg.solve(Xw.T @ Xm + alpha * n * eye, Xw.T @ ym)
        r = ym - Xm @ coef
        mad = np.median(np.abs(r - np.median(r)))
        delta = 1.345 * 1.4826 * mad
        if not np.isfinite(delta) or delta <= 0:
            break
        aw = np.abs(r)
        w = np.where(aw <= delta, 1.0, delta / np.maximum(aw, 1e-12))
    return coef


def temporal_split(ts, embargo: str = "48h"):
    """按时间中位切前/后段行号；后段起点 ≥ 前段末行 + embargo（重叠窗 192 步 = 48h，
    防泄漏）。返回 (front_idx, back_idx)；数据太短后段可为空——调用方 λ=0 保守不剥。"""
    ts = pd.DatetimeIndex(ts)
    order = np.argsort(ts.asi8)
    n = len(order)
    if n < 4:
        return order, np.array([], int)
    half = n // 2
    cutoff = ts[order[half - 1]] + pd.Timedelta(embargo)
    back = np.array([i for i in order[half:] if ts[i] >= cutoff], int)
    return order[:half], back


def lag1_reducibility(E: np.ndarray) -> float:
    """可约性 v1：逐行 lag-1 自相关的中位数，负值截 0 后平方（≈AR(1) 可解释方差占比）。
    白噪声/常量 → 0（上游拿它没辙，点名是废话）。v2 占位：相位/幅度/爬坡形状分解。"""
    rows = []
    for r in np.asarray(E, float):
        a, b = r[:-1], r[1:]
        m = np.isfinite(a) & np.isfinite(b)
        a, b = a[m], b[m]
        if len(a) < 8 or np.std(a) == 0 or np.std(b) == 0:
            continue
        c = np.corrcoef(a, b)[0, 1]
        if np.isfinite(c):
            rows.append(float(c))
    if not rows:
        return 0.0
    return round(max(0.0, float(np.median(rows))) ** 2, 4)


def eps_matrices(ft: pd.DataFrame, pairs: list) -> dict:
    """逐点特征误差矩阵 {feature: (n_rows,192) pred − label}。分解（Stage 1.5）与
    归因（Stage 2）共用同一定义——只对配对特征存在 ε，未配对列无 ε 无反事实。"""
    d = require_du()
    return {p["feature"]: d.to_matrix(ft, p["pred_col"]) - d.to_matrix(ft, p["label_col"])
            for p in pairs}
```

同时在 `fb_common.py` 头部 docstring 的 config 示例里（`"revision"` 块之后）加：

```
  "decompose": {"enabled": true,                # Stage 1.5：ε_sys/ε_res 分解（v3）
                "embargo": "48h",               # 前/后段稳定性切分的重叠窗隔离（=192 步）
                "max_orders_hod": 3, "max_orders_doy": 2, "n_knots": 4,   # df 上限
                "alpha": 1e-3, "fit_cap": 400000,   # 岭系数 / 拟合点数上限（等距抽样）
                "reducibility_min": 0.1},       # Stage 2 可约性闸：低于此不点名
```

- [ ] **Step 4: feature_blame.py 的 err_mats 改调共用函数（行为不变的重构）**

`feature_blame.py` 第 88-89 行：

```python
    err_mats = {p["feature"]: d.to_matrix(ft, p["pred_col"]) - d.to_matrix(ft, p["label_col"])
                for p in pairs}
```

改为：

```python
    err_mats = fb.eps_matrices(ft, pairs)
```

- [ ] **Step 5: 跑测试确认通过 + 现有金标准不回归**

Run: `python3 -m pytest pv-feature-blame/scripts/test_decompose.py pv-feature-blame/scripts/test_blame_golden.py -v`
Expected: test_decompose 5 PASS；test_blame_golden 全 PASS（重构未改行为）

- [ ] **Step 6: Commit**

```bash
git add pv-feature-blame/scripts/fb_common.py pv-feature-blame/scripts/test_decompose.py pv-feature-blame/scripts/feature_blame.py
git commit -m "feat(pv-feature-blame): ε 分解构件——谐波/hinge 基、Huber 岭、embargo 时间切分、lag-1 可约性、共用 eps_matrices"
```

---

### Task 2: feature_decompose.py（Stage 1.5 CLI）

**Files:**
- Create: `<SKILL>/scripts/feature_decompose.py`
- Modify: `<SKILL>/scripts/test_decompose.py`（追加端到端测试）

**Interfaces:**
- Consumes: Task 1 的 6 个 fb_common 函数；`fb.load_any`/`read_json`/`dump_json`/`sanitize`；`d.FREQ`/`d.HORIZON`。
- Produces: `eps_res_<sanitize(feat)>.npy` + `feature_decomp.json`（schema 见总览；Task 4 gate、Task 5 blame、Task 8 cf 消费）。

- [ ] **Step 1: 写失败测试（追加到 test_decompose.py）**

```python
def _mini_ft(tmp_path):
    """合成 feature_true：40 行、6h 间距（跨 10 天，前后段切得开）。
    f_mult：pred = 1.3·true（乘性系统偏差，own-pred 线性可剥）+ period-16 波动 w（必须保全）。"""
    rows = pd.date_range("2025-03-01", periods=40, freq="6h")
    H = 192
    FREQ = pd.Timedelta("15min")
    recs = []
    for T in rows:
        t = T + FREQ * np.arange(H)
        hod = t.hour + t.minute / 60.0
        true = 50.0 + 10.0 * np.sin(2 * np.pi * hod / 24.0)
        n = ((t - pd.Timestamp("2025-01-01")) / FREQ).astype(int)
        w = 5.0 * np.sin(2 * np.pi * n / 16.0)            # 波动：低 df 曲面装不下
        pred = 1.3 * true + w
        recs.append({"timestamp_win": T,
                     "f_mult_pred": pred.astype(np.float32),
                     "f_mult_true": true.astype(np.float32)})
    p = tmp_path / "ft.parquet"
    pd.DataFrame(recs).to_parquet(p, index=False)
    pairs = {"pairs": [{"feature": "f_mult", "pred_col": "f_mult_pred",
                        "label_col": "f_mult_true"}], "unmapped": ["aux_obs"]}
    import json
    (tmp_path / "feature_pairs.json").write_text(json.dumps(pairs), encoding="utf-8")
    return p


def test_decompose_end_to_end(tmp_path, monkeypatch):
    import json
    import subprocess
    ftp = _mini_ft(tmp_path)
    r = subprocess.run(
        [sys.executable, os.path.join(HERE, "feature_decompose.py"),
         "--feature-true", str(ftp), "--pairs", "feature_pairs.json"],
        cwd=tmp_path, capture_output=True, text=True)
    assert r.returncode == 0, r.stdout + r.stderr
    dec = json.load(open(tmp_path / "feature_decomp.json", encoding="utf-8"))
    f = dec["features"]["f_mult"]
    assert dec["n_rows"] == 40 and dec["n_features"] == 1
    assert "aux_obs" in dec["skipped_unpaired"]           # 作用域：未配对列绝不分解
    assert f["sys_frac"] >= 0.6                           # 乘性偏差被剥掉大头
    assert f["stability_lambda"] >= 0.5                   # 稳定关系 → λ 高
    assert f["reducibility"] >= 0.5                       # period-16 波动有结构
    res = np.load(tmp_path / "eps_res_f_mult.npy")
    assert res.shape == (40, 192)
    # 波动保全：ε_res 与植入的 w 高度相关（回归只减条件均值，不碰波动）
    rows = pd.date_range("2025-03-01", periods=40, freq="6h")
    FREQ = pd.Timedelta("15min")
    W = np.array([5.0 * np.sin(2 * np.pi *
                  (((T + FREQ * np.arange(192)) - pd.Timestamp("2025-01-01")) / FREQ)
                  .astype(int) / 16.0) for T in rows])
    cc = np.corrcoef(res.ravel(), W.ravel())[0, 1]
    assert cc >= 0.85
```

- [ ] **Step 2: 跑测试确认失败**

Run: `python3 -m pytest pv-feature-blame/scripts/test_decompose.py::test_decompose_end_to_end -v`
Expected: FAIL（feature_decompose.py 不存在，returncode ≠ 0）

- [ ] **Step 3: 实现 feature_decompose.py（完整文件）**

```python
#!/usr/bin/env python3
"""Stage 1.5：ε_sys/ε_res 分解——稳健加性回归剥系统偏差，只留波动给 Stage 2 点名。

方法（spec: docs/superpowers/specs/2026-07-17-pv-feature-blame-epsilon-decomp-design.md）：
  ε_f = pred − label（逐点；仅 feature_pairs.json 配对特征——未配对的真实值列无 ε）
  ε_sys_f ≈ Huber 岭 [1 | 谐波(钟点≤3阶) | 谐波(DoY≤2阶) | hinge(提前期) | hinge(X_pred_g) ∀g]
    ——不分箱：无稀疏格子、无人为边界、无 weather_class 标签依赖（天气型由各特征
    pred 值的样条隐式承载）；加性主效应成本随特征数线性。
  跨期稳定性：前段拟合 → 后段验证 λ = clip(⟨ε_b,ŝ_b⟩/⟨ŝ_b,ŝ_b⟩, 0, 1)；
    后段空/拟合失败 → λ=0（保守：宁少剥不过剥）。ε_res = ε − λ·ŝ。
  可约性 = 逐行 lag-1 自相关中位数²（Stage 2 闸用：< min 不点名，白噪声硬追是废话）。
  波动保全：回归只减条件均值不碰条件方差——res_var_front/back 落盘供检查。

用法（工作目录下，Stage 0 产物就位后）：
  python3 <SKILL>/scripts/feature_decompose.py \
      [--feature-true F.parquet] [--pairs feature_pairs.json] \
      [--embargo 48h] [--alpha 1e-3] [--fit-cap 400000] [--out feature_decomp.json]

产物：eps_res_<feature>.npy（n_rows×192，行序 = feature_true 行序）+ feature_decomp.json
"""
from __future__ import annotations

import argparse
import os
import sys

import numpy as np
import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import fb_common as fb  # noqa: E402


def build_design(ts_rows, pred_mats: dict, orders_hod: int, orders_doy: int,
                 n_knots: int) -> np.ndarray:
    """全部特征共用的设计矩阵 (n_rows·H, p)：截距 + 钟点/DoY 谐波 + 提前期 hinge
    + 每个配对特征的 pred 值 hinge（列序 = sorted(特征名)，确定性）。"""
    d = fb.require_du()
    H = d.HORIZON
    ts = pd.DatetimeIndex(ts_rows)
    k = np.arange(H)
    t_ns = ts.asi8[:, None] + (k * d.FREQ.value)[None, :]
    tt = pd.DatetimeIndex(t_ns.ravel())
    hod = tt.hour + tt.minute / 60.0
    doy = tt.dayofyear + hod / 24.0
    lead = np.tile(k.astype(float), len(ts))
    blocks = [np.ones((len(tt), 1)),
              fb.harmonic_basis(hod, 24.0, orders_hod),
              fb.harmonic_basis(doy, 365.25, orders_doy),
              fb.hinge_basis(lead, n_knots)]
    for g in sorted(pred_mats):
        blocks.append(fb.hinge_basis(pred_mats[g].ravel(), n_knots))
    return np.column_stack(blocks)


def point_mask(row_idx: np.ndarray, n_rows: int, H: int) -> np.ndarray:
    m = np.zeros(n_rows, bool)
    m[row_idx] = True
    return np.repeat(m, H)


def decompose_one(eps: np.ndarray, X: np.ndarray, fmask: np.ndarray,
                  bmask: np.ndarray, alpha: float, fit_cap: int):
    """单特征：前段拟合 → 后段 λ → ε_sys/ε_res。返回 (eps_res, meta)。"""
    y = eps.ravel()
    fidx = np.where(fmask)[0]
    if len(fidx) > fit_cap:                          # 等距抽样（确定性，无随机）
        fidx = fidx[:: max(1, len(fidx) // fit_cap)]
    coef = fb.huber_ridge(X[fidx], y[fidx], alpha=alpha)
    if coef is None:
        return eps.copy(), {"stability_lambda": 0.0, "fit": "insufficient_data"}
    s_hat = X @ coef
    yb, sb = y[bmask], s_hat[bmask]
    m = np.isfinite(yb) & np.isfinite(sb)
    lam = 0.0
    if m.sum() >= 100:
        denom = float(sb[m] @ sb[m])
        if denom > 0:
            lam = float(np.clip((yb[m] @ sb[m]) / denom, 0.0, 1.0))
    sys_flat = lam * np.where(np.isfinite(s_hat), s_hat, 0.0)   # 未知处不剥（保守）
    res = (y - sys_flat).reshape(eps.shape)
    return res, {"stability_lambda": round(lam, 4), "fit": "ok"}


def main():
    cfg = fb.config_or_empty()
    dcfg = cfg.get("decompose", {})
    ap = argparse.ArgumentParser()
    ap.add_argument("--feature-true", default=cfg.get("feature_true"))
    ap.add_argument("--pairs", default="feature_pairs.json")
    ap.add_argument("--embargo", default=dcfg.get("embargo", "48h"))
    ap.add_argument("--alpha", type=float, default=dcfg.get("alpha", 1e-3))
    ap.add_argument("--fit-cap", type=int, default=dcfg.get("fit_cap", 400000))
    ap.add_argument("--orders-hod", type=int, default=dcfg.get("max_orders_hod", 3))
    ap.add_argument("--orders-doy", type=int, default=dcfg.get("max_orders_doy", 2))
    ap.add_argument("--n-knots", type=int, default=dcfg.get("n_knots", 4))
    ap.add_argument("--out", default="feature_decomp.json")
    args = ap.parse_args()
    if not args.feature_true:
        raise SystemExit("缺 --feature-true（或先写 blame_config.json）。")

    d = fb.require_du()
    pj = fb.read_json(args.pairs) or {}
    pairs = pj.get("pairs") or []
    if not pairs:
        raise SystemExit(f"{args.pairs} 里没有特征对——先跑 Stage 0 probe_schema.py。")
    ft, _ = fb.load_any(args.feature_true)
    ts_rows = ft[d.TIMESTAMP_COL]
    n_rows, H = len(ft), d.HORIZON

    eps = fb.eps_matrices(ft, pairs)
    pred_mats = {p["feature"]: d.to_matrix(ft, p["pred_col"]) for p in pairs}
    X = build_design(ts_rows, pred_mats, args.orders_hod, args.orders_doy, args.n_knots)
    front, back = fb.temporal_split(ts_rows, embargo=args.embargo)
    fmask = point_mask(front, n_rows, H)
    bmask = point_mask(back, n_rows, H)
    frow = np.zeros(n_rows, bool); frow[front] = True

    feats, lines = {}, []
    for feat in sorted(eps):
        res, meta = decompose_one(eps[feat], X, fmask, bmask, args.alpha, args.fit_cap)
        np.save(f"eps_res_{fb.sanitize(feat)}.npy", res)
        var_raw = float(np.nanvar(eps[feat]))
        var_res = float(np.nanvar(res))
        meta.update({
            "var_raw": round(var_raw, 6), "var_res": round(var_res, 6),
            "sys_frac": round(max(0.0, 1.0 - var_res / var_raw), 4) if var_raw > 0 else 0.0,
            "reducibility": fb.lag1_reducibility(res),
            "res_var_front": round(float(np.nanvar(res[frow])), 6),
            "res_var_back": round(float(np.nanvar(res[~frow])), 6) if (~frow).any() else None,
        })
        feats[feat] = meta
        lines.append(f"  {feat:16s} λ={meta['stability_lambda']:.2f} sys_frac="
                     f"{meta['sys_frac']:.2f} 可约性={meta['reducibility']:.2f} [{meta['fit']}]")

    out = {"params": {"embargo": args.embargo, "alpha": args.alpha,
                      "orders_hod": args.orders_hod, "orders_doy": args.orders_doy,
                      "n_knots": args.n_knots, "fit_cap": args.fit_cap,
                      "n_front_rows": int(len(front)), "n_back_rows": int(len(back))},
           "n_rows": n_rows, "n_features": len(pairs),
           "skipped_unpaired": list(pj.get("unmapped") or []),
           "features": feats}
    fb.dump_json(args.out, out)

    print(f"[feature_decompose] 特征 ×{len(pairs)}  前段 {len(front)} 行 / 后段 {len(back)} 行"
          f"（embargo {args.embargo}；后段空 → λ=0 全部不剥）")
    for ln in lines[:20]:
        print(ln)
    print(f"  产物: eps_res_<feat>.npy ×{len(pairs)} + {args.out}")


if __name__ == "__main__":
    main()
```

- [ ] **Step 4: 跑测试确认通过**

Run: `python3 -m pytest pv-feature-blame/scripts/test_decompose.py -v`
Expected: 全 PASS（含 end_to_end：sys_frac≥0.6、λ≥0.5、波动相关≥0.85）。若 sys_frac 不达标先查 own-pred hinge 是否进了设计矩阵；若波动相关不达标 = 过剥，查 df 是否超上限。

- [ ] **Step 5: Commit**

```bash
git add pv-feature-blame/scripts/feature_decompose.py pv-feature-blame/scripts/test_decompose.py
git commit -m "feat(pv-feature-blame): Stage 1.5 feature_decompose——稳健加性回归剥 ε_sys，λ 稳定性收缩，ε_res+可约性落盘"
```

---

### Task 3: golden 新埋点（f_sys_bias / f_res_culprit / f_irreducible + pred_M4res）

**Files:**
- Modify: `<SKILL>/golden/make_golden.py`
- Regenerate: `<SKILL>/golden/golden_{test,predict,feature_true}.parquet`、`feature_pairs.json`、`bad_rows_summary.json`、`bad_rows_*.csv`（4 模型 × 3 口径 = 12 个）、`eps_res_*.npy` ×9、`feature_decomp.json`

**Interfaces:**
- Consumes: Task 2 的 feature_decompose.py。
- Produces: Task 4/5 的 golden 输入文件全套。

- [ ] **Step 1: make_golden.py 加埋点函数（在 `s_period4` 之后追加）**

```python
# ------------------------------------------------- ε 分解埋点（v3；全部纯 f(物理时间)）
def dayidx(t):
    return (t.normalize() - pd.Timestamp("2025-01-01")).days


def daytime(t):
    return max(0.0, math.sin(math.pi * (hour_of(t) - 6.0) / 12.0))


def f_sys_bias_true(t):                     # 幅度逐日增长：per-row 误差才有跨行排名信号
    return (20.0 + 4.0 * dayidx(t)) * daytime(t)
# pred = 1.3×true：乘性系统偏差（报得越高越偏高）。不进任何模型预测 =「模型已补偿」。
# 陷阱设计：raw 误差逐日增长、与 pred_M4res 行误差 raw-Spearman 高 → 旧逻辑必冤枉；
# own-pred 线性精确捕获 ε=0.3·true 且跨期稳定 → λ≈1、ε_res≈0 → 剥后必不点名。


def f_res_culprit_true(t):
    return 45.0 + 5.0 * math.sin(2 * math.pi * hour_of(t) / 24.0)


def w_culprit(t):                           # period-16（4h）波动：≤3 阶钟点谐波装不下
    n = int((t - EPOCH) / FREQ)
    return (4.0 + 1.5 * dayidx(t)) * math.sin(2 * math.pi * n / 16.0 + 0.5)
# ε_sys≈0、ε_res=w 驱动 pred_M4res → 必点名；lag-1=cos(2π/16)≈0.92 → 可约性高过闸。


def f_irreducible_true(t):
    return 35.0 + 5.0 * math.cos(2 * math.pi * hour_of(t) / 24.0)


def v_irred(t):                             # period-4 近奈奎斯特：lag-1=cos(π/2)=0 → 不可约
    n = int((t - EPOCH) / FREQ)
    return (6.0 + 2.0 * dayidx(t)) * math.sin(math.pi * n / 2.0 + 0.7)
# 也驱动 pred_M4res（z/ρ 双关都过）→ 唯一挡它的是可约性闸——证明闸有牙。
```

- [ ] **Step 2: f_jumpy_true 振幅 5→25**

```python
def f_jumpy_true(t):
    return 60.0 + 25.0 * math.sin(2 * math.pi * hour_of(t) / 24.0 + 2.0)
```

理由（写进该函数上方注释）：`ε_jumpy = s(T)·A(t)` 不变（跳变/churn/M3 行误差全不受扰）；但真值日变幅 25 使 pred 的 ±A 两支值域重叠——own-pred 样条无法按值分离 ε 符号，防止回归把翻新跳变误吸成 ε_sys（这是对"低 df + 值域重叠 → 偷不走波动"的真实性检验）。

- [ ] **Step 3: main() 循环里追加第三组特征与新模型列**

在 v2 翻新埋点 for 循环之后、`yy = series(y, T, H)` 之前插入：

```python
        for name, fn, wig in (("f_sys_bias", f_sys_bias_true, None),
                              ("f_res_culprit", f_res_culprit_true, w_culprit),
                              ("f_irreducible", f_irreducible_true, v_irred)):
            hist = series(fn, T, HIST, step0=-HIST)
            fut_true = series(fn, T, H)
            if wig is None:
                fut_pred = (1.3 * fut_true).astype(np.float32)      # 乘性系统偏差
            else:
                fut_pred = (fut_true + series(wig, T, H)).astype(np.float32)
            feat864[name] = np.concatenate([hist, fut_pred]).astype(np.float32)
            feat864["_ft"].update({f"{name}_pred": fut_pred, f"{name}_true": fut_true})
```

`pred.append({...})` 里加一列（f_sys_bias 故意不进——被补偿的偏差不影响模型）：

```python
                     "pred_M4res": (yy - 0.55 * series(w_culprit, T, H)
                                    - 0.45 * series(v_irred, T, H)).astype(np.float32),
```

- [ ] **Step 4: 重生成三 parquet**

Run: `python3 pv-feature-blame/golden/make_golden.py`
Expected: 三行"写出 ...parquet"，feature_true 列数 = 1 + 9×2 + 1(mystery_x) = 20。

- [ ] **Step 5: 重生成 Stage 0/1/1.5 中间产物并拷回 golden/**

```bash
cd "$(mktemp -d)" && G="<REPO>/pv-feature-blame/golden" && S="<REPO>/pv-feature-blame/scripts"
python3 "$S/probe_schema.py" --test "$G/golden_test.parquet" --predict "$G/golden_predict.parquet" --feature-true "$G/golden_feature_true.parquet"
python3 "$S/find_bad_rows.py" --test "$G/golden_test.parquet" --predict "$G/golden_predict.parquet" --metrics ultra_short,short,rmse_192
python3 "$S/feature_decompose.py" --feature-true "$G/golden_feature_true.parquet" --pairs feature_pairs.json
cp feature_pairs.json bad_rows_summary.json bad_rows_*.csv feature_decomp.json eps_res_*.npy "$G/"
```

Expected: probe 报 4 模型、9 特征对、mystery_x unmapped；find_bad_rows 12 组；decompose 9 特征。

- [ ] **Step 6: 定性清单核对（不成立=回去修，禁改清单）**

写一次性核对脚本跑（或交互确认 `feature_decomp.json` / `bad_rows_summary.json`）：

1. `f_sys_bias`: `sys_frac ≥ 0.85`、`stability_lambda ≥ 0.7`；
2. `f_res_culprit`: `sys_frac ≤ 0.3`、`reducibility ≥ 0.5`、`res_var_back > 2×res_var_front`（波动的逐日增长结构保全）；
3. `f_irreducible`: `reducibility ≤ 0.05`；
4. `f_blame`: `stability_lambda ≤ 0.3`（day2 一次性崩坏非稳定偏差 → 不剥）且其 ε_res≈raw；
5. `f_jumpy`: `sys_frac ≤ 0.4`（值域重叠防吸收生效）；
6. `skipped_unpaired` 含 `mystery_x`、`n_features == 9`；
7. `bad_rows_summary.json` 里 pred_M1/ensemble/M3 三模型的全部数值与旧版一致（新特征列/新模型不扰动旧模型行误差）；pred_M4res 的 rmse_192 worst_timestamp = day7 或 day8 的 09:00 行。

- [ ] **Step 7: Commit**

```bash
git add pv-feature-blame/golden/
git commit -m "feat(pv-feature-blame): golden v3 埋点——f_sys_bias(乘性稳偏必洗清)/f_res_culprit(波动必点名)/f_irreducible(白噪声必被闸)+pred_M4res；f_jumpy 真值幅 5→25 防 own-pred 吸收"
```

---

### Task 4: manifest 加 stage "decomp" + gate 接线

**Files:**
- Modify: `<SKILL>/golden/manifest.json`
- Modify: `<SKILL>/scripts/test_blame_golden.py:19-20`

**Interfaces:**
- Consumes: Task 3 的 golden 产物；ts-diagnose `gen_gate.py`（断言 DSL：eq/le/ge/between/contains/exists/argmax/first_is）。
- Produces: `("decomp", "feature_decompose.py")` 过闸能力（Task 5 依赖同机制）。

- [ ] **Step 1: manifest.json 更新——先改受 Task 3 影响的既有断言**

- `stages."0"`: `n_models` 3→4；`feature_names contains` 追加三条（f_sys_bias/f_res_culprit/f_irreducible）。
- `stages."1"`: 旧断言（M1/ensemble/M3）**原样保留**（Step 6-7 已验不变）；追加：

```json
        {"file": "bad_rows_summary.json", "path": "metrics.rmse_192.pred_M4res.n_rows", "op": "eq", "value": 40},
        {"file": "bad_rows_summary.json", "path": "metrics.rmse_192.pred_M4res.n_bad", "op": "between", "value": [1, 6]},
        {"file": "bad_rows_rmse_192_pred_M4res.csv", "op": "exists"}
```

- `stages."2"` 的 `inputs` 追加：`bad_rows_rmse_192_pred_M4res.csv`、`bad_rows_ultra_short_pred_M4res.csv`、`bad_rows_short_pred_M4res.csv`、`feature_decomp.json`、9 个 `eps_res_*.npy`（文件名用 `fb.sanitize` 后缀，如 `eps_res_f_sys_bias.npy`）。

- [ ] **Step 2: manifest.json 新增 stage "decomp"（放在 "1" 与 "2" 之间）**

```json
    "decomp": {
      "desc": "ε_sys/ε_res 分解：f_sys_bias 乘性稳偏被剥（sys_frac 高、λ 高）；f_res_culprit 波动保全（sys_frac 低、可约性高、后段方差>前段——异方差结构留在 ε_res）；f_irreducible 零结构（可约性≈0）；f_blame 一次性崩坏跨期不稳 → λ≈0 不剥；mystery_x 未配对绝不分解（作用域断言）",
      "inputs": ["golden_feature_true.parquet", "feature_pairs.json"],
      "args": ["--feature-true", "golden_feature_true.parquet", "--pairs", "feature_pairs.json"],
      "expect": [
        {"file": "feature_decomp.json", "path": "n_rows", "op": "eq", "value": 40},
        {"file": "feature_decomp.json", "path": "n_features", "op": "eq", "value": 9},
        {"file": "feature_decomp.json", "path": "skipped_unpaired", "op": "contains", "value": "mystery_x"},
        {"file": "feature_decomp.json", "path": "features.f_sys_bias.sys_frac", "op": "ge", "value": 0.85},
        {"file": "feature_decomp.json", "path": "features.f_sys_bias.stability_lambda", "op": "ge", "value": 0.7},
        {"file": "feature_decomp.json", "path": "features.f_res_culprit.sys_frac", "op": "le", "value": 0.3},
        {"file": "feature_decomp.json", "path": "features.f_res_culprit.reducibility", "op": "ge", "value": 0.5},
        {"file": "feature_decomp.json", "path": "features.f_irreducible.reducibility", "op": "le", "value": 0.05},
        {"file": "feature_decomp.json", "path": "features.f_blame.stability_lambda", "op": "le", "value": 0.3},
        {"file": "feature_decomp.json", "path": "features.f_jumpy.sys_frac", "op": "le", "value": 0.4},
        {"file": "eps_res_f_res_culprit.npy", "op": "exists"},
        {"file": "eps_res_f_sys_bias.npy", "op": "exists"}
      ]
    },
```

数值容差按 Task 3 Step 6 实测值校准（约定见「期望值冻结」节）；波动保全的 `res_var_back/res_var_front ≥ 2` 若 DSL 无除法运算，改为分别断言 `res_var_front le <实测上界>` + `res_var_back ge <实测下界>`（两界从实跑取，间隔 ≥2×）。

- [ ] **Step 3: test_blame_golden.py STAGES 加一行**

```python
STAGES = [("0", "probe_schema.py"), ("1", "find_bad_rows.py"),
          ("decomp", "feature_decompose.py"), ("2", "feature_blame.py"),
          ("revision", "feature_revision.py"), ("4", "cf_logic.py")]
```

- [ ] **Step 4: 跑 gate（此时 stage 2 仍是旧逻辑——manifest 的 stage 2 断言暂未加新键，应仍绿）**

Run: `python3 -m pytest pv-feature-blame/scripts/test_blame_golden.py -v`
Expected: stage 0/1/decomp/revision/4 PASS。stage 2 若因输入清单变化报错，检查 inputs 拼写；若因 f_jumpy×M3 断言 `global_spearman between [0.15,0.45]` 变化而 FAIL——此时 stage 2 还没接 ε_res，不应变，真变了说明 golden 数据改动扰动了旧路径，回 Task 3 查（最可能是 f_jumpy_true 振幅改动未按 Step 2 只动真值幅度）。

- [ ] **Step 5: Commit**

```bash
git add pv-feature-blame/golden/manifest.json pv-feature-blame/scripts/test_blame_golden.py
git commit -m "feat(pv-feature-blame): manifest 加 decomp 闸——sys_frac/λ/可约性/作用域/波动保全断言全过 gen_gate"
```

---

### Task 5: feature_blame.py 接 ε_res + 可约性闸 + 三栏报告

**Files:**
- Modify: `<SKILL>/scripts/feature_blame.py`
- Modify: `<SKILL>/golden/manifest.json`（stage 2 期望）
- Modify: `<SKILL>/scripts/test_blame_golden.py`（BAD_BLAME 新 schema）

**Interfaces:**
- Consumes: Task 2 产物（`feature_decomp.json` + `eps_res_*.npy`）；Task 1 `fb.eps_matrices`。
- Produces: `blame_report.csv` 新列 `feature_err_raw/feature_err_sys/reducibility_frac`；`blame_summary.json` 每特征新键 `sys_frac/stability_lambda/reducibility_frac/global_spearman_raw/feature_err_raw_mean`、顶层 `"decomp": "on"|"off"`（Task 7 文档、Task 8 引用）。

- [ ] **Step 1: 改 CLI 与误差源（main() 开头段）**

argparse 加两个参数：

```python
    dcfg = cfg.get("decompose", {})
    ap.add_argument("--use-residual", action=argparse.BooleanOptionalAction,
                    default=dcfg.get("enabled", True))
    ap.add_argument("--reducibility-min", type=float,
                    default=dcfg.get("reducibility_min", 0.1))
```

`err_mats = fb.eps_matrices(ft, pairs)` 之后插入：

```python
    raw_mats = err_mats
    decomp_meta, decomp_mode = {}, "off"
    if args.use_residual:
        dec = fb.read_json("feature_decomp.json")
        if not dec:
            print("  ⚠ 未找到 feature_decomp.json —— 回退原始 ε 点名（decomp=off；"
                  "spec 要求先跑 Stage 1.5 feature_decompose.py）")
        elif int(dec.get("n_rows", -1)) != len(ft):
            raise SystemExit("feature_decomp.json 行数与 feature_true 不符——分解产物过期，"
                             "先重跑 feature_decompose.py。")
        else:
            res_mats = {}
            for feat in raw_mats:
                p = f"eps_res_{fb.sanitize(feat)}.npy"
                if not os.path.exists(p):
                    raise SystemExit(f"缺 {p}——分解产物不全，先重跑 feature_decompose.py。")
                res_mats[feat] = np.load(p)
            err_mats, decomp_meta, decomp_mode = res_mats, dec.get("features", {}), "on"
```

- [ ] **Step 2: 可约性闸 + 三栏报告（坏行循环内）**

循环前加辅助（`fe_by_feature` 构造后）：

```python
            fe_raw = {feat: np.sqrt(np.nanmean(E[idx][:, sl] ** 2, axis=1))
                      for feat, E in raw_mats.items()}
            rho_raw = {feat: round(fb.spearman(rows["row_error"].to_numpy(), fe_raw[feat]), 4)
                       for feat in raw_mats}

            def red_frac(feat):
                if decomp_mode != "on":
                    return 1.0
                v = (decomp_meta.get(feat) or {}).get("reducibility")
                return float(v) if v is not None else 1.0
```

（`fe_by_feature`/`z_by_feature`/`rho` 保持现状——`err_mats` 已是 ε_res，z/Spearman/共线自动全在波动上。）

blamed 判定改为（原 4 条件 + 可约性）：

```python
                    reducible = red_frac(feat) >= args.reducibility_min
                    blamed = (z >= args.z_hi and rho[feat] >= args.spearman_min
                              and rank_f <= args.top_k and score > 0 and reducible)
```

report_rows 每行追加 4 键（放在 `"feature_err"` 之后）：

```python
                        "feature_err_raw": round(float(fe_raw[feat][ri]), 6),
                        "feature_err_sys": round(float(fe_raw[feat][ri] - fe_by_feature[feat][ri]), 6),
                        "reducibility_frac": round(red_frac(feat), 4),
                        "note": "" if reducible else "irreducible",
```

- [ ] **Step 3: summary 扩展**

features 字典每特征追加：

```python
                                    "global_spearman_raw": rho_raw[feat],
                                    "feature_err_raw_mean": round(float(np.nanmean(fe_raw[feat])), 6),
                                    "sys_frac": (decomp_meta.get(feat) or {}).get("sys_frac"),
                                    "stability_lambda": (decomp_meta.get(feat) or {}).get("stability_lambda"),
                                    "reducibility_frac": round(red_frac(feat), 4),
```

`fb.dump_json(args.summary, {...})` 的 params 后加 `"decomp": decomp_mode`。收尾 print 首行加 ` decomp={decomp_mode}`。

- [ ] **Step 4: BAD_BLAME 升级（放水必拦仍有牙）**

test_blame_golden.py 的 `BAD_BLAME`：特征元组扩成 9 个（加 f_jumpy/f_jumpy_decoy/f_sys_bias/f_res_culprit/f_irreducible），每特征字典补 `"global_spearman_raw": 0.1, "feature_err_raw_mean": 1.0, "sys_frac": 0.0, "stability_lambda": 0.0, "reducibility_frac": 1.0`，顶层 summary 加 `"decomp": "on"`，模型循环加 `"pred_M3", "pred_M4res"`——CLI/schema 全对但点名 f_decoy → gate 必 FAIL（断言不变：`returncode != 0` 且含"不许拿本脚本跑真实数据"）。

- [ ] **Step 5: manifest stage "2" 期望更新**

- **旧断言处理**：f_blame/f_decoy/f_good 各条**原样保留**（f_blame λ≈0 → ε_res≈raw，数值应基本不动）；f_jumpy×M3 的 `global_spearman between [0.15, 0.45]` 按实跑值重校（值域重叠下吸收有限，预计仍在带内或轻微下移——若移出，加宽下界到实测−0.05 并在 manifest note 里记一句"ε_res 下真值误差路径进一步减弱，翻新轴补位"）。
- **新增断言**：

```json
        {"file": "blame_summary.json", "path": "params.decomp", "op": "eq", "value": "on"},
        {"file": "blame_summary.json", "path": "rmse_192.pred_M4res.features.f_res_culprit.blamed_rows", "op": "ge", "value": 1},
        {"file": "blame_summary.json", "path": "rmse_192.pred_M4res.features.f_res_culprit.global_spearman", "op": "ge", "value": 0.8},
        {"file": "blame_summary.json", "path": "rmse_192.pred_M4res.features.f_irreducible.blamed_rows", "op": "eq", "value": 0},
        {"file": "blame_summary.json", "path": "rmse_192.pred_M4res.features.f_irreducible.global_spearman", "op": "ge", "value": 0.5},
        {"file": "blame_summary.json", "path": "rmse_192.pred_M4res.features.f_irreducible.reducibility_frac", "op": "le", "value": 0.05},
        {"file": "blame_summary.json", "path": "rmse_192.pred_M4res.features.f_sys_bias.blamed_rows", "op": "eq", "value": 0},
        {"file": "blame_summary.json", "path": "rmse_192.pred_M4res.features.f_sys_bias.global_spearman_raw", "op": "ge", "value": 0.5},
        {"file": "blame_summary.json", "path": "rmse_192.pred_M4res.features.f_sys_bias.sys_frac", "op": "ge", "value": 0.85},
        {"file": "blame_summary.json", "path": "rmse_192.pred_M1.features.f_sys_bias.blamed_rows", "op": "eq", "value": 0}
```

三条金律逐一在此闭环：f_irreducible 的 `global_spearman ≥ 0.5` + `blamed_rows == 0` = **只有可约性闸能挡它**；f_sys_bias 的 `global_spearman_raw ≥ 0.5` + `blamed_rows == 0` = **旧逻辑必冤枉、剥后洗清**；f_res_culprit `blamed ≥ 1` = **真波动元凶必点名**。

- [ ] **Step 6: 跑全套 gate + pytest**

Run: `python3 -m pytest pv-feature-blame/scripts/ -v`
Expected: 全 PASS（含 stage 2 新断言、BAD_BLAME 有牙测试、decompose 单测）。定性清单不成立时回 Task 3 修埋点，禁改断言迁就。

- [ ] **Step 7: Commit**

```bash
git add pv-feature-blame/scripts/feature_blame.py pv-feature-blame/scripts/test_blame_golden.py pv-feature-blame/golden/manifest.json
git commit -m "feat(pv-feature-blame): Stage 2 点名换 ε_res+可约性闸+raw/sys/res 三栏——f_sys_bias 洗清、f_res_culprit 点名、f_irreducible 被闸全过金标准"
```

---

### Task 6: run_orient.py 接入 Stage 1.5

**Files:**
- Modify: `<SKILL>/scripts/run_orient.py`

**Interfaces:**
- Consumes: `feature_decomp.json` 存在性；config `decompose.enabled`。
- Produces: orient 的阶段判定/前置行（无下游代码消费，人读）。

- [ ] **Step 1: 四处小改**

1. `STAGE_NAMES[2]` 改为：`"特征归因·先剥系统偏差（feature_decompose.py=Stage 1.5）再 ε_res 两关点名（feature_blame.py）+ 翻新跳变两关（feature_revision.py，免 API）"`
2. `scan()` 加 `"decomp": _exists("feature_decomp.json"),`
3. `revision_enabled` 旁加：

```python
def decompose_enabled(cfg):
    return (cfg.get("decompose") or {}).get("enabled", True) is not False
```

`stage_done(2)` 改为：

```python
    if stage == 2:
        return (ev["blame"] and (ev["revision"] or not revision_enabled(cfg))
                and (ev["decomp"] or not decompose_enabled(cfg)))
```

4. `prereqs(2)` 列表首行插入：

```python
        return [("feature_decomp.json 在（Stage 1.5 feature_decompose.py；不想剥系统偏差可"
                 "在 config 设 decompose.enabled=false）",
                 ev["decomp"] or not decompose_enabled(cfg)),
                ("bad_rows_summary.json 在（Stage 1）", ev["bad_rows"]),
                ("feature_pairs.json 在（Stage 0）", bool((ev["pairs"] or {}).get("pairs")))]
```

另在 main() 的旧版产物提示区（revision 提示旁）加：

```python
    if ev["blame"] and not ev["decomp"] and decompose_enabled(cfg):
        print("  ℹ 旧版产物：blame 在但缺 feature_decomp.json（v3 起点名基于 ε_res）。")
        print("    补跑 feature_decompose.py + 重跑 feature_blame.py 即升级；不需要可设"
              " decompose.enabled=false。")
```

- [ ] **Step 2: 冒烟验证**

```bash
cd "$(mktemp -d)" && python3 "<SKILL>/scripts/run_orient.py"
```
Expected: 报"未找到 blame_config.json"引导语（无崩溃）。再在含 golden 拷贝产物的临时目录跑一次，确认 Stage 2 行含 decompose、缺 feature_decomp.json 时前置 ✗。

- [ ] **Step 3: Commit**

```bash
git add pv-feature-blame/scripts/run_orient.py
git commit -m "feat(pv-feature-blame): orient 接 Stage 1.5——decomp 产物进阶段判定与前置，旧目录升级提示"
```

---

### Task 7: 文档同步（blame-methods / blame-discipline / SKILL.md / fb_common docstring 已在 Task 1）

**Files:**
- Modify: `<SKILL>/references/blame-methods.md`（「共线性聚类」节后插新节）
- Modify: `<SKILL>/references/blame-discipline.md`（反驳门 8 条 → 10 条；升级表补一行）
- Modify: `<SKILL>/SKILL.md`（阶段表 Stage 2 行、首要框定、常见错误）

**Interfaces:** 无代码接口；表述必须与 Task 1–6 的实名（`feature_decompose.py`/`feature_decomp.json`/`reducibility_frac`/`stability_lambda`/`decomp=on|off`）一致。

- [ ] **Step 1: blame-methods.md 插入新节（放在「两关点名（Stage 2）」之前）**

```markdown
## ε_sys/ε_res 分解（Stage 1.5，v3 起默认；feature_decompose.py）

**为什么**：功率模型在有偏预报上训练，会学会补偿**稳定的系统偏差**（共适应）——这部分
ε 再大也不该点名（修了对固定模型中性甚至有害）；纯白噪声的 ε 上游改不了，点名是废话。
点名对象应是"波动、可约、且与功率误差相关"的部分。

**方法**（稳健加性回归，不分箱——多维分箱会稀疏、要人为边界、要 weather_class 标签）：
`ε_f = pred − label` 逐点 → Huber 岭回归拟合条件均值：截距 + 钟点谐波(≤3 阶, cyclic) +
DoY 谐波(≤2 阶, cyclic) + 提前期 hinge(df≤5) + **每个配对特征的 pred 值 hinge**（天气型由
特征值隐式承载；own-pred 项抓"报得越高越偏高"的乘性偏差）。**回归只减条件均值不碰条件
方差**——"碎云段波动大"这类异方差结构原样留在 ε_res（feature_decomp.json 的
res_var_front/back 可查）。

**跨期稳定性收缩**：前段拟合、后段验证（embargo 48h = 192 步，防重叠窗泄漏），
`λ = clip(⟨ε_b,ŝ_b⟩/⟨ŝ_b,ŝ_b⟩,0,1)`；后段不复现（如一次性崩坏）→ λ→0 整条不剥。
拟合失败/样本不足/后段空一律 λ=0。**方向保守：宁少剥（残留点系统偏差）不过剥（把可约
波动当偏差丢，毁归因）。**

**可约性闸（Stage 2 消费）**：`reducibility = median(逐行 lag-1 自相关)₊²`；
< reducibility_min(0.1) → 该特征标 irreducible **不点名**。v2 占位：ε_res 形状分解
（相位/幅度/爬坡——相位错和幅度错对上游的指导完全不同）。

**作用域**：只有 feature_pairs.json 配对的预报特征存在 ε——未配对列（真实观测列）无 ε、
无反事实语义，落 feature_decomp.json 的 skipped_unpaired。golden 埋点：f_sys_bias
（乘性稳偏，raw 必冤枉、剥后必洗清）、f_res_culprit（波动元凶必点名）、f_irreducible
（ρ 双关都过、唯可约性闸挡）。缺分解产物 → feature_blame 回退原始 ε 并标 decomp=off。
```

同时「两关点名（Stage 2）」节首加一句：`v3 起 z 与 Spearman 都算在 ε_res 上（decomp=on 时）；共线簇也在 ε_res 向量上——剥掉公共系统偏差后虚假共线消解。`

- [ ] **Step 2: blame-discipline.md 反驳门追加两条（接续现有 8 条编号）**

```markdown
9. **系统偏差门**：sys_frac 高（>0.7）的特征即便 raw ε 大也不得升"假设"——疑似模型已
   补偿（共适应），修它需重训验证；blame_summary 的 global_spearman_raw vs global_spearman
   对照可见"剥前会冤枉、剥后洗清"。decomp=off（未跑 Stage 1.5）时点名基于原始 ε，
   结论最高到"现象"并注明未剥系统偏差。
10. **可约性门**：reducibility_frac < 0.1 的特征标 irreducible，只描述不点名——白噪声
    上游改不了，硬追是废话（金标准 f_irreducible：z/ρ 双关都过、唯此闸挡）。
```

升级表"现象"行判据补：`（v3 起基于 ε_res；decomp=off 须注明）`。

- [ ] **Step 3: SKILL.md 三处**

1. 阶段表 Stage 2 行改：`| **2 归因** | 三步：**剥系统偏差**（feature_decompose.py：稳健加性回归 ε_sys→ε_res+可约性，Stage 1.5）→ ε_res 两关（z + 全局 Spearman）点名 + 可约性闸 + 共线簇 → 翻新跳变两关（免 API） | `feature_decompose.py` → `feature_decomp.json` + `eps_res_*.npy`；`feature_blame.py` → `blame_report.csv` + `blame_summary.json`；`feature_revision.py` → `revision_report.csv` + `revision_summary.json` |`
2. 首要框定加第 6 条：`6. **稳定的系统偏差 ≠ 有罪**——功率模型在有偏预报上训练会学会补偿它（共适应）；点名基于剥掉 ε_sys 后的波动 ε_res（Stage 1.5），sys_frac 高的特征"修了"对固定模型可能有害。白噪声 ε_res 也不点名（可约性闸）——上游改不了的误差点名是废话。`
3. 常见错误加两条：

```markdown
- ❌ 在原始 ε 上点名不剥系统偏差（冤枉被模型吃掉的稳定偏差——金标准 f_sys_bias 专门埋了
  这个陷阱：raw Spearman 高但剥后必须洗清）。
- ❌ 点名 reducibility_frac < 0.1 的白噪声特征（上游改不了；金标准 f_irreducible 双关全过、
  唯可约性闸挡得住）。
```

- [ ] **Step 4: 跑 SKILL 相关守卫测试（若有 token 预算/路由测试覆盖本技能则一并）**

Run: `python3 -m pytest ts-diagnose/ pv-feature-blame/ -q 2>&1 | tail -5`
Expected: 全 PASS（SKILL.md 变长但非路由层，无预算闸；若 test_routing 有 description 钉子，未动 description 不受扰）。

- [ ] **Step 5: Commit**

```bash
git add pv-feature-blame/references/ pv-feature-blame/SKILL.md
git commit -m "docs(pv-feature-blame): ε 分解方法节+反驳门⑨⑩+SKILL 框定与常见错误"
```

---

### Task 8: Stage 4 residual 模式（反事实只换 ε_res）

**Files:**
- Modify: `<SKILL>/scripts/cf_logic.py`（`_finite` 之后加函数；`selfcheck()` 加检查）
- Modify: `<SKILL>/scripts/counterfactual_api.py`（Runner 初始化 + `err_of_factory` + oracle 调用点）
- Modify: `<SKILL>/golden/manifest.json`（stage "4" expect 加一条）

**Interfaces:**
- Consumes: Task 2 产物（`feature_decomp.json` + `eps_res_*.npy`）。
- Produces: `cf.residual_replacement(pred, eps_res) -> np.ndarray`；`counterfactual_summary.json` 顶层 `"counterfactual_mode": "residual"|"full"`；results CSV 新列 `mode`。

- [ ] **Step 1: cf_logic.py 加纯函数**

```python
def residual_replacement(pred, eps_res):
    """residual 模式替换向量：pred − ε_res = label + ε_sys（保留系统偏差、只去波动）。
    保持输入在功率模型分布内（避开 ε_sys 方向的 OOD），Δ 才可信。任一点非有限 →
    该点回退 pred（保守：不替换）。oracle 的 G 闸不用本函数——整换测"是不是特征问题"。"""
    pred = np.asarray(pred, float)
    out = pred - np.asarray(eps_res, float)
    return np.where(np.isfinite(out), out, pred)
```

`selfcheck()` 的 checks 里加：

```python
    label = np.array([10.0, 20.0, 30.0])
    sys_b = np.array([2.0, 2.0, 2.0])
    res_b = np.array([1.0, -3.0, np.nan])
    rep = residual_replacement(label + sys_b + res_b, res_b)
    checks["residual_replacement_identity"] = (
        np.allclose(rep[:2], (label + sys_b)[:2]) and np.isfinite(rep).all())
```

- [ ] **Step 2: manifest stage "4" expect 追加**

```json
        {"file": "cf_logic_selfcheck.json", "path": "checks.residual_replacement_identity", "op": "eq", "value": true}
```

- [ ] **Step 3: counterfactual_api.py 接线（三处）**

1. `Runner.__init__` 末尾：

```python
        dec = fb.read_json("feature_decomp.json")
        self.eps_res, self.residual_on = {}, False
        if dec and (cfg.get("decompose", {}).get("enabled", True)) \
                and int(dec.get("n_rows", -1)) == len(self.ft):
            try:
                self.eps_res = {f: np.load(f"eps_res_{fb.sanitize(f)}.npy")
                                for f in self.pcols}
                self.residual_on = True
            except OSError:
                self.eps_res = {}
        self.summary["counterfactual_mode"] = "residual" if self.residual_on else "full"
```

2. `err_of_factory(self, metric, model, ts)` 加参数 `residual: bool = False`，替换构造改：

```python
            if residual and self.residual_on:
                i = self.ft_idx[ts]
                replaced = {f: cf.residual_replacement(rd["features"][f]["pred"],
                                                       self.eps_res[f][i]) for f in subset}
            else:
                replaced = {f: rd["features"][f]["label"] for f in subset}
```

cache key 与 CSV 行加 mode 维度：`key = (metric, model, ts, sid, "res" if (residual and self.residual_on) else "full")`；`_record` 增 `mode` 列（旧 CSV 迁移逻辑给缺失列填 "full"，沿用现有 schema 迁移机制）。

3. 调用点：`run_oracle` 传 `residual=False`（G 闸整换，spec §7）；`run_marginal`/`run_minimal`/`run_lattice` 传 `residual=True`。`plan_table`/收尾 print 报 `counterfactual_mode`。

- [ ] **Step 4: 跑 gate + 全套**

Run: `python3 -m pytest pv-feature-blame/scripts/ -v`
Expected: 全 PASS（stage 4 selfcheck 新检查过；counterfactual_api 不过闸——HTTP 层本就靠 --dry-run 兜底，维持现状）。

- [ ] **Step 5: Commit**

```bash
git add pv-feature-blame/scripts/cf_logic.py pv-feature-blame/scripts/counterfactual_api.py pv-feature-blame/golden/manifest.json
git commit -m "feat(pv-feature-blame): Stage 4 residual 模式——边际/minimal/lattice 只换 ε_res（label+ε_sys），oracle G 闸仍整换"
```

---

### Task 9: 全仓验证 + CHANGELOG + 收尾

**Files:**
- Modify: `<SKILL>/CHANGELOG.md`

- [ ] **Step 1: 全仓测试**

Run: `python3 -m pytest "<REPO>" -q 2>&1 | tail -3`
Expected: 全 PASS（v3 前基线 102 项 + 本轮新增 ≈7 项）。任何 FAIL 回对应 task 修完重跑。

- [ ] **Step 2: CHANGELOG.md 记录**

```markdown
## 2026-07-20 v3：ε_sys/ε_res 分解（剥系统偏差后只对波动点名）
- Stage 1.5 feature_decompose.py：稳健加性回归（钟点/DoY 谐波+提前期+全部配对特征 pred 值
  hinge，df≤6）估 ε_sys；跨期稳定性 λ 收缩（embargo 48h）；lag-1 可约性；宁少剥不过剥。
- Stage 2：z/Spearman/共线全算在 ε_res 上 + 可约性闸 + raw/sys/res 三栏 +
  global_spearman_raw 对照；缺分解产物回退 raw 并标 decomp=off。
- Stage 4：residual 模式（边际/minimal/lattice 换 pred−ε_res=label+ε_sys；oracle 整换不变）。
- golden 新埋点：f_sys_bias（乘性稳偏 raw 必冤枉、剥后必洗清）/f_res_culprit（波动必点名）/
  f_irreducible（双关全过唯可约性闸挡）+ pred_M4res；f_jumpy 真值幅 5→25（防 own-pred 吸收，
  值域重叠检验）。反驳门 ⑨系统偏差门 ⑩可约性门。
- spec: docs/superpowers/specs/2026-07-17-pv-feature-blame-epsilon-decomp-design.md
```

- [ ] **Step 3: 最终 commit + 汇报**

```bash
git add pv-feature-blame/CHANGELOG.md
git commit -m "docs(pv-feature-blame): CHANGELOG v3 ε 分解轮"
```

向用户汇报：pytest 总数、golden 三诱饵的实测数值（sys_frac/λ/可约性/global_spearman_raw vs global_spearman）、遗留（真实数据未跑、FastAPI 契约待用户、v2 占位：张量交互与形状分解）。

---

## Self-Review 记录

- **Spec 覆盖**：§1 数据流(T2/T6)、§2.1 回归+df 上限+作用域(T1/T2)、§2.2 稳定性+波动保全(T2/T3/T4)、§3 可约性+v2 占位(T1/T7)、§4 三处改动(T5)、§5 报告纪律(T5/T7)、§6 文件清单(全)、§7 residual 模式(T8)、§8 golden 埋点+两断言(T3/T4/T5)、§9 顺序(任务序一致)、§10 边界(T7 文档)。偏差三处已显式记录：Stage 1.5 实现为 Stage 2 子步（orient 整数阶段约束）；分桶退路简化为 λ=0 不剥（比分桶更保守）；反驳门编号接续现有 ⑧ 为 ⑨⑩（spec 写 ⑦⑧ 时未计入 v2 已有 8 条）。
- **Placeholder 扫描**：无 TBD/TODO；全部步骤含完整代码或精确 diff 描述；数值期望的"实跑冻结"是仓库既有 golden 约定（manifest note 原文），非占位。
- **类型一致性**：`eps_matrices` 返回 dict[str, ndarray]（T1 定义，T2/T5 消费同名）；`feature_decomp.json` 键名（sys_frac/stability_lambda/reducibility/res_var_front/back/skipped_unpaired）在 T2 产、T4 断言、T5 消费、T7 文档四处逐字一致；`residual_replacement` 签名 T8 内一致；npy 命名统一 `eps_res_<fb.sanitize(feat)>.npy`。
