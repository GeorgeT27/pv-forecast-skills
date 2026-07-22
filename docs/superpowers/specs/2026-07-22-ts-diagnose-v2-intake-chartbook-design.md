# ts-diagnose v2：引擎级 intake + provider_skill 委托 + chartbook 图谱库 + model-comparison playbook

日期：2026-07-22
状态：已与用户逐项确认（范围 / intake 层级 / 委托机制 / 路由边界 / 图库形态五个决策点）

## 0. 动机与目标

用户愿景：**用户进站只面对一个入口**（`/ts-diagnose` + 四个专用技能），提出诊断目标
（如「为什么模型 A 比模型 B 好」），引擎负责：

1. 先搞清楚「我们有什么材料」（用户不会一次说全，要 checklist + 追问）；
2. 数据结构当场问清（哪列是 y-label、哪些是 feature——不许猜）；
3. 需要模型侧知识时嵌入调用 pv-model-analysis 再回主流程；
4. 事实提取阶段画一组标准分析图（JSON 一等产物，供无视觉能力的模型做后续归因）；
5. playbook = 流程图，小模块（intake / provider skill / chartbook）具体实施，
   不同 playbook 按需组合。

现有架构已有一半地基（提问纪律、contexts 三分支、playbook frontmatter 驱动 orient），
本轮是**三处加固 + 两个新增**，不推翻任何现有机制。

## 1. 已确认的五个决策

| # | 决策点 | 结论 |
|---|--------|------|
| 1 | 本轮范围 | 框架改动 + model-comparison playbook 一起做（框架需要第一个消费者验证） |
| 2 | intake 层级 | 引擎级材料分类表 + playbook 声明需求（required/optional），不做独立 skill、不逐 playbook 重复声明 |
| 3 | skill 调 skill | 主 agent 内联执行（保留提问权），泛化 pv-station-influence 已验证的 ask-then-embed 模式进 playbook 规范 |
| 4 | 路由边界 | 专用优先不变：pv-result-analysis 标准场景仍走专用技能；model-comparison 接非标格式/每模型一 parquet/任意模型集合/非光伏时序 |
| 5 | chartbook 形态 | 引擎级共享库（非独立 skill）+ 一个 fact-scan 薄 playbook 作用户直达入口 |

## 2. 组件① 引擎级材料盘点（intake）

### 新文件 `ts-diagnose/references/intake.md`

统一材料分类表。每类材料一节，含：

- **id**（进 check-DSL 与 config）：`predict` / `truth` / `model_code` / `training_log` /
  `features`（预测特征序列，NWP 等）/ `feature_true`（特征真值对照）/ `train_y`
  （训练期真值，漂移图用）/ `checkpoint` / `serving_api`（反事实端点）/
  `experiment_config` / `data_profile`（可扩展，新增类照本文件格式追加）；
- **追问模板**：在哪（路径）、什么格式（每模型一个文件还是合并、贴 2-3 行样例）、
  覆盖范围（时间/站点）；
- **schema 追问块**（本轮新增重点）：哪列是 y-label、哪些列是 feature、时间戳列、
  id/分组列、单位——答案结构化落 `materials.<id>.schema`。这是「必问五类」第 1 条
  （schema 不明必问）的结构化落地：**不清楚就问，不许猜**；
- **证据自答探测**：如 glob 命中即可免问路径（沿用 skip_if 思想）。

### 盘点流程（绑定 playbook 后、Stage 0 前，engine-core 新增 Step 0.75）

1. 一次 AskUserQuestion **多选 checklist**：「你手头有哪些材料？」——选项 = 该 playbook
   声明的 required + optional 材料集。checklist 本身就是提醒器（解决「用户不一次说全」）；
   末尾固定追一项开放的「还有别的吗？」。
2. 对每个勾选的材料按追问模板**批量**追问（≤4 题/次，沿用提问纪律§3）。
3. 答案落 `diagnose_config.json` 新增 `materials` 块：

```json
"materials": {
  "predict": {
    "status": "present",
    "paths": ["runs/mA/pred.parquet", "runs/mB/pred.parquet"],
    "layout": "per-model",
    "schema": {"y_col": "power_pred", "time_col": "ts", "id_col": "station"},
    "sample_rows": "<用户贴的原话样例>",
    "source": "user", "date": "2026-07-22"
  },
  "training_log": {"status": "absent-confirmed"}
}
```

- `status` 三值：`present` / `absent-confirmed`（用户明确说没有）/ `unknown`（未问）。
  **absent-confirmed 才允许降级路径；unknown 阻塞**——延续「绝不静默降级」纪律。
- `sample_rows` 存用户原话（提问纪律§4：answer 存原话不存转述）。
- materials 块与 questions 块同为 crystallize 固化原料（跨次稳定条目进 profile.yaml）。

### orient.py 改动

- playbook frontmatter 新增顶层键：

```yaml
materials:
  required: [predict, truth]        # unknown/absent 均阻塞 Stage 0（absent-confirmed 时按 playbook 降级说明）
  optional: [model_code, training_log]
```

- orient 输出新增「材料盘点」段：✓present / ✗required-unknown（阻塞）/
  ○optional-unknown / −absent-confirmed；
- check-DSL 新增表达式 `material:<id>`（= materials 块该 id 的 status 为 present），
  可用于 prereqs.check / variants.when / questions.skip_if——**阶段与变体按材料解锁**；
- 兼容：无 materials 键的既有三个 playbook 行为完全不变（回归测试守卫）。

## 3. 组件② contexts 升级：provider_skill（skill 调 skill 再回来）

`_playbook-spec.md` contexts 新增两个可选字段：

```yaml
contexts:
  - id: model-profile
    name: 模型参考档案
    provider_skill: pv-model-analysis   # 新：谁能生产这个上下文
    trigger_material: model_code        # 新：该材料 present 才提议嵌入生产
    workdir_key: modelmap_dir
    status_key: modelmap_status
    marker_files: [".modelmap/models.md"]
    on_absent: ask
```

### 执行语义（engine-core 新增「嵌入执行 provider skill」一节）

1. 材料盘点后，context absent 且 `trigger_material` 为 present →
   AskUserQuestion：「有模型代码，要不要我现在嵌入跑 pv-model-analysis 生成模型档案，
   跑完回来继续？」（列大致成本）。
2. 同意 → **主 agent 内联读 provider skill 的 SKILL.md 完整执行**——保留提问权
   （能问「哪个是产线版本」这类必须用户裁决的问题），不经 subagent（subagent 无提问权）。
3. 产物落盘、按 marker_files 核验、写回 config 的 workdir_key/status_key=linked，
   PROGRESS.md 记「嵌入执行 <skill> 起止」两行。
4. 回主流程重跑 orient（重扫后 context 变 linked），继续推进。
5. 拒绝 → status_key=declined，结论按现有纪律注明缺失。

pv-station-influence 现有的 ask-then-embed 行为不动（它是专用技能自己实现的），
本设计只是把该模式写进 playbook 规范供引擎 playbook 使用。

## 4. 组件③ chartbook 图谱库（引擎级共享库）

位置：`ts-diagnose/chartbook/`。**不是独立 skill**（图从不是用户最终目的、独立 skill
要重复 intake、占路由预算）；playbook 层互不引用的 layering 纪律不受影响——共享下沉到
引擎层是合法的（同 references/ 地位）。

### 预写 vs 现场写（关键决策：**预写**）

图脚本**预先写好、随引擎提交、pytest+golden 验证**，不在跑 skill 时现场生成。理由：

1. **先例已验证**：pv-result-analysis 的 fig01-fig12 就是预写的 `plots.py` + stats.json
   自足产物，实跑多轮稳定——chartbook 是同一模式的引擎级泛化；
2. **图是稳定复用件**：引擎「分析代码运行时生成」纪律是为**没见过的新任务**设计的；
   chartbook 恰是各 playbook 反复消费的标准件，属于引擎机制（同 orient.py 地位），
   预写+CI 验证一次，胜过每次现场写+现场过验证步；
3. **token 经济**：现场写十几张图的代码极耗 token 且每次重付；预写后现场只剩三件事：
   写**薄适配器**（几十行：用户数据 → 规范长表，由 materials.schema 驱动）、Bash 跑脚本、
   读紧凑 JSON。**不需要 subagent**——只有数据格式极乱、适配器需反复试错解析，或
   多站多模型大批量分片跑时，才按现有 subagent 编排纪律外包（brief 里只带 schema 与
   样例行，不带图代码）。

engine-core 的「分析代码运行时生成」纪律加一句豁免：chartbook 覆盖的图**必须**用
chartbook 预写脚本（禁止现场重写同类图）；运行时生成只用于 chartbook 没有的
playbook 特有分析。

### 规范数据接口（脚本与用户数据解耦）

所有图脚本消费统一的**规范长表**（canonical long format）：

```
predictions.parquet: window_ts | unit_id | model | horizon_step | y_true | y_pred
features.parquet(可选): window_ts | unit_id | feature | horizon_step | f_pred | f_true(可选)
train_y.parquet(可选): ts | unit_id | y        # 漂移图用
```

现场唯一要写的代码 = `adapter.py`：用户的任意格式（每模型一 parquet、192 点 list 列、
宽表……）→ 规范长表，由 `materials.<id>.schema` 的答案驱动，写完先过**对账验证步**
（行数守恒 + 抽 3 个窗口人工核对数值）再喂图脚本。

### 结构

```
chartbook/
├── _recipe-spec.md          # recipe 编写规范（本节字段定义）
├── scripts/                 # 预写图脚本（一 recipe 一脚本，CLI 契约，消费规范长表）
│   ├── chart_common.py      # 读长表/落 json+png/形状描述符公共件
│   └── chart_<recipe-id>.py
├── golden/                  # 图脚本金标准（合成植入回收，pytest 驱动）
└── recipes/<id>.md          # 每图一 recipe：适用问题/JSON schema/判读节/桥接钩子
```

每个 recipe（frontmatter + 正文菜谱）：

```yaml
id: horizon-degradation
needs_materials: [predict, truth]    # material: DSL 联动；缺材料 → orient 报「不可用」
适用问题: 短期准长期崩？哪个 target 在长 horizon 崩溃？退化速度对比？
outputs:
  json: horizon_degradation.json     # 一等产物
  png: horizon_degradation.png       # 人看的副产品
json_schema: >
  每模型每 horizon 的指标数组、退化斜率（早段/晚段）、模型间交叉点 horizon、
  per-target 崩溃 horizon、形状描述符
bridge_hooks: >                      # 桥接钩子：形状描述符 → 架构假设的映射指引
  晚段斜率陡 + 早段平 → 长程依赖衰减类假设（如 attention 窗口/位置编码外推）
验证步: 合成已知退化曲线（解析式构造）→ 脚本必须回收出植入的斜率与交叉点
```

### 硬规则

1. **JSON 是一等产物，PNG 是副产品——没有 JSON 的图不算完成**。JSON 自足
   （完整数字 + 形状描述符），后续机制归因只读 JSON 不读 PNG（模型无视觉能力；
   这是现有「产物自足」纪律升格为图谱规范）。
2. JSON 预置 `bridge_hooks` 相关的形状描述符字段，让 pv-model-analysis 的桥接假设
   （H-ID）能直接对上号。
3. 每个 recipe 带验证步（合成植入回收）；被 playbook golden 覆盖到的照常走 gen_gate。
4. 图脚本预写在 `chartbook/scripts/`（本节预写决策）；运行时生成进 `analysis_scripts/` 的
   只有薄适配器 `adapter.py`（用户数据 → 规范长表），不含任何画图代码。

### v1 recipe 集（五组；A-C 组核心先行，D-E 组按材料驱动同轮实现、批次靠后）

用户点名的四张只是例子；v1 同时**收编泛化 pv-result-analysis fig01-fig12** 的通用部分
（代码可移植改造，站点/模型维度参数化；光伏专属的 fig12 功率-辐照泛化为
`y-vs-feature-mapping`）。零跨 skill 依赖纪律照旧：chartbook 拿的是泛化副本，
pv-result-analysis 自己的 plots.py 不动、不被引用。

**A 组：y-label 误差分解（用户强调最重要——谁、什么时候、错在哪）**

| recipe | 内容（源） | JSON 关键字段 |
|---|---|---|
| `error-breakdown` | 分单元(站点)×日历(月/日/小时)×horizon 的误差矩阵热力图：**什么站点什么时候 RMSE 最大**（新写，核心图） | 分组指标矩阵、argmax 单元格、per-站点/per-月/per-小时边际曲线、Top-K 最差组合 |
| `intraday-profile` | 日内时段 bias/RMSE 剖面（fig06 泛化） | 逐时段 bias/RMSE 曲线、形状描述符 |
| `worst-points` | 误差 top-N（默认 20）点，自动打标签：极值/转折点(ramp)/高波动（fig07 泛化到点级） | 每点时间戳、单元、误差、标签、上下文统计 |

**B 组：走势与稳定**

| recipe | 内容（源） | JSON 关键字段 |
|---|---|---|
| `horizon-degradation` | 指标随 horizon 退化速度；短期准 vs 长期失效；per-单元崩溃点（fig05 泛化） | 每模型每 horizon 指标、早/晚段斜率、模型交叉点、崩溃 horizon |
| `rolling-stability` | 滚动 MAE/bias、变点检测（前后对比）、日历时段分组（新写） | 滚动序列(降采样)、变点列表、日历切片表 |

**C 组：模型对比**

| recipe | 内容（源） | JSON 关键字段 |
|---|---|---|
| `true-vs-pred-scatter` | 真值-预测散点 slope/R² 四象限（fig01 泛化，判读纪律带过来：R² 管齐不齐、slope 管正不正） | slope、r2、分位残差 |
| `model-error-correlation` | 模型间误差相关热力图——同质化/互补性（fig02 泛化） | 相关矩阵、最互补对 |
| `worst-slice-compare` | 模型 A 最差月份/最差片上 A vs B 同期对比（新写） | 片选择依据、片内各模型指标、逐日分解 |
| `oracle-gap` | 逐样本动态选最优模型的提升空间（fig09 泛化；模型≥2 时可用） | oracle 指标、各模型被选率、差距 |

**D 组：feature 关联（needs_materials 含 feature；完整重要性归因仍属
feature-importance playbook / pv-feature-blame——本组只产图级事实）**

| recipe | 内容（源） | JSON 关键字段 |
|---|---|---|
| `feature-error-conditional` | 按 feature 值/质量分箱的条件误差：**feature 不准时对 y-label 影响大不大**（fig08 天气分型泛化） | 分箱条件指标、单调性、效应幅度 |
| `feature-trend-overlay` | 坏片上 feature 走势与 y 误差 overlay 对照（新写） | 对齐序列(降采样)、同步性描述符 |
| `y-vs-feature-mapping` | y 与关键 feature 的映射关系训练/测试对比（fig12 泛化） | 映射曲线、偏移描述符 |

**E 组：分布漂移（needs_materials 含 train_y）**

| recipe | 内容（源） | JSON 关键字段 |
|---|---|---|
| `train-test-drift` | 训练/测试同期分布对比——标签与 feature 漂移（fig11 泛化） | 分布分位数、漂移统计量 |

### 判读库（收编 figure-diagnostics 模式）

每个 recipe 正文带**判读节**：「JSON 形状描述符 → 候选机制 → 去哪张图交叉验证」，
泛化 pv-result-analysis figure-diagnostics.md 的纪律：判读只给**候选假设**不给结论，
结论必须回 playbook 的三道门；判读一律读 JSON 描述符（curve/trend/max_jump/
roughness/argmax），**不 Read PNG**。

### playbook 消费方式

playbook frontmatter 阶段级声明（或正文菜谱引用 recipe id）：

```yaml
stages:
  - id: 2
    name: 差距分解（事实）
    charts: [horizon-degradation, rolling-stability, worst-points, worst-slice-compare]
```

orient 按 `needs_materials` 报每张图可用/不可用；材料不够的图跳过并在现象清单注明
（不算失败）。robustness / training-sufficiency 后续可各自声明 `rolling-stability`
等——复用点即在此。

**画图决策不需要用户提示**（三层自动判定）：

1. **该看哪些**：playbook 阶段 `charts` 声明——「这个诊断目标该画什么图」是 playbook
   知识，不依赖用户点名；
2. **能画哪些**：recipe `needs_materials` × intake 盘点结果，orient 自动判定；
   缺材料的图自动跳过并在现象清单注明「因缺 <材料> 未画」，不问用户；
3. **用户点名只是补充**：`pause_after` 停顿汇报时附「已画/跳过」清单，用户可
   追加点图或调参数（top-N、切片粒度）——可选，不是流程前提。

## 5. 组件④ model-comparison playbook

`playbooks/model-comparison/`（独立目录，Layer 1 纪律照旧）。

- **定位**：「为什么模型 A 比模型 B 好/差、多模型对比归因」，接**非** pv-result-analysis
  标准场景（格式不标准 / 每模型一个 parquet / 任意模型集合 / 非光伏时序任务）。
- **materials**：required `[predict, truth]`；optional `[model_code, training_log,
  experiment_config]`。
- **contexts**：`model-profile`（provider_skill: pv-model-analysis，
  trigger_material: model_code，见组件②）。
- **阶段**：

| Stage | 名称 | 要点 |
|---|---|---|
| 0 | 口径与对齐 | 考核口径（默认 rmse_192，可自定义）、对齐键、比哪几个模型（>2 个时问配对）——questions 声明 |
| 1 | 总差距事实 | 对齐后逐模型指标、差距量化 + 配对检验（差距是真的还是噪声）——事实阶段 |
| 2 | 差距分解 | charts 声明 A+B+C 组全部 recipe（D/E 组按材料可用性自动加入）；A 赢在哪些片、差距集中还是普遍——事实阶段，`pause_after: true`，产现象清单等用户点名 |
| 3 | 机制归因（变体） | `when: material:model_code` 解锁；经 model-profile 上下文拿桥接假设，对照 Stage 2 的图 JSON 证据 |
| 4 | 结论 | 三道门 + provenance 归因闸 + CONCLUSION.md 直接呈现 |

- **evidence_lines**：总指标线（Stage 1）+ 切片线（Stage 2）；
  `upgrade_rule`: 两线方向一致（总差距方向与主导切片方向相符）才升「假设」。
- **golden/**：make_golden.py 解析式构造两个合成模型预测——植入已知差距结构
  （一个整体好但特定片/特定 horizon 段差），manifest 断言总指标排序、交叉点 horizon、
  最差片识别；reference/ 按菜谱写参考实现。gen_gate 覆盖 Stage 1、2 脚本。

## 6. 组件⑤ fact-scan 薄 playbook（图库用户直达入口）

`playbooks/fact-scan/`。用户「只想看图/体检一遍，不要诊断结论」时命中。

- **流程**：intake（组件①）→ 按材料可用性画 chartbook 全部可用图 → 现象清单
  （FINDINGS.md 只写「现象」，禁机制语言）→ **停**，不进结论阶段。
- **阶段**：Stage 0 口径与对齐（同 model-comparison 精简版）→ Stage 1 画图 + 现象清单
  （`pause_after: true` 且为终点）。无 evidence_lines、无结论三道门（因为不下结论）。
- **衔接**：用户看完想深挖 → 切 model-comparison（或其他 playbook），materials 块与
  图 JSON 全部复用，orient 重扫自动跳过已完成部分。
- **golden/**：断言各可用图 JSON 的关键字段存在且数值正确。注意 Layer 1 零共享纪律：
  不与 model-comparison 共享 make_golden.py，fact-scan/golden/ 自带精简版生成器
  （思路可同、代码各自独立）。

## 7. 组件⑥ 路由与 description 更新

- `ts-diagnose/SKILL.md` 路由表加两行：

| 用户的目标像这样 | playbook |
|---|---|
| 为什么模型 A 比模型 B 好/差、多模型对比归因（非 pv-result-analysis 标准场景：格式不标准/每模型一个 parquet/任意模型集合/非光伏） | `model-comparison` |
| 只想体检/画标准分析图/看现象不要结论 | `fact-scan` |

- SKILL.md description 同步补两个目标的触发语；**≤60 行 / token 预算 CI 必须继续过**
  （行数紧张则压缩既有措辞，不放宽 CI）。
- `pv-result-analysis` SKILL.md description 负面清单反向加一句：非标准格式/任意模型
  集合的模型对比 → ts-diagnose 的 model-comparison。
- 路由优先级四层顺序不变：固化代理 > 专用技能 > 引擎 playbook > 写新 playbook。

## 8. 测试与守卫

| 对象 | 测试 |
|---|---|
| orient.py materials 解析 + 盘点报告 + `material:` DSL | 新增单测（含无 materials 键的旧 playbook 兼容回归） |
| contexts provider_skill/trigger_material 解析 | orient 单测 |
| chartbook recipe frontmatter 规范 | 新增 test_chartbook.py：全部 recipe 过 _recipe-spec 校验（必备字段、needs_materials 合法 id、json/png 双产物声明、判读节存在） |
| chartbook 预写图脚本 | 每个 chart_<id>.py 一套 golden（合成植入回收：已知斜率/变点/最差单元格/相关结构必须被回收），pytest 驱动；chart_common.py 单测 |
| 规范长表 adapter 契约 | adapter 对账验证步写进 intake.md/engine-core（行数守恒 + 抽窗核对），golden 里附一个「非标格式 → 长表」示例适配 |
| model-comparison golden | gen_gate 端到端（reference 实跑出期望值，留容差） |
| fact-scan golden | 同上（精简版） |
| Layer 纪律 | test_layering.py 扩展覆盖两个新 playbook 目录 + chartbook（引擎级共享合法、playbook 引用 recipe id 合法、playbook 间互引仍非法） |
| SKILL.md 预算 | 现有 token 预算 CI 继续过 |
| 全仓 | 现有 100+ pytest 全绿 |

## 9. 明确不做（YAGNI / 排后续轮）

- 四个专用技能的入口与内部流程不动（pv-station-influence 的 ask-then-embed 保持自有实现）；
- pv-result-analysis 能力不迁移进引擎；
- pv-model-analysis 的事实提取增强（做什么图、什么提取物）——用户已预告后续轮，
  组件②的 provider_skill 接口已留好位置；
- chartbook 独立用户 skill 化——fact-scan 已覆盖直达需求；
- 实验线 v0→v1 迁移（原占位不变）。
