"""chartbook 公共件：规范长表读入、逐行 RMSE、形状描述符、JSON+PNG 落盘。

纪律（见 chartbook/_recipe-spec.md）：
- JSON 是一等产物，PNG 是给人看的副产品——判读一律读 JSON；
- err ≡ y_pred − y_true；
- curve_stats 字段名与判读库绑定，不得改名。
"""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd
import matplotlib

matplotlib.use("Agg")
import matplotlib.font_manager  # noqa: E402
import matplotlib.pyplot as plt  # noqa: E402

REQUIRED_COLS = ("window_ts", "unit_id", "model", "horizon_step",
                 "y_true", "y_pred")

FEATURE_COLS = ("window_ts", "unit_id", "feature", "horizon_step", "f_pred")


CJK_FONTS = ("Arial Unicode MS", "PingFang SC", "Hiragino Sans GB", "Heiti TC",
             "SimHei", "Noto Sans CJK SC", "Microsoft YaHei")


def setup_font() -> list:
    """CJK 字体探测:命中项组成 sans-serif 回退链(单字体断链→回退链硬化)。
    返回命中列表;空列表 = 环境无 CJK,发一次警告但不炸图。"""
    installed = {f.name for f in matplotlib.font_manager.fontManager.ttflist}
    hits = [f for f in CJK_FONTS if f in installed]
    if hits:
        plt.rcParams["font.family"] = "sans-serif"
        plt.rcParams["font.sans-serif"] = hits + ["DejaVu Sans"]
    else:
        import warnings
        warnings.warn("未找到 CJK 字体,中文将渲染为方框;建议安装 Noto Sans CJK SC")
    plt.rcParams["axes.unicode_minus"] = False
    return hits


def load_predictions(path):
    p = Path(path)
    df = pd.read_parquet(p) if p.suffix == ".parquet" else pd.read_csv(p)
    missing = [c for c in REQUIRED_COLS if c not in df.columns]
    if missing:
        raise ValueError(
            f"规范长表缺列 {missing}；需要 {list(REQUIRED_COLS)}"
            "（适配器契约见 chartbook/_recipe-spec.md）")
    df = df.copy()
    df["window_ts"] = pd.to_datetime(df["window_ts"])
    df["err"] = df["y_pred"] - df["y_true"]
    return df


def load_features(path):
    """features 长表：一行 = 一特征一步；f_true 可缺列（缺则补 NaN，质量分箱自动降级）。"""
    p = Path(path)
    df = pd.read_parquet(p) if p.suffix == ".parquet" else pd.read_csv(p)
    missing = [c for c in FEATURE_COLS if c not in df.columns]
    if missing:
        raise ValueError(
            f"features 长表缺列 {missing}；需要 {list(FEATURE_COLS)}(+可选 f_true)"
            "（适配器契约见 chartbook/_recipe-spec.md）")
    df = df.copy()
    if "f_true" not in df.columns:
        df["f_true"] = np.nan
    df["window_ts"] = pd.to_datetime(df["window_ts"])
    return df


def row_rmse(df):
    """每 (model, unit_id, window_ts) 一行的全 horizon RMSE（整行全部 horizon 点的 RMSE——行级口径）。"""
    g = df.groupby(["model", "unit_id", "window_ts"])["err"]
    return (g.apply(lambda e: float(np.sqrt(np.mean(np.square(e)))))
            .rename("rmse").reset_index())


def curve_stats(y, index=None, round_to=3):
    """曲线序列化 + 形状描述符（字段名与判读库绑定）。"""
    v = np.asarray(y, float)
    n = len(v)
    idx = list(index) if index is not None else list(range(n))
    finite = v[np.isfinite(v)]
    if n < 2 or finite.size < 2:
        return {"curve": {str(k): (round(float(val), round_to)
                                   if np.isfinite(val) else None)
                          for k, val in zip(idx, v)},
                "trend": "平", "monotonic": True,
                "max_jump_idx": None, "max_jump": 0.0, "roughness": 0.0,
                "argmax": str(idx[0]) if idx else None,
                "argmin": str(idx[0]) if idx else None}
    diff = np.diff(v)
    j = int(np.nanargmax(np.abs(diff)))
    return {
        "curve": {str(k): (round(float(val), round_to)
                           if np.isfinite(val) else None)
                  for k, val in zip(idx, v)},
        "trend": "上升" if v[-1] > v[0] else ("下降" if v[-1] < v[0] else "平"),
        "monotonic": bool(np.all(diff >= 0) or np.all(diff <= 0)),
        "max_jump_idx": str(idx[j]), "max_jump": round(float(diff[j]), round_to),
        "roughness": round(float(np.nanstd(diff)), round_to),
        "argmax": str(idx[int(np.nanargmax(v))]),
        "argmin": str(idx[int(np.nanargmin(v))]),
    }


def downsample(d: dict, max_points: int = 500) -> dict:
    """曲线字典等距抽样到 ≤max_points 点（首尾必留）。"""
    items = list(d.items())
    if len(items) <= max_points:
        return d
    keep = np.linspace(0, len(items) - 1, max_points).round().astype(int)
    return dict(items[i] for i in sorted(set(keep.tolist())))


def save_outputs(fig, out_dir, recipe_id: str, stats: dict) -> dict:
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    fig.savefig(out / f"{recipe_id}.png", dpi=150, bbox_inches="tight")
    plt.close(fig)
    (out / f"{recipe_id}.json").write_text(
        json.dumps(stats, ensure_ascii=False, indent=2, default=str))
    return stats


def detect_period_steps(values, max_lag: int = 96, threshold: float = 0.5):
    """去趋势后 ACF 的**局部极大值**里取最高峰作主周期(步数)。
    注意不能用全局 argmax:正弦的 ACF 在低阶 lag 本来就高(cos 因子),
    全局 argmax 会答 lag≈2;周期表现为 ACF 先降后升的局部峰。
    峰值 < threshold 或无局部峰时返回 None。
    baseline-skill 的季节基线与 lookback 类图的 lag 桶共用。"""
    x = np.asarray(values, float)
    x = x[np.isfinite(x)]
    if len(x) < 6:
        return None
    x = x - np.polyval(np.polyfit(np.arange(len(x)), x, 1), np.arange(len(x)))
    denom = float(np.dot(x, x))
    if denom < 1e-12:
        return None
    kmax = min(max_lag, len(x) // 2)
    rho = np.array([float(np.dot(x[:-k], x[k:]) / denom)
                    for k in range(1, kmax + 1)])
    best_lag, best_rho = None, threshold
    for i in range(1, len(rho) - 1):
        if rho[i] > rho[i - 1] and rho[i] > rho[i + 1] and rho[i] > best_rho:
            best_lag, best_rho = i + 1, float(rho[i])
    return best_lag
