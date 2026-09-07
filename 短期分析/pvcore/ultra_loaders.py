"""超短期侧的时间网格与三个 loader：预测矩阵、真值、历史。

两侧都按 起报时间 组织，每 15min 一个 起报：
  predict_dir  扁平目录，每个 起报 一个 parquet，文件名含 YYYYMMDDHHMM token
  input_dir    Hive 分区 date=YYYY-MM-DD/time=HH:MM/ 下单个 parquet
"""
from __future__ import annotations

import glob
import os

import numpy as np
import pandas as pd

STEP = pd.Timedelta(minutes=15)
N_LEADS = 16
TRUTH_COLS = {"power_true": "observe_power_future",
              "ghi_true": "GHI_real_future",
              "ghi_pred": "GHI_SOLARGIS_predict"}
HIST_COLS = {"power_hist": "observe_power",
             "ghi_hist": "GHI_SOLARGIS"}


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


def load_history(input_dir: str, D: pd.Timestamp, station_col: str = "station"):
    """-> ({station: {"ghi_hist": Series, "power_hist": Series}}, 所用起报时刻|None)。
    只读 date=D 下**最早**一个含 station 列与至少一个历史列的 time=HH:MM 目录（当日无 00:00 就取
    02:15 之类实际存在的第一个）。历史 list 反向排（list[-1] 落在该起报时刻 S），故长 L 的 list
    元素 i 的时间 = S − 15min×(L−1−i)，672 长即展开成往前 7 天的曲线；非有限值逐点剔除。
    全天无可用目录 -> ({}, None)，调用方据此让历史面板显示 no data。"""
    day = os.path.join(input_dir, f"date={D:%Y-%m-%d}")
    for d in sorted(glob.glob(os.path.join(day, "time=*"))):
        hits = sorted(glob.glob(os.path.join(d, "*.parquet")))
        if not hits:
            continue
        df = pd.read_parquet(hits[0])
        if station_col not in df.columns or not any(c in df.columns for c in HIST_COLS.values()):
            continue
        S = pd.Timestamp(f"{D:%Y-%m-%d} {os.path.basename(d).split('=', 1)[1]}")
        out = {}
        for _, row in df.iterrows():
            ser = {}
            for out_col, src_col in HIST_COLS.items():
                s = pd.Series(dtype=float)
                cell = row[src_col] if src_col in df.columns else None
                if cell is not None and np.ndim(cell) != 0:
                    arr = np.asarray(cell, dtype=float).ravel()
                    if arr.size:
                        idx = pd.date_range(S - STEP * (arr.size - 1), periods=arr.size, freq=STEP)
                        s = pd.Series(arr, index=idx)
                        s = s[np.isfinite(s.to_numpy(float))]
                ser[out_col] = s
            out[str(row[station_col])] = ser
        return out, S
    print(f"  [warn] date={D:%Y-%m-%d}: no usable 起报 dir for history columns -> history panels empty")
    return {}, None
