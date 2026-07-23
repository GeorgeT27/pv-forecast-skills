"""Stage 2 参考实现（跨维稳定性证据线）：直接复用 chartbook 预写
cross-dim-stability 的 compute——参考实现与产线同源，钉住「稳定性检查
不现场写代码」的契约。"""
import argparse
import json
import os
import sys

_ENGINE = os.path.abspath(os.path.join(
    os.path.dirname(os.path.abspath(__file__)), "..", "..", "..", ".."))
sys.path.insert(0, os.path.join(_ENGINE, "chartbook", "scripts"))

import chart_common as cc                    # noqa: E402
import chart_cross_dim_stability as ccds     # noqa: E402


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--pred", required=True)
    ap.add_argument("--focal", required=True)
    ap.add_argument("--out", required=True)
    a = ap.parse_args()
    stats = ccds.compute(cc.load_predictions(a.pred), focal_model=a.focal)
    json.dump(stats, open(a.out, "w"), ensure_ascii=False, indent=2)


if __name__ == "__main__":
    main()
