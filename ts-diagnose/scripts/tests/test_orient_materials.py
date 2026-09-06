"""orient 材料盘点段的端到端测试（subprocess 跑真 orient，断言输出契约）。"""
import os
import subprocess
import sys

SCRIPTS_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ORIENT = os.path.join(SCRIPTS_DIR, "orient.py")
sys.path.insert(0, SCRIPTS_DIR)
import engine_common as ec  # noqa: E402

PB = """---
id: mat-demo
name: 材料演示
goal: 测试材料盘点
materials:
  required: [predict, truth]
  optional: [model_code]
stages:
  - id: 0
    name: 起步
    done_when: {artifacts: ['stage0.json']}
---
正文占位。
"""


def run_orient(workdir, *args):
    r = subprocess.run([sys.executable, ORIENT, *args], cwd=workdir,
                       capture_output=True, text=True, timeout=60)
    assert r.returncode == 0, r.stderr
    return r.stdout


FIVE_OK = {}


def setup_pb(tmp_path, cfg_materials=None, five_ok=True):
    pb = tmp_path / "pb" / "playbook.md"
    pb.parent.mkdir()
    pb.write_text(PB, encoding="utf-8")
    mats = dict(FIVE_OK) if five_ok else {}
    mats.update(cfg_materials or {})
    cfg = {"playbook": str(pb)}
    if mats:
        cfg["materials"] = mats
    ec.dump_json(cfg, str(tmp_path / "diagnose_config.json"))
    return tmp_path


def test_blocked_when_unknown(tmp_path):
    out = run_orient(setup_pb(tmp_path, five_ok=False))
    assert "BLOCKED: 材料盘点未完成" in out
    assert "Stage 0" not in out
    assert "可开工" not in out
    assert "追问" in out


def test_optional_model_code_does_not_block_orient(tmp_path):
    mats = {"predict": {"status": "present", "paths": ["x.parquet"],
                        "schema": {"y_col": "y", "time_col": "ts"}},
            "truth": {"status": "present", "paths": ["x.parquet"],
                     "schema": {"y_col": "y", "time_col": "ts"}},
            "model_code": {"status": "present", "paths": ["x.parquet"]}}
    out = run_orient(setup_pb(tmp_path, mats))
    assert "[✓present] predict (required)" in out
    assert "先嵌入执行 playbook「model-audit」" not in out
    assert "→ 前置齐，可开工 Stage 0" in out


def test_modelmap_receipt_unlocks_open(tmp_path):
    """已有回执不影响 optional model_code 的正常开工。"""
    mats = {"predict": {"status": "present", "paths": ["x.parquet"],
                        "schema": {"y_col": "y", "time_col": "ts"}},
            "truth": {"status": "present", "paths": ["x.parquet"],
                     "schema": {"y_col": "y", "time_col": "ts"}},
            "model_code": {"status": "present", "paths": ["x.parquet"]}}
    wd = setup_pb(tmp_path, mats)
    (wd / "MODELMAP_RECEIPT.json").write_text(
        '{"modelmap_dir": "x", "commit": "abc"}', encoding="utf-8")
    out = run_orient(wd)
    assert "先嵌入执行 playbook「model-audit」" not in out
    assert "→ 前置齐，可开工 Stage 0" in out


def test_degraded_absent_not_blocking(tmp_path):
    mats = {"predict": {"status": "present", "paths": ["x.parquet"],
                        "schema": {"y_col": "y", "time_col": "ts"}},
            "truth": {"status": "absent-confirmed", "source": "user",
                     "degraded_ok": True}}
    out = run_orient(setup_pb(tmp_path, mats))
    assert "[−absent] truth (required, 已确认降级)" in out
    assert "⚠ 必需材料未就绪" not in out
    assert "→ 前置齐，可开工 Stage 0" in out


def test_absent_without_waiver_blocks(tmp_path):
    mats = {"predict": {"status": "present", "paths": ["x.parquet"],
                        "schema": {"y_col": "y", "time_col": "ts"}},
            "truth": {"status": "absent-confirmed", "source": "user"}}
    out = run_orient(setup_pb(tmp_path, mats))
    assert "BLOCKED: 材料盘点未完成" in out
    assert "absent-need-degraded-ok" in out or "须用户确认接受降级" in out
    assert "可开工" not in out


def test_legacy_playbook_no_materials_section(tmp_path):
    """无 materials 声明的旧 playbook 不因未使用材料被入口闸阻塞。"""
    cfg = {"playbook": "training-sufficiency"}
    ec.dump_json(cfg, str(tmp_path / "diagnose_config.json"))
    out = run_orient(tmp_path)
    assert "BLOCKED" not in out
    assert "材料盘点" not in out


def test_goto_still_gated_when_materials_unknown(tmp_path):
    """--goto 直达阶段不得绕过入口闸：required 材料 unknown 时仍须 BLOCKED。"""
    out = run_orient(setup_pb(tmp_path, five_ok=False), "--goto", "0")
    assert "BLOCKED: 材料盘点未完成" in out
    assert "可开工" not in out


def test_blocked_hides_all_menus_and_logs_progress(tmp_path):
    wd = setup_pb(tmp_path, five_ok=False)
    out = run_orient(wd)
    assert "BLOCKED: 材料盘点未完成" in out
    for banned in ("Stage 0", "图表选择门", "问题清单", "可开工", "前置"):
        assert banned not in out
    assert "AskUserQuestion" in out and "materials" in out
    audit = (wd / ".orient_audit.jsonl").read_text(encoding="utf-8")
    assert "BLOCKED" in audit


def test_present_without_schema_blocks(tmp_path):
    mats = {"predict": {"status": "present", "paths": ["p.parquet"]},  # 缺 schema
            "truth": {"status": "present", "paths": ["t.parquet"],
                      "schema": {"y_col": "y", "time_col": "ts"}}}
    out = run_orient(setup_pb(tmp_path, mats))
    assert "BLOCKED" in out and "present-incomplete" in out
    assert "schema.y_col" in out
