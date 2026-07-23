# ts-diagnose 证据可靠性加固 实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 堵图证据链的两个统计漏洞——worst-slice-compare 内置按日块置换基线（未超随机不点名切片）+ 新图 cross-dim-stability（时间对半/口径切换正交稳定性），并把 model-comparison 的「现象→假设」升级改为三条腿。

**Architecture:** 全部走 chartbook 预写脚本 + recipe + golden 测试的既有基础设施；引擎层只加文档纪律（mechanisms.md 证据维度、golden 种子豁免）；model-comparison playbook 消费两个新产物；golden 用伪 stage 键 `2-crossdim` 挂新参考实现。

**Tech Stack:** Python 3 + pandas/numpy/matplotlib（Agg）、pytest；纯标准库 `random.Random(seed)` 做置换（固定种子，决定论）。

**Spec:** `docs/superpowers/specs/2026-07-23-ts-diagnose-evidence-hardening-design.md`（含 2026-07-23 统计量修正：置换统计量 = 最差片正差距，非 concentration_ratio）。

## Global Constraints

- 分支：`feat/pv-result-analysis-weak-model-enforcement`，任何子代理不得切分支。
- **绝不触碰**：`row-diagnostic/` 的已有工作区改动、`docs/skill解析/`、`pv-*` 四个技能目录、`ts-diagnose/SKILL.md`、`playbooks/model-comparison/golden/make_golden.py` 与 `predictions.csv`、`chartbook/scripts/chart_common.py`。不 `git add -A`；每次只 add 本任务明确列出的文件。
- 置换决定论：种子必须是显式 CLI 参数（默认 `--perm-seed 0 --n-perm 200`）并写进产物 JSON；期望值来自同种子实跑。
- JSON 增量纪律：对现有产物只加字段（`perm`、note 追加），不改、不删既有字段——现有 manifest/测试的期望必须原样继续通过。
- 判读纪律：recipe「## 判读」只给候选假设；`not-significant` 时必须写"不点名切片"。
- 任务顺序 1→6 严格串行（Task 4 依赖 Task 2 的 recipe 存在，否则 playbook frontmatter 校验红；Task 5 依赖 Task 1+2 的脚本）。
- 每任务结束跑该任务声明的测试命令并全绿后才 commit。

---

### Task 1: worst-slice-compare 内置置换基线（脚本 + recipe + 测试）

**Files:**
- Modify: `ts-diagnose/chartbook/scripts/chart_worst_slice_compare.py`（整文件替换，见 Step 3）
- Modify: `ts-diagnose/chartbook/recipes/worst-slice-compare.md`（整文件替换，见 Step 5）
- Test: `ts-diagnose/chartbook/tests/test_chart_worst_slice_compare.py`（文件末尾追加，见 Step 1）

**Interfaces:**
- Consumes: `chart_common.row_rmse/load_predictions/downsample/save_outputs`（不改）。
- Produces: `compute(df, focal_model, slice_by="month", n_perm=200, perm_seed=0)`——JSON 新增顶层 `perm` 块 `{stat,n_perm,seed,real_stat,null_q95,perm_p,verdict,note}` 或 `None`（跳过原因追加进顶层 `note`）；CLI 新增 `--n-perm`（默认 200）、`--perm-seed`（默认 0）。既有字段（worst_slice/basis/overall/in_slice/daily_in_slice/slice_gaps/concentration_ratio）**一个不动**。Task 5 的 manifest 依赖 `perm.verdict/perm_p/real_stat/null_q95` 这些字段名。

- [ ] **Step 1: 追加失败测试**

在 `ts-diagnose/chartbook/tests/test_chart_worst_slice_compare.py` 文件末尾追加（不动已有内容）：

```python
def _df_perm():
    """置换基线专用加密版：8 日/月——A 的 8 个坏日全在 2024-02。
    随机重排把 8 个坏日重聚同一片的概率 ~4e-6 ⇒ perm_p 恰为 1/201，
    判定稳不依赖种子运气（3 日/月的原构造 null 概率 1/28，太贴 0.05 线）。"""
    windows = [f"2024-{mm:02d}-{dd:02d}" for mm in (1, 2, 3)
               for dd in (2, 5, 8, 11, 14, 17, 20, 23)]

    def err(m, u, w, s):
        amp = 3.0 if (m == "A" and w.startswith("2024-02")) else 1.0
        return alt(amp, s)

    df = make_long(["A", "B"], ["U1"], windows, 4, err)
    df["window_ts"] = pd.to_datetime(df["window_ts"])
    df["err"] = df["y_pred"] - df["y_true"]
    return df


def test_perm_significant_on_planted():
    st = cwsc.compute(_df_perm(), focal_model="A")
    perm = st["perm"]
    assert perm["stat"] == "worst_slice_gap"
    assert perm["n_perm"] == 200 and perm["seed"] == 0
    assert np.isclose(perm["real_stat"], 2.0)
    assert perm["perm_p"] < 0.05
    assert perm["null_q95"] < perm["real_stat"]
    assert perm["verdict"] == "significant"


def test_perm_not_significant_on_diffuse_decoy():
    """弥散诱饵：A 各月同幅小差 → 任意重排统计量不变 → perm_p 精确 = 1.0。
    防「逢集中必点名」——conc 描述量照算，但置换判 not-significant。"""
    windows = [f"2024-{mm:02d}-{dd:02d}" for mm in (1, 2, 3)
               for dd in (5, 15, 25)]
    df = make_long(["A", "B"], ["U1"], windows, 4,
                   lambda m, u, w, s: alt(1.2 if m == "A" else 1.0, s))
    df["window_ts"] = pd.to_datetime(df["window_ts"])
    df["err"] = df["y_pred"] - df["y_true"]
    st = cwsc.compute(df, focal_model="A")
    assert st["perm"]["verdict"] == "not-significant"
    assert np.isclose(st["perm"]["perm_p"], 1.0)


def test_perm_skipped_when_focal_never_behind():
    """焦点全面领先 → 最差片无正差距 → perm 置 null、原因进 note。"""
    st = cwsc.compute(_df(), focal_model="B")
    assert st["perm"] is None
    assert "perm 未做" in st["note"]


def test_perm_disabled_flag():
    st = cwsc.compute(_df_perm(), focal_model="A", n_perm=0)
    assert st["perm"] is None
    assert "n_perm=0" in st["note"]
```

- [ ] **Step 2: 跑测试确认失败**

Run: `python3 -m pytest ts-diagnose/chartbook/tests/test_chart_worst_slice_compare.py -v`
Expected: 新增 4 个测试 FAIL（`KeyError: 'perm'` / TypeError n_perm），原有 4 个 PASS。

- [ ] **Step 3: 整文件替换 chart_worst_slice_compare.py**

```python
"""worst-slice-compare：焦点模型最差片（默认按月）上的全模型同期对比——
「A 输掉的是一个月还是整个周期」。片指标 = 片内行 RMSE 均值。
内置置换基线：最差片正差距按日块置换检验——未超随机基线不许点名切片。"""
from __future__ import annotations

import argparse
import random

import numpy as np
import pandas as pd

import chart_common as cc

RECIPE_ID = "worst-slice-compare"


def _worst_gap_stat(rr: pd.DataFrame, focal_model: str, others: list) -> float:
    """统计量：焦点自身最差片（片 RMSE argmax）上的正差距（焦点−同片最优他模型）。
    不用 concentration_ratio 做统计量——正差稀疏时任意重排的占比仍近 1（null
    退化无检验力）；坏日被打散后片均值被稀释，gap 幅度才有检验力。"""
    focal = rr[rr["model"] == focal_model]
    basis = focal.groupby("slice")["rmse"].mean()
    worst = basis.idxmax()
    per = rr.groupby(["slice", "model"])["rmse"].mean().unstack()
    gaps = (per[focal_model] - per[others].min(axis=1)).fillna(0.0)
    return float(gaps.clip(lower=0.0)[worst])


def _perm_baseline(rr, focal_model, others, n_perm, seed):
    """→ (perm 块 | None, 跳过原因)。按日块置换，片日数配额保持。"""
    real = _worst_gap_stat(rr, focal_model, others)
    if real <= 0:
        return None, "焦点最差片无正差距（焦点未落后），置换基线不适用"
    if n_perm <= 0:
        return None, "n_perm=0 显式关闭"
    slice_of_date = (rr.drop_duplicates("date")
                     .set_index("date")["slice"].sort_index())
    quota = slice_of_date.value_counts().sort_index()
    dates = list(slice_of_date.index)
    if len(quota) < 2:
        return None, "切片数 < 2，置换无意义"
    if len(dates) < len(quota):
        return None, "日块数少于切片数，置换无意义"
    rng = random.Random(seed)
    null = []
    for _ in range(n_perm):
        shuffled = dates[:]
        rng.shuffle(shuffled)
        mapping, i = {}, 0
        for sl, k in quota.items():
            for d in shuffled[i:i + int(k)]:
                mapping[d] = sl
            i += int(k)
        pr = rr.assign(slice=rr["date"].map(mapping))
        null.append(_worst_gap_stat(pr, focal_model, others))
    p = (1 + sum(1 for c in null if c >= real)) / (n_perm + 1)
    return {"stat": "worst_slice_gap", "n_perm": n_perm, "seed": seed,
            "real_stat": round(real, 4),
            "null_q95": round(float(np.quantile(null, 0.95)), 4),
            "perm_p": round(p, 4),
            "verdict": "significant" if p < 0.05 else "not-significant",
            "note": "按日块置换、片日数配额保持；月内跨日相关未校正——"
                    "significant 是点名的必要条件而非充分证明"}, None


def compute(df: pd.DataFrame, focal_model: str, slice_by: str = "month",
            n_perm: int = 200, perm_seed: int = 0) -> dict:
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
    perm, skip = _perm_baseline(rr, focal_model, others, n_perm, perm_seed)
    note = ("片指标=片内行 RMSE 均值；gap=焦点−同片最优他模型；"
            "concentration_ratio→1 表示差距集中于最差片，→均匀表示普遍性落后。")
    if perm is None:
        note += f"perm 未做：{skip}。"
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
        "perm": perm,
        "note": note}


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
    ap.add_argument("--n-perm", type=int, default=200)
    ap.add_argument("--perm-seed", type=int, default=0)
    a = ap.parse_args(argv)
    stats = compute(cc.load_predictions(a.pred), focal_model=a.focal_model,
                    slice_by=a.slice_by, n_perm=a.n_perm, perm_seed=a.perm_seed)
    cc.save_outputs(render(stats), a.out_dir, RECIPE_ID, stats)


if __name__ == "__main__":
    main()
```

（相对原文件：模块头注释加一行；新增 `random`/`numpy` 导入与 `_worst_gap_stat`/`_perm_baseline` 两函数；`compute` 加 `n_perm`/`perm_seed` 参数、`perm` 字段与 note 追加逻辑；`main` 加两个 CLI 参数。`render` 与其余字段逐字不变。`_worst_gap_stat` 与 `compute` 有 4 行相似代码——刻意保留：置换循环需要独立函数，而 `compute` 的 basis/gaps 还要进 JSON，共享会把返回值搅在一起。）

- [ ] **Step 4: 跑测试确认通过**

Run: `python3 -m pytest ts-diagnose/chartbook/tests/test_chart_worst_slice_compare.py -v`
Expected: 8 个全 PASS（含原有 4 个——既有字段与数值零变化）。

- [ ] **Step 5: 整文件替换 recipes/worst-slice-compare.md**

````markdown
---
id: worst-slice-compare
needs_materials: [predict, truth]
适用问题: 模型 A 最差的月份/片上，其他模型表现如何？差距是集中爆发还是普遍落后？该集中超出随机了吗？
outputs:
  json: worst-slice-compare.json
  png: worst-slice-compare.png
json_schema: >
  worst_slice（按焦点模型片 RMSE argmax）、basis（焦点逐片曲线）、overall /
  in_slice（各模型全期/片内指标）、daily_in_slice（片内逐日）、slice_gaps
  （逐片 焦点−最优他模型）、concentration_ratio（最差片 gap 占比，描述量）、
  perm（最差片正差距的按日块置换基线：stat/real_stat/null_q95/perm_p/verdict；
  不适用时为 null 且原因追加在 note）。
bridge_hooks: >
  perm.verdict=significant 且 concentration_ratio→1 且他模型片内不受影响 →
  焦点模型特有机制（架构对该片形态失配），对照 model-profile 桥接假设；
  全模型片内同差 → 数据侧事件，去 rolling-stability 变点与 error-breakdown
  交叉；perm.verdict=not-significant → 集中叙事不成立，不点名切片。
验证步: A 仅 2024-02 植入 3 倍误差 → 最差片、片内数值、gap 集中度 1.0 全回收；8日/月加密版置换基线 significant（perm_p=1/201）；弥散诱饵（各月同幅小差）必须 not-significant（tests/test_chart_worst_slice_compare.py）
---

# worst-slice-compare：最差片同期对比

## 适用问题
「为什么 A 比 B 差」的切片化：先回答差在**哪儿**（集中 or 普遍），再回答该集中
**超出随机了吗**（置换基线）——切片够多时「最差片」必然存在，未过基线不许点名。

## CLI 与参数
```bash
python3 chartbook/scripts/chart_worst_slice_compare.py \
  --pred predictions.parquet --out-dir <workdir>/charts \
  --focal-model <模型名> [--slice-by month] [--n-perm 200] [--perm-seed 0]
```
v1 仅支持按月切片；焦点模型必须在数据里（typo 直接抛错）。置换基线默认开
（200 次、种子 0，两者均落盘进 JSON）；`--n-perm 0` 显式关闭。

## JSON schema
见 frontmatter；片指标 = 片内行 RMSE 均值（与 rolling-stability 同口径）。
置换统计量是**最差片正差距**而非 concentration_ratio——正差稀疏时任意重排的
占比仍近 1（null 退化无检验力）；坏日被打散后片均值被稀释，gap 幅度才有检验力。
按日块整块置换、片日数配额保持；`perm_p = (1+#{null≥real})/(n_perm+1)`。

## 判读
- **先看 `perm.verdict`**：not-significant → 必须写「最差片差距未超随机基线
  （perm_p=…），不点名切片」，切片证据线在 playbook 升级判定中弃权；
  以下条目只在 significant 时适用。
- `concentration_ratio > 0.7` → 差距集中：焦点模型在该片塌方——去该片跑
  worst-points 看点级性质、error-breakdown 看单元贡献；
- `concentration_ratio` 低（各片均摊）→ 普遍落后：候选为全局性机制（容量/
  损失/输入集差异），切片证据不再增益，转 horizon-degradation 与
  true-vs-pred-scatter；
- 片内逐日曲线他模型同步抬升（只是幅度小）→ 候选：共同外因+焦点更敏感。
- 已知局限：按日块置换只抵消日内自相关，月内跨日相关未校正——significant 是
  点名的**必要条件而非充分证明**。
只给候选假设；结论回 playbook 三道门。

## 验证步
见 frontmatter。
````

- [ ] **Step 6: 跑 chartbook 全套 + 引擎套件**

Run: `python3 -m pytest ts-diagnose/chartbook/tests/ ts-diagnose/scripts/tests/ -q`
Expected: 全 PASS（conformance 闸重校验新 recipe；引擎侧 gen_gate 对 stage2_slice.py 的既有 expect 仍绿——perm 是纯增量字段）。

- [ ] **Step 7: Commit**

```bash
git add ts-diagnose/chartbook/scripts/chart_worst_slice_compare.py \
        ts-diagnose/chartbook/recipes/worst-slice-compare.md \
        ts-diagnose/chartbook/tests/test_chart_worst_slice_compare.py
git commit -m "feat(chartbook): worst-slice-compare 内置按日块置换基线——统计量=最差片正差距，未超随机不点名切片"
```

---

### Task 2: 新图 cross-dim-stability（脚本 + recipe + 测试）

**Files:**
- Create: `ts-diagnose/chartbook/scripts/chart_cross_dim_stability.py`
- Create: `ts-diagnose/chartbook/recipes/cross-dim-stability.md`
- Test: `ts-diagnose/chartbook/tests/test_chart_cross_dim_stability.py`

**Interfaces:**
- Consumes: `chart_common.row_rmse/load_predictions/save_outputs/setup_font`。
- Produces: `compute(df, focal_model)` → JSON `{recipe, focal, pairs: {<other>: {time_split: {cut_ts,n_first,n_second,first_half_diff,second_half_diff,consistent}, caliber_switch: {row_diff,pooled_diff,consistent}, verdict: {time_stable,caliber_stable}}}, note}`；CLI `--pred --out-dir --focal-model`。Task 4 的 playbook 与 Task 5 的 manifest 依赖这些字段名。

- [ ] **Step 1: 写失败测试（新文件全文）**

`ts-diagnose/chartbook/tests/test_chart_cross_dim_stability.py`：

```python
"""cross-dim-stability golden：双稳构造精确回收（A 恒 0.8 vs B 恒 1.0 ⇒
两半差与两口径差全 −0.2）；口径翻转构造复刻 model-comparison 金标准
（A 按月 0.8/2.5/0.8 vs B 恒 1.5 ⇒ 时间对半各 −0.1333 稳、pooled 反超
+0.0843 翻转）。"""
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

import chart_cross_dim_stability as ccds  # noqa: E402
from synth import make_long, alt          # noqa: E402

WINDOWS = [f"2024-{mm:02d}-{dd:02d}" for mm in (1, 2, 3)
           for dd in (5, 10, 15, 20)]


def _prep(df):
    df["window_ts"] = pd.to_datetime(df["window_ts"])
    df["err"] = df["y_pred"] - df["y_true"]
    return df


def test_both_stable_exact():
    df = _prep(make_long(["A", "B"], ["U1"], WINDOWS, 8,
                         lambda m, u, w, s: alt(0.8 if m == "A" else 1.0, s)))
    st = ccds.compute(df, focal_model="A")
    p = st["pairs"]["B"]
    assert np.isclose(p["time_split"]["first_half_diff"], -0.2)
    assert np.isclose(p["time_split"]["second_half_diff"], -0.2)
    assert np.isclose(p["caliber_switch"]["row_diff"], -0.2)
    assert np.isclose(p["caliber_switch"]["pooled_diff"], -0.2)
    assert p["verdict"] == {"time_stable": True, "caliber_stable": True}


def test_caliber_flip_recovered():
    """复刻 playbook 金标准构造：时间对半两半各 −0.1333（稳），
    pooled 口径 A sqrt(2.51)=1.5843 反超 B 1.5（翻转）。"""
    amps = {"2024-01": 0.8, "2024-02": 2.5, "2024-03": 0.8}
    df = _prep(make_long(
        ["A", "B"], ["U1"], WINDOWS, 8,
        lambda m, u, w, s: alt(amps[w[:7]] if m == "A" else 1.5, s)))
    st = ccds.compute(df, focal_model="A")
    p = st["pairs"]["B"]
    ts = p["time_split"]
    assert ts["cut_ts"] == "2024-02-10" and ts["n_first"] == 6
    assert np.isclose(ts["first_half_diff"], -0.1333, atol=1e-3)
    assert np.isclose(ts["second_half_diff"], -0.1333, atol=1e-3)
    assert ts["consistent"] is True
    cs = p["caliber_switch"]
    assert np.isclose(cs["row_diff"], -0.1333, atol=1e-3)
    assert np.isclose(cs["pooled_diff"], 0.0843, atol=1e-3)
    assert cs["consistent"] is False
    assert p["verdict"] == {"time_stable": True, "caliber_stable": False}


def test_zero_half_diff_counts_as_unstable():
    """两半差为零（A、B 同幅）→ 按不稳处理，不算「稳定」。"""
    df = _prep(make_long(["A", "B"], ["U1"], WINDOWS, 8,
                         lambda m, u, w, s: alt(1.0, s)))
    st = ccds.compute(df, focal_model="A")
    assert st["pairs"]["B"]["verdict"]["time_stable"] is False


def test_unknown_focal_raises():
    df = _prep(make_long(["A", "B"], ["U1"], WINDOWS[:2], 4,
                         lambda m, u, w, s: alt(1.0, s)))
    with pytest.raises(ValueError, match="focal"):
        ccds.compute(df, focal_model="Z")


def test_single_model_raises():
    df = _prep(make_long(["A"], ["U1"], WINDOWS[:2], 4,
                         lambda m, u, w, s: alt(1.0, s)))
    with pytest.raises(ValueError, match="2"):
        ccds.compute(df, focal_model="A")


def test_main_writes_outputs(tmp_path):
    df = make_long(["A", "B"], ["U1"], WINDOWS[:4], 4,
                   lambda m, u, w, s: alt(1.0 if m == "A" else 1.2, s))
    p = tmp_path / "pred.csv"
    df.to_csv(p, index=False)
    ccds.main(["--pred", str(p), "--out-dir", str(tmp_path),
               "--focal-model", "A"])
    assert (tmp_path / "cross-dim-stability.json").exists()
    assert (tmp_path / "cross-dim-stability.png").exists()
```

- [ ] **Step 2: 跑测试确认失败**

Run: `python3 -m pytest ts-diagnose/chartbook/tests/test_chart_cross_dim_stability.py -v`
Expected: FAIL——`ModuleNotFoundError: chart_cross_dim_stability`。

- [ ] **Step 3: 写脚本（新文件全文）**

`ts-diagnose/chartbook/scripts/chart_cross_dim_stability.py`：

```python
"""cross-dim-stability：正交切分稳定性——时间对半 + 口径切换下，焦点与各他
模型的差距方向是否保持。同一份 predictions 派生的多张图属同一证据维度，方向
一致只是内部自洽；本图给「现象→假设」升级所需的跨维稳定性证据。"""
from __future__ import annotations

import argparse

import numpy as np
import pandas as pd

import chart_common as cc

RECIPE_ID = "cross-dim-stability"


def _hm(half_mean, model, half):
    v = half_mean.get((model, half))
    return float(v) if v is not None else float("nan")


def compute(df: pd.DataFrame, focal_model: str) -> dict:
    models = sorted(df["model"].unique())
    if focal_model not in models:
        raise ValueError(f"focal_model {focal_model!r} 不在数据模型集 {models}")
    if len(models) < 2:
        raise ValueError("跨维稳定性对比至少需要 2 个模型")
    rr = cc.row_rmse(df)
    ts_sorted = sorted(rr["window_ts"].unique())
    n_first = (len(ts_sorted) + 1) // 2
    cut_ts = ts_sorted[n_first - 1]
    rr["half"] = np.where(rr["window_ts"] <= cut_ts, "first", "second")
    half_mean = rr.groupby(["model", "half"])["rmse"].mean()
    row_mean = rr.groupby("model")["rmse"].mean()
    pooled = df.groupby("model")["err"].apply(
        lambda e: float(np.sqrt(np.mean(np.square(e)))))
    pairs = {}
    for other in models:
        if other == focal_model:
            continue
        d1 = _hm(half_mean, focal_model, "first") - _hm(half_mean, other, "first")
        d2 = _hm(half_mean, focal_model, "second") - _hm(half_mean, other, "second")
        time_ok = bool(np.isfinite(d1) and np.isfinite(d2) and d1 * d2 > 0)
        rd = float(row_mean[focal_model] - row_mean[other])
        pooled_d = float(pooled[focal_model] - pooled[other])
        cal_ok = bool(rd * pooled_d > 0)
        pairs[other] = {
            "time_split": {"cut_ts": str(pd.Timestamp(cut_ts).date()),
                           "n_first": int(n_first),
                           "n_second": int(len(ts_sorted) - n_first),
                           "first_half_diff": round(d1, 4),
                           "second_half_diff": round(d2, 4),
                           "consistent": time_ok},
            "caliber_switch": {"row_diff": round(rd, 4),
                               "pooled_diff": round(pooled_d, 4),
                               "consistent": cal_ok},
            "verdict": {"time_stable": time_ok, "caliber_stable": cal_ok}}
    return {"recipe": RECIPE_ID, "focal": focal_model, "pairs": pairs,
            "note": "同一份 predictions 的多图属同一证据维度，方向一致只是内部"
                    "自洽；本图给正交切分稳定性：time_stable 是「现象→假设」"
                    "必查项；caliber_stable=false 不阻塞升级，但结论必须限定"
                    "口径。半区差为零按不稳处理。两维都稳仍是同一份数据的重"
                    "切分——「已证实」照旧要走三道门之门2或外部实验。"}


def render(stats: dict):
    import matplotlib.pyplot as plt
    cc.setup_font()
    others = list(stats["pairs"])
    fig, axes = plt.subplots(len(others), 2, figsize=(9, 3.2 * len(others)),
                             squeeze=False)
    for i, o in enumerate(others):
        p = stats["pairs"][o]
        ts, cs = p["time_split"], p["caliber_switch"]
        axes[i][0].bar(["前半", "后半"],
                       [ts["first_half_diff"], ts["second_half_diff"]],
                       color="steelblue")
        axes[i][0].axhline(0, color="gray", lw=0.8)
        axes[i][0].set_title(f"{stats['focal']}−{o} 时间对半差"
                             f"（一致={ts['consistent']}）")
        axes[i][1].bar(["行RMSE均值", "点级pool"],
                       [cs["row_diff"], cs["pooled_diff"]], color="darkorange")
        axes[i][1].axhline(0, color="gray", lw=0.8)
        axes[i][1].set_title(f"口径切换差（一致={cs['consistent']}）")
    fig.tight_layout()
    return fig


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--pred", required=True)
    ap.add_argument("--out-dir", required=True)
    ap.add_argument("--focal-model", required=True)
    a = ap.parse_args(argv)
    stats = compute(cc.load_predictions(a.pred), focal_model=a.focal_model)
    cc.save_outputs(render(stats), a.out_dir, RECIPE_ID, stats)


if __name__ == "__main__":
    main()
```

- [ ] **Step 4: 跑测试确认通过**

Run: `python3 -m pytest ts-diagnose/chartbook/tests/test_chart_cross_dim_stability.py -v`
Expected: 7 个全 PASS。

- [ ] **Step 5: 写 recipe（新文件全文）**

`ts-diagnose/chartbook/recipes/cross-dim-stability.md`：

````markdown
---
id: cross-dim-stability
needs_materials: [predict, truth]
适用问题: A 比 B 好——换时间对半/换口径后方向还成立吗？（多图同源之外的正交稳定性证据）
outputs:
  json: cross-dim-stability.json
  png: cross-dim-stability.png
json_schema: >
  pairs.<other>.time_split（cut_ts/两半窗数/两半配对差 first_half_diff、
  second_half_diff/consistent 两半同号）、caliber_switch（row_diff 行 RMSE
  均值口径差 / pooled_diff 点级 pool 口径差 / consistent 同号）、
  verdict（time_stable / caliber_stable）。
bridge_hooks: >
  time_stable=false → 差距是「半程运气」候选：去 rolling-stability 找变点、
  worst-slice-compare 看是否单片驱动；caliber_stable=false → 少数 horizon
  step 拖爆 pool 口径候选：去 horizon-degradation 看交叉点；两维都稳 →
  差距结构性候选，进 playbook 升级判定。
验证步: 双稳构造（A 恒 0.8 vs B 恒 1.0）两半差与两口径差全 −0.2 精确回收；口径翻转构造（0.8/2.5/0.8 vs 恒 1.5）回收 time_stable=true + caliber_stable=false（tests/test_chart_cross_dim_stability.py）
---

# cross-dim-stability：正交切分稳定性

## 适用问题
「现象→假设」升级的第三条腿：同一份 predictions 派生的多张图属**同一证据维度**，
方向一致只是内部自洽；本图检验差距在两条正交切分（时间对半、口径切换）下是否保持。

## CLI 与参数
```bash
python3 chartbook/scripts/chart_cross_dim_stability.py \
  --pred predictions.parquet --out-dir <workdir>/charts --focal-model <模型名>
```
模型数 <2 抛 ValueError；对 focal 之外每个他模型各出一组配对结果。

## JSON schema
- `pairs.<other>.time_split`：distinct window_ts 排序对半（奇数窗前半多一窗），
  `cut_ts` = 前半末窗；`first/second_half_diff` = 该半区
  mean(row_rmse_focal) − mean(row_rmse_other)；`consistent` = 两半差同号
  （任一为零 → false）。
- `pairs.<other>.caliber_switch`：`row_diff`（行 RMSE 均值口径）与
  `pooled_diff`（点级 pool 口径，全点 sqrt(mean(err²))）同号才 `consistent`。
- `verdict`：`time_stable` / `caliber_stable`。

## 判读
- `time_stable=false` → 总差距是「半程运气」候选：禁升假设，去 rolling-stability
  看变点、worst-slice-compare 看是否单片驱动；
- `caliber_stable=false` → 结论限定口径（「A 更好」只在行均值口径成立），去
  horizon-degradation 看是否少数 step 拖爆 pool 口径；
- 两维都稳 ≠ 独立数据验证——仍是同一份数据的重切分；「已证实」层级照旧要走
  playbook 三道门之门 2（先预测后看数）或外部实验。
只给候选假设；结论回 playbook 三道门。

## 验证步
见 frontmatter。
````

- [ ] **Step 6: 跑 chartbook 全套（conformance 闸自动覆盖新 recipe）**

Run: `python3 -m pytest ts-diagnose/chartbook/tests/ -q`
Expected: 全 PASS（`test_recipes_conform` 多一个参数化项 `cross-dim-stability`）。

- [ ] **Step 7: Commit**

```bash
git add ts-diagnose/chartbook/scripts/chart_cross_dim_stability.py \
        ts-diagnose/chartbook/recipes/cross-dim-stability.md \
        ts-diagnose/chartbook/tests/test_chart_cross_dim_stability.py
git commit -m "feat(chartbook): 新图 cross-dim-stability——时间对半/口径切换正交稳定性（升级三条腿的第三条）"
```

---

### Task 3: 引擎层文档纪律（mechanisms 证据维度 + golden 种子豁免）

**Files:**
- Modify: `ts-diagnose/references/mechanisms.md`（§2 末尾追加一段）
- Modify: `ts-diagnose/playbooks/_playbook-spec.md`（§5 追加一条 bullet）
- Modify: `ts-diagnose/chartbook/_recipe-spec.md`（§5 硬规则 3 扩一句）

**Interfaces:** 纯文档，无代码接口；Task 4 的 playbook 正文将引用 mechanisms.md §2「证据维度」。

- [ ] **Step 1: mechanisms.md §2 末尾追加**

在 §2 段落（以 `……并在 FINDINGS 注明"仅 X 侧证据"。` 结尾）之后、`## 3` 之前追加：

```markdown
**证据维度**：同一份原始数据派生的所有产物（全部图 JSON、统计摘要）属**同一证据维度**——同维度内多产物方向一致只算一条线的内部自洽，不叠加置信度。「现象→假设」除 upgrade_rule 外，还须至少一条**正交切分**上方向稳定：时间重切 / 口径切换 / 外部材料（训练日志、特征真值、模型档案）任一，具体用哪条由 playbook 在 upgrade_rule 与正文声明（如 model-comparison 用 chartbook cross-dim-stability 的 time_split）。argmax 型点名（最差片/最差点/最差 step）必须先过随机基线（置换或解析 null）——未过者只能写「存在波动」，不得点名对象。
```

- [ ] **Step 2: _playbook-spec.md §5 追加 bullet**

在 §5 的 bullet「**期望值来自 reference 实跑并留容差**……」之后追加：

```markdown
- **种子豁免边界**：「零随机」约束的是 make_golden 的数据构造；分析/图脚本内的
  **固定种子置换**允许——种子必须是显式 CLI 参数并写进产物 JSON，期望值来自
  reference 同种子实跑；改种子=改期望，须连 manifest 一起改并重跑 pytest。
```

- [ ] **Step 3: _recipe-spec.md §5 硬规则 3 扩句**

把 `3. golden 决定论：合成数据零随机（幅度+奇偶交替符号 ⇒ 单元格 RMSE == 幅度）。` 改为：

```markdown
3. golden 决定论：合成数据零随机（幅度+奇偶交替符号 ⇒ 单元格 RMSE == 幅度）；
   脚本内固定种子置换例外——种子显式 CLI 参数并落 JSON，期望由同种子实跑钉住。
```

- [ ] **Step 4: 跑引擎套件（文档不破测试）**

Run: `python3 -m pytest ts-diagnose/scripts/tests/ ts-diagnose/chartbook/tests/ -q`
Expected: 全 PASS。

- [ ] **Step 5: Commit**

```bash
git add ts-diagnose/references/mechanisms.md \
        ts-diagnose/playbooks/_playbook-spec.md \
        ts-diagnose/chartbook/_recipe-spec.md
git commit -m "docs(ts-diagnose): 证据维度纪律进 mechanisms §2 + golden 固定种子豁免边界"
```

---

### Task 4: model-comparison playbook 消费两个新产物（升级三条腿）

**Files:**
- Modify: `ts-diagnose/playbooks/model-comparison/playbook.md`（8 处精确替换，见各 Step）

**Interfaces:**
- Consumes: Task 1 的 `perm.verdict` 字段、Task 2 的 recipe id `cross-dim-stability` 与 `verdict.time_stable/caliber_stable` 字段（frontmatter charts 校验要求该 recipe 已存在——Task 2 必须已完成）。
- Produces: frontmatter `evidence_lines` 第三条 `cross-dim`、新 `upgrade_rule` 文案（Task 5 manifest 的 desc 与之呼应）。

以下每步是一次 Edit（old → new 均为唯一匹配）。

- [ ] **Step 1: frontmatter charts 列表加 cross-dim-stability**

old:
```yaml
             y-vs-feature-mapping, train-test-drift]
```
new:
```yaml
             y-vs-feature-mapping, train-test-drift, cross-dim-stability]
```

- [ ] **Step 2: evidence_lines 加第三条 + upgrade_rule 改写**

old:
```yaml
  - id: slice-gap
    stage: 2
    output: charts/worst-slice-compare.json
upgrade_rule: "总差距方向（gap_summary 排名）与主导切片方向（worst-slice 片内排名）一致才把差距结论从「现象」升「假设」"
```
new:
```yaml
  - id: slice-gap
    stage: 2
    output: charts/worst-slice-compare.json
  - id: cross-dim
    stage: 2
    output: charts/cross-dim-stability.json
upgrade_rule: "总差距方向与主导切片方向一致（slice-gap 仅在 worst-slice perm.verdict=significant 时计入）且 cross-dim time_split 两半同向，才把差距结论从「现象」升「假设」"
```

- [ ] **Step 3: §1 追加第四陷阱**

old:
```
量纲纪律：点级 pool 口径（error-breakdown/horizon 等）与行 RMSE 均值口径
（rolling-stability/oracle-gap 等）两族数值不可直接比大小，只比走势与排名。
```
new:
```
量纲纪律：点级 pool 口径（error-breakdown/horizon 等）与行 RMSE 均值口径
（rolling-stability/oracle-gap 等）两族数值不可直接比大小，只比走势与排名。
第四陷阱：**多图同源≠多证据**——全部图派生自同一份 predictions，方向一致只是
同一证据维度的内部自洽（mechanisms.md §2「证据维度」）；升「假设」还须
cross-dim-stability 的正交切分稳定性（§3 三条腿）。
```

- [ ] **Step 4: §2 Stage 2 参数括号改写**

old:
```
（worst-slice-compare 传 `--focal-model` = model-set 答案里的关注模型；D 组图
加 `--features features.csv`；train-test-drift 加 `--train-y train_y.csv`。）
```
new:
```
（worst-slice-compare 与 cross-dim-stability 传 `--focal-model` = model-set
答案里的关注模型；worst-slice 置换基线默认开——`--n-perm 200 --perm-seed 0`，
改种子=改期望须连 golden 一起改；D 组图加 `--features features.csv`；
train-test-drift 加 `--train-y train_y.csv`。）
```

- [ ] **Step 5: §2 Stage 3 菜谱句改指向 §3**

old:
```
菜谱：逐条桥接假设 → 找它预言的图形态（bridge_hooks）→ 对照实际描述符；
两条证据线（total-gap 与 slice-gap）方向一致才把「现象」升「假设」
（upgrade_rule）。产出写回 FINDINGS.md（状态用保留字）。
```
new:
```
菜谱：逐条桥接假设 → 找它预言的图形态（bridge_hooks）→ 对照实际描述符；
升级按 §3 三条腿判定（upgrade_rule 两线一致 + 噪声门 + 跨维时间稳定）。
产出写回 FINDINGS.md（状态用保留字）。
```

- [ ] **Step 6: §3 首条升级规则改三条腿**

old:
```
- 现象 → 假设：upgrade_rule（两线方向一致）**且** |sign_z| ≥ 2（差距非噪声）；
```
new:
```
- 现象 → 假设（三条腿缺一不可）：①upgrade_rule 两线方向一致——slice-gap 线仅在
  worst-slice `perm.verdict=significant` 时计入，not-significant → 该线弃权、
  只剩单线则上限「现象」；②|sign_z| ≥ 2（差距非噪声）；③cross-dim
  `time_stable=true`（时间对半同向）。`caliber_stable=false` 不阻塞升级，
  但结论必须限定口径（「A 更好」仅在行 RMSE 均值口径成立）；
```

- [ ] **Step 7: §4 停顿汇报加两项**

old:
```
Stage 2 完成即停：向用户汇报 ①gap_summary 的排名与 z ②已画/跳过图清单
③Top-3 现象（引用图 JSON 数字）。请用户点名：
```
new:
```
Stage 2 完成即停：向用户汇报 ①gap_summary 的排名与 z ②已画/跳过图清单
③Top-3 现象（引用图 JSON 数字）④worst-slice 置换基线判定（significant →
点名最差片；否则明说「集中未超随机基线，不点名」）⑤cross-dim 两维是否稳。
请用户点名：
```

- [ ] **Step 8: §6 反驳门改写口径反转门 + 加两门**

old:
```
- **口径反转门**：horizon 交叉点存在吗？换口径（子段）后排名保持吗？
- **切片挑拣门**：结论引用的片段是事先声明的（最差片规则）还是事后挑的？
```
new:
```
- **口径反转门**：horizon 交叉点存在吗？换口径后方向保持吗（引 cross-dim
  caliber_switch 数字；翻转 → 结论限定口径）？
- **切片挑拣门**：结论引用的片段是事先声明的（最差片规则）还是事后挑的？
- **随机集中门**：点名的最差片过了置换基线吗（perm_p、null_q95 抄进结论）？
- **半程运气门**：时间对半后差距方向保持吗（引 cross-dim time_split 数字）？
```

- [ ] **Step 9: 跑引擎套件（frontmatter 校验 + 路由/分层守卫）**

Run: `python3 -m pytest ts-diagnose/scripts/tests/ -q`
Expected: 全 PASS（`test_charts_decl` 的全 playbook frontmatter 加载守卫会校验 charts 里新增的 `cross-dim-stability` recipe 存在——Task 2 已落地所以绿）。

- [ ] **Step 10: Commit**

```bash
git add ts-diagnose/playbooks/model-comparison/playbook.md
git commit -m "feat(ts-diagnose): model-comparison 升级三条腿——置换基线准入 + 跨维时间稳定必查 + 口径翻转限定口径"
```

---

### Task 5: golden 扩展（manifest 增量 + 跨维参考实现 + REFS 注册）

**Files:**
- Create: `ts-diagnose/playbooks/model-comparison/golden/reference/stage2_crossdim.py`
- Modify: `ts-diagnose/playbooks/model-comparison/golden/manifest.json`（整文件替换，见 Step 2）
- Modify: `ts-diagnose/scripts/tests/test_gen_gate.py`（REFS 加一行）

**Interfaces:**
- Consumes: Task 1/2 的 chartbook 脚本 compute；`make_golden.py` 与 `predictions.csv` **不动**（Global Constraints）。
- Produces: 伪 stage 键 `2-crossdim`（gen_gate 的 stage 键只作 manifest 查找，不要求等于 playbook 阶段 id——manifest note 写明此约定）。

- [ ] **Step 1: 写参考实现（新文件全文）**

`ts-diagnose/playbooks/model-comparison/golden/reference/stage2_crossdim.py`：

```python
"""Stage 2 参考实现（跨维稳定性证据线）：直接复用 chartbook 预写
cross-dim-stability 的 compute——参考实现与产线同源，钉住「稳定性检查
不现场写代码」的契约。"""
import argparse
import json
import os
import sys

_ENGINE = os.path.abspath(os.path.join(
    os.path.dirname(os.path.abspath(__file__)), "..", "..", "..", ".."))
sys.path.insert(0, os.path.join(_ENGINE, "chartbook", "scripts"))

import chart_common as cc                    # noqa: E402
import chart_cross_dim_stability as ccds     # noqa: E402


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--pred", required=True)
    ap.add_argument("--focal", required=True)
    ap.add_argument("--out", required=True)
    a = ap.parse_args()
    stats = ccds.compute(cc.load_predictions(a.pred), focal_model=a.focal)
    json.dump(stats, open(a.out, "w"), ensure_ascii=False, indent=2)


if __name__ == "__main__":
    main()
```

- [ ] **Step 2: 整文件替换 manifest.json**

```json
{
  "playbook": "model-comparison",
  "note": "金标准由 make_golden.py 确定性生成（零随机）；期望值来自 reference/ 实跑留容差。Stage 0 依赖真实数据格式（适配器+对账验证步兜底）；Stage 2 的图脚本本体由 chartbook 自带 golden 闸住，此处钉的是切片证据线契约（含置换基线 seed=0/n_perm=200，改种子=改期望）。伪 stage 键 2-crossdim 钉跨维稳定性证据线——gen_gate 的 stage 键只作 manifest 查找，不要求等于 playbook 阶段 id。改期望先改 make_golden.py 并重跑 pytest。",
  "planted": {
    "overall_better": "A",
    "a_worst_slice": "2024-02",
    "slice_winner_in_worst": "B",
    "gap_concentration": 1.0,
    "perm_significant": true,
    "time_stable": true,
    "caliber_flip": true
  },
  "stages": {
    "1": {
      "desc": "总差距：A 总体更好但差距未过噪声线（|z|<2），配对统计精确回收",
      "inputs": ["predictions.csv"],
      "args": ["--pred", "predictions.csv", "--pair", "A,B", "--out", "gap_summary.json"],
      "expect": [
        {"file": "gap_summary.json", "path": "ranking", "op": "first_is", "value": "A"},
        {"file": "gap_summary.json", "path": "per_model.A", "op": "between", "value": [1.36, 1.38]},
        {"file": "gap_summary.json", "path": "per_model.B", "op": "between", "value": [1.49, 1.51]},
        {"file": "gap_summary.json", "path": "mean_diff", "op": "between", "value": [-0.14, -0.12]},
        {"file": "gap_summary.json", "path": "win_rate", "op": "between", "value": [0.66, 0.68]},
        {"file": "gap_summary.json", "path": "sign_z", "op": "between", "value": [1.05, 1.25]},
        {"file": "gap_summary.json", "path": "sign_p", "op": "exists"}
      ]
    },
    "2": {
      "desc": "切片证据线：A 最差片 2024-02、片内 B 反超、gap 全集中且过置换基线（seed=0：真实 worst_slice_gap=1.0，null 典型 0.575/0.15）",
      "inputs": ["predictions.csv"],
      "args": ["--pred", "predictions.csv", "--focal", "A", "--out", "worst-slice-compare.json"],
      "expect": [
        {"file": "worst-slice-compare.json", "path": "worst_slice", "op": "eq", "value": "2024-02"},
        {"file": "worst-slice-compare.json", "path": "in_slice.A", "op": "between", "value": [2.49, 2.51]},
        {"file": "worst-slice-compare.json", "path": "in_slice.B", "op": "between", "value": [1.49, 1.51]},
        {"file": "worst-slice-compare.json", "path": "concentration_ratio", "op": "eq", "value": 1.0},
        {"file": "worst-slice-compare.json", "path": "perm.verdict", "op": "eq", "value": "significant"},
        {"file": "worst-slice-compare.json", "path": "perm.perm_p", "op": "le", "value": 0.05},
        {"file": "worst-slice-compare.json", "path": "perm.real_stat", "op": "between", "value": [0.99, 1.01]},
        {"file": "worst-slice-compare.json", "path": "perm.null_q95", "op": "le", "value": 0.7}
      ]
    },
    "2-crossdim": {
      "desc": "跨维稳定性证据线：时间对半 A 两半均领先（各 −0.1333）、口径切换翻转（pooled A 1.5843 > B 1.5）",
      "inputs": ["predictions.csv"],
      "args": ["--pred", "predictions.csv", "--focal", "A", "--out", "cross-dim-stability.json"],
      "expect": [
        {"file": "cross-dim-stability.json", "path": "pairs.B.time_split.consistent", "op": "eq", "value": true},
        {"file": "cross-dim-stability.json", "path": "pairs.B.time_split.first_half_diff", "op": "between", "value": [-0.14, -0.13]},
        {"file": "cross-dim-stability.json", "path": "pairs.B.time_split.second_half_diff", "op": "between", "value": [-0.14, -0.13]},
        {"file": "cross-dim-stability.json", "path": "pairs.B.caliber_switch.pooled_diff", "op": "between", "value": [0.08, 0.09]},
        {"file": "cross-dim-stability.json", "path": "pairs.B.caliber_switch.consistent", "op": "eq", "value": false},
        {"file": "cross-dim-stability.json", "path": "pairs.B.verdict.time_stable", "op": "eq", "value": true},
        {"file": "cross-dim-stability.json", "path": "pairs.B.verdict.caliber_stable", "op": "eq", "value": false}
      ]
    }
  }
}
```

（相对原 manifest：stage 1 逐字不变；stage 2 只增 4 条 perm expect 与 desc；新增 planted 三键与 2-crossdim 段。）

- [ ] **Step 3: test_gen_gate.py REFS 注册**

old:
```python
    ("model-comparison", "1", "reference/stage1_gap.py"),
    ("model-comparison", "2", "reference/stage2_slice.py"),
```
new:
```python
    ("model-comparison", "1", "reference/stage1_gap.py"),
    ("model-comparison", "2", "reference/stage2_slice.py"),
    ("model-comparison", "2-crossdim", "reference/stage2_crossdim.py"),
```

- [ ] **Step 4: 跑生成闸测试（新参考实现被端到端闸）**

Run: `python3 -m pytest ts-diagnose/scripts/tests/test_gen_gate.py -v`
Expected: 全 PASS，含新参数化项 `model-comparison-2-crossdim-reference/stage2_crossdim.py`；stage 2 的 perm 断言过（若 perm_p/null_q95 实跑值越界——只可能是实现偏离本计划——回 Task 1 查实现，**不改期望**）。

- [ ] **Step 5: 跑引擎全套**

Run: `python3 -m pytest ts-diagnose/scripts/tests/ ts-diagnose/chartbook/tests/ -q`
Expected: 全 PASS。

- [ ] **Step 6: Commit**

```bash
git add ts-diagnose/playbooks/model-comparison/golden/reference/stage2_crossdim.py \
        ts-diagnose/playbooks/model-comparison/golden/manifest.json \
        ts-diagnose/scripts/tests/test_gen_gate.py
git commit -m "test(ts-diagnose): model-comparison golden 钉置换基线与跨维稳定性契约（伪 stage 2-crossdim + REFS 注册）"
```

---

### Task 6: CHANGELOG + 全仓回归

**Files:**
- Modify: `ts-diagnose/CHANGELOG.md`（文件末尾追加一行——该文件是扁平行式、新条目在底部，不要加小节标题）

**Interfaces:** 无。

- [ ] **Step 1: CHANGELOG 末尾追加一行**

```markdown
- 2026-07-23 | 证据可靠性加固：worst-slice-compare 内置按日块置换基线（统计量=最差片正差距，未过基线不点名切片）+ 新图 cross-dim-stability（时间对半/口径切换正交稳定性）+ mechanisms §2「证据维度」纪律 + model-comparison 升级三条腿（两线一致·噪声门·时间稳定；口径翻转限定口径不阻塞）+ golden 固定种子豁免边界 | 用户："我觉得你说的两个 suggestion 非常好，帮我写一个 spec" | 堵多重比较虚警与多图同源伪收敛；spec：docs/superpowers/specs/2026-07-23-ts-diagnose-evidence-hardening-design.md
```

- [ ] **Step 2: 全仓回归**

Run: `python3 -m pytest ts-diagnose/ pv-result-analysis/ pv-station-influence/ pv-model-analysis/ pv-feature-blame/ -q`（超时给足 300s）
Expected: 全 PASS，0 failed（相对基线 246 净增约 12 项：worst-slice +4、cross-dim +7、conformance +1、gen_gate REFS +1，具体以 pytest 输出为准）。

- [ ] **Step 3: Commit**

```bash
git add ts-diagnose/CHANGELOG.md
git commit -m "docs(ts-diagnose): CHANGELOG 记证据可靠性加固轮"
```
