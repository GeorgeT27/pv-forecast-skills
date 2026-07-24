"""三层渐进加载守卫（硬不变量一：引擎常驻 token 有上限）。

Layer 0 = SKILL.md 纯路由层：命中任何 playbook 之前，进上下文的 ts-diagnose 内容
只有它。加载是静态文件，所以探针 = 直接度量 SKILL.md 并断言它不指示命中前加载
其他文件、不内联任何 playbook 方法内容——超预算/越界即 fail，防引擎重新长成单体。
"""
import glob
import os
import re
import sys
import tempfile

SCRIPTS_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, SCRIPTS_DIR)
import engine_common as ec  # noqa: E402

ENGINE_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
SKILL_PATH = os.path.join(ENGINE_DIR, "SKILL.md")

# 动态发现（弱模型压力测试 G-2：硬编码元组会让新 playbook 静默脱离本文件全部守卫）。
# MIN_PLAYBOOK_IDS 只作下限断言——防目录被误删；新增 playbook 自动进守卫，无需改这里。
MIN_PLAYBOOK_IDS = frozenset(
    ("training-sufficiency", "robustness", "feature-importance",
     "model-comparison", "fact-scan"))
PLAYBOOK_IDS = tuple(sorted(
    os.path.basename(os.path.dirname(p))
    for p in glob.glob(os.path.join(ENGINE_DIR, "playbooks", "*", "playbook.md"))
    if not os.path.basename(os.path.dirname(p)).startswith("_")))


def test_playbook_discovery_covers_min_set():
    missing = MIN_PLAYBOOK_IDS - set(PLAYBOOK_IDS)
    assert not missing, f"playbooks/ 目录缺已知 playbook：{sorted(missing)}"

LINE_BUDGET = 60
TOKEN_BUDGET = 6000

# playbook 方法词表：任何一个出现在 Layer 0 = 分析逻辑上浮，违反三层边界
METHOD_VOCAB = (
    "final_loss", "conv_slope", "plateau", "marginal_gain",
    "岭回归", "ridge", "中心化", "sum-to-zero", "四象限",
    "Wilcoxon", "wilcoxon", "Spearman", "spearman", "permutation", "KS 检验",
    # 阶段机制词汇也不属于路由层（属于 engine-core / playbook / spec）
    "Stage", "done_when", "pause_after", "evidence_lines", "findings_marker",
)


def _read(path):
    with open(path, encoding="utf-8") as f:
        return f.read()


def estimate_tokens(text):
    """粗估：CJK 字符 ≈ 1 token/字，其余按 4 字符/token。够守预算即可。"""
    cjk = sum(1 for ch in text if 0x2E80 <= ord(ch) <= 0x9FFF or 0xFF00 <= ord(ch) <= 0xFFEF)
    other = len(text) - cjk
    return cjk + other / 4


def prehit_payload(playbook_id):
    """命中 playbook_id 之前必然加载的 ts-diagnose 内容。三层结构下恒 = SKILL.md。"""
    assert playbook_id in PLAYBOOK_IDS
    return _read(SKILL_PATH)


def test_layer0_line_budget():
    n = len(_read(SKILL_PATH).splitlines())
    assert n <= LINE_BUDGET, f"SKILL.md {n} 行 > 预算 {LINE_BUDGET}——把内容下沉 engine-core/playbook"


def test_layer0_token_budget():
    t = estimate_tokens(_read(SKILL_PATH))
    assert t <= TOKEN_BUDGET, f"SKILL.md 估算 {t:.0f} token > 预算 {TOKEN_BUDGET}"


def test_probe_identical_across_playbooks():
    """三次探针（每 playbook 一次）的命中前负载必须完全相同——证明加载的是路由层而非全量。"""
    payloads = {pid: prehit_payload(pid) for pid in PLAYBOOK_IDS}
    assert len(set(payloads.values())) == 1


def test_layer0_no_method_vocab():
    text = _read(SKILL_PATH)
    hits = [w for w in METHOD_VOCAB if w in text]
    assert not hits, f"Layer 0 出现 playbook/机制方法词汇 {hits}——下沉到 engine-core 或 playbook"


def test_layer0_only_posthit_references():
    """SKILL.md 允许指向的 references/ 文件只有命中后加载的两个入口。"""
    refs = set(re.findall(r"references/([\w\-.]+\.md)", _read(SKILL_PATH)))
    assert refs <= {"engine-core.md", "crystallize.md"}, f"路由层引用越界：{refs}"


def test_layer0_routes_every_playbook():
    """路由表覆盖全部 playbook，且以目录路径转发（Layer 1 独立目录）。"""
    text = _read(SKILL_PATH)
    for pid in PLAYBOOK_IDS:
        assert pid in text, f"路由表缺 {pid}"
    assert "playbooks/<id>/playbook.md" in text
    assert os.path.exists(os.path.join(ENGINE_DIR, "references", "engine-core.md"))


# model-audit 是跨 playbook 共享的档案供应方（`contexts[].provider_playbook` 机制 +
# engine_common.modelmap_blocker 全局阻塞，见 3b0ed11）：一个 playbook 若在自己的
# frontmatter `contexts[]` 里显式声明某 id 为 provider_playbook，它以该 id 引用对方
# 触发嵌入执行提示——这不是方法内容内联，是引擎既定的 provider 接线，按共享库豁免，
# 而非 Layer 1 独立性违例。豁免按「声明」颗粒度收窄：只有 a 自己声明了 b 为
# provider_playbook，a 全文提及 b 才合法；未声明的 playbook 提及任何其他 id 一律 0 次
# ——防止未来 playbook 把 model-audit（或任何 provider）的说明文字贴进正文却不声明
# provider 关系，从而绕过本守卫（见 fix round 1 报告）。
def _declared_providers(playbook_path):
    """读取 playbook frontmatter 的 contexts[].provider_playbook 声明集合。"""
    fm = ec.load_frontmatter(playbook_path)
    return frozenset(
        ctx["provider_playbook"]
        for ctx in (fm.get("contexts") or [])
        if isinstance(ctx, dict) and ctx.get("provider_playbook"))


def _assert_no_undeclared_cross_reference(a, text, providers, b):
    """独立性守卫的单点判据：b 只有在 a 声明它为 provider 时才允许出现在 a 的正文里。"""
    if b in providers:
        return
    assert b not in text, f"playbook {a} 内联引用了 {b}（未在 contexts[] 声明为 provider）"


def test_layer1_guard_rejects_undeclared_provider_mention():
    """RED 探针：一个不声明 model-audit 为 provider 的 playbook 正文提到 model-audit，
    必须被判违例——证明「id 出现在共享供应方集合里就整份豁免」的旧规则有洞
    （字符串"model-audit"可以因任何理由出现在正文任何位置而不被拦截）。"""
    fm_text = (
        "---\n"
        "id: decoy\n"
        "name: 诱饵 playbook\n"
        "goal: 验证守卫\n"
        "stages:\n"
        "  - id: 0\n"
        "    name: 占位阶段\n"
        "    done_when:\n"
        "      manual: true\n"
        "---\n"
        "\n"
        "# decoy\n"
        "\n"
        "本 playbook 没有在 contexts[] 里把 model-audit 声明为 provider_playbook，"
        "但正文这里贴了一段提到 model-audit 的说明文字（模拟未来误粘贴）。\n")
    with tempfile.TemporaryDirectory() as td:
        path = os.path.join(td, "playbook.md")
        with open(path, "w", encoding="utf-8") as f:
            f.write(fm_text)
        providers = _declared_providers(path)
        text = _read(path)
        assert "model-audit" not in providers  # 前提：确未声明
        try:
            _assert_no_undeclared_cross_reference("decoy", text, providers, "model-audit")
        except AssertionError:
            return  # 期望：未声明的引用必须被拦截
        raise AssertionError("守卫应拦截未声明 provider 的跨 playbook 引用，但放行了")


def test_layer1_playbooks_independent():
    """全部 playbook 之间零共享内联：互不引用对方 id（动态发现，新增自动纳管），
    但仅当 a 在自己 frontmatter 的 contexts[] 里把 b 声明为 provider_playbook 时，
    a 才允许在正文提及 b（见上，颗粒度=每个 playbook 自己声明了什么，而非固定豁免表）。
    """
    for a in PLAYBOOK_IDS:
        path = os.path.join(ENGINE_DIR, "playbooks", a, "playbook.md")
        text = _read(path)
        providers = _declared_providers(path)
        for b in PLAYBOOK_IDS:
            if a != b:
                _assert_no_undeclared_cross_reference(a, text, providers, b)


def test_chartbook_scripts_no_cross_skill_imports():
    """chartbook 是引擎级共享库：脚本不得引用 playbook 或任何专用技能目录。"""
    import glob
    forbidden = ("pv-result-analysis", "pv_result_analysis",
                 "pv-feature-blame", "pv-station-influence",
                 "pv-model-analysis", "playbooks/")
    scripts = (glob.glob(os.path.join(ENGINE_DIR, "chartbook", "scripts", "*.py"))
               + glob.glob(os.path.join(ENGINE_DIR, "chartbook", "recipes", "*.md"))
               + glob.glob(os.path.join(ENGINE_DIR, "chartbook", "tests", "*.py")))
    assert scripts, "chartbook/{scripts,recipes,tests} 不应为空"
    for path in scripts:
        text = open(path, encoding="utf-8").read()
        for bad in forbidden:
            assert bad not in text, f"{os.path.basename(path)} 引用了 {bad}"


def test_chartbook_recipes_have_scripts():
    """每个 recipe 必有同名预写脚本（chart_<蛇形id>.py）。"""
    import glob
    recipes = glob.glob(os.path.join(ENGINE_DIR, "chartbook", "recipes", "*.md"))
    assert len(recipes) >= 9, "A-C 组 9 个 recipe 应已就位"
    for path in recipes:
        rid = os.path.splitext(os.path.basename(path))[0]
        script = os.path.join(ENGINE_DIR, "chartbook", "scripts",
                              f"chart_{rid.replace('-', '_')}.py")
        assert os.path.exists(script), f"recipe {rid} 缺预写脚本"
