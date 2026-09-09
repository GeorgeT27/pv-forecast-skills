"""orient --goto 护栏测试：前置不齐拒绝直达，--force 放行且留痕（阶段闸之一）。

自包含：不依赖 test_orient_materials.py 的 fixture，仅复用其 run_orient/FIVE_OK 模式
（同一入口闸约束，见该文件顶部注释）。
"""
import os
import subprocess
import sys

SCRIPTS_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ORIENT = os.path.join(SCRIPTS_DIR, "orient.py")
sys.path.insert(0, SCRIPTS_DIR)
import engine_common as ec  # noqa: E402

PB = """---
id: goto-demo
name: goto 护栏演示
goal: 测试 --goto 前置校验
materials:
  required: [predict, truth]
stages:
  - id: 0
    name: 起步
    done_when: {artifacts: ['stage0.json']}
  - id: 1
    name: 后续
    prereqs:
      - {desc: 前一阶段, check: 'stage:0'}
    done_when: {artifacts: ['stage1.json']}
---
正文占位。
"""


def run_orient(workdir, *args):
    r = subprocess.run([sys.executable, ORIENT, *args], cwd=workdir,
                       capture_output=True, text=True, timeout=60)
    assert r.returncode == 0, r.stderr
    return r.stdout


# 本 PB 用两阶段测 --goto 校验；额外材料记录仅作兼容夹具。
FIVE_OK = {mid: {"status": "absent-confirmed", "source": "user"}
           for mid in ("training_log", "train_y", "checkpoint", "model_code")}


# 会产 CONCLUSION.md 的剧本——「全部完成 → 指路结论闸」这条只对它成立。
# 此前夹具的唯一阶段产 stage0.json，是个错样例：不产结论的剧本本就不该被指去写结论。
PB_ONE_STAGE = """---
id: all-done-demo
name: 全部完成演示
goal: 测试 Mode A 全部阶段完成路径的收尾提示
materials:
  required: [predict, truth]
stages:
  - id: 0
    name: 起步
    done_when: {artifacts: ['CONCLUSION.md', 'gate_reports/conclusion_gate.json']}
---
正文占位。
"""


# 对照：不产结论的生产者剧本（data-setup/metric-eval/model-audit/model-comparison/
# fact-scan 那一类），全部完成时必须改口，不许再指它去写 CONCLUSION.md（r2 联调 R2-3）。
PB_PRODUCER = """---
id: producer-demo
name: 生产者演示
goal: 测试全部完成时生产者收到的收尾提示
produces:
  id: demo_product
  manifest: demo_manifest.json
  marker_files: [stage0.json]
materials:
  required: [predict, truth]
stages:
  - id: 0
    name: 起步
    done_when: {artifacts: ['stage0.json']}
---
正文占位。
"""


def setup_one_stage_pb(tmp_path, pb_text=PB_ONE_STAGE):
    pb = tmp_path / "pb" / "playbook.md"
    pb.parent.mkdir()
    pb.write_text(pb_text, encoding="utf-8")
    mats = dict(FIVE_OK)
    mats["predict"] = {"status": "present", "paths": ["p.parquet"],
                        "schema": {"y_col": "y", "time_col": "ts"}}
    mats["truth"] = {"status": "present", "paths": ["t.parquet"],
                      "schema": {"y_col": "y", "time_col": "ts"}}
    cfg = {"playbook": str(pb), "materials": mats}
    ec.dump_json(cfg, str(tmp_path / "diagnose_config.json"))
    return tmp_path


def test_all_stages_done_completion_message_points_at_conclusion_gate(tmp_path):
    """I-2：Mode A（cur is None，全部阶段完成）的收尾提示必须指路结论闸——
    不能只说"可写/刷新 CONCLUSION.md"就完了，得带上跑 conclusion_gate.py 的硬要求，
    否则结论闸形同虚设（模型写完 CONCLUSION.md 就以为交付了）。"""
    wd = setup_one_stage_pb(tmp_path)
    (wd / "CONCLUSION.md").write_text("# c\n", encoding="utf-8")
    (wd / "gate_reports").mkdir()
    (wd / "gate_reports" / "conclusion_gate.json").write_text("{}", encoding="utf-8")
    out = run_orient(wd)
    assert "全部阶段完成" in out
    assert "conclusion_gate" in out


def test_producer_completion_message_does_not_point_at_conclusion(tmp_path):
    """R2-3：生产者剧本全部完成时，收尾提示必须改口——它没有结论阶段，
    Stop 钩子也按 frontmatter 判定它不产结论，这里再教它写 CONCLUSION.md 就是自相矛盾。"""
    wd = setup_one_stage_pb(tmp_path, pb_text=PB_PRODUCER)
    (wd / "stage0.json").write_text("{}", encoding="utf-8")
    out = run_orient(wd)
    assert "全部阶段完成" in out
    assert "不写 CONCLUSION.md" in out
    assert "demo_product" in out          # 交付什么要说清楚
    assert "可写/刷新 CONCLUSION.md" not in out
    assert "conclusion_gate" not in out


# manual 阶段：没有产物判据，完成标记只有主 agent 会写。R2-2 之前这件事只写在
# engine_common.py 的代码注释里，剧本与 orient 输出一个字都没有——agent 得自己猜。
PB_MANUAL = """---
id: manual-demo
name: manual 阶段演示
goal: 测试 manual 阶段的完成方式有没有打印到眼前
materials:
  required: [predict, truth]
stages:
  - id: 0
    name: 人工确认
    done_when: {manual: true}
  - id: 1
    name: 后续
    prereqs:
      - {desc: 前一阶段, check: 'stage:0'}
    done_when: {artifacts: ['stage1.json']}
---
正文占位。
"""


def test_manual_stage_prints_how_to_mark_it_done(tmp_path):
    """R2-2：manual 阶段做完要把 stage id 写进 state.manual_done，否则 orient 永远
    判它未完成、流程原地打转。这条必须打印到眼前——它是 agent 不可能从产物推出来的。"""
    wd = setup_one_stage_pb(tmp_path, pb_text=PB_MANUAL)
    out = run_orient(wd)
    assert "manual_done" in out, "manual 阶段没告诉 agent 怎么标完成"
    assert "diagnose_state.json" in out


def test_manual_done_actually_closes_the_stage(tmp_path):
    """指令得是真的：写进 manual_done 之后阶段必须真的关掉，当前阶段前移。"""
    wd = setup_one_stage_pb(tmp_path, pb_text=PB_MANUAL)
    assert "进入 Stage 0 的前置" in run_orient(wd)
    st = ec.read_json(str(wd / "diagnose_state.json"))
    st["manual_done"] = [0]
    ec.dump_json(st, str(wd / "diagnose_state.json"))
    out = run_orient(wd)
    assert "进入 Stage 1 的前置" in out
    # 不能断言 "manual_done" 不出现：pytest 的临时目录名里就带这几个字，
    # 而 orient 会打印工作目录。认那条提示自己的标记。
    assert "done_when.manual" not in out     # Stage 1 不是 manual，就别再念这条


def setup_two_stage_pb(tmp_path):
    pb = tmp_path / "pb" / "playbook.md"
    pb.parent.mkdir()
    pb.write_text(PB, encoding="utf-8")
    mats = dict(FIVE_OK)
    mats["predict"] = {"status": "present", "paths": ["p.parquet"],
                        "schema": {"y_col": "y", "time_col": "ts"}}
    mats["truth"] = {"status": "present", "paths": ["t.parquet"],
                      "schema": {"y_col": "y", "time_col": "ts"}}
    cfg = {"playbook": str(pb), "materials": mats}
    ec.dump_json(cfg, str(tmp_path / "diagnose_config.json"))
    return tmp_path


def test_goto_refused_without_force(tmp_path):
    wd = setup_two_stage_pb(tmp_path)          # stage0.json 不存在
    out = run_orient(wd, "--goto", "1")
    assert "⛔ 拒绝直达 Stage 1" in out
    assert "正确入口 = Stage 0" in out
    assert "三道门" not in out                  # 不吐目标阶段的自检/菜谱指引
    # ⛔ 块唯一负责拒绝措辞——旧 elif 分支的"不能直达"不得再重复一遍拒绝
    assert "不能直达" not in out


def test_goto_force_allows_and_logs(tmp_path):
    wd = setup_two_stage_pb(tmp_path)
    out = run_orient(wd, "--goto", "1", "--force")
    assert "⛔" not in out
    assert "进入 Stage 1 的前置" in out
    # --force 放行后不得在同一输出里又打印"不能直达"，自相矛盾
    assert "不能直达" not in out
    audit = (wd / ".orient_audit.jsonl").read_text(encoding="utf-8")
    assert "--force" in audit and "跳过前置" in audit


def test_goto_force_with_met_prereqs_no_skip_suffix(tmp_path):
    """M-c：--force 留痕不撒谎——前置本就齐时，即使带 --force，PROGRESS 也不该写
    「跳过前置」（那是没发生的事）。只有 force 真的放行了本会被拒绝的直达才记这笔。"""
    wd = setup_two_stage_pb(tmp_path)
    (wd / "stage0.json").write_text("{}", encoding="utf-8")   # Stage 0 前置已满足
    out = run_orient(wd, "--goto", "1", "--force")
    assert "⛔" not in out
    assert "进入 Stage 1 的前置" in out
    audit = (wd / ".orient_audit.jsonl").read_text(encoding="utf-8")
    assert "（--goto 1）" in audit
    assert "跳过前置" not in audit
