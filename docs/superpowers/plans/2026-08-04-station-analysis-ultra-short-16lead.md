# Ultra-Short 16-Lead Analysis + Short-Script Arg Restore — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Restore `--date`/`--pred-col-template` on `station_analysis_short.py` (green suite), and build `station_analysis_ultra_short.py` that reconstructs 16 constant-lead prediction lines per station for one day from per-起报 parquets.

**Architecture:** Two self-contained scripts. Short script keeps its unconditional report-day + D+1/D+4 + history flow; only CLI args and one counterfactual guard change. Ultra-short is a new file: loaders build a per-station 96×16 lead matrix (predict side) and a 96-row truth frame (input side, `list[0]` sampling), then minimal metrics + 17-line/2-line plots.

**Tech Stack:** Python, pandas / numpy / pyarrow / matplotlib only (no other deps). pytest via subprocess + importlib module-import (existing pattern).

**Spec:** `docs/superpowers/specs/2026-08-04-station-analysis-ultra-short-16lead-design.md`

## Global Constraints

- Both scripts stay copy-anywhere self-contained: stdlib + pandas/numpy/pyarrow/matplotlib only; NEVER import one script from the other — copy helpers (`sanitize`, `night_mask`, `_cn_font`, `_station_dir`, `rmse`).
- Matplotlib: `matplotlib.use("Agg")` inside each plot function before pyplot import; call `_cn_font()`.
- Doc/comment style: every sentence is an instruction or a fact needed to run; no design rationale essays (user rule).
- All pytest commands run from `短期分析/`: `python3 -m pytest <file> -q`.
- Lead labeling (fixed vocabulary): for target t, 起报 S = t − k·15min contributes at lead k; line label `p{17−k}`. So **p1 = lead 16 = 4h-ahead (oldest), p16 = lead 1 = 15min-ahead (newest)**.
- Ultra-short target grid: `D 00:00 … 23:45` (96 points); required 起报: predict side `D−1 20:00 … D 23:30` (111), input side `D−1 23:45` + `D 00:00 … 23:30` (96).
- Missing 起报 file/dir → warn + NaN gap, never abort. >1 glob match for one 起报 → `SystemExit`.

---

### Task 1: Short script — restore `--date` + `--pred-col-template`, reconcile test suite

The committed script dropped `--short`/`--date`/`--pred-col-template` and made D+1/D+4 unconditional; the suite is red. Migrate tests to the no-flag reality (all core fixtures sit on 2026-07-16, so `--date 2026-07-15` puts them inside the D+1 window), and restore the two args.

**Files:**
- Modify: `短期分析/station_analysis_short.py` (`resolve_pred_col` ~line 129, `compute_windows` ~line 1166, `main` argparse ~line 1177, warn text ~line 942)
- Modify: `短期分析/test_station_analysis_short.py` (`_run` line 28, `_run_short` line 453, `test_no_station_plots_keeps_csv` line 258, delete `test_default_no_short_folders` line 497, `test_short_counterfactual_per_window` line 549)

**Interfaces:**
- Produces: `resolve_pred_col(st, pred, template) -> str | None` (template has `{station}` placeholder); `compute_windows(inp, win_col, date_arg) -> (report_name: str, [(label, start, end), ...])`; CLI args `--date` (default None), `--pred-col-template` (default `"predict_power_{station}"`). Task 2 relies on these exact signatures.

- [ ] **Step 1: Update the test helpers and mode-dependent tests**

Replace `_run` (line 28) — fixtures' data lands in the `--date 2026-07-15` D+1 window, CSVs read from the report dir:

```python
def _run(wd, extra=()):
    r = subprocess.run(
        [sys.executable, SCRIPT, "--input", str(wd / "input.parquet"),
         "--predict", str(wd / "predict.parquet"), "--out-dir", str(wd / "out"),
         "--date", "2026-07-15", "--pred-col-template", "{station}"] + list(extra),
        cwd=str(wd), capture_output=True, text=True)
    assert r.returncode == 0, r.stdout + r.stderr

    def load(name):
        p = wd / "out" / "20260715" / "D+1" / name
        return pd.read_csv(p) if os.path.exists(p) else None
    return {"power": load("station_power_rmse.csv"), "feat": load("station_feature_rmse.csv"),
            "fleet": load("fleet_ranking.csv"), "cf": load("counterfactual_results.csv"),
            "out": r.stdout}
```

In `_run_short` (line 453): delete the `"--short"` list element (leave everything else).

Replace `test_no_station_plots_keeps_csv` (line 258) — the old flat-dir listdir check is vacuous now:

```python
def test_no_station_plots_keeps_csv(data, tmp_path):
    """--no-station-plots：不出逐站图，但站级 CSV 与总览仍在。"""
    r = _run(data, ["--no-station-plots"])
    assert r["power"] is not None
    pngs = [f for _, _, fs in os.walk(data / "out") for f in fs if f.endswith("_Power.png")]
    assert pngs == []
```

Delete `test_default_no_short_folders` (lines 497–505) entirely — there is no plain mode.

In `test_short_counterfactual_per_window` (line 549): delete the `"--short"` element from the subprocess arg list.

- [ ] **Step 2: Run suite, verify the expected failure set**

Run: `python3 -m pytest test_station_analysis_short.py -q`
Expected: many FAIL with `error: unrecognized arguments: --date --pred-col-template` (helpers now pass args the script lacks). No collection errors.

- [ ] **Step 3: Restore the args in the script**

`resolve_pred_col` (line 129):

```python
def resolve_pred_col(st, pred, template):
    """站点 -> 预测表列名 template.format(station=st)；列不存在返回 None（调用方 warn + skip）。"""
    col = template.format(station=st)
    return col if col in pred.columns else None
```

Update all three call sites to pass `args.pred_col_template`: `run_analysis` (~line 940), `run_counterfactual` stations filter (~line 786) and loop (~line 826). Update the warn text at ~line 942 to use the resolved name:

```python
        col = resolve_pred_col(st, pred, args.pred_col_template)
        if col is None:
            print(f"  [warn] station {st}: predict table has no column "
                  f"'{args.pred_col_template.format(station=st)}', skip Power plot")
```

`compute_windows` (line 1166) — add `--date` override + announce the fallback:

```python
def compute_windows(inp, win_col, date_arg):
    """起报日 D：--date 显式给定，否则取 timestamp_win 最早日期并播报；切 [D+1 00:00,+24h) 与 [D+4 00:00,+24h)。"""
    if date_arg:
        D = pd.Timestamp(date_arg).normalize()
    else:
        D = pd.Timestamp(inp[win_col].min()).normalize()
        print(f"  [short] --date not given; using D = {D:%Y-%m-%d} (from earliest {win_col})")
    day = pd.Timedelta(days=1)
    d1, d4 = D + day, D + 4 * day
    return D.strftime("%Y%m%d"), [("D+1", d1, d1 + day), ("D+4", d4, d4 + day)]
```

In `main`: add the two args next to `--station-col` and update the call site (line 1254):

```python
    ap.add_argument("--date", default=None, help="起报日 YYYY-MM-DD；缺省取 timestamp_win 最早日期并播报")
    ap.add_argument("--pred-col-template", default="predict_power_{station}",
                    help='预测表列名模板，{station} 占位，如 "{station}" 或 "predict_power_{station}"')
```

```python
    report_name, windows = compute_windows(inp, args.win_col, args.date)
```

- [ ] **Step 4: Run suite, verify only the CF-hits tests still fail**

Run: `python3 -m pytest test_station_analysis_short.py -q`
Expected: PASS for everything except exactly these 5 (they assert API hit counts; the empty D+4 window currently still burns 2 calls/station — fixed in Task 2):
`test_cf_decomposition`, `test_cf_resume_skips_done`, `test_cf_worst_selects_worst`, `test_cf_worst_ignored_when_stations_given`, `test_cf_worst_no_fleet_falls_back`.
If anything else fails, stop and fix before proceeding.

- [ ] **Step 5: Commit**

```bash
git add 短期分析/station_analysis_short.py 短期分析/test_station_analysis_short.py
git commit -m "feat(station_analysis_short): restore --date/--pred-col-template; migrate tests to windowed reality"
```

---

### Task 2: Counterfactual window guard — no API calls when the window has no truth

A window whose truth series has zero points (e.g. fixtures whose data only covers D+1) must not spend 2 API calls per station before discovering `no_overlap`. Guard before the first call. This turns the 5 remaining test failures green with their original hit counts.

**Files:**
- Modify: `短期分析/station_analysis_short.py` (`run_counterfactual` per-station loop, ~lines 825–850)
- Test: `短期分析/test_station_analysis_short.py` (existing tests only)

**Interfaces:**
- Consumes: `resolve_pred_col(st, pred, template)`, `window_mask(idx, win)`, `series_from_lists(wins, lists, step)` — all already in the file.
- Produces: behavior only — station rows with no truth in `win` get `status=no_overlap` with zero HTTP.

- [ ] **Step 1: Confirm the 5 failing tests fail for the predicted reason**

Run: `python3 -m pytest test_station_analysis_short.py -q -k "cf_decomposition or cf_resume or cf_worst"`
Expected: FAIL on hit-count asserts (e.g. `assert fake_api.hits == 4` seeing 8) — the D+4 pass doubles calls.

- [ ] **Step 2: Move truth computation up and add the guard**

In `run_counterfactual`'s loop, currently:

```python
    for st in todo:
        col = resolve_pred_col(st, pred, args.pred_col_template)   # non-None: the station list was filtered above
        sub = inp[inp[args.station_col] == st].sort_values(args.win_col)
        pq = pred[col].dropna()
        dtimes = pq.index.sort_values()
        try:
```

insert the truth block right after `sub = ...` and delete the later duplicate (`truth = series_from_lists(...)` two lines, currently after the except block ~line 849):

```python
    for st in todo:
        col = resolve_pred_col(st, pred, args.pred_col_template)   # non-None: the station list was filtered above
        sub = inp[inp[args.station_col] == st].sort_values(args.win_col)
        truth = series_from_lists(sub[args.win_col].to_numpy(),
                                  sub[args.power_col].to_numpy(), step)
        if win is not None and not window_mask(truth.index, win).any():
            print(f"  [warn] station {st}: truth has no points in this window -> counterfactual skipped (0 API calls)")
            _cf_append(csv_path, {"station": st, "status": "no_overlap"})
            continue
        pq = pred[col].dropna()
        dtimes = pq.index.sort_values()
        try:
```

- [ ] **Step 3: Run the full suite, verify all green**

Run: `python3 -m pytest test_station_analysis_short.py -q`
Expected: ALL PASS. Sanity-check the guard didn't break the real-window path: `test_short_counterfactual_per_window` (480-pt lists, both windows populated, hits == 4) must still pass.

- [ ] **Step 4: Commit**

```bash
git add 短期分析/station_analysis_short.py
git commit -m "fix(counterfactual): skip API calls for windows with no truth points"
```

---

### Task 3: Ultra-short loaders (`station_analysis_ultra_short.py` core) + unit tests

New self-contained script: time helpers, glob resolution, predict lead-matrix loader, input truth loader. Unit-tested by module import (same importlib pattern the short tests use).

**Files:**
- Create: `短期分析/station_analysis_ultra_short.py`
- Create: `短期分析/test_station_analysis_ultra_short.py`

**Interfaces (Task 4 builds on these exact signatures):**
- `STEP = pd.Timedelta(minutes=15)`, `N_LEADS = 16`
- `target_grid(D) -> pd.DatetimeIndex` — 96 pts, `D 00:00 … 23:45`
- `issue_times(D) -> list[pd.Timestamp]` — 111 pts, `D−1 20:00 … D 23:30`
- `find_parquet(dirpath, token) -> str | None` — glob `*{token}*.parquet`; >1 → SystemExit
- `stations_from_columns(cols, template, skip=("dtime",)) -> list[str]`
- `load_predict_matrix(predict_dir, D, stations, template, dtime_col="dtime") -> (dict[str, pd.DataFrame], int)` — per station a `96×["p1".."p16"]` float frame; int = missing-file count
- `load_truth(input_dir, D, station_col="station") -> (dict[str, pd.DataFrame], int)` — per station a `96×["power_true","ghi_true","ghi_pred"]` frame; int = missing-dir count
- Copied helpers: `sanitize`, `night_mask`, `_cn_font`, `_station_dir`, `rmse` (same bodies as the short script)

- [ ] **Step 1: Write the failing unit tests**

Create `短期分析/test_station_analysis_ultra_short.py`:

```python
"""station_analysis_ultra_short.py 单测。
数据模型：真值 v(t) = 自 D 00:00 起的 15min 槽序号；起报 S、lead k 的预测 = v(S+k*step) + scale*k。
→ p16 线 = v+scale、p1 线 = v+16*scale；合并 RMSE = scale*sqrt(mean(k², k=1..16)) = scale*sqrt(93.5)。
GHI：真值 2v、lead-1 预测 2v+5 → RMSE 5。文件名带拼写漂移（gunagxi/porvince）以测 token glob。"""
import math
import os
import shutil
import subprocess
import sys

import numpy as np
import pandas as pd
import pytest

HERE = os.path.dirname(os.path.abspath(__file__))
SCRIPT = os.path.join(HERE, "station_analysis_ultra_short.py")

import importlib.util
_spec = importlib.util.spec_from_file_location("us", SCRIPT)
us = importlib.util.module_from_spec(_spec); _spec.loader.exec_module(us)

D = pd.Timestamp("2026-07-23")
STEP = pd.Timedelta(minutes=15)


def _slot(t):                                  # 15-min slots since D 00:00
    return (t - D).total_seconds() / 900.0


@pytest.fixture
def us_data(tmp_path):
    scale = {"s1": 1.0, "s2": 2.0}
    pdir = tmp_path / "predict"; pdir.mkdir()
    for S in [D - 16 * STEP + k * STEP for k in range(111)]:
        dt = [S + STEP * (k + 1) for k in range(20)]          # 20 rows, script keeps first 16
        df = pd.DataFrame({"dtime": dt})
        for st, sc in scale.items():
            df[f"predict_power_{st}"] = [_slot(t) + sc * (i + 1) for i, t in enumerate(dt)]
        df.to_parquet(pdir / f"hw_nuoya_{S:%Y%m%d%H%M}_ultra_short_province_gunagxi_solar.parquet")
    idir = tmp_path / "input"
    for t in pd.date_range(D, D + pd.Timedelta(days=1) - STEP, freq="15min"):
        S = t - STEP
        d = idir / f"date={S:%Y-%m-%d}" / f"time={S:%H:%M}"; d.mkdir(parents=True)
        rows = [{"station": st,
                 "observe_power_future": [_slot(t), 999.0],   # only list[0] must be read
                 "GHI_real_future": [2 * _slot(t), 999.0],
                 "GHI_SOLARGIS_predict": [2 * _slot(t) + 5.0, 999.0]} for st in scale]
        pd.DataFrame(rows).to_parquet(
            d / f"hw_nuoya_ds_{S:%Y-%m-%d}_ultra_short_porvince_guangxi_solar.parquet")
    return tmp_path


def test_issue_times_and_grid():
    ts = us.issue_times(D)
    assert len(ts) == 111
    assert ts[0] == D - pd.Timedelta(hours=4)                 # D-1 20:00
    assert ts[-1] == D + pd.Timedelta(hours=23, minutes=30)
    g = us.target_grid(D)
    assert len(g) == 96 and g[0] == D and g[-1] == D + pd.Timedelta(hours=23, minutes=45)


def test_lead_mapping_full_coverage(us_data):
    mats, miss = us.load_predict_matrix(str(us_data / "predict"), D, ["s1"], "predict_power_{station}")
    assert miss == 0
    m = mats["s1"]
    assert list(m.columns) == [f"p{j}" for j in range(1, 17)]
    t = D + pd.Timedelta(hours=12)
    assert m.loc[t, "p16"] == pytest.approx(_slot(t) + 1)     # 起报 11:45, lead 1
    assert m.loc[t, "p1"] == pytest.approx(_slot(t) + 16)     # 起报 08:00, lead 16
    assert m.notna().all().all()                              # full 96x16


def test_cross_midnight_sources(us_data):
    mats, _ = us.load_predict_matrix(str(us_data / "predict"), D, ["s1"], "predict_power_{station}")
    assert mats["s1"].loc[D, "p1"] == pytest.approx(16.0)     # from D-1 20:00 起报
    truth, miss = us.load_truth(str(us_data / "input"), D)
    assert miss == 0
    assert truth["s1"].loc[D, "power_true"] == pytest.approx(0.0)   # from date=D-1/time=23:45 list[0]
    assert truth["s1"].loc[D, "ghi_pred"] == pytest.approx(5.0)


def test_find_parquet_glob_and_dup(us_data, tmp_path):
    tok = "202607231200"
    assert us.find_parquet(str(us_data / "predict"), tok) is not None   # matched despite name drift
    assert us.find_parquet(str(us_data / "predict"), "209901010000") is None
    dup = tmp_path / "dup"; dup.mkdir()
    for n in ("a_202607231200_x.parquet", "b_202607231200_y.parquet"):
        pd.DataFrame({"dtime": [D]}).to_parquet(dup / n)
    with pytest.raises(SystemExit):
        us.find_parquet(str(dup), tok)


def test_stations_from_columns():
    cols = ["dtime", "predict_power_s1", "predict_power_s2", "other"]
    assert us.stations_from_columns(cols, "predict_power_{station}") == ["s1", "s2"]
    assert us.stations_from_columns(["dtime", "s1", "s2"], "{station}") == ["s1", "s2"]


def test_missing_predict_file_gap(us_data):
    victim = us.find_parquet(str(us_data / "predict"), "202607231200")
    os.remove(victim)
    mats, miss = us.load_predict_matrix(str(us_data / "predict"), D, ["s1"], "predict_power_{station}")
    assert miss == 1
    assert int(mats["s1"].isna().sum().sum()) == 16           # 16 targets lose exactly one lead each
```

- [ ] **Step 2: Run to verify failure**

Run: `python3 -m pytest test_station_analysis_ultra_short.py -q`
Expected: collection ERROR — `station_analysis_ultra_short.py` does not exist.

- [ ] **Step 3: Create the script with the loader core**

Create `短期分析/station_analysis_ultra_short.py`:

```python
#!/usr/bin/env python3
"""PV 多站超短期预测结果分析：对指定日期 D 重建 16 条等 lead 预测线并对照真值。

数据源（两侧都按 起报时间 组织，每 15min 一个 起报）：
  --predict-dir  扁平目录，每个 起报 一个 parquet，文件名含 YYYYMMDDHHMM token；表 = dtime 列 +
                 每站一列（--pred-col-template，默认 predict_power_{station}）；行自 起报+15min 起，
                 只取前 16 点（lead 1..16 = 15min..4h）。
  --input-dir    Hive 分区 date=YYYY-MM-DD/time=HH:MM/ 下单个 parquet；行=station、列=特征
                 （schema 同短期 input，list 列，长 192）；只取每个 list 的第 0 个元素 = 起报+15min 值。

目标网格 = D 00:00..23:45 共 96 点。目标 t 的 16 个预测来自 起报 S=t-4h..t-15min；线 p_j = 恒定
lead(17-j)：p1=4h 前（最旧）、p16=15min 前（最新）。真值/GHI 取 time=(t-15min) 目录的 list[0]
（t=00:00 → date=D-1/time=23:45）。缺 起报 → 告警+NaN 缺口，不中断；同 token 多文件 → 退出。
产物：stations/ 17 线 Power 图 + 2 线 GHI 图；station_power_rmse.csv（16 lead 合并 RMSE）、
station_feature_rmse.csv（lead-1 GHI RMSE）。无散点/Theil/舰队图/反事实/history/南网。"""
from __future__ import annotations

import argparse
import glob
import os

import numpy as np
import pandas as pd

STEP = pd.Timedelta(minutes=15)
N_LEADS = 16
TRUTH_COLS = {"power_true": "observe_power_future",
              "ghi_true": "GHI_real_future",
              "ghi_pred": "GHI_SOLARGIS_predict"}


# ================================================================ shared helpers (copied from station_analysis_short.py)
def sanitize(s) -> str:
    return "".join(c if str(c).isalnum() else "_" for c in str(s))


def night_mask(idx: pd.DatetimeIndex, drop_night: bool, night_end_hour: float) -> np.ndarray:
    """True = keep. When drop_night, remove points in [00:00, night_end_hour)."""
    if not drop_night:
        return np.ones(len(idx), bool)
    hod = idx.hour + idx.minute / 60.0
    return ~(hod < night_end_hour)


def rmse(a, b):
    return float(np.sqrt(np.mean((a - b) ** 2)))


def _cn_font():
    import matplotlib
    try:
        matplotlib.rcParams["font.sans-serif"] = ["DejaVu Sans", "Arial", "Helvetica"]
        matplotlib.rcParams["axes.unicode_minus"] = False
    except Exception:
        pass


def _station_dir(out_dir):
    d = os.path.join(out_dir, "stations")
    os.makedirs(d, exist_ok=True)
    return d


# ================================================================ time grid / file resolution
def target_grid(D: pd.Timestamp) -> pd.DatetimeIndex:
    """D 00:00 .. 23:45, 96 points."""
    return pd.date_range(D, D + pd.Timedelta(days=1) - STEP, freq="15min")


def issue_times(D: pd.Timestamp) -> list:
    """预测侧所需 起报：D-1 20:00 .. D 23:30（111 个）。首 = 最早目标 00:00 的 lead-16 起报。"""
    first = D - N_LEADS * STEP
    return [first + k * STEP for k in range(N_LEADS + 96 - 1)]


def find_parquet(dirpath: str, token: str):
    """glob *token*.parquet：0 个 → None（调用方 warn+缺口）；>1 → 退出（目录被污染）。"""
    hits = sorted(glob.glob(os.path.join(dirpath, f"*{token}*.parquet")))
    if len(hits) > 1:
        raise SystemExit(f"{dirpath}: token '{token}' matches {len(hits)} parquets: {hits[:3]}")
    return hits[0] if hits else None


def stations_from_columns(cols, template: str, skip=("dtime",)) -> list:
    """按模板反解列名里的站名；template 需含 {station} 占位。"""
    pre, _, suf = template.partition("{station}")
    out = []
    for c in cols:
        c = str(c)
        if c in skip:
            continue
        if c.startswith(pre) and c.endswith(suf) and len(c) > len(pre) + len(suf):
            out.append(c[len(pre):len(c) - len(suf)] if suf else c[len(pre):])
    return out


# ================================================================ loaders
def load_predict_matrix(predict_dir: str, D: pd.Timestamp, stations: list, template: str,
                        dtime_col: str = "dtime"):
    """-> ({station: DataFrame(index=96 目标, columns=p1..p16 float)}, 缺文件数)。
    每个 起报 S 的 lead k 值放到 目标 S+k*step 的列 p{17-k}；目标不在当日网格的行忽略。"""
    grid = target_grid(D)
    labels = [f"p{j}" for j in range(1, N_LEADS + 1)]
    mats = {st: pd.DataFrame(np.nan, index=grid, columns=labels) for st in stations}
    n_missing = 0
    for S in issue_times(D):
        path = find_parquet(predict_dir, S.strftime("%Y%m%d%H%M"))
        if path is None:
            print(f"  [warn] predict 起报 {S:%Y-%m-%d %H:%M}: parquet not found -> gap")
            n_missing += 1
            continue
        df = pd.read_parquet(path)
        if dtime_col not in df.columns:
            print(f"  [warn] {os.path.basename(path)}: no '{dtime_col}' column -> skipped")
            n_missing += 1
            continue
        df = df.set_index(pd.to_datetime(df[dtime_col])).sort_index()
        df = df[~df.index.duplicated(keep="first")]
        for k in range(1, N_LEADS + 1):
            t = S + k * STEP
            if t not in grid or t not in df.index:
                continue
            lab = f"p{N_LEADS + 1 - k}"
            for st in stations:
                col = template.format(station=st)
                if col in df.columns:
                    v = df.at[t, col]
                    if pd.notna(v) and np.isfinite(float(v)):
                        mats[st].at[t, lab] = float(v)
    return mats, n_missing


def load_truth(input_dir: str, D: pd.Timestamp, station_col: str = "station"):
    """-> ({station: DataFrame(index=96 目标, columns=power_true/ghi_true/ghi_pred)}, 缺目录数)。
    目标 t 的值来自 起报 S=t-15min 目录内唯一 parquet 各 list 列的第 0 个元素。"""
    grid = target_grid(D)
    frames, n_missing = {}, 0
    for t in grid:
        S = t - STEP
        d = os.path.join(input_dir, f"date={S:%Y-%m-%d}", f"time={S:%H:%M}")
        hits = sorted(glob.glob(os.path.join(d, "*.parquet")))
        if not hits:
            print(f"  [warn] input 起报 {S:%Y-%m-%d %H:%M}: no parquet in {d} -> gap")
            n_missing += 1
            continue
        if len(hits) > 1:
            raise SystemExit(f"{d}: {len(hits)} parquets, expected exactly 1: {hits}")
        df = pd.read_parquet(hits[0])
        if station_col not in df.columns:
            print(f"  [warn] {hits[0]}: no '{station_col}' column -> skipped")
            n_missing += 1
            continue
        for _, row in df.iterrows():
            st = str(row[station_col])
            fr = frames.setdefault(st, pd.DataFrame(np.nan, index=grid, columns=list(TRUTH_COLS)))
            for out_col, src_col in TRUTH_COLS.items():
                if src_col not in df.columns:
                    continue
                cell = row[src_col]
                if cell is None or np.ndim(cell) == 0:
                    continue
                arr = np.asarray(cell, dtype=float).ravel()
                if arr.size and np.isfinite(arr[0]):
                    fr.at[t, out_col] = float(arr[0])
    return frames, n_missing
```

- [ ] **Step 4: Run the unit tests, verify they pass**

Run: `python3 -m pytest test_station_analysis_ultra_short.py -q`
Expected: all Task-3 tests PASS (no `main` yet — no e2e tests exist yet either).

- [ ] **Step 5: Commit**

```bash
git add 短期分析/station_analysis_ultra_short.py 短期分析/test_station_analysis_ultra_short.py
git commit -m "feat(ultra_short): loaders — 16-lead predict matrix + list[0] truth sampling"
```

---

### Task 4: Ultra-short metrics, plots, CLI + end-to-end tests

**Files:**
- Modify: `短期分析/station_analysis_ultra_short.py` (append below loaders)
- Modify: `短期分析/test_station_analysis_ultra_short.py` (append e2e tests)

**Interfaces:**
- Consumes: everything from Task 3 (exact signatures above).
- Produces: `pooled_rmse(truth: pd.Series, leads: pd.DataFrame, keep: np.ndarray) -> (float | None, int)`; `plot_power_17(st, truth, leads, rmse_v, n, out_dir, tick_hours) -> str`; `plot_ghi(st, ghi_true, ghi_pred, rmse_v, out_dir, tick_hours) -> str`; `main()`; CLI: `--input-dir --predict-dir --date` (all required), `--out-dir` (default `station_analysis_ultra_short_out`), `--pred-col-template`, `--station-col`, `--drop-night`, `--night-end-hour`, `--tick-hours`, `--no-plots`. Output: `<out>/<YYYYMMDD>/{stations/*.png, station_power_rmse.csv, station_feature_rmse.csv}`.

- [ ] **Step 1: Write the failing e2e tests**

Append to `短期分析/test_station_analysis_ultra_short.py`:

```python
# ---------------------------------------------------------------- e2e
def _run_us(wd, extra=()):
    r = subprocess.run(
        [sys.executable, SCRIPT, "--input-dir", str(wd / "input"),
         "--predict-dir", str(wd / "predict"), "--date", "20260723",
         "--out-dir", str(wd / "out")] + list(extra),
        cwd=str(wd), capture_output=True, text=True)
    assert r.returncode == 0, r.stdout + r.stderr
    return r


def _out(wd):
    return wd / "out" / "20260723"


def test_e2e_metrics_and_outputs(us_data):
    _run_us(us_data)
    pw = pd.read_csv(_out(us_data) / "station_power_rmse.csv")
    assert list(pw["station"]) == ["s2", "s1"]                        # sorted worst-first
    pw = pw.set_index("station")
    assert pw.loc["s1", "power_rmse"] == pytest.approx(math.sqrt(93.5), abs=1e-6)
    assert pw.loc["s2", "power_rmse"] == pytest.approx(2 * math.sqrt(93.5), abs=1e-6)
    assert set(pw["n_points"]) == {96 * 16}
    ft = pd.read_csv(_out(us_data) / "station_feature_rmse.csv").set_index("station")
    assert ft.loc["s1", "rmse"] == pytest.approx(5.0)
    assert int(ft.loc["s1", "n_points"]) == 96
    for st in ("s1", "s2"):
        assert (_out(us_data) / "stations" / f"station_{st}_Power.png").exists()
        assert (_out(us_data) / "stations" / f"station_{st}_GHI.png").exists()


def test_e2e_drop_night(us_data):
    _run_us(us_data, ["--drop-night"])                                # removes hod<5 → 20 targets
    pw = pd.read_csv(_out(us_data) / "station_power_rmse.csv").set_index("station")
    assert set(pw["n_points"]) == {76 * 16}
    assert pw.loc["s1", "power_rmse"] == pytest.approx(math.sqrt(93.5), abs=1e-6)   # per-lead常数误差不变


def test_e2e_missing_input_dir_warns_and_gaps(us_data):
    shutil.rmtree(us_data / "input" / "date=2026-07-23" / "time=12:00")
    r = _run_us(us_data)
    assert "input 起报 2026-07-23 12:00" in r.stdout
    pw = pd.read_csv(_out(us_data) / "station_power_rmse.csv").set_index("station")
    assert set(pw["n_points"]) == {96 * 16 - 16}                      # target 12:15 unscored on all 16 leads
    ft = pd.read_csv(_out(us_data) / "station_feature_rmse.csv").set_index("station")
    assert int(ft.loc["s1", "n_points"]) == 95


def test_e2e_no_plots(us_data):
    _run_us(us_data, ["--no-plots"])
    assert not (_out(us_data) / "stations").exists()
    assert (_out(us_data) / "station_power_rmse.csv").exists()
```

- [ ] **Step 2: Run to verify failure**

Run: `python3 -m pytest test_station_analysis_ultra_short.py -q`
Expected: Task-3 tests PASS; the 4 new e2e tests FAIL (script has no `main`, exits with argparse/attribute error).

- [ ] **Step 3: Append metrics, plots, and main**

Append to `短期分析/station_analysis_ultra_short.py`:

```python
# ================================================================ metrics
def pooled_rmse(truth: pd.Series, leads: pd.DataFrame, keep: np.ndarray):
    """16 lead 合并 RMSE：leads 每列减 truth，keep（夜滤）行内所有有限 (lead,目标) 对。-> (rmse|None, n)。"""
    err = leads.sub(truth, axis=0).to_numpy(float)[keep]
    err = err[np.isfinite(err)]
    if err.size == 0:
        return None, 0
    return float(np.sqrt(np.mean(err ** 2))), int(err.size)


# ================================================================ plots
def plot_power_17(st, truth: pd.Series, leads: pd.DataFrame, rmse_v, n, out_dir, tick_hours):
    """17 线：真值黑粗 + p1..p16 由浅到深（p1=4h 前最旧最浅、p16=15min 前最新最深）。"""
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.dates as mdates
    import matplotlib.pyplot as plt
    from matplotlib import cm
    _cn_font()
    fig, ax = plt.subplots(figsize=(24, 7))
    colors = cm.viridis(np.linspace(0.88, 0.10, N_LEADS))
    for j, lab in enumerate(leads.columns):
        ax.plot(leads.index, leads[lab], color=colors[j], lw=0.9, alpha=0.8,
                label=f"{lab} ({(N_LEADS - j) * 15}min ahead)")
    ax.plot(truth.index, truth, color="#000000", lw=2.2, label="observed power")
    rtxt = f"pooled RMSE={rmse_v:.3f}" if rmse_v is not None else "no scored points"
    ax.set_title(f"Station {st} - ultra-short 16-lead power   {rtxt}   (n={n} lead-target pairs)",
                 fontsize=13, fontweight="bold")
    ax.xaxis.set_major_locator(mdates.HourLocator(interval=max(1, int(tick_hours))))
    ax.xaxis.set_major_formatter(mdates.DateFormatter("%m-%d %H:%M"))
    plt.setp(ax.get_xticklabels(), rotation=90, fontsize=7)
    ax.set_xlabel("time"); ax.set_ylabel("power")
    ax.legend(loc="upper right", fontsize=6, ncol=2); ax.grid(alpha=0.25)
    fig.tight_layout()
    path = os.path.join(_station_dir(out_dir), f"station_{sanitize(st)}_Power.png")
    fig.savefig(path, dpi=110); plt.close(fig)
    return path


def plot_ghi(st, ghi_true: pd.Series, ghi_pred: pd.Series, rmse_v, out_dir, tick_hours):
    """2 线：lead-1 GHI 预测 vs GHI 真值（都来自 input 侧 list[0]，是特征质量图不是模型输出图）。"""
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.dates as mdates
    import matplotlib.pyplot as plt
    _cn_font()
    fig, ax = plt.subplots(figsize=(24, 6))
    ax.plot(ghi_true.index, ghi_true, label="GHI_real_future (true)", color="#1f77b4", lw=1.3)
    ax.plot(ghi_pred.index, ghi_pred, label="GHI_SOLARGIS_predict (lead-1 pred)",
            color="#d62728", lw=1.1, alpha=0.85)
    ax.fill_between(ghi_true.index, ghi_true.to_numpy(float), ghi_pred.to_numpy(float),
                    color="#d62728", alpha=0.12)
    ax.set_title(f"Station {st} - GHI (lead-1)   RMSE={rmse_v:.3f}", fontsize=13, fontweight="bold")
    ax.xaxis.set_major_locator(mdates.HourLocator(interval=max(1, int(tick_hours))))
    ax.xaxis.set_major_formatter(mdates.DateFormatter("%m-%d %H:%M"))
    plt.setp(ax.get_xticklabels(), rotation=90, fontsize=7)
    ax.set_xlabel("time"); ax.set_ylabel("GHI"); ax.legend(loc="upper right"); ax.grid(alpha=0.25)
    fig.tight_layout()
    path = os.path.join(_station_dir(out_dir), f"station_{sanitize(st)}_GHI.png")
    fig.savefig(path, dpi=110); plt.close(fig)
    return path


# ================================================================ main
def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--input-dir", required=True, help="真值侧根目录：date=YYYY-MM-DD/time=HH:MM/ 分区")
    ap.add_argument("--predict-dir", required=True, help="预测侧扁平目录：每 起报 一个 parquet，文件名含 YYYYMMDDHHMM")
    ap.add_argument("--date", required=True, help="分析日 D，如 20260723 或 2026-07-23")
    ap.add_argument("--out-dir", default="station_analysis_ultra_short_out")
    ap.add_argument("--pred-col-template", default="predict_power_{station}")
    ap.add_argument("--station-col", default="station")
    ap.add_argument("--drop-night", action="store_true", help="remove each day's 00:00-night_end_hour points")
    ap.add_argument("--night-end-hour", type=float, default=5.0)
    ap.add_argument("--tick-hours", type=int, default=1)
    ap.add_argument("--no-plots", action="store_true", help="no plots, still writes CSVs")
    args = ap.parse_args()
    D = pd.Timestamp(args.date).normalize()

    truth, miss_in = load_truth(args.input_dir, D, args.station_col)
    if not truth:
        raise SystemExit("no input data found in any 起报 dir -- check --input-dir/--date")
    probe = None
    for S in issue_times(D):
        probe = find_parquet(args.predict_dir, S.strftime("%Y%m%d%H%M"))
        if probe:
            break
    if probe is None:
        raise SystemExit("no predict parquet found for any 起报 -- check --predict-dir/--date")
    pred_sts = set(stations_from_columns(pd.read_parquet(probe).columns, args.pred_col_template))
    sts = sorted(set(truth) & pred_sts, key=str)
    only_in, only_pred = sorted(set(truth) - pred_sts), sorted(pred_sts - set(truth))
    if only_in:
        print(f"  [warn] stations only on input side, skipped: {only_in}")
    if only_pred:
        print(f"  [warn] stations only on predict side, skipped: {only_pred}")
    if not sts:
        raise SystemExit("no station present on both input and predict sides")
    mats, miss_pred = load_predict_matrix(args.predict_dir, D, sts, args.pred_col_template)

    out_root = os.path.join(args.out_dir, D.strftime("%Y%m%d"))
    os.makedirs(out_root, exist_ok=True)
    keep = night_mask(target_grid(D), args.drop_night, args.night_end_hour)
    power_rows, feat_rows = [], []
    for st in sts:
        tr = truth[st]
        rv, n = pooled_rmse(tr["power_true"], mats[st], keep)
        if rv is not None:
            power_rows.append({"station": st, "power_rmse": round(rv, 6), "n_points": n})
        else:
            print(f"  [warn] station {st}: no scored (lead, target) pairs, power skipped")
        gt, gp = tr["ghi_true"][keep], tr["ghi_pred"][keep]
        both = np.isfinite(gt.to_numpy(float)) & np.isfinite(gp.to_numpy(float))
        grm = rmse(gp.to_numpy(float)[both], gt.to_numpy(float)[both]) if both.any() else None
        if grm is not None:
            feat_rows.append({"station": st, "feature": "GHI", "rmse": round(grm, 6),
                              "n_points": int(both.sum())})
        if not args.no_plots:
            plot_power_17(st, tr["power_true"][keep], mats[st][keep], rv, n, out_root, args.tick_hours)
            if grm is not None:
                plot_ghi(st, gt, gp, grm, out_root, args.tick_hours)

    if power_rows:
        pd.DataFrame(power_rows).sort_values("power_rmse", ascending=False).to_csv(
            os.path.join(out_root, "station_power_rmse.csv"), index=False)
    if feat_rows:
        pd.DataFrame(feat_rows).sort_values("rmse", ascending=False).to_csv(
            os.path.join(out_root, "station_feature_rmse.csv"), index=False)
    print(f"[ultra_short] D={D:%Y-%m-%d}   stations x{len(sts)}   "
          f"missing 起报: predict {miss_pred}/{len(issue_times(D))}, input {miss_in}/96   -> {out_root}/")


if __name__ == "__main__":
    main()
```

- [ ] **Step 4: Run the full ultra-short suite, verify green**

Run: `python3 -m pytest test_station_analysis_ultra_short.py -q`
Expected: ALL PASS (unit + e2e).

- [ ] **Step 5: Regression — short suite still green**

Run: `python3 -m pytest test_station_analysis_short.py -q`
Expected: ALL PASS (no shared code, but confirm).

- [ ] **Step 6: Commit**

```bash
git add 短期分析/station_analysis_ultra_short.py 短期分析/test_station_analysis_ultra_short.py
git commit -m "feat(ultra_short): pooled RMSE + 17-line/GHI plots + CLI"
```

---

### Task 5: README update

**Files:**
- Modify: `短期分析/README.md`

**Interfaces:** none (docs only; describes Tasks 1–4 behavior).

- [ ] **Step 1: Update the short section and add the ultra-short section**

In `短期分析/README.md`:
1. Remove every mention of a `--short` flag / plain no-flag mode (lines ~40, ~49, ~94): the report-day + `D+1`/`D+4` + `history/` layout is unconditional; document `--date YYYY-MM-DD`（缺省取 `timestamp_win` 最早日期并播报 `using D = ...`）and `--pred-col-template`（默认 `predict_power_{station}`）。Document the counterfactual window guard: 窗口内无真值点的站 0 次 API 调用、直接记 `no_overlap`。
2. Append a new top-level section:

```markdown
## 超短期：station_analysis_ultra_short.py

自包含，同样只依赖 pandas / numpy / pyarrow / matplotlib。

```bash
python3 station_analysis_ultra_short.py --input-dir <根目录> --predict-dir <预测目录> \
  --date 20260723 --out-dir out_us
```

**预测侧（--predict-dir）**：扁平目录，每 15min 一个 起报、每 起报 一个 parquet，文件名含
`YYYYMMDDHHMM`（按该 token glob，容忍文件名拼写漂移；同 token 多文件报错退出）。表结构 =
`dtime` 列 + 每站一列（`--pred-col-template`，默认 `predict_power_{station}`）；行自 起报+15min
起，只取前 16 点（lead 1..16 = 15min..4h）。

**真值侧（--input-dir）**：Hive 分区 `date=YYYY-MM-DD/time=HH:MM/` 下唯一 parquet
（schema 同短期 input，list 列长 192）；只取 `observe_power_future` / `GHI_real_future` /
`GHI_SOLARGIS_predict` 各 list 的第 0 个元素（= 起报+15min 处的值）。

**重建**：目标网格 = D 00:00..23:45（96 点）。目标 t 的 16 个预测来自 起报 t-4h..t-15min；
线 `p_j` = 恒定 lead(17-j)：**p1 = 4h 前（最旧），p16 = 15min 前（最新）**。t=00:00 的真值来自
`date=D-1/time=23:45`；p1 需要 `D-1 20:00` 起的预测 parquet。缺 起报 → 告警 + NaN 缺口，不中断。

**产物**（`<out>/<YYYYMMDD>/`）：
- `stations/station_<站>_Power.png` — 17 线（真值黑粗 + p1..p16 由浅到深）
- `stations/station_<站>_GHI.png` — 2 线（lead-1 GHI 预测 vs 真值；两者都来自 input 侧 = 特征质量图）
- `station_power_rmse.csv` — 每站 16 lead 合并 RMSE（降序 = 排名）
- `station_feature_rmse.csv` — 每站 lead-1 GHI RMSE

无散点 / Theil / 舰队总览 / 反事实 / history / 南网指标。
```

- [ ] **Step 2: Verify README claims against behavior**

Run: `python3 -m pytest test_station_analysis_short.py test_station_analysis_ultra_short.py -q`
Expected: ALL PASS. Skim the README diff once against the CLI help of both scripts (`python3 station_analysis_ultra_short.py --help`) for arg-name typos.

- [ ] **Step 3: Commit**

```bash
git add 短期分析/README.md
git commit -m "docs(短期分析): unconditional short layout + ultra-short 16-lead section"
```
