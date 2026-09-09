# ts-diagnose 改进环（auto-research）+ Phase 4 workflow 实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 给 ts-diagnose 加一条按轮批跑的改进环（候选 → ≥3 种子重训 → 与冠军比 → 留弃 → 实验日志 → 代码守停止规则 → 封存测试集只评一次 → 结论闸），并补上 Phase 4 的通用重训 workflow；第一条接入链 model-comparison → architecture-attribution → model-improve；用 lsf-mini Weather 数据做脚本驱动的冒烟验证。

**Architecture:** 环的执行层复用「改配置 + ≥3 种子重训 + receipt」的 worker 形态；判定层新增 `improve_verdict.py`（超冠军且守护切片不退化）；记忆层新增 `experiment_log.py`（日志 + 冠军 + 轮次 + 停止规则）；评估器契约 `evaluator.py` 把训练入口冻结成一条命令；引擎只加两样通用件（`{round}` 占位、`json:` DSL）让 orient 能按轮回到候选阶段并在收敛前拦住结论；新剧本 `model-improve` 是环的宿主；`workflows/ts-train-batch.js` 是一轮候选的并行派卡脚本，architecture-attribution 与 model-improve 共用。

**Tech Stack:** Python 3（标准库 + numpy，仅适配器用 torch）、pytest、Claude Code Workflow（JS）、lsf-mini（CPU 训练）。

**Spec:** `docs/superpowers/specs/2026-09-07-improve-loop-phase4-design.md`

## Global Constraints

- 工作区：从 `main`（bcab943）新建分支 `improve-loop-phase4`，在临时 worktree 里干活（主检出的 `短期分析/**` 有未提交改动，不许碰）。用 superpowers:using-git-worktrees。
- git 纪律：绝不 `git add -A`；只按显式路径 stage；永不 stage `短期分析/**`、`短期分析.zip`、`diagnose_config.json`、`PROGRESS.md`、`.orient_audit.jsonl`。每个 task 原子提交，提交信息末尾加 `Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>`。不 push、不合并到 main。
- 技能文件（playbook / references / agents / SKILL.md）写作风格：每句只许是指令或执行所需事实；不写术语表、动机、教训故事；自然句子，不缩略密写。
- 弱模型保障：只加不删——现有硬规则、红线、常见错误表一条不删；新规则要「打印到眼前」（进 playbook 菜谱或卡片），不只放散文。
- 预算守卫：`SKILL.md` ≤60 行且不得出现 `scripts/tests/test_layering.py::METHOD_VOCAB` 里的词（含 `Stage`、`done_when`、`pause_after`）；`references/engine-core.md` 估算 ≤4200 token（`scripts/tests/test_engine_core_budget.py`）；卡片正文非空行 ≤80、六节齐全、不复述菜谱（`test_cards.py`）。
- 单写者：`champion.json`、`experiment_log.jsonl`、`rounds/**`、`diagnose_state.json` 只由主 agent（经 `experiment_log.py`）写；worker 只写 `runs/<exp_id>/**` 与 `receipts/E*.json`。
- 封存：环内任何脚本不读 `sealed/`；`experiment_log.py append` 拒收键名含 `test`/`sealed` 的结果。
- 测试基线：`ts-diagnose/scripts/tests` 307 绿 + `ts-diagnose/chartbook/tests` 162 绿；每个 task 结束两套都必须全绿，只许增不许减。
- 冒烟验证不读 `eval-cases/holdout/HW1/`（Weather 上的冻结 holdout 案例）。
- 训练产物（`runs/**`、`*.npy`、`ckpt.pth`、`checkpoints/`、`results/`）一律 gitignore，只提交 json/jsonl/md/receipts。

## 文件地图

| 路径 | 动作 | 职责 |
|---|---|---|
| `ts-diagnose/scripts/engine_common.py` | 改 | `expand_round()`；check-DSL `json:` 前缀 |
| `ts-diagnose/scripts/orient.py` | 改 | state 保留 `round`；头行打印轮次 |
| `ts-diagnose/playbooks/_playbook-spec.md` | 改 | 记 `{round}` 与 `json:` |
| `ts-diagnose/scripts/tests/test_loop_dsl.py` | 新 | Task 1 测试 |
| `ts-diagnose/scripts/hypothesis_ledger.py` | 改 | kind / fix / untested / receipt |
| `ts-diagnose/scripts/tests/test_hypothesis_ledger.py` | 改 | 扩展测试 |
| `ts-diagnose/scripts/improve_verdict.py` | 新 | 改进判定 + receipt |
| `ts-diagnose/scripts/tests/test_improve_verdict.py` | 新 | |
| `ts-diagnose/scripts/evaluator.py` | 新 | 评估器契约校验 + 跑适配器 |
| `ts-diagnose/references/evaluator-contract.md` | 新 | 契约文档 |
| `ts-diagnose/playbooks/model-improve/golden/reference/fake_adapter.py` | 新 | 确定性假适配器 |
| `ts-diagnose/scripts/tests/test_evaluator.py` | 新 | |
| `ts-diagnose/scripts/experiment_log.py` | 新 | 日志 / 冠军 / 轮次 / 停止 / 封存终评 |
| `ts-diagnose/scripts/tests/test_experiment_log.py` | 新 | |
| `ts-diagnose/scripts/conclusion_gate.py` | 改 | 规则 7 |
| `ts-diagnose/scripts/tests/test_conclusion_gate.py` | 改 | 规则 7 正反例 |
| `ts-diagnose/playbooks/model-improve/playbook.md` | 新 | 环的宿主剧本 |
| `ts-diagnose/playbooks/model-improve/golden/{make_golden.py,manifest.json,fake_round.json,reference/improve_verdict_ref.py}` | 新 | 金标准 |
| `ts-diagnose/agents/model-improve-worker.md` | 新 | 重训工卡片 |
| `ts-diagnose/agents/architecture-attribution-worker.md` | 改 | 契约加 run_status / metrics_dirs |
| `ts-diagnose/playbooks/model-comparison/playbook.md` | 改 | Stage 2 登记 F 条目 |
| `ts-diagnose/playbooks/architecture-attribution/playbook.md` | 改 | §5 提 workflow |
| `ts-diagnose/SKILL.md`、`README.md`、`ts-diagnose/references/engine-core.md`、`ts-diagnose/CHANGELOG.md`、`ts-diagnose/INSTALL.md` | 改 | 路由 / 计数 / 改进环说明 |
| `ts-diagnose/scripts/tests/{test_routing.py,test_products.py}` | 改 | 新剧本进表 |
| `ts-diagnose/workflows/ts-train-batch.js` | 新 | 一轮候选并行派卡 |
| `ts-diagnose/scripts/tests/test_workflows.py` | 新 | |
| `eval-cases/adapters/lsf_mini_adapter.py` | 新 | lsf-mini 真适配器 |
| `ts-diagnose/scripts/tests/test_lsf_mini_adapter.py` | 新 | 集成测试（lsf-mini 缺席 skip） |
| `eval-cases/improve-smoke-weather/**` | 新 | 冒烟产物 |

---

### Task 0: 工作区与基线

**Files:** 无代码改动。

- [ ] **Step 1: 建 worktree 与分支**

```bash
cd "/Users/tqa946816/Documents/华为/光伏预测/结果分析skill"
git worktree add -b improve-loop-phase4 /private/tmp/improve-loop-phase4 main
cd /private/tmp/improve-loop-phase4
git log --oneline -1     # 期望 bcab943
```

- [ ] **Step 2: 跑基线测试**

```bash
cd /private/tmp/improve-loop-phase4/ts-diagnose
python3 -m pytest scripts/tests -q 2>&1 | tail -1      # 期望 307 passed
python3 -m pytest chartbook/tests -q 2>&1 | tail -1    # 期望 162 passed
```

- [ ] **Step 3: 记录基线到 ledger**（SDD 工作区 `progress.md`）：`baseline: scripts 307 / chartbook 162`。

---

### Task 1: 引擎加法——`{round}` 占位与 `json:` DSL

**Files:**
- Modify: `ts-diagnose/scripts/engine_common.py`（`stage_done`、`check`）
- Modify: `ts-diagnose/scripts/orient.py`（state 的 `round`、头行）
- Modify: `ts-diagnose/playbooks/_playbook-spec.md`（§stages、§2）
- Test: `ts-diagnose/scripts/tests/test_loop_dsl.py`

**Interfaces:**
- Produces: `ec.expand_round(s: str, ctx: dict) -> str`；DSL `json:<相对路径>:<点路径>`（文件缺失 / 解析失败 / 值为假 → False）；`diagnose_state.json.round: int`（缺省 1，orient 保留不覆盖）。

- [ ] **Step 1: 写失败测试**

`ts-diagnose/scripts/tests/test_loop_dsl.py`：

```python
"""改进环用的两个引擎加法：done_when.artifacts 的 {round} 占位 + check-DSL 的 json: 前缀。"""
import os
import subprocess
import sys

import pytest

SCRIPTS_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ORIENT = os.path.join(SCRIPTS_DIR, "orient.py")
sys.path.insert(0, SCRIPTS_DIR)
import engine_common as ec  # noqa: E402

PB = """---
id: loop-demo
name: 循环演示
goal: 测试 {round} 占位与 json: DSL
materials:
  required: []
stages:
  - id: 0
    name: 基线
    done_when: {artifacts: ['champion.json']}
  - id: 1
    name: 候选
    prereqs:
      - {desc: 基线已定, check: 'stage:0'}
    done_when: {artifacts: ['rounds/round_{round}/candidates.json']}
  - id: 2
    name: 结论
    prereqs:
      - {desc: 已收敛, check: 'json:champion.json:converged'}
    done_when: {artifacts: ['CONCLUSION.md', 'gate_reports/conclusion_gate.json']}
---
正文占位。
"""


@pytest.fixture
def wd(tmp_path, monkeypatch):
    pb = tmp_path / "pb" / "playbook.md"
    pb.parent.mkdir()
    pb.write_text(PB, encoding="utf-8")
    ec.dump_json({"playbook": str(pb), "materials": {}}, str(tmp_path / "diagnose_config.json"))
    monkeypatch.chdir(tmp_path)
    return tmp_path


def _ctx(state=None):
    fm = ec.load_frontmatter(ec.load_config()["playbook"])
    return fm, {"cfg": ec.load_config(), "fm": fm, "state": state or {}}


def test_expand_round_default_and_state():
    assert ec.expand_round("rounds/round_{round}/x.json", {"state": {}}) == "rounds/round_1/x.json"
    assert ec.expand_round("rounds/round_{round}/x.json", {"state": {"round": 3}}) == "rounds/round_3/x.json"
    assert ec.expand_round("plain.json", {"state": {"round": 3}}) == "plain.json"


def test_stage_done_uses_round_from_state(wd):
    (wd / "rounds" / "round_1").mkdir(parents=True)
    (wd / "rounds" / "round_1" / "candidates.json").write_text("{}", encoding="utf-8")
    fm, ctx1 = _ctx({"round": 1})
    _, ctx2 = _ctx({"round": 2})
    st1 = ec._stage_by_id(fm, 1)
    assert ec.stage_done(st1, ctx1) is True
    assert ec.stage_done(st1, ctx2) is False


def test_json_dsl_missing_falsy_truthy_and_malformed(wd):
    fm, ctx = _ctx({"round": 1})
    assert ec.check("json:champion.json:converged", ctx) is False          # 文件不存在
    ec.dump_json({"converged": False, "budget": {"used": 3}}, "champion.json")
    assert ec.check("json:champion.json:converged", ctx) is False          # 值为假
    assert ec.check("json:champion.json:budget.used", ctx) is True         # 嵌套点路径
    ec.dump_json({"converged": True}, "champion.json")
    assert ec.check("json:champion.json:converged", ctx) is True
    assert ec.check("not json:champion.json:converged", ctx) is False
    with pytest.raises(ValueError):
        ec.check("json:champion.json", ctx)                                # 缺点路径


def test_current_stage_reenters_after_round_bump_and_gate_opens_on_converged(wd):
    ec.dump_json({"converged": False}, "champion.json")
    (wd / "rounds" / "round_1").mkdir(parents=True)
    (wd / "rounds" / "round_1" / "candidates.json").write_text("{}", encoding="utf-8")
    fm, ctx = _ctx({"round": 1})
    assert ec.current_stage(fm, ctx)["id"] == 2
    assert ec.prereqs_ok(ec.prereqs_of(ec._stage_by_id(fm, 2), ctx)) is False
    _, ctx_r2 = _ctx({"round": 2})
    assert ec.current_stage(fm, ctx_r2)["id"] == 1                       # 新一轮回到候选阶段
    ec.dump_json({"converged": True}, "champion.json")
    assert ec.prereqs_ok(ec.prereqs_of(ec._stage_by_id(fm, 2), ctx)) is True


def test_orient_preserves_round_and_prints_it(wd):
    ec.dump_json({"converged": False}, "champion.json")
    ec.dump_json({"round": 2, "manual_done": []}, "diagnose_state.json")
    r = subprocess.run([sys.executable, ORIENT], cwd=str(wd), capture_output=True, text=True, timeout=60)
    assert r.returncode == 0, r.stderr
    assert "第 2 轮" in r.stdout
    assert (ec.read_json("diagnose_state.json") or {}).get("round") == 2
```

- [ ] **Step 2: 跑测试确认失败**

```bash
cd /private/tmp/improve-loop-phase4/ts-diagnose && python3 -m pytest scripts/tests/test_loop_dsl.py -q
```
期望：`AttributeError: module 'engine_common' has no attribute 'expand_round'` 等失败。

- [ ] **Step 3: 改 engine_common.py**

在 `stage_done` 前加：

```python
def expand_round(s, ctx):
    """`{round}` 占位 → state.round（缺省 1）。改进环用它让 Stage 1–3 的产物按轮分目录。"""
    if "{round}" not in s:
        return s
    rnd = ((ctx.get("state") or {}).get("round")) or 1
    return s.replace("{round}", str(rnd))
```

`stage_done` 里把 `arts = dw.get("artifacts") or []` 改为：

```python
    arts = [expand_round(a, ctx) for a in (dw.get("artifacts") or [])]
```

`check()` 里 `if expr.startswith("product:")` 之前插入：

```python
    if expr.startswith("json:"):
        body = expr[len("json:"):]
        if ":" not in body:
            raise ValueError(f"json: 表达式须写成 json:<文件路径>:<点路径>，实际 {expr!r}")
        path, dotted = body.rsplit(":", 1)
        doc = read_json(expand_round(path, ctx))
        return bool(_value_at(doc, dotted)) if isinstance(doc, dict) else False
```

- [ ] **Step 4: 改 orient.py**

两处 `new_state = {...}`（intake-blocked 分支与正常分支）各加一个键：

```python
            "round": int((state or {}).get("round") or 1),
```

`if blocked is not None: … else: …` 两个分支都结束之后（`ec.dump_json(new_state, ec.STATE_PATH)` 之前）加：

```python
    if any("{round}" in a for st in fm["stages"]
           for a in ((st.get("done_when") or {}).get("artifacts") or [])):
        print(f"  改进环：第 {new_state['round']} 轮（产物路径里的 {{round}} 占位按此展开）")
```

- [ ] **Step 5: 改 `_playbook-spec.md`**

§stages 的 `done_when` 说明后加一段：

```
`done_when.artifacts` 与 `prereqs.check` 里的 `json:` 路径可以写 `{round}` 占位，orient 用
`diagnose_state.json.round`（缺省 1）替换。按轮重复的阶段把产物放 `rounds/round_{round}/`，
`experiment_log.py new-round` 把 round 加一，这些阶段就自动回到未完成。
```

§2 check-DSL 表加一行：

```
| `json:<文件路径>:<点路径>` | 文件存在且该点路径的值为真（`false`/`null`/空 都算假）；路径可含 `{round}` |
```

- [ ] **Step 6: 跑测试确认通过 + 全量回归**

```bash
python3 -m pytest scripts/tests/test_loop_dsl.py -q                # 期望 5 passed
python3 -m pytest scripts/tests -q 2>&1 | tail -1                  # 期望 312 passed
```

- [ ] **Step 7: 提交**

```bash
cd /private/tmp/improve-loop-phase4
git add ts-diagnose/scripts/engine_common.py ts-diagnose/scripts/orient.py \
        ts-diagnose/playbooks/_playbook-spec.md ts-diagnose/scripts/tests/test_loop_dsl.py
git commit -m "feat(engine): done_when/json: 支持 {round} 占位 + check-DSL 新增 json: 前缀（改进环回到候选阶段与收敛门的机器判据）

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>"
```

---

### Task 2: 账本扩展——kind / fix / untested / receipt

**Files:**
- Modify: `ts-diagnose/scripts/hypothesis_ledger.py`
- Test: `ts-diagnose/scripts/tests/test_hypothesis_ledger.py`

**Interfaces:**
- Produces: `hl.KINDS = {"mechanism", "improvement"}`；`hl.FIX_REQUIRED = ["target_model", "config_diff", "predicted_gain", "guard_slices"]`；`hl.STATUSES` 含 `untested`；improvement 条目字段形如：

```json
{"id": "F1", "kind": "improvement", "derived_from": "H1",
 "claim": "关闭 TSMixer 通道混合能降低 val_mse", "component": "tsmixer.channel_mix",
 "falsifiable_pred": "关闭后 val_mse 下降超噪声底且 horizon:far 不退化",
 "fix": {"target_model": "TSMixer", "config_diff": {"tsmixer_no_channel_mix": true},
         "predicted_gain": "val_mse 下降 ≥ 噪声底 0.0154",
         "guard_slices": ["horizon:near", "horizon:mid", "horizon:far"]},
 "status": "pending", "provenance": "pre-registered", "kill_receipt": null, "receipt": null}
```

- [ ] **Step 1: 追加失败测试**（文件末尾）

```python
IMPROVE = {"id": "F1", "kind": "improvement", "derived_from": "H1",
           "claim": "关闭通道混合能降 val_mse", "component": "tsmixer.channel_mix",
           "falsifiable_pred": "关闭后 val_mse 下降超噪声底且 far 不退化",
           "fix": {"target_model": "TSMixer", "config_diff": {"tsmixer_no_channel_mix": True},
                   "predicted_gain": "val_mse 下降 ≥ 0.0154", "guard_slices": ["horizon:far"]},
           "status": "pending", "provenance": "pre-registered", "kill_receipt": None, "receipt": None}


def test_improvement_entry_valid():
    assert hl.validate_ledger({"slice_map": [], "hypotheses": [IMPROVE]}) == []


def test_kind_default_mechanism_and_illegal_kind_rejected():
    assert hl.validate_ledger(VALID) == []                      # 无 kind = mechanism
    h = dict(VALID["hypotheses"][0], kind="magic")
    assert any("kind" in e for e in hl.validate_ledger({"slice_map": [], "hypotheses": [h]}))


def test_improvement_requires_fix_fields():
    h = dict(IMPROVE, fix={"target_model": "TSMixer"})
    errs = hl.validate_ledger({"slice_map": [], "hypotheses": [h]})
    assert any("config_diff" in e for e in errs) and any("guard_slices" in e for e in errs)
    h2 = dict(IMPROVE); del h2["fix"]
    assert any("fix" in e for e in hl.validate_ledger({"slice_map": [], "hypotheses": [h2]}))
    h3 = dict(IMPROVE, fix=dict(IMPROVE["fix"], config_diff="--flag"))
    assert any("config_diff" in e for e in hl.validate_ledger({"slice_map": [], "hypotheses": [h3]}))


def test_untested_requires_reason():
    h = dict(IMPROVE, status="untested")
    assert any("untested_reason" in e for e in hl.validate_ledger({"slice_map": [], "hypotheses": [h]}))
    ok = dict(IMPROVE, status="untested", untested_reason="seed 1337 crash: NaN loss")
    assert hl.validate_ledger({"slice_map": [], "hypotheses": [ok]}) == []


def test_improvement_confirmed_requires_receipt():
    h = dict(IMPROVE, status="confirmed")
    assert any("receipt" in e for e in hl.validate_ledger({"slice_map": [], "hypotheses": [h]}))
    ok = dict(IMPROVE, status="confirmed", receipt="receipts/E003.json")
    assert hl.validate_ledger({"slice_map": [], "hypotheses": [ok]}) == []
```

- [ ] **Step 2: 跑测试确认失败**

```bash
python3 -m pytest scripts/tests/test_hypothesis_ledger.py -q     # 期望新增 5 项里至少 4 项失败
```

- [ ] **Step 3: 改 hypothesis_ledger.py**

常量区改为：

```python
REQUIRED = ["id", "claim", "component", "falsifiable_pred", "status", "provenance"]
STATUSES = {"pending", "confirmed", "refuted", "undecided", "untested"}
KINDS = {"mechanism", "improvement"}
FIX_REQUIRED = ["target_model", "config_diff", "predicted_gain", "guard_slices"]
```

`validate_ledger` 的 for 循环末尾（`post-hoc` 检查之后）追加：

```python
        kind = h.get("kind", "mechanism")
        if kind not in KINDS:
            errs.append(f"{hid}: kind 非法（{kind}），只许 mechanism / improvement")
        if kind == "improvement":
            fix = h.get("fix")
            if not isinstance(fix, dict):
                errs.append(f"{hid}: improvement 假设必须带 fix 对象")
            else:
                for k in FIX_REQUIRED:
                    if not fix.get(k):
                        errs.append(f"{hid}: fix 缺 {k}")
                if fix.get("config_diff") is not None and not isinstance(fix["config_diff"], dict):
                    errs.append(f"{hid}: fix.config_diff 须为 dict（键=knob 名）")
                if fix.get("guard_slices") is not None and not isinstance(fix["guard_slices"], list):
                    errs.append(f"{hid}: fix.guard_slices 须为 list")
            if h.get("status") == "confirmed" and not h.get("receipt"):
                errs.append(f"{hid}: improvement 假设升 confirmed 必须带 receipt（receipts/E*.json 路径）")
        if h.get("status") == "untested" and not h.get("untested_reason"):
            errs.append(f"{hid}: untested 必须带 untested_reason（crash/timeout 与一句原因）")
```

模块 docstring 改为：`"""假设账本校验：字段纪律 = component 必填 / 可否证 / provenance / 状态一致性；kind=improvement 条目另查 fix 四字段与 receipt。"""`

- [ ] **Step 4: 跑测试确认通过 + 回归**

```bash
python3 -m pytest scripts/tests/test_hypothesis_ledger.py -q     # 全绿
python3 -m pytest scripts/tests -q 2>&1 | tail -1                  # 317 passed
```

- [ ] **Step 5: 提交**

```bash
git add ts-diagnose/scripts/hypothesis_ledger.py ts-diagnose/scripts/tests/test_hypothesis_ledger.py
git commit -m "feat(ledger): 账本加 kind=improvement（fix 四字段）、untested 状态、confirmed 需 receipt

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>"
```

---

### Task 3: 改进判定 `improve_verdict.py`

**Files:**
- Create: `ts-diagnose/scripts/improve_verdict.py`
- Test: `ts-diagnose/scripts/tests/test_improve_verdict.py`

**Interfaces:**
- Produces: `guard_check(guards) -> {slice: {delta, noise_floor, regress}}`；`verdict(delta, noise_floor_3sigma, guard_regress) -> "keep"|"discard"|"undecided"`；`judge(exp_id, hypothesis_id, per_seed, champion_mean, noise_floor_3sigma, guards=None, higher_is_better=False) -> dict`（含 `line`）；`judge_round(obj) -> {"verdicts": {exp_id: judge(...)}}`；CLI 两种模式（见下）；receipt 行格式 `- E003 keep: hyp=F1 delta=-0.0123 noise_floor=0.0154 seeds=3 guard=ok`，匹配 `conclusion_gate.IMPROVE_RECEIPT_RE`（Task 7 定义 `(keep|discard|undecided).*delta.*seeds?=\d`）。
- Consumes: Task 4 的 `summary.json`（`per_seed`、`slices_per_seed`）与 Task 5 的 `champion.json`（`mean`、`noise_floor_3sigma`、`slices_mean`、`slices_noise_floor`）。

- [ ] **Step 1: 写失败测试**

```python
"""改进判定：四态 + 守护切片 + receipt 行格式 + CLI 两种模式。"""
import json
import os
import re
import subprocess
import sys

SCRIPTS_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, SCRIPTS_DIR)
import improve_verdict as iv  # noqa: E402

SCRIPT = os.path.join(SCRIPTS_DIR, "improve_verdict.py")
LINE_RE = re.compile(r"(keep|discard|undecided).*delta.*seeds?=\d")


def test_verdict_four_states():
    assert iv.verdict(-0.02, 0.006, False) == "keep"
    assert iv.verdict(-0.02, 0.006, True) == "discard"
    assert iv.verdict(0.02, 0.006, False) == "discard"
    assert iv.verdict(-0.002, 0.006, False) == "undecided"


def test_guard_check_regress_only_when_worse_beyond_floor():
    g = iv.guard_check({"far": {"per_seed": [0.30, 0.31, 0.29], "champion_mean": 0.26, "noise_floor": 0.006},
                        "near": {"per_seed": [0.10, 0.11, 0.09], "champion_mean": 0.12, "noise_floor": 0.006},
                        "mid": {"per_seed": [0.201, 0.199, 0.200], "champion_mean": 0.20, "noise_floor": 0.006}})
    assert g["far"]["regress"] is True
    assert g["near"]["regress"] is False      # 变好
    assert g["mid"]["regress"] is False       # 噪声内


def test_judge_line_and_fields():
    r = iv.judge("E003", "F1", [0.180, 0.181, 0.179], 0.200, 0.006)
    assert r["verdict"] == "keep" and abs(r["delta"] + 0.02) < 1e-9 and r["seeds"] == 3
    assert LINE_RE.search(r["line"]) and r["line"].startswith("- E003 keep: hyp=F1 ")
    r2 = iv.judge("E004", "F2", [0.178, 0.179, 0.180], 0.200, 0.006,
                  guards={"far": {"per_seed": [0.30, 0.31, 0.29], "champion_mean": 0.26, "noise_floor": 0.006}})
    assert r2["verdict"] == "discard" and "guard=regress:far" in r2["line"]


def test_higher_is_better_flips_sign():
    r = iv.judge("E005", None, [0.92, 0.93, 0.91], 0.90, 0.006, higher_is_better=True)
    assert r["verdict"] == "keep" and r["delta"] < 0


def test_judge_round_batch():
    obj = {"champion_mean": 0.200, "noise_floor_3sigma": 0.006,
           "candidates": [{"exp_id": "E001", "hypothesis_id": "F1", "per_seed": [0.180, 0.181, 0.179]},
                          {"exp_id": "E002", "hypothesis_id": "F2", "per_seed": [0.221, 0.220, 0.219]}]}
    v = iv.judge_round(obj)["verdicts"]
    assert v["E001"]["verdict"] == "keep" and v["E002"]["verdict"] == "discard"


def test_cli_summary_mode_writes_receipt_with_provenance(tmp_path):
    summary = {"per_seed": [0.180, 0.181, 0.179],
               "slices_per_seed": [{"far": 0.25}, {"far": 0.26}, {"far": 0.25}],
               "t_start": "2026-09-07T10:00:00", "t_end": "2026-09-07T10:03:00"}
    champ = {"mean": 0.200, "noise_floor_3sigma": 0.006,
             "slices_mean": {"far": 0.26}, "slices_noise_floor": {"far": 0.006}}
    (tmp_path / "summary.json").write_text(json.dumps(summary), encoding="utf-8")
    (tmp_path / "champion.json").write_text(json.dumps(champ), encoding="utf-8")
    adapter = tmp_path / "adapter.py"
    adapter.write_text("print('x')\n", encoding="utf-8")
    r = subprocess.run([sys.executable, SCRIPT, "--exp-id", "E003", "--hypothesis-id", "F1",
                        "--summary", "summary.json", "--champion", "champion.json", "--guard", "far",
                        "--config-diff", '{"tsmixer_no_channel_mix": true}', "--script", str(adapter),
                        "--selftest", "assert ok", "--out", "receipts/E003.json"],
                       cwd=str(tmp_path), capture_output=True, text=True)
    assert r.returncode == 0, r.stderr
    assert LINE_RE.search(r.stdout)
    rec = json.loads((tmp_path / "receipts" / "E003.json").read_text(encoding="utf-8"))[-1]
    for k in ("exp_id", "hypothesis_id", "config_diff", "per_seed", "mean", "std", "champion_mean",
              "delta", "noise_floor_3sigma", "seeds", "guard", "verdict", "line",
              "produced_by", "script_sha256", "t_start", "t_end", "script_selftest"):
        assert k in rec, k
    assert rec["verdict"] == "keep" and rec["script_sha256"] and rec["t_start"] == "2026-09-07T10:00:00"


def test_cli_refuses_fewer_than_three_seeds(tmp_path):
    (tmp_path / "summary.json").write_text(json.dumps({"per_seed": [0.18, 0.18], "slices_per_seed": [{}, {}]}), encoding="utf-8")
    (tmp_path / "champion.json").write_text(json.dumps({"mean": 0.2, "noise_floor_3sigma": 0.006, "slices_mean": {}, "slices_noise_floor": {}}), encoding="utf-8")
    r = subprocess.run([sys.executable, SCRIPT, "--exp-id", "E009", "--summary", "summary.json",
                        "--champion", "champion.json", "--out", "receipts/E009.json"],
                       cwd=str(tmp_path), capture_output=True, text=True)
    assert r.returncode != 0 and "种子" in (r.stdout + r.stderr)


def test_cli_round_mode(tmp_path):
    obj = {"champion_mean": 0.200, "noise_floor_3sigma": 0.006,
           "candidates": [{"exp_id": "E001", "hypothesis_id": "F1", "per_seed": [0.199, 0.198, 0.200]}]}
    (tmp_path / "round.json").write_text(json.dumps(obj), encoding="utf-8")
    r = subprocess.run([sys.executable, SCRIPT, "--round", "round.json", "--out", "verdicts.json"],
                       cwd=str(tmp_path), capture_output=True, text=True)
    assert r.returncode == 0, r.stderr
    out = json.loads((tmp_path / "verdicts.json").read_text(encoding="utf-8"))
    assert out["verdicts"]["E001"]["verdict"] == "undecided"
```

- [ ] **Step 2: 跑测试确认失败**（`ModuleNotFoundError: improve_verdict`）

- [ ] **Step 3: 写 `improve_verdict.py`**

```python
#!/usr/bin/env python3
"""改进判定：候选 vs 冠军。delta = mean(候选) − mean(冠军)，lower_is_better 时负=变好；
|delta| < 噪声底 3σ → undecided；变好且守护切片无退化 → keep；否则 discard。
守护退化 = 该切片 delta > 0 且 ≥ 该切片噪声底。
CLI summary 模式写 receipts/E<id>.json（追加数组；字段与 ablation_verdict 同族：判定 + 溯源块），
receipt 行格式匹配 conclusion_gate.IMPROVE_RECEIPT_RE。`--round` 模式批量判定（golden 闸用）。"""
from __future__ import annotations

import argparse
import hashlib
import json
import statistics
import sys


def guard_check(guards):
    """guards: {slice: {"per_seed": [...], "champion_mean": float, "noise_floor": float}}
    → {slice: {"delta", "noise_floor", "regress"}}。"""
    out = {}
    for s, g in (guards or {}).items():
        m = statistics.fmean([float(x) for x in g["per_seed"]])
        d = m - float(g["champion_mean"])
        nf = float(g["noise_floor"])
        out[s] = {"delta": d, "noise_floor": nf, "regress": bool(d > 0 and d >= nf)}
    return out


def verdict(delta, noise_floor_3sigma, guard_regress):
    if abs(delta) < noise_floor_3sigma:
        return "undecided"
    if delta < 0:
        return "discard" if guard_regress else "keep"
    return "discard"


def judge(exp_id, hypothesis_id, per_seed, champion_mean, noise_floor_3sigma,
          guards=None, higher_is_better=False):
    sign = -1.0 if higher_is_better else 1.0
    per = [sign * float(x) for x in per_seed]
    champ = sign * float(champion_mean)
    g_in = {}
    for s, g in (guards or {}).items():
        g_in[s] = {"per_seed": [sign * float(x) for x in g["per_seed"]],
                   "champion_mean": sign * float(g["champion_mean"]),
                   "noise_floor": float(g["noise_floor"])}
    mean = statistics.fmean(per)
    std = statistics.stdev(per) if len(per) > 1 else 0.0
    delta = mean - champ
    g = guard_check(g_in)
    regress = sorted(s for s, r in g.items() if r["regress"])
    v = verdict(delta, float(noise_floor_3sigma), bool(regress))
    line = (f"- {exp_id} {v}: hyp={hypothesis_id} delta={delta:+.4f} "
            f"noise_floor={float(noise_floor_3sigma):.4f} seeds={len(per)} "
            f"guard={('regress:' + ','.join(regress)) if regress else 'ok'}")
    return {"exp_id": exp_id, "hypothesis_id": hypothesis_id,
            "per_seed": [float(x) for x in per_seed], "mean": sign * mean, "std": std,
            "champion_mean": float(champion_mean), "delta": delta,
            "noise_floor_3sigma": float(noise_floor_3sigma), "seeds": len(per),
            "guard": g, "verdict": v, "line": line}


def judge_round(obj):
    """obj: {"champion_mean", "noise_floor_3sigma", "higher_is_better"?, "candidates": [{exp_id, hypothesis_id, per_seed, guards?}]}"""
    out = {}
    for c in obj["candidates"]:
        out[c["exp_id"]] = judge(c["exp_id"], c.get("hypothesis_id"), c["per_seed"],
                                 obj["champion_mean"], obj["noise_floor_3sigma"],
                                 guards=c.get("guards"), higher_is_better=bool(obj.get("higher_is_better")))
    return {"verdicts": out}


def _sha256(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:  # 路径写错必须当场炸，不许静默记空指纹
        for blk in iter(lambda: f.read(65536), b""):
            h.update(blk)
    return h.hexdigest()


def _guards_from(summary, champ, guard_ids):
    guards = {}
    for s in guard_ids:
        per = [float(sp[s]) for sp in summary.get("slices_per_seed") or [] if s in sp]
        if not per or s not in (champ.get("slices_mean") or {}):
            sys.exit(f"✗ 守护切片 {s} 在 summary.slices_per_seed 或 champion.slices_mean 里缺失")
        guards[s] = {"per_seed": per, "champion_mean": champ["slices_mean"][s],
                     "noise_floor": (champ.get("slices_noise_floor") or {}).get(s, 0.0)}
    return guards


def main():
    ap = argparse.ArgumentParser(description="改进判定：候选 vs 冠军 → keep/discard/undecided + receipt")
    ap.add_argument("--round", default=None, help="批量模式：{champion_mean, noise_floor_3sigma, candidates[]} 的 JSON")
    ap.add_argument("--exp-id", dest="exp_id")
    ap.add_argument("--hypothesis-id", dest="hypothesis_id", default=None)
    ap.add_argument("--summary", help="evaluator.py run-seeds 产的 summary.json")
    ap.add_argument("--champion", help="champion.json")
    ap.add_argument("--guard", default="", help="守护切片 id，逗号分隔")
    ap.add_argument("--config-diff", dest="config_diff", default="{}")
    ap.add_argument("--higher-is-better", dest="higher_is_better", action="store_true")
    ap.add_argument("--script", default=None, help="产出指标的适配器/eval 脚本（receipt 记 produced_by + sha256）")
    ap.add_argument("--t-start", dest="t_start", default=None)
    ap.add_argument("--t-end", dest="t_end", default=None)
    ap.add_argument("--selftest", default=None)
    ap.add_argument("--out", required=True)
    a = ap.parse_args()

    if a.round:
        obj = json.load(open(a.round, encoding="utf-8"))
        res = judge_round(obj)
        with open(a.out, "w", encoding="utf-8") as f:
            json.dump(res, f, ensure_ascii=False, indent=2)
        for v in res["verdicts"].values():
            print(v["line"])
        return

    if not (a.exp_id and a.summary and a.champion):
        sys.exit("✗ summary 模式须给 --exp-id --summary --champion")
    summary = json.load(open(a.summary, encoding="utf-8"))
    champ = json.load(open(a.champion, encoding="utf-8"))
    per = [float(x) for x in summary.get("per_seed") or []]
    if len(per) < 3:
        sys.exit(f"✗ 有效种子只有 {len(per)} 个（<3）——本候选记 untested，不判定")
    guard_ids = [s for s in a.guard.split(",") if s]
    r = judge(a.exp_id, a.hypothesis_id, per, champ["mean"], champ["noise_floor_3sigma"],
              guards=_guards_from(summary, champ, guard_ids), higher_is_better=a.higher_is_better)
    print(r["line"])
    r.update({"config_diff": json.loads(a.config_diff),
              "produced_by": a.script, "script_sha256": _sha256(a.script) if a.script else None,
              "t_start": a.t_start or summary.get("t_start"), "t_end": a.t_end or summary.get("t_end"),
              "script_selftest": a.selftest})
    import os
    os.makedirs(os.path.dirname(a.out) or ".", exist_ok=True)
    try:
        with open(a.out, encoding="utf-8") as f:
            receipts = json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        receipts = []
    receipts.append(r)
    with open(a.out, "w", encoding="utf-8") as f:
        json.dump(receipts, f, ensure_ascii=False, indent=2)


if __name__ == "__main__":
    main()
```

- [ ] **Step 4: 跑测试确认通过 + 回归**

```bash
python3 -m pytest scripts/tests/test_improve_verdict.py -q          # 8 passed
python3 -m pytest scripts/tests -q 2>&1 | tail -1                   # 325 passed
```

- [ ] **Step 5: 提交**

```bash
git add ts-diagnose/scripts/improve_verdict.py ts-diagnose/scripts/tests/test_improve_verdict.py
git commit -m "feat(scripts): improve_verdict.py——候选 vs 冠军三态判定 + 守护切片 + receipt（溯源块同 ablation_verdict）

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>"
```

---

### Task 4: 评估器契约 `evaluator.py` + 假适配器 + 契约文档

**Files:**
- Create: `ts-diagnose/scripts/evaluator.py`
- Create: `ts-diagnose/playbooks/model-improve/golden/reference/fake_adapter.py`
- Create: `ts-diagnose/references/evaluator-contract.md`
- Test: `ts-diagnose/scripts/tests/test_evaluator.py`

**Interfaces:**
- Produces: `evaluator.validate(ev) -> [errors]`；`evaluator.apply_diff(ev, diff) -> config`（未登记 knob → ValueError）；`evaluator.run_one(ev, config, seed, out_dir) -> metrics dict`；`evaluator.run_seeds(ev, diff, seeds, out_root) -> summary dict`（并写 `<out_root>/summary.json`）；CLI `validate` / `run` / `run-seeds`。`evaluator.json` 可选键 `kill_grace_s`（超时后再等几秒杀进程，缺省 60）。
- 适配器 CLI 契约：`python3 <adapter> --config <cfg.json> --seed <int> --out <dir> [--time-limit <s>]`；产 `<dir>/metrics.json`（`status/primary/metric_id/slices/t_start/t_end/config/error`）与 `<dir>/sealed/test_metrics.json`。
- `summary.json` 字段：`config_diff, config, seeds, per_seed, slices_per_seed, run_status, metrics_dirs, mean, std, metric_id, adapter, t_start, t_end`。Task 3 的 `improve_verdict.py --summary` 与 Task 5 的 `init --baseline` 都吃这个文件。

- [ ] **Step 1: 写假适配器**（golden 目录先建好，Task 8 再补 manifest）

`ts-diagnose/playbooks/model-improve/golden/reference/fake_adapter.py`：

```python
#!/usr/bin/env python3
"""确定性假适配器（评估器契约的参考实现，不训练，测试 / golden / dry-run 用）。
primary = 0.20 + 0.10*dropout − 0.03*[tsmixer_no_channel_mix] + 0.02*[learning_rate ≥ 2e-3] + 种子噪声(≤0.002)
slices：horizon:near = 0.8*primary；horizon:mid = primary；horizon:far = 1.3*primary + 0.05*[tsmixer_no_channel_mix]
（关掉通道混合整体变好但远端退化——用来测守护切片。）
config.crash=true → 退出码 2 且不写 metrics.json；config.sleep_s>0 → 先睡（测超时）。
sealed/test_metrics.json = primary×1.1（封存，环内不读）。"""
import argparse
import datetime as dt
import json
import os
import time


def compute(cfg, seed):
    p = (0.20 + 0.10 * float(cfg.get("dropout", 0.1))
         - (0.03 if cfg.get("tsmixer_no_channel_mix") else 0.0)
         + (0.02 if float(cfg.get("learning_rate", 1e-3)) >= 2e-3 else 0.0)
         + ((int(seed) * 7919) % 1000) / 1000 * 0.002)
    far = 1.3 * p + (0.05 if cfg.get("tsmixer_no_channel_mix") else 0.0)
    return p, {"horizon:near": 0.8 * p, "horizon:mid": p, "horizon:far": far}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--config", required=True)
    ap.add_argument("--seed", type=int, required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--time-limit", type=int, default=0)
    a = ap.parse_args()
    cfg = json.load(open(a.config, encoding="utf-8"))
    os.makedirs(a.out, exist_ok=True)
    t0 = dt.datetime.now().isoformat(timespec="seconds")
    if cfg.get("sleep_s"):
        time.sleep(float(cfg["sleep_s"]))
    if cfg.get("crash"):
        raise SystemExit(2)
    p, sl = compute(cfg, a.seed)
    os.makedirs(os.path.join(a.out, "sealed"), exist_ok=True)
    with open(os.path.join(a.out, "sealed", "test_metrics.json"), "w", encoding="utf-8") as f:
        json.dump({"test_primary": p * 1.1, "metric_id": "test_mse"}, f, indent=2)
    with open(os.path.join(a.out, "metrics.json"), "w", encoding="utf-8") as f:
        json.dump({"status": "ok", "primary": p, "metric_id": "val_mse", "slices": sl,
                   "t_start": t0, "t_end": dt.datetime.now().isoformat(timespec="seconds"),
                   "config": cfg, "error": None}, f, ensure_ascii=False, indent=2)


if __name__ == "__main__":
    main()
```

- [ ] **Step 2: 写失败测试**

`ts-diagnose/scripts/tests/test_evaluator.py`：

```python
"""评估器契约：校验 / 单种子 ok·crash·timeout·切片缺失 / 多种子 summary / 未登记 knob。"""
import json
import os
import subprocess
import sys

import pytest

SCRIPTS_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ENGINE_DIR = os.path.dirname(SCRIPTS_DIR)
FAKE = os.path.join(ENGINE_DIR, "playbooks", "model-improve", "golden", "reference", "fake_adapter.py")
sys.path.insert(0, SCRIPTS_DIR)
import evaluator as ev  # noqa: E402

SCRIPT = os.path.join(SCRIPTS_DIR, "evaluator.py")


def _ev(**over):
    d = {"adapter": FAKE,
         "base_config": {"model": "TSMixer", "dropout": 0.1, "learning_rate": 1e-3},
         "knobs": {"dropout": {"family": "training", "type": "float"},
                   "learning_rate": {"family": "training", "type": "float"},
                   "tsmixer_no_channel_mix": {"family": "architecture", "type": "flag"},
                   "crash": {"family": "training", "type": "flag"},
                   "sleep_s": {"family": "training", "type": "float"}},
         "metric": {"id": "val_mse", "direction": "lower_is_better"},
         "slices": ["horizon:near", "horizon:mid", "horizon:far"],
         "seeds": [7, 1337, 2021], "time_limit_s": 5, "kill_grace_s": 0}
    d.update(over)
    return d


def test_validate_catches_contract_errors(tmp_path):
    assert ev.validate(_ev()) == []
    errs = ev.validate(_ev(adapter=str(tmp_path / "nope.py"), seeds=[1, 2],
                           knobs={"x": {"family": "magic"}}, metric={"id": "m", "direction": "up"}))
    joined = " ".join(errs)
    for k in ("adapter", "seeds", "family", "direction"):
        assert k in joined, k


def test_apply_diff_rejects_unknown_knob():
    with pytest.raises(ValueError):
        ev.apply_diff(_ev(), {"n_heads": 1})
    assert ev.apply_diff(_ev(), {"dropout": 0.2})["dropout"] == 0.2


def test_run_one_ok_and_sealed_written(tmp_path):
    m = ev.run_one(_ev(), _ev()["base_config"], 7, str(tmp_path / "s7"))
    assert m["status"] == "ok" and abs(m["primary"] - 0.210866) < 1e-6
    assert set(m["slices"]) == {"horizon:near", "horizon:mid", "horizon:far"}
    assert (tmp_path / "s7" / "sealed" / "test_metrics.json").exists()


def test_run_one_crash_and_timeout_write_metrics(tmp_path):
    m = ev.run_one(_ev(), ev.apply_diff(_ev(), {"crash": True}), 7, str(tmp_path / "c"))
    assert m["status"] == "crash" and (tmp_path / "c" / "metrics.json").exists()
    m2 = ev.run_one(_ev(time_limit_s=1), ev.apply_diff(_ev(), {"sleep_s": 3}), 7, str(tmp_path / "t"))
    assert m2["status"] == "timeout"


def test_run_one_missing_slice_is_crash(tmp_path):
    m = ev.run_one(_ev(slices=["horizon:near", "horizon:bogus"]), _ev()["base_config"], 7, str(tmp_path / "b"))
    assert m["status"] == "crash" and "horizon:bogus" in (m.get("error") or "")


def test_run_seeds_summary(tmp_path):
    s = ev.run_seeds(_ev(), {"dropout": 0.05}, [7, 1337, 2021], str(tmp_path / "root"))
    assert s["run_status"] == ["ok", "ok", "ok"] and len(s["per_seed"]) == 3
    assert abs(s["mean"] - 0.205957) < 1e-5 and s["std"] > 0
    assert len(s["slices_per_seed"]) == 3 and s["metrics_dirs"][0].endswith("seed_7")
    doc = json.loads((tmp_path / "root" / "summary.json").read_text(encoding="utf-8"))
    assert doc["config_diff"] == {"dropout": 0.05} and doc["config"]["dropout"] == 0.05


def test_cli_validate_run_run_seeds(tmp_path):
    p = tmp_path / "evaluator.json"
    p.write_text(json.dumps(_ev()), encoding="utf-8")
    r = subprocess.run([sys.executable, SCRIPT, "validate", str(p)], capture_output=True, text=True)
    assert r.returncode == 0 and "合法" in r.stdout
    r = subprocess.run([sys.executable, SCRIPT, "run", "--evaluator", str(p), "--seed", "7",
                        "--out", str(tmp_path / "one")], capture_output=True, text=True)
    assert r.returncode == 0 and '"status": "ok"' in r.stdout
    r = subprocess.run([sys.executable, SCRIPT, "run-seeds", "--evaluator", str(p),
                        "--config-diff", '{"crash": true}', "--out-root", str(tmp_path / "bad")],
                       capture_output=True, text=True)
    assert r.returncode == 2 and (tmp_path / "bad" / "summary.json").exists()
    r = subprocess.run([sys.executable, SCRIPT, "run", "--evaluator", str(p), "--seed", "7",
                        "--config-diff", '{"n_heads": 1}', "--out", str(tmp_path / "x")],
                       capture_output=True, text=True)
    assert r.returncode == 1 and "未登记" in (r.stdout + r.stderr)
```

- [ ] **Step 3: 跑测试确认失败**（`ModuleNotFoundError: evaluator`）

- [ ] **Step 4: 写 `evaluator.py`**

```python
#!/usr/bin/env python3
"""评估器契约：evaluator.json 校验 + 按契约跑适配器（单种子 / 多种子）。
适配器 CLI：python3 <adapter> --config <cfg.json> --seed <int> --out <dir> [--time-limit <秒>]
产物：<out>/metrics.json = {"status":"ok|crash|timeout","primary":float|null,"metric_id":str,
      "slices":{id:float},"t_start","t_end","config":{...},"error":str|null}
      <out>/sealed/test_metrics.json 封存——环内任何脚本不读。
子命令：validate <evaluator.json>；run --evaluator … [--config-diff …] --seed N --out DIR；
run-seeds --evaluator … [--config-diff …] [--seeds a,b,c] --out-root DIR（产 summary.json）。"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import statistics
import subprocess
import sys

FAMILIES = ("architecture", "training", "features", "data")
DIRECTIONS = ("lower_is_better", "higher_is_better")


def _now():
    return dt.datetime.now().isoformat(timespec="seconds")


def validate(ev):
    errs = []
    if not isinstance(ev, dict):
        return ["evaluator.json 须为对象"]
    ad = ev.get("adapter")
    if not ad or not os.path.exists(ad):
        errs.append(f"adapter 不存在：{ad}")
    if not isinstance(ev.get("base_config"), dict) or not ev["base_config"]:
        errs.append("base_config 须为非空 dict")
    knobs = ev.get("knobs")
    if not isinstance(knobs, dict) or not knobs:
        errs.append("knobs 须为非空 dict")
    else:
        for k, v in knobs.items():
            if not isinstance(v, dict) or v.get("family") not in FAMILIES:
                errs.append(f"knob {k} 缺 family 或不在 {FAMILIES}")
    m = ev.get("metric") or {}
    if not m.get("id") or m.get("direction") not in DIRECTIONS:
        errs.append(f"metric 须含 id 与 direction ∈ {DIRECTIONS}")
    if not isinstance(ev.get("slices"), list) or not ev["slices"]:
        errs.append("slices 须为非空 list")
    seeds = ev.get("seeds")
    if not isinstance(seeds, list) or len(seeds) < 3 or not all(isinstance(s, int) for s in seeds):
        errs.append("seeds 须为 ≥3 个整数")
    tl = ev.get("time_limit_s")
    if not isinstance(tl, int) or tl <= 0:
        errs.append("time_limit_s 须为正整数")
    return errs


def apply_diff(ev, diff):
    unknown = [k for k in diff if k not in ev["knobs"]]
    if unknown:
        raise ValueError(f"config_diff 含未登记 knob：{unknown}（登记在 evaluator.json.knobs）")
    cfg = dict(ev["base_config"])
    cfg.update(diff)
    return cfg


def _write_metrics(out_dir, status, error, metric_id, t_start, config):
    m = {"status": status, "primary": None, "metric_id": metric_id, "slices": {},
         "t_start": t_start, "t_end": _now(), "config": config, "error": error}
    with open(os.path.join(out_dir, "metrics.json"), "w", encoding="utf-8") as f:
        json.dump(m, f, ensure_ascii=False, indent=2)
    return m


def run_one(ev, config, seed, out_dir):
    os.makedirs(out_dir, exist_ok=True)
    cfg_path = os.path.join(out_dir, "config.json")
    with open(cfg_path, "w", encoding="utf-8") as f:
        json.dump(config, f, ensure_ascii=False, indent=2)
    t_start = _now()
    tl = int(ev["time_limit_s"])
    mid = ev["metric"]["id"]
    cmd = [sys.executable, ev["adapter"], "--config", cfg_path, "--seed", str(seed),
           "--out", out_dir, "--time-limit", str(tl)]
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=tl + int(ev.get("kill_grace_s", 60)))
    except subprocess.TimeoutExpired:
        return _write_metrics(out_dir, "timeout", f"超过 time_limit_s={tl}", mid, t_start, config)
    mp = os.path.join(out_dir, "metrics.json")
    m = None
    if os.path.exists(mp):
        try:
            m = json.load(open(mp, encoding="utf-8"))
        except json.JSONDecodeError:
            m = None
    if not isinstance(m, dict) or m.get("status") not in ("ok", "crash", "timeout"):
        tail = (r.stderr or r.stdout or "")[-2000:]
        return _write_metrics(out_dir, "crash", tail or f"退出码 {r.returncode}，无合法 metrics.json", mid, t_start, config)
    if m["status"] == "ok":
        missing = [s for s in ev["slices"] if s not in (m.get("slices") or {})]
        if not isinstance(m.get("primary"), (int, float)) or missing:
            return _write_metrics(out_dir, "crash", f"metrics.json 缺 primary 或切片 {missing}", mid, t_start, config)
    return m


def run_seeds(ev, diff, seeds, out_root):
    config = apply_diff(ev, diff)
    per, slices, status, dirs = [], [], [], []
    t_start = _now()
    for s in seeds:
        d = os.path.join(out_root, f"seed_{s}")
        m = run_one(ev, config, s, d)
        status.append(m["status"])
        dirs.append(d)
        if m["status"] == "ok":
            per.append(float(m["primary"]))
            slices.append({k: float(v) for k, v in m["slices"].items()})
    summary = {"config_diff": diff, "config": config, "seeds": list(seeds), "per_seed": per,
               "slices_per_seed": slices, "run_status": status, "metrics_dirs": dirs,
               "mean": statistics.fmean(per) if per else None,
               "std": statistics.stdev(per) if len(per) > 1 else None,
               "metric_id": ev["metric"]["id"], "adapter": ev["adapter"],
               "t_start": t_start, "t_end": _now()}
    os.makedirs(out_root, exist_ok=True)
    with open(os.path.join(out_root, "summary.json"), "w", encoding="utf-8") as f:
        json.dump(summary, f, ensure_ascii=False, indent=2)
    return summary


def main():
    ap = argparse.ArgumentParser(description="评估器契约：校验 evaluator.json / 跑适配器")
    sub = ap.add_subparsers(dest="cmd", required=True)
    v = sub.add_parser("validate")
    v.add_argument("evaluator")
    r = sub.add_parser("run")
    r.add_argument("--evaluator", required=True)
    r.add_argument("--config-diff", dest="config_diff", default="{}")
    r.add_argument("--seed", type=int, required=True)
    r.add_argument("--out", required=True)
    rs = sub.add_parser("run-seeds")
    rs.add_argument("--evaluator", required=True)
    rs.add_argument("--config-diff", dest="config_diff", default="{}")
    rs.add_argument("--seeds", default=None, help="逗号分隔；缺省用 evaluator.json.seeds")
    rs.add_argument("--out-root", dest="out_root", required=True)
    a = ap.parse_args()
    ev = json.load(open(a.evaluator, encoding="utf-8"))
    errs = validate(ev)
    if errs:
        print("\n".join("✗ " + e for e in errs))
        sys.exit(1)
    if a.cmd == "validate":
        print("✓ evaluator.json 合法")
        return
    diff = json.loads(a.config_diff)
    try:
        config = apply_diff(ev, diff)
    except ValueError as e:
        print(f"✗ {e}")
        sys.exit(1)
    if a.cmd == "run":
        m = run_one(ev, config, a.seed, a.out)
        print(json.dumps({"status": m["status"], "primary": m.get("primary"), "out": a.out}, ensure_ascii=False))
        sys.exit(0 if m["status"] == "ok" else 2)
    seeds = [int(s) for s in a.seeds.split(",")] if a.seeds else list(ev["seeds"])
    s = run_seeds(ev, diff, seeds, a.out_root)
    print(json.dumps({"run_status": s["run_status"], "mean": s["mean"], "std": s["std"],
                      "summary": os.path.join(a.out_root, "summary.json")}, ensure_ascii=False))
    sys.exit(0 if all(x == "ok" for x in s["run_status"]) else 2)


if __name__ == "__main__":
    main()
```

- [ ] **Step 5: 写契约文档** `ts-diagnose/references/evaluator-contract.md`

```markdown
# 评估器契约（改进环的训练入口）

工作目录放 `evaluator.json`，主 agent 在 model-improve Stage 0 按用户答案写；写完先跑
`python3 "<ENGINE>/scripts/evaluator.py" validate evaluator.json`。

字段：`adapter`（适配器脚本绝对路径）、`base_config`（冠军起点的全量配置）、`knobs`（每个可改
配置项 → `{"family": architecture|training|features|data, "type": flag|int|float|str}`；`config_diff`
只许改这里登记过的键）、`metric`（`{"id", "direction": lower_is_better|higher_is_better}`）、
`slices`（适配器必须产出的切片 id 列表，守护切片从中选）、`seeds`（≥3 个整数）、
`time_limit_s`（单次训练上限，超过记 timeout）、可选 `kill_grace_s`（超时后再等几秒，缺省 60）。

适配器 CLI：`python3 <adapter> --config <cfg.json> --seed <int> --out <dir> [--time-limit <秒>]`。
适配器必须写 `<dir>/metrics.json`：`status`（ok|crash|timeout）、`primary`（该种子的指标）、
`metric_id`、`slices`（切片 id → 指标）、`t_start`、`t_end`、`config`、`error`。
测试集指标只写 `<dir>/sealed/test_metrics.json`（键 `test_primary`），环内任何脚本不读它，
`experiment_log.py finalize` 在收敛后读一次。

跑法：`evaluator.py run-seeds --evaluator evaluator.json --config-diff '<json>' --out-root runs/<exp_id>`
→ `runs/<exp_id>/seed_<n>/metrics.json` 与 `runs/<exp_id>/summary.json`（per_seed / slices_per_seed /
run_status / metrics_dirs / mean / std）。任一种子非 ok，退出码 2，summary 仍写。

参考实现：`playbooks/model-improve/golden/reference/fake_adapter.py`（解析式假适配器，不训练）；
`eval-cases/adapters/lsf_mini_adapter.py`（lsf-mini 真训练，仓库根下）。
```

- [ ] **Step 6: 跑测试确认通过 + 回归**

```bash
python3 -m pytest scripts/tests/test_evaluator.py -q     # 7 passed（timeout 用例约 1–2 秒）
python3 -m pytest scripts/tests -q 2>&1 | tail -1        # 332 passed
```

- [ ] **Step 7: 提交**

```bash
git add ts-diagnose/scripts/evaluator.py ts-diagnose/references/evaluator-contract.md \
        ts-diagnose/playbooks/model-improve/golden/reference/fake_adapter.py \
        ts-diagnose/scripts/tests/test_evaluator.py
git commit -m "feat(scripts): 评估器契约 evaluator.py（validate/run/run-seeds，超时与崩溃有状态，封存测试集）+ 假适配器 + 契约文档

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>"
```

---

### Task 5: 实验日志与冠军 `experiment_log.py`（上）：init / candidates / confirm-round / append

**Files:**
- Create: `ts-diagnose/scripts/experiment_log.py`
- Test: `ts-diagnose/scripts/tests/test_experiment_log.py`

**Interfaces:**
- Produces（文件）：`experiment_log.jsonl`（一行一条候选，字段见 Step 3 的 `cmd_init`/`cmd_append`）；`champion.json`（`exp_id, round, base_config, config, metric, mean, std, per_seed, seeds, noise_floor_3sigma, slices_mean, slices_noise_floor, metrics_dirs, since_round, history[], budget{max_trainings,max_rounds,max_per_round,stagnation_rounds,used_trainings}, converged, converged_reason, updated`）；`rounds/round_<n>/candidates.json`（`round, confirmed, target_model, champion_exp_id, champion_mean, noise_floor_3sigma, seeds, candidates[{exp_id, hypothesis_id, source, config_diff, predicted_gain, guard_slices}], deferred[]`）；`diagnose_state.json.round`。
- Consumes：Task 4 的 `summary.json`（`init --baseline`）；Task 3 的 receipt；Task 2 的账本 `kind=improvement` 条目；`model_profile` 的 `ablation_switches`（`[{component, switch, kind}]`）。
- 批结果文件 `batch_result.json`：`{"results": [<worker 输出 JSON>...]}`，每条含 `status, exp_id, run_status[], receipt_file, per_seed, slices_per_seed, metrics_dirs, blocked_reason`。
- Task 6 补 `decide / new-round / stop / finalize / status`。

- [ ] **Step 1: 写失败测试**

`ts-diagnose/scripts/tests/test_experiment_log.py`：

```python
"""实验日志与冠军：init / candidates / confirm-round / append（Task 5）；decide / new-round / stop / finalize（Task 6）。
全部走 subprocess 跑真 CLI；receipt 用 improve_verdict.judge 现造。"""
import json
import os
import subprocess
import sys

import pytest

SCRIPTS_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ENGINE_DIR = os.path.dirname(SCRIPTS_DIR)
FAKE = os.path.join(ENGINE_DIR, "playbooks", "model-improve", "golden", "reference", "fake_adapter.py")
sys.path.insert(0, SCRIPTS_DIR)
import engine_common as ec  # noqa: E402
import improve_verdict as iv  # noqa: E402

XL = os.path.join(SCRIPTS_DIR, "experiment_log.py")

EVALUATOR = {"adapter": FAKE,
             "base_config": {"model": "TSMixer", "dropout": 0.1, "learning_rate": 1e-3},
             "knobs": {"dropout": {"family": "training", "type": "float"},
                       "learning_rate": {"family": "training", "type": "float"},
                       "tsmixer_no_channel_mix": {"family": "architecture", "type": "flag"},
                       "n_heads": {"family": "architecture", "type": "int"}},
             "metric": {"id": "val_mse", "direction": "lower_is_better"},
             "slices": ["horizon:near", "horizon:mid", "horizon:far"],
             "seeds": [7, 1337, 2021], "time_limit_s": 5}
BASELINE = {"per_seed": [0.2109, 0.2114, 0.2106], "seeds": [7, 1337, 2021],
            "slices_per_seed": [{"horizon:far": 0.274, "horizon:near": 0.169},
                                {"horizon:far": 0.275, "horizon:near": 0.169},
                                {"horizon:far": 0.274, "horizon:near": 0.168}],
            "metrics_dirs": ["runs/E000/seed_7", "runs/E000/seed_1337", "runs/E000/seed_2021"],
            "run_status": ["ok", "ok", "ok"]}
LEDGER = {"slice_map": [], "hypotheses": [
    {"id": "H1", "claim": "c", "component": "tsmixer.channel_mix", "falsifiable_pred": "p",
     "discriminating_power": 3, "status": "pending", "provenance": "pre-registered", "kill_receipt": None},
    {"id": "H2", "claim": "c", "component": "tsmixer.dropout", "falsifiable_pred": "p",
     "discriminating_power": 1, "status": "pending", "provenance": "pre-registered", "kill_receipt": None},
    {"id": "F2", "kind": "improvement", "derived_from": "H2", "claim": "c", "component": "tsmixer.dropout",
     "falsifiable_pred": "p", "fix": {"target_model": "TSMixer", "config_diff": {"dropout": 0.05},
                                     "predicted_gain": "降 0.005", "guard_slices": ["horizon:far"]},
     "status": "pending", "provenance": "pre-registered", "kill_receipt": None, "receipt": None},
    {"id": "F1", "kind": "improvement", "derived_from": "H1", "claim": "c", "component": "tsmixer.channel_mix",
     "falsifiable_pred": "p", "fix": {"target_model": "TSMixer", "config_diff": {"tsmixer_no_channel_mix": True},
                                     "predicted_gain": "降 0.03", "guard_slices": ["horizon:far"]},
     "status": "pending", "provenance": "pre-registered", "kill_receipt": None, "receipt": None},
    {"id": "F9", "kind": "improvement", "derived_from": "H1", "claim": "c", "component": "x",
     "falsifiable_pred": "p", "fix": {"target_model": "TiDE", "config_diff": {"dropout": 0.3},
                                     "predicted_gain": "g", "guard_slices": []},
     "status": "pending", "provenance": "pre-registered", "kill_receipt": None, "receipt": None}]}


def run(wd, *args, ok=True):
    r = subprocess.run([sys.executable, XL, *args], cwd=str(wd), capture_output=True, text=True, timeout=60)
    if ok:
        assert r.returncode == 0, r.stdout + r.stderr
    return r


@pytest.fixture
def wd(tmp_path):
    ec.dump_json(EVALUATOR, str(tmp_path / "evaluator.json"))
    ec.dump_json(BASELINE, str(tmp_path / "baseline.json"))
    ec.dump_json(LEDGER, str(tmp_path / "hypothesis_ledger.json"))
    ec.dump_json({"playbook": "model-improve"}, str(tmp_path / "diagnose_config.json"))
    for d in BASELINE["metrics_dirs"]:
        os.makedirs(tmp_path / d / "sealed", exist_ok=True)
        (tmp_path / d / "sealed" / "test_metrics.json").write_text(json.dumps({"test_primary": 0.23}), encoding="utf-8")
    run(tmp_path, "init", "--evaluator", "evaluator.json", "--baseline", "baseline.json",
        "--max-trainings", "30", "--max-rounds", "3", "--max-per-round", "10", "--stagnation-rounds", "2")
    return tmp_path


def receipt(wd, exp_id, hyp, per_seed, guards=None, sealed_seed_vals=(0.20, 0.20, 0.20)):
    champ = ec.read_json(str(wd / "champion.json"))
    r = iv.judge(exp_id, hyp, per_seed, champ["mean"], champ["noise_floor_3sigma"], guards=guards)
    adapter = wd / "adapter.py"
    adapter.write_text("print(1)\n", encoding="utf-8")
    r.update({"config_diff": {}, "produced_by": str(adapter), "script_sha256": iv._sha256(str(adapter)),
              "t_start": "t0", "t_end": "t1", "script_selftest": "ok"})
    os.makedirs(wd / "receipts", exist_ok=True)
    (wd / "receipts" / f"{exp_id}.json").write_text(json.dumps([r]), encoding="utf-8")
    dirs = []
    for i, v in enumerate(sealed_seed_vals):
        d = wd / "runs" / exp_id / f"seed_{i}"
        os.makedirs(d / "sealed", exist_ok=True)
        (d / "sealed" / "test_metrics.json").write_text(json.dumps({"test_primary": v}), encoding="utf-8")
        dirs.append(str(d.relative_to(wd)))
    return {"status": "COMPUTE_DONE", "task": "candidate", "exp_id": exp_id, "hypothesis_id": hyp,
            "receipt_file": f"receipts/{exp_id}.json", "receipt_line": r["line"], "per_seed": per_seed,
            "run_status": ["ok"] * 3, "metrics_dirs": dirs,
            "slices_per_seed": [{"horizon:far": 0.26, "horizon:near": 0.16}] * 3}


def test_init_writes_champion_log_state_and_refuses_twice(wd):
    champ = ec.read_json(str(wd / "champion.json"))
    assert champ["exp_id"] == "E000" and abs(champ["mean"] - 0.21097) < 1e-5
    assert champ["budget"]["used_trainings"] == 3 and champ["converged"] is False
    assert champ["base_config"] == EVALUATOR["base_config"]
    assert "horizon:far" in champ["slices_mean"] and "horizon:far" in champ["slices_noise_floor"]
    rows = [json.loads(l) for l in (wd / "experiment_log.jsonl").read_text(encoding="utf-8").splitlines()]
    assert rows[0]["exp_id"] == "E000" and rows[0]["verdict"] == "baseline"
    assert ec.read_json(str(wd / "diagnose_state.json"))["round"] == 1
    r = run(wd, "init", "--evaluator", "evaluator.json", "--baseline", "baseline.json", ok=False)
    assert r.returncode != 0 and "只 init 一次" in r.stdout + r.stderr


def test_candidates_from_ledger_filters_orders_and_numbers(wd):
    run(wd, "candidates", "--ledger", "hypothesis_ledger.json", "--target", "TSMixer")
    doc = ec.read_json(str(wd / "rounds" / "round_1" / "candidates.json"))
    ids = [c["hypothesis_id"] for c in doc["candidates"]]
    assert ids == ["F1", "F2"]                       # F9 目标模型不符被滤掉；按父假设判别力排序
    assert [c["exp_id"] for c in doc["candidates"]] == ["E001", "E002"]
    assert doc["confirmed"] is False and doc["seeds"] == [7, 1337, 2021]


def test_candidates_from_switches_parses_flags_and_caps_by_budget(wd):
    ec.dump_json({"ablation_switches": [
        {"component": "b", "switch": "--n_heads=1", "kind": "config-flag"},
        {"component": "a", "switch": "--tsmixer_no_channel_mix", "kind": "config-flag"},
        {"component": "c", "switch": "--zero_attn", "kind": "code-stub"},
        {"component": "d", "switch": "", "kind": "not-intervenable"}]}, str(wd / "switches.json"))
    champ = ec.read_json(str(wd / "champion.json"))
    champ["budget"]["max_per_round"] = 2
    ec.dump_json(champ, str(wd / "champion.json"))
    run(wd, "candidates", "--switches", "switches.json", "--target", "TSMixer", "--guard", "horizon:far")
    doc = ec.read_json(str(wd / "rounds" / "round_1" / "candidates.json"))
    diffs = [c["config_diff"] for c in doc["candidates"]]
    assert diffs == [{"tsmixer_no_channel_mix": True}, {"n_heads": 1}]   # config-flag 先、按 component 排
    assert doc["deferred"][0]["config_diff"] == {"zero_attn": True} and len(doc["candidates"]) == 2
    assert doc["candidates"][0]["guard_slices"] == ["horizon:far"]


def test_append_requires_confirm_and_rejects_sealed_unknown_duplicate(wd):
    run(wd, "candidates", "--ledger", "hypothesis_ledger.json", "--target", "TSMixer")
    res = receipt(wd, "E001", "F1", [0.180, 0.181, 0.179])
    ec.dump_json({"results": [res]}, str(wd / "rounds" / "round_1" / "batch_result.json"))
    r = run(wd, "append", "--batch", "rounds/round_1/batch_result.json", ok=False)
    assert r.returncode != 0 and "未确认" in r.stdout + r.stderr
    run(wd, "confirm-round")
    bad = dict(res, sealed_test_primary=0.1)
    ec.dump_json({"results": [bad]}, str(wd / "bad.json"))
    r = run(wd, "append", "--batch", "bad.json", ok=False)
    assert r.returncode != 0 and "封存" in r.stdout + r.stderr
    ec.dump_json({"results": [dict(res, exp_id="E077")]}, str(wd / "unk.json"))
    assert run(wd, "append", "--batch", "unk.json", ok=False).returncode != 0
    run(wd, "append", "--batch", "rounds/round_1/batch_result.json")
    r = run(wd, "append", "--batch", "rounds/round_1/batch_result.json", ok=False)
    assert r.returncode != 0 and "重复" in r.stdout + r.stderr
    rows = [json.loads(l) for l in (wd / "experiment_log.jsonl").read_text(encoding="utf-8").splitlines()]
    assert rows[-1]["exp_id"] == "E001" and rows[-1]["verdict"] == "keep" and rows[-1]["round"] == 1
    assert rows[-1]["receipt_line"].startswith("- E001 keep")


def test_append_marks_blocked_or_crashed_as_untested(wd):
    run(wd, "candidates", "--ledger", "hypothesis_ledger.json", "--target", "TSMixer")
    run(wd, "confirm-round")
    blocked = {"status": "BLOCKED", "task": "candidate", "exp_id": "E001", "hypothesis_id": "F1",
               "run_status": ["ok", "crash", "ok"], "blocked_reason": "seed 1337 NaN loss"}
    ec.dump_json({"results": [blocked]}, str(wd / "rounds" / "round_1" / "batch_result.json"))
    run(wd, "append", "--batch", "rounds/round_1/batch_result.json")
    rows = [json.loads(l) for l in (wd / "experiment_log.jsonl").read_text(encoding="utf-8").splitlines()]
    assert rows[-1]["verdict"] == "untested" and "NaN" in rows[-1]["untested_reason"]
```

- [ ] **Step 2: 跑测试确认失败**（`experiment_log.py` 不存在）

- [ ] **Step 3: 写 `experiment_log.py`**（本 task 写全模块骨架；`decide/new-round/stop/finalize/status` 先放占位函数，Task 6 填）

```python
#!/usr/bin/env python3
"""实验日志与冠军状态（改进环的记忆）。只由主 agent 执行（单写者）。
文件：experiment_log.jsonl（一行一条候选）、champion.json（当前冠军 + 预算 + 收敛）、
rounds/round_<n>/{candidates.json, batch_result.json, summary.json}、final_test.json（封存终评）。
子命令：init / candidates / confirm-round / append / decide / new-round / stop / finalize / status。"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import statistics
import sys
from collections import Counter

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import engine_common as ec  # noqa: E402

LOG = "experiment_log.jsonl"
CHAMP = "champion.json"
FINAL = "final_test.json"
SEALED_KEYS = ("test", "sealed")


def _now():
    return dt.datetime.now().isoformat(timespec="seconds")


def _state():
    return ec.read_json(ec.STATE_PATH) or {}


def _round():
    return int(_state().get("round") or 1)


def _set_round(n):
    st = _state()
    st["round"] = int(n)
    ec.dump_json(st, ec.STATE_PATH)


def _round_dir(n=None):
    d = os.path.join("rounds", f"round_{_round() if n is None else n}")
    os.makedirs(d, exist_ok=True)
    return d


def _need(path, msg):
    doc = ec.read_json(path)
    if doc is None:
        sys.exit(f"✗ {msg}：{path}")
    return doc


def _champ():
    return _need(CHAMP, "无 champion.json——先 experiment_log.py init")


def _save_champ(c):
    c["updated"] = _now()
    ec.dump_json(c, CHAMP)


def read_log():
    if not os.path.exists(LOG):
        return []
    with open(LOG, encoding="utf-8") as f:
        return [json.loads(line) for line in f if line.strip()]


def append_rows(rows):
    with open(LOG, "a", encoding="utf-8") as f:
        for r in rows:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")


def _nf(per):
    return (statistics.stdev(per) if len(per) > 1 else 0.0) * 3


def _slice_keys(sps):
    keys = set()
    for s in sps:
        keys |= set(s)
    return sorted(keys)


def _slices_mean(sps):
    return {k: statistics.fmean([s[k] for s in sps if k in s]) for k in _slice_keys(sps)}


def _slices_nf(sps):
    return {k: _nf([s[k] for s in sps if k in s]) for k in _slice_keys(sps)}


def _keys(o):
    if isinstance(o, dict):
        for k, v in o.items():
            yield k
            yield from _keys(v)
    elif isinstance(o, list):
        for v in o:
            yield from _keys(v)


def _last_entry(path):
    doc = ec.read_json(path)
    if isinstance(doc, list):
        return doc[-1] if doc else None
    return doc if isinstance(doc, dict) else None


def _switch_to_diff(switch):
    s = str(switch).lstrip("-")
    if "=" in s:
        k, v = s.split("=", 1)
        for cast in (int, float):
            try:
                return {k: cast(v)}
            except ValueError:
                pass
        return {k: v}
    return {s: True}


# ---------------------------------------------------------------- init
def cmd_init(a):
    if os.path.exists(CHAMP):
        sys.exit("✗ champion.json 已存在——改进环只 init 一次；要重来先删 champion.json / experiment_log.jsonl / rounds/")
    ev = _need(a.evaluator, "读不到 evaluator")
    base = _need(a.baseline, "读不到基线 summary")
    per = [float(x) for x in base.get("per_seed") or []]
    if len(per) < 3:
        sys.exit(f"✗ 基线有效种子 {len(per)} 个（<3）——补种子再 init")
    sps = base.get("slices_per_seed") or []
    mean, std = statistics.fmean(per), statistics.stdev(per)
    champ = {"exp_id": "E000", "round": 1, "base_config": ev["base_config"], "config": dict(ev["base_config"]),
             "metric": ev["metric"], "mean": mean, "std": std, "per_seed": per,
             "seeds": base.get("seeds") or ev["seeds"], "noise_floor_3sigma": _nf(per),
             "slices_mean": _slices_mean(sps), "slices_noise_floor": _slices_nf(sps),
             "metrics_dirs": base.get("metrics_dirs") or [], "since_round": 0,
             "history": [{"round": 0, "exp_id": "E000", "mean": mean, "delta": 0.0}],
             "budget": {"max_trainings": a.max_trainings, "max_rounds": a.max_rounds,
                        "max_per_round": a.max_per_round, "stagnation_rounds": a.stagnation_rounds,
                        "used_trainings": len(per)},
             "converged": False, "converged_reason": None}
    _save_champ(champ)
    append_rows([{"exp_id": "E000", "round": 0, "hypothesis_id": None, "source": "baseline",
                  "config_diff": {}, "seeds": champ["seeds"], "per_seed": per, "mean": mean, "std": std,
                  "delta": 0.0, "noise_floor_3sigma": champ["noise_floor_3sigma"], "guard": {},
                  "verdict": "baseline", "receipt_file": None, "receipt_line": None,
                  "slices_per_seed": sps, "metrics_dirs": champ["metrics_dirs"], "t": _now()}])
    _set_round(1)
    print(f"✓ 冠军 E000：mean={mean:.6f} std={std:.6f} 噪声底3σ={champ['noise_floor_3sigma']:.6f}；"
          f"预算 {a.max_trainings} 次训练 / {a.max_rounds} 轮 / 每轮 ≤{a.max_per_round} 候选；已用 {len(per)}")


# ---------------------------------------------------------------- candidates
def cmd_candidates(a):
    champ = _champ()
    rows = read_log()
    rnd = _round()
    if champ.get("converged"):
        sys.exit(f"✗ 已收敛（{champ['converged_reason']}）——进结论阶段，不再排候选")
    next_id = 1 + max(int(r["exp_id"][1:]) for r in rows)
    cands = []
    if a.ledger:
        led = _need(a.ledger, "读不到账本")
        by_id = {h.get("id"): h for h in led.get("hypotheses") or []}
        hyps = [h for h in led.get("hypotheses") or []
                if h.get("kind") == "improvement" and h.get("status") == "pending"
                and (h.get("fix") or {}).get("target_model") == a.target]

        def key(h):
            parent = by_id.get(h.get("derived_from")) or {}
            return (-(parent.get("discriminating_power") or 0), h["id"])
        for h in sorted(hyps, key=key):
            cands.append({"hypothesis_id": h["id"], "source": "ledger", "config_diff": h["fix"]["config_diff"],
                          "predicted_gain": h["fix"]["predicted_gain"], "guard_slices": h["fix"]["guard_slices"]})
    if a.switches:
        sw = _need(a.switches, "读不到 switches")
        items = sw.get("ablation_switches", sw) if isinstance(sw, dict) else sw
        order = {"config-flag": 0, "code-stub": 1}
        picked = [i for i in items if i.get("kind") in order and i.get("switch")]
        for it in sorted(picked, key=lambda i: (order[i["kind"]], i.get("component", ""))):
            cands.append({"hypothesis_id": None, "source": "switches", "config_diff": _switch_to_diff(it["switch"]),
                          "predicted_gain": "未预登记（素版）", "guard_slices": [s for s in a.guard.split(",") if s]})
    seen = {json.dumps(r["config_diff"], sort_keys=True) for r in rows}
    fresh = []
    for c in cands:
        k = json.dumps(c["config_diff"], sort_keys=True)
        if k in seen:
            continue
        seen.add(k)
        fresh.append(c)
    b = champ["budget"]
    left = int(b["max_trainings"]) - int(b["used_trainings"])
    cap = min(int(b["max_per_round"]), max(0, left // max(1, len(champ["seeds"]))))
    for i, c in enumerate(fresh[:cap]):
        c["exp_id"] = f"E{next_id + i:03d}"
    doc = {"round": rnd, "confirmed": False, "target_model": a.target, "champion_exp_id": champ["exp_id"],
           "champion_mean": champ["mean"], "noise_floor_3sigma": champ["noise_floor_3sigma"],
           "seeds": champ["seeds"], "candidates": fresh[:cap], "deferred": fresh[cap:], "t": _now()}
    out = a.out or os.path.join(_round_dir(), "candidates.json")
    ec.dump_json(doc, out)
    n = len(doc["candidates"])
    print(f"✓ 第 {rnd} 轮候选 {n} 条（× {len(champ['seeds'])} 种子 = {n * len(champ['seeds'])} 次训练），"
          f"顺延 {len(doc['deferred'])} 条 → {out}")
    if n == 0:
        print("  ⚠ 本轮没有新候选——用 stop --reason no_candidates 收敛，或换候选来源")


def cmd_confirm_round(a):
    p = os.path.join(_round_dir(), "candidates.json")
    doc = _need(p, "无本轮 candidates.json——先 candidates")
    if not doc.get("candidates"):
        sys.exit("✗ 候选为空，不能确认")
    doc["confirmed"], doc["confirmed_at"] = True, _now()
    ec.dump_json(doc, p)
    print(f"✓ 第 {doc['round']} 轮已确认开跑：{[c['exp_id'] for c in doc['candidates']]}")


# ---------------------------------------------------------------- append
def cmd_append(a):
    _champ()
    rnd = _round()
    cands = _need(os.path.join(_round_dir(), "candidates.json"), "本轮无 candidates.json")
    if not cands.get("confirmed"):
        sys.exit("✗ 本轮候选未确认（先 confirm-round）")
    batch = _need(a.batch, "读不到批结果")
    results = batch.get("results", batch) if isinstance(batch, dict) else batch
    for k in _keys(results):
        if any(s in str(k).lower() for s in SEALED_KEYS):
            sys.exit(f"✗ 结果里出现封存字段 {k!r}——环内不许读测试集")
    by_exp = {c["exp_id"]: c for c in cands["candidates"]}
    existing = {r["exp_id"] for r in read_log()}
    rows = []
    for res in results:
        if not isinstance(res, dict):
            continue
        eid = res.get("exp_id")
        c = by_exp.get(eid)
        if c is None:
            sys.exit(f"✗ {eid} 不在第 {rnd} 轮候选里")
        if eid in existing:
            sys.exit(f"✗ {eid} 已在日志里，不许重复追加")
        row = {"exp_id": eid, "round": rnd, "hypothesis_id": c.get("hypothesis_id"), "source": c["source"],
               "config_diff": c["config_diff"], "seeds": cands["seeds"], "t": _now(),
               "metrics_dirs": res.get("metrics_dirs") or [], "slices_per_seed": res.get("slices_per_seed") or []}
        bad = [s for s in (res.get("run_status") or []) if s != "ok"]
        if res.get("status") != "COMPUTE_DONE" or bad or not res.get("receipt_file"):
            row.update({"verdict": "untested", "per_seed": res.get("per_seed") or [], "delta": None,
                        "untested_reason": res.get("blocked_reason") or ",".join(res.get("run_status") or [])
                        or res.get("status") or "无结果", "receipt_file": None, "receipt_line": None})
        else:
            rec = _last_entry(res["receipt_file"])
            if rec is None:
                sys.exit(f"✗ {eid} 的 receipt 缺失或为空：{res['receipt_file']}")
            if rec.get("exp_id") != eid:
                sys.exit(f"✗ {res['receipt_file']} 的 exp_id={rec.get('exp_id')} ≠ {eid}")
            if rec.get("verdict") not in ("keep", "discard", "undecided"):
                sys.exit(f"✗ {eid} receipt 判定非法：{rec.get('verdict')}")
            row.update({"per_seed": rec["per_seed"], "mean": rec["mean"], "std": rec["std"], "delta": rec["delta"],
                        "noise_floor_3sigma": rec["noise_floor_3sigma"], "guard": rec.get("guard") or {},
                        "verdict": rec["verdict"], "receipt_file": res["receipt_file"], "receipt_line": rec["line"]})
        rows.append(row)
    if not rows:
        sys.exit("✗ 批结果里没有任何候选")
    append_rows(rows)
    print(f"✓ 追加 {len(rows)} 行：" + ", ".join(f"{r['exp_id']}={r['verdict']}" for r in rows))


# ---------------------------------------------------------------- Task 6 填充
def cmd_decide(a):
    sys.exit("✗ decide 未实现（Task 6）")


def cmd_new_round(a):
    sys.exit("✗ new-round 未实现（Task 6）")


def cmd_stop(a):
    sys.exit("✗ stop 未实现（Task 6）")


def cmd_finalize(a):
    sys.exit("✗ finalize 未实现（Task 6）")


def cmd_status(a):
    sys.exit("✗ status 未实现（Task 6）")


# ---------------------------------------------------------------- CLI
def main():
    ap = argparse.ArgumentParser(description="实验日志与冠军状态（改进环）")
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("init")
    p.add_argument("--evaluator", required=True)
    p.add_argument("--baseline", required=True, help="evaluator.py run-seeds 产的基线 summary.json")
    p.add_argument("--max-trainings", dest="max_trainings", type=int, default=30)
    p.add_argument("--max-rounds", dest="max_rounds", type=int, default=3)
    p.add_argument("--max-per-round", dest="max_per_round", type=int, default=10)
    p.add_argument("--stagnation-rounds", dest="stagnation_rounds", type=int, default=2)
    p.set_defaults(fn=cmd_init)
    p = sub.add_parser("candidates")
    p.add_argument("--ledger", default=None, help="hypothesis_ledger.json（取 kind=improvement 且 pending 的条目）")
    p.add_argument("--switches", default=None, help="model_profile 的 ablation_switches JSON（素版候选）")
    p.add_argument("--target", required=True, help="改进目标模型名（匹配 fix.target_model）")
    p.add_argument("--guard", default="", help="素版候选的守护切片，逗号分隔")
    p.add_argument("--out", default=None)
    p.set_defaults(fn=cmd_candidates)
    sub.add_parser("confirm-round").set_defaults(fn=cmd_confirm_round)
    p = sub.add_parser("append")
    p.add_argument("--batch", required=True, help="{\"results\": [<worker 输出 JSON>...]}")
    p.set_defaults(fn=cmd_append)
    sub.add_parser("decide").set_defaults(fn=cmd_decide)
    sub.add_parser("new-round").set_defaults(fn=cmd_new_round)
    p = sub.add_parser("stop")
    p.add_argument("--reason", required=True)
    p.set_defaults(fn=cmd_stop)
    sub.add_parser("finalize").set_defaults(fn=cmd_finalize)
    sub.add_parser("status").set_defaults(fn=cmd_status)
    a = ap.parse_args()
    a.fn(a)


if __name__ == "__main__":
    main()
```

- [ ] **Step 4: 跑测试确认通过 + 回归**

```bash
python3 -m pytest scripts/tests/test_experiment_log.py -q     # 5 passed
python3 -m pytest scripts/tests -q 2>&1 | tail -1               # 337 passed
```

- [ ] **Step 5: 提交**

```bash
git add ts-diagnose/scripts/experiment_log.py ts-diagnose/scripts/tests/test_experiment_log.py
git commit -m "feat(scripts): experiment_log.py（上）——init 冠军与噪声底、candidates 排队（账本/素版）、confirm-round、append（封存键拒收、untested）

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>"
```

---

### Task 6: `experiment_log.py`（下）：decide / new-round / stop / finalize / status

**Files:**
- Modify: `ts-diagnose/scripts/experiment_log.py`（替换 Task 5 的五个占位函数）
- Test: `ts-diagnose/scripts/tests/test_experiment_log.py`（追加）

**Interfaces:**
- Produces：`rounds/round_<n>/summary.json`（`round, n_candidates, counts, kept[], new_champion, previous_champion, champion_mean, champion_delta_vs_prev, budget, converged, converged_reason, receipt_lines[], untested[], guard_regress[], deferred[], t`）；`champion.json.converged/converged_reason`（`budget_exhausted | max_rounds | stagnation | user:<原因>`）；`final_test.json`（`baseline{exp_id,per_seed,mean}, champion{exp_id,per_seed,mean,config_diff_vs_baseline}, delta, noise_floor_3sigma_test, verdict ∈ improved|not_distinguishable|worse|no_change, line, converged_reason, t`）。
- 停止规则：`used_trainings ≥ max_trainings`；`round ≥ max_rounds`；最近 `stagnation_rounds` 轮都无 keep；`stop --reason`。

- [ ] **Step 1: 追加失败测试**（文件末尾）

```python
def _round1(wd, keep=True):
    run(wd, "candidates", "--ledger", "hypothesis_ledger.json", "--target", "TSMixer")
    run(wd, "confirm-round")
    guards = {"horizon:far": {"per_seed": [0.30, 0.31, 0.29], "champion_mean": 0.274, "noise_floor": 0.002}}
    r1 = receipt(wd, "E001", "F1", [0.180, 0.181, 0.179], guards=guards, sealed_seed_vals=(0.19, 0.19, 0.19))
    r2 = receipt(wd, "E002", "F2", [0.205, 0.206, 0.204] if keep else [0.2109, 0.2114, 0.2106],
                 sealed_seed_vals=(0.215, 0.216, 0.214))
    ec.dump_json({"results": [r1, r2]}, str(wd / "rounds" / "round_1" / "batch_result.json"))
    run(wd, "append", "--batch", "rounds/round_1/batch_result.json")


def test_decide_updates_champion_budget_summary_and_refuses_twice(wd):
    _round1(wd)
    r = run(wd, "decide")
    assert "E000 → E002" in r.stdout
    champ = ec.read_json(str(wd / "champion.json"))
    assert champ["exp_id"] == "E002" and champ["config"]["dropout"] == 0.05 and champ["since_round"] == 1
    assert champ["budget"]["used_trainings"] == 9 and champ["converged"] is False
    s = ec.read_json(str(wd / "rounds" / "round_1" / "summary.json"))
    assert s["counts"] == {"discard": 1, "keep": 1} and s["guard_regress"] == ["E001"]
    assert s["new_champion"] == "E002" and len(s["receipt_lines"]) == 2
    r = run(wd, "decide", ok=False)
    assert r.returncode != 0 and "已裁决" in r.stdout + r.stderr


def test_decide_requires_all_candidates_logged(wd):
    run(wd, "candidates", "--ledger", "hypothesis_ledger.json", "--target", "TSMixer")
    run(wd, "confirm-round")
    r = run(wd, "decide", ok=False)
    assert r.returncode != 0 and "先 append" in r.stdout + r.stderr


def test_new_round_bumps_and_reenters_candidates(wd):
    _round1(wd)
    run(wd, "decide")
    run(wd, "new-round")
    assert ec.read_json(str(wd / "diagnose_state.json"))["round"] == 2
    run(wd, "candidates", "--ledger", "hypothesis_ledger.json", "--target", "TSMixer")
    doc = ec.read_json(str(wd / "rounds" / "round_2" / "candidates.json"))
    assert doc["candidates"] == [] and doc["round"] == 2      # F1/F2 的 config_diff 已跑过，去重后为空


def test_convergence_max_rounds_and_stagnation_and_budget(wd):
    champ = ec.read_json(str(wd / "champion.json"))
    champ["budget"].update({"max_rounds": 1})
    ec.dump_json(champ, str(wd / "champion.json"))
    _round1(wd)
    run(wd, "decide")
    assert ec.read_json(str(wd / "champion.json"))["converged_reason"] == "max_rounds"
    r = run(wd, "new-round", ok=False)
    assert r.returncode != 0 and "已收敛" in r.stdout + r.stderr


def test_convergence_stagnation_two_rounds_without_keep(wd):
    champ = ec.read_json(str(wd / "champion.json"))
    champ["budget"].update({"max_rounds": 5, "max_trainings": 100})
    ec.dump_json(champ, str(wd / "champion.json"))
    _round1(wd, keep=False)                       # E001 守护退化 discard，E002 噪声内 undecided
    run(wd, "decide")
    assert ec.read_json(str(wd / "champion.json"))["converged"] is False
    run(wd, "new-round")
    ec.dump_json({"ablation_switches": [{"component": "h", "switch": "--n_heads=4", "kind": "config-flag"}]},
                 str(wd / "sw.json"))
    run(wd, "candidates", "--switches", "sw.json", "--target", "TSMixer")
    run(wd, "confirm-round")
    r3 = receipt(wd, "E003", None, [0.2110, 0.2113, 0.2108])
    ec.dump_json({"results": [r3]}, str(wd / "rounds" / "round_2" / "batch_result.json"))
    run(wd, "append", "--batch", "rounds/round_2/batch_result.json")
    run(wd, "decide")
    assert ec.read_json(str(wd / "champion.json"))["converged_reason"] == "stagnation"


def test_convergence_budget_exhausted(wd):
    champ = ec.read_json(str(wd / "champion.json"))
    champ["budget"].update({"max_trainings": 9, "max_rounds": 5})
    ec.dump_json(champ, str(wd / "champion.json"))
    _round1(wd)
    run(wd, "decide")
    assert ec.read_json(str(wd / "champion.json"))["converged_reason"] == "budget_exhausted"


def test_stop_then_finalize_reads_sealed_once(wd):
    _round1(wd)
    run(wd, "decide")
    r = run(wd, "finalize", ok=False)
    assert r.returncode != 0 and "未收敛" in r.stdout + r.stderr
    run(wd, "stop", "--reason", "够了")
    assert ec.read_json(str(wd / "champion.json"))["converged_reason"] == "user:够了"
    r = run(wd, "finalize")
    doc = ec.read_json(str(wd / "final_test.json"))
    assert doc["champion"]["exp_id"] == "E002" and abs(doc["baseline"]["mean"] - 0.23) < 1e-12
    assert doc["verdict"] == "improved" and doc["champion"]["config_diff_vs_baseline"] == {"dropout": 0.05}
    assert "final_test improved" in r.stdout
    r = run(wd, "finalize", ok=False)
    assert r.returncode != 0 and "只评一次" in r.stdout + r.stderr


def test_status_prints_json(wd):
    r = run(wd, "status")
    doc = json.loads(r.stdout)
    assert doc["champion"] == "E000" and doc["round"] == 1 and doc["verdicts"] == {"baseline": 1}
```

- [ ] **Step 2: 跑测试确认失败**（占位函数退出非零）

- [ ] **Step 3: 替换五个占位函数**

```python
# ---------------------------------------------------------------- decide
def cmd_decide(a):
    champ = _champ()
    rnd = _round()
    cands = _need(os.path.join(_round_dir(), "candidates.json"), "本轮无 candidates.json")
    if os.path.exists(os.path.join(_round_dir(), "summary.json")):
        sys.exit("✗ 本轮已裁决过（summary.json 存在）——要再来一轮先 new-round")
    all_rows = read_log()
    rows = [r for r in all_rows if r["round"] == rnd]
    have = {r["exp_id"] for r in rows}
    missing = [c["exp_id"] for c in cands["candidates"] if c["exp_id"] not in have]
    if missing:
        sys.exit(f"✗ 候选 {missing} 还没有日志行——先 append")
    keeps = [r for r in rows if r["verdict"] == "keep"]
    best = min(keeps, key=lambda r: r["mean"]) if keeps else None
    prev = champ["exp_id"]
    if best:
        sps = best.get("slices_per_seed") or []
        champ.update({"exp_id": best["exp_id"], "config": {**champ["config"], **best["config_diff"]},
                      "mean": best["mean"], "std": best["std"], "per_seed": best["per_seed"],
                      "noise_floor_3sigma": _nf(best["per_seed"]),
                      "slices_mean": _slices_mean(sps) if sps else champ["slices_mean"],
                      "slices_noise_floor": _slices_nf(sps) if sps else champ["slices_noise_floor"],
                      "metrics_dirs": best.get("metrics_dirs") or [], "since_round": rnd})
        champ["history"].append({"round": rnd, "exp_id": best["exp_id"], "mean": best["mean"], "delta": best["delta"]})
    b = champ["budget"]
    b["used_trainings"] = int(b["used_trainings"]) + len(cands["candidates"]) * len(cands["seeds"])
    reason = None
    if b["used_trainings"] >= int(b["max_trainings"]):
        reason = "budget_exhausted"
    elif rnd >= int(b["max_rounds"]):
        reason = "max_rounds"
    else:
        k = int(b["stagnation_rounds"])
        recent = sorted({r["round"] for r in all_rows if r["round"] >= 1})[-k:]
        if len(recent) >= k and not any(r["verdict"] == "keep" for r in all_rows if r["round"] in recent):
            reason = "stagnation"
    if reason:
        champ["converged"], champ["converged_reason"] = True, reason
    champ["round"] = rnd
    _save_champ(champ)
    counts = Counter(r["verdict"] for r in rows)
    summary = {"round": rnd, "n_candidates": len(cands["candidates"]), "counts": dict(counts),
               "kept": [r["exp_id"] for r in keeps], "new_champion": best["exp_id"] if best else None,
               "previous_champion": prev, "champion_mean": champ["mean"],
               "champion_delta_vs_prev": best["delta"] if best else 0.0, "budget": b,
               "converged": champ["converged"], "converged_reason": champ["converged_reason"],
               "receipt_lines": [r["receipt_line"] for r in rows if r.get("receipt_line")],
               "untested": [{"exp_id": r["exp_id"], "reason": r.get("untested_reason")} for r in rows if r["verdict"] == "untested"],
               "guard_regress": [r["exp_id"] for r in rows
                                 if any(g.get("regress") for g in (r.get("guard") or {}).values())],
               "deferred": cands.get("deferred") or [], "t": _now()}
    ec.dump_json(summary, os.path.join(_round_dir(), "summary.json"))
    print(f"✓ 第 {rnd} 轮裁决：{dict(counts)}；冠军 {prev} → {champ['exp_id']}（mean={champ['mean']:.6f}）；"
          f"已用训练 {b['used_trainings']}/{b['max_trainings']}；"
          + (f"已收敛（{reason}）→ 进结论阶段" if reason else "未收敛 → new-round 或 stop"))


def cmd_new_round(a):
    champ = _champ()
    rnd = _round()
    if champ.get("converged"):
        sys.exit(f"✗ 已收敛（{champ['converged_reason']}）——进结论阶段；不许绕过预算再开一轮")
    if not os.path.exists(os.path.join(_round_dir(), "summary.json")):
        sys.exit("✗ 本轮还没裁决（先 decide）")
    _set_round(rnd + 1)
    champ["round"] = rnd + 1
    _save_champ(champ)
    print(f"✓ 进入第 {rnd + 1} 轮——下一步 candidates（回生成器补的候选标 provenance=post-hoc）")


def cmd_stop(a):
    champ = _champ()
    champ["converged"], champ["converged_reason"] = True, f"user:{a.reason}"
    _save_champ(champ)
    print(f"✓ 用户终止：{a.reason}——进结论阶段")


def _sealed_primary(dirs):
    vals = []
    for d in dirs:
        p = os.path.join(d, "sealed", "test_metrics.json")
        doc = ec.read_json(p)
        if not isinstance(doc, dict):
            sys.exit(f"✗ 缺封存终评文件 {p}")
        v = doc.get("test_primary", doc.get("test_mse"))
        if not isinstance(v, (int, float)):
            sys.exit(f"✗ {p} 缺 test_primary / test_mse")
        vals.append(float(v))
    return vals


def cmd_finalize(a):
    champ = _champ()
    if not champ.get("converged"):
        sys.exit("✗ 未收敛不许开封测试集——decide/stop 之后再 finalize")
    if os.path.exists(FINAL):
        sys.exit(f"✗ {FINAL} 已存在——封存测试集只评一次")
    base = next(r for r in read_log() if r["exp_id"] == "E000")
    b = _sealed_primary(base["metrics_dirs"])
    c = b if champ["exp_id"] == "E000" else _sealed_primary(champ["metrics_dirs"])
    bm, cm, nf = statistics.fmean(b), statistics.fmean(c), _nf(b)
    delta = cm - bm
    if champ["exp_id"] == "E000":
        v = "no_change"
    elif delta < 0 and abs(delta) >= nf:
        v = "improved"
    elif delta > 0 and delta >= nf:
        v = "worse"
    else:
        v = "not_distinguishable"
    doc = {"metric_id_sealed": "test_primary",
           "baseline": {"exp_id": "E000", "per_seed": b, "mean": bm},
           "champion": {"exp_id": champ["exp_id"], "per_seed": c, "mean": cm,
                        "config_diff_vs_baseline": {k: v2 for k, v2 in champ["config"].items()
                                                    if (champ.get("base_config") or {}).get(k) != v2}},
           "delta": delta, "noise_floor_3sigma_test": nf, "verdict": v,
           "converged_reason": champ["converged_reason"],
           "line": f"- final_test {v}: champion={champ['exp_id']} delta={delta:+.4f} noise_floor={nf:.4f} seeds={len(c)}",
           "t": _now()}
    ec.dump_json(doc, FINAL)
    print(doc["line"])


def cmd_status(a):
    champ = _champ()
    rows = read_log()
    print(json.dumps({"round": _round(), "champion": champ["exp_id"], "mean": champ["mean"],
                      "budget": champ["budget"], "converged": champ["converged"],
                      "reason": champ["converged_reason"], "rows": len(rows),
                      "verdicts": dict(Counter(r["verdict"] for r in rows))}, ensure_ascii=False, indent=2))
```

- [ ] **Step 4: 跑测试确认通过 + 回归**

```bash
python3 -m pytest scripts/tests/test_experiment_log.py -q     # 13 passed
python3 -m pytest scripts/tests -q 2>&1 | tail -1               # 345 passed
```

- [ ] **Step 5: 提交**

```bash
git add ts-diagnose/scripts/experiment_log.py ts-diagnose/scripts/tests/test_experiment_log.py
git commit -m "feat(scripts): experiment_log.py（下）——decide 冠军更新与四条停止规则、new-round、stop、finalize 封存终评只评一次、status

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>"
```

---

### Task 7: 结论闸规则 7（`produces_experiment_log`）

**Files:**
- Modify: `ts-diagnose/scripts/conclusion_gate.py`
- Test: `ts-diagnose/scripts/tests/test_conclusion_gate.py`（追加）

**Interfaces:**
- Produces：`IMPROVE_SECTION = "## 改进证据"`；`IMPROVE_RECEIPT_RE = re.compile(r"(keep|discard|undecided).*delta.*seeds?=\d")`；`IMPROVE_RECEIPT_REQUIRED = ("exp_id", "delta", "noise_floor_3sigma", "seeds", "verdict", "produced_by", "script_sha256")`；`check_improve(text)`。只对 frontmatter `produces_experiment_log: true` 的 playbook 生效；其余 playbook 零破坏。

- [ ] **Step 1: 追加失败测试**（文件末尾；复用文件顶部的 `setup()` 与 `GATE`）

```python
PB_IMPROVE = """---
id: improve-demo
name: i
goal: i
produces_experiment_log: true
stages:
  - id: 0
    name: 环
    done_when: {artifacts: ['champion.json']}
  - id: 1
    name: 结论
    done_when: {artifacts: ['CONCLUSION.md', 'gate_reports/conclusion_gate.json']}
---
"""

IMPROVE_GOOD = """# 结论
冠军 E002（dropout 0.1→0.05）在验证集上超基线（见 receipts/E002.json）；封存测试集终评见 final_test.json。
## 模型结构依据
absent-confirmed：无模型档案，降级为配置级改进结论。
## 改进证据
- E001 discard: hyp=F1 delta=-0.0300 noise_floor=0.0012 seeds=3 guard=regress:horizon:far
- E002 keep: hyp=F2 delta=-0.0050 noise_floor=0.0012 seeds=3 guard=ok
- final_test improved: champion=E002 delta=-0.0150 noise_floor=0.0010 seeds=3
## 证据清单
- `receipts/E001.json` — 守护退化被弃
- `receipts/E002.json` — 留下的冠军
- `experiment_log.jsonl` — 全部候选
- `champion.json` — 冠军状态
- `final_test.json` — 封存终评
"""


def _improve_receipt(tmp_path, exp_id, verdict):
    adapter = tmp_path / "adapter.py"
    adapter.write_text("print(1)\n", encoding="utf-8")
    import hashlib
    sha = hashlib.sha256(adapter.read_bytes()).hexdigest()
    (tmp_path / "receipts").mkdir(exist_ok=True)
    (tmp_path / "receipts" / f"{exp_id}.json").write_text(json.dumps([{
        "exp_id": exp_id, "hypothesis_id": "F", "delta": -0.01, "noise_floor_3sigma": 0.001, "seeds": 3,
        "verdict": verdict, "line": f"- {exp_id} {verdict}: hyp=F delta=-0.0100 noise_floor=0.0010 seeds=3 guard=ok",
        "produced_by": str(adapter), "script_sha256": sha}]), encoding="utf-8")


def _improve_setup(tmp_path, text):
    setup(tmp_path, text, with_chart=False, pb_text=PB_IMPROVE)
    _improve_receipt(tmp_path, "E001", "discard")
    _improve_receipt(tmp_path, "E002", "keep")
    for name in ("experiment_log.jsonl", "champion.json", "final_test.json"):
        (tmp_path / name).write_text("{}\n", encoding="utf-8")


def test_rule7_passes_with_full_improve_evidence(tmp_path):
    _improve_setup(tmp_path, IMPROVE_GOOD)
    r = subprocess.run([sys.executable, GATE], cwd=str(tmp_path), capture_output=True, text=True)
    assert r.returncode == 0, r.stdout + r.stderr
    assert (tmp_path / "gate_reports" / "conclusion_gate.json").exists()


def test_rule7_missing_section_or_receipt_line_fails(tmp_path):
    _improve_setup(tmp_path, IMPROVE_GOOD.replace("## 改进证据", "## 改进"))
    r = subprocess.run([sys.executable, GATE], cwd=str(tmp_path), capture_output=True, text=True)
    assert r.returncode != 0 and "改进证据" in r.stdout


def test_rule7_unlisted_receipt_or_missing_final_fails(tmp_path):
    _improve_setup(tmp_path, IMPROVE_GOOD.replace("- `receipts/E001.json` — 守护退化被弃\n", ""))
    r = subprocess.run([sys.executable, GATE], cwd=str(tmp_path), capture_output=True, text=True)
    assert r.returncode != 0 and "E001" in r.stdout
    _improve_setup(tmp_path, IMPROVE_GOOD)
    (tmp_path / "final_test.json").unlink()
    r = subprocess.run([sys.executable, GATE], cwd=str(tmp_path), capture_output=True, text=True)
    assert r.returncode != 0 and "final_test.json" in r.stdout


def test_rule7_receipt_hash_mismatch_fails(tmp_path):
    _improve_setup(tmp_path, IMPROVE_GOOD)
    (tmp_path / "adapter.py").write_text("print(2)\n", encoding="utf-8")
    r = subprocess.run([sys.executable, GATE], cwd=str(tmp_path), capture_output=True, text=True)
    assert r.returncode != 0 and "sha256" in r.stdout


def test_rule7_not_applied_to_other_playbooks(tmp_path):
    setup(tmp_path, GOOD, with_chart=True, pb_text=PB_NON_ABLATION)   # 无改进证据节也过闸
    r = subprocess.run([sys.executable, GATE], cwd=str(tmp_path), capture_output=True, text=True)
    assert r.returncode == 0, r.stdout + r.stderr
```

- [ ] **Step 2: 跑测试确认失败**（前四项失败，第五项通过）

- [ ] **Step 3: 改 `conclusion_gate.py`**

常量区（`EVIDENCE_SECTION` 之后）加：

```python
IMPROVE_SECTION = "## 改进证据"
IMPROVE_RECEIPT_RE = re.compile(r"(keep|discard|undecided).*delta.*seeds?=\d")
IMPROVE_RECEIPT_REQUIRED = ("exp_id", "delta", "noise_floor_3sigma", "seeds", "verdict",
                            "produced_by", "script_sha256")
```

`check_evidence_list` 之后加：

```python
def check_improve(text):
    """规则 7 改进环:「## 改进证据」节 + 每张 E receipt 溯源 + 封存终评被引用 + 证据清单列全。"""
    if IMPROVE_SECTION not in text:
        fail(f"缺「{IMPROVE_SECTION}」节——改进结论必须贴 keep/discard/undecided 的 receipt 行")
    sec = text.split(IMPROVE_SECTION, 1)[1].split("\n## ", 1)[0]
    if not IMPROVE_RECEIPT_RE.search(sec):
        fail(f"「{IMPROVE_SECTION}」节无 receipt 行（须含 keep/discard/undecided + delta + seeds=N）")
    receipts = sorted(glob.glob("receipts/E*.json"))
    for rp in receipts:
        rec = _last_entry(rp)
        if rec is None:
            fail(f"{rp} 为空或不是合法 receipt")
        missing = [k for k in IMPROVE_RECEIPT_REQUIRED if rec.get(k) in (None, "")]
        if missing:
            fail(f"{rp} 缺必填字段 {missing}——receipt 必须由 improve_verdict.py --out 生成")
        if not (isinstance(rec["seeds"], int) and rec["seeds"] >= 3):
            fail(f"{rp} seeds={rec['seeds']!r}——改进判定必须 ≥3 种子")
        if not os.path.exists(rec["produced_by"]):
            fail(f"{rp} 的 produced_by 指向不存在的脚本:{rec['produced_by']}")
        if sha256_of(rec["produced_by"]) != rec["script_sha256"]:
            fail(f"{rp} 的 script_sha256 与 {rec['produced_by']} 当前内容不符——适配器在出回执后被改过")
    if not os.path.exists("final_test.json"):
        fail("无 final_test.json——写结论前先跑 experiment_log.py finalize（封存测试集只评一次）")
    if "final_test.json" not in text:
        fail("结论未引用 final_test.json——封存测试集的终评必须写进结论")
    if EVIDENCE_SECTION not in text:
        fail(f"缺「{EVIDENCE_SECTION}」节")
    esec = text.split(EVIDENCE_SECTION, 1)[1].split("\n## ", 1)[0]
    cited = re.findall(r"`([^`\s]+)`", esec)
    must = receipts + [p for p in ("experiment_log.jsonl", "champion.json", "final_test.json") if os.path.exists(p)]
    unlisted = [p for p in must if p not in cited]
    if unlisted:
        fail(f"证据清单漏列:{unlisted}——每张 E receipt(含被弃的)、日志、冠军、终评都必须列出")
```

`main()` 里规则 5+6 之后、`os.makedirs("gate_reports")` 之前加：

```python
    # 规则 7：改进环（只对声明 produces_experiment_log: true 的 playbook 生效——model-improve）
    if fm.get("produces_experiment_log"):
        check_improve(text)
```

- [ ] **Step 4: 跑测试确认通过 + 回归**

```bash
python3 -m pytest scripts/tests/test_conclusion_gate.py -q      # 全绿
python3 -m pytest scripts/tests -q 2>&1 | tail -1                # 350 passed
```

- [ ] **Step 5: 提交**

```bash
git add ts-diagnose/scripts/conclusion_gate.py ts-diagnose/scripts/tests/test_conclusion_gate.py
git commit -m "feat(gate): 结论闸规则 7——改进证据节、E receipt 溯源、封存终评必引、证据清单列全（仅 produces_experiment_log）

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>"
```

---

### Task 8: `model-improve` 剧本 + 金标准 + 路由/文档/测试表同步

**Files:**
- Create: `ts-diagnose/playbooks/model-improve/playbook.md`
- Create: `ts-diagnose/playbooks/model-improve/golden/make_golden.py`、`golden/fake_round.json`、`golden/manifest.json`、`golden/reference/improve_verdict_ref.py`
- Modify: `ts-diagnose/SKILL.md`（路由表加一行、12→13、description 加一条触发短语）
- Modify: `README.md`（仓库根：12→13、分析层表加一行）
- Modify: `ts-diagnose/references/engine-core.md`（假设验证循环节加「改进环」三行）
- Modify: `ts-diagnose/scripts/tests/test_routing.py`（`ALL_PLAYBOOK_IDS` 加 `model-improve`）
- Modify: `ts-diagnose/scripts/tests/test_products.py`（`REAL_UPSTREAM` 加 `"model-improve": {"model_profile": False}`）
- Modify: `ts-diagnose/CHANGELOG.md`

**Interfaces:**
- Consumes：Task 1 的 `{round}` / `json:`；Task 4–6 的三支脚本 CLI；Task 7 的规则 7；Task 9 的卡片名 `model-improve-worker`；Task 10 的 `workflows/ts-train-batch.js`（剧本先写调用方式，脚本 Task 10 落地）。
- Produces：playbook id `model-improve`；frontmatter `produces_experiment_log: true`；问题 id `evaluator-adapter / improve-target / improve-budget / guard-slices / candidate-source`。

- [ ] **Step 1: 写金标准（先写，后面 test_gen_gate 自动收）**

`golden/make_golden.py`：

```python
#!/usr/bin/env python3
"""确定性金标准：一轮四条候选，答案已知——E001 keep / E002 discard（更差）/ E003 undecided（噪声内）
/ E004 discard（整体变好但守护切片 far 退化）。零随机；改期望先改这里并重跑 pytest。"""
import json
import os

HERE = os.path.dirname(os.path.abspath(__file__))
DOC = {"champion_mean": 0.2000, "noise_floor_3sigma": 0.0060,
       "candidates": [
           {"exp_id": "E001", "hypothesis_id": "F1", "per_seed": [0.180, 0.181, 0.179]},
           {"exp_id": "E002", "hypothesis_id": "F2", "per_seed": [0.221, 0.220, 0.219]},
           {"exp_id": "E003", "hypothesis_id": "F3", "per_seed": [0.199, 0.198, 0.200]},
           {"exp_id": "E004", "hypothesis_id": "F4", "per_seed": [0.178, 0.179, 0.180],
            "guards": {"horizon:far": {"per_seed": [0.30, 0.31, 0.29], "champion_mean": 0.26,
                                       "noise_floor": 0.006}}}]}

if __name__ == "__main__":
    with open(os.path.join(HERE, "fake_round.json"), "w", encoding="utf-8") as f:
        json.dump(DOC, f, ensure_ascii=False, indent=2)
    print("✓ fake_round.json")
```

跑 `python3 playbooks/model-improve/golden/make_golden.py` 生成 `fake_round.json`。

`golden/reference/improve_verdict_ref.py`：

```python
#!/usr/bin/env python3
"""金标准闸对象：直接调用生产脚本 scripts/improve_verdict.py 的 main()——同一份代码，不复制逻辑。"""
import os
import sys

ENGINE_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(
    os.path.dirname(os.path.abspath(__file__))))))
sys.path.insert(0, os.path.join(ENGINE_DIR, "scripts"))

import improve_verdict  # noqa: E402

if __name__ == "__main__":
    improve_verdict.main()
```

`golden/manifest.json`：

```json
{
  "playbook": "model-improve",
  "note": "本 playbook 的 Stage 0/2 依赖真实训练入口（评估器适配器）与 subagent，Stage 1/3/4 是 experiment_log.py 的状态机（scripts/tests/test_experiment_log.py 直接覆盖 init/candidates/append/decide/new-round/stop/finalize 与四条停止规则）。可确定性验证、且是每条候选留弃核心的是改进判定：fake_round.json 植入四条候选——E001 整体变好超噪声底（keep）、E002 变差（discard）、E003 落噪声底内（undecided）、E004 整体变好但守护切片 far 退化 +0.04 ≥ 切片噪声底（discard, guard=regress）。改期望先改 make_golden.py 并重跑 pytest。",
  "planted": {"champion_mean": 0.2, "noise_floor_3sigma": 0.006,
              "E001_delta": -0.02, "E002_delta": 0.02, "E003_delta": -0.001, "E004_far_delta": 0.04},
  "stages": {
    "2": {
      "desc": "改进判定四态：keep / discard(更差) / undecided(噪声内) / discard(守护退化)",
      "inputs": ["fake_round.json"],
      "args": ["--round", "fake_round.json", "--out", "verdicts.json"],
      "expect": [
        {"file": "verdicts.json", "path": "verdicts.E001.verdict", "op": "eq", "value": "keep"},
        {"file": "verdicts.json", "path": "verdicts.E001.delta", "op": "between", "value": [-0.0201, -0.0199]},
        {"file": "verdicts.json", "path": "verdicts.E002.verdict", "op": "eq", "value": "discard"},
        {"file": "verdicts.json", "path": "verdicts.E003.verdict", "op": "eq", "value": "undecided"},
        {"file": "verdicts.json", "path": "verdicts.E004.verdict", "op": "eq", "value": "discard"},
        {"file": "verdicts.json", "path": "verdicts.E004.guard.horizon:far.regress", "op": "eq", "value": true},
        {"file": "verdicts.json", "path": "verdicts.E004.line", "op": "contains", "value": "guard=regress:horizon:far"}
      ],
      "reference": "reference/improve_verdict_ref.py"
    }
  }
}
```

注意 `path` 用点分隔，切片 id 里的冒号原样保留（`gen_gate` 的点路径按 `.` 切）。

- [ ] **Step 2: 写剧本** `ts-diagnose/playbooks/model-improve/playbook.md`

```markdown
---
id: model-improve
name: 改进环（按轮批跑）
goal: 把假设账本里的改进假设（或素版的可干预开关）排成候选，按轮批跑 ≥3 种子重训，与冠军比较后留弃，停止规则由代码守，收敛后封存测试集只评一次，结论过闸产一次
produces_experiment_log: true
upstream:
  - product: model_profile
    required: false
stages:
  - id: 0
    name: 冻结评估器与冠军基线
    done_when:
      artifacts: ["evaluator.json", "champion.json"]
    prereqs:
      - desc: 评估器适配器已定
        check: "question:evaluator-adapter"
      - desc: 改进目标与起点配置已定
        check: "question:improve-target"
      - desc: 预算已定
        check: "question:improve-budget"
      - desc: 守护切片已定
        check: "question:guard-slices"
    pause_after: true
    subagent_ok: true
  - id: 1
    name: 候选队列
    done_when:
      artifacts: ["rounds/round_{round}/candidates.json"]
    prereqs:
      - desc: 冠军基线已定
        check: "stage:0"
      - desc: 候选来源已定
        check: "question:candidate-source"
  - id: 2
    name: 跑一轮
    done_when:
      artifacts: ["rounds/round_{round}/batch_result.json"]
    prereqs:
      - desc: 本轮候选已排
        check: "stage:1"
      - desc: 用户已确认本轮训练次数（candidates.json.confirmed）
        check: "json:rounds/round_{round}/candidates.json:confirmed"
    subagent_ok: true
  - id: 3
    name: 轮次裁决
    done_when:
      artifacts: ["rounds/round_{round}/summary.json"]
    prereqs:
      - desc: 本轮批结果已落盘
        check: "stage:2"
    pause_after: true
  - id: 4
    name: 结论落笔
    done_when:
      artifacts: ["final_test.json", "CONCLUSION.md", "gate_reports/conclusion_gate.json"]
    prereqs:
      - desc: 已收敛（预算耗尽 / 轮数封顶 / 连续无 keep / 用户 stop）
        check: "json:champion.json:converged"
materials:
  required: []
  optional: [model_code, experiment_config, checkpoint]
questions:
  - id: evaluator-adapter
    stage: 0
    ask: "训练入口适配器脚本的绝对路径？（须实现 references/evaluator-contract.md：--config/--seed/--out，产 metrics.json 与 sealed/test_metrics.json）"
    why: "没有一条命令的评估器就没有环"
    default: null
  - id: improve-target
    stage: 0
    ask: "改进哪个模型？起点配置 base_config 是什么？基线 3 种子用已有产物还是新跑？"
    why: "冠军 E000 与噪声底由它定；候选只接 fix.target_model 相同的条目"
    default: null
  - id: improve-budget
    stage: 0
    ask: "预算：最多几次训练、最多几轮、每轮最多几条候选？"
    why: "停止规则由 experiment_log.py 按这三个数守"
    default: "30 次 / 3 轮 / 每轮 10 条"
  - id: guard-slices
    stage: 0
    ask: "守护切片：哪些切片不许退化？（从 evaluator.json.slices 里选）"
    why: "整体变好但某切片变坏的候选必须弃"
    default: "全部 horizon:* 切片"
  - id: candidate-source
    stage: 1
    ask: "候选来源：假设账本路径（取 kind=improvement 的条目），还是素版（model_profile 的 ablation_switches）？"
    why: "有诊断的候选优先；素版只在没有账本时用"
    default: null
---

# model-improve：改进环（按轮批跑）

## 1. 问题框定与首要陷阱

本 playbook 回答「改了会不会好」，不回答「为什么」。「为什么」归验证主脊 `architecture-attribution`，本 playbook 只把它的账本里 `kind: improvement` 的条目拿来试。

首要陷阱：**单次运行就留下改法**。keep 只认三种子均值超冠军且超噪声底 3σ，再加守护切片无退化；一次运行的好成绩不是证据。

第二陷阱：**反复对同一份验证集选择会过拟合**。环内只看验证集指标；测试集在适配器里封存，`experiment_log.py finalize` 在收敛后只开封一次，结论必须报它。

第三陷阱：**崩溃当成推翻**。种子 crash/timeout 的候选记 `untested`，账本状态 `untested` 带原因，不进 refuted。

第四陷阱：**绕过预算再来一轮**。轮数、训练次数、连续无 keep 三条停止规则由 `experiment_log.py decide` 判，收敛后 `new-round` 会拒绝；要多跑只能重新 init 一个新的工作目录并在结论里说明。

## 2. 逐阶段菜谱

引擎目录 `<ENGINE>`；三支脚本：`<ENGINE>/scripts/evaluator.py`、`<ENGINE>/scripts/improve_verdict.py`、`<ENGINE>/scripts/experiment_log.py`。评估器契约见 `<ENGINE>/references/evaluator-contract.md`。

### Stage 0 冻结评估器与冠军基线

输入：四个问题的答案；可选 `model_profile` 的 `ablation_switches`。

菜谱：
1. 按答案写 `evaluator.json`（adapter / base_config / knobs / metric / slices / seeds / time_limit_s），然后跑 `python3 "<ENGINE>/scripts/evaluator.py" validate evaluator.json`，不过不往下。
2. 基线 3 种子：派 `model-improve-worker`（task=baseline，输入：工作目录、引擎目录、`evaluator.json` 路径、`exp_id=E000`）。它跑 `evaluator.py run-seeds --config-diff '{}' --out-root runs/E000`，回 `runs/E000/summary.json` 路径。用户答「用已有产物」时，主 agent 按契约把已有 3 种子产物整理成同结构的 `runs/E000/summary.json`（per_seed / slices_per_seed / metrics_dirs / run_status，metrics_dirs 里必须有 `sealed/test_metrics.json`）。
3. `python3 "<ENGINE>/scripts/experiment_log.py" init --evaluator evaluator.json --baseline runs/E000/summary.json --max-trainings <N> --max-rounds <R> --max-per-round <K>`。

done：`evaluator.json` + `champion.json` 落盘 → **pause_after 停顿**（§4）。

### Stage 1 候选队列

输入：`candidate-source` 的答案。

菜谱：
1. 账本来源：`python3 "<ENGINE>/scripts/experiment_log.py" candidates --ledger <账本路径> --target <improve-target 的模型名>`。只取 `kind=improvement`、`status=pending`、`fix.target_model` 相同的条目，按其 `derived_from` 父假设的 `discriminating_power` 降序。
2. 素版来源：把 `model_profile` 的 `ablation_switches` 存成 JSON，跑 `candidates --switches <该 JSON> --target <模型名> --guard <守护切片,逗号分隔>`。`config-flag` 先于 `code-stub`，`not-intervenable` 不进队。
3. 两种来源可以同时给。已跑过的 `config_diff` 自动去重；超出每轮上限或剩余预算的候选进 `deferred`。
4. 向用户汇报本轮候选清单与训练次数（候选数 × 种子数），用户说开跑后执行 `experiment_log.py confirm-round`。候选为空时不确认，改走 `stop --reason no_candidates`。

第 2 轮起的候选：先看上一轮 `summary.json` 的 `deferred`；需要新假设时回生成器（重跑 `model-comparison`，配对写「新冠军 vs 旧冠军」，新条目 `provenance: post-hoc`）。

done：`rounds/round_{round}/candidates.json` 落盘（confirmed 由用户确认后置 true）。

### Stage 2 跑一轮

输入：`rounds/round_{round}/candidates.json`（confirmed=true）。

菜谱：
1. 每条候选一个 worker 任务（task=candidate，输入：工作目录、引擎目录、exp_id、hypothesis_id、config_diff、guard_slices）。Claude Code 下调用 Workflow 工具：`scriptPath="<ENGINE>/workflows/ts-train-batch.js"`，`args={"engine": "<ENGINE>", "workdir": "<工作目录>", "agent_type": "model-improve-worker", "task": "candidate", "candidates": <candidates.json 的 candidates 数组>, "chunk": 4}`；本 playbook 写明的这条调用即 Workflow 的用户授权。Workflow 不可用时，主 agent 在一条消息里并行派多张 `model-improve-worker` 卡（每张一条候选）。
2. 把返回的 `{results, failed}` 原样写成 `rounds/round_{round}/batch_result.json`。
3. `python3 "<ENGINE>/scripts/experiment_log.py" append --batch rounds/round_{round}/batch_result.json`。append 拒收：未确认的轮、不在本轮候选里的 exp_id、重复 exp_id、结果里任何含 `test`/`sealed` 的键名。
4. 每条候选的判定写回账本：keep → 该 F 条目 `status: confirmed`、`receipt: receipts/E<id>.json`；discard → `status: refuted`、`kill_receipt` 同路径；undecided → `undecided`；crash/timeout → `untested` + `untested_reason`。改完跑 `python3 "<ENGINE>/scripts/hypothesis_ledger.py" <账本>`。

done：`rounds/round_{round}/batch_result.json` 落盘且 append 成功。

### Stage 3 轮次裁决

菜谱：`python3 "<ENGINE>/scripts/experiment_log.py" decide`。它在本轮 keep 里取均值最小者为新冠军、累加已用训练次数、判收敛，写 `rounds/round_{round}/summary.json`。

done：`summary.json` 落盘 → **pause_after 停顿**（§4）。用户选择：
- 再来一轮 → `python3 "<ENGINE>/scripts/experiment_log.py" new-round`，然后回 Stage 1（orient 会自动指向第 N+1 轮的候选阶段）。
- 到此为止 → `python3 "<ENGINE>/scripts/experiment_log.py" stop --reason "<用户原话>"`，进 Stage 4。
- decide 已报收敛 → 直接进 Stage 4，`new-round` 会拒绝。

### Stage 4 结论落笔

菜谱：
1. `python3 "<ENGINE>/scripts/experiment_log.py" finalize`——读基线与冠军各种子的 `sealed/test_metrics.json`，写 `final_test.json`。只跑一次。
2. `python3 "<ENGINE>/scripts/provenance.py" --code <适配器路径> --data evaluator.json experiment_log.jsonl --out provenance.json`。
3. 按 §6 模板写 CONCLUSION.md，然后 `python3 "<ENGINE>/scripts/conclusion_gate.py"`。规则 7 检查：「## 改进证据」节含 receipt 行、每张 `receipts/E*.json` 溯源块与适配器 sha 相符、`final_test.json` 存在且被引用、证据清单列全 E receipt / 日志 / 冠军 / 终评。

done：`final_test.json` + `CONCLUSION.md` + `gate_reports/conclusion_gate.json`。

## 3. 证据升级规则

- 候选 → keep：三种子均值低于冠军且 |delta| ≥ 冠军噪声底 3σ，且每个守护切片的 delta 不满足「>0 且 ≥ 该切片噪声底」（门 1 稳健性）。
- keep → 冠军：本轮 keep 里均值最小者（门 2 假设登记先于看数：候选在 confirm-round 前已登记，config_diff 不许事后改）。
- 冠军 → 「改进成立」：`final_test.json.verdict == improved`（封存测试集上超基线且超测试集噪声底）。verdict 为 not_distinguishable 时结论只许写「验证集上改进、测试集上不可分」（门 3 反驳门）。
- 素版候选（无假设）留下的冠军，结论只许写「配置级改进」，不写机制。

## 4. 停顿点与汇报

Stage 0 完成：报基线均值、三种子 std、噪声底 3σ、切片均值与切片噪声底、预算三个数、守护切片；请用户确认候选来源。

Stage 3 完成：报 `summary.json` 的 counts、每条 receipt 行、守护退化名单、untested 名单与原因、冠军是否更换与 delta、已用/总预算、是否收敛与原因、deferred 数量；请用户选「再来一轮 / 到此为止」。收敛时只报结果，不问。

## 5. subagent 拆分建议

Stage 0 基线与 Stage 2 每条候选都派 `model-improve-worker`（mode worker），一次一条任务，输出目录 `runs/<exp_id>/`，receipt `receipts/<exp_id>.json`，天然防竞态。Stage 1/3/4 归主 agent，不拆。Claude Code 下 Stage 2 用 `<ENGINE>/workflows/ts-train-batch.js` 批量派卡。

## 6. 结论模板与本 playbook 特有的反驳门条目

```
# 结论
一句话：冠军 <exp_id>（<config_diff_vs_baseline>）验证集 <metric> 从 <基线均值> 到 <冠军均值>；封存测试集终评 <verdict>（见 final_test.json）。
## 模型结构依据
<有账本：引用 F 条目的 derived_from H-id；素版：absent-confirmed，降级为配置级改进结论>
## 改进证据
<summary.json 里每条 receipt_line 原样贴，含被弃的；末尾贴 final_test.json 的 line>
## 反驳排除
- 单次运行误判：每条候选 ≥3 种子，噪声底 3σ 见 champion.json
- 验证集过拟合：测试集封存，final_test.json 只评一次
- 守护切片：退化候选逐条列出（summary.guard_regress）
- 未测候选：untested 名单与原因，不计入推翻
## 已知缺口
<deferred 未跑的候选；undecided 的候选；收敛原因>
## 证据清单
- `receipts/E001.json` — …（每张都列，含 discard/undecided）
- `experiment_log.jsonl` — 全部候选
- `champion.json` — 冠军与预算
- `final_test.json` — 封存终评
```

反驳门条目：①冠军领先是否只靠一个种子（逐种子符号都同向才写「稳定」）；②守护切片里有没有噪声底为 0 的切片（三种子完全相同）——有则该切片的守护判定标「噪声底不可用」；③`final_test` 为 worse 时结论必须写「验证集改进未迁移到测试集」，不许只报验证集。

## 7. 材料降级说明

本 playbook 不需要 predict/truth 长表；`model_code / experiment_config / checkpoint` 只影响候选来源：三者都 absent-confirmed 且无账本 → 无候选可排，Stage 1 止步并向用户说明。`model_profile` declined → 素版候选不可用，只接账本条目。

## 8. chartbook 覆盖声明

本 playbook 读评估器产的指标 JSON，不读长表，全部 recipe 结构性不适用：bad-window-clustering、baseline-skill、cross-dim-stability、error-acf、error-breakdown、feature-error-conditional、feature-regime-error、feature-trend-overlay、global-attribution、good-bad-contrast、horizon-degradation、horizon-error-quantiles、intraday-profile、local-waterfall、lookback-decay、model-error-correlation、model-rank-significance、oracle-gap、pp-calibration、revision-stability、rolling-stability、theil-decomposition、time-shift-diagnosis、train-test-drift、true-vs-pred-scatter、worst-points、worst-slice-compare、y-vs-feature-mapping——跳过理由相同：输入不是 setup 长表。轮次边界要看「新冠军 vs 旧冠军」的切片版图时，走 `model-comparison`。
```

- [ ] **Step 3: 路由与文档同步**

`ts-diagnose/SKILL.md`：
- 第 14 行 `12 个 playbook` → `13 个 playbook`。
- 路由表 `architecture-attribution` 行之后加：`| 已有改进假设或可改的配置开关，想按轮试改法把指标提上去、留好弃坏、代码守预算 | \`model-improve\` |`
- 「升级条件」段末尾加一句：`干预验证后要把指标提上去，转 \`model-improve\`。`
- description 末尾「命中后按本文件路由表转发」之前加 `按轮试改法提升模型指标、自动留好弃坏；`。
- 改完确认 ≤60 行：`wc -l SKILL.md`。

`README.md`（仓库根）：`12 个 playbook` 三处改 `13 个 playbook`；`（分层机制已全量落地：4 生产者 + 8 分析 playbook…）` 改 `4 生产者 + 9 分析 playbook`；分析层表 `architecture-attribution` 行之后加：

```
| `model-improve` | 改进环：账本里的改进假设（或可干预开关）排成候选，按轮批跑 ≥3 种子重训、与冠军比、留好弃坏；预算/轮数/连续无 keep 三条停止规则由 `experiment_log.py` 守；测试集封存只在收敛后评一次；Claude Code 下一轮候选经 `workflows/ts-train-batch.js` 并行派 `model-improve-worker` |
```

`ts-diagnose/references/engine-core.md` 「假设验证循环」节末尾加：

```
**改进环**（`model-improve`）：账本 `kind: improvement` 条目 → 候选按轮批跑（每条派 `model-improve-worker`，
≥3 种子）→ `improve_verdict` 判 keep/discard/undecided（超冠军且守护切片不退化）→ `experiment_log.py decide`
更新冠军并判收敛（预算耗尽 / 轮数封顶 / 连续两轮无 keep / 用户 stop）→ 收敛后 `finalize` 开封测试集一次
→ 结论过 `conclusion_gate` 规则 7。crash/timeout 记 `untested`，不算 refuted。
```

改完跑 `python3 -m pytest scripts/tests/test_engine_core_budget.py -q`。

`ts-diagnose/scripts/tests/test_routing.py` 的 `ALL_PLAYBOOK_IDS` 元组末尾加 `"model-improve",`。

`ts-diagnose/scripts/tests/test_products.py` 的 `REAL_UPSTREAM` 加一行：`"model-improve": {"model_profile": False},`。

`ts-diagnose/CHANGELOG.md` 顶部加一行：

```
- 2026-09-07 | 改进环 + Phase 4：新 playbook model-improve（按轮批跑候选、冠军、四条停止规则、封存终评）、scripts/{evaluator,improve_verdict,experiment_log}.py、账本 kind=improvement/untested、conclusion_gate 规则 7、engine {round} 占位 + json: DSL、model-improve-worker 卡、workflows/ts-train-batch.js、eval-cases/adapters/lsf_mini_adapter.py + Weather 冒烟 | 用户："我想做一个 auto research 的框架……发现能改进的地方，然后我们去改进，然后进步" | 解释环只到组件为止；改进环把「改了会不会好」做成代码守规则的循环，与消融验证共用 worker 形态，第一条链只接 model-comparison
```

- [ ] **Step 4: 跑守卫**

```bash
python3 -m pytest scripts/tests/test_layering.py scripts/tests/test_routing.py scripts/tests/test_products.py \
        scripts/tests/test_gen_gate.py scripts/tests/test_engine_core_budget.py -q
python3 -m pytest scripts/tests -q 2>&1 | tail -1      # 全绿（数量随 gen_gate 参数化增加）
python3 -m pytest chartbook/tests -q 2>&1 | tail -1    # 162 passed
```

`test_layer0_no_method_vocab` 报错时只改 SKILL.md 新加那一行的措辞，不动其他行。

- [ ] **Step 5: 提交**

```bash
git add ts-diagnose/playbooks/model-improve ts-diagnose/SKILL.md README.md \
        ts-diagnose/references/engine-core.md ts-diagnose/scripts/tests/test_routing.py \
        ts-diagnose/scripts/tests/test_products.py ts-diagnose/CHANGELOG.md
git commit -m "feat(playbook): model-improve 改进环剧本（五段、{round} 产物、json: 收敛门）+ golden 四态判定 + 路由/README/engine-core 同步

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>"
```

---

### Task 9: 卡片 `model-improve-worker` + 两处契约/剧本补充

**Files:**
- Create: `ts-diagnose/agents/model-improve-worker.md`
- Modify: `ts-diagnose/agents/architecture-attribution-worker.md`（输出契约加 `run_status`、`metrics_dirs`）
- Modify: `ts-diagnose/playbooks/model-comparison/playbook.md`（Stage 2 加「改进假设」段）
- Modify: `ts-diagnose/playbooks/architecture-attribution/playbook.md`（§5 加一句 workflow）
- Modify: `ts-diagnose/INSTALL.md`、`README.md`、`ts-diagnose/agents/_agent-spec.md`（卡片计数 13→14，只改出现的地方）

**Interfaces:**
- Produces：卡片名 `model-improve-worker`（mode worker，serves_stages [0, 2]）；输出契约 JSON（见 Step 1），Task 10 的 workflow schema 与 Task 5 的 `append` 都按它读。
- architecture-attribution-worker 契约新增字段：`"run_status": ["ok", "ok", "ok"]`、`"metrics_dirs": ["runs/H3/seed_7", ...]`。

- [ ] **Step 1: 写卡片** `ts-diagnose/agents/model-improve-worker.md`（正文非空行 ≤80；六节标题必须含「你是谁 / 输入 / 步骤 / 红线 / 输出契约 / 停顿」）

```markdown
---
name: model-improve-worker
description: 改进环的重训工——一次只跑一条「配置差异 × ≥3 种子重训 + 评估 + 与冠军比较」，回一张 receipt
mode: worker
playbook: model-improve
compute_stages: "scripts"
serves_stages: [0, 2]
tools: [Bash, Read, Write]
model: sonnet
---

## 你是谁

一句话身份：只做「按给定配置差异重训 ≥3 个种子、评估、和冠军比」的计算，不问用户、不裁决冠军、不改账本。

## 输入（主 agent 派发时给你）

- 任务类型 task：`baseline`（Stage 0，config_diff 为空，exp_id=E000）或 `candidate`（Stage 2 单条候选）
- 工作目录：`<workdir>`（含 `evaluator.json`；candidate 任务还含 `champion.json`）
- 引擎目录：`<ENGINE>`（绝对路径，含 scripts/ playbooks/ references/）
- candidate 任务附：exp_id / hypothesis_id / config_diff（JSON 对象）/ guard_slices（切片 id 列表）

## 步骤（去菜谱）

按 `playbooks/model-improve/playbook.md` 的 Stage 0 第 2 步（task=baseline）或 Stage 2 第 1 步（task=candidate）执行；契约见 `<ENGINE>/references/evaluator-contract.md`。
1. `python3 "<ENGINE>/scripts/evaluator.py" run-seeds --evaluator evaluator.json --config-diff '<config_diff JSON>' --out-root runs/<exp_id>`，记起止时刻。退出码 2 表示有种子非 ok：读 `runs/<exp_id>/summary.json` 的 `run_status`。
2. candidate 任务且全部种子 ok：`python3 "<ENGINE>/scripts/improve_verdict.py" --exp-id <exp_id> --hypothesis-id <hypothesis_id> --summary runs/<exp_id>/summary.json --champion champion.json --guard <guard_slices 逗号分隔> --config-diff '<config_diff JSON>' --script <evaluator.json 里的 adapter 路径> --t-start <ISO> --t-end <ISO> --selftest "<一句话：summary 种子数与 evaluator.json.seeds 一致>" --out receipts/<exp_id>.json`。
3. 有种子非 ok：不跑 improve_verdict，回 BLOCKED，`run_status` 照 summary 填，`blocked_reason` 写种子号与 metrics.json 的 error 首行。
阶段与 prereq 由主 agent 掌握；本卡不跑 `python3 "<ENGINE>/scripts/orient.py"`（阶段状态单写者是主 agent）。

## 红线

- 单变量：只用派发给你的 config_diff；不加、不改、不"顺手"调别的参数。
- 不读 `runs/**/sealed/`，不把 sealed 里的任何数字写进输出；不读 pred/true 数组、训练日志进上下文。
- 只写 `runs/<exp_id>/**` 与 `receipts/<exp_id>.json`；不碰 champion.json / experiment_log.jsonl / rounds/ / hypothesis_ledger.json / PROGRESS.md / FINDINGS.md / diagnose_*.json。
- 不问用户：缺 evaluator.json、champion.json、config_diff → NEED_INFO；训练崩溃或超时 → BLOCKED 带种子号与一句原因，不带日志。
- 不判「该留还是该弃」以外的任何结论；不再派 subagent；一次只做一条任务。

## 输出契约

你的 final message **就是**下面这个 JSON：

```json
{
  "status": "COMPUTE_DONE | NEED_INFO | BLOCKED",
  "task": "candidate",
  "exp_id": "E003",
  "hypothesis_id": "F1",
  "receipt_line": "- E003 keep: hyp=F1 delta=-0.0123 noise_floor=0.0154 seeds=3 guard=ok",
  "receipt_file": "receipts/E003.json",
  "config_diff": {"tsmixer_no_channel_mix": true},
  "per_seed": [0.1541, 0.1552, 0.1538],
  "mean": 0.1544, "std": 0.0007,
  "run_status": ["ok", "ok", "ok"],
  "metrics_dirs": ["runs/E003/seed_7", "runs/E003/seed_1337", "runs/E003/seed_2021"],
  "slices_per_seed": [{"horizon:near": 0.12, "horizon:mid": 0.15, "horizon:far": 0.19}],
  "summary_file": "runs/E003/summary.json",
  "need_info": [],
  "blocked_reason": ""
}
```
- baseline 任务：`receipt_line / receipt_file` 留空，其余照 summary.json 填。
- `slices_per_seed` 每种子一个对象，顺序与 `metrics_dirs` 一致。

## 停顿/交回

一条任务跑完即返回；主 agent 把结果写进 `rounds/round_N/batch_result.json`，用 `experiment_log.py append` 入日志、`decide` 裁决。
```

- [ ] **Step 2: 改 architecture-attribution-worker 契约**

「输出契约」JSON 里 `"instability_note": "",` 之后加两行：

```
  "run_status": ["ok", "ok", "ok"],
  "metrics_dirs": ["runs/H3/seed_7", "runs/H3/seed_1337", "runs/H3/seed_2021"],
```

「步骤」节 intervention 一条末尾加一句：`每个种子的产物目录记进 metrics_dirs，种子状态记 run_status（ok|crash|timeout）；某种子非 ok → 回 BLOCKED。`

- [ ] **Step 3: model-comparison Stage 2 加「改进假设」段**

在「**切片认领规则（硬规则）**」段之后、「Stage 2 已因 `model_code` 解锁、但 `model_profile` declined 时」之前插入：

```
**改进假设（可选，`kind: "improvement"`）**：对每条 component 的 switch 是 `config-flag` 或 `code-stub` 的机理假设，若它的 `falsifiable_pred` 蕴含「改该组件能让某个模型的口径指标变好」，同步登记一条 `F<n>`：`kind: "improvement"`、`derived_from: "H<n>"`、`fix: {target_model, config_diff, predicted_gain, guard_slices}`——`config_diff` 是评估器 knob 名到取值的对象（如 `{"tsmixer_no_channel_mix": true}`），`predicted_gain` 写方向与相对噪声底的幅度，`guard_slices` 默认取 `slice_map` 里 `target_model` 占优的全部切片；其余字段同机理假设，`status: "pending"`、`provenance: "pre-registered"`、`kill_receipt: null`、`receipt: null`。F 条目不进验证主脊的判别力排序，由 `model-improve` 消费；账本仍须过 `hypothesis_ledger.py`。
```

- [ ] **Step 4: architecture-attribution §5 加一句**

「## 5. subagent 拆分建议」节末尾加：`Claude Code 下 Stage 3 的一轮干预可调 workflow：Workflow 工具 \`scriptPath="<ENGINE>/workflows/ts-train-batch.js"\`，\`args={"engine", "workdir", "agent_type": "architecture-attribution-worker", "task": "intervention", "candidates": <intervention_plan 里未执行且无 skipped_reason 的条目>}\`；返回的 results 逐条复核后再更新账本。`

- [ ] **Step 5: 卡片计数**

```bash
grep -rn "13 张\|13 个链接\|13 个" ts-diagnose/INSTALL.md README.md ts-diagnose/agents/_agent-spec.md ts-diagnose/references/engine-core.md
```
把指卡片数量的 `13` 改成 `14`（只改指卡片的；指 playbook 的已在 Task 8 改）。

- [ ] **Step 6: 跑守卫**

```bash
python3 -m pytest scripts/tests/test_cards.py scripts/tests/test_layering.py scripts/tests/test_engine_core_budget.py -q
python3 -m pytest scripts/tests -q 2>&1 | tail -1
```

- [ ] **Step 7: 提交**

```bash
git add ts-diagnose/agents/model-improve-worker.md ts-diagnose/agents/architecture-attribution-worker.md \
        ts-diagnose/playbooks/model-comparison/playbook.md ts-diagnose/playbooks/architecture-attribution/playbook.md \
        ts-diagnose/INSTALL.md README.md ts-diagnose/agents/_agent-spec.md
git commit -m "feat(agents): model-improve-worker 卡（run-seeds + improve_verdict，一次一条）；worker 契约加 run_status/metrics_dirs；model-comparison 登记 F 改进假设；architecture-attribution §5 提 workflow

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>"
```

---

### Task 10: Workflow `ts-train-batch.js` + 静态测试 + INSTALL 说明

**Files:**
- Create: `ts-diagnose/workflows/ts-train-batch.js`
- Test: `ts-diagnose/scripts/tests/test_workflows.py`
- Modify: `ts-diagnose/INSTALL.md`（安装项加 workflow 一句）

**Interfaces:**
- `args = {engine, workdir, agent_type, task, candidates: [{exp_id?, hypothesis_id?, config_diff?, guard_slices?, ...}], chunk?}`；返回 `{results: [<worker JSON>|占位 BLOCKED], failed: [id...]}`。
- 调用方式：`Workflow({scriptPath: "<ENGINE>/workflows/ts-train-batch.js", args})`；`install.sh` 已把 `workflows/*.js` 链接到 `~/.claude/workflows/`，按名字 `ts-train-batch` 调用是否可用以实测为准，剧本一律写 scriptPath。

- [ ] **Step 1: 写失败测试** `ts-diagnose/scripts/tests/test_workflows.py`

```python
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


@pytest.mark.skipif(shutil.which("node") is None, reason="无 node")
@pytest.mark.parametrize("path", FILES, ids=[os.path.basename(p) for p in FILES])
def test_node_syntax(path, tmp_path):
    # Workflow 运行时把脚本包进 async 函数（顶层 await / return 合法）；这里同样包一层再 node --check
    src = open(path, encoding="utf-8").read().replace("export const meta", "const meta", 1)
    cjs = tmp_path / (os.path.basename(path) + ".cjs")
    cjs.write_text("async function __wf(args, agent, parallel, pipeline, phase, log) {\n" + src + "\n}\n", encoding="utf-8")
    r = subprocess.run(["node", "--check", str(cjs)], capture_output=True, text=True)
    assert r.returncode == 0, r.stderr
```

- [ ] **Step 2: 跑测试确认失败**（`ts-train-batch.js` 不存在）

- [ ] **Step 3: 写 `ts-diagnose/workflows/ts-train-batch.js`**

```js
export const meta = {
  name: 'ts-train-batch',
  description: '一轮候选并行重训：每条候选派一张 worker 卡片，回 receipt 数组（不判定、不写账本、不问用户）',
  phases: [{ title: 'Train', detail: '每条候选一个 worker，chunk 内并行；判定与账本归主 agent' }],
}

// args = {engine, workdir, agent_type, task, candidates: [...], chunk}
// agent_type: 'model-improve-worker'（task=candidate|baseline）或 'architecture-attribution-worker'（task=intervention）
const CONTRACT = {
  type: 'object',
  properties: {
    status: { type: 'string', enum: ['COMPUTE_DONE', 'NEED_INFO', 'BLOCKED'] },
    task: { type: 'string' },
    exp_id: { type: 'string' },
    hypothesis_id: { type: ['string', 'null'] },
    receipt_line: { type: 'string' },
    receipt_file: { type: 'string' },
    config_diff: { type: 'object' },
    per_seed: { type: 'array', items: { type: 'number' } },
    mean: { type: ['number', 'null'] },
    std: { type: ['number', 'null'] },
    run_status: { type: 'array', items: { type: 'string' } },
    metrics_dirs: { type: 'array', items: { type: 'string' } },
    slices_per_seed: { type: 'array', items: { type: 'object' } },
    summary_file: { type: 'string' },
    need_info: { type: 'array', items: { type: 'string' } },
    blocked_reason: { type: 'string' },
  },
  required: ['status', 'task', 'run_status'],
}

const a = args || {}
if (!a.engine || !a.workdir || !a.agent_type || !Array.isArray(a.candidates) || a.candidates.length === 0) {
  throw new Error('args 须含 engine / workdir / agent_type / 非空 candidates[]')
}
const task = a.task || 'candidate'
const chunk = Math.max(1, Number(a.chunk) || 4)

function idOf(c) {
  return c.exp_id || c.hypothesis_id || 'unknown'
}

function prompt(c) {
  return [
    `任务类型 task：${task}`,
    `工作目录：${a.workdir}`,
    `引擎目录：${a.engine}`,
    '按你的卡片执行下面这一条任务；final message 只回卡片「输出契约」的 JSON，不回其他文字：',
    JSON.stringify(c),
  ].join('\n')
}

phase('Train')
const results = []
for (let i = 0; i < a.candidates.length; i += chunk) {
  const part = a.candidates.slice(i, i + chunk)
  log(`训练批次 ${Math.floor(i / chunk) + 1}/${Math.ceil(a.candidates.length / chunk)}：${part.map(idOf).join(', ')}`)
  const got = await parallel(part.map(c => () =>
    agent(prompt(c), { agentType: a.agent_type, schema: CONTRACT, label: `train:${idOf(c)}`, phase: 'Train' })))
  got.forEach((r, j) => {
    results.push(r || {
      status: 'BLOCKED', task, exp_id: part[j].exp_id || '', hypothesis_id: part[j].hypothesis_id || null,
      run_status: ['crash'], blocked_reason: 'worker 无返回（被跳过或异常终止）',
    })
  })
}
const failed = results.filter(r => r.status !== 'COMPUTE_DONE').map(r => r.exp_id || r.hypothesis_id)
if (failed.length) log(`未完成 ${failed.length} 条：${failed.join(', ')}`)
return { results, failed }
```

- [ ] **Step 4: INSTALL.md 加一句**

在「`install.sh` 做五件事」段落里 `~/.claude/workflows/ 下链接 workflows/*.js（如有）` 后加：`——现有 \`ts-train-batch.js\`（一轮候选并行派 worker 卡；剧本用 scriptPath 调用，按名字调用是否可用以实测为准）`。

- [ ] **Step 5: 跑测试 + 安装校验**

```bash
python3 -m pytest scripts/tests/test_workflows.py -q
python3 -m pytest scripts/tests -q 2>&1 | tail -1
bash install.sh --check 2>&1 | tail -8      # workflows: 行应列出 ts-train-batch.js（本机 ~/.claude 指向主检出时会报指向不是本包——记录即可，不改主检出的安装）
```

- [ ] **Step 6: 提交**

```bash
git add ts-diagnose/workflows/ts-train-batch.js ts-diagnose/scripts/tests/test_workflows.py ts-diagnose/INSTALL.md
git commit -m "feat(workflows): ts-train-batch.js——一轮候选按 chunk 并行派 worker 卡回 receipt 数组（两本 playbook 共用）+ 静态守卫

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>"
```

---

### Task 11: lsf-mini 真适配器 + 集成测试

**Files:**
- Create: `eval-cases/adapters/lsf_mini_adapter.py`
- Test: `ts-diagnose/scripts/tests/test_lsf_mini_adapter.py`（lsf-mini 或 torch 缺席则 skip）

**Interfaces:**
- 实现 Task 4 的适配器 CLI 契约。`cfg.json` 除 run.py 参数外必含 `lsf_mini_dir`；`root_path` 写绝对路径。
- 产出切片 id：`horizon:near|mid|far` + `channel:<列名（非字母数字替换成 _）>`。
- 已实测：TSMixer @ Weather pl96 CPU 一个 epoch ≈ 10 s，早停约 5 epoch，单次 run.py 全程 ≈ 20–60 s。

- [ ] **Step 1: 写失败测试** `ts-diagnose/scripts/tests/test_lsf_mini_adapter.py`

```python
"""lsf-mini 适配器集成测试：ETTh1 + DLinear 1 epoch（几秒）；lsf-mini 或 torch 缺席则 skip。"""
import importlib.util
import json
import os
import subprocess
import sys

import pytest

REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
ADAPTER = os.path.join(REPO, "eval-cases", "adapters", "lsf_mini_adapter.py")
LSF = os.path.join(os.path.dirname(REPO), "lsf-mini")

pytestmark = pytest.mark.skipif(
    not os.path.exists(os.path.join(LSF, "run.py")) or importlib.util.find_spec("torch") is None,
    reason="需要同级目录的 lsf-mini 与 torch")


def test_adapter_end_to_end_etth1(tmp_path):
    cfg = {"lsf_mini_dir": LSF, "model": "DLinear", "data": "ETTh1",
           "root_path": os.path.join(LSF, "dataset"), "features": "M", "target": "OT",
           "seq_len": 96, "label_len": 48, "pred_len": 24, "enc_in": 7,
           "train_epochs": 1, "patience": 1, "batch_size": 32, "learning_rate": 1e-3}
    (tmp_path / "cfg.json").write_text(json.dumps(cfg), encoding="utf-8")
    out = tmp_path / "s7"
    r = subprocess.run([sys.executable, ADAPTER, "--config", str(tmp_path / "cfg.json"), "--seed", "7",
                        "--out", str(out), "--time-limit", "600"], capture_output=True, text=True, timeout=900)
    assert r.returncode == 0, r.stderr[-2000:]
    m = json.loads((out / "metrics.json").read_text(encoding="utf-8"))
    assert m["status"] == "ok" and m["metric_id"] == "val_mse" and m["primary"] > 0
    for s in ("horizon:near", "horizon:mid", "horizon:far", "channel:OT"):
        assert s in m["slices"], s
    sealed = json.loads((out / "sealed" / "test_metrics.json").read_text(encoding="utf-8"))
    assert sealed["test_primary"] > 0 and "test_slices" in sealed
    assert not (out / "pred.npy").exists() and not (out / "true.npy").exists()
    assert (out / "results" / "results.csv").exists()          # results.csv 落在 out 目录，不污染 lsf-mini


def test_adapter_crash_writes_metrics(tmp_path):
    cfg = {"lsf_mini_dir": LSF, "model": "NoSuchModel", "data": "ETTh1",
           "root_path": os.path.join(LSF, "dataset"), "enc_in": 7, "train_epochs": 1}
    (tmp_path / "cfg.json").write_text(json.dumps(cfg), encoding="utf-8")
    r = subprocess.run([sys.executable, ADAPTER, "--config", str(tmp_path / "cfg.json"), "--seed", "7",
                        "--out", str(tmp_path / "bad")], capture_output=True, text=True, timeout=300)
    assert r.returncode == 2
    m = json.loads((tmp_path / "bad" / "metrics.json").read_text(encoding="utf-8"))
    assert m["status"] == "crash" and m["error"]
```

- [ ] **Step 2: 跑测试确认失败**（适配器不存在）

- [ ] **Step 3: 写适配器** `eval-cases/adapters/lsf_mini_adapter.py`

```python
#!/usr/bin/env python3
"""lsf-mini 训练入口适配器（评估器契约实现，契约见 ts-diagnose/references/evaluator-contract.md）。
用法：python3 lsf_mini_adapter.py --config cfg.json --seed 7 --out DIR [--time-limit 900]
cfg.json：lsf_mini_dir（lsf-mini 仓库绝对路径）+ run.py 参数（model/data/root_path/enc_in/seq_len/pred_len/…，
root_path 写绝对路径）。流程：子进程跑 run.py（cwd=DIR，results.csv 落 DIR/results/）→ 载 DIR/ckpt.pth 在
val 集推理 → primary=val_mse（标准化空间，与 run.py 的 test_mse 同口径）+ 切片 MSE（horizon 三桶 × 通道）
→ DIR/metrics.json。run.py 自带的 test 指标只写 DIR/sealed/test_metrics.json（封存）；pred.npy/true.npy
算完即删（Weather 单次各 84 MB）。"""
import argparse
import datetime as dt
import json
import os
import re
import subprocess
import sys

RUN_KEYS = ("model", "data", "root_path", "features", "target", "seq_len", "label_len", "pred_len", "enc_in",
            "d_model", "n_heads", "e_layers", "d_ff", "dropout", "factor", "moving_avg", "patch_len", "stride",
            "frets_embed_size", "corrupt_col", "activation", "embed", "freq", "batch_size", "learning_rate",
            "train_epochs", "patience", "num_workers")
FLAG_KEYS = ("itrans_no_attn", "ptst_layernorm", "nlinear_avginit", "dlinear_reanchor",
             "tsmixer_no_channel_mix", "tide_no_residual", "frets_channel_indep")


def _now():
    return dt.datetime.now().isoformat(timespec="seconds")


def build_cmd(cfg, seed, out):
    cmd = [sys.executable, os.path.join(cfg["lsf_mini_dir"], "run.py"), "--seed", str(seed),
           "--save_dir", out, "--checkpoints", os.path.join(out, "checkpoints")]
    for k in RUN_KEYS:
        if k in cfg:
            cmd += [f"--{k}", str(cfg[k])]
    for k in FLAG_KEYS:
        if cfg.get(k):
            cmd.append(f"--{k}")
    return cmd


def _write(out, doc):
    with open(os.path.join(out, "metrics.json"), "w", encoding="utf-8") as f:
        json.dump(doc, f, ensure_ascii=False, indent=2)


def _fail(out, status, error, cfg, t0):
    _write(out, {"status": status, "primary": None, "metric_id": "val_mse", "slices": {},
                 "t_start": t0, "t_end": _now(), "config": cfg, "error": error})


def slices_of(err, names):
    """err: (N, L, C) 平方误差 → horizon 三桶 + 每通道 的 MSE。"""
    L = err.shape[1]
    b = [0, L // 3, 2 * L // 3, L]
    out = {"horizon:near": float(err[:, b[0]:b[1]].mean()),
           "horizon:mid": float(err[:, b[1]:b[2]].mean()),
           "horizon:far": float(err[:, b[2]:b[3]].mean())}
    for i, n in enumerate(names):
        out[f"channel:{n}"] = float(err[:, :, i].mean())
    return out


def channel_names(cfg, n):
    csv = os.path.join(cfg["root_path"], f"{cfg['data']}.csv")
    if os.path.exists(csv):
        with open(csv, encoding="utf-8") as f:
            cols = [c for c in f.readline().strip().split(",") if c != "date"]
        if len(cols) == n:
            return [re.sub(r"[^0-9A-Za-z_]+", "_", c).strip("_") for c in cols]
    return [f"c{i}" for i in range(n)]


def val_predict(cfg, out):
    sys.path.insert(0, cfg["lsf_mini_dir"])
    import importlib
    import numpy as np
    import torch
    from run import build_loader, run_epoch
    meta = json.load(open(os.path.join(out, "config.json"), encoding="utf-8"))
    args = argparse.Namespace(**meta)
    _, loader = build_loader(args, "val")
    model = importlib.import_module(f"models.{args.model}").Model(args).float()
    model.load_state_dict(torch.load(os.path.join(out, "ckpt.pth")))
    model.eval()
    _, preds, trues = run_epoch(model, loader, args, torch.device("cpu"), torch.nn.MSELoss())
    return np.asarray(preds), np.asarray(trues), meta


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--config", required=True)
    ap.add_argument("--seed", type=int, required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--time-limit", type=int, default=900)
    a = ap.parse_args()
    cfg = json.load(open(a.config, encoding="utf-8"))
    out = os.path.abspath(a.out)
    os.makedirs(out, exist_ok=True)
    t0 = _now()
    for k in ("lsf_mini_dir", "model", "data", "root_path"):
        if k not in cfg:
            _fail(out, "crash", f"config 缺 {k}", cfg, t0)
            sys.exit(2)
    try:
        r = subprocess.run(build_cmd(cfg, a.seed, out), cwd=out, capture_output=True, text=True, timeout=a.time_limit)
    except subprocess.TimeoutExpired:
        _fail(out, "timeout", f"run.py 超过 {a.time_limit}s", cfg, t0)
        sys.exit(3)
    if r.returncode != 0:
        _fail(out, "crash", (r.stderr or r.stdout or "")[-2000:], cfg, t0)
        sys.exit(2)
    try:
        import numpy as np
        preds, trues, meta = val_predict(cfg, out)
        err = (preds - trues) ** 2
        names = channel_names(cfg, err.shape[2])
        primary = float(err.mean())
        sl = slices_of(err, names)
        tp, tt = np.load(os.path.join(out, "pred.npy")), np.load(os.path.join(out, "true.npy"))
        test_slices = slices_of((tp - tt) ** 2, names)
    except Exception as e:  # 推理或切片失败也算 crash，带一句原因
        _fail(out, "crash", f"val 推理失败：{type(e).__name__}: {e}"[-2000:], cfg, t0)
        sys.exit(2)
    os.makedirs(os.path.join(out, "sealed"), exist_ok=True)
    with open(os.path.join(out, "sealed", "test_metrics.json"), "w", encoding="utf-8") as f:
        json.dump({"test_primary": float(meta["test_mse"]), "test_mae": float(meta["test_mae"]),
                   "metric_id": "test_mse", "test_slices": test_slices}, f, indent=2)
    for name in ("pred.npy", "true.npy"):
        p = os.path.join(out, name)
        if os.path.exists(p):
            os.remove(p)
    _write(out, {"status": "ok", "primary": primary, "metric_id": "val_mse", "slices": sl,
                 "n_epochs": len(meta.get("epoch_log") or []), "best_val_epoch": meta.get("best_val_epoch"),
                 "n_params": meta.get("n_params"), "t_start": t0, "t_end": _now(), "config": cfg, "error": None})
    print(json.dumps({"status": "ok", "primary": primary}))


if __name__ == "__main__":
    main()
```

- [ ] **Step 4: 跑测试**

```bash
python3 -m pytest scripts/tests/test_lsf_mini_adapter.py -q -s    # 2 passed（本机有 lsf-mini + torch）
python3 -m pytest scripts/tests -q 2>&1 | tail -1
```

- [ ] **Step 5: 提交**

```bash
git add eval-cases/adapters/lsf_mini_adapter.py ts-diagnose/scripts/tests/test_lsf_mini_adapter.py
git commit -m "feat(eval-cases): lsf-mini 评估器适配器（val_mse + horizon/通道切片，test 指标封存，npy 即删）+ ETTh1 集成测试

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>"
```

---

### Task 12: Weather 冒烟——素版改进环两轮脚本驱动跑通

**Files:**
- Create: `eval-cases/improve-smoke-weather/{README.md, .gitignore, evaluator.json, switches.json, diagnose_config.json, smoke_driver.py}`
- 产物（提交）：`experiment_log.jsonl, champion.json, rounds/**, receipts/*.json, final_test.json, provenance.json, CONCLUSION.md, gate_reports/conclusion_gate.json`
- 产物（不提交）：`runs/**, diagnose_state.json, PROGRESS.md, .orient_audit.jsonl`

**Interfaces:**
- Consumes：Task 1–11 全部。`smoke_driver.py` 代替 worker 卡片机械执行「run-seeds + improve_verdict」，正式运行由 `model-improve-worker` / `ts-train-batch.js` 执行同样两条命令。
- 预算：3 种子基线 + 第 1 轮 4 候选 + 第 2 轮 2 候选 = 21 次训练，约 15–25 分钟。

- [ ] **Step 1: 建目录与配置**

`eval-cases/improve-smoke-weather/.gitignore`：

```
runs/
diagnose_state.json
PROGRESS.md
.orient_audit.jsonl
```

`evaluator.json`（把 `<REPO>` 换成仓库绝对路径、`<LSF>` 换成 lsf-mini 绝对路径，本机分别是 `/private/tmp/improve-loop-phase4` 与 `/Users/tqa946816/Documents/华为/光伏预测/lsf-mini`）：

```json
{
  "adapter": "<REPO>/eval-cases/adapters/lsf_mini_adapter.py",
  "base_config": {"lsf_mini_dir": "<LSF>", "model": "TSMixer", "data": "weather",
                  "root_path": "<LSF>/dataset", "features": "M", "target": "OT",
                  "seq_len": 96, "label_len": 48, "pred_len": 96, "enc_in": 21,
                  "d_model": 128, "n_heads": 8, "e_layers": 2, "d_ff": 256, "dropout": 0.1,
                  "batch_size": 32, "learning_rate": 0.001, "train_epochs": 10, "patience": 3},
  "knobs": {"tsmixer_no_channel_mix": {"family": "architecture", "type": "flag"},
            "d_model": {"family": "architecture", "type": "int"},
            "e_layers": {"family": "architecture", "type": "int"},
            "dropout": {"family": "training", "type": "float"},
            "learning_rate": {"family": "training", "type": "float"},
            "batch_size": {"family": "training", "type": "int"}},
  "metric": {"id": "val_mse", "direction": "lower_is_better"},
  "slices": ["horizon:near", "horizon:mid", "horizon:far"],
  "seeds": [7, 1337, 2021],
  "time_limit_s": 900
}
```

`switches.json`（素版候选来源，模拟 model_profile 的 ablation_switches）：

```json
{"ablation_switches": [
  {"component": "train.batch_size", "switch": "--batch_size=64", "kind": "config-flag"},
  {"component": "train.dropout", "switch": "--dropout=0.2", "kind": "config-flag"},
  {"component": "train.learning_rate", "switch": "--learning_rate=0.0005", "kind": "config-flag"},
  {"component": "tsmixer.channel_mix", "switch": "--tsmixer_no_channel_mix", "kind": "config-flag"},
  {"component": "tsmixer.d_model", "switch": "--d_model=256", "kind": "config-flag"},
  {"component": "tsmixer.e_layers", "switch": "--e_layers=3", "kind": "config-flag"}]}
```

`diagnose_config.json`：

```json
{"playbook": "model-improve",
 "materials": {"model_code": {"status": "absent-confirmed", "source": "user"},
               "experiment_config": {"status": "absent-confirmed", "source": "user"},
               "checkpoint": {"status": "absent-confirmed", "source": "user"}},
 "products": {"model_profile": {"status": "declined"}},
 "questions": {"evaluator-adapter": {"answer": "eval-cases/adapters/lsf_mini_adapter.py", "source": "user"},
               "improve-target": {"answer": "TSMixer @ Weather pl96；基线新跑 3 种子", "source": "user"},
               "improve-budget": {"answer": "30 次 / 2 轮 / 每轮 4 条", "source": "user"},
               "guard-slices": {"answer": "horizon:near,horizon:mid,horizon:far", "source": "user"},
               "candidate-source": {"answer": "素版：switches.json", "source": "user"}}}
```

`smoke_driver.py`：

```python
#!/usr/bin/env python3
"""冒烟驱动：代替 worker 卡片，机械执行「evaluator.py run-seeds + improve_verdict.py」并写本轮 batch_result.json。
用法：python3 smoke_driver.py <ENGINE> baseline | python3 smoke_driver.py <ENGINE> round
正式运行由 model-improve-worker / workflows/ts-train-batch.js 执行同样两条命令；本脚本只服务脚本驱动的冒烟。"""
import json
import subprocess
import sys

ENGINE, MODE = sys.argv[1], sys.argv[2]
EV = json.load(open("evaluator.json", encoding="utf-8"))


def run(cmd):
    r = subprocess.run(cmd, capture_output=True, text=True)
    print(r.stdout[-600:], r.stderr[-300:] if r.returncode else "")
    return r


if MODE == "baseline":
    run([sys.executable, f"{ENGINE}/scripts/evaluator.py", "run-seeds", "--evaluator", "evaluator.json",
         "--config-diff", "{}", "--out-root", "runs/E000"])
    sys.exit(0)

rnd = json.load(open("diagnose_state.json", encoding="utf-8"))["round"]
cands = json.load(open(f"rounds/round_{rnd}/candidates.json", encoding="utf-8"))
results = []
for c in cands["candidates"]:
    eid = c["exp_id"]
    run([sys.executable, f"{ENGINE}/scripts/evaluator.py", "run-seeds", "--evaluator", "evaluator.json",
         "--config-diff", json.dumps(c["config_diff"]), "--out-root", f"runs/{eid}"])
    s = json.load(open(f"runs/{eid}/summary.json", encoding="utf-8"))
    res = {"status": "COMPUTE_DONE", "task": "candidate", "exp_id": eid, "hypothesis_id": c.get("hypothesis_id"),
           "config_diff": c["config_diff"], "per_seed": s["per_seed"], "mean": s["mean"], "std": s["std"],
           "run_status": s["run_status"], "metrics_dirs": s["metrics_dirs"], "slices_per_seed": s["slices_per_seed"],
           "summary_file": f"runs/{eid}/summary.json", "receipt_line": "", "receipt_file": "",
           "need_info": [], "blocked_reason": ""}
    if all(x == "ok" for x in s["run_status"]):
        r = run([sys.executable, f"{ENGINE}/scripts/improve_verdict.py", "--exp-id", eid,
                 "--hypothesis-id", c.get("hypothesis_id") or "", "--summary", f"runs/{eid}/summary.json",
                 "--champion", "champion.json", "--guard", ",".join(c.get("guard_slices") or []),
                 "--config-diff", json.dumps(c["config_diff"]), "--script", EV["adapter"],
                 "--t-start", s["t_start"], "--t-end", s["t_end"],
                 "--selftest", f"seeds={len(s['per_seed'])}=={len(EV['seeds'])}", "--out", f"receipts/{eid}.json"])
        res["receipt_file"] = f"receipts/{eid}.json"
        res["receipt_line"] = r.stdout.strip().splitlines()[-1] if r.stdout.strip() else ""
    else:
        res["status"], res["blocked_reason"] = "BLOCKED", ",".join(s["run_status"])
    results.append(res)
json.dump({"results": results, "failed": [x["exp_id"] for x in results if x["status"] != "COMPUTE_DONE"]},
          open(f"rounds/round_{rnd}/batch_result.json", "w", encoding="utf-8"), ensure_ascii=False, indent=2)
print("✓ batch_result.json:", [(x["exp_id"], x["status"]) for x in results])
```

- [ ] **Step 2: 按阶段跑，每步跑 orient 核对阶段**（`ENGINE=<REPO>/ts-diagnose`，在 `eval-cases/improve-smoke-weather/` 里执行）

```bash
cd <REPO>/eval-cases/improve-smoke-weather
ENGINE=<REPO>/ts-diagnose
python3 "$ENGINE/scripts/orient.py" | head -20            # 期望：当前 Stage 0
python3 "$ENGINE/scripts/evaluator.py" validate evaluator.json
python3 smoke_driver.py "$ENGINE" baseline                # 3 次训练 ≈ 3 分钟
python3 "$ENGINE/scripts/experiment_log.py" init --evaluator evaluator.json --baseline runs/E000/summary.json \
        --max-trainings 30 --max-rounds 2 --max-per-round 4
python3 "$ENGINE/scripts/orient.py" | head -20            # 期望：当前 Stage 1（第 1 轮）
python3 "$ENGINE/scripts/experiment_log.py" candidates --switches switches.json --target TSMixer \
        --guard horizon:near,horizon:mid,horizon:far      # 期望 4 条候选、顺延 2 条
python3 "$ENGINE/scripts/orient.py" | head -20            # 期望：Stage 2 前置 ✗（未确认）
python3 "$ENGINE/scripts/experiment_log.py" confirm-round
python3 "$ENGINE/scripts/orient.py" | head -20            # 期望：当前 Stage 2
python3 smoke_driver.py "$ENGINE" round                   # 12 次训练 ≈ 10–15 分钟
python3 "$ENGINE/scripts/experiment_log.py" append --batch rounds/round_1/batch_result.json
python3 "$ENGINE/scripts/orient.py" | head -20            # 期望：当前 Stage 3
python3 "$ENGINE/scripts/experiment_log.py" decide        # 期望：未收敛（round 1 < 2）
python3 "$ENGINE/scripts/orient.py" | head -20            # 期望：Stage 4 前置 ✗（未收敛）
python3 "$ENGINE/scripts/experiment_log.py" new-round
python3 "$ENGINE/scripts/orient.py" | head -20            # 期望：当前 Stage 1（第 2 轮）
python3 "$ENGINE/scripts/experiment_log.py" candidates --switches switches.json --target TSMixer \
        --guard horizon:near,horizon:mid,horizon:far      # 期望 2 条（去重后剩 d_model / e_layers）
python3 "$ENGINE/scripts/experiment_log.py" confirm-round
python3 smoke_driver.py "$ENGINE" round                   # 6 次训练
python3 "$ENGINE/scripts/experiment_log.py" append --batch rounds/round_2/batch_result.json
python3 "$ENGINE/scripts/experiment_log.py" decide        # 期望：已收敛（max_rounds）
python3 "$ENGINE/scripts/orient.py" | head -20            # 期望：当前 Stage 4
python3 "$ENGINE/scripts/experiment_log.py" finalize
python3 "$ENGINE/scripts/experiment_log.py" status
```

把每次 orient 的头两行与每条子命令的 ✓ 行抄进 `README.md` 的「运行记录」节。任一步与期望不符 → 停下修脚本或剧本（这就是冒烟的目的），修完从该步继续。

- [ ] **Step 3: 写结论并过闸**

```bash
python3 "$ENGINE/scripts/provenance.py" --code ../adapters/lsf_mini_adapter.py \
        --data evaluator.json experiment_log.jsonl --out provenance.json
```

按剧本 §6 模板写 `CONCLUSION.md`：一句话用 `champion.json` 与 `final_test.json` 的真实数字；「## 模型结构依据」写 `absent-confirmed：无模型档案，降级为配置级改进结论`；「## 改进证据」贴两轮 `summary.json` 的全部 `receipt_lines` 与 `final_test.json.line`；「## 证据清单」列全部 `receipts/E*.json`、`experiment_log.jsonl`、`champion.json`、`final_test.json`、两轮 `summary.json`。然后：

```bash
python3 "$ENGINE/scripts/conclusion_gate.py"              # 期望 ✓ 并写 gate_reports/conclusion_gate.json
python3 "$ENGINE/scripts/orient.py" | head -5             # 期望：全部阶段完成
```

- [ ] **Step 4: 写 README.md**（冒烟目录）

内容：目的（脚本驱动验证改进环机器件，不经 agent 交互）；复现命令（Step 2 全部）；运行记录（每步 orient 头两行 + ✓ 行）；结果摘要表（exp_id / config_diff / mean / delta / verdict，来自 experiment_log.jsonl）；两条说明：receipts 里 `produced_by` 是本机绝对路径，换机器重跑闸会因 sha 校验对象缺失而不过，属预期；本目录不读 `eval-cases/holdout/HW1`。

- [ ] **Step 5: 全量回归 + 提交**

```bash
cd <REPO>/ts-diagnose && python3 -m pytest scripts/tests -q 2>&1 | tail -1 && python3 -m pytest chartbook/tests -q 2>&1 | tail -1
cd <REPO>
git add eval-cases/improve-smoke-weather/README.md eval-cases/improve-smoke-weather/.gitignore \
        eval-cases/improve-smoke-weather/evaluator.json eval-cases/improve-smoke-weather/switches.json \
        eval-cases/improve-smoke-weather/diagnose_config.json eval-cases/improve-smoke-weather/smoke_driver.py \
        eval-cases/improve-smoke-weather/experiment_log.jsonl eval-cases/improve-smoke-weather/champion.json \
        eval-cases/improve-smoke-weather/rounds eval-cases/improve-smoke-weather/receipts \
        eval-cases/improve-smoke-weather/final_test.json eval-cases/improve-smoke-weather/provenance.json \
        eval-cases/improve-smoke-weather/CONCLUSION.md eval-cases/improve-smoke-weather/gate_reports
git status --short eval-cases/improve-smoke-weather      # 确认 runs/ 未被 stage
git commit -m "test(eval-cases): Weather 素版改进环冒烟——TSMixer 基线 + 两轮 6 候选脚本驱动跑通，orient 逐阶段推进、收敛后封存终评、结论过闸规则 7

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>"
```

---

## 收尾

- 全分支终审（superpowers:subagent-driven-development 的 final review）后，用 superpowers:finishing-a-development-branch 收尾；合并到 main 与 push 都等用户说。
- 计划外验收（需用户在场，因为有停顿点）：在真实工作目录跑 `model-comparison`（TSMixer vs NLinear @ Weather pl96，两者都有 phase0-weather 的 3 种子产物）→ Stage 2 账本登记 H + F → `architecture-attribution` 验证机理 → `model-improve` 经 Workflow `ts-train-batch` 派 `model-improve-worker` 跑一轮。这一步验证的是卡片、Workflow 与停顿点，冒烟已验证的机器件不重复。
- 记忆更新：`ts-diagnose-packaging-2026-09.md` 补 Phase 4 落地状态；新建 `improve-loop-2026-09.md` 记改进环设计决策与冒烟结果。
