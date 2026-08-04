"""Stage 1 参考实现：跑通两张代表图（分解类+对比类），钉住「体检=复用 chartbook
预写脚本」契约。"""
import argparse
import json
import os
import sys

_ENGINE = os.path.abspath(os.path.join(
    os.path.dirname(os.path.abspath(__file__)), "..", "..", "..", ".."))
sys.path.insert(0, os.path.join(_ENGINE, "chartbook", "scripts"))

import chart_common as cc              # noqa: E402
import chart_error_breakdown as ceb    # noqa: E402
import chart_oracle_gap as cog         # noqa: E402


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--pred", required=True)
    ap.add_argument("--out-eb", required=True)
    ap.add_argument("--out-og", required=True)
    a = ap.parse_args()
    df = cc.load_predictions(a.pred)
    json.dump(ceb.compute(df), open(a.out_eb, "w"), ensure_ascii=False)
    json.dump(cog.compute(df), open(a.out_og, "w"), ensure_ascii=False)


if __name__ == "__main__":
    main()
