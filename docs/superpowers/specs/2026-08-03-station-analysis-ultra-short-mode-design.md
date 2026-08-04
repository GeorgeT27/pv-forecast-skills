# Design: `--ultra-short` mode + unified `--timestamp` (drop `--date`)

**Date:** 2026-08-03
**Target file:** `短期分析/station_analysis_short.py`
**Tests:** `短期分析/test_station_analysis_short.py`
**Docs:** `短期分析/README.md`
**Status:** SUPERSEDED by `2026-08-04-station-analysis-ultra-short-16lead-design.md` — the
ultra-short input model here (single 192-point-list parquet, single-window reuse of
`run_analysis`) and the unified mandatory `--timestamp` are both obsolete. Do not implement.

## Problem

The committed `station_analysis_short.py` is a mid-refactor WIP: the report-day directory +
`D+1`/`D+4` slicing + `history/` are **unconditional** (no `--short` flag), and the previously
designed `--short`, `--date`, and `--pred-col-template` args were dropped. As a result the
existing `test_station_analysis_short.py` suite is **red** — both the plain-mode tests (`_run`,
no flag) and the `--short` tests (`_run_short`) fail against the current file.

We now also need a second, shorter forecast horizon — **ultra-short** — where a forecast issued
at 起报时间 `T` produces input list columns of **192 points** (48h at 15-min step, first element
`T+00:15`, last `T+48:00`) instead of the short-mode 480. There are no `D+1`/`D+4` horizon
slices for ultra-short; we want a single window covering the whole 192-point series, aligned
against the predict table.

## Goal

Re-introduce an explicit mode gate and add ultra-short, under one **unified, mandatory
`--timestamp`**:

- Exactly one of `--short` / `--ultra-short` is required. Neither, or both, → `SystemExit`.
- `--timestamp "YYYY-MM-DD HH:MM:SS"` (起报时间 `T`) is **always required** in both modes.
- `--date` is **removed** — `--timestamp` subsumes it. The old "auto-infer D from data /
  `using D = …`" fallback is removed too (timestamp is now mandatory).

Ultra-short reuses the entire existing per-station + fleet pipeline over a single window.

Non-goals: no change to the parquet input schema; no new chart types; no 南网 `nanwang_official`
metric in ultra-short.

## Decisions (locked with user)

1. **Mode model.** `--short` XOR `--ultra-short`, both consume the same mandatory `--timestamp`
   (full datetime). Plain no-flag mode is **gone** (was the old default) — see Test
   reconciliation for how the plain-mode tests migrate.
2. **`--short` semantics.** `D = pd.Timestamp(args.timestamp).normalize()` (date part). The time
   part is the recorded 起报时间 (informational). `D+1`/`D+4`/`history` exactly as today, under
   the report-day root `<out>/<D:%Y%m%d>/`.
3. **`--ultra-short` semantics.** `T = pd.Timestamp(args.timestamp)`. A **single window** covering
   the whole series (`win=None` — no D+1/D+4). Output → `<out>/<T:%Y%m%d>/ultra_short/`.
   Report-day dir uses `%Y%m%d` for parity with `--short` (same-day intraday 起报 would collide;
   accepted for now).
4. **Alignment.** Unchanged. Per-station Power compares input `observe_power_future` (flattened,
   element k → `timestamp_win + step·(k+1)`) against predict-table `predict_power_{station}`
   (dtime-indexed) via `_aligned()` **intersection** of absolute timestamps → exactly the
   overlapping points (192 for ultra-short). Metrics use the intersection; plotted lines use
   `_display()` union + fill-0 so gaps stay visible. No flattener change — ultra-short's
   length-192 lists flatten through the same `series_from_lists`.
5. **Per-station charts (both modes, unchanged).** Each station gets:
   - `stations/station_<st>_Power.png` — observed vs predicted power (crosses input↔predict).
   - `stations/station_<st>_GHI.png` — `GHI_SOLARGIS_predict` vs `GHI_real_future` (default
     feature pair; **both from input** = feature-quality plot, not model output).
   - `stations/station_<st>_scatter.png` — true-vs-pred power scatter (kept).
6. **Ultra-short history.** Included when `observe_power` / `GHI_SOLARGIS` columns are present,
   anchored at `T` (window `[T − 2 days, T]`), written to `<out>/<T:%Y%m%d>/ultra_short/history/`.
7. **Ultra-short 南网 metric.** Skipped — ultra-short does not compute `nanwang_official`
   (do not thread `--info-csv` gccap into the ultra-short pipeline).
8. **`--pred-col-template`.** Restored; default `predict_power_{station}`. Threaded into
   `resolve_pred_col(st, pred, template)` (currently hardcoded `predict_power_{st}`).
9. **Sanity warning.** Ultra-short warns (does not fail) if the earliest flattened input time
   ≠ `T + 15min` (catches a wrong `--timestamp`).

## Target directory layout

```
out_dir/
  <YYYYMMDD>/                         report root = timestamp date part
    # --short:
    D+1/       stations/*.png + CSVs + fleet_overview.png + theil_decomposition.png
    D+4/       stations/*.png + CSVs + fleet_overview.png + theil_decomposition.png
    history/   stations/*.png                              (plots only)
    # --ultra-short:
    ultra_short/
      stations/*.png (Power + GHI + scatter per station)
      station_power_rmse.csv, station_feature_rmse.csv, fleet_ranking.csv
      fleet_overview.png, theil_decomposition.png
      history/ stations/*.png                              (when columns present)
      counterfactual_results.csv, counterfactual_overview.png   (with --counterfactual)
```

## Changes

### 1. CLI (`main`)
- Add `--short` (`action="store_true"`).
- Add `--ultra-short` (`action="store_true"`).
- Add `--timestamp` (`required=True`), help: 起报时间 `YYYY-MM-DD HH:MM:SS`.
- Add `--pred-col-template` (`default="predict_power_{station}"`).
- **Remove** `--date`.
- Validate mode: exactly one of `--short` / `--ultra-short`, else
  `raise SystemExit("choose exactly one of --short / --ultra-short")`.

### 2. `resolve_pred_col(st, pred, template)`
Format `template` with `station=st` (support `{station}` placeholder) → column name; return it if
present in `pred.columns`, else `None`. Update both call sites (`run_analysis`, `run_counterfactual`)
to pass `args.pred_col_template`.

### 3. `compute_windows` — short only
```
def compute_windows(inp, win_col, timestamp):
    D = pd.Timestamp(timestamp).normalize()
    day = pd.Timedelta(days=1)
    d1, d4 = D + day, D + 4*day
    return D.strftime("%Y%m%d"), [("D+1", d1, d1 + day), ("D+4", d4, d4 + day)]
```
(Drops the data-derived / `--date` branch; `timestamp` is mandatory.)

### 4. `main` dispatch
```
T = pd.Timestamp(args.timestamp)
report_name = T.strftime("%Y%m%d")
report_root = os.path.join(args.out_dir, report_name)
os.makedirs(report_root, exist_ok=True)

if args.short:
    _, windows = compute_windows(inp, args.win_col, args.timestamp)
    for label, start, end in windows:
        sub_out = os.path.join(report_root, label); os.makedirs(sub_out, exist_ok=True)
        run_analysis(..., gccap_map, sub_out, (start, end), label)
    if args.counterfactual:
        for label, start, end in windows:
            run_counterfactual(..., out_dir=os.path.join(report_root, label),
                               win=(start, end), gccap_map=gccap_map)
    run_history(inp, args, step, os.path.join(report_root, "history"))
else:  # ultra-short
    us_dir = os.path.join(report_root, "ultra_short"); os.makedirs(us_dir, exist_ok=True)
    _warn_if_first_point_off(inp, args, step, T)          # sanity warning, non-fatal
    run_analysis(..., gccap_map={}, us_dir, win=None, label="ultra-short")
    if args.counterfactual:
        run_counterfactual(..., out_dir=us_dir, win=None, gccap_map={})
    run_history(inp, args, step, os.path.join(us_dir, "history"))   # T-anchored via data
```
`run_analysis` / `run_counterfactual` / `run_history` signatures are unchanged from the current
file (they already accept `out_dir` + `win`); ultra-short simply passes `win=None` and an empty
`gccap_map` (decision 7).

### 5. Sanity helper (`_warn_if_first_point_off`)
Flatten one station's `power_col` (or first available list column) and warn if
`series.index.min() != T + step`.

## Test reconciliation (get the suite green)

Root cause of the current red suite: tests assume plain no-flag mode + a `predict_power`-free
column layout, both removed by the WIP.

1. **Core logic tests (`_run`-based: rmse/overlap/night/feature/fleet).** Migrate onto
   `--ultra-short --timestamp <fixture 起报时间>` — a single `win=None` window is semantically
   identical to the old plain single-pass, so their RMSE / dedup / night assertions hold. Update
   the `_run` helper to add `--ultra-short --timestamp …` and read from
   `out/<YYYYMMDD>/ultra_short/` (via a small path helper). Fixtures with bare `station1`/`s1`
   predict columns pass `--pred-col-template {station}`.
2. **`test_default_no_short_folders`.** Replace with `test_requires_a_mode`: no `--short`/
   `--ultra-short` → non-zero exit + error message.
3. **`--short` tests (`test_short_*`).** Keep, but replace `--date YYYY-MM-DD` with
   `--timestamp "YYYY-MM-DD 10:00:00"`; drop the `using D = …` fallback assertion
   (`test_short_makes_two_folders_96pts`).
4. **New ultra-short tests.**
   - Output lands under `ultra_short/`, not `D+1`/`D+4`.
   - Single window over a 192-point (or fixture-sized) list → point count matches the
     input∩predict intersection.
   - Per-station Power + GHI + scatter PNGs emitted.
   - History PNGs emitted when `observe_power`/`GHI_SOLARGIS` present; absent otherwise.
   - No `nanwang_official*` columns even when `--info-csv` is passed.

## README

Rewrite the mode section to document `--short` / `--ultra-short` (exactly one) + mandatory
`--timestamp`; remove `--date`; add the `ultra_short/` layout and the "GHI plot = feature-quality,
Power plot = model output" distinction.

## Approach note

Reuses the existing `_aligned()` window choke-point and the `run_analysis(out_dir, win)` seam
already present in the file. Ultra-short adds no new metric/chart code — it is a new dispatch
branch (`win=None`, `gccap_map={}`) plus CLI wiring. The only genuinely new helper is the
first-point sanity warning.
