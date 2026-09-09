#!/usr/bin/env python3
"""取证计划校验（图表选择门第一步的机器闸）：先写「要弄清什么 + 需要什么证据」，
再去对图池。字段纪律 = 四字段必填 / 疑问与证据不许雷同 / chartbook 来源须是真 recipe /
ad-hoc 来源须声明验证档位。--strict（开画前）另查 recipe 已填。"""
import json
import os
import sys

REQUIRED = ["question", "evidence", "recipe", "source"]
SOURCES = {"chartbook", "ad-hoc"}
# 三档验证路径（engine-core §现场写图的验证路径）：
#   reconcile-2  纯聚合类，过对账两关（行数守恒 + 抽 3 窗逐值核对）→ 可进结论
#   chartbook-fn 统计检验调 chartbook 已验证的函数                → 可进结论
#   exploratory  自写的检验未经验证                              → 只作线索，不进结论
VERIFICATIONS = {"reconcile-2", "chartbook-fn", "exploratory"}
MIN_LEN = 8  # 「分析一下」这种水货挡在门外


def _known_recipes():
    """chartbook 已有的 recipe id 集合；引擎不可用时返回 None = 跳过该项校验。"""
    try:
        sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
        import engine_common as ec
        return set(ec.available_recipes())
    except Exception:
        return None


def validate_plan(obj, strict=False, known=None):
    """→ (errs, warns)。errs 非空 = 不许开画。"""
    errs, warns = [], []
    if not isinstance(obj, dict) or "entries" not in obj:
        return ["顶层缺 entries 键或非法对象"], warns
    ent = obj["entries"]
    if not isinstance(ent, list):
        return [f"entries 须为 list，实际是 {type(ent).__name__}"], warns
    if not ent:
        return ["entries 为空——取证计划至少一条疑问；"
                "没有疑问就不该进画图阶段（engine-core §图表选择门）"], warns
    for i, e in enumerate(ent):
        tag = f"entries[{i}]"
        if not isinstance(e, dict):
            errs.append(f"{tag}: 条目须为 dict，实际是 {type(e).__name__}")
            continue
        for k in REQUIRED:
            if k not in e:
                errs.append(f"{tag}: 缺字段 {k}")
        q = str(e.get("question") or "").strip()
        ev = str(e.get("evidence") or "").strip()
        rid = str(e.get("recipe") or "").strip()
        src = e.get("source")
        if len(q) < MIN_LEN:
            errs.append(f"{tag}: question 太短（<{MIN_LEN} 字）——"
                        "写清这一步要弄清什么，不是写「分析数据」")
        if len(ev) < MIN_LEN:
            errs.append(f"{tag}: evidence 太短（<{MIN_LEN} 字）——"
                        "写清需要什么形态的证据：看什么量、按什么切、跟谁比")
        if q and ev and q == ev:
            errs.append(f"{tag}: evidence 与 question 雷同——"
                        "证据形态是「怎么看」，不是把疑问抄一遍")
        if src not in SOURCES:
            errs.append(f"{tag}: source 非法（{src!r}），只许 {sorted(SOURCES)}")
        if src == "ad-hoc":
            v = e.get("verification")
            if v not in VERIFICATIONS:
                errs.append(f"{tag}: source=ad-hoc 必须声明 verification ∈ "
                            f"{sorted(VERIFICATIONS)}（现场写的图怎么验，见 engine-core）")
            elif v == "exploratory":
                warns.append(f"{tag}: verification=exploratory —— 该图只作线索，"
                             "数字不许进 FINDINGS 的「假设」条目与 CONCLUSION")
        if strict and not rid:
            errs.append(f"{tag}: recipe 未填——开画前每条疑问都要落到一张具体的图"
                        "（chartbook recipe id，或 analysis_scripts/<name>.py）")
        if src == "chartbook" and rid and known is not None and rid not in known:
            errs.append(f"{tag}: recipe {rid!r} 不在 chartbook（source=chartbook 时"
                        f"必须是真 recipe id；现场写的图请标 source=ad-hoc）")
    return errs, warns


def main(argv=None):
    argv = list(sys.argv[1:] if argv is None else argv)
    strict = "--strict" in argv
    argv = [a for a in argv if a != "--strict"]
    path = argv[0] if argv else "chart_plan.json"
    try:
        with open(path, encoding="utf-8") as f:
            obj = json.load(f)
    except OSError:
        print(f"✗ 读不到 {path}——取证计划是画图前的阶段闸判据，先落盘")
        return 1
    except json.JSONDecodeError as ex:
        print(f"✗ {path} 不是合法 JSON：{ex}")
        return 1
    errs, warns = validate_plan(obj, strict=strict, known=_known_recipes())
    for w in warns:
        print("⚠ " + w)
    if errs:
        print("\n".join("✗ " + e for e in errs))
        return 1
    n = len(obj["entries"])
    print(f"✓ 取证计划合法（{n} 条疑问{'，已可开画' if strict else ''}）")
    return 0


if __name__ == "__main__":
    sys.exit(main())
