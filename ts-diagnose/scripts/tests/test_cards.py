import os, re, glob, sys
import yaml
import pytest

HERE = os.path.dirname(os.path.abspath(__file__))
SCRIPTS_DIR = os.path.dirname(HERE)                        # ts-diagnose/scripts
ENGINE_DIR = os.path.dirname(SCRIPTS_DIR)                  # ts-diagnose
AGENTS_DIR = os.path.join(ENGINE_DIR, "agents")
sys.path.insert(0, SCRIPTS_DIR)
import engine_common as ec  # noqa: E402

PRODUCTS = {"setup", "model_profile", "metric_table", "chart_sweep", "eval_report"}
BODY_LINE_BUDGET = 80
FORBIDDEN_BODY = ["## 逐阶段菜谱", "### Stage", "## 2. 逐阶段"]
SIX_SECTIONS = ["你是谁", "输入", "步骤", "红线", "输出契约", "停顿"]

def _card_paths():
    pats = ("*-compute.md", "*-worker.md", "*-baseline.md")
    return sorted(p for pat in pats for p in glob.glob(os.path.join(AGENTS_DIR, pat)))

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
    role = fm["name"].rsplit("-", 1)[1]
    assert role in {"compute", "worker", "baseline"}, "name 须以 -compute/-worker/-baseline 结尾"
    assert fm["name"] == f"{pid}-{role}", "命名律：name == <playbook>-<role>"
    assert os.path.basename(card) == f"{fm['name']}.md", "文件名 == name.md"
    mode = fm["mode"]
    assert mode in {"producer", "compute", "compute-fine", "worker"}
    assert (mode == "worker") == (role in {"worker", "baseline"}), "worker 模式与 -worker/-baseline 后缀一一对应"
    tools = fm.get("tools") or []
    assert "AskUserQuestion" not in tools, "工具锁死：卡片不得含 AskUserQuestion"

    pb_fm = ec.load_frontmatter(ec.find_playbook(pid))
    stages = pb_fm["stages"]
    by_id = {str(s["id"]): s for s in stages}

    # regression guard (commit 4eca085): evidence_lines ids must never be listed as up-front questions.
    # Cards keep evidence lines on a SEPARATE bullet, so only lines containing "已答问题" are checked.
    ev_ids = [e["id"] for e in (pb_fm.get("evidence_lines") or [])]
    for line in body.splitlines():
        if "已答问题" in line:
            for ev in ev_ids:
                assert not re.search(rf'(?<![\w-]){re.escape(ev)}(?![\w-])', line), (
                    f"{pid}: evidence_line id '{ev}' appears on a 已答问题 line — "
                    f"evidence lines must not be presented as up-front questions")

    if mode == "producer":
        assert fm.get("produces") in PRODUCTS, "producer 必须声明已知产物"
        assert not any(s.get("pause_after") for s in stages), "producer 的 playbook 不应有 pause_after"

        lo, hi = _stage_range(fm["compute_stages"])
        prod = pb_fm.get("produces") or {}
        targets = [prod.get("manifest")] + list(prod.get("marker_files") or [])
        targets = [t for t in targets if t]
        producing = sorted({int(s["id"]) for s in stages
                            if any(t in ((s.get("done_when") or {}).get("artifacts") or [])
                                   for t in targets)})
        if producing:
            assert hi == max(producing), (
                f"{pid}: producer compute_stages ends at stage {hi}, but the product "
                f"manifest/marker is finalized at stage {max(producing)}; the card must stop "
                f"at the product stage (later main-agent-only stages are not the card's)")
    elif mode == "compute":
        lo, hi = _stage_range(fm["compute_stages"])
        for sid in range(lo, hi + 1):
            assert by_id[str(sid)].get("subagent_ok") is True, f"compute 区间 stage {sid} 必须 subagent_ok:true"
        assert any(by_id[str(s)].get("pause_after") for s in range(lo, hi + 1)), "compute 区间须含 pause_after"
        if fm.get("produces"):
            assert fm["produces"] in PRODUCTS
            prod = pb_fm.get("produces") or {}
            targets = [prod.get("manifest")] + list(prod.get("marker_files") or [])
            targets = [t for t in targets if t]
            producing = sorted({int(s["id"]) for s in stages
                                if any(t in ((s.get("done_when") or {}).get("artifacts") or [])
                                       for t in targets)})
            if producing:
                assert all(lo <= sid <= hi for sid in producing), (
                    f"{pid}: produces manifest/marker written at stage(s) {producing}, "
                    f"outside compute range {lo}-{hi}")
    elif mode == "worker":
        assert str(fm.get("compute_stages")) == "scripts"
        served = fm.get("serves_stages") or []
        assert served, "worker 须声明 serves_stages"
        for sid in served:
            assert by_id[str(sid)].get("subagent_ok") is True, f"worker 服务的 stage {sid} 必须 subagent_ok:true"
        assert "receipt_line" in body, "worker 输出契约须含 receipt_line"
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
    if mode != "worker":
        assert '"verification"' in body, (
            "输出契约须回传 verification：区间内每个验证步/闸的名字+数字+过/不过，"
            "主 agent 据此记 PROGRESS.md（无验证记录的产出不可引用）")
    assert f"playbooks/{pid}/playbook.md" in body, "步骤须指向对应 playbook.md"
    assert '"<ENGINE>/scripts/orient.py"' in body, "步骤须用 <ENGINE> 绝对路径调 orient"
    assert "引擎目录：`<ENGINE>`" in body, "输入节须有引擎目录字段"
