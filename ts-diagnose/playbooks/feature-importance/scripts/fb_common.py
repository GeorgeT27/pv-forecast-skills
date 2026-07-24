"""pv-feature-blame —— 共享工具（配置 / 口径切片 / 复用主技能 data_utils / 统计）。

设计纪律（见 SKILL.md 上下文预算节）：
- 重活在脚本内完成，脚本只 print ≤30 行摘要；产物落盘 CSV/JSON，各带自足 summary。
- 复用 ts-diagnose/playbooks/result-eval/scripts/data_utils.py 的口径常量与读表工具
  （原 pv-result-analysis/scripts/data_utils.py，2026-07-24 迁入 result-eval playbook），
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
  "decompose": {"enabled": true,                # Stage 1.5：ε_sys/ε_res 分解（v3）
                "embargo": "48h",               # 前/后段稳定性切分的重叠窗隔离（=192 步）
                "max_orders_hod": 3, "max_orders_doy": 2, "n_knots": 4,   # df 上限
                "alpha": 1e-3, "fit_cap": 400000,   # 岭系数 / 拟合点数上限（等距抽样）
                "reducibility_min": 0.1,        # Stage 2 可约性闸：低于此不点名
                "sys_frac_max": 0.85},          # 系统偏差门：sys_frac ≥ 此值不点名（模型已补偿的稳定偏差）
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
# data_utils.py 现居 ts-diagnose/playbooks/result-eval/scripts/（2026-07-24 迁入 result-eval
# playbook，原 pv-result-analysis/scripts/）。本文件自身也已随 feature-blame 方法并入
# feature-importance playbook 迁移到 ts-diagnose/playbooks/feature-importance/scripts/
# （2026-07-24，原 pv-feature-blame/scripts/）——相对层级从 skill-root/scripts 变为
# ts-diagnose/playbooks/<id>/scripts，多套一层 playbooks/，故 sibling 路径改为「同为
# playbooks/ 下的兄弟 playbook」而非旧式「仓库根下的兄弟技能」（同 si_common.py 的推导）；
# 旧路径保留兜底，防止尚未同步迁移的检出环境炸掉。
_SCRIPTS_DIR = os.path.dirname(os.path.abspath(__file__))
_PLAYBOOKS_DIR = os.path.dirname(os.path.dirname(_SCRIPTS_DIR))       # .../ts-diagnose/playbooks
_REPO_ROOT = os.path.dirname(os.path.dirname(_PLAYBOOKS_DIR))         # 仓库根
_SIBLING_CANDIDATES = (
    os.path.join(_PLAYBOOKS_DIR, "result-eval", "scripts"),           # 新路径（同引擎兄弟 playbook）
    os.path.join(_REPO_ROOT, "ts-diagnose", "playbooks", "result-eval", "scripts"),  # 兜底写法等价
    os.path.join(_REPO_ROOT, "pv-result-analysis", "scripts"),        # 旧路径兜底（迁移前）
)
_SIBLING = next((p for p in _SIBLING_CANDIDATES if os.path.isdir(p)), _SIBLING_CANDIDATES[0])
if os.path.isdir(_SIBLING) and _SIBLING not in sys.path:
    sys.path.insert(0, _SIBLING)
try:
    import data_utils as du  # noqa: E402  复用：TIMESTAMP_COL/ULTRA_SHORT_IDX/SHORT_SLICE/load_table/to_matrix
except Exception:            # pragma: no cover - 仅在兄弟技能缺失时
    du = None


def require_du():
    if du is None:
        raise SystemExit(
            "找不到 data_utils.py（找过：" + "、".join(_SIBLING_CANDIDATES) + "）—— "
            "本技能的口径常量（ULTRA_SHORT_IDX/SHORT_SLICE）从它导入，绝不本地重定义。"
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


# ---------------------------------------------------------------- ε 分解构件（Stage 1.5）
def harmonic_basis(x: np.ndarray, period: float, n_orders: int = 3) -> np.ndarray:
    """cyclic 谐波基 sin/cos(2πk·x/period)，k=1..n_orders → (n, 2·n_orders)。
    钟点/DoY 用它——天然处理午夜与跨年回绕，无分箱边界。"""
    x = np.asarray(x, float)
    cols = []
    for k in range(1, n_orders + 1):
        ang = 2.0 * np.pi * k * x / period
        cols += [np.sin(ang), np.cos(ang)]
    return np.column_stack(cols)


def hinge_basis(x: np.ndarray, n_knots: int = 4) -> np.ndarray:
    """线性 + 分位点 hinge 样条基，df = 1+n_knots ≤ 6（结构性防偷波动：低 df 曲面
    只装得下慢变偏置）。x 先稳健标准化（median/IQR）；常量列返回全零基。"""
    x = np.asarray(x, float)
    med = np.nanmedian(x)
    iqr = np.nanpercentile(x, 75) - np.nanpercentile(x, 25)
    if not np.isfinite(iqr) or iqr == 0:
        return np.zeros((len(x), 1))
    z = (x - med) / iqr
    knots = np.nanpercentile(z, np.linspace(20, 80, n_knots))
    return np.column_stack([z] + [np.maximum(0.0, z - q) for q in knots])


def huber_ridge(X: np.ndarray, y: np.ndarray, alpha: float = 1e-3,
                iters: int = 10):
    """Huber-IRLS + 岭（确定性）。返回系数；样本 < max(30, 2p) → None（保守不剥）。
    非有限行剔除后拟合；共线协变量靠岭稳住——只取拟合值不解释系数。"""
    X, y = np.asarray(X, float), np.asarray(y, float)
    m = np.isfinite(y) & np.all(np.isfinite(X), axis=1)
    Xm, ym = X[m], y[m]
    n, p = Xm.shape
    if n < max(30, 2 * p):
        return None
    w, coef, eye = np.ones(n), np.zeros(p), np.eye(p)
    for _ in range(iters):
        Xw = Xm * w[:, None]
        coef = np.linalg.solve(Xw.T @ Xm + alpha * n * eye, Xw.T @ ym)
        r = ym - Xm @ coef
        mad = np.median(np.abs(r - np.median(r)))
        delta = 1.345 * 1.4826 * mad
        if not np.isfinite(delta) or delta <= 0:
            break
        aw = np.abs(r)
        w = np.where(aw <= delta, 1.0, delta / np.maximum(aw, 1e-12))
    return coef


def temporal_split(ts, embargo: str = "48h"):
    """按时间中位切前/后段行号；后段起点 ≥ 前段末行 + embargo（重叠窗 192 步 = 48h，
    防泄漏）。返回 (front_idx, back_idx)；数据太短后段可为空——调用方 λ=0 保守不剥。"""
    ts = pd.DatetimeIndex(ts)
    order = np.argsort(ts.asi8)
    n = len(order)
    if n < 4:
        return order, np.array([], int)
    half = n // 2
    cutoff = ts[order[half - 1]] + pd.Timedelta(embargo)
    back = np.array([i for i in order[half:] if ts[i] >= cutoff], int)
    return order[:half], back


def lag1_reducibility(E: np.ndarray) -> float:
    """可约性 v1：逐行 lag-1 自相关的中位数，负值截 0 后平方（≈AR(1) 可解释方差占比）。
    白噪声/常量 → 0（上游拿它没辙，点名是废话）。v2 占位：相位/幅度/爬坡形状分解。"""
    rows = []
    for r in np.asarray(E, float):
        a, b = r[:-1], r[1:]
        m = np.isfinite(a) & np.isfinite(b)
        a, b = a[m], b[m]
        if len(a) < 8 or np.std(a) == 0 or np.std(b) == 0:
            continue
        c = np.corrcoef(a, b)[0, 1]
        if np.isfinite(c):
            rows.append(float(c))
    if not rows:
        return 0.0
    return round(max(0.0, float(np.median(rows))) ** 2, 4)


def eps_matrices(ft: pd.DataFrame, pairs: list) -> dict:
    """逐点特征误差矩阵 {feature: (n_rows,192) pred − label}。分解（Stage 1.5）与
    归因（Stage 2）共用同一定义——只对配对特征存在 ε，未配对列无 ε 无反事实。"""
    d = require_du()
    return {p["feature"]: d.to_matrix(ft, p["pred_col"]) - d.to_matrix(ft, p["label_col"])
            for p in pairs}
