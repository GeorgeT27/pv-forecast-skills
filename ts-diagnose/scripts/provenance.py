#!/usr/bin/env python3
"""归因闸（硬不变量二的另一半）：结论必须可归因。

每次诊断出结论时生成 provenance 块——生成代码 hash + 输入数据 hash + 金标准自检
结果（gate_reports/ 汇总）。两次运行结论不同时，看它就能判定：
  code combined 变了 → 生成不稳定（代码问题）；data combined 变了 → 真实变化。

用法（在工作目录下，写 CONCLUSION.md 之前）：
  python3 <ENGINE>/scripts/provenance.py \
      --code analysis_scripts/*.py --data <本次消费的输入文件...> --out provenance.json
落盘 provenance.json 并打印可直接粘进 CONCLUSION.md 末尾的 markdown 块。
若某脚本在过闸之后又被改过（当前 sha ≠ 闸报告 sha）→ 标 stale 并以退出码 1 提醒重闸。
"""
from __future__ import annotations

import argparse
import glob
import hashlib
import json
import os
import sys


def sha256_of(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for blk in iter(lambda: f.read(65536), b""):
            h.update(blk)
    return h.hexdigest()


def hash_group(paths):
    files = {p: sha256_of(p) for p in sorted(paths)}
    combined = hashlib.sha256(
        "\n".join(f"{p}:{h}" for p, h in files.items()).encode()).hexdigest()
    return {"files": files, "combined": combined}


def gate_summary(code_files):
    """gate_reports/ 汇总 + 陈旧检测（脚本过闸后又被改 → stale）。"""
    cur = {os.path.basename(p): sha256_of(p) for p in code_files}
    out = {}
    for rp in sorted(glob.glob(os.path.join("gate_reports", "*.json"))):
        try:
            rep = json.load(open(rp, encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        name = os.path.basename(rep.get("script", rp))
        out[name] = {"passed": bool(rep.get("passed")),
                     "playbook": rep.get("playbook"), "stage": rep.get("stage"),
                     "script_sha256": rep.get("script_sha256"),
                     "stale": cur.get(name) is not None
                     and cur.get(name) != rep.get("script_sha256")}
    return out


def main():
    ap = argparse.ArgumentParser(description="ts-diagnose 归因闸")
    ap.add_argument("--code", nargs="+", required=True, help="生成的分析脚本（可 glob）")
    ap.add_argument("--data", nargs="+", required=True, help="本次消费的输入数据文件")
    ap.add_argument("--serves", nargs="*", default=[],
                    help="脚本挂回假设/段：<脚本名>=<episode_id>[@<segment_id>]，"
                         "如 eval_H1.py=H1@07-architecture-attribution-stage-3；"
                         "脚本名须在 --code 展开结果里，写错当场报错")
    ap.add_argument("--out", default="provenance.json")
    args = ap.parse_args()

    code_files = sorted({p for pat in args.code for p in (glob.glob(pat) or [pat])})
    data_files = sorted({p for pat in args.data for p in (glob.glob(pat) or [pat])})
    missing = [p for p in code_files + data_files if not os.path.exists(p)]
    if missing:
        raise SystemExit(f"文件不存在：{missing}")

    code_names = {os.path.basename(p) for p in code_files}
    serves = {}
    for item in args.serves:
        name, _, target = item.partition("=")
        if not target or name not in code_names:
            raise SystemExit(f"--serves 无效或脚本不在 --code 里：{item!r}")
        episode, _, segment = target.partition("@")
        serves[name] = {"episode_id": episode, "segment_id": segment or None}

    prov = {"code": hash_group(code_files), "data": hash_group(data_files),
            "golden_selfcheck": gate_summary(code_files)}
    if serves:
        prov["code"]["serves"] = serves  # 逐脚本挂回 episode/segment，孤儿脚本清零
    gates = prov["golden_selfcheck"]
    prov["all_gates_passed"] = bool(gates) and all(
        g["passed"] and not g["stale"] for g in gates.values())
    with open(args.out, "w", encoding="utf-8") as f:
        json.dump(prov, f, ensure_ascii=False, indent=2)

    stale = [n for n, g in gates.items() if g["stale"]]
    print("以下 provenance 块粘贴到 CONCLUSION.md 末尾：\n")
    print("## Provenance（结论可归因块）\n")
    print(f"- 生成代码 hash：`{prov['code']['combined'][:16]}`（{len(code_files)} 个脚本，逐文件见 provenance.json）")
    print(f"- 输入数据 hash：`{prov['data']['combined'][:16]}`（{len(data_files)} 个文件）")
    if gates:
        oks = sum(g["passed"] and not g["stale"] for g in gates.values())
        print(f"- 金标准自检：{oks}/{len(gates)} 过闸"
              + (f"，⚠ 过闸后被改动（需重闸）：{stale}" if stale else ""))
    else:
        print("- 金标准自检：无闸报告（本 playbook 无 golden 覆盖阶段，或漏跑 gen_gate）")
    print("- 归因规则：两次运行结论不同 → 代码 hash 变 = 生成不稳定；数据 hash 变 = 真实变化。\n")
    if stale:
        print(f"⛔ {stale} 在过闸后被改过——先重跑 gen_gate 再出结论。")
        sys.exit(1)


if __name__ == "__main__":
    main()
