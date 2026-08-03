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
    ask/options 分歧者（按 qid 去重）。"""
    seen = {}
    conflict_qids = {}
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
                    conflict_qids[qid] = {"qid": qid, "owners": list(prev["owners"])}
    union = [seen[k] for k in sorted(seen)]
    conflicts = [conflict_qids[k] for k in sorted(conflict_qids)]
    return union, conflicts
