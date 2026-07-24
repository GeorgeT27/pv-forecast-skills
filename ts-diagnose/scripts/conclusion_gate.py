#!/usr/bin/env python3
"""结论闸（三道闸之三）：CONCLUSION.md 交付前的机械校验。
全过 → 写 gate_reports/conclusion_gate.json（唯一合法生成方式），exit 0；
否则打印缺项 exit 1。结论阶段的 done_when 依赖该 receipt（playbook 声明）。"""
from __future__ import annotations

import hashlib
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import engine_common as ec

SECTION = "## 模型结构依据"
ANCHOR_RE = re.compile(r"(?:H-?\d+|\.modelmap|file:\d+)")
CHART_REF_RE = re.compile(r"[\w./_-]+\.(?:png|svg|json)")


def fail(msg):
    print(f"✗ 结论闸不过：{msg}")
    sys.exit(1)


def main():
    cfg = ec.load_config() or {}
    if not cfg.get("playbook"):
        fail("无 diagnose_config.json 或未绑定 playbook")
    if not os.path.exists("CONCLUSION.md"):
        fail("CONCLUSION.md 不存在")
    try:
        fm = ec.load_frontmatter(ec.find_playbook(cfg["playbook"]))
    except Exception as e:
        fail(f"playbook 加载失败：{e}")
    text = open("CONCLUSION.md", encoding="utf-8").read()

    # 规则 1+2：模型结构依据节
    if SECTION not in text:
        fail(f"缺「{SECTION}」节——结论必须挂到架构事实或显式降级")
    sec = text.split(SECTION, 1)[1].split("\n## ", 1)[0]
    degraded = ("absent-confirmed" in sec and "降级" in sec)
    if not (ANCHOR_RE.search(sec) or degraded):
        fail("「模型结构依据」节既无桥接锚（H-id / .modelmap / file:行号），"
             "也无降级声明（须同时含 absent-confirmed 与 降级）")

    # 规则 3：图证据（仅 playbook 有 chart 阶段时）
    if ec.has_chart_stage(fm):
        cited = sorted(c for c in set(CHART_REF_RE.findall(text)) if c.startswith("charts/"))
        if not cited:
            fail("本 playbook 有图表阶段，但结论未引用任何 charts/ 产物——归因必须有图支撑")
        missing = [c for c in cited if not os.path.exists(c)]
        if missing:
            fail(f"结论引用了不存在的图：{missing}")

    os.makedirs("gate_reports", exist_ok=True)
    ec.dump_json({"passed": True,
                  "conclusion_sha256": hashlib.sha256(text.encode()).hexdigest()},
                 os.path.join("gate_reports", "conclusion_gate.json"))
    print("✓ 结论闸通过，receipt 已写 gate_reports/conclusion_gate.json")


if __name__ == "__main__":
    main()
