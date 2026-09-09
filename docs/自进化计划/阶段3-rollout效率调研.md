# 阶段 3 补充调研:rollout 太长太贵怎么办(2026-08-14,四路并行深查)

触发:阶段 3 单次 rollout(全程盲跑)约 30-60 分钟、大量 token;11 迭代例 + 4 holdout、每轮 2-5 个候选编辑的规模下,全量评估 = 3×11×2 = 66 次/轮,不可持续。四路调研:① GEPA 系预算机制 ② 模块级评估/部分 rollout 先例 ③ 评估预算分配算法 ④ 单次 rollout 执行层省钱。所有结论带一手来源,原始报告见本次会话记录。

## 一、两条省钱轴 + 一条设计验证轴

### 轴 A:少跑 rollout(循环调度层)

| 机制 | 省多少 | 难度 | 来源 |
|---|---|---|---|
| **两级评估闸**:新候选先只在 2-3 个筛选案例上盲跑,赢过父候选才晋级全量;否则丢弃 | 被否候选成本 11 次→2-3 次;GEPA 省 35x 的最大单一来源 | 低 | GEPA Algorithm 1(arXiv:2507.19457),官方默认 reflection_minibatch_size=3 |
| **(候选,案例) 分数永久缓存 + Pareto per-instance 记账**:incumbent 与池内候选绝不重评;保留"至少在一个案例上最优"的候选 | 每轮 incumbent 的 22 次评估→0 | 极低 | gepa-ai/gepa `cache_evaluation` + `val_evaluation_policy`(一手验证 api.py) |
| **irace 竞速纪律**:每候选先评满 5 例才允许淘汰(firstTest=5),之后逐例做案例级配对检验(同案例差分挡住案例难度方差);2 候选时用 Wilcoxon 符号秩 | 每轮 66 次→约 25-35 次 | 中 | irace 官方默认(Friedman/配对 t);Miller "Adding Error Bars to Evals"(arXiv:2411.00640):比较两版本必须用案例级配对差 |
| **序贯加评**:第 2 次重复只加评"分差落在该案例历史噪声带内"的案例;分差远超噪声带的不用重复 | 第 2 遍 22 次→5-12 次 | 低 | SQRS(arXiv:2112.12438)/SPRT 思想 |
| **rejected-edit buffer**:被验证门否掉的编辑存档喂给后续反思,失败 rollout 的信号复用而非丢弃;每步最多 4 个编辑(文本学习率) | 反思零 rollout 成本持续产负梯度 | 低 | SkillOpt 配置一手核对(microsoft/SkillOpt) |
| 案例排序:编辑影响(覆盖矩阵)+ 历史判别力(翻转率)优先 | 让竞速淘汰更早发生 | 低 | 回归测试选择思想移植;**注意:无已发表工作、无安全保证,只能做排序不能做剪枝,每 3-4 个编辑全量兜底一次** |

**明确不采用**:Hyperband/successive halving/ASHA/IRT 类(HbBoPs 附录一手警告:~10 个验证实例时噪声主导,这类算法的收益轴"大验证集只跑一小部分"在 11 例下不存在);MIPROv2(源码核对:valset≤50 时 minibatch 机制整个失效)。

### 轴 B:单次 rollout 变便宜(执行层)

| 机制 | 省多少 | 难度 | 来源 |
|---|---|---|---|
| **消融训练内容寻址缓存**:`(脚本hash, 数据hash, config, seed) → metrics+产物` 跨 rollout/跨轮持久化;盲跑 agent 的重复训练直接查表 | 单次墙钟约一半;重复盲跑同案例时训练时间→0 | 低(一天) | TVCache(arXiv:2602.10986,RL rollout 工具缓存,命中 70%/提速 6.9x);我们场景是纯函数,比它更干净 |
| **种子并行 + 假设并行(带信息屏障)**:3 种子 shell 层并行砍 2/3 训练墙钟;并行验证多假设时,结果落盘但在 ledger 登记 receipt 前对主 agent 不可读 | 墙钟大头 | 低-中 | Anthropic 多代理系统(墙钟 -90%、token ×15 的权衡);staged preregistration(arXiv:2606.11217):预登记决策规则而非等结果 |
| **context editing + 大产物离盘**:图表/长表/训练日志只落盘,上下文留路径+一行摘要 | token -84%、性能反升 29%(Anthropic 一手实测) | 低 | claude.com/blog/context-management |
| 沙箱快照分叉:数据准备/探索完成后克隆目录,多假设分叉验证 | 免重复准备 | 低 | 学术系统(BranchFS/DeltaBox)在解毫秒级难题;我们用 git worktree / APFS `cp -c` 即拿 80% 收益 |
| 便宜模型探索+强模型判定 | 未知 | — | **文献空白**(现有量化全在查询级路由),要做就是自己造证据;放最后 |

### 轴 C:"中途起跑 + 首次分歧"设计的文献判决

**支持**:
- 阶段隔离评估有直接先例:Cybench subtask-guided mode(给前序 gold 答案)、SWE-bench oracle retrieval、RAG gold-context 评生成器;信号密度远高于端到端 all-or-nothing。
- Agent-as-a-Judge(ICML 2025):judge 主动查**产物**而非读原始轨迹,与人一致率 60-70%→约 90%——正中我们"阶段产物链"设计。
- Who&When(ICML 2025):LLM 从失败日志定位决定性错误步准确率仅 **14.2%**——所以首次分歧必须用冻结产物的**确定性/结构化比对**完成,不能靠 LLM 判(我们的 schema 化 ledger 恰好支持)。

**四条警告(设计时必须吃进)**:
1. **暴露偏差 agent 版**(MOTAB,arXiv:2605.19433):gold 输入下的阶段分系统性高估端到端表现。对策:保留小比例全程 rollout 专测"组合差距",像 Cybench 一样 guided/unguided 两列都报。
2. **首次分歧 ≠ 首个错误**:同一案例存在多条合法路径(不同但同真的切片方式/假设)。对策:gold 侧为切片/假设建等价类(C1 审计时已提过"真因等价表述列全"),分歧判定落在等价类层;否则误杀最有创造性的 rollout(DataPRM 的"误罚合法探索")。
3. **silent error**:阶段 judge 只读产物文本抓不到"不报错但算错"。对策:判定器主动重执行/核算产物(我们的 slice_zcheck 类脚本本来就是重算式,保持)。
4. **阶段分进优化循环即成可 hack 的 proxy**(PRM 文献反复记录):阶段隔离分数只用于**诊断与快速迭代**,验证门的采纳判定必须用全程 rollout + holdout(阶段 3 文档原有纪律,文献背书)。

另:早停(检测到不可救即中止 rollout)有成熟工作(Doomed from the Start,省 40-60% token 且误杀率受控),但需要校准基础设施,标记为后期可选。

## 二、落地顺序建议(按 收益×难度)

1. 消融训练缓存(轴 B1)——一天,单次墙钟减半;
2. (候选,案例) 分数缓存 + incumbent 免重评(轴 A2)——配置级;
3. 两级评估闸:2-3 筛选案例 minibatch(轴 A1)——循环骨架规则;
4. context editing + 产物离盘纪律(轴 B3)——playbook 已半强制,补全;
5. 种子并行 + 信息屏障(轴 B2);
6. irace 配对竞速 + 序贯加评(轴 A3/A4)——第 2-3 轮循环再上(第 1 轮先手动全量,顺便攒每案例噪声带);
7. 中途起跑阶段隔离(轴 C)——带四条警告落地,只用于诊断迭代,不进验证门。

## 三、其他值得知道的

- DSPy 官方对小数据的建议:"整个数据集同时当 trainset 和 valset,接受过拟合风险换优化深度"——我们因有 holdout + 改述变体,比这个默认建议更稳。
- RoboPhD(arXiv:2604.04347):紧预算下取消 train/val 切分、用 Elo 锦标赛同时完成评估+选择,3/4 基准超 GEPA Pareto——若将来预算更紧可考虑。
- GEPA+(ROMA,arXiv:2602.01848):560→150 次 metric call(数字未逐字核对);TextBO(arXiv:2511.12063)可叠加在 GEPA 上。
- ProcessBench 的 F1 形态(有错样本检出率 × 全对样本不误报率的调和平均)是阶段判定器该采用的指标。
- 评测成本实录(EvalEval 2026):scaffold 选择就能造成同任务 33 倍成本差——harness 本身值得被优化。
