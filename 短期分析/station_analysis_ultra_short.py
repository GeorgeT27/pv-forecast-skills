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
