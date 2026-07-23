# Chartbook 扩展 Plan 2/4:纯数据侧 11 张新图

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** chartbook 新增 11 张不依赖模型访问的诊断图(误差结构 5、样本对比 2、输入侧 1、模型对比 2、时间稳定 1),每张 = recipe.md + 预写脚本 + 合成植入回收 golden。

**Architecture:** spec 见 `docs/superpowers/specs/2026-07-23-chartbook-expansion-design.md` §4。每张图独立一个 task,全部遵循既有 chartbook 模式:`chart_<蛇形>.py` 里 `compute()`(纯计算,被 golden 测)与 `render()`(画图)分离、`main(argv=None)` 可注入;JSON 一等 PNG 副产品;golden 用 `tests/synth.py` 的解析式构造(零随机;需要聚类/置换种子的图,种子显式 CLI 参数并落 JSON)。conform CI(Task 1 已落地的 category 闸)自动校验每个新 recipe。

**Tech Stack:** Python 3 / pytest / numpy / pandas / matplotlib / scipy(ks_2samp、chi2、norm)/ scikit-learn(KMeans、silhouette_score)。scipy 与 sklearn 是 sklearn 既有依赖链,无新装。

## Global Constraints

- 仓库根:`/Users/tqa946816/Documents/华为/光伏预测/结果分析skill`;分支 main;工作树 untracked 目录(docs/skill解析、gate_reports、row-diagnostic/demo_out)不得 add
- 每个 recipe frontmatter 必填 `category`(∈ engine_common.CATEGORY_IDS)且 id == 文件名;conform 闸 `ts-diagnose/chartbook/tests/test_recipes_conform.py` 必须绿
- **领域中立(评审执法)**:recipe 正文/图内标签/判读不得出现天气、光伏、站点、医学等领域名词——CI 只闸 id,正文靠人审,这条写给每个实施者
- 脚本公共 CLI:`--pred`(规范长表)、`--out-dir`;render() 首行调 `cc.setup_font()`;matplotlib 只在 render 内 import
- golden 决定论:零随机,或固定种子显式 CLI 参数并落 JSON(_recipe-spec §5.3)
- 每 task:先写测试跑红 → 实现转绿 → `python3 -m pytest ts-diagnose/chartbook/tests/ -q` 全绿 → commit
- commit message 末尾带 `Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>`
- 数值断言优先精确回收(np.isclose 默认容差);统计检验断言用阈值(如 p<0.05)

---

### Task 1: pp-calibration(分位数校准)

**Files:**
- Create: `ts-diagnose/chartbook/recipes/pp-calibration.md`
- Create: `ts-diagnose/chartbook/scripts/chart_pp_calibration.py`
- Test: `ts-diagnose/chartbook/tests/test_chart_pp_calibration.py`

**Interfaces:**
- Consumes: `chart_common.load_predictions/curve_stats/save_outputs/setup_font`
- Produces: recipe id `pp-calibration`(category error-structure)

- [ ] **Step 1: 写 recipe**

```markdown
---
id: pp-calibration
category: error-structure
needs_materials: [predict, truth]
适用问题: 预测的取值分布与真值分布对齐吗?模型是否系统性压缩高值/抬高低值(归一化副作用)?
outputs:
  json: pp-calibration.json
  png: pp-calibration.png
json_schema: >
  每模型:quantiles(q/y_true_q/y_pred_q/ratio 列表)、slope(分位数对 OLS 斜率)、
  high_tail_ratio(q95_pred/q95_true)、low_tail_ratio(q05 同理,分母近 0 时 null)、n。
bridge_hooks: >
  slope<1 且 high_tail_ratio 明显<1 → 幅值压缩类候选(归一化/裁剪副作用),
  与 true-vs-pred-scatter 高值段 slope 交叉;slope≈1 但尾部比值偏离 → 仅尾部
  失真,转 horizon-error-quantiles 看误差分布形态。
验证步: 植入 y_pred=0.8·y_true → slope 与两尾比值精确回收 0.8(tests/test_chart_pp_calibration.py)
---

# pp-calibration:分位数-分位数校准

## 适用问题
边缘分布层面的校准:不看逐点误差,看"预测值的分布"与"真值的分布"是否同形。
系统性压缩/抬升在散点图上易被点云掩盖,分位数对上一目了然。

## CLI 与参数
```bash
python3 chartbook/scripts/chart_pp_calibration.py \
  --pred predictions.parquet --out-dir <workdir>/charts
```

## JSON schema
见 frontmatter;分位点固定 q ∈ {0.01,0.05,0.1,...,0.9,0.95,0.99}(0.1 步进主体);
ratio = y_pred_q / y_true_q,|y_true_q| < 1e-9 时该点 ratio 为 null。

## 判读
- `slope < 0.9` 且 `high_tail_ratio < 0.9` → 候选:整体幅值压缩——去
  true-vs-pred-scatter 看高值段是否同证;
- 两尾比值一高一低 → 候选:分布被"往中间挤"(过平滑),转 worst-points 看
  极值点占比;
- slope≈1、尾比≈1 但误差仍大 → 分布对齐、逐点错位,转 time-shift-diagnosis。
只给候选假设;结论回 playbook 三道门。

## 验证步
golden 植入 y_pred = 0.8·y_true(y 随 step 变化保证分位数非退化)→
slope、high_tail_ratio、low_tail_ratio 全部精确回收 0.8。
```

- [ ] **Step 2: 写 golden 测试(先跑红)**

`tests/test_chart_pp_calibration.py`:

```python
"""pp-calibration golden:y_pred=0.8·y_true(y=10+s 非退化)→ slope 与两尾比值精确回收。"""
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

import chart_pp_calibration as cpc  # noqa: E402
from synth import make_long         # noqa: E402
import pandas as pd                 # noqa: E402


def _prep(df):
    df["window_ts"] = pd.to_datetime(df["window_ts"])
    df["err"] = df["y_pred"] - df["y_true"]
    return df


def test_scale_08_recovered():
    y_fn = lambda w, u, s: 10.0 + s
    df = _prep(make_long(["A"], ["U1"], ["2024-01-01", "2024-01-02"], 24,
                         lambda m, u, w, s: -0.2 * (10.0 + s), y_fn=y_fn))
    st = cpc.compute(df)
    a = st["models"]["A"]
    assert np.isclose(a["slope"], 0.8)
    assert np.isclose(a["high_tail_ratio"], 0.8)
    assert np.isclose(a["low_tail_ratio"], 0.8)
    for q in a["quantiles"]:
        if q["ratio"] is not None:
            assert np.isclose(q["ratio"], 0.8)


def test_identity_gives_slope_1():
    df = _prep(make_long(["A"], ["U1"], ["2024-01-01"], 24,
                         lambda m, u, w, s: 0.0, y_fn=lambda w, u, s: 10.0 + s))
    st = cpc.compute(df)
    assert np.isclose(st["models"]["A"]["slope"], 1.0)


def test_main_writes_outputs(tmp_path):
    df = make_long(["A"], ["U1"], ["2024-01-01"], 24,
                   lambda m, u, w, s: 0.0, y_fn=lambda w, u, s: 10.0 + s)
    p = tmp_path / "pred.csv"
    df.to_csv(p, index=False)
    cpc.main(["--pred", str(p), "--out-dir", str(tmp_path)])
    assert (tmp_path / "pp-calibration.json").exists()
    assert (tmp_path / "pp-calibration.png").exists()
```

Run: `python3 -m pytest ts-diagnose/chartbook/tests/test_chart_pp_calibration.py -q`
Expected: FAIL(ModuleNotFoundError: chart_pp_calibration)

- [ ] **Step 3: 写脚本**

`scripts/chart_pp_calibration.py`:

```python
"""pp-calibration:y_pred 与 y_true 的分位数-分位数对齐——系统性压缩/抬升的直接证据。"""
from __future__ import annotations

import argparse

import numpy as np
import pandas as pd

import chart_common as cc

RECIPE_ID = "pp-calibration"
QS = [0.01, 0.05, 0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8, 0.9, 0.95, 0.99]


def compute(df: pd.DataFrame) -> dict:
    out = {"recipe": RECIPE_ID, "models": {},
           "note": "ratio=y_pred_q/y_true_q;|y_true_q|<1e-9 时 ratio=null;"
                   "slope 为分位数对过原点 OLS 斜率。"}
    for m, g in df.groupby("model"):
        qt = np.quantile(g["y_true"], QS)
        qp = np.quantile(g["y_pred"], QS)
        pairs = []
        for q, t, p in zip(QS, qt, qp):
            ratio = round(float(p / t), 4) if abs(t) > 1e-9 else None
            pairs.append({"q": q, "y_true_q": round(float(t), 4),
                          "y_pred_q": round(float(p), 4), "ratio": ratio})
        denom = float(np.dot(qt, qt))
        slope = round(float(np.dot(qt, qp) / denom), 4) if denom > 1e-12 else None
        def _tail(i):
            return round(float(qp[i] / qt[i]), 4) if abs(qt[i]) > 1e-9 else None
        out["models"][str(m)] = {
            "quantiles": pairs, "slope": slope,
            "high_tail_ratio": _tail(QS.index(0.95)),
            "low_tail_ratio": _tail(QS.index(0.05)),
            "n": int(len(g))}
    return out


def render(stats: dict):
    import matplotlib.pyplot as plt
    cc.setup_font()
    fig, ax = plt.subplots(figsize=(6, 6))
    lo, hi = np.inf, -np.inf
    for m, s in stats["models"].items():
        xs = [q["y_true_q"] for q in s["quantiles"]]
        ys = [q["y_pred_q"] for q in s["quantiles"]]
        ax.plot(xs, ys, marker="o", ms=3, label=f"{m} (slope={s['slope']})")
        lo, hi = min(lo, min(xs + ys)), max(hi, max(xs + ys))
    ax.plot([lo, hi], [lo, hi], "k--", lw=0.8, label="y=x")
    ax.set_xlabel("真值分位数"), ax.set_ylabel("预测分位数")
    ax.set_title("pp-calibration 分位数校准")
    ax.legend()
    return fig


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--pred", required=True)
    ap.add_argument("--out-dir", required=True)
    a = ap.parse_args(argv)
    stats = compute(cc.load_predictions(a.pred))
    cc.save_outputs(render(stats), a.out_dir, RECIPE_ID, stats)


if __name__ == "__main__":
    main()
```

- [ ] **Step 4: 跑绿 + 全量 + Commit**

Run: `python3 -m pytest ts-diagnose/chartbook/tests/test_chart_pp_calibration.py -q` → PASS;
`python3 -m pytest ts-diagnose/chartbook/tests/ -q` → 全 PASS(conform 闸自动覆盖新 recipe)。

```bash
git add ts-diagnose/chartbook/recipes/pp-calibration.md ts-diagnose/chartbook/scripts/chart_pp_calibration.py ts-diagnose/chartbook/tests/test_chart_pp_calibration.py
git commit -m "feat(ts-diagnose): chartbook 新图 pp-calibration——分位数校准(斜率+两尾比值精确回收 golden)

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```

---

### Task 2: horizon-error-quantiles(逐步误差分位扇形)

**Files:**
- Create: `ts-diagnose/chartbook/recipes/horizon-error-quantiles.md`
- Create: `ts-diagnose/chartbook/scripts/chart_horizon_error_quantiles.py`
- Test: `ts-diagnose/chartbook/tests/test_chart_horizon_error_quantiles.py`

**Interfaces:**
- Consumes: chart_common 同上
- Produces: recipe id `horizon-error-quantiles`(category error-structure)

- [ ] **Step 1: 写 recipe**

```markdown
---
id: horizon-error-quantiles
category: error-structure
needs_materials: [predict, truth]
适用问题: h 步预测该配多宽的经验置信带?误差分布随 horizon 是否偏斜/厚尾?
outputs:
  json: horizon-error-quantiles.json
  png: horizon-error-quantiles.png
json_schema: >
  每模型:p05/p25/p50/p75/p95 逐 horizon 曲线(curve_stats)、width90 曲线
  (p95−p05)、growth_ratio(末步 width90/首步 width90)、median_skew
  (p50 偏离 0 的均值)、n_per_step。
bridge_hooks: >
  width90 随 horizon 线性/超线性增长 → 误差累积类候选,与 horizon-degradation
  的 RMSE 曲线互证;p50 持续偏一侧 → 系统性偏差候选,转 theil-decomposition
  看 U_bias 占比;带宽不增但 RMSE 增 → 少数大误差点驱动,转 worst-points。
验证步: 植入误差幅度 0.1·(h+1)、窗口间对称正负 → 每步 p05/p95=∓/+幅度、width90 线性增长精确回收(tests/test_chart_horizon_error_quantiles.py)
---

# horizon-error-quantiles:逐步误差分位扇形带

## 适用问题
点预测场景下"该给下游多宽的置信带"的经验答案;同时把"误差大"细化成
"分布宽"还是"分布偏"。

## CLI 与参数
```bash
python3 chartbook/scripts/chart_horizon_error_quantiles.py \
  --pred predictions.parquet --out-dir <workdir>/charts
```

## JSON schema
见 frontmatter;分位在每 (model, horizon_step) 的全部 err 样本上算(pool 单元与窗口)。

## 判读
- `growth_ratio` 大(>3)且 width90 曲线单调 → 候选:误差随 horizon 累积——
  与 horizon-degradation 退化斜率互证;
- `median_skew` 显著非 0 → 候选:系统性偏差主导,转 theil-decomposition;
- 带对称且窄、但 RMSE 高 → 厚尾/离群驱动,转 worst-points 看点级性质。
只给候选假设;结论回 playbook 三道门。

## 验证步
4 窗口、误差幅度 0.1·(h+1)、窗口按奇偶取正负号(每步样本恰为 {−a,−a,+a,+a})→
p05=−a、p95=+a、p50=0、width90=0.2·(h+1) 逐步精确回收,growth_ratio=末步/首步。
```

- [ ] **Step 2: 写 golden 测试(先跑红)**

```python
"""horizon-error-quantiles golden:幅度 0.1(h+1)、窗口奇偶定符号 → 分位带逐步精确回收。"""
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

import chart_horizon_error_quantiles as chq  # noqa: E402
from synth import make_long                  # noqa: E402

WINDOWS = ["2024-01-01", "2024-01-02", "2024-01-03", "2024-01-04"]


def _prep(df):
    df["window_ts"] = pd.to_datetime(df["window_ts"])
    df["err"] = df["y_pred"] - df["y_true"]
    return df


def _err(m, u, w, s):
    sign = 1.0 if WINDOWS.index(w) % 2 == 0 else -1.0
    return sign * 0.1 * (s + 1)


def test_bands_recovered():
    df = _prep(make_long(["A"], ["U1"], WINDOWS, 12, _err))
    st = chq.compute(df)
    a = st["models"]["A"]
    for h in range(12):
        amp = 0.1 * (h + 1)
        assert np.isclose(a["p95"]["curve"][str(h)], amp)
        assert np.isclose(a["p05"]["curve"][str(h)], -amp)
        assert np.isclose(a["p50"]["curve"][str(h)], 0.0)
        assert np.isclose(a["width90"]["curve"][str(h)], 2 * amp)
    assert np.isclose(a["growth_ratio"], 12.0)
    assert np.isclose(a["median_skew"], 0.0)
    assert a["n_per_step"] == 4


def test_main_writes_outputs(tmp_path):
    df = make_long(["A"], ["U1"], WINDOWS, 12, _err)
    p = tmp_path / "pred.csv"
    df.to_csv(p, index=False)
    chq.main(["--pred", str(p), "--out-dir", str(tmp_path)])
    assert (tmp_path / "horizon-error-quantiles.json").exists()
    assert (tmp_path / "horizon-error-quantiles.png").exists()
```

Run → FAIL(ModuleNotFoundError)。

- [ ] **Step 3: 写脚本**

```python
"""horizon-error-quantiles:逐 horizon 的经验误差分位扇形带——该配多宽的置信带、
分布是否偏斜。"""
from __future__ import annotations

import argparse

import numpy as np
import pandas as pd

import chart_common as cc

RECIPE_ID = "horizon-error-quantiles"
BAND_QS = {"p05": 0.05, "p25": 0.25, "p50": 0.5, "p75": 0.75, "p95": 0.95}


def compute(df: pd.DataFrame) -> dict:
    out = {"recipe": RECIPE_ID, "models": {},
           "note": "分位在每 (model,horizon_step) 全样本上算(pool 单元与窗口);"
                   "width90=p95−p05;growth_ratio=末步 width90/首步 width90。"}
    for m, g in df.groupby("model"):
        grp = g.groupby("horizon_step")["err"]
        steps = sorted(g["horizon_step"].unique().tolist())
        bands = {k: grp.quantile(q) for k, q in BAND_QS.items()}
        s = {k: cc.curve_stats(v.values, index=steps) for k, v in bands.items()}
        w90 = bands["p95"].values - bands["p05"].values
        s["width90"] = cc.curve_stats(w90, index=steps)
        first, last = float(w90[0]), float(w90[-1])
        s["growth_ratio"] = round(last / first, 4) if abs(first) > 1e-12 else None
        s["median_skew"] = round(float(np.mean(bands["p50"].values)), 4)
        s["n_per_step"] = int(grp.count().min())
        out["models"][str(m)] = s
    return out


def render(stats: dict):
    import matplotlib.pyplot as plt
    cc.setup_font()
    n = len(stats["models"])
    fig, axes = plt.subplots(1, n, figsize=(6 * n, 4), squeeze=False)
    for ax, (m, s) in zip(axes[0], stats["models"].items()):
        xs = [int(k) for k in s["p50"]["curve"]]
        get = lambda key: [s[key]["curve"][str(x)] for x in xs]
        ax.fill_between(xs, get("p05"), get("p95"), alpha=0.2, label="p05–p95")
        ax.fill_between(xs, get("p25"), get("p75"), alpha=0.35, label="p25–p75")
        ax.plot(xs, get("p50"), lw=1.2, label="p50")
        ax.axhline(0, color="k", lw=0.5)
        ax.set_title(f"{m} 误差分位扇形"), ax.set_xlabel("horizon step")
        ax.legend(fontsize=8)
    return fig


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--pred", required=True)
    ap.add_argument("--out-dir", required=True)
    a = ap.parse_args(argv)
    stats = compute(cc.load_predictions(a.pred))
    cc.save_outputs(render(stats), a.out_dir, RECIPE_ID, stats)


if __name__ == "__main__":
    main()
```

- [ ] **Step 4: 跑绿 + 全量 + Commit**

同 Task 1 模式;commit message:
`feat(ts-diagnose): chartbook 新图 horizon-error-quantiles——逐步误差分位扇形(带宽线性增长精确回收 golden)`(带 Co-Authored-By 尾行)

---

### Task 3: theil-decomposition(误差性质三分)

**Files:**
- Create: `ts-diagnose/chartbook/recipes/theil-decomposition.md`
- Create: `ts-diagnose/chartbook/scripts/chart_theil_decomposition.py`
- Test: `ts-diagnose/chartbook/tests/test_chart_theil_decomposition.py`

**Interfaces:**
- Consumes: chart_common 同上
- Produces: recipe id `theil-decomposition`(category error-structure)

- [ ] **Step 1: 写 recipe**

```markdown
---
id: theil-decomposition
category: error-structure
needs_materials: [predict, truth]
适用问题: 误差是水平偏移(bias)、幅度不匹配(variance)还是形状/错位(covariance)?修法完全不同。
outputs:
  json: theil-decomposition.json
  png: theil-decomposition.png
json_schema: >
  每模型:overall{u_bias,u_var,u_cov,mse}(三者和为 1)+ by_segment(horizon
  三等分 early/mid/late 各一组)+ n;mse≈0 时该组四值为 null 并记 note。
bridge_hooks: >
  u_bias 主导 → 系统性偏移候选(后处理平移可修),与 pp-calibration 的 slope
  截距侧互证;u_var 主导 → 幅度压缩/放大候选,转 true-vs-pred-scatter;
  u_cov 主导 → 形状/时序错位候选,转 time-shift-diagnosis 查时移。
验证步: 纯偏移植入 → u_bias=1;纯幅度失配植入 → u_var=1,精确回收(tests/test_chart_theil_decomposition.py)
---

# theil-decomposition:Theil U 误差三分

## 适用问题
把"误差大"翻译成修复动作:MSE = (ȳp−ȳt)² + (σp−σt)² + 2(1−r)σpσt,
三项占比 u_bias/u_var/u_cov 直接指向平移修正、幅度校准、还是结构问题。

## CLI 与参数
```bash
python3 chartbook/scripts/chart_theil_decomposition.py \
  --pred predictions.parquet --out-dir <workdir>/charts
```

## JSON schema
见 frontmatter;segment 按 horizon_step 三等分(early/mid/late),池化单元与窗口。

## 判读
- `u_bias ≥ 0.5` → 候选:系统性水平偏移——最便宜的修法(输出平移),先查
  by_segment 是否全段一致;
- `u_var ≥ 0.5` → 候选:幅度失配(归一化/容量假设错),与 pp-calibration 互证;
- `u_cov ≥ 0.5` → 误差主要来自"形对不上",转 time-shift-diagnosis 与
  error-acf 找结构;
- 三项均衡 → 无单一主因,回 error-breakdown 先定位坏切片再分解。
只给候选假设;结论回 playbook 三道门。

## 验证步
纯偏移(y_pred=y_true+2,y 随 step 变化)→ overall u_bias=1、其余=0;
纯幅度(y_t=s 均值对齐、y_p=2s−11.5,r=1)→ u_var=1,精确回收。
```

- [ ] **Step 2: 写 golden 测试(先跑红)**

```python
"""theil-decomposition golden:纯偏移→u_bias=1;纯幅度失配(均值对齐、r=1)→u_var=1。"""
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

import chart_theil_decomposition as ctd  # noqa: E402
from synth import make_long              # noqa: E402


def _prep(df):
    df["window_ts"] = pd.to_datetime(df["window_ts"])
    df["err"] = df["y_pred"] - df["y_true"]
    return df


def test_pure_bias():
    df = _prep(make_long(["A"], ["U1"], ["2024-01-01"], 24,
                         lambda m, u, w, s: 2.0, y_fn=lambda w, u, s: 10.0 + s))
    o = ctd.compute(df)["models"]["A"]["overall"]
    assert np.isclose(o["u_bias"], 1.0)
    assert np.isclose(o["u_var"], 0.0) and np.isclose(o["u_cov"], 0.0)
    assert np.isclose(o["mse"], 4.0)


def test_pure_variance():
    # y_t = s (mean 11.5), y_p = 2s − 11.5 (同均值、2 倍标准差、r=1) → u_var=1
    df = _prep(make_long(["A"], ["U1"], ["2024-01-01"], 24,
                         lambda m, u, w, s: float(s) - 11.5,
                         y_fn=lambda w, u, s: float(s)))
    o = ctd.compute(df)["models"]["A"]["overall"]
    assert np.isclose(o["u_var"], 1.0)
    assert np.isclose(o["u_bias"], 0.0) and np.isclose(o["u_cov"], 0.0)


def test_zero_mse_gives_null():
    df = _prep(make_long(["A"], ["U1"], ["2024-01-01"], 24,
                         lambda m, u, w, s: 0.0, y_fn=lambda w, u, s: 10.0 + s))
    o = ctd.compute(df)["models"]["A"]["overall"]
    assert o["u_bias"] is None and o["mse"] == 0.0


def test_main_writes_outputs(tmp_path):
    df = make_long(["A"], ["U1"], ["2024-01-01"], 24,
                   lambda m, u, w, s: 2.0, y_fn=lambda w, u, s: 10.0 + s)
    p = tmp_path / "pred.csv"
    df.to_csv(p, index=False)
    ctd.main(["--pred", str(p), "--out-dir", str(tmp_path)])
    assert (tmp_path / "theil-decomposition.json").exists()
    assert (tmp_path / "theil-decomposition.png").exists()
```

Run → FAIL。

- [ ] **Step 3: 写脚本**

```python
"""theil-decomposition:MSE 的 Theil 三分(bias/variance/covariance 占比)——
误差是平移、幅度还是形状问题。"""
from __future__ import annotations

import argparse

import numpy as np
import pandas as pd

import chart_common as cc

RECIPE_ID = "theil-decomposition"


def _theil(y_true: np.ndarray, y_pred: np.ndarray) -> dict:
    mse = float(np.mean((y_pred - y_true) ** 2))
    if mse < 1e-12:
        return {"u_bias": None, "u_var": None, "u_cov": None,
                "mse": round(mse, 6)}
    st, sp = float(np.std(y_true)), float(np.std(y_pred))
    bias2 = (float(np.mean(y_pred)) - float(np.mean(y_true))) ** 2
    var2 = (sp - st) ** 2
    if st > 1e-12 and sp > 1e-12:
        r = float(np.corrcoef(y_true, y_pred)[0, 1])
        cov = 2 * (1 - r) * sp * st
    else:
        cov = mse - bias2 - var2
    return {"u_bias": round(bias2 / mse, 4), "u_var": round(var2 / mse, 4),
            "u_cov": round(cov / mse, 4), "mse": round(mse, 6)}


def compute(df: pd.DataFrame) -> dict:
    out = {"recipe": RECIPE_ID, "models": {},
           "note": "u_bias+u_var+u_cov=1(浮点容差);segment 按 horizon 三等分;"
                   "mse≈0 时四值 null。"}
    for m, g in df.groupby("model"):
        seg = {}
        smax = int(g["horizon_step"].max()) + 1
        bounds = [(0, smax // 3), (smax // 3, 2 * smax // 3), (2 * smax // 3, smax)]
        for name, (lo, hi) in zip(("early", "mid", "late"), bounds):
            gs = g[(g["horizon_step"] >= lo) & (g["horizon_step"] < hi)]
            if len(gs):
                seg[name] = _theil(gs["y_true"].values, gs["y_pred"].values)
        out["models"][str(m)] = {
            "overall": _theil(g["y_true"].values, g["y_pred"].values),
            "by_segment": seg, "n": int(len(g))}
    return out


def render(stats: dict):
    import matplotlib.pyplot as plt
    cc.setup_font()
    models = list(stats["models"])
    fig, ax = plt.subplots(figsize=(1.5 + 1.2 * len(models), 4))
    bottoms = np.zeros(len(models))
    for key, label in (("u_bias", "偏移"), ("u_var", "幅度"), ("u_cov", "形状")):
        vals = np.array([stats["models"][m]["overall"][key] or 0.0
                         for m in models])
        ax.bar(models, vals, bottom=bottoms, label=label)
        bottoms += vals
    ax.set_ylabel("MSE 占比"), ax.set_ylim(0, 1.05)
    ax.set_title("theil-decomposition 误差性质三分")
    ax.legend()
    return fig


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--pred", required=True)
    ap.add_argument("--out-dir", required=True)
    a = ap.parse_args(argv)
    stats = compute(cc.load_predictions(a.pred))
    cc.save_outputs(render(stats), a.out_dir, RECIPE_ID, stats)


if __name__ == "__main__":
    main()
```

- [ ] **Step 4: 跑绿 + 全量 + Commit**

commit message:`feat(ts-diagnose): chartbook 新图 theil-decomposition——误差三分(纯偏移/纯幅度双植入精确回收 golden)`(带 Co-Authored-By 尾行)

---

### Task 4: time-shift-diagnosis(时移诊断)

**Files:**
- Create: `ts-diagnose/chartbook/recipes/time-shift-diagnosis.md`
- Create: `ts-diagnose/chartbook/scripts/chart_time_shift_diagnosis.py`
- Test: `ts-diagnose/chartbook/tests/test_chart_time_shift_diagnosis.py`

**Interfaces:**
- Consumes: chart_common 同上
- Produces: recipe id `time-shift-diagnosis`(category error-structure)

- [ ] **Step 1: 写 recipe**

```markdown
---
id: time-shift-diagnosis
category: error-structure
needs_materials: [predict, truth]
适用问题: 预测曲线是不是整体提前/滞后了几步?(形状对、对时错)
outputs:
  json: time-shift-diagnosis.json
  png: time-shift-diagnosis.png
json_schema: >
  每模型:shift_hist(各平移步数的窗口计数)、mode_shift(众数)、
  share_nonzero(最优平移≠0 的窗口占比)、mean_abs_shift、n_windows、
  max_shift(搜索半径)。shift>0=预测滞后(晚),<0=超前。
bridge_hooks: >
  mode_shift≠0 且 share_nonzero 高 → 系统性对时错位候选(输入时间基准/
  时区/发布延迟类),与 theil-decomposition 的 u_cov 主导互证;shift 集中 0
  但 u_cov 仍高 → 非平移型形状失配,转 error-acf/worst-points。
验证步: y_pred=y_true 平移 2 步(非线性周期形)→ mode_shift=2、share_nonzero=1 精确回收(tests/test_chart_time_shift_diagnosis.py)
---

# time-shift-diagnosis:逐窗最优时移分布

## 适用问题
逐点误差大而形状描述符都正常时,第一个该排查的就是"对时错位"——整体
提前/滞后 k 步会造出大 RMSE 却完全可修(对齐输入时间基准)。

## CLI 与参数
```bash
python3 chartbook/scripts/chart_time_shift_diagnosis.py \
  --pred predictions.parquet --out-dir <workdir>/charts [--max-shift 8]
```

## JSON schema
见 frontmatter;每 (model,unit,window) 求 k* = argmin_k MSE(y_pred[t], y_true[t−k]),
k ∈ [−max_shift, max_shift],重叠段 < 8 点的窗口跳过并计入 skipped。

## 判读
- `mode_shift ≠ 0` 且 `share_nonzero ≥ 0.7` → 候选:系统性对时错位——查数据
  管道时间基准(采样对齐/时区/发布延迟),修好即免费收益;
- shift 分布双峰/弥散 → 候选:间歇性延迟(部分批次晚到),回 error-breakdown
  看时间聚集;
- 全部 ≈0 → 排除平移型错位,u_cov 高时转非平移形状假设。
只给候选假设;结论回 playbook 三道门。

## 验证步
y 为周期 8 的确定性正弦形,y_pred 恰为 y_true 平移 2 步 → 每窗 k*=2 唯一,
mode_shift=2、share_nonzero=1.0、mean_abs_shift=2 精确回收;零平移对照 mode=0。
```

- [ ] **Step 2: 写 golden 测试(先跑红)**

```python
"""time-shift-diagnosis golden:周期 8 正弦形、y_pred=y_true 平移 2 步 → mode_shift=2。"""
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

import chart_time_shift_diagnosis as cts  # noqa: E402
from synth import make_long               # noqa: E402


def _y(s):
    return round(10.0 + 5.0 * np.sin(2 * np.pi * s / 8.0), 6)


def _prep(df):
    df["window_ts"] = pd.to_datetime(df["window_ts"])
    df["err"] = df["y_pred"] - df["y_true"]
    return df


def test_shift_2_recovered():
    # y_pred[s] = y_true[s−2] → 预测滞后 2 步
    df = _prep(make_long(["A"], ["U1", "U2"], ["2024-01-01", "2024-01-02"], 24,
                         lambda m, u, w, s: _y(s - 2) - _y(s),
                         y_fn=lambda w, u, s: _y(s)))
    a = cts.compute(df, max_shift=4)["models"]["A"]
    assert a["mode_shift"] == 2
    assert np.isclose(a["share_nonzero"], 1.0)
    assert np.isclose(a["mean_abs_shift"], 2.0)
    assert a["n_windows"] == 4


def test_zero_shift_control():
    df = _prep(make_long(["A"], ["U1"], ["2024-01-01"], 24,
                         lambda m, u, w, s: 0.0, y_fn=lambda w, u, s: _y(s)))
    a = cts.compute(df, max_shift=4)["models"]["A"]
    assert a["mode_shift"] == 0 and a["share_nonzero"] == 0.0


def test_main_writes_outputs(tmp_path):
    df = make_long(["A"], ["U1"], ["2024-01-01"], 24,
                   lambda m, u, w, s: 0.0, y_fn=lambda w, u, s: _y(s))
    p = tmp_path / "pred.csv"
    df.to_csv(p, index=False)
    cts.main(["--pred", str(p), "--out-dir", str(tmp_path), "--max-shift", "4"])
    assert (tmp_path / "time-shift-diagnosis.json").exists()
    assert (tmp_path / "time-shift-diagnosis.png").exists()
```

Run → FAIL。

- [ ] **Step 3: 写脚本**

```python
"""time-shift-diagnosis:逐窗最优互相关平移量分布——预测是否整体提前/滞后。
shift>0 = 预测滞后(y_pred[t] ≈ y_true[t−shift])。"""
from __future__ import annotations

import argparse

import numpy as np
import pandas as pd

import chart_common as cc

RECIPE_ID = "time-shift-diagnosis"
MIN_OVERLAP = 8


def _best_shift(y_pred: np.ndarray, y_true: np.ndarray, max_shift: int):
    n = len(y_true)
    best_k, best_mse = None, np.inf
    for k in range(-max_shift, max_shift + 1):
        t = np.arange(n)
        m = (t - k >= 0) & (t - k < n)
        if m.sum() < MIN_OVERLAP:
            continue
        mse = float(np.mean((y_pred[m] - y_true[t[m] - k]) ** 2))
        if mse < best_mse - 1e-12:
            best_k, best_mse = k, mse
    return best_k


def compute(df: pd.DataFrame, max_shift: int = 8) -> dict:
    out = {"recipe": RECIPE_ID, "max_shift": max_shift, "models": {},
           "note": "shift>0=预测滞后;k*=argmin_k MSE(y_pred[t],y_true[t−k]);"
                   f"重叠<{MIN_OVERLAP} 点的窗口跳过。"}
    for m, g in df.groupby("model"):
        shifts, skipped = [], 0
        for (_u, _w), gw in g.groupby(["unit_id", "window_ts"]):
            gw = gw.sort_values("horizon_step")
            k = _best_shift(gw["y_pred"].values, gw["y_true"].values, max_shift)
            if k is None:
                skipped += 1
            else:
                shifts.append(k)
        if not shifts:
            out["models"][str(m)] = {"shift_hist": {}, "mode_shift": None,
                                     "share_nonzero": None, "mean_abs_shift": None,
                                     "n_windows": 0, "skipped": skipped}
            continue
        vals, counts = np.unique(shifts, return_counts=True)
        hist = {str(int(v)): int(c) for v, c in zip(vals, counts)}
        out["models"][str(m)] = {
            "shift_hist": hist,
            "mode_shift": int(vals[int(np.argmax(counts))]),
            "share_nonzero": round(float(np.mean(np.array(shifts) != 0)), 4),
            "mean_abs_shift": round(float(np.mean(np.abs(shifts))), 4),
            "n_windows": len(shifts), "skipped": skipped}
    return out


def render(stats: dict):
    import matplotlib.pyplot as plt
    cc.setup_font()
    n = len(stats["models"])
    fig, axes = plt.subplots(1, n, figsize=(5 * n, 3.5), squeeze=False)
    for ax, (m, s) in zip(axes[0], stats["models"].items()):
        ks = sorted(int(k) for k in s["shift_hist"])
        ax.bar(ks, [s["shift_hist"][str(k)] for k in ks])
        ax.axvline(0, color="k", lw=0.5)
        ax.set_title(f"{m} 最优平移分布 (mode={s['mode_shift']})")
        ax.set_xlabel("平移步数(>0=滞后)"), ax.set_ylabel("窗口数")
    return fig


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--pred", required=True)
    ap.add_argument("--out-dir", required=True)
    ap.add_argument("--max-shift", type=int, default=8)
    a = ap.parse_args(argv)
    stats = compute(cc.load_predictions(a.pred), max_shift=a.max_shift)
    cc.save_outputs(render(stats), a.out_dir, RECIPE_ID, stats)


if __name__ == "__main__":
    main()
```

- [ ] **Step 4: 跑绿 + 全量 + Commit**

commit message:`feat(ts-diagnose): chartbook 新图 time-shift-diagnosis——逐窗最优时移分布(平移 2 步植入精确回收 golden)`(带 Co-Authored-By 尾行)

---

### Task 5: error-acf(误差残余结构)

**Files:**
- Create: `ts-diagnose/chartbook/recipes/error-acf.md`
- Create: `ts-diagnose/chartbook/scripts/chart_error_acf.py`
- Test: `ts-diagnose/chartbook/tests/test_chart_error_acf.py`

**Interfaces:**
- Consumes: chart_common 同上;scipy.stats.chi2
- Produces: recipe id `error-acf`(category error-structure)

- [ ] **Step 1: 写 recipe**

```markdown
---
id: error-acf
category: error-structure
needs_materials: [predict, truth]
适用问题: 误差序列里还有可预测结构吗?(持续性偏差=漏了慢变量/可后处理修正)
outputs:
  json: error-acf.json
  png: error-acf.png
json_schema: >
  每模型:窗口级序列(每窗均值误差,按 window_ts 排序)的 acf(lag 1..L 曲线)、
  argmax_lag、acf1、ljung_box{stat,p,lags}、n。多步预测纪律:窗口重叠时
  低阶自相关天然存在(h 步最优残差为 MA(h−1)),判读只对超出重叠尺度的
  lag 下断言,note 记窗口步数。
bridge_hooks: >
  acf 在某 lag 有孤立峰 → 周期性残余候选(漏了该周期的驱动变量),与
  intraday-profile 的时段剖面互证;acf1 高且缓衰减 → 慢变量缺失/水平漂移
  候选,转 rolling-stability 看变点;全 lag ≈0 → 误差近白噪,系统性成分已榨干。
验证步: 逐窗均值误差植入周期 8 的余弦 → argmax_lag=8、acf[8]≥0.75、Ljung-Box p<0.01(tests/test_chart_error_acf.py)
---

# error-acf:窗口级误差自相关

## 适用问题
误差是"白噪声"还是"有结构"直接决定两件事:还能不能免费改进(后处理
校正),以及模型是否漏了慢变量/周期变量。

## CLI 与参数
```bash
python3 chartbook/scripts/chart_error_acf.py \
  --pred predictions.parquet --out-dir <workdir>/charts [--max-lag 12]
```

## JSON schema
见 frontmatter;序列 = 每 (window_ts) 全模型行的均值误差(单元池化),按时间排序;
Ljung-Box 在 lag 1..L 上算(χ² 检验),p 落 JSON。

## 判读
- `argmax_lag = P` 且 `acf[P]` 显著 → 候选:周期 P 的残余结构——对照
  数据背景确认 P 对应什么物理周期,该周期驱动变量缺失或用错;
- `acf1 ≥ 0.5` 且缓衰减 → 候选:慢变量缺失/概念漂移,转 rolling-stability;
- **窗口重叠纪律**:相邻窗口共享真值区间时低阶 lag 自相关是结构必然,
  不做病灶断言——只看超出重叠尺度的 lag。
只给候选假设;结论回 playbook 三道门。

## 验证步
40 窗、逐窗常数误差 = 3·cos(2π·widx/8)(窗内各步同值,窗间余弦周期 8)→
acf argmax_lag=8、acf[8]≈(n−8)/n=0.8、Ljung-Box p<0.01。
```

- [ ] **Step 2: 写 golden 测试(先跑红)**

```python
"""error-acf golden:逐窗均值误差=3cos(2π widx/8) → argmax_lag=8、acf[8]≈0.8。"""
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

import chart_error_acf as cea  # noqa: E402
from synth import make_long    # noqa: E402

WINDOWS = [f"2024-01-{d:02d}" for d in range(1, 31)] + \
          [f"2024-02-{d:02d}" for d in range(1, 11)]  # 40 窗


def _prep(df):
    df["window_ts"] = pd.to_datetime(df["window_ts"])
    df["err"] = df["y_pred"] - df["y_true"]
    return df


def _err(m, u, w, s):
    widx = WINDOWS.index(w)
    return 3.0 * np.cos(2 * np.pi * widx / 8.0)


def test_period_8_recovered():
    df = _prep(make_long(["A"], ["U1"], WINDOWS, 6, _err))
    a = cea.compute(df, max_lag=12)["models"]["A"]
    assert a["argmax_lag"] == 8
    assert a["acf"]["curve"]["8"] >= 0.75
    assert a["ljung_box"]["p"] < 0.01
    assert a["n"] == 40


def test_main_writes_outputs(tmp_path):
    df = make_long(["A"], ["U1"], WINDOWS, 6, _err)
    p = tmp_path / "pred.csv"
    df.to_csv(p, index=False)
    cea.main(["--pred", str(p), "--out-dir", str(tmp_path), "--max-lag", "12"])
    assert (tmp_path / "error-acf.json").exists()
    assert (tmp_path / "error-acf.png").exists()
```

Run → FAIL。

- [ ] **Step 3: 写脚本**

```python
"""error-acf:窗口级均值误差序列的自相关——误差是白噪声还是有可预测结构。"""
from __future__ import annotations

import argparse

import numpy as np
import pandas as pd
from scipy.stats import chi2

import chart_common as cc

RECIPE_ID = "error-acf"


def _acf(x: np.ndarray, max_lag: int) -> np.ndarray:
    x = x - x.mean()
    denom = float(np.dot(x, x))
    if denom < 1e-12:
        return np.zeros(max_lag)
    return np.array([float(np.dot(x[:-k], x[k:]) / denom)
                     for k in range(1, max_lag + 1)])


def compute(df: pd.DataFrame, max_lag: int = 12) -> dict:
    out = {"recipe": RECIPE_ID, "max_lag": max_lag, "models": {},
           "note": "序列=每窗均值误差(单元池化,按 window_ts 排序);"
                   "窗口重叠时低阶 lag 自相关是结构必然,判读见 recipe。"}
    for m, g in df.groupby("model"):
        ser = (g.groupby("window_ts")["err"].mean().sort_index())
        x = ser.values
        n = len(x)
        lags = list(range(1, max_lag + 1))
        rho = _acf(x, max_lag)
        lb = float(n * (n + 2) * np.sum(rho ** 2 / (n - np.array(lags))))
        p = float(chi2.sf(lb, df=max_lag))
        out["models"][str(m)] = {
            "acf": cc.curve_stats(rho, index=lags),
            "argmax_lag": int(lags[int(np.argmax(rho))]),
            "acf1": round(float(rho[0]), 4),
            "ljung_box": {"stat": round(lb, 4), "p": round(p, 6),
                          "lags": max_lag},
            "n": n, "steps_per_window": int(g["horizon_step"].max()) + 1}
    return out


def render(stats: dict):
    import matplotlib.pyplot as plt
    cc.setup_font()
    n = len(stats["models"])
    fig, axes = plt.subplots(1, n, figsize=(5 * n, 3.5), squeeze=False)
    for ax, (m, s) in zip(axes[0], stats["models"].items()):
        curve = s["acf"]["curve"]
        ks = sorted(int(k) for k in curve)
        ax.bar(ks, [curve[str(k)] for k in ks], width=0.6)
        ax.axhline(0, color="k", lw=0.5)
        nn = s["n"]
        ci = 1.96 / np.sqrt(nn) if nn > 0 else 0
        ax.axhline(ci, color="r", ls="--", lw=0.6)
        ax.axhline(-ci, color="r", ls="--", lw=0.6)
        ax.set_title(f"{m} 误差 ACF (LB p={s['ljung_box']['p']:.3g})")
        ax.set_xlabel("lag(窗)")
    return fig


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--pred", required=True)
    ap.add_argument("--out-dir", required=True)
    ap.add_argument("--max-lag", type=int, default=12)
    a = ap.parse_args(argv)
    stats = compute(cc.load_predictions(a.pred), max_lag=a.max_lag)
    cc.save_outputs(render(stats), a.out_dir, RECIPE_ID, stats)


if __name__ == "__main__":
    main()
```

- [ ] **Step 4: 跑绿 + 全量 + Commit**

commit message:`feat(ts-diagnose): chartbook 新图 error-acf——窗口级误差自相关+Ljung-Box(周期 8 植入回收 golden)`(带 Co-Authored-By 尾行)

---

### Task 6: good-bad-contrast(好/坏样本特征对比)

**Files:**
- Create: `ts-diagnose/chartbook/recipes/good-bad-contrast.md`
- Create: `ts-diagnose/chartbook/scripts/chart_good_bad_contrast.py`
- Test: `ts-diagnose/chartbook/tests/test_chart_good_bad_contrast.py`

**Interfaces:**
- Consumes: `chart_common.load_predictions/load_features/row_rmse/save_outputs/setup_font`;scipy.stats.ks_2samp
- Produces: recipe id `good-bad-contrast`(category sample-contrast)

- [ ] **Step 1: 写 recipe**

```markdown
---
id: good-bad-contrast
category: sample-contrast
needs_materials: [predict, truth, features]
适用问题: 预测最坏的窗口和最好的窗口,输入特征与上下文有什么系统性差别?
outputs:
  json: good-bad-contrast.json
  png: good-bad-contrast.png
json_schema: >
  每模型:k(每组窗口数)、features{名: {basis(quality|level), d(Cohen), ks, p,
  mean_best, mean_worst, direction}}(按 |d| 降序的 ranked 列表)、context
  (y_level/volatility/window_hour 三个通用协变量的同款对比)。f_true 全缺时
  basis 自动降级 level。
bridge_hooks: >
  某特征 quality 基 |d|≥0.8 且 KS p 小 → 该输入质量与坏样本强关联候选——
  与 feature-error-conditional 的 effect_ratio 交叉,两线一致才升假设;
  所有特征 |d| 都小但 context.volatility 分离 → 误差由目标自身动力学驱动
  (输入无辜),转 bad-window-clustering 看失败形态。
验证步: worst 组植入质量差 d≈2 真凶 + 两组同分布诱饵 → 真凶居 ranked 首、诱饵 |d|<0.2(tests/test_chart_good_bad_contrast.py)
---

# good-bad-contrast:best-K vs worst-K 特征对照

## 适用问题
"坏样本的特征有什么特性、好样本有什么特质"的直接回答:按行 RMSE 取两端
各 K 窗,逐特征对比三层——量值分布、预测质量(有 f_true 时)、通用上下文。

## CLI 与参数
```bash
python3 chartbook/scripts/chart_good_bad_contrast.py \
  --pred predictions.parquet --features features.parquet \
  --out-dir <workdir>/charts [--k 50]
```
k 默认 min(50, ⌈10% 行数⌉),不足 5 时抛 ValueError(样本太少不出对比)。

## JSON schema
见 frontmatter;每行(窗口)的特征 level=窗内 f_pred 均值、quality=窗内
|f_pred−f_true| 均值;d=(mean_worst−mean_best)/pooled_std;direction=d 的符号。

## 判读
- ranked 首位特征 basis=quality 且 |d|≥0.8 → 候选:该输入的预测质量分辨
  好坏样本——回 feature-error-conditional 看全局耦合是否同证;
- basis=level 的高 |d| 只说明"坏样本发生在该特征的某值域"(如高值段),
  是条件不是罪证——转 feature-regime-error 看制式;
- context 三项都分离而特征不分离 → 目标自身难度驱动,转 bad-window-clustering。
只给候选假设;结论回 playbook 三道门。

## 验证步
真凶特征在 worst 组 quality≈4、best 组≈0.5(合成 σ 使 d≈2);诱饵特征两组
同分布(d≈0)→ ranked[0]=真凶且 d≥1.5、诱饵 |d|<0.2 必须不上榜前二。
```

- [ ] **Step 2: 写 golden 测试(先跑红)**

```python
"""good-bad-contrast golden:真凶 quality 分离(d≥1.5)居首、同分布诱饵 |d|<0.2。"""
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

import chart_good_bad_contrast as cgb  # noqa: E402
from synth import make_long, alt       # noqa: E402

WINDOWS = [f"2024-01-{d:02d}" for d in range(1, 21)]  # 20 窗;前 10 坏后 10 好
BAD = set(WINDOWS[:10])


def _prep(df):
    df["window_ts"] = pd.to_datetime(df["window_ts"])
    df["err"] = df["y_pred"] - df["y_true"]
    return df


def _feats():
    rows = []
    for w in WINDOWS:
        widx = WINDOWS.index(w)
        for s in range(6):
            # 真凶:坏/好窗质量差 4/0.5 量级,按窗序微抖动(组内方差>0,d 分母才有意义)
            culprit_q = (4.0 + 0.1 * (widx % 3)) if w in BAD else (0.5 + 0.1 * (widx % 3))
            # 诱饵:两组近同分布(widx%3 在两组计数只差 1,d≈0.1)
            decoy_q = 1.0 + 0.2 * (widx % 3)
            for name, q in (("culprit", culprit_q), ("decoy", decoy_q)):
                rows.append({"window_ts": w, "unit_id": "U1", "feature": name,
                             "horizon_step": s, "f_pred": 10.0,
                             "f_true": 10.0 + q})
    df = pd.DataFrame(rows)
    df["window_ts"] = pd.to_datetime(df["window_ts"])
    return df


def _err(m, u, w, s):
    return alt(5.0 if w in BAD else 0.5, s)


def test_culprit_ranked_first_decoy_cleared():
    df = _prep(make_long(["A"], ["U1"], WINDOWS, 6, _err))
    st = cgb.compute(df, _feats(), k=10)
    a = st["models"]["A"]
    assert a["k"] == 10
    assert a["ranked"][0] == "culprit"
    culprit = a["features"]["culprit"]
    assert culprit["basis"] == "quality" and culprit["d"] >= 1.5
    assert culprit["direction"] == 1
    assert abs(a["features"]["decoy"]["d"]) < 0.2


def test_k_too_small_raises(tmp_path):
    df = _prep(make_long(["A"], ["U1"], WINDOWS[:4], 6, _err))
    try:
        cgb.compute(df, _feats(), k=2)
        assert False, "应抛 ValueError"
    except ValueError as e:
        assert "5" in str(e)


def test_main_writes_outputs(tmp_path):
    df = make_long(["A"], ["U1"], WINDOWS, 6, _err)
    p, f = tmp_path / "pred.csv", tmp_path / "feat.csv"
    df.to_csv(p, index=False)
    _feats().to_csv(f, index=False)
    cgb.main(["--pred", str(p), "--features", str(f),
              "--out-dir", str(tmp_path), "--k", "10"])
    assert (tmp_path / "good-bad-contrast.json").exists()
    assert (tmp_path / "good-bad-contrast.png").exists()
```

Run → FAIL。

- [ ] **Step 3: 写脚本**

```python
"""good-bad-contrast:best-K vs worst-K 窗口的特征/上下文分布对照——坏样本
的输入有什么系统性不同。"""
from __future__ import annotations

import argparse

import numpy as np
import pandas as pd
from scipy.stats import ks_2samp

import chart_common as cc

RECIPE_ID = "good-bad-contrast"
MIN_K = 5


def _contrast(worst: np.ndarray, best: np.ndarray) -> dict:
    mw, mb = float(np.mean(worst)), float(np.mean(best))
    pooled = np.sqrt((np.var(worst, ddof=1) + np.var(best, ddof=1)) / 2)
    d = (mw - mb) / pooled if pooled > 1e-12 else 0.0
    ks, p = ks_2samp(worst, best)
    return {"d": round(float(d), 4), "ks": round(float(ks), 4),
            "p": round(float(p), 6), "mean_best": round(mb, 4),
            "mean_worst": round(mw, 4),
            "direction": int(np.sign(d)) if abs(d) > 1e-12 else 0}


def compute(df: pd.DataFrame, feats: pd.DataFrame, k: int = None) -> dict:
    rr = cc.row_rmse(df)
    out = {"recipe": RECIPE_ID, "models": {},
           "note": "level=窗内 f_pred 均值;quality=窗内|f_pred−f_true|均值"
                   "(f_true 全缺时 basis 降级 level);d=(worst−best)/pooled_std。"}
    fq = feats.copy()
    fq["quality"] = (fq["f_pred"] - fq["f_true"]).abs()
    per_row = fq.groupby(["unit_id", "window_ts", "feature"]).agg(
        level=("f_pred", "mean"), quality=("quality", "mean")).reset_index()
    ctx_y = df[df["model"] == df["model"].iloc[0]]
    ctx = ctx_y.groupby(["unit_id", "window_ts"]).agg(
        y_level=("y_true", "mean"),
        volatility=("y_true", lambda v: float(np.std(np.diff(v)))),
    ).reset_index()
    ctx["window_hour"] = pd.to_datetime(ctx["window_ts"]).dt.hour.astype(float)
    for m, g in rr.groupby("model"):
        n = len(g)
        kk = k if k is not None else min(50, max(MIN_K, int(np.ceil(0.1 * n))))
        if kk < MIN_K or n < 2 * kk:
            raise ValueError(
                f"行数 {n} 不足以取两组各 {kk}(最少每组 {MIN_K});样本太少不出对比")
        g = g.sort_values("rmse")
        best = g.head(kk)[["unit_id", "window_ts"]]
        worst = g.tail(kk)[["unit_id", "window_ts"]]
        def _pick(tbl, rows, col):
            j = tbl.merge(rows, on=["unit_id", "window_ts"])
            return j[col].values
        features, ranked = {}, []
        for fname, ft in per_row.groupby("feature"):
            has_true = ft["quality"].notna().any()
            basis = "quality" if has_true else "level"
            wv = _pick(ft, worst, basis)
            bv = _pick(ft, best, basis)
            if len(wv) < MIN_K or len(bv) < MIN_K:
                continue
            features[str(fname)] = {"basis": basis,
                                    **_contrast(wv, bv)}
        ranked = sorted(features, key=lambda f: -abs(features[f]["d"]))
        context = {}
        for col in ("y_level", "volatility", "window_hour"):
            context[col] = _contrast(_pick(ctx, worst, col), _pick(ctx, best, col))
        out["models"][str(m)] = {"k": kk, "features": features,
                                 "ranked": ranked, "context": context}
    return out


def render(stats: dict):
    import matplotlib.pyplot as plt
    cc.setup_font()
    n = len(stats["models"])
    fig, axes = plt.subplots(1, n, figsize=(6 * n, 4), squeeze=False)
    for ax, (m, s) in zip(axes[0], stats["models"].items()):
        names = s["ranked"]
        ds = [s["features"][f]["d"] for f in names]
        ax.barh(range(len(names)), ds)
        ax.set_yticks(range(len(names))), ax.set_yticklabels(names, fontsize=8)
        ax.axvline(0, color="k", lw=0.5)
        ax.invert_yaxis()
        ax.set_xlabel("Cohen's d (worst−best)")
        ax.set_title(f"{m} 好/坏样本特征分离度 (k={s['k']})")
    return fig


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--pred", required=True)
    ap.add_argument("--features", required=True)
    ap.add_argument("--out-dir", required=True)
    ap.add_argument("--k", type=int, default=None)
    a = ap.parse_args(argv)
    stats = compute(cc.load_predictions(a.pred), cc.load_features(a.features),
                    k=a.k)
    cc.save_outputs(render(stats), a.out_dir, RECIPE_ID, stats)


if __name__ == "__main__":
    main()
```

- [ ] **Step 4: 跑绿 + 全量 + Commit**

commit message:`feat(ts-diagnose): chartbook 新图 good-bad-contrast——best/worst-K 特征对照(真凶+诱饵双植入 golden)`(带 Co-Authored-By 尾行)

---

### Task 7: bad-window-clustering(坏窗形态聚类)

**Files:**
- Create: `ts-diagnose/chartbook/recipes/bad-window-clustering.md`
- Create: `ts-diagnose/chartbook/scripts/chart_bad_window_clustering.py`
- Test: `ts-diagnose/chartbook/tests/test_chart_bad_window_clustering.py`

**Interfaces:**
- Consumes: `chart_common.row_rmse` 等;sklearn.cluster.KMeans、sklearn.metrics.silhouette_score
- Produces: recipe id `bad-window-clustering`(category sample-contrast)

- [ ] **Step 1: 写 recipe**

```markdown
---
id: bad-window-clustering
category: sample-contrast
needs_materials: [predict, truth]
适用问题: 坏样本是一种失败模式还是几种?各占多少?
outputs:
  json: bad-window-clustering.json
  png: bad-window-clustering.png
json_schema: >
  每模型:top_n、chosen_k、silhouette_by_k、seed、clusters[{share, n,
  mean_rmse, prototype(归一化质心曲线,≤24 点)}]。簇不做领域命名——质心
  形状事实归 JSON,命名交运行时判读结合 intake 背景。
bridge_hooks: >
  单簇占比 ≥0.8 → 单一失败模式候选,对照 worst-points 标签看是哪类形态;
  多簇均衡 → 多机制并存,逐簇回 error-breakdown 查时间聚集;某簇 mean_rmse
  显著更高 → 优先攻那一簇。
验证步: 植入升/降两种确定形状的坏窗 → chosen_k=2、成员精确分离、share 各 0.5(tests/test_chart_bad_window_clustering.py)
---

# bad-window-clustering:worst-N 窗口形态聚类

## 适用问题
worst-points 给"点"贴标签,本图给"整窗曲线"聚类——坏样本的真值形态
是一种还是几种失败模式,决定修一个机制还是修几个。

## CLI 与参数
```bash
python3 chartbook/scripts/chart_bad_window_clustering.py \
  --pred predictions.parquet --out-dir <workdir>/charts \
  [--top-n 50] [--seed 0]
```
k 在 2..4 由轮廓系数选;seed 显式落 JSON(_recipe-spec §5.3 种子例外)。

## JSON schema
见 frontmatter;每窗曲线 z 归一化(σ≈0 的平坦窗跳过并计入 skipped_flat),
曲线重采样到 ≤24 点后聚类。

## 判读
- `chosen_k=1 语义`(silhouette 全低)本图不产——k≥2 强制,share 极不均衡
  (≥0.8)时按"单一模式"判读;
- 各簇 prototype 的形状差异(升/降/尖峰)用 curve 数字描述,领域命名结合
  intake 背景在判读层给;
- 簇间 mean_rmse 差异大 → 优先修误差最重的簇对应机制。
只给候选假设;结论回 playbook 三道门。

## 验证步
12 个坏窗(误差幅度 5):6 窗 y=s 升形 + 6 窗 y=23−s 降形;8 个好窗(0.1)
→ top-12 恰为坏窗、chosen_k=2、两簇成员精确分离、share 各 0.5。
```

- [ ] **Step 2: 写 golden 测试(先跑红)**

```python
"""bad-window-clustering golden:升/降两种坏窗形态 → k=2、成员精确分离。"""
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

import chart_bad_window_clustering as cbw  # noqa: E402
from synth import make_long, alt           # noqa: E402

UP = [f"2024-01-{d:02d}" for d in range(1, 7)]     # 升形坏窗
DOWN = [f"2024-01-{d:02d}" for d in range(7, 13)]  # 降形坏窗
GOOD = [f"2024-01-{d:02d}" for d in range(13, 21)]
WINDOWS = UP + DOWN + GOOD


def _y(w, u, s):
    if w in UP:
        return float(s)
    if w in DOWN:
        return float(23 - s)
    return 10.0


def _err(m, u, w, s):
    return alt(5.0 if w in UP + DOWN else 0.1, s)


def _prep(df):
    df["window_ts"] = pd.to_datetime(df["window_ts"])
    df["err"] = df["y_pred"] - df["y_true"]
    return df


def test_two_shapes_recovered():
    df = _prep(make_long(["A"], ["U1"], WINDOWS, 24, _err, y_fn=_y))
    st = cbw.compute(df, top_n=12, seed=0)
    a = st["models"]["A"]
    assert a["chosen_k"] == 2
    assert a["seed"] == 0
    shares = sorted(c["share"] for c in a["clusters"])
    assert np.allclose(shares, [0.5, 0.5])
    protos = [c["prototype"] for c in a["clusters"]]
    trends = sorted(np.sign(p[-1] - p[0]) for p in protos)
    assert trends == [-1.0, 1.0]  # 一升一降


def test_flat_windows_skipped():
    df = _prep(make_long(["A"], ["U1"], GOOD, 24, lambda m, u, w, s: alt(5.0, s),
                         y_fn=lambda w, u, s: 10.0))
    st = cbw.compute(df, top_n=8, seed=0)
    assert st["models"]["A"]["skipped_flat"] == 8
    assert st["models"]["A"]["clusters"] == []


def test_main_writes_outputs(tmp_path):
    df = make_long(["A"], ["U1"], WINDOWS, 24, _err, y_fn=_y)
    p = tmp_path / "pred.csv"
    df.to_csv(p, index=False)
    cbw.main(["--pred", str(p), "--out-dir", str(tmp_path),
              "--top-n", "12", "--seed", "0"])
    assert (tmp_path / "bad-window-clustering.json").exists()
    assert (tmp_path / "bad-window-clustering.png").exists()
```

Run → FAIL。

- [ ] **Step 3: 写脚本**

```python
"""bad-window-clustering:worst-N 窗口真值曲线归一化聚类——坏样本是几种失败模式。"""
from __future__ import annotations

import argparse

import numpy as np
import pandas as pd
from sklearn.cluster import KMeans
from sklearn.metrics import silhouette_score

import chart_common as cc

RECIPE_ID = "bad-window-clustering"
MAX_POINTS = 24


def _curve(y: np.ndarray):
    """z 归一化 + 重采样 ≤MAX_POINTS;平坦窗返回 None。"""
    sd = float(np.std(y))
    if sd < 1e-9:
        return None
    z = (y - np.mean(y)) / sd
    if len(z) > MAX_POINTS:
        idx = np.linspace(0, len(z) - 1, MAX_POINTS).round().astype(int)
        z = z[idx]
    return z


def compute(df: pd.DataFrame, top_n: int = 50, seed: int = 0) -> dict:
    rr = cc.row_rmse(df)
    out = {"recipe": RECIPE_ID, "top_n": top_n, "models": {},
           "note": "每窗 y_true z 归一化后 k-means;k∈2..4 由轮廓系数选;"
                   "σ≈0 平坦窗跳过(skipped_flat);簇命名交判读层。"}
    truth = df[df["model"] == df["model"].iloc[0]]
    for m, g in rr.groupby("model"):
        worst = g.sort_values("rmse").tail(top_n)
        curves, keys, rmses, skipped = [], [], [], 0
        for _, row in worst.iterrows():
            gw = truth[(truth["unit_id"] == row["unit_id"]) &
                       (truth["window_ts"] == row["window_ts"])]
            gw = gw.sort_values("horizon_step")
            z = _curve(gw["y_true"].values)
            if z is None:
                skipped += 1
                continue
            curves.append(z), keys.append(
                f"{row['unit_id']}|{row['window_ts']}"), rmses.append(row["rmse"])
        entry = {"chosen_k": None, "silhouette_by_k": {}, "seed": seed,
                 "clusters": [], "skipped_flat": skipped, "n_clustered": len(curves)}
        if len(curves) >= 6:
            X = np.vstack(curves)
            best_k, best_s, best_labels = None, -np.inf, None
            for k in (2, 3, 4):
                if k >= len(X):
                    continue
                km = KMeans(n_clusters=k, n_init=10, random_state=seed).fit(X)
                s = float(silhouette_score(X, km.labels_))
                entry["silhouette_by_k"][str(k)] = round(s, 4)
                if s > best_s:
                    best_k, best_s, best_labels = k, s, km.labels_
            entry["chosen_k"] = best_k
            for ci in range(best_k):
                mask = best_labels == ci
                entry["clusters"].append({
                    "share": round(float(np.mean(mask)), 4),
                    "n": int(mask.sum()),
                    "mean_rmse": round(float(np.mean(np.array(rmses)[mask])), 4),
                    "members": [keys[i] for i in np.where(mask)[0]],
                    "prototype": [round(float(v), 4)
                                  for v in X[mask].mean(axis=0)]})
        out["models"][str(m)] = entry
    return out


def render(stats: dict):
    import matplotlib.pyplot as plt
    cc.setup_font()
    n = len(stats["models"])
    fig, axes = plt.subplots(1, n, figsize=(6 * n, 4), squeeze=False)
    for ax, (m, s) in zip(axes[0], stats["models"].items()):
        for i, c in enumerate(s["clusters"]):
            ax.plot(c["prototype"], lw=1.5,
                    label=f"簇{i} share={c['share']:.2f} rmse={c['mean_rmse']:.2f}")
        ax.set_title(f"{m} 坏窗形态原型 (k={s['chosen_k']})")
        ax.set_xlabel("归一化窗内位置"), ax.set_ylabel("z(y_true)")
        if s["clusters"]:
            ax.legend(fontsize=8)
    return fig


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--pred", required=True)
    ap.add_argument("--out-dir", required=True)
    ap.add_argument("--top-n", type=int, default=50)
    ap.add_argument("--seed", type=int, default=0)
    a = ap.parse_args(argv)
    stats = compute(cc.load_predictions(a.pred), top_n=a.top_n, seed=a.seed)
    cc.save_outputs(render(stats), a.out_dir, RECIPE_ID, stats)


if __name__ == "__main__":
    main()
```

- [ ] **Step 4: 跑绿 + 全量 + Commit**

commit message:`feat(ts-diagnose): chartbook 新图 bad-window-clustering——坏窗形态聚类(双形状植入精确分离 golden)`(带 Co-Authored-By 尾行)

---

### Task 8: feature-regime-error(特征制式条件误差)

**Files:**
- Create: `ts-diagnose/chartbook/recipes/feature-regime-error.md`
- Create: `ts-diagnose/chartbook/scripts/chart_feature_regime_error.py`
- Test: `ts-diagnose/chartbook/tests/test_chart_feature_regime_error.py`

**Interfaces:**
- Consumes: chart_common;sklearn KMeans/silhouette_score
- Produces: recipe id `feature-regime-error`(category input-side)

- [ ] **Step 1: 写 recipe**

```markdown
---
id: feature-regime-error
category: input-side
needs_materials: [predict, truth, features]
适用问题: 按多变量输入状态聚出的"制式"里,哪个制式下误差最重?占比多少?
outputs:
  json: feature-regime-error.json
  png: feature-regime-error.png
json_schema: >
  chosen_k、silhouette_by_k、seed、regimes[{share, n, centroid{特征:原始
  单位均值}, rmse_by_model, }]、worst_best_ratio_by_model。制式不做领域
  命名——质心事实归 JSON,命名交运行时判读结合 intake 背景。
bridge_hooks: >
  某制式 rmse 比值 ≥2 且占比可观 → 模型对该输入状态失配候选——与
  feature-error-conditional 的单特征分箱互证(多变量制式 vs 单变量条件);
  全制式误差均衡 → 输入状态不是分辨维度,转 temporal/结构类图。
验证步: 两个分离制式、一制式 3 倍误差 → chosen_k=2、质心与比值精确回收(tests/test_chart_feature_regime_error.py)
---

# feature-regime-error:多变量制式条件误差

## 适用问题
单特征分箱(feature-error-conditional)看不到"多个输入共同定义的状态"。
本图对窗口级特征向量聚类,回答"误差集中在哪种输入状态"。

## CLI 与参数
```bash
python3 chartbook/scripts/chart_feature_regime_error.py \
  --pred predictions.parquet --features features.parquet \
  --out-dir <workdir>/charts [--seed 0]
```
k 在 2..4 由轮廓系数选;seed 落 JSON。

## JSON schema
见 frontmatter;窗口特征向量 = 每特征窗内 f_pred 均值,聚类前逐特征标准化,
centroid 以原始单位报告。

## 判读
- worst_best_ratio ≥ 2 的模型 → 候选:该模型对高误差制式的输入状态失配;
  对照 centroid 数字与 intake 背景给制式起名后再入结论;
- 所有模型在同一制式同倍率变差 → 数据侧难度(该状态本身难预测),不是
  单模型失配——与 model-error-correlation 互证;
- share < 0.05 的小制式不下断言(n 太小)。
只给候选假设;结论回 playbook 三道门。

## 验证步
两特征、两制式(质心 (0,0) vs (10,10))、制式 2 植入 3 倍误差 →
chosen_k=2、centroid 精确回收、worst_best_ratio≈3。
```

- [ ] **Step 2: 写 golden 测试(先跑红)**

```python
"""feature-regime-error golden:双制式质心 (0,0)/(10,10)、制式 2 三倍误差 → 精确回收。"""
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

import chart_feature_regime_error as cfr  # noqa: E402
from synth import make_long, alt          # noqa: E402

R1 = [f"2024-01-{d:02d}" for d in range(1, 11)]
R2 = [f"2024-01-{d:02d}" for d in range(11, 21)]
WINDOWS = R1 + R2


def _prep(df):
    df["window_ts"] = pd.to_datetime(df["window_ts"])
    df["err"] = df["y_pred"] - df["y_true"]
    return df


def _feats():
    rows = []
    for w in WINDOWS:
        base = 0.0 if w in R1 else 10.0
        for s in range(6):
            for name in ("fa", "fb"):
                rows.append({"window_ts": w, "unit_id": "U1", "feature": name,
                             "horizon_step": s, "f_pred": base})
    df = pd.DataFrame(rows)
    df["window_ts"] = pd.to_datetime(df["window_ts"])
    return df


def _err(m, u, w, s):
    return alt(3.0 if w in R2 else 1.0, s)


def test_regimes_recovered():
    df = _prep(make_long(["A"], ["U1"], WINDOWS, 6, _err))
    st = cfr.compute(df, _feats(), seed=0)
    assert st["chosen_k"] == 2
    regs = sorted(st["regimes"], key=lambda r: r["centroid"]["fa"])
    assert np.isclose(regs[0]["centroid"]["fa"], 0.0)
    assert np.isclose(regs[1]["centroid"]["fa"], 10.0)
    assert np.isclose(regs[0]["share"], 0.5) and np.isclose(regs[1]["share"], 0.5)
    assert np.isclose(regs[0]["rmse_by_model"]["A"], 1.0)
    assert np.isclose(regs[1]["rmse_by_model"]["A"], 3.0)
    assert np.isclose(st["worst_best_ratio_by_model"]["A"], 3.0)


def test_main_writes_outputs(tmp_path):
    df = make_long(["A"], ["U1"], WINDOWS, 6, _err)
    p, f = tmp_path / "pred.csv", tmp_path / "feat.csv"
    df.to_csv(p, index=False)
    _feats().to_csv(f, index=False)
    cfr.main(["--pred", str(p), "--features", str(f),
              "--out-dir", str(tmp_path), "--seed", "0"])
    assert (tmp_path / "feature-regime-error.json").exists()
    assert (tmp_path / "feature-regime-error.png").exists()
```

Run → FAIL。

- [ ] **Step 3: 写脚本**

```python
"""feature-regime-error:窗口级多变量特征聚类出"制式",各制式条件误差——
误差集中在哪种输入状态。"""
from __future__ import annotations

import argparse

import warnings

import numpy as np
import pandas as pd
from sklearn.cluster import KMeans
from sklearn.exceptions import ConvergenceWarning
from sklearn.metrics import silhouette_score

import chart_common as cc

RECIPE_ID = "feature-regime-error"


def compute(df: pd.DataFrame, feats: pd.DataFrame, seed: int = 0) -> dict:
    vec = (feats.groupby(["unit_id", "window_ts", "feature"])["f_pred"].mean()
           .unstack("feature").dropna())
    if len(vec) < 8:
        raise ValueError(f"可聚类窗口数 {len(vec)} < 8,不足以分制式")
    X = vec.values
    mu, sd = X.mean(axis=0), X.std(axis=0)
    sd[sd < 1e-12] = 1.0
    Xz = (X - mu) / sd
    sil, best = {}, (None, -np.inf, None)
    for k in (2, 3, 4):
        if k >= len(Xz):
            continue
        with warnings.catch_warnings():
            # k > 真实制式数时重复点必然簇合并——固有告警,局部消音防污染测试输出
            warnings.simplefilter("ignore", ConvergenceWarning)
            km = KMeans(n_clusters=k, n_init=10, random_state=seed).fit(Xz)
            s = float(silhouette_score(Xz, km.labels_))
        sil[str(k)] = round(s, 4)
        if s > best[1]:
            best = (k, s, km.labels_)
    k, _, labels = best
    rr = cc.row_rmse(df)
    lab = pd.Series(labels, index=vec.index, name="regime")
    rr = rr.join(lab, on=["unit_id", "window_ts"]).dropna(subset=["regime"])
    out = {"recipe": RECIPE_ID, "chosen_k": int(k), "silhouette_by_k": sil,
           "seed": seed, "regimes": [], "worst_best_ratio_by_model": {},
           "note": "制式=窗口级 f_pred 均值向量标准化后 k-means;centroid 为"
                   "原始单位;制式命名交判读层结合 intake 背景。"}
    for ci in range(k):
        members = vec.index[labels == ci]
        sub = rr[rr["regime"] == ci]
        out["regimes"].append({
            "share": round(float(np.mean(labels == ci)), 4),
            "n": int((labels == ci).sum()),
            "centroid": {c: round(float(v), 4)
                         for c, v in vec.loc[members].mean().items()},
            "rmse_by_model": {str(m): round(float(g["rmse"].mean()), 4)
                              for m, g in sub.groupby("model")}})
    for m in rr["model"].unique():
        vals = [r["rmse_by_model"].get(str(m)) for r in out["regimes"]
                if r["rmse_by_model"].get(str(m)) is not None]
        if vals and min(vals) > 1e-12:
            out["worst_best_ratio_by_model"][str(m)] = round(
                max(vals) / min(vals), 4)
    return out


def render(stats: dict):
    import matplotlib.pyplot as plt
    cc.setup_font()
    fig, ax = plt.subplots(figsize=(7, 4))
    regimes = stats["regimes"]
    models = sorted({m for r in regimes for m in r["rmse_by_model"]})
    x = np.arange(len(regimes))
    w = 0.8 / max(1, len(models))
    for i, m in enumerate(models):
        ax.bar(x + i * w, [r["rmse_by_model"].get(m, 0) for r in regimes],
               width=w, label=m)
    ax.set_xticks(x + 0.4 - w / 2)
    ax.set_xticklabels([f"制式{i}\nshare={r['share']:.2f}"
                        for i, r in enumerate(regimes)], fontsize=8)
    ax.set_ylabel("行 RMSE 均值")
    ax.set_title(f"feature-regime-error (k={stats['chosen_k']})")
    ax.legend(fontsize=8)
    return fig


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--pred", required=True)
    ap.add_argument("--features", required=True)
    ap.add_argument("--out-dir", required=True)
    ap.add_argument("--seed", type=int, default=0)
    a = ap.parse_args(argv)
    stats = compute(cc.load_predictions(a.pred), cc.load_features(a.features),
                    seed=a.seed)
    cc.save_outputs(render(stats), a.out_dir, RECIPE_ID, stats)


if __name__ == "__main__":
    main()
```

- [ ] **Step 4: 跑绿 + 全量 + Commit**

commit message:`feat(ts-diagnose): chartbook 新图 feature-regime-error——多变量制式条件误差(双制式植入精确回收 golden)`(带 Co-Authored-By 尾行)

---

### Task 9: baseline-skill(朴素基线技能阶梯)+ chart_common.detect_period_steps

**Files:**
- Modify: `ts-diagnose/chartbook/scripts/chart_common.py`(文件末尾加 detect_period_steps)
- Modify: `ts-diagnose/chartbook/tests/test_chart_common.py`(加 detect_period_steps 测试)
- Create: `ts-diagnose/chartbook/recipes/baseline-skill.md`
- Create: `ts-diagnose/chartbook/scripts/chart_baseline_skill.py`
- Test: `ts-diagnose/chartbook/tests/test_chart_baseline_skill.py`

**Interfaces:**
- Consumes: chart_common
- Produces: recipe id `baseline-skill`(category model-comparison);`chart_common.detect_period_steps(values, max_lag) -> int | None`(Plan 3 lookback-decay 复用)

- [ ] **Step 1: chart_common 加周期检测(先写测试跑红)**

`test_chart_common.py` 末尾加:

```python
def test_detect_period_steps_sine():
    import numpy as np
    x = 10 + 5 * np.sin(2 * np.pi * np.arange(96) / 24)
    assert cc.detect_period_steps(x, max_lag=48) == 24


def test_detect_period_steps_aperiodic_returns_none():
    import numpy as np
    x = np.arange(50, dtype=float)  # 纯趋势,无周期
    assert cc.detect_period_steps(x, max_lag=20) is None
```

`chart_common.py` 末尾加:

```python
def detect_period_steps(values, max_lag: int = 96, threshold: float = 0.5):
    """去趋势后 ACF 的**局部极大值**里取最高峰作主周期(步数)。
    注意不能用全局 argmax:正弦的 ACF 在低阶 lag 本来就高(cos 因子),
    全局 argmax 会答 lag≈2;周期表现为 ACF 先降后升的局部峰。
    峰值 < threshold 或无局部峰时返回 None。
    baseline-skill 的季节基线与 lookback 类图的 lag 桶共用。"""
    x = np.asarray(values, float)
    x = x[np.isfinite(x)]
    if len(x) < 6:
        return None
    x = x - np.polyval(np.polyfit(np.arange(len(x)), x, 1), np.arange(len(x)))
    denom = float(np.dot(x, x))
    if denom < 1e-12:
        return None
    kmax = min(max_lag, len(x) // 2)
    rho = np.array([float(np.dot(x[:-k], x[k:]) / denom)
                    for k in range(1, kmax + 1)])
    best_lag, best_rho = None, threshold
    for i in range(1, len(rho) - 1):
        if rho[i] > rho[i - 1] and rho[i] > rho[i + 1] and rho[i] > best_rho:
            best_lag, best_rho = i + 1, float(rho[i])
    return best_lag
```

Run: `python3 -m pytest ts-diagnose/chartbook/tests/test_chart_common.py -q` → PASS。

- [ ] **Step 2: 写 recipe**

```markdown
---
id: baseline-skill
category: model-comparison
needs_materials: [predict, truth]
适用问题: 模型比"抄上次/抄同相位/抄均值"好多少?有没有模型退化成抄 persistence?
outputs:
  json: baseline-skill.json
  png: baseline-skill.png
json_schema: >
  period_steps(来源:CLI 或 ACF 自动检测,null=无周期)、baselines{persistence/
  seasonal_naive?/climatology: rmse}、每模型{rmse, skill_vs_persistence,
  skill_vs_seasonal?, skill_vs_climatology, corr_with_truth,
  corr_with_persistence, copies_persistence(bool)}、n_scored(基线可算的行数)。
bridge_hooks: >
  skill≤0 的模型 → 不如朴素基线,存在性存疑——查它是不是 copies_persistence
  (corr_with_persistence>corr_with_truth);全模型 skill 都低 → 该数据可预测
  上限本身低(与 oracle-gap 互证);seasonal skill 高但 persistence skill 低 →
  模型只学到了周期形。
验证步: 一模型恰等于季节朴素 → skill_vs_seasonal=0;半误差模型 → 0.5;抄 persistence 模型 → copies_persistence=true(tests/test_chart_baseline_skill.py)
---

# baseline-skill:朴素基线技能阶梯

## 适用问题
全图库唯一的朴素参照系:skill = 1 − RMSE_model/RMSE_baseline。回答"模型
值不值得存在"以及"深度模型是否退化成抄 persistence"。

## CLI 与参数
```bash
python3 chartbook/scripts/chart_baseline_skill.py \
  --pred predictions.parquet --out-dir <workdir>/charts \
  [--period-steps 96] [--freq 15min]
```
period 未给时用 detect_period_steps 对真值序列自动检测;检测不到 →
seasonal 基线缺省(JSON 记 null),只算 persistence 与 climatology。

## JSON schema
见 frontmatter;真值全局序列按 target_ts=window_ts+step·freq 建;persistence
基线 = 发起时刻真值 y(window_ts);seasonal = y(target−period);climatology =
全局均值。基线值缺失的行跳过,分母为 n_scored。

## 判读
- `skill_vs_persistence ≤ 0` → 候选:模型无增值——先查 copies_persistence,
  是则模型在"抄输入",转 revision-stability 看翻新形态;
- persistence skill 低而 seasonal skill 高 → 只学到周期形,突变段必差,
  与 worst-points 的转折占比互证;
- 全模型 skill 均低且 oracle-gap 也小 → 数据可预测上限低,不是模型问题。
只给候选假设;结论回 playbook 三道门。

## 验证步
y=100·widx+s(日间水平位移+日内斜坡)、period=24 显式传入 → 抄 seasonal 的
模型 skill_vs_seasonal=0;误差减半模型 =0.5;恰抄 persistence 的模型
copies_persistence=true。
```

- [ ] **Step 3: 写 golden 测试(先跑红)**

```python
"""baseline-skill golden:y=100·widx+s;seasonal 基线 RMSE=100;三模型分别
验 skill=0 / 0.5 / copies_persistence。"""
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

import chart_baseline_skill as cbs  # noqa: E402
from synth import make_long, alt    # noqa: E402

WINDOWS = ["2024-01-01", "2024-01-02", "2024-01-03", "2024-01-04"]


def _y(w, u, s):
    return 100.0 * WINDOWS.index(w) + float(s)


def _err(m, u, w, s):
    if m == "seasonal_copy":       # y_pred = y(target−24) = y − 100
        return -100.0
    if m == "half_err":            # RMSE 50 → skill_vs_seasonal = 0.5
        return alt(50.0, s)
    if m == "persist_copy":        # y_pred = y(window 发起时刻) = 100·widx
        return -float(s)
    raise AssertionError(m)


def _prep(df):
    df["window_ts"] = pd.to_datetime(df["window_ts"])
    df["err"] = df["y_pred"] - df["y_true"]
    return df


def _mk():
    return _prep(make_long(["seasonal_copy", "half_err", "persist_copy"],
                           ["U1"], WINDOWS, 24, _err, y_fn=_y))


def test_seasonal_skills():
    st = cbs.compute(_mk(), period_steps=24, freq="1h")
    assert np.isclose(st["baselines"]["seasonal_naive"], 100.0)
    ms = st["models"]
    assert np.isclose(ms["seasonal_copy"]["skill_vs_seasonal"], 0.0)
    assert np.isclose(ms["half_err"]["skill_vs_seasonal"], 0.5)


def test_persistence_copy_flagged():
    st = cbs.compute(_mk(), period_steps=24, freq="1h")
    m = st["models"]["persist_copy"]
    assert m["copies_persistence"] is True
    # 阴性对照用 seasonal_copy:pred=y−100 与 truth 相关恒为 1(平移不变),
    # 必大于与 persistence 的相关 → 稳健地不触发
    assert st["models"]["seasonal_copy"]["copies_persistence"] is False


def test_no_period_degrades():
    st = cbs.compute(_mk(), period_steps=None, freq="1h", auto_detect=False)
    assert st["period_steps"] is None
    assert "seasonal_naive" not in st["baselines"]
    assert "skill_vs_seasonal" not in st["models"]["half_err"]


def test_main_writes_outputs(tmp_path):
    df = make_long(["half_err"], ["U1"], WINDOWS, 24,
                   lambda m, u, w, s: alt(50.0, s), y_fn=_y)
    p = tmp_path / "pred.csv"
    df.to_csv(p, index=False)
    cbs.main(["--pred", str(p), "--out-dir", str(tmp_path),
              "--period-steps", "24", "--freq", "1h"])
    assert (tmp_path / "baseline-skill.json").exists()
    assert (tmp_path / "baseline-skill.png").exists()
```

Run → FAIL。

- [ ] **Step 4: 写脚本**

```python
"""baseline-skill:persistence/季节朴素/气候均值三基线的技能阶梯——模型比
"抄"好多少、有没有模型退化成抄 persistence。"""
from __future__ import annotations

import argparse

import numpy as np
import pandas as pd

import chart_common as cc

RECIPE_ID = "baseline-skill"


def _rmse(x):
    return float(np.sqrt(np.mean(np.square(x))))


def compute(df: pd.DataFrame, period_steps=None, freq: str = "15min",
            auto_detect: bool = True) -> dict:
    d = df.copy()
    d["target_ts"] = d["window_ts"] + d["horizon_step"] * pd.Timedelta(freq)
    first = d["model"].iloc[0]
    truth = (d[d["model"] == first]
             .drop_duplicates(["unit_id", "target_ts"])
             .set_index(["unit_id", "target_ts"])["y_true"])
    if period_steps is None and auto_detect:
        u0 = d["unit_id"].iloc[0]
        ser = truth.loc[u0].sort_index().values
        period_steps = cc.detect_period_steps(ser)
    step = pd.Timedelta(freq)
    keys = list(zip(d["unit_id"], d["window_ts"]))
    d["base_persistence"] = [truth.get(k, np.nan) for k in keys]
    if period_steps:
        keys_s = list(zip(d["unit_id"], d["target_ts"] - period_steps * step))
        d["base_seasonal"] = [truth.get(k, np.nan) for k in keys_s]
    clim = float(truth.mean())
    out = {"recipe": RECIPE_ID, "period_steps": period_steps,
           "freq": freq, "baselines": {}, "models": {},
           "note": "skill=1−RMSE_model/RMSE_baseline,基线可算的行上对齐比较;"
                   "copies_persistence: corr(pred,persistence)>corr(pred,truth)。"}
    scored = d.dropna(subset=["base_persistence"])
    out["n_scored"] = int(len(scored) / max(1, d["model"].nunique()))
    rmse_p = _rmse(scored["base_persistence"] - scored["y_true"])
    out["baselines"]["persistence"] = round(rmse_p, 4)
    if period_steps and d["base_seasonal"].notna().any():
        ds = d.dropna(subset=["base_seasonal"])
        rmse_s = _rmse(ds["base_seasonal"] - ds["y_true"])
        out["baselines"]["seasonal_naive"] = round(rmse_s, 4)
    else:
        rmse_s = None
    out["baselines"]["climatology"] = round(_rmse(truth.values - clim), 4)
    for m, g in d.groupby("model"):
        rmse_m = _rmse(g["err"])
        gp = g.dropna(subset=["base_persistence"])
        entry = {"rmse": round(rmse_m, 4)}
        def _skill(base_rmse):
            return round(1 - rmse_m / base_rmse, 4) if base_rmse and base_rmse > 1e-12 else None
        entry["skill_vs_persistence"] = _skill(
            _rmse(gp["base_persistence"] - gp["y_true"]) if len(gp) else None)
        if rmse_s is not None:
            gs = g.dropna(subset=["base_seasonal"])
            entry["skill_vs_seasonal"] = _skill(
                _rmse(gs["base_seasonal"] - gs["y_true"]) if len(gs) else None)
        entry["skill_vs_climatology"] = _skill(out["baselines"]["climatology"])
        ct = float(np.corrcoef(g["y_pred"], g["y_true"])[0, 1])
        cp = float(np.corrcoef(gp["y_pred"], gp["base_persistence"])[0, 1]) \
            if len(gp) > 2 else np.nan
        entry["corr_with_truth"] = round(ct, 4)
        entry["corr_with_persistence"] = round(cp, 4) if np.isfinite(cp) else None
        entry["copies_persistence"] = bool(np.isfinite(cp) and cp > ct)
        out["models"][str(m)] = entry
    return out


def render(stats: dict):
    import matplotlib.pyplot as plt
    cc.setup_font()
    fig, ax = plt.subplots(figsize=(7, 4))
    models = list(stats["models"])
    skills = ["skill_vs_persistence", "skill_vs_seasonal", "skill_vs_climatology"]
    labels = {"skill_vs_persistence": "vs persistence",
              "skill_vs_seasonal": "vs 季节朴素",
              "skill_vs_climatology": "vs 均值"}
    x = np.arange(len(models))
    present = [s for s in skills if any(s in stats["models"][m] for m in models)]
    w = 0.8 / max(1, len(present))
    for i, sk in enumerate(present):
        vals = [stats["models"][m].get(sk) or 0.0 for m in models]
        ax.bar(x + i * w, vals, width=w, label=labels[sk])
    ax.axhline(0, color="k", lw=0.8)
    ax.set_xticks(x + 0.4 - w / 2), ax.set_xticklabels(models, fontsize=8)
    ax.set_ylabel("skill = 1 − RMSE/RMSE_base")
    ax.set_title("baseline-skill 基线技能阶梯")
    ax.legend(fontsize=8)
    return fig


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--pred", required=True)
    ap.add_argument("--out-dir", required=True)
    ap.add_argument("--period-steps", type=int, default=None)
    ap.add_argument("--freq", default="15min")
    a = ap.parse_args(argv)
    stats = compute(cc.load_predictions(a.pred),
                    period_steps=a.period_steps, freq=a.freq)
    cc.save_outputs(render(stats), a.out_dir, RECIPE_ID, stats)


if __name__ == "__main__":
    main()
```

- [ ] **Step 5: 跑绿 + 全量 + Commit**

commit message:`feat(ts-diagnose): chartbook 新图 baseline-skill——朴素基线技能阶梯+detect_period_steps 公共件(三模型植入 golden)`(带 Co-Authored-By 尾行)

---

### Task 10: model-rank-significance(排名显著性)

**Files:**
- Create: `ts-diagnose/chartbook/recipes/model-rank-significance.md`
- Create: `ts-diagnose/chartbook/scripts/chart_model_rank_significance.py`
- Test: `ts-diagnose/chartbook/tests/test_chart_model_rank_significance.py`

**Interfaces:**
- Consumes: chart_common;scipy.stats.norm
- Produces: recipe id `model-rank-significance`(category model-comparison,needs_models 2)

- [ ] **Step 1: 写 recipe**

```markdown
---
id: model-rank-significance
category: model-comparison
needs_materials: [predict, truth]
needs_models: 2
适用问题: 模型排名的差异是真差异还是噪声?哪些模型统计上不可区分?
outputs:
  json: model-rank-significance.json
  png: model-rank-significance.png
json_schema: >
  avg_ranks(每模型平均秩,损失=行 RMSE,秩按行取、并列取均秩)、cd
  (Nemenyi 临界差,α=0.05)、groups(秩差≤cd 的不可区分组,含最优组
  best_group)、dm(成对{stat,p};损失差按 window_ts 排序、Newey-West HAC
  方差,d 恒 0 时 p=1、方差退化且均值≠0 时 p=0 并记 degenerate)、n_rows。
bridge_hooks: >
  焦点模型与次优在同一 group 且 dm p 大 → 排名差异不可靠,结论只能说
  "无显著差异"——喂给 model-comparison playbook 的准入门;分离显著 →
  差距真实,转 worst-slice-compare 查差在哪。
验证步: 恒 3 倍误差对 → dm p<0.05 且秩分离;同款模型对 → 同组且 p=1(tests/test_chart_model_rank_significance.py)
---

# model-rank-significance:平均秩 + 临界差 + DM 检验

## 适用问题
多模型对比的最后一道统计门:平均秩差超过 Nemenyi 临界差才算"排名可信",
成对 DM 检验(HAC 方差,容忍误差自相关)给逐对 p 值。

## CLI 与参数
```bash
python3 chartbook/scripts/chart_model_rank_significance.py \
  --pred predictions.parquet --out-dir <workdir>/charts
```
< 2 模型抛 ValueError(§5.5)。

## JSON schema
见 frontmatter;损失矩阵 = 每 (unit_id,window_ts) 行的行 RMSE,只保留全模型
齐的行;Nemenyi q_α 表内置 k=2..10。

## 判读
- best_group 只有一个成员且它对第二名 dm p<0.05 → 排名可信,可下"谁最优";
- best_group 多成员 → 只能说"这几个不可区分地并列最优",禁止点单一冠军;
- dm.degenerate 出现 → 损失差没有变化(克隆/恒差),对照数据核实而非下结论。
只给候选假设;结论回 playbook 三道门。

## 验证步
A 恒 1 倍、B 恒 3+0.5·(widx%2) 倍误差 → 每行 A 胜,avg_rank A=1、B=2,
40 窗下秩差 1 > cd≈0.31,dm p<0.05;C 与 D 同款(恒同损失)→ 同组、p=1。
```

- [ ] **Step 2: 写 golden 测试(先跑红)**

```python
"""model-rank-significance golden:恒差对显著分离;克隆对不可区分。"""
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

import chart_model_rank_significance as cmr  # noqa: E402
from synth import make_long, alt             # noqa: E402

WINDOWS = [f"2024-01-{d:02d}" for d in range(1, 31)] + \
          [f"2024-02-{d:02d}" for d in range(1, 11)]  # 40 窗


def _err(m, u, w, s):
    widx = WINDOWS.index(w)
    if m == "A":
        return alt(1.0, s)
    if m == "B":
        return alt(3.0 + 0.5 * (widx % 2), s)
    if m in ("C", "D"):
        return alt(2.0, s)
    raise AssertionError(m)


def _prep(df):
    df["window_ts"] = pd.to_datetime(df["window_ts"])
    df["err"] = df["y_pred"] - df["y_true"]
    return df


def test_separated_pair():
    df = _prep(make_long(["A", "B"], ["U1"], WINDOWS, 6, _err))
    st = cmr.compute(df)
    assert st["avg_ranks"]["A"] == 1.0 and st["avg_ranks"]["B"] == 2.0
    assert 1.0 > st["cd"]
    assert st["dm"]["A|B"]["p"] < 0.05
    assert st["best_group"] == ["A"]


def test_clone_pair_indistinguishable():
    df = _prep(make_long(["C", "D"], ["U1"], WINDOWS, 6, _err))
    st = cmr.compute(df)
    assert st["avg_ranks"]["C"] == 1.5 and st["avg_ranks"]["D"] == 1.5
    assert st["dm"]["C|D"]["p"] == 1.0
    assert sorted(st["best_group"]) == ["C", "D"]


def test_single_model_raises():
    df = _prep(make_long(["A"], ["U1"], WINDOWS[:4], 6, _err))
    try:
        cmr.compute(df)
        assert False, "应抛 ValueError"
    except ValueError as e:
        assert "2" in str(e)


def test_main_writes_outputs(tmp_path):
    df = make_long(["A", "B"], ["U1"], WINDOWS, 6, _err)
    p = tmp_path / "pred.csv"
    df.to_csv(p, index=False)
    cmr.main(["--pred", str(p), "--out-dir", str(tmp_path)])
    assert (tmp_path / "model-rank-significance.json").exists()
    assert (tmp_path / "model-rank-significance.png").exists()
```

Run → FAIL。

- [ ] **Step 3: 写脚本**

```python
"""model-rank-significance:平均秩+Nemenyi 临界差+成对 Diebold-Mariano(HAC)——
模型排名差异是真是噪声。"""
from __future__ import annotations

import argparse
import itertools

import numpy as np
import pandas as pd
from scipy.stats import norm

import chart_common as cc

RECIPE_ID = "model-rank-significance"
# Nemenyi q_alpha (α=0.05), k=2..10
Q_ALPHA = {2: 1.959964, 3: 2.343701, 4: 2.569032, 5: 2.727774,
           6: 2.849705, 7: 2.948319, 8: 3.030879, 9: 3.102173, 10: 3.163684}


def _dm(d: np.ndarray) -> dict:
    """损失差序列(已按时间排序)的 DM 检验;HAC(Bartlett)方差,lag=⌊n^{1/3}⌋。"""
    n = len(d)
    mean = float(np.mean(d))
    if np.allclose(d, d[0]):
        if abs(mean) < 1e-12:
            return {"stat": 0.0, "p": 1.0, "degenerate": True}
        return {"stat": None, "p": 0.0, "degenerate": True}
    dc = d - mean
    L = max(1, int(np.floor(n ** (1 / 3))))
    g0 = float(np.dot(dc, dc)) / n
    var = g0
    for l in range(1, L + 1):
        gl = float(np.dot(dc[:-l], dc[l:])) / n
        var += 2 * (1 - l / (L + 1)) * gl
    var = max(var, 1e-12)
    stat = mean / np.sqrt(var / n)
    p = float(2 * norm.sf(abs(stat)))
    return {"stat": round(float(stat), 4), "p": round(p, 6),
            "degenerate": False}


def compute(df: pd.DataFrame) -> dict:
    models = sorted(df["model"].unique().tolist())
    k = len(models)
    if k < 2:
        raise ValueError("model-rank-significance 需要 ≥2 模型(§5.5)")
    if k > 10:
        raise ValueError("Nemenyi q 表内置至 k=10")
    rr = cc.row_rmse(df)
    mat = rr.pivot_table(index=["unit_id", "window_ts"], columns="model",
                         values="rmse").dropna()
    mat = mat.sort_index(level="window_ts")
    n = len(mat)
    ranks = mat.rank(axis=1, method="average")
    avg = ranks.mean()
    cd = float(Q_ALPHA[k] * np.sqrt(k * (k + 1) / (6.0 * n)))
    dm = {}
    for a, b in itertools.combinations(models, 2):
        dm[f"{a}|{b}"] = _dm((mat[a] - mat[b]).values)
    best = avg.idxmin()
    best_group = sorted([m for m in models if avg[m] - avg[best] <= cd])
    out = {"recipe": RECIPE_ID, "n_rows": n, "cd": round(cd, 4),
           "avg_ranks": {m: round(float(avg[m]), 4) for m in models},
           "dm": dm, "best_group": best_group,
           "note": "损失=行 RMSE(全模型齐的行);cd=Nemenyi α=0.05;"
                   "dm 为成对 HAC 方差 DM 检验,克隆/恒差记 degenerate。"}
    return out


def render(stats: dict):
    import matplotlib.pyplot as plt
    cc.setup_font()
    fig, axes = plt.subplots(2, 1, figsize=(7, 6),
                             gridspec_kw={"height_ratios": [1, 1.2]})
    ax = axes[0]
    items = sorted(stats["avg_ranks"].items(), key=lambda kv: kv[1])
    names = [kv[0] for kv in items]
    vals = [kv[1] for kv in items]
    ax.errorbar(vals, range(len(names)), xerr=stats["cd"] / 2, fmt="o",
                capsize=4)
    ax.set_yticks(range(len(names))), ax.set_yticklabels(
        [n + (" ★" if n in stats["best_group"] else "") for n in names])
    ax.invert_yaxis()
    ax.set_xlabel(f"平均秩(横杠=cd/2,cd={stats['cd']})")
    ax.set_title("model-rank-significance")
    ax2 = axes[1]
    pairs = list(stats["dm"])
    ps = [stats["dm"][p]["p"] for p in pairs]
    ax2.barh(range(len(pairs)), ps)
    ax2.axvline(0.05, color="r", ls="--", lw=0.8)
    ax2.set_yticks(range(len(pairs))), ax2.set_yticklabels(pairs, fontsize=8)
    ax2.set_xlabel("DM p 值(虚线=0.05)")
    fig.tight_layout()
    return fig


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--pred", required=True)
    ap.add_argument("--out-dir", required=True)
    a = ap.parse_args(argv)
    stats = compute(cc.load_predictions(a.pred))
    cc.save_outputs(render(stats), a.out_dir, RECIPE_ID, stats)


if __name__ == "__main__":
    main()
```

- [ ] **Step 4: 跑绿 + 全量 + Commit**

commit message:`feat(ts-diagnose): chartbook 新图 model-rank-significance——平均秩+Nemenyi CD+DM 检验(分离/克隆双植入 golden)`(带 Co-Authored-By 尾行)

---

### Task 11: revision-stability(翻新刺猬图)

**Files:**
- Create: `ts-diagnose/chartbook/recipes/revision-stability.md`
- Create: `ts-diagnose/chartbook/scripts/chart_revision_stability.py`
- Test: `ts-diagnose/chartbook/tests/test_chart_revision_stability.py`

**Interfaces:**
- Consumes: chart_common
- Produces: recipe id `revision-stability`(category temporal-stability)

- [ ] **Step 1: 写 recipe**

```markdown
---
id: revision-stability
category: temporal-stability
needs_materials: [predict, truth]
适用问题: 对同一目标时刻,随发起窗推进(lead 缩短)预测是收敛到真值还是来回跳?
outputs:
  json: revision-stability.json
  png: revision-stability.png
json_schema: >
  每模型:n_targets(≥2 窗覆盖的目标时刻数)、coverage_hist、smapc(逐对
  翻新 2|Δ|/(|p1|+|p2|) 的均值)、convergence_ratio(最短 lead |err| 均值 /
  最长 lead |err| 均值)、sample_trajectories(≤6 个目标:lead→pred 序列+
  y_true,画刺猬图用)。无任何目标被 ≥2 窗覆盖时抛 ValueError(结构性不适用)。
bridge_hooks: >
  smapc 高且 convergence_ratio≈1 → 翻新抖动不收敛候选(输入翻新噪声直通/
  模型对输入过敏),与 pv 特征侧翻新类分析呼应——输入侧有对照数据时先查输入;
  smapc 低但 convergence_ratio≈1 → 稳定地错(系统性偏差),转 theil-decomposition;
  轨迹集体平坦贴均值 → 回归均值塌缩候选,与 pp-calibration 压缩互证。
验证步: 收敛轨迹(每翻新近 1)与跳变轨迹(交替 ±2)双模型 → smapc 排序与 convergence_ratio 阈值回收;单覆盖数据抛 ValueError(tests/test_chart_revision_stability.py)
---

# revision-stability:以目标时刻为锚的翻新稳定性

## 适用问题
长表里同一 target_ts 被多个发起窗覆盖时,"历次预测怎么变"是完全没被
其他图利用的轴:收敛=健康;跳变=翻新噪声直通;平坦贴均值=塌缩。

## CLI 与参数
```bash
python3 chartbook/scripts/chart_revision_stability.py \
  --pred predictions.parquet --out-dir <workdir>/charts [--freq 15min]
```

## JSON schema
见 frontmatter;lead(步数)= horizon_step;同 (model,unit,target_ts) 按 lead
降序排列构成翻新轨迹。

## 判读
- `smapc` 模型间对比:高者对输入翻新更敏感——有特征对照数据时转特征侧
  翻新分析确认输入是否本身在跳;
- `convergence_ratio < 0.5` → 临近显著变准(正常);≈1 → 临近不变准,
  lead 信息没被利用或误差是系统性的;
- sample_trajectories 供人工看形态(收敛/跳变/塌缩),数字结论以 smapc 与
  ratio 为准。
只给候选假设;结论回 playbook 三道门。

## 验证步
6 个 1h 间隔发起窗、6 步窗长 → 中段目标时刻被多窗覆盖;converge 模型
pred=y+lead(每翻新净变 1)、jumpy 模型 pred=y+(lead 奇偶 ? +2 : −2)
(每翻新跳 4)→ smapc_jumpy > 2·smapc_converge、convergence_ratio_converge<0.5;
单窗数据(无重叠覆盖)抛 ValueError。
```

- [ ] **Step 2: 写 golden 测试(先跑红)**

```python
"""revision-stability golden:收敛 vs 跳变双模型;单覆盖抛 ValueError。"""
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

import chart_revision_stability as crs  # noqa: E402
from synth import make_long             # noqa: E402

WINDOWS = [f"2024-01-01 {h:02d}:00:00" for h in range(6)]  # 1h 间隔 6 窗


def _err(m, u, w, s):
    lead = s  # horizon_step 即 lead
    if m == "converge":
        return float(lead)
    if m == "jumpy":
        return 2.0 if lead % 2 == 0 else -2.0
    raise AssertionError(m)


def _prep(df):
    df["window_ts"] = pd.to_datetime(df["window_ts"])
    df["err"] = df["y_pred"] - df["y_true"]
    return df


def test_converge_vs_jumpy():
    df = _prep(make_long(["converge", "jumpy"], ["U1"], WINDOWS, 6, _err))
    st = crs.compute(df, freq="1h")
    c, j = st["models"]["converge"], st["models"]["jumpy"]
    assert c["n_targets"] >= 2 and j["n_targets"] >= 2
    assert j["smapc"] > 2 * c["smapc"]
    assert c["convergence_ratio"] < 0.5
    assert len(c["sample_trajectories"]) >= 1


def test_no_overlap_raises():
    df = _prep(make_long(["converge"], ["U1"],
                         ["2024-01-01", "2024-02-01"], 6, _err))
    try:
        crs.compute(df, freq="1h")
        assert False, "应抛 ValueError"
    except ValueError as e:
        assert "覆盖" in str(e)


def test_main_writes_outputs(tmp_path):
    df = make_long(["converge"], ["U1"], WINDOWS, 6, _err)
    p = tmp_path / "pred.csv"
    df.to_csv(p, index=False)
    crs.main(["--pred", str(p), "--out-dir", str(tmp_path), "--freq", "1h"])
    assert (tmp_path / "revision-stability.json").exists()
    assert (tmp_path / "revision-stability.png").exists()
```

Run → FAIL。

- [ ] **Step 3: 写脚本**

```python
"""revision-stability:以目标时刻为锚,历次发起窗对它的预测轨迹——收敛、
跳变还是塌缩。"""
from __future__ import annotations

import argparse

import numpy as np
import pandas as pd

import chart_common as cc

RECIPE_ID = "revision-stability"
MAX_SAMPLES = 6


def compute(df: pd.DataFrame, freq: str = "15min") -> dict:
    d = df.copy()
    d["target_ts"] = d["window_ts"] + d["horizon_step"] * pd.Timedelta(freq)
    out = {"recipe": RECIPE_ID, "freq": freq, "models": {},
           "note": "lead=horizon_step;轨迹按 lead 降序;smapc=逐对翻新"
                   "2|Δ|/(|p1|+|p2|) 均值;convergence_ratio=最短/最长 lead "
                   "的 |err| 均值比。"}
    any_covered = False
    for m, g in d.groupby("model"):
        cov = g.groupby(["unit_id", "target_ts"]).size()
        covered = cov[cov >= 2]
        entry = {"n_targets": int(len(covered)),
                 "coverage_hist": {str(int(k)): int(v) for k, v in
                                   cov.value_counts().sort_index().items()}}
        if len(covered) == 0:
            out["models"][str(m)] = entry
            continue
        any_covered = True
        smapc_vals, first_err, last_err, samples = [], [], [], []
        gg = g.set_index(["unit_id", "target_ts"]).sort_index()
        for key in covered.index:
            traj = gg.loc[key].sort_values("horizon_step", ascending=False)
            preds = traj["y_pred"].values
            for p1, p2 in zip(preds[:-1], preds[1:]):
                den = abs(p1) + abs(p2)
                if den > 1e-12:
                    smapc_vals.append(2 * abs(p2 - p1) / den)
            errs = (traj["y_pred"] - traj["y_true"]).abs().values
            first_err.append(errs[0])   # 最长 lead
            last_err.append(errs[-1])   # 最短 lead
            if len(samples) < MAX_SAMPLES:
                samples.append({
                    "unit_id": str(key[0]), "target_ts": str(key[1]),
                    "leads": [int(v) for v in traj["horizon_step"]],
                    "preds": [round(float(v), 4) for v in preds],
                    "y_true": round(float(traj["y_true"].iloc[0]), 4)})
        fe, le = float(np.mean(first_err)), float(np.mean(last_err))
        entry.update({
            "smapc": round(float(np.mean(smapc_vals)), 6) if smapc_vals else None,
            "convergence_ratio": round(le / fe, 4) if fe > 1e-12 else None,
            "sample_trajectories": samples})
        out["models"][str(m)] = entry
    if not any_covered:
        raise ValueError(
            "无任何目标时刻被 ≥2 个发起窗覆盖——数据不含翻新结构,本图结构性"
            "不适用(需要重叠预测窗)")
    return out


def render(stats: dict):
    import matplotlib.pyplot as plt
    cc.setup_font()
    n = len(stats["models"])
    fig, axes = plt.subplots(1, n, figsize=(6 * n, 4), squeeze=False)
    for ax, (m, s) in zip(axes[0], stats["models"].items()):
        for tr in s.get("sample_trajectories", []):
            ax.plot(tr["leads"], tr["preds"], marker="o", ms=3, lw=1, alpha=0.7)
            ax.axhline(tr["y_true"], color="k", lw=0.4, ls=":")
        ax.invert_xaxis()
        ax.set_xlabel("lead(步,右=临近)"), ax.set_ylabel("预测值")
        sm = s.get("smapc")
        ax.set_title(f"{m} 翻新轨迹 (sMAPC={sm if sm is not None else 'n/a'})")
    return fig


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--pred", required=True)
    ap.add_argument("--out-dir", required=True)
    ap.add_argument("--freq", default="15min")
    a = ap.parse_args(argv)
    stats = compute(cc.load_predictions(a.pred), freq=a.freq)
    cc.save_outputs(render(stats), a.out_dir, RECIPE_ID, stats)


if __name__ == "__main__":
    main()
```

- [ ] **Step 4: 跑绿 + 全量 + Commit**

commit message:`feat(ts-diagnose): chartbook 新图 revision-stability——目标时刻锚定的翻新轨迹(收敛/跳变双植入 golden)`(带 Co-Authored-By 尾行)

---

## 收尾核对(并入 Task 11 的最后一步,不单独成任务)

- [ ] `python3 -m pytest ts-diagnose/ -q` 全绿(conform 闸覆盖 11 个新 recipe 的 category/结构)
- [ ] `git log --oneline` 确认 11 个 feat commit 各自独立

## 后续(本文件不含)

- **Plan 3/4**:predict_adapter 契约 + attribution_common + 归因 3 张(global-attribution / lookback-decay / local-waterfall);
- **Plan 4/4**:orient 选择门按类分组呈现 + build_index.py + true-vs-pred-scatter 加 Mincer-Zarnowitz + CHANGELOG 收口。
