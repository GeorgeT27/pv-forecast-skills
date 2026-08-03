# station_analysis.py `--short` mode Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a `--short` flag to `row-diagnostic/station_analysis.py` that produces two complete output sets — one per 24h horizon slice (D+1 and D+4, 96 points each) — under `<out-dir>/D+1/` and `<out-dir>/D+4/`.

**Architecture:** Slice by an absolute-time window mask applied at the alignment choke point (`_aligned` / `cf_metrics`), so truth (from input lists) and pred (from predict table) are masked identically with one change. The per-station+fleet analysis body is extracted into `run_analysis(..., out_dir, win)` and called once per window; the counterfactual similarly gains `out_dir`/`win` params. Default (non-`--short`) behavior is unchanged: a single `win=None` pass writing straight to `<out-dir>`.

**Tech Stack:** Python 3, pandas, numpy, matplotlib (Agg), pytest, subprocess-driven tests.

## Global Constraints

- Self-contained script: only `pandas`/`numpy`/`matplotlib`/stdlib. No new dependencies.
- Default (no `--short`) behavior must stay byte-for-behavior identical — the existing `test_station_analysis.py` suite is the regression guard and must stay green.
- 15-min step assumed for the 96-point arithmetic (`24h / step`); the general mask works for any step, count follows from the data.
- Window is half-open `[start, start + 24h)` — the next-midnight point belongs to the following day.
- Output subfolders are literally named `D+1` and `D+4`.
- All new/changed comments and CLI help follow the file's existing bilingual, terse style.

---

### Task 1: Extract `run_analysis` from `main` (pure refactor, no behavior change)

**Files:**
- Modify: `row-diagnostic/station_analysis.py` (the tail of `main`, current lines ≈ 898–1089)
- Test: `row-diagnostic/test_station_analysis.py` (existing suite as regression guard)

**Interfaces:**
- Produces: `run_analysis(inp, pred, args, step, active_pairs, have_ghi, cap_map, out_dir, win, label) -> None` — runs the full per-station + fleet analysis for one window into `out_dir`. `win` is `(start, end)` or `None`; `label` is `"D+1"`/`"D+4"`/`None` (used only for log prefixes). This task calls it once with `out_dir=args.out_dir, win=None, label=None`.

- [ ] **Step 1: Run the existing suite to confirm a green baseline**

Run: `cd row-diagnostic && python3 -m pytest test_station_analysis.py -q`
Expected: PASS (all tests). This is the refactor's safety net.

- [ ] **Step 2: Extract the body into `run_analysis`**

Cut the block in `main` that currently starts at `stations = list(pd.unique(inp[args.station_col]))` and runs through the `print("  Products: " + ...)` line (the per-station loop, `--worst-only` selection, station CSV writes, fleet overview, Theil, and terminal summary). Define, just above `main`:

```python
def run_analysis(inp, pred, args, step, active_pairs, have_ghi, cap_map, out_dir, win, label):
    """Run the full per-station + fleet analysis for ONE window into out_dir.
    win=(start,end) restricts every aligned series to [start,end); win=None = whole series.
    label prefixes log lines ('D+1'/'D+4'); None = default single pass."""
    pfx = f"[{label}] " if label else ""
    plot_station = not (args.no_plots or args.no_station_plots)
    stations = list(pd.unique(inp[args.station_col]))
    power_rows, feat_rows, imgs = [], [], []
    fleet_recs, hourly = [], {}
    # <... paste the moved body verbatim ...>
```

Then apply these mechanical substitutions **inside the moved body only**:
1. Every `args.out_dir` → `out_dir`.
2. Every `_aligned(A, B, args.drop_night, args.night_end_hour)` → `_aligned(A, B, args.drop_night, args.night_end_hour, win)` (three call sites: Power, feature, GHI).
3. The final "nothing could be produced" guard becomes window-aware — replace:

```python
    if not power_rows and not feat_rows and fleet_img is None:
        raise SystemExit("nothing could be produced (check --pred-col-template against the predict-table column names, "
                         "whether times align, whether columns exist).")
```
with:
```python
    if not power_rows and not feat_rows and fleet_img is None:
        msg = ("nothing could be produced (check --pred-col-template against the predict-table column names, "
               "whether times align, whether columns exist).")
        if win is None:
            raise SystemExit(msg)
        print(f"  {pfx}[warn] {msg}")
        return
```
4. Prefix the two summary prints with `pfx`:
   - `print(f"[station_analysis] stations x{len(stations)} ...")` → `print(f"{pfx}[station_analysis] stations x{len(stations)} ...")`

- [ ] **Step 3: Replace the removed block in `main` with a single call**

Where the block used to be (after `os.makedirs(args.out_dir, exist_ok=True)`), put:

```python
    os.makedirs(args.out_dir, exist_ok=True)
    run_analysis(inp, pred, args, step, active_pairs, have_ghi, cap_map,
                 args.out_dir, None, None)

    if args.counterfactual:
        run_counterfactual(inp, pred, args, cap_map, step)
```
Delete the now-duplicated `os.makedirs`/counterfactual lines that followed the old block. Confirm `plot_station` is still defined in `main` only if `main` still uses it — it does not anymore, so remove the stray `plot_station = ...` line from `main` (it now lives in `run_analysis`).

- [ ] **Step 4: Run the suite to verify no behavior change**

Run: `cd row-diagnostic && python3 -m pytest test_station_analysis.py -q`
Expected: PASS (same as Step 1). If any test fails, the extraction changed behavior — diff the moved body against the original.

- [ ] **Step 5: Commit**

```bash
git add row-diagnostic/station_analysis.py
git commit -m "refactor(station_analysis): 抽出 run_analysis(out_dir,win,label)，为 --short 双切片铺路（行为不变）"
```

---

### Task 2: Window mask in `_aligned` and `cf_metrics`

**Files:**
- Modify: `row-diagnostic/station_analysis.py` (add `window_mask`; extend `_aligned` at ≈ line 117 and `cf_metrics` at ≈ line 568)
- Test: `row-diagnostic/test_station_analysis.py` (new unit tests importing the module directly)

**Interfaces:**
- Consumes: `night_mask` (existing).
- Produces:
  - `window_mask(idx: pd.DatetimeIndex, win) -> np.ndarray` — True=keep; `win=(start,end)` keeps `[start,end)`; `win=None` keeps all.
  - `_aligned(a, b, drop_night, night_end_hour, win=None)` — now also restricts common times to `win`.
  - `cf_metrics(p_true, p_base, p_cf, drop_night, night_end_hour, cap, win=None)` — same restriction on its 3-series common index.

- [ ] **Step 1: Write the failing unit test**

Add to `test_station_analysis.py`:
```python
import importlib.util
_spec = importlib.util.spec_from_file_location("sa", SCRIPT)
sa = importlib.util.module_from_spec(_spec); _spec.loader.exec_module(sa)


def test_window_mask_half_open():
    idx = pd.date_range("2026-07-27 00:00", periods=4, freq="15min")
    m = sa.window_mask(idx, (pd.Timestamp("2026-07-27 00:00"), pd.Timestamp("2026-07-27 00:45")))
    assert list(m) == [True, True, True, False]          # end is exclusive
    assert list(sa.window_mask(idx, None)) == [True] * 4


def test_aligned_applies_window():
    idx = pd.date_range("2026-07-27 00:00", periods=4, freq="15min")
    a = pd.Series([1., 2, 3, 4], index=idx)
    b = pd.Series([1., 2, 3, 4], index=idx)
    out = sa._aligned(a, b, False, 5.0,
                      (pd.Timestamp("2026-07-27 00:00"), pd.Timestamp("2026-07-27 00:30")))
    times, av, bv = out
    assert len(times) == 2 and list(av) == [1.0, 2.0]     # only 00:00, 00:15 kept
```

- [ ] **Step 2: Run to verify it fails**

Run: `cd row-diagnostic && python3 -m pytest test_station_analysis.py::test_window_mask_half_open test_station_analysis.py::test_aligned_applies_window -q`
Expected: FAIL — `window_mask` does not exist / `_aligned` takes no `win`.

- [ ] **Step 3: Implement `window_mask` and thread it in**

Add just below `night_mask`:
```python
def window_mask(idx: pd.DatetimeIndex, win) -> np.ndarray:
    """True = keep. win=(start,end) keeps [start, end) (end exclusive); win=None keeps all."""
    if win is None:
        return np.ones(len(idx), bool)
    start, end = win
    return (idx >= start) & (idx < end)
```
Change `_aligned` signature and mask line:
```python
def _aligned(a: pd.Series, b: pd.Series, drop_night, night_end_hour, win=None):
    """Take common time points of two series + drop night + restrict to win. Returns (times, a_vals, b_vals) or None."""
    common = a.index.intersection(b.index).sort_values()
    if len(common) == 0:
        return None
    keep = night_mask(common, drop_night, night_end_hour) & window_mask(common, win)
    common = common[keep]
    if len(common) == 0:
        return None
    return common, a.loc[common].to_numpy(), b.loc[common].to_numpy()
```
Change `cf_metrics` signature and its filter line (the line currently `common = common[night_mask(common, drop_night, night_end_hour)]`):
```python
def cf_metrics(p_true, p_base, p_cf, drop_night, night_end_hour, cap, win=None):
    ...
    common = common[night_mask(common, drop_night, night_end_hour) & window_mask(common, win)]
```

- [ ] **Step 4: Run to verify pass + no regression**

Run: `cd row-diagnostic && python3 -m pytest test_station_analysis.py -q`
Expected: PASS (new unit tests + full existing suite; the new default `win=None` args keep old call sites valid).

- [ ] **Step 5: Commit**

```bash
git add row-diagnostic/station_analysis.py row-diagnostic/test_station_analysis.py
git commit -m "feat(station_analysis): window_mask + _aligned/cf_metrics 支持 win 绝对时窗切片"
```

---

### Task 3: `--short` / `--date` + `compute_windows` + per-window loop

**Files:**
- Modify: `row-diagnostic/station_analysis.py` (`main`: add args, add `compute_windows`, replace single call with a window loop; update module docstring Usage)
- Modify: `row-diagnostic/README.md` (document `--short` / `--date`)
- Test: `row-diagnostic/test_station_analysis.py` (new fixture + tests)

**Interfaces:**
- Consumes: `run_analysis(...)` (Task 1), `window_mask`/`_aligned(win=)` (Task 2).
- Produces: `compute_windows(args, inp) -> list[tuple[str|None, pd.Timestamp|None, pd.Timestamp|None]]` — `[(None,None,None)]` when not `--short`; else `[("D+1", d1, d1+1d), ("D+4", d4, d4+1d)]` with `d1 = D+1day@00:00`, `d4 = D+4day@00:00`, `D` from `--date` or `date(min timestamp_win)`.

- [ ] **Step 1: Write the failing tests + fixture**

Add to `test_station_analysis.py`:
```python
@pytest.fixture
def short_data(tmp_path):
    """起报 D=2026-07-26 10:00, 每站一窗、480 点、15min。predict 覆盖全部 480 绝对时刻。"""
    D = pd.Timestamp("2026-07-26 10:00:00")
    n = 480
    times = [D + pd.Timedelta(minutes=15 * (k + 1)) for k in range(n)]
    truth = {"s1": [float(10 + (k % 96)) for k in range(n)],       # 日内 0..95 变化
             "s2": [float(5 + (k % 96)) for k in range(n)]}
    off = {"s1": 2.0, "s2": 3.0}
    rows = [{"station": st, "timestamp_win": D, "observe_power_future": truth[st]}
            for st in ("s1", "s2")]
    pd.DataFrame(rows).to_parquet(tmp_path / "input.parquet")
    pred = pd.DataFrame({"dtime": times})
    for st in ("s1", "s2"):
        pred[st] = [v + off[st] for v in truth[st]]
    pred.to_parquet(tmp_path / "predict.parquet")
    return tmp_path


def _run_short(wd, extra=()):
    r = subprocess.run(
        [sys.executable, SCRIPT, "--input", str(wd / "input.parquet"),
         "--predict", str(wd / "predict.parquet"), "--out-dir", str(wd / "out"),
         "--short"] + list(extra),
        cwd=str(wd), capture_output=True, text=True)
    assert r.returncode == 0, r.stdout + r.stderr
    return r


def test_short_makes_two_folders_96pts(short_data):
    r = _run_short(short_data, ["--no-plots", "--pred-col-template", "{station}"])
    for sub in ("D+1", "D+4"):
        d = short_data / "out" / sub
        assert d.is_dir(), f"missing {sub}"
        pw = pd.read_csv(d / "station_power_rmse.csv")
        assert set(pw["n_points"]) == {96}, f"{sub}: {pw['n_points'].tolist()}"
    assert "using D = 2026-07-26" in r.stdout               # auto-fallback announced


def test_short_date_override(short_data):
    r = _run_short(short_data, ["--no-plots", "--pred-col-template", "{station}",
                                "--date", "2026-07-26"])
    pw = pd.read_csv(short_data / "out" / "D+1" / "station_power_rmse.csv")
    assert set(pw["n_points"]) == {96}
    assert "using D" not in r.stdout                        # explicit date -> no fallback line


def test_default_no_short_folders(short_data):
    # 常规模式（无 --short）：直接写 out/，不建 D+1/D+4
    subprocess.run(
        [sys.executable, SCRIPT, "--input", str(short_data / "input.parquet"),
         "--predict", str(short_data / "predict.parquet"), "--out-dir", str(short_data / "out"),
         "--no-plots", "--pred-col-template", "{station}"],
        cwd=str(short_data), capture_output=True, text=True, check=True)
    assert not (short_data / "out" / "D+1").exists()
    assert (short_data / "out" / "station_power_rmse.csv").exists()


def test_short_worst_only(short_data):
    # --worst-only 1：每个切片图只画最差 1 站，CSV 仍含全部站
    r = _run_short(short_data, ["--pred-col-template", "{station}", "--worst-only", "1"])
    pw = pd.read_csv(short_data / "out" / "D+1" / "station_power_rmse.csv")
    assert len(pw) == 2                                     # CSV 全量
    pngs = os.listdir(short_data / "out" / "D+1" / "stations")
    powers = [f for f in pngs if f.endswith("_Power.png")]
    assert len(powers) == 1                                 # 仅最差 1 站出图
```

- [ ] **Step 2: Run to verify failure**

Run: `cd row-diagnostic && python3 -m pytest test_station_analysis.py -k short -q`
Expected: FAIL — `--short` is an unrecognized argument (nonzero exit).

- [ ] **Step 3: Add args + `compute_windows` + loop**

In `main`'s argparse block (near the other flags), add:
```python
    ap.add_argument("--short", action="store_true",
                    help="短期模式：只看 D+1 与 D+4 两个 24h 切片，各产一份全套产物到 out_dir/D+1、out_dir/D+4")
    ap.add_argument("--date", default=None,
                    help="起报日 YYYY-MM-DD；D+1/D+4 从此日算。--short 专用，缺省则取最早 timestamp_win 的日期")
```
Add, just above `main`:
```python
def compute_windows(args, inp):
    """[(label, start, end), ...]. 非 short：单趟全序列 (None,None,None)。
    short：D = --date 或最早 timestamp_win 的日期，切 [D+1 00:00, +24h) 与 [D+4 00:00, +24h)。"""
    if not args.short:
        return [(None, None, None)]
    if args.date:
        D = pd.Timestamp(args.date).normalize()
    else:
        D = pd.Timestamp(inp[args.win_col].min()).normalize()
        print(f"  [short] --date not given; using D = {D:%Y-%m-%d} (from earliest {args.win_col})")
    day = pd.Timedelta(days=1)
    d1, d4 = D + day, D + 4 * day
    return [("D+1", d1, d1 + day), ("D+4", d4, d4 + day)]
```
Replace the Task-1 call block with the loop (note `inp[args.win_col]` is already datetime by this point):
```python
    os.makedirs(args.out_dir, exist_ok=True)
    windows = compute_windows(args, inp)
    for label, start, end in windows:
        sub_out = args.out_dir if label is None else os.path.join(args.out_dir, label)
        os.makedirs(sub_out, exist_ok=True)
        run_analysis(inp, pred, args, step, active_pairs, have_ghi, cap_map,
                     sub_out, (start, end) if label else None, label)

    if args.counterfactual:
        for label, start, end in windows:
            sub_out = args.out_dir if label is None else os.path.join(args.out_dir, label)
            run_counterfactual(inp, pred, args, cap_map, step)   # out_dir/win wired in Task 4
```

- [ ] **Step 4: Run to verify pass + no regression**

Run: `cd row-diagnostic && python3 -m pytest test_station_analysis.py -q`
Expected: PASS (new `-k short` tests + full existing suite).

- [ ] **Step 5: Update docs**

In `station_analysis.py`'s module docstring `Usage:` block, add a line:
```
    [--short [--date 2026-07-26]]   # 短期：D+1/D+4 两个 24h 切片，各产一套到 out_dir/D+1、out_dir/D+4
```
In `row-diagnostic/README.md`, add a short subsection describing `--short` (two 96-point slices, `--date` anchor + fallback, output subfolders, worst-only per slice). Match the README's existing tone/length.

- [ ] **Step 6: Commit**

```bash
git add row-diagnostic/station_analysis.py row-diagnostic/test_station_analysis.py row-diagnostic/README.md
git commit -m "feat(station_analysis): --short 双 24h 切片（D+1/D+4 各 96 点、子目录分装、--date 可选带回退）"
```

---

### Task 4: Counterfactual per-window

**Files:**
- Modify: `row-diagnostic/station_analysis.py` (`run_counterfactual` gains `out_dir`/`win`; pass `win` into `cf_metrics`; `main` CF loop uses subfolders)
- Test: `row-diagnostic/test_station_analysis.py` (new fixture + test with fake API)

**Interfaces:**
- Consumes: `cf_metrics(..., win=None)` (Task 2), `compute_windows` (Task 3), `_FakeAPI`/`fake_api`/`_url` (existing test infra).
- Produces: `run_counterfactual(inp, pred, args, cap_map, step, out_dir=None, win=None)` — writes `counterfactual_results.csv` / pngs under `out_dir` (default `args.out_dir`), metrics restricted to `win`.

- [ ] **Step 1: Write the failing test + fixture**

Add to `test_station_analysis.py`:
```python
@pytest.fixture
def short_cf_data(tmp_path):
    """短期反事实：D=2026-07-26 10:00、每站一窗 480 点。假模型 power=GHI/10。"""
    D = pd.Timestamp("2026-07-26 10:00:00")
    n = 480
    times = [D + pd.Timedelta(minutes=15 * (k + 1)) for k in range(n)]
    OFF = {"c1": 40.0}
    gt = {"c1": [float(100 + k) for k in range(n)]}                 # GHI 真值
    rows = [{"station": "c1", "timestamp_win": D,
             "observe_power_future": [g / 10.0 for g in gt["c1"]],
             "GHI_SOLARGIS_predict": [g + OFF["c1"] for g in gt["c1"]],
             "GHI_real_future": gt["c1"]}]
    pd.DataFrame(rows).to_parquet(tmp_path / "input.parquet")
    pred = pd.DataFrame({"dtime": times})
    pred["c1"] = [(g + OFF["c1"]) / 10.0 for g in gt["c1"]]         # 复现基线（=API baseline）
    pred.to_parquet(tmp_path / "predict.parquet")
    return tmp_path


def test_short_counterfactual_per_window(short_cf_data, fake_api):
    r = subprocess.run(
        [sys.executable, SCRIPT, "--input", str(short_cf_data / "input.parquet"),
         "--predict", str(short_cf_data / "predict.parquet"),
         "--out-dir", str(short_cf_data / "out"), "--short", "--no-plots",
         "--counterfactual", "--api-url", _url(fake_api)],
        cwd=str(short_cf_data), capture_output=True, text=True)
    assert r.returncode == 0, r.stdout + r.stderr
    for sub in ("D+1", "D+4"):
        p = short_cf_data / "out" / sub / "counterfactual_results.csv"
        assert p.exists(), f"missing CF csv in {sub}"
        d = pd.read_csv(p).set_index("station")
        assert d.loc["c1", "status"] == "ok"
        assert int(d.loc["c1", "n_points"]) == 96              # 每切片 96 点
    assert fake_api.hits == 4                                   # 1 站 × 2 次 × 2 切片
```

- [ ] **Step 2: Run to verify failure**

Run: `cd row-diagnostic && python3 -m pytest test_station_analysis.py::test_short_counterfactual_per_window -q`
Expected: FAIL — CF writes only to `out/` (no `D+1`/`D+4` CF csv), and `n_points`=480 not 96.

- [ ] **Step 3: Wire `out_dir`/`win` through `run_counterfactual`**

Change the signature:
```python
def run_counterfactual(inp, pred, args, cap_map, step, out_dir=None, win=None):
    """... 2 API calls per station ... restricted to win, written under out_dir."""
    out_dir = out_dir if out_dir is not None else args.out_dir
```
Inside the body, replace `args.out_dir` with `out_dir` (the `csv_path = os.path.join(args.out_dir, "counterfactual_results.csv")` line and the `plot_cf_overview(okd, args.out_dir, ...)` call). In the `plot_cf_curves(...)` call, pass `out_dir` instead of `args.out_dir`. Change the metrics call:
```python
        got = cf_metrics(truth, p_base, p_cf, args.drop_night, args.night_end_hour, cap, win)
```

- [ ] **Step 4: Use subfolders in `main`'s CF loop**

Replace the placeholder CF call from Task 3 Step 3 with:
```python
    if args.counterfactual:
        for label, start, end in windows:
            sub_out = args.out_dir if label is None else os.path.join(args.out_dir, label)
            run_counterfactual(inp, pred, args, cap_map, step,
                               out_dir=sub_out, win=(start, end) if label else None)
```

- [ ] **Step 5: Run to verify pass + full regression**

Run: `cd row-diagnostic && python3 -m pytest test_station_analysis.py -q`
Expected: PASS (new CF-per-window test + all existing CF tests — the default `out_dir=None,win=None` keeps the old single-pass CF calls identical).

- [ ] **Step 6: Commit**

```bash
git add row-diagnostic/station_analysis.py row-diagnostic/test_station_analysis.py
git commit -m "feat(station_analysis): 反事实随 --short 逐切片（out_dir/win 参数、D+1/D+4 各自 resumable）"
```

---

### Task 5: End-to-end smoke on a realistic 480-point fixture (plots on)

**Files:**
- Test: `row-diagnostic/test_station_analysis.py` (one plots-on end-to-end test)

**Interfaces:**
- Consumes: `short_data` fixture (Task 3).

- [ ] **Step 1: Write the end-to-end test (plots enabled)**

```python
def test_short_end_to_end_with_plots(short_data):
    r = _run_short(short_data, ["--pred-col-template", "{station}", "--worst-only", "2"])
    for sub in ("D+1", "D+4"):
        d = short_data / "out" / sub
        assert (d / "fleet_overview.png").exists()
        assert (d / "theil_decomposition.png").exists()
        assert (d / "fleet_ranking.csv").exists()
        stn = os.listdir(d / "stations")
        assert any(f.endswith("_Power.png") for f in stn)
        assert any(f.endswith("_scatter.png") for f in stn)
```

- [ ] **Step 2: Run it**

Run: `cd row-diagnostic && python3 -m pytest test_station_analysis.py::test_short_end_to_end_with_plots -q`
Expected: PASS — both slices produce fleet + Theil pngs, ranking CSV, and per-station Power/scatter pngs.

- [ ] **Step 3: Full suite once more**

Run: `cd row-diagnostic && python3 -m pytest test_station_analysis.py -q`
Expected: PASS (everything).

- [ ] **Step 4: Commit**

```bash
git add row-diagnostic/test_station_analysis.py
git commit -m "test(station_analysis): --short 480 点端到端冒烟（双切片全产物 + 图）"
```

---

## Self-Review

**Spec coverage:**
- `--short` flag + two output sets → Tasks 3 (loop/folders), 5 (e2e). ✓
- Anchor D via `--date` with `timestamp_win` fallback → Task 3 (`compute_windows`, `test_short_date_override`, fallback print). ✓
- D+1 / D+4 96-point half-open slices → Task 2 (`window_mask` half-open unit test), Task 3 (`n_points==96`). ✓
- Mask at `_aligned` (no input slicing) → Task 2. ✓
- Everything doubled incl. fleet/Theil/CSVs → Task 5 asserts fleet+Theil+ranking per slice; per-station via Task 3/5. ✓
- Counterfactual per-window → Task 4. ✓
- worst-only within slice → Task 3 `test_short_worst_only`. ✓
- Output layout `out_dir/D+1`, `out_dir/D+4` → Tasks 3/4/5. ✓
- Default behavior unchanged → Task 1 (regression), Task 3 `test_default_no_short_folders`. ✓
- Docs (docstring Usage + README) → Task 3 Step 5. ✓

**Placeholder scan:** No TBD/TODO; every code + test step has concrete content. ✓

**Type consistency:** `run_analysis(inp, pred, args, step, active_pairs, have_ghi, cap_map, out_dir, win, label)` — same 10-arg signature defined in Task 1 and called in Task 3. `compute_windows(args, inp)` returns `(label, start, end)` tuples, unpacked consistently in the Task 3/4 loops. `run_counterfactual(..., out_dir=None, win=None)` defined in Task 4, called with those kwargs in Task 4 Step 4. `window_mask(idx, win)`/`_aligned(...win=None)`/`cf_metrics(...win=None)` names match across Tasks 2–4. ✓

**Note on `--pred-col-template {station}`:** the `short_data`/`short_cf_data` fixtures name predict columns by bare station (`s1`,`c1`), so tests pass `--pred-col-template "{station}"`... which would look for a column literally named `s1` — the template's `{station}` expands to the station name, matching the bare column. (The default `predict_power_{station}` would look for `predict_power_s1`; the bare-name fallback also matches. Passing `{station}` is explicit and unambiguous.) ✓
