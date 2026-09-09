"""取证计划（plan-first 选图门）：模式判定、frontmatter 硬要求、chart_plan.py 校验、
orient 两回合打印（计划未落盘时图池必须不出现）。"""
import json
import os
import subprocess
import sys
import textwrap

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
import chart_plan as cp  # noqa: E402
import engine_common as ec  # noqa: E402

ENGINE = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
ORIENT = os.path.join(ENGINE, "scripts", "orient.py")
PLAN_CLI = os.path.join(ENGINE, "scripts", "chart_plan.py")

REST = {mid: {"status": "absent-confirmed", "source": "user"}
        for mid in ("training_log", "train_y", "checkpoint", "model_code")}
PT = {"predict": {"status": "present", "paths": ["p.parquet"],
                  "schema": {"y_col": "y", "time_col": "ts"}},
      "truth": {"status": "present", "paths": ["t.parquet"],
                "schema": {"y_col": "y", "time_col": "ts"}}}

GOOD = {"question": "TSMixer 的落后是集中在某段时间还是全年普遍",
        "evidence": "按月切分的逐模型误差、差距集中度、对随机基线的对照",
        "recipe": "worst-slice-compare", "source": "chartbook"}


def _pb(tmp_path, gate_line="", arts='["x.json", "INDEX.md"]'):
    d = tmp_path / "playbooks" / "demo-plan"
    d.mkdir(parents=True)
    (d / "playbook.md").write_text(textwrap.dedent(f"""\
        ---
        id: demo-plan
        name: demo
        goal: g
        {gate_line}
        stages:
          - id: 0
            name: s0
            done_when: {{artifacts: {arts}}}
            charts: [error-breakdown]
        materials:
          required: [predict, truth]
        ---
        正文
        """))
    return str(d / "playbook.md")


def _run_orient(tmp_path, pb_path, plan=None):
    cfg = {"playbook": pb_path, "materials": dict(PT, **REST)}
    (tmp_path / "diagnose_config.json").write_text(json.dumps(cfg))
    if plan is not None:
        (tmp_path / "chart_plan.json").write_text(
            json.dumps(plan, ensure_ascii=False))
    proc = subprocess.run([sys.executable, ORIENT], cwd=tmp_path,
                          capture_output=True, text=True)
    assert proc.returncode == 0, proc.stderr
    return proc.stdout


# ------------------------------------------------------------ 模式判定
def test_chart_gate_mode_defaults_to_sweep():
    assert ec.chart_gate_mode({}) == "sweep"
    assert ec.chart_gate_mode(None) == "sweep"
    assert ec.chart_gate_mode({"chart_gate": "plan-first"}) == "plan-first"
    assert ec.chart_gate_mode({"chart_gate": "nonsense"}) == "sweep"


def test_chart_plan_ready_reads_entries(tmp_path):
    p = tmp_path / "chart_plan.json"
    assert not ec.chart_plan_ready(str(p))
    p.write_text(json.dumps({"entries": []}))
    assert not ec.chart_plan_ready(str(p)), "空 entries 不算就绪"
    p.write_text(json.dumps({"entries": [GOOD]}, ensure_ascii=False))
    assert ec.chart_plan_ready(str(p))
    assert ec.chart_plan_entries(str(p))[0]["recipe"] == "worst-slice-compare"


# ------------------------------------------ frontmatter 硬要求（漏写直接拦）
def test_plan_first_stage_must_declare_chart_plan_artifact(tmp_path):
    p = _pb(tmp_path, gate_line="chart_gate: plan-first")
    with pytest.raises(ValueError, match="chart_plan.json"):
        ec.load_frontmatter(p)


def test_plan_first_stage_with_artifact_loads(tmp_path):
    p = _pb(tmp_path, gate_line="chart_gate: plan-first",
            arts='["chart_plan.json", "x.json", "INDEX.md"]')
    assert ec.chart_gate_mode(ec.load_frontmatter(p)) == "plan-first"


def test_sweep_stage_not_required_to_declare_chart_plan(tmp_path):
    """向后兼容：不写 chart_gate 的旧剧本不受新要求约束。"""
    assert ec.load_frontmatter(_pb(tmp_path))


def test_model_comparison_is_plan_first():
    """守卫：归因主剧本不许退回菜单驱动。"""
    fm = ec.load_frontmatter(
        os.path.join(ENGINE, "playbooks", "model-comparison", "playbook.md"))
    assert ec.chart_gate_mode(fm) == "plan-first"
    st1 = [s for s in fm["stages"] if s.get("charts")][0]
    assert "chart_plan.json" in st1["done_when"]["artifacts"]


def test_fact_scan_stays_sweep():
    """守卫：体检剧本保持全画——它的活就是没有疑问时广撒网。"""
    fm = ec.load_frontmatter(
        os.path.join(ENGINE, "playbooks", "fact-scan", "playbook.md"))
    assert ec.chart_gate_mode(fm) == "sweep"


# ------------------------------------------------------------ 计划校验
def test_plan_rejects_empty_entries():
    errs, _ = cp.validate_plan({"entries": []})
    assert any("为空" in e for e in errs)


def test_plan_rejects_missing_top_key():
    assert cp.validate_plan({})[0]


def test_plan_rejects_thin_question_and_evidence():
    errs, _ = cp.validate_plan(
        {"entries": [{"question": "分析", "evidence": "看图",
                      "recipe": "", "source": "chartbook"}]})
    assert any("question 太短" in e for e in errs)
    assert any("evidence 太短" in e for e in errs)


def test_plan_rejects_evidence_echoing_question():
    q = "TSMixer 的落后集中在哪一段时间"
    errs, _ = cp.validate_plan(
        {"entries": [{"question": q, "evidence": q,
                      "recipe": "", "source": "chartbook"}]})
    assert any("雷同" in e for e in errs)


def test_plan_rejects_bad_source():
    errs, _ = cp.validate_plan({"entries": [dict(GOOD, source="随便")]})
    assert any("source 非法" in e for e in errs)


def test_plan_requires_verification_for_ad_hoc():
    e = dict(GOOD, source="ad-hoc", recipe="analysis_scripts/x.py")
    errs, _ = cp.validate_plan({"entries": [e]})
    assert any("verification" in x for x in errs)
    errs2, _ = cp.validate_plan({"entries": [dict(e, verification="reconcile-2")]})
    assert not errs2


def test_exploratory_warns_but_passes():
    e = dict(GOOD, source="ad-hoc", recipe="analysis_scripts/x.py",
             verification="exploratory")
    errs, warns = cp.validate_plan({"entries": [e]})
    assert not errs
    assert any("只作线索" in w for w in warns)


def test_plan_rejects_invented_chartbook_recipe():
    errs, _ = cp.validate_plan({"entries": [dict(GOOD, recipe="magic-chart")]},
                               known=set(ec.available_recipes()))
    assert any("不在 chartbook" in e for e in errs)


def test_plan_skips_recipe_check_when_registry_unavailable():
    errs, _ = cp.validate_plan({"entries": [dict(GOOD, recipe="magic-chart")]},
                               known=None)
    assert not errs


def test_strict_requires_recipe_filled():
    e = dict(GOOD, recipe="")
    assert not cp.validate_plan({"entries": [e]})[0], "非 strict 允许 recipe 待匹配"
    errs, _ = cp.validate_plan({"entries": [e]}, strict=True)
    assert any("recipe 未填" in x for x in errs)


def test_cli_missing_file_fails(tmp_path):
    proc = subprocess.run([sys.executable, PLAN_CLI], cwd=tmp_path,
                          capture_output=True, text=True)
    assert proc.returncode == 1
    assert "读不到" in proc.stdout


def test_cli_accepts_good_plan(tmp_path):
    (tmp_path / "chart_plan.json").write_text(
        json.dumps({"entries": [GOOD]}, ensure_ascii=False))
    proc = subprocess.run([sys.executable, PLAN_CLI, "--strict"], cwd=tmp_path,
                          capture_output=True, text=True)
    assert proc.returncode == 0, proc.stdout
    assert "已可开画" in proc.stdout


# ------------------------------------------------------- orient 两回合
def test_orient_hides_pool_before_plan(tmp_path):
    """核心防跳过：计划没落盘，图池一个字都不许出现——看不到菜单就没法从菜单里挑。"""
    p = _pb(tmp_path, gate_line="chart_gate: plan-first",
            arts='["chart_plan.json", "x.json", "INDEX.md"]')
    out = _run_orient(tmp_path, p)
    assert "error-breakdown" not in out, "声明图名泄漏"
    assert "intraday-profile" not in out, "可加画池泄漏"
    assert "✓可画" not in out
    assert "第一步" in out and "chart_plan.json" in out
    assert "图池暂不展示" in out


def test_orient_unlocks_pool_after_plan(tmp_path):
    p = _pb(tmp_path, gate_line="chart_gate: plan-first",
            arts='["chart_plan.json", "x.json", "INDEX.md"]')
    out = _run_orient(tmp_path, p, plan={"entries": [GOOD]})
    assert "✓可画" in out and "error-breakdown" in out
    assert "第二步" in out
    assert "worst-slice-compare" in out, "计划条目应回显"
    assert GOOD["question"][:12] in out


def test_orient_sweep_mode_unchanged(tmp_path):
    """回归守卫：不写 chart_gate 的剧本仍是老四步全勾流程。"""
    p = _pb(tmp_path)
    out = _run_orient(tmp_path, p)
    assert "默认全勾" in out
    assert "✓可画" in out and "error-breakdown" in out
    assert "第一步" not in out
