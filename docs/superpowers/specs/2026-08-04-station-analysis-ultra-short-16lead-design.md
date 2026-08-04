# Design: `station_analysis_ultra_short.py` (16-lead reconstruction) + short-script `--date` restore

**Date:** 2026-08-04
**Supersedes:** `2026-08-03-station-analysis-ultra-short-mode-design.md` (ultra-short input model
and the unified `--timestamp` idea are both obsolete)
**Target files:** new `短期分析/station_analysis_ultra_short.py`; existing
`短期分析/station_analysis_short.py` (arg restore only)
**Tests:** `短期分析/test_station_analysis_short.py` (reconcile) + new
`短期分析/test_station_analysis_ultra_short.py`
**Status:** approved for planning

## Problem

Ultra-short forecasting issues a forecast every 15 minutes. Each 起报 S produces a small predict
parquet (~20 rows from S+15min) of which only the **first 16 points** matter (targets S+15min …
S+4h). Evaluating "the forecast for day D" therefore means **reconstructing constant-lead curves
across many 起报 files** — a completely different data layout from the short mode's single
480-point-list parquet. The two workflows share almost no I/O, so they get **two scripts**.

## Decisions (locked with user)

1. **Two scripts.** `station_analysis_short.py` stays as-is behaviorally (unconditional
   report-day + `D+1`/`D+4` + `history/`); no `--short`, no `--timestamp`. It only gets
   `--date YYYY-MM-DD` restored (override 起报日; else auto-infer from data with a
   `using D = …` announcement) and `--pred-col-template` restored (default
   `predict_power_{station}`). New `station_analysis_ultra_short.py` handles ultra-short.
2. **Ultra-short CLI.** `--input-dir` (root containing `date=YYYY-MM-DD/` partitions),
   `--predict-dir` (flat dir of per-起报 predict parquets), `--date YYYYMMDD` (the day to plot;
   target grid = D 00:00 → 23:45, 96 points), `--out-dir`, plus reused `--drop-night`,
   `--night-end-hour`, `--tick-hours`, `--station-col`.
3. **Prediction = 16 constant-lead lines per station.**
   - Each predict parquet: same shape as short's predict table — `dtime` column + one column per
     station (`predict_power_{station}` via `--pred-col-template`). Filename carries 起报时间 as
     a `YYYYMMDDHHMM` token (e.g. `hw_nuoya_202607231700_ultra_short_…parquet`).
   - For target t, the 16 contributing 起报 are S = t−4h … t−15min. Label **p1 = oldest 起报
     (lead 16, 4h-ahead) … p16 = newest (lead 1, 15min-ahead)**; p_j = lead (17−j).
   - Required 起报 range for day D: **D−1 20:00 → D 23:30** (111 起报). Files outside the range
     (e.g. D+1) are ignored.
   - Per station, build a 96×16 lead matrix indexed by target time; each column plotted as one
     line.
4. **Truth + GHI = lead-1 sampling of the input partitions.**
   - Layout: `<input-dir>/date=YYYY-MM-DD/time=HH:MM/<single parquet>`; `time=HH:MM` is the
     起报时间. Parquet schema = short input (rows = station, list columns, length 192 = 48h).
   - From each 起报 dir take **`list[0]` only** (value at 起报+15min) of `observe_power_future`
     (true power), `GHI_real_future` (true GHI), `GHI_SOLARGIS_predict` (lead-1 GHI forecast).
   - Value at target t ← dir `time = t−15min`: target D 00:00 ← `date=D−1/time=23:45`; targets
     D 00:15…23:45 ← `date=D/time=00:00…23:30` (96 dirs total).
5. **Plots per station** (into `stations/`):
   - `station_<st>_Power.png` — **17 lines**: true power (bold) + p1…p16 on a sequential
     colormap (light = p1/4h-ahead → dark = p16/15min-ahead), x = 00:00–23:45.
   - `station_<st>_GHI.png` — **2 lines**: lead-1 `GHI_SOLARGIS_predict` vs `GHI_real_future`
     (GHI does *not* get 16 lines — only `list[0]` is read).
6. **Metrics: minimal, plots are the deliverable.**
   - `station_power_rmse.csv` — one row per station: pooled RMSE over all (lead, target) pairs
     with both prediction and truth present, plus n_points; sorted desc (doubles as ranking).
   - `station_feature_rmse.csv` — lead-1 GHI RMSE per station.
   - **No** scatter, Theil, fleet dashboard, counterfactual, history, or 南网 metric in v1.
7. **File matching: glob by token, not exact names** (observed name drift: gunagxi/porvince/
   SOLARGIST). Predict: `*<YYYYMMDDHHMM>*.parquet` in `--predict-dir`; input: the single
   `*.parquet` inside each `time=HH:MM/` dir. 0 matches → missing-起报 handling; >1 → error.
8. **Missing 起报 → warn + gap.** Warn once per missing file/dir; leave NaN gaps in the affected
   line(s)/truth points; metrics use available points only. Never abort.
9. **Station universe** = stations present in predict columns ∩ stations in input parquets;
   warn on either-side-only stations.

## Target directory layout

```
out_dir/
  <YYYYMMDD>/                      report root = --date
    stations/
      station_<st>_Power.png       17 lines (truth + p1..p16)
      station_<st>_GHI.png         2 lines  (lead-1 GHI pred vs real)
    station_power_rmse.csv         pooled RMSE per station (all leads)
    station_feature_rmse.csv       lead-1 GHI RMSE per station
```
(No `ultra_short/` subdir — the separate script makes the earlier disambiguation layer
unnecessary.)

## Components (`station_analysis_ultra_short.py` — self-contained, same dependency contract
as the short script: pandas / numpy / pyarrow / matplotlib only)

- `iter_baoshi(date)` → the 111 起报 timestamps `D−1 20:00 … D 23:30`.
- `load_predict_matrix(predict_dir, date, template)` → `{station: DataFrame[96 targets × p1..p16]}`.
  Per 起报 file: parse token, read parquet, for lead k take the row with `dtime == S + 15min·k`
  (row missing → NaN + warn once per file).
- `load_truth(input_dir, date, cols)` → `DataFrame[96 targets × (observe_power, ghi_real,
  ghi_pred)]` per station, from `list[0]` of the 96 起报 dirs.
- `plot_power_17(st, truth, lead_df, …)` / `plot_ghi(st, …)` — reuse the short script's style
  conventions (Agg backend, `_cn_font`, `sanitize`, HourLocator ticks, `stations/` dir).
- `pooled_rmse(truth, lead_df)` — RMSE over the flattened 96×16 matrix vs broadcast truth,
  night filter applied via the same `night_mask` logic.
- `main()` — CLI, assembly, warn+gap accounting summary (`N 起报 missing on predict side,
  M on input side`), CSV writes, terminal summary.

Shared helpers (`sanitize`, `night_mask`, `_cn_font`, plot conventions) are **copied**, not
imported — both files stay copy-anywhere self-contained (existing contract in README).

## Test plan

New `test_station_analysis_ultra_short.py` with synthetic fixtures:
- Build a tmp `--predict-dir` (a few 起报 parquets with known offsets) + `--input-dir`
  partitions; assert: 96-point target grid; p_j ↔ lead mapping (value at target t of line p16
  equals the S = t−15min parquet's first point); cross-midnight sourcing (target 00:00 pulled
  from `date=D−1/time=23:45` and 起报 `D−1 20:00`-onward predict files used);
  pooled RMSE arithmetic on a hand-computable case; warn+gap on a deleted 起报 (run succeeds,
  gap in CSV n_points); glob tolerance (misspelled province in filename still matched by token).

Existing `test_station_analysis_short.py`: reconcile to the two-script reality —
- `--short` flag dropped from `_run_short` (behavior is unconditional); `--date` cases keep
  working as before.
- Old plain-mode/full-series tests: their fixtures predate the unconditional D+1 window and
  place data outside it; migrate fixture data into the D+1 window (or convert pure-logic cases
  to direct helper-function tests). `test_default_no_short_folders` is deleted (no plain mode).

## README

Split into two sections: short (existing, plus restored `--date`/`--pred-col-template`) and
ultra-short (data layout diagrams above, p1..p16 semantics, warn+gap contract, no-metrics note).
