import os

ENGINE_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
PATH = os.path.join(ENGINE_DIR, "references", "engine-core.md")
BUDGET = 4200
MUST_KEEP = ("恒问五类", "不许用假设填补不确定", "禁机制语言", "单写者", "subagent 无提问权",
             "对账两关", "chartbook 豁免", "预算阶梯", "常见错误", "运行后回顾", "general-purpose",
             "post-hoc", "只报排名", "现象 / 假设 / 已证实 / 被推翻")


def _estimate(text):
    cjk = sum(1 for ch in text if 0x2E80 <= ord(ch) <= 0x9FFF or 0xFF00 <= ord(ch) <= 0xFFEF)
    return cjk + (len(text) - cjk) / 4


def test_engine_core_within_budget():
    t = _estimate(open(PATH, encoding="utf-8").read())
    assert t <= BUDGET, f"engine-core 估算 {t:.0f} token > {BUDGET}——orient 已打印的内容改成一行指针"


def test_engine_core_keeps_judgment_rules():
    text = open(PATH, encoding="utf-8").read()
    missing = [k for k in MUST_KEEP if k not in text]
    assert not missing, f"精简不得删除判断规则：{missing}"
