"""全部指标口径集中在这里：短期与超短期共用同一套定义，改口径只改这一个文件。

三类：
  误差      rmse / nrmse_pct / pooled_rmse / hourly_nrmse —— 归一化分母一律走 resolve_cap
  南网      nanwang_official（短期，逐点 sqrt 平方均值）/ nanwang_ultrashort（超短期，逐点绝对值均值）
            两者都恒用全点（含夜间）：0.2*GCCAPCITY 的分母下限保证夜间点良态，去夜间反而改了口径
  比较      flag_outliers（MAD 离群）/ cf_decomposition（反事实 base-vs-cf 分解）
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from .timeseries import night_mask, window_mask


# ================================================================ 误差
def rmse(a, b):
    return float(np.sqrt(np.mean((a - b) ** 2)))


def resolve_cap(cap, truth=None):
    """归一化分母：给定的 cap 可用就用它，否则拿真值峰值兜底，峰值不为正再退 1.0。
    分母必须为正，否则整列 nRMSE 变 inf/nan/负，排名和离群判定跟着全废。"""
    if cap and cap > 0:
        return float(cap)
    if truth is not None and len(truth):
        peak = float(np.max(truth))
        if peak > 0:
            return peak
    return 1.0


def nrmse_pct(a, b, cap):
    """RMSE 归一化到装机（或峰值）的百分比 —— 跨站可比的唯一形式，绝对 RMSE 不可比。"""
    return rmse(a, b) / cap * 100.0


def pooled_rmse(truth: pd.Series, leads: pd.DataFrame, keep: np.ndarray):
    """16 lead 合并 RMSE：leads 每列减 truth，keep（夜滤）行内所有有限 (lead,目标) 对。-> (rmse|None, n)。"""
    err = leads.sub(truth, axis=0).to_numpy(float)[keep]
    err = err[np.isfinite(err)]
    if err.size == 0:
        return None, 0
    return float(np.sqrt(np.mean(err ** 2))), int(err.size)


def hourly_nrmse(times, err, cap):
    """Aggregate err's RMSE by hour (0..23) / cap*100. Returns length-24 array (no data = nan)."""
    hod = pd.DatetimeIndex(times).hour
    out = np.full(24, np.nan)
    for h in range(24):
        m = hod == h
        if m.any():
            out[h] = np.sqrt(np.mean(err[m] ** 2)) / cap * 100.0
    return out


# ================================================================ 南网「两个细则」
def nanwang_official(p_real, p_pred, gccap):
    """南网「两个细则」official forecast accuracy over aligned arrays, returned in percent:
        (1 - sqrt( mean( ((p_real - p_pred) / max(p_real, 0.2*gccap))^2 ) )) * 100.
    The 0.2*gccap denominator floor keeps night/near-zero points well-defined, so callers should pass
    ALL points (night included, NOT the drop-night subset). Returns None if gccap<=0 or no points."""
    if gccap is None or not (gccap > 0):
        return None
    a = np.asarray(p_real, dtype=float)
    p = np.asarray(p_pred, dtype=float)
    if a.size == 0:
        return None
    denom = np.maximum(a, 0.2 * gccap)            # per-point floor; a is nonneg power, denom always > 0
    r = (a - p) / denom
    return (1.0 - float(np.sqrt(np.mean(r ** 2)))) * 100.0


NANWANG_FACTORS = (1.4, 1.2, 1.0, 0.8, 0.6, 0.4)   # 1.0 = 原官方列，居中放置


def nanwang_factor_row(p_real, p_pred, gccap, factors=NANWANG_FACTORS):
    """南网口径的乘性灵敏度扫描：每个 factor 把预测的每一个点乘以 factor 后重算 nanwang_official。
    不做任何截断，factor>1 的预测可以超过 GCCAPCITY。返回按 factors 顺序排列的 {列名: 值}，
    factor 1.0 沿用原列名 nanwang_official_power，其余为 nanwang_official_power_x<factor>。
    gccap 不可用（None/<=0）或无点时返回 {}。"""
    p = np.asarray(p_pred, dtype=float)
    out = {}
    for f in factors:
        v = nanwang_official(p_real, p * f, gccap)
        if v is None:
            return {}
        out["nanwang_official_power" if f == 1.0 else f"nanwang_official_power_x{f:g}"] = round(v, 4)
    return out


def nanwang_ultrashort(truth: pd.Series, leads: pd.DataFrame, gccap):
    """南网超短期准确率（仅打印不落 CSV）：
        Acc = (1 − mean_t mean_i |P_real(t) − p_i(t)| / max(P_real(t), 0.2·GCCAPCITY)) × 100，
    逐项 sqrt(x²) 即 |x|。恒用全 96 目标点（含夜间，0.2C 分母下限保证良态，不受 --drop-night 影响）。
    缺项跳过：时刻内对可用 lead 取均值，日内对（真值有效且 ≥1 lead 有值）的时刻取均值。
    返回 (百分比, 有效时刻数)；gccap 缺失/非正或无有效时刻 → (None, 0)。"""
    if gccap is None or not (gccap > 0):
        return None, 0
    t = truth.to_numpy(float)
    P = leads.to_numpy(float)
    r = np.abs(t[:, None] - P) / np.maximum(t, 0.2 * gccap)[:, None]
    ok = np.isfinite(r)
    valid_t = np.flatnonzero(ok.any(axis=1))
    if valid_t.size == 0:
        return None, 0
    per_t = np.array([r[j][ok[j]].mean() for j in valid_t])
    return (1.0 - float(per_t.mean())) * 100.0, int(valid_t.size)


# ================================================================ 比较
def flag_outliers(vals, k):
    """> median + k x MAD is flagged as outlier. Returns bool array (valid count <3 or MAD=0 -> all False)."""
    v = np.asarray(vals, float)
    ok = np.isfinite(v)
    out = np.zeros(len(v), bool)
    if ok.sum() < 3:
        return out
    med = np.median(v[ok])
    mad = np.median(np.abs(v[ok] - med)) * 1.4826  # normal-consistent scaling
    thr = med + k * mad if mad > 0 else np.inf
    out[ok] = v[ok] > thr
    return out


def cf_decomposition(p_true, p_base, p_cf, drop_night, night_end_hour, cap, win=None, gccap=None):
    """Take common time points of three series (respecting drop-night + win) -> decomposition metrics. Returns (metrics dict, (times,t,b,c)) or None.
    When gccap is given, also compute the 南网 nanwang_official accuracy for baseline/cf on ALL window points
    (night included, ignoring drop-night, since the 0.2*gccap floor handles zero-power points)."""
    common0 = p_true.index.intersection(p_base.index).intersection(p_cf.index).sort_values()
    if len(common0) == 0:
        return None
    common = common0[night_mask(common0, drop_night, night_end_hour) & window_mask(common0, win)]
    if len(common) == 0:
        return None
    t = p_true.loc[common].to_numpy()
    b = p_base.loc[common].to_numpy()
    c = p_cf.loc[common].to_numpy()
    cap = resolve_cap(cap, t)
    nb = nrmse_pct(b, t, cap)
    nc = nrmse_pct(c, t, cap)
    m = {"n_points": int(len(common)), "capacity": round(cap, 4),
         "nrmse_base": round(nb, 4), "nrmse_cf": round(nc, 4),
         "delta_nrmse": round(nb - nc, 4),
         "frac_explained": round((nb - nc) / nb * 100.0, 2) if nb > 0 else np.nan,
         "coadapt": int(nb - nc < -0.1)}    # only substantial worsening (>0.1 pct point) counts as co-adaptation, excludes noise-level negative delta
    if gccap is not None and gccap > 0:
        allc = common0[window_mask(common0, win)]            # all points in window, night included
        if len(allc) > 0:
            ta, ba, ca = (p_true.loc[allc].to_numpy(), p_base.loc[allc].to_numpy(), p_cf.loc[allc].to_numpy())
            m["GCCAPCITY"] = round(float(gccap), 4)
            nwb, nwc = nanwang_official(ta, ba, gccap), nanwang_official(ta, ca, gccap)
            if nwb is not None:
                m["nanwang_official_base"] = round(nwb, 4)
            if nwc is not None:
                m["nanwang_official_cf"] = round(nwc, 4)
    return m, (common, t, b, c)
