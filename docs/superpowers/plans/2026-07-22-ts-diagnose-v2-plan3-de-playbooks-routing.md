# ts-diagnose v2 Plan 3：D/E 组图 + model-comparison/fact-scan playbook + 路由收口

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 完成 ts-diagnose v2 的最后一环：Plan 2 终审卫生小修、D 组 feature 关联 3 图 + E 组漂移 1 图、playbook 阶段级 `charts:` 声明（orient 报可画性）、model-comparison 与 fact-scan 两个 playbook（含 golden+gen_gate）、SKILL 路由表两行与 pv-result-analysis 反向负面清单。

**Architecture:** 沿用 Plan 2 的 chartbook 模式（预写脚本+合成植入回收 golden+recipe 判读节）；playbook 沿用既有三 playbook 的目录规范（frontmatter 机器读 + 正文菜谱 + golden/manifest + reference/ 参考实现过 gen_gate 闸）。设计规格：`docs/superpowers/specs/2026-07-22-ts-diagnose-v2-intake-chartbook-design.md` §4 D/E 组、§5、§6、§7。

**Tech Stack:** Python 3 + pandas + numpy + matplotlib(Agg) + pytest + PyYAML（scipy 仅可选）。

**仓库根** `<REPO>` = `/Users/tqa946816/Documents/华为/光伏预测/结果分析skill`。`<ENGINE>` = `<REPO>/ts-diagnose`。

## Global Constraints

- **规范长表**（Plan 2 已定，列名精确）：predictions `window_ts|unit_id|model|horizon_step|y_true|y_pred`（err≡y_pred−y_true）。**本计划新增 features 长表**：`window_ts|unit_id|feature|horizon_step|f_pred|f_true`（f_true 可缺列，缺则补 NaN）；**train_y 长表**：`ts|unit_id|y`。
- **JSON 一等/PNG 副产品**、curve_stats 字段名、recipe frontmatter 7 键、id↔文件名映射、CLI 公共参数 `--pred --out-dir`、golden 决定论（零随机，幅度+奇偶交替符号 ⇒ RMSE==幅度）——全部沿用 Plan 2 Global Constraints 原文。
- **零跨 skill 引用**：chartbook 与两个新 playbook 的任何文件不得出现字符串 `pv-result-analysis / pv_result_analysis / pv-feature-blame / pv-station-influence`；例外：playbook frontmatter 的 `provider_skill: pv-model-analysis`（contexts 机制的合法字段，Plan 1 已定）。
- **Layer 1 互不引用**：model-comparison 与 fact-scan 的 playbook.md 正文互相不得出现对方 id，也不得出现既有三 playbook 的 id（test_layering.test_layer1_playbooks_independent 将扩到五个）。fact-scan 的"深挖衔接"只能写"切换其他 playbook（由路由层选择）"，不点名。
- **SKILL.md 预算**：≤60 行 / ~6K token（test_layering 守卫），且不得出现 METHOD_VOCAB 禁词（含 `Stage/done_when/pause_after/evidence_lines/findings_marker/Spearman` 等——路由行措辞注意规避）。
- **gen_gate manifest 契约**（与既有 playbook 一致）：`{"playbook","note","planted","stages":{"<n>":{"desc","inputs":[golden 内相对路径],"args":[脚本 CLI 参数],"expect":[{"file","path","op","value"}]}}}`；op ∈ eq/ge/le/between/contains/first_is/argmax/argmin/exists；reference/ 参考实现走 `scripts/gen_gate.py --script <ref> --playbook <id> --stage <n>`，并在 `scripts/tests/test_gen_gate.py` 的 REFS 元组登记。reference 脚本禁 subprocess/网络/绝对路径写（static_check），golden 输入用 csv/json（零 pyarrow 依赖）。
- **绝不触碰**：pv-* 四技能目录（除 Task 10 对 pv-result-analysis/SKILL.md description 的一句让路补充）、row-diagnostic/、docs/skill解析/、工作区其他未提交文件。
- 每任务收尾：`python3 -m pytest <REPO>/ts-diagnose -q` 全绿（快闸），最后一个任务另跑全仓 `python3 -m pytest <REPO> -q`（约 100 秒，216+ 起步）。
- 提交前缀 `feat(ts-diagnose)` / `fix(ts-diagnose)` / `docs(ts-diagnose)`。

## 文件结构总览

```
ts-diagnose/
├── chartbook/
│   ├── scripts/chart_common.py                 # Task 1 卫生修 + Task 2 加 load_features
│   ├── scripts/chart_feature_error_conditional.py   # Task 2 (D)
│   ├── scripts/chart_feature_trend_overlay.py       # Task 3 (D)
│   ├── scripts/chart_y_vs_feature_mapping.py        # Task 4 (D)
│   ├── scripts/chart_train_test_drift.py            # Task 5 (E)
│   ├── recipes/<id>.md ×4 + tests/test_chart_<id>.py ×4   # 随各任务
├── scripts/engine_common.py                    # Task 6：charts 声明校验 + recipe_materials
├── scripts/orient.py                           # Task 6：stage 可画性输出
├── scripts/tests/test_charts_decl.py           # Task 6
├── playbooks/model-comparison/{playbook.md, golden/}    # Task 7 / Task 8
├── playbooks/fact-scan/{playbook.md, golden/}           # Task 9
├── playbooks/_playbook-spec.md                 # Task 6：charts 键文档
├── scripts/tests/{test_gen_gate.py, test_layering.py, test_routing.py}  # Task 8/9/10 扩
├── SKILL.md + CHANGELOG.md                     # Task 10
pv-result-analysis/SKILL.md                     # Task 10（仅 description 一句）
```

---

### Task 1: Plan 2 终审卫生小修包（六项一次提交）

**Files:**
- Modify: `ts-diagnose/chartbook/scripts/chart_common.py`
- Modify: `ts-diagnose/chartbook/scripts/chart_error_breakdown.py`
- Modify: `ts-diagnose/chartbook/scripts/chart_worst_slice_compare.py`
- Modify: `ts-diagnose/scripts/tests/test_layering.py`
- Modify: `ts-diagnose/chartbook/tests/test_chart_common.py`（退化分支契约测试）

**Interfaces:** 不改任何对外签名；curve_stats 退化分支（n<2）语义变更：`max_jump_idx` 由 `str(idx[0])` 改为 `None`，`argmax/argmin` 由 `None` 改为 `str(idx[0])`（有点即有峰谷、无相邻对即无跳变——语义自洽）。

- [ ] **Step 1: 逐项修改（先改代码再补测试，本任务为微修包，TDD 环节合并执行）**

1. `chart_common.py`：`matplotlib.use("Agg")` 行之后加一行 `import matplotlib.font_manager  # noqa: E402  （setup_font 依赖，显式化避免 import 顺序脆弱）`。
2. `chart_common.py` `row_rmse` docstring：`（rmse_192 口径泛化）` 改为 `（整行全部 horizon 点的 RMSE——行级口径）`（引擎库去光伏专属词汇）。
3. `chart_common.py` `curve_stats` n<2 退化分支改为：

```python
        return {"curve": {str(k): (round(float(val), round_to)
                                   if np.isfinite(val) else None)
                          for k, val in zip(idx, v)},
                "trend": "平", "monotonic": True,
                "max_jump_idx": None, "max_jump": 0.0, "roughness": 0.0,
                "argmax": str(idx[0]) if idx else None,
                "argmin": str(idx[0]) if idx else None}
```

4. `chart_error_breakdown.py` `_cell_rmse`：`df.groupby(keys)` → `df.groupby(keys, observed=False)`（钉住现行为，消 pandas FutureWarning）。
5. `chart_worst_slice_compare.py`：删除未使用的 `import numpy as np` 行。
6. `test_layering.py` `test_chartbook_scripts_no_cross_skill_imports`：扫描范围从 `chartbook/scripts/*.py` 扩为三处——`chartbook/scripts/*.py` + `chartbook/recipes/*.md` + `chartbook/tests/*.py`（改为对三个 glob 结果拼接后循环；断言消息带文件名不变）。

- [ ] **Step 2: 补退化分支契约测试**

`ts-diagnose/chartbook/tests/test_chart_common.py` 末尾追加：

```python
def test_curve_stats_degenerate_single_point():
    st = cc.curve_stats([5.0], index=["only"])
    assert st["max_jump_idx"] is None and st["max_jump"] == 0.0
    assert st["argmax"] == "only" and st["argmin"] == "only"
```

- [ ] **Step 3: 跑测试**

Run: `python3 -m pytest ts-diagnose/ -q`
Expected: 全绿（135+1 项），FutureWarning 从输出消失。

- [ ] **Step 4: Commit**

```bash
git add ts-diagnose/chartbook/ ts-diagnose/scripts/tests/test_layering.py
git commit -m "fix(ts-diagnose): chartbook 卫生轮——font_manager 显式 import、observed 钉住、退化分支语义统一、去 rmse_192 字样、未用 import、layering 守卫扩 recipes+tests"
```

---

### Task 2: `feature-error-conditional`（D 组：feature 值/质量分箱条件误差）+ chart_common.load_features

**Files:**
- Modify: `ts-diagnose/chartbook/scripts/chart_common.py`（加 FEATURE_COLS + load_features）
- Create: `ts-diagnose/chartbook/scripts/chart_feature_error_conditional.py`
- Create: `ts-diagnose/chartbook/recipes/feature-error-conditional.md`
- Create: `ts-diagnose/chartbook/tests/test_chart_feature_error_conditional.py`

**Interfaces:**
- Produces（Task 3/4 复用）：`chart_common.FEATURE_COLS = ("window_ts","unit_id","feature","horizon_step","f_pred")`；`chart_common.load_features(path) -> pd.DataFrame`（校验 5 必需列、f_true 缺列补 NaN、window_ts 转 datetime）
- Produces：`compute(pred_df, feat_df, n_bins=5) -> dict`；CLI `--pred --features --out-dir [--n-bins 5]`

- [ ] **Step 1: 写失败测试**

```python
"""feature-error-conditional golden：真凶 ghi 的质量误差 q∈{0,20} 与 y 误差幅度
1+0.1q 完全耦合（effect_ratio=3、rho=1）；诱饵 temp 的 q 与 y 误差按奇偶交替解耦
（effect_ratio<1.3）——防冤枉埋点。"""
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

import chart_feature_error_conditional as cfe  # noqa: E402
import chart_common as cc                      # noqa: E402
from synth import make_long, alt               # noqa: E402

WINDOWS = [f"2024-01-{d:02d}" for d in range(1, 11)]   # w 索引 = 日-1


def _q_ghi(w):
    return 0.0 if int(w[-2:]) - 1 < 5 else 20.0


def _q_temp(w):
    return 20.0 if (int(w[-2:]) - 1) % 2 == 0 else 0.0


def _pred_df():
    df = make_long(["A"], ["U1"], WINDOWS, 8,
                   lambda m, u, w, s: alt(1.0 + 0.1 * _q_ghi(w), s))
    df["window_ts"] = pd.to_datetime(df["window_ts"])
    df["err"] = df["y_pred"] - df["y_true"]
    return df


def _feat_df():
    rows = []
    for w in WINDOWS:
        for s in range(8):
            rows.append({"window_ts": w, "unit_id": "U1", "feature": "ghi",
                         "horizon_step": s, "f_pred": 100.0 + _q_ghi(w),
                         "f_true": 100.0})
            rows.append({"window_ts": w, "unit_id": "U1", "feature": "temp",
                         "horizon_step": s, "f_pred": 50.0 + _q_temp(w),
                         "f_true": 50.0})
    df = pd.DataFrame(rows)
    df["window_ts"] = pd.to_datetime(df["window_ts"])
    return df


def test_load_features_contract(tmp_path):
    p = tmp_path / "f.csv"
    _feat_df().drop(columns=["f_true"]).to_csv(p, index=False)
    out = cc.load_features(p)
    assert "f_true" in out.columns and out["f_true"].isna().all()
    import pytest
    with pytest.raises(ValueError, match="feature"):
        bad = tmp_path / "bad.csv"
        _feat_df().drop(columns=["feature"]).to_csv(bad, index=False)
        cc.load_features(bad)


def test_culprit_and_decoy():
    st = cfe.compute(_pred_df(), _feat_df(), n_bins=5)
    ghi = st["models"]["A"]["ghi"]
    temp = st["models"]["A"]["temp"]
    assert np.isclose(ghi["quality_effect_ratio"], 3.0)
    assert ghi["quality_monotonic_rho"] == 1.0
    assert temp["quality_effect_ratio"] < 1.3          # 诱饵不得被点名
    assert set(ghi["quality_bins"]) and set(ghi["value_bins"])


def test_no_ftrue_falls_back_to_value_bins_only():
    fd = _feat_df()
    fd["f_true"] = np.nan
    st = cfe.compute(_pred_df(), fd, n_bins=5)
    a = st["models"]["A"]["ghi"]
    assert a["quality_bins"] is None and a["quality_effect_ratio"] is None
    assert a["value_bins"]


def test_main_writes_outputs(tmp_path):
    pp, fp = tmp_path / "p.csv", tmp_path / "f.csv"
    _pred_df().drop(columns=["err"]).to_csv(pp, index=False)
    _feat_df().to_csv(fp, index=False)
    cfe.main(["--pred", str(pp), "--features", str(fp),
              "--out-dir", str(tmp_path)])
    assert (tmp_path / "feature-error-conditional.json").exists()
    assert (tmp_path / "feature-error-conditional.png").exists()
```

- [ ] **Step 2: 跑测试确认失败**

Run: `python3 -m pytest ts-diagnose/chartbook/tests/test_chart_feature_error_conditional.py -q`
Expected: FAIL（ModuleNotFoundError 或 AttributeError: load_features）

- [ ] **Step 3: chart_common.py 加 features 长表接口（REQUIRED_COLS 定义之后）**

```python
FEATURE_COLS = ("window_ts", "unit_id", "feature", "horizon_step", "f_pred")


def load_features(path):
    """features 长表：一行 = 一特征一步；f_true 可缺列（缺则补 NaN，质量分箱自动降级）。"""
    p = Path(path)
    df = pd.read_parquet(p) if p.suffix == ".parquet" else pd.read_csv(p)
    missing = [c for c in FEATURE_COLS if c not in df.columns]
    if missing:
        raise ValueError(
            f"features 长表缺列 {missing}；需要 {list(FEATURE_COLS)}(+可选 f_true)"
            "（适配器契约见 chartbook/_recipe-spec.md）")
    df = df.copy()
    if "f_true" not in df.columns:
        df["f_true"] = np.nan
    df["window_ts"] = pd.to_datetime(df["window_ts"])
    return df
```

- [ ] **Step 4: 写 `chart_feature_error_conditional.py`**

```python
"""feature-error-conditional：按 feature 值分箱与质量(|f_pred−f_true|)分箱的条件
y 误差——「feature 不准的时候，y-label 误差变大多少」。

只产图级事实（分箱指标+单调性+效应幅度），不做完整重要性归因（那属于
feature-importance playbook / 专用特征归因技能）。effect_ratio = 最差箱 RMSE /
最好箱 RMSE；rho = 箱序与 RMSE 的 Spearman（质量单调放大误差 → rho→1）。
"""
from __future__ import annotations

import argparse

import numpy as np
import pandas as pd

import chart_common as cc

RECIPE_ID = "feature-error-conditional"
JOIN = ["window_ts", "unit_id", "horizon_step"]


def _bin_rmse(joined, by_col, n_bins):
    d = joined.dropna(subset=[by_col])
    if d.empty or d[by_col].nunique() < 2:
        return None
    d = d.copy()
    if d[by_col].nunique() <= n_bins:
        # 离散少值（如质量误差只有 0/20 两档）：qcut 会塌箱，按值精确分组
        d["bin"] = d[by_col]
        g = d.groupby("bin")
    else:
        d["bin"] = pd.qcut(d[by_col], n_bins, duplicates="drop")
        g = d.groupby("bin", observed=True)
    rmse = g["err"].apply(lambda e: float(np.sqrt(np.mean(np.square(e)))))
    centers = g[by_col].mean()
    return {f"{c:.2f}": round(float(r), 4)
            for c, r in zip(centers.values, rmse.values)}, rmse


def _stats_of(rmse_series):
    v = rmse_series.values.astype(float)
    ratio = round(float(v.max() / v.min()), 4) if v.min() > 0 else None
    rho = float(pd.Series(range(len(v))).corr(pd.Series(v),
                                              method="spearman")) \
        if len(v) >= 2 else None
    return ratio, (round(rho, 4) if rho is not None else None)


def compute(pred_df: pd.DataFrame, feat_df: pd.DataFrame,
            n_bins: int = 5) -> dict:
    out = {"recipe": RECIPE_ID, "n_bins": n_bins, "models": {},
           "note": "quality=|f_pred−f_true|；effect_ratio=最差箱/最好箱 RMSE；"
                   "rho→1 = 质量越差误差单调越大。f_true 全缺 → 质量分箱记 null，"
                   "只看值分箱。只产图级事实，归因回 playbook。"}
    feat_df = feat_df.copy()
    feat_df["quality"] = (feat_df["f_pred"] - feat_df["f_true"]).abs()
    for m, g in pred_df.groupby("model"):
        per_feature = {}
        for feat, fg in feat_df.groupby("feature"):
            joined = g.merge(fg[JOIN + ["f_pred", "quality"]], on=JOIN,
                             how="inner")
            if joined.empty:
                continue
            vb = _bin_rmse(joined, "f_pred", n_bins)
            qb = _bin_rmse(joined, "quality", n_bins)
            entry = {"n": int(len(joined)),
                     "value_bins": vb[0] if vb else None,
                     "quality_bins": qb[0] if qb else None,
                     "value_effect_ratio": None, "value_monotonic_rho": None,
                     "quality_effect_ratio": None,
                     "quality_monotonic_rho": None}
            if vb:
                entry["value_effect_ratio"], entry["value_monotonic_rho"] = \
                    _stats_of(vb[1])
            if qb:
                entry["quality_effect_ratio"], entry["quality_monotonic_rho"] = \
                    _stats_of(qb[1])
            per_feature[str(feat)] = entry
        out["models"][str(m)] = per_feature
    return out


def render(stats: dict):
    import matplotlib.pyplot as plt
    cc.setup_font()
    models = list(stats["models"])
    fig, axes = plt.subplots(len(models), 1,
                             figsize=(10, 3.2 * len(models)), squeeze=False)
    for ax, m in zip(axes.ravel(), models):
        for feat, e in stats["models"][m].items():
            bins = e["quality_bins"] or e["value_bins"] or {}
            ax.plot(range(len(bins)), list(bins.values()), "-o", ms=3,
                    label=f"{feat}"
                          f"(ratio={e['quality_effect_ratio'] or e['value_effect_ratio']})")
        ax.set_title(f"feature-error-conditional 分箱条件 RMSE — {m}",
                     fontsize=10)
        ax.set_xlabel("箱序（质量/值 由低到高）"), ax.set_ylabel("RMSE")
        ax.legend(fontsize=7)
    fig.tight_layout()
    return fig


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--pred", required=True)
    ap.add_argument("--features", required=True)
    ap.add_argument("--out-dir", required=True)
    ap.add_argument("--n-bins", type=int, default=5)
    a = ap.parse_args(argv)
    stats = compute(cc.load_predictions(a.pred), cc.load_features(a.features),
                    n_bins=a.n_bins)
    cc.save_outputs(render(stats), a.out_dir, RECIPE_ID, stats)


if __name__ == "__main__":
    main()
```

- [ ] **Step 5: 跑测试确认通过**

Run: `python3 -m pytest ts-diagnose/chartbook/tests/test_chart_feature_error_conditional.py -q`
Expected: PASS（4 passed）

- [ ] **Step 6: 写 `recipes/feature-error-conditional.md`**

````markdown
---
id: feature-error-conditional
needs_materials: [predict, truth, features]
适用问题: feature 不准的时候 y 误差变大多少？哪个 feature 的质量与误差耦合最强？
outputs:
  json: feature-error-conditional.json
  png: feature-error-conditional.png
json_schema: >
  每模型每 feature：value_bins / quality_bins（分箱 RMSE）、value/quality 的
  effect_ratio（最差箱/最好箱）与 monotonic_rho（箱序 Spearman）、n。
  f_true 全缺时 quality_* 为 null（自动降级为值分箱）。
bridge_hooks: >
  某 feature quality_effect_ratio 高且 rho→1 → 该输入质量主导误差的候选（错在
  输入不在模型）；全 feature 比值都低 → 误差非输入质量驱动，转结构类假设
  （horizon-degradation / true-vs-pred-scatter 交叉）。
验证步: 真凶(耦合 ratio=3, rho=1)+诱饵(解耦 ratio<1.3)双埋点，诱饵必须不被点名（tests/test_chart_feature_error_conditional.py）
---

# feature-error-conditional：feature 质量条件误差

## 适用问题
「feature 什么时候不准、对 y-label 影响大不大」的第一张图。只产图级事实；
完整重要性归因走 feature-importance playbook 或专用特征归因技能。

## CLI 与参数
```bash
python3 chartbook/scripts/chart_feature_error_conditional.py \
  --pred predictions.parquet --features features.parquet \
  --out-dir <workdir>/charts [--n-bins 5]
```
features 长表：`window_ts|unit_id|feature|horizon_step|f_pred|f_true(可选)`。

## JSON schema
见 frontmatter；分箱按分位（qcut），键为箱内均值。n < 200 的 feature 不下断言。

## 判读
- `quality_effect_ratio ≥ 2` 且 `quality_monotonic_rho ≥ 0.8` → 候选：该 feature
  质量主导——去 feature-trend-overlay 看坏片上是否同步；
- 多个 feature 同时高比值 → 候选：共线（同一上游源坏了），先看它们 quality 的
  相互相关再点名；
- `value_bins` 有效应而 `quality_bins` 无 → 候选：模型对该值域欠拟合（非输入质量
  问题），转 true-vs-pred-scatter 的分箱残差交叉。
只给候选假设；结论回 playbook 三道门。

## 验证步
见 frontmatter；防冤枉纪律：诱饵 feature 的质量波动与误差解耦，比值必须≈1。
````

- [ ] **Step 7: 跑一致性闸 + 引擎全绿**

Run: `python3 -m pytest ts-diagnose/ -q`
Expected: 全绿。

- [ ] **Step 8: Commit**

```bash
git add ts-diagnose/chartbook/
git commit -m "feat(ts-diagnose): chartbook feature-error-conditional——feature 质量分箱条件误差（真凶/诱饵双埋点）+ load_features 公共件"
```

---

### Task 3: `feature-trend-overlay`（D 组：坏片上 feature 走势与 y 误差对照）

**Files:**
- Create: `ts-diagnose/chartbook/scripts/chart_feature_trend_overlay.py`
- Create: `ts-diagnose/chartbook/recipes/feature-trend-overlay.md`
- Create: `ts-diagnose/chartbook/tests/test_chart_feature_trend_overlay.py`

**Interfaces:**
- Consumes: `chart_common.load_predictions / load_features / row_rmse / downsample`
- Produces: `compute(pred_df, feat_df, model=None, slice_month=None) -> dict`；CLI `--pred --features --out-dir [--model <名>] [--slice-month YYYY-MM]`

- [ ] **Step 1: 写失败测试**

```python
"""feature-trend-overlay golden：2 月为坏片（日误差幅度=1+0.1q_d，q_d 隔日 0/20），
日 y-RMSE 与日 quality 完全同步 → 切片自动选中 2024-02、sync_corr≈1、basis=quality。"""
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

import chart_feature_trend_overlay as cfo  # noqa: E402
from synth import make_long, alt           # noqa: E402

FEB = [f"2024-02-{d:02d}" for d in range(1, 13)]
OTHER = [f"2024-{mm:02d}-{dd:02d}" for mm in (1, 3) for dd in (5, 15, 25)]


def _q(w):
    if not w.startswith("2024-02"):
        return 0.0
    return 0.0 if int(w[-2:]) % 2 == 0 else 20.0


def _amp(w):
    return 0.5 if not w.startswith("2024-02") else 1.0 + 0.1 * _q(w)


def _pred_df():
    df = make_long(["A"], ["U1"], FEB + OTHER, 4,
                   lambda m, u, w, s: alt(_amp(w), s))
    df["window_ts"] = pd.to_datetime(df["window_ts"])
    df["err"] = df["y_pred"] - df["y_true"]
    return df


def _feat_df():
    rows = []
    for w in FEB + OTHER:
        for s in range(4):
            rows.append({"window_ts": w, "unit_id": "U1", "feature": "ghi",
                         "horizon_step": s, "f_pred": 100.0 + _q(w),
                         "f_true": 100.0})
    df = pd.DataFrame(rows)
    df["window_ts"] = pd.to_datetime(df["window_ts"])
    return df


def test_slice_autopick_and_sync():
    st = cfo.compute(_pred_df(), _feat_df())
    assert st["slice"] == "2024-02" and st["model"] == "A"
    ghi = st["features"]["ghi"]
    assert ghi["sync_basis"] == "quality"
    assert ghi["sync_corr"] > 0.99
    some_day = "2024-02-03"
    rec = ghi["aligned"][some_day]
    assert np.isclose(rec["y_rmse"], 3.0) and np.isclose(rec["quality"], 20.0)


def test_level_fallback_without_ftrue():
    fd = _feat_df()
    fd["f_true"] = np.nan
    st = cfo.compute(_pred_df(), fd)
    assert st["features"]["ghi"]["sync_basis"] == "level"


def test_main_writes_outputs(tmp_path):
    pp, fp = tmp_path / "p.csv", tmp_path / "f.csv"
    _pred_df().drop(columns=["err"]).to_csv(pp, index=False)
    _feat_df().to_csv(fp, index=False)
    cfo.main(["--pred", str(pp), "--features", str(fp),
              "--out-dir", str(tmp_path)])
    assert (tmp_path / "feature-trend-overlay.json").exists()
    assert (tmp_path / "feature-trend-overlay.png").exists()
```

- [ ] **Step 2: 跑测试确认失败**

Run: `python3 -m pytest ts-diagnose/chartbook/tests/test_chart_feature_trend_overlay.py -q`
Expected: FAIL（ModuleNotFoundError）

- [ ] **Step 3: 写 `chart_feature_trend_overlay.py`**

```python
"""feature-trend-overlay：焦点模型最差月份内，feature 走势/质量与 y 日误差的
对齐 overlay——「坏片上输入是不是也在坏」。

sync_basis：有 f_true → 用日均质量 |f_pred−f_true| 与日 RMSE 求 Pearson（quality）；
f_true 全缺 → 退化用日均 f_pred 水平（level，仅提示同步性、不可归因质量）。
"""
from __future__ import annotations

import argparse

import numpy as np
import pandas as pd

import chart_common as cc

RECIPE_ID = "feature-trend-overlay"


def compute(pred_df: pd.DataFrame, feat_df: pd.DataFrame,
            model: str | None = None, slice_month: str | None = None) -> dict:
    models = sorted(pred_df["model"].unique())
    focal = model or models[0]
    if focal not in models:
        raise ValueError(f"model {focal!r} 不在数据模型集 {models}")
    rr = cc.row_rmse(pred_df[pred_df["model"] == focal])
    rr["month"] = pd.to_datetime(rr["window_ts"]).dt.strftime("%Y-%m")
    rr["date"] = pd.to_datetime(rr["window_ts"]).dt.strftime("%Y-%m-%d")
    sl = slice_month or str(rr.groupby("month")["rmse"].mean().idxmax())
    in_rr = rr[rr["month"] == sl]
    y_daily = in_rr.groupby("date")["rmse"].mean()
    fd = feat_df.copy()
    fd["month"] = fd["window_ts"].dt.strftime("%Y-%m")
    fd["date"] = fd["window_ts"].dt.strftime("%Y-%m-%d")
    fd["quality"] = (fd["f_pred"] - fd["f_true"]).abs()
    out = {"recipe": RECIPE_ID, "model": focal, "slice": sl, "features": {},
           "note": "sync_corr=日 RMSE 与日均质量(或水平)的 Pearson；"
                   "level 口径只提示同步、不可归因质量。"}
    for feat, fg in fd[fd["month"] == sl].groupby("feature"):
        daily = fg.groupby("date").agg(f_pred=("f_pred", "mean"),
                                       f_true=("f_true", "mean"),
                                       quality=("quality", "mean"))
        aligned = daily.join(y_daily.rename("y_rmse"), how="inner").dropna(
            subset=["y_rmse"])
        has_quality = aligned["quality"].notna().any()
        basis_col = "quality" if has_quality else "f_pred"
        corr = float(aligned["y_rmse"].corr(aligned[basis_col])) \
            if len(aligned) >= 3 else None
        rec = {}
        for d, row in aligned.iterrows():
            item = {"y_rmse": round(float(row["y_rmse"]), 4),
                    "f_pred": round(float(row["f_pred"]), 4)}
            if np.isfinite(row["f_true"]):
                item["f_true"] = round(float(row["f_true"]), 4)
            if np.isfinite(row["quality"]):
                item["quality"] = round(float(row["quality"]), 4)
            rec[str(d)] = item
        out["features"][str(feat)] = {
            "aligned": cc.downsample(rec),
            "sync_basis": "quality" if has_quality else "level",
            "sync_corr": (round(corr, 4) if corr is not None
                          and np.isfinite(corr) else None),
            "n_days": int(len(aligned))}
    return out


def render(stats: dict):
    import matplotlib.pyplot as plt
    cc.setup_font()
    feats = list(stats["features"])
    fig, axes = plt.subplots(max(len(feats), 1), 1,
                             figsize=(11, 3 * max(len(feats), 1)),
                             squeeze=False)
    for ax, feat in zip(axes.ravel(), feats):
        e = stats["features"][feat]
        days = pd.to_datetime(list(e["aligned"]))
        ax.plot(days, [v["y_rmse"] for v in e["aligned"].values()],
                color="firebrick", label="y 日RMSE")
        ax2 = ax.twinx()
        key = "quality" if e["sync_basis"] == "quality" else "f_pred"
        ax2.plot(days, [v.get(key) for v in e["aligned"].values()],
                 color="steelblue", ls="--", label=key)
        ax.set_title(f"feature-trend-overlay {stats['slice']} — {feat} "
                     f"(corr={e['sync_corr']})", fontsize=10)
        ax.legend(loc="upper left"), ax2.legend(loc="upper right")
    fig.autofmt_xdate()
    fig.tight_layout()
    return fig


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--pred", required=True)
    ap.add_argument("--features", required=True)
    ap.add_argument("--out-dir", required=True)
    ap.add_argument("--model", default=None)
    ap.add_argument("--slice-month", default=None)
    a = ap.parse_args(argv)
    stats = compute(cc.load_predictions(a.pred), cc.load_features(a.features),
                    model=a.model, slice_month=a.slice_month)
    cc.save_outputs(render(stats), a.out_dir, RECIPE_ID, stats)


if __name__ == "__main__":
    main()
```

- [ ] **Step 4: 跑测试确认通过**

Run: `python3 -m pytest ts-diagnose/chartbook/tests/test_chart_feature_trend_overlay.py -q`
Expected: PASS（3 passed）

- [ ] **Step 5: 写 `recipes/feature-trend-overlay.md`**

````markdown
---
id: feature-trend-overlay
needs_materials: [predict, truth, features]
适用问题: 最差月份里 feature 是不是也在坏？输入质量恶化与 y 误差在时间上同步吗？
outputs:
  json: feature-trend-overlay.json
  png: feature-trend-overlay.png
json_schema: >
  slice（自动选焦点模型最差月，可指定）、每 feature：aligned 日对齐序列
  （y_rmse/f_pred/f_true?/quality?，降采样）、sync_basis(quality|level)、
  sync_corr、n_days。
bridge_hooks: >
  sync_corr 高（≥0.7）且 basis=quality → 输入质量事件驱动坏片的候选，与
  feature-error-conditional 的高比值 feature 交叉印证；坏片里 quality 平稳而
  y_rmse 突跳 → 输入无辜，转 rolling-stability 变点/外生事件类候选。
验证步: 坏月内日质量与日误差完全耦合 → 切片自动选中、corr>0.99、量值精确回收（tests/test_chart_feature_trend_overlay.py）
---

# feature-trend-overlay：坏片上的输入-误差对照

## 适用问题
error-breakdown / worst-slice-compare 定位坏片之后，看该片内输入质量走势是否
与误差同步——归因方向的第一道分流（输入侧 vs 模型侧）。

## CLI 与参数
```bash
python3 chartbook/scripts/chart_feature_trend_overlay.py \
  --pred predictions.parquet --features features.parquet \
  --out-dir <workdir>/charts [--model A] [--slice-month 2024-02]
```

## JSON schema
见 frontmatter；y 日指标 = 焦点模型日均行 RMSE（与 rolling-stability 同口径）。

## 判读
- `sync_corr ≥ 0.7` 且 basis=quality → 候选：输入质量事件——回
  feature-error-conditional 看该 feature 的 effect_ratio 是否也高（两线一致才升假设）；
- corr 低但坏片存在 → 候选：模型侧/其他输入——转 worst-points 看点级性质；
- basis=level 时 corr 高只说明"误差跟着量值走"（如辐照高误差大是正常物理），
  **不可**据此点名 feature 质量。
只给候选假设；结论回 playbook 三道门。

## 验证步
见 frontmatter。
````

- [ ] **Step 6: 跑一致性闸 + 引擎全绿**

Run: `python3 -m pytest ts-diagnose/ -q`
Expected: 全绿。

- [ ] **Step 7: Commit**

```bash
git add ts-diagnose/chartbook/
git commit -m "feat(ts-diagnose): chartbook feature-trend-overlay——坏片输入质量与 y 误差同步性对照"
```

---

### Task 4: `y-vs-feature-mapping`（D 组：y-feature 映射前后期对比）

**Files:**
- Create: `ts-diagnose/chartbook/scripts/chart_y_vs_feature_mapping.py`
- Create: `ts-diagnose/chartbook/recipes/y-vs-feature-mapping.md`
- Create: `ts-diagnose/chartbook/tests/test_chart_y_vs_feature_mapping.py`

**Interfaces:**
- Produces: `compute(pred_df, feat_df, split_date=None, n_bins=8) -> dict`；CLI `--pred --features --out-dir [--split-date YYYY-MM-DD] [--n-bins 8]`

- [ ] **Step 1: 写失败测试**

```python
"""y-vs-feature-mapping golden：前半期 y=0.5f、后半期 y=0.5f−5（物理映射整体
位移）→ 每箱 shift 恰为 −5、mean_abs_shift=5。分箱边界取全期 pooled 保两期可比。"""
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

import chart_y_vs_feature_mapping as cym  # noqa: E402
from synth import make_long                # noqa: E402

WINDOWS = [f"2024-01-{d:02d}" for d in range(1, 21)]   # 前 10 天 A 期、后 10 天 B 期


def _f(w, s):
    return 10.0 * s + int(w[-2:])          # f 随 step 与日铺开 10..170


def _y(w, s):
    base = 0.5 * _f(w, s)
    return base if int(w[-2:]) <= 10 else base - 5.0


def _pred_df():
    df = make_long(["A"], ["U1"], WINDOWS, 16,
                   err_fn=lambda m, u, w, s: 0.1,
                   y_fn=lambda w, u, s: _y(w, s))
    df["window_ts"] = pd.to_datetime(df["window_ts"])
    df["err"] = df["y_pred"] - df["y_true"]
    return df


def _feat_df():
    rows = [{"window_ts": w, "unit_id": "U1", "feature": "ghi",
             "horizon_step": s, "f_pred": _f(w, s), "f_true": _f(w, s)}
            for w in WINDOWS for s in range(16)]
    df = pd.DataFrame(rows)
    df["window_ts"] = pd.to_datetime(df["window_ts"])
    return df


def test_shift_recovered():
    st = cym.compute(_pred_df(), _feat_df(), split_date="2024-01-11")
    ghi = st["features"]["ghi"]
    assert np.isclose(ghi["mean_shift"], -5.0, atol=0.2)
    assert np.isclose(ghi["mean_abs_shift"], 5.0, atol=0.2)
    assert ghi["n_a"] == 160 and ghi["n_b"] == 160
    assert len(ghi["curve_a"]) >= 5 and len(ghi["curve_b"]) >= 5


def test_default_split_is_median():
    st = cym.compute(_pred_df(), _feat_df())
    assert st["split_date"].startswith("2024-01-1")   # 中位窗附近


def test_main_writes_outputs(tmp_path):
    pp, fp = tmp_path / "p.csv", tmp_path / "f.csv"
    _pred_df().drop(columns=["err"]).to_csv(pp, index=False)
    _feat_df().to_csv(fp, index=False)
    cym.main(["--pred", str(pp), "--features", str(fp),
              "--out-dir", str(tmp_path)])
    assert (tmp_path / "y-vs-feature-mapping.json").exists()
    assert (tmp_path / "y-vs-feature-mapping.png").exists()
```

- [ ] **Step 2: 跑测试确认失败**

Run: `python3 -m pytest ts-diagnose/chartbook/tests/test_chart_y_vs_feature_mapping.py -q`
Expected: FAIL（ModuleNotFoundError）

- [ ] **Step 3: 写 `chart_y_vs_feature_mapping.py`**

```python
"""y-vs-feature-mapping：y_true 与关键 feature 的映射曲线，按 split 日期分前后
两期对比——映射整体位移 = 物理关系改变（组件衰减/扩容/限电），所有模型同时受害。

分箱边界取全期 pooled 分位（两期同一把尺）；f 参考值 = f_true（缺则退 f_pred）。
把训练期数据并入对比：由适配器把训练段追加进两张长表再指定 --split-date 即可，
本脚本只认 split。
"""
from __future__ import annotations

import argparse

import numpy as np
import pandas as pd

import chart_common as cc

RECIPE_ID = "y-vs-feature-mapping"
JOIN = ["window_ts", "unit_id", "horizon_step"]


def compute(pred_df: pd.DataFrame, feat_df: pd.DataFrame,
            split_date: str | None = None, n_bins: int = 8) -> dict:
    first = pred_df["model"].iloc[0]
    y = pred_df[pred_df["model"] == first][JOIN + ["y_true"]].drop_duplicates()
    split = pd.Timestamp(split_date) if split_date else \
        pred_df["window_ts"].drop_duplicates().sort_values().reset_index(
            drop=True).median()
    fd = feat_df.copy()
    fd["f_ref"] = fd["f_true"].where(fd["f_true"].notna(), fd["f_pred"])
    out = {"recipe": RECIPE_ID, "split_date": str(split), "n_bins": n_bins,
           "features": {},
           "note": "curve_a=split 前、curve_b=split 后；分箱边界全期 pooled；"
                   "mean_shift=各公共箱 (b−a) 均值——整体位移 → 物理映射改变，"
                   "所有模型同时受害。"}
    for feat, fg in fd.groupby("feature"):
        j = fg.merge(y, on=JOIN, how="inner").dropna(subset=["f_ref", "y_true"])
        if j["f_ref"].nunique() < n_bins:
            continue
        edges = np.unique(j["f_ref"].quantile(
            np.linspace(0, 1, n_bins + 1)).values)
        j = j.copy()
        j["bin"] = pd.cut(j["f_ref"], bins=edges, include_lowest=True)
        j["period"] = np.where(j["window_ts"] < split, "a", "b")
        g = j.groupby(["bin", "period"], observed=True).agg(
            f=("f_ref", "mean"), yv=("y_true", "mean"), n=("y_true", "size"))
        curves = {"a": {}, "b": {}}
        shifts = []
        for b in j["bin"].cat.categories:
            try:
                ra = g.loc[(b, "a")]
                rb = g.loc[(b, "b")]
            except KeyError:
                continue
            key = f"{(ra.f + rb.f) / 2:.2f}"
            curves["a"][key] = round(float(ra.yv), 4)
            curves["b"][key] = round(float(rb.yv), 4)
            shifts.append(float(rb.yv - ra.yv))
        out["features"][str(feat)] = {
            "curve_a": curves["a"], "curve_b": curves["b"],
            "mean_shift": round(float(np.mean(shifts)), 4) if shifts else None,
            "mean_abs_shift": (round(float(np.mean(np.abs(shifts))), 4)
                               if shifts else None),
            "n_a": int((j["period"] == "a").sum()),
            "n_b": int((j["period"] == "b").sum())}
    return out


def render(stats: dict):
    import matplotlib.pyplot as plt
    cc.setup_font()
    feats = list(stats["features"])
    fig, axes = plt.subplots(1, max(len(feats), 1),
                             figsize=(6 * max(len(feats), 1), 4.5),
                             squeeze=False)
    for ax, feat in zip(axes.ravel(), feats):
        e = stats["features"][feat]
        for period, color in (("curve_a", "steelblue"), ("curve_b", "firebrick")):
            xs = [float(k) for k in e[period]]
            ax.plot(xs, list(e[period].values()), "-o", ms=3, color=color,
                    label=period[-1] + " 期")
        ax.set_title(f"y-vs-feature-mapping — {feat} "
                     f"(shift={e['mean_shift']})", fontsize=10)
        ax.set_xlabel(feat), ax.set_ylabel("y_true 均值"), ax.legend()
    fig.tight_layout()
    return fig


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--pred", required=True)
    ap.add_argument("--features", required=True)
    ap.add_argument("--out-dir", required=True)
    ap.add_argument("--split-date", default=None)
    ap.add_argument("--n-bins", type=int, default=8)
    a = ap.parse_args(argv)
    stats = compute(cc.load_predictions(a.pred), cc.load_features(a.features),
                    split_date=a.split_date, n_bins=a.n_bins)
    cc.save_outputs(render(stats), a.out_dir, RECIPE_ID, stats)


if __name__ == "__main__":
    main()
```

- [ ] **Step 4: 跑测试确认通过**

Run: `python3 -m pytest ts-diagnose/chartbook/tests/test_chart_y_vs_feature_mapping.py -q`
Expected: PASS（3 passed）

- [ ] **Step 5: 写 `recipes/y-vs-feature-mapping.md`**

````markdown
---
id: y-vs-feature-mapping
needs_materials: [predict, truth, features]
适用问题: y 与关键 feature 的物理映射关系变了吗？（组件衰减/扩容/限电类整体位移）
outputs:
  json: y-vs-feature-mapping.json
  png: y-vs-feature-mapping.png
json_schema: >
  split_date（默认中位窗）、每 feature：curve_a/curve_b（pooled 分箱 → y_true
  均值）、mean_shift / mean_abs_shift、n_a/n_b。
bridge_hooks: >
  曲线整体平移（mean_abs_shift 大且各箱同号）→ 物理映射改变类候选——所有模型
  同时受害，与 model-error-correlation 全对高相关联判；仅高值段偏移 → 容量/
  限电类候选。
验证步: 前后期植入 −5 整体位移 → 每箱 shift 精确回收（tests/test_chart_y_vs_feature_mapping.py）
---

# y-vs-feature-mapping：物理映射前后期对比

## 适用问题
误差抬升是"模型退化"还是"世界变了"——映射位移指向后者。要对比训练期 vs
测试期时，由适配器把训练段并入两张长表后用 `--split-date` 指定训练/测试分界。

## CLI 与参数
```bash
python3 chartbook/scripts/chart_y_vs_feature_mapping.py \
  --pred predictions.parquet --features features.parquet \
  --out-dir <workdir>/charts [--split-date 2024-02-01] [--n-bins 8]
```

## JSON schema
见 frontmatter；f 参考值 = f_true 缺则 f_pred（level 口径时位移解释要谨慎）。

## 判读
- `mean_abs_shift` 显著（相对 y 量级 >10%）且各箱同号 → 候选：物理映射整体改变
  ——去 train-test-drift（有 train_y 时）与 rolling-stability 变点交叉定位发生时点；
- 仅个别箱偏移 → 候选：该值域样本构成变化，先查 n_a/n_b 箱内样本量再判读；
- 无位移但误差抬升 → 排除"世界变了"，归因回模型/输入质量侧。
只给候选假设；结论回 playbook 三道门。

## 验证步
见 frontmatter。
````

- [ ] **Step 6: 跑一致性闸 + 引擎全绿**

Run: `python3 -m pytest ts-diagnose/ -q`
Expected: 全绿。

- [ ] **Step 7: Commit**

```bash
git add ts-diagnose/chartbook/
git commit -m "feat(ts-diagnose): chartbook y-vs-feature-mapping——物理映射前后期位移检测"
```

---

### Task 5: `train-test-drift`（E 组：训练/测试同月分布对比）

**Files:**
- Create: `ts-diagnose/chartbook/scripts/chart_train_test_drift.py`
- Create: `ts-diagnose/chartbook/recipes/train-test-drift.md`
- Create: `ts-diagnose/chartbook/tests/test_chart_train_test_drift.py`

**Interfaces:**
- Produces: `chart_train_test_drift.TRAIN_COLS = ("ts","unit_id","y")`、`load_train_y(path)`（本脚本内，校验三列+ts 转 datetime）、`psi(a, b, bins=10) -> float`、`compute(pred_df, train_df, psi_alert=0.25) -> dict`；CLI `--pred --train-y --out-dir [--psi-alert 0.25]`

- [ ] **Step 1: 写失败测试**

```python
"""train-test-drift golden：1 月 train/test 同分布（PSI≈0）、2 月 test 整体 +20
（PSI 显著）→ 逐月 PSI/分位摘要回收、告警月列表恰为 ["2"]。"""
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

import chart_train_test_drift as ctd  # noqa: E402
from synth import make_long           # noqa: E402

CYCLE = [10.0, 12.0, 14.0, 16.0]


def _train_df():
    rows = []
    for mm in (1, 2):
        for i in range(200):
            rows.append({"ts": f"2023-{mm:02d}-{(i % 27) + 1:02d}",
                         "unit_id": "U1", "y": CYCLE[i % 4]})
    df = pd.DataFrame(rows)
    df["ts"] = pd.to_datetime(df["ts"])
    return df


def _pred_df():
    windows = [f"2024-{mm:02d}-{dd:02d}" for mm in (1, 2)
               for dd in range(1, 26)]

    def y_fn(w, u, s):
        base = CYCLE[(int(w[-2:]) + s) % 4]
        return base if w[5:7] == "01" else base + 20.0

    df = make_long(["A"], ["U1"], windows, 8,
                   err_fn=lambda m, u, w, s: 0.1, y_fn=y_fn)
    df["window_ts"] = pd.to_datetime(df["window_ts"])
    df["err"] = df["y_pred"] - df["y_true"]
    return df


def test_psi_helper_extremes():
    a = np.array(CYCLE * 50)
    assert ctd.psi(a, a) < 1e-6
    assert ctd.psi(a, a + 20.0) > 0.25


def test_monthly_drift_recovered():
    st = ctd.compute(_pred_df(), _train_df())
    assert st["by_month"]["1"]["psi"] < 0.05
    assert st["by_month"]["2"]["psi"] > 0.25
    assert st["alert_months"] == ["2"]
    m1 = st["by_month"]["1"]
    for k in ("n_train", "n_test", "mean_train", "mean_test",
              "median_train", "median_test", "p90_train", "p90_test"):
        assert k in m1
    assert np.isclose(m1["mean_train"], 13.0, atol=0.5)


def test_main_writes_outputs(tmp_path):
    pp, tp = tmp_path / "p.csv", tmp_path / "t.csv"
    _pred_df().drop(columns=["err"]).to_csv(pp, index=False)
    _train_df().to_csv(tp, index=False)
    ctd.main(["--pred", str(pp), "--train-y", str(tp),
              "--out-dir", str(tmp_path)])
    assert (tmp_path / "train-test-drift.json").exists()
    assert (tmp_path / "train-test-drift.png").exists()
```

- [ ] **Step 2: 跑测试确认失败**

Run: `python3 -m pytest ts-diagnose/chartbook/tests/test_chart_train_test_drift.py -q`
Expected: FAIL（ModuleNotFoundError）

- [ ] **Step 3: 写 `chart_train_test_drift.py`**

```python
"""train-test-drift：训练期 y 与测试期 y_true 的同日历月分布对比（PSI+分位摘要，
scipy 可用时附 KS p 值）。PSI>psi_alert 的月进告警列表——分布漂移候选。

train_y 长表：ts|unit_id|y；test 侧 y_true 取自 predictions（首模型去重）。
同月对比 = 日历月号（1..12），跨年可比季节位（fig 泛化口径）。
"""
from __future__ import annotations

import argparse

import numpy as np
import pandas as pd

import chart_common as cc

RECIPE_ID = "train-test-drift"
TRAIN_COLS = ("ts", "unit_id", "y")


def load_train_y(path):
    from pathlib import Path
    p = Path(path)
    df = pd.read_parquet(p) if p.suffix == ".parquet" else pd.read_csv(p)
    missing = [c for c in TRAIN_COLS if c not in df.columns]
    if missing:
        raise ValueError(f"train_y 长表缺列 {missing}；需要 {list(TRAIN_COLS)}")
    df = df.copy()
    df["ts"] = pd.to_datetime(df["ts"])
    return df


def psi(a, b, bins: int = 10) -> float:
    """Population Stability Index：分箱边界取 a 的分位（含 ±inf 兜底两侧溢出）。"""
    a, b = np.asarray(a, float), np.asarray(b, float)
    edges = np.unique(np.quantile(a, np.linspace(0, 1, bins + 1)))
    edges[0], edges[-1] = -np.inf, np.inf
    pa, _ = np.histogram(a, bins=edges)
    pb, _ = np.histogram(b, bins=edges)
    fa = np.clip(pa / max(pa.sum(), 1), 1e-4, None)
    fb = np.clip(pb / max(pb.sum(), 1), 1e-4, None)
    return float(np.sum((fa - fb) * np.log(fa / fb)))


def _q(arr, side):
    return {f"n_{side}": int(arr.size),
            f"mean_{side}": round(float(np.mean(arr)), 2),
            f"std_{side}": round(float(np.std(arr)), 2),
            f"p10_{side}": round(float(np.percentile(arr, 10)), 2),
            f"p25_{side}": round(float(np.percentile(arr, 25)), 2),
            f"median_{side}": round(float(np.median(arr)), 2),
            f"p75_{side}": round(float(np.percentile(arr, 75)), 2),
            f"p90_{side}": round(float(np.percentile(arr, 90)), 2)}


def compute(pred_df: pd.DataFrame, train_df: pd.DataFrame,
            psi_alert: float = 0.25) -> dict:
    try:
        from scipy.stats import ks_2samp
    except ImportError:
        ks_2samp = None
    first = pred_df["model"].iloc[0]
    test = pred_df[pred_df["model"] == first][
        ["window_ts", "unit_id", "horizon_step", "y_true"]].drop_duplicates()
    test_month = test["window_ts"].dt.month
    train_month = train_df["ts"].dt.month
    out = {"recipe": RECIPE_ID, "psi_alert": psi_alert, "by_month": {},
           "alert_months": [],
           "note": "同日历月对比（跨年比季节位）；PSI>阈值 → 分布漂移候选，"
                   "所有模型同时受害类机制。"}
    for m in range(1, 13):
        a = train_df.loc[train_month == m, "y"].dropna().to_numpy()
        b = test.loc[test_month == m, "y_true"].dropna().to_numpy()
        if len(a) < 10 or len(b) < 10:
            continue
        p = psi(a, b)
        entry = {"psi": round(p, 4),
                 "ks_p": (float(ks_2samp(a, b).pvalue) if ks_2samp else None),
                 **_q(a, "train"), **_q(b, "test")}
        out["by_month"][str(m)] = entry
        if p > psi_alert:
            out["alert_months"].append(str(m))
    return out


def render(stats: dict):
    import matplotlib.pyplot as plt
    cc.setup_font()
    months = list(stats["by_month"])
    fig, ax = plt.subplots(figsize=(1.1 * max(len(months), 4) + 3, 4))
    vals = [stats["by_month"][m]["psi"] for m in months]
    colors = ["firebrick" if m in stats["alert_months"] else "steelblue"
              for m in months]
    ax.bar(months, vals, color=colors)
    ax.axhline(stats["psi_alert"], color="k", ls="--", lw=0.8,
               label=f"alert={stats['psi_alert']}")
    ax.set_xlabel("日历月"), ax.set_ylabel("PSI")
    ax.set_title("train-test-drift 逐月标签分布漂移"), ax.legend()
    fig.tight_layout()
    return fig


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--pred", required=True)
    ap.add_argument("--train-y", required=True)
    ap.add_argument("--out-dir", required=True)
    ap.add_argument("--psi-alert", type=float, default=0.25)
    a = ap.parse_args(argv)
    stats = compute(cc.load_predictions(a.pred), load_train_y(a.train_y),
                    psi_alert=a.psi_alert)
    cc.save_outputs(render(stats), a.out_dir, RECIPE_ID, stats)


if __name__ == "__main__":
    main()
```

- [ ] **Step 4: 跑测试确认通过**

Run: `python3 -m pytest ts-diagnose/chartbook/tests/test_chart_train_test_drift.py -q`
Expected: PASS（3 passed）

- [ ] **Step 5: 写 `recipes/train-test-drift.md`**

````markdown
---
id: train-test-drift
needs_materials: [predict, truth, train_y]
适用问题: 测试期标签分布还像训练期吗？哪些月漂了、漂多少？
outputs:
  json: train-test-drift.json
  png: train-test-drift.png
json_schema: >
  by_month（日历月 → psi/ks_p/train-test 双侧 n/mean/std/p10..p90 分位摘要）、
  alert_months（PSI>阈值月列表）、psi_alert。
bridge_hooks: >
  某月 PSI 告警且该月误差也峰值（error-breakdown per_month）→ 分布漂移主导候选
  ——所有模型同时受害，与 model-error-correlation 高相关联判；PSI 全绿但误差
  抬升 → 排除标签漂移，转输入质量/模型侧。
验证步: 2 月 test 整体+20（PSI>0.25）、1 月同分布（PSI≈0）→ 告警列表恰为 ["2"]（tests/test_chart_train_test_drift.py）
---

# train-test-drift：训练/测试标签分布漂移

## 适用问题
"世界变了吗"的分布级证据；与 y-vs-feature-mapping（映射级）互为印证。

## CLI 与参数
```bash
python3 chartbook/scripts/chart_train_test_drift.py \
  --pred predictions.parquet --train-y train_y.parquet \
  --out-dir <workdir>/charts [--psi-alert 0.25]
```
train_y 长表：`ts|unit_id|y`。v1 只做标签漂移；feature 漂移待训练期 feature
材料定义后扩展。

## JSON schema
见 frontmatter；月样本 <10 双侧任一即跳过该月（不进 by_month）。

## 判读
- `alert_months` 非空 → 候选：季节性/结构性漂移——对照 error-breakdown 的
  per_month 边际曲线看漂移月是否同为误差峰值月（两线一致才升假设）；
- PSI 高但 mean 差小（分位摘要形变）→ 候选：分布形状变（双峰/截断），看
  p10/p90 差异定位哪一侧；
- scipy 缺席时 ks_p=null，仅凭 PSI 判读（阈值 0.25 为业界惯例、可调）。
只给候选假设；结论回 playbook 三道门。

## 验证步
见 frontmatter。
````

- [ ] **Step 6: 跑一致性闸 + 引擎全绿**

Run: `python3 -m pytest ts-diagnose/ -q`
Expected: 全绿。

- [ ] **Step 7: Commit**

```bash
git add ts-diagnose/chartbook/
git commit -m "feat(ts-diagnose): chartbook train-test-drift——逐月 PSI 标签分布漂移+分位摘要"
```

---

### Task 6: playbook 阶段级 `charts:` 声明——engine_common 校验 + orient 可画性输出

**Files:**
- Modify: `ts-diagnose/scripts/engine_common.py`
- Modify: `ts-diagnose/scripts/orient.py`
- Modify: `ts-diagnose/playbooks/_playbook-spec.md`
- Create: `ts-diagnose/scripts/tests/test_charts_decl.py`

**Interfaces:**
- Produces（Task 7/9 的 frontmatter 依赖）：
  - `engine_common.recipe_path(rid) -> str`（`<ENGINE>/chartbook/recipes/<rid>.md`）
  - `engine_common.available_recipes() -> list[str]`（recipes/*.md 的 id 列表，目录缺失返回 []）
  - `engine_common.recipe_materials(rid) -> list[str]`（解析 recipe frontmatter 的 needs_materials；recipe 不存在 → ValueError 列出可用 id）
  - `engine_common.charts_report(fm, cfg) -> list[(stage_id, rid, missing:list[str])]`（missing 为该 recipe needs_materials 中 status≠present 的材料 id；空列表=可画）
  - `_validate_frontmatter`：stages 里可选 `charts` 键——必须是字符串列表且每个 id ∈ available_recipes()，否则 ValueError（报出可用 id）
- orient 行为：stage 列表打印中，声明了 charts 的阶段逐图输出 `📊 <rid> ✓可画` 或 `📊 <rid> ✗缺材料:<ids>（自动跳过，不阻塞）`；**不进开工闸**（缺材料的图跳过不算失败）。

**实现指引**（integration 任务，改动嵌入既有代码——先读文件再动手）：
- `engine_common.py`：在 materials 区块（`MATERIAL_IDS` 附近）之后加四个函数。`recipe_materials` 解析：读文件、`re.match(r"^---\n(.*?)\n---", text, re.S)` 取 frontmatter、`yaml.safe_load`、返回 `fm.get("needs_materials") or []`。`charts_report` 用已有 `material_status(cfg, mid)`。`_validate_frontmatter` 的 stages 循环里加 charts 校验（非列表/含非字符串/未知 id 各自 ValueError，消息含 `_playbook-spec.md` 指引与 available_recipes() 列表）。
- `orient.py`：定位 stage 打印循环（约 115 行 `for st in fm["stages"]:`），在每 stage 的 prereq 行之后加 charts 段（读 `st.get("charts")`，逐条按 `charts_report` 结果打印）。注意：charts_report 按整个 fm 算一次、按 stage_id 过滤即可。
- `_playbook-spec.md`：frontmatter 示例 stages 里加一行 `charts: [horizon-degradation]     # 可选。本阶段消费的 chartbook recipe id（须存在于 chartbook/recipes/）；orient 按 needs_materials × 盘点结果逐图报可画/缺材料自动跳过`；§4 正文必备节第 2 条补一句：「声明了 charts 的阶段，正文菜谱写清各图的调用命令与参数（预写脚本，禁现场重写；见 engine-core chartbook 豁免）」。

- [ ] **Step 1: 写失败测试 `test_charts_decl.py`**

```python
"""charts 声明：frontmatter 校验（未知 recipe id 报错并列出可用）、recipe_materials
解析、charts_report 按盘点结果分可画/缺材料、orient e2e 输出。"""
import json
import os
import subprocess
import sys
import textwrap

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
import engine_common as ec  # noqa: E402

ENGINE = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def _pb(tmp_path, charts_line):
    d = tmp_path / "playbooks" / "demo-charts"
    d.mkdir(parents=True)
    (d / "playbook.md").write_text(textwrap.dedent(f"""\
        ---
        id: demo-charts
        name: demo
        goal: g
        stages:
          - id: 0
            name: s0
            done_when: {{artifacts: ["x.json"]}}
        {charts_line}
        materials:
          required: [predict, truth]
          optional: [features]
        ---
        正文
        """))
    return str(d / "playbook.md")


def test_recipe_materials_reads_frontmatter():
    assert ec.recipe_materials("error-breakdown") == ["predict", "truth"]
    assert "features" in ec.recipe_materials("feature-error-conditional")


def test_recipe_materials_unknown_id_lists_available():
    with pytest.raises(ValueError, match="error-breakdown"):
        ec.recipe_materials("no-such-recipe")


def test_frontmatter_rejects_unknown_chart_id(tmp_path):
    p = _pb(tmp_path, "    charts: [no-such-recipe]")
    with pytest.raises(ValueError, match="no-such-recipe"):
        ec.load_frontmatter(p)


def test_frontmatter_rejects_non_list_charts(tmp_path):
    p = _pb(tmp_path, "    charts: error-breakdown")
    with pytest.raises(ValueError, match="charts"):
        ec.load_frontmatter(p)


def test_charts_report_splits_by_materials(tmp_path):
    p = _pb(tmp_path, "    charts: [error-breakdown, feature-error-conditional]")
    fm = ec.load_frontmatter(p)
    cfg = {"materials": {"predict": {"status": "present"},
                         "truth": {"status": "present"}}}
    rep = ec.charts_report(fm, cfg)
    by_rid = {rid: missing for (_sid, rid, missing) in rep}
    assert by_rid["error-breakdown"] == []
    assert "features" in by_rid["feature-error-conditional"]


def test_orient_prints_chart_availability(tmp_path):
    pb_dir = tmp_path / "playbooks" / "demo-charts"
    _pb(tmp_path, "    charts: [error-breakdown, feature-error-conditional]")
    cfg = {"playbook": "demo-charts",
           "materials": {"predict": {"status": "present"},
                         "truth": {"status": "present"}}}
    (tmp_path / "diagnose_config.json").write_text(json.dumps(cfg))
    proc = subprocess.run(
        [sys.executable, os.path.join(ENGINE, "scripts", "orient.py"),
         "--playbook", str(pb_dir)],
        cwd=tmp_path, capture_output=True, text=True)
    out = proc.stdout
    assert "✓可画" in out and "error-breakdown" in out
    assert "✗缺材料" in out and "feature-error-conditional" in out
```

注意最后一个 e2e 测试：先确认 orient `--playbook` 是否接受目录/文件路径（Plan 1 的
test_orient_materials.py 有现成的 run_orient/setup 模式——照抄那里的调用方式，
如需传 id 则把 demo playbook 建进 tmp 引擎镜像，跟随既有测试的做法，**不得**为
测试改 orient 的 CLI 语义）。若既有模式是拷贝 orient 所需文件到 tmp，沿用之。

- [ ] **Step 2: 跑测试确认失败**

Run: `python3 -m pytest ts-diagnose/scripts/tests/test_charts_decl.py -q`
Expected: FAIL（AttributeError: recipe_materials）

- [ ] **Step 3: 实现 engine_common 四函数 + frontmatter 校验 + orient 输出 + spec 文档**

engine_common 新增（放 materials 函数区之后）：

```python
def recipe_path(rid):
    return os.path.join(ENGINE_DIR, "chartbook", "recipes", f"{rid}.md")


def available_recipes():
    d = os.path.join(ENGINE_DIR, "chartbook", "recipes")
    if not os.path.isdir(d):
        return []
    return sorted(os.path.splitext(f)[0] for f in os.listdir(d)
                  if f.endswith(".md"))


def recipe_materials(rid):
    """chartbook recipe 的 needs_materials（orient 可画性判定用）。"""
    p = recipe_path(rid)
    if not os.path.exists(p):
        raise ValueError(f"未知 chartbook recipe '{rid}'；可用：{available_recipes()}")
    with open(p, encoding="utf-8") as f:
        text = f.read()
    m = re.match(r"^---\n(.*?)\n---", text, re.S)
    fm = yaml.safe_load(m.group(1)) if m else {}
    return list(fm.get("needs_materials") or [])


def charts_report(fm, cfg):
    """→ [(stage_id, recipe_id, missing_materials)]；missing 空 = 可画。"""
    rep = []
    for st in fm.get("stages") or []:
        for rid in st.get("charts") or []:
            missing = [mid for mid in recipe_materials(rid)
                       if material_status(cfg, mid) != "present"]
            rep.append((st["id"], rid, missing))
    return rep
```

（`ENGINE_DIR` / `re` / `yaml` / `os` 若 engine_common 已有同义常量或导入则复用，
不重复定义；ENGINE_DIR 语义 = ts-diagnose 根目录。）

`_validate_frontmatter` stages 循环内加：

```python
        charts = st.get("charts")
        if charts is not None:
            if not isinstance(charts, list) or not all(
                    isinstance(c, str) for c in charts):
                raise ValueError(
                    f"stage {st.get('id')} 的 charts 必须是字符串列表"
                    "（见 _playbook-spec.md）")
            known = available_recipes()
            bad = [c for c in charts if c not in known]
            if bad:
                raise ValueError(
                    f"stage {st.get('id')} 的 charts 含未知 recipe {bad}；"
                    f"可用：{known}")
```

orient.py stage 循环内（prereq 打印后）加：

```python
        if st.get("charts"):
            for (_sid, rid, missing) in ec.charts_report(fm, cfg):
                if _sid != st["id"]:
                    continue
                if missing:
                    print(f"    📊 {rid} ✗缺材料:{','.join(missing)}"
                          "（自动跳过，不阻塞）")
                else:
                    print(f"    📊 {rid} ✓可画")
```

（`cfg` 用 orient 已加载的 config 变量名；对照上下文命名。）

- [ ] **Step 4: 跑测试确认通过 + 引擎全绿**

Run: `python3 -m pytest ts-diagnose/scripts/tests/test_charts_decl.py -q && python3 -m pytest ts-diagnose/ -q`
Expected: 全绿（旧 playbook 无 charts 键零回归）。

- [ ] **Step 5: Commit**

```bash
git add ts-diagnose/scripts/ ts-diagnose/playbooks/_playbook-spec.md
git commit -m "feat(ts-diagnose): playbook 阶段级 charts 声明——frontmatter 校验+orient 逐图可画性报告"
```

---

### Task 7: model-comparison playbook（frontmatter + 正文菜谱）

**Files:**
- Create: `ts-diagnose/playbooks/model-comparison/playbook.md`

**Interfaces:**
- Consumes: Task 6 的 charts 声明（Stage 2）、Plan 1 的 materials/contexts/provider_skill 机制
- Produces: Task 8 的 golden 断言目标（Stage 1 脚本 CLI 契约：`--pred <长表> --pair A,B --out gap_summary.json`；Stage 2 直接调 chartbook 预写脚本）

**frontmatter（逐字）**：

```yaml
---
id: model-comparison
name: 多模型对比归因
goal: 量化「模型 A 为什么比 B 好/差」，把差距分解到片段/时效/输入并归因到机制
stages:
  - id: 0
    name: 口径与对齐
    done_when:
      artifacts: ["alignment_report.json"]
    prereqs:
      - desc: 考核口径已定
        check: "question:metric-caliber"
      - desc: 对比模型集已定
        check: "question:model-set"
  - id: 1
    name: 总差距事实
    done_when:
      artifacts: ["gap_summary.json"]
    prereqs:
      - desc: 对齐完成
        check: "stage:0"
  - id: 2
    name: 差距分解（事实）
    done_when:
      artifacts: ["charts/*.json"]
      findings_marker: "现象"
    prereqs:
      - desc: 总差距已知
        check: "stage:1"
    pause_after: true
    charts: [error-breakdown, intraday-profile, worst-points,
             horizon-degradation, rolling-stability, true-vs-pred-scatter,
             model-error-correlation, worst-slice-compare, oracle-gap,
             feature-error-conditional, feature-trend-overlay,
             y-vs-feature-mapping, train-test-drift]
  - id: 3
    name: 机制归因（变体）
    done_when:
      findings_marker: "假设"
    prereqs:
      - desc: 模型档案上下文已解决（linked 或 declined）
        check: "config:model_profile_status"
  - id: 4
    name: 结论
    done_when:
      artifacts: ["CONCLUSION.md"]
    subagent_ok: false
    prereqs:
      - desc: 现象清单已停顿汇报
        check: "stage:2"
materials:
  required: [predict, truth]
  optional: [model_code, training_log, experiment_config, features, train_y]
variants:
  - id: mechanism
    when: "material:model_code"
    unlocks_stages: [3]
questions:
  - id: metric-caliber
    stage: 0
    ask: "考核口径是什么？（默认 rmse_192=每行全部 horizon 点的 RMSE；也可指定子段或自定义）"
    why: "口径不同结论可反转——horizon 交叉存在时尤甚"
    options: ["rmse_192（默认）", "指定 horizon 子段", "自定义公式"]
    default: "rmse_192"
  - id: align-keys
    stage: 0
    ask: "各模型预测按什么键对齐？缺窗如何处理？（默认 window_ts+unit_id 内连接）"
    why: "对齐错位会把数据覆盖差异误判成模型差异"
    options: ["window_ts+unit_id 内连接（默认）", "其他"]
    default: "window_ts+unit_id 内连接"
  - id: model-set
    stage: 0
    ask: "这次对比哪些模型？多于 2 个时，最关注哪一对（如 A vs B）？"
    why: "全集对比与定向配对的分解深度不同；配对决定 Stage 1 的差距检验对象"
    default: null
contexts:
  - id: model-profile
    name: 模型架构档案
    workdir_key: model_profile_dir
    status_key: model_profile_status
    marker_files: ["models.md"]
    on_absent: ask
    provider_skill: pv-model-analysis
    trigger_material: model_code
evidence_lines:
  - id: total-gap
    stage: 1
    output: gap_summary.json
  - id: slice-gap
    stage: 2
    output: charts/worst-slice-compare.json
upgrade_rule: "总差距方向（gap_summary 排名）与主导切片方向（worst-slice 片内排名）一致才把差距结论从「现象」升「假设」"
---
```

**正文必备七节（逐字，_playbook-spec §4 顺序）**：

```markdown
# model-comparison：多模型对比归因

## 1. 问题框定与首要陷阱

「A 比 B 好」不是结论，是三个待验证命题的合取：①在**这个口径**下好（口径换了
可反转——horizon-degradation 的交叉点存在时必须先回 Stage 0 确认口径再比）；
②在**对齐样本**上好（缺窗不对称时，差距可能是覆盖差异——先看 alignment_report
的 dropped 统计）；③好得**稳定**（差距集中在一个月 ≠ 普遍领先——看
worst-slice-compare 的集中度）。首要陷阱：**排名≠机制**——Stage 1/2 全部是事实
阶段，禁机制语言；机制只能在 Stage 3 经模型档案桥接假设 + 图 JSON 证据合流产生。
量纲纪律：点级 pool 口径（error-breakdown/horizon 等）与行 RMSE 均值口径
（rolling-stability/oracle-gap 等）两族数值不可直接比大小，只比走势与排名。

## 2. 逐阶段菜谱

### Stage 0 口径与对齐
输入：materials 盘点后的 predict/truth 原始数据。
菜谱：现场只写薄适配器 `analysis_scripts/adapter.py`（用户格式 → 规范长表
predictions，见 chartbook/_recipe-spec.md §2；有 feature/train_y 材料时同步产
features/train_y 长表），过**对账两关**（行数守恒 + 抽 3 窗数值核对，样例
chartbook/golden/example_adapter/），对账记录写 PROGRESS.md。随后写
`analysis_scripts/align.py`：按 align-keys 答案对齐各模型 → 落
`alignment_report.json`（schema：`{"models":[...], "n_rows_per_model":{},
"n_aligned":int, "n_dropped_per_model":{}, "caliber":"rmse_192|...",
"note":"dropped 不对称时的说明"}`，自足）。
验证步：合成 3 窗小样跑 align.py，n_aligned 与手数一致。
done：alignment_report.json 落盘。

### Stage 1 总差距事实
菜谱：写 `analysis_scripts/gap_metrics.py`，CLI 契约固定：
`--pred predictions.csv --pair A,B --out gap_summary.json`。
计算（口径=rmse_192 时）：每 (model,unit,window) 行 RMSE → 每模型均值与排名；
配对差 d_i = rmse_focal_i − rmse_other_i（对齐行内逐样本）→ mean_diff、
win_rate（d<0 占比）、符号检验正态近似 z=(wins−n/2)/sqrt(n/4) 与双侧 p。
落 `gap_summary.json`（schema：`{"caliber":str, "per_model":{m:mean},
"ranking":[...], "pair":[A,B], "n":int, "mean_diff":float, "win_rate":float,
"sign_z":float, "sign_p":float, "note":"差距是真的还是噪声：|z|<2 时只写现象
不写方向"}`）。
**生成闸（硬规则）**：真实数据前先过
`python3 <ENGINE>/scripts/gen_gate.py --script analysis_scripts/gap_metrics.py \
  --playbook model-comparison --stage 1`。
验证步：gen_gate 金标准（golden/ 植入已知差距结构）全 expect 通过。
done：gap_summary.json 落盘。

### Stage 2 差距分解（事实）
**不写图代码**——frontmatter charts 声明的图全部用 chartbook 预写脚本
（engine-core chartbook 豁免），orient 已按材料标好可画/跳过；命令模板：

    python3 <ENGINE>/chartbook/scripts/chart_<蛇形id>.py \
      --pred predictions.csv --out-dir charts/ [各图特有参数]

（worst-slice-compare 传 `--focal-model` = model-set 答案里的关注模型；D 组图
加 `--features features.csv`；train-test-drift 加 `--train-y train_y.csv`。）
判读读各图 JSON 的描述符（recipe 判读节），产出 FINDINGS.md 现象清单——
只写「现象」；因缺材料跳过的图逐条注明「因缺 <材料> 未画」。
done：charts/*.json 至少一个 + FINDINGS.md 含「现象」→ **pause_after 停顿**。

### Stage 3 机制归因（变体，material:model_code 解锁）
输入：model-profile 上下文（contexts 机制：linked 目录下 models.md 的桥接假设
H-ID）+ Stage 2 图 JSON。
菜谱：逐条桥接假设 → 找它预言的图形态（bridge_hooks）→ 对照实际描述符；
两条证据线（total-gap 与 slice-gap）方向一致才把「现象」升「假设」
（upgrade_rule）。产出写回 FINDINGS.md（状态用保留字）。
done：FINDINGS.md 出现「假设」。

### Stage 4 结论
主 agent 亲自做（subagent_ok: false）。三道门（references/mechanisms.md）+
本 playbook 反驳门（§6）逐条过 → 跑 `scripts/provenance.py` 归因闸 → 写
CONCLUSION.md（末尾附 Provenance 块）。

## 3. 证据升级规则

- 现象 → 假设：upgrade_rule（两线方向一致）**且** |sign_z| ≥ 2（差距非噪声）；
- 假设 → 已证实：仅当机制预言了**未用于生成假设的**新图形态且被验证（三道门
  之门 2），或用户提供外部实验（换 checkpoint/换输入重跑）证实；
- 任何一步不满足 → 停在当前层级，结论如实写层级。

## 4. 停顿点与汇报

Stage 2 完成即停：向用户汇报 ①gap_summary 的排名与 z ②已画/跳过图清单
③Top-3 现象（引用图 JSON 数字）。请用户点名：补画哪张图/调参数（top-N、切片
粒度）/指定下一步关注的配对或片段。用户不点名则按 orient 推荐推进。

## 5. subagent 拆分建议

Stage 2 各图独立可并发：每图一子代理，brief 只带命令模板+长表路径+输出目录
（互不同文件天然防竞态，见 references/subagent-briefs.md）；判读与 FINDINGS
汇总由主 agent 做。Stage 0/1/4 不拆。

## 6. 结论模板与特有反驳门

模板（CONCLUSION.md）：口径与对齐声明 → 总差距（含 z）→ 差距结构（集中/普遍，
引 concentration_ratio）→ 机制归因（层级如实）→ 建议（换模/组合/维持，引
oracle-gap）→ Provenance 块。
特有反驳门（写结论前逐条自问并记录）：
- **对齐偏置门**：dropped 不对称吗？只在对齐子集上比较的结论声明了子集吗？
- **口径反转门**：horizon 交叉点存在吗？换口径（子段）后排名保持吗？
- **切片挑拣门**：结论引用的片段是事先声明的（最差片规则）还是事后挑的？
- **同质化门**：模型间误差相关 >0.95 时，「A 略好」的差距有实际意义吗
  （与 sign_z 联判）？

## 7. 材料降级说明

- predict / truth 缺（absent-confirmed）：本 playbook 不可做——没有降级路径，
  向用户说明后终止；
- model_code 缺：Stage 3 锁死（变体不解锁），结论上限=「假设」，机制归因缺席
  要在 CONCLUSION 显式声明；
- features 缺：D 组三图跳过，输入侧归因缺席（现象清单注明）；
- train_y 缺：train-test-drift 跳过，「世界变了」类候选只能靠
  y-vs-feature-mapping 的期内 split 弱替代；
- training_log / experiment_config 缺：不影响本 playbook 主线（它们只服务
  Stage 3 的旁证），缺席仅记录。
```

- [ ] **Step 1: 创建 playbook.md（frontmatter+正文逐字落盘）**

- [ ] **Step 2: 验证 frontmatter 可加载 + 引擎全绿**

Run: `python3 -c "import sys; sys.path.insert(0,'ts-diagnose/scripts'); import engine_common as ec; fm=ec.load_frontmatter('ts-diagnose/playbooks/model-comparison/playbook.md'); print(fm['id'], len(fm['stages']), [s.get('charts') and len(s['charts']) for s in fm['stages']])"`
Expected: `model-comparison 5 [None, None, 13, None, None]`
Run: `python3 -m pytest ts-diagnose/ -q`
Expected: 全绿（PLAYBOOK_IDS 未含新 id，零回归；orient --playbook 路径式冒烟可选：`python3 ts-diagnose/scripts/orient.py --playbook ts-diagnose/playbooks/model-comparison` 在临时目录跑通不报错）。

- [ ] **Step 3: Commit**

```bash
git add ts-diagnose/playbooks/model-comparison/
git commit -m "feat(ts-diagnose): model-comparison playbook——五阶段多模型对比归因（charts 声明 13 图+对齐/口径反驳门）"
```

---

### Task 8: model-comparison golden + reference + gen_gate 登记

**Files:**
- Create: `ts-diagnose/playbooks/model-comparison/golden/make_golden.py`
- Create: `ts-diagnose/playbooks/model-comparison/golden/predictions.csv`（由 make_golden 生成后随仓提交）
- Create: `ts-diagnose/playbooks/model-comparison/golden/manifest.json`
- Create: `ts-diagnose/playbooks/model-comparison/golden/reference/stage1_gap.py`
- Create: `ts-diagnose/playbooks/model-comparison/golden/reference/stage2_slice.py`
- Modify: `ts-diagnose/scripts/tests/test_gen_gate.py`（REFS 加两行）

**Interfaces:**
- Consumes: gen_gate manifest 契约（Global Constraints）；chartbook `chart_worst_slice_compare.compute`（stage2 wrapper 经 sys.path import，**不用 subprocess**——static_check 禁）
- Produces: 植入结构（manifest.planted 记录）：模型 A 幅度 0.8（2024-01/03）、2.5（2024-02）；B 恒 1.5 ⇒ A 总体更好（1.3667 vs 1.5）但最差片 2024-02 上 B 反超；gap 全部集中该片（concentration_ratio=1.0）

**make_golden.py（逐字；决定论、csv 输出、零随机）**：

```python
"""model-comparison 金标准：解析式构造双模型规范长表。

植入：A 在 2024-02 崩（幅度 2.5），其余月 0.8；B 恒 1.5。
⇒ A 总体行 RMSE 均值 (0.8*8+2.5*4)/12 = 1.3667 < B 1.5（A 总体更好）；
  A 的最差片 = 2024-02，片内 B（1.5）反超 A（2.5）；
  slice_gaps 仅 2024-02 为正（+1.0）⇒ concentration_ratio = 1.0。
配对差 d=A−B：8 行 −0.7、4 行 +1.0 ⇒ mean_diff=−0.1333、win_rate=8/12、
sign_z=(8−6)/sqrt(3)=1.1547。符号交替（step 奇偶）保证行 RMSE 恰等于幅度。
"""
import csv
import os

MONTHS = {"2024-01": 0.8, "2024-02": 2.5, "2024-03": 0.8}
B_AMP = 1.5
DAYS = (5, 10, 15, 20)
STEPS = 8


def amp(model, month):
    return MONTHS[month] if model == "A" else B_AMP


def main():
    out = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                       "predictions.csv")
    with open(out, "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["window_ts", "unit_id", "model", "horizon_step",
                    "y_true", "y_pred"])
        for month in MONTHS:
            for d in DAYS:
                for model in ("A", "B"):
                    for s in range(STEPS):
                        e = amp(model, month) * (1.0 if s % 2 == 0 else -1.0)
                        w.writerow([f"{month}-{d:02d}", "U1", model, s,
                                    10.0, 10.0 + e])
    print(f"wrote {out}")


if __name__ == "__main__":
    main()
```

注意：4 天×3 月 = 每模型 12 行；A 均值 = (0.8×8 + 2.5×4)/12 = 1.3667。

**reference/stage1_gap.py（逐字）**：

```python
"""Stage 1 参考实现：总差距事实。CLI 契约即菜谱契约（gen_gate 钉死）。"""
import argparse
import json
import math

import numpy as np
import pandas as pd


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--pred", required=True)
    ap.add_argument("--pair", required=True)      # 如 A,B
    ap.add_argument("--out", required=True)
    a = ap.parse_args()
    df = pd.read_csv(a.pred)
    df["err"] = df["y_pred"] - df["y_true"]
    rr = (df.groupby(["model", "unit_id", "window_ts"])["err"]
          .apply(lambda e: float(np.sqrt(np.mean(np.square(e)))))
          .rename("rmse").reset_index())
    per_model = rr.groupby("model")["rmse"].mean()
    focal, other = a.pair.split(",")
    piv = rr.pivot_table(index=["unit_id", "window_ts"], columns="model",
                         values="rmse").dropna()
    d = (piv[focal] - piv[other]).to_numpy()
    n = len(d)
    wins = int((d < 0).sum())
    z = (wins - n / 2) / math.sqrt(n / 4)
    p = 2 * (1 - 0.5 * (1 + math.erf(abs(z) / math.sqrt(2))))
    json.dump({
        "caliber": "rmse_192",
        "per_model": {m: round(float(v), 4) for m, v in per_model.items()},
        "ranking": list(per_model.sort_values().index),
        "pair": [focal, other], "n": n,
        "mean_diff": round(float(d.mean()), 4),
        "win_rate": round(wins / n, 4),
        "sign_z": round(float(z), 4), "sign_p": round(float(p), 4),
        "note": "|z|<2 → 差距未过噪声线，只写现象不写方向",
    }, open(a.out, "w"), ensure_ascii=False, indent=2)


if __name__ == "__main__":
    main()
```

**reference/stage2_slice.py（逐字；import chartbook，禁 subprocess）**：

```python
"""Stage 2 参考实现（切片证据线）：直接复用 chartbook 预写 worst-slice-compare
的 compute——参考实现与产线同源，钉住「Stage 2 不现场写图代码」的契约。"""
import argparse
import json
import os
import sys

import pandas as pd

_ENGINE = os.path.abspath(os.path.join(
    os.path.dirname(os.path.abspath(__file__)), "..", "..", "..", ".."))
sys.path.insert(0, os.path.join(_ENGINE, "chartbook", "scripts"))

import chart_common as cc                    # noqa: E402
import chart_worst_slice_compare as cwsc     # noqa: E402


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--pred", required=True)
    ap.add_argument("--focal", required=True)
    ap.add_argument("--out", required=True)
    a = ap.parse_args()
    stats = cwsc.compute(cc.load_predictions(a.pred), focal_model=a.focal)
    json.dump(stats, open(a.out, "w"), ensure_ascii=False, indent=2)


if __name__ == "__main__":
    main()
```

（路径推导：reference/ 在 playbooks/model-comparison/golden/reference/，上溯四级
= ts-diagnose 根。gen_gate 以脚本原始绝对路径执行、cwd=沙箱，`__file__` 可用。）

**manifest.json（逐字）**：

```json
{
  "playbook": "model-comparison",
  "note": "金标准由 make_golden.py 确定性生成（零随机）；期望值来自 reference/ 实跑留容差。Stage 0 依赖真实数据格式（适配器+对账验证步兜底）；Stage 2 的图脚本本体由 chartbook 自带 golden 闸住，此处钉的是切片证据线契约。改期望先改 make_golden.py 并重跑 pytest。",
  "planted": {
    "overall_better": "A",
    "a_worst_slice": "2024-02",
    "slice_winner_in_worst": "B",
    "gap_concentration": 1.0
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
      "desc": "切片证据线：A 最差片 2024-02、片内 B 反超、gap 全集中",
      "inputs": ["predictions.csv"],
      "args": ["--pred", "predictions.csv", "--focal", "A", "--out", "worst-slice-compare.json"],
      "expect": [
        {"file": "worst-slice-compare.json", "path": "worst_slice", "op": "eq", "value": "2024-02"},
        {"file": "worst-slice-compare.json", "path": "in_slice.A", "op": "between", "value": [2.49, 2.51]},
        {"file": "worst-slice-compare.json", "path": "in_slice.B", "op": "between", "value": [1.49, 1.51]},
        {"file": "worst-slice-compare.json", "path": "concentration_ratio", "op": "eq", "value": 1.0}
      ]
    }
  }
}
```

**test_gen_gate.py REFS 追加两行**（元组内、既有条目之后）：

```python
    ("model-comparison", "1", "reference/stage1_gap.py"),
    ("model-comparison", "2", "reference/stage2_slice.py"),
```

- [ ] **Step 1: 写 make_golden.py 并生成 predictions.csv**

Run: `python3 ts-diagnose/playbooks/model-comparison/golden/make_golden.py`
Expected: `wrote .../predictions.csv`（192 数据行 + 表头）

- [ ] **Step 2: 写两个 reference + manifest；先手跑确认期望值**

Run（临时目录里拷 predictions.csv 后）:
`python3 .../reference/stage1_gap.py --pred predictions.csv --pair A,B --out gap_summary.json && python3 -c "import json;print(json.load(open('gap_summary.json')))"`
Expected: per_model.A≈1.3667、mean_diff≈−0.1333、win_rate≈0.6667、sign_z≈1.1547——若与 manifest 期望不符，**先改 make_golden 或期望并重跑**，不许放宽容差蒙混。

- [ ] **Step 3: REFS 登记 + 跑闸**

Run: `python3 -m pytest ts-diagnose/scripts/tests/test_gen_gate.py -q && python3 -m pytest ts-diagnose/ -q`
Expected: 全绿（新 REFS 两项 PASS）。

- [ ] **Step 4: Commit**

```bash
git add ts-diagnose/playbooks/model-comparison/golden/ ts-diagnose/scripts/tests/test_gen_gate.py
git commit -m "feat(ts-diagnose): model-comparison golden——植入 A 总体优/B 片内反超结构，Stage1/2 过 gen_gate 闸"
```

---

### Task 9: fact-scan 薄 playbook + golden

**Files:**
- Create: `ts-diagnose/playbooks/fact-scan/playbook.md`
- Create: `ts-diagnose/playbooks/fact-scan/golden/make_golden.py`
- Create: `ts-diagnose/playbooks/fact-scan/golden/predictions.csv`
- Create: `ts-diagnose/playbooks/fact-scan/golden/manifest.json`
- Create: `ts-diagnose/playbooks/fact-scan/golden/reference/scan_charts.py`
- Modify: `ts-diagnose/scripts/tests/test_gen_gate.py`（REFS 加一行）

**frontmatter（逐字）**：

```yaml
---
id: fact-scan
name: 图谱体检（只看现象不下结论）
goal: 把手头材料能画的标准分析图一次画全，产出现象清单——终点即停顿，不进任何归因
stages:
  - id: 0
    name: 口径与对齐
    done_when:
      artifacts: ["alignment_report.json"]
    prereqs:
      - desc: 步长/口径已确认
        check: "question:scan-caliber"
  - id: 1
    name: 画图与现象清单（终点）
    done_when:
      artifacts: ["charts/*.json"]
      findings_marker: "现象"
    prereqs:
      - desc: 对齐完成
        check: "stage:0"
    pause_after: true
    charts: [error-breakdown, intraday-profile, worst-points,
             horizon-degradation, rolling-stability, true-vs-pred-scatter,
             model-error-correlation, worst-slice-compare, oracle-gap,
             feature-error-conditional, feature-trend-overlay,
             y-vs-feature-mapping, train-test-drift]
materials:
  required: [predict, truth]
  optional: [features, train_y]
questions:
  - id: scan-caliber
    stage: 0
    ask: "horizon 步长（freq）是多少？单模型还是多模型？（对比类图需 ≥2 模型）"
    why: "freq 错则 hour/tod 维度全错；模型数决定哪些图可画"
    default: null
---
```

**正文（逐字；注意：不点名任何其他 playbook id）**：

```markdown
# fact-scan：图谱体检

## 1. 问题框定与首要陷阱

用户只要"看一遍"，不要诊断。本 playbook **没有结论阶段**：产出止于现象清单，
FINDINGS.md 只许「现象」状态、禁一切机制语言（"因为/导致/说明模型…"都不许出现）。
首要陷阱：把体检写成诊断——发现的形态只登记，归因走别的 playbook（用户想深挖时
回路由层重新选择；本清单与图 JSON 全部可复用，materials 盘点结果同样复用）。

## 2. 逐阶段菜谱

### Stage 0 口径与对齐
同标准 intake：薄适配器 → 规范长表 → 对账两关（样例
chartbook/golden/example_adapter/）→ `alignment_report.json`
（schema：`{"models":[...], "n_rows":int, "freq":str}`）。单模型数据合法
（对比类图会自动因 <2 模型不可画，跳过即可，不算失败）。

### Stage 1 画图与现象清单（终点）
orient 已按材料/模型数标好可画集；逐图跑 chartbook 预写脚本（命令模板同
chartbook 各 recipe 的 CLI 节），产物进 `charts/`。对比类图在单模型数据上会
抛 ValueError——捕获后在清单记「因模型数 <2 未画」，不算失败。
判读各图 JSON 描述符 → FINDINGS.md 现象清单（每条：图 id + 描述符数字 + 一句
现象陈述，禁机制词）。跳过的图逐条注明原因（缺材料/模型数）。
done：charts/*.json ≥1 + FINDINGS.md 含「现象」→ 停顿汇报，**流程终点**。

## 3. 证据升级规则

无。本 playbook 不升级——现象即产出上限（这正是它与诊断类 playbook 的边界）。

## 4. 停顿点与汇报

终点停顿：向用户交付 ①已画/跳过清单（含原因）②按图分组的现象清单 ③提示
"想深挖哪条现象，请回到技能入口重新描述目标"（材料盘点与图产物自动复用）。

## 5. subagent 拆分建议

各图独立可并发（每图一子代理，互不同输出文件）；FINDINGS 汇总主 agent 做。

## 6. 结论模板与反驳门

不适用（无结论阶段）。唯一自查：FINDINGS.md 里出现机制语言 = 越界，删改后再交付。

## 7. 材料降级说明

predict/truth 缺 → 不可做；features 缺 → 输入关联三图跳过；train_y 缺 → 漂移图
跳过。跳过永远注明、永远不算失败——体检报告如实写"未查项"。
```

**golden/**（精简版，与 model-comparison 各自独立——思路可同、代码零共享）：

make_golden.py（逐字）：

```python
"""fact-scan 金标准：双模型 mini 长表。A 在 2024-02 崩（幅度 2.0，其余 1.0），
B 恒 1.5 ⇒ error-breakdown argmax=(U1,2024-02)、oracle 均值 = (1.0×4+1.5×4)/8。"""
import csv
import os

AMP = {"A": {"2024-01": 1.0, "2024-02": 2.0}, "B": {"2024-01": 1.5, "2024-02": 1.5}}


def main():
    out = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                       "predictions.csv")
    with open(out, "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["window_ts", "unit_id", "model", "horizon_step",
                    "y_true", "y_pred"])
        for month in ("2024-01", "2024-02"):
            for d in (5, 10, 15, 20):
                for model in ("A", "B"):
                    for s in range(4):
                        e = AMP[model][month] * (1.0 if s % 2 == 0 else -1.0)
                        w.writerow([f"{month}-{d:02d}", "U1", model, s,
                                    10.0, 10.0 + e])
    print(f"wrote {out}")


if __name__ == "__main__":
    main()
```

reference/scan_charts.py（逐字；同 stage2_slice 的 import 模式）：

```python
"""Stage 1 参考实现：跑通两张代表图（分解类+对比类），钉住「体检=复用 chartbook
预写脚本」契约。"""
import argparse
import json
import os
import sys

_ENGINE = os.path.abspath(os.path.join(
    os.path.dirname(os.path.abspath(__file__)), "..", "..", "..", ".."))
sys.path.insert(0, os.path.join(_ENGINE, "chartbook", "scripts"))

import chart_common as cc              # noqa: E402
import chart_error_breakdown as ceb    # noqa: E402
import chart_oracle_gap as cog         # noqa: E402


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--pred", required=True)
    ap.add_argument("--out-eb", required=True)
    ap.add_argument("--out-og", required=True)
    a = ap.parse_args()
    df = cc.load_predictions(a.pred)
    json.dump(ceb.compute(df), open(a.out_eb, "w"), ensure_ascii=False)
    json.dump(cog.compute(df), open(a.out_og, "w"), ensure_ascii=False)


if __name__ == "__main__":
    main()
```

manifest.json（逐字）：

```json
{
  "playbook": "fact-scan",
  "note": "精简金标准：体检=复用 chartbook 预写脚本，此处钉两张代表图（分解类+对比类）的关键数字；各图本体由 chartbook 自带 golden 闸住。改期望先改 make_golden.py。",
  "planted": {"a_bad_month": "2024-02", "oracle_mean": 1.25},
  "stages": {
    "1": {
      "desc": "代表图关键数字：A 的 argmax 单元格与 oracle 均值",
      "inputs": ["predictions.csv"],
      "args": ["--pred", "predictions.csv", "--out-eb", "error-breakdown.json", "--out-og", "oracle-gap.json"],
      "expect": [
        {"file": "error-breakdown.json", "path": "models.A.argmax_cell.month", "op": "eq", "value": "2024-02"},
        {"file": "error-breakdown.json", "path": "models.A.argmax_cell.rmse", "op": "between", "value": [1.99, 2.01]},
        {"file": "oracle-gap.json", "path": "mean_rmse.oracle", "op": "between", "value": [1.24, 1.26]},
        {"file": "oracle-gap.json", "path": "oracle_pick_share.A", "op": "between", "value": [0.45, 0.55]}
      ]
    }
  }
}
```

（oracle 逐行取 min(A,B)：1 月 min(1.0,1.5)=1.0 ×4 行、2 月 min(2.0,1.5)=1.5 ×4 行
⇒ 均值 1.25；pick 1 月全 A、2 月全 B ⇒ share 各 0.5。）

REFS 追加一行：`("fact-scan", "1", "reference/scan_charts.py"),`

- [ ] **Step 1: playbook.md 落盘 + frontmatter 冒烟**

Run: `python3 -c "import sys; sys.path.insert(0,'ts-diagnose/scripts'); import engine_common as ec; fm=ec.load_frontmatter('ts-diagnose/playbooks/fact-scan/playbook.md'); print(fm['id'], len(fm['stages']))"`
Expected: `fact-scan 2`

- [ ] **Step 2: golden 三件 + 生成数据 + 手跑 reference 验数**

Run: `python3 ts-diagnose/playbooks/fact-scan/golden/make_golden.py`，临时目录手跑 scan_charts 验 oracle 均值 1.25 / argmax 2024-02。

- [ ] **Step 3: REFS 登记 + 跑闸 + 引擎全绿**

Run: `python3 -m pytest ts-diagnose/scripts/tests/test_gen_gate.py -q && python3 -m pytest ts-diagnose/ -q`
Expected: 全绿。

- [ ] **Step 4: Commit**

```bash
git add ts-diagnose/playbooks/fact-scan/ ts-diagnose/scripts/tests/test_gen_gate.py
git commit -m "feat(ts-diagnose): fact-scan 薄 playbook——图谱体检终点停顿+精简 golden 过闸"
```

---

### Task 10: 路由收口——SKILL 两行 + description、pv-result-analysis 让路句、守卫扩表、CHANGELOG

**Files:**
- Modify: `ts-diagnose/SKILL.md`
- Modify: `pv-result-analysis/SKILL.md`（仅 frontmatter description 一句）
- Modify: `ts-diagnose/scripts/tests/test_layering.py`（PLAYBOOK_IDS 扩 5）
- Modify: `ts-diagnose/scripts/tests/test_routing.py`（触发短语钉子——先读文件、照既有条目风格加）
- Modify: `ts-diagnose/CHANGELOG.md`

**改动内容**：

1. `ts-diagnose/SKILL.md` 路由表加两行（逐字）：

```markdown
| 为什么模型 A 比 B 好/差、多模型对比归因（非光伏标准评估场景：格式不标准/每模型一个文件/任意模型集合/非光伏时序） | `model-comparison` |
| 只想体检/把标准分析图画一遍/看现象不要结论 | `fact-scan` |
```

2. `ts-diagnose/SKILL.md` description 里"当用户对时序/预测任务提出**新的诊断目标**时使用"的列举串里补两个触发语（在 feature-importance 触发语之后）：`、"为什么模型 A 比 B 好/多模型对比归因（非光伏标准评估场景）"（model-comparison）、"只想把标准分析图画一遍看现象、不要结论"（fact-scan）`。
   **硬约束**：改完 SKILL.md 必须 ≤60 行、无 METHOD_VOCAB 禁词（行文别用"Stage/阶段声明"等词——上面两行措辞已规避）；`python3 -m pytest ts-diagnose/scripts/tests/test_layering.py -q` 立即验证。

3. `pv-result-analysis/SKILL.md` frontmatter description 末尾追加一句（逐字，只动这一处）：`非标准格式/每模型一个文件/任意模型集合的模型对比归因 → 用 ts-diagnose 的 model-comparison。`

4. `test_layering.py`：`PLAYBOOK_IDS = ("training-sufficiency", "robustness", "feature-importance", "model-comparison", "fact-scan")`。若 `test_layer1_playbooks_independent` 因新 playbook 正文出现旧 id 而红——那是正文违规，改正文不改测试。

5. `test_routing.py`：先读文件；按既有钉子风格为两个新 playbook 各加触发短语存在性断言（如"模型对比归因"、"体检"、"不要结论"出现在 ts-diagnose SKILL.md）；若文件有 SKILLS 元组/负面清单结构，把 pv-result-analysis 的新让路句纳入既有断言风格。

6. `CHANGELOG.md` 底部追加一行（格式同文件既有行）：

```
- 2026-07-22 | v2 Plan 3 收口：D 组 3 图（feature-error-conditional/feature-trend-overlay/y-vs-feature-mapping）+E 组 train-test-drift、playbook 阶段级 charts 声明（orient 逐图可画性）、model-comparison 五阶段 playbook+fact-scan 体检 playbook（各带 golden 过 gen_gate）、路由表加两行+pv-result-analysis 反向让路 | 用户："用户进站直接跑 /ts-diagnose…比如用户想问模型A为什么比模型B要好" | 完成"盘点材料→自动画图→对比归因"闭环；体检与诊断分离（fact-scan 无结论阶段）
```

- [ ] **Step 1: 依次落六处改动**
- [ ] **Step 2: 跑守卫**

Run: `python3 -m pytest ts-diagnose/scripts/tests/test_layering.py ts-diagnose/scripts/tests/test_routing.py -q`
Expected: 全绿（SKILL 预算/禁词/五 playbook 互不引用/路由钉子全过）。

- [ ] **Step 3: 全仓回归**

Run: `python3 -m pytest ts-diagnose/ -q && python3 -m pytest . -q`（后者约 100 秒）
Expected: 引擎全绿；全仓 230+ 全绿。

- [ ] **Step 4: Commit**

```bash
git add ts-diagnose/SKILL.md ts-diagnose/CHANGELOG.md ts-diagnose/scripts/tests/ pv-result-analysis/SKILL.md
git commit -m "feat(ts-diagnose): 路由收口——model-comparison/fact-scan 进路由表与 description，pv-result-analysis 反向让路，layering/routing 守卫扩五 playbook"
```

---

## 计划边界（本计划不做）

- orient 自动"执行"图脚本（只报可画性；执行由主 agent 按菜谱做）；
- 训练期 feature 材料定义与 feature 漂移（train-test-drift v1 只做标签）；
- pv-model-analysis 事实提取增强（用户预告的后续轮）；
- 实验线 v0→v1 迁移（占位不变）。
