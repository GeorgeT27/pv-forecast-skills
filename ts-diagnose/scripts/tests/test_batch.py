"""batch.py：Layer -1 批量计划器测试。全部在 tmp 沙箱 playbooks 目录里跑
（monkeypatch ec.PLAYBOOKS_DIR），不依赖真实 playbook 内容。"""
import os
import sys

import pytest

SCRIPTS_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, SCRIPTS_DIR)
import engine_common as ec  # noqa: E402
import batch  # noqa: E402

PRODUCER = """\
---
id: setup-prod
name: 生产者
goal: 产 setup
produces:
  id: setup
  manifest: setup_manifest.json
  marker_files: [predictions.csv]
stages:
  - id: 0
    name: 做事
    done_when: {artifacts: ["predictions.csv"]}
questions:
  - id: freq
    stage: 0
    ask: 步长?
    why: schema
    default: null
---
正文
"""

def _consumer(pid, qid):
    return f"""\
---
id: {pid}
name: 消费者{pid}
goal: 消费 setup
upstream:
  - product: setup
    required: true
stages:
  - id: 0
    name: 计算
    done_when: {{artifacts: ["m.json"]}}
    subagent_ok: true
  - id: 1
    name: 事实提取
    done_when: {{artifacts: ["{batch.phenomena_name(pid)}"]}}
    pause_after: true
    subagent_ok: true
questions:
  - id: {qid}
    stage: 0
    ask: 问 {qid}?
    why: w
    default: null
---
正文
"""

def _write_pb(root, pid, text):
    d = root / pid
    d.mkdir(parents=True, exist_ok=True)
    (d / "playbook.md").write_text(text, encoding="utf-8")
    return str(d / "playbook.md")

@pytest.fixture
def pbdir(tmp_path, monkeypatch):
    d = tmp_path / "playbooks"
    _write_pb(d, "setup-prod", PRODUCER)
    _write_pb(d, "pb-x", _consumer("pb-x", "口径"))
    _write_pb(d, "pb-y", _consumer("pb-y", "阈值"))
    monkeypatch.setattr(ec, "PLAYBOOKS_DIR", str(d))
    monkeypatch.chdir(tmp_path)
    return d

def test_producer_union_dedups_upstream(pbdir):
    assert batch.producer_union(["pb-x", "pb-y"]) == ["setup"]

def test_phenomena_name(pbdir):
    assert batch.phenomena_name("pb-x") == "phenomena_pb-x.json"

def test_question_union_dedups_and_tracks_owners(pbdir):
    # 两个消费者各带不同问题；再加一个也问"口径"的消费者，验证 owners 合并
    _write_pb(pbdir, "pb-z", _consumer("pb-z", "口径"))
    union, conflicts = batch.question_union(["pb-x", "pb-y", "pb-z"])
    by_qid = {q["id"]: q for q in union}
    assert set(by_qid) == {"口径", "阈值"}
    assert sorted(by_qid["口径"]["owners"]) == ["pb-x", "pb-z"]
    assert by_qid["阈值"]["owners"] == ["pb-y"]
    assert conflicts == []

def test_question_union_flags_conflict(pbdir):
    # 两个 playbook 用同一 qid 但 ask 文案不同 → 冲突
    _write_pb(pbdir, "pb-z", _consumer("pb-z", "口径").replace("问 口径?", "另一种问法?"))
    union, conflicts = batch.question_union(["pb-x", "pb-z"])
    assert [c["qid"] for c in conflicts] == ["口径"]
    assert sorted(conflicts[0]["owners"]) == ["pb-x", "pb-z"]

def test_producer_playbooks_maps_id_to_producer(pbdir):
    assert batch.producer_playbooks(["setup"]) == ["setup-prod"]
