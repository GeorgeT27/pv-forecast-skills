#!/usr/bin/env python3
"""ts-diagnose 引擎共享层：playbook frontmatter 解析、check-DSL、问题状态判定、
profile / project-context 实验线合并。

设计边界（防膨胀，见 spec 风险 7）：本模块只做**声明求值与打印素材**——
"问用户 / 嵌入运行 / 升级判定"永远是主 agent 照 SKILL.md 与 playbook 正文做的活，
不进脚本。分析计算也不在这里：那些由 agent 按 playbook 菜谱运行时生成进工作目录
`analysis_scripts/`。
"""
from __future__ import annotations

import fnmatch
import glob
import hashlib
import json
import os
import re

try:
    import yaml
except ImportError:  # 明确报错好过神秘 ImportError 栈
    raise SystemExit("缺 pyyaml：pip install -r <仓库根>/requirements.txt")

ENGINE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PLAYBOOKS_DIR = os.environ.get("TSD_PLAYBOOKS_DIR") \
    or os.path.join(ENGINE_DIR, "playbooks")

CONFIG_PATH = "diagnose_config.json"
STATE_PATH = "diagnose_state.json"
PROGRESS_PATH = "PROGRESS.md"
ORIENT_AUDIT_PATH = ".orient_audit.jsonl"  # orient 机器审计线;agent 不碰,不会被叙事重写清掉
FINDINGS_PATH = "FINDINGS.md"

PROFILE_VERSION = 1
PENDING = "【待补】"
# profile 里 experiment_line 引用的接口版本：project-context 定稿轮才发 v1。
# v0-draft（含旧的裸字符串形态）= 占位不生效——固化技能不得对该字段做逻辑依赖。
EXPERIMENT_LINE_IFACE_FINAL = "v1"
CRYSTALLIZE_MIN_CASES_DEFAULT = 3
# FINDINGS 状态保留字（_playbook-spec.md §3）
FINDINGS_MARKERS = ("现象", "假设", "已证实", "被推翻")

# 问题状态码 → 打印标签
Q_LABELS = {
    "user": "✓已答(user)",
    "profile": "✓固化(profile)",
    "default": "✓已答(默认)",
    "experiment-line": "✓实验线",
    "evidence": "✓证据自答",
    "default-available": "○可默认(未定)",
    "unanswered": "✗未答",
}


# ---------------------------------------------------------------- 基础 IO
def _read_text(path):
    try:
        with open(path, encoding="utf-8") as f:
            return f.read()
    except OSError:
        return ""


def read_json(path):
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except (OSError, json.JSONDecodeError):
        return None


def dump_json(obj, path):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(obj, f, ensure_ascii=False, indent=2)


def load_config(path=CONFIG_PATH):
    return read_json(path)


def save_config(cfg, path=CONFIG_PATH):
    dump_json(cfg, path)


# ---------------------------------------------------------------- playbook
def _raw_frontmatter(md_path):
    """轻解析：只切 YAML，不做校验（products_index/validate_upstream 内部用，
    避免 load_frontmatter ↔ 全目录扫描的递归）。解析不动 → None。"""
    text = _read_text(md_path)
    if not text.startswith("---"):
        return None
    end = text.find("\n---", 3)
    if end < 0:
        return None
    fm = yaml.safe_load(text[3:end])
    return fm if isinstance(fm, dict) else None


def load_frontmatter(md_path):
    """切出 md 文件头部 --- ... --- 的 YAML 块并解析。没有 frontmatter → ValueError。"""
    text = _read_text(md_path)
    if not text.startswith("---"):
        raise ValueError(f"{md_path} 缺 YAML frontmatter")
    end = text.find("\n---", 3)
    if end < 0:
        raise ValueError(f"{md_path} frontmatter 未闭合")
    fm = yaml.safe_load(text[3:end])
    if not isinstance(fm, dict) or "stages" not in fm:
        raise ValueError(f"{md_path} frontmatter 缺 stages（见 _playbook-spec.md）")
    _validate_frontmatter(fm, md_path)
    return fm


def _validate_frontmatter(fm, md_path):
    for key in ("id", "name", "goal"):
        if not fm.get(key):
            raise ValueError(f"{md_path} frontmatter 缺 {key}")
    for st in fm["stages"]:
        dw = st.get("done_when") or {}
        marker = dw.get("findings_marker")
        if marker and marker not in FINDINGS_MARKERS:
            raise ValueError(
                f"{md_path} stage {st.get('id')} findings_marker='{marker}' "
                f"不在保留字表 {FINDINGS_MARKERS}（_playbook-spec.md §3）")
        if not (dw.get("artifacts") or marker or dw.get("manual")):
            raise ValueError(f"{md_path} stage {st.get('id')} done_when 三种判定至少给一种")
        charts = st.get("charts")
        if charts is not None:
            if not isinstance(charts, list) or not all(
                    isinstance(c, str) for c in charts):
                raise ValueError(
                    f"{md_path} stage {st.get('id')} 的 charts 必须是字符串列表"
                    "（见 _playbook-spec.md）")
            known = available_recipes()
            bad = [c for c in charts if c not in known]
            if bad:
                raise ValueError(
                    f"{md_path} stage {st.get('id')} 的 charts 含未知 recipe {bad}；"
                    f"可用：{known}")
        if charts:
            arts = (st.get("done_when") or {}).get("artifacts") or []
            if "INDEX.md" not in arts:
                raise ValueError(
                    f"{md_path} stage {st.get('id')} 声明了 charts 但 done_when."
                    f"artifacts 缺 'INDEX.md'——画完必须跑 build_index.py 建索引"
                    "才算阶段完成（阶段闸，_playbook-spec §charts）")
        concl_arts = (st.get("done_when") or {}).get("artifacts") or []
        if "CONCLUSION.md" in concl_arts and "gate_reports/conclusion_gate.json" not in concl_arts:
            raise ValueError(
                f"{md_path} stage {st.get('id')} 结论阶段必须把 "
                "gate_reports/conclusion_gate.json 列入 done_when.artifacts"
                "——结论闸 receipt 即完成判据，见 _playbook-spec")
    if len(fm.get("evidence_lines") or []) >= 2 and not fm.get("upgrade_rule"):
        raise ValueError(f"{md_path} 有 ≥2 条 evidence_lines 但缺 upgrade_rule")
    mats = fm.get("materials") or {}
    if not isinstance(mats, dict):
        raise ValueError(
            f"{md_path} materials 须为 dict（形如 {{required: [...], optional: [...]}}）"
            f"，实际是 {type(mats).__name__}（见 _playbook-spec.md）")
    for key in ("required", "optional"):
        v = mats.get(key)
        if v is not None and not isinstance(v, list):
            raise ValueError(
                f"{md_path} materials.{key} 须为 list，实际是 {type(v).__name__}"
                f"（见 _playbook-spec.md）")
    req, opt = list(mats.get("required") or []), list(mats.get("optional") or [])
    for mid in req + opt:
        if mid not in MATERIAL_IDS:
            raise ValueError(
                f"{md_path} materials 引用了未知材料 id '{mid}'"
                f"（合法集见 engine_common.MATERIAL_IDS / references/intake.md）")
    overlap = set(req) & set(opt)
    if overlap:
        raise ValueError(f"{md_path} 材料 {sorted(overlap)} 既是 required 又是 optional")
    pr = fm.get("produces")
    if pr is not None:
        if not isinstance(pr, dict):
            raise ValueError(f"{md_path} produces 须为 dict（_playbook-spec §produces）")
        for key in ("id", "manifest", "marker_files"):
            if not pr.get(key):
                raise ValueError(f"{md_path} produces 缺 {key}（_playbook-spec §produces）")
        if not isinstance(pr["marker_files"], list):
            raise ValueError(f"{md_path} produces.marker_files 须为 list")
    ups = fm.get("upstream")
    if ups is not None:
        if not isinstance(ups, list):
            raise ValueError(f"{md_path} upstream 须为 list（_playbook-spec §upstream）")
        validate_upstream(fm, md_path)


def find_playbook(name):
    """按 id 定位本引擎 playbooks/<id>/playbook.md（每 playbook 一个独立目录，Layer 1）；
    兜底平铺 <id>.md（外部/旧式）；也接受直接给路径（profile 可指向外部 playbook）。"""
    if os.path.sep in str(name) and os.path.exists(name):
        return os.path.abspath(name)
    for p in (os.path.join(PLAYBOOKS_DIR, str(name), "playbook.md"),
              os.path.join(PLAYBOOKS_DIR, f"{name}.md")):
        if os.path.exists(p):
            return p
    raise FileNotFoundError(f"playbook '{name}' 不存在（找过 {PLAYBOOKS_DIR}/{name}/playbook.md 与 {name}.md）")


def playbook_dir(name):
    """playbook 的目录（golden/ 等资源所在）。平铺形态 → playbooks/ 本身。"""
    return os.path.dirname(find_playbook(name))


def list_playbooks():
    """[(id, name, goal)]，供 orient 无 config 时打印菜单。"""
    out = []
    cands = sorted(glob.glob(os.path.join(PLAYBOOKS_DIR, "*", "playbook.md"))) + \
        sorted(glob.glob(os.path.join(PLAYBOOKS_DIR, "*.md")))
    for p in cands:
        rel = os.path.relpath(p, PLAYBOOKS_DIR)
        if rel.split(os.path.sep)[0].startswith("_"):
            continue
        try:
            fm = load_frontmatter(p)
            out.append((fm["id"], fm["name"], fm["goal"]))
        except ValueError:
            continue
    return out


# ---------------------------------------------------------------- products（分层）
def products_index():
    """全引擎 produces 声明扫描 → {产物id: {playbook, manifest, marker_files}}。
    产物 id 冲突（两个 playbook 声明同一 id）→ ValueError。"""
    out = {}
    for p in sorted(glob.glob(os.path.join(PLAYBOOKS_DIR, "*", "playbook.md"))):
        fm = _raw_frontmatter(p)
        if not fm or not fm.get("produces"):
            continue
        pr = fm["produces"]
        pid = pr.get("id")
        if pid in out:
            raise ValueError(f"产物 id '{pid}' 重复声明：{out[pid]['playbook']} 与 "
                             f"{fm.get('id')}（produces.id 引擎内唯一）")
        out[pid] = {"playbook": fm.get("id"), "manifest": pr.get("manifest"),
                    "marker_files": list(pr.get("marker_files") or [])}
    return out


def validate_upstream(fm, md_path):
    """upstream 声明的加载期校验：引用存在、不自引用、问题不与生产者重复、依赖不成环。"""
    idx = products_index()
    my_product = (fm.get("produces") or {}).get("id")
    qids_own = {q["id"] for q in fm.get("questions") or []}
    for u in fm.get("upstream") or []:
        if not isinstance(u, dict) or not u.get("product"):
            raise ValueError(f"{md_path} upstream 条目缺 product 键（_playbook-spec §upstream）")
        pid = u["product"]
        if pid not in idx:
            raise ValueError(f"{md_path} upstream 引用未声明的产物 '{pid}'"
                             f"（已声明：{sorted(idx)}）")
        if pid == my_product:
            raise ValueError(f"{md_path} 自引用：既 produces 又 upstream '{pid}'")
        prod_fm = _raw_frontmatter(find_playbook(idx[pid]["playbook"])) or {}
        dup = qids_own & {q["id"] for q in prod_fm.get("questions") or []}
        if dup:
            raise ValueError(f"{md_path} 重复声明了生产者 {idx[pid]['playbook']} "
                             f"拥有的问题 {sorted(dup)}——上游产物的问题只在生产者处问一次")
    _upstream_cycle_check(fm, idx, [fm.get("id")])


def _upstream_cycle_check(fm, idx, seen):
    for u in fm.get("upstream") or []:
        info = idx.get(u["product"])
        if info is None:
            raise ValueError(f"upstream 引用未声明的产物 '{u['product']}'"
                             f"（已声明：{sorted(idx)}）")
        producer = info["playbook"]
        if producer in seen:
            raise ValueError(f"upstream 依赖成环：{' → '.join(seen + [producer])}")
        pfm = _raw_frontmatter(find_playbook(producer))
        if pfm:
            _upstream_cycle_check(pfm, idx, seen + [producer])


FULL_HASH_MAX_BYTES = 64 << 20   # ≤64MB 全量哈希（权威）；更大走 头+尾 采样（imohash 模式）
SAMPLE_BYTES = 1 << 20           # 采样块：头 1MB + 尾 1MB（尾部覆盖 parquet footer 的 EOF 元数据）
FINGERPRINT_ALGO = "v1"          # 算法版本前缀——未来换算法不至于全体产物 stale


def file_fingerprint(path):
    """产物过期检测用指纹。≤FULL_HASH_MAX_BYTES 全量 sha256；更大取 头+尾 各 1MB
    ——头部单独哈希对列式格式不安全（footer 在 EOF）。同尺寸只改中段的超大文件
    检测不到：显式接受的残余风险（spec §2）。"""
    size = os.path.getsize(path)
    h = hashlib.sha256()
    with open(path, "rb") as f:
        if size <= FULL_HASH_MAX_BYTES:
            for chunk in iter(lambda: f.read(SAMPLE_BYTES), b""):
                h.update(chunk)
            mode = "full"
        else:
            h.update(f.read(SAMPLE_BYTES))
            f.seek(max(size - SAMPLE_BYTES, 0))
            h.update(f.read(SAMPLE_BYTES))
            mode = "ht"
    return f"{FINGERPRINT_ALGO}:{mode}:{size}:{h.hexdigest()}"


def product_status(cfg, pid):
    """产物状态（真相以产物为准）：config.products 登记 + marker 核验 + 指纹对账。
    → {status: built|linked|declined|absent|invalid|stale, ...}"""
    idx = products_index()
    if pid not in idx:
        raise ValueError(f"未知产物 id '{pid}'（已声明：{sorted(idx)}）")
    rec = ((cfg or {}).get("products") or {}).get(pid) or {}
    status, workdir = rec.get("status"), rec.get("workdir") or ""
    if status == "declined":
        return {"status": "declined"}
    if status not in ("built", "linked") or not workdir:
        return {"status": "absent"}
    missing = [m for m in idx[pid]["marker_files"]
               if not os.path.exists(os.path.join(workdir, m))]
    manifest = read_json(os.path.join(workdir, idx[pid]["manifest"]))
    if missing or manifest is None:
        return {"status": "invalid", "workdir": workdir,
                "missing_markers": missing + ([idx[pid]["manifest"]]
                                              if manifest is None else [])}
    stale = []
    for mid, fp in (manifest.get("inputs") or {}).items():
        path = (fp or {}).get("path")
        if not path:
            continue
        # manifest 由生产者在自己的 workdir 里写，相对路径以 workdir 为基准解析
        if not os.path.isabs(path):
            path = os.path.join(workdir, path)
        if not os.path.exists(path):
            stale.append(mid)      # 输入文件消失也算过期（redo/apenwarr 教训）
        elif file_fingerprint(path) != fp.get("fingerprint"):
            stale.append(mid)
    if stale and not rec.get("accept_stale"):
        return {"status": "stale", "workdir": workdir, "stale_inputs": sorted(stale)}
    return {"status": status, "workdir": workdir, "missing_markers": [],
            "stale_inputs": sorted(stale)}


def upstream_report(fm, cfg):
    """orient 打印素材：[(upstream 条目, product_status 结果)]。"""
    return [(u, product_status(cfg, u["product"])) for u in fm.get("upstream") or []]


# ---------------------------------------------------------------- check-DSL
def _value_at(cfg, dotted):
    cur = cfg
    for part in dotted.split("."):
        if not isinstance(cur, dict) or part not in cur:
            return None
        cur = cur[part]
    return cur


def _filled(v):
    if v is None or v == "" or v == PENDING:
        return False
    if isinstance(v, (list, dict)):
        return len(v) > 0
    return True


def check(expr, ctx):
    """求值一条 DSL 表达式。ctx: {cfg, fm, state}。未知前缀直接报错（拼错早死）。"""
    expr = expr.strip()
    if expr.startswith("not "):
        return not check(expr[4:], ctx)
    if expr.startswith("config:"):
        return _filled(_value_at(ctx["cfg"], expr[len("config:"):]))
    if expr.startswith("file:config."):
        v = _value_at(ctx["cfg"], expr[len("file:config."):])
        return isinstance(v, str) and _filled(v) and os.path.exists(v)
    if expr.startswith("artifact:"):
        return bool(glob.glob(expr[len("artifact:"):], recursive=True))
    if expr.startswith("stage:"):
        sid = int(expr[len("stage:"):])
        st = _stage_by_id(ctx["fm"], sid)
        return stage_done(st, ctx) if st else False
    if expr.startswith("question:"):
        qid = expr[len("question:"):]
        q = _question_by_id(ctx["fm"], qid)
        if q is None:
            raise ValueError(f"DSL 引用了未声明的问题 '{qid}'")
        code, _ = question_status(q, ctx)
        return code != "unanswered"
    if expr.startswith("material:"):
        mid = expr[len("material:"):]
        if mid not in MATERIAL_IDS:
            raise ValueError(f"DSL 引用了未知材料 id '{mid}'（合法集见 MATERIAL_IDS）")
        return material_status(ctx["cfg"], mid) == "present"
    if expr.startswith("product:"):
        pid = expr[len("product:"):]
        return product_status(ctx["cfg"], pid)["status"] in ("built", "linked")
    raise ValueError(f"未知 DSL 表达式：{expr}")


def _stage_by_id(fm, sid):
    for st in fm["stages"]:
        if st["id"] == sid:
            return st
    return None


def _question_by_id(fm, qid):
    for q in fm.get("questions") or []:
        if q["id"] == qid:
            return q
    return None


# ---------------------------------------------------------------- 阶段判定
def stage_done(st, ctx):
    """真相以产物为准；manual 阶段例外——由主 agent 写进 state.manual_done。"""
    dw = st.get("done_when") or {}
    if dw.get("manual"):
        return st["id"] in ((ctx.get("state") or {}).get("manual_done") or [])
    arts = dw.get("artifacts") or []
    if arts and not all(glob.glob(a, recursive=True) for a in arts):
        return False
    marker = dw.get("findings_marker")
    if marker and marker not in _read_text(FINDINGS_PATH):
        return False
    return bool(arts or marker)


def variant_active(fm, ctx):
    """{variant_id: bool}。"""
    return {v["id"]: check(v["when"], ctx) for v in fm.get("variants") or []}


def stage_skipped(st, fm, ctx, actives=None):
    """阶段属于某未激活变体 → 跳过不阻塞。"""
    actives = actives if actives is not None else variant_active(fm, ctx)
    for v in fm.get("variants") or []:
        if st["id"] in (v.get("unlocks_stages") or []) and not actives.get(v["id"]):
            return True
    return False


def current_stage(fm, ctx):
    """第一个既未完成也未跳过的阶段；全完成 → None。"""
    actives = variant_active(fm, ctx)
    for st in fm["stages"]:
        if not stage_done(st, ctx) and not stage_skipped(st, fm, ctx, actives):
            return st
    return None


OPTIONAL_PREFIX = "（可选）"


def prereqs_of(st, ctx):
    """[(desc, ok)]。"""
    return [(p["desc"], check(p["check"], ctx)) for p in st.get("prereqs") or []]


def prereqs_ok(pr):
    return all(ok for desc, ok in pr if not desc.startswith(OPTIONAL_PREFIX))


# ---------------------------------------------------------------- 问题状态
def question_status(q, ctx):
    """→ (code, label)。code ∈ Q_LABELS 键。"""
    cfg = ctx["cfg"]
    rec = (cfg.get("questions") or {}).get(q["id"])
    if rec is not None:
        src = rec.get("source", "user")
        code = src if src in Q_LABELS else "user"
        return code, Q_LABELS[code]
    skip = q.get("skip_if")
    if skip and check(skip, ctx):
        if skip.startswith("config:") and \
                skip[len("config:"):] in (cfg.get("_experiment_line_keys") or []):
            return "experiment-line", Q_LABELS["experiment-line"]
        return "evidence", Q_LABELS["evidence"]
    if q.get("default") is not None:
        return "default-available", Q_LABELS["default-available"]
    return "unanswered", Q_LABELS["unanswered"]


def blocking_questions(fm, ctx, stage_id=None):
    """未答且无 default 的问题；stage_id 给定时只看该阶段的。"""
    out = []
    for q in fm.get("questions") or []:
        if stage_id is not None and q.get("stage") != stage_id:
            continue
        code, _ = question_status(q, ctx)
        if code == "unanswered":
            out.append(q)
    return out


# ---------------------------------------------------------------- materials
# intake 材料盘点（spec 2026-07-22 §2）。id 全集 = 引擎单一真源；
# 分类表与追问模板在 references/intake.md（test_materials 交叉校验两边一致）。
MATERIAL_IDS = ("predict", "truth", "model_code", "training_log", "features",
                "feature_true", "train_y", "checkpoint", "serving_api",
                "experiment_config", "data_profile")
MATERIAL_STATUSES = ("present", "absent-confirmed")  # 其余一律视为 unknown

# 材料入口只检查 playbook 声明的 required；未声明的材料由变体/图表按需触发。
# 保留常量名供旧调用方导入，但不再把它们提升为全局阻塞条件。
GLOBAL_MATERIALS = ()

# present 记录的实质字段要求：缺任一 → 不算过闸（防"标 present 但没问 schema"）。
# 字段名支持点路径；未列出的材料默认只要求 paths 非空。
PRESENT_REQUIRED_FIELDS = {
    "predict": ("paths", "schema.y_col", "schema.time_col"),
    "truth": ("paths", "schema.y_col", "schema.time_col"),
    "serving_api": ("schema.endpoint",),
}
_PRESENT_DEFAULT_FIELDS = ("paths",)


def present_gaps(cfg, mid):
    """present 记录缺的实质字段列表；非 present 记录 → []。"""
    rec = ((cfg or {}).get("materials") or {}).get(mid)
    if not isinstance(rec, dict) or rec.get("status") != "present":
        return []
    fields = PRESENT_REQUIRED_FIELDS.get(mid, _PRESENT_DEFAULT_FIELDS)
    return [f for f in fields if not _filled(_value_at(rec, f))]


def intake_blockers(fm, cfg):
    """入口闸：playbook required 中所有未过闸材料 → [(mid, reason)]。
    absent-confirmed 只认用户亲口（source=user）；required 材料降级还须 degraded_ok。"""
    req = set(materials_of(fm)[0])
    out = []
    for mid in [m for m in MATERIAL_IDS if m in req]:
        s = material_status(cfg, mid)
        rec = ((cfg or {}).get("materials") or {}).get(mid) or {}
        if s == "unknown":
            out.append((mid, "unknown"))
        elif s == "present":
            gaps = present_gaps(cfg, mid)
            if gaps:
                out.append((mid, "present-incomplete:" + ",".join(gaps)))
        else:  # absent-confirmed
            if rec.get("source") != "user":
                out.append((mid, "absent-not-user"))
            elif mid in req and rec.get("degraded_ok") is not True:
                out.append((mid, "absent-need-degraded-ok"))
    return out


def intake_ask_lines(mid):
    """references/intake.md 中该材料小节的原文行（orient BLOCKED 时打印追问模板）。"""
    doc = os.path.join(ENGINE_DIR, "references", "intake.md")
    m = re.search(rf"^## `{re.escape(mid)}`\n(.*?)(?=^## |\Z)",
                  _read_text(doc), re.S | re.M)
    if not m:
        return []
    return [ln.strip() for ln in m.group(1).strip().splitlines() if ln.strip()]

# chartbook recipe 类别全集(呈现层归组;spec 2026-07-23 §6)。
# recipe frontmatter 的 category 必填且 ∈ 本集(test_recipes_conform 闸)。
CATEGORY_IDS = ("error-structure", "temporal-stability", "input-side",
                "model-comparison", "sample-contrast", "attribution")


def material_status(cfg, mid):
    """config.materials 里该材料的状态：present / absent-confirmed / unknown。
    无 config、无记录、status 非法 → unknown（不许静默降级：unknown 必须去问）。"""
    rec = ((cfg or {}).get("materials") or {}).get(mid)
    if not isinstance(rec, dict):
        return "unknown"
    s = rec.get("status")
    return s if s in MATERIAL_STATUSES else "unknown"


def materials_of(fm):
    """playbook frontmatter 的材料声明 → (required, optional)。无声明 → ([], [])。"""
    m = fm.get("materials") or {}
    return list(m.get("required") or []), list(m.get("optional") or [])


def materials_report(fm, cfg):
    """[(mid, 'required'|'optional', status)]，orient 打印素材。"""
    req, opt = materials_of(fm)
    return ([(mid, "required", material_status(cfg, mid)) for mid in req]
            + [(mid, "optional", material_status(cfg, mid)) for mid in opt])


def blocking_materials(fm, cfg):
    """开工阻塞的 required 材料：[(mid, 'unknown'|'absent')]。
    absent-confirmed 且主 agent 经用户确认降级后写了 degraded_ok=true 的不算。"""
    out = []
    for mid in materials_of(fm)[0]:
        s = material_status(cfg, mid)
        if s == "unknown":
            out.append((mid, "unknown"))
        elif s == "absent-confirmed":
            rec = ((cfg or {}).get("materials") or {}).get(mid) or {}
            if rec.get("degraded_ok") is not True:
                out.append((mid, "absent"))
    return out


# ---------------------------------------------------------------- charts (chartbook)
def recipe_path(rid):
    """chartbook recipe 的 md 文件路径（不保证存在，调用方自行判断）。"""
    return os.path.join(ENGINE_DIR, "chartbook", "recipes", f"{rid}.md")


def available_recipes():
    """chartbook/recipes/*.md 的 id 列表；目录缺失 → []。"""
    d = os.path.join(ENGINE_DIR, "chartbook", "recipes")
    if not os.path.isdir(d):
        return []
    return sorted(os.path.splitext(f)[0] for f in os.listdir(d)
                  if f.endswith(".md"))


def _recipe_frontmatter(rid):
    p = recipe_path(rid)
    if not os.path.exists(p):
        raise ValueError(f"未知 chartbook recipe '{rid}'；可用：{available_recipes()}")
    with open(p, encoding="utf-8") as f:
        text = f.read()
    m = re.match(r"^---\n(.*?)\n---", text, re.S)
    return yaml.safe_load(m.group(1)) if m else {}


def recipe_materials(rid):
    """chartbook recipe 的 needs_materials（orient 可画性判定用）。"""
    return list(_recipe_frontmatter(rid).get("needs_materials") or [])


def recipe_min_models(rid):
    """chartbook recipe 需要的最少模型数（对比类图=2，默认 1；_recipe-spec §5.5）。"""
    return int(_recipe_frontmatter(rid).get("needs_models") or 1)


def recipe_category(rid):
    """chartbook recipe 的类别(orient 分组呈现用;缺失回退 uncategorized)。"""
    return str(_recipe_frontmatter(rid).get("category") or "uncategorized")


def charts_report(fm, cfg):
    """→ [(stage_id, recipe_id, missing_materials)]；missing 空 = 可画。"""
    rep = []
    for st in fm.get("stages") or []:
        for rid in st.get("charts") or []:
            missing = [mid for mid in recipe_materials(rid)
                       if material_status(cfg, mid) != "present"]
            rep.append((st["id"], rid, missing))
    return rep


def declared_recipes(fm):
    """本 playbook 任一阶段 charts: 里声明过的 recipe id 集合。"""
    out = set()
    for st in fm.get("stages") or []:
        out |= set(st.get("charts") or [])
    return out


def addable_recipes(fm, cfg):
    """图表选择门的「可加画池」：未在本 playbook 声明、但材料已全部满足的 chartbook
    recipe（跨 playbook 任取）。→ [(rid, needs_materials, min_models)]，按 rid 排序。
    材料不满足的未声明 recipe 不进池（缺什么材料由 intake 负责，不在此门问）；
    min_models≥2 的对比类图仍进池但带标注（模型数运行时才知，不静默隐藏，
    <N 模型时 recipe 脚本按 _recipe-spec §5.5 抛 ValueError 兜底）。"""
    declared = declared_recipes(fm)
    out = []
    for rid in available_recipes():
        if rid in declared:
            continue
        needs = recipe_materials(rid)
        if all(material_status(cfg, mid) == "present" for mid in needs):
            out.append((rid, needs, recipe_min_models(rid)))
    return out


def has_chart_stage(fm):
    """本 playbook 是否存在声明了 charts: 的阶段（图表选择门是否适用）。"""
    return any(st.get("charts") for st in fm.get("stages") or [])


def modelmap_blocker(cfg, fm):
    """兼容性硬闸：仅 required model_code 可阻塞；optional 走 upstream 三分支。"""
    if (fm or {}).get("id") == "model-audit":
        return None
    if material_status(cfg, "model_code") != "present":
        return None
    # 未声明 materials 的旧/简单 playbook 不消费模型代码；父 config 传入的
    # model_code:present 也不应凭空触发 model-audit。
    declared = (fm or {}).get("materials")
    if declared is None:
        return None
    req, _ = materials_of(fm or {})
    if "model_code" not in req:
        return None
    if os.path.exists("MODELMAP_RECEIPT.json"):
        return None
    try:
        if product_status(cfg, "model_profile")["status"] in ("built", "linked", "declined"):
            return None
    except ValueError:
        pass  # model_profile 产物未声明（model-audit 未升格的部署形态）——退回 receipt 判定
    return ("有模型代码（model_code=present）但无 .modelmap 档案回执——"
            "先嵌入执行 playbook「model-audit」生成档案（MODELMAP_RECEIPT.json），"
            "再回本 playbook 继续")


# ---------------------------------------------------------------- project-context
def detect_project_context():
    """探 <引擎目录>/../project-context（symlink 安装下物理解析可达）。无 → None。"""
    cand = os.path.join(os.path.dirname(ENGINE_DIR), "project-context")
    return cand if os.path.isdir(cand) else None


def list_experiments(pc_dir):
    """[(name, path)]。"""
    out = []
    for p in sorted(glob.glob(os.path.join(pc_dir, "experiments", "*.json"))):
        exp = read_json(p)
        if exp and exp.get("name"):
            out.append((exp["name"], p))
    return out


def merge_experiment_line(cfg, exp_json_path):
    """把实验线 json 的已填字段合并进 config（只补缺，【待补】不搬），记 provenance。
    返回本次合并的键列表。"""
    exp = read_json(exp_json_path)
    if not exp:
        raise FileNotFoundError(f"实验线不可读：{exp_json_path}")
    merged = []
    flat = {
        "held_out_station": exp.get("held_out_station"),
        "held_out_station_slug": exp.get("held_out_station_slug"),
        "models": exp.get("models"),
        "chunking": exp.get("chunking"),
        "training_entries": exp.get("training_entries"),
    }
    for k, v in (exp.get("data_paths") or {}).items():
        flat[f"data_{k}"] = v
    for k, v in flat.items():
        if _filled(v) and not _filled(cfg.get(k)):
            cfg[k] = v
            merged.append(k)
    cfg["experiment_line"] = exp_json_path
    keys = set(cfg.get("_experiment_line_keys") or []) | set(merged)
    cfg["_experiment_line_keys"] = sorted(keys)
    return merged


# ---------------------------------------------------------------- profile
def load_profile(path):
    prof = yaml.safe_load(_read_text(path))
    if not isinstance(prof, dict) or not prof.get("playbook"):
        raise ValueError(f"profile 不合法（缺 playbook）：{path}")
    return prof


def merge_profile(cfg, prof, date_stamp):
    """profile → config：playbook / config_defaults 补缺 / questions 以 source=profile 落盘。
    返回 {'version_ok': bool, 'merged_keys': [...], 'merged_questions': [...]}。
    版本不匹配 → version_ok=False，调用方（orient）警告并降级为"按 playbook 现问"
    （即不合并 questions，只合并 playbook 与 config_defaults）。"""
    version_ok = prof.get("profile_version") == PROFILE_VERSION
    cfg.setdefault("playbook", prof["playbook"])
    merged_keys, merged_qs = [], []
    for k, v in (prof.get("config_defaults") or {}).items():
        if _filled(v) and not _filled(cfg.get(k)):
            cfg[k] = v
            merged_keys.append(k)
    # experiment_line 引用：只有接口定稿（v1）才生效；v0-draft / 旧裸字符串 = 占位，
    # 不写进 cfg——相关问题照常问（约束只针对固化产物；运行时主 agent 现场写入不受影响）。
    exp_placeholder = False
    exp = prof.get("experiment_line")
    if exp:
        iface = exp.get("interface_version") if isinstance(exp, dict) else "v0-draft"
        path = exp.get("path") if isinstance(exp, dict) else exp
        if iface == EXPERIMENT_LINE_IFACE_FINAL and path:
            cfg.setdefault("experiment_line", path)
        else:
            exp_placeholder = True
    merged_mats = []
    if prof.get("materials"):
        mats = cfg.setdefault("materials", {})
        for mid, rec in prof["materials"].items():
            if mid in MATERIAL_IDS and mid not in mats and isinstance(rec, dict):
                merged_rec = {**rec, "source": "profile", "date": date_stamp}
                # degraded_ok 是每次运行的用户降级豁免，不得由固化 profile 带入——强制剥除。
                merged_rec.pop("degraded_ok", None)
                mats[mid] = merged_rec
                merged_mats.append(mid)
    if version_ok:
        qs = cfg.setdefault("questions", {})
        for qid, rec in (prof.get("questions") or {}).items():
            if qid not in qs:
                qs[qid] = {"answer": rec.get("answer") if isinstance(rec, dict) else rec,
                           "source": "profile", "date": date_stamp}
                merged_qs.append(qid)
    return {"version_ok": version_ok, "experiment_line_placeholder": exp_placeholder,
            "merged_keys": merged_keys, "merged_questions": merged_qs,
            "merged_materials": merged_mats}


def crystallize_min_cases(fm):
    """固化三关之一（多样性）的 N：playbook frontmatter 可覆盖默认值。"""
    return int(fm.get("crystallize_min_cases") or CRYSTALLIZE_MIN_CASES_DEFAULT)


STAGE_HEADING_RE = re.compile(r"^###\s+Stage\s*(\d+)(?:\s*[–\-~/]\s*(\d+))?(?!\d)")


def recipe_sections(playbook_path):
    """playbook 正文 → {stage_id: 小节原文}。小节 = '### Stage N' 标题起，到下一个 '## '/'### ' 止；
    '### Stage N–M' 把范围内每个 id 映射到同一节。同一 id 两个标题 → ValueError。"""
    with open(playbook_path, encoding="utf-8") as f:
        body = f.read().split("---", 2)[2]
    out, cur, buf = {}, None, []

    def flush():
        if cur is None:
            return
        text = "\n".join(buf).rstrip()
        for i in cur:
            if i in out:
                raise ValueError(f"{playbook_path}: Stage {i} 出现两个菜谱标题")
            out[i] = text

    for ln in body.splitlines():
        m = STAGE_HEADING_RE.match(ln)
        if m:
            flush()
            lo, hi = int(m.group(1)), int(m.group(2) or m.group(1))
            cur, buf = list(range(lo, hi + 1)), [ln]
        elif cur is not None and (ln.startswith("## ") or ln.startswith("### ")):
            flush()
            cur, buf = None, []
        elif cur is not None:
            buf.append(ln)
    flush()
    return out
