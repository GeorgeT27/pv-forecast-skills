"""build_index golden:只索引实际产物、按类别分节、适用问题+关键描述符摘录、
未识别 json 单列不归组、无 PNG 如实标注。"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

import build_index as bi  # noqa: E402


def _mk(tmp_path, rid, stats, png=True):
    (tmp_path / f"{rid}.json").write_text(
        json.dumps(stats, ensure_ascii=False), encoding="utf-8")
    if png:
        (tmp_path / f"{rid}.png").write_bytes(b"\x89PNG\r\n")


def test_groups_by_category_and_excludes_unplotted(tmp_path):
    _mk(tmp_path, "true-vs-pred-scatter",
        {"recipe": "true-vs-pred-scatter", "note": "x",
         "models": {"A": {"slope": 0.8, "r2": 0.99}}})
    _mk(tmp_path, "worst-points", {"recipe": "worst-points", "top_n": 20})
    text = bi.build(tmp_path)
    assert "## error-structure" in text
    assert "## sample-contrast" in text
    assert "## attribution" not in text            # 没画的类别不留空位
    assert "### true-vs-pred-scatter" in text
    assert "![true-vs-pred-scatter](true-vs-pred-scatter.png)" in text
    assert "适用问题" in text                        # recipe frontmatter 摘录
    assert "top_n=20" in text                       # 顶层标量描述符
    assert "slope=0.8" in text                      # 顶层无标量时下钻 models


def test_unknown_json_listed_not_grouped(tmp_path):
    _mk(tmp_path, "true-vs-pred-scatter",
        {"recipe": "true-vs-pred-scatter", "models": {"A": {"slope": 1.0}}})
    _mk(tmp_path, "my-adhoc-analysis", {"whatever": 1})
    text = bi.build(tmp_path)
    assert "未识别产物" in text
    assert "my-adhoc-analysis.json" in text
    assert "### my-adhoc-analysis" not in text


def test_missing_png_noted(tmp_path):
    _mk(tmp_path, "worst-points", {"recipe": "worst-points", "top_n": 5},
        png=False)
    text = bi.build(tmp_path)
    assert "无 PNG" in text


def test_main_writes_index(tmp_path):
    _mk(tmp_path, "worst-points", {"recipe": "worst-points", "top_n": 5})
    bi.main(["--charts-dir", str(tmp_path)])
    assert (tmp_path / "INDEX.md").exists()
    assert "worst-points" in (tmp_path / "INDEX.md").read_text(encoding="utf-8")
