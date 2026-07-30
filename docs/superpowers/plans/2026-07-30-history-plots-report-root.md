# History Plots + `<起报日>` Report Root — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** In `--short` mode, add per-station single-line plots of the historical columns `observe_power` and `GHI_SOLARGIS` (last 2 days, ending at 起报时间) under a new `history/` folder, and group `D+1`/`D+4`/`history` under one report directory named by the 起报日 (e.g. `20260726`).

**Architecture:** One reversed-time-base flatten helper (`series_from_lists_history`), a lightweight plots-only driver (`run_history`) with its own single-line plotter (`plot_history_line`), and a directory change where `compute_windows` returns a report name so `main` nests every window under `out_dir/<YYYYMMDD>/`. History is `--short`-gated and computes no metrics.

**Tech Stack:** Python 3, pandas, numpy, matplotlib (Agg). Tests via pytest + subprocess, matching the existing `row-diagnostic/test_station_analysis.py` style.

## Global Constraints

- Single self-contained script `row-diagnostic/station_analysis.py` — no new module files, no new third-party deps.
- 起报时间 time-base for history: for a cell with `timestamp_win = t0` and finite list of length `L`, element `i` maps to `t0 − step·(L−1−i)`; `list[-1] → t0`.
- History window = `[T_end − 2 days, T_end]`, `T_end = max(timestamp_win)`; `HISTORY_DAYS = 2`, `HISTORY_COLS = ["observe_power", "GHI_SOLARGIS"]` — module constants, no new CLI flag.
- Report name = `D.strftime("%Y%m%d")` where `D` is the 起报日 from `compute_windows` (`--date` or earliest `timestamp_win`, normalized). Non-`--short` runs write directly to `--out-dir` (unchanged).
- Each per-station × per-column plot succeeds or fails independently: missing column, empty list, or empty-in-window skips only that one PNG with a warning.
- Tests are loaded against the module via the existing `sa` importlib handle (test file lines 315-317) for unit tests, and via subprocess `_run_short` for integration tests.

---

### Task 1: `series_from_lists_history` reversed-time-base helper

**Files:**
- Modify: `row-diagnostic/station_analysis.py` (add function next to `series_from_lists`, ~line 108)
- Test: `row-diagnostic/test_station_analysis.py` (add unit tests near the other `sa.*` unit tests, ~line 320)

**Interfaces:**
- Produces: `series_from_lists_history(wins, lists, step) -> pd.Series` — `wins` = iterable of window start timestamps, `lists` = iterable of per-window list/array cells, `step` = `pd.Timedelta`. Returns an absolute-time-indexed float Series (groupby-time mean, sorted); empty Series if no finite points.

- [ ] **Step 1: Write the failing tests**

Add to `row-diagnostic/test_station_analysis.py`:

```python
def test_series_from_lists_history_endpoint():
    t0 = pd.Timestamp("2026-07-26 10:00")
    step = pd.Timedelta(minutes=15)
    s = sa.series_from_lists_history([t0], [[1.0, 2.0, 3.0, 4.0]], step)
    assert s.index[-1] == t0                       # last element sits at 起报时间
    assert s.iloc[-1] == 4.0
    assert s.index[-2] == t0 - step                # one 15-min step back
    assert s.iloc[-2] == 3.0
    assert s.index[0] == t0 - step * 3             # first element = t0 - step*(L-1)


def test_series_from_lists_history_skips_nan_and_empty():
    t0 = pd.Timestamp("2026-07-26 10:00")
    step = pd.Timedelta(minutes=15)
    s = sa.series_from_lists_history([t0], [[float("nan"), 2.0]], step)
    assert list(s.to_numpy()) == [2.0]             # NaN dropped
    assert s.index[0] == t0                        # the surviving value is the endpoint
    assert sa.series_from_lists_history([t0], [None], step).empty
    assert sa.series_from_lists_history([t0], [[]], step).empty
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd row-diagnostic && python -m pytest test_station_analysis.py -k series_from_lists_history -v`
Expected: FAIL with `AttributeError: module 'sa' has no attribute 'series_from_lists_history'`

- [ ] **Step 3: Write minimal implementation**

Add to `row-diagnostic/station_analysis.py` immediately after `series_from_lists` (after its `return` at ~line 107):

```python
def series_from_lists_history(wins, lists, step) -> pd.Series:
    """Like series_from_lists but the list runs BACKWARD from the window time (起报时间): for a cell
    with timestamp_win=t0 and finite array of length L, element i -> t0 - step*(L-1-i), so the LAST
    element lands at t0, the second-to-last at t0-step, etc. Non-list / None / NaN cells auto-skipped;
    flatten all windows, groupby absolute time and dedup by mean."""
    times, vals = [], []
    for t0, fut in zip(wins, lists):
        if fut is None or np.ndim(fut) == 0:
            continue
        arr = np.asarray(fut, dtype=float).ravel()
        if arr.size == 0:
            continue
        t0 = pd.Timestamp(t0)
        L = arr.size
        for i, v in enumerate(arr):
            if np.isfinite(v):
                times.append(t0 - step * (L - 1 - i))
                vals.append(float(v))
    if not times:
        return pd.Series(dtype=float)
    s = pd.Series(vals, index=pd.DatetimeIndex(times))
    return s.groupby(s.index).mean().sort_index()
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd row-diagnostic && python -m pytest test_station_analysis.py -k series_from_lists_history -v`
Expected: PASS (2 tests)

- [ ] **Step 5: Commit**

```bash
git add row-diagnostic/station_analysis.py row-diagnostic/test_station_analysis.py
git commit -m "feat(station_analysis): series_from_lists_history (reversed time-base, list[-1]->起报时间)"
```

---

### Task 2: Report-root nesting — `compute_windows` returns report name, `main` nests windows

**Files:**
- Modify: `row-diagnostic/station_analysis.py` — `compute_windows` (~lines 1051-1068), `main` window/counterfactual loops (~lines 1150-1163), output-layout docstring (~lines 53-57)
- Test: `row-diagnostic/test_station_analysis.py` — update all `--short` path references (~lines 367-496)

**Interfaces:**
- Consumes: nothing new.
- Produces: `compute_windows(args, inp) -> (report_name, windows)` where `report_name` is `str` (`"%Y%m%d"`) in `--short` mode else `None`; `windows` is the same `[(label, start, end), ...]` list as before. `main` derives `report_root = args.out_dir if report_name is None else os.path.join(args.out_dir, report_name)` and hangs every window off it.

- [ ] **Step 1: Update the `--short` tests to expect the nested report root (red)**

In `row-diagnostic/test_station_analysis.py`, add a helper just below `_run_short` (after ~line 364):

```python
def _rep(wd, name="20260726"):
    """Report root for --short runs: <out>/<起报日 YYYYMMDD>/."""
    return wd / "out" / name
```

Then update every `--short` test to read from the report root instead of `out/` directly:

- `test_short_makes_two_folders_96pts`: replace `short_data / "out" / sub` with `_rep(short_data) / sub`.
- `test_short_date_override`: replace `short_data / "out" / "D+1"` with `_rep(short_data) / "D+1"`.
- `test_short_date_shifts_window`: replace `short_data / "out" / "D+1"` with `_rep(short_data, "20260727") / "D+1"` (— `--date 2026-07-27` → report `20260727`).
- `test_short_worst_only`: replace both `short_data / "out" / "D+1"` occurrences with `_rep(short_data) / "D+1"`.
- `test_short_end_to_end_with_plots`: replace `short_data / "out" / sub` with `_rep(short_data) / sub`.
- `test_short_counterfactual_per_window`: replace `short_cf_data / "out" / sub / "counterfactual_results.csv"` with `_rep(short_cf_data) / sub / "counterfactual_results.csv"`.
- `test_short_missing_d4_slice_skips_gracefully`: replace `short_data_missing_d4 / "out" / "D+1" / ...` and `.../ "D+4" / ...` with `_rep(short_data_missing_d4) / "D+1" / ...` and `_rep(short_data_missing_d4) / "D+4" / ...`.
- `test_default_no_short_folders`: leave unchanged (non-`--short` still writes directly to `out/`).

- [ ] **Step 2: Run the short tests to verify they fail**

Run: `cd row-diagnostic && python -m pytest test_station_analysis.py -k short -v`
Expected: FAIL — folders found at `out/D+1` etc., not under `out/20260726/`.

- [ ] **Step 3: Change `compute_windows` to return the report name**

Replace `compute_windows` (~lines 1051-1068) with:

```python
def compute_windows(args, inp):
    """(report_name, [(label, start, end), ...]). report_name = D.strftime('%Y%m%d') (起报日) in --short,
    else None. 非 short：单趟全序列 (None,None,None)。short：D = --date 或最早 timestamp_win 的日期，
    切 [D+1 00:00, +24h) 与 [D+4 00:00, +24h)。"""
    if not args.short:
        if args.date:
            print("  [warn] --date is ignored without --short")
        return None, [(None, None, None)]
    if args.date:
        try:
            D = pd.Timestamp(args.date).normalize()
        except (ValueError, TypeError):
            raise SystemExit(f"--date must be a valid date (YYYY-MM-DD), got '{args.date}'")
    else:
        D = pd.Timestamp(inp[args.win_col].min()).normalize()
        print(f"  [short] --date not given; using D = {D:%Y-%m-%d} (from earliest {args.win_col})")
    day = pd.Timedelta(days=1)
    d1, d4 = D + day, D + 4 * day
    return D.strftime("%Y%m%d"), [("D+1", d1, d1 + day), ("D+4", d4, d4 + day)]
```

- [ ] **Step 4: Nest windows under `report_root` in `main`**

Replace the block at ~lines 1150-1163 (from `os.makedirs(args.out_dir, exist_ok=True)` through the counterfactual loop) with:

```python
    os.makedirs(args.out_dir, exist_ok=True)
    report_name, windows = compute_windows(args, inp)
    report_root = args.out_dir if report_name is None else os.path.join(args.out_dir, report_name)
    os.makedirs(report_root, exist_ok=True)
    for label, start, end in windows:
        sub_out = report_root if label is None else os.path.join(report_root, label)
        os.makedirs(sub_out, exist_ok=True)
        run_analysis(inp, pred, args, step, active_pairs, have_ghi, cap_map,
                     sub_out, (start, end) if label else None, label)

    if args.counterfactual:
        # sub_out dirs already created by the run_analysis loop above (same windows)
        for label, start, end in windows:
            sub_out = report_root if label is None else os.path.join(report_root, label)
            run_counterfactual(inp, pred, args, cap_map, step,
                               out_dir=sub_out, win=(start, end) if label else None)
```

(The `if args.short: run_history(...)` call is added in Task 3 — do not add it here, `run_history` does not exist yet.)

- [ ] **Step 5: Update the output-layout docstring**

In the module docstring, replace the "Output layout" block (~lines 53-57) so the `--short` case shows the report root. Change the opening line to note nesting and add a short-mode note:

```
Output layout (everything under one --out-dir, default station_analysis_out/):
  <out-dir>/                     overview pngs (fleet_overview / theil_decomposition / counterfactual_overview) + all CSVs
  <out-dir>/stations/            per-station pngs (Power / feature curves, scatter, counterfactual three-line)
  --short mode nests one level deeper under the 起报日: <out-dir>/<YYYYMMDD>/{D+1,D+4,history}/, each D+1/D+4
  carrying the same overview+stations layout above; history/ holds plots only (see below).
  All plots draw automatically on every run -- no extra flag for Theil or scatter; --no-plots / --no-station-plots /
  --no-fleet turn layers off, --worst-only restricts which stations get images.
```

- [ ] **Step 6: Run the full suite to verify green**

Run: `cd row-diagnostic && python -m pytest test_station_analysis.py -v`
Expected: PASS (all previously-green tests plus Task 1's, now under the nested paths).

- [ ] **Step 7: Commit**

```bash
git add row-diagnostic/station_analysis.py row-diagnostic/test_station_analysis.py
git commit -m "feat(station_analysis): --short nests D+1/D+4 under <起报日 YYYYMMDD> report root"
```

---

### Task 3: `run_history` + `plot_history_line` — per-station history plots, wired into `main`

**Files:**
- Modify: `row-diagnostic/station_analysis.py` — add `HISTORY_DAYS`/`HISTORY_COLS` constants (near `DEFAULT_FEATURE_PAIRS`, ~line 81), add `plot_history_line` (near `plot_two_lines`, ~line 247), add `run_history` (near `compute_windows`, ~line 1069), add the `run_history` call in `main` (after the counterfactual loop from Task 2), and update the header docstring + `--short` usage line.
- Test: `row-diagnostic/test_station_analysis.py` — add `hist_data` fixture + history integration tests (end of the `--short` section, ~line 496).

**Interfaces:**
- Consumes: `series_from_lists_history` (Task 1), `window_mask(idx, win)`, `night_mask(idx, drop_night, night_end_hour)`, `_station_dir`, `sanitize`, `_cn_font`; `report_root` (Task 2).
- Produces: `run_history(inp, args, step, out_dir) -> None` (plots only, no return); `plot_history_line(st, name, times, vals, out_dir, tick_hours) -> str` (PNG path).

- [ ] **Step 1: Write the failing integration tests**

Add to `row-diagnostic/test_station_analysis.py`, at the end of the `--short` section:

```python
@pytest.fixture
def hist_data(tmp_path):
    """起报 T=2026-07-26 10:00. Historical list cols observe_power/GHI_SOLARGIS: 7-day (672-pt, 15min)
    lists whose LAST element sits at T. Forward observe_power_future + predict cover D+1/D+4 so --short's
    metric pass also runs without crashing."""
    T = pd.Timestamp("2026-07-26 10:00:00")
    n_hist, n_fut = 672, 480
    hist_power = {"s1": [float(k) for k in range(n_hist)], "s2": [float(k + 1000) for k in range(n_hist)]}
    hist_ghi = {"s1": [float(2 * k) for k in range(n_hist)], "s2": [float(2 * k + 1) for k in range(n_hist)]}
    fut = {"s1": [float(10 + (k % 96)) for k in range(n_fut)], "s2": [float(5 + (k % 96)) for k in range(n_fut)]}
    rows = [{"station": st, "timestamp_win": T, "observe_power_future": fut[st],
             "observe_power": hist_power[st], "GHI_SOLARGIS": hist_ghi[st]} for st in ("s1", "s2")]
    pd.DataFrame(rows).to_parquet(tmp_path / "input.parquet")
    times = [T + pd.Timedelta(minutes=15 * (k + 1)) for k in range(n_fut)]
    pred = pd.DataFrame({"dtime": times})
    for st in ("s1", "s2"):
        pred[st] = fut[st]
    pred.to_parquet(tmp_path / "predict.parquet")
    return tmp_path


def test_history_plots_per_station(hist_data):
    r = _run_short(hist_data, ["--pred-col-template", "{station}", "--no-fleet"])
    hd = _rep(hist_data) / "history" / "stations"
    assert (hd / "station_s1_observe_power.png").exists()
    assert (hd / "station_s1_GHI_SOLARGIS.png").exists()
    assert (hd / "station_s2_observe_power.png").exists()
    assert (hd / "station_s2_GHI_SOLARGIS.png").exists()
    assert "[history] observe_power: 2 plotted, 0 skipped" in r.stdout


def test_history_no_plots_flag_skips(hist_data):
    r = _run_short(hist_data, ["--no-plots", "--pred-col-template", "{station}"])
    assert not (_rep(hist_data) / "history").exists()
    assert "[history] skipped" in r.stdout


def test_history_missing_column_warns(short_data):
    # short_data has no observe_power / GHI_SOLARGIS columns -> history warns per missing col, no crash
    r = _run_short(short_data, ["--no-fleet", "--pred-col-template", "{station}"])
    assert "[history] column 'observe_power' missing" in r.stdout
    assert "[history] column 'GHI_SOLARGIS' missing" in r.stdout
```

- [ ] **Step 2: Run to verify they fail**

Run: `cd row-diagnostic && python -m pytest test_station_analysis.py -k history -v`
Expected: FAIL — `run_history` not called / `[history]` lines absent / PNGs missing.

- [ ] **Step 3: Add constants**

In `row-diagnostic/station_analysis.py`, just below `DEFAULT_FEATURE_PAIRS` (~line 81):

```python
HISTORY_DAYS = 2                                  # --short history plots: how many days back from 起报时间 T
HISTORY_COLS = ["observe_power", "GHI_SOLARGIS"]  # historical (past-observed) list columns to plot
```

- [ ] **Step 4: Add `plot_history_line`**

In `row-diagnostic/station_analysis.py`, after `plot_two_lines` (after its `return path`, ~line 247):

```python
def plot_history_line(st, name, times, vals, out_dir, tick_hours):
    """Single-line history plot (no truth/pred pair, no RMSE). Saved to <out_dir>/stations/."""
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.dates as mdates
    import matplotlib.pyplot as plt
    _cn_font()

    times = pd.DatetimeIndex(times)
    n_hours = max(1.0, (times[-1] - times[0]).total_seconds() / 3600.0)
    width = min(60.0, max(16.0, n_hours * 0.3))
    fig, ax = plt.subplots(figsize=(width, 6))
    ax.plot(times, vals, color="#1f77b4", lw=1.3, label=name)
    ax.set_title(f"Station {st}  -  {name} (history)   "
                 f"{times[0]:%Y-%m-%d %H:%M} -> {times[-1]:%Y-%m-%d %H:%M}   (n={len(times)})",
                 fontsize=13, fontweight="bold")
    ax.xaxis.set_major_locator(mdates.HourLocator(interval=max(1, int(tick_hours))))
    ax.xaxis.set_major_formatter(mdates.DateFormatter("%m-%d %H:%M"))
    plt.setp(ax.get_xticklabels(), rotation=90, fontsize=7)
    ax.set_xlabel("time"); ax.set_ylabel(name); ax.legend(loc="upper right"); ax.grid(alpha=0.25)
    fig.tight_layout()
    path = os.path.join(_station_dir(out_dir), f"station_{sanitize(st)}_{sanitize(name)}.png")
    fig.savefig(path, dpi=110); plt.close(fig)
    return path
```

- [ ] **Step 5: Add `run_history`**

In `row-diagnostic/station_analysis.py`, just before `compute_windows` (~line 1051):

```python
def run_history(inp, args, step, out_dir):
    """--short only: per-station single-line plots of HISTORY_COLS over the last HISTORY_DAYS days,
    ending at 起报时间 T = max(timestamp_win). Plots only -- no metrics, no CSV. Each station x column
    succeeds/fails independently (empty in window -> warn + skip that one PNG)."""
    if args.no_plots or args.no_station_plots:
        print("  [history] skipped (--no-plots/--no-station-plots)")
        return
    cols = []
    for c in HISTORY_COLS:
        if c in inp.columns:
            cols.append(c)
        else:
            print(f"  [history] column '{c}' missing from input table -> skipped")
    if not cols:
        return
    os.makedirs(out_dir, exist_ok=True)
    T_end = pd.Timestamp(inp[args.win_col].max())
    win = (T_end - pd.Timedelta(days=HISTORY_DAYS), T_end + step)   # end-exclusive -> keeps up to and incl. T_end
    stations = sorted(inp[args.station_col].unique(), key=str)
    if args.worst_only:
        print(f"  [history] --worst-only ignored (history has no nRMSE ranking); drawing all {len(stations)} stations")
    summary = {c: [0, 0] for c in cols}                            # col -> [plotted, skipped]
    for st in stations:
        sub = inp[inp[args.station_col] == st].sort_values(args.win_col)
        for c in cols:
            s = series_from_lists_history(sub[args.win_col].to_numpy(), sub[c].to_numpy(), step)
            if not s.empty:
                keep = window_mask(s.index, win) & night_mask(s.index, args.drop_night, args.night_end_hour)
                s = s[keep]
            if s.empty:
                print(f"  [warn] station {st}: history '{c}' empty in window, skipped")
                summary[c][1] += 1
                continue
            plot_history_line(st, c, s.index, s.to_numpy(), out_dir, args.tick_hours)
            summary[c][0] += 1
    print("  [history] " + "; ".join(f"{c}: {p} plotted, {k} skipped" for c, (p, k) in summary.items()))
```

- [ ] **Step 6: Wire `run_history` into `main`**

In `row-diagnostic/station_analysis.py`, immediately after the `if args.counterfactual:` loop from Task 2 (before `main`'s end / the `if __name__` guard):

```python
    if args.short:
        run_history(inp, args, step, os.path.join(report_root, "history"))
```

- [ ] **Step 7: Run history tests to verify they pass**

Run: `cd row-diagnostic && python -m pytest test_station_analysis.py -k history -v`
Expected: PASS (3 tests).

- [ ] **Step 8: Update the header docstring + usage line for history**

In `row-diagnostic/station_analysis.py`:

Add a `[History]` blurb after the `[Counterfactual]` section of the module docstring (~after line 41):

```
[History] (--short only) Per-station single-line plots of the historical (past-observed) columns
  observe_power and GHI_SOLARGIS, last 2 days ending at 起报时间 T (the list's last element sits at T,
  stepping back 15min per element). Plots only -- no metrics/CSV. Written to <report>/history/stations/.
```

Update the `--short` usage line (~line 69) to mention history:

```
    [--short [--date 2026-07-26]]   # 短期：<out>/<起报日>/ 下 D+1、D+4 各一套产物 + history 两日历史曲线
```

- [ ] **Step 9: Run the full suite**

Run: `cd row-diagnostic && python -m pytest test_station_analysis.py -v`
Expected: PASS (all tests green).

- [ ] **Step 10: Commit**

```bash
git add row-diagnostic/station_analysis.py row-diagnostic/test_station_analysis.py
git commit -m "feat(station_analysis): --short history/ per-station 2-day observe_power & GHI_SOLARGIS plots"
```

---

## Self-Review

**Spec coverage:**
- Report root named by 起报日 with D+1/D+4/history inside → Task 2 (nesting) + Task 3 (history dir). ✓
- History columns observe_power + GHI_SOLARGIS, list ending at 起报时间 T → Task 1 (reversed time-base) + Task 3 (`run_history`). ✓
- Last 2 days only → Task 3 (`HISTORY_DAYS`, `window_mask`). ✓
- One PNG per feature per station → Task 3 (`plot_history_line`, per-column loop). ✓
- No statistical analysis → Task 3 (`run_history` plots only, no CSV/metrics). ✓
- `--short`-gated, skip+warn robustness → Task 3 (gate + per-station/per-column warnings). ✓
- Run-level logging of skips → Task 3 (`[history] <col>: N plotted, M skipped`). ✓

**Placeholder scan:** No TBD/TODO/"handle edge cases"; every code step carries full code. ✓

**Type consistency:** `series_from_lists_history(wins, lists, step)`, `plot_history_line(st, name, times, vals, out_dir, tick_hours)`, `run_history(inp, args, step, out_dir)`, `compute_windows -> (report_name, windows)`, `report_root` — names identical across tasks and `main`. ✓
