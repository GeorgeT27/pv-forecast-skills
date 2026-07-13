# pv-model-analysis Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Rename+expand `pv-model-verify` into `pv-model-analysis` — a producer that, given a model-code directory, generates code-anchored model reference docs (engineering flowchart + per-method math + 架构→结果分析含义 bridge) for humans and for `pv-result-analysis` to consume; and rewire `pv-result-analysis` to locate those docs via a pointer file (or trigger the producer as a subagent).

**Architecture:** Two coupled skills. `pv-model-analysis` reads a code repo, extracts each model (locate via known class names → per-model subagent → engineering/math/bridge → reconcile → write `<repo>/.modelmap/` + a fixed pointer file). `pv-result-analysis` drops its hand-dictated `models.md` and instead resolves `references/model-ref.pointer` → `.modelmap/models.md`, triggering the producer if the pointer is missing/stale. The bridge hypotheses tie into `pv-result-analysis`'s `hypotheses.md` H-IDs and figure catalog, which the producer reads and registers back into.

**Tech Stack:** Markdown skill authoring (SKILL.md + `references/*.md` + templates); Python 3.11 helper scripts (`pointer.py`, imported `profile_data.py`/`read_pptx.py`); pytest for the scripts.

## Global Constraints

- **This is a skill-authoring repo, not a service.** For Python scripts use real pytest (TDD). For Markdown skill/reference/template files, the "test" cycle is a **consistency/grep verification** (assert the intended content is present and no stale/dangling references remain), then commit. Both are shown per task.
- **Fixed pointer path (hardcoded, absolute — matches the existing convention of hardcoding archive paths):** `/Users/tqa946816/Documents/华为/光伏预测/结果分析skill/pv-result-analysis/references/model-ref.pointer`
- **Produced docs default location:** `<model-repo>/.modelmap/`
- **Confidence tags used verbatim everywhere:** `✅` code / `📊` data / `📐` derived / `⚠️` unverified. Unknown stays explicit (empty field / `⚠️` / `<!-- 待确认 -->`).
- **Known class→model map (locate step):** `FourierMobaTransformer`=M1, `PatchRegForecast`=M2, `MoiraiPvForecaster`=M3, `PatchTSTPvForecaster`=M4; plus Chronos usage + ensemble combiner.
- **H-ID convention:** `H-<TOPIC-or-model>-<n>` (existing e.g. `H-CHRONOS-1`, `H-WXSRC-1`, `H-M1-2`). Producer must **check `hypotheses.md` before appending** and mark new rows `预注册 by pv-model-analysis YYYY-MM-DD`.
- **Do not rewrite historical log entries** (`pv-result-analysis/CHANGELOG.md` past rows that mention `pv-model-verify` stay as history).
- **Commit after every task.** Work stays on branch `design/pv-model-analysis`.
- **cartographer source of truth** for imported machinery/scripts: `/Users/tqa946816/Documents/华为/project-cartographer/` (`SKILL.md`, `scripts/profile_data.py`, `scripts/read_pptx.py`, `references/`).

---

## Phase A — Producer scaffolding (rename + shared machine interface)

### Task 1: Rename the skill directory and update its frontmatter

**Files:**
- Rename: `pv-model-verify/` → `pv-model-analysis/` (git mv)
- Modify: `pv-model-analysis/SKILL.md` (frontmatter `name` + `description` only, in this task)

- [ ] **Step 1: Rename the directory with git**

```bash
cd "/Users/tqa946816/Documents/华为/光伏预测/结果分析skill"
git mv pv-model-verify pv-model-analysis
```

- [ ] **Step 2: Update the SKILL.md frontmatter**

Replace the frontmatter block (lines 1–4) of `pv-model-analysis/SKILL.md` with:

```markdown
---
name: pv-model-analysis
description: 给定光伏功率预测项目的模型代码目录，生成「代码锚定」的模型参考文档——每个模型（M1-M4 + ensemble + Chronos）的工程流程图（I/O 维度、模块、损失）、逐方法数学分析、以及「架构→结果分析含义」桥接假设，产物同时供人阅读与供 pv-result-analysis 机制归因消费。当用户给出模型代码仓库/目录路径，要求"分析模型/生成模型档案/核验模型描述是否与代码一致/在代码库里找 M1-M4/为结果分析准备模型参考"时，务必使用本技能。既能从零生成，也能对已有产物按代码增量核验（reconcile）。
---
```

- [ ] **Step 3: Verify the rename and frontmatter**

Run:
```bash
cd "/Users/tqa946816/Documents/华为/光伏预测/结果分析skill"
test -f pv-model-analysis/SKILL.md && echo "DIR OK"
head -2 pv-model-analysis/SKILL.md | grep -q "name: pv-model-analysis" && echo "NAME OK"
test ! -d pv-model-verify && echo "OLD GONE"
```
Expected: `DIR OK`, `NAME OK`, `OLD GONE`

- [ ] **Step 4: Commit**

```bash
git add -A
git commit -m "refactor: rename pv-model-verify -> pv-model-analysis (frontmatter)"
```

---

### Task 2: Import cartographer's read-only scripts

**Files:**
- Create: `pv-model-analysis/scripts/profile_data.py` (copied from cartographer)
- Create: `pv-model-analysis/scripts/read_pptx.py` (copied from cartographer)
- Test: `pv-model-analysis/scripts/test_profile_data_smoke.py`

**Interfaces:**
- Produces: `profile_data.py` CLI (`python profile_data.py <path> [--time COL --value COL]`) used by the producer's optional data-profiling pass.

- [ ] **Step 1: Copy the two scripts verbatim**

```bash
cd "/Users/tqa946816/Documents/华为/光伏预测/结果分析skill"
cp "/Users/tqa946816/Documents/华为/project-cartographer/scripts/profile_data.py" pv-model-analysis/scripts/profile_data.py
cp "/Users/tqa946816/Documents/华为/project-cartographer/scripts/read_pptx.py" pv-model-analysis/scripts/read_pptx.py
```

- [ ] **Step 2: Write a smoke test that profiles a tiny generated CSV**

Create `pv-model-analysis/scripts/test_profile_data_smoke.py`:

```python
import subprocess, sys, os, textwrap

HERE = os.path.dirname(__file__)

def test_profile_data_runs_on_small_csv(tmp_path):
    csv = tmp_path / "sample.csv"
    csv.write_text("t,power\n0,1.0\n1,2.0\n2,3.0\n3,2.0\n", encoding="utf-8")
    out = subprocess.run(
        [sys.executable, os.path.join(HERE, "profile_data.py"), str(csv)],
        capture_output=True, text=True,
    )
    # Either it profiles successfully, or it prints a dependency install hint —
    # both are acceptable; a traceback/crash is not.
    assert out.returncode == 0 or "install" in (out.stdout + out.stderr).lower(), out.stderr
```

- [ ] **Step 3: Run the smoke test**

Run: `cd "/Users/tqa946816/Documents/华为/光伏预测/结果分析skill" && python -m pytest pv-model-analysis/scripts/test_profile_data_smoke.py -v`
Expected: PASS (or a clean skip-style pass if pandas/pyarrow missing — the assertion allows the install-hint path).

- [ ] **Step 4: Commit**

```bash
git add pv-model-analysis/scripts/profile_data.py pv-model-analysis/scripts/read_pptx.py pv-model-analysis/scripts/test_profile_data_smoke.py
git commit -m "feat: import cartographer data-profiling scripts into pv-model-analysis"
```

---

### Task 3: Add the pointer helper (the shared machine interface)

**Files:**
- Create: `pv-model-analysis/scripts/pointer.py`
- Test: `pv-model-analysis/scripts/test_pointer.py`

**Interfaces:**
- Produces:
  - `write_pointer(pointer_path, docs_path, repo, commit, models, date) -> None`
  - `read_pointer(pointer_path) -> dict` with keys `path, repo, commit, date, models` (`models` is a `list[str]`)
  - `is_stale(pointer: dict, current_commit: str) -> bool` (`commit` of `""`/`"no-git"` → never stale)
- Consumed by: Task 8 (producer writes the pointer), Task 10 (consumer reads it).

- [ ] **Step 1: Write the failing test**

Create `pv-model-analysis/scripts/test_pointer.py`:

```python
import os
from pointer import write_pointer, read_pointer, is_stale

def test_roundtrip(tmp_path):
    p = tmp_path / "sub" / "model-ref.pointer"
    write_pointer(
        str(p),
        docs_path="/repo/.modelmap",
        repo="/repo",
        commit="abc123",
        models=["M1", "M2", "ensemble"],
        date="2026-07-13",
    )
    got = read_pointer(str(p))
    assert got["path"] == "/repo/.modelmap"
    assert got["repo"] == "/repo"
    assert got["commit"] == "abc123"
    assert got["date"] == "2026-07-13"
    assert got["models"] == ["M1", "M2", "ensemble"]

def test_is_stale_commit_mismatch():
    assert is_stale({"commit": "abc123"}, "def456") is True
    assert is_stale({"commit": "abc123"}, "abc123") is False

def test_is_stale_no_git_never_stale():
    assert is_stale({"commit": "no-git"}, "anything") is False
    assert is_stale({"commit": ""}, "anything") is False
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd "/Users/tqa946816/Documents/华为/光伏预测/结果分析skill/pv-model-analysis/scripts" && python -m pytest test_pointer.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'pointer'`

- [ ] **Step 3: Write the implementation**

Create `pv-model-analysis/scripts/pointer.py`:

```python
"""Read/write/validate the model-ref pointer that lets pv-result-analysis
find the produced .modelmap docs. Format: plain `key: value` lines, UTF-8."""
from __future__ import annotations
import os

def write_pointer(pointer_path, docs_path, repo, commit, models, date):
    lines = [
        f"path: {docs_path}",
        f"repo: {repo}",
        f"commit: {commit}",
        f"date: {date}",
        f"models: {', '.join(models)}",
    ]
    os.makedirs(os.path.dirname(pointer_path) or ".", exist_ok=True)
    with open(pointer_path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")

def read_pointer(pointer_path):
    result = {}
    with open(pointer_path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line or ":" not in line:
                continue
            key, _, val = line.partition(":")
            result[key.strip()] = val.strip()
    result["models"] = [m.strip() for m in result.get("models", "").split(",") if m.strip()]
    return result

def is_stale(pointer, current_commit):
    """True if the pointer's recorded commit differs from the repo's current
    HEAD. A commit of '' or 'no-git' means we can't tell → treat as not stale."""
    c = pointer.get("commit", "")
    if c in ("", "no-git"):
        return False
    return c != current_commit
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd "/Users/tqa946816/Documents/华为/光伏预测/结果分析skill/pv-model-analysis/scripts" && python -m pytest test_pointer.py -v`
Expected: PASS (3 passed)

- [ ] **Step 5: Commit**

```bash
cd "/Users/tqa946816/Documents/华为/光伏预测/结果分析skill"
git add pv-model-analysis/scripts/pointer.py pv-model-analysis/scripts/test_pointer.py
git commit -m "feat: pointer.py — shared model-ref discovery interface"
```

---

## Phase B — Producer reference knowledge (what the workflow consults)

### Task 4: `references/machinery.md` — imported cartographer discipline

**Files:**
- Create: `pv-model-analysis/references/machinery.md`

- [ ] **Step 1: Write the file**

Create `pv-model-analysis/references/machinery.md` distilling cartographer's discipline (adapt wording to the PV context; keep it self-contained). It MUST contain these labelled sections:

```markdown
# 建档机制（从 project-cartographer 提炼，PV 语境适配）

## 1. 置信标签（每条非平凡断言都要带）
- ✅ 代码已证：指向实现行（`file:line`），最好带可测量量。
- 📊 数据实测：来自 `scripts/profile_data.py` 对真实数据文件算出的统计量，锚 `data: <file> — <stat>`。
- 📐 理论/推导：从声明的假设推出；几何直觉（"防专家坍缩"）默认 📐，需写清前提。
- ⚠️ 未证/推断：无法锚定；同时写入 `open-questions.md`。
未知永远显式：空字段 / ⚠️ / `<!-- 待确认 -->`，绝不用推断冒充事实。

## 2. 训练流程图四要素（pipeline.md 的核心，缺一不算完成）
1. 每个节点/边都带张量维度（真值取自 config/data 并锚定，否则符号化；无法确定→`?`+⚠️）。
2. 具体模型模块名（"带 MoBA 注意力的 Transformer 编码器"，不是"核心模型"）。
3. 命名的损失进图（形式 + 系数 + `file:line`），预测与标签都流入损失节点。
4. 训练回路：data→forward→pred→loss→backward/optimizer（写出优化器与关键超参）。

## 3. 反造假铁律
- 不臆造张量形状：静态定不下来→⚠️+open-questions；有数据用 profile_data.py 锚。
- 不臆造数据统计：每个 📊 数字必来自真实文件。
- 不为叙事编推导：无代码/材料支撑的"为什么"只能是 📐（写清前提）或 ⚠️，不能 ✅。
- 内部名≠论文名：`symbol-map.md`/术语表两者都记；不确定就说不确定。

## 4. 上下文策略（撑住大仓库）
逐模型串行处理 + 立即落盘 + `manifest`/pointer 断点续跑；每个模型只在上下文里停留一次，
写完即从上下文丢弃。运行时若有子代理：一模型一子代理并行，父代理只持有小账本汇总；
无子代理则静默退回串行。

## 5. 自检（每次产出收尾，强制）
- 落盘后置条件：预期文件确实存在（见 output-spec.md 清单）。
- 锚点抽查：抽 ✅ 断言，打开引用的 `file:line`，确认确实那么说；不符→降级 ⚠️ 并记 open-questions。
- 链接完整：`[[M*]]`/符号表条目都能解析。
- 覆盖：模型找到数 vs 建档数；未触达的模型文件列出（不留静默缺口）。
- 无裸断言：每条非平凡陈述都带标签，✅/📊 带锚。
末尾给一份简短自检报告（抽查/通过/降级/覆盖）。
```

- [ ] **Step 2: Verify the required sections exist**

Run:
```bash
cd "/Users/tqa946816/Documents/华为/光伏预测/结果分析skill/pv-model-analysis/references"
for s in "置信标签" "训练流程图四要素" "反造假铁律" "上下文策略" "自检"; do
  grep -q "$s" machinery.md && echo "OK $s" || echo "MISSING $s"
done
```
Expected: five `OK` lines.

- [ ] **Step 3: Commit**

```bash
cd "/Users/tqa946816/Documents/华为/光伏预测/结果分析skill"
git add pv-model-analysis/references/machinery.md
git commit -m "docs: machinery.md — imported cartographer discipline (tags, flowchart, anti-fab, context, self-check)"
```

---

### Task 5: `references/output-spec.md` — the `.modelmap/` file set + pointer schema

**Files:**
- Create: `pv-model-analysis/references/output-spec.md`

- [ ] **Step 1: Write the file**

Create `pv-model-analysis/references/output-spec.md` specifying every output file and the pointer schema:

```markdown
# 产物规范：`<repo>/.modelmap/` + pointer

所有产物写到 `<model-repo>/.modelmap/`；pointer 写到固定绝对路径
`/Users/tqa946816/Documents/华为/光伏预测/结果分析skill/pv-result-analysis/references/model-ref.pointer`。

## 文件清单
| 文件 | 读者 | 内容 |
|------|------|------|
| `START-HERE.md` | 人 | 5 行 TL;DR + 阅读顺序 + "改哪找哪"表 |
| `pipeline.md` | 人 | 逐模型工程流程图（machinery.md 四要素）|
| `math.md` | 人 | 逐方法数学，一个 `##` 一方法，符号与 symbol-map 一致 |
| `models.md` | **pv-result-analysis** | 分析就绪档案：逐模型 代码类名/架构/输入特征/损失/训练窗口/强弱项 + 架构→结果分析含义桥接假设。结构见 models-template.md |
| `symbol-map.md` | 双方 | 符号 ↔ 代码变量 ↔ 位置 ↔ 形状/dtype |
| `ledger.md` | 双方 | 断言 ↔ `file:line` 证据（reconcile 审计轨迹）|
| `open-questions.md` | 双方 | ⚠️ + 待确认，需人解决 |
| `data-profile.md` | 双方 | 仅当给了数据样本：profile_data.py 实测统计 |

`models.md` 是从 `pipeline.md`+`math.md` 蒸馏出的分析面视图；产出时三者事实/锚点必须一致。

## pointer 文件格式（`scripts/pointer.py` 读写）
```
path:   /abs/.../<repo>/.modelmap
repo:   /abs/.../<repo>
commit: <git sha 或 no-git>
date:   YYYY-MM-DD
models: M1, M2, M3, M4, ensemble
```
陈旧判定：`is_stale` 比对 pointer.commit 与 `git -C <repo> rev-parse HEAD`；`no-git`/空 → 无法判定按不陈旧。
```

- [ ] **Step 2: Verify all seven `.modelmap` filenames + pointer keys are present**

Run:
```bash
cd "/Users/tqa946816/Documents/华为/光伏预测/结果分析skill/pv-model-analysis/references"
for f in START-HERE.md pipeline.md math.md models.md symbol-map.md ledger.md open-questions.md; do
  grep -q "$f" output-spec.md && echo "OK $f" || echo "MISSING $f"
done
for k in "path:" "repo:" "commit:" "date:" "models:"; do
  grep -q "$k" output-spec.md && echo "OK $k" || echo "MISSING $k"
done
```
Expected: all `OK`.

- [ ] **Step 3: Commit**

```bash
cd "/Users/tqa946816/Documents/华为/光伏预测/结果分析skill"
git add pv-model-analysis/references/output-spec.md
git commit -m "docs: output-spec.md — .modelmap file set + pointer schema"
```

---

### Task 6: `references/models-template.md` — target `models.md` structure (from the current archive)

**Files:**
- Create: `pv-model-analysis/references/models-template.md` (structure lifted from `pv-result-analysis/references/models.md`)

**Interfaces:**
- Produces: the canonical section skeleton the producer fills when emitting `.modelmap/models.md`. This preserves the current archive's *structure* (the 全体共同约定 block, per-model fields, the 架构→结果分析含义 bridge, the class-name locate table) as a **template/example**, NOT as fact.

- [ ] **Step 1: Create the template from the existing archive's shape**

Copy the section skeleton (headings + field labels + the class-name locate table + the 全体共同约定 block) out of `pv-result-analysis/references/models.md` into `pv-model-analysis/references/models-template.md`. Replace all dictated *values* with `<…按代码填写…>` placeholders and prepend this banner:

```markdown
# models.md 目标结构模板（不是事实，是产出骨架）

> 本文件规定 `.modelmap/models.md` 的章节骨架与桥接假设写法。产出时逐字段按代码填写并带
> 置信标签；空字段留空或标 ⚠️/待确认。**不得把本模板里的占位/示例当作已知事实。**

## 全体共同约定（跨站设定）
<按代码与用户确认填写：联合训练站、留出测试站、零样本跨站迁移等>

## M1 —— 类名 FourierMobaTransformer
- **代码类名**：FourierMobaTransformer  ✅ `file:line`
- **模型类型/架构**：<…>
- **输入特征**：<…（看得见/看不见什么，决定可归因边界）>
- **损失函数**：<…读实际代码，非注释/函数名>  ✅ `file:line`
- **训练数据窗口**：<…>
- **已知强项/弱项**：<…>
- **版本历史**：<…>

### M1 架构 → 结果分析含义（桥接假设；每条 → 图# + H-ID）
- <架构事实> → <预期误差形态> → <哪张图检验> （H-M1-<n>，📐 前提：<…>）

## M2 —— 类名 PatchRegForecast
（同上骨架）

## M3 —— 类名 MoiraiPvForecaster
（同上骨架）

## M4 —— 类名 PatchTSTPvForecaster
（同上骨架）

## ensemble
- **组合方式** / **成员** / **权重确定方法** / **强弱项**：<…；若代码里找不到组合器，留空+⚠️>

## 定位速查表（locate 步用）
| 模型 | 类名（grep 首选） | 容错前缀 | 架构签名兜底关键词 |
|------|------|------|------|
| M1 | FourierMobaTransformer | FourierMoba | MoBA / vicreg / ortho / fourier / customTSTiEncoder |
| M2 | PatchRegForecast | PatchReg | stat_embd / GHIembedding / Patch1d / weather_source_names |
| M3 | MoiraiPvForecaster | MoiraiPv | moirai / MultiInSizeLinear / loss_auxi / rfft |
| M4 | PatchTSTPvForecaster | PatchTSTPv | PatchTST / RevIN / TSTencoder / pinball / quantile |
| 共用 | — | — | chronos / observe_power_predicted |
```

- [ ] **Step 2: Verify skeleton + locate table present, no dictated facts leaked**

Run:
```bash
cd "/Users/tqa946816/Documents/华为/光伏预测/结果分析skill/pv-model-analysis/references"
grep -q "目标结构模板" models-template.md && echo "BANNER OK"
for m in FourierMobaTransformer PatchRegForecast MoiraiPvForecaster PatchTSTPvForecaster ensemble; do
  grep -q "$m" models-template.md && echo "OK $m" || echo "MISSING $m"
done
grep -q "架构 → 结果分析含义" models-template.md && echo "BRIDGE OK"
grep -q "定位速查表" models-template.md && echo "LOCATE OK"
```
Expected: `BANNER OK`, five model `OK`, `BRIDGE OK`, `LOCATE OK`.

- [ ] **Step 3: Commit**

```bash
cd "/Users/tqa946816/Documents/华为/光伏预测/结果分析skill"
git add pv-model-analysis/references/models-template.md
git commit -m "docs: models-template.md — target models.md skeleton (structure, not fact)"
```

---

### Task 7: `references/cross-skill-contract.md` — hypotheses + figure catalog interface

**Files:**
- Create: `pv-model-analysis/references/cross-skill-contract.md`

- [ ] **Step 1: Write the contract**

Create `pv-model-analysis/references/cross-skill-contract.md`:

```markdown
# 跨技能契约：桥接假设如何对接 pv-result-analysis

桥接假设引用「图#」与「H-ID」，二者归 pv-result-analysis 所有。产出 models.md 的桥接节前：

## 读入（作为输入，不复制）
- `../../pv-result-analysis/references/hypotheses.md` —— 现有 H-ID 与写法（可判别预测、验证手段、状态）。
- `../../pv-result-analysis/SKILL.md` 的「图谱目录」小节 + `../../pv-result-analysis/references/figure-diagnostics.md`
  —— 图#1–#12 各自查什么，桥接假设的「哪张图检验」必须指真实的图。

## H-ID 注册（写回，不臆造）
- 每条桥接假设给一个 H-ID，遵循现有命名（`H-CHRONOS-1`/`H-WXSRC-1`/`H-<model>-<n>`）。
- **先读 hypotheses.md**：命中已有条目→复用其 ID；没有→在 hypotheses.md 追加一行，状态
  `预注册`，末尾标 `预注册 by pv-model-analysis YYYY-MM-DD`，并写清可判别预测 + 验证手段（哪张图）。
- 绝不引用 hypotheses.md 里不存在的 H-ID（否则消费端 H-ID 门解析失败）。

## 接口面（两技能只通过这三样耦合）
1. pointer 文件（model-ref.pointer）
2. hypotheses.md 的 H-ID 登记表
3. 图谱目录 / figure-diagnostics.md
模型事实不在两技能间复制粘贴。
```

- [ ] **Step 2: Verify the three interface items + H-ID rule present**

Run:
```bash
cd "/Users/tqa946816/Documents/华为/光伏预测/结果分析skill/pv-model-analysis/references"
grep -q "hypotheses.md" cross-skill-contract.md && echo "HYPO OK"
grep -q "图谱目录" cross-skill-contract.md && echo "FIG OK"
grep -q "model-ref.pointer" cross-skill-contract.md && echo "PTR OK"
grep -q "预注册 by pv-model-analysis" cross-skill-contract.md && echo "REG OK"
```
Expected: `HYPO OK`, `FIG OK`, `PTR OK`, `REG OK`.

- [ ] **Step 3: Commit**

```bash
cd "/Users/tqa946816/Documents/华为/光伏预测/结果分析skill"
git add pv-model-analysis/references/cross-skill-contract.md
git commit -m "docs: cross-skill-contract.md — hypotheses/figure-catalog interface + H-ID registration"
```

---

## Phase C — Producer SKILL.md rewrite

### Task 8: Rewrite `pv-model-analysis/SKILL.md` into the producer workflow

**Files:**
- Modify: `pv-model-analysis/SKILL.md` (body below the frontmatter — full rewrite of the workflow)

**Interfaces:**
- Consumes: `references/machinery.md`, `references/output-spec.md`, `references/models-template.md`, `references/cross-skill-contract.md`, `scripts/pointer.py`, `scripts/profile_data.py`.
- Produces: the documented 6-step pipeline (locate → optional profile → per-model subagent extract → reconcile → write docs+pointer → self-check).

- [ ] **Step 1: Replace the SKILL.md body**

Keep the frontmatter from Task 1. Replace everything after it with a workflow that documents these six steps (write full prose; the reference files carry the detail, link to them):

```markdown
# 模型代码 → 模型参考文档（供人 + 供 pv-result-analysis）

给定模型代码目录，生成 `<repo>/.modelmap/` 文档集并写 pointer。既能从零生成，也能对已有产物
按代码增量核验（reconcile）。纪律与产物格式见 `references/`。

产物固定位置：`<repo>/.modelmap/`；pointer 固定路径见 `references/output-spec.md`。

## Step 0：定位模型（先问后花）
按 `references/models-template.md` 的「定位速查表」grep 类名定位 M1-M4 + Chronos 用法 +
ensemble 组合器；类名搬走了用架构签名兜底。确认 类名→M-id 映射。多候选版本（实验副本/旧文件）
→ 列候选请用户确认哪个是产线，绝不自行裁决。某模型定位不到 → 报"未找到"，该节留空，不硬套。

## Step 1：（可选）数据画像
用户给了数据样本 → 跑 `scripts/profile_data.py` 落 `data-profile.md`，把"为什么"从 📐 升 📊；
没给则静默跳过。

## Step 2：逐模型抽取（一模型一子代理，写完即忘；无子代理则串行）
每个模型产出三层（纪律见 `references/machinery.md`）：
- 工程（✅ `file:line`）：输入通道与维度、切 patch、模块、**读实际代码的损失**、训练窗口。
- 数学（📐）：每个方法（Fourier tokenizer、MoBA、RevIN、pinball≡4.5·MAE、MSE+rfft、Moirai…）。
- 桥接（架构→结果分析含义）：架构事实 → 预期误差形态 → 哪张图检验 → H-ID。桥接须遵
  `references/cross-skill-contract.md`（读 hypotheses.md + 图谱目录，H-ID 写回登记）。
核验优先级：损失函数 > 输入特征 > 训练窗口 > 其余结构。

## Step 3：Reconcile（统一核验流）
已有 `.modelmap/` 且仓库未变（commit 命中）→ 复用；变了 → 重抽取、与旧产物 diff，改动条目带
日期锚 `【代码核验 YYYY-MM-DD，来源 file:line】`；**前提被推翻的桥接假设必须重推**（不留半新半旧）。

## Step 4：落盘 + 写 pointer
按 `references/output-spec.md` 写 `.modelmap/` 全套（models.md 结构照 `references/models-template.md`）；
用 `scripts/pointer.py` 的 `write_pointer` 写 pointer（commit 取 `git -C <repo> rev-parse HEAD`，
无 git 用 `no-git`）。

## Step 5：自检（强制）
跑 `references/machinery.md` 第 5 节：落盘后置条件 + 锚点抽查 + 链接 + 覆盖 + 无裸断言，
末尾给自检报告。

## 纪律
- 证据强度：代码 > 推导 > 空白；多版本"哪个是产线"由用户定。
- "代码里没找到" ≠ "不存在"——未找到留空，不编造。
- 每处结论带置信标签 + `file:line`；未知永远显式。
- 产出后 `.modelmap/` 三层（事实 / 待确认 / 桥接假设）必须自洽。
```

- [ ] **Step 2: Verify all six steps, all four reference files, and the pointer script are referenced**

Run:
```bash
cd "/Users/tqa946816/Documents/华为/光伏预测/结果分析skill/pv-model-analysis"
for s in "Step 0" "Step 1" "Step 2" "Step 3" "Step 4" "Step 5"; do
  grep -q "$s" SKILL.md && echo "OK $s" || echo "MISSING $s"
done
for r in machinery.md output-spec.md models-template.md cross-skill-contract.md pointer.py; do
  grep -q "$r" SKILL.md && echo "OK $r" || echo "MISSING $r"
done
```
Expected: six `Step` OKs + five reference OKs.

- [ ] **Step 3: Commit**

```bash
cd "/Users/tqa946816/Documents/华为/光伏预测/结果分析skill"
git add pv-model-analysis/SKILL.md
git commit -m "feat: rewrite pv-model-analysis SKILL.md into the producer workflow"
```

---

## Phase D — Consumer rewiring (`pv-result-analysis`)

### Task 9: Preserve nuance, delete the hand-dictated `models.md`, add the locate-or-produce brief

**Files:**
- Delete: `pv-result-analysis/references/models.md`
- Modify: `pv-result-analysis/references/subagent-briefs.md` (append a brief)

**Interfaces:**
- Produces: a subagent brief named "模型参考：定位或生成" that Task 10's SKILL edits point to.

**Note:** Task 6 already lifted the archive's *structure* into `models-template.md`, so deleting the values here loses no reusable structure.

- [ ] **Step 1: Delete the dictated archive**

```bash
cd "/Users/tqa946816/Documents/华为/光伏预测/结果分析skill"
git rm pv-result-analysis/references/models.md
```

- [ ] **Step 2: Append the locate-or-produce brief**

Append to `pv-result-analysis/references/subagent-briefs.md`:

```markdown
## Brief: 模型参考——定位或生成（Stage 4 / Playbook B 前置）

触发：分析进入机制层（Stage 4 / Playbook B）需要"模型看得见/看不见什么"这类事实时。

1. 读固定 pointer：`references/model-ref.pointer`。
   - 存在且 `path` 指向的 `.modelmap/models.md` 在盘上 → 直接读它作为模型参考。
     - 额外：`git -C <pointer.repo> rev-parse HEAD` 与 `pointer.commit` 不一致 → 提示"模型档案可能
       已过时，建议重跑 pv-model-analysis"，但先用现有档案继续（不阻塞分析）。
   - pointer 不存在，或 `path` 不在盘上 → 向用户要模型代码目录路径，派子代理执行
     **pv-model-analysis** 技能于该目录；产出 `.modelmap/` + pointer 后再读 models.md。
2. 消费纪律：只引用带 ✅/📊/📐 且前提清晰的字段；⚠️/待确认/缺失一律按未知，不编造。
3. 桥接假设里的 H-ID 直接对应 `references/hypotheses.md`；落 FINDINGS 前照常过 H-ID 门。
```

- [ ] **Step 3: Verify**

Run:
```bash
cd "/Users/tqa946816/Documents/华为/光伏预测/结果分析skill"
test ! -f pv-result-analysis/references/models.md && echo "MODELS.MD GONE"
grep -q "模型参考——定位或生成" pv-result-analysis/references/subagent-briefs.md && echo "BRIEF OK"
grep -q "model-ref.pointer" pv-result-analysis/references/subagent-briefs.md && echo "PTR OK"
grep -q "pv-model-analysis" pv-result-analysis/references/subagent-briefs.md && echo "TRIGGER OK"
```
Expected: `MODELS.MD GONE`, `BRIEF OK`, `PTR OK`, `TRIGGER OK`.

- [ ] **Step 4: Commit**

```bash
git add -A
git commit -m "feat: pv-result-analysis consumes model ref via pointer; delete dictated models.md"
```

---

### Task 10: Repoint every `models.md` reference in `pv-result-analysis/SKILL.md`

**Files:**
- Modify: `pv-result-analysis/SKILL.md` (lines ~82, ~84, ~209, ~219, ~229 — every `models.md` mention)

- [ ] **Step 1: Update the references-table row (line ~219)**

Replace the table row:
```
| `models.md` | 模型间对比归因时读（架构/特征/训练窗口） |
```
with:
```
| 模型参考（`.modelmap/models.md`，经 `references/model-ref.pointer` 定位；缺失则子代理跑 pv-model-analysis 生成，见 subagent-briefs.md） | 模型间对比归因时读（架构/特征/训练窗口/桥接假设）；只引用带置信标签的已填字段 |
```

- [ ] **Step 2: Update the discipline note (line ~229)**

Replace the sentence:
```
`models.md` 由用户口述、可能与代码有出入：用户给代码仓库路径要求核验时，走配套技能 **`pv-model-verify`**。
```
with:
```
模型参考不再是口述档案：由配套技能 **`pv-model-analysis`** 从模型代码生成（代码锚定、带置信标签），存于 `<repo>/.modelmap/`，经 `references/model-ref.pointer` 定位；pointer 缺失/过时则按 `subagent-briefs.md` 的"模型参考——定位或生成"派子代理生成后再读。
```

- [ ] **Step 3: Update the remaining inline mentions (lines ~82, ~84, ~209)**

At each remaining occurrence, replace the bare token `models.md` with `模型参考（.modelmap/models.md）` and leave the surrounding sentence intact. (Line 84 `models.md 该节为空` → `模型参考里 ensemble 节为空`; line 82 and 209 `models.md/…` → `模型参考/…`.)

- [ ] **Step 4: Verify no bare `models.md` remains except the new pointer-qualified mentions**

Run:
```bash
cd "/Users/tqa946816/Documents/华为/光伏预测/结果分析skill"
echo "--- remaining models.md mentions (should all be .modelmap/ or pointer-qualified) ---"
grep -n "models\.md" pv-result-analysis/SKILL.md
grep -q "model-ref.pointer" pv-result-analysis/SKILL.md && echo "PTR REF OK"
grep -q "pv-model-analysis" pv-result-analysis/SKILL.md && echo "SKILL REF OK"
! grep -q "pv-model-verify" pv-result-analysis/SKILL.md && echo "NO STALE VERIFY"
```
Expected: every printed line is `.modelmap/`- or pointer-qualified; `PTR REF OK`, `SKILL REF OK`, `NO STALE VERIFY`.

- [ ] **Step 5: Commit**

```bash
git add pv-result-analysis/SKILL.md
git commit -m "feat: repoint pv-result-analysis model-ref lookups to pointer/.modelmap"
```

---

### Task 11: Log the change in `pv-result-analysis/CHANGELOG.md`

**Files:**
- Modify: `pv-result-analysis/CHANGELOG.md` (append one row; do not touch historical rows)

- [ ] **Step 1: Append the changelog row**

Add one row to the table (matching the existing `日期 | 改哪节 | 触发反馈 | 为什么` format):

```
| 2026-07-13 | 模型参考改为经 model-ref.pointer 定位 `.modelmap/models.md`；删除口述 models.md；配套技能改名 pv-model-analysis（生成式） | 用户要求：模型档案由代码生成、供人+供分析消费，分析时定位或触发生成 | 口述档案会漂移；代码锚定 + 置信标签让归因前提可靠、可增量核验 |
```

- [ ] **Step 2: Verify**

Run: `grep -q "model-ref.pointer" "/Users/tqa946816/Documents/华为/光伏预测/结果分析skill/pv-result-analysis/CHANGELOG.md" && echo "CHANGELOG OK"`
Expected: `CHANGELOG OK`

- [ ] **Step 3: Commit**

```bash
cd "/Users/tqa946816/Documents/华为/光伏预测/结果分析skill"
git add pv-result-analysis/CHANGELOG.md
git commit -m "docs: changelog — pointer-based model reference + pv-model-analysis rename"
```

---

## Phase E — Repo-wide consistency + memory

### Task 12: Sweep stale `pv-model-verify` references

**Files:**
- Modify: `README.md` (lines 20, 38), `结果分析Skill介绍.md` (lines 185, 189), `pv-station-influence/SKILL.md` (line 3 description)

- [ ] **Step 1: Update README.md**

- Line 20: `ln -s "$(pwd)/pv-model-verify"  ~/.claude/skills/pv-model-verify` → `ln -s "$(pwd)/pv-model-analysis"  ~/.claude/skills/pv-model-analysis`
- Line 38: `- 模型档案核验：\`/pv-model-verify\` 并给出模型代码仓库路径。` → `- 模型参考生成/核验：\`/pv-model-analysis\` 并给出模型代码仓库路径（产出 .modelmap，供 pv-result-analysis 消费）。`

- [ ] **Step 2: Update 结果分析Skill介绍.md**

- Line 185 (the table row for `pv-model-verify`): rename the skill to `pv-model-analysis` and change the description to "从模型代码**生成**代码锚定的模型参考（工程流程图 + 数学 + 架构→含义桥接），供人阅读并供 pv-result-analysis 消费；亦可对已有产物按代码增量核验".
- Line 189 (两者关系): replace `pv-model-verify 保证分析的输入前提（模型档案）正确` with `pv-model-analysis 从代码生成模型参考（存 .modelmap，经 model-ref.pointer 定位）`, and keep the rest of the sentence about `pv-result-analysis` executing the main flow.

- [ ] **Step 3: Update pv-station-influence/SKILL.md description**

Line 3: change the parenthetical `pv-model-verify（模型档案代码核验）` to `pv-model-analysis（从代码生成/核验模型参考）`.

- [ ] **Step 4: Verify no unintended stale references remain**

Run:
```bash
cd "/Users/tqa946816/Documents/华为/光伏预测/结果分析skill"
echo "--- pv-model-verify mentions left (expect ONLY historical CHANGELOG + docs/superpowers/specs) ---"
grep -rn "pv-model-verify" --include="*.md" . | grep -v "/.git/"
```
Expected: only `pv-result-analysis/CHANGELOG.md` historical rows and `docs/superpowers/` design/plan files appear (those are history — leave them).

- [ ] **Step 5: Commit**

```bash
git add README.md 结果分析Skill介绍.md pv-station-influence/SKILL.md
git commit -m "docs: sweep pv-model-verify -> pv-model-analysis across README/intro/sibling skill"
```

---

### Task 13: Update persistent memory

**Files:**
- Modify: `/Users/tqa946816/.claude/projects/-Users-tqa946816-Documents-------------skill/memory/MEMORY.md`
- Modify: `/Users/tqa946816/.claude/projects/-Users-tqa946816-Documents-------------skill/memory/pv-forecast-result-analysis-skill.md`

- [ ] **Step 1: Read the current skill-memory file**

Run: `cat "/Users/tqa946816/.claude/projects/-Users-tqa946816-Documents-------------skill/memory/pv-forecast-result-analysis-skill.md"`
(Read it before editing so the edit matches existing content.)

- [ ] **Step 2: Record the architecture change**

In `pv-forecast-result-analysis-skill.md`, add a fact: `pv-model-verify` renamed to `pv-model-analysis`; it is now a **producer** (model code → `<repo>/.modelmap/` with pipeline.md/math.md/models.md + bridge hypotheses), discovered by `pv-result-analysis` via the fixed `references/model-ref.pointer`; the hand-dictated `models.md` was deleted. Link `[[pv-forecast-result-analysis-skill]]`.

In `MEMORY.md`, update the existing PV pointer line so any `pv-model-verify` wording becomes `pv-model-analysis` and mention the pointer-based model reference.

- [ ] **Step 3: Verify**

Run:
```bash
M="/Users/tqa946816/.claude/projects/-Users-tqa946816-Documents-------------skill/memory"
grep -q "pv-model-analysis" "$M/pv-forecast-result-analysis-skill.md" && echo "SKILL MEM OK"
grep -q "model-ref.pointer" "$M/pv-forecast-result-analysis-skill.md" && echo "PTR MEM OK"
```
Expected: `SKILL MEM OK`, `PTR MEM OK`

- [ ] **Step 4: Commit**

Memory lives outside the repo, so no repo commit is needed for the memory files. Make a final no-op verification that the working tree is clean of plan-related changes:
```bash
cd "/Users/tqa946816/Documents/华为/光伏预测/结果分析skill"
git status --short
```
Expected: only pre-existing unrelated modifications (the `M pv-analysis-resume/SKILL.md` etc. that predate this work), nothing from this plan uncommitted.

---

## Self-Review (completed by plan author)

**Spec coverage:** D1 unified reconcile → Task 8 Step 3. D2 description+bridge → Tasks 5/6/8 (three layers). D3 rename → Task 1 + sweep Task 12. D4 pointer discovery → Tasks 3/5/9/10. D5 lean import → Tasks 2/4 (machinery+scripts, no extra modes). Cross-skill contract → Task 7 + Task 9 brief. Output file set → Task 5. Consumer rewiring → Tasks 9–11. Memory → Task 13. All spec sections mapped.

**Placeholder scan:** No TBD/TODO; every doc task shows the actual content to write and a concrete grep/pytest verification; scripts show full code.

**Type consistency:** `write_pointer`/`read_pointer`/`is_stale` signatures defined in Task 3 are used identically in Task 8 (`write_pointer`) and Task 9/10 (pointer read + `is_stale` staleness check). Pointer keys (`path/repo/commit/date/models`) match across Tasks 3, 5, 9, 10. `.modelmap/` filenames match across Tasks 5, 6, 8, 9, 10.
