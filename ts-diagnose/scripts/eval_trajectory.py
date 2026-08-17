"""评测模式轨迹埋点(rollout v2)。

仅当环境变量 SKILL_EVOLVE_TRAJECTORY_AGENT 指向日志路径时启用;日常使用零行为改变。
由 orient._write_state_progress 在状态落盘后调用,对比旧/新 diagnose_state,追加事件:
route / blocked / phase_enter / phase_exit / phase_skip / workflow_complete。
自身 I/O 错误只记 stderr,绝不影响 orient 的正常诊断;不写 diagnose_state/PROGRESS。
"""
from __future__ import annotations

import datetime as _dt
import json
import os
import sys

ENV_VAR = "SKILL_EVOLVE_TRAJECTORY_AGENT"
SCHEMA_VERSION = 2


def _event(type_, playbook, **kw):
    ev = {"schema_version": SCHEMA_VERSION,
          "timestamp": _dt.datetime.now().astimezone().isoformat(timespec="seconds"),
          "source": "orient", "type": type_, "playbook": playbook,
          "phase": kw.pop("phase", ""), "summary": kw.pop("summary", ""),
          "artifact_refs": kw.pop("artifact_refs", [])}
    ev.update(kw)
    return ev


def transitions(old_state, new_state) -> list[dict]:
    """纯函数:从旧/新状态推导事件列表(可单测,不碰文件系统)。"""
    events = []
    pb = new_state.get("playbook", "")
    old_pb = (old_state or {}).get("playbook")
    if old_pb != pb:
        events.append(_event("route", pb, summary=f"绑定 playbook {pb}"))
    new_cur = new_state.get("current_stage")
    if new_cur == "intake-blocked":
        events.append(_event("blocked", pb, summary="入口材料盘点未完成"))
        return events
    old_stages = (old_state or {}).get("stages") or {}
    for sid, st in (new_state.get("stages") or {}).items():
        old = old_stages.get(sid, "todo")
        if old != "done" and st == "done":
            events.append(_event("phase_exit", pb, phase=f"stage-{sid}"))
        elif old != "skipped" and st == "skipped":
            events.append(_event("phase_skip", pb, phase=f"stage-{sid}"))
    old_cur = (old_state or {}).get("current_stage")
    if new_cur == "done":
        if old_cur != "done":
            events.append(_event("workflow_complete", pb, summary="全部阶段完成"))
    elif new_cur is not None and new_cur != old_cur:
        events.append(_event("phase_enter", pb, phase=f"stage-{new_cur}"))
    return events


def maybe_emit(old_state, new_state) -> None:
    """入口:env 未设置时是无操作。追加失败只记 stderr。"""
    log_path = os.environ.get(ENV_VAR)
    if not log_path:
        return
    try:
        events = transitions(old_state, new_state)
        if not events:
            return
        with open(log_path, "a", encoding="utf-8") as f:
            for ev in events:
                f.write(json.dumps(ev, ensure_ascii=False) + "\n")
    except OSError as e:
        print(f"[eval_trajectory] 事件追加失败(不影响诊断):{e}", file=sys.stderr)
