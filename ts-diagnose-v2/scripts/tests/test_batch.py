"""batch.py：Layer -1 批量计划器测试。全部在 tmp 沙箱 playbooks 目录里跑
（monkeypatch ec.PLAYBOOKS_DIR），不依赖真实 playbook 内容。"""
import os
import subprocess
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

PRODUCER_OPT = """\
---
id: opt-prod
name: 可选生产者
goal: 产 opt
produces:
  id: opt
  manifest: opt_manifest.json
  marker_files: [opt.csv]
stages:
  - id: 0
    name: 做事
    done_when: {artifacts: ["opt.csv"]}
---
正文
"""

def _consumer_with_optional(pid, qid):
    """既有 required:true 的 setup 上游，又有 required:false 的 opt 上游——
    验证 producer_union 只并入 required 的那个。"""
    return f"""\
---
id: {pid}
name: 消费者{pid}
goal: 消费 setup + 可选 opt
upstream:
  - product: setup
    required: true
  - product: opt
    required: false
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

def test_producer_union_excludes_optional_upstream(pbdir):
    # pb-opt 声明了 required:true 的 setup 与 required:false 的 opt——
    # producer_union 只应并入 setup；opt 是可选产物，由主 agent 在 Phase A
    # 逐 playbook 三分支裁决（build/link/decline），不进产物并集，否则 Phase A
    # 会永久卡在等一个用户可能压根不打算建的可选产物上。
    _write_pb(pbdir, "opt-prod", PRODUCER_OPT)
    _write_pb(pbdir, "pb-opt", _consumer_with_optional("pb-opt", "阈值2"))
    prods = batch.producer_union(["pb-opt"])
    assert "setup" in prods
    assert "opt" not in prods

def test_phenomena_name(pbdir):
    assert batch.phenomena_name("pb-x") == "phenomena_pb-x.json"

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

def test_question_union_flags_options_conflict(pbdir):
    # 两个 playbook 用同一 qid 和 ask 但 options 不同 → 冲突
    pb_with_opts1 = """\
---
id: pb-a
name: 消费者pb-a
goal: 消费 setup
upstream:
  - product: setup
    required: true
stages:
  - id: 0
    name: 计算
    done_when: {artifacts: ["m.json"]}
    subagent_ok: true
questions:
  - id: 选项
    stage: 0
    ask: 选择?
    why: w
    default: null
    options: [A, B]
---
正文
"""
    pb_with_opts2 = """\
---
id: pb-b
name: 消费者pb-b
goal: 消费 setup
upstream:
  - product: setup
    required: true
stages:
  - id: 0
    name: 计算
    done_when: {artifacts: ["m.json"]}
    subagent_ok: true
questions:
  - id: 选项
    stage: 0
    ask: 选择?
    why: w
    default: null
    options: [A, B, C]
---
正文
"""
    _write_pb(pbdir, "pb-a", pb_with_opts1)
    _write_pb(pbdir, "pb-b", pb_with_opts2)
    union, conflicts = batch.question_union(["pb-a", "pb-b"])
    assert [c["qid"] for c in conflicts] == ["选项"]
    assert sorted(conflicts[0]["owners"]) == ["pb-a", "pb-b"]

def test_producer_playbooks_maps_id_to_producer(pbdir):
    assert batch.producer_playbooks(["setup"]) == ["setup-prod"]

def _touch(path):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        f.write("x")

def _cfg(wd, **kw):
    ec.dump_json(kw, os.path.join(wd, batch.BATCH_CONFIG))

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
    # Phase E 只认 BATCH_REPORT.md 存在——不是 all-playbooks-done（用户可能只深挖
    # 子集，或选中的 playbook 根本没有结论阶段，两种情况都不该卡在 D）。
    wd = str(tmp_path)
    setup_wd = os.path.join(wd, "_shared", "setup")
    _touch(os.path.join(setup_wd, "predictions.csv"))
    ec.dump_json({}, os.path.join(setup_wd, "setup_manifest.json"))
    _cfg(wd, playbooks=["pb-x"], answers={"口径": {"answer": "r"}},
         products={"setup": {"workdir": setup_wd, "status": "built"}})
    _touch(os.path.join(wd, "pb-x", "phenomena_pb-x.json"))
    _touch(os.path.join(wd, "BATCH_REPORT.md"))
    assert batch.derive_phase(wd, ["pb-x"], ["setup"]) == "E"

def test_phase_D_when_some_done_but_no_batch_report(pbdir, tmp_path):
    # pb-x 深挖完（有 CONCLUSION+gate），pb-y 停在 compute-done（用户没点名深挖它）
    # ——只要 BATCH_REPORT.md 还没写，仍是 D，不能提前跳成 E。
    wd = str(tmp_path)
    setup_wd = os.path.join(wd, "_shared", "setup")
    _touch(os.path.join(setup_wd, "predictions.csv"))
    ec.dump_json({}, os.path.join(setup_wd, "setup_manifest.json"))
    _cfg(wd, playbooks=["pb-x", "pb-y"],
         answers={"口径": {"answer": "r"}, "阈值": {"answer": "t"}},
         products={"setup": {"workdir": setup_wd, "status": "built"}})
    _touch(os.path.join(wd, "pb-x", "phenomena_pb-x.json"))
    _touch(os.path.join(wd, "pb-x", "CONCLUSION.md"))
    _touch(os.path.join(wd, "pb-x", "gate_reports", "conclusion_gate.json"))
    _touch(os.path.join(wd, "pb-y", "phenomena_pb-y.json"))
    assert batch.derive_phase(wd, ["pb-x", "pb-y"], ["setup"]) == "D"

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


def test_cli_build_plan_without_select_exits_error(tmp_path):
    wd = str(tmp_path)
    # 跑 batch.py without --select 应该失败（没有 playbooks config）
    r = subprocess.run([sys.executable, os.path.join(SCRIPTS_DIR, "batch.py"),
                       "--workdir", wd], capture_output=True, text=True)
    assert r.returncode != 0, "Expected non-zero exit code"
    output = r.stderr + r.stdout
    assert "playbooks" in output or "--select" in output, \
        f"Error message should mention playbooks or --select: {output}"


def test_every_level2_pause_stage_is_subagent_ok():
    # compute 子代理从 stage 0 一路跑到（含）第一个 pause_after 停顿阶段——沿途
    # 任何一个阶段不是 subagent_ok，子代理半路就撞死，到不了停顿点。只查
    # pause_after 那一个阶段不够，必须查从头到它的整段路径。
    root = os.path.dirname(SCRIPTS_DIR)
    pbdir_real = os.path.join(root, "playbooks")
    import glob
    fails = []
    for p in glob.glob(os.path.join(pbdir_real, "*", "playbook.md")):
        fm = ec.load_frontmatter(p)
        # level-2 = 声明了 upstream（消费产物）
        if not fm.get("upstream"):
            continue
        stages = fm["stages"]
        pause_idx = next((i for i, st in enumerate(stages) if st.get("pause_after")), None)
        if pause_idx is None:
            continue
        for st in stages[:pause_idx + 1]:
            if not st.get("subagent_ok", False):
                fails.append(f"{fm['id']} stage {st['id']}")
    assert not fails, (
        "这些阶段（首个 pause_after 停顿阶段之前，含该阶段本身）未标 "
        f"subagent_ok=true，compute 子代理无法从 stage 0 连续跑到停顿点：{fails}")


def test_skill_routes_batch_via_engine_core_not_ref():
    root = os.path.dirname(SCRIPTS_DIR)
    skill = open(os.path.join(root, "SKILL.md"), encoding="utf-8").read()
    # SKILL.md 提到批量、并指向 engine-core；但不得直接引用 batch-orchestration.md（越界守卫）
    assert "批量" in skill or "batch" in skill
    assert "batch-orchestration.md" not in skill
    core = open(os.path.join(root, "references", "engine-core.md"), encoding="utf-8").read()
    assert "batch-orchestration.md" in core
    assert "scripts/batch.py" in core or "batch.py" in core
