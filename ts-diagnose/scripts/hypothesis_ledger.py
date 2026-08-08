#!/usr/bin/env python3
"""假设账本校验：字段纪律 = component 必填 / 可否证 / provenance / 状态一致性。"""
import json, sys

REQUIRED = ["id", "claim", "component", "falsifiable_pred", "status", "provenance"]
STATUSES = {"pending", "confirmed", "refuted", "undecided"}

def validate_ledger(obj):
    errs = []
    for h in obj.get("hypotheses", []):
        hid = h.get("id", "?")
        for k in REQUIRED:
            if not h.get(k):
                errs.append(f"{hid}: 缺字段 {k}")
        if h.get("status") not in STATUSES:
            errs.append(f"{hid}: status 非法")
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
