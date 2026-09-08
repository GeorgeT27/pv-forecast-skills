"""路由漂移守卫（非模拟路由器——语义路由由 Claude 做，这里只锁 description 契约）。

Task 11 前：四类技能共存（已固化代理 > 三个专用技能 > 引擎兜底），本文件曾同时守
引擎 SKILL.md 与四个 pv-* 专用技能各自的 description/让位条款。Task 11 起四个 pv-*
技能壳（pv-result-analysis/pv-station-influence/pv-model-analysis/pv-feature-blame）
已删除，方法全部下沉本引擎的 playbook（result-eval/subset-influence/model-audit/
feature-importance）——原先逐技能 description 的存在性/触发短语/让位条款测试随技能
目录一起失去测试对象，已随本次删壳移除（不是精简，是测试对象不存在了）。保留的测试
只锁引擎自己 SKILL.md 的 description 与路由表内容，这是删壳后唯一还站得住的锚点；
四技能间的路由优先级契约现由 test_layering.py 的 provider_playbook 声明式守卫接管。

Task 12：单入口化。description 的「负面清单」与 pv-* 让位条款已删除（不再有让位对象），
路由优先级由三级（固化代理 > 专用技能 > 引擎兜底）收成两级（固化代理 > 本引擎）。本文件
新增断言锁住这两点，并把 10 个 playbook（含新并入的 result-eval/model-audit/subset-influence）
都纳入 description 与路由表的存在性检查——防止收编回归、防止 SKILL.md 再长回 pv-* 负面清单。
"""
import os
import re

ENGINE_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

ALL_PLAYBOOK_IDS = (
    "training-sufficiency", "robustness", "feature-importance",
    "model-comparison", "architecture-attribution", "deployment-drift", "fact-scan",
    "model-audit", "result-eval", "subset-influence", "data-setup",
    "metric-eval", "model-improve",
)


def description_of(skill_dir):
    text = open(os.path.join(skill_dir, "SKILL.md"), encoding="utf-8").read()
    m = re.search(r"^description:\s*(.+?)^---", text, re.S | re.M)
    assert m, f"{skill_dir}/SKILL.md 解析不到 description"
    return m.group(1)


def test_engine_keeps_trigger_phrases():
    d = description_of(ENGINE_DIR)
    for phrase in ("训练是否充分", "batch 不足", "loss 震荡", "稳不稳", "影响最大",
                   "模型对比归因", "不要结论", "上线后", "退化"):
        assert phrase in d, f"引擎 description 丢了触发短语「{phrase}」"


def test_engine_routes_model_comparison_and_fact_scan():
    """SKILL.md 路由表（不只 description）要点名两个新 playbook 的触发短语。"""
    text = open(os.path.join(ENGINE_DIR, "SKILL.md"), encoding="utf-8").read()
    assert "模型对比归因" in text
    assert "体检" in text
    assert "不要结论" in text
    assert "model-comparison" in text
    assert "fact-scan" in text


def test_engine_routes_deployment_drift():
    """路由表要点名 deployment-drift 的触发短语（上线后退化/从何时开始变差）。"""
    text = open(os.path.join(ENGINE_DIR, "SKILL.md"), encoding="utf-8").read()
    assert "deployment-drift" in text
    assert "退化" in text


def test_description_is_triggers_only_and_short():
    """description 只留触发短语：≤350 字符、不含 playbook id、不含括号枚举——skill 列表预算 = 上下文 1%，
    超出时最少使用的 skill 会被丢出列表；路由表在正文（test_skill_md_line_budget_and_full_playbook_coverage 守）。"""
    d = description_of(ENGINE_DIR).strip()
    assert len(d) <= 350, f"description {len(d)} 字符 > 350"
    leaked = [pid for pid in ALL_PLAYBOOK_IDS if pid in d]
    assert not leaked, f"description 不应枚举 playbook id：{leaked}"


def test_engine_description_has_no_negative_list_or_pvstar_deferral():
    """负面清单与 pv-* 让位条款已随单入口化删除——不应再出现在 description 里。"""
    d = description_of(ENGINE_DIR)
    for stale in ("负面清单", "pv-result-analysis", "pv-station-influence",
                  "pv-model-analysis", "pv-feature-blame"):
        assert stale not in d, f"引擎 description 残留旧让位条款文案「{stale}」"


def test_routing_priority_is_two_level():
    """路由优先级节已从三级收成两级：固化代理技能 > 本引擎；不应再提「专用技能」分级。"""
    text = open(os.path.join(ENGINE_DIR, "SKILL.md"), encoding="utf-8").read()
    assert "两级" in text
    assert "专用技能" not in text, "路由优先级仍残留三级措辞（专用技能一档）"


def test_skill_md_line_budget_and_full_playbook_coverage():
    """SKILL.md ≤60 行（与 test_layering 的预算口径一致），且路由表覆盖全部 12 个 playbook。"""
    path = os.path.join(ENGINE_DIR, "SKILL.md")
    lines = open(path, encoding="utf-8").read().splitlines()
    assert len(lines) <= 60, f"SKILL.md {len(lines)} 行 > 60 行预算"
    text = "\n".join(lines)
    missing = [pid for pid in ALL_PLAYBOOK_IDS if pid not in text]
    assert not missing, f"路由表缺 playbook：{missing}"
