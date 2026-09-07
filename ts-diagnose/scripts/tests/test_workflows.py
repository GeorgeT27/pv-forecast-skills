"""workflows/*.js 静态守卫：meta 纯字面量、无 Date.now/Math.random/文件系统、agentType 来自 args、node --check 通过；
另加共用 CONTRACT 与两张 worker 卡片输出契约示例的相容性（同一支脚本派两种 task）。"""
import glob
import json
import os
import re
import shutil
import subprocess

import pytest

ENGINE_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
WF_DIR = os.path.join(ENGINE_DIR, "workflows")
AGENTS_DIR = os.path.join(ENGINE_DIR, "agents")
FILES = sorted(glob.glob(os.path.join(WF_DIR, "*.js")))
BANNED = ("Date.now(", "Math.random(", "new Date(", "require(", "import ", "fs.", "process.")
CARDS = ("model-improve-worker.md", "architecture-attribution-worker.md")


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


def _contract():
    """不依赖 node：从 JS 源抠出 const CONTRACT 字面量转成 JSON（键补引号、单引号换双引号、去尾逗号）。"""
    src = open(os.path.join(WF_DIR, "ts-train-batch.js"), encoding="utf-8").read()
    m = re.search(r"^const CONTRACT = (\{.*?^\})$", src, re.S | re.M)
    assert m, "ts-train-batch.js 里找不到 const CONTRACT = {...} 字面量"
    js = re.sub(r"([{,]\s*)([A-Za-z_]\w*)\s*:", r'\1"\2":', m.group(1)).replace("'", '"')
    return json.loads(re.sub(r",(\s*[}\]])", r"\1", js))


def _card_example(name):
    """卡片「输出契约」节的 ```json 示例块；status 占位形如 `A | B | C`，拆成候选列表。"""
    body = open(os.path.join(AGENTS_DIR, name), encoding="utf-8").read()
    m = re.search(r"```json\n(.*?)\n```", body, re.S)
    assert m, f"{name} 缺 ```json 输出契约示例块"
    doc = json.loads(m.group(1))
    if isinstance(doc.get("status"), str) and "|" in doc["status"]:
        doc["status"] = [s.strip() for s in doc["status"].split("|")]
    return doc


def _json_type(v):
    if v is None:
        return "null"
    if isinstance(v, bool):
        return "boolean"
    if isinstance(v, (int, float)):
        return "number"
    if isinstance(v, str):
        return "string"
    if isinstance(v, list):
        return "array"
    return "object"


def _check(doc, contract):
    """jsonschema 可导入就用它；否则退回最小检查：required 齐、每个属性的 type 相容（type 可为列表）。"""
    try:
        import jsonschema
    except ImportError:
        jsonschema = None
    if jsonschema is not None:
        jsonschema.validate(doc, contract)
        return
    for k in contract["required"]:
        assert k in doc, f"输出契约示例缺 required 字段 {k!r}"
    for k, v in doc.items():
        spec = (contract.get("properties") or {}).get(k)
        if not spec or "type" not in spec:
            continue
        allowed = spec["type"] if isinstance(spec["type"], list) else [spec["type"]]
        assert _json_type(v) in allowed, f"{k!r} 实际类型 {_json_type(v)} 不在契约 {allowed} 里"


@pytest.mark.parametrize("card", CARDS)
def test_card_output_example_satisfies_shared_contract(card):
    """运行时按 CONTRACT 校验 worker 的 final message：任一张卡片的输出契约示例过不了 CONTRACT，
    该 task 的派发就回不来（intervention 的 config_diff 是 CLI 开关数组）。"""
    contract = _contract()
    doc = _card_example(card)
    enum = contract["properties"]["status"]["enum"]
    status = doc["status"]
    for s in (status if isinstance(status, list) else [status]):
        assert s in enum, f"{card} 的 status 取值 {s!r} 不在契约 enum {enum} 里"
    doc["status"] = status[0] if isinstance(status, list) else status
    _check(doc, contract)


def test_contract_config_diff_accepts_object_and_array():
    """model-improve-worker 回 config_diff 对象，architecture-attribution-worker 回 CLI 开关数组。"""
    spec = _contract()["properties"]["config_diff"]["type"]
    assert isinstance(spec, list) and set(spec) == {"object", "array"}


@pytest.mark.skipif(shutil.which("node") is None, reason="无 node")
@pytest.mark.parametrize("path", FILES, ids=[os.path.basename(p) for p in FILES])
def test_node_syntax(path, tmp_path):
    # Workflow 运行时把脚本包进 async 函数（顶层 await / return 合法）；这里同样包一层再 node --check
    src = open(path, encoding="utf-8").read().replace("export const meta", "const meta", 1)
    cjs = tmp_path / (os.path.basename(path) + ".cjs")
    cjs.write_text("async function __wf(args, agent, parallel, pipeline, phase, log) {\n" + src + "\n}\n", encoding="utf-8")
    r = subprocess.run(["node", "--check", str(cjs)], capture_output=True, text=True)
    assert r.returncode == 0, r.stderr
