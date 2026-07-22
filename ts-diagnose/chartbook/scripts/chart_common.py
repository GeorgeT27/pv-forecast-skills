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
import matplotlib.pyplot as plt  # noqa: E402

REQUIRED_COLS = ("window_ts", "unit_id", "model", "horizon_step",
                 "y_true", "y_pred")


def setup_font():
    for font in ("Arial Unicode MS", "PingFang SC", "SimHei",
                 "Noto Sans CJK SC"):
        if font in {f.name for f in matplotlib.font_manager.fontManager.ttflist}:
            plt.rcParams["font.family"] = font
            break
    plt.rcParams["axes.unicode_minus"] = False


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


def row_rmse(df):
    """每 (model, unit_id, window_ts) 一行的全 horizon RMSE（rmse_192 口径泛化）。"""
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
                "max_jump_idx": str(idx[0]) if idx else None,
                "max_jump": 0.0, "roughness": 0.0,
                "argmax": None, "argmin": None}
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
