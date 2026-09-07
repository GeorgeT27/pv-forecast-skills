import glob, os, sys, tempfile
import pytest
SCRIPTS_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, SCRIPTS_DIR)
import engine_common as ec  # noqa: E402
ENGINE_DIR = os.path.dirname(SCRIPTS_DIR)
PLAYBOOKS = sorted(glob.glob(os.path.join(ENGINE_DIR, "playbooks", "*", "playbook.md")))


@pytest.mark.parametrize("path", PLAYBOOKS, ids=lambda p: p.split(os.sep)[-2])
def test_every_stage_maps_to_exactly_one_section(path):
    fm = ec.load_frontmatter(path)
    secs = ec.recipe_sections(path)
    for st in fm["stages"]:
        assert st["id"] in secs, f"Stage {st['id']} 无 '### Stage {st['id']}' 小节"
        assert secs[st["id"]].startswith("### Stage")
        assert len(secs[st["id"]]) > 80, f"Stage {st['id']} 小节过短"


def _write(text):
    d = tempfile.mkdtemp()
    p = os.path.join(d, "playbook.md")
    open(p, "w", encoding="utf-8").write(text)
    return p


FM = "---\nid: x\nname: x\ngoal: g\nstages:\n  - id: 0\n    name: a\n    done_when: {manual: true}\n---\n"


def test_range_heading_maps_each_id_and_stops_at_next_heading():
    p = _write(FM + "\n## 2. 逐阶段菜谱\n\n### Stage 0 甲\n步骤甲\n\n### Stage 1–2 乙\n步骤乙\n\n## 3. 停顿\n别算进去\n")
    secs = ec.recipe_sections(p)
    assert set(secs) == {0, 1, 2}
    assert secs[1] == secs[2] and "步骤乙" in secs[1] and "别算进去" not in secs[1]
    assert "步骤甲" in secs[0] and "步骤乙" not in secs[0]


def test_duplicate_stage_heading_raises():
    p = _write(FM + "\n### Stage 0 甲\nx\n\n### Stage 0 又来\ny\n")
    with pytest.raises(ValueError):
        ec.recipe_sections(p)
