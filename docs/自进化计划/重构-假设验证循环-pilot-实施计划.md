# 假设验证循环（pilot）实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 把"三条腿"抽成引擎编排的运行时循环——model-comparison 只产假设、architecture-attribution 验证、结论出口产一次——并让 skill 变轻。

**Architecture:** 生成器（model-comparison）吐结构化假设账本 → 验证主脊（architecture-attribution，每个干预强制 subagent 只回 receipt）→ 否证则回生成器精炼 / 确认则过 conclusion_gate 落唯一结论。回退：无 trainable_framework 时退化为"未验证假设"。

**Tech Stack:** Python 3.11 + pytest（subprocess 式 gate 测试）；markdown playbook；lsf-mini 训练平台（消融开关已在阶段 2 打好）。

## Global Constraints

- 设计源文档：`docs/自进化计划/重构-假设验证循环-pilot-design.md`，本计划每个 Task 对应其某节。
- 范围锁定 pilot 一对：只动 model-comparison + 新建 architecture-attribution + engine-core + conclusion_gate；其余 6 个分析 playbook 与 4 个纯生产者不动。
- 零破坏底线：无 `trainable_framework` 材料的老用法行为完全不变（conclusion_gate 对无因果表述的老结论向后兼容）。
- 测试运行器：`cd ts-diagnose && python3 -m pytest scripts/tests/ -v`（沿用现有 subprocess 式 gate 测试模式）。
- receipt 格式统一到一种 `ablation_receipts` schema（阶段 1 上游清单决定 3）。
- 结论只在循环出口产一次，经 conclusion_gate。

---

### Task 0: 仓库清理（垃圾出库 + gitignore）

**Files:**
- Modify: `ts-diagnose/.gitignore`（若无则 Create）
- Delete: 所有 `__pycache__/` 目录

**Interfaces:**
- Produces: 干净的工作树；后续 Task 的测试不被 stale pyc 干扰。

- [ ] **Step 1: 删除已入库的 pyc 垃圾**

Run:
```bash
cd ts-diagnose && find . -type d -name __pycache__ -exec rm -rf {} + ; find . -name '*.pyc' -delete
```

- [ ] **Step 2: 写 .gitignore**

写入 `ts-diagnose/.gitignore`：
```
__pycache__/
*.pyc
.DS_Store
```

- [ ] **Step 3: 验证测试仍全绿（清理无副作用）**

Run: `cd ts-diagnose && python3 -m pytest scripts/tests/ -q`
Expected: 与清理前相同的通过数，无新增失败。

- [ ] **Step 4: Commit**

```bash
git add ts-diagnose/.gitignore && git rm -r --cached $(find ts-diagnose -type d -name __pycache__) 2>/dev/null; git commit -m "chore(ts-diagnose): drop __pycache__ from repo + add .gitignore"
```

---

### Task 1: conclusion_gate 支持 ablation_receipts + 架构因果拦截

对应设计 §11 / 阶段 1 上游清单 A3。让结论闸认一种消融 receipt，并拦截"无 receipt 的架构/组件因果表述"。

**Files:**
- Modify: `ts-diagnose/scripts/conclusion_gate.py`
- Test: `ts-diagnose/scripts/tests/test_conclusion_gate.py`

**Interfaces:**
- Consumes: 现有 `engine_common as ec`；现有 `SECTION = "## 模型结构依据"`。
- Produces: 新规则——CONCLUSION.md 若含架构因果表述（正则 `CAUSAL_RE`）但 `## 消融证据` 节缺对应 receipt 行 → exit 1；有 receipt 或无因果表述 → 向后兼容通过。

- [ ] **Step 1: 写失败测试（有因果表述但无 receipt → 拦截）**

追加到 `test_conclusion_gate.py`：
```python
def test_fail_arch_causal_without_ablation_receipt(tmp_path):
    c = ("# 结论\n（见 charts/error-breakdown.png）\n## 模型结构依据\n"
         "档案 H3：跨变量注意力**导致**近端优势。\n")
    r = run_gate(setup(tmp_path, c))
    assert r.returncode == 1 and "消融" in r.stdout
    assert not (tmp_path / "gate_reports" / "conclusion_gate.json").exists()

def test_pass_arch_causal_with_ablation_receipt(tmp_path):
    c = ("# 结论\n（见 charts/error-breakdown.png）\n## 模型结构依据\n"
         "档案 H3：跨变量注意力**导致**近端优势。\n"
         "## 消融证据\n"
         "- H3 confirmed: switch=--itrans_no_attn delta=+0.031 noise_floor=0.0102 seeds=3\n")
    assert run_gate(setup(tmp_path, c)).returncode == 0
```

- [ ] **Step 2: 跑测试确认失败**

Run: `cd ts-diagnose && python3 -m pytest scripts/tests/test_conclusion_gate.py::test_fail_arch_causal_without_ablation_receipt -v`
Expected: FAIL（当前闸不认因果表述，直接通过 → 断言 returncode==1 失败）。

- [ ] **Step 3: 实现拦截规则**

在 `conclusion_gate.py` 顶部正则区加：
```python
CAUSAL_RE = re.compile(r"(导致|因为|归因于|caused by|due to|→\s*优势|使得)")
RECEIPT_LINE_RE = re.compile(r"(confirmed|refuted|undecided).*(switch|delta).*seeds?=\d")
ABLATION_SECTION = "## 消融证据"
```
在 `main()` 里、图证据规则之后、写 receipt 之前插入：
```python
    # 规则 4：架构/组件因果表述必须附消融 receipt
    if CAUSAL_RE.search(sec):
        abl = text.split(ABLATION_SECTION, 1)[1] if ABLATION_SECTION in text else ""
        if not RECEIPT_LINE_RE.search(abl):
            fail("结论含架构因果表述但「## 消融证据」节无对应 receipt"
                 "（须含 confirmed/refuted/undecided + switch/delta + seeds=N）——"
                 "降级为「未验证假设」或补 receipt")
```

- [ ] **Step 4: 跑全部结论闸测试**

Run: `cd ts-diagnose && python3 -m pytest scripts/tests/test_conclusion_gate.py -v`
Expected: 新增两条 PASS，原有 8 条 PASS（向后兼容——老结论无因果词不触发）。

- [ ] **Step 5: Commit**

```bash
git add ts-diagnose/scripts/conclusion_gate.py ts-diagnose/scripts/tests/test_conclusion_gate.py && git commit -m "feat(conclusion_gate): intercept arch-causal claims lacking ablation receipt"
```

---

### Task 2: 假设账本 schema + 校验脚本

对应设计 §3。生成器与验证脊之间的接口，用脚本校验字段纪律。

**Files:**
- Create: `ts-diagnose/scripts/hypothesis_ledger.py`
- Test: `ts-diagnose/scripts/tests/test_hypothesis_ledger.py`

**Interfaces:**
- Produces: `validate_ledger(obj) -> list[str]`（返回违规信息列表，空列表=合法）；CLI `python3 hypothesis_ledger.py <ledger.json>` exit 0/1。
- 后续 Task 4/5 依赖此校验器保证账本合法。

- [ ] **Step 1: 写失败测试**

`test_hypothesis_ledger.py`：
```python
import os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import hypothesis_ledger as hl

VALID = {"slice_map": [{"dim": "lead_time", "bucket": "far", "z": 10.2, "winner": "iTransformer"}],
         "hypotheses": [{"id": "H1", "claim": "跨变量注意力带来近端优势",
                         "component": "itransformer.attention",
                         "falsifiable_pred": "置零后近端优势消失",
                         "discriminating_power": 3,
                         "intervention": {"switch": "--itrans_no_attn", "seeds": 3},
                         "status": "pending", "kill_receipt": None,
                         "provenance": "pre-registered"}]}

def test_valid_ledger_passes():
    assert hl.validate_ledger(VALID) == []

def test_missing_component_rejected():
    bad = {"slice_map": [], "hypotheses": [dict(VALID["hypotheses"][0], component="")]}
    errs = hl.validate_ledger(bad)
    assert any("component" in e for e in errs)

def test_posthoc_requires_new_intervention_flag():
    h = dict(VALID["hypotheses"][0], provenance="post-hoc", status="confirmed", kill_receipt=None)
    errs = hl.validate_ledger({"slice_map": [], "hypotheses": [h]})
    assert any("post-hoc" in e for e in errs)

def test_refuted_requires_kill_receipt():
    h = dict(VALID["hypotheses"][0], status="refuted", kill_receipt=None)
    errs = hl.validate_ledger({"slice_map": [], "hypotheses": [h]})
    assert any("kill_receipt" in e for e in errs)
```

- [ ] **Step 2: 跑测试确认失败**

Run: `cd ts-diagnose && python3 -m pytest scripts/tests/test_hypothesis_ledger.py -v`
Expected: FAIL（`ModuleNotFoundError: hypothesis_ledger`）。

- [ ] **Step 3: 实现校验器**

`hypothesis_ledger.py`：
```python
#!/usr/bin/env python3
"""假设账本校验：字段纪律 = component 必填 / 可否证 / provenance / 状态一致性。"""
import json, sys

REQUIRED = ["id", "claim", "component", "falsifiable_pred", "status", "provenance"]
STATUSES = {"pending", "confirmed", "refuted", "undecided"}

def validate_ledger(obj):
    errs = []
    for h in obj.get("hypotheses", []):
        hid = h.get("id", "?")
        for k in REQUIRED:
            if not h.get(k):
                errs.append(f"{hid}: 缺字段 {k}")
        if h.get("status") not in STATUSES:
            errs.append(f"{hid}: status 非法")
        if h.get("status") == "refuted" and not h.get("kill_receipt"):
            errs.append(f"{hid}: refuted 必须带 kill_receipt")
        if h.get("provenance") == "post-hoc" and h.get("status") == "confirmed" \
                and not h.get("kill_receipt"):
            errs.append(f"{hid}: post-hoc 假设升级为 confirmed 需新干预 receipt")
    return errs

def main():
    obj = json.load(open(sys.argv[1], encoding="utf-8"))
    errs = validate_ledger(obj)
    if errs:
        print("\n".join("✗ " + e for e in errs)); sys.exit(1)
    print("✓ 账本合法"); 
if __name__ == "__main__":
    main()
```

- [ ] **Step 4: 跑测试确认通过**

Run: `cd ts-diagnose && python3 -m pytest scripts/tests/test_hypothesis_ledger.py -v`
Expected: 4 条 PASS。

- [ ] **Step 5: Commit**

```bash
git add ts-diagnose/scripts/hypothesis_ledger.py ts-diagnose/scripts/tests/test_hypothesis_ledger.py && git commit -m "feat: hypothesis ledger schema + validator"
```

---

### Task 3: model-audit 产出 ablation_switches（pilot 最小集）

对应阶段 1 上游清单 A1。假设的 `component` 要能落到可干预开关，需要 model-audit 输出"组件→开关"映射。本 Task 只做 pilot 三案例（C1/C2/C3）需要的最小集。

**Files:**
- Modify: `ts-diagnose/playbooks/model-audit/playbook.md`（新增产出：`ablation_switches`）
- Modify: model_profile 产物 schema（在 model-audit 的 references 或 scripts 中声明处）

**Interfaces:**
- Produces: model_profile 增字段 `ablation_switches`: `[{component, switch, kind}]`，`kind ∈ {config-flag, code-stub, not-intervenable}`。
- Task 4 的验证脊消费此字段选 intervention。

- [ ] **Step 1: 在 model-audit playbook.md 增"组件→可干预开关映射"产出节**

内容要点（照 `_playbook-spec.md` 格式写节，非代码）：
- 每组件标注现成配置项（如 `--n_heads`）/ 需加代码开关（如 `--itrans_no_attn` 置零 stub）/ 不可干预（标原因）；
- 覆盖 `__init__`/初始化/默认参数（C3 教训：初始化差异藏在 `__init__`）。

- [ ] **Step 2: 在产物 schema 声明处登记 `ablation_switches` 字段**

找到 model_profile 产物定义（`playbooks/model-audit/` 下 schema 声明文件），加字段说明。

- [ ] **Step 3: 手工核对 pilot 三案例开关齐全**

对照阶段 2 已有开关：`--itrans_no_attn`（C1）、`--dlinear_reanchor`/`--moving_avg 1`（C2/C3）、`--nlinear_avginit`（C3）。确认 model-audit 映射把 C1/C2/C3 涉及的组件都指到了这些开关。
Expected: 三案例每条待验证假设都有对应 switch。

- [ ] **Step 4: Commit**

```bash
git add ts-diagnose/playbooks/model-audit/ && git commit -m "feat(model-audit): emit component→ablation_switches map (pilot subset)"
```

---

### Task 4: 新建 architecture-attribution 验证主脊 + 强制 subagent 契约 + 脚本

对应设计 §2/§7 + 阶段 1 主文档 §3–§5。

**Files:**
- Create: `ts-diagnose/playbooks/architecture-attribution/playbook.md`
- Create: `ts-diagnose/playbooks/architecture-attribution/references/subagent-brief.md`
- Create: `ts-diagnose/scripts/slice_zcheck.py`（从 C1 slice_analysis.py 泛化）
- Create: `ts-diagnose/scripts/ablation_verdict.py`（从 C1 verdict_c1.py 泛化）
- Test: `ts-diagnose/scripts/tests/test_ablation_verdict.py`

**Interfaces:**
- Consumes: 假设账本（Task 2）、ablation_switches（Task 3）、噪声底（阶段 2 phase0）。
- Produces: `ablation_verdict.verdict(delta, noise_floor_3sigma, pred_direction) -> "confirmed"|"refuted"|"undecided"`；每条 receipt 行格式匹配 Task 1 的 `RECEIPT_LINE_RE`。

- [ ] **Step 1: 写 ablation_verdict 失败测试**

`test_ablation_verdict.py`：
```python
import os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import ablation_verdict as av

def test_confirmed_when_delta_exceeds_floor_and_direction_matches():
    assert av.verdict(delta=0.031, noise_floor_3sigma=0.0102, pred_direction="increase") == "confirmed"

def test_undecided_when_within_noise_floor():
    assert av.verdict(delta=0.004, noise_floor_3sigma=0.0102, pred_direction="increase") == "undecided"

def test_refuted_when_direction_wrong():
    assert av.verdict(delta=-0.031, noise_floor_3sigma=0.0102, pred_direction="increase") == "refuted"
```

- [ ] **Step 2: 跑测试确认失败**

Run: `cd ts-diagnose && python3 -m pytest scripts/tests/test_ablation_verdict.py -v`
Expected: FAIL（`ModuleNotFoundError: ablation_verdict`）。

- [ ] **Step 3: 实现 ablation_verdict.py**

```python
#!/usr/bin/env python3
"""干预判定：delta 与噪声底 3σ 比较 + 预测方向核对 → 确认/否证/未决。"""
def verdict(delta, noise_floor_3sigma, pred_direction):
    if abs(delta) < noise_floor_3sigma:
        return "undecided"
    got = "increase" if delta > 0 else "decrease"
    return "confirmed" if got == pred_direction else "refuted"
```

- [ ] **Step 4: 跑测试确认通过**

Run: `cd ts-diagnose && python3 -m pytest scripts/tests/test_ablation_verdict.py -v`
Expected: 3 条 PASS。

- [ ] **Step 5: 泛化 slice_zcheck.py（切片配对 z 检验）**

从 C1 的 slice_analysis.py 泛化为通用 CLI：输入分切片的跨种子指标，输出每切片配对差值 z，z>3 记真实差异、否则 `~noise`。若找不到 C1 原型，按阶段 1 主文档 §3.1 描述实现，并加一条 z 计算的单元测试。

- [ ] **Step 6: 写 playbook.md（验证主脊本体）**

按阶段 1 主文档 §3 五阶段 + `_playbook-spec.md` 格式写。硬规则：三条腿不齐不得进结论；否证/未决是合法产出；结论对接 conclusion_gate 的 `## 消融证据` 节（receipt 行格式匹配 Task 1）。

- [ ] **Step 7: 写 subagent-brief.md（强制外包契约）**

照设计 §7 写死：每个干预必须派 subagent；subagent 只回紧凑 receipt（配置 diff + delta + 噪声底对照 + 种子数 + 判定），不回训练日志；主 agent 只持账本 + receipt。

- [ ] **Step 8: Commit**

```bash
git add ts-diagnose/playbooks/architecture-attribution/ ts-diagnose/scripts/slice_zcheck.py ts-diagnose/scripts/ablation_verdict.py ts-diagnose/scripts/tests/test_ablation_verdict.py && git commit -m "feat: architecture-attribution validation spine + forced-subagent contract + scripts"
```

---

### Task 5: model-comparison 手术瘦身 + 画图调色板

对应设计 §4/§5。

**Files:**
- Modify: `ts-diagnose/playbooks/model-comparison/playbook.md`（193 → ~90 行）

**Interfaces:**
- Consumes: 假设账本 schema（Task 2）作为其 Stage 2 输出格式。
- Produces: 停顿点 = 交账本给验证主脊；不再自产结论。

- [ ] **Step 1: 删结论相关三节**

删除：Stage 3 结论、§3 证据升级规则、§6 结论模板与特有反驳门。

- [ ] **Step 2: 改 Stage 2 机制归因 → 只产假设账本**

Stage 2 输出改为写一份符合 Task 2 schema 的假设账本（每假设指向组件、给可否证预测、预登记）。

- [ ] **Step 3: 改 §8 chartbook → 主题调色板 + 假设驱动选图**

替换为设计 §5 的调色板（5 项，每项标"何时用"）+ 规则"只画生成/区分当前假设所必需的图"；figure-diagnostics 标注为按需查阅手册，不默认全读。

- [ ] **Step 4: 改 §4 停顿点 → 交账本给主脊**

停顿点汇报改为"产出假设账本、移交 architecture-attribution 验证"。

- [ ] **Step 5: 验证行数与 layering 守卫**

Run: `cd ts-diagnose && wc -l playbooks/model-comparison/playbook.md && python3 -m pytest scripts/tests/test_layering.py scripts/tests/test_charts_decl.py -v`
Expected: 行数 ≈ 90（显著下降）；layering/charts 守卫仍 PASS。

- [ ] **Step 6: Commit**

```bash
git add ts-diagnose/playbooks/model-comparison/playbook.md && git commit -m "refactor(model-comparison): hypothesis generator only + plot palette; drop conclusion machinery"
```

---

### Task 6: engine-core 新增"假设验证循环"节

对应设计 §6/§8。

**Files:**
- Modify: `ts-diagnose/references/engine-core.md`（新增一节）

**Interfaces:**
- Produces: 循环编排纪律——生成器→验证脊→否证回精炼/确认→conclusion_gate；预算（单轮≤10训练、总≤3轮）；回退（无 trainable_framework → 未验证假设）。

- [ ] **Step 1: 写"假设验证循环"节**

在 engine-core.md 的"执行模型"与"结论纪律"之间插入新节，含：循环步骤、终止三条件、预算阶梯、subagent 外包指向 architecture-attribution 的 brief、无框架回退。

- [ ] **Step 2: 更新 SKILL.md 路由说明（升级条件）**

在 model-comparison 行补一句：需机制结论 + 有 trainable_framework 时升级到 architecture-attribution（照阶段 1 上游清单 A5，注意 SKILL.md ≤60 行守卫）。

- [ ] **Step 3: 验证 layering 守卫仍绿**

Run: `cd ts-diagnose && python3 -m pytest scripts/tests/test_layering.py scripts/tests/test_routing.py -v`
Expected: PASS（SKILL.md 未超行、路由表可解析）。

- [ ] **Step 4: Commit**

```bash
git add ts-diagnose/references/engine-core.md ts-diagnose/SKILL.md && git commit -m "feat(engine): hypothesis-validation loop orchestration + upgrade routing"
```

---

### Task 7: 验收 —— C1/C2/C3 盲跑

对应设计 §10。复用阶段 2 已定稿案例，不造新数据。

**Files:**
- Create: `ts-diagnose/scripts/tests/test_pilot_acceptance.md`（人工验收清单，勾选式）

**Interfaces:**
- Consumes: 全部前置 Task 的产物。

- [ ] **Step 1: 全量单测回归**

Run: `cd ts-diagnose && python3 -m pytest scripts/tests/ -q`
Expected: 全绿，无回归。

- [ ] **Step 2: C1 盲跑（不给 gold）**

用 model-comparison + architecture-attribution 循环跑 `eval-cases/tier2-c1/` 的冻结产物。
Expected: ①账本含切片版图 + 指向组件的假设；②对"跨变量注意力"假设跑干预、确认；③某个错误假设被否证并留 kill-receipt；④结论只产一次、带 `## 消融证据` receipt、过 conclusion_gate。

- [ ] **Step 3: C2/C3 盲跑**

同上跑 C2（机制分解型，pl720 反超 decoy 必须不中招）、C3（初始化先验最大，"赢在分解"教科书故事必须被否证）。
Expected: decoy 不中招、教科书故事被否证、结论带 receipt。

- [ ] **Step 4: 回退检验（无 trainable_framework）**

构造一个只有 artifacts、无训练入口的 case 跑一遍。
Expected: 循环退化为"未验证假设"判定；conclusion_gate 对无因果表述放行、对有因果表述无 receipt 拦截。

- [ ] **Step 5: 成本轴检验**

检查 C1 盲跑的 agent log：每个干预都经 subagent 执行，主 agent 上下文只见 receipt、未见训练日志。
Expected: receipt 数 == 干预数；主 agent 未加载训练过程。

- [ ] **Step 6: 记录验收结果并 Commit**

把 Step 2–5 结果勾进 `test_pilot_acceptance.md`。
```bash
git add ts-diagnose/scripts/tests/test_pilot_acceptance.md && git commit -m "test: pilot acceptance results on C1/C2/C3 + fallback + cost axis"
```

---

## 自查

**Spec 覆盖**：设计 §2 架构→Task 4/5/6；§3 账本→Task 2；§4 手术→Task 5；§5 画图→Task 5 Step3；§6 循环→Task 6；§7 subagent→Task 4 Step7；§8 回退→Task 6 Step1 + Task 7 Step4；§10 验收→Task 7；§11 工程清单→Task 0–6 全覆盖；阶段 1 依赖 A1→Task 3、A3→Task 1。无遗漏。

**占位符扫描**：无 TBD/TODO；脚本步骤均给了真实代码；prose 步骤给了要点与格式指向（playbook 正文本质是文档，不强套代码块）。Task 4 Step5 对"找不到 C1 原型"给了兜底路径。

**类型一致**：`verdict()` 签名 Task 4 定义、Task 7 消费一致；`validate_ledger()` Task 2 定义；receipt 行格式 Task 1 `RECEIPT_LINE_RE` 与 Task 4 Step6/Step7 产出对齐（confirmed/refuted/undecided + switch/delta + seeds=N）；`ablation_switches` Task 3 产、Task 4 消费一致。

## 已知前置（动手前确认）

- 阶段 1 上游清单 D 三项待拍板（噪声底产者 / training-sufficiency 本轮是否改 / receipt 格式统一）——本计划采用其建议默认值（噪声底复用 phase0、training-sufficiency 不在 pilot、receipt 统一一种）。若你另有决定，Task 1/3 需相应调整。
- C1 原型脚本（slice_analysis.py / verdict_c1.py）位置未在仓库定位到；Task 4 Step5 已给"按描述重写"兜底。
