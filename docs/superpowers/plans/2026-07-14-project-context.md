# project-context 共享站点注册表 + 技能泛化 实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 把站点/实验设定从两个技能中抽成仓库顶层 `project-context/`（站点注册表 + 实验线配置），两个 SKILL.md 彻底抽象化，运行时经 AskUserQuestion 问一次落盘复用。

**Architecture:** 仓库顶层新建 `project-context/`（stations.md 物理站档案 / station-entries.md 数据条目 / experiments/*.json 实验线配置）；两技能各放 `references/project-context.pointer`（沿用 model-ref.pointer 先例）；SKILL.md 新增 Step 0.5 载入流程；正文站名全部抽象为「留出测试站/训练站集合/N 站」。

**Tech Stack:** Markdown + JSON + 纯文本 pointer；唯一代码改动是 `pv-station-influence/scripts/` 的站名参数化（Python，pytest）。

**Spec:** `docs/superpowers/specs/2026-07-14-project-context-design.md`（已批准）。

## Global Constraints

- **⚠️ 绝不 `git add -A` / `git add .`**——只按显式文件路径 stage；每个任务一次原子提交。
- **所有路径相对仓库根**：执行时先 `REPO=$(git rev-parse --show-toplevel)`；**不要把主仓库绝对路径硬编码进 brief/文件内容**（worktree 陷阱）——唯一例外是 pointer 文件，它的职责就是存绝对路径，但必须在执行时用 `$REPO` 现算，不得照抄本计划中的示例路径。
- **反编造纪律**：站点事实查不到就标【待补】，网络检索到的标【检索】待核实，用户确认过的标 ✅+日期；绝不编造。
- **迁移文件一律 `git mv`** 保历史。
- **零残留验收范围**（Task 8 统一验收）：`pv-result-analysis/SKILL.md`、`pv-station-influence/SKILL.md`、`pv-station-influence/references/*.md`、`pv-station-influence/scripts/README.md`、`pv-result-analysis/references/` 下除 `hypotheses.md` 外全部 md、`pv-result-analysis/scripts/README.md`——具体站名（白马湖/雅砻江/泗洪/小壕兔/润达/和熙及新站名）与"17 站/5 站/5 个电站"不得出现。**豁免**：`hypotheses.md`（运行产物登记表，只加表头注）；`project-context/`、`CHANGELOG.md`、`docs/`、`结果分析Skill介绍.md` 的历史行、记忆文件允许出现。
- **不动 `pv-model-analysis/`**（站点无关）。SKILL.md 里的 `<SKILL> = /Users/...` 技能自身路径行不属于站点硬编码，保留。
- 中间任务允许短暂的引用不一致（如 Task 1 移走文件后 SKILL.md 引用旧路径，Task 3 修复）——按顺序执行即可，但**每个任务自身的产物必须完整**。

---

### Task 1: 建 project-context/（注册表 + 实验线 + pointer）

**Files:**
- Move (`git mv`): `pv-result-analysis/references/station.md` → `project-context/stations.md`
- Move (`git mv`): `pv-result-analysis/references/seasonality.md` → `project-context/seasonality.md`
- Move (`git mv`): `pv-result-analysis/references/event-log.md` → `project-context/event-log.md`
- Create: `project-context/README.md`
- Create: `project-context/station-entries.md`
- Create: `project-context/experiments/yalongjiang-line.json`
- Create: `project-context/experiments/baimahu-line.json`
- Create: `pv-result-analysis/references/project-context.pointer`
- Create: `pv-station-influence/references/project-context.pointer`
- Modify: `project-context/stations.md`（迁入后重构，见 Step 3）

**Interfaces:**
- Produces: `project-context/` 目录布局与实验线 JSON schema（后续任务的 SKILL.md 文本引用它们）；entry_id 命名（`1002`…`1022`、`runda-b`、`hexi`、`sihong`、`xiaohaotu`、`yalong-jiefang-b`、`*-2025`）。
- Produces: pointer 文件格式 `path:`/`written:` 两行（Claude 直接读文本，无代码依赖）。

- [ ] **Step 1: git mv 三个文件**

```bash
REPO=$(git rev-parse --show-toplevel); cd "$REPO"
mkdir -p project-context/experiments
git mv pv-result-analysis/references/station.md    project-context/stations.md
git mv pv-result-analysis/references/seasonality.md project-context/seasonality.md
git mv pv-result-analysis/references/event-log.md   project-context/event-log.md
```

- [ ] **Step 2: 写 project-context/README.md**（完整内容如下）

```markdown
# project-context —— 当前项目实例的全部事实（技能之外的共享外部信息）

本目录是 pv-result-analysis 与 pv-station-influence 两个技能的**共享站点注册表与实验配置**。
技能本体（SKILL.md/scripts/references）不写死任何站点、数量、划分——它们全在这里。
**换新项目 = 整目录替换（或把各技能 references/project-context.pointer 指向别处）**，技能一行不用改。

## 文件

| 文件 | 内容 |
|------|------|
| `stations.md` | **物理站档案**：每站一节（地理/装机/形式/气候/限电），字段带置信标签 ✅确认 /【检索】待核实 /【待补】 |
| `station-entries.md` | **数据条目表**：entry_id 为主键——同一物理站可因数据时间段不同出现多条目 |
| `seasonality.md` | 各站气候季节性（从 pv-result-analysis 迁入，2026-07-14） |
| `event-log.md` | 站点事件台账（同上迁入） |
| `experiments/*.json` | **实验线配置**：训练条目 + 留出站 + 数据路径 + chunk 方案；技能运行时 AskUserQuestion 的答案落盘处 |

## 实验线 JSON schema

```json
{
  "name": "<实验线名（=文件名）>",
  "description": "<一句话>",
  "held_out_station": "<留出/目标测试站名，必填>",
  "training_entries": ["<entry_id，见 station-entries.md，必填>"],
  "chunking": {"n_chunks": 4, "sizes": [5, 5, 5, 2], "epochs_per_chunk": 20},
  "models": ["M1", "M2", "M3", "M4"],
  "data_paths": {"train": "【待补】", "test_label": "【待补】", "metric_py": "【待补】", "predictions": {}},
  "notes": ["<实验线级别的重要事实（分析主线、气候带覆盖等）>"],
  "source": "<谁在什么时候提供>"
}
```

约定：`held_out_station`/`training_entries` 必填；`data_paths` 允许【待补】占位——技能运行到需要处
追问一次并**补写回本文件**；`chunking` 无分块训练时置 null；`models` 按实验线实际。

## 发现机制

各技能 `references/project-context.pointer`（`path:` 行 = 本目录绝对路径）。pointer 缺失时技能会
先探 `<技能目录>/../project-context`（symlink 安装下内核物理解析可达），再不行 AskUserQuestion 问路径。

## 使用纪律

- 已填写的字段才可被分析结论引用；【待补】视为未知——宁写"缺 XX 背景无法归因"也不编造。
- 【检索】字段来自网络检索，用户未核实，引用时注明。
- 同名站点多条目（如 1012 与 runda-b）是**同站不同数据时段**，归因/漂移按条目区分，站点背景共享档案。
```

- [ ] **Step 3: 重构 stations.md**（迁入的旧 station.md 基础上）：

3a. 标题与头注替换——

旧（第 1-5 行）：
```markdown
# 电站与数据背景（跨站设定：5 训练站 + 雅砻江留出测试）

<!-- 状态：2026-07 设定变更——五站联合训练（全 2025），测试留出站=雅砻江（不在训练里）。
```
新：
```markdown
# 物理站档案（站点注册表——项目全部站点，不含训练/留出划分）

<!-- 训练/留出划分不在本文件：见 experiments/*.json（两条实验线并行：yalongjiang-line、baimahu-line）。
     数据条目（同站可多时段）见 station-entries.md。
```
（头注其余两行"部分字段由网络检索填入……见 seasonality.md"保留。）

3b. **整节删除**「## 本项目的跨站结构（分析主线）」（4 个 bullet 全删——内容已收进 `experiments/yalongjiang-line.json` 的 notes）。

3c. 既有各节标题去掉划分框定（正文字段全部原样保留，含勘误注释）：
- `## 测试站：雅砻江（柯拉，留出，不在训练里）` → `## 雅砻江柯拉一期（四川甘孜，高原水光互补）——子场站：解放、庆达`
- `## 训练站一：泗洪光伏电站（江苏）` → `## 泗洪光伏电站（江苏宿迁）`
- `## 训练站二：白马湖光伏电站（江苏）` → `## 白马湖光伏电站（江苏淮安）`
- `## 训练站三：西北戈壁小壕兔（陕西榆林）` → `## 西北戈壁小壕兔（陕西榆林）`
- `## 训练站四：华能北方润达光伏电站【多数字段待补】` → `## 华能北方润达光伏电站【多数字段待补】`
- `## 训练站五：国能和熙光储能站【多数字段待补】` → `## 国能和熙光储电站【多数字段待补】`
- 泗洪节内"与白马湖同气候带"等**站间比较句保留**（是气候事实，非划分）。
- 雅砻江节内 bullet `**地理位置**` 行保留；节首加一行：`- **子场站**：解放（entry 1005 / yalong-jiefang-b）、庆达（entry 1006）✅用户 2026-07-14——本档案两子场站共用。`

3d. 文末（"## 数据来源"节之前）追加 9 个新站骨架节，每站一节、格式统一（Task 2 检索后填）：

```markdown
## 黄河水电共和红旗二光伏电站【待检索】

- **地理位置**：【待补】
- **装机容量**：【待补】
- **电站形式**：【待补】
- **气候类型**：【待补】
- **限电与运行**：【待补】
```

同格式再写 8 节，站名依次：`黄河水电共和红旗八光电站`、`大朝山西光伏电站`、`国家能源集团茂克`、`幕家湾光伏电站`、`湖北华店襄城卧龙农光互补发电项目`、`阳江中能建光伏电站`、`保定满城白龙`、`国电投东辛农场`。

3e. 「## 数据来源」节标题下头一行加注：`<!-- 以下按实验线区分口径；yalongjiang-line 的疑问迁自旧版，baimahu-line 的待补 -->`（节内旧内容保留）。

- [ ] **Step 4: 写 station-entries.md**（完整内容如下）

```markdown
# 数据条目表（entry_id 为主键；同一物理站可因数据时段不同出现多条目）

<!-- 来源：baimahu-line 17 条目清单由用户提供（2026-07-14）；同名多条目=同站不同时段 ✅用户。
     时间段全部【待补】——用户后续提供或分析时从数据探出再填，不编造。 -->

## baimahu-line 训练条目（17）

| entry_id | 编号 | 物理站 | 数据时段 | 备注 |
|----------|------|--------|----------|------|
| 1002 | 1002 | 黄河水电共和红旗二光伏电站 | 【待补】 | |
| 1003 | 1003 | 大朝山西光伏电站 | 【待补】 | |
| 1004 | 1004 | 黄河水电共和红旗八光电站 | 【待补】 | |
| 1005 | 1005 | 雅砻江柯拉一期（解放） | 【待补】 | |
| 1006 | 1006 | 雅砻江柯拉一期（庆达） | 【待补】 | |
| 1009 | 1009 | 国家能源集团茂克 | 【待补】 | |
| 1010 | 1010 | 幕家湾光伏电站 | 【待补】 | |
| 1012 | 1012 | 华能北方润达光伏电站 | 【待补】 | 与 runda-b 同站不同时段 ✅用户 2026-07-14 |
| 1015 | 1015 | 湖北华店襄城卧龙农光互补发电项目 | 【待补】 | |
| 1016 | 1016 | 阳江中能建光伏电站 | 【待补】 | |
| 1019 | 1019 | 保定满城白龙 | 【待补】 | |
| 1022 | 1022 | 国电投东辛农场 | 【待补】 | |
| runda-b | — | 华能北方润达光伏电站 | 【待补】 | 同 1012 站、不同时段 ✅用户 2026-07-14 |
| hexi | — | 国能和熙光储电站 | 【待补】 | |
| sihong | — | 泗洪光伏电站 | 【待补】 | |
| xiaohaotu | — | 西北戈壁小壕兔 | 【待补】 | |
| yalong-jiefang-b | — | 雅砻江柯拉一期（解放） | 【待补】 | =解放站，时段可能异于 1005 ✅用户 2026-07-14 |

留出测试站：**白马湖**（不在训练条目内）。

## yalongjiang-line 条目（5 训练 + 1 留出测试）

| entry_id | 编号 | 物理站 | 数据时段 | 备注 |
|----------|------|--------|----------|------|
| sihong-2025 | — | 泗洪光伏电站 | 2025 全年 | 与 sihong 条目是否同一份数据【待确认】 |
| baimahu-2025 | — | 白马湖光伏电站 | 2025 全年 | |
| xiaohaotu-2025 | — | 西北戈壁小壕兔 | 2025 全年 | 与 xiaohaotu 条目关系【待确认】 |
| runda-2025 | — | 华能北方润达光伏电站 | 2025 全年 | 与 1012/runda-b 关系【待确认】 |
| hexi-2025 | — | 国能和熙光储电站 | 2025 全年 | 与 hexi 条目关系【待确认】 |
| yalong-2025 | — | 雅砻江柯拉一期 | 2025 | **留出测试数据**（不在训练里） |
```

- [ ] **Step 5: 写两个实验线 JSON**

`project-context/experiments/baimahu-line.json`：
```json
{
  "name": "baimahu-line",
  "description": "17 条目分块联合训练，白马湖留出零样本（站点影响力归因主实验线）",
  "held_out_station": "白马湖",
  "training_entries": ["1002", "1003", "1004", "1005", "1006", "1009", "1010", "1012", "1015", "1016", "1019", "1022", "runda-b", "hexi", "sihong", "xiaohaotu", "yalong-jiefang-b"],
  "chunking": {"n_chunks": 4, "sizes": [5, 5, 5, 2], "epochs_per_chunk": 20},
  "models": ["M1", "M2", "M3", "M4"],
  "data_paths": {"train": "【待补】", "test_label": "【待补】", "metric_py": "【待补】", "predictions": {}},
  "notes": [
    "每迭代把全部 17 训练条目随机重排进 4 个 chunk（3×5+2），每 chunk 20 epoch；M1–M4 各自训后取平均 ensemble",
    "留出站白马湖（江苏平原湖区）不在训练条目内"
  ],
  "source": "用户提供 17 条目清单，AskUserQuestion 澄清同站多时段，2026-07-14"
}
```

`project-context/experiments/yalongjiang-line.json`：
```json
{
  "name": "yalongjiang-line",
  "description": "5 站 2025 全年联合训练，雅砻江（柯拉）留出零样本（结果分析主实验线，2026-07-09 设定）",
  "held_out_station": "雅砻江",
  "training_entries": ["sihong-2025", "baimahu-2025", "xiaohaotu-2025", "runda-2025", "hexi-2025"],
  "chunking": null,
  "models": ["M1", "M2", "M3", "M4", "ensemble"],
  "data_paths": {"train": "【待补】", "test_label": "【待补】", "metric_py": "【待补】", "predictions": {}},
  "notes": [
    "训练站跨两类气候带——江苏平原湿润（泗洪/白马湖）与西北干旱沙戈荒高辐照（小壕兔；润达/和熙疑似同类【待补】）",
    "留出站雅砻江属川西高原季风带（海拔约 4600m、水光互补）——训练未覆盖；第一大分析主线是'雅砻江离训练分布多远、最像哪个训练站'",
    "训练/测试都是 2025，无跨年成分；训练集不参与指标计算，只作跨站漂移诊断基准"
  ],
  "source": "迁自 pv-result-analysis SKILL.md 项目背景节 + station.md 跨站结构节，2026-07-14"
}
```

- [ ] **Step 6: 写两个 pointer 文件**（路径执行时现算，勿照抄示例）

```bash
REPO=$(git rev-parse --show-toplevel)
for skill in pv-result-analysis pv-station-influence; do
  printf 'path: %s/project-context\nwritten: 2026-07-14\n' "$REPO" > "$REPO/$skill/references/project-context.pointer"
done
cat "$REPO/pv-result-analysis/references/project-context.pointer"
```
Expected: 两行 `path: <REPO>/project-context` 与 `written: 2026-07-14`。

- [ ] **Step 7: 验证 JSON 可解析、条目一致**

```bash
cd "$(git rev-parse --show-toplevel)"
python3 - <<'EOF'
import json
for name in ("baimahu-line", "yalongjiang-line"):
    cfg = json.load(open(f"project-context/experiments/{name}.json"))
    assert cfg["held_out_station"] and cfg["training_entries"], name
    print(name, "OK:", len(cfg["training_entries"]), "entries, held_out =", cfg["held_out_station"])
EOF
grep -c "^| " project-context/station-entries.md
```
Expected: `baimahu-line OK: 17 entries, held_out = 白马湖`；`yalongjiang-line OK: 5 entries, held_out = 雅砻江`；表行数 = 25（2 表头×2 + 17 + 6，按实际核对 17 条目行都在）。

- [ ] **Step 8: Commit**

```bash
cd "$(git rev-parse --show-toplevel)"
git add project-context/ pv-result-analysis/references/project-context.pointer pv-station-influence/references/project-context.pointer
git commit -m "feat: project-context 共享站点注册表（物理站×数据条目两层 + 两条实验线 + pointer）"
```
（`git add project-context/` 覆盖 3 个 git mv 的新路径与新建文件；`git status` 确认旧路径的 deleted 已随 mv staged。）

---

### Task 2: 联网检索预填 9 个新站（标【检索】）

**Files:**
- Modify: `project-context/stations.md`（Task 1 建的 9 个骨架节）

**Interfaces:**
- Consumes: Task 1 的 9 个【待检索】骨架节。
- Produces: 各站地理/装机/形式/气候字段，值后带【检索】标；查不到保持【待补】。

- [ ] **Step 1: 逐站 WebSearch**（每站 1-2 次检索，中文查询）

查询词模板（逐个跑）：`"黄河水电 共和 红旗二 光伏电站"`、`"黄河水电 共和 红旗八 光伏"`、`"大朝山西 光伏电站"`（注意甄别：可能是云南大朝山水电站配套光伏，需证据）、`"国家能源集团 茂克 光伏"`、`"幕家湾 光伏电站"`、`"襄城 卧龙 农光互补 湖北"`、`"阳江 中能建 光伏电站"`、`"保定 满城 白龙 光伏"`、`"国电投 东辛农场 光伏"`。

- [ ] **Step 2: 回填字段**

规则：每个查到的字段值后加【检索】；**多个候选项目无法唯一锁定时**写 `<!-- 待补：检索到多个候选（列出），未能唯一锁定 -->`（沿用旧 station.md 润达/和熙节的既有写法）；**气候类型可由确定的地理位置推断**（如青海共和=高原干旱高辐照带），推断值标【检索+推断】；节标题的【待检索】改为省份（如 `## 黄河水电共和红旗二光伏电站（青海海南州）【检索】`）。

- [ ] **Step 3: 自查无编造**

```bash
cd "$(git rev-parse --show-toplevel)"
grep -n "【待检索】" project-context/stations.md   # Expected: 0 行（都已处理成【检索】或【待补】）
```

- [ ] **Step 4: Commit**

```bash
git add project-context/stations.md
git commit -m "docs(project-context): 联网检索预填 9 个新站（全部标【检索】待核实）"
```

---

### Task 3: pv-result-analysis/SKILL.md 抽象化 + Step 0.5

**Files:**
- Modify: `pv-result-analysis/SKILL.md`

**Interfaces:**
- Consumes: Task 1 的 pointer 文件与实验线 JSON schema。
- Produces: 「Step 0.5」节与 `analysis_config.json` 新字段 `experiment`（Task 5/6 的 pv-station-influence 文本与之同构；Task 4 references 的措辞与之对齐：「留出测试站」「训练站集合」）。

- [ ] **Step 1: 改「项目背景与数据结构」节**——第 15-17 行三个 bullet（跨站设定/测试输出/训练测试都是2025）整体替换为：

```markdown
- **实验设定不写死在本技能（核心）**：训练/留出划分、站点全集、数据路径全部来自共享 **project-context**（经 `references/project-context.pointer` 定位；载入流程见 Step 0.5）。下文「**留出测试站**」= 实验线 `held_out_station`，「**训练站集合**」= 实验线 `training_entries` 对应站点。典型设定是**跨站零样本迁移**：若干训练站（条目）联合训练，留出站完全不在训练里——此时第一大分析主线是"留出站离训练分布多远、最像哪个训练站"（站点气候背景见 project-context 的 `stations.md`/`seasonality.md`）。
- **测试输出是单站（留出站）**：指标 Excel、图、结论都只针对留出站，不存在"多测试站混算"。但**训练侧要分站看**——判断留出站像谁时，训练站要逐站比较（跨站漂移诊断），不能 pooled 成一个平均气候。
- **训练集是可选输入**：不参与指标计算，用途是**跨站漂移诊断的基准**（训练站 pooled + 逐站 vs 留出站，见 `references/drift-and-nwp.md`）——回答"模型是不是没见过这个站的这种天"。数据结构：训练与测试同构（同样的滚动窗口时序表）。没放训练集就跳过漂移诊断（`run_drift.py` / 图#11/#12），metric 与其余图谱照常。是否跨年等设定细节以实验线 `notes` 为准。
```

- [ ] **Step 2: 第 29 行**（true_label schema 警示 bullet 末句）：`test 侧（雅砻江）若要用` → `test 侧（留出站）若要用`。

- [ ] **Step 3: 在「Step 0：Orient」节之后插入新节**（完整文本）：

```markdown
## Step 0.5：载入项目上下文与实验线（首次问一次，之后自动复用）

本技能不写死任何站点/划分——它们来自共享 **project-context**（站点注册表 + 实验线配置）：

1. **定位 project-context**：读 `references/project-context.pointer` 的 `path:` 行；pointer 缺失/失效 → 探 `<技能目录>/../project-context`；仍无 → AskUserQuestion 问路径（或经用户同意按 project-context/README.md 的 schema 新建骨架），拿到后写回 pointer。
2. **选实验线**：工作目录 `analysis_config.json` 已有 `experiment` 字段 → 直接载入 `<project-context>/experiments/<experiment>.json`，**不再问**。没有 → 列出 `experiments/*.json`，AskUserQuestion 让用户选已有实验线或新建。
3. **新建实验线**：AskUserQuestion 收集——留出（目标）站、训练条目（对照 `station-entries.md` 列候选）、数据路径 → 按 README.md schema 写 `experiments/<name>.json`，后续会话复用。
4. **字段缺口**：载入后发现 `data_paths` 有【待补】且本次要用 → 追问一次，答案**补写回实验线 json**（不是只写本地 config）。

载入后：「留出测试站」=`held_out_station`；「训练站集合」=`training_entries` 对应站点（查 `station-entries.md`）；站点背景查 `<project-context>/stations.md`（只引用已填字段）。
```

- [ ] **Step 4: 改 Step 1 节**：
- 第 92 行 bullet `测试站固定是**雅砻江**。train_set（5 站联合训练集）**可选**` → `测试站 = 实验线 held_out_station（Step 0.5 已载入）。train_set（训练站联合训练集）**可选**`。
- config 模板（第 96-106 行）替换为：

```json
{
  "experiment": "<实验线名（experiments/ 下文件名，Step 0.5 选定）>",
  "station": "<留出测试站（= 实验线 held_out_station）>",
  "metric_py": "<metric.py 绝对路径>",
  "train_set": "<训练站联合训练集 parquet（pooled）；可选——不做跨站漂移可省略>",
  "true_label": "<留出站 test/true_label parquet 绝对路径>",
  "predicted": {"M1": "<路径>", "M2": "<路径>", "M3": "<路径>", "M4": "<路径>", "ensemble": "<路径>"},
  "pred_col": "<可选：预测列名；缺省则 run_analysis.py 自动侦测 192 宽的列>",
  "train_stations": {"<训练站名>": "<路径>", "…": "…"}
}
```
- 模板下一行 `没有则只做 pooled。` 之后原文保留；`train_stations` 说明句里 `找雅砻江最像哪个训练站` → `找留出站最像哪个训练站`。

- [ ] **Step 5: 其余散点替换**（Edit，逐处）：

| 位置 | 旧 | 新 |
|------|----|----|
| Step 2 末（~147 行） | `（测试站只有雅砻江，产物存 figures/yalongjiang/）` | `（测试站只有留出站，产物存 figures/<留出站拼音>/）` |
| 输出规范（~194 行） | `图输出目录 figures/yalongjiang/<范围>/（测试站固定雅砻江）` | `图输出目录 figures/<留出站拼音>/<范围>/（留出站来自实验线配置）` |
| 阶段纪律（~82 行） | `模型参考（.modelmap/models.md）/station.md/seasonality.md 已填字段` | `模型参考（.modelmap/models.md）/project-context 的 stations.md/seasonality.md 已填字段` |
| 可疑日二分（~125 行） | `进 references/event-log.md` | `进 <project-context>/event-log.md` |
| 常见错误第 1 条 | `跨站漂移把 5 训练站 pooled 成一个"平均气候"（掩盖"很像小壕兔、很不像泗洪"）` | `跨站漂移把训练站集合 pooled 成一个"平均气候"（掩盖"很像 A 站、很不像 B 站"）` |
| 常见错误第 2 条 | `把雅砻江变差直接归因为模型能力` | `把留出站变差直接归因为模型能力` |
| 运行后回顾 | `确认的新项目事实 → 补 references/` | `确认的新项目事实 → 补 project-context/（站点/季节/事件）；方法类知识 → 补 references/` |

- [ ] **Step 6: 改「背景知识库（references/）」表**——三行改路径并加一行：
- `event-log.md` 行首列 → `<project-context>/event-log.md`（"什么时候读"列不变）
- `station.md` 行首列 → `<project-context>/stations.md（+station-entries.md 条目表）`
- `seasonality.md` 行首列 → `<project-context>/seasonality.md`
- 表后使用纪律段追加一句：`project-context 经 references/project-context.pointer 定位（见 Step 0.5）；站点/季节/事件是项目实例数据，方法类文档才在 references/。`

- [ ] **Step 7: 验证 + Commit**

```bash
cd "$(git rev-parse --show-toplevel)"
grep -n "白马湖\|雅砻江\|泗洪\|小壕兔\|润达\|和熙\|17 站\|5 个电站\|5 站\|yalongjiang" pv-result-analysis/SKILL.md
```
Expected: 0 行。

```bash
git add pv-result-analysis/SKILL.md
git commit -m "refactor(pv-result-analysis): SKILL.md 彻底抽象化——实验设定经 project-context 载入（Step 0.5 + AskUserQuestion 问一次落盘）"
```

---

### Task 4: pv-result-analysis references/ 与 scripts/ 清扫

**Files:**
- Modify: `pv-result-analysis/references/figure-diagnostics.md`
- Modify: `pv-result-analysis/references/subagent-briefs.md`
- Modify: `pv-result-analysis/references/analysis-discipline.md`
- Modify: `pv-result-analysis/references/playbooks.md`
- Modify: `pv-result-analysis/references/drift-and-nwp.md`
- Modify: `pv-result-analysis/references/hypotheses.md`（只加表头注）
- Modify: `pv-result-analysis/scripts/README.md`（如有站名）
- Modify: `pv-result-analysis/scripts/{data_utils.py,plots.py,run_drift.py,run_quality_check.py}`（注释/print/docstring）

**Interfaces:**
- Consumes: Task 3 的措辞约定（「留出测试站」「训练站集合」）。
- Produces: 无新接口（纯文案）；脚本行为不变（只动注释与 print 字符串，不动逻辑）。

- [ ] **Step 1: figure-diagnostics.md**（7 处，Edit 逐处）：

| 行 | 旧 | 新 |
|----|----|----|
| 373 | `查 seasonality.md 该站该月机制（雅砻江 6–9 月雨季对流、白马湖 6 月梅雨等）` | `查 <project-context>/seasonality.md 该站该月机制（各站季节性条目）` |
| 479 | `（跨站设定下 train=5 训练站 pooled、test=雅砻江）` | `（跨站设定下 train=训练站集合 pooled、test=留出站）` |
| 487 | `雅砻江见到"训练站没覆盖的` | `留出站见到"训练站没覆盖的` |
| 494 | `跨站气候带差异（雅砻江高原 vs 训练站平原/干旱）` | `跨站气候带差异（留出站 vs 训练站气候带，见 project-context/stations.md）` |
| 495 | `run_drift 逐站找雅砻江最像哪个训练站` | `run_drift 逐站找留出站最像哪个训练站` |
| 504 | `判"雅砻江整体更亮/更多波动天"` | `判"留出站整体更亮/更多波动天"` |
| 510 | `train vs test（训练站 vs 雅砻江）` | `train vs test（训练站 vs 留出站）` |

另全文搜 `seasonality.md`/`station.md`/`event-log.md` 的裸引用 → 前缀 `<project-context>/`。

- [ ] **Step 2: subagent-briefs.md 第 71 行**：`产物存 figures/yalongjiang/（测试站固定雅砻江）` → `产物存 figures/<留出站拼音>/（留出站名从 analysis_config.json 的 station 字段取）`。全文搜 `station.md`→`<project-context>/stations.md`（如有）。

- [ ] **Step 3: analysis-discipline.md 第 39 行**：`雅砻江该月是否偏出 5 训练站分布` → `留出站该月是否偏出训练站分布`。**playbooks.md 第 18 行**：`雅砻江 X 月的天气/功率/映射分布 vs 5 训练站` → `留出站 X 月的天气/功率/映射分布 vs 训练站集合`。两文件再全文 grep 站名清残留、`event-log.md`/`station.md`/`seasonality.md` 裸引用加 `<project-context>/` 前缀。

- [ ] **Step 4: drift-and-nwp.md 全文抽象化**（~15 处）：`雅砻江`→`留出站`；`5 训练站`/`5 站`→`训练站集合`/`训练站`；47-48 行示例结论句改为占位版：`"留出站 6 月的 σΔ 分布显著偏出训练站（pooled PSI 0.34；逐站看最接近 A 站 PSI 0.12、最远离 B 站 PSI 0.51）——该月天气模式是训练站集合未覆盖的，跨站 OOD 是变差主因。"`；19 行 `查 station.md（和熙储能、雅砻江容量）` → `查 <project-context>/stations.md（储能站充放电改形、留出站容量）`；标题（第 5 行）`（跨站：5 训练站 vs 留出测试站雅砻江）` → `（跨站：训练站集合 vs 留出测试站）`。

- [ ] **Step 5: hypotheses.md 表头注**——在文件头注释块（`<!-- 本表把 models.md…` 之后）加一行：`本表的假设行属当前项目实例（含具体站名/实验线），换项目时归档重开；表结构与状态流转纪律是技能逻辑，保持不变。`（F 节等既有站名行**不改**。）

- [ ] **Step 6: scripts 注释/print 抽象化**（不动逻辑，只动字符串）：
- `data_utils.py` 272/303 行 docstring：`train=5 训练站、test=雅砻江`→`train=训练站集合、test=留出站`（两处同理）。
- `plots.py` 332/374 行 docstring 同理。
- `run_drift.py`：4-16 行头注、38/51/55/57/66 行注释与 print 里 `雅砻江`→`留出站`、`5 站`→`训练站`；`"训练站(pooled) vs 雅砻江"`→`"训练站(pooled) vs 留出站"`。
- `run_quality_check.py`、`scripts/README.md`：grep 站名逐处同样替换。

- [ ] **Step 7: 脚本冒烟**（确认只动了字符串）：

```bash
cd "$(git rev-parse --show-toplevel)/pv-result-analysis/scripts"
python3 -c "import data_utils, plots" && python3 run_drift.py --help >/dev/null && echo SMOKE-OK
```
Expected: `SMOKE-OK`（run_drift 无 --help 则 `python3 -m py_compile run_drift.py run_quality_check.py` 代替）。

- [ ] **Step 8: 验证 + Commit**

```bash
cd "$(git rev-parse --show-toplevel)"
grep -rn "白马湖\|雅砻江\|泗洪\|小壕兔\|润达\|和熙" pv-result-analysis/references/ pv-result-analysis/scripts/ | grep -v hypotheses.md
```
Expected: 0 行。

```bash
git add pv-result-analysis/references/figure-diagnostics.md pv-result-analysis/references/subagent-briefs.md pv-result-analysis/references/analysis-discipline.md pv-result-analysis/references/playbooks.md pv-result-analysis/references/drift-and-nwp.md pv-result-analysis/references/hypotheses.md pv-result-analysis/scripts/data_utils.py pv-result-analysis/scripts/plots.py pv-result-analysis/scripts/run_drift.py pv-result-analysis/scripts/run_quality_check.py pv-result-analysis/scripts/README.md
git commit -m "refactor(pv-result-analysis): references 与 scripts 文案去站名硬编码（hypotheses 登记表豁免+表头注）"
```

---

### Task 5: pv-station-influence/SKILL.md 抽象化 + Step 0.5

**Files:**
- Modify: `pv-station-influence/SKILL.md`

**Interfaces:**
- Consumes: Task 1 pointer/schema；Task 3 的 Step 0.5 文本模式（本技能同构复制并适配 config 名）。
- Produces: `influence_config.json` 新字段 `experiment`、`test_station_aliases`（Task 7 的 si_common/probe_logs 与之对应）。

- [ ] **Step 1: 重写 frontmatter description**（第 3 行整行替换）：

```
description: 光伏多站分块训练的「站点影响力归因」——找出联合训练的 N 个训练站/数据条目里哪些拖累了留出测试站的零样本预测（负迁移），并解释训练动力学（为什么不同 iteration/chunk 的 training loss 不同）。当用户说"哪个站拖累留出站/哪些训练站有负迁移/为什么每个 chunk 的 RMSE 上下震荡/为什么有的 chunk loss 更高、收敛更慢/某些站是不是在帮倒忙/从 N 站里挑出该剔除的站/训练集构成对某站的影响/先做留出站结果分析再归因"时使用。区别于 pv-result-analysis（单次预测结果评估）与 pv-model-analysis（从模型代码生成模型参考档案）：本技能做的是**训练集构成 → 目标站性能**的归因；实验设定（站点全集/留出站/chunk 方案）经共享 project-context 载入（Step 0.5，AskUserQuestion 问一次落盘）；它会检测/复用留出站线 pv-result-analysis 的产物作预测侧上下文，没跑过会先问用户要不要嵌入跑。两种证据模式：只有预测/日志走观测归因（Mode A，零 GPU），有 checkpoint 可进一步做梯度与重训确认（Mode B），模式由 config 自动识别。
```

- [ ] **Step 2: 重写「问题」段**（第 8 行）：

```markdown
**问题**（N、chunk 数/大小、每 chunk epoch、模型数等实验参数经 project-context 实验线配置载入——见 Step 0.5；下文以「N 站分 K 个 chunk」指代）：N 个电站/数据条目分块联合训练（每迭代把全部条目随机重排进 K 个 chunk，每 chunk 训固定 epoch，各模型独立训后取平均 ensemble），留出测试站**不在训练条目内**。每 chunk 后留出站零样本 RMSE **上下震荡不单调**，怀疑某些站负迁移。目标：**找出拖累留出站的站，给证据，顺带解释训练 loss 为什么因 chunk 而异，再决定怎么处理。**
```

- [ ] **Step 3: 在「Step 0：Orient」节前插入 Step 0.5 节**（与 pv-result-analysis 同构，config 换名）：

```markdown
## Step 0.5：载入项目上下文与实验线（首次问一次，之后自动复用）

1. **定位 project-context**：读 `references/project-context.pointer` 的 `path:` 行；缺失 → 探 `<技能目录>/../project-context`；仍无 → AskUserQuestion 问路径，写回 pointer。
2. **选实验线**：`influence_config.json` 已有 `experiment` 字段 → 直接载入 `experiments/<experiment>.json`，不再问。没有 → 列出 experiments/*.json，AskUserQuestion 选已有或新建（新建流程同 pv-result-analysis Step 0.5，收集留出站/训练条目/chunk 方案/数据路径）。
3. 载入后：「留出（测试）站」=`held_out_station`；`stations` 字段 = `training_entries`（顺序即回归设计矩阵列序）；chunk 方案 = `chunking`；`data_paths` 缺【待补】且本次要用 → 追问一次并补写回实验线 json。
```

- [ ] **Step 4: 全文机械替换**（Edit 逐处；语义不变）：

| 旧 | 新 | 处数（约） |
|----|----|------|
| `白马湖` | `留出站`（句式需要时`留出测试站`） | 30+（含表格、纪律、常见错误、上下文预算节） |
| `17 站`/`17 个电站`/`原 17 站`/`15–16 站` | `N 站`/`N 个电站/条目`/`原 N 站`/`N−2~N−3 站` | 8+ |
| `4 个 chunk = 3×5+2，每 chunk 20 epoch` | `K 个 chunk（大小与 epoch 见实验线 chunking）` | 1（问题段已重写则跳过） |
| `连训某 5 站 20 epoch` | `连训某一 chunk 的站若干 epoch` | 1 |
| `figures/baimahu/drift/` | `figures/<留出站拼音>/drift/` | 1 |
| `result_analysis_baimahu/` | `result_analysis_<留出站拼音>/` | 2 |
| `station=白马湖` | `station=实验线 held_out_station` | 1 |
| `（如指到雅砻江线）` | `（如指到另一条实验线）` | 1 |
| `这是**并行的另一条实验线**（白马湖/17 站），两者独立` | `其他实验线的工作目录/配置**绝不混用**——各实验线独立` | 1 |
| `雅砻江线目录/复用雅砻江 analysis_config.json` | `其他实验线目录/复用其他实验线的 analysis_config.json` | 1 |

- [ ] **Step 5: Step 1 收集节改写**：`test_label` 行 → `test_label：留出站 true_label parquet（算 RMSE 的真值；默认取实验线 data_paths.test_label）`；`stations` 行 → `stations：训练条目 id 列表（= 实验线 training_entries，Step 0.5 已载入；顺序即回归设计矩阵列序）`；加一行 `experiment：实验线名（Step 0.5 写入）` 与 `test_station_aliases：留出站在日志里的可能写法（中文/拼音/站 id，probe_logs 用它扫日志）`。

- [ ] **Step 6: 运行后回顾节**：`确认的项目事实 → 记忆 + pv-result-analysis/references/station.md（白马湖背景）` → `确认的项目事实 → 记忆 + <project-context>/stations.md（站点档案）`。

- [ ] **Step 7: 验证 + Commit**

```bash
cd "$(git rev-parse --show-toplevel)"
grep -n "白马湖\|雅砻江\|泗洪\|小壕兔\|17 站\|17站\|baimahu" pv-station-influence/SKILL.md
```
Expected: 0 行。

```bash
git add pv-station-influence/SKILL.md
git commit -m "refactor(pv-station-influence): SKILL.md 彻底抽象化——N 站/留出站经 project-context 实验线载入"
```

---

### Task 6: pv-station-influence references/ 与 scripts/README.md 清扫

**Files:**
- Modify: `pv-station-influence/references/attribution-discipline.md`
- Modify: `pv-station-influence/references/influence-methods.md`
- Modify: `pv-station-influence/references/subagent-briefs.md`
- Modify: `pv-station-influence/scripts/README.md`

**Interfaces:**
- Consumes: Task 5 的措辞（留出站/N 站/`result_analysis_<留出站拼音>`）。

- [ ] **Step 1: attribution-discipline.md**（11/18/21/27/29/39/42/56/57/62 行）：`白马湖`→`留出站`；57 行 `剔除 top 2–3 嫌疑（15–16 站）重训一次，与原 17 站同种子同协议` → `剔除 top 2–3 嫌疑重训一次，与原全量训练同种子同协议`；62 行示例管理层结论句里 `（西北干旱高辐照，与白马湖平原湿润气候差异最大）` → `（与留出站气候差异最大）`、`拉低白马湖预测，剔除后白马湖 RMSE` → `拉低留出站预测，剔除后留出站 RMSE`；39 行 `走 pv-result-analysis 的 run_quality_check.py + event-log.md` → `… + <project-context>/event-log.md`。

- [ ] **Step 2: influence-methods.md**（7/33/36/39/47/55/68/73/88/93 行）：`17 站`→`N 站`（7、88 行两处 `全部 17 站`→`全部 N 站`、`把 17 站无重叠地分进 4 个 chunk（大小 5/5/5/2）`→`把 N 站无重叠地分进 K 个 chunk（大小见实验线 chunking）`）；`白马湖`→`留出站`（其余各处）；`RMSE_白马湖`→`RMSE_留出站`（47 行公式）。

- [ ] **Step 3: subagent-briefs.md**（24/29/33/34/37/56/132/152/155/161 行）：`白马湖`→`留出站`；29 行 `result_analysis_baimahu/（独立目录——绝不写雅砻江线的` → `result_analysis_<留出站拼音>/（独立目录——绝不写其他实验线的`；37/152/155 行 `17 站`→`N 站`/`全部训练站`；161 行 `最像白马湖`→`最像留出站`。全文 `station.md`→`<project-context>/stations.md`（132 行）。

- [ ] **Step 4: scripts/README.md**（11/20/39 行）：`白马湖 RMSE`→`留出站 RMSE`、`白马湖逐 chunk RMSE`→`留出站逐 chunk RMSE`。

- [ ] **Step 5: 验证 + Commit**

```bash
cd "$(git rev-parse --show-toplevel)"
grep -rn "白马湖\|雅砻江\|17 站\|17站\|baimahu" pv-station-influence/references/ pv-station-influence/scripts/README.md
```
Expected: 0 行。

```bash
git add pv-station-influence/references/attribution-discipline.md pv-station-influence/references/influence-methods.md pv-station-influence/references/subagent-briefs.md pv-station-influence/scripts/README.md
git commit -m "refactor(pv-station-influence): references 与 scripts/README 去站名硬编码"
```

---

### Task 7: pv-station-influence scripts 站名参数化（TDD）

**Files:**
- Modify: `pv-station-influence/scripts/probe_logs.py`（STATION_PAT 从 config 构建）
- Modify: `pv-station-influence/scripts/si_common.py`（CONFIG 模板注释 + 新字段说明）
- Modify: `pv-station-influence/scripts/run_orient.py`（print 字串 genericize）
- Modify: `pv-station-influence/scripts/ckpt_eval.py`、`loss_dynamics.py`、`adapter_template.py`（注释/print 字串）
- Test: `pv-station-influence/scripts/test_probe_station_pat.py`（新建）

**Interfaces:**
- Consumes: config 字段 `test_station`、`test_station_aliases`（Task 5 已写进 SKILL.md Step 1）。
- Produces: `probe_logs.station_pattern(cfg) -> re.Pattern`——test_station + aliases 逃逸后 OR 连接、IGNORECASE；cfg 两字段都空时回退 DEFAULT_STATION_PAT（保持向后兼容旧 config）。

- [ ] **Step 1: 写失败测试** `pv-station-influence/scripts/test_probe_station_pat.py`：

```python
import probe_logs

def test_pattern_from_config_aliases():
    cfg = {"test_station": "baimahu", "test_station_aliases": ["白马湖", "bmh"]}
    pat = probe_logs.station_pattern(cfg)
    assert pat.search("epoch 3 白马湖 rmse=0.123")
    assert pat.search("BAIMAHU eval rmse")
    assert pat.search("[bmh] chunk2 rmse 0.2")
    assert not pat.search("yalong eval rmse")

def test_pattern_fallback_when_config_empty():
    pat = probe_logs.station_pattern({})
    assert pat is probe_logs.DEFAULT_STATION_PAT

def test_alias_regex_escaped():
    pat = probe_logs.station_pattern({"test_station": "st.1", "test_station_aliases": []})
    assert pat.search("st.1 rmse") and not pat.search("stX1 rmse")
```

- [ ] **Step 2: 跑测试确认失败**

```bash
cd "$(git rev-parse --show-toplevel)/pv-station-influence/scripts" && python3 -m pytest test_probe_station_pat.py -q
```
Expected: FAIL（`AttributeError: module 'probe_logs' has no attribute 'station_pattern'`）。

- [ ] **Step 3: 实现**——probe_logs.py：

第 35-36 行替换为：
```python
# 留出站在日志里的可能写法：config 的 test_station + test_station_aliases（中文/拼音/站 id）。
# 两者都空时回退默认（历史项目兼容）。
DEFAULT_STATION_PAT = re.compile(r"(白马湖|baima|baimahu|bmh)", re.IGNORECASE)


def station_pattern(cfg):
    names = [cfg.get("test_station", "")] + list(cfg.get("test_station_aliases", []))
    parts = [re.escape(n) for n in names if n]
    if not parts:
        return DEFAULT_STATION_PAT
    return re.compile("(" + "|".join(parts) + ")", re.IGNORECASE)
```

`_scan_file` 改签名接收 pattern：`def _scan_file(path, station_pat, max_hits=5):`，第 54 行 `STATION_PAT.search(line)` → `station_pat.search(line)`；`main()` 里读到 cfg 后（load_config 的 try 块内）算 `station_pat = station_pattern(cfg)`、无 config 时 `station_pat = DEFAULT_STATION_PAT`，传给所有 `_scan_file` 调用点（grep `_scan_file(` 逐个补参）。

- [ ] **Step 4: 跑测试通过 + 冒烟**

```bash
cd "$(git rev-parse --show-toplevel)/pv-station-influence/scripts"
python3 -m pytest test_probe_station_pat.py -q          # Expected: 3 passed
python3 -m py_compile probe_logs.py run_orient.py si_common.py ckpt_eval.py loss_dynamics.py && echo COMPILE-OK
```

- [ ] **Step 5: 字符串清扫**（不动逻辑）：
- `si_common.py` CONFIG 模板注释：`"test_station": "baimahu",  # 留出测试站（白马湖）` → `"test_station": "<留出测试站拼音/id>",  # 留出测试站（= 实验线 held_out_station）`；补一行 `"test_station_aliases": [],  # 留出站在日志里的可能写法（probe_logs 扫日志用）`；补 `"experiment": "<实验线名>",  # project-context/experiments/ 下的文件名（Step 0.5 写入）`；`"test_label": "<白马湖 true_label parquet>"` → `"<留出站 true_label parquet>"`；`result_analysis_workdir` 注释里 `白马湖线`→`留出站线`、`result_analysis_baimahu/`→`result_analysis_<留出站拼音>/`。
- `run_orient.py`：6/144/150-151/163/169/171/186/188/190 行 print/注释里 `白马湖`→`留出站`（150 行保留 `cfg.get('test_station', ...)` 逻辑，仅改中文提示；default `'baimahu'` → `''`）；`（如雅砻江）`→`（另一条实验线）`；171 行 `result_analysis_baimahu/`→`result_analysis_<test_station>/`。
- `ckpt_eval.py` 2/90 行：`白马湖 RMSE`→`留出站 RMSE`、print `白马湖RMSE=` → `留出站RMSE=`。
- `loss_dynamics.py` 7/11/200/226 行：`白马湖`→`留出站`。
- `adapter_template.py` 47/58 行：`白马湖`→`留出站`。
- `probe_logs.py` 其余：4/128/131 行 `白马湖`→`留出站`。

- [ ] **Step 6: 验证 + Commit**

```bash
cd "$(git rev-parse --show-toplevel)"
grep -rn "白马湖\|雅砻江\|baimahu" pv-station-influence/scripts/*.py | grep -v test_probe_station_pat.py | grep -v "DEFAULT_STATION_PAT = "
```
Expected: 0 行（DEFAULT_STATION_PAT 定义行是历史兼容回退、测试文件用它作 fixture，允许保留）。

```bash
git add pv-station-influence/scripts/probe_logs.py pv-station-influence/scripts/test_probe_station_pat.py pv-station-influence/scripts/si_common.py pv-station-influence/scripts/run_orient.py pv-station-influence/scripts/ckpt_eval.py pv-station-influence/scripts/loss_dynamics.py pv-station-influence/scripts/adapter_template.py
git commit -m "refactor(pv-station-influence): scripts 站名参数化——probe_logs 站名模式从 config 构建（+测试），print/注释去硬编码"
```

---

### Task 8: 顶层文档 + CHANGELOG + 记忆 + 总验收

**Files:**
- Modify: `README.md`
- Modify: `结果分析Skill介绍.md`
- Modify: `pv-result-analysis/CHANGELOG.md`
- Modify: `~/.claude/projects/-Users-tqa946816-Documents-------------skill/memory/pv-forecast-result-analysis-skill.md`、`station-influence-17-stations.md`、`MEMORY.md`

- [ ] **Step 1: README.md**：
- 三技能表 `pv-station-influence` 行 → `多站分块训练的站点影响力归因：找出哪些训练站拖累留出测试站的零样本预测（负迁移），观测归因（Mode A）/ 梯度重训确认（Mode B）；实验设定经 project-context 载入`。
- `pv-result-analysis` 行末尾追加 `；实验设定（站点/划分/路径）经 project-context 载入`。
- 「使用」节第一条 → `- 结果分析：首次进入会经 AskUserQuestion 选定/新建 project-context 实验线（站点、数据路径问一次落盘复用）；也可直接给 训练集 parquet、测试集（true label）parquet、metric.py 路径。`
- 「安装」节 symlink 代码块后加一句：`仓库顶层 project-context/ 是当前项目实例的站点注册表与实验线配置（两技能共享；换项目整目录替换）。`

- [ ] **Step 2: 结果分析Skill介绍.md**：第 31 行 `本技能支持两个电站：**雅砻江（柯拉）**与**白马湖**。…` → `本技能不绑定电站：站点全集、训练/留出划分与数据路径经共享 project-context（站点注册表 + 实验线配置）载入，运行时 AskUserQuestion 问一次落盘复用。当前项目实例有两条实验线（见 project-context/experiments/）：yalongjiang-line（5 站训练 + 雅砻江留出）与 baimahu-line（17 条目分块训练 + 白马湖留出），所有计算与结论按实验线独立进行，不混算。`（介绍文档允许提当前实例站名——它介绍的是本项目。）再全文 grep 与旧 references/station.md 路径相关的行改为 project-context 路径。

- [ ] **Step 3: pv-result-analysis/CHANGELOG.md** 追加一行：`| 2026-07-14 | SKILL.md 全文/references/scripts | 用户要求两技能共享站点信息并泛化 | 站点/实验设定抽到仓库顶层 project-context/（stations.md+station-entries.md+experiments/*.json，经 references/project-context.pointer 定位）；station/seasonality/event-log 迁出 references/；新增 Step 0.5（AskUserQuestion 问一次落盘）；正文站名全部抽象 |`（列格式对齐现有表）。

- [ ] **Step 4: 记忆更新**：
- `pv-forecast-result-analysis-skill.md`：追加/更新——project-context 架构（顶层共享注册表、两层结构站点×条目、实验线 json、pointer 发现、Step 0.5 问一次落盘）；station.md/seasonality.md/event-log.md 已迁出 references/。
- `station-influence-17-stations.md`：更新——技能已泛化为 N 站；17 条目清单与同站多时段事实已入 project-context/station-entries.md；白马湖=baimahu-line 的 held_out_station。
- `MEMORY.md` 两行 hook 同步改。

- [ ] **Step 5: 总验收 grep**（Global Constraints 的零残留范围）：

```bash
cd "$(git rev-parse --show-toplevel)"
grep -rn "白马湖\|雅砻江\|泗洪\|小壕兔\|润达\|和熙\|17 站\|17站\|5 个电站\|baimahu\|yalongjiang" \
  pv-result-analysis/SKILL.md pv-station-influence/SKILL.md \
  pv-station-influence/references/ pv-station-influence/scripts/README.md \
  pv-result-analysis/references/ pv-result-analysis/scripts/README.md \
  | grep -v "references/hypotheses.md"
```
Expected: 0 行。再跑 Task 1 Step 7 的 JSON 校验仍通过；`python3 -m pytest pv-station-influence/scripts/test_probe_station_pat.py -q` 仍 3 passed。

- [ ] **Step 6: Commit**

```bash
git add README.md 结果分析Skill介绍.md pv-result-analysis/CHANGELOG.md
git commit -m "docs: README/介绍/CHANGELOG 同步 project-context 架构；技能不再绑定站点"
```
（记忆文件在仓库外，不入库。）

---

## 自审记录

- **Spec 覆盖**：目录结构与两层注册表（Task 1）、检索预填（Task 2）、pv-result-analysis 抽象化+Step 0.5（Task 3-4）、pv-station-influence 抽象化（Task 5-7）、错误处理（pointer 探测/字段补写/站不匹配——写进两个 Step 0.5 与 run_orient 文案）、验收四条（Task 8 + 各任务 grep）、hypotheses 豁免（Task 4 Step 5）、README/介绍/CHANGELOG/记忆（Task 8）。无缺口。
- **占位符扫描**：文档中的【待补】/【检索】是注册表的**设计内容**（反编造纪律），非计划占位符。
- **类型一致性**：`station_pattern(cfg)`/`DEFAULT_STATION_PAT`（Task 7 测试与实现一致）；config 字段 `experiment`/`test_station_aliases` 在 Task 5（SKILL.md）与 Task 7（si_common/probe_logs）名称一致；entry_id 在 Task 1 两文件间一致（17+6 条）。
