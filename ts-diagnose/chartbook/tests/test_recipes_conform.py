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
from engine_common import MATERIAL_IDS  # noqa: E402

REQUIRED_KEYS = ("id", "needs_materials", "适用问题", "outputs",
                 "json_schema", "bridge_hooks", "验证步")


def parse_recipe(text):
    m = re.match(r"^---\n(.*?)\n---\n(.*)$", text, re.S)
    assert m, "recipe 必须以 YAML frontmatter 开头"
    return yaml.safe_load(m.group(1)), m.group(2)


def check_recipe(path: Path):
    fm, body = parse_recipe(path.read_text())
    for k in REQUIRED_KEYS:
        assert k in fm, f"{path.name} 缺 frontmatter 键 {k}"
    assert fm["id"] == path.stem, f"{path.name} id 与文件名不一致"
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
    bad.write_text("---\nid: bad-recipe\nneeds_materials: [不存在的材料]\n"
                   "适用问题: x\noutputs:\n  json: bad-recipe.json\n"
                   "  png: bad-recipe.png\njson_schema: x\nbridge_hooks: x\n"
                   "验证步: x\n---\n## 判读\n")
    with pytest.raises(AssertionError, match="needs_materials"):
        check_recipe(bad)
