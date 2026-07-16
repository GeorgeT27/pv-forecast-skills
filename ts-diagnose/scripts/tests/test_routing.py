"""路由漂移守卫（非模拟路由器——语义路由由 Claude 做，这里只锁 description 契约）。

四类技能共存的确定性优先级：已固化代理 > 三个专用技能 > 引擎兜底。
本测试断言各 SKILL.md 的 description 持续携带：核心触发短语（召回不丢）、
优先级/让位条款（新技能加入或措辞重写时不打架）。谁改掉了这些句子，谁在这里被抓。
"""
import os
import re

ENGINE_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
REPO_ROOT = os.path.dirname(ENGINE_DIR)

SKILLS = ("pv-result-analysis", "pv-station-influence", "pv-model-analysis", "pv-feature-blame")


def description_of(skill_dir):
    text = open(os.path.join(skill_dir, "SKILL.md"), encoding="utf-8").read()
    m = re.search(r"^description:\s*(.+?)^---", text, re.S | re.M)
    assert m, f"{skill_dir}/SKILL.md 解析不到 description"
    return m.group(1)


def test_engine_is_fallback_with_negative_list():
    d = description_of(ENGINE_DIR)
    assert "仅当无匹配的专用诊断技能或已固化代理技能时使用" in d
    for s in SKILLS:                       # 负面清单必须点名全部专用技能
        assert s in d, f"引擎负面清单丢了 {s}"
    assert "已固化代理技能" in d and "优先级最高" in d


def test_engine_keeps_trigger_phrases():
    d = description_of(ENGINE_DIR)
    for phrase in ("训练是否充分", "batch 不足", "loss 震荡", "稳不稳", "影响最大"):
        assert phrase in d, f"引擎 description 丢了触发短语「{phrase}」"


def test_specific_skills_declare_priority():
    for s in SKILLS:
        d = description_of(os.path.join(REPO_ROOT, s))
        assert "优先于泛化引擎 ts-diagnose" in d, f"{s} 缺优先级声明"
        assert "让位于覆盖同场景的已固化代理技能" in d, f"{s} 缺让位条款"


def test_specific_skills_keep_trigger_phrases():
    required = {
        "pv-result-analysis": ("结果评估", "准确率", "月度"),
        "pv-station-influence": ("拖累", "负迁移", "留出"),
        "pv-model-analysis": ("模型代码", "模型参考"),
        "pv-feature-blame": ("feature", "指标变差", "feature_true", "反事实"),
    }
    for s, phrases in required.items():
        d = description_of(os.path.join(REPO_ROOT, s))
        for p in phrases:
            assert p in d, f"{s} description 丢了触发短语「{p}」"


def test_overlap_case_station_influence_narrowed():
    """已知重叠 query（"为什么 chunk loss 震荡/收敛慢"）：专用技能靠收窄条款裁决——
    站点归因场景归 pv-station-influence，一般性训练充分性归引擎。"""
    d = description_of(os.path.join(REPO_ROOT, "pv-station-influence"))
    assert "训练动力学解释仅限「站点/条目影响力归因」场景" in d
    assert "ts-diagnose 的 training-sufficiency" in d


def test_overlap_case_feature_blame_narrowed():
    """已知重叠 query（"哪个变量对误差影响大"）：有 feature_true 对照的特征质量归因归
    pv-feature-blame，无对照的一般变量重要性归引擎 feature-importance。"""
    d = description_of(os.path.join(REPO_ROOT, "pv-feature-blame"))
    assert "无 feature_true 对照的一般变量重要性" in d
    assert "ts-diagnose 的 feature-importance" in d
    assert "绝不静默降级" in d              # feature_true 硬规则不许被改丢


def test_feature_blame_yields_to_result_analysis_scope():
    """pv-result-analysis 的让路句：特征质量归因场景指向 pv-feature-blame。"""
    d = description_of(os.path.join(REPO_ROOT, "pv-result-analysis"))
    assert "pv-feature-blame" in d
