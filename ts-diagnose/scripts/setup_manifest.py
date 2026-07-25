#!/usr/bin/env python3
"""setup 产物 manifest 落盘器（引擎机制脚本——pytest 单测覆盖，不走 gen_gate；
gen_gate 只闸运行时生成的分析脚本）。读规范长表 + 对齐报告 + config.materials，
写 setup_manifest.json：表/模型/freq/行数/窗口范围/完整材料清单（含训练日志与实验
配置的位置——下游 playbook 由此获知，不再各自问）/输入指纹（product_status 过期
检测的对账对象）。"""
from __future__ import annotations

import argparse
import os
import sys

import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import engine_common as ec  # noqa: E402


def _inputs_of(cfg):
    inputs = {}
    for mid, rec in ((cfg or {}).get("materials") or {}).items():
        if not isinstance(rec, dict) or rec.get("status") != "present":
            continue
        for i, p in enumerate(rec.get("paths") or []):
            if os.path.exists(p):
                key = mid if i == 0 else f"{mid}#{i}"
                inputs[key] = {"path": p, "fingerprint": ec.file_fingerprint(p)}
            else:
                print(f"⚠ 材料 {mid} 的路径不存在，未入指纹（过期检测对它失明）：{p}")
    return inputs


def build_manifest(pred_path, alignment_path, cfg):
    df = pd.read_csv(pred_path)
    align = ec.read_json(alignment_path) or {}
    tables = {"predictions": pred_path}
    for extra in ("features.csv", "train_y.csv"):
        if os.path.exists(extra):
            tables[extra.split(".")[0]] = extra
    inputs = _inputs_of(cfg)
    # 代码也是依赖（Snakemake 7.8 教训）：适配逻辑变了 → setup 产物即过期
    if os.path.exists("analysis_scripts/adapter.py"):
        inputs["_adapter_code"] = {
            "path": "analysis_scripts/adapter.py",
            "fingerprint": ec.file_fingerprint("analysis_scripts/adapter.py")}
    return {
        "product": "setup",
        "tables": tables,
        "models": sorted(df["model"].astype(str).unique().tolist()),
        "freq": align.get("freq"),
        "n_rows": int(len(df)),
        "window_range": [str(df["window_ts"].min()), str(df["window_ts"].max())],
        "materials": (cfg or {}).get("materials") or {},
        "inputs": inputs,
    }


def main():
    ap = argparse.ArgumentParser(description="setup 产物 manifest 落盘")
    ap.add_argument("--pred", default="predictions.csv")
    ap.add_argument("--alignment", default="alignment_report.json")
    ap.add_argument("--config", default=ec.CONFIG_PATH)
    ap.add_argument("--out", default="setup_manifest.json")
    a = ap.parse_args()
    man = build_manifest(a.pred, a.alignment, ec.read_json(a.config))
    ec.dump_json(man, a.out)
    print(f"setup_manifest → {a.out}：models={man['models']} "
          f"n_rows={man['n_rows']} freq={man['freq']} inputs={sorted(man['inputs'])}")


if __name__ == "__main__":
    main()
