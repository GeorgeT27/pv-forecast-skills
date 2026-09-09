#!/usr/bin/env python3
"""通用产物 manifest 落盘器（setup 有专用 setup_manifest.py，域字段更全；
其余产物——chart_sweep 等——用本脚本）。只记产物 id + 来源材料指纹，
供 product_status 过期检测。引擎机制脚本，pytest 单测覆盖，不走 gen_gate。"""
from __future__ import annotations

import argparse
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import engine_common as ec  # noqa: E402


def main():
    ap = argparse.ArgumentParser(description="通用产物 manifest 落盘")
    ap.add_argument("--product", required=True)
    ap.add_argument("--config", default=ec.CONFIG_PATH)
    ap.add_argument("--out", required=True)
    ap.add_argument("--input", action="append", default=[],
                    metavar="KEY=PATH", help="额外输入指纹（如上游产物 manifest）")
    a = ap.parse_args()
    inputs = {}
    for mid, rec in ((ec.read_json(a.config) or {}).get("materials") or {}).items():
        if isinstance(rec, dict) and rec.get("status") == "present":
            for i, p in enumerate(rec.get("paths") or []):
                if os.path.exists(p):
                    key = mid if i == 0 else f"{mid}#{i}"
                    inputs[key] = {"path": p,
                                   "fingerprint": ec.path_fingerprint(p)}
                else:
                    print(f"⚠ 材料 {mid} 的路径不存在，未入指纹（过期检测对它失明）：{p}")
    for spec in a.input:
        key, _, path = spec.partition("=")
        if not path:
            sys.exit(f"--input 需要 KEY=PATH 形式：{spec}")
        if os.path.exists(path):
            inputs[key] = {"path": path,
                           "fingerprint": ec.path_fingerprint(path)}
        else:
            print(f"⚠ --input {key} 路径不存在，未入指纹：{path}")
    ec.dump_json({"product": a.product, "inputs": inputs}, a.out)
    print(f"{a.product} manifest → {a.out}（inputs={sorted(inputs)}）")


if __name__ == "__main__":
    main()
