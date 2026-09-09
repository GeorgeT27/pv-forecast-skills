# ts-diagnose 打包 + 逐回合负载缩短 实施计划（Phase 1–2）

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 把 ts-diagnose 整理成一个可用 `install.sh` 装到另一台 Claude Code 设备的完整包（skill 壳 + agents 卡片 + hooks），退役 v2，并让每回合进入上下文的指令量减半而内容不减。

**Architecture:** 包内文件不搬家；`agents/`（13 张卡片）、`hooks/`（三钩子 + 幂等合并器）、`install.sh` 新增在 `ts-diagnose/` 下，`install.sh` 用 symlink 把它们放到 `~/.claude/{skills,agents,workflows}` 与 `settings.json`。派发层改为「按名字派卡片，未注册则把卡片全文当 prompt 回退」。缩短靠 orient 每回合打印当前阶段菜谱原文，engine-core 只留代码查不了的判断规则，SKILL.md description 只留触发短语。

**Tech Stack:** Python 3 + pyyaml + pytest（引擎既有）、bash（install.sh）、Claude Code 原生 agents/hooks 目录。

**Spec:** `docs/superpowers/specs/2026-09-06-ts-diagnose-packaging-design.md`

## Global Constraints

- 仓库纪律：绝不 `git add -A`；只按显式路径 stage；每个 task 原子提交；提交信息末尾带 `Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>` 与 `Claude-Session: https://claude.ai/code/session_01AKCjyuiAiWvtupjpTfi59f` 两行。
- 所有 pytest 命令在 `ts-diagnose/` 目录下跑：`cd ts-diagnose && python3 -m pytest scripts/tests -q`（全量含 chartbook 时 `python3 -m pytest scripts/tests chartbook/tests -q`）。基线：410 项通过。
- 卡片正文非空行 ≤ 80；正文不得出现 `## 逐阶段菜谱` / `### Stage` / `## 2. 逐阶段`；六节标题固定：你是谁 / 输入 / 步骤 / 红线 / 输出契约 / 停顿。
- SKILL.md ≤ 60 行、估算 ≤ 6000 token（`test_layering.py`）；正文只许引用 `references/engine-core.md` 与 `references/crystallize.md`。
- playbook 之间零交叉引用（`test_layering.py::test_layer1_playbooks_independent`）。
- 文档写法：技能文件每句只许是指令或执行所需事实，不写术语解释、不写设计动机。
- 仓库根 `hooks/` 路径必须继续有效（外部 `run_blind.wire_hooks()` 按此路径接线）。
- 弱模型保障：指令内容只改出现时机，不删除任何硬规则、合理化对照表、红线。

---

## 文件结构（本计划涉及）

| 路径 | 动作 | 职责 |
|---|---|---|
| `ts-diagnose/hooks/{stage_probe,gate_guard,orient_reminder}.py` | 从仓库根 `git mv` 迁入 | 三钩子脚本（不改内容） |
| `hooks` （仓库根） | 变为 symlink → `ts-diagnose/hooks` | 保住外部路径 |
| `ts-diagnose/hooks/hooks.json` | 新建 | 三钩子事件声明，`<PKG>` 占位 |
| `ts-diagnose/hooks/install_hooks.py` | 新建 | 幂等合并/卸载进 settings.json |
| `ts-diagnose/scripts/tests/test_install_hooks.py` | 新建 | 合并器测试 |
| `ts-diagnose/agents/_agent-spec.md` | 从 v2 拷入并改 | 卡片规格（加 worker 模式、80 行预算） |
| `ts-diagnose/agents/<11 张>-compute.md` | 从 v2 拷入并改 | 路径改 `<ENGINE>`，区间重核 |
| `ts-diagnose/agents/architecture-attribution-compute.md` | 新建 | Stage 0 计算卡 |
| `ts-diagnose/agents/architecture-attribution-worker.md` | 新建 | Stage 0 噪声底 / Stage 3 单条干预重训工 |
| `ts-diagnose/scripts/tests/test_cards.py` | 从 v2 拷入并改 | 卡片守卫（含 worker 分支、`<ENGINE>` 断言） |
| `ts-diagnose/references/engine-core.md` | 改 | Phase 1：派发节改卡片；Phase 2：整体精简 |
| `ts-diagnose/references/subagent-briefs.md` | 重写 | 共用派发纪律 + 卡片索引 + 回退 + NEED_INFO 回环 + Brief-EMBED |
| `ts-diagnose/references/batch-orchestration.md` | 改 | Phase C worker = 卡片，删 Brief-BATCH-COMPUTE |
| `ts-diagnose/scripts/orient.py` | 改 | 派发措辞；Phase 2 菜谱打印 + `--no-recipe/--recipe` |
| `ts-diagnose/scripts/engine_common.py` | 改 | Phase 2 `recipe_sections()` |
| `ts-diagnose/scripts/tests/test_dispatch_docs.py` | 新建 | 派发文档一致性守卫 |
| `ts-diagnose/scripts/tests/test_recipe_sections.py` | 新建 | 每阶段恰好一节 |
| `ts-diagnose/scripts/tests/test_install_sh.py` | 新建 | install.sh 端到端（临时 CLAUDE_HOME） |
| `ts-diagnose/install.sh` / `ts-diagnose/INSTALL.md` | 新建 | 安装脚本 / 安装说明 |
| `ts-diagnose/SKILL.md` | Phase 2 改 | description 精简 |
| `ts-diagnose/scripts/tests/test_routing.py` | Phase 2 改 | description 枚举断言改为路由表 |
| `ts-diagnose-v2/` | `git rm -r` | 退役 |
| `.claude/settings.json`、`.claude/settings.local.json`、`README.md`、`ts-diagnose/CHANGELOG.md` | 改 | 路径/退役/沿革 |

---

# Phase 1：卡片进 v1 + 包结构 + v2 退役

### Task 0: 把现有未提交改动单独入库，开工作分支

**Files:**
- Commit: `ts-diagnose/**`（31 个已修改文件）、`hooks/stage_probe.py`
- 不动：`短期分析/**` 的未提交改动（另一条工作线）

**Interfaces:**
- Produces: 干净的 ts-diagnose 基线提交 + 分支 `ts-diagnose-packaging`

- [ ] **Step 1: 确认基线绿**

Run: `cd ts-diagnose && python3 -m pytest scripts/tests chartbook/tests -q 2>&1 | tail -3`
Expected: `410 passed`（数字可略大，不得有 failed）

- [ ] **Step 2: 看清未提交 diff 属于哪次工作**

Run: `git diff -- ts-diagnose/CHANGELOG.md | head -20`
Expected: 新增一行以 `- 2026-08-31 | conclusion_gate 规则 5+6` 开头。

- [ ] **Step 3: 只提交 ts-diagnose 与 hooks 的改动**

```bash
git add ts-diagnose hooks/stage_probe.py
git status --short | grep -v '^ M 短期' | grep -v '^ D "' | grep -v '^?? ' | head
git commit -m "feat(ts-diagnose): conclusion_gate 规则 5+6（溯源闭环+证据清单）+ stage_probe 指纹排除轨迹日志 — 打包前基线

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01AKCjyuiAiWvtupjpTfi59f"
```

- [ ] **Step 4: 开分支**

Run: `git checkout -b ts-diagnose-packaging`
Expected: `Switched to a new branch 'ts-diagnose-packaging'`

---

### Task 1: hooks 迁入包内 + 根目录 symlink + hooks.json + install_hooks.py

**Files:**
- Move: `hooks/*.py` → `ts-diagnose/hooks/*.py`
- Create: `hooks`（仓库根 symlink → `ts-diagnose/hooks`）
- Create: `ts-diagnose/hooks/hooks.json`
- Create: `ts-diagnose/hooks/install_hooks.py`
- Test: `ts-diagnose/scripts/tests/test_install_hooks.py`
- Modify: `.claude/settings.json`（stage_probe 绝对路径改指新位置）

**Interfaces:**
- Produces: `install_hooks.py main(argv) -> int`，参数 `--settings <path>` `--uninstall` `--dry-run`；`load_hooks_json() -> dict[event, list[entry]]`；`is_ours(entry) -> bool`（按三个脚本文件名识别）。

- [ ] **Step 1: 迁移并建 symlink**

```bash
git mv hooks ts-diagnose/hooks
ln -s ts-diagnose/hooks hooks
git add hooks
ls -la hooks && ls ts-diagnose/hooks
```
Expected: `hooks -> ts-diagnose/hooks`；三个 .py 在新位置。

- [ ] **Step 2: 确认外部路径仍有效**

Run: `python3 hooks/stage_probe.py --selftest && python3 hooks/gate_guard.py --selftest`
Expected: 两个自检都以 0 退出（输出含 PASS/ok 字样）。

- [ ] **Step 3: 看 gate_guard 的 block 输出格式（供 hooks.json 决定要不要 `|| true`）**

Run: `sed -n '60,120p' ts-diagnose/hooks/gate_guard.py`
Expected: `run_hook()` 末尾要么 `print(json.dumps({"decision": "block", "reason": ...}))` 后 `sys.exit(0)`，要么 `sys.exit(2)` 并写 stderr。若是 JSON decision 形式，Stop 条目**不加** `|| true` 也可加；若是 exit 2 形式，Stop 条目**绝不能**加 `|| true`。下一步按此写。

- [ ] **Step 4: 写 hooks.json**

```json
{
  "hooks": {
    "PostToolUse": [
      {
        "matcher": "Bash|Write|Edit",
        "hooks": [
          {"type": "command", "command": "python3 \"<PKG>/hooks/stage_probe.py\" 2>/dev/null || true", "timeout": 10}
        ]
      }
    ],
    "Stop": [
      {
        "hooks": [
          {"type": "command", "command": "python3 \"<PKG>/hooks/gate_guard.py\"", "timeout": 15}
        ]
      }
    ],
    "UserPromptSubmit": [
      {
        "hooks": [
          {"type": "command", "command": "python3 \"<PKG>/hooks/orient_reminder.py\" 2>/dev/null || true", "timeout": 5}
        ]
      }
    ]
  }
}
```

- [ ] **Step 5: 写失败测试**

`ts-diagnose/scripts/tests/test_install_hooks.py`:

```python
import json, os, sys
HERE = os.path.dirname(os.path.abspath(__file__))
ENGINE_DIR = os.path.dirname(os.path.dirname(HERE))
sys.path.insert(0, os.path.join(ENGINE_DIR, "hooks"))
import install_hooks as ih  # noqa: E402

SCRIPTS = ("stage_probe.py", "gate_guard.py", "orient_reminder.py")


def _cmds(settings):
    return [h["command"] for ev in settings.get("hooks", {}).values()
            for e in ev for h in e["hooks"]]


def test_hooks_json_resolves_pkg_and_scripts_exist():
    ours = ih.load_hooks_json()
    assert set(ours) == {"PostToolUse", "Stop", "UserPromptSubmit"}
    for ev in ours.values():
        for e in ev:
            for h in e["hooks"]:
                assert "<PKG>" not in h["command"]
                path = h["command"].split('"')[1]
                assert os.path.isfile(path), path


def test_merge_into_empty_then_idempotent(tmp_path):
    s = tmp_path / "settings.json"
    ih.main(["--settings", str(s)])
    first = json.loads(s.read_text(encoding="utf-8"))
    assert sorted(os.path.basename(c.split('"')[1]) for c in _cmds(first)) == sorted(SCRIPTS)
    ih.main(["--settings", str(s)])
    second = json.loads(s.read_text(encoding="utf-8"))
    assert first == second


def test_merge_preserves_foreign_entries_and_uninstall_removes_only_ours(tmp_path):
    s = tmp_path / "settings.json"
    foreign = {"hooks": {"PostToolUse": [{"matcher": "Bash", "hooks": [
        {"type": "command", "command": "echo foreign"}]}]}, "permissions": {"allow": ["x"]}}
    s.write_text(json.dumps(foreign), encoding="utf-8")
    ih.main(["--settings", str(s)])
    merged = json.loads(s.read_text(encoding="utf-8"))
    assert "echo foreign" in _cmds(merged)
    assert merged["permissions"] == {"allow": ["x"]}
    ih.main(["--settings", str(s), "--uninstall"])
    after = json.loads(s.read_text(encoding="utf-8"))
    assert _cmds(after) == ["echo foreign"]
    assert "Stop" not in after["hooks"]


def test_dry_run_writes_nothing(tmp_path, capsys):
    s = tmp_path / "settings.json"
    ih.main(["--settings", str(s), "--dry-run"])
    assert not s.exists()
    assert "gate_guard.py" in capsys.readouterr().out
```

- [ ] **Step 6: 跑测试确认失败**

Run: `cd ts-diagnose && python3 -m pytest scripts/tests/test_install_hooks.py -q`
Expected: FAIL，`ModuleNotFoundError: No module named 'install_hooks'`

- [ ] **Step 7: 写 install_hooks.py**

```python
#!/usr/bin/env python3
"""把 hooks.json 声明的三条 ts-diagnose 钩子幂等合并进 Claude Code settings.json。

用法：
  python3 install_hooks.py                       # 合并进 ~/.claude/settings.json
  python3 install_hooks.py --settings <path>     # 指定文件（本仓库 .claude/settings.json 也用它）
  python3 install_hooks.py --uninstall           # 只删自家条目
  python3 install_hooks.py --dry-run             # 打印将写入的 JSON，不落盘
识别自家条目：命令串里出现三个脚本文件名之一。
"""
from __future__ import annotations
import argparse, json, os

HERE = os.path.dirname(os.path.abspath(__file__))
PKG = os.path.dirname(HERE)
SCRIPTS = ("stage_probe.py", "gate_guard.py", "orient_reminder.py")


def load_hooks_json():
    with open(os.path.join(HERE, "hooks.json"), encoding="utf-8") as f:
        return json.loads(f.read().replace("<PKG>", PKG))["hooks"]


def is_ours(entry):
    return any(any(s in (h.get("command") or "") for s in SCRIPTS)
               for h in (entry.get("hooks") or []))


def merge(settings, ours):
    hooks = settings.setdefault("hooks", {})
    for event, entries in ours.items():
        hooks[event] = [e for e in (hooks.get(event) or []) if not is_ours(e)] + entries
    return settings


def remove(settings):
    hooks = settings.get("hooks") or {}
    for event in list(hooks):
        hooks[event] = [e for e in hooks[event] if not is_ours(e)]
        if not hooks[event]:
            del hooks[event]
    return settings


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--settings", default=os.path.expanduser("~/.claude/settings.json"))
    ap.add_argument("--uninstall", action="store_true")
    ap.add_argument("--dry-run", action="store_true")
    a = ap.parse_args(argv)
    settings = {}
    if os.path.exists(a.settings):
        with open(a.settings, encoding="utf-8") as f:
            settings = json.load(f)
    settings = remove(settings) if a.uninstall else merge(settings, load_hooks_json())
    out = json.dumps(settings, ensure_ascii=False, indent=2)
    if a.dry_run:
        print(out)
        return 0
    os.makedirs(os.path.dirname(os.path.abspath(a.settings)), exist_ok=True)
    with open(a.settings, "w", encoding="utf-8") as f:
        f.write(out + "\n")
    print(f"{'removed' if a.uninstall else 'merged'} ts-diagnose hooks → {a.settings}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
```

- [ ] **Step 8: 跑测试确认通过**

Run: `cd ts-diagnose && python3 -m pytest scripts/tests/test_install_hooks.py -q`
Expected: `4 passed`

- [ ] **Step 9: 本仓库 .claude/settings.json 改指新路径**

Run: `python3 ts-diagnose/hooks/install_hooks.py --settings .claude/settings.json && cat .claude/settings.json`
Expected: 三条钩子，命令路径都在 `.../ts-diagnose/hooks/`；旧的根目录 `hooks/stage_probe.py` 条目已被替换。

- [ ] **Step 10: 全量测试 + 提交**

Run: `cd ts-diagnose && python3 -m pytest scripts/tests -q 2>&1 | tail -2`
Expected: 全绿（基线 + 4）。

```bash
git add hooks ts-diagnose/hooks ts-diagnose/scripts/tests/test_install_hooks.py .claude/settings.json
git commit -m "feat(ts-diagnose): hooks 迁入包内（根目录 symlink 保路径）+ hooks.json + 幂等合并器 install_hooks.py

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01AKCjyuiAiWvtupjpTfi59f"
```

---

### Task 2: 从 v2 移植 11 张卡片、规格与守卫到 v1

**Files:**
- Create: `ts-diagnose/agents/_agent-spec.md`、`ts-diagnose/agents/*-compute.md`（11 张）
- Create: `ts-diagnose/scripts/tests/test_cards.py`

**Interfaces:**
- Produces: 卡片 frontmatter 契约 `name / description / mode / playbook / compute_stages / tools / model`；卡片正文占位 `<ENGINE>`（引擎绝对路径）与 `<workdir>`（工作目录绝对路径），主 agent 派发时替换。

- [ ] **Step 1: 拷入**

```bash
mkdir -p ts-diagnose/agents
cp ts-diagnose-v2/agents/*.md ts-diagnose/agents/
cp ts-diagnose-v2/scripts/tests/test_cards.py ts-diagnose/scripts/tests/test_cards.py
ls ts-diagnose/agents | wc -l
```
Expected: 12（11 卡 + `_agent-spec.md`）。

- [ ] **Step 2: 守卫路径改 v1**

在 `ts-diagnose/scripts/tests/test_cards.py` 顶部，把

```python
SCRIPTS_DIR = os.path.join(os.path.dirname(HERE))          # ts-diagnose-v2/scripts
V2 = os.path.dirname(SCRIPTS_DIR)                          # ts-diagnose-v2
AGENTS_DIR = os.path.join(V2, "agents")
```
改为
```python
SCRIPTS_DIR = os.path.dirname(HERE)                        # ts-diagnose/scripts
ENGINE_DIR = os.path.dirname(SCRIPTS_DIR)                  # ts-diagnose
AGENTS_DIR = os.path.join(ENGINE_DIR, "agents")
```

- [ ] **Step 3: 跑守卫，看 v1/v2 漂移**

Run: `cd ts-diagnose && python3 -m pytest scripts/tests/test_cards.py -q 2>&1 | tail -15`
Expected: 大多数通过；失败项的断言信息形如 `compute 区间 stage N 必须 subagent_ok:true` 或 `compute 区间须含 pause_after` 或 `producer compute_stages ends at stage …`。

- [ ] **Step 4: 逐张修正失败卡片的 `compute_stages`**

对每个失败的 `<id>`，先看 v1 当前阶段形状：

```bash
cd ts-diagnose && python3 - <<'EOF'
import sys; sys.path.insert(0,'scripts'); import engine_common as ec
for pid in ["training-sufficiency","robustness","feature-importance","model-comparison","deployment-drift","fact-scan","result-eval","subset-influence","data-setup","metric-eval","model-audit"]:
    fm=ec.load_frontmatter(ec.find_playbook(pid))
    print(pid, [(s['id'], bool(s.get('pause_after')), bool(s.get('subagent_ok'))) for s in fm['stages']])
EOF
```
规则：compute 卡 = 从 Stage 0 起连续 `subagent_ok:true`、到**第一个** `pause_after:true` 为止的区间；producer 卡 = 到产物 manifest/marker 落盘的阶段为止。按此改卡片 frontmatter 的 `compute_stages`，并同步改「步骤」节里的「Stage `lo-hi`」文字。

- [ ] **Step 5: 卡片里的脚本路径改为 `<ENGINE>` 绝对路径形态**

v2 卡片写的是 `python3 scripts/orient.py …`，在工作目录里跑不到。全量替换：

```bash
cd ts-diagnose/agents && sed -i '' \
  -e 's#`python3 scripts/orient.py#`python3 "<ENGINE>/scripts/orient.py"#g' \
  -e 's#`python3 scripts/gen_gate.py#`python3 "<ENGINE>/scripts/gen_gate.py"#g' \
  -e 's#（golden 在副本的 playbook 目录，脚本自动引用，卡片不内联菜谱正文）#（在 `<workdir>` 下运行；`<ENGINE>` = 主 agent 派发时填入的引擎绝对路径；golden 由脚本按 playbook 目录自动引用）#g' \
  *-compute.md
grep -L '<ENGINE>/scripts/orient.py' *-compute.md
```
Expected: 最后一条 grep 无输出（每张卡都含新写法）。若某张卡的原句式不同导致未替换，手工把「步骤」节里的两条命令改成上述写法。

- [ ] **Step 6: 「输入」节加引擎目录字段**

每张卡「输入」节第一条 `- 工作目录：\`<workdir>\`` 之后加一行 `- 引擎目录：\`<ENGINE>\`（绝对路径，含 scripts/ playbooks/ chartbook/）`。

```bash
cd ts-diagnose/agents && sed -i '' 's#^- 工作目录：`<workdir>`$#- 工作目录：`<workdir>`\
- 引擎目录：`<ENGINE>`（绝对路径，含 scripts/ playbooks/ chartbook/）#' *-compute.md
grep -c '引擎目录' *-compute.md
```
Expected: 每张 1。

- [ ] **Step 7: 守卫加 `<ENGINE>` 断言与 80 行预算**

在 `test_cards.py`：`BODY_LINE_BUDGET = 60` 改 `80`；`test_card_conforms` 末尾加：

```python
    assert '"<ENGINE>/scripts/orient.py"' in body, "步骤须用 <ENGINE> 绝对路径调 orient"
    assert "引擎目录：`<ENGINE>`" in body, "输入节须有引擎目录字段"
```

- [ ] **Step 8: 改 `_agent-spec.md` 的运行位置与预算**

把「在 `ts-diagnose-v2/` 下运行」改为「在 `ts-diagnose/` 下运行」；「正文非空行数 ≤60 行」改为「≤80 行」；「全 11 张卡」改为「全部卡片」；§2 frontmatter 示例里 `playbook: <id> # → ./playbooks/<id>/playbook.md（v2 自己的副本…）` 的括号删掉。

- [ ] **Step 9: 守卫全绿**

Run: `cd ts-diagnose && python3 -m pytest scripts/tests/test_cards.py -q`
Expected: `11 passed`

- [ ] **Step 10: 提交**

```bash
git add ts-diagnose/agents ts-diagnose/scripts/tests/test_cards.py
git commit -m "feat(ts-diagnose): 从 v2 移植 11 张 agent 卡片 + _agent-spec + test_cards，区间按 v1 frontmatter 重核，脚本路径改 <ENGINE>

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01AKCjyuiAiWvtupjpTfi59f"
```

---

### Task 3: architecture-attribution 两张新卡 + worker 模式守卫

**Files:**
- Create: `ts-diagnose/agents/architecture-attribution-compute.md`
- Create: `ts-diagnose/agents/architecture-attribution-worker.md`
- Modify: `ts-diagnose/scripts/tests/test_cards.py`（命名律泛化 + worker 分支）
- Modify: `ts-diagnose/agents/_agent-spec.md`（worker 模式行）

**Interfaces:**
- Produces: worker 卡输出契约 JSON 字段 `status, task, hypothesis_id, receipt_line, receipt_file, config_diff, per_seed, mean, std, noise_floor_3sigma, instability_note, need_info, blocked_reason`；frontmatter 新字段 `serves_stages: [int]`。Phase 4 的 `ts-ablation-loop.js` 以此为 schema。

- [ ] **Step 1: 先改守卫（RED）**

`test_cards.py` 中：

`_card_paths()` 改为
```python
def _card_paths():
    pats = ("*-compute.md", "*-worker.md", "*-baseline.md")
    return sorted(p for pat in pats for p in glob.glob(os.path.join(AGENTS_DIR, pat)))
```

`test_card_conforms` 开头的两条命名断言改为
```python
    role = fm["name"].rsplit("-", 1)[1]
    assert role in {"compute", "worker", "baseline"}, "name 须以 -compute/-worker/-baseline 结尾"
    assert fm["name"] == f"{pid}-{role}", "命名律：name == <playbook>-<role>"
    assert os.path.basename(card) == f"{fm['name']}.md", "文件名 == name.md"
    mode = fm["mode"]
    assert mode in {"producer", "compute", "compute-fine", "worker"}
    assert (mode == "worker") == (role in {"worker", "baseline"}), "worker 模式与 -worker/-baseline 后缀一一对应"
```

`else:  # compute-fine` 分支前插入 worker 分支：
```python
    elif mode == "worker":
        assert str(fm.get("compute_stages")) == "scripts"
        served = fm.get("serves_stages") or []
        assert served, "worker 须声明 serves_stages"
        for sid in served:
            assert by_id[str(sid)].get("subagent_ok") is True, f"worker 服务的 stage {sid} 必须 subagent_ok:true"
        assert "receipt_line" in body, "worker 输出契约须含 receipt_line"
```

Run: `cd ts-diagnose && python3 -m pytest scripts/tests/test_cards.py -q`
Expected: `11 passed`（新分支尚无卡片；不失败但也未覆盖——下一步补卡片后变 13）。

- [ ] **Step 2: 查 architecture-attribution 的 Stage 0 问题 id**

Run:
```bash
cd ts-diagnose && python3 -c "
import sys; sys.path.insert(0,'scripts'); import engine_common as ec
fm=ec.load_frontmatter(ec.find_playbook('architecture-attribution'))
print([(q['id'], q['stage']) for q in fm.get('questions',[])])"
```
Expected: 含 `('noise-floor', 0)`；把所有 `stage == 0` 的 id 写进下一步卡片「已答问题」行。

- [ ] **Step 3: 写 compute 卡**

`ts-diagnose/agents/architecture-attribution-compute.md`（若 Step 2 有别的 stage-0 题，追加到「已答问题」行）:

````markdown
---
name: architecture-attribution-compute
description: 架构归因验证主脊的计算半段——噪声底落盘 + 切片长表 + 配对 z 检验，跑到现象清单为止
mode: compute
playbook: architecture-attribution
compute_stages: "0-0"
tools: [Bash, Read, Write]
model: sonnet
---

## 你是谁

一句话身份：只做「噪声底落盘、切片长表构建、切片配对 z 检验」的计算，不问用户、不下结论。

## 输入（主 agent 派发时给你）

- 工作目录：`<workdir>`
- 引擎目录：`<ENGINE>`（绝对路径，含 scripts/ playbooks/ chartbook/）
- 已答问题：noise-floor（"已有数值"时附 metric/config/seeds/per_seed；"需现算"时主 agent 已先派 worker 并把 `noise_floor.json` 落盘）
- 已就绪的上游产物目录：`setup=<path>`（规范长表 + alignment_report.json）；`model_profile=<path>` 可选
- 种子维度来源：用户给的 seed/run 映射或已有逐种子产物路径（没有就如实 BLOCKED）

## 步骤（去菜谱）

按 `playbooks/architecture-attribution/playbook.md` 的 Stage `0-0` 执行：噪声底落盘 →
池化对照 → 写 `analysis_scripts/build_slice_metrics.py` 出 `slice,seed,model_a,model_b` 长表并过
对账（行数守恒、(slice,seed) 唯一、抽 2 行核对）→
`python3 "<ENGINE>/scripts/slice_zcheck.py" --metrics slice_metrics.csv --out slice_zcheck.json` →
FINDINGS.md 现象清单（只写 real/~noise 与数字）。
用 `python3 "<ENGINE>/scripts/orient.py" --playbook architecture-attribution` 领阶段与 prereq；
现场脚本先过 `python3 "<ENGINE>/scripts/gen_gate.py" --script <path> --playbook architecture-attribution --stage 0`
（在 `<workdir>` 下运行；`<ENGINE>` = 主 agent 派发时填入的引擎绝对路径；golden 由脚本按 playbook 目录自动引用）。

## 红线

- 不问用户：noise-floor 未答、seed 维度不明 → NEED_INFO，不把 model 名臆当 seed。
- 不重训：噪声底"需现算"而 `noise_floor.json` 不在 → BLOCKED（blocked_reason 写"先派 architecture-attribution-worker task=noise-floor"）。
- 不下结论：止步于「现象」，禁机制语言；Stage 1–4 不在本卡范围。
- 单写者：只写 noise_floor.json / slice_metrics.csv / slice_zcheck.json / analysis_scripts/ / FINDINGS.md，不碰 hypothesis_ledger.json、intervention_plan.json、PROGRESS.md、diagnose_*.json。
- 禁再派 subagent。

## 输出契约

你的 final message **就是**下面这个 JSON：

```json
{
  "status": "COMPUTE_DONE | NEED_INFO | BLOCKED",
  "playbook": "architecture-attribution",
  "phenomena_file": "phenomena_architecture-attribution.json",
  "produces_dir": "",
  "artifacts": ["noise_floor.json", "slice_metrics.csv", "slice_zcheck.json", "FINDINGS.md"],
  "phenomena": ["≤30 行：每个 real 切片的 z/mean_diff/赢家；~noise 切片计数；池化差距 vs 噪声底"],
  "need_info": [{"question_id": "…", "ask": "…", "why": "…"}],
  "blocked_reason": ""
}
```

## 停顿/交回

跑到 Stage 0 终点（pause）即返回 `COMPUTE_DONE`；账本校验、干预设计、干预执行（worker）、
三道门与 CONCLUSION.md 由主 agent 接手。
````

- [ ] **Step 4: 写 worker 卡**

`ts-diagnose/agents/architecture-attribution-worker.md`:

````markdown
---
name: architecture-attribution-worker
description: 架构归因的重训工——一次只执行一条「改配置 + ≥3 种子重训 + 评估」任务，回一张 receipt
mode: worker
playbook: architecture-attribution
compute_stages: "scripts"
serves_stages: [0, 3]
tools: [Bash, Read, Write]
model: sonnet
---

## 你是谁

一句话身份：只做「按给定配置重训 ≥3 个种子并评估」的计算，不问用户、不下综合判定。

## 输入（主 agent 派发时给你）

- 任务类型 task：`noise-floor`（Stage 0 基线，仅改种子）或 `intervention`（Stage 3 单条干预）
- 工作目录：`<workdir>`
- 引擎目录：`<ENGINE>`（绝对路径，含 scripts/ playbooks/ chartbook/）
- 训练入口、experiment_config 路径、checkpoint 起点、种子集、口径（缺省 rmse_192）
- intervention 任务附：hypothesis_id / component / switch / kind / seeds / pred_direction /
  kill_criterion / confirm_criterion / noise_floor_3sigma / baseline_mean（同口径、同种子批）

## 步骤（去菜谱）

按 `playbooks/architecture-attribution/playbook.md` 的 Stage 0「第一步，噪声底」（task=noise-floor）
或 Stage 3「执行契约」（task=intervention）执行；逐条任务细则照
`playbooks/architecture-attribution/references/subagent-brief.md` 的 Brief A / Brief B 任务 1–5。
- noise-floor：每种子一行落 `baseline_seed_metrics.csv`（seed,metric）；算 mean、std(ddof=1)、noise_floor_3sigma = std×3。
- intervention：delta 逻辑写成 `analysis_scripts/eval_<hypothesis_id>.py`（带自检），记起止时刻，然后
  `python3 "<ENGINE>/scripts/ablation_verdict.py" --hypothesis-id <id> --switch=<switch> --delta <delta> --noise-floor <nf> --direction <pred_direction> --seeds <N> --script analysis_scripts/eval_<id>.py --t-start <ISO> --t-end <ISO> --selftest "<一句话>" --out receipts/<id>.json`
阶段与 prereq 由主 agent 掌握；本卡不跑 `python3 "<ENGINE>/scripts/orient.py"`（阶段状态单写者是主 agent）。

## 红线

- 单变量：intervention 只改一个 switch；数据、步数、其余超参与基线完全一致。
- 不读 checkpoint 权重、逐 iteration loss、训练日志进上下文——脚本内跑、脚本内落盘。
- 只写 `receipts/<hypothesis_id>.json`、`analysis_scripts/eval_<id>.py`、`baseline_seed_metrics.csv`；
  不碰 hypothesis_ledger.json / intervention_plan.json / PROGRESS.md / FINDINGS.md / diagnose_*.json。
- 不问用户：缺训练入口、config、种子 → NEED_INFO；某种子发散 → BLOCKED，带种子号与一句原因，不带日志。
- 不下「confirmed 支持整条因果结论」类综合判断；不再派 subagent；一次只做一条任务。

## 输出契约

你的 final message **就是**下面这个 JSON：

```json
{
  "status": "COMPUTE_DONE | NEED_INFO | BLOCKED",
  "task": "intervention",
  "hypothesis_id": "H3",
  "receipt_line": "- H3 confirmed: switch=--no-cross-attn delta=+0.412 noise_floor=0.1200 seeds=3",
  "receipt_file": "receipts/H3.json",
  "config_diff": ["--no-cross-attn"],
  "per_seed": [0.812, 0.799, 0.826],
  "mean": 0.812, "std": 0.0135, "noise_floor_3sigma": 0.0405,
  "instability_note": "",
  "need_info": [],
  "blocked_reason": ""
}
```
- noise-floor 任务：`hypothesis_id / receipt_line / receipt_file / config_diff` 留空，填 per_seed / mean / std / noise_floor_3sigma。

## 停顿/交回

一条任务跑完即返回；主 agent 用 ablation_verdict.py 独立复核、回填 intervention_plan.script、
更新账本 status 与 verdict_summary.json。
````

- [ ] **Step 5: `_agent-spec.md` 加 worker 行**

在 §1 三种 mode 表后追加一行：

```
| `worker` | 有 `subagent_ok:true` 的重训/评估型阶段，且这些阶段的工作单元是「一条配置 + ≥3 种子」 | 不整段交接；每次只执行主 agent 指派的一条任务，回一张 receipt | 每条任务即回 | `compute_stages` 固定 `"scripts"`；`serves_stages` 列出的 stage 必须 `subagent_ok:true`；输出契约含 `receipt_line`；文件名 `<playbook>-worker.md` 或 `<playbook>-baseline.md` |
```

- [ ] **Step 6: 守卫全绿**

Run: `cd ts-diagnose && python3 -m pytest scripts/tests/test_cards.py -q`
Expected: `13 passed`

- [ ] **Step 7: 提交**

```bash
git add ts-diagnose/agents ts-diagnose/scripts/tests/test_cards.py
git commit -m "feat(ts-diagnose): architecture-attribution 两张卡（compute Stage 0 + worker 噪声底/单条干预）+ worker 模式守卫

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01AKCjyuiAiWvtupjpTfi59f"
```

---

### Task 4: 派发规则改为卡片（engine-core / subagent-briefs / batch-orchestration / orient 措辞）

**Files:**
- Modify: `ts-diagnose/references/engine-core.md`（「subagent 编排」两段 + 「假设验证循环」的外包段 + 「常见错误」两行）
- Rewrite: `ts-diagnose/references/subagent-briefs.md`
- Modify: `ts-diagnose/references/batch-orchestration.md`（删 `## Brief-BATCH-COMPUTE` 节，Phase C 改卡片）
- Modify: `ts-diagnose/scripts/orient.py`（🤝 横幅措辞）
- Test: `ts-diagnose/scripts/tests/test_dispatch_docs.py`（新建）；受影响的既有断言按 grep 更新

**Interfaces:**
- Produces: 派发规则三句话（卡片优先 / 回退 general-purpose / NEED_INFO 回环），后续 Phase 2 精简与 Phase 4 workflow 都引用它。

- [ ] **Step 1: 写失败测试**

`ts-diagnose/scripts/tests/test_dispatch_docs.py`:

```python
import glob, os
ENGINE_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
REF = os.path.join(ENGINE_DIR, "references")


def _read(name):
    return open(os.path.join(REF, name), encoding="utf-8").read()


def _card_names():
    return sorted(os.path.splitext(os.path.basename(p))[0]
                  for p in glob.glob(os.path.join(ENGINE_DIR, "agents", "*.md"))
                  if not os.path.basename(p).startswith("_"))


def test_engine_core_dispatches_by_card_name_with_fallback():
    t = _read("engine-core.md")
    assert "agents/" in t and "-compute" in t
    assert "general-purpose" in t, "须写明卡片未注册时的回退：卡片全文作 prompt 派 general-purpose"
    for stale in ("Brief-COMPUTE", "Brief-PRODUCER", "Brief-FACT"):
        assert stale not in t, f"engine-core 仍引用已删除的模板 {stale}"


def test_subagent_briefs_indexes_every_card():
    t = _read("subagent-briefs.md")
    for name in _card_names():
        assert name in t, f"subagent-briefs.md 卡片索引缺 {name}"
    assert "NEED_INFO" in t and "general-purpose" in t
    for stale in ("## Brief-COMPUTE", "## Brief-PRODUCER", "## Brief-FACT"):
        assert stale not in t


def test_batch_phase_c_uses_cards():
    t = _read("batch-orchestration.md")
    assert "Brief-BATCH-COMPUTE" not in t
    assert "-compute" in t
```

Run: `cd ts-diagnose && python3 -m pytest scripts/tests/test_dispatch_docs.py -q`
Expected: 3 failed。

- [ ] **Step 2: 改 engine-core「subagent 编排」两段**

把「执行模型」里以 `- **subagent 编排**：` 开头的一段和紧随其后的 `**分层原则**` 一段整体替换为：

```markdown
- **派发（卡片制）**：重活不现场拼 Brief，按名字派 `agents/` 里的预定义卡片。
  命中 playbook `X` → 派 `X-compute`：producer 卡（data-setup / metric-eval / model-audit）
  整体跑到产物落盘；compute 卡跑 Stage 0 到第一个 pause_after 为止；compute-fine
  （subset-influence）与 worker（architecture-attribution-worker）每次只做一条指派任务。
  派发前：按该 playbook `questions:` 问齐 `stage ≤` 区间终点的题，答案与已就绪的上游产物目录
  填进卡片「输入」节，`<ENGINE>`/`<workdir>` 填绝对路径；`upstream[]` required 产物缺 →
  先派对应 producer 卡（setup→data-setup-compute、model_profile→model-audit-compute、
  metric_table→metric-eval-compute）。卡片回 `NEED_INFO` → 主 agent 问用户、写 config、
  **重派同一张卡**；回 `BLOCKED` → 主 agent 修材料或脚本后重派，不换卡。
  **回退**：Agent 工具可用类型里没有该名字（非 Claude Code 宿主或未安装）→ 把
  `agents/<name>.md` 全文作为 prompt 派 `general-purpose`，PROGRESS.md 记一行「卡片未注册，
  走回退」。索引、回环细则与 Brief-EMBED 见 `subagent-briefs.md`。
  `diagnose_config / diagnose_state / PROGRESS / FINDINGS` 只由主 agent 写；卡片不得再派
  subagent；**结论永远由主 agent 落笔**。
```

- [ ] **Step 3: 改 engine-core「假设验证循环」的外包段**

把 `**subagent 外包（强制）**：` 一段里的「brief 模板见 `playbooks/architecture-attribution/references/subagent-brief.md`，不在此重复。」改为「派 `architecture-attribution-worker`（task=intervention），每条干预一次派发；噪声底需现算时同卡 task=noise-floor；细则见该 playbook 的 `references/subagent-brief.md`。」

- [ ] **Step 4: 改 engine-core「常见错误」**

把 `- ❌ 内联生产 upstream 产物时，没收齐它的 questions 答案就丢给 subagent（…按 \`Brief-PRODUCER\` 整体外包执行段）；` 一条里的 `按 \`Brief-PRODUCER\` 整体外包执行段` 改为 `派 producer 卡整体执行`。末尾追加两条：

```markdown
- ❌ 现场手拼 Brief 派 subagent，而 `agents/` 里已有对应卡片（卡片才有守卫过的红线与输出契约）。
- ❌ 卡片回 `NEED_INFO` 后主 agent 自己猜答案继续，或换一张卡顶替（必须问用户后重派同一张）。
```

- [ ] **Step 5: 重写 subagent-briefs.md**

整文件替换为：

```markdown
# 子 agent 派发（卡片制）

主 agent 只做编排：提问、派发、收契约 JSON、升级判定、反驳门、FINDINGS/CONCLUSION、
state/config 更新。重活按名字派 `agents/` 卡片；本文件是索引 + 回环规则。

## 卡片索引（playbook → 卡片 · mode · 覆盖）

| playbook | 卡片 | mode | 覆盖 |
|---|---|---|---|
| data-setup | `data-setup-compute` | producer | 全程到 setup 产物落盘 |
| metric-eval | `metric-eval-compute` | producer | 全程到 metric_table 落盘 |
| model-audit | `model-audit-compute` | producer | 全程到 model_profile 落盘 |
| training-sufficiency | `training-sufficiency-compute` | compute | Stage 0 到第一个 pause |
| robustness | `robustness-compute` | compute | 同上 |
| feature-importance | `feature-importance-compute` | compute | 同上；`on_demand_stages` 用户点名后再派 |
| model-comparison | `model-comparison-compute` | compute | 同上 |
| deployment-drift | `deployment-drift-compute` | compute | 同上 |
| fact-scan | `fact-scan-compute` | compute | 同上 |
| result-eval | `result-eval-compute` | compute | Stage 0–3；Stage 4 结论归主 agent，eval_report 产物在主 agent 收尾后才算 built |
| subset-influence | `subset-influence-compute` | compute-fine | 每次一个具名脚本 |
| architecture-attribution | `architecture-attribution-compute` | compute | Stage 0 |
| architecture-attribution | `architecture-attribution-worker` | worker | Stage 0 噪声底重训 / Stage 3 单条干预 |

每张卡的 frontmatter 是契约（name/mode/playbook/compute_stages/tools/model），正文六节：
你是谁 / 输入 / 步骤 / 红线 / 输出契约 / 停顿；规格见 `agents/_agent-spec.md`。

## 派发六步（单 playbook）

1. 读该 playbook frontmatter `questions:`，取 `stage ≤` 卡片区间终点的题，同阶段合并一次
   AskUserQuestion，答案落 `diagnose_config.json`。只取 `questions:`，不取 `evidence_lines`。
2. 按 `upstream[]` 保证 required 产物 built/linked：缺 → 先派对应 producer 卡（先问齐它自己的题）；
   optional 缺 → 三分支必须问用户，卡片不替用户拍板。
3. 把答案、上游目录、`<ENGINE>`、`<workdir>` 填进卡片「输入」节，按名字派发（`subagent_type` = 卡片名）。
   名字不可用 → 回退：卡片全文作 prompt 派 `general-purpose`，PROGRESS.md 记「卡片未注册，走回退」。
4. 收 final message（契约 JSON）：`NEED_INFO` → 问用户、写 config、重派同一张卡；`BLOCKED` →
   修材料/脚本后重派同一张卡。
5. `COMPUTE_DONE` → 只读 `phenomena_file`/`artifacts` 摘要，向用户停顿汇报现象清单，请用户点名深挖。
6. 主 agent 亲跑：变体解锁判定、结论三道门、`conclusion_gate.py`、CONCLUSION.md 直接呈现。

producer 目标：②③坍缩，问齐 → 整体派发 → 产物落盘即 `COMPUTE_DONE, produces_dir`，主 agent 写
`config.products.<id>` 回填与 PROGRESS 验证记录（这两样卡片无权写）。

## 派发纪律（全部卡片共用）

- 并行：互不共享输出文件的卡片可一条消息多派；GPU 任务单卡不分片。
- 单写者：`diagnose_config.json / diagnose_state.json / PROGRESS.md / FINDINGS.md` 只由主 agent 写。
- 分片防竞态：并发各写各的 `--out <name>.<shard>`，主 agent 收齐后合并。
- 上下文纪律：卡片只读结构化产物，不读 PNG / 逐行原始日志 / 大二进制。
- 无提问权：卡片没有 AskUserQuestion；缺信息走 `NEED_INFO`。
- 禁嵌套：卡片不得再派 subagent；要拆分由主 agent 派平级卡片。
- 回传要瘦：只回契约 JSON。

## Brief-EMBED 提示（嵌入运行其他技能）

playbook 需要先跑另一个技能建立上下文时，**由主 agent 亲自编排**：建独立子目录 → 照被嵌入技能的
SKILL.md 走到需要的阶段 → 回填本工作目录 config 的 `<workdir_key>` + `<status_key>="linked"` →
重跑 orient 确认。
```

- [ ] **Step 6: 改 batch-orchestration Phase C 与删模板节**

Run: `sed -n '34,70p' ts-diagnose/references/batch-orchestration.md`，然后：
- Phase C 节里「主 agent 现场拼 Brief-BATCH-COMPUTE 注入」类措辞改为「每个 worker = 该 playbook 的具名卡片 `<id>-compute`（索引见 `subagent-briefs.md`），「输入」节由主 agent 填 `_shared/` 产物目录与合并后的答案；名字不可用走回退」；
- 删除从 `## Brief-BATCH-COMPUTE` 标题起、到 `## 上下文预算` 标题前的整节。

- [ ] **Step 7: 改 orient 🤝 横幅**

`ts-diagnose/scripts/orient.py` 里四行 `print("  🤝 生产者 playbook：…")` 段改为：

```python
        print("  🤝 生产者 playbook：提问/用户裁决只在主 agent；questions 收齐后整体派")
        print(f"     卡片 agents/{fm['id']}-compute.md（名字不可用则卡片全文作 prompt 派")
        print("     general-purpose），产物落盘后主 agent 写 config.products 回填——")
        print("     主 agent 不要自己埋头执行。")
```

- [ ] **Step 8: 跑全量，修被文案变更打中的既有断言**

Run: `cd ts-diagnose && python3 -m pytest scripts/tests -q 2>&1 | tail -20`
Expected: `test_dispatch_docs.py` 3 项通过。若 `test_engine.py` / `test_products.py` 有断言 `Brief-PRODUCER` 字样失败，用 `grep -rn "Brief-PRODUCER\|Brief-COMPUTE" scripts/tests` 定位，把期望字符串改为 `-compute.md`（含义不变：横幅要求整体外包）。

- [ ] **Step 9: 提交**

```bash
git add ts-diagnose/references/engine-core.md ts-diagnose/references/subagent-briefs.md ts-diagnose/references/batch-orchestration.md ts-diagnose/scripts/orient.py ts-diagnose/scripts/tests/test_dispatch_docs.py ts-diagnose/scripts/tests
git commit -m "refactor(ts-diagnose): 派发层改卡片制——engine-core/subagent-briefs/batch Phase C 按名字派 agents/ 卡片，未注册回退 general-purpose

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01AKCjyuiAiWvtupjpTfi59f"
```

---

### Task 5: install.sh + INSTALL.md + 端到端测试

**Files:**
- Create: `ts-diagnose/install.sh`
- Create: `ts-diagnose/INSTALL.md`
- Test: `ts-diagnose/scripts/tests/test_install_sh.py`

**Interfaces:**
- Produces: `install.sh [--check|--uninstall|--copy]`，环境变量 `CLAUDE_HOME`（缺省 `~/.claude`）。

- [ ] **Step 1: 写失败测试**

`ts-diagnose/scripts/tests/test_install_sh.py`:

```python
import glob, json, os, subprocess
ENGINE_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
SH = os.path.join(ENGINE_DIR, "install.sh")


def _run(args, home):
    return subprocess.run(["bash", SH, *args], env={**os.environ, "CLAUDE_HOME": str(home)},
                          capture_output=True, text=True)


def _cards():
    return sorted(os.path.basename(p) for pat in ("*-compute.md", "*-worker.md", "*-baseline.md")
                  for p in glob.glob(os.path.join(ENGINE_DIR, "agents", pat)))


def test_install_links_everything_then_check_passes(tmp_path):
    home = tmp_path / "claude"
    r = _run([], home)
    assert r.returncode == 0, r.stderr
    assert os.path.realpath(home / "skills" / "ts-diagnose") == os.path.realpath(ENGINE_DIR)
    for c in _cards():
        assert os.path.islink(home / "agents" / c), c
    settings = json.loads((home / "settings.json").read_text(encoding="utf-8"))
    assert {"PostToolUse", "Stop", "UserPromptSubmit"} <= set(settings["hooks"])
    assert not (home / "skills" / "ts-diagnose-v2").exists()
    r = _run(["--check"], home)
    assert r.returncode == 0, r.stdout + r.stderr
    assert "ALL OK" in r.stdout


def test_install_is_idempotent_and_uninstall_cleans(tmp_path):
    home = tmp_path / "claude"
    assert _run([], home).returncode == 0
    assert _run([], home).returncode == 0
    r = _run(["--uninstall"], home)
    assert r.returncode == 0, r.stderr
    assert not (home / "skills" / "ts-diagnose").exists()
    assert not list((home / "agents").glob("*.md"))
    settings = json.loads((home / "settings.json").read_text(encoding="utf-8"))
    assert not settings.get("hooks")


def test_copy_mode_copies_cards(tmp_path):
    home = tmp_path / "claude"
    assert _run(["--copy"], home).returncode == 0
    for c in _cards():
        p = home / "agents" / c
        assert p.is_file() and not p.is_symlink(), c
```

Run: `cd ts-diagnose && python3 -m pytest scripts/tests/test_install_sh.py -q`
Expected: 3 failed（`install.sh` 不存在）。

- [ ] **Step 2: 写 install.sh**

```bash
#!/usr/bin/env bash
# ts-diagnose 安装：把包内文件链接进 Claude Code 目录并合并钩子。
#   bash install.sh              安装/刷新（幂等）
#   bash install.sh --check      只校验
#   bash install.sh --uninstall  卸载
#   bash install.sh --copy       agents/workflows 用复制而非 symlink
# 环境变量 CLAUDE_HOME 覆盖 ~/.claude（测试用）。
set -euo pipefail
PKG="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
CLAUDE="${CLAUDE_HOME:-$HOME/.claude}"
MODE="install"; COPY=0
for a in "$@"; do
  case "$a" in
    --check) MODE=check ;;
    --uninstall) MODE=uninstall ;;
    --copy) COPY=1 ;;
    *) echo "unknown arg: $a" >&2; exit 2 ;;
  esac
done

# macOS 自带 bash 3.2：空数组展开在 set -u 下会报错，统一用 ${arr[@]+"${arr[@]}"} 写法。
cards=()
for f in "$PKG"/agents/*-compute.md "$PKG"/agents/*-worker.md "$PKG"/agents/*-baseline.md; do
  [ -e "$f" ] && cards+=("$f")
done
flows=()
for f in "$PKG"/workflows/*.js; do [ -e "$f" ] && flows+=("$f"); done

place() {  # place <src> <dst>
  if [ "$COPY" = 1 ]; then rm -f "$2"; cp "$1" "$2"; else ln -sfn "$1" "$2"; fi
}

case "$MODE" in
  install)
    mkdir -p "$CLAUDE/skills" "$CLAUDE/agents" "$CLAUDE/workflows"
    ln -sfn "$PKG" "$CLAUDE/skills/ts-diagnose"
    rm -f "$CLAUDE/skills/ts-diagnose-v2"
    for f in ${cards[@]+"${cards[@]}"}; do place "$f" "$CLAUDE/agents/$(basename "$f")"; done
    for f in ${flows[@]+"${flows[@]}"}; do place "$f" "$CLAUDE/workflows/$(basename "$f")"; done
    python3 "$PKG/hooks/install_hooks.py" --settings "$CLAUDE/settings.json"
    echo "installed → $CLAUDE   (verify: bash \"$PKG/install.sh\" --check)"
    ;;
  uninstall)
    rm -f "$CLAUDE/skills/ts-diagnose"
    for f in ${cards[@]+"${cards[@]}"}; do rm -f "$CLAUDE/agents/$(basename "$f")"; done
    for f in ${flows[@]+"${flows[@]}"}; do rm -f "$CLAUDE/workflows/$(basename "$f")"; done
    python3 "$PKG/hooks/install_hooks.py" --settings "$CLAUDE/settings.json" --uninstall
    echo "uninstalled from $CLAUDE"
    ;;
  check)
    ok=1
    chk() { if [ -e "$1" ]; then echo "  ✓ $1"; else echo "  ✗ $1"; ok=0; fi; }
    echo "skill:";     chk "$CLAUDE/skills/ts-diagnose/SKILL.md"
    echo "agents:";    for f in ${cards[@]+"${cards[@]}"}; do chk "$CLAUDE/agents/$(basename "$f")"; done
    echo "workflows:"; for f in ${flows[@]+"${flows[@]}"}; do chk "$CLAUDE/workflows/$(basename "$f")"; done
    echo "hooks in $CLAUDE/settings.json:"
    for h in stage_probe.py gate_guard.py orient_reminder.py; do
      if grep -q "$h" "$CLAUDE/settings.json" 2>/dev/null; then echo "  ✓ $h"; else echo "  ✗ $h"; ok=0; fi
    done
    echo "selftests:"
    python3 "$PKG/hooks/gate_guard.py" --selftest >/dev/null 2>&1 && echo "  ✓ gate_guard" || { echo "  ✗ gate_guard"; ok=0; }
    python3 "$PKG/hooks/stage_probe.py" --selftest >/dev/null 2>&1 && echo "  ✓ stage_probe" || { echo "  ✗ stage_probe"; ok=0; }
    if [ "$ok" = 1 ]; then echo "ALL OK"; else echo "CHECK FAILED"; exit 1; fi
    ;;
esac
```

写完后：

Run: `chmod +x ts-diagnose/install.sh && bash -n ts-diagnose/install.sh`
Expected: 无输出（语法通过）。

- [ ] **Step 3: 跑测试确认通过**

Run: `cd ts-diagnose && python3 -m pytest scripts/tests/test_install_sh.py -q`
Expected: `3 passed`

- [ ] **Step 4: 写 INSTALL.md**

```markdown
# 安装 ts-diagnose（Claude Code）

## 前置

- python3 ≥ 3.9，`pip install -r <仓库根>/requirements.txt`（pyyaml、numpy 1.26.4、shap 0.44.1 等）
- Claude Code CLI 已登录

## 安装

    git clone <仓库> && cd <仓库>/ts-diagnose
    bash install.sh
    bash install.sh --check     # 期望最后一行 ALL OK

`install.sh` 做四件事：`~/.claude/skills/ts-diagnose` → 本目录；`~/.claude/agents/` 下逐张链接
`agents/*-compute.md` `*-worker.md`；`~/.claude/workflows/` 下链接 `workflows/*.js`（如有）；
把 `hooks/hooks.json` 三条钩子合并进 `~/.claude/settings.json`（幂等，可重复跑）。

Claude Code 若不跟随 agents 目录下的 symlink（新会话里 Agent 工具的可用类型没有
`model-comparison-compute`），改跑 `bash install.sh --copy`，以后每次更新包后重跑一次。

## 确认卡片已注册

开一个新的 `claude` 会话，让它列出可用 subagent 类型；应出现 13 个名字：
`data-setup-compute` `metric-eval-compute` `model-audit-compute` `training-sufficiency-compute`
`robustness-compute` `feature-importance-compute` `model-comparison-compute`
`deployment-drift-compute` `fact-scan-compute` `result-eval-compute` `subset-influence-compute`
`architecture-attribution-compute` `architecture-attribution-worker`。

## 钩子说明

| 事件 | 脚本 | 作用 |
|---|---|---|
| PostToolUse | `hooks/stage_probe.py` | 评测轨迹埋点；环境变量 `SKILL_EVOLVE_TRAJECTORY_AGENT` 未设时零行为 |
| Stop | `hooks/gate_guard.py` | 结论闸守卫：cwd 下有诊断在跑且 receipt 不合法时打回；连续 3 次后放行 |
| UserPromptSubmit | `hooks/orient_reminder.py` | 每回合注入「先跑 orient」提醒 |

工程会话里不想被 Stop 钩子打回：`python3 hooks/install_hooks.py --uninstall`，用完 `bash install.sh` 装回。

## 卸载

    bash install.sh --uninstall

## 附录：非 Claude Code 宿主（自研 SDK / DeepSeek）

- 只需 `SKILL.md` + `references/` + `playbooks/` + `scripts/` + `chartbook/` + `agents/`；钩子不装。
- 卡片按 `agents[name]` 查表加载：name = 文件名去 `.md`，frontmatter `tools/model` 是该 agent 的工具白名单与模型；
  正文整份作为 system prompt。宿主必须保证卡片没有向用户提问的工具。
- 派发时主 agent 把「输入」节的 `<ENGINE>`/`<workdir>` 替换为绝对路径，final message 按「输出契约」解析 JSON。
- 所有强制（入口闸 / 阶段闸 / 结论闸）都在 `scripts/` 的 Python 里，与宿主无关。
```

- [ ] **Step 5: 本机真装一次并校验**

Run: `bash ts-diagnose/install.sh && bash ts-diagnose/install.sh --check | tail -3`
Expected: `ALL OK`。然后 `ls -la ~/.claude/agents | grep compute | wc -l` → 12，`grep -c gate_guard ~/.claude/settings.json` → 1。

- [ ] **Step 6: 提交**

```bash
git add ts-diagnose/install.sh ts-diagnose/INSTALL.md ts-diagnose/scripts/tests/test_install_sh.py
git commit -m "feat(ts-diagnose): install.sh（symlink 安装/--check/--uninstall/--copy）+ INSTALL.md

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01AKCjyuiAiWvtupjpTfi59f"
```

---

### Task 6: 退役 v2 + README/设置/CHANGELOG + 端到端验证

**Files:**
- Delete: `ts-diagnose-v2/`
- Modify: `.claude/settings.local.json`（删 `skillOverrides.ts-diagnose-v2`）
- Modify: `README.md`（表格行 + 安装一句）
- Modify: `ts-diagnose/CHANGELOG.md`
- Modify: `ts-diagnose/scripts/tests/test_routing.py`（`ALL_PLAYBOOK_IDS` 已含 12 个，不动）

- [ ] **Step 1: 确认 v2 独有内容已搬完**

Run: `diff <(ls ts-diagnose-v2/agents) <(ls ts-diagnose/agents) ; grep -c "NEED_INFO 回环" ts-diagnose/references/subagent-briefs.md`
Expected: diff 只显示 v1 多出的两张 architecture-attribution 卡；grep ≥ 1。

- [ ] **Step 2: 删除**

```bash
git rm -r -q ts-diagnose-v2
rm -rf ts-diagnose-v2
rm -f ~/.claude/skills/ts-diagnose-v2
python3 - <<'EOF'
import json,io
p='.claude/settings.local.json'; s=json.load(open(p,encoding='utf-8'))
s.get('skillOverrides',{}).pop('ts-diagnose-v2',None)
json.dump(s,open(p,'w',encoding='utf-8'),ensure_ascii=False,indent=2)
EOF
grep -rn "ts-diagnose-v2" README.md 结果分析Skill介绍.md ts-diagnose/*.md 2>/dev/null
```
Expected: 最后一条 grep 列出 README/介绍里残留的 v2 引用（若有）；下一步清掉。

- [ ] **Step 3: README 更新**

`README.md` 第 7 行的表格行：`11 个可插拔 playbook` 改 `12 个可插拔 playbook`，行末追加 `；13 张 agent 卡片（\`agents/\`）+ 三钩子（\`hooks/\`），\`ts-diagnose/INSTALL.md\` 一键装到任意 Claude Code 设备`。删掉所有提到 `ts-diagnose-v2` 的行/句。

- [ ] **Step 4: CHANGELOG 追加一行（首行）**

```
- 2026-09-06 | Phase 1 打包：agents/（v2 的 11 张卡移植 + architecture-attribution compute/worker 两张新卡 + worker 模式守卫）、hooks/ 迁入包内（根目录 symlink 保外部路径）+ hooks.json + install_hooks.py、install.sh/INSTALL.md、派发层改卡片制（engine-core/subagent-briefs/batch Phase C；未注册回退 general-purpose）、ts-diagnose-v2 删除 | 用户："divide ts-diagnose into different folders … so ts-diagnose will be a package include everything like agents, workflow I need for this task" + 拍板 Claude Code 宿主 / symlink 安装 / 删 v2 | v2 已落后 v1（12 playbook 文件、5 脚本有差异）；只有 SKILL.md 是 Claude Code 意义上的 skill，卡片与钩子在原生目录才有工具锁死/无提问权/Stop 拦截；回退规则让同一套卡片在非 CC 宿主可用
```

- [ ] **Step 5: 全量测试 + 四步弱模型冒烟复演**

Run: `cd ts-diagnose && python3 -m pytest scripts/tests chartbook/tests -q 2>&1 | tail -2`
Expected: 全绿（基线 + 4 + 13 + 3 + 3）。

冒烟（临时目录，复演 CHANGELOG 2026-07-24 四步）：
```bash
T=$(mktemp -d) && cd "$T" && E=<仓库根>/ts-diagnose
python3 "$E/scripts/orient.py" --playbook model-comparison | grep -c "BLOCKED: 材料盘点未完成"   # 期望 1
python3 "$E/scripts/orient.py" --playbook model-comparison | grep -c "^  Stage "                # 期望 0
```
Expected: `1` 与 `0`。

- [ ] **Step 6: 真派一张卡（手动，Claude Code 新会话）**

开新会话到 `<仓库根>`，让主 agent：「在临时目录用 `ts-diagnose/playbooks/data-setup/golden/` 的 wide.csv 与 manifest.json 里记录的答案，按 `references/subagent-briefs.md` 派发六步派 `data-setup-compute`」。
Expected: Agent 工具可用类型里出现 `data-setup-compute`；返回 JSON `status: COMPUTE_DONE` 且 `produces_dir` 下有 `setup_manifest.json`。若类型列表没有卡片名 → 改 `bash install.sh --copy` 重试，并把 INSTALL.md 「若不跟随 symlink」一段提到安装节首位。

- [ ] **Step 6b: 真触发一次 Stop 钩子与回合提醒（手动，同一新会话）**

在一个含 `diagnose_config.json`（playbook 绑定为 model-comparison、无 CONCLUSION.md）的临时目录里开 `claude`，发一条任意消息后让它结束回合。
Expected: 回合开头上下文里出现 `[ts-diagnose 诊断进行中] 本回合开工前先在 … 跑 orient`（orient_reminder 生效）；会话试图结束时被打回一次，文案含「缺 conclusion_gate receipt 或 CONCLUSION.md」（gate_guard 生效），最多打回 3 次后放行。若两者之一没出现：对照 Claude Code hooks 文档核对该脚本输出的 JSON 字段名（`hookSpecificOutput.additionalContext` / `decision: block`），改脚本后重跑 `bash install.sh --check`，并在 CHANGELOG 记一行。

- [ ] **Step 7: 提交**

```bash
git add -u ts-diagnose-v2
git add README.md ts-diagnose/CHANGELOG.md ts-diagnose/INSTALL.md
git commit -m "chore(ts-diagnose): 退役 ts-diagnose-v2（卡片已移植 v1）+ README/CHANGELOG Phase 1 收口

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01AKCjyuiAiWvtupjpTfi59f"
```

---

# Phase 2：逐回合负载缩短（内容不删，只改出现时机）

### Task 7: `recipe_sections()` + 每阶段恰好一节守卫

**Files:**
- Modify: `ts-diagnose/scripts/engine_common.py`（末尾新增函数）
- Test: `ts-diagnose/scripts/tests/test_recipe_sections.py`

**Interfaces:**
- Produces: `engine_common.recipe_sections(playbook_path) -> dict[int, str]`；标题 `### Stage N` 或 `### Stage N–M`（`–`/`-`/`~`/`/` 四种分隔）；同一 id 出现两个标题抛 `ValueError`。

- [ ] **Step 1: 写失败测试**

`ts-diagnose/scripts/tests/test_recipe_sections.py`:

```python
import glob, os, sys, tempfile
import pytest
SCRIPTS_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, SCRIPTS_DIR)
import engine_common as ec  # noqa: E402
ENGINE_DIR = os.path.dirname(SCRIPTS_DIR)
PLAYBOOKS = sorted(glob.glob(os.path.join(ENGINE_DIR, "playbooks", "*", "playbook.md")))


@pytest.mark.parametrize("path", PLAYBOOKS, ids=lambda p: p.split(os.sep)[-2])
def test_every_stage_maps_to_exactly_one_section(path):
    fm = ec.load_frontmatter(path)
    secs = ec.recipe_sections(path)
    for st in fm["stages"]:
        assert st["id"] in secs, f"Stage {st['id']} 无 '### Stage {st['id']}' 小节"
        assert secs[st["id"]].startswith("### Stage")
        assert len(secs[st["id"]]) > 80, f"Stage {st['id']} 小节过短"


def _write(text):
    d = tempfile.mkdtemp()
    p = os.path.join(d, "playbook.md")
    open(p, "w", encoding="utf-8").write(text)
    return p


FM = "---\nid: x\nname: x\ngoal: g\nstages:\n  - id: 0\n    name: a\n    done_when: {manual: true}\n---\n"


def test_range_heading_maps_each_id_and_stops_at_next_heading():
    p = _write(FM + "\n## 2. 逐阶段菜谱\n\n### Stage 0 甲\n步骤甲\n\n### Stage 1–2 乙\n步骤乙\n\n## 3. 停顿\n别算进去\n")
    secs = ec.recipe_sections(p)
    assert set(secs) == {0, 1, 2}
    assert secs[1] == secs[2] and "步骤乙" in secs[1] and "别算进去" not in secs[1]
    assert "步骤甲" in secs[0] and "步骤乙" not in secs[0]


def test_duplicate_stage_heading_raises():
    p = _write(FM + "\n### Stage 0 甲\nx\n\n### Stage 0 又来\ny\n")
    with pytest.raises(ValueError):
        ec.recipe_sections(p)
```

Run: `cd ts-diagnose && python3 -m pytest scripts/tests/test_recipe_sections.py -q`
Expected: 全部失败，`AttributeError: module 'engine_common' has no attribute 'recipe_sections'`。

- [ ] **Step 2: 实现**

`engine_common.py` 末尾追加：

```python
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
```
（文件顶部若无 `import re`，补上。）

- [ ] **Step 3: 跑测试，处理 feature-importance 的标题形态**

Run: `cd ts-diagnose && python3 -m pytest scripts/tests/test_recipe_sections.py -q 2>&1 | tail -8`
Expected: 合成用例通过；若 `feature-importance` 失败（7 个 stage 只有 5 个 `### Stage` 标题），执行
`grep -n '^### ' playbooks/feature-importance/playbook.md` 看缺哪些 id：标题若写成 `### Stage 5/6 …` 或 `### Stage 5 与 6` 之类，**只改标题**为 `### Stage 5–6 …`（正文一字不动）；若两个阶段确实共用一节但标题只写了一个 id，同样把标题改成范围写法。其他 playbook 同法。改完重跑，期望全绿。

- [ ] **Step 4: 提交**

```bash
git add ts-diagnose/scripts/engine_common.py ts-diagnose/scripts/tests/test_recipe_sections.py ts-diagnose/playbooks
git commit -m "feat(ts-diagnose): engine_common.recipe_sections()——按 '### Stage N[–M]' 抽取阶段菜谱 + 每阶段恰好一节守卫

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01AKCjyuiAiWvtupjpTfi59f"
```

---

### Task 8: orient 每回合打印当前阶段菜谱（`--no-recipe` / `--recipe N` / 首次示例提示）

**Files:**
- Modify: `ts-diagnose/scripts/orient.py`
- Test: `ts-diagnose/scripts/tests/test_orient_recipe.py`（新建）；`test_orient_goto.py` 补一条断言

**Interfaces:**
- Consumes: `ec.recipe_sections(path)`
- Produces: orient 输出新增块，固定标题行 `📖 本阶段菜谱（playbook.md §Stage N 原文；done：…）`；`--recipe N` 只打印该节并退出、不写 state/PROGRESS。

- [ ] **Step 1: 写失败测试**

`ts-diagnose/scripts/tests/test_orient_recipe.py`:

```python
import json, os, subprocess, sys
SCRIPTS_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ORIENT = os.path.join(SCRIPTS_DIR, "orient.py")


def _orient(workdir, *args):
    return subprocess.run([sys.executable, ORIENT, *args], cwd=workdir,
                          capture_output=True, text=True).stdout


def test_recipe_flag_prints_only_that_section_and_writes_no_state(tmp_path):
    (tmp_path / "diagnose_config.json").write_text(json.dumps({"playbook": "model-comparison"}), encoding="utf-8")
    out = _orient(tmp_path, "--recipe", "0")
    assert "### Stage 0 总差距事实" in out
    assert "gap_metrics.py" in out
    assert "### Stage 1" not in out
    assert not (tmp_path / "diagnose_state.json").exists()
    assert not (tmp_path / "PROGRESS.md").exists()


def test_recipe_flag_unknown_stage(tmp_path):
    (tmp_path / "diagnose_config.json").write_text(json.dumps({"playbook": "model-comparison"}), encoding="utf-8")
    out = _orient(tmp_path, "--recipe", "9")
    assert "无 Stage 9" in out
```

Run: `cd ts-diagnose && python3 -m pytest scripts/tests/test_orient_recipe.py -q`
Expected: 2 failed（`unrecognized arguments: --recipe`）。

- [ ] **Step 2: 加参数与 `--recipe` 早退**

`orient.py` `main()`：`ap.add_argument("--force", …)` 之后加

```python
    ap.add_argument("--no-recipe", action="store_true", help="不打印当前阶段菜谱原文")
    ap.add_argument("--recipe", type=int, default=None, metavar="N",
                     help="只打印 Stage N 的菜谱原文并退出（复核用，不写 state/PROGRESS）")
```

在 `fm = ec.load_frontmatter(ec.find_playbook(cfg["playbook"]))` 之后、`state = …` 之前插入：

```python
    if args.recipe is not None:
        secs = ec.recipe_sections(ec.find_playbook(cfg["playbook"]))
        if args.recipe not in secs:
            print(f"→ 无 Stage {args.recipe}（本 playbook 阶段：{sorted(secs)}）")
        else:
            print(secs[args.recipe])
        return
```

- [ ] **Step 3: 默认打印**

把 `print(f"→ 前置齐，可开工 Stage {target['id']}。")` 这一行改为：

```python
            print(f"→ 前置齐，可开工 Stage {target['id']}。")
            if not args.no_recipe:
                _print_recipe(fm, target)
```

并在 `main()` 之前新增：

```python
def _print_recipe(fm, stage):
    secs = ec.recipe_sections(ec.find_playbook(fm["id"]))
    text = secs.get(stage["id"])
    if not text:
        return
    done = (stage.get("done_when") or {})
    done_s = ", ".join(done.get("artifacts") or []) or ("manual" if done.get("manual") else "")
    if done.get("findings_marker"):
        done_s += f"；FINDINGS 含「{done['findings_marker']}」"
    print("-" * 62)
    print(f"📖 本阶段菜谱（playbook.md §Stage {stage['id']} 原文；done：{done_s}）——照此做，"
          "标【硬规则】的步骤不得合并或跳过；整份 playbook 只在需要跨阶段判断时再读：")
    print(text)
```

- [ ] **Step 4: 首次进入提示示例轨迹**

在 `print("-" * 62)` 后打印阶段列表之前（`for st in fm["stages"]:` 之前）加：

```python
    example = os.path.join(os.path.dirname(ec.find_playbook(fm["id"])), "EXAMPLE-RUN.md")
    if os.path.exists(example) and not any(ec.stage_done(st, ctx) for st in fm["stages"]):
        print(f"  📎 首次进入：示例轨迹 {example}（golden 数据的完整一遍，读一次即可）")
```

- [ ] **Step 5: 既有 goto 测试补默认打印断言**

Run: `grep -n "前置齐" ts-diagnose/scripts/tests/*.py | head`
在其中**一个**断言了 `"→ 前置齐，可开工"` 出现在 orient 输出的测试里，紧接着加：

```python
    assert "📖 本阶段菜谱" in out
    assert "### Stage" in out
```
（`out` 为该测试里 orient 的 stdout 变量名，按现场为准。）

- [ ] **Step 6: 全量测试**

Run: `cd ts-diagnose && python3 -m pytest scripts/tests -q 2>&1 | tail -3`
Expected: 全绿。若某个断言 orient 输出**完全相等**的测试因新增块失败，把该断言改为子串断言（新增块不改变既有行）。

- [ ] **Step 7: engine-core Step 0 加一句**

`engine-core.md`「Step 0」段的「orient 的输出就是你这一回合的行动清单」句后加：「前置齐时 orient 会把当前阶段的菜谱原文一并打印——按打印的做，不必整份读 playbook；`--recipe N` 可单独复核某阶段。」

- [ ] **Step 8: 提交**

```bash
git add ts-diagnose/scripts/orient.py ts-diagnose/scripts/tests/test_orient_recipe.py ts-diagnose/scripts/tests ts-diagnose/references/engine-core.md
git commit -m "feat(ts-diagnose): orient 前置齐时打印当前阶段菜谱原文（--no-recipe/--recipe N）+ 首次进入提示 EXAMPLE-RUN

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01AKCjyuiAiWvtupjpTfi59f"
```

---

### Task 9: engine-core.md 精简到判断规则 + token 预算守卫

**Files:**
- Rewrite: `ts-diagnose/references/engine-core.md`
- Test: `ts-diagnose/scripts/tests/test_engine_core_budget.py`（新建）；受影响断言按 grep 更新

**Interfaces:**
- Produces: engine-core 估算 token ≤ 4200（`test_layering.estimate_tokens` 同口径），标题集合固定：Step 0 / 三道闸 / 提问纪律 / 执行模型 / 派发 / 假设验证循环 / 结论纪律 / 常见错误 / 批量编排 / 运行后回顾。

- [ ] **Step 1: 量现值，写失败测试**

Run:
```bash
cd ts-diagnose && python3 -c "
import sys; sys.path.insert(0,'scripts/tests'); from test_layering import estimate_tokens
print(estimate_tokens(open('references/engine-core.md',encoding='utf-8').read()))"
```
Expected: 一个 > 4200 的数（记进 CHANGELOG）。

`ts-diagnose/scripts/tests/test_engine_core_budget.py`:

```python
import os
ENGINE_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
PATH = os.path.join(ENGINE_DIR, "references", "engine-core.md")
BUDGET = 4200
MUST_KEEP = ("恒问五类", "不许用假设填补不确定", "禁机制语言", "单写者", "subagent 无提问权",
             "对账两关", "chartbook 豁免", "预算阶梯", "常见错误", "运行后回顾", "general-purpose",
             "post-hoc", "只报排名", "现象 / 假设 / 已证实 / 被推翻")


def _estimate(text):
    cjk = sum(1 for ch in text if 0x2E80 <= ord(ch) <= 0x9FFF or 0xFF00 <= ord(ch) <= 0xFFEF)
    return cjk + (len(text) - cjk) / 4


def test_engine_core_within_budget():
    t = _estimate(open(PATH, encoding="utf-8").read())
    assert t <= BUDGET, f"engine-core 估算 {t:.0f} token > {BUDGET}——orient 已打印的内容改成一行指针"


def test_engine_core_keeps_judgment_rules():
    text = open(PATH, encoding="utf-8").read()
    missing = [k for k in MUST_KEEP if k not in text]
    assert not missing, f"精简不得删除判断规则：{missing}"
```

Run: `cd ts-diagnose && python3 -m pytest scripts/tests/test_engine_core_budget.py -q`
Expected: `test_engine_core_within_budget` FAIL，`keeps_judgment_rules` PASS。

- [ ] **Step 2: 重写 engine-core.md**

整文件替换为（保留全部判断规则；orient 已打印的只留指针）：

````markdown
# 引擎执行核心（engine-core）——命中 playbook 后必读

<!-- SKILL.md（Layer 0）只做路由；本文件只写领域无关、代码查不了的执行纪律。
     阶段/前置/闸/清单由 orient 与闸脚本打印和强制，这里不复述。 -->

## Step 0：Orient——每回合先跑

每个回合开工前先跑 orient；本阶段做完再跑一次核对。不凭记忆推进——真相以落盘产物为准。
前置齐时 orient 会打印**当前阶段菜谱原文**与该阶段清单（图表选择门 / 三道门）——照打印的做，
不必整份读 playbook；`--recipe N` 单独复核某阶段。

```bash
python3 "<ENGINE>/scripts/orient.py" [--playbook <id> | --profile <skill>/profile.yaml] [--goto N] [--recipe N]
```

- 发现 project-context 时 orient 列实验线：AskUserQuestion 问要不要预填；同意则把路径写
  `config.experiment_line`；运行中补齐的【待补】按仓库纪律写回实验线 json。
- orient 报「必需材料未就绪」→ 按 `intake.md` 盘点：一次多选 checklist（末尾「还有别的吗」）→
  逐项追问路径/格式/schema（y 列、时间列、id 列必须问清）→ 落 `config.materials`。
  用户明确说没有 = absent-confirmed；required 材料降级须用户再确认并写 degraded_ok。

**三道闸（脚本强制）**：入口闸（材料不齐 orient 只打追问清单）· 阶段闸（`--goto` 前置不齐默认拒绝，
`--force` 留痕；声明 `charts:` 的阶段 done 必含 INDEX.md）· 结论闸（`conclusion_gate.py` 通过生成的
receipt 是结论阶段唯一完成判据）。

## 提问纪律

**不许用假设填补不确定**（细则 `question-discipline.md`）：

1. orient 报 ✗ 的问题，在其 stage 开工前必须 AskUserQuestion；同阶段合并一次问，带 playbook 的 options。
2. **恒问五类**——任务用到且信息不明时必问：① schema/单位/口径；② 成功判据；③ 证据不足以升级
   （问「接受降级还是补证据」，列补证据成本）；④ 破坏性或昂贵操作；⑤ 多候选文件/版本。
3. 有 default 的可不问，但采用默认须在 PROGRESS.md 记「按默认」。
4. 答案落 `diagnose_config.json` 的 questions 块：`{"<qid>": {"answer","source":"user","date"}}`。
5. **subagent 无提问权**：停顿与提问只在主 agent。

## 执行模型

- 阶段由 playbook frontmatter 定义（`_playbook-spec.md`），orient 是通用求值器。菜谱是编号步骤时，
  逐条建 todo，做一步勾一步；标【硬规则】的步骤不得合并、不得跳过。
- **分析代码运行时生成**进 `analysis_scripts/`，每个脚本先过菜谱声明的验证步（对账/合成小样/
  植入回收），结果记 PROGRESS.md；无验证记录的脚本产出不可引用，crystallize 不快照。
  golden 覆盖的阶段先过 `gen_gate.py`，PASS 才碰真实数据；FAIL 改脚本不改期望。
- **chartbook 豁免**：chartbook 已覆盖的图**必须**直接调 `chartbook/scripts/chart_*.py`，禁止现场重写；
  唯一现场写的是薄适配器 `analysis_scripts/adapter.py`（样例 `chartbook/golden/example_adapter/`）。
- **对账两关适用一切整形脚本**（行数守恒 + 抽 3 个窗口逐值核对）：菜谱没预见的临时整形/换算脚本
  同样要过；菜谱没声明验证步 ≠ 免验证。转换口径记 PROGRESS.md。
- **图表选择门**：声明 `charts:` 的阶段画图前必停一次（orient 打印四步清单）。默认全勾可画图；
  用户删图不静默（PROGRESS 一行 + CONCLUSION 声明缺口）；画完 `build_index.py` 出 INDEX.md 再停顿。
  选择门 = 画前定范围；停顿点 = 画后定深挖；不可合并。
- **事实阶段 ⏸**：`pause_after` 的事实阶段产出「现象清单」（观察 + 数字 + 来源，**禁机制语言**），
  停下汇报，等用户点名再进结论阶段。用户模糊授权（「挑最强的」）时选**效应量最大且样本过功效阈值**
  的现象，并列取证据线多的；选了哪条、按什么判据记 PROGRESS.md。
- **上游产物**：orient 按 `upstream[]` 打印三分支操作（required 缺 → 立即内联生产不问用户；optional
  缺 → 问用户三选一）。linked/built 的产物核验 manifest 与 marker 才能消费；stale 时让用户二选一
  （重建 / `accept_stale=true` 且结论声明）。
- **派发（卡片制）**：重活按名字派 `agents/` 卡片——`X-compute`（producer 整体 / compute 到第一个
  pause / compute-fine 与 worker 逐任务）。派发前问齐区间内 `questions:`，填「输入」节的答案、上游目录、
  `<ENGINE>`/`<workdir>` 绝对路径；required 上游缺先派 producer 卡。`NEED_INFO` → 问用户、写 config、
  重派同一张；`BLOCKED` → 修后重派，不换卡。**回退**：Agent 可用类型无该名字 → 卡片全文作 prompt 派
  `general-purpose`，PROGRESS 记「卡片未注册，走回退」。索引与六步见 `subagent-briefs.md`。
  **单写者**：`diagnose_config / diagnose_state / PROGRESS / FINDINGS` 只由主 agent 写；卡片不再派 subagent；
  **结论永远由主 agent 落笔**。
- **上下文预算**：产物自足（json 自带数字与形状），判读读 json，不读 PNG、原始日志、大 parquet。

## 假设验证循环

生成器 playbook（吐 `hypothesis_ledger.json`，如 model-comparison）不下结论；结论由跨 playbook 循环
在出口产一次：① 生成器产账本停顿移交 → ② `architecture-attribution` 取判别力最高的假设做单变量
干预（每条干预派 `architecture-attribution-worker`，主 agent 只收 receipt）→ ③ refuted 且预算未耗 →
回生成器提修正假设，标 `provenance: post-hoc`（不许同一批数据既生成又确认）→ ④ confirmed /
预算耗尽 / 无新判别假设 → 收敛 → ⑤ 结论只在出口过 `conclusion_gate` 产一次（架构因果表述附
「## 消融证据」receipt）。**预算阶梯**：单轮干预 ~10 次训练，总轮数 ≤3。
无 `trainable_framework`（checkpoint/experiment_config absent-confirmed）→ 跳过验证主脊，结论标未经干预验证。

## 结论纪律（细则 `mechanisms.md`）

1. 三道门（orient 在结论阶段打印清单）：门 1 稳健性 · 门 2 假设登记先于看数 · 门 3 反驳门逐条排除，
   排不掉显式降级。写 CONCLUSION.md 前跑 `provenance.py`；写完直接呈现给用户，不只丢路径。
2. 多证据线：≥2 条 evidence_lines 按 `upgrade_rule` 一致才升「假设」；单证据线上限「现象」。
3. 功效诚实：单元数不足（默认 <10）**只报排名**与趋势，不报显著性。
4. FINDINGS.md 状态只用保留字：**现象 / 假设 / 已证实 / 被推翻**。
5. CONCLUSION.md 按 `conclusion-reporting.md` 写。

## 常见错误

- ❌ orient 报 ✗ 的必答题没问，靠「合理假设」开工（schema 猜错污染全部下游）。
- ❌ 生成脚本没过验证步就引用其产出（或 crystallize 快照了无验证记录的脚本）。
- ❌ 事实阶段写机制语言（「因为遗忘 / 因为 batch 小」）——解释只出现在结论阶段。
- ❌ 单证据线就下「某成员/某变量有害」的判定。
- ❌ 跨 series/模型把不可比量纲的数值 pool 在一起（只比排名）。
- ❌ subagent 写 state/PROGRESS/FINDINGS/config；两个 subagent 追加同一文件。
- ❌ 把 PNG、原始日志、大 parquet 读进上下文。
- ❌ 上游产物 absent 不走三分支就开跑；linked/built 不核验 manifest/marker 就消费。
- ❌ 任务命中已固化专用技能却用引擎从头问一遍。
- ❌ 运行中补齐的实验线【待补】忘了写回 project-context。
- ❌ 材料 unknown 当「大概有」处理：unknown 必须问，absent-confirmed 才许走用户确认过的降级。
- ❌ 内联生产上游产物时没收齐它的 questions 就派卡；跑完不写 manifest/marker/config 回填。
- ❌ 现场手拼 Brief 派 subagent，而 `agents/` 里已有卡片。
- ❌ 卡片回 `NEED_INFO` 后自己猜答案继续，或换一张卡顶替。
- ❌ 只跑一次 orient 后凭记忆连推多个阶段。

## 批量编排

同一份数据多条 playbook 一起诊断 → `python3 "<ENGINE>/scripts/batch.py" --select <ids> --workdir <dir>`，
照它报的 Phase 办；协议见 `batch-orchestration.md`（生产者一次、提问一次、卡片 fan-out、合并停顿、结论归主）。

## 运行后回顾（每次实跑收尾必做）

1. 哪条菜谱缺失或有歧义、哪个脚本被迫返工、哪个问题该预声明进 questions；
2. 菜谱问题改 `playbooks/<id>/playbook.md`；机制问题改 `scripts/`（跑 pytest）；漏问/提问疲劳调 questions 的 default/skip_if；
3. `CHANGELOG.md` 追加一行（日期 | 改了什么 | 触发反馈原文 | 为什么）；
4. 用户会复用 → 提议 crystallize（`crystallize.md`）。
````

- [ ] **Step 3: 跑预算测试**

Run: `cd ts-diagnose && python3 -m pytest scripts/tests/test_engine_core_budget.py -q`
Expected: `2 passed`。若 `within_budget` 仍失败，先把「常见错误」以外的段落再压（不删规则，删重复措辞），不许提高 BUDGET。

- [ ] **Step 4: 修被打中的既有断言**

Run: `cd ts-diagnose && python3 -m pytest scripts/tests -q 2>&1 | grep -E "FAILED|passed|failed"`
对每个失败：`grep -rn "<失败断言里的字符串>" scripts/tests` 定位，把期望字符串改为新文案中语义相同的句子（例如 `test_charts_decl.py` 若断言四步清单在 engine-core，改为断言在 `orient.py` 输出——四步清单已由 orient 打印）。禁止为通过测试把内容加回 engine-core。

- [ ] **Step 5: 提交**

```bash
git add ts-diagnose/references/engine-core.md ts-diagnose/scripts/tests
git commit -m "refactor(ts-diagnose): engine-core 精简到代码查不了的判断规则（orient 已打印的改指针）+ token 预算守卫 ≤4200

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01AKCjyuiAiWvtupjpTfi59f"
```

---

### Task 10: SKILL.md description 精简 + 路由测试调整 + Phase 2 收口

**Files:**
- Modify: `ts-diagnose/SKILL.md`（仅 frontmatter description）
- Modify: `ts-diagnose/scripts/tests/test_routing.py`
- Modify: `ts-diagnose/CHANGELOG.md`

- [ ] **Step 1: 先改测试（RED）**

`test_routing.py` 中 `test_engine_description_enumerates_all_playbooks` 整个函数替换为：

```python
def test_description_is_triggers_only_and_short():
    """description 只留触发短语：≤350 字符、不含 playbook id、不含括号枚举——skill 列表预算 = 上下文 1%，
    超出时最少使用的 skill 会被丢出列表；路由表在正文（test_skill_md_line_budget_and_full_playbook_coverage 守）。"""
    d = description_of(ENGINE_DIR).strip()
    assert len(d) <= 350, f"description {len(d)} 字符 > 350"
    leaked = [pid for pid in ALL_PLAYBOOK_IDS if pid in d]
    assert not leaked, f"description 不应枚举 playbook id：{leaked}"
```

Run: `cd ts-diagnose && python3 -m pytest scripts/tests/test_routing.py -q`
Expected: 新测试 FAIL（现 603 字符且含 id）。

- [ ] **Step 2: 改 description**

SKILL.md frontmatter 替换为：

```yaml
---
name: ts-diagnose
description: 泛化的时序/预测模型诊断与评估引擎。用户想知道：训练是否充分、batch 不足、loss 震荡收敛慢；结论或模型在扰动与分组切片下稳不稳；哪个输入变量对误差影响最大、反事实验证；为什么模型 A 比 B 好、模型对比归因；要消融实验验证模型组件；上线后是否退化、误差何时开始变大；只画标准分析图看现象不要结论；分析模型代码、生成模型档案；评估预测结果、算 RMSE 或指标表、月度时段归因；哪些训练条目拖累留出目标。命中后按本文件路由表转发。
---
```

- [ ] **Step 3: 跑路由与分层守卫**

Run: `cd ts-diagnose && python3 -m pytest scripts/tests/test_routing.py scripts/tests/test_layering.py -q`
Expected: 全绿（触发短语九条仍在；正文路由表仍枚举 12 个 id）。

- [ ] **Step 4: 记录缩短前后的每回合负载**

Run:
```bash
cd ts-diagnose && python3 - <<'EOF'
import sys, os, json, subprocess, tempfile
sys.path.insert(0, 'scripts/tests'); from test_layering import estimate_tokens as t
r = lambda p: open(p, encoding='utf-8').read()
print('SKILL.md', t(r('SKILL.md')))
print('engine-core', t(r('references/engine-core.md')))
print('model-comparison playbook (whole)', t(r('playbooks/model-comparison/playbook.md')))
d = tempfile.mkdtemp(); json.dump({"playbook": "model-comparison"}, open(os.path.join(d, 'diagnose_config.json'), 'w'))
out = subprocess.run([sys.executable, os.path.abspath('scripts/orient.py'), '--recipe', '0'], cwd=d, capture_output=True, text=True).stdout
print('orient --recipe 0 (Stage 0 only)', t(out))
EOF
```
Expected: 四个数；`--recipe 0` 的值应远小于整份 playbook。把四个数与 Task 9 Step 1 的旧值一起写进 CHANGELOG。

- [ ] **Step 5: CHANGELOG 首行追加**

```
- 2026-09-06 | Phase 2 缩短：orient 前置齐时打印当前阶段菜谱原文（recipe_sections + 每阶段恰好一节守卫）、engine-core <旧值>→<新值> token（只留代码查不了的判断规则，预算 ≤4200 守卫）、SKILL.md description 603→<新值> 字符只留触发短语（skill 列表预算 = 上下文 1%，最少使用者被丢） | 用户："my playbook is too long, will this affect the skill performance?" | 弱模型失效 = 拿着整份 playbook 与 6.7K 的散文只执行一支；07-24 三轮加固证明「打印到眼前」才绑定；内容一字不删，只改出现时机
```

- [ ] **Step 6: 全量 + 四步冒烟 + 提交**

Run: `cd ts-diagnose && python3 -m pytest scripts/tests chartbook/tests -q 2>&1 | tail -2`
Expected: 全绿。再复演 Task 6 Step 5 的两条冒烟命令，期望 `1` 与 `0`。

```bash
git add ts-diagnose/SKILL.md ts-diagnose/scripts/tests/test_routing.py ts-diagnose/CHANGELOG.md
git commit -m "refactor(ts-diagnose): SKILL.md description 只留触发短语（≤350 字符，不枚举 playbook id）+ Phase 2 收口

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01AKCjyuiAiWvtupjpTfi59f"
```

---

# 后续（本计划不含，各自另出计划）

**Phase 3 运行示例**（依赖 Task 3 的卡片格式与 Task 8 的首次提示）：
- `playbooks/{result-eval,model-comparison,feature-importance}/EXAMPLE-RUN.md`：临时目录用各自 `golden/` 走一遍，录 orient 输出 → 命令 → 产物 → 现象清单 → 停顿汇报，≤2K token，头部标「golden 数据，数字仅示例」；
- 每张卡「输出契约」下加一个填好的 JSON 示例（golden 数字），行预算 80 已留；
- 守卫：EXAMPLE-RUN.md 里出现的 `scripts/*.py` / `chart_*.py` 路径必须存在。

**Phase 4 workflows（仅 Claude Code）**（依赖 Task 3 的 worker 契约与 Task 4 的派发六步）：
- `workflows/ts-batch-compute.js`：`args={workdir, producers:[{id,inputs}], computes:[{id,inputs}]}`；Phase Producers 串行 `agent(填好的卡片输入, {agentType:`${id}-compute`, schema: CONTRACT})`；Phase Compute `parallel`；返回契约数组；`NEED_INFO` 由主 agent 问用户后 `resumeFromRunId` 重跑；
- `workflows/ts-ablation-loop.js`：`args={workdir, noise_floor_3sigma, baseline_mean, seeds, interventions:[…]}`；`parallel` 派 `architecture-attribution-worker`（task=intervention），返回 receipts；判定/账本/下一轮归主 agent；
- engine-core「批量编排」与 architecture-attribution §5 各加一句可调用的 workflow 名；SKILL.md 不提；
- 真跑需用户一句「run the workflow」（Workflow 工具 opt-in）。
