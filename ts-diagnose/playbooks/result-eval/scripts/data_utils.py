"""光伏预测结果分析 —— 数据工具库。

数据格式约定（详见 SKILL.md 项目背景）：
- parquet 每行：timestamp（序列起点）+ 各数据列为从该时刻起的定长 list；
- 相邻行错开 15 分钟，窗口重叠 671/672 —— 任何分布统计前先用 rebuild_series
  重建物理连续序列，否则同一物理点被重复计数几百次。

列名与实际 parquet 不符时，只改下方 CONFIG，不改函数逻辑。
"""
from __future__ import annotations

import numpy as np
import pandas as pd

# ---------------------------------------------------------------- CONFIG
TIMESTAMP_COL = "timestamp"
# true_label.parquet 常沿用完整训练 schema（带 observe_power/GHI/SSRD_pos/t2m_pos… 一堆特征列）；
# 评估只用 observe_power_future 这一列，其余对本技能无关。取 label 一律走 LABEL_COL，勿混入其他列。
LABEL_COL = "observe_power_future"   # 未来 192 点真实功率（label）—— true_label 里唯一有用的列
GHI_COL = "GHI-solargis"             # 气象/漂移分析用；来源应是训练集 parquet，不是 true_label
FREQ = pd.Timedelta("15min")
POINTS_PER_DAY = 96
HORIZON = 192                        # 预测时域 48h
# 考核取点（0-indexed，见 SKILL.md 五种口径）
ULTRA_SHORT_IDX = 16                 # 超短期：第 16 个点（4h）
SHORT_SLICE = slice(59, 155)         # 短期：09:00 行的 [59:155]，次日全天 96 点

MODEL_COLORS = {                     # 全部图固定配色，跨图可比
    "M1": "#1f77b4",
    "M2": "#ff7f0e",
    "M3": "#2ca02c",
    "M4": "#d62728",
    "ensemble": "#9467bd",
}


# ---------------------------------------------------------------- 读取与对齐
def load_table(path: str, timestamp_col: str = TIMESTAMP_COL) -> pd.DataFrame:
    df = pd.read_parquet(path)
    if timestamp_col not in df.columns:
        # 常见坑：predicted.parquet 往往把 timestamp 存成 index 而不是普通列
        idx = df.index
        looks_time = idx.name == timestamp_col or isinstance(idx, pd.DatetimeIndex)
        if not looks_time and idx.dtype == object:
            try:
                pd.to_datetime(idx[:5])
                looks_time = True
            except (ValueError, TypeError):
                pass
        if not looks_time:
            raise KeyError(f"'{timestamp_col}' 不在列中，index 也不是时间戳；"
                           f"实际列: {list(df.columns)}, index: {idx.dtype}/{idx.name}")
        df = df.rename_axis(timestamp_col).reset_index()
    df[timestamp_col] = pd.to_datetime(df[timestamp_col])
    return df.sort_values(timestamp_col).reset_index(drop=True)


def to_matrix(df: pd.DataFrame, col: str) -> np.ndarray:
    """list 单元格列 -> (n_rows, L) float ndarray。"""
    return np.stack([np.asarray(v, dtype=float) for v in df[col].to_numpy()])


def align(pred_df: pd.DataFrame, label_df: pd.DataFrame,
          pred_col: str, label_col: str = LABEL_COL):
    """按 timestamp 内连接，返回 (timestamps, P, Y)，P/Y 形状 (n, 192)。"""
    merged = pd.merge(
        pred_df[[TIMESTAMP_COL, pred_col]],
        label_df[[TIMESTAMP_COL, label_col]],
        on=TIMESTAMP_COL, how="inner",
    )
    if len(merged) < max(len(pred_df), len(label_df)):
        print(f"[align] 警告: 对齐后 {len(merged)} 行 "
              f"(pred {len(pred_df)} / label {len(label_df)})，有时间戳缺失")
    P, Y = to_matrix(merged, pred_col), to_matrix(merged, label_col)
    assert P.shape == Y.shape and P.shape[1] == HORIZON, f"维度异常: {P.shape} vs {Y.shape}"
    return merged[TIMESTAMP_COL].reset_index(drop=True), P, Y


def error_matrices(P: np.ndarray, Y: np.ndarray, timestamps: pd.Series):
    """返回 (over_error 矩阵, 逐样本 RMSE 序列)。over_error = pred - true。"""
    over_error = P - Y
    sample_rmse = pd.Series(np.sqrt((over_error ** 2).mean(axis=1)),
                            index=pd.DatetimeIndex(timestamps), name="sample_rmse")
    return over_error, sample_rmse


# ---------------------------------------------------------------- 序列重建与质检
def rebuild_series(df: pd.DataFrame, col: str, offset: int = 0) -> pd.Series:
    """滚动窗口 -> 物理连续序列：每行取 list 第 offset 个点，时间 = timestamp + offset*15min。"""
    m = to_matrix(df, col)
    ts = pd.DatetimeIndex(df[TIMESTAMP_COL]) + FREQ * offset
    return pd.Series(m[:, offset], index=ts, name=col).sort_index()


def check_window_consistency(df: pd.DataFrame, col: str, n_checks: int = 300,
                             seed: int = 0) -> float:
    """抽查滚动窗口一致性：行 t 第 k 点 == 行 t+1 第 k-1 点。返回不一致比例。
    比例 > 0 说明窗口构造有 bug，所有取点口径不可信——立刻停下报告。"""
    m = to_matrix(df, col)
    ts = pd.DatetimeIndex(df[TIMESTAMP_COL])
    adjacent = np.where((ts[1:] - ts[:-1]) == FREQ)[0]
    if len(adjacent) == 0:
        return np.nan
    rng = np.random.default_rng(seed)
    rows = rng.choice(adjacent, size=min(n_checks, len(adjacent)), replace=False)
    ks = rng.integers(1, m.shape[1], size=len(rows))
    bad = sum(not np.isclose(m[r, k], m[r + 1, k - 1], equal_nan=True)
              for r, k in zip(rows, ks))
    return bad / len(rows)


def basic_quality_checks(df: pd.DataFrame) -> dict:
    """基础完整性检查（Step 1 质检）：重复时间戳、网格缺口、最长缺失段。"""
    ts = pd.DatetimeIndex(df[TIMESTAMP_COL]).sort_values()
    gaps = ts[1:] - ts[:-1]
    gap_mask = gaps > FREQ
    return {
        "n_rows": len(ts),
        "time_range": [str(ts[0]), str(ts[-1])],
        "duplicated_timestamps": int(ts.duplicated().sum()),
        "n_gaps": int(gap_mask.sum()),
        "max_gap": str(gaps.max()) if len(gaps) else None,
        "gap_locations": [str(t) for t in ts[:-1][gap_mask][:20]],  # 最多列 20 处
    }


def longest_constant_run(series: pd.Series, min_value: float = 0.0) -> dict:
    """任意水平上的最长常值段（传感器卡死检测，与限电平顶不同层面）。"""
    v = series.to_numpy()
    run = best = 1
    best_end = 0
    for i in range(1, len(v)):
        run = run + 1 if (v[i] == v[i - 1] and v[i] > min_value) else 1
        if run > best:
            best, best_end = run, i
    return {"longest_run": int(best),
            "at": str(series.index[best_end]) if best > 1 else None}


def scan_suspect_days(power: pd.Series, capacity: float | None = None) -> pd.DataFrame:
    """label 可疑模式扫描（输入为 rebuild_series 后的连续功率序列）。
    返回 DataFrame(date, issue)。命中日期须提交用户核对 -> event-log.md。"""
    cap = capacity or float(power.quantile(0.999))
    out = []
    for date, day in power.groupby(power.index.date):
        night = day.between_time("00:00", "04:00")
        noon = day.between_time("10:00", "14:00")
        if len(night) and (night > 0.02 * cap).any():
            out.append((date, "夜间功率非零"))
        if len(noon) and (noon == 0).all():
            out.append((date, "日照时段整段为零(疑似停机/缺测)"))
        daytime = day.between_time("08:00", "16:00")
        if len(daytime) >= 8:
            v = daytime.to_numpy()
            run, best = 1, 1
            for i in range(1, len(v)):
                run = run + 1 if (v[i] == v[i - 1] and v[i] > 0.2 * cap) else 1
                best = max(best, run)
            if best >= 8:
                out.append((date, "白天连续平顶(疑似限电压制)"))
    return pd.DataFrame(out, columns=["date", "issue"])


# ---------------------------------------------------------------- 扩容检测
def detect_capacity_expansion(power: pd.Series,
                               window_months: int = 1,
                               jump_ratio: float = 0.10,
                               min_days: int = 10) -> pd.DataFrame:
    """检测装机容量台阶式跳升（扩容）。

    逻辑：以月为窗口计算滚动峰值（P99），若相邻两月峰值涨幅 > jump_ratio
    且两侧各有 min_days 天数据，则标记为扩容嫌疑点。
    返回 DataFrame(month, p99_power, jump_ratio, is_expansion_suspect)。
    发现嫌疑后需核对 event-log.md，确认则按扩容日期分段归一化。
    """
    daily_max = power.resample("D").max().dropna()
    monthly_p99 = daily_max.resample("MS").quantile(0.99)
    monthly_count = daily_max.resample("MS").count()

    rows = []
    months = monthly_p99.index.tolist()
    for i in range(1, len(months)):
        prev_m, curr_m = months[i - 1], months[i]
        prev_p99, curr_p99 = monthly_p99[prev_m], monthly_p99[curr_m]
        if monthly_count[prev_m] < min_days or monthly_count[curr_m] < min_days:
            continue
        if prev_p99 <= 0:
            continue
        ratio = (curr_p99 - prev_p99) / prev_p99
        rows.append({
            "month": curr_m,
            "prev_p99": round(prev_p99, 4),
            "curr_p99": round(curr_p99, 4),
            "jump_ratio": round(ratio, 4),
            "is_expansion_suspect": ratio > jump_ratio,
        })
    return pd.DataFrame(rows)


# ---------------------------------------------------------------- 天气分型
def clear_sky_envelope(ghi: pd.Series) -> pd.Series:
    """晴天包络代理：当月每个时刻(tod) GHI 的 95 分位曲线，index=(month, tod)。
    供 daily_weather_class 复用；跨站/跨期漂移诊断应把 train 侧（基准）的包络当共享
    基准传给两年，否则各年自归一化会掩盖整体变暗/变亮。"""
    f = ghi.to_frame("ghi")
    f["month"], f["tod"] = f.index.month, f.index.time
    return f.groupby(["month", "tod"])["ghi"].quantile(0.95).rename("env")


def daily_kt_sigma(ghi: pd.Series, envelope: pd.Series | None = None) -> pd.DataFrame:
    """按天算 kt 与 sigma（不分类）。index=date，列 [kt, sigma]。
    kt = 当日 GHI 总量 / 晴天包络总量；sigma = 白天段 GHI 一阶差分标准差 / 包络峰值。
    envelope=None 时用 ghi 自身算包络；跨站/跨期漂移诊断传入统一基准。"""
    env = clear_sky_envelope(ghi) if envelope is None else envelope
    f = ghi.to_frame("ghi")
    f["month"], f["tod"] = f.index.month, f.index.time
    f = f.join(env, on=["month", "tod"])
    rows = []
    for date, day in f.groupby(f.index.date):
        env_sum, env_peak = day["env"].sum(), day["env"].max()
        if not (env_sum and env_sum > 0):
            continue
        kt = day["ghi"].sum() / env_sum
        daytime = day[day["env"] > 0.05 * env_peak]["ghi"]
        sigma = daytime.diff().std() / env_peak if env_peak > 0 else np.nan
        rows.append((date, kt, sigma))
    return pd.DataFrame(rows, columns=["date", "kt", "sigma"]).set_index("date")


def daily_weather_class(ghi: pd.Series, kt_hi: float = 0.65, kt_lo: float = 0.35,
                        jump: float = 0.30, sigma_q: float = 0.70,
                        envelope: pd.Series | None = None,
                        sig_hi: float | None = None) -> pd.DataFrame:
    """日级天气分型（输入为 rebuild_series 后的连续 GHI 序列）。
    五类（低波动日按 kt 分三档，高波动/突变另立）：
      - 晴稳：kt >= kt_hi，明亮平稳；
      - 多云平稳：kt_lo <= kt < kt_hi（默认档），中等云量、日内平稳；
      - 阴稳：kt < kt_lo，真正的阴天（持续厚云）、日内平稳；
      - 多云波动：sigma > sig_hi（默认取当期 sigma 的 sigma_q 分位），日内剧烈起伏（覆盖 kt 分档）；
      - 突变日：|kt - 前一日 kt| > jump，相对昨日天气型骤变（优先级最高，覆盖全部）。
    envelope / sig_hi：默认 None 时从输入自算；**跨站/跨期漂移诊断须传入统一基准**（用 train 的
    包络与 sigma 阈值分类 2025），否则各年自归一化会把"整体变暗/更多波动天"抹平——见
    weather_class_drift。结果供图#8 与分布漂移诊断复用，落盘 weather_class.csv。"""
    out = daily_kt_sigma(ghi, envelope)
    if sig_hi is None:
        sig_hi = out["sigma"].quantile(sigma_q)
    cls = pd.Series("多云平稳", index=out.index)        # 中等 kt、低波动 = 默认档
    cls[out["kt"] >= kt_hi] = "晴稳"
    cls[out["kt"] < kt_lo] = "阴稳"                      # 真正的阴天（低 kt）
    cls[out["sigma"] > sig_hi] = "多云波动"              # 高波动覆盖 kt 分档
    cls[(out["kt"] - out["kt"].shift(1)).abs() > jump] = "突变日"
    out["wclass"] = cls
    out.attrs["sig_hi"] = float(sig_hi)                  # 便于跨站/跨期复用同一阈值
    return out


# ---------------------------------------------------------------- 统计工具
def psi(expected: np.ndarray, actual: np.ndarray, bins: int = 10) -> float:
    """Population Stability Index。<0.1 稳定，0.1-0.25 轻微漂移，>0.25 显著漂移。"""
    qs = np.quantile(expected[~np.isnan(expected)], np.linspace(0, 1, bins + 1))
    qs[0], qs[-1] = -np.inf, np.inf
    e = np.histogram(expected, qs)[0] / max(len(expected), 1)
    a = np.histogram(actual, qs)[0] / max(len(actual), 1)
    e, a = np.clip(e, 1e-6, None), np.clip(a, 1e-6, None)
    return float(((a - e) * np.log(a / e)).sum())


# ---------------------------------------------------------------- 分布漂移诊断（train vs test，跨站/跨期通用）
def drift_table(train_df: pd.DataFrame, test_df: pd.DataFrame, cols,
                bins: int = 10) -> pd.DataFrame:
    """特征漂移 / 标签漂移的数值总表：对每个变量列先 rebuild_series 重建物理连续序列，
    再 train vs test **同月对比** PSI + KS（跨站设定下 train=训练站集合、test=留出站）。cols 传气象列做特征漂移、功率标签列做
    标签漂移，口径一致。返回长表：[var, month, psi, ks_p, median_train, median_test,
    n_train, n_test, drift]（drift：PSI>0.25 显著 / 0.1-0.25 轻微 / 否则 稳定）。
    先跑本表定位"哪个变量哪个月漂了"，再用 fig11 把该变量画出来看形态。"""
    try:
        from scipy.stats import ks_2samp
    except ImportError:
        ks_2samp = None
    rows = []
    for col in cols:
        s_tr, s_te = rebuild_series(train_df, col), rebuild_series(test_df, col)
        for m in range(1, 13):
            a = s_tr[s_tr.index.month == m].dropna().to_numpy()
            b = s_te[s_te.index.month == m].dropna().to_numpy()
            if len(a) < 10 or len(b) < 10:
                continue
            p = psi(a, b)
            rows.append({
                "var": col, "month": m, "psi": round(p, 3),
                "ks_p": round(float(ks_2samp(a, b).pvalue), 4) if ks_2samp else None,
                "median_train": round(float(np.median(a)), 2),
                "median_test": round(float(np.median(b)), 2),
                "n_train": len(a), "n_test": len(b),
                "drift": "显著" if p > 0.25 else "轻微" if p > 0.1 else "稳定"})
    return pd.DataFrame(rows)


def weather_class_drift(ghi_train: pd.Series, ghi_test: pd.Series,
                        **kw) -> dict:
    """天气型漂移：用 **train（基准）的晴天包络与 sigma 阈值作共享基准**分类两侧，
    这样"test 整体更亮/更暗、多波动天变多"才显现（各自归一化会抹平）。跨站设定下
    train=训练站集合(pooled)、test=留出站。ghi_* 为 rebuild_series 后的连续 GHI。返回：
      - share：各天气型占比表（DataFrame，行=天气型，列=[train, test, 占比差]）；
      - kt / sigma：两侧日级 kt、sigma 的 PSI + KS（回答"晴空指数分布是否偏移"）；
      - counts：各型天数（披露样本量用）。
    kw 透传 daily_weather_class 的阈值（kt_hi/kt_lo/jump/sigma_q）。"""
    env_ref = clear_sky_envelope(ghi_train)                     # train 作基准包络
    wc_tr = daily_weather_class(ghi_train, envelope=env_ref, **kw)
    sig_ref = wc_tr.attrs["sig_hi"]                             # train 的 sigma 阈值
    wc_te = daily_weather_class(ghi_test, envelope=env_ref, sig_hi=sig_ref, **kw)
    order = ["晴稳", "多云平稳", "阴稳", "多云波动", "突变日"]
    def _share(wc):
        c = wc["wclass"].value_counts()
        return (c / c.sum()).reindex(order).fillna(0.0)
    share = pd.DataFrame({"train": _share(wc_tr), "test": _share(wc_te)})
    share["占比差"] = (share["test"] - share["train"]).round(3)
    share = share.round(3)
    counts = pd.DataFrame({
        "train": wc_tr["wclass"].value_counts().reindex(order).fillna(0).astype(int),
        "test": wc_te["wclass"].value_counts().reindex(order).fillna(0).astype(int)})
    try:
        from scipy.stats import ks_2samp
        ksf = lambda a, b: round(float(ks_2samp(a, b).pvalue), 4)
    except ImportError:
        ksf = lambda a, b: None
    drift = {}
    for v in ["kt", "sigma"]:
        a, b = wc_tr[v].dropna().to_numpy(), wc_te[v].dropna().to_numpy()
        drift[v] = {"psi": round(psi(a, b), 3), "ks_p": ksf(a, b),
                    "median_train": round(float(np.median(a)), 3),
                    "median_test": round(float(np.median(b)), 3)}
    return {"share": share, "counts": counts, "kt": drift["kt"],
            "sigma": drift["sigma"]}


def robustness_check(rmse_a: pd.Series, rmse_b: pd.Series, trim: int = 3) -> dict:
    """模型对比结论的稳健性门槛（SKILL.md 输出规范）：
    ① 按天配对 Wilcoxon；② 剔除差值最大的 trim 天后均值差方向不变。"""
    da = rmse_a.groupby(rmse_a.index.date).mean()
    db = rmse_b.groupby(rmse_b.index.date).mean()
    d = (da - db).dropna()
    try:
        from scipy.stats import wilcoxon
        pval = float(wilcoxon(d).pvalue) if (d != 0).any() else 1.0
    except ImportError:
        pval = None  # scipy 不可用时报告 None，由调用方降级为 bootstrap
    trimmed = d.drop(d.abs().nlargest(trim).index)
    return {
        "mean_diff": float(d.mean()),
        "wilcoxon_p": pval,
        "trimmed_mean_diff": float(trimmed.mean()),
        "direction_stable": bool(np.sign(d.mean()) == np.sign(trimmed.mean())),
        "passed": bool(pval is not None and pval < 0.05
                       and np.sign(d.mean()) == np.sign(trimmed.mean())),
    }
