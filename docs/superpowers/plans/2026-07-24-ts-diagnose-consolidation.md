# ts-diagnose 单入口化 + 三道硬闸 实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 把 4 个 pv-* 技能的方法下沉为 ts-diagnose playbook 后删壳，并给引擎装三道硬闸（入口闸/阶段闸/结论闸），使弱执行模型无法跳过材料盘点、画图阶段与模型结构依据。

**Architecture:** 强制力全部放在脚本 exit 路径（orient.py BLOCKED 模式 + conclusion_gate.py receipt），不放散文纪律。playbook 从 6 → 9（+model-audit / result-eval / subset-influence），feature-blame 方法并入 feature-importance 变体。光伏特有内容只存在于 project-context/。

**Tech Stack:** Python 3 + pyyaml + pytest；引擎 = `ts-diagnose/scripts/{orient.py, engine_common.py}` 声明求值器，playbook = frontmatter(YAML) + 正文菜谱。

**Spec:** `docs/superpowers/specs/2026-07-24-ts-diagnose-consolidation-design.md`

## Global Constraints

- 每个 Task 结束跑 `python3 -m pytest ts-diagnose/ pv-*/ -q`（仓库根），全绿才 commit；Phase 3 起 pv-* 目录逐步消失，命令随之收缩为 `python3 -m pytest ts-diagnose/ -q`。
- `ts-diagnose/SKILL.md` ≤60 行、token 预算由 `scripts/tests/test_layering.py` 守卫——凡动 SKILL.md 必跑它。
- 单一真源：材料 id 全集 = `engine_common.MATERIAL_IDS`；人读定义 = `references/intake.md`；`test_materials.py::test_intake_doc_covers_all_material_ids` 逼两边同步。
- `train_y` 定义放宽为「训练集数据（train.parquet，含真值，特征列可选）」——intake.md 与本计划所有引用处同步用该口径，不新增材料 id。
- 所有引擎脚本注释/输出保持中文、现有风格；文件路径一律仓库相对（工作目录产物除外）。
- 迁移用 `git mv`（保历史），不用 cp+rm。
- 本仓库脚本无 `Date.now` 类禁忌，但 orient 输出契约测试全部走 subprocess（沿用 `test_orient_materials.py` 风格）。

---

## Phase 1：引擎加固（不动任何 pv 技能）

### Task 1: engine_common —— 全局五件套 + present 实质校验 + intake_blockers

**Files:**
- Modify: `ts-diagnose/scripts/engine_common.py`（materials 段，line ~340）
- Test: `ts-diagnose/scripts/tests/test_materials.py`（追加）

**Interfaces:**
- Produces:
  - `GLOBAL_MATERIALS: tuple`（五件套 id）
  - `present_gaps(cfg, mid) -> list[str]`（present 记录缺的实质字段；非 present → []）
  - `intake_blockers(fm, cfg) -> list[tuple[str, str]]`（入口闸阻塞项；reason ∈ `unknown` / `present-incomplete:<fields>` / `absent-not-user` / `absent-need-degraded-ok`）
  - `intake_ask_lines(mid) -> list[str]`（intake.md 该材料小节的追问文案行）

- [ ] **Step 1: 写失败测试**（追加到 `test_materials.py` 末尾）

```python
# ---------------------------------------------------------------- 入口闸（三道闸之一）
def test_present_gaps():
    cfg = {"materials": {
        "predict": {"status": "present", "paths": ["p.parquet"],
                    "schema": {"y_col": "power"}},                 # 缺 time_col
        "truth": {"status": "present", "paths": ["t.parquet"],
                  "schema": {"y_col": "y", "time_col": "ts"}},     # 齐
        "checkpoint": {"status": "present"},                        # 缺 paths
        "training_log": {"status": "absent-confirmed"},             # 非 present → []
    }}
    assert ec.present_gaps(cfg, "predict") == ["schema.time_col"]
    assert ec.present_gaps(cfg, "truth") == []
    assert ec.present_gaps(cfg, "checkpoint") == ["paths"]
    assert ec.present_gaps(cfg, "training_log") == []
    assert ec.present_gaps({}, "predict") == []


def test_intake_blockers_five_piece_always_asked(tmp_path):
    """五件套是引擎级恒问：playbook 只声明 predict/truth，五件套照样阻塞。"""
    fm = fm_with_materials(
        tmp_path, "materials:\n  required: [predict, truth]\n")
    got = dict(ec.intake_blockers(fm, {}))
    for mid in ("training_log", "truth", "train_y", "checkpoint",
                "model_code", "predict"):
        assert got[mid] == "unknown"
    assert "features" not in got      # 非五件套、非 required → 不恒问


def test_intake_blockers_reasons(tmp_path):
    fm = fm_with_materials(tmp_path, "materials:\n  required: [predict]\n")
    cfg = {"materials": {
        "predict": {"status": "present", "paths": ["p.parquet"],
                    "schema": {"y_col": "p", "time_col": "ts"}},
        "truth": {"status": "present"},                              # 缺实质字段
        "train_y": {"status": "absent-confirmed", "source": "user"},
        "training_log": {"status": "absent-confirmed"},              # source≠user
        "checkpoint": {"status": "absent-confirmed", "source": "user"},
        "model_code": {"status": "absent-confirmed", "source": "user"},
    }}
    got = dict(ec.intake_blockers(fm, cfg))
    assert "predict" not in got
    assert got["truth"].startswith("present-incomplete:")
    assert "paths" in got["truth"]
    assert got["training_log"] == "absent-not-user"
    assert "train_y" not in got and "checkpoint" not in got
    # required 材料 absent-confirmed（source=user）仍须 degraded_ok
    cfg["materials"]["predict"] = {"status": "absent-confirmed", "source": "user"}
    got = dict(ec.intake_blockers(fm, cfg))
    assert got["predict"] == "absent-need-degraded-ok"


def test_intake_ask_lines():
    lines = ec.intake_ask_lines("training_log")
    assert any("追问" in ln for ln in lines)
    assert ec.intake_ask_lines("不存在的id") == []
```

- [ ] **Step 2: 跑测试确认失败**

Run: `python3 -m pytest ts-diagnose/scripts/tests/test_materials.py -q`
Expected: FAIL，`AttributeError: ... has no attribute 'present_gaps'`

- [ ] **Step 3: 实现**（`engine_common.py` materials 段，`MATERIAL_STATUSES` 之后插入）

```python
# 入口闸（spec 2026-07-24 §2）：五件套引擎级恒问——不管 playbook 声明什么，
# 都必须盘点到 present / absent-confirmed(source=user)。
GLOBAL_MATERIALS = ("training_log", "truth", "train_y", "checkpoint", "model_code")

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
    """入口闸：五件套 ∪ playbook required 中所有未过闸材料 → [(mid, reason)]。
    absent-confirmed 只认用户亲口（source=user）；required 材料降级还须 degraded_ok。"""
    req = set(materials_of(fm)[0])
    out = []
    for mid in [m for m in MATERIAL_IDS if m in (set(GLOBAL_MATERIALS) | req)]:
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
```

- [ ] **Step 4: 跑测试确认通过**

Run: `python3 -m pytest ts-diagnose/scripts/tests/test_materials.py -q`
Expected: PASS（全部，含旧用例）

- [ ] **Step 5: 更新 intake.md 的 train_y 定义**（同步全局约束）

`ts-diagnose/references/intake.md` 的 `## \`train_y\`` 小节改为：

```markdown
## `train_y`

训练集数据（train.parquet：训练期真值，特征列可选；漂移对比与训练侧诊断用）。
**追问**：在哪？时间范围？含哪些列（真值列名？带不带特征）？与 test 真值同单位同口径吗？
```

并在 intake.md 开头「盘点流程」小节后追加一段：

```markdown
## 引擎级恒问五件套

不管进哪个 playbook，`training_log / truth / train_y / checkpoint / model_code`
五类必须全部问到 present 或 absent-confirmed(source=user)，否则 orient 直接
BLOCKED（不输出任何阶段菜单）。playbook 声明的 required/optional 照旧叠加。
```

Run: `python3 -m pytest ts-diagnose/scripts/tests/test_materials.py -q` → PASS

- [ ] **Step 6: Commit**

```bash
git add ts-diagnose/scripts/engine_common.py ts-diagnose/scripts/tests/test_materials.py ts-diagnose/references/intake.md
git commit -m "feat(ts-diagnose): 入口闸数据层——五件套恒问 + present 实质校验 + intake_blockers"
```

### Task 2: orient BLOCKED 模式（入口闸执行层）

**Files:**
- Modify: `ts-diagnose/scripts/orient.py`
- Test: `ts-diagnose/scripts/tests/test_orient_materials.py`（改旧 + 加新）

**Interfaces:**
- Consumes: Task 1 的 `intake_blockers` / `intake_ask_lines`
- Produces: orient 输出契约——阻塞时首行含 `BLOCKED: 材料盘点未完成`，且**不出现**「Stage」菜单、图表选择门、问题清单、「可开工」。

- [ ] **Step 1: 修旧测试 + 写新测试**

`test_orient_materials.py` 现有三个用例的 cfg 只盘点了 playbook 材料，新闸下五件套 unknown 会 BLOCKED——这是**预期行为变化**。改法：给 `setup_pb` 增加参数 `full=True` 时自动把五件套补成 `absent-confirmed + source=user`：

```python
FIVE_OK = {mid: {"status": "absent-confirmed", "source": "user"}
           for mid in ("training_log", "train_y", "checkpoint", "model_code")}
# truth 是五件套之一且本 PB required：required+absent 需 degraded_ok，
# 各用例已自带 truth 记录或用 present，见下。


def setup_pb(tmp_path, cfg_materials=None, five_ok=True):
    pb = tmp_path / "pb" / "playbook.md"
    pb.parent.mkdir()
    pb.write_text(PB, encoding="utf-8")
    mats = dict(FIVE_OK) if five_ok else {}
    mats.update(cfg_materials or {})
    cfg = {"playbook": str(pb)}
    if mats:
        cfg["materials"] = mats
    ec.dump_json(cfg, str(tmp_path / "diagnose_config.json"))
    return tmp_path
```

旧用例改动：
- `test_blocked_when_unknown`：改为断言新契约——`"BLOCKED: 材料盘点未完成" in out`、`"Stage 0" not in out`、`"可开工" not in out`、追问模板出现（`"追问" in out`）；
- `test_open_when_present_and_embed_hint`：present 记录补实质字段
  `{"status": "present", "paths": ["x.parquet"], "schema": {"y_col": "y", "time_col": "ts"}}`（model_code 只需 paths）；沿用 `five_ok=True`；断言不变；
- `test_degraded_absent_not_blocking`：truth 记录补 `"source": "user"`。

新用例：

```python
def test_blocked_hides_all_menus_and_logs_progress(tmp_path):
    wd = setup_pb(tmp_path, five_ok=False)
    out = run_orient(wd)
    assert "BLOCKED: 材料盘点未完成" in out
    for banned in ("Stage 0", "图表选择门", "问题清单", "可开工", "前置"):
        assert banned not in out
    assert "AskUserQuestion" in out and "materials" in out
    prog = (wd / "PROGRESS.md").read_text(encoding="utf-8")
    assert "BLOCKED" in prog


def test_present_without_schema_blocks(tmp_path):
    mats = {"predict": {"status": "present", "paths": ["p.parquet"]},  # 缺 schema
            "truth": {"status": "present", "paths": ["t.parquet"],
                      "schema": {"y_col": "y", "time_col": "ts"}}}
    out = run_orient(setup_pb(tmp_path, mats))
    assert "BLOCKED" in out and "present-incomplete" in out
    assert "schema.y_col" in out
```

- [ ] **Step 2: 跑测试确认失败**

Run: `python3 -m pytest ts-diagnose/scripts/tests/test_orient_materials.py -q`
Expected: 新用例 FAIL（无 BLOCKED 输出）

- [ ] **Step 3: 实现**——`orient.py` 在 `fm = ec.load_frontmatter(...)` 与 state 读取之后、打印表头之前插入：

```python
    blockers = ec.intake_blockers(fm, cfg)
    if blockers:
        print("=" * 62)
        print(f"BLOCKED: 材料盘点未完成（入口闸）    playbook: {fm['id']}")
        print("-" * 62)
        print("以下材料过闸前，orient 不输出任何阶段菜单与菜谱入口。")
        print("主 agent 现在只做一件事：AskUserQuestion 盘点（一次多选列 checklist，")
        print("末尾带『还有别的吗』开放项；再按追问模板逐项补齐，答案落")
        print("diagnose_config.json 的 materials 块——格式见 references/intake.md）。")
        reasons = {
            "unknown": "未盘点（从没问过）",
            "absent-not-user": "absent-confirmed 但 source≠user——只有用户亲口说没有才算",
            "absent-need-degraded-ok": "required 材料缺失——须用户确认接受降级后写 degraded_ok: true",
        }
        for mid, reason in blockers:
            desc = reasons.get(reason)
            if desc is None and reason.startswith("present-incomplete:"):
                desc = (f"标了 present 但缺实质字段 {reason.split(':', 1)[1]}"
                        "——schema 没问清不算 present")
            print(f"  ✗ {mid} —— {desc}")
            for ln in ec.intake_ask_lines(mid)[:3]:
                print(f"      {ln}")
        print("=" * 62)
        _write_state_progress(fm, None, args, blocked=[m for m, _ in blockers])
        return
```

并把文件末尾的 state+PROGRESS 写盘抽成函数（BLOCKED 分支复用）：

```python
def _write_state_progress(fm, cur, args, ctx=None, actives=None, blocked=None):
    if blocked is not None:
        new_state = {"playbook": fm["id"],
                     "updated": dt.datetime.now().isoformat(timespec="seconds"),
                     "current_stage": "intake-blocked", "stages": {},
                     "manual_done": [], "variants": {}}
        line = f"orient：playbook={fm['id']}，BLOCKED 材料盘点未完成：{','.join(blocked)}"
    else:
        ...  # 原 new_state / line 逻辑原样搬入
    ec.dump_json(new_state, ec.STATE_PATH)
    ...  # 原 PROGRESS 追加逻辑原样搬入，f.write 用 line
```

- [ ] **Step 4: 跑测试确认通过**

Run: `python3 -m pytest ts-diagnose/scripts/tests/ -q`
Expected: PASS（`test_engine.py` / `test_charts_decl.py` 等若有 orient 端到端用例同样要补五件套 cfg——按 Step 1 的 FIVE_OK 模式修，修完必须全绿）

- [ ] **Step 5: Commit**

```bash
git add ts-diagnose/scripts/orient.py ts-diagnose/scripts/tests/
git commit -m "feat(ts-diagnose): orient 入口闸 BLOCKED 模式——材料未过闸只吐提问清单"
```

### Task 3: --goto 护栏 + --force 留痕（阶段闸之一）

**Files:**
- Modify: `ts-diagnose/scripts/orient.py`（argparse + target 分支）
- Test: `ts-diagnose/scripts/tests/test_orient_goto.py`（新建）

**Interfaces:**
- Produces: `--goto N` 前置不齐时输出 `⛔ 拒绝直达`，且不打印目标阶段前置详情与三道门自检；`--goto N --force` 放行并在 PROGRESS.md 记 `--force` 行。

- [ ] **Step 1: 写失败测试**（新文件，复用 `test_orient_materials.py` 的 run_orient/PB 模式；PB 用两阶段：Stage 0 `done_when: {artifacts: ['stage0.json']}`，Stage 1 `prereqs: [{desc: 前一阶段, check: 'stage:0'}]`；cfg 五件套齐 + predict/truth present-完整）

```python
def test_goto_refused_without_force(tmp_path):
    wd = setup_two_stage_pb(tmp_path)          # stage0.json 不存在
    out = run_orient(wd, "--goto", "1")
    assert "⛔ 拒绝直达 Stage 1" in out
    assert "正确入口 = Stage 0" in out
    assert "三道门" not in out                  # 不吐目标阶段的自检/菜谱指引


def test_goto_force_allows_and_logs(tmp_path):
    wd = setup_two_stage_pb(tmp_path)
    out = run_orient(wd, "--goto", "1", "--force")
    assert "⛔" not in out
    assert "进入 Stage 1 的前置" in out
    prog = (wd / "PROGRESS.md").read_text(encoding="utf-8")
    assert "--force" in prog and "跳过前置" in prog
```

- [ ] **Step 2: 跑测试确认失败** → `python3 -m pytest ts-diagnose/scripts/tests/test_orient_goto.py -q`，FAIL

- [ ] **Step 3: 实现**：argparse 加 `ap.add_argument("--force", action="store_true", help="用户明确要求跳过前置时才可用；PROGRESS 留痕")`。target 分支改为：

```python
    if target is not None:
        pr = ec.prereqs_of(target, ctx)
        blocked_qs = ec.blocking_questions(fm, ctx, stage_id=target["id"])
        goto_jump = (args.goto is not None and cur is not None
                     and target["id"] != cur["id"])
        if goto_jump and not (ec.prereqs_ok(pr) and not blocked_qs) \
                and not args.force:
            print("-" * 62)
            print(f"⛔ 拒绝直达 Stage {target['id']}：前置不齐。"
                  f"正确入口 = Stage {cur['id']}（{cur['name']}）。")
            print("   确需跳过：须用户明确指示后重跑 orient --goto "
                  f"{target['id']} --force（将记 PROGRESS 留痕，结论须声明缺口）。")
            target = cur          # 回落到当前阶段，按正常流程打印
            pr = ec.prereqs_of(target, ctx)
            blocked_qs = ec.blocking_questions(fm, ctx, stage_id=target["id"])
        ...  # 原打印逻辑继续（前置清单/恒问五类/三道门自检）
```

PROGRESS 行（在 `_write_state_progress` 的 line 组装处）：`--goto` 且 `--force` 时追加 `"（--force：用户要求跳过前置，Stage 前置未齐）"`。

- [ ] **Step 4: 跑测试确认通过** → `python3 -m pytest ts-diagnose/scripts/tests/ -q`，PASS

- [ ] **Step 5: Commit**

```bash
git add ts-diagnose/scripts/orient.py ts-diagnose/scripts/tests/test_orient_goto.py
git commit -m "feat(ts-diagnose): --goto 护栏——前置不齐拒绝直达，--force 须用户指示且留痕"
```

### Task 4: 图表阶段完成判据收紧（阶段闸之二）

**Files:**
- Modify: `ts-diagnose/scripts/engine_common.py`（`_validate_frontmatter`）
- Modify: `ts-diagnose/playbooks/model-comparison/playbook.md` + 其余所有声明 `charts:` 的 playbook（先 `grep -rl "charts:" ts-diagnose/playbooks/`）
- Modify: `ts-diagnose/playbooks/_playbook-spec.md`（规则入 spec）
- Test: `ts-diagnose/scripts/tests/test_materials.py`（追加）

**Interfaces:**
- Produces: 加载期校验——声明了 `charts:` 的阶段，其 `done_when.artifacts` 必须包含 `"INDEX.md"`（build_index.py 产物；画完不建索引不算完成）。

- [ ] **Step 1: 写失败测试**

```python
def test_chart_stage_requires_index_artifact(tmp_path):
    p = tmp_path / "pb.md"
    p.write_text("---\nid: x\nname: x\ngoal: x\nstages:\n"
                 "  - id: 0\n    name: 图\n"
                 "    done_when: {artifacts: ['charts/*.json']}\n"
                 "    charts: [error-breakdown]\n---\n", encoding="utf-8")
    with pytest.raises(ValueError, match="INDEX.md"):
        ec.load_frontmatter(str(p))
```

- [ ] **Step 2: 确认失败** → FAIL（不抛错）

- [ ] **Step 3: 实现**：`_validate_frontmatter` 的 charts 校验块末尾加：

```python
        if charts:
            arts = (st.get("done_when") or {}).get("artifacts") or []
            if "INDEX.md" not in arts:
                raise ValueError(
                    f"{md_path} stage {st.get('id')} 声明了 charts 但 done_when."
                    f"artifacts 缺 'INDEX.md'——画完必须跑 build_index.py 建索引"
                    "才算阶段完成（阶段闸，_playbook-spec §charts）")
```

- [ ] **Step 4: 修所有现有 chart 阶段**：`grep -rn "charts:" ts-diagnose/playbooks/*/playbook.md` 命中的每个阶段，`done_when.artifacts` 列表加 `"INDEX.md"`（如 model-comparison Stage 2 → `artifacts: ["charts/*.json", "INDEX.md"]`）。`_playbook-spec.md` charts 小节加一行规则说明。

- [ ] **Step 5: 全量测试通过** → `python3 -m pytest ts-diagnose/ -q`，PASS（golden/gen_gate 用例若含旧 frontmatter 快照需同步）

- [ ] **Step 6: Commit**

```bash
git add ts-diagnose/scripts/engine_common.py ts-diagnose/playbooks/ ts-diagnose/scripts/tests/test_materials.py
git commit -m "feat(ts-diagnose): 阶段闸——chart 阶段 done_when 强制含 INDEX.md，加载期校验"
```

---

## Phase 2：model-audit playbook + provider 接线

### Task 5: 迁入 model-audit playbook（原 pv-model-analysis）

**Files:**
- Create: `ts-diagnose/playbooks/model-audit/playbook.md`
- Move: `pv-model-analysis/references/{machinery,models-template,output-spec,cross-skill-contract}.md` → `ts-diagnose/playbooks/model-audit/references/`
- Move: `pv-model-analysis/scripts/{pointer.py, profile_data.py, read_pptx.py, test_pointer.py, test_profile_data_smoke.py}` → `ts-diagnose/playbooks/model-audit/scripts/`
- Test: 迁移后的 `test_pointer.py` 增一用例（receipt）

- [ ] **Step 1: git mv 迁移**

```bash
mkdir -p ts-diagnose/playbooks/model-audit
git mv pv-model-analysis/references ts-diagnose/playbooks/model-audit/references
git mv pv-model-analysis/scripts ts-diagnose/playbooks/model-audit/scripts
```

- [ ] **Step 2: pointer.py 加 receipt——写失败测试**（迁移后的 `test_pointer.py` 追加）

```python
def test_write_receipt(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    import pointer
    pointer.write_receipt(modelmap_dir=str(tmp_path / "repo/.modelmap"),
                          commit="abc1234")
    rec = json.load(open("MODELMAP_RECEIPT.json", encoding="utf-8"))
    assert rec["modelmap_dir"].endswith(".modelmap")
    assert rec["commit"] == "abc1234" and rec["date"]
```

Run: `python3 -m pytest ts-diagnose/playbooks/model-audit/scripts/test_pointer.py -q` → FAIL

- [ ] **Step 3: 实现 `write_receipt`**（pointer.py 追加；工作目录回执 = 阶段闸的产物判据）

```python
def write_receipt(modelmap_dir, commit, path="MODELMAP_RECEIPT.json"):
    """在诊断工作目录写回执——orient 用它判定 model-audit 阶段完成与档案新鲜度。"""
    import datetime as _dt
    rec = {"modelmap_dir": modelmap_dir, "commit": commit,
           "date": _dt.date.today().isoformat()}
    with open(path, "w", encoding="utf-8") as f:
        json.dump(rec, f, ensure_ascii=False, indent=2)
    return rec
```

Run 同上 → PASS

- [ ] **Step 4: 写 playbook.md**（frontmatter 完整如下；正文 = 原 `pv-model-analysis/SKILL.md` 的 Step 0-5 与「纪律」节原样搬入，仅两处改写：①「M1-M4 + ensemble + Chronos」等产线专名改为「模型清单来自 intake 问答或 project-context 实验线」；②文内 `references/` 相对路径保持有效——已随迁同目录）

```yaml
---
id: model-audit
name: 模型代码审计（生成 .modelmap 档案）
goal: 把模型代码目录固化为「代码锚定」的模型参考档案（.modelmap/ + 工作目录回执），供其他 playbook 机制归因消费
materials:
  required: [model_code]
  optional: [train_y, experiment_config, data_profile]
stages:
  - id: 0
    name: 定位模型（先问后花）
    done_when: {manual: true}
  - id: 1
    name: 数据画像（可选）
    done_when: {artifacts: ["data-profile-receipt.json"]}
  - id: 2
    name: 逐模型三层抽取（工程/数学/桥接）
    done_when: {manual: true}
    prereqs:
      - desc: 模型清单已与用户确认
        check: "stage:0"
  - id: 3
    name: reconcile + 落盘 + 回执
    done_when: {artifacts: ["MODELMAP_RECEIPT.json"]}
    prereqs:
      - desc: 抽取完成
        check: "stage:2"
  - id: 4
    name: 自检（machinery §5）
    done_when: {artifacts: ["AUDIT_SELFCHECK.md"]}
    subagent_ok: false
    prereqs:
      - desc: 已落盘
        check: "stage:3"
variants:
  - id: data-profile
    when: "material:train_y"
    unlocks_stages: [1]
questions:
  - id: production-version
    stage: 0
    ask: "代码里发现多个候选版本/副本时，哪个是产线版本？（绝不自行裁决）"
    why: "分析错版本 = 整套档案作废"
    default: null
---
```

正文另加一节「回执纪律」：Stage 3 落盘 `.modelmap/` 后必须调
`python3 <本目录>/scripts/pointer.py`（原 write_pointer 流程）**并** 在诊断工作目录
`write_receipt(modelmap_dir, commit)`；Stage 1 跑 `profile_data.py` 后写
`data-profile-receipt.json`（内容 `{"profile_md": <路径>, "date": ...}`）。

- [ ] **Step 5: 验证加载 + 全量测试**

```bash
python3 -c "
import sys; sys.path.insert(0, 'ts-diagnose/scripts')
import engine_common as ec
fm = ec.load_frontmatter(ec.find_playbook('model-audit')); print(fm['id'], len(fm['stages']))"
python3 -m pytest ts-diagnose/ pv-*/ -q
```
Expected: `model-audit 5`；pytest PASS

- [ ] **Step 6: Commit** → `git commit -m "feat(ts-diagnose): model-audit playbook 迁入——原 pv-model-analysis 全流程 + 工作目录回执"`

### Task 6: provider 接线——provider_playbook + modelmap 全局阻塞

**Files:**
- Modify: `ts-diagnose/scripts/engine_common.py`（`context_embed_hint` + 新 `modelmap_blocker`）
- Modify: `ts-diagnose/scripts/orient.py`（前置段插入）
- Modify: `ts-diagnose/references/intake.md`（model_code 节 provider 文案）
- Test: `test_materials.py` / `test_orient_materials.py` 追加

**Interfaces:**
- Produces: `context_embed_hint` 认 `provider_playbook` 键（文案「内联执行 playbook『model-audit』」）；`modelmap_blocker(cfg, fm) -> str|None`——`model_code present` 且工作目录无 `MODELMAP_RECEIPT.json` 且 `fm.id != "model-audit"` → 返回阻塞文案；orient 把它打成 ✗ 前置（不齐则不可开工）。

- [ ] **Step 1: 写失败测试**

```python
# test_materials.py 追加
def test_context_embed_hint_provider_playbook():
    cx = {**{k: v for k, v in CX.items() if k != "provider_skill"},
          "provider_playbook": "model-audit"}
    hint = ec.context_embed_hint(cx, {"materials": {"model_code": {"status": "present"}}})
    assert "model-audit" in hint and "嵌入" in hint


def test_modelmap_blocker(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    cfg = {"materials": {"model_code": {"status": "present", "paths": ["/repo"]}}}
    fm_diag = {"id": "model-comparison"}
    assert ec.modelmap_blocker(cfg, fm_diag) is not None      # 无回执 → 阻塞
    (tmp_path / "MODELMAP_RECEIPT.json").write_text(
        '{"modelmap_dir": "x", "commit": "abc"}', encoding="utf-8")
    assert ec.modelmap_blocker(cfg, fm_diag) is None          # 有回执 → 放行
    assert ec.modelmap_blocker(cfg, {"id": "model-audit"}) is None  # 自身豁免
    assert ec.modelmap_blocker({}, fm_diag) is None           # 无 model_code → 不管
```

Run → FAIL

- [ ] **Step 2: 实现**

`context_embed_hint` 里 `prov = cx.get("provider_skill")` 改为：

```python
    prov = cx.get("provider_playbook") or cx.get("provider_skill")
    kind = "playbook" if cx.get("provider_playbook") else "技能"
```
文案里 `技能「{prov}」` 改 `{kind}「{prov}」`。

新函数（materials 段末尾）：

```python
def modelmap_blocker(cfg, fm):
    """模型档案强制衔接（spec §4）：有模型代码就必须先有 .modelmap 回执。"""
    if (fm or {}).get("id") == "model-audit":
        return None
    if material_status(cfg, "model_code") != "present":
        return None
    if os.path.exists("MODELMAP_RECEIPT.json"):
        return None
    return ("有模型代码（model_code=present）但无 .modelmap 档案回执——"
            "先嵌入执行 playbook「model-audit」生成档案（MODELMAP_RECEIPT.json），"
            "再回本 playbook 继续")
```

orient.py target 前置打印段（`for mid, reason in mat_blocked:` 之后）加：

```python
        mm = ec.modelmap_blocker(cfg, fm)
        if mm:
            print(f"  [✗] {mm}")
```
并把「可开工」判定 `if ec.prereqs_ok(pr) and not blocked_qs and not mat_blocked:` 扩成 `... and not mm`。

- [ ] **Step 3: 端到端用例**（test_orient_materials.py：model_code present + 无回执 → 输出含 `model-audit` 且无「可开工」；touch 回执后重跑 → 「可开工」出现）

- [ ] **Step 4: intake.md model_code 节**：`provider_skill: pv-model-analysis` 提示改为「（present 时 orient 会强制先跑 playbook `model-audit` 生成档案回执，见 modelmap_blocker）」。test_orient_materials.py 的 PB 模板 `provider_skill: pv-model-analysis` 改 `provider_playbook: model-audit`。

- [ ] **Step 5: 全量测试** → `python3 -m pytest ts-diagnose/ pv-*/ -q` PASS

- [ ] **Step 6: Commit** → `git commit -m "feat(ts-diagnose): provider_playbook + modelmap 全局阻塞——有模型代码必先出档案"`

---

## Phase 3：result-eval 与 subset-influence 迁入

> 两个 Task 同构：先从源技能的 `run_orient.py` 抽阶段真源，再搬 scripts/正文。执行者不得凭记忆写阶段表——必须照源文件抄。

### Task 7: result-eval playbook（原 pv-result-analysis）

**Files:**
- Create: `ts-diagnose/playbooks/result-eval/playbook.md`
- Move: `pv-result-analysis/scripts/{data_utils,plots,run_analysis,run_drift,run_quality_check}.py` → `ts-diagnose/playbooks/result-eval/scripts/`（`run_orient.py` 不迁——其职责由引擎 orient 承接，抽完阶段表后随壳删除）
- Move: `pv-result-analysis/references/` → `ts-diagnose/playbooks/result-eval/references/`

- [ ] **Step 1: 抽阶段真源**：`sed -n '1,160p' pv-result-analysis/scripts/run_orient.py`，找到阶段定义（阶段名 + 完成判据文件 + 顺序）。把每个阶段翻译成 frontmatter 条目：源码里「检测文件 X 存在则该阶段完成」→ `done_when: {artifacts: ["X"]}`，人工确认类阶段 → `manual: true`。

- [ ] **Step 2: 写 frontmatter**（骨架如下；stages 列表以 Step 1 抽取结果为准填满，画图阶段必须 `charts:` + artifacts 含 `INDEX.md`（Task 4 校验会逼你），结论阶段 artifacts=`["CONCLUSION.md"]`）：

```yaml
---
id: result-eval
name: 预测结果评估与归因
goal: 评估一次预测结果（指标口径可配，默认 rmse_192），画标准图集，把指标变化归因到时段/单元/输入
materials:
  required: [predict, truth]
  optional: [features, train_y, model_code, training_log, experiment_config]
stages:
  # ← Step 1 抽取的阶段表，逐条填
questions:
  - id: metric-caliber
    stage: 0
    ask: "考核口径是什么？（默认 rmse_192=每行全部 horizon 点的 RMSE）"
    why: "口径不同结论可反转"
    options: ["rmse_192（默认）", "指定子段", "自定义公式"]
    default: "rmse_192"
contexts:
  - id: model-profile
    name: 模型架构档案
    workdir_key: modelmap_dir
    status_key: modelmap_status
    marker_files: [models.md]
    on_absent: ask
    provider_playbook: model-audit
    trigger_material: model_code
---
```

- [ ] **Step 3: 正文搬运与泛化**：`pv-result-analysis/SKILL.md` + references 的阶段菜谱按阶段搬进 playbook.md 正文。改写规则（机械执行）：
  1. 「光伏/电站/station」→「预测单元（unit）」，站点专名一律删除或改「见 project-context 注册表」；
  2. `metric.py` 五口径叙述 → 「口径由 metric-caliber 问题决定，默认 rmse_192；专项口径定义在 project-context」；
  3. M1-M4/ensemble 专名 → 「模型集来自 intake 的 predict 材料盘点」；
  4. 原「自带续跑（run_orient.py）」小节整段删除——由引擎 orient 承接；
  5. 脚本调用路径改 `<本 playbook 目录>/scripts/...`。

- [ ] **Step 4: scripts 迁移 + import 修复**

```bash
mkdir -p ts-diagnose/playbooks/result-eval
git mv pv-result-analysis/references ts-diagnose/playbooks/result-eval/references
mkdir -p ts-diagnose/playbooks/result-eval/scripts
for f in data_utils plots run_analysis run_drift run_quality_check; do
  git mv pv-result-analysis/scripts/$f.py ts-diagnose/playbooks/result-eval/scripts/
done
grep -rn "import\|from" ts-diagnose/playbooks/result-eval/scripts/*.py | grep -v "^.*#"   # 检查相互引用，同目录 import 不用改
```

- [ ] **Step 5: 验证**：`load_frontmatter` 冒烟（同 Task 5 Step 5 命令，id 换 result-eval）+ 临时目录端到端：五件套 cfg 齐 + `--playbook result-eval` 跑 orient，输出含 Stage 列表与图表选择门。`python3 -m pytest ts-diagnose/ pv-*/ -q` PASS。

- [ ] **Step 6: Commit** → `git commit -m "feat(ts-diagnose): result-eval playbook 迁入——pv-result-analysis 方法泛化，续跑由引擎承接"`

### Task 8: subset-influence playbook（原 pv-station-influence）

**Files:**
- Create: `ts-diagnose/playbooks/subset-influence/playbook.md`
- Move: `pv-station-influence/scripts/{si_common,probe_logs,loss_dynamics,influence_regression,replay_assignments,ckpt_eval,tracin_influence,adapter_template}.py` + `test_probe_station_pat.py, test_si_common_mismatch.py` → `ts-diagnose/playbooks/subset-influence/scripts/`
- Move: `pv-station-influence/references/` → `ts-diagnose/playbooks/subset-influence/references/`

- [ ] **Step 1: 抽阶段真源**：同 Task 7 Step 1，源 = `pv-station-influence/scripts/run_orient.py`（六阶段 + Mode A/B 判定逻辑）。Mode B 翻译成变体：

```yaml
materials:
  required: [training_log, predict, truth]
  optional: [checkpoint, experiment_config, model_code]
variants:
  - id: mode-b
    when: "material:checkpoint"
    unlocks_stages: [<梯度/重训确认阶段的 id，照源阶段表填>]
contexts:
  - id: heldout-eval
    name: 留出单元的 result-eval 产物
    workdir_key: heldout_eval_dir
    status_key: heldout_eval_status
    marker_files: [CONCLUSION.md]
    on_absent: ask
    provider_playbook: result-eval
```

- [ ] **Step 2: 正文搬运与泛化**：改写规则同 Task 7 Step 3，外加：「站点/station」→「训练条目/数据子集（entry）」；实验设定（条目全集/留出/chunk 方案）叙述 → 「经 experiment_config 材料 + project-context 实验线载入」。

- [ ] **Step 3: scripts 迁移**（git mv 同构）；`test_probe_station_pat.py` 等两个测试文件里的 import 路径核对（同目录不需改）。

- [ ] **Step 4: 验证**：frontmatter 冒烟 + `python3 -m pytest ts-diagnose/ pv-*/ -q` PASS（两个随迁测试必须仍被 pytest 收集到——`pytest --collect-only -q | grep si_common` 确认）。

- [ ] **Step 5: Commit** → `git commit -m "feat(ts-diagnose): subset-influence playbook 迁入——站点影响力归因泛化为条目/子集"`

---

## Phase 4：feature-blame 方法并入 feature-importance

### Task 9: scripts/golden 迁移 + 变体阶段

**Files:**
- Move: `pv-feature-blame/scripts/*.py`（含全部 test_*.py，除 `run_orient.py`）→ `ts-diagnose/playbooks/feature-importance/scripts/`
- Move: `pv-feature-blame/golden/` → `ts-diagnose/playbooks/feature-importance/golden-feature-blame/`
- Move: `pv-feature-blame/references/`（含 prompt-template.md）→ `ts-diagnose/playbooks/feature-importance/references/`
- Modify: `ts-diagnose/playbooks/feature-importance/playbook.md`

- [ ] **Step 1: 迁移**

```bash
mkdir -p ts-diagnose/playbooks/feature-importance/scripts
for f in pv-feature-blame/scripts/*.py; do
  [ "$(basename $f)" = "run_orient.py" ] || git mv "$f" ts-diagnose/playbooks/feature-importance/scripts/
done
git mv pv-feature-blame/golden ts-diagnose/playbooks/feature-importance/golden-feature-blame
git mv pv-feature-blame/references ts-diagnose/playbooks/feature-importance/references
```

- [ ] **Step 2: 测试路径修复并确认全被收集**：`python3 -m pytest ts-diagnose/playbooks/feature-importance/scripts/ -q` → 原 pv-feature-blame 的用例数全对上（迁移前先 `pytest pv-feature-blame -q` 记住数字）。golden 路径若在测试里是相对 `../golden`，改为 `../golden-feature-blame`。

- [ ] **Step 3: playbook.md 扩展**：frontmatter `materials.optional` 加 `[feature_true, serving_api]`（保留原有），追加变体与阶段（阶段 id 接在现有阶段之后，编号照现有 playbook 顺延）：

```yaml
variants:
  - id: feature-quality
    when: "material:feature_true"
    unlocks_stages: [<新阶段A id>]
  - id: counterfactual
    when: "material:serving_api"
    unlocks_stages: [<新阶段B id>]
stages:
  # ...现有阶段不动，追加：
  - id: <A>
    name: 预测特征质量归因（feature_true 对照）
    done_when: {artifacts: ["feature_blame_report.json"]}
  - id: <B>
    name: 反事实验证（预算阶梯）
    done_when: {artifacts: ["cf_summary.json"]}
    prereqs:
      - desc: 特征质量归因已点名
        check: "stage:<A>"
```

正文新增两节，内容从 `pv-feature-blame/SKILL.md` 搬运泛化（改写规则同 Task 7 Step 3）：①「两口径坏行 → 逐行 z 分数 + 全局校准 ρ 双关点名（防冤枉）+ 翻新跳变 churn 两关」；②「反事实预算阶梯：oracle G 闸 → minimal-set → lattice Shapley → neighbor-swap，决策逻辑 `scripts/cf_logic.py`」。硬规则保留原话：**feature_true 材料 unknown 时本变体不解锁——由入口闸的 intake 盘点解决，绝不静默降级**。

- [ ] **Step 4: 全量测试** → `python3 -m pytest ts-diagnose/ pv-*/ -q` PASS

- [ ] **Step 5: Commit** → `git commit -m "feat(ts-diagnose): feature-blame 方法并入 feature-importance——feature_true/serving_api 材料驱动变体解锁"`

---

## Phase 5：结论闸 + 删壳 + 路由收口

### Task 10: conclusion_gate.py（结论闸）

**Files:**
- Create: `ts-diagnose/scripts/conclusion_gate.py`
- Test: `ts-diagnose/scripts/tests/test_conclusion_gate.py`

**Interfaces:**
- Produces: CLI `python3 <ENGINE>/scripts/conclusion_gate.py`（在工作目录跑）。全过 → 写 `gate_reports/conclusion_gate.json`（含 CONCLUSION.md 的 sha256），exit 0；任一不过 → 打印缺什么，exit 1，不写 receipt。校验规则：
  1. `CONCLUSION.md` 存在且含 `## 模型结构依据` 节；
  2. 该节含桥接锚（regex `H-?\d+` 或 `.modelmap` 或 `file:\d+`）**或** 降级声明（同时含 `absent-confirmed` 与 `降级`）；
  3. playbook 有 chart 阶段时：CONCLUSION.md 中被引用的图表路径（regex 提取 `[\w./_-]+\.(png|svg|json)`，取存在于 `charts:` 声明产物目录下的引用）≥1 且**每一条引用的路径都真实存在**（引用不存在的图 = 立即 fail）。

- [ ] **Step 1: 写失败测试**

```python
"""结论闸测试：subprocess 跑真 gate，断言 exit code 与 receipt。"""
import json
import os
import subprocess
import sys

SCRIPTS_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
GATE = os.path.join(SCRIPTS_DIR, "conclusion_gate.py")
sys.path.insert(0, SCRIPTS_DIR)
import engine_common as ec  # noqa: E402

PB = """---
id: gate-demo
name: g
goal: g
stages:
  - id: 0
    name: 图
    done_when: {artifacts: ['charts/*.json', 'INDEX.md']}
    charts: [error-breakdown]
  - id: 1
    name: 结论
    done_when: {artifacts: ['CONCLUSION.md']}
---
"""

GOOD = """# 结论
误差集中在 horizon 末段（见 charts/error-breakdown.png）。
## 模型结构依据
档案 H3：attention 窗口 96 点 → 预期长时效退化，与 charts/error-breakdown.png 一致。
"""


def setup(tmp_path, conclusion, with_chart=True):
    pb = tmp_path / "pb" / "playbook.md"
    pb.parent.mkdir()
    pb.write_text(PB, encoding="utf-8")
    ec.dump_json({"playbook": str(pb)}, str(tmp_path / "diagnose_config.json"))
    if with_chart:
        (tmp_path / "charts").mkdir()
        (tmp_path / "charts" / "error-breakdown.png").write_bytes(b"png")
    if conclusion is not None:
        (tmp_path / "CONCLUSION.md").write_text(conclusion, encoding="utf-8")
    return tmp_path


def run_gate(wd):
    return subprocess.run([sys.executable, GATE], cwd=wd,
                          capture_output=True, text=True, timeout=60)


def test_pass_writes_receipt(tmp_path):
    wd = setup(tmp_path, GOOD)
    r = run_gate(wd)
    assert r.returncode == 0, r.stdout + r.stderr
    rec = json.load(open(wd / "gate_reports" / "conclusion_gate.json"))
    assert rec["passed"] is True and rec["conclusion_sha256"]


def test_fail_missing_structure_section(tmp_path):
    wd = setup(tmp_path, "# 结论\n没依据。\n")
    r = run_gate(wd)
    assert r.returncode == 1
    assert "模型结构依据" in r.stdout
    assert not (wd / "gate_reports" / "conclusion_gate.json").exists()


def test_degraded_statement_accepted(tmp_path):
    c = ("# 结论\n（见 charts/error-breakdown.png）\n## 模型结构依据\n"
         "模型档案缺失（materials.model_code = absent-confirmed），结构性解释降级为猜测级。\n")
    assert run_gate(setup(tmp_path, c)).returncode == 0


def test_fail_cited_chart_missing(tmp_path):
    bad = GOOD.replace("error-breakdown.png", "no-such-chart.png")
    wd = setup(tmp_path, bad)
    r = run_gate(wd)
    assert r.returncode == 1 and "no-such-chart.png" in r.stdout


def test_fail_no_chart_citation_when_chart_stage(tmp_path):
    c = "# 结论\n直觉归因。\n## 模型结构依据\n档案 H1 支持。\n"
    r = run_gate(setup(tmp_path, c))
    assert r.returncode == 1 and "图" in r.stdout
```

Run: `python3 -m pytest ts-diagnose/scripts/tests/test_conclusion_gate.py -q` → FAIL（无脚本）

- [ ] **Step 2: 实现 conclusion_gate.py**

```python
#!/usr/bin/env python3
"""结论闸（三道闸之三）：CONCLUSION.md 交付前的机械校验。
全过 → 写 gate_reports/conclusion_gate.json（唯一合法生成方式），exit 0；
否则打印缺项 exit 1。结论阶段的 done_when 依赖该 receipt（playbook 声明）。"""
from __future__ import annotations

import hashlib
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import engine_common as ec

SECTION = "## 模型结构依据"
ANCHOR_RE = re.compile(r"(H-?\d+|\.modelmap|file:\d+)")
CHART_REF_RE = re.compile(r"[\w./_-]+\.(?:png|svg|json)")


def fail(msg):
    print(f"✗ 结论闸不过：{msg}")
    sys.exit(1)


def main():
    cfg = ec.load_config() or {}
    if not cfg.get("playbook"):
        fail("无 diagnose_config.json 或未绑定 playbook")
    fm = ec.load_frontmatter(ec.find_playbook(cfg["playbook"]))
    if not os.path.exists("CONCLUSION.md"):
        fail("CONCLUSION.md 不存在")
    text = open("CONCLUSION.md", encoding="utf-8").read()

    # 规则 1+2：模型结构依据节
    if SECTION not in text:
        fail(f"缺「{SECTION}」节——结论必须挂到架构事实或显式降级")
    sec = text.split(SECTION, 1)[1].split("\n## ", 1)[0]
    degraded = ("absent-confirmed" in sec and "降级" in sec)
    if not (ANCHOR_RE.search(sec) or degraded):
        fail("「模型结构依据」节既无桥接锚（H-id / .modelmap / file:行号），"
             "也无降级声明（须同时含 absent-confirmed 与 降级）")

    # 规则 3：图证据（仅 playbook 有 chart 阶段时）
    if ec.has_chart_stage(fm):
        cited = [c for c in CHART_REF_RE.findall(text) or []]
        cited = [c for c in set(CHART_REF_RE.findall(text))
                 if c.split("/")[0] in ("charts",) or c.startswith("charts")]
        if not cited:
            fail("本 playbook 有图表阶段，但结论未引用任何 charts/ 产物——归因必须有图支撑")
        missing = [c for c in cited if not os.path.exists(c)]
        if missing:
            fail(f"结论引用了不存在的图：{missing}")

    os.makedirs("gate_reports", exist_ok=True)
    ec.dump_json({"passed": True,
                  "conclusion_sha256": hashlib.sha256(text.encode()).hexdigest()},
                 os.path.join("gate_reports", "conclusion_gate.json"))
    print("✓ 结论闸通过，receipt 已写 gate_reports/conclusion_gate.json")


if __name__ == "__main__":
    main()
```

注意 `CHART_REF_RE.findall` 带分组会只返回分组——用 `(?:...)` 非捕获（如上），并删掉重复的 cited 行（实现时以测试为准收敛）。

Run → PASS（六个用例全绿）

- [ ] **Step 3: 结论阶段接线**：所有 9 个 playbook 的结论阶段（done_when 含 `CONCLUSION.md` 的）artifacts 追加 `"gate_reports/conclusion_gate.json"`；orient.py 的「三道门自检」打印块末尾加一行：

```python
            print("    收尾后必须跑：python3 <ENGINE>/scripts/conclusion_gate.py"
                  "（不过则结论不算交付，receipt 是本阶段完成判据）")
```

- [ ] **Step 4: 全量测试** → `python3 -m pytest ts-diagnose/ pv-*/ -q` PASS

- [ ] **Step 5: Commit** → `git commit -m "feat(ts-diagnose): 结论闸——模型结构依据+图证据机械校验，receipt 即完成判据"`

### Task 11: 删壳 + 技能链接收口

**Files:**
- Delete: `pv-model-analysis/ pv-result-analysis/ pv-station-influence/ pv-feature-blame/`（此时只剩 SKILL.md/CHANGELOG 等壳文件）
- Modify: `~/.claude/skills/` 链接

- [ ] **Step 1: 确认壳里已无未迁文件**：`find pv-* -type f | grep -v __pycache__`——除 SKILL.md / CHANGELOG.md / run_orient.py / README.md 外若还有别的，回对应 Phase 补迁，不许直接删。

- [ ] **Step 2: 删除**

```bash
git rm -r pv-model-analysis pv-result-analysis pv-station-influence pv-feature-blame
rm ~/.claude/skills/pv-feature-blame ~/.claude/skills/pv-result-analysis \
   ~/.claude/skills/pv-station-influence ~/.claude/skills/pv-analysis-resume \
   ~/.claude/skills/pv-model-verify        # 后两个本就是悬空链接
ln -sfn "/Users/tqa946816/Documents/华为/光伏预测/结果分析skill/ts-diagnose" ~/.claude/skills/ts-diagnose
ls -la ~/.claude/skills/
```
Expected: 只剩 find-skills / web-design-guidelines / ts-diagnose（→ 仓库路径）。
**注**：ts-diagnose 此前从未链接进 `~/.claude/skills`——这是本次路由失灵的隐性原因之一，此步是修复不是顺手。

- [ ] **Step 3: 全量测试** → `python3 -m pytest ts-diagnose/ -q` PASS（pv 目录已不在）

- [ ] **Step 4: Commit** → `git commit -m "refactor: 删除四个 pv-* 技能壳——方法已全部下沉 ts-diagnose playbook"`

### Task 12: SKILL.md 路由重写 + 文档收口

**Files:**
- Modify: `ts-diagnose/SKILL.md`（description + 路由表 +3 行）
- Modify: `ts-diagnose/CHANGELOG.md`、`README.md`（仓库根）
- Test: `test_layering.py`、`test_routing.py`

- [ ] **Step 1: description 重写**（frontmatter 单行）：删除全部「负面清单」与 pv-* 让位条款，改为正面枚举 9 个 playbook 触发词（training-sufficiency/robustness/feature-importance 含特征质量归因与反事实/model-comparison/deployment-drift/fact-scan/model-audit「分析模型代码/生成模型档案」/result-eval「评估预测结果/指标/月度归因」/subset-influence「哪个条目拖累留出目标/负迁移」）。保留句式：「已固化代理技能（经 crystallize 产出）若覆盖当前场景则优先级最高」。

- [ ] **Step 2: 路由表加 3 行**：

```markdown
| 评估一次预测结果 / 算指标（默认 rmse_192）/ 月度或时段归因 / 深度分析 | `result-eval` |
| 给定模型代码目录：分析模型/生成模型档案/核验描述与代码一致 | `model-audit` |
| N 个训练条目里哪些拖累留出目标（负迁移）/ chunk loss 震荡解释 | `subset-influence` |
```

路由优先级节从三级改两级：固化代理技能 > 本引擎。

- [ ] **Step 3: 守卫测试**：`python3 -m pytest ts-diagnose/scripts/tests/test_layering.py ts-diagnose/scripts/tests/test_routing.py -q`——test_routing 若断言旧的负面清单/优先级文案，按新契约更新断言（新断言至少含：description 出现全部 9 个 playbook id；SKILL.md ≤60 行）。

- [ ] **Step 4: CHANGELOG + README**：CHANGELOG 记本轮（单入口化 + 三道闸 + 4 技能收编）；仓库根 README.md 的技能清单章节改为单技能 + 9 playbook 表。

- [ ] **Step 5: 全量测试** → `python3 -m pytest ts-diagnose/ -q` PASS

- [ ] **Step 6: Commit** → `git commit -m "feat(ts-diagnose): 路由收口——单入口 9 playbook，两级优先级，文档同步"`

### Task 13: 端到端冒烟 + 记忆更新

- [ ] **Step 1: 弱模型场景端到端冒烟**（临时目录，模拟这次翻车路径）：
  1. 空目录跑 `orient.py --playbook model-comparison` → 必须 BLOCKED 且不见 Stage 菜单；
  2. 写全五件套 + predict/truth（present+schema）→ orient 出 Stage 0；
  3. `--goto 4` → 必须 ⛔ 拒绝；
  4. 造 CONCLUSION.md（无模型结构依据节）跑 conclusion_gate → exit 1。
  四步结果记入 `ts-diagnose/CHANGELOG.md` 验证段。

- [ ] **Step 2: 全仓测试终验** → `python3 -m pytest ts-diagnose/ -q`，输出计数记 CHANGELOG。

- [ ] **Step 3: 更新 auto-memory**（主 agent 在会话里做，非仓库文件）：`pv-forecast-result-analysis-skill.md` 与 `MEMORY.md` 改写为单入口 ts-diagnose + 三道闸现状；`station-influence-17-stations.md` 指向 subset-influence。

- [ ] **Step 4: Commit + push**（用户确认后）

```bash
git add -A && git commit -m "docs(ts-diagnose): 三道闸端到端冒烟记录 + 收编工程收口"
```

---

## Self-Review 结果

- **Spec 覆盖**：§1 拓扑=Task 5/7/8/9/11/12；§2 入口闸=Task 1/2；§3 阶段闸=Task 3/4（+§3.4 联动在 Task 10 规则 3）；§4 model-audit=Task 5/6；§5 下沉=Task 9；§6 结论闸=Task 10；§7 对照表=三闸各 Task；§8 顺序=Phase 1-5 一一对应；§9 测试=各 Task Step + Task 13。无缺口。
- **已知取舍**（执行者勿"顺手修复"）：① receipt 过期（CONCLUSION.md 改了没重跑 gate）只靠 orient 提醒行 + sha 字段，不做强校验——YAGNI，出问题再加；② profile 固化的 absent-confirmed 记录 source=profile 会被入口闸打回重问——有意为之（"没有"必须每次由用户亲口确认）；③ 其余 4 个旧 playbook 不在本轮补 stage manifest。
- **类型一致性**：`intake_blockers` 返回 `[(mid, reason)]` 与 orient/测试用法一致；`write_receipt`/`modelmap_blocker` 的 `MODELMAP_RECEIPT.json` 文件名两处一致；`provider_playbook` 键名在 Task 6/7/8 一致。
