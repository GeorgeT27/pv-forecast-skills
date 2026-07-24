"""路由漂移守卫（非模拟路由器——语义路由由 Claude 做，这里只锁 description 契约）。

Task 11 前：四类技能共存（已固化代理 > 三个专用技能 > 引擎兜底），本文件曾同时守
引擎 SKILL.md 与四个 pv-* 专用技能各自的 description/让位条款。Task 11 起四个 pv-*
技能壳（pv-result-analysis/pv-station-influence/pv-model-analysis/pv-feature-blame）
已删除，方法全部下沉本引擎的 playbook（result-eval/subset-influence/model-audit/
feature-importance）——原先逐技能 description 的存在性/触发短语/让位条款测试随技能
目录一起失去测试对象，已随本次删壳移除（不是精简，是测试对象不存在了）。保留的测试
只锁引擎自己 SKILL.md 的 description 与路由表内容，这是删壳后唯一还站得住的锚点；
四技能间的路由优先级契约现由 test_layering.py 的 provider_playbook 声明式守卫接管。
"""
import os
import re

ENGINE_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


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
