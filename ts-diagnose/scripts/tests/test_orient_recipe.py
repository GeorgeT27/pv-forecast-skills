import json, os, subprocess, sys
SCRIPTS_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ORIENT = os.path.join(SCRIPTS_DIR, "orient.py")


def _orient(workdir, *args):
    return subprocess.run([sys.executable, ORIENT, *args], cwd=workdir,
                          capture_output=True, text=True).stdout


def test_recipe_flag_prints_only_that_section_and_writes_no_state(tmp_path):
    (tmp_path / "diagnose_config.json").write_text(json.dumps({"playbook": "model-comparison"}), encoding="utf-8")
    out = _orient(tmp_path, "--recipe", "0")
    assert "### Stage 0 总差距事实" in out
    assert "gap_metrics.py" in out
    assert "### Stage 1" not in out
    assert not (tmp_path / "diagnose_state.json").exists()
    assert not (tmp_path / "PROGRESS.md").exists()


def test_recipe_flag_unknown_stage(tmp_path):
    (tmp_path / "diagnose_config.json").write_text(json.dumps({"playbook": "model-comparison"}), encoding="utf-8")
    out = _orient(tmp_path, "--recipe", "9")
    assert "无 Stage 9" in out
