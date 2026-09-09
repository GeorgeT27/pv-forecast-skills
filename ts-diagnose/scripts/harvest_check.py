#!/usr/bin/env python3
"""解释环收口：一轮干预验证结束后，机检这一轮到底解释了多少现象。

输入 Stage 0 的 `slice_zcheck.json`（真实切片全集）、Stage 1 的 `hypothesis_ledger.json`
（谁认领了哪个切片）、Stage 3 的 `verdict_summary.json`（哪些切片被干预推动过），
算出未解释的 real 切片清单与残留维度分布，追加写 `harvest.json`（数组，重跑安全）。

不自动开下一轮：本脚本只把「解释了多少、还剩什么」摆成事实，下一步三选一交用户定。"""
from __future__ import annotations

import argparse
import datetime as _dt
import hashlib
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import engine_common as ec  # noqa: E402

OUT_PATH = "harvest.json"
UNEXPLAINED_KEY = "unexplained_real_slices"


def _dimension(name):
    """维度名一律取切片名的冒号前缀。账本 slice_map 的 dimension 字段是自由填写的，
    实测同一维度会被标成不同名字（month:2020-12 标 time、month:2020-10 标 month），
    拿它分组会把同一批残留拆成两堆——这里只认命名约定。"""
    return name.split(":", 1)[0] if ":" in name else "total"


def real_slices(zcheck):
    """→ {切片名: {"z":float,"mean_diff":float}}，只收 verdict=="real"。"""
    out = {}
    for name, s in ((zcheck or {}).get("slices") or {}).items():
        if isinstance(s, dict) and s.get("verdict") == "real":
            out[name] = {"z": s.get("z"), "mean_diff": s.get("mean_diff")}
    return out


def claim_map(ledger):
    """→ {切片名: claim_state}，三态：
    `claimed` 有假设认领 · `uncovered` 登记过但明确无人认领 · 不在表里 = 根本没登记。
    「登记为无人认领」和「压根没登记」是两回事：前者是 Stage 1 认领核对走完的合法出口，
    后者是那道硬规则没走完。账本缺失时空表（全部按未登记算）。"""
    out = {}
    for row in ((ledger or {}).get("slice_map") or []):
        if isinstance(row, dict) and row.get("slice"):
            out[row["slice"]] = {"claimed_by": list(row.get("claimed_by") or []),
                                 "state": "claimed" if row.get("claimed_by") else "uncovered"}
    for row in ((ledger or {}).get("uncovered") or []):
        name = row.get("slice") if isinstance(row, dict) else row
        if name and name not in out:
            out[str(name)] = {"claimed_by": [], "state": "uncovered"}
    return out


def moved_slices(verdicts):
    """被干预推动过（超该切片噪声底）的切片名集合 —— 取自 slice_recompute 的
    beyond_noise_floor 三元组首项。"""
    out = set()
    for rec in ((verdicts or {}).get("slice_recompute") or {}).values():
        if not isinstance(rec, dict):
            continue
        for item in rec.get("beyond_noise_floor") or []:
            if isinstance(item, (list, tuple)) and item:
                out.add(str(item[0]))
            elif isinstance(item, dict) and item.get("slice"):
                out.add(str(item["slice"]))
    return out


def _counts(verdicts):
    """三态计数：显式字段优先，缺字段时从 interventions 现数。"""
    ivs = [i for i in ((verdicts or {}).get("interventions") or [])
           if isinstance(i, dict)]
    counted = {}
    for v in ("confirmed", "refuted", "undecided", "skipped"):
        counted[v] = sum(1 for i in ivs if i.get("verdict") == v)
    out = {}
    for v, n in counted.items():
        declared = (verdicts or {}).get(f"n_{v}")
        out[v] = n if declared is None else int(declared)
    return out, counted


def compute_harvest(zcheck, ledger, verdicts, round_no=1):
    real = real_slices(zcheck)
    claims = claim_map(ledger)
    moved = moved_slices(verdicts) & set(real)
    counts, _ = _counts(verdicts)
    unexplained = []
    residual = {}
    for name in sorted(set(real) - moved):
        c = claims.get(name) or {"claimed_by": [], "state": "unregistered"}
        dim = _dimension(name)
        residual[dim] = residual.get(dim, 0) + 1
        unexplained.append({"slice": name, "dimension": dim,
                            "z": real[name]["z"], "mean_diff": real[name]["mean_diff"],
                            "claimed_by": c["claimed_by"],
                            "claim_state": c["state"],
                            "ever_claimed": bool(c["claimed_by"])})
    if not real:
        harvest = "no-real-slices"
    elif not unexplained:
        harvest = "full"
    elif counts["confirmed"] == 0 and not moved:
        harvest = "none"
    else:
        harvest = "partial"
    return {"round": round_no,
            "harvest": harvest,
            "n_real_slices": len(real),
            "n_moved": len(moved),
            "n_confirmed": counts["confirmed"], "n_refuted": counts["refuted"],
            "n_undecided": counts["undecided"], "n_skipped": counts["skipped"],
            "moved_slices": sorted(moved),
            "unexplained": unexplained,
            "residual_by_dimension": dict(sorted(residual.items())),
            "never_claimed": [u["slice"] for u in unexplained if not u["ever_claimed"]],
            "unregistered_real_slices": sorted(
                n for n in real if (claims.get(n) or {}).get("state") is None),
            "next_round_required": bool(unexplained) or counts["confirmed"] == 0}


def validate(h, verdicts):
    """收口一致性：账本外的三条硬检查。→ 错误列表（空=通过）。"""
    errs = []
    declared = (verdicts or {}).get(UNEXPLAINED_KEY)
    computed = [u["slice"] for u in h["unexplained"]]
    if declared is None:
        errs.append(f"verdict_summary.json 缺 {UNEXPLAINED_KEY} 字段——Stage 3 硬规则要求"
                    f"未被推动的 real 切片逐条标为未解释（实算 {len(computed)} 条）")
    else:
        extra = sorted(set(map(str, declared)) - set(computed))
        missing = sorted(set(computed) - set(map(str, declared)))
        if extra or missing:
            errs.append(f"verdict_summary.{UNEXPLAINED_KEY} 与实算不符——"
                        f"多列 {extra or '无'}；漏列 {missing or '无'}")
    counts, counted = _counts(verdicts)
    for v, n in counted.items():
        d = (verdicts or {}).get(f"n_{v}")
        if d is not None and int(d) != n:
            errs.append(f"verdict_summary.n_{v}={d} 与 interventions 里 "
                        f"verdict=='{v}' 的 {n} 条不符")
    unreg = h.get("unregistered_real_slices") or []
    if unreg:
        errs.append(f"这些 real 切片在账本里既没进 slice_map 也没进 uncovered：{unreg}——"
                    "Stage 1 认领核对的硬规则是每个 real 切片必须三选一（被假设认领 / "
                    "标注为已认领机制的同源表现 / 进 uncovered），漏登记不是「无人认领」，"
                    "是那道核对没走完。补进账本再重跑收口。")
    if h["n_confirmed"] == 0 and not h["unexplained"] and h["n_real_slices"]:
        errs.append("一条 confirmed 都没有，却没有任何未解释切片——"
                    "自相矛盾：没有确认的机制就没有解释过任何现象")
    return errs


def report(h):
    """把收成摆成事实 + 三个选项。不替用户选，也不编取证角度。"""
    lines = [f"收成：{h['harvest']}（confirmed {h['n_confirmed']} 条 / "
             f"干预推动 {h['n_moved']} 个 real 切片 / 共 {h['n_real_slices']} 个）"]
    if h["unexplained"]:
        dims = "、".join(f"{k} {v}" for k, v in h["residual_by_dimension"].items())
        lines.append(f"未解释 {len(h['unexplained'])} 条，按维度：{dims}")
        for u in h["unexplained"]:
            if u["claimed_by"]:
                who = "、".join(u["claimed_by"]) + "（认领但未推动）"
            elif u.get("claim_state") == "uncovered":
                who = "账本登记为无人认领"
            else:
                who = "未登记进账本"
            lines.append(f"  - {u['slice']}  z={u['z']}  mean_diff={u['mean_diff']}  {who}")
    if h["n_confirmed"] == 0:
        lines.append("本轮 confirmed=0：没有任何机制被证实。选②收口时，CONCLUSION.md "
                     "必须含「本轮未能归因到任何组件」，结论闸机检这句。")
    lines += ["下一步三选一，向用户汇报后由用户点名，不许自己替用户选：",
              "  ① 绕回取证换角度——先对上面每个残留维度各说一个本轮没试过的取证角度，"
              "再起新一轮假设（回上游取证剧本，或 orient.py --goto 1 补账本）",
              "  ② 以未决收口——进 Stage 4 写结论，未解释清单逐条进「## 已知缺口」节（切片名连前缀原样抄）",
              "  ③ 换方向——记 PROGRESS.md 后停"]
    return "\n".join(lines)


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--zcheck", default="slice_zcheck.json")
    ap.add_argument("--ledger", default="hypothesis_ledger.json")
    ap.add_argument("--verdicts", default="verdict_summary.json")
    ap.add_argument("--out", default=OUT_PATH)
    a = ap.parse_args(argv)
    zcheck = ec.read_json(a.zcheck)
    if zcheck is None:
        print(f"✗ 收口不过：{a.zcheck} 缺失或非法——Stage 0 的切片版图是收成的分母")
        sys.exit(1)
    verdicts = ec.read_json(a.verdicts)
    if verdicts is None:
        print(f"✗ 收口不过：{a.verdicts} 缺失或非法——先完成 Stage 3 的干预汇总")
        sys.exit(1)
    ledger = ec.read_json(a.ledger)
    if ledger is None:
        print(f"✗ 收口不过：{a.ledger} 缺失或非法——没有账本就判不了哪个切片被谁认领，"
              "收成也就无从谈起（它是 Stage 1 的产物，正常路径上一定在）")
        sys.exit(1)
    # 轮次以 state.round 为准——解释环由 new_round.py 维护它（改进环由 experiment_log
    # 维护）。没有 state 时退回「第 N 次收口 = 第 N 轮」自己数。
    prev = ec.read_json(a.out)
    prev = prev if isinstance(prev, list) else []
    state = ec.read_json(ec.STATE_PATH)
    rnd = int(state.get("round") or 1) if isinstance(state, dict) else len(prev) + 1
    h = compute_harvest(zcheck, ledger, verdicts, round_no=rnd)
    errs = validate(h, verdicts)
    if errs:
        print("\n".join("✗ 收口不过：" + e for e in errs))
        sys.exit(1)
    h["verdict_summary_sha256"] = hashlib.sha256(
        open(a.verdicts, "rb").read()).hexdigest()
    h["t"] = _dt.datetime.now().strftime("%Y-%m-%dT%H:%M:%S")
    ec.dump_json(prev + [h], a.out)
    print(f"✓ 收口核对通过，已追加 {a.out}")
    print(report(h))


if __name__ == "__main__":
    main()
