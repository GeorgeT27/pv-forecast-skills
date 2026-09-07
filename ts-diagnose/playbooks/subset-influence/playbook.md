---
id: subset-influence
name: 训练条目/数据子集影响力归因
goal: 找出联合训练的 N 个训练条目（数据子集）里哪些拖累了留出单元的零样本预测（负迁移），并解释训练动力学（为什么不同 iteration/chunk 的 training loss 不同）
materials:
  required: [predict, truth]
  optional: [training_log, checkpoint, experiment_config, model_code]
upstream:
  - product: setup
    required: true
  - product: model_profile
    required: false
  - product: eval_report
    required: false
variants:
  - id: mode-b
    when: "material:checkpoint"
    unlocks_stages: [3, 5]
stages:
  - id: 0
    name: 回放分组（种子/指纹 → assignments.csv）
    done_when:
      artifacts: ["assignments.csv"]
    prereqs:
      - desc: sampler.n_iters（实际迭代数）已填
        check: "config:sampler.n_iters"
      - desc: （可选）Mode B 才需 adapter.py（回放采样用 checkpoint 指纹抽查）
        check: "material:checkpoint"
  - id: 1
    name: 训练动力学（loss 水平/收敛 ~ 条目成员 → chunk_loss_dynamics.json）
    done_when:
      artifacts: ["chunk_loss_dynamics.json"]
    prereqs:
      - desc: 回放已完成（Stage 0）
        check: "stage:0"
  - id: 2
    name: 影响力回归（Mode A 主证据 → influence_coefs.json）
    done_when:
      artifacts: ["influence_coefs.json"]
    prereqs:
      - desc: 回放已完成（Stage 0）
        check: "stage:0"
      - desc: 留出单元逐 chunk RMSE 序列已就位（日志解析或 ckpt_eval 重算，setup 长表或日志解析）
        check: "material:predict"
  - id: 3
    name: 梯度佐证 TracIn（Mode B → tracin_scores.json）
    done_when:
      artifacts: ["tracin_scores.json"]
    prereqs:
      - desc: 有可用 checkpoint（Mode B）
        check: "material:checkpoint"
  - id: 4
    name: 漂移解释（气候/分布距离 → 现象/假设）
    done_when:
      findings_marker: "现象"
    prereqs:
      - desc: Stage 2/3 已给出嫌疑条目
        check: "stage:2"
  - id: 5
    name: 确认（Mode B：微调探针 + 剔除重训 → 已证实/CONCLUSION）
    done_when:
      artifacts: ["CONCLUSION.md", "gate_reports/conclusion_gate.json"]
    prereqs:
      - desc: 有可用 checkpoint（Mode B）
        check: "material:checkpoint"
      - desc: Stage 2/3 已给出 top 嫌疑（且最好两法一致）
        check: "stage:2"
    subagent_ok: false
---

# subset-influence：训练条目/数据子集影响力归因（负迁移诊断 + 训练动力学）

场景：一个模型由 N 个训练条目联合训练。"训练条目"指任何可枚举、可整体加入或剔除的
训练数据单元（光伏场景通常是一个电站的全部数据，本 playbook 已泛化）。训练方式是
分块（chunk）顺序训练：每次迭代把 N 个条目随机重排进若干个 chunk，逐个 chunk 连续训
若干 epoch。

本 playbook 做**训练集构成 → 目标单元性能**的归因，回答两个问题：**负迁移归因**
（哪些条目拖累了留出单元的零样本预测）与**训练动力学**（训练 loss 为什么因 chunk
而异）。前身技能的续跑/直达脚本 run_orient.py 已废弃：引擎 orient 每次进入自动核对
产物、定位第一个未完成阶段，支持 `--goto` 直达。

## 1. 问题框定与首要陷阱

- **震荡本身不是罪证**。顺序分块训练下，留出单元的 RMSE 逐 chunk 上下震荡是**预期
  现象**，不是异常（灾难性遗忘所致，就算 N 个条目全是"好"条目曲线也会震）。"有害"
  必须定义为：**训练到条目 X 会系统性地把留出单元 RMSE 推高**——利用每次迭代重新
  随机分组这一天然随机化实验，在大量随机 chunk 上估计条目 X 的边际效应。禁止看到某
  chunk 后 RMSE 跳升就归咎当时在场的条目——那很可能只是遗忘。
- **loss 高 ≠ 有罪**。loss 量的是训练条目自己"难学"与否，不是它拖不拖累留出单元。
  分布冲突的典型指纹反而是 loss 低但 harm 高。四象限对照表见
  `references/influence-methods.md`。
- **两法一致才升级**。影响力回归（Stage 2）与梯度 TracIn（Stage 3，仅 Mode B）是两条
  独立证据线。只有两法排名一致（报 Spearman）时，嫌疑条目才能从"现象"升"假设"。
  单证据线不下"假设"级结论。
- **功效诚实**。迭代数 < 10 只报排名，不报显著性。分组样本不足只描述趋势，不下定论。
- **只有剔除重训改善才算"已证实"**。Stage 5（Mode B 专属）剔除嫌疑条目重训后，留出
  单元表现在多口径 + 配对显著性检验上确实改善，才可标"已证实"；其余一律停在
  "现象/假设"。

## 2. 两种证据模式（由材料自动识别，不用预选）

判定规则：`checkpoint` 材料 present 就走 Mode B（`mode-b` variant 激活，解锁
Stage 3/5，Stage 1 可加 `--from-ckpt`）；没有就走 Mode A（纯观测归因，零 GPU）。

| | **Mode A 观测归因（只有预测/日志）** | **Mode B 干预确认（有 checkpoint）** |
|---|---|---|
| 输入 | 逐 chunk 留出单元 RMSE 序列 + 种子回放代码（+ 日志里的 loss） | Mode A **加** checkpoint + 训练代码 |
| 阶段 | 0 回放 → 1 动力学（日志有 loss 才可）→ 2 影响力回归 → 4 漂移解释 | 上面全部 **加** 3 梯度 TracIn + 5 微调探针/剔除重训（且 1 可 --from-ckpt） |
| 证据 | 嫌疑条目**相关性排名** + loss 侧现象 | 独立方法佐证 + 因果确认 |
| 算力 | 几乎零 GPU，纯统计 | GPU 前/反向 + 少量重训 |

**关键前置**：任何一次进入本 playbook，orient 之后第一件事是跑一次
`<本 playbook 目录>/scripts/probe_logs.py`，同时探"逐 chunk 留出单元 RMSE"（Stage 2
因变量）与"逐 epoch training loss"（Stage 1 原料）的来源，然后据
`probe_summary.json` 决定路线：RMSE 已写进训练日志则 Mode A 全程不必碰权重文件，
没写进则靠 `ckpt_eval.py` 逐 checkpoint 重算；loss 没有记录、也拿不到 checkpoint 内的
loss，则 Stage 1 跳过，不阻塞主线。

## 3. 实验设定载入：project-context 实验线

"N 个条目分 K 个 chunk"这一类实验参数——条目全集、留出单元、chunk 方案、每 chunk
训多少 epoch、有几个模型——不硬编码在本 playbook 里，也不在会话里临场向用户逐项收集，
而是**经 `experiment_config` 材料 + project-context 实验线载入**：

1. `experiment_config` present → 从它指向的 project-context 实验线 json 里取：
   `held_out_station`/`held_out_station_slug`（留出单元 id）、`training_entries`
   （N 个训练条目，列表顺序就是回归设计矩阵的列序）、`chunking`（chunk 方案）、
   `models`。实验线没覆盖的字段保留【待补】，需要时向用户问一次并回填实验线 json；
   已载入的字段不重复问。
2. `experiment_config` absent，或实验线里确实没有某字段 → 照 `_playbook-spec.md` 的
   入口闸纪律向用户问，不臆造默认值。下文各阶段提到的"条目全集/留出单元/chunk 方案"
   都指此处载入（或补问）的值。
3. 工作目录配置文件 `influence_config.json`（字段清单见
   `<本 playbook 目录>/scripts/si_common.py` 头部）里的 `stations`/`test_station` 等
   键名是历史遗留，语义已泛化为"训练条目列表"/"留出单元 id"。脚本层不改字段名；
   正文一律用"训练条目/留出单元"表述。

## 4. 留出单元预测侧上游：eval_report 产物

留出单元的预测侧素材（指标基线、分组条件、数据质量、现象清单）来自 frontmatter
`upstream` 里声明的 `eval_report` 产物（可选），由 result-eval 生产。orient 按产物
状态给指令：

- **built/linked**：直接消费该工作目录。对应关系：指标表 = 留出单元基线；分组条件
  （如天气分型）= 归因分组变量；suspect_days.csv 一类质检产物 = 反驳门「数据质量」
  证据；FINDINGS 现象 = 归因素材；漂移类图产物可直接复用于本 playbook Stage 4。
- **absent**：orient 打三分支问用户（现跑 / 链接已有 / 放弃）。选"现跑"= 在会话根
  目录 `<root>/eval_report/` 内联执行 result-eval 至 CONCLUSION.md，登记
  `config.products.eval_report = {workdir, status: "built"}`。
- **declined**：继续 influence-only 分析，但 FINDINGS/CONCLUSION 须注明
  「缺预测侧上游」。

## 5. 逐阶段菜谱

复用脚本都在 `<本 playbook 目录>/scripts/`；`si_common.py` 里 data_utils 的复用路径
指向兄弟 playbook 的 `result-eval/scripts/data_utils.py`。

### Stage 0：回放分组

输入：`sampler.seeds` + `sampler.n_iters`（实际迭代数）、训练代码仓库根（Mode B 的
adapter 要从这里导入采样器/模型类）。

菜谱：`replay_assignments.py` 用训练同款 RNG 复现每次迭代把 N 个训练条目重排进 K 个
chunk 的分组结果。Mode B 下额外做 checkpoint 指纹抽查验证回放：训完某个 chunk 后，
模型对该 chunk 成员条目的 RMSE 改善应该最大；若回放出的成员与"改善 Top-k"重叠
<60%，就判回放不可信。回放不可信时的兜底方案见
`references/influence-methods.md`「Stage 0」节。

done：`assignments.csv` 落盘。

### Stage 1：训练动力学

输入：Stage 0 的 `assignments.csv`；一个 loss 记录源，三选一：现成的
`loss_records.csv`、probe 报 `loss_found`（解析原始日志）、或 Mode B 下用
`--from-ckpt` 从 checkpoint 里取。

菜谱：`loss_dynamics.py` 对每个 (model, iteration, chunk) 组合算三个指标：
`final_loss`（尾 3 epoch 均值）、`conv_slope`（log(loss)~epoch 的回归斜率）、
`plateau_epoch`（第几个 epoch 进入平台期）。然后对训练条目做与 Stage 2 完全同款的
回归设计——"中心化指示 + 岭回归 + 控制变量"（直接 import 复用
`influence_regression` 的实现），只是因变量从 RMSE 换成 loss 指标。

**没有任何 loss 记录源时，本阶段仍需落盘一个带 `status: "skipped"` 和
`reason: "no_loss_source"` 的 `chunk_loss_dynamics.json`，然后继续主线；Mode B 可从
checkpoint 提取，training_log 则在材料 present 时解析。**

解读：拿到 `highest_final_loss_entries`/`slowest_converging_entries` 两个排名后，连接
project-context 的条目档案与 event-log：高 loss + 分布远 = 预期内的难拟合，不是问题；
高 loss + 分布平凡却难学 = 数据质量红旗，走 suspect_days/event-log 核查。

**逐模型独立分析，绝不跨模型 pool loss**：loss 数值跨模型不可比，只比 Spearman 排名。

done：`chunk_loss_dynamics.json` 落盘。

### Stage 2：影响力回归

输入：Stage 0 的 `assignments.csv`；留出单元逐 chunk RMSE 序列（`rmse_series.csv`，
来源是日志解析或 `ckpt_eval.py` 重算）。

菜谱：`influence_regression.py`。因变量先按全局训练顺序 `(iteration, position)` 差分：
`ΔRMSE(i,c) = RMSE_留出单元(训完 chunk c) − RMSE_留出单元(训完上一个 chunk)`（消掉
训练整体慢趋势）。条目指示变量与截距/size 控制共线（每次迭代每个条目恰好进一个
chunk），用"中心化条目指示 + 岭回归"处理。系数 θ_entry 读作**相对平均条目的相对
有害度**（sum-to-zero 语义）：排名与相对比较有效，绝对数值别过度解读。控制变量：
`iteration`/`position`/`size`。Bootstrap 给每个系数 95% CI，**CI 排除 0 才算方向
可信**；迭代 < 10 只报排名不报显著性（`power_note` 字段会提示）。方法细节见
`references/influence-methods.md`「Stage 2」节。

done：`influence_coefs.json` 落盘。

### Stage 3：梯度佐证 TracIn（`mode-b` variant，仅 checkpoint present 时解锁）

输入：checkpoint 序列 + `adapter.loss_gradient`（用户按 `scripts/adapter_template.py`
模板填好的 adapter.py）。

菜谱：`tracin_influence.py` 在多个 checkpoint 上计算训练条目梯度与留出单元梯度的
余弦式归一内积 `⟨g_entry, g_heldout⟩`，再累加。内积持续为负 = 训练该条目把参数推离
留出单元（有害）。输出 `harm_score = −Σ cos(...)`（数值高 = 拖累，与 Stage 2 的
θ_entry 同向）。降成本手段：`--every N`（每 N 个迭代取一个 checkpoint）、
`--n-windows`（每条目取多少窗口）、`params_filter`（只取部分参数的梯度）。多卡分片时
各写各的 `--out`，主 agent 合并原始 CSV 后重跑一次汇总。

与 Stage 2 的关系：两条**独立**证据线。脚本报两两 Spearman；**排名一致的条目才从
"现象"升"假设"**。

done：`tracin_scores.json` 落盘。**Mode A 下本阶段不激活（variant 未命中），orient 标
"跳过不阻塞"，不是失败。**

### Stage 4：漂移解释

输入：Stage 2/3 给出的嫌疑条目列表；逐条目的训练数据（用来算分布距离/天气型/kt 等）；
`eval_report` 产物为 built/linked 时，其漂移产物可直接复用。

菜谱：复用 result-eval 的 `run_drift.py`（跨数据集 PSI/天气型/kt，逐条目对比），回答
"嫌疑条目为什么分布远/为什么有害"。产出只到现象/假设级条目（对应 frontmatter 的
`findings_marker: "现象"`）——只写"看到了什么"，不越过升级门槛写"已证实"。

done：`FINDINGS.md` 含"现象"标记。

### Stage 5：确认（`mode-b` variant，仅 checkpoint present 时解锁）

输入：Stage 2/3 给出的 top 2-3 嫌疑条目（最好是两法排名一致的）。

菜谱：两步协议（细则见 `references/attribution-discipline.md`「Stage 5 确认协议」）。
第一步**便宜探针**：从最终 checkpoint 出发，只在单个 top 嫌疑条目上短暂微调，测留出
单元验证集的 ΔRMSE，方向对（微调它 → 留出单元变差）= 一阶因果信号。第二步**决定性
检验**：剔除 top 2-3 嫌疑条目**重训一次**，与原全量训练同种子同协议，对留出单元做
多口径对比 + 配对显著性检验（复用 result-eval 指标流水线的按天配对显著性门槛工具），
过了才升"已证实"；若剔除反而变差 → 推翻假设，回头查是不是遗忘伪装或回放错位误报。

`CONCLUSION.md` 面向管理层写："哪些条目（与留出单元分布差异最大）系统性拉低留出
单元预测，剔除后留出单元指标改善多少"。方法论机器（回归/TracIn/显著性检验）不进
正文，末尾一句话说可信度。结尾附**给未来训练的建议**：逐 chunk 组成与逐 epoch loss
落结构化日志；混条目 batch 或回放缓冲抑制遗忘；相似度加权采样偏向部署目标的分布。

done：`CONCLUSION.md` 落盘。**Mode A 下本阶段不激活，orient 标"跳过不阻塞"。**
frontmatter 标了 `subagent_ok: false`——因果确认必须主 agent 亲自做，不得外包
subagent。

## 6. 证据升级规则

两条证据线（`evidence_lines`）：Stage 2 影响力回归、Stage 3 TracIn 梯度（仅 Mode B
可用）：

- **现象**：Stage 2 回归给出 θ_entry 排名（迭代 ≥10 时要求 CI 排除 0）。Stage 1 的
  loss 效应排名同样只到"现象"级，且属于 loss 侧现象，必须注明，不可当成负迁移排名。
- **假设**：Stage 2 与 Stage 3 排名一致（Spearman 显著为正，且该条目在两法里都靠前）
  + Stage 4 给出可解释机制（分布距离/映射差异），并登记一条假设。Mode A 下没有
  Stage 3，两证据线机制不适用——单证据线（仅 Stage 2）不得升"假设"，只能停在
  "现象"，除非用户明确接受降级举证标准（记入 open-questions）。
- **已证实**：Stage 5 剔除该条目重训后，留出单元在多口径 + 配对显著性检验上确实改善，
  且过反驳门。
- **被推翻**：剔除重训无改善，或反驳门发现存在数据质量/训练顺序等替代解释。

跨阶段单调：没到条件不许跳级。只拿着回归排名就写"已证实"，是本 playbook 的头号错误。

## 7. 停顿点与汇报

Stage 4（漂移解释产出现象清单）完成后，向用户汇报嫌疑条目清单：按证据线分组、标注
两法排名是否一致。然后请用户点名要不要进 Stage 5 做因果确认（仅 Mode B 有此选项）。
Stage 5 若激活，收尾时把 `CONCLUSION.md` 的内容（含关键数字）直接展示给用户。

## 8. subagent 拆分建议

重活（逐 checkpoint 评估、TracIn、动力学提取、嵌入跑 result-eval、逐条目漂移）外包给
subagent，固化 brief 见 `references/subagent-briefs.md`。可并发外包的拆法：Stage 2
补料（ckpt_eval 按模型分片）、Stage 3 TracIn（单卡就派一个跑全量，多卡才分片）、
Stage 1（probe → 解析 loss → loss_dynamics，只回数字排名）、Stage 4（run_drift 逐条目
漂移，回现象清单）。Stage 5 因果确认与最终结论/反驳门的综合判断，主 agent 亲自做。

**单写者纪律**：`diagnose_state.json`/`PROGRESS.md`/`FINDINGS.md`/`influence_config.json`
只由主 agent 写。subagent 只读结构化的 JSON/CSV（checkpoint/原始日志/PNG 永不进
上下文），只写脚本产物与自己的分片文件。

## 9. 结论模板与本 playbook 特有反驳门条目

结论模板见引擎 `references/conclusion-reporting.md`。反驳门 = 下结论前必须逐条排除的
替代解释清单，本 playbook 特有条目如下（细则见
`references/attribution-discipline.md`）：

- **遗忘伪装**：ΔRMSE 冲击会不会只是训练顺序/新近效应？看第二因变量（区分"排最后
  才有害"与"任意位置都有害"），并确认控制 `position` 后 θ_entry 仍显著。
- **样本量**：该条目出现次数够吗（出现次数 ≈ 迭代数）？迭代 <10 一律降级。
- **数据质量红旗**：该条目分布与留出单元**相似却有害** = 强烈提示数据质量问题（原始
  记录异常/预报偏差/传感器故障），不是"分布冲突"。核查路径：走 `eval_report` 产物的
  质检产物（built/linked 时 `suspect_days.csv` 现成）+ project-context event-log 查该
  条目原始数据。确认是数据问题就修数据，别删条目。
- **回放错位**：assignments 过了指纹校验吗？没过 → θ_entry 归错了条目，先修 Stage 0。
- **单证据线**：只有回归、没有 TracIn 佐证（或 Mode A 结构性没有 Stage 3）？→ 只能
  停在"现象"。
- **口径/评估错**：留出单元指标是不是用了错的 label 列或取点口径？
- **共享上游**：若"有害"只在共享同一上游组件（如同一预训练基座）的模型子集里同时
  出现、其余模型无感，那可能是上游组件的问题而非条目本身。跨模型 Spearman 帮助判别。

## 10. 材料降级说明

- `predict`/`truth` 缺：不可做。`training_log` 缺：Stage 1 可从 checkpoint 提取；
  两者都缺时写入 skipped 产物并继续 Stage 2，结论声明未做训练动力学。
- `checkpoint` 缺：走 Mode A。Stage 3/5 结构性不适用（`mode-b` variant 不激活），归因
  停在"现象/假设"，不可升"已证实"。若仍需产出 `CONCLUSION.md`，须显式标注"未做
  因果确认，仅观测归因"。
- `experiment_config` 缺：无法从 project-context 实验线自动载入条目全集/留出单元/
  chunk 方案。须逐项向用户问齐并写入工作目录配置。不阻塞主线，但每次进入都要重新
  确认，无法复用实验线记忆。
- `model_code` 缺：不影响主线归因。只是核验模型架构相关假设（如"某条目只对特定架构
  有害"）时少一路交叉验证来源，缺席记入 `open-questions.md`。

## 11. chartbook 覆盖声明

本 playbook 不产出 chartbook 图——frontmatter 里没有任何阶段声明 `charts:`（主线
产物是 JSON/CSV 统计量）。留出单元的预测侧可视化由 `eval_report` 产物（result-eval
playbook）负责；Stage 4 的漂移可视化复用 result-eval 的 `train-test-drift` 一类图
产物，不在本 playbook 内重复声明。

## 12. 运行后回顾

每次实跑暴露的问题按类型写回对应位置：脚本 bug/字段名问题改
`<本 playbook 目录>/scripts/`；指令歧义/缺步骤改本文件；确认的新项目事实（条目档案/
event-log）补 project-context；方法类知识补 `<本 playbook 目录>/references/`。

"给未来训练的建议"固定写进结论：逐 chunk 组成与逐 epoch loss 直接落结构化日志；
并考虑混条目 batch / 小回放缓冲来抑制遗忘震荡。
