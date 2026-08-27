#!/usr/bin/env python3
"""读取南网 IN 侧的原始可用功率宽表 DQYC_IN_HISTORY_AVAIL_POWER_WIDE.txt，拼成每站一条时间序列。

目录约定  {root}/{YYYY-MM-DD}/IN/{plantid}/DQYC_IN_HISTORY_AVAIL_POWER_WIDE.txt
          —— {root} 指到「含日期文件夹」那一层，例如 .../products/data/qy/63/1002
宽表格式  utf-8、回车隔行、空格隔列、大小写不敏感；数值空列写 "null"（-> NaN，画图时断线）。
          列 = PlantID PDate Tjlx V0000 V0015 ... V2345，V0000 即当日 00:00 的取值。
          Tjlx = 0 调度端 / 1 场站端 / 2 agc限电标志位，同一 plant+date 可能每种一行。

供短期分析在历史功率面板上叠加「原始」那条线（主表 observe_power 是调整后的，两者是两回事）。
"""
from __future__ import annotations

import os
import re

import numpy as np
import pandas as pd

WIDE_FILENAME = "DQYC_IN_HISTORY_AVAIL_POWER_WIDE.txt"
STEP = pd.Timedelta("15min")
VCOLS = [f"V{h:02d}{m:02d}" for h in range(24) for m in (0, 15, 30, 45)]   # V0000..V2345, 96 个
_FIXED = ["PLANTID", "PDATE", "TJLX"]                                      # 无表头时的文档列序


def station_to_plant_id(station) -> str:
    """站名 -> 场站文件夹号：取末尾连续数字（plant_guangfu1358 -> 1358），没有数字就原样返回。"""
    m = re.search(r"(\d+)\s*$", str(station))
    return m.group(1) if m else str(station)


def _to_float(tok) -> float:
    """"null" / 空 / 不可解析 -> NaN。功率里 0 是合法值（夜间、停机都是真 0），拿 0 冒充缺测就再也
    分不出「没出力」和「没数据」，所以缺测一律 NaN，画图时断线。"""
    try:
        v = float(tok)
    except (TypeError, ValueError):
        return np.nan
    return v if np.isfinite(v) else np.nan


def parse_wide_file(path, tjlx: int = 1) -> pd.Series | None:
    """一个宽表文件 -> 该 PDate 当天 96 点的 Series（缺列/null 留 NaN）。
    文件里没有请求的 Tjlx 那一行时返回 None —— 交给调用方告警并留空洞，不拿一整天的空值冒充。"""
    with open(path, encoding="utf-8", errors="replace") as f:
        lines = [ln.split() for ln in f.read().splitlines() if ln.strip()]
    if not lines:
        return None
    head = [t.upper() for t in lines[0]]
    if any(re.fullmatch(r"V\d{4}", t) for t in head):        # 有表头行：按列名取，缺哪列就是缺哪列
        cols, rows = head, lines[1:]
    else:                                                    # 无表头行：按文档列序，V 列从第 4 个 token 起
        cols, rows = _FIXED + VCOLS, lines
    pos = {c: i for i, c in enumerate(cols)}
    ti = pos.get("TJLX")
    for r in rows:
        if ti is None or ti >= len(r):
            continue
        tv = _to_float(r[ti])                                # Tjlx 本身解析不出来就当这行不匹配
        if not np.isfinite(tv) or int(tv) != int(tjlx):
            continue
        day = pd.Timestamp(r[pos["PDATE"]]).normalize()
        idx = pd.date_range(day, periods=96, freq=STEP)
        vals = [_to_float(r[pos[c]]) if c in pos and pos[c] < len(r) else np.nan for c in VCOLS]
        return pd.Series(vals, index=idx)
    return None


def load_raw_history(root, stations, t_start, t_end, tjlx: int = 1, verbose: bool = True) -> dict:
    """{站: Series} —— 每站把 [t_start, t_end] 覆盖到的每个日期文件夹读一遍、拼起来、再裁到该区间。
    裁剪就是两条线对齐的地方：主表 observe_power 的历史线收在起报时刻（当日 10:00），这条也收在那里。
    root 不存在 -> SystemExit（指错路径要立刻炸，而不是安静地画不出线）。"""
    if not os.path.isdir(root):
        raise SystemExit(f"--hist-root not a directory: {root}")
    t_start, t_end = pd.Timestamp(t_start), pd.Timestamp(t_end)
    days = pd.date_range(t_start.normalize(), t_end.normalize(), freq="D")
    out, miss_day, miss_station, miss_tjlx = {}, set(), {}, set()
    for st in stations:
        plant, parts = station_to_plant_id(st), []
        for d in days:
            ds = f"{d:%Y-%m-%d}"
            in_dir = os.path.join(root, ds, "IN")
            path = os.path.join(in_dir, plant, WIDE_FILENAME)
            if not os.path.isfile(path):
                if os.path.isdir(in_dir) and not os.path.isdir(os.path.join(in_dir, plant)):
                    miss_station.setdefault(str(st), (plant, in_dir))
                else:
                    miss_day.add(ds)
                continue
            s = parse_wide_file(path, tjlx)
            if s is None:
                miss_tjlx.add(ds)
            else:
                parts.append(s)
        if not parts:
            out[str(st)] = pd.Series(dtype=float)
            continue
        s = pd.concat(parts)
        s = s.groupby(s.index).mean().sort_index()
        s = s[(s.index >= t_start) & (s.index <= t_end)]
        # 补齐成完整 15 分钟网格：整天缺失的地方留 NaN。不补的话索引里直接没有这些点，
        # matplotlib 会从缺口前一点拉一条直线连到后一点，看起来像有数据。
        if not s.empty:
            s = s.reindex(pd.date_range(s.index[0], s.index[-1], freq=STEP))
        out[str(st)] = s
    if verbose:
        if miss_day:
            print(f"  [hist-raw] no {WIDE_FILENAME} for {len(miss_day)} date(s): "
                  f"{sorted(miss_day)[:8]}{' ...' if len(miss_day) > 8 else ''} -> gap left in the raw line")
        if miss_tjlx:
            print(f"  [hist-raw] Tjlx={tjlx} absent on {len(miss_tjlx)} date(s): "
                  f"{sorted(miss_tjlx)[:8]}{' ...' if len(miss_tjlx) > 8 else ''} -> gap left in the raw line")
        for st, (plant, in_dir) in sorted(miss_station.items()):
            have = sorted(x for x in os.listdir(in_dir) if os.path.isdir(os.path.join(in_dir, x)))
            print(f"  [hist-raw] station {st} -> folder '{plant}' not found under {in_dir}; "
                  f"available: {have[:15]}{' ...' if len(have) > 15 else ''}")
        for st, s in out.items():
            if len(s):
                n_gap = int(s.isna().sum())                  # 网格里的空洞：缺测点 + 整天缺失
                gap = f"  ({n_gap} missing -> line broken there)" if n_gap else ""
                rng = (f"[{s.min():.4g}, {s.max():.4g}]" if s.notna().any() else "[all missing]")
                print(f"  [hist-raw] {st}: {int(s.notna().sum())} pts  {s.index[0]:%Y-%m-%d %H:%M} -> "
                      f"{s.index[-1]:%Y-%m-%d %H:%M}  range {rng}{gap}")
    return out
