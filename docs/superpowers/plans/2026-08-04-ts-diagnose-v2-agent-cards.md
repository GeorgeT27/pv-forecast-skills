# ts-diagnose v2（预定义 agent 卡片版）实现计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 产出自包含的 `ts-diagnose-v2/`：v1 引擎逐字复制 + 一层预定义 agent 卡片派发层，供后续与 v1 做同数据同目标的准确率 A/B。

**Architecture:** 复制 v1 的 `scripts/ playbooks/ chartbook/ references/`（引擎用 `__file__` 自定位，零逻辑改动即工作），在其上加 `SKILL.md` 编排脑 + `agents/` 卡片（3 producer / 7 compute / 1 compute-fine）+ `references/dispatch-protocol.md` + `EVAL.md` + 两支守卫测试。只改「派发机制」这一个变量，菜谱/闸/golden/纪律全部沿用。

**Tech Stack:** Python 3 + pytest + PyYAML（已装 6.0.1）；引擎脚本已有；卡片与文档为 Markdown（YAML frontmatter）。

## Global Constraints

- **引擎冻结**：复制来的 `scripts/ playbooks/ chartbook/ golden/ references/`（除 `references/subagent-briefs.md` 第 30 行路径修正外）逻辑一字不改，只往上加派发层。改了即 A/B 作废。
- **scoped 测试**：v1 与 v2 的 `scripts/tests/` 同名文件（`test_batch.py` 等）无 `__init__.py`，同一 pytest 进程里会撞名并交叉 import 错的 `engine_common`。v2 测试**永远**用 `cd ts-diagnose-v2 && python3 -m pytest scripts/tests -q` 单独跑，绝不在 repo 根一次收集两份。
- **复制基线**：v1 当前 `scripts/tests` = 190 passed。v2 复制后同一套应仍 190 passed（引擎未改；`test_layering`/`test_routing` 需 v2 `SKILL.md` 到位）。
- **薄卡**：每张卡片 frontmatter 之后正文 ≤60 行、零菜谱、golden 绝不进卡片；步骤指针化到 `playbook.md`/`orient.py`/`gen_gate.py`。
- **命名律**：卡片文件名 = frontmatter `name` = `<playbook-id>-compute`，含 producer，无例外。
- **工具锁死**：任何卡片 `tools:` 不得含 `AskUserQuestion`。
- **编排脑预算**：`ts-diagnose-v2/SKILL.md` ≤60 行 / ≤6000 token 且禁方法词（复制来的 `test_layering` 守卫）。
- **路径**：以下所有相对路径以 repo 根 `/Users/tqa946816/Documents/华为/光伏预测/结果分析skill` 为基准。`<V2>` = `ts-diagnose-v2`，`<V1>` = `ts-diagnose`。

---

## Task 1: Bootstrap — 复制引擎 + 路径修正 + 编排脑 SKILL.md + 绿基线

**Files:**
- Create: `ts-diagnose-v2/scripts/` `ts-diagnose-v2/playbooks/` `ts-diagnose-v2/chartbook/` `ts-diagnose-v2/references/`（复制自 v1）
- Modify: `ts-diagnose-v2/references/subagent-briefs.md`（第 30 行 ENGINE 路径）
- Create: `ts-diagnose-v2/SKILL.md`

**Interfaces:**
- Produces: 自包含引擎副本；`SKILL.md`（路由表 = v1 逐字；卡片索引 11 行；派发增量段）。后续任务的卡片/测试都在此副本内运行。

- [ ] **Step 1: 复制四个目录并清 pycache**

```bash
cd /Users/tqa946816/Documents/华为/光伏预测/结果分析skill
mkdir -p ts-diagnose-v2
for d in scripts playbooks chartbook references; do cp -R "ts-diagnose/$d" "ts-diagnose-v2/$d"; done
find ts-diagnose-v2 -name __pycache__ -type d -prune -exec rm -rf {} +
find ts-diagnose-v2 -name '*.pyc' -delete
```

- [ ] **Step 2: 修正 subagent-briefs.md 硬编码 ENGINE 路径**

`ts-diagnose-v2/references/subagent-briefs.md` 第 30 行把
`引擎目录 ENGINE：/Users/tqa946816/Documents/华为/光伏预测/结果分析skill/ts-diagnose`
改成结尾 `.../ts-diagnose-v2`（其余不动）。用精确字符串替换，仅此一行。

- [ ] **Step 3: 运行复制来的测试，确认除 SKILL 相关外皆绿**

Run: `cd ts-diagnose-v2 && python3 -m pytest scripts/tests -q 2>&1 | tail -8`
Expected: 仅 `test_layering.py` / `test_routing.py`（依赖 `SKILL.md`）失败或报错，其余通过。记录失败清单，供下一步定标。

- [ ] **Step 4: 写编排脑 SKILL.md（≤60 行）**

内容三段：①`---` frontmatter（`name: ts-diagnose-v2`，`description:` 一句话说明"卡片派发版诊断引擎，与 v1 同菜谱同闸，只改派发层"）；②路由表 = 逐字复制 `ts-diagnose/SKILL.md` 的「用户目标 → playbook」11 行表 + 两级路由优先级 + 批量入口指向 `references/engine-core.md` 批量节；③**卡片索引**（11 行 `playbook → agents/<id>-compute.md（mode）`）；④**派发增量段**，原文：

> 执行纪律全部继承 `references/engine-core.md` + `references/batch-orchestration.md`（提问上浮 / 停顿归主 / 结论归主 / 禁嵌套 / 单写者 / 批量 Phase A–E）。**只替换派发机制**：不再按 `references/subagent-briefs.md` 注入 Brief，改为按名字派发预定义卡片 `agents/<id>-compute.md`；派发前先按该 playbook 的上浮问题问用户、把答案随派发带入。选卡与协议见 `references/dispatch-protocol.md`。

约束：不得出现 `test_layering` 禁词（`Stage`/`done_when`/`pause_after`/`evidence_lines`/`findings_marker`/`crystallize` 等——先看 `scripts/tests/test_layering.py` 里的禁词表照避）；"停顿/结论"等执行细节留给 `dispatch-protocol.md`（Task 8）。转发段落照抄 v1 SKILL 的 orient 调用模板（`python3 "<ENGINE>/scripts/orient.py" ...`），`<ENGINE>` = 本 SKILL.md 所在目录。

- [ ] **Step 5: 全量绿基线**

Run: `cd ts-diagnose-v2 && python3 -m pytest scripts/tests -q 2>&1 | tail -5`
Expected: `190 passed`。若 `test_routing`/`test_layering` 仍红，按其断言调 SKILL.md 措辞（路由表行文、批量指向、行/词预算）直到全绿。**不得**改测试文件本身（引擎冻结）。

- [ ] **Step 6: Commit**

```bash
cd /Users/tqa946816/Documents/华为/光伏预测/结果分析skill
git add ts-diagnose-v2
git commit -m "feat(ts-diagnose-v2): bootstrap self-contained engine copy + orchestrator SKILL"
```

---

## Task 2: `_agent-spec.md` 卡片模板 + `test_cards.py` 守卫

**Files:**
- Create: `ts-diagnose-v2/agents/_agent-spec.md`
- Create: `ts-diagnose-v2/scripts/tests/test_cards.py`

**Interfaces:**
- Produces: 卡片正文六节模板 + 三 mode 约定 + 输出契约 JSON（`_agent-spec.md`）；`test_cards.py` 对 `agents/*-compute.md` 逐卡校验（无卡时 0 参数即通过）。后续 Task 3–7 的卡片都实例化此模板并须过此守卫。

- [ ] **Step 1: 写失败测试 `test_cards.py`**

完整代码（放 `ts-diagnose-v2/scripts/tests/test_cards.py`）：

```python
import os, re, glob, sys
import yaml
import pytest

HERE = os.path.dirname(os.path.abspath(__file__))
SCRIPTS_DIR = os.path.join(os.path.dirname(HERE))          # ts-diagnose-v2/scripts
V2 = os.path.dirname(SCRIPTS_DIR)                          # ts-diagnose-v2
AGENTS_DIR = os.path.join(V2, "agents")
sys.path.insert(0, SCRIPTS_DIR)
import engine_common as ec  # noqa: E402

PRODUCTS = {"setup", "model_profile", "metric_table", "chart_sweep", "eval_report"}
BODY_LINE_BUDGET = 60
FORBIDDEN_BODY = ["## 逐阶段菜谱", "### Stage", "## 2. 逐阶段"]
SIX_SECTIONS = ["你是谁", "输入", "步骤", "红线", "输出契约", "停顿"]

def _card_paths():
    return sorted(p for p in glob.glob(os.path.join(AGENTS_DIR, "*-compute.md")))

def _split(path):
    text = open(path, encoding="utf-8").read()
    assert text.startswith("---\n"), f"{path} 缺 frontmatter"
    end = text.index("\n---", 3)
    fm = yaml.safe_load(text[4:end])
    body = text[end+4:]
    return fm, body

def _stage_range(spec):
    lo, _, hi = str(spec).partition("-")
    return (int(lo), int(hi if hi else lo))

@pytest.mark.parametrize("card", _card_paths(), ids=lambda p: os.path.basename(p))
def test_card_conforms(card):
    fm, body = _split(card)
    pid = fm["playbook"]
    assert fm["name"] == f"{pid}-compute", "命名律：name == <playbook>-compute"
    assert os.path.basename(card) == f"{pid}-compute.md", "文件名 == name.md"
    mode = fm["mode"]
    assert mode in {"producer", "compute", "compute-fine"}
    tools = fm.get("tools") or []
    assert "AskUserQuestion" not in tools, "工具锁死：卡片不得含 AskUserQuestion"

    pb_fm = ec.load_frontmatter(ec.find_playbook(pid))
    stages = pb_fm["stages"]
    by_id = {str(s["id"]): s for s in stages}

    if mode == "producer":
        assert fm.get("produces") in PRODUCTS, "producer 必须声明已知产物"
        assert not any(s.get("pause_after") for s in stages), "producer 的 playbook 不应有 pause_after"
    elif mode == "compute":
        lo, hi = _stage_range(fm["compute_stages"])
        for sid in range(lo, hi + 1):
            assert by_id[str(sid)].get("subagent_ok") is True, f"compute 区间 stage {sid} 必须 subagent_ok:true"
        assert any(by_id[str(s)].get("pause_after") for s in range(lo, hi + 1)), "compute 区间须含 pause_after"
        if fm.get("produces"):
            assert fm["produces"] in PRODUCTS
    else:  # compute-fine
        assert not any(s.get("subagent_ok") for s in stages), "compute-fine 的 playbook 不应有 subagent_ok:true 阶段"
        assert str(fm.get("compute_stages")) == "scripts"

    body_lines = [ln for ln in body.splitlines() if ln.strip()]
    assert len(body_lines) <= BODY_LINE_BUDGET, f"薄卡：正文 {len(body_lines)} 行 > {BODY_LINE_BUDGET}"
    for bad in FORBIDDEN_BODY:
        assert bad not in body, f"卡片不得复述菜谱（命中 {bad!r}），须指向 playbook.md"
    for sec in SIX_SECTIONS:
        assert sec in body, f"缺六节之一：{sec}"
    assert "COMPUTE_DONE" in body and "NEED_INFO" in body, "输出契约节须含状态字"
    assert f"playbooks/{pid}/playbook.md" in body, "步骤须指向对应 playbook.md"
```

- [ ] **Step 2: 运行确认无卡时通过**

Run: `cd ts-diagnose-v2 && python3 -m pytest scripts/tests/test_cards.py -q`
Expected: `no tests ran` 或 0 参数通过（`agents/` 尚无 `*-compute.md`）。

- [ ] **Step 3: 写 `_agent-spec.md`**

内容：①三 mode 约定表（producer / compute / compute-fine 各自语义与守卫，抄自 spec §7）；②frontmatter 字段说明（`name`/`description`/`mode`/`playbook`/`compute_stages`/`on_demand_stages`/`produces`/`tools`/`model`）；③**正文六节模板**（逐节给出：`## 你是谁` / `## 输入` / `## 步骤（去菜谱）` / `## 红线` / `## 输出契约` / `## 停顿/交回`），每节写清应放什么、指针指向哪；④输出契约 JSON（原样抄 spec §11）；⑤命名律与薄卡预算。此文件是 Task 3–7 的唯一模板来源。

- [ ] **Step 4: Commit**

```bash
git add ts-diagnose-v2/agents/_agent-spec.md ts-diagnose-v2/scripts/tests/test_cards.py
git commit -m "feat(ts-diagnose-v2): card body template (_agent-spec) + test_cards guard"
```

---

## Task 3: 3 张 producer 卡片（data-setup / model-audit / metric-eval）

**Files:**
- Create: `ts-diagnose-v2/agents/data-setup-compute.md`
- Create: `ts-diagnose-v2/agents/model-audit-compute.md`
- Create: `ts-diagnose-v2/agents/metric-eval-compute.md`

**Interfaces:**
- Consumes: `_agent-spec.md` 六节模板；`test_cards.py` 守卫。
- Produces: 3 张 `mode: producer` 卡片。

- [ ] **Step 1: 写三张卡片**

各卡 frontmatter（其余字段照 `_agent-spec.md`；`model: sonnet`；`tools: [Bash, Read, Write]`）：

```yaml
# data-setup-compute.md
name: data-setup-compute
description: 把原始预测/真值规范成长表并对齐，产 setup 产物供全部分析复用
mode: producer
playbook: data-setup
compute_stages: "0-1"
produces: setup
```
```yaml
# model-audit-compute.md
name: model-audit-compute
description: 把模型代码目录固化为代码锚定的模型参考档案，产 model_profile 供机制归因消费
mode: producer
playbook: model-audit
compute_stages: "0-4"
produces: model_profile
```
```yaml
# metric-eval-compute.md
name: metric-eval-compute
description: 按指定口径从 setup 长表算逐模型指标表，产 metric_table，不画图不归因不下结论
mode: producer
playbook: metric-eval
compute_stages: "0-1"
produces: metric_table
```

正文用 `_agent-spec.md` 六节模板。producer 差异（写进正文对应节）：
- `## 输入` 的「已答问题」逐卡列：data-setup→`freq, align-keys`；model-audit→`production-version`；metric-eval→`metric-spec`（主 agent 派发前答）；并列「已就绪上游产物目录」（data-setup 无上游；metric-eval 需 `setup=<path>`；model-audit 无上游）。
- `## 步骤（去菜谱）`：按 `playbooks/<id>/playbook.md` 全程跑到产物落盘；`python3 scripts/orient.py --playbook <id>` 领阶段；生成脚本前过 `python3 scripts/gen_gate.py`。
- `## 停顿/交回`：改为「产物落盘即返回 `COMPUTE_DONE`，`produces_dir` = 产物工作目录」。
- `## 红线`：不问用户（缺答案→NEED_INFO）；单写者；禁嵌套。

- [ ] **Step 2: 过守卫**

Run: `cd ts-diagnose-v2 && python3 -m pytest scripts/tests/test_cards.py -q`
Expected: 3 passed（三卡各一参数）。

- [ ] **Step 3: Commit**

```bash
git add ts-diagnose-v2/agents/data-setup-compute.md ts-diagnose-v2/agents/model-audit-compute.md ts-diagnose-v2/agents/metric-eval-compute.md
git commit -m "feat(ts-diagnose-v2): 3 producer cards (data-setup/model-audit/metric-eval)"
```

---

## Task 4: 2 张「compute + 产物」卡片（fact-scan / result-eval）

**Files:**
- Create: `ts-diagnose-v2/agents/fact-scan-compute.md`
- Create: `ts-diagnose-v2/agents/result-eval-compute.md`

**Interfaces:**
- Produces: `mode: compute` 且带 `produces` 的两卡；跑到现象清单/产物即停，交回主 agent。

- [ ] **Step 1: 写两张卡片**

```yaml
# fact-scan-compute.md
name: fact-scan-compute
description: 把手头材料能画的标准分析图一次画全，产现象清单与 chart_sweep——终点即停，不归因
mode: compute
playbook: fact-scan
compute_stages: "0-0"
produces: chart_sweep
```
```yaml
# result-eval-compute.md
name: result-eval-compute
description: 评估一次预测结果（默认 rmse_192），算指标+画标准图集，跑到现象清单为止
mode: compute
playbook: result-eval
compute_stages: "0-3"
produces: eval_report
```

正文用六节模板。`## 输入` 已答问题：fact-scan→无；result-eval→`metric-caliber`。已就绪上游：两者皆 `setup=<path>`（result-eval 另可选 `model_profile/chart_sweep/metric_table`）。`## 步骤` 指向各自 `playbooks/<id>/playbook.md` 的 Stage `compute_stages`；`## 停顿/交回` 写「跑到区间终点（pause）即返回 `COMPUTE_DONE` + `phenomena_file` + `artifacts`（含产物）」。红线：compute 只到「现象」，禁机制/因果语言。

- [ ] **Step 2: 过守卫**

Run: `cd ts-diagnose-v2 && python3 -m pytest scripts/tests/test_cards.py -q`
Expected: 5 passed（累计）。

- [ ] **Step 3: Commit**

```bash
git add ts-diagnose-v2/agents/fact-scan-compute.md ts-diagnose-v2/agents/result-eval-compute.md
git commit -m "feat(ts-diagnose-v2): 2 compute+product cards (fact-scan/result-eval)"
```

---

## Task 5: 2 张样例 compute 卡片（model-comparison / training-sufficiency）

**Files:**
- Create: `ts-diagnose-v2/agents/model-comparison-compute.md`
- Create: `ts-diagnose-v2/agents/training-sufficiency-compute.md`

**Interfaces:**
- Produces: 两条 golden 冒烟样例（Task 10）指向的卡片。额外注意上浮问题清单完整。

- [ ] **Step 1: 写两张卡片**

```yaml
# model-comparison-compute.md
name: model-comparison-compute
description: 为什么模型A比B好/多模型对比归因的计算半段——跑到差距现象清单为止
mode: compute
playbook: model-comparison
compute_stages: "0-1"
```
```yaml
# training-sufficiency-compute.md
name: training-sufficiency-compute
description: 判断训练是否充分（收敛/平台期/batch瓶颈）的计算半段——跑到现象清单为止
mode: compute
playbook: training-sufficiency
compute_stages: "0-5"
```

正文六节。`## 输入` 已答问题：
- model-comparison→`metric-caliber, model-set, total-gap, slice-gap, cross-dim`；已就绪上游 `setup=<path>`（可选 `model_profile/chart_sweep/metric_table`）。
- training-sufficiency→`loss-source, unit-structure, training-config, loss-composition, external-metric, target-link, fig-style`；上游 `setup`（`required:false`——缺则按 playbook 降级说明处理，写进现象注记）。
`## 步骤` 指向各自 playbook.md Stage `compute_stages`；`## 红线` compute 只到「现象」，禁机制语言；`## 停顿/交回` 跑到 pause 返回 `COMPUTE_DONE`+`phenomena_file`。

- [ ] **Step 2: 过守卫**

Run: `cd ts-diagnose-v2 && python3 -m pytest scripts/tests/test_cards.py -q`
Expected: 7 passed（累计）。

- [ ] **Step 3: Commit**

```bash
git add ts-diagnose-v2/agents/model-comparison-compute.md ts-diagnose-v2/agents/training-sufficiency-compute.md
git commit -m "feat(ts-diagnose-v2): 2 sample compute cards (model-comparison/training-sufficiency)"
```

---

## Task 6: 3 张 compute 卡片（deployment-drift / feature-importance / robustness）

**Files:**
- Create: `ts-diagnose-v2/agents/deployment-drift-compute.md`
- Create: `ts-diagnose-v2/agents/feature-importance-compute.md`
- Create: `ts-diagnose-v2/agents/robustness-compute.md`

**Interfaces:**
- Produces: 3 张 `mode: compute` 卡片。feature-importance 含结论后变体阶段 `on_demand_stages`。

- [ ] **Step 1: 写三张卡片**

```yaml
# deployment-drift-compute.md
name: deployment-drift-compute
description: 上线是否退化/误差何时变大/漂移诊断的计算半段——跑到结构分解现象清单为止
mode: compute
playbook: deployment-drift
compute_stages: "0-2"
```
```yaml
# feature-importance-compute.md
name: feature-importance-compute
description: 哪个输入变量对误差影响最大的计算半段——跑到事实提取现象清单为止
mode: compute
playbook: feature-importance
compute_stages: "0-3"
on_demand_stages: "5-6"
```
```yaml
# robustness-compute.md
name: robustness-compute
description: 结论/模型在扰动与分组切片下稳不稳的计算半段——跑到事实提取现象清单为止
mode: compute
playbook: robustness
compute_stages: "0-3"
```

正文六节。`## 输入` 已答问题：
- deployment-drift→`metric-caliber, deploy-timeline, degradation-criterion, error-changepoint`（`feature-shift` 是 pause 后深挖问题，注明由主 agent 停顿后再问，不进本卡上浮）；上游 `setup`（可选 `model_profile/chart_sweep`）。
- feature-importance→`importance-scope, feature-list, model-access, collinearity-handling, correlation, permutation, ablation`；上游 `setup`。`## 停顿/交回` 额外写「变体阶段 5–6（feature_true 对照 / 反事实）为 `on_demand_stages`：主 agent 在停顿后按用户点名再派本卡跑之，仍只到证据合流前」。
- robustness→`conclusions-under-test, metric-and-pairing, perturbation-families, group-columns, perturbation, slices`；上游 `setup`（可选 `chart_sweep`）。
共同：`## 红线` compute 只到「现象」；`## 步骤` 指向各自 playbook.md Stage `compute_stages`。

- [ ] **Step 2: 过守卫**

Run: `cd ts-diagnose-v2 && python3 -m pytest scripts/tests/test_cards.py -q`
Expected: 10 passed（累计）。

- [ ] **Step 3: Commit**

```bash
git add ts-diagnose-v2/agents/deployment-drift-compute.md ts-diagnose-v2/agents/feature-importance-compute.md ts-diagnose-v2/agents/robustness-compute.md
git commit -m "feat(ts-diagnose-v2): 3 compute cards (deployment-drift/feature-importance/robustness)"
```

---

## Task 7: compute-fine 卡片（subset-influence）

**Files:**
- Create: `ts-diagnose-v2/agents/subset-influence-compute.md`

**Interfaces:**
- Produces: 唯一 `mode: compute-fine` 卡片：不做整段交接，只按主 agent 指派跑具名重活脚本、回数字摘要。

- [ ] **Step 1: 写卡片**

```yaml
# subset-influence-compute.md
name: subset-influence-compute
description: N个训练条目里哪个拖累留出目标（负迁移）——按主agent指派跑单个重活脚本回数字
mode: compute-fine
playbook: subset-influence
compute_stages: "scripts"
```

正文六节，compute-fine 差异（对照 `references/subagent-briefs.md`）：
- `## 步骤（去菜谱）`：只按主 agent 指派运行**一个**具名脚本（`find_bad_rows.py` / `feature_blame.py` / 影响力回归 / TracIn / `counterfactual_api.py`），逐行落各自产物文件，回数字摘要；阶段进度、Mode A/B 选择、结论均由主 agent 驱动；步骤总纲仍指向 `playbooks/subset-influence/playbook.md`。
- `## 红线`：一次只跑被指派的一个脚本/一层，不自行连跑；不改阈值；不碰共享状态；禁嵌套。
- `## 停顿/交回`：每个脚本跑完回 `COMPUTE_DONE`+数字摘要，等主 agent 下一步指派。
- `## 输入`：已答问题=无；工作目录 + 本次被指派的脚本名 + 相关产物路径。

- [ ] **Step 2: 过守卫**

Run: `cd ts-diagnose-v2 && python3 -m pytest scripts/tests/test_cards.py -q`
Expected: 11 passed（累计，全 11 卡）。

- [ ] **Step 3: Commit**

```bash
git add ts-diagnose-v2/agents/subset-influence-compute.md
git commit -m "feat(ts-diagnose-v2): compute-fine card (subset-influence)"
```

---

## Task 8: `dispatch-protocol.md` + `EVAL.md`

**Files:**
- Create: `ts-diagnose-v2/references/dispatch-protocol.md`
- Create: `ts-diagnose-v2/EVAL.md`

**Interfaces:**
- Consumes: 编排脑 SKILL.md 的派发增量段（下沉细节到此）。
- Produces: 选卡 + 单playbook三明治 + 批量 A–E + NEED_INFO 回环协议；A/B 对比口径文档。

- [ ] **Step 1: 写 `dispatch-protocol.md`**

四节（抄自 spec §10 + §12）：①**选卡**（命中 playbook X → 派 `X-compute`；批量下 dispatch_list 映射卡片名；`description` 仅模糊兜底）；②**单 playbook 三明治**六步（上浮问 → 保上游产物就绪(先派 producer) → 派 X-compute → 处理 NEED_INFO 重派 → 停顿展示/用户点名 → 主 agent 亲跑变体(按需再派 `on_demand_stages`)+结论+闸）；③**批量 A–E** 复用 `scripts/batch.py` 与 `references/batch-orchestration.md`，唯一差异 Phase C 每 worker=具名卡片；禁嵌套→重活由主 agent 拆平级兄弟卡片；④**NEED_INFO 回环**（worker 不猜→返回 need_info→主 agent 问用户→重派同卡补答案）。

- [ ] **Step 2: 写 `EVAL.md`**

抄自 spec §13+§14：①CC 限制（只有 `.claude/agents/*.md` 可按名派发；v2 卡片是可移植源文件，CC 内演示派发=派 general-purpose+把卡片当 context）；②你自己的 Claude SDK 移植（`agents[name]` 查表 + flatten-on-export）；③A/B 对比口径（同目标同数据分别过 `ts-diagnose/SKILL.md` 与 `ts-diagnose-v2/SKILL.md`，对比 CONCLUSION 证据层级 / gate receipt / 现象与点名切片 / 往返轮次；强调单变量框架）。

- [ ] **Step 3: Commit**

```bash
git add ts-diagnose-v2/references/dispatch-protocol.md ts-diagnose-v2/EVAL.md
git commit -m "docs(ts-diagnose-v2): dispatch-protocol + EVAL (A/B rubric)"
```

---

## Task 9: `test_orchestrator.py` + 收口 SKILL.md 卡片索引

**Files:**
- Create: `ts-diagnose-v2/scripts/tests/test_orchestrator.py`
- Modify: `ts-diagnose-v2/SKILL.md`（收口卡片索引/派发增量以过守卫，若 Task 1 已满足则仅微调）

**Interfaces:**
- Consumes: 全 11 卡片（Task 3–7）、`dispatch-protocol.md`（Task 8）。
- Produces: 编排层守卫；确保路由↔卡片↔playbook 三者对齐。

- [ ] **Step 1: 写失败测试 `test_orchestrator.py`**

完整代码：

```python
import os, re, sys, glob
HERE = os.path.dirname(os.path.abspath(__file__))
SCRIPTS_DIR = os.path.dirname(HERE)
V2 = os.path.dirname(SCRIPTS_DIR)
sys.path.insert(0, SCRIPTS_DIR)
import engine_common as ec  # noqa: E402

def _read(p): return open(p, encoding="utf-8").read()

def test_every_playbook_has_exactly_one_card():
    pbs = {os.path.basename(os.path.dirname(p)) for p in glob.glob(os.path.join(V2, "playbooks", "*", "playbook.md"))}
    cards = {os.path.basename(p)[:-len("-compute.md")] for p in glob.glob(os.path.join(V2, "agents", "*-compute.md"))}
    assert pbs == cards, f"卡片与 playbook 不是一一对应：仅playbook={pbs-cards} 仅卡片={cards-pbs}"

def test_skill_indexes_all_cards_and_routes_all_playbooks():
    skill = _read(os.path.join(V2, "SKILL.md"))
    for pid in {os.path.basename(os.path.dirname(p)) for p in glob.glob(os.path.join(V2, "playbooks", "*", "playbook.md"))}:
        assert pid in skill, f"SKILL 路由/索引缺 {pid}"
        assert f"{pid}-compute" in skill, f"SKILL 卡片索引缺 {pid}-compute"

def test_skill_dispatch_delta_references_engine_and_batch():
    skill = _read(os.path.join(V2, "SKILL.md"))
    assert "engine-core.md" in skill
    assert "dispatch-protocol.md" in skill

def test_dispatch_protocol_covers_modes_and_batch():
    dp = _read(os.path.join(V2, "references", "dispatch-protocol.md"))
    assert "batch.py" in dp or "batch-orchestration.md" in dp
    assert "NEED_INFO" in dp
```

- [ ] **Step 2: 运行，按失败收口 SKILL.md**

Run: `cd ts-diagnose-v2 && python3 -m pytest scripts/tests/test_orchestrator.py -q`
若红：补齐 SKILL.md 卡片索引 11 行、派发增量引用 `engine-core.md` 与 `dispatch-protocol.md`。改动须仍满足 `test_layering` 预算（≤60 行）——若逼近上限，把说明挪去 `dispatch-protocol.md`，SKILL 只留索引与一行指针。

- [ ] **Step 3: 全量绿**

Run: `cd ts-diagnose-v2 && python3 -m pytest scripts/tests -q 2>&1 | tail -5`
Expected: `190 + 11(cards) + 4(orchestrator) = 205 passed`（若引擎测试数因环境略有出入，以「原 190 全绿 + 新增全绿」为准）。

- [ ] **Step 4: Commit**

```bash
git add ts-diagnose-v2/scripts/tests/test_orchestrator.py ts-diagnose-v2/SKILL.md
git commit -m "feat(ts-diagnose-v2): test_orchestrator guard + finalize SKILL card index"
```

---

## Task 10: golden 冒烟（两样例）+ 全量收尾

**Files:**
- Create: `ts-diagnose-v2/scripts/tests/test_smoke.py`

**Interfaces:**
- Consumes: model-comparison / training-sufficiency 卡片 + 各自 golden。
- Produces: 证明卡片指向的管线在副本 golden 上真能起步（orient 步进 + golden 可重生），无需真实数据。

- [ ] **Step 1: 写冒烟测试 `test_smoke.py`**

完整代码（只验机械可跑项：orient 能在 golden 工作目录步进、`make_golden.py` 能重生 golden；不冒充跑完整 LLM 现象提取）：

```python
import os, sys, subprocess, tempfile, shutil
HERE = os.path.dirname(os.path.abspath(__file__))
SCRIPTS_DIR = os.path.dirname(HERE)
V2 = os.path.dirname(SCRIPTS_DIR)
ORIENT = os.path.join(SCRIPTS_DIR, "orient.py")

import pytest

@pytest.mark.parametrize("pid", ["model-comparison", "training-sufficiency"])
def test_orient_steps_on_copy(pid):
    with tempfile.TemporaryDirectory() as wd:
        r = subprocess.run([sys.executable, ORIENT, "--playbook", pid],
                           cwd=wd, capture_output=True, text=True)
        assert r.returncode == 0, f"orient --playbook {pid} 失败：{r.stderr[-800:]}"
        assert pid in (r.stdout + r.stderr), "orient 输出未提及该 playbook"

@pytest.mark.parametrize("pid", ["model-comparison", "training-sufficiency"])
def test_golden_regenerates(pid):
    gdir = os.path.join(V2, "playbooks", pid, "golden")
    mk = os.path.join(gdir, "make_golden.py")
    assert os.path.exists(mk), f"{pid} 缺 golden/make_golden.py"
    r = subprocess.run([sys.executable, mk], cwd=gdir, capture_output=True, text=True)
    assert r.returncode == 0, f"{pid} make_golden 失败：{r.stderr[-800:]}"
```

若 `orient --playbook` 在空工作目录的正确行为是非零退出（例如强制先建 setup），据实把断言改为「退出码 = 该 playbook 无材料时 orient 的既定退出码，且输出含引导语」——以运行 v1 同命令观察到的真实行为为准，不臆造。

- [ ] **Step 2: 运行冒烟**

Run: `cd ts-diagnose-v2 && python3 -m pytest scripts/tests/test_smoke.py -q`
Expected: 4 passed（2 playbook × 2 检查）。据 Step 1 说明按真实行为定标。

- [ ] **Step 3: 全量最终绿**

Run: `cd ts-diagnose-v2 && python3 -m pytest scripts/tests -q 2>&1 | tail -6`
Expected: 全绿（205 + 4 = 209，或按环境实数，原引擎测试全绿 + 全部新增全绿）。

- [ ] **Step 4: Commit**

```bash
git add ts-diagnose-v2/scripts/tests/test_smoke.py
git commit -m "test(ts-diagnose-v2): golden smoke for 2 sample playbooks + final green"
```

---

## Self-Review（写完计划的自查）

- **Spec 覆盖**：§5 目录→Task1；§6 复制+修正→Task1；§7 三 mode 11 卡→Task3–7；§8 schema/模板→Task2；§9 编排脑→Task1+9；§10 dispatch-protocol→Task8；§11 输出契约→Task2(模板)+各卡；§12 问题回传→卡片红线+dispatch-protocol；§13 CC/SDK→Task8(EVAL)；§14 EVAL→Task8；§15 测试→Task2/9/10；§17 全局约束→Global Constraints。无遗漏。
- **占位符扫描**：测试代码为完整可运行代码；卡片给出确切 frontmatter 值 + 六节模板来源（`_agent-spec.md`）+ 逐卡上浮问题清单（枚举自 spec §7），非占位。
- **类型/命名一致**：命名律 `<id>-compute` 在 Global Constraints、test_cards、test_orchestrator、各 Task 一致；三 mode 名 `producer/compute/compute-fine` 一致；产物集合 `{setup,model_profile,metric_table,chart_sweep,eval_report}` 一致；`compute_stages` 区间语义（producer=全程 / compute=区间 / compute-fine="scripts"）在 spec §8、test_cards、各卡一致。
