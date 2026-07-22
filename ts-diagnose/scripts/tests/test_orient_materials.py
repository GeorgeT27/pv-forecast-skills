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
contexts:
  - id: model-profile
    name: 模型参考档案
    workdir_key: modelmap_dir
    status_key: modelmap_status
    marker_files: [models.md]
    on_absent: ask
    provider_skill: pv-model-analysis
    trigger_material: model_code
---
正文占位。
"""


def run_orient(workdir, *args):
    r = subprocess.run([sys.executable, ORIENT, *args], cwd=workdir,
                       capture_output=True, text=True, timeout=60)
    assert r.returncode == 0, r.stderr
    return r.stdout


def setup_pb(tmp_path, cfg_materials=None):
    pb = tmp_path / "pb" / "playbook.md"
    pb.parent.mkdir()
    pb.write_text(PB, encoding="utf-8")
    cfg = {"playbook": str(pb)}
    if cfg_materials is not None:
        cfg["materials"] = cfg_materials
    ec.dump_json(cfg, str(tmp_path / "diagnose_config.json"))
    return tmp_path


def test_blocked_when_unknown(tmp_path):
    out = run_orient(setup_pb(tmp_path))
    assert "材料盘点" in out
    assert "[✗未盘点·阻塞] predict (required)" in out
    assert "[✗未盘点·阻塞] truth (required)" in out
    assert "[○未盘点] model_code (optional)" in out
    assert "⚠ 必需材料未就绪" in out and "intake.md" in out
    assert "可开工" not in out


def test_open_when_present_and_embed_hint(tmp_path):
    mats = {"predict": {"status": "present"}, "truth": {"status": "present"},
            "model_code": {"status": "present"}}
    out = run_orient(setup_pb(tmp_path, mats))
    assert "[✓present] predict (required)" in out
    assert "→ 前置齐，可开工 Stage 0" in out
    # model_code present + 上下文 absent → 打印嵌入提示
    assert "pv-model-analysis" in out and "嵌入" in out


def test_degraded_absent_not_blocking(tmp_path):
    mats = {"predict": {"status": "present"},
            "truth": {"status": "absent-confirmed", "degraded_ok": True}}
    out = run_orient(setup_pb(tmp_path, mats))
    assert "[−absent] truth (required, 已确认降级)" in out
    assert "⚠ 必需材料未就绪" not in out
    assert "→ 前置齐，可开工 Stage 0" in out


def test_absent_without_waiver_blocks(tmp_path):
    mats = {"predict": {"status": "present"},
            "truth": {"status": "absent-confirmed"}}
    out = run_orient(setup_pb(tmp_path, mats))
    assert "[−absent] truth (required)" in out
    assert "⚠ 必需材料未就绪" in out
    assert "可开工" not in out


def test_legacy_playbook_no_materials_section(tmp_path):
    """向后兼容：真实 training-sufficiency playbook 无 materials 键 → 无盘点段。"""
    ec.dump_json({"playbook": "training-sufficiency"},
                 str(tmp_path / "diagnose_config.json"))
    out = run_orient(tmp_path)
    assert "材料盘点" not in out
