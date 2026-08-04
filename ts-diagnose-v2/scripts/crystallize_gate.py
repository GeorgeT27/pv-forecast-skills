#!/usr/bin/env python3
"""固化三关判据（硬不变量三：固化产物与专用技能同等可信）。

一个薄代理技能可固化，当且仅当同时过三关（本脚本判定，任一不过退出码非零）：
  关1 多样性：≥N 个 input_hash 互异的成功 case（N = playbook frontmatter
       crystallize_min_cases，默认 3），每个 case 注明覆盖的适用域边界；
  关2 held-out：一条**未参与开发**的留出场景记录，passed=true 且 input_hash
       不与任何 case 重合（场景库排后续轮——本轮要求记录存在且通过）；
  关3 快照自洽：每个快照脚本经 gen_gate 在其 playbook 金标准上重跑 PASS
       （golden 未覆盖的阶段列为 unchecked 警告，需 PROGRESS.md 验证记录人工确认）。

用法：
  python3 <ENGINE>/scripts/crystallize_gate.py --record crystallize_record.json \
      [--skill-dir <候选薄技能目录，快照相对路径的根>]

crystallize_record.json 由主 agent 汇总各次成功运行（schema 见 references/crystallize.md；
input_hash 取各次运行 provenance.json 的 data.combined）。
"""
from __future__ import annotations

import argparse
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import engine_common as ec  # noqa: E402
import gen_gate as gg  # noqa: E402


def gate1_diversity(record, fm):
    need = ec.crystallize_min_cases(fm)
    cases = record.get("cases") or []
    bad = [c.get("name", "?") for c in cases
           if not c.get("input_hash") or not c.get("boundary")]
    hashes = {c["input_hash"] for c in cases if c.get("input_hash")}
    errs = []
    if bad:
        errs.append(f"case 缺 input_hash 或 boundary（适用域边界说明）：{bad}")
    if len(hashes) < need:
        errs.append(f"互异 input_hash 的成功 case 只有 {len(hashes)} 个，"
                    f"需 ≥{need}（playbook crystallize_min_cases）")
    return errs


def gate2_heldout(record):
    h = record.get("heldout")
    if not h:
        return ["缺 held-out 记录（一个从未参与开发的留出场景）"]
    errs = []
    if not h.get("passed"):
        errs.append("held-out 场景未通过（passed != true）——不许固化")
    if not h.get("input_hash"):
        errs.append("held-out 缺 input_hash")
    elif h["input_hash"] in {c.get("input_hash") for c in record.get("cases") or []}:
        errs.append("held-out 的 input_hash 与某个开发 case 重合——不算留出")
    return errs


def gate3_snapshots(record, skill_dir):
    playbook = record["playbook"]
    gdir = os.path.join(ec.playbook_dir(playbook), "golden")
    manifest = ec.read_json(os.path.join(gdir, "manifest.json")) or {}
    covered = set((manifest.get("stages") or {}).keys())
    errs, unchecked = [], []
    for snap in record.get("snapshots") or []:
        path = snap["file"] if os.path.isabs(snap["file"]) \
            else os.path.join(skill_dir, snap["file"])
        if not os.path.exists(path):
            errs.append(f"快照不存在：{path}")
            continue
        st_ok, issues = gg.static_check(path)
        if not st_ok:
            errs.append(f"{snap['file']} 静态检查未过：{issues}")
            continue
        stage = str(snap.get("stage"))
        if stage not in covered:
            unchecked.append(f"{snap['file']}（stage {stage} 无 golden 覆盖）")
            continue
        ok, checks, err = gg.golden_run(path, playbook, stage)
        if not ok:
            fails = [f"{c.get('path')}:{c['op']}" for c in checks if not c["ok"]]
            errs.append(f"{snap['file']} 金标准重跑 FAIL：{err or fails}")
    return errs, unchecked


def main():
    ap = argparse.ArgumentParser(description="ts-diagnose 固化三关判据")
    ap.add_argument("--record", required=True, help="crystallize_record.json 路径")
    ap.add_argument("--skill-dir", default=None, help="候选薄技能目录（快照相对路径根）")
    args = ap.parse_args()

    record = ec.read_json(args.record)
    if not record or not record.get("playbook"):
        raise SystemExit(f"record 不可读或缺 playbook：{args.record}")
    skill_dir = args.skill_dir or os.path.dirname(os.path.abspath(args.record))
    fm = ec.load_frontmatter(ec.find_playbook(record["playbook"]))

    g1 = gate1_diversity(record, fm)
    g2 = gate2_heldout(record)
    g3, unchecked = gate3_snapshots(record, skill_dir)

    print(f"[crystallize_gate] playbook={record['playbook']}")
    for name, errs in (("关1 多样性", g1), ("关2 held-out", g2), ("关3 快照自洽", g3)):
        print(f"  {name}：{'PASS' if not errs else 'FAIL'}")
        for e in errs:
            print(f"    ✗ {e}")
    for u in unchecked:
        print(f"    ⚠ 未机判（需 PROGRESS.md 验证记录人工确认）：{u}")
    if g1 or g2 or g3:
        print("  ⛔ 三关未全过：不许写 profile.yaml / SKILL.md。")
        sys.exit(1)
    print("  ✅ 三关全过：可以固化（继续 references/crystallize.md 的交付检查）。")


if __name__ == "__main__":
    main()
