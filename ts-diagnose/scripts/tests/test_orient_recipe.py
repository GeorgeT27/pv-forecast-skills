import json, os, shutil, subprocess, sys
SCRIPTS_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ENGINE_DIR = os.path.dirname(SCRIPTS_DIR)
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


# ---------------------------------------------------------- 菜谱通则（preamble）
def test_recipe_flag_prints_preamble_with_gen_gate_rule(tmp_path):
    """robustness 的生成闸硬规则写在 `## 2.` 节开头，必须随菜谱打印到眼前。"""
    (tmp_path / "diagnose_config.json").write_text(json.dumps({"playbook": "robustness"}), encoding="utf-8")
    out = _orient(tmp_path, "--recipe", "1")
    assert "📖 菜谱通则（playbook.md 该节开头原文）" in out
    assert "gen_gate.py" in out and "--playbook robustness --stage 1" in out


def test_recipe_flag_omits_preamble_when_heading_only(tmp_path):
    """fact-scan 的 `## 2.` 节只有标题，没有通则可打——不打空表头。"""
    (tmp_path / "diagnose_config.json").write_text(json.dumps({"playbook": "fact-scan"}), encoding="utf-8")
    out = _orient(tmp_path, "--recipe", "0")
    assert "📖 菜谱通则" not in out
    assert "### Stage 0 画图与现象清单" in out


# ---------------------------------------------------------- 抽取失败降级为警告
def _factscan_with_duplicate_stage(tmp_path):
    """复制 fact-scan playbook 并追加重复的 `### Stage 0` 标题；配好材料与 setup 产物，
    使 orient 走到「前置齐 → 打印菜谱」这一步。"""
    pb = tmp_path / "pb" / "playbook.md"
    pb.parent.mkdir()
    shutil.copy(os.path.join(ENGINE_DIR, "playbooks", "fact-scan", "playbook.md"), pb)
    with open(pb, "a", encoding="utf-8") as f:
        f.write("\n### Stage 0 dup\n重复标题，抽取器必须报错。\n")
    setup = tmp_path / "setup"
    setup.mkdir()
    (setup / "predictions.csv").write_text("t,y\n", encoding="utf-8")
    (setup / "alignment_report.json").write_text("{}", encoding="utf-8")
    (setup / "setup_manifest.json").write_text("{}", encoding="utf-8")
    schema = {"y_col": "y", "time_col": "ts"}
    cfg = {"playbook": str(pb),
           "materials": {"predict": {"status": "present", "paths": ["p.parquet"], "schema": schema},
                         "truth": {"status": "present", "paths": ["t.parquet"], "schema": schema}},
           "products": {"setup": {"workdir": "setup", "status": "built"}}}
    (tmp_path / "diagnose_config.json").write_text(json.dumps(cfg, ensure_ascii=False), encoding="utf-8")
    return tmp_path


def test_duplicate_stage_heading_degrades_to_warning_and_still_writes_state(tmp_path):
    wd = _factscan_with_duplicate_stage(tmp_path)
    r = subprocess.run([sys.executable, ORIENT], cwd=wd, capture_output=True, text=True)
    assert r.returncode == 0, r.stderr
    assert "菜谱抽取失败" in r.stdout
    assert (wd / "diagnose_state.json").exists()


def test_duplicate_stage_heading_recipe_flag_warns_and_exits_zero(tmp_path):
    wd = _factscan_with_duplicate_stage(tmp_path)
    r = subprocess.run([sys.executable, ORIENT, "--recipe", "0"], cwd=wd,
                       capture_output=True, text=True)
    assert r.returncode == 0, r.stderr
    assert "菜谱抽取失败" in r.stdout
    assert not (wd / "diagnose_state.json").exists()


# ---------------------------------------------------------- --no-recipe
PB_MIN = """---
id: recipe-demo
name: 菜谱演示
goal: 测试 --no-recipe
materials:
  required: [predict, truth]
stages:
  - id: 0
    name: 起步
    done_when: {artifacts: ['stage0.json']}
---
正文占位。

### Stage 0 起步

菜谱正文占位，长度足够让抽取器认这是一节正经菜谱内容。
"""


def _ready_workdir(tmp_path):
    pb = tmp_path / "pb" / "playbook.md"
    pb.parent.mkdir()
    pb.write_text(PB_MIN, encoding="utf-8")
    schema = {"y_col": "y", "time_col": "ts"}
    cfg = {"playbook": str(pb),
           "materials": {"predict": {"status": "present", "paths": ["p.parquet"], "schema": schema},
                         "truth": {"status": "present", "paths": ["t.parquet"], "schema": schema}}}
    (tmp_path / "diagnose_config.json").write_text(json.dumps(cfg, ensure_ascii=False), encoding="utf-8")
    return tmp_path


def test_no_recipe_suppresses_recipe_but_keeps_stage_entry(tmp_path):
    out = _orient(_ready_workdir(tmp_path), "--no-recipe")
    assert "→ 前置齐" in out
    assert "📖 本阶段菜谱" not in out
