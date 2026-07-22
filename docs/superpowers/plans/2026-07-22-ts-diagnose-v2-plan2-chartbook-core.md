# ts-diagnose v2 Plan 2：chartbook 基础件 + A/B/C 组 9 个预写图脚本

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 落地 ts-diagnose 引擎级 chartbook 图谱库——公共件 + recipe 规范 + A 组（y-label 误差分解 3 图）+ B 组（走势稳定 2 图）+ C 组（模型对比 4 图），全部预写、pytest 合成植入回收验证。

**Architecture:** `ts-diagnose/chartbook/` 引擎级共享库（非独立 skill）。所有图脚本消费统一规范长表，compute()（纯函数、被测）与 render()（matplotlib、副产品）分离，JSON 一等产物 + PNG 副产品。每图一个 recipe md（frontmatter 供 orient 机器读 + 判读节供 agent 读）。设计规格：`docs/superpowers/specs/2026-07-22-ts-diagnose-v2-intake-chartbook-design.md` §4。

**Tech Stack:** Python 3 + pandas + numpy + matplotlib(Agg) + pytest + PyYAML。

**仓库根** `<REPO>` = `/Users/tqa946816/Documents/华为/光伏预测/结果分析skill`。所有路径相对它。

## Global Constraints

- **规范长表列名精确**（缺一列即 ValueError）：`window_ts | unit_id | model | horizon_step | y_true | y_pred`；误差定义恒为 `err = y_pred − y_true`。
- **JSON 一等产物**：每脚本落 `<out_dir>/<recipe-id>.json` + `<recipe-id>.png` 两个文件；没有 JSON 的图不算完成；JSON 自足（完整数字 + 形状描述符），后续判读只读 JSON 不读 PNG。
- **形状描述符字段名精确**（与 pv-result-analysis `_curve_stats` 同名，判读库依赖）：`curve / trend / monotonic / max_jump_idx / max_jump / roughness / argmax / argmin`；trend 取值 `上升/下降/平`。
- **零跨 skill 依赖**：chartbook 任何文件不 import、不读取 `pv-result-analysis/` 下任何文件（代码允许复制改造进来，不允许引用）。
- **golden 决定论**：测试合成数据禁 `random`、禁 `datetime.now()`；一律解析式构造（固定幅度 + 按 step 奇偶交替符号 ⇒ 单元格 RMSE 恰等于幅度）。
- **matplotlib 必须 Agg 后端**（`chart_common` import 时设定），CJK 字体回退链 `Arial Unicode MS → PingFang SC → SimHei → Noto Sans CJK SC`。
- **recipe frontmatter 必备键**：`id / needs_materials / 适用问题 / outputs.json / outputs.png / json_schema / bridge_hooks / 验证步`；`id` == 文件名（去 .md）；`needs_materials ⊆ engine_common.MATERIAL_IDS`；`outputs.json == "<id>.json"`、`outputs.png == "<id>.png"`；正文必须含 `## 判读` 节。
- **文件命名映射**：recipe id 用 kebab-case（`error-breakdown`），脚本文件用 `chart_` + id 的 snake_case（`chart_error_breakdown.py`），脚本内常量 `RECIPE_ID` = kebab-case id。
- **CLI 公共约定**：每脚本 `--pred <规范长表路径>`（必填）、`--out-dir <目录>`（必填），其余为 recipe 特有参数；`main(argv=None)` 可注入参数供测试。
- 提交信息用 `feat(ts-diagnose)` / `test(ts-diagnose)` / `docs(ts-diagnose)` 前缀。
- **绝不触碰**：`pv-result-analysis/`、`row-diagnostic/`、`docs/skill解析/`、工作区里任何本计划未列出的未提交文件。
- 每个任务收尾跑全仓 `python3 -m pytest <REPO> -q` 必须全绿。

## 文件结构总览

```
ts-diagnose/chartbook/
├── _recipe-spec.md                    # Task 1
├── scripts/
│   ├── chart_common.py                # Task 1
│   ├── chart_error_breakdown.py       # Task 2  (A)
│   ├── chart_intraday_profile.py      # Task 3  (A)
│   ├── chart_worst_points.py          # Task 4  (A)
│   ├── chart_horizon_degradation.py   # Task 5  (B)
│   ├── chart_rolling_stability.py     # Task 6  (B)
│   ├── chart_true_vs_pred_scatter.py  # Task 7  (C)
│   ├── chart_model_error_correlation.py # Task 8 (C)
│   ├── chart_worst_slice_compare.py   # Task 9  (C)
│   └── chart_oracle_gap.py            # Task 10 (C)
├── recipes/<id>.md                    # 各任务随脚本一起写
├── golden/example_adapter/            # Task 11（非标宽表→长表示例适配 + 对账）
└── tests/
    ├── synth.py                       # Task 1（合成长表构造器，全部图测试共用）
    ├── test_chart_common.py           # Task 1
    ├── test_recipes_conform.py        # Task 1（regexp 全部 recipes/*.md 过规范校验）
    └── test_chart_<snake_id>.py       # 各任务
```

---

### Task 1: chartbook 骨架 + `_recipe-spec.md` + `chart_common.py` + recipe 规范校验测试

**Files:**
- Create: `ts-diagnose/chartbook/_recipe-spec.md`
- Create: `ts-diagnose/chartbook/scripts/chart_common.py`
- Create: `ts-diagnose/chartbook/tests/synth.py`
- Create: `ts-diagnose/chartbook/tests/test_chart_common.py`
- Create: `ts-diagnose/chartbook/tests/test_recipes_conform.py`

**Interfaces:**
- Produces（后续所有任务依赖，签名逐字用）：
  - `chart_common.REQUIRED_COLS: tuple`
  - `chart_common.load_predictions(path) -> pd.DataFrame`（校验列、window_ts 转 datetime、加 `err` 列）
  - `chart_common.row_rmse(df) -> pd.DataFrame`（列 `model, unit_id, window_ts, rmse`）
  - `chart_common.curve_stats(y, index=None, round_to=3) -> dict`
  - `chart_common.downsample(d: dict, max_points=500) -> dict`
  - `chart_common.save_outputs(fig, out_dir, recipe_id, stats) -> dict`
  - `chart_common.setup_font() -> None`
  - `tests/synth.py` 的 `make_long(models, units, windows, steps, err_fn, y_fn=...) -> pd.DataFrame`

- [ ] **Step 1: 写失败测试 `tests/test_chart_common.py`**

```python
"""chart_common 单测：长表校验 / row_rmse / 形状描述符 / 落盘双产物。"""
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))
sys.path.insert(0, str(Path(__file__).resolve().parent))

import chart_common as cc          # noqa: E402
from synth import make_long        # noqa: E402


def _write_csv(tmp_path, df):
    p = tmp_path / "pred.csv"
    df.to_csv(p, index=False)
    return p


def test_load_predictions_missing_col_raises(tmp_path):
    df = make_long(["A"], ["U1"], ["2024-01-01"], 4,
                   lambda m, u, w, s: 1.0).drop(columns=["y_pred"])
    with pytest.raises(ValueError, match="y_pred"):
        cc.load_predictions(_write_csv(tmp_path, df))


def test_load_predictions_adds_err_and_datetime(tmp_path):
    df = make_long(["A"], ["U1"], ["2024-01-01"], 4, lambda m, u, w, s: 2.0)
    out = cc.load_predictions(_write_csv(tmp_path, df))
    assert np.allclose(out["err"], 2.0)
    assert pd.api.types.is_datetime64_any_dtype(out["window_ts"])


def test_row_rmse_exact():
    # err = ±3 交替 ⇒ 每行 RMSE 恰为 3
    df = make_long(["A"], ["U1"], ["2024-01-01", "2024-01-02"], 8,
                   lambda m, u, w, s: 3.0 * (1 if s % 2 == 0 else -1))
    df["window_ts"] = pd.to_datetime(df["window_ts"])
    df["err"] = df["y_pred"] - df["y_true"]
    rr = cc.row_rmse(df)
    assert len(rr) == 2
    assert np.allclose(rr["rmse"], 3.0)
    assert set(rr.columns) == {"model", "unit_id", "window_ts", "rmse"}


def test_curve_stats_fields_and_values():
    st = cc.curve_stats([1.0, 1.0, 4.0, 2.0])
    assert st["trend"] == "上升"
    assert st["monotonic"] is False
    assert st["max_jump_idx"] == "1" and st["max_jump"] == 3.0
    assert st["argmax"] == "2" and st["argmin"] == "0"
    assert set(st) == {"curve", "trend", "monotonic", "max_jump_idx",
                       "max_jump", "roughness", "argmax", "argmin"}


def test_downsample_keeps_ends_and_bound():
    d = {str(i): i for i in range(2000)}
    out = cc.downsample(d, max_points=100)
    assert len(out) <= 100
    assert "0" in out and "1999" in out


def test_save_outputs_writes_json_and_png(tmp_path):
    import matplotlib.pyplot as plt
    fig, ax = plt.subplots()
    ax.plot([0, 1], [0, 1])
    stats = cc.save_outputs(fig, tmp_path, "demo-recipe", {"a": 1})
    assert stats == {"a": 1}
    assert (tmp_path / "demo-recipe.png").exists()
    loaded = json.loads((tmp_path / "demo-recipe.json").read_text())
    assert loaded == {"a": 1}
```

- [ ] **Step 2: 写 `tests/synth.py`（测试共用合成器，决定论）**

```python
"""chartbook 测试共用：解析式构造规范长表（零随机——符号按 step 奇偶交替，
使每单元格 RMSE 恰等于幅度）。"""
import pandas as pd


def make_long(models, units, windows, steps, err_fn,
              y_fn=lambda w, u, s: 10.0):
    """err_fn(model, unit, window, step) -> 有符号误差；window 传字符串日期。"""
    rows = []
    for m in models:
        for u in units:
            for w in windows:
                for s in range(steps):
                    y = y_fn(w, u, s)
                    e = err_fn(m, u, w, s)
                    rows.append({"window_ts": w, "unit_id": u, "model": m,
                                 "horizon_step": s, "y_true": y,
                                 "y_pred": y + e})
    return pd.DataFrame(rows)


def alt(amp, s):
    """幅度 amp、按 step 奇偶交替符号 ⇒ RMSE == amp。"""
    return amp * (1.0 if s % 2 == 0 else -1.0)
```

- [ ] **Step 3: 跑测试确认失败**

Run: `python3 -m pytest ts-diagnose/chartbook/tests/test_chart_common.py -q`
Expected: FAIL（`ModuleNotFoundError: chart_common`）

- [ ] **Step 4: 写 `scripts/chart_common.py`**

```python
"""chartbook 公共件：规范长表读入、逐行 RMSE、形状描述符、JSON+PNG 落盘。

纪律（见 chartbook/_recipe-spec.md）：
- JSON 是一等产物，PNG 是给人看的副产品——判读一律读 JSON；
- err ≡ y_pred − y_true；
- curve_stats 字段名与判读库绑定，不得改名。
"""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd
import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402

REQUIRED_COLS = ("window_ts", "unit_id", "model", "horizon_step",
                 "y_true", "y_pred")


def setup_font():
    for font in ("Arial Unicode MS", "PingFang SC", "SimHei",
                 "Noto Sans CJK SC"):
        if font in {f.name for f in matplotlib.font_manager.fontManager.ttflist}:
            plt.rcParams["font.family"] = font
            break
    plt.rcParams["axes.unicode_minus"] = False


def load_predictions(path):
    p = Path(path)
    df = pd.read_parquet(p) if p.suffix == ".parquet" else pd.read_csv(p)
    missing = [c for c in REQUIRED_COLS if c not in df.columns]
    if missing:
        raise ValueError(
            f"规范长表缺列 {missing}；需要 {list(REQUIRED_COLS)}"
            "（适配器契约见 chartbook/_recipe-spec.md）")
    df = df.copy()
    df["window_ts"] = pd.to_datetime(df["window_ts"])
    df["err"] = df["y_pred"] - df["y_true"]
    return df


def row_rmse(df):
    """每 (model, unit_id, window_ts) 一行的全 horizon RMSE（rmse_192 口径泛化）。"""
    g = df.groupby(["model", "unit_id", "window_ts"])["err"]
    return (g.apply(lambda e: float(np.sqrt(np.mean(np.square(e)))))
            .rename("rmse").reset_index())


def curve_stats(y, index=None, round_to=3):
    """曲线序列化 + 形状描述符（字段名与判读库绑定）。"""
    v = np.asarray(y, float)
    n = len(v)
    idx = list(index) if index is not None else list(range(n))
    finite = v[np.isfinite(v)]
    if n < 2 or finite.size < 2:
        return {"curve": {str(k): (round(float(val), round_to)
                                   if np.isfinite(val) else None)
                          for k, val in zip(idx, v)},
                "trend": "平", "monotonic": True,
                "max_jump_idx": str(idx[0]) if idx else None,
                "max_jump": 0.0, "roughness": 0.0,
                "argmax": None, "argmin": None}
    diff = np.diff(v)
    j = int(np.nanargmax(np.abs(diff)))
    return {
        "curve": {str(k): (round(float(val), round_to)
                           if np.isfinite(val) else None)
                  for k, val in zip(idx, v)},
        "trend": "上升" if v[-1] > v[0] else ("下降" if v[-1] < v[0] else "平"),
        "monotonic": bool(np.all(diff >= 0) or np.all(diff <= 0)),
        "max_jump_idx": str(idx[j]), "max_jump": round(float(diff[j]), round_to),
        "roughness": round(float(np.nanstd(diff)), round_to),
        "argmax": str(idx[int(np.nanargmax(v))]),
        "argmin": str(idx[int(np.nanargmin(v))]),
    }


def downsample(d: dict, max_points: int = 500) -> dict:
    """曲线字典等距抽样到 ≤max_points 点（首尾必留）。"""
    items = list(d.items())
    if len(items) <= max_points:
        return d
    keep = np.linspace(0, len(items) - 1, max_points).round().astype(int)
    return dict(items[i] for i in sorted(set(keep.tolist())))


def save_outputs(fig, out_dir, recipe_id: str, stats: dict) -> dict:
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    fig.savefig(out / f"{recipe_id}.png", dpi=150, bbox_inches="tight")
    plt.close(fig)
    (out / f"{recipe_id}.json").write_text(
        json.dumps(stats, ensure_ascii=False, indent=2, default=str))
    return stats
```

- [ ] **Step 5: 跑测试确认通过**

Run: `python3 -m pytest ts-diagnose/chartbook/tests/test_chart_common.py -q`
Expected: PASS（6 passed）

- [ ] **Step 6: 写 `_recipe-spec.md`**

内容（逐字）：

````markdown
# chartbook recipe 编写规范（_recipe-spec）

chartbook = ts-diagnose 引擎级共享图谱库（**不是独立 skill**；layering：引擎层共享合法，
playbook 只许按 recipe id 引用，playbook 之间照旧互不引用）。一图一 recipe：
`recipes/<id>.md`（本规范）+ `scripts/chart_<id 蛇形>.py`（预写脚本）+
`tests/test_chart_<id 蛇形>.py`（合成植入回收 golden）。

## 1. 预写纪律

图脚本**预写、随引擎提交、pytest 验证**——运行时禁止现场重写 chartbook 已覆盖的图；
现场唯一要写的代码是薄适配器 `analysis_scripts/adapter.py`（用户数据 → §2 规范长表，
由 `materials.<id>.schema` 驱动），写完必须过**对账验证步**：
①行数守恒（长表行数 == 源数据行数 × horizon 步数，缺测另行说明）；
②抽 3 个窗口人工核对数值与源一致。对账记录写 PROGRESS.md。

## 2. 规范长表（canonical long format）

```
predictions: window_ts | unit_id | model | horizon_step | y_true | y_pred
```

- `window_ts` 预报发起时刻（datetime）；`unit_id` 单元（站点/序列）；
  `horizon_step` 0 起整数；误差恒为 `err = y_pred − y_true`。
- 单模型场景 model 列填一个常量名即可；单单元场景 unit_id 同理。

## 3. Frontmatter schema（orient/校验测试机器读）

```yaml
---
id: horizon-degradation            # 必填，== 文件名（去 .md），kebab-case
needs_materials: [predict, truth]  # 必填，⊆ engine_common.MATERIAL_IDS；orient 据此报可用性
适用问题: 短期准长期崩？退化速度对比？   # 必填，一句话（路由与 playbook 选图依据）
outputs:
  json: horizon-degradation.json   # 必填，== "<id>.json"（一等产物）
  png: horizon-degradation.png     # 必填，== "<id>.png"（人看的副产品）
json_schema: >                     # 必填，JSON 关键字段的自然语言描述
  每模型每 horizon 指标曲线（curve_stats）、早/晚段斜率、模型交叉点、per-unit 崩溃点
bridge_hooks: >                    # 必填，形状描述符 → 架构假设的映射指引
  晚段斜率陡且早段平 → 长程依赖衰减类假设
验证步: 合成已知退化曲线 → 脚本必须回收植入的斜率与交叉点   # 必填，一句话
---
```

## 4. 正文必备节

1. **适用问题**——什么诊断问题该看这张图；
2. **CLI 与参数**——精确命令行（含默认值）；
3. **JSON schema**——逐字段说明（完整、自足：判读只读它）;
4. **`## 判读`**——形状描述符 → 候选机制 → 去哪张图交叉验证。只给**候选假设**，
   结论必须回 playbook 三道门；判读读 `curve/trend/max_jump/roughness/argmax` 等
   描述符数字，**不 Read PNG**；
5. **验证步**——本图 golden 植入了什么、回收断言是什么（对应 tests/ 文件）。

## 5. 硬规则

1. JSON 一等、PNG 副产品——没有 JSON 的图不算完成；JSON 必须自足（完整数字+描述符）。
2. compute()（纯计算，被 golden 测）与 render()（画图）分离；main(argv=None) 可注入。
3. golden 决定论：合成数据零随机（幅度+奇偶交替符号 ⇒ 单元格 RMSE == 幅度）。
4. 每脚本 CLI 公共参数：`--pred`（规范长表路径）、`--out-dir`；其余 recipe 特有。
5. 多模型才有意义的图（对比类）在 <2 模型时抛 ValueError 并说明，不静默出空图。
````

- [ ] **Step 7: 写失败测试 `tests/test_recipes_conform.py`**

```python
"""全部 recipes/*.md 过 _recipe-spec 规范校验（Task 1 时 recipes 为空=空转；
后续任务每加一个 recipe 自动被闸）。同时用 tmp fixture 验证校验器本身有牙。"""
import re
import sys
from pathlib import Path

import pytest
import yaml

CHARTBOOK = Path(__file__).resolve().parents[1]
ENGINE_SCRIPTS = CHARTBOOK.parent / "scripts"
sys.path.insert(0, str(ENGINE_SCRIPTS))
from engine_common import MATERIAL_IDS  # noqa: E402

REQUIRED_KEYS = ("id", "needs_materials", "适用问题", "outputs",
                 "json_schema", "bridge_hooks", "验证步")


def parse_recipe(text):
    m = re.match(r"^---\n(.*?)\n---\n(.*)$", text, re.S)
    assert m, "recipe 必须以 YAML frontmatter 开头"
    return yaml.safe_load(m.group(1)), m.group(2)


def check_recipe(path: Path):
    fm, body = parse_recipe(path.read_text())
    for k in REQUIRED_KEYS:
        assert k in fm, f"{path.name} 缺 frontmatter 键 {k}"
    assert fm["id"] == path.stem, f"{path.name} id 与文件名不一致"
    mats = fm["needs_materials"]
    assert mats and set(mats) <= set(MATERIAL_IDS), \
        f"{path.name} needs_materials 非法: {mats}"
    assert fm["outputs"]["json"] == f"{fm['id']}.json"
    assert fm["outputs"]["png"] == f"{fm['id']}.png"
    assert "## 判读" in body, f"{path.name} 缺 ## 判读 节"
    script = CHARTBOOK / "scripts" / f"chart_{fm['id'].replace('-', '_')}.py"
    assert script.exists(), f"{path.name} 对应脚本 {script.name} 不存在"


def all_recipes():
    return sorted((CHARTBOOK / "recipes").glob("*.md")) \
        if (CHARTBOOK / "recipes").is_dir() else []


@pytest.mark.parametrize("path", all_recipes(),
                         ids=lambda p: p.stem if hasattr(p, "stem") else str(p))
def test_recipe_conforms(path):
    check_recipe(path)


def test_recipe_checker_has_teeth(tmp_path):
    bad = tmp_path / "bad-recipe.md"
    bad.write_text("---\nid: bad-recipe\nneeds_materials: [不存在的材料]\n"
                   "适用问题: x\noutputs:\n  json: bad-recipe.json\n"
                   "  png: bad-recipe.png\njson_schema: x\nbridge_hooks: x\n"
                   "验证步: x\n---\n## 判读\n")
    with pytest.raises(AssertionError, match="needs_materials"):
        check_recipe(bad)
```

注意：`all_recipes()` 为空时 parametrize 产生 0 个用例，pytest 对空参数集默认 skip 而非 fail——这正是想要的空转语义。

- [ ] **Step 8: 跑全部新测试 + 全仓回归**

Run: `python3 -m pytest ts-diagnose/chartbook/tests/ -q && python3 -m pytest "<REPO>" -q`
Expected: chartbook 测试 PASS（7 passed, 1 skipped 左右）；全仓绿。

- [ ] **Step 9: Commit**

```bash
git add ts-diagnose/chartbook/
git commit -m "feat(ts-diagnose): chartbook 骨架——规范长表公共件 chart_common + recipe 规范与一致性闸"
```

---

### Task 2: `error-breakdown`（A 组核心图：什么单元什么时候 RMSE 最大）

**Files:**
- Create: `ts-diagnose/chartbook/scripts/chart_error_breakdown.py`
- Create: `ts-diagnose/chartbook/recipes/error-breakdown.md`
- Create: `ts-diagnose/chartbook/tests/test_chart_error_breakdown.py`

**Interfaces:**
- Consumes: Task 1 的 `chart_common`（load_predictions/curve_stats/save_outputs）、`tests/synth.py`
- Produces: `compute(df, freq="15min", top_k=10) -> dict`；CLI `--pred --out-dir [--freq 15min] [--top-k 10]`

- [ ] **Step 1: 写失败测试**

```python
"""error-breakdown golden：植入 (U2, 2024-02) 单元格误差幅度 3（其余 1）→
argmax 单元格、边际曲线、Top-K 必须回收。"""
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

import chart_error_breakdown as ceb  # noqa: E402
import chart_common as cc            # noqa: E402
from synth import make_long, alt     # noqa: E402


def _df():
    windows = [f"2024-{mm:02d}-{dd:02d}" for mm in (1, 2, 3)
               for dd in (5, 15, 25)]

    def err(m, u, w, s):
        amp = 3.0 if (u == "U2" and w.startswith("2024-02")) else 1.0
        return alt(amp, s)

    df = make_long(["A"], ["U1", "U2"], windows, 8, err)
    df["window_ts"] = __import__("pandas").to_datetime(df["window_ts"])
    df["err"] = df["y_pred"] - df["y_true"]
    return df


def test_argmax_cell_recovered():
    st = ceb.compute(_df(), freq="15min", top_k=3)
    cell = st["models"]["A"]["argmax_cell"]
    assert cell["unit"] == "U2" and cell["month"] == "2024-02"
    assert np.isclose(cell["rmse"], 3.0)


def test_marginals_and_topk():
    st = ceb.compute(_df(), freq="15min", top_k=3)
    a = st["models"]["A"]
    # 单元×月矩阵：非植入格恰为 1
    assert np.isclose(a["unit_month_rmse"]["U1"]["2024-01"], 1.0)
    # per-month 边际（U2 被拉高的月）argmax 落在 2024-02
    assert a["per_month"]["argmax"] == "2024-02"
    top = a["top_worst"]
    assert top[0]["unit"] == "U2" and top[0]["month"] == "2024-02"
    assert len(top) == 3
    # horizon 分带矩阵存在且键完整
    assert set(a["unit_band_rmse"]["U2"]) == {"band0", "band1", "band2", "band3"}


def test_main_writes_json_and_png(tmp_path):
    p = tmp_path / "pred.csv"
    _df().drop(columns=["err"]).to_csv(p, index=False)
    ceb.main(["--pred", str(p), "--out-dir", str(tmp_path)])
    assert (tmp_path / "error-breakdown.json").exists()
    assert (tmp_path / "error-breakdown.png").exists()
```

- [ ] **Step 2: 跑测试确认失败**

Run: `python3 -m pytest ts-diagnose/chartbook/tests/test_chart_error_breakdown.py -q`
Expected: FAIL（`ModuleNotFoundError: chart_error_breakdown`）

- [ ] **Step 3: 写 `chart_error_breakdown.py`**

```python
"""error-breakdown：分单元×日历(月/小时)×horizon 误差矩阵——谁、什么时候、错在哪。

JSON 一等产物；单元格 RMSE = sqrt(mean(err²))（点级聚合，跨单元格可比）。
"""
from __future__ import annotations

import argparse

import numpy as np
import pandas as pd

import chart_common as cc

RECIPE_ID = "error-breakdown"
N_BANDS = 4


def _cell_rmse(df, keys):
    return (df.groupby(keys)["err"]
            .apply(lambda e: float(np.sqrt(np.mean(np.square(e))))))


def compute(df: pd.DataFrame, freq: str = "15min", top_k: int = 10) -> dict:
    d = df.copy()
    d["month"] = d["window_ts"].dt.strftime("%Y-%m")
    # 目标时刻 = window_ts + step*freq（hour 维度按目标物理时刻算，不是发起时刻）
    d["target_hour"] = (d["window_ts"]
                        + d["horizon_step"] * pd.Timedelta(freq)).dt.hour
    n_steps = int(d["horizon_step"].max()) + 1
    band_edges = np.linspace(0, n_steps, N_BANDS + 1).astype(int)
    d["band"] = pd.cut(d["horizon_step"], bins=band_edges, right=False,
                       labels=[f"band{i}" for i in range(N_BANDS)],
                       include_lowest=True)
    out = {"recipe": RECIPE_ID, "freq": freq, "n_steps": n_steps,
           "band_edges": band_edges.tolist(), "models": {},
           "note": "单元格 RMSE=sqrt(mean(err^2)) 点级聚合；argmax_cell 即"
                   "「什么单元什么时候最差」；判读读边际 curve_stats 描述符。"}
    for m, g in d.groupby("model"):
        um = _cell_rmse(g, ["unit_id", "month"]).unstack()
        uh = _cell_rmse(g, ["unit_id", "target_hour"]).unstack()
        ub = _cell_rmse(g, ["unit_id", "band"]).unstack()
        flat = _cell_rmse(g, ["unit_id", "month"]).sort_values(ascending=False)
        counts = g.groupby(["unit_id", "month"])["err"].size()
        (u_star, mo_star) = flat.index[0]
        per_month = _cell_rmse(g, ["month"]).sort_index()
        per_hour = _cell_rmse(g, ["target_hour"]).sort_index()
        out["models"][str(m)] = {
            "unit_month_rmse": {u: {k: round(float(v), 4)
                                    for k, v in row.dropna().items()}
                                for u, row in um.iterrows()},
            "unit_hour_rmse": {u: {str(k): round(float(v), 4)
                                   for k, v in row.dropna().items()}
                               for u, row in uh.iterrows()},
            "unit_band_rmse": {u: {str(k): round(float(v), 4)
                                   for k, v in row.dropna().items()}
                               for u, row in ub.iterrows()},
            "argmax_cell": {"unit": str(u_star), "month": str(mo_star),
                            "rmse": round(float(flat.iloc[0]), 4),
                            "n": int(counts[(u_star, mo_star)])},
            "per_unit_rmse": {str(u): round(float(v), 4)
                              for u, v in _cell_rmse(g, ["unit_id"]).items()},
            "per_month": cc.curve_stats(per_month.values,
                                        index=list(per_month.index)),
            "per_hour": cc.curve_stats(per_hour.values,
                                       index=list(per_hour.index)),
            "top_worst": [{"unit": str(u), "month": str(mo),
                           "rmse": round(float(v), 4),
                           "n": int(counts[(u, mo)])}
                          for (u, mo), v in flat.head(top_k).items()],
        }
    return out


def render(stats: dict):
    import matplotlib.pyplot as plt
    cc.setup_font()
    models = list(stats["models"])
    fig, axes = plt.subplots(len(models), 1,
                             figsize=(10, 3.2 * len(models)), squeeze=False)
    for ax, m in zip(axes.ravel(), models):
        um = stats["models"][m]["unit_month_rmse"]
        units = sorted(um)
        months = sorted({mo for u in um for mo in um[u]})
        mat = np.array([[um[u].get(mo, np.nan) for mo in months]
                        for u in units], float)
        im = ax.imshow(mat, cmap="RdYlGn_r", aspect="auto")
        ax.set_xticks(range(len(months)), months, rotation=45, fontsize=7)
        ax.set_yticks(range(len(units)), units, fontsize=8)
        for i in range(len(units)):
            for j in range(len(months)):
                if np.isfinite(mat[i, j]):
                    ax.text(j, i, f"{mat[i, j]:.2f}", ha="center",
                            va="center", fontsize=7)
        ax.set_title(f"error-breakdown 单元×月 RMSE — {m}", fontsize=10)
        fig.colorbar(im, ax=ax, shrink=0.8)
    fig.tight_layout()
    return fig


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--pred", required=True)
    ap.add_argument("--out-dir", required=True)
    ap.add_argument("--freq", default="15min")
    ap.add_argument("--top-k", type=int, default=10)
    a = ap.parse_args(argv)
    df = cc.load_predictions(a.pred)
    stats = compute(df, freq=a.freq, top_k=a.top_k)
    cc.save_outputs(render(stats), a.out_dir, RECIPE_ID, stats)


if __name__ == "__main__":
    main()
```


- [ ] **Step 4: 跑测试确认通过**

Run: `python3 -m pytest ts-diagnose/chartbook/tests/test_chart_error_breakdown.py -q`
Expected: PASS（3 passed）

- [ ] **Step 5: 写 `recipes/error-breakdown.md`**

````markdown
---
id: error-breakdown
needs_materials: [predict, truth]
适用问题: 什么单元(站点)什么时候 RMSE 最大？误差集中在哪些月/时段/horizon 带？
outputs:
  json: error-breakdown.json
  png: error-breakdown.png
json_schema: >
  每模型：unit_month_rmse / unit_hour_rmse / unit_band_rmse 三个矩阵、
  argmax_cell（最差单元格+数值+样本量）、per_unit_rmse、per_month 与 per_hour
  边际 curve_stats、top_worst 前 K 组合。
bridge_hooks: >
  单一单元格独大（argmax 显著高于 top_worst 次位）→ 局部事件/数据质量类假设；
  某月整行同衰（per_month max_jump 大）→ 季节/分布漂移类假设，去 train-test-drift 交叉；
  band3 独差 → 长 horizon 衰减，去 horizon-degradation 交叉。
验证步: 植入 (U2, 2024-02) 幅度 3（其余 1）→ argmax_cell 与 Top-K 必须回收（tests/test_chart_error_breakdown.py）
---

# error-breakdown：单元×日历×horizon 误差分解

## 适用问题
y-label 误差「谁、什么时候、错在哪」的第一张图；A 组入口，几乎所有 playbook 的
事实阶段都该先看它。

## CLI 与参数
```bash
python3 chartbook/scripts/chart_error_breakdown.py \
  --pred predictions.parquet --out-dir <workdir>/charts [--freq 15min] [--top-k 10]
```
`--freq`：horizon 步长（目标时刻 = window_ts + step×freq，hour 维度据此算）。

## JSON schema
见 frontmatter json_schema；所有 RMSE 为点级 sqrt(mean(err²))，跨单元格可比；
n 为单元格样本量（判读时先看 n，样本 < 100 的单元格不下断言）。

## 判读
- `argmax_cell` 与 `top_worst` 断层大（首位 ≫ 次位）→ 候选：局部事件（限电/检修/
  数据缺陷）——去 worst-points 看该单元格内点级标签交叉验证；
- `per_month.curve` 整体抬升某月 → 候选：分布漂移——有 train_y 材料时去
  train-test-drift 交叉；
- `per_hour` 峰值时段 → 候选：日内物理过程（如爬坡时段）——去 intraday-profile
  看 bias 方向；
- `unit_band_rmse` 仅 band3 高 → 候选：长程衰减——去 horizon-degradation 看斜率。
只给候选假设；结论回 playbook 三道门。

## 验证步
合成 2 单元×3 月、幅度植入见 frontmatter；断言 argmax、边际 argmax、Top-K 排序、
非植入格数值恰为 1。
````

- [ ] **Step 6: 跑 recipe 一致性闸 + 全仓**

Run: `python3 -m pytest ts-diagnose/chartbook/tests/ -q && python3 -m pytest "<REPO>" -q`
Expected: 全绿（test_recipes_conform 现在有 1 个真实用例）。

- [ ] **Step 7: Commit**

```bash
git add ts-diagnose/chartbook/
git commit -m "feat(ts-diagnose): chartbook error-breakdown——单元×日历×horizon 误差分解（A 组核心）"
```

---

### Task 3: `intraday-profile`（A 组：日内时段 bias/RMSE 剖面）

**Files:**
- Create: `ts-diagnose/chartbook/scripts/chart_intraday_profile.py`
- Create: `ts-diagnose/chartbook/recipes/intraday-profile.md`
- Create: `ts-diagnose/chartbook/tests/test_chart_intraday_profile.py`

**Interfaces:**
- Consumes: Task 1 全部公共件
- Produces: `compute(df, freq="15min") -> dict`；CLI `--pred --out-dir [--freq 15min]`

- [ ] **Step 1: 写失败测试**

```python
"""intraday-profile golden：freq=1h、窗口起点 00:00、24 步 ⇒ 目标时刻==step；
植入 12 时误差幅度 3（其余 1）→ worst_hour 必须回收 12.0；纯正误差 → 偏度不对称回收。"""
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

import chart_intraday_profile as cip  # noqa: E402
from synth import make_long, alt      # noqa: E402


def _prep(df):
    df["window_ts"] = pd.to_datetime(df["window_ts"])
    df["err"] = df["y_pred"] - df["y_true"]
    return df


def test_worst_hour_recovered():
    def err(m, u, w, s):
        return alt(3.0 if s == 12 else 1.0, s)
    df = _prep(make_long(["A"], ["U1", "U2"], ["2024-01-01", "2024-01-02"], 24, err))
    st = cip.compute(df, freq="1h")
    a = st["models"]["A"]
    assert a["worst_hour"] == 12.0
    assert np.isclose(a["rmse_by_tod"]["curve"]["12.0"], 3.0)
    assert np.isclose(a["rmse_by_tod"]["curve"]["11.0"], 1.0)
    assert a["unit_worst_hour"]["U1"] == 12.0


def test_bias_asymmetry_all_positive_err():
    df = _prep(make_long(["A"], ["U1"], ["2024-01-01"], 24,
                         lambda m, u, w, s: 2.0))
    st = cip.compute(df, freq="1h")
    ba = st["models"]["A"]["bias_asymmetry"]
    assert ba["mean_over"] == 2.0 and ba["mean_under"] == 0.0


def test_main_writes_outputs(tmp_path):
    df = make_long(["A"], ["U1"], ["2024-01-01"], 24,
                   lambda m, u, w, s: alt(1.0, s))
    p = tmp_path / "pred.csv"
    df.to_csv(p, index=False)
    cip.main(["--pred", str(p), "--out-dir", str(tmp_path), "--freq", "1h"])
    assert (tmp_path / "intraday-profile.json").exists()
    assert (tmp_path / "intraday-profile.png").exists()
```

- [ ] **Step 2: 跑测试确认失败**

Run: `python3 -m pytest ts-diagnose/chartbook/tests/test_chart_intraday_profile.py -q`
Expected: FAIL（ModuleNotFoundError）

- [ ] **Step 3: 写 `chart_intraday_profile.py`**

```python
"""intraday-profile：按目标物理时刻（window_ts + step×freq）聚合的日内
bias/RMSE 剖面——峰值时段、低估/高估不对称。"""
from __future__ import annotations

import argparse

import numpy as np
import pandas as pd

import chart_common as cc

RECIPE_ID = "intraday-profile"


def compute(df: pd.DataFrame, freq: str = "15min") -> dict:
    d = df.copy()
    target = d["window_ts"] + d["horizon_step"] * pd.Timedelta(freq)
    d["tod_h"] = (target.dt.hour * 60 + target.dt.minute) / 60.0
    out = {"recipe": RECIPE_ID, "freq": freq, "models": {},
           "note": "tod 为目标物理时刻（小时）；bias>0 高估、<0 低估；"
                   "mean_under/mean_over 为负/正误差各自的均值（无该侧误差记 0）。"}
    for m, g in d.groupby("model"):
        grp = g.groupby("tod_h")["err"]
        rmse = grp.apply(lambda e: float(np.sqrt(np.mean(np.square(e)))))
        bias = grp.mean()
        hkey = [round(float(h), 2) for h in rmse.index]
        neg, pos = g.loc[g["err"] < 0, "err"], g.loc[g["err"] > 0, "err"]
        uw = {}
        for u, gu in g.groupby("unit_id"):
            r_u = gu.groupby("tod_h")["err"].apply(
                lambda e: float(np.sqrt(np.mean(np.square(e)))))
            uw[str(u)] = round(float(r_u.idxmax()), 2)
        out["models"][str(m)] = {
            "rmse_by_tod": cc.curve_stats(rmse.values, index=hkey),
            "bias_by_tod": cc.curve_stats(bias.values, index=hkey),
            "worst_hour": round(float(rmse.idxmax()), 2),
            "bias_asymmetry": {
                "mean_under": round(float(neg.mean()), 4) if len(neg) else 0.0,
                "mean_over": round(float(pos.mean()), 4) if len(pos) else 0.0},
            "unit_worst_hour": uw,
        }
    return out


def render(stats: dict):
    import matplotlib.pyplot as plt
    cc.setup_font()
    fig, axes = plt.subplots(2, 1, figsize=(10, 6), sharex=True)
    for m, s in stats["models"].items():
        for ax, key in zip(axes, ("rmse_by_tod", "bias_by_tod")):
            curve = s[key]["curve"]
            xs = [float(k) for k in curve]
            ys = [curve[k] for k in curve]
            ax.plot(xs, ys, label=m)
    axes[0].set_ylabel("RMSE"), axes[1].set_ylabel("bias")
    axes[1].axhline(0, color="k", lw=0.5)
    axes[1].set_xlabel("目标时刻 (h)")
    axes[0].set_title("intraday-profile 日内时段误差剖面")
    axes[0].legend(ncol=max(1, len(stats["models"])))
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

- [ ] **Step 4: 跑测试确认通过**

Run: `python3 -m pytest ts-diagnose/chartbook/tests/test_chart_intraday_profile.py -q`
Expected: PASS（3 passed）

- [ ] **Step 5: 写 `recipes/intraday-profile.md`**

````markdown
---
id: intraday-profile
needs_materials: [predict, truth]
适用问题: 误差集中在一天中的什么时段？系统性高估还是低估、集中在哪个物理时刻？
outputs:
  json: intraday-profile.json
  png: intraday-profile.png
json_schema: >
  每模型：rmse_by_tod / bias_by_tod（curve_stats，索引为目标时刻小时）、worst_hour、
  bias_asymmetry（mean_under/mean_over）、unit_worst_hour（每单元最差时刻）。
bridge_hooks: >
  bias 单向偏移（mean_over ≫ |mean_under| 或反之）→ 系统性标定/损失不对称类假设；
  worst_hour 落在物理过程转换时段（如爬坡）→ 输入变量分辨率/滞后类假设，
  去 error-breakdown 的 unit_hour_rmse 看是否全单元一致。
验证步: 植入 12 时幅度 3（其余 1）→ worst_hour==12.0 且曲线数值精确回收（tests/test_chart_intraday_profile.py）
---

# intraday-profile：日内时段误差剖面

## 适用问题
时段维度的误差定位；与 error-breakdown 的 hour 边际互为印证（本图多出 bias 方向
与不对称度）。

## CLI 与参数
```bash
python3 chartbook/scripts/chart_intraday_profile.py \
  --pred predictions.parquet --out-dir <workdir>/charts [--freq 15min]
```
tod = window_ts + step×freq 的物理时刻，**不是**预报发起时刻。

## JSON schema
见 frontmatter；curve_stats 索引为小时浮点（"11.0"、"11.25"…）。

## 判读
- `bias_by_tod` 全时段同号 → 候选：全局标定偏差（去 true-vs-pred-scatter 看 slope）；
- `bias_by_tod` 峰谷各偏一侧（早升段低估、午后高估）→ 候选：滞后/平滑类机制；
- `rmse_by_tod.argmax` 与 `unit_worst_hour` 不一致（各单元峰值时刻分散）→ 候选：
  单元本地因素主导，去 error-breakdown 的 unit_hour_rmse 交叉；
- roughness 大（剖面毛刺）→ 样本量不足的时段在支配曲线，先查每时段 n 再判读。
只给候选假设；结论回 playbook 三道门。

## 验证步
见 frontmatter；另断言纯正误差时 mean_under==0（无该侧误差记 0 的契约）。
````

- [ ] **Step 6: 跑一致性闸 + 全仓**

Run: `python3 -m pytest ts-diagnose/chartbook/tests/ -q && python3 -m pytest "<REPO>" -q`
Expected: 全绿。

- [ ] **Step 7: Commit**

```bash
git add ts-diagnose/chartbook/
git commit -m "feat(ts-diagnose): chartbook intraday-profile——日内时段 bias/RMSE 剖面"
```

---

### Task 4: `worst-points`（A 组：误差 top-N 点自动打标签 极值/转折点/高波动）

**Files:**
- Create: `ts-diagnose/chartbook/scripts/chart_worst_points.py`
- Create: `ts-diagnose/chartbook/recipes/worst-points.md`
- Create: `ts-diagnose/chartbook/tests/test_chart_worst_points.py`

**Interfaces:**
- Consumes: Task 1 公共件
- Produces: `compute(df, top_n=20, freq="15min", pct=0.95, vol_window=5) -> dict`；CLI `--pred --out-dir [--top-n 20] [--freq 15min] [--pct 0.95] [--vol-window 5]`

- [ ] **Step 1: 写失败测试**

```python
"""worst-points golden：单单元 3 窗口，分别植入 极值点/转折点/高波动点（各配大误差 5，
底噪 0.1）→ top-3 必须是这 3 个点且各自标签命中（标签可叠加，断言成员而非相等）。"""
import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

import chart_worst_points as cwp  # noqa: E402
from synth import make_long       # noqa: E402


def _df():
    # 三类现象放三个不同单元——标签阈值按单元自身分位数算，
    # 植入点是本单元该统计量的最大值 ⇒ 必然 ≥ q95（分位数 ≤ 最大值恒成立），回收有保证。
    def y_fn(w, u, s):
        if u == "U_ext":
            return 100.0 if s == 30 else 10.0 + 0.05 * s   # 极值尖峰
        if u == "U_ramp":
            return 50.0 if s >= 30 else 10.0               # 30 处陡坡（转折点）
        if 40 <= s <= 50:                                  # U_vol 高波动段
            return 10.0 + (8.0 if s % 2 == 0 else -8.0)
        return 10.0 + 0.05 * s

    def err(m, u, w, s):
        big = (u == "U_ext" and s == 30) or \
              (u == "U_ramp" and s == 30) or \
              (u == "U_vol" and s == 45)
        return 5.0 if big else 0.1

    df = make_long(["A"], ["U_ext", "U_ramp", "U_vol"],
                   ["2024-01-01"], 60, err, y_fn=y_fn)
    df["window_ts"] = pd.to_datetime(df["window_ts"])
    df["err"] = df["y_pred"] - df["y_true"]
    return df


def test_top3_points_and_labels():
    st = cwp.compute(_df(), top_n=3, freq="15min")
    pts = st["models"]["A"]["points"]
    assert len(pts) == 3
    by_key = {(p["unit"], p["step"]): p for p in pts}
    assert ("U_ext", 30) in by_key
    assert "极值" in by_key[("U_ext", 30)]["labels"]
    assert "转折点" in by_key[("U_ramp", 30)]["labels"]
    assert "高波动" in by_key[("U_vol", 45)]["labels"]
    for p in pts:
        assert p["err"] == 5.0
        assert set(p["context"]) == {"abs_dy", "local_std", "y_quantile"}


def test_label_share_sums_to_points():
    st = cwp.compute(_df(), top_n=3, freq="15min")
    share = st["models"]["A"]["label_share"]
    assert all(0 <= v <= 1 for v in share.values())


def test_main_writes_outputs(tmp_path):
    p = tmp_path / "pred.csv"
    _df().drop(columns=["err"]).to_csv(p, index=False)
    cwp.main(["--pred", str(p), "--out-dir", str(tmp_path), "--top-n", "3"])
    assert (tmp_path / "worst-points.json").exists()
    assert (tmp_path / "worst-points.png").exists()
```

- [ ] **Step 2: 跑测试确认失败**

Run: `python3 -m pytest ts-diagnose/chartbook/tests/test_chart_worst_points.py -q`
Expected: FAIL（ModuleNotFoundError）

- [ ] **Step 3: 写 `chart_worst_points.py`**

```python
"""worst-points：|err| top-N 点 + 自动标签（极值/转折点/高波动/普通）。

标签阈值均为该单元自身分布的分位数（pct，默认 0.95）——跨单元量纲不可比，
绝不 pool 阈值。标签可叠加；都不命中记「普通」。
"""
from __future__ import annotations

import argparse

import numpy as np
import pandas as pd

import chart_common as cc

RECIPE_ID = "worst-points"


def _annotate(d: pd.DataFrame, pct: float, vol_window: int) -> pd.DataFrame:
    """按 (unit, window) 序列算 |Δy| 与局部波动，阈值按 unit 分位数。"""
    d = d.sort_values(["unit_id", "window_ts", "horizon_step"]).copy()
    g = d.groupby(["unit_id", "window_ts"], sort=False)["y_true"]
    d["abs_dy"] = g.diff().abs()
    d["local_std"] = (g.rolling(vol_window, center=True, min_periods=2)
                      .std().reset_index(level=[0, 1], drop=True))
    for col, thr_col in (("abs_dy", "ramp_thr"), ("local_std", "vol_thr")):
        d[thr_col] = d.groupby("unit_id")[col].transform(
            lambda s: s.quantile(pct))
    d["y_hi"] = d.groupby("unit_id")["y_true"].transform(
        lambda s: s.quantile(pct))
    d["y_lo"] = d.groupby("unit_id")["y_true"].transform(
        lambda s: s.quantile(1 - pct))
    d["y_quantile"] = d.groupby("unit_id")["y_true"].rank(pct=True)
    return d


def _labels(row) -> list[str]:
    lab = []
    if row.y_true >= row.y_hi or row.y_true <= row.y_lo:
        lab.append("极值")
    if np.isfinite(row.abs_dy) and row.abs_dy >= row.ramp_thr:
        lab.append("转折点")
    if np.isfinite(row.local_std) and row.local_std >= row.vol_thr:
        lab.append("高波动")
    return lab or ["普通"]


def compute(df: pd.DataFrame, top_n: int = 20, freq: str = "15min",
            pct: float = 0.95, vol_window: int = 5) -> dict:
    base = _annotate(df[df["model"] == df["model"].iloc[0]]
                     [["unit_id", "window_ts", "horizon_step", "y_true"]]
                     .drop_duplicates(), pct, vol_window)
    key = ["unit_id", "window_ts", "horizon_step"]
    out = {"recipe": RECIPE_ID,
           "params": {"top_n": top_n, "pct": pct, "vol_window": vol_window},
           "models": {},
           "note": "标签阈值 = 单元自身 y_true/|Δy|/局部σ 的 pct 分位；可叠加。"}
    for m, g in df.groupby("model"):
        gg = g.merge(base[key + ["abs_dy", "local_std", "ramp_thr",
                                 "vol_thr", "y_hi", "y_lo", "y_quantile"]],
                     on=key, how="left")
        top = gg.reindex(gg["err"].abs().sort_values(ascending=False).index) \
                .head(top_n)
        pts, counts = [], {}
        for row in top.itertuples():
            labs = _labels(row)
            for lb in labs:
                counts[lb] = counts.get(lb, 0) + 1
            target = row.window_ts + row.horizon_step * pd.Timedelta(freq)
            pts.append({
                "target_ts": str(target), "window_ts": str(row.window_ts),
                "unit": str(row.unit_id), "step": int(row.horizon_step),
                "y_true": round(float(row.y_true), 4),
                "y_pred": round(float(row.y_pred), 4),
                "err": round(float(row.err), 4), "labels": labs,
                "context": {
                    "abs_dy": (round(float(row.abs_dy), 4)
                               if np.isfinite(row.abs_dy) else None),
                    "local_std": (round(float(row.local_std), 4)
                                  if np.isfinite(row.local_std) else None),
                    "y_quantile": round(float(row.y_quantile), 3)},
            })
        out["models"][str(m)] = {
            "points": pts,
            "label_share": {k: round(v / max(len(pts), 1), 3)
                            for k, v in sorted(counts.items())}}
    return out


def render(stats: dict):
    import matplotlib.pyplot as plt
    cc.setup_font()
    colors = {"极值": "firebrick", "转折点": "darkorange",
              "高波动": "purple", "普通": "gray"}
    models = list(stats["models"])
    fig, axes = plt.subplots(len(models), 1,
                             figsize=(11, 3 * len(models)), squeeze=False)
    for ax, m in zip(axes.ravel(), models):
        for p in stats["models"][m]["points"]:
            c = colors.get(p["labels"][0], "gray")
            ax.scatter(pd.Timestamp(p["target_ts"]), abs(p["err"]),
                       color=c, s=30)
        handles = [plt.Line2D([], [], marker="o", ls="", color=c, label=k)
                   for k, c in colors.items()]
        ax.legend(handles=handles, fontsize=7, ncol=4)
        ax.set_title(f"worst-points |err| top-{len(stats['models'][m]['points'])}"
                     f" — {m}", fontsize=10)
        ax.set_ylabel("|err|")
    fig.autofmt_xdate()
    fig.tight_layout()
    return fig


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--pred", required=True)
    ap.add_argument("--out-dir", required=True)
    ap.add_argument("--top-n", type=int, default=20)
    ap.add_argument("--freq", default="15min")
    ap.add_argument("--pct", type=float, default=0.95)
    ap.add_argument("--vol-window", type=int, default=5)
    a = ap.parse_args(argv)
    stats = compute(cc.load_predictions(a.pred), top_n=a.top_n, freq=a.freq,
                    pct=a.pct, vol_window=a.vol_window)
    cc.save_outputs(render(stats), a.out_dir, RECIPE_ID, stats)


if __name__ == "__main__":
    main()
```

实现提示：`_annotate` 只对 y_true 序列做（与模型无关），因此取第一个模型的去重
(unit, window, step, y_true) 作 base——若各模型 y_true 不一致（适配器错误），
merge 后 labels 仍按 base 算，这是可接受近似；recipe 判读节须写明。

- [ ] **Step 4: 跑测试确认通过**

Run: `python3 -m pytest ts-diagnose/chartbook/tests/test_chart_worst_points.py -q`
Expected: PASS（3 passed）

- [ ] **Step 5: 写 `recipes/worst-points.md`**

````markdown
---
id: worst-points
needs_materials: [predict, truth]
适用问题: 误差最大的 N 个点是什么性质——极值、转折点(ramp)、还是高波动时段？
outputs:
  json: worst-points.json
  png: worst-points.png
json_schema: >
  每模型：points 列表（target_ts/window_ts/unit/step/y_true/y_pred/err/labels/
  context{abs_dy,local_std,y_quantile}）+ label_share 标签占比。
bridge_hooks: >
  「极值」占比高 → 幅值压缩类假设（RevIN/归一化裁剪），去 true-vs-pred-scatter 看
  高功率段 slope；「转折点」占比高 → 平滑/滞后类假设（模型对 ramp 反应慢）；
  「高波动」占比高 → 高频容量不足类假设（patch 太粗/下采样）。
验证步: 三单元各植入一类点（配误差 5、底噪 0.1；植入统计量为单元内最大值保证过阈值）→ top-3 恰为三点且标签命中（tests/test_chart_worst_points.py）
---

# worst-points：最差点定位与性质标签

## 适用问题
把「误差大」翻译成「误差发生在什么形态的真值上」——error-breakdown 找到最差单元格后，
用本图看单元格内部的点级性质。

## CLI 与参数
```bash
python3 chartbook/scripts/chart_worst_points.py \
  --pred predictions.parquet --out-dir <workdir>/charts \
  [--top-n 20] [--freq 15min] [--pct 0.95] [--vol-window 5]
```

## JSON schema
见 frontmatter。标签阈值均为**单元自身分布**的 pct 分位（跨单元不 pool）；
标签可叠加（一个尖峰点常同时是极值+转折点+高波动），label_share 分母是点数、
分子按标签计，故各标签占比之和可 >1。y_true 以首个模型的序列为准（各模型
y_true 应一致；不一致说明适配器有错，先回对账）。

## 判读
- label_share 由某一类主导（>0.6）→ 对应 bridge_hooks 里的候选机制；
- 三类都不占优、多为「普通」→ 候选：误差非形态驱动（外生事件/数据质量），
  回 error-breakdown 看时间聚集性；
- 同一 target_ts 在多模型的 points 里反复出现 → 候选：输入侧问题（所有模型
  同时受害），有 feature 材料时转 D 组图交叉。
只给候选假设；结论回 playbook 三道门。

## 验证步
见 frontmatter；context 三字段契约（abs_dy/local_std/y_quantile）被测试锁定。
````

- [ ] **Step 6: 跑一致性闸 + 全仓**

Run: `python3 -m pytest ts-diagnose/chartbook/tests/ -q && python3 -m pytest "<REPO>" -q`
Expected: 全绿。

- [ ] **Step 7: Commit**

```bash
git add ts-diagnose/chartbook/
git commit -m "feat(ts-diagnose): chartbook worst-points——top-N 误差点自动标签（极值/转折点/高波动）"
```

---

### Task 5: `horizon-degradation`（B 组：指标随 horizon 退化速度）

**Files:**
- Create: `ts-diagnose/chartbook/scripts/chart_horizon_degradation.py`
- Create: `ts-diagnose/chartbook/recipes/horizon-degradation.md`
- Create: `ts-diagnose/chartbook/tests/test_chart_horizon_degradation.py`

**Interfaces:**
- Consumes: Task 1 公共件
- Produces: `compute(df, early_frac=0.25, late_frac=0.25, collapse_mult=1.5) -> dict`；CLI `--pred --out-dir [--early-frac 0.25] [--late-frac 0.25] [--collapse-mult 1.5]`

- [ ] **Step 1: 写失败测试**

```python
"""horizon-degradation golden：解析式构造 48 步双模型——
A: s<24 恒 1.0，之后 1.0+0.1*(s-24)（早段斜率 0、晚段 0.1、U1 崩溃点 s=30）；
B: 2.0-0.01*s（缓降）。A/B 首个交叉在 s=31。全部必须回收。"""
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

import chart_horizon_degradation as chd  # noqa: E402
from synth import make_long, alt         # noqa: E402


def _target(m, s):
    if m == "A":
        return 1.0 if s < 24 else 1.0 + 0.1 * (s - 24)
    return 2.0 - 0.01 * s


def _df():
    df = make_long(["A", "B"], ["U1"], ["2024-01-01", "2024-01-02"], 48,
                   lambda m, u, w, s: alt(_target(m, s), s))
    df["window_ts"] = pd.to_datetime(df["window_ts"])
    df["err"] = df["y_pred"] - df["y_true"]
    return df


def test_slopes_recovered():
    st = chd.compute(_df())
    a = st["models"]["A"]
    assert abs(a["early_slope"]) < 1e-9
    assert np.isclose(a["late_slope"], 0.1)
    assert np.isclose(st["models"]["B"]["late_slope"], -0.01)


def test_crossing_and_collapse():
    st = chd.compute(_df())
    assert st["crossings"]["A|B"] == 31
    assert st["collapse_horizon"]["A"]["U1"] == 30
    assert st["collapse_horizon"]["B"]["U1"] is None


def test_curve_stats_present():
    st = chd.compute(_df())
    a = st["models"]["A"]["rmse_by_step"]
    assert np.isclose(a["curve"]["47"], 1.0 + 0.1 * 23)
    assert a["trend"] == "上升"


def test_main_writes_outputs(tmp_path):
    p = tmp_path / "pred.csv"
    _df().drop(columns=["err"]).to_csv(p, index=False)
    chd.main(["--pred", str(p), "--out-dir", str(tmp_path)])
    assert (tmp_path / "horizon-degradation.json").exists()
    assert (tmp_path / "horizon-degradation.png").exists()
```

- [ ] **Step 2: 跑测试确认失败**

Run: `python3 -m pytest ts-diagnose/chartbook/tests/test_chart_horizon_degradation.py -q`
Expected: FAIL（ModuleNotFoundError）

- [ ] **Step 3: 写 `chart_horizon_degradation.py`**

```python
"""horizon-degradation：指标随预报步退化——早/晚段斜率、模型交叉点、
per-unit 崩溃 horizon（短期准长期失效的量化）。"""
from __future__ import annotations

import argparse
from itertools import combinations

import numpy as np
import pandas as pd

import chart_common as cc

RECIPE_ID = "horizon-degradation"


def _rmse_by_step(g):
    return g.groupby("horizon_step")["err"].apply(
        lambda e: float(np.sqrt(np.mean(np.square(e))))).sort_index()


def compute(df: pd.DataFrame, early_frac: float = 0.25,
            late_frac: float = 0.25, collapse_mult: float = 1.5) -> dict:
    n_steps = int(df["horizon_step"].max()) + 1
    n_early = max(2, int(np.ceil(n_steps * early_frac)))
    n_late = max(2, int(np.ceil(n_steps * late_frac)))
    out = {"recipe": RECIPE_ID, "n_steps": n_steps,
           "params": {"early_frac": early_frac, "late_frac": late_frac,
                      "collapse_mult": collapse_mult,
                      "n_early": n_early, "n_late": n_late},
           "models": {}, "crossings": {}, "collapse_horizon": {},
           "note": "斜率=对应段最小二乘；崩溃点=首个 rmse>collapse_mult×早段均值"
                   "的 step（该单元该模型自身早段为基准，跨模型可比排名不比数值）。"}
    curves = {}
    for m, g in df.groupby("model"):
        rmse = _rmse_by_step(g)
        bias = g.groupby("horizon_step")["err"].mean().sort_index()
        v = rmse.values
        steps = np.arange(n_steps, dtype=float)
        out["models"][str(m)] = {
            "rmse_by_step": cc.curve_stats(v),
            "bias_by_step": cc.curve_stats(bias.values),
            "early_slope": round(float(np.polyfit(steps[:n_early],
                                                  v[:n_early], 1)[0]), 6),
            "late_slope": round(float(np.polyfit(steps[-n_late:],
                                                 v[-n_late:], 1)[0]), 6),
        }
        curves[str(m)] = v
        coll = {}
        for u, gu in g.groupby("unit_id"):
            vu = _rmse_by_step(gu).values
            base = float(np.mean(vu[:n_early]))
            over = np.nonzero(vu > collapse_mult * base)[0]
            coll[str(u)] = int(over[0]) if len(over) else None
        out["collapse_horizon"][str(m)] = coll
    for a, b in combinations(sorted(curves), 2):
        diff = curves[a] - curves[b]
        sign = np.sign(diff)
        nz = sign != 0
        cross = None
        prev = None
        for i in range(len(diff)):
            if not nz[i]:
                continue
            if prev is not None and sign[i] != prev:
                cross = i
                break
            prev = sign[i]
        out["crossings"][f"{a}|{b}"] = cross
    return out


def render(stats: dict):
    import matplotlib.pyplot as plt
    cc.setup_font()
    fig, axes = plt.subplots(2, 1, figsize=(10, 6), sharex=True)
    for m, s in stats["models"].items():
        for ax, key in zip(axes, ("rmse_by_step", "bias_by_step")):
            curve = s[key]["curve"]
            ax.plot([int(k) for k in curve], list(curve.values()), label=m)
    axes[0].set_ylabel("RMSE"), axes[1].set_ylabel("bias")
    axes[1].axhline(0, color="k", lw=0.5)
    axes[1].set_xlabel(f"预报步 (0–{stats['n_steps'] - 1})")
    axes[0].set_title("horizon-degradation 误差随预报时效")
    axes[0].legend(ncol=max(1, len(stats["models"])))
    return fig


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--pred", required=True)
    ap.add_argument("--out-dir", required=True)
    ap.add_argument("--early-frac", type=float, default=0.25)
    ap.add_argument("--late-frac", type=float, default=0.25)
    ap.add_argument("--collapse-mult", type=float, default=1.5)
    a = ap.parse_args(argv)
    stats = compute(cc.load_predictions(a.pred), early_frac=a.early_frac,
                    late_frac=a.late_frac, collapse_mult=a.collapse_mult)
    cc.save_outputs(render(stats), a.out_dir, RECIPE_ID, stats)


if __name__ == "__main__":
    main()
```

- [ ] **Step 4: 跑测试确认通过**

Run: `python3 -m pytest ts-diagnose/chartbook/tests/test_chart_horizon_degradation.py -q`
Expected: PASS（4 passed）

- [ ] **Step 5: 写 `recipes/horizon-degradation.md`**

````markdown
---
id: horizon-degradation
needs_materials: [predict, truth]
适用问题: 短期准长期崩？退化速度谁快？哪个单元在长 horizon 崩溃？模型排序在哪个步反转？
outputs:
  json: horizon-degradation.json
  png: horizon-degradation.png
json_schema: >
  每模型：rmse_by_step / bias_by_step（curve_stats）、early_slope / late_slope；
  全局：crossings（模型对→首个排序反转步）、collapse_horizon（模型→单元→崩溃步）。
bridge_hooks: >
  晚段斜率陡且早段平 → 长程依赖衰减类假设（attention 有效窗口/位置编码外推）；
  开头台阶（max_jump_idx 靠前）→ 起报对齐/输入延迟类假设；
  roughness 大（毛刺）→ 高频分量拟合类假设；交叉点存在 → 「哪个模型好」
  依赖考核 horizon 段——先问口径再下对比结论。
验证步: 解析式双模型（平坦+折线 vs 缓降）→ 早晚斜率、交叉步 31、崩溃步 30 精确回收（tests/test_chart_horizon_degradation.py）
---

# horizon-degradation：误差随预报时效退化

## 适用问题
「模型 A 比 B 好」是否随 horizon 反转；长期失效从哪一步开始、哪些单元先崩。

## CLI 与参数
```bash
python3 chartbook/scripts/chart_horizon_degradation.py \
  --pred predictions.parquet --out-dir <workdir>/charts \
  [--early-frac 0.25] [--late-frac 0.25] [--collapse-mult 1.5]
```

## JSON schema
见 frontmatter。崩溃点基准是**该单元该模型自身早段均值**——跨模型只比崩溃步的
排名/有无，不比数值（量纲纪律）。

## 判读
- `late_slope ≫ early_slope`（如 >5×）→ 候选：长程依赖衰减，有 model_code 材料时
  对照架构桥接假设（H-ID）验证；
- `crossings` 非空 → 候选：结论依赖口径——回 Stage 0 确认考核 horizon 段再比；
- `collapse_horizon` 集中在少数单元 → 候选：单元本地可预测性差，去
  error-breakdown 的 unit_band_rmse 交叉；
- `bias_by_step.trend == 上升/下降`（单调漂移）→ 候选：递推累积偏差类机制。
只给候选假设；结论回 playbook 三道门。

## 验证步
见 frontmatter；斜率用早/晚各 25% 段最小二乘，容差 1e-9/精确浮点。
````

- [ ] **Step 6: 跑一致性闸 + 全仓**

Run: `python3 -m pytest ts-diagnose/chartbook/tests/ -q && python3 -m pytest "<REPO>" -q`
Expected: 全绿。

- [ ] **Step 7: Commit**

```bash
git add ts-diagnose/chartbook/
git commit -m "feat(ts-diagnose): chartbook horizon-degradation——退化斜率+模型交叉点+崩溃 horizon"
```

---

### Task 6: `rolling-stability`（B 组：滚动 MAE/bias + 变点 + 日历分组）

**Files:**
- Create: `ts-diagnose/chartbook/scripts/chart_rolling_stability.py`
- Create: `ts-diagnose/chartbook/recipes/rolling-stability.md`
- Create: `ts-diagnose/chartbook/tests/test_chart_rolling_stability.py`

**Interfaces:**
- Consumes: Task 1 公共件（含 `row_rmse`、`downsample`）
- Produces: `compute(df, roll_days=7, max_cp=3, min_shift_frac=0.3, min_seg=5) -> dict`；CLI `--pred --out-dir [--roll-days 7] [--max-cp 3] [--min-shift-frac 0.3] [--min-seg 5]`

- [ ] **Step 1: 写失败测试**

```python
"""rolling-stability golden：60 天单模型，第 31 天起日 RMSE 从 1.0 跳 2.0 →
变点日期 2024-01-31（±0 天，构造是干净台阶）、before/after 均值与 shift 回收；
平坦段不得再报变点（阈值闸有牙）。"""
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

import chart_rolling_stability as crs  # noqa: E402
from synth import make_long, alt       # noqa: E402


def _df():
    days = pd.date_range("2024-01-01", periods=60, freq="D")
    windows = [d.strftime("%Y-%m-%d") for d in days]

    def err(m, u, w, s):
        day_idx = (pd.Timestamp(w) - days[0]).days
        return alt(1.0 if day_idx < 30 else 2.0, s)

    df = make_long(["A"], ["U1"], windows, 4, err)
    df["window_ts"] = pd.to_datetime(df["window_ts"])
    df["err"] = df["y_pred"] - df["y_true"]
    return df


def test_changepoint_recovered():
    st = crs.compute(_df())
    cps = st["models"]["A"]["changepoints"]
    assert len(cps) == 1
    cp = cps[0]
    assert cp["date"] == "2024-01-31"
    assert np.isclose(cp["before_mean"], 1.0)
    assert np.isclose(cp["after_mean"], 2.0)
    assert np.isclose(cp["shift"], 1.0)


def test_calendar_slices():
    st = crs.compute(_df())
    a = st["models"]["A"]
    assert np.isclose(a["by_month"]["2024-02"], 2.0)
    assert set(a["by_dayofweek"]) <= {"0", "1", "2", "3", "4", "5", "6"}


def test_series_and_curve_present():
    st = crs.compute(_df())
    a = st["models"]["A"]
    assert len(a["daily_rmse"]) == 60
    assert len(a["rolling_rmse"]) == 60
    # curve_stats 的 max_jump_idx 取跳变的左端点日（与变点 date=后段首日相邻一天）
    assert a["daily_curve"]["max_jump_idx"] == "2024-01-30"


def test_main_writes_outputs(tmp_path):
    p = tmp_path / "pred.csv"
    _df().drop(columns=["err"]).to_csv(p, index=False)
    crs.main(["--pred", str(p), "--out-dir", str(tmp_path)])
    assert (tmp_path / "rolling-stability.json").exists()
    assert (tmp_path / "rolling-stability.png").exists()
```

- [ ] **Step 2: 跑测试确认失败**

Run: `python3 -m pytest ts-diagnose/chartbook/tests/test_chart_rolling_stability.py -q`
Expected: FAIL（ModuleNotFoundError）

- [ ] **Step 3: 写 `chart_rolling_stability.py`**

```python
"""rolling-stability：日粒度 RMSE/bias 的滚动走势 + 二分分段变点检测 +
日历（月/星期）分组——性能是否随时间漂移、从哪天开始。

日指标 = 当日各行 row_rmse 的均值（行与行等权；与点级 pool 不同，量纲注意）。
变点：对日 RMSE 序列做贪心二分分段（SSE 增益最大处切），仅保留
|后段均值−前段均值| > min_shift_frac × 全序列 std 的切点，至多 max_cp 个。
零随机、零外部依赖，确定性可回收。
"""
from __future__ import annotations

import argparse

import numpy as np
import pandas as pd

import chart_common as cc

RECIPE_ID = "rolling-stability"


def _best_split(v: np.ndarray, min_seg: int):
    n = len(v)
    if n < 2 * min_seg:
        return None, 0.0
    total = float(np.sum((v - v.mean()) ** 2))
    best_i, best_gain = None, 0.0
    for i in range(min_seg, n - min_seg + 1):
        sse = (float(np.sum((v[:i] - v[:i].mean()) ** 2))
               + float(np.sum((v[i:] - v[i:].mean()) ** 2)))
        gain = total - sse
        if gain > best_gain:
            best_i, best_gain = i, gain
    return best_i, best_gain


def detect_changepoints(values: np.ndarray, dates: list[str],
                        max_cp: int, min_shift_frac: float,
                        min_seg: int) -> list[dict]:
    thr = min_shift_frac * float(np.std(values))
    segments = [(0, len(values))]
    found = []
    for _ in range(max_cp):
        cand = []
        for lo, hi in segments:
            i, gain = _best_split(values[lo:hi], min_seg)
            if i is not None:
                cand.append((gain, lo, hi, lo + i))
        cand.sort(reverse=True)
        accepted = False
        for gain, lo, hi, cut in cand:
            before = float(np.mean(values[lo:cut]))
            after = float(np.mean(values[cut:hi]))
            if abs(after - before) > thr:
                found.append({"date": dates[cut],
                              "before_mean": round(before, 4),
                              "after_mean": round(after, 4),
                              "shift": round(after - before, 4)})
                segments.remove((lo, hi))
                segments += [(lo, cut), (cut, hi)]
                accepted = True
                break
        if not accepted:
            break
    return sorted(found, key=lambda c: -abs(c["shift"]))


def compute(df: pd.DataFrame, roll_days: int = 7, max_cp: int = 3,
            min_shift_frac: float = 0.3, min_seg: int = 5) -> dict:
    rr = cc.row_rmse(df)
    rr["date"] = pd.to_datetime(rr["window_ts"]).dt.strftime("%Y-%m-%d")
    bias = df.groupby(["model", df["window_ts"].dt.strftime("%Y-%m-%d")])[
        "err"].mean()
    out = {"recipe": RECIPE_ID,
           "params": {"roll_days": roll_days, "max_cp": max_cp,
                      "min_shift_frac": min_shift_frac, "min_seg": min_seg},
           "models": {},
           "note": "日指标=当日各行 row_rmse 均值；变点=贪心二分分段+幅度阈值闸。"}
    for m, g in rr.groupby("model"):
        daily = g.groupby("date")["rmse"].mean().sort_index()
        rolling = daily.rolling(roll_days, min_periods=1).mean()
        dates = list(daily.index)
        dts = pd.to_datetime(daily.index)
        month = daily.groupby(dts.strftime("%Y-%m")).mean()
        dow = daily.groupby(dts.dayofweek.astype(str)).mean()
        st = cc.curve_stats(daily.values, index=dates)
        st["curve"] = cc.downsample(st["curve"])
        out["models"][str(m)] = {
            "daily_rmse": cc.downsample(
                {k: round(float(v), 4) for k, v in daily.items()}),
            "rolling_rmse": cc.downsample(
                {k: round(float(v), 4) for k, v in rolling.items()}),
            "daily_bias": cc.downsample(
                {k: round(float(v), 4) for k, v in bias[m].items()}),
            "changepoints": detect_changepoints(
                daily.values.astype(float), dates, max_cp,
                min_shift_frac, min_seg),
            "by_month": {k: round(float(v), 4) for k, v in month.items()},
            "by_dayofweek": {k: round(float(v), 4) for k, v in dow.items()},
            "daily_curve": st,
        }
    return out


def render(stats: dict):
    import matplotlib.pyplot as plt
    cc.setup_font()
    fig, ax = plt.subplots(figsize=(12, 4))
    for m, s in stats["models"].items():
        xs = pd.to_datetime(list(s["rolling_rmse"]))
        ax.plot(xs, list(s["rolling_rmse"].values()), label=f"{m} rolling")
        for cp in s["changepoints"]:
            ax.axvline(pd.Timestamp(cp["date"]), color="red", ls=":", lw=1)
    ax.set_ylabel("滚动日均 RMSE")
    ax.set_title("rolling-stability（红虚线=变点）")
    ax.legend()
    fig.autofmt_xdate()
    return fig


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--pred", required=True)
    ap.add_argument("--out-dir", required=True)
    ap.add_argument("--roll-days", type=int, default=7)
    ap.add_argument("--max-cp", type=int, default=3)
    ap.add_argument("--min-shift-frac", type=float, default=0.3)
    ap.add_argument("--min-seg", type=int, default=5)
    a = ap.parse_args(argv)
    stats = compute(cc.load_predictions(a.pred), roll_days=a.roll_days,
                    max_cp=a.max_cp, min_shift_frac=a.min_shift_frac,
                    min_seg=a.min_seg)
    cc.save_outputs(render(stats), a.out_dir, RECIPE_ID, stats)


if __name__ == "__main__":
    main()
```

- [ ] **Step 4: 跑测试确认通过**

Run: `python3 -m pytest ts-diagnose/chartbook/tests/test_chart_rolling_stability.py -q`
Expected: PASS（4 passed）

- [ ] **Step 5: 写 `recipes/rolling-stability.md`**

````markdown
---
id: rolling-stability
needs_materials: [predict, truth]
适用问题: 性能随时间稳不稳？从哪天开始变差？变点前后差多少？不同日历时段有无规律？
outputs:
  json: rolling-stability.json
  png: rolling-stability.png
json_schema: >
  每模型：daily_rmse / rolling_rmse / daily_bias（降采样序列）、changepoints
  （date/before_mean/after_mean/shift）、by_month、by_dayofweek、daily_curve
  （curve_stats，含 max_jump_idx）。
bridge_hooks: >
  存在显著变点且各模型同日变 → 数据侧事件类假设（输入源切换/单元扩容/限电），
  非模型问题；仅单模型变 → 该模型 checkpoint/服务侧类假设；
  by_month 峰值月 → 季节漂移，去 train-test-drift（有 train_y 时）交叉。
验证步: 60 天台阶（第 31 天 1.0→2.0）→ 变点日期/前后均值/shift 精确回收，平坦段零误报（tests/test_chart_rolling_stability.py）
---

# rolling-stability：时间稳定性与变点

## 适用问题
「模型是不是从某天开始变差」的量化；月度归因前先看这张图确认差是突变还是渐变。

## CLI 与参数
```bash
python3 chartbook/scripts/chart_rolling_stability.py \
  --pred predictions.parquet --out-dir <workdir>/charts \
  [--roll-days 7] [--max-cp 3] [--min-shift-frac 0.3] [--min-seg 5]
```

## JSON schema
见 frontmatter。日指标 = 当日各行 row_rmse 的**均值**（行等权），与点级 pool
口径不同——与其他图对数值时只比走势不比绝对值。

## 判读
- `changepoints` 非空且 `daily_curve.max_jump_idx` 紧邻首变点（max_jump_idx 是跳变
  左端点日、变点 date 是后段首日，正常相差一天）→ 台阶型突变，
  候选：外生事件——去 error-breakdown 看该月是否单一单元贡献；
- `changepoints` 空但 `daily_curve.trend == 上升` → 渐变漂移，候选：分布缓慢
  漂移/设备衰减，去 train-test-drift 交叉；
- `by_dayofweek` 有结构（工作日/周末分层）→ 候选：负荷/调度行为混入 y-label；
- 多模型 changepoints 同日 → 数据侧；仅一家 → 模型侧（bridge_hooks）。
只给候选假设；结论回 playbook 三道门。

## 验证步
见 frontmatter；变点检测为贪心二分分段 + `min_shift_frac×std` 幅度闸，
阈值闸有牙由「只报 1 个变点」断言锁定。
````

- [ ] **Step 6: 跑一致性闸 + 全仓**

Run: `python3 -m pytest ts-diagnose/chartbook/tests/ -q && python3 -m pytest "<REPO>" -q`
Expected: 全绿。

- [ ] **Step 7: Commit**

```bash
git add ts-diagnose/chartbook/
git commit -m "feat(ts-diagnose): chartbook rolling-stability——滚动走势+变点检测+日历分组"
```

---

### Task 7: `true-vs-pred-scatter`（C 组：真值-预测散点 slope/R²）

**Files:**
- Create: `ts-diagnose/chartbook/scripts/chart_true_vs_pred_scatter.py`
- Create: `ts-diagnose/chartbook/recipes/true-vs-pred-scatter.md`
- Create: `ts-diagnose/chartbook/tests/test_chart_true_vs_pred_scatter.py`

**Interfaces:**
- Consumes: Task 1 公共件
- Produces: `compute(df, n_bins=10) -> dict`；CLI `--pred --out-dir [--n-bins 10]`

- [ ] **Step 1: 写失败测试**

```python
"""true-vs-pred-scatter golden：构造 y_pred = 0.8*y_true + 0.5（无噪声）→
slope/intercept/R² 精确回收；pred_by_true_bin 单调。"""
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

import chart_true_vs_pred_scatter as cts  # noqa: E402
from synth import make_long               # noqa: E402


def _df():
    df = make_long(["A"], ["U1"], ["2024-01-01", "2024-01-02"], 50,
                   err_fn=lambda m, u, w, s: -0.2 * (10.0 + s) + 0.5,
                   y_fn=lambda w, u, s: 10.0 + s)
    df["window_ts"] = pd.to_datetime(df["window_ts"])
    df["err"] = df["y_pred"] - df["y_true"]
    return df


def test_slope_intercept_r2():
    st = cts.compute(_df())
    a = st["models"]["A"]
    assert np.isclose(a["slope"], 0.8)
    assert np.isclose(a["intercept"], 0.5)
    assert a["r2"] > 0.9999
    assert a["n"] == 100


def test_bins_monotone():
    st = cts.compute(_df())
    binned = st["models"]["A"]["pred_by_true_bin"]
    vals = list(binned.values())
    assert vals == sorted(vals)
    assert len(binned) >= 5


def test_constant_truth_raises():
    df = _df()
    df["y_true"] = 7.0
    with pytest.raises(ValueError, match="y_true"):
        cts.compute(df)


def test_main_writes_outputs(tmp_path):
    p = tmp_path / "pred.csv"
    _df().drop(columns=["err"]).to_csv(p, index=False)
    cts.main(["--pred", str(p), "--out-dir", str(tmp_path)])
    assert (tmp_path / "true-vs-pred-scatter.json").exists()
    assert (tmp_path / "true-vs-pred-scatter.png").exists()
```

- [ ] **Step 2: 跑测试确认失败**

Run: `python3 -m pytest ts-diagnose/chartbook/tests/test_chart_true_vs_pred_scatter.py -q`
Expected: FAIL（ModuleNotFoundError）

- [ ] **Step 3: 写 `chart_true_vs_pred_scatter.py`**

```python
"""true-vs-pred-scatter：真值-预测回归诊断——R² 管「齐不齐」（离散度），
slope 管「正不正」（系统性压低/抬高）；分位分箱看偏差沿功率段的形状。"""
from __future__ import annotations

import argparse

import numpy as np
import pandas as pd

import chart_common as cc

RECIPE_ID = "true-vs-pred-scatter"


def compute(df: pd.DataFrame, n_bins: int = 10) -> dict:
    out = {"recipe": RECIPE_ID, "models": {},
           "note": "slope<1 → 大值段被系统性压低；R² 低而 slope≈1 → 离散不齐；"
                   "pred_by_true_bin 看压低集中在高段还是全段。"}
    for m, g in df.groupby("model"):
        gg = g.dropna(subset=["y_true", "y_pred"])
        y, p = gg["y_true"].to_numpy(float), gg["y_pred"].to_numpy(float)
        if np.unique(y).size < 2:
            raise ValueError(f"模型 {m} 的 y_true 无方差，回归无意义"
                             "（检查适配器是否填错列）")
        slope, intercept = np.polyfit(y, p, 1)
        r2 = float(np.corrcoef(y, p)[0, 1] ** 2)
        dfb = pd.DataFrame({"y": y, "p": p, "e": p - y})
        dfb["bin"] = pd.qcut(dfb["y"], n_bins, duplicates="drop")
        gb = dfb.groupby("bin", observed=True)
        binned = gb.agg(y=("y", "mean"), p=("p", "mean"))
        resid = gb["e"].quantile([0.1, 0.5, 0.9]).unstack()
        out["models"][str(m)] = {
            "slope": round(float(slope), 6),
            "intercept": round(float(intercept), 6),
            "r2": round(r2, 6), "n": int(len(gg)),
            "true_max": round(float(y.max()), 4),
            "pred_max": round(float(p.max()), 4),
            "pred_by_true_bin": {f"{r.y:.2f}": round(float(r.p), 4)
                                 for r in binned.itertuples()},
            "resid_quantiles_by_bin": {
                f"{binned.loc[b, 'y']:.2f}": {
                    "p10": round(float(row[0.1]), 4),
                    "p50": round(float(row[0.5]), 4),
                    "p90": round(float(row[0.9]), 4)}
                for b, row in resid.iterrows()},
        }
    return out


def render_from_df(df: pd.DataFrame, stats: dict):
    import matplotlib.pyplot as plt
    cc.setup_font()
    models = list(stats["models"])
    fig, axes = plt.subplots(1, len(models),
                             figsize=(5.5 * len(models), 5), squeeze=False)
    for ax, m in zip(axes.ravel(), models):
        g = df[df["model"] == m].dropna(subset=["y_true", "y_pred"])
        s = stats["models"][m]
        ax.hexbin(g["y_true"], g["y_pred"], gridsize=60, cmap="viridis",
                  mincnt=1)
        lim = [0, max(float(g["y_true"].max()), float(g["y_pred"].max())) * 1.02]
        ax.plot(lim, lim, "r--", lw=1, label="y = x")
        ax.plot(lim, [s["slope"] * v + s["intercept"] for v in lim],
                color="orange", lw=1.5, label=f"slope={s['slope']:.3f}")
        ax.text(0.03, 0.95, f"R²={s['r2']:.4f}", transform=ax.transAxes,
                va="top", bbox=dict(fc="white", alpha=0.85))
        ax.set_xlabel("y_true"), ax.set_ylabel("y_pred")
        ax.set_title(f"true-vs-pred — {m}"), ax.legend(loc="lower right")
    fig.tight_layout()
    return fig


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--pred", required=True)
    ap.add_argument("--out-dir", required=True)
    ap.add_argument("--n-bins", type=int, default=10)
    a = ap.parse_args(argv)
    df = cc.load_predictions(a.pred)
    stats = compute(df, n_bins=a.n_bins)
    cc.save_outputs(render_from_df(df, stats), a.out_dir, RECIPE_ID, stats)


if __name__ == "__main__":
    main()
```

- [ ] **Step 4: 跑测试确认通过**

Run: `python3 -m pytest ts-diagnose/chartbook/tests/test_chart_true_vs_pred_scatter.py -q`
Expected: PASS（4 passed）

- [ ] **Step 5: 写 `recipes/true-vs-pred-scatter.md`**

````markdown
---
id: true-vs-pred-scatter
needs_materials: [predict, truth]
适用问题: 预测系统性偏低/偏高？大值段被压低？误差是「不齐」还是「不正」？
outputs:
  json: true-vs-pred-scatter.json
  png: true-vs-pred-scatter.png
json_schema: >
  每模型：slope / intercept / r2 / n / true_max / pred_max、pred_by_true_bin
  （真值分位箱均值→预测均值）、resid_quantiles_by_bin（每箱残差 p10/p50/p90）。
bridge_hooks: >
  slope<1 且压低集中高段 → 幅值压缩类假设（归一化/RevIN 反变换、损失对大值欠罚）；
  slope≈1 而 R² 低 → 时序错位类假设（相位/滞后），去 worst-points 看转折点占比；
  intercept 显著非 0 → 基线偏置类假设。
验证步: 无噪声 y_pred=0.8y+0.5 → slope/intercept 精确回收、R²>0.9999、分箱单调（tests/test_chart_true_vs_pred_scatter.py）
---

# true-vs-pred-scatter：真值-预测回归诊断

## 适用问题
判读纪律：**R² 管齐不齐、slope 管正不正**——两者解耦，别混着下结论。

## CLI 与参数
```bash
python3 chartbook/scripts/chart_true_vs_pred_scatter.py \
  --pred predictions.parquet --out-dir <workdir>/charts [--n-bins 10]
```

## JSON schema
见 frontmatter；y_true 无方差时抛错（适配器填错列的常见症状，先回对账）。

## 判读
- `slope < 1`、`resid_quantiles_by_bin` 高段 p50 显著为负 → 候选：大值压低——
  对照 worst-points 的「极值」标签占比交叉；
- `r2` 低、slope≈1 → 候选：错位/离散——非幅值问题，去 intraday-profile 看
  bias 时段结构；
- 各模型 slope 都 <1 且接近 → 候选：共同的标签/输入侧原因，非单模型缺陷；
- `pred_by_true_bin` 在某箱折弯 → 候选：该功率段训练样本稀疏。
只给候选假设；结论回 playbook 三道门。

## 验证步
见 frontmatter。
````

- [ ] **Step 6: 跑一致性闸 + 全仓**

Run: `python3 -m pytest ts-diagnose/chartbook/tests/ -q && python3 -m pytest "<REPO>" -q`
Expected: 全绿。

- [ ] **Step 7: Commit**

```bash
git add ts-diagnose/chartbook/
git commit -m "feat(ts-diagnose): chartbook true-vs-pred-scatter——slope/R² 回归诊断+分箱残差"
```

---

### Task 8: `model-error-correlation`（C 组：模型间误差相关——同质化/互补性）

**Files:**
- Create: `ts-diagnose/chartbook/scripts/chart_model_error_correlation.py`
- Create: `ts-diagnose/chartbook/recipes/model-error-correlation.md`
- Create: `ts-diagnose/chartbook/tests/test_chart_model_error_correlation.py`

**Interfaces:**
- Consumes: Task 1 公共件（`row_rmse`）
- Produces: `compute(df, by_month=False) -> dict`；CLI `--pred --out-dir [--by-month]`

- [ ] **Step 1: 写失败测试**

```python
"""model-error-correlation golden：三模型行 RMSE 模式——A、B 逐窗完全同步
（corr=1，最同质对），C 与 A/B 正交交替（corr=0，最互补对）。<2 模型抛错。"""
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

import chart_model_error_correlation as cmc  # noqa: E402
from synth import make_long, alt             # noqa: E402


def _df():
    windows = [f"2024-01-{d:02d}" for d in range(1, 9)]   # 8 窗，idx=日-1

    def err(m, u, w, s):
        i = int(w[-2:]) - 1
        if m in ("A", "B"):
            amp = 1.0 if i % 2 == 0 else 2.0        # 1,2,1,2,...
        else:
            amp = 1.0 if (i // 2) % 2 == 0 else 2.0  # 1,1,2,2,...
        return alt(amp, s)

    df = make_long(["A", "B", "C"], ["U1"], windows, 4, err)
    df["window_ts"] = pd.to_datetime(df["window_ts"])
    df["err"] = df["y_pred"] - df["y_true"]
    return df


def test_corr_structure_recovered():
    st = cmc.compute(_df())
    corr = st["corr"]["all"]
    assert np.isclose(corr["A"]["B"], 1.0)
    assert abs(corr["A"]["C"]) < 1e-9
    assert st["most_redundant"]["pair"] == ["A", "B"]
    assert "C" in st["most_complementary"]["pair"]
    assert abs(st["most_complementary"]["corr"]) < 1e-9
    assert st["n_samples"] == 8


def test_single_model_raises():
    df = _df()
    with pytest.raises(ValueError, match="2"):
        cmc.compute(df[df["model"] == "A"])


def test_main_writes_outputs(tmp_path):
    p = tmp_path / "pred.csv"
    _df().drop(columns=["err"]).to_csv(p, index=False)
    cmc.main(["--pred", str(p), "--out-dir", str(tmp_path)])
    assert (tmp_path / "model-error-correlation.json").exists()
    assert (tmp_path / "model-error-correlation.png").exists()
```

- [ ] **Step 2: 跑测试确认失败**

Run: `python3 -m pytest ts-diagnose/chartbook/tests/test_chart_model_error_correlation.py -q`
Expected: FAIL（ModuleNotFoundError）

- [ ] **Step 3: 写 `chart_model_error_correlation.py`**

```python
"""model-error-correlation：模型间逐样本 RMSE 相关——高相关=同质化
（组合增益有限），低相关=互补（动态选模/加权有空间）。"""
from __future__ import annotations

import argparse
from itertools import combinations

import numpy as np
import pandas as pd

import chart_common as cc

RECIPE_ID = "model-error-correlation"


def _pivot(df: pd.DataFrame) -> pd.DataFrame:
    rr = cc.row_rmse(df)
    piv = rr.pivot_table(index=["unit_id", "window_ts"], columns="model",
                         values="rmse").dropna()
    if piv.shape[1] < 2:
        raise ValueError("模型间相关至少需要 2 个模型的对齐样本")
    return piv


def compute(df: pd.DataFrame, by_month: bool = False) -> dict:
    piv = _pivot(df)
    corr = piv.corr()
    pairs = {(a, b): float(corr.loc[a, b])
             for a, b in combinations(sorted(corr.columns), 2)}
    comp = min(pairs, key=pairs.get)
    red = max(pairs, key=pairs.get)
    out = {"recipe": RECIPE_ID, "n_samples": int(len(piv)),
           "corr": {"all": {a: {b: round(float(corr.loc[a, b]), 4)
                                for b in corr.columns}
                            for a in corr.columns}},
           "most_complementary": {"pair": list(comp),
                                  "corr": round(pairs[comp], 4)},
           "most_redundant": {"pair": list(red),
                              "corr": round(pairs[red], 4)},
           "note": "相关>0.95 → 高度同质化，ensemble 组合增益有限；"
                   "最互补对是动态选模/加权的首选组合。"}
    if by_month:
        months = piv.index.get_level_values("window_ts").to_period("M")
        for mo in sorted(set(months)):
            sub = piv[months == mo]
            if len(sub) >= 3:
                c = sub.corr()
                out["corr"][str(mo)] = {a: {b: round(float(c.loc[a, b]), 4)
                                            for b in c.columns}
                                        for a in c.columns}
    return out


def render(stats: dict):
    import matplotlib.pyplot as plt
    cc.setup_font()
    names = list(stats["corr"]["all"])
    mat = np.array([[stats["corr"]["all"][a][b] for b in names]
                    for a in names], float)
    fig, ax = plt.subplots(figsize=(1.2 * len(names) + 2.5,
                                    1.2 * len(names) + 2))
    im = ax.imshow(mat, vmin=-1, vmax=1, cmap="RdYlGn_r")
    ax.set_xticks(range(len(names)), names, rotation=45, fontsize=8)
    ax.set_yticks(range(len(names)), names, fontsize=8)
    for i in range(len(names)):
        for j in range(len(names)):
            ax.text(j, i, f"{mat[i, j]:.2f}", ha="center", va="center",
                    fontsize=8)
    ax.set_title("model-error-correlation 逐样本 RMSE 相关")
    fig.colorbar(im, ax=ax, shrink=0.8)
    fig.tight_layout()
    return fig


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--pred", required=True)
    ap.add_argument("--out-dir", required=True)
    ap.add_argument("--by-month", action="store_true")
    a = ap.parse_args(argv)
    stats = compute(cc.load_predictions(a.pred), by_month=a.by_month)
    cc.save_outputs(render(stats), a.out_dir, RECIPE_ID, stats)


if __name__ == "__main__":
    main()
```

- [ ] **Step 4: 跑测试确认通过**

Run: `python3 -m pytest ts-diagnose/chartbook/tests/test_chart_model_error_correlation.py -q`
Expected: PASS（3 passed）

- [ ] **Step 5: 写 `recipes/model-error-correlation.md`**

````markdown
---
id: model-error-correlation
needs_materials: [predict, truth]
适用问题: 多个模型是同质还是互补？组合/动态选模有没有空间？谁和谁犯同样的错？
outputs:
  json: model-error-correlation.json
  png: model-error-correlation.png
json_schema: >
  corr.all 全周期相关矩阵（--by-month 时另有逐月矩阵）、most_complementary /
  most_redundant（模型对+相关值）、n_samples。
bridge_hooks: >
  全对高相关（>0.95）→ 共享输入/共享标签缺陷类假设（错在数据不在模型）；
  某对独低 → 架构差异真实有效，对照 model-profile 上下文的架构差异点；
  逐月相关骤变月 → 该月外生事件，去 rolling-stability 变点交叉。
验证步: 三模型植入 A≡B、C 正交 → corr(A,B)=1、corr(A,C)=0、最同质/最互补对回收（tests/test_chart_model_error_correlation.py）
---

# model-error-correlation：模型同质化/互补性

## 适用问题
模型对比归因的前置事实：差距是「一个更强」还是「各错各的」——后者才有组合空间。

## CLI 与参数
```bash
python3 chartbook/scripts/chart_model_error_correlation.py \
  --pred predictions.parquet --out-dir <workdir>/charts [--by-month]
```
样本 = (unit, window) 的行 RMSE；各模型须对齐（缺任一模型的样本被 drop）。

## JSON schema
见 frontmatter；n_samples 是对齐后样本量，先看它够不够（<30 不下断言）。

## 判读
- 所有对 >0.95 → 候选：同质化——ensemble 增益有限；差距归因应转向数据/标签侧；
- `most_complementary.corr` < 0.5 → 候选：互补——去 oracle-gap 量化动态选模空间；
- 与 oracle-gap 的 pick_share 联判：互补且 pick_share 分散 → 组合空间实锤（仍属
  现象，机制回三道门）。
只给候选假设；结论回 playbook 三道门。

## 验证步
见 frontmatter；<2 模型抛 ValueError 的契约被测试锁定。
````

- [ ] **Step 6: 跑一致性闸 + 全仓**

Run: `python3 -m pytest ts-diagnose/chartbook/tests/ -q && python3 -m pytest "<REPO>" -q`
Expected: 全绿。

- [ ] **Step 7: Commit**

```bash
git add ts-diagnose/chartbook/
git commit -m "feat(ts-diagnose): chartbook model-error-correlation——同质化/互补性相关矩阵"
```

---

### Task 9: `worst-slice-compare`（C 组：焦点模型最差片上的同期对比）

**Files:**
- Create: `ts-diagnose/chartbook/scripts/chart_worst_slice_compare.py`
- Create: `ts-diagnose/chartbook/recipes/worst-slice-compare.md`
- Create: `ts-diagnose/chartbook/tests/test_chart_worst_slice_compare.py`

**Interfaces:**
- Consumes: Task 1 公共件（`row_rmse`、`downsample`）
- Produces: `compute(df, focal_model, slice_by="month") -> dict`；CLI `--pred --out-dir --focal-model <名> [--slice-by month]`

- [ ] **Step 1: 写失败测试**

```python
"""worst-slice-compare golden：A 仅 2024-02 差（RMSE 3，其余 1），B 恒 1 →
最差片=2024-02、片内 A=3/B=1、gap 全部集中该片（concentration_ratio=1）。"""
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

import chart_worst_slice_compare as cwsc  # noqa: E402
from synth import make_long, alt          # noqa: E402


def _df():
    windows = [f"2024-{mm:02d}-{dd:02d}" for mm in (1, 2, 3)
               for dd in (5, 15, 25)]

    def err(m, u, w, s):
        amp = 3.0 if (m == "A" and w.startswith("2024-02")) else 1.0
        return alt(amp, s)

    df = make_long(["A", "B"], ["U1"], windows, 4, err)
    df["window_ts"] = pd.to_datetime(df["window_ts"])
    df["err"] = df["y_pred"] - df["y_true"]
    return df


def test_worst_slice_and_compare():
    st = cwsc.compute(_df(), focal_model="A")
    assert st["worst_slice"] == "2024-02"
    assert np.isclose(st["in_slice"]["A"], 3.0)
    assert np.isclose(st["in_slice"]["B"], 1.0)
    assert np.isclose(st["slice_gaps"]["2024-02"], 2.0)
    assert np.isclose(st["slice_gaps"]["2024-01"], 0.0)
    assert np.isclose(st["concentration_ratio"], 1.0)
    assert "2024-02-15" in st["daily_in_slice"]["A"]


def test_unknown_focal_raises():
    with pytest.raises(ValueError, match="focal"):
        cwsc.compute(_df(), focal_model="Z")


def test_single_model_raises():
    df = _df()
    with pytest.raises(ValueError, match="2"):
        cwsc.compute(df[df["model"] == "A"], focal_model="A")


def test_main_writes_outputs(tmp_path):
    p = tmp_path / "pred.csv"
    _df().drop(columns=["err"]).to_csv(p, index=False)
    cwsc.main(["--pred", str(p), "--out-dir", str(tmp_path),
               "--focal-model", "A"])
    assert (tmp_path / "worst-slice-compare.json").exists()
    assert (tmp_path / "worst-slice-compare.png").exists()
```

- [ ] **Step 2: 跑测试确认失败**

Run: `python3 -m pytest ts-diagnose/chartbook/tests/test_chart_worst_slice_compare.py -q`
Expected: FAIL（ModuleNotFoundError）

- [ ] **Step 3: 写 `chart_worst_slice_compare.py`**

```python
"""worst-slice-compare：焦点模型最差片（默认按月）上的全模型同期对比——
「A 输掉的是一个月还是整个周期」。片指标 = 片内行 RMSE 均值。"""
from __future__ import annotations

import argparse

import numpy as np
import pandas as pd

import chart_common as cc

RECIPE_ID = "worst-slice-compare"


def compute(df: pd.DataFrame, focal_model: str,
            slice_by: str = "month") -> dict:
    models = sorted(df["model"].unique())
    if focal_model not in models:
        raise ValueError(f"focal_model {focal_model!r} 不在数据模型集 {models}")
    if len(models) < 2:
        raise ValueError("同期对比至少需要 2 个模型")
    rr = cc.row_rmse(df)
    if slice_by != "month":
        raise ValueError("v1 仅支持 slice_by=month")
    rr["slice"] = pd.to_datetime(rr["window_ts"]).dt.strftime("%Y-%m")
    rr["date"] = pd.to_datetime(rr["window_ts"]).dt.strftime("%Y-%m-%d")
    focal = rr[rr["model"] == focal_model]
    basis = focal.groupby("slice")["rmse"].mean().sort_index()
    worst = str(basis.idxmax())
    per = rr.groupby(["slice", "model"])["rmse"].mean().unstack()
    others = [m for m in models if m != focal_model]
    gaps = (per[focal_model] - per[others].min(axis=1)).fillna(0.0)
    pos = gaps.clip(lower=0.0)
    conc = (round(float(pos[worst] / pos.sum()), 4)
            if float(pos.sum()) > 0 else None)
    sl = rr[rr["slice"] == worst]
    daily = sl.groupby(["model", "date"])["rmse"].mean()
    return {
        "recipe": RECIPE_ID, "focal": focal_model, "slice_by": slice_by,
        "worst_slice": worst,
        "basis": {k: round(float(v), 4) for k, v in basis.items()},
        "overall": {m: round(float(v), 4)
                    for m, v in rr.groupby("model")["rmse"].mean().items()},
        "in_slice": {m: round(float(v), 4)
                     for m, v in sl.groupby("model")["rmse"].mean().items()},
        "daily_in_slice": {m: cc.downsample(
            {d: round(float(v), 4) for d, v in daily[m].items()})
            for m in models if m in daily.index.get_level_values(0)},
        "slice_gaps": {k: round(float(v), 4) for k, v in gaps.items()},
        "concentration_ratio": conc,
        "note": "片指标=片内行 RMSE 均值；gap=焦点−同片最优他模型；"
                "concentration_ratio→1 表示差距集中于最差片，→均匀表示普遍性落后。"}


def render(stats: dict):
    import matplotlib.pyplot as plt
    cc.setup_font()
    fig, axes = plt.subplots(1, 2, figsize=(13, 4.2),
                             gridspec_kw={"width_ratios": [2, 3]})
    models = list(stats["in_slice"])
    axes[0].bar(models, [stats["in_slice"][m] for m in models],
                color=["firebrick" if m == stats["focal"] else "steelblue"
                       for m in models])
    axes[0].set_title(f"最差片 {stats['worst_slice']} 内各模型 RMSE")
    for m, series in stats["daily_in_slice"].items():
        axes[1].plot(pd.to_datetime(list(series)), list(series.values()),
                     label=m, lw=1.5 if m == stats["focal"] else 0.9)
    axes[1].set_title("片内逐日对比"), axes[1].legend()
    fig.autofmt_xdate()
    fig.tight_layout()
    return fig


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--pred", required=True)
    ap.add_argument("--out-dir", required=True)
    ap.add_argument("--focal-model", required=True)
    ap.add_argument("--slice-by", default="month")
    a = ap.parse_args(argv)
    stats = compute(cc.load_predictions(a.pred), focal_model=a.focal_model,
                    slice_by=a.slice_by)
    cc.save_outputs(render(stats), a.out_dir, RECIPE_ID, stats)


if __name__ == "__main__":
    main()
```

- [ ] **Step 4: 跑测试确认通过**

Run: `python3 -m pytest ts-diagnose/chartbook/tests/test_chart_worst_slice_compare.py -q`
Expected: PASS（4 passed）

- [ ] **Step 5: 写 `recipes/worst-slice-compare.md`**

````markdown
---
id: worst-slice-compare
needs_materials: [predict, truth]
适用问题: 模型 A 最差的月份/片上，其他模型表现如何？A 的差距是集中爆发还是普遍落后？
outputs:
  json: worst-slice-compare.json
  png: worst-slice-compare.png
json_schema: >
  worst_slice（按焦点模型片 RMSE argmax）、basis（焦点逐片曲线）、overall /
  in_slice（各模型全期/片内指标）、daily_in_slice（片内逐日）、slice_gaps
  （逐片 焦点−最优他模型）、concentration_ratio（最差片 gap 占比）。
bridge_hooks: >
  concentration_ratio→1 且他模型片内不受影响 → 焦点模型特有机制（架构对该片
  形态失配），对照 model-profile 桥接假设；全模型片内同差 → 数据侧事件，
  去 rolling-stability 变点与 error-breakdown 交叉。
验证步: A 仅 2024-02 植入 3 倍误差 → 最差片、片内数值、gap 集中度 1.0 全回收（tests/test_chart_worst_slice_compare.py）
---

# worst-slice-compare：最差片同期对比

## 适用问题
「为什么 A 比 B 差」的切片化：先回答差在**哪儿**（集中 or 普遍），再谈为什么。

## CLI 与参数
```bash
python3 chartbook/scripts/chart_worst_slice_compare.py \
  --pred predictions.parquet --out-dir <workdir>/charts \
  --focal-model <模型名> [--slice-by month]
```
v1 仅支持按月切片；焦点模型必须在数据里（typo 直接抛错）。

## JSON schema
见 frontmatter；片指标 = 片内行 RMSE 均值（与 rolling-stability 同口径）。

## 判读
- `concentration_ratio > 0.7` → 差距集中：焦点模型在该片塌方——去该片跑
  worst-points 看点级性质、error-breakdown 看单元贡献；
- `concentration_ratio` 低（各片均摊）→ 普遍落后：候选为全局性机制（容量/
  损失/输入集差异），切片证据不再增益，转 horizon-degradation 与
  true-vs-pred-scatter；
- 片内逐日曲线他模型同步抬升（只是幅度小）→ 候选：共同外因+焦点更敏感。
只给候选假设；结论回 playbook 三道门。

## 验证步
见 frontmatter。
````

- [ ] **Step 6: 跑一致性闸 + 全仓**

Run: `python3 -m pytest ts-diagnose/chartbook/tests/ -q && python3 -m pytest "<REPO>" -q`
Expected: 全绿。

- [ ] **Step 7: Commit**

```bash
git add ts-diagnose/chartbook/
git commit -m "feat(ts-diagnose): chartbook worst-slice-compare——最差片同期对比+差距集中度"
```

---

### Task 10: `oracle-gap`（C 组：逐样本动态选优的提升空间）

**Files:**
- Create: `ts-diagnose/chartbook/scripts/chart_oracle_gap.py`
- Create: `ts-diagnose/chartbook/recipes/oracle-gap.md`
- Create: `ts-diagnose/chartbook/tests/test_chart_oracle_gap.py`

**Interfaces:**
- Consumes: Task 1 公共件（`row_rmse`、`downsample`）
- Produces: `compute(df, ensemble_key=None) -> dict`；CLI `--pred --out-dir [--ensemble-key <名>]`

- [ ] **Step 1: 写失败测试**

```python
"""oracle-gap golden：A 前 4 窗 RMSE 1/后 4 窗 2，B 相反 → 单模型均值 1.5、
oracle 均值 1.0、gap 0.5、pick_share 各 0.5。单模型抛错。"""
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

import chart_oracle_gap as cog    # noqa: E402
from synth import make_long, alt  # noqa: E402


def _df():
    windows = [f"2024-01-{d:02d}" for d in range(1, 9)]

    def err(m, u, w, s):
        i = int(w[-2:]) - 1
        first_half = i < 4
        amp = (1.0 if first_half else 2.0) if m == "A" else \
              (2.0 if first_half else 1.0)
        return alt(amp, s)

    df = make_long(["A", "B"], ["U1"], windows, 4, err)
    df["window_ts"] = pd.to_datetime(df["window_ts"])
    df["err"] = df["y_pred"] - df["y_true"]
    return df


def test_oracle_and_pick_share():
    st = cog.compute(_df())
    assert np.isclose(st["mean_rmse"]["A"], 1.5)
    assert np.isclose(st["mean_rmse"]["B"], 1.5)
    assert np.isclose(st["mean_rmse"]["oracle"], 1.0)
    assert np.isclose(st["best_single_minus_oracle"], 0.5)
    assert np.isclose(st["oracle_pick_share"]["A"], 0.5)
    assert np.isclose(st["oracle_pick_share"]["B"], 0.5)
    assert st["ensemble_minus_oracle"] is None


def test_single_model_raises():
    df = _df()
    with pytest.raises(ValueError, match="2"):
        cog.compute(df[df["model"] == "A"])


def test_main_writes_outputs(tmp_path):
    p = tmp_path / "pred.csv"
    _df().drop(columns=["err"]).to_csv(p, index=False)
    cog.main(["--pred", str(p), "--out-dir", str(tmp_path)])
    assert (tmp_path / "oracle-gap.json").exists()
    assert (tmp_path / "oracle-gap.png").exists()
```

- [ ] **Step 2: 跑测试确认失败**

Run: `python3 -m pytest ts-diagnose/chartbook/tests/test_chart_oracle_gap.py -q`
Expected: FAIL（ModuleNotFoundError）

- [ ] **Step 3: 写 `chart_oracle_gap.py`**

```python
"""oracle-gap：逐样本(unit×window)事后选最优单模型的 oracle 下界——
量化「动态选模/组合」的理论提升空间；ensemble 存在时另报 ensemble−oracle。"""
from __future__ import annotations

import argparse

import numpy as np
import pandas as pd

import chart_common as cc

RECIPE_ID = "oracle-gap"


def compute(df: pd.DataFrame, ensemble_key: str | None = None) -> dict:
    rr = cc.row_rmse(df)
    piv = rr.pivot_table(index=["unit_id", "window_ts"], columns="model",
                         values="rmse").dropna()
    singles = [c for c in piv.columns if c != ensemble_key]
    if len(singles) < 2:
        raise ValueError("oracle 至少需要 2 个（非 ensemble）模型的对齐样本")
    oracle = piv[singles].min(axis=1)
    picks = piv[singles].idxmin(axis=1)
    means = piv.mean()
    best_single = float(means[singles].min())
    dates = piv.index.get_level_values("window_ts").strftime("%Y-%m-%d")
    daily = piv.assign(oracle=oracle).groupby(dates).mean()
    return {
        "recipe": RECIPE_ID, "ensemble_key": ensemble_key,
        "n_samples": int(len(piv)),
        "mean_rmse": {**{str(m): round(float(v), 4)
                         for m, v in means.items()},
                      "oracle": round(float(oracle.mean()), 4)},
        "best_single_minus_oracle": round(best_single - float(oracle.mean()), 4),
        "ensemble_minus_oracle": (
            round(float(means[ensemble_key]) - float(oracle.mean()), 4)
            if ensemble_key in piv.columns else None),
        "oracle_pick_share": {str(k): round(float(v), 4)
                              for k, v in picks.value_counts(
                                  normalize=True).items()},
        "daily_rmse": {str(col): cc.downsample(
            {str(d): round(float(v), 4) for d, v in daily[col].items()})
            for col in daily.columns},
        "note": "gap 大 → 动态选模有空间；pick_share 看谁最常是逐样本最优；"
                "ensemble−oracle 大 → 现组合方式远未吃满互补性。"}


def render(stats: dict):
    import matplotlib.pyplot as plt
    cc.setup_font()
    fig, ax = plt.subplots(figsize=(12, 4))
    for col, series in stats["daily_rmse"].items():
        style = (dict(color="black", ls="--", lw=1.5) if col == "oracle"
                 else dict(lw=0.9))
        ax.plot(pd.to_datetime(list(series)), list(series.values()),
                label=col, **style)
    gap = stats["best_single_minus_oracle"]
    ax.set_title(f"oracle-gap（最优单模型−oracle 日均 = {gap:.3f}）")
    ax.set_ylabel("日均行 RMSE"), ax.legend(ncol=len(stats["daily_rmse"]))
    fig.autofmt_xdate()
    return fig


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--pred", required=True)
    ap.add_argument("--out-dir", required=True)
    ap.add_argument("--ensemble-key", default=None)
    a = ap.parse_args(argv)
    stats = compute(cc.load_predictions(a.pred), ensemble_key=a.ensemble_key)
    cc.save_outputs(render(stats), a.out_dir, RECIPE_ID, stats)


if __name__ == "__main__":
    main()
```

- [ ] **Step 4: 跑测试确认通过**

Run: `python3 -m pytest ts-diagnose/chartbook/tests/test_chart_oracle_gap.py -q`
Expected: PASS（3 passed）

- [ ] **Step 5: 写 `recipes/oracle-gap.md`**

````markdown
---
id: oracle-gap
needs_materials: [predict, truth]
适用问题: 逐样本动态选最优模型能提升多少？现有 ensemble 吃满互补性了吗？谁最常是最优？
outputs:
  json: oracle-gap.json
  png: oracle-gap.png
json_schema: >
  mean_rmse（各模型+oracle）、best_single_minus_oracle、ensemble_minus_oracle
  （无 ensemble 记 null）、oracle_pick_share、daily_rmse（各模型+oracle 逐日，降采样）、
  n_samples。
bridge_hooks: >
  gap 大且 pick_share 分散 → 互补性真实存在（与 model-error-correlation 低相关
  联判）；gap 大但 pick_share 一边倒 → 弱模型只在少数场景赢，查那些场景
  （worst-slice-compare）；ensemble−oracle ≈ best_single−oracle → 组合器没学到
  选择能力。
验证步: 双模型前后半期互为最优 → oracle 均值 1.0、gap 0.5、pick_share 0.5/0.5 回收（tests/test_chart_oracle_gap.py）
---

# oracle-gap：动态选优提升空间

## 适用问题
模型对比的收尾图：对比不是为了排名，是为了决定「换模型/组合/维持」——本图给
组合路线的收益上界。

## CLI 与参数
```bash
python3 chartbook/scripts/chart_oracle_gap.py \
  --pred predictions.parquet --out-dir <workdir>/charts [--ensemble-key ensemble]
```
oracle 是**事后**下界（作弊线），不是可部署策略——判读措辞里必须带这句。

## JSON schema
见 frontmatter；样本 = (unit, window) 对齐行（缺任一模型即 drop）。

## 判读
- `best_single_minus_oracle` 占 best_single 的比例 >15% → 候选：互补显著，
  组合路线值得投入——与 model-error-correlation 的低相关交叉后升「假设」；
- `oracle_pick_share` 某模型 <5% → 候选：该模型几乎无场景增益（下线候选），
  但先查它是否在特定片独赢（worst-slice-compare）；
- `daily_rmse` 里 oracle 与最优单模型曲线基本重合的时段 → 该时段无组合空间。
只给候选假设；结论回 playbook 三道门。

## 验证步
见 frontmatter。
````

- [ ] **Step 6: 跑一致性闸 + 全仓**

Run: `python3 -m pytest ts-diagnose/chartbook/tests/ -q && python3 -m pytest "<REPO>" -q`
Expected: 全绿。

- [ ] **Step 7: Commit**

```bash
git add ts-diagnose/chartbook/
git commit -m "feat(ts-diagnose): chartbook oracle-gap——动态选优空间+pick_share"
```

---

### Task 11: 示例适配器 golden + engine-core 豁免句 + layering 守卫 + CHANGELOG

**Files:**
- Create: `ts-diagnose/chartbook/golden/example_adapter/example_adapter.py`
- Create: `ts-diagnose/chartbook/tests/test_example_adapter.py`
- Modify: `ts-diagnose/references/engine-core.md`（「分析代码运行时生成」纪律处加 chartbook 豁免）
- Modify: `ts-diagnose/scripts/tests/test_layering.py`（新增 chartbook 层级守卫）
- Modify: `ts-diagnose/CHANGELOG.md`

**Interfaces:**
- Consumes: Task 1 `chart_common.load_predictions`；Task 2 `chart_error_breakdown.compute`（端到端冒烟）
- Produces: `example_adapter.to_long(wide_df, n_steps) -> pd.DataFrame`、`example_adapter.reconcile(wide_df, long_df, n_steps) -> dict`

- [ ] **Step 1: 写失败测试 `tests/test_example_adapter.py`**

```python
"""示例适配器 golden：非标宽表（每行一窗、y_0..y_3/p_0..p_3 列）→ 规范长表，
对账两关（行数守恒 + 抽 3 窗数值核对）必须可执行且有牙（篡改即报）。"""
import sys
from pathlib import Path

import pandas as pd
import pytest

CB = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(CB / "scripts"))
sys.path.insert(0, str(CB / "golden" / "example_adapter"))

import chart_common as cc            # noqa: E402
import example_adapter as ea         # noqa: E402


def _wide():
    rows = []
    for m in ("A", "B"):
        for d in (1, 2, 3):
            rows.append({"station": "S1", "ts": f"2024-01-0{d} 00:00",
                         "model": m,
                         **{f"y_{s}": 10.0 + s for s in range(4)},
                         **{f"p_{s}": 10.0 + s + (0.5 if m == "A" else 1.0)
                            for s in range(4)}})
    return pd.DataFrame(rows)


def test_to_long_shape_and_values():
    wide = _wide()
    long = ea.to_long(wide, n_steps=4)
    assert list(long.columns) == list(cc.REQUIRED_COLS)
    assert len(long) == len(wide) * 4
    one = long[(long["model"] == "A") & (long["horizon_step"] == 2)].iloc[0]
    assert one["y_true"] == 12.0 and one["y_pred"] == 12.5


def test_reconcile_passes_and_has_teeth():
    wide = _wide()
    long = ea.to_long(wide, n_steps=4)
    rep = ea.reconcile(wide, long, n_steps=4)
    assert rep["row_conservation"] is True and len(rep["spot_checks"]) == 3
    with pytest.raises(AssertionError):
        ea.reconcile(wide, long.iloc[:-1], n_steps=4)   # 少一行 → 守恒破
    bad = long.copy()
    bad.loc[bad.index[0], "y_pred"] += 99
    with pytest.raises(AssertionError):
        ea.reconcile(wide, bad, n_steps=4)              # 数值篡改 → 抽查破


def test_long_feeds_chartbook(tmp_path):
    import chart_error_breakdown as ceb
    long = ea.to_long(_wide(), n_steps=4)
    p = tmp_path / "pred.csv"
    long.to_csv(p, index=False)
    st = ceb.compute(cc.load_predictions(p))
    assert set(st["models"]) == {"A", "B"}
```

- [ ] **Step 2: 跑测试确认失败**

Run: `python3 -m pytest ts-diagnose/chartbook/tests/test_example_adapter.py -q`
Expected: FAIL（ModuleNotFoundError: example_adapter）

- [ ] **Step 3: 写 `golden/example_adapter/example_adapter.py`**

```python
"""示例薄适配器：非标宽表 → 规范长表 + 对账两关。

这是 intake 对账纪律（references/intake.md）的可执行样例：现场写 adapter.py 时
照此模式——to_long 只做重排不做清洗，reconcile 行数守恒 + 抽 3 窗数值核对，
过账后才准喂 chartbook 图脚本。
"""
from __future__ import annotations

import pandas as pd


def to_long(wide: pd.DataFrame, n_steps: int) -> pd.DataFrame:
    rows = []
    for r in wide.itertuples():
        for s in range(n_steps):
            rows.append({"window_ts": r.ts, "unit_id": r.station,
                         "model": r.model, "horizon_step": s,
                         "y_true": getattr(r, f"y_{s}"),
                         "y_pred": getattr(r, f"p_{s}")})
    return pd.DataFrame(rows, columns=["window_ts", "unit_id", "model",
                                       "horizon_step", "y_true", "y_pred"])


def reconcile(wide: pd.DataFrame, long: pd.DataFrame, n_steps: int) -> dict:
    """对账两关：①行数守恒；②抽前 3 个源行核对每步数值。返回报告 dict，
    任一关不过直接 AssertionError（绝不静默）。"""
    assert len(long) == len(wide) * n_steps, \
        f"行数守恒破产：long={len(long)} != wide={len(wide)}×{n_steps}"
    checks = []
    for r in wide.head(3).itertuples():
        sub = long[(long["window_ts"] == r.ts) & (long["model"] == r.model)
                   & (long["unit_id"] == r.station)]
        assert len(sub) == n_steps, f"窗口 {r.ts}/{r.model} 步数不齐"
        for s in range(n_steps):
            row = sub[sub["horizon_step"] == s].iloc[0]
            assert row["y_true"] == getattr(r, f"y_{s}"), \
                f"抽查失败 {r.ts}/{r.model} step{s} y_true"
            assert row["y_pred"] == getattr(r, f"p_{s}"), \
                f"抽查失败 {r.ts}/{r.model} step{s} y_pred"
        checks.append({"ts": str(r.ts), "model": str(r.model), "ok": True})
    return {"row_conservation": True, "spot_checks": checks}
```

- [ ] **Step 4: 跑测试确认通过**

Run: `python3 -m pytest ts-diagnose/chartbook/tests/test_example_adapter.py -q`
Expected: PASS（3 passed）

- [ ] **Step 5: engine-core.md 加 chartbook 豁免**

先 `grep -n "运行时生成" ts-diagnose/references/engine-core.md` 定位「分析代码运行时生成」
纪律所在段，在该段末尾追加（逐字）：

> **chartbook 豁免**：chartbook（`<ENGINE>/chartbook/`）已覆盖的图**必须**直接调用其
> 预写脚本 `chartbook/scripts/chart_*.py`，禁止现场重写同类图；运行时生成只用于
> chartbook 没有的 playbook 特有分析。现场唯一要写的画图相关代码是薄适配器
> `analysis_scripts/adapter.py`（用户数据 → 规范长表，样例见
> `chartbook/golden/example_adapter/`），先过对账两关（行数守恒 + 抽 3 窗核对）
> 再喂图脚本，对账记录写 PROGRESS.md。

- [ ] **Step 6: test_layering.py 加 chartbook 守卫**

在 `ts-diagnose/scripts/tests/test_layering.py` 末尾追加（读现有文件顶部的
`ENGINE_DIR` 常量复用之）：

```python
def test_chartbook_scripts_no_cross_skill_imports():
    """chartbook 是引擎级共享库：脚本不得引用 playbook 或任何专用技能目录。"""
    import glob
    forbidden = ("pv-result-analysis", "pv_result_analysis",
                 "pv-feature-blame", "pv-station-influence",
                 "pv-model-analysis", "playbooks/")
    scripts = glob.glob(os.path.join(ENGINE_DIR, "chartbook", "scripts", "*.py"))
    assert scripts, "chartbook/scripts 不应为空"
    for path in scripts:
        text = open(path, encoding="utf-8").read()
        for bad in forbidden:
            assert bad not in text, f"{os.path.basename(path)} 引用了 {bad}"


def test_chartbook_recipes_have_scripts():
    """每个 recipe 必有同名预写脚本（chart_<蛇形id>.py）。"""
    import glob
    recipes = glob.glob(os.path.join(ENGINE_DIR, "chartbook", "recipes", "*.md"))
    assert len(recipes) >= 9, "A-C 组 9 个 recipe 应已就位"
    for path in recipes:
        rid = os.path.splitext(os.path.basename(path))[0]
        script = os.path.join(ENGINE_DIR, "chartbook", "scripts",
                              f"chart_{rid.replace('-', '_')}.py")
        assert os.path.exists(script), f"recipe {rid} 缺预写脚本"
```

（若 test_layering.py 未 `import os` 则补上。）

- [ ] **Step 7: CHANGELOG 追加**

在 `ts-diagnose/CHANGELOG.md` 最新条目上方追加：

```markdown
## v2 chartbook 轮（A-C 组）
- 新增引擎级图谱库 `chartbook/`：规范长表接口（window_ts|unit_id|model|horizon_step|y_true|y_pred）、
  chart_common 公共件、_recipe-spec 规范 + 一致性闸；
- 9 个预写图脚本（A：error-breakdown/intraday-profile/worst-points；
  B：horizon-degradation/rolling-stability；C：true-vs-pred-scatter/
  model-error-correlation/worst-slice-compare/oracle-gap），全部合成植入回收 golden；
- 示例薄适配器 + 对账两关样例（golden/example_adapter）；engine-core 增 chartbook
  豁免（预写图禁现场重写）；layering 守卫扩展至 chartbook。
```

- [ ] **Step 8: 跑全部测试**

Run: `python3 -m pytest ts-diagnose/ -q && python3 -m pytest "<REPO>" -q`
Expected: 全绿（chartbook 测试 ≈35+，全仓 200+）。

- [ ] **Step 9: Commit**

```bash
git add ts-diagnose/chartbook/ ts-diagnose/references/engine-core.md \
        ts-diagnose/scripts/tests/test_layering.py ts-diagnose/CHANGELOG.md
git commit -m "feat(ts-diagnose): chartbook 收尾——示例适配器对账样例+engine-core 豁免+layering 守卫+CHANGELOG"
```

---

## 计划边界（本计划不做）

- D 组（feature 关联 3 图）、E 组（train-test-drift）→ Plan 3；
- model-comparison / fact-scan 两个 playbook、SKILL.md 路由表两行、
  pv-result-analysis description 反向负面清单 → Plan 3；
- orient.py 对 playbook `charts:` 声明的解析与可用性报告 → Plan 3
  （本计划的 recipe frontmatter `needs_materials` 已按 material id 就位，Plan 3 直接消费）。
