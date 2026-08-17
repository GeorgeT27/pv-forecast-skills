"""eval_trajectory:状态迁移→事件映射、env 激活开关、隔离性。"""
import json
import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
import eval_trajectory as et  # noqa: E402


def _state(playbook="model-comparison", cur=0, stages=None):
    return {"playbook": playbook, "current_stage": cur,
            "stages": stages or {"0": "todo", "1": "todo", "2": "todo"}}


def _types(evs):
    return [e["type"] for e in evs]


def test_route_on_first_binding():
    evs = et.transitions(None, _state())
    assert "route" in _types(evs)
    assert all(e["playbook"] == "model-comparison" for e in evs)


def test_no_route_when_playbook_unchanged():
    assert "route" not in _types(et.transitions(_state(cur=0), _state(cur=1)))


def test_phase_exit_todo_to_done():
    old = _state(cur=0)
    new = _state(cur=1, stages={"0": "done", "1": "todo", "2": "todo"})
    evs = et.transitions(old, new)
    assert ("phase_exit", "stage-0") in [(e["type"], e["phase"]) for e in evs]
    assert ("phase_enter", "stage-1") in [(e["type"], e["phase"]) for e in evs]


def test_phase_skip_todo_to_skipped():
    old = _state(cur=1, stages={"0": "done", "1": "todo", "2": "todo"})
    new = _state(cur=1, stages={"0": "done", "1": "todo", "2": "skipped"})
    evs = et.transitions(old, new)
    assert ("phase_skip", "stage-2") in [(e["type"], e["phase"]) for e in evs]


def test_blocked_intake():
    new = {"playbook": "model-comparison", "current_stage": "intake-blocked", "stages": {}}
    evs = et.transitions(None, new)
    assert _types(evs) == ["route", "blocked"]


def test_workflow_complete():
    old = _state(cur=2, stages={"0": "done", "1": "done", "2": "todo"})
    new = _state(cur="done", stages={"0": "done", "1": "done", "2": "done"})
    evs = et.transitions(old, new)
    assert "workflow_complete" in _types(evs)
    assert "phase_enter" not in _types(evs)


def test_events_are_valid_v2_schema():
    for ev in et.transitions(None, _state()):
        for field in ("schema_version", "timestamp", "source", "type"):
            assert ev.get(field) not in (None, "")
        assert ev["source"] == "orient"


def test_maybe_emit_writes_jsonl(tmp_path, monkeypatch):
    log = tmp_path / "traj.jsonl"
    monkeypatch.setenv(et.ENV_VAR, str(log))
    et.maybe_emit(None, _state())
    lines = [json.loads(x) for x in log.read_text().splitlines()]
    assert lines and lines[0]["type"] == "route"


def test_maybe_emit_noop_without_env(tmp_path, monkeypatch):
    monkeypatch.delenv(et.ENV_VAR, raising=False)
    et.maybe_emit(None, _state())
    assert list(tmp_path.iterdir()) == []


def test_maybe_emit_swallows_io_error(monkeypatch, capsys):
    monkeypatch.setenv(et.ENV_VAR, "/nonexistent-dir/x/y/traj.jsonl")
    et.maybe_emit(None, _state())  # 不应抛
    assert "事件追加失败" in capsys.readouterr().err
