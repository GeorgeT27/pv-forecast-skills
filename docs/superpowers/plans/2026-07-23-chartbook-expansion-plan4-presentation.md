# Chartbook 扩展 Plan 4/4:呈现层(归组呈现+索引+MZ 增强+收口) 实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 完成 chartbook 28 图扩展的呈现层——orient 图表选择门按类别分组、build_index.py 生成只索引实际产物的 INDEX.md、true-vs-pred-scatter 加 Mincer-Zarnowitz 检验,并清掉 Plan 3 延后清单、同步 engine-core.md 与 CHANGELOG 收口。

**Architecture:** 归组只在呈现层(PNG 平铺不动、零 golden 扰动):engine_common 加 `recipe_category()`,orient 给声明图打类别标签、可加画池按类别分组;build_index.py 扫产物目录按 CATEGORY_IDS 分节。MZ 检验以纯解析构造(配对 ±d 正交噪声)做零随机精确 golden。

**Tech Stack:** Python 3(现有环境),scipy.stats.f,yaml,matplotlib,pytest。

## Global Constraints

- **禁止改动 numpy/pandas/sklearn/shap 版本**(numpy==1.26.4, shap==0.44.1 钉死)。
- 领域中立:recipe id 与 frontmatter 不得含 weather/station/solar/irradiance/pv(词边界,conform 闸自动查)。
- JSON 一等产物、PNG 副产物;compute()/render() 分离;`main(argv=None)` 可注入。
- golden:零随机精确解析回收,或显式种子落 JSON;本计划全部 golden 零随机。
- PNG 文件保持平铺(不动现有脚本输出路径,零 golden 扰动),归组只在呈现层(spec §6)。
- 测试在 `-W error` 下通过;Task 1 完成后全套件应 **0 warnings**(OpenMP 豁免收进 conftest)。
- 实施者提交时**只 `git add` 任务点名的文件,禁止 `git add -A` / `git add .`**(工作区有用户未跟踪文件)。
- 28 张是库存非必画清单;build_index 只索引实际产物,不为没画的图留空位(spec §8)。

---

### Task 1: Plan 3 延后清单一次提交清扫

**Files:**
- Modify: `ts-diagnose/chartbook/scripts/attribution_common.py`(死 import、退化分支标签)
- Modify: `ts-diagnose/chartbook/scripts/chart_global_attribution.py`(死 import、双 RNG 注释)
- Modify: `ts-diagnose/chartbook/scripts/chart_lookback_decay.py`(死 import)
- Modify: `ts-diagnose/chartbook/scripts/chart_local_waterfall.py`(死 import)
- Create: `ts-diagnose/chartbook/tests/conftest.py`(OpenMP 豁免集中)
- Modify: `ts-diagnose/chartbook/tests/test_chart_global_attribution.py`(删 pytestmark)
- Modify: `ts-diagnose/chartbook/tests/test_attribution_common.py`(退化分支断言)
- Modify: `ts-diagnose/chartbook/tests/test_chart_lookback_decay.py`(ref≈0 测试)
- Modify: `ts-diagnose/chartbook/tests/test_chart_local_waterfall.py`(负 φ 渲染测试)

**Interfaces:**
- Consumes: attribution_common.background_set / chart_lookback_decay.compute / chart_local_waterfall.render 现有签名(全部不变)。
- Produces: `background_set` 返回的 meta["method"] 在退化分支(k≥完整窗数,未聚类)变为 `"all-windows"`;聚类分支仍 `"kmeans-medoid"`。无测试断言旧标签(已核查),但依赖方如有需知悉。

- [ ] **Step 1: 写三个失败测试**

在 `ts-diagnose/chartbook/tests/test_attribution_common.py` 末尾追加:

```python
def test_background_set_degenerate_labels_all_windows():
    """k≥完整窗数时未跑聚类,meta.method 不得谎称 kmeans-medoid。"""
    feats = _feats_two_clusters()          # 该文件已有夹具:8 个完整窗
    _series, meta = ac.background_set(feats, k=99, seed=0)
    assert meta["method"] == "all-windows"
    assert meta["k"] == 8
    _series2, meta2 = ac.background_set(feats, k=2, seed=0)
    assert meta2["method"] == "kmeans-medoid"
```

在 `ts-diagnose/chartbook/tests/test_chart_lookback_decay.py` 末尾追加:

```python
CONST_ADAPTER = '''\
import pandas as pd
CAPABILITIES = {"perturb_features": False, "perturb_lookback": True,
                "torch_module": False, "lookback_steps": 4, "features": []}
HORIZON = 2
def predict(requests):
    rows = []
    for i, r in enumerate(requests):
        for s in range(HORIZON):
            rows.append({"request_idx": i, "unit_id": r["unit_id"],
                         "window_ts": r["window_ts"], "horizon_step": s,
                         "y_pred": 5.0})
    return pd.DataFrame(rows)
'''


def test_mask_insensitive_adapter_ref_zero(tmp_path):
    """对遮蔽完全不敏感的模型:全桶 Δ=0 → weights=None 不归一;
    per-instance ref≈0 分支 → h*=0(此前无覆盖,Plan3 终审 T4b)。"""
    p = tmp_path / "predict_adapter.py"
    p.write_text(CONST_ADAPTER)
    st = cld.compute(_pred(), ac.load_adapter(p), max_windows=2, seed=0,
                     max_calls=5000, per_instance=True)
    assert st["weights"] is None
    assert st["short_term_share"] is None
    assert st["per_instance"]["median"] == 0
    assert set(st["per_instance"]["hist"]) == {"0"}
```

在 `ts-diagnose/chartbook/tests/test_chart_local_waterfall.py` 末尾追加:

```python
def test_render_negative_phi_cumulative_positions():
    """负 φ 瀑布条:bar(bottom=cum, height=v<0) 应占据 [cum+v, cum] 区间,
    下一条从 cum+v 起(Plan3 终审 T5b 补覆盖)。"""
    stats = {"rows": [{"window_ts": "2024-01-01T00:00:00", "unit_id": "U1",
                       "rmse_actual": 2.0, "base_value": 5.0,
                       "check_sum": 3.0, "basis": "f_true",
                       "contributions": {"fa": -3.0, "fb": 1.0}}],
             "k": 1, "model": "A"}
    fig = clw.render(stats)
    ax = fig.axes[0]
    bars = [p for p in ax.patches]
    assert len(bars) == 2
    # 排序按 |φ| 降序:fa(-3) 先画,从 base_value=5.0 起,占 [2,5]
    y0, h0 = bars[0].get_y(), bars[0].get_height()
    assert np.isclose(min(y0, y0 + h0), 2.0) and np.isclose(max(y0, y0 + h0), 5.0)
    # fb(+1) 从 cum=2.0 起,占 [2,3]
    y1, h1 = bars[1].get_y(), bars[1].get_height()
    assert np.isclose(min(y1, y1 + h1), 2.0) and np.isclose(max(y1, y1 + h1), 3.0)
    import matplotlib.pyplot as plt
    plt.close(fig)
```

注:若该测试文件缺 `import numpy as np`,补上。

- [ ] **Step 2: 跑新测试确认失败**

```bash
python -m pytest ts-diagnose/chartbook/tests/test_attribution_common.py::test_background_set_degenerate_labels_all_windows ts-diagnose/chartbook/tests/test_chart_lookback_decay.py::test_mask_insensitive_adapter_ref_zero ts-diagnose/chartbook/tests/test_chart_local_waterfall.py::test_render_negative_phi_cumulative_positions -q -W error
```

预期:第一个 FAIL(method 仍是 kmeans-medoid);后两个应 PASS 或 FAIL——如后两个直接 PASS,说明是纯补覆盖测试,属预期,继续。

- [ ] **Step 3: 实施修改**

`attribution_common.py`:
1. 删除 `background_set` 内的 `import pandas as pd` 行(函数体内未用 pd,确认后删;若删后 NameError 则说明有用,保留并在报告说明)。
2. meta 行改为:

```python
    meta = {"method": "kmeans-medoid" if len(idx) < len(vec) else "all-windows",
            "k": int(k), "seed": int(seed),
            "windows": [f"{u}|{w}" for u, w in chosen]}
```

`chart_global_attribution.py`:
1. 顶部 `import pandas as pd` 若全文件未用 pd 则删除(用 `grep -n "pd\."` 确认)。
2. 在 `rng = np.random.RandomState(seed)` 与 `np.random.seed(seed)` 两行处加注释(一处即可,放在 `np.random.seed(seed)` 行上方):

```python
    # 双重播种非冗余:rng 喂本脚本自己的采样;shap KernelExplainer 内部走全局
    # np.random——两者都不种任一侧就不可复现(Plan3 T3 评审备注)。
```

`chart_lookback_decay.py` 与 `chart_local_waterfall.py`:顶部 `import pandas as pd` 未用则删(同样 grep 确认;`chart_lookback_decay.py` 第 8 行、`chart_local_waterfall.py` 第 8 行)。

新建 `ts-diagnose/chartbook/tests/conftest.py`:

```python
"""chartbook 测试公共 conftest:集中豁免本环境唯一允许的警告——
anaconda 下 shap(Intel OpenMP)与 sklearn(LLVM OpenMP)同进程双载的
RuntimeWarning(环境产物,Plan3 T3 裁定接受)。此外任何警告都该在 -W error
下炸,新警告=回归。"""
import pytest

_OMP = "ignore:(?s).*Found Intel OpenMP.*LLVM OpenMP.*:RuntimeWarning"


def pytest_collection_modifyitems(items):
    for item in items:
        item.add_marker(pytest.mark.filterwarnings(_OMP))
```

`test_chart_global_attribution.py`:删除文件头的 `pytestmark = pytest.mark.filterwarnings(...)` 两行及其解释注释段(docstring 里关于 pytestmark 的句子改为指向 conftest.py);若删后 `pytest` import 不再被使用则一并清理。

- [ ] **Step 4: 跑测试确认通过**

```bash
python -m pytest ts-diagnose/chartbook/tests/ -q -W error
```

预期:全部通过,**0 warnings**(conftest 豁免吸收 OpenMP)。若仍有 warning,逐条列入报告——不许静默扩大豁免。

- [ ] **Step 5: 提交**

```bash
git add ts-diagnose/chartbook/scripts/attribution_common.py ts-diagnose/chartbook/scripts/chart_global_attribution.py ts-diagnose/chartbook/scripts/chart_lookback_decay.py ts-diagnose/chartbook/scripts/chart_local_waterfall.py ts-diagnose/chartbook/tests/conftest.py ts-diagnose/chartbook/tests/test_chart_global_attribution.py ts-diagnose/chartbook/tests/test_attribution_common.py ts-diagnose/chartbook/tests/test_chart_lookback_decay.py ts-diagnose/chartbook/tests/test_chart_local_waterfall.py
git commit -m "chore(ts-diagnose): Plan3 延后清单清扫——死 import/退化标签/双RNG注释/conftest 收 OpenMP 豁免/ref≈0 与负φ补覆盖"
```

---

### Task 2: orient 图表选择门按类别分组

**Files:**
- Modify: `ts-diagnose/scripts/engine_common.py`(加 `recipe_category`)
- Modify: `ts-diagnose/scripts/orient.py`(声明图打类别标签、可加画池分组)
- Modify: `ts-diagnose/scripts/tests/test_charts_decl.py`(扩展断言)

**Interfaces:**
- Consumes: `_recipe_frontmatter(rid)`、`CATEGORY_IDS`、`addable_recipes(fm, cfg)`(签名全部不变)。
- Produces: `engine_common.recipe_category(rid) -> str`(返回 frontmatter category,缺失返回 `"uncategorized"`)。orient 输出格式变化:声明图行尾加 `[<category>]`;可加画池按 CATEGORY_IDS 顺序分组,组头 `[<category>]`。

- [ ] **Step 1: 写失败测试**

`ts-diagnose/scripts/tests/test_charts_decl.py` 追加:

```python
def test_recipe_category_reads_frontmatter():
    assert ec.recipe_category("error-breakdown") == "error-structure"
    assert ec.recipe_category("global-attribution") == "attribution"


def test_orient_groups_addable_pool_by_category(tmp_path):
    """可加画池按类别分组:出现有池类别的组头;无一图满足材料的类别不出现。"""
    _pb(tmp_path, "    charts: [error-breakdown]")
    pb_path = str(tmp_path / "playbooks" / "demo-charts" / "playbook.md")
    cfg = {"playbook": pb_path,
           "materials": {"predict": {"status": "present"},
                         "truth": {"status": "present"}}}
    (tmp_path / "diagnose_config.json").write_text(json.dumps(cfg))
    proc = subprocess.run(
        [sys.executable, ORIENT], cwd=tmp_path, capture_output=True, text=True)
    assert proc.returncode == 0, proc.stderr
    out = proc.stdout
    assert "[error-structure]" in out          # intraday-profile 等在池,组头出现
    assert "[sample-contrast]" in out          # worst-points 等只需 predict+truth
    assert "[attribution]" not in out          # 归因图需 serving_api+features,不满足
    # 声明图行带类别标签
    assert "error-breakdown" in out
```

并修改现有 `test_orient_prints_chart_availability`,在末尾追加一行断言:

```python
    assert "[error-structure]" in out  # 声明图行尾类别标签
```

- [ ] **Step 2: 跑测试确认失败**

```bash
python -m pytest ts-diagnose/scripts/tests/test_charts_decl.py -q -W error
```

预期:新增 2 个测试 FAIL(`recipe_category` 不存在 / 输出无组头)。

- [ ] **Step 3: 实施**

`engine_common.py` 在 `recipe_min_models` 之后加:

```python
def recipe_category(rid):
    """chartbook recipe 的类别(orient 分组呈现用;缺失回退 uncategorized)。"""
    return str(_recipe_frontmatter(rid).get("category") or "uncategorized")
```

`orient.py` 两处改动。声明图行(现第 122-126 行)改为:

```python
                cat = ec.recipe_category(rid)
                if missing:
                    print(f"    📊 {rid} ✗缺材料:{','.join(missing)}"
                          f"（自动跳过，不阻塞）[{cat}]")
                else:
                    print(f"    📊 {rid} ✓可画 [{cat}]")
```

可加画池(现第 133-137 行)改为:

```python
        if addable:
            print("    ➕ 可加画（未声明、材料已满足，可跨 playbook 任取，按类别分组）：")
            by_cat = {}
            for rid, needs, min_models in addable:
                by_cat.setdefault(ec.recipe_category(rid), []).append(
                    (rid, needs, min_models))
            for cat in list(ec.CATEGORY_IDS) + ["uncategorized"]:
                if cat not in by_cat:
                    continue
                print(f"      [{cat}]")
                for rid, needs, min_models in by_cat[cat]:
                    mnote = (f"，需 ≥{min_models} 模型（单模型勿加）"
                             if min_models >= 2 else "")
                    print(f"        {rid}（需 {','.join(needs) or '无'}{mnote}）")
```

- [ ] **Step 4: 跑测试确认通过**

```bash
python -m pytest ts-diagnose/scripts/tests/ -q -W error
```

预期:全部 PASS(含既有 orient e2e——若其它测试对旧缩进/文案有精确断言而红,按新格式修断言,不改功能)。

- [ ] **Step 5: 提交**

```bash
git add ts-diagnose/scripts/engine_common.py ts-diagnose/scripts/orient.py ts-diagnose/scripts/tests/test_charts_decl.py
git commit -m "feat(ts-diagnose): 图表选择门按类别分组——recipe_category+声明图类别标签+可加画池分组(spec §6)"
```

---

### Task 3: build_index.py 产物索引生成器

**Files:**
- Create: `ts-diagnose/chartbook/scripts/build_index.py`
- Create: `ts-diagnose/chartbook/tests/test_build_index.py`

**Interfaces:**
- Consumes: `engine_common.CATEGORY_IDS`(path-insert 引入,先例见 `tests/test_recipes_conform.py`);recipe frontmatter 的 `category` 与 `适用问题` 字段;`charts` 目录里 `<recipe-id>.json` / `<recipe-id>.png` 的产物命名约定(`chart_common.save_outputs` 固定此约定)。
- Produces: CLI `python3 build_index.py --charts-dir <dir>` → 写 `<dir>/INDEX.md`;库函数 `build(charts_dir: Path) -> str`(测试直接调)。

- [ ] **Step 1: 写失败测试**

`ts-diagnose/chartbook/tests/test_build_index.py`:

```python
"""build_index golden:只索引实际产物、按类别分节、适用问题+关键描述符摘录、
未识别 json 单列不归组、无 PNG 如实标注。"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

import build_index as bi  # noqa: E402


def _mk(tmp_path, rid, stats, png=True):
    (tmp_path / f"{rid}.json").write_text(
        json.dumps(stats, ensure_ascii=False), encoding="utf-8")
    if png:
        (tmp_path / f"{rid}.png").write_bytes(b"\x89PNG\r\n")


def test_groups_by_category_and_excludes_unplotted(tmp_path):
    _mk(tmp_path, "true-vs-pred-scatter",
        {"recipe": "true-vs-pred-scatter", "note": "x",
         "models": {"A": {"slope": 0.8, "r2": 0.99}}})
    _mk(tmp_path, "worst-points", {"recipe": "worst-points", "top_n": 20})
    text = bi.build(tmp_path)
    assert "## error-structure" in text
    assert "## sample-contrast" in text
    assert "## attribution" not in text            # 没画的类别不留空位
    assert "### true-vs-pred-scatter" in text
    assert "![true-vs-pred-scatter](true-vs-pred-scatter.png)" in text
    assert "适用问题" in text                        # recipe frontmatter 摘录
    assert "top_n=20" in text                       # 顶层标量描述符
    assert "slope=0.8" in text                      # 顶层无标量时下钻 models


def test_unknown_json_listed_not_grouped(tmp_path):
    _mk(tmp_path, "true-vs-pred-scatter",
        {"recipe": "true-vs-pred-scatter", "models": {"A": {"slope": 1.0}}})
    _mk(tmp_path, "my-adhoc-analysis", {"whatever": 1})
    text = bi.build(tmp_path)
    assert "未识别产物" in text
    assert "my-adhoc-analysis.json" in text
    assert "### my-adhoc-analysis" not in text


def test_missing_png_noted(tmp_path):
    _mk(tmp_path, "worst-points", {"recipe": "worst-points", "top_n": 5},
        png=False)
    text = bi.build(tmp_path)
    assert "无 PNG" in text


def test_main_writes_index(tmp_path):
    _mk(tmp_path, "worst-points", {"recipe": "worst-points", "top_n": 5})
    bi.main(["--charts-dir", str(tmp_path)])
    assert (tmp_path / "INDEX.md").exists()
    assert "worst-points" in (tmp_path / "INDEX.md").read_text(encoding="utf-8")
```

- [ ] **Step 2: 跑测试确认失败**

```bash
python -m pytest ts-diagnose/chartbook/tests/test_build_index.py -q -W error
```

预期:FAIL(module 不存在)。

- [ ] **Step 3: 实施 build_index.py**

```python
"""build_index:扫描 charts 目录的实际产物(<recipe-id>.json/.png),按类别
生成 INDEX.md——只索引画出来的图,不为没画的留空位(设计 spec §6/§8)。
PNG 保持平铺,归组只发生在本索引呈现层。"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

import yaml

CHARTBOOK = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(CHARTBOOK.parent / "scripts"))
from engine_common import CATEGORY_IDS  # noqa: E402


def recipe_meta(rid: str):
    """recipe frontmatter(dict);非 chartbook recipe 返回 None。"""
    p = CHARTBOOK / "recipes" / f"{rid}.md"
    if not p.exists():
        return None
    m = re.match(r"^---\n(.*?)\n---", p.read_text(encoding="utf-8"), re.S)
    return yaml.safe_load(m.group(1)) if m else None


def _scalars(d: dict, limit: int) -> list:
    out = []
    for k, v in d.items():
        if k in ("recipe", "note", "seed"):
            continue
        if isinstance(v, (bool, int, float, str)):
            out.append(f"{k}={v}")
        if len(out) >= limit:
            break
    return out


def key_descriptors(stats: dict, limit: int = 8) -> list:
    """JSON 顶层标量摘录;顶层没有标量时下钻 models 的第一个模型。"""
    out = _scalars(stats, limit)
    models = stats.get("models")
    if not out and isinstance(models, dict) and models:
        name, first = next(iter(models.items()))
        if isinstance(first, dict):
            out = [f"models[{name}].{s}" for s in _scalars(first, limit)]
    return out


def build(charts_dir: Path) -> str:
    charts_dir = Path(charts_dir)
    found, unknown = [], []
    for jp in sorted(charts_dir.glob("*.json")):
        rid = jp.stem
        meta = recipe_meta(rid)
        if meta is None:
            unknown.append(rid)
            continue
        stats = json.loads(jp.read_text(encoding="utf-8"))
        found.append((str(meta.get("category") or "uncategorized"), rid, meta,
                      stats, (charts_dir / f"{rid}.png").exists()))
    lines = ["# 图表索引（本次实际产物）", ""]
    if not found and not unknown:
        lines.append("（本目录无产物）")
    for cat in list(CATEGORY_IDS) + ["uncategorized"]:
        group = [f for f in found if f[0] == cat]
        if not group:
            continue
        lines += [f"## {cat}", ""]
        for _cat, rid, meta, stats, has_png in group:
            lines.append(f"### {rid}")
            q = str(meta.get("适用问题") or "").strip()
            if q:
                lines.append(f"适用问题: {q}")
            lines.append(f"![{rid}]({rid}.png)" if has_png
                         else "（无 PNG 产物,只有 JSON）")
            desc = key_descriptors(stats)
            if desc:
                lines.append("关键描述符: " + ", ".join(desc))
            lines.append("")
    if unknown:
        lines += ["## 未识别产物（非 chartbook recipe,不归组）", ""]
        lines += [f"- {r}.json" for r in unknown] + [""]
    return "\n".join(lines) + "\n"


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--charts-dir", required=True)
    a = ap.parse_args(argv)
    d = Path(a.charts_dir)
    (d / "INDEX.md").write_text(build(d), encoding="utf-8")
    print(f"INDEX.md written: {d / 'INDEX.md'}")


if __name__ == "__main__":
    main()
```

- [ ] **Step 4: 跑测试确认通过**

```bash
python -m pytest ts-diagnose/chartbook/tests/test_build_index.py -q -W error
```

预期:4 passed。再跑全 chartbook 套件确认无回归:

```bash
python -m pytest ts-diagnose/chartbook/tests/ -q -W error
```

- [ ] **Step 5: 提交**

```bash
git add ts-diagnose/chartbook/scripts/build_index.py ts-diagnose/chartbook/tests/test_build_index.py
git commit -m "feat(ts-diagnose): build_index.py 按类别生成 INDEX.md——只索引实际产物,未识别 json 单列(spec §6/§8)"
```

---

### Task 4: true-vs-pred-scatter 加 Mincer-Zarnowitz 检验

**Files:**
- Modify: `ts-diagnose/chartbook/scripts/chart_true_vs_pred_scatter.py`
- Modify: `ts-diagnose/chartbook/recipes/true-vs-pred-scatter.md`(json_schema/验证步)
- Modify: `ts-diagnose/chartbook/tests/test_chart_true_vs_pred_scatter.py`

**Interfaces:**
- Consumes: 现有 compute(df, n_bins) 签名不变。
- Produces: 每模型 JSON 新增 `"mz"` 键:`{"a", "b", "f_stat", "p_value"}`(退化分支 f_stat=None 并带 "note")。MZ 方向:**y_true = a + b·y_pred**(与既有 slope 的 p-on-y 方向相反,勿混)。

**解析 golden 构造(零随机)**:配对正交噪声——y_pred 取值成对重复 `[v,v]`,y_true = y_pred + `[+d,−d]`,则 Σe=0 且 Σ(y_pred·e)=0 **精确**成立,OLS 精确回收 a=0,b=1,SSR_u=SSR_r=Σd² → F=0,p=1。带偏置版 y_true = c + y_pred + e 同理精确回收 a=c,b=1,F = (c²·n/2)/(Σd²/(n−2)) 解析可算。

- [ ] **Step 1: 写失败测试**

`test_chart_true_vs_pred_scatter.py` 追加:

```python
def _paired_df(bias=0.0, d=1.0, n_pairs=20):
    """配对 ±d 正交噪声:MZ OLS 精确回收 a=bias,b=1(零随机解析 golden)。"""
    p = np.repeat(np.linspace(1.0, 20.0, n_pairs), 2)
    e = np.tile([d, -d], n_pairs)
    return pd.DataFrame({"model": "A", "y_true": bias + p + e, "y_pred": p})


def test_mz_unbiased_exact():
    """无偏预测:a=0,b=1 精确回收,F=0,p=1——不拒绝无偏。"""
    mz = cts.compute(_paired_df())["models"]["A"]["mz"]
    assert np.isclose(mz["a"], 0.0, atol=1e-9)
    assert np.isclose(mz["b"], 1.0, atol=1e-9)
    assert np.isclose(mz["f_stat"], 0.0, atol=1e-9)
    assert np.isclose(mz["p_value"], 1.0)


def test_mz_biased_exact():
    """常数偏置 c=2:a=2,b=1 精确回收;F=(c²n/2)/(Σd²/(n−2)) 解析值,p≈0 拒绝。
    n=40,d=1:SSR_u=40,F=(4·40/2)/(40/38)=76·38/40=76.0。"""
    mz = cts.compute(_paired_df(bias=2.0))["models"]["A"]["mz"]
    assert np.isclose(mz["a"], 2.0, atol=1e-9)
    assert np.isclose(mz["b"], 1.0, atol=1e-9)
    assert np.isclose(mz["f_stat"], 76.0, atol=1e-6)
    assert mz["p_value"] < 1e-6


def test_mz_noiseless_degenerate():
    """既有无噪声夹具(y_pred=0.8y+0.5):SSR_u=0,F 发散→f_stat=None;
    SSR_r>0 → p=0 拒绝。反解 b=1/0.8=1.25,a=-0.5/0.8=-0.625。"""
    mz = cts.compute(_df())["models"]["A"]["mz"]
    assert np.isclose(mz["b"], 1.25)
    assert np.isclose(mz["a"], -0.625)
    assert mz["f_stat"] is None
    assert mz["p_value"] == 0.0


def test_mz_perfect_forecast():
    """y_pred==y_true:SSR_u=SSR_r=0,恰为无偏 → p=1。"""
    y = np.linspace(1.0, 9.0, 30)
    df = pd.DataFrame({"model": "A", "y_true": y, "y_pred": y})
    mz = cts.compute(df)["models"]["A"]["mz"]
    assert mz["f_stat"] is None
    assert mz["p_value"] == 1.0
```

- [ ] **Step 2: 跑测试确认失败**

```bash
python -m pytest ts-diagnose/chartbook/tests/test_chart_true_vs_pred_scatter.py -q -W error
```

预期:4 个新测试 FAIL(KeyError "mz");既有 4 个仍 PASS。

- [ ] **Step 3: 实施**

`chart_true_vs_pred_scatter.py` 顶部 import 区加:

```python
from scipy.stats import f as f_dist
```

模块内(compute 之前)加:

```python
def _mincer_zarnowitz(y, p, eps=1e-12):
    """MZ 回归 y_true = a + b·y_pred;联合检验 H0: a=0,b=1(F,df=(2,n-2))。
    SSR_u≈0 时 F 发散:f_stat=None,p 由 SSR_r 是否也≈0 判(恰无偏→1,有偏→0)。"""
    n = len(y)
    b, a = np.polyfit(p, y, 1)
    ssr_u = float(np.sum((y - (a + b * p)) ** 2))
    ssr_r = float(np.sum((y - p) ** 2))
    out = {"a": round(float(a), 6), "b": round(float(b), 6)}
    if ssr_u < eps:
        out.update({"f_stat": None,
                    "p_value": 1.0 if ssr_r < eps else 0.0,
                    "note": "无噪声退化:SSR_u≈0,F 发散;p 由 SSR_r 判"})
        return out
    f_stat = max(((ssr_r - ssr_u) / 2.0) / (ssr_u / (n - 2)), 0.0)
    out.update({"f_stat": round(float(f_stat), 6),
                "p_value": round(float(f_dist.sf(f_stat, 2, n - 2)), 6)})
    return out
```

compute() 的 `out["models"][str(m)] = {...}` 字典里加一项(放 "n" 之后):

```python
            "mz": _mincer_zarnowitz(y, p),
```

render_from_df() 里给注记加 MZ(替换现有 ax.text 一行):

```python
        mz = s["mz"]
        ptxt = ("p<1e-6" if mz["p_value"] < 1e-6 else f"p={mz['p_value']:.3f}")
        ax.text(0.03, 0.95,
                f"R²={s['r2']:.4f}\nMZ: b={mz['b']:.3f} {ptxt}",
                transform=ax.transAxes, va="top",
                bbox=dict(fc="white", alpha=0.85))
```

并在 `ax.plot(lim, [s["slope"]*v...])` 之后加 MZ 线(y_true=a+b·y_pred 反解到本图坐标 x=y_true,y=y_pred):

```python
        if abs(mz["b"]) > 1e-12:
            ax.plot(lim, [(v - mz["a"]) / mz["b"] for v in lim],
                    color="green", lw=1.2, ls=":",
                    label=f"MZ b={mz['b']:.3f}")
```

`recipes/true-vs-pred-scatter.md` frontmatter 更新两处:
- `json_schema` 段落末尾补一句:`每模型另有 mz(Mincer-Zarnowitz:y_true=a+b·y_pred 的 a/b/f_stat/p_value;p 小 → 拒绝「无偏」,系统性衰减/放大真值)。`
- `验证步` 行末补:`;MZ 配对正交噪声精确回收 a/b 与解析 F 值(同测试文件)`

正文「JSON schema」小节如列有字段清单,同步补 mz 一行。

- [ ] **Step 4: 跑测试确认通过**

```bash
python -m pytest ts-diagnose/chartbook/tests/test_chart_true_vs_pred_scatter.py ts-diagnose/chartbook/tests/test_recipes_conform.py -q -W error
```

预期:全 PASS(conform 闸确认 recipe 改动无域名词泄漏)。

- [ ] **Step 5: 提交**

```bash
git add ts-diagnose/chartbook/scripts/chart_true_vs_pred_scatter.py ts-diagnose/chartbook/recipes/true-vs-pred-scatter.md ts-diagnose/chartbook/tests/test_chart_true_vs_pred_scatter.py
git commit -m "feat(ts-diagnose): true-vs-pred-scatter 加 Mincer-Zarnowitz 联合检验(a=0,b=1)——配对正交噪声零随机精确 golden"
```

---

### Task 5: engine-core.md 选择门同步 + CHANGELOG 收口

**Files:**
- Modify: `ts-diagnose/references/engine-core.md`(图表选择门 bullet)
- Modify: `ts-diagnose/CHANGELOG.md`

**Interfaces:** 纯文档,无代码接口。

- [ ] **Step 1: engine-core.md 更新**

「图表选择门」bullet(约第 51-58 行)内,把

```
（①声明且可画 ②声明但缺材料自动跳过 ③未声明但材料已满足的 chartbook recipe＝
  可加画池）。
```

改为

```
（①声明且可画 ②声明但缺材料自动跳过 ③未声明但材料已满足的 chartbook recipe＝
  可加画池,**按六类 category 分组呈现**,各图带类别标签）。
```

并在该 bullet 末尾(「同「抽样/截断必须披露」纪律）」之后)追加一句:

```
  画完后跑 `chartbook/scripts/build_index.py --charts-dir <workdir>/charts` 生成
  `INDEX.md`——按类别分节、只索引本次实际产物,判读入口从索引进。
```

- [ ] **Step 2: CHANGELOG 收口条目**

`ts-diagnose/CHANGELOG.md` 顶部(现有最新条目之上)加:

```markdown
## 2026-07-23 chartbook 扩展第四轮(呈现层收口,28 图工程完结)
- orient 图表选择门按六类 category 分组:声明图带类别标签,可加画池分组呈现
  (engine_common.recipe_category);
- 新增 `chartbook/scripts/build_index.py`:扫产物目录生成 INDEX.md,按类别分节、
  只索引实际产物(28 图是库存非必画清单,不为没画的留空位);
- true-vs-pred-scatter 增强:Mincer-Zarnowitz 回归(y_true=a+b·y_pred)+
  a=0,b=1 联合 F 检验注记,配对正交噪声零随机精确 golden;
- Plan3 延后清单清扫:死 pandas import×4、背景集退化分支如实标 all-windows、
  双 RNG 播种注释、tests/conftest.py 集中 OpenMP 豁免(全套件回到 0 warnings)、
  lookback ref≈0 与负 φ 瀑布渲染补覆盖。
```

- [ ] **Step 3: 全仓测试**

```bash
python -m pytest ts-diagnose/ -q
```

预期:全部 PASS,0 warnings。

- [ ] **Step 4: 提交**

```bash
git add ts-diagnose/references/engine-core.md ts-diagnose/CHANGELOG.md
git commit -m "docs(ts-diagnose): 选择门分组与 INDEX.md 进 engine-core + CHANGELOG 第四轮收口——28 图扩展工程完结"
```
