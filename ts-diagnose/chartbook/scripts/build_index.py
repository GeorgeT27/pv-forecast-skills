"""build_index:扫描 charts 目录的实际产物(<recipe-id>.json/.png),按类别
生成 INDEX.md——只索引画出来的图,不为没画的留空位(设计 spec §6/§8)。
PNG 保持平铺,归组只发生在本索引呈现层。

--out 决定索引写到哪:缺省写 <charts-dir>/INDEX.md;剧本的阶段闸判据是工作目录根部的
INDEX.md,所以剧本正文传 `--charts-dir charts/ --out INDEX.md`。图片链接按 out 所在目录
相对化(根部索引写成 charts/<id>.png),换位置不断链。"""
from __future__ import annotations

import argparse
import json
import os
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


def _link_prefix(charts_dir: Path, out_path) -> str:
    """PNG 链接前缀:索引与图同目录时为空,索引在工作目录根部时为 'charts/'。"""
    if out_path is None:
        return ""
    rel = os.path.relpath(str(charts_dir), str(Path(out_path).parent))
    if rel in (".", ""):
        return ""
    if rel.startswith(".."):
        # 索引与图不在同一棵树（少见）：一长串 ../ 一旦挪动就断链，改用绝对路径
        return str(Path(charts_dir).resolve()) + "/"
    return rel.rstrip("/") + "/"


def _norm_rid(rid: str) -> str:
    """recipe id 归一化：脚本名多用蛇形，产物名多用连字符，配疑问时按同一形态比。"""
    return str(rid).replace("_", "-").strip().lower()


def _verification_tier(stats: dict):
    """图 JSON 的 verification：字符串或 {tier: ...} → 档位名；没有 → None。
    有档位 = 现场写的图（chartbook 未覆盖），归自己那一组，不是「未识别产物」。"""
    v = stats.get("verification")
    if isinstance(v, str):
        return v
    if isinstance(v, dict):
        t = v.get("tier") or v.get("档位")
        return str(t) if t else None
    return None


def _plan_questions(charts_dir: Path, out_path=None):
    """从工作目录的 chart_plan.json 读 recipe→疑问，供 INDEX 自动登记「服务哪条疑问」。
    找不到计划返回空 dict（sweep 模式的剧本没有计划，照旧不登记）。"""
    roots = []
    if out_path:
        roots.append(Path(out_path).parent)
    roots += [Path(charts_dir).parent, Path(charts_dir)]
    for r in roots:
        f = r / "chart_plan.json"
        if not f.exists():
            continue
        try:
            ent = json.loads(f.read_text(encoding="utf-8")).get("entries") or []
        except (OSError, json.JSONDecodeError):
            return {}
        out = {}
        for e in ent:
            rid = str(e.get("recipe") or "").strip()
            if not rid:
                continue
            # 计划里现场脚本写的是路径（蛇形），图产物用连字符主干——两边都归一化
            out[_norm_rid(Path(rid).stem)] = str(e.get("question") or "").strip()
        return out
    return {}


def build(charts_dir: Path, out_path=None) -> str:
    charts_dir = Path(charts_dir)
    prefix = _link_prefix(charts_dir, out_path)
    questions = _plan_questions(charts_dir, out_path)
    found, adhoc, unknown = [], [], []
    for jp in sorted(charts_dir.glob("*.json")):
        rid = jp.stem
        meta = recipe_meta(rid)
        if meta is None:
            try:
                stats = json.loads(jp.read_text(encoding="utf-8"))
            except json.JSONDecodeError:
                unknown.append(rid)
                continue
            tier = _verification_tier(stats) if isinstance(stats, dict) else None
            if tier:
                adhoc.append((rid, tier, stats,
                              (charts_dir / f"{rid}.png").exists()))
            else:
                unknown.append(rid)
            continue
        stats = json.loads(jp.read_text(encoding="utf-8"))
        found.append((str(meta.get("category") or "uncategorized"), rid, meta,
                      stats, (charts_dir / f"{rid}.png").exists()))
    lines = ["# 图表索引（本次实际产物）", ""]
    if not found and not adhoc and not unknown:
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
            lines.append(f"![{rid}]({prefix}{rid}.png)" if has_png
                         else "（无 PNG 产物,只有 JSON）")
            desc = key_descriptors(stats)
            if desc:
                lines.append("关键描述符: " + ", ".join(desc))
            if questions.get(_norm_rid(rid)):
                lines.append(f"服务疑问: {questions[_norm_rid(rid)]}")
            lines.append("")
    if adhoc:
        lines += ["## 现场脚本（chartbook 未覆盖）", ""]
        for rid, tier, stats, has_png in adhoc:
            lines.append(f"### {rid}")
            if questions.get(_norm_rid(rid)):
                lines.append(f"服务疑问: {questions[_norm_rid(rid)]}")
            lines.append(f"![{rid}]({prefix}{rid}.png)" if has_png
                         else "（无 PNG 产物,只有 JSON）")
            desc = key_descriptors(stats)
            if desc:
                lines.append("关键描述符: " + ", ".join(desc))
            if tier == "exploratory":
                lines.append(f"验证档位: {tier} —— **只作线索**，"
                             "数字不许进 FINDINGS 的「假设」条目与 CONCLUSION")
            else:
                lines.append(f"验证档位: {tier}")
            lines.append("")
    if unknown:
        lines += ["## 未识别产物（非 chartbook recipe、且未声明 verification）", ""]
        lines += [f"- {r}.json（现场脚本请在 JSON 顶层写 verification，"
                  "见 engine-core 三档验证路径）" for r in unknown] + [""]
    return "\n".join(lines) + "\n"


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--charts-dir", required=True)
    ap.add_argument("--out", default=None,
                    help="索引落盘路径（缺省 <charts-dir>/INDEX.md）；"
                         "阶段闸判的是工作目录根部的 INDEX.md，剧本传 --out INDEX.md")
    a = ap.parse_args(argv)
    d = Path(a.charts_dir)
    out = Path(a.out) if a.out else d / "INDEX.md"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(build(d, out), encoding="utf-8")
    print(f"INDEX.md written: {out}")


if __name__ == "__main__":
    main()
