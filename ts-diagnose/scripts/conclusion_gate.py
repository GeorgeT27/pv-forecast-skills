#!/usr/bin/env python3
"""结论闸（三道闸之三）：CONCLUSION.md 交付前的机械校验。
全过 → 写 gate_reports/conclusion_gate.json（唯一合法生成方式），exit 0；
否则打印缺项 exit 1。结论阶段的 done_when 依赖该 receipt（playbook 声明）。"""
from __future__ import annotations

import glob
import hashlib
import json
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import engine_common as ec

SECTION = "## 模型结构依据"
ANCHOR_RE = re.compile(r"(?:H-?\d+|\.modelmap|file:\d+)")
CHART_REF_RE = re.compile(r"[\w./_-]+\.(?:png|svg|json)")
CAUSAL_RE = re.compile(r"(导致|因为|归因于|caused by|due to|→\s*优势|使得)")
RECEIPT_LINE_RE = re.compile(r"(confirmed|refuted|undecided).*(switch|delta).*seeds?=\d")
ABLATION_SECTION = "## 消融证据"
EVIDENCE_SECTION = "## 证据清单"
IMPROVE_SECTION = "## 改进证据"
IMPROVE_RECEIPT_RE = re.compile(r"(keep|discard|undecided).*delta.*seeds?=\d")
IMPROVE_RECEIPT_REQUIRED = ("exp_id", "delta", "noise_floor_3sigma", "seeds", "verdict",
                            "produced_by", "script_sha256")
# ablation_verdict.py --out 写的正典 receipt schema:三态判定四件 + 溯源块。
# 手搓的薄 receipt(缺 produced_by/逐字段)在此被拦——回执必须由脚本生成。
RECEIPT_REQUIRED = ("hypothesis_id", "switch", "delta", "noise_floor_3sigma",
                    "seeds", "pred_direction", "verdict",
                    "produced_by", "script_sha256")


def sha256_of(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for blk in iter(lambda: f.read(65536), b""):
            h.update(blk)
    return h.hexdigest()


def _last_entry(path):
    """receipt 文件是追加数组(重跑安全);裸 dict 是历史形态。取最新一条。"""
    doc = json.load(open(path, encoding="utf-8"))
    if isinstance(doc, list):
        return doc[-1] if doc else None
    return doc if isinstance(doc, dict) else None


def check_traceability():
    """规则 5 溯源闭环:回执→脚本→假设的链条逐环机检,断一环不放行。"""
    receipts = sorted(glob.glob("receipts/H*.json"))
    prov = None
    if os.path.exists("provenance.json"):
        try:
            prov = json.load(open("provenance.json", encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            fail("provenance.json 存在但解析失败")
    for rp in receipts:
        rec = _last_entry(rp)
        if rec is None:
            fail(f"{rp} 为空或不是合法 receipt")
        missing = [k for k in RECEIPT_REQUIRED if rec.get(k) in (None, "")]
        if missing:
            fail(f"{rp} 缺必填字段 {missing}——receipt 必须由 ablation_verdict.py "
                 "--out 生成(含溯源块),不许手搓薄回执")
        if not (isinstance(rec["seeds"], int) and rec["seeds"] >= 3):
            fail(f"{rp} seeds={rec['seeds']!r}——数值判定必须 ≥3 种子,"
                 "不足只能标 skipped_reason 走降级路径")
        script = rec["produced_by"]
        if not os.path.exists(script):
            fail(f"{rp} 的 produced_by 指向不存在的脚本:{script}")
        if sha256_of(script) != rec["script_sha256"]:
            fail(f"{rp} 的 script_sha256 与 {script} 当前内容不符——"
                 "脚本在出回执后被改过,重跑判定再出结论")
        if prov is None:
            fail(f"有 receipt({rp})但无 provenance.json——先跑 provenance.py"
                 "(带 --serves)再过闸")
        serves = (prov.get("code") or {}).get("serves") or {}
        entry = serves.get(os.path.basename(script))
        if not entry or entry.get("episode_id") != rec["hypothesis_id"]:
            fail(f"孤儿脚本:{script} 未在 provenance --serves 里挂回 "
                 f"{rec['hypothesis_id']}(现挂:{entry})")
    if os.path.exists("intervention_plan.json"):
        plan = json.load(open("intervention_plan.json", encoding="utf-8"))
        items = plan.get("interventions", plan) if isinstance(plan, dict) else plan
        for iv in items if isinstance(items, list) else []:
            if not isinstance(iv, dict) or iv.get("skipped_reason"):
                continue
            hid = iv.get("hypothesis_id")
            rp = f"receipts/{hid}.json"
            if not os.path.exists(rp):
                fail(f"干预 {hid} 无 receipt 也无 skipped_reason——"
                     "执行了就要有回执,没执行要写明原因")
            if not iv.get("script"):
                fail(f"intervention_plan 里 {hid} 的 script 为空——"
                     "收到 receipt 后须回填为其 produced_by")


def check_evidence_list(text):
    """规则 6 证据清单:结论逐条点名所站文件;盘上每张 receipt 必列(防摘樱桃)。"""
    if EVIDENCE_SECTION not in text:
        fail(f"缺「{EVIDENCE_SECTION}」节——结论必须逐条点名它站在哪些证据文件上"
             "(反引号包路径,如 `receipts/H2.json`)")
    sec = text.split(EVIDENCE_SECTION, 1)[1].split("\n## ", 1)[0]
    cited = re.findall(r"`([^`\s]+)`", sec)
    if not cited:
        fail(f"「{EVIDENCE_SECTION}」节没有任何反引号包的文件路径")
    dead = [p for p in cited if not os.path.exists(p)]
    if dead:
        fail(f"证据清单引用了不存在的文件:{dead}")
    must = sorted(glob.glob("receipts/H*.json")) \
        + [p for p in ("verdict_summary.json",) if os.path.exists(p)]
    unlisted = [p for p in must if p not in cited]
    if unlisted:
        fail(f"证据清单漏列:{unlisted}——盘上每张假设 receipt(含被否证的)"
             "与 verdict_summary 都必须列出,不许只列支持结论的")


def check_improve(text):
    """规则 7 改进环:「## 改进证据」节 + 每张 E receipt 溯源 + 封存终评被引用 + 证据清单列全。"""
    if IMPROVE_SECTION not in text:
        fail(f"缺「{IMPROVE_SECTION}」节——改进结论必须贴 keep/discard/undecided 的 receipt 行")
    sec = text.split(IMPROVE_SECTION, 1)[1].split("\n## ", 1)[0]
    if not IMPROVE_RECEIPT_RE.search(sec):
        fail(f"「{IMPROVE_SECTION}」节无 receipt 行（须含 keep/discard/undecided + delta + seeds=N）")
    receipts = sorted(glob.glob("receipts/E*.json"))
    for rp in receipts:
        rec = _last_entry(rp)
        if rec is None:
            fail(f"{rp} 为空或不是合法 receipt")
        missing = [k for k in IMPROVE_RECEIPT_REQUIRED if rec.get(k) in (None, "")]
        if missing:
            fail(f"{rp} 缺必填字段 {missing}——receipt 必须由 improve_verdict.py --out 生成")
        if not (isinstance(rec["seeds"], int) and rec["seeds"] >= 3):
            fail(f"{rp} seeds={rec['seeds']!r}——改进判定必须 ≥3 种子")
        if not os.path.exists(rec["produced_by"]):
            fail(f"{rp} 的 produced_by 指向不存在的脚本:{rec['produced_by']}")
        if sha256_of(rec["produced_by"]) != rec["script_sha256"]:
            fail(f"{rp} 的 script_sha256 与 {rec['produced_by']} 当前内容不符——适配器在出回执后被改过")
    if not os.path.exists("final_test.json"):
        fail("无 final_test.json——写结论前先跑 experiment_log.py finalize（封存测试集只评一次）")
    if "final_test.json" not in text:
        fail("结论未引用 final_test.json——封存测试集的终评必须写进结论")
    if EVIDENCE_SECTION not in text:
        fail(f"缺「{EVIDENCE_SECTION}」节")
    esec = text.split(EVIDENCE_SECTION, 1)[1].split("\n## ", 1)[0]
    cited = re.findall(r"`([^`\s]+)`", esec)
    must = receipts + [p for p in ("experiment_log.jsonl", "champion.json", "final_test.json") if os.path.exists(p)]
    unlisted = [p for p in must if p not in cited]
    if unlisted:
        fail(f"证据清单漏列:{unlisted}——每张 E receipt(含被弃的)、日志、冠军、终评都必须列出")


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

    # 规则 4：架构/组件因果表述必须附消融 receipt
    # 仅对声明 produces_ablation_receipts: true 的 playbook 生效（architecture-attribution）；
    # 其余 6 个非 pilot playbook（robustness/subset-influence/training-sufficiency/
    # result-eval/feature-importance/deployment-drift）用各自方法（置换/反事实/留一法）
    # 验证因果表述，不产消融 receipt——不受本规则约束（零破坏契约）。
    if fm.get("produces_ablation_receipts") and CAUSAL_RE.search(sec):
        abl = text.split(ABLATION_SECTION, 1)[1] if ABLATION_SECTION in text else ""
        if not RECEIPT_LINE_RE.search(abl):
            fail("结论含架构因果表述但「## 消融证据」节无对应 receipt"
                 "（须含 confirmed/refuted/undecided + switch/delta + seeds=N）——"
                 "降级为「未验证假设」或补 receipt")

    # 规则 5+6：溯源闭环 + 证据清单。同规则 4 的作用域契约：只对声明
    # produces_ablation_receipts 的 playbook 生效，6 个非 pilot playbook 零破坏。
    if fm.get("produces_ablation_receipts"):
        check_traceability()
        check_evidence_list(text)

    # 规则 7：改进环（只对声明 produces_experiment_log: true 的 playbook 生效——model-improve）
    if fm.get("produces_experiment_log"):
        check_improve(text)

    os.makedirs("gate_reports", exist_ok=True)
    ec.dump_json({"passed": True,
                  "conclusion_sha256": hashlib.sha256(text.encode()).hexdigest()},
                 os.path.join("gate_reports", "conclusion_gate.json"))
    print("✓ 结论闸通过，receipt 已写 gate_reports/conclusion_gate.json")


if __name__ == "__main__":
    main()
