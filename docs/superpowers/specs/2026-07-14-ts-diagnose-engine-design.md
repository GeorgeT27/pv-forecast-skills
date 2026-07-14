# 设计：ts-diagnose 泛化时序诊断引擎 + 技能固化（crystallize）机制

日期：2026-07-14
状态：已获用户批准（本文档为定稿记录）

## 背景与目标

仓库现有三个技能（pv-result-analysis / pv-station-influence / pv-model-analysis）都是针对特定实验线的专用技能。用户的问题：同类时序任务换一个关注点（本次真实需求："训练是否充分、是否 batch 不足、chunk 间训练分配问题"）时，想复用这些技能里已验证的 workflow——orient 续跑、事实/解释隔离、结论三道门、多证据线、subagent 编排——而不是每次重写一个专用技能。

方案：新建**泛化引擎技能 `ts-diagnose`**，分析目标以 playbook 挂载；专用需求经 **crystallize（固化）** 操作从一次成功运行沉淀为薄代理技能。三个现有专用技能与 project-context/ 本轮**一行不动**。

## 用户拍板的四个决策

| # | 决策 | 内容 |
|---|------|------|
| 1 | 形态 | **引擎 + 薄配置**：一个引擎技能 + playbooks/；专用技能 = 引擎 + 已固化 profile |
| 2 | 固化产物 | **薄代理技能**：SKILL.md（~50 行）+ profile.yaml（路径/schema/已答问答对/playbook 名）+ scripts/（验证过的脚本快照）；不做完整快照展开（引擎升级时薄技能自动受益） |
| 3 | Playbook 范围 | 三个全要：training-sufficiency（最深，自 pv-station-influence Stage 0–2 泛化）、robustness、feature-importance；附 `_playbook-spec.md` 接口规范 |
| 4 | 脚本策略 | **混合**：引擎只带领域无关机制脚本；分析代码由 agent 按 playbook 菜谱运行时生成进工作目录 `analysis_scripts/`；crystallize 只快照验证过的脚本 |

时序：project-context 设计已先行落地（5ec7ff8…f6ee493），ts-diagnose 直接对接其实验线机制（可选层），不再"预留接口"。

## 目录结构

```
ts-diagnose/
├── SKILL.md                       # ≤200 行
├── CHANGELOG.md
├── scripts/                       # 只有领域无关机制层
│   ├── orient.py                  # 通用续跑/阶段定位（阶段由 playbook frontmatter 定义）
│   ├── engine_common.py           # frontmatter 解析、check-DSL、问题状态、profile/实验线合并
│   ├── tests/test_engine.py       # pytest（training-sufficiency frontmatter 作 fixture）
│   └── templates/                 # FINDINGS / HYPOTHESES / ANALYSIS 模板
├── playbooks/
│   ├── _playbook-spec.md          # playbook 接口规范（frontmatter schema + 正文必备节 + 编写纪律）
│   ├── training-sufficiency.md
│   ├── robustness.md
│   └── feature-importance.md
└── references/
    ├── mechanisms.md              # 事实/解释隔离、三道门、多证据线、stats 自足、上下文预算
    ├── question-discipline.md     # 提问纪律（必问五类 / 可默认 / 批量提问 / 落盘格式）
    ├── subagent-briefs.md         # 参数化 Brief-FACT / Brief-COMPUTE 模板
    ├── crystallize.md             # 固化流程 + profile.yaml schema + 三步验证
    └── conclusion-reporting.md    # CONCLUSION 写法（自 playbooks.md 去领域化）
```

## 核心机制

### 1. playbook frontmatter（orient.py 机器读）

`id/name/goal`、`stages`（`done_when.artifacts` glob + `findings_marker` + `manual` 逃生门；`prereqs` 用 check-DSL：`config:<key>` / `file:config.<key>` / `artifact:<glob>` / `stage:<id>` / `question:<qid>`，`（可选）`前缀不阻塞）、`variants`（泛化 Mode A/B，条件不满足的阶段"跳过不阻塞"）、`questions`（`{id, stage, ask, why, options?, default?, skip_if?}`）、`contexts`（泛化 ask-then-embed 三分支）、`evidence_lines + upgrade_rule`。

### 2. 通用 orient.py

新实现，提取两个现有 run_orient.py 的交集骨架（不改、不 import 它们）：真相以产物为准、当前阶段=首个未完成、--goto 前置校验、state+PROGRESS 单写者、可选前置不阻塞、变体识别、上下文三分支打印。差异：阶段定义不再硬编码 Python 函数，改由 playbook frontmatter 驱动（pyyaml 解析，requirements.txt 新增）。输出四块：阶段表 → 上下文 → **问题清单（✓user/✓profile/✓默认/✓实验线/✗未答·阻塞 Stage N）** → 目标阶段前置。

### 3. 提问纪律（一等公民）

- 答案统一落 `diagnose_config.json` 的 `questions` 块（`{answer, source: user|profile|default|experiment-line, date}`）。
- 未答且无 default → 对应 stage 前必须 AskUserQuestion（同阶段批量合并提问）；`skip_if` 证据自答则不问。
- 引擎级恒问五类（不依赖 playbook 声明）：① schema/单位/口径不明；② 成功判据未定义；③ 证据不足以升级——问"接受降级还是补证据"；④ 破坏性/昂贵操作；⑤ 多候选文件。
- subagent 无提问权，停顿点只在主 agent。

### 4. project-context 对接（可选层）

orient 探测 `<技能目录>/../project-context`；找到 → 列实验线供选择预填（对应 question 标 `source: experiment-line`），【待补】占位照常问、答案补写回实验线 json（沿用两专用技能纪律）；找不到 → 静默跳过。crystallize 的 profile 对与实验线重叠的字段写 `experiment_line: <name>` 引用不复制，防两处漂移。

### 5. crystallize（固化）

触发：一次运行到达结论阶段 + 用户表示复用意愿。流程：AskUserQuestion 收集技能名/触发词/稳定 vs 每次变的路径 → 生成薄技能（SKILL.md ~50 行 + profile.yaml + 验证过的脚本快照，头部带 provenance 注释）→ 三步验证（冷启动 orient --profile / 快照脚本 py_compile 冒烟 / 可选影子重跑 diff <1%）→ README 加行 + symlink 提示。profile_version 不匹配时 orient 警告并降级为"按 playbook 现问"。

## 三个 playbook 要点

- **training-sufficiency**（最深）：探测（泛化 probe_logs）→ 曲线提取（长表 unit,group,epoch,loss；unit 泛化 chunk/fold/run）→ 动力学指标（final_loss/conv_slope/plateau_epoch，自 influence-methods.md Stage 1 去领域化）→ 成分回归（中心化指示+岭+sum-to-zero）→ 外部指标关联（Spearman，仅佐证）→ 结论（充分性判据按用户答案；"loss 效应≠目标效应"四象限）。陷阱：震荡≠异常、loss 高≠有罪、跨模型不 pool 量纲；单元 <10 只报排名；支持单曲线退化形态。
- **robustness**：基线 → 扰动矩阵（剔最差 k/子期/分组切片/配对检验）→ Wilcoxon+剔除方向不变 → 稳定性报告；两扰动族一致才升级。
- **feature-importance**：permutation/剔除重算/相关筛查，两法 Spearman 一致才升级；必问泄漏列与重要性口径；"重要≠因果"。

## 与专用技能的关系（README 口径）

三个 PV 专用技能概念上是引擎的"已固化实例"**先例**：先于引擎存在、不经 profile 机制、原样保留。新诊断目标走引擎；成熟后 crystallize 成新的薄专用技能。引擎 description 写明负面清单（光伏结果评估/留出站归因/模型档案 → 三个专用技能），防触发抢占。

## 实施顺序与验收

1. 机制层（spec/engine_common/orient/templates）→ pytest 全绿；
2. training-sufficiency + SKILL.md + references → frontmatter 可解析、问题清单打印正确；
3. **影子验证**：合成数据（3 模型 × 8 迭代 × 4 chunk，植入已知效应）全程走一遍——召回效应方向、产物形态与 pv-station-influence Stage 0–2 对齐、必答题零跳过；
4. 另两个 playbook + dry-run；
5. crystallize.md + 固化演练（demo 薄技能放 scratchpad 不提交）；
6. README/介绍/CHANGELOG/requirements.txt(+pyyaml)；终检：三个专用技能目录与 project-context/ 的 `git diff` 为空。

## 风险（已识别）

done_when 文本标记脆弱（保留字表 + manual 逃生门）；运行时生成脚本质量方差（菜谱伪代码 + 强制验证步 + 只快照验证过的）；触发词抢占（负面清单）；提问疲劳（必问限五类 + 批量）；引擎升级 vs 旧 profile（profile_version 警告降级）；orient 膨胀纪律（contexts/variants 只做打印与跳过判定，问用户/嵌入运行永远是主 agent 照文档做）。

## 约束

沿用仓库纪律：绝不 `git add -A`，只按显式路径 stage；每任务原子提交；固化产出的薄技能是否入 git 主仓（含项目路径事实）在固化时问用户。
