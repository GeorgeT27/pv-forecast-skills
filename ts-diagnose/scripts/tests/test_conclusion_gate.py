"""结论闸测试：subprocess 跑真 gate，断言 exit code 与 receipt。"""
import json
import os
import subprocess
import sys

SCRIPTS_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
GATE = os.path.join(SCRIPTS_DIR, "conclusion_gate.py")
sys.path.insert(0, SCRIPTS_DIR)
import engine_common as ec  # noqa: E402

PB = """---
id: gate-demo
name: g
goal: g
stages:
  - id: 0
    name: 图
    done_when: {artifacts: ['charts/*.json', 'INDEX.md']}
    charts: [error-breakdown]
  - id: 1
    name: 结论
    done_when: {artifacts: ['CONCLUSION.md']}
---
"""

GOOD = """# 结论
误差集中在 horizon 末段（见 charts/error-breakdown.png）。
## 模型结构依据
档案 H3：attention 窗口 96 点 → 预期长时效退化，与 charts/error-breakdown.png 一致。
"""


def setup(tmp_path, conclusion, with_chart=True):
    pb = tmp_path / "pb" / "playbook.md"
    pb.parent.mkdir()
    pb.write_text(PB, encoding="utf-8")
    ec.dump_json({"playbook": str(pb)}, str(tmp_path / "diagnose_config.json"))
    if with_chart:
        (tmp_path / "charts").mkdir()
        (tmp_path / "charts" / "error-breakdown.png").write_bytes(b"png")
    if conclusion is not None:
        (tmp_path / "CONCLUSION.md").write_text(conclusion, encoding="utf-8")
    return tmp_path


def run_gate(wd):
    return subprocess.run([sys.executable, GATE], cwd=wd,
                          capture_output=True, text=True, timeout=60)


def test_pass_writes_receipt(tmp_path):
    wd = setup(tmp_path, GOOD)
    r = run_gate(wd)
    assert r.returncode == 0, r.stdout + r.stderr
    rec = json.load(open(wd / "gate_reports" / "conclusion_gate.json"))
    assert rec["passed"] is True and rec["conclusion_sha256"]


def test_fail_missing_structure_section(tmp_path):
    wd = setup(tmp_path, "# 结论\n没依据。\n")
    r = run_gate(wd)
    assert r.returncode == 1
    assert "模型结构依据" in r.stdout
    assert not (wd / "gate_reports" / "conclusion_gate.json").exists()


def test_degraded_statement_accepted(tmp_path):
    c = ("# 结论\n（见 charts/error-breakdown.png）\n## 模型结构依据\n"
         "模型档案缺失（materials.model_code = absent-confirmed），结构性解释降级为猜测级。\n")
    assert run_gate(setup(tmp_path, c)).returncode == 0


def test_fail_cited_chart_missing(tmp_path):
    bad = GOOD.replace("error-breakdown.png", "no-such-chart.png")
    wd = setup(tmp_path, bad)
    r = run_gate(wd)
    assert r.returncode == 1 and "no-such-chart.png" in r.stdout


def test_fail_no_chart_citation_when_chart_stage(tmp_path):
    c = "# 结论\n直觉归因。\n## 模型结构依据\n档案 H1 支持。\n"
    r = run_gate(setup(tmp_path, c))
    assert r.returncode == 1 and "图" in r.stdout


def test_decoy_path_containing_charts_substring_rejected(tmp_path):
    wd = setup(tmp_path, None)
    (wd / "mycharts").mkdir()
    (wd / "mycharts" / "decoy.png").write_bytes(b"png")
    c = ("# 结论\n误差分析（见 mycharts/decoy.png）。\n"
         "## 模型结构依据\n档案 H3：attention 窗口 96 点。\n")
    (wd / "CONCLUSION.md").write_text(c, encoding="utf-8")
    r = run_gate(wd)
    assert r.returncode == 1 and "图" in r.stdout
    assert not (wd / "gate_reports" / "conclusion_gate.json").exists()


def test_charts_rooted_citation_required_even_with_lookalike_file(tmp_path):
    wd = setup(tmp_path, None)
    (wd / "archived_charts_summary.json").write_text("{}", encoding="utf-8")
    c = ("# 结论\n误差分析（见 archived_charts_summary.json）。\n"
         "## 模型结构依据\n档案 H3：attention 窗口 96 点。\n")
    (wd / "CONCLUSION.md").write_text(c, encoding="utf-8")
    r = run_gate(wd)
    assert r.returncode == 1 and "图" in r.stdout
    assert not (wd / "gate_reports" / "conclusion_gate.json").exists()
