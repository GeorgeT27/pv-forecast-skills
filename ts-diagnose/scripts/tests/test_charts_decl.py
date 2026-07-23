"""charts 声明：frontmatter 校验（未知 recipe id 报错并列出可用）、recipe_materials
解析、charts_report 按盘点结果分可画/缺材料、orient e2e 输出。"""
import json
import os
import subprocess
import sys
import textwrap

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
import engine_common as ec  # noqa: E402

ENGINE = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
ORIENT = os.path.join(ENGINE, "scripts", "orient.py")


def _pb(tmp_path, charts_line):
    d = tmp_path / "playbooks" / "demo-charts"
    d.mkdir(parents=True)
    (d / "playbook.md").write_text(textwrap.dedent(f"""\
        ---
        id: demo-charts
        name: demo
        goal: g
        stages:
          - id: 0
            name: s0
            done_when: {{artifacts: ["x.json"]}}
        {charts_line}
        materials:
          required: [predict, truth]
          optional: [features]
        ---
        正文
        """))
    return str(d / "playbook.md")


def test_recipe_materials_reads_frontmatter():
    assert ec.recipe_materials("error-breakdown") == ["predict", "truth"]
    assert "features" in ec.recipe_materials("feature-error-conditional")


def test_recipe_materials_unknown_id_lists_available():
    with pytest.raises(ValueError, match="error-breakdown"):
        ec.recipe_materials("no-such-recipe")


def test_frontmatter_rejects_unknown_chart_id(tmp_path):
    p = _pb(tmp_path, "    charts: [no-such-recipe]")
    with pytest.raises(ValueError, match="no-such-recipe"):
        ec.load_frontmatter(p)


def test_frontmatter_rejects_non_list_charts(tmp_path):
    p = _pb(tmp_path, "    charts: error-breakdown")
    with pytest.raises(ValueError, match="charts"):
        ec.load_frontmatter(p)


def test_charts_report_splits_by_materials(tmp_path):
    p = _pb(tmp_path, "    charts: [error-breakdown, feature-error-conditional]")
    fm = ec.load_frontmatter(p)
    cfg = {"materials": {"predict": {"status": "present"},
                         "truth": {"status": "present"}}}
    rep = ec.charts_report(fm, cfg)
    by_rid = {rid: missing for (_sid, rid, missing) in rep}
    assert by_rid["error-breakdown"] == []
    assert "features" in by_rid["feature-error-conditional"]


def test_orient_prints_chart_availability(tmp_path):
    pb_dir = tmp_path / "playbooks" / "demo-charts"
    pb_path = _pb(tmp_path, "    charts: [error-breakdown, feature-error-conditional]")
    cfg = {"playbook": pb_path,
           "materials": {"predict": {"status": "present"},
                         "truth": {"status": "present"}}}
    (tmp_path / "diagnose_config.json").write_text(json.dumps(cfg))
    proc = subprocess.run(
        [sys.executable, ORIENT], cwd=tmp_path, capture_output=True, text=True)
    assert proc.returncode == 0, proc.stderr
    out = proc.stdout
    assert "✓可画" in out and "error-breakdown" in out
    assert "✗缺材料" in out and "feature-error-conditional" in out


def test_addable_recipes_excludes_declared_and_missing(tmp_path):
    """可加画池：未声明 且 材料全满足的 recipe 才进；声明过的、或材料缺的都不进。"""
    p = _pb(tmp_path, "    charts: [error-breakdown]")
    fm = ec.load_frontmatter(p)
    cfg = {"materials": {"predict": {"status": "present"},
                         "truth": {"status": "present"}}}  # 无 features
    pool = {rid: mm for rid, _needs, mm in ec.addable_recipes(fm, cfg)}
    assert "error-breakdown" not in pool, "已声明的不进可加画池"
    assert "intraday-profile" in pool, "未声明且 predict+truth 满足的应进池"
    assert "feature-error-conditional" not in pool, "缺 features 的不进池"
    assert pool["worst-slice-compare"] == 2, "对比类图带 needs_models=2 标注"
    assert pool["intraday-profile"] == 1, "单模型图默认 min_models=1"
    # 补上 features → 需要 features 的 recipe 进池
    cfg["materials"]["features"] = {"status": "present"}
    pool2 = {rid for rid, _n, _m in ec.addable_recipes(fm, cfg)}
    assert "feature-error-conditional" in pool2


def test_has_chart_stage(tmp_path):
    assert ec.has_chart_stage(ec.load_frontmatter(_pb(tmp_path / "a", "    charts: [error-breakdown]")))
    assert not ec.has_chart_stage(ec.load_frontmatter(_pb(tmp_path / "b", "")))


def test_orient_prints_selection_gate(tmp_path):
    _pb(tmp_path, "    charts: [error-breakdown]")
    pb_path = str(tmp_path / "playbooks" / "demo-charts" / "playbook.md")
    cfg = {"playbook": pb_path,
           "materials": {"predict": {"status": "present"},
                         "truth": {"status": "present"}}}
    (tmp_path / "diagnose_config.json").write_text(json.dumps(cfg))
    proc = subprocess.run(
        [sys.executable, ORIENT], cwd=tmp_path, capture_output=True, text=True)
    assert proc.returncode == 0, proc.stderr
    assert "图表选择门" in proc.stdout
    assert "可加画" in proc.stdout
    assert "intraday-profile" in proc.stdout  # 未声明但材料满足 → 出现在可加画池
    assert "需 ≥2 模型" in proc.stdout        # 对比类图（worst-slice-compare 等）带模型数标注


def test_all_real_playbooks_frontmatter_loads():
    """终审 I-1 守卫：全部真实 playbook 的 frontmatter 必须能过校验加载——
    charts 声明的 recipe 改名/被删时 CI 立刻红，而不是等用户跑 orient 才炸。"""
    import glob
    paths = sorted(glob.glob(os.path.join(ENGINE, "playbooks", "*", "playbook.md")))
    assert len(paths) >= 5, "五个 playbook 应已就位"
    for p in paths:
        fm = ec.load_frontmatter(p)
        assert fm.get("id"), f"{p} frontmatter 无 id"
