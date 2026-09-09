#!/usr/bin/env python3
"""解释环开新一轮：把上一轮的取证与判定产物归档，腾空工作目录，让阶段入口回来。

用户在收口（`harvest_check.py`）后选①「换角度再取一轮」时跑这一支。它做三件事：
1. 把本轮的取证/判定产物**移**进 `rounds/round_<N>/`（移不是删，原样保留可回查）；
2. `diagnose_state.round` +1；
3. 给账本里每条还没有 `round` 字段的假设补上它当轮的轮次。

账本本身不归档——它是累积的：新一轮必须看得见上一轮已经否掉了什么，才不会把同一条
再提一遍。receipts/ 也不归档——按假设 id 命名不会撞，且结论闸要求盘上每张 receipt 都
进证据清单（防摘樱桃），归档掉就等于把上一轮的否证藏起来了。"""
from __future__ import annotations

import argparse
import datetime as _dt
import os
import shutil
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import engine_common as ec  # noqa: E402

ROUNDS_DIR = "rounds"
MANIFEST = os.path.join(ROUNDS_DIR, "manifest.json")

# 每轮重做的东西——换个角度取证就该重来一遍的那些。
ARCHIVE = ["chart_plan.json", "INDEX.md", "charts",
           "slice_zcheck.json", "slice_metrics.csv",
           "intervention_plan.json", "verdict_summary.json"]
# 明确不归档，各有各的理由（见模块 docstring）。
KEEP = ["hypothesis_ledger.json", "receipts", "harvest.json", "runs",
        "noise_floor.json", "slice_noise_floor.json", "FINDINGS.md", "PROGRESS.md"]


def current_round(state):
    return int((state or {}).get("round") or 1)


def plan_archive(items=None, cwd="."):
    """→ 实际在盘上、需要归档的条目（保持 ARCHIVE 的顺序）。"""
    return [n for n in (items or ARCHIVE) if os.path.exists(os.path.join(cwd, n))]


def tag_ledger_rounds(ledger, rnd):
    """给没有 round 字段的假设补上当轮轮次。→ (改过的账本, 补了几条)。"""
    n = 0
    for h in (ledger.get("hypotheses") or []):
        if isinstance(h, dict) and h.get("round") is None:
            h["round"] = rnd
            n += 1
    return ledger, n


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--dry-run", action="store_true",
                    help="只打印会归档什么、轮次会变成几，不动盘")
    ap.add_argument("--note", default="", help="这一轮换的是什么角度（记进 manifest）")
    a = ap.parse_args(argv)

    state = ec.read_json(ec.STATE_PATH)
    if state is None:
        print("✗ 开不了新一轮：没有 diagnose_state.json——先跑 orient.py")
        sys.exit(1)
    rnd = current_round(state)
    nxt = rnd + 1
    dest = os.path.join(ROUNDS_DIR, f"round_{rnd}")

    harvest = ec.read_json("harvest.json")
    last = harvest[-1] if isinstance(harvest, list) and harvest else None
    if last is None:
        print("✗ 开不了新一轮：没有 harvest.json——先跑 harvest_check.py 收口。"
              "不知道这一轮解释了多少，就无从判断下一轮该换什么角度。")
        sys.exit(1)

    moving = plan_archive()
    if not moving:
        print(f"✗ 开不了新一轮：{ARCHIVE} 一个都不在盘上——这一轮还没产出任何取证或判定产物")
        sys.exit(1)
    if os.path.exists(dest) and not a.dry_run:
        print(f"✗ 开不了新一轮：{dest} 已存在——第 {rnd} 轮似乎已经归过档，"
              "先确认它的内容再决定怎么办（本脚本不覆盖已有归档）")
        sys.exit(1)

    print(f"第 {rnd} 轮 → 第 {nxt} 轮")
    print(f"  上一轮收成：{last.get('harvest')}（confirmed {last.get('n_confirmed')} / "
          f"未解释 {len(last.get('unexplained') or [])} 个 real 切片）")
    print(f"  归档到 {dest}/：{'、'.join(moving)}")
    print(f"  留在原地：{'、'.join(n for n in KEEP if os.path.exists(n))}"
          "（账本累积、receipt 防摘樱桃、收成追加）")
    if a.dry_run:
        print("  --dry-run：没动盘")
        return

    os.makedirs(dest, exist_ok=True)
    for n in moving:
        shutil.move(n, os.path.join(dest, os.path.basename(n)))

    ledger = ec.read_json("hypothesis_ledger.json")
    tagged = 0
    if isinstance(ledger, dict):
        ledger, tagged = tag_ledger_rounds(ledger, rnd)
        ec.dump_json(ledger, "hypothesis_ledger.json")

    state["round"] = nxt
    ec.dump_json(state, ec.STATE_PATH)

    prev = ec.read_json(MANIFEST)
    ec.dump_json((prev if isinstance(prev, list) else []) + [{
        "round": rnd, "archived_to": dest, "items": moving,
        "harvest": last.get("harvest"),
        "n_confirmed": last.get("n_confirmed"),
        "unexplained": [u.get("slice") for u in (last.get("unexplained") or [])],
        "note": a.note,
        "t": _dt.datetime.now().strftime("%Y-%m-%dT%H:%M:%S")}], MANIFEST)

    print(f"✓ 已归档，账本补了 {tagged} 条 round 字段，state.round={nxt}，清单写 {MANIFEST}")
    print("  下一步：重跑 orient.py——被归档的产物一没，阶段入口就回来了。"
          "新一轮的假设登记时带上 `\"round\": %d`，别把上一轮否掉的再提一遍"
          "（账本还在原地，先读它）。" % nxt)


if __name__ == "__main__":
    main()
