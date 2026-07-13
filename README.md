# 光伏功率预测结果分析 —— Claude Code 技能包

三个配套技能：

| 技能 | 用途 |
|------|------|
| [`pv-result-analysis`](pv-result-analysis/SKILL.md) | 预测结果评估与归因分析：五口径指标（metric.py）、12 图谱、月度变差/模型对比诊断 Playbook、分布漂移诊断；**自带续跑能力**（每次进入先跑 `scripts/run_orient.py` 定位阶段、跳过已完成步骤、`--goto N` 直达）；`references/` 为项目知识库（模型档案/电站/事件/气候），`scripts/` 为固化的分析与画图代码 |
| [`pv-model-verify`](pv-model-verify/SKILL.md) | 对照真实代码仓库核验 M1-M4 模型档案（`references/models.md`），以代码为准修正口述记录、补齐待确认项 |
| [`pv-station-influence`](pv-station-influence/SKILL.md) | 17 站分块训练的站点影响力归因：找出哪些训练站拖累留出测试站（白马湖）的零样本预测（负迁移），观测归因（Mode A）/ 梯度重训确认（Mode B） |

## 安装

Claude Code 要求 `~/.claude/skills/` 下每个一级子目录直接包含 `SKILL.md`，
所以**不能把整个仓库放进 skills 文件夹**，而是 clone 后分别 symlink 各子目录：

```bash
git clone https://github.com/GeorgeT27/pv-result-analysis.git
cd pv-result-analysis
ln -s "$(pwd)/pv-result-analysis"   ~/.claude/skills/pv-result-analysis
ln -s "$(pwd)/pv-model-verify"      ~/.claude/skills/pv-model-verify
ln -s "$(pwd)/pv-station-influence" ~/.claude/skills/pv-station-influence
```

之后 `git pull` 更新仓库，技能自动同步。

## 运行依赖

分析脚本需要的 Python 包：

```bash
pip install -r requirements.txt
```

## 使用

- 结果分析：调用技能时提供**训练集 parquet、测试集（true label）parquet、metric.py** 三个路径，
  以及各模型（M1-M4/ensemble）的 predicted parquet 路径。
- 模型档案核验：`/pv-model-verify` 并给出模型代码仓库路径。
- `references/models.md` 中 `<!-- 待确认 -->` 注释标记的字段为尚未证实的信息，
  分析结论不得引用；核验命令会自动把它们列入清单。
