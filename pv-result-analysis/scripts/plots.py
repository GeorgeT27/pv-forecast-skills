"""光伏预测结果分析 —— 图谱库（对应 SKILL.md 图谱目录 #1-#12）。

设计原则（见 SKILL.md 输出与结论规范）：
- 图为双读者设计（人 + 模型）：关键数值直接标注在图上；
- 每个函数除 PNG 外同时落盘同名 .stats.json —— 相关系数、KS/PSI、R² 等
  分析数值，供大模型直接读取，再结合 references/ 背景写结论；
- 模型配色固定用 data_utils.MODEL_COLORS，跨图可比。

用法示例见 scripts/README.md。所有函数输入均为 data_utils 的标准产物。
"""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd
import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt

from data_utils import MODEL_COLORS, HORIZON, ULTRA_SHORT_IDX, SHORT_SLICE, psi

# 中文字体（macOS: Arial Unicode MS；其他环境自动回退，最坏图上中文变方块但数值仍可读）
for font in ("Arial Unicode MS", "PingFang SC", "SimHei", "Noto Sans CJK SC"):
    if font in {f.name for f in matplotlib.font_manager.fontManager.ttflist}:
        plt.rcParams["font.family"] = font
        break
plt.rcParams["axes.unicode_minus"] = False


def _save(fig, out_png: str | Path, stats: dict):
    out_png = Path(out_png)
    out_png.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(out_png, dpi=150, bbox_inches="tight")
    plt.close(fig)
    out_png.with_suffix(".stats.json").write_text(
        json.dumps(stats, ensure_ascii=False, indent=2, default=str))
    return stats


def _color(name):
    return MODEL_COLORS.get(name, "gray")


# ---------------------------------------------------------------- #1 真值-预测归因散点
def fig01_true_vs_pred(P: np.ndarray, Y: np.ndarray, model: str, out_png,
                       pick: str = "all"):
    """pick: 'all' 全部点 | 'ultra' 第16点 | 'short' [59:155]。"""
    if pick == "ultra":
        p, y = P[:, ULTRA_SHORT_IDX], Y[:, ULTRA_SHORT_IDX]
    elif pick == "short":
        p, y = P[:, SHORT_SLICE].ravel(), Y[:, SHORT_SLICE].ravel()
    else:
        p, y = P.ravel(), Y.ravel()
    mask = ~(np.isnan(p) | np.isnan(y))
    p, y = p[mask], y[mask]
    slope, intercept = np.polyfit(y, p, 1)
    r2 = float(np.corrcoef(y, p)[0, 1] ** 2)
    fig, ax = plt.subplots(figsize=(6, 6))
    ax.hexbin(y, p, gridsize=60, cmap="viridis", mincnt=1)
    lim = [0, max(y.max(), p.max()) * 1.02]
    ax.plot(lim, lim, "r--", lw=1, label="y = x")
    ax.plot(lim, [slope * v + intercept for v in lim], "orange", lw=1.5,
            label=f"回归: slope={slope:.3f}")
    ax.text(0.03, 0.95, f"R² = {r2:.4f}\nslope = {slope:.3f}",
            transform=ax.transAxes, va="top",
            bbox=dict(fc="white", alpha=0.85))
    ax.set_xlabel("真实功率"), ax.set_ylabel("预测功率")
    ax.set_title(f"#1 True vs Pred — {model} ({pick})"), ax.legend(loc="lower right")
    return _save(fig, out_png, {"fig": 1, "model": model, "pick": pick,
                                "r2": r2, "slope": float(slope),
                                "note": "slope<1 → 大功率段被系统性压低"})


# ---------------------------------------------------------------- #2 模型间误差相关热力图
def fig02_error_corr(sample_rmse_or_err: dict[str, pd.Series], out_png,
                     by_month: bool = False):
    """输入 {模型名: 逐样本日均 over_error 或逐样本 RMSE 序列}（各模型须同 index）。
    by_month=True 时逐月分面。"""
    df = pd.DataFrame(sample_rmse_or_err)
    # 长模型名（fourierMoBA、PatchTST…）直接当刻度会互相压叠：>4 字符的改用编号，
    # 编号→全名的映射放图底一行图例；stats.json 的 corr 键保持全名不受影响
    labels = [n if len(n) <= 4 else str(i + 1) for i, n in enumerate(df.columns)]
    legend = {lab: n for lab, n in zip(labels, df.columns) if lab != n}
    def _corr_ax(ax, sub, title, show_ylabels=True):
        c = sub.corr()
        ax.imshow(c, vmin=0, vmax=1, cmap="RdYlGn_r")
        ax.set_xticks(range(len(c)), labels)
        ax.set_yticks(range(len(c)), labels if show_ylabels else [""] * len(c))
        for i in range(len(c)):
            for j in range(len(c)):
                ax.text(j, i, f"{c.iloc[i, j]:.2f}", ha="center", va="center",
                        fontsize=8)
        ax.set_title(title, fontsize=10)
        return c
    stats = {"fig": 2, "corr": {}}
    if by_month:
        months = sorted(df.index.to_period("M").unique())
        n = len(months)
        fig, axes = plt.subplots(1, n, figsize=(3.2 * n, 3.4))
        for k, (ax, m) in enumerate(zip(np.atleast_1d(axes), months)):
            c = _corr_ax(ax, df[df.index.to_period("M") == m], str(m),
                         show_ylabels=(k == 0))
            stats["corr"][str(m)] = c.round(3).to_dict()
    else:
        fig, ax = plt.subplots(figsize=(4.5, 4))
        c = _corr_ax(ax, df, "#2 over_error 模型间相关（全周期）")
        stats["corr"]["all"] = c.round(3).to_dict()
    if legend:
        fig.text(0.5, 0.005, "   ".join(f"{k}={v}" for k, v in legend.items()),
                 ha="center", fontsize=9)
        stats["labels"] = legend
    stats["note"] = "相关>0.95 → 高度同质化，ensemble 组合增益有限"
    return _save(fig, out_png, stats)


# ---------------------------------------------------------------- #4 逐样本 RMSE 时间序列
def fig04_sample_rmse_ts(sample_rmse: dict[str, pd.Series], out_png,
                         month: str | None = None, top_bad: int = 5):
    fig, ax = plt.subplots(figsize=(14, 4))
    worst = {}
    for name, s in sample_rmse.items():
        if month:
            s = s[s.index.to_period("M") == month]
        ax.plot(s.index, s.values, lw=0.8, color=_color(name), label=name)
        daily = s.groupby(s.index.date).mean()
        worst[name] = daily.nlargest(top_bad).round(3).to_dict()
    ref = list(sample_rmse)[0]
    for d in list(worst[ref])[:top_bad]:      # 标注第一个模型的坏天日期
        ax.axvline(pd.Timestamp(d), color="gray", ls=":", lw=0.8)
        ax.text(pd.Timestamp(d), ax.get_ylim()[1] * 0.97, str(d)[5:],
                rotation=90, va="top", fontsize=7, color="gray")
    ax.set_title(f"#4 逐样本RMSE时间序列 {month or '全周期'}")
    ax.set_ylabel("RMSE (行内192点)"), ax.legend(ncol=len(sample_rmse))
    return _save(fig, out_png, {"fig": 4, "month": month, "worst_days": worst})


# ---------------------------------------------------------------- #5 按预报时效误差曲线
def fig05_horizon_error(over_error: dict[str, np.ndarray], out_png):
    fig, axes = plt.subplots(2, 1, figsize=(10, 6), sharex=True)
    stats = {"fig": 5, "rmse_at_ultra_idx": {}, "rmse_short_window": {}}
    for name, e in over_error.items():
        rmse_h = np.sqrt(np.nanmean(e ** 2, axis=0))
        bias_h = np.nanmean(e, axis=0)
        axes[0].plot(rmse_h, color=_color(name), label=name)
        axes[1].plot(bias_h, color=_color(name))
        stats["rmse_at_ultra_idx"][name] = float(rmse_h[ULTRA_SHORT_IDX])
        stats["rmse_short_window"][name] = float(
            np.sqrt(np.nanmean(e[:, SHORT_SLICE] ** 2)))
    for ax in axes:
        ax.axvline(ULTRA_SHORT_IDX, color="k", ls="--", lw=0.8)
        ax.axvspan(SHORT_SLICE.start, SHORT_SLICE.stop, alpha=0.12, color="orange")
    axes[0].text(ULTRA_SHORT_IDX + 2, axes[0].get_ylim()[1] * 0.9, "超短期 idx16",
                 fontsize=8)
    axes[0].set_ylabel("RMSE"), axes[1].set_ylabel("bias (pred−true)")
    axes[1].axhline(0, color="k", lw=0.5), axes[1].set_xlabel("预报步 (0–191)")
    axes[0].set_title("#5 误差随预报时效"), axes[0].legend(ncol=len(over_error))
    return _save(fig, out_png, stats)


# ---------------------------------------------------------------- #6 日内时段误差剖面
def fig06_intraday_profile(over_error: dict[str, np.ndarray],
                           timestamps: pd.Series, out_png):
    """按目标物理时刻聚合（行起点 + 步序 → 目标时刻的 time-of-day）。"""
    fig, axes = plt.subplots(2, 1, figsize=(10, 6), sharex=True)
    stats = {"fig": 6, "worst_hour_rmse": {}, "bias_asymmetry": {}}
    base = pd.DatetimeIndex(timestamps)
    for name, e in over_error.items():
        rec = []
        for step in range(e.shape[1]):
            tod = ((base + pd.Timedelta("15min") * step).hour * 60
                   + (base + pd.Timedelta("15min") * step).minute)
            rec.append(pd.DataFrame({"tod": tod, "err": e[:, step]}))
        allr = pd.concat(rec)
        g = allr.groupby("tod")["err"]
        rmse, bias = np.sqrt((g.apply(lambda x: (x ** 2).mean()))), g.mean()
        h = rmse.index / 60
        axes[0].plot(h, rmse.values, color=_color(name), label=name)
        axes[1].plot(h, bias.values, color=_color(name))
        stats["worst_hour_rmse"][name] = float(rmse.idxmax() / 60)
        neg = allr[allr["err"] < 0]["err"]
        stats["bias_asymmetry"][name] = {
            "mean_under": float(neg.mean()),                     # 低估深度
            "mean_over": float(allr[allr["err"] > 0]["err"].mean()),
        }
    axes[1].axhline(0, color="k", lw=0.5)
    axes[0].set_ylabel("RMSE"), axes[1].set_ylabel("bias")
    axes[1].set_xlabel("目标时刻 (h)"), axes[0].set_title("#6 日内时段误差剖面")
    axes[0].legend(ncol=len(over_error))
    return _save(fig, out_png, stats)


# ---------------------------------------------------------------- #7 坏天定位
def fig07_daily_rmse(sample_rmse: pd.Series, model: str, out_png, top: int = 15):
    daily = sample_rmse.groupby(sample_rmse.index.date).mean().sort_values(
        ascending=False)
    fig, ax = plt.subplots(figsize=(10, 4))
    head = daily.head(top)
    ax.bar([str(d) for d in head.index], head.values, color=_color(model))
    ax.tick_params(axis="x", rotation=75, labelsize=7)
    ax.set_title(f"#7 最差{top}天 — {model}"), ax.set_ylabel("日均RMSE")
    return _save(fig, out_png, {"fig": 7, "model": model,
                                "worst_days": head.round(3).to_dict()})


# ---------------------------------------------------------------- #8 天气分型条件对比
def fig08_weather_conditional(sample_rmse: dict[str, pd.Series],
                              wclass: pd.DataFrame, out_png):
    """wclass: data_utils.daily_weather_class 的输出（index=date, 列含 wclass）。"""
    order = ["晴稳", "多云平稳", "阴稳", "多云波动", "突变日"]
    fig, axes = plt.subplots(1, 2, figsize=(13, 4.2),
                             gridspec_kw={"width_ratios": [3, 2]})
    stats = {"fig": 8, "rmse_by_class": {}, "class_share_by_month": {}}
    width = 0.8 / len(sample_rmse)
    for i, (name, s) in enumerate(sample_rmse.items()):
        daily = s.groupby(s.index.date).mean()
        joined = wclass.join(daily.rename("rmse"), how="inner")
        m = joined.groupby("wclass")["rmse"].mean().reindex(order)
        xs = np.arange(len(order)) + i * width
        axes[0].bar(xs, m.values, width, color=_color(name), label=name)
        for x, v in zip(xs, m.values):
            if np.isfinite(v):
                axes[0].text(x, v, f"{v:.2f}", ha="center", va="bottom", fontsize=7)
        stats["rmse_by_class"][name] = m.round(3).to_dict()
    axes[0].set_xticks(np.arange(len(order)) + 0.4 - width / 2, order)
    axes[0].set_title("#8 分天气类型 RMSE"), axes[0].legend()
    share = (wclass.assign(month=pd.to_datetime(wclass.index.astype(str))
                           .to_period("M").astype(str))
             .groupby(["month", "wclass"]).size().unstack(fill_value=0))
    share = share.div(share.sum(axis=1), axis=0)
    share.reindex(columns=order).plot(kind="bar", stacked=True, ax=axes[1],
                                      colormap="RdYlBu", legend=True)
    axes[1].set_title("各月天气类型占比"), axes[1].tick_params(axis="x", rotation=45)
    stats["class_share_by_month"] = share.round(3).to_dict()
    return _save(fig, out_png, stats)


# ---------------------------------------------------------------- #9 ensemble oracle 差距
def fig09_oracle_gap(sample_rmse: dict[str, pd.Series], out_png,
                     ensemble_key: str = "ensemble"):
    daily = pd.DataFrame({k: v.groupby(v.index.date).mean()
                          for k, v in sample_rmse.items()}).dropna()
    singles = [c for c in daily.columns if c != ensemble_key]
    daily["oracle"] = daily[singles].min(axis=1)
    fig, ax = plt.subplots(figsize=(12, 4))
    for c in daily.columns:
        style = dict(color="black", ls="--", lw=1.5) if c == "oracle" else \
                dict(color=_color(c), lw=0.9)
        ax.plot(pd.to_datetime(daily.index.astype(str)), daily[c], label=c, **style)
    gap = float((daily[ensemble_key] - daily["oracle"]).mean()) \
        if ensemble_key in daily else None
    ax.set_title(f"#9 oracle 差距（ensemble−oracle 日均 = {gap:.3f}）" if gap is not None
                 else "#9 oracle 差距")
    ax.legend(ncol=len(daily.columns)), ax.set_ylabel("日均RMSE")
    return _save(fig, out_png, {
        "fig": 9, "mean_daily_rmse": daily.mean().round(3).to_dict(),
        "ensemble_minus_oracle": gap,
        "oracle_pick_share": daily[singles].idxmin(axis=1).value_counts(
            normalize=True).round(3).to_dict(),
        "note": "差距大 → 动态选模型有改进空间；pick_share 看谁最常是当日最优"})


# ---------------------------------------------------------------- #11 训练/测试同月分布对比
def fig11_train_test_dist(train_series: pd.Series, test_series: pd.Series,
                          varname: str, out_png):
    """输入为重建后的物理连续序列（train=2024, test=2025）。逐月对比 + KS/PSI。"""
    try:
        from scipy.stats import ks_2samp
    except ImportError:
        ks_2samp = None
    months = range(1, 13)
    fig, axes = plt.subplots(2, 6, figsize=(16, 5), sharey=True)
    stats = {"fig": 11, "var": varname, "by_month": {}}
    for ax, m in zip(axes.ravel(), months):
        a = train_series[train_series.index.month == m].dropna().to_numpy()
        b = test_series[test_series.index.month == m].dropna().to_numpy()
        if len(a) < 10 or len(b) < 10:
            ax.set_visible(False)
            continue
        ax.violinplot([a, b], showmedians=True)
        ax.set_xticks([1, 2], ["2024", "2025"]), ax.set_title(f"{m}月", fontsize=9)
        p = psi(a, b)
        ks_p = float(ks_2samp(a, b).pvalue) if ks_2samp else None
        flag = "!" if p > 0.25 else ""
        ax.text(0.5, 0.92, f"PSI={p:.2f}{flag}", transform=ax.transAxes,
                fontsize=7, ha="center",
                color="red" if p > 0.25 else "black")
        stats["by_month"][m] = {"psi": round(p, 3), "ks_p": ks_p,
                                "median_2024": float(np.median(a)),
                                "median_2025": float(np.median(b))}
    fig.suptitle(f"#11 {varname} 分布 2024 vs 2025（PSI>0.25 显著漂移）")
    return _save(fig, out_png, stats)


# ---------------------------------------------------------------- #12 功率-辐照映射对比
def fig12_power_ghi_mapping(power_train, ghi_train, power_test, ghi_test,
                            out_png, bins: int = 20):
    """输入均为物理连续序列；按 GHI 分位分箱画两年的功率均值曲线。"""
    fig, ax = plt.subplots(figsize=(7, 5))
    stats = {"fig": 12, "curve": {}}
    for label, p, g, color in [("2024", power_train, ghi_train, "steelblue"),
                               ("2025", power_test, ghi_test, "firebrick")]:
        df = pd.concat([p.rename("power"), g.rename("ghi")], axis=1).dropna()
        df = df[df["ghi"] > 0]
        df["bin"] = pd.qcut(df["ghi"], bins, duplicates="drop")
        c = df.groupby("bin", observed=True).agg(ghi=("ghi", "mean"),
                                                 power=("power", "mean"))
        ax.plot(c["ghi"], c["power"], "-o", ms=3, color=color, label=label)
        stats["curve"][label] = {f"{r.ghi:.0f}": round(r.power, 2)
                                 for r in c.itertuples()}
    ax.set_xlabel("GHI"), ax.set_ylabel("平均功率")
    ax.set_title("#12 功率-辐照映射 2024 vs 2025"), ax.legend()
    stats["note"] = "曲线整体位移 → 组件衰减/扩容/限电改变物理映射，所有模型同时受害"
    return _save(fig, out_png, stats)
