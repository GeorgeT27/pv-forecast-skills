"""改进环用的两个引擎加法：done_when.artifacts 的 {round} 占位 + check-DSL 的 json: 前缀。"""
import os
import subprocess
import sys

import pytest

SCRIPTS_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ORIENT = os.path.join(SCRIPTS_DIR, "orient.py")
sys.path.insert(0, SCRIPTS_DIR)
import engine_common as ec  # noqa: E402

PB = """---
id: loop-demo
name: 循环演示
goal: "测试 {round} 占位与 json: DSL"
materials:
  required: []
stages:
  - id: 0
    name: 基线
    done_when: {artifacts: ['champion.json']}
  - id: 1
    name: 候选
    prereqs:
      - {desc: 基线已定, check: 'stage:0'}
    done_when: {artifacts: ['rounds/round_{round}/candidates.json']}
  - id: 2
    name: 结论
    prereqs:
      - {desc: 已收敛, check: 'json:champion.json:converged'}
    done_when: {artifacts: ['CONCLUSION.md', 'gate_reports/conclusion_gate.json']}
---
正文占位。
"""


@pytest.fixture
def wd(tmp_path, monkeypatch):
    pb = tmp_path / "pb" / "playbook.md"
    pb.parent.mkdir()
    pb.write_text(PB, encoding="utf-8")
    ec.dump_json({"playbook": str(pb), "materials": {}}, str(tmp_path / "diagnose_config.json"))
    monkeypatch.chdir(tmp_path)
    return tmp_path


def _ctx(state=None):
    fm = ec.load_frontmatter(ec.load_config()["playbook"])
    return fm, {"cfg": ec.load_config(), "fm": fm, "state": state or {}}


def test_expand_round_default_and_state():
    assert ec.expand_round("rounds/round_{round}/x.json", {"state": {}}) == "rounds/round_1/x.json"
    assert ec.expand_round("rounds/round_{round}/x.json", {"state": {"round": 3}}) == "rounds/round_3/x.json"
    assert ec.expand_round("plain.json", {"state": {"round": 3}}) == "plain.json"


def test_stage_done_uses_round_from_state(wd):
    (wd / "rounds" / "round_1").mkdir(parents=True)
    (wd / "rounds" / "round_1" / "candidates.json").write_text("{}", encoding="utf-8")
    fm, ctx1 = _ctx({"round": 1})
    _, ctx2 = _ctx({"round": 2})
    st1 = ec._stage_by_id(fm, 1)
    assert ec.stage_done(st1, ctx1) is True
    assert ec.stage_done(st1, ctx2) is False


def test_json_dsl_missing_falsy_truthy_and_malformed(wd):
    fm, ctx = _ctx({"round": 1})
    assert ec.check("json:champion.json:converged", ctx) is False          # 文件不存在
    ec.dump_json({"converged": False, "budget": {"used": 3}}, "champion.json")
    assert ec.check("json:champion.json:converged", ctx) is False          # 值为假
    assert ec.check("json:champion.json:budget.used", ctx) is True         # 嵌套点路径
    ec.dump_json({"converged": True}, "champion.json")
    assert ec.check("json:champion.json:converged", ctx) is True
    assert ec.check("not json:champion.json:converged", ctx) is False
    with pytest.raises(ValueError):
        ec.check("json:champion.json", ctx)                                # 缺点路径


def test_current_stage_reenters_after_round_bump_and_gate_opens_on_converged(wd):
    ec.dump_json({"converged": False}, "champion.json")
    (wd / "rounds" / "round_1").mkdir(parents=True)
    (wd / "rounds" / "round_1" / "candidates.json").write_text("{}", encoding="utf-8")
    fm, ctx = _ctx({"round": 1})
    assert ec.current_stage(fm, ctx)["id"] == 2
    assert ec.prereqs_ok(ec.prereqs_of(ec._stage_by_id(fm, 2), ctx)) is False
    _, ctx_r2 = _ctx({"round": 2})
    assert ec.current_stage(fm, ctx_r2)["id"] == 1                       # 新一轮回到候选阶段
    ec.dump_json({"converged": True}, "champion.json")
    assert ec.prereqs_ok(ec.prereqs_of(ec._stage_by_id(fm, 2), ctx)) is True


def test_orient_preserves_round_and_prints_it(wd):
    ec.dump_json({"converged": False}, "champion.json")
    ec.dump_json({"round": 2, "manual_done": []}, "diagnose_state.json")
    r = subprocess.run([sys.executable, ORIENT], cwd=str(wd), capture_output=True, text=True, timeout=60)
    assert r.returncode == 0, r.stderr
    assert "第 2 轮" in r.stdout
    assert (ec.read_json("diagnose_state.json") or {}).get("round") == 2
