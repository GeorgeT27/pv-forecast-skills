"""workflows/*.js 静态守卫：meta 纯字面量、无 Date.now/Math.random/文件系统、agentType 来自 args、node --check 通过。"""
import glob
import os
import re
import shutil
import subprocess

import pytest

ENGINE_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
WF_DIR = os.path.join(ENGINE_DIR, "workflows")
FILES = sorted(glob.glob(os.path.join(WF_DIR, "*.js")))
BANNED = ("Date.now(", "Math.random(", "new Date(", "require(", "import ", "fs.", "process.")


def test_train_batch_exists():
    assert os.path.join(WF_DIR, "ts-train-batch.js") in FILES


@pytest.mark.parametrize("path", FILES, ids=[os.path.basename(p) for p in FILES])
def test_meta_literal_and_bans(path):
    src = open(path, encoding="utf-8").read()
    assert src.lstrip().startswith("export const meta = {"), "脚本必须以 export const meta 纯字面量开头"
    head = src.split("}", 1)[0]
    assert re.search(r"name:\s*'[a-z0-9-]+'", head) and "description:" in head
    for b in BANNED:
        assert b not in src, f"workflow 脚本不得含 {b!r}"
    assert "agentType: a.agent_type" in src, "agentType 必须来自 args.agent_type（两本 playbook 共用一支脚本）"
    assert "schema: CONTRACT" in src


def test_train_batch_prompt_only_card_input_fields():
    # 候选对象（experiment_log.py cmd_candidates 产出）还带 source/predicted_gain 等字段；
    # prompt 只能带卡片「输入」四个字段，不能把整个候选对象原样喂给 worker。
    src = open(os.path.join(WF_DIR, "ts-train-batch.js"), encoding="utf-8").read()
    for field in ("exp_id", "hypothesis_id", "config_diff", "guard_slices"):
        assert field in src, f"prompt 取值需覆盖卡片输入字段 {field!r}"
    assert "JSON.stringify(c)" not in src, "prompt 不得把候选对象整体（含 source/predicted_gain 等）原样传给 worker"


@pytest.mark.skipif(shutil.which("node") is None, reason="无 node")
@pytest.mark.parametrize("path", FILES, ids=[os.path.basename(p) for p in FILES])
def test_node_syntax(path, tmp_path):
    # Workflow 运行时把脚本包进 async 函数（顶层 await / return 合法）；这里同样包一层再 node --check
    src = open(path, encoding="utf-8").read().replace("export const meta", "const meta", 1)
    cjs = tmp_path / (os.path.basename(path) + ".cjs")
    cjs.write_text("async function __wf(args, agent, parallel, pipeline, phase, log) {\n" + src + "\n}\n", encoding="utf-8")
    r = subprocess.run(["node", "--check", str(cjs)], capture_output=True, text=True)
    assert r.returncode == 0, r.stderr
