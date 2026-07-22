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


# ---------------------------------------------------------------- material: DSL
def test_material_dsl(tmp_path):
    fm = fm_with_materials(tmp_path, "materials:\n  required: [predict]\n"
                                     "  optional: [model_code]\n")
    cfg = {"materials": {"predict": {"status": "present"},
                         "model_code": {"status": "absent-confirmed"}}}
    ctx = {"cfg": cfg, "fm": fm, "state": {}}
    assert ec.check("material:predict", ctx) is True
    assert ec.check("material:model_code", ctx) is False      # absent ≠ present
    assert ec.check("material:training_log", ctx) is False    # unknown ≠ present
    assert ec.check("not material:model_code", ctx) is True
    with pytest.raises(ValueError, match="未知材料"):
        ec.check("material:predikt", ctx)


def test_material_dsl_drives_variant(tmp_path):
    """材料驱动变体解锁：有 model_code 才激活机制归因类阶段（spec §2 orient 改动）。"""
    p = tmp_path / "pb.md"
    p.write_text("---\nid: x\nname: x\ngoal: x\n"
                 "materials:\n  required: [predict]\n  optional: [model_code]\n"
                 "stages:\n"
                 "  - id: 0\n    name: a\n    done_when: {artifacts: ['a.json']}\n"
                 "  - id: 1\n    name: b\n    done_when: {artifacts: ['b.json']}\n"
                 "variants:\n"
                 "  - id: model-side\n    when: 'material:model_code'\n"
                 "    unlocks_stages: [1]\n---\n", encoding="utf-8")
    fm = ec.load_frontmatter(str(p))
    ctx = {"cfg": {}, "fm": fm, "state": {}}
    assert ec.variant_active(fm, ctx) == {"model-side": False}
    ctx["cfg"] = {"materials": {"model_code": {"status": "present"}}}
    assert ec.variant_active(fm, ctx) == {"model-side": True}


# ---------------------------------------------------------------- provider_skill
CX = {"id": "model-profile", "name": "模型参考档案",
      "workdir_key": "modelmap_dir", "status_key": "modelmap_status",
      "marker_files": ["models.md"], "on_absent": "ask",
      "provider_skill": "pv-model-analysis", "trigger_material": "model_code"}


def test_context_embed_hint():
    cfg_has = {"materials": {"model_code": {"status": "present"}}}
    hint = ec.context_embed_hint(CX, cfg_has)
    assert "pv-model-analysis" in hint and "嵌入" in hint
    # 触发材料不 present → 不提议嵌入
    assert ec.context_embed_hint(CX, {}) is None
    # 无 provider_skill → 永远 None
    cx2 = {k: v for k, v in CX.items() if k != "provider_skill"}
    assert ec.context_embed_hint(cx2, cfg_has) is None
    # 无 trigger_material → 只要有 provider_skill 就提议
    cx3 = {k: v for k, v in CX.items() if k != "trigger_material"}
    assert ec.context_embed_hint(cx3, {}) is not None


def test_frontmatter_rejects_bad_trigger_material(tmp_path):
    p = tmp_path / "pb.md"
    p.write_text("---\nid: x\nname: x\ngoal: x\nstages:\n"
                 "  - id: 0\n    name: a\n    done_when: {artifacts: ['a.json']}\n"
                 "contexts:\n"
                 "  - id: c\n    name: c\n    workdir_key: w\n    status_key: s\n"
                 "    trigger_material: nope\n---\n", encoding="utf-8")
    with pytest.raises(ValueError, match="trigger_material"):
        ec.load_frontmatter(str(p))


# ---------------------------------------------------------------- profile 固化
def test_merge_profile_materials():
    prof = {"profile_version": ec.PROFILE_VERSION, "playbook": "x",
            "materials": {
                "predict": {"status": "present", "layout": "per-model",
                            "schema": {"y_col": "power"}},
                "truth": {"status": "present"}}}
    cfg = {"materials": {"truth": {"status": "absent-confirmed", "source": "user"}}}
    res = ec.merge_profile(cfg, prof, "2026-07-22")
    assert res["merged_materials"] == ["predict"]          # truth 已有，不覆盖
    assert cfg["materials"]["predict"]["status"] == "present"
    assert cfg["materials"]["predict"]["source"] == "profile"
    assert cfg["materials"]["truth"]["status"] == "absent-confirmed"  # 原样保留


def test_merge_profile_materials_absent_key():
    prof = {"profile_version": ec.PROFILE_VERSION, "playbook": "x"}
    cfg = {}
    res = ec.merge_profile(cfg, prof, "2026-07-22")
    assert res["merged_materials"] == []


# ---------------------------------------------------------------- intake.md 交叉校验
def test_intake_doc_covers_all_material_ids():
    doc = os.path.join(os.path.dirname(SCRIPTS_DIR), "references", "intake.md")
    text = open(doc, encoding="utf-8").read()
    for mid in ec.MATERIAL_IDS:
        assert f"## `{mid}`" in text, f"intake.md 缺材料 '{mid}' 的小节"
    for kw in ("absent-confirmed", "degraded_ok", "还有别的", "sample_rows",
               "y_col", "对账"):
        assert kw in text, f"intake.md 缺关键纪律词 '{kw}'"
