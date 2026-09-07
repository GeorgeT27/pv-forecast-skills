#!/usr/bin/env python3
"""确定性假适配器（评估器契约的参考实现，不训练，测试 / golden / dry-run 用）。
primary = 0.20 + 0.10*dropout − 0.03*[tsmixer_no_channel_mix] + 0.02*[learning_rate ≥ 2e-3] + 种子噪声(≤0.002)
slices：horizon:near = 0.8*primary；horizon:mid = primary；horizon:far = 1.3*primary + 0.05*[tsmixer_no_channel_mix]
（关掉通道混合整体变好但远端退化——用来测守护切片。）
config.crash=true → 退出码 2 且不写 metrics.json；config.sleep_s>0 → 先睡（测超时）。
sealed/test_metrics.json = primary×1.1（封存，环内不读）。"""
import argparse
import datetime as dt
import json
import os
import time


def compute(cfg, seed):
    p = (0.20 + 0.10 * float(cfg.get("dropout", 0.1))
         - (0.03 if cfg.get("tsmixer_no_channel_mix") else 0.0)
         + (0.02 if float(cfg.get("learning_rate", 1e-3)) >= 2e-3 else 0.0)
         + ((int(seed) * 7919) % 1000) / 1000 * 0.002)
    far = 1.3 * p + (0.05 if cfg.get("tsmixer_no_channel_mix") else 0.0)
    return p, {"horizon:near": 0.8 * p, "horizon:mid": p, "horizon:far": far}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--config", required=True)
    ap.add_argument("--seed", type=int, required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--time-limit", type=int, default=0)
    a = ap.parse_args()
    cfg = json.load(open(a.config, encoding="utf-8"))
    os.makedirs(a.out, exist_ok=True)
    t0 = dt.datetime.now().isoformat(timespec="seconds")
    if cfg.get("sleep_s"):
        time.sleep(float(cfg["sleep_s"]))
    if cfg.get("crash"):
        raise SystemExit(2)
    p, sl = compute(cfg, a.seed)
    os.makedirs(os.path.join(a.out, "sealed"), exist_ok=True)
    with open(os.path.join(a.out, "sealed", "test_metrics.json"), "w", encoding="utf-8") as f:
        json.dump({"test_primary": p * 1.1, "metric_id": "test_mse"}, f, indent=2)
    with open(os.path.join(a.out, "metrics.json"), "w", encoding="utf-8") as f:
        json.dump({"status": "ok", "primary": p, "metric_id": "val_mse", "slices": sl,
                   "t_start": t0, "t_end": dt.datetime.now().isoformat(timespec="seconds"),
                   "config": cfg, "error": None}, f, ensure_ascii=False, indent=2)


if __name__ == "__main__":
    main()
