# Model Comparison Prior Ranking Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make the legacy `ts-diagnose` model-comparison flow explicitly distinguish architecture-prior plausibility from intervention priority, without adding a new ledger, web-search dependency, or attribution playbook.

**Architecture:** Reuse `model-audit`'s existing symmetric `diff_list` as the A/B architecture ledger and keep `model-comparison` as the hypothesis generator. Add optional, validated plausibility metadata to generated hypothesis entries; retain `discriminating_power` for selecting the next experiment. `architecture-attribution` remains the only playbook that verifies component causality.

**Tech Stack:** Markdown playbooks, Python JSON validation, pytest.

---

### Task 1: Add contract tests for hypothesis-prior metadata

**Files:**
- Create: `/Users/tqa946816/Documents/华为/光伏预测/结果分析skill/ts-diagnose/scripts/tests/test_model_comparison_contract.py`

- [ ] **Step 1: Write the failing tests**

Create the contract test with concrete imports and helpers:

```python
from pathlib import Path
import sys

ENGINE = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ENGINE / "scripts"))
import hypothesis_ledger as hl

MODEL_COMPARISON = ENGINE / "playbooks/model-comparison/playbook.md"
MODEL_AUDIT = ENGINE / "playbooks/model-audit/playbook.md"


def base_ledger(**overrides):
    hypothesis = {
        "id": "H1",
        "claim": "attention affects near horizon",
        "component": "itransformer.attention",
        "falsifiable_pred": "attention removal removes the gap",
        "status": "pending",
        "provenance": "pre-registered",
    }
    hypothesis.update(overrides)
    return {"hypotheses": [hypothesis]}


def test_prior_metadata_is_validated():
    ledger = base_ledger(
        prior_plausibility="high",
        prior_basis="specific A/B implementation difference",
    )
    assert hl.validate_ledger(ledger) == []


def test_invalid_prior_metadata_is_rejected():
    ledger = base_ledger(prior_plausibility="certain")
    assert any("prior_plausibility" in e for e in hl.validate_ledger(ledger))


def test_model_comparison_requires_symmetric_diff_and_two_rankings():
    text = Path(MODEL_COMPARISON).read_text(encoding="utf-8")
    assert "diff_list" in text
    assert "prior_plausibility" in text
    assert "discriminating_power" in text
    assert "最可能解释" in text
    assert "验证优先级" in text


def test_model_audit_declares_no_web_prerequisite():
    text = Path(MODEL_AUDIT).read_text(encoding="utf-8")
    assert "外部联网检索不是本 playbook 的前置条件" in text
```

Keep existing ledgers valid when the new metadata is absent; this preserves compatibility with `architecture-attribution` and old evaluation artifacts.

- [ ] **Step 2: Run the targeted tests to verify the contract fails**

Run:

```bash
cd "/Users/tqa946816/Documents/华为/光伏预测/结果分析skill"
pytest ts-diagnose/scripts/tests/test_model_comparison_contract.py \
       ts-diagnose/scripts/tests/test_hypothesis_ledger.py -q
```

Expected: the new validation and playbook-contract assertions fail because the metadata validation and wording do not yet exist.

### Task 2: Validate optional plausibility metadata without breaking old ledgers

**Files:**
- Modify: `/Users/tqa946816/Documents/华为/光伏预测/结果分析skill/ts-diagnose/scripts/hypothesis_ledger.py:8-31`
- Test: `/Users/tqa946816/Documents/华为/光伏预测/结果分析skill/ts-diagnose/scripts/tests/test_model_comparison_contract.py`

- [ ] **Step 1: Add minimal validation constants**

Add:

```python
PRIOR_PLAUSIBILITY = {"high", "medium", "low"}
```

In `validate_ledger`, validate only when `prior_plausibility` is present:

```python
if "prior_plausibility" in h:
    if h["prior_plausibility"] not in PRIOR_PLAUSIBILITY:
        errs.append(f"{hid}: prior_plausibility 非法")
    if not h.get("prior_basis"):
        errs.append(f"{hid}: prior_plausibility 缺 prior_basis")
```

Do not add these fields to `REQUIRED`; ledgers produced before this change must remain valid.

- [ ] **Step 2: Run the targeted tests**

Run the same pytest command from Task 1.

Expected: all ledger validation tests pass, including legacy fixtures and the new valid/invalid metadata cases.

### Task 3: Make Stage 2’s reasoning order explicit

**Files:**
- Modify: `/Users/tqa946816/Documents/华为/光伏预测/结果分析skill/ts-diagnose/playbooks/model-comparison/playbook.md:136-159`
- Test: `/Users/tqa946816/Documents/华为/光伏预测/结果分析skill/ts-diagnose/scripts/tests/test_model_comparison_contract.py`

- [ ] **Step 1: Update the Stage 2 input and procedure text**

State that `diff_list` is the existing symmetric A/B ledger and must be read row-by-row, including shared components, A-only differences, B-only differences, initialization, and default parameters. Do not introduce a new ledger artifact.

State that no web search is required. Internal architecture knowledge may supply a `📐` prior, but code-anchored facts and measured interventions are the evidence hierarchy.

Change the candidate workflow to:

```text
read the complete diff_list and pre-registered bridge hypotheses
-> assign prior_plausibility and prior_basis
-> compare predictions with Stage 1 descriptors
-> keep only falsifiable candidates that explain named slices
-> rank verification order by discriminating_power
-> transfer the ledger to architecture-attribution
```

Require each model-comparison-generated hypothesis to include the optional fields:

```json
{
  "prior_plausibility": "high|medium|low",
  "prior_basis": "specific implementation difference or theoretical prior"
}
```

Clarify that `prior_plausibility` ranks the likely explanation, while `discriminating_power` ranks the best next experiment; they must not be conflated.

- [ ] **Step 2: Run the contract test**

Run:

```bash
cd "/Users/tqa946816/Documents/华为/光伏预测/结果分析skill"
pytest ts-diagnose/scripts/tests/test_model_comparison_contract.py -q
```

Expected: PASS.

### Task 4: Document the no-web architecture-prior boundary in model-audit

**Files:**
- Modify: `/Users/tqa946816/Documents/华为/光伏预测/结果分析skill/ts-diagnose/playbooks/model-audit/playbook.md:109-117`

- [ ] **Step 1: Add the boundary to the bridge-layer instructions**

After the architecture-to-result bridge description, state:

```text
外部联网检索不是本 playbook 的前置条件。模型通用知识只能作为 📐 理论先验；实际实现以代码锚点为准，案例归因必须由数据/消融证据验证。无法由代码或数据支持的陈述标 ⚠️，不得写成代码事实。
```

Do not alter the existing `diff_list`, `ablation_switches`, pointer, or model-profile contracts.

- [ ] **Step 2: Run the model-audit and routing tests**

Run:

```bash
cd "/Users/tqa946816/Documents/华为/光伏预测/结果分析skill"
pytest ts-diagnose/scripts/tests/test_orient_materials.py \
       ts-diagnose/scripts/tests/test_routing.py -q
```

Expected: PASS.

### Task 5: Run the regression suite and review the diff

**Files:**
- Test: `/Users/tqa946816/Documents/华为/光伏预测/结果分析skill/ts-diagnose/scripts/tests/`

- [ ] **Step 1: Run all legacy engine tests**

Run:

```bash
cd "/Users/tqa946816/Documents/华为/光伏预测/结果分析skill"
pytest ts-diagnose/scripts/tests -q
```

Expected: all tests pass; no existing C1–C3-compatible ledger is rejected.

- [ ] **Step 2: Review scope and user changes before integration**

Run:

```bash
git -C "/Users/tqa946816/Documents/华为/光伏预测/结果分析skill" diff -- \
  ts-diagnose/playbooks/model-comparison/playbook.md \
  ts-diagnose/playbooks/model-audit/playbook.md \
  ts-diagnose/scripts/hypothesis_ledger.py \
  ts-diagnose/scripts/tests
```

Confirm the diff does not alter the user’s existing `architecture-attribution` changes, add a web dependency, create a second ledger, or change chart-selection behavior.
