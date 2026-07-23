"""生成闸测试（硬不变量二）。

端到端：每个 playbook 的 golden reference 实现必须过闸（这同时钉死 CLI 契约与
期望值的自洽）；蓄意算错的脚本金标准必须 FAIL；危险副作用必须静态 FAIL。

REFS 从各 playbook golden/manifest.json 的 stage 条目 `reference` 字段动态收集
（弱模型压力测试 G-2 同族修复：硬编码清单会让新 playbook 的 reference 静默脱闸）；
MIN_REFS 下限断言防清单静默缩水。
"""
import json
import os
import subprocess
import sys

import pytest

SCRIPTS_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, SCRIPTS_DIR)
import engine_common as ec  # noqa: E402
import gen_gate as gg  # noqa: E402

MIN_REFS = 9  # 2026-07 五 playbook 时的 reference 数——只许增不许减


def collect_refs():
    out = []
    for pid, _, _ in ec.list_playbooks():
        man = ec.read_json(os.path.join(ec.playbook_dir(pid), "golden", "manifest.json"))
        for stage, ent in sorted(((man or {}).get("stages") or {}).items()):
            if ent.get("reference"):
                out.append((pid, stage, ent["reference"]))
    return out


REFS = collect_refs()


def test_refs_not_shrunk():
    assert len(REFS) >= MIN_REFS, (
        f"manifest reference 声明只剩 {len(REFS)} 条（下限 {MIN_REFS}）——"
        "有人删了 reference 字段或 golden？")


def run_gate(workdir, script, playbook, stage):
    return subprocess.run(
        [sys.executable, os.path.join(SCRIPTS_DIR, "gen_gate.py"),
         "--script", script, "--playbook", playbook, "--stage", str(stage)],
        cwd=workdir, capture_output=True, text=True)


@pytest.mark.parametrize("playbook,stage,rel", REFS)
def test_reference_impl_passes_gate(tmp_path, playbook, stage, rel):
    script = os.path.join(ec.playbook_dir(playbook), "golden", rel)
    r = run_gate(tmp_path, script, playbook, stage)
    assert r.returncode == 0, r.stdout + r.stderr
    report_name = os.path.basename(rel).rsplit(".", 1)[0] + ".json"
    rep = json.load(open(tmp_path / "gate_reports" / report_name, encoding="utf-8"))
    assert rep["passed"] and rep["static"]["passed"] and rep["golden"]["passed"]
    assert len(rep["script_sha256"]) == 64


def test_wrong_result_fails_golden(tmp_path):
    """算错的脚本（CLI 正确、期望值错）必须被金标准拦下——不许碰真实数据。"""
    bad = tmp_path / "bad_screen.py"
    bad.write_text(
        "import argparse, json\n"
        "ap = argparse.ArgumentParser()\n"
        "for f in ('--data','--target','--leakage','--out'): ap.add_argument(f)\n"
        "a = ap.parse_args()\n"
        "json.dump({'n_rows': 100, 'dropped_rows': 0,\n"
        "           'features': {'x1': {'spearman_vs_error': 0.1},\n"
        "                        'x2': {'spearman_vs_error': 0.9},\n"
        "                        'x3': {'spearman_vs_error': 1.0}},\n"
        "           'leakage_flagged': ['x3'],\n"
        "           'ranking_nonleak': ['x2','x1']}, open(a.out,'w'))\n",
        encoding="utf-8")
    r = run_gate(tmp_path, str(bad), "feature-importance", "0")
    assert r.returncode != 0
    assert "不许拿本脚本跑真实数据" in r.stdout


def test_schema_violation_fails_golden(tmp_path):
    """产物缺契约字段（schema 漂移）同样 FAIL，而不是静默跳过断言。"""
    bad = tmp_path / "bad_schema.py"
    bad.write_text(
        "import argparse, json\n"
        "ap = argparse.ArgumentParser()\n"
        "for f in ('--data','--target','--leakage','--out'): ap.add_argument(f)\n"
        "a = ap.parse_args()\n"
        "json.dump({'whatever': 1}, open(a.out,'w'))\n", encoding="utf-8")
    r = run_gate(tmp_path, str(bad), "feature-importance", "0")
    assert r.returncode != 0


def test_static_check_bans_subprocess_and_abs_write(tmp_path):
    bad = tmp_path / "danger.py"
    bad.write_text("import subprocess\nopen('/etc/x', 'w')\n", encoding="utf-8")
    ok, issues = gg.static_check(str(bad))
    assert not ok
    assert any("subprocess" in i for i in issues)
    assert any("绝对路径写" in i for i in issues)
    r = run_gate(tmp_path, str(bad), "feature-importance", "0")
    assert r.returncode != 0 and "跳过（静态检查未过）" in r.stdout


def test_static_check_allows_relative_write(tmp_path):
    good = tmp_path / "fine.py"
    good.write_text("import json\njson.dump({}, open('out.json', 'w'))\n", encoding="utf-8")
    ok, issues = gg.static_check(str(good))
    assert ok, issues


def test_check_dsl_ops(tmp_path):
    (tmp_path / "o.json").write_text(json.dumps(
        {"a": {"b": 3.0}, "d": {"x": {"v": 1}, "y": {"v": 9}}, "l": ["p", "q"]}),
        encoding="utf-8")
    sb = str(tmp_path)
    assert gg.eval_check({"file": "o.json", "path": "a.b", "op": "eq", "value": 3.01,
                          "tol": 0.05}, sb)[0]
    assert gg.eval_check({"file": "o.json", "path": "a.b", "op": "between",
                          "value": [2, 4]}, sb)[0]
    assert gg.eval_check({"file": "o.json", "path": "d", "op": "argmax", "field": "v",
                          "value": "y"}, sb)[0]
    assert gg.eval_check({"file": "o.json", "path": "l", "op": "first_is",
                          "value": "p"}, sb)[0]
    assert not gg.eval_check({"file": "o.json", "path": "l", "op": "contains",
                              "value": "z"}, sb)[0]


def test_every_playbook_has_golden():
    """每个 playbook 必须自带金标准（manifest + 声明的输入文件齐全）。"""
    for pid, _, _ in ec.list_playbooks():
        gdir = os.path.join(ec.playbook_dir(pid), "golden")
        man = ec.read_json(os.path.join(gdir, "manifest.json"))
        assert man and man.get("stages"), f"{pid} 缺 golden/manifest.json"
        for st, ent in man["stages"].items():
            for rel in ent.get("inputs") or []:
                assert os.path.exists(os.path.join(gdir, rel)), f"{pid} golden 缺 {rel}"
            assert ent.get("args") and ent.get("expect"), f"{pid} stage {st} 契约不完整"
            assert ent.get("reference"), (
                f"{pid} stage {st} 缺 reference 字段——reference 不声明就不进 CI 闸")
            assert os.path.exists(os.path.join(gdir, ent["reference"])), \
                f"{pid} stage {st} 的 reference 文件不存在：{ent['reference']}"
