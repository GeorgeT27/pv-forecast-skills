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
import json
import os

try:
    import yaml
except ImportError:  # 明确报错好过神秘 ImportError 栈
    raise SystemExit("缺 pyyaml：pip install -r <仓库根>/requirements.txt")

ENGINE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PLAYBOOKS_DIR = os.path.join(ENGINE_DIR, "playbooks")

CONFIG_PATH = "diagnose_config.json"
STATE_PATH = "diagnose_state.json"
PROGRESS_PATH = "PROGRESS.md"
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
    has_materials_key = "materials" in fm
    for cx in fm.get("contexts") or []:
        trig = cx.get("trigger_material")
        if trig and trig not in MATERIAL_IDS:
            raise ValueError(
                f"{md_path} context '{cx.get('id')}' 的 trigger_material='{trig}' "
                f"不是合法材料 id（见 MATERIAL_IDS）")
        if trig and has_materials_key and trig not in req + opt:
            raise ValueError(
                f"{md_path} context '{cx.get('id')}' 的 trigger_material='{trig}' "
                f"未声明在 materials.required/optional 里——其状态永远无法盘点，"
                f"embed hint 永远不会触发，须补进 materials.required/optional")


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


# ---------------------------------------------------------------- contexts
def context_status(cx, ctx):
    """泛化 ask-then-embed 三分支：linked / declined / absent（+linked 时的有效性核验）。"""
    cfg = ctx["cfg"]
    status = cfg.get(cx["status_key"]) or ""
    workdir = cfg.get(cx["workdir_key"]) or ""
    if status == "declined":
        return {"status": "declined"}
    if status == "linked" and workdir:
        missing = [m for m in cx.get("marker_files") or []
                   if not glob.glob(os.path.join(workdir, "**", m), recursive=True)
                   and not os.path.exists(os.path.join(workdir, m))]
        return {"status": "linked", "workdir": workdir, "missing_markers": missing}
    return {"status": "absent"}


def context_embed_hint(cx, cfg):
    """absent 上下文的嵌入执行提示：声明了 provider_skill 且触发材料到位 → 文案；
    否则 None。执行本身（读 provider 的 SKILL.md 内联跑）是主 agent 的活，见
    engine-core「嵌入执行 provider skill」。"""
    prov = cx.get("provider_skill")
    if not prov:
        return None
    trig = cx.get("trigger_material")
    if trig and material_status(cfg, trig) != "present":
        return None
    return (f"可嵌入生产：AskUserQuestion 问用户要不要现在内联执行技能「{prov}」"
            f"生成本上下文（跑完写 marker 回填 config，纪律见 engine-core「嵌入执行」）")


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
