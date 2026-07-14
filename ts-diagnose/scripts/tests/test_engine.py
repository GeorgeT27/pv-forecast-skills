"""engine_common / orient 的机制层测试。

fixture 用真实的 playbooks/training-sufficiency.md（spec 要求：引擎与首个 playbook
互为验证）。所有工作目录相关的测试在 tmp_path 里跑（engine_common 的 artifact/
config 判定都是 cwd 相对）。
"""
import json
import os
import subprocess
import sys

import pytest

SCRIPTS_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, SCRIPTS_DIR)
import engine_common as ec  # noqa: E402

TS_PLAYBOOK = os.path.join(ec.PLAYBOOKS_DIR, "training-sufficiency.md")


@pytest.fixture
def fm():
    return ec.load_frontmatter(TS_PLAYBOOK)


@pytest.fixture
def workdir(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    return tmp_path


def ctx_of(fm, cfg=None, state=None):
    return {"cfg": cfg or {}, "fm": fm, "state": state or {}}


# ---------------------------------------------------------------- frontmatter
def test_load_real_playbook(fm):
    assert fm["id"] == "training-sufficiency"
    assert [s["id"] for s in fm["stages"]] == [0, 1, 2, 3, 4, 5, 6]
    assert {v["id"] for v in fm["variants"]} == {"grouped", "external"}
    assert fm["upgrade_rule"]


def test_frontmatter_validation_rejects_bad_marker(tmp_path):
    bad = tmp_path / "bad.md"
    bad.write_text("---\nid: x\nname: x\ngoal: x\nstages:\n"
                   "  - id: 0\n    name: a\n    done_when: {findings_marker: 结论}\n---\n",
                   encoding="utf-8")
    with pytest.raises(ValueError, match="保留字表"):
        ec.load_frontmatter(str(bad))


def test_frontmatter_validation_requires_done_when(tmp_path):
    bad = tmp_path / "bad2.md"
    bad.write_text("---\nid: x\nname: x\ngoal: x\nstages:\n"
                   "  - id: 0\n    name: a\n---\n", encoding="utf-8")
    with pytest.raises(ValueError, match="done_when"):
        ec.load_frontmatter(str(bad))


def test_evidence_lines_require_upgrade_rule(tmp_path):
    bad = tmp_path / "bad3.md"
    bad.write_text("---\nid: x\nname: x\ngoal: x\nstages:\n"
                   "  - id: 0\n    name: a\n    done_when: {artifacts: ['a.json']}\n"
                   "evidence_lines:\n  - {id: a, stage: 0, output: a.json}\n"
                   "  - {id: b, stage: 0, output: b.json}\n---\n", encoding="utf-8")
    with pytest.raises(ValueError, match="upgrade_rule"):
        ec.load_frontmatter(str(bad))


def test_list_playbooks_skips_spec(fm):
    ids = [pid for pid, _, _ in ec.list_playbooks()]
    assert "training-sufficiency" in ids
    assert not any(i.startswith("_") for i in ids)


# ---------------------------------------------------------------- check-DSL
def test_check_config_and_pending(fm, workdir):
    ctx = ctx_of(fm, {"a": {"b": 1}, "p": "【待补】", "e": ""})
    assert ec.check("config:a.b", ctx)
    assert not ec.check("config:p", ctx)       # 【待补】= 未填
    assert not ec.check("config:e", ctx)
    assert not ec.check("config:missing", ctx)
    assert ec.check("not config:missing", ctx)


def test_check_file_and_artifact(fm, workdir):
    (workdir / "data.csv").write_text("x", encoding="utf-8")
    ctx = ctx_of(fm, {"path": str(workdir / "data.csv"), "bad": str(workdir / "no.csv")})
    assert ec.check("file:config.path", ctx)
    assert not ec.check("file:config.bad", ctx)
    assert ec.check("artifact:data.csv", ctx)
    assert not ec.check("artifact:nothing_*.json", ctx)


def test_check_stage_and_question(fm, workdir):
    ctx = ctx_of(fm, {"questions": {"loss-source": {"answer": "csv", "source": "user"}}})
    (workdir / "probe_summary.json").write_text("{}", encoding="utf-8")
    assert ec.check("stage:0", ctx)
    assert not ec.check("stage:1", ctx)
    assert ec.check("question:loss-source", ctx)
    assert not ec.check("question:sufficiency-criterion", ctx)
    with pytest.raises(ValueError, match="未声明的问题"):
        ec.check("question:no-such-q", ctx)


def test_check_unknown_prefix_raises(fm, workdir):
    with pytest.raises(ValueError, match="未知 DSL"):
        ec.check("magic:foo", ctx_of(fm))


# ---------------------------------------------------------------- 阶段判定
def test_stage_done_marker_and_manual(fm, workdir):
    st5 = ec._stage_by_id(fm, 5)
    ctx = ctx_of(fm)
    assert not ec.stage_done(st5, ctx)
    (workdir / "FINDINGS.md").write_text("| x | y | 现象 | 2026-07-14 |", encoding="utf-8")
    assert ec.stage_done(st5, ctx)
    manual_st = {"id": 9, "name": "m", "done_when": {"manual": True}}
    assert not ec.stage_done(manual_st, ctx_of(fm, state={}))
    assert ec.stage_done(manual_st, ctx_of(fm, state={"manual_done": [9]}))


def test_variant_skip_and_current_stage(fm, workdir):
    ctx = ctx_of(fm, {})
    actives = ec.variant_active(fm, ctx)
    assert not actives["grouped"] and not actives["external"]
    st3, st4 = ec._stage_by_id(fm, 3), ec._stage_by_id(fm, 4)
    assert ec.stage_skipped(st3, fm, ctx) and ec.stage_skipped(st4, fm, ctx)
    # 造 0-2 的产物 → 当前应跳过 3/4 直达 5
    for name in ("probe_summary.json", "loss_records.csv", "dynamics_metrics.json"):
        (workdir / name).write_text("{}", encoding="utf-8")
    assert ec.current_stage(fm, ctx)["id"] == 5
    # 激活 grouped → 3 不再跳过
    ctx2 = ctx_of(fm, {"grouped": True})
    assert not ec.stage_skipped(st3, fm, ctx2)
    assert ec.current_stage(fm, ctx2)["id"] == 3


def test_all_done_returns_none(fm, workdir):
    for name in ("probe_summary.json", "loss_records.csv", "dynamics_metrics.json",
                 "CONCLUSION.md"):
        (workdir / name).write_text("{}", encoding="utf-8")
    (workdir / "FINDINGS.md").write_text("现象", encoding="utf-8")
    assert ec.current_stage(fm, ctx_of(fm, {})) is None


def test_prereqs_optional_prefix(fm, workdir):
    st = {"id": 7, "name": "x", "done_when": {"manual": True},
          "prereqs": [{"desc": "（可选）有更好", "check": "artifact:no.csv"},
                      {"desc": "必须有", "check": "artifact:yes.csv"}]}
    (workdir / "yes.csv").write_text("x", encoding="utf-8")
    pr = ec.prereqs_of(st, ctx_of(fm))
    assert ec.prereqs_ok(pr)  # 可选项 ✗ 不阻塞


# ---------------------------------------------------------------- 问题状态
def test_question_status_lifecycle(fm, workdir):
    q_loss = ec._question_by_id(fm, "loss-source")
    q_cfgd = ec._question_by_id(fm, "training-config")
    q_unit = ec._question_by_id(fm, "unit-structure")

    ctx = ctx_of(fm, {})
    assert ec.question_status(q_loss, ctx)[0] == "unanswered"
    assert ec.question_status(q_cfgd, ctx)[0] == "default-available"

    ctx = ctx_of(fm, {"questions": {"loss-source": {"answer": "x", "source": "user"},
                                    "unit-structure": {"answer": "y", "source": "profile"}}})
    assert ec.question_status(q_loss, ctx)[0] == "user"
    assert ec.question_status(q_unit, ctx)[0] == "profile"

    # skip_if 证据自答 vs 实验线 provenance
    ctx = ctx_of(fm, {"chunking": {"n_chunks": 4}})
    assert ec.question_status(q_unit, ctx)[0] == "evidence"
    ctx = ctx_of(fm, {"chunking": {"n_chunks": 4}, "_experiment_line_keys": ["chunking"]})
    assert ec.question_status(q_unit, ctx)[0] == "experiment-line"


def test_blocking_questions_by_stage(fm, workdir):
    ctx = ctx_of(fm, {})
    b0 = [q["id"] for q in ec.blocking_questions(fm, ctx, stage_id=0)]
    assert set(b0) == {"loss-source", "unit-structure"}  # training-config 有 default 不阻塞
    b6 = [q["id"] for q in ec.blocking_questions(fm, ctx, stage_id=6)]
    assert b6 == ["sufficiency-criterion"]
    assert len(ec.blocking_questions(fm, ctx)) == 3  # 全局：external-metric/fig-style 有 default


# ---------------------------------------------------------------- contexts
def test_context_status_branches(fm, workdir):
    cx = {"id": "up", "name": "上游", "workdir_key": "up_dir", "status_key": "up_status",
          "marker_files": ["FINDINGS.md"]}
    assert ec.context_status(cx, ctx_of(fm, {}))["status"] == "absent"
    assert ec.context_status(cx, ctx_of(fm, {"up_status": "declined"}))["status"] == "declined"
    up = workdir / "up"
    up.mkdir()
    cs = ec.context_status(cx, ctx_of(fm, {"up_status": "linked", "up_dir": str(up)}))
    assert cs["status"] == "linked" and cs["missing_markers"] == ["FINDINGS.md"]
    (up / "FINDINGS.md").write_text("现象", encoding="utf-8")
    cs = ec.context_status(cx, ctx_of(fm, {"up_status": "linked", "up_dir": str(up)}))
    assert cs["missing_markers"] == []


# ---------------------------------------------------------------- 合并
def test_merge_experiment_line(fm, workdir):
    exp = {"name": "l1", "held_out_station": "X", "models": ["A", "B"],
           "chunking": {"n_chunks": 4},
           "data_paths": {"test_label": "【待补】", "metric_py": str(workdir / "m.py")}}
    p = workdir / "l1.json"
    p.write_text(json.dumps(exp), encoding="utf-8")
    cfg = {"models": ["already"]}
    merged = ec.merge_experiment_line(cfg, str(p))
    assert "chunking" in merged and "held_out_station" in merged
    assert cfg["models"] == ["already"]          # 已填不覆盖
    assert "data_test_label" not in cfg          # 【待补】不搬
    assert cfg["data_metric_py"] == str(workdir / "m.py")
    assert "chunking" in cfg["_experiment_line_keys"]


def test_merge_profile_version_gate(fm, workdir):
    prof_ok = {"profile_version": ec.PROFILE_VERSION, "playbook": "training-sufficiency",
               "config_defaults": {"log_dir": "/tmp/logs"},
               "questions": {"loss-source": {"answer": "结构化 CSV"}}}
    cfg = {}
    res = ec.merge_profile(cfg, prof_ok, "2026-07-14")
    assert res["version_ok"] and cfg["playbook"] == "training-sufficiency"
    assert cfg["questions"]["loss-source"]["source"] == "profile"

    prof_old = dict(prof_ok, profile_version=0)
    cfg2 = {}
    res2 = ec.merge_profile(cfg2, prof_old, "2026-07-14")
    assert not res2["version_ok"]
    assert "questions" not in cfg2 or not cfg2["questions"]  # 降级：不合并问答
    assert cfg2["log_dir"] == "/tmp/logs"                    # defaults 照常合并


# ---------------------------------------------------------------- orient 冒烟（子进程）
ORIENT = os.path.join(SCRIPTS_DIR, "orient.py")


def run_orient(cwd, *args):
    return subprocess.run([sys.executable, ORIENT, *args],
                          cwd=cwd, capture_output=True, text=True, timeout=60)


def test_orient_no_config_guidance(workdir):
    r = run_orient(workdir)
    assert r.returncode == 0 and "未找到 diagnose_config.json" in r.stdout
    assert "training-sufficiency" in r.stdout


def test_orient_bind_playbook_and_progress(workdir):
    r = run_orient(workdir, "--playbook", "training-sufficiency")
    assert r.returncode == 0, r.stderr
    assert "← 当前" in r.stdout and "✗未答" in r.stdout
    assert "阻塞 Stage 0" in r.stdout
    assert (workdir / "diagnose_state.json").exists()
    assert (workdir / "PROGRESS.md").exists()
    state = json.loads((workdir / "diagnose_state.json").read_text(encoding="utf-8"))
    assert state["current_stage"] == 0
    assert state["stages"]["3"] == "skipped"


def test_orient_goto_blocked_reports_entry(workdir):
    run_orient(workdir, "--playbook", "training-sufficiency")
    r = run_orient(workdir, "--goto", "6")
    assert "不能直达 Stage 6" in r.stdout and "正确入口 = Stage 0" in r.stdout


def test_orient_profile_merge_and_skip_questions(workdir):
    prof = workdir / "profile.yaml"
    prof.write_text(
        "profile_version: 1\nplaybook: training-sufficiency\n"
        "config_defaults:\n  log_dir: /tmp/x\n"
        "questions:\n  loss-source: {answer: 结构化 CSV}\n"
        "  unit-structure: {answer: chunk 轮换}\n", encoding="utf-8")
    r = run_orient(workdir, "--profile", str(prof))
    assert r.returncode == 0, r.stderr
    assert "✓固化(profile)" in r.stdout
    cfg = json.loads((workdir / "diagnose_config.json").read_text(encoding="utf-8"))
    assert cfg["questions"]["loss-source"]["source"] == "profile"
    # 固化了 Stage 0 两问 → Stage 0 前置应齐
    assert "可开工 Stage 0" in r.stdout


def test_orient_profile_version_mismatch_degrades(workdir):
    prof = workdir / "profile.yaml"
    prof.write_text("profile_version: 99\nplaybook: training-sufficiency\n"
                    "questions:\n  loss-source: {answer: x}\n", encoding="utf-8")
    r = run_orient(workdir, "--profile", str(prof))
    assert "profile_version" in r.stdout and "降级" in r.stdout
    assert "✗未答" in r.stdout  # loss-source 未被合并，仍必问
