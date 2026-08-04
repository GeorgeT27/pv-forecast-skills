"""chartbook 测试共用：解析式构造规范长表（零随机——符号按 step 奇偶交替，
使每单元格 RMSE 恰等于幅度）。"""
import pandas as pd


def make_long(models, units, windows, steps, err_fn,
              y_fn=lambda w, u, s: 10.0):
    """err_fn(model, unit, window, step) -> 有符号误差；window 传字符串日期。"""
    rows = []
    for m in models:
        for u in units:
            for w in windows:
                for s in range(steps):
                    y = y_fn(w, u, s)
                    e = err_fn(m, u, w, s)
                    rows.append({"window_ts": w, "unit_id": u, "model": m,
                                 "horizon_step": s, "y_true": y,
                                 "y_pred": y + e})
    return pd.DataFrame(rows)


def alt(amp, s):
    """幅度 amp、按 step 奇偶交替符号 ⇒ RMSE == amp。"""
    return amp * (1.0 if s % 2 == 0 else -1.0)
