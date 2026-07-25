# Playbook 分层 Phase 2 实施计划（6 playbook 批量改造 + contexts 退役 + 加固）

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 把剩余 6 个分析 playbook（result-eval / deployment-drift / robustness / feature-importance / subset-influence / training-sufficiency）改造到 produces/upstream 机制，退役 contexts: 机制，落地 Phase 1 终审移交的加固项。

**Architecture:** 沿用 Phase 1 已落地的机制（`produces`/`upstream` frontmatter + orient 机器裁决 + products 注册表 + 指纹过期检测），本阶段只做声明改造与 prose 手术，不加新机制——唯二的引擎代码变更是 contexts 代码路径删除（Task 7）与 product_manifest.py 的 `--input` 扩展 + setup_manifest 时间序修正（Task 8）。**本阶段不做任何阶段重编号**：deployment-drift 的 Stage 0 只挖掉适配器部分保留误差序列计算，全部 golden manifest 的 stage 键原样不动。

**Tech Stack:** Python 3 + pytest（`ts-diagnose/scripts/tests/`，当前 160 绿）；playbook = YAML frontmatter + 中文 Markdown 正文。

## Global Constraints

- 每个 task 结束时 `python3 -m pytest ts-diagnose/scripts/tests -q` 全绿（初始 160 个，逐 task 递增）。
- SKILL.md ≤60 行（test_routing 锁定）；本计划不改 SKILL.md。
- **Layer-1 独立性守卫**（test_layering）：playbook 正文出现另一 playbook 的字面 id，仅当对方是自己声明的 provider（contexts.provider_playbook ∪ upstream 推导的生产者）才合法。改造后 upstream 推导即白名单；prose 若触守卫且不该声明依赖，按 Phase 1 判例改写为非 id 措辞（如「体检类 playbook」）。
- **提问去重守卫**（validate_upstream，load_frontmatter 时执行）：消费者不得重复声明生产者拥有的问题。data-setup 拥有 `freq` 与 `align-keys`——声明 `upstream: setup` 的 playbook 必须删掉自己的同 id 问题。
- **materials 块除 Task 4（feature-importance）外一律不动**：robustness / training-sufficiency 现在不声明 materials，modelmap_blocker 对它们照常生效（Phase 1 豁免收窄的前提），加 materials 块会静默改变闸行为。
- **产物 id 全引擎唯一**：本计划新增 `eval_report`（生产者 result-eval）。生产者工作目录按产物 id 命名（`<root>/eval_report/`）。
- 可选生产者必须写进 upstream 逐条机器问（用户 2026-07-25 明确要求，见 phase2-TODO 第 0 条）：凡消费图的分析 playbook 声明 `chart_sweep (optional)`；机制归因类声明 `model_profile (optional)`。
- 提交信息风格：`feat(ts-diagnose): <一句话>——<机制/理由>`，中文。
- 分支：`playbook-layering-phase2`，自 main 切出。

## 改造总表（每 task 的目标状态）

| playbook | upstream | produces | contexts | charts 收窄 | 问题变更 |
|---|---|---|---|---|---|
| result-eval | setup(req) + model_profile(opt) + chart_sweep(opt) | **eval_report**（新） | 删 model-profile | 11→5 | 无 |
| deployment-drift | setup(req) + model_profile(opt) + chart_sweep(opt) | — | 删 model-profile | 10→4 | 删 align-keys |
| robustness | setup(req) + chart_sweep(opt) | — | （本无） | 无 charts，维持 | metric-and-pairing 去路径问 |
| feature-importance | setup(req) | — | （本无） | 无 charts，维持 | importance-scope 去路径问 |
| subset-influence | setup(req) + model_profile(opt) + eval_report(opt) | — | 删 heldout-eval | 无 charts，维持 | 无 |
| training-sufficiency | setup(**opt**) | — | （本无） | 无 charts，维持 | 无（prose 注记免问日志位置） |

设计裁决记录（执行者不需重新决策）：
- **不重编号**：deployment-drift 原 Stage 0「口径与对齐」= 薄适配器 + error_series.py 两件事。适配器归 setup，error_series.py 是分析活留下——Stage 0 更名「误差序列（口径）」，1..5 原样。全计划零 golden stage 键平移（phase2-TODO 第 2 条按此落空，属预期）。
- **robustness 不加默认 charts**：其证据产物是 JSON 矩阵（perturbation_matrix/group_slices），「切分稳定组」由 group_slices.json 承担；cross-dim-stability 留可加画池。TODO 里的"图组"措辞只约束 result-eval / deployment-drift 两个带 charts 的 playbook。
- **modelmap_blocker 保留不降级**（TODO 第 4 条裁决）：variants 无法表达"material 出现时 optional 自动升 required"，现闸有测试有判例，YAGNI。Task 9 在 engine_common.py 该函数 docstring 补一行裁决记录。
- **profile 不携带 products 登记**（TODO 第 5 条裁决）：产物是每次运行的现场事实（同 degraded_ok）。Task 9 在 crystallize.md 补一行，不改代码。

---

### Task 1: result-eval 改造（含新产物 eval_report）

**Files:**
- Modify: `ts-diagnose/playbooks/result-eval/playbook.md`
- Test: `ts-diagnose/scripts/tests/test_products.py`

**Interfaces:**
- Produces: 产物 id `eval_report`（manifest `gate_reports/conclusion_gate.json`，marker `CONCLUSION.md`）——Task 5 的 subset-influence 以 upstream 引用它；REAL_UPSTREAM 守卫表（本 task 创建，后续 task 逐行追加）。

- [ ] **Step 1: 写失败守卫测试**——在 `test_products.py` 末尾新增真实 playbook 层的表驱动守卫（后续每个转换 task 往表里加一行）：

```python
# ------------------------------------------------------------ 真实 playbook 转换守卫
# Phase 2 逐个转换的目标态：upstream 声明表 + contexts 必须清空。
# 每转换一个 playbook 加一行——表驱动，红→绿即转换完成的机器判据。
REAL_UPSTREAM = {
    "model-comparison": {"setup": True, "model_profile": False, "chart_sweep": False},
    "result-eval": {"setup": True, "model_profile": False, "chart_sweep": False},
}
REAL_PRODUCES = {
    "data-setup": "setup",
    "model-audit": "model_profile",
    "fact-scan": "chart_sweep",
    "result-eval": "eval_report",
}


def test_real_playbooks_upstream_table():
    for pid, expect in REAL_UPSTREAM.items():
        path = os.path.join(ec.PLAYBOOKS_DIR, pid, "playbook.md")
        fm = ec.load_frontmatter(path)
        ups = {u["product"]: bool(u.get("required"))
               for u in (fm.get("upstream") or [])}
        assert ups == expect, f"{pid} upstream 声明与目标态不符：{ups}"
        assert not fm.get("contexts"), f"{pid} 已转换却仍残留 contexts 声明"


def test_real_playbooks_produces_table():
    idx = ec.products_index()
    for pid, prod in REAL_PRODUCES.items():
        assert prod in idx and idx[prod]["playbook"] == pid, \
            f"产物 {prod} 应由 {pid} 生产，实际：{idx.get(prod)}"
```

注意：本文件顶部若无 `ec.PLAYBOOKS_DIR` 可用则沿用文件内既有的真实引擎目录定位方式（test_products.py 的 sandbox fixture 是 monkeypatch 版，本测试要用真实目录——参考 test_charts_decl.py 的 `ENGINE` 常量写法，勿在 sandbox fixture 内跑）。

- [ ] **Step 2: 跑测试确认失败**

Run: `python3 -m pytest ts-diagnose/scripts/tests/test_products.py -k real_playbooks -v`
Expected: FAIL——result-eval 无 upstream 声明、eval_report 不在 products_index。

- [ ] **Step 3: 改 frontmatter**。对 `result-eval/playbook.md`：
  1. 在 `materials:` 块之前插入：

```yaml
produces:
  id: eval_report
  manifest: gate_reports/conclusion_gate.json
  marker_files: [CONCLUSION.md]
upstream:
  - product: setup
    required: true
  - product: model_profile
    required: false
  - product: chart_sweep
    required: false
```

  2. Stage 0 的 prereqs 增加一条（放在 metric-caliber 之前）：

```yaml
      - desc: setup 产物就绪
        check: "product:setup"
```

  3. Stage 2 的 `charts:` 收窄为（11→5，月度/时段归因组）：

```yaml
    charts: [error-breakdown, intraday-profile, worst-points,
             rolling-stability, cross-dim-stability]
```

  4. 删除整个 `contexts:` 块（frontmatter 末尾 model-profile 一段）。

- [ ] **Step 4: 正文手术**（逐条，anchor 用现文件行文）：
  1. **§2 Stage 0「路径与质检」**：改名「质检（消费 setup 长表）」。删除菜谱第 1、2 条（找路径/找 metric.py 的内容——路径收集已由 setup 的材料盘点承接；外部指标脚本路径若用户提过会在 config.materials/questions 里）。菜谱第 3 条开头改为：「**质检对象是 setup 产物的规范长表**（orient 注入的 manifest 摘要给出 predictions.csv 位置与模型清单，不再自行摸文件）。复用 `<本 playbook 目录>/scripts/run_quality_check.py`（…原文其余不动）」。第 4 条（可疑日二分）不动。
  2. **§1 首要陷阱**「滚动窗口重叠陷阱」条目末尾补一句：「滚动窗口结构与重叠步数在 setup 适配时已确认并记入 alignment_report——本 playbook 直接读，不重新猜。」
  3. **§2 Stage 2**：命令模板段后补一段：「**chart_sweep 产物 built/linked 时**：与本阶段声明重叠的图直接复用其 charts/*.json 判读，不重画；只补画本组缺的图。」
  4. **§7 材料降级说明** `model_code` 条：把「`model-profile` 上下文保持 absent」改为「`model_profile` 产物保持 absent/declined」。
  5. **§8 chartbook 覆盖声明** 重写为（全文替换该节正文）：

```
声明进 Stage 2 charts（月度/时段归因组）：error-breakdown、intraday-profile、
worst-points、rolling-stability、cross-dim-stability。

跳过（默认不画，可经图表选择门加画或复用 chart_sweep 产物；逐条理由）：
true-vs-pred-scatter / horizon-degradation——单结果广谱体检图，体检类 playbook
的 chart_sweep 产物覆盖，按需复用；
train-test-drift——漂移专项（需 train_y），归 Stage 4 深挖时按需加画；
feature-error-conditional / feature-trend-overlay / y-vs-feature-mapping——输入侧
归因三件套（需 features），Stage 4 点名输入侧假设时加画；
model-error-correlation / oracle-gap / worst-slice-compare /
model-rank-significance / baseline-skill——多模型对比定位，本目标主线是单一结果
质量归因，present ≥2 模型时可加画；
global-attribution / local-waterfall / lookback-decay——需 serving_api，结构性不适用；
bad-window-clustering / good-bad-contrast / error-acf / pp-calibration /
theil-decomposition / time-shift-diagnosis / horizon-error-quantiles——误差结构
补充切面，可加画池。
```

  6. 全文 grep `model-audit`/`fact-scan`/`data-setup` 字面 id：本 playbook 现在 upstream 推导的 provider = data-setup、model-audit、fact-scan，字面引用合法，无需改写；但检查文中旧「上下文/contexts」措辞统一改「上游产物」。

- [ ] **Step 5: 跑守卫测试转绿 + 全量**

Run: `python3 -m pytest ts-diagnose/scripts/tests -q`
Expected: 全绿（新增 2 个测试通过；`test_all_real_playbooks_frontmatter_loads` 顺带验证 frontmatter 合法）。

- [ ] **Step 6: Commit**

```bash
git add ts-diagnose/playbooks/result-eval/playbook.md ts-diagnose/scripts/tests/test_products.py
git commit -m "feat(ts-diagnose): result-eval 转两层——upstream setup/model_profile/chart_sweep + 新产物 eval_report，图 11→5"
```

---

### Task 2: deployment-drift 改造

**Files:**
- Modify: `ts-diagnose/playbooks/deployment-drift/playbook.md`
- Test: `ts-diagnose/scripts/tests/test_products.py`（REAL_UPSTREAM 加行）

**Interfaces:**
- Consumes: Task 1 的 REAL_UPSTREAM 表。
- Produces: 无新接口。**不重编号**：Stage 0 只去适配器保留 error_series，golden stages 键 `1`/`3` 原样。

- [ ] **Step 1: REAL_UPSTREAM 加行（红）**

```python
    "deployment-drift": {"setup": True, "model_profile": False, "chart_sweep": False},
```

Run: `python3 -m pytest ts-diagnose/scripts/tests/test_products.py -k upstream_table -v` → FAIL。

- [ ] **Step 2: 改 frontmatter**：
  1. `stages:` 之前插入：

```yaml
upstream:
  - product: setup
    required: true
  - product: model_profile
    required: false
  - product: chart_sweep
    required: false
```

  2. Stage 0 更名 `误差序列（口径）`，prereqs 改为：

```yaml
    prereqs:
      - desc: setup 产物就绪
        check: "product:setup"
      - desc: 考核口径已定
        check: "question:metric-caliber"
      - desc: 上线/训练截止时间已知
        check: "question:deploy-timeline"
```

（即删除 align-keys prereq；对齐由 setup 完成。）
  3. Stage 4 prereq 的 check 由 `"config:model_profile_status"` 改为 `"config:products.model_profile.status"`，desc 改「模型档案产物已解决（built/linked 或 declined）」。
  4. Stage 2 `charts:` 收窄为（10→4，时序稳定组）：

```yaml
    charts: [rolling-stability, intraday-profile, error-breakdown, train-test-drift]
```

  5. `questions:` 删除整个 `align-keys` 条目（data-setup 拥有；不删则 load_frontmatter 因提问去重直接报错——这就是机器强制）。
  6. 删除整个 `contexts:` 块。

- [ ] **Step 3: 正文手术**：
  1. **§2 Stage 0**：标题改「Stage 0 误差序列（口径）」。删除「写薄适配器 …样例 chartbook/golden/example_adapter/，记录写 PROGRESS.md。随后」这段适配器文字；改为「输入：setup 产物的规范长表 predictions.csv（orient 注入 manifest 摘要；features/train_y 长表若 setup 产了同样直接用）。菜谱：写 `analysis_scripts/error_series.py`：…（其余原文不动）」。
  2. **§2 Stage 2** 命令模板段后补：「**chart_sweep 产物 built/linked 时**：重叠图直接复用其 charts/*.json 判读，不重画。」
  3. **§7 材料降级** 与 **§8 覆盖声明**：§8 重写为：

```
声明进 Stage 2 charts（时序稳定组）：rolling-stability（时间形态主图）、
intraday-profile（退化的物理时刻集中度）、error-breakdown（前后段构成对照，
喂反驳门③）、train-test-drift（"世界变了"候选）。

跳过（可加画池或复用 chart_sweep 产物）：horizon-degradation /
true-vs-pred-scatter / worst-points——广谱体检切面，体检类 playbook 覆盖；
feature-error-conditional / feature-trend-overlay / y-vs-feature-mapping——
输入侧三件套，Stage 3 诱因筛查有专用脚本 cause_screen.py，图形佐证按需加画；
model-error-correlation / oracle-gap / worst-slice-compare /
cross-dim-stability——需 ≥2 模型，本目标单模型；单模型正交稳定性由 Stage 1
interleave 与口径子段复算承担。
```

  4. 全文把「模型档案上下文」措辞改「模型档案产物」；grep `contexts` 残留清零。

- [ ] **Step 4: 全量测试**

Run: `python3 -m pytest ts-diagnose/scripts/tests -q` → 全绿。另跑金标准确认零漂移：
`cd ts-diagnose/playbooks/deployment-drift && python3 ../../scripts/gen_gate.py --script golden/reference/changepoint.py --playbook deployment-drift --stage 1 && python3 ../../scripts/gen_gate.py --script golden/reference/cause_screen.py --playbook deployment-drift --stage 3`
Expected: 两闸 PASS（stage 键没动，reference 脚本原样过）。

- [ ] **Step 5: Commit**

```bash
git add ts-diagnose/playbooks/deployment-drift/playbook.md ts-diagnose/scripts/tests/test_products.py
git commit -m "feat(ts-diagnose): deployment-drift 转两层——适配器出 Stage 0 归 setup，align-keys 让渡，图 10→4"
```

---

### Task 3: robustness 改造

**Files:**
- Modify: `ts-diagnose/playbooks/robustness/playbook.md`
- Test: `ts-diagnose/scripts/tests/test_products.py`（REAL_UPSTREAM 加行）

- [ ] **Step 1: REAL_UPSTREAM 加行（红）**

```python
    "robustness": {"setup": True, "chart_sweep": False},
```

- [ ] **Step 2: 改 frontmatter**：
  1. `stages:` 之前插入：

```yaml
upstream:
  - product: setup
    required: true
  - product: chart_sweep
    required: false
```

  2. Stage 0 prereqs 头部加：

```yaml
      - desc: setup 产物就绪
        check: "product:setup"
```

  3. `metric-and-pairing` 问题的 ask 改为：

```yaml
    ask: "评估指标是什么、按什么单位配对？（如按天配对的 RMSE、按 fold 配对的 loss；数据一律来自 setup 产物的规范长表，不再另给路径）"
```

  4. **materials 块保持不存在**（Global Constraints：modelmap_blocker 行为不动）。

- [ ] **Step 3: 正文手术**：
  1. **§2 Stage 0** 首条改为：「按 `metric-and-pairing` 答案，**从 setup 产物的 predictions.csv**（orient 注入 manifest 摘要）重算被检结论涉及的全部指标（不信任来路数字，自己算一遍），逐配对单位落长表 + 汇总。…（schema 原文不动）」。
  2. **§2 开头**（"脚本生成进 analysis_scripts/"段前）补一段：「广谱图形证据（如切片翻向的可视化）不属本 playbook 默认产物——chart_sweep 产物 built/linked 时直接复用其图 JSON；需要跨维稳定图时经图表选择门加画 cross-dim-stability。」

- [ ] **Step 4: 全量测试** → 全绿。

- [ ] **Step 5: Commit**

```bash
git add ts-diagnose/playbooks/robustness/playbook.md ts-diagnose/scripts/tests/test_products.py
git commit -m "feat(ts-diagnose): robustness 转两层——基线复算改消费 setup 长表，配对问题去路径问"
```

---

### Task 4: feature-importance 改造

**Files:**
- Modify: `ts-diagnose/playbooks/feature-importance/playbook.md`
- Test: `ts-diagnose/scripts/tests/test_products.py`（REAL_UPSTREAM 加行）

**Interfaces:**
- 本 task 是唯一动 materials 块的转换：`required: [predict, truth, features]`（相关筛查没有特征序列做不了；predict/truth 是误差目标的最小闭环，且 setup 内联生产需要盘点记录可拷）。原 optional 两材料线（feature_true/serving_api）一字不动。

- [ ] **Step 1: REAL_UPSTREAM 加行（红）**

```python
    "feature-importance": {"setup": True},
```

- [ ] **Step 2: 改 frontmatter**：
  1. `stages:` 之前插入：

```yaml
upstream:
  - product: setup
    required: true
```

  2. Stage 0 更名 `相关筛查（对齐由 setup 承接）`，prereqs 头部加：

```yaml
      - desc: setup 产物就绪
        check: "product:setup"
```

  3. `materials:` 块改为：

```yaml
materials:
  required: [predict, truth, features]
  optional: [feature_true, serving_api]
```

  4. `importance-scope` 问题的 ask 改为：

```yaml
    ask: "『重要』对什么口径说？（整体误差 / 某类时段或条件下的误差 / 某个业务指标）目标列取 setup 长表的哪个误差口径？"
```

（去掉「数据路径？」——路径已在材料盘点。）

- [ ] **Step 3: 正文手术**：
  1. **§2 Stage 0** 首条改为：「分析表 = **setup 产物的 features.csv × predictions.csv 逐窗误差**（orient 注入 manifest 摘要定位两表；对齐键与丢行数由 setup 的 alignment_report 披露，本阶段只做特征×误差的合表核对）；逐变量算…（其余原文不动）」。
  2. **§8 变体 counterfactual 之后的「两变体的材料降级说明」**：开头补一句「predict/truth/features 缺 → 本 playbook 不可做（升为 required，setup 内联生产时同样要求）」。

- [ ] **Step 4: 全量测试** → 全绿。特别确认 `test_materials.py` 的 modelmap 测试仍绿（本 playbook 声明 materials 但无 model_code → 豁免逻辑与改造前一致）。

- [ ] **Step 5: Commit**

```bash
git add ts-diagnose/playbooks/feature-importance/playbook.md ts-diagnose/scripts/tests/test_products.py
git commit -m "feat(ts-diagnose): feature-importance 转两层——对齐让渡 setup，features 升 required"
```

---

### Task 5: subset-influence 改造（heldout-eval 上下文 → eval_report 产物）

**Files:**
- Modify: `ts-diagnose/playbooks/subset-influence/playbook.md`
- Test: `ts-diagnose/scripts/tests/test_products.py`（REAL_UPSTREAM 加行）

**Interfaces:**
- Consumes: Task 1 声明的 `eval_report` 产物（result-eval 生产）。

- [ ] **Step 1: REAL_UPSTREAM 加行（红）**

```python
    "subset-influence": {"setup": True, "model_profile": False, "eval_report": False},
```

- [ ] **Step 2: 改 frontmatter**：
  1. `materials:` 之后、`variants:` 之前插入：

```yaml
upstream:
  - product: setup
    required: true
  - product: model_profile
    required: false
  - product: eval_report
    required: false
```

  2. 删除整个 `contexts:` 块（heldout-eval）。
  3. Stage 2 prereqs 的第二条（留出单元逐 chunk RMSE 序列）check 保持 `material:predict` 不动，但 desc 补「（setup 长表或日志解析）」。

- [ ] **Step 3: 正文手术**：
  1. **§4「留出单元预测侧上下文：与 result-eval 的接续」** 整节重写为：

```
## 4. 留出单元预测侧上游：eval_report 产物

本 playbook 的归因要以留出单元的预测侧分析（指标基线、分组条件、数据质量、现象清单）
为上游素材——即 frontmatter `upstream` 里的 `eval_report` 产物（可选），由
result-eval 生产。orient 按产物状态给指令：

- **built/linked**：直接消费该工作目录——指标表 = 留出单元基线；分组条件（如天气分型）
  = 归因分组变量；suspect_days.csv 一类质检产物 = 反驳门「数据质量」证据；FINDINGS
  现象 = 归因素材；漂移类图产物可直接复用于本 playbook Stage 4。
- **absent**：orient 打三分支问（现跑 / 链接已有 / 放弃）。现跑 = 在会话根目录
  `<root>/eval_report/` 内联执行 result-eval 至 CONCLUSION.md，登记
  `config.products.eval_report = {workdir, status: "built"}`。
- **declined**：继续 influence-only 分析，FINDINGS/CONCLUSION 须注明「缺预测侧上游」。
```

  2. **§5 逐阶段菜谱开头**的 data_utils 复用句：把「兄弟 playbook `result-eval/scripts/data_utils.py`」保留（result-eval 现在是 upstream 推导的合法 provider，字面 id 不再触 Layer-1 守卫；若守卫仍报错说明推导集缺 eval_report——先修声明不改守卫）。
  3. 全文 grep `heldout_eval_status` / `heldout_eval_dir` / `contexts`：残留清零（含 §10 材料降级、§9 结论模板里的措辞）。

- [ ] **Step 4: 全量测试** → 全绿（test_layering 对 result-eval 字面引用经 upstream 白名单放行是本 task 的隐性断言）。

- [ ] **Step 5: Commit**

```bash
git add ts-diagnose/playbooks/subset-influence/playbook.md ts-diagnose/scripts/tests/test_products.py
git commit -m "feat(ts-diagnose): subset-influence 转两层——heldout-eval 上下文改 eval_report 产物三分支"
```

---

### Task 6: training-sufficiency 改造（setup 为可选加速器）

**Files:**
- Modify: `ts-diagnose/playbooks/training-sufficiency/playbook.md`
- Test: `ts-diagnose/scripts/tests/test_products.py`（REAL_UPSTREAM 加行）

**Interfaces:**
- 语义与其他 5 个相反：**setup 是 optional**——本 playbook 的记录源是训练日志不是预测长表，没有 setup 照样能跑；setup built 时其 manifest.materials 记录的 training_log / experiment_config 位置免去重问。

- [ ] **Step 1: REAL_UPSTREAM 加行（红）**

```python
    "training-sufficiency": {"setup": False},
```

- [ ] **Step 2: 改 frontmatter**：`stages:` 之前插入：

```yaml
upstream:
  - product: setup
    required: false
```

（不加任何 stage prereq——orient 的三分支问在产物层，阶段推进不依赖它。materials 块保持不存在。）

- [ ] **Step 3: 正文手术**：**§2 Stage 0** 的「输入」条改为：「输入：question `loss-source` / `unit-structure` 的答案；config 里的日志/记录路径。**setup 产物 built/linked 时**：先读其 setup_manifest.json 的 materials 清单——training_log / experiment_config 的位置与格式已在 setup 盘点时记录，『在哪』免问直接用，`loss-source` 只补格式细节与样例行。」

- [ ] **Step 4: 全量测试** → 全绿。

- [ ] **Step 5: Commit**

```bash
git add ts-diagnose/playbooks/training-sufficiency/playbook.md ts-diagnose/scripts/tests/test_products.py
git commit -m "feat(ts-diagnose): training-sufficiency 转两层——setup 作可选加速器，日志位置从 manifest 免问"
```

---

### Task 7: contexts 机制退役

**Files:**
- Modify: `ts-diagnose/scripts/engine_common.py`（删 `context_status` / `context_embed_hint`；若有 contexts 专属解析/校验分支一并删）
- Modify: `ts-diagnose/scripts/orient.py`（删 `for cx in fm.get("contexts")` 循环整段）
- Modify: `ts-diagnose/playbooks/_playbook-spec.md`（删 contexts 声明节；upstream 节补「迁移完成，contexts 已退役」一句）
- Modify: `ts-diagnose/references/engine-core.md`（「嵌入执行 provider skill」相关措辞改为 upstream 产物内联生产的说法）
- Modify: `ts-diagnose/scripts/tests/test_engine.py`（删 contexts 节测试 ~200-215 行）
- Modify: `ts-diagnose/scripts/tests/test_materials.py`（删 `test_context_embed_hint_provider_playbook` 与 220-252 行的 contexts frontmatter 解析测试；`test_modelmap_blocker` 用的 fm 若含 contexts 字段改为不含——断言语义不变）
- Modify: `ts-diagnose/scripts/tests/test_orient_materials.py`（fixture 里的 contexts 块改写为 upstream 等价物或直接删除该配置——取决于该测试断言的是材料盘点不是上下文，读文件后择小者）
- Modify: `ts-diagnose/scripts/tests/test_layering.py`（`_declared_providers` 删 contexts 分支，只保留 upstream 推导；docstring 同步）

- [ ] **Step 1: 前置闸（红的另一种形态）**——先加退役守卫测试到 `test_layering.py`：

```python
def test_no_contexts_declarations_remain():
    """contexts 机制已退役——任何真实 playbook 不得再声明。"""
    for pid in os.listdir(PLAYBOOKS):
        path = os.path.join(PLAYBOOKS, pid, "playbook.md")
        if not os.path.isfile(path):
            continue
        fm = ec.load_frontmatter(path)
        assert not fm.get("contexts"), f"{pid} 仍声明 contexts——机制已退役"
```

Run: 应当**直接绿**（Task 1-6 已清空）——这是删代码前的安全网：先证明无调用方。同时 `grep -rn "contexts:" ts-diagnose/playbooks/*/playbook.md` 应零命中。

- [ ] **Step 2: 删代码与测试**（上面 Files 清单逐个执行）。engine_common 里若 `load_frontmatter` 对 contexts 有校验分支、`orient.py` 顶部有相关 import/辅助，一并删。**不删** `modelmap_blocker`（它读 MODELMAP_RECEIPT，不依赖 contexts——若发现依赖，停下报 BLOCKED，这是计划错误）。

- [ ] **Step 3: 全量测试** → 全绿（数量比 Task 6 后少若干个被删测试、多 1 个退役守卫）。`grep -rn "context_status\|context_embed_hint\|provider_playbook" ts-diagnose/scripts/ ts-diagnose/playbooks/_playbook-spec.md` 零命中（tests 目录 docstring 里的历史叙述除外，允许保留在 test_routing.py 文件头注释）。

- [ ] **Step 4: Commit**

```bash
git add -A ts-diagnose/
git commit -m "feat(ts-diagnose): contexts 机制退役——upstream 产物机制全面接管，删两函数一循环与配套测试"
```

---

### Task 8: 加固项打包（Phase 1 终审移交清单）

**Files:**
- Modify: `ts-diagnose/scripts/setup_manifest.py`（window_range 时间序）
- Modify: `ts-diagnose/scripts/product_manifest.py`（`--input` 追加外部输入指纹）
- Modify: `ts-diagnose/playbooks/fact-scan/playbook.md`（manifest 命令补 setup 依赖边）
- Modify: `docs/superpowers/specs/2026-07-25-playbook-layering-design.md`（§5/§6 勘误）
- Test: `ts-diagnose/scripts/tests/test_products.py`、`test_product_manifest.py`

五个子项，每项红→绿后一并提交：

- [ ] **Step 1（ht 指纹尾采样独立钉）**：`test_products.py` 加测试——monkeypatch `ec.FULL_HASH_MAX_BYTES = 8`、`ec.SAMPLE_BYTES = 4`，写 32 字节文件：改中段字节（offset 16）指纹**不变**（显式接受的残余风险，钉住语义）；只改最后 1 字节指纹**变**；只改第 1 字节指纹**变**。三断言缺一不可（Phase 1 的旧测试因 head/tail 重叠只证明了走 ht 路径）。

- [ ] **Step 2（optional-stale 行为钉）**：`test_products.py` 加测试——sandbox 里消费者声明 optional 产物，产物 built 后改其 manifest.inputs 指向的文件内容，跑 orient：输出含 `accept_stale` 指引且开工判定为「有 ✗ 先补」（optional 但 stale = 未决不一致，阻塞——Phase 1 Task 4 已定语义，本测试钉死防回归）。

- [ ] **Step 3（modelmap declined 专测）**：`test_materials.py` 加测试——`config.products.model_profile.status = "declined"` 且 model_code present、无 MODELMAP_RECEIPT：断言 `modelmap_blocker(cfg, fm) is not None`（declined ≠ 有档案，闸照落；用户放弃档案的路径是 conclusion 声明缺席，不是绕过 model-audit 强制）。

- [ ] **Step 4（window_range 时间序）**：`setup_manifest.py` 里 window_range 的 min/max 改为：

```python
def _window_range(values):
    """min/max 按时间序而非字典序（非 ISO 时间戳字典序会错）。"""
    import datetime as _dt

    def _key(v):
        s = str(v)
        try:
            return (0, _dt.datetime.fromisoformat(s.replace("/", "-").replace(" ", "T")))
        except ValueError:
            return (1, s)  # 解析不了退回字典序，同类比较
    vs = [v for v in values if str(v).strip()]
    if not vs:
        return None
    return [str(min(vs, key=_key)), str(max(vs, key=_key))]
```

（接入点：现有构造 window_range 的表达式换成 `_window_range(...)`；测试：`test_product_manifest.py` 加一条——`["2026/1/2 00:00", "2026/1/10 00:00"]` 这类非补零格式下 max 必须是 1/10 而非字典序的 1/2。）

- [ ] **Step 5（chart_sweep→setup 依赖边）**：`product_manifest.py` 的 argparse 加：

```python
    ap.add_argument("--input", action="append", default=[],
                    metavar="KEY=PATH", help="额外输入指纹（如上游产物 manifest）")
```

主循环后追加：

```python
    for spec in a.input:
        key, _, path = spec.partition("=")
        if not path:
            sys.exit(f"--input 需要 KEY=PATH 形式：{spec}")
        if os.path.exists(path):
            inputs[key] = {"path": path, "fingerprint": ec.file_fingerprint(path)}
        else:
            print(f"⚠ --input {key} 路径不存在，未入指纹：{path}")
```

fact-scan playbook.md 的 manifest 命令行改为：

```
python3 <ENGINE>/scripts/product_manifest.py --product chart_sweep \
  --out chart_sweep_manifest.json \
  --input setup_manifest=<setup 产物 workdir>/setup_manifest.json
```

并补一句：「setup 重建后 chart_sweep 因该指纹自动判 stale——图不落后于数据。」
测试：`test_product_manifest.py` 加一条断言 `--input k=path` 的指纹进 inputs 且键为 `k`。

- [ ] **Step 6（spec 勘误）**：设计文档 §5 「阶段 5 → 3」改「阶段 5 → 4（0 总差距 → 1 分解 → 2 机制变体 → 3 结论）」；§6 `manifest_hashes` 改为实际实现 `{workdir, status, accept_stale}`（指纹在产物 manifest.inputs，product_status 对账），并注明「as-built 勘误 2026-07-25」。

- [ ] **Step 7: 全量测试** → 全绿。

- [ ] **Step 8: Commit**

```bash
git add -A ts-diagnose/ docs/superpowers/specs/
git commit -m "fix(ts-diagnose): Phase1 终审移交加固五件——尾采样钉/optional-stale 钉/modelmap declined 钉/window_range 时间序/chart_sweep→setup 依赖边"
```

---

### Task 9: 文档收尾与裁决落笔

**Files:**
- Modify: `ts-diagnose/references/question-discipline.md`（新节）
- Modify: `ts-diagnose/references/crystallize.md`（一行）
- Modify: `ts-diagnose/scripts/engine_common.py`（modelmap_blocker docstring 一行）
- Modify: `README.md`（分层表与 Phase 2 说明）
- Modify: `docs/superpowers/plans/2026-07-25-playbook-layering-phase2-TODO.md`（收口）

- [ ] **Step 1**: `question-discipline.md` 末尾加节：

```
## 上游产物拥有的问题

生产者 playbook 拥有其领域的形状问题（data-setup：freq、align-keys），消费者
**不得重复声明同 id 问题**——validate_upstream 在 load_frontmatter 时机器拒绝，
不是约定是闸。消费者要用答案时读上游产物的 manifest（orient 已注入摘要），
不再问用户第二遍。目标特有口径问题（metric-caliber、model-set 等）留在消费者。
```

- [ ] **Step 2**: `crystallize.md` 的 profile 相关节补一行：「products 登记不入 profile——产物是每次运行的现场事实（同 degraded_ok），固化它会把上次会话的产物路径当成这次的。」

- [ ] **Step 3**: `engine_common.py` 的 `modelmap_blocker` docstring 补：「2026-07-25 裁决：保留本闸不降级为 upstream 声明——variants 无法表达 material 触发的 optional→required 升级（phase2-TODO 第 4 条）。」

- [ ] **Step 4**: `README.md`：分析层表格加一列说明 result-eval 兼产 `eval_report`；删除第 31 行「（分层机制 Phase 1 已落地…phase2-TODO.md）」括号段，改为「（分层机制已全量落地：3 生产者 + 7 分析 playbook 全部声明上游；contexts 机制已退役。）」。

- [ ] **Step 5**: `phase2-TODO.md` 内容整体替换为完成记录（保留文件作沿革）：首行「# 已全部落地（2026-07-25，分支 playbook-layering-phase2）」+ 原 6 条逐条一行标注落在哪个 task（0→Task1-6、1→Task1-6、2→零平移见计划裁决、3→Task7、4→保留裁决见 engine_common docstring、5→crystallize.md、6→Task9）。

- [ ] **Step 6: 全量测试 + 行数预算**

Run: `python3 -m pytest ts-diagnose/scripts/tests -q` → 全绿；`wc -l ts-diagnose/SKILL.md` ≤60。

- [ ] **Step 7: Commit**

```bash
git add -A
git commit -m "docs(ts-diagnose): Phase 2 收尾——提问归属节/裁决落笔/README 全量落地口径/TODO 收口"
```

---

## 完成判据

全部 9 task 提交、全量 pytest 绿、`grep -rn "contexts" ts-diagnose/playbooks/*/playbook.md` 零命中、REAL_UPSTREAM 表覆盖全部 7 个分析 playbook。之后走 finishing-a-development-branch（合并方式用户定）。
