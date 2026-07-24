#!/usr/bin/env python3
"""feature-importance playbook 的 feature-quality 变体金标准输入生成器——**确定性解析式构造，零随机**。

场景：40 行滚动窗（33 个相邻行的连续块 06:00–14:00 覆盖 day1 09:00 + day2..day8 的 09:00 行），
所有序列都是物理时间 T 的解析函数——这样滚动窗一致性（行 t 点 k == 行 t+1 点 k-1）天然成立，
坏行由「预报崩坏区间」被口径切片覆盖而自然涌现（埋点绝不能按行埋，会破坏窗口重叠约束）。

植入三个已知效应（期望见 manifest.json，改本文件前先想清楚期望要跟着改，并重跑 pytest）：
  - f_blame：day2 08:00–16:00 预报崩坏 d=+30，且模型预测 pred = y − 0.6·d（M1）/ − 0.3·d（ensemble）
      → ultra_short 坏行 = day2 09:00（第16点=13:00 落在区间），short 坏行 = day1 09:00
        （[59:155] 覆盖 day2 全天）；特征误差与行误差全局 Spearman = 1 → 必须被归罪。
  - f_decoy：day5 08:00–16:00 特征误差 +40 但**不耦合进任何模型预测**
      → 特征误差巨大、全局相关 ≈ 0 → 必须不被归罪（诱饵有牙测试钉这个）。
  - f_good / ghi 对（nwp_ghi_fc/ghi_obs 奇异命名，练配对启发式）：预测=真值，零误差。
  - mystery_x：孤列配不成对 → 必须出现在 unmapped 里（练"配不上就问用户"路径）。

翻新跳变埋点（v2，练 feature_revision + 反事实阶梯；跳变项是 (行起点 T, 物理时刻 t) 的函数
——同一 t 在相邻行取不同值，这正是"逐行重新起报"的物理，真值列仍是纯 t 函数，窗一致性闸不受扰）：
  - f_jumpy：pred = true + s(T)·A(t)，s=行步进 parity 符号（相邻行同一物理时刻预报差 2A——跳变），
      A(t)=8·(1+max(0,sin(π(h−6)/12))) 白天大夜里小（幅度随时刻变化，churn 相关才有排名信号）。
      pred_M3 = y − 0.5·s(T)·A(t) 消费这个坏信号 → M3 的行间 churn 与 f_jumpy 的跳变完全相关
      （revision 两关必点名）；同时 M3 的行误差经真值误差路径正当归因到 f_jumpy（Stage 2）。
      f_jumpy 对 M1/ensemble 零耦合 → 不得被点名。
  - f_jumpy_decoy：pred = true + s₄(T)·25（period-4 方波，跳变幅恒 50、比 f_jumpy 更大）但
      **不进任何模型** → 跳变巨大、与任何模型 churn 相关 ≈ 0 → 必须不被点名（跳变大≠有罪）。

数据结构与真实约定一致：
  golden_test.parquet         timestamp + observe_power_future(192) + 特征列(864 = 672 历史观测
                              + 192 未来预报；历史止于 T：点 j 的时间 = T+(j-672)Δ，惯例 A)
  golden_predict.parquet      timestamp + pred_M1 / pred_ensemble（各 192，练 1..N 模型鲁棒）
  golden_feature_true.parquet timestamp_win（故意与 test 不同名，练时间戳侦测）+ 每特征
                              *_pred / *_true 各 192
"""
import math
import os

import numpy as np
import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
FREQ = pd.Timedelta("15min")
H, HIST = 192, 672
D2, D5 = pd.Timestamp("2025-01-02"), pd.Timestamp("2025-01-05")


def hour_of(t: pd.Timestamp) -> float:
    return t.hour + t.minute / 60.0


def y(t):                                   # 真实功率：白天正弦
    return 100.0 * max(0.0, math.sin(math.pi * (hour_of(t) - 6.0) / 12.0))


def f_blame_true(t):
    return 50.0 + 10.0 * math.sin(2 * math.pi * hour_of(t) / 24.0) + u_incom("f_blame", t)


def f_decoy_true(t):
    return 80.0 + 5.0 * math.cos(2 * math.pi * hour_of(t) / 24.0) + u_incom("f_decoy", t)


def f_good_true(t):
    return 20.0 + 2.0 * math.sin(2 * math.pi * hour_of(t) / 24.0 + 1.0) + u_incom("f_good", t)


def ghi_true(t):
    return 500.0 * max(0.0, math.sin(math.pi * (hour_of(t) - 6.0) / 12.0)) \
        + u_incom("ghi", t, 50.0)


def d_blame(t):                             # f_blame 的预报崩坏区间（day2 08:00–16:00）
    return 30.0 if (t.normalize() == D2 and 8.0 <= hour_of(t) < 16.0) else 0.0


def d_decoy(t):                             # 诱饵崩坏（day5），不进任何模型预测
    return 40.0 if (t.normalize() == D5 and 8.0 <= hour_of(t) < 16.0) else 0.0


# ------------------------------------------------- 翻新跳变埋点（v2）
EPOCH = pd.Timestamp("2025-01-01")


def f_jumpy_true(t):
    return 60.0 + 5.0 * math.sin(2 * math.pi * hour_of(t) / 24.0 + 2.0) \
        + u_incom("f_jumpy", t, 35.0)
# u 幅 35（非默认 25）：own-pred hinge（df=5）能借「pred 数值本身编码 parity 分支」
# 部分代理 A_jump(t) 的跳变结构（Task 3 诊断发现，不同于 Task 2 的纯 hod 谐波退化）；
# 加大 u 使 pred 数值不再干净地编码 parity 分支，sys_frac 0.42→0.31，见 checklist 项 5。


def f_jumpy_decoy_true(t):
    return 40.0 + 3.0 * math.cos(2 * math.pi * hour_of(t) / 24.0) + u_incom("f_jumpy_decoy", t)


def A_jump(t):                              # 跳变幅：白天 16 夜里 8（随物理时刻平滑变化）
    return 8.0 * (1.0 + max(0.0, math.sin(math.pi * (hour_of(t) - 6.0) / 12.0)))


def s_parity(T):                            # 行步进 parity 符号：相邻行必翻转 → 每对都跳
    return 1.0 if int((T - EPOCH) / FREQ) % 2 == 0 else -1.0


def s_period4(T):                           # period-4 方波：隔对才跳，与 parity 序列近零相关
    return 1.0 if int((T - EPOCH) / FREQ) % 4 < 2 else -1.0


# ---- 反退化项：真值不可由设计矩阵表示（见 plan Task 3 首注） ----
U_REG = {"f_blame": (89, 0.3), "f_decoy": (113, 1.1), "f_good": (131, 2.0),
         "ghi": (151, 0.7), "f_jumpy": (173, 1.7), "f_jumpy_decoy": (197, 2.6),
         "f_sys_bias": (211, 0.9), "f_res_culprit": (233, 1.9),
         "f_irreducible": (251, 0.2)}


def u_incom(name, t, amp=25.0):
    P, phi = U_REG[name]
    n = int((t - EPOCH) / FREQ)
    return amp * math.sin(2 * math.pi * n / P + phi)


# ------------------------------------------------- ε 分解埋点（v3；全部纯 f(物理时间)）
def dayidx(t):
    return (t.normalize() - pd.Timestamp("2025-01-01")).days


def daytime(t):
    return max(0.0, math.sin(math.pi * (hour_of(t) - 6.0) / 12.0))


def f_sys_bias_true(t):                     # 幅度逐日增长：per-row 误差才有跨行排名信号
    return (20.0 + 4.0 * dayidx(t)) * daytime(t) + 30.0 + u_incom("f_sys_bias", t, 10.0)
# （+30 抬底、u 幅取 10：保持真值为正，乘性偏差 0.3·true 仍逐日增长主导）
# pred = 1.3×true：乘性系统偏差（报得越高越偏高）。不进任何模型预测 =「模型已补偿」。
# 陷阱设计：raw 误差逐日增长、与 pred_M4res 行误差 raw-Spearman 高 → 旧逻辑必冤枉；
# own-pred 线性精确捕获 ε=(0.3/1.3)·pred（恒等式，与 u 无关）且跨期稳定 → λ≈1、
# ε_res≈0 → 剥后必不点名。


def f_res_culprit_true(t):
    return 45.0 + 5.0 * math.sin(2 * math.pi * hour_of(t) / 24.0) + u_incom("f_res_culprit", t)


def w_culprit(t):                           # period-16（4h）波动：≤3 阶钟点谐波装不下
    n = int((t - EPOCH) / FREQ)
    return (4.0 + 1.5 * dayidx(t)) * math.sin(2 * math.pi * n / 16.0 + 0.5)
# ε_sys≈0、ε_res=w 驱动 pred_M4res → 必点名；lag-1=cos(2π/16)≈0.92 → 可约性高过闸。


def f_irreducible_true(t):
    return 35.0 + 5.0 * math.cos(2 * math.pi * hour_of(t) / 24.0) + u_incom("f_irreducible", t)


def v_irred(t):                             # period-4 近奈奎斯特：lag-1=cos(π/2)=0 → 不可约
    n = int((t - EPOCH) / FREQ)
    return (6.0 + 2.0 * dayidx(t)) * math.sin(math.pi * n / 2.0 + 0.7)
# 也驱动 pred_M4res（z/ρ 双关都过）→ 唯一挡它的是可约性闸——证明闸有牙。
# 注意：ε_res ≈ (1−β)v − β·u 混入少量平滑 u → 可约性非严格 0；断言按实测留余量，
# 必须 < 0.1 闸线且与 f_res_culprit（≥0.5）拉得开；不达标先调大 u 幅或 v 幅再看。


def series(fn, start, n, step0=0):
    return np.asarray([fn(start + (step0 + k) * FREQ) for k in range(n)], np.float32)


def main():
    block = pd.date_range("2025-01-01 06:00", periods=33, freq=FREQ)     # 含 day1 09:00
    nines = pd.date_range("2025-01-02 09:00", periods=7, freq="1D")      # day2..day8 09:00
    rows = block.append(nines)

    test, pred, ft = [], [], []
    for T in rows:
        feat864 = {}
        for name, fn, bust in (("f_blame", f_blame_true, d_blame),
                               ("f_decoy", f_decoy_true, d_decoy),
                               ("f_good", f_good_true, None),
                               ("ghi", ghi_true, None)):
            hist = series(fn, T, HIST, step0=-HIST)                      # 历史观测，止于 T
            fut_true = series(fn, T, H)
            fut_pred = fut_true + (series(bust, T, H) if bust else 0.0)  # 未来段 = 预报值
            feat864[name] = np.concatenate([hist, fut_pred]).astype(np.float32)
            if name == "ghi":                                            # 奇异命名对
                ft_cols = {"nwp_ghi_fc": fut_pred, "ghi_obs": fut_true}
            else:
                ft_cols = {f"{name}_pred": fut_pred, f"{name}_true": fut_true}
            feat864.setdefault("_ft", {}).update(ft_cols)
        for name, fn, sign_fn, amp_fn in (("f_jumpy", f_jumpy_true, s_parity, A_jump),
                                          ("f_jumpy_decoy", f_jumpy_decoy_true, s_period4,
                                           lambda t: 25.0)):
            hist = series(fn, T, HIST, step0=-HIST)                      # 历史观测 = 真值
            fut_true = series(fn, T, H)
            fut_pred = (fut_true + sign_fn(T) * series(amp_fn, T, H)).astype(np.float32)
            feat864[name] = np.concatenate([hist, fut_pred]).astype(np.float32)
            feat864["_ft"].update({f"{name}_pred": fut_pred, f"{name}_true": fut_true})
        for name, fn, wig in (("f_sys_bias", f_sys_bias_true, None),
                              ("f_res_culprit", f_res_culprit_true, w_culprit),
                              ("f_irreducible", f_irreducible_true, v_irred)):
            hist = series(fn, T, HIST, step0=-HIST)
            fut_true = series(fn, T, H)
            if wig is None:
                fut_pred = (1.3 * fut_true).astype(np.float32)      # 乘性系统偏差
            else:
                fut_pred = (fut_true + series(wig, T, H)).astype(np.float32)
            feat864[name] = np.concatenate([hist, fut_pred]).astype(np.float32)
            feat864["_ft"].update({f"{name}_pred": fut_pred, f"{name}_true": fut_true})
        yy = series(y, T, H)
        dd = series(d_blame, T, H)
        test.append({"timestamp": T, "observe_power_future": yy,
                     **{k: v for k, v in feat864.items() if k != "_ft"}})
        pred.append({"timestamp": T,
                     "pred_M1": (yy - 0.6 * dd).astype(np.float32),
                     "pred_ensemble": (yy - 0.3 * dd).astype(np.float32),
                     "pred_M3": (yy - 0.5 * s_parity(T) * series(A_jump, T, H)).astype(np.float32),
                     "pred_M4res": (yy - 0.55 * series(w_culprit, T, H)
                                    - 0.45 * series(v_irred, T, H)).astype(np.float32)})
        ft.append({"timestamp_win": T, **feat864["_ft"],
                   "mystery_x": np.full(H, 7.0, np.float32)})

    for name, recs in (("golden_test.parquet", test),
                       ("golden_predict.parquet", pred),
                       ("golden_feature_true.parquet", ft)):
        df = pd.DataFrame(recs)
        df.to_parquet(os.path.join(HERE, name), index=False)
        print(f"写出 {name}（{len(df)} 行 × {len(df.columns)} 列）")


if __name__ == "__main__":
    main()
