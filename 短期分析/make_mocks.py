#!/usr/bin/env python3
"""生成短期分析用的 mock 数据：mock_input.parquet + mock_predict.parquet + mock_info.csv。

形状锁 inference.py 的两条 assert（第 15、16 行）：station 全表唯一、每站只有一行，
timestamp_win 全表只有一个值。所以这份 input 既能直接喂 station_analysis_short.py --input，
也能不做任何切片直接喂 multi_station_inference。

时间约定与真实数据一致：
  起报时刻 t0 = 起报日 10:00；
  正向列（*_predict / *_future）长 480，第 k 个元素落在 t0 + 15min x (k+1)，即 10:15 起、跨 5 天；
  历史列（observe_power / GHI_SOLARGIS / GHI_real / ssrd_pos_* / t2m_pos_*）长 672，
  第 i 个元素落在 t0 - 15min x (671-i)，即最后一个元素正好落在 t0；
  预测表 dtime 从 D+1 00:00 排到 D+4 23:45（384 点），覆盖 D+1 与 D+4 两个分析窗。

数值不是纯噪声：GHI 由各站自己的经纬度算晴空辐照 GHI_cs，再乘一条平滑的云况 K_t 序列；
功率由 GHI 经温度降额换算并按装机截断。每个站还带一个固定的 GHI 预报乘性偏差（见 BIAS），
--cf-kt-scale 的 K_t 扫描应当能把它们逐站找回来。

    python make_mocks.py                       # 写进本目录
    python make_mocks.py --out-dir /tmp/x --stations 5
"""
from __future__ import annotations

import argparse
import os

import numpy as np
import pandas as pd

from pvcore.solar import clear_sky_ghi
from pvcore.timeseries import STEP

N_FUTURE = 480              # 正向列长度：480 x 15min = 5 天
N_HISTORY = 672             # 历史列长度：672 x 15min = 7 天
NWP_POS = 9                 # ssrd_pos_1..9 / t2m_pos_1..9

# 20 个站：站号沿用 plant_guangfu<数字> 命名（--hist-root 按末尾连续数字取 plantid）。
# 每个三元组是 (装机 MW, 经纬度所在城市, GHI 预报的乘性偏差)。偏差 1.0 = 预报无系统性缩放。
STATIONS = [
    ("plant_guangfu1025", 120.0, "南宁", 22.82, 108.32, 1.00),
    ("plant_guangfu1358", 80.0, "柳州", 24.33, 109.42, 0.88),
    ("plant_guangfu1780", 200.0, "桂林", 25.28, 110.29, 1.15),
    ("plant_guangfu2740", 45.0, "梧州", 23.48, 111.28, 1.00),
    ("plant_guangfu2741", 45.0, "北海", 21.48, 109.12, 0.95),
    ("plant_guangfu3011", 150.0, "防城港", 21.69, 108.35, 1.22),
    ("plant_guangfu3102", 60.0, "钦州", 21.98, 108.65, 1.01),
    ("plant_guangfu3255", 95.0, "贵港", 23.11, 109.60, 0.80),
    ("plant_guangfu3407", 175.0, "玉林", 22.65, 110.18, 1.08),
    ("plant_guangfu3618", 30.0, "百色", 23.90, 106.62, 0.99),
    ("plant_guangfu3720", 110.0, "贺州", 24.40, 111.57, 1.30),
    ("plant_guangfu3891", 25.0, "河池", 24.69, 108.09, 0.92),
    ("plant_guangfu4103", 140.0, "来宾", 23.75, 109.23, 1.05),
    ("plant_guangfu4276", 55.0, "崇左", 22.38, 107.37, 1.00),
    ("plant_guangfu4419", 185.0, "广州", 23.13, 113.26, 0.85),
    ("plant_guangfu4530", 70.0, "阳江", 21.86, 111.98, 1.12),
    ("plant_guangfu4688", 100.0, "湛江", 21.27, 110.36, 1.00),
    ("plant_guangfu4712", 35.0, "茂名", 21.66, 110.93, 1.18),
    ("plant_guangfu4855", 160.0, "肇庆", 23.05, 112.47, 0.90),
    ("plant_guangfu4967", 90.0, "清远", 23.68, 113.06, 1.03),
]


def _smooth_noise(rng, n, scale, corr=0.90):
    """一阶自回归噪声：相邻点相关，避免云况逐点跳变成白噪声。"""
    e = rng.normal(0.0, scale, n)
    out = np.empty(n)
    out[0] = e[0]
    for i in range(1, n):
        out[i] = corr * out[i - 1] + np.sqrt(1 - corr ** 2) * e[i]
    return out


def _ghi(times, lat, lon, rng):
    """真实 GHI = 晴空辐照 x 云况 K_t。夜间 GHI_cs 为 0，乘完自然也是 0。"""
    cs = clear_sky_ghi(times, lat, lon)
    kt = np.clip(0.72 + _smooth_noise(rng, len(times), 0.22), 0.05, 1.05)
    return cs * kt, cs


def _power(ghi, t2m, cap, rng):
    """GHI -> 功率：线性转换 + 组件温度降额，按装机截断，再加一点计量噪声。"""
    tcell = t2m + 0.030 * ghi
    p = cap * np.clip(ghi / 1000.0, 0.0, 1.15) * (1.0 - 0.004 * (tcell - 25.0))
    p = p + rng.normal(0.0, 0.004 * cap, len(ghi))
    return np.clip(p, 0.0, cap).round(3)


def _t2m(times, rng):
    """日变化气温：正午前后最高，凌晨最低。"""
    h = times.hour.to_numpy(float) + times.minute.to_numpy(float) / 60.0
    return (26.0 - 6.0 * np.cos((h - 14.0) / 24.0 * 2 * np.pi)
            + _smooth_noise(rng, len(times), 0.8)).round(2)


def build(date="2026-07-15", n_stations=len(STATIONS), seed=20260715):
    """返回 (input 帧, predict 帧, info 帧)。date 是起报日 D，起报时刻固定 D 10:00。"""
    stations = STATIONS[:n_stations]
    t0 = pd.Timestamp(date) + pd.Timedelta(hours=10)
    fut_t = pd.date_range(t0 + STEP, periods=N_FUTURE, freq=STEP)
    hist_t = pd.date_range(t0 - STEP * (N_HISTORY - 1), periods=N_HISTORY, freq=STEP)

    rows, pred_cols = [], {}
    for si, (st, cap, city, lat, lon, bias) in enumerate(stations):
        rng = np.random.default_rng(seed + si)
        ghi_f, cs_f = _ghi(fut_t, lat, lon, rng)                 # 未来真值
        ghi_h, _ = _ghi(hist_t, lat, lon, rng)                   # 历史实测
        t2m_f, t2m_h = _t2m(fut_t, rng), _t2m(hist_t, rng)

        # 预报 GHI：真值 + 预报误差，再整体乘上该站的系统性偏差，最后按 K_t<=1.2 收口，
        # 免得偏差把预报推到物理上不可能的辐照度上（K_t 扫描找的就是这个 bias）。
        err = cs_f * _smooth_noise(rng, N_FUTURE, 0.11)
        ghi_p = np.clip((ghi_f + err) * bias, 0.0, np.maximum(1.2 * cs_f, 5.0))

        row = {"station": st, "timestamp_win": t0,
               "GHI_real": ghi_h.round(2), "GHI_real_future": ghi_f.round(2),
               "GHI_SOLARGIS": (ghi_h * 0.99).round(2),          # SolarGIS 实测产品，与实测略有出入
               "TEMP_SOLARGIS": t2m_h,
               "GHI_SOLARGIS_predict": ghi_p.round(2), "TEMP_SOLARGIS_predict": t2m_f,
               "observe_power": _power(ghi_h, t2m_h, cap, rng),
               "observe_power_future": _power(ghi_f, t2m_f, cap, rng)}
        # NWP 网格点：9 个邻近格点，各自在站点值上偏一点
        for g in range(1, NWP_POS + 1):
            off = 1.0 + 0.02 * (g - 5)
            row[f"ssrd_pos_{g}"] = (ghi_h * off).round(2)
            row[f"ssrd_pos_{g}_predict"] = (ghi_p * off).round(2)
            row[f"t2m_pos_{g}"] = (t2m_h + 0.3 * (g - 5)).round(2)
            row[f"t2m_pos_{g}_predict"] = (t2m_f + 0.3 * (g - 5)).round(2)
        rows.append({k: (v.tolist() if isinstance(v, np.ndarray) else v) for k, v in row.items()})

        # 生产预测表：模型吃预报 GHI 出的功率，所以它天然带着预报误差 + 该站的 bias
        pred_cols[f"predict_power_{st}"] = pd.Series(_power(ghi_p, t2m_f, cap, rng), index=fut_t)

    # 列序照抄真实表：站号/起报时刻，9 个网格点的历史，9 个网格点的预报，最后是 GHI/温度/功率
    order = (["station", "timestamp_win"]
             + [f"{p}_pos_{g}" for g in range(1, NWP_POS + 1) for p in ("ssrd", "t2m")]
             + [f"{p}_pos_{g}_predict" for g in range(1, NWP_POS + 1) for p in ("ssrd", "t2m")]
             + ["GHI_real", "GHI_real_future", "GHI_SOLARGIS", "TEMP_SOLARGIS",
                "GHI_SOLARGIS_predict", "TEMP_SOLARGIS_predict",
                "observe_power", "observe_power_future"])
    inp = pd.DataFrame(rows)[order]
    assert inp["station"].is_unique, "station 必须全表唯一（inference.py 第 15 行的 assert）"
    assert inp["timestamp_win"].nunique() == 1, "timestamp_win 必须全表只有一个值（第 16 行的 assert）"

    D = pd.Timestamp(date)
    dtime = pd.date_range(D + pd.Timedelta(days=1), D + pd.Timedelta(days=5) - STEP, freq=STEP)
    pred = pd.DataFrame({"dtime": dtime})
    for c, s in pred_cols.items():
        pred[c] = s.reindex(dtime).to_numpy()          # 起报窗只覆盖到 D+5 10:00，之后留空

    info = pd.DataFrame([{"plantid": st.rsplit("guangfu", 1)[-1], "station": st,
                          "plantname": f"光伏{city}{st[-4:]}", "city": city,
                          "GCCAPCITY": cap, "LATITUDE": lat, "LONGITUDE": lon}
                         for st, cap, city, lat, lon, _ in stations])
    return inp, pred, info


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out-dir", default=os.path.dirname(os.path.abspath(__file__)))
    ap.add_argument("--date", default="2026-07-15", help="起报日 D（起报时刻固定 D 10:00）")
    ap.add_argument("--stations", type=int, default=len(STATIONS))
    ap.add_argument("--seed", type=int, default=20260715)
    a = ap.parse_args()
    os.makedirs(a.out_dir, exist_ok=True)
    inp, pred, info = build(a.date, min(a.stations, len(STATIONS)), a.seed)
    for name, df in (("mock_input.parquet", inp), ("mock_predict.parquet", pred)):
        df.to_parquet(os.path.join(a.out_dir, name), index=False)
    info.to_csv(os.path.join(a.out_dir, "mock_info.csv"), index=False)
    print(f"mock_input.parquet    {inp.shape[0]} 行 x {inp.shape[1]} 列   "
          f"station 唯一={inp['station'].is_unique}  timestamp_win={inp['timestamp_win'].iloc[0]}")
    print(f"mock_predict.parquet  {pred.shape[0]} 行 x {pred.shape[1]} 列   "
          f"dtime {pred.dtime.min()} -> {pred.dtime.max()}")
    print(f"mock_info.csv         {len(info)} 站（GCCAPCITY / LATITUDE / LONGITUDE / city）")
    print(f"-> {a.out_dir}")


if __name__ == "__main__":
    main()
