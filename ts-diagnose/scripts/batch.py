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
