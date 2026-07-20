"""pv-feature-blame —— 共享工具（配置 / 口径切片 / 复用主技能 data_utils / 统计）。

设计纪律（见 SKILL.md 上下文预算节）：
- 重活在脚本内完成，脚本只 print ≤30 行摘要；产物落盘 CSV/JSON，各带自足 summary。
- 复用兄弟技能 pv-result-analysis/scripts/data_utils.py 的口径常量与读表工具，
  绝不重新定义第 16 点 / [59:155]（口径漂移 = 整条归因链作废）——缺该文件直接硬失败。

配置文件 blame_config.json（工作目录；字段渐进填，缺就问用户，CLI flag 可覆盖）：
{
  "experiment": "<实验线名>",                  # project-context/experiments/ 文件名（Step 0.5 写入）
  "station": "<held_out_station_slug>",
  "test_label": "<test.parquet 绝对路径>",     # 真值（observe_power_future）+ 特征窗口
  "predict": "<predict.parquet 绝对路径>",     # 1..N 个模型的 192 点预测列
  "feature_true": "<feature_true.parquet 绝对路径 | null>",  # 各特征 预测/真值 序列对照
  "feature_true_status": "provided",          # provided | user_confirmed_missing —— 硬规则台账：
                                              #   feature_true 为空且未确认缺失 → orient 阻塞 Stage 0，
                                              #   绝不静默降级到重叠重建
  "metric_py": "<metric.py 路径>",             # 仅 Stage 4 --monthly 复算月度口径用，可缺
  "metrics": ["rmse_192"],                    # 行级化口径：rmse_192（默认，每行全 192 点 RMSE）
                                              #   / ultra_short / short，可多选各自找坏行
  "top_pct": 10,                              # 坏行 = 高于均值 且 误差进 top 10%
  "threshold_rule": "top_pct_above_mean",
  "blame": {"z_hi": 2.0, "spearman_min": 0.3, "top_k": 3,
            "tau": 0.8, "g_min": 0.2,          # Stage 4：修复谓词阈 / oracle 缺口闸
            "z_relax": 1.0, "pool_cap": 8},    # Stage 4：消解候选池放宽线与上限
  "revision": {"enabled": true,               # 翻新跳变分析（Stage 2 并行产物，免 API）
               "spearman_min": 0.3, "jumpiness_min": 0.05, "stable_max": 0.02},
  "api": {"endpoint": "【待补】", "confirmed": false,
          "neighbor_swap_confirmed": false,   # neighbor-swap 模式单独确认（拼接序列可能被服务端拒）
          "timeout_s": 30, "batch_size": 8}
}
"""
from __future__ import annotations

import json
import os
import sys

import numpy as np
import pandas as pd

CONFIG_PATH = "blame_config.json"

# 复用主技能 data_utils（口径常量 / load_table / to_matrix / check_window_consistency）。
# 与 si_common 不同：本技能的口径常量承重（坏行定义直接依赖），缺失时硬失败而非降级。
_SKILL_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_SIBLING = os.path.normpath(os.path.join(_SKILL_ROOT, "..", "pv-result-analysis", "scripts"))
if os.path.isdir(_SIBLING) and _SIBLING not in sys.path:
    sys.path.insert(0, _SIBLING)
try:
    import data_utils as du  # noqa: E402  复用：TIMESTAMP_COL/ULTRA_SHORT_IDX/SHORT_SLICE/load_table/to_matrix
except Exception:            # pragma: no cover - 仅在兄弟技能缺失时
    du = None


def require_du():
    if du is None:
        raise SystemExit(
            "找不到 pv-result-analysis/scripts/data_utils.py —— 本技能的口径常量"
            "（ULTRA_SHORT_IDX/SHORT_SLICE）从它导入，绝不本地重定义。"
            f"请确认兄弟技能目录存在：{_SIBLING}"
        )
    return du


# ---------------------------------------------------------------- 配置
def load_config(path: str = CONFIG_PATH) -> dict:
    if not os.path.exists(path):
        raise FileNotFoundError(
            f"未找到 {path}。先按 SKILL.md Step 1 收集路径写 blame_config.json（缺字段就先留空）。")
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def has_config(path: str = CONFIG_PATH) -> bool:
    return os.path.exists(path)


def config_or_empty(path: str = CONFIG_PATH) -> dict:
    return load_config(path) if has_config(path) else {}


def dump_json(path: str, obj) -> None:
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(obj, f, ensure_ascii=False, indent=2, default=str)


def read_json(path: str):
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except (OSError, json.JSONDecodeError):
        return None


def sanitize(name: str) -> str:
    """列名 → 文件名安全片段。"""
    return "".join(c if c.isalnum() else "_" for c in str(name))


# ---------------------------------------------------------------- 读表（时间戳列自动侦测）
TS_CANDIDATES = ("timestamp", "timestamp_win", "time", "ts", "date", "datetime")


def detect_ts_col(path: str) -> str:
    """探测 parquet 的时间戳列名；列里没有则看 index（返回 '<index>'）。"""
    df = pd.read_parquet(path)
    for c in TS_CANDIDATES:
        if c in df.columns:
            return c
    idx = df.index
    if isinstance(idx, pd.DatetimeIndex) or idx.name in TS_CANDIDATES:
        return "<index>"
    if idx.dtype == object:
        try:
            pd.to_datetime(idx[:5])
            return "<index>"
        except (ValueError, TypeError):
            pass
    raise KeyError(f"{path} 探测不到时间戳列（候选 {TS_CANDIDATES}，index 也不是时间）；"
                   f"实际列: {list(df.columns)[:20]}")


def load_any(path: str) -> tuple[pd.DataFrame, str]:
    """载入任意一方 parquet，时间戳列统一重命名为 du.TIMESTAMP_COL。返回 (df, 原始列名)。"""
    d = require_du()
    ts = detect_ts_col(path)
    if ts == "<index>":
        df = d.load_table(path)                      # load_table 自带 index→列 兜底
        return df, "<index>"
    df = d.load_table(path, timestamp_col=ts)
    if ts != d.TIMESTAMP_COL:
        df = df.rename(columns={ts: d.TIMESTAMP_COL})
    return df, ts


def list_columns(df: pd.DataFrame) -> dict[str, int]:
    """list 单元格列 → {列名: 序列长度}（取首个非空单元格判定）。"""
    out = {}
    for c in df.columns:
        s = df[c].dropna()
        if not len(s):
            continue
        v = s.iloc[0]
        if isinstance(v, (list, tuple, np.ndarray)):
            out[c] = len(v)
    return out


# ---------------------------------------------------------------- 口径（常量一律取自 data_utils）
def metric_slices() -> dict[str, slice]:
    """特征误差的口径匹配切片：rmse_192 看全窗 192 点，ultra_short 看前 0..16 步
    （考核点及其前导），short 看 [59:155]（09:00 行的次日全天）。"""
    d = require_du()
    return {"rmse_192": slice(0, d.HORIZON),
            "ultra_short": slice(0, d.ULTRA_SHORT_IDX + 1), "short": d.SHORT_SLICE}


def row_errors(timestamps: pd.Series, P: np.ndarray, Y: np.ndarray, metric: str):
    """行级误差。返回 (sel_idx, err)：sel_idx = 参与该口径的行号（相对入参顺序），
    err = 对应行误差。rmse_192 = 每行全 192 点 RMSE（全行参与，默认考核口径）；
    ultra_short = 每行第 ULTRA_SHORT_IDX 点绝对误差（全行参与）；
    short = 仅 09:00 行，SHORT_SLICE 上 RMSE。"""
    d = require_du()
    ts = pd.DatetimeIndex(timestamps)
    if metric == "rmse_192":
        sel = np.arange(len(ts))
        err = np.sqrt(np.nanmean((P - Y) ** 2, axis=1))
    elif metric == "ultra_short":
        sel = np.arange(len(ts))
        err = np.abs(P[:, d.ULTRA_SHORT_IDX] - Y[:, d.ULTRA_SHORT_IDX])
    elif metric == "short":
        sel = np.where((ts.hour == 9) & (ts.minute == 0))[0]
        diff = P[sel, d.SHORT_SLICE] - Y[sel, d.SHORT_SLICE]
        err = np.sqrt(np.nanmean(diff ** 2, axis=1))
    else:
        raise ValueError(f"未知口径 {metric}（支持 rmse_192 / ultra_short / short）")
    return sel, np.asarray(err, float)


def bad_mask(err: np.ndarray, top_pct: float) -> np.ndarray:
    """坏行判定：误差 > 均值 且 进 top_pct%（两个条件都要，top_pct 参数化）。"""
    err = np.asarray(err, float)
    n = len(err)
    if n == 0:
        return np.zeros(0, bool)
    n_top = max(1, int(np.ceil(top_pct / 100.0 * n)))
    order = np.argsort(-err)                    # 误差降序
    in_top = np.zeros(n, bool)
    in_top[order[:n_top]] = True
    return in_top & (err > np.nanmean(err))


# ---------------------------------------------------------------- 统计
def spearman(x: np.ndarray, y: np.ndarray) -> float:
    """Spearman ρ；常量向量/样本不足时返回 0.0（不给 NaN 传播机会）。"""
    x, y = np.asarray(x, float), np.asarray(y, float)
    m = np.isfinite(x) & np.isfinite(y)
    x, y = x[m], y[m]
    if len(x) < 3 or np.all(x == x[0]) or np.all(y == y[0]):
        return 0.0
    try:
        from scipy.stats import spearmanr
        r = float(spearmanr(x, y).statistic)
    except ImportError:
        rx = pd.Series(x).rank().to_numpy()
        ry = pd.Series(y).rank().to_numpy()
        r = float(np.corrcoef(rx, ry)[0, 1])
    return 0.0 if not np.isfinite(r) else r


def zscores(v: np.ndarray) -> np.ndarray:
    """对全体行的分布做 z 归一；std=0（如完美特征全零误差）→ 全 0，不产 NaN。"""
    v = np.asarray(v, float)
    sd = np.nanstd(v)
    if not np.isfinite(sd) or sd == 0:
        return np.zeros_like(v)
    return (v - np.nanmean(v)) / sd
