# Chartbook 扩展 Plan 1/4:地基(category 归类 + CJK 渲染硬化)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 为 28 张图的扩展打地基——所有 recipe 获得机器可校验的 `category` 分类,CJK 字体渲染在全仓画图脚本上可靠。

**Architecture:** spec 见 `docs/superpowers/specs/2026-07-23-chartbook-expansion-design.md`。本计划只动:`engine_common.py`(加 CATEGORY_IDS)、14 个既有 recipe frontmatter、conform CI 测试、`chart_common.setup_font()` 硬化、两个缺字体配置的外围脚本、规范文档。**不加任何新图**(Plan 2/3)、不动 orient 呈现(Plan 4)。

**Tech Stack:** Python 3 / pytest / matplotlib / PyYAML。既有测试风格:合成数据、零网络、`Path(__file__)` 相对定位(cwd 无关)。

## Global Constraints

- 仓库根:`/Users/tqa946816/Documents/华为/光伏预测/结果分析skill`(下文相对路径均基于此)
- CATEGORY_IDS 六类,逐字:`("error-structure", "temporal-stability", "input-side", "model-comparison", "sample-contrast", "attribution")`
- recipe 领域中立硬纪律:id/字段不得含领域名词(英文黑名单 weather/station/solar/irradiance)
- 每 task 结束跑 `python3 -m pytest ts-diagnose/chartbook/tests/ ts-diagnose/scripts/tests/ -q` 全绿再 commit
- commit message 末尾带 `Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>`

---

### Task 1: CATEGORY_IDS + 14 recipe 归类 + conform 闸

**Files:**
- Modify: `ts-diagnose/scripts/engine_common.py`(MATERIAL_STATUSES 定义行之后,约 line 346)
- Modify: `ts-diagnose/chartbook/tests/test_recipes_conform.py`
- Modify: `ts-diagnose/chartbook/recipes/*.md`(全部 14 个,frontmatter 加一行)

**Interfaces:**
- Produces: `engine_common.CATEGORY_IDS: tuple[str, ...]`(Plan 2/3 新 recipe、Plan 4 orient 分组都消费它);recipe frontmatter 新必填键 `category`。

- [ ] **Step 1: 扩 conform 测试(先失败)**

`test_recipes_conform.py` 改三处。导入行:

```python
from engine_common import MATERIAL_IDS, CATEGORY_IDS  # noqa: E402
```

REQUIRED_KEYS 加 `category`:

```python
REQUIRED_KEYS = ("id", "needs_materials", "适用问题", "outputs",
                 "json_schema", "bridge_hooks", "验证步", "category")
```

`check_recipe()` 里 `assert fm["id"] == path.stem` 之后插入:

```python
    assert fm["category"] in CATEGORY_IDS, \
        f"{path.name} category 非法: {fm.get('category')}(合法集 {CATEGORY_IDS})"
    DOMAIN_WORDS = ("weather", "station", "solar", "irradiance")
    hit = [w for w in DOMAIN_WORDS if w in fm["id"]]
    assert not hit, f"{path.name} id 含领域名词 {hit}(领域中立纪律见 _recipe-spec §5.6)"
```

文件末尾加"有牙"测试:

```python
def test_recipe_checker_rejects_bad_category(tmp_path):
    bad = tmp_path / "bad-cat.md"
    bad.write_text("---\nid: bad-cat\ncategory: 不存在的类\n"
                   "needs_materials: [predict]\n适用问题: x\noutputs:\n"
                   "  json: bad-cat.json\n  png: bad-cat.png\njson_schema: x\n"
                   "bridge_hooks: x\n验证步: x\n---\n## 判读\n")
    with pytest.raises(AssertionError, match="category"):
        check_recipe(bad)


def test_recipe_checker_rejects_domain_word_id(tmp_path):
    bad = tmp_path / "weather-regime.md"
    bad.write_text("---\nid: weather-regime\ncategory: input-side\n"
                   "needs_materials: [predict]\n适用问题: x\noutputs:\n"
                   "  json: weather-regime.json\n  png: weather-regime.png\n"
                   "json_schema: x\nbridge_hooks: x\n验证步: x\n---\n## 判读\n")
    with pytest.raises(AssertionError, match="领域名词"):
        check_recipe(bad)
```

- [ ] **Step 2: 跑测试确认失败**

Run: `python3 -m pytest ts-diagnose/chartbook/tests/test_recipes_conform.py -q`
Expected: FAIL——先是 `ImportError: cannot import name 'CATEGORY_IDS'`。

- [ ] **Step 3: engine_common.py 加 CATEGORY_IDS**

在 `MATERIAL_STATUSES = (...)` 行之后加:

```python
# chartbook recipe 类别全集(呈现层归组;spec 2026-07-23 §6)。
# recipe frontmatter 的 category 必填且 ∈ 本集(test_recipes_conform 闸)。
CATEGORY_IDS = ("error-structure", "temporal-stability", "input-side",
                "model-comparison", "sample-contrast", "attribution")
```

- [ ] **Step 4: 再跑,确认 14 个 recipe 因缺 category 失败**

Run: `python3 -m pytest ts-diagnose/chartbook/tests/test_recipes_conform.py -q`
Expected: 14 个 `test_recipe_conforms[...]` FAIL,均为"缺 frontmatter 键 category";两个 teeth 测试 PASS。

- [ ] **Step 5: 14 个 recipe frontmatter 加 category**

每个文件在 `id: <...>` 行的下一行插入 `category: <值>`,指派表(逐字):

| recipe 文件 | category |
|---|---|
| error-breakdown.md | error-structure |
| horizon-degradation.md | error-structure |
| intraday-profile.md | error-structure |
| true-vs-pred-scatter.md | error-structure |
| rolling-stability.md | temporal-stability |
| cross-dim-stability.md | temporal-stability |
| train-test-drift.md | temporal-stability |
| y-vs-feature-mapping.md | temporal-stability |
| feature-error-conditional.md | input-side |
| feature-trend-overlay.md | input-side |
| model-error-correlation.md | model-comparison |
| oracle-gap.md | model-comparison |
| worst-slice-compare.md | model-comparison |
| worst-points.md | sample-contrast |

- [ ] **Step 6: 全量测试通过**

Run: `python3 -m pytest ts-diagnose/chartbook/tests/ ts-diagnose/scripts/tests/ -q`
Expected: 全 PASS(engine 侧 orient/charts_decl 测试不读 category,不受影响)。

- [ ] **Step 7: Commit**

```bash
git add ts-diagnose/scripts/engine_common.py ts-diagnose/chartbook/tests/test_recipes_conform.py ts-diagnose/chartbook/recipes/
git commit -m "feat(ts-diagnose): chartbook recipe 强制 category 归类(六类)+ id 领域名词闸

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```

---

### Task 2: setup_font 硬化 + 两个外围脚本 CJK 回填

**Files:**
- Modify: `ts-diagnose/chartbook/scripts/chart_common.py:27-33`(setup_font)
- Modify: `ts-diagnose/chartbook/tests/test_chart_common.py`(加一测试)
- Modify: `row-diagnostic/row_analysis.py:168-170`(matplotlib 导入块后插字体配置)
- Modify: `pv-feature-blame/scripts/analyze_row.py:177-179`(同上)

**Interfaces:**
- Produces: `chart_common.setup_font() -> list[str]`(返回命中的 CJK 字体列表,空列表=环境无 CJK;既有调用方只调用不接返回值,兼容)。Plan 2/3 所有新图脚本沿用 `setup_font()`。

**背景(调查结论,执行者不必复查):** chartbook 15 个脚本已全部调用 setup_font 且本机命中 Arial Unicode MS;中文方框来自 `row_analysis.py` 与 `analyze_row.py` 两个从未配置字体的脚本。原 setup_font 设单一 `font.family`,命中即断链无回退——硬化为 sans-serif 回退链。

- [ ] **Step 1: 写渲染测试(先失败)**

`test_chart_common.py` 文件末尾加:

```python
def test_setup_font_returns_hits_and_renders_cjk(tmp_path):
    """setup_font 返回命中字体列表;命中时渲染中文+负号必须无 missing-glyph 警告。"""
    import warnings
    import matplotlib.pyplot as plt
    hits = cc.setup_font()
    assert isinstance(hits, list)
    if not hits:
        pytest.skip("环境无 CJK 字体")
    assert plt.rcParams["font.family"] == ["sans-serif"]
    assert plt.rcParams["font.sans-serif"][:len(hits)] == hits
    fig, ax = plt.subplots()
    ax.set_title("中文标题")
    ax.plot([0, 1], [-1.5, 1.0])
    with warnings.catch_warnings(record=True) as rec:
        warnings.simplefilter("always")
        fig.savefig(tmp_path / "cjk.png")
    plt.close(fig)
    bad = [w for w in rec if "Glyph" in str(w.message) or "findfont" in str(w.message)]
    assert not bad, f"渲染出缺字形警告: {[str(w.message) for w in bad]}"
```

(测试文件里 chart_common 的既有导入别名以文件现状为准;若现状是 `import chart_common as cc` 则如上,否则对齐现状。)

- [ ] **Step 2: 跑测试确认失败**

Run: `python3 -m pytest ts-diagnose/chartbook/tests/test_chart_common.py -q`
Expected: 新测试 FAIL(`setup_font` 返回 None,`isinstance(hits, list)` 断言炸)。

- [ ] **Step 3: 硬化 setup_font**

`chart_common.py` 里整体替换 `setup_font` 函数为:

```python
CJK_FONTS = ("Arial Unicode MS", "PingFang SC", "Hiragino Sans GB", "Heiti TC",
             "SimHei", "Noto Sans CJK SC", "Microsoft YaHei")


def setup_font() -> list:
    """CJK 字体探测:命中项组成 sans-serif 回退链(单字体断链→回退链硬化)。
    返回命中列表;空列表 = 环境无 CJK,发一次警告但不炸图。"""
    installed = {f.name for f in matplotlib.font_manager.fontManager.ttflist}
    hits = [f for f in CJK_FONTS if f in installed]
    if hits:
        plt.rcParams["font.family"] = "sans-serif"
        plt.rcParams["font.sans-serif"] = hits + ["DejaVu Sans"]
    else:
        import warnings
        warnings.warn("未找到 CJK 字体,中文将渲染为方框;建议安装 Noto Sans CJK SC")
    plt.rcParams["axes.unicode_minus"] = False
    return hits
```

- [ ] **Step 4: 跑 chartbook 全部测试通过**

Run: `python3 -m pytest ts-diagnose/chartbook/tests/ -q`
Expected: 全 PASS(15 个图脚本走新回退链,golden 只断 JSON 不断 PNG 像素,不受影响)。

- [ ] **Step 5: 回填 row_analysis.py**

`row-diagnostic/row_analysis.py` 在 `import matplotlib.pyplot as plt`(line 170)之后插入:

```python
    import matplotlib.font_manager
    for _f in ("Arial Unicode MS", "PingFang SC", "Hiragino Sans GB", "Heiti TC",
               "SimHei", "Noto Sans CJK SC", "Microsoft YaHei"):
        if _f in {f.name for f in matplotlib.font_manager.fontManager.ttflist}:
            plt.rcParams["font.family"] = "sans-serif"
            plt.rcParams["font.sans-serif"] = [_f, "DejaVu Sans"]
            break
    plt.rcParams["axes.unicode_minus"] = False
```

(缩进对齐所在函数体;该文件是独立技能脚本,不 import ts-diagnose,块内代码自包含。)

- [ ] **Step 6: 回填 analyze_row.py**

`pv-feature-blame/scripts/analyze_row.py` 在 `import matplotlib.pyplot as plt`(line 179)之后插入与 Step 5 完全相同的代码块(同样对齐缩进)。

- [ ] **Step 7: 两技能自测跑通**

Run: `python3 -m pytest row-diagnostic/ pv-feature-blame/ -q 2>/dev/null; echo done`
Expected: 既有测试全 PASS(若某目录无 pytest 测试则跳过);另外冒烟:`python3 -c "import ast; ast.parse(open('row-diagnostic/row_analysis.py').read()); ast.parse(open('pv-feature-blame/scripts/analyze_row.py').read()); print('syntax ok')"` 输出 `syntax ok`。

- [ ] **Step 8: Commit**

```bash
git add ts-diagnose/chartbook/scripts/chart_common.py ts-diagnose/chartbook/tests/test_chart_common.py row-diagnostic/row_analysis.py pv-feature-blame/scripts/analyze_row.py
git commit -m "fix: CJK 字体渲染——setup_font 回退链硬化 + row_analysis/analyze_row 两脚本回填字体配置

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```

---

### Task 3: 规范与文档收口

**Files:**
- Modify: `ts-diagnose/chartbook/_recipe-spec.md`(frontmatter schema + 硬规则)
- Modify: `ts-diagnose/chartbook/recipes/intraday-profile.md`(适用性标注)
- Modify: `docs/superpowers/specs/2026-07-23-chartbook-expansion-design.md`(§4.5 按实情修订)
- Modify: `ts-diagnose/CHANGELOG.md`(记一条)

**Interfaces:**
- Consumes: Task 1 的 CATEGORY_IDS;Task 2 的 setup_font 现状。
- Produces: 规范文本(Plan 2/3 写新 recipe 时照此写 category 与领域中立)。

- [ ] **Step 1: _recipe-spec.md 两处编辑**

§3 frontmatter 示例块中 `id:` 行之后插入:

```yaml
category: error-structure          # 必填,∈ engine_common.CATEGORY_IDS
                                   #   (error-structure/temporal-stability/input-side/
                                   #    model-comparison/sample-contrast/attribution)
                                   #   呈现层按类归组(orient 选择门 + INDEX.md)
```

§5 硬规则末尾加第 6 条:

```markdown
6. **领域中立**:recipe 的 id/frontmatter 字段/图内标签/判读不得出现领域名词
   (天气/站点/光伏/医学等;id 英文黑名单 weather/station/solar/irradiance 由
   test_recipes_conform 闸)。领域语义只允许运行时经 intake 背景(data_profile)
   注入呈现层——如给聚类簇起领域名。周期性假设图(如 intraday-profile)须在
   recipe 内标注"周期性数据专用",orient 按 data_profile 判断适用。
```

- [ ] **Step 2: intraday-profile.md 标注**

正文"## 适用问题"节首行前加:

```markdown
> ⚠️ 周期性数据专用:本图假设序列存在日周期;无周期数据(如部分医学时序)不适用,
> orient/判读按 intake 的 data_profile 判断。
```

- [ ] **Step 3: 设计文档 §4.5 按实情修订**

`docs/superpowers/specs/2026-07-23-chartbook-expansion-design.md` 的 §4.5 整节替换为:

```markdown
## 4.5 中文渲染修复(跨切面,已按实情收窄)

实施时调查发现:chartbook 15 个脚本已全部调用 `chart_common.setup_font()`,
方框来自两个从未配置字体的外围脚本。实际修复(Plan 1 Task 2):

- `chart_common.setup_font()` 硬化:单字体 `font.family` → CJK 命中列表组成
  sans-serif 回退链 + 无 CJK 时警告不炸图 + 返回命中列表;新图脚本(Plan 2/3)
  沿用它,不再新建 mpl_style.py;
- 回填 `row-diagnostic/row_analysis.py` 与 `pv-feature-blame/scripts/analyze_row.py`;
- 测试:渲染中文+负号断言无 missing-glyph 警告(无 CJK 环境 skip)。
```

- [ ] **Step 4: CHANGELOG 记录**

`ts-diagnose/CHANGELOG.md` 在最新条目上方按现有条目的标题层级加一条,正文逐字:

```markdown
## 2026-07-23 chartbook 扩展第一轮:地基

- recipe frontmatter 强制 `category`(六类,engine_common.CATEGORY_IDS,conform CI 闸)
- id 领域名词闸(weather/station/solar/irradiance)+ 领域中立硬规则进 _recipe-spec §5.6
- `setup_font` 硬化为 CJK 回退链(返回命中列表);回填 row_analysis / analyze_row 两外围脚本
- 28 图扩展总设计:docs/superpowers/specs/2026-07-23-chartbook-expansion-design.md
```

- [ ] **Step 5: 全量测试 + Commit**

Run: `python3 -m pytest ts-diagnose/ -q`
Expected: 全 PASS。

```bash
git add ts-diagnose/chartbook/_recipe-spec.md ts-diagnose/chartbook/recipes/intraday-profile.md docs/superpowers/specs/2026-07-23-chartbook-expansion-design.md ts-diagnose/CHANGELOG.md
git commit -m "docs(ts-diagnose): 规范补 category 字段与领域中立硬规则;intraday-profile 周期性标注;spec §4.5 按实情收窄

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```

---

## 后续计划(本文件不含)

- **Plan 2/4**:纯数据 11 张(样本对比 2 + 误差结构 6 + 输入侧 1 + 模型对比 2 + 时间稳定 1),每张 = recipe + chart 脚本 + golden 测试,植入值按 spec §4;
- **Plan 3/4**:predict_adapter 契约(_recipe-spec §6)+ attribution_common(shap 双路选路/背景集元数据/成组置换/预算缓存)+ 归因 3 张 + 合成线性适配器 golden;
- **Plan 4/4**:orient 选择门按类分组呈现 + build_index.py(INDEX.md 只索引实际产物)+ true-vs-pred-scatter 加 Mincer-Zarnowitz + CHANGELOG 收口。

每个后续计划在前一个落地后基于真实代码撰写。
