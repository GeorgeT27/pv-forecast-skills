"""时间序列骨架：把 parquet 的 list 单元格摊成绝对时间序列，再按夜间/窗口筛，最后对齐成可打分的数组。

指标与绘图共用这一层，两者的区别只在对齐方式：指标走 _aligned（交集，只打分两边都有的点），
绘图走 _display / _display_multi（并集 + 填 0，让缺口看得见而不是被悄悄丢掉）。
"""
from __future__ import annotations

import numpy as np
import pandas as pd

STEP = pd.Timedelta(minutes=15)


def sanitize(s) -> str:
    return "".join(c if str(c).isalnum() else "_" for c in str(s))


# ---------------------------------------------------------------- parquet list 单元格
def _listlen(v):
    """Length of a parquet list cell; 0 for None/NaN/scalar so unusable rows are easy to spot."""
    if v is None or np.ndim(v) == 0:
        return 0
    return len(v)


def _has_nan(v):
    """True if a non-empty list cell has NaN among its points. A cell can pass the length check (non-empty,
    matches the other side) and still carry scattered NaN inside -- those don't get caught by _listlen, they
    sail into the swap and only surface as a crash inside the model's own data_check mid-window."""
    return bool(np.isnan(np.asarray(v, dtype=float)).any())


def _fillna0(v):
    """NaN points inside a list cell -> 0.0, returned as a plain list so it writes back into the frame cleanly."""
    return np.nan_to_num(np.asarray(v, dtype=float), nan=0.0).tolist()


# ---------------------------------------------------------------- flatten
def series_from_lists(wins, lists, step) -> pd.Series:
    """Flatten all windows of a station's list column into an (absolute time -> value) series, groupby time to dedup.
    Non-list / None / NaN cells are auto-skipped (robust: a station missing this feature -> returns empty series)."""
    times, vals = [], []
    for t0, fut in zip(wins, lists):
        if fut is None or np.ndim(fut) == 0:          # scalar/None/NaN -> skip
            continue
        arr = np.asarray(fut, dtype=float).ravel()
        if arr.size == 0:
            continue
        t0 = pd.Timestamp(t0)
        for k, v in enumerate(arr):
            if np.isfinite(v):
                times.append(t0 + step * (k + 1))
                vals.append(float(v))
    if not times:
        return pd.Series(dtype=float)
    s = pd.Series(vals, index=pd.DatetimeIndex(times))
    return s.groupby(s.index).mean().sort_index()


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


def hist_span(inp, win_col, hist_col, step):
    """(t_start, t_end) covered by series_from_lists_history over the whole table, without flattening it:
    the last element of each list sits at its timestamp_win, so the union runs from
    min(win) - step*(Lmax-1) to max(win). Used to decide which date folders --hist-root must read."""
    if hist_col not in inp.columns or inp.empty:
        return None
    lens = inp[hist_col].map(_listlen)
    L = int(lens.max()) if len(lens) else 0
    if L == 0:
        return None
    wins = pd.to_datetime(pd.Series(inp[win_col].to_numpy()))
    return wins.min() - step * (L - 1), wins.max()


# ---------------------------------------------------------------- masks / alignment
def night_mask(idx: pd.DatetimeIndex, drop_night: bool, night_end_hour: float) -> np.ndarray:
    """True = keep. When drop_night, remove points in [00:00, night_end_hour)."""
    if not drop_night:
        return np.ones(len(idx), bool)
    hod = idx.hour + idx.minute / 60.0
    return ~(hod < night_end_hour)


def window_mask(idx: pd.DatetimeIndex, win) -> np.ndarray:
    """True = keep. win=(start,end) keeps [start, end) (end exclusive); win=None keeps all."""
    if win is None:
        return np.ones(len(idx), bool)
    start, end = win
    return (idx >= start) & (idx < end)


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


def _display_multi(a: pd.Series, others, drop_night, night_end_hour, win=None, fill=0.0):
    """PLOT-ONLY: union of ALL series' timestamps (within win, minus night), reindex every series onto that
    one index, gaps filled with `fill`. Metrics keep using _aligned (intersection); this only makes the lines
    span the full window so gaps are visible instead of silently dropped. One shared index is what lets the
    truth / prediction / counterfactual lines sit on a single x-axis.
    Returns (times, a_vals, [other_vals, ...]) or None."""
    idx = a.index
    for s in others:
        idx = idx.union(s.index)
    idx = idx.sort_values()
    keep = night_mask(idx, drop_night, night_end_hour) & window_mask(idx, win)
    idx = idx[keep]
    if len(idx) == 0:
        return None
    return (idx, a.reindex(idx).fillna(fill).to_numpy(),
            [s.reindex(idx).fillna(fill).to_numpy() for s in others])


def _display(a: pd.Series, b: pd.Series, drop_night, night_end_hour, win=None, fill=0.0):
    """Two-series form of _display_multi (kept so existing callers read unchanged)."""
    got = _display_multi(a, [b], drop_night, night_end_hour, win, fill)
    return None if got is None else (got[0], got[1], got[2][0])
