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
    """选中 playbook 的 upstream 产物 id 并集（sorted unique）。"""
    prods = set()
    for pid in playbook_ids:
        fm = ec.load_frontmatter(ec.find_playbook(pid))
        for u in fm.get("upstream") or []:
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
    """五阶段推断（全部从磁盘 + batch_config 派生）。"""
    cfg = ec.read_json(os.path.join(workdir, BATCH_CONFIG)) or {}
    for p in producers:
        if ec.product_status(cfg, p).get("status") not in ("built", "linked"):
            return "A"
    if not cfg.get("answers"):
        return "B"
    statuses = [d["status"] for d in dispatch_list(workdir, playbook_ids)]
    if all(s == "done" for s in statuses):
        return "E"
    if any(s in ("pending", "running", "failed") for s in statuses):
        return "C"
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
