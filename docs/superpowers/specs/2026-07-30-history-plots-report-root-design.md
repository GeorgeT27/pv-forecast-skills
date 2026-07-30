# Design: `history/` per-station plots + `<起报日>` report root

Date: 2026-07-30
Target file: `row-diagnostic/station_analysis.py`
Depends on: existing `--short` mode (D+1 / D+4 slicing).

## Goal

In `--short` mode, additionally plot the **historical** (past, observed) series for each
station — `observe_power` and `GHI_SOLARGIS` — as single-line per-station PNGs, and group
D+1 / D+4 / history under one report directory named by the 起报日 (e.g. `20260726`).
No statistics for history: plots only.

Motivation: `observe_power` / `GHI_SOLARGIS` are the historical counterparts of the forecast
columns `observe_power_future` / `GHI_SOLARGIS_predict`. Their lists span ~7 days, which is too
long to read on one chart, so we display only the last **2 days**.

## Decisions (locked with user)

1. **Directory layout:** insert a 起报日 level under `--out-dir`; D+1/D+4/history nest inside.
2. **History time-base:** each cell's list ends at 起报时间 `T = timestamp_win`; element `i` of
   length-`L` list → `T − step·(L−1−i)`, so `list[-1] → T`. Plot window = `[T − 2 days, T]`.
3. **Plot layout:** one PNG per feature (2 files per station).
4. **Columns / gating:** fixed columns `observe_power`, `GHI_SOLARGIS`; produced only in `--short`
   mode; per-station skip+warn on missing/empty (same robustness contract as feature plots).

## Target directory layout

```
out_dir/
  20260726/                        report root = D.strftime("%Y%m%d")
    D+1/     stations/*.png + CSVs  (unchanged content, moved one level down)
    D+4/     stations/*.png + CSVs  (unchanged content, moved one level down)
    history/ stations/*.png         NEW — plots only, no CSV
```

Non-`--short` runs are unchanged: no report level, no `history/`.

## Components

### `series_from_lists_history(wins, lists, step)` (new)

Mirror of `series_from_lists`, but the list runs **backwards**: for a cell with
`timestamp_win = t0` and finite-value array of length `L`, element `i` maps to
`t0 − step·(L−1−i)` (so `[-1] → t0`, `[-2] → t0 − step`). Same non-finite skip, same
flatten → groupby-time → mean → sort. Returns empty series for a station missing the column.

### `run_history(inp, args, step, out_dir)` (new)

- Module constants: `HISTORY_DAYS = 2`, `HISTORY_COLS = [("observe_power", ...), ("GHI_SOLARGIS", ...)]`.
- Globally-missing column → warn once and drop it (mirror of the feature-pair guard around
  `main`'s `active_pairs` construction).
- Global endpoint `T_end = max(inp[win_col])`; window `[T_end − HISTORY_DAYS days, T_end]`
  applied via existing `window_mask` (end set to `T_end + step`, exclusive, to include `T_end`).
  `--drop-night` still honored via `night_mask` if set.
- Per station × per remaining column: build reversed series, restrict to window; empty →
  `[warn] station <st>: history '<col>' empty in window, skipped`; else draw one line.
- Purely visual: if `--no-plots` or `--no-station-plots`, skip history entirely and log it.
- `--worst-only` is **ignored** for history (no nRMSE to rank on); all stations drawn, logged once.

### `plot_history_line(st, name, series, out_dir, tick_hours)` (new)

Trimmed `plot_two_lines`: single line, no fill, no RMSE. Title
`Station <st> — <name>   <start> → <end=T>   (n=<points>)`. Auto-width by span (reuse existing
formula). Saves to `<out_dir>/stations/station_<sanitize(st)>_<sanitize(col)>.png`
(`_station_dir` already routes to `<out_dir>/stations/`).

### `compute_windows` / `main` changes

- `compute_windows` returns `(report_name, windows)`: `report_name = D.strftime("%Y%m%d")` in
  `--short`, else `None`.
- `main` builds `report_root = out_dir` (non-short) or `out_dir/<report_name>` (short), then:
  - runs the existing `run_analysis` loop with `sub_out` hung off `report_root`;
  - runs the existing `run_counterfactual` loop off `report_root`;
  - if `--short`: calls `run_history(inp, args, step, os.path.join(report_root, "history"))`.

## Logging

After the history loop, one summary line per column:
`[history] observe_power: <N> plotted, <M> skipped (<reason breakdown>); GHI_SOLARGIS: ...`
so run-level visibility of skips, not only per-station warnings.

## Robustness

Each station × column plot succeeds or fails independently (existing contract). A missing column,
an empty list, or an out-of-window series skips only that one PNG with a warning; every other
station/column and the D+1/D+4 outputs are unaffected.

## Testing

Update the existing `--short` smoke test (introduced in commit `9fbcc09`):
- paths move from `out_dir/D+{1,4}` to `out_dir/<YYYYMMDD>/D+{1,4}`;
- add existence check for `out_dir/<YYYYMMDD>/history/stations/*.png`;
- add a reversed-endpoint unit assertion: for a known synthetic history list, the last element
  lands at `timestamp_win` and the series is restricted to the 2-day window.

## Rejected alternative

Folding history into `run_analysis` as a third window tuple. Rejected: `run_analysis` computes
power true/pred metrics, feature RMSE, fleet overview, Theil and scatter — none wanted here — and
its time-base is forward-only. A separate, isolated `run_history` (~40 lines) is cleaner.
