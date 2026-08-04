"""Stage 2 参考实现（切片证据线）：直接复用 chartbook 预写 worst-slice-compare
的 compute——参考实现与产线同源，钉住「Stage 2 不现场写图代码」的契约。"""
import argparse
import json
import os
import sys

import pandas as pd

_ENGINE = os.path.abspath(os.path.join(
    os.path.dirname(os.path.abspath(__file__)), "..", "..", "..", ".."))
sys.path.insert(0, os.path.join(_ENGINE, "chartbook", "scripts"))

import chart_common as cc                    # noqa: E402
import chart_worst_slice_compare as cwsc     # noqa: E402


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--pred", required=True)
    ap.add_argument("--focal", required=True)
    ap.add_argument("--out", required=True)
    a = ap.parse_args()
    stats = cwsc.compute(cc.load_predictions(a.pred), focal_model=a.focal)
    json.dump(stats, open(a.out, "w"), ensure_ascii=False, indent=2)


if __name__ == "__main__":
    main()
