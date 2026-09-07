#!/usr/bin/env python3
"""假设账本校验：字段纪律 = component 必填 / 可否证 / provenance / 状态一致性。"""
import json, sys

REQUIRED = ["id", "claim", "component", "falsifiable_pred", "status", "provenance"]
STATUSES = {"pending", "confirmed", "refuted", "undecided"}

def validate_ledger(obj):
    errs = []
    if not isinstance(obj, dict) or "hypotheses" not in obj:
        return ["顶层缺 hypotheses 键或非法对象"]
    hyps = obj["hypotheses"]
    if not isinstance(hyps, list):
        return [f"hypotheses 须为 list，实际是 {type(hyps).__name__}"]
    for h in hyps:
        if not isinstance(h, dict):
            errs.append(f"hypotheses 条目须为 dict，实际是 {type(h).__name__}")
            continue
        hid = h.get("id", "?")
        for k in REQUIRED:
            if not h.get(k):
                errs.append(f"{hid}: 缺字段 {k}")
        if h.get("status") not in STATUSES:
            errs.append(f"{hid}: status 非法")
        if h.get("provenance") == "no_candidate" and h.get("status") != "undecided":
            errs.append(f"{hid}: no_candidate 必须保持 undecided")
        if h.get("status") == "refuted" and not h.get("kill_receipt"):
            errs.append(f"{hid}: refuted 必须带 kill_receipt")
        if h.get("provenance") == "post-hoc" and h.get("status") == "confirmed" \
                and not h.get("kill_receipt"):
            errs.append(f"{hid}: post-hoc 假设升级为 confirmed 需新干预 receipt")
    return errs

def main():
    obj = json.load(open(sys.argv[1], encoding="utf-8"))
    errs = validate_ledger(obj)
    if errs:
        print("\n".join("✗ " + e for e in errs)); sys.exit(1)
    print("✓ 账本合法");
if __name__ == "__main__":
    main()
