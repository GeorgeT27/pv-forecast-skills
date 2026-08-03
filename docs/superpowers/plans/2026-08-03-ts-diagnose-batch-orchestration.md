# ts-diagnose 批量编排层 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 给 ts-diagnose 加一个 Layer -1 批量编排层，让用户一次在同一份数据上并行诊断多条 level-2 playbook，把 2×N 个人机停顿收敛成 2 个。

**Architecture:** 新增纯函数脚本 `scripts/batch.py`（计划器 + 从磁盘派生状态的汇聚器，不派发/不跑生产者）；主 agent 照 `references/batch-orchestration.md` 的五阶段协议驱动（提问、派发 subagent、合并停顿、结论）。batch.py 复用 `engine_common` 的 frontmatter/产物 API，与 `orient.py`（单 playbook 求值器）职责不重叠。

**Tech Stack:** Python 3（stdlib + PyYAML，经 `engine_common` 间接使用）；pytest；无新增第三方依赖。

## Global Constraints

- **复用 `engine_common`（导入为 `ec`），不重复实现**：`load_frontmatter` / `find_playbook` / `playbook_dir` / `products_index` / `product_status(cfg, pid)` / `read_json`（缺文件返回 `None`）/ `dump_json`（`ensure_ascii=False, indent=2`）/ `PLAYBOOKS_DIR` / `PENDING`。
- **单写者纪律**：`batch_plan.json` 只由 `batch.py` 写；`batch_config.json` / `BATCH_PROGRESS.md` / `BATCH_REPORT.md` 只由主 agent 写；`batch_state.json` 只由 `batch.py --mark` 写；subagent 只写自己的 `phenomena_<pb>.json`。
- **status 派生自磁盘，绝不手写伪造完成**：`compute-done`（存在 `<pb>/phenomena_<pb>.json`）与 `done`（存在 `<pb>/CONCLUSION.md` 且 `<pb>/gate_reports/conclusion_gate.json`）永远从磁盘产物算；`running`/`failed` 是 `batch_state.json` 的瞬态标注，一旦磁盘出现产物，磁盘判定覆盖标注。
- **status 保留字**：`pending / running / compute-done / done / failed`，别处不得自造。
- **SKILL.md 是 Layer 0 路由层，受 `test_layering.py` 硬守**：改后必须仍 ≤60 行、≤6000 token、不含方法词汇（含 `Stage` `done_when` `pause_after` `evidence_lines` `findings_marker`）、`references/` 引用只允许 `engine-core.md` 与 `crystallize.md`。**因此 SKILL.md 不得直接引用 `batch-orchestration.md`**——批量协议指针放进 `engine-core.md`（命中即加载，不受该守卫约束）。
- **测试沙箱模式**（照 `scripts/tests/test_products.py`）：`sys.path.insert(0, SCRIPTS_DIR); import engine_common as ec`；用合成 playbook 字符串 + `_write_pb` + `monkeypatch.setattr(ec, "PLAYBOOKS_DIR", str(d))` + `monkeypatch.chdir(tmp_path)`，不依赖真实 playbook 内容。
- **技能文档零解释风格**（用户偏好）：`references/batch-orchestration.md`、`SKILL.md` 每句只许是指令或执行所需事实，不写术语表/设计动机/教训故事。
- **每个 stage 落盘、随时断点续跑**；`batch.py` 每次调用重扫工作目录重算，不信记忆。

---

## Task 1: batch.py 脚手架 + `producer_union`

**Files:**
- Create: `ts-diagnose/scripts/batch.py`
- Test: `ts-diagnose/scripts/tests/test_batch.py`

**Interfaces:**
- Consumes: `ec.products_index()` → `{pid: {playbook, manifest, marker_files}}`；`ec.load_frontmatter(path)`；`ec.find_playbook(id)`。
- Produces: `phenomena_name(pid: str) -> str`；`producer_union(playbook_ids: list[str]) -> list[str]`（选中 playbook 的 `upstream` 产物 id 并集，sorted unique）；模块常量 `BATCH_CONFIG="batch_config.json"`、`BATCH_PLAN="batch_plan.json"`、`BATCH_STATE="batch_state.json"`。

- [ ] **Step 1: Write the failing test**

在 `test_batch.py` 顶部放沙箱基建（合成 playbook + fixture），并写第一个测试：

```python
"""batch.py：Layer -1 批量计划器测试。全部在 tmp 沙箱 playbooks 目录里跑
（monkeypatch ec.PLAYBOOKS_DIR），不依赖真实 playbook 内容。"""
import os
import sys

import pytest

SCRIPTS_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, SCRIPTS_DIR)
import engine_common as ec  # noqa: E402
import batch  # noqa: E402

PRODUCER = """\
---
id: setup-prod
name: 生产者
goal: 产 setup
produces:
  id: setup
  manifest: setup_manifest.json
  marker_files: [predictions.csv]
stages:
  - id: 0
    name: 做事
    done_when: {artifacts: ["predictions.csv"]}
questions:
  - id: freq
    stage: 0
    ask: 步长?
    why: schema
    default: null
---
正文
"""

def _consumer(pid, qid):
    return f"""\
---
id: {pid}
name: 消费者{pid}
goal: 消费 setup
upstream:
  - product: setup
    required: true
stages:
  - id: 0
    name: 计算
    done_when: {{artifacts: ["m.json"]}}
    subagent_ok: true
  - id: 1
    name: 事实提取
    done_when: {{artifacts: ["{batch.phenomena_name(pid)}"]}}
    pause_after: true
    subagent_ok: true
questions:
  - id: {qid}
    stage: 0
    ask: 问 {qid}?
    why: w
    default: null
---
正文
"""

def _write_pb(root, pid, text):
    d = root / pid
    d.mkdir(parents=True, exist_ok=True)
    (d / "playbook.md").write_text(text, encoding="utf-8")
    return str(d / "playbook.md")

@pytest.fixture
def pbdir(tmp_path, monkeypatch):
    d = tmp_path / "playbooks"
    _write_pb(d, "setup-prod", PRODUCER)
    _write_pb(d, "pb-x", _consumer("pb-x", "口径"))
    _write_pb(d, "pb-y", _consumer("pb-y", "阈值"))
    monkeypatch.setattr(ec, "PLAYBOOKS_DIR", str(d))
    monkeypatch.chdir(tmp_path)
    return d

def test_producer_union_dedups_upstream(pbdir):
    assert batch.producer_union(["pb-x", "pb-y"]) == ["setup"]

def test_phenomena_name(pbdir):
    assert batch.phenomena_name("pb-x") == "phenomena_pb-x.json"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd ts-diagnose && python3 -m pytest scripts/tests/test_batch.py -v`
Expected: FAIL —`ModuleNotFoundError: No module named 'batch'`。

- [ ] **Step 3: Write minimal implementation**

`scripts/batch.py`：

```python
"""Layer -1 批量编排计划器：给定选中的 level-2 playbook，从 frontmatter 确定性算出
生产者并集/问题并集/派发清单，并从磁盘重扫派生 status/phase。只计划与汇聚，不派发
subagent、不跑生产者（那是主 agent 的事）。与 orient.py（单 playbook 求值器）职责不重叠。"""
import argparse
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import engine_common as ec  # noqa: E402

BATCH_CONFIG = "batch_config.json"
BATCH_PLAN = "batch_plan.json"
BATCH_STATE = "batch_state.json"


def phenomena_name(pid):
    return f"phenomena_{pid}.json"


def producer_union(playbook_ids):
    """选中 playbook 的 upstream 产物 id 并集（sorted unique）。"""
    prods = set()
    for pid in playbook_ids:
        fm = ec.load_frontmatter(ec.find_playbook(pid))
        for u in fm.get("upstream") or []:
            prods.add(u["product"])
    return sorted(prods)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd ts-diagnose && python3 -m pytest scripts/tests/test_batch.py -v`
Expected: PASS（2 passed）。

- [ ] **Step 5: Commit**

```bash
git add ts-diagnose/scripts/batch.py ts-diagnose/scripts/tests/test_batch.py
git commit -m "feat(batch): batch.py scaffold + producer_union"
```

---

## Task 2: `question_union` — 按 qid 去重 + 冲突检测

**Files:**
- Modify: `ts-diagnose/scripts/batch.py`
- Test: `ts-diagnose/scripts/tests/test_batch.py`

**Interfaces:**
- Consumes: `ec.load_frontmatter`、`ec.find_playbook`、`ec.products_index`。
- Produces: `question_union(playbook_ids: list[str]) -> tuple[list[dict], list[dict]]`。返回 `(union, conflicts)`。`union` 每项是原 question dict 再加 `owners: list[str]`（哪些 playbook 声明了它），按 qid 排序。`conflicts` 每项 `{"qid": str, "owners": list[str]}`——同 qid 但 `ask` 或 `options` 分歧，按 qid 去重。`producer_playbooks(product_ids: list[str]) -> list[str]`（产物 id → 生产者 playbook id，sorted unique）。

- [ ] **Step 1: Write the failing test**

追加到 `test_batch.py`：

```python
def test_question_union_dedups_and_tracks_owners(pbdir):
    # 两个消费者各带不同问题；再加一个也问"口径"的消费者，验证 owners 合并
    _write_pb(pbdir, "pb-z", _consumer("pb-z", "口径"))
    union, conflicts = batch.question_union(["pb-x", "pb-y", "pb-z"])
    by_qid = {q["id"]: q for q in union}
    assert set(by_qid) == {"口径", "阈值"}
    assert sorted(by_qid["口径"]["owners"]) == ["pb-x", "pb-z"]
    assert by_qid["阈值"]["owners"] == ["pb-y"]
    assert conflicts == []

def test_question_union_flags_conflict(pbdir):
    # 两个 playbook 用同一 qid 但 ask 文案不同 → 冲突
    _write_pb(pbdir, "pb-z", _consumer("pb-z", "口径").replace("问 口径?", "另一种问法?"))
    union, conflicts = batch.question_union(["pb-x", "pb-z"])
    assert [c["qid"] for c in conflicts] == ["口径"]
    assert sorted(conflicts[0]["owners"]) == ["pb-x", "pb-z"]

def test_producer_playbooks_maps_id_to_producer(pbdir):
    assert batch.producer_playbooks(["setup"]) == ["setup-prod"]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd ts-diagnose && python3 -m pytest scripts/tests/test_batch.py -k "question_union or producer_playbooks" -v`
Expected: FAIL —`AttributeError: module 'batch' has no attribute 'question_union'`。

- [ ] **Step 3: Write minimal implementation**

追加到 `batch.py`：

```python
def producer_playbooks(product_ids):
    """产物 id → 生产者 playbook id（sorted unique）。"""
    idx = ec.products_index()
    return sorted({idx[p]["playbook"] for p in product_ids if p in idx})


def question_union(playbook_ids):
    """按 qid 去重的问题并集 + 冲突表。union 每项含 owners；conflicts 记同 qid 但
    ask/options 分歧者（按 qid 去重）。"""
    seen = {}
    conflict_qids = {}
    for pid in playbook_ids:
        fm = ec.load_frontmatter(ec.find_playbook(pid))
        for q in fm.get("questions") or []:
            qid = q["id"]
            if qid not in seen:
                seen[qid] = {**q, "owners": [pid]}
            else:
                prev = seen[qid]
                prev["owners"].append(pid)
                if q.get("ask") != prev.get("ask") or q.get("options") != prev.get("options"):
                    conflict_qids[qid] = {"qid": qid, "owners": list(prev["owners"])}
    union = [seen[k] for k in sorted(seen)]
    conflicts = [conflict_qids[k] for k in sorted(conflict_qids)]
    return union, conflicts
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd ts-diagnose && python3 -m pytest scripts/tests/test_batch.py -v`
Expected: PASS（全部）。

- [ ] **Step 5: Commit**

```bash
git add ts-diagnose/scripts/batch.py ts-diagnose/scripts/tests/test_batch.py
git commit -m "feat(batch): question_union with dedup + conflict detection"
```

---

## Task 3: `dispatch_list` — 从磁盘派生 status + batch_state 覆盖

**Files:**
- Modify: `ts-diagnose/scripts/batch.py`
- Test: `ts-diagnose/scripts/tests/test_batch.py`

**Interfaces:**
- Consumes: `ec.read_json`；`phenomena_name`。
- Produces: `dispatch_list(workdir: str, playbook_ids: list[str]) -> list[dict]`。每项 `{"playbook": pid, "workdir": f"./{pid}", "out": phenomena_name(pid), "status": str}`。status 判定优先级：磁盘 `done`（`<pb>/CONCLUSION.md` 且 `<pb>/gate_reports/conclusion_gate.json`）> 磁盘 `compute-done`（`<pb>/phenomena_<pb>.json`）> `batch_state.json` 里的 `running`/`failed` 标注 > `pending`。

- [ ] **Step 1: Write the failing test**

追加到 `test_batch.py`：

```python
def _touch(path):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        f.write("x")

def test_dispatch_status_pending_by_default(pbdir, tmp_path):
    wd = str(tmp_path)
    disp = {d["playbook"]: d for d in batch.dispatch_list(wd, ["pb-x", "pb-y"])}
    assert disp["pb-x"]["status"] == "pending"
    assert disp["pb-x"]["out"] == "phenomena_pb-x.json"
    assert disp["pb-x"]["workdir"] == "./pb-x"

def test_dispatch_status_compute_done_when_phenomena_exists(pbdir, tmp_path):
    wd = str(tmp_path)
    _touch(os.path.join(wd, "pb-x", "phenomena_pb-x.json"))
    disp = {d["playbook"]: d for d in batch.dispatch_list(wd, ["pb-x", "pb-y"])}
    assert disp["pb-x"]["status"] == "compute-done"
    assert disp["pb-y"]["status"] == "pending"

def test_dispatch_status_done_when_conclusion_and_gate_exist(pbdir, tmp_path):
    wd = str(tmp_path)
    _touch(os.path.join(wd, "pb-x", "phenomena_pb-x.json"))
    _touch(os.path.join(wd, "pb-x", "CONCLUSION.md"))
    _touch(os.path.join(wd, "pb-x", "gate_reports", "conclusion_gate.json"))
    disp = {d["playbook"]: d for d in batch.dispatch_list(wd, ["pb-x"])}
    assert disp["pb-x"]["status"] == "done"

def test_dispatch_state_annotation_overridden_by_disk(pbdir, tmp_path):
    wd = str(tmp_path)
    ec.dump_json({"pb-x": "failed"}, os.path.join(wd, batch.BATCH_STATE))
    # 无磁盘产物 → 采用标注
    d1 = {d["playbook"]: d for d in batch.dispatch_list(wd, ["pb-x"])}
    assert d1["pb-x"]["status"] == "failed"
    # 磁盘出现 phenomena → 磁盘覆盖标注
    _touch(os.path.join(wd, "pb-x", "phenomena_pb-x.json"))
    d2 = {d["playbook"]: d for d in batch.dispatch_list(wd, ["pb-x"])}
    assert d2["pb-x"]["status"] == "compute-done"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd ts-diagnose && python3 -m pytest scripts/tests/test_batch.py -k dispatch -v`
Expected: FAIL —`AttributeError: module 'batch' has no attribute 'dispatch_list'`。

- [ ] **Step 3: Write minimal implementation**

追加到 `batch.py`：

```python
def dispatch_list(workdir, playbook_ids):
    """每条 playbook 的派发条目 + 从磁盘派生的 status（磁盘产物永远覆盖 batch_state 标注）。"""
    state = ec.read_json(os.path.join(workdir, BATCH_STATE)) or {}
    out = []
    for pid in playbook_ids:
        pbwd = os.path.join(workdir, pid)
        concl = os.path.join(pbwd, "CONCLUSION.md")
        gate = os.path.join(pbwd, "gate_reports", "conclusion_gate.json")
        phen = os.path.join(pbwd, phenomena_name(pid))
        if os.path.exists(concl) and os.path.exists(gate):
            status = "done"
        elif os.path.exists(phen):
            status = "compute-done"
        else:
            status = state.get(pid, "pending")
            if status not in ("running", "failed"):
                status = "pending"
        out.append({"playbook": pid, "workdir": f"./{pid}",
                    "out": phenomena_name(pid), "status": status})
    return out
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd ts-diagnose && python3 -m pytest scripts/tests/test_batch.py -v`
Expected: PASS（全部）。

- [ ] **Step 5: Commit**

```bash
git add ts-diagnose/scripts/batch.py ts-diagnose/scripts/tests/test_batch.py
git commit -m "feat(batch): dispatch_list derives status from disk with state overlay"
```

---

## Task 4: `derive_phase` — 五阶段推断

**Files:**
- Modify: `ts-diagnose/scripts/batch.py`
- Test: `ts-diagnose/scripts/tests/test_batch.py`

**Interfaces:**
- Consumes: `ec.read_json`、`ec.product_status(cfg, pid)`、`dispatch_list`、`producer_union`。
- Produces: `derive_phase(workdir: str, playbook_ids: list[str], producers: list[str]) -> str`。返回 `"A"`（有生产者未就绪）/`"B"`（生产者就绪但 `batch_config.answers` 为空）/`"C"`（有派发条目仍 pending/running/failed）/`"D"`（全部 ≥compute-done 但未全 done）/`"E"`（全部 done）。判定用 `ec.product_status(cfg, p)`（cfg 读自 `batch_config.json`），status ∈ {built, linked} 才算生产者就绪。

- [ ] **Step 1: Write the failing test**

追加到 `test_batch.py`：

```python
def _cfg(wd, **kw):
    ec.dump_json(kw, os.path.join(wd, batch.BATCH_CONFIG))

def test_phase_A_when_producer_absent(pbdir, tmp_path):
    wd = str(tmp_path)
    _cfg(wd, playbooks=["pb-x"])  # 无 products 登记 → setup absent
    assert batch.derive_phase(wd, ["pb-x"], ["setup"]) == "A"

def test_phase_B_when_producer_ready_no_answers(pbdir, tmp_path):
    wd = str(tmp_path)
    setup_wd = os.path.join(wd, "_shared", "setup")
    _touch(os.path.join(setup_wd, "predictions.csv"))
    ec.dump_json({}, os.path.join(setup_wd, "setup_manifest.json"))
    _cfg(wd, playbooks=["pb-x"],
         products={"setup": {"workdir": setup_wd, "status": "built"}})
    assert batch.derive_phase(wd, ["pb-x"], ["setup"]) == "B"

def test_phase_C_when_answers_present_compute_pending(pbdir, tmp_path):
    wd = str(tmp_path)
    setup_wd = os.path.join(wd, "_shared", "setup")
    _touch(os.path.join(setup_wd, "predictions.csv"))
    ec.dump_json({}, os.path.join(setup_wd, "setup_manifest.json"))
    _cfg(wd, playbooks=["pb-x"], answers={"口径": {"answer": "rmse_192"}},
         products={"setup": {"workdir": setup_wd, "status": "built"}})
    assert batch.derive_phase(wd, ["pb-x"], ["setup"]) == "C"

def test_phase_D_when_all_compute_done(pbdir, tmp_path):
    wd = str(tmp_path)
    setup_wd = os.path.join(wd, "_shared", "setup")
    _touch(os.path.join(setup_wd, "predictions.csv"))
    ec.dump_json({}, os.path.join(setup_wd, "setup_manifest.json"))
    _cfg(wd, playbooks=["pb-x"], answers={"口径": {"answer": "r"}},
         products={"setup": {"workdir": setup_wd, "status": "built"}})
    _touch(os.path.join(wd, "pb-x", "phenomena_pb-x.json"))
    assert batch.derive_phase(wd, ["pb-x"], ["setup"]) == "D"

def test_phase_E_when_all_done(pbdir, tmp_path):
    wd = str(tmp_path)
    setup_wd = os.path.join(wd, "_shared", "setup")
    _touch(os.path.join(setup_wd, "predictions.csv"))
    ec.dump_json({}, os.path.join(setup_wd, "setup_manifest.json"))
    _cfg(wd, playbooks=["pb-x"], answers={"口径": {"answer": "r"}},
         products={"setup": {"workdir": setup_wd, "status": "built"}})
    _touch(os.path.join(wd, "pb-x", "phenomena_pb-x.json"))
    _touch(os.path.join(wd, "pb-x", "CONCLUSION.md"))
    _touch(os.path.join(wd, "pb-x", "gate_reports", "conclusion_gate.json"))
    assert batch.derive_phase(wd, ["pb-x"], ["setup"]) == "E"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd ts-diagnose && python3 -m pytest scripts/tests/test_batch.py -k phase -v`
Expected: FAIL —`AttributeError: module 'batch' has no attribute 'derive_phase'`。

- [ ] **Step 3: Write minimal implementation**

追加到 `batch.py`：

```python
def derive_phase(workdir, playbook_ids, producers):
    """五阶段推断（全部从磁盘 + batch_config 派生）。"""
    cfg = ec.read_json(os.path.join(workdir, BATCH_CONFIG)) or {}
    for p in producers:
        if ec.product_status(cfg, p).get("status") not in ("built", "linked"):
            return "A"
    if not cfg.get("answers"):
        return "B"
    statuses = [d["status"] for d in dispatch_list(workdir, playbook_ids)]
    if all(s == "done" for s in statuses):
        return "E"
    if any(s in ("pending", "running", "failed") for s in statuses):
        return "C"
    return "D"
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd ts-diagnose && python3 -m pytest scripts/tests/test_batch.py -v`
Expected: PASS（全部）。

- [ ] **Step 5: Commit**

```bash
git add ts-diagnose/scripts/batch.py ts-diagnose/scripts/tests/test_batch.py
git commit -m "feat(batch): derive_phase A-E from disk + batch_config"
```

---

## Task 5: `build_plan` — 组装并落盘 batch_plan.json

**Files:**
- Modify: `ts-diagnose/scripts/batch.py`
- Test: `ts-diagnose/scripts/tests/test_batch.py`

**Interfaces:**
- Consumes: `producer_union`、`producer_playbooks`、`question_union`、`dispatch_list`、`derive_phase`、`ec.read_json`、`ec.dump_json`。
- Produces: `build_plan(workdir: str) -> dict`。读 `batch_config.json`（缺 `playbooks` → `ValueError`），组装 `{"producer_union", "question_union", "question_conflicts", "dispatch", "phase"}` 并 `dump_json` 到 `<workdir>/batch_plan.json`，返回该 dict。问题并集覆盖“选中 playbook + 其生产者 playbook”两者（一次性问全，生产者问题也在同一次 intake）。

- [ ] **Step 1: Write the failing test**

追加到 `test_batch.py`：

```python
def test_build_plan_assembles_and_writes(pbdir, tmp_path):
    wd = str(tmp_path)
    _cfg(wd, playbooks=["pb-x", "pb-y"])
    plan = batch.build_plan(wd)
    assert plan["producer_union"] == ["setup"]
    assert plan["phase"] == "A"  # 无 products 登记
    assert {d["playbook"] for d in plan["dispatch"]} == {"pb-x", "pb-y"}
    # 问题并集含生产者的 freq + 两个消费者的问题
    qids = {q["id"] for q in plan["question_union"]}
    assert qids == {"freq", "口径", "阈值"}
    # 落盘且可复读
    on_disk = ec.read_json(os.path.join(wd, batch.BATCH_PLAN))
    assert on_disk["phase"] == "A"

def test_build_plan_requires_playbooks(pbdir, tmp_path):
    wd = str(tmp_path)
    ec.dump_json({}, os.path.join(wd, batch.BATCH_CONFIG))
    with pytest.raises(ValueError, match="playbooks"):
        batch.build_plan(wd)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd ts-diagnose && python3 -m pytest scripts/tests/test_batch.py -k build_plan -v`
Expected: FAIL —`AttributeError: module 'batch' has no attribute 'build_plan'`。

- [ ] **Step 3: Write minimal implementation**

追加到 `batch.py`：

```python
def build_plan(workdir):
    """读 batch_config.json → 组装 batch_plan.json（重扫渲染，不可手改）。"""
    cfg = ec.read_json(os.path.join(workdir, BATCH_CONFIG)) or {}
    ids = cfg.get("playbooks")
    if not ids:
        raise ValueError("batch_config.json 缺 playbooks——先跑 batch.py --select 初始化")
    producers = producer_union(ids)
    all_pbs = sorted(set(ids) | set(producer_playbooks(producers)))
    union, conflicts = question_union(all_pbs)
    plan = {
        "producer_union": producers,
        "question_union": union,
        "question_conflicts": conflicts,
        "dispatch": dispatch_list(workdir, ids),
        "phase": derive_phase(workdir, ids, producers),
    }
    ec.dump_json(plan, os.path.join(workdir, BATCH_PLAN))
    return plan
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd ts-diagnose && python3 -m pytest scripts/tests/test_batch.py -v`
Expected: PASS（全部）。

- [ ] **Step 5: Commit**

```bash
git add ts-diagnose/scripts/batch.py ts-diagnose/scripts/tests/test_batch.py
git commit -m "feat(batch): build_plan assembles + writes batch_plan.json"
```

---

## Task 6: CLI `main()` — `--select` / 刷新 / `--mark`

**Files:**
- Modify: `ts-diagnose/scripts/batch.py`
- Test: `ts-diagnose/scripts/tests/test_batch.py`

**Interfaces:**
- Consumes: `argparse`、`build_plan`、`ec.find_playbook`、`ec.read_json`、`ec.dump_json`。
- Produces: 命令行入口。`python3 batch.py --select id1,id2 [--workdir DIR]` 校验每个 id 存在（`ec.find_playbook`，不存在即报错退出码 2）→ 写 `batch_config.json` 的 `playbooks` → `build_plan` → 打印。`python3 batch.py [--workdir DIR]` 刷新并打印计划。`python3 batch.py --mark pb:running|failed [--workdir DIR]` 写 `batch_state.json` 标注 → 刷新。打印含 phase、producer_union、每条 dispatch 的 status、问题并集条数与冲突、下一步提示。

- [ ] **Step 1: Write the failing test**

追加到 `test_batch.py`（子进程调用，照 test_products.py 用 `TSD_PLAYBOOKS_DIR`）：

```python
import subprocess

def _run(args, cwd, pbroot):
    env = dict(os.environ, TSD_PLAYBOOKS_DIR=str(pbroot))
    return subprocess.run([sys.executable, os.path.join(SCRIPTS_DIR, "batch.py"), *args],
                          cwd=cwd, env=env, capture_output=True, text=True)

def test_cli_select_writes_config_and_prints_plan(pbdir, tmp_path):
    wd = str(tmp_path)
    r = _run(["--select", "pb-x,pb-y", "--workdir", wd], wd, pbdir)
    assert r.returncode == 0, r.stderr
    cfg = ec.read_json(os.path.join(wd, batch.BATCH_CONFIG))
    assert cfg["playbooks"] == ["pb-x", "pb-y"]
    assert "phase" in r.stdout.lower() or "阶段" in r.stdout
    assert os.path.exists(os.path.join(wd, batch.BATCH_PLAN))

def test_cli_select_rejects_unknown_playbook(pbdir, tmp_path):
    wd = str(tmp_path)
    r = _run(["--select", "pb-x,nope", "--workdir", wd], wd, pbdir)
    assert r.returncode != 0
    assert "nope" in (r.stderr + r.stdout)

def test_cli_mark_writes_state(pbdir, tmp_path):
    wd = str(tmp_path)
    _run(["--select", "pb-x", "--workdir", wd], wd, pbdir)
    r = _run(["--mark", "pb-x:failed", "--workdir", wd], wd, pbdir)
    assert r.returncode == 0, r.stderr
    assert ec.read_json(os.path.join(wd, batch.BATCH_STATE))["pb-x"] == "failed"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd ts-diagnose && python3 -m pytest scripts/tests/test_batch.py -k cli -v`
Expected: FAIL（batch.py 无 `__main__` 入口 / 无参数处理，子进程无输出或非零退出但原因不符）。

- [ ] **Step 3: Write minimal implementation**

追加到 `batch.py`：

```python
def _print_plan(plan):
    print(f"阶段 phase: {plan['phase']}")
    print(f"生产者并集 producer_union: {plan['producer_union'] or '（无）'}")
    print("派发 dispatch:")
    for d in plan["dispatch"]:
        print(f"  - {d['playbook']:24} status={d['status']:12} → {d['out']}")
    print(f"问题并集 {len(plan['question_union'])} 条"
          f"（qid: {[q['id'] for q in plan['question_union']]}）")
    if plan["question_conflicts"]:
        print(f"⚠ 问题冲突（同 qid 语义分歧，主 agent 须让用户裁决）: "
              f"{[c['qid'] for c in plan['question_conflicts']]}")
    nxt = {"A": "内联跑生产者进 _shared/，回填 batch_config.products",
           "B": "一次性合并提问，答案写 batch_config.answers",
           "C": "为每条 pending 派发 Brief-BATCH-COMPUTE 子代理（见 references/batch-orchestration.md）",
           "D": "合并呈现各 phenomena，请用户点名深挖，逐条跑结论",
           "E": "全部结论完成——写 BATCH_REPORT.md"}
    print(f"下一步: {nxt.get(plan['phase'], '')}")


def main():
    ap = argparse.ArgumentParser(description="ts-diagnose Layer -1 批量编排计划器")
    ap.add_argument("--select", default=None, help="逗号分隔的 playbook id，初始化批量")
    ap.add_argument("--mark", default=None, help="pb:running|failed 标注派发瞬态")
    ap.add_argument("--workdir", default=".", help="批量工作目录")
    args = ap.parse_args()
    wd = args.workdir
    os.makedirs(wd, exist_ok=True)
    if args.select:
        ids = [s.strip() for s in args.select.split(",") if s.strip()]
        for pid in ids:
            try:
                ec.find_playbook(pid)
            except FileNotFoundError as e:
                ap.error(str(e))
        cfg = ec.read_json(os.path.join(wd, BATCH_CONFIG)) or {}
        cfg["playbooks"] = ids
        ec.dump_json(cfg, os.path.join(wd, BATCH_CONFIG))
    if args.mark:
        pid, _, mark = args.mark.partition(":")
        if mark not in ("running", "failed"):
            ap.error("--mark 只接受 <pb>:running 或 <pb>:failed")
        state = ec.read_json(os.path.join(wd, BATCH_STATE)) or {}
        state[pid] = mark
        ec.dump_json(state, os.path.join(wd, BATCH_STATE))
    _print_plan(build_plan(wd))


if __name__ == "__main__":
    main()
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd ts-diagnose && python3 -m pytest scripts/tests/test_batch.py -v`
Expected: PASS（全部）。

- [ ] **Step 5: Commit**

```bash
git add ts-diagnose/scripts/batch.py ts-diagnose/scripts/tests/test_batch.py
git commit -m "feat(batch): CLI --select / refresh / --mark with plan print"
```

---

## Task 7: `references/batch-orchestration.md` — 主 agent 协议 + Brief-BATCH-COMPUTE

**Files:**
- Create: `ts-diagnose/references/batch-orchestration.md`
- Test: `ts-diagnose/scripts/tests/test_batch.py`

**Interfaces:**
- Consumes: 无（纯文档）。
- Produces: 文档文件。含五个二级标题锚点 `## Phase A`~`## Phase E`、一个 `## Brief-BATCH-COMPUTE` 节、一个 `## 上下文预算` 节。

- [ ] **Step 1: Write the failing test**

追加到 `test_batch.py`：

```python
def test_batch_orchestration_doc_has_required_sections():
    doc = os.path.join(os.path.dirname(SCRIPTS_DIR), "references", "batch-orchestration.md")
    assert os.path.exists(doc), "references/batch-orchestration.md 缺失"
    text = open(doc, encoding="utf-8").read()
    for anchor in ("## Phase A", "## Phase B", "## Phase C", "## Phase D",
                   "## Phase E", "## Brief-BATCH-COMPUTE", "## 上下文预算"):
        assert anchor in text, f"batch-orchestration.md 缺 {anchor} 节"
    # 禁止项与停止点必须写明（钉死 subagent 边界）
    assert "phenomena_" in text
    assert "结论永远由主 agent" in text
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd ts-diagnose && python3 -m pytest scripts/tests/test_batch.py -k orchestration_doc -v`
Expected: FAIL —`references/batch-orchestration.md 缺失`。

- [ ] **Step 3: Write the document**

写 `references/batch-orchestration.md`，零解释风格，含（内容按 spec §6/§7/§8）：

```markdown
# 批量编排协议（batch-orchestration）——主 agent 照此驱动

前置：用户要在同一份数据上一次诊断多条 level-2 playbook。每回合先跑
`python3 <ENGINE>/scripts/batch.py --workdir <批量工作目录>`，照它报的 phase 与下一步办。
状态以落盘产物为准，随时断点续跑。

## Phase A — 生产者只跑一次
batch.py 报 phase=A 时：按 `producer_union` 逐个在 `<批量工作目录>/_shared/<产物id>/`
内联跑生产方 playbook 的完整正文（收齐其问题答案后按 engine-core 的 Brief-PRODUCER
整体外包），写回 `batch_config.json` 的 `products.<id> = {workdir, status: built}`，重跑 batch.py。

## Phase B — 一次合并提问
phase=B 时：把 `question_union` 一次性问用户（同一阶段多题合并成一次 AskUserQuestion，
每题带 options）。`question_conflicts` 里的 qid 必须显式呈现两种语义请用户裁决，不静默取一。
答案写 `batch_config.json` 的 `answers`，并拷进每条 playbook 子目录的 `diagnose_config.json`
（用户答过的不重复问）。重跑 batch.py。

## Phase C — 并行计算 fan-out
phase=C 时：为每条 status=pending 的 playbook 派一个子代理，brief 用下方
Brief-BATCH-COMPUTE。派发前 `batch.py --mark <pb>:running`；子代理返回后不写 status
（磁盘出现 phenomena 即自动判 compute-done）；子代理报错则 `batch.py --mark <pb>:failed`
并向用户报告，供单条重派。收齐后重跑 batch.py。

## Phase D — 一次合并停顿
phase=D 时：读齐所有 `<pb>/phenomena_<pb>.json`（自足 json，不读大文件），一并呈现现象
清单，请用户点名要深挖哪些（可跨 playbook）。选了哪些、按什么判据，记 BATCH_PROGRESS.md。

## Phase E — 结论
对每个选中的深挖目标，在其 `<pb>/` 子目录跑 orient 进结论阶段：三道门 +
`conclusion_gate.json` receipt，结论永远由主 agent 落笔。全部完成后写 BATCH_REPORT.md
（合并各 CONCLUSION.md 要点 + 覆盖缺口声明）直接呈现用户。

## Brief-BATCH-COMPUTE
> 工作目录：`<批量工作目录>/<playbook>/`（已含预填的 diagnose_config.json）。
> 共享产物：`<批量工作目录>/_shared/setup/`（已就绪，已登记进 config.products）。
> 入口：在工作目录内跑 `python3 <ENGINE>/scripts/orient.py`，被它逐阶带走。
> 跑：stage 0 → 事实提取 stage（含），产出 `phenomena_<playbook>.json`（观察+数字+来源，
>   禁机制语言）。
> 停：事实提取 stage 完成、phenomena 写盘即止——不得进结论 stage。
> 回：≤30 行数字摘要 + phenomena 文件路径；不贴 CSV/parquet/大日志。
> 闸：golden 覆盖的 stage 必过 gen_gate.py；整形脚本必过对账两关。
> 重活可再嵌子代理（深度 ≤3）。
> 禁：改任何共享状态文件（batch_*、别的 playbook 产物、FINDINGS/CONCLUSION）；提问用户；
>   进结论 stage；跨越停止点。出错即返回错误摘要，不重试破坏性操作。

## 上下文预算
主 agent 全程只吃 json 摘要（批量计划、提问答案、各 ≤30 行摘要、现象清单 json），
从不摄入原始数据，稳在 256k。每个计算子代理各吃各的 256k，重活落盘只回摘要。
不靠记忆——每步先跑 batch.py / orient 从磁盘重建状态。golden 是磁盘上的验证闸，不进上下文。
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd ts-diagnose && python3 -m pytest scripts/tests/test_batch.py -k orchestration_doc -v`
Expected: PASS。

- [ ] **Step 5: Commit**

```bash
git add ts-diagnose/references/batch-orchestration.md ts-diagnose/scripts/tests/test_batch.py
git commit -m "docs(batch): batch-orchestration protocol + Brief-BATCH-COMPUTE"
```

---

## Task 8: SKILL.md 路由 + engine-core.md 批量节

**Files:**
- Modify: `ts-diagnose/SKILL.md`
- Modify: `ts-diagnose/references/engine-core.md`
- Test: `ts-diagnose/scripts/tests/test_batch.py`（新增守卫）；既有 `scripts/tests/test_layering.py` 必须仍全绿。

**Interfaces:**
- Consumes: 无。
- Produces: SKILL.md 增一条"多条 playbook 同跑 → 见 engine-core.md 批量节"的路由（不含方法词汇、不直接引用 batch-orchestration.md）；engine-core.md 增 `## 批量编排（多 playbook 同跑）` 一节，指向 `references/batch-orchestration.md` 与 `scripts/batch.py`。

- [ ] **Step 1: Write the failing test**

追加到 `test_batch.py`：

```python
def test_skill_routes_batch_via_engine_core_not_ref():
    root = os.path.dirname(SCRIPTS_DIR)
    skill = open(os.path.join(root, "SKILL.md"), encoding="utf-8").read()
    # SKILL.md 提到批量、并指向 engine-core；但不得直接引用 batch-orchestration.md（越界守卫）
    assert "批量" in skill or "batch" in skill
    assert "batch-orchestration.md" not in skill
    core = open(os.path.join(root, "references", "engine-core.md"), encoding="utf-8").read()
    assert "batch-orchestration.md" in core
    assert "scripts/batch.py" in core or "batch.py" in core
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd ts-diagnose && python3 -m pytest scripts/tests/test_batch.py -k skill_routes_batch -v`
Expected: FAIL（SKILL.md 无批量提及 / engine-core 无 batch 节）。

- [ ] **Step 3: Implement — 改 SKILL.md 与 engine-core.md**

在 `SKILL.md` 路由表下方"都不像 →"那段之前或之后，加一行（避开 METHOD_VOCAB：不用 `Stage`/`pause_after` 等）：

```markdown
用户想在**同一份数据上一次跑多条 playbook**（多角度诊断）→ 批量模式：读
`references/engine-core.md` 的「批量编排」节。
```

在 `references/engine-core.md` 末尾（"运行后回顾"节之前）加：

```markdown
## 批量编排（多 playbook 同跑）

同一份数据要一次诊断多条 playbook 时，走 Layer -1 批量层，不逐条串跑。每回合先跑
`python3 "<ENGINE>/scripts/batch.py" --select <id1,id2,...> --workdir <批量工作目录>`
（后续回合去掉 --select 刷新），照它报的 phase 与下一步办；完整协议、Brief-BATCH-COMPUTE
模板、上下文预算见 `references/batch-orchestration.md`。生产者只跑一次入 `_shared/`、
提问一次合并、计算 fan-out 到事实提取、合并停顿、结论仍由主 agent 落笔。
```

- [ ] **Step 4: Run tests — 新守卫 + 分层守卫双绿**

Run: `cd ts-diagnose && python3 -m pytest scripts/tests/test_batch.py -k skill_routes_batch scripts/tests/test_layering.py -v`
Expected: PASS（尤其 `test_layer0_line_budget` / `test_layer0_token_budget` / `test_layer0_no_method_vocab` / `test_layer0_only_posthit_references` 仍绿）。
若 `test_layer0_no_method_vocab` 报红：把 SKILL.md 那行里的违规词换成非方法词表达；若行数超 60：精简措辞。

- [ ] **Step 5: Commit**

```bash
git add ts-diagnose/SKILL.md ts-diagnose/references/engine-core.md ts-diagnose/scripts/tests/test_batch.py
git commit -m "feat(batch): route multi-playbook batch via SKILL.md → engine-core"
```

---

## Task 9: subagent_ok 审计 + 事实提取阶段守卫

**Files:**
- Modify: `ts-diagnose/playbooks/result-eval/playbook.md`、`ts-diagnose/playbooks/deployment-drift/playbook.md`、`ts-diagnose/playbooks/model-comparison/playbook.md`（按审计结果补 `subagent_ok: true`）
- Test: `ts-diagnose/scripts/tests/test_batch.py`

**Interfaces:**
- Consumes: `ec.load_frontmatter`、`ec.products_index`（判定谁是 level-2：声明了 `upstream` 且有结论阶段）。
- Produces: 新守卫——每条消费 `setup` 的 level-2 playbook，其 `pause_after: true` 的事实提取阶段必须 `subagent_ok` 为真（batch 派发前置：subagent 必须能跑到事实提取）。审计把三条缺声明的 playbook 早期与事实提取阶段显式补 `subagent_ok: true`。

- [ ] **Step 1: Write the failing test**

追加到 `test_batch.py`（跑真实 playbooks——不 monkeypatch PLAYBOOKS_DIR）：

```python
def test_every_level2_pause_stage_is_subagent_ok():
    root = os.path.dirname(SCRIPTS_DIR)
    pbdir_real = os.path.join(root, "playbooks")
    import glob
    fails = []
    for p in glob.glob(os.path.join(pbdir_real, "*", "playbook.md")):
        fm = ec.load_frontmatter(p)
        # level-2 = 声明了 upstream（消费产物）
        if not fm.get("upstream"):
            continue
        for st in fm["stages"]:
            if st.get("pause_after") and not st.get("subagent_ok", False):
                fails.append(f"{fm['id']} stage {st['id']}")
    assert not fails, f"这些事实提取阶段未标 subagent_ok=true，batch 无法派发到该阶段：{fails}"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd ts-diagnose && python3 -m pytest scripts/tests/test_batch.py -k level2_pause -v`
Expected: FAIL — 列出 result-eval / deployment-drift / model-comparison 的事实提取阶段。

- [ ] **Step 3: 审计并补声明**

对每条报红的 playbook：在其 `pause_after: true` 的事实提取阶段（及其之前的计算阶段）显式加 `subagent_ok: true`。仅补该字段，不动 done_when/prereqs/charts。逐条核对：结论阶段保持 `subagent_ok: false`。

- [ ] **Step 4: Run test to verify it passes**

Run: `cd ts-diagnose && python3 -m pytest scripts/tests/test_batch.py -k level2_pause -v`
Expected: PASS。

- [ ] **Step 5: Commit**

```bash
git add ts-diagnose/playbooks/result-eval/playbook.md ts-diagnose/playbooks/deployment-drift/playbook.md ts-diagnose/playbooks/model-comparison/playbook.md ts-diagnose/scripts/tests/test_batch.py
git commit -m "fix(playbooks): mark fact-extraction stages subagent_ok for batch dispatch"
```

---

## Task 10: 全量回归 + CHANGELOG

**Files:**
- Modify: `ts-diagnose/CHANGELOG.md`

**Interfaces:**
- Consumes: 无。
- Produces: 全套 pytest 绿 + CHANGELOG 一行记录。

- [ ] **Step 1: 全量测试**

Run: `cd ts-diagnose && python3 -m pytest scripts/tests/ chartbook/tests/ -q`
Expected: 全绿（含既有 test_layering / test_products / test_engine 与新 test_batch）。
若有红：修到绿——尤其确认 batch.py 的改动没破坏 engine_common 的既有契约。

- [ ] **Step 2: CHANGELOG 追加一行**

在 `CHANGELOG.md` 顶部按既有格式加（日期 | 改了什么 | 触发反馈 | 为什么）：

```markdown
- 2026-08-03 | 新增 Layer -1 批量编排层（scripts/batch.py + references/batch-orchestration.md）：同一份数据一次并行诊断多条 level-2 playbook，生产者跑一次、提问一次、计算 fan-out 到事实提取、合并停顿、结论仍主 agent 落笔 | 用户问"如何同时跑多个 playbook、subagent 无提问权下消息如何回传" | subagent 无提问权是硬约束，唯一解是把交互全提到主 agent 的两个合并停顿点，重活各吃各的 256k
```

- [ ] **Step 3: Commit**

```bash
git add ts-diagnose/CHANGELOG.md
git commit -m "docs(ts-diagnose): CHANGELOG for batch orchestration layer"
```

---

## Self-Review 结果

**Spec 覆盖对照：**
- §4 分层（batch.py=Layer -1，不重叠 orient）→ Task 1-6。
- §5 文件布局（batch_config / batch_plan / _shared / phenomena_<pb> / batch_state）→ Task 3-6 + Task 7 文档。
- §6 五阶段 A-E → Task 4（derive_phase）+ Task 7（主 agent 协议正文）。
- §7 Brief-BATCH-COMPUTE 完整字段 → Task 7。
- §8 上下文预算 → Task 7。
- §9 问题并集 + 冲突 → Task 2 + Task 5。
- §10 schema（config=意图/agent、plan=派生/batch.py）→ Task 3-6（status 派生、单写者）。
- §11 清单：batch.py→T1-6；batch-orchestration.md→T7；SKILL.md→T8；subagent_ok 审计→T9；test_batch→贯穿。
- §13 风险：subagent_ok 审计→T9；"同 playbook×多输入"/通用 DAG 明确不在本计划（spec 已声明后续轮）。

**Placeholder 扫描：** 无 TBD/TODO；每个 code step 带完整代码；每个测试带断言。

**类型一致性：** `producer_union`/`question_union`/`producer_playbooks`/`dispatch_list`/`derive_phase`/`build_plan`/`phenomena_name` 签名在 Task 1-6 定义后于后续 Task 一致引用；status 保留字 `pending/running/compute-done/done/failed` 全程一致；`BATCH_CONFIG/BATCH_PLAN/BATCH_STATE` 常量一致。
```
