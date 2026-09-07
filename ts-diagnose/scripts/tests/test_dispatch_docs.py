import glob, os
ENGINE_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
REF = os.path.join(ENGINE_DIR, "references")


def _read(name):
    return open(os.path.join(REF, name), encoding="utf-8").read()


def _card_names():
    return sorted(os.path.splitext(os.path.basename(p))[0]
                  for p in glob.glob(os.path.join(ENGINE_DIR, "agents", "*.md"))
                  if not os.path.basename(p).startswith("_"))


def test_engine_core_dispatches_by_card_name_with_fallback():
    t = _read("engine-core.md")
    assert "agents/" in t and "-compute" in t
    assert "general-purpose" in t, "须写明卡片未注册时的回退：卡片全文作 prompt 派 general-purpose"
    for stale in ("Brief-COMPUTE", "Brief-PRODUCER", "Brief-FACT"):
        assert stale not in t, f"engine-core 仍引用已删除的模板 {stale}"


def test_subagent_briefs_indexes_every_card():
    t = _read("subagent-briefs.md")
    for name in _card_names():
        assert name in t, f"subagent-briefs.md 卡片索引缺 {name}"
    assert "NEED_INFO" in t and "general-purpose" in t
    for stale in ("## Brief-COMPUTE", "## Brief-PRODUCER", "## Brief-FACT"):
        assert stale not in t


def test_batch_phase_c_uses_cards():
    t = _read("batch-orchestration.md")
    assert "Brief-BATCH-COMPUTE" not in t
    assert "-compute" in t


def test_playbooks_and_batch_have_no_stale_brief_templates():
    stale = ("Brief-COMPUTE", "Brief-PRODUCER", "Brief-FACT", "Brief-BATCH")
    paths = glob.glob(os.path.join(ENGINE_DIR, "playbooks", "**", "*.md"), recursive=True)
    paths.append(os.path.join(ENGINE_DIR, "scripts", "batch.py"))
    hits = [(p, s) for p in paths for s in stale
            if s in open(p, encoding="utf-8").read()]
    assert not hits, f"已删除的 Brief 模板仍被引用：{hits}"


def test_playbooks_have_no_brief_era_dispatch_wording():
    """brief 模板已删：playbook 不得再教「brief 写法」，也不得指向单数 subagent-brief.md。"""
    stale = ("brief 写法见", "subagent-brief.md")
    hits = [(os.path.relpath(p, ENGINE_DIR), s)
            for p in glob.glob(os.path.join(ENGINE_DIR, "playbooks", "**", "*.md"), recursive=True)
            for s in stale if s in open(p, encoding="utf-8").read()]
    assert not hits, f"playbook 仍是 brief 时代措辞：{hits}"


def test_dispatching_playbooks_name_their_own_card():
    """派发段必须按名字派卡，而不是泛指「一个子代理」。"""
    expect = {"model-comparison": "model-comparison-compute",
              "deployment-drift": "deployment-drift-compute",
              "fact-scan": "fact-scan-compute",
              "robustness": "robustness-compute",
              "feature-importance": "feature-importance-compute",
              "architecture-attribution": "architecture-attribution-worker"}
    for pid, card in expect.items():
        t = open(os.path.join(ENGINE_DIR, "playbooks", pid, "playbook.md"), encoding="utf-8").read()
        assert card in t, f"{pid}/playbook.md 的派发段未按名字点出 {card}"
