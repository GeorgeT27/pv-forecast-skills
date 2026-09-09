#!/usr/bin/env python3
"""假设账本校验：字段纪律 = component 必填 / 可否证 / provenance / 状态一致性；
kind=improvement 条目另查 fix 四字段与 receipt；slice_map/uncovered 的结构与覆盖。

给了 slice_zcheck.json（默认读工作目录同名文件）就做认领核对：每个 verdict=="real"
的切片必须登记进 slice_map 或 uncovered。漏登记在 r1 真跑里没人发现，一路带到 Stage 3
才被收口脚本抓出来——那时已经晚了三个阶段。"""
import argparse, hashlib, json, os, sys

REQUIRED = ["id", "claim", "component", "falsifiable_pred", "status", "provenance"]
STATUSES = {"pending", "confirmed", "refuted", "undecided", "untested"}
KINDS = {"mechanism", "improvement"}
FIX_REQUIRED = ["target_model", "config_diff", "predicted_gain", "guard_slices"]
# slice_map 每行的必填两件。此前全引擎没有任何地方写过这个 schema，于是真跑里出现过
# {slice, claimed_by, ...} 与 {dim, bucket, ...} 两套不兼容形态——而下游（收口脚本、
# guard_slices 默认取值）全都键 slice/claimed_by,键不上就静默当成没认领。
SLICE_ROW_REQUIRED = ["slice", "claimed_by"]

def _uncovered_names(obj):
    """uncovered 两种形态都收：裸字符串，或 {"slice":..., "note":...}。"""
    out = []
    for row in (obj.get("uncovered") or []):
        name = row.get("slice") if isinstance(row, dict) else row
        if name:
            out.append(str(name))
    return out


def validate_slice_map(obj, real_slices=None, zcheck_slices=None):
    """slice_map/uncovered 的结构、去重、互斥与覆盖。real_slices 给了才做覆盖对账。"""
    errs = []
    smap = obj.get("slice_map")
    if smap is None:
        return errs                      # 不是每本剧本都产 slice_map（改进环账本就没有）
    if not isinstance(smap, list):
        return [f"slice_map 须为 list，实际是 {type(smap).__name__}"]
    seen, claimed = set(), set()
    for row in smap:
        if not isinstance(row, dict):
            errs.append(f"slice_map 条目须为 dict，实际是 {type(row).__name__}")
            continue
        name = row.get("slice")
        if not name:
            errs.append(f"slice_map 有条目缺 slice 名（必填 {SLICE_ROW_REQUIRED}；"
                        f"slice 取值须与 slice_zcheck.json 的切片名一字不差）：{row}")
            continue
        if "claimed_by" not in row:
            errs.append(f"{name}: slice_map 行缺 claimed_by（无人认领写 []，"
                        "不许省略——省略与 [] 在下游是两个意思）")
        if name in seen:
            errs.append(f"slice_map 重复登记切片 {name}")
        seen.add(name)
        cb = row.get("claimed_by")
        if cb is not None and not isinstance(cb, list):
            errs.append(f"{name}: claimed_by 须为 list（无人认领写 []）")
        elif cb:
            claimed.add(name)
        # 内嵌的 zcheck 是权威产物的副本——副本漂了比没有更危险
        zc = row.get("zcheck")
        if isinstance(zc, dict) and zcheck_slices and name in zcheck_slices:
            src = zcheck_slices[name]
            if zc.get("verdict") and zc["verdict"] != src.get("verdict"):
                errs.append(f"{name}: slice_map 内嵌 zcheck.verdict={zc['verdict']!r} 与 "
                            f"slice_zcheck.json 的 {src.get('verdict')!r} 不符——副本已漂")
    unc = _uncovered_names(obj)
    dup = sorted(set(unc) & claimed)
    if dup:
        errs.append(f"这些切片同时被假设认领又列进 uncovered，二选一：{dup}")
    if real_slices is not None:
        missing = sorted(set(real_slices) - seen - set(unc))
        if missing:
            errs.append(f"这些 real 切片既没进 slice_map 也没进 uncovered：{missing}——"
                        "认领核对的硬规则是每个 real 切片三选一（被假设认领 / 标注为已认领"
                        "机制的同源表现 / 进 uncovered），漏登记不等于无人认领")
    return errs


def validate_ledger(obj, real_slices=None, zcheck_slices=None):
    errs = []
    if not isinstance(obj, dict) or "hypotheses" not in obj:
        return ["顶层缺 hypotheses 键或非法对象"]
    errs += validate_slice_map(obj, real_slices, zcheck_slices)
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
                    # 空 list / 空 dict 是合法取值（如无守护切片），只有键不在或值为 null 才算缺
                    if k not in fix or fix[k] is None:
                        errs.append(f"{hid}: fix 缺 {k}")
                if fix.get("config_diff") is not None and not isinstance(fix["config_diff"], dict):
                    errs.append(f"{hid}: fix.config_diff 须为 dict（键=knob 名）")
                if fix.get("guard_slices") is not None and not isinstance(fix["guard_slices"], list):
                    errs.append(f"{hid}: fix.guard_slices 须为 list")
            if h.get("status") == "confirmed" and not h.get("receipt"):
                errs.append(f"{hid}: improvement 假设升 confirmed 必须带 receipt（receipts/E*.json 路径）")
        if h.get("status") == "untested" and not h.get("untested_reason"):
            errs.append(f"{hid}: untested 必须带 untested_reason（crash/timeout 与一句原因）")
        # 解释环第二轮起，账本是跨轮累积的——不标轮次就分不清哪条是这轮提的，
        # 「post-hoc 假设必须经新干预才能升 confirmed」这条规则也就无从执行。
        rnd = h.get("round")
        if rnd is not None and not (isinstance(rnd, int) and not isinstance(rnd, bool)
                                    and rnd >= 1):
            errs.append(f"{hid}: round 须为 ≥1 的整数，实际 {rnd!r}")
    return errs

def hypotheses_in_round(obj, rnd):
    """本轮登记了哪几条。没有 round 字段的按第 1 轮算（第二轮起由 new_round.py 补齐）。"""
    return [h.get("id") for h in (obj.get("hypotheses") or [])
            if isinstance(h, dict) and int(h.get("round") or 1) == rnd]


def write_round_receipt(obj, ledger_path, rnd, out_dir):
    """账本合法 + 本轮有假设 → 盖一张按轮的章。解释环第二轮起，阶段闸靠它判
    「这一轮的假设登记完了没有」——账本是跨轮累积的一个文件，它的存在本身
    说明不了当前这一轮做过什么。→ (receipt 路径, 本轮假设 id 列表)。"""
    ids = hypotheses_in_round(obj, rnd)
    if not ids:
        return None, ids
    os.makedirs(out_dir, exist_ok=True)
    path = os.path.join(out_dir, f"ledger_round_{rnd}.json")
    with open(ledger_path, "rb") as f:
        sha = hashlib.sha256(f.read()).hexdigest()
    with open(path, "w", encoding="utf-8") as f:
        json.dump({"round": rnd, "hypotheses_this_round": ids,
                   "n_hypotheses_total": len(obj.get("hypotheses") or []),
                   "ledger_sha256": sha}, f, ensure_ascii=False, indent=2)
    return path, ids


def load_zcheck(path):
    """→ ({real 切片名}, {切片名: 原始记录})；文件不在返回 (None, None)。"""
    if not path or not os.path.exists(path):
        return None, None
    slices = (json.load(open(path, encoding="utf-8")) or {}).get("slices") or {}
    real = {k for k, v in slices.items()
            if isinstance(v, dict) and v.get("verdict") == "real"}
    return real, slices


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("ledger")
    ap.add_argument("--zcheck", default="slice_zcheck.json",
                    help="切片版图产物；存在则做认领核对，不存在则跳过该项")
    ap.add_argument("--no-zcheck", action="store_true", help="显式跳过认领核对")
    ap.add_argument("--round", type=int, default=None,
                    help="本轮轮次；缺省读 diagnose_state.json 的 round（没有则 1）")
    ap.add_argument("--receipt-dir", default="gate_reports",
                    help="按轮 receipt 的落盘目录；空字符串=不盖章")
    a = ap.parse_args(argv)
    obj = json.load(open(a.ledger, encoding="utf-8"))
    real, slices = (None, None) if a.no_zcheck else load_zcheck(a.zcheck)
    errs = validate_ledger(obj, real, slices)
    if errs:
        print("\n".join("✗ " + e for e in errs)); sys.exit(1)
    rnd = a.round
    if rnd is None:
        st = json.load(open("diagnose_state.json", encoding="utf-8")) \
            if os.path.exists("diagnose_state.json") else {}
        rnd = int((st or {}).get("round") or 1)
    if a.receipt_dir:
        rp, ids = write_round_receipt(obj, a.ledger, rnd, a.receipt_dir)
        if rp is None:
            print(f"✗ 第 {rnd} 轮还没登记任何假设——账本是跨轮累积的，"
                  f"本轮的新假设要带 \"round\": {rnd}（上一轮的条目由 new_round.py 标好了，"
                  "别改它们，也别把已经否掉的再提一遍）")
            sys.exit(1)
        print(f"  第 {rnd} 轮登记 {len(ids)} 条：{'、'.join(map(str, ids))} → {rp}")
    if real is not None:
        scope = f"（含认领核对：{len(real)} 个 real 切片全部已登记）"
    elif a.no_zcheck:
        scope = "（--no-zcheck：按要求跳过认领核对）"
    else:
        scope = f"（{a.zcheck} 不在，跳过认领核对——切片版图产在别处的剧本属正常）"
    print(f"✓ 账本合法{scope}");
if __name__ == "__main__":
    main()
