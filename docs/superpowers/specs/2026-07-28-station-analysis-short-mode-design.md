# station_analysis.py `--short` mode — design

**Date:** 2026-07-28
**File:** `row-diagnostic/station_analysis.py`
**Status:** approved for planning

## Problem

Today `station_analysis.py` analyzes the **entire** flattened time series per station (all
points in every list column, aligned to the predict table). For the short-term forecasting
workflow we instead want to look at two specific 24-hour horizon slices of a single forecast
and produce a full set of charts for **each** slice.

Concretely, a forecast is issued (起报) at **D 10:00:00**. Each input list column holds **480
points** at 15-min step, so:

- element 1 = D 10:15:00, element 2 = D 10:30:00, … element 480 = **(D+5) 10:00:00**.

We want to evaluate two horizon windows of that forecast:

- **D+1 slice** — 24h starting **(D+1) 00:00:00** (= D 10:00 + 14h → element 56; slice = elements 56–151 = **96 points**, 00:00…23:45).
- **D+4 slice** — 24h starting **(D+4) 00:00:00** (= D 10:00 + 86h → element 344; slice = elements 344–439 = **96 points**).

Both slices sit well inside the 480-point horizon.

## Goal

Add a `--short` flag that, when set, produces **two complete output sets** — one per horizon
slice (D+1 and D+4) — instead of one full-series set. Everything the tool produces today gets
doubled: per-station Power curves, per-station feature curves, per-station scatter, the fleet
overview dashboard, the Theil decomposition, all CSVs, and (when `--counterfactual` is on) the
counterfactual outputs. Each output is computed **only** on its 96-point slice.

Non-goals: no change to default (non-`--short`) behavior; no change to the parquet input schema;
no new chart types.

## Key decisions (settled during brainstorming)

1. **Anchor "D".** New optional `--date YYYY-MM-DD`.
   - If given: `D = --date`.
   - If omitted in `--short`: `D = date(min(timestamp_win))` from the input table, and the code
     prints which date it used. (`timestamp_win` is assumed to equal the 起报时间 `D 10:00:00`.)
2. **Slices.** `d1_start = D + 1 day @ 00:00`, `d4_start = D + 4 days @ 00:00`. Each window is
   the half-open interval `[start, start + 24h)` → exactly 96 points at 15-min step. The point at
   the next midnight belongs to the following day, not this slice.
3. **Scope.** Everything doubled (per-station + fleet + Theil + scatter + all CSVs + counterfactual).
4. **Output layout.** `<out-dir>/D+1/` and `<out-dir>/D+4/`, each with the **same internal
   structure** as today's `<out-dir>` (root pngs + CSVs, `stations/` subdir for per-station pngs).
5. **worst-only.** The existing `--worst-only N` already restricts images to the worst N stations;
   in `--short` it ranks **within each slice** (fleet metrics are recomputed per slice) and limits
   images to that slice's worst N. CSVs still cover all stations. No new argument.

## Approach

**Rejected:** physically slicing `input`/`predict` to a 24h window before running the existing
pipeline. The predict table (dtime-indexed) is sliceable, but the **input** table is not: each
`timestamp_win` row carries list columns spanning ~5 days, so a 24h view cannot be obtained by
dropping rows — it would require trimming inside every list cell.

**Chosen:** apply a **time-window mask at the alignment choke point**. Both the truth series (from
input lists) and the predicted series (from the predict table) already pass through `_aligned()`,
which intersects their timestamps and applies the night filter. Adding an optional
`win=(start, end)` filter there masks **both sides identically** with one change. Every downstream
metric and chart (RMSE, nRMSE, Theil, scatter, hourly heatmap) is derived from the already-masked
aligned points, so they all restrict automatically — no per-chart edits. This is why "editing the
input" needs no input-specific code: the shared mask handles it.

## Changes

### 1. New CLI args (`main`)
- `--short` (`action="store_true"`).
- `--date` (`default=None`), help: 起报 date `YYYY-MM-DD`; D+1/D+4 counted from this. `--short` only.

### 2. Window computation (`main`, new helper)
```
def compute_windows(args, inp):
    if not args.short:
        return [(None, None, None)]                 # single full-series pass -> out_dir directly
    if args.date:
        D = pd.Timestamp(args.date).normalize()
    else:
        D = pd.Timestamp(inp[args.win_col].min()).normalize()
        print(f"  [short] --date not given; using D = {D:%Y-%m-%d} (from earliest {args.win_col})")
    day = pd.Timedelta(days=1)
    d1 = D + 1*day
    d4 = D + 4*day
    return [("D+1", d1, d1 + day), ("D+4", d4, d4 + day)]
```
`inp[args.win_col]` is already converted to datetime before this call.

### 3. Filtering choke point
- `_aligned(a, b, drop_night, night_end_hour, win=None)` — after the night mask, if `win` is not
  None, additionally keep only `start <= t < end`. Return `None` when nothing remains (existing
  contract: caller warns + skips).
- `cf_metrics(p_true, p_base, p_cf, drop_night, night_end_hour, cap, win=None)` — same filter
  applied to its 3-series common index.

### 4. Extract `run_analysis(...)` from `main`
Move the per-station loop + `--worst-only` selection + station CSV writes + fleet overview + Theil
+ terminal summary (current lines ≈ 899–1085) into:
```
def run_analysis(inp, pred, args, step, active_pairs, have_ghi, cap_map, out_dir, win):
    ...
```
- All `os.path.join(args.out_dir, ...)` become `os.path.join(out_dir, ...)`.
- All `_aligned(...)` calls pass `win=win`.
- `_station_dir(out_dir)` already takes the dir; pass the per-window `out_dir`.
- Terminal summary prints a `[D+1]` / `[D+4]` prefix (or full-series when `win is None`) so the two
  passes are distinguishable in the log.

`main` keeps: arg parsing, parquet load + column validation, datetime coercion, predict groupby,
`active_pairs` / `have_ghi` computation, then:
```
os.makedirs(args.out_dir, exist_ok=True)
for label, start, end in compute_windows(args, inp):
    sub_out = args.out_dir if label is None else os.path.join(args.out_dir, label)
    os.makedirs(sub_out, exist_ok=True)
    run_analysis(inp, pred, args, step, active_pairs, have_ghi, cap_map,
                 sub_out, (start, end) if label else None)
if args.counterfactual:
    for label, start, end in compute_windows(args, inp):
        sub_out = args.out_dir if label is None else os.path.join(args.out_dir, label)
        run_counterfactual(inp, pred, args, cap_map, step,
                           out_dir=sub_out, win=(start, end) if label else None)
```

### 5. Counterfactual per-window
- `run_counterfactual(..., out_dir=None, win=None)` — default `out_dir = args.out_dir` to preserve
  the current call. Its `csv_path`, curve pngs, and overview png go under `out_dir`; `cf_metrics`
  receives `win`. Resumability keys off the per-folder `counterfactual_results.csv`, so D+1 and D+4
  resume independently.

## Data-flow (per window, unchanged except the mask)

```
input.parquet  --series_from_lists-->  truth series (absolute time, all 480 pts)   \
                                                                                     >-- _aligned(win) --> 96 aligned pts --> metrics/charts
predict.parquet --groupby(dtime)-->     pred series (absolute time)                 /
```

## Testing

Extend the existing demo generator to emit a realistic short-mode fixture:
- `timestamp_win = D 10:00:00`, one window per station, list length **480**, 15-min step.
- predict table dtime covering at least D+1 and D+4 (00:00…23:45 on each).

Then assert:
1. `--short` (no `--date`) creates `out/D+1/` and `out/D+4/`, each with `stations/`,
   `fleet_overview.png`, `theil_decomposition.png`, `fleet_ranking.csv`, `station_power_rmse.csv`.
2. `station_power_rmse.csv` in each folder reports `n_points == 96` per station.
3. Printed line shows the auto-derived D matches the fixture's issue date; `--date` override changes
   which slice is analyzed.
4. Default run (no `--short`) is byte-for-behavior identical to before (writes straight to
   `out/`, no `D+1`/`D+4` subdirs) — regression guard.
5. `--short --worst-only 2` restricts images in each slice to 2 stations; CSVs still list all.
6. Robustness: a station whose predict table lacks the D+4 dates is skipped for D+4 only (warning),
   D+1 still produced.

## Risks / assumptions

- **`timestamp_win` = 起报时间 (D 10:00).** The auto-fallback depends on this; `--date` is the escape
  hatch if not.
- **Grid alignment.** A 10:00 issue at 15-min step lands exactly on 00:00 marks, so D+1/D+4 midnights
  exist in the flattened series. Non-15-min steps or non-:00/:15/:30/:45 issue minutes could miss the
  exact midnight; `_aligned` intersection handles it gracefully (fewer points, warning) rather than
  crashing.
- **Predict coverage.** The predict table must contain the D+1 / D+4 dates or those slices are empty
  (existing skip-with-warning behavior).
