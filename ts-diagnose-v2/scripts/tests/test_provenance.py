"""归因闸测试：可复现（同输入两次同 hash）、可归因（改数据只动 data hash）、
陈旧闸报告拦截（脚本过闸后被改 → 退出码 1）。"""
import json
import os
import subprocess
import sys

SCRIPTS_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PROV = os.path.join(SCRIPTS_DIR, "provenance.py")


def run_prov(workdir, out="provenance.json"):
    return subprocess.run(
        [sys.executable, PROV, "--code", "analysis_scripts/*.py",
         "--data", "input.csv", "--out", out],
        cwd=workdir, capture_output=True, text=True)


def setup(tmp_path):
    (tmp_path / "analysis_scripts").mkdir()
    (tmp_path / "analysis_scripts" / "a.py").write_text("print(1)\n", encoding="utf-8")
    (tmp_path / "input.csv").write_text("x\n1\n", encoding="utf-8")


def test_reproducible_and_attributable(tmp_path):
    setup(tmp_path)
    assert run_prov(tmp_path, "p1.json").returncode == 0
    assert run_prov(tmp_path, "p2.json").returncode == 0
    p1 = json.load(open(tmp_path / "p1.json", encoding="utf-8"))
    p2 = json.load(open(tmp_path / "p2.json", encoding="utf-8"))
    assert p1["code"]["combined"] == p2["code"]["combined"]
    assert p1["data"]["combined"] == p2["data"]["combined"]

    (tmp_path / "input.csv").write_text("x\n2\n", encoding="utf-8")
    assert run_prov(tmp_path, "p3.json").returncode == 0
    p3 = json.load(open(tmp_path / "p3.json", encoding="utf-8"))
    assert p3["data"]["combined"] != p1["data"]["combined"]      # 数据变 → data hash 变
    assert p3["code"]["combined"] == p1["code"]["combined"]      # 代码没动 → code hash 不变


def test_stale_gate_report_blocks(tmp_path):
    setup(tmp_path)
    (tmp_path / "gate_reports").mkdir()
    (tmp_path / "gate_reports" / "a.json").write_text(json.dumps(
        {"script": "analysis_scripts/a.py", "script_sha256": "0" * 64,
         "playbook": "x", "stage": "1", "passed": True}), encoding="utf-8")
    r = run_prov(tmp_path)
    assert r.returncode == 1 and "重跑 gen_gate" in r.stdout
    prov = json.load(open(tmp_path / "provenance.json", encoding="utf-8"))
    assert prov["golden_selfcheck"]["a.py"]["stale"]
    assert not prov["all_gates_passed"]
