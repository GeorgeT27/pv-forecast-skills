"""金标准端到端：三个阶段脚本必须过 gen_gate（复用 ts-diagnose 的闸，--playbook 给路径形式）。

这同时钉死：CLI 契约、产物 schema、埋点召回（f_blame 被点名）与诱饵拒绝（f_decoy 不被点名）。
另含一个「放水脚本必须 FAIL」用例——谁把诱饵点了名，金标准就拦谁，钉住诱饵断言有牙。
"""
import json
import os
import subprocess
import sys

import pytest

HERE = os.path.dirname(os.path.abspath(__file__))
SKILL = os.path.dirname(HERE)
REPO = os.path.dirname(SKILL)
GATE = os.path.join(REPO, "ts-diagnose", "scripts", "gen_gate.py")
PLAYBOOK = os.path.join(SKILL, "SKILL.md")   # 路径形式：golden/ 解析到本技能目录下

STAGES = [("0", "probe_schema.py"), ("1", "find_bad_rows.py"), ("2", "feature_blame.py"),
          ("revision", "feature_revision.py"), ("4", "cf_logic.py")]


def run_gate(workdir, script, stage):
    return subprocess.run(
        [sys.executable, GATE, "--script", script, "--playbook", PLAYBOOK, "--stage", stage],
        cwd=workdir, capture_output=True, text=True)


@pytest.mark.parametrize("stage,script", STAGES)
def test_stage_scripts_pass_gate(tmp_path, stage, script):
    r = run_gate(tmp_path, os.path.join(HERE, script), stage)
    assert r.returncode == 0, r.stdout + r.stderr
    rep = json.load(open(tmp_path / "gate_reports" / (script[:-3] + ".json"), encoding="utf-8"))
    assert rep["passed"] and rep["static"]["passed"] and rep["golden"]["passed"]
    assert len(rep["script_sha256"]) == 64


BAD_BLAME = r'''
import argparse, json
ap = argparse.ArgumentParser()
ap.add_argument("--feature-true")
a, _ = ap.parse_known_args()
def feats(top):
    out = {}
    for f in ("f_blame", "f_decoy", "f_good", "ghi"):
        out[f] = {"global_spearman": 0.95 if f == top else 0.1,
                  "feature_err_mean": 2.0 if f in ("f_blame", "f_decoy") else 0.0,
                  "blamed_rows": 1 if f == top else 0, "z_max": 3.0}
    return out
summary = {}
for metric in ("ultra_short", "short", "rmse_192"):
    for model in ("pred_M1", "pred_ensemble"):
        summary.setdefault(metric, {})[model] = {
            "n_rows": 40, "n_bad": 1, "features": feats("f_decoy"),   # 放水：点名了诱饵
            "ranking_by_spearman": ["f_decoy", "f_blame", "f_good", "ghi"],
            "collinearity_clusters": []}
json.dump(summary, open("blame_summary.json", "w"))
open("blame_report.csv", "w").write("model,metric\n")
'''


def test_decoy_assertion_has_teeth(tmp_path):
    """CLI 正确、产物 schema 正确、但把误差大的诱饵点了名 → 金标准必须 FAIL。"""
    bad = tmp_path / "bad_blame.py"
    bad.write_text(BAD_BLAME, encoding="utf-8")
    r = run_gate(tmp_path, str(bad), "2")
    assert r.returncode != 0
    assert "不许拿本脚本跑真实数据" in r.stdout


def test_manifest_inputs_exist():
    """manifest 声明的 golden 输入文件必须齐全（防中间产物漏拷/漏提交）。"""
    gdir = os.path.join(SKILL, "golden")
    man = json.load(open(os.path.join(gdir, "manifest.json"), encoding="utf-8"))
    assert man.get("stages")
    for st, ent in man["stages"].items():
        for rel in ent.get("inputs") or []:
            assert os.path.exists(os.path.join(gdir, rel)), f"golden 缺 {rel}（stage {st}）"
        assert ent.get("args") and ent.get("expect"), f"stage {st} 契约不完整"
