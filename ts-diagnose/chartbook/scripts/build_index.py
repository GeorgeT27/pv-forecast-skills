"""build_index:扫描 charts 目录的实际产物(<recipe-id>.json/.png),按类别
生成 INDEX.md——只索引画出来的图,不为没画的留空位(设计 spec §6/§8)。
PNG 保持平铺,归组只发生在本索引呈现层。"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

import yaml

CHARTBOOK = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(CHARTBOOK.parent / "scripts"))
from engine_common import CATEGORY_IDS  # noqa: E402


def recipe_meta(rid: str):
    """recipe frontmatter(dict);非 chartbook recipe 返回 None。"""
    p = CHARTBOOK / "recipes" / f"{rid}.md"
    if not p.exists():
        return None
    m = re.match(r"^---\n(.*?)\n---", p.read_text(encoding="utf-8"), re.S)
    return yaml.safe_load(m.group(1)) if m else None


def _scalars(d: dict, limit: int) -> list:
    out = []
    for k, v in d.items():
        if k in ("recipe", "note", "seed"):
            continue
        if isinstance(v, (bool, int, float, str)):
            out.append(f"{k}={v}")
        if len(out) >= limit:
            break
    return out


def key_descriptors(stats: dict, limit: int = 8) -> list:
    """JSON 顶层标量摘录;顶层没有标量时下钻 models 的第一个模型。"""
    out = _scalars(stats, limit)
    models = stats.get("models")
    if not out and isinstance(models, dict) and models:
        name, first = next(iter(models.items()))
        if isinstance(first, dict):
            out = [f"models[{name}].{s}" for s in _scalars(first, limit)]
    return out


def build(charts_dir: Path) -> str:
    charts_dir = Path(charts_dir)
    found, unknown = [], []
    for jp in sorted(charts_dir.glob("*.json")):
        rid = jp.stem
        meta = recipe_meta(rid)
        if meta is None:
            unknown.append(rid)
            continue
        stats = json.loads(jp.read_text(encoding="utf-8"))
        found.append((str(meta.get("category") or "uncategorized"), rid, meta,
                      stats, (charts_dir / f"{rid}.png").exists()))
    lines = ["# 图表索引（本次实际产物）", ""]
    if not found and not unknown:
        lines.append("（本目录无产物）")
    for cat in list(CATEGORY_IDS) + ["uncategorized"]:
        group = [f for f in found if f[0] == cat]
        if not group:
            continue
        lines += [f"## {cat}", ""]
        for _cat, rid, meta, stats, has_png in group:
            lines.append(f"### {rid}")
            q = str(meta.get("适用问题") or "").strip()
            if q:
                lines.append(f"适用问题: {q}")
            lines.append(f"![{rid}]({rid}.png)" if has_png
                         else "（无 PNG 产物,只有 JSON）")
            desc = key_descriptors(stats)
            if desc:
                lines.append("关键描述符: " + ", ".join(desc))
            lines.append("")
    if unknown:
        lines += ["## 未识别产物（非 chartbook recipe,不归组）", ""]
        lines += [f"- {r}.json" for r in unknown] + [""]
    return "\n".join(lines) + "\n"


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--charts-dir", required=True)
    a = ap.parse_args(argv)
    d = Path(a.charts_dir)
    (d / "INDEX.md").write_text(build(d), encoding="utf-8")
    print(f"INDEX.md written: {d / 'INDEX.md'}")


if __name__ == "__main__":
    main()
