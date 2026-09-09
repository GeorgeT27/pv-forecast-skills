"""Stop 钩子守卫：拦「已出结论却没过闸」，放行「流水线中途的停顿」。

回归点（全链路联调 F1）：钩子过去按 cwd 下 mtime 最新的 diagnose_config.json 一律拦，
主 agent 在 pause_after 停顿汇报或等 subagent 回卡时被空拦 3 个回合。
"""
import hashlib
import json
import os
import subprocess
import sys

HOOK = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__)))), "hooks", "gate_guard.py")
sys.path.insert(0, os.path.dirname(HOOK))
import gate_guard as gg  # noqa: E402

CONCL = "# 结论\n## 模型结构依据\nH-1 ...\n"
MID = {"current_stage": "2", "stages": {"0": "done", "1": "done"},
       "produces_conclusion": True}
DONE = {"current_stage": "done", "stages": {"0": "done"},
        "produces_conclusion": True}


# 默认用真会产 CONCLUSION.md 的剧本：本文件多数用例测的是「该有结论却没过闸 → 拦」。
# 此前默认 model-comparison 是个错样例——它产账本不产结论，本就不该被拦（R2-7）。
def mk(d, *, playbook="result-eval", conclusion=None, receipt=None, state=None):
    d.mkdir(parents=True, exist_ok=True)
    (d / "diagnose_config.json").write_text(json.dumps({"playbook": playbook}), encoding="utf-8")
    if conclusion is not None:
        (d / "CONCLUSION.md").write_text(conclusion, encoding="utf-8")
    if receipt is not None:
        (d / "gate_reports").mkdir(exist_ok=True)
        (d / "gate_reports" / "conclusion_gate.json").write_text(json.dumps(receipt), encoding="utf-8")
    if state is not None:
        (d / "diagnose_state.json").write_text(json.dumps(state), encoding="utf-8")
    return d


def good_receipt(text=CONCL):
    return {"passed": True, "conclusion_sha256": hashlib.sha256(text.encode()).hexdigest()}


def test_selftest_passes():
    r = subprocess.run([sys.executable, HOOK, "--selftest"], capture_output=True, text=True)
    assert r.returncode == 0, r.stdout + r.stderr


def test_mid_pipeline_pause_is_not_blocked(tmp_path):
    """pause_after 停顿 / 等 subagent：有 config、没结论、阶段在中途 → 放行。"""
    wd = mk(tmp_path / "mc", state=MID)
    assert gg.block_reason(str(wd))[0] is False


def test_conclusion_without_receipt_is_blocked(tmp_path):
    wd = mk(tmp_path / "mc", conclusion=CONCL, state=MID)
    assert gg.block_reason(str(wd))[0] is True


def test_tampered_conclusion_is_blocked(tmp_path):
    wd = mk(tmp_path / "mc", conclusion=CONCL, receipt={"passed": True, "conclusion_sha256": "dead"},
            state=DONE)
    assert gg.block_reason(str(wd))[0] is True


def test_state_claims_done_without_receipt_is_blocked(tmp_path):
    wd = mk(tmp_path / "mc", state=DONE)
    assert gg.block_reason(str(wd))[0] is True


def test_missing_state_is_blocked(tmp_path):
    """没跑过 orient.py → 阶段状态不明，保守打回。"""
    wd = mk(tmp_path / "mc")
    assert gg.block_reason(str(wd))[0] is True


def test_producer_and_passed_gate_are_not_blocked(tmp_path):
    prod = mk(tmp_path / "setup", playbook="data-setup")
    assert gg.block_reason(str(prod))[0] is False
    ok = mk(tmp_path / "aa", conclusion=CONCL, receipt=good_receipt(), state=DONE)
    assert gg.block_reason(str(ok))[0] is False


def _run(cwd):
    return subprocess.run([sys.executable, HOOK], input=json.dumps({"cwd": str(cwd)}),
                          capture_output=True, text=True)


def test_finished_case_dir_does_not_block_a_running_one(tmp_path):
    """已过闸的旧工作目录（mtime 最新）不再替别人挡路；中途的目录也不拦。"""
    mk(tmp_path / "old", conclusion=CONCL, receipt=good_receipt(), state=DONE)
    mk(tmp_path / "cur", state=MID)
    os.utime(tmp_path / "old" / "diagnose_config.json", None)  # 让旧目录成为 mtime 最新
    r = _run(tmp_path)
    assert r.returncode == 0 and r.stdout.strip() == "", r.stdout


def test_hook_blocks_and_caps_at_three(tmp_path):
    wd = mk(tmp_path / "mc", conclusion=CONCL, state=MID)
    for _ in range(gg.CAP):
        r = _run(tmp_path)
        assert json.loads(r.stdout)["decision"] == "block"
    assert _run(tmp_path).stdout.strip() == ""  # 上限后放行，升级给人类
    assert (wd / "gate_reports" / ".stop_force_count").exists()



# ------------------------------------- R2-7：该不该有结论，看 frontmatter 不看名单
def test_generator_playbook_not_blocked_when_done(tmp_path):
    """model-comparison / fact-scan 产账本与图集、结论交下游，阶段全完成本就没有
    CONCLUSION.md。硬编码的三人生产者名单漏掉它们，r2 联调里连拦三个回合。"""
    wd = mk(tmp_path / "mc", playbook="model-comparison",
            state={"current_stage": "done", "produces_conclusion": False})
    blocked, why = gg.block_reason(str(wd))
    assert blocked is False, why
    assert "不产 CONCLUSION.md" in why


def test_conclusion_playbook_still_blocked_when_done_without_receipt(tmp_path):
    """反面：真产结论的剧本同样状态必须照拦——别把闸放松了。"""
    wd = mk(tmp_path / "aa", playbook="architecture-attribution",
            state={"current_stage": "done", "produces_conclusion": True})
    blocked, why = gg.block_reason(str(wd))
    assert blocked is True and "没有合法结论 receipt" in why


def test_legacy_state_without_flag_falls_back_to_name_list(tmp_path):
    """旧工作目录的 state 没有 produces_conclusion 字段 → 退回兜底名单，不误拦。"""
    wd = mk(tmp_path / "fs", playbook="fact-scan",
            state={"current_stage": "done", "stages": {"0": "done"}})
    assert gg.block_reason(str(wd))[0] is False


def test_state_flag_wins_over_name_list(tmp_path):
    """事实优先于名单：名单里的剧本若 state 说它产结论，照拦。"""
    wd = mk(tmp_path / "x", playbook="fact-scan",
            state={"current_stage": "done", "produces_conclusion": True})
    assert gg.block_reason(str(wd))[0] is True


def test_fallback_list_agrees_with_real_playbooks():
    """守卫：兜底名单必须与 frontmatter 事实一致——剧本增删结论阶段时这里先红。"""
    import glob
    from pathlib import Path
    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    import engine_common as ec
    engine = Path(__file__).resolve().parents[2]
    for p in glob.glob(str(engine / "playbooks" / "*" / "playbook.md")):
        fm = ec.load_frontmatter(p)
        assert (fm["id"] in gg.PRODUCERS) != ec.produces_conclusion(fm), (
            f"{fm['id']}：兜底名单与 frontmatter 不一致")
