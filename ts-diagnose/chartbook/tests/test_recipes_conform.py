"""全部 recipes/*.md 过 _recipe-spec 规范校验（Task 1 时 recipes 为空=空转；
后续任务每加一个 recipe 自动被闸）。同时用 tmp fixture 验证校验器本身有牙。"""
import re
import sys
from pathlib import Path

import pytest
import yaml

CHARTBOOK = Path(__file__).resolve().parents[1]
ENGINE_SCRIPTS = CHARTBOOK.parent / "scripts"
sys.path.insert(0, str(ENGINE_SCRIPTS))
from engine_common import MATERIAL_IDS, CATEGORY_IDS  # noqa: E402

REQUIRED_KEYS = ("id", "needs_materials", "适用问题", "outputs",
                 "json_schema", "bridge_hooks", "验证步", "category")


def parse_recipe(text):
    m = re.match(r"^---\n(.*?)\n---\n(.*)$", text, re.S)
    assert m, "recipe 必须以 YAML frontmatter 开头"
    return yaml.safe_load(m.group(1)), m.group(2)


def check_recipe(path: Path):
    fm, body = parse_recipe(path.read_text())
    for k in REQUIRED_KEYS:
        assert k in fm, f"{path.name} 缺 frontmatter 键 {k}"
    assert fm["id"] == path.stem, f"{path.name} id 与文件名不一致"
    assert fm["category"] in CATEGORY_IDS, \
        f"{path.name} category 非法: {fm.get('category')}(合法集 {CATEGORY_IDS})"
    DOMAIN_WORDS = ("weather", "station", "solar", "irradiance")
    hit = [w for w in DOMAIN_WORDS if w in fm["id"]]
    assert not hit, f"{path.name} id 含领域名词 {hit}(领域中立纪律见 _recipe-spec §5.6)"
    m2 = re.match(r"^---\n(.*?)\n---", path.read_text(), re.S)
    fm_raw = m2.group(1) if m2 else ""
    hit_fm = [w for w in DOMAIN_WORDS + ("pv",)
              if re.search(rf"(?i)\b{w}\b", fm_raw)]
    assert not hit_fm, \
        f"{path.name} frontmatter 含领域名词 {hit_fm}(领域中立纪律 §5.6,不限于 id)"
    mats = fm["needs_materials"]
    assert mats and set(mats) <= set(MATERIAL_IDS), \
        f"{path.name} needs_materials 非法: {mats}"
    assert fm["outputs"]["json"] == f"{fm['id']}.json"
    assert fm["outputs"]["png"] == f"{fm['id']}.png"
    assert "## 判读" in body, f"{path.name} 缺 ## 判读 节"
    script = CHARTBOOK / "scripts" / f"chart_{fm['id'].replace('-', '_')}.py"
    assert script.exists(), f"{path.name} 对应脚本 {script.name} 不存在"


def all_recipes():
    return sorted((CHARTBOOK / "recipes").glob("*.md")) \
        if (CHARTBOOK / "recipes").is_dir() else []


@pytest.mark.parametrize("path", all_recipes(),
                         ids=lambda p: p.stem if hasattr(p, "stem") else str(p))
def test_recipe_conforms(path):
    check_recipe(path)


def test_recipe_checker_has_teeth(tmp_path):
    bad = tmp_path / "bad-recipe.md"
    bad.write_text("---\nid: bad-recipe\ncategory: error-structure\nneeds_materials: [不存在的材料]\n"
                   "适用问题: x\noutputs:\n  json: bad-recipe.json\n"
                   "  png: bad-recipe.png\njson_schema: x\nbridge_hooks: x\n"
                   "验证步: x\n---\n## 判读\n")
    with pytest.raises(AssertionError, match="needs_materials"):
        check_recipe(bad)


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


def test_recipe_checker_rejects_domain_word_in_frontmatter(tmp_path):
    bad = tmp_path / "ok-id.md"
    bad.write_text("---\nid: ok-id\ncategory: input-side\n"
                   "needs_materials: [predict]\n适用问题: x\noutputs:\n"
                   "  json: ok-id.json\n  png: ok-id.png\njson_schema: x\n"
                   "bridge_hooks: solar 辐照坏了\n验证步: x\n---\n## 判读\n")
    with pytest.raises(AssertionError, match="frontmatter 含领域名词"):
        check_recipe(bad)
