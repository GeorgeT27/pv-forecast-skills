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


# 入口闸（五件套）恒问：training_log/truth/train_y/checkpoint/model_code——
# 本 PB 用两阶段测 --goto 校验，truth 同时是 required 材料，故用 present-完整记录覆盖，
# 其余四件走 absent-confirmed+source=user。
FIVE_OK = {mid: {"status": "absent-confirmed", "source": "user"}
           for mid in ("training_log", "train_y", "checkpoint", "model_code")}


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
    prog = (wd / "PROGRESS.md").read_text(encoding="utf-8")
    assert "--force" in prog and "跳过前置" in prog
