#!/usr/bin/env python3
"""metric-eval 金标准：确定性长表（零随机）——已是规范长表形态（模拟 setup 产物的
predictions.csv），2 模型 × 2 窗 × 4 horizon 步。
偏置手算：模型 A 恒定偏置 +0.5（每行误差平方 0.25）→ rmse_192 口径下 RMSE = 0.5；
模型 B 交替偏置 ±1.0（每行误差平方 1.0）→ RMSE = 1.0。两值均可手算复核，无需再跑代码。"""
import pandas as pd


def main():
    rows = []
    biases = {
        "A": lambda w, s: 0.5,
        "B": lambda w, s: 1.0 if s % 2 == 0 else -1.0,
    }
    for model, bias_fn in biases.items():
        for w in range(2):
            for s in range(4):
                y_true = float(w + s)
                y_pred = y_true + bias_fn(w, s)
                rows.append({
                    "window_ts": f"2024-01-0{w + 1}T00:00:00",
                    "unit_id": "S1",
                    "model": model,
                    "horizon_step": s,
                    "y_true": y_true,
                    "y_pred": y_pred,
                })
    pd.DataFrame(rows).to_csv("predictions.csv", index=False)


if __name__ == "__main__":
    main()
