"""rolling-stability：日粒度 RMSE/bias 的滚动走势 + 二分分段变点检测 +
日历（月/星期）分组——性能是否随时间漂移、从哪天开始。

日指标 = 当日各行 row_rmse 的均值（行与行等权；与点级 pool 不同，量纲注意）。
变点：对日 RMSE 序列做贪心二分分段（SSE 增益最大处切），仅保留
|后段均值−前段均值| > min_shift_frac × 全序列 std 的切点，至多 max_cp 个。
零随机、零外部依赖，确定性可回收。
"""
from __future__ import annotations

import argparse

import numpy as np
import pandas as pd

import chart_common as cc

RECIPE_ID = "rolling-stability"


def _best_split(v: np.ndarray, min_seg: int):
    n = len(v)
    if n < 2 * min_seg:
        return None, 0.0
    total = float(np.sum((v - v.mean()) ** 2))
    best_i, best_gain = None, 0.0
    for i in range(min_seg, n - min_seg + 1):
        sse = (float(np.sum((v[:i] - v[:i].mean()) ** 2))
               + float(np.sum((v[i:] - v[i:].mean()) ** 2)))
        gain = total - sse
        if gain > best_gain:
            best_i, best_gain = i, gain
    return best_i, best_gain


def detect_changepoints(values: np.ndarray, dates: list[str],
                        max_cp: int, min_shift_frac: float,
                        min_seg: int) -> list[dict]:
    thr = min_shift_frac * float(np.std(values))
    segments = [(0, len(values))]
    found = []
    for _ in range(max_cp):
        cand = []
        for lo, hi in segments:
            i, gain = _best_split(values[lo:hi], min_seg)
            if i is not None:
                cand.append((gain, lo, hi, lo + i))
        cand.sort(reverse=True)
        accepted = False
        for gain, lo, hi, cut in cand:
            before = float(np.mean(values[lo:cut]))
            after = float(np.mean(values[cut:hi]))
            if abs(after - before) > thr:
                found.append({"date": dates[cut],
                              "before_mean": round(before, 4),
                              "after_mean": round(after, 4),
                              "shift": round(after - before, 4)})
                segments.remove((lo, hi))
                segments += [(lo, cut), (cut, hi)]
                accepted = True
                break
        if not accepted:
            break
    return sorted(found, key=lambda c: -abs(c["shift"]))


def compute(df: pd.DataFrame, roll_days: int = 7, max_cp: int = 3,
            min_shift_frac: float = 0.3, min_seg: int = 5) -> dict:
    rr = cc.row_rmse(df)
    rr["date"] = pd.to_datetime(rr["window_ts"]).dt.strftime("%Y-%m-%d")
    bias = df.groupby(["model", df["window_ts"].dt.strftime("%Y-%m-%d")])[
        "err"].mean()
    out = {"recipe": RECIPE_ID,
           "params": {"roll_days": roll_days, "max_cp": max_cp,
                      "min_shift_frac": min_shift_frac, "min_seg": min_seg},
           "models": {},
           "note": "日指标=当日各行 row_rmse 均值；变点=贪心二分分段+幅度阈值闸。"}
    for m, g in rr.groupby("model"):
        daily = g.groupby("date")["rmse"].mean().sort_index()
        rolling = daily.rolling(roll_days, min_periods=1).mean()
        dates = list(daily.index)
        dts = pd.to_datetime(daily.index)
        month = daily.groupby(dts.strftime("%Y-%m")).mean()
        dow = daily.groupby(dts.dayofweek.astype(str)).mean()
        st = cc.curve_stats(daily.values, index=dates)
        st["curve"] = cc.downsample(st["curve"])
        out["models"][str(m)] = {
            "daily_rmse": cc.downsample(
                {k: round(float(v), 4) for k, v in daily.items()}),
            "rolling_rmse": cc.downsample(
                {k: round(float(v), 4) for k, v in rolling.items()}),
            "daily_bias": cc.downsample(
                {k: round(float(v), 4) for k, v in bias[m].items()}),
            "changepoints": detect_changepoints(
                daily.values.astype(float), dates, max_cp,
                min_shift_frac, min_seg),
            "by_month": {k: round(float(v), 4) for k, v in month.items()},
            "by_dayofweek": {k: round(float(v), 4) for k, v in dow.items()},
            "daily_curve": st,
        }
    return out


def render(stats: dict):
    import matplotlib.pyplot as plt
    cc.setup_font()
    fig, ax = plt.subplots(figsize=(12, 4))
    for m, s in stats["models"].items():
        xs = pd.to_datetime(list(s["rolling_rmse"]))
        ax.plot(xs, list(s["rolling_rmse"].values()), label=f"{m} rolling")
        for cp in s["changepoints"]:
            ax.axvline(pd.Timestamp(cp["date"]), color="red", ls=":", lw=1)
    ax.set_ylabel("滚动日均 RMSE")
    ax.set_title("rolling-stability（红虚线=变点）")
    ax.legend()
    fig.autofmt_xdate()
    return fig


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--pred", required=True)
    ap.add_argument("--out-dir", required=True)
    ap.add_argument("--roll-days", type=int, default=7)
    ap.add_argument("--max-cp", type=int, default=3)
    ap.add_argument("--min-shift-frac", type=float, default=0.3)
    ap.add_argument("--min-seg", type=int, default=5)
    a = ap.parse_args(argv)
    stats = compute(cc.load_predictions(a.pred), roll_days=a.roll_days,
                    max_cp=a.max_cp, min_shift_frac=a.min_shift_frac,
                    min_seg=a.min_seg)
    cc.save_outputs(render(stats), a.out_dir, RECIPE_ID, stats)


if __name__ == "__main__":
    main()
