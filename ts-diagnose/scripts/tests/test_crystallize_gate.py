"""固化三关判据测试（硬不变量三）+ experiment_line v0-draft 占位测试。

用 feature-importance（crystallize_min_cases 默认 3，golden 覆盖 stage 0，
快照直接借 golden reference 实现）伪造 record，逐关验证 FAIL/PASS。
"""
import json
import os
import shutil
import subprocess
import sys

import pytest

SCRIPTS_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, SCRIPTS_DIR)
import engine_common as ec  # noqa: E402

GATE = os.path.join(SCRIPTS_DIR, "crystallize_gate.py")


def good_record():
    return {
        "playbook": "feature-importance",
        "cases": [{"name": f"case{i}", "input_hash": f"h{i}", "workdir": f"/w{i}",
                   "date": "2026-07-14", "boundary": f"边界{i}"} for i in range(3)],
        "heldout": {"name": "留出", "input_hash": "h-held", "passed": True,
                    "date": "2026-07-14"},
        "snapshots": [{"file": "scripts/correlation_screen.py", "stage": 0}],
    }


@pytest.fixture
def skill_dir(tmp_path):
    (tmp_path / "scripts").mkdir()
    ref = os.path.join(ec.playbook_dir("feature-importance"),
                       "golden", "reference", "correlation_screen.py")
    shutil.copy(ref, tmp_path / "scripts" / "correlation_screen.py")
    return tmp_path


def run_gate(skill_dir, record):
    rec = skill_dir / "crystallize_record.json"
    rec.write_text(json.dumps(record, ensure_ascii=False), encoding="utf-8")
    return subprocess.run(
        [sys.executable, GATE, "--record", str(rec), "--skill-dir", str(skill_dir)],
        capture_output=True, text=True)


def test_all_gates_pass(skill_dir):
    r = run_gate(skill_dir, good_record())
    assert r.returncode == 0, r.stdout + r.stderr
    assert "三关全过" in r.stdout


def test_gate1_diversity_fails_on_duplicate_hashes(skill_dir):
    rec = good_record()
    for c in rec["cases"]:
        c["input_hash"] = "same"                      # 同场景微调伪装成多样性
    r = run_gate(skill_dir, rec)
    assert r.returncode == 1 and "关1 多样性：FAIL" in r.stdout


def test_gate1_respects_playbook_min_cases():
    """training-sufficiency 声明 crystallize_min_cases=5，默认为 3。"""
    fm_ts = ec.load_frontmatter(ec.find_playbook("training-sufficiency"))
    fm_fi = ec.load_frontmatter(ec.find_playbook("feature-importance"))
    assert ec.crystallize_min_cases(fm_ts) == 5
    assert ec.crystallize_min_cases(fm_fi) == 3


def test_gate2_heldout_missing_or_failed_or_overlapping(skill_dir):
    rec = good_record()
    rec.pop("heldout")
    assert run_gate(skill_dir, rec).returncode == 1
    rec = good_record()
    rec["heldout"]["passed"] = False
    r = run_gate(skill_dir, rec)
    assert r.returncode == 1 and "关2 held-out：FAIL" in r.stdout
    rec = good_record()
    rec["heldout"]["input_hash"] = "h0"               # 与开发 case 重合 = 不算留出
    assert run_gate(skill_dir, rec).returncode == 1


def test_gate3_bad_snapshot_fails(skill_dir):
    (skill_dir / "scripts" / "correlation_screen.py").write_text(
        "import argparse, json\n"
        "ap = argparse.ArgumentParser()\n"
        "for f in ('--data','--target','--leakage','--out'): ap.add_argument(f)\n"
        "a = ap.parse_args()\n"
        "json.dump({'n_rows': 1}, open(a.out,'w'))\n", encoding="utf-8")
    r = run_gate(skill_dir, good_record())
    assert r.returncode == 1 and "关3 快照自洽：FAIL" in r.stdout


def test_gate3_uncovered_stage_is_warning_not_fail(skill_dir):
    rec = good_record()
    rec["snapshots"].append({"file": "scripts/correlation_screen.py", "stage": 2})
    r = run_gate(skill_dir, rec)
    assert r.returncode == 0 and "未机判" in r.stdout


# ---------------------------------------------------------------- v0-draft 占位
def test_profile_experiment_line_v0_draft_is_placeholder():
    cfg = {}
    prof = {"profile_version": ec.PROFILE_VERSION, "playbook": "training-sufficiency",
            "experiment_line": {"path": "/pc/experiments/x.json",
                                "interface_version": "v0-draft"}}
    res = ec.merge_profile(cfg, prof, "2026-07-14")
    assert res["experiment_line_placeholder"]
    assert "experiment_line" not in cfg               # 占位不生效：不写进 cfg

    cfg2 = {}
    prof2 = dict(prof, experiment_line="/pc/experiments/x.json")   # 旧裸字符串形态
    assert ec.merge_profile(cfg2, prof2, "2026-07-14")["experiment_line_placeholder"]
    assert "experiment_line" not in cfg2

    cfg3 = {}
    prof3 = dict(prof, experiment_line={"path": "/pc/experiments/x.json",
                                        "interface_version": "v1"})
    res3 = ec.merge_profile(cfg3, prof3, "2026-07-14")
    assert not res3["experiment_line_placeholder"]
    assert cfg3["experiment_line"] == "/pc/experiments/x.json"     # 定稿版才生效
