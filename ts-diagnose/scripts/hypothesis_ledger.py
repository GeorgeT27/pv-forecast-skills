#!/usr/bin/env python3
"""假设账本校验：字段纪律 = component 必填 / 可否证 / provenance / 状态一致性；kind=improvement 条目另查 fix 四字段与 receipt。"""
import json, sys

REQUIRED = ["id", "claim", "component", "falsifiable_pred", "status", "provenance"]
STATUSES = {"pending", "confirmed", "refuted", "undecided", "untested"}
KINDS = {"mechanism", "improvement"}
FIX_REQUIRED = ["target_model", "config_diff", "predicted_gain", "guard_slices"]

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
        kind = h.get("kind", "mechanism")
        if kind not in KINDS:
            errs.append(f"{hid}: kind 非法（{kind}），只许 mechanism / improvement")
        if kind == "improvement":
            fix = h.get("fix")
            if not isinstance(fix, dict):
                errs.append(f"{hid}: improvement 假设必须带 fix 对象")
            else:
                for k in FIX_REQUIRED:
                    if not fix.get(k):
                        errs.append(f"{hid}: fix 缺 {k}")
                if fix.get("config_diff") is not None and not isinstance(fix["config_diff"], dict):
                    errs.append(f"{hid}: fix.config_diff 须为 dict（键=knob 名）")
                if fix.get("guard_slices") is not None and not isinstance(fix["guard_slices"], list):
                    errs.append(f"{hid}: fix.guard_slices 须为 list")
            if h.get("status") == "confirmed" and not h.get("receipt"):
                errs.append(f"{hid}: improvement 假设升 confirmed 必须带 receipt（receipts/E*.json 路径）")
        if h.get("status") == "untested" and not h.get("untested_reason"):
            errs.append(f"{hid}: untested 必须带 untested_reason（crash/timeout 与一句原因）")
    return errs

def main():
    obj = json.load(open(sys.argv[1], encoding="utf-8"))
    errs = validate_ledger(obj)
    if errs:
        print("\n".join("✗ " + e for e in errs)); sys.exit(1)
    print("✓ 账本合法");
if __name__ == "__main__":
    main()
