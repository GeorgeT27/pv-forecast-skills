import os, re, sys, glob
HERE = os.path.dirname(os.path.abspath(__file__))
SCRIPTS_DIR = os.path.dirname(HERE)
V2 = os.path.dirname(SCRIPTS_DIR)
sys.path.insert(0, SCRIPTS_DIR)
import engine_common as ec  # noqa: E402

def _read(p): return open(p, encoding="utf-8").read()

def test_every_playbook_has_exactly_one_card():
    pbs = {os.path.basename(os.path.dirname(p)) for p in glob.glob(os.path.join(V2, "playbooks", "*", "playbook.md"))}
    cards = {os.path.basename(p)[:-len("-compute.md")] for p in glob.glob(os.path.join(V2, "agents", "*-compute.md"))}
    assert pbs == cards, f"卡片与 playbook 不是一一对应：仅playbook={pbs-cards} 仅卡片={cards-pbs}"

def test_skill_indexes_all_cards_and_routes_all_playbooks():
    skill = _read(os.path.join(V2, "SKILL.md"))
    for pid in {os.path.basename(os.path.dirname(p)) for p in glob.glob(os.path.join(V2, "playbooks", "*", "playbook.md"))}:
        assert pid in skill, f"SKILL 路由/索引缺 {pid}"
        assert f"{pid}-compute" in skill, f"SKILL 卡片索引缺 {pid}-compute"

def test_skill_dispatch_delta_references_engine_and_batch():
    skill = _read(os.path.join(V2, "SKILL.md"))
    assert "engine-core.md" in skill
    assert "dispatch-protocol.md" in skill

def test_dispatch_protocol_covers_modes_and_batch():
    dp = _read(os.path.join(V2, "references", "dispatch-protocol.md"))
    assert "batch.py" in dp or "batch-orchestration.md" in dp
    assert "NEED_INFO" in dp
