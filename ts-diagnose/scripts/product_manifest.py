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
    a = ap.parse_args()
    inputs = {}
    for mid, rec in ((ec.read_json(a.config) or {}).get("materials") or {}).items():
        if isinstance(rec, dict) and rec.get("status") == "present":
            for p in rec.get("paths") or []:
                if os.path.exists(p):
                    inputs.setdefault(mid, {"path": p,
                                            "fingerprint": ec.file_fingerprint(p)})
    ec.dump_json({"product": a.product, "inputs": inputs}, a.out)
    print(f"{a.product} manifest → {a.out}（inputs={sorted(inputs)}）")


if __name__ == "__main__":
    main()
