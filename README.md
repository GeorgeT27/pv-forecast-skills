# 光伏功率预测结果分析 —— Claude Code 技能包

三个配套技能：

| 技能 | 用途 |
|------|------|
| [`pv-result-analysis`](pv-result-analysis/SKILL.md) | 预测结果评估与归因分析：五口径指标（metric.py）、12 图谱、月度变差/模型对比诊断 Playbook、分布漂移诊断；**自带续跑能力**（每次进入先跑 `scripts/run_orient.py` 定位阶段、跳过已完成步骤、`--goto N` 直达）；`references/` 为项目知识库（模型档案/电站/事件/气候），`scripts/` 为固化的分析与画图代码；实验设定（站点/划分/路径）经 project-context 载入 |
| [`pv-model-analysis`](pv-model-analysis/SKILL.md) | 从模型代码仓库生成代码锚定的模型参考（工程流程图 + 逐方法数学 + 架构→结果分析含义桥接），产物存 `<repo>/.modelmap/`，经 `model-ref.pointer` 供 pv-result-analysis 消费；亦可按代码增量核验 |
| [`pv-station-influence`](pv-station-influence/SKILL.md) | 多站分块训练的站点影响力归因：找出哪些训练站拖累留出测试站的零样本预测（负迁移），观测归因（Mode A）/ 梯度重训确认（Mode B）；实验设定经 project-context 载入 |

## 安装

Claude Code 要求 `~/.claude/skills/` 下每个一级子目录直接包含 `SKILL.md`，
所以**不能把整个仓库放进 skills 文件夹**，而是 clone 后分别 symlink 各子目录：

```bash
git clone https://github.com/GeorgeT27/pv-forecast-skills.git
cd pv-forecast-skills
ln -s "$(pwd)/pv-result-analysis"   ~/.claude/skills/pv-result-analysis
ln -s "$(pwd)/pv-model-analysis"    ~/.claude/skills/pv-model-analysis
ln -s "$(pwd)/pv-station-influence" ~/.claude/skills/pv-station-influence
```

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
