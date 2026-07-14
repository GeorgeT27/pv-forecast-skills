# 设计：project-context 共享站点注册表 + 技能泛化（AskUserQuestion 运行时配置）

日期：2026-07-14
状态：已获用户口头批准（本文档为定稿记录）

## 背景与目标

pv-result-analysis 与 pv-station-influence 两个技能各自硬编码了一套实验设定：

- pv-result-analysis：旧设定（5 训练站 + 雅砻江留出），写死在 SKILL.md 第 15 行与 `references/station.md`；
- pv-station-influence：新设定（17 训练条目分块训练 + 白马湖留出），写死在 SKILL.md 的 description、各 Stage 表、反模式清单等 20+ 处。

两条实验线**都在跑**。用户提供了 17 条目清单（见下），并要求：

1. 站点信息抽成两技能之外的**共享外部信息**（outer info）；
2. 两个 SKILL.md **彻底抽象**——正文不再出现具体站名/数量/划分，任何新项目拿来即用；
3. 运行时用 **AskUserQuestion** 收集本次分析的站点/数据信息，**问一次落盘**，同实验线续跑不再问；
4. 新站点的地理/气候信息由 Claude 联网检索预填，标【检索】待核实。

### 关键领域事实（用户澄清）

- 清单里的"17 个"是 **17 份训练数据条目**，不是 17 个物理站：**同名站点可因数据时间段不同出现多次**。已知：1012 华能北方润达 与 无编号华能北方润达 是同站不同时段；末尾无编号"雅砻江"= 雅砻江解放站（与 1005 同站，时段可能不同）。
- 白马湖不在 17 条目内（它是白马湖线的留出测试站）；雅砻江在 17 条目内（旧设定里它是留出站）——**训练/留出划分不能写进站点表，必须独立成"实验线配置"层**。

### 17 条目清单（用户提供，2026-07-14）

```
1002 黄河水电共和红旗二光伏电站
1003 大朝山西光伏电站
1004 黄河水电共和红旗八光电站
1005 雅砻江水电坷拉一期解放
1006 雅砻江水电坷拉一期庆达
1009 国家能源集团茂克
1010 幕家湾光伏电站
1012 华能北方润达光伏电站
1015 湖北华店襄城卧龙农光互补发电项目
1016 阳江中能建光伏电站
1019 保定满城白龙
1022 国电投东辛农场
华能北方润达光伏电站      （无编号；=1012 同站，时段不同）
国能和熙光储电站
泗洪光伏电站
西北戈壁小壕兔
雅砻江                    （无编号；=雅砻江解放站，时段可能与 1005 不同）
```

## 备选方案与决策

| 方案 | 内容 | 结论 |
|------|------|------|
| **A（采纳）** | 仓库顶层 `project-context/` 目录 + 各技能 `references/project-context.pointer` | 技能与项目数据物理分离；沿用 model-ref.pointer 先例 |
| B | canonical 留在 pv-result-analysis 内，另一技能 pointer 消费 | 不对称，违背"outer info"意图，弃 |
| C | 做成第三个"知识技能"（带 SKILL.md、symlink 进 skills） | 无工作流的空技能是噪音，项目数据混入技能发布，弃 |

## 第 1 节：project-context/ 结构与文件格式

```
project-context/
├── README.md               ← 声明：本目录 = "当前项目实例"的全部事实；换项目整目录替换（或改 pointer）
├── stations.md             ← 物理站档案（~16 站：地理/气候/装机/形式/限电；字段带 ✅确认/【检索】/【待补】）
├── station-entries.md      ← 数据条目表：entry_id | 编号 | 物理站 | 数据时段 | 备注
├── seasonality.md          ← 自 pv-result-analysis/references/ 迁入（git mv 保历史）
├── event-log.md            ← 同上迁入
└── experiments/
    ├── yalongjiang-line.json    ← 雅砻江线：5 训练站 + 雅砻江留出
    └── baimahu-line.json        ← 白马湖线：17 训练条目 + 白马湖留出
```

**两层结构**：

- `stations.md` 管**物理站**——每个站一份档案（雅砻江柯拉解放只有一份，不管有几个数据条目）。
- `station-entries.md` 管**数据条目**——`entry_id` 为主键；有编号的条目用编号（`1002`…`1022`），无编号的由注册表分配稳定 slug（如 `runda-b`、`yalong-jiefang-b`、`hexi`、`sihong`、`xiaohaotu`）。实验线配置**只引用 entry_id**。

**实验线配置 JSON schema**（AskUserQuestion 答案的落盘处）：

```json
{
  "name": "baimahu-line",
  "description": "17 条目分块训练，白马湖留出零样本",
  "held_out_station": "白马湖",
  "training_entries": ["1002", "1003", "…", "runda-b", "yalong-jiefang-b"],
  "chunking": {"n_chunks": 4, "sizes": [5, 5, 5, 2], "epochs_per_chunk": 20},
  "models": ["M1", "M2", "M3", "M4"],
  "data_paths": {
    "train": "【待补】",
    "test_label": "【待补】",
    "metric_py": "【待补】",
    "predictions": {}
  },
  "source": "AskUserQuestion 2026-07-14"
}
```

字段约定：`held_out_station` 与 `training_entries` 必填；`data_paths` 允许【待补】占位（缺时运行到需要处追问并**补写回本文件**）；`chunking`/`models` 按实验线可选。

**发现机制（pointer）**：

- 两技能各放 `references/project-context.pointer`（key: value 纯文本：`path=<project-context 绝对路径>`、`written=<日期>`），沿用 model-ref.pointer 先例。
- pointer 缺失/失效时的探测顺序：① 相对路径 `<技能目录>/../project-context`（symlink 安装下内核物理解析可达）；② AskUserQuestion 问路径；拿到后写回 pointer。

## 第 2 节：SKILL.md 抽象化 + 运行时问答流程

**统一运行时流程**（写进两个技能的 Step 0 / orient）：

1. 读 pointer → 定位 project-context；
2. 列出 `experiments/*.json` → AskUserQuestion：**选已有实验线，还是新建**；
3. 选已有 → 载入；缺关键字段（如数据路径）才追问，并补写回 json；
4. 新建 → AskUserQuestion 收集：目标/留出站、训练条目（对照 station-entries.md 列候选）、数据路径、chunking → 写 `experiments/<name>.json`；
5. 同一实验线续跑**不再问**（analysis_config 记实验线名）。

**逐技能改动**：

- `pv-result-analysis/SKILL.md`：第 15 行"核心设定"段改为"训练/留出划分与站点全集经 project-context 载入"；正文"雅砻江"→"留出测试站"、"5 训练站"→"训练站集合"；station/seasonality/event-log 的引用路径改为经 pointer；`references/` 下这三个文件 `git mv` 迁走。
- `pv-station-influence/SKILL.md`：description 与正文"17 站"→"N 站分块"、"白马湖"→"留出测试站"；预测侧接续的"station=白马湖"校验改为"station=实验线 held_out_station"；references/（attribution-discipline.md、influence-methods.md、subagent-briefs.md）及 scripts/README.md 中的具体站名同步抽象，具体例子改为引用实验线配置。
- `pv-model-analysis`：不动（站点无关）。
- 脚本层基本不动（站点名从数据/CSV 列流入）；只需 orient 类脚本加"读实验线 json"入口。

## 第 3 节：注册表预填、错误处理、验收

**预填**：

- 9 个新站（黄河水电共和红旗二/八、大朝山西、茂克、幕家湾、湖北华店襄城卧龙、阳江中能建、保定满城白龙、国电投东辛农场）由 Claude 联网检索地理/气候/装机，**全部标【检索】**待用户核实；
- 已有 6 站（泗洪、白马湖、小壕兔、润达、和熙、雅砻江）档案从旧 station.md 迁移保留（含既有 ✅/【检索】/【待补】标注与勘误注释）；
- **所有数据时段一律【待补】**（反编造纪律：查不到不编）。

**错误处理**：

- pointer 失效 → 相对路径探测 → AskUserQuestion；
- 实验线 json 缺字段 → 追问一次、补写回文件；
- 预测侧产物 station 与实验线 `held_out_station` 不匹配 → 红字警告、拒绝消费（现有白马湖专用逻辑的泛化）。

**验收标准**：

1. `grep` 零残留范围：两个 SKILL.md、pv-station-influence/references/ 与 scripts/README.md、pv-result-analysis/references/figure-diagnostics.md 与 subagent-briefs.md——具体站名/编号/"17 站"不得出现（仅 project-context/、CHANGELOG、docs/ 历史文档允许）。**豁免**：`pv-result-analysis/references/hypotheses.md` 的假设行是运行产物（类似 FINDINGS.md，随项目重置，且 pv-model-analysis 跨技能契约向其追加行），不强制清洗，但需在表头加注"行内容属当前项目实例"；
2. 两个实验线 json 可被手工读出且必填字段齐全；
3. README.md、结果分析Skill介绍.md 同步更新（三技能表 + 使用说明提及 project-context）；
4. pv-result-analysis/CHANGELOG.md 增行；记忆（memory/）更新。

## 约束

- **并发安全**：沿用仓库纪律——绝不 `git add -A` / `git add .`，只按显式路径 stage；每个任务原子提交。
- 迁移文件用 `git mv` 保历史。
- 本仓库连接 GitHub（pv-forecast-skills，改名待用户操作）；project-context/ 含项目事实，随仓库发布——用户已知悉（此前 station.md 同样入库）。
