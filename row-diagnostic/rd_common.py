"""row-diagnostic 共享工具 —— 完全自包含，不依赖任何 skill / data_utils。

只做三件小事：读三张大表（时间戳归一 + 192点list→矩阵）、配 X_pred/X 特征对、
算逐行 RMSE 与统计块。两个脚本（build_baseline / row_analysis）都从这里取。
"""
from __future__ import annotations

import numpy as np
import pandas as pd

TS_CANDIDATES = ("timestamp", "timestamp_win", "time", "ts", "datetime", "date")
DEFAULT_TRUE_POWER_COL = "observe_power_future"
PRED_SUFFIX = "_pred"


# ---------------------------------------------------------------- 读表（时间戳统一成 "timestamp" 列）
def load_table(path: str) -> pd.DataFrame:
    """载入 parquet，把时间戳统一成名为 'timestamp' 的 datetime 列（列或 index 都兜底）。"""
    df = pd.read_parquet(path)
    for c in TS_CANDIDATES:
        if c in df.columns:
            df = df.rename(columns={c: "timestamp"})
            df["timestamp"] = pd.to_datetime(df["timestamp"])
            return df.reset_index(drop=True)
    idx = df.index
    if isinstance(idx, pd.DatetimeIndex) or idx.name in TS_CANDIDATES:
        df = df.reset_index()
        df = df.rename(columns={df.columns[0]: "timestamp"})
        df["timestamp"] = pd.to_datetime(df["timestamp"])
        return df.reset_index(drop=True)
    raise KeyError(f"{path}: 找不到时间戳列（候选 {TS_CANDIDATES}，index 也不是时间）；"
                   f"实际列: {list(df.columns)[:20]}")


def to_matrix(df: pd.DataFrame, col: str) -> np.ndarray:
    """list 单元格列 → (n_rows, L) float 矩阵。"""
    return np.stack([np.asarray(v, dtype=float) for v in df[col].to_numpy()])


def list_columns(df: pd.DataFrame) -> dict[str, int]:
    """返回 {列名: 序列长度}，只含单元格是 list/array 的列（跳过 timestamp）。"""
    out = {}
    for c in df.columns:
        if c == "timestamp":
            continue
        s = df[c].dropna()
        if not len(s):
            continue
        v = s.iloc[0]
        if isinstance(v, (list, tuple, np.ndarray)):
            out[c] = len(v)
    return out


def discover_models(pred_df: pd.DataFrame) -> list[str]:
    """predict 表里所有 192点list 列都算模型列。"""
    return sorted(list_columns(pred_df))


def feature_pairs(ft_df: pd.DataFrame) -> tuple[dict, list]:
    """配对：凡 `X_pred` 列且基名 `X` 也在，配成 {X: {pred, true}}。配不上的进 unmapped。"""
    listcols = list_columns(ft_df)
    cols = set(ft_df.columns)
    pairs, matched = {}, set()
    for c in listcols:
        if c.endswith(PRED_SUFFIX):
            base = c[: -len(PRED_SUFFIX)]
            if base in cols:
                pairs[base] = {"pred": c, "true": base}
                matched.update((c, base))
    unmapped = sorted(c for c in listcols if c not in matched)
    return pairs, unmapped


# ---------------------------------------------------------------- 对齐 & RMSE
def align_power(pred_df, test_df, model, true_power_col):
    """按 timestamp 内连接功率预测与真值。返回 (timestamps, P, Y)。"""
    if model not in pred_df.columns:
        raise SystemExit(f"predict 里没有模型列 '{model}'；可选: {discover_models(pred_df)}")
    if true_power_col not in test_df.columns:
        raise SystemExit(f"test 里没有真功率列 '{true_power_col}'。")
    m = pd.merge(pred_df[["timestamp", model]], test_df[["timestamp", true_power_col]],
                 on="timestamp", how="inner")
    return (m["timestamp"].reset_index(drop=True),
            to_matrix(m, model), to_matrix(m, true_power_col))


def row_rmse(P: np.ndarray, Y: np.ndarray) -> np.ndarray:
    """逐行全序列 RMSE = sqrt(nanmean((P-Y)^2))，形状 (n_rows,)。"""
    return np.sqrt(np.nanmean((P - Y) ** 2, axis=1))


def hour_key(ts) -> str:
    """窗口时间戳 → 'HH:MM' 钟点分组键。"""
    return pd.Timestamp(ts).strftime("%H:%M")


# ---------------------------------------------------------------- 统计块
STAT_KEYS = ("mean", "std", "median", "p10", "p25", "p75", "p90", "min", "max", "n")


def stats_block(values) -> dict:
    """一组 RMSE → 统计块（正态口径 mean/std + 稳健口径 median/分位）。空组 n=0、其余 None。"""
    v = np.asarray(values, float)
    v = v[np.isfinite(v)]
    if v.size == 0:
        return {k: (0 if k == "n" else None) for k in STAT_KEYS}
    p10, p25, p75, p90 = np.percentile(v, [10, 25, 75, 90])
    return {"mean": round(float(np.mean(v)), 6), "std": round(float(np.std(v)), 6),
            "median": round(float(np.median(v)), 6),
            "p10": round(float(p10), 6), "p25": round(float(p25), 6),
            "p75": round(float(p75), 6), "p90": round(float(p90), 6),
            "min": round(float(np.min(v)), 6), "max": round(float(np.max(v)), 6),
            "n": int(v.size)}


def stats_global_and_hourly(rmses: np.ndarray, timestamps) -> dict:
    """同一组逐行 RMSE，产出 {'global': 块, 'by_hour': {'HH:MM': 块}}。"""
    ts = pd.DatetimeIndex(timestamps)
    by_hour = {}
    keys = np.array([hour_key(t) for t in ts])
    for k in sorted(set(keys)):
        by_hour[k] = stats_block(rmses[keys == k])
    return {"global": stats_block(rmses), "by_hour": by_hour}


# ---------------------------------------------------------------- 偏离度（row vs 基线块）
def pctl_band(x: float, blk: dict) -> str:
    """x 落在历史分布哪一带。"""
    for label, key in (("<p10", "p10"), ("p10–p25", "p25"), ("p25–p50", "median"),
                       ("p50–p75", "p75"), ("p75–p90", "p90")):
        if blk.get(key) is not None and x <= blk[key]:
            return label
    return ">p90"


def deviation(x: float, blk: dict | None) -> dict:
    """row 值 vs 一个统计块：diff / z / 稳健z / 百分位带。块缺失或 n=0 → 全 None。"""
    if not blk or not blk.get("n"):
        return {"diff": None, "z": None, "z_robust": None, "pctl_band": None}
    mean, std, med = blk["mean"], blk["std"], blk["median"]
    iqr = (blk["p75"] - blk["p25"]) if (blk["p75"] is not None and blk["p25"] is not None) else None
    z = (x - mean) / std if (std and std > 0) else None
    zr = (x - med) / iqr if (iqr and iqr > 0) else None
    return {"diff": round(x - mean, 6),
            "z": round(float(z), 3) if z is not None else None,
            "z_robust": round(float(zr), 3) if zr is not None else None,
            "pctl_band": pctl_band(x, blk)}


def status_from_z(z) -> str:
    """z → 中文状态标签（|z|<1 正常，1≤|z|<2 略，≥2 显著）。"""
    if z is None:
        return "n/a"
    if z >= 2:
        return "⚠️偏高"
    if z >= 1:
        return "略偏高"
    if z <= -2:
        return "明显偏低"
    if z <= -1:
        return "略偏低"
    return "正常"
