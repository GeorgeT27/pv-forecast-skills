import os, re, glob, sys
import yaml
import pytest

HERE = os.path.dirname(os.path.abspath(__file__))
SCRIPTS_DIR = os.path.join(os.path.dirname(HERE))          # ts-diagnose-v2/scripts
V2 = os.path.dirname(SCRIPTS_DIR)                          # ts-diagnose-v2
AGENTS_DIR = os.path.join(V2, "agents")
sys.path.insert(0, SCRIPTS_DIR)
import engine_common as ec  # noqa: E402

PRODUCTS = {"setup", "model_profile", "metric_table", "chart_sweep", "eval_report"}
BODY_LINE_BUDGET = 60
FORBIDDEN_BODY = ["## 逐阶段菜谱", "### Stage", "## 2. 逐阶段"]
SIX_SECTIONS = ["你是谁", "输入", "步骤", "红线", "输出契约", "停顿"]

def _card_paths():
    return sorted(p for p in glob.glob(os.path.join(AGENTS_DIR, "*-compute.md")))

def _split(path):
    text = open(path, encoding="utf-8").read()
    assert text.startswith("---\n"), f"{path} 缺 frontmatter"
    end = text.index("\n---", 3)
    fm = yaml.safe_load(text[4:end])
    body = text[end+4:]
    return fm, body

def _stage_range(spec):
    lo, _, hi = str(spec).partition("-")
    return (int(lo), int(hi if hi else lo))

@pytest.mark.parametrize("card", _card_paths(), ids=lambda p: os.path.basename(p))
def test_card_conforms(card):
    fm, body = _split(card)
    pid = fm["playbook"]
    assert fm["name"] == f"{pid}-compute", "命名律：name == <playbook>-compute"
    assert os.path.basename(card) == f"{pid}-compute.md", "文件名 == name.md"
    mode = fm["mode"]
    assert mode in {"producer", "compute", "compute-fine"}
    tools = fm.get("tools") or []
    assert "AskUserQuestion" not in tools, "工具锁死：卡片不得含 AskUserQuestion"

    pb_fm = ec.load_frontmatter(ec.find_playbook(pid))
    stages = pb_fm["stages"]
    by_id = {str(s["id"]): s for s in stages}

    if mode == "producer":
        assert fm.get("produces") in PRODUCTS, "producer 必须声明已知产物"
        assert not any(s.get("pause_after") for s in stages), "producer 的 playbook 不应有 pause_after"
    elif mode == "compute":
        lo, hi = _stage_range(fm["compute_stages"])
        for sid in range(lo, hi + 1):
            assert by_id[str(sid)].get("subagent_ok") is True, f"compute 区间 stage {sid} 必须 subagent_ok:true"
        assert any(by_id[str(s)].get("pause_after") for s in range(lo, hi + 1)), "compute 区间须含 pause_after"
        if fm.get("produces"):
            assert fm["produces"] in PRODUCTS
    else:  # compute-fine
        assert not any(s.get("subagent_ok") for s in stages), "compute-fine 的 playbook 不应有 subagent_ok:true 阶段"
        assert str(fm.get("compute_stages")) == "scripts"

    body_lines = [ln for ln in body.splitlines() if ln.strip()]
    assert len(body_lines) <= BODY_LINE_BUDGET, f"薄卡：正文 {len(body_lines)} 行 > {BODY_LINE_BUDGET}"
    for bad in FORBIDDEN_BODY:
        assert bad not in body, f"卡片不得复述菜谱（命中 {bad!r}），须指向 playbook.md"
    for sec in SIX_SECTIONS:
        assert sec in body, f"缺六节之一：{sec}"
    assert "COMPUTE_DONE" in body and "NEED_INFO" in body, "输出契约节须含状态字"
    assert f"playbooks/{pid}/playbook.md" in body, "步骤须指向对应 playbook.md"
