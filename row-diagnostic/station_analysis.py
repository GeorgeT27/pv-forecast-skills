#!/usr/bin/env python3
"""光伏多站预测分析 —— 一个脚本、一次运行同时产出两层视图。完全自包含（pandas/numpy/matplotlib）。

【逐站细看】每站若干张两线对比图（预测 vs 真实），标注 RMSE：
  1) Power   —— 预测功率（predict 表 dtime×站列）vs 真实功率（input 的 observe_power_future）。
  2) 各特征 —— 预测特征 vs 真值特征，二者都在 input 宽表里（list 列）。默认 1 张：
     GHI = GHI_SOLARGIS_predict vs GHI_real_future（后者是这些预测量的公共真值 label）。
     --feature-pairs 可加更多，如 ssrd_pos_1_predict:GHI_real_future:ssrd1。

【全场总览】单张 fleet_overview.png（2×2 仪表盘）+ fleet_ranking.csv，定位「谁最离谱」：
  A1/A2 排行榜 —— 各站按 nRMSE 降序（worst 在顶），中位线 + 离群站红标（功率 + GHI）。
  B  散点     —— GHI-nRMSE vs 功率-nRMSE，一站一点：功率差是 GHI 输入差（右上）
                还是模型/其它问题（左上 = GHI 好但功率仍差）。
  C  热力图   —— 时刻×场站的功率 nRMSE，看谁在哪个钟点坏。

为什么归一化（关键）：绝对 RMSE 被电站规模支配（大站天然大，排名无意义）。
  nRMSE = RMSE / 该站峰值功率（自包含代理容量；有真实装机用 --capacity 更准），单位 %。
  「离谱」= nRMSE 排名靠前 **且** 异常高于全场（> 中位数 + --mad-k×MAD，默认 3，红标）。
  只用 observe_power_future（功率真值）与 GHI_real_future（GHI 真值）两种 label——
  温度等无真值列评不了，总览不涉及。

鲁棒（关键）：每张图/每项指标独立成败。某列缺失、或**某站**该列全空 → 只跳过那一项并告警，
  power 与其它站/其它特征/总览照常输出，绝不整体报错。

【反事实】（--counterfactual 门控，可选）oracle GHI swap：把 GHI 预测列换成 GHI 真值经用户
  的 FastAPI 统一模型重预测，分解每站误差 = 模型底线（GHI 完美仍剩）+ GHI 归因（换真值即消失）。
  每站 2 次调用：基线复现（原特征原样发，与 predict 表核对 = 复现闸）+ 换真值。逐站落盘可断点
  续跑；首跑必 --cf-dry-run 确认 payload。产出 counterfactual_results.csv +
  counterfactual_overview.png（堆叠条：灰=模型的锅、橙=GHI 输入的锅、蓝=换真值反而差=共适应）。
  API 契约：POST {"data":[{行dict}]}（字段=parquet 列名，list 原样，不带站名与真值 label 列）；
  响应 = {"status":..., "predictions":[{"timestamp_win":..., "ensemble":[192值]}, ...]}——
  逐窗返回，只取 ensemble，按响应自带 timestamp_win 摊平去重（同 input 表规则）；
  窗数 ≠ 发送行数 = 对齐闸拦下。兼容回退：响应也可以是一条扁平功率 list（与 predict 表
  该站列按 dtime 排序逐点对应）。

时间对齐：input 某行 timestamp_win=T，则任意 list 列（observe_power_future / *_predict /
  GHI_real_future）第 k 个元素时间 = T+15min×(k+1)（首元素=T+15min）。同站各窗摊平、按绝对
  时间 groupby 去重成连续序列；power 的预测再与 predict 表 dtime 对齐。

配置：--drop-night 去掉每天 00:00–night_end_hour（RMSE 也按去掉后算）；--tick-hours 每几小时
  一个 x 刻度；图宽随点数自适应，600+ 点也铺得开。开关：--no-plots（不出任何图，仍写 CSV）、
  --no-station-plots（不出逐站曲线，仍写站级 CSV）、--no-fleet（不出总览与 fleet_ranking）。

用法：
  python3 station_analysis.py --input input.parquet --predict predict.parquet [--out-dir OUT]
    [--drop-night --night-end-hour 5] [--tick-hours 1] [--step-min 15]
    [--feature-pairs "GHI_SOLARGIS_predict:GHI_real_future:GHI,ssrd_pos_1_predict:GHI_real_future:ssrd1"]
    [--top-n 30] [--mad-k 3] [--capacity "st1:500,st2:5"] [--ghi-pred ... --ghi-true ...]
    [--station-col station --win-col timestamp_win --power-col observe_power_future --dtime-col dtime]
    [--no-plots] [--no-station-plots] [--no-fleet]
    [--counterfactual --api-url URL [--cf-dry-run] [--cf-stations st1,st2] [--cf-force]
     [--cf-swap "GHI_SOLARGIS_predict:GHI_real_future"] [--cf-exclude-cols ...]
     [--cf-timeout 120] [--cf-retries 1] [--cf-check-tol 1.0] [--cf-curves]]
"""
from __future__ import annotations

import argparse
import json
import os
import urllib.request

import numpy as np
import pandas as pd

DEFAULT_FEATURE_PAIRS = [("GHI_SOLARGIS_predict", "GHI_real_future", "GHI")]


# ================================================================ 公共：摊平 / 夜间 / 对齐
def sanitize(s) -> str:
    return "".join(c if str(c).isalnum() else "_" for c in str(s))


def series_from_lists(wins, lists, step) -> pd.Series:
    """把一个站某 list 列的所有窗摊平成 (绝对时间→值) 序列，按时间 groupby 去重。
    非 list / None / NaN 单元格自动跳过（鲁棒：某站该特征缺失 → 返回空序列）。"""
    times, vals = [], []
    for t0, fut in zip(wins, lists):
        if fut is None or np.ndim(fut) == 0:          # 标量/None/NaN → 跳过
            continue
        arr = np.asarray(fut, dtype=float).ravel()
        if arr.size == 0:
            continue
        t0 = pd.Timestamp(t0)
        for k, v in enumerate(arr):
            if np.isfinite(v):
                times.append(t0 + step * (k + 1))
                vals.append(float(v))
    if not times:
        return pd.Series(dtype=float)
    s = pd.Series(vals, index=pd.DatetimeIndex(times))
    return s.groupby(s.index).mean().sort_index()


def night_mask(idx: pd.DatetimeIndex, drop_night: bool, night_end_hour: float) -> np.ndarray:
    """True=保留。drop_night 时去掉 [00:00, night_end_hour) 的点。"""
    if not drop_night:
        return np.ones(len(idx), bool)
    hod = idx.hour + idx.minute / 60.0
    return ~(hod < night_end_hour)


def _aligned(a: pd.Series, b: pd.Series, drop_night, night_end_hour):
    """两条时间序列取公共时间点 + 去夜间。返回 (times, a_vals, b_vals) 或 None（无公共点）。"""
    common = a.index.intersection(b.index).sort_values()
    if len(common) == 0:
        return None
    keep = night_mask(common, drop_night, night_end_hour)
    common = common[keep]
    if len(common) == 0:
        return None
    return common, a.loc[common].to_numpy(), b.loc[common].to_numpy()


def rmse(a, b):
    return float(np.sqrt(np.mean((a - b) ** 2)))


def parse_feature_pairs(spec):
    if not spec:
        return list(DEFAULT_FEATURE_PAIRS)
    out = []
    for item in spec.split(","):
        parts = [p.strip() for p in item.split(":")]
        if len(parts) == 2:
            parts.append(parts[0])
        if len(parts) != 3 or not all(parts[:2]):
            raise SystemExit(f"--feature-pairs 项格式应为 pred:true[:label]，收到 '{item}'")
        out.append(tuple(parts))
    return out


def parse_capacity(spec):
    if not spec:
        return {}
    out = {}
    for item in spec.split(","):
        k, _, v = item.partition(":")
        out[k.strip()] = float(v)
    return out


# ================================================================ 逐站两线对比图
def plot_two_lines(st, name, times, true_v, pred_v, rmse_v, out_dir,
                   tick_hours, true_label, pred_label):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.dates as mdates
    import matplotlib.pyplot as plt
    _cn_font()

    times = pd.DatetimeIndex(times)
    n_hours = max(1.0, (times[-1] - times[0]).total_seconds() / 3600.0)
    width = min(60.0, max(16.0, n_hours * 0.3))       # 随时间跨度自适应，600+ 点也铺得开
    fig, ax = plt.subplots(figsize=(width, 6))
    ax.plot(times, true_v, label=true_label, color="#1f77b4", lw=1.3)
    ax.plot(times, pred_v, label=pred_label, color="#d62728", lw=1.1, alpha=0.85)
    ax.fill_between(times, true_v, pred_v, color="#d62728", alpha=0.12)
    ax.set_title(f"Station {st}  —  {name}   RMSE={rmse_v:.3f}   "
                 f"start {times[0]:%Y-%m-%d %H:%M}   (n={len(times)} pts)",
                 fontsize=13, fontweight="bold")
    ax.xaxis.set_major_locator(mdates.HourLocator(interval=max(1, int(tick_hours))))
    ax.xaxis.set_major_formatter(mdates.DateFormatter("%m-%d %H:%M"))
    plt.setp(ax.get_xticklabels(), rotation=90, fontsize=7)
    ax.set_xlabel("time"); ax.set_ylabel(name); ax.legend(loc="upper right"); ax.grid(alpha=0.25)
    fig.tight_layout()
    path = os.path.join(out_dir, f"station_{sanitize(st)}_{sanitize(name)}.png")
    fig.savefig(path, dpi=110); plt.close(fig)
    return path


# ================================================================ 全场总览：指标 + 仪表盘
def hourly_nrmse(times, err, cap):
    """按小时(0..23)聚合 err 的 RMSE / cap*100。返回长 24 数组（无数据=nan）。"""
    hod = pd.DatetimeIndex(times).hour
    out = np.full(24, np.nan)
    for h in range(24):
        m = hod == h
        if m.any():
            out[h] = np.sqrt(np.mean(err[m] ** 2)) / cap * 100.0
    return out


def flag_outliers(vals, k):
    """> 中位数 + k×MAD 记为离群。返回布尔数组（有效值 <3 或 MAD=0 → 全 False）。"""
    v = np.asarray(vals, float)
    ok = np.isfinite(v)
    out = np.zeros(len(v), bool)
    if ok.sum() < 3:
        return out
    med = np.median(v[ok])
    mad = np.median(np.abs(v[ok] - med)) * 1.4826  # 正态一致化
    thr = med + k * mad if mad > 0 else np.inf
    out[ok] = v[ok] > thr
    return out


def _cn_font():
    import matplotlib
    try:
        matplotlib.rcParams["font.sans-serif"] = ["Arial Unicode MS", "PingFang SC",
                                                  "Heiti SC", "DejaVu Sans"]
        matplotlib.rcParams["axes.unicode_minus"] = False
    except Exception:
        pass


def _barh(ax, df, col, title, mad_k, top_n):
    d = df[np.isfinite(df[col])].sort_values(col, ascending=False)
    note = ""
    if top_n and len(d) > top_n:
        note = f"（worst {top_n}/{len(d)}）"
        d = d.head(top_n)
    if d.empty:
        ax.text(0.5, 0.5, "无数据", ha="center", va="center"); ax.set_title(title); return
    out = flag_outliers(d[col].to_numpy(), mad_k)
    med = float(np.median(df[col][np.isfinite(df[col])]))
    y = np.arange(len(d))[::-1]                       # worst 在最上
    colors = ["#d62728" if o else "#4c78a8" for o in out]
    ax.barh(y, d[col], color=colors)
    ax.set_yticks(y); ax.set_yticklabels(d["station"].astype(str), fontsize=8)
    ax.axvline(med, color="gray", ls="--", lw=1, label=f"中位 {med:.1f}%")
    ax.set_xlabel("nRMSE (%)")
    ax.set_xlim(0, float(d[col].max()) * 1.22)        # 留白，防离群标注冲出右界
    ax.legend(loc="lower right", fontsize=8); ax.grid(axis="x", alpha=0.25)
    for yi, (v, o) in enumerate(zip(d[col], out)):
        ax.text(v, y[yi], f" {v:.1f}" + ("  离群" if o else ""),
                va="center", fontsize=7, color="#d62728" if o else "#333")
    ax.set_title(title + ("  " + note if note else ""), fontsize=12, fontweight="bold")


def _scatter(ax, df, mad_k):
    if "power_nrmse" not in df or "ghi_nrmse" not in df:
        ax.text(0.5, 0.5, "缺 GHI 或功率，无法画散点", ha="center", va="center")
        ax.set_title("B  GHI-nRMSE vs 功率-nRMSE", fontsize=12, fontweight="bold"); return
    d = df[np.isfinite(df["power_nrmse"]) & np.isfinite(df["ghi_nrmse"])]
    if d.empty:
        ax.text(0.5, 0.5, "缺 GHI 或功率，无法画散点", ha="center", va="center")
        ax.set_title("B  GHI-nRMSE vs 功率-nRMSE", fontsize=12, fontweight="bold"); return
    xm, ym = float(np.median(d.ghi_nrmse)), float(np.median(d.power_nrmse))
    po = flag_outliers(d.power_nrmse.to_numpy(), mad_k)
    ax.scatter(d.ghi_nrmse, d.power_nrmse, c=["#d62728" if o else "#4c78a8" for o in po], s=60, zorder=3)
    for _, r in d.iterrows():
        ax.annotate(str(r.station), (r.ghi_nrmse, r.power_nrmse),
                    fontsize=7, xytext=(4, 3), textcoords="offset points")
    ax.axvline(xm, color="gray", ls="--", lw=1); ax.axhline(ym, color="gray", ls="--", lw=1)
    ax.set_xlabel("GHI nRMSE (%)  →输入越差"); ax.set_ylabel("功率 nRMSE (%)  →输出越差")
    ax.set_title("B  功率差 是否由 GHI 输入差解释", fontsize=12, fontweight="bold")
    ax.grid(alpha=0.25)
    ax.text(0.98, 0.02, "右上=GHI坏&功率坏\n(输入可解释)", transform=ax.transAxes,
            ha="right", va="bottom", fontsize=7, color="#777")
    ax.text(0.02, 0.98, "左上=GHI好但功率坏\n(模型/其它问题)", transform=ax.transAxes,
            ha="left", va="top", fontsize=7, color="#777")


def _heatmap(fig, ax, df, hourly, drop_night, night_end_hour):
    if "power_nrmse" not in df:
        ax.text(0.5, 0.5, "无功率逐时数据", ha="center", va="center")
        ax.set_title("C  时刻×场站 功率 nRMSE", fontsize=12, fontweight="bold"); return
    order = df[np.isfinite(df["power_nrmse"])].sort_values("power_nrmse", ascending=False)
    sts = [s for s in order.station if s in hourly]
    if not sts:
        ax.text(0.5, 0.5, "无功率逐时数据", ha="center", va="center")
        ax.set_title("C  时刻×场站 功率 nRMSE", fontsize=12, fontweight="bold"); return
    h0 = int(night_end_hour) if drop_night else 0
    hours = list(range(h0, 24))
    M = np.vstack([hourly[s][h0:24] for s in sts])
    im = ax.imshow(M, aspect="auto", cmap="YlOrRd", interpolation="nearest")
    ax.set_xticks(range(len(hours))); ax.set_xticklabels(hours, fontsize=7)
    ax.set_yticks(range(len(sts))); ax.set_yticklabels([str(s) for s in sts], fontsize=8)
    ax.set_xlabel("hour of day"); ax.set_title("C  时刻×场站 功率 nRMSE (%)", fontsize=12, fontweight="bold")
    fig.colorbar(im, ax=ax, fraction=0.046, pad=0.04)


def plot_dashboard(df, hourly, have_ghi, args, out_dir):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    _cn_font()
    n_st = len(df)
    h = max(9.0, 1.0 + n_st * 0.45)                  # 高度随站数自适应
    fig, axes = plt.subplots(2, 2, figsize=(18, h))
    if "power_nrmse" in df:
        _barh(axes[0, 0], df, "power_nrmse", "A1  功率 nRMSE 排行", args.mad_k, args.top_n)
    else:
        axes[0, 0].text(0.5, 0.5, "无功率数据", ha="center", va="center")
        axes[0, 0].set_title("A1  功率 nRMSE 排行", fontsize=12, fontweight="bold")
    if have_ghi and "ghi_nrmse" in df:
        _barh(axes[0, 1], df, "ghi_nrmse", "A2  GHI nRMSE 排行", args.mad_k, args.top_n)
    else:
        axes[0, 1].text(0.5, 0.5, "无 GHI 真值/预测，跳过", ha="center", va="center")
        axes[0, 1].set_title("A2  GHI nRMSE 排行", fontsize=12, fontweight="bold")
    _scatter(axes[1, 0], df, args.mad_k)
    _heatmap(fig, axes[1, 1], df, hourly, args.drop_night, args.night_end_hour)
    fig.suptitle(f"Fleet overview —— {n_st} 站   "
                 f"（nRMSE = RMSE / 峰值功率；红条 = 离群: 高于中位 + {args.mad_k}×MAD）"
                 + ("   已去夜间" if args.drop_night else ""),
                 fontsize=14, fontweight="bold")
    fig.tight_layout(rect=(0, 0, 1, 0.98))
    path = os.path.join(out_dir, "fleet_overview.png")
    fig.savefig(path, dpi=120); plt.close(fig)
    return path


# ================================================================ 反事实（oracle GHI swap）
CF_COLS = ["station", "status", "n_points", "capacity", "nrmse_base", "nrmse_cf",
           "delta_nrmse", "frac_explained", "base_vs_parquet_pct", "coadapt"]


def parse_cf_swap(spec):
    """"pred:true[,pred2:true2]" → {pred列: 真值列}。多对 = 联合替换。"""
    out = {}
    for item in spec.split(","):
        p, _, t = item.partition(":")
        p, t = p.strip(), t.strip()
        if not p or not t:
            raise SystemExit(f"--cf-swap 项格式应为 pred:true，收到 '{item}'")
        out[p] = t
    return out


def _jsonable(v):
    """parquet 单元格 → 可 JSON 化：Timestamp→ISO 字符串、array/list→list、NaN→None。"""
    if isinstance(v, pd.Timestamp):
        return v.isoformat()
    if v is None:
        return None
    if np.ndim(v) > 0:
        arr = np.asarray(v, dtype=float).ravel()
        return [float(x) if np.isfinite(x) else None for x in arr]
    if isinstance(v, (bool, np.bool_)):
        return bool(v)
    if isinstance(v, (int, np.integer)):
        return int(v)
    if isinstance(v, (float, np.floating)):
        return float(v) if np.isfinite(v) else None
    return str(v)


def cf_build_payload(sub: pd.DataFrame, exclude: set, swap: dict | None):
    """一个站的窗口行 → {"data": [行dict]}。字段名 = parquet 列名；swap 给定时，
    被换列的字段名不变、值取同行真值列（oracle 替换）。"""
    rows = []
    for _, r in sub.iterrows():
        d = {}
        for col in sub.columns:
            if col in exclude:
                continue
            src = swap.get(col, col) if swap else col
            d[col] = _jsonable(r[src])
        rows.append(d)
    return {"data": rows}


def _payload_skeleton(payload, n_preview=4):
    lines = []
    for k, v in payload["data"][0].items():
        if isinstance(v, list):
            prev = ", ".join("None" if x is None else f"{x:.4g}" for x in v[:n_preview])
            lines.append(f"    {k}: list[{len(v)}]  [{prev}, ...]")
        else:
            lines.append(f"    {k}: {type(v).__name__}  {v!r}")
    return "\n".join(lines)


def _extract_response(obj):
    """解析 API 响应，返回 (kind, data)：
    ① 逐窗（真实契约）："predictions": [{"timestamp_win":..., "ensemble":[192值]}, ...]
       → ("windows", [(Timestamp, list), ...])，只取 ensemble，其余键忽略。
    ② 扁平 list（兼容回退）：裸 list 或 {"prediction":[...]} → ("flat", [...])。"""
    if isinstance(obj, dict):
        preds = obj.get("predictions")
        if isinstance(preds, list) and preds and isinstance(preds[0], dict):
            out = []
            for p in preds:
                if "timestamp_win" not in p or "ensemble" not in p:
                    raise RuntimeError(f"响应 predictions 元素缺 timestamp_win/ensemble 键"
                                       f"（实际键: {list(p)[:6]}）")
                out.append((pd.Timestamp(p["timestamp_win"]), p["ensemble"]))
            return "windows", out
    if isinstance(obj, list):
        return "flat", obj
    if isinstance(obj, dict):
        for k in ("prediction", "predictions", "result", "power", "data", "output"):
            if isinstance(obj.get(k), list):
                return "flat", obj[k]
        for v in obj.values():
            if isinstance(v, list):
                return "flat", v
    raise RuntimeError(f"无法从 API 响应中提取预测（响应键: "
                       f"{list(obj)[:5] if isinstance(obj, dict) else type(obj).__name__}）")


def cf_call_api(url, payload, timeout, retries):
    body = json.dumps(payload).encode()
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))  # 内网 API 直连，不走系统代理
    last = None
    for _ in range(int(retries) + 1):
        try:
            req = urllib.request.Request(url, data=body,
                                         headers={"Content-Type": "application/json"})
            with opener.open(req, timeout=timeout) as resp:
                return _extract_response(json.loads(resp.read().decode()))
        except Exception as e:                        # noqa: BLE001 —— 重试后统一上抛
            last = e
    raise RuntimeError(f"API 调用失败（重试 {retries} 次后）: {last}")


def cf_series(kind, data, dtimes, n_sent, step):
    """API 响应 → 带绝对时间戳的功率序列。对不齐 → (None, 原因)。
    windows：校验返回窗数 = 发送行数，按响应自带的 timestamp_win 摊平去重
             （与 input 表同一规则：T+step×(k+1)，重叠窗取均值）。
    flat   ：校验长度 = predict 表该站非空 dtime 数，逐点对应。"""
    if kind == "windows":
        if len(data) != n_sent:
            return None, f"返回 {len(data)} 窗 ≠ 发送 {n_sent} 窗"
        wins = [t for t, _ in data]
        lists = [[np.nan if v is None else float(v) for v in lst] for _, lst in data]
        s = series_from_lists(wins, lists, step)
        if s.empty:
            return None, "各窗 ensemble 全空"
        return s, ""
    if data is None or len(data) != len(dtimes):
        return None, f"返回 {0 if data is None else len(data)} 点 ≠ predict 表 {len(dtimes)} 点"
    return pd.Series([np.nan if v is None else float(v) for v in data], index=dtimes), ""


def cf_metrics(p_true, p_base, p_cf, drop_night, night_end_hour, cap):
    """三序列取公共时间点（尊重去夜间）→ 分解指标。返回 (指标dict, (times,t,b,c)) 或 None。"""
    common = p_true.index.intersection(p_base.index).intersection(p_cf.index).sort_values()
    if len(common) == 0:
        return None
    common = common[night_mask(common, drop_night, night_end_hour)]
    if len(common) == 0:
        return None
    t = p_true.loc[common].to_numpy()
    b = p_base.loc[common].to_numpy()
    c = p_cf.loc[common].to_numpy()
    cap = cap if cap and cap > 0 else (float(np.max(t)) or 1.0)
    nb = rmse(b, t) / cap * 100.0
    nc = rmse(c, t) / cap * 100.0
    m = {"n_points": int(len(common)), "capacity": round(cap, 4),
         "nrmse_base": round(nb, 4), "nrmse_cf": round(nc, 4),
         "delta_nrmse": round(nb - nc, 4),
         "frac_explained": round((nb - nc) / nb * 100.0, 2) if nb > 0 else np.nan,
         "coadapt": int(nb - nc < -0.1)}    # 实质性变差（>0.1 个百分点）才算共适应，排除噪声级负 Δ
    return m, (common, t, b, c)


def _cf_append(path, row):
    pd.DataFrame([{c: row.get(c, "") for c in CF_COLS}]).to_csv(
        path, mode="a", header=not os.path.exists(path), index=False)


def plot_cf_curves(st, times, t, b, c, out_dir, tick_hours):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.dates as mdates
    import matplotlib.pyplot as plt
    _cn_font()
    times = pd.DatetimeIndex(times)
    n_hours = max(1.0, (times[-1] - times[0]).total_seconds() / 3600.0)
    fig, ax = plt.subplots(figsize=(min(60.0, max(16.0, n_hours * 0.3)), 6))
    ax.plot(times, t, label="observed power", color="#1f77b4", lw=1.4)
    ax.plot(times, b, label="baseline pred (API, 原特征)", color="#d62728", lw=1.1, alpha=0.85)
    ax.plot(times, c, label="counterfactual pred (GHI→真值)", color="#2ca02c", lw=1.1, alpha=0.85)
    ax.set_title(f"Station {st} — counterfactual   base RMSE={rmse(b, t):.3f} → "
                 f"cf RMSE={rmse(c, t):.3f}", fontsize=13, fontweight="bold")
    ax.xaxis.set_major_locator(mdates.HourLocator(interval=max(1, int(tick_hours))))
    ax.xaxis.set_major_formatter(mdates.DateFormatter("%m-%d %H:%M"))
    plt.setp(ax.get_xticklabels(), rotation=90, fontsize=7)
    ax.legend(loc="upper right"); ax.grid(alpha=0.25)
    fig.tight_layout()
    path = os.path.join(out_dir, f"station_{sanitize(st)}_counterfactual.png")
    fig.savefig(path, dpi=110); plt.close(fig)
    return path


def plot_cf_overview(df, out_dir, swap_label):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from matplotlib.patches import Patch
    _cn_font()
    d = df[np.isfinite(df["nrmse_base"])].sort_values("nrmse_base", ascending=False)
    if d.empty:
        return None
    n = len(d)
    fig, (axL, axR) = plt.subplots(1, 2, figsize=(16, max(7.0, 1.5 + n * 0.5)),
                                   gridspec_kw={"width_ratios": [1.6, 1]})
    # 左：堆叠条 —— 灰=模型底线、橙=GHI 归因、蓝=换真值反而差（共适应）
    y = np.arange(n)[::-1]
    for yi, (_, r) in zip(y, d.iterrows()):
        if r.delta_nrmse >= 0:
            axL.barh(yi, r.nrmse_cf, color="#9aa0a6")
            axL.barh(yi, r.delta_nrmse, left=r.nrmse_cf, color="#f28e2b")
            xend = r.nrmse_base
        else:
            axL.barh(yi, r.nrmse_base, color="#9aa0a6")
            axL.barh(yi, r.nrmse_cf - r.nrmse_base, left=r.nrmse_base,
                     color="#4c78a8", hatch="//")
            xend = r.nrmse_cf
        if np.isfinite(r.frac_explained) and r.delta_nrmse >= 0:
            tag = f"  {r.frac_explained:.0f}%可由{swap_label}解释"
        elif r.get("coadapt", 0) > 0:
            tag = "  换真值反而差(共适应)"
        else:
            tag = ""
        star = "  基线未复现!" if str(r.status) == "baseline_mismatch" else ""
        axL.text(xend, yi, f" {r.nrmse_base:.1f}%{tag}{star}", va="center", fontsize=7)
    axL.set_yticks(y); axL.set_yticklabels(d.station.astype(str), fontsize=8)
    axL.set_xlim(0, float(max(d.nrmse_base.max(), d.nrmse_cf.max())) * 1.5)
    axL.set_xlabel("功率 nRMSE (%)")
    axL.legend(handles=[
        Patch(color="#9aa0a6", label=f"模型底线（{swap_label} 换真值后仍剩）"),
        Patch(color="#f28e2b", label=f"{swap_label} 输入归因（换真值即消失）"),
        Patch(facecolor="#4c78a8", hatch="//", label="换真值反而更差（共适应警示）")],
        loc="lower right", fontsize=8)
    axL.set_title(f"误差分解：{swap_label} 输入的锅 vs 模型的锅（按基线 nRMSE 降序）",
                  fontsize=12, fontweight="bold")
    axL.grid(axis="x", alpha=0.25)
    # 右：GHI 可解释比例（条长裁剪到 [-100,100] 防极端负值拉爆横轴，真实值标在条端）
    dr = d[np.isfinite(d["frac_explained"])].sort_values("frac_explained", ascending=False)
    if not dr.empty:
        yr = np.arange(len(dr))[::-1]
        shown = dr.frac_explained.clip(lower=-100.0, upper=100.0)
        axR.barh(yr, shown,
                 color=["#f28e2b" if f >= 0 else "#4c78a8" for f in dr.frac_explained])
        for yi, v, f in zip(yr, shown, dr.frac_explained):
            axR.text(v + (2 if v >= 0 else -2), yi, f"{f:.0f}%", va="center",
                     ha="left" if v >= 0 else "right", fontsize=7,
                     color="#333" if f >= 0 else "#4c78a8")
        axR.set_xlim(-118, 130)
        axR.set_yticks(yr); axR.set_yticklabels(dr.station.astype(str), fontsize=8)
        med = float(np.median(dr.frac_explained))
        axR.axvline(med, color="gray", ls="--", lw=1, label=f"中位 {med:.0f}%")
        axR.axvline(0, color="#333", lw=0.8)
        axR.legend(loc="lower right", fontsize=8)
    else:
        axR.text(0.5, 0.5, "无数据", ha="center", va="center")
    axR.set_xlabel(f"{swap_label} 可解释比例 (%)")
    axR.set_title(f"哪些站该催 {swap_label} 数据源（比例高 = 输入问题）",
                  fontsize=12, fontweight="bold")
    axR.grid(axis="x", alpha=0.25)
    fig.suptitle(f"Counterfactual —— {swap_label} 预测换成真值经模型重预测，误差消多少（{n} 站）",
                 fontsize=14, fontweight="bold")
    fig.text(0.01, 0.005,
             f"注意：① Δ≈0 不等于 {swap_label} 预报没问题——模型可能对它不敏感或已共适应；"
             f"② 「模型底线」含其它无真值输入（如温度）的误差，是模型自身误差的上界。",
             fontsize=8, color="#666")
    fig.tight_layout(rect=(0, 0.03, 1, 0.96))
    path = os.path.join(out_dir, "counterfactual_overview.png")
    fig.savefig(path, dpi=120); plt.close(fig)
    return path


def run_counterfactual(inp, pred, args, cap_map, step):
    """编排：逐站 2 次 API 调用（基线复现 + 换真值），逐站落盘可断点续跑。"""
    swap = parse_cf_swap(args.cf_swap)
    miss = sorted({c for pair in swap.items() for c in pair if c not in inp.columns})
    if miss:
        print(f"  ⚠ 反事实跳过：--cf-swap 涉及的列缺失 {miss}")
        return
    exclude = {c.strip() for c in args.cf_exclude_cols.split(",") if c.strip()}
    exclude.add(args.station_col)
    exclude |= set(swap.values())               # 真值列是 label，不作为字段发出

    stations = [s for s in pd.unique(inp[args.station_col])
                if s in pred.columns or str(s) in pred.columns]
    if args.cf_stations:
        want = {s.strip() for s in args.cf_stations.split(",")}
        stations = [s for s in stations if str(s) in want]
    if not stations:
        print("  ⚠ 反事实：没有可跑的站（站名需同时在 input 与 predict 表）")
        return

    csv_path = os.path.join(args.out_dir, "counterfactual_results.csv")
    if args.cf_force and os.path.exists(csv_path):
        os.remove(csv_path)
    done = set()
    if os.path.exists(csv_path):
        prev = pd.read_csv(csv_path)
        done = set(prev[prev["status"].isin(["ok", "baseline_mismatch"])]["station"].astype(str))
    todo = [s for s in stations if str(s) not in done]
    swap_label = "+".join(p[: -len("_predict")] if p.endswith("_predict") else p for p in swap)
    print(f"[counterfactual] 计划：站 ×{len(stations)}（续跑跳过 {len(stations) - len(todo)}），"
          f"每站 2 次调用（基线复现 + {swap_label} 换真值）= 共 {len(todo) * 2} 次")

    if args.cf_dry_run:
        st0 = todo[0] if todo else stations[0]
        sub0 = inp[inp[args.station_col] == st0].sort_values(args.win_col)
        pl = cf_build_payload(sub0, exclude, None)
        print(f"  —— dry-run（零 HTTP）：站 {st0} 的 payload 骨架"
              f"（data 共 {len(pl['data'])} 行，字段 = parquet 列名，仅示首行）——")
        print(_payload_skeleton(pl))
        print("  反事实调用与基线唯一区别：" +
              "；".join(f"{p} 的值换成同行 {t}" for p, t in swap.items()))
        print("  确认格式无误后去掉 --cf-dry-run 实跑。")
        return
    if not args.api_url:
        raise SystemExit("--counterfactual 实跑需要 --api-url（或先 --cf-dry-run 检查 payload）")

    for st in todo:
        col = st if st in pred.columns else str(st)
        sub = inp[inp[args.station_col] == st].sort_values(args.win_col)
        pq = pred[col].dropna()
        dtimes = pq.index.sort_values()
        try:
            kind, data = cf_call_api(args.api_url, cf_build_payload(sub, exclude, None),
                                     args.cf_timeout, args.cf_retries)
            p_base, why = cf_series(kind, data, dtimes, len(sub), step)
            if p_base is None:
                print(f"  ⚠ 站 {st}: 基线 API 输出对不齐（{why}），跳过")
                _cf_append(csv_path, {"station": st, "status": "align_mismatch"})
                continue
            kind, data = cf_call_api(args.api_url, cf_build_payload(sub, exclude, swap),
                                     args.cf_timeout, args.cf_retries)
            p_cf, why = cf_series(kind, data, dtimes, len(sub), step)
            if p_cf is None:
                print(f"  ⚠ 站 {st}: 反事实 API 输出对不齐（{why}），跳过")
                _cf_append(csv_path, {"station": st, "status": "align_mismatch"})
                continue
        except RuntimeError as e:
            print(f"  ⚠ 站 {st}: {e}")
            _cf_append(csv_path, {"station": st, "status": "api_error"})
            continue
        truth = series_from_lists(sub[args.win_col].to_numpy(),
                                  sub[args.power_col].to_numpy(), step)
        cap = cap_map.get(str(st)) or cap_map.get(st)
        got = cf_metrics(truth, p_base, p_cf, args.drop_night, args.night_end_hour, cap)
        if got is None:
            print(f"  ⚠ 站 {st}: 真值与 API 输出无公共时间点，跳过")
            _cf_append(csv_path, {"station": st, "status": "no_overlap"})
            continue
        m, (times, t, b, c) = got
        al_pq = _aligned(p_base, pq, args.drop_night, args.night_end_hour)   # 复现闸：公共时间点上比
        bvp = rmse(al_pq[1], al_pq[2]) / m["capacity"] * 100.0 if al_pq else float("inf")
        m["base_vs_parquet_pct"] = round(bvp, 4) if np.isfinite(bvp) else ""
        m["status"] = "ok" if bvp <= args.cf_check_tol else "baseline_mismatch"
        if m["status"] == "baseline_mismatch":
            print(f"  ⚠ 站 {st}: API 基线与 predict 表差 {bvp:.2f}%（>{args.cf_check_tol}%）"
                  "——契约/对齐可能有出入，分解仍按 API 基线计算")
        m["station"] = st
        _cf_append(csv_path, m)
        if args.cf_curves and not args.no_plots:
            plot_cf_curves(st, times, t, b, c, args.out_dir, args.tick_hours)
        print(f"  站 {st}: nRMSE 基线 {m['nrmse_base']:.2f}% → 换真值 {m['nrmse_cf']:.2f}%   "
              f"Δ={m['delta_nrmse']:+.2f}%"
              + (f"（{m['frac_explained']:.0f}% 可由 {swap_label} 解释）"
                 if np.isfinite(m['frac_explained']) else ""))

    # ---- 汇总：图 + 结论速览（含此前续跑已完成的站）----
    if not os.path.exists(csv_path):
        return
    res = pd.read_csv(csv_path).drop_duplicates("station", keep="last")
    okd = res[res["status"].isin(["ok", "baseline_mismatch"])].copy()
    for c in ("nrmse_base", "nrmse_cf", "delta_nrmse", "frac_explained", "coadapt"):
        if c in okd:
            okd[c] = pd.to_numeric(okd[c], errors="coerce")
    img = None
    if not okd.empty and not args.no_plots:
        img = plot_cf_overview(okd, args.out_dir, swap_label)
    n_bad = len(res) - len(okd)
    print(f"[counterfactual] 完成：ok/复现告警 ×{len(okd)}"
          + (f"，失败/对不齐 ×{n_bad}" if n_bad else "")
          + f" → counterfactual_results.csv" + (" + counterfactual_overview.png" if img else ""))
    if not okd.empty:
        good = okd[np.isfinite(okd["frac_explained"])]
        if not good.empty:
            top_in = good.sort_values("frac_explained", ascending=False).head(2)
            print("  输入问题最大（换真值提升最多）: " +
                  "、".join(f"{r.station}({r.frac_explained:.0f}%)" for _, r in top_in.iterrows()))
        top_md = okd[np.isfinite(okd["nrmse_cf"])].sort_values("nrmse_cf", ascending=False).head(2)
        if not top_md.empty:
            print("  模型问题最大（换真值后仍剩误差高）: " +
                  "、".join(f"{r.station}({r.nrmse_cf:.2f}%)" for _, r in top_md.iterrows()))
        co = okd[okd["coadapt"].fillna(0) > 0]
        if not co.empty:
            print(f"  共适应警示（换真值反而差）: {co.station.tolist()}")


# ================================================================ 主流程：一趟同时算两层
def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--input", required=True)
    ap.add_argument("--predict", required=True)
    ap.add_argument("--out-dir", default="station_analysis_out")
    ap.add_argument("--step-min", type=int, default=15)
    ap.add_argument("--drop-night", action="store_true", help="去掉每天 00:00–night_end_hour 的点")
    ap.add_argument("--night-end-hour", type=float, default=5.0)
    ap.add_argument("--tick-hours", type=int, default=1, help="逐站图每几小时一个 x 刻度")
    ap.add_argument("--feature-pairs", default=None,
                    help="pred:true[:label] 逗号分隔；缺省 GHI_SOLARGIS_predict:GHI_real_future:GHI")
    ap.add_argument("--top-n", type=int, default=30, help="排行榜最多显示几站（0=全部）")
    ap.add_argument("--mad-k", type=float, default=3.0, help="离群阈值：中位 + k×MAD")
    ap.add_argument("--capacity", default=None, help='每站装机 "st1:500,st2:5"，缺省用峰值代理')
    ap.add_argument("--ghi-pred", default="GHI_SOLARGIS_predict", help="总览散点/GHI榜用的预测列")
    ap.add_argument("--ghi-true", default="GHI_real_future", help="总览散点/GHI榜用的真值列")
    ap.add_argument("--station-col", default="station")
    ap.add_argument("--win-col", default="timestamp_win")
    ap.add_argument("--power-col", default="observe_power_future")
    ap.add_argument("--dtime-col", default="dtime")
    ap.add_argument("--no-plots", action="store_true", help="不出任何图，仍写 CSV")
    ap.add_argument("--no-station-plots", action="store_true", help="不出逐站曲线，仍写站级 CSV")
    ap.add_argument("--no-fleet", action="store_true", help="不出总览与 fleet_ranking.csv")
    ap.add_argument("--counterfactual", action="store_true",
                    help="反事实：GHI 预测换真值经 API 重预测，分解 输入的锅 vs 模型的锅")
    ap.add_argument("--api-url", default=None, help="FastAPI 预测服务地址（POST JSON）")
    ap.add_argument("--cf-dry-run", action="store_true",
                    help="零 HTTP：只打印调用计划 + 首站 payload 骨架，确认契约后再实跑")
    ap.add_argument("--cf-stations", default=None, help='只跑这些站 "st1,st2"（默认全部）')
    ap.add_argument("--cf-force", action="store_true", help="忽略已完成记录，全部重算")
    ap.add_argument("--cf-swap", default="GHI_SOLARGIS_predict:GHI_real_future",
                    help="pred:true 逗号分隔可多对（多对 = 联合替换）")
    ap.add_argument("--cf-exclude-cols", default="observe_power_future,GHI_real_future",
                    help="不发给 API 的列（真值 label；station 列自动剔除）")
    ap.add_argument("--cf-timeout", type=float, default=120.0)
    ap.add_argument("--cf-retries", type=int, default=1)
    ap.add_argument("--cf-check-tol", type=float, default=1.0,
                    help="基线复现闸：API 基线 vs predict 表 nRMSE%% 超此值告警")
    ap.add_argument("--cf-curves", action="store_true", help="逐站三线图（真值/基线/反事实）")
    args = ap.parse_args()
    step = pd.Timedelta(minutes=args.step_min)
    feature_pairs = parse_feature_pairs(args.feature_pairs)
    cap_map = parse_capacity(args.capacity)
    plot_station = not (args.no_plots or args.no_station_plots)

    inp = pd.read_parquet(args.input)
    pred = pd.read_parquet(args.predict)
    for c in (args.station_col, args.win_col, args.power_col):
        if c not in inp.columns:
            raise SystemExit(f"输入表缺列 '{c}'；实际列: {list(inp.columns)[:30]}")
    if args.dtime_col not in pred.columns:
        raise SystemExit(f"预测表缺列 '{args.dtime_col}'；实际列: {list(pred.columns)[:30]}")
    inp[args.win_col] = pd.to_datetime(inp[args.win_col])
    pred[args.dtime_col] = pd.to_datetime(pred[args.dtime_col])
    pred = pred.groupby(args.dtime_col).mean(numeric_only=True).sort_index()

    # 逐站特征对里列全局缺失的先整对剔除（告警一次）
    active_pairs = []
    for pcol, tcol, label in feature_pairs:
        miss = [c for c in (pcol, tcol) if c not in inp.columns]
        if miss:
            print(f"  ⚠ 特征图 '{label}' 跳过：输入表缺列 {miss}")
        else:
            active_pairs.append((pcol, tcol, label))
    have_ghi = args.ghi_pred in inp.columns and args.ghi_true in inp.columns
    if not have_ghi and not args.no_fleet:
        miss = [c for c in (args.ghi_pred, args.ghi_true) if c not in inp.columns]
        print(f"  ⚠ 总览 GHI 列缺失 {miss} → 跳过 GHI 排行榜与散点（功率总览照出）")

    os.makedirs(args.out_dir, exist_ok=True)
    stations = list(pd.unique(inp[args.station_col]))
    power_rows, feat_rows, imgs = [], [], []
    fleet_recs, hourly = [], {}

    for st in stations:
        sub = inp[inp[args.station_col] == st]
        wins = sub[args.win_col].to_numpy()
        cache = {}

        def ser(col):                                 # 每站列级记忆化：同列只摊平一次
            if col not in cache:
                cache[col] = series_from_lists(wins, sub[col].to_numpy(), step)
            return cache[col]

        rec = {"station": st}

        # ---- Power（预测来自 predict 表）----
        truth = ser(args.power_col)
        col = st if st in pred.columns else (str(st) if str(st) in pred.columns else None)
        if col is None:
            print(f"  ⚠ 站 {st}: 预测表无此列，跳过 Power 图")
        else:
            al = _aligned(truth, pred[col].dropna(), args.drop_night, args.night_end_hour)
            if al is None:
                print(f"  ⚠ 站 {st}: Power 真值/预测无公共时间点（或全在夜间被去掉），跳过")
            else:
                times, t, p = al
                rv = rmse(p, t)
                power_rows.append({"station": st, "power_rmse": round(rv, 6),
                                   "n_points": int(len(times)),
                                   "t_start": str(times.min()), "t_end": str(times.max())})
                if plot_station:
                    imgs.append(plot_two_lines(st, "Power", times, t, p, rv, args.out_dir,
                                               args.tick_hours, "observed power", "predicted power"))
                # 总览：功率 nRMSE / bias / 逐时
                cap = cap_map.get(str(st)) or cap_map.get(st) or float(np.max(t))
                cap = cap if cap and cap > 0 else 1.0
                rec.update(power_rmse=round(rv, 4), power_nrmse=round(rv / cap * 100, 4),
                           power_bias_pct=round(float(np.mean(p - t)) / cap * 100, 4),
                           capacity=round(cap, 4), n_points=int(len(times)))
                hourly[st] = hourly_nrmse(times, p - t, cap)

        # ---- 逐站特征图（预测与真值都在 input）----
        for pcol, tcol, label in active_pairs:
            pser, tser = ser(pcol), ser(tcol)
            if pser.empty or tser.empty:
                print(f"  ⚠ 站 {st}: 特征 '{label}' 该站数据缺失/为空，跳过（不影响其它图）")
                continue
            al = _aligned(tser, pser, args.drop_night, args.night_end_hour)
            if al is None:
                print(f"  ⚠ 站 {st}: 特征 '{label}' 无公共时间点，跳过")
                continue
            times, tv, pv = al
            rv = rmse(pv, tv)
            feat_rows.append({"station": st, "feature": label, "rmse": round(rv, 6),
                              "n_points": int(len(times))})
            if plot_station:
                imgs.append(plot_two_lines(st, label, times, tv, pv, rv, args.out_dir,
                                           args.tick_hours, f"{tcol} (true)", f"{pcol} (pred)"))

        # ---- 总览：GHI nRMSE（散点/GHI榜；用指定列，复用缓存不重复摊平）----
        if have_ghi and not args.no_fleet:
            gp, gt = ser(args.ghi_pred), ser(args.ghi_true)
            if not gp.empty and not gt.empty:
                al = _aligned(gt, gp, args.drop_night, args.night_end_hour)
                if al is not None:
                    _, tvg, pvg = al
                    gcap = float(np.max(tvg)) or 1.0
                    gr = rmse(pvg, tvg)
                    rec.update(ghi_rmse=round(gr, 4), ghi_nrmse=round(gr / gcap * 100, 4))
        fleet_recs.append(rec)

    # ---------------- 站级 CSV ----------------
    if power_rows:
        pw = pd.DataFrame(power_rows).sort_values("power_rmse", ascending=False)
        pw.to_csv(os.path.join(args.out_dir, "station_power_rmse.csv"), index=False)
    if feat_rows:
        pd.DataFrame(feat_rows).sort_values(["feature", "rmse"], ascending=[True, False]).to_csv(
            os.path.join(args.out_dir, "station_feature_rmse.csv"), index=False)

    # ---------------- 全场总览 ----------------
    fleet_img = None
    fdf = pd.DataFrame(fleet_recs)
    if not args.no_fleet and ("power_nrmse" in fdf.columns or "ghi_nrmse" in fdf.columns):
        if "power_nrmse" in fdf.columns:
            fdf["power_outlier"] = flag_outliers(fdf["power_nrmse"].to_numpy(), args.mad_k)
            fdf["power_rank"] = fdf["power_nrmse"].rank(ascending=False, method="min").astype("Int64")
        sort_col = "power_nrmse" if "power_nrmse" in fdf.columns else "station"
        fdf.sort_values(sort_col, ascending=(sort_col == "station")).to_csv(
            os.path.join(args.out_dir, "fleet_ranking.csv"), index=False)
        if not args.no_plots:
            fleet_img = plot_dashboard(fdf, hourly, have_ghi, args, args.out_dir)

    if not power_rows and not feat_rows and fleet_img is None:
        raise SystemExit("没有任何图/指标能产出（检查 station 是否等于预测表列名、时间是否对得上、列是否存在）。")

    # ---------------- 终端摘要 ----------------
    print(f"[station_analysis] 站 ×{len(stations)}   特征对 {[p[2] for p in active_pairs] or '无'}   "
          f"drop_night={args.drop_night}   → {args.out_dir}/")
    if power_rows:
        print("  逐站 Power RMSE（绝对，供细看）:")
        print(pw.to_string(index=False))
    if not args.no_fleet and "power_nrmse" in fdf.columns:
        top = fdf[np.isfinite(fdf.power_nrmse)].sort_values("power_nrmse", ascending=False)
        print("  全场 功率 nRMSE 最离谱 Top（%，归一化后才可比）:")
        for _, r in top.head(5).iterrows():
            tag = "  ⚠离群" if r.get("power_outlier") else ""
            print(f"    {r.station}: {r.power_nrmse:.2f}%  (RMSE={r.power_rmse:.2f}, "
                  f"bias={r.get('power_bias_pct', float('nan')):+.2f}%){tag}")
        outs = top[top.power_outlier == True]["station"].tolist() if "power_outlier" in top else []
        if outs:
            print(f"  ⚠ 离群站（明显高于全场）：{outs}")
    prod = []
    if imgs:
        prod.append(f"逐站图 ×{len(imgs)}")
    if power_rows:
        prod.append("station_power_rmse.csv")
    if feat_rows:
        prod.append("station_feature_rmse.csv")
    if not args.no_fleet and ("power_nrmse" in fdf.columns or "ghi_nrmse" in fdf.columns):
        prod.append("fleet_ranking.csv")
    if fleet_img:
        prod.append("fleet_overview.png")
    print("  产物: " + ("  + ".join(prod) if prod else "无"))

    # ---------------- 反事实（可选，门控） ----------------
    if args.counterfactual:
        run_counterfactual(inp, pred, args, cap_map, step)


if __name__ == "__main__":
    main()
