#!/usr/bin/env python3
"""lsf-mini 训练入口适配器（评估器契约实现，契约见 ts-diagnose/references/evaluator-contract.md）。
用法：python3 lsf_mini_adapter.py --config cfg.json --seed 7 --out DIR [--time-limit 900]
cfg.json：lsf_mini_dir（lsf-mini 仓库绝对路径）+ run.py 参数（model/data/root_path/enc_in/seq_len/pred_len/…，
root_path 写绝对路径）。流程：子进程跑 run.py（cwd=DIR，results.csv 落 DIR/results/）→ 载 DIR/ckpt.pth 在
val 集推理 → primary=val_mse（标准化空间，与 run.py 的 test_mse 同口径）+ 切片 MSE（horizon 三桶 × 通道）
→ DIR/metrics.json。run.py 自带的 test 指标只写 DIR/sealed/test_metrics.json（封存）；pred.npy/true.npy
算完即删（Weather 单次各 84 MB）。
primary 的精确定义：对全体 val 窗口 (样本×时间步×通道) 的逐元素平方误差展平取 mean——这与 run.py
自己算 test_mse 的口径完全一致，两者可比。它不是 run.py 早停用来选 ckpt 的 val_loss（run.py 的
val_loss 是先对每个 batch 求均值、再对各 batch 的均值取均值；末尾不满批时两种口径的加权不同）。"""
import argparse
import datetime as dt
import json
import os
import re
import subprocess
import sys

RUN_KEYS = ("model", "data", "root_path", "features", "target", "seq_len", "label_len", "pred_len", "enc_in",
            "d_model", "n_heads", "e_layers", "d_ff", "dropout", "factor", "moving_avg", "patch_len", "stride",
            "frets_embed_size", "corrupt_col", "activation", "embed", "freq", "batch_size", "learning_rate",
            "train_epochs", "patience", "num_workers")
FLAG_KEYS = ("itrans_no_attn", "ptst_layernorm", "nlinear_avginit", "dlinear_reanchor",
             "tsmixer_no_channel_mix", "tide_no_residual", "frets_channel_indep")


def _now():
    return dt.datetime.now().isoformat(timespec="seconds")


def build_cmd(cfg, seed, out):
    cmd = [sys.executable, os.path.join(cfg["lsf_mini_dir"], "run.py"), "--seed", str(seed),
           "--save_dir", out, "--checkpoints", os.path.join(out, "checkpoints")]
    for k in RUN_KEYS:
        if k in cfg:
            cmd += [f"--{k}", str(cfg[k])]
    for k in FLAG_KEYS:
        if cfg.get(k):
            cmd.append(f"--{k}")
    return cmd


def _write(out, doc):
    with open(os.path.join(out, "metrics.json"), "w", encoding="utf-8") as f:
        json.dump(doc, f, ensure_ascii=False, indent=2)


def _fail(out, status, error, cfg, t0):
    _write(out, {"status": status, "primary": None, "metric_id": "val_mse", "slices": {},
                 "t_start": t0, "t_end": _now(), "config": cfg, "error": error})


def slices_of(err, names):
    """err: (N, L, C) 平方误差 → horizon 三桶 + 每通道 的 MSE。"""
    L = err.shape[1]
    b = [0, L // 3, 2 * L // 3, L]
    out = {"horizon:near": float(err[:, b[0]:b[1]].mean()),
           "horizon:mid": float(err[:, b[1]:b[2]].mean()),
           "horizon:far": float(err[:, b[2]:b[3]].mean())}
    for i, n in enumerate(names):
        out[f"channel:{n}"] = float(err[:, :, i].mean())
    return out


def channel_names(cfg, n):
    csv = os.path.join(cfg["root_path"], f"{cfg['data']}.csv")
    if os.path.exists(csv):
        with open(csv, encoding="utf-8") as f:
            cols = [c for c in f.readline().strip().split(",") if c != "date"]
        if len(cols) == n:
            return [re.sub(r"[^0-9A-Za-z_]+", "_", c).strip("_") for c in cols]
    return [f"c{i}" for i in range(n)]


def val_predict(cfg, out):
    sys.path.insert(0, cfg["lsf_mini_dir"])
    import importlib
    import numpy as np
    import torch
    from run import build_loader, run_epoch
    meta = json.load(open(os.path.join(out, "config.json"), encoding="utf-8"))
    args = argparse.Namespace(**meta)
    _, loader = build_loader(args, "val")
    model = importlib.import_module(f"models.{args.model}").Model(args).float()
    model.load_state_dict(torch.load(os.path.join(out, "ckpt.pth")))
    model.eval()
    _, preds, trues = run_epoch(model, loader, args, torch.device("cpu"), torch.nn.MSELoss())
    return np.asarray(preds), np.asarray(trues), meta


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--config", required=True)
    ap.add_argument("--seed", type=int, required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--time-limit", type=int, default=900)
    a = ap.parse_args()
    out = os.path.abspath(a.out)
    os.makedirs(out, exist_ok=True)
    t0 = _now()
    try:
        cfg = json.load(open(a.config, encoding="utf-8"))
    except (OSError, ValueError) as e:
        _fail(out, "crash", f"config load failed: {type(e).__name__}: {e}"[-2000:], {}, t0)
        sys.exit(2)
    for k in ("lsf_mini_dir", "model", "data", "root_path"):
        if k not in cfg:
            _fail(out, "crash", f"config 缺 {k}", cfg, t0)
            sys.exit(2)
    try:
        r = subprocess.run(build_cmd(cfg, a.seed, out), cwd=out, capture_output=True, text=True, timeout=a.time_limit)
    except subprocess.TimeoutExpired:
        _fail(out, "timeout", f"run.py 超过 {a.time_limit}s", cfg, t0)
        sys.exit(3)
    if r.returncode != 0:
        _fail(out, "crash", (r.stderr or r.stdout or "")[-2000:], cfg, t0)
        sys.exit(2)
    try:
        import numpy as np
        preds, trues, meta = val_predict(cfg, out)
        err = (preds - trues) ** 2
        names = channel_names(cfg, err.shape[2])
        primary = float(err.mean())
        sl = slices_of(err, names)
        tp, tt = np.load(os.path.join(out, "pred.npy")), np.load(os.path.join(out, "true.npy"))
        test_slices = slices_of((tp - tt) ** 2, names)
    except Exception as e:  # 推理或切片失败也算 crash，带一句原因
        _fail(out, "crash", f"val 推理失败：{type(e).__name__}: {e}"[-2000:], cfg, t0)
        sys.exit(2)
    os.makedirs(os.path.join(out, "sealed"), exist_ok=True)
    with open(os.path.join(out, "sealed", "test_metrics.json"), "w", encoding="utf-8") as f:
        json.dump({"test_primary": float(meta["test_mse"]), "test_mae": float(meta["test_mae"]),
                   "metric_id": "test_mse", "test_slices": test_slices}, f, indent=2)
    for name in ("pred.npy", "true.npy"):
        p = os.path.join(out, name)
        if os.path.exists(p):
            os.remove(p)
    _write(out, {"status": "ok", "primary": primary, "metric_id": "val_mse", "slices": sl,
                 "n_epochs": len(meta.get("epoch_log") or []), "best_val_epoch": meta.get("best_val_epoch"),
                 "n_params": meta.get("n_params"), "t_start": t0, "t_end": _now(), "config": cfg, "error": None})
    print(json.dumps({"status": "ok", "primary": primary}))


if __name__ == "__main__":
    main()
