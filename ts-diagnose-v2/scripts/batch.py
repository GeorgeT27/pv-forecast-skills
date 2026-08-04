"""Layer -1 批量编排计划器：给定选中的 level-2 playbook，从 frontmatter 确定性算出
生产者并集/问题并集/派发清单，并从磁盘重扫派生 status/phase。只计划与汇聚，不派发
subagent、不跑生产者（那是主 agent 的事）。与 orient.py（单 playbook 求值器）职责不重叠。"""
import argparse
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import engine_common as ec  # noqa: E402

BATCH_CONFIG = "batch_config.json"
BATCH_PLAN = "batch_plan.json"
BATCH_STATE = "batch_state.json"


def phenomena_name(pid):
    return f"phenomena_{pid}.json"


def producer_union(playbook_ids):
    """选中 playbook 的 upstream 产物 id 并集（sorted unique）——只算 required:true 的。
    required:false 的可选产物（model_profile、chart_sweep……）常被用户放弃/链接，
    若也并进这里，derive_phase 的 Phase A 就会永久等一个用户压根不打算建的产物；
    可选产物改由主 agent 在 Phase A 逐 playbook 三分支裁决（build/link/decline），
    见 references/batch-orchestration.md Phase A。"""
    prods = set()
    for pid in playbook_ids:
        fm = ec.load_frontmatter(ec.find_playbook(pid))
        for u in fm.get("upstream") or []:
            if u.get("required"):
                prods.add(u["product"])
    return sorted(prods)


def producer_playbooks(product_ids):
    """产物 id → 生产者 playbook id（sorted unique）。"""
    idx = ec.products_index()
    return sorted({idx[p]["playbook"] for p in product_ids if p in idx})


def question_union(playbook_ids):
    """按 qid 去重的问题并集 + 冲突表。union 每项含 owners；conflicts 记同 qid 但
    ask/options 分歧者（按 qid 去重，owners 为该 qid 的全部声明者）。"""
    seen = {}
    conflicting = set()
    for pid in playbook_ids:
        fm = ec.load_frontmatter(ec.find_playbook(pid))
        for q in fm.get("questions") or []:
            qid = q["id"]
            if qid not in seen:
                seen[qid] = {**q, "owners": [pid]}
            else:
                prev = seen[qid]
                prev["owners"].append(pid)
                if q.get("ask") != prev.get("ask") or q.get("options") != prev.get("options"):
                    conflicting.add(qid)
    union = [seen[k] for k in sorted(seen)]
    conflicts = [{"qid": k, "owners": list(seen[k]["owners"])} for k in sorted(conflicting)]
    return union, conflicts


def dispatch_list(workdir, playbook_ids):
    """每条 playbook 的派发条目 + 从磁盘派生的 status（磁盘产物永远覆盖 batch_state 标注）。"""
    state = ec.read_json(os.path.join(workdir, BATCH_STATE)) or {}
    out = []
    for pid in playbook_ids:
        pbwd = os.path.join(workdir, pid)
        concl = os.path.join(pbwd, "CONCLUSION.md")
        gate = os.path.join(pbwd, "gate_reports", "conclusion_gate.json")
        phen = os.path.join(pbwd, phenomena_name(pid))
        if os.path.exists(concl) and os.path.exists(gate):
            status = "done"
        elif os.path.exists(phen):
            status = "compute-done"
        else:
            status = state.get(pid, "pending")
            if status not in ("running", "failed"):
                status = "pending"
        out.append({"playbook": pid, "workdir": f"./{pid}",
                    "out": phenomena_name(pid), "status": status})
    return out


def derive_phase(workdir, playbook_ids, producers):
    """五阶段推断（全部从磁盘 + batch_config 派生）。Phase E 只认 BATCH_REPORT.md
    是否已写——不是 all-playbooks-done：用户常只深挖选中的子集，或选中的 playbook
    根本没有结论阶段（如 fact-scan），这两种情况都不该让批量永久卡在 D。"""
    cfg = ec.read_json(os.path.join(workdir, BATCH_CONFIG)) or {}
    for p in producers:
        if ec.product_status(cfg, p).get("status") not in ("built", "linked"):
            return "A"
    if not cfg.get("answers"):
        return "B"
    statuses = [d["status"] for d in dispatch_list(workdir, playbook_ids)]
    if any(s in ("pending", "running", "failed") for s in statuses):
        return "C"
    if os.path.exists(os.path.join(workdir, "BATCH_REPORT.md")):
        return "E"
    return "D"


def build_plan(workdir):
    """读 batch_config.json → 组装 batch_plan.json（重扫渲染，不可手改）。"""
    cfg = ec.read_json(os.path.join(workdir, BATCH_CONFIG)) or {}
    ids = cfg.get("playbooks")
    if not ids:
        raise ValueError("batch_config.json 缺 playbooks——先跑 batch.py --select 初始化")
    producers = producer_union(ids)
    all_pbs = sorted(set(ids) | set(producer_playbooks(producers)))
    union, conflicts = question_union(all_pbs)
    plan = {
        "producer_union": producers,
        "question_union": union,
        "question_conflicts": conflicts,
        "dispatch": dispatch_list(workdir, ids),
        "phase": derive_phase(workdir, ids, producers),
    }
    ec.dump_json(plan, os.path.join(workdir, BATCH_PLAN))
    return plan


def _print_plan(plan):
    print(f"阶段 phase: {plan['phase']}")
    print(f"生产者并集 producer_union: {plan['producer_union'] or '（无）'}")
    print("派发 dispatch:")
    for d in plan["dispatch"]:
        print(f"  - {d['playbook']:24} status={d['status']:12} → {d['out']}")
    print(f"问题并集 {len(plan['question_union'])} 条"
          f"（qid: {[q['id'] for q in plan['question_union']]}）")
    if plan["question_conflicts"]:
        print(f"⚠ 问题冲突（同 qid 语义分歧，主 agent 须让用户裁决）: "
              f"{[c['qid'] for c in plan['question_conflicts']]}")
    nxt = {"A": "内联跑生产者进 _shared/，回填 batch_config.products",
           "B": "一次性合并提问，答案写 batch_config.answers",
           "C": "为每条 pending 派发 Brief-BATCH-COMPUTE 子代理（见 references/batch-orchestration.md）",
           "D": "合并呈现各 phenomena，请用户点名深挖，逐条跑结论；"
                "跑完选中结论后写 BATCH_REPORT.md 进入 E",
           "E": "批量完成（BATCH_REPORT.md 已写）"}
    print(f"下一步: {nxt.get(plan['phase'], '')}")


def main():
    ap = argparse.ArgumentParser(description="ts-diagnose Layer -1 批量编排计划器")
    ap.add_argument("--select", default=None, help="逗号分隔的 playbook id，初始化批量")
    ap.add_argument("--mark", default=None, help="pb:running|failed 标注派发瞬态")
    ap.add_argument("--workdir", default=".", help="批量工作目录")
    args = ap.parse_args()
    wd = args.workdir
    os.makedirs(wd, exist_ok=True)
    if args.select:
        ids = [s.strip() for s in args.select.split(",") if s.strip()]
        for pid in ids:
            try:
                ec.find_playbook(pid)
            except FileNotFoundError as e:
                ap.error(str(e))
        cfg = ec.read_json(os.path.join(wd, BATCH_CONFIG)) or {}
        cfg["playbooks"] = ids
        ec.dump_json(cfg, os.path.join(wd, BATCH_CONFIG))
    if args.mark:
        pid, _, mark = args.mark.partition(":")
        if mark not in ("running", "failed"):
            ap.error("--mark 只接受 <pb>:running 或 <pb>:failed")
        state = ec.read_json(os.path.join(wd, BATCH_STATE)) or {}
        state[pid] = mark
        ec.dump_json(state, os.path.join(wd, BATCH_STATE))
    try:
        _print_plan(build_plan(wd))
    except ValueError as e:
        ap.error(str(e))


if __name__ == "__main__":
    main()
