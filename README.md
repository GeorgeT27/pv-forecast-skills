# 光伏功率预测结果分析 —— Claude Code 技能包

三个配套技能 + 一个泛化诊断引擎：

| 技能 | 用途 |
|------|------|
| [`pv-result-analysis`](pv-result-analysis/SKILL.md) | 预测结果评估与归因分析：五口径指标（metric.py）、12 图谱、月度变差/模型对比诊断 Playbook、分布漂移诊断；**自带续跑能力**（每次进入先跑 `scripts/run_orient.py` 定位阶段、跳过已完成步骤、`--goto N` 直达）；`references/` 为项目知识库（模型档案/电站/事件/气候），`scripts/` 为固化的分析与画图代码；实验设定（站点/划分/路径）经 project-context 载入 |
| [`pv-model-analysis`](pv-model-analysis/SKILL.md) | 从模型代码仓库生成代码锚定的模型参考（工程流程图 + 逐方法数学 + 架构→结果分析含义桥接），产物存 `<repo>/.modelmap/`，经 `model-ref.pointer` 供 pv-result-analysis 消费；亦可按代码增量核验 |
| [`pv-station-influence`](pv-station-influence/SKILL.md) | 多站分块训练的站点影响力归因：找出哪些训练站拖累留出测试站的零样本预测（负迁移），观测归因（Mode A）/ 梯度重训确认（Mode B）；实验设定经 project-context 载入 |
| [`ts-diagnose`](ts-diagnose/SKILL.md) | **泛化时序诊断引擎**：同一套已验证 workflow（orient 续跑、事实/解释隔离、结论三道门、多证据线、提问一等公民）+ 可插拔 playbook（训练充分性 / 鲁棒性 / 变量重要性）；面向三个专用技能不覆盖的**新诊断目标**；成熟运行可经 crystallize 固化成新的薄专用技能 |

## 引擎与专用技能的关系

- **专用技能优先**：光伏结果评估 → pv-result-analysis；训练站负迁移归因 → pv-station-influence；模型档案 → pv-model-analysis。这三个是引擎概念上的"已固化实例"**先例**——先于引擎存在、不经 profile 机制、原样保留维护。
- **新诊断目标走引擎**：换一个关注点（如"训练是否充分 / batch 是否不足 / chunk 分配有没有问题"）用 `ts-diagnose` + 对应 playbook；不确定处引擎按提问纪律 AskUserQuestion，绝不假设。
- **泛化 → 特化（crystallize）**：一次成功运行后按 `ts-diagnose/references/crystallize.md` 固化成薄专用技能（SKILL.md 触发词 + profile.yaml 已答问题 + 验证过的脚本快照）——下次同类任务不再重复提问；workflow 留在引擎，引擎升级时薄技能自动受益。
- **新目标扩展**：按 `ts-diagnose/playbooks/_playbook-spec.md` 写新 playbook，orient 直接执行其 frontmatter（先跑 `ts-diagnose/scripts/tests` 的 pytest 确认可解析）。

## 安装

Claude Code 要求 `~/.claude/skills/` 下每个一级子目录直接包含 `SKILL.md`，
所以**不能把整个仓库放进 skills 文件夹**，而是 clone 后分别 symlink 各子目录：

```bash
git clone https://github.com/GeorgeT27/pv-forecast-skills.git
cd pv-forecast-skills
ln -s "$(pwd)/pv-result-analysis"   ~/.claude/skills/pv-result-analysis
ln -s "$(pwd)/pv-model-analysis"    ~/.claude/skills/pv-model-analysis
ln -s "$(pwd)/pv-station-influence" ~/.claude/skills/pv-station-influence
ln -s "$(pwd)/ts-diagnose"          ~/.claude/skills/ts-diagnose
```

（crystallize 产出的新薄技能同样各自 symlink 一条。）

之后 `git pull` 更新仓库，技能自动同步。

仓库顶层 project-context/ 是当前项目实例的站点注册表与实验线配置（两技能共享；换项目整目录替换）。

## 运行依赖

分析脚本需要的 Python 包：

```bash
pip install -r requirements.txt
```

## 使用

- 结果分析：首次进入会经 AskUserQuestion 选定/新建 project-context 实验线（站点、数据路径问一次落盘复用）；也可直接给 训练集 parquet、测试集（true label）parquet、metric.py 路径。
- 模型参考生成/核验：`/pv-model-analysis` 并给出模型代码仓库路径（产出 .modelmap，供 pv-result-analysis 消费）。
- 模型参考（`.modelmap/models.md`）中未带 ✅/📊/📐 置信标签或标 ⚠️/待确认的字段为尚未证实的信息，
  分析结论不得引用；pv-model-analysis 产出时会把它们列入 `open-questions.md`。
