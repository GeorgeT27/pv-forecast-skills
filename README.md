# 光伏功率预测结果分析skill —— Claude Code 技能包

单一入口技能 —— 一个泛化时序诊断引擎，13 个可插拔 playbook，**两层结构**（生产者 playbook 产出持久化产物，分析 playbook 声明上游依赖消费之，orient 机器裁决先后）：

| 技能 | 用途 |
|------|------|
| [`ts-diagnose`](ts-diagnose/SKILL.md) | **泛化时序诊断引擎**：同一套已验证 workflow（orient 续跑、事实/解释隔离、结论三道门、多证据线、提问一等公民、生成闸+归因闸）+ 13 个可插拔 playbook（分两层：生产者/分析），覆盖时序/预测任务的全部诊断与评估目标；成熟运行可经 crystallize 固化成薄的已固化代理技能；14 张 agent 卡片（`agents/`）+ 三钩子（`hooks/`），`ts-diagnose/INSTALL.md` 一键装到任意 Claude Code 设备 |

### 13 个 playbook（两层）

**生产者层（level-1）——产出持久化产物供下游复用：**

| playbook | 产物 | 用途 |
|---|---|---|
| `data-setup` | `setup`（**全部分析目标的必需前置**，缺了引擎自动先跑） | 原始预测/真值 → 规范长表 + 对齐报告 + manifest（材料清单含训练日志位置、输入指纹过期检测） |
| `model-audit` | `model_profile`（可选） | 给定模型代码目录：分析模型/生成模型档案/核验描述与代码一致 |
| `fact-scan` | `chart_sweep`（可选） | 只想体检/把标准分析图画一遍/看现象不要结论；产物供分析 playbook 复用免重画 |
| `metric-eval` | `metric_table`（可选） | 只算指标不归因/给我指标表（默认 rmse_192）；产物供 result-eval/model-comparison 口径匹配即复用 |

**分析层（level-2）——声明上游产物依赖，各自只留目标核心菜谱（`result-eval` 兼产 `eval_report`，供 `subset-influence` 等下游可选复用）：**

| playbook | 用途 |
|---|---|
| `training-sufficiency` | 训练是否充分 / batch 或数据量不足 / chunk·fold 构成与分配 / loss 震荡收敛慢 |
| `robustness` | 结论或模型在扰动、分组切片、子期下稳不稳 |
| `feature-importance` | 哪个输入变量对误差/目标指标影响最大；有 feature_true 对照的预测特征质量归因与反事实验证 |
| `model-comparison` | 为什么模型 A 比 B 好/差、多模型对比归因（已按两层改造的试点：图 14→5、阶段 5→4） |
| `deployment-drift` | 上线/部署后是不是退化了、误差从什么时候开始变大、漂移诊断 |
| `result-eval` | 评估一次预测结果 / 算指标（默认 rmse_192）/ 月度或时段归因 / 深度分析 |
| `subset-influence` | N 个训练条目里哪些拖累留出目标（负迁移）/ chunk loss 震荡解释 |
| `architecture-attribution` | 提出假设后的验证主脊：噪声底 + 切片 z 检验 → 假设账本校验 → 单变量消融干预（每条干预派 `architecture-attribution-worker` 重训 ≥3 种子）→ 确认/否证/未决三态判定；结论只在出口过 conclusion_gate |
| `model-improve` | 改进环：账本里的改进假设（或可干预开关）排成候选，按轮批跑 ≥3 种子重训、与冠军比、留好弃坏；预算/轮数/连续无 keep 三条停止规则由 `experiment_log.py` 守；测试集封存只在收敛后评一次；Claude Code 下一轮候选经 `workflows/ts-train-batch.js` 并行派 `model-improve-worker` |

（分层机制已全量落地：4 生产者 + 9 分析 playbook 全部声明上游；contexts 机制已退役。）

## 引擎的运作方式

- **路由优先级（写死在 SKILL.md 路由表，勿改丢——有 CI 守卫）**：已固化代理技能 > 本引擎。命中已固化场景直接短路用固化技能；其余诊断与评估目标一律由引擎的 13 个 playbook 覆盖。分析 playbook 声明的必需上游产物（如 `setup`）缺失时 orient 打自动内联生产指令，可选上游（模型档案/图谱体检）缺失时三分支问用户——先后次序由引擎裁决，不靠使用者记。
- **不确定处必问**：引擎按提问纪律 AskUserQuestion，绝不假设；都不像现有 playbook → 先跑 orient 看菜单再与用户确认。
- **泛化 → 特化（crystallize）**：按 `ts-diagnose/references/crystallize.md` 固化成薄的已固化代理技能（SKILL.md 触发词 + profile.yaml 已答问题 + 验证过的脚本快照）——下次同类任务不再重复提问；workflow 留在引擎，引擎升级时薄技能自动受益。转正门槛 = **三关判据**（多样性 ≥N 个互异 case / held-out 留出场景 / 快照金标准自洽，`scripts/crystallize_gate.py` 判定），与人工技能同等可信才放行。
- **质量闸**：引擎运行时生成的分析代码要先过**生成闸**（`scripts/gen_gate.py`：静态检查 + 每 playbook 自带的金标准基线算对了才许碰真实数据）；结论必附**归因闸** provenance 块（代码 hash + 数据 hash，两次结论不同可判是代码变了还是数据变了）。
- **新目标扩展**：按 `ts-diagnose/playbooks/_playbook-spec.md` 写新 playbook，orient 直接执行其 frontmatter（先跑 `ts-diagnose/scripts/tests` 的 pytest 确认可解析）。

## 安装

Claude Code 要求 `~/.claude/skills/` 下每个一级子目录直接包含 `SKILL.md`，
所以**不能把整个仓库放进 skills 文件夹**，而是 clone 后分别 symlink 各子目录：

```bash
git clone https://github.com/GeorgeT27/pv-forecast-skills.git
cd pv-forecast-skills
ln -s "$(pwd)/ts-diagnose"          ~/.claude/skills/ts-diagnose
```

（crystallize 产出的新薄技能同样各自 symlink 一条。）

之后 `git pull` 更新仓库，技能自动同步。

仓库顶层 project-context/ 是当前项目实例的站点注册表与实验线配置（换项目整目录替换）。

## 运行依赖

分析脚本需要的 Python 包：

```bash
pip install -r requirements.txt
```

## 使用

- `/ts-diagnose` 并描述诊断目标（见上方 13 个 playbook 表）；引擎先跑 orient 定位阶段/匹配 playbook，
  首次进入会经 AskUserQuestion 选定/新建 project-context 实验线（站点、数据路径问一次落盘复用）。
- 结果评估（`result-eval`）：给 训练集 parquet、测试集（true label）parquet、metric.py 路径，默认口径 rmse_192。
- 模型档案生成/核验（`model-audit`）：给出模型代码仓库路径，产出 `.modelmap/`，供其余 playbook 消费。
- 模型参考（`.modelmap/models.md`）中未带 ✅/📊/📐 置信标签或标 ⚠️/待确认的字段为尚未证实的信息，
  分析结论不得引用；`model-audit` 产出时会把它们列入 `open-questions.md`。
