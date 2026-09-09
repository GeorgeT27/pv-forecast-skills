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


def test_out_writes_root_index_with_relative_png_links(tmp_path):
    """全链路联调 F5：阶段闸判工作目录根部的 INDEX.md，图链接要带 charts/ 前缀。"""
    charts = tmp_path / "charts"
    charts.mkdir()
    _mk(charts, "worst-points", {"recipe": "worst-points", "top_n": 5})
    bi.main(["--charts-dir", str(charts), "--out", str(tmp_path / "INDEX.md")])
    text = (tmp_path / "INDEX.md").read_text(encoding="utf-8")
    assert "![worst-points](charts/worst-points.png)" in text
    assert not (charts / "INDEX.md").exists()   # --out 给了就只写 out，不再写图目录


def test_default_out_keeps_bare_png_links(tmp_path):
    _mk(tmp_path, "worst-points", {"recipe": "worst-points", "top_n": 5})
    bi.main(["--charts-dir", str(tmp_path)])
    assert "![worst-points](worst-points.png)" in (tmp_path / "INDEX.md").read_text(encoding="utf-8")


def test_out_outside_charts_tree_uses_absolute_links(tmp_path):
    """索引落在图目录之外的另一棵树时，用绝对路径而不是一长串 ../。"""
    charts = tmp_path / "case" / "charts"
    charts.mkdir(parents=True)
    _mk(charts, "worst-points", {"recipe": "worst-points", "top_n": 5})
    out = tmp_path / "elsewhere" / "INDEX.md"
    bi.main(["--charts-dir", str(charts), "--out", str(out)])
    text = out.read_text(encoding="utf-8")
    assert f"![worst-points]({charts.resolve()}/worst-points.png)" in text
    assert "../" not in text


# ---------------------------------------------- 现场脚本（chartbook 未覆盖）
def test_adhoc_chart_gets_own_group_with_tier(tmp_path):
    """声明了 verification 的非 recipe 产物 = 现场写的图，归自己那组、带 PNG 链接、
    标出验证档位——不是「未识别产物」。"""
    _mk(tmp_path, "volatility-strata",
        {"recipe": "volatility-strata", "metric": "mse_96", "n_strata": 4,
         "verification": {"tier": "reconcile-2", "passed": True}})
    text = bi.build(tmp_path)
    assert "## 现场脚本（chartbook 未覆盖）" in text
    assert "![volatility-strata](volatility-strata.png)" in text
    assert "验证档位: reconcile-2" in text
    assert "未识别产物" not in text


def test_adhoc_accepts_plain_string_verification(tmp_path):
    _mk(tmp_path, "my-chart", {"recipe": "my-chart", "verification": "chartbook-fn"})
    assert "验证档位: chartbook-fn" in bi.build(tmp_path)


def test_exploratory_tier_is_flagged_as_not_for_conclusion(tmp_path):
    """exploratory 档位必须在索引里就写明不进结论，别等写 CONCLUSION 时才想起来。"""
    _mk(tmp_path, "hunch-chart",
        {"recipe": "hunch-chart", "verification": {"tier": "exploratory"}})
    text = bi.build(tmp_path)
    assert "只作线索" in text and "CONCLUSION" in text


def test_json_without_verification_stays_unknown(tmp_path):
    _mk(tmp_path, "mystery", {"recipe": "mystery", "x": 1})
    text = bi.build(tmp_path)
    assert "未识别产物" in text and "mystery.json" in text
    assert "## 现场脚本" not in text


def test_plan_questions_annotate_both_groups(tmp_path):
    """chart_plan.json 在场时，chartbook 图与现场图都自动登记「服务疑问」；
    计划里的脚本名是蛇形、产物名是连字符，两边要能对上。"""
    charts = tmp_path / "charts"
    charts.mkdir()
    _mk(charts, "worst-points", {"recipe": "worst-points", "top_n": 20})
    _mk(charts, "volatility-strata",
        {"recipe": "volatility-strata", "verification": "reconcile-2"})
    (tmp_path / "chart_plan.json").write_text(json.dumps({"entries": [
        {"question": "最差的那些点长什么样", "evidence": "e",
         "recipe": "worst-points", "source": "chartbook"},
        {"question": "剧变窗口上差距是不是更大", "evidence": "e",
         "recipe": "analysis_scripts/volatility_strata.py", "source": "ad-hoc",
         "verification": "reconcile-2"},
    ]}, ensure_ascii=False), encoding="utf-8")
    text = bi.build(charts, out_path=str(tmp_path / "INDEX.md"))
    assert "服务疑问: 最差的那些点长什么样" in text
    assert "服务疑问: 剧变窗口上差距是不是更大" in text, "蛇形↔连字符没对上"


def test_no_plan_file_means_no_annotation(tmp_path):
    """sweep 模式的剧本没有计划文件，索引照旧不登记疑问，不报错。"""
    _mk(tmp_path, "worst-points", {"recipe": "worst-points", "top_n": 20})
    assert "服务疑问" not in bi.build(tmp_path)
