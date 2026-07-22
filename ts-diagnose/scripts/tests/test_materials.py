"""materials 机制（intake 材料盘点的数据模型 + DSL + frontmatter 校验）测试。"""
import os
import sys

import pytest

SCRIPTS_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, SCRIPTS_DIR)
import engine_common as ec  # noqa: E402


def fm_with_materials(tmp_path, materials_yaml):
    p = tmp_path / "pb.md"
    p.write_text("---\nid: x\nname: x\ngoal: x\n"
                 f"{materials_yaml}"
                 "stages:\n  - id: 0\n    name: a\n"
                 "    done_when: {artifacts: ['a.json']}\n---\n", encoding="utf-8")
    return ec.load_frontmatter(str(p))


# ---------------------------------------------------------------- 状态判定
def test_material_status_three_values():
    cfg = {"materials": {
        "predict": {"status": "present", "paths": ["a.parquet"]},
        "training_log": {"status": "absent-confirmed"},
        "truth": {"status": "怪值"},
    }}
    assert ec.material_status(cfg, "predict") == "present"
    assert ec.material_status(cfg, "training_log") == "absent-confirmed"
    assert ec.material_status(cfg, "truth") == "unknown"      # 非法值按 unknown
    assert ec.material_status(cfg, "model_code") == "unknown"  # 无记录
    assert ec.material_status(None, "predict") == "unknown"    # 无 config
    assert ec.material_status({}, "predict") == "unknown"


# ---------------------------------------------------------------- frontmatter
def test_materials_of_and_report(tmp_path):
    fm = fm_with_materials(
        tmp_path, "materials:\n  required: [predict, truth]\n  optional: [model_code]\n")
    assert ec.materials_of(fm) == (["predict", "truth"], ["model_code"])
    cfg = {"materials": {"predict": {"status": "present"}}}
    assert ec.materials_report(fm, cfg) == [
        ("predict", "required", "present"),
        ("truth", "required", "unknown"),
        ("model_code", "optional", "unknown"),
    ]


def test_materials_of_absent_key(tmp_path):
    fm = fm_with_materials(tmp_path, "")   # 无 materials 键（旧 playbook 形态）
    assert ec.materials_of(fm) == ([], [])
    assert ec.materials_report(fm, {}) == []
    assert ec.blocking_materials(fm, {}) == []


def test_frontmatter_rejects_unknown_material_id(tmp_path):
    with pytest.raises(ValueError, match="材料 id"):
        fm_with_materials(tmp_path, "materials:\n  required: [predikt]\n")


def test_frontmatter_rejects_required_optional_overlap(tmp_path):
    with pytest.raises(ValueError, match="既是 required 又是 optional"):
        fm_with_materials(
            tmp_path, "materials:\n  required: [predict]\n  optional: [predict]\n")


# ---------------------------------------------------------------- 阻塞
def test_blocking_materials(tmp_path):
    fm = fm_with_materials(
        tmp_path, "materials:\n  required: [predict, truth, training_log]\n"
                  "  optional: [model_code]\n")
    cfg = {"materials": {
        "predict": {"status": "present"},
        "truth": {"status": "absent-confirmed"},                      # 阻塞（未降级）
        "training_log": {"status": "absent-confirmed", "degraded_ok": True},  # 已降级不阻塞
    }}
    assert ec.blocking_materials(fm, cfg) == [("truth", "absent")]
    # optional 永不阻塞
    cfg2 = {"materials": {"predict": {"status": "present"},
                          "truth": {"status": "present"},
                          "training_log": {"status": "present"}}}
    assert ec.blocking_materials(fm, cfg2) == []
    # 全 unknown → required 逐个报 unknown
    assert ec.blocking_materials(fm, {}) == [
        ("predict", "unknown"), ("truth", "unknown"), ("training_log", "unknown")]


def test_existing_playbooks_still_load():
    """向后兼容：现有三个 playbook 无 materials 键，加载与判定不受影响。"""
    for pid in ("training-sufficiency", "robustness", "feature-importance"):
        fm = ec.load_frontmatter(ec.find_playbook(pid))
        assert ec.materials_of(fm) == ([], [])
