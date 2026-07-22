# ts-diagnose v2 Plan 1/3：引擎框架（intake 材料盘点 + material DSL + provider_skill 委托）

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 给 ts-diagnose 引擎加上「材料盘点」一等机制（materials 块 + `material:` DSL + orient 盘点报告）与 contexts 的 `provider_skill`/`trigger_material` 委托字段，全部向后兼容既有三个 playbook。

**Architecture:** 全部改动集中在 `engine_common.py`（数据模型+DSL）、`orient.py`（打印）、三个规范文档（intake.md 新建、engine-core.md、_playbook-spec.md）。真相以产物为准的哲学不变：materials 状态存 `diagnose_config.json` 的 `materials` 块，orient 只求值与打印，提问永远是主 agent 的活。

**Tech Stack:** Python 3 + pyyaml + pytest（现有栈，零新依赖）。

**Spec:** `docs/superpowers/specs/2026-07-22-ts-diagnose-v2-intake-chartbook-design.md` §2、§3（§4-§7 属 Plan 2/3）。

## Global Constraints

- 所有路径相对仓库根 `/Users/tqa946816/Documents/华为/光伏预测/结果分析skill/`（下称 `<REPO>`）。
- **向后兼容硬约束**：无 `materials` 键的 playbook（现有 training-sufficiency / robustness / feature-importance）行为完全不变。
- 材料 id 全集（引擎单一真源，intake.md 与之交叉校验）：`predict` `truth` `model_code` `training_log` `features` `feature_true` `train_y` `checkpoint` `serving_api` `experiment_config` `data_profile`。
- materials 状态三值：`present` / `absent-confirmed` / `unknown`（缺记录=unknown）；**unknown 的 required 材料阻塞开工；absent-confirmed 的 required 材料也阻塞，除非主 agent 经用户确认降级后写 `degraded_ok: true`**。
- 单写者纪律不变：subagent 不写 config/state/PROGRESS。
- 每个 Task 收尾跑全仓 `python3 -m pytest <REPO> -q` 必须全绿（当前基线 100+ 项）。
- 提交信息用中文、`feat(ts-diagnose):` / `docs(ts-diagnose):` / `test(ts-diagnose):` 前缀，结尾带 `Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>`。
- pytest 运行方式：`cd <REPO> && python3 -m pytest ts-diagnose/scripts/tests/ -q`。

---

### Task 1: engine_common — 材料数据模型 + frontmatter `materials` 键校验

**Files:**
- Modify: `ts-diagnose/scripts/engine_common.py`（在 `# ---- contexts` 节之前插入新节；`_validate_frontmatter` 追加校验）
- Test: `ts-diagnose/scripts/tests/test_materials.py`（新建）

**Interfaces:**
- Produces（后续 Task 依赖的精确签名）:
  - `MATERIAL_IDS: tuple[str, ...]`（11 个 id，见 Global Constraints）
  - `material_status(cfg: dict|None, mid: str) -> str`（→ `"present"|"absent-confirmed"|"unknown"`）
  - `materials_of(fm: dict) -> tuple[list[str], list[str]]`（→ (required, optional)）
  - `materials_report(fm: dict, cfg: dict|None) -> list[tuple[str, str, str]]`（→ [(mid, "required"|"optional", status)]）
  - `blocking_materials(fm: dict, cfg: dict|None) -> list[tuple[str, str]]`（→ [(mid, reason)]，reason ∈ `"unknown"|"absent"`；absent-confirmed 且 `degraded_ok` 为真的不算阻塞）
- frontmatter 新键格式：`materials: {required: [predict, truth], optional: [model_code]}`
- config 新块格式：`"materials": {"predict": {"status": "present", "paths": [...], "layout": "...", "schema": {...}, "sample_rows": "...", "source": "user", "date": "..."}}`

- [ ] **Step 1: 写失败测试**

新建 `ts-diagnose/scripts/tests/test_materials.py`：

```python
"""materials 机制（intake 材料盘点的数据模型 + DSL + frontmatter 校验）测试。"""
import os
import sys

import pytest

SCRIPTS_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, SCRIPTS_DIR)
import engine_common as ec  # noqa: E402


def fm_with_materials(tmp_path, materials_yaml):
    p = tmp_path / "pb.md"
    p.write_text("---\nid: x\nname: x\ngoal: x\n"
                 f"{materials_yaml}"
                 "stages:\n  - id: 0\n    name: a\n"
                 "    done_when: {artifacts: ['a.json']}\n---\n", encoding="utf-8")
    return ec.load_frontmatter(str(p))


# ---------------------------------------------------------------- 状态判定
def test_material_status_three_values():
    cfg = {"materials": {
        "predict": {"status": "present", "paths": ["a.parquet"]},
        "training_log": {"status": "absent-confirmed"},
        "truth": {"status": "怪值"},
    }}
    assert ec.material_status(cfg, "predict") == "present"
    assert ec.material_status(cfg, "training_log") == "absent-confirmed"
    assert ec.material_status(cfg, "truth") == "unknown"      # 非法值按 unknown
    assert ec.material_status(cfg, "model_code") == "unknown"  # 无记录
    assert ec.material_status(None, "predict") == "unknown"    # 无 config
    assert ec.material_status({}, "predict") == "unknown"


# ---------------------------------------------------------------- frontmatter
def test_materials_of_and_report(tmp_path):
    fm = fm_with_materials(
        tmp_path, "materials:\n  required: [predict, truth]\n  optional: [model_code]\n")
    assert ec.materials_of(fm) == (["predict", "truth"], ["model_code"])
    cfg = {"materials": {"predict": {"status": "present"}}}
    assert ec.materials_report(fm, cfg) == [
        ("predict", "required", "present"),
        ("truth", "required", "unknown"),
        ("model_code", "optional", "unknown"),
    ]


def test_materials_of_absent_key(tmp_path):
    fm = fm_with_materials(tmp_path, "")   # 无 materials 键（旧 playbook 形态）
    assert ec.materials_of(fm) == ([], [])
    assert ec.materials_report(fm, {}) == []
    assert ec.blocking_materials(fm, {}) == []


def test_frontmatter_rejects_unknown_material_id(tmp_path):
    with pytest.raises(ValueError, match="材料 id"):
        fm_with_materials(tmp_path, "materials:\n  required: [predikt]\n")


def test_frontmatter_rejects_required_optional_overlap(tmp_path):
    with pytest.raises(ValueError, match="既是 required 又是 optional"):
        fm_with_materials(
            tmp_path, "materials:\n  required: [predict]\n  optional: [predict]\n")


# ---------------------------------------------------------------- 阻塞
def test_blocking_materials(tmp_path):
    fm = fm_with_materials(
        tmp_path, "materials:\n  required: [predict, truth, training_log]\n"
                  "  optional: [model_code]\n")
    cfg = {"materials": {
        "predict": {"status": "present"},
        "truth": {"status": "absent-confirmed"},                      # 阻塞（未降级）
        "training_log": {"status": "absent-confirmed", "degraded_ok": True},  # 已降级不阻塞
    }}
    assert ec.blocking_materials(fm, cfg) == [("truth", "absent")]
    # optional 永不阻塞
    cfg2 = {"materials": {"predict": {"status": "present"},
                          "truth": {"status": "present"},
                          "training_log": {"status": "present"}}}
    assert ec.blocking_materials(fm, cfg2) == []
    # 全 unknown → required 逐个报 unknown
    assert ec.blocking_materials(fm, {}) == [
        ("predict", "unknown"), ("truth", "unknown"), ("training_log", "unknown")]


def test_existing_playbooks_still_load():
    """向后兼容：现有三个 playbook 无 materials 键，加载与判定不受影响。"""
    for pid in ("training-sufficiency", "robustness", "feature-importance"):
        fm = ec.load_frontmatter(ec.find_playbook(pid))
        assert ec.materials_of(fm) == ([], [])
```

- [ ] **Step 2: 跑测试确认失败**

Run: `cd <REPO> && python3 -m pytest ts-diagnose/scripts/tests/test_materials.py -q`
Expected: FAIL / ERROR，`AttributeError: ... has no attribute 'material_status'`。

- [ ] **Step 3: 实现**

`engine_common.py` 在 `# ---------------------------------------------------------------- contexts` 节**之前**插入：

```python
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
            if not rec.get("degraded_ok"):
                out.append((mid, "absent"))
    return out
```

`_validate_frontmatter` 末尾（`evidence_lines` 校验之后）追加：

```python
    mats = fm.get("materials") or {}
    req, opt = list(mats.get("required") or []), list(mats.get("optional") or [])
    for mid in req + opt:
        if mid not in MATERIAL_IDS:
            raise ValueError(
                f"{md_path} materials 引用了未知材料 id '{mid}'"
                f"（合法集见 engine_common.MATERIAL_IDS / references/intake.md）")
    overlap = set(req) & set(opt)
    if overlap:
        raise ValueError(f"{md_path} 材料 {sorted(overlap)} 既是 required 又是 optional")
```

- [ ] **Step 4: 跑测试确认通过**

Run: `cd <REPO> && python3 -m pytest ts-diagnose/scripts/tests/test_materials.py -q`
Expected: PASS（8 项）。

- [ ] **Step 5: 全仓回归 + 提交**

Run: `cd <REPO> && python3 -m pytest ts-diagnose/scripts/tests/ -q`
Expected: 全绿（原有项 + 新 8 项）。

```bash
cd <REPO> && git add ts-diagnose/scripts/engine_common.py ts-diagnose/scripts/tests/test_materials.py
git commit --no-verify -m "feat(ts-diagnose): materials 数据模型——11 类材料 id、三值状态、required 阻塞判定（含 degraded_ok 降级逃生门）

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```

---

### Task 2: check-DSL 新增 `material:<id>` 表达式

**Files:**
- Modify: `ts-diagnose/scripts/engine_common.py`（`check()` 函数）
- Test: `ts-diagnose/scripts/tests/test_materials.py`（追加）

**Interfaces:**
- Consumes: Task 1 的 `material_status` / `MATERIAL_IDS`。
- Produces: `check("material:<id>", ctx) -> bool`（status==present 才 True；未知 id 抛 ValueError——拼错早死，与 `question:` 同哲学）。prereqs.check / variants.when / questions.skip_if 三处通用（`check` 是共用求值器，自动生效）。

- [ ] **Step 1: 追加失败测试**

`test_materials.py` 末尾追加：

```python
# ---------------------------------------------------------------- material: DSL
def test_material_dsl(tmp_path):
    fm = fm_with_materials(tmp_path, "materials:\n  required: [predict]\n"
                                     "  optional: [model_code]\n")
    cfg = {"materials": {"predict": {"status": "present"},
                         "model_code": {"status": "absent-confirmed"}}}
    ctx = {"cfg": cfg, "fm": fm, "state": {}}
    assert ec.check("material:predict", ctx) is True
    assert ec.check("material:model_code", ctx) is False      # absent ≠ present
    assert ec.check("material:training_log", ctx) is False    # unknown ≠ present
    assert ec.check("not material:model_code", ctx) is True
    with pytest.raises(ValueError, match="未知材料"):
        ec.check("material:predikt", ctx)


def test_material_dsl_drives_variant(tmp_path):
    """材料驱动变体解锁：有 model_code 才激活机制归因类阶段（spec §2 orient 改动）。"""
    p = tmp_path / "pb.md"
    p.write_text("---\nid: x\nname: x\ngoal: x\n"
                 "materials:\n  required: [predict]\n  optional: [model_code]\n"
                 "stages:\n"
                 "  - id: 0\n    name: a\n    done_when: {artifacts: ['a.json']}\n"
                 "  - id: 1\n    name: b\n    done_when: {artifacts: ['b.json']}\n"
                 "variants:\n"
                 "  - id: model-side\n    when: 'material:model_code'\n"
                 "    unlocks_stages: [1]\n---\n", encoding="utf-8")
    fm = ec.load_frontmatter(str(p))
    ctx = {"cfg": {}, "fm": fm, "state": {}}
    assert ec.variant_active(fm, ctx) == {"model-side": False}
    ctx["cfg"] = {"materials": {"model_code": {"status": "present"}}}
    assert ec.variant_active(fm, ctx) == {"model-side": True}
```

- [ ] **Step 2: 跑测试确认失败**

Run: `cd <REPO> && python3 -m pytest ts-diagnose/scripts/tests/test_materials.py -q`
Expected: 新 2 项 FAIL，`ValueError: 未知 DSL 表达式：material:predict`。

- [ ] **Step 3: 实现**

`engine_common.py` 的 `check()` 中、`raise ValueError(f"未知 DSL 表达式…")` 之前插入：

```python
    if expr.startswith("material:"):
        mid = expr[len("material:"):]
        if mid not in MATERIAL_IDS:
            raise ValueError(f"DSL 引用了未知材料 id '{mid}'（合法集见 MATERIAL_IDS）")
        return material_status(ctx["cfg"], mid) == "present"
```

- [ ] **Step 4: 跑测试确认通过**

Run: `cd <REPO> && python3 -m pytest ts-diagnose/scripts/tests/test_materials.py -q`
Expected: PASS（10 项）。

- [ ] **Step 5: 全仓回归 + 提交**

Run: `cd <REPO> && python3 -m pytest ts-diagnose/scripts/tests/ -q` → 全绿。

```bash
cd <REPO> && git add ts-diagnose/scripts/engine_common.py ts-diagnose/scripts/tests/test_materials.py
git commit --no-verify -m "feat(ts-diagnose): check-DSL 新增 material:<id>——阶段/变体/skip_if 可按材料解锁

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```

---

### Task 3: contexts 新字段 `provider_skill` / `trigger_material` + 校验

**Files:**
- Modify: `ts-diagnose/scripts/engine_common.py`（`_validate_frontmatter` + 新 helper）
- Test: `ts-diagnose/scripts/tests/test_materials.py`（追加）

**Interfaces:**
- Consumes: Task 1 的 `MATERIAL_IDS` / `material_status`。
- Produces: `context_embed_hint(cx: dict, cfg: dict|None) -> str|None`——absent 上下文若声明了 `provider_skill` 且（无 `trigger_material` 或该材料 present）→ 返回嵌入执行提示文案；否则 None。frontmatter 校验：`trigger_material` 必须 ∈ MATERIAL_IDS。

- [ ] **Step 1: 追加失败测试**

`test_materials.py` 末尾追加：

```python
# ---------------------------------------------------------------- provider_skill
CX = {"id": "model-profile", "name": "模型参考档案",
      "workdir_key": "modelmap_dir", "status_key": "modelmap_status",
      "marker_files": ["models.md"], "on_absent": "ask",
      "provider_skill": "pv-model-analysis", "trigger_material": "model_code"}


def test_context_embed_hint():
    cfg_has = {"materials": {"model_code": {"status": "present"}}}
    hint = ec.context_embed_hint(CX, cfg_has)
    assert "pv-model-analysis" in hint and "嵌入" in hint
    # 触发材料不 present → 不提议嵌入
    assert ec.context_embed_hint(CX, {}) is None
    # 无 provider_skill → 永远 None
    cx2 = {k: v for k, v in CX.items() if k != "provider_skill"}
    assert ec.context_embed_hint(cx2, cfg_has) is None
    # 无 trigger_material → 只要有 provider_skill 就提议
    cx3 = {k: v for k, v in CX.items() if k != "trigger_material"}
    assert ec.context_embed_hint(cx3, {}) is not None


def test_frontmatter_rejects_bad_trigger_material(tmp_path):
    p = tmp_path / "pb.md"
    p.write_text("---\nid: x\nname: x\ngoal: x\nstages:\n"
                 "  - id: 0\n    name: a\n    done_when: {artifacts: ['a.json']}\n"
                 "contexts:\n"
                 "  - id: c\n    name: c\n    workdir_key: w\n    status_key: s\n"
                 "    trigger_material: nope\n---\n", encoding="utf-8")
    with pytest.raises(ValueError, match="trigger_material"):
        ec.load_frontmatter(str(p))
```

- [ ] **Step 2: 跑测试确认失败**

Run: `cd <REPO> && python3 -m pytest ts-diagnose/scripts/tests/test_materials.py -q`
Expected: 新 2 项 FAIL（`context_embed_hint` 不存在；trigger_material 校验缺失）。

- [ ] **Step 3: 实现**

`engine_common.py` 的 `context_status` 函数之后追加：

```python
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
```

`_validate_frontmatter` 末尾（Task 1 的 materials 校验之后）追加：

```python
    for cx in fm.get("contexts") or []:
        trig = cx.get("trigger_material")
        if trig and trig not in MATERIAL_IDS:
            raise ValueError(
                f"{md_path} context '{cx.get('id')}' 的 trigger_material='{trig}' "
                f"不是合法材料 id（见 MATERIAL_IDS）")
```

- [ ] **Step 4: 跑测试确认通过**

Run: `cd <REPO> && python3 -m pytest ts-diagnose/scripts/tests/test_materials.py -q`
Expected: PASS（12 项）。

- [ ] **Step 5: 全仓回归 + 提交**

Run: `cd <REPO> && python3 -m pytest ts-diagnose/scripts/tests/ -q` → 全绿。

```bash
cd <REPO> && git add ts-diagnose/scripts/engine_common.py ts-diagnose/scripts/tests/test_materials.py
git commit --no-verify -m "feat(ts-diagnose): contexts 新字段 provider_skill/trigger_material——absent 上下文可提议嵌入执行专用技能生产

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```

---

### Task 4: orient.py — 材料盘点段 + 嵌入提示 + 开工闸

**Files:**
- Modify: `ts-diagnose/scripts/orient.py`
- Test: `ts-diagnose/scripts/tests/test_orient_materials.py`（新建，subprocess 端到端）

**Interfaces:**
- Consumes: Task 1-3 的 `materials_report` / `blocking_materials` / `context_embed_hint`。
- Produces: orient 输出契约（测试断言这些子串，主 agent 靠它们行动）：
  - 有 materials 声明时打印 `材料盘点` 段，行格式 `[✓present] predict (required)` / `[✗未盘点·阻塞] truth (required)` / `[○未盘点] model_code (optional)` / `[−absent] training_log (required, 已确认降级)`；
  - 有阻塞材料时打印 `⚠ 必需材料未就绪` + 指引（多选 AskUserQuestion + intake.md）且**目标阶段判定为不可开工**（不打印 `→ 前置齐，可开工`）；
  - absent 上下文若 `context_embed_hint` 非 None，追加打印该提示；
  - 无 materials 声明的 playbook：输出不含 `材料盘点`（向后兼容）。

- [ ] **Step 1: 写失败测试**

新建 `ts-diagnose/scripts/tests/test_orient_materials.py`：

```python
"""orient 材料盘点段的端到端测试（subprocess 跑真 orient，断言输出契约）。"""
import os
import subprocess
import sys

SCRIPTS_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ORIENT = os.path.join(SCRIPTS_DIR, "orient.py")
sys.path.insert(0, SCRIPTS_DIR)
import engine_common as ec  # noqa: E402

PB = """---
id: mat-demo
name: 材料演示
goal: 测试材料盘点
materials:
  required: [predict, truth]
  optional: [model_code]
stages:
  - id: 0
    name: 起步
    done_when: {artifacts: ['stage0.json']}
contexts:
  - id: model-profile
    name: 模型参考档案
    workdir_key: modelmap_dir
    status_key: modelmap_status
    marker_files: [models.md]
    on_absent: ask
    provider_skill: pv-model-analysis
    trigger_material: model_code
---
正文占位。
"""


def run_orient(workdir, *args):
    r = subprocess.run([sys.executable, ORIENT, *args], cwd=workdir,
                       capture_output=True, text=True, timeout=60)
    assert r.returncode == 0, r.stderr
    return r.stdout


def setup_pb(tmp_path, cfg_materials=None):
    pb = tmp_path / "pb" / "playbook.md"
    pb.parent.mkdir()
    pb.write_text(PB, encoding="utf-8")
    cfg = {"playbook": str(pb)}
    if cfg_materials is not None:
        cfg["materials"] = cfg_materials
    ec.dump_json(cfg, str(tmp_path / "diagnose_config.json"))
    return tmp_path


def test_blocked_when_unknown(tmp_path):
    out = run_orient(setup_pb(tmp_path))
    assert "材料盘点" in out
    assert "[✗未盘点·阻塞] predict (required)" in out
    assert "[✗未盘点·阻塞] truth (required)" in out
    assert "[○未盘点] model_code (optional)" in out
    assert "⚠ 必需材料未就绪" in out and "intake.md" in out
    assert "可开工" not in out


def test_open_when_present_and_embed_hint(tmp_path):
    mats = {"predict": {"status": "present"}, "truth": {"status": "present"},
            "model_code": {"status": "present"}}
    out = run_orient(setup_pb(tmp_path, mats))
    assert "[✓present] predict (required)" in out
    assert "→ 前置齐，可开工 Stage 0" in out
    # model_code present + 上下文 absent → 打印嵌入提示
    assert "pv-model-analysis" in out and "嵌入" in out


def test_degraded_absent_not_blocking(tmp_path):
    mats = {"predict": {"status": "present"},
            "truth": {"status": "absent-confirmed", "degraded_ok": True}}
    out = run_orient(setup_pb(tmp_path, mats))
    assert "[−absent] truth (required, 已确认降级)" in out
    assert "⚠ 必需材料未就绪" not in out
    assert "→ 前置齐，可开工 Stage 0" in out


def test_absent_without_waiver_blocks(tmp_path):
    mats = {"predict": {"status": "present"},
            "truth": {"status": "absent-confirmed"}}
    out = run_orient(setup_pb(tmp_path, mats))
    assert "[−absent] truth (required)" in out
    assert "⚠ 必需材料未就绪" in out
    assert "可开工" not in out


def test_legacy_playbook_no_materials_section(tmp_path):
    """向后兼容：真实 training-sufficiency playbook 无 materials 键 → 无盘点段。"""
    ec.dump_json({"playbook": "training-sufficiency"},
                 str(tmp_path / "diagnose_config.json"))
    out = run_orient(tmp_path)
    assert "材料盘点" not in out
```

- [ ] **Step 2: 跑测试确认失败**

Run: `cd <REPO> && python3 -m pytest ts-diagnose/scripts/tests/test_orient_materials.py -q`
Expected: 前 4 项 FAIL（无 `材料盘点` 输出），末项 PASS。

- [ ] **Step 3: 实现**

`orient.py` 两处修改。

**(a)** contexts 循环里，absent 分支（`else:` 打印 `[absent]` 之后）追加嵌入提示：

```python
        else:
            print(f"  ⚠ 上下文「{cx['name']}」[absent]：主 agent 必须先 AskUserQuestion"
                  f"（要不要先建立该上下文？做法见 playbook 正文），"
                  f"答案回填 config.{cx['status_key']}（+{cx['workdir_key']}）。")
            hint = ec.context_embed_hint(cx, cfg)
            if hint:
                print(f"    {hint}")
```

**(b)** contexts 循环之后、问题清单之前插入材料盘点段；并把开工判定接入阻塞。先在 contexts 循环后加：

```python
    mat_rows = ec.materials_report(fm, cfg)
    mat_blocked = ec.blocking_materials(fm, cfg)
    if mat_rows:
        print("-" * 62)
        print("  材料盘点（追问模板与 status 写法见 references/intake.md；"
              "答案落 config.materials）：")
        for mid, kind, st in mat_rows:
            rec = ((cfg.get("materials") or {}).get(mid)) or {}
            if st == "present":
                label = "✓present"
            elif st == "absent-confirmed":
                label = "−absent"
                kind = f"{kind}, 已确认降级" if rec.get("degraded_ok") else kind
            else:
                label = "✗未盘点·阻塞" if (mid, "unknown") in mat_blocked else "○未盘点"
            print(f"  [{label}] {mid} ({kind})")
        if mat_blocked:
            print("  ⚠ 必需材料未就绪：" + ", ".join(m for m, _ in mat_blocked)
                  + " —— 开工前先按 references/intake.md 盘点：")
            print("    一次多选 AskUserQuestion 列全该 playbook 的材料 checklist"
                  "（末尾带『还有别的吗』开放项），")
            print("    再按每类的追问模板批量补齐 路径/格式/schema（y列/时间列/id列）；")
            print("    absent-confirmed 的必需材料要走降级须经用户确认后写 degraded_ok。")
```

再把目标阶段「可开工」判定改为同时要求材料不阻塞——原：

```python
        if ec.prereqs_ok(pr) and not blocked_qs:
            print(f"→ 前置齐，可开工 Stage {target['id']}。")
```

改为：

```python
        for mid, reason in mat_blocked:
            print(f"  [✗] 必需材料未就绪：{mid}（{reason}）")
        if ec.prereqs_ok(pr) and not blocked_qs and not mat_blocked:
            print(f"→ 前置齐，可开工 Stage {target['id']}。")
```

（注意 `elif args.goto ...` / `else` 分支保持原样，材料阻塞时落入 `else` 的「有 ✗ 先补」提示。）

- [ ] **Step 4: 跑测试确认通过**

Run: `cd <REPO> && python3 -m pytest ts-diagnose/scripts/tests/test_orient_materials.py -q`
Expected: PASS（5 项）。

- [ ] **Step 5: 全仓回归 + 提交**

Run: `cd <REPO> && python3 -m pytest ts-diagnose/scripts/tests/ -q` → 全绿。

```bash
cd <REPO> && git add ts-diagnose/scripts/orient.py ts-diagnose/scripts/tests/test_orient_materials.py
git commit --no-verify -m "feat(ts-diagnose): orient 材料盘点段——必需材料未就绪阻塞开工 + absent 上下文嵌入执行提示

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```

---

### Task 5: profile 固化支持 materials（crystallize 原料闭环)

**Files:**
- Modify: `ts-diagnose/scripts/engine_common.py`（`merge_profile`）
- Modify: `ts-diagnose/references/crystallize.md`（补一行说明）
- Test: `ts-diagnose/scripts/tests/test_materials.py`（追加）

**Interfaces:**
- Consumes: Task 1 的 config `materials` 块格式。
- Produces: profile.yaml 可带 `materials:` 块（结构同 config.materials 的条目）；`merge_profile` 返回 dict 新增键 `"merged_materials": [...]`（本次合并的材料 id 列表）。合并规则与 config_defaults 一致：**只补缺**（config 已有该材料记录则不覆盖），source 改写为 `"profile"`。

- [ ] **Step 1: 追加失败测试**

`test_materials.py` 末尾追加：

```python
# ---------------------------------------------------------------- profile 固化
def test_merge_profile_materials():
    prof = {"profile_version": ec.PROFILE_VERSION, "playbook": "x",
            "materials": {
                "predict": {"status": "present", "layout": "per-model",
                            "schema": {"y_col": "power"}},
                "truth": {"status": "present"}}}
    cfg = {"materials": {"truth": {"status": "absent-confirmed", "source": "user"}}}
    res = ec.merge_profile(cfg, prof, "2026-07-22")
    assert res["merged_materials"] == ["predict"]          # truth 已有，不覆盖
    assert cfg["materials"]["predict"]["status"] == "present"
    assert cfg["materials"]["predict"]["source"] == "profile"
    assert cfg["materials"]["truth"]["status"] == "absent-confirmed"  # 原样保留


def test_merge_profile_materials_absent_key():
    prof = {"profile_version": ec.PROFILE_VERSION, "playbook": "x"}
    cfg = {}
    res = ec.merge_profile(cfg, prof, "2026-07-22")
    assert res["merged_materials"] == []
```

- [ ] **Step 2: 跑测试确认失败**

Run: `cd <REPO> && python3 -m pytest ts-diagnose/scripts/tests/test_materials.py -q`
Expected: 新 2 项 FAIL（`KeyError: 'merged_materials'`）。

- [ ] **Step 3: 实现**

`merge_profile` 中 `if version_ok:` 块**之前**插入（materials 合并不依赖 questions 版本门：材料是路径/schema 事实，与提问版本无关；但保守起见与 config_defaults 同层）：

```python
    merged_mats = []
    if prof.get("materials"):
        mats = cfg.setdefault("materials", {})
        for mid, rec in prof["materials"].items():
            if mid in MATERIAL_IDS and mid not in mats and isinstance(rec, dict):
                mats[mid] = {**rec, "source": "profile", "date": date_stamp}
                merged_mats.append(mid)
```

返回值里加 `"merged_materials": merged_mats`（保持字段顺序不重要，加进现有 dict）。

`references/crystallize.md`：在讲 questions 固化的段落后追加一行（用 Grep 找到「questions」相关小节，紧随其后）：

```markdown
- **materials 同为固化原料**：config.materials 里跨次稳定的条目（layout/schema——
  路径通常每次不同，别固化具体路径）搬进 profile.yaml 的 `materials:` 块，
  结构同 config 条目；orient --profile 时只补缺合并，source 记 `profile`。
```

- [ ] **Step 4: 跑测试确认通过**

Run: `cd <REPO> && python3 -m pytest ts-diagnose/scripts/tests/test_materials.py -q`
Expected: PASS（14 项）。

- [ ] **Step 5: 全仓回归 + 提交**

Run: `cd <REPO> && python3 -m pytest ts-diagnose/scripts/tests/ -q` → 全绿。

```bash
cd <REPO> && git add ts-diagnose/scripts/engine_common.py ts-diagnose/references/crystallize.md ts-diagnose/scripts/tests/test_materials.py
git commit --no-verify -m "feat(ts-diagnose): profile 固化支持 materials 块——盘点结果可随 crystallize 复用

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```

---

### Task 6: references/intake.md — 材料分类表与盘点纪律（新文档）

**Files:**
- Create: `ts-diagnose/references/intake.md`
- Test: `ts-diagnose/scripts/tests/test_materials.py`（追加交叉校验）

**Interfaces:**
- Consumes: Task 1 的 `MATERIAL_IDS`（文档必须逐一覆盖）。
- Produces: 主 agent 盘点时读的完整分类表；每个材料 id 一节（`## \`<id>\`` 格式，测试按此断言）。

- [ ] **Step 1: 追加失败测试**

`test_materials.py` 末尾追加：

```python
# ---------------------------------------------------------------- intake.md 交叉校验
def test_intake_doc_covers_all_material_ids():
    doc = os.path.join(os.path.dirname(SCRIPTS_DIR), "references", "intake.md")
    text = open(doc, encoding="utf-8").read()
    for mid in ec.MATERIAL_IDS:
        assert f"## `{mid}`" in text, f"intake.md 缺材料 '{mid}' 的小节"
    for kw in ("absent-confirmed", "degraded_ok", "还有别的", "sample_rows",
               "y_col", "对账"):
        assert kw in text, f"intake.md 缺关键纪律词 '{kw}'"
```

- [ ] **Step 2: 跑测试确认失败**

Run: `cd <REPO> && python3 -m pytest ts-diagnose/scripts/tests/test_materials.py::test_intake_doc_covers_all_material_ids -q`
Expected: FAIL（文件不存在）。

- [ ] **Step 3: 写文档**

新建 `ts-diagnose/references/intake.md`，完整内容：

````markdown
# 材料盘点（intake）——「我们有什么」的引擎级 checklist

<!-- 单一真源分工：材料 id 全集在 engine_common.MATERIAL_IDS（机器校验用），
     本文件是每类材料的人读定义 + 追问模板（test_materials.py 交叉校验两边一致）。
     新增材料类：两边同时加，测试逼你保持同步。 -->

playbook frontmatter 声明 `materials: {required: [...], optional: [...]}` 后，
orient 会报盘点状态。主 agent 按本文件流程收集，答案落 `diagnose_config.json`
的 `materials` 块。

## 盘点流程（orient 报「必需材料未就绪」时执行）

1. **一次多选 AskUserQuestion**：「你手头有哪些材料？」——选项 = 该 playbook 声明的
   required + optional 材料（每项带下表的一句话说明），**末尾固定加一项开放的
   「还有别的吗？（自由描述）」**——用户不会一次说全，checklist 就是提醒器。
2. 对每个勾选的材料，按其小节的**追问模板**批量补齐（同一批 ≤4 题；先问 required）。
   **schema 类问题请用户贴 2-3 行样例**（存 `sample_rows`，原话不转述）。
3. 落盘 `config.materials`，status 三值：
   - `present`：有，路径/schema 已问清；
   - `absent-confirmed`：**用户明确说没有**——required 材料走降级前还须用户确认
     「接受降级结论」，确认后主 agent 写 `degraded_ok: true`（PROGRESS.md 记一行）；
   - 没问过 = 无记录 = unknown：**阻塞，绝不静默降级**。
4. 材料相关的证据自答（如工作目录已有明显的 predict parquet）只能免"在哪"，
   **免不了 schema 追问**——列名语义猜错污染全部下游（必问五类第 1 条）。

## config.materials 条目格式

```json
"materials": {
  "predict": {
    "status": "present",
    "paths": ["runs/mA/pred.parquet", "runs/mB/pred.parquet"],
    "layout": "per-model",
    "schema": {"y_col": "power_pred", "time_col": "ts", "id_col": "station"},
    "sample_rows": "<用户贴的原话样例>",
    "source": "user", "date": "2026-07-22"
  },
  "training_log": {"status": "absent-confirmed", "degraded_ok": true,
                    "source": "user", "date": "2026-07-22"}
}
```

`source` 枚举同 questions 块：`user` / `profile` / `default` / `experiment-line`。
跨次稳定的条目（layout/schema）是 crystallize 固化原料；具体路径通常每次不同，不固化。

## 材料分类表

## `predict`

模型的预测结果（1..N 个模型）。
**追问**：在哪（每模型一个文件还是合并一个）？哪列是预测值（`y_col`）？时间戳列？
单元/站点 id 列？每行是单点还是一个窗口（如 192 点 list）？覆盖什么时间范围？贴样例行。

## `truth`

与预测同期的真值（test 集 y-label）。
**追问**：在哪？真值列名？与 predict 怎么对齐（时间戳键？窗口起点？）？有没有缺失段？贴样例行。

## `model_code`

模型实现代码仓库/目录。
**追问**：路径？里面有几个模型、名字分别是什么？哪个是产线版本（多版本必问，不许自行裁决）？
（present 时 orient 会对声明了 `provider_skill: pv-model-analysis` 的上下文给出嵌入执行提示。）

## `training_log`

训练日志。
**追问**：在哪？什么格式（结构化 CSV/JSON 还是文本）？记录了什么（loss/lr/iteration/chunk）？
贴 2-3 行样例。

## `features`

模型输入的预测特征序列（如 NWP 气象预报，与预测同期未来窗口）。
**追问**：在哪？哪些列是特征、各自什么含义与单位？与 predict 的行怎么对应？贴样例行。

## `feature_true`

特征的真值对照（每特征"预报 vs 实况"成对序列）。
**追问**：在哪？结构（每行一个窗口时间戳、每格 192 点 list？）？覆盖哪些特征？
（有此材料的特征质量归因场景优先走专用技能 pv-feature-blame——见路由优先级。）

## `train_y`

训练期真值序列（漂移对比用：训练/测试同期分布）。
**追问**：在哪？时间范围？与 test 真值同单位同口径吗？

## `checkpoint`

模型权重/检查点（可支持重训、梯度类证据）。
**追问**：在哪？对应哪个模型哪个版本？加载入口（框架/脚本）？用它属昂贵操作——必问授权。

## `serving_api`

可调用的预测服务（反事实验证入口，如 FastAPI）。
**追问**：endpoint 与调用契约（输入输出格式）？调一次的成本/时长？有调用示例代码吗？

## `experiment_config`

实验设定（站点全集/留出划分/chunk 方案/超参）。
**追问**：在哪（文件还是口述）？project-context 实验线覆盖了吗（覆盖则走 Step 0.5 预填，
不重复问）？

## `data_profile`

数据画像/统计摘要（已有的探索性分析产物）。
**追问**：在哪？基于哪份数据、什么时候做的（过期画像误导大）？

## 适配器对账（材料 → 规范长表，chartbook/分析消费前必过）

用 materials.schema 写薄适配器把用户格式转规范长表后，**先过对账验证步再消费**：

1. 行数守恒：转换前后样本数对得上（窗口展开的按 `窗口数 × horizon` 核对）；
2. 抽 3 个窗口人工核对数值（原文件 vs 长表，逐点相等）；
3. 结果记 PROGRESS.md 一行（没对账记录的长表不可引用——同脚本验证纪律）。
````

- [ ] **Step 4: 跑测试确认通过**

Run: `cd <REPO> && python3 -m pytest ts-diagnose/scripts/tests/test_materials.py -q`
Expected: PASS（15 项）。

- [ ] **Step 5: 提交**

```bash
cd <REPO> && git add ts-diagnose/references/intake.md ts-diagnose/scripts/tests/test_materials.py
git commit --no-verify -m "docs(ts-diagnose): references/intake.md——11 类材料分类表+追问模板+schema 块+适配器对账纪律（与 MATERIAL_IDS 交叉校验）

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```

---

### Task 7: engine-core.md — Step 0.75 盘点 + 嵌入执行纪律

**Files:**
- Modify: `ts-diagnose/references/engine-core.md`
- Test: 无新脚本测试（纯文档；`test_layering.py` 现有守卫继续过）

**Interfaces:**
- Consumes: intake.md（Task 6）、`context_embed_hint` 行为（Task 3/4）。
- Produces: 主 agent 执行纪律的两段新文本（Plan 2 的 chartbook 豁免条款也预留钩子句）。

- [ ] **Step 1: 编辑「Step 0：Orient」节**

在 `**Step 0.5（可选）**：...` 段落之后追加：

```markdown
**Step 0.75：材料盘点（playbook 声明了 materials 时）**：orient 报「必需材料未就绪」→
按 `references/intake.md` 盘点：一次多选 AskUserQuestion（checklist + 「还有别的吗」
开放项）→ 逐材料追问模板补齐路径/格式/schema（y 列、时间列、id 列——猜错污染全部下游，
必问）→ 落 `config.materials`（status 三值；用户确认没有 = absent-confirmed，required
材料降级须用户再确认后写 degraded_ok）。材料状态驱动 `material:` DSL（变体/前置/skip_if）。
```

- [ ] **Step 2: 编辑「执行模型」节**

在「**上下文三分支**」条目之后插入一条：

```markdown
- **嵌入执行 provider skill**：context 声明了 `provider_skill` 且 orient 给出嵌入提示 →
  AskUserQuestion 问用户要不要现在生产（列大致成本）。同意 → **主 agent 内联读该技能的
  SKILL.md 完整执行**（保留提问权；不经 subagent——subagent 无提问权），产物落盘、按
  marker_files 核验、写回 config 的 workdir_key/status_key=linked，PROGRESS.md 记
  「嵌入执行 <skill> 开始/完成」两行，回来重跑 orient 继续主流程。拒绝 → status_key=declined。
```

- [ ] **Step 3: 编辑「常见错误」节**

追加两条：

```markdown
- ❌ orient 报「必需材料未就绪」却跳过盘点直接开工，或材料 unknown 时按"大概有"处理
  （unknown ≠ absent-confirmed：前者必须问，后者才允许走确认过的降级）。
- ❌ 嵌入执行 provider skill 时丢给 subagent（其流程含必须用户裁决的问题），或跑完
  不写 marker/config 回填就继续（下次 orient 仍报 absent，白跑）。
```

- [ ] **Step 4: 全仓回归 + 提交**

Run: `cd <REPO> && python3 -m pytest ts-diagnose/scripts/tests/ -q` → 全绿
（注意 test_layering 若有 engine-core 行数/token 上限断言，超限则精简本次新增文字再跑）。

```bash
cd <REPO> && git add ts-diagnose/references/engine-core.md
git commit --no-verify -m "docs(ts-diagnose): engine-core 新增 Step 0.75 材料盘点与「嵌入执行 provider skill」纪律

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```

---

### Task 8: _playbook-spec.md — materials 键 + contexts 新字段 + material DSL 文档化

**Files:**
- Modify: `ts-diagnose/playbooks/_playbook-spec.md`
- Test: 无新脚本测试（规范文档；Task 1-3 的机器校验已覆盖行为）

**Interfaces:**
- Consumes: Task 1-3 的 frontmatter 语义。
- Produces: Plan 3 写 model-comparison / fact-scan playbook 时依据的规范文本。

- [ ] **Step 1: frontmatter schema 示例更新**

§1 的 YAML 示例里、`variants:` 之前插入：

```yaml
materials:                        # 可选。本 playbook 的材料需求（intake 引擎级机制）
  required: [predict, truth]      #   unknown/absent 均阻塞开工（absent 可经用户确认降级）
  optional: [model_code]          #   不阻塞；驱动变体/图表可用性
```

`contexts:` 示例的条目里追加两行：

```yaml
    provider_skill: pv-model-analysis   # 可选：谁能生产本上下文（触发嵌入执行提示）
    trigger_material: model_code        # 可选：该材料 present 才提议嵌入（须为合法材料 id）
```

- [ ] **Step 2: check-DSL 表格加一行**

§2 表格追加：

```markdown
| `material:<id>` | config.materials 该材料 status 为 present（id 必须 ∈ engine_common.MATERIAL_IDS，拼错报错） |
```

- [ ] **Step 3: 正文必备节补充**

§4 末尾追加一条：

```markdown
7. **材料降级说明**（声明了 materials 时）——required 材料 absent-confirmed 时本
   playbook 怎么降级（哪些阶段跳过/结论上限降到什么），主 agent 据此向用户描述
   降级成本再请求 degraded_ok 确认。
```

- [ ] **Step 4: 全仓回归 + 提交**

Run: `cd <REPO> && python3 -m pytest ts-diagnose/scripts/tests/ -q` → 全绿。

```bash
cd <REPO> && git add ts-diagnose/playbooks/_playbook-spec.md
git commit --no-verify -m "docs(ts-diagnose): playbook 规范新增 materials 键、contexts provider_skill/trigger_material、material: DSL

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```

---

### Task 9: 收尾——全仓验证 + CHANGELOG

**Files:**
- Modify: `ts-diagnose/CHANGELOG.md`（若无则创建，照现有仓库格式）

- [ ] **Step 1: 全仓测试**

Run: `cd <REPO> && python3 -m pytest -q`
Expected: 全绿（原有 100+ 项 + 本计划新增 ~20 项）。

- [ ] **Step 2: CHANGELOG 追加**

`ts-diagnose/CHANGELOG.md` 追加一行（存在则续写，格式照旧：日期 | 改了什么 | 触发反馈 | 为什么）：

```markdown
- 2026-07-22 | 引擎 v2 框架：materials 盘点（11 类+三值状态+material: DSL+orient 盘点段）、contexts provider_skill 嵌入执行、profile 固化 materials | 用户："所有 skill 开始时都该搞清楚我们有什么…如何让一个 skill 调用一个 skill 然后回主流程" | 泛化 intake 与 skill 委托，为 chartbook（Plan 2）与 model-comparison/fact-scan（Plan 3）铺路
```

- [ ] **Step 3: 提交**

```bash
cd <REPO> && git add ts-diagnose/CHANGELOG.md
git commit --no-verify -m "docs(ts-diagnose): CHANGELOG——v2 框架轮（intake+provider_skill）

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```

---

## Self-Review 记录

1. **Spec 覆盖**：§2 材料分类表→Task 6；§2 盘点流程→Task 4/7；§2 orient/DSL→Task 1/2/4；§2 crystallize 原料→Task 5；§3 provider_skill 字段→Task 3；§3 执行语义→Task 7；§3 规范化→Task 8。§4-§7（chartbook/playbooks/路由）明确属 Plan 2/3，不在本计划。
2. **占位符扫描**：无 TBD/TODO；每个代码步骤有完整代码；文档步骤有完整文本。
3. **类型一致性**：`material_status` 返回 str 三值、`blocking_materials` 返回 [(mid, reason)]、`context_embed_hint` 返回 str|None、`merge_profile` 新键 `merged_materials`——Task 4/5 的消费处与 Task 1/3 的定义一致；orient 输出子串契约与 test_orient_materials 断言一致。
